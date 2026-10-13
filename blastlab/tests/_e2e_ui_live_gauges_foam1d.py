"""D6 (owner 2026-10-13, batch 2026-10-12 gui-final): a short real 1D
blastFoam run shows live gauge samples BEFORE it ends.

A 1 kg charge in a 5 m sector at 10 mm (500 cells), four gauges, on WSL.
The Run screen is shown, so the live-gauge column collects (D60). Every
payload the column receives is recorded with its series length and
whether it is the finished Result's (`final`). Pass: at least two live
payloads of different lengths before the final one, and no
`[ui error handling 'gauges']` in the log.

WSL, offscreen, throwaway settings and runs folder (outside OneDrive).
Deletes nothing in /root/blastlab_runs. Before running:
`wsl -d Ubuntu -- pgrep -a blastFoam` empty.

    cd blastlab/tests && python -u _e2e_ui_live_gauges_foam1d.py
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

UI_ERR = "[ui error handling 'gauges']"


def main():
    from blastlab.ui.testing import ensure_qapp, pump, use_model
    ensure_qapp()
    from blastlab.core.case import Case1D
    from blastlab.solvers.foam import env
    from blastlab.ui import dialogs
    from blastlab.ui.app import MainWindow
    env.hardware(probe=True)

    errors = []
    dialogs.show_error = lambda *a, **k: errors.append(a)
    win = MainWindow()
    use_model(win, name='D6_live_gauges_foam1d')
    win.show()
    pump(300)
    win.setup.set_case(Case1D(radius_m=5.0, charge_kg=1.0,
                              cell_size_m=0.01,
                              gauge_radii=[1.0, 2.0, 3.0, 4.0],
                              gauge_file=None, n_snapshots=2,
                              solver='blastfoam', material='TNT'))
    win._schedule_validate()
    pump(1500)
    win._show('run')
    pump(200)
    rp = win.run_panel
    col = rp.gauge_col
    got = []                    # (s since Run, series length, final?)
    real_set = col.set_payload
    t0 = time.monotonic()

    def set_payload(payload, final=False):
        n = len(payload.get('times', ())) if payload else 0
        got.append((time.monotonic() - t0, n, bool(final)))
        real_set(payload, final=final)
    col.set_payload = set_payload
    print(f'collecting live gauges: {getattr(win.ctrl, "_live_gauges", None)}')
    rp.run_btn.click()
    while win.ctrl.running and time.monotonic() - t0 < 900:
        pump(100)
    pump(1000)
    wall = time.monotonic() - t0
    live = [g for g in got if not g[2]]
    final = [g for g in got if g[2]]
    lengths = sorted({n for _t, n, _f in live if n > 0})
    log = rp.log_text()
    print(f'the run took {wall:.1f} s; {len(live)} live payload(s), '
          f'{len(final)} final')
    shown = got if len(got) <= 12 else got[:6] + [None] + got[-6:]
    for g in shown:
        print('    ...' if g is None else
              f'    {g[0]:7.1f} s  {g[1]:6d} samples  '
              f'{"final" if g[2] else "live"}')
    end_t = final[0][0] if final else wall
    before = [g for g in live if g[0] < end_t and g[1] > 0]
    ok = (len({n for _t, n, _f in before}) >= 2 and bool(final)
          and UI_ERR not in log and not errors)
    print('log tail: ' + ' / '.join(log.strip().splitlines()[-3:]))
    print(f'distinct live lengths before the Result: {lengths[:6]}'
          f'{" ..." if len(lengths) > 6 else ""}')
    print(f'{UI_ERR} in the log: {UI_ERR in log}')
    win.close()
    pump(200)
    print('D6 FOAM 1D LIVE GAUGES: ' + ('PASS' if ok else
                                        f'FAIL (errors: {errors[:1]})'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
