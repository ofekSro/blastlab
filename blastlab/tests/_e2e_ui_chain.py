"""A real 1D -> 2D native chain through the real Qt window.

The Chain tab's own suite proves the refusals and the wiring without
running anything. This one actually runs the thing: two stages, a
profile handed from the first to the second on disk, both results
arriving in the Results tab, and the case JSONs left behind so the chain
can be reproduced.

The reproducibility claim is checked, not assumed: `adaptive_write` must
be False both on the case that ran AND in the JSON on disk.

No WSL. Offscreen by default; `--window` shows it.

Run:  cd blastlab/tests && python _e2e_ui_chain.py
"""
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
os.environ.setdefault('MPLBACKEND', 'Agg')
os.environ.setdefault('BLASTLAB_SETTINGS', os.path.join(
    tempfile.mkdtemp(prefix='blastlab_ui_chain_'), 'settings.json'))

FAIL = []
RAN = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    RAN.append(name)
    if not ok:
        FAIL.append(name)


def main():
    from blastlab.ui.testing import ensure_qapp, pump, use_model
    ensure_qapp(offscreen='--window' not in sys.argv)
    from blastlab.core.case import Case1D, Case2D
    from blastlab.ui.app import MainWindow

    win = MainWindow()
    # OUT-1: the chain writes into the Run tab's model folder
    ws = use_model(win, 'CHAIN')
    win.show()
    pump(200)
    ch = win.chain
    ch.use[3].setChecked(False)
    ch.set_stage_case(1, Case1D(radius_m=1.5, charge_kg=1.0,
                                cell_size_m=0.004, n_snapshots=2,
                                gauge_radii=[], gauge_file=None))
    ch.set_stage_case(2, Case2D(geometry='axisymmetric', Lx=1.5, Ly=1.5,
                                cell_size_m=0.05, charge=1.0,
                                center=(0.0, 0.75), n_snapshots=2,
                                gauges=[], gauge_file=None,
                                anim_file=None, record_frames=0))
    pump(200)

    print('\nX1: the chain is accepted')
    refusals = []
    ch.error_sink = lambda title, lines: refusals.append(list(lines))
    check('1 -> 2 runs', ch.run() is True, str(refusals))
    check('nothing was refused', not refusals, str(refusals))
    check('and the Run tab came forward', win.current_tab() == 'run',
          win.current_tab())

    print('\nX2: it finishes')
    t0 = time.time()
    for _ in range(6000):                      # <= 10 min
        pump(100)
        if not win.ctrl.running:
            break
    print(f'    chain took {time.time() - t0:.1f} s')
    log = win.run_panel.log_text()
    check('the run finished', '[run finished]' in log)
    check('with no ui error while draining',
          '[ui error handling' not in log)
    check('both stage banners reached the log',
          '1D' in log and '2D' in log)

    print('\nX3: the profile really was handed over on disk')
    p1 = os.path.join(ws, 'handoff_1d_to_2d.txt')     # at the model root
    check('the 1D stage wrote its profile',
          os.path.exists(p1) and os.path.getsize(p1) > 100,
          str(os.path.getsize(p1) if os.path.exists(p1) else 0))
    check('and the 2D stage was told to read it',
          '2D' in log and ('profile' in log.lower()), '')

    print('\nX4: both results arrived in the Results tab')
    entries = win.results.entries()
    check('two entries', len(entries) == 2,
          str([e.label for e in entries]))
    check('one per dimension', sorted(e.dim for e in entries) == [1, 2],
          str([e.dim for e in entries]))
    win._show('results')
    pump(80)
    for ent in entries:
        win.results.sel.setCurrentIndex(entries.index(ent))
        pump(80)
        page = win.results.fields.page()
        check(f'{ent.dim}D draws in Fields',
              page in ('image', 'figure'), page)

    print('\nX5: the chain can be reproduced from what it left behind')
    # OUT-1: each stage's MODEL.json in <MODEL>\1d, 2d (was stageN_case.json)
    saved = [os.path.join(d, 'MODEL.json') for d in ('1d', '2d')
             if os.path.isfile(os.path.join(ws, d, 'MODEL.json'))]
    check('a case JSON per stage',
          saved == [os.path.join('1d', 'MODEL.json'),
                    os.path.join('2d', 'MODEL.json')], str(saved))
    for name in saved:
        with open(os.path.join(ws, name), encoding='utf-8') as f:
            d = json.load(f)
        check(f'{name} pins the write schedule',
              d.get('adaptive_write') is False,
              str(d.get('adaptive_write')))
    with open(os.path.join(ws, '2d', 'MODEL.json'),
              encoding='utf-8') as f:
        d2 = json.load(f)
    check('and stage 2 records where its profile came from',
          d2.get('profile_file_in') == '../handoff_1d_to_2d.txt'
          and d2.get('init_mode') == 'profile1d',
          f"{d2.get('init_mode')} {d2.get('profile_file_in')}")

    win.close()
    pump(200)
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        sys.exit(1)
    print(f'E2E UI CHAIN: PASS ({len(RAN)} checks)')


if __name__ == '__main__':
    main()
