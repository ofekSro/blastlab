"""G15Q-5a (batch 2026-10-12 gui-final D4): a Stop during blockMesh
leaves the bar empty and the percent tile at `0 %`.

Harness F07's case (axisymmetric 5 x 5 m at 4 mm, 1.56 M cells, so
blockMesh takes long enough to be stopped in) on blastFoam in WSL: Run,
Stop as soon as the `blockMesh` stage line is in the log, wait for the
worker to end, then print the bar, the percent tile and the time line.
The run is stopped before its solve starts, so no progress ever arrived:
`0 %`, bar 0 and `Stopped after …` are the pass.

WSL, offscreen, throwaway settings and runs folder (outside OneDrive).
Deletes nothing: the stopped case stays in /root/blastlab_runs like any
stopped run. Before running: `wsl -d Ubuntu -- pgrep -a blastFoam` empty.

    cd blastlab/tests && python -u _e2e_ui_stop_in_mesh.py
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass


def main():
    from blastlab.ui.testing import ensure_qapp, pump, use_model
    ensure_qapp()
    from blastlab.core.case import Case2D
    from blastlab.solvers.foam import env
    from blastlab.ui import dialogs
    from blastlab.ui.app import MainWindow
    env.hardware(probe=True)        # the real VM, not the 4 GB guess

    errors = []
    dialogs.show_error = lambda *a, **k: errors.append(a)
    win = MainWindow()
    use_model(win, name='D4_stop_in_mesh')
    win.show()
    pump(300)
    win.setup.set_case(Case2D(geometry='axisymmetric', Lx=5.0, Ly=5.0,
                              cell_size_m=0.004, charge=8.0,
                              center=(0.0, 2.5), n_snapshots=2,
                              record_frames=0, solver='blastfoam',
                              material='TNT'))
    win._schedule_validate()
    pump(1500)
    win._show('run')
    rp = win.run_panel
    # where a 1.0 could come from: a progress post, or mark_complete
    seen = dict(progress=0, complete=0)
    real_progress, real_complete = rp.on_progress, rp.mark_complete

    def on_progress(p):
        seen['progress'] += 1
        real_progress(p)

    def mark_complete():
        seen['complete'] += 1
        real_complete()
    rp.on_progress, rp.mark_complete = on_progress, mark_complete
    rp.run_btn.click()
    t0 = time.monotonic()
    while 'blockMesh' not in rp.log_text():
        pump(100)
        if time.monotonic() - t0 > 300:
            print('FAIL: no blockMesh line in 300 s')
            print(rp.log_text()[-2000:])
            return 1
    print(f'blockMesh line after {time.monotonic() - t0:.1f} s; Stop')
    rp.stop_btn.click()
    t1 = time.monotonic()
    while win.ctrl.running and time.monotonic() - t1 < 150:
        pump(100)
    pump(1000)
    print(f'the run ended {time.monotonic() - t1:.1f} s after Stop')
    pct, bar, line = rp.pct_text(), rp.progress.value(), rp.time_text()
    print(f'percent tile: {pct!r}')
    print(f'bar value   : {bar} of {rp.progress.maximum()}')
    print(f'time line   : {line!r}')
    print(f'progress posts: {seen["progress"]}, '
          f'mark_complete calls: {seen["complete"]}')
    print('log tail    : '
          + ' / '.join(rp.log_text().strip().splitlines()[-3:]))
    ok = (not win.ctrl.running and pct == '0 %' and bar == 0
          and line.startswith('Stopped after') and not errors)
    win.close()
    pump(200)
    print('D4 STOP IN MESH: ' + ('PASS' if ok else
                                 f'FAIL (errors: {errors[:1]})'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
