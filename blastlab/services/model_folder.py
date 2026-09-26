"""The model folder: where every file a run produces lands (OUT-1).

docs/model-folder-and-vtk-plan.md section 2 (owner decisions 8-12, 14,
2026-09-26). A run needs a runs folder and a model name before it
starts, and writes everything into `<runs_dir>\\<MODEL>\\`.

This module knows no GUI toolkit, no pyplot and no VTK. The name rule and
the folder check are pure; the GUIs and the CLI show the messages.

What lands in the folder (plan sec. 2.2), in the order `write_all`
writes it: MODEL.json, the files the run stage wrote itself (gauge TSV,
animation, profile, trigger remap), the gauge summary, figures\\,
fields\\, report.html, and last manifest.json. run.log fills while the
run runs (`RunHooks.log_file`).
"""

import copy
import datetime
import json
import os
import shutil
import stat
from types import SimpleNamespace

#: the longest model name accepted (plan sec. 2.1)
NAME_MAX = 100

#: characters Windows refuses in a file or folder name
FORBIDDEN_CHARS = '\\/:*?"<>|'

#: reserved device names: refused with or without an extension
#: ('con.txt' is the device CON too), in any letter case
RESERVED_NAMES = frozenset(
    ['CON', 'PRN', 'AUX', 'NUL']
    + [f'COM{i}' for i in range(1, 10)]
    + [f'LPT{i}' for i in range(1, 10)])


class ModelFolderError(Exception):
    """The model folder could not be prepared or written. The message
    carries the OS text, e.g. the file another program holds open."""


def validate_name(name):
    """None when `name` (trimmed) is a valid model folder name, else the
    reason it is not. Trimmed; non-empty; at most NAME_MAX characters; no
    `\\ / : * ? " < > |` and no control characters; no trailing dot or
    space; not a reserved device name (plan sec. 2.1)."""
    name = str(name or '').strip()
    if not name:
        return 'the name is empty'
    if len(name) > NAME_MAX:
        return (f'at most {NAME_MAX} characters (this one has '
                f'{len(name)})')
    bad = sorted({c for c in name if c in FORBIDDEN_CHARS})
    if bad:
        return ('a folder name cannot contain '
                + ' '.join(bad))
    if any(ord(c) < 32 for c in name):
        return 'a folder name cannot contain control characters'
    if name[-1] in '. ':
        return 'a folder name cannot end with a dot or a space'
    stem = name.split('.', 1)[0].rstrip(' ').upper()
    if stem in RESERVED_NAMES:
        return f'"{stem}" is a reserved Windows device name'
    return None


def _norm(path):
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


def _desktop_roots():
    """The Desktop folders a runs folder must never be (CLAUDE.md 8.5):
    ~\\Desktop and the OneDrive-redirected ones."""
    roots = [os.path.join(os.path.expanduser('~'), 'Desktop')]
    for var in ('OneDrive', 'OneDriveCommercial', 'OneDriveConsumer'):
        base = os.environ.get(var)
        if base:
            roots.append(os.path.join(base, 'Desktop'))
    return {_norm(r) for r in roots}


def check(runs_dir, model):
    """Everything wrong with (runs folder, model name), as messages that
    each name the box they are about. [] means a run may start."""
    errors = []
    runs_dir = str(runs_dir or '').strip()
    if not runs_dir:
        errors.append('Runs folder is empty')
    elif not os.path.isdir(runs_dir):
        errors.append(f'Runs folder does not exist: {runs_dir}')
    elif _norm(runs_dir) in _desktop_roots():
        # the Desktop holds the owner's thesis data; an overwrite there
        # deletes a folder of it (plan risk 1, CLAUDE.md 8.5)
        errors.append(f'Runs folder cannot be the Desktop itself: '
                      f'{runs_dir}')
    why = validate_name(model)
    if why:
        errors.append(f'Model name: {why}')
    return errors


def folder_for(runs_dir, model):
    """`<runs_dir>\\<model>` for a trimmed name. An existing folder whose
    name differs only in letter case IS this model on Windows, so its own
    spelling is returned."""
    name = str(model or '').strip()
    runs_dir = str(runs_dir or '').strip()
    try:
        entries = os.listdir(runs_dir)
    except OSError:
        entries = []
    for entry in entries:
        if entry.casefold() == name.casefold():
            return os.path.join(runs_dir, entry)
    return os.path.join(runs_dir, name)


# ── the names of plan sec. 2.2 ───────────────────────────────────────────
CASE_FILE = 'MODEL.json'
LOG_FILE = 'run.log'
MANIFEST_FILE = 'manifest.json'
REPORT_FILE = 'report.html'
GAUGES_DIR = 'gauges'
FIGURES_DIR = 'figures'
FIELDS_DIR = 'fields'

