"""The blastFoam run browser: WSL run directories as a table, with
Load, Resume, Delete, Refresh and a plain directory Browse fallback.

Listing is instant (names plus each `case.json`'s dim); sizes and the
alive state cost WSL round trips over 9p, so they arrive in a second
pass from a worker thread while the status line says so. The Tk version
needed a `queue.Queue` plus an `after` poll for that; here the worker
hands back through `ThreadBridge`, so there is nothing to drain.

Two rules are load-bearing:

- **Resume and Delete refuse unless `alive is False`.** A `None` means
  "WSL did not report its state", and acting on that would race a live
  solver, so it is refused exactly like a running one.
- **The refusal reaches the status line and the log BEFORE any dialog.**
  A `QMessageBox` static call spins a nested event loop and will hang an
  unattended driver, which is what made the Tk test non-deterministic
  (P2-8). Every dialog here is injectable and strictly last.
"""

import os
import threading

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QTableWidget,
                               QTableWidgetItem)

# dims_from_case_json stays importable here; the main window now reads a
# run's dimension through services/foam_runs (Phase 9)
from ..solvers.foam.runs import (COLS, HEADS, WIDTHS,     # noqa: F401
                                 apply_sizes, build_rows, default_deleter,
                                 default_lister, default_sizer,
                                 dims_from_case_json, human_size,
                                 started_from_name, state_text)
from . import dialogs, theme
from .bridge import ThreadBridge
from .theme import PAD
from .widgets import Card, button, hbox, label, vbox

#: P2-17: the Model column follows the shared columns (`solvers.foam.runs`,
#: which the Tk browser reads too): the model folder whose manifest holds
#: this run's WSL scratch, `-` when none does
MODEL_HEAD, MODEL_WIDTH, NO_MODEL = 'Model', 150, '-'


def model_label(stage_dir):
    """The model a stage folder (`model_folder.model_of_run`) belongs to:
    its own name, or - a chain's `1d`, `2d`, `3d` stage - its parent's."""
    if not stage_dir:
        return ''
    stage_dir = os.path.normpath(stage_dir)
    name = os.path.basename(stage_dir)
    if name.lower() in ('1d', '2d', '3d'):
        return os.path.basename(os.path.dirname(stage_dir))
    return name


