"""The exported animation's colour range.

It used to rescale on every frame, so the colour bar meant something
different in each one: no two frames could be compared and the shock
never appeared to decay. There are now three scales - one range for the
whole video (the default), the old per-frame behaviour, and a range you
pin - carried on the case so both export paths honour it.

No WSL, no GUI window: the core is plain numpy + matplotlib, and the two
forms are driven headlessly."""
import os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
os.environ.setdefault('MPLBACKEND', 'Agg')
os.environ.setdefault('BLASTLAB_SETTINGS',
                      os.path.join(tempfile.mkdtemp(prefix='blastlab_as_'),
                                   'settings.json'))

import numpy as np                                          # noqa: E402

from blastlab.core.case import (Case2D, Case3D,             # noqa: E402
                                case_from_dict, case_to_dict,
                                validate_case)
from blastlab.core.constants import (ANIM_SCALE_LABELS,      # noqa: E402
                                     ANIM_SCALES, P_AIR,
                                     anim_scale_from_label)
from blastlab.output import animation as anim                # noqa: E402

FAIL = []
RAN = []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")
    RAN.append(name)
    if not ok:
        FAIL.append(name)


def synthetic():
    """Five frames whose peak decays 500 -> 100 kPa, with one carved
    cell holding ambient."""
    solid = np.zeros((8, 6), bool)
    solid[2, 2] = True
    frames = []
    for k in range(5):
        p = P_AIR + (500e3 / (k + 1)) * np.ones((8, 6))
        p[solid] = P_AIR
        frames.append(p)
    meta = dict(frames=dict(times=[1e-4 * k for k in range(5)],
                            pressures=frames),
                x_face=np.linspace(0, 1, 9),
                y_face=np.linspace(0, 1, 7),
                solid=solid, Lx=1.0, Ly=1.0, charge=1.0,
                geometry='planar', gauges=[], dx=0.125)
    return meta, frames, solid


def graded():
    """Five frames of a decaying blast: a spatial profile that always
    reaches ~0 far from the burst, with a peak falling 500 -> 100 kPa.
    The uniform fixture above cannot serve here - autoscaling a flat
    field gives a 1 kPa band, so its frames differ for the wrong reason.
    """
    nx, ny = 24, 18
    r = np.hypot(*np.meshgrid(np.linspace(0, 3, nx),
                              np.linspace(0, 3, ny), indexing='ij'))
    frames = [P_AIR + (500e3 / (k + 1)) * np.exp(-r ** 2)
              for k in range(5)]
    return dict(frames=dict(times=[1e-4 * k for k in range(5)],
                            pressures=frames),
                x_face=np.linspace(0, 3, nx + 1),
                y_face=np.linspace(0, 3, ny + 1),
                solid=np.zeros((nx, ny), bool), Lx=3.0, Ly=3.0,
                charge=1.0, geometry='planar', gauges=[], dx=0.125)


