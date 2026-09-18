"""Remap-chain helpers shared by the GUI front-ends (1D -> 2D -> 3D as
one workflow). Toolkit-free; moved out of the Tk chain panel."""

from .case import validate_case

#: N5-4. Fixing B0 (the missing lambda.<phase>) made blastFoam actually
#: READ the pressure a profile hands it - before that it blended the
#: products back to the unreacted Murnaghan reactants and reset them to
#: pRef, so the handed-over pressure was thrown away and nobody could
#: see what was wrong with it. What that exposed: the native solvers
#: normally run eos='idealGas', blastFoam always runs JWL products, and
#: the guide's 5.9 says blastFoam back-derives internal energy from the
#: pressure field. The ratio is exactly (gamma_air - 1) / omega, i.e.
#: 0.4 / 0.30 = 1.333 for TNT - measured at +33.3 % on the product
#: cells, which carry 16.8 % of the domain's internal energy.
HANDOFF_MSG = (
    'a blastFoam stage cannot be fed a profile produced by the native '
    'solver: the native hand-off carries an ideal-gas state and '
    'blastFoam re-derives internal energy from its pressure with the '
    'JWL products EOS, injecting ~33 % extra energy into the product '
    'cells. Run the stage before it on blastFoam, or run this stage on '
    'the native solver.')


def handoff_conflicts(stages, solvers):
    """[(dim, message)] for every stage that would be fed a profile its
    solver must not accept.

    `solvers` is {dim: 'native' | 'blastfoam'} - the panels pass their
    own per-stage switch state, which always parses, so this stays
    usable on every click without touching a half-typed form or the
    disk. `stages` is the ordered list of dims that are switched on.

    Only native -> blastFoam is a conflict. blastFoam -> native is fine:
    profiles.remap_* carry `e` straight through and never re-derive
    energy from pressure, so nothing is mispriced in that direction.
    """
    bad = []
    for prev, nxt in zip(stages, stages[1:]):
        if (solvers.get(prev) == 'native'
                and solvers.get(nxt) == 'blastfoam'):
            bad.append((nxt, HANDOFF_MSG))
    return bad


def stage_errors(stages, cases):
    """Per-stage validation errors for an auto-wired chain, as
    "Stage <n> (<n>D): <message>" lines (empty = ready to run).

    Must run AFTER the profile hand-offs are wired: the wiring is what
    makes a later stage profile-initialized, so validating the raw forms
    would miss exactly the combination that used to reach the backend
    and die there with a traceback."""
    errors = [f'Stage {d} ({d}D): {m}'
              for d, m in handoff_conflicts(
                  stages,
                  {d: getattr(cases[d], 'solver', 'native') for d in stages})]
    for d in stages:
        case = cases[d]
        # every stage but the first is fed by the one before it, so its
        # profile input cannot exist on disk yet
        # blastFoam stages fed by a profile are supported since T41 (N7):
        # the remapped state is written into 0/ as nonuniform fields.
        msgs = list(validate_case(
            case, pending_inputs=(d != stages[0])).errors)
        errors += [f'Stage {d} ({d}D): {m}' for m in msgs]
    return errors
