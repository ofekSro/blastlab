"""Characterisation: the HD 1.3 assessment chain (Phase 0).

docs/ARCHITECTURE_REVIEW.md section 5, Phase 0. Runs `core.assessment.run`
on the starter case `output/cli_hd13.write_starter_case` writes and pins
the numbers the report leads with: confined peak pressure and stop
reason, unconfined expansion Mach number, SDOF ductility and response
regime, and the structural verdict - to rel = 1e-9. Phase 7 moves the
orchestration into `services/hd13.py`; these must not move.

The starter case has the sensitivity band OFF, so its verdict is None
and is pinned as None. Switching the band on costs 15 more solves - many
minutes at this case's 20 cohorts - which is too slow for a gate run on
every phase, so the verdict itself is not characterised here.

Run:  cd blastlab/tests && python test_char_hd13.py [--update]
"""
import sys

import char_common as cc
from blastlab.core import assessment                      # noqa: E402

REL = 1e-9


def headline(out):
    c = out['confined']
    u = out['unconfined']
    s = out['sdof']
    v = out['verdict']
    return dict(
        confined_p_max=c['p_max'],
        confined_stop_reason=c['stop_reason'],
        unconfined_mach_max=u['mach_max'],
        sdof_ductility=s.ductility,
        sdof_regime=s.regime,
        sdof_collapsed=s.collapsed,
        verdict=None if v is None else v['verdict'],
        verdict_low_ductility=None if v is None else v['low']['ductility'],
        verdict_high_ductility=None if v is None else v['high']['ductility'],
    )


def check(name, got):
    """Write the golden on --update; otherwise floats to REL, the rest
    exact."""
    if cc.UPDATE:
        cc.check_json(name, got)
        return
    want = cc.load_json(name)
    bad = cc.approx_equal(got, want, REL)
    assert bad is None, f'{name}: {bad} differs - now {cc.plain(got)}, ' \
                        f'golden {want}'


def test_starter_case():
    check('hd13_starter.json', headline(assessment.run(cc.hd13_starter_case())))


def main():
    return cc.run_main('CHAR HD13', [test_starter_case])


if __name__ == '__main__':
    sys.exit(main())
