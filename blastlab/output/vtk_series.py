"""OUT-2: ParaView's `.vtk.series` index and the vtk\\ manifest.

docs/model-folder-and-vtk-plan.md sec. 3.5 step 5 and sec. 3.6; batch
plan docs/batches/2026-09-27-out-2-vtk-output.md Step 5.

A `.vtk.series` file is ParaView's JSON file series, the index blastFoam's
own vtkTimeSeries writer and createTimeSeries utility write "with the
relative paths to all write times" (blastFoam User Guide v6.0, sec. 15.5,
p. 124 and sec. 16.3, p. 133; the guide gives no layout - this one is
vtkTimeSeries.C::writeTimeSeries, blastfoam src, read on this machine):

    {"file-series-version": "1.0",
     "files": [{"name": "t_0.0005.vtk", "time": 0.0005}, ...]}

`name` is relative to the series file. Every file here is written UTF-8
without BOM, LF, and atomically (a temp file, then os.replace), so a
ParaView session that has the series open never reads half a file.

Pure file I/O: no VTK import (the GUI process never imports VTK).
"""

import json
import os

SERIES_SUFFIX = '.vtk.series'
SERIES_VERSION = '1.0'
MANIFEST_FILE = 'manifest.json'

#: the vtk\\ manifest's keys, in file order
MANIFEST_KEYS = ('fields', 'cadence', 'families', 'not_converted',
                 'deleted_in_wsl', 'replay_incomplete')


def _atomic_write(path, text):
    """`text` to `path` via `<path>.tmp` + os.replace; the old file stays
    whole when anything fails (the temp file is removed, the error
    re-raised)."""
    tmp = path + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _entry(e):
    """(name, time) from a (name, time) pair or a {'name', 'time'} dict."""
    if isinstance(e, dict):
        name, t = e['name'], e['time']
    else:
        name, t = e
    name = str(name).replace('\\', '/')
    if not name or name.startswith('/') or ':' in name \
            or '..' in name.split('/'):
        raise ValueError(f'a series entry must be a relative name: {name!r}')
    return name, float(t)


def read_series(path):
    """[(name, time)] of an existing `.vtk.series`, [] when it is absent
    or unreadable."""
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        return [_entry(e) for e in data.get('files', [])]
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return []


def series_path(folder, name):
    """`<folder>/<name>.vtk.series` (the suffix added when missing)."""
    name = str(name)
    if not name.endswith(SERIES_SUFFIX):
        name += SERIES_SUFFIX
    return os.path.join(folder, name)


def write_series(folder, name, entries, merge=True):
    """Write `<folder>/<name>.vtk.series` listing `entries` - (relative
    name, time) pairs or {'name', 'time'} dicts - sorted by time as a
    float (so `1e-05` comes before `0.0001`), one entry per name. With
    `merge` the entries already in the file are kept, so a rewrite after
    one more time (or after a resume) never drops the earlier ones.
    Returns the path. Raises OSError / ValueError; the old file is then
    untouched."""
    path = series_path(folder, name)
    by_name = dict(read_series(path)) if merge else {}
    by_name.update(_entry(e) for e in entries)
    files = [dict(name=n, time=t) for n, t in
             sorted(by_name.items(), key=lambda kv: (kv[1], kv[0]))]
    text = json.dumps({'file-series-version': SERIES_VERSION,
                       'files': files}, indent=2) + '\n'
    os.makedirs(folder, exist_ok=True)
    _atomic_write(path, text)
    return path


def new_vtk_state():
    """An empty vtk\\ manifest state, keys in file order."""
    return dict(fields={}, cadence={}, families={}, not_converted=[],
                deleted_in_wsl=[], replay_incomplete=False)


def write_vtk_manifest(vtk_dir, state):
    """`<vtk_dir>/manifest.json`: {fields, cadence, families{volumes |
    sections | obstacles: {count, times, series, files}}, not_converted: [{time,
    why}], deleted_in_wsl, replay_incomplete} (plan sec. 3.5 step 5).
    Keys missing from `state` get their empty value; extra keys follow.
    Returns the path; raises OSError on a failed write (old file kept)."""
    out = new_vtk_state()
    out.update(state or {})
    ordered = {k: out[k] for k in MANIFEST_KEYS}
    ordered.update((k, v) for k, v in out.items() if k not in ordered)
    os.makedirs(vtk_dir, exist_ok=True)
    path = os.path.join(vtk_dir, MANIFEST_FILE)
    _atomic_write(path, json.dumps(ordered, indent=2, ensure_ascii=False)
                  + '\n')
    return path


def load_vtk_manifest(vtk_dir):
    """The vtk\\ manifest as a dict, or None when there is none (or it
    cannot be read)."""
    try:
        with open(os.path.join(vtk_dir, MANIFEST_FILE),
                  encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _disk_totals(folder):
    """(files, bytes) of everything under `folder`."""
    n = size = 0
    for root, _dirs, names in os.walk(folder):
        for name in names:
            try:
                size += os.path.getsize(os.path.join(root, name))
            except OSError:
                continue
            n += 1
    return n, size


def vtk_summary(vtk_dir, rel='vtk'):
    """The model folder manifest's `vtk` entry, or None when the run
    exported nothing: {dir, counts (converted files per family), files and
    bytes (everything under vtk\\, series and manifest included),
    not_converted}. Numbers only (owner decision P4, 2026-09-27): the
    root manifest's `outputs` leaves vtk\\ out, and the full file list is
    vtk\\manifest.json's `families.<family>.files`."""
    state = load_vtk_manifest(vtk_dir)
    if state is None:
        return None
    fams = state.get('families') or {}
    counts = {k: int((v or {}).get('count') or 0) for k, v in fams.items()}
    n, size = _disk_totals(vtk_dir)
    return dict(dir=rel, counts=counts, files=n, bytes=size,
                not_converted=list(state.get('not_converted') or []))
