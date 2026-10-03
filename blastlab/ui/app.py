"""blastlab Qt main window: the 64 px top bar (workflow pills, case
menu, solver chip, dimension control), the content stack and the 28 px
status bar (GUI-3, plan §4; board BC_Combined). A port of gui/app.py."""

import json
import os
import sys
import threading

from PySide6.QtCore import QEvent, QTimer
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout,
                               QMainWindow, QMenu, QSizePolicy,
                               QStackedWidget, QVBoxLayout, QWidget)

from .. import __version__
from ..core import hardware
from ..core import mode as mode_mod
from ..core import settings as app_settings
from ..core.case import (load_case, long_run_note, save_case,
                         validate_case)
from ..core.mode import SolverMode
from ..models import hd13_case
from ..models.case import load_any_case
from ..services.model_folder import CASE_FILE, model_for_case_file
from ..solvers.foam import env as foam_env
from ..viz3d import pyvista_available
from . import chain_route, dialogs, theme
from .bridge import ThreadBridge
from .chain_panel import ChainPanel
from .chain_strip import ChainStrip
from .results_panel import ResultsPanel
from .run_clock import fmt_duration
from .run_controller import RunController
from .run_gauges import highest_peak
from .run_panel import RunPanel
from .setup_panel import SetupPanel
from .theme import PAD
from .topbar import TopBar, dot_pixmap
from .view3d_host import View3DHost
from .viewer_link import ViewerLink
from .widgets import label, refresh_icons

CASE_FILTER = 'blastlab case (*.json);;All files (*.*)'

#: The GIL switch interval while an HD 1.3 assessment runs on its thread
#: (Python's default is 5 ms). The assessment is pure-Python loops, and at
#: 5 ms every GIL hand-back to the GUI thread cost up to 5 ms, so one
#: live validation took ~250 ms instead of ~8 ms and its repaint stalled
#: the window for ~600 ms. At 0.5 ms: ~20 ms and a longest gap of ~60 ms,
#: for ~3 % on the assessment's wall clock (measured, UX_REVIEW finding 1).
#: Scheduling only - no number the assessment returns can depend on it.
_HD13_SWITCH_INTERVAL = 0.0005

#: Stop asks first once a run has had this much run time - held time
#: excluded (plan §6, UX-7; decision D50). Shorter runs stop at once.
STOP_CONFIRM_S = 30.0


