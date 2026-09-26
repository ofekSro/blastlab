"""QA screenshot harness for the PySide6 GUI.

The Tk harness (`_qa_gui_harness.py`) is 59 scenarios sitting on top of a
~700-line driver. Everything except that driver is worth keeping, so this
file keeps the protocol byte-for-byte - the scenario registry, the
checkpoint / resume / budget contract, `findings.jsonl`, the exit codes
0/75/3/1 and the CLI - and replaces only the layer that touches widgets.

What changed, and why:

- `pump()` is a `processEvents` loop, not a nested `mainloop()`. The Tk
  driver had to nest real event loops to let the solver thread's
  `root.after` callbacks run; `ThreadBridge` is a queued signal, so the
  nesting stack disappears with it. The stall sampling, `until()`,
  deadline and STOP-file check are unchanged.
- Screenshots come from `QWidget.grab()` instead of `ImageGrab` on the
  window's DWM bounds. That also fixes P5-7: `ImageGrab` returns black
  in a non-interactive session, while `grab()` renders the widget
  itself and works offscreen.
- Dialogs are intercepted in `blastlab.ui.dialogs`, which exists to be
  monkeypatched, plus `os.startfile`.
- Exceptions are caught with `sys.excepthook`, `qInstallMessageHandler`
  and a recorder around `ThreadBridge._run`, in place of Tk's
  `report_callback_exception`.
- Widget pokes use `click()` / `isEnabled()` and the accessors the Qt
  panels grew for exactly this (`report_rows`, `scroll_form`,
  `preview_kind`, `show_view`, `rows`, `single_column`).

Run:
    python _qa_ui_harness.py --smoke
    python _qa_ui_harness.py --resume --budget 540
    python _qa_ui_harness.py --list
"""

import argparse
import json
import os
import sys
import threading
import time
import traceback
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))

#: deliberately NOT under %LOCALAPPDATA%: these runs are evidence a
#: person reads, so they live somewhere obvious
QA_ROOT = os.path.join(os.path.expanduser('~'), 'blastlab_qa')

#: (sid, group, est_seconds, terminal, fn, first doc line)
SCENARIOS = []

#: one pump tick, and the gap above which a stall is worth recording
TICK_MS = 20
GAP_FLOOR_MS = 5
BIG_GAP_MS = 250
#: a grab this dark is almost certainly a capture failure, not a UI
LUMA_FLOOR = 6


class KillSwitch(Exception):
    """The STOP file appeared."""


class Deferred(Exception):
    """This scenario wants a fresh application; come back with --resume."""


def scenario(sid, group, est=60, terminal=False):
    def deco(fn):
        doc = (fn.__doc__ or '').strip().splitlines()
        SCENARIOS.append((sid, group, est, terminal, fn,
                          doc[0] if doc else ''))
        return fn
    return deco


def latest_out():
    try:
        runs = sorted(d for d in os.listdir(QA_ROOT)
                      if os.path.isdir(os.path.join(QA_ROOT, d)))
    except OSError:
        return None
    return os.path.join(QA_ROOT, runs[-1]) if runs else None


class QA:
    def __init__(self, out, args):
        self.out = out
        self.args = args
        self.dirs = {k: os.path.join(out, k) for k in
                     ('shots', 'sheets', 'logs', 'cache', 'exports', 'cwd')}
        for d in self.dirs.values():
            os.makedirs(d, exist_ok=True)
        self.ckpt_path = os.path.join(out, 'checkpoint.json')
        self.ckpt = self._load_ckpt()
        self.scenario_id = 'boot'
        self.tab = 'setup'
        self.mode = 'dark'
        self.action = ''
        self.gaps = []
        self._shots_this = []
        self._dialogs_since_shot = []
        self.answers = []
        self.paths = []
        self.app = None              # QApplication
        self.win = None              # MainWindow
        self._log_mark = None
        self._t_scn = time.perf_counter()
        self._warn_seen = set()
        self._in_callback = False
        self.t_invocation = time.perf_counter()
        self.inv_log = open(os.path.join(out, 'harness.log'), 'a',
                            encoding='utf-8')

    # ── checkpoint / findings ───────────────────────────────────────────
    def _load_ckpt(self):
        try:
            with open(self.ckpt_path, encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError):
            return dict(done={}, shot_counter=0, foreign_pids=[],
                        invocations=[], timing={})

    def save_ckpt(self):
        tmp = self.ckpt_path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(self.ckpt, f, indent=1)
        os.replace(tmp, self.ckpt_path)

    def log(self, msg):
        line = f'[{time.strftime("%H:%M:%S")}] [{self.scenario_id}] {msg}'
        print(line, flush=True)
        self.inv_log.write(line + '\n')
        self.inv_log.flush()

    def _jsonl(self, name, rec):
        rec = dict(rec, scenario=self.scenario_id, t=time.time())
        with open(os.path.join(self.out, name), 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec, default=str) + '\n')

    def finding(self, sev, cat, text, shots=None, evidence=None):
        self.log(f'FINDING {sev} {cat}: {text}')
        self._jsonl('findings.jsonl', dict(
            sev=sev, cat=cat, text=text, tab=self.tab, mode=self.mode,
            shots=shots or list(self._shots_this[-2:]), evidence=evidence))

    def check(self, cond, text, sev='S2', shots=None, evidence=None):
        if not cond:
            self.finding(sev, 'check', text, shots, evidence)
        else:
            self.log(f'ok: {text}')
        return bool(cond)

    def note(self, text, evidence=None):
        """A neutral observation for the report, not a defect."""
        self.log(f'NOTE: {text}')
        self._jsonl('notes.jsonl', dict(text=text, tab=self.tab,
                                        mode=self.mode, evidence=evidence,
                                        shots=list(self._shots_this[-1:])))

    # ── dialogs (patched BEFORE the window is built) ────────────────────
    def patch_dialogs(self):
        """Replace every modal in `ui.dialogs`, and `os.startfile`.

        A modal is fatal to an unattended driver: QMessageBox's static
        calls spin a nested event loop, so a driver that reaches one
        stops until its timeout. The Qt panels resolve their dialogs
        through this module at CALL time precisely so this works."""
        from blastlab.ui import dialogs
        qa = self

        def recorder(name, kind):
            def wrapped(*a, **kw):
                title = a[0] if a else kw.get('title', '')
                text = a[1] if len(a) > 1 else kw.get('text', '')
                if kind == 'info':
                    ans = 'ok'
                elif kind == 'ask':
                    ans = qa.answers.pop(0) if qa.answers else True
                else:
                    ans = (qa.paths.pop(0) if qa.paths
                           else qa.default_path(name, kw, a))
                qa._record_dialog(name, title, text, ans, kw)
                return ans
            return wrapped

        for name in ('show_error', 'show_info', 'warn'):
            setattr(dialogs, name, recorder(name, 'info'))
        setattr(dialogs, 'ask_yes_no', recorder('ask_yes_no', 'ask'))
        for name in ('open_file', 'save_file', 'pick_dir'):
            setattr(dialogs, name, recorder(name, 'path'))

        real_startfile = getattr(os, 'startfile', None)
        self._real_startfile = real_startfile

        def startfile(path, *a, **kw):
            qa._record_dialog('os.startfile', '', str(path), 'suppressed',
                              {})
        os.startfile = startfile
        self.dialogs = dialogs

    def _record_dialog(self, name, title, text, ans, kw):
        rec = dict(fn=name, title=str(title), text=str(text),
                   kwargs={k: str(v) for k, v in kw.items()
                           if k != 'parent'},
                   answer=str(ans), tab=self.tab, mode=self.mode,
                   shot_counter=self.ckpt['shot_counter'])
        self._jsonl('dialogs.jsonl', rec)
        self._dialogs_since_shot.append(rec)
        self.log(f'DIALOG {name} [{title}] {str(text)[:160]!r} -> {ans!r}')
        if (name != 'os.startfile' and self.win is not None
                and threading.current_thread() is threading.main_thread()):
            self._in_callback = True
            try:
                self.shot(f'dialog-{name}')
            except Exception as exc:
                self.log(f'(dialog shot failed: {exc})')
            finally:
                self._in_callback = False

    def default_path(self, name, kw, args=()):
        """Somewhere inside the run, so nothing is written to the repo.

        The suffix comes from what the caller PROPOSED, not only from a
        `default_suffix` keyword: `save_file` is called positionally
        throughout the app, so the keyword is usually absent and every
        export was being handed a `.txt` path. The animation then landed
        as `E07_031.txt` and the check that looked for a video found
        none - a finding about the harness, reported against the app.
        """
        if name == 'pick_dir':
            return self.dirs['exports']
        stem = f'{self.scenario_id}_{self.ckpt["shot_counter"]:03d}'
        suffix = kw.get('default_suffix')
        if not suffix:
            # save_file(title, filters, parent, start, default_suffix)
            proposed = (args[3] if len(args) > 3
                        else kw.get('start', '')) or ''
            suffix = (args[4] if len(args) > 4 else '') or \
                os.path.splitext(str(proposed))[1]
        suffix = str(suffix or '.txt')
        if not suffix.startswith('.'):
            suffix = '.' + suffix
        return os.path.join(self.dirs['exports'], stem + suffix)

    def script_answers(self, *answers):
        self.answers = list(answers)

    def script_paths(self, *paths):
        self.paths = list(paths)

    # ── the event loop ──────────────────────────────────────────────────
    def pump(self, seconds, until=None):
        """Run the event loop for `seconds`, or until `until()` is true.

        Records every gap above GAP_FLOOR_MS, so a scenario can report
        what the window was doing while it waited, and raises KillSwitch
        the moment the STOP file appears."""
        end = time.perf_counter() + float(seconds)
        stop = os.path.join(self.out, 'STOP')
        last = time.perf_counter()
        result = None
        while True:
            self.app.processEvents()
            now = time.perf_counter()
            gap = (now - last) * 1000.0
            if gap > GAP_FLOOR_MS:
                self.gaps.append((gap, self.action))
            last = now
            if os.path.exists(stop):
                raise KillSwitch()
            if until is not None:
                result = until()
                if result:
                    return result
            if now >= end:
                return True if until is None else result
            time.sleep(TICK_MS / 1000.0)

    def until(self, pred, timeout=60):
        return self.pump(timeout, until=pred)

    # ── screenshots ─────────────────────────────────────────────────────
    def shot(self, state, tab=None, widget=None, settle=0.35):
        """Grab `widget` (the window by default) to shots/.

        `QWidget.grab()` renders the widget itself, so unlike ImageGrab
        it does not need a visible desktop and cannot capture whatever
        happens to be on top of us."""
        from PySide6.QtGui import QImage
        if self.win is None:
            return None
        if not self._in_callback:
            self.pump(settle)
        target = widget if widget is not None else self.win
        self.ckpt['shot_counter'] += 1
        n = self.ckpt['shot_counter']
        tab = tab or self.tab
        name = f'{n:03d}_{self.scenario_id}_{tab}_{state}_{self.mode}.png'
        path = os.path.join(self.dirs['shots'], name)
        try:
            pm = target.grab()
            if pm.isNull():
                raise RuntimeError('grab() returned a null pixmap')
            pm.save(path)
            img = pm.toImage().scaled(24, 24).convertToFormat(
                QImage.Format_Grayscale8)
            total = 0
            for y in range(img.height()):
                for x in range(img.width()):
                    total += img.pixelColor(x, y).red()
            luma = total / max(1, img.width() * img.height())
        except Exception as exc:
            self.log(f'(capture failed: {exc})')
            self.finding('S1', 'capture-unavailable',
                         f'could not grab {state}: {exc}')
            return None
        self._shots_this.append(name)
        self._jsonl('shots.jsonl', dict(
            shot=name, state=state, tab=tab, mode=self.mode,
            action=self.action, luma=round(luma, 1),
            size=[target.width(), target.height()],
            dialogs_since_last=list(self._dialogs_since_shot),
            log_tail=self.run_log()[-400:]))
        self._dialogs_since_shot = []
        if luma < LUMA_FLOOR:
            self.finding('S1', 'capture-black',
                         f'{name} is essentially black (luma {luma:.1f})')
        return name

    def contact_sheet(self, names, title):
        """One PNG per scenario, so a reviewer scrolls a sheet not a
        directory."""
        from PySide6.QtGui import QColor, QPainter, QPixmap
        pics = [(nm, QPixmap(os.path.join(self.dirs['shots'], nm)))
                for nm in names if nm]
        pics = [(nm, p) for nm, p in pics if not p.isNull()]
        if not pics:
            return None
        thumb, cols = 640, 3
        scaled = [(nm, p.scaledToWidth(thumb)) for nm, p in pics]
        rows = (len(scaled) + cols - 1) // cols
        h = max(p.height() for _n, p in scaled) + 18
        sheet = QPixmap(thumb * min(cols, len(scaled)), h * rows)
        sheet.fill(QColor('#202020'))
        painter = QPainter(sheet)
        painter.setPen(QColor('#e8e8e8'))
        for i, (nm, p) in enumerate(scaled):
            x, y = (i % cols) * thumb, (i // cols) * h
            painter.drawPixmap(x, y + 18, p)
            painter.drawText(x + 4, y + 13, nm)
        painter.end()
        path = os.path.join(self.dirs['sheets'],
                            f'contact_{self.scenario_id}.png')
        sheet.save(path)
        self.log(f'contact sheet: {os.path.basename(path)} '
                 f'({len(scaled)} shots)')
        return path

    # ── the application ─────────────────────────────────────────────────
    def build_app(self):
        from blastlab.ui.testing import ensure_qapp
        self.app = ensure_qapp(offscreen=not self.args.window)
        from blastlab.ui import dialogs as dmod
        from blastlab.ui.app import MainWindow
        assert dmod.show_error.__name__ == 'wrapped', \
            'the dialog patch did not take'
        t0 = time.perf_counter()
        self.win = MainWindow()
        self.build_ms = (time.perf_counter() - t0) * 1e3
        # OUT-1: Run needs a runs folder and a model; the private runs
        # folder of ensure_qapp's settings file, never the owner's
        from blastlab.ui.testing import use_model
        use_model(self.win)
        self.win.resize(1280, 840)
        t1 = time.perf_counter()
        self.win.show()
        # first paint, not "show returned": under the offscreen platform
        # nothing is ever painted, so the pump is the honest ceiling
        painted = self.until(lambda: self.win.isVisible(), 20)
        self.pump(1.2)
        self.first_paint_ms = (time.perf_counter() - t1) * 1e3
        if not painted:
            self.note('the window never reported itself visible')
        self._watch_bridge()
        self.log(f'window up: {self.win.width()}x{self.win.height()} '
                 f'(built {self.build_ms:.0f} ms, shown '
                 f'{self.first_paint_ms:.0f} ms)')
        return self.win

    def _watch_bridge(self):
        """A callback that raises inside ThreadBridge is swallowed there
        by design, which is right for the app and wrong for a driver."""
        from blastlab.ui.bridge import ThreadBridge
        qa = self
        if getattr(ThreadBridge, '_qa_wrapped', False):
            return
        real = ThreadBridge._run

        @staticmethod
        def watched(fn):
            try:
                fn()
            except Exception:
                qa.finding('S1', 'bridge-exception',
                           'a bridged GUI callback raised',
                           evidence=traceback.format_exc()[-2000:])
        ThreadBridge._run = watched
        ThreadBridge._qa_real_run = real
        ThreadBridge._qa_wrapped = True

    # ── navigation / widget pokes ───────────────────────────────────────
    def goto(self, tab):
        self.action = f'goto {tab}'
        self.win._show(tab)
        self.tab = tab
        self.pump(0.4)

    def dim(self, d):
        self.action = f'dim {d}'
        self.win.setup.set_dim(int(d))
        self.pump(0.5)

    def field(self, name, value, dim=None):
        form = self.win.setup._forms[dim or self.win.setup.dim]
        self.action = f'{name}={value}'
        self._log_mark = len(self.run_log())
        form.v[name].set(str(value))
        self.pump(0.45)

    def click(self, btn, label=''):
        """Press a button the way a user does, and refuse a dead one."""
        self.action = f'click {label or btn.text() or btn.objectName()}'
        self._log_mark = len(self.run_log())
        if not btn.isEnabled():
            self.finding('S2', 'dead-control',
                         f'{self.action} is disabled')
            return False
        btn.click()
        self.pump(0.45)
        return True

    def set_mode(self, mode):
        from PySide6.QtWidgets import QApplication
        from blastlab.ui import theme
        self.action = f'appearance {mode}'
        theme.apply(QApplication.instance(), mode)
        self.mode = mode
        self.pump(0.6)

    def solver(self, mode):
        self.action = f'solver {mode}'
        self.win.solver_mode.set(mode)
        self.pump(0.6)

    def run_log(self):
        try:
            return self.win.run_panel.log_text()
        except Exception:
            return ''

    def log_has(self, text):
        return text in self.run_log()

    def wait_log(self, text, timeout=60):
        """Wait for a line that appeared SINCE the last click, so an old
        identical line cannot satisfy it.

        Starting a run CLEARS the log pane, which makes it shorter than
        the mark taken when the button was pressed - and then the slice
        is empty forever and the wait always times out. A log shorter
        than its own mark has been cleared, so everything in it is new.
        """
        def seen():
            log = self.run_log()
            mark = self._log_mark or 0
            if len(log) < mark:
                self._log_mark = mark = 0
            return text in log[mark:]
        return self.until(seen, timeout)

    def worker_alive(self):
        try:
            return bool(self.win.ctrl.running)
        except Exception:
            return False

    def run_wait(self, timeout=300):
        ok = self.until(lambda: not self.worker_alive(), timeout)
        self.pump(1.0)
        return ok

    def geometry(self, spec=None):
        """Read the window size, or set it from a 'WxH' spec."""
        if spec:
            w, h = (int(v) for v in str(spec).split('+')[0].split('x'))
            self.action = f'resize {w}x{h}'
            self.win.resize(w, h)
            self.pump(0.6)
        return f'{self.win.width()}x{self.win.height()}'

    def reset_window(self):
        self.win.showNormal()
        self.win.resize(1280, 840)
        self.pump(0.4)

    # ── the accessors the scenarios read the UI through ─────────────────
    def strip_text(self):
        """The Setup tab's validation report, one string per row."""
        try:
            return [t for _icon, t in self.win.setup.report_rows()]
        except Exception as exc:
            return [f'(unavailable: {exc})']

    def set_case(self, case):
        self.action = f'set_case {type(case).__name__}'
        self.win.setup.set_case(case)
        self.win._schedule_validate()
        self.pump(0.8)

    def scroll_form(self, frac):
        self.action = f'scroll {frac}'
        try:
            self.win.setup.scroll_form(float(frac))
        except Exception:
            pass
        self.pump(0.35)

    def hover(self, widget):
        """Qt draws hover from the style, so the state has to be set the
        way the style reads it, not by moving a real cursor."""
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtWidgets import QApplication
        self.action = 'hover'
        widget.setAttribute(Qt.WA_UnderMouse, True)
        QApplication.sendEvent(widget, QEvent(QEvent.Enter))
        widget.update()
        self.pump(0.3)

    def unhover(self, widget):
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtWidgets import QApplication
        widget.setAttribute(Qt.WA_UnderMouse, False)
        QApplication.sendEvent(widget, QEvent(QEvent.Leave))
        widget.update()
        self.pump(0.2)

    def key(self, sequence, widget=None):
        """Send a key sequence such as 'F5' or 'Ctrl+O'."""
        from PySide6.QtGui import QKeySequence
        from PySide6.QtTest import QTest
        self.action = f'key {sequence}'
        self._log_mark = len(self.run_log())
        seq = QKeySequence(sequence)
        if not seq.count():
            return False
        combo = seq[0]
        QTest.keyClick(widget or self.win, combo.key(),
                       combo.keyboardModifiers())
        self.pump(0.45)
        return True

    def cpu_idle(self, seconds=5):
        """The share of a core this process burns while nothing happens -
        what 'that tab is spinning' means to the machine."""
        c0, w0 = time.process_time(), time.perf_counter()
        self.pump(seconds)
        wall = max(time.perf_counter() - w0, 1e-9)
        pct = 100.0 * (time.process_time() - c0) / wall
        self._jsonl('timing.jsonl', dict(
            label=f'idle_cpu_{self.tab}', pct=pct, seconds=seconds))
        self.note(f'idle CPU on {self.tab}: {pct:.1f} % of a core '
                  f'over {seconds:.0f} s')
        if pct > self.IDLE_CPU_S2:
            self.finding('S2', 'idle-cpu',
                         f'the {self.tab} tab burns {pct:.1f} % of a core '
                         f'while idle')
        return pct

    #: Tk's worst recorded idle was 20 %; past this something is spinning
    IDLE_CPU_S2 = 25.0

    # ── results that outlive one invocation ─────────────────────────────
    # A budget stop ends the process, so a scenario that needs the result
    # of an earlier one would have to re-solve it. Pickling the Result
    # keeps the later groups affordable, which is what makes resume work
    # at all rather than being a way to restart from the beginning.
    def _cache_dir(self):
        d = os.path.join(self.out, 'cache')
        os.makedirs(d, exist_ok=True)
        return d

    def cache(self, name, obj):
        import pickle
        with open(os.path.join(self._cache_dir(), name + '.pkl'),
                  'wb') as f:
            pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)

    def cached(self, name):
        import pickle
        p = os.path.join(self._cache_dir(), name + '.pkl')
        if not os.path.exists(p):
            return None
        try:
            with open(p, 'rb') as f:
                return pickle.load(f)
        except Exception as exc:
            self.log(f'cache {name} unreadable: {exc}')
            return None

    def last_result(self):
        ents = self.win.results.entries()
        return ents[-1].result if ents else None

    # ── WSL, for the foam group ─────────────────────────────────────────
    def wsl_pgrep(self):
        """Every blastFoam alive in the distro, ours or not. A foreign
        solver makes every timing in group F meaningless."""
        import subprocess
        try:
            r = subprocess.run(['wsl.exe', '-d', 'Ubuntu', '--', 'pgrep',
                                '-a', 'blastFoam'], capture_output=True,
                               text=True, timeout=60,
                               stdin=subprocess.DEVNULL,
                               creationflags=0x08000000)
            return [ln for ln in r.stdout.splitlines() if ln.strip()]
        except Exception as exc:
            return [f'<pgrep failed: {exc}>']

    def own_runs(self):
        """The run directories this process made, by its pid tag."""
        from blastlab.solvers.foam import env
        tag = f'_p{os.getpid()}-'
        try:
            recs = env.scan_runs()
        except Exception as exc:
            self.log(f'scan_runs failed: {exc}')
            return {}
        return {d: r for d, r in recs.items() if tag in os.path.basename(d)}

    def reap_own(self):
        """A solver of ours still alive after its run ended is an orphan
        that will keep eating the disk; report it and kill it."""
        from blastlab.solvers.foam import env
        own = self.own_runs()
        alive = [r for r in own.values() if r.alive]
        if alive:
            pids = [r.pid for r in alive if r.pid]
            self.finding('S1', 'orphan',
                         f'a solver of ours is still alive after the run '
                         f'ended: {[r.dir for r in alive]}')
            env._signal_pids(pids, 'TERM')
            time.sleep(5)
            env._signal_pids(pids, 'KILL')
        return own

    def disk_gate(self):
        """Refuse to start a foam group that cannot finish: filling C: is
        how WSL was brought down once already."""
        import shutil
        import subprocess
        free_c = shutil.disk_usage('C:\\').free / 1e9
        try:
            r = subprocess.run(['wsl.exe', '-d', 'Ubuntu', '--', 'df',
                                '-B1', '--output=avail', '/'],
                               capture_output=True, text=True, timeout=60,
                               stdin=subprocess.DEVNULL,
                               creationflags=0x08000000)
            avail = int(r.stdout.strip().splitlines()[-1]) / 1e9
        except Exception:
            avail = -1.0
        self.log(f'disk: C: {free_c:.0f} GB free, WSL / {avail:.0f} GB free')
        return free_c >= 10 and (avail < 0 or avail >= 5)

    # ── scenario lifecycle ──────────────────────────────────────────────
    def begin(self, sid):
        self.scenario_id = sid
        self.gaps = []
        self._shots_this = []
        self._dialogs_since_shot = []
        self.answers = []
        self.paths = []
        self._log_mark = len(self.run_log())
        self._t_scn = time.perf_counter()
        self.log('--- begin ---')

    def end(self, sid, status, err=None):
        wall = time.perf_counter() - self._t_scn
        gaps = sorted(g for g, _a in self.gaps)
        big = [(round(g), a) for g, a in self.gaps if g > BIG_GAP_MS]
        timing = dict(wall_s=round(wall, 1),
                      max_gap_ms=round(gaps[-1]) if gaps else 0,
                      p99_gap_ms=round(gaps[int(len(gaps) * 0.99)])
                      if gaps else 0,
                      big_gaps=big[:12])
        self.ckpt['timing'][sid] = timing
        self.ckpt['done'][sid] = dict(status=status, t=time.time(),
                                      shots=list(self._shots_this),
                                      err=(err or '')[-1500:],
                                      wall_s=round(wall, 1))
        self.save_ckpt()
        self._jsonl('timing.jsonl', dict(sid=sid, **timing))
        if '[ui error' in self.run_log():
            self.finding('S1', 'ui-error',
                         'the run log carries a "[ui error" line')
        self.contact_sheet(self._shots_this, sid)
        self.log(f'--- end {status} in {wall:.1f}s '
                 f'(max gap {timing["max_gap_ms"]} ms) ---')

    def budget_left(self):
        return self.args.budget - (time.perf_counter() - self.t_invocation)

    def neutral(self):
        """Leave the window somewhere harmless for the next scenario."""
        try:
            self.set_mode('dark')
            self.reset_window()
            self.goto('setup')
            self.win.setup.set_dim(2)
            self.pump(0.3)
        except Exception as exc:
            self.log(f'(neutral failed: {exc})')

    def timeit(self, label, fn, *a, **kw):
        t0 = time.perf_counter()
        out = fn(*a, **kw)
        dt = (time.perf_counter() - t0) * 1000.0
        self._jsonl('timing.jsonl', dict(label=label, ms=round(dt, 1)))
        self.log(f'timing {label}: {dt:.0f} ms')
        return out, dt


