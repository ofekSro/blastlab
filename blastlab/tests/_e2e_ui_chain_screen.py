"""GUI-9: a native 1D -> 2D chain from the new Chain screen, end to end.

Batch docs/batches/2026-09-29-gui-chain.md, T3 (the 9a form; part 9b
adds the Run strip and the one Results entry with stage tabs). Every
step goes through what a user clicks:

  1. a tiny 2D case opened in 01 Setup (`_open_case`, the test_ui_chain
     C11 2D case saved to a scratch JSON);
  2. Chain; the `1D → 2D` route button clicked;
  3. stage 1 filled by **Load case…** (the C11 1D case,
     `dialogs.open_file` patched), stage 2 by **Copy from 01 Setup**,
     both clicked;
  4. after the debounce both cards read `● case OK`; a bad Lx typed into
     stage 2 turns card 2 to `● 1 error`, and back once fixed;
  5. **Run chain** clicked (`QTest.mouseClick`); the chain finishes;
  6. the model folder is test_ui_chain C11's layout (`.blastlab-model`,
     `1d`, `2d`, `handoff_1d_to_2d.txt`, `manifest.json`).

Real platform by default (QT_QPA_PLATFORM unset); `--offscreen` for a
CI-style run. Throwaway settings, `use_model`, no WSL. `--shots DIR`
saves a screenshot per step.

Run:  cd blastlab/tests && python _e2e_ui_chain_screen.py [--offscreen]
"""
import os
import sys
import tempfile
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
sys.path.insert(0, HERE)
os.environ.setdefault('MPLBACKEND', 'Agg')
os.environ.setdefault('BLASTLAB_SETTINGS', os.path.join(
    tempfile.mkdtemp(prefix='blastlab_ui_chainscreen_'), 'settings.json'))

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

FAIL = []
RAN = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    RAN.append(name)
    if not ok:
        FAIL.append(name)


def _arg(flag):
    if flag in sys.argv:
        i = sys.argv.index(flag)
        return sys.argv[i + 1] if i + 1 < len(sys.argv) else None
    return None


