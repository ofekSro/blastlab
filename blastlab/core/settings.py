"""Tiny persistent settings: one json dict in the user config dir.

Started for the foam run-dir auto-cleanup policy (N8); the same file is
where G9's UI-state persistence (window geometry, appearance mode,
refresh field) belongs. Reads never fail (defaults on any problem),
writes are best-effort.

Lives in `core` (not the GUI package) because the foam backend reads it
too - `solvers/foam/env.py` primes the hardware cache and the cleanup
policy from here. `blastlab.gui.settings` re-exports this module for
the Tk GUI until that package is removed.
"""

import json
import os
import sys
import threading

#: one warning per process when a write fails - see save()
_warned = False

#: N21: `update()` is a load-modify-save, and two threads in this one
#: process race on it - the hardware probe thread writes hw_* while the
#: main thread writes the window geometry on close, and whichever loaded
#: first wins. The file write itself is already atomic (os.replace).
_lock = threading.Lock()

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
    # T34: the sidebar solver mode ('native' | 'blastfoam'); a fresh
    # install starts in blastFoam mode
    solver='blastfoam',
    # N17/T48: last WSL hardware probe, so the sidebar and the cell
    # caps show real numbers before the first probe of a session
    # returns. mpi_headroom is the cores left free for the rest of
    # the machine when the rank count is automatic.
    hw_cores=0,                 # WSL VM physical cores
    hw_ram_gb=0,                # WSL VM RAM, GiB
    hw_stamp='',                # when the probe ran (ISO-8601)
    # N21: which machine those numbers describe, and the Windows host's
    # own RAM (the native solvers run in THIS process, not in the VM).
    # Without the fingerprint a settings file carried to another machine
    # - or a .wslconfig edit on this one - pinned stale caps silently;
    # hw_stamp was written but never read.
    hw_fingerprint='',
    hw_host_ram_gb=0,
    mpi_headroom=1,
    #: N21: hard rank ceiling (0 = auto). MAX_AUTO_PROCS is
    #: now only the fallback for an unknown core count.
    mpi_max_ranks=0,
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
    """Write the dict; returns True on success.

    A failure used to be completely silent - `update` ignores the return
    value, so a settings write that never landed looked exactly like one
    that did. That is how a measured hardware probe can be lost, which
    sends the next headless run back to the assumed 4 GB VM. Say so once,
    on stderr, rather than returning False into nothing."""
    path = path or config_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # pid-unique: a GUI and a CLI writing at once used to collide on
        # one fixed '.tmp' name and could publish a half-written file
        tmp = f'{path}.{os.getpid()}.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2)
        os.replace(tmp, path)
        return True
    except OSError as exc:
        global _warned
        if not _warned:
            _warned = True
            print(f'[blastlab] could not write settings ({path}): {exc}',
                  file=sys.stderr)
        return False


def update(**kw):
    """load -> update -> save; returns the merged dict.

    Serialised: the read-modify-write is not atomic, and the hardware
    probe thread and the main thread both call it."""
    with _lock:
        s = load()
        s.update(kw)
        save(s)
        return s
