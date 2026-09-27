"""OUT-2, owner decision P11: the readers of a finished run warn when its
VTK export deleted written times after converting them - no WSL.

docs/batches/2026-09-27-out-2-vtk-output.md, "Owner decisions on the
parked list" (P11). postmortem load (`--load-foam-run` and the Results
tab), the run browser's resume (`backend.resume_run`) and the manual VTK
button (`export_vtk`) read only the writes left in WSL. Each says so in
ONE line, with the count and "see <MODEL>\\vtk (vtk\\manifest.json)".

  R1  output.vtk_series.find_vtk_dir: a model's vtk\\ is found by the
      `scratch` its manifest names (top level and chain stage); another
      run, no runs folder, or a manifest without `scratch` give None;
  R2  deleted_warning: count + the folder; None when nothing was deleted;
  R3  VtkExport.state() records `scratch`;
  R4  postmortem.load_run logs the line once, and puts it on the Result;
      a run without a deleting export logs nothing;
  R5  backend.resume_run (no model folder on the hooks) logs the line
      once, before it touches the controlDict;
  R6  export_vtk logs it (vtk_dir given, or found by the scratch).

Run:  cd blastlab/tests && python test_vtk_readers.py
"""
import os
import shutil
import sys
import tempfile
from types import SimpleNamespace

os.environ.setdefault('MPLBACKEND', 'Agg')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core import settings                              # noqa: E402
from blastlab.output import vtk_series as vs                    # noqa: E402
from blastlab.solvers.foam import env                           # noqa: E402
from blastlab.solvers.foam import vtk_export as vx               # noqa: E402

FAILS = []
POSIX = env.RUNS_ROOT + '/20260927-090000_2d_p4242-00'
OTHER = env.RUNS_ROOT + '/20260927-090000_2d_p4243-00'


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAILS.append(name)


def model(runs, rel, scratch, deleted):
    """A model folder's vtk\\manifest.json under `runs`."""
    vdir = os.path.join(runs, *rel.split('/'), 'vtk')
    state = dict(deleted_in_wsl=list(deleted))
    if scratch is not None:
        state['scratch'] = scratch
    vs.write_vtk_manifest(vdir, state)
    return vdir


class _Settings:
    """settings.load() -> {'runs_dir': runs} while in the block."""

    def __init__(self, runs):
        self.runs = runs

    def __enter__(self):
        self.real = settings.load
        settings.load = lambda *a, **k: {'runs_dir': self.runs,
                                         'auto_cleanup': False}

    def __exit__(self, *_a):
        settings.load = self.real


def warn_lines(lines):
    return [ln for ln in lines if 'deleted in WSL after their VTK' in ln]


def test_find_and_warn():
    print('\nR1-R3: finding the vtk\\ folder, the line, the manifest key')
    runs = tempfile.mkdtemp(prefix='blastlab_vr_runs_')
    try:
        check('no runs folder -> None',
              vs.find_vtk_dir(POSIX, '') is None
              and vs.find_vtk_dir(POSIX, os.path.join(runs, 'nope')) is None)
        old = model(runs, 'OLD', None, ['0.001'])
        check('a manifest without `scratch` is not matched',
              vs.find_vtk_dir(POSIX, runs) is None)
        top = model(runs, 'TOP', POSIX, ['0.001', '0.002', '0.003'])
        chain = model(runs, 'CHAIN/2d', OTHER, [])
        check('the top-level model is found by its scratch',
              vs.find_vtk_dir(POSIX, runs) == top,
              str(vs.find_vtk_dir(POSIX, runs)))
        check('   a trailing / on the run dir does not matter',
              vs.find_vtk_dir(POSIX + '/', runs) == top)
        check('a chain stage (<MODEL>\\<stage>\\vtk) is found too',
              vs.find_vtk_dir(OTHER, runs) == chain)
        line = vs.deleted_warning(top)
        check('the line: [warn], the count, and see <MODEL>\\vtk',
              line is not None and '[warn]' in line
              and ' 3 written time(s)' in line and top in line
              and 'vtk\\manifest.json' in line and '\n' not in line,
              str(line))
        check('no line when nothing was deleted',
              vs.deleted_warning(chain) is None)
        check('no line without a folder or a manifest',
              vs.deleted_warning(None) is None
              and vs.deleted_warning(os.path.join(runs, 'x')) is None)
        with _Settings(runs):
            check('deleted_note finds it through the settings runs folder',
                  vx.deleted_note(POSIX) == line)
            check('   and from the UNC form of the run dir',
                  vx.deleted_note(env.unc(POSIX)) == line)
            check('   an explicit vtk_dir wins',
                  vx.deleted_note(OTHER, top) == line)
            check('   another run: None', vx.deleted_note(
                env.RUNS_ROOT + '/20260101-000000_3d_p1-00') is None)
        assert os.path.isdir(old)
        # R3: the export records its scratch
        vdir = os.path.join(runs, 'R3', 'vtk')
        spec = SimpleNamespace(dim=3, case_posix=POSIX, vtk_volumes=dict(
            on=True, mode='step', value=10, fields=['p']),
            vtk_surfaces=None, decomposed=False, n_procs=1, start_dir='0')
        ex = vx.VtkExport(spec, SimpleNamespace(vtk_dir=vdir,
                                                log=lambda *_a: None), ('p',))
        check('VtkExport.state() records the scratch',
              ex.state().get('scratch') == POSIX, str(ex.state()))
    finally:
        shutil.rmtree(runs, ignore_errors=True)


