"""GUI QA 2026-09-27 F2: the Qt Results tab after an OUT-2 VTK export.

A blastFoam run that wrote `<MODEL>\\vtk\\` (with its manifest.json) and
released its WSL scratch used to show a greyed VTK button saying "there
is nothing left to write as VTK". Now the button is live, its tooltip
says where the files were written and how many, and pressing it opens
that folder instead of converting anything. Checks, on the REAL
`ui.results_panel.ResultsPanel`, offscreen:

  W1  services.exports.run_vtk / vtk_tip / can on a fake model folder;
  W2  the Qt button: enabled, the tooltip names the folder and the count;
  W3  pressing it opens the folder (os.startfile patched) and writes
      nothing; no dialog;
  W4  a released run WITHOUT vtk\\ keeps the old greyed SCRATCH_RELEASED
      text, and a result with a live case dir keeps the export help.

Headless: QT_QPA_PLATFORM=offscreen, a private settings file, a fake
viewer link. No WSL, no solver.
Run:  cd blastlab/tests && python test_ui_results_vtk_folder.py
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
sys.path.insert(0, HERE)
os.environ.setdefault('MPLBACKEND', 'Agg')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('BLASTLAB_SETTINGS',
                      os.path.join(tempfile.mkdtemp(prefix='blastlab_uv_'),
                                   'settings.json'))

from blastlab.ui.testing import ensure_qapp, pump               # noqa: E402

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def model_folder(root, name, with_vtk):
    """A model folder like a released OUT-2 run leaves: vtk\\manifest.json,
    one series and two .vtk files (4 files in all) when `with_vtk`."""
    from blastlab.output import vtk_series as vs
    folder = os.path.join(root, name)
    os.makedirs(folder)
    if with_vtk:
        vdir = os.path.join(folder, 'vtk')
        vol = os.path.join(vdir, 'volumes')
        os.makedirs(vol)
        for t in ('0.0001', '0.0002'):
            with open(os.path.join(vol, f't_{t}.vtk'), 'w',
                      encoding='utf-8') as f:
                f.write('# vtk DataFile Version 2.0\n')
        vs.write_series(vol, 'volumes', [('t_0.0001.vtk', 1e-4),
                                         ('t_0.0002.vtk', 2e-4)])
        vs.write_vtk_manifest(vdir, dict(families={'volumes': dict(
            count=2, times=[1e-4, 2e-4], series='volumes/volumes.vtk.series')}))
    return folder


def released(res, folder, case_dir=None):
    """`res` as a blastFoam run whose scratch was released into `folder`."""
    res.meta.update(solver='blastfoam', model_dir=folder,
                    scratch_released=case_dir is None,
                    case_dir=case_dir or os.path.join(folder, 'gone'))
    return res


def main():
    ensure_qapp()
    from test_gui_results_fields import fake_3d
    from test_ui_view3d_host import FakeLink
    from blastlab.services import exports as svc
    from blastlab.ui import dialogs
    from blastlab.ui.results_panel import ResultsPanel

    tmp = tempfile.mkdtemp(prefix='blastlab_uv_runs_')
    with_vtk = model_folder(tmp, 'WITH_VTK', True)
    without = model_folder(tmp, 'NO_VTK', False)
    live_case = os.path.join(tmp, 'live_case')
    os.makedirs(live_case)

    print('\nW1: services.exports')
    ent = type('E', (), {})()
    ent.result, ent.dim = released(fake_3d(), with_vtk), 3
    found = svc.run_vtk(ent)
    check('run_vtk finds <MODEL>\\vtk\\ and counts its files',
          found == (os.path.join(with_vtk, 'vtk'), 4), str(found))
    check('so the VTK export is offered', svc.can('vtk', ent))
    tip = svc.vtk_tip(ent)
    check('the tip says written during the run, where, how many',
          tip.startswith('Written during the run: ')
          and os.path.join(with_vtk, 'vtk') in tip and '4 files' in tip
          and 'vtk\\manifest.json' in tip, tip)
    ent2 = type('E', (), {})()
    ent2.result, ent2.dim = released(fake_3d(), without), 3
    check('no vtk\\ -> no folder, no offer', svc.run_vtk(ent2) is None
          and not svc.can('vtk', ent2) and svc.vtk_tip(ent2) == '')

    print('\nW2: the Qt button after an OUT-2 run')
    log = []
    p = ResultsPanel(viewer_link=FakeLink(), log_fn=log.append)
    p.set_solver_mode('blastfoam')
    p.resize(1280, 840)
    p.show()
    pump(30)
    p.add_result('with vtk', 3, released(fake_3d(), with_vtk))
    pump(30)
    btn = p._export_btns['vtk']
    check('the VTK button is enabled', btn.isEnabled())
    check('its tooltip points at the vtk\\ folder, not "nothing left"',
          btn.toolTip().startswith('Written during the run: ')
          and '4 files' in btn.toolTip()
          and 'nothing left' not in btn.toolTip(), btn.toolTip())

    print('\nW3: pressing it opens the folder and writes nothing')
    opened, asked = [], []
    real_open, real_pick = svc._open, dialogs.pick_dir
    svc._open = lambda path, log: opened.append(path)
    dialogs.pick_dir = lambda *a, **k: asked.append(a) or ''
    before = sorted(os.listdir(with_vtk))
    try:
        got = p.export('vtk', threaded=False)
    finally:
        svc._open, dialogs.pick_dir = real_open, real_pick
    check('the folder is opened', opened == [os.path.join(with_vtk, 'vtk')],
          str(opened))
    check('no export ran and nothing was written',
          got == '' and sorted(os.listdir(with_vtk)) == before and not asked)
    check('the log says where the files are',
          any('written during the run' in s and '4 files' in s for s in log),
          str(log[-2:]))

    print('\nW4: the other cases keep their texts')
    p.add_result('no vtk', 3, released(fake_3d(), without))
    pump(30)
    check('released without vtk\\: greyed, SCRATCH_RELEASED',
          not btn.isEnabled() and btn.toolTip() == svc.SCRATCH_RELEASED,
          btn.toolTip())
    p.add_result('live', 3, released(fake_3d(), with_vtk, case_dir=live_case))
    pump(30)
    from blastlab.ui.results_panel import EXPORT_HELP
    check('a live case dir keeps the converter and its help text',
          btn.isEnabled() and btn.toolTip() == EXPORT_HELP.get('vtk', ''),
          btn.toolTip())

    p.shutdown()
    p.close()
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} check(s): {FAIL}')
        sys.exit(1)
    print('UI RESULTS VTK FOLDER: PASS')


if __name__ == '__main__':
    main()
