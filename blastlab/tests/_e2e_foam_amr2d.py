"""Manual e2e (WSL): a planar 2D blastFoam run with DYNAMIC mesh
refinement (adaptiveFvMesh, ROADMAP N16) against a uniform run at the
same finest cell.

A 400 kg/m line charge in a 4 x 4 m planar box on a 20 cm base with 3
AMR levels (finest 2.5 cm, the display grid) versus the same case on a
uniform 2.5 cm grid (160 x 160 = 25,600 cells).

The charge was 100 kg/m until 2026-09-09. T39 raised the blastFoam
charge target from 5 cells across the radius to 8 (FOAM_EXP_CELLS), and
100 kg/m then needed AMR level 4 - so this suite stopped before the
solver even started, with "Resolving the charge (8 cells across its
radius) needs AMR level 4". Raising the charge restores the invariant
this comparison is built on - AMR's finest cell IS the uniform grid's
cell - which adding a level would have broken (it would have made the
uniform reference 4x more expensive and no longer the same cell size). Checks the AMR mesh
stages, the per-time structure (C + cellLevel -> display remap), the
per-write log line, the per-frame level maps, gauge agreement with the
uniform reference (peak / arrival / positive-phase impulse), the FO
peak/impulse against the per-write Python accumulation, the graceful
arrival stop, the post-mortem reload, the wall-time ratio and the cell
count over time.

Run:  cd blastlab/tests && python _e2e_foam_amr2d.py   (~5 min, WSL)
"""
import os
import re
import subprocess
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from blastlab.core.case import Case2D, validate_case            # noqa: E402
from blastlab.core.constants import P_AIR                       # noqa: E402
from blastlab.solvers import get_solver                         # noqa: E402
from blastlab.solvers.foam import env                           # noqa: E402
from blastlab.solvers.hooks import RunHooks                     # noqa: E402

#: T50: the pre-T50 solver default - every side lets the wave out
#: AND ends the run when it arrives (the plain 'transmit'
#: default would run this to the safety cap).
ALL_TERM = dict(x_lo='terminate', x_hi='terminate',
                y_lo='terminate', y_hi='terminate')

FAILS = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f' - {detail}' if detail else ''))
    if not ok:
        FAILS.append(name)


class Hooks(RunHooks):
    def __init__(self):
        super().__init__()
        self.lines, self.frames = [], 0

    def log(self, s):
        self.lines.append(s)
        print(s)

    def frame(self, payload, t, levels=None):
        self.frames += 1


def arrival(times, p, thresh=0.05):
    ovp = p - P_AIR
    idx = np.argmax(ovp > thresh * P_AIR)
    return times[idx]


def pos_impulse(times, p, t_max):
    """Positive-phase impulse up to t_max [Pa s]."""
    m = times <= t_max
    ovp = np.clip(p[m] - P_AIR, 0.0, None)
    trapz = getattr(np, 'trapezoid', None) or np.trapz
    return float(trapz(ovp, times[m]))


def run(case, label):
    rep = validate_case(case)
    check(f'{label}: validates', rep.ok, '; '.join(rep.errors))
    for n in rep.notes:
        if 'AMR' in n or 'display' in n:
            print('   note:', n)
    h = Hooks()
    t0 = time.perf_counter()
    res = get_solver(2, 'blastfoam')(case, h)
    wall = time.perf_counter() - t0
    print(f'  --- {label}: {wall:.0f} s, {h.frames} live frames')
    return res, h, wall


