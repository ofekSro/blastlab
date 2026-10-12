"""Boundary kinds + end time + trigger gauge + gauge markers.

T50  transmit / reflect / terminate: only a TERMINATE side ends a run,
     `reflect` still mirrors, legacy 'open'/'wall' still load, and the
     snapshot/progress distances count every non-reflecting side.
T51  the trigger gauge: it ends the run and/or captures the remap state
     at the instant the wave reaches it.
T52  a user end time on 1D and 2D as well.
T53  gauge markers on a field axis (2D straight through, 3D reduced to
     the plotted plane).
T60  the 1D outer boundary takes the same three kinds - and a
     reflecting one really reflects.

Tiny grids, no WSL, no GUI.  Run:  cd blastlab/tests && python test_bc_trigger.py
"""
import io
import os
import sys
import contextlib
import tempfile

import numpy as np

os.environ.setdefault('MPLBACKEND', 'Agg')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core import geometry                              # noqa: E402
from blastlab.core.constants import P_AIR                       # noqa: E402
from blastlab.core.bc import (BC_KINDS, normalize_bc,           # noqa: E402
                              normalize_bcs)
from blastlab.core.case import (Case1D, Case2D, Case3D,         # noqa: E402
                                TRIGGER_ACTIONS, case_from_dict,
                                case_to_dict, validate_case)
from blastlab.output import plots                               # noqa: E402
from blastlab.solvers.hooks import ConsoleHooks, trigger_index  # noqa: E402
from blastlab.solvers.solver1d import solve_1d                  # noqa: E402
from blastlab.solvers.solver2d import solve_2d                  # noqa: E402

FAILS = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAILS.append(name)


