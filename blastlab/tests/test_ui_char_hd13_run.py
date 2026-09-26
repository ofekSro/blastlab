"""Characterisation: Run on the Qt HD 1.3 (0-D) tab (Phase 7, UX 1).

docs/ARCHITECTURE_REVIEW.md section 5, Phase 7, and docs/UX_REVIEW.md
finding 1. Drives the REAL `ui.app.MainWindow` offscreen, switched to the
0-D dimension with the starter case in its form, through `_run_single` ->
`_run_hd13`, and pins in one golden (`char_golden/ui_hd13_run.json`) plus
the report (`char_golden/ui_hd13_run_report.html`):

  * with a report file typed in: which temp directories are made (their
    `tempfile.mkdtemp` arguments), the temp case JSON written into each,
    byte for byte (ARCHITECTURE_REVIEW Q4 - the owner has not yet said
    whether it is provenance, so it is pinned as it is), the report written
    where it was asked for (byte for byte after the timestamp and PNG
    masking of `test_char_hd13_cli.py`), the status line, its tooltip,
    colour and timer, the lines the run added to the Run log (HD1-16,
    QA F2), no dialog, and HOW MANY TIMES `assessment.run` is called - once since
    UX 1 (it was twice: once "to fail before touching disk", then again
    in `services/hd13.assess`);
  * the Run controls right after the press (`during`: Run and Initialise
    Model off, the bar indeterminate, the status line) and after it
    finishes (`after`), and that a second press while it works starts
    nothing;
  * with the report field blank: the `hd13_report.html` fallback, written
    relative to the working directory;
  * a case `assessment.validate` refuses: the dialog title and text, no
    temp directory, no run, no report;
  * a run that raises: the dialog title and text, and nothing on disk -
    the temp directory, made before the assessment since UX 1, is removed
    again (`temp_dirs_left`).

The assessment runs on a worker thread, so each press is waited out with
the event loop running, and the longest gap between ticks of a 10 ms
timer during the real assessment must stay under `MAX_GAP_S`.

Only the first scenario runs the real assessment (once, about 40-90 s -
the starter case has the sensitivity band off). The blank-field one
reuses that result through a patched `assessment.run`, so the figures and
the report are still built for real; the failing one patches it to raise.

Script only - it builds Qt widgets, so conftest.py keeps it out of
pytest collection (`test_ui_*.py`). BLASTLAB_SETTINGS points at a private
file with `auto_cleanup: false` (`char_common`), so building the window
can never sweep the run corpus (CLAUDE.md 8.2).

Run:  cd blastlab/tests && python test_ui_char_hd13_run.py [--update]
"""
import os
import shutil
import sys
import tempfile
import time

import char_common as cc
from blastlab.ui.testing import ensure_qapp, pump             # noqa: E402

app = ensure_qapp()

from blastlab.core import assessment                          # noqa: E402
from test_char_hd13_cli import normalise_html                 # noqa: E402

_REAL_RUN = assessment.run
_REAL_MKDTEMP = tempfile.mkdtemp


class Recorder:
    """For the duration of one Run press: `win.show_error`,
    `tempfile.mkdtemp` (made under `root`) and `assessment.run` (counted,
    and replaced by `run` when one is given) are recorders."""

    def __init__(self, win, root, run=None):
        self.win, self.root, self.run = win, root, run
        self.errors, self.mkdtemp, self.dirs, self.runs = [], [], [], 0

    def __enter__(self):
        def show_error(title, msg):
            self.errors.append([title, msg])

        def mkdtemp(suffix=None, prefix=None, dir=None):
            self.mkdtemp.append(dict(suffix=suffix, prefix=prefix, dir=dir))
            d = _REAL_MKDTEMP(suffix=suffix, prefix=prefix, dir=self.root)
            self.dirs.append(d)
            return d

        def run(case):
            self.runs += 1
            return (self.run or _REAL_RUN)(case)

        self.win.show_error = show_error
        tempfile.mkdtemp = mkdtemp
        assessment.run = run
        return self

    def __exit__(self, *exc):
        del self.win.show_error
        tempfile.mkdtemp = _REAL_MKDTEMP
        assessment.run = _REAL_RUN

    def temp_files(self):
        """{dir index: {file name: text}} for every temp dir made and
        still there (a failed run removes its own)."""
        out = {}
        for i, d in enumerate(self.dirs):
            if not os.path.isdir(d):
                continue
            files = {}
            for n in sorted(os.listdir(d)):
                with open(os.path.join(d, n), 'rb') as f:
                    files[n] = f.read().decode('utf-8')
            out[str(i)] = files
        return out


def scrub(obj, root):
    if isinstance(obj, str):
        for form in (root, root.replace('\\', '/')):
            obj = obj.replace(form, '<tmp>')
        return obj.replace('\\', '/')
    if isinstance(obj, list):
        return [scrub(x, root) for x in obj]
    if isinstance(obj, dict):
        return {k: scrub(v, root) for k, v in obj.items()}
    return obj


#: UX finding 1, pre-registered before the first run of the worker
#: version: while the real assessment runs, the event loop may not stall
#: for longer than this. The inline version stalled for the whole
#: assessment, twice (91 s in one piece on the starter case, measured).
MAX_GAP_S = 1.0


def ui_state(win):
    """What the Run controls say right now."""
    bar = win.run_panel.progress
    return dict(busy=win._hd13_busy,
                run_enabled=win.run_panel.run_btn.isEnabled(),
                init_enabled=win.run_panel.init_btn.isEnabled(),
                bar_range=[bar.minimum(), bar.maximum()],
                switch_interval_s=sys.getswitchinterval(),
                status=win._status.text())


