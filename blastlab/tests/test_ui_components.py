"""GUI-4 gate: the shared components of the redesign
(docs/gui-redesign-plan.md §2.5; blastlab/ui/components.py).

 C1  ToggleSwitch - programmatic setChecked and a synthesized click
     both flip isChecked() and emit toggled; Space toggles when
     focused; it IS a QCheckBox (the accessibility contract);
 C2  StatTile - set() shows value and caption; the value is Space
     Grotesk; the accent variant paints `accent_bg`; the bar clamps
     to [0, 1];
 C3  TreeRow - a click emits `clicked` with the row id; selection sets
     the dynamic property (and repolishes to `accent_bg`); the status
     mark switches ✓ / ! / ✗;
 C4  DockTabs - set() is silent, a user click emits `changed` and
     switches the stacked page, exactly one tab underlined;
 C5  Banner / HandoffCard - text set is text shown; the banner action
     fires its callback.

Plain script, offscreen, no pytest: `python test_ui_components.py`.
"""
import os
import sys

# the ✓ / ✗ marks are outside cp1252, the console's default here
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.ui.testing import ensure_qapp, pump          # noqa: E402

app = ensure_qapp()

from PySide6.QtCore import Qt                              # noqa: E402
from PySide6.QtTest import QTest                           # noqa: E402
from PySide6.QtWidgets import QCheckBox, QLabel            # noqa: E402

from blastlab.ui import theme                              # noqa: E402
from blastlab.ui.components import (Banner, DockTabs,      # noqa: E402
                                    HandoffCard, StatTile,
                                    ToggleSwitch, TreeRow)

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        FAIL.append(name)


def c1_toggle():
    print('\nC1: ToggleSwitch')
    sw = ToggleSwitch()
    sw.show()
    pump(30)
    got = []
    sw.toggled.connect(got.append)
    check('is a QCheckBox', isinstance(sw, QCheckBox))
    sw.setChecked(True)
    check('setChecked(True) flips and emits', sw.isChecked()
          and got == [True], str(got))
    QTest.mouseClick(sw, Qt.LeftButton)
    check('a click flips and emits', not sw.isChecked()
          and got == [True, False], str(got))
    sw.setFocus()
    pump(20)
    QTest.keyClick(sw, Qt.Key_Space)
    check('Space toggles when focused', sw.isChecked()
          and got == [True, False, True], str(got))
    sw.close()


