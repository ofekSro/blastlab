"""The Qt Chain tab: refusals, wiring, and what reaches the disk.

The order inside `ChainPanel.run()` is load-bearing, and most of these
checks exist because getting it wrong is silent:

- the workspace directory must NOT appear when the run is refused
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


def main():
    ensure_qapp()
    from blastlab.ui.chain_panel import ChainPanel, default_workspace

    launched = []
    errs = Recorder()
    log = []
    panel = ChainPanel(on_run_chain=lambda stages, ws: launched.append(
        (list(stages), ws)), log_fn=log.append, error_sink=errs)
    panel.resize(1100, 760)
    panel.show()
    pump(60)
    ws_root = tempfile.mkdtemp(prefix='blastlab_ws_')
    ws = os.path.join(ws_root, 'chain')
    panel.ws_box.setText(ws)

    print('\nC1: the panel')
    check('a workspace is suggested under Documents, not the CWD',
          'blastlab' in default_workspace()
          and os.path.isabs(default_workspace()), default_workspace())
    check('all three stages start checked', panel.checked() == [1, 2, 3])
    check('and each has its own form',
          sorted(panel.forms) == [1, 2, 3]
          and panel.forms[2].dim == 2)
    check('stage 1 is on top', panel.stage() == 1)
    panel.stage_seg.changed.emit('Stage 3D')
    pump(20)
    check('the switcher moves between them', panel.stage() == 3)
    panel.focus_stage(1)
    pump(20)
    check('and focus_stage moves it back', panel.stage() == 1
          and panel.stage_seg.get() == 'Stage 1D')

    print('\nC2: the two refusals')
    for d in (1, 2, 3):
        panel.use[d].setChecked(False)
    errs.clear()
    check('no stages selected -> refused',
          panel.run() is False
          and errs.lines == ['No stages selected.'], str(errs.lines))
    check('and the status line says it too',
          'No stages selected' in panel.status.text())
    panel.use[1].setChecked(True)
    panel.use[3].setChecked(True)
    errs.clear()
    check('1 and 3 without 2 -> refused as non-consecutive',
          panel.run() is False
          and errs.lines == ['Stages must be consecutive.'],
          str(errs.lines))
    check('the workspace was NOT created by a refused run',
          not os.path.exists(ws))

    print('\nC3: a bad field names its own stage and shows it')
    for d in (1, 2, 3):
        panel.use[d].setChecked(True)
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
    check('still no workspace', not os.path.exists(ws))
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
          and [d for d, _c in launched[0][0]] == [1, 2, 3]
          and launched[0][1] == ws, str(launched[:1]))
    stages = dict(launched[0][0])
    p1 = os.path.join(ws, 'stage1_profile.txt')
    p2 = os.path.join(ws, 'stage2_profile.npz')
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
    check('the workspace exists now, and only now',
          os.path.isdir(ws))
    saved = sorted(f for f in os.listdir(ws) if f.endswith('.json'))
    check('one case JSON per stage, for reproducibility',
          saved == ['stage1_case.json', 'stage2_case.json',
                    'stage3_case.json'], str(saved))
    with open(os.path.join(ws, 'stage2_case.json'), encoding='utf-8') as f:
        on_disk = json.load(f)
    check('and the JSON carries the wiring, not the form defaults',
          on_disk.get('profile_file_in') == p1
          and on_disk.get('adaptive_write') is False,
          str({k: on_disk.get(k)
               for k in ('profile_file_in', 'adaptive_write')}))

    print('\nC6: a shorter chain wires only what it has')
    panel.use[3].setChecked(False)
    launched.clear()
    errs.clear()
    check('1 -> 2 accepted', panel.run() is True, str(errs.lines))
    two = dict(launched[0][0])
    check('the 2D stage no longer writes a profile for a 3D stage',
          two[2].profile_file != p2 and two[2].profile_file_in == p1,
          f'{two[2].profile_file} / {two[2].profile_file_in}')
    panel.use[3].setChecked(True)
    panel.use[1].setChecked(False)
    launched.clear()
    errs.clear()
    check('2 -> 3 accepted', panel.run() is True, str(errs.lines))
    late = dict(launched[0][0])
    check('a 2D stage with no 1D before it starts from its own case',
          late[2].init_mode != 'profile1d'
          and late[3].profile_file_in == p2,
          f'{late[2].init_mode} / {late[3].profile_file_in}')
    panel.use[1].setChecked(True)

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
    for d in (1, 2, 3):
        panel.use[d].setChecked(False)
    check('a refusal still returns False when the dialog blows up',
          panel.run() is False)
    check('and the reason reached the status line first',
          'No stages selected' in panel.status.text(),
          panel.status.text())
    check('and the log', any('No stages selected' in s
                             for s in log[n_log:]), str(log[n_log:]))
    check('the dialog failure is noted, not swallowed silently',
          any('dialog failed' in s for s in log[n_log:]),
          str(log[n_log:]))
    panel.error_sink = errs

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
    for d in (1, 2, 3):
        panel.use[d].setChecked(True)          # C8 left them all off
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
    panel.use[2].setChecked(False)
    pump(0.05)
    check('dropping the middle stage moves it to 1 -> 3',
          bool(panel._compat[3].text()) and not panel._compat[2].text(),
          str({d: panel._compat[d].text()[:30] for d in (1, 2, 3)}))
    panel.use[2].setChecked(True)

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

    shutil.rmtree(ws_root, ignore_errors=True)
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        sys.exit(1)
    print(f'UI CHAIN: PASS ({len(RAN)} checks)')


if __name__ == '__main__':
    main()