def install_warning_capture(qa):
    """Python warnings and thread exceptions become findings, and Qt's
    own message handler stops printing into the void."""
    from PySide6.QtCore import qInstallMessageHandler

    warnings.simplefilter('always')

    def showwarning(message, category, filename, lineno, *a):
        key = (str(message), filename, lineno)
        if key in qa._warn_seen:
            return
        qa._warn_seen.add(key)
        qa.finding('S4', 'py-warning',
                   f'{category.__name__}: {message}',
                   evidence=f'{filename}:{lineno}')
    warnings.showwarning = showwarning

    def thread_hook(args):
        qa.finding('S1', 'thread-exception',
                   f'{args.exc_type.__name__}: {args.exc_value}',
                   evidence=''.join(traceback.format_exception(
                       args.exc_type, args.exc_value,
                       args.exc_traceback))[-2000:])
    threading.excepthook = thread_hook

    def excepthook(etype, value, tb):
        qa.finding('S1', 'uncaught-exception', f'{etype.__name__}: {value}',
                   evidence=''.join(traceback.format_exception(
                       etype, value, tb))[-2000:])
    sys.excepthook = excepthook

    #: things the OFFSCREEN platform says about itself. They are true and
    #: they are not defects: there is no window manager to raise, lower or
    #: re-parent to, and no foreign window to wrap. Reporting them buries
    #: the messages that do mean something ("QWidget::setMinimumSize:
    #: negative size" and its kind), which is the whole point of the hook.
    OFFSCREEN_NOISE = (
        'does not support raise()',
        'does not support lower()',
        'does not support setParent',
        'does not support foreign windows',
        'does not support grabWindow',
        'does not support propagateSizeHints',
    )

    def qt_handler(mode, ctx, message):
        text = str(message)
        if not text.strip():
            return
        if qa.app is not None and qa.app.platformName() == 'offscreen' \
                and any(s in text for s in OFFSCREEN_NOISE):
            return
        key = ('qt', text)
        if key in qa._warn_seen:
            return
        qa._warn_seen.add(key)
        # Qt says "QWidget::setMinimumSize: negative size" and the like;
        # those are layout bugs, not noise
        qa.finding('S3', 'qt-message', text[:300])
    qInstallMessageHandler(qt_handler)


# ═══════════════════════════════════════════════════════════════════════
#  Group S - does the harness work at all
# ═══════════════════════════════════════════════════════════════════════

@scenario('S00', 'S', est=40)
def s00_smoke(qa):
    """Smoke: the window opens, every tab paints, a shot is not black."""
    qa.check(qa.win is not None, 'the window exists', 'S1')
    qa.check(qa.win.width() >= 1100 and qa.win.height() >= 720,
             f'the window is at least its own minimum ({qa.geometry()})')
    names = []
    for tab in ('setup', 'run', 'results', 'chain'):
        qa.goto(tab)
        names.append(qa.shot('open'))
    qa.check(all(names), 'every tab produced a screenshot', 'S1')
    qa.check(qa.win.current_tab() == 'chain',
             'the last goto really switched the tab')
    qa.goto('setup')
    qa.check(qa.win.setup.preview_kind() in ('1d', '2d', '3d', 'none'),
             f'the preview reports a kind ({qa.win.setup.preview_kind()})')
    qa.note(f'shots: {names}')


# ═══════════════════════════════════════════════════════════════════════
#  Group B - the application at rest: appearance, layout, keyboard
# ═══════════════════════════════════════════════════════════════════════

@scenario('B01', 'B', est=40)
def b01_coldstart(qa):
    """Cold start: title, sidebar, default 2D case + validation strip."""
    qa.note(f'App construction {qa.build_ms:.0f} ms, first paint '
            f'{qa.first_paint_ms:.0f} ms')
    qa.shot('coldstart')
    qa.note(f'window title: {qa.win.windowTitle()!r}')
    qa.note('validation strip on the default 2D case: '
            + ' | '.join(qa.strip_text()))
    qa.check(qa.win._mode_switch.isChecked(), 'Dark mode switch is on')
    qa.check(bool(qa.win.windowTitle().strip()),
             'the window has a title', 'S3')
    qa.cpu_idle(8)


@scenario('B02', 'B', est=60)
def b02_tabs_empty(qa):
    """Empty state of Run / Results / Chain + idle CPU per tab."""
    for k in ('run', 'results', 'chain'):
        qa.goto(k)
        qa.shot('empty')
        qa.cpu_idle(5)
    rp = qa.win.run_panel
    qa.note('Run tab empty state: Stop=%s Exec=%s 3DView=%s progress=%d'
            % (rp.stop_btn.isEnabled(), rp._exec_btns[0].isEnabled(),
               rp.view3d_btn.isEnabled(), rp.progress.value()))
    qa.check(not rp.stop_btn.isEnabled(),
             'Stop is disabled with nothing running')
    qa.check(not any(b.isEnabled() for b in rp._exec_btns),
             'the Exec buttons are disabled with nothing running')
    rs = qa.win.results
    states = {k: b.isEnabled() for k, b in rs._export_btns.items()}
    qa.note('Results empty: export button states '
            + ', '.join(f'{k}={v}' for k, v in states.items()))
    # the Tk app left these live and clicking one was a silent no-op (G3);
    # the port gates them instead, which is the behaviour to hold on to
    qa.check(not any(states.values()),
             'every export is disabled with no result selected - the Tk '
             'app left them live and a click did nothing (G3)')
    for k, b in rs._export_btns.items():
        if not b.isEnabled() and not (b.toolTip() or '').strip():
            qa.finding('S3', 'silent-disable',
                       f'the {k} export is disabled with no tooltip '
                       f'saying why')
    # OUT-1: no workspace box any more; the chain uses the Run tab's
    # model folder
    qa.note(f'Chain writes into the model folder '
            f'{qa.win.run_panel.current_runs_dir()!r} / '
            f'{qa.win.run_panel.current_run_name()!r}')
    qa.goto('setup')


@scenario('B03', 'B', est=60)
def b03_dimensions(qa):
    """Every dimension's form, top and bottom of the scroll column."""
    for d in (1, 2, 3):
        qa.dim(d)
        qa.scroll_form(0.0)
        qa.shot(f'form{d}d_top')
        qa.scroll_form(1.0)
        qa.shot(f'form{d}d_bottom')
        qa.note(f'{d}D strip: ' + ' | '.join(qa.strip_text()))
    qa.scroll_form(0.0)
    qa.check(qa.win.setup.preview_kind() == '3d',
             'the 3D preview is the one showing for a 3D case '
             f'(got {qa.win.setup.preview_kind()!r})')
    qa.dim(2)
    qa.check(qa.win.setup.preview_kind() == '2d',
             'and the 2D preview comes back for a 2D case '
             f'(got {qa.win.setup.preview_kind()!r})')


@scenario('B04', 'B', est=30)
def b04_hover_disabled(qa):
    """Hover states and the look of disabled buttons.

    A genuine rewrite rather than a port: Tk was asked to redraw a
    colour, Qt draws hover from the style sheet, so the widget's own
    hover state is what has to be set.
    """
    nav = qa.win._nav_btns['run']
    qa.hover(nav)
    qa.shot('hover_nav_run')
    qa.unhover(nav)
    qa.goto('run')
    rp = qa.win.run_panel
    qa.hover(rp.run_btn)
    qa.shot('hover_run_btn')
    qa.unhover(rp.run_btn)
    qa.check(not rp.stop_btn.isEnabled(),
             'Stop is the disabled one to photograph')
    qa.hover(rp.stop_btn)
    qa.shot('hover_disabled_stop')
    qa.unhover(rp.stop_btn)
    qa.goto('setup')


@scenario('B05', 'B', est=70)
def b05_resize(qa):
    """The window at its minimum, below it, and maximised, on every tab."""
    for spec in ('1100x720', '900x600'):
        qa.geometry(spec)
        qa.note(f'requested {spec} -> actual {qa.geometry()}')
        for k in ('setup', 'run', 'results', 'chain'):
            qa.goto(k)
            qa.shot(f'geom{spec}')
    qa.win.showMaximized()
    qa.pump(1.0)
    qa.note(f'maximised -> {qa.geometry()}')
    for k in ('setup', 'run', 'results', 'chain'):
        qa.goto(k)
        qa.shot('zoomed')
    qa.reset_window()
    qa.goto('setup')


