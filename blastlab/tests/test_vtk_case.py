"""OUT-2: the VTK output case keys and their validation (no WSL, no GUI).

docs/batches/2026-09-27-out-2-vtk-output.md, Steps 1 and 2.

  A  (V1a) case keys, save / load
     * the three default cases save byte for byte as they did at c73d4fc
       (SHA-256 of save_case, taken from that commit's own tree);
     * an `on` family round-trips every key through save_case/load_case,
       with the planes, fields and value normalised;
     * `on: false` (and None) is not written;
     * a 1D file carrying `vtk_surfaces` is refused as an unknown key, and
       an unknown key inside a family is refused too.
  B  (V1b) validation - see test_validation below.

Run:  cd blastlab/tests && python test_vtk_case.py
"""
import hashlib
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core.case import (Case1D, Case2D, Case3D,        # noqa: E402
                                case_from_dict, case_to_dict, load_case,
                                save_case)
from blastlab.models import case as mcase                      # noqa: E402

FAILS = []

#: save_case(cls()) at c73d4fc (OUT-1 merged), measured on that commit's
#: own tree before OUT-2 touched models/case.py: (bytes, sha256)
DEFAULT_SAVES = {
    'Case1D': (537, 'ebeec40f5371e84fe3b67c9467fc1152'
                    'ae72610ab814e62f9fc1148dcf82aa40'),
    'Case2D': (1256, '7071cf98b62eeeef726f6a3e26da99ac'
                     '47d56d0a3f4f65311b819304d9f00bdf'),
    'Case3D': (1437, 'ff3e3925cc2cd12bd5af6c64993a1804'
                     '7eeedd6ce3ab3ff4f7a65bfd294f27d0'),
}


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAILS.append(name)


def saved_bytes(case):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, 'case.json')
        save_case(case, path)
        with open(path, 'rb') as f:
            return f.read()