def c2_tile():
    print('\nC2: StatTile')
    tile = StatTile('Cells')
    tile.set('368 k', 'cells')
    tile.resize(160, 80)
    tile.show()
    pump(30)
    texts = [w.text() for w in tile.findChildren(QLabel)]
    check("set('368 k','cells') shows both", '368 k' in texts
          and 'cells' in texts, str(texts))
    fam = tile.value.font().families()[0]
    check('value font is Space Grotesk', fam == 'Space Grotesk', fam)
    zt = StatTile('Z at gauges', variant='accent')
    zt.resize(160, 80)
    zt.show()
    pump(30)
    img = zt.grab().toImage()
    c = img.pixelColor(zt.width() // 2, zt.height() // 2)
    want = theme.qcolor('accent_bg')
    check('accent variant paints accent_bg',
          (abs(c.red() - want.red()) <= 3
           and abs(c.green() - want.green()) <= 3
           and abs(c.blue() - want.blue()) <= 3),
          f'{c.name()} vs {want.name()}')
    mem = StatTile('Memory', bar=True)
    mem.set('1.0', 'of 63', frac=1.7)
    check('bar clamps high to 1.0', mem.bar.frac() == 1.0,
          str(mem.bar.frac()))
    mem.set('1.0', frac=-2)
    check('bar clamps low to 0.0', mem.bar.frac() == 0.0,
          str(mem.bar.frac()))
    tile.close()
    zt.close()


def c3_treerow():
    print('\nC3: TreeRow')
    row = TreeRow('threat', '01', 'Threat', '1.0 kg TNT · z 2.0 m')
    row.resize(260, 46)
    row.show()
    pump(30)
    check('min height >= 44', row.minimumHeight() >= 44,
          str(row.minimumHeight()))
    got = []
    row.clicked.connect(got.append)
    QTest.mouseClick(row, Qt.LeftButton)
    check("click emits clicked('threat')", got == ['threat'], str(got))
    row.set_selected(True)
    pump(20)
    check("selected property set + repolished",
          row.property('selected') == 'true')
    img = row.grab().toImage()
    c = img.pixelColor(row.width() // 2, row.height() // 2)
    want = theme.qcolor('accent_bg')
    check('selected row paints accent_bg',
          (abs(c.red() - want.red()) <= 3
           and abs(c.green() - want.green()) <= 3
           and abs(c.blue() - want.blue()) <= 3),
          f'{c.name()} vs {want.name()}')
    row.set_selected(False)
    check('deselect clears the property',
          row.property('selected') == 'false')
    for status, mark in (('ok', '✓'), ('warn', '!'),
                         ('error', '✗')):
        row.set_status(status)
        check(f'status {status} shows {mark}', row.mark.text() == mark,
              row.mark.text())
    row.set_status(None)
    check('status None clears the mark', row.mark.text() == '')
    row.close()


def c4_docktabs():
    print('\nC4: DockTabs')
    tabs = DockTabs()
    pages = {}
    for name in ('Gauges', 'Checks', 'Log'):
        pages[name] = tabs.add(name, QLabel(f'{name} page'))
    tabs.resize(420, 200)
    tabs.show()
    pump(30)
    got = []
    tabs.changed.connect(got.append)
    tabs.set('Checks')
    check('set() switches silently', tabs.get() == 'Checks'
          and tabs.stack.currentWidget() is pages['Checks']
          and got == [], str(got))
    b_log = tabs._tabs['Log'][0]
    QTest.mouseClick(b_log, Qt.LeftButton)
    check("a click emits changed('Log') and switches",
          got == ['Log'] and tabs.get() == 'Log'
          and tabs.stack.currentWidget() is pages['Log'], str(got))
    checked = [n for n, (b, _w) in tabs._tabs.items() if b.isChecked()]
    check('exactly one underline active', checked == ['Log'],
          str(checked))
    tabs.close()


def c5_banner_handoff():
    print('\nC5: Banner and HandoffCard')
    fired = []
    ban = Banner('Result ready: wall_A', 'Open in 03 Results →',
                 on_action=lambda: fired.append(1))
    ban.resize(500, 60)
    ban.show()
    pump(30)
    check('banner shows its message',
          ban.message.text() == 'Result ready: wall_A')
    ban.set('Result ready: wall_B')
    check('banner set() updates',
          ban.message.text() == 'Result ready: wall_B')
    QTest.mouseClick(ban.action, Qt.LeftButton)
    check('banner action fires its callback', fired == [1], str(fired))
    card = HandoffCard('Hand-off in')
    card.set('handoff_1d_to_2d.txt', 'remapped onto the axis')
    card.resize(300, 100)
    card.show()
    pump(30)
    check('hand-off card shows the file',
          card.file.text() == 'handoff_1d_to_2d.txt')
    check('hand-off card shows the caption',
          card.caption.text() == 'remapped onto the axis'
          and card.caption.isVisibleTo(card))
    ban.close()
    card.close()


def main():
    for fn in (c1_toggle, c2_tile, c3_treerow, c4_docktabs,
               c5_banner_handoff):
        fn()
    # components must not drag VTK or pyplot into the process
    bad = [m for m in sys.modules
           if m.split('.')[0] in ('vtk', 'vtkmodules', 'pyvista',
                                  'pyvistaqt')
           or m == 'matplotlib.pyplot']
    print()
    check('no VTK / pyplot imported', not bad, str(bad))
    print(f'\nCOMPONENTS: {"PASS" if not FAIL else "FAIL " + str(FAIL)}')
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
