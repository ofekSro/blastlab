"""Modal dialogs and file pickers behind module-level functions.

Every modal is a hazard for unattended drivers (the Tk app learned this
with `messagebox`): an e2e script or the QA harness that reaches one
stops dead. Resolving them through this module at CALL time lets a test
replace `dialogs.show_error` with a recorder and keep going."""

import re

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel, QMessageBox

#: the tray icon behind the last desktop notification, or None. It is
#: created on demand and removed on a click, after TRAY_LIFE_MS, at the
#: next run start and at close (clear_tray), so it never lingers
_tray = None
TRAY_LIFE_MS = 60_000
#: how long Windows is asked to show the notification
TOAST_MS = 10_000

#: a Windows path in a message: a drive or UNC start, up to the next space,
#: with the opening quote or bracket that may precede it - an OSError's
#: text quotes its path (`Permission denied: 'C:\\...'`), and a quoted path
#: must start its line with its quote or Qt breaks it mid-path (verify11a)
_PATH_TOKEN = re.compile(r'''['"(]?(?:[A-Za-z]:[\\/]|\\\\)\S*''')
#: a message box may widen to keep a path on one line up to this share of
#: the available screen width (P2-18, D207) ...
PATH_SCREEN_SHARE = 0.70
#: ... and never past QMessageBox's own hard limit, min(available width
#: - 480, 1000) px (Qt 6 qmessagebox.cpp, updateSize), less the icon and
#: the margins: past that limit Qt wraps the text anywhere
_BOX_HARD_MARGIN, _BOX_HARD_MAX, _BOX_ICON_ALLOW = 480, 1000, 120


def _keep_paths(box):
    """Keep every path in `box`'s text on one line (P2-18: the refusal and
    overwrite boxes broke a path after `C:`). The text label's minimum
    width becomes the advance of the longest path token, capped as above.
    That alone is not enough (measured on the real platform, D207): Qt's
    line breaking may break between `C:` and `\\` whenever the text
    before the path leaves too little room on its line. So a path whose
    line would not fit starts a new line instead. A path wider than the
    cap is elided in the middle, the whole text in the label's tooltip.
    The text is selectable either way."""
    lbl = box.findChild(QLabel, 'qt_msgbox_label')
    if lbl is None:
        return
    lbl.setTextInteractionFlags(Qt.TextSelectableByMouse
                                | Qt.TextSelectableByKeyboard)
    text = box.text()
    tokens = _PATH_TOKEN.findall(text)
    if not tokens:
        return
    box.ensurePolished()
    lbl.ensurePolished()
    fm = lbl.fontMetrics()
    parent = box.parentWidget()
    screen = ((parent.screen() if parent is not None else None)
              or QApplication.primaryScreen())
    avail = screen.availableGeometry().width() if screen else 1280
    cap = int(min(avail * PATH_SCREEN_SHARE,
                  min(avail - _BOX_HARD_MARGIN, _BOX_HARD_MAX)
                  - _BOX_ICON_ALLOW))
    need = max(fm.horizontalAdvance(t) for t in tokens) + 2
    shown = text
    if need > cap:
        cut = []

        def elide(m):
            tok = m.group(0)
            if fm.horizontalAdvance(tok) + 2 <= cap:
                return tok
            cut.append(tok)
            return fm.elidedText(tok, Qt.ElideMiddle, cap - 2)
        shown = _PATH_TOKEN.sub(elide, text)
        lbl.setToolTip(text)
        # F40 (GUI-11): a tooltip cannot be copied, so each path shortened
        # here is also given whole under Show Details…, one per line
        box.setDetailedText('\n'.join(_bare_path(t) for t in cut))
        need = cap
    shown = _paths_start_lines(shown, fm, need)
    if shown != text:
        box.setText(shown)
    lbl.setMinimumWidth(need)


def _bare_path(token):
    """A path token without the quote or bracket around it and the
    sentence's own trailing punctuation: `'C:\\a\\b.json'.` -> the path.
    A quoted path is an OSError's repr, whose backslashes are doubled;
    they are halved back (a UNC start doubled twice gives `\\\\`)."""
    opener = token[:1] if token[:1] in '\'"(' else ''
    path = token[len(opener):]
    closer = {'\'': '\'', '"': '"', '(': ')'}.get(opener, '')
    path = path.rstrip('.,;:')
    if closer and path.endswith(closer):
        path = path[:-1]
    if opener in '\'"' and opener:
        path = path.replace('\\\\', '\\')
    return path.rstrip('.,;:')


