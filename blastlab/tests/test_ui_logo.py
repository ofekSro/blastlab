"""GUI-2 gate: the QPainter-drawn BlastLab mark and app icon
(docs/gui-redesign-plan.md §3, board Logo_Final).

 L1  pixel test at 64 (dark): a front cell is #ff6a2b, a wake cell is
     orange at reduced alpha, an empty grid corner is transparent, a
     frame pixel is #e7eaee;
 L2  pixel test at 16: a step cell is #ff6a2b and the render carries no
     grid or wake pixels (front + frame colours only);
 L3  light mode: a front pixel is #e0501a;
 L4  app_icon() carries 16/24/32/48/64/128/256, and a MainWindow built
     offscreen has a non-null window icon;
 L5  the ELSL logo.gif is gone from the Qt window (no reference in
     blastlab/ui/), still present at the repo root for the Tk app, and
     the sidebar shows the BLASTLAB wordmark.

Plain script, offscreen, no pytest: `python test_ui_logo.py`.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, REPO)

from blastlab.ui.testing import ensure_qapp, pump          # noqa: E402

app = ensure_qapp()

from blastlab.ui import theme                              # noqa: E402

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        FAIL.append(name)


def px(img, x, y):
    c = img.pixelColor(x, y)
    return (c.red(), c.green(), c.blue(), c.alpha())


def near(a, b, tol=12):
    return all(abs(x - y) <= tol for x, y in zip(a[:3], b[:3]))


FRONT_D = (0xff, 0x6a, 0x2b)
FRONT_L = (0xe0, 0x50, 0x1a)
FRAME_D = (0xe7, 0xea, 0xee)


def l1_64_dark():
    print('\nL1: 64 dark pixels (board Logo_Final rectangles)')
    img = theme.logo_pixmap(64, 'dark').toImage()
    c = px(img, 11, 23)          # centre of front cell (8, 20)
    check('front cell (8,20) is #ff6a2b', near(c, FRONT_D)
          and c[3] == 255, str(c))
    c = px(img, 11, 29)          # centre of wake cell (8, 26)
    check('wake cell (8,26) is orange at ~35 % alpha',
          near(c, FRONT_D, tol=20) and 50 <= c[3] <= 130, str(c))
    c = px(img, 11, 11)          # inside the frame, no grid/cell there
    check('empty corner is transparent', c[3] == 0, str(c))
    c = px(img, 32, 8)           # top edge of the frame stroke
    check('frame pixel is #e7eaee', near(c, FRAME_D) and c[3] > 200,
          str(c))


def l2_16():
    print('\nL2: 16 dark - steps and frame only, no grid, no wake')
    img = theme.logo_pixmap(16, 'dark').toImage()
    c = px(img, 3, 4)            # inside step rect (2, 4, 3, 2)
    check('step cell is #ff6a2b', near(c, FRONT_D) and c[3] == 255,
          str(c))
    stray = []
    for y in range(16):
        for x in range(16):
            c = px(img, x, y)
            if c[3] == 0:
                continue
            if not (near(c, FRONT_D) and c[3] == 255) \
                    and not (near(c, FRAME_D) and c[3] == 255):
                stray.append((x, y, c))
    check('no grid/wake pixels at 16', not stray, str(stray[:4]))


def l3_light():
    print('\nL3: light mode front colour')
    img = theme.logo_pixmap(64, 'light').toImage()
    c = px(img, 11, 23)
    check('front cell is #e0501a in light', near(c, FRONT_L)
          and c[3] == 255, str(c))


def l4_icon():
    print('\nL4: app icon sizes and the window icon')
    sizes = {s.width() for s in theme.app_icon().availableSizes()}
    want = {16, 24, 32, 48, 64, 128, 256}
    check('app_icon() carries 16/24/32/48/64/128/256', want <= sizes,
          str(sorted(sizes)))
    from blastlab.ui.app import MainWindow
    win = MainWindow()
    pump(100)
    check('MainWindow icon is not null', not win.windowIcon().isNull())
    from PySide6.QtWidgets import QLabel
    texts = [w.text() for w in win.findChildren(QLabel)]
    check('sidebar shows the BLASTLAB wordmark',
          'BLAST' in texts and 'LAB' in texts)
    win.close()
    pump(50)


def l5_gif():
    print('\nL5: the ELSL logo stays with Tk only')
    hits = []
    ui_dir = os.path.join(REPO, 'blastlab', 'ui')
    for base, _dirs, files in os.walk(ui_dir):
        for name in files:
            if not name.endswith('.py'):
                continue
            path = os.path.join(base, name)
            with open(path, encoding='utf-8') as f:
                if 'logo.gif' in f.read():
                    hits.append(path)
    check('no logo.gif reference under blastlab/ui/', not hits,
          str(hits))
    check('logo.gif still exists at the repo root (Tk asset)',
          os.path.exists(os.path.join(REPO, 'logo.gif')))
    with open(os.path.join(REPO, 'blastlab', 'gui', 'app.py'),
              encoding='utf-8') as f:
        check('the Tk app still uses logo.gif', 'logo.gif' in f.read())


def main():
    l1_64_dark()
    l2_16()
    l3_light()
    l4_icon()
    l5_gif()
    print(f'\nLOGO: {"PASS" if not FAIL else "FAIL " + str(FAIL)}')
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
