"""Characterisation: what the Qt Chain panel launches, and what it refuses.

Batch 2026-09-29-gui-chain, T0 (GUI-9). Recorded at base `4b28007`,
before any GUI-9 change, and committed alone: GUI-9 moves the stage forms
to the Setup layout, the wiring into `ui/chain_route.py` and the stage
checkboxes into route buttons. None of that may change a single value a
chain hands to the solver. Golden: `char_golden/ui_chain_wiring.json`.

What it drives: a standalone `ui.chain_panel.ChainPanel` (offscreen),
built exactly as `test_ui_chain.main()` builds it - a recorder as
`on_run_chain`, a recording `error_sink`, `model_source` = a temp runs
folder + `CHAIN`. A fresh panel per scenario, so nothing leaks.

The route is set by ONE function, `drive_route()`, which is not edited
after T0: `panel.set_route(key)` when the panel has it, else the three
stage checkboxes. Nothing else here knows which API it is on.

Per scenario it records `run()`'s return value, the launched
`[(dim, case)]` as `dataclasses.asdict(case)` (floats as `repr`, the
model root replaced by `<MODEL>`, the runs folder by `<RUNS>`), the
error sink's calls, the log lines, and what is on disk under the runs
folder (must be nothing: the window creates the model folder, never the
panel).

Scenarios: the four routes (1,2,3) (1,3) (1,2) (2,3) on the default
forms and on one variant (stage 2 with a gauge and `trigger_gauge` 1,
stage 1 with radius 2 m); the refusals stage 2 `Lx = 'abc'`, stage 2
planar with a 3D stage, stage 2 `cy = 99`, native 1D -> blastFoam 2D
(route 1,2,3), native 1D -> blastFoam 3D (route 1,3), and the three
model-box refusals of `test_ui_chain` C2b.

The golden's (1,3) default entry is also checked against
`test_ui_chain` C6b's expectations, so the two pins cannot drift.

Run:  cd blastlab/tests && python test_ui_char_chain_wiring.py [--update]
"""
import dataclasses
import os
import shutil
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import char_common as cc                                     # noqa: E402

from blastlab.ui.testing import ensure_qapp, pump            # noqa: E402

GOLDEN = 'ui_chain_wiring.json'

ROUTES = ((1, 2, 3), (1, 3), (1, 2), (2, 3))

_ERRORS = []


def _hook(etype, value, tb):
    """An exception raised in a Qt slot would otherwise print and be
    lost; record it, and let the test fail on it."""
    import traceback
    _ERRORS.append(''.join(traceback.format_exception(etype, value, tb)))
    sys.__excepthook__(etype, value, tb)


def drive_route(panel, dims):
    """The one route setter: the route buttons when the panel has them
    (GUI-9), else the stage checkboxes (base)."""
    dims = tuple(int(d) for d in dims)
    if hasattr(panel, 'set_route'):
        panel.set_route(''.join(str(d) for d in dims))
    else:
        for d in (1, 2, 3):
            panel.use[d].setChecked(d in dims)
    pump(5)


class _Sink:
    def __init__(self):
        self.calls = []

    def __call__(self, title, lines):
        self.calls.append([str(title), [str(ln) for ln in lines]])


def _scrub(obj, model, runs):
    """Floats as repr, tuples as lists, the model root as <MODEL> and
    the runs folder as <RUNS> (model first: it starts with runs)."""
    if isinstance(obj, dict):
        return {str(k): _scrub(v, model, runs) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_scrub(v, model, runs) for v in obj]
    if isinstance(obj, bool) or obj is None or isinstance(obj, int):
        return obj
    if isinstance(obj, float):
        return repr(obj)
    if isinstance(obj, str):
        return obj.replace(model, '<MODEL>').replace(runs, '<RUNS>')
    return repr(obj)


