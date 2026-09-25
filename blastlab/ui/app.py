"""blastlab Qt main window: left sidebar (Setup | Run | Results | Chain)
+ content stack, built with PySide6. A port of gui/app.py."""

import json
import os
import sys
import threading

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QApplication, QCheckBox, QFrame, QHBoxLayout,
                               QLabel, QMainWindow, QSizePolicy,
                               QStackedWidget, QVBoxLayout, QWidget)

from .. import __version__
from ..core import hardware
from ..core import mode as mode_mod
from ..core import settings as app_settings
from ..core.case import (load_case, long_run_note, save_case,
                         validate_case)
from ..core.mode import SolverMode
from ..solvers.foam import env as foam_env
from ..viz3d import pyvista_available
from . import dialogs, theme
from .bridge import ThreadBridge
from .chain_panel import ChainPanel
from .results_panel import ResultsPanel
from .run_controller import RunController
from .run_panel import RunPanel
from .setup_panel import SetupPanel
from .theme import GAP, PAD
from .view3d_host import View3DHost
from .viewer_link import ViewerLink
from .widgets import Segmented, button, label, refresh_icons

_LOGO = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), 'logo.gif')

CASE_FILTER = 'blastlab case (*.json);;All files (*.*)'


class MainWindow(QMainWindow):
    #: How a failed run is reported (see RunController.show_error).
    show_error = staticmethod(lambda title, msg: dialogs.show_error(title, msg))

    def __init__(self, case_file=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'blastlab {__version__}')
        self.resize(1280, 840)
        self.setMinimumSize(1100, 720)
        if os.path.exists(_LOGO):
            self.setWindowIcon(QIcon(QPixmap(_LOGO)))

        self.bridge = ThreadBridge(self)
        self._case = None
        self._case_path = None
        self._results = []
        self._validate_timer = QTimer(self)
        self._validate_timer.setSingleShot(True)
        self._validate_timer.setInterval(300)
        self._validate_timer.timeout.connect(self._validate)
        self._wsl_timer = QTimer(self)
        self._wsl_timer.setSingleShot(True)
        self._wsl_timer.setInterval(1000)
        self._wsl_timer.timeout.connect(self._poll_wsl)
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.setInterval(12000)

        # T34: the solver is an app-level mode, seeded from the persisted
        # settings BEFORE the sidebar and the panels exist
        st = app_settings.load()
        self.solver_mode = SolverMode(st.get('solver', mode_mod.DEFAULT))
        # N17/T48/N21: last session's WSL hardware, if it is this
        # machine's and not stale
        foam_env.prime_from_settings(st)

        central = QWidget()
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_sidebar())

        column = QVBoxLayout()
        column.setContentsMargins(0, PAD, PAD, 6)
        column.setSpacing(6)
        outer.addLayout(column, 1)
        self._stack = QStackedWidget()
        column.addWidget(self._stack, 1)
        # one status line for the whole window: exports, loads and solver
        # warnings used to land only in the Run tab's log
        self._status = label('', 'small')
        self._status.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        column.addWidget(self._status)
        self._status_timer.timeout.connect(lambda: self._status.setText(''))

        self.viewer_link = ViewerLink(self, log_fn=self._log_threadsafe)
        self.view3d = View3DHost(self.viewer_link, 'run',
                                 log_fn=self._log_threadsafe)
        self.setup = SetupPanel(on_change=self._schedule_validate,
                                mode=self.solver_mode,
                                viewer_link=self.viewer_link,
                                log_fn=self._log_threadsafe)
        self.run_panel = RunPanel(view3d_host=self.view3d)
        self.results = ResultsPanel(viewer_link=self.viewer_link,
                                    log_fn=self._result_msg,
                                    mode=self.solver_mode,
                                    on_resume=self._resume_foam_run,
                                    bridge=self.bridge)
        self.chain = ChainPanel(on_run_chain=self._run_chain,
                                mode=self.solver_mode,
                                log_fn=self._log_threadsafe)
        self._panels = {'setup': self.setup, 'run': self.run_panel,
                        'results': self.results, 'chain': self.chain}
        for panel in self._panels.values():
            self._stack.addWidget(panel)

        self.ctrl = RunController(handlers=self, view3d=self.view3d,
                                  parent=self)
        self.run_panel.run_requested.connect(lambda: self._run_single())
        self.run_panel.stop_requested.connect(self._stop)
        self.run_panel.view3d_requested.connect(self._open_view3d)
        self.run_panel.init_requested.connect(self._init_model)
        self.run_panel.exec_requested.connect(self.ctrl.exec_cmd)
        self.run_panel.refresh_changed.connect(self._apply_refresh)
        self.run_panel.gauges_wanted.connect(self._gauges_wanted)

        # N8: sweep old/large WSL run dirs per the persisted settings,
        # off-thread (WSL round trips must never block the window)
        self._cleanup_thread = foam_env.start_auto_cleanup(
            st, self._log_threadsafe)

        self._show('setup')
        self._restore_ui_state(st)
        self._bind_accelerators()
        theme.signals.changed.connect(self._retheme)

        # the panels are all built; from here on a mode change re-lays
        # them out. The first call fills the sidebar hints and schedules
        # the first validation.
        self.solver_mode.subscribe(self._on_solver_mode)
        self._on_solver_mode(self.solver_mode.get())
        # HD1-11c: the solver switch is meaningless for a 0-D
        # deflagration case, and leaving 'blastFoam' lit beside one would
        # be a lie about what is running. The signal was declared when
        # SetupPanel was written and never connected to anything.
        self.setup.dim_changed.connect(self._dim_changed)
        self._dim_changed(self.setup.dim)

        if case_file:
            self._open_case(case_file)

    # ── sidebar / navigation ─────────────────────────────────────────────
    def _build_sidebar(self):
        side = QFrame()
        side.setObjectName('sidebar')
        # Stays 216. Widening it to 232 to fit 'blastFoam' took those
        # 16 px straight out of the Setup form, whose two columns need
        # 612 px of viewport and then got 604 - so the fix for a 7 px
        # label collapsed the whole form to one column. The solver
        # switch uses the small font instead.
        side.setFixedWidth(216)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(12, PAD, 12, 12)
        lay.setSpacing(3)

        if os.path.exists(_LOGO):
            pm = QPixmap(_LOGO)
            logo = QLabel()
            logo.setPixmap(pm.scaledToWidth(184, Qt.SmoothTransformation))
            logo.setAlignment(Qt.AlignHCenter)
            lay.addWidget(logo)
        else:
            lay.addWidget(label('blastlab', 'h1', align=Qt.AlignHCenter))
        lay.addWidget(label(f'v{__version__}', 'small',
                            align=Qt.AlignHCenter))
        lay.addSpacing(PAD - 4)

        self._nav_btns = {}
        for key, text, ic in (('setup', 'Setup', 'sliders'),
                              ('run', 'Run', 'play'),
                              ('results', 'Results', 'chart'),
                              ('chain', 'Chain', 'chain')):
            b = button(text, ic, 'nav', height=40, icon_size=17,
                       on_click=lambda k=key: self._show(k))
            lay.addWidget(b)
            self._nav_btns[key] = b
        lay.addStretch(1)

        # bottom block: case files, solver, appearance, credit
        for text, ic, cmd in (('Open case…', 'folder', self._open_case),
                              ('Save case…', 'save', self._save_case)):
            lay.addWidget(button(text, ic, 'quiet', height=36,
                                 on_click=lambda f=cmd: f()))
        lay.addSpacing(10)
        # T34: the solver is chosen here, once, for the whole app
        self._solver_label = label('Solver', 'small')
        lay.addWidget(self._solver_label)
        self._solver_seg = Segmented([mode_mod.label(m) for m in mode_mod.MODES],
                                     height=30, small=True)
        self._solver_seg.set(mode_mod.label(self.solver_mode.get()))
        self._solver_seg.changed.connect(
            lambda text: self.solver_mode.set(mode_mod.from_label(text)))
        lay.addWidget(self._solver_seg)
        self._solver_hint = label('', 'small', wrap=True)
        lay.addWidget(self._solver_hint)
        self._wsl_hint = label('', 'small', wrap=True)
        lay.addWidget(self._wsl_hint)
        # N17/T48: the hardware behind the rank/cap decisions, and a way
        # to re-probe it without restarting
        self._wsl_redetect = button('Re-detect', kind='link', height=20,
                                    on_click=self._redetect_hw)
        self._wsl_redetect.setFont(theme.font('small'))
        lay.addWidget(self._wsl_redetect, alignment=Qt.AlignLeft)
        lay.addSpacing(8)
        self._mode_switch = QCheckBox('Dark mode')
        self._mode_switch.setChecked(theme.mode() == 'dark')
        self._mode_switch.toggled.connect(self._toggle_mode)
        lay.addWidget(self._mode_switch)
        lay.addWidget(label('By Ofek Rotem', 'small', align=Qt.AlignHCenter))
        return side

    def _show(self, key):
        self._stack.setCurrentWidget(self._panels[key])
        for k, b in self._nav_btns.items():
            b.setProperty('active', 'true' if k == key else 'false')
            theme.repolish(b)

    def current_tab(self):
        for k, p in self._panels.items():
            if self._stack.currentWidget() is p:
                return k
        return None

    def _toggle_mode(self, checked):
        theme.apply(QApplication.instance(), 'dark' if checked else 'light')

    def _retheme(self, _mode=None):
        refresh_icons(self)
        self._show(self.current_tab() or 'setup')

    # ── T34: app-level solver mode ───────────────────────────────────────
    @property
    def solver(self):
        return self.solver_mode.get()

    def set_solver(self, mode):
        """Public entry point (tests, the QA harness): the same as
        clicking the sidebar segment."""
        self.solver_mode.set(mode)

    def _on_solver_mode(self, m):
        self._solver_seg.set(mode_mod.label(m))
        self._solver_hint.setText(mode_mod.EXPLAIN[m])
        self._wsl_timer.stop()
        if m == 'blastfoam':
            # warm the cached WSL availability check off-thread and show
            # its outcome under the selector
            foam_env.ensure_check_started()
            self._probe_hw_async()
            self._poll_wsl()
        else:
            self._wsl_hint.setText('')
            self._wsl_hint.setToolTip('')
        self._wsl_redetect.setVisible(m == 'blastfoam')
        self._schedule_validate()

    def _hw_suffix(self):
        """" · 8 cores · 16 GB" from the cached probe (N17/T48). Empty
        while nothing is known - the line must never invent numbers."""
        hw = foam_env.hardware() or {}
        bits = []
        if hw.get('cores'):
            bits.append(f"{hw['cores']} cores")
        if hw.get('ram_gb'):
            bits.append(f"{hw['ram_gb']} GB VM")
        if not bits:
            return ' · hardware unknown'
        if hw.get('ram_source') == hardware.CACHED:
            bits.append('cached')
        return ' · ' + ' · '.join(bits)

    def _hw_tooltip(self):
        hw = foam_env.hardware() or {}
        if not hw.get('ram_gb') and not hw.get('cores'):
            return ('WSL has not answered the hardware probe. Cell caps '
                    'are conservative until it does - click Re-detect.')
        bits = [f"WSL VM: {hw.get('cores') or '?'} physical cores, "
                f"{hw.get('ram_gb') or '?'} GB"]
        host_ram = hardware.host().get('ram_gb')
        if host_ram:
            bits.append(f"Windows host: {host_ram} GB")
        stamp = app_settings.load().get('hw_stamp')
        if stamp:
            bits.append(f"measured {str(stamp).replace('T', ' ')}")
        return '. '.join(bits) + '.'

    def _probe_hw_async(self):
        """Probe the WSL VM's cores + RAM off-thread and persist them, so
        the next session can show the numbers before WSL is warm."""
        def work():
            try:
                hw = foam_env.hardware(probe=True) or {}
                hardware.detect_host_ram_gb()
            except Exception:
                return
            try:
                foam_env.persist_hardware(hw)
            except Exception:
                pass
            self.bridge.post(self._poll_wsl)
            self.bridge.post(self._schedule_validate)
        threading.Thread(target=work, daemon=True).start()

    def _redetect_hw(self):
        foam_env.forget_hardware()
        self._wsl_hint.setText('WSL: detecting hardware…')
        self._wsl_hint.setStyleSheet(f'color: {theme.cur("muted")};')
        self._probe_hw_async()

    def _poll_wsl(self):
        try:
            st = foam_env.status()
            state, detail = (st if isinstance(st, tuple) else (st, ''))[:2]
        except Exception as exc:
            state, detail = 'fail', str(exc)
        detail = str(detail or '')
        if state == 'checking':
            text, colour = 'WSL: checking blastFoam…', 'muted'
        elif state == 'ok':
            suffix = self._hw_suffix()
            colour = 'warn' if 'unknown' in suffix else 'ok'
            text = 'WSL: blastFoam ready' + suffix
        elif state == 'fail':
            text, colour = 'WSL: unavailable - ' + detail[:60], 'warn'
        else:
            text, colour = 'WSL: verified at run start', 'muted'
        self._wsl_hint.setText(text)
        self._wsl_hint.setStyleSheet(f'color: {theme.cur(colour)};')
        self._wsl_hint.setToolTip(
            detail if state == 'fail'
            else (self._hw_tooltip() if state == 'ok' else ''))
        if state == 'checking':
            self._wsl_timer.start()

    # ── G9: keyboard + persisted window state ────────────────────────────
    def _bind_accelerators(self):
        for seq, fn in (('Ctrl+O', self._open_case), ('Ctrl+S', self._save_case),
                        ('F5', self._run_single), ('Esc', self._stop)):
            sc = QShortcut(QKeySequence(seq), self)
            sc.activated.connect(lambda f=fn: f())

    def _restore_ui_state(self, st):
        try:
            geo = str(st.get('geometry') or '')
            if 'x' in geo:
                size, _plus, rest = geo.partition('+')
                w, h = (int(v) for v in size.split('x'))
                self.resize(max(w, 1100), max(h, 720))
                if rest:
                    x, y = (int(v) for v in rest.split('+')[:2])
                    self.move(max(0, x), max(0, y))
            self.run_panel.set_refresh_policy_text(
                st.get('refresh_value', ''), str(st.get('refresh_mode',
                                                       'seconds')))
            self._apply_refresh()
        except Exception:
            pass

    def _save_ui_state(self):
        try:
            val, mode = self.run_panel.refresh_policy_text()
            state = dict(appearance=theme.mode(), refresh_value=val,
                         refresh_mode=mode, solver=self.solver_mode.get())
            # only a real, normal window has a meaningful geometry
            if self.isVisible() and not self.isMinimized() \
                    and not self.isMaximized():
                g = self.geometry()
                if g.width() >= 1100 and g.height() >= 720:
                    pos = self.pos()
                    state['geometry'] = (f'{g.width()}x{g.height()}'
                                         f'+{pos.x()}+{pos.y()}')
            app_settings.update(**state)
        except Exception:
            pass

    # ── case files ───────────────────────────────────────────────────────
    def current_case(self):
        """The case the form currently describes, or None when it does
        not parse (the Setup report says why)."""
        try:
            return self.setup.get_case()
        except ValueError:
            return None

    def _open_case(self, path=None):
        path = path or dialogs.open_file('Open case', CASE_FILTER, self)
        if not path:
            return
        try:
            case = load_case(path)
        except FileNotFoundError:
            self.show_error('Open case', f'File not found: {path}')
            return
        except json.JSONDecodeError as exc:
            self.show_error('Open case', f'This file is not valid JSON '
                                         f'(line {exc.lineno}, column '
                                         f'{exc.colno}).')
            return
        except (KeyError, TypeError) as exc:
            self.show_error('Open case', f'Not a blastlab case file: '
                                         f'unsupported or missing field '
                                         f'{exc}.')
            return
        except OSError as exc:
            self.show_error('Open case', f'Could not read the file: '
                                         f'{exc.strerror or exc}')
            return
        except Exception as exc:
            msg = str(exc)
            self.show_error('Open case', msg if 'case file' in msg.lower()
                            else f'Not a blastlab case file: {msg}')
            return
        self._case_path = path
        self.setup.set_case(case)
        self._maybe_prewarm_viewer(case)
        # a run started from this case is named after the file (N9)
        self.run_panel.set_run_name(
            os.path.splitext(os.path.basename(path))[0])
        self._show('setup')
        self._schedule_validate()

    def _maybe_prewarm_viewer(self, case):
        """Start the viewer child early for a 3D case, so its pyvista
        import and first GL context are paid while the user is still
        reading the Setup tab (the Tk app paid this on the Run click and
        froze the window for 11-13 s - N2-12/N2-08/E06; here it is
        another process, so it only delays the picture).

        Only for 3D: a viewer child holds VTK in memory, and a 2D-only
        session on this machine cannot spare it."""
        if getattr(case, 'dim', 0) == 3 and pyvista_available():
            QTimer.singleShot(400, self.viewer_link.prewarm)

    def _save_case(self):
        try:
            case = self.setup.get_case()
        except ValueError as exc:
            self.show_error('Save case', str(exc))
            return
        path = dialogs.save_file('Save case', 'blastlab case (*.json)', self,
                                 default_suffix='json')
        if path:
            save_case(case, path)

    # ── live validation ──────────────────────────────────────────────────
    def _schedule_validate(self):
        self._validate_timer.start()

    def _validate(self):
        try:
            case = self.setup.get_case()
        except ValueError as exc:
            lines = [ln for ln in str(exc).splitlines() if ln.strip()]
            self.setup.show_report(errors=lines)
            self.run_panel.set_validation(False, len(lines))
            self.setup.update_preview(None)
            return
        if getattr(case, 'dim', None) == 0:
            # HD 1.3: a different validator, the SAME ValidationReport, so
            # everything below this point is unchanged - which is why
            # core/assessment returns that type rather than its own.
            from ..core.assessment import validate as validate_hd13
            rep = validate_hd13(case)
            self.setup.show_report(rep.errors, rep.warnings, rep.notes)
            self.run_panel.set_validation(not rep.errors, len(rep.errors))
            self.setup.update_preview(case)
            return
        if getattr(case, 'solver', 'native') == 'blastfoam':
            foam_env.ensure_check_started()
        rep = validate_case(case)
        extra = []
        if rep.n_cells:
            from ..core.case import fmt_cells
            line = (f'~{fmt_cells(rep.n_cells)} cells '
                    f'at dx = {rep.effective_dx:g} m')
            if getattr(rep, 'amr_levels', 0):
                line += (f' at t = 0; AMR up to level {rep.amr_levels} '
                         f'(finest {rep.dx_fine:g} m), displayed at level '
                         f'{rep.display_level} ({rep.n_fine:,} cells)')
            elif getattr(rep, 'lmax', 0):
                line += (f' (finest {rep.dx_fine:g} m, {rep.n_fine:,} '
                         f'display cells)')
            extra.append(line)
        self.setup.show_report(rep.errors, rep.warnings, rep.notes + extra)
        self.run_panel.set_validation(not rep.errors, len(rep.errors))
        self.setup.update_preview(case)

    # ── running ──────────────────────────────────────────────────────────
    def _run_single(self, paused=False):
        try:
            case = self.setup.get_case()
        except ValueError as exc:
            self.show_error('Run', str(exc))
            return
        if getattr(case, 'dim', None) == 0:
            self._run_hd13(case)
            return
        rep = validate_case(case)
        if not rep.ok:
            self.show_error('Run', '\n'.join(rep.errors))
            return
        if not self._confirm_long_run([case]):
            return
        if self.ctrl.start_stages([(case.dim, case)], paused=paused,
                                  run_name=self.run_panel.current_run_name()):
            self._show('run')

    def _dim_changed(self, dim):
        """Hide, never grey, the controls a dimension does not have - the
        app-wide rule (CLAUDE.md Sec. 4). A 0-D case has no solver
        backend, so the whole solver block goes."""
        blast = int(dim) != 0
        for w in (self._solver_label, self._solver_seg, self._solver_hint,
                  self._wsl_hint, self._wsl_redetect):
            w.setVisible(blast and not (w is self._wsl_hint
                                        and not w.text()))
        if blast:
            self._on_solver_mode(self.solver_mode.get())

    def _run_hd13(self, case):
        """Run an HD 1.3 assessment and write its report.

        Solved INLINE, on the GUI thread, not through RunController. That
        machinery exists for a solve in a worker thread with progress, a
        live viewer, cancellation and resume. A 0-D deflagration case is
        closed form, but it is not instant: the starter case takes about
        40 s per assessment (sensitivity band off), and this method runs
        the assessment twice (see below) - known UX debt, pinned by
        `tests/test_ui_char_hd13_run.py`.
        """
        # Imported here, and called through the module, so a test that
        # patches `assessment.run` or `tempfile.mkdtemp` is honoured.
        import tempfile
        from ..core import assessment
        from ..services import hd13 as hd13_service
        rep = assessment.validate(case)
        if not rep.ok:
            self.show_error('Run', '\n'.join(rep.errors))
            return
        path = self.setup.form.v['report_file'].get().strip() \
            or 'hd13_report.html'
        try:
            # Run 1: fail before touching disk. `assess` below is run 2.
            assessment.run(case)
            # The temp case file is kept, and the report is made from the
            # case read back from it, exactly as before Phase 7 of
            # docs/ARCHITECTURE_REVIEW.md: whether it is provenance is
            # open question Q4 there.
            case_dir = tempfile.mkdtemp(prefix='blastlab_hd13_')
            case_path = os.path.join(case_dir, 'case.json')
            assessment.save_case(case, case_path)
            bundle = hd13_service.assess(assessment.load_case(case_path))
            out = hd13_service.write_report(bundle, path)
        except Exception as exc:               # noqa: BLE001 - shown to the user
            self.show_error('HD 1.3 assessment', str(exc))
            return
        self._status.setText(f'HD 1.3 report written: {out}')
        self._status_timer.start()

    def _confirm_long_run(self, cases):
        """An end time past the automatic stop is now honoured (T52),
        so its cost is confirmed instead of silently discarded.

        The number used to be thrown away, which is why the field felt
        inert; honouring it means a typed 500 ms in a domain whose
        automatic stop is 47 ms really does run ten times as long. One
        dialog, only when that is what was asked for - a case at or
        under the automatic stop never sees it.

        Resolved through `ui.dialogs` at call time, so the QA driver and
        every test patch it rather than meeting a modal (P2-8).
        """
        notes = [(c, long_run_note(c)) for c in cases]
        notes = [(c, n) for c, n in notes if n is not None]
        if not notes:
            return True
        lines = []
        for case, (t_end, cap, ratio) in notes:
            where = (f'Stage {case.dim}D: ' if len(cases) > 1 else '')
            lines.append(f'{where}end time {t_end * 1e3:.4g} ms is '
                         f'{ratio:.1f}x the automatic stop time '
                         f'({cap * 1e3:.0f} ms).')
        worst = max(n[2] for _c, n in notes)
        lines.append('')
        lines.append(f'The full span will be simulated, so expect roughly '
                     f'{worst:.0f}x the wall clock of an automatic run. '
                     f'The wave will have left the domain long before the '
                     f'end.')
        lines.append('')
        lines.append('Start it?')
        return dialogs.ask_yes_no('Long run', '\n'.join(lines), self)

    def _run_chain(self, dim_cases, workspace):
        """The Chain panel has already validated and wired the stages and
        written their case JSONs; all that is left is to launch them as
        one worker, so the Run tab, Stop and Results behave as usual."""
        if not self._confirm_long_run([c for _d, c in dim_cases]):
            return
        self.notify(f'Chain: {len(dim_cases)} stage(s) in {workspace}')
        if self.ctrl.start_stages(
                dim_cases, run_name=self.run_panel.current_run_name()):
            self._show('run')

    def _init_model(self):
        """VIPER-style 'Initialise Model': start the run held at step 0
        so the initial field is visible; Exec buttons advance it."""
        self._run_single(paused=True)

    def _stop(self):
        self.ctrl.stop()

    def _apply_refresh(self):
        val, mode = self.run_panel.refresh_policy_text()
        self.run_panel.mark_refresh(self.ctrl.apply_refresh(val, mode))

    def _open_view3d(self):
        if self.ctrl.open_view3d():
            self.run_panel.show_3d_tab()

    # ── RunController handlers ───────────────────────────────────────────
    def on_log(self, text):
        self.run_panel.on_log(text)
        line = ' '.join(str(text).split())
        if '[warn]' in line or '[error]' in line:
            self.notify(line, 'warn')

    def on_run_started(self, info):
        self.run_panel.on_run_started(info)

    def on_view3d_available(self, is3d):
        self.run_panel.enable_view3d(is3d)

    def on_cadence(self, dt, steps):
        self.run_panel.set_cadence(dt, steps)

    def on_progress(self, p):
        self.run_panel.on_progress(p)

    def on_paused(self, paused):
        self.run_panel.set_paused(paused)

    def on_frame(self, field, t, levels=None):
        self.run_panel.on_frame(field, t, levels)

    def on_gauges(self, payload):
        self.run_panel.set_gauge_payload(payload)

    def _gauges_wanted(self, on):
        """The live gauge view was opened or left."""
        self.ctrl.set_live_gauges(on)
        if not on:
            return
        # a case with no gauges would otherwise sit on "waiting for the
        # solver" forever, which reads as a fault rather than as nothing
        # to show
        try:
            case = self.current_case()
        except Exception:
            return
        pts = getattr(case, 'gauges', None)
        if pts is None:
            pts = getattr(case, 'gauge_radii', None)
        if not pts and not self.run_panel.gauges.has_data():
            self.run_panel.say_no_gauges()

    def on_running(self, running):
        self.run_panel.set_running(running)
        # a second start while a run is live would orphan the drain loop
        # and drop the finished result
        self.chain.set_running(running)

    def on_result(self, k, dim, label_, res):
        self._results.append((label_, dim, res))
        self.results.add_result(label_, dim, res)
        self.notify(f'Result ready: {label_}')

    def on_finished(self, stopped_early, errored):
        if not (stopped_early or errored):
            # the last progress message is often throttled away, so a
            # completed run would otherwise rest below 100%
            self.run_panel.mark_complete()

    def _resume_foam_run(self, path):
        """Resume a stopped blastFoam run. The dimension comes from the
        run's own case.json, so the run browser only has to hand over a
        path."""
        from ..services.foam_runs import dims_from_case_json
        from ..solvers.foam import env as _env
        try:
            _p, unc = _env.case_paths(path)
            dim = int((dims_from_case_json(unc) or '?').rstrip('D'))
        except (ValueError, OSError, TypeError) as exc:
            self.notify(f'cannot resume {path}: {exc}', 'error')
            self._log_threadsafe(f'  [runs] cannot resume {path}: {exc}')
            return False
        return self.ctrl.resume_foam_run(
            path, dim, run_name=self.run_panel.current_run_name())

    # ── status line ──────────────────────────────────────────────────────
    def notify(self, text, level='info'):
        text = ' '.join(str(text).split())
        if not text:
            return
        colour = {'error': 'error', 'warn': 'warn'}.get(level, 'muted')
        self._status.setText(text[:200])
        self._status.setStyleSheet(f'color: {theme.cur(colour)};')
        self._status_timer.start()

    def _log_threadsafe(self, text):
        """Log sink for worker threads (cleanup, viewer link)."""
        self.bridge.post(self.run_panel.on_log, str(text))

    def _result_msg(self, text):
        """Results-panel messages - exports, post-mortem loads, viewer
        hints - go to the run log AND the status bar. Only the Run tab
        shows the log, and someone standing on Results would otherwise
        get no sign that an export had finished or failed."""
        text = str(text)
        self._log_threadsafe(text)
        low = text.lower()
        level = 'error' if ('fail' in low or 'error' in low) else 'info'
        self.bridge.post(self.notify, text, level)

    # ── shutdown ─────────────────────────────────────────────────────────
    def closeEvent(self, event):
        self._save_ui_state()
        self._wsl_timer.stop()
        self._validate_timer.stop()
        self._status_timer.stop()
        self.ctrl.shutdown()
        # release the embedded window first, then stop the child: the
        # reverse order leaves Qt holding a dangling HWND
        for panel in (self.view3d, self.results):
            try:
                panel.shutdown()
            except Exception:
                pass
        self.viewer_link.close()
        event.accept()


def main(case_file=None):
    # Before the window, so a failure while BUILDING it is reported too.
    # An unhandled exception in a Qt slot used to abort the process with
    # no traceback anywhere - see ui/crashlog.py for the run that found
    # that out the hard way.
    from . import crashlog
    crashlog.install()
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName('blastlab')
    st = app_settings.load()
    theme.apply(app, st.get('appearance', 'dark'))
    win = MainWindow(case_file=case_file)
    win.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
