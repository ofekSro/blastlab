"""The Chain screen: run 1D -> 2D -> 3D as one workflow (GUI-9, plan
§8, board Chain).

OUT-1: a chain writes into the Run tab's model folder (the workspace box
is gone, owner decision 14): each stage into `<MODEL>\\1d`, `2d`, `3d`,
with its own MODEL.json, and the profile hand-offs at the model root.

GUI-9 lays it out as the board does: the route buttons and a pipeline of
stage cards joined by hand-off arrows (`chain_pipeline`), Run chain, and
under them one stage editor in the 01 Setup layout (`chain_stage`), with
live per-stage checks (`chain_route.stage_checks`, the Setup's 300 ms
debounce) and Copy from 01 Setup / Load case… per stage. A new stage
starts from 01 Setup's charge, material and solver (owner decision).

Two things are deliberate here and both were paid for in Tk:

- **One injectable error sink.** Five `showerror` calls became
  `self.error_sink(title, lines)`, and `_run()` returns False on
  refusal. A test asserts on the return value and the recorded lines,
  never on a modal.
- **The refusal reaches the status line and the log BEFORE any dialog is
  attempted.** `QMessageBox`'s static calls spin a nested event loop and
  will hang an offscreen driver exactly as Tk's `messagebox` did (P2-8),
  so the dialog is strictly last and its failure cannot swallow the
  reason.

The order inside `_run()` is load-bearing and stays literal: the model
folder is created only once the run is certain to start - after every
check here, by the window (`on_run_chain`), which asks before it
overwrites an existing model.
"""

import html
import os

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

from ..core import mode as mode_mod
from ..core import chain
from ..core.chain import stage_errors
from ..services import model_folder
from . import chain_route, dialogs, theme
from .chain_pipeline import HandoffArrow, Pipeline, RouteBar, StageCard
from .chain_stage import STAGE_NODE, StageEditor
from .results_list import ElidedLabel
from .widgets import label

HINT = ('The chain runs the route\'s stages in order, into the model folder '
        'set on the Run tab (Runs folder and Model): each stage writes '
        '<MODEL>\\1d, 2d or 3d. The profile hand-offs are wired '
        'automatically at the model root: 1D writes handoff_1d_to_2d.txt, '
        'the 2D stage remaps it (axisymmetric) and writes '
        'handoff_2d_to_3d.npz, and the 3D stage remaps that. The 2D burst '
        'height is taken from the 2D form; the 3D burst height comes from '
        'the 2D profile. 1D and 3D without 2D hand handoff_1d_to_3d.txt '
        'straight to the 3D stage; the 3D burst height comes from the 3D '
        'form.')

#: added to a model-folder refusal: the boxes live on another tab
WHERE_BOXES = 'The Runs folder and Model boxes are on the Run tab.'

#: board Chain line 60
SEED_CAPTION = 'New stages take the charge, material and solver from 01 Setup.'

#: the chain's own start values, {stage dim: {field: text}}, applied once
#: when the editors are built (01 Setup's defaults do not change). Stage
#: 1's Domain radius starts at the board's 1.5 m, so the default 1 -> 2 -> 3
#: route opens with card 2 clean: at the form's 10 m the 1D stage hands off
#: beyond stage 2's 4 x 4 m box (S2-1). Checked 2026-10-11: 1.5 m brings no
#: error or warning that 10 m does not, native / blastFoam, unprobed and
#: probed. Stage 3's Lz stays 1.5 (the 4.0 m seed trips the blastFoam cell
#: cap unprobed; GUI-13 A1).
CHAIN_SEED = {1: {'radius_m': '1.5'}}

#: the live checks' debounce: the Setup's (`MainWindow._validate_timer`)
CHECK_MS = 300

#: Run chain (board line 89: 176 x 56)
RUN_W = 176
RUN_H = 56

CASE_FILTER = 'blastlab case (*.json);;All files (*.*)'

#: why Copy from 01 Setup is off (plan §8.1, UX-16)
COPY_TIP = 'Fill this stage from the case open in 01 Setup'
COPY_BAD = '01 Setup has errors - fix them first.'
COPY_HD13 = '01 Setup holds an HD 1.3 case.'
COPY_NONE = 'There is no 01 Setup to copy from.'


