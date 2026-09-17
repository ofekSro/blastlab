"""Helpers for the plain-script UI tests (no pytest): an offscreen
QApplication, an event pump and widget text collection."""

import os
import tempfile
import time


def private_settings():
    """Point BLASTLAB_SETTINGS at a throwaway file (the app's auto-cleanup
    of WSL run dirs reads the real settings otherwise). Returns the path."""
    path = os.environ.get('BLASTLAB_SETTINGS')
    if not path:
        path = os.path.join(tempfile.mkdtemp(prefix='blastlab_ui_'),
                            'settings.json')
        os.environ['BLASTLAB_SETTINGS'] = path
    return path


def ensure_qapp(offscreen=True):
    """The process-wide QApplication, created on the offscreen platform
    unless QT_QPA_PLATFORM is already set (or offscreen=False)."""
    if offscreen:
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        # the offscreen platform has no system font database; without a
        # font dir every label grabs as boxes (only screenshots care)
        fonts = os.path.join(os.environ.get('WINDIR', r'C:\Windows'),
                             'Fonts')
        if os.path.isdir(fonts):
            os.environ.setdefault('QT_QPA_FONTDIR', fonts)
    os.environ.setdefault('MPLBACKEND', 'Agg')
    private_settings()
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(['blastlab-test'])
        from . import theme
        theme.apply(app, 'dark')
    return app


def pump(ms=50):
    """Run the event loop for about `ms` milliseconds."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    end = time.monotonic() + ms / 1000.0
    while True:
        app.processEvents()
        if time.monotonic() >= end:
            break
        time.sleep(0.005)
    app.processEvents()


def widget_texts(root):
    """Every non-empty text of the labels/buttons under `root`."""
    from PySide6.QtWidgets import (QAbstractButton, QLabel, QLineEdit,
                                   QWidget)
    out = []
    for w in root.findChildren(QWidget):
        text = ''
        if isinstance(w, (QLabel, QAbstractButton)):
            text = w.text()
        elif isinstance(w, QLineEdit):
            text = w.text()
        if text:
            out.append(text)
    return out
