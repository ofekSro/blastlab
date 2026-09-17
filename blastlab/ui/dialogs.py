"""Modal dialogs and file pickers behind module-level functions.

Every modal is a hazard for unattended drivers (the Tk app learned this
with `messagebox`): an e2e script or the QA harness that reaches one
stops dead. Resolving them through this module at CALL time lets a test
replace `dialogs.show_error` with a recorder and keep going."""

from PySide6.QtWidgets import QFileDialog, QMessageBox


def show_error(title, text, parent=None):
    QMessageBox.critical(parent, title, str(text))


def show_info(title, text, parent=None):
    QMessageBox.information(parent, title, str(text))


def warn(title, text, parent=None):
    QMessageBox.warning(parent, title, str(text))


def ask_yes_no(title, text, parent=None):
    btn = QMessageBox.question(parent, title, str(text),
                               QMessageBox.Yes | QMessageBox.No,
                               QMessageBox.No)
    return btn == QMessageBox.Yes


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
