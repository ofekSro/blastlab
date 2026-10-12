"""P1-23 / P2-22 A6: the cases that died at t = 0 now run (WSL, real solves).

On 2026-10-11 three cases aborted at blastFoam start-up with "No cells
will be activated using the detonation point": the P1-23 case (static
zones, the charge in a shallower zone than the deepest) and the GUI-14 QA
cases F05 / F06 (AMR, the charge interior left coarse at t = 0). A2's
run-time fit (backend._fit_ignition) must light them.

Pre-registered criteria (the batch plan, before any run):
  1. P1-23 serial, P1-23 on 4 ranks, F05 and F06 each log the fit note
     and reach a write after t = 0; P1-23 serial and parallel fit the
     same radius.
  2. The controls (light a cell today) log no fit, and their
     constant/phaseProperties on disk equals the rendered file. The plan
     named test_foam_writer's case2d_planar_amr, which validate_case
     refuses (see main); test_foam_writer's case2d_planar_refine and
     case3d_refine stand in for it.
  3. A4's rule: the P1-23 mesh stages run twice, once with the pre-A4
     dx_charge (a script-local override: the global fine cell) and once
     as committed, and the `[note] blastFoam set ... kg` ratio is read
     from each. A4 stays only if |1 - after| < |1 - before| (model:
     0.979 -> 0.984); otherwise its commit is reverted.
     Applied 2026-10-12: both runs set 48.88 kg (0.4888 of 100 kg, the
     charge is halved by the y_lo wall) - the two scales mark the same
     cells, the rule is not met and A4 was reverted. With A4 gone the
     two runs are the same case; the section stays as the record.

End time 2e-5 s per case (D6). Nothing is deleted; the run folders are
printed for the report. Before every solve the VM must be free (CLAUDE.md
8.6).

Run:  cd blastlab/tests && python -u _e2e_foam_ignition.py
"""

import dataclasses
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.solvers.hooks import RunHooks                    # noqa: E402

T_END = 2.0e-5
FAIL = []
RE_FIT = re.compile(r'\[note\] detonation point (\d+): the ignition radius '
                    r'([0-9.eE+-]+) mm .* fitted to ([0-9.eE+-]+) mm, '
                    r'(\d+) cell\(s\) lit')
RE_SET = re.compile(r'\[note\] blastFoam set ([0-9.eE+-]+) kg of explosive')


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


class Cap(RunHooks):
    """Keeps every log line; prints the notes, warnings and errors."""

    def __init__(self):
        self.lines = []

    def log(self, msg):
        self.lines.append(msg)
        if any(s in msg for s in ('[note]', '[warn]', 'rror', 'case dir')):
            print('    | ' + msg.strip()[:200])


def vm_free():
    res = subprocess.run(['wsl', '-d', 'Ubuntu', '--', 'pgrep', '-a',
                          'blastFoam'], capture_output=True, text=True,
                         timeout=120)
    busy = res.stdout.strip()
    if busy:
        print(f'  [busy] {busy}')
    return not busy


def times_after_0(unc):
    from blastlab.solvers.foam import reader
    out = []
    for d in (unc, os.path.join(unc, 'processor0')):
        if os.path.isdir(d):
            out += [n for t, n in reader.list_times(d) if t > 0]
    return sorted(set(out), key=float)


def fits_of(lines):
    return [m.groups() for m in map(RE_FIT.search, lines) if m]


def run_case(tag, case):
    """One real solve; returns (fits, posix, wall seconds)."""
    from blastlab.solvers import get_solver
    from blastlab.solvers.foam import env
    print(f'\n{tag}')
    if not vm_free():
        check(f'{tag}: the VM is free before the solve', False)
        return None, None, 0.0
    h = Cap()
    t0 = time.time()
    try:
        res = get_solver(case.dim, 'blastfoam')(case, h)
        posix, unc = env.case_paths(res.meta['case_dir'])
        stop = res.stop_reason
    except Exception as exc:                      # noqa: BLE001
        print(f'  [error] {type(exc).__name__}: {exc}')
        dirs = [ln.split(': ', 1)[1].strip() for ln in h.lines
                if 'case directory:' in ln]
        posix, unc = (env.case_paths(dirs[-1]) if dirs else (None, None))
        stop = f'raised {type(exc).__name__}'
    wall = time.time() - t0
    fits = fits_of(h.lines)
    writes = times_after_0(unc) if unc else []
    print(f'  run      {posix} ({wall:.0f} s, stop: {stop}); writes after '
          f'0: {writes[-3:]}; fits {fits}')
    return dict(fits=fits, writes=writes, posix=posix, unc=unc,
                lines=h.lines, stop=stop), posix, wall