#: the case keys that name a file. MODEL.json writes them relative to
#: itself, so the folder can move (load_case resolves profile_file_in)
PATH_KEYS = ('gauge_file', 'anim_file', 'profile_file', 'trigger_file',
             'profile_file_in')

#: why a row of sec. 2.2 is absent: the Results tab's `why_not` texts
WHY_NO_ANIMATION = 'replay frames were not recorded'
WHY_NO_PROFILE = '3D / planar 2D has no profile export'
WHY_NO_GAUGES = 'the case has no gauges'
WHY_NO_SNAPSHOTS = 'this result has no field snapshots'
WHY_NO_FIELDS = 'this result has no field maps'


def now_iso():
    """Local time, ISO-8601 to the second (the manifest's stamps)."""
    return datetime.datetime.now().isoformat(timespec='seconds')


# ── prepare: create, or overwrite after a confirmation ───────────────────
def overwrite_text(runs_dir, model):
    """The confirmation question for an existing model (plan sec. 2.1)."""
    return (f'{str(model).strip()} already exists in '
            f'{str(runs_dir).strip()}. Overwrite? The previous run\'s '
            f'files will be deleted.')


def _retry_writable(func, path, exc):
    """rmtree `onexc`: clear a read-only attribute and retry once. Any
    other failure (a file another program holds open) propagates."""
    if isinstance(exc, PermissionError) and os.path.exists(path) \
            and not os.access(path, os.W_OK):
        os.chmod(path, stat.S_IWRITE)
        func(path)
        return
    raise exc


def prepare(runs_dir, model, confirm):
    """The empty model folder for a run, or None when the user declined.

    Absent: created. Present: `confirm(overwrite_text(...))` is asked;
    yes deletes it and creates it again, no returns None with nothing
    touched. A folder that cannot be deleted (a file open in ParaView)
    raises ModelFolderError with the OS text, and nothing is recreated.

    Guards (batch plan risk 1): the inputs must pass `check`, and the
    target must be a direct child of the runs folder - never the runs
    folder itself, never outside it, never a link."""
    errors = check(runs_dir, model)
    if errors:
        raise ModelFolderError('\n'.join(errors))
    runs_dir = str(runs_dir).strip()
    target = folder_for(runs_dir, model)
    parent, t = _norm(runs_dir), _norm(target)
    if t == parent or os.path.dirname(t) != parent:
        raise ModelFolderError(f'Model name: {target} is not a folder '
                               f'inside {runs_dir}')
    if os.path.lexists(target):
        if os.path.islink(target) or os.path.isjunction(target) \
                or not os.path.isdir(target):
            raise ModelFolderError(f'{target} exists and is not a plain '
                                   f'folder - not deleting it')
        if not confirm(overwrite_text(runs_dir, model)):
            return None
        try:
            shutil.rmtree(target, onexc=_retry_writable)
        except OSError as exc:
            raise ModelFolderError(
                f'Could not delete the previous run in {target}: {exc}'
            ) from exc
    try:
        os.makedirs(target)
    except OSError as exc:
        raise ModelFolderError(f'Could not create {target}: {exc}') from exc
    return target


# ── binding a case to its folder ─────────────────────────────────────────
def anim_ext(anim_file):
    """The animation's extension: the case's own .gif / .mp4 choice
    (owner Q1: the format choice stays visible), else what this machine
    can write."""
    ext = os.path.splitext(str(anim_file or ''))[1].lower()
    if ext in ('.gif', '.mp4'):
        return ext
    from ..output.animation import default_ext
    return default_ext()


def has_profile(case):
    """1D and axisymmetric 2D have a profile export (exports.can)."""
    return case.dim == 1 or (case.dim == 2 and getattr(
        case, 'geometry', None) == 'axisymmetric')


def bind_case(case, stage_dir):
    """A copy of `case` whose output files are the sec. 2.2 names inside
    `stage_dir` (absolute paths), so the run stage writes them there and
    not into the working directory. Creates `stage_dir\\gauges`.

    gauge_file -> gauges\\gauges_<d>d.txt; anim_file -> animation.<ext>;
    profile_file -> profile.txt (1D) / profile_2d.npz (axisymmetric 2D),
    None where there is no profile export; trigger_file (2D) ->
    trigger_remap.npz. A chain hand-off overrides profile_file afterwards
    (Step 6)."""
    bound = copy.deepcopy(case)
    dim = case.dim
    os.makedirs(os.path.join(stage_dir, GAUGES_DIR), exist_ok=True)
    bound.gauge_file = os.path.join(stage_dir, GAUGES_DIR,
                                    f'gauges_{dim}d.txt')
    if dim > 1:
        bound.anim_file = os.path.join(
            stage_dir, 'animation' + anim_ext(case.anim_file))
    if dim == 1:
        bound.profile_file = os.path.join(stage_dir, 'profile.txt')
    elif dim == 2:
        bound.profile_file = (os.path.join(stage_dir, 'profile_2d.npz')
                              if has_profile(case) else None)
        bound.trigger_file = os.path.join(stage_dir, 'trigger_remap.npz')
    return bound