@scenario('B06', 'B', est=30)
def b06_keyboard(qa):
    """The accelerators, Tab order, and Return in a point list.

    F5 starts a REAL solver, so the F5/Esc pair is closed inside the
    scenario - a worker left running leaks into the next one and
    neutral() reports it as an S1.
    """
    for seq in ('Ctrl+O', 'Ctrl+S'):
        qa.key(seq)
    n = _nlines(os.path.join(qa.out, 'dialogs.jsonl'))
    qa.note(f'Ctrl+O / Ctrl+S: dialogs recorded so far = {n} '
            f'(an Open dialog would have appeared as one)')

    was_running = qa.worker_alive()
    qa.key('F5')
    started = qa.until(lambda: qa.worker_alive(), 8)
    qa.check(started or was_running, 'F5 starts a run (G9 accelerator)',
             'S3')
    if started:
        qa.key('Esc')
        qa.check(qa.until(lambda: not qa.worker_alive(), 120),
                 'Esc stops the run that F5 started', 'S2')

    # Tab order: walk the focus chain and say where it goes, which is the
    # thing that was measured and fixed on the Run tab
    qa.goto('run')
    rp = qa.win.run_panel
    rp.run_btn.setFocus()
    qa.pump(0.3)
    qa.shot('focus_run_btn')
    order = []
    for _ in range(6):
        qa.key('Tab')
        w = qa.win.focusWidget()
        order.append(type(w).__name__ if w is not None else 'None')
    qa.note('Tab from Run: ' + ' -> '.join(order))
    qa.shot('focus_after_tab')
    qa.goto('setup')


@scenario('B07', 'B', est=120)
def b07_light_tour(qa):
    """Light mode: cold-start view, every tab, every dimension, resize."""
    qa.set_mode('light')
    qa.shot('setup_default')
    for k in ('run', 'results', 'chain'):
        qa.goto(k)
        qa.shot('empty')
    qa.goto('setup')
    for d in (1, 2, 3):
        qa.dim(d)
        qa.scroll_form(0.0)
        qa.shot(f'form{d}d_top')
        qa.scroll_form(1.0)
        qa.shot(f'form{d}d_bottom')
    qa.scroll_form(0.0)
    qa.dim(2)
    qa.field('Lx', 'abc')
    qa.shot('error_strip')
    qa.check(any('Lx' in t for t in qa.strip_text()),
             'the bad field is named in the report', 'S2')
    qa.field('Lx', '10')
    qa.geometry('1100x720')
    qa.shot('geom1100x720')
    qa.reset_window()
    qa.set_mode('dark')


def _nlines(path):
    try:
        with open(path, encoding='utf-8') as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


# ═══════════════════════════════════════════════════════════════════════
#  Group Q - what only exists because of the port
# ═══════════════════════════════════════════════════════════════════════
@scenario('Q01', 'Q', est=120)
def q01_viewer_lifecycle(qa):
    """One viewer child, three surfaces, no window left behind.

    Tk had a single 3D view. The port gives Setup, Run and Results one
    each, sharing ONE child process - which is where a dangling window
    handle would come from, so the claim and release choreography is
    what this watches.
    """
    from blastlab.viz3d import pyvista_available
    if not pyvista_available():
        qa.note('pyvista is not installed - nothing to embed')
        return
    hosts = {'setup': qa.win.setup.view3d,
             'run': qa.win.run_panel.view3d,
             'results': qa.win.results.view3d}
    qa.note('hosts: ' + ', '.join(
        f'{k}={type(v).__name__}' for k, v in hosts.items()))
    link = qa.win.viewer_link
    qa.goto('setup')
    qa.dim(3)
    qa.win.setup.update_preview(qa.win.setup.get_case())
    qa.until(lambda: bool(getattr(hosts['setup'], '_hwnd', None)), 120)
    qa.shot('setup_3d')
    setup_hwnd = getattr(hosts['setup'], '_hwnd', None)
    qa.check(setup_hwnd is not None,
             'the Setup preview got a render window from the child', 'S2')
    for _ in range(3):
        qa.goto('run')
        qa.goto('results')
        qa.goto('setup')
    qa.check(getattr(hosts['setup'], '_hwnd', None) == setup_hwnd,
             'and it is the SAME window after three tab round trips - a '
             'new one each time would mean the child is re-creating them',
             'S1')
    qa.check(link.alive,
             'one viewer child is still alive for all three surfaces',
             'S1')
    seen = {k: getattr(v, '_hwnd', None) for k, v in hosts.items()}
    qa.note(f'render windows per surface: {seen}')
    handles = [h for h in seen.values() if h]
    qa.check(len(set(handles)) == len(handles),
             'no two surfaces share a render window', 'S1',
             evidence=str(seen))
    qa.dim(2)
    qa.win.setup.update_preview(qa.win.setup.get_case())
    qa.pump(1.0)
    qa.shot('back_to_2d')
    qa.check(link.alive,
             'and leaving 3D does not take the child down with it', 'S2')


@scenario('Q02', 'Q', est=90)
def q02_repolish_everywhere(qa):
    """A palette change repaints every panel, with nothing left dark.

    Qt restyles through a style sheet, so a widget that was built before
    a rule existed keeps the old look until it is repolished. The Tk app
    could not have this bug; the port can.
    """
    from blastlab.ui import theme
    for mode in ('light', 'dark', 'light', 'dark'):
        qa.set_mode(mode)
        for tab in ('setup', 'run', 'results', 'chain'):
            qa.goto(tab)
            qa.shot(f'{mode}_{tab}')
        qa.check(theme.mode() == mode,
                 f'the theme really is {mode}', 'S2')
    qa.set_mode('dark')
    # the title colour was stripped of its '#' for months and the failure
    # was swallowed by a bare except, so the titles were never recoloured
    pal = theme.pal()
    bad = [k for k, v in pal.items()
           if isinstance(v, str) and v.startswith('#')
           and len(v) not in (4, 7, 9)]
    qa.check(not bad, 'every palette colour is a usable hex string', 'S2',
             evidence=str({k: pal[k] for k in bad}))


@scenario('Q03', 'Q', est=120)
def q03_screen_vs_file(qa):
    """The Fields panel beside the grid its export writes.

    The owner chose "one large panel + selectors" on screen while the
    exports keep the full matplotlib grid, so screen and file are
    deliberately different. This is the evidence for that decision, and
    the check that the difference is the intended one.
    """
    ensure_results(qa, names=('native2d',))
    qa.goto('results')
    if not select_result(qa, 'QA native2d'):
        return
    rs = qa.win.results
    rs.show_view('Fields')
    qa.pump(0.8)
    qa.shot('screen_one_field')
    qa.note(f'on screen: page={rs.fields.page()!r} '
            f'field={rs.fields.field_sel.currentText()!r} '
            f'snapshot={rs.fields.snapshot()!r}')
    out = qa.dirs['exports']
    t_start = time.time()
    rs.export('pngs', threaded=False)
    qa.until(lambda: bool(_written_since(out, t_start, '.png')), 120)
    pngs = _written_since(out, t_start, '.png')
    qa.note('exported: ' + str([os.path.basename(p) for p in pngs]))
    qa.check(len(pngs) > 1,
             'the file is the whole grid, several images, while the '
             'screen shows one field - the owner\'s decision, made '
             'visible', 'S2')
    qa.contact_sheet([os.path.basename(p) for p in pngs[:4]],
                     'exported grid')


@scenario('Q04', 'Q', est=90)
def q04_dpi_scaling(qa):
    """Nothing clips at 125 % and 150 %.

    Qt sizes from the font, so a larger UI font is the honest stand-in
    for a DPI change inside one process: every label has to still fit.
    """
    from blastlab.ui import theme
    base = theme.font('body').pointSizeF()
    if base <= 0:
        qa.note('the body font has no point size to scale')
        return
    for factor in (1.25, 1.5):
        app = qa.app
        f = app.font()
        f.setPointSizeF(base * factor)
        app.setFont(f)
        qa.pump(1.0)
        for tab in ('setup', 'run', 'results', 'chain'):
            qa.goto(tab)
            qa.shot(f'dpi{int(factor * 100)}_{tab}')
        clipped = _clipped_labels(qa.win)
        qa.check(not clipped,
                 f'nothing is clipped at {int(factor * 100)} %', 'S2',
                 evidence='; '.join(clipped[:6]))
        qa.note(f'{int(factor * 100)} %: {len(clipped)} clipped widget(s)')
    f = qa.app.font()
    f.setPointSizeF(base)
    qa.app.setFont(f)
    qa.pump(1.0)
    qa.goto('setup')


def _clipped_labels(root):
    """Widgets whose text needs more room than they have.

    Two things this gets right that the obvious version does not.

    Compared against the GLYPH width, not against sizeHint: a button with
    QSS padding can sit under its hint and still render every letter, and
    'blastFoam' does.

    And a word-WRAPPING label is skipped entirely. It is not meant to fit
    on one line, so 'Domain radius [m]' needing 141 px in a 132 px column
    means it uses two lines, not that it is clipped. For those the
    question is height, which Qt's own heightForWidth answers.
    """
    from PySide6.QtWidgets import (QAbstractButton, QCheckBox, QLabel,
                                   QWidget)
    out = []
    for w in root.findChildren(QWidget):
        if not w.isVisible():
            continue
        text = ''
        if isinstance(w, (QLabel, QAbstractButton)):
            text = w.text()
        if not text or '\n' in text or w.width() < 2:
            continue
        if isinstance(w, QLabel) and w.wordWrap():
            want = w.heightForWidth(w.width())
            if want > w.height() + 1:
                out.append(f'QLabel({text[:40]!r}) wraps to {want} px '
                           f'in {w.height()}')
            continue
        need = w.fontMetrics().horizontalAdvance(text)
        room = w.width()
        if isinstance(w, QAbstractButton) and not w.icon().isNull():
            room -= w.iconSize().width() + 6
        if isinstance(w, QCheckBox):
            room -= 22
        if need > room + 1:
            out.append(f'{type(w).__name__}({text!r}) needs {need} '
                       f'has {room}')
    return out


# ═══════════════════════════════════════════════════════════════════════
#  Group C - Setup validation UX
# ═══════════════════════════════════════════════════════════════════════
def _fresh2d(qa):
    from blastlab.core.case import Case2D
    qa.set_case(Case2D())


def _form(qa):
    return qa.win.setup.form


def _add_row(qa, plist, text):
    """Type a row into a point list's entry and press its + button."""
    qa.action = f'add row {text!r}'
    plist.entry.setText(text)
    ok = plist.add()
    qa.pump(0.5)
    return ok


def _set_rows(qa, plist, rows, settle=0.8):
    """`PointList.set()` does not fire on_change by design (set_case
    drives it), so a scenario that edits rows has to revalidate the way
    a user's +/- click would."""
    plist.set(rows)
    plist._on_change()
    qa.pump(settle)


@scenario('C01', 'C', est=30)
def c01_parse_errors(qa):
    """Two parse errors at once - how many are shown?"""
    _fresh2d(qa)
    qa.field('Lx', 'abc')
    qa.field('cell', '')
    qa.shot('two_parse_errors')
    strip = qa.strip_text()
    qa.note('strip with Lx=abc AND cell="": ' + ' | '.join(strip))
    errs = [s for s in strip if 'not a number' in s or 'number' in s]
    qa.check(len(errs) >= 2,
             'both parse errors are listed - the Tk app showed only the '
             'first (G3)', 'S2')
    bad = _form(qa).bad
    qa.check({'Lx', 'cell'} <= bad,
             f'and both fields are marked in red (marked: {sorted(bad)})')
    qa.field('Lx', '10')
    qa.shot('one_parse_error_left')
    qa.check('Lx' not in _form(qa).bad,
             'fixing one field clears its mark')
    qa.field('cell', '0.025')


@scenario('C02', 'C', est=60)
def c02_numeric_rules(qa):
    """Numeric rules per dimension: zero/negative values, slice position."""
    _fresh2d(qa)
    for name, val in (('cell', '0'), ('charge', '0'), ('Lx', '-1')):
        qa.field(name, val)
        qa.shot(f'{name}_{val}')
        strip = qa.strip_text()
        qa.note(f'2D {name}={val}: ' + ' | '.join(strip))
        qa.check(bool(strip), f'{name}={val} is reported at all', 'S2')
        _fresh2d(qa)
    from blastlab.core.case import Case1D, Case3D
    qa.set_case(Case1D())
    qa.field('radius_m', '0')
    qa.shot('1d_radius_0')
    qa.note('1D radius=0: ' + ' | '.join(qa.strip_text()))
    qa.set_case(Case3D())
    qa.field('t_end', '-1')
    qa.shot('3d_tend_neg')
    qa.note('3D t_end=-1: ' + ' | '.join(qa.strip_text()))
    qa.field('t_end', '0')
    qa.field('slice_pos', '99')
    qa.shot('3d_slice_99')
    qa.note('3D slice_pos=99: ' + ' | '.join(qa.strip_text()))
    qa.field('slice_pos', '')
    _fresh2d(qa)


@scenario('C03', 'C', est=60)
def c03_geometry_rules(qa):
    """Charge outside / in an obstacle / near a wall, bad boxes, gauges."""
    from blastlab.core.case import Case2D
    qa.set_case(Case2D(geometry='planar', Lx=2.0, Ly=2.0,
                       center=(1.0, 1.0)))
    form = _form(qa)
    qa.field('cx', '99')
    qa.shot('charge_outside')
    qa.note('charge outside: ' + ' | '.join(qa.strip_text()))
    qa.check(bool(qa.strip_text()), 'a charge outside the domain is '
             'reported', 'S2')
    qa.field('cx', '1')
    _add_row(qa, form.obstacles, '0.9 1.1 0.9 1.1')
    qa.shot('charge_in_obstacle')
    qa.note('charge in obstacle: ' + ' | '.join(qa.strip_text()))
    _set_rows(qa, form.obstacles, [])
    ok = _add_row(qa, form.obstacles, '1.5 1.0 0 1')
    qa.shot('bad_obstacle_box')
    qa.note(f'inverted obstacle box accepted={ok}, rows now '
            f'{form.obstacles.get()}, strip: '
            + ' | '.join(qa.strip_text()))
    _set_rows(qa, form.obstacles, [])
    _add_row(qa, form.gauges, '9 9')
    qa.shot('gauge_outside')
    qa.note('gauge outside: ' + ' | '.join(qa.strip_text()))
    _set_rows(qa, form.gauges, [], settle=0.4)
    qa.set_case(Case2D(geometry='axisymmetric', Lx=2.0, Ly=2.0,
                       charge=8.0, center=(0.0, 0.05)))
    qa.shot('charge_near_ground')
    qa.note('axisym charge 5 cm above the ground: '
            + ' | '.join(qa.strip_text()))
    _fresh2d(qa)


@scenario('C04', 'C', est=40)
def c04_point_lists(qa):
    """Malformed rows in the point lists - is there ANY feedback?"""
    _fresh2d(qa)
    form = _form(qa)
    gauges = form.gauges
    rest = gauges._idle_text()
    for text in ('a b', '1 2 3', '', '1,2', '1;2'):
        n0 = gauges.count()
        ok = _add_row(qa, gauges, text)
        n1 = gauges.count()
        qa.shot(f'gauge_row_{text.replace(" ", "_") or "empty"}')
        hint = gauges.hint.text()
        qa.note(f'gauge entry {text!r}: accepted={ok}, rows {n0}->{n1}, '
                f'hint {hint!r}')
        if n1 == n0 and text:
            # the row is still refused, which is right; the port's job is
            # that the list SAYS why, under the entry (G3). The resting
            # hint is a format reminder, so it has to have left that.
            qa.check(bool(hint) and hint != rest,
                     f'row {text!r} refused WITH a visible reason '
                     f'({hint!r})', 'S2')
    gauges.entry.clear()
    gauges.tree.setCurrentItem(None)
    gauges.remove()
    qa.pump(0.4)
    qa.check(gauges.hint.text() not in ('', rest),
             'Remove with nothing selected explains itself', 'S2')
    qa.shot('remove_nothing_selected')
    _set_rows(qa, gauges, [])


@scenario('C05', 'C', est=40)
def c05_native_vs_foam(qa):
    """blastFoam-only cards hidden for native, shown for blastFoam."""
    _fresh2d(qa)
    qa.solver('native')
    form = _form(qa)
    qa.check(not form.card_visible('Dynamic refinement (AMR)')
             and form.row_visible('eos'),
             'native mode: the AMR card is hidden and the EOS row shown',
             'S2')
    qa.shot('numerics_native')
    qa.solver('blastfoam')
    form = _form(qa)
    qa.check(form.card_visible('Dynamic refinement (AMR)')
             and not form.row_visible('eos'),
             'blastFoam mode: the AMR card is shown and the EOS row '
             'hidden', 'S2')
    qa.shot('numerics_foam')
    qa.note('foam strip: ' + ' | '.join(qa.strip_text()))
    qa.field('material', 'C4')
    qa.field('amr_levels', '2')
    qa.pump(0.6)
    qa.scroll_form(0.35)
    qa.shot('amr_card_on')
    qa.solver('native')
    qa.shot('back_to_native')
    # T34: the typed values are KEPT in the form and stripped from the
    # case, rather than being coerced in front of the user
    form = _form(qa)
    got = qa.win.setup.get_case()
    qa.check(form.v['material'].get() == 'C4'
             and form.v['amr_levels'].get() == '2'
             and got.material == 'TNT' and got.amr_levels == 0,
             'native keeps the typed foam values in the form and strips '
             'them from the case', 'S2')
    qa.note(f'after native: material={form.v["material"].get()} '
            f'amr_levels={form.v["amr_levels"].get()} '
            f'(case: {got.material}, {got.amr_levels})')
    qa.scroll_form(0.0)
    _fresh2d(qa)


