"""Remap-chain helpers shared by the GUI front-ends (1D -> 2D -> 3D as
one workflow). Toolkit-free; moved out of the Tk chain panel."""

from .case import validate_case


def stage_errors(stages, cases):
    """Per-stage validation errors for an auto-wired chain, as
    "Stage <n> (<n>D): <message>" lines (empty = ready to run).

    Must run AFTER the profile hand-offs are wired: the wiring is what
    makes a later stage profile-initialized, so validating the raw forms
    would miss exactly the combination that used to reach the backend
    and die there with a traceback."""
    errors = []
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
