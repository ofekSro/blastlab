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


TESTS = [test_default_path, test_migrate_from_virtual_copy,
         test_migrate_from_appdata, test_no_source,
         test_override_never_migrates, test_existing_file_untouched,
         test_tk_and_qt_share_the_path]


if __name__ == '__main__':
    for fn in TESTS:
        fn()
    print()
    print('SETTINGS PATH: ' + ('PASS' if not FAILS else
                               f'FAIL ({len(FAILS)}): ' + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)
