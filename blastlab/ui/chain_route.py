"""GUI-9 (plan §8.1-§8.3, board Chain): the chain's routes, its wiring
and its live per-stage checks, as data. Toolkit-free on purpose, like
`setup_nodes`: a test can read it without a QApplication.

- `ROUTES` are the four routes the Chain screen offers instead of the old
  stage checkboxes; no other combination can be chosen (plan §8.1).
- `wire()` is the body of `ChainPanel.run()`'s wiring, moved here
  unchanged, so the launch and the live checks share ONE wiring and
  cannot say different things (batch risk 2). T0's golden
  (`tests/test_ui_char_chain_wiring.py`) pins what it hands on.
- `stage_checks()` is what the screen shows per stage while you type:
  parse, wire, then `validate_case(..., pending_inputs=...)` and the
  native -> blastFoam hand-off rule, exactly what `run()` will say.
  Nothing is written and no hand-off path of a later stage is checked.
- The hand-off texts are the board's sentences with the wired case's own
  numbers (formatted, never computed).

The hand-off itself is a lower-dimension field remapped onto the next
grid (Wurster & McDonald, Viper Blast Theory Manual (2025), sec. 3.4.1,
p. 6) - background for the texts only, not a source for any value.
"""

import copy
import os
from dataclasses import dataclass, field

from ..core import mode as mode_mod
from ..services import chain as chain_svc
from ..services import model_folder
from ..services.validation import validate_case
from . import setup_nodes

#: (key, label, dims) in board order (Chain.dc.html, `ROUTES`)
ROUTES = (('123', '1D → 2D → 3D', (1, 2, 3)),
          ('13', '1D → 3D', (1, 3)),
          ('12', '1D → 2D', (1, 2)),
          ('23', '2D → 3D', (2, 3)))
DEFAULT_ROUTE = '123'

#: the refusal `run()` has always given for a planar 2D stage feeding 3D
AXISYM_REFUSAL = 'Stage 2 (2D): must be axisymmetric to feed the 3D stage.'

#: board script `NONE_IN` / `LAST_OUT`
NONE_IN = 'Starts from the charge itself.'
LAST_OUT = ('Last stage: its results open in 03 Results, as one result '
            'with a tab per stage.')
NONE_FILE = 'none'


def route_dims(key):
    """The dims of route `key`; ValueError for anything else."""
    for k, _label, dims in ROUTES:
        if k == key:
            return dims
    raise ValueError(f'not a chain route: {key!r} (one of '
                     f'{", ".join(k for k, _l, _d in ROUTES)})')


def route_key(dims):
    """The key of the route with these dims; ValueError for a set that
    is not a route (a single stage, a gap the engine cannot wire)."""
    dims = tuple(int(d) for d in dims)
    for k, _label, ds in ROUTES:
        if ds == dims:
            return k
    raise ValueError(f'not a chain route: {dims!r}')


def route_label(key):
    for k, label, _dims in ROUTES:
        if k == key:
            return label
    raise ValueError(f'not a chain route: {key!r}')


def handoff_name(a, b):
    """The hand-off file between stage `a` and stage `b` at the model
    root. `model_folder.handoff_paths` stays the one source of the names
    (plan §8.2): handoff_1d_to_2d.txt, handoff_1d_to_3d.txt,
    handoff_2d_to_3d.npz."""
    target = model_folder.Target(runs_dir='', model='', folder='')
    path = model_folder.handoff_paths(target, [a, b])[(int(a), int(b))]
    return os.path.basename(path)