def _plural(n, word):
    return f'{n} {word}{"" if n == 1 else "s"}'


def card_state(chk):
    """(state, text) of a stage card from its live check (decision
    D-row): `● N errors` (parse errors count) / `● N warnings` /
    `● case OK`."""
    if chk.n_errors:
        return 'error', f'● {_plural(chk.n_errors, "error")}'
    if chk.warnings:
        return 'warn', f'● {_plural(len(chk.warnings), "warning")}'
    return 'ok', '● case OK'


def folder_text(runs, model):
    """Where the files go (D47's rule): `<Runs folder>\\<Model>\\` until
    both boxes are filled, then the model folder and a separator."""
    runs, model = str(runs or '').strip(), str(model or '').strip()
    if not runs or not model:
        return '<Runs folder>\\<Model>\\'
    return model_folder.folder_for(runs, model) + os.sep


class _RunButton(QPushButton):
    """Run chain: the play glyph and the text on `accent` (board line 89);
    the glyph follows the enabled state."""

    def __init__(self, parent=None):
        super().__init__('Run chain', parent)
        self.setObjectName('chainrun')
        self.setFixedSize(RUN_W, RUN_H)
        self.setCursor(Qt.PointingHandCursor)
        self.setIconSize(QSize(15, 15))
        self._paint_icon()
        theme.signals.changed.connect(self._paint_icon)

    def _paint_icon(self, _mode=None):
        self.setIcon(theme.icon('play', 15, color='on_accent'
                                if self.isEnabled() else 'muted'))

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == event.Type.EnabledChange:
            self._paint_icon()


