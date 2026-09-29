"""The dock under the Run screen's view (GUI-6, plan §6, UX-18; board Run
lines 246-256): **Log · Messages · Earlier runs**, with **Copy** and
**Save log…** at the right of the tab strip.

- *Log* is the run log the panel has always had (`QPlainTextEdit` named
  `log`, mono, 50 000 blocks, the AMR collapse lives in the panel).
- *Messages* is this session's `notify()` history - the status-line
  messages that vanish after 12 s - `HH:MM:SS  level  text`, newest
  last, at most MESSAGES_MAX.
- *Earlier runs* keeps what the Log showed for each of this session's
  earlier runs, newest first, at most HISTORY_MAX, in memory. The
  persistent record is each model's `run.log` (OUT-1), written as
  before and not touched here.

Copy and Save log… act on the page on screen: the current log, the
Messages text, or the selected earlier run. Display only."""

import os
import time
from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout,
                               QListWidget, QListWidgetItem, QPlainTextEdit,
                               QPushButton, QVBoxLayout, QWidget)

from . import theme
from .components import DockTabs

#: earlier runs kept in memory (the persistent record is <model>\run.log)
HISTORY_MAX = 20
#: notify() messages kept on the Messages page
MESSAGES_MAX = 500
#: the Save log… file filter
LOG_FILTER = 'Log (*.log *.txt);;All files (*.*)'
#: how a run ended, as the Earlier runs row says it
HOW_TEXT = {'done': 'finished', 'stopped': 'stopped by the user',
            'failed': 'failed', 'ended': 'ended', None: 'ended'}
#: the model folder's log file (services/model_folder.LOG_FILE)
RUN_LOG = 'run.log'


def _text_view(name):
    v = QPlainTextEdit()
    v.setObjectName(name)
    v.setReadOnly(True)
    v.setFont(theme.font('mono'))
    v.setLineWrapMode(QPlainTextEdit.WidgetWidth)
    return v


def _tool(text, tip):
    b = QPushButton(text)
    b.setObjectName('docktool')
    b.setCursor(Qt.PointingHandCursor)
    b.setToolTip(tip)
    return b