# ── the wiring (moved verbatim from ChainPanel.run) ──────────────────────
def wire(dims, cases, hand):
    """Wire the profile hand-offs of a chain into `cases` ({dim: case},
    one key per stage of the route, the caller's objects, mutated as
    `run()` always did). `hand` is `model_folder.handoff_paths(target,
    dims)`. Returns (cases, refusal): `refusal` is the one line `run()`
    refuses with, or None.

    A value may be None (a stage whose form does not parse, during the
    live checks): its key still says the stage is in the route, so the
    other stages are wired exactly as they will be at run time."""
    p1, p2 = hand.get((1, 2)), hand.get((2, 3))
    p13 = hand.get((1, 3))

    def put(d, **values):
        if cases[d] is not None:
            for k, v in values.items():
                setattr(cases[d], k, v)

    # N2-13: a chain must be reproducible, so every stage runs on a
    # PINNED write schedule. The adaptive-writeInterval controller
    # rewrites writeInterval mid-run from what the ingest has managed
    # to keep up with - wall clock - so with it on the set of write
    # times differs between identical runs, and the arrival-pinned
    # hand-off lands on a different write each time (measured: stage
    # ends spread +/-7% / 2.3x over five identical chains).
    for case in cases.values():
        if case is not None:
            case.adaptive_write = False

    # the hand-offs live at the model root (plan sec. 2.2); a single
    # stage has none and writes its own profile into the folder
    if 1 in cases and 2 in cases:
        put(1, profile_file=p1)
        put(2, init_mode='profile1d', profile_file_in=p1)
    if 2 in cases:
        if 3 in cases and cases[2] is not None \
                and cases[2].geometry != 'axisymmetric':
            return cases, AXISYM_REFUSAL
        if 3 in cases:
            put(2, profile_file=p2)
    if 3 in cases and 2 in cases:
        put(3, init_mode='profile2d', profile_file_in=p2)
    # GUI-8 (plan sec. 8.3): 1D -> 3D without a 2D stage. The engine
    # already supports it - solve_3d / the foam writer remap a 1D
    # profile (core/profiles.remap_profile_1d_to_3d); the 3D burst
    # height comes from the 3D form.
    if 1 in cases and 3 in cases and 2 not in cases:
        put(1, profile_file=p13)
        put(3, init_mode='profile1d', profile_file_in=p13)
    return cases, None


# ── the live checks (UX-16) ──────────────────────────────────────────────
def stage_prefix(d):
    """The prefix `services.chain.stage_errors` puts on a stage's line."""
    return f'Stage {int(d)} ({int(d)}D): '


@dataclass
class StageCheck:
    """What one stage's live check found. `case` is the wired case (None
    when the form does not parse); `parse` the form's own errors (a field
    that is not a number), `errors` the hand-off rule's and validation's,
    in `stage_errors` order; `report` the ValidationReport, or None."""
    case: object = None
    parse: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    report: object = None

    @property
    def n_errors(self):
        """Parse errors count as errors (the card and the pill)."""
        return len(self.parse) + len(self.errors)

    def rows(self):
        """(severity, message) in the Setup's order: errors -> warnings
        -> notes."""
        return ([('error', m) for m in self.parse + self.errors]
                + [('warn', m) for m in self.warnings]
                + [('note', m) for m in self.notes])


def stage_checks(dims, sources, hand):
    """{dim: StageCheck} for the route `dims`. `sources` maps each dim to
    a form (anything with `get_case()`, whose ValueError lines are parse
    errors) or a parsed case (copied, never mutated). Every parsed stage
    is wired with `wire()` exactly as `run()` wires it, then validated
    with `pending_inputs` for every stage but the first - the hand-offs
    of later stages do not exist yet and are not looked for. Nothing is
    written."""
    dims = [int(d) for d in dims]
    parsed, parse = {}, {}
    for d in dims:
        src = sources[d]
        parse[d] = []
        if hasattr(src, 'get_case'):
            try:
                parsed[d] = src.get_case()
            except ValueError as exc:
                parsed[d] = None
                parse[d] = [ln for ln in str(exc).splitlines()
                            if ln.strip()]
        else:
            parsed[d] = copy.deepcopy(src)
    cases, refusal = wire(dims, parsed, hand)
    # the hand-off rule reads each stage's solver; an unparsed form still
    # knows its own (CaseForm.mode), as the panel's switch does
    solvers = {d: (getattr(cases[d], 'solver', 'native')
                   if cases[d] is not None
                   else getattr(sources[d], 'mode', 'native'))
               for d in dims}
    conflicts = dict(chain_svc.handoff_conflicts(dims, solvers))
    out = {}
    for d in dims:
        chk = StageCheck(case=cases[d], parse=parse[d])
        if d in conflicts:
            chk.errors.append(conflicts[d])
        if refusal and refusal.startswith(stage_prefix(d)):
            chk.errors.append(refusal[len(stage_prefix(d)):])
        if cases[d] is not None:
            rep = validate_case(cases[d], pending_inputs=(d != dims[0]))
            chk.report = rep
            chk.errors += list(rep.errors)
            chk.warnings = list(rep.warnings)
            chk.notes = list(rep.notes)
        out[d] = chk
    return out


