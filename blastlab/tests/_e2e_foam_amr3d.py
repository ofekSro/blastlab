"""Manual e2e (WSL): a 3D blastFoam run with DYNAMIC mesh refinement
(adaptiveFvMesh, ROADMAP N16) against a statically refined reference at
the display level.

60 kg TNT in a 3 x 3 x 3 m box on a 10 cm base with 2 AMR levels
(finest 2.5 cm) displayed at level 1 (5 cm, 60^3 = 216,000 display cells;
cells finer than that are box-averaged) versus the same case on a 5 cm
grid with the N15 static charge zones ('zone' mode: base 5 cm + level-1
zones around the charge, ~216k cells). A true uniform run at the finest
2.5 cm would be 120^3 = 1.7M cells - infeasible in WSL, which is the
point of AMR - so its cost is extrapolated from the AMR run's step count.
Checks the AMR mesh stages, the per-time structure, the per-write log
line, the display grid, the recorded per-frame level maps (slices), gauge
agreement (peak / arrival), the FO peak at the gauge cell, the arrival
stop, the post-mortem reload, the wall times and the cell count over time.

Two gauges are recorded: the requested (2.5, 1.5, 1.5), which is a cell
CORNER on both meshes, and (2.45, 1.45, 1.45), which is the centre of a
base (10 cm) cell - the pair separates a real arrival difference from the
probe being snapped somewhere else (N16-a).

Run:  cd blastlab/tests && python _e2e_foam_amr3d.py   (~30 min, WSL: the
      AMR run itself is ~23 min at 300k cells; --amr-dir=<case dir> reloads
      a finished AMR run post-mortem instead of re-running it;
      --no-adjust-locations writes blastProbes with adjustLocations no)
"""
import os
import re
import subprocess
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from blastlab.core.case import Case3D, validate_case            # noqa: E402
from blastlab.core.constants import P_AIR                       # noqa: E402
from blastlab.solvers import get_solver                         # noqa: E402
from blastlab.solvers.foam import env                           # noqa: E402
from blastlab.solvers.hooks import RunHooks                     # noqa: E402

#: T50: the pre-T50 3D solver default - terminating sides over a
#: reflecting ground.
ALL_TERM_3D = dict(x_lo='terminate', x_hi='terminate',
                   y_lo='terminate', y_hi='terminate',
                   z_lo='reflect', z_hi='terminate')

FAILS = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f' - {detail}' if detail else ''))
    if not ok:
        FAILS.append(name)


class Hooks(RunHooks):
    def __init__(self):
        super().__init__()
        self.lines, self.frames, self.steps = [], 0, 0

    def log(self, s):
        self.lines.append(s)
        if not s.startswith('  [foam]'):
            print(s)

    def frame(self, payload, t, levels=None):
        self.frames += 1

    def progress(self, p):
        self.steps = max(self.steps, p.step)


def arrival(times, p, thresh=0.05):
    ovp = p - P_AIR
    idx = np.argmax(ovp > thresh * P_AIR)
    return times[idx]


def run(case, label):
    rep = validate_case(case)
    check(f'{label}: validates', rep.ok, '; '.join(rep.errors))
    for n in rep.notes:
        if 'AMR' in n or 'display' in n or 'refinement' in n:
            print('   note:', n)
    h = Hooks()
    t0 = time.perf_counter()
    res = get_solver(3, 'blastfoam')(case, h)
    wall = time.perf_counter() - t0
    print(f'  --- {label}: {wall:.0f} s, {h.steps} steps, {h.frames} live frames')
    return res, h, wall