def press_run(win, root, run=None, gaps=None):
    """One Run press, recorded, waited out with the event loop running.

    The assessment is on a worker thread, so the recorders stay in place
    until the window says it is done. A 10 ms QTimer ticks throughout;
    the longest gap between its ticks goes into `gaps` when given - that
    is how long the window was unresponsive."""
    from PySide6.QtCore import QTimer
    from blastlab.ui import theme
    win._status.setText('')
    win._status.setToolTip('')
    win._status_timer.stop()
    log_before = win.run_panel.log_text()
    ticks = []
    timer = QTimer()
    timer.setInterval(10)
    timer.timeout.connect(lambda: ticks.append(time.perf_counter()))
    with Recorder(win, root, run) as rec:
        timer.start()
        ticks.append(time.perf_counter())
        win._run_single()
        during = ui_state(win)
        if win._hd13_busy:
            # F5 (or Initialise Model) while it works must not start a
            # second one: assessment_runs and mkdtemp would show it
            win._run_single()
        end = time.monotonic() + 900
        while win._hd13_busy:
            assert time.monotonic() < end, 'the HD 1.3 worker never finished'
            app.processEvents()
            time.sleep(0.002)
        ticks.append(time.perf_counter())
        timer.stop()
        app.processEvents()
    if gaps is not None:
        gaps.append(max(b - a for a, b in zip(ticks, ticks[1:])))
    after = ui_state(win)
    del after['status']
    log = win.run_panel.log_text()
    assert log.startswith(log_before), 'the Run log lost earlier lines'
    new_log = log[len(log_before):].lstrip('\n')
    return dict(errors=rec.errors, mkdtemp=rec.mkdtemp,
                temp_files=rec.temp_files(), assessment_runs=rec.runs,
                temp_dirs_left=sum(os.path.isdir(d) for d in rec.dirs),
                status=win._status.text(),
                # QA 2026-09-26-hd1-16 F2: the full text is in the tooltip
                # and the Run log, and the still-active rule makes the
                # short status line a warning
                status_tooltip=win._status.toolTip(),
                status_is_warning=(bool(win._status.text())
                                   and win._status.styleSheet()
                                   == f'color: {theme.cur("warn")};'),
                log_added=new_log.splitlines(),
                status_timer_active=win._status_timer.isActive(),
                during=during, after=after)


def main_window():
    from blastlab.ui.app import MainWindow
    win = MainWindow()
    win.show()
    pump(150)
    win.setup.set_dim(0)
    pump(150)
    assert win.setup.dim == 0 and win.setup.form is win.setup.forms[0]
    return win


def collect(gaps):
    root = _REAL_MKDTEMP(prefix='blastlab_char_hd13run_')
    here = os.getcwd()
    win = main_window()
    form = win.setup.forms[0]
    got, report = {}, None
    try:
        starter = cc.hd13_starter_case()

        # 1. a report file typed in - the real assessment
        form.set_case(starter)
        out_dir = os.path.join(root, 'out')
        os.makedirs(out_dir)
        form.v['report_file'].set(os.path.join(out_dir, 'report.html'))
        pump(400)                       # past the 300 ms validation timer
        results = []

        def real(case):
            results.append(_REAL_RUN(case))
            return results[-1]
        g = press_run(win, root, real, gaps)
        g['out_files'] = sorted(os.listdir(out_dir))
        with open(os.path.join(out_dir, 'report.html'), 'rb') as f:
            data = f.read()
        g['report_crlf_count'] = data.count(b'\r\n')
        got['typed'] = g
        report = normalise_html(data.decode('utf-8'))

        # 2. the report field blank: the fallback name, in the cwd
        cwd = os.path.join(root, 'cwd')
        os.makedirs(cwd)
        os.chdir(cwd)
        form.v['report_file'].set('')
        pump(400)
        g = press_run(win, root, lambda case: results[-1])
        g['cwd_files'] = sorted(os.listdir(cwd))
        with open(os.path.join(cwd, 'hd13_report.html'), 'rb') as f:
            blank = f.read()
        g['same_report_as_typed'] = \
            normalise_html(blank.decode('utf-8')) == report \
            and blank.count(b'\r\n') == data.count(b'\r\n')
        got['blank'] = g
        os.chdir(here)

        # 3. a case the validator refuses (two errors, so the join shows)
        form.v['report_file'].set(os.path.join(out_dir, 'refused.html'))
        form.v['charge_kg'].set('0')
        form.v['t_end'].set('0')
        pump(400)
        g = press_run(win, root)
        g['out_files'] = sorted(os.listdir(out_dir))
        got['refused'] = g

        # 4. a run that raises
        form.set_case(starter)
        form.v['report_file'].set(os.path.join(out_dir, 'raised.html'))
        pump(400)

        def boom(case):
            raise ValueError('char: the assessment failed')
        g = press_run(win, root, boom)
        g['out_files'] = sorted(os.listdir(out_dir))
        got['raised'] = g
    finally:
        os.chdir(here)
        win.close()
        pump(100)
        shutil.rmtree(root, ignore_errors=True)
    return scrub(got, root), report


def test_hd13_run():
    gaps = []
    got, report = collect(gaps)
    print(f'  longest event-loop gap during the real assessment: '
          f'{gaps[0] * 1e3:.1f} ms (limit {MAX_GAP_S * 1e3:.0f} ms)')
    cc.check_json('ui_hd13_run.json', got)
    cc.check_text('ui_hd13_run_report.html', report)
    assert gaps[0] < MAX_GAP_S, \
        f'the window stalled for {gaps[0]:.2f} s during the assessment'


def main():
    return cc.run_main('CHAR UI HD13 RUN', [test_hd13_run])


if __name__ == '__main__':
    sys.exit(main())