# ── what the screen says about a stage (board Chain) ─────────────────────
def stage_title(dim, geometry='axisymmetric'):
    """`1D spherical`, `2D axisymmetric` / `2D planar`, `3D`."""
    dim = int(dim)
    if dim == 1:
        return '1D spherical'
    if dim == 2:
        return f'2D {geometry}'
    return '3D'


def solver_label(m):
    return mode_mod.label(m)


def neighbours(dims, d):
    """(previous dim or 0, next dim or 0) of stage `d` in the route."""
    dims = [int(x) for x in dims]
    i = dims.index(int(d))
    return (dims[i - 1] if i > 0 else 0,
            dims[i + 1] if i < len(dims) - 1 else 0)


def _n1(v):
    """A value as the board writes it: one decimal at least."""
    v = float(v)
    s = f'{v:.1f}'
    return s if abs(float(s) - v) < 1e-9 else f'{v:g}'


def key_line(case, prev=0):
    """The card's mono key line, built from `setup_nodes.summaries` of
    the WIRED case (display only): 1D `<threat> · <domain>`; 2D / 3D
    `<domain> · from 1D` when fed, else `<domain> · <charge and
    material>`."""
    s = setup_nodes.summaries(case)
    if case.dim == 1:
        return f'{s["threat"]} · {s["domain"]}'
    if prev:
        return f'{s["domain"]} · from {int(prev)}D'
    return f'{s["domain"]} · {s["threat"].split(" · ")[0]}'


def stage_summary(solver, prev=0):
    """The 00 Stage row's summary: `<solver> · from 1D profile` /
    `<solver> · from the charge`."""
    how = f'from {int(prev)}D profile' if prev else 'from the charge'
    return f'{solver_label(solver)} · {how}'


def in_file(prev, d):
    return handoff_name(prev, d) if prev else NONE_FILE


def out_file(d, nxt):
    return handoff_name(d, nxt) if nxt else NONE_FILE


def in_text(case, prev):
    """HAND-OFF IN (plan §8.2): what the stage starts from. The burst
    height named is the wired case's own (2D: cy, 3D: cz)."""
    if not prev:
        return NONE_IN
    if case.dim == 2:
        return (f'Remapped onto the axis. The burst height, z '
                f'{_n1(case.center[1])} m, is taken from this stage’s '
                f'form.')
    if prev == 2:
        return ('Swept around the burst axis to start the 3D field. The '
                'burst height comes from the 2D profile.')
    return (f'The 1D profile is placed around the burst point. With no 2D '
            f'stage, the burst height, z {_n1(case.center[2])} m, is set '
            f'in this stage’s form.')


def out_text(case, nxt):
    """HAND-OFF OUT. The file is written when the stage ends
    (`solvers/jobs.py` `_solver`, after the solve) and holds the field
    of the instant the stage stopped: for 1D the outer boundary's
    arrival when Outer terminates the run (`solver1d`), else the end of
    the run; for 2D the trigger gauge's arrival when a trigger is set
    (the run stops there, or - `remap` - `write_trigger_remap` writes
    that instant over it), else the end of the run (decision D-row:
    the code, not the board, says when)."""
    if not nxt:
        return LAST_OUT
    then = ('The 2D stage starts from it.' if nxt == 2 else
            'The 3D stage places it around the burst point.'
            if case.dim == 1 else 'The 3D stage starts from it.')
    if case.dim == 1:
        if 'Outer' in setup_nodes.terminate_sides(case):
            return (f'The profile when the wave reaches Outer '
                    f'({_n1(case.radius_m)} m). {then}')
        return f'The profile at the end of the run. {then}'
    tg = getattr(case, 'trigger_gauge', None)
    if tg is not None:
        action = getattr(case, 'trigger_action', 'terminate')
        return (f'The field when the wave reaches G{tg} (trigger gauge, '
                f'{action}), or at the end of the run. {then}')
    ends = setup_nodes.terminate_sides(case)
    if ends:
        return (f'The field when the wave reaches {" or ".join(ends)}, or '
                f'at the end of the run. {then}')
    return f'The field at the end of the run. {then}'