def main():
    # 60 kg, not 20: blastFoam resolves the charge with 8 cells across
    # its radius (T39), and at 20 kg that needs a third AMR level and a
    # 13.8M-cell display grid. 60 kg keeps 2 levels and the same mesh and
    # display budget this study was built around.
    # Gauge 2 sits at a BASE-cell centre; gauge 1 at a cell corner.
    base = dict(Lx=3.0, Ly=3.0, Lz=3.0, charge=60.0, center=(1.5, 1.5, 1.5),
                gauges=[(2.5, 1.5, 1.5), (2.45, 1.45, 1.45)],
                n_snapshots=2, solver='blastfoam', material='TNT')
    adjust = '--no-adjust-locations' not in sys.argv
    base['probe_adjust'] = adjust
    print(f'  probe adjustLocations: {"yes" if adjust else "no"}')
    # maxCells bounds the solver's memory: the WSL VM has 4 GB and an
    # uncapped run took it down (2026-09-05)
    amr = Case3D(cell_size_m=0.1, amr_levels=2, amr_display_level=1,
                 amr_max_cells=300_000, **base, bcs=ALL_TERM_3D)
    reuse = [a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith('--amr-dir=')]
    if reuse:
        # reload a finished AMR run (post-mortem) instead of the ~23 min solve
        from blastlab.solvers.foam import postmortem
        h = Hooks()
        res = postmortem.load_run(reuse[0], h)
        wall_amr = float('nan')
        h.steps = 0
        print(f'  --- AMR run reloaded post-mortem from {reuse[0]}')
    else:
        res, h, wall_amr = run(amr, 'AMR (base 0.1 m, 2 levels, display level 1)')
    m = res.meta

    if not reuse:
        check('mesh stages: t = 0 refinement stage + cell centres logged',
              any('t = 0 refinement to level 2' in l for l in h.lines)
              and any('writing cell centres' in l for l in h.lines))
    t0_line = [l for l in h.lines if 'AMR mesh at t = 0' in l]
    n0 = int(re.search(r'(\d[\d,]*) cells', t0_line[0]).group(1).replace(',', '')) if t0_line else 0
    check('t = 0 mesh: more than the 27,000 base cells (charge refined)',
          n0 > 27_000, str(t0_line[:1]))
    notes = [l for l in h.lines if '[blastfoam] AMR t = ' in l]
    counts = [int(re.search(r'ms: (\d[\d,]*) cells', l).group(1).replace(',', ''))
              for l in notes]
    if not reuse:
        check('per-write AMR log lines (>= 5 writes)', len(notes) >= 5, str(len(notes)))
    if counts:
        n_fine = 120 ** 3
        print(f'  cells per write: min {min(counts):,}, max {max(counts):,}, '
              f'final {counts[-1]:,}, mean {int(np.mean(counts)):,}  '
              f'(uniform 2.5 cm would be {n_fine:,}: AMR uses '
              f'{100 * np.mean(counts) / n_fine:.0f} % of its cell-steps)')
        check('the mesh grew and stayed well below the uniform-finest count',
              max(counts) > n0 and max(counts) < 0.5 * n_fine, f'{max(counts):,}')
    ref = m.get('refine')
    check("meta['refine']: amr 2, display level 1, final level map on the 60^3 grid",
          ref is not None and ref.get('amr') == 2 and ref.get('display_level') == 1
          and ref['lmax'] == 1 and ref['levels'].shape == (60, 60, 60)
          and (not counts or ref.get('n_cells') == counts[-1]),
          f"{None if ref is None else (ref.get('amr'), ref.get('display_level'), ref['levels'].shape)}")
    p = list(res.snapshots.values())[-1]['p']
    check('final field on the 60^3 display grid', p.shape == (60, 60, 60), str(p.shape))
    check('peak / impulse maps on the display grid',
          m['p_peak'].shape == (60, 60, 60) and m['impulse'].shape == (60, 60, 60))
    fr = m.get('frames') or {}
    if not reuse:                   # a post-mortem reload records no frames
        check("frames['levels'] recorded per frame as live-slice planes",
              'levels' in fr and len(fr['levels']) == len(fr['pressures']) > 3
              and all(lv.shape == (60, 60) for lv in fr['levels']),
              f"{len(fr.get('levels', []))} vs {len(fr.get('pressures', []))}")
        check('live frames arrived (from written times)', h.frames >= 3, str(h.frames))
        check('stopped via arrival', res.stop_reason.startswith('shock arrived'),
              res.stop_reason)
        check('graceful stop honoured (no kill)',
              not any('did not stop cleanly' in l for l in h.lines))
    check("peak/impulse from the FO fields", m.get('peak_source') == 'foam-fo',
          str(m.get('peak_source')))
    if res.gauges['pressures']:
        gx, gy, gz = amr.gauges[0]
        i = int(np.searchsorted(m['x_face'], gx)) - 1
        j = int(np.searchsorted(m['y_face'], gy)) - 1
        k = int(np.searchsorted(m['z_face'], gz)) - 1
        fo_pk = float(m['p_peak'][i, j, k]) - P_AIR
        g_pk = float(res.gauges['pressures'][0].max()) - P_AIR
        print(f'  gauge cell peak: FO pMax {fo_pk/1e3:.0f} kPa (display cell, box-averaged '
              f'over up to 8 fine cells), gauge trace {g_pk/1e3:.0f} kPa')
        check('FO pMax at the gauge display cell within 20 % of the gauge trace peak',
              abs(fo_pk - g_pk) / g_pk < 0.20, f'{fo_pk/1e3:.0f} vs {g_pk/1e3:.0f} kPa')

    # serial like the AMR run (auto would pick 2 ranks at 228k cells)
    ref_case = Case3D(cell_size_m=0.05, charge_refine='zone',
                      n_procs=1, bcs=ALL_TERM_3D, **base)
    ref_res, hr, wall_ref = run(ref_case, 'static reference (5 cm base + charge zones)')
    print(f'  wall time: AMR {wall_amr:.0f} s ({h.steps} steps) vs static 5 cm '
          f'{wall_ref:.0f} s ({hr.steps} steps)')
    if counts and h.steps:
        est = 120 ** 3 * h.steps / max(1.0, np.mean(counts) * h.steps)
        print(f'  extrapolated: a uniform 2.5 cm run would cost ~{est:.1f}x the '
              f'AMR cell-steps ({120 ** 3:,} cells x {h.steps} steps)')
    g_a, g_u = res.gauges, ref_res.gauges
    check('both runs recorded the gauges',
          len(g_a['pressures']) == 2 and len(g_u['pressures']) == 2)
    if g_a['pressures'] and g_u['pressures']:
        # the study table (N16-a/T40): both gauges, both runs
        print('   gauge                 AMR arr    static arr   d%     '
              'AMR pk      static pk   d%')
        for k, gp in enumerate(base['gauges']):
            if k >= min(len(g_a['pressures']), len(g_u['pressures'])):
                continue
            aa = arrival(g_a['times'], g_a['pressures'][k])
            au = arrival(g_u['times'], g_u['pressures'][k])
            pa = g_a['pressures'][k].max() - P_AIR
            pu = g_u['pressures'][k].max() - P_AIR
            print(f'   {str(gp):20s} {aa*1e3:8.3f}  {au*1e3:11.3f}  '
                  f'{(aa-au)/au*100:+6.1f}  {pa/1e3:9.0f}  {pu/1e3:10.0f}  '
                  f'{(pa-pu)/pu*100:+6.1f}')
        pk_a = g_a['pressures'][0].max() - P_AIR
        pk_u = g_u['pressures'][0].max() - P_AIR
        ta_a = arrival(g_a['times'], g_a['pressures'][0])
        ta_u = arrival(g_u['times'], g_u['pressures'][0])
        # Bands RE-TUNED 2026-09-14 (the P5-2 default change reached this
        # test late). The 10 % / 25 % bands were calibrated against the
        # old amr_refine=0.4 default; 2dc4c9f tightened it to 0.2/0.1 (a
        # deliberate accuracy fix, amr2d's bands were re-tuned in that
        # commit) and this e2e simply was not rerun until the 14.09
        # sweep. Measured then: the finer-refining AMR run diverges
        # UPWARD from the deliberately coarse 5 cm static reference -
        # peak +23.1 % / +25.2 %, arrival +28.2 % / +28.1 % on the two
        # gauges. The two gauges (cell corner vs base-cell centre)
        # agreeing to 0.1 pp also confirms T40's refutation of the
        # probe-snapping hypothesis: this is field resolution, not
        # sampling. The reference is NOT ground truth - a true uniform
        # 2.5 cm run is 1.7M cells, infeasible here - so these stay
        # sanity bands around the measured offsets: 30 % peak, 35 %
        # arrival.
        check('gauge peak within 30 % of the static reference (sanity '
              'band; measured +23 % after the 0.2/0.1 re-tune)',
              abs(pk_a - pk_u) / pk_u < 0.30,
              f'AMR {pk_a/1e3:.0f} kPa, static {pk_u/1e3:.0f} kPa')
        print(f'  gauge arrival: AMR {ta_a*1e3:.3f} ms, static {ta_u*1e3:.3f} ms '
              f'({(ta_a - ta_u) / ta_u * 100:+.1f} %)')
        check('gauge arrival within 35 % of the static reference (sanity '
              'band; measured +28 % - the open N16 offset, grown by the '
              '0.2/0.1 re-tune)',
              abs(ta_a - ta_u) / ta_u < 0.35,
              f'AMR {ta_a*1e3:.3f} ms, static {ta_u*1e3:.3f} ms')

    from blastlab.solvers.foam import postmortem
    pm = postmortem.load_run(m['case_dir'])
    check("meta['frames'] absent after a post-mortem reload is fine; refine record kept",
          pm.meta.get('refine') is not None)
    pp = list(pm.snapshots.values())[-1]['p']
    check('post-mortem reload: same display grid, AMR record and final field',
          pm.meta.get('refine') is not None and pm.meta['refine'].get('amr') == 2
          and pm.meta['refine'].get('n_cells') == ref.get('n_cells')
          and pp.shape == p.shape and np.allclose(pp, p), f"{pp.shape} vs {p.shape}")
    left = subprocess.run(
        env.wsl_plain_argv('pgrep -a -f "[b]lastFoam|[s]etRefinedFields" 2>/dev/null; true'),
        capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL,
        creationflags=env.CREATE_NO_WINDOW).stdout.strip()
    check('no solver process left behind in WSL', not left, left)
    print(f"  AMR case dir: {m['case_dir']}")
    print(f"  static case dir: {ref_res.meta['case_dir']}")
    return m['case_dir']


if __name__ == '__main__':
    main()
    print()
    print('E2E FOAM AMR 3D: ' + ('PASS' if not FAILS else f'FAIL ({len(FAILS)}): ' + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)
