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
