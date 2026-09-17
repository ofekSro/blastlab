"""A stand-in for the viewer child, for the embedding tests.

One `Qt.Window` widget whose native handle is printed on stdout, which
is all the host needs to exercise `QWindow.fromWinId` +
`createWindowContainer`. Used instead of the real viewer because a
pyvista scene needs an OpenGL context, while the bug under test is
purely about where Windows puts a re-parented window.

Run by `_e2e_ui_embed.py`; not a test on its own.
"""
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication, QWidget


class Surface(QWidget):
    """Shaped like the viewer's SurfaceWindow: top-level, no parent."""

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(Qt.Window)
        self.setWindowTitle('blastlab - stand-in surface')
        self.resize(320, 240)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#101010'))
        p.setPen(QColor('#ff8000'))
        p.drawText(16, 32, 'stand-in render window')


def main():
    app = QApplication(['blastlab-foreign'])
    w = Surface()
    w.show()
    app.processEvents()
    print(f'HWND {int(w.winId())}', flush=True)
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
