"""Tiny persistent GUI settings: one json dict in the user config dir.

Started for the foam run-dir auto-cleanup policy (N8); the same file is
where G9's UI-state persistence (window geometry, appearance mode,
refresh field) belongs. Reads never fail (defaults on any problem),
writes are best-effort.
"""

import json
import os

DEFAULTS = dict(
    auto_cleanup=True,          # sweep old/large foam run dirs at GUI start
    cleanup_max_gb=20.0,        # keep the runs root under this total size
    cleanup_max_age_days=14,    # delete runs untouched for longer than this
    cleanup_keep_recent=3,      # never delete the N most recent runs
    # G9 UI state: restored at startup, saved on close
    geometry='1280x840',        # main window size/position
    appearance='dark',          # 'dark' | 'light'
    refresh_value='',           # Run tab "Refresh every" box
    refresh_mode='seconds',     # 'seconds' | 'steps'
)


def config_path():
    """%APPDATA%\\blastlab\\settings.json on Windows, ~/.config/blastlab
    elsewhere; BLASTLAB_SETTINGS overrides (tests)."""
    override = os.environ.get('BLASTLAB_SETTINGS')
    if override:
        return override
    base = os.environ.get('APPDATA') or os.path.join(
        os.path.expanduser('~'), '.config')
    return os.path.join(base, 'blastlab', 'settings.json')


def load(path=None):
    """DEFAULTS updated with whatever the file holds (missing/corrupt
    file -> defaults)."""
    path = path or config_path()
    out = dict(DEFAULTS)
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            out.update(data)
    except (OSError, ValueError):
        pass
    return out


def save(settings, path=None):
    """Write the dict; returns True on success."""
    path = path or config_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2)
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def update(**kw):
    """load -> update -> save; returns the merged dict."""
    s = load()
    s.update(kw)
    save(s)
    return s
