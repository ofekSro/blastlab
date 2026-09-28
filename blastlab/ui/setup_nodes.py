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

from . import setup_spec


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
