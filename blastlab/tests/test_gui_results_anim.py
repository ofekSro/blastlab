"""ResultsPanel animation replay: B3 regression check. A fake 3D result
with a non-default `slice_axis` must drive _setup_anim/_show_frame
without error, using the recorded slice's own axes/mask (mirroring
output/animation.py) rather than the old hardcoded x-z plane. Headless
(Agg backend, hidden Tk root) - needs customtkinter but no WSL, no
solver run."""
import os, sys
import numpy as np

os.environ.setdefault('MPLBACKEND', 'Agg')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

FAIL = []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def fake_3d_result(slice_axis, n_frames=3):
    """A minimal 3D Result whose meta shape matches what solver3d.py /
    foam backend.py actually emit (see solver3d.py's `meta = dict(...)`
    at the end of _run_blast_3d)."""
    from blastlab.solvers.hooks import Result
    from blastlab.core.grid import make_grid

    Lx, Ly, Lz, dx = 1.2, 1.0, 0.8, 0.2
    grid = make_grid(Lx, Ly, Lz, dx)
    x_c, y_c, z_c = grid['x_c'], grid['y_c'], grid['z_c']
    nx, ny, nz = len(x_c), len(y_c), len(z_c)
    solid = np.zeros((nx, ny, nz), dtype=bool)
    ax_i = 'xyz'.index(slice_axis)
    s0 = (nx, ny, nz)[ax_i] // 2
    slab_shape = tuple(n for a, n in enumerate((nx, ny, nz)) if a != ax_i)

    times = np.linspace(0.0, 1e-3, n_frames)
    pressures = [np.full(slab_shape, 1e5 + 1e3 * k, dtype=np.float32)
                for k in range(n_frames)]

    meta = dict(x_c=x_c, y_c=y_c, z_c=z_c,
               x_face=grid['x_face'], y_face=grid['y_face'],
               z_face=grid['z_face'], j0=ny // 2, k0=nz // 2,
               slice_axis=slice_axis, s0=s0,
               solid=solid, Lx=Lx, Ly=Ly, Lz=Lz, dx=dx,
               eos='idealGas', bcs={}, obstacles=[],
               charge=1.0, charge_center=(Lx / 2, Ly / 2, Lz / 2),
               r_exp=0.1, r_src=0.1, from_profile=None,
               frames=dict(times=times, pressures=pressures))
    gauges = dict(times=np.array([]), points=[], pressures=[])
    return Result({}, gauges, meta, 'end time reached', False)


def main():
    import tkinter as tk
    import customtkinter as ctk
    from blastlab.gui.results_panel import ResultsPanel

    root = ctk.CTk()
    root.withdraw()
    panel = ResultsPanel(root)

    for slice_axis, expect_shape in (('x', 'y-z'), ('y', 'x-z'),
                                     ('z', 'x-y')):
        res = fake_3d_result(slice_axis)
        try:
            # add_result -> _refresh -> _setup_anim (exercises the real
            # selection flow, not just a direct call)
            panel.add_result(f'3D ({slice_axis} slice)', 3, res)
            panel._show_frame(0)
            panel._show_frame(len(res.meta['frames']['pressures']) - 1)
            ok = True
            detail = ''
        except Exception as exc:
            ok = False
            detail = f'{type(exc).__name__}: {exc}'
        check(f"slice_axis='{slice_axis}' ({expect_shape} plane) replays "
              f"without error", ok, detail)
        if not ok:
            continue

        want_shape = res.meta['frames']['pressures'][0].shape
        check(f"slice_axis='{slice_axis}': solid mask matches frame shape",
              panel._anim_solid.shape == want_shape,
              f"solid {panel._anim_solid.shape} vs frame {want_shape}")

    root.destroy()

    print("\n" + "=" * 50)
    if FAIL:
        print(f"FAILED: {len(FAIL)} check(s): {FAIL}")
        sys.exit(1)
    print("All GUI results-animation checks passed.")


if __name__ == '__main__':
    main()