def roundtrip(case):
    """(the JSON dict save_case wrote, the case load_case read back)."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, 'case.json')
        save_case(case, path)
        with open(path, encoding='utf-8') as f:
            raw = json.load(f)
        return raw, load_case(path)


#: Time-mode values are in SECONDS (owner decision P22, reversing Q3's ms)
SURF = {'on': True, 'mode': 'time', 'value': 0.0005,
        'fields': ['p', 'pMax'], 'obstacle_fields': ['p', 'impulse'],
        'planes': [['y', 1.4], ['z', 0.5]]}
VOL = {'on': True, 'mode': 'step', 'value': 25, 'fields': ['p', 'rho', 'U']}


def test_keys():
    print('\nA: case keys, save / load')
    for cls in (Case1D, Case2D, Case3D):
        b = saved_bytes(cls())
        n, sha = DEFAULT_SAVES[cls.__name__]
        check(f'{cls.__name__}(): save_case is byte-identical to c73d4fc',
              len(b) == n and hashlib.sha256(b).hexdigest() == sha,
              f'{len(b)} B {hashlib.sha256(b).hexdigest()}')
    check('Case1D has vtk_volumes and no vtk_surfaces',
          hasattr(Case1D(), 'vtk_volumes')
          and not hasattr(Case1D(), 'vtk_surfaces'))

    c3 = Case3D(solver='blastfoam', vtk_surfaces=dict(SURF),
                vtk_volumes=dict(VOL))
    raw, back = roundtrip(c3)
    check('3D, both families on: every key written, VERSION still 13',
          raw.get('vtk_surfaces') == SURF and raw.get('vtk_volumes') == VOL
          and raw.get('version') == 13, str(raw.get('vtk_surfaces')))
    check('   and read back unchanged',
          back.vtk_surfaces == SURF and back.vtk_volumes == VOL,
          f'{back.vtk_surfaces} {back.vtk_volumes}')
    check('   in the canonical key order',
          list(back.vtk_surfaces) == list(mcase.VTK_SURFACE_KEYS)
          and list(back.vtk_volumes) == list(mcase.VTK_VOLUME_KEYS))

    c2 = Case2D(solver='blastfoam',
                obstacles=[(2.0, 2.4, 0.0, 1.6)],
                vtk_surfaces={'on': True, 'mode': 'step', 'value': 10,
                              'obstacle_fields': ['p']},
                vtk_volumes={'on': True, 'mode': 'time', 'value': 0.001,
                             'fields': ['p']})
    raw2, back2 = roundtrip(c2)
    check('2D: a family written without some keys comes back complete',
          back2.vtk_surfaces == {'on': True, 'mode': 'step', 'value': 10,
                                 'fields': [], 'obstacle_fields': ['p'],
                                 'planes': []}, str(back2.vtk_surfaces))
    check('   Time-mode value is a float in s (P22), Step-mode value an int',
          isinstance(back2.vtk_volumes['value'], float)
          and back2.vtk_volumes['value'] == 0.001
          and raw2['vtk_volumes']['value'] == 0.001
          and type(back2.vtk_surfaces['value']) is int)

    d = case_to_dict(Case3D())
    d['vtk_surfaces'] = {'on': True, 'mode': 'step', 'value': 25.0,
                         'fields': ('p',), 'planes': [('x', '0.7')]}
    got = case_from_dict(json.loads(json.dumps(d))).vtk_surfaces
    check('case_from_dict normalises planes to [axis, float], fields to '
          'list of str, a whole Step value to int',
          got['planes'] == [['x', 0.7]] and got['fields'] == ['p']
          and got['value'] == 25 and type(got['value']) is int, str(got))
    d['vtk_surfaces'] = {'on': True, 'mode': 'step', 'value': 2.5,
                         'fields': ['p']}
    got = case_from_dict(json.loads(json.dumps(d))).vtk_surfaces
    check('   a fractional Step value is kept, for validation to refuse',
          got['value'] == 2.5)

    for off in ({'on': False, 'mode': 'time', 'value': 1.0,
                 'fields': ['p']}, None):
        for cls in (Case2D, Case3D):
            c = cls(vtk_surfaces=off, vtk_volumes=off)
            d = case_to_dict(c)
            check(f'{cls.__name__}: {off and "on: false" or "None"} is not '
                  f'written',
                  'vtk_surfaces' not in d and 'vtk_volumes' not in d)
        d1 = case_to_dict(Case1D(vtk_volumes=off))
        check(f'Case1D: {off and "on: false" or "None"} is not written',
              'vtk_volumes' not in d1)
    check('   and an on:false case saves byte-identical to the default',
          saved_bytes(Case3D(vtk_volumes={'on': False}))
          == saved_bytes(Case3D()))

    d1 = case_to_dict(Case1D())
    d1['vtk_surfaces'] = dict(SURF)
    try:
        case_from_dict(d1)
        check('Case1D refuses vtk_surfaces', False)
    except ValueError as exc:
        check('Case1D refuses vtk_surfaces ("Unknown case keys")',
              'Unknown case keys' in str(exc), str(exc))
    d1 = case_to_dict(Case1D())
    d1['vtk_volumes'] = dict(VOL)
    back1 = case_from_dict(json.loads(json.dumps(d1)))
    check('Case1D keeps vtk_volumes', back1.vtk_volumes == VOL)

    d = case_to_dict(Case3D())
    d['vtk_volumes'] = dict(VOL, planes=[['y', 1.0]])
    try:
        case_from_dict(d)
        check('vtk_volumes refuses a surfaces-only key (planes)', False)
    except ValueError as exc:
        check('vtk_volumes refuses a surfaces-only key (planes)',
              'Unknown vtk_volumes keys' in str(exc), str(exc))
    d['vtk_volumes'] = ['p']
    try:
        case_from_dict(d)
        check('a family that is not an object is refused', False)
    except ValueError as exc:
        check('a family that is not an object is refused',
              'must be an object' in str(exc), str(exc))


# ── B: validation ─────────────────────────────────────────────────────────


def said(rep, words, where=('errors', 'warnings', 'notes')):
    return [m for w in where for m in getattr(rep, w) if words in m]


def vtk_errors(rep):
    return [m for m in rep.errors if 'VTK' in m or 'vtk_' in m]


def s_on(**kw):
    d = {'on': True, 'mode': 'time', 'value': 0.0005, 'fields': ['p', 'pMax'],
         'obstacle_fields': [], 'planes': []}
    d.update(kw)
    return d


def v_on(**kw):
    d = {'on': True, 'mode': 'step', 'value': 25,
         'fields': ['p', 'rho', 'U']}
    d.update(kw)
    return d


def rep3(**kw):
    """The shipped 3D default on blastFoam (validates clean) plus `kw`."""
    from blastlab.core.case import validate_case
    base = dict(solver='blastfoam', t_end=0.002)
    base.update(kw)
    return validate_case(Case3D(**base))


def rep2(**kw):
    from blastlab.core.case import validate_case
    base = dict(solver='blastfoam', t_end=0.002,
                obstacles=[(2.0, 2.4, 0.0, 1.6)])
    base.update(kw)
    return validate_case(Case2D(**base))


def rep1(**kw):
    from blastlab.core.case import validate_case
    base = dict(solver='blastfoam', radius_m=5.0, cell_size_m=0.02)
    base.update(kw)
    return validate_case(Case1D(**base))


def test_validation():
    print('\nB: validation')
    base3, base2, base1 = rep3(), rep2(), rep1()
    check('the three base cases have no error at all',
          not base3.errors and not base2.errors and not base1.errors,
          f'{base3.errors} {base2.errors} {base1.errors}')
    check('   and not one word about VTK',
          not any(said(r, 'VTK') for r in (base3, base2, base1)))
    ok3 = rep3(vtk_surfaces=s_on(planes=[['y', 1.0], ['z', 0.4]],
                                 obstacle_fields=[]),
               vtk_volumes=v_on())
    check('3D, both families on and sane: no error',
          not ok3.errors, str(ok3.errors))
    ok1 = rep1(vtk_volumes=v_on(fields=['p', 'rho', 'U', 'T', 'alpha.expl',
                                        'rhoE']))
    check('1D volumes with its six fields: no error', not ok1.errors,
          str(ok1.errors))
    ok2 = rep2(vtk_surfaces=s_on(fields=[], obstacle_fields=['p', 'pMax']),
               vtk_volumes=v_on(mode='time', value=0.0001))
    check('2D obstacles + volumes: no error', not ok2.errors, str(ok2.errors))

    refusals = (
        ('value <= 0 (surfaces)', rep3(vtk_surfaces=s_on(value=0)),
         'VTK sections/obstacles: the interval must be > 0'),
        ('value < 0 (volumes)', rep3(vtk_volumes=v_on(value=-5)),
         'VTK volumes: the interval must be > 0'),
        ('a value that is not a number',
         rep3(vtk_volumes=v_on(value='fast')),
         'VTK volumes: the interval must be a number'),
        ('a NaN value (Step)', rep3(vtk_volumes=v_on(value=float('nan'))),
         'VTK volumes: the interval must be a number'),
        ('an infinite value (Time)', rep3(vtk_surfaces=s_on(
            value=float('inf'))),
         'VTK sections/obstacles: the interval must be a number'),
        ('a fractional Step value', rep3(vtk_volumes=v_on(value=2.5)),
         'whole number of solver steps'),
        ('a mode not in time|step', rep3(vtk_volumes=v_on(mode='frames')),
         "VTK volumes: mode 'frames'"),
        ('a field 1D does not have', rep1(vtk_volumes=v_on(fields=['pMax'])),
         "VTK volumes: 'pMax' is not written in 1D"),
        ('an unknown field', rep3(vtk_volumes=v_on(fields=['Ma'])),
         "VTK volumes: unknown field 'Ma'"),
        ('an unknown obstacle field',
         rep3(obstacles=[(1.2, 1.4, 0.2, 1.3, 0.0, 0.6)],
              vtk_surfaces=s_on(obstacle_fields=['q'])),
         "VTK obstacles: unknown field 'q'"),
        ('a plane axis not in x y z',
         rep3(vtk_surfaces=s_on(planes=[['q', 1.0]])),
         "plane axis 'q'"),
        ('a plane on the domain edge',
         rep3(vtk_surfaces=s_on(planes=[['y', 1.5]])),
         'plane y = 1.5 m is not inside the domain'),
        ('a plane at 0', rep3(vtk_surfaces=s_on(planes=[['x', 0.0]])),
         'plane x = 0 m is not inside the domain'),
        ('a plane outside', rep3(vtk_surfaces=s_on(planes=[['z', -1.0]])),
         'plane z = -1 m is not inside the domain'),
        ('two planes on one cell layer',
         rep3(vtk_surfaces=s_on(planes=[['y', 1.0], ['y', 1.004]])),
         'snap to one cell layer'),
        ('a plane on the live slice layer',
         rep3(vtk_surfaces=s_on(planes=[['y', 0.752]])),
         'the live slice and y = 0.752 m snap to one cell layer'),
        ('planes in 2D', rep2(vtk_surfaces=s_on(
            fields=[], obstacle_fields=['p'], planes=[['y', 1.0]])),
         'VTK sections: planes are 3D only'),
        ('section fields in 2D', rep2(vtk_surfaces=s_on(fields=['p'])),
         'VTK sections: a 2D case has no sections'),
        ('2D surfaces without obstacles', rep2(
            obstacles=[], vtk_surfaces=s_on(fields=[],
                                            obstacle_fields=['p'])),
         'VTK obstacles: the case has no obstacles - nothing to sample'),
        ('3D obstacle fields only, without obstacles', rep3(
            vtk_surfaces=s_on(fields=[], obstacle_fields=['p'])),
         'VTK obstacles: the case has no obstacles - nothing to sample'),
        ('a family with no field at all', rep3(vtk_volumes=v_on(fields=[])),
         'VTK volumes: no field selected'),
        ('surfaces with no field at all', rep3(vtk_surfaces=s_on(
            fields=[], obstacle_fields=[])),
         'VTK sections/obstacles: no field selected'),
        ('volumes together with a write budget',
         rep3(write_budget=20, vtk_volumes=v_on()),
         'both pin the write interval - clear one'),
        ('volumes on a parallel AMR case',
         rep3(amr_levels=1, n_procs=4, vtk_volumes=v_on()),
         'cannot be exported from a parallel AMR run'),
        ('an unknown key inside a family',
         rep3(vtk_volumes=dict(v_on(), planes=[])),
         'Unknown vtk_volumes keys'),
    )
    for what, rep, words in refusals:
        check(f'refused: {what}', said(rep, words, ('errors',)),
              str(rep.errors))

    check('3D obstacle fields without obstacles, with section fields: a '
          'note, not an error',
          said(rep3(vtk_surfaces=s_on(obstacle_fields=['p'])),
               'only the sections are written', ('notes',))
          and not vtk_errors(rep3(vtk_surfaces=s_on(obstacle_fields=['p']))))
    # out-2 verify: the clash test must snap on the writer's own grid
    # (refine.plan_levels), not a uniform grid rebuilt from the charge
    # cell size - here those put x = 0.1534 / 0.1554 m on one layer, while
    # the writer cuts them on two
    from blastlab.solvers.foam import writer
    near = dict(Lx=0.6, Ly=0.5, Lz=0.4, cell_size_m=0.05, charge=0.1,
                center=(0.3, 0.25, 0.2), gauges=[(0.55, 0.25, 0.2)],
                slice_axis='x', slice_pos=0.58,
                vtk_surfaces=s_on(planes=[['x', 0.1534], ['x', 0.1554]]))
    r_near = rep3(**near)
    sp_near = writer.plan_case(Case3D(solver='blastfoam', t_end=0.002,
                                      **near))
    check('two planes the writer cuts on two layers are not refused',
          not r_near.errors
          and writer.snap_plane(sp_near, 'x', 0.1534)
          != writer.snap_plane(sp_near, 'x', 0.1554), str(r_near.errors))
    check('volumes on a SERIAL AMR case are allowed',
          not said(rep3(amr_levels=1, n_procs=1, vtk_volumes=v_on()),
                   'parallel AMR', ('errors',)))
    check('a write budget with surfaces only is allowed',
          not vtk_errors(rep3(write_budget=20, vtk_surfaces=s_on())))
    off = rep3(vtk_surfaces=s_on(on=False, value=-1),
               vtk_volumes=v_on(on=False, mode='bad'))
    check('a family that is off is not looked at', not said(off, 'VTK'))
    nat = rep3(solver='native', vtk_volumes=v_on(value=-1))
    check('native mode: one note, "the native solver ignores it", no error',
          said(nat, 'VTK output is a blastFoam setting - the native solver '
                    'ignores it', ('notes',))
          and not said(nat, 'VTK', ('errors',)), str(nat.errors))
    # P22: seconds - 0.002 s / 0.0001 s = 20 writes (not 21: the float
    # quotient is 20.000000000000004)
    tm = rep3(vtk_volumes=v_on(mode='time', value=0.0001))
    check('Time-mode volumes: a note with the write count and the disk',
          said(tm, 'VTK volumes: one write every 0.0001 s, 20 writes',
               ('notes',)) and said(tm, 'GB of written times', ('notes',))
          and said(tm, 'slows it', ('notes',)),
          str(tm.notes))
    fr = rep3(vtk_volumes=v_on(mode='time', value=0.0003))
    check('   a cadence that does not divide t_end rounds the count up',
          said(fr, 'one write every 0.0003 s, 7 writes', ('notes',)),
          str(fr.notes))
    s_err = rep3(vtk_surfaces=s_on(value=0))
    check('   the refusal names seconds, not ms',
          said(s_err, 'the interval must be > 0 (s)', ('errors',)),
          str(s_err.errors))
    auto = rep3(t_end=0.0, vtk_volumes=v_on(mode='time', value=0.0005))
    check('   with an automatic end time it says "up to"',
          said(auto, 'writes (~', ('notes',))
          and said(auto, ', up to ', ('notes',)), str(auto.notes))


def main():
    from blastlab.core import hardware
    from blastlab.solvers.foam import env
    test_keys()
    # the parallel-AMR refusal reads the rank plan and the caps read the
    # machine: pin both, as test_case_validate.main does
    hw_attrs = ('_cores', '_slots', '_ram_gb', '_cores_src', '_slots_src',
                '_ram_src', '_cores_tried', '_slots_tried', '_ram_tried')
    old = tuple(getattr(env, a) for a in hw_attrs)
    old_host = (hardware._host_ram_gb, hardware._host_ram_src,
                hardware._host_probed)
    try:
        env.forget_hardware()
        env.prime_hardware(cores=8, ram_gb=512, source=hardware.MEASURED)
        hardware.forget_host()
        hardware.prime_host(ram_gb=256, source=hardware.MEASURED)
        test_validation()
    finally:
        for a, v in zip(hw_attrs, old):
            setattr(env, a, v)
        (hardware._host_ram_gb, hardware._host_ram_src,
         hardware._host_probed) = old_host


if __name__ == '__main__':
    main()
    print()
    print('VTK CASE: ' + ('PASS' if not FAILS else
                          f'FAIL ({len(FAILS)}): ' + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)