def scenario(route, prepare=None, source=None):
    """Build a fresh panel, set the route, apply `prepare(panel)`, run,
    and return what happened (scrubbed)."""
    from blastlab.ui.chain_panel import ChainPanel
    runs = tempfile.mkdtemp(prefix='blastlab_chw_')
    model = os.path.join(runs, 'CHAIN')
    box = list(source) if source is not None else [runs, 'CHAIN']
    box = [runs if b == '<RUNS>' else
           (os.path.join(runs, 'no') if b == '<RUNS>\\no' else b)
           for b in box]
    launched, log, sink = [], [], _Sink()
    panel = ChainPanel(on_run_chain=lambda stages: launched.append(
        list(stages)), log_fn=log.append, error_sink=sink,
        model_source=lambda: tuple(box))
    try:
        panel.resize(1100, 760)
        panel.show()
        pump(20)
        drive_route(panel, route)
        if prepare is not None:
            prepare(panel)
            pump(10)
        ok = panel.run()
        pump(5)
        got = dict(
            returned=ok,
            launched=[[[d, dataclasses.asdict(c)] for d, c in st]
                      for st in launched],
            sink=sink.calls,
            log=list(log),
            on_disk=sorted(os.listdir(runs)))
        return _scrub(got, model, runs)
    finally:
        panel.hide()
        panel.deleteLater()
        pump(5)
        shutil.rmtree(runs, ignore_errors=True)


# ── the variants ─────────────────────────────────────────────────────────
def variant(panel):
    """Stage 2 with a gauge and the trigger on it; stage 1 radius 2 m."""
    f2 = panel.forms[2]
    f2.points['gauges'].set([(1.5, 1.0)])
    f2.v['trigger_gauge'].set('1')
    panel.forms[1].v['radius_m'].set('2')


def bad_lx(panel):
    panel.forms[2].v['Lx'].set('abc')


def planar(panel):
    panel.forms[2].v['geometry'].set('planar')
    pump(10)


def bad_cy(panel):
    panel.forms[2].v['cy'].set('99')


def native_into(dim):
    def prep(panel):
        panel.set_stage_solver(1, 'native')
        panel.set_stage_solver(dim, 'blastfoam')
    return prep


def plan():
    """[(key, route, prepare, source)] in golden order."""
    out = []
    for r in ROUTES:
        key = ''.join(str(d) for d in r)
        out.append((f'route/{key}/default', r, None, None))
        out.append((f'route/{key}/variant', r, variant, None))
    out += [
        ('refuse/stage2_Lx_abc', (1, 2, 3), bad_lx, None),
        ('refuse/stage2_planar_with_3d', (1, 2, 3), planar, None),
        ('refuse/stage2_cy_99', (1, 2, 3), bad_cy, None),
        ('refuse/native1d_foam2d', (1, 2, 3), native_into(2), None),
        ('refuse/native1d_foam3d_route13', (1, 3), native_into(3), None),
        ('refuse/model_runs_empty', (1, 2, 3), None, ['', 'CHAIN']),
        ('refuse/model_name_empty', (1, 2, 3), None, ['<RUNS>', '']),
        ('refuse/model_runs_missing', (1, 2, 3), None,
         ['<RUNS>\\no', 'CHAIN']),
    ]
    return out


_GOT = {}


def test_chain_wiring():
    ensure_qapp()
    for key, route, prep, source in plan():
        _GOT[key] = scenario(route, prep, source)
    assert not _ERRORS, 'uncaught exception(s):\n' + '\n'.join(_ERRORS)
    cc.check_json(GOLDEN, _GOT)


def test_route13_is_c6b():
    """The golden's (1,3) default entry says what `test_ui_chain` C6b
    asserts: two stages in order, 1D writes <MODEL>\\handoff_1d_to_3d.txt,
    the 3D stage reads it as a 1D profile, both on a pinned write
    schedule, nothing refused, nothing on disk."""
    got = (_GOT or cc.load_json(GOLDEN))['route/13/default']
    p13 = '<MODEL>\\handoff_1d_to_3d.txt'
    assert got['returned'] is True and got['sink'] == [], got['sink']
    assert len(got['launched']) == 1, len(got['launched'])
    pair = dict((d, c) for d, c in got['launched'][0])
    assert [d for d, _c in got['launched'][0]] == [1, 3]
    assert pair[1]['profile_file'] == p13, pair[1]['profile_file']
    assert pair[3]['profile_file_in'] == p13, pair[3]['profile_file_in']
    assert pair[3]['init_mode'] == 'profile1d', pair[3]['init_mode']
    assert pair[1]['adaptive_write'] is False \
        and pair[3]['adaptive_write'] is False
    assert got['on_disk'] == [], got['on_disk']


def main():
    sys.excepthook = _hook
    return cc.run_main('CHAR UI CHAIN WIRING',
                       [test_chain_wiring, test_route13_is_c6b])


if __name__ == '__main__':
    sys.exit(main())
