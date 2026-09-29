"""Modal dialogs and file pickers behind module-level functions.

Every modal is a hazard for unattended drivers (the Tk app learned this
with `messagebox`): an e2e script or the QA harness that reaches one
stops dead. Resolving them through this module at CALL time lets a test
replace `dialogs.show_error` with a recorder and keep going."""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFileDialog, QMessageBox

#: the tray icon behind the last desktop notification, or None. It is
#: created on demand and removed on a click, after TRAY_LIFE_MS, at the
#: next run start and at close (clear_tray), so it never lingers
_tray = None
TRAY_LIFE_MS = 60_000
#: how long Windows is asked to show the notification
TOAST_MS = 10_000


def show_error(title, text, parent=None):
    QMessageBox.critical(parent, title, str(text))


def show_info(title, text, parent=None):
    QMessageBox.information(parent, title, str(text))


def warn(title, text, parent=None):
    QMessageBox.warning(parent, title, str(text))


def ask_yes_no(title, text, parent=None, yes=None, no=None):
    """True for yes. `yes` / `no` relabel the two buttons (the Stop
    confirmation: `Stop the run` / `Keep running`); either way *no* is
    the default and the Escape answer, so a stray Enter never says
    yes. With neither label given it is the plain Yes / No box, as
    every existing call has it."""
    if yes is None and no is None:
        btn = QMessageBox.question(parent, title, str(text),
                                   QMessageBox.Yes | QMessageBox.No,
                                   QMessageBox.No)
        return btn == QMessageBox.Yes
    box = QMessageBox(QMessageBox.Question, title, str(text),
                      QMessageBox.NoButton, parent)
    yes_btn = box.addButton(str(yes or 'Yes'), QMessageBox.YesRole)
    no_btn = box.addButton(str(no or 'No'), QMessageBox.NoRole)
    box.setDefaultButton(no_btn)
    box.setEscapeButton(no_btn)
    box.exec()
    return box.clickedButton() is yes_btn


def open_file(title, filters='All files (*.*)', parent=None, start=''):
    """Path or '' (the Qt filter syntax: 'blastlab case (*.json)')."""
    path, _f = QFileDialog.getOpenFileName(parent, title, start, filters)
    return path or ''


def save_file(title, filters='All files (*.*)', parent=None, start='',
              default_suffix=None):
    dlg = QFileDialog(parent, title, start, filters)
    dlg.setAcceptMode(QFileDialog.AcceptSave)
    if default_suffix:
        dlg.setDefaultSuffix(default_suffix.lstrip('.'))
    if dlg.exec():
        files = dlg.selectedFiles()
        return files[0] if files else ''
    return ''


def pick_dir(title, parent=None, start=''):
    path = QFileDialog.getExistingDirectory(parent, title, start)
    return path or ''


def notify_desktop(title, text, on_click=None, parent=None):
    """A Windows notification (plan §6): a tray icon with the app icon is
    created on demand and `showMessage` raises the toast; a click on it
    calls `on_click`. The icon goes on that click, after TRAY_LIFE_MS, or
    at `clear_tray()`. Returns False and does nothing when the platform
    has no system tray (the offscreen tests). Not modal, but resolved
    through this module like every dialog, so the QA harness records it
    instead of raising a real one."""
    from PySide6.QtWidgets import QSystemTrayIcon

    from . import theme
    global _tray
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return False
    clear_tray()
    icon = theme.app_icon()
    tray = QSystemTrayIcon(icon, parent)
    tray.setToolTip(str(title))

    def clicked():
        clear_tray()
        if on_click is not None:
            on_click()

    tray.messageClicked.connect(clicked)
    life = QTimer(tray)
    life.setSingleShot(True)
    life.setInterval(TRAY_LIFE_MS)
    life.timeout.connect(clear_tray)
    tray.show()
    tray.showMessage(str(title), str(text), icon, TOAST_MS)
    life.start()
    _tray = tray
    return True


def clear_tray():
    """Remove the notification's tray icon, if there is one."""
    global _tray
    tray, _tray = _tray, None
    if tray is not None:
        tray.hide()
        tray.deleteLater()
