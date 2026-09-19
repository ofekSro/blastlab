"""Minimal OpenFOAM dictionary text emitter.

`block()` renders a nested Python mapping as OpenFOAM dict syntax:
  dict value          -> named sub-dictionary
  list/tuple value    -> `key (a b c);` when all elements are scalars,
                         otherwise a multi-line parenthesized list whose
                         elements may be vectors (tuples of numbers),
                         (name, dict) pairs (named blocks) or Raw lines
  Raw value           -> emitted verbatim after the key
  scalars             -> `key   value;`

Python dict insertion order is preserved, so files render exactly as
composed. Golden tests in tests/test_foam_writer.py pin the output.
"""

BANNER = ('// * * * * * * * * * * * * * * * * * * * * * * * * '
          '* * * * * * * * * * * * * //')
FOOTER = ('// ' + '*' * 73 + ' //')

#: single-point switches (see plan): flux scheme and the open-boundary
#: pressure BC. Kurganov + pressureWaveTransmissive are the
#: vendor-validated tutorial defaults.
FLUX_SCHEME = 'Kurganov'
P_OPEN_BC = 'pressureWaveTransmissive'
#: Lohner error-estimator noise floor (adaptiveFvMesh `epsilon`); the
#: classic value for pressure-based blast refinement
LOHNER_EPS = 0.05
#: Rebalance the decomposition as the refined region moves (parallel AMR
#: only). ONE switch on purpose: it drives both the `loadBalance` entry
#: in dynamicMeshDict and the addEmptyPatch mesh stage in
#: backend._mesh_stages, and blastFoam refuses to start if the dict says
#: yes without that patch (fvMeshBalance.C:112). Flipping this flips
#: both, so the two can never drift apart.
AMR_LOAD_BALANCE = True
#: `allowableImbalance` (N5-13): rebalancing is SKIPPED while the worst
#: rank is within this fraction of the ideal cell count
#: (fvMeshBalance.C:519, its own default 0.2). A 13-rank AMR run here
#: was measured at a 1:64 imbalance - most of the machine idle - so the
#: point of naming it is to make the knob visible, not to move it.
AMR_ALLOWABLE_IMBALANCE = 0.2
#: `balanceInterval`: refinement steps between rebalances. blastFoam
#: defaults it to `refineInterval`, i.e. rebalance EVERY time the mesh
#: changes, which is the expensive end - every rebalance is a full
#: decompose plus an all-to-all field migration, and the guide warns
#: that migration is where large cases hit the MPI buffer limit (11.2).
#: 5 refinement steps between rebalances keeps the imbalance bounded at
#: a fraction of the cost.
AMR_BALANCE_INTERVAL = 5
#: controlDict `timePrecision` - and, because `startFrom latestTime`
#: re-derives the time NAME from the value it read, the precision any
#: time directory this side writes must be named at. See tfmt().
TIME_PRECISION = 8


class Raw(str):
    """Verbatim fragment - bypasses all formatting."""


def fmt(v):
    """Format one value: floats via %.10g, tuples as (a b c) vectors."""
    if isinstance(v, Raw):
        return str(v)
    if isinstance(v, bool):
        return 'yes' if v else 'no'
    if isinstance(v, float):
        return format(v, '.10g')
    if isinstance(v, (tuple, list)):
        return '(' + ' '.join(fmt(x) for x in v) + ')'
    return str(v)


def tfmt(v):
    """Format a time the way OpenFOAM names its own time directories -
    `timeFormat general` is %g at `timePrecision` significant digits.

    A directory we write must carry exactly this name: `startFrom
    latestTime` keeps the VALUE it scanned and rebuilds the name from
    it, so a name with more digits than timePrecision (fmt's %.10g on a
    remap t0, say) is asked for back at 8 and the run dies on a missing
    field file."""
    return format(float(v), f'.{TIME_PRECISION}g')


def _is_scalar(e):
    # Raw counts as non-scalar so template lines (e.g. setFieldsDict
    # volScalarFieldValue entries) render as multi-line lists.
    return not isinstance(e, (tuple, list, dict, Raw))


def block(mapping, indent=0):
    pad = '    ' * indent
    out = []
    for key, val in mapping.items():
        if isinstance(val, dict):
            out += [f'{pad}{key}', f'{pad}{{',
                    block(val, indent + 1), f'{pad}}}']
        elif isinstance(val, (list, tuple)) and not isinstance(val, Raw):
            if all(_is_scalar(e) for e in val):
                out.append(f'{pad}{key} ({" ".join(fmt(e) for e in val)});')
            else:
                out += [f'{pad}{key}', f'{pad}(']
                for e in val:
                    if (isinstance(e, tuple) and len(e) == 2
                            and isinstance(e[1], dict)):
                        out += [f'{pad}    {e[0]}', f'{pad}    {{',
                                block(e[1], indent + 2), f'{pad}    }}']
                    else:
                        out.append(f'{pad}    {fmt(e)}')
                out.append(f'{pad});')
        else:
            out.append(f'{pad}{key}{" " * max(1, 16 - len(key))}{fmt(val)};')
    return '\n'.join(out)


def foam_file(obj, body, cls='dictionary', location=None):
    """Complete file text: FoamFile header + banner + body + footer."""
    loc = f'    location    "{location}";\n' if location else ''
    return ('FoamFile\n'
            '{\n'
            '    version     2.0;\n'
            '    format      ascii;\n'
            f'    class       {cls};\n'
            f'{loc}'
            f'    object      {obj};\n'
            '}\n'
            f'{BANNER}\n'
            '\n'
            f'{body}\n'
            '\n'
            f'{FOOTER}\n')