def _inside(path, root):
    try:
        return os.path.commonpath([_norm(path), _norm(root)]) == _norm(root)
    except ValueError:                   # another drive
        return False


def relative_case(case, stage_dir, root=None):
    """A copy of `case` with every PATH_KEYS path under `root` (default:
    `stage_dir`) written relative to `stage_dir`, with '/' separators.
    Paths elsewhere stay as they are."""
    root = root or stage_dir
    rel = copy.deepcopy(case)
    for key in PATH_KEYS:
        value = getattr(rel, key, None)
        if value and os.path.isabs(value) and _inside(value, root):
            setattr(rel, key, os.path.relpath(value, stage_dir)
                    .replace('\\', '/'))
    return rel


# ── the manifest ─────────────────────────────────────────────────────────
def _repo_root():
    here = os.path.dirname(os.path.abspath(__file__))       # .../services
    return os.path.dirname(os.path.dirname(here))


def git_commit(repo=None):
    """The short commit hash of the checkout, read from the .git files
    directly: git is not on PATH (CLAUDE.md 3, batch plan D9). A worktree's
    .git is a `gitdir:` file, and its branch refs live in the common dir.
    None when nothing can be read."""
    try:
        dot = os.path.join(repo or _repo_root(), '.git')
        if os.path.isfile(dot):
            with open(dot, encoding='utf-8') as f:
                line = f.read().strip()
            if not line.startswith('gitdir:'):
                return None
            gitdir = line[len('gitdir:'):].strip()
            if not os.path.isabs(gitdir):
                gitdir = os.path.join(os.path.dirname(dot), gitdir)
        else:
            gitdir = dot
        common = gitdir
        cfile = os.path.join(gitdir, 'commondir')
        if os.path.isfile(cfile):
            with open(cfile, encoding='utf-8') as f:
                common = os.path.normpath(os.path.join(gitdir,
                                                       f.read().strip()))
        with open(os.path.join(gitdir, 'HEAD'), encoding='utf-8') as f:
            head = f.read().strip()
        if not head.startswith('ref:'):
            return head[:7] or None                     # detached HEAD
        ref = head[4:].strip()
        for base in (gitdir, common):
            path = os.path.join(base, *ref.split('/'))
            if os.path.isfile(path):
                with open(path, encoding='utf-8') as f:
                    return f.read().strip()[:7] or None
        packed = os.path.join(common, 'packed-refs')
        if os.path.isfile(packed):
            with open(packed, encoding='utf-8') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) == 2 and parts[1] == ref:
                        return parts[0][:7]
    except OSError:
        pass
    return None


def list_outputs(stage_dir):
    """[{'path': 'gauges/gauges_2d.txt', 'bytes': n}, ...]: every file in
    the folder except manifest.json, sorted, '/' separators."""
    out = []
    for root, dirs, files in os.walk(stage_dir):
        dirs.sort()
        for name in sorted(files):
            full = os.path.join(root, name)
            rel = os.path.relpath(full, stage_dir).replace('\\', '/')
            if rel == MANIFEST_FILE:
                continue
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            out.append(dict(path=rel, bytes=size))
    return out


def write_manifest(manifest, stage_dir):
    """manifest.json, UTF-8, LF. Returns an error text or None."""
    try:
        with open(os.path.join(stage_dir, MANIFEST_FILE), 'w',
                  encoding='utf-8', newline='\n') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
            f.write('\n')
    except (OSError, TypeError, ValueError) as exc:
        return str(exc) or type(exc).__name__
    return None


