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
import hashlib
import json
import os
import shutil
import stat
import subprocess
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
    """`path` made absolute, symlink-resolved and case-normalised."""
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


def _desktop_roots():
    """The Desktop folders a runs folder must never be (CLAUDE.md 8.5):
    ~\\Desktop, the OneDrive-redirected ones, and wherever the Windows
    shell says the Desktop is (a redirected known folder)."""
    roots = [os.path.join(os.path.expanduser('~'), 'Desktop')]
    for var in ('OneDrive', 'OneDriveCommercial', 'OneDriveConsumer'):
        base = os.environ.get(var)
        if base:
            roots.append(os.path.join(base, 'Desktop'))
    if os.name == 'nt':
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(1024)
            # CSIDL_DESKTOPDIRECTORY = 0x10; 0 = S_OK
            if ctypes.windll.shell32.SHGetFolderPathW(
                    None, 0x10, None, 0, buf) == 0 and buf.value:
                roots.append(buf.value)
        except (OSError, AttributeError, ValueError):
            pass                  # the two sources above still apply
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
    elif not errors:
        # the model folder itself must not be - or hold - a Desktop: with
        # the home folder as runs folder, the model 'Desktop' would make
        # an overwrite rmtree the thesis data (CLAUDE.md 8.5)
        target = folder_for(runs_dir, model)
        if any(_inside(d, target) for d in _desktop_roots()):
            errors.append(f'Model name: {str(model).strip()} in {runs_dir} '
                          f'is or holds the Desktop - choose another name')
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
#: OUT-2: the VTK files for ParaView (plan sec. 3.6)
VTK_DIR = 'vtk'

def model_for_case_file(path):
    """The Model box after Open case (GUI QA 2026-09-26 C1): the file's
    stem, except for a model folder's own `<MODEL>\\MODEL.json`, which
    names the folder - and a chain stage's `<MODEL>\\2d\\MODEL.json` the
    chain's model folder (a stage folder is not a model)."""
    stem = os.path.splitext(os.path.basename(path))[0]
    if stem != os.path.splitext(CASE_FILE)[0]:
        return stem
    folder = os.path.dirname(os.path.abspath(path))
    parent = os.path.dirname(folder)
    if os.path.basename(folder) in ('1d', '2d', '3d') \
            and os.path.isfile(os.path.join(parent, MARKER_FILE)):
        folder = parent
    return os.path.basename(folder) or stem


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
#: written by `prepare` the moment it creates a model folder, before
#: anything else (owner Q4, 2026-09-26): only a folder holding it - or an
#: empty one - may ever be overwritten
MARKER_FILE = '.blastlab-model'


def overwrite_text(runs_dir, model):
    """The confirmation question for an existing model (plan sec. 2.1)."""
    return (f'{str(model).strip()} already exists in '
            f'{str(runs_dir).strip()}. Overwrite? The previous run\'s '
            f'files will be deleted.')


def foreign_text(target):
    """The refusal for an existing folder blastlab did not create (Q4)."""
    return (f'{target} was not created by blastlab - choose another model '
            f'name')


def is_model_folder(path):
    """True when `path` holds the marker `prepare` writes, or is empty:
    the only folders an overwrite may delete (owner Q4)."""
    try:
        entries = os.listdir(path)
    except OSError:
        return False
    return not entries or MARKER_FILE in entries


