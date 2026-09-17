"""The Results tab: browse the snapshots and gauges of finished runs,
replay recorded frames, drive the 3D viewer, and export.

Screen and file differ here by design. On screen the Fields view is ONE
large panel with selectors, because a persistent pyqtgraph image makes a
field change a single array upload. The `PNGs` and `Report` exports keep
writing the full multi-panel grid that `output/plots.py` builds, and
their tooltips say so.

The sub-views live in their own modules (`results_fields`,
`results_gauges`, `results_anim`) and the writing in `exports`, so each
is testable without building a window.
"""

import os
import threading

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QLineEdit, QStackedWidget,
                               QWidget)

from ..viz3d import MISSING_MSG, pyvista_available
from . import dialogs, exports
from .bridge import ThreadBridge
from .results_anim import AnimView
from .results_fields import FieldsView
from .results_gauges import GaugesView
from .view3d_host import View3DHost
from .widgets import Card, Segmented, button, hbox, label, vbox

#: longest label the picker shows in full; anything longer is elided
#: there and kept whole in the item's tooltip
PICKER_MAX = 34

#: (text, icon, kind) for the export row, in the order they sit
EXPORT_BUTTONS = (('Profile', 'curve', 'profile'),
                  # the kind stays 'gif'; the writer follows whatever
                  # extension the dialog returns
                  ('Animation', 'film', 'gif'),
                  ('VTK', 'cube', 'vtk'),
                  ('Summary CSV', 'table', 'summary'),
                  ('Gauges TSV', 'table', 'tsv'),
                  ('Field CSV', 'table', 'fieldcsv'),
                  ('Report', 'image', 'report'),
                  ('PNGs', 'image', 'pngs'))

#: what each export writes, said once so the buttons are not a guess.
#: 'pngs' and 'report' are explicit that the file is NOT what is on
#: screen: the screen shows one field, the file the whole grid.
EXPORT_HELP = {
    'profile': 'Save the final state for a later stage to start from.',
    'gif': 'Write the recorded frames as a video, using the colour '
           'scale set in the Animation view.',
    'vtk': 'Convert the blastFoam case to VTK for ParaView.',
    'summary': 'Per-gauge peak, arrival, phase and impulse as CSV.',
    'tsv': 'The raw gauge time histories.',
    'fieldcsv': 'Every field map as a long-format CSV, one file per '
                'field.',
    'report': 'One self-contained HTML file: the FULL snapshot grid, '
              'the gauge table and the case, not just the panel on '
              'screen.',
    'pngs': 'The FULL multi-panel snapshot grid as PNGs, not just the '
            'single panel on screen.',
}

VIEWS = ('Fields', 'Gauges', 'Animation', '3D')


class ResultEntry:
    def __init__(self, label, dim, result):
        self.label = label
        self.display = label
        self.dim = dim
        self.result = result


def elide_middle(text, width=PICKER_MAX):
    """Elide the MIDDLE of a long label: the tail carries the dimension,
    the '(stopped)' note and the ' #2' de-duplication marker, all of
    which a trailing ellipsis would eat."""
    if len(text) <= width:
        return text
    keep = width - 1
    head, tail = (keep + 1) // 2, keep // 2
    return text[:head] + '…' + text[len(text) - tail:]