def new_manifest(case, dim, stage_dir, run_info=None):
    """The manifest's head, keys in the order of plan sec. 2.2, plus
    `failed` (additive). `run_info` may carry model, runs_dir, created,
    n_cells, n_procs, n_steps; model / runs_dir default to the folder's
    own name and parent."""
    info = run_info or {}
    return dict(
        model=info.get('model') or os.path.basename(
            os.path.normpath(stage_dir)),
        runs_dir=info.get('runs_dir') or os.path.dirname(
            os.path.normpath(stage_dir)),
        created=info.get('created') or now_iso(),
        finished=None,
        solver=getattr(case, 'solver', 'native'),
        dim=dim,
        case_file=CASE_FILE,
        git_commit=git_commit(),
        stop_reason=info.get('stop_reason'),
        n_cells=info.get('n_cells'),
        n_procs=info.get('n_procs'),
        n_steps=info.get('n_steps'),
        wsl_scratch=None,
        outputs=[],
        missing=[],
        vtk=None,
        failed=[])


def _file_problem(path):
    """None when `path` exists with size > 0, else why not."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return 'not written'
    return None if size > 0 else 'empty file'


def _rel_or_abs(path, stage_dir):
    if _inside(path, stage_dir):
        return os.path.relpath(path, stage_dir).replace('\\', '/')
    return path


# ── write_all ────────────────────────────────────────────────────────────
def write_all(res, case, dim, stage_dir, run_info=None, log=print):
    """Write and verify every row of plan sec. 2.2 for one finished run
    stage; return the manifest dict. Runs on the WORKER thread: the 3D
    figures take seconds.

    `case` is the bound case (`bind_case`); `res` its Result, or None
    when the run raised (then only MODEL.json and the manifest). Order:
    MODEL.json (paths relative to the folder), the files the run stage
    already wrote (gauge TSV, animation, profile, trigger remap), then
    the summary, figures, field CSVs and report through
    `services.exports.run_export(..., open_after=False)`, and last
    manifest.json. Every output is checked to exist with size > 0.

    Never raises (the ux(2) rule: a finished solve is never lost to a
    failed write). A failure lands in `manifest['failed']` and the log."""
    info = dict(run_info or {})
    manifest = new_manifest(case, dim, stage_dir, info)
    failed, missing = manifest['failed'], manifest['missing']

    def fail(name, path, why):
        path = _rel_or_abs(path, stage_dir)
        failed.append(dict(name=name, path=path, why=why))
        log(f'[warn] model folder: could not write {name} ({path}): {why}')

    def verify(name, path):
        why = _file_problem(path)
        if why:
            fail(name, path, why)

    # 1. the case exactly as run
    case_path = os.path.join(stage_dir, CASE_FILE)
    try:
        from ..models.case import save_case
        save_case(relative_case(case, stage_dir, info.get('model_dir')),
                  case_path)
    except Exception as exc:
        fail('case', case_path, str(exc) or type(exc).__name__)
    else:
        verify('case', case_path)

    if res is not None:
        try:
            _write_result_rows(res, case, dim, stage_dir, info, log,
                               verify, fail, missing)
        except Exception as exc:        # a bug here must not lose the run
            fail('exports', stage_dir, str(exc) or type(exc).__name__)
        manifest['stop_reason'] = info.get('stop_reason') \
            or res.stop_reason or None

    manifest['outputs'] = list_outputs(stage_dir)
    manifest['finished'] = now_iso()
    why = write_manifest(manifest, stage_dir)
    if why:
        log(f'[warn] model folder: could not write {MANIFEST_FILE}: {why}')
    return manifest


def _write_result_rows(res, case, dim, stage_dir, info, log, verify, fail,
                       missing):
    """The Result's rows of sec. 2.2 (write_all steps 2 and 3)."""
    from . import exports
    meta = res.meta or {}
    has_gauges = bool((res.gauges or {}).get('pressures'))
    frames = bool(meta.get('frames'))

    # 2. what the run stage wrote itself (solvers/jobs.solve_stage)
    if has_gauges and case.gauge_file:
        verify('gauges', case.gauge_file)
    if dim > 1 and frames and case.anim_file:
        path = case.anim_file
        if path.lower().endswith('.mp4') and not os.path.exists(path):
            # write_animation falls back to .gif without ffmpeg
            path = path[:-4] + '.gif'
        verify('animation', path)
    if not frames:
        missing.append(dict(name='animation', why=WHY_NO_ANIMATION))
    if getattr(case, 'profile_file', None):
        verify('profile', case.profile_file)
    elif not has_profile(case):
        missing.append(dict(name='profile', why=WHY_NO_PROFILE))
    if dim == 2 and getattr(case, 'trigger_file', None) \
            and meta.get('trigger_state') is not None:
        verify('trigger remap', case.trigger_file)

    # 3. the exports, exactly as the Results tab writes them
    label = info.get('label') or info.get('model') \
        or os.path.basename(os.path.normpath(stage_dir))
    ent = SimpleNamespace(label=label, display=label, dim=dim, result=res)

    def export(kind, target):
        try:
            return exports.run_export(kind, ent, target, log=log,
                                      open_after=False)
        except Exception as exc:        # run_export logs and returns None
            log(f'Export failed: {exc}')
            return None

    if has_gauges:
        target = os.path.join(stage_dir, GAUGES_DIR,
                              f'gauges_{dim}d_summary.csv')
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if export('summary', target) is None:
            fail('summary', target, 'export failed (see the log)')
        else:
            verify('summary', target)
    else:
        missing.append(dict(name='gauges', why=WHY_NO_GAUGES))

    for kind, sub, why_none in (('pngs', FIGURES_DIR, WHY_NO_SNAPSHOTS),
                                ('fieldcsv', FIELDS_DIR, WHY_NO_FIELDS)):
        name = sub
        if kind == 'pngs' and not res.snapshots:
            missing.append(dict(name=name, why=why_none))
            continue
        target = os.path.join(stage_dir, sub)
        os.makedirs(target, exist_ok=True)
        got = export(kind, target)
        if got is None:
            fail(name, target, 'export failed (see the log)')
        elif not got:
            missing.append(dict(name=name, why=why_none))
        for entry in sorted(os.listdir(target)):
            verify(name, os.path.join(target, entry))
        if not os.listdir(target):
            os.rmdir(target)

    target = os.path.join(stage_dir, REPORT_FILE)
    if export('report', target) is None:
        fail('report', target, 'export failed (see the log)')
    else:
        verify('report', target)


