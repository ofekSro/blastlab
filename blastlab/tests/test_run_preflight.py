"""The OUT-1 run pre-flight: no run starts without a Runs folder and a
Model name (docs/model-folder-and-vtk-plan.md sec. 2.1; batch plan
docs/batches/2026-09-26-out-1-model-folder.md, Steps 5 and 8).

  A  the Qt window, offscreen, dialogs stubbed: Run, Initialise Model
     and a resume all go through `MainWindow._model_target` - a refusal
     names its box and creates nothing, an existing model is overwritten
     only after Yes, and the Runs folder survives a close and reopen
  B  the command line: `--cli`, `--hd13` and `--hd13-wall-export` without
     `--runs-dir` / `--model` exit 2 with usage (added in Step 8)

The controller is stubbed where a real solve would add nothing: what is
pinned is the gate, not the run (test_model_folder.py part C runs the
worker with a model folder; _qa_ui_harness.py M03 a whole run).

Run:  cd blastlab/tests && python test_run_preflight.py
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
os.environ.setdefault('MPLBACKEND', 'Agg')
_dir = tempfile.mkdtemp(prefix='blastlab_preflight_')
os.environ['BLASTLAB_SETTINGS'] = os.path.join(_dir, 'settings.json')

FAIL = []
RAN = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    RAN.append(name)
    if not ok:
        FAIL.append(name)


class Dialogs:
    """Records every modal instead of showing it; `answer` is what a
    Yes/No question gets."""

    def __init__(self):
        self.errors, self.infos, self.questions = [], [], []
        self.answer = False

    def install(self):
        from blastlab.ui import dialogs
        self._real = (dialogs.show_error, dialogs.show_info,
                      dialogs.ask_yes_no)
        dialogs.show_error = lambda t, m, p=None: self.errors.append((t, m))
        dialogs.show_info = lambda t, m, p=None: self.infos.append((t, m))

        def ask(title, text, parent=None):
            self.questions.append((title, text))
            return self.answer
        dialogs.ask_yes_no = ask

    def clear(self):
        self.errors.clear()
        self.infos.clear()
        self.questions.clear()

    def restore(self):
        from blastlab.ui import dialogs
        (dialogs.show_error, dialogs.show_info,
         dialogs.ask_yes_no) = self._real


class Launches:
    """Stands in for RunController.start_stages / resume_foam_run."""

    def __init__(self, ctrl):
        self.calls = []
        ctrl.start_stages = lambda *a, **k: self.calls.append(
            ('start', a, k)) or True
        ctrl.resume_foam_run = lambda *a, **k: self.calls.append(
            ('resume', a, k)) or True


def listing(path):
    out = []
    for root, dirs, files in os.walk(path):
        for n in dirs + files:
            out.append(os.path.relpath(os.path.join(root, n), path))
    return sorted(out)


def part_a():
    from blastlab.ui.testing import ensure_qapp, pump, private_runs_dir
    ensure_qapp()
    from blastlab.ui.app import MainWindow
    runs = private_runs_dir()
    dlg = Dialogs()
    dlg.install()
    try:
        win = MainWindow()
        win.set_solver('native')
        win.show()
        pump(150)
        rp = win.run_panel
        launches = Launches(win.ctrl)
        check('the private settings fill the Runs folder box',
              rp.current_runs_dir() == runs, rp.current_runs_dir())
        check('the Model box starts empty (it names the run)',
              rp.current_run_name() == '')

        print('\nA1: an empty Runs folder box refuses, naming the box')
        rp.set_runs_dir('')
        rp.run_name.setText('MODEL')
        before = listing(runs)
        win._run_single()
        check('one error dialog', len(dlg.errors) == 1, str(dlg.errors))
        check('it names "Runs folder"',
              dlg.errors and 'Runs folder' in dlg.errors[0][1],
              dlg.errors[0][1] if dlg.errors else '')
        check('the worker never starts', launches.calls == [])
        check('no directory is created', listing(runs) == before)
        check('no question was asked', dlg.questions == [])

        print('\nA2: a missing folder and a bad name, the same way')
        dlg.clear()
        missing = os.path.join(runs, 'not_there')
        rp.set_runs_dir(missing)
        win._run_single()
        check('a missing folder is refused, naming it',
              len(dlg.errors) == 1 and 'does not exist' in dlg.errors[0][1]
              and missing in dlg.errors[0][1], str(dlg.errors))
        check('and is not created', not os.path.exists(missing))
        for bad in ('', 'A:B', 'CON', 'x.'):
            dlg.clear()
            rp.set_runs_dir(runs)
            rp.run_name.setText(bad)
            win._run_single()
            check(f'model name {bad!r} is refused, naming the box',
                  len(dlg.errors) == 1
                  and dlg.errors[0][1].startswith('Model name:'),
                  str(dlg.errors))
        check('nothing started', launches.calls == [])
        check('nothing created', listing(runs) == before)

        print('\nA3: an existing model - No changes nothing, Yes replaces')
        dlg.clear()
        rp.run_name.setText('MODEL')
        win._run_single()
        check('a new model runs without a question',
              dlg.questions == [] and len(launches.calls) == 1,
              f'{dlg.questions} {len(launches.calls)} launch(es)')
        folder = os.path.join(runs, 'MODEL')
        _how, _a, kw = launches.calls[-1]
        model = kw.get('model')
        check('the controller gets the prepared model folder',
              model is not None and model.folder == folder
              and model.model == 'MODEL' and model.runs_dir == runs,
              repr(model))
        check('and the pre-flight ValidationReport, for the manifest',
              len(kw.get('reports') or []) == 1
              and kw['reports'][0].n_cells,
              f"n_cells = {kw['reports'][0].n_cells}"
              if kw.get('reports') else 'none')
        check('the run is named after the model',
              kw.get('run_name') == 'MODEL', str(kw.get('run_name')))
        with open(os.path.join(folder, 'report.html'), 'w') as f:
            f.write('the previous run\n')
        launches.calls.clear()
        dlg.clear()
        dlg.answer = False
        win._run_single()
        check('an existing model asks first', len(dlg.questions) == 1
              and "MODEL already exists in" in dlg.questions[0][1]
              and 'Overwrite?' in dlg.questions[0][1],
              str(dlg.questions))
        check('No: no run', launches.calls == [])
        check('No: the old file is still there',
              os.path.isfile(os.path.join(folder, 'report.html')))
        dlg.clear()
        dlg.answer = True
        win._run_single()
        check('Yes: the run starts', len(launches.calls) == 1)
        check('Yes: the old file is gone',
              not os.path.exists(os.path.join(folder, 'report.html'))
              and os.listdir(folder) == ['.blastlab-model'],
              str(os.listdir(folder)))

        print('\nA4: a folder blastlab did not create is refused (Q4)')
        foreign = os.path.join(runs, 'Thesis')
        os.makedirs(foreign, exist_ok=True)
        with open(os.path.join(foreign, 'notes.txt'), 'w') as f:
            f.write('mine\n')
        launches.calls.clear()
        dlg.clear()
        rp.run_name.setText('Thesis')
        win._run_single()
        check('refused before any question',
              dlg.questions == [] and len(dlg.errors) == 1
              and 'was not created by blastlab' in dlg.errors[0][1],
              str(dlg.errors))
        check('nothing deleted, no run',
              os.listdir(foreign) == ['notes.txt'] and launches.calls == [])

        print('\nA5: Initialise Model goes through the same gate')
        dlg.clear()
        rp.set_runs_dir('')
        rp.run_name.setText('INIT')
        win._init_model()
        check('refused with the Runs folder message',
              len(dlg.errors) == 1 and 'Runs folder' in dlg.errors[0][1]
              and launches.calls == [], str(dlg.errors))
        rp.set_runs_dir(runs)
        dlg.clear()
        win._init_model()
        _how, _a, kw = launches.calls[-1] if launches.calls else ('', (), {})
        check('with the boxes filled it starts, held at step 0',
              kw.get('paused') is True and kw.get('model') is not None
              and os.path.isdir(os.path.join(runs, 'INIT')),
              f"paused={kw.get('paused')}")

        print('\nA6: a resume goes through the same gate')
        from blastlab.models.case import Case2D, save_case
        from blastlab.solvers.foam import env as foam_env
        scratch = tempfile.mkdtemp(prefix='blastlab_preflight_scratch_')
        save_case(Case2D(Lx=1.0, Ly=1.0, cell_size_m=0.05, charge=0.5,
                         center=(0.0, 0.5), solver='blastfoam'),
                  os.path.join(scratch, 'case.json'))
        real_paths = foam_env.case_paths
        posix = '/root/blastlab_runs/20260926-120000_2d_p1-00'
        foam_env.case_paths = lambda p: (posix, scratch)
        try:
            launches.calls.clear()
            dlg.clear()
            rp.run_name.setText('')
            got = win._resume_foam_run(posix)
            check('an empty Model box refuses the resume',
                  got is False and len(dlg.errors) == 1
                  and dlg.errors[0][1].startswith('Model name:')
                  and launches.calls == [], str(dlg.errors))
            rp.run_name.setText('RESUMED')
            dlg.clear()
            got = win._resume_foam_run(posix)
            how, args, kw = (launches.calls[-1] if launches.calls
                             else ('', (), {}))
            check('with a name the resume starts into the model folder',
                  got and how == 'resume' and args[:2] == (posix, 2)
                  and kw['model'].folder == os.path.join(runs, 'RESUMED')
                  and kw['case'].solver == 'blastfoam', f'{how} {args}')
        finally:
            foam_env.case_paths = real_paths
            shutil.rmtree(scratch, ignore_errors=True)

        print('\nA9: the HD 1.3 Run goes through the same gate')
        from blastlab.core import assessment
        real_run = assessment.run
        calls = []
        assessment.run = lambda case: calls.append(case) or real_run(case)
        try:
            win.setup.set_dim(0)
            pump(150)
            win.setup.forms[0].set_case(assessment.DeflagrationCase(
                name='preflight', charge_kg=5.0, volume_m3=1.0,
                vent_area_m2=0.02, t_end=0.5, n_out=50))
            pump(400)
            dlg.clear()
            rp.set_runs_dir(runs)
            rp.run_name.setText('')
            win._run_single()
            pump(50)
            check('an empty Model box refuses HD 1.3 before any assessment',
                  len(dlg.errors) == 1
                  and dlg.errors[0][1].startswith('Model name:')
                  and calls == [] and not win._hd13_busy, str(dlg.errors))
            check('the report-file row is gone from the 0-D form',
                  'report_file' not in win.setup.forms[0].v)
        finally:
            assessment.run = real_run
            win.setup.set_dim(2)
            pump(150)

        print('\nA7: the Runs folder survives a close and a reopen')
        other = os.path.join(_dir, 'elsewhere')
        os.makedirs(other, exist_ok=True)
        rp.set_runs_dir(other)
        rp.runs_dir.editingFinished.emit()
        with open(os.environ['BLASTLAB_SETTINGS'], encoding='utf-8') as f:
            saved = json.load(f).get('runs_dir')
        check('an edit is saved to the settings file at once',
              saved == other, str(saved))
        rp.set_runs_dir(runs)            # saved only on close now
        win.close()
        pump(60)
        win2 = MainWindow()
        pump(60)
        check('a new window shows the folder the last one closed with',
              win2.run_panel.current_runs_dir() == runs,
              win2.run_panel.current_runs_dir())
        with open(os.environ['BLASTLAB_SETTINGS'], encoding='utf-8') as f:
            st = json.load(f)
        check('and the settings file still has the sweep off',
              st.get('auto_cleanup') is False, str(st))
        win2.close()
        pump(30)
    finally:
        dlg.restore()


def part_a_controller():
    """RunController with a model: a real tiny native 1D run lands in the
    folder; a kept-scratch notice reaches the error dialog."""
    import time
    from blastlab.models.case import Case1D
    from blastlab.services import model_folder as mf
    from blastlab.ui.run_controller import RunController
    from blastlab.ui.testing import pump, private_runs_dir
    runs = private_runs_dir()
    shown = []
    ctrl = RunController()
    ctrl.show_error = lambda t, m: shown.append((t, m))
    target = mf.prepare_target(runs, 'CTRL', confirm=lambda t: True)
    case = Case1D(radius_m=1.0, charge_kg=0.5, cell_size_m=0.01,
                  n_snapshots=1, t_end=3e-4, gauge_radii=[0.5])
    check('start_stages takes the model', ctrl.start_stages(
        [(1, case)], run_name='CTRL', model=target))
    t0 = time.time()
    while ctrl.running and time.time() - t0 < 120:
        pump(30)
    check('the run finished', not ctrl.running)
    got = sorted(os.listdir(target.folder))
    for name in ('MODEL.json', 'manifest.json', 'report.html', 'run.log',
                 'profile.txt', 'gauges'):
        check(f'the folder holds {name}', name in got, str(got))
    check('the controller kept the stage manifest',
          list(ctrl._folders) == [target.folder]
          and ctrl._folders[target.folder]['model'] == 'CTRL')
    check('no dialog for a clean native run', shown == [], str(shown))
    ctrl._dispatch(ctrl.worker, ('folder', target.folder, {}, 'kept: why'))
    check('a kept-scratch notice is shown through show_error',
          shown == [('Model folder', 'kept: why')], str(shown))


def blastlab(cwd, *args, stdin=''):
    """`python -m blastlab *args` in `cwd`: (exit code, stdout, stderr)."""
    import subprocess
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONPATH'] = (os.path.abspath(os.path.join(HERE, '..', '..'))
                         + os.pathsep + env.get('PYTHONPATH', ''))
    p = subprocess.run([sys.executable, '-m', 'blastlab', *args], cwd=cwd,
                       env=env, capture_output=True, input=stdin.encode(),
                       timeout=600)
    return (p.returncode, p.stdout.decode('utf-8', 'replace'),
            p.stderr.decode('utf-8', 'replace'))


def part_b():
    """Step 8: the entries that produce output refuse to start without
    --runs-dir and --model; the ones that do not, still work."""
    tmp = tempfile.mkdtemp(prefix='blastlab_preflight_cli_')
    try:
        code, out, _err = blastlab(tmp, '--hd13-new', 't.json')
        check('--hd13-new needs neither argument',
              code == 0 and os.path.isfile(os.path.join(tmp, 't.json')),
              f'rc={code} {out.strip()[-80:]}')
        for args in (('--cli', '1d'), ('--cli', '2d', '--solver',
                                       'blastfoam'),
                     ('--hd13', 't.json'), ('--hd13-wall-export', 't.json'),
                     ('--hd13', 't.json', '--runs-dir', tmp),
                     ('--cli', '3d', '--model', 'M')):
            code, _out, err = blastlab(tmp, *args)
            check(f'{" ".join(args)}: exit 2 naming --runs-dir',
                  code == 2 and '--runs-dir' in err and 'usage:' in err,
                  f'rc={code} {err.strip().splitlines()[-1][:120]}')
        check('and nothing was written by any of them',
              sorted(os.listdir(tmp)) == ['t.json'], str(os.listdir(tmp)))
        code, _out, err = blastlab(tmp, '--hd13', 't.json', '--report',
                                   'r.html')
        check('--report is gone (argparse refuses it)',
              code == 2 and '--report' in err, err.strip()[-120:])

        print('\nB2: the native --cli runs in the model folder (D14)')
        runs = os.path.join(tmp, 'runs')
        os.mkdir(runs)
        # legacy blast1d's prompts: charge, radius, cell size (a small,
        # quick domain), then every other one at its default
        code, out, err = blastlab(
            tmp, '--cli', '1d', '--runs-dir', 'runs', '--model', 'CLI1D',
            stdin='\n'.join(['0.5', '2', '0.01'] + [''] * 40) + '\n')
        folder = os.path.join(runs, 'CLI1D')
        got = sorted(os.listdir(folder)) if os.path.isdir(folder) else []
        check('the run finished', code == 0,
              f'rc={code} {(err or out).strip()[-200:]}')
        check('its files landed in the model folder, none in the cwd',
              'manifest.json' in got and '.blastlab-model' in got
              and sorted(os.listdir(tmp)) == ['runs', 't.json']
              and len(got) > 2, str(got))
        if 'manifest.json' in got:
            with open(os.path.join(folder, 'manifest.json'),
                      encoding='utf-8') as f:
                m = json.load(f)
            names = [x['name'] for x in m['missing']]
            check('the manifest lists what it wrote and what the prompt '
                  'flow does not write',
                  m['model'] == 'CLI1D' and m['dim'] == 1
                  and m['outputs'] and 'report' in names
                  and 'figures' in names and m['case_file'] is None,
                  f"{[o['path'] for o in m['outputs']]} missing={names}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print('A: the Qt pre-flight')
    part_a()
    print('\nA8: the controller writes the model folder')
    part_a_controller()
    print('\nB: the command line')
    part_b()
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        return 1
    print(f'RUN PREFLIGHT: PASS ({len(RAN)} checks)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
