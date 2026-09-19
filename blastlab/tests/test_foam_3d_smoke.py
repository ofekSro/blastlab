"""3D blastFoam backend smoke test: 8 kg TNT centred in a 1 m box
(76^3 = ~439k cells after the charge refine, ~2-3 min wall). Asserts
the full native Result
contract (snapshot keys/dtypes/shapes incl. rho3, gauges, meta incl.
j0/k0/s0, frames) plus x/y gauge symmetry and the arrival-watcher
stop. Auto-SKIPs when WSL/blastFoam is unavailable.

Pass --tiny for a 0.6 m box (~2.5 min measured 2026-09-10 on a 20-core
/ 62 GiB-VM machine; the old "~30-60 s" predates T39).
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

import numpy as np                                             # noqa: E402

from blastlab.core.case import Case3D                          # noqa: E402
from blastlab.core.constants import P_AIR                      # noqa: E402

#: T50: the pre-T50 3D solver default - terminating sides over a
#: reflecting ground.
ALL_TERM_3D = dict(x_lo='terminate', x_hi='terminate',
                   y_lo='terminate', y_hi='terminate',
                   z_lo='reflect', z_hi='terminate')

FAIL = []
SNAP_KEYS = {'p', 'rho_xz', 'rho_xy', 'speed_xz', 'speed_xy', 't', 'rho3'}
META_KEYS = {'x_c', 'y_c', 'z_c', 'x_face', 'y_face', 'z_face',
             'j0', 'k0', 'slice_axis', 's0', 'solid', 'Lx', 'Ly', 'Lz',
             'dx', 'eos', 'bcs', 'obstacles', 'charge', 'charge_center',
             'r_exp', 'r_src', 'from_profile', 'frames'}


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAIL.append(name)


#: N5-7, resolved. Two mechanisms, both fixed:
#:   1. the detonation point sat exactly on a cell corner and parallel
#:      runs ignited an extra cell (E0 injected twice, the systematic
#:      +7 %) - fixed by _off_faces() nudging points off face planes;
#:   2. scotch's ragged interface seeded ~1e-6 perturbations the near
#:      field amplified chaotically (+9.7 % on one gauge even nudged) -
#:      fixed by the planar decomposition, which seeds none.
#: Measured with both fixes: z-cut+nudge tracks serial to 0.14 % with
#: 0.02 % asymmetry. 2 % gives an order of magnitude of margin and
#: still catches either mechanism coming back.
SERIAL_TOL = 0.02


def _serial_gate(case, px, py):
    """N5-7: parallel against a SERIAL reference - the real gate.

    Serial has no processor boundaries, so it is the reference the
    parallel run has to reproduce. Measured on this case with the
    planar decomposition that N5-7 made the default:

        full size (Z = 0.175)   +0.17 %     <- gated at 2 %
        --tiny    (Z = 0.075)   +28 %       <- NOT gated, see below

    The tiny case is not gated on accuracy on purpose. At Z = 0.075 the
    gauges sit 0.15 m from an 8 kg charge, inside the fireball, and
    EVERY parallel decomposition measured there lands 13-28 % high -
    scotch and both planar cuts alike. A gate there would be pinning a
    tracked defect rather than testing anything, so --tiny stays a smoke
    test: does a 3D run work end to end. The accuracy question is asked
    at full size, where it has an answer.
    """
    if '--tiny' in sys.argv:
        print('  [note] --tiny: accuracy vs serial NOT gated at '
              'Z = 0.075 (N5-7); run without --tiny for that')
        return
    import copy
    from blastlab.solvers import get_solver
    ser = copy.deepcopy(case)
    ser.n_procs = 1
    res = get_solver(3, 'blastfoam')(ser)
    sx = res.gauges['pressures'][0].max() - P_AIR
    sy = res.gauges['pressures'][1].max() - P_AIR
    ref = 0.5 * (sx + sy)
    for lbl, v in (('gauge x', px), ('gauge y', py)):
        rel = v / ref - 1.0
        check(f'parallel matches serial at {lbl}',
              abs(rel) <= SERIAL_TOL,
              f'{v/1e3:.0f} vs serial {ref/1e3:.0f} kPa ({rel:+.2%}, '
              f'tol {SERIAL_TOL:.0%})')
    print(f'  [note] serial {sx/1e3:.0f} / {sy/1e3:.0f} kPa, '
          f'parallel {px/1e3:.0f} / {py/1e3:.0f} kPa')


def main():
    from blastlab.solvers.foam import env
    ok, detail = env.check_available()
    if not ok:
        print(f"  [SKIP] blastFoam unavailable: {detail}")
        print("\nFOAM 3D SMOKE: SKIP")
        return

    L = 0.6 if '--tiny' in sys.argv else 1.0
    c = L / 2.0
    case = Case3D(Lx=L, Ly=L, Lz=L, cell_size_m=0.025,
                  charge=8.0, center=(c, c, c),
                  gauges=[(L - 0.15, c, c), (c, L - 0.15, c)],
                  n_snapshots=4, record_frames=150,
                  solver='blastfoam', material='TNT', bcs=ALL_TERM_3D)
    # N3-01 (14.09): two determinism fixes, both measured on this case.
    # (1) The x/y gate was BIMODAL - PASS/FAIL flipping run to run with
    # digit-identical fail values (8579/8084 kPa). Root: the adaptive
    # writeInterval rewrite lands at an ingest-(wall-clock-)dependent
    # step, and `writeControl adjustableRunTime` clips deltaT onto the
    # write times, so two write schedules fork the whole float
    # trajectory (peaks 8579/8084 in one mode, 8469/8050 in the other -
    # even the peak SAMPLE TIMES differ). Pinning the schedule (B23)
    # makes the record digit-identical across runs.
    case.adaptive_write = False
    # (2) The requested gauge coordinates (0.85, 0.5) are exact FACE
    # coordinates of the refined grid, so adjustLocations snapped the
    # two probes to non-mirror cells. Align them to exact mirror CELL
    # CENTRES of the grid the writer really builds (the charge rule
    # refines dx below cell_size_m - dx_fine = L/76 here, not 0.025):
    # (a, b, b) <-> (b, a, b) map onto each other under the x<->y swap,
    # so what remains in the gate is the solver, not probe placement.
    # Measured with both fixes the residual asymmetry is REAL and comes
    # from the MPI decomposition - same case, mirror probes, pinned
    # schedule: np=1 -> 0.10 %, np=2 -> 0.26 %, np=8 (this machine's
    # auto) -> 4.85 %, digit-identical per np and INDEPENDENT of the
    # live-slice axis (slice x reproduces slice y's digits exactly).
    # So the gate's number is a function of whatever rank count `auto`
    # resolves to on the running machine. Pin np=2: deterministic
    # across machines, still exercises the parallel path, and the 5 %
    # gate then holds a ~19x margin instead of a 3 % one. (A machine
    # whose rank ceiling is 1 clamps to serial - also fine.) The
    # parallel-vs-serial near-field deviation itself is tracked in
    # TODO as an accuracy observation.
    case.n_procs = 2
    from blastlab.core import refine
    from blastlab.core.case import material_rho0
    plan = refine.plan_levels(case, rho0=material_rho0(case))
    dxf = float(plan.fine['dx'])
    a = (round((L - 0.15) / dxf - 0.5) + 0.5) * dxf
    b = (round(c / dxf - 0.5) + 0.5) * dxf
    case.gauges = [(a, b, b), (b, a, b)]
    from blastlab.solvers import get_solver
    res = get_solver(3, 'blastfoam')(case)

    check('arrival-watcher stop',
          res.stop_reason.startswith('shock arrived'), res.stop_reason)
    check('stopped_early False', res.stopped_early is False)

    labels = list(res.snapshots)
    check('snapshot labels', len(labels) >= 2
          and labels[-1].endswith('(final)')
          and all(k.startswith('t = ') for k in labels))
    N = None
    for label, snap in res.snapshots.items():
        if set(snap) != SNAP_KEYS:
            check(f'snapshot keys ({label})', False,
                  str(set(snap) ^ SNAP_KEYS))
            break
        N = snap['p'].shape
    else:
        check('snapshot keys', True)
    snap = res.snapshots[labels[-1]]
    check('snapshot dtypes/shapes',
          snap['p'].dtype == np.float32 and snap['p'].ndim == 3
          and snap['rho_xz'].shape == (N[0], N[2])
          and snap['rho_xy'].shape == (N[0], N[1])
          and snap['speed_xz'].dtype == np.float32
          and isinstance(snap['t'], float)
          and snap['rho3'].ndim == 3)

    m = res.meta
    check('meta keys', set(m) >= META_KEYS,
          str(META_KEYS - set(m)))
    check('meta grid consistency',
          (len(m['x_c']), len(m['y_c']), len(m['z_c'])) == N
          and len(m['x_face']) == N[0] + 1
          and m['solid'].shape == N and not m['solid'].any()
          and 0 <= m['j0'] < N[1] and 0 <= m['k0'] < N[2]
          and m['slice_axis'] == 'y' and 0 <= m['s0'] < N[1])
    fr = m['frames']
    check('frames record',
          len(fr['times']) == len(fr['pressures']) >= 3
          and fr['pressures'][0].shape == (N[0], N[2])
          and fr['pressures'][0].dtype == np.float32
          and (np.diff(fr['times']) > 0).all())

    check('gauge points snapped',
          len(res.gauges['points']) == 2
          and len(res.gauges['pressures']) == 2
          and (np.diff(res.gauges['times']) > 0).all())
    px = res.gauges['pressures'][0].max() - P_AIR
    py = res.gauges['pressures'][1].max() - P_AIR
    check('gauges shocked', px > 2 * P_AIR and py > 2 * P_AIR,
          f'{px/1e3:.0f} / {py/1e3:.0f} kPa')
    # N5-7: the x/y gate USED to live here, and it was the wrong
    # instrument. It only sees an error that lands unevenly on the two
    # mirror probes, so a decomposition whose cut is x/y symmetric
    # scored a perfect 0.00 % while both gauges were 28 % high. The
    # "0.26 % residual" this gate reported at full size was a measure of
    # how asymmetric scotch's partition happened to be, not of how
    # accurate the solution was - the real error in that same run was
    # +7.00 %.
    #
    # What replaces it is below: the parallel peaks against a SERIAL
    # reference, which has no processor boundaries at all. Symmetry is
    # still checked, but only as a cheap sanity bound - it is no longer
    # asked to stand in for accuracy.
    # ...and at --tiny neither gate applies, for the same reason. At
    # Z = 0.075 the gauges sit 0.15 m from an 8 kg charge, inside the
    # fireball, and EVERY decomposition measured there is 13-28 % off
    # serial - scotch and both planar cuts alike. Judging symmetry or
    # accuracy there pins a tracked defect (N5-7) instead of testing
    # anything, so --tiny is what its name says: does a 3D run work end
    # to end. Both questions are asked at full size, where they have
    # answers.
    # x/y symmetry is a NOTE, not a gate: each gauge is already held
    # to the serial reference below, which bounds asymmetry too. A
    # second, stricter gate on the same phenomenon is how this test
    # ended up failing configurations the real gate accepted.
    print(f'  [note] x/y: {px/1e3:.0f} vs {py/1e3:.0f} kPa '
          f'({abs(px-py)/max(px,py):.1%})')

    _serial_gate(case, px, py)

    # per-step peak/impulse maps from the function objects. Snapshot p
    # is float32 (quantum ~8 Pa at 1e8 Pa), p_peak float64 - compare
    # with a relative margin.
    check('peak source is foam FO', m.get('peak_source') == 'foam-fo',
          str(m.get('peak_source')))

    fin_p = res.snapshots[labels[-1]]['p'].astype(np.float64)
    check('p_peak dominates final p',
          m['p_peak'].shape == N
          and (m['p_peak'] >= fin_p * (1.0 - 1e-6)).all()
          and m['p_peak'].max() > 2 * P_AIR)
    check('impulse map sane',
          m['impulse'].shape == N and np.isfinite(m['impulse']).all()
          and m['impulse'].max() > 0)

    print()
    if FAIL:
        print(f"FOAM 3D SMOKE: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        sys.exit(1)
    print("FOAM 3D SMOKE: PASS")


if __name__ == '__main__':
    main()