def preflight_mass(tag, case, old_dx_charge):
    """A4: the mesh stages only (backend._preflight); the set-mass ratio."""
    from blastlab.solvers.foam import backend, writer
    print(f'\n{tag}')
    if not vm_free():
        check(f'{tag}: the VM is free before the stages', False)
        return None, None
    saved = writer.CaseSpec.dx_charge
    if old_dx_charge:
        # pre-A4: AMR at its level, every static case at the global fine
        writer.CaseSpec.dx_charge = property(
            lambda s: s.dx_base / 2 ** s.amr if s.amr else s.dx)
    h = Cap()
    try:
        spec = backend._preflight(case, h)
        dx_charge = spec.dx_charge      # read while the override holds
    finally:
        writer.CaseSpec.dx_charge = saved
    sc = re.search(r'scale\s+([0-9.eE+-]+);',
                   spec.files['system/setFieldsDict'])
    m = [RE_SET.search(ln) for ln in h.lines]
    m = [x for x in m if x]
    mass = float(m[0].group(1)) if m else None
    # the charge sits on the reflecting y_lo wall, so about half of it is
    # in the domain: the ratio reads ~0.49, and the rule compares the two
    # runs with each other, which that factor does not change
    ratio = mass / float(case.charge) if mass else None
    print(f'  stages   {spec.case_posix}: dx_charge {dx_charge:g} m, '
          f'scale {sc and sc.group(1)}, set {mass} kg -> ratio {ratio}')
    return ratio, spec.case_posix


def main():
    from blastlab.solvers.foam import env
    import test_foam_ignition as T
    import test_foam_writer as W
    print('P1-23 A6 - the cases that died at t = 0')
    ok, detail = env.check_available()
    if not ok:
        print(f'  [SKIP] blastFoam unavailable: {detail}')
        print('\nIGNITION E2E: SKIP')
        return 0
    env.hardware(probe=True)
    short = dict(t_end=T_END)
    p123 = T.p123_case(**short)
    walls, folders = {}, {}

    r1, folders['1 P1-23 serial'], walls['1'] = run_case(
        'case 1 - P1-23, serial', dataclasses.replace(p123, n_procs=1))
    r2, folders['2 P1-23 np4'], walls['2'] = run_case(
        'case 2 - P1-23, 4 ranks', dataclasses.replace(p123, n_procs=4))
    r3a, folders['3 F05'], walls['3a'] = run_case(
        'case 3a - F05', T.f05_case(**short))
    r3b, folders['3 F06'], walls['3b'] = run_case(
        'case 3b - F06', T.f06_case(**short))
    # the plan named case2d_planar_amr, but as a golden it is text only:
    # validate_case refuses it (the charge needs AMR level 4, not 3), so
    # the run never starts. The controls are the two static-zone goldens
    # whose charge sits on a node of its deepest zone, where the default
    # 0.9 dx clears the corner centres (0.707 / 0.866 dx) by construction
    ctls = [(nm, dataclasses.replace(W.cases()[nm], **short))
            for nm in ('case2d_planar_refine', 'case3d_refine')]
    r4s = []
    for i, (nm, c) in enumerate(ctls):
        r, folders[f'4{"ab"[i]} {nm}'], walls[f'4{"ab"[i]}'] = run_case(
            f'case 4{"ab"[i]} - control, {nm}', c)
        r4s.append((nm, c, r))

    print('\ncriteria 1-2')
    for tag, r in (('P1-23 serial', r1), ('P1-23 np4', r2),
                   ('F05', r3a), ('F06', r3b)):
        check(f'{tag}: the fit note is logged',
              bool(r and r['fits']), r and str(r['fits']))
        check(f'{tag}: a write after t = 0 exists',
              bool(r and r['writes']), r and str(r['writes'][-3:]))
    check('P1-23 serial and parallel fit the same radius',
          bool(r1 and r2 and r1['fits'] and r1['fits'] == r2['fits']),
          f"{r1 and r1['fits']} vs {r2 and r2['fits']}")
    from blastlab.solvers.foam import writer
    for nm, c, r4 in r4s:
        if not (r4 and r4['unc']):
            check(f'control {nm} ran', False)
            continue
        with open(os.path.join(r4['unc'], 'constant', 'phaseProperties'),
                  encoding='ascii', newline='') as f:
            disk = f.read()
        want = writer.render_case(c).files['constant/phaseProperties']
        check(f'control {nm}: no fit note', not r4['fits'], str(r4['fits']))
        check(f'control {nm}: phaseProperties on disk equals the rendered '
              f'file', disk == want)
        check(f'control {nm}: a write after t = 0 exists',
              bool(r4['writes']), str(r4['writes'][-3:]))

    before, folders['5 A4 before'] = preflight_mass(
        'case 5a - P1-23 mesh stages, pre-A4 dx_charge', p123, True)
    after, folders['5 A4 after'] = preflight_mass(
        'case 5b - P1-23 mesh stages, as committed', p123, False)
    print('\nA4 rule (pre-registered): keep only if |1 - after| < '
          '|1 - before|')
    if before and after:
        keep = abs(1 - after) < abs(1 - before)
        print(f'  before {before:.4f}  after {after:.4f}  -> '
              f'{"KEEP A4" if keep else "REVERT A4"}')
    else:
        print('  [FAIL] a ratio is missing')
        FAIL.append('A4 ratios')

    print('\nwall times [s]: ' + ', '.join(f'{k} {v:.0f}'
                                          for k, v in walls.items()))
    print('folders:')
    for k, v in folders.items():
        print(f'  {k:16s} {v}')
    print('\nIGNITION E2E: ' + ('FAIL - ' + ', '.join(FAIL) if FAIL
                                else 'PASS'))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