class ChainPanel(QWidget):
    #: the route key ('123', '13', '12', '23') after every change
    route_changed = Signal(str)
    #: the Run chain line's folder link was clicked (UXR-12, D222): the
    #: window shows 02 Run with the Model box focused
    model_link_clicked = Signal()

    def __init__(self, on_run_chain=None, mode=None, log_fn=print,
                 error_sink=None, model_source=None, setup_source=None,
                 case_reader=None, parent=None):
        super().__init__(parent)
        #: on_run_chain([(dim, case), ...]) -> False when the window did
        #: not start it (it said why); anything else = started
        self._on_run_chain = on_run_chain or (lambda stages: None)
        #: () -> (runs_dir, model): the Run tab's two boxes (OUT-1)
        self._model_source = model_source or (lambda: ('', ''))
        #: () -> the 01 Setup case, or None when it does not parse; None
        #: (a standalone panel): no seeding, no Copy (GUI-9)
        self._setup_source = setup_source
        #: (path) -> case or None after its own error dialog (Load case…)
        self._case_reader = case_reader or self._read_case
        self._running = False       # a run is live somewhere in the app
        self._busy = False          # an HD 1.3 assessment is working
        self._log = log_fn
        self.error_sink = error_sink or self._default_sink
        # every stage starts on the app-level solver and can be
        # overridden per stage (a native 2D stage may follow a blastFoam
        # 1D one); a global change presets all three again
        self._mode = mode if mode is not None else mode_mod.SolverMode()
        self._route = chain_route.DEFAULT_ROUTE
        self._stage = 1
        self._node = STAGE_NODE      # the node last selected in a stage
        # GUI-9: a stage never edited, loaded or copied takes 01 Setup's
        # charge, material and solver; programmatic writes (seeding, a
        # global solver change) run `_quiet` and touch nothing
        self._touched = {1: False, 2: False, 3: False}
        self._quiet = 1             # the forms fire on_change while built
        self._shown = False
        self._stale = False         # a check came due while off screen
        self._hw_pending = False    # the WSL hardware probe is running
        self._checks = {}
        # the one timer of the screen: the live checks' debounce
        self._check_timer = QTimer(self)
        self._check_timer.setSingleShot(True)
        self._check_timer.setInterval(CHECK_MS)
        self._check_timer.timeout.connect(self._run_checks)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        # ── top: route, pipeline, Run chain (board lines 52-96) ──────────
        top = QFrame()
        top.setObjectName('chaintop')
        tl = QVBoxLayout(top)
        tl.setContentsMargins(4, 0, 4, 14)
        tl.setSpacing(12)
        row = QHBoxLayout()
        row.setSpacing(14)
        route_lbl = QLabel('Route')
        route_lbl.setObjectName('chainfield')
        row.addWidget(route_lbl)
        self.route_bar = RouteBar()
        self.route_bar.set(self._route)
        self.route_bar.picked.connect(self.set_route)
        #: the route group (its tooltip is the old HINT line) and its
        #: buttons, by key (the QA harness reads them)
        self.route_group = self.route_bar
        self.route_group.setToolTip(HINT)
        self.route_btns = self.route_bar.btns
        # UXR-12 (D222): each route says in one line what it hands on
        for key, btn in self.route_btns.items():
            btn.setToolTip(chain_route.ROUTE_TIPS[key])
        row.addWidget(self.route_bar)
        self.caption = ElidedLabel(SEED_CAPTION, mode=Qt.ElideRight)
        self.caption.setObjectName('chaincaption')
        self.caption.set_tip(SEED_CAPTION)
        row.addWidget(self.caption, 1)
        tl.addLayout(row)

        pipe_row = QHBoxLayout()
        pipe_row.setSpacing(0)
        self.pipeline = Pipeline()
        pipe_row.addWidget(self.pipeline, 1)
        pipe_row.addSpacing(12)
        run_col = QVBoxLayout()
        run_col.setSpacing(8)
        run_col.addStretch(1)
        self.run_btn = _RunButton()
        # F5 runs the chain while this screen is shown (UXR-7, D205)
        self.run_btn.setToolTip('Run the chain (F5)')
        self.run_btn.clicked.connect(lambda *_: self.run())
        run_col.addWidget(self.run_btn, 0, Qt.AlignHCenter)
        self.run_line = QLabel('')
        self.run_line.setObjectName('chainrunline')
        self.run_line.setAlignment(Qt.AlignHCenter)
        self.run_line.setWordWrap(True)
        self.run_line.setFixedWidth(RUN_W)
        # UXR-12 (D222): the line is a link to the Model box on 02 Run,
        # where the chain's folder is set
        self.run_line.setTextFormat(Qt.RichText)
        self.run_line.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
        self.run_line.linkActivated.connect(
            lambda *_a: self.model_link_clicked.emit())
        self._run_line_text = ''
        theme.signals.changed.connect(self._retheme_run_line)
        run_col.addWidget(self.run_line)
        run_col.addStretch(1)
        pipe_row.addLayout(run_col)
        tl.addLayout(pipe_row)
        # the refusal always lands here, whatever happens to the dialog;
        # full width under the pipeline (a 176 px column would make a
        # long refusal twelve lines tall), hidden while empty
        self.status = label('', 'small')
        self.status.setWordWrap(True)
        self.status.setVisible(False)
        tl.addWidget(self.status)
        root.addWidget(top)

        self.cards = {}
        for d in (1, 2, 3):
            card = StageCard(d)
            card.clicked.connect(self.focus_stage)
            card.setVisible(False)
            self.cards[d] = card
        self.arrows = []

        # ── the stage editors (board lines 98-217), one per stage ────────
        self._editors_box = QWidget()
        el = QVBoxLayout(self._editors_box)
        el.setContentsMargins(0, 0, 0, 0)
        el.setSpacing(0)
        self.editors, self.forms, self.stage_solver = {}, {}, {}
        self._stage_seg_solver, self._compat = {}, {}
        self._compat_bad = False
        for d in (1, 2, 3):
            ed = StageEditor(d, mode=self._mode.get(),
                             on_change=lambda d=d: self._form_changed(d))
            ed.setVisible(False)
            ed.solver_picked.connect(
                lambda m, d=d: self._solver_clicked(d, m))
            ed.copy_clicked.connect(lambda d=d: self.copy_from_setup(d))
            ed.load_clicked.connect(lambda d=d: self.load_case(d))
            ed.focus_requested.connect(self._focus_requested)
            el.addWidget(ed)
            self.editors[d] = ed
            #: the same object API as before GUI-9: one CaseForm per stage
            self.forms[d] = ed.form
            self._stage_seg_solver[d] = ed.solver_seg
            # N5-4: the hand-off refusal, said where the choice is made
            # (the stage's 00 Stage page). stage_errors is still the
            # authority (run() re-checks), but a refusal that only appears
            # after Run chain is a refusal the user meets having already
            # filled three forms.
            self._compat[d] = ed.compat
            self.stage_solver[d] = self._mode.get()
            ed.solver_seg.set(mode_mod.label(self.stage_solver[d]))
        root.addWidget(self._editors_box, 1)
        # GUI-14 (a): the chain's own start values, once, while still quiet
        # (the stage stays untouched; a route change never reapplies them)
        for d, fields in CHAIN_SEED.items():
            for name, value in fields.items():
                self.forms[d].v[name].set(value)
        self._quiet = 0

        self._mode.subscribe(self._on_global_mode)
        self._apply_route()
        self.focus_stage(1)
        self._refresh_compat()
        self._refresh_copy()

    # ── the error sink ───────────────────────────────────────────────────
    def _default_sink(self, title, lines):
        dialogs.show_error(title, '\n'.join(lines), self)

    def _set_status(self, text):
        self.status.setText(text)
        self.status.setVisible(bool(text))

    def _refuse(self, lines):
        """Say no, in this order: the status line, the log, and only then
        a dialog. A dialog that hangs or raises must not be able to
        swallow the reason."""
        lines = [str(ln) for ln in lines if str(ln).strip()]
        # one line of sentences: each ends with a stop (GUI QA V2)
        said = [ln.rstrip() if ln.rstrip()[-1] in '.:!?'
                else ln.rstrip() + '.' for ln in lines]
        self._set_status(' '.join(' '.join(said).split())[:300])
        for ln in lines:
            self._log(f'Chain: {ln}')
        try:
            self.error_sink('Chain', lines)
        except Exception as exc:
            self._log(f'Chain: (the dialog failed: {exc})')
        return False

    # ── hand-off compatibility (N5-4) ────────────────────────────────────
    def _refresh_compat(self):
        """Show/clear the native -> blastFoam refusal per stage.

        Deliberately reads `self.stage_solver` and `checked()` and NOT
        `get_case()`: a half-typed field makes get_case raise, which is
        exactly when a user is most likely to be clicking around.
        """
        bad = dict(chain.handoff_conflicts(self.checked(), self.stage_solver))
        for d in (1, 2, 3):
            msg = bad.get(d, '')
            self._compat[d].setText(msg)
            self._compat[d].setVisible(bool(msg))
            if msg:
                self._compat[d].setStyleSheet(
                    f'color: {theme.cur("error")};')
        self._compat_bad = bool(bad)
        if bad:
            self._set_status(f'Stage {min(bad)}: {bad[min(bad)]}')
        elif self.status.text().startswith('Stage '):
            self._set_status('')
        self._sync_run_btn()

    def _sync_run_btn(self):
        """The ONE owner of the Run button's enabled state. Two owners
        (set_running and the compat check) would fight, and whichever
        ran last would win."""
        self.run_btn.setEnabled(not self._running and not self._busy
                                and not self._compat_bad)

    # ── per-stage solver ─────────────────────────────────────────────────
    def set_stage_solver(self, d, m):
        m = mode_mod.normalize(m)
        self.stage_solver[d] = m
        self._stage_seg_solver[d].set(mode_mod.label(m))   # silent
        self._quiet += 1
        try:
            self.forms[d].set_mode(m)
        finally:
            self._quiet -= 1
        self.cards[d].set_solver(mode_mod.label(m))
        self.editors[d]._sync_tree_nodes()
        self._refresh_compat()
        self.schedule_checks()

    def _solver_clicked(self, d, m):
        """The stage's own solver switch: an edit of the stage."""
        self.set_stage_solver(d, m)
        self._touched[d] = True

    def set_stage_case(self, d, case):
        """Fill stage `d` from a Case, adopting its solver. The stage
        counts as edited from then on (no 01 Setup seeding over it)."""
        self._quiet += 1
        try:
            self.set_stage_solver(d, getattr(case, 'solver', 'native'))
            self.forms[d].set_case(case)
        finally:
            self._quiet -= 1
        self._touched[d] = True
        self.schedule_checks()

    def _on_global_mode(self, m):
        for d in (1, 2, 3):
            self.set_stage_solver(d, m)
        self._refresh_compat()      # after the loop: mid-loop the set
        #                             is transiently mixed

    def touched(self, d):
        """True once stage `d` was edited, loaded or copied (tests)."""
        return self._touched[int(d)]

    # ── the route (GUI-9, plan §8.1) ─────────────────────────────────────
    def route(self):
        """The route's key: '123', '13', '12' or '23'."""
        return self._route

    def set_route(self, key):
        """Choose route `key`; ValueError for anything that is not a
        route, with the route and the buttons left as they were."""
        key = str(key)
        chain_route.route_dims(key)              # ValueError first
        changed = key != self._route
        self._route = key
        self.route_bar.set(key)
        if changed:
            self._apply_route()
            if self._stage not in self.checked():
                # board script: the selection falls back to 2, else the
                # last stage of the route
                dims = self.checked()
                self.focus_stage(2 if 2 in dims else dims[-1])
            self._seed()
        self._refresh_compat()
        self.schedule_checks()
        if changed:
            self.route_changed.emit(key)

    def checked(self):
        """The route's stages, in order (the compat check and the QA
        harness read the stage list through this)."""
        return list(chain_route.route_dims(self._route))

    def _apply_route(self):
        """Lay the route's cards and arrows out, number them, and feed
        every stage but the first (its form hides Initialize from and
        Profile file)."""
        dims = self.checked()
        self.arrows = [HandoffArrow(a, b, n_stages=len(dims))
                       for a, b in zip(dims, dims[1:])]
        for d, card in self.cards.items():
            card.setVisible(False)
            card.setParent(self.pipeline)
        self.pipeline.set_items([self.cards[d] for d in dims], self.arrows)
        for i, d in enumerate(dims):
            self.cards[d].set_number(f'{i + 1:02d}')
            self.cards[d].setVisible(True)
        for d in (1, 2, 3):
            self.forms[d].set_fed(d in dims and dims.index(d) > 0)
        self._sync_titles()
        self._update_run_line()

    def _sync_titles(self):
        dims = self.checked()
        for d in (1, 2, 3):
            title = chain_route.stage_title(
                d, self.forms[2].v['geometry'].get() if d == 2 else '')
            self.cards[d].set_title(title)
            self.cards[d].set_solver(mode_mod.label(self.stage_solver.get(
                d, self._mode.get())))
            num = f'{dims.index(d) + 1:02d}' if d in dims else '00'
            self.editors[d].set_position(num, title)

    def _update_run_line(self):
        n = len(self.checked())
        _runs, model = self._model_source()
        model = str(model or '').strip()
        # an unbroken model name would overrun the 176 px column: elided
        # in the middle to fit its own line, the whole in the tooltip
        self.run_line.ensurePolished()
        fm = self.run_line.fontMetrics()
        shown = fm.elidedText(model, Qt.ElideMiddle,
                              RUN_W - fm.horizontalAdvance('\\\\') - 4)
        head, tail = ((f'{n} stages · into ', f'\\{shown}\\') if model
                      else (f'{n} stages · ', 'set the Model on 02 Run'))
        self._run_line_text = head + tail
        # the folder part is the link (UXR-12, D222), in the accent text
        # colour, so it reads as one in both themes
        self.run_line.setText(
            f'{html.escape(head)}<a href="model" style="color: '
            f'{theme.cur("accent_text")}; text-decoration: none;">'
            f'{html.escape(tail)}</a>')
        self.run_line.setToolTip(f'Into {model}' if shown != model else
                                 'Set the Model on 02 Run')

    def run_line_text(self):
        """The line as plain text (it is shown as a link)."""
        return self._run_line_text

    def _retheme_run_line(self, _mode=None):
        self._update_run_line()           # the link's colour

    # ── navigation ───────────────────────────────────────────────────────
    def focus_stage(self, d):
        """Bring stage `d` forward: its card selected, its editor shown.
        The node selected in the stage before stays selected when this
        stage has it (05 stays 05), else 00 Stage; the first show of a
        stage is 00 Stage. A dialog naming 'Stage 2' used to leave the
        switcher wherever it happened to be."""
        d = int(d)
        if self.editors.get(self._stage) is not None \
                and self._stage != d:
            self._node = self.editors[self._stage].selected_node() \
                or STAGE_NODE
        self._stage = d
        for k, card in self.cards.items():
            card.set_selected(k == d)
        for k, ed in self.editors.items():
            ed.setVisible(k == d)
        ed = self.editors[d]
        if not ed._shown_once:
            ed._shown_once = True
            ed.select_node(STAGE_NODE)
        elif ed.has_node(self._node):
            ed.select_node(self._node)
        else:
            ed.select_node(STAGE_NODE)
        # D25: a warned stage opens with its Checks in view
        if ed.selected_node() == STAGE_NODE and ed.has_alerts():
            ed.reveal_checks()

    def _focus_requested(self, d, kind, key):
        """D24: a Checks line was clicked - show the stage that holds the
        fix (the 1D stage's radius for S2-1) and focus the field or gauge."""
        d = int(d)
        if d not in self.editors or d not in self.checked():
            return
        self.focus_stage(d)
        self.editors[d].focus(kind, key)

    def stage(self):
        return self._stage

    def editor(self, d=None):
        return self.editors[self._stage if d is None else int(d)]

    # ── live checks (UX-16, plan §8.1) ───────────────────────────────────
    def schedule_checks(self):
        """(Re)start the one debounce: every form, route, solver and
        Run-tab model change lands here."""
        self._check_timer.start()

    def set_hw_pending(self, on):
        """D28: the WSL hardware probe is running (`on`) or ended. While
        it runs a blastFoam stage's `Large grid` line reads as a
        provisional note (`chain_route.provisional_grid`); the checks run
        again when it ends."""
        on = bool(on)
        if on == self._hw_pending:
            return
        self._hw_pending = on
        self.schedule_checks()

    def _form_changed(self, d):
        if not self._quiet:
            self._touched[d] = True
        if hasattr(self, '_check_timer'):
            self._check_timer.start()

    def _live_hand(self, dims):
        runs, model = self._model_source()
        folder = ''
        if not model_folder.check(runs, model):
            folder = model_folder.folder_for(runs, model)
        target = model_folder.Target(runs_dir=str(runs or ''),
                                     model=str(model or ''), folder=folder)
        return model_folder.handoff_paths(target, dims)

    def _run_checks(self):
        """Every stage of the route: parse, wire, validate - what run()
        will say - and show it on the cards, trees, pills, headers and
        Checks lists. Nothing is written."""
        self._check_timer.stop()
        if not self.isVisible():
            # off screen: nothing to show; the next show runs them
            self._stale = True
            return
        self._stale = False
        dims = self.checked()
        checks = chain_route.stage_checks(
            dims, {d: self.forms[d] for d in dims}, self._live_hand(dims))
        if self._hw_pending:
            for chk in checks.values():
                chain_route.provisional_grid(chk)
        self._checks = checks
        self._sync_titles()
        runs, model = self._model_source()
        # a zero-width space between the path's characters lets the note
        # wrap inside a long folder path; unbroken, the path was the
        # page's minimum and widened the 340 px column (D19) to ~490
        where = '​'.join(folder_text(runs, model))
        note = (f'Every stage is checked live, like 01 Setup. The files go '
                f'to {where} (1d, 2d, 3d, and the hand-offs at its root). '
                f'If that folder already exists, the app asks before '
                f'overwriting.')
        for d in dims:
            prev, nxt = chain_route.neighbours(dims, d)
            chk = checks[d]
            self.cards[d].set_state(*card_state(chk))
            if chk.case is not None:
                key = chain_route.key_line(chk.case, prev)
                self.cards[d].set_key(key)
            src = checks[prev].case if prev in checks else None
            # D27: S2-1 (a 1D hand-off reaching the next stage) is fixed in
            # the 1D stage's radius too
            fed = d == 1 and nxt in checks and bool(checks[nxt].reach)
            self.editors[d].show_check(chk, self.stage_solver[d], prev, nxt,
                                       note, source=src, fed_reach=fed)
        self._update_run_line()
        self._refresh_copy()

    def checks(self):
        """{dim: chain_route.StageCheck} of the last live check (tests)."""
        return dict(self._checks)

    def showEvent(self, event):
        super().showEvent(event)
        self._seed()
        self._refresh_copy()
        if not self._shown or self._stale:
            # the screen's first show runs the checks at once, and so
            # does a show after a change made while it was off screen
            self._shown = True
            self._run_checks()

    # ── seeding, Copy from 01 Setup, Load case… (plan §8.1, UX-16) ───────
    def _setup_case(self):
        """The 01 Setup case, or None: no source (a standalone panel) or
        a form that does not parse (ValueError, as `get_case()` says it).
        Anything else is a bug and propagates to the crash log - a broad
        except here would show it as `01 Setup has errors`."""
        if self._setup_source is None:
            return None
        try:
            return self._setup_source()
        except ValueError:
            return None

    def _seed(self):
        """Every untouched stage of the route takes 01 Setup's charge,
        material and solver; everything else keeps the dimension's
        defaults. Not touched by it."""
        src = self._setup_case()
        if src is None or not getattr(src, 'dim', 0):
            return
        for d in self.checked():
            if not self._touched[d]:
                self._seed_stage(d, src)

    def _seed_stage(self, d, src):
        """01 Setup's charge (kg; a planar source or target gives none:
        kg/m is not kg), material and solver into stage `d`."""
        form = self.forms[d]
        planar_src = src.dim == 2 and getattr(src, 'geometry', '') == 'planar'
        planar_dst = d == 2 and form.v['geometry'].get() == 'planar'
        w = getattr(src, 'charge_kg' if src.dim == 1 else 'charge', None)
        self._quiet += 1
        try:
            if w is not None and not planar_src and not planar_dst \
                    and 'charge' in form.v:
                form.v['charge'].set(f'{float(w):g}')
            if getattr(src, 'material', None) and 'material' in form.v:
                form.v['material'].set(src.material)
            self.set_stage_solver(d, getattr(src, 'solver', 'native'))
        finally:
            self._quiet -= 1
        self.schedule_checks()

    def _refresh_copy(self):
        """Copy from 01 Setup is off, with the why-not as its tooltip,
        while 01 Setup does not parse or holds an HD 1.3 case."""
        if self._setup_source is None:
            on, tip = False, COPY_NONE
        else:
            src = self._setup_case()
            if src is None:
                on, tip = False, COPY_BAD
            elif not getattr(src, 'dim', 0):
                on, tip = False, COPY_HD13
            else:
                on, tip = True, COPY_TIP
        for ed in self.editors.values():
            ed.copy_btn.setEnabled(on)
            ed.copy_btn.setToolTip(tip)

    def _number(self, d):
        dims = self.checked()
        return f'{dims.index(d) + 1:02d}' if d in dims else f'0{d}'

    def copy_from_setup(self, d):
        """Stage `d` from the 01 Setup case: whole when it is the same
        dimension (its solver adopted), else the seeding rule. Asks only
        when the stage was edited. True when the stage changed."""
        src = self._setup_case()
        if src is None or not getattr(src, 'dim', 0):
            self._refresh_copy()
            return False
        if self._touched[d] and not dialogs.ask_yes_no(
                'Copy from 01 Setup',
                f'Replace stage {self._number(d)}\'s settings with 01 '
                f'Setup\'s?', self, yes='Replace', no='Keep'):
            return False
        if src.dim == d:
            self.set_stage_case(d, src)
        else:
            self._seed_stage(d, src)
        self._touched[d] = True
        return True

    def _read_case(self, path):
        """A standalone panel's reader: the case, or None after an error
        dialog (the window passes its own `_read_case_file`)."""
        from ..models.case import load_any_case
        try:
            return load_any_case(path)
        except Exception as exc:
            dialogs.show_error('Load case', f'Could not read {path}: {exc}',
                               self)
            return None

    def load_case(self, d):
        """Load case… into stage `d`: a case of the stage's dimension
        fills it; another dimension, or an HD 1.3 case, is refused with
        one sentence and the stage is unchanged. True when it loaded."""
        path = dialogs.open_file('Load case', CASE_FILTER, self)
        if not path:
            return False
        case = self._case_reader(path)
        if case is None:
            return False
        dim = getattr(case, 'dim', None)
        if dim != d:
            what = ('an HD 1.3 case' if not dim else f'{dim}D')
            dialogs.show_error('Load case', f'That case is {what}; stage '
                                            f'{self._number(d)} is {d}D.',
                               self)
            return False
        self.set_stage_case(d, case)
        return True

    # ── running ──────────────────────────────────────────────────────────
    def run(self):
        """Validate, wire and launch. Returns True only if the chain was
        handed on; every refusal returns False having said why."""
        self._set_status('')
        # Refuse here, not after the model folder has been written.
        #
        # The button is disabled while a run is live, but a disabled
        # button is not a guard - anything that calls this directly (an
        # accelerator, a script, a test) got all the way to creating the
        # workspace and saving three case JSONs, logged "Chain: 3
        # stage(s) into ...", returned True, and only THEN did the
        # controller refuse with "A run is already in progress". The run
        # never started and the evidence of one was on disk.
        if self._running:
            return self._refuse(['A run is already in progress.'])
        stages = self.checked()
        if not stages:
            # a defence only: since GUI-9 no route can be empty
            return self._refuse(['No stages selected.'])
        # GUI-8 (plan sec. 8.3): no consecutive-stages guard any more.
        # The only non-consecutive subset of {1, 2, 3} is {1, 3}, and
        # that is now a supported route (wired below).

        # OUT-1: the Run tab's model folder, checked (nothing is written
        # yet) before the forms are read, so the hand-off paths are known
        runs_dir, model = self._model_source()
        problems = model_folder.check(runs_dir, model)
        if problems:
            return self._refuse(problems + [WHERE_BOXES])
        target = model_folder.Target(
            runs_dir=str(runs_dir).strip(), model=str(model).strip(),
            folder=model_folder.folder_for(runs_dir, model))
        hand = model_folder.handoff_paths(target, stages)

        cases = {}
        for d in stages:
            try:
                cases[d] = self.forms[d].get_case()
            except ValueError as exc:
                # name the stage - a bare "'Lx' is not a number" gave no
                # clue which of the three forms it came from - and switch
                # to it so the offending field is on screen
                self.focus_stage(d)
                return self._refuse([f'Stage {d} ({d}D): {ln}'
                                     for ln in str(exc).splitlines()
                                     if ln.strip()])

        # GUI-9: the wiring (pinned write schedule N2-13, the hand-offs at
        # the model root, the axisymmetric rule, GUI-8's 1D -> 3D) lives
        # in chain_route.wire, shared with the live per-stage checks
        cases, refusal = chain_route.wire(stages, cases, hand)
        if refusal:
            self.focus_stage(2)
            return self._refuse([refusal])

        # after the wiring, so the checks see what will actually run
        errors = stage_errors(stages, cases)
        if errors:
            for d in stages:                  # jump to the first bad one
                if any(e.startswith(f'Stage {d} ') for e in errors):
                    self.focus_stage(d)
                    break
            return self._refuse(errors)

        # the window creates the model folder (after asking, for an
        # existing one) only now, and each stage writes its own MODEL.json
        if self._on_run_chain([(d, cases[d]) for d in stages]) is False:
            return False
        self._log(f'Chain: {len(stages)} stage(s) into {target.folder}')
        return True

    def set_running(self, running):
        """Mirror the Run button: a second start while a run is live
        would orphan the drain loop and drop the finished result. The
        flag is what `run()` consults, so the greyed button is the
        visible half of the guard and not the whole of it."""
        self._running = bool(running)
        self._sync_run_btn()

    def set_busy(self, busy):
        """An HD 1.3 assessment is working (it runs on its own thread, not
        the controller): Run chain greys until it ends - a state grey,
        like Run during a run (GUI-11 T5, P2-18, D206). A direct `run()`
        still reaches the window's own refusal (`_model_target`)."""
        self._busy = bool(busy)
        self._sync_run_btn()
