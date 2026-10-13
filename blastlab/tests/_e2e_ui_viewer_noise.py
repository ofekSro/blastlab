"""G14Q (batch 2026-10-12-gui-final, task D2): the Qt messages the 3D
viewer leaves behind on the real platform.

Every QA round since GUI-13 logged two `External WM_DESTROY received
for QWidgetWindow(name="viewWindow") / (name="QWidgetClassWindow"),
parent QStackedWidgetClassWindow` per scenario that had a 3D view. This
script walks the 3D path once - Setup preview, a native 3D run, the
Results 3D view, closing the window - with a Qt message handler that
records each message, the window it names and the step it came in.

Real platform only (QT_QPA_PLATFORM unset): the windows in question
only exist when the viewer child embeds a real render window.

    python blastlab/tests/_e2e_ui_viewer_noise.py

Exit 0 when no `External WM_DESTROY` was recorded at any step.

Recorded 2026-10-13 on the office PC: before the fix 2 messages, both at
`close`, window `viewWindow` (the host's placeholder) and
`QWidgetClassWindow` (its native mount), parent the host's stack - the
Setup preview's host, which `MainWindow.closeEvent` never shut down.
After it: 0.
"""
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
os.environ.setdefault('MPLBACKEND', 'Agg')

NOISE = 'External WM_DESTROY'
_NAME = re.compile(r'QWidgetWindow\([^,]+, name="([^"]*)"\)')


def main():
    os.environ.pop('QT_QPA_PLATFORM', None)
    from PySide6.QtCore import qInstallMessageHandler
    from blastlab.ui.testing import (answer_discard, ensure_qapp,
                                     private_settings, pump, use_model)
    private_settings()
    answer_discard()
    app = ensure_qapp(offscreen=False)
    step = ['start']
    seen = []

    def handler(mode, context, message):
        seen.append((step[0], str(message)))
        print(f'  [qt] ({step[0]}) {message}', flush=True)
    qInstallMessageHandler(handler)

    from blastlab.ui import theme
    from blastlab.ui.app import MainWindow
    from blastlab.viz3d import pyvista_available
    if not pyvista_available():
        print('pyvista is not installed - no 3D viewer, nothing to measure')
        sys.exit(1)
    theme.apply(app, 'dark')
    win = MainWindow(case_file=os.path.join(HERE, 'cases',
                                            'native_3d_small.json'))
    use_model(win)
    win.show()
    pump(400)

    def wait(cond, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            pump(50)
            if cond():
                return True
        return False

    def goto(tab):
        win._nav_btns[tab].click()
        pump(400)

    step[0] = 'preview'
    goto('setup')
    win.setup.update_preview(win.setup.get_case())
    got = wait(lambda: bool(win.setup.view3d._hwnd), 120)
    print(f'preview: render window {"embedded" if got else "MISSING"}')
    pump(800)

    step[0] = 'run'
    win._run_single()
    wait(lambda: not win.ctrl.running, 240)
    pump(800)
    print(f"run: {'finished' if '[run finished]' in win.run_panel.log_text() else 'DID NOT FINISH'}")

    step[0] = 'results3d'
    goto('results')
    rs = win.results
    rs.show_view('3D')
    pump(500)
    rs.open_3d()
    got = wait(lambda: rs.view3d._container is not None, 60)
    print(f'results 3D: {"embedded" if got else "MISSING"}')
    pump(1500)

    step[0] = 'tabs'
    for tab in ('setup', 'run', 'results', 'setup'):
        goto(tab)

    step[0] = 'close'
    win.close()
    pump(1500)
    step[0] = 'after'
    pump(300)

    noise = [(s, m) for s, m in seen if NOISE in m]
    print('\n' + '=' * 50)
    print(f'{NOISE} messages: {len(noise)}')
    for s, m in noise:
        names = _NAME.findall(m)
        print(f'  step {s}: window {names[0] if names else "?"}, '
              f'parent {names[1] if len(names) > 1 else "?"}')
    others = [(s, m) for s, m in seen if NOISE not in m]
    print(f'other Qt messages: {len(others)}')
    for s, m in others[:10]:
        print(f'  step {s}: {m[:160]}')
    sys.exit(1 if noise else 0)


if __name__ == '__main__':
    main()