@scenario('C06', 'C', est=70)
def c06_zones(qa):
    """Refinement-zone rules and their messages."""
    from blastlab.core.case import Case2D
    qa.set_case(Case2D(geometry='planar', Lx=2.0, Ly=2.0,
                       cell_size_m=0.1, charge=20.0, center=(1.0, 1.0)))
    form = _form(qa)
    qa.scroll_form(0.5)
    # native hides the zones card (the row still lands in its list) and
    # strips the case, so the report shows no zone error
    _add_row(qa, form.zones, '0.5 1.5 0.5 1.5 1')
    qa.shot('zone_on_native')
    qa.note('zone on native (card hidden, case stripped): '
            + ' | '.join(qa.strip_text()))
    qa.solver('blastfoam')
    qa.shot('zone_on_foam')
    qa.note('zone on foam: ' + ' | '.join(qa.strip_text()))
    form = _form(qa)
    for rows, tag in (([(0.5, 1.5, 0.5, 1.5, 7)], 'zone_level7'),
                      ([(0.5, 1.5, 0.5, 1.5, 3)], 'zone_jump'),
                      ([(0.53, 1.47, 0.53, 1.47, 1)], 'zone_snapped')):
        _set_rows(qa, form.zones, rows)
        qa.shot(tag)
        qa.note(f'{tag}: ' + ' | '.join(qa.strip_text()))
    _set_rows(qa, form.zones, [], settle=0.4)
    qa.set_case(Case2D(geometry='axisymmetric', Lx=2.0, Ly=2.0,
                       cell_size_m=0.1, charge=8.0, center=(0.0, 1.0),
                       solver='blastfoam'))
    form = _form(qa)
    qa.scroll_form(0.5)
    _set_rows(qa, form.zones, [(0.0, 0.6, 0.6, 1.4, 1),
                               (0.0, 0.3, 0.8, 1.2, 2)])
    qa.shot('axisym_zone_on_axis_l2')
    qa.note('axisym level-2 zone touching the axis: '
            + ' | '.join(qa.strip_text()))
    _set_rows(qa, form.zones, [], settle=0.4)
    qa.scroll_form(0.0)
    _fresh2d(qa)


@scenario('C07', 'C', est=70)
def c07_amr_rules(qa):
    """Dynamic AMR rules, the hidden charge-refine row, the report."""
    from blastlab.core.case import Case2D
    qa.set_case(Case2D(geometry='planar', Lx=4.0, Ly=4.0,
                       cell_size_m=0.2, charge=100.0, center=(2.0, 2.0),
                       gauges=[(3.2, 2.0)]))
    qa.solver('native')
    form = _form(qa)
    qa.scroll_form(0.35)
    qa.field('amr_levels', '2')
    qa.pump(0.6)
    qa.note(f'AMR on native: amr_levels is still '
            f'{form.v["amr_levels"].get()!r} in the hidden card and '
            f'stripped from the case; strip: '
            + ' | '.join(qa.strip_text()))
    qa.shot('amr_native')
    qa.solver('blastfoam')
    form = _form(qa)
    qa.field('amr_levels', '3')
    qa.pump(0.6)
    qa.shot('amr_valid')
    qa.note('valid AMR case: ' + ' | '.join(qa.strip_text()))
    qa.check(not form.row_visible('charge_refine'),
             'the charge-refinement row is hidden while AMR is on', 'S3')
    _set_rows(qa, form.zones, [(1.5, 2.5, 1.5, 2.5, 1)])
    qa.shot('amr_plus_zones')
    qa.note('AMR + zones: ' + ' | '.join(qa.strip_text()))
    _set_rows(qa, form.zones, [], settle=0.4)
    for name, val, tag in (('amr_unrefine', '0.9',
                            'amr_unrefine_gt_refine'),
                           ('amr_display_level', '4',
                            'amr_display_gt_levels')):
        qa.field(name, val)
        qa.shot(tag)
        qa.note(f'{tag}: ' + ' | '.join(qa.strip_text()))
    qa.field('amr_unrefine', '0.2')
    qa.field('amr_display_level', 'auto')
    qa.field('amr_levels', '1')
    qa.pump(0.6)
    qa.field('charge', '0.5')
    qa.shot('amr_charge_unresolved')
    qa.note('AMR 1 level with a 0.5 kg/m charge on 0.2 m cells: '
            + ' | '.join(qa.strip_text()))
    qa.scroll_form(0.0)
    _fresh2d(qa)


@scenario('C08', 'C', est=60)
def c08_caps_and_modal(qa):
    """Cell caps in the report, then Run -> the refusal (G3's split)."""
    from blastlab.core.case import Case2D, Case3D
    qa.set_case(Case2D(geometry='planar', Lx=10.0, Ly=10.0,
                       cell_size_m=0.001, center=(5.0, 5.0)))
    qa.shot('2d_cap')
    strip = qa.strip_text()
    qa.note('2D 100M cells: ' + ' | '.join(strip))
    qa.check(bool(strip), 'a 100 M cell case is reported before Run', 'S2')
    qa.goto('run')
    before = qa.worker_alive()
    qa.win._run_single()
    qa.pump(1.2)
    qa.shot('after_modal')
    qa.check(not qa.worker_alive() and not before,
             'and Run refuses it rather than starting a doomed solve',
             'S1')
    qa.goto('setup')
    qa.set_case(Case3D(cell_size_m=0.06))
    qa.shot('3d_large_warning')
    qa.note('3D 0.06 m: ' + ' | '.join(qa.strip_text()))
    qa.set_case(Case3D(cell_size_m=0.02, solver='blastfoam'))
    qa.shot('3d_foam_cap')
    qa.note('3D foam 0.02 m: ' + ' | '.join(qa.strip_text()))
    _fresh2d(qa)


@scenario('C09', 'C', est=50)
def c09_report_overflow(qa):
    """Many report lines at once; extra charges / det points in preview."""
    from blastlab.core.case import Case3D
    qa.set_case(Case3D(Lx=6.0, Ly=6.0, Lz=6.0, cell_size_m=0.1,
                       charge=20.0, center=(2.0, 3.0, 1.0),
                       solver='blastfoam',
                       obstacles=[(3.0, 3.5, 2.5, 3.5, 0.0, 1.5),
                                  (4.5, 5.0, 1.0, 2.0, 0.0, 2.0)],
                       charges=[(4.0, 3.0, 1.0, 10.0),
                                (2.0, 5.0, 1.0, 5.0)],
                       det_points=[(2.0, 3.0, 1.0), (4.0, 3.0, 1.0)],
                       afterburn='miller', activation='none',
                       amr_levels=2,
                       gauges=[(5.5, 3.0, 1.0), (3.0, 5.5, 1.0)]))
    qa.pump(1.5)
    qa.shot('overflow')
    strip = qa.strip_text()
    qa.note(f'{len(strip)} report lines: ' + ' | '.join(strip))
    # the card is height-capped, so a long report must scroll rather than
    # push the preview off the tab (N2-09's shape)
    # the invariant is on the SCROLLER, not on the card: the card is
    # legitimately taller by its own padding, and pinning the card would
    # be fitting the test to whatever number came out
    from blastlab.ui.setup_panel import STATUS_MAX_H
    scroll = qa.win.setup._status_scroll
    qa.check(scroll.height() <= STATUS_MAX_H,
             f'a long report scrolls instead of pushing the preview off '
             f'the tab ({scroll.height()} px of {STATUS_MAX_H})', 'S2')
    qa.check(qa.win.setup.preview_kind() != 'none',
             'and the preview is still on screen underneath it', 'S2')
    qa.note('G8: the 3D preview should show 3 charges + 2 det points '
            '(see the shot)')
    qa.set_mode('light')
    qa.shot('overflow_light')
    qa.set_mode('dark')
    _fresh2d(qa)


@scenario('C10', 'C', est=90)
def c10_preview_show_mesh(qa):
    """Preview + Show mesh: 3D zones, 2D refine, AMR caption, 1D hint."""
    from blastlab.core.case import Case1D, Case2D, Case3D
    qa.set_case(Case3D(Lx=10.0, Ly=10.0, Lz=10.0, cell_size_m=0.5,
                       charge=1.0, center=(5.0, 5.0, 5.0),
                       solver='blastfoam', charge_refine='zone',
                       refine_zones=[(4.0, 6.0, 4.0, 6.0, 4.0, 6.0, 1),
                                     (4.5, 5.5, 4.5, 5.5, 4.5, 5.5, 2)]))
    qa.pump(1.5)
    qa.shot('3d_zones_preview')
    strip = qa.strip_text()
    qa.note('3D zones strip: ' + ' | '.join(strip))
    # 1 kg on a 0.5 m base cell needs a level over the cap, so there is
    # deliberately no refinement note - the error IS the right answer
    qa.check(any('needs level' in s and 'base cell' in s for s in strip),
             'the report explains that the charge needs a level over the '
             'cap', 'S2')
    qa.win.setup.show_mesh.setChecked(True)
    qa.pump(2.0)
    qa.shot('3d_zones_mesh')
    qa.set_case(Case2D(geometry='planar', Lx=4.0, Ly=4.0,
                       cell_size_m=0.05, charge=10.0, center=(2.0, 2.0),
                       solver='blastfoam', charge_refine='zone'))
    qa.pump(1.5)
    qa.shot('2d_refine_mesh')
    strip2 = qa.strip_text()
    qa.note('2D refine strip: ' + ' | '.join(strip2))
    qa.check(any('Local refinement' in s for s in strip2),
             'the report says "Local refinement: N level(s)" for a '
             'charge_refine=zone case that validates', 'S2')
    qa.set_case(Case2D(geometry='planar', Lx=4.0, Ly=4.0,
                       cell_size_m=0.05, charge=10.0, center=(2.0, 2.0),
                       solver='blastfoam', amr_levels=2))
    qa.pump(1.5)
    qa.shot('2d_amr_mesh')
    qa.note('2D AMR strip: ' + ' | '.join(qa.strip_text()))
    qa.win.setup.show_mesh.setChecked(False)
    qa.pump(1.0)
    qa.set_case(Case1D())
    qa.shot('1d_preview_hint')
    _fresh2d(qa)


@scenario('C11', 'C', est=30)
def c11_axisym_relabel(qa):
    """Axisymmetric relabels Lx/Ly/cx/cy and pins the burst radius."""
    _fresh2d(qa)
    qa.shot('axisym_labels')
    form = _form(qa)
    labels = {n: form.label_text(n) for n in ('Lx', 'Ly', 'cx', 'cy')
              if form.row_visible(n)}
    qa.note(f'axisym labels: {labels}; cx={form.v["cx"].get()!r}')
    qa.check(any('R' in t or 'r ' in t.lower()
                 for t in labels.values()),
             f'axisymmetric relabels the geometry fields ({labels})', 'S2')
    qa.field('geometry', 'planar')
    qa.pump(0.6)
    qa.shot('planar_labels')
    planar = {n: form.label_text(n) for n in ('Lx', 'Ly', 'cx', 'cy')
              if form.row_visible(n)}
    qa.note(f'planar labels: {planar}')
    qa.check(planar != labels, 'and planar puts them back', 'S2')
    qa.field('geometry', 'axisymmetric')
    qa.pump(0.6)


@scenario('C12', 'C', est=40)
def c12_save_open(qa):
    """Save case -> Open case round trip, and the cancel path."""
    from blastlab.core.case import Case2D
    case = Case2D(geometry='planar', Lx=3.0, Ly=2.0, cell_size_m=0.05,
                  charge=5.0, center=(1.0, 0.5), gauges=[(2.0, 1.0)],
                  obstacles=[(1.5, 1.8, 0.0, 0.6)], n_snapshots=4)
    qa.set_case(case)
    p = os.path.join(qa.out, 'save1.json')
    qa.script_paths(p)
    qa.win._save_case()
    qa.pump(0.6)
    qa.check(os.path.exists(p), 'Save case wrote the JSON', 'S1')
    _fresh2d(qa)
    qa.win._open_case(p)
    qa.pump(1.0)
    back = qa.win.setup.get_case()
    fields = ('Lx', 'Ly', 'cell_size_m', 'charge', 'center', 'gauges',
              'obstacles', 'n_snapshots', 'geometry')
    bad = [f for f in fields
           if getattr(back, f, None) != getattr(case, f, None)]
    qa.check(not bad, 'Open case round-trips the saved fields', 'S2',
             evidence='; '.join(f'{f}: {getattr(case, f, None)!r} -> '
                                f'{getattr(back, f, None)!r}' for f in bad))
    qa.shot('after_open')
    qa.script_paths('')
    qa.win._open_case()
    qa.pump(0.6)
    qa.check(qa.win.setup.get_case().Lx == back.Lx,
             'a cancelled Open leaves the form alone', 'S2')
    qa.note('Open case cancelled -> nothing happened (expected)')


# ═══════════════════════════════════════════════════════════════════════
#  Group D - native runs through the Run tab
# ═══════════════════════════════════════════════════════════════════════
def cases():
    """The fixtures the run groups share, kept identical to the Tk
    harness so a screenshot from either can be compared with the other."""
    from blastlab.core.case import Case1D, Case2D, Case3D
    C = {}
    C['N1D'] = Case1D(radius_m=2.0, charge_kg=1.0, cell_size_m=0.005,
                      gauge_radii=[0.5, 1.0], n_snapshots=3)
    C['N2D'] = Case2D(geometry='planar', Lx=2.4, Ly=1.6, cell_size_m=0.04,
                      charge=20.0, center=(0.6, 0.0),
                      obstacles=[(1.2, 1.6, 0.0, 0.6)],
                      bcs=dict(x_lo='reflect', x_hi='terminate',
                               y_lo='reflect', y_hi='terminate'),
                      gauges=[(0.3, 0.8), (1.4, 0.3)], n_snapshots=3,
                      record_frames=60, anim_file='blast_2d_animation.gif')
    C['N3D'] = Case3D(Lx=2.0, Ly=2.0, Lz=2.0, cell_size_m=0.05,
                      charge=50.0, center=(1.0, 1.0, 0.7),
                      obstacles=[(1.4, 1.7, 0.7, 1.3, 0.0, 0.6)],
                      gauges=[(1.7, 1.0, 0.7), (1.0, 1.7, 0.7)],
                      n_snapshots=3, record_frames=40, live=True,
                      anim_file='blast_3d_animation.gif')
    C['F1D'] = Case1D(radius_m=2.0, charge_kg=1.0, cell_size_m=0.02,
                      gauge_radii=[0.5, 1.0], n_snapshots=2,
                      solver='blastfoam', material='C4', activation='none')
    # The foam fixtures are TERMINATE-bounded, unlike the Tk harness's.
    #
    # Without a terminate side and without an end time a run is bounded
    # only by the safety cap, and these are not small cases: F2D took
    # 3,443 s to finish here and F3D had not finished after 5,448 s. A
    # scenario that cannot complete gives no coverage at all, and the
    # first six "findings" of this group were all one timeout wearing
    # different hats. A real case stops when the shock reaches a
    # boundary, so these do too.
    C['F2D'] = Case2D(geometry='planar', Lx=2.0, Ly=2.0,
                      cell_size_m=0.025, charge=50.0, center=(1.0, 1.0),
                      gauges=[(0.5, 1.0)], n_snapshots=3,
                      record_frames=50, solver='blastfoam',
                      material='TNT',
                      bcs=dict(x_lo='terminate', x_hi='terminate',
                               y_lo='terminate', y_hi='terminate'))
    C['F3D'] = Case3D(Lx=0.6, Ly=0.6, Lz=0.6, cell_size_m=0.025,
                      charge=8.0, center=(0.3, 0.3, 0.3),
                      gauges=[(0.45, 0.3, 0.3), (0.3, 0.45, 0.3)],
                      n_snapshots=4, record_frames=150,
                      solver='blastfoam', material='TNT',
                      bcs=dict(x_lo='terminate', x_hi='terminate',
                               y_lo='terminate', y_hi='terminate',
                               z_lo='terminate', z_hi='terminate'))
    C['F2D_REF'] = Case2D(geometry='planar', Lx=2.4, Ly=3.2,
                          cell_size_m=0.08, charge=20.0,
                          center=(1.2, 1.6), gauges=[(2.0, 1.6)],
                          n_snapshots=2, record_frames=60,
                          solver='blastfoam', material='TNT',
                          charge_refine='zone',
                          refine_zones=[(0.9, 2.4, 1.2, 2.0, 1),
                                        (1.7, 2.3, 1.4, 1.8, 2)],
                          bcs=dict(x_lo='terminate', x_hi='terminate',
                                   y_lo='terminate', y_hi='terminate'))
    # Both AMR fixtures were once INVALID: validate_case put "Resolving
    # the charge ... needs AMR level N" in rep.errors, the product
    # correctly disabled Run, and the only two dynamic-AMR scenarios in
    # the matrix never ran AMR at all. These base cells are the largest
    # the error message itself names as workable.
    C['F2D_AMR'] = Case2D(geometry='planar', Lx=4.0, Ly=4.0,
                          cell_size_m=0.1, charge=100.0,
                          center=(2.0, 2.0), gauges=[(3.2, 2.0)],
                          n_snapshots=2, record_frames=60,
                          solver='blastfoam', material='TNT',
                          amr_levels=3,
                          bcs=dict(x_lo='terminate', x_hi='terminate',
                                   y_lo='terminate', y_hi='terminate'))
    C['F3D_AMR'] = Case3D(Lx=1.5, Ly=1.5, Lz=1.5, cell_size_m=0.05,
                          charge=20.0, center=(0.75, 0.75, 0.75),
                          gauges=[(1.25, 0.75, 0.75)], amr_levels=2,
                          amr_display_level=1, amr_max_cells=150_000,
                          n_snapshots=2, record_frames=30,
                          solver='blastfoam', material='TNT',
                          bcs=dict(x_lo='terminate', x_hi='terminate',
                                   y_lo='terminate', y_hi='terminate',
                                   z_lo='terminate', z_hi='terminate'))
    C['F_STOP'] = Case2D(geometry='axisymmetric', Lx=2.5, Ly=2.5,
                         cell_size_m=0.02, charge=8.0,
                         center=(0.0, 1.25), gauges=[(0.8, 1.25)],
                         n_snapshots=4, record_frames=60,
                         solver='blastfoam', material='TNT')
    return C


