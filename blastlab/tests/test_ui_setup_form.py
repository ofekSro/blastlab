"""The Qt Setup form: the spec covers every field, cases round-trip in
both solver modes, bad fields are all reported and marked, the solver
mode and the AMR sub-group hide rows without losing values, and the
axisymmetric hook relabels and pins the burst to the axis.

Headless: offscreen Qt, no window shown, no solver run."""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.ui.testing import ensure_qapp, pump          # noqa: E402

app = ensure_qapp()

from blastlab.core.case import (Case1D, Case2D,            # noqa: E402
                                Case3D, validate_case)
from blastlab.ui import setup_spec                          # noqa: E402
from blastlab.ui.case_form import CaseForm                  # noqa: E402
from blastlab.ui.setup_panel import STATUS_MAX_H, SetupPanel  # noqa: E402

FAIL = []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        FAIL.append(name)


def form(dim, mode='blastfoam'):
    f = CaseForm(dim, mode=mode)
    f.resize(900, 700)
    f.show()
    pump(40)
    return f


def main():
    print("\nS1: the spec and the form agree, per dimension")
    for d in (1, 2, 3):
        f = form(d)
        names = set(f.v) | set(f.points)
        want = {x.name for x in setup_spec.fields(d)}
        check(f"dim {d}: every spec field exists",
              want == names, str(sorted(want ^ names)))
        check(f"dim {d}: defaults formatted as the Tk form did",
              f.v['cfl'].get() == {1: '0.5', 2: '0.4', 3: '0.3'}[d],
              f.v['cfl'].get())
    f1, f2, f3 = form(1), form(2), form(3)
    check("1D has no trigger card and no obstacles",
          'trigger_gauge' not in f1.v and 'obstacles' not in f1.points)
    check("only 3D has Lz, cz and the extra charges",
          'Lz' in f3.v and 'Lz' not in f2.v
          and 'extra_charges' in f3.points
          and 'extra_charges' not in f2.points)
    check("only 2D has geometry",
          'geometry' in f2.v and 'geometry' not in f3.v)
    check("3D drops the remap trigger action",
          all('remap' not in a
              for a in setup_spec.by_name(3)['trigger_action'].values))

    print("\nS2: a fresh form validates clean (UX-01)")
    for d in (2, 3):
        for mode in ('native', 'blastfoam'):
            f = form(d, mode)
            rep = validate_case(f.get_case())
            no_bc = [w for w in rep.warnings if 'terminate' in w.lower()]
            check(f"dim {d} {mode}: no errors", not rep.errors,
                  str(rep.errors))
            check(f"dim {d} {mode}: no 'no terminate boundary' warning",
                  not no_bc, str(no_bc))

    print("\nS3: set_case -> get_case round trip, both modes")
    for d, cls in ((1, Case1D), (2, Case2D), (3, Case3D)):
        for mode in ('native', 'blastfoam'):
            f = form(d, mode)
            src = cls()
            f.set_case(src)
            pump(20)
            back = f.get_case()
            diffs = []
            for key, want in vars(src).items():
                if key in ('solver', 'amr_refine', 'amr_unrefine'):
                    # solver is the form's own mode; the two AMR
                    # coefficients are substituted with the form's
                    # defaults while AMR is off, exactly as in Tk
                    continue
                got = getattr(back, key, None)
                same = (abs(want - got) < 1e-12
                        if isinstance(want, float)
                        and isinstance(got, float) else want == got)
                if not same:
                    diffs.append(f'{key}: {want!r} -> {got!r}')
            check(f"dim {d} {mode}: round trips", not diffs,
                  '; '.join(diffs[:3]))

    print("\nS3b: an optional path that is None stays None")
    # It did not. `gauge_file` alone lacked the `or None` / `or ''` its
    # neighbours had, so None went into the widget as the string 'None'
    # and came back as one - and the writer then used it as a FILE NAME.
    # Every finished run left a file called "None" in the working
    # directory. Its neighbours were always right, which is why it took
    # a stray file in `git status` to notice.
    import blastlab.core.case as case_mod
    blank = {1: case_mod.Case1D(gauge_radii=[0.5], gauge_file=None,
                                profile_file=None),
             2: case_mod.Case2D(gauges=[(1.0, 0.4)], gauge_file=None,
                                profile_file=None, anim_file=None),
             3: case_mod.Case3D(gauges=[(1.0, 0.4, 0.3)],
                                gauge_file=None, anim_file=None)}
    for d, case in blank.items():
        f = form(d)
        f.set_case(case)
        pump(5)
        back = f.get_case()
        bad = [(k, getattr(back, k))
               for k in ('gauge_file', 'profile_file', 'anim_file')
               if hasattr(case, k) and getattr(case, k) is None
               and getattr(back, k, None) is not None]
        check(f'dim {d}: no optional path comes back as a string',
              not bad, str(bad))

    print("\nS4: every bad field is reported, and marked")
    f = form(2)
    f.v['Lx'].set('abc')
    f.v['cell'].set('')
    try:
        f.get_case()
        lines = []
    except ValueError as exc:
        lines = [ln for ln in str(exc).splitlines() if ln.strip()]
    check("two bad fields -> two messages", len(lines) == 2, str(lines))
    check("each message names its field",
          any("'Lx'" in ln for ln in lines)
          and any("'cell size'" in ln for ln in lines), str(lines))
    check("both are red-bordered", f.bad == {'Lx', 'cell'},
          str(sorted(f.bad)))
    f.v['Lx'].set('4')
    try:
        f.get_case()
        lines = []
    except ValueError as exc:
        lines = [ln for ln in str(exc).splitlines() if ln.strip()]
    check("fixing one leaves one", len(lines) == 1, str(lines))
    check("and clears that field's mark", f.bad == {'cell'},
          str(sorted(f.bad)))
    f.v['cell'].set('0.025')
    f.get_case()
    check("all clean clears every mark", f.bad == set(), str(sorted(f.bad)))
    f = form(2)
    f.v['n_snapshots'].set('2.7')
    try:
        f.get_case()
        msg = ''
    except ValueError as exc:
        msg = str(exc)
    check("a fractional integer is refused, not truncated",
          'whole number' in msg, msg)
    f = form(2)
    f.v['Lx'].set('inf')
    try:
        f.get_case()
        msg = ''
    except ValueError as exc:
        msg = str(exc)
    check("inf/nan are refused as geometry", 'finite' in msg, msg)

    print("\nS5: the reconstruction order can no longer raise "
          "out of get_case")
    for raw in ('', 'two', '1 (Godunov)', '2 (MUSCL)'):
        f = form(2, 'native')
        f.v['order'].set(raw)
        try:
            case = f.get_case()
            got, err = case.order, ''
        except ValueError as exc:
            got, err = None, str(exc)
        except Exception as exc:                 # the old IndexError
            got, err = None, f'{type(exc).__name__}: {exc}'
            FAIL.append('order raised')
        if raw in ('1 (Godunov)', '2 (MUSCL)'):
            check(f"order {raw!r} -> {raw[0]}", got == int(raw[0]), str(got))
        else:
            check(f"order {raw!r} is a field error, not a crash",
                  got is None and 'order' in err, err)
    f = form(2, 'blastfoam')
    f.v['order'].set('')
    f.v['eos'].set('JWL')
    case = f.get_case()
    check("blastFoam ignores order/eos instead of blocking the run",
          case.order == 1 and case.eos == 'idealGas',
          f'order={case.order} eos={case.eos}')

    print("\nS6: solver mode hides rows and whole cards, keeps values")
    f = form(2, 'native')
    check("native hides the blastFoam rows",
          not f.row_visible('activation')
          and not f.row_visible('afterburn')
          and not f.row_visible('n_procs'))
    check("native hides the blastFoam cards",
          not f.card_visible('Dynamic refinement (AMR)')
          and not f.card_visible('Refinement zones [m, level]'))
    check("native shows its own rows",
          f.row_visible('eos') and f.row_visible('order'))
    f.v['Lx'].set('6.25')
    f.v['n_procs'].set('7')
    f.set_mode('blastfoam')
    check("blastFoam shows its rows and cards",
          f.row_visible('activation')
          and f.card_visible('Dynamic refinement (AMR)'))
    check("blastFoam hides the native rows",
          not f.row_visible('eos') and not f.row_visible('order'))
    f.set_mode('native')
    check("nothing typed was lost across two switches",
          f.v['Lx'].get() == '6.25' and f.v['n_procs'].get() == '7')

    print("\nS7: the AMR sub-group follows the level count")
    f = form(2, 'blastfoam')
    check("AMR off: coefficients hidden, charge refinement shown",
          not f.row_visible('amr_refine')
          and not f.row_visible('amr_display_level')
          and f.row_visible('charge_refine'))
    f.v['amr_levels'].set('2')
    check("AMR on: coefficients shown, charge refinement hidden",
          f.row_visible('amr_refine')
          and f.row_visible('amr_display_level')
          and not f.row_visible('charge_refine'))
    case = f.get_case()
    check("and the case carries them", case.amr_levels == 2
          and case.charge_refine == 'global', str(case.amr_levels))
    f.v['amr_display_level'].set('auto')
    check("'auto' display level means None",
          f.get_case().amr_display_level is None)
    f.v['amr_levels'].set('0')
    check("back off again", not f.row_visible('amr_refine')
          and f.row_visible('charge_refine'))
    f = form(2, 'native')
    f.v['amr_levels'].set('3')
    check("a native case never carries AMR",
          f.get_case().amr_levels == 0)

    print("\nS8: the 2D axisymmetric hook")
    f = form(2)
    f.v['geometry'].set('planar')
    check("planar labels", f.label_text('Lx') == 'Lx [m]'
          and f.label_text('cx') == 'Burst x [m]', f.label_text('Lx'))
    check("planar charge is per metre of depth (UX-02)",
          f.label_text('charge') == 'Charge [kg TNT/m]',
          f.label_text('charge'))
    check("planar frees the burst x and the x_lo boundary",
          f.is_enabled('cx') and f.is_enabled('bc_x_lo'))
    f.v['cx'].set('1.5')
    f.v['geometry'].set('axisymmetric')
    check("axisym relabels to r/z",
          f.label_text('Lx') == 'Radius R [m]'
          and f.label_text('Ly') == 'Height Z [m]'
          and f.label_text('cx') == 'Burst r [m]'
          and f.label_text('cy') == 'Burst z [m]', f.label_text('Ly'))
    check("axisym charge is a plain mass",
          f.label_text('charge') == 'Charge [kg TNT]')
    check("axisym pins the burst to the axis and locks it",
          f.v['cx'].get() == '0' and not f.is_enabled('cx'),
          f.v['cx'].get())
    check("axisym forces the axis boundary to reflect and locks it",
          f.v['bc_x_lo'].get() == 'reflect'
          and not f.is_enabled('bc_x_lo'))
    check("the case agrees", f.get_case().center[0] == 0.0)

    print("\nS9: the point lists")
    arity = {1: dict(gauges=1), 2: dict(gauges=2, obstacles=4, zones=5,
                                        det_pts=2),
             3: dict(gauges=3, obstacles=6, zones=7, det_pts=3,
                     extra_charges=4)}
    for d, table in arity.items():
        f = form(d)
        for name, n in table.items():
            check(f"dim {d} {name} takes {n} numbers",
                  f.points[name]._arity == n, str(f.points[name]._arity))
    f = form(2)
    pl = f.points['obstacles']
    pl.entry.setText('1, 2, 3, 4')
    pl.add()
    pl.entry.setText('5 6 7 8')
    pl.add()
    check("commas and spaces both work",
          pl.get() == [(1.0, 2.0, 3.0, 4.0), (5.0, 6.0, 7.0, 8.0)],
          str(pl.get()))
    pl.entry.setText('1 2 3')
    check("the wrong count is refused", pl.add() is False and pl.count() == 2)
    check("and says how many are wanted",
          pl.hint.text() == 'expected 4 numbers (x0  x1  y0  y1)',
          pl.hint.text())
    pl.entry.setText('1 a 3 4')
    check("a non-number is refused", pl.add() is False)
    check("and names it", pl.hint.text() == 'not numbers: a', pl.hint.text())
    pl.tree.setCurrentItem(None)
    check("removing nothing is refused", pl.remove() is False)
    check("and says to select a row",
          pl.hint.text() == 'select a row in the list first', pl.hint.text())
    pl.tree.setCurrentItem(pl.tree.topLevelItem(0))
    pl.remove()
    check("removing a selected row works",
          pl.get() == [(5.0, 6.0, 7.0, 8.0)], str(pl.get()))
    check("at rest the hint lists the columns",
          pl.hint.text() == 'add a row: x0  x1  y0  y1', pl.hint.text())
    check("the rows reach the case",
          f.get_case().obstacles == [(5.0, 6.0, 7.0, 8.0)])
    f.points['zones'].set([(1, 2, 3, 4, 2.0)])
    check("a zone level is an int in the case",
          f.get_case().refine_zones == [(1.0, 2.0, 3.0, 4.0, 2)],
          str(f.get_case().refine_zones))

    print("\nS10: the validation report card")
    sp = SetupPanel()
    sp.resize(1200, 800)
    sp.show()
    pump(60)
    sp.show_report(['e1', 'e2', 'e3'], ['w1', 'w2'], ['n1'])
    rows = sp.report_rows()
    check("one row per message", len(rows) == 6, str(len(rows)))
    check("in error, warning, note order",
          [r[0] for r in rows] == ['error'] * 3 + ['warn'] * 2 + ['note'],
          str([r[0] for r in rows]))
    sp.show_report()
    check("an empty report reads Case OK",
          sp.report_rows() == [('ok', 'Case OK')], str(sp.report_rows()))
    sp.show_report([f'error {i}' for i in range(12)])
    pump(60)
    check("a long report is capped, not allowed to eat the form",
          sp._status_scroll.height() <= STATUS_MAX_H,
          f'{sp._status_scroll.height()} > {STATUS_MAX_H}')

    print("\nS11: the panel's own wiring")
    calls = []
    sp = SetupPanel(on_change=lambda: calls.append(1))
    sp.resize(1200, 800)
    sp.show()
    pump(60)
    check("starts on 2D", sp.dim == 2 and sp.form.dim == 2)
    n0 = len(calls)
    sp.set_dim(3)
    check("switching dimension swaps the form and notifies",
          sp.form.dim == 3 and len(calls) > n0)
    sp.set_case(Case1D())
    check("set_case adopts the dimension", sp.dim == 1)
    sp.set_case(Case2D(solver='blastfoam'))
    check("set_case adopts the solver", sp.solver == 'blastfoam'
          and sp.form.mode == 'blastfoam')
    check("get_case comes from the active form",
          sp.get_case().dim == 2)
    check("the harness accessors exist",
          sp.preview_kind() in ('1d', '2d', '3d', 'hint')
          and isinstance(sp.scroll_form(1.0), int)
          and isinstance(sp.report_rows(), list))

    pump(20)
    print("\n" + "=" * 50)
    if FAIL:
        print(f"FAILED: {len(FAIL)} check(s): {FAIL}")
        sys.exit(1)
    print("All Qt setup-form checks passed.")


if __name__ == '__main__':
    main()