def _paths_start_lines(text, fm, width):
    """`text` with the space before a path turned into a line break when
    the path's line, from its start to the path's end, is wider than
    `width` px (see `_keep_paths`)."""
    out, last, line_start = [], 0, 0
    for m in _PATH_TOKEN.finditer(text):
        s, e = m.span()
        start = max(line_start, text.rfind('\n', 0, s) + 1)
        if s > start and text[s - 1] == ' ' \
                and fm.horizontalAdvance(text[start:e]) > width:
            out += [text[last:s - 1], '\n']
            last = line_start = s
    out.append(text[last:])
    return ''.join(out)


def _message(icon, title, text, parent=None):
    box = QMessageBox(icon, title, str(text), QMessageBox.Ok, parent)
    _keep_paths(box)
    box.exec()


def show_error(title, text, parent=None):
    _message(QMessageBox.Critical, title, text, parent)


def show_info(title, text, parent=None):
    _message(QMessageBox.Information, title, text, parent)


def warn(title, text, parent=None):
    _message(QMessageBox.Warning, title, text, parent)


def ask_yes_no(title, text, parent=None, yes=None, no=None):
    """True for yes. `yes` / `no` relabel the two buttons (the Stop
    confirmation: `Stop the run` / `Keep running`); either way *no* is
    the default and the Escape answer, so a stray Enter never says
    yes. With neither label given it is the plain Yes / No box, as
    every existing call has it."""
    if yes is None and no is None:
        box = QMessageBox(QMessageBox.Question, title, str(text),
                          QMessageBox.Yes | QMessageBox.No, parent)
        box.setDefaultButton(QMessageBox.No)
        box.setEscapeButton(QMessageBox.No)
        _keep_paths(box)
        box.exec()
        return box.clickedButton() is box.button(QMessageBox.Yes)
    box = QMessageBox(QMessageBox.Question, title, str(text),
                      QMessageBox.NoButton, parent)
    yes_btn = box.addButton(str(yes or 'Yes'), QMessageBox.YesRole)
    no_btn = box.addButton(str(no or 'No'), QMessageBox.NoRole)
    box.setDefaultButton(no_btn)
    box.setEscapeButton(no_btn)
    _keep_paths(box)
    box.exec()
    return box.clickedButton() is yes_btn


def ask_discard(kind, text, parent=None, title='BlastLab'):
    """The one question before Close, Open or Recent drops a live run or
    unsaved edits (GUI-11 T2, UXR-1, D202). `kind`:

    - 'run': `Stop and quit` / `Keep running`;
    - 'hd13': `Quit` / `Keep running`;
    - 'dirty': `Save` / `Discard` / `Cancel`.

    Returns 'proceed' (stop and quit, quit, discard), 'save' or
    'cancel'. Keeping the run, and Cancel, are the Escape answers, so a
    stray Escape never loses anything. `testing.ensure_qapp()` replaces
    this function with a recorder that answers 'proceed'."""
    box = QMessageBox(QMessageBox.Question if kind == 'dirty'
                      else QMessageBox.Warning, title, str(text),
                      QMessageBox.NoButton, parent)
    _keep_paths(box)
    if kind == 'dirty':
        save = box.addButton('Save', QMessageBox.AcceptRole)
        discard = box.addButton('Discard', QMessageBox.DestructiveRole)
        cancel = box.addButton('Cancel', QMessageBox.RejectRole)
        box.setDefaultButton(save)
        box.setEscapeButton(cancel)
        box.exec()
        hit = box.clickedButton()
        return ('save' if hit is save else
                'proceed' if hit is discard else 'cancel')
    go = box.addButton('Stop and quit' if kind == 'run' else 'Quit',
                       QMessageBox.DestructiveRole)
    keep = box.addButton('Keep running', QMessageBox.RejectRole)
    box.setDefaultButton(keep)
    box.setEscapeButton(keep)
    box.exec()
    return 'proceed' if box.clickedButton() is go else 'cancel'


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