def _run_tree():
    """A finished serial 2D run on the local disk (test_foam_postmortem_
    decomposed's fake AMR case) and a runs folder."""
    from test_foam_postmortem_decomposed import build_case
    root = tempfile.mkdtemp(prefix='blastlab_vr_case_')
    build_case(root, n_procs=1)
    return root


def test_postmortem():
    print('\nR4: postmortem.load_run')
    from blastlab.solvers.foam import postmortem
    from test_foam_amr_ingest import Log
    root, runs = _run_tree(), tempfile.mkdtemp(prefix='blastlab_vr_runs_')
    real = postmortem._paths
    postmortem._paths = lambda _d: (POSIX, root)
    try:
        with _Settings(runs):
            log = Log()
            res = postmortem.load_run(root, log)
            check('no deleting export: no line, no note on the Result',
                  not warn_lines(log.lines)
                  and 'vtk_deleted_note' not in res.meta, str(log.lines))
            vdir = model(runs, 'PM', POSIX, ['1e-05', '2e-05'])
            log = Log()
            res = postmortem.load_run(root, log)
            said = warn_lines(log.lines)
            check('after deletion: ONE line, the count and the folder',
                  len(said) == 1 and ' 2 written time(s)' in said[0]
                  and vdir in said[0], str(log.lines))
            check('   and the same line on the Result (the Results tab '
                  'logs it)', res.meta.get('vtk_deleted_note') == said[0])
    finally:
        postmortem._paths = real
        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(runs, ignore_errors=True)


def test_resume():
    print('\nR5: backend.resume_run from the run browser (no model folder)')
    from blastlab.solvers.foam import backend
    from blastlab.solvers.hooks import RunHooks
    root, runs = _run_tree(), tempfile.mkdtemp(prefix='blastlab_vr_runs_')

    class Stop(Exception):
        pass

    class Hooks(RunHooks):
        def __init__(self):
            super().__init__()
            self.lines = []

        def log(self, msg):
            self.lines.append(msg)

    def stop(*_a, **_k):
        raise Stop()

    saved = (backend.env.case_paths, backend.env.run_is_alive,
             backend.runner.rewrite_control_entry)
    backend.env.case_paths = lambda _d: (POSIX, root)
    backend.env.run_is_alive = lambda _p: False
    backend.runner.rewrite_control_entry = stop
    try:
        with _Settings(runs):
            vdir = model(runs, 'RES', POSIX, ['1e-05'])
            h = Hooks()
            try:
                backend.resume_run(POSIX, h)
                reached = False
            except Stop:
                reached = True
            said = warn_lines(h.lines)
            check('the line is logged once, before the controlDict is '
                  'touched', reached and len(said) == 1
                  and ' 1 written time(s)' in said[0] and vdir in said[0],
                  str(h.lines))
    finally:
        (backend.env.case_paths, backend.env.run_is_alive,
         backend.runner.rewrite_control_entry) = saved
        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(runs, ignore_errors=True)


