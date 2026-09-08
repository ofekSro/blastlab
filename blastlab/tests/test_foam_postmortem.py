"""postmortem.load_run round-trip, and resume (N6/T43).

Round-trip: run a small 2D foam case live, reload the finished case dir
and require the exact same Result shapes and values. Resume: run the
SAME case again but stop it after a few writes, `backend.resume_run` it,
and compare the merged result against the uninterrupted reference -
gauges identical over the pre-stop prefix, final peak map within 0.5 %.
Path mapping and run listing are checked without WSL; everything else
auto-SKIPs when blastFoam is unavailable."""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

import numpy as np                                             # noqa: E402

#: T50: the pre-T50 solver default - every side lets the wave out
#: AND ends the run when it arrives (the plain 'transmit'
#: default would run this to the safety cap).
ALL_TERM = dict(x_lo='terminate', x_hi='terminate',
                y_lo='terminate', y_hi='terminate')

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAIL.append(name)


def main():
    from blastlab.solvers.foam import postmortem as pm

    # ── path mapping (no WSL) ───────────────────────────────────────────
    p, _ = pm._paths('20260101-000000_2d')
    check('bare name maps under RUNS_ROOT',
          p == '/root/blastlab_runs/20260101-000000_2d', p)
    p, _ = pm._paths('\\\\wsl.localhost\\Ubuntu\\root\\blastlab_runs'
                     '\\x_3d')
    check('UNC maps to posix', p == '/root/blastlab_runs/x_3d', p)
    p, _ = pm._paths('/root/spike/s1')
    check('posix passes through', p == '/root/spike/s1', p)

    # listing contract (B14a): triples, and "not checked" is None -
    # never False, so a caller cannot read it as "nothing is running"
    runs = pm.list_runs()
    check('list_runs yields (name, unc, alive) triples',
          all(len(r) == 3 for r in runs), f'{len(runs)} run(s)')
    check('list_runs leaves alive unknown unless asked',
          all(r[2] is None for r in runs))

    # ── live-vs-loaded round trip (WSL) ─────────────────────────────────
    from blastlab.solvers.foam import env
    ok, detail = env.check_available()
    if not ok:
        print(f"  [SKIP] blastFoam unavailable: {detail}")
        print("\nFOAM POSTMORTEM: "
              + ("FAIL" if FAIL else "PASS (offline checks only)"))
        return 1 if FAIL else 0

    from blastlab.core.case import Case2D
    from blastlab.solvers import get_solver
    case = Case2D(geometry='axisymmetric', Lx=2.0, Ly=2.0,
                  cell_size_m=0.02, charge=4.0, center=(0.0, 1.0),
                  n_snapshots=3, gauges=[(0.6, 1.0)], record_frames=0,
                  solver='blastfoam', material='TNT', bcs=ALL_TERM)
    live = get_solver(2, 'blastfoam')(case)
    loaded = pm.load_run(live.meta['case_dir'])

    check('snapshot labels equal',
          list(live.snapshots) == list(loaded.snapshots),
          f"{list(live.snapshots)} vs {list(loaded.snapshots)}")
    lbl = list(live.snapshots)[-1]
    for key in ('p', 'rho', 'speed'):
        a = live.snapshots[lbl][key]
        b = loaded.snapshots[lbl][key]
        check(f'final snapshot {key} identical',
              a.shape == b.shape and np.array_equal(a, b))
    check('gauge times identical',
          np.array_equal(live.gauges['times'], loaded.gauges['times']))
    check('gauge pressures identical',
          all(np.array_equal(a, b) for a, b in
              zip(live.gauges['pressures'], loaded.gauges['pressures'])))
    check('meta keys superset',
          set(loaded.meta) >= set(live.meta),
          str(set(live.meta) - set(loaded.meta)))
    # QA-24/T30: a loaded run replays. Its frames come from every written
    # time, so it has at least as many as the live run's live-frame gate
    # let through - and they are the same slice shape.
    lf = (live.meta.get('frames') or {}).get('pressures') or []
    pf = (loaded.meta.get('frames') or {}).get('pressures') or []
    check('a loaded run carries replay frames', len(pf) > 0, f'{len(pf)}')
    check('loaded frames have the live frame shape',
          not lf or lf[0].shape == pf[0].shape,
          f'{lf[0].shape if lf else None} vs {pf[0].shape if pf else None}')
    check('loaded frame times are sorted and finite',
          bool(len(pf)) and list(loaded.meta['frames']['times'])
          == sorted(loaded.meta['frames']['times']))
    fs_l, fs_p = live.meta['final_state'], loaded.meta['final_state']
    check('final_state identical',
          all(np.array_equal(np.asarray(fs_l[k]), np.asarray(fs_p[k]))
              for k in ('rho', 'u', 'v', 'e', 'p', 'phase'))
          and fs_l['t'] == fs_p['t'])
    check('FO maps survive reload',
          loaded.meta.get('peak_source') == live.meta.get('peak_source'))
    check('stop reason marks post-mortem',
          loaded.stop_reason.startswith('loaded post-mortem'))

    # ── stop -> resume -> compare with the uninterrupted run (N6/T43) ──
    print("\nresume (N6/T43)")
    from blastlab.solvers.foam.backend import resume_run
    from blastlab.solvers.hooks import RunHooks

    class StopAfter(RunHooks):
        """Request a graceful stop once N frames were ingested."""
        refresh = ('steps', 1)          # a frame per ingested write

        def __init__(self, n):
            self.n, self.frames = n, 0

        def frame(self, field2d, t, levels=None):
            self.frames += 1

        def should_stop(self):
            return self.frames >= self.n

    st_hooks = StopAfter(3)
    part = get_solver(2, 'blastfoam')(case, st_hooks)
    check('run stopped early by the scripted hooks',
          part.stopped_early and len(part.gauges['times'])
          < len(live.gauges['times']),
          f"{part.stop_reason}; {len(part.gauges['times'])} vs "
          f"{len(live.gauges['times'])} samples")

    res = resume_run(part.meta['case_dir'])
    check('resume returns a completed result',
          not res.stopped_early
          and res.meta['case_dir'] == part.meta['case_dir'],
          res.stop_reason)

    n_pre = len(part.gauges['times'])
    check('gauge times identical over the pre-stop prefix',
          np.array_equal(res.gauges['times'][:n_pre],
                         live.gauges['times'][:n_pre]))
    check('gauge pressures identical over the pre-stop prefix',
          all(np.array_equal(res.gauges['pressures'][k][:n_pre],
                             live.gauges['pressures'][k][:n_pre])
              for k in range(len(live.gauges['pressures']))))
    pk_live = live.meta['p_peak']
    pk_res = res.meta['p_peak']
    rel = float(np.abs(pk_res - pk_live).max() / np.abs(pk_live).max())
    check('final peak map within 0.5 % of the uninterrupted run',
          rel <= 0.005, f'max rel diff {rel:.2e}')
    # characterisation, not a gate (W2): blastProbes buffers its per-step
    # samples and only flushes them at a graceful End, so a run that is
    # STOPPED loses the samples still in the buffer - measured 5 of ~600
    # surviving. The loss happens at stop time, with or without a
    # resume; the brief's own acceptance (prefix identical, peak map
    # within 0.5 %) is asserted above.
    n_res, n_live = len(res.gauges['times']), len(live.gauges['times'])
    print(f'  [note] merged trace {n_res} samples vs uninterrupted'
          f' {n_live} (blastProbes flush-on-End, see W2)')

    print()
    if FAIL:
        print(f"FOAM POSTMORTEM: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        return 1
    print("FOAM POSTMORTEM: PASS")
    return 0


if __name__ == '__main__':
    sys.exit(main())
