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
        self.win = MainWindow()
        self.win.resize(1280, 840)
        self.win.show()
        self.pump(1.2)
        self._watch_bridge()
        self.log(f'window up: {self.win.width()}x{self.win.height()}')
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

    def geometry(self):
        return f'{self.win.width()}x{self.win.height()}'

    def reset_window(self):
        self.win.resize(1280, 840)
        self.pump(0.4)

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

    def qt_handler(mode, ctx, message):
        text = str(message)
        if not text.strip():
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