def main():
    meta, frames, solid = synthetic()

    print("\nA1: one range covers every frame")
    got = anim.frame_clim(frames, solid)
    check("the range spans the whole run",
          got is not None and abs(got[0] - 100.0) < 1e-6
          and abs(got[1] - 500.0) < 1e-6, str(got))
    check("carved cells are excluded from the minimum",
          anim.frame_clim(frames, None)[0] == 0.0,
          str(anim.frame_clim(frames, None)))
    flat = [np.full((4, 4), P_AIR)]
    check("a dead-flat run still gets a usable range",
          anim.frame_clim(flat) == (0.0, 1.0),
          str(anim.frame_clim(flat)))
    check("no finite data -> no range",
          anim.frame_clim([np.full((3, 3), np.nan)]) is None)

    print("\nA2: resolving the scale, and every fallback")
    cases = [
        (('run', None), 'run', (100.0, 500.0)),
        (('frame', None), 'frame', None),
        (('manual', (0, 300)), 'manual', (0.0, 300.0)),
        (('manual', (300, 0)), 'run', (100.0, 500.0)),
        (('manual', None), 'run', (100.0, 500.0)),
        (('manual', ('a', 'b')), 'run', (100.0, 500.0)),
        (('bogus', None), 'run', (100.0, 500.0)),
        ((None, None), 'run', (100.0, 500.0)),
    ]
    for (scale, clim), want_used, want_range in cases:
        rng, used = anim.resolve_clim(meta, frames, solid, scale, clim)
        ok = used == want_used and (
            rng is None if want_range is None
            else rng is not None
            and abs(rng[0] - want_range[0]) < 1e-6
            and abs(rng[1] - want_range[1]) < 1e-6)
        check(f"scale={scale!r} clim={clim!r} -> {want_used}", ok,
              f'used={used} range={rng}')

    print("\nA3: the run's own choice travels in its meta")
    m = dict(meta, anim_scale='manual', anim_clim=(10.0, 40.0))
    rng, used = anim.resolve_clim(m, frames, solid)
    check("a Result exported later keeps the case's choice",
          used == 'manual' and rng == (10.0, 40.0), f'{used} {rng}')
    rng, used = anim.resolve_clim(m, frames, solid, scale='frame')
    check("an explicit argument still overrides it", used == 'frame'
          and rng is None, f'{used} {rng}')

    print("\nA4: the file is written in every mode, and says which")
    out = tempfile.mkdtemp(prefix='blastlab_anim_')
    gmeta = graded()
    # the manual range is deliberately far narrower than the data (peak
    # 500 kPa), so A4a can tell its pixels apart from 'run' at a glance
    for scale, clim in (('run', None), ('frame', None),
                        ('manual', (0.0, 50.0))):
        path = os.path.join(out, f'{scale}.gif')
        got = anim.write_animation(gmeta, path, fps=5, scale=scale,
                                   clim=clim)
        check(f"{scale}: a real file",
              got == path and os.path.getsize(path) > 1000,
              str(os.path.getsize(path) if os.path.exists(path) else 0))
    check("no frames recorded -> nothing written, no crash",
          anim.write_animation(dict(meta, frames=None),
                              os.path.join(out, 'none.gif')) is None)

    print("\nA5: the scale reaches the pixels, not just the clim")
    # the peak decays 500 -> 100 kPa. Under 'frame' every frame is
    # autoscaled to its own peak, so the last one looks like the first;
    # under 'run' it must be visibly cooler.
    from PIL import Image

    def frame_px(path, k):
        with Image.open(path) as im:
            im.seek(k)
            return np.asarray(im.convert('RGB'), dtype=np.int16)
    def spread(tag, i, j):
        return float(np.abs(frame_px(os.path.join(out, tag + '.gif'), i)
                            - frame_px(os.path.join(out, tag + '.gif'),
                                       j)).mean())

    def across(t1, t2, k):
        return float(np.abs(frame_px(os.path.join(out, t1 + '.gif'), k)
                            - frame_px(os.path.join(out, t2 + '.gif'),
                                       k)).mean())
    d_frame, d_run = spread('frame', 0, 4), spread('run', 0, 4)
    check("per-frame: the decayed frame still looks like the first",
          d_frame < 1.0, f'mean |diff| = {d_frame:.2f}')
    check("one range: the decayed frame is visibly cooler",
          d_run > 5.0, f'mean |diff| = {d_run:.2f}')
    check("so the two videos end on different pictures",
          across('frame', 'run', 4) > 5.0,
          f"mean |diff| = {across('frame', 'run', 4):.2f}")
    # 'run' (0..500) and 'manual' (0..50) share the plain bar label, so a
    # difference here is the pinned range reaching the pixels and nothing
    # else - the 'frame' comparison above also shifts the label
    check("a pinned range repaints the same frame",
          across('run', 'manual', 0) > 5.0,
          f"mean |diff| = {across('run', 'manual', 0):.2f}")

    print("\nA6: 3D animates a slice, so the mask must be sliced too")
    # the obstacle mask is (Nx,Ny,Nz) while the recorded frames are the
    # 2D live slice: pass the whole array and frame_clim silently ignores
    # it, putting the minimum back at zero
    n = 6
    solid3 = np.zeros((n, n, n), bool)
    solid3[:, 3, :] = True                  # the whole animated plane
    f3 = [P_AIR + 300e3 * np.ones((n, n)) for _ in range(3)]
    m3 = dict(frames=dict(times=[0.0, 1e-4, 2e-4], pressures=f3),
              x_face=np.linspace(0, 1, n + 1),
              y_face=np.linspace(0, 1, n + 1),
              z_face=np.linspace(0, 1, n + 1),
              x_c=np.linspace(0, 1, n), y_c=np.linspace(0, 1, n),
              z_c=np.linspace(0, 1, n),
              solid=solid3, Lx=1.0, Ly=1.0, Lz=1.0, charge=1.0,
              slice_axis='y', s0=3, j0=3, gauges=[], dx=1.0 / n)
    check("the full 3D mask does not match, so it is ignored",
          anim.frame_clim(f3, solid3) == (300.0, 301.0),
          str(anim.frame_clim(f3, solid3)))
    check("its slice matches, and hides every cell -> no range",
          anim.frame_clim(f3, solid3[:, 3, :]) is None)
    p3 = os.path.join(out, 'slice3d.gif')
    import contextlib, io, warnings
    buf = io.StringIO()
    with warnings.catch_warnings():
        warnings.simplefilter('error')       # an all-NaN nanmax warning
        with contextlib.redirect_stdout(buf):
            wrote = anim.write_animation(m3, p3, fps=5)
    check("a 3D run still writes its video",
          wrote == p3 and os.path.getsize(p3) > 1000)
    check("and says it fell back to rescaling, not 'fixed'",
          'rescaling per frame' in buf.getvalue(),
          repr(buf.getvalue()[:110]))
    # per-frame autoscale over a fully masked plane used to hand
    # matplotlib clim=(nan, nan): NaN fails the hi <= lo guard
    from blastlab.output.plots import overpressure_panel, set_frame
    from matplotlib.figure import Figure
    ax = Figure().add_subplot()
    blank = np.full((4, 4), True)
    qm = overpressure_panel(ax, np.linspace(0, 1, 5),
                            np.linspace(0, 1, 5), blank.shape)
    set_frame(qm, np.full((4, 4), P_AIR), blank)
    check("a fully masked frame gets a finite range, not NaN",
          all(np.isfinite(v) for v in qm.get_clim()),
          str(qm.get_clim()))

    print("\nA7: the case carries it, and validation guards it")
    for cls in (Case2D, Case3D):
        c = cls()
        check(f"{cls.__name__} defaults to one range per video",
              c.anim_scale == 'run' and c.anim_clim is None,
              f'{c.anim_scale} {c.anim_clim}')
        back = case_from_dict(case_to_dict(
            cls(anim_scale='manual', anim_clim=(5.0, 250.0))))
        check(f"{cls.__name__} round-trips through JSON as a tuple",
              back.anim_scale == 'manual'
              and back.anim_clim == (5.0, 250.0)
              and isinstance(back.anim_clim, tuple),
              f'{back.anim_scale} {back.anim_clim!r}')
    checks = [
        (dict(), [], False),
        (dict(anim_scale='run'), [], False),
        (dict(anim_scale='frame'), [], True),
        (dict(anim_scale='manual', anim_clim=(0, 300)), [], False),
        (dict(anim_scale='manual'), ['needs a minimum'], False),
        (dict(anim_scale='manual', anim_clim=(300, 0)),
         ['must be above'], False),
        (dict(anim_scale='manual', anim_clim=(0, float('inf'))),
         ['must be finite'], False),
        (dict(anim_scale='nope'), ['Unknown animation colour scale'],
         False),
    ]
    for kw, want_err, want_note in checks:
        rep = validate_case(Case2D(**kw))
        errs = [e for e in rep.errors
                if 'animation' in e.lower() or 'colour' in e.lower()]
        notes = [n for n in rep.notes if 'rescales' in n]
        ok = (len(errs) == len(want_err)
              and all(frag in ' '.join(errs) for frag in want_err)
              and bool(notes) == want_note)
        check(f"{kw or 'defaults'}", ok, f'errors={errs} notes={notes}')
    check("1D has no animation, so no scale to validate",
          not hasattr(__import__('blastlab.core.case',
                                 fromlist=['Case1D']).Case1D(),
                      'anim_scale'))

    print("\nA8: the run's export path passes it through")
    from blastlab.solvers import jobs

    class _Res:
        def __init__(self):
            self.meta = dict(meta)
            self.gauges = {}
    seen = {}
    real = jobs.write_animation
    jobs.write_animation = lambda m, fn, **kw: seen.update(
        dict(kw, target=fn, meta_scale=m.get('anim_scale')))
    try:
        res = _Res()
        jobs._animate(Case2D(anim_file='x.gif', anim_scale='manual',
                             anim_clim=(2.0, 20.0)), res)
        check("the case's scale reaches write_animation",
              seen.get('scale') == 'manual' and seen.get('clim')
              == (2.0, 20.0), str(seen))
        check("and is recorded in the Result's meta for a later export",
              res.meta['anim_scale'] == 'manual'
              and res.meta['anim_clim'] == (2.0, 20.0),
              f"{res.meta['anim_scale']} {res.meta['anim_clim']}")
        seen.clear()
        res = _Res()
        jobs._animate(Case2D(anim_file=None), res)
        check("no animation file -> nothing written", not seen)
        check("but the choice is still recorded",
              res.meta['anim_scale'] == 'run')
    finally:
        jobs.write_animation = real

    print("\nA9: both forms expose it the same way")
    from blastlab.ui.testing import ensure_qapp, pump
    ensure_qapp()
    from blastlab.ui.case_form import CaseForm as QtForm
    import customtkinter as ctk
    from blastlab.gui.forms import CaseForm as TkForm

    qt = QtForm(2, mode='native')
    qt.resize(900, 700)
    qt.show()
    pump(40)
    root = ctk.CTk()
    root.withdraw()
    tk = TkForm(root, 2, mode='native')
    root.update()

    def tk_visible(pair):
        return pair[1].winfo_manager() != ''

    try:
        check("both default to one range per video",
              qt.get_case().anim_scale == 'run'
              and tk.get_case().anim_scale == 'run')
        check("both hide the min/max boxes until they are needed",
              not qt.row_visible('anim_clim_min')
              and not tk_visible(tk._aclim_rows[0]))
        for f, setter in ((qt, lambda v: qt.v['anim_scale'].set(v)),
                          (tk, lambda v: tk.v['anim_scale'].set(v))):
            setter(ANIM_SCALE_LABELS['manual'])
        pump(40)
        root.update()
        check("both reveal them for a manual range",
              qt.row_visible('anim_clim_min')
              and tk_visible(tk._aclim_rows[0]))
        # a hidden Qt row must leave no gap behind: measure the card's
        # own sizeHint, not its height - the form under test is squeezed
        card = qt.cards['Outputs']
        h_manual = card.sizeHint().height()
        qt.v['anim_scale'].set(ANIM_SCALE_LABELS['run'])
        pump(40)
        h_run = card.sizeHint().height()
        check("and the card collapses again when they go",
              h_manual - h_run > 40 and not qt.row_visible('anim_clim_min'),
              f'{h_manual} -> {h_run} px')
        qt.v['anim_scale'].set(ANIM_SCALE_LABELS['manual'])
        pump(40)
        check("the Qt label and its box share a row without overlapping",
              all(qt.widgets[n].mapTo(qt, qt.widgets[n].rect().topLeft()).x()
                  - (qt.labels[n].mapTo(
                      qt, qt.labels[n].rect().topLeft()).x()
                     + qt.labels[n].width()) > 0
                  for n in ('anim_scale', 'anim_clim_min',
                            'anim_clim_max')))
        for f in (qt, tk):
            f.v['anim_clim_min'].set('7')
            f.v['anim_clim_max'].set('400')
        pump(20)
        root.update()
        check("both build the same case",
              qt.get_case().anim_clim == tk.get_case().anim_clim
              == (7.0, 400.0),
              f'{qt.get_case().anim_clim} vs {tk.get_case().anim_clim}')
        for f in (qt, tk):
            f.set_case(Case2D(anim_scale='frame'))
        pump(20)
        root.update()
        check("both round-trip a case back into the combo",
              qt.v['anim_scale'].get() == tk.v['anim_scale'].get()
              == ANIM_SCALE_LABELS['frame'],
              f"{qt.v['anim_scale'].get()!r} vs {tk.v['anim_scale'].get()!r}")
        check("a hidden bad range cannot block a run",
              (tk.v['anim_clim_max'].set('abc') or
               tk.get_case().anim_scale == 'frame'))
    finally:
        root.destroy()

    print("\nA10: the label mapping is total")
    for key in ANIM_SCALES:
        check(f"{key!r} <-> {ANIM_SCALE_LABELS[key]!r}",
              anim_scale_from_label(ANIM_SCALE_LABELS[key]) == key
              and anim_scale_from_label(key) == key)
    check("unknown text falls back to the default",
          anim_scale_from_label('whatever') == 'run')

    print("\n" + "=" * 50)
    if FAIL:
        print(f"FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}")
        sys.exit(1)
    print(f"ANIM SCALE: PASS ({len(RAN)} checks)")


if __name__ == '__main__':
    main()