class RunDock(QFrame):
    """The dock. `log` is the live Log page; `record_start` /
    `record_end` bracket a run so its text can be kept when the next
    one starts."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('rundock')
        dl = QVBoxLayout(self)
        dl.setContentsMargins(1, 0, 1, 1)
        dl.setSpacing(0)
        self.tabs = DockTabs()
        rule = QFrame()
        rule.setObjectName('dockrule')
        rule.setFixedHeight(1)
        self.tabs.layout().insertWidget(1, rule)
        dl.addWidget(self.tabs)

        self.log = _text_view('log')
        self.log.setMaximumBlockCount(50000)
        self.tabs.add('Log', self.log)
        self.messages = _text_view('runmsgs')
        self.messages.setMaximumBlockCount(MESSAGES_MAX)
        self.tabs.add('Messages', self.messages)
        page = QWidget()
        pl = QHBoxLayout(page)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(0)
        self.earlier_list = QListWidget()
        self.earlier_list.setObjectName('earlierlist')
        self.earlier_list.setMinimumWidth(150)
        self.earlier_list.setMaximumWidth(230)
        self.earlier_list.currentRowChanged.connect(self._earlier_selected)
        pl.addWidget(self.earlier_list)
        self.earlier_view = _text_view('earlierlog')
        pl.addWidget(self.earlier_view, 1)
        self.tabs.add('Earlier runs', page)

        self.copy_btn = self.tabs.add_corner(_tool(
            'Copy', 'Copy the text of the page on screen'))
        self.copy_btn.clicked.connect(lambda *_: self.copy())
        self.save_btn = self.tabs.add_corner(_tool(
            'Save log…', 'Save the text of the page on screen as a file'),
            gap=6)
        self.save_btn.clicked.connect(lambda *_: self.save())

        self._history = []      # newest first: dict(model, started, ...)
        self._messages = []     # (stamp, level, text), oldest first
        self._cur = None        # the run the Log pane is showing now
        self._label_earlier()
        theme.signals.changed.connect(self._retheme)

    def focus_widgets(self):
        """The dock's Tab stops in reading order - the tabs, Copy, Save
        log…, the other pages - without the Log, which the Run panel
        puts last."""
        return ([self.tabs.button(n) for n in self.tabs.names()]
                + [self.copy_btn, self.save_btn, self.messages,
                   self.earlier_list, self.earlier_view])

    # ── runs: the Log pane's text kept per run ───────────────────────────
    def record_start(self, model, folder):
        """A run starts: keep what the Log showed (if anything) as an
        earlier run, then clear the pane - `log_text()` stays the
        current run's log (U14, the harness's wait_log, the e2e
        drivers). Everything the pane showed between two run starts is
        one entry, HD 1.3 lines included, named after the run that began
        it (text from before the first run is `session start`)."""
        text = self.log.toPlainText()
        if text:
            cur = self._cur or dict(model='session start', folder=None,
                                    started=None, ended=None, how=None)
            entry = dict(cur, text=text)
            if entry.get('ended') is None:
                entry['ended'] = time.localtime()
            self._history.insert(0, entry)
            del self._history[HISTORY_MAX:]
            self._fill_earlier()
        self.log.clear()
        self._cur = dict(model=str(model or '') or 'unnamed',
                         folder=folder or None, started=time.localtime(),
                         ended=None, how=None)

    def record_end(self, how=None):
        """The run ended; `how` from on_finished (None: not known yet).
        HD 1.3 lines keep landing in the same entry until the next
        start."""
        if self._cur is None:
            return
        if self._cur.get('ended') is None:
            self._cur['ended'] = time.localtime()
        if how is not None:
            self._cur['how'] = how

    def history(self):
        """[dict(model, started, ended, how, text, folder)], newest first
        (`started` / `ended` are time.struct_time or None)."""
        return [dict(e) for e in self._history]

    def _row_text(self, e):
        started = (time.strftime('%H:%M', e['started']) if e['started']
                   else '')
        n = len(e['text'].splitlines())
        bits = [e['model']]
        if started:
            bits.append(f'started {started}')
        if e['model'] != 'session start':
            bits.append(HOW_TEXT.get(e.get('how'), str(e.get('how'))))
        bits.append(f'{n} line{"" if n == 1 else "s"}')
        return ' · '.join(bits)

    def _fill_earlier(self):
        self.earlier_list.blockSignals(True)
        self.earlier_list.clear()
        for e in self._history:
            item = QListWidgetItem(self._row_text(e))
            item.setToolTip(os.path.join(e['folder'], RUN_LOG)
                            if e.get('folder') else
                            'No model folder (text from this session only)')
            self.earlier_list.addItem(item)
        self.earlier_list.blockSignals(False)
        self.earlier_view.clear()
        self._label_earlier()

    def _label_earlier(self):
        self.tabs.set_label('Earlier runs',
                            f'Earlier runs   {len(self._history)}')

    def _earlier_selected(self, row):
        if 0 <= row < len(self._history):
            self.earlier_view.setPlainText(self._history[row]['text'])
        else:
            self.earlier_view.clear()

    def show_earlier(self, i):
        """Bring up Earlier runs with entry `i` (0 = newest) shown."""
        self.tabs.set('Earlier runs')
        if 0 <= i < len(self._history):
            self.earlier_list.setCurrentRow(i)
            self._earlier_selected(i)

    def earlier_text(self):
        """The text the Earlier runs viewer shows now."""
        return self.earlier_view.toPlainText()

    # ── messages: the session's notify() history ─────────────────────────
    def add_message(self, level, text):
        stamp = time.strftime('%H:%M:%S')
        self._messages.append((stamp, str(level or 'info'), str(text)))
        del self._messages[:-MESSAGES_MAX]
        self._append_message(*self._messages[-1])

    def _append_message(self, stamp, level, text):
        colour = theme.cur({'warn': 'warn', 'error': 'danger'}.get(
            level, 'text2'))
        self.messages.appendHtml(
            f'<span style="color: {colour};">'
            f'{escape(self._message_line(stamp, level, text))}</span>')

    @staticmethod
    def _message_line(stamp, level, text):
        return f'{stamp}  {level}  {text}'

    def messages_text(self):
        return '\n'.join(self._message_line(*m) for m in self._messages)

    def _retheme(self, _mode=None):
        # the levels' colours are baked into the rows
        self.messages.clear()
        for m in self._messages:
            self._append_message(*m)

    # ── Copy / Save log… ─────────────────────────────────────────────────
    def shown_text(self):
        """The text of the page on screen."""
        page = self.tabs.get()
        if page == 'Messages':
            return self.messages_text()
        if page == 'Earlier runs':
            row = self.earlier_list.currentRow()
            return (self._history[row]['text']
                    if 0 <= row < len(self._history) else '')
        return self.log.toPlainText()

    def _shown_entry(self):
        if self.tabs.get() == 'Earlier runs':
            row = self.earlier_list.currentRow()
            if 0 <= row < len(self._history):
                return self._history[row]
        return self._cur

    def copy(self):
        QApplication.clipboard().setText(self.shown_text())

    def save(self):
        """Save log…: the shown text, UTF-8, `\\n` newlines, exactly as
        shown; a cancelled dialog writes nothing. The dialog starts in
        the run's model folder as `run-<model>-<HHMMSS>.log`."""
        from . import dialogs
        e = self._shown_entry() or {}
        model = e.get('model') or 'session'
        name = f'run-{model}-{time.strftime("%H%M%S")}.log'
        start = os.path.join(e['folder'], name) if e.get('folder') else name
        path = dialogs.save_file('Save log', LOG_FILTER, self, start=start)
        if not path:
            return None
        try:
            with open(path, 'wb') as f:
                f.write(self.shown_text().encode('utf-8'))
        except OSError as exc:
            # a read-only folder or a locked file: say so, as every other
            # export does, instead of an exception out of a click
            dialogs.show_error('Save log', f'Could not write {path}:\n{exc}',
                               self)
            return None
        return path