class MainWindow(QMainWindow):
    #: How a failed run is reported (see RunController.show_error).
    show_error = staticmethod(lambda title, msg: dialogs.show_error(title, msg))

    def __init__(self, case_file=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('untitled · BlastLab')
        self.resize(1280, 840)
        self.setMinimumSize(1100, 720)
        # GUI-2: the QPainter-drawn app icon (plan §3); the ELSL gif
        # logo stays with the Tk app (gui/app.py)
        self.setWindowIcon(theme.app_icon())

        self.bridge = ThreadBridge(self)
        self._hd13_busy = False     # an HD 1.3 assessment is on its thread
        self._switch_interval = sys.getswitchinterval()
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

        # GUI-3 (plan §4): the dirty flag and the title's run state
        self._dirty = False
        self._running_ui = False
        self._run_pct = None
        self._chain_k = 0
        self._chain_n = 0
        # GUI-9: the running chain's 02 Run strip (None for a single run)
        # and its one 03 Results entry (None until its first result)
        self._chain_strip = None
        self._chain_entry = None
        # GUI-6: the start in progress was an Initialise (held at step 0);
        # the controller's on_running(True) carries no such flag
        self._start_paused = False

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        # the top bar replaces the 216 px sidebar (GUI-3, no sidebar)
        self.topbar = TopBar()
        self.topbar.navigate.connect(self._show)
        self.topbar.dim_selected.connect(lambda d: self.setup.set_dim(d))
        self.topbar.case_clicked.connect(self._show_case_menu)
        self.topbar.chip_clicked.connect(self._show_chip_menu)
        outer.addWidget(self.topbar)
        #: the pills, for the QA harness (B04) and the hover checks
        self._nav_btns = self.topbar.nav_btns

        column = QVBoxLayout()
        column.setContentsMargins(PAD, 10, PAD, 8)
        column.setSpacing(6)
        outer.addLayout(column, 1)
        self._stack = QStackedWidget()
        column.addWidget(self._stack, 1)
        outer.addWidget(self._build_statusbar())
        self._status_timer.timeout.connect(self._clear_status)
        self._case_menu = self._build_case_menu()
        self._chip_menu = self._build_chip_menu()

        self.viewer_link = ViewerLink(self, log_fn=self._log_threadsafe)
        self.view3d = View3DHost(self.viewer_link, 'run',
                                 log_fn=self._log_threadsafe)
        self.setup = SetupPanel(on_change=self._setup_changed,
                                mode=self.solver_mode,
                                viewer_link=self.viewer_link,
                                log_fn=self._log_threadsafe)
        self.run_panel = RunPanel(view3d_host=self.view3d)
        # GUI-6: run time with held time excluded (ui/run_clock.py) -
        # the elapsed line, the ETA and the 30 s Stop rule read it
        self._run_clock = self.run_panel.clock
        self._run_got_result = False    # a result landed in this run
        self._last_result = None        # the newest Result of this run
        # `✓ Done · ` in the title after a run that ended on its own,
        # until the next run or Open case (decision D68)
        self._done_mark = False
        self._stop_asked = False        # the user pressed Stop in this run
        #: the case of each stage of the run in progress (one for a single
        #: run, the stage cases of a chain); the Stop question reads the
        #: running stage's solver from it
        self._run_cases = []
        self.results = ResultsPanel(viewer_link=self.viewer_link,
                                    log_fn=self._result_msg,
                                    mode=self.solver_mode,
                                    on_resume=self._resume_foam_run,
                                    bridge=self.bridge)
        self.results.load_case_requested.connect(self._load_case_from_result)
        self.chain = ChainPanel(on_run_chain=self._run_chain,
                                mode=self.solver_mode,
                                log_fn=self._log_threadsafe,
                                model_source=lambda: (
                                    self.run_panel.current_runs_dir(),
                                    self.run_panel.current_run_name()),
                                # GUI-9: new stages start from 01 Setup;
                                # Load case… reads as Open case does
                                setup_source=self.current_case,
                                case_reader=lambda path: (
                                    self._read_case_file(path, 'Load case')))
        # a Run-tab model change restarts the Chain's live checks (the
        # Run chain line and the folder note name the model)
        for box in (self.run_panel.runs_dir, self.run_panel.run_name):
            box.textChanged.connect(
                lambda _t: self.chain.schedule_checks())
        # GUI-9: the top bar's Chain link names the route
        self.chain.route_changed.connect(
            lambda key: self.topbar.set_chain_label(
                'Chain ' + chain_route.route_label(key)))
        self._panels = {'setup': self.setup, 'run': self.run_panel,
                        'results': self.results, 'chain': self.chain}
        for panel in self._panels.values():
            self._stack.addWidget(panel)

        self.ctrl = RunController(handlers=self, view3d=self.view3d,
                                  parent=self)
        self.run_panel.run_requested.connect(lambda: self._run_single())
        # GUI-5b: the Setup strip's Run F5 / Initialise are the same
        # actions as the Run tab's buttons and the F5 key
        self.setup.run_requested.connect(lambda: self._run_single())
        self.setup.init_requested.connect(lambda: self._init_model())
        self.run_panel.stop_requested.connect(self._stop)
        self.run_panel.view3d_requested.connect(self._open_view3d)
        self.run_panel.init_requested.connect(self._init_model)
        self.run_panel.exec_requested.connect(self.ctrl.exec_cmd)
        self.run_panel.refresh_changed.connect(self._apply_refresh)
        self.run_panel.gauges_wanted.connect(self._gauges_wanted)
        self.run_panel.runs_dir_changed.connect(self._save_runs_dir)
        # GUI-6: the Run screen's `Setup: Case OK` link goes back to Setup
        self.run_panel.setup_requested.connect(lambda: self._show('setup'))
        # GUI-6b: the finish banner's `Open in 03 Results →`
        self.run_panel.results_requested.connect(self._open_results)

        # N8: sweep old/large WSL run dirs per the persisted settings,
        # off-thread (WSL round trips must never block the window)
        self._cleanup_thread = foam_env.start_auto_cleanup(
            st, self._log_threadsafe)
        # owner 2026-09-27: with the sweep off (the default), warn - never
        # delete - when the runs root is over cleanup_max_gb
        self._disk_warning_thread = foam_env.start_disk_warning(
            st, self._disk_warning)

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

    # ── frame: status bar, menus, navigation (GUI-3, plan §4) ───────────
    def _build_statusbar(self):
        """The 28 px status bar (board BC_Combined footer, lines
        392-396): WSL dot + text · the dirty context · the app-wide
        status line (`self._status` - name, `notify()` semantics, timer
        and tooltip behaviour unchanged) · the shortcuts + version."""
        bar = QFrame()
        bar.setObjectName('statusbar')
        bar.setFixedHeight(28)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(12)
        self._wsl_dot = label('')
        self._wsl_dot.setFixedWidth(9)
        self._wsl_dot.setVisible(False)
        lay.addWidget(self._wsl_dot)
        self._wsl_hint = label('', 'small')
        self._wsl_hint.setMinimumWidth(10)     # may compress, never clip
        lay.addWidget(self._wsl_hint)
        # `<case>.json has unsaved changes` (plan §4). Its own label, so
        # `self._status` keeps its pinned notify()/timer semantics
        # (test_ui_char_hd13_run) - decision D10.
        self._dirty_lbl = label('', 'small')
        self._dirty_lbl.setMinimumWidth(10)
        lay.addWidget(self._dirty_lbl)
        # one status line for the whole window: exports, loads and solver
        # warnings used to land only in the Run tab's log
        self._status = label('', 'small')
        self._status.setMinimumWidth(10)
        self._status.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lay.addWidget(self._status, 1)
        self._keys_lbl = label(f'Ctrl+S save · F5 run · Shift+Esc stop '
                               f'· v{__version__}')
        self._keys_lbl.setMinimumWidth(10)
        lay.addWidget(self._keys_lbl)
        self._style_statusbar()
        return bar

    def _style_statusbar(self):
        """Mode-dependent colours the QSS cannot carry (re-run on a
        theme switch)."""
        self._keys_lbl.setStyleSheet(
            f'font-family: "{theme.MONO}"; font-size: 11px; '
            f'color: {theme.cur("faint")};')
        self._dirty_lbl.setStyleSheet(f'color: {theme.cur("muted")};')

    def _build_case_menu(self):
        """The case-name button's menu (plan §4, UX-8). The `\\t` texts
        show the keys without binding them - the QShortcuts of
        `_bind_accelerators` are the only bindings."""
        m = QMenu(self)
        m.addAction('Open…\tCtrl+O', lambda: self._open_case())
        m.addAction('Save\tCtrl+S', self._save_case_inplace)
        m.addAction('Save as…\tCtrl+Shift+S', self._save_case)
        self._recent_menu = m.addMenu('Recent')
        self._recent_menu.aboutToShow.connect(self._fill_recent_menu)
        m.addSeparator()
        self._dark_action = QAction('Dark mode', self)
        self._dark_action.setCheckable(True)
        self._dark_action.setChecked(theme.mode() == 'dark')
        self._dark_action.toggled.connect(self._toggle_mode)
        m.addAction(self._dark_action)
        m.addSeparator()
        credit = m.addAction('By Ofek Rotem')
        credit.setEnabled(False)                # decision D11
        return m

    def _fill_recent_menu(self):
        self._recent_menu.clear()
        rec = app_settings.load().get('recent_cases') or []
        if not rec:
            none = self._recent_menu.addAction('No recent cases')
            none.setEnabled(False)
            return
        for p in rec[:self.RECENT_MAX]:
            # a missing file goes through _open_case's FileNotFound path
            self._recent_menu.addAction(os.path.basename(p),
                                        lambda p=p: self._open_case(p))

    def _show_case_menu(self):
        b = self.topbar.case_btn
        self._case_menu.popup(b.mapToGlobal(b.rect().bottomLeft()))

    def _build_chip_menu(self):
        """The solver chip's menu = the old sidebar switch (T34):
        exclusive native / blastFoam, the hardware line (N17/T48) and
        Re-detect."""
        m = QMenu(self)
        group = QActionGroup(m)
        group.setExclusive(True)
        self._chip_actions = {}
        for mode in mode_mod.MODES:
            act = QAction(mode_mod.label(mode), m)
            act.setCheckable(True)
            act.setActionGroup(group)
            act.triggered.connect(
                lambda _c=False, mm=mode: self.solver_mode.set(mm))
            m.addAction(act)
            self._chip_actions[mode] = act
        self._chip_actions[self.solver_mode.get()].setChecked(True)
        m.addSeparator()
        self._chip_info = m.addAction('')
        self._chip_info.setEnabled(False)
        m.addAction('Re-detect', self._redetect_hw)
        m.aboutToShow.connect(self._fill_chip_info)
        return m

    def _fill_chip_info(self):
        suffix = self._hw_suffix().strip(' ·')
        self._chip_info.setText(suffix or 'hardware unknown')

    def _show_chip_menu(self):
        b = self.topbar.chip
        self._chip_menu.popup(b.mapToGlobal(b.rect().bottomLeft()))

    def _show(self, key):
        self._stack.setCurrentWidget(self._panels[key])
        for k, b in self._nav_btns.items():
            b.setProperty('active', 'true' if k == key else 'false')
            theme.repolish(b)
        # GUI-6b: the Run screen's live-gauge column is on screen
        self._sync_gauge_collection()

    def current_tab(self):
        for k, p in self._panels.items():
            if self._stack.currentWidget() is p:
                return k
        return None

    def _toggle_mode(self, checked):
        theme.apply(QApplication.instance(), 'dark' if checked else 'light')

    def _retheme(self, _mode=None):
        # the top bar re-tints itself on theme.signals.changed (GUI-3)
        refresh_icons(self)
        self._style_statusbar()
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
        # the chip is the old sidebar switch (GUI-3): sync the menu's
        # checked action, the chip text and the tooltip - silent, so
        # set_solver() cannot loop through the menu
        for mode, act in self._chip_actions.items():
            act.setChecked(mode == m)
        self.topbar.chip.setToolTip(mode_mod.EXPLAIN[m])
        self._wsl_timer.stop()
        if m == 'blastfoam':
            # warm the cached WSL availability check off-thread and show
            # its outcome on the chip and the status bar
            foam_env.ensure_check_started()
            self._probe_hw_async()
            self._poll_wsl()
        else:
            self.topbar.set_chip(mode_mod.label(m), None)
            self._wsl_hint.setText('')
            self._wsl_hint.setToolTip('')
            self._wsl_dot.setVisible(False)
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
        # blastfoam mode only: the probe thread posts this back and
        # must not overwrite the 'native' chip after a mode switch
        if self.solver_mode.get() != 'blastfoam':
            return
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
        # the chip mirrors it: dot ok / warn / danger (plan §4)
        blast_dim = getattr(getattr(self, 'setup', None), 'dim', 2) != 0
        chip_text, dot = {
            'checking': ('checking', 'warn'),
            'ok': ('WSL ready', colour if colour in ('ok', 'warn')
                   else 'ok'),
            'fail': ('WSL unavailable', 'danger'),
        }.get(state, ('WSL at run start', 'warn'))
        self.topbar.set_chip(f'{mode_mod.label("blastfoam")} · '
                             f'{chip_text}', dot)
        self._wsl_dot.setPixmap(dot_pixmap(colour if colour != 'muted'
                                           else 'faint'))
        self._wsl_dot.setVisible(blast_dim)
        if state == 'checking':
            self._wsl_timer.start()

    # ── G9: keyboard + persisted window state ────────────────────────────
    def _bind_accelerators(self):
        # plan §4 / UX-7: Shift+Esc stops - plain Esc is deliberately
        # NOT bound; Ctrl+S saves in place, Ctrl+Shift+S is Save as
        for seq, fn in (('Ctrl+O', self._open_case),
                        ('Ctrl+S', self._save_case_inplace),
                        ('Ctrl+Shift+S', self._save_case),
                        ('F5', self._run_single),
                        ('Shift+Esc', self._stop)):
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
        self.run_panel.set_runs_dir(st.get('runs_dir', ''))

    def _save_runs_dir(self):
        """OUT-1: the Runs folder box is remembered across sessions."""
        try:
            app_settings.update(runs_dir=self.run_panel.current_runs_dir())
        except Exception:
            pass

    def _save_ui_state(self):
        try:
            val, mode = self.run_panel.refresh_policy_text()
            state = dict(appearance=theme.mode(), refresh_value=val,
                         refresh_mode=mode, solver=self.solver_mode.get(),
                         runs_dir=self.run_panel.current_runs_dir())
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

    def _read_case_file(self, path, title='Open case'):
        """The case in `path` (`load_any_case`), or None after an error
        dialog titled `title` saying why it could not be read."""
        try:
            # a blast case, or an HD 1.3 one for the 0-D form (QA F2)
            return load_any_case(path)
        except FileNotFoundError:
            self.show_error(title, f'File not found: {path}')
        except json.JSONDecodeError as exc:
            self.show_error(title, f'This file is not valid JSON '
                                   f'(line {exc.lineno}, column '
                                   f'{exc.colno}).')
        except (KeyError, TypeError) as exc:
            self.show_error(title, f'Not a blastlab case file: '
                                   f'unsupported or missing field {exc}.')
        except OSError as exc:
            self.show_error(title, f'Could not read the file: '
                                   f'{exc.strerror or exc}')
        except Exception as exc:
            msg = str(exc)
            self.show_error(title, msg if 'case file' in msg.lower()
                            else f'Not a blastlab case file: {msg}')
        return None

    def _open_case(self, path=None):
        path = path or dialogs.open_file('Open case', CASE_FILTER, self)
        if not path:
            return
        case = self._read_case_file(path)
        if case is None:
            return
        self._case_path = path
        self.setup.set_case(case)
        self._maybe_prewarm_viewer(case)
        # a run started from this case is named after the file (N9) - the
        # model it came from, replacing the last name (GUI QA C1: the next
        # Run offered to overwrite the PREVIOUS model)
        self.run_panel.set_run_name(model_for_case_file(path), replace=True)
        # a set_case from Open does not mark dirty (plan §4)
        self._push_recent(path)
        self._done_mark = False
        self._set_dirty(False)
        self.topbar.set_case_name(self._case_stem())
        self._update_title()
        self._show('setup')
        self._schedule_validate()

    def _load_case_from_result(self, path):
        """Results → Load into 01 Setup (UX-15): the case a result was
        run from (its model folder's MODEL.json, or a loaded run's
        case.json) as a NEW, unsaved case. The path is dropped, so Ctrl+S
        goes to Save as and never writes into the model folder's record
        of the run (batch risk 5)."""
        case = self._read_case_file(path, 'Load into 01 Setup')
        if case is None:
            return False
        if self._dirty and not dialogs.ask_yes_no(
                'Load into 01 Setup',
                f'Replace the unsaved changes in {self._case_stem()}?',
                self, yes='Replace', no='Keep editing'):
            return False
        self.setup.set_case(case)
        if os.path.basename(path) == CASE_FILE:
            model = model_for_case_file(path)
        else:                       # <run dir>\case.json: the run's name
            model = os.path.basename(os.path.dirname(os.path.abspath(path)))
        self.run_panel.set_run_name(model, replace=True)
        self._case_path = None
        # a case was opened: `✓ Done` belonged to the last run (D68)
        self._done_mark = False
        self._set_dirty(True)
        self.topbar.set_case_name(self._case_stem())
        self._update_title()
        self._show('setup')
        self._schedule_validate()
        return True

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

    @staticmethod
    def _case_writer(case):
        # P1-18: the 0-D form's DeflagrationCase is an HD 1.3 file
        # (schema 'blastlab-hd13'), which Open reads back; the blast
        # writer used to stamp it 'blastlab-case' and Open refused it
        return (hd13_case.save_case if getattr(case, 'dim', None) == 0
                else save_case)

    def _save_case(self):
        """Save as… (Ctrl+Shift+S): always through the file dialog."""
        try:
            case = self.setup.get_case()
        except ValueError as exc:
            self.show_error('Save case', str(exc))
            return
        path = dialogs.save_file('Save case', 'blastlab case (*.json)', self,
                                 default_suffix='json')
        if not path:
            return
        self._case_writer(case)(case, path)
        self._case_path = path
        self._push_recent(path)
        self._set_dirty(False)
        self.topbar.set_case_name(self._case_stem())
        self._update_title()

    def _save_case_inplace(self):
        """Save (Ctrl+S): in place when the case has a path, no dialog;
        else Save as - never a silent write to a guessed path (plan §4)."""
        if not self._case_path:
            self._save_case()
            return
        try:
            case = self.setup.get_case()
        except ValueError as exc:
            self.show_error('Save case', str(exc))
            return
        try:
            self._case_writer(case)(case, self._case_path)
        except OSError as exc:
            self.show_error('Save case',
                            f'Could not write {self._case_path}: {exc}')
            return
        self._set_dirty(False)

    #: Recent-menu length cap (plan §4)
    RECENT_MAX = 8

    def _push_recent(self, path):
        """`recent_cases` in the settings file: most recent first, no
        duplicates, at most RECENT_MAX. No DEFAULTS entry is needed -
        `settings.load()` keeps unknown keys (decision D9)."""
        path = os.path.abspath(path)
        try:
            st = app_settings.load()
            rec = [p for p in (st.get('recent_cases') or [])
                   if os.path.normcase(str(p)) != os.path.normcase(path)]
            rec.insert(0, path)
            app_settings.update(recent_cases=rec[:self.RECENT_MAX])
        except Exception:
            pass

    # ── dirty flag + window title (GUI-3, plan §4) ───────────────────────
    def _setup_changed(self):
        """Setup's on_change: the debounced validation plus the dirty
        flag (piggybacked where the validation is scheduled)."""
        self._set_dirty(True)
        self._schedule_validate()

    def _set_dirty(self, dirty):
        """The ● unsaved state: the top-bar marker, the status-bar
        context line and the title. Cleared on open / save / save-as
        and at the startup baseline."""
        self._dirty = bool(dirty)
        self.topbar.set_dirty(self._dirty)
        if self._dirty:
            name = (os.path.basename(self._case_path) if self._case_path
                    else 'this case')
            self._dirty_lbl.setText(f'{name} has unsaved changes')
        else:
            self._dirty_lbl.setText('')
        self._update_title()

    def _case_stem(self):
        if not self._case_path:
            return 'untitled'
        return os.path.splitext(os.path.basename(self._case_path))[0]

    def _update_title(self):
        """`<case> · BlastLab`; `<pct> % · ` while a run goes (UX-19),
        `Chain k/n · ` during a chain; ● marks the dirty state
        (decision D8). QWinTaskbarProgress is gone in Qt 6 - the title
        is enough (plan §4)."""
        parts = ''
        if self._running_ui and self._chain_n > 1:
            parts += f'Chain {self._chain_k}/{self._chain_n} · '
        if self._running_ui and self._run_pct is not None:
            parts += f'{self._run_pct} % · '
        if self._done_mark and not self._running_ui:
            parts += '✓ Done · '        # GUI-6b (board Run_Finished)
        mark = '● ' if self._dirty else ''
        self.setWindowTitle(f'{parts}{mark}{self._case_stem()} · BlastLab')

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
            # Setup pill ✓ = the last debounced validation was clean
            # (decision D7)
            self.topbar.set_done('setup', False)
            self.setup.update_preview(None)
            # GUI-5: the tree's marks and children (no case to summarise)
            self.setup.refresh(None, None)
            return
        if getattr(case, 'dim', None) == 0:
            # HD 1.3: a different validator, the SAME ValidationReport, so
            # everything below this point is unchanged - which is why
            # core/assessment returns that type rather than its own.
            from ..core.assessment import validate as validate_hd13
            rep = validate_hd13(case)
            self.setup.show_report(rep.errors, rep.warnings, rep.notes)
            self.run_panel.set_setup_case(case)
            self.run_panel.set_validation(not rep.errors, len(rep.errors))
            self.topbar.set_done('setup', not rep.errors)
            self.setup.update_preview(case)
            self.setup.refresh(case, rep)
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
        # GUI-6b: until the first run the gauge column lists these gauges
        self.run_panel.set_setup_case(case)
        # GUI-6: the Run screen's Setup link shows the report's cell count
        self.run_panel.set_validation(not rep.errors, len(rep.errors),
                                      n_cells=rep.n_cells)
        self.topbar.set_done('setup', not rep.errors)
        self.setup.update_preview(case)
        # GUI-5: the model tree's summaries, marks and children, and the
        # Derived card, from the same case and report
        self.setup.refresh(case, rep)

    # ── running ──────────────────────────────────────────────────────────
    def _run_single(self, paused=False):
        if self._hd13_busy:
            # F5 and Initialise Model reach here with Run greyed
            return
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
        model = self._model_target()
        if model is None:
            return
        # read by on_running(True): an Initialise opens Step through
        self._start_paused = bool(paused)
        self._run_cases = [case]
        try:
            started = self.ctrl.start_stages(
                [(case.dim, case)], paused=paused, run_name=model.model,
                model=model, reports=[rep])
        finally:
            self._start_paused = False
        if started:
            self._show('run')

    def model_check(self):
        """OUT-1: what is wrong with the Run tab's Runs folder and Model
        boxes ([] = a run may start). No file is touched."""
        from ..services import model_folder
        return model_folder.check(self.run_panel.current_runs_dir(),
                                  self.run_panel.current_run_name())

    def _model_target(self, title='Run'):
        """OUT-1 pre-flight, after the case validation and before anything
        is written: refuse with one message naming the box when the Runs
        folder or the Model name is wrong, ask before overwriting an
        existing model, and return the prepared `model_folder.Target` -
        or None, having said why (or the user said No)."""
        from ..services import model_folder
        if self.ctrl.running or self._hd13_busy:
            # before prepare: an overwrite could hit the running model (an
            # HD 1.3 assessment runs on its own thread, not the controller:
            # the Chain tab and a resume are not greyed by it)
            dialogs.show_info('Run', 'A run is already in progress.')
            return None
        errors = self.model_check()
        if errors:
            self.show_error(title, '\n'.join(errors))
            return None
        try:
            return model_folder.prepare_target(
                self.run_panel.current_runs_dir(),
                self.run_panel.current_run_name(),
                confirm=lambda text: dialogs.ask_yes_no(
                    'Model folder', text, self))
        except model_folder.ModelFolderError as exc:
            self.show_error(title, str(exc))
            return None

    def _dim_changed(self, dim):
        """Hide, never grey, the controls a dimension does not have - the
        app-wide rule (CLAUDE.md Sec. 4). A 0-D case has no solver
        backend, so the solver chip and the WSL line go (HD1-11c)."""
        blast = int(dim) != 0
        self.topbar.set_chip_visible(blast)
        self._wsl_hint.setVisible(blast)
        self._wsl_dot.setVisible(blast and bool(self._wsl_hint.text()))
        # two-way dimension sync (silent - the Segmented convention)
        self.topbar.set_dim(int(dim))
        # GUI-6: the Run screen hides what a 0-D assessment does not have
        self.run_panel.set_dim(int(dim))
        if blast:
            self._on_solver_mode(self.solver_mode.get())

    def _run_hd13(self, case):
        """Run an HD 1.3 assessment and write its report.

        Not through RunController: that machinery is for a solve with
        frames, gauges, stepping and resume. A 0-D deflagration case is
        closed form but not instant - the starter case takes about 40 s
        with the sensitivity band off, about 20 min with it on - so the
        assessment runs ONCE, on a worker
        thread, and the outcome comes back through `self.bridge`; the
        worker touches no widget (UX_REVIEW finding 1). Meanwhile Run,
        F5 and Initialise Model are off, the Run tab's bar is
        indeterminate and the status line says what is running.

        There is no Cancel: `assessment.run` has no cooperative stop
        hook, and the physics does not grow one for a button.

        Validation and the model folder (OUT-1: `_model_target`, the same
        pre-flight as every run) are settled here, on the GUI thread.
        Pinned by `tests/test_ui_char_hd13_run.py`.
        """
        # Imported here, and called through the module, so a test that
        # patches `assessment.run` is honoured.
        from ..core import assessment
        from ..services import hd13 as hd13_service
        rep = assessment.validate(case)
        if not rep.ok:
            self.show_error('Run', '\n'.join(rep.errors))
            return
        model = self._model_target()
        if model is None:
            return

        def work():
            out = err = loads = None
            try:
                # OUT-1: <MODEL>\MODEL.json, read back for the assessment
                # (the provenance the leaked temp case file stood for,
                # ARCHITECTURE_REVIEW Q4), then the report, the loads and
                # the manifest; a failure leaves MODEL.json and a manifest
                bundle = hd13_service.run_into_model_folder(
                    case, model, log=self._log_threadsafe)
                out, loads = bundle['report'], bundle.get('loads')
            except Exception as exc:           # noqa: BLE001 - shown to the user
                err = exc
            finally:
                self.bridge.post(self._hd13_done, out, err, loads)

        self._set_hd13_busy(True)
        threading.Thread(target=work, name='hd13-assessment',
                         daemon=True).start()

    def _set_hd13_busy(self, busy):
        """GUI thread: enter or leave the HD 1.3 busy state.

        Entering greys the Run controls, shows the running status and
        lowers the GIL switch interval for the worker's lifetime (see
        `_HD13_SWITCH_INTERVAL`); leaving restores the interval saved on
        entry. The status line after a run is `_hd13_done`'s business.
        """
        self._hd13_busy = bool(busy)
        # GUI-6: the progress strip's clock counts the assessment
        if busy:
            self._run_clock.start()
            # GUI-9: an assessment is a run start too - the last chain's
            # strip goes (it would describe a run that is not this one)
            self._chain_strip = None
            self.run_panel.set_chain_strip(None)
        else:
            self._run_clock.stop()
        self.run_panel.set_busy(busy)
        if busy:
            self._switch_interval = sys.getswitchinterval()
            sys.setswitchinterval(min(self._switch_interval,
                                      _HD13_SWITCH_INTERVAL))
            self._status.setText('HD 1.3 assessment running…')
            self._status.setToolTip('')
            self._status.setStyleSheet(f'color: {theme.cur("muted")};')
            self._status_timer.stop()
        else:
            sys.setswitchinterval(self._switch_interval)

    def _hd13_done(self, out, err, loads=None):
        """GUI thread: the worker of `_run_hd13` has finished.

        `loads` is `output/load_csv.export_hd13`'s result (HD1-16). The
        full text - the report, the load folder and every CSV as absolute
        paths, and each "record ends while the load is still active"
        message verbatim - goes to the Run log and the status tooltip; the
        status line gets a short summary that fits, as a warning when that
        rule fired (QA 2026-09-26-hd1-16 F2: one line of ~3300 px was
        clipped to "HD 1.3 report written: C:\\...")."""
        self._set_hd13_busy(False)
        if err is not None:
            self._status.setText('')
            self._status.setToolTip('')
            self.show_error('HD 1.3 assessment', str(err))
            return
        files = (loads or {}).get('files') or []
        msgs = (loads or {}).get('messages') or []
        lines = [f'HD 1.3 report written: {os.path.abspath(out)}']
        if files:
            lines.append(f'SBEDS loads: {len(files)} CSV in '
                         f'{os.path.abspath(loads["dir"])}')
            lines += [f'  {os.path.abspath(f)}' for f in files]
        lines += [f'{name}: {msg}' for name, msg in msgs]
        for line in lines:
            self.run_panel.on_log(line)
        summary = (f'HD 1.3 done - report and {len(files)} SBEDS load CSV'
                   f'{"" if len(files) == 1 else "s"} written' if files
                   else 'HD 1.3 done - report written')
        if msgs:
            summary += (f'; {len(msgs)} load record'
                        f'{" ends" if len(msgs) == 1 else "s end"} while '
                        f'the load is still active')
        self.notify(f'{summary} (see Log)', 'warn' if msgs else 'info')
        self._status.setToolTip('\n'.join(lines))

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

    def _run_chain(self, dim_cases):
        """The Chain panel has already validated and wired the stages
        into the model folder's paths; what is left is the long-run
        question, the model folder itself (OUT-1: created only now, after
        asking for an existing one) and the launch as one worker, so the
        Run tab, Stop and Results behave as usual. False when it did not
        start."""
        cases = [c for _d, c in dim_cases]
        if not self._confirm_long_run(cases):
            return False
        model = self._model_target('Chain')
        if model is None:
            return False
        # the manifest's n_cells / n_procs, one report per stage
        reports = [validate_case(c, pending_inputs=k > 0)
                   for k, c in enumerate(cases)]
        self.notify(f'Chain: {len(dim_cases)} stage(s) into {model.folder}')
        self._run_cases = list(cases)
        if self.ctrl.start_stages(dim_cases, run_name=model.model,
                                  model=model, reports=reports):
            self._show('run')
            return True
        return False

    def _init_model(self):
        """VIPER-style 'Initialise Model': start the run held at step 0
        so the initial field is visible; Exec buttons advance it."""
        self._run_single(paused=True)

    def _stop(self):
        """Stop: the Run screen's button, Shift+Esc and the QA harness
        all come here. Plain Esc is not bound (UX-7).

        With no run live, or under STOP_CONFIRM_S of run time (held time
        excluded), it stops at once exactly as before - test_ui_frame F5
        pins that Shift+Esc reaches `ctrl.stop` with nothing running.
        From 30 s on it asks first (plan §6); on *Stop the run* it stops
        only if the run is still going (it may have ended meanwhile)."""
        if self.ctrl.running \
                and self._run_clock.run_s() >= STOP_CONFIRM_S:
            if not dialogs.ask_yes_no('Stop the run', self._stop_question(),
                                      self, yes='Stop the run',
                                      no='Keep running'):
                return
            if not self.ctrl.running:
                return
        if self.ctrl.running:
            self._stop_asked = True
        self.ctrl.stop()

    def _running_case(self):
        """The case of the stage now running, or None."""
        cases = self._run_cases or []
        k = max(self._chain_k, 1) - 1
        return cases[k] if k < len(cases) else None

    def _stop_question(self):
        """`Stop <model> (stage k of n) at 78 %?` + the run time (board
        Run lines 348-350). The resume sentence only for a blastFoam
        stage: `model_folder.release_decision` keeps the WSL scratch of a
        run that ended early, and the run browser resumes it."""
        model = self.ctrl._run_name or self._case_stem()
        stage = (f' (stage {max(self._chain_k, 1)} of {self._chain_n})'
                 if self._chain_n > 1 else '')
        at = f' at {self._run_pct} %' if self._run_pct is not None else ''
        text = (f'Stop {model}{stage}{at}?\n\nIt has been running for '
                f'{fmt_duration(self._run_clock.run_s())}.')
        case = self._running_case()
        if getattr(case, 'solver', None) == 'blastfoam':
            text += (' blastFoam keeps what it has written, so you can '
                     'resume it later from the runs list.')
        return text

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
        # a (chain) stage: its ETA restarts, the run time goes on
        self._run_clock.stage()
        self.run_panel.on_run_started(info)
        # k of the title's `Chain k/n · ` = runs started since
        # start_stages (plan §4)
        self._chain_k += 1
        self._update_title()
        if self._chain_strip is not None:
            self._chain_strip.stage_started(self._chain_k - 1)
        # GUI-6b: the gauge column's Z and walls are this stage's case
        self.run_panel.set_gauge_case(self._running_case())

    def on_view3d_available(self, is3d):
        self.run_panel.enable_view3d(is3d)

    def on_cadence(self, dt, steps):
        self.run_panel.set_cadence(dt, steps)

    def on_progress(self, p):
        self.run_panel.on_progress(p)
        pct = int(round(100 * max(0.0, min(1.0, p.frac))))
        if pct != self._run_pct:        # whole-percent changes only
            self._run_pct = pct
            self._update_title()
            if self._chain_strip is not None:
                self._chain_strip.set_pct(self._chain_k - 1, pct)

    def on_paused(self, paused):
        # held time is not run time (decision D50)
        self._run_clock.hold(paused)
        self.run_panel.set_paused(paused)

    def on_frame(self, field, t, levels=None):
        self.run_panel.on_frame(field, t, levels)

    def on_gauges(self, payload):
        self.run_panel.set_gauge_payload(payload)

    def _sync_gauge_collection(self):
        """GUI-6b collection rule (decisions D60, D69): live gauge traces
        are collected while the Run screen's gauge column is visible - the
        Run screen is current and the window is not minimised - or the
        view's Gauges segment is selected, and not otherwise: a native run
        copies every series on each live frame, a foam run re-reads
        blastProbes. Display only: the solver's own gauge record does not
        depend on it (T9: the arrays are identical either way)."""
        ctrl = getattr(self, 'ctrl', None)
        if ctrl is None:
            return
        column = self.current_tab() == 'run' and not self.isMinimized()
        ctrl.set_live_gauges(column or self.run_panel.watching_gauges())

    def changeEvent(self, event):
        super().changeEvent(event)
        # minimised or restored: the gauge column left or came back
        if event.type() == QEvent.WindowStateChange:
            self._sync_gauge_collection()

    def _gauges_wanted(self, on):
        """The live gauge view was opened or left."""
        self._sync_gauge_collection()
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
        if running:
            self._run_clock.start()
            self._run_got_result = False
            self._last_result = None
            self._stop_asked = False
            self._done_mark = False
            # the last run's notification icon goes (plan §6)
            dialogs.clear_tray()
            if self._start_paused:
                # Initialise: the run starts held at step 0
                self._run_clock.hold(True)
        else:
            self._run_clock.stop()
        # the dock keeps the last run's log under this run's name
        model = getattr(self.ctrl, '_model', None)
        self.run_panel.set_running(
            running, paused=bool(running) and self._start_paused,
            model=getattr(self.ctrl, '_run_name', None) or None,
            folder=getattr(model, 'folder', None))
        if running:
            # the gauge column shows the first stage's gauges, waiting
            self.run_panel.set_gauge_case(
                self._run_cases[0] if self._run_cases else
                self.current_case())
        # a second start while a run is live would orphan the drain loop
        # and drop the finished result
        self.chain.set_running(running)
        # title progress state (plan §4): restored when the run ends
        self._running_ui = bool(running)
        self._run_pct = None
        if running:
            self._chain_k = 0
            self._chain_n = len(getattr(self.ctrl, '_stage_dims', None)
                                or [])
            self._chain_entry = None
            self._show_chain_strip()
        self._update_title()

    def _show_chain_strip(self):
        """GUI-9 T4 (plan §6): a run of more than one stage gets a fresh
        chain strip in 02 Run's chain slot; a single run empties it. The
        last chain's strip stays after its end until this next start."""
        dims = list(getattr(self.ctrl, '_stage_dims', None) or [])
        if len(dims) < 2:
            self._chain_strip = None
            self.run_panel.set_chain_strip(None)
            return
        strip = ChainStrip()
        strip.set_chain(getattr(self.ctrl, '_run_name', '') or '', dims)
        # one row or two for the centre's width now, so it appears at
        # its final height (the viewer is shrunk ahead by that much)
        strip.arrange(self.run_panel.column_widths()[1])
        self._chain_strip = strip
        self.run_panel.set_chain_strip(strip)

    def on_result(self, k, dim, label_, res):
        if self._running_ui and k == len(
                getattr(self.ctrl, '_stage_dims', None) or []) - 1:
            # GUI-6b: the last stage's full traces in the gauge column
            # (only for a live run: tests feed on_result by hand)
            self.run_panel.set_final_gauges(getattr(res, 'gauges', None))
        if self._running_ui:
            self._last_result = res
            if self._chain_strip is not None:
                # the stage's run time, held time excluded (D50), its
                # folder writes included (D59)
                self._chain_strip.stage_done(
                    k, self._run_clock.stage_s(),
                    'stopped' if res.stopped_early else 'done')
        self._run_got_result = True
        self._results.append((label_, dim, res))
        self.results.add_result(label_, dim, res)
        # Run pill ✓ = a result landed this session (decision D7)
        self.topbar.set_done('run', True)
        self.notify(f'Result ready: {label_}')

    def on_finished(self, stopped_early, errored):
        if not (stopped_early or errored):
            # the last progress message is often throttled away, so a
            # completed run would otherwise rest below 100%
            self.run_panel.mark_complete()
        # the elapsed line says how the run ended (a Stop before the
        # first result leaves no result to call stopped: say so anyway)
        if errored:
            how = 'failed'
        elif stopped_early or (self._stop_asked
                               and not self._run_got_result):
            how = 'stopped'
        elif self._run_got_result:
            how = 'done'
        else:
            how = 'ended'
        self.run_panel.mark_ended(how)
        if self._chain_strip is not None:
            self._chain_strip.finish(how, self._run_clock.run_s())
        self._finish_notice(how)

    def _finish_notice(self, how):
        """GUI-6b (plan §6, When a run ends). An errored run keeps
        today's dialog path, and a run with no result (StoppedBeforeStart)
        gets nothing. Otherwise the banner names the model, how it ended
        (the last result's stop_reason, verbatim) and the model folder.
        A run that ended on its own - not stopped, not failed - also
        gets `✓ Done` in the title and one Windows notification: the run
        time and the highest peak of its gauges (decision D67)."""
        res = self._last_result
        if how not in ('done', 'stopped') or res is None:
            return
        model = getattr(self.ctrl, '_run_name', '') or self._case_stem()
        folder = getattr(getattr(self.ctrl, '_model', None), 'folder', None)
        self.run_panel.show_finish(model, getattr(res, 'stop_reason', ''),
                                   folder)
        self.run_panel.set_run_again(True)
        if how != 'done':
            return
        self._done_mark = True
        self._update_title()
        dialogs.notify_desktop('BlastLab', self._finish_text(model, res),
                               on_click=self._raise_on_results, parent=self)

    def _finish_text(self, model, res):
        """`<model> finished in 5 min 31 s. Highest peak: G6, 296 kPa at
        2.21 ms.` - the run time (held time excluded) and
        run_gauges.highest_peak of the last result's gauges; no gauge
        with an arrival leaves the second sentence out."""
        text = (f'{model} finished in '
                f'{fmt_duration(self._run_clock.run_s())}.')
        top = highest_peak(getattr(res, 'gauges', None))
        if top is not None:
            n, kpa, t_ms = top
            text += f' Highest peak: G{n}, {kpa:,.0f} kPa at {t_ms:.2f} ms.'
        return text

    def _open_results(self):
        """03 Results with the newest result selected."""
        self._show('results')
        sel = self.results.sel
        n = sel.count()
        if n and sel.currentIndex() != n - 1:
            sel.setCurrentIndex(n - 1)

    def _raise_on_results(self):
        """A click on the notification: the window back on Results. From
        a toast Windows may only flash the taskbar button (its
        foreground lock); that is accepted (batch risk 7)."""
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()
        self._open_results()

    def _resume_foam_run(self, path):
        """Resume a stopped blastFoam run. The dimension comes from the
        run's own case.json, so the run browser only has to hand over a
        path."""
        from ..services.foam_runs import dims_from_case_json
        from ..solvers.foam import env as _env
        try:
            _p, unc = _env.case_paths(path)
            dim = int((dims_from_case_json(unc) or '?').rstrip('D'))
            # OUT-1: the resume writes the model folder from the run's own
            # case, like a fresh run
            case = load_case(os.path.join(unc, 'case.json'))
        except (ValueError, OSError, TypeError, KeyError) as exc:
            self.notify(f'cannot resume {path}: {exc}', 'error')
            self._log_threadsafe(f'  [runs] cannot resume {path}: {exc}')
            return False
        model = self._model_target('Resume')
        if model is None:
            return False
        self._run_cases = [case]
        return self.ctrl.resume_foam_run(path, dim, run_name=model.model,
                                         model=model, case=case)

    # ── status line ──────────────────────────────────────────────────────
    def notify(self, text, level='info'):
        text = ' '.join(str(text).split())
        if not text:
            return
        colour = {'error': 'error', 'warn': 'warn'}.get(level, 'muted')
        # GUI-6 (UX-18): the Run dock's Messages page keeps the history
        # the 12 s status line loses
        self.run_panel.add_message(level, text)
        self._status.setText(text[:200])
        self._status.setToolTip(text)   # the whole text, past the cap
        self._status.setStyleSheet(f'color: {theme.cur(colour)};')
        # the message outranks the shortcuts hint: hide it so the summary
        # keeps the full label width it had before the 28 px status bar
        # (pinned by _e2e_hd13_gui: 'the summary fits inside the label');
        # _clear_status restores it with the message (decision D13)
        self._keys_lbl.setVisible(False)
        self._status_timer.start()

    def _clear_status(self):
        """The 12 s timer: clear the message, restore the shortcuts."""
        self._status.setText('')
        self._status.setToolTip('')
        self._keys_lbl.setVisible(True)

    def _log_threadsafe(self, text):
        """Log sink for worker threads (cleanup, viewer link)."""
        self.bridge.post(self.run_panel.on_log, str(text))

    def _disk_warning(self, text):
        """`foam_env.start_disk_warning`'s sink, called on its thread: one
        Run-log line and one status-line warning, nothing modal."""
        self._log_threadsafe(f'  [blastfoam] {text}')
        self.bridge.post(self.notify, text, 'warn')

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
        # the notification's tray icon never outlives the window
        dialogs.clear_tray()
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
    # GUI-2 (plan §3): the drawn icon on the application, and an
    # explicit AppUserModelID so the Windows taskbar shows it (grouped
    # as blastlab, not as Python)
    app.setWindowIcon(theme.app_icon())
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.shell32.\
                SetCurrentProcessExplicitAppUserModelID('blastlab')
        except Exception:
            pass
    win = MainWindow(case_file=case_file)
    win.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
