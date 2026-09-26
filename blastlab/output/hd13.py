"""HD1-10: the HD 1.3 report.

A separate writer from `report.save_html_report`, which is a reader of a
solver `Result` - gauges, snapshots, field maps. An HD 1.3 analysis has
none of those and has several things that one has no place for: the
sensitivity envelope, how much of the burn ran outside its calibration,
the three exponents of the closed-vessel reduction, and two thermal
answers that must stay side by side rather than merge.

It shares `report`'s stylesheet and image encoder on purpose, so the two
reports cannot drift apart visually and there is one place to restyle.

WHAT THIS FILE IS REALLY FOR
----------------------------
Every number in the HD 1.3 track carries a caveat that is larger than the
number's own precision, and a report that prints the value without the
caveat is worse than no report. So the writer's contract is:

  * a quantity derived from an uncalibrated field is labelled AT the
    number, not in a footnote;
  * the extrapolation fraction appears next to the peak pressure it
    qualifies, because a peak quoted without it is a two-decade reach
    presented as a measurement;
  * the ignition scenario is stated always, since uniform ignition is a
    laboratory condition and the entrainment it assumes away moves the
    answer by more than any material property;
  * the sensitivity band is ONE envelope, with a small
    one-at-a-time table beside it to say which knob dominates.
"""

import datetime
import html

import numpy as np

# Deliberately the same stylesheet and image encoder as the solver
# report: two reports from one tool should not look like two tools.
from .report import _CSS, _b64png


def _fmt(v, nd=3):
    if v is None:
        return '-'
    if isinstance(v, bool):
        return 'yes' if v else 'no'
    if isinstance(v, str):
        return v
    if isinstance(v, float) and not np.isfinite(v):
        return '-'
    return f'{v:,.{nd}f}'


def _flag(prop, field):
    """The label a number derived from `field` has to carry."""
    return '' if prop is None or prop.is_calibrated(field) \
        else ' <span class="warn">uncalibrated</span>'


def _table(heads, rows):
    out = ['<table><tr>' + ''.join(f'<th>{h}</th>' for h in heads) + '</tr>']
    for r in rows:
        out.append('<tr>' + ''.join(f'<td>{c}</td>' for c in r) + '</tr>')
    out.append('</table>')
    return ''.join(out)


_EXTRA_CSS = """.warn{color:#b00;font-size:0.8em;font-weight:600}
.ok{color:#070;font-size:0.8em}.note{background:#fff8e1;border-left:4px
solid #e0a800;padding:8px 12px;margin:10px 0;font-size:0.92em}"""


