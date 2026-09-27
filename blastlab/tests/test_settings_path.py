"""P0-5: the settings file lives in the repo, and cleanup has a dry run.

- `settings.default_path()` is `<repo>\\settings.json`; `config_path()`
  is BLASTLAB_SETTINGS when set, `default_path()` otherwise.
- The one-time migration seeds the repo file from the Store-Python
  virtual copy (or `%APPDATA%`), forces `auto_cleanup` off, names its
  source, and never touches the source or an existing repo file.

Every case runs in a sandbox: the repo root, LOCALAPPDATA and APPDATA
point at a temp dir, so no check can read or write the owner's files.
No WSL, no GUI.

Run:  cd blastlab/tests && python test_settings_path.py
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from blastlab.core import settings                              # noqa: E402

FAILS = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAILS.append(name)


@contextlib.contextmanager
def sandbox(override=None):
    """A temp dir holding `root\\blastlab\\`, `local\\` and `appdata\\`;
    settings.REPO_ROOT, LOCALAPPDATA and APPDATA point into it, and
    BLASTLAB_SETTINGS is `override` (None = unset). Everything is put
    back afterwards. REPO_ROOT moves first and returns last, so the real
    repo is never the default path while the override is unset."""
    tmp = tempfile.mkdtemp(prefix='blastlab_settings_')
    root = os.path.join(tmp, 'root')
    os.makedirs(os.path.join(root, 'blastlab'))
    saved_root = settings.REPO_ROOT
    saved_env = {k: os.environ.get(k)
                 for k in ('BLASTLAB_SETTINGS', 'LOCALAPPDATA', 'APPDATA')}
    settings.REPO_ROOT = root
    try:
        os.environ['LOCALAPPDATA'] = os.path.join(tmp, 'local')
        os.environ['APPDATA'] = os.path.join(tmp, 'appdata')
        if override is None:
            os.environ.pop('BLASTLAB_SETTINGS', None)
        else:
            os.environ['BLASTLAB_SETTINGS'] = override
        yield tmp
    finally:
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        settings.REPO_ROOT = saved_root
        shutil.rmtree(tmp, ignore_errors=True)


def virtual_copy(tmp):
    """The Store-Python virtual settings path inside the sandbox."""
    return os.path.join(tmp, 'local', 'Packages',
                        'PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0',
                        'LocalCache', 'Roaming', 'blastlab', 'settings.json')


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


def read_bytes(path):
    with open(path, 'rb') as f:
        return f.read()


def load_quiet():
    """settings.load() with its stderr captured: (dict, stderr text)."""
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        got = settings.load()
    return got, err.getvalue()


# ── P0-5 items 1, 2, 5: the path and the migration ──────────────────────────

def test_default_path():
    print('\n(a) default_path')
    with sandbox() as tmp:
        root = os.path.join(tmp, 'root')
        p = settings.default_path()
        check('(a) default_path() is <root>\\settings.json',
              p == os.path.join(root, 'settings.json'), p)
        check('(a) <root> holds the blastlab package',
              os.path.isdir(os.path.join(os.path.dirname(p), 'blastlab')))
        check('(a) config_path() == default_path() without the override',
              settings.config_path() == p, settings.config_path())
    # the real module: the repo is the parent of the package directory
    pkg = os.path.dirname(os.path.dirname(os.path.abspath(
        settings.__file__)))
    check('(a) real REPO_ROOT is the parent of blastlab/',
          os.path.normcase(settings.REPO_ROOT)
          == os.path.normcase(os.path.dirname(pkg))
          and os.path.basename(pkg) == 'blastlab', settings.REPO_ROOT)


def test_migrate_from_virtual_copy():
    print('\n(b) migration from the Store-Python virtual copy')
    with sandbox() as tmp:
        src = virtual_copy(tmp)
        runs = os.path.join(tmp, 'runs')
        source = dict(auto_cleanup=True, cleanup_max_gb=150.0,
                      cleanup_keep_recent=10, runs_dir=runs,
                      appearance='light')
        write_json(src, source)
        # an %APPDATA% file too: the virtual copy must win
        write_json(os.path.join(tmp, 'appdata', 'blastlab', 'settings.json'),
                   dict(auto_cleanup=False, cleanup_max_gb=1.0))
        before = read_bytes(src)
        os.utime(src, (1_000_000_000, 1_000_000_000))
        mtime = os.path.getmtime(src)
        got, err = load_quiet()
        target = settings.default_path()
        check('(b) the repo file was created', os.path.isfile(target))
        with open(target, encoding='utf-8') as f:
            made = json.load(f)
        check('(b) auto_cleanup forced False in the file',
              made.get('auto_cleanup') is False, str(made))
        check('(b) auto_cleanup False in what load() returns',
              got.get('auto_cleanup') is False, str(got))
        others = {k: v for k, v in source.items() if k != 'auto_cleanup'}
        check('(b) every other source key identical',
              all(made.get(k) == v for k, v in others.items()), str(made))
        check('(b) migrated_from names the source',
              made.get('migrated_from') == src, str(made.get('migrated_from')))
        check('(b) no key beyond the source + migrated_from',
              set(made) == set(source) | {'migrated_from'}, str(set(made)))
        check('(b) source bytes unchanged', read_bytes(src) == before)
        check('(b) source mtime unchanged', os.path.getmtime(src) == mtime)
        check('(b) the stderr line names the target and the source',
              f'created {target} from {src} (auto_cleanup forced off)'
              in err, repr(err))
        # a second load finds the file and does not migrate again
        again, err2 = load_quiet()
        check('(b) the second load does not migrate again',
              err2 == '' and again == got, repr(err2))


def test_migrate_from_appdata():
    print('\n(c) migration from %APPDATA%')
    with sandbox() as tmp:
        src = os.path.join(tmp, 'appdata', 'blastlab', 'settings.json')
        write_json(src, dict(auto_cleanup=True, cleanup_max_gb=33.0))
        got, err = load_quiet()
        target = settings.default_path()
        check('(c) the repo file was seeded from %APPDATA%',
              os.path.isfile(target) and src in err, repr(err))
        with open(target, encoding='utf-8') as f:
            made = json.load(f)
        check('(c) values carried, cleanup off',
              made.get('cleanup_max_gb') == 33.0
              and made.get('auto_cleanup') is False
              and made.get('migrated_from') == src, str(made))
        check('(c) load() agrees with the file',
              got.get('cleanup_max_gb') == 33.0
              and got.get('auto_cleanup') is False, str(got))


def test_no_source():
    print('\n(d) no source')
    with sandbox() as tmp:
        # an unreadable source is skipped, not taken
        bad = os.path.join(tmp, 'appdata', 'blastlab', 'settings.json')
        os.makedirs(os.path.dirname(bad))
        with open(bad, 'w', encoding='utf-8') as f:
            f.write('{not json')
        got, err = load_quiet()
        check('(d) no file created', not os.path.exists(
            settings.default_path()))
        check('(d) load() auto_cleanup is False',
              got.get('auto_cleanup') is False, str(got))
        check('(d) nothing said on stderr', err == '', repr(err))


def test_override_never_migrates():
    print('\n(e) BLASTLAB_SETTINGS set')
    tmp_over = tempfile.mkdtemp(prefix='blastlab_override_')
    over = os.path.join(tmp_over, 'settings.json')
    try:
        with sandbox(override=over) as tmp:
            write_json(virtual_copy(tmp), dict(auto_cleanup=True))
            root = os.path.join(tmp, 'root')
            before = sorted(os.listdir(root))
            got, err = load_quiet()
            check('(e) config_path() is the override',
                  settings.config_path() == over, settings.config_path())
            check('(e) nothing created under <root>',
                  sorted(os.listdir(root)) == before, str(os.listdir(root)))
            check('(e) the override file is not created either',
                  not os.path.exists(over))
            check('(e) no migration line', err == '', repr(err))
            check('(e) a missing override reads cleanup off',
                  got.get('auto_cleanup') is False, str(got))
    finally:
        shutil.rmtree(tmp_over, ignore_errors=True)


def test_existing_file_untouched():
    print('\n(f) an existing repo file')
    with sandbox() as tmp:
        write_json(virtual_copy(tmp), dict(auto_cleanup=False,
                                           cleanup_max_gb=99.0))
        target = settings.default_path()
        raw = b'{\n  "auto_cleanup": true,\n  "cleanup_max_gb": 7.0\n}\n'
        with open(target, 'wb') as f:
            f.write(raw)
        got, err = load_quiet()
        check('(f) the repo file is byte-identical', read_bytes(target) == raw)
        check('(f) it is what load() returns (no migration)',
              got.get('cleanup_max_gb') == 7.0
              and got.get('auto_cleanup') is True and err == '',
              str(got) + repr(err))


def test_unwritable_root():
    print('\n(h) a repo root that cannot be written')
    with sandbox() as tmp:
        src = virtual_copy(tmp)
        write_json(src, dict(auto_cleanup=True, cleanup_max_gb=150.0))
        before = read_bytes(src)
        # the root's parent is a FILE, so save() cannot create anything
        blocker = os.path.join(tmp, 'blocker')
        with open(blocker, 'w', encoding='utf-8') as f:
            f.write('not a directory')
        settings.REPO_ROOT = os.path.join(blocker, 'root')
        got, err = load_quiet()
        check('(h) no file claimed: no "created" line',
              'created' not in err, repr(err))
        check('(h) load() still reads cleanup off',
              got.get('auto_cleanup') is False, str(got))
        check('(h) nothing written, the source untouched',
              not os.path.exists(settings.default_path())
              and read_bytes(src) == before)


def test_tk_and_qt_share_the_path():
    print('\n(g) one path for Tk and Qt')
    from blastlab.gui import settings as gui_settings
    check('(g) gui.settings.config_path is core.settings.config_path',
          gui_settings.config_path() == settings.config_path())
    check('(g) gui.settings re-exports default_path',
          gui_settings.default_path is settings.default_path)
    with sandbox():
        check('(g) ... and both resolve to the repo file',
              gui_settings.config_path() == settings.default_path())


# ── P0-5 item 3: cleanup_plan, the dry run auto_cleanup is built on ─────────

GB = 1024 ** 3
DAY = 86400.0
NOW = 2_000_000_000.0
ROOT = '/root/blastlab_runs'


def fake_runs():
    """{dir: (bytes, mtime, alive)}: an alive run and an unknown one (both
    old - only their state protects them), two old finished runs, and
    three fresh ones that `cleanup_keep_recent = 3` protects anyway.
    15 GB in all, under the 20 GB default, so only age decides."""
    return {
        f'{ROOT}/old_a': (4 * GB, NOW - 30 * DAY, False),
        f'{ROOT}/alive': (2 * GB, NOW - 25 * DAY, True),
        f'{ROOT}/old_b': (3 * GB, NOW - 20 * DAY, False),
        f'{ROOT}/unknown': (3 * GB, NOW - 18 * DAY, None),
        f'{ROOT}/fresh_1': (1 * GB, NOW - 3 * DAY, False),
        f'{ROOT}/fresh_2': (1 * GB, NOW - 2 * DAY, False),
        f'{ROOT}/fresh_3': (1 * GB, NOW - 1 * DAY, False),
    }


@contextlib.contextmanager
def stub_wsl(runs, delete=None):
    """Replace env's four WSL touch points. `delete` None = raise if
    called. Yields the call log {name: count} and the deleted lists."""
    from blastlab.solvers.foam import env
    calls = dict(run_dirs=0, run_info=0, runs_alive=0, delete_runs=0)
    deleted = []

    def run_dirs():
        calls['run_dirs'] += 1
        return sorted(runs)

    def run_info(dirs=None, timeout=None):
        calls['run_info'] += 1
        return {d: dict(bytes=int(runs[d][0]), mtime=int(runs[d][1]))
                for d in (dirs or runs)}

    def runs_alive(dirs=None, timeout=None):
        calls['runs_alive'] += 1
        return {d: runs[d][2] for d in (dirs or runs)}

    def delete_runs(dirs, timeout=300):
        calls['delete_runs'] += 1
        if delete is None:
            raise AssertionError('delete_runs called by a dry run')
        deleted.append(list(dirs))
        return delete

    saved = {k: getattr(env, k) for k in calls}
    env.run_dirs, env.run_info = run_dirs, run_info
    env.runs_alive, env.delete_runs = runs_alive, delete_runs
    try:
        yield calls, deleted
    finally:
        for k, v in saved.items():
            setattr(env, k, v)


def test_cleanup_plan_dry_run():
    print('\ncleanup_plan: the dry run')
    from blastlab.solvers.foam import env
    runs = fake_runs()
    with stub_wsl(runs) as (calls, _deleted):
        try:
            plan = env.cleanup_plan(dict(auto_cleanup=False,
                                         cleanup_max_age_days=14), now=NOW)
            err = None
        except Exception as exc:                   # noqa: BLE001
            plan, err = [], exc
        check('plan: does not raise (delete_runs never called)',
              err is None and calls['delete_runs'] == 0, repr(err))
        check('plan: the two old, non-alive runs, oldest first',
              [r['dir'] for r in plan]
              == [f'{ROOT}/old_a', f'{ROOT}/old_b'], str(plan))
        check('plan: names, bytes and mtimes carried',
              [(r['name'], r['bytes'], r['mtime']) for r in plan]
              == [('old_a', 4 * GB, int(NOW - 30 * DAY)),
                  ('old_b', 3 * GB, int(NOW - 20 * DAY))], str(plan))
        check('plan: the flag is ignored (on gives the same list)',
              env.cleanup_plan(dict(auto_cleanup=True,
                                    cleanup_max_age_days=14), now=NOW)
              == plan)
    with stub_wsl({}) as (calls, _deleted):
        check('plan: no runs -> []', env.cleanup_plan({}, now=NOW) == [])
    with stub_wsl(runs) as (calls, _deleted):
        env.run_info = lambda dirs=None, timeout=None: {}
        check('plan: WSL unreachable (no info) -> []',
              env.cleanup_plan({}, now=NOW) == [])


def test_auto_cleanup_on_the_plan():
    print('\nauto_cleanup is built on cleanup_plan')
    from blastlab.solvers.foam import env
    runs = fake_runs()
    cfg = dict(auto_cleanup=True, cleanup_max_age_days=14)
    with stub_wsl(runs) as (_c, _d):
        plan = env.cleanup_plan(cfg, now=NOW)
    logs = []
    with stub_wsl(runs, delete=True) as (calls, deleted):
        got = env.auto_cleanup(cfg, log=logs.append, now=NOW)
    check('sweep: deletes exactly the plan, once',
          deleted == [[r['dir'] for r in plan]], str(deleted))
    check('sweep: returns (2, their bytes)',
          got == (2, 7 * GB), str(got))
    check('sweep: log line unchanged in form',
          logs == ['  [blastfoam] run-dir cleanup: removed 2 old run(s), '
                   '7.0 GB (5 kept)'], str(logs))
    logs = []
    with stub_wsl(runs, delete=False) as (calls, deleted):
        got = env.auto_cleanup(cfg, log=logs.append, now=NOW)
    check('sweep: WSL refusing the delete -> (0, 0) and says so',
          got == (0, 0) and logs == ['  [blastfoam] run-dir cleanup: WSL '
                                     'did not delete 2 old run(s)'],
          str((got, logs)))
    with stub_wsl(runs, delete=True) as (calls, deleted):
        got = env.auto_cleanup(dict(auto_cleanup=False), now=NOW)
    check('sweep off: (0, 0) and none of the four stubs called',
          got == (0, 0) and not any(calls.values()), str(calls))


# ── owner 2026-09-27 (Q3): cleanup off by default, a disk warning instead ──

def test_default_is_off():
    print('\nauto_cleanup defaults to off')
    from blastlab.solvers.foam import env
    check('DEFAULTS auto_cleanup is False',
          settings.DEFAULTS['auto_cleanup'] is False)
    with stub_wsl(fake_runs(), delete=True) as (calls, deleted):
        got = env.auto_cleanup({}, now=NOW)
    check('a settings dict without the key does not sweep',
          got == (0, 0) and not any(calls.values()), str(calls))
    with sandbox() as tmp:
        target = settings.default_path()
        with open(target, 'w', encoding='utf-8') as f:
            f.write('{}')
        check('a file without the key loads cleanup off',
              settings.load()['auto_cleanup'] is False)


def _warn_run(cfg, runs, **kw):
    """start_disk_warning with the WSL stubs; (warnings, stub calls,
    thread or None)."""
    from blastlab.solvers.foam import env
    got = []
    with stub_wsl(runs) as (calls, _deleted):
        th = env.start_disk_warning(cfg, got.append, **kw)
        if th is not None:
            th.join(10)
    return got, calls, th


def test_disk_warning():
    print('\nthe disk warning (sweep off)')
    from blastlab.solvers.foam import env
    text = env.disk_warning_text(15 * GB, 10, 2, 7 * GB)
    check('text: size, limit, the plan and the CLI',
          '15.0 GB' in text and 'the 10 GB limit' in text
          and 'would delete 2 runs (7.0 GB)' in text
          and 'nothing was deleted' in text
          and '--clean-foam-runs' in text, text)
    long_text = env.disk_warning_text(12345 * GB, 1000, 999, 9999 * GB)
    check('text fits the 200-character status line of both GUIs',
          len(long_text) <= 200, f'{len(long_text)} chars')
    check('text: one run is singular',
          'would delete 1 run (' in env.disk_warning_text(GB, 0.5, 1, GB))
    runs = fake_runs()                                   # 15 GB in all
    over = dict(auto_cleanup=False, cleanup_max_gb=10,
                cleanup_max_age_days=14)
    got, calls, _th = _warn_run(over, runs, private_ok=True)
    check('over the limit: exactly one warning',
          len(got) == 1 and got[0] == env.disk_warning_text(
              15 * GB, 10, 2, 7 * GB), str(got))
    check('over the limit: delete_runs never called (the stub raises)',
          calls['delete_runs'] == 0, str(calls))
    check('over the limit: one du round trip',
          calls['run_info'] == 1 and calls['run_dirs'] == 1, str(calls))
    under = dict(over, cleanup_max_gb=20)
    got, calls, _th = _warn_run(under, runs, private_ok=True)
    check('under the limit: no warning, no liveness probe',
          got == [] and calls['runs_alive'] == 0, str((got, calls)))
    got, calls, _th = _warn_run(dict(over, auto_cleanup=True), runs,
                                private_ok=True)
    check('sweep on: no warning and no WSL (the sweep is the answer)',
          got == [] and not any(calls.values()), str((got, calls)))
    # WSL unreachable: no info, or a probe that raises
    with stub_wsl(runs) as (calls, _deleted):
        env.run_info = lambda dirs=None, timeout=None: {}
        got = []
        env.start_disk_warning(over, got.append, private_ok=True).join(10)
    check('WSL unreachable (no info): no warning', got == [], str(got))

    def boom():
        raise OSError('wsl is gone')
    err = io.StringIO()
    with stub_wsl(runs) as (calls, _deleted), contextlib.redirect_stderr(err):
        env.run_dirs = boom
        got = []
        th = env.start_disk_warning(over, got.append, private_ok=True)
        th.join(10)
    check('WSL error: no warning, and the thread ends quietly',
          got == [] and not th.is_alive(), str(got))
    check('WSL error: not swallowed - one stderr line names it',
          err.getvalue() == '[blastlab] disk warning skipped: '
                            'OSError: wsl is gone\n', repr(err.getvalue()))
    # a private settings file (tests, harnesses) never starts it
    saved = os.environ.get('BLASTLAB_SETTINGS')
    os.environ['BLASTLAB_SETTINGS'] = os.path.join(
        tempfile.gettempdir(), 'blastlab_never_written.json')
    try:
        got, calls, th = _warn_run(over, runs)
    finally:
        if saved is None:
            os.environ.pop('BLASTLAB_SETTINGS', None)
        else:
            os.environ['BLASTLAB_SETTINGS'] = saved
    check('private settings: no thread, no WSL touched',
          th is None and got == [] and not any(calls.values()), str(calls))


def test_disk_warning_sinks():
    print('\nthe GUI sinks: a log line and a status warning, nothing modal')
    from types import SimpleNamespace
    posted, logged = [], []
    from blastlab.ui.app import MainWindow
    qt = SimpleNamespace(_log_threadsafe=logged.append,
                         bridge=SimpleNamespace(
                             post=lambda fn, *a: posted.append((fn, a))),
                         notify='NOTIFY')
    MainWindow._disk_warning(qt, 'W')
    check('Qt: one log line and one status warning via the bridge',
          logged == ['  [blastfoam] W'] and posted == [('NOTIFY', ('W',
                                                                   'warn'))],
          str((logged, posted)))
    from blastlab.gui.app import App
    after, logged = [], []
    tk = SimpleNamespace(_log_threadsafe=logged.append, notify='NOTIFY',
                         root=SimpleNamespace(
                             after=lambda ms, fn, *a: after.append(
                                 (ms, fn, a))))
    App._disk_warning(tk, 'W')
    check('Tk: one log line and one status warning via after()',
          logged == ['  [blastfoam] W']
          and after == [(0, 'NOTIFY', ('W', 'warn'))], str((logged, after)))


TESTS = [test_default_path, test_migrate_from_virtual_copy,
         test_migrate_from_appdata, test_no_source,
         test_override_never_migrates, test_existing_file_untouched,
         test_unwritable_root, test_tk_and_qt_share_the_path,
         test_cleanup_plan_dry_run, test_auto_cleanup_on_the_plan, test_default_is_off,
         test_disk_warning, test_disk_warning_sinks]


if __name__ == '__main__':
    for fn in TESTS:
        fn()
    print()
    print('SETTINGS PATH: ' + ('PASS' if not FAILS else
                               f'FAIL ({len(FAILS)}): ' + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)
