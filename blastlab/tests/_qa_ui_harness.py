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
                           else qa.default_path(name, kw))
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

    def default_path(self, name, kw):
        """Somewhere inside the run, so nothing is written to the repo."""
        if name == 'pick_dir':
            return self.dirs['exports']
        stem = f'{self.scenario_id}_{self.ckpt["shot_counter"]:03d}'
        suffix = str(kw.get('default_suffix') or '.txt')
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
        identical line cannot satisfy it."""
        mark = self._log_mark or 0
        return self.until(lambda: text in self.run_log()[mark:], timeout)

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
    qa.note(f'Chain workspace default: {qa.win.chain.ws_box.text()!r}')
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
