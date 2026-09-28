"""The Chain tab: run 1D -> 2D -> 3D as one workflow.

OUT-1: a chain writes into the Run tab's model folder (the workspace box
is gone, owner decision 14): each stage into `<MODEL>\\1d`, `2d`, `3d`,
with its own MODEL.json, and the profile hand-offs at the model root.

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

from PySide6.QtWidgets import QCheckBox, QStackedWidget, QWidget

from ..core import mode as mode_mod
from ..core import chain
from ..core.chain import stage_errors
from ..services import model_folder
from . import dialogs
from .case_form import CaseForm
from . import theme
from .widgets import (Card, ScrollColumn, Segmented, button, hbox, label,
                      vbox)

HINT = ('The chain runs the checked stages in order, into the model folder '
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

STAGE_LABELS = {1: 'Stage 1D', 2: 'Stage 2D', 3: 'Stage 3D'}


class ChainPanel(QWidget):
    def __init__(self, on_run_chain=None, mode=None, log_fn=print,
                 error_sink=None, model_source=None, parent=None):
        super().__init__(parent)
        #: on_run_chain([(dim, case), ...]) -> False when the window did
        #: not start it (it said why); anything else = started
        self._on_run_chain = on_run_chain or (lambda stages: None)
        #: () -> (runs_dir, model): the Run tab's two boxes (OUT-1)
        self._model_source = model_source or (lambda: ('', ''))
        self._running = False       # a run is live somewhere in the app
        self._log = log_fn
        self.error_sink = error_sink or self._default_sink
        # every stage starts on the app-level solver and can be
        # overridden per stage (a native 2D stage may follow a blastFoam
        # 1D one); a global change presets all three again
        self._mode = mode if mode is not None else mode_mod.SolverMode()

        root = vbox(self, margins=(0, 0, 0, 0))
        root.addWidget(label('Chain', 'h1'))

        top = Card()
        root.addWidget(top)
        bar = hbox()
        bar.addWidget(label('Stages', 'muted'))
        self.use = {}
        for d in (1, 2, 3):
            box = QCheckBox(f'{d}D')
            box.setChecked(True)
            box.toggled.connect(lambda _c: self._refresh_compat())
            self.use[d] = box
            bar.addWidget(box)
        bar.addStretch(1)
        self.run_btn = button('Run chain', 'play', 'primary', width=136,
                              height=36, on_click=self.run)
        bar.addWidget(self.run_btn)
        top.add_layout(bar)

        hrow = hbox()
        hrow.addWidget(label(HINT, 'small', wrap=True), 1)
        top.add_layout(hrow)
        # the refusal always lands here, whatever happens to the dialog
        self.status = label('', 'small')
        self.status.setWordWrap(True)
        top.add(self.status)

        stages = Card(pad=12)
        root.addWidget(stages, 1)
        self.stage_seg = Segmented([STAGE_LABELS[d] for d in (1, 2, 3)])
        self.stage_seg.setMaximumWidth(360)
        self.stage_seg.changed.connect(self._stage_selected)
        stages.add(self.stage_seg)

        self.stack = QStackedWidget()
        stages.add(self.stack, 1)
        self.forms, self.stage_solver = {}, {}
        self._stage_seg_solver, self._pages, self._compat = {}, {}, {}
        self._compat_bad = False
        for d in (1, 2, 3):
            col = ScrollColumn()
            row = hbox()
            row.addWidget(label('Solver for this stage', 'muted'))
            seg = Segmented([mode_mod.label(m) for m in mode_mod.MODES],
                            height=28, small=True)
            seg.setMaximumWidth(240)
            seg.changed.connect(
                lambda lbl, d=d: self.set_stage_solver(
                    d, mode_mod.from_label(lbl)))
            row.addWidget(seg)
            row.addWidget(label('preset from the sidebar - override per '
                                'stage', 'small'))
            row.addStretch(1)
            col.add_layout(row)
            # N5-4: the hand-off refusal, said where the choice is made.
            # stage_errors is still the authority (run() re-checks), but
            # a refusal that only appears after Run chain is a refusal
            # the user meets having already filled three forms.
            self._compat[d] = label('', 'small', wrap=True)
            self._compat[d].setVisible(False)
            col.add(self._compat[d])
            self.forms[d] = CaseForm(d, mode=self._mode.get())
            col.add(self.forms[d], 1)
            self.stack.addWidget(col)
            self._pages[d] = col
            self._stage_seg_solver[d] = seg
            self.stage_solver[d] = self._mode.get()
            seg.set(mode_mod.label(self.stage_solver[d]))
        self.stage_seg.set(STAGE_LABELS[1])
        self.stack.setCurrentWidget(self._pages[1])
        self._mode.subscribe(self._on_global_mode)
        self._refresh_compat()

    # ── the error sink ───────────────────────────────────────────────────
    def _default_sink(self, title, lines):
        dialogs.show_error(title, '\n'.join(lines), self)

    def _refuse(self, lines):
        """Say no, in this order: the status line, the log, and only then
        a dialog. A dialog that hangs or raises must not be able to
        swallow the reason."""
        lines = [str(ln) for ln in lines if str(ln).strip()]
        # one line of sentences: each ends with a stop (GUI QA V2)
        said = [ln.rstrip() if ln.rstrip()[-1] in '.:!?'
                else ln.rstrip() + '.' for ln in lines]
        self.status.setText(' '.join(' '.join(said).split())[:300])
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
            self.status.setText(f'Stage {min(bad)}: {bad[min(bad)]}')
        elif self.status.text().startswith('Stage '):
            self.status.setText('')
        self._sync_run_btn()

    def _sync_run_btn(self):
        """The ONE owner of the Run button's enabled state. Two owners
        (set_running and the compat check) would fight, and whichever
        ran last would win."""
        self.run_btn.setEnabled(not self._running and not self._compat_bad)

    # ── per-stage solver ─────────────────────────────────────────────────
    def set_stage_solver(self, d, m):
        m = mode_mod.normalize(m)
        self.stage_solver[d] = m
        self._stage_seg_solver[d].set(mode_mod.label(m))   # silent
        self.forms[d].set_mode(m)
        self._refresh_compat()

    def set_stage_case(self, d, case):
        """Fill stage `d` from a Case, adopting its solver."""
        self.set_stage_solver(d, getattr(case, 'solver', 'native'))
        self.forms[d].set_case(case)

    def _on_global_mode(self, m):
        for d in (1, 2, 3):
            self.set_stage_solver(d, m)
        self._refresh_compat()      # after the loop: mid-loop the set
        #                             is transiently mixed

    # ── navigation ───────────────────────────────────────────────────────
    def focus_stage(self, d):
        """Bring stage `d`'s form to the front. A dialog naming 'Stage 2'
        used to leave the switcher wherever it happened to be."""
        self.stage_seg.set(STAGE_LABELS[d])
        self.stack.setCurrentWidget(self._pages[d])

    def stage(self):
        for d, page in self._pages.items():
            if self.stack.currentWidget() is page:
                return d
        return None

    def _stage_selected(self, value):
        for d, text in STAGE_LABELS.items():
            if text == value:
                self.stack.setCurrentWidget(self._pages[d])
                return

    def checked(self):
        return [d for d in (1, 2, 3) if self.use[d].isChecked()]

    # ── running ──────────────────────────────────────────────────────────
    def run(self):
        """Validate, wire and launch. Returns True only if the chain was
        handed on; every refusal returns False having said why."""
        self.status.setText('')
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
        p1, p2 = hand.get((1, 2)), hand.get((2, 3))
        p13 = hand.get((1, 3))

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

        # N2-13: a chain must be reproducible, so every stage runs on a
        # PINNED write schedule. The adaptive-writeInterval controller
        # rewrites writeInterval mid-run from what the ingest has managed
        # to keep up with - wall clock - so with it on the set of write
        # times differs between identical runs, and the arrival-pinned
        # hand-off lands on a different write each time (measured: stage
        # ends spread +/-7% / 2.3x over five identical chains).
        for case in cases.values():
            case.adaptive_write = False

        # the hand-offs live at the model root (plan sec. 2.2); a single
        # stage has none and writes its own profile into the folder
        if 1 in cases and 2 in cases:
            cases[1].profile_file = p1
            cases[2].init_mode = 'profile1d'
            cases[2].profile_file_in = p1
        if 2 in cases:
            if cases[2].geometry != 'axisymmetric' and 3 in cases:
                self.focus_stage(2)
                return self._refuse(['Stage 2 (2D): must be axisymmetric '
                                     'to feed the 3D stage.'])
            if 3 in cases:
                cases[2].profile_file = p2
        if 3 in cases and 2 in cases:
            cases[3].init_mode = 'profile2d'
            cases[3].profile_file_in = p2
        # GUI-8 (plan sec. 8.3): 1D -> 3D without a 2D stage. The engine
        # already supports it - solve_3d / the foam writer remap a 1D
        # profile (core/profiles.remap_profile_1d_to_3d); the 3D burst
        # height comes from the 3D form.
        if 1 in cases and 3 in cases and 2 not in cases:
            cases[1].profile_file = p13
            cases[3].init_mode = 'profile1d'
            cases[3].profile_file_in = p13

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