class FoamRunBrowser(QDialog):
    """`on_load(unc_path)` receives the selected run (the Results
    panel's loader) and `log(str)` the progress lines. The data sources
    are injectable so the headless test drives this without WSL."""

    TITLE = 'Runs in WSL (/root/blastlab_runs)'

    def __init__(self, parent=None, on_load=None, log=print, lister=None,
                 sizer=None, deleter=None, confirm=None, autorefresh=True,
                 on_resume=None, warner=None, bridge=None, runs_dir=None,
                 modeler=None):
        super().__init__(parent)
        self.setWindowTitle('blastFoam runs')
        self.resize(900, 420)
        # P2-17: `runs_dir()` is the Run tab's Runs folder; `modeler(runs,
        # posix)` finds a run's model folder (injectable like the rest)
        self._runs_dir = runs_dir or (lambda: '')
        self._modeler = modeler or self._find_model
        self._on_load = on_load or (lambda path: None)
        self._on_resume = on_resume
        self._log = log
        self._lister = lister or default_lister
        self._sizer = sizer or default_sizer
        self._deleter = deleter or default_deleter
        self._warn = warner or (
            lambda title, msg: dialogs.warn(title, msg, self))
        self._confirm = confirm or (
            lambda title, msg: dialogs.ask_yes_no(title, msg, self))
        self._bridge = bridge if bridge is not None else ThreadBridge(self)
        self.rows = {}           # name -> dict(unc, posix, alive, bytes)
        self._busy = False

        root = vbox(self, margins=(PAD, PAD, PAD, PAD))
        card = Card(title=self.TITLE, pad=12)
        root.addWidget(card, 1)

        self.table = QTableWidget(0, len(COLS) + 1)
        self.table.setHorizontalHeaderLabels(list(HEADS) + [MODEL_HEAD])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        for i, w in enumerate(tuple(WIDTHS) + (MODEL_WIDTH,)):
            self.table.setColumnWidth(i, w)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(lambda *_: self.load_selected())
        card.add(self.table, 1)

        bar = hbox()
        self.status = label('', 'small')
        bar.addWidget(self.status, 1)
        self.btn_browse = button('Browse…', width=100, height=30,
                                 on_click=self.browse)
        self.btn_refresh = button('Refresh', width=100, height=30,
                                  on_click=self.refresh)
        bar.addWidget(self.btn_browse)
        bar.addWidget(self.btn_refresh)
        self.btn_resume = None
        if on_resume is not None:
            # continue a STOPPED run from its last written time
            self.btn_resume = button('Resume', width=100, height=30,
                                     on_click=self.resume_selected)
            bar.addWidget(self.btn_resume)
        self.btn_load = button('Load', width=100, height=30,
                               on_click=self.load_selected)
        self.btn_delete = button('Delete', kind='danger', width=100,
                                 height=30, on_click=self.delete_selected)
        self.btn_close = button('Close', width=100, height=30,
                                on_click=self.close)
        for b in (self.btn_load, self.btn_delete, self.btn_close):
            bar.addWidget(b)
        card.add_layout(bar)
        if autorefresh:
            self.refresh()

    # -- the status line --------------------------------------------------
    def _say(self, text, bad=False):
        self.status.setText(str(text))
        self.status.setStyleSheet(
            f'color: {theme.cur("danger" if bad else "muted")};')

    # -- data -------------------------------------------------------------
    def refresh(self):
        """Names, dims and start time now; sizes and the alive state from
        a worker thread, because each is a WSL round trip."""
        if self._busy:
            return False
        self._busy = True
        self._say('listing runs…')
        self.table.setRowCount(0)
        self.rows = {}

        def work():
            try:
                rows = build_rows(self._lister())
                # names first, so 80 run dirs are on screen immediately
                self._bridge.post(self._fill, dict(rows), False)
                sizes = self._sizer([r['posix'] for r in rows.values()])
                sized = apply_sizes(rows, sizes)
                runs = self._runs_dir()
                for r in sized.values():       # P2-17: off the GUI thread
                    r['model'] = self._modeler(runs, r['posix'])
                self._bridge.post(self._fill, sized, True)
            except Exception as exc:        # surfaced, never a dead window
                self._bridge.post(self._failed,
                                  f'{type(exc).__name__}: {exc}')

        threading.Thread(target=work, daemon=True).start()
        return True

    @staticmethod
    def _find_model(runs_dir, posix):
        """The stage folder of the model that holds this run's scratch, or
        None (`model_folder.model_of_run`)."""
        from ..services import model_folder
        try:
            return model_folder.model_of_run(runs_dir, posix)
        except OSError:
            return None

    def _fill(self, rows, sized):
        """Repaint the table, keeping the selection by NAME - the row
        order can change between the two passes."""
        sel = self.selected_name()
        self.rows = rows
        self.table.setRowCount(len(rows))
        total = 0
        pick = -1
        for r, (name, row) in enumerate(rows.items()):
            total += row['bytes'] or 0
            values = (name, row['dims'],
                      human_size(row['bytes']) if sized else '…',
                      started_from_name(name), state_text(row['alive']),
                      (model_label(row.get('model')) or NO_MODEL) if sized
                      else '…')
            for c, text in enumerate(values):
                item = QTableWidgetItem(str(text))
                item.setTextAlignment(Qt.AlignVCenter | (
                    Qt.AlignLeft if c == 0 else Qt.AlignHCenter))
                self.table.setItem(r, c, item)
            if name == sel:
                pick = r
        if pick >= 0:
            self.table.selectRow(pick)
        n = len(rows)
        if sized:
            self._busy = False
            self._say(f'{n} run{"s" if n != 1 else ""}, '
                      f'{human_size(total)} total' if n else 'no runs')
        else:
            self._say(f'{n} run{"s" if n != 1 else ""} - '
                      f'measuring sizes…')

    def _failed(self, msg):
        self._busy = False
        self._say(f'listing failed: {msg}', bad=True)
        self._log(f'  [runs] listing failed: {msg}')

    # -- selection --------------------------------------------------------
    def selected_name(self):
        r = self.table.currentRow()
        item = self.table.item(r, 0) if r >= 0 else None
        return item.text() if item is not None else None

    def selected(self):
        name = self.selected_name()
        return name, (self.rows.get(name) if name else None)

    def select(self, name):
        """Pick a row by run name (the test and the QA harness use it)."""
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item is not None and item.text() == name:
                self.table.selectRow(r)
                return True
        return False

    def names(self):
        return [self.table.item(r, 0).text()
                for r in range(self.table.rowCount())
                if self.table.item(r, 0) is not None]

    def row_text(self, name):
        for r in range(self.table.rowCount()):
            first = self.table.item(r, 0)
            if first is not None and first.text() == name:
                return tuple(
                    (self.table.item(r, c).text()
                     if self.table.item(r, c) is not None else '')
                    for c in range(self.table.columnCount()))
        return None

    # -- actions ----------------------------------------------------------
    def load_selected(self):
        name, row = self.selected()
        if row is None:
            self._say('select a run first')
            return False
        self._log(f'  [runs] loading {name} ...')
        self._on_load(row['unc'])
        return True

    def _refuse(self, gerund, verb, name, alive):
        """`alive is None` is refused exactly like a live run: WSL did
        not say, and acting blind would race the solver."""
        why = ('its solver is still running' if alive
               else 'WSL did not report its state')
        self._say(f'not {gerund} {name}: {why}', bad=True)
        self._log(f'  [runs] refused to {verb} {name}: {why}')
        return why

    def resume_selected(self):
        """Continue the selected run from its last written time. Resume
        is for STOPPED runs only."""
        name, row = self.selected()
        if row is None:
            self._say('select a run first')
            return False
        if row['alive'] is not False:
            self._refuse('resuming', 'resume', name, row['alive'])
            return False
        self._log(f'  [runs] resuming {name} ...')
        self.close()                     # the Run tab takes over
        self._on_resume(row['unc'])
        return True

    def delete_selected(self):
        name, row = self.selected()
        if row is None:
            self._say('select a run first')
            return False
        if row['alive'] is not False:
            why = self._refuse('deleting', 'delete', name, row['alive'])
            # a muted status line was easy to miss for a refused delete,
            # so it is also said out loud - AFTER the two lines above
            try:
                self._warn('Delete run',
                           f'{name} was not deleted: {why}.')
            except Exception as exc:
                self._log(f'  [runs] (the warning dialog failed: {exc})')
            return False
        size = human_size(row['bytes'])
        if not self._confirm('Delete run',
                             f'Delete {name} ({size}) from the WSL disk? '
                             f'This cannot be undone.'):
            return False
        self._say(f'deleting {name}…')
        self._busy = True

        def work():
            ok = self._deleter([row['posix']])
            self._bridge.post(self._deleted, name, ok)

        threading.Thread(target=work, daemon=True).start()
        return True

    def _deleted(self, name, ok):
        self._log(f'  [runs] {"deleted" if ok else "could not delete"} '
                  f'{name}')
        self._busy = False
        self.refresh()

    def browse(self):
        from ..solvers.foam import env
        initial = env.unc(env.RUNS_ROOT)
        path = dialogs.pick_dir(
            'Load a finished blastFoam run directory', self,
            initial if os.path.isdir(initial) else '')
        if path:
            self._on_load(path)
            return True
        return False