class ResultsPanel(QWidget):
    def __init__(self, viewer_link=None, log_fn=print, mode=None,
                 on_resume=None, bridge=None, parent=None):
        super().__init__(parent)
        self._entries = []
        self._log = log_fn
        self._on_resume = on_resume
        # the post-mortem loader runs on a worker thread and must not
        # touch a widget from there; without a bridge it falls back to
        # calling straight through, which is only safe in tests
        self._bridge = bridge if bridge is not None else ThreadBridge(self)
        self._run_browser = None
        # a standalone panel (tests) shows everything; the app narrows
        # this the moment the solver mode arrives
        self._solver_mode = 'blastfoam'

        root = vbox(self, margins=(0, 0, 0, 0))
        root.addWidget(label('Results', 'h1'))

        top = Card()
        root.addWidget(top)
        bar = hbox()
        bar.addWidget(label('Result', 'muted'))
        self.sel = QComboBox()
        self.sel.setMinimumWidth(250)
        self.sel.currentIndexChanged.connect(lambda *_: self.refresh())
        bar.addWidget(self.sel)
        self._remove_btn = button('Remove', 'minus', width=104, height=32,
                                  on_click=self.remove_current)
        bar.addWidget(self._remove_btn)
        self._view3d_btn = button('3D Viewer', 'cube', 'primary', width=124,
                                  height=32, on_click=self.open_3d)
        bar.addWidget(self._view3d_btn)
        self._foam_runs_btn = button('Foam runs…', 'folder', width=140,
                                     height=32,
                                     on_click=self.open_run_browser)
        bar.addWidget(self._foam_runs_btn)
        bar.addStretch(1)
        top.add_layout(bar)

        bar2 = hbox()
        bar2.addWidget(label('Export', 'muted'))
        self._export_btns = {}
        for text, glyph, kind in EXPORT_BUTTONS:
            b = button(text, glyph, width=118 if kind == 'summary' else 106,
                       height=32, on_click=lambda k=kind: self.export(k))
            bar2.addWidget(b)
            self._export_btns[kind] = b
        bar2.addStretch(1)
        top.add_layout(bar2)

        # A line of the user's own ABOVE the automatic title, on every
        # figure this tab shows or exports. It belongs to this
        # presentation of a result, not to the case.
        bar3 = hbox()
        bar3.addWidget(label('Title', 'muted'))
        self.title_box = QLineEdit()
        self.title_box.setMinimumWidth(420)
        self.title_box.setPlaceholderText(
            'optional - added above the automatic title')
        self.title_box.textChanged.connect(lambda *_: self._title_changed())
        bar3.addWidget(self.title_box)
        bar3.addStretch(1)
        top.add_layout(bar3)

        views = Card(pad=12)
        root.addWidget(views, 1)
        self.view_seg = Segmented(list(VIEWS))
        self.view_seg.setMaximumWidth(420)
        self.view_seg.changed.connect(self._view_selected)
        views.add(self.view_seg)

        self.stack = QStackedWidget()
        views.add(self.stack, 1)
        self.fields = FieldsView(on_change=self._mesh_changed)
        self.gauges = GaugesView()
        self.anim = AnimView()
        self.view3d = (View3DHost(viewer_link, 'results', log_fn=log_fn)
                       if viewer_link is not None else QWidget())
        self._views = {'Fields': self.fields, 'Gauges': self.gauges,
                       'Animation': self.anim, '3D': self.view3d}
        for w in self._views.values():
            self.stack.addWidget(w)
        self.view_seg.set('Fields')
        self.stack.setCurrentWidget(self.fields)

        self._sync_export_buttons(None)
        if mode is not None:
            mode.subscribe(self.set_solver_mode)
            self.set_solver_mode(mode.get())

    # ── entries ──────────────────────────────────────────────────────────
    def _unique_label(self, text):
        """Number a duplicate. The picker matched entries by their text,
        so two identical labels made the second unreachable - selecting
        it always returned the first, which is exactly what loading the
        same foam run twice did."""
        taken = {e.label for e in self._entries}
        if text not in taken:
            return text
        n = 2
        while f'{text} #{n}' in taken:
            n += 1
        return f'{text} #{n}'

    def _repopulate(self, keep=None):
        """Rebuild the picker, the entry itself in each item's data so
        `current()` never has to match on text."""
        taken = set()
        self.sel.blockSignals(True)
        self.sel.clear()
        for ent in self._entries:
            d, n = elide_middle(ent.label), 2
            base = d
            while d in taken:
                d = f'{base} ({n})'
                n += 1
            taken.add(d)
            ent.display = d
            self.sel.addItem(d, ent)
            if d != ent.label:
                self.sel.setItemData(self.sel.count() - 1, ent.label,
                                     Qt.ToolTipRole)
        if self._entries:
            idx = (self._entries.index(keep) if keep in self._entries
                   else len(self._entries) - 1)
            self.sel.setCurrentIndex(idx)
        self.sel.blockSignals(False)

    def add_result(self, text, dim, result):
        ent = ResultEntry(self._unique_label(text), dim, result)
        self._entries.append(ent)
        self._repopulate(keep=ent)
        self.refresh()
        return ent

    def entries(self):
        return list(self._entries)

    def current(self):
        return self.sel.currentData()

    def remove_current(self):
        """Drop the selected result. They used to accumulate for a whole
        session with no way to free their frames."""
        ent = self.current()
        if ent is None:
            self._log('Remove: select a result first.')
            return
        self.anim.stop_play()
        self._entries.remove(ent)
        self._repopulate()
        if self._entries:
            self.refresh()
        else:
            self.clear_views()
        self._log(f'Removed result: {ent.label}')

    def clear_views(self):
        self.fields.clear()
        self.gauges.clear()
        self.anim.placeholder('')
        if isinstance(self.view3d, View3DHost):
            self.view3d.cancel_feed()
        self._sync_export_buttons(None)

    # ── views ────────────────────────────────────────────────────────────
    def _view_selected(self, value):
        w = self._views.get(value)
        if w is not None:
            self.stack.setCurrentWidget(w)

    def show_view(self, name):
        """Switch sub-view programmatically (the QA harness uses this)."""
        self.view_seg.set(name)
        self._view_selected(name)

    def view(self):
        return self.view_seg.get()

    def title_extra(self):
        return self.title_box.text().strip() or None

    def _title_changed(self):
        extra = self.title_extra()
        for v in (self.fields, self.gauges, self.anim):
            v.set_title_extra(extra)
        # retitle only what is on screen; the animation stays on the
        # frame it is showing - retyping a title must not jump the
        # replay back to the start
        view = self.view()
        if view == 'Fields':
            self.fields.redraw()
        elif view == 'Gauges':
            self.gauges.redraw()
        elif view == 'Animation':
            self.anim.show_frame(self.anim.frame())

    def _mesh_changed(self):
        self.anim.set_show_mesh(self.fields.show_mesh.isChecked())

    def refresh(self):
        ent = self.current()
        if ent is None:
            # a picker that matches nothing used to leave the export row
            # exactly as the previous result had left it, so every button
            # stayed enabled and did nothing when pressed
            self._sync_export_buttons(None)
            return
        self.anim.stop_play()
        self._sync_export_buttons(ent)
        extra = self.title_extra()
        for v in (self.fields, self.gauges, self.anim):
            v.set_title_extra(extra)
        self.fields.set_result(ent)
        self.gauges.set_result(ent)
        self.anim.set_result(
            ent, show_mesh=self.fields.show_mesh.isChecked())

    def set_solver_mode(self, m):
        """Hide the blastFoam-only launchers in native mode. Per-result
        gating of the VTK button is unchanged - configuring a hidden
        button is harmless, and a post-mortem load still works in native
        mode; only the launcher is out of the way."""
        self._solver_mode = m
        foam = (m == 'blastfoam')
        self._foam_runs_btn.setVisible(foam)
        self._export_btns['vtk'].setVisible(foam)

    def _sync_export_buttons(self, ent):
        """Only offer an export that can actually run for this result.
        Every button used to stay enabled: with nothing selected they
        were silent no-ops, and Profile on a planar 2D result opened a
        file dialog and then failed in the log."""
        for kind, b in self._export_btns.items():
            good = exports.can(kind, ent)
            b.setEnabled(bool(good))
            # a greyed button has to say why
            b.setToolTip(EXPORT_HELP.get(kind, '') if good
                         else exports.why_not(kind, ent))

    def export_enabled(self, kind):
        return self._export_btns[kind].isEnabled()

    # ── exports ──────────────────────────────────────────────────────────
    def export_opts(self):
        opts = dict(show_mesh=bool(self.fields.show_mesh.isChecked()),
                    title_extra=self.title_extra())
        opts.update(self.anim.export_opts())
        return opts

    def export(self, kind, threaded=True):
        return exports.export(
            kind, self.current(), self.export_opts(), log=self._log,
            parent=self, on_error=dialogs.show_error, threaded=threaded)

    # ── the embedded 3D viewer ───────────────────────────────────────────
    def open_3d(self):
        ent = self.current()
        if ent is None:
            return
        if ent.dim != 3:
            self._log('3D Viewer: select a 3D result.')
            return
        if not pyvista_available():
            self._log(MISSING_MSG)
            return
        if not ent.result.snapshots:
            self._log('3D Viewer: this result has no snapshots.')
            return
        if not isinstance(self.view3d, View3DHost):
            self._log('3D Viewer: no viewer link in this panel.')
            return
        try:
            if self.view3d.feed_result(ent.result):
                self.show_view('3D')
                self._log(f'3D view loaded: {ent.label} '
                          f'({len(ent.result.snapshots)} snapshots)')
        except Exception as exc:
            self._log(f'3D view failed: {exc}')

    # ── post-mortem load of a finished blastFoam case dir ────────────────
    def open_run_browser(self):
        from .run_browser import FoamRunBrowser
        win = self._run_browser
        if win is not None and win.isVisible():
            win.raise_()
            win.activateWindow()
            win.refresh()
            return win
        self._run_browser = FoamRunBrowser(
            self, on_load=self.load_foam_run_path, log=self._log,
            on_resume=self._on_resume, bridge=self._bridge)
        self._run_browser.show()
        return self._run_browser

    def load_foam_run_path(self, path):
        """Post-mortem load of one run dir (UNC / posix / bare name) off
        the GUI thread, then add it to the results list."""
        if not path:
            return
        self._log(f'Loading foam run {path} ...')

        def work():
            try:
                from ..solvers.foam.postmortem import load_run
                res = load_run(path)
            except Exception as exc:
                self._log(f'Load failed: {exc}')
                return
            dim = 1 if 'radius_m' in res.meta else (
                3 if 'z_c' in res.meta else 2)
            name = (str(res.meta.get('name') or '').strip()
                    or os.path.basename(str(path).rstrip('/' + os.sep)))
            res.meta.setdefault('name', name)
            text = f'{name} (loaded, {dim}D)'
            # widgets only on the GUI thread
            self._bridge.post(self.add_result, text, dim, res)
            self._log(f'Loaded: {text} ({len(res.snapshots)} snapshots)')

        threading.Thread(target=work, daemon=True).start()

    def shutdown(self):
        self.anim.stop_play()
        if isinstance(self.view3d, View3DHost):
            self.view3d.shutdown()
