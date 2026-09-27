"""Throwaway QA harness, part 2: the matrix tooltips in the real Qt window.

The workstation session is locked during this pass (ImageGrab fails with
"screen grab failed"), so a real cursor cannot hover. Each tooltip is shown
through QToolTip.showText at the label - the call Qt's own hover handler
makes with the widget's toolTip() - and the tooltip window itself is
grabbed. Dark and light.
Run:  python -u qa_qt_tips.py <shots dir>
"""
import json
import os
import sys
import time
import traceback

REPO = r'C:\Users\rotem.ofek\OneDrive - Technion\BlastFoam'
sys.path.insert(0, REPO)
os.environ.pop('QT_QPA_PLATFORM', None)
assert os.environ.get('BLASTLAB_SETTINGS')
SHOTS = sys.argv[1]
OUT = {}


def main():
    from PySide6.QtCore import QEvent, QPoint, Qt
    from PySide6.QtGui import QHelpEvent
    from PySide6.QtWidgets import QApplication, QLabel, QToolTip
    app = QApplication.instance() or QApplication(['blastlab'])
    from blastlab.ui import theme
    theme.apply(app, 'dark')
    from blastlab.ui.app import MainWindow
    from blastlab.core.case import Case3D, Case2D

    def pump(s=0.3):
        end = time.monotonic() + s
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.01)

    win = MainWindow()
    win.resize(1100, 720)
    win.show()
    pump(2.0)
    win._show('setup')
    for mode_name in ('dark', 'light'):
        win._mode_switch.setChecked(mode_name == 'dark')
        pump(0.8)
        for dim, C in ((3, Case3D), (2, Case2D)):
            win.setup.set_case(C(solver='blastfoam'))
            pump(1.0)
            f = win.setup.form
            grid = f.widgets['vtk_fields']
            win.setup._scroll.ensureWidgetVisible(grid, 0, 0)
            pump(0.5)
            for lbl in grid.findChildren(QLabel):
                tip = lbl.toolTip()
                if not tip:
                    continue
                # the event Qt's hover machinery sends: QEvent.ToolTip
                pos = QPoint(lbl.width() // 2, lbl.height() // 2)
                ev = QHelpEvent(QEvent.ToolTip, pos, lbl.mapToGlobal(pos))
                QApplication.sendEvent(lbl, ev)
                pump(0.6)
                tw = None
                for w in QApplication.topLevelWidgets():
                    if w.metaObject().className() == 'QTipLabel' and w.isVisible():
                        tw = w
                shown = QToolTip.text()
                key = f'{mode_name}_{dim}d_{lbl.text()}'
                OUT[key] = dict(label=lbl.text(), tip=tip, shown=shown,
                                visible=tw is not None,
                                size=(tw.width(), tw.height()) if tw else None)
                if tw is not None and lbl.text() in ('Gauge', 'Sect.', 'Obst.',
                                                     'Vol.', 'Domain',
                                                     'Peak overpr.', 'Products'):
                    safe = lbl.text().replace('.', '').replace(' ', '_')
                    tw.grab().save(os.path.join(
                        SHOTS, f'qt_tip_{mode_name}_{dim}d_{safe}.png'))
                    # the label and the tip together, as a user sees them
                QToolTip.hideText()
                pump(0.2)
            # also the locked Gauge box (disabled widgets get no tooltip
            # events in Qt): does it explain itself?
            from PySide6.QtWidgets import QCheckBox
            locked = [b for b in grid.findChildren(QCheckBox) if not b.isEnabled()]
            OUT[f'{mode_name}_{dim}d_locked_box_tooltip'] = locked[0].toolTip()
            OUT[f'{mode_name}_{dim}d_greyed_ms_tooltip'] = f.widgets['vtk_v_steps'].toolTip()
    # the Outputs card right edge at 1280 (compare with the VTK card)
    win._mode_switch.setChecked(True)
    win.resize(1280, 840)
    pump(0.8)
    win.setup.set_case(Case3D(solver='blastfoam'))
    pump(1.0)
    f = win.setup.form
    vp = win.setup._scroll.viewport()
    edges = {}
    for t, card in f.cards.items():
        if card.isHidden():
            continue
        tl = card.mapTo(vp, QPoint(0, 0))
        edges[t] = dict(left=tl.x(), right=tl.x() + card.width(),
                        viewport_w=vp.width())
    OUT['card_edges_1280'] = edges
    win.close()
    pump(0.5)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        traceback.print_exc()
    with open(os.path.join(SHOTS, 'qt_tips.json'), 'w', encoding='utf-8') as fh:
        json.dump(OUT, fh, indent=1)
    print(json.dumps(OUT, indent=1))
