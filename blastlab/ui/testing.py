"""Helpers for the plain-script UI tests (no pytest): an offscreen
QApplication, an event pump and widget text collection."""

import json
import os
import tempfile
import time


def private_settings():
    """Point BLASTLAB_SETTINGS at a throwaway file and WRITE
    `auto_cleanup: false` into it. Returns the path.

    Redirecting the path alone is not enough, and believing it was cost
    real data. Building a MainWindow starts `foam_env.start_auto_cleanup`
    against whatever `settings.load()` returns, and for a file that does
    not exist that is `settings.DEFAULTS` - which is the MOST aggressive
    policy there is: keep the runs root under 20 GB, drop anything older
    than 14 days, keep only the 3 newest runs. So a test that "protected"
    the real settings by pointing away from them was in fact deleting the
    run corpus harder than the real app would have.

    A test must never delete a run directory, so the file is written with
    the sweep off rather than left absent. (Since 2026-09-27 DEFAULTS
    has the sweep off too; the explicit key stays as a second lock.)

    OUT-1: it also carries a throwaway `runs_dir` (a `runs` folder beside
    the file), so a test that runs something never writes a model folder
    into the owner's runs folder.
    """
    path = os.environ.get('BLASTLAB_SETTINGS')
    if not path:
        path = os.path.join(tempfile.mkdtemp(prefix='blastlab_ui_'),
                            'settings.json')
        os.environ['BLASTLAB_SETTINGS'] = path
    disable_cleanup(path)
    private_runs_dir(path)
    return path


def private_runs_dir(path=None):
    """The throwaway runs folder of the private settings file at `path`:
    `<dir of the file>\\runs`, created, and written into the file as
    `runs_dir` unless the file already names an existing one. Returns
    the folder (None without a settings file)."""
    path = path or os.environ.get('BLASTLAB_SETTINGS')
    if not path:
        return None
    data = {}
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    runs = data.get('runs_dir')
    if runs and os.path.isdir(runs):
        return runs
    runs = os.path.join(os.path.dirname(os.path.abspath(path)), 'runs')
    os.makedirs(runs, exist_ok=True)
    data['runs_dir'] = runs
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass
    return runs


def use_model(win, name='QA', runs_dir=None):
    """Fill the Run tab's Runs folder (default: the private one) and
    Model boxes of the Qt window - or the Tk app - `win`, so pressing Run
    passes the OUT-1 pre-flight. An existing model folder of that name is
    removed first, so no overwrite question comes up. Returns the model
    folder path."""
    import shutil
    from ..services import model_folder
    runs = runs_dir or private_runs_dir(private_settings())
    folder = os.path.join(runs, name)
    if os.path.isdir(folder):
        if not model_folder.is_model_folder(folder):
            raise RuntimeError(f'use_model: {folder} is not a blastlab '
                               f'model folder - not deleting it')
        # the run in progress writes there (Qt: ctrl, Tk: the app itself)
        owner = getattr(win, 'ctrl', win)
        live = getattr(owner, '_model', None)
        running = (owner.running if hasattr(owner, 'running')
                   else getattr(owner, '_drain_pending', False))
        if running and live is not None and os.path.normcase(
                live.folder) == os.path.normcase(folder):
            raise RuntimeError(f'use_model: {folder} belongs to the run in '
                               f'progress - not deleting it')
        shutil.rmtree(folder, ignore_errors=True)
    win.run_panel.set_runs_dir(runs)
    box = win.run_panel.run_name
    (box.setText if hasattr(box, 'setText') else box.set)(name)  # Qt | Tk
    return folder


def disable_cleanup(path=None):
    """Make sure the settings file at `path` says `auto_cleanup: false`,
    creating it if need be. Never touches any other key."""
    path = path or os.environ.get('BLASTLAB_SETTINGS')
    if not path:
        return None
    data = {}
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    if data.get('auto_cleanup') is False:
        return path
    data['auto_cleanup'] = False
    try:
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass
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