def test_export_button():
    print('\nR6: the manual VTK button (export_vtk)')
    from blastlab.solvers.foam import export_vtk as ev
    root, runs = _run_tree(), tempfile.mkdtemp(prefix='blastlab_vr_runs_')
    saved = (ev.env.case_paths, ev.runner.run_stage)
    ev.env.case_paths = lambda _d: (POSIX, root)
    ev.runner.run_stage = lambda *_a, **_k: None
    try:
        vdir = model(runs, 'BTN', POSIX, ['1e-05', '2e-05', '3e-05'])
        lines = []
        ev.export_vtk(root, log=lines.append, vtk_dir=vdir)
        said = warn_lines(lines)
        check('with the Result\'s vtk_dir: ONE line, count and folder',
              len(said) == 1 and ' 3 written time(s)' in said[0]
              and vdir in said[0], str(lines))
        with _Settings(runs):
            lines = []
            ev.export_vtk(root, log=lines.append)
            check('without it: found by the scratch, ONE line',
                  len(warn_lines(lines)) == 1, str(lines))
        with _Settings(''):
            lines = []
            ev.export_vtk(root, log=lines.append)
            check('no model to be found: no line', not warn_lines(lines),
                  str(lines))
    finally:
        ev.env.case_paths, ev.runner.run_stage = saved
        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(runs, ignore_errors=True)


def root_model(runs, rel, scratch, mode, n):
    """A model stage's root manifest.json (OUT-3 `wsl_fields`)."""
    import json
    folder = os.path.join(runs, *rel.split('/'))
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, 'manifest.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(dict(model=rel, wsl_scratch=dict(posix=scratch),
                       vtk=None, wsl_fields=dict(
                           mode=mode, deleted=n,
                           first='1e-05' if n else None,
                           last='3e-05' if n else None)), f)
    return path


def fields_lines(lines):
    return [ln for ln in lines if 'deleted in WSL during the run' in ln]


def test_fields_purge():
    print('\nR7: OUT-3 - a run with no VTK that kept only its newest writes')
    root, runs = _run_tree(), tempfile.mkdtemp(prefix='blastlab_vr_runs_')
    from blastlab.solvers.foam import export_vtk as ev
    from blastlab.solvers.foam import postmortem
    saved = (ev.env.case_paths, ev.runner.run_stage, postmortem._paths)
    ev.env.case_paths = lambda _d: (POSIX, root)
    ev.runner.run_stage = lambda *_a, **_k: None
    postmortem._paths = lambda _d: (POSIX, root)
    try:
        with _Settings(runs):
            keep = root_model(runs, 'KEEP', POSIX, 'keep_all', 0)
            check('keep_all: no note', vx.deleted_note(POSIX) is None)
            os.remove(keep)
            path = root_model(runs, 'CHAIN/2d', POSIX, 'newest', 3)
            note = vx.deleted_note(POSIX)
            check('newest: the line, the count, the root manifest',
                  note is not None and '[warn]' in note
                  and ' 3 older written time(s)' in note and path in note
                  and '\n' not in note, str(note))
            check('   another run: None',
                  vs.find_model_manifest(OTHER, runs) is None)
            lines = []
            ev.export_vtk(root, log=lines.append)
            check('the VTK button logs it once',
                  len(fields_lines(lines)) == 1, str(lines))
            from test_foam_amr_ingest import Log
            log = Log()
            res = postmortem.load_run(root, log)
            check('postmortem logs it once and puts it on the Result',
                  len(fields_lines(log.lines)) == 1
                  and res.meta.get('vtk_deleted_note') == note,
                  str(log.lines))
        # the model's vtk\ given (the Results tab of a VTK run with no
        # VTK deletion): the stage's root manifest still answers
        vdir = model(runs, 'CHAIN/2d', POSIX, [])
        lines = []
        ev.export_vtk(root, log=lines.append, vtk_dir=vdir)
        check('   with vtk_dir: the stage root manifest answers',
              len(fields_lines(lines)) == 1, str(lines))
        # the in-stage W3 auto-resume: hooks.fields_deleted
        lines = []
        check('note_resume from the hooks record',
              vx.note_resume(None, ['0', '3e-05'], lines.append,
                             deleted={'1e-05', '2e-05'})
              and len(lines) == 1 and 'resuming after 2 older' in lines[0],
              str(lines))
        check('   nothing gone: no line',
              not vx.note_resume(None, ['1e-05'], lines.append,
                                 deleted={'1e-05'}) and len(lines) == 1)
    finally:
        (ev.env.case_paths, ev.runner.run_stage, postmortem._paths) = saved
        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(runs, ignore_errors=True)


if __name__ == '__main__':
    test_find_and_warn()
    test_postmortem()
    test_resume()
    test_export_button()
    test_fields_purge()
    print()
    print('VTK READERS: ' + ('PASS' if not FAILS else
                             f'FAIL ({len(FAILS)}): ' + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)
