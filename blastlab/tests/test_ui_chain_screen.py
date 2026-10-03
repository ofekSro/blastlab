"""GUI-9 gate: the Chain screen (docs/gui-redesign-plan.md section 8,
board Chain; batch docs/batches/2026-09-29-gui-chain.md).

 S1  the routes (T1): `chain_route` is toolkit-free; the four routes,
     their keys and labels, `route_dims` / `route_key` refuse anything
     else; the hand-off names are `model_folder.handoff_paths`' own; the
     top bar's Chain link follows the route and still navigates.

Plain script, offscreen, throwaway settings, no window on screen:
    cd blastlab/tests && python test_ui_chain_screen.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
import traceback

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

from blastlab.ui.testing import ensure_qapp, pump             # noqa: E402

app = ensure_qapp()

FAIL = []
RAN = []
TMP = tempfile.mkdtemp(prefix='blastlab_chainscreen_')


def check(name, ok, detail=''):
    RAN.append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def raises(fn, *args):
    try:
        fn(*args)
    except ValueError:
        return True
    return False


# ── S1 ───────────────────────────────────────────────────────────────────
def s1_routes(win):
    from blastlab.services import model_folder
    from blastlab.ui import chain_route as cr
    print('\nS1: the routes')
    code = ('import sys, blastlab.ui.chain_route; '
            'print(sorted({m.split(".")[0] for m in sys.modules '
            'if m.split(".")[0] in ("PySide6", "shiboken6", "vtk", '
            '"vtkmodules", "pyvista")} | ({"pyplot"} if "matplotlib.pyplot" '
            'in sys.modules else set())))')
    out = subprocess.run([sys.executable, '-c', code], cwd=REPO,
                         capture_output=True, text=True, timeout=120)
    check('chain_route imports no toolkit (no Qt, VTK or pyplot)',
          out.returncode == 0 and out.stdout.strip() == '[]',
          (out.stdout + out.stderr).strip()[-200:])
    check('four routes, board order and labels',
          [(k, lbl, d) for k, lbl, d in cr.ROUTES]
          == [('123', '1D → 2D → 3D', (1, 2, 3)), ('13', '1D → 3D', (1, 3)),
              ('12', '1D → 2D', (1, 2)), ('23', '2D → 3D', (2, 3))])
    check('route_dims / route_key round-trip',
          all(cr.route_key(cr.route_dims(k)) == k for k, _l, _d in cr.ROUTES))
    check('route_dims refuses anything else',
          all(raises(cr.route_dims, k) for k in ('', '1', '32', '132', 'x')))
    check('route_key refuses a single stage and a reversed route',
          all(raises(cr.route_key, d) for d in ((1,), (2,), (3, 2), ())))
    target = model_folder.Target(runs_dir=TMP, model='M',
                                 folder=os.path.join(TMP, 'M'))
    want = {(1, 2): 'handoff_1d_to_2d.txt', (1, 3): 'handoff_1d_to_3d.txt',
            (2, 3): 'handoff_2d_to_3d.npz'}
    got = {e: cr.handoff_name(*e) for e in want}
    svc = {e: os.path.basename(model_folder.handoff_paths(target, e)[e])
           for e in want}
    check('the hand-off names are model_folder.handoff_paths\' own '
          '(plan §8.2)', got == want == svc, str(got))

    link = win.topbar.nav_btns['chain']
    check('the top bar starts on Chain 1D → 2D → 3D',
          link.text() == 'Chain 1D → 2D → 3D', link.text())
    seen = []
    win.chain.route_changed.connect(seen.append)
    win.chain.set_route('13')
    pump(20)
    check('set_route(13) -> the link reads Chain 1D → 3D',
          link.text() == 'Chain 1D → 3D', link.text())
    check('route_changed fired once with the key', seen == ['13'], str(seen))
    win.chain.set_route('13')
    check('the same route again fires nothing', seen == ['13'], str(seen))
    link.click()
    pump(30)
    check('and the link still navigates to the Chain screen',
          win.current_tab() == 'chain', str(win.current_tab()))
    win.chain.route_btns['12'].click()
    pump(20)
    check('a click on a route button is a route change too',
          win.chain.route() == '12' and link.text() == 'Chain 1D → 2D',
          f'{win.chain.route()} {link.text()}')
    win.chain.set_route('123')
    pump(20)
    check('and back to Chain 1D → 2D → 3D',
          link.text() == 'Chain 1D → 2D → 3D', link.text())
    win._show('setup')
    pump(20)


def main():
    from blastlab.ui.app import MainWindow
    crashes = []
    sys.excepthook = lambda *a: crashes.append(
        ''.join(traceback.format_exception(*a)))
    win = MainWindow()
    win.show()
    pump(200)
    try:
        s1_routes(win)
    finally:
        check('nothing raised', not crashes, crashes[0][-400:]
              if crashes else '')
        # the recorder is for Qt slots only: an exception out of a check
        # function still prints its traceback (61bfd56)
        sys.excepthook = sys.__excepthook__
        win.close()
        pump(100)
        shutil.rmtree(TMP, ignore_errors=True)
    bad = [m for m in sys.modules
           if m.split('.')[0] in ('vtk', 'vtkmodules', 'pyvista', 'pyvistaqt')
           or m == 'matplotlib.pyplot']
    check('no VTK / pyplot in the GUI process', not bad, str(bad[:3]))
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        return 1
    print(f'UI CHAIN SCREEN: PASS ({len(RAN)} checks)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