def save_hd13_report(path, prop=None, confined=None, unconfined=None,
                     sdof=None, component=None, calibration=None,
                     thermal=None, radiation=(), sensitivity=None,
                     sensitivity_note='', verdict=None, qd=None, oat=(),
                     figures=(), title=None):
    """Write the whole HD 1.3 analysis as one self-contained .html.

    Every argument is optional: the report prints the sections it was
    given, so a bare 0-D run and a full confined/unconfined/thermal
    study both render. Returns the list of sections written.

    `sdof`, `component` and `verdict` are accepted and IGNORED (HD1-16
    step 1, item 3: no output carries a structural response); they go
    with core/sdof.py in HD1-16 step 2.
    """
    name = title or 'HD 1.3 assessment'
    p, sections = [], []
    p.append(f'<!doctype html><html><head><meta charset="utf-8">'
             f'<title>{html.escape(name)}</title>'
             f'<style>{_CSS}{_EXTRA_CSS}</style></head><body>')
    p.append(f'<h1>{html.escape(name)}</h1>'
             f'<p class="meta">HD 1.3 deflagration &middot; '
             f'{datetime.datetime.now():%Y-%m-%d %H:%M}</p>')
    sections.append('banner')

    p.append('<div class="note"><b>What this is.</b> An HD 1.3 material '
             'deflagrates rather than detonates. Entering it as a "TNT '
             'equivalent" does not merely change the magnitude - it moves '
             'the answer to the opposite corner of the pressure-impulse '
             'diagram, because the load is quasi-static rather than '
             'impulsive. The blast path in this repo models detonation '
             'and does not apply.</div>')

    if prop is not None:
        rows = []
        for f, label, val, unit in (
                ('force', 'Impetus', prop.force / 1e6, 'MJ/kg'),
                ('T_flame', 'Flame temperature', prop.T_flame, 'K'),
                ('covolume', 'Co-volume', prop.covolume * 1e3, 'l/kg'),
                ('rho', 'Solid density', prop.rho, 'kg/m3'),
                ('n', 'Vieille exponent', prop.n, '-'),
                ('a', 'Vieille coefficient', prop.a, 'm/s/Pa^n'),
                ('web', 'Web', prop.web * 1e3, 'mm'),
                ('r_atm', 'Burn rate at 1 atm', prop.r_atm * 1e3, 'mm/s'),
                ('p_extinction', 'Extinction limit',
                 prop.p_extinction / 1e6, 'MPa'),
                ('secondary_heat', 'Secondary (air) heat',
                 prop.secondary_heat / 1e6, 'MJ/kg')):
            rows.append((label + _flag(prop, f), _fmt(val, 4), unit))
        p.append('<h2>Material</h2>' + _table(('Property', 'Value', 'Unit'),
                                              rows))
        if not prop.calibrated:
            p.append(f'<div class="note"><b>Not calibrated.</b> The fields '
                     f'marked above rest on class-typical literature '
                     f'ranges, not on a test of this material: '
                     f'<code>{html.escape(", ".join(prop.uncalibrated))}'
                     f'</code>. A closed-vessel record fixes the burn law '
                     f'but can never fix the extinction limit, the '
                     f'atmospheric rate or the secondary heat, because it '
                     f'never visits low pressure and contains no free '
                     f'oxygen.</div>')
        sections.append('material')

    if calibration:
        c = calibration
        p.append('<h2>Closed-vessel calibration</h2>')
        p.append(_table(
            ('Reduction', 'n', 'What it accounts for'),
            ((f'raw', _fmt(c['n_raw'], 4),
              'nothing - the textbook regression'),
             ('form-corrected', _fmt(c['n_form'], 4),
              'the burning surface changing as the grain burns'),
             ('form + heat', _fmt(c['n_form_heat'], 4),
              'and the energy the vessel gave its walls'),
             ('<b>fitted</b>', f"<b>{_fmt(c['n'], 4)}</b>",
              'least squares on the full record'))))
        p.append(f'<p class="meta">Form-function bias '
                 f'{c["form_bias"]:+.4f}, heat bias {c["heat_bias"]:+.4f}. '
                 f'Measured peak was {100 * c["energy_retained"]:.1f} % of '
                 f'the adiabatic limit. Valid over '
                 f'{c["p_valid"][0] / 1e6:.2f}-{c["p_valid"][1] / 1e6:.1f} '
                 f'MPa.</p>')
        sections.append('calibration')

    if confined is not None:
        r = confined
        ex = r.get('extrapolated_fraction', 0.0)
        rows = [
            ('Peak pressure', _fmt(r['p_max'] / 1e6, 3), 'MPa'),
            ('Peak overpressure', _fmt((r['p_max'] - 101325.0) / 1e3, 1),
             'kPa'),
            ('Time of peak', _fmt(r['t_p_max'], 4), 's'),
            ('Burnt out', _fmt(r['burnt_out']), ''),
            ('Stopped because', html.escape(str(r.get('stop_reason', '-'))),
             ''),
            ('Ignition scenario',
             html.escape(str(r.get('scenario_kind', '-')))
             + (' <span class="warn">laboratory condition</span>'
                if r.get('calibration_only_scenario') else ''), ''),
            ('Burn outside the calibration window',
             f'{100 * ex:.1f}'
             + (' <span class="warn">the whole burn</span>'
                if ex > 0.99 else ''), '%'),
        ]
        p.append('<h2>Confined: quasi-static pressure</h2>'
                 + _table(('Quantity', 'Value', 'Unit'), rows))
        if ex > 0.5:
            p.append('<div class="note"><b>Extrapolation.</b> The burn law '
                     'was measured over a pressure range this run mostly '
                     'did not visit. A closed vessel is calibrated at tens '
                     'to hundreds of MPa; a vented magazine sits at a few. '
                     'The dominant error in a reach that long is in the '
                     'exponent, not the coefficient.</div>')
        sections.append('confined')

    if unconfined is not None:
        r = unconfined
        rows = [
            ('Burn duration', _fmt(r['burn_time'], 2), 's'),
            ('Peak gas rate', _fmt(r['mdot_max'], 4), 'kg/s'),
            ('Energy released (anaerobic)', _fmt(r['energy_total'] / 1e6, 1),
             'MJ'),
            ('Expansion Mach (upper bound)', _fmt(r['mach_max'], 4), '-'),
            ('Blast negligible', _fmt(r['blast_negligible']), ''),
        ]
        p.append('<h2>Unconfined: the same charge in the open</h2>'
                 + _table(('Quantity', 'Value', 'Unit'), rows))
        if r.get('simultaneous_limit'):
            p.append('<div class="note"><b>This is a limit, not a '
                     'scenario.</b> It lights the whole stack at once. In '
                     'the open a grain cannot burn before the flame has '
                     'reached it, so simultaneous ignition is not a '
                     'conservative assumption - it is an impossible one. '
                     'Use it to see how far a real fire sits from it.</div>')
        elif r['blast_negligible']:
            p.append('<div class="note"><b>Why there is no blast.</b> The '
                     'gas leaves the burning stack far below the speed of '
                     'sound, so the release cannot steepen into a shock. '
                     'That is computed here, not quoted - and it holds '
                     'because the fire takes far longer to cross the stack '
                     'than any item takes to burn, not because of the '
                     'material alone.</div>')
        sections.append('unconfined')

    # HD1-16 step 1, item 3: no "Structural response" section. blastlab
    # gives the load (the SBEDS CSVs beside this report), SBEDS the
    # response.

    if thermal is not None:
        rows = [('Peak flux to the wall',
                 _fmt(thermal['q_max'] / 1e3, 1), 'kW/m2'),
                ('Peak inner-face temperature',
                 _fmt(thermal['T_surface_max'] - 273.15, 1), 'C'),
                ('Heat delivered per unit area',
                 _fmt(thermal['heat_per_area'] / 1e6, 3), 'MJ/m2')]
        p.append('<h2>Heat: the confined wall</h2>'
                 + _table(('Quantity', 'Value', 'Unit'), rows))
        sections.append('thermal')

    if radiation:
        rows = [(f"{r['distance']:.0f}", _fmt(r['flux'] / 1e3, 2),
                 _fmt(r['dose'], 0), html.escape(r['verdict'])
                 + ' <span class="warn">uncalibrated</span>')
                for r in radiation]
        p.append('<h2>Heat: fireball radiation</h2>'
                 + _table(('Standoff [m]', 'Flux [kW/m2]',
                           'Dose [(kW/m2)^(4/3) s]', 'Against thresholds'),
                          rows))
        p.append('<div class="note"><b>Empirical path.</b> blastFoam does '
                 'not solve radiation, so the fireball comes from '
                 'correlations fitted to hydrocarbon and BLEVE work, '
                 'driven by the energy actually available here. The '
                 'emissive power that falls out lands in the range '
                 'measured on real fireballs, which is a consistency '
                 'check - not a calibration.</div>')
        sections.append('radiation')

    if sensitivity:
        rows = [(html.escape(k), _fmt(v[0], 4), _fmt(v[1], 4))
                for k, v in sensitivity.items()]
        p.append('<h2>Sensitivity</h2>'
                 '<p class="meta">One envelope over the corners of the '
                 'uncertain inputs - not a set of runs to choose from.</p>'
                 + _table(('Quantity', 'Low', 'High'), rows))
        # The caveats travel with the band and not in a footnote: the
        # width rests on ranges that are usually a judgement, and a band
        # that straddles extinction is not an interval at all.
        if sensitivity_note:
            p.append(f'<p class="warn">{html.escape(sensitivity_note)}</p>')
        # HD1-16: no "Does that verdict survive the band?" table - the
        # band's traces go to SBEDS as band_<signs>.csv instead.
        if oat:
            p.append('<p class="meta">Which knob dominates, one at a '
                     'time:</p>'
                     + _table(('Input', 'Swing'),
                              [(html.escape(a), _fmt(b, 4)) for a, b in oat]))
        sections.append('sensitivity')

    # QUANTITY-DISTANCE. The section renders whether or not anything was
    # entered, and that is the point: a siting report that simply omits
    # the comparison reads as though it was not needed, while one that
    # prints the sentence says it was not DONE. The two are different
    # and only the second is true.
    if qd is not None:
        p.append('<h2>Quantity-distance</h2>')
        if not qd.get('have_criteria'):
            p.append(f'<div class="note"><b>No comparison.</b> '
                     f'{html.escape(qd.get("note", ""))}</div>')
        else:
            p.append(_table(
                ('Criterion', 'Protects', 'Basis', 'K', 'Required [m]',
                 'Source'),
                [(html.escape(str(r['name'])),
                  html.escape(str(r['protects'])),
                  html.escape(str(r['basis'])),
                  _fmt(r['k_factor'], 3),
                  f"<b>{_fmt(r['distance_m'], 1)}</b>",
                  html.escape(str(r['source']))) for r in qd['rows']]))
            if qd.get('standoffs'):
                p.append(_table(
                    ('Criterion',) + tuple(f'{s:g} m'
                                           for s in qd['standoffs']),
                    [(html.escape(str(r['name'])),)
                     + tuple(('<span class="ok">meets</span>' if ok else
                              f'<span class="warn">short by '
                              f'{_fmt(sh, 1)} m</span>')
                             for ok, sh in zip(r['meets'],
                                               r['shortfall_m']))
                     for r in qd['rows']]))
            p.append(f'<p class="meta">Every factor above is one the user '
                     f'entered, with the source it came from printed '
                     f'beside it - this tool ships none. Governing: '
                     f'<b>{html.escape(str(qd["governing"]))}</b> at '
                     f'{_fmt(qd["governing_distance_m"], 1)} m.</p>')
        sections.append('qd')

    for caption, fig in figures:
        p.append(f'<h2>{html.escape(str(caption))}</h2>'
                 f'<img src="data:image/png;base64,{_b64png(fig)}">')
    if figures:
        sections.append('figures')

    p.append('</body></html>')
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(''.join(p))
    return sections