def quiet(fn, *a, **kw):
    """Run something with the solver banner captured; returns (out, log)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        out = fn(*a, **kw)
    return out, buf.getvalue()


def case2d(**kw):
    """A 0.6 x 1.2 m axisymmetric case small enough to run in a second."""
    kw.setdefault('bcs', dict(x_lo='reflect', x_hi='transmit',
                              y_lo='reflect', y_hi='transmit'))
    return Case2D(Lx=0.6, Ly=1.2, cell_size_m=0.03, charge=0.5,
                  center=(0.0, 0.6), n_snapshots=1, record_frames=0,
                  gauges=[(0.25, 0.6), (0.5, 0.6)], **kw)


def main():
    print("\nT50 vocabulary")
    check('the three kinds', BC_KINDS == ('transmit', 'reflect', 'terminate'))
    check("legacy 'open' -> transmit, 'wall' -> reflect",
          normalize_bc('open') == 'transmit'
          and normalize_bc('wall') == 'reflect'
          and normalize_bc('terminate') == 'terminate')
    notes = []
    normalize_bcs(dict(x_lo='wall', x_hi='open'), notes.append)
    check('normalize_bcs warns once about the mapping',
          len(notes) == 1 and 'transmit' in notes[0], str(notes))
    check('no note when nothing is legacy',
          not [n for n in [] if normalize_bcs(dict(x_lo='reflect'),
                                              [].append)])

    d = case_to_dict(Case2D())
    d['bcs'] = dict(x_lo='wall', x_hi='open', y_lo='wall', y_hi='open')
    back = case_from_dict(d)
    check('a legacy case file loads in the new vocabulary',
          back.bcs == dict(x_lo='reflect', x_hi='transmit',
                           y_lo='reflect', y_hi='transmit'), str(back.bcs))
    check('an unknown kind is a validation error',
          any("unknown kind" in e for e in validate_case(
              case2d(bcs=dict(x_lo='reflect', x_hi='nonsense',
                              y_lo='reflect', y_hi='transmit'))).errors))

    print("\nT50 masks and distances")
    bcs = dict(x_lo='reflect', x_hi='terminate',
               y_lo='transmit', y_hi='reflect')
    m = geometry.terminate_edge_mask((4, 4), bcs)
    # the corner cells of the terminate side belong to it too, so the
    # other three sides are checked away from that shared corner
    check('only the terminate side is in the mask',
          m[-1, :].all() and not m[0, :].any()
          and not m[:-1, 0].any() and not m[:-1, -1].any(),
          str(m.astype(int)))
    check('a transmit-only case terminates nowhere',
          not geometry.terminate_edge_mask(
              (4, 4), dict(x_lo='transmit', x_hi='transmit',
                           y_lo='transmit', y_hi='transmit')).any())
    # the wave leaves through transmit AND terminate: same distance set
    # the pre-T50 'open' gave, so snapshots/progress do not move
    legacy = geometry.stop_dists_2d(2.0, 2.0, 0.5, 0.5,
                                    dict(x_lo='wall', x_hi='open',
                                         y_lo='open', y_hi='open'))
    new = geometry.stop_dists_2d(2.0, 2.0, 0.5, 0.5,
                                 dict(x_lo='reflect', x_hi='transmit',
                                      y_lo='terminate', y_hi='transmit'))
    check('stop distances count every non-reflecting side',
          sorted(legacy) == sorted(new), f'{legacy} vs {new}')
    check('a fully reflecting box falls back to the far corner',
          len(geometry.stop_dists_2d(
              2.0, 2.0, 0.5, 0.5,
              dict(x_lo='reflect', x_hi='reflect',
                   y_lo='reflect', y_hi='reflect'))) == 1)

    print("\nT50 end to end (2D)")
    res_t, log = quiet(solve_2d, case2d(
        bcs=dict(x_lo='reflect', x_hi='terminate',
                 y_lo='reflect', y_hi='transmit')), ConsoleHooks(2))
    check('a terminate side ends the run',
          'terminate boundary' in res_t.stop_reason, res_t.stop_reason)
    t_term = res_t.meta['final_state']['t']
    res_x, log_x = quiet(solve_2d, case2d(t_end=t_term * 3.0),
                         ConsoleHooks(2))
    check('the same run with transmit only does NOT stop there',
          res_x.meta['final_state']['t'] > t_term * 2.0,
          f"{res_x.meta['final_state']['t']:.3e} vs {t_term:.3e}")
    check('...it stops on the end time instead (T52)',
          res_x.stop_reason == 'end time reached', res_x.stop_reason)
    check('the banner says which stop condition is armed',
          'no terminate boundaries' in log_x
          and 'shock arrival at a terminate boundary' in log)
    check('validate_case warns when nothing can end the run',
          any('No terminate boundary' in w
              for w in validate_case(case2d()).warnings))
    check('...and stays quiet once an end time is set',
          not any('No terminate boundary' in w
                  for w in validate_case(case2d(t_end=1e-3)).warnings))

    print("\nT52 end time (1D)")
    r1, _ = quiet(solve_1d, Case1D(radius_m=1.0, charge_kg=0.2,
                                   cell_size_m=0.005, n_snapshots=1,
                                   t_end=2e-4), ConsoleHooks(1))
    check('1D honours t_end', r1.stop_reason == 'end time reached',
          r1.stop_reason)

    print("\nT60 the 1D outer boundary")

    def one_d(kind):
        c = Case1D(radius_m=1.0, charge_kg=0.5, cell_size_m=0.005,
                   n_snapshots=1, bc_outer=kind, t_end=1.2e-3,
                   gauge_radii=[0.98])
        r, log = quiet(solve_1d, c, ConsoleHooks(1))
        return r, log, float(r.gauges['pressures'][0].max() - P_AIR)

    r_t, log_t, pk_t = one_d('terminate')
    check('terminate ends the run at the outer face, as 1D always did',
          r_t.stop_reason.startswith('shock arrived at outer boundary'),
          r_t.stop_reason)
    r_x, log_x, pk_x = one_d('transmit')
    check('transmit lets the wave leave and runs to the end time',
          r_x.stop_reason == 'end time reached', r_x.stop_reason)
    r_r, log_r, pk_r = one_d('reflect')
    check('reflect also runs on', r_r.stop_reason == 'end time reached',
          r_r.stop_reason)
    # the physics, not just the plumbing: a wall one cell out doubles
    # and more, a transmissive end does not
    check('a reflecting end really reflects (wall overshoot)',
          pk_r > 1.3 * pk_x,
          f'reflect {pk_r/1e3:.0f} kPa vs transmit {pk_x/1e3:.0f} kPa')
    check('the banner names the kind and the stop condition it implies',
          'Outer boundary  : reflect' in log_r
          and 'does not stop it' in log_r
          and 'shock arrival at r' in log_t)

    print("\nT51 trigger gauge")
    check('the actions', TRIGGER_ACTIONS
          == ('terminate', 'remap', 'remap+terminate'))
    hooks = ConsoleHooks(2)
    with contextlib.redirect_stdout(io.StringIO()):
        check('a 1-based number becomes an index',
              trigger_index(2, 3, hooks) == 1
              and trigger_index(None, 3, hooks) is None
              and trigger_index(0, 3, hooks) is None
              and trigger_index(4, 3, hooks) is None)

    res, _ = quiet(solve_2d, case2d(trigger_gauge=1, t_end=5e-3),
                   ConsoleHooks(2))
    check('terminate: the run stops at the gauge',
          res.stop_reason.startswith('trigger gauge G1 reached'),
          res.stop_reason)
    t_trig = res.meta['trigger']['t']
    check('the trigger record carries t, the number and the point',
          res.meta['trigger']['gauge'] == 1
          and len(res.meta['trigger']['point']) == 2 and t_trig > 0)

    res2, _ = quiet(solve_2d, case2d(trigger_gauge=1, t_end=5e-3,
                                     trigger_action='remap',
                                     profile_file='unused.npz'),
                    ConsoleHooks(2))
    check('remap: the run carries on past the gauge',
          res2.stop_reason == 'end time reached', res2.stop_reason)
    check('...and the captured state is the arrival instant',
          abs(res2.meta['trigger_state']['t'] - t_trig) < 1e-12,
          f"{res2.meta['trigger_state']['t']} vs {t_trig}")
    check('no trigger_state without a remap action',
          'trigger_state' not in res.meta)

    tmp = tempfile.mkdtemp(prefix='blastlab_trig_')
    out = os.path.join(tmp, 'remap.npz')
    from blastlab.core.profiles import load_profile_2d
    from blastlab.solvers.jobs import write_trigger_remap as _write_trigger_remap
    c2 = case2d(trigger_gauge=1, trigger_action='remap', t_end=5e-3,
                trigger_file=out)
    with contextlib.redirect_stdout(io.StringIO()):
        _write_trigger_remap(c2, res2)
    check('the remap file is written at the trigger instant',
          os.path.exists(out)
          and abs(load_profile_2d(out)['t'] - t_trig) < 1e-9)

    res3, log3 = quiet(solve_2d, case2d(trigger_gauge=9, t_end=2e-4),
                       ConsoleHooks(2))
    check('a gauge number that does not exist warns and runs on',
          '[warn] Trigger gauge G9' in log3
          and res3.stop_reason == 'end time reached')

    # T63: 1D has no trigger gauge at all. The 1D hand-off is the run's
    # own profile output, and bc_outer='terminate' ends the run at the
    # end of the sector - the per-gauge trigger only duplicated those in
    # the native solver and did nothing whatsoever on blastFoam.
    check('Case1D carries no trigger fields',
          not any(hasattr(Case1D(), f) for f in
                  ('trigger_gauge', 'trigger_action', 'trigger_file')))
    r1t, _ = quiet(solve_1d, Case1D(radius_m=1.0, charge_kg=0.2,
                                    cell_size_m=0.005, n_snapshots=1,
                                    gauge_radii=[0.3, 0.6]),
                   ConsoleHooks(1))
    check('a 1D run records no trigger in its meta',
          not any(k in r1t.meta for k in
                  ('trigger', 'trigger_profile', 'trigger_gauge')))
    old1d = dict(case_to_dict(Case1D(radius_m=1.0, gauge_radii=[0.3])),
                 version=10, trigger_gauge=1,
                 trigger_action='remap+terminate', trigger_file='x.txt')
    c_old = case_from_dict(old1d)
    check('a pre-T63 1D case file still loads, without the trigger keys',
          c_old.radius_m == 1.0 and c_old.gauge_radii == [0.3]
          and not hasattr(c_old, 'trigger_gauge'))

    print("\nT51 validation")
    check('remap is refused in 3D',
          any('not available in 3D' in e for e in validate_case(
              Case3D(gauges=[(1., 1., 1.)], trigger_gauge=1,
                     trigger_action='remap')).errors))
    check('remap is refused on a planar 2D case',
          any('axisymmetric' in e for e in validate_case(
              case2d(geometry='planar', trigger_gauge=1,
                     trigger_action='remap')).errors))
    check('remap with nowhere to write is refused',
          any('remap filename' in e for e in validate_case(
              case2d(trigger_gauge=1, trigger_action='remap')).errors))
    check('an out-of-range number is refused',
          any('the case has 2 gauge(s)' in e for e in validate_case(
              case2d(trigger_gauge=5)).errors))
    check('the trigger round-trips through a case file',
          case_from_dict(case_to_dict(case2d(
              trigger_gauge=2, trigger_action='remap+terminate',
              trigger_file='x.npz'))).trigger_action == 'remap+terminate')

    print("\nT51 on the blastFoam backend (no WSL)")
    from blastlab.solvers.foam import backend as fb
    import inspect
    # the trigger is armed in the run function but the meta is built in
    # finalize_*, a DIFFERENT function: a run that stopped raised
    # NameError until the two were threaded together
    for name in ('finalize_2d', 'finalize_3d'):
        params = inspect.signature(getattr(fb, name)).parameters
        check(f'{name} takes the trigger state',
              'trig_k' in params and 'trigger' in params
              and params['trig_k'].default is None
              and params['trigger'].default is None)
    for name in ('solve_2d_foam', 'solve_3d_foam'):
        src = inspect.getsource(getattr(fb, name))
        check(f'{name} passes the trigger on to finalize',
              'trig_k=trig_k' in src and 'trigger=trigger' in src)

    c2f = case2d(trigger_gauge=2)
    xc = np.linspace(0.015, 0.585, 20)
    yc = np.linspace(0.015, 1.185, 40)
    k, cell = fb._trigger_cells(c2f, (xc, yc), (20, 40))
    check('the foam grid snaps the trigger gauge to a cell',
          k == 1 and len(cell) == 2
          and abs(xc[cell[0]] - 0.5) < 0.03, f'{k} {cell}')
    check('no trigger gauge -> nothing armed',
          fb._trigger_cells(case2d(), (xc, yc), (20, 40)) == (None, None))
    check('an out-of-range one is ignored',
          fb._trigger_cells(case2d(trigger_gauge=9),
                            (xc, yc), (20, 40)) == (None, None))

    class _Loop:
        stop_requested = False

        def request_stop(self, reason):
            self.stop_requested = reason

    class _Hooks:
        def __init__(self):
            self.msgs = []

        def log(self, m):
            self.msgs.append(m)

    lp = _Loop()
    rec = fb._trigger_fire(lp, _Hooks(), c2f, 1, 1.5e-4, 1.2e5)
    check('firing it records t/gauge/point and asks for the stop',
          rec['gauge'] == 2 and rec['action'] == 'terminate'
          and lp.stop_requested == 'trigger gauge G2 reached', str(rec))
    lp2 = _Loop()
    fb._trigger_fire(lp2, _Hooks(),
                     case2d(trigger_gauge=2, trigger_action='remap'),
                     1, 1.5e-4, 1.2e5)
    check("a plain 'remap' action does not stop the foam run",
          lp2.stop_requested is False)

    print("\nreplay-frame memory budget")
    from blastlab.solvers.hooks import FRAME_MEM_BUDGET, frame_budget

    class _Log:
        def __init__(self):
            self.msgs = []

        def log(self, m):
            self.msgs.append(m)

    check('off stays off', frame_budget(0, 640 * 640, None) == 0)
    check('a small grid is not capped',
          frame_budget(150, 80 * 60, None) == 150)
    # the owner's run: a 640^2 AMR display grid at 150 frames held up to
    # 614 MB (the recorder grew to 2x record_frames), and the ingest then
    # failed allocating 400 KiB
    lg = _Log()
    n_amr = frame_budget(150, 640 * 640, lg, amr=True)
    check('a 640^2 AMR run is capped to fit the budget',
          n_amr < 150 and 5 * 640 * 640 * n_amr <= FRAME_MEM_BUDGET,
          f'{n_amr} frames')
    check('...and says so once', len(lg.msgs) == 1
          and 'Replay frames reduced' in lg.msgs[0], str(lg.msgs))
    check('an AMR run costs more per frame than a plain one',
          frame_budget(500, 640 * 640, None, amr=True)
          < frame_budget(500, 640 * 640, None))
    check('even an absurd grid keeps a few frames',
          frame_budget(150, 4096 * 4096, None, amr=True) >= 8)
    check('no note when nothing is capped',
          not _Log().msgs and frame_budget(10, 640 * 640, _Log()) == 10)

    # the recorders must thin AT record_frames, never at twice it
    import inspect
    from blastlab.solvers import solver2d, solver3d
    from blastlab.solvers.foam import backend as fbk
    for mod in (solver2d, solver3d, fbk):
        src = inspect.getsource(mod)
        check(f'{mod.__name__.split(".")[-1]} never holds 2x the frames',
              '2 * record_frames' not in src
              and 'len(frame_p) > record_frames' in src)

    print("\nT53 gauge markers")
    meta2 = dict(gauges=[(0.25, 0.6), (0.5, 0.6)], dx=0.03)
    pts = plots.gauge_points(meta2)
    check('2D: every gauge, numbered from 1',
          pts == [(1, 0.25, 0.6), (2, 0.5, 0.6)], str(pts))
    meta3 = dict(gauges=[(1.0, 2.0, 3.0), (1.0, 9.0, 3.0)], dx=0.5,
                 x_c=np.array([1.0]), y_c=np.array([2.0]),
                 z_c=np.array([3.0]))
    on_plane = plots.gauge_points(meta3, (slice(None), 0, slice(None)))
    check('3D: only the gauges the plane cuts',
          on_plane == [(1, 1.0, 3.0)], str(on_plane))
    check('no gauges -> nothing to draw', plots.gauge_points({}) == [])

    from matplotlib.figure import Figure
    ax = Figure().add_subplot()
    arts = plots.add_gauge_markers(ax, pts, trigger=2)
    check('two artists per gauge (marker + label)', len(arts) == 4)
    check('the trigger gauge is marked', any(
        getattr(a, 'get_text', lambda: '')() == 'G2*' for a in arts))

    # the same helper reaches the run's own animation
    from blastlab.output import animation as anim_mod
    import inspect
    src = inspect.getsource(anim_mod.write_animation)
    check('write_animation draws them', 'add_gauge_markers' in src)
    check('the live pane draws them', 'add_gauge_markers' in
          open(os.path.join(HERE, '..', 'gui', 'run_panel.py'),
               encoding='utf-8').read())

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()
    print()
    print('BC / TRIGGER: ' + ('PASS' if not FAILS
                              else f'FAIL ({len(FAILS)}): '
                                   + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)
