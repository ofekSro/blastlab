"""Field-map CSV export (N14) and the one-click HTML report (N13).

Both are pure writers over a finished Result's pieces, so they are unit
tested headlessly and shared by the GUI export buttons; the report
inlines its images (base64 PNRGs) so the single .html file is the whole
deliverable.
"""

import base64
import datetime
import html
import io
import json
import os

import numpy as np

from ..core.constants import P_AIR
from . import gauge_summary


# ── field-map CSVs (N14) ─────────────────────────────────────────────────────

def _axes(meta, dim):
    if dim == 1:
        return (np.asarray(meta['r']),)
    axes = (np.asarray(meta['x_c']), np.asarray(meta['y_c']))
    if dim == 3:
        axes += (np.asarray(meta['z_c']),)
    return axes

def _write_field(path, axes, values, value_name, unit):
    """One field as long-format CSV: x[,y[,z]],value - row per cell."""
    dim = len(axes)
    heads = ('r[m]',) if dim == 1 else ('x[m]', 'y[m]', 'z[m]')[:dim]
    grids = np.meshgrid(*axes, indexing='ij')
    vals = np.asarray(values)
    cols = [g.ravel(order='C') for g in grids] + [vals.ravel(order='C')]
    header = ','.join(heads) + f',{value_name}[{unit}]'
    np.savetxt(path, np.column_stack(cols), delimiter=',', header=header,
               comments='', fmt='%.6e')
    return vals.size


def save_field_csvs(res, dim, outdir, prefix=''):
    """Write p_peak / impulse / every snapshot field as long-format CSVs
    into `outdir`. Returns the list of (filename, rows) written. Native
    and foam results share the meta layout, 1D exports r,value."""
    meta = res.meta
    axes = _axes(meta, dim)
    out = []

    def emit(name, values, value_name, unit):
        if values is None:
            return
        values = np.asarray(values)
        if values.shape != tuple(len(a) for a in axes):
            return                      # not a field on this grid
        fn = f'{prefix}{name}.csv'
        rows = _write_field(os.path.join(outdir, fn), axes, values,
                            value_name, unit)
        out.append((fn, rows))

    emit('p_peak', meta.get('p_peak'), 'p_peak', 'Pa')
    emit('impulse', meta.get('impulse'), 'impulse', 'Pa.s')
    for label, snap in res.snapshots.items():
        tag = (label.replace(' ', '').replace('=', '')
               .replace('(final)', '_final').replace('.', 'p'))
        for field, unit in (('p', 'Pa'), ('rho', 'kg/m3'),
                            ('speed', 'm/s')):
            if isinstance(snap, dict) and field in snap:
                emit(f'{tag}_{field}', snap[field], field, unit)
    return out


# ── Kingery-Bulmash free-air comparison (N13) ────────────────────────────────

#: KB free-air incident peak overpressure [kPa] at Z = R/W^(1/3)
#: [m/kg^(1/3)] - the same standard polynomial values the KB anchor test
#: pins (test_foam_kb_anchor.KB_FREE_AIR, extended a little both ways)
KB_FREE_AIR = {0.5: 5070.0, 1.0: 904.0, 1.5: 350.0, 2.0: 186.0,
               3.0: 80.0, 4.0: 47.0, 6.0: 24.0, 10.0: 10.6}


def kb_peak_kpa(z):
    """KB free-air peak overpressure at scaled distance `z`, log-log
    interpolated in the table; None outside its range."""
    zs = sorted(KB_FREE_AIR)
    if not zs[0] <= z <= zs[-1]:
        return None
    lz = np.log([float(v) for v in zs])
    lp = np.log([KB_FREE_AIR[v] for v in zs])
    return float(np.exp(np.interp(np.log(z), lz, lp)))


def kb_rows(res, dim, numbers=None):
    """[(gauge label, R, Z, peak kPa, KB kPa, ratio)] for a FREE-AIR
    case - single charge, no obstacles - else [] (the report drops the
    block entirely). `numbers`: the 1D entered numbers (GUI-16 (b),
    `gauge_summary.gauge_labels`)."""
    meta = res.meta
    if meta.get('obstacles'):
        return []
    if meta.get('charges'):             # extra 3D charges
        return []
    W = meta.get('charge_kg') if dim == 1 else meta.get('charge')
    if not W or W <= 0:
        return []
    if dim == 2 and meta.get('geometry') != 'axisymmetric':
        return []                       # planar kg/m has no KB free-air Z
    centre = ((0.0,) if dim == 1
              else (0.0, meta.get('charge_center', (0, 0))[1]) if dim == 2
              else tuple(meta.get('charge_center', (0, 0, 0))))
    rows = []
    g = res.gauges
    pts = g.get('radii') or g.get('points') or []
    for k, pt in enumerate(pts):
        R = (float(pt) if dim == 1
             else float(np.hypot(*(np.asarray(pt) - centre[:len(pt)])))
             if dim == 2
             else float(np.linalg.norm(np.asarray(pt) - centre)))
        z = R / W ** (1.0 / 3.0)
        kb = kb_peak_kpa(z)
        if kb is None or k >= len(g.get('pressures', [])):
            continue
        peak = (np.asarray(g['pressures'][k]).max() - P_AIR) / 1e3
        rows.append((gauge_summary.gauge_labels(g, numbers=numbers)[k], R,
                     z, peak, kb, peak / kb))
    return rows


