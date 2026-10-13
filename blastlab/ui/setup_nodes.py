"""GUI-5 (plan §5.1): the Setup model tree's nodes, as data.

Each node groups existing `setup_spec` cards - no field is added,
removed or renamed. Numbering is fixed 01-07 for the blast forms even
when a node is hidden (1D has no 04 Structure; decision D16), so a
number always means the same thing. The 0-D (HD 1.3) form has its own
cards; its tree is one node per visible card, numbered in build order
(plan §5.1), and `setup_spec.HIDDEN_CARDS_0` get no node at all.

Toolkit-free on purpose, like `setup_spec`: a test can read it without a
QApplication. `node_of_field` goes through the card a field is built
into, which is exactly `FieldForm._card_of` (the tree tests cross-check
the two).
"""

from dataclasses import dataclass

from . import scaled_distance, setup_spec


@dataclass(frozen=True)
class Node:
    id: str
    number: str
    title: str
    caption: str = ''


#: the seven blast-form nodes, in tree order (plan §5.1 table). The
#: captions are the one line under the properties heading (plan §5.2).
BLAST_NODES = (
    Node('threat', '01', 'Threat',
         'The design-basis charge the structure must resist.'),
    Node('domain', '02', 'Domain & mesh',
         'The air around the charge and the cells it is solved on.'),
    Node('bounds', '03', 'Boundaries',
         'What each side of the domain does to the wave, and which side '
         'ends the run.'),
    Node('structure', '04', 'Structure',
         'The rigid obstacles the wave reflects from.'),
    Node('gauges', '05', 'Gauges',
         'Where the pressure history is recorded. A gauge just in front '
         'of a wall reads the load that wall carries.'),
    Node('solver', '06', 'Solver',
         'Detonation and afterburn models, time step and end time.'),
    Node('output', '07', 'Output',
         'What the run writes: the animation and the ParaView files.'),
)

_TRIGGER = 'Trigger gauge'
_VTK = 'VTK output (ParaView)'


def _blast_cards(dim):
    """node id -> card titles, for a blast form (dim 1-3)."""
    if dim == 1:
        return {'threat': ('Charge',),
                'domain': ('Domain',),
                'bounds': ('Boundaries',),
                'structure': (),
                'gauges': ('Gauge radii [m]',),
                'solver': ('Numerics',),
                'output': ('Outputs', _VTK)}
    threat = (('Initialization', 'Detonation points [m]') if dim == 2 else
              ('Initialization', 'Extra charges [m, kg]',
               'Detonation points [m]'))
    return {'threat': threat,
            'domain': ('Domain', 'Dynamic refinement (AMR)',
                       'Refinement zones [m, level]'),
            'bounds': ('Boundaries',),
            'structure': ('Obstacles [m]',),
            'gauges': ('Gauges [m]', _TRIGGER),
            'solver': ('Numerics',),
            'output': ('Outputs', _VTK)}


#: 0-D captions, by card title (one line each; blank where the card
#: title already says it)
_HD13_CAPTIONS = {
    'Material': 'The propellant and, where measured, its own burn data.',
    'Charge and chamber': 'How much burns, in what room, and how it vents.',
    'Ignition': 'How the fire spreads through the stack.',
    'Run': 'How long the assessment runs and how often it samples.',
    'Heat': 'Heat lost to the chamber walls.',
    'Radiation standoffs [m]': 'Where the thermal radiation is assessed.',
    'Loaded wall': 'The wall the load export is written for.',
    'Vent stage (blastFoam)': 'Optional: a CFD stage of the vented flow.',
    'Vent gauges [m]': 'Where the vent stage records pressure.',
    'Outputs': 'The run name.',
}


def nodes(dim):
    """[(Node, card titles)] in tree order. Blast forms: always the
    seven nodes (a node may hold no card - 1D's Structure; the tree hides
    it). 0-D: one node per visible card."""
    dim = int(dim)
    if dim == 0:
        out, n = [], 0
        for spec in setup_spec.cards(0):
            if spec.title in setup_spec.HIDDEN_CARDS_0:
                continue
            n += 1
            out.append((Node(f'hd{n:02d}', f'{n:02d}', spec.title,
                             _HD13_CAPTIONS.get(spec.title, '')),
                        (spec.title,)))
        return out
    table = _blast_cards(dim)
    return [(node, table[node.id]) for node in BLAST_NODES]


def node(dim, node_id):
    """The Node `node_id` of dimension `dim`, or None."""
    for n, _titles in nodes(dim):
        if n.id == node_id:
            return n
    return None


def node_cards(dim, node_id):
    for n, titles in nodes(dim):
        if n.id == node_id:
            return tuple(titles)
    return ()


def node_of_card(dim, title):
    """The id of the node that holds card `title`, or None (a card that
    is never shown: HIDDEN_CARDS_0)."""
    for n, titles in nodes(dim):
        if title in titles:
            return n.id
    return None


def card_of_field(dim, name):
    """The title of the card field `name` is built into - the same
    mapping as FieldForm._card_of, read from the spec."""
    for spec in setup_spec.cards(dim):
        if any(f.name == name for f in spec.rows):
            return spec.title
    return None


def node_of_field(dim, name):
    title = card_of_field(dim, name)
    return None if title is None else node_of_card(dim, title)


def card_order(dim):
    """Every card title of the form, in tree order; cards with no node
    (HIDDEN_CARDS_0) last."""
    out = [t for _n, titles in nodes(dim) for t in titles]
    out += [s.title for s in setup_spec.cards(dim) if s.title not in out]
    return out