def main():
    if '--offscreen' not in sys.argv:
        os.environ.pop('QT_QPA_PLATFORM', None)
    from blastlab.ui.testing import ensure_qapp, pump, use_model
    ensure_qapp(offscreen='--offscreen' in sys.argv)
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from blastlab.models.case import Case1D, Case2D, save_case
    from blastlab.ui import dialogs
    from blastlab.ui.app import MainWindow

    shots = _arg('--shots')
    if shots:
        os.makedirs(shots, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix='blastlab_e2e_chainscreen_')
    one = os.path.join(tmp, 'stage1_1d.json')
    two = os.path.join(tmp, 'setup_2d.json')
    # test_ui_chain C11's two cases
    save_case(Case1D(radius_m=1.0, charge_kg=0.5, cell_size_m=0.01,
                     n_snapshots=1, t_end=3e-4, gauge_radii=[0.5]), one)
    save_case(Case2D(Lx=0.6, Ly=1.2, cell_size_m=0.03, charge=0.5,
                     center=(0.0, 0.6), n_snapshots=1, t_end=2e-4,
                     record_frames=0, gauges=[(0.25, 0.6)],
                     bcs=dict(x_lo='reflect', x_hi='transmit',
                              y_lo='reflect', y_hi='transmit')), two)

    crashes = []
    sys.excepthook = lambda *a: crashes.append(
        ''.join(traceback.format_exception(*a)))
    real = (dialogs.show_error, dialogs.ask_yes_no, dialogs.open_file,
            dialogs.notify_desktop)
    shown = []
    dialogs.show_error = lambda t, m, p=None: shown.append((t, m))
    dialogs.ask_yes_no = lambda *a, **k: True
    dialogs.open_file = lambda *a, **k: one
    dialogs.notify_desktop = lambda *a, **k: None
    win = MainWindow()

    def shot(name):
        if shots:
            pump(150)
            win.grab().save(os.path.join(shots, f'e2e9a_{name}.png'))

    try:
        win.set_solver('native')
        win.resize(1280, 840)
        win.show()
        pump(300)

        print('\nE1: a 2D case in 01 Setup')
        win._open_case(two)
        pump(500)
        check('Setup holds the 2D case', win.setup.dim == 2
              and win.current_case() is not None)
        # after Open case, which names the model after the file (GUI QA
        # C1): the chain's own model folder
        folder = use_model(win, 'CHAIN_E2E')

        print('\nE2: Chain, the 1D → 2D route clicked')
        QTest.mouseClick(win.topbar.nav_btns['chain'], Qt.LeftButton)
        pump(400)
        ch = win.chain
        check('the Chain screen is on', win.current_tab() == 'chain')
        QTest.mouseClick(ch.route_btns['12'], Qt.LeftButton)
        pump(400)
        check('route 1D → 2D, two cards',
              ch.route() == '12' and ch.checked() == [1, 2]
              and ch.cards[1].isVisible() and ch.cards[2].isVisible()
              and not ch.cards[3].isVisible())
        check('the top-bar link follows',
              win.topbar.nav_btns['chain'].text() == 'Chain 1D → 2D')
        shot('route12')

        print('\nE3: Load case… into stage 1, Copy from 01 Setup into 2')
        QTest.mouseClick(ch.cards[1], Qt.LeftButton)
        pump(200)
        QTest.mouseClick(ch.editors[1].load_btn, Qt.LeftButton)
        pump(400)
        c1 = ch.forms[1].get_case()
        check('stage 1 holds the loaded 1D case',
              c1.radius_m == 1.0 and c1.charge_kg == 0.5
              and c1.cell_size_m == 0.01 and not shown, str(shown))
        QTest.mouseClick(ch.cards[2], Qt.LeftButton)
        pump(200)
        btn = ch.editors[2].copy_btn
        check('Copy from 01 Setup is enabled', btn.isEnabled(),
              btn.toolTip())
        QTest.mouseClick(btn, Qt.LeftButton)
        pump(500)
        c2 = ch.forms[2].get_case()
        check('stage 2 holds the Setup case',
              c2.Lx == 0.6 and c2.Ly == 1.2 and c2.charge == 0.5
              and list(c2.gauges) == [(0.25, 0.6)], str(c2.gauges))
        check('both cards read ● case OK after the debounce',
              ch.cards[1].state_text() == '● case OK'
              and ch.cards[2].state_text() == '● case OK',
              ascii([ch.cards[d].state_text() for d in (1, 2)]))
        shot('loaded_copied')

        print('\nE4: a bad field, live')
        ch.forms[2].v['Lx'].set('abc')
        pump(500)
        check('card 2 reads ● 1 error', ch.cards[2].state_text()
              == '● 1 error', ascii(ch.cards[2].state_text()))
        shot('stage_error')
        ch.forms[2].v['Lx'].set('0.6')
        pump(500)
        check('and ● case OK once fixed',
              ch.cards[2].state_text() == '● case OK')

        print('\nE5: Run chain clicked')
        refusals = []
        ch.error_sink = lambda t, lines: refusals.append(list(lines))
        QTest.mouseClick(ch.run_btn, Qt.LeftButton)
        pump(300)
        check('the chain started', win.ctrl.running and not refusals,
              str(refusals))
        t0 = time.time()
        while win.ctrl.running and time.time() - t0 < 600:
            pump(100)
        print(f'    chain took {time.time() - t0:.1f} s')
        check('and finished without an error dialog',
              not win.ctrl.running and not shown, str(shown))
        shot('done')

        print('\nE6: the model folder')
        got = sorted(os.listdir(folder)) if os.path.isdir(folder) else []
        check('1d\\, 2d\\, the hand-off and the root manifest',
              got == ['.blastlab-model', '1d', '2d',
                      'handoff_1d_to_2d.txt', 'manifest.json'], str(got))
        names = [lbl for lbl, _d, _r in win._results]
        check('the stage results are named after the model',
              names == ['CHAIN_E2E - 1D', 'CHAIN_E2E - 2D'], str(names))
    finally:
        check('nothing raised', not crashes,
              crashes[0][-400:] if crashes else '')
        sys.excepthook = sys.__excepthook__
        (dialogs.show_error, dialogs.ask_yes_no, dialogs.open_file,
         dialogs.notify_desktop) = real
        win.close()
        pump(200)
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        return 1
    print(f'E2E UI CHAIN SCREEN: PASS ({len(RAN)} checks)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
