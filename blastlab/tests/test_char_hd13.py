"""Characterisation: the HD 1.3 assessment chain (Phase 0).

docs/ARCHITECTURE_REVIEW.md section 5, Phase 0. Runs `core.assessment.run`
on the starter case `output/cli_hd13.write_starter_case` writes and pins
the numbers the report leads with: confined peak pressure and stop
reason and unconfined expansion Mach number - to rel = 1e-9. Phase 7
moves the orchestration into `services/hd13.py`; these must not move.

The SDOF ductility, regime and structural-verdict pins were removed with
the structural response itself (TODO.md HD1-16 step 1, item 3).

Run:  cd blastlab/tests && python test_char_hd13.py [--update]
"""
import sys

import char_common as cc
from blastlab.core import assessment                      # noqa: E402

REL = 1e-9


def headline(out):
    """HD1-16 step 1, item 3: the sdof_* and verdict* pins are gone with
    the structural response; every other pin is unchanged."""
    c = out['confined']
    u = out['unconfined']
    return dict(
        confined_p_max=c['p_max'],
        confined_stop_reason=c['stop_reason'],
        unconfined_mach_max=u['mach_max'],
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
