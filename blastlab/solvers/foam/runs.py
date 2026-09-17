"""Reading the WSL-side blastFoam run directories, without a toolkit.

Lifted out of `gui/run_browser.py` so both front-ends share one
definition of how a run directory is named, sized and dated. The Tk
module re-exports these names, so its importers and its test keep
working.

Listing is instant (names plus the dim out of each `case.json`); sizes
and the alive state cost WSL round trips over 9p, so a browser fills
those in from a worker thread.
"""

import json
import os
import time

#: table layout both browsers use: key, heading, pixel width
COLS = ('name', 'dims', 'size', 'date', 'state')
HEADS = ('Run', 'Dim', 'Size', 'Started', 'State')
WIDTHS = (260, 50, 90, 150, 110)


def human_size(n):
    if n is None:
        return '?'
    n = float(n)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024 or unit == 'TB':
            return f'{n:.0f} {unit}' if unit == 'B' else f'{n:.1f} {unit}'
        n /= 1024.0


def started_from_name(name):
    """'20260905-162157_2d_p26412-00' -> '2026-09-05 16:21:57', or ''
    when the name carries no stamp."""
    try:
        t = time.strptime(str(name)[:15], '%Y%m%d-%H%M%S')
        return time.strftime('%Y-%m-%d %H:%M:%S', t)
    except ValueError:
        return ''


def dims_from_case_json(unc):
    try:
        with open(os.path.join(unc, 'case.json'), encoding='utf-8') as f:
            return f"{int(json.load(f).get('dim'))}D"
    except (OSError, ValueError, TypeError):
        return '?'


def state_text(alive):
    """A run's state in one word. `None` is 'unknown', NOT 'finished':
    Resume and Delete refuse it exactly as they refuse a live one."""
    return 'running' if alive else 'unknown' if alive is None else 'finished'


def posix_of(unc, name):
    from . import env
    return f'{env.RUNS_ROOT}/{name}' if unc else name


# ── the default data sources (each one a WSL round trip) ─────────────────
def default_lister():
    from .postmortem import list_runs
    return list_runs(check_alive=True)


def default_sizer(posix_dirs):
    from . import env
    return env.run_info(posix_dirs)


def default_deleter(posix_dirs):
    from . import env
    return env.delete_runs(posix_dirs)


def build_rows(runs):
    """[(name, unc, alive)] -> {name: {unc, posix, alive, dims, bytes}}.
    Sizes are left None for the second pass to fill."""
    return {name: dict(unc=unc, alive=alive, bytes=None,
                       posix=posix_of(unc, name),
                       dims=dims_from_case_json(unc))
            for name, unc, alive in runs}


def apply_sizes(rows, sizes):
    """Merge a sizer's reply into rows built above."""
    for r in rows.values():
        info = sizes.get(r['posix'])
        if info is not None:
            r['bytes'] = info.get('bytes')
    return rows