# ── the run stage (solvers/jobs.solve_stage with a stage_dir) ────────────
def headline(exc):
    """The one line that says why a stage ended without finishing: the
    manifest's `stop_reason` for a stage that raised."""
    from ..solvers.hooks import StoppedBeforeStart
    from ..solvers.jobs import HandoffWriteError
    text = next((ln.strip() for ln in str(exc).splitlines() if ln.strip()),
                '')
    if isinstance(exc, (StoppedBeforeStart, HandoffWriteError)):
        return text or type(exc).__name__
    return f'{type(exc).__name__}: {text}' if text else type(exc).__name__


def _append(path, line):
    """One line into run.log directly, not through the hooks: the stage's
    closing line is not a solver line the Run tab should show twice."""
    try:
        with open(path, 'a', encoding='utf-8', newline='\n') as f:
            f.write(f'{line}\n')
    except OSError:
        pass


def stage_solve(dim, case, stage_dir, run_info, make_solve):
    """`solve(hooks)` for one run stage writing into `stage_dir`.

    Registered with `solvers.jobs` (see `jobs.register_stage_folder`), so
    `jobs.solve_stage(dim, case, stage_dir)` returns this. On the worker
    thread it binds the case into the folder (`bind_case`), points
    `hooks.log_file` at run.log, runs the ordinary stage
    (`make_solve(bound)`: solve + the case's own files), then `write_all`.

    A stage that raises - StoppedBeforeStart, a failed hand-off write, any
    error - still gets MODEL.json, run.log and manifest.json
    (`stop_reason` = the error's headline, and the result's rows when a
    HandoffWriteError carries one), and the exception is re-raised
    unchanged, so the worker's 'error' path is what it always was.

    The manifest is left on `hooks.stage_manifest` for the front end."""
    def solve(hooks):
        info = dict(run_info or {})
        info.setdefault('created', now_iso())
        log_path = os.path.join(stage_dir, LOG_FILE)
        os.makedirs(stage_dir, exist_ok=True)
        open(log_path, 'a', encoding='utf-8').close()   # exists from start
        prev_log = getattr(hooks, 'log_file', None)
        hooks.log_file = log_path
        hooks.scratch_posix = None        # set by the blastFoam backend
        p0 = getattr(hooks, '_last_p', None)
        bound, res, err = case, None, None
        try:
            bound = bind_case(case, stage_dir)
            res = make_solve(bound)(hooks)
            return res
        except Exception as exc:
            err = exc
            res = getattr(exc, 'result', None)     # HandoffWriteError
            raise
        finally:
            try:
                p = getattr(hooks, '_last_p', None)
                if p is not None and p is not p0:
                    info.setdefault('n_steps', int(p.step))
                if err is not None:
                    info['stop_reason'] = headline(err)
                    _append(log_path, f'[stage ended: {info["stop_reason"]}]')
                hooks.stage_manifest = write_all(
                    res, bound, dim, stage_dir, info, log=hooks.log)
            finally:
                hooks.log_file = prev_log
    return solve


def _register():
    from ..solvers import jobs
    jobs.register_stage_folder(stage_solve)


_register()