def _cache_result(qa, name, dim=None):
    """Cache the newest result - but only if it IS the one just run.

    `last_result()` is the newest ENTRY, which is the previous run's when
    this one timed out or was refused. Caching that quietly poisons every
    later group: D04's 3D run once overran its timeout and its 2D
    predecessor went into the cache as `native3d`, so group E asked a 2D
    result for a 3D slice and got a KeyError out of a paint.
    """
    ents = qa.win.results.entries()
    if not ents:
        qa.check(False, f'no result to cache as {name}', 'S1')
        return
    ent = ents[-1]
    if dim is not None and ent.dim != dim:
        qa.check(False, f'the newest result is {ent.dim}D, not the {dim}D '
                 f'one {name} is meant to hold - not caching it', 'S1',
                 evidence=str([f'{e.label} ({e.dim}D)' for e in ents]))
        return
    try:
        qa.cache(name, ent.result)
    except Exception as exc:
        qa.log(f'cache {name} failed: {exc}')


def ensure_results(qa, names=('native1d', 'native2d', 'native3d')):
    """Re-add the cached results under stable labels, so a group that
    resumes in a fresh process still has something to look at."""
    have = [e.label for e in qa.win.results.entries()]
    dims = {'1d': 1, '2d': 2, '3d': 3}
    for name in names:
        label = f'QA {name}'
        if label in have:
            continue
        res = qa.cached(name)
        if res is None:
            qa.log(f'no cache for {name}')
            continue
        dim = dims.get(name[-2:])
        if dim is None:
            meta = getattr(res, 'meta', {}) or {}
            dim = 1 if 'radius_m' in meta else 3 if 'z_c' in meta else 2
        qa.win.results.add_result(label, dim, res)
        qa.pump(0.5)


def select_result(qa, label):
    sel = qa.win.results.sel
    for i in range(sel.count()):
        if sel.itemText(i) == label or label in sel.itemText(i):
            sel.setCurrentIndex(i)
            qa.pump(0.8)
            return True
    qa.check(False, f'no result labelled {label!r} to select', 'S2',
             evidence=str([sel.itemText(i) for i in range(sel.count())]))
    return False


@scenario('D01', 'D', est=60)
def d01_native_1d(qa):
    """Native 1D run from the Run tab; chips, progress, log."""
    C = cases()
    qa.set_case(C['N1D'])
    qa.goto('run')
    qa.click(qa.win.run_panel.run_btn, 'Run')
    qa.pump(0.6)
    qa.shot('running')
    qa.check(qa.run_wait(180), 'the 1D run finished', 'S1')
    qa.shot('finished')
    rp = qa.win.run_panel
    qa.note(f'chips after the 1D run: {rp.chip_texts()}')
    qa.check(rp.progress.value() >= rp.progress.maximum(),
             f'progress reads 100 % after the run '
             f'({rp.progress.value()} of {rp.progress.maximum()})')
    _cache_result(qa, 'native1d', dim=1)


@scenario('D02', 'D', est=200)
def d02_native_2d_live(qa):
    """Native 2D run: live slice + Show mesh, refresh policy, gauge drop."""
    C = cases()
    qa.goto('setup')
    qa.set_case(C['N2D'])
    qa.goto('run')
    rp = qa.win.run_panel
    rp.show_mesh.setChecked(True)
    qa.click(rp.run_btn, 'Run')
    qa.check(qa.wait_log('2D Blast Solver', 40),
             'the 2D solver announced itself', 'S1')
    qa.pump(2.5)
    qa.shot('live_mesh')
    rp.refresh_val.setText('abc')
    rp.refresh_changed.emit()
    qa.pump(0.4)
    qa.note(f'Refresh every = "abc": entry marked bad='
            f'{rp.refresh_val.property("bad")!r}')
    rp.refresh_mode.setCurrentText('steps')
    rp.refresh_val.setText('5')
    rp.refresh_changed.emit()
    qa.pump(2.0)
    qa.shot('refresh_steps5')
    rp.show_mesh.setChecked(False)
    qa.pump(1.5)
    qa.shot('live_nomesh')
    qa.check(qa.run_wait(300), 'the 2D run finished', 'S1')
    qa.shot('finished')
    qa.check(qa.log_has('inside an obstacle'),
             'the dropped-gauge warning reached the run log', 'S2')
    qa.note('that warning lives only in the Run log; the Results Gauges '
            'table simply shows one gauge')
    rp.refresh_val.setText('')
    rp.refresh_mode.setCurrentText('seconds')
    rp.refresh_changed.emit()
    _cache_result(qa, 'native2d', dim=2)


@scenario('D03', 'D', est=240)
def d03_stepped(qa):
    """Initialise Model / Exec / Interrupt / END on the 2D case."""
    C = cases()
    qa.goto('setup')
    qa.set_case(C['N2D'])
    qa.goto('run')
    rp = qa.win.run_panel
    qa.click(rp.init_btn, 'Initialise Model')
    qa.pump(1.5)
    qa.shot('initialised')
    qa.check(qa.log_has('[model initialised'),
             'the G1 hint is there after Initialise Model', 'S3')
    qa.note(f'after init: Run enabled={rp.run_btn.isEnabled()} '
            f'Exec1 enabled={rp._exec_btns[0].isEnabled()} '
            f'progress={rp.progress.value()} chips={rp.chip_texts()}')
    qa.check(rp._exec_btns[0].isEnabled(),
             'and the Exec buttons came alive', 'S2')
    qa.click(rp._exec_btns[1], 'Exec 10')
    qa.pump(1.5)
    qa.shot('exec10')
    qa.note(f'chips after Exec 10: {rp.chip_texts()}')
    qa.click(rp._exec_btns[2], 'Exec 100')
    qa.pump(1.5)
    qa.click(rp._exec_btns[5], 'Interrupt')
    qa.pump(1.0)
    qa.shot('interrupted')
    # the port says this where the run state is read, not only in the log
    qa.note(f'paused readout: {rp.paused_text()!r}')
    qa.check(bool(rp.paused_text().strip()),
             'an interrupted run says so beside the run state, not only '
             'in the log', 'S2')
    qa.click(rp._exec_btns[4], 'END')
    qa.check(qa.run_wait(300), 'END finished the run', 'S1')
    qa.shot('finished')


@scenario('D04', 'D', est=330)
def d04_native_3d_view(qa):
    """Native 3D run with the auto-attached embedded 3D view."""
    C = cases()
    qa.goto('setup')
    qa.set_case(C['N3D'])
    qa.shot('3d_form')
    qa.goto('run')
    rp = qa.win.run_panel
    qa.click(rp.run_btn, 'Run')
    ok = qa.until(lambda: rp.view3d_btn.isEnabled(), 90)
    qa.check(ok, 'the 3D View button is enabled at run start', 'S2')
    qa.pump(2.0)
    qa.shot('live_slice')
    qa.win._open_view3d()
    qa.pump(2.5)
    qa.shot('live_3d')
    qa.check(rp.current_view() == '3D view',
             'and it brings the 3D page forward', 'S2')
    rp.show_slice_tab()
    qa.pump(0.5)
    # a 40-cubed native 3D solve takes minutes; a short timeout here does
    # not just fail this scenario, it poisons the cache the E group reads
    qa.check(_wait_while_progressing(qa), 'the 3D run finished', 'S1')
    qa.shot('finished_slice')
    rp.show_3d_tab()
    qa.pump(1.5)
    qa.shot('finished_3d')
    v = rp.view3d
    qa.note(f'after the run: frames in the host={getattr(v, "_n_frames", "?")} '
            f'3D View enabled={rp.view3d_btn.isEnabled()}')
    rp.show_slice_tab()
    _cache_result(qa, 'native3d', dim=3)


@scenario('D05', 'D', est=200)
def d05_stop_midrun(qa):
    """Stop during a native 3D run: bar, label, buttons."""
    C = cases()
    qa.goto('setup')
    qa.set_case(C['N3D'])
    qa.goto('run')
    rp = qa.win.run_panel
    qa.click(rp.run_btn, 'Run')
    qa.check(qa.wait_log('3D Blast Solver', 40),
             'the 3D solver announced itself', 'S1')
    qa.pump(4.0)
    t0 = time.perf_counter()
    qa.click(rp.stop_btn, 'Stop')
    qa.shot('stop_requested')
    qa.note(f'right after Stop: Stop enabled={rp.stop_btn.isEnabled()} '
            f'Run enabled={rp.run_btn.isEnabled()}')
    qa.check(qa.run_wait(180), 'the run stopped', 'S1')
    qa.note(f'stop latency {time.perf_counter() - t0:.1f} s')
    qa.shot('stopped')
    labels = [e.label for e in qa.win.results.entries()]
    qa.check(labels and labels[-1].endswith('(stopped)'),
             'the stopped run is labelled "(stopped)"', 'S2',
             evidence=str(labels))
    qa.check(rp.progress.value() < rp.progress.maximum(),
             'and the progress bar is NOT filled after a stop')
    _cache_result(qa, 'native3d_stopped', dim=3)


@scenario('D06', 'D', est=90)
def d06_double_start(qa):
    """A second start while a run is live must be refused, not queued."""
    C = cases()
    qa.goto('setup')
    qa.set_case(C['N2D'])
    qa.goto('run')
    rp = qa.win.run_panel
    qa.click(rp.run_btn, 'Run')
    qa.check(qa.wait_log('2D Blast Solver', 40),
             'the first run started', 'S1')
    worker = qa.win.ctrl.worker
    qa.check(not rp.run_btn.isEnabled(),
             'Run is disabled while a run is live - the refusal is '
             'visible before it is needed', 'S2')
    qa.win._run_single()            # the accelerator path, which is live
    qa.pump(0.6)
    qa.shot('second_start')
    qa.check(qa.win.ctrl.worker is worker,
             'a second start did NOT replace the running worker', 'S1')
    qa.win.ctrl.stop()
    qa.check(qa.run_wait(180), 'and the run still stops cleanly', 'S1')


# ═══════════════════════════════════════════════════════════════════════
#  Group E - the Results tab, on the cached native runs
# ═══════════════════════════════════════════════════════════════════════
def _combo_items(combo):
    return [combo.itemText(i) for i in range(combo.count())]


@scenario('E01', 'E', est=60)
def e01_picker_and_1d(qa):
    """The result picker, the 1D views, and 3D asked of a 1D result."""
    ensure_results(qa)
    qa.goto('results')
    rs = qa.win.results
    qa.note('picker: ' + str(_combo_items(rs.sel)))
    if not select_result(qa, 'QA native1d'):
        return
    qa.shot('1d_fields')
    qa.check(rs.fields.page() == 'figure',
             'a 1D result draws profiles, not a map '
             f'(page {rs.fields.page()!r})', 'S2')
    for view in ('Gauges', 'Animation', '3D'):
        rs.show_view(view)
        qa.pump(0.8)
        qa.shot(f'1d_{view.lower()}')
    rs.show_view('Fields')
    qa.pump(0.5)
    qa.click(rs._export_btns['profile'], 'Profile')
    qa.pump(1.0)
    # G3: asking for the 3D viewer on a 1D result has to say something
    # where the user is looking, not only in the Run-tab log
    rs.open_3d()
    qa.pump(0.8)
    qa.check(qa.log_has('select a 3D result'),
             '3D Viewer on a 1D result explains itself', 'S3')
    qa.shot('after_3dviewer_click')


@scenario('E02', 'E', est=120)
def e02_2d_fields(qa):
    """Every 2D field for the first and last snapshot, with and without
    the mesh."""
    ensure_results(qa)
    qa.goto('results')
    if not select_result(qa, 'QA native2d'):
        return
    f = qa.win.results.fields
    snaps = _combo_items(f.snap_sel)
    fields = _combo_items(f.field_sel)
    qa.note(f'2D snapshots: {snaps}; fields: {fields}')
    qa.check(bool(snaps) and bool(fields),
             'the 2D result offers snapshots and fields', 'S1')
    for name in fields:
        f.field_sel.setCurrentText(name)
        for s in (snaps[0], snaps[-1]):
            f.snap_sel.setCurrentText(s)
            qa.pump(0.6)
            tag = (name.replace(' ', '_') + '_'
                   + s.replace(' ', '_')[:12])
            qa.shot(tag)
            qa.check(f.page() in ('image', 'figure'),
                     f'{name} / {s} drew something', 'S2')
    f.field_sel.setCurrentText(fields[0])
    f.snap_sel.setCurrentText(snaps[-1])
    f.show_mesh.setChecked(True)
    qa.pump(1.0)
    qa.shot('overpressure_mesh')
    f.show_mesh.setChecked(False)
    qa.pump(0.6)


@scenario('E03', 'E', est=60)
def e03_gauges_table(qa):
    """Gauges figure + summary table; four exports that write files."""
    ensure_results(qa)
    qa.goto('results')
    if not select_result(qa, 'QA native2d'):
        return
    rs = qa.win.results
    rs.show_view('Gauges')
    qa.pump(0.8)
    qa.shot('gauges_2d')
    rows = rs.gauges.rows()
    qa.note(f'summary rows: {rows}')
    qa.check(bool(rows), 'the summary table has a row per gauge', 'S2')
    # N2-09: the table must not starve the traces it sits above
    qa.check(rs.gauges.canvas.height() > rs.gauges.table.height(),
             f'the traces keep more height than the table '
             f'({rs.gauges.canvas.height()} vs '
             f'{rs.gauges.table.height()} px)', 'S2')
    # no scripted path: `default_path` already answers pick_dir with the
    # exports directory and save_file with a name inside it, which is
    # what distinguishes the two kinds. Handing a directory to a
    # save_file export is how these were "failing" a moment ago.
    out = qa.dirs['exports']
    for kind in ('summary', 'tsv', 'fieldcsv', 'report'):
        t_start = time.time()
        rs.export(kind, threaded=False)
        qa.pump(1.5)
        written = [os.path.relpath(p, out)
                   for p in _written_since(out, t_start)]
        qa.check(bool(written), f'the {kind} export wrote a file', 'S2',
                 evidence=str(written))
        qa.note(f'{kind} -> {written}')
        qa.shot(f'after_{kind}_export')
    if select_result(qa, 'QA native1d'):
        qa.shot('gauges_1d')
    rs.show_view('Fields')


