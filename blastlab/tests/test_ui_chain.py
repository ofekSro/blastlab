"""The Qt Chain tab: refusals, wiring, and what reaches the disk.

The order inside `ChainPanel.run()` is load-bearing, and most of these
checks exist because getting it wrong is silent:

- the model folder must NOT appear when the run is refused, and the
  panel itself never creates it - the window does, only once the run is
  certain to start (OUT-1; before OUT-1 this was the workspace box)
- `adaptive_write` must be False on every stage, or the arrival-pinned
  hand-off lands on a different write from one run to the next
- a bad field must name ITS stage and bring that form to the front, or
  "'Lx' is not a number" gives no clue which of the three it came from
- `stage_errors` runs AFTER the profile wiring, so it judges what will
  actually run

Nothing here opens a modal: the error sink is injected and the checks
read its recorded lines plus `run()`'s return value.

Run:  cd blastlab/tests && python test_ui_chain.py
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
sys.path.insert(0, HERE)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('MPLBACKEND', 'Agg')
os.environ.setdefault('BLASTLAB_SETTINGS',
                      os.path.join(tempfile.mkdtemp(prefix='blastlab_ch_'),
                                   'settings.json'))

from blastlab.core import mode as mode_mod                     # noqa: E402
from blastlab.ui.testing import ensure_qapp, pump              # noqa: E402

FAIL = []
RAN = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    RAN.append(name)
    if not ok:
        FAIL.append(name)


class Recorder:
    """Stands in for the modal: records instead of blocking."""

    def __init__(self):
        self.calls = []

    def __call__(self, title, lines):
        self.calls.append((title, list(lines)))

    @property
    def lines(self):
        return self.calls[-1][1] if self.calls else []

    def clear(self):
        self.calls = []


def real_chain_run():
    """The window's path: Chain tab -> _run_chain -> _model_target ->
    the controller. Lands <MODEL>\\1d, 2d, the hand-off at the root and
    the root manifest.json."""
    import time
    from blastlab.models.case import Case1D, Case2D
    from blastlab.ui import dialogs
    from blastlab.ui.app import MainWindow
    from blastlab.ui.testing import use_model
    real = (dialogs.show_error, dialogs.ask_yes_no)
    shown = []
    dialogs.show_error = lambda t, m, p=None: shown.append((t, m))
    dialogs.ask_yes_no = lambda t, m, p=None: True
    try:
        win = MainWindow()
        win.set_solver('native')
        folder = use_model(win, 'CHAIN_RUN')
        win.show()
        pump(100)
        ch = win.chain
        ch.set_route('12')          # GUI-9: was use[3].setChecked(False)
        ch.set_stage_case(1, Case1D(radius_m=1.0, charge_kg=0.5,
                                    cell_size_m=0.01, n_snapshots=1,
                                    t_end=3e-4, gauge_radii=[0.5]))
        ch.set_stage_case(2, Case2D(Lx=0.6, Ly=1.2, cell_size_m=0.03,
                                    charge=0.5, center=(0.0, 0.6),
                                    n_snapshots=1, t_end=2e-4,
                                    record_frames=0,
                                    gauges=[(0.25, 0.6)],
                                    bcs=dict(x_lo='reflect',
                                             x_hi='transmit',
                                             y_lo='reflect',
                                             y_hi='transmit')))
        pump(50)
        ok = ch.run()
        check('the chain started', ok is True,
              f'{ch.status.text()} | {shown}')
        t0 = time.time()
        while win.ctrl.running and time.time() - t0 < 300:
            pump(50)
        check('and finished without an error dialog',
              not win.ctrl.running and shown == [], str(shown))
        got = sorted(os.listdir(folder)) if os.path.isdir(folder) else []
        check('the model root holds 1d\\, 2d\\, the hand-off and the '
              'root manifest',
              got == ['.blastlab-model', '1d', '2d',
                      'handoff_1d_to_2d.txt', 'manifest.json'], str(got))
        for d in ('1d', '2d'):
            sub = os.path.join(folder, d)
            names = sorted(os.listdir(sub)) if os.path.isdir(sub) else []
            check(f'{d}\\ is a complete stage folder',
                  {'MODEL.json', 'run.log', 'manifest.json',
                   'report.html'} <= set(names), str(names))
        with open(os.path.join(folder, 'manifest.json'),
                  encoding='utf-8') as f:
            root = json.load(f)
        check('the root manifest names the chain, both stages and the '
              'hand-off',
              root.get('chain') == [1, 2]
              and sorted(root.get('stages', {})) == ['1d', '2d']
              and root.get('handoffs') == ['handoff_1d_to_2d.txt'],
              str({k: root.get(k) for k in ('chain', 'handoffs')}))
        with open(os.path.join(folder, '2d', 'MODEL.json'),
                  encoding='utf-8') as f:
            two = json.load(f)
        with open(os.path.join(folder, '1d', 'MODEL.json'),
                  encoding='utf-8') as f:
            one = json.load(f)
        check('the 2D stage reads the hand-off, folder-relative',
              two.get('profile_file_in') == '../handoff_1d_to_2d.txt'
              and two.get('init_mode') == 'profile1d', str(
                  {k: two.get(k) for k in ('profile_file_in',
                                           'init_mode')}))
        check('the 1D stage wrote it',
              one.get('profile_file') == '../handoff_1d_to_2d.txt',
              str(one.get('profile_file')))
        check('both stages ran on a pinned write schedule (N2-13)',
              one.get('adaptive_write') is False
              and two.get('adaptive_write') is False)
        names = [lbl for lbl, _d, _r in win._results]
        check('the results are named after the model',
              names == ['CHAIN_RUN - 1D', 'CHAIN_RUN - 2D'], str(names))
        # GUI-9 T5 (plan §7): the chain is ONE Results entry with a stage
        # per dimension, labelled as the per-stage entries were
        ents = win.results.entries()
        check('the Results list holds one chain entry, stages [1, 2] '
              'labelled CHAIN_RUN - 1D, CHAIN_RUN - 2D',
              len(ents) == 1 and ents[0].kind == 'chain'
              and [s.dim for s in ents[0].stages] == [1, 2]
              and [s.label for s in ents[0].stages]
              == ['CHAIN_RUN - 1D', 'CHAIN_RUN - 2D'],
              str([(e.label, e.kind, [(s.label, s.dim) for s in
                                      (e.stages or [])]) for e in ents]))
        win.close()
        pump(50)
    finally:
        dialogs.show_error, dialogs.ask_yes_no = real


def real_chain_run_13():
    """GUI-8 (plan sec. 8.3): a tiny native 1D -> 3D chain through the
    window path. The 3D stage must start FROM THE PROFILE - its first
    recorded frame at t0 is non-ambient around the burst point."""
    import time
    from blastlab.models.case import Case1D, Case3D
    from blastlab.ui import dialogs
    from blastlab.ui.app import MainWindow
    from blastlab.ui.testing import use_model
    real = (dialogs.show_error, dialogs.ask_yes_no)
    shown = []
    dialogs.show_error = lambda t, m, p=None: shown.append((t, m))
    dialogs.ask_yes_no = lambda t, m, p=None: True
    try:
        win = MainWindow()
        win.set_solver('native')
        folder = use_model(win, 'CHAIN13_RUN')
        win.show()
        pump(100)
        ch = win.chain
        ch.set_route('13')          # GUI-9: was use[2].setChecked(False)
        # hand off at t = 0.05 ms: the shock sits at r ~ 0.24 m then
        # (measured), inside the 0.6 m box - a later hand-off leaves
        # only the under-pressured core inside the 3D domain
        ch.set_stage_case(1, Case1D(radius_m=1.0, charge_kg=0.5,
                                    cell_size_m=0.01, n_snapshots=1,
                                    t_end=5e-5, gauge_radii=[0.5]))
        ch.set_stage_case(3, Case3D(Lx=0.6, Ly=0.6, Lz=0.6,
                                    cell_size_m=0.05,
                                    center=(0.3, 0.3, 0.3),
                                    n_snapshots=1, t_end=2e-4,
                                    record_frames=8,
                                    gauges=[(0.45, 0.3, 0.3)]))
        pump(50)
        ok = ch.run()
        check('the 1 -> 3 chain started', ok is True,
              f'{ch.status.text()} | {shown}')
        t0 = time.time()
        while win.ctrl.running and time.time() - t0 < 300:
            pump(50)
        check('and finished without an error dialog',
              not win.ctrl.running and shown == [], str(shown))
        got = sorted(os.listdir(folder)) if os.path.isdir(folder) else []
        check('the model root holds 1d\\, 3d\\, the hand-off and the '
              'root manifest',
              got == ['.blastlab-model', '1d', '3d',
                      'handoff_1d_to_3d.txt', 'manifest.json'], str(got))
        with open(os.path.join(folder, 'manifest.json'),
                  encoding='utf-8') as f:
            root = json.load(f)
        check('the root manifest names the chain and the hand-off',
              root.get('chain') == [1, 3]
              and sorted(root.get('stages', {})) == ['1d', '3d']
              and root.get('handoffs') == ['handoff_1d_to_3d.txt'],
              str({k: root.get(k) for k in ('chain', 'handoffs')}))
        with open(os.path.join(folder, '3d', 'MODEL.json'),
                  encoding='utf-8') as f:
            three = json.load(f)
        check('the 3D stage reads the hand-off, folder-relative',
              three.get('profile_file_in') == '../handoff_1d_to_3d.txt'
              and three.get('init_mode') == 'profile1d', str(
                  {k: three.get(k) for k in ('profile_file_in',
                                             'init_mode')}))
        res3 = next((r for lbl, d, r in win._results if d == 3), None)
        fr = (res3.meta.get('frames') or {}) if res3 is not None else {}
        t_first = float(fr['times'][0]) if len(fr.get('times', [])) else -1
        p_first = fr['pressures'][0] if fr.get('pressures') else None
        # the 3D clock continues from the profile's hand-off time, so
        # this stage's t0 is the 1D t_end (5e-5 s)
        check('the 3D stage started from the profile: the first frame '
              'at t0 is non-ambient around the burst point',
              res3 is not None and 0 <= t_first <= 6e-5
              and p_first is not None
              and float(p_first.max()) > 101325 + 1e4,
              f't0={t_first} pmax='
              f'{None if p_first is None else float(p_first.max()):}')
        win.close()
        pump(50)
    finally:
        dialogs.show_error, dialogs.ask_yes_no = real


def c13_routes(panel, launched, errs, ws, ws_root):
    """GUI-9 T1 (plan §10 "the four routes wire the right hand-offs",
    one fast test per route): the route buttons, what each route hands
    on, and the routes that do not exist."""
    from PySide6.QtWidgets import QPushButton
    from blastlab.services.chain import stage_errors
    from blastlab.ui import chain_route

    print('\nC13: the four routes (GUI-9)')
    for key, _label, dims in chain_route.ROUTES:
        panel.set_route(key)
        pump(10)
        check(f'{key}: checked() is the route\'s stages',
              panel.checked() == list(dims) and panel.route() == key,
              f'{panel.checked()}')
        # each form's own values, before the wiring touches a copy
        own = {d: panel.forms[d].get_case() for d in dims}
        errs.clear()
        launched.clear()
        ok = panel.run()
        check(f'{key}: run() starts it, nothing refused',
              ok is True and not errs.calls, str(errs.lines)[:160])
        got = launched[0] if launched else []
        check(f'{key}: the stages are handed on in route order',
              [d for d, _c in got] == list(dims),
              str([d for d, _c in got]))
        cases = dict(got)
        if [d for d, _c in got] != list(dims):
            continue
        for a, b in zip(dims, dims[1:]):
            path = os.path.join(ws, chain_route.handoff_name(a, b))
            want = 'profile1d' if a == 1 else 'profile2d'
            check(f'{key}: {a}D -> {b}D through {os.path.basename(path)}',
                  cases[a].profile_file == path
                  and cases[b].profile_file_in == path
                  and cases[b].init_mode == want,
                  f'{cases[a].profile_file} / {cases[b].profile_file_in} '
                  f'/ {cases[b].init_mode}')
        first, last = dims[0], dims[-1]
        check(f'{key}: the first stage starts from its own form, the last '
              f'writes its own profile',
              getattr(cases[first], 'init_mode', None)
              == getattr(own[first], 'init_mode', None)
              and getattr(cases[last], 'profile_file', None)
              == getattr(own[last], 'profile_file', None),
              f'{getattr(cases[first], "init_mode", None)} / '
              f'{getattr(cases[last], "profile_file", None)}')
        check(f'{key}: every stage on a pinned write schedule (N2-13)',
              all(c.adaptive_write is False for c in cases.values()))
        check(f'{key}: stage_errors is empty for the wired route',
              stage_errors(list(dims), cases) == [],
              str(stage_errors(list(dims), cases))[:160])
        check(f'{key}: nothing on disk', os.listdir(ws_root) == [],
              str(os.listdir(ws_root)))

    panel.set_route('13')
    btns = [b for b in panel.findChildren(QPushButton)
            if b.objectName() == 'chainroute']
    for bad in ('', '1', '32'):
        try:
            panel.set_route(bad)
            raised = False
        except ValueError:
            raised = True
        check(f'set_route({bad!r}) raises ValueError and changes nothing',
              raised and panel.route() == '13'
              and [b.isChecked() for b in btns]
              == [k == '13' for k, _l, _d in chain_route.ROUTES],
              f'{raised} {panel.route()}')
    check('exactly four route buttons, exactly one checked',
          len(btns) == 4 and sum(b.isChecked() for b in btns) == 1
          and [b.text() for b in btns]
          == [label_ for _k, label_, _d in chain_route.ROUTES],
          ascii([b.text() for b in btns]))
    panel.set_route('123')


def main():
    ensure_qapp()
    from blastlab.ui.chain_panel import HINT, ChainPanel

    launched = []
    errs = Recorder()
    log = []
    ws_root = tempfile.mkdtemp(prefix='blastlab_ws_')
    source = [ws_root, 'CHAIN']         # the Run tab's two boxes
    panel = ChainPanel(on_run_chain=lambda stages: launched.append(
        list(stages)), log_fn=log.append, error_sink=errs,
        model_source=lambda: tuple(source))
    panel.resize(1100, 760)
    panel.show()
    pump(60)
    ws = os.path.join(ws_root, 'CHAIN')           # the model folder
    p1 = os.path.join(ws, 'handoff_1d_to_2d.txt')
    p2 = os.path.join(ws, 'handoff_2d_to_3d.npz')
    p13 = os.path.join(ws, 'handoff_1d_to_3d.txt')

    print('\nC1: the panel')
    check('OUT-1: no workspace box - the Run tab\'s model folder is it',
          not hasattr(panel, 'ws_box') and 'model folder' in HINT
          and 'handoff_1d_to_2d.txt' in HINT, HINT[:80])
    # GUI-9 (plan §9 layout pin): the three checkboxes became routes
    check('the route starts on 1D -> 2D -> 3D, all three stages',
          panel.route() == '123' and panel.checked() == [1, 2, 3],
          f'{panel.route()} {panel.checked()}')
    check('and each has its own form',
          sorted(panel.forms) == [1, 2, 3]
          and panel.forms[2].dim == 2)
    check('stage 1 is on top', panel.stage() == 1)
    # GUI-9 (plan §9 layout pin): the stage switcher became the pipeline's
    # stage cards - a click on card 3 / card 1 selected
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    QTest.mouseClick(panel.cards[3], Qt.LeftButton)
    pump(20)
    check('the switcher moves between them', panel.stage() == 3)
    panel.focus_stage(1)
    pump(20)
    check('and focus_stage moves it back', panel.stage() == 1
          and panel.cards[1].selected()
          and not panel.cards[3].selected())

    # C2 (the empty refusal) is gone with the checkboxes (GUI-9, plan §9
    # layout pin): no route can be empty; C13 pins the invalid routes.
    # 'The model folder was NOT created by a refused run' is asserted on
    # the C3 refusal below.

    print('\nC2b: OUT-1 - the model folder is refused before anything')
    panel.set_route('123')
    for runs, model, want in (('', 'CHAIN', 'Runs folder is empty'),
                              (ws_root, '', 'Model name: '),
                              (os.path.join(ws_root, 'no'), 'CHAIN',
                               'Runs folder does not exist')):
        source[:] = [runs, model]
        errs.clear()
        launched.clear()
        check(f'{want.strip()} -> refused, naming the box',
              panel.run() is False and errs.lines
              and errs.lines[0].startswith(want)
              and errs.lines[-1] == 'The Runs folder and Model boxes are '
                                    'on the Run tab.'
              and not launched, str(errs.lines))
    source[:] = [ws_root, 'CHAIN']
    check('and still nothing on disk', os.listdir(ws_root) == [],
          str(os.listdir(ws_root)))

    print('\nC3: a bad field names its own stage and shows it')
    panel.set_route('123')
    panel.focus_stage(1)
    panel.forms[2].v['Lx'].set('abc')
    pump(20)
    errs.clear()
    ok = panel.run()
    check('refused', ok is False)
    check('every line is prefixed "Stage 2 (2D)"',
          errs.lines and all(ln.startswith('Stage 2 (2D): ')
                             for ln in errs.lines), str(errs.lines))
    check('and stage 2 is now the one on screen', panel.stage() == 2)
    check('the log carries it as well',
          any('Stage 2 (2D)' in s for s in log), str(log[-2:]))
    check('still no model folder', not os.path.exists(ws))
    check('the model folder was NOT created by a refused run',
          not os.path.exists(ws))
    panel.forms[2].v['Lx'].set('4')
    pump(20)

    print('\nC4: a 2D stage feeding 3D must be axisymmetric')
    panel.forms[2].v['geometry'].set('planar')
    pump(30)
    errs.clear()
    check('planar stage 2 with a 3D stage -> refused',
          panel.run() is False
          and errs.lines == ['Stage 2 (2D): must be axisymmetric to '
                             'feed the 3D stage.'], str(errs.lines))
    check('and it jumped to stage 2', panel.stage() == 2)
    panel.forms[2].v['geometry'].set('axisymmetric')
    pump(30)

    print('\nC5: a chain that runs')
    errs.clear()
    launched.clear()
    ok = panel.run()
    check('accepted', ok is True and not errs.calls,
          str(errs.lines) + ' | ' + str(panel.status.text()))
    check('and handed on as three stages in order',
          len(launched) == 1
          and [d for d, _c in launched[0]] == [1, 2, 3],
          str([[d for d, _c in st] for st in launched]))
    stages = dict(launched[0])
    check('1D writes the profile the 2D stage reads',
          stages[1].profile_file == p1
          and stages[2].profile_file_in == p1
          and stages[2].init_mode == 'profile1d')
    check('2D writes the profile the 3D stage reads',
          stages[2].profile_file == p2
          and stages[3].profile_file_in == p2
          and stages[3].init_mode == 'profile2d')
    check('N2-13: every stage runs on a PINNED write schedule',
          all(c.adaptive_write is False for c in stages.values()),
          str([c.adaptive_write for c in stages.values()]))
    check('the hand-offs sit at the model root (plan sec. 2.2)',
          os.path.dirname(p1) == ws and os.path.dirname(p2) == ws)
    check('the panel wrote nothing: the window creates the folder, and '
          'each stage its own MODEL.json', not os.path.exists(ws))

    print('\nC6: a shorter chain wires only what it has')
    panel.set_route('12')
    launched.clear()
    errs.clear()
    check('1 -> 2 accepted', panel.run() is True, str(errs.lines))
    two = dict(launched[0])
    check('the 2D stage no longer writes a profile for a 3D stage',
          two[2].profile_file != p2 and two[2].profile_file_in == p1,
          f'{two[2].profile_file} / {two[2].profile_file_in}')
    panel.set_route('23')
    launched.clear()
    errs.clear()
    check('2 -> 3 accepted', panel.run() is True, str(errs.lines))
    late = dict(launched[0])
    check('a 2D stage with no 1D before it starts from its own case',
          late[2].init_mode != 'profile1d'
          and late[3].profile_file_in == p2,
          f'{late[2].init_mode} / {late[3].profile_file_in}')
    panel.set_route('123')

    print('\nC6b: the 1D -> 3D route (GUI-8, plan sec. 8.3)')
    panel.set_route('13')
    pump(20)
    launched.clear()
    errs.clear()
    check('1 -> 3 accepted', panel.run() is True and not errs.calls,
          str(errs.lines) + ' | ' + str(panel.status.text()))
    check('and handed on as two stages in order',
          len(launched) == 1
          and [d for d, _c in launched[0]] == [1, 3],
          str([[d for d, _c in st] for st in launched]))
    pair = dict(launched[0])
    check('1D writes the profile the 3D stage reads, at the model root',
          pair[1].profile_file == p13
          and pair[3].profile_file_in == p13
          and pair[3].init_mode == 'profile1d'
          and os.path.dirname(p13) == ws,
          f'{pair[1].profile_file} / {pair[3].profile_file_in}')
    check('N2-13: the new route runs on a PINNED write schedule too',
          pair[1].adaptive_write is False
          and pair[3].adaptive_write is False)
    check('the panel wrote nothing to disk', not os.path.exists(ws))
    from blastlab.services.chain import stage_errors
    check('stage_errors is empty for the wired pair',
          stage_errors([1, 3], pair) == [],
          str(stage_errors([1, 3], pair)))

    # the native -> blastFoam refusal covers the (1, 3) edge unchanged
    panel.set_stage_solver(1, 'native')
    panel.set_stage_solver(3, 'blastfoam')
    pump(20)
    check('native 1D feeding blastFoam 3D disables Run chain (N5-4)',
          bool(panel._compat[3].text())
          and not panel.run_btn.isEnabled(),
          str({d: panel._compat[d].text()[:30] for d in (1, 2, 3)}))
    errs.clear()
    launched.clear()
    from blastlab.services.chain import HANDOFF_MSG
    check('and run() refuses it with the hand-off message',
          panel.run() is False and not launched
          and any(HANDOFF_MSG in ln for ln in errs.lines),
          str(errs.lines)[:120])
    panel.set_stage_solver(1, mode_mod.DEFAULT)
    panel.set_stage_solver(3, mode_mod.DEFAULT)
    panel.set_route('123')
    pump(20)

    print('\nC7: the per-stage solver')
    # the sidebar's mode is the preset, whatever it happens to be
    other = next(m for m in mode_mod.MODES if m != mode_mod.DEFAULT)
    panel._mode.set(mode_mod.DEFAULT)
    pump(40)
    check('all three start on the app-level solver',
          set(panel.stage_solver.values()) == {mode_mod.DEFAULT},
          str(panel.stage_solver))
    panel.set_stage_solver(2, other)
    pump(30)
    check('one stage can differ from the others',
          panel.stage_solver == {1: mode_mod.DEFAULT, 2: other,
                                 3: mode_mod.DEFAULT},
          str(panel.stage_solver))
    check('and only its form followed',
          panel.forms[2]._mode == other
          and panel.forms[1]._mode == mode_mod.DEFAULT)
    seen = []
    panel._stage_seg_solver[2].changed.connect(seen.append)
    panel.set_stage_solver(2, mode_mod.DEFAULT)
    pump(20)
    check('setting it programmatically fires no segment command',
          seen == [], str(seen))
    panel.set_stage_solver(2, other)
    pump(20)
    panel._mode.set(other)
    pump(40)
    check('a global change presets all three again',
          set(panel.stage_solver.values()) == {other},
          str(panel.stage_solver))
    check('and every form followed',
          all(panel.forms[d]._mode == other for d in (1, 2, 3)))
    panel._mode.set(mode_mod.DEFAULT)
    pump(40)
    check('and back', set(panel.stage_solver.values())
          == {mode_mod.DEFAULT}, str(panel.stage_solver))

    print('\nC8: the dialog is strictly last (P2-8)')

    def exploding(title, lines):
        raise RuntimeError('a modal would have blocked here')
    panel.error_sink = exploding
    panel.status.setText('')
    n_log = len(log)
    # GUI-9 (plan §9): the refusal that exercises it is the empty Model
    # box now - no route can be empty; the four assertions are unchanged
    source[:] = [ws_root, '']
    check('a refusal still returns False when the dialog blows up',
          panel.run() is False)
    check('and the reason reached the status line first',
          'Model name' in panel.status.text(),
          panel.status.text())
    check('and the log', any('Model name' in s
                             for s in log[n_log:]), str(log[n_log:]))
    check('the dialog failure is noted, not swallowed silently',
          any('dialog failed' in s for s in log[n_log:]),
          str(log[n_log:]))
    panel.error_sink = errs
    source[:] = [ws_root, 'CHAIN']

    print('\nC9: Run chain follows the Run button')
    panel.set_running(True)
    check('a live run disables it', not panel.run_btn.isEnabled())
    panel.set_running(False)
    check('and it comes back after', panel.run_btn.isEnabled())

    print('\nC10: native -> blastFoam is refused where it is chosen')
    # N5-4. The native solvers run eos='idealGas'; blastFoam runs JWL
    # products and back-derives internal energy from the pressure it is
    # handed (guide 5.9), so the hand-off inflates the product cells by
    # (gamma_air - 1) / omega = 33 %. stage_errors refuses it, but a
    # refusal that only lands on Run chain is one the user meets having
    # already filled three forms - hence the live per-stage message.
    panel.set_route('123')
    for d in (1, 2, 3):
        panel.set_stage_solver(d, 'blastfoam')
    panel.status.setText('')
    pump(0.05)
    check('a foam -> foam chain says nothing',
          not any(panel._compat[d].text() for d in (1, 2, 3))
          and panel.run_btn.isEnabled(),
          str({d: panel._compat[d].text()[:30] for d in (1, 2, 3)}))

    panel.set_stage_solver(1, 'native')
    pump(0.05)
    check('the message lands on the stage being FED, not the source',
          bool(panel._compat[2].text()) and not panel._compat[1].text(),
          str({d: panel._compat[d].text()[:30] for d in (1, 2, 3)}))
    check('it says why and what to do',
          'JWL' in panel._compat[2].text()
          and '33' in panel._compat[2].text(),
          panel._compat[2].text()[:120])
    check('Run chain is disabled while it stands',
          not panel.run_btn.isEnabled())
    check('and the status line carries it too',
          panel.status.text().startswith('Stage 2:'),
          panel.status.text()[:60])
    # run() must refuse on its own account - the greyed button is the
    # visible half of the guard, never the whole of it
    n_log = len(log)
    check('run() refuses it even with the button bypassed',
          panel.run() is False
          and any('Stage 2 (2D)' in s for s in log[n_log:]),
          str(log[n_log:][:2]))

    # switching off the stage in between must re-evaluate 1 -> 3
    panel.set_route('13')
    pump(0.05)
    check('the route 1D -> 3D moves it to 1 -> 3',
          bool(panel._compat[3].text()) and not panel._compat[2].text(),
          str({d: panel._compat[d].text()[:30] for d in (1, 2, 3)}))
    panel.set_route('123')

    panel.set_stage_solver(1, 'blastfoam')
    pump(0.05)
    check('and it all clears when the source goes back to blastFoam',
          not any(panel._compat[d].text() for d in (1, 2, 3))
          and not panel.status.text()
          and panel.run_btn.isEnabled(),
          str({d: panel._compat[d].text()[:30] for d in (1, 2, 3)}))

    # the two owners of the Run button must not fight (C9 + C10)
    panel.set_stage_solver(1, 'native')
    panel.set_running(True)
    panel.set_running(False)
    pump(0.05)
    check('a finished run does not re-arm a chain that is still refused',
          not panel.run_btn.isEnabled())
    panel.set_stage_solver(1, 'blastfoam')
    pump(0.05)
    check('and clearing the conflict re-arms it once',
          panel.run_btn.isEnabled())

    c13_routes(panel, launched, errs, ws, ws_root)

    shutil.rmtree(ws_root, ignore_errors=True)

    print('\nC11: OUT-1 - a tiny native 1D -> 2D chain, run in a window')
    real_chain_run()
    print('\nC12: GUI-8 - a tiny native 1D -> 3D chain, run in a window')
    real_chain_run_13()
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        sys.exit(1)
    print(f'UI CHAIN: PASS ({len(RAN)} checks)')


if __name__ == '__main__':
    main()