def write_marker(folder, model):
    """The `.blastlab-model` marker: the model name and the creation time,
    JSON, UTF-8. Raises OSError."""
    with open(os.path.join(folder, MARKER_FILE), 'w', encoding='utf-8',
              newline='\n') as f:
        json.dump(dict(model=str(model).strip(), created=now_iso()), f)
        f.write('\n')


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
    """The model folder for a run, holding only its marker, or None when
    the user declined.

    Absent: created, and the `.blastlab-model` marker written first
    (owner Q4). Present: only a folder with the marker, or an empty one,
    may be overwritten - any other raises ModelFolderError
    (`foreign_text`) before any question. Then
    `confirm(overwrite_text(...))` is asked; yes deletes it and creates it
    again, no returns None with nothing touched. A folder that cannot be
    deleted (a file open in ParaView) raises ModelFolderError with the OS
    text, and nothing is recreated.

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
        if not is_model_folder(target):
            raise ModelFolderError(foreign_text(target))
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
        write_marker(target, model)
    except OSError as exc:
        raise ModelFolderError(f'Could not create {target}: {exc}') from exc
    return target


class Target(SimpleNamespace):
    """A prepared model folder: `runs_dir`, `model` (trimmed) and
    `folder`, the directory `prepare` returned."""


def prepare_target(runs_dir, model, confirm):
    """The front ends' pre-flight after `check` passed: `prepare`, as a
    Target, or None when the overwrite was declined. Raises
    ModelFolderError like `prepare`."""
    folder = prepare(runs_dir, model, confirm)
    if folder is None:
        return None
    return Target(runs_dir=str(runs_dir).strip(), model=str(model).strip(),
                  folder=folder)


def stage_dirs(target, dims):
    """Where each stage of a run writes: the model folder itself for one
    stage, `<MODEL>\\1d`, `2d`, `3d` for a chain (plan sec. 2.2)."""
    dims = list(dims)
    if len(dims) == 1:
        return [target.folder]
    return [os.path.join(target.folder, f'{int(d)}d') for d in dims]


def run_info(target, case=None, rep=None, handoff=None):
    """The manifest facts a front end knows before the run: the model,
    the runs folder, the model root (for folder-relative hand-off paths)
    and, from the pre-flight ValidationReport, `n_cells` and `n_procs`
    (the planned MPI ranks of a blastFoam run; 1 for a native one).
    `handoff`: the chain hand-off this stage writes (`stage_solve`)."""
    info = dict(model=target.model, runs_dir=target.runs_dir,
                model_dir=target.folder)
    if handoff:
        info['handoff'] = handoff
    if rep is not None and getattr(rep, 'n_cells', None):
        info['n_cells'] = int(rep.n_cells)
    if case is not None:
        if getattr(case, 'solver', 'native') != 'blastfoam':
            info['n_procs'] = 1
        elif case.dim == 1:
            info['n_procs'] = 1                 # 1D blastFoam runs serial
        elif rep is not None and getattr(rep, 'run_plan', None) is not None:
            info['n_procs'] = int(rep.run_plan.ranks)
    return info


def make_stages(target, dim_cases, reports=None):
    """[(label, solve)] for a run into the model folder `target`, one per
    (dim, case): each stage writes its own folder (`stage_dirs`) with the
    pre-flight report's facts in its manifest, and a chain stage before
    the last one keeps its hand-off - the `profile_file` the Chain tab
    wired - as its profile. Shared by the Qt controller and the Tk app."""
    from ..solvers.jobs import solve_stage
    dims = [dim for dim, _ in dim_cases]
    reports = list(reports or [None] * len(dim_cases))
    last = len(dim_cases) - 1
    return [solve_stage(dim, case, stage_dir=sd,
                        run_info=run_info(target, case, rep,
                                          handoff=(case.profile_file
                                                   if k < last else None)))
            for k, ((dim, case), sd, rep) in enumerate(zip(
                dim_cases, stage_dirs(target, dims), reports))]


HANDOFF_PREFIX = 'handoff_'


def handoff_paths(target, dims):
    """The chain's hand-off files at the model root (plan sec. 2.2):
    `handoff_1d_to_2d.txt` into a 2D stage, `handoff_2d_to_3d.npz` into
    a 3D one. {(from_dim, to_dim): path}."""
    dims = [int(d) for d in dims]
    out = {}
    for a, b in zip(dims, dims[1:]):
        ext = '.txt' if a == 1 else '.npz'
        out[(a, b)] = os.path.join(
            target.folder, f'{HANDOFF_PREFIX}{a}d_to_{b}d{ext}')
    return out


def write_chain_root(target, dims, folders):
    """The chain's root manifest.json, written when the run is done:
    {"chain": [1, 2, 3], "stages": {"1d": <stage manifest>}, "handoffs":
    [...]} plus the model, the runs folder and the finish time.
    `folders` maps each stage folder that was written to its manifest (a
    stage that never ran is absent); `handoffs` lists the hand-off files
    found at the model root. Returns an error text or None."""
    stages = {os.path.basename(os.path.normpath(d)): m
              for d, m in folders.items()}
    try:
        handoffs = sorted(n for n in os.listdir(target.folder)
                          if n.startswith(HANDOFF_PREFIX))
    except OSError:
        handoffs = []
    manifest = dict(model=target.model, runs_dir=target.runs_dir,
                    finished=now_iso(), chain=[int(d) for d in dims],
                    stages=stages, handoffs=handoffs)
    return write_manifest(manifest, target.folder)


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
    """True when `path` is `root` or below it; False across drives."""
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
#: git's default abbreviation length for a commit hash
SHORT_HASH_LEN = 7


def _read_stripped(path):
    """The UTF-8 text of `path`, stripped. Raises OSError."""
    with open(path, encoding='utf-8') as f:
        return f.read().strip()


def _repo_root():
    """The repository checkout root (two levels above services/)."""
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
            line = _read_stripped(dot)
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
            common = os.path.normpath(os.path.join(gitdir,
                                                   _read_stripped(cfile)))
        head = _read_stripped(os.path.join(gitdir, 'HEAD'))
        if not head.startswith('ref:'):
            return head[:SHORT_HASH_LEN] or None        # detached HEAD
        ref = head[4:].strip()
        for base in (gitdir, common):
            path = os.path.join(base, *ref.split('/'))
            if os.path.isfile(path):
                return _read_stripped(path)[:SHORT_HASH_LEN] or None
        packed = os.path.join(common, 'packed-refs')
        if os.path.isfile(packed):
            with open(packed, encoding='utf-8') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) == 2 and parts[1] == ref:
                        return parts[0][:SHORT_HASH_LEN]
    except OSError:
        pass
    return None


def list_outputs(stage_dir):
    """[{'path': 'gauges/gauges_2d.txt', 'bytes': n}, ...]: every file in
    the folder except manifest.json, the `.blastlab-model` marker
    (bookkeeping, not an output) and the VTK export's `vtk/` (thousands
    of files on a long run - the manifest's `vtk` entry carries its
    numbers and vtk/manifest.json its full list; owner decision P4),
    sorted, '/' separators."""
    out = []
    top = os.path.normpath(stage_dir)
    for root, dirs, files in os.walk(stage_dir):
        if os.path.normpath(root) == top and VTK_DIR in dirs:
            dirs.remove(VTK_DIR)
        dirs.sort()
        for name in sorted(files):
            full = os.path.join(root, name)
            rel = os.path.relpath(full, stage_dir).replace('\\', '/')
            if rel in (MANIFEST_FILE, MARKER_FILE):
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
        wsl_fields=None,
        failed=[])


def wsl_fields_record(foam, keep_all, dim, deleted):
    """OUT-3 (E7, Q6): the root manifest's `wsl_fields` - {mode, deleted,
    first, last} - or None for a native stage. `mode`: 'newest' (older
    writes deleted once ingested), 'keep_all' (the box was ticked) or
    'off' (1D keeps every write, P9). Numbers only, as P4's root
    manifest; the times deleted are counted, first and last named."""
    if not foam:
        return None
    mode = 'keep_all' if keep_all else ('off' if int(dim) == 1
                                        else 'newest')
    times = sorted({str(t) for t in (deleted or ())}, key=float)
    return dict(mode=mode, deleted=len(times),
                first=times[0] if times else None,
                last=times[-1] if times else None)


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

    for sub in (GAUGES_DIR, FIGURES_DIR, FIELDS_DIR):   # no empty folders
        try:
            os.rmdir(os.path.join(stage_dir, sub))
        except OSError:
            pass                        # absent, or holds files
    # OUT-2: the VTK export's own summary (additive; None without export).
    # A time it could not convert or copy is a failed row, so the WSL
    # scratch - which still holds it - is kept for a manual export (Q4)
    from ..output.vtk_series import vtk_summary
    manifest['vtk'] = vtk_summary(os.path.join(stage_dir, VTK_DIR), VTK_DIR)
    for e in (manifest['vtk'] or {}).get('not_converted') or ():
        failed.append(dict(name='vtk', path=e.get('path') or VTK_DIR,
                           why=f"t = {e.get('time')}: {e.get('why')}"))
    # OUT-3: what the run kept in WSL (additive; None for a native run
    # and for a caller that does not say - run_info['wsl_fields'])
    manifest['wsl_fields'] = info.get('wsl_fields')
    manifest['outputs'] = list_outputs(stage_dir)
    manifest['finished'] = now_iso()
    why = write_manifest(manifest, stage_dir)
    if why:
        # a row of sec. 2.2 too: recorded, so the WSL scratch is kept
        failed.append(dict(name='manifest', path=MANIFEST_FILE, why=why))
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

    def figures_log(msg):
        # run_export names each PNG bare ("Saved x.png"); in the run log
        # it reads as if in the working folder (GUI QA C3)
        if msg.startswith('Saved '):
            msg = f'Saved {os.path.join(FIGURES_DIR, msg[len("Saved "):])}'
        log(msg)

    def export(kind, target):
        try:
            return exports.run_export(
                kind, ent, target, open_after=False,
                log=figures_log if kind == 'pngs' else log)
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

    target = os.path.join(stage_dir, REPORT_FILE)
    if export('report', target) is None:
        fail('report', target, 'export failed (see the log)')
    else:
        verify('report', target)


# ── the native --cli (batch plan D14, owner Q2) ──────────────────────────
#: the rows of plan sec. 2.2 the historical native prompt flow
#: (legacy/blast*d._main, byte-pinned) never writes, and why
CLI_NOT_WRITTEN = (
    ('case', CASE_FILE, 'the native prompt flow writes no case file'),
    ('run log', LOG_FILE, 'the native prompt flow prints to the console '
                          'only'),
    ('summary', f'{GAUGES_DIR}/', 'the native prompt flow writes no gauge '
                                  'summary'),
    ('figures', f'{FIGURES_DIR}/', 'the native prompt flow saves its own '
                                   'plots (blast_*.png) instead of the '
                                   'figures set'),
    ('fields', f'{FIELDS_DIR}/', 'the native prompt flow writes no field '
                                 'CSVs'),
    ('report', REPORT_FILE, 'the native prompt flow writes no report'),
)


def cli_manifest(folder, dim, info=None, stop_reason=None):
    """The manifest of a native `--cli` run (D14): what the legacy prompt
    flow wrote into the folder (it ran with the folder as working
    directory), and under `missing` every row of sec. 2.2 it does not
    write. Written to manifest.json and returned; never raises."""
    manifest = new_manifest(None, dim, folder, info)
    manifest['stop_reason'] = stop_reason
    for name, rel, why in CLI_NOT_WRITTEN:
        if not os.path.exists(os.path.join(folder, *rel.rstrip('/')
                                           .split('/'))):
            manifest['missing'].append(dict(name=name, why=why))
    manifest['case_file'] = None
    manifest['outputs'] = list_outputs(folder)
    manifest['finished'] = now_iso()
    err = write_manifest(manifest, folder)
    if err:
        manifest['failed'].append(dict(name='manifest', path=MANIFEST_FILE,
                                       why=err))
    return manifest


# ── blastFoam: the foam\ skeleton and the WSL scratch (plan sec. 2.3) ────
FOAM_DIR = 'foam'
SUMS_FILE = 'SHA256SUMS'

#: the case skeleton copied into foam\: the top-level entries of the run
#: directory (`writer.write_case` layout), never processor*/ or a time dir
SKELETON_DIRS = ('system', 'constant', '0', 'postProcessing')

#: hashing a large polyMesh inside WSL takes seconds; this is the ceiling
SKELETON_TIMEOUT_S = 600

#: OUT-2 (batch plan D11): the VTK surface output under postProcessing/
#: belongs to the export, which copies it into vtk\ and deletes it in
#: WSL - never part of foam\ (and blastFoam's own .vtk.series there is
#: not copied). The names are writer.VTK_SECTIONS / VTK_OBSTACLES.
VTK_POST_DIRS = ('postProcessing/vtkSections', 'postProcessing/vtkObstacles')


def skeleton_script(scratch_posix):
    """The bash line run inside WSL (no OpenFOAM env needed): hash every
    skeleton file into <scratch>/SHA256SUMS, `sha256sum` format
    (`<hex>  <relpath>`), sorted. Missing entries (a profile stage has no
    0/, a run without logs has no log.*) are skipped silently; the VTK
    surface output (VTK_POST_DIRS) is left out."""
    tops = ' '.join(SKELETON_DIRS)
    prune = ''.join(f" -not -path '{d}/*'" for d in VTK_POST_DIRS)
    return (f"cd '{scratch_posix}' && find {tops} log.* -type f{prune} "
            f"-print0 2>/dev/null | LC_ALL=C sort -z | xargs -0 -r "
            f"sha256sum > {SUMS_FILE}")


def in_skeleton(rel):
    """True for a relative path that belongs in foam\\ (SKELETON_DIRS or
    a top-level log.*); a stray line can never pull in processor*/,
    a time directory, the VTK surface output or a path outside the
    scratch."""
    parts = rel.split('/')
    if not rel or rel.startswith('/') or '..' in parts or '' in parts:
        return False
    if len(parts) == 1:
        return parts[0].startswith('log.')
    if any(rel.startswith(d + '/') for d in VTK_POST_DIRS):
        return False
    return parts[0] in SKELETON_DIRS


def parse_sums(text):
    """[(hex, relpath)] from a sha256sum listing; other lines skipped."""
    out = []
    for line in text.splitlines():
        if len(line) < 67 or line[64:66] not in ('  ', ' *'):
            continue
        digest, rel = line[:64].lower(), line[66:]
        if all(c in '0123456789abcdef' for c in digest):
            out.append((digest, rel))
    return out


_HASH_CHUNK = 1 << 20  # 1 MiB read size


def _sha256(path):
    """Hex SHA-256 of a file, read in 1 MiB chunks."""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(_HASH_CHUNK), b''):
            h.update(chunk)
    return h.hexdigest()


def _copy_listed(listing, root, foam, out):
    """Copy each (digest, rel) of `listing` from `root` into `foam`, hash
    the copy and compare; updates `out` files / errors / mismatches."""
    for digest, rel in listing:
        parts = rel.split('/')
        dst = os.path.join(foam, *parts)
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(os.path.join(root, *parts), dst)
            got = _sha256(dst)
        except OSError as exc:
            out['errors'].append((rel, str(exc) or type(exc).__name__))
            continue
        out['files'] += 1
        if got != digest:
            out['mismatches'].append(rel)


def copy_foam_skeleton(scratch_posix, dest, run=subprocess.run, unc=None,
                       timeout=SKELETON_TIMEOUT_S):
    """Copy the blastFoam case skeleton of `scratch_posix` into
    `dest\\foam\\` and verify it (plan sec. 2.3):

    1. inside WSL, `sha256sum` every skeleton file into SHA256SUMS
       (`skeleton_script`, through `env.wsl_plain_argv`);
    2. copy each listed file over the UNC path;
    3. hash the copy on Windows and compare with the WSL hash;
    4. copy SHA256SUMS itself.

    `run` and `unc` (posix -> Windows path) are injectable for tests.
    Never raises. Returns dict(ok, files, mismatches, errors, detail):
    `ok` only when the listing ran, listed at least one file and every
    file copied with a matching hash."""
    from ..solvers.foam import env
    unc = unc or env.unc
    out = dict(ok=False, files=0, mismatches=[], errors=[], detail='')
    if "'" in scratch_posix:
        out['detail'] = f'unexpected scratch path {scratch_posix!r}'
        return out
    try:
        res = run(env.wsl_plain_argv(skeleton_script(scratch_posix)),
                  capture_output=True, text=True, timeout=timeout,
                  stdin=subprocess.DEVNULL,
                  creationflags=env.CREATE_NO_WINDOW)
    except (OSError, subprocess.SubprocessError) as exc:
        out['detail'] = f'hashing in WSL failed: {exc}'
        return out
    if res.returncode != 0:
        err = (res.stderr or '').strip().splitlines()
        out['detail'] = ('hashing in WSL failed (exit '
                         f'{res.returncode}' + (f': {err[-1]}' if err else '')
                         + ')')
        return out
    root = unc(scratch_posix)
    foam = os.path.join(dest, FOAM_DIR)
    try:
        with open(os.path.join(root, SUMS_FILE), encoding='utf-8',
                  errors='replace') as f:
            text = f.read()
    except OSError as exc:
        out['detail'] = f'cannot read {SUMS_FILE}: {exc}'
        return out
    listing = parse_sums(text)
    # a line parse_sums cannot read (sha256sum escapes a name holding a
    # backslash or a newline) is a file that would not be copied: the
    # copy is then not complete, and the scratch must stay
    unread = sum(1 for ln in text.splitlines() if ln.strip()) - len(listing)
    if unread:
        out['errors'].append((SUMS_FILE, f'{unread} line(s) not understood'))
    listing = [(h, rel) for h, rel in listing if in_skeleton(rel)]
    _copy_listed(listing, root, foam, out)
    try:
        os.makedirs(foam, exist_ok=True)
        shutil.copyfile(os.path.join(root, SUMS_FILE),
                        os.path.join(foam, SUMS_FILE))
    except OSError as exc:
        out['errors'].append((SUMS_FILE, str(exc) or type(exc).__name__))
    notes = []
    if not listing:
        notes.append('the WSL listing named no skeleton file')
    if out['mismatches']:
        notes.append('hash mismatch: ' + ', '.join(out['mismatches']))
    if out['errors']:
        notes.append('not copied: ' + ', '.join(
            f'{rel} ({why})' for rel, why in out['errors']))
    out['ok'] = not notes
    out['detail'] = '; '.join(notes) or (f'{out["files"]} files copied '
                                         f'and verified')
    return out


#: OUT-3 (E5, Q3): why a finished run with the box ticked keeps its scratch
KEEP_ALL_WHY = 'Keep all fields in WSL was ticked'


def release_decision(errored, stopped_early, verify, keep_all=False,
                     stopped=False):
    """(release, why): may the WSL scratch be deleted? Pure.

    Release only when the run did not raise, did not end early (a user
    stop or `STOP_UNSTABLE`: `Result.stopped_early`), every row of sec.
    2.2 was verified (`verify['rows_ok']`) and the foam\\ copy matched
    its WSL hashes (`verify['hashes_ok']`). Otherwise `why` names the
    first reason, in that order; `verify['rows_detail']` /
    `['hash_detail']` say which files. OUT-3 (E5): `keep_all` (the "Keep
    all fields in WSL" box) keeps the scratch of a run that would
    otherwise be released - else the box would keep nothing.

    G15Q-5b: `stopped` is the user's stop before the solve started (a
    Stop during blockMesh raises StoppedBeforeStart, so the run also
    reads as `errored`); it is named first, as a stop, not a raise."""
    if stopped:
        return False, 'the run was stopped before it finished'
    if errored:
        return False, 'the run did not finish (it raised)'
    if stopped_early:
        return False, 'the run ended before its end time'
    if not verify.get('rows_ok'):
        return False, ('not every output was written: '
                       + (verify.get('rows_detail') or '?'))
    if not verify.get('hashes_ok'):
        return False, ('the foam\\ copy did not verify: '
                       + (verify.get('hash_detail') or '?'))
    if keep_all:
        return False, KEEP_ALL_WHY
    return True, 'finished, every output written and foam\\ verified'


def model_of_run(runs_dir, posix):
    """P2-17 (D15): the stage folder whose manifest.json records `posix`
    as its WSL scratch (`wsl_scratch.posix`), else None - so a resume of
    that run writes into the model it belongs to, and its release
    decision rewrites that same manifest (the original no longer says
    "kept"). Looks at `<runs_dir>\\<MODEL>\\` and a chain's `1d`, `2d`,
    `3d` stage folders; when two record the run, the newest manifest
    (its file time) wins. Read only; no new file (D15)."""
    if not runs_dir or not posix or not os.path.isdir(runs_dir):
        return None
    best = None
    for name in sorted(os.listdir(runs_dir)):
        model = os.path.join(runs_dir, name)
        if not os.path.isdir(model):
            continue
        for stage in [model] + [os.path.join(model, f'{d}d')
                                for d in (1, 2, 3)]:
            path = os.path.join(stage, MANIFEST_FILE)
            try:
                with open(path, encoding='utf-8') as f:
                    manifest = json.load(f)
                when = os.path.getmtime(path)
            except (OSError, ValueError):
                continue
            scratch = (manifest.get('wsl_scratch')
                       if isinstance(manifest, dict) else None)
            if not isinstance(scratch, dict) \
                    or scratch.get('posix') != posix:
                continue
            if best is None or when > best[0]:
                best = (when, stage)
    return best[1] if best else None


def is_run_dir(posix):
    """Only a direct child of the runs root is ever deleted."""
    from ..solvers.foam import env
    head = env.RUNS_ROOT.rstrip('/') + '/'
    name = str(posix or '')[len(head):]
    return (str(posix or '').startswith(head) and bool(name)
            and '/' not in name and name not in ('.', '..')
            and "'" not in name)


def verify_and_release_scratch(manifest, stage_dir, scratch_posix, errored,
                               stopped_early, log=print, run=subprocess.run,
                               delete=None, unc=None, keep_all=False,
                               stopped=False):
    """Copy foam\\, decide, and delete the WSL scratch only after a
    verified copy of a finished run (plan sec. 2.3, decision 12).

    A run that raised is not copied (WSL may be what failed; `errored` is
    False for a HandoffWriteError, whose solve finished) and keeps its
    scratch whole; a stopped run is copied and kept. The delete goes
    through `env.delete_runs` (batch plan D11) on this run's own posix
    path, and only a direct child of the runs root. The manifest gets
    `wsl_scratch` {posix, deleted, deleted_at} (+ `kept_because`), a
    failed copy's files in `failed`, and is written again. `stopped`:
    the user stopped the run before its solve (`release_decision`).

    Returns (manifest, notice): `notice` is the dialog text for the GUI
    when a finished run's scratch was kept because the copy or a row
    failed; None otherwise. Never raises."""
    from ..solvers.foam import env
    delete = delete or env.delete_runs
    scratch = dict(posix=scratch_posix, deleted=False, deleted_at=None)
    manifest['wsl_scratch'] = scratch
    failed = manifest.setdefault('failed', [])
    copied = dict(ok=False, detail='not copied: the run failed')
    if not errored:
        copied = copy_foam_skeleton(scratch_posix, stage_dir, run=run,
                                    unc=unc)
        for rel in copied.get('mismatches', []):
            failed.append(dict(name='foam', path=f'{FOAM_DIR}/{rel}',
                               why='hash mismatch'))
        for rel, why in copied.get('errors', []):
            failed.append(dict(name='foam', path=f'{FOAM_DIR}/{rel}',
                               why=why))
    rows = [f for f in failed if f.get('name') != 'foam']
    verify = dict(rows_ok=not rows,
                  rows_detail=', '.join(str(f.get('path')) for f in rows),
                  hashes_ok=bool(copied.get('ok')),
                  hash_detail=copied.get('detail', ''))
    release, why = release_decision(errored, stopped_early, verify,
                                    keep_all=keep_all, stopped=stopped)
    if release and not is_run_dir(scratch_posix):
        release, why = False, (f'{scratch_posix} is not a run directory '
                               f'directly under {env.RUNS_ROOT}')
    if release:
        try:
            ok = delete([scratch_posix])
        except Exception as exc:
            ok, why = False, f'the WSL delete failed: {exc}'
        if ok:
            scratch.update(deleted=True, deleted_at=now_iso())
            log(f'  [model folder] WSL scratch deleted: {scratch_posix}')
        elif not why.startswith('the WSL delete'):
            why = 'the WSL delete failed'
    notice = None
    if not scratch['deleted']:
        scratch['kept_because'] = why
        kind = 'note' if (errored or stopped_early or stopped) else 'warn'
        log(f'  [{"note" if why == KEEP_ALL_WHY else kind}] WSL scratch '
            f'kept ({why}): {scratch_posix}')
        if kind == 'warn':
            notice = (f'The blastFoam run finished, but its WSL scratch was '
                      f'kept:\n{why}\n\n{scratch_posix}\n\nThe model folder '
                      f'{stage_dir} holds everything that could be copied. '
                      f'The scratch still opens from the run browser.')
    manifest['outputs'] = list_outputs(stage_dir)
    manifest['finished'] = now_iso()
    err = write_manifest(manifest, stage_dir)
    if err:
        log(f'[warn] model folder: could not write {MANIFEST_FILE}: {err}')
    return manifest, notice


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


#: the provisional manifest's stop_reason, written when a stage starts and
#: replaced when it ends: a folder that still says this was left by a run
#: that never reached its end - blastlab closed mid-run, or the process died
UNFINISHED = ('unfinished: the run did not reach its end (blastlab was '
              'closed, or the process ended, during the run)')


def write_started(case, dim, stage_dir, run_info=None):
    """MODEL.json and a provisional manifest.json the moment a stage
    starts, so a folder whose run never ends (the window closed mid-run:
    the worker is a daemon thread and dies with the process) still says
    what ran and that it did not finish. `write_all` replaces both at
    the end. Never raises."""
    info = dict(run_info or {})
    manifest = new_manifest(case, dim, stage_dir, info)
    manifest['stop_reason'] = UNFINISHED
    try:
        from ..models.case import save_case
        save_case(relative_case(case, stage_dir, info.get('model_dir')),
                  os.path.join(stage_dir, CASE_FILE))
    except Exception:             # write_all writes it again, or says why
        pass
    manifest['outputs'] = list_outputs(stage_dir)
    write_manifest(manifest, stage_dir)


def _append(path, line):
    """One line into run.log directly, not through the hooks: the stage's
    closing line is not a solver line the Run tab should show twice."""
    try:
        with open(path, 'a', encoding='utf-8', errors='replace',
                  newline='\n') as f:
            f.write(f'{line}\n')
    except (OSError, ValueError):
        pass


def stage_solve(dim, case, stage_dir, run_info, make_solve):
    """`solve(hooks)` for one run stage writing into `stage_dir`.

    Registered with `solvers.jobs` (see `jobs.register_stage_folder`), so
    `jobs.solve_stage(dim, case, stage_dir)` returns this. On the worker
    thread it binds the case into the folder (`bind_case`), points
    `hooks.log_file` at run.log, writes MODEL.json and a provisional
    manifest (`write_started`: a run that never ends still says so), runs
    the ordinary stage (`make_solve(bound)`: solve + the case's own
    files), then `write_all`.

    A stage that raises - StoppedBeforeStart, a failed hand-off write, any
    error - still gets MODEL.json, run.log and manifest.json
    (`stop_reason` = the error's headline, and the result's rows when a
    HandoffWriteError carries one), and the exception is re-raised
    unchanged, so the worker's 'error' path is what it always was.

    A blastFoam stage (`hooks.scratch_posix` set by the backend) then
    copies foam\\ and releases or keeps its WSL scratch
    (`verify_and_release_scratch`).

    The manifest is left on `hooks.stage_manifest` and a kept-scratch
    dialog text on `hooks.folder_notice` (None when there is nothing to
    say) for the front end."""
    def solve(hooks):
        info = dict(run_info or {})
        info.setdefault('created', now_iso())
        log_path = os.path.join(stage_dir, LOG_FILE)
        os.makedirs(stage_dir, exist_ok=True)
        with open(log_path, 'a', encoding='utf-8'):     # exists from start
            pass
        prev_log = getattr(hooks, 'log_file', None)
        prev_vtk = getattr(hooks, 'vtk_dir', None)
        prev_fields = (getattr(hooks, 'purge_fields', False),
                       getattr(hooks, 'keep_all_fields', False),
                       getattr(hooks, 'fields_deleted', None))
        hooks.log_file = log_path
        hooks.scratch_posix = None        # set by the blastFoam backend
        # OUT-2 (D12): the VTK export writes into <stage>\vtk - only for a
        # blastFoam stage with a family on; None keeps it inactive
        hooks.vtk_dir = (os.path.join(stage_dir, VTK_DIR)
                         if _exports_vtk(case) else None)
        # OUT-3 (E4): a blastFoam stage keeps only its newest writes in
        # WSL unless "Keep all fields in WSL" is ticked
        foam = getattr(case, 'solver', 'native') == 'blastfoam'
        keep = foam and getattr(case, 'keep_all_fields', False) is True
        hooks.purge_fields = foam and not keep
        hooks.keep_all_fields = keep
        hooks.fields_deleted = set()
        p0 = getattr(hooks, '_last_p', None)
        bound, res, err = case, None, None
        try:
            bound = bind_case(case, stage_dir)
            if info.get('handoff'):
                # a chain stage feeding the next: its profile IS the
                # hand-off at the model root, and a 'remap' trigger writes
                # there too - a blank trigger file, the form default the
                # chain always ran with before OUT-1 (jobs falls back to
                # profile_file)
                bound.profile_file = info['handoff']
                bound.trigger_file = None
            write_started(bound, dim, stage_dir, info)
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
                info['wsl_fields'] = wsl_fields_record(
                    foam, keep, dim, hooks.fields_deleted)
                manifest = write_all(res, bound, dim, stage_dir, info,
                                     log=hooks.log)
                hooks.folder_notice = None
                posix = getattr(hooks, 'scratch_posix', None)
                if posix and foam:
                    try:
                        manifest, hooks.folder_notice = \
                            verify_and_release_scratch(
                                manifest, stage_dir, posix,
                                errored=err is not None and not isinstance(
                                    err, _handoff_error()),
                                stopped_early=bool(res is not None
                                                   and res.stopped_early),
                                log=hooks.log, keep_all=keep,
                                # G15Q-5b: the user's Stop before the
                                # solve (during blockMesh) is a stop
                                stopped=isinstance(err, _stopped_error()))
                    except Exception as exc:   # keeps the scratch
                        hooks.log(f'  [warn] WSL scratch kept: the foam\\ '
                                  f'copy raised {exc!r}: {posix}')
                hooks.stage_manifest = manifest
                if res is not None:
                    # the Results tab: export dialogs start here (Q3), and
                    # the VTK button says why the case directory is gone
                    res.meta['model_dir'] = stage_dir
                    res.meta['scratch_released'] = bool(
                        (manifest.get('wsl_scratch') or {}).get('deleted'))
                try:
                    hooks.folder_written(stage_dir, manifest,
                                         hooks.folder_notice)
                except Exception as exc:   # a front end's bug is not the run's
                    _append(log_path, f'[warn] model folder: the front end '
                                      f'could not take the manifest: {exc!r}')
            finally:
                hooks.log_file = prev_log
                hooks.vtk_dir = prev_vtk
                (hooks.purge_fields, hooks.keep_all_fields,
                 hooks.fields_deleted) = prev_fields
    return solve


def _exports_vtk(case):
    """Does this blastFoam case have a VTK family switched on (OUT-2)?"""
    if getattr(case, 'solver', 'native') != 'blastfoam':
        return False
    from ..models.case import vtk_family
    try:
        return bool(vtk_family(case, 'vtk_surfaces')
                    or vtk_family(case, 'vtk_volumes'))
    except ValueError:              # validation refuses it before the run
        return False


def _handoff_error():
    from ..solvers.jobs import HandoffWriteError
    return HandoffWriteError


def _stopped_error():
    from ..solvers.hooks import StoppedBeforeStart
    return StoppedBeforeStart


def _register():
    from ..solvers import jobs
    jobs.register_stage_folder(stage_solve)


_register()