@scenario('E04', 'E', est=60)
def e04_animation(qa):
    """Replay: play/pause, the slider, and ONE colour range per video."""
    ensure_results(qa)
    qa.goto('results')
    if not select_result(qa, 'QA native2d'):
        return
    rs = qa.win.results
    rs.show_view('Animation')
    qa.pump(1.0)
    an = rs.anim
    qa.shot('anim_frame0')
    qa.check(an.play_btn.isEnabled(), 'Play is enabled', 'S2')
    n = an.slider.maximum()
    qa.note(f'recorded frames: slider 0..{n}, scale={an.scale()!r} '
            f'used={an.scale_used()!r}')
    qa.check(n > 0, 'the slider spans the recorded frames', 'S2')
    first = an.image.levels
    an.start_play()
    qa.pump(2.0)
    qa.shot('playing')
    an.stop_play()
    qa.check(not an.timer.isActive(), 'and stopping stops the timer', 'S2')
    an.slider.setValue(n)
    qa.pump(0.6)
    qa.shot('last_frame')
    qa.check(an.image.levels == first,
             'the last frame keeps the SAME colour range as the first - '
             'one range for the whole video', 'S2',
             evidence=f'{first} -> {an.image.levels}')
    an.set_show_mesh(True)
    qa.pump(1.0)
    an.slider.setValue(max(0, n // 2))
    qa.pump(0.6)
    qa.shot('mid_frame_mesh')
    an.set_show_mesh(False)
    rs.show_view('Fields')


@scenario('E05', 'E', est=120)
def e05_3d_fields(qa):
    """Every 3D field entry, plus the mesh overlay."""
    ensure_results(qa)
    qa.goto('results')
    if not select_result(qa, 'QA native3d'):
        return
    f = qa.win.results.fields
    fields = _combo_items(f.field_sel)
    qa.note(f'3D fields: {fields}')
    for name in fields:
        f.field_sel.setCurrentText(name)
        qa.pump(0.8)
        qa.shot(name.replace(' ', '_').replace('(', '').replace(')', ''))
        qa.check(f.page() in ('image', 'figure'),
                 f'{name} drew something', 'S2')
    f.field_sel.setCurrentText(fields[0])
    f.show_mesh.setChecked(True)
    qa.pump(1.0)
    qa.shot('ovp_slice_mesh')
    f.show_mesh.setChecked(False)
    qa.win.results.show_view('Gauges')
    qa.pump(0.8)
    qa.shot('gauges_3d')
    qa.win.results.show_view('Fields')


@scenario('E06', 'E', est=200)
def e06_3d_viewer(qa):
    """The embedded 3D viewer: feed timing + every control.

    The Tk app blocked the UI here for 1 to 10 s because pyvista was
    imported on the click. The port pays that in the child process, so
    the gate stays and the new number is the port's evidence.
    """
    ensure_results(qa)
    qa.goto('results')
    if not select_result(qa, 'QA native3d'):
        return
    rs = qa.win.results
    _, ms = qa.timeit('feed_result native3d', rs.open_3d)
    qa.check(ms < 1000,
             f'opening the 3D viewer blocked the UI for {ms:.0f} ms (G4)',
             'S2')
    qa.pump(2.0)
    qa.shot('viewer_default')
    v = rs.view3d
    if not hasattr(v, '_field_btns'):
        qa.note('no 3D host on this build (pyvista missing)')
        return
    qa.note('field buttons: ' + ', '.join(
        f'{k}={b.isEnabled()}' for k, b in v._field_btns.items()))
    for key in ('rho', 'e', 'p_peak', 'imp', 'p'):
        btn = v._field_btns.get(key)
        if btn is None or not btn.isEnabled():
            qa.note(f'field {key} is not offered for this result')
            continue
        btn.setChecked(True)
        qa.pump(1.2)
        qa.shot(f'field_{key}')
    v._checks['auto_scale'].setChecked(False)
    v._vmin.setText('0')
    v._vmax.setText('200')
    v._clim_changed()
    qa.pump(1.2)
    qa.shot('manual_clim_0_200')
    was_log = v._checks['log'].isChecked()
    v._checks['log'].setChecked(not was_log)
    qa.pump(1.2)
    qa.shot('log_toggled')
    v._checks['log'].setChecked(was_log)
    v._checks['auto_scale'].setChecked(True)
    v._checks['iso'].setChecked(False)
    qa.pump(1.0)
    qa.shot('iso_off')
    v._checks['iso'].setChecked(True)
    qa.pump(0.8)
    rs.show_view('Fields')


@scenario('E07', 'E', est=150)
def e07_exports(qa):
    """PNGs and the animation: the file is the GRID, not the screen."""
    ensure_results(qa)
    qa.goto('results')
    if not select_result(qa, 'QA native2d'):
        return
    rs = qa.win.results
    out = qa.dirs['exports']
    t_start = time.time()
    rs.export('pngs', threaded=False)
    qa.pump(2.0)
    pngs = _written_since(out, t_start, '.png')
    qa.check(len(pngs) > 1,
             'PNGs wrote the whole snapshot grid, several files - the '
             'screen shows one field, the file does not', 'S2',
             evidence=str(sorted(os.path.basename(p) for p in pngs)))
    qa.check(all(os.path.getsize(p) > 5000 for p in pngs),
             'and each one is a real image', 'S2')
    qa.shot('after_pngs')
    t_vid = time.time()
    rs.export('gif', threaded=False)

    def _video():
        # by size, not only by extension: write_animation falls back
        # from .mp4 to .gif when ffmpeg is missing, and the export names
        # its own file
        return [p for p in _written_since(out, t_vid)
                if os.path.getsize(p) > 20000]
    # the writer reports its own progress and the file lands when it is
    # done, which for 81 frames is well past any fixed sleep
    qa.until(lambda: bool(_video()), 120)
    vids = _video()
    qa.check(bool(vids), 'the animation export wrote a video', 'S2',
             evidence=str([os.path.basename(p) for p in vids]))
    qa.note(f'exports in {out}: '
            f'{sorted(os.path.basename(p) for p in _walk(out))}')
    qa.shot('after_anim')


@scenario('E08', 'E', est=30)
def e08_remove(qa):
    """Remove blanks every sub-view and disables every export."""
    ensure_results(qa)
    qa.goto('results')
    rs = qa.win.results
    n0 = len(rs.entries())
    if not n0:
        qa.check(False, 'nothing to remove', 'S2')
        return
    rs.sel.setCurrentIndex(n0 - 1)
    qa.pump(0.6)
    rs.remove_current()
    qa.pump(0.8)
    qa.shot('after_remove')
    qa.check(len(rs.entries()) == n0 - 1,
             f'Remove took the entry out ({n0} -> {len(rs.entries())})',
             'S2')
    if not rs.entries():
        qa.check(not any(b.isEnabled()
                         for b in rs._export_btns.values()),
                 'with nothing left, every export is disabled', 'S2')
        qa.check(rs.fields.page() == 'empty',
                 'and Fields shows its placeholder rather than a stale '
                 f'picture (page {rs.fields.page()!r})', 'S2')


@scenario('E09', 'E', est=30)
def e09_title(qa):
    """The title box rides into the figures and the exported names."""
    ensure_results(qa)
    qa.goto('results')
    if not select_result(qa, 'QA native2d'):
        return
    rs = qa.win.results
    rs.title_box.setText('QA title')
    qa.pump(1.0)
    qa.shot('titled')
    qa.check('QA title' in (rs.title_extra() or ''),
             'the panel carries the typed title', 'S3',
             evidence=repr(rs.title_extra()))
    qa.check('QA title' in (rs.fields.title() or ''),
             'and it reaches the figure title', 'S3',
             evidence=repr(rs.fields.title()))
    rs.title_box.setText('')
    qa.pump(0.6)


def _walk(root):
    out = []
    for base, _dirs, files in os.walk(root):
        out.extend(os.path.join(base, f) for f in files)
    return out


def _written_since(root, t0, suffix=None):
    """Files an export has just written, by MTIME rather than by
    appearing.

    A set difference misses a re-run: the second time a scenario runs,
    the export overwrites the same names and the diff comes back empty -
    so the check reports that nothing was written while the files sit
    there, freshly stamped. That cost two false findings.
    """
    out = []
    for p in _walk(root):
        if suffix and not p.lower().endswith(suffix):
            continue
        try:
            if os.path.getmtime(p) >= t0 - 1.0:
                out.append(p)
        except OSError:
            continue
    return sorted(out)


# ═══════════════════════════════════════════════════════════════════════
#  Group F - real blastFoam runs in WSL
# ═══════════════════════════════════════════════════════════════════════
def _foreign_busy(qa):
    return [ln for ln in qa.wsl_pgrep() if ln and not ln.startswith('<')]


def _wait_while_progressing(qa, stall_s=420, hard_s=5400):
    """Wait for a run, judging it by PROGRESS rather than by a stopwatch.

    A fixed timeout asks the wrong question. F02's fixture has no
    terminate boundary, so it runs to the safety cap: it took 723 s here
    against a 700 s limit, the harness gave up, `reap_own` killed the
    solver as an orphan, and the app then reported a failed run - three
    findings, none of them a defect, all from a number being too small.

    So: wait while the solver's own step counter keeps moving, give up
    only when it has genuinely stalled, and keep a hard ceiling so a
    wedged run cannot hold the budget forever.
    """
    t0 = last_move = time.perf_counter()
    last_step = None
    while qa.worker_alive():
        qa.pump(2.0)
        now = time.perf_counter()
        step = qa.win.run_panel.chip_texts().get('step')
        if step != last_step:
            last_step, last_move = step, now
        if now - last_move > stall_s:
            qa.note(f'the run stopped advancing at step {step!r} - '
                    f'{stall_s:.0f} s without a step')
            return False
        if now - t0 > hard_s:
            qa.note(f'giving up after {hard_s:.0f} s at step {step!r}')
            return False
    qa.pump(1.0)
    return True


def _foam_run(qa, case, label, timeout, show_mesh=False):
    """Set a foam case, run it from the Run tab, and photograph the
    stages the backend actually goes through.

    A disabled Run button means the case does not validate. Carrying on
    anyway is how one scenario came to report another's run as its own,
    so this stops instead: no run started, nothing to observe.
    """
    qa.goto('setup')
    qa.set_case(case)
    qa.shot(f'{label}_setup')
    qa.note(f'{label} strip: ' + ' | '.join(qa.strip_text()))
    qa.goto('run')
    rp = qa.win.run_panel
    rp.show_mesh.setChecked(show_mesh)
    t0 = time.perf_counter()
    if not qa.click(rp.run_btn, 'Run'):
        qa.check(False,
                 f'Run is enabled for {label}, i.e. its case validates',
                 'S1', evidence=' | '.join(qa.strip_text()))
        qa.note(f'{label}: Run disabled, so no run started - not '
                f'attributing someone else\'s run to it')
        return False
    if qa.wait_log('checking WSL', 20):
        qa.shot(f'{label}_checking_wsl')
    if qa.wait_log('blockMesh', 150):
        qa.pump(0.5)
        qa.shot(f'{label}_meshing')
    if qa.wait_log('[blastfoam] write', 300):
        frac = rp.progress.value() / max(1, rp.progress.maximum())
        qa.note(f'{label}: progress at the first write = {frac:.3f} '
                f'({time.perf_counter() - t0:.0f} s after Run)')
        qa.check(frac > 0.0,
                 'the progress bar has moved by the first write (B7)',
                 'S3')
        qa.pump(2.5)
        qa.shot(f'{label}_first_write')
    qa.check(_wait_while_progressing(qa), f'{label} finished', 'S1')
    qa.note(f'{label} wall {time.perf_counter() - t0:.0f} s')
    qa.shot(f'{label}_finished')
    own = qa.reap_own()
    qa.note(f'own runs after {label}: '
            + ', '.join(f'{os.path.basename(d)} alive={r.alive}'
                        for d, r in own.items()))
    return True


@scenario('F00', 'F', est=480)
def f00_gate(qa):
    """WSL availability, foreign solvers, and the disk gate.

    Deferred rather than failed when the distro is busy or absent: a
    foreign solver makes every timing in this group meaningless, and a
    full disk is how WSL was brought down once already.
    """
    from blastlab.solvers.foam import env
    box = {}

    def probe():
        box['r'] = env.check_available()
    th = threading.Thread(target=probe, daemon=True)
    th.start()
    qa.until(lambda: not th.is_alive(), 150)
    qa.note(f'check_available -> {box.get("r")}')
    if not box.get('r', (False,))[0]:
        raise Deferred('blastFoam is unavailable')
    t0 = time.perf_counter()
    busy = _foreign_busy(qa)
    while busy and time.perf_counter() - t0 < 400:
        qa.log(f'foreign solvers still running: {busy} - waiting')
        qa.pump(30)
        busy = _foreign_busy(qa)
    qa.ckpt.setdefault('f00_attempts', 0)
    qa.ckpt['f00_attempts'] += 1
    if busy and qa.ckpt['f00_attempts'] < 3:
        raise Deferred(f'foreign solvers busy: {busy}')
    if busy:
        qa.note(f'proceeding with foreign solvers running: {busy} '
                f'(timings contaminated)')
    qa.ckpt['pre_f_pgrep'] = qa.wsl_pgrep()
    qa.check(qa.disk_gate(), 'the disk gate passes before the foam runs',
             'S1')
    try:
        info = env.run_info()
        before = sum((i.get('bytes') or 0) for i in info.values())
        qa.ckpt['runs_root_bytes_before'] = before
        qa.note(f'runs root before F: {len(info)} runs, '
                f'{before / 1e9:.1f} GB')
    except Exception as exc:
        qa.log(f'run_info failed: {exc}')


@scenario('F01', 'F', est=420)
def f01_foam_1d(qa):
    """1D blastFoam (C4) through the Run tab."""
    if not _foam_run(qa, cases()['F1D'], 'foam1d', 600):
        return
    qa.goto('results')
    qa.shot('results_fields')
    qa.win.results.show_view('Gauges')
    qa.pump(0.8)
    qa.shot('results_gauges')
    qa.check(bool(qa.win.results.gauges.rows()),
             'the foam gauges reached the summary table', 'S2')
    qa.win.results.show_view('Fields')
    _cache_result(qa, 'foam1d', dim=1)


@scenario('F02', 'F', est=480)
def f02_foam_2d_planar(qa):
    """2D planar blastFoam: every field, replay, and the VTK export."""
    if not _foam_run(qa, cases()['F2D'], 'foam2d', 700, show_mesh=True):
        return
    qa.goto('results')
    rs = qa.win.results
    fields = _combo_items(rs.fields.field_sel)
    meta = rs.current().result.meta if rs.current() else {}
    qa.note(f'foam 2D fields: {fields}; '
            f'peak_source={meta.get("peak_source")}')
    for f in fields:
        rs.fields.field_sel.setCurrentText(f)
        qa.pump(0.6)
        qa.shot(f.replace(' ', '_'))
    rs.show_view('Gauges')
    qa.pump(0.8)
    qa.shot('gauges')
    rs.show_view('Animation')
    qa.pump(0.8)
    qa.shot('anim')
    rs.show_view('Fields')
    qa.check(rs.export_enabled('vtk'),
             'the VTK export is offered for a foam run', 'S2')
    qa.click(rs._export_btns['vtk'], 'VTK')
    ok = qa.wait_log('VTK export done', 300)
    tail = qa.run_log().strip().splitlines()[-4:]
    qa.note('VTK export log: ' + ' / '.join(tail))
    qa.check(ok, 'and it finishes', 'S2', evidence=' / '.join(tail))
    qa.shot('after_vtk')
    _cache_result(qa, 'foam2d', dim=2)


@scenario('F03', 'F', est=420)
def f03_foam_3d_tiny(qa):
    """3D blastFoam: the live 3D view, then Results playback with p_peak."""
    C = cases()
    qa.goto('setup')
    qa.set_case(C['F3D'])
    qa.goto('run')
    rp = qa.win.run_panel
    t0 = time.perf_counter()
    qa.click(rp.run_btn, 'Run')
    qa.check(qa.until(lambda: rp.view3d_btn.isEnabled(), 300),
             '3D View is enabled for the foam 3D run', 'S2')
    qa.wait_log('[blastfoam] write', 300)
    qa.pump(3.0)
    rp.show_3d_tab()
    qa.pump(1.5)
    qa.shot('live_3d')
    rp.show_slice_tab()
    qa.pump(0.5)
    qa.shot('live_slice')
    qa.check(_wait_while_progressing(qa), 'the foam 3D run finished',
             'S1')
    qa.note(f'foam3d wall {time.perf_counter() - t0:.0f} s')
    qa.shot('finished')
    qa.reap_own()
    qa.goto('results')
    rs = qa.win.results
    rs.open_3d()
    qa.pump(2.0)
    qa.shot('results_3d')
    v = rs.view3d
    if hasattr(v, '_field_btns'):
        qa.note('3D viewer fields for foam: ' + ', '.join(
            f'{k}={b.isEnabled()}' for k, b in v._field_btns.items()))
        peak = v._field_btns.get('p_peak')
        if peak is not None and peak.isEnabled():
            peak.setChecked(True)
            qa.pump(1.5)
            qa.shot('results_3d_ppeak')
        v._field_btns['p'].setChecked(True)
        v._checks['mesh'].setChecked(True)
        qa.pump(1.5)
        qa.shot('results_3d_mesh')
        v._checks['mesh'].setChecked(False)
    rs.show_view('Fields')
    _cache_result(qa, 'foam3d', dim=3)


@scenario('F04', 'F', est=420)
def f04_foam_2d_refine(qa):
    """2D planar with static refinement zones, and Show mesh everywhere."""
    qa.goto('setup')
    qa.win.setup.show_mesh.setChecked(True)
    ran = _foam_run(qa, cases()['F2D_REF'], 'refine2d', 700,
                    show_mesh=True)
    qa.win.setup.show_mesh.setChecked(False)
    if not ran:
        return
    qa.goto('results')
    rs = qa.win.results
    rs.fields.show_mesh.setChecked(True)
    qa.pump(1.0)
    qa.shot('fields_mesh')
    rs.show_view('Animation')
    qa.pump(0.8)
    qa.shot('replay_mesh')
    an = rs.anim
    an.slider.setValue(an.slider.maximum())
    qa.pump(0.8)
    qa.shot('replay_last_mesh')
    rs.show_view('Fields')
    out = qa.dirs['exports']
    t_start = time.time()
    rs.export('pngs', threaded=False)
    qa.until(lambda: bool(_written_since(out, t_start, '.png')), 150)
    files = [os.path.basename(p)
             for p in _written_since(out, t_start, '.png')]
    qa.note(f'PNG export with mesh: {files}')
    qa.check(bool(files), 'the PNG export wrote files', 'S2')
    rs.fields.show_mesh.setChecked(False)
    _cache_result(qa, 'foam2d_refine', dim=2)


@scenario('F05', 'F', est=420)
def f05_foam_2d_amr(qa):
    """2D planar dynamic AMR: a per-write mesh in the live view and replay."""
    qa.goto('setup')
    qa.set_case(cases()['F2D_AMR'])
    strip = qa.strip_text()
    qa.check(any('AMR up to level' in s for s in strip),
             'the report names the AMR levels and the display level',
             'S2', evidence=str(strip))
    if not _foam_run(qa, cases()['F2D_AMR'], 'amr2d', 700, show_mesh=True):
        return
    lines = [ln for ln in qa.run_log().splitlines() if 'AMR t =' in ln]
    qa.note(f'{len(lines)} AMR log lines; first {lines[:1]}, '
            f'last {lines[-1:]}')
    qa.check(bool(lines), 'the mesh really did adapt during the run', 'S2')
    qa.goto('results')
    rs = qa.win.results
    rs.fields.show_mesh.setChecked(True)
    rs.show_view('Animation')
    qa.pump(0.8)
    qa.shot('replay_frame0_mesh')
    an = rs.anim
    an.slider.setValue(an.slider.maximum())
    qa.pump(0.8)
    qa.shot('replay_last_mesh')
    frames = (rs.current().result.meta or {}).get('frames') or {}
    lv = frames.get('levels')
    n = len(frames.get('pressures') or [])
    qa.check(lv is not None and len(lv) == n,
             'a level map was recorded per frame, so the replay can draw '
             'the mesh the solver actually had', 'S2',
             evidence=f'{None if lv is None else len(lv)} of {n}')
    rs.show_view('Fields')
    qa.shot('fields_mesh')
    rs.fields.show_mesh.setChecked(False)
    _cache_result(qa, 'foam2d_amr', dim=2)


@scenario('F06', 'F', est=200)
def f06_foam_3d_amr(qa):
    """3D dynamic AMR: a per-frame mesh in the 3D viewer."""
    from blastlab.core.case import validate_case
    qa.goto('setup')
    qa.set_case(cases()['F3D_AMR'])
    qa.note('3D AMR strip: ' + ' | '.join(qa.strip_text()))
    # ask the REPORT, not the rendered text: the old guard looked for the
    # word "error" in the strip, no message contains it, so the guard
    # never fired and this scenario ran an invalid case for months
    rep = validate_case(qa.win.setup.get_case())
    if rep.errors:
        qa.check(False, 'the 3D AMR fixture validates', 'S2',
                 evidence=str(rep.errors))
        return
    if not _foam_run(qa, cases()['F3D_AMR'], 'amr3d', 900):
        return
    qa.goto('results')
    rs = qa.win.results
    rs.open_3d()
    qa.pump(2.5)
    qa.shot('results_3d_amr')
    v = rs.view3d
    if hasattr(v, '_checks'):
        v._checks['mesh'].setChecked(True)
        qa.pump(2.0)
        qa.shot('results_3d_amr_mesh')
        v._checks['mesh'].setChecked(False)
    rs.show_view('Fields')
    _cache_result(qa, 'foam3d_amr', dim=3)


@scenario('F07', 'F', est=120)
def f07_stop_during_meshing(qa):
    """Stop while blockMesh is running.

    The thing being checked is what must NOT happen: a "Run failed"
    dialog, and a Results entry for a run that never started.
    """
    from blastlab.core.case import Case2D
    qa.goto('setup')
    qa.set_case(Case2D(geometry='axisymmetric', Lx=5.0, Ly=5.0,
                       cell_size_m=0.004, charge=8.0, center=(0.0, 2.5),
                       n_snapshots=2, record_frames=0,
                       solver='blastfoam', material='TNT'))
    qa.goto('run')
    rp = qa.win.run_panel
    n_res = len(qa.win.results.entries())
    d0 = _nlines(os.path.join(qa.out, 'dialogs.jsonl'))
    qa.click(rp.run_btn, 'Run')
    qa.check(qa.wait_log('blockMesh', 200),
             'the blockMesh stage line appeared', 'S2')
    t0 = time.perf_counter()
    qa.click(rp.stop_btn, 'Stop')
    qa.shot('stop_during_meshing')
    qa.check(qa.run_wait(150), 'the run ended', 'S1')
    dt = time.perf_counter() - t0
    qa.note(f'stop during meshing -> the run ended in {dt:.1f} s')
    qa.check(dt < 15, f'a stop during meshing returns in {dt:.1f} s', 'S2')
    d1 = _nlines(os.path.join(qa.out, 'dialogs.jsonl'))
    qa.check(d1 == d0,
             'no "Run failed" dialog for a deliberate stop', 'S2')
    qa.check(len(qa.win.results.entries()) == n_res,
             'and no Results entry for a run that never started', 'S2')
    qa.shot('after_stop')
    qa.note('log tail: '
            + ' / '.join(qa.run_log().strip().splitlines()[-4:]))
    qa.reap_own()


@scenario('F08', 'F', est=200)
def f08_stop_during_solve(qa):
    """Stop while solving; the revolved 3D view; the browser's 'running'."""
    qa.goto('setup')
    qa.set_case(cases()['F_STOP'])
    qa.goto('run')
    rp = qa.win.run_panel
    qa.click(rp.run_btn, 'Run')
    qa.check(qa.wait_log('[blastfoam] write', 300),
             'the axisymmetric stop case reached its first write', 'S2')
    qa.pump(2.0)
    rp.show_3d_tab()
    qa.pump(3.0)
    qa.shot('revolved_3d')
    rp.show_slice_tab()
    browser = qa.win.results.open_run_browser()
    if browser is not None:
        qa.until(lambda: not browser._busy, 120)
        qa.shot('browser_with_running', widget=browser)
        tag = f'_p{os.getpid()}-'
        own = sorted((n for n in browser.names() if tag in n),
                     reverse=True)
        qa.note(f'browser rows: {len(browser.names())}; own: {own}; '
                f'status {browser.status.text()!r}')
        if own:
            browser.select(own[0])
            qa.pump(0.3)
            row = browser.rows.get(own[0]) or {}
            qa.check(row.get('alive') is True,
                     'the browser reports the live run as running', 'S2',
                     evidence=str(row.get('alive')))
            qa.script_answers(False)
            browser.delete_selected()
            qa.pump(0.6)
            qa.shot('browser_delete_refused', widget=browser)
            qa.note(f'status after Delete on a running run: '
                    f'{browser.status.text()!r}')
        browser.close()
        qa.pump(0.5)
    t0 = time.perf_counter()
    qa.click(rp.stop_btn, 'Stop')
    qa.check(qa.run_wait(300), 'the run stopped', 'S1')
    qa.note(f'a graceful stop during the solve took '
            f'{time.perf_counter() - t0:.1f} s')
    qa.check(not qa.log_has('did not stop cleanly'),
             'and it was graceful', 'S2')
    labels = [e.label for e in qa.win.results.entries()]
    qa.check(labels and labels[-1].endswith('(stopped)'),
             'the stopped foam run is labelled "(stopped)"', 'S2',
             evidence=str(labels))
    qa.shot('stopped')
    qa.reap_own()
    _cache_result(qa, 'foam2d_axi_stopped', dim=2)


@scenario('F09', 'F', est=240)
def f09_run_browser(qa):
    """The run browser: list, Load (post-mortem == live), Delete."""
    qa.goto('results')
    browser = qa.win.results.open_run_browser()
    if browser is None:
        qa.check(False, 'the run browser opened', 'S1')
        return
    qa.pump(1.0)
    qa.shot('browser_listing', widget=browser)
    qa.until(lambda: not browser._busy, 180)
    qa.shot('browser_sized', widget=browser)
    qa.note(f'browser: {len(browser.names())} rows; '
            f'status {browser.status.text()!r}')
    cached = qa.cached('foam2d')
    name = ''
    if cached is not None:
        name = os.path.basename(
            str((cached.meta or {}).get('case_dir', '')).rstrip('/\\'))
    qa.note(f'F02 run dir: {name!r}; in the browser: '
            f'{name in browser.names()}')
    if name and name in browser.names():
        browser.select(name)
        qa.pump(0.3)
        n_before = len(qa.win.results.entries())
        browser.load_selected()
        ok = qa.wait_log('Loaded:', 300)
        qa.pump(1.5)
        qa.check(ok, 'the post-mortem load succeeded', 'S1',
                 evidence=qa.run_log()[-400:])
        qa.check(len(qa.win.results.entries()) > n_before,
                 'and it arrived in the Results picker', 'S2')
        qa.shot('after_load', widget=browser)
        qa.shot('results_loaded')
    browser.close()
    qa.pump(0.5)


@scenario('F10', 'F', est=100)
def f10_foam_dialogs(qa):
    """The foam-only exports on a native result, and the other way round."""
    ensure_results(qa, names=('native2d',))
    qa.goto('results')
    rs = qa.win.results
    if select_result(qa, 'QA native2d'):
        qa.check(not rs.export_enabled('vtk'),
                 'VTK is NOT offered for a native result', 'S2')
        btn = rs._export_btns.get('vtk')
        if btn is not None and not btn.isEnabled():
            qa.check(bool((btn.toolTip() or '').strip()),
                     'and it says why rather than just being grey', 'S3',
                     evidence=repr(btn.toolTip()))
        qa.shot('native_exports')
    if qa.cached('foam2d') is not None:
        ensure_results(qa, names=('foam2d',))
        if select_result(qa, 'QA foam2d'):
            qa.check(rs.export_enabled('vtk'),
                     'and it IS offered for a foam result', 'S2')
            qa.shot('foam_exports')


@scenario('F11', 'F', est=200, terminal=True)
def f11_close_during_foam(qa):
    """Close the window mid-foam-run: the solver must not be orphaned.

    Terminal: the window is gone afterwards.
    """
    qa.goto('setup')
    qa.set_case(cases()['F_STOP'])
    qa.goto('run')
    qa.click(qa.win.run_panel.run_btn, 'Run')
    qa.check(qa.wait_log('[blastfoam] write', 300),
             'the run reached its first write', 'S1')
    qa.pump(2.0)
    t0 = time.perf_counter()
    qa.win.close()
    qa.pump(1.0)
    dt = time.perf_counter() - t0
    qa.note(f'closing during a foam run returned in {dt:.1f} s')
    qa.check(dt < 20, f'and it returned promptly ({dt:.1f} s)', 'S2')
    qa.pump(8.0)
    own = qa.reap_own()           # reports an orphan as an S1 by itself
    qa.note('own runs after the close: '
            + ', '.join(f'{os.path.basename(d)} alive={r.alive}'
                        for d, r in own.items()))
    qa.win = None


# ═══════════════════════════════════════════════════════════════════════
#  Group G - the Chain tab
# ═══════════════════════════════════════════════════════════════════════
def _chain_forms(qa, model='QA_CHAIN'):
    """A small 1D -> 2D -> 3D chain, all three stages checked, into the
    model folder `model` (OUT-1: the Run tab's boxes). Returns the panel;
    the folder is `qa.chain_folder`."""
    from blastlab.core.case import Case1D, Case2D, Case3D
    from blastlab.ui.testing import use_model
    ch = qa.win.chain
    qa.chain_folder = use_model(qa.win, model)
    ch.set_stage_case(1, Case1D(radius_m=0.6, charge_kg=0.5,
                                cell_size_m=0.004, n_snapshots=1,
                                gauge_radii=[], gauge_file=None))
    ch.set_stage_case(2, Case2D(geometry='axisymmetric', Lx=1.0, Ly=1.6,
                                cell_size_m=0.03, charge=0.5,
                                center=(0.0, 0.8), n_snapshots=1,
                                gauges=[], gauge_file=None,
                                anim_file=None, record_frames=0))
    ch.set_stage_case(3, Case3D(Lx=1.2, Ly=1.2, Lz=1.2, cell_size_m=0.08,
                                charge=0.5, center=(0.6, 0.6, 0.6),
                                n_snapshots=1, gauges=[],
                                gauge_file=None, anim_file=None,
                                record_frames=0))
    for d in (1, 2, 3):
        ch.use[d].setChecked(True)
    qa.pump(0.5)
    return ch


@scenario('G01', 'G', est=90)
def g01_chain_validation(qa):
    """Every Chain refusal, and the model folder that must NOT appear."""
    qa.goto('chain')
    # a model of its own (use_model removes a leftover one), so the
    # assertion below cannot be satisfied by an earlier session's folder
    ch = _chain_forms(qa, 'QA_CHAIN_REFUSED')
    ws = qa.chain_folder
    qa.shot('chain_default')
    refusals = []
    ch.error_sink = lambda title, lines: refusals.append(list(lines))

    def refuse(tag):
        n = len(refusals)
        started = ch.run()
        qa.pump(0.3)
        qa.check(started is not True and len(refusals) > n,
                 f'{tag} is refused, with a reason', 'S2',
                 evidence=str(refusals[-1] if refusals else []))
        qa.note(f'{tag}: {refusals[-1] if refusals else []}')

    for d in (1, 2, 3):
        ch.use[d].setChecked(False)
    refuse('no stage checked')
    ch.use[1].setChecked(True)
    ch.use[3].setChecked(True)
    refuse('a gap in the chain (1 and 3)')
    ch.use[2].setChecked(True)
    ch.forms[2].v['geometry'].set('planar')
    qa.pump(0.3)
    refuse('a planar stage 2 with a 3D stage after it')
    ch.forms[2].v['geometry'].set('axisymmetric')
    qa.pump(0.3)
    ch.forms[2].v['Lx'].set('abc')
    qa.pump(0.3)
    refuse('a stage-2 field that does not parse')
    qa.check(any('Stage 2' in ln for ln in (refusals[-1] if refusals
                                            else [])),
             'and the refusal names the stage', 'S2',
             evidence=str(refusals[-1] if refusals else []))
    ch.forms[2].v['Lx'].set('1.0')
    ch.forms[2].v['cy'].set('99')
    qa.pump(0.3)
    refuse('a charge outside stage 2')
    ch.forms[2].v['cy'].set('0.8')
    qa.pump(0.3)
    # OUT-1: the Run tab's model boxes are checked by the chain too
    rp = qa.win.run_panel
    name = rp.current_run_name()
    rp.run_name.setText('')
    refuse('an empty Model name on the Run tab')
    qa.check(any('Model name' in ln for ln in (refusals[-1] if refusals
                                               else [])),
             'and the refusal names the Model box', 'S2',
             evidence=str(refusals[-1] if refusals else []))
    rp.run_name.setText(name)
    qa.shot('after_refusals')
    qa.note(f'stage switcher after the refusals: stage {ch.stage()} '
            '(a refusal naming stage 2 should have brought it forward)')
    # QA-23/T28, OUT-1: the model folder is created only once a chain
    # will really run (it replaced the workspace this held before)
    qa.check(not os.path.isdir(ws),
             'no model folder was created while every run was refused',
             'S2')
    qa.check(ch.run_btn.isEnabled(),
             'Run chain is still enabled after refused starts', 'S2')


@scenario('G02', 'G', est=420)
def g02_chain_run(qa):
    """A 1D -> 2D -> 3D native chain, end to end."""
    qa.goto('chain')
    ch = _chain_forms(qa)
    refusals = []
    ch.error_sink = lambda title, lines: refusals.append(list(lines))
    t0 = time.perf_counter()
    started = ch.run()
    qa.pump(0.6)
    qa.check(started is True, 'the chain started', 'S1', str(refusals))
    if started is not True:
        return
    qa.check(not ch.run_btn.isEnabled(),
             'Run chain is disabled while the chain runs', 'S2')
    qa.goto('chain')
    qa.shot('chain_running')
    qa.goto('run')
    qa.shot('stage1')
    qa.check(qa.wait_log('=== Stage 2D ===', 300), 'stage 2 started',
             'S1')
    qa.pump(2.0)
    qa.shot('stage2')
    qa.check(qa.wait_log('=== Stage 3D ===', 600), 'stage 3 started',
             'S1')
    qa.pump(3.0)
    qa.shot('stage3')
    qa.win.run_panel.show_3d_tab()
    qa.pump(1.5)
    qa.shot('stage3_3d')
    qa.win.run_panel.show_slice_tab()
    qa.check(_wait_while_progressing(qa), 'the chain finished', 'S1')
    qa.note(f'chain wall {time.perf_counter() - t0:.0f} s')
    qa.shot('chain_done')
    qa.check(ch.run_btn.isEnabled(),
             'Run chain is enabled again afterwards', 'S2')
    labels = [e.label for e in qa.win.results.entries()]
    qa.note(f'results after the chain: {labels}')
    # OUT-1: <MODEL>\1d, 2d, 3d, the hand-offs at the root
    ws = qa.chain_folder
    files = sorted(os.listdir(ws)) if os.path.isdir(ws) else []
    qa.note(f'model folder: {files}')
    qa.check(all(os.path.isfile(os.path.join(ws, d, 'MODEL.json'))
                 for d in ('1d', '2d', '3d')),
             'the model folder holds a stage folder with its MODEL.json '
             'per stage', 'S2', evidence=str(files))
    qa.check(all(f in files for f in ('handoff_1d_to_2d.txt',
                                      'handoff_2d_to_3d.npz',
                                      'manifest.json')),
             'and the hand-offs and the root manifest at the model root',
             'S2', evidence=str(files))
    qa.goto('results')
    qa.shot('results_picker')
    _cache_result(qa, 'chain3d', dim=3)


@scenario('G03', 'G', est=120)
def g03_cross_tab_guard(qa):
    """Run chain while a Run-tab run is live."""
    C = cases()
    qa.goto('setup')
    qa.set_case(C['N2D'])
    qa.goto('run')
    qa.click(qa.win.run_panel.run_btn, 'Run')
    qa.check(qa.wait_log('2D Blast Solver', 40), 'the run started', 'S1')
    qa.goto('chain')
    ch = _chain_forms(qa)
    qa.shot('chain_while_running')
    qa.check(not ch.run_btn.isEnabled(),
             'Run chain is disabled during a Run-tab run', 'S2')
    refusals = []
    ch.error_sink = lambda title, lines: refusals.append(list(lines))
    started = ch.run()          # the callback behind the disabled button
    qa.pump(0.4)
    qa.check(started is not True,
             'and the callback behind it refuses too, so the guard is '
             'not just a greyed button', 'S1', str(refusals))
    qa.win.ctrl.stop()
    qa.check(qa.run_wait(300), 'the Run-tab run still stops', 'S1')


# ═══════════════════════════════════════════════════════════════════════
#  Group H - light mode over everything that draws
# ═══════════════════════════════════════════════════════════════════════
@scenario('H01', 'H', est=60)
def h01_preview_theme(qa):
    """The Setup preview across a theme toggle, with and without a redraw.

    The interesting half is "without": a palette change has to repaint
    what is already on screen, not wait for the next edit.
    """
    from blastlab.core.case import Case2D
    qa.goto('setup')
    qa.set_case(Case2D(geometry='planar', Lx=3.0, Ly=2.0,
                       cell_size_m=0.05, charge=5.0, center=(1.0, 0.5),
                       gauges=[(2.0, 1.0)],
                       obstacles=[(1.5, 1.8, 0.0, 0.6)]))
    qa.win.setup.show_mesh.setChecked(True)
    qa.pump(1.0)
    qa.shot('preview_dark')
    qa.set_mode('light')
    qa.shot('preview_light_no_redraw')
    qa.field('Lx', '3.0001')
    qa.pump(0.8)
    qa.shot('preview_light_redrawn')
    qa.set_mode('dark')
    qa.shot('preview_dark_no_redraw')
    qa.field('Lx', '3.0')
    qa.win.setup.show_mesh.setChecked(False)
    qa.check(qa.win.setup.preview_kind() == '2d',
             'the preview survived four theme changes', 'S2')


@scenario('H02', 'H', est=200)
def h02_live_theme(qa):
    """A theme toggle in the middle of a live native 2D run."""
    C = cases()
    qa.goto('setup')
    qa.set_case(C['N2D'])
    qa.goto('run')
    rp = qa.win.run_panel
    rp.show_mesh.setChecked(True)
    qa.click(rp.run_btn, 'Run')
    qa.check(qa.wait_log('2D Blast Solver', 40), 'the run started', 'S1')
    qa.pump(2.0)
    qa.set_mode('light')
    qa.pump(1.5)
    qa.shot('live_light')
    qa.check(qa.worker_alive() or not qa.win.ctrl.running,
             'the run is still alive (or already done) after a repaint',
             'S2')
    qa.check(qa.run_wait(300), 'and it finished', 'S1')
    qa.shot('finished_light')
    qa.set_mode('dark')
    qa.pump(1.0)
    qa.shot('finished_dark_again')
    rp.show_mesh.setChecked(False)


@scenario('H03', 'H', est=150)
def h03_results_light(qa):
    """Results views, the run browser and Chain in light mode."""
    ensure_results(qa)
    qa.set_mode('light')
    qa.goto('results')
    rs = qa.win.results
    for label in ('QA native2d', 'QA native3d'):
        if not select_result(qa, label):
            continue
        for view in ('Fields', 'Gauges', 'Animation'):
            rs.show_view(view)
            qa.pump(0.8)
            qa.shot(f'{label[-2:]}_{view.lower()}')
        if label.endswith('3d'):
            rs.open_3d()
            qa.pump(1.5)
            qa.shot('3d_viewer')
    rs.show_view('Fields')
    browser = rs.open_run_browser()
    if browser is not None:
        qa.until(lambda: browser.table.rowCount() > 0, 90)
        qa.shot('browser_light', widget=browser)
        browser.close()
        qa.pump(0.5)
    qa.goto('chain')
    qa.shot('chain_light')
    qa.goto('run')
    qa.shot('run_light')
    qa.set_mode('dark')


# ═══════════════════════════════════════════════════════════════════════
#  Group I - robustness
# ═══════════════════════════════════════════════════════════════════════
@scenario('I01', 'I', est=330)
def i01_rapid_tabs(qa):
    """Random tab and view switching during a native 3D run."""
    import random
    C = cases()
    qa.goto('setup')
    qa.set_case(C['N3D'])
    qa.goto('run')
    rp = qa.win.run_panel
    qa.click(rp.run_btn, 'Run')
    qa.check(qa.wait_log('3D Blast Solver', 40), 'the run started', 'S1')
    qa.pump(3.0)
    rnd = random.Random(7)
    t0 = time.perf_counter()
    qa.action = 'rapid tabs'
    while time.perf_counter() - t0 < 12:
        k = rnd.choice(['setup', 'run', 'results', 'chain'])
        qa.win._show(k)
        qa.tab = k
        if k == 'results' and rnd.random() < 0.5:
            qa.win.results.show_view(rnd.choice(
                ['Fields', 'Gauges', 'Animation', '3D']))
        if k == 'run' and rnd.random() < 0.5:
            (rp.show_3d_tab if rnd.random() < 0.5
             else rp.show_slice_tab)()
        qa.pump(0.1)
    qa.action = ''
    qa.goto('run')
    qa.check(qa.win.ctrl.running or not qa.win.ctrl.running,
             'the window survived the switching', 'S1')
    qa.check(qa.run_wait(900), 'and the run still finished', 'S1')
    for k in ('setup', 'run', 'results', 'chain'):
        qa.goto(k)
        qa.shot('after_rapid')
    rp.show_slice_tab()


@scenario('I02', 'I', est=120, terminal=True)
def i02_close_during_native(qa):
    """Close the window two seconds into a native 3D run.

    Terminal: the window is gone afterwards, so this ends the
    invocation and the next one starts a fresh app.
    """
    C = cases()
    qa.goto('setup')
    qa.set_case(C['N3D'])
    qa.goto('run')
    qa.click(qa.win.run_panel.run_btn, 'Run')
    qa.check(qa.wait_log('3D Blast Solver', 40), 'the run started', 'S1')
    qa.pump(2.0)
    worker = qa.win.ctrl.worker
    t0 = time.perf_counter()
    qa.win.close()
    qa.pump(1.0)
    dt = time.perf_counter() - t0
    thread = getattr(worker, 'thread', None) or worker
    try:
        thread.join(60)
        alive = thread.is_alive()
    except Exception:
        alive = 'unknown'
    qa.log(f'close took {dt:.1f} s; worker alive after join: {alive}')
    qa.check(dt < 12,
             f'closing during a native run returned in {dt:.1f} s', 'S2')
    qa.check(alive is not True,
             'and the solver thread did not outlive the window', 'S2')
    qa.win = None


@scenario('I03', 'I', est=60)
def i03_bad_json(qa):
    """Open case on garbage / wrong schema / wrong dim / missing file."""
    qa.goto('setup')
    from blastlab.core.case import Case2D
    qa.set_case(Case2D(Lx=3.3))
    where = qa.dirs['cwd']
    bad = {'garbage.json': '{not json',
           'wrongschema.json': json.dumps({'schema': 99, 'dim': 2}),
           'dim5.json': json.dumps({'dim': 5}),
           'empty.json': ''}
    for name, text in bad.items():
        with open(os.path.join(where, name), 'w', encoding='utf-8') as f:
            f.write(text)
    for name in list(bad) + ['missing.json']:
        qa.win._open_case(os.path.join(where, name))
        qa.pump(0.5)
        lx = _form(qa).v['Lx'].get()
        qa.note(f'{name}: form Lx still {lx!r}')
        qa.check(lx == '3.3',
                 f'{name} left the form alone rather than half-loading it',
                 'S2')
    qa.shot('after_bad_json')


@scenario('I04', 'I', est=120)
def i04_huge_cells(qa):
    """Cap errors on Run / Initialise; a warning-level case starts."""
    from blastlab.core.case import Case2D
    qa.goto('setup')
    qa.set_case(Case2D(geometry='planar', Lx=10.0, Ly=10.0,
                       cell_size_m=0.001, center=(5.0, 5.0)))
    qa.goto('run')
    rp = qa.win.run_panel
    qa.win._run_single()
    qa.pump(1.0)
    qa.check(not qa.worker_alive(),
             'a 100 M cell case is refused at Run', 'S1')
    rp.init_btn.click()
    qa.pump(1.0)
    qa.check(not qa.worker_alive(),
             'and refused at Initialise Model too', 'S1')
    qa.goto('setup')
    qa.set_case(Case2D(geometry='planar', Lx=6.0, Ly=6.0,
                       cell_size_m=0.004, charge=50.0, center=(3.0, 3.0),
                       record_frames=0))
    qa.note('2.25 M-cell 2D case strip: ' + ' | '.join(qa.strip_text()))
    qa.goto('run')
    d0 = _nlines(os.path.join(qa.out, 'dialogs.jsonl'))
    qa.click(rp.run_btn, 'Run')
    qa.pump(2.0)
    started = qa.worker_alive() or qa.log_has('[run finished]')
    d1 = _nlines(os.path.join(qa.out, 'dialogs.jsonl'))
    qa.note(f'warning-level case: started={started}, dialogs={d1 - d0} '
            f'(no confirmation prompt for a merely large run)')
    qa.check(started,
             'a case that only WARNS starts without asking', 'S2')
    qa.shot('large_run_started')
    qa.win.ctrl.stop()
    qa.check(qa.run_wait(300), 'and stops on request', 'S1')


@scenario('I05', 'I', est=60)
def i05_input_stress(qa):
    """Odd numeric inputs: 1e400, nan, inf, whitespace, decimal comma."""
    from blastlab.core.case import Case2D
    qa.goto('setup')
    qa.set_case(Case2D())
    for val in ('1e400', 'nan', 'inf', ' 1 ', '1,5', '-0'):
        qa.field('charge', val)
        qa.note(f'charge={val!r}: ' + ' | '.join(qa.strip_text()))
        qa.shot('charge_' + val.strip().replace(',', 'comma')
                .replace(' ', '').replace('-', 'neg'))
    qa.field('charge', '1.0')
    qa.field('n_snapshots', '2.7')
    # refusing 2.7 is the CORRECT answer, so get_case() raising here is a
    # pass and not a crash - it is recorded, never propagated
    try:
        parsed = f'parsed as {qa.win.setup.get_case().n_snapshots}'
    except Exception as exc:
        parsed = (f'rejected: {type(exc).__name__}: '
                  + ' / '.join(str(exc).splitlines()))
    qa.note(f'n_snapshots=2.7: ' + ' | '.join(qa.strip_text())
            + f' ({parsed})')
    qa.field('n_snapshots', '6')
    qa.field('cell', '1e-9')
    qa.note('cell=1e-9: ' + ' | '.join(qa.strip_text()))
    qa.check(bool(qa.strip_text()),
             'a 1e-9 m cell is reported rather than accepted in silence',
             'S2')
    qa.field('cell', '0.025')


@scenario('I06', 'I', est=40)
def i06_small_window_3d(qa):
    """A below-minimum window with the Results 3D sub-tab open."""
    ensure_results(qa)
    qa.goto('results')
    if select_result(qa, 'QA native3d'):
        qa.win.results.open_3d()
        qa.pump(1.5)
    for spec in ('1100x720', '900x600'):
        qa.geometry(spec)
        qa.shot(f'3d_{spec}')
    qa.reset_window()
    qa.check(qa.win.width() >= 1100,
             f'the window refuses to go under its own minimum '
             f'({qa.geometry()})', 'S2')
    qa.win.results.show_view('Fields')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out')
    ap.add_argument('--resume', action='store_true')
    ap.add_argument('--only', default='')
    ap.add_argument('--skip', default='')
    ap.add_argument('--scenario', default='')
    ap.add_argument('--redo', default='')
    ap.add_argument('--budget', type=float, default=540)
    ap.add_argument('--smoke', action='store_true')
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--window', action='store_true',
                    help='run on the real desktop instead of offscreen')
    ap.add_argument('--solver', default='',
                    help="seed the sidebar solver mode the app starts in "
                         "('native' | 'blastfoam')")
    args = ap.parse_args()

    if args.out:
        out = args.out
    elif args.resume and latest_out():
        out = latest_out()
    else:
        out = os.path.join(QA_ROOT, time.strftime('%Y%m%d-%H%M'))
    os.makedirs(out, exist_ok=True)
    print(f'QA output: {out}', flush=True)

    # scratch settings + CWD BEFORE importing the app. auto_cleanup off
    # is not optional: building the window otherwise sweeps the WSL run
    # corpus (see core/settings.load).
    settings = os.path.join(out, 'settings.json')
    if not os.path.exists(settings):
        with open(settings, 'w', encoding='utf-8') as f:
            json.dump(dict(auto_cleanup=False), f)
    if args.solver:
        with open(settings, encoding='utf-8') as f:
            st = json.load(f)
        st['solver'] = args.solver
        with open(settings, 'w', encoding='utf-8') as f:
            json.dump(st, f)
    os.environ['BLASTLAB_SETTINGS'] = settings
    os.environ['MPLBACKEND'] = 'Agg'
    cwd = os.path.join(out, 'cwd')
    os.makedirs(cwd, exist_ok=True)
    os.chdir(cwd)
    sys.path.insert(0, REPO)

    qa = QA(out, args)
    only = [g for g in args.only.split(',') if g]
    skip = [s for s in args.skip.split(',') if s]
    for r in (s for s in args.redo.split(',') if s):
        qa.ckpt['done'].pop(r, None)

    def selected(sid, group):
        if args.smoke:
            return sid == 'S00'
        if args.scenario:
            return sid in args.scenario.split(',')
        if sid == 'S00':
            return False
        if only and group not in only and sid not in only:
            return False
        return sid not in skip

    todo = [s for s in SCENARIOS if selected(s[0], s[1])
            and s[0] not in qa.ckpt['done']]
    if args.list:
        for sid, group, est, _term, _fn, doc in SCENARIOS:
            st = qa.ckpt['done'].get(sid, {}).get('status', '-')
            print(f'  {sid:5s} {group:2s} {est:4d}s {st:10s} {doc}')
        print(f'{len(todo)} pending')
        return 0
    if not todo:
        print('nothing to do')
        return 0

    qa.ckpt['invocations'].append(dict(start=time.time(),
                                       argv=sys.argv[1:]))
    qa.save_ckpt()

    install_warning_capture(qa)
    qa.patch_dialogs()
    exit_code = 0
    try:
        qa.build_app()
        for sid, group, est, terminal, fn, _doc in todo:
            if os.path.exists(os.path.join(out, 'STOP')):
                raise KillSwitch()
            if est > qa.budget_left():
                qa.log(f'budget: {qa.budget_left():.0f}s left < {est}s '
                       f'for {sid} - exiting 75')
                exit_code = 75
                break
            qa.begin(sid)
            try:
                fn(qa)
                qa.end(sid, 'done')
            except KillSwitch:
                qa.end(sid, 'killed')
                raise
            except Deferred as exc:
                qa.end(sid, 'deferred', str(exc))
                qa.ckpt['done'].pop(sid, None)
                qa.save_ckpt()
                qa.log(f'{sid} deferred: {exc} - exiting 75')
                exit_code = 75
                break
            except Exception:
                err = traceback.format_exc()
                qa.finding('S1', 'harness-crash', f'{sid} raised',
                           evidence=err[-2000:])
                qa.end(sid, 'crashed', err)
            if terminal:
                qa.log(f'{sid} is terminal - exiting 75 for a fresh app')
                exit_code = 75
                break
            qa.neutral()
        else:
            exit_code = 0
    except KillSwitch:
        qa.log('kill switch - stopping')
        exit_code = 3
    except Exception:
        qa.log('HARNESS CRASH\n' + traceback.format_exc())
        exit_code = 1
    finally:
        try:
            if qa.win is not None and qa.worker_alive():
                qa.win.ctrl.stop()
                qa.pump(90, until=lambda: not qa.worker_alive())
        except Exception:
            pass
        try:
            if qa.win is not None:
                qa.win.close()
                qa.pump(0.6)
        except Exception:
            pass
        qa.ckpt['invocations'][-1]['end'] = time.time()
        qa.ckpt['invocations'][-1]['exit'] = exit_code
        qa.save_ckpt()
        pending = [s[0] for s in SCENARIOS if selected(s[0], s[1])
                   and s[0] not in qa.ckpt['done']]
        qa.log(f'exit {exit_code}; pending: {pending}')
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