def main():
    base = dict(geometry='planar', Lx=4.0, Ly=4.0, charge=400.0,
                center=(2.0, 2.0), gauges=[(3.2, 2.0)], n_snapshots=2,
                solver='blastfoam', material='TNT')
    # --np=N (T42/N16-b): run the AMR case on N MPI ranks. Its written
    # times then stay in processor*/ and the ingest concatenates them,
    # because reconstructPar cannot follow a mesh that changes.
    np_req = 0
    for a in sys.argv[1:]:
        if a.startswith('--np='):
            np_req = int(a.split('=', 1)[1])
    amr = Case2D(cell_size_m=0.2, amr_levels=3, n_procs=np_req,
                 bcs=ALL_TERM, **base)
    if np_req:
        print(f'  (AMR on {np_req} MPI ranks)')
    res, h, wall_amr = run(amr, 'AMR (base 0.2 m, 3 levels)')
    m = res.meta

    check('mesh stages: t = 0 refinement stage + cell centres logged',
          any('t = 0 refinement to level 3' in l for l in h.lines)
          and any('writing cell centres' in l for l in h.lines))
    t0_line = [l for l in h.lines if 'AMR mesh at t = 0' in l]
    n0 = int(re.search(r'(\d[\d,]*) cells', t0_line[0]).group(1).replace(',', '')) if t0_line else 0
    check('t = 0 mesh read back: more than the 400 base cells (charge refined)',
          n0 > 400, str(t0_line[:1]))
    notes = [l for l in h.lines if '[blastfoam] AMR t = ' in l]
    counts = [int(re.search(r'ms: (\d[\d,]*) cells', l).group(1).replace(',', ''))
              for l in notes]
    check('per-write AMR log lines (>= 5 writes)', len(notes) >= 5, str(len(notes)))
    if counts:
        print(f'  cells per write: min {min(counts):,}, max {max(counts):,}, '
              f'final {counts[-1]:,}  (uniform reference 25,600)')
        check('the mesh grew and stayed well below the uniform count',
              max(counts) > n0 and max(counts) < 25_600, f'{max(counts):,}')
    ref = m.get('refine')
    check("meta['refine']: amr 3, display level 3, final level map on the 160x160 grid",
          ref is not None and ref.get('amr') == 3 and ref.get('display_level') == 3
          and ref['levels'].shape == (160, 160) and ref['levels'].max() >= 1
          and ref.get('n_cells') == (counts[-1] if counts else None),
          f"{None if ref is None else (ref.get('amr'), ref['levels'].shape, ref.get('n_cells'))}")
    p = list(res.snapshots.values())[-1]['p']
    check('final field on the display grid', p.shape == (160, 160), str(p.shape))
    fr = m.get('frames') or {}
    check("frames['levels'] recorded, one per frame",
          'levels' in fr and len(fr['levels']) == len(fr['pressures']) > 3
          and all(lv.shape == (160, 160) for lv in fr['levels']),
          f"{len(fr.get('levels', []))} vs {len(fr.get('pressures', []))}")
    check('live frames arrived (from written times)', h.frames >= 3, str(h.frames))
    check('stopped via arrival', res.stop_reason.startswith('shock arrived'), res.stop_reason)
    check('graceful stop honoured (no kill)',
          not any('did not stop cleanly' in l for l in h.lines))
    check('no live-slice leftovers', not os.path.isdir(
        os.path.join(m['case_dir'], 'postProcessing', 'liveSlice')))
    check("peak/impulse from the FO fields", m.get('peak_source') == 'foam-fo',
          str(m.get('peak_source')))
    if fr.get('pressures') and res.gauges['pressures']:
        # the FO pMax is per step and mapped across every mesh change; the
        # blastProbes gauge is per step too, so the two must agree at the
        # gauge cell (the per-write frame maximum is only a lower bound)
        gx, gy = amr.gauges[0]
        i = int(np.searchsorted(m['x_face'], gx)) - 1
        j = int(np.searchsorted(m['y_face'], gy)) - 1
        fo_pk = float(m['p_peak'][i, j]) - P_AIR
        g_pk = float(res.gauges['pressures'][0].max()) - P_AIR
        py_pk = float(np.max(np.stack(fr['pressures']), axis=0)[i, j]) - P_AIR
        print(f'  gauge cell peak: FO pMax {fo_pk/1e3:.0f} kPa, gauge trace '
              f'{g_pk/1e3:.0f} kPa, per-write frames {py_pk/1e3:.0f} kPa')
        check('FO pMax at the gauge cell within 10 % of the gauge trace peak '
              '(mapped across every mesh change)',
              abs(fo_pk - g_pk) / g_pk < 0.10, f'{fo_pk/1e3:.0f} vs {g_pk/1e3:.0f} kPa')

    uni = Case2D(cell_size_m=0.025, **base, bcs=ALL_TERM)
    ref_res, _hu, wall_uni = run(uni, 'uniform 0.025 m reference')
    print(f'  wall time: AMR {wall_amr:.0f} s vs uniform {wall_uni:.0f} s '
          f'-> ratio {wall_uni / max(wall_amr, 1e-9):.2f}x')
    g_a, g_u = res.gauges, ref_res.gauges
    check('both runs recorded the gauge',
          len(g_a['pressures']) == 1 and len(g_u['pressures']) == 1)
    if g_a['pressures'] and g_u['pressures']:
        pk_a = g_a['pressures'][0].max() - P_AIR
        pk_u = g_u['pressures'][0].max() - P_AIR
        ta_a = arrival(g_a['times'], g_a['pressures'][0])
        ta_u = arrival(g_u['times'], g_u['pressures'][0])
        t_max = min(g_a['times'][-1], g_u['times'][-1])
        i_a = pos_impulse(g_a['times'], g_a['pressures'][0], t_max)
        i_u = pos_impulse(g_u['times'], g_u['pressures'][0], t_max)
        check('gauge peak within 10 % of the uniform reference',
              abs(pk_a - pk_u) / pk_u < 0.10,
              f'AMR {pk_a/1e3:.0f} kPa, uniform {pk_u/1e3:.0f} kPa')
        # the AMR charge comes from the mass-based cylinder source (a
        # backup region is needed on the coarse base), the uniform one
        # from the geometric cylinderToCell: slightly different initial
        # charges, hence the wider arrival / impulse bands (measured
        # 2026-09-05: peak -0.6 %, arrival -5.6 %, impulse +10.3 %)
        check('gauge arrival within 10 % of the uniform reference',
              abs(ta_a - ta_u) / ta_u < 0.10,
              f'AMR {ta_a*1e3:.3f} ms, uniform {ta_u*1e3:.3f} ms')
        check('positive-phase impulse within 15 % (common window)',
              abs(i_a - i_u) / i_u < 0.15,
              f'AMR {i_a:.1f} Pa s, uniform {i_u:.1f} Pa s to {t_max*1e3:.3f} ms')

    # optional threshold sweep: --sweep 0.2:0.1,0.5:0.25 runs extra AMR
    # variants and tabulates them against the uniform reference (the
    # defaults are tuned from this table; nothing here is a pass/fail)
    sweep = [a for a in sys.argv[1:] if a.startswith('--sweep')]
    if sweep and g_u['pressures']:
        arg = sweep[0].split('=', 1)[1] if '=' in sweep[0] else sys.argv[sys.argv.index(sweep[0]) + 1]
        pk_u = g_u['pressures'][0].max() - P_AIR
        ta_u = arrival(g_u['times'], g_u['pressures'][0])
        rows = [('uniform 0.025 m', wall_uni, 25_600, 25_600, 0.0, 0.0),
                (f'AMR {amr.amr_refine:g}/{amr.amr_unrefine:g}', wall_amr,
                 max(counts), counts[-1], (pk_a - pk_u) / pk_u * 100,
                 (ta_a - ta_u) / ta_u * 100)]
        for pair in arg.split(','):
            lo, un = (float(v) for v in pair.split(':'))
            c = Case2D(cell_size_m=0.2, amr_levels=3, amr_refine=lo,
                       amr_unrefine=un, **base, bcs=ALL_TERM)
            r_i, h_i, w_i = run(c, f'AMR {lo:g}/{un:g}')
            n_i = [int(re.search(r'ms: (\d[\d,]*) cells', l).group(1).replace(',', ''))
                   for l in h_i.lines if '[blastfoam] AMR t = ' in l]
            g_i = r_i.gauges
            pk_i = g_i['pressures'][0].max() - P_AIR
            ta_i = arrival(g_i['times'], g_i['pressures'][0])
            rows.append((f'AMR {lo:g}/{un:g}', w_i, max(n_i), n_i[-1],
                         (pk_i - pk_u) / pk_u * 100, (ta_i - ta_u) / ta_u * 100))
        print('\n  threshold sweep (refine/unrefine) vs the uniform reference:')
        print(f"  {'case':<22}{'wall s':>8}{'max cells':>11}{'final':>9}{'peak %':>9}{'arrival %':>11}")
        for name, w, nmax, nfin, dpk, dta in rows:
            print(f'  {name:<22}{w:>8.0f}{nmax:>11,}{nfin:>9,}{dpk:>+9.1f}{dta:>+11.1f}')

    from blastlab.solvers.foam import postmortem
    pm = postmortem.load_run(m['case_dir'])
    pp = list(pm.snapshots.values())[-1]['p']
    check('post-mortem reload: same display grid, AMR record and final field',
          pm.meta.get('refine') is not None and pm.meta['refine'].get('amr') == 3
          and pm.meta['refine'].get('n_cells') == ref.get('n_cells')
          and np.array_equal(pm.meta['refine']['levels'], ref['levels'])
          and pp.shape == p.shape and np.allclose(pp, p),
          f"{pp.shape} vs {p.shape}")
    left = subprocess.run(
        env.wsl_plain_argv('pgrep -a -f "[b]lastFoam|[s]etRefinedFields" 2>/dev/null; true'),
        capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL,
        creationflags=env.CREATE_NO_WINDOW).stdout.strip()
    check('no solver process left behind in WSL', not left, left)
    print(f"  AMR case dir: {m['case_dir']}")
    print(f"  uniform case dir: {ref_res.meta['case_dir']}")
    return m['case_dir']


if __name__ == '__main__':
    main()
    print()
    print('E2E FOAM AMR 2D: ' + ('PASS' if not FAILS else f'FAIL ({len(FAILS)}): ' + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)
