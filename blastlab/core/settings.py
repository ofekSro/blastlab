"""Tiny persistent settings: one json dict in the repo checkout.

Started for the foam run-dir auto-cleanup policy (N8); the same file is
where G9's UI-state persistence (window geometry, appearance mode,
refresh field) belongs. Reads never fail (defaults on any problem),
writes are best-effort.

Lives in `core` (not the GUI package) because the foam backend reads it
too - `solvers/foam/env.py` primes the hardware cache and the cleanup
policy from here. `blastlab.gui.settings` re-exports this module for
the Tk GUI, which stays as the permanent way back behind `--tk`
(CLAUDE.md section 9).

P0-5 (owner decision): the file lives IN THE REPO, at one explicit path
no virtualisation can redirect.

- `default_path()` is `<repo>\\settings.json`, `<repo>` being the parent
  of the `blastlab/` package. It is git-ignored (it carries this
  machine's `hw_*` fields). The Microsoft Store Python used to redirect
  `%APPDATA%\\blastlab\\settings.json` to a private
  `LocalCache\\Roaming` copy that the app read and nobody else saw.
- `config_path()` is `BLASTLAB_SETTINGS` when set (tests, harnesses),
  `default_path()` otherwise.
- One-time migration, inside `load()`, only when the path in use is
  `default_path()` (BLASTLAB_SETTINGS unset) and that file is missing:
  the first readable JSON dict among the Store-Python virtual copy
  (newest if several) and `%APPDATA%\\blastlab\\settings.json` is copied
  there with `auto_cleanup` forced to False and a `migrated_from` key,
  and one stderr line names the source. The sources are never written,
  renamed or deleted, and an existing repo file is never overwritten.
  No source: nothing is created, and the first `update()` writes it.
- Every checkout (worktrees included) has its own file, seeded on its
  first run - a consequence of "in the repo", not a bug.
- The crash log (`ui/crashlog.py`) sits beside the settings file, so it
  lands in the repo root too; `.gitignore` covers both.
"""

import glob
import json
import os
import sys
import threading

#: The repo checkout that holds the `blastlab/` package. A module-level
#: name so the tests can point it at a temp dir.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

#: one warning per process when a write fails - see save()
_warned = False

#: N21: `update()` is a load-modify-save, and two threads in this one
#: process race on it - the hardware probe thread writes hw_* while the
#: main thread writes the window geometry on close, and whichever loaded
#: first wins. The file write itself is already atomic (os.replace).
_lock = threading.Lock()

DEFAULTS = dict(
    # sweep old/large foam run dirs at GUI start. OFF by default (owner
    # 2026-09-27): deletion inside WSL is final, a full disk is
    # recoverable, so the sweep runs only when the file says true. With
    # it off the GUI warns instead when the runs root passes
    # cleanup_max_gb (env.start_disk_warning).
    auto_cleanup=False,
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
    #: OUT-1: the Run tab's "Runs folder"; every run writes into
    #: <runs_dir>\<MODEL>\ (docs/model-folder-and-vtk-plan.md sec. 2.1)
    runs_dir='',
)


def default_path():
    """`<repo>\\settings.json`, beside the `blastlab/` package (P0-5)."""
    return os.path.join(REPO_ROOT, 'settings.json')


def config_path():
    """BLASTLAB_SETTINGS when set (tests), else `default_path()`."""
    override = os.environ.get('BLASTLAB_SETTINGS')
    if override:
        return override
    return default_path()


def _legacy_sources():
    """Where the settings lived before P0-5, in the order the migration
    tries them: the Store-Python virtual copy of `%APPDATA%` (the file
    the app actually read; newest mtime first if several), then the
    real `%APPDATA%\\blastlab\\settings.json` (`~/.config` elsewhere)."""
    out = []
    local = os.environ.get('LOCALAPPDATA')
    if local:
        pattern = os.path.join(
            local, 'Packages', 'PythonSoftwareFoundation.Python.3*_*',
            'LocalCache', 'Roaming', 'blastlab', 'settings.json')
        found = glob.glob(pattern)
        found.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        out += found
    base = os.environ.get('APPDATA') or os.path.join(
        os.path.expanduser('~'), '.config')
    out.append(os.path.join(base, 'blastlab', 'settings.json'))
    return out


def _migrate(target):
    """Seed `target` once from the first readable legacy settings dict,
    with `auto_cleanup` forced off. Returns the new dict, or None when
    there was no source. Never writes, renames or deletes a source."""
    for src in _legacy_sources():
        try:
            with open(src, encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        data = dict(data)
        # the sweep deletes WSL runs: never carry it across switched on
        data['auto_cleanup'] = False
        data['migrated_from'] = src
        if os.path.exists(target):          # someone else got there first
            return None
        save(data, target)
        print(f'[blastlab] settings: created {target} from {src} '
              f'(auto_cleanup forced off)', file=sys.stderr)
        return data
    return None


def load(path=None):
    """DEFAULTS updated with whatever the file holds.

    A missing or unreadable file gives the defaults, with `auto_cleanup`
    forced False. Since 2026-09-27 that is also the default, so the
    force is a second lock rather than an exception; it predates the
    default change and stays. The sweep deletes run directories,
    and a settings file we could not read means nobody has told us
    anything about this machine - `cleanup_max_gb = 20` is then a policy
    the user has never seen, applied to data they may care about very
    much. Turning it on needs a file that says so.

    This is not hypothetical. Every test and harness "protects" the real
    settings by pointing BLASTLAB_SETTINGS at a throwaway path, which
    does not exist - so each one built a GUI that swept the corpus to
    20 GB, keeping 3 runs, which is harsher than the real app with the
    user's own 150 GB / 10-run policy would ever have been.

    P0-5: reading the repo file (BLASTLAB_SETTINGS unset) when it does
    not exist yet runs the one-time migration first - see the module
    docstring. Under the test override it never runs.
    """
    path = path or config_path()
    if (not os.environ.get('BLASTLAB_SETTINGS')
            and os.path.normcase(os.path.abspath(path))
            == os.path.normcase(os.path.abspath(default_path()))
            and not os.path.exists(path)):
        _migrate(path)
    out = dict(DEFAULTS)
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            out.update(data)
            return out
    except (OSError, ValueError):
        pass
    out['auto_cleanup'] = False
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