# ── the one-line summaries under each tree row (plan §5.1) ───────────────
#: 2D axisymmetric side names, as the board says them ("the run ends at
#: Outer"); planar and 3D keep the side keys, which is what the
#: Boundaries card itself shows
AXISYM_SIDES = {'x_lo': 'Axis', 'x_hi': 'Outer', 'y_lo': 'Ground',
                'y_hi': 'Top'}


def _n1(v):
    """A value as the board writes it: one decimal at least ('1.0',
    '2.0'), more when it has them ('0.75', '2.95')."""
    v = float(v)
    s = f'{v:.1f}'
    return s if abs(float(s) - v) < 1e-9 else f'{v:g}'


def _count(n, word):
    return f'no {word}s' if not n else f'{n} {word}{"" if n == 1 else "s"}'


def _mm(cell_m):
    return f'{float(cell_m) * 1000.0:.3g} mm'


def terminate_sides(case):
    """The side names that end the run ('Outer', 'x_hi', ...)."""
    if case.dim == 1:
        return ['Outer'] if case.bc_outer == 'terminate' else []
    axisym = case.dim == 2 and case.geometry == 'axisymmetric'
    return [AXISYM_SIDES.get(s, s) if axisym else s
            for s, kind in (case.bcs or {}).items() if kind == 'terminate']


def summaries(case):
    """{node id: summary line} for a parsed case (a Case1D/2D/3D or a
    DeflagrationCase). Display only: every number is the case's own
    value, formatted, never recomputed."""
    dim = getattr(case, 'dim', None)
    if dim == 0:
        by_title = {
            'Material': str(case.propellant),
            'Charge and chamber': (f'{_n1(case.charge_kg)} kg · '
                                   f'{_n1(case.volume_m3)} m³'),
            'Ignition': str(case.scenario_kind),
            'Run': f'{case.t_end:g} s · {case.n_out} samples',
            'Outputs': str(case.name or ''),
        }
        return {n.id: by_title.get(ts[0], '') for n, ts in nodes(0)}
    foam = getattr(case, 'solver', 'native') == 'blastfoam'
    out = {}
    # 01 Threat
    if dim == 1:
        out['threat'] = f'{_n1(case.charge_kg)} kg {case.material}'
    elif case.init_mode != 'charge':
        out['threat'] = f'starts from a {case.init_mode[-2:].upper()} ' \
                        f'profile'
    else:
        planar = dim == 2 and case.geometry == 'planar'
        up = ('y', case.center[1]) if dim == 2 and planar else \
             ('z', case.center[1] if dim == 2 else case.center[2])
        text = (f'{_n1(case.charge)} kg{"/m" if planar else ""} '
                f'{case.material} · {up[0]} {_n1(up[1])} m')
        extra = len(getattr(case, 'charges', None) or []) if foam else 0
        out['threat'] = text + (f' · +{extra}' if extra else '')
    # 02 Domain & mesh
    if dim == 1:
        dom = f'R {_n1(case.radius_m)} m · {_mm(case.cell_size_m)}'
    else:
        sides = [case.Lx, case.Ly] + ([case.Lz] if dim == 3 else [])
        dom = (' × '.join(f'{float(s):g}' for s in sides)
               + f' m · {_mm(case.cell_size_m)}')
        if foam and case.amr_levels:
            dom += f' · AMR {case.amr_levels}'
        if foam and case.refine_zones:
            dom += f' · {_count(len(case.refine_zones), "zone")}'
    out['domain'] = dom
    # 03 Boundaries
    ends = terminate_sides(case)
    out['bounds'] = ('the run ends at ' + ', '.join(ends) if ends
                     else 'no side ends the run')
    # 04 Structure
    out['structure'] = ('' if dim == 1 else
                        _count(len(case.obstacles or []), 'obstacle'))
    # 05 Gauges: `2 · in front of Wall 1` when a gauge stands within
    # 0.5 m of a wall face (board line 89; the Where helper), else
    # `2 gauges`
    pts = case.gauge_radii if dim == 1 else case.gauges
    walls = scaled_distance.walls_in_front(case)
    g = (f'{len(pts)} · in front of '
         + ', '.join(f'Wall {i}' for i in walls) if walls
         else _count(len(pts or []), 'gauge'))
    # GUI-15 (e), D2 / D11: the dropped gauges are named before the trigger
    gone, off = scaled_distance.drop_state(case)
    if gone:
        g += ' · ' + ', '.join(f'G{n}' for n in gone) + ' dropped'
    tg = getattr(case, 'trigger_gauge', None)
    # GUI-16 (a): a dropped trigger never fires - the caption says so
    out['gauges'] = g + (f' · trigger G{tg}' + (' (disabled)' if off is not None
                                                else '')
                         if tg is not None else '')
    # 06 Solver
    if foam:
        burn = ('no afterburn' if case.afterburn == 'none'
                else f'{case.afterburn} afterburn')
        out['solver'] = f'{case.activation} · {burn} · CFL {case.cfl:g}'
    else:
        out['solver'] = f'{case.eos} · order {case.order} · CFL {case.cfl:g}'
    # 07 Output
    bits = []
    if dim > 1:
        # the extension the run will write - the run's own rule
        from ..services.model_folder import anim_ext
        bits.append(anim_ext(getattr(case, 'anim_file', None)))
    if foam:
        on = any(isinstance(getattr(case, k, None), dict)
                 and getattr(case, k).get('on')
                 for k in ('vtk_volumes', 'vtk_surfaces'))
        bits.append('VTK on' if on else 'VTK off')
    out['output'] = ' · '.join(bits)
    return out
