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
  native -> blastFoam hand-off rule, exactly what `run()` will say, plus
  one warning `run()` does not give: `handoff_reach`, a 1D hand-off
  radius that already reaches the next stage's boundary or a wall (QA
  S2-1, D200). Nothing is written and no hand-off path of a later stage
  is checked.
- The hand-off texts are the board's sentences with the wired case's own
  numbers (formatted, never computed).

The hand-off itself is a lower-dimension field remapped onto the next
grid (Wurster & McDonald, Viper Blast Theory Manual (2025), sec. 3.4.1,
p. 6) - background for the texts only, not a source for any value.
"""

import copy
import os
import re
from dataclasses import dataclass, field

from ..core import mode as mode_mod
from ..services import chain as chain_svc
from ..services import model_folder
from ..services.validation import validate_case
from . import scaled_distance, setup_nodes

#: (key, label, dims) in board order (Chain.dc.html, `ROUTES`)
ROUTES = (('123', '1D → 2D → 3D', (1, 2, 3)),
          ('13', '1D → 3D', (1, 3)),
          ('12', '1D → 2D', (1, 2)),
          ('23', '2D → 3D', (2, 3)))
DEFAULT_ROUTE = '123'
#: UXR-12 (D222): one line per route button, what its hand-offs do (the
#: route group's own tooltip keeps the whole explanation, HINT)
ROUTE_TIPS = {
    '123': ('1D → 2D → 3D: the 1D profile is remapped onto the 2D axis, '
            'then the 2D field is swept around the 3D burst axis'),
    '13': ('1D → 3D: the 1D profile is placed around the 3D burst point; '
           'no 2D stage'),
    '12': ('1D → 2D: the 1D profile is remapped onto the 2D axis at the 2D '
           'burst height; no 3D stage'),
    '23': ('2D → 3D: the 2D stage starts from its charge, and its field is '
           'swept around the 3D burst axis; no 1D stage'),
}

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


_STAGE_LINE = re.compile(r'^Stage (\d) \((\d)D\): ')


def by_position(lines, stages):
    """GUI-16 round 2 (A5, U4): `services.chain` numbers a stage by its
    dimension (`Stage 3 (3D): ...`); on route 1 -> 3 the user sees two
    stages, so the Chain screen's dialogs say `Stage 2 (3D): ...`.
    `stages` is the checked dims in order. Routes 1 -> 2 and 1 -> 2 -> 3
    keep every byte; a line with another start is returned as it is."""
    where = {int(d): i for i, d in enumerate(stages, 1)}

    def one(line):
        m = _STAGE_LINE.match(line)
        if m is None or int(m.group(2)) not in where:
            return line
        return (f'Stage {where[int(m.group(2))]} ({m.group(2)}D): '
                + line[m.end():])
    return [one(str(ln)) for ln in lines]


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
    #: the F45 / S2-1 line (also in `warnings`), '' when there is none:
    #: it is fixed on the Domain & mesh node (GUI-13 B2, D8)
    reach: str = ''

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


def _reach_2d(R, case):
    """(limit, far, domain text, reaches) of a 1D profile of radius R
    remapped onto 2D stage `case`, burst at (0, cy). The rule is the
    solver's own remap warning (solvers/solver2d.py, `if profile is not
    None`: R > Lx, cy - R < 0, cy + R > Ly, or an obstacle closer than R
    to (0, cy)); `limit` is the largest R that does not trigger it, `far`
    the farthest domain point from the burst."""
    Lx, Ly = float(case.Lx), float(case.Ly)
    cy = float(case.center[1])
    gaps = [Lx, cy, Ly - cy]
    for box in case.obstacles or []:
        ox0, ox1, oy0, oy1 = (float(v) for v in box[:4])
        px = min(max(0.0, ox0), ox1)
        py = min(max(cy, oy0), oy1)
        gaps.append((px * px + (py - cy) ** 2) ** 0.5)
    limit = min(gaps)
    far = (Lx * Lx + max(cy, Ly - cy) ** 2) ** 0.5
    reaches = R > Lx or cy - R < 0 or cy + R > Ly or any(
        g < R for g in gaps[3:])
    return limit, far, f'{_n1(Lx)} × {_n1(Ly)}', reaches


def _reach_3d(R, case):
    """The same for a 1D profile placed around the 3D burst point: the
    solver's rule (solvers/solver3d.py, the 1D-profile branch) is
    min(x0, Lx - x0, y0, Ly - y0, z0, Lz - z0) < R; obstacles are not
    part of it."""
    Ls = [float(case.Lx), float(case.Ly), float(case.Lz)]
    c = [float(v) for v in case.center[:3]]
    gaps = [g for v, L in zip(c, Ls) for g in (v, L - v)]
    limit = min(gaps)
    far = sum(max(v, L - v) ** 2 for v, L in zip(c, Ls)) ** 0.5
    dom = ' × '.join(_n1(L) for L in Ls)
    return limit, far, dom, limit < R


def _burst_above_3d(two, three):
    """GUI-12 B1 (F45, owner row 5): the 2D -> 3D remap
    (core/profiles.remap_profile_2d_to_3d) rotates the r-z field about the
    3D burst axis and maps the 2D z onto the 3D z (both grounds at 0). A 2D
    burst at or above the 3D height therefore lands outside the 3D box.
    Only the burst height is checked; a cut radial far field is normal in a
    chain (decision row 3). Returns the warning or ''.

    GUI-13 (b), owner 2026-10-04 (D1, D3, Q3): the trigger stays Burst >=
    Lz; the text names the fields by their form labels (the axisymmetric
    form calls cy `Burst z` and Ly `Height H`, `setup_spec.AXISYM_LABELS`)
    and advises Lz >= the 2D stage's height, the whole 2D field."""
    try:
        zb = float(two.center[1])
        Lz = float(three.Lz)
    except (AttributeError, TypeError, ValueError, IndexError):
        return ''
    if zb < Lz:
        return ''
    axisym = getattr(two, 'geometry', 'axisymmetric') == 'axisymmetric'
    burst, height = ('Burst z', 'Height H') if axisym else ('Burst y', 'Ly')
    # F45 (C7 (i)): a short lead - the burst, not the whole field, is the
    # point; the advice sentence says what to size
    head = (f'The 2D stage\'s {burst} ({_n1(zb)} m) is at or above this '
            f'stage\'s Lz ({_n1(Lz)} m): the 3D box cuts the burst off. ')
    try:
        Ly = float(two.Ly)
    except (AttributeError, TypeError, ValueError):
        return head + f'Raise Lz above {_n1(zb)} m.'
    return head + (f'Raise Lz to at least {_n1(Ly)} m (the 2D stage\'s '
                   f'{height}) or lower the 2D stage\'s {burst}.')


def handoff_reach(dims, cases):
    """{dim: warning} for a stage fed by a 1D stage whose shock has, at
    the hand-off, already reached this stage's boundary or a wall (QA
    S2-1, D200). Toolkit-free; `cases` are the WIRED cases ({dim: case
    or None}).

    Checked only where the hand-off radius is known before the run: the
    stage before is 1D, its Outer boundary terminates it and it has no
    End time, so it hands off when the shock is at R = radius_m
    (`out_text`; solvers/solver1d.py stops at the End time when one is
    set, or at the shock's arrival at a terminating Outer, whichever
    comes first - with an End time the radius at the hand-off is not
    known before the run). A 2D stage feeding 3D is checked on the burst
    height alone (`_burst_above_3d`, GUI-12 B1). Every other case is not
    checked and nothing is said. The rule mirrors the
    solvers' own remap warning (`_reach_2d`, `_reach_3d`); this only
    says it before the run."""
    dims = [int(d) for d in dims]
    out = {}
    for prev, d in zip(dims, dims[1:]):
        one, case = cases.get(prev), cases.get(d)
        if prev == 2 and d == 3 and one is not None and case is not None:
            msg = _burst_above_3d(one, case)
            if msg:
                out[d] = msg
            continue
        if prev != 1 or d not in (2, 3) or one is None or case is None:
            continue
        try:
            if 'Outer' not in setup_nodes.terminate_sides(one) \
                    or float(getattr(one, 't_end', 0.0) or 0.0) > 0.0:
                continue
            R = float(one.radius_m)
            limit, far, dom, reaches = (_reach_2d if d == 2
                                        else _reach_3d)(R, case)
        except (AttributeError, TypeError, ValueError, IndexError):
            continue
        if not reaches:
            continue
        fix = limit > 0.0
        if R >= far:
            msg = (f'The 1D stage hands off when its shock is at '
                   f'{_n1(R)} m, beyond this stage\'s whole {dom} m '
                   f'domain: this stage would start after the wave has '
                   f'left it.'
                   + (f' Set stage 1\'s radius below {_n1(limit)} m.'
                      if fix else ''))
        else:
            msg = (f'The 1D stage hands off at {_n1(R)} m; that already '
                   f'reaches this stage\'s boundary or a wall, so the remap '
                   f'is not spherical there (the run warns too).'
                   + (f' Set stage 1\'s radius below {_n1(limit)} m to '
                      f'keep it inside.' if fix else ''))
        out[d] = msg
    return out


_GAUGE_LINE = re.compile(r'G(\d+)\b')


def focus_target(message):
    """D24, toolkit-free: what a click on a Checks line focuses, by the
    message. `(stage or None, kind, key)` - `stage` None is the stage the
    line stands in: F45 (the 2D burst at or above this stage's Lz) ->
    `(None, 'field', 'Lz')`; S2-1 (the 1D hand-off reaches this stage's
    boundary) -> `(1, 'field', 'radius_m')`, the 1D stage's radius; a line
    that starts `G<n>` -> `(None, 'gauge', n)`. None for any other line:
    a click on it does nothing."""
    text = str(message).replace('’', "'")
    if text.startswith('The 1D stage hands off'):
        return 1, 'field', 'radius_m'
    if text.startswith('The 2D stage') and "this stage's Lz" in text:
        return None, 'field', 'Lz'
    m = _GAUGE_LINE.match(text)
    if m:
        return None, 'gauge', int(m.group(1))
    return None


#: D28: what a blastFoam stage's `Large grid` line gains while the WSL
#: hardware probe runs - validation then judges it against assumed caps
PROVISIONAL = ' (provisional until the WSL hardware check finishes)'


def provisional_grid(chk):
    """C7 (ii), D28: while the hardware probe runs, a blastFoam stage's
    `Large grid: ...` warning becomes a note carrying PROVISIONAL (the cap
    it is judged against is an assumed VM's). Only that line moves; a
    native stage, whose caps the probe does not touch, is left alone."""
    if getattr(chk.case, 'solver', 'native') != 'blastfoam':
        return chk
    keep = []
    for w in chk.warnings:
        if w.startswith('Large grid'):
            chk.notes.append(w + PROVISIONAL)
        else:
            keep.append(w)
    chk.warnings = keep
    return chk


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
    reach = handoff_reach(dims, cases)
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
        if d in reach:
            # D200: a warning, never a refusal - run() is unchanged
            chk.warnings.append(reach[d])
            chk.reach = reach[d]
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
    height named is the wired case's own (2D: cy, 3D: cz), by its form
    label (GUI-13 (b))."""
    if not prev:
        return NONE_IN
    if case.dim == 2:
        burst = ('Burst z' if getattr(case, 'geometry', 'axisymmetric')
                 == 'axisymmetric' else 'Burst y')
        return (f'Remapped onto the axis. The burst height ({burst}, '
                f'{_n1(case.center[1])} m) is taken from this stage’s '
                f'form.')
    if prev == 2:
        return ('Swept around the burst axis to start the 3D field. The '
                'burst height comes from the 2D profile.')
    return (f'The 1D profile is placed around the burst point. With no 2D '
            f'stage, the burst height (Burst z, {_n1(case.center[2])} m) '
            f'is set in this stage’s form.')


#: the 3D stage's centre before its first live check (UXR-12)
HINT_3D_HEAD = 'This 3D stage has no preview here.'


def hint_3d(case, prev, source=None):
    """The 3D stage's centre text (UXR-12, D222), from the WIRED case:
    `This 3D stage has no preview here. Its domain is 6 × 6 × 4 m, burst
    at z 2.0 m (from the 2D profile).` Fed by 2D, the burst height is the
    2D stage's (`source`) burst z: `core/profiles.remap_profile_2d_to_3d`
    maps the 2D z straight onto the 3D z. Fed by 1D, it is this stage's
    own cz (`in_text`). Display only, formatted, never computed."""
    if case is None:
        return HINT_3D_HEAD
    dom = ' × '.join(f'{float(v):g}' for v in (case.Lx, case.Ly, case.Lz))
    if prev == 2:
        z = (source.center[1] if source is not None
             and getattr(source, 'center', None) else None)
        burst = (f'burst at z {_n1(z)} m (from the 2D profile)'
                 if z is not None else
                 'its burst height comes from the 2D profile')
    elif prev == 1:
        burst = (f'burst at z {_n1(case.center[2])} m (set in this '
                 f'stage’s form)')
    else:
        burst = f'burst at z {_n1(case.center[2])} m'
    return f'{HINT_3D_HEAD} Its domain is {dom} m, {burst}.'


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
    if tg is not None and scaled_distance.drop_state(case)[1] is not None:
        # GUI-16 (a), D21: a dropped trigger never fires - the stage runs on
        ends = setup_nodes.terminate_sides(case)
        lead = (f'The field when the wave reaches {" or ".join(ends)}, or '
                f'at the end of the run' if ends else
                'The field at the end of the run')
        return (f'{lead} (trigger G{tg} is dropped, so it never fires). '
                f'{then}')
    if tg is not None:
        action = getattr(case, 'trigger_action', 'terminate')
        return (f'The field when the wave reaches G{tg} (trigger gauge, '
                f'{action}), or at the end of the run. {then}')
    ends = setup_nodes.terminate_sides(case)
    if ends:
        return (f'The field when the wave reaches {" or ".join(ends)}, or '
                f'at the end of the run. {then}')
    return f'The field at the end of the run. {then}'
