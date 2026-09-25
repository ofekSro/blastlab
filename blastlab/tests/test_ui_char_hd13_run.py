"""Characterisation: Run on the Qt HD 1.3 (0-D) tab (Phase 7).

docs/ARCHITECTURE_REVIEW.md section 5, Phase 7. Drives the REAL
`ui.app.MainWindow` offscreen, switched to the 0-D dimension with the
starter case in its form, through `_run_single` -> `_run_hd13`, and pins
in one golden (`char_golden/ui_hd13_run.json`) plus the report
(`char_golden/ui_hd13_run_report.html`):

  * with a report file typed in: which temp directories are made (their
    `tempfile.mkdtemp` arguments), the temp case JSON written into each,
    byte for byte (ARCHITECTURE_REVIEW Q4 - the owner has not yet said
    whether it is provenance, so it is pinned as it is), the report written
    where it was asked for (byte for byte after the timestamp and PNG
    masking of `test_char_hd13_cli.py`), the status line and its timer,
    no dialog, and HOW MANY TIMES `assessment.run` is called - two today
    (UX finding: `_run_hd13` runs the assessment once to fail before
    touching disk, then `services/hd13.assess` runs it again - before
    Phase 7 it was `run_and_report`);
  * with the report field blank: the `hd13_report.html` fallback, written
    relative to the working directory;
  * a case `assessment.validate` refuses: the dialog title and text, no
    temp directory, no run, no report;
  * a run that raises: the dialog title and text, and nothing on disk.

Only the first scenario runs the real assessment (twice, about 40 s each
- the starter case has the sensitivity band off). The blank-field one
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
        """{dir index: {file name: text}} for every temp dir made."""
        out = {}
        for i, d in enumerate(self.dirs):
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


def press_run(win, root, run=None):
    """One Run press, recorded."""
    win._status.setText('')
    win._status_timer.stop()
    with Recorder(win, root, run) as rec:
        win._run_single()
    return dict(errors=rec.errors, mkdtemp=rec.mkdtemp,
                temp_files=rec.temp_files(), assessment_runs=rec.runs,
                status=win._status.text(),
                status_timer_active=win._status_timer.isActive())


def main_window():
    from blastlab.ui.app import MainWindow
    win = MainWindow()
    win.show()
    pump(150)
    win.setup.set_dim(0)
    pump(150)
    assert win.setup.dim == 0 and win.setup.form is win.setup.forms[0]
    return win


def collect():
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
        pump(50)
        results = []

        def real(case):
            results.append(_REAL_RUN(case))
            return results[-1]
        g = press_run(win, root, real)
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
        pump(50)
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
        pump(50)
        g = press_run(win, root)
        g['out_files'] = sorted(os.listdir(out_dir))
        got['refused'] = g

        # 4. a run that raises
        form.set_case(starter)
        form.v['report_file'].set(os.path.join(out_dir, 'raised.html'))
        pump(50)

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
    got, report = collect()
    cc.check_json('ui_hd13_run.json', got)
    cc.check_text('ui_hd13_run_report.html', report)


def main():
    return cc.run_main('CHAR UI HD13 RUN', [test_hd13_run])


if __name__ == '__main__':
    sys.exit(main())