# ── the HTML report (N13) ────────────────────────────────────────────────────

def _b64png(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=110, bbox_inches='tight')
    return base64.b64encode(buf.getvalue()).decode('ascii')


_CSS = """body{font-family:Segoe UI,Arial,sans-serif;margin:24px auto;
max-width:1100px;color:#222}h1{margin-bottom:0}h2{margin-top:28px;
border-bottom:1px solid #ccc;padding-bottom:4px}table{border-collapse:
collapse;margin:8px 0}th,td{border:1px solid #bbb;padding:4px 10px;
text-align:right}th{background:#eee}td:first-child,th:first-child{
text-align:left}img{max-width:100%;border:1px solid #ddd;margin:6px 0}
.meta{color:#666;font-size:0.9em}pre{background:#f6f6f6;padding:10px;
overflow-x:auto;font-size:0.85em}"""


def save_html_report(res, dim, path, figures=(), title=None,
                     case_json=None, numbers=None):
    """Self-contained HTML report for one Result: banner, case JSON,
    the per-gauge engineering table (N2), inlined field PNGs and - for a
    free-air case - the Kingery-Bulmash comparison. `figures` is
    [(caption, matplotlib Figure)] built by the caller (the GUI reuses
    its existing builders). `numbers`: a 1D result's entered gauge
    numbers, for the tables (GUI-16 (b); None: 1, 2, ...). Returns the
    sections it wrote."""
    meta = res.meta
    name = title or str(meta.get('name') or f'{dim}D run')
    parts, sections = [], []
    parts.append(f'<!doctype html><html><head><meta charset="utf-8">'
                 f'<title>{html.escape(name)}</title>'
                 f'<style>{_CSS}</style></head><body>')
    solver = meta.get('solver', 'native')
    parts.append(
        f'<h1>{html.escape(name)}</h1>'
        f'<p class="meta">{dim}D &middot; solver: {html.escape(solver)}'
        f' &middot; {datetime.datetime.now():%Y-%m-%d %H:%M}'
        f' &middot; stop: {html.escape(res.stop_reason or "-")}</p>')
    sections.append('banner')

    rows = gauge_summary.table_rows(
        gauge_summary.summarize_gauges(res.gauges,
                                       requested=meta.get('gauges'),
                                       numbers=numbers))
    if rows:
        heads = ('Gauge', 'Peak ovp [kPa]', 'Arrival [ms]', 't peak [ms]',
                 'Pos. phase [ms]', 'Pos. imp [Pa&middot;s]',
                 'Net imp [Pa&middot;s]', 'Phase ended')
        parts.append('<h2>Gauges</h2><table><tr>'
                     + ''.join(f'<th>{h}</th>' for h in heads) + '</tr>')
        for r in rows:
            parts.append('<tr>' + ''.join(
                f'<td>{html.escape(str(v))}</td>' for v in r) + '</tr>')
        parts.append('</table>')
        sections.append('gauges')

    kb = kb_rows(res, dim, numbers)
    if kb:
        parts.append('<h2>Kingery-Bulmash free-air comparison</h2>'
                     '<table><tr><th>Gauge</th><th>R [m]</th>'
                     '<th>Z [m/kg<sup>1/3</sup>]</th>'
                     '<th>Peak [kPa]</th><th>KB [kPa]</th>'
                     '<th>ratio</th></tr>')
        for lbl, R, z, pk, ref, ratio in kb:
            parts.append(f'<tr><td>{html.escape(str(lbl))}</td>'
                         f'<td>{R:.2f}</td><td>{z:.2f}</td>'
                         f'<td>{pk:.0f}</td><td>{ref:.0f}</td>'
                         f'<td>{ratio:.2f}</td></tr>')
        parts.append('</table><p class="meta">KB values: standard '
                     'free-air incident polynomial table; detonation-'
                     'only runs land below 1.0 (see ROADMAP N3).</p>')
        sections.append('kb')

    for caption, fig in figures:
        if fig is None:
            continue
        parts.append(f'<h2>{html.escape(caption)}</h2>'
                     f'<img alt="{html.escape(caption)}" '
                     f'src="data:image/png;base64,{_b64png(fig)}">')
        sections.append(f'fig:{caption}')

    cj = case_json
    if cj is None:
        cd = meta.get('case_dir')
        if cd and os.path.isfile(os.path.join(cd, 'case.json')):
            with open(os.path.join(cd, 'case.json'),
                      encoding='utf-8') as f:
                cj = f.read()
    if cj:
        try:
            cj = json.dumps(json.loads(cj), indent=2)
        except ValueError:
            pass
        parts.append('<h2>Case</h2><pre>' + html.escape(cj) + '</pre>')
        sections.append('case')

    parts.append('</body></html>')
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(parts))
    return sections
