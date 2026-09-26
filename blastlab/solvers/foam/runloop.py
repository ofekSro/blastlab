"""The blastFoam run loop shared by the 1D/2D/3D backends (ROADMAP A1).

Run loop model: blastFoam streams stdout (every step prints `Time =`,
`deltaT =` and `max(p):` lines -> Progress), while written time
directories are polled and ingested as backend "steps" (live frames,
step_gate, stop conditions). Graceful stop and the shock-arrival
condition both go through `stopAt writeNow` so a final complete time
directory is always written.

`FoamRunLoop` owns everything the three dims share: starting the solver,
stdout pumping, time-dir polling + readiness + strictly ordered ingest,
stop-request -> writeNow -> grace -> kill escalation, the final drain and
sweep, the adaptive writeInterval controller and the `finally` cleanup.
The per-dim work is two callbacks: `read_dir(name, dpath)` reads one
time dir (raising ValueError/OSError on a torn file, which the loop
treats as "retry next poll") and `on_frame(name, dpath, payload)` turns
that read into frames/snapshots/stop decisions (return False to have the
dir skipped for good). `solve_*_foam` in backend.py are thereby
preflight -> callbacks -> `FoamRunLoop(...).run()` -> `finalize_*`.

Every log string here is load-bearing: the GUI and the tests grep them.
"""

import os
import re
import shutil
import time as _time

import numpy as np

from ...core.constants import P_AIR
from ..hooks import Progress
from . import reader, runner, writer
from .common import rd_scalar

_RE_TIME = re.compile(r'^Time = ([0-9.eE+-]+)s?$')
_RE_DT = re.compile(r'^deltaT = ([0-9.eE+-]+)$')
#: blastFoam prints `max(p): X, min(p): Y` on one line. The min was
#: parsed away for years; it is captured now for the instability message
#: only - a strong rarefaction can dip negative and recover, so it is NOT
#: a stop trigger. group(1) is unchanged, so every existing match is too.
_RE_MAXP = re.compile(r'^max\(p\):\s*([0-9.eE+-]+)'
                      r'(?:,\s*min\(p\):\s*([0-9.eE+-]+))?')

#: conservedQuantities (N5-5) prints a four-line block per field, e.g.
#:
#:     rhoE [1 -1 -2 0 0 0 0] :
#:         Original = 28.4068
#:         Current = 28.4068
#:         difference (abs/rel) = 0, 0
#:
#: captured verbatim from a real 6.2.0 run. `Original` is the value at
#: the FIRST execute, not at t = 0 of the physical problem - on a resume
#: it is the value at restart. The value itself is sum(field*V) over the
#: mesh (conservedQuantities.C:141), i.e. a volume integral in the
#: mesh's OWN units: a wedge reports its sector, not the full revolve.
_RE_CONS_HEAD = re.compile(r'^(rho|rhoE) \[[-0-9 ]+\] :$')
_RE_CONS_VAL = re.compile(r'^\s+(Original|Current) = ([0-9.eE+-]+)$')

ARRIVAL_P = 1.001 * P_AIR       # native shock-arrival threshold
STOP_GRACE_S = 60.0             # writeNow -> kill escalation window
POLL_S = 0.25
#: polls a torn earlier dir may hold up ingest once later dirs are complete
STALL_POLLS = 20
#: adaptive writeInterval: act at most once per this many ingests
ADAPT_EVERY = 3
#: solver stdout lines tolerated before the first `Time = ` match. The
#: regex below is load-bearing - step counting, the progress bar and the
#: live-frame cadence all hang off it - so a blastFoam release that
#: reworded its time banner would silently freeze all three. One warning
#: after this many lines is the canary (A6). blastFoam's own header is
#: well under 100 lines.
TIME_CANARY_LINES = 500

#: A blastFoam run whose deltaT collapses toward zero does not fail fast:
#: it spins, the solver clock stops advancing at print precision, and it
#: finally dies inside compressibleBlastSystem::decode() dividing rhoU by
#: a zero density - SIGFPE, exit 136, no result at all. Measured on a
#: profile+AMR 3D case: deltaT fell 6.4e-06 -> 1e-08 -> 7.5e-12 over ~43
#: steps with the clock frozen, and the user just waited.
#: deltaT is compared to its own RUNNING MAXIMUM, so the small-and-growing
#: deltaT of a healthy start cannot trip this, and neither can a run with
#: adjustTimeStep off (dt == dt_max forever). The stalled-clock conjunct
#: is what separates "unstable" from "legitimately tiny fixed step".
DT_COLLAPSE_FRAC = 1e-3
COLLAPSE_STEPS = 15
COLLAPSE_STEPS_HARD = 60
CLOCK_STUCK_STEPS = 3
MIN_STABLE_STEPS = 20

#: stop_reason for the above. Deliberately NOT 'stopped by user' (the
#: exact string three backends key stopped_early off) and deliberately
#: not in backend._NATURAL_END, so the W2 gauge-tail note still fires.
STOP_UNSTABLE = 'numerical instability'

#: W3 (2026-09-16): the WSL distribution can be torn down UNDER a running
#: solver - measured on a 13-rank 3D run, 11 minutes in: `dmesg` said
#: "Init has exited. Terminating distribution", ext4 was unmounted, and
#: the solver's next write (its gauge file, whose tail is ~200 NUL bytes
#: of never-flushed delayed allocation) failed IOstream::check. What
#: reaches stdout is not one FOAM error but the filesystem going away for
#: every process at once: blastFoam's own I/O error, Open MPI unable to
#: read its STATIC help text (`help-mpi-api.txt: Input/output error`),
#: PMIx losing its dstore files. None of these is something the solve did
#: wrong, and the written time dirs up to the last flush are intact - so
#: backend auto-resumes such a run instead of reporting it failed.
#: Deliberately narrow: a genuine numerical death (SIGFPE, divergence,
#: mesh-size mismatch) must still surface as the failure it is.
WSL_VANISHED = ('Input/output error',
                'PMIX ERROR: NO-PERMISSIONS',
                'Stale file handle',
                'Transport endpoint is not connected')


def wsl_vanished(tail):
    """Does this solver log tail carry the W3 filesystem-gone signature?"""
    return any(s in (tail or '') for s in WSL_VANISHED)


class WslVanished(RuntimeError):
    """The solver died because WSL was torn down under it (W3). A
    RuntimeError with the same message as any other solver failure, so
    every caller that does not know about auto-resume sees exactly what
    it always did; `backend` catches this one and resumes."""


#: FOAM warnings that are inherent to the collapsed-hex sector/wedge
#: meshes (1D sector, 2D axisym): the apex face degenerates into the
#: default patch, and the 1-degree wedge planarity residual is ~1e-16
#: (pure float round-off - the vendor's own wedge tutorials print the
#: same). Summarized once instead of spamming the log.
BENIGN_WARN = ('undefined faces in mesh; adding to default patch',
               'is not planar')


def stop_grace(spec):
    """writeNow -> kill escalation window: a big mesh needs longer to
    finish the current step + final write."""
    return max(STOP_GRACE_S, spec.n_cells / 2e5)


def common_ready_times(spec, fields):
    """Names of the processor*/ times complete on EVERY rank (an empty
    set when there are none), or None when a rank dir cannot be listed."""
    common = None
    for i in range(spec.n_procs):
        pu = os.path.join(spec.case_unc, f'processor{i}')
        try:
            times = {name for _t, name in reader.list_times(pu)
                     if reader.time_ready(os.path.join(pu, name),
                                          fields)}
        except OSError:
            return None
        common = times if common is None else (common & times)
    return common or set()


def maybe_reconstruct(spec, fields, done=False):
    """Parallel runs: reconstruct processor time dirs that are complete
    on every rank and absent top-level, so the ingest loops read
    reconstructed dirs indistinguishable from serial output. Quietly
    retries next poll on failure. `done` lifts the per-poll batch cap
    (final sweep after the solver exits).

    Returns the times a SUCCESSFUL reconstructPar call covered ([]
    otherwise) - what the HD1-15 purge needs to know is safely at the
    root; every other caller ignores it."""
    if spec.n_procs <= 1 or spec.decomposed:
        # `decomposed` (parallel AMR, N16-b/T42): reconstructPar cannot
        # follow a mesh that changes between writes, so those runs are
        # ingested straight from processor*/ instead.
        return []
    common = common_ready_times(spec, fields)
    if not common:
        return []
    have = {name for _t, name in reader.list_times(spec.case_unc)}
    todo = sorted(common - have, key=float)
    if not done:
        todo = todo[:4]             # bound per-poll reconstruct work
    if not todo:
        return []
    try:
        runner.run_stage(
            spec.case_posix,
            [f'reconstructPar -newTimes -time {",".join(todo)}'],
            timeout=1800)
    except runner.FoamStageError:
        return []                   # transient (mid-write): next poll
    return todo


# ── HD1-15: the decomposed copy of the latest write only ───────────────

_TIME_NAME = re.compile(r'[0-9][0-9.eE+-]*')
_CASE_POSIX = re.compile(r'/[A-Za-z0-9_.+/-]+')


def _is_time(name):
    try:
        v = float(name)
    except (TypeError, ValueError):
        return False
    return bool(_TIME_NAME.fullmatch(str(name))) and np.isfinite(v)


def purge_active(spec):
    """Does this run purge? Only with a write budget, in parallel, and
    never on a decomposed (parallel AMR) run - that one is READ from its
    per-rank copies (N16-b, T42), because a balanced case makes the
    standard reconstructPar fail fatally (blastFoam User Guide v6.0,
    sec. 16.9, p. 136), so those copies are the run's record."""
    return (int(getattr(spec, 'write_budget', 0) or 0) > 0
            and int(getattr(spec, 'n_procs', 1) or 1) > 1
            and not getattr(spec, 'decomposed', False))


def decomposed_purge_plan(done, reconstructed_ok, common_ready, start_dir):
    """Pure. The processor*/<t> times that may be deleted: every t the
    ingest has read (`done`), that a successful reconstructPar covered
    (`reconstructed_ok`), that is not `start_dir`, and that is OLDER than
    the anchor - the newest time complete on every rank (`common_ready`)
    whose own reconstructPar succeeded too. So never the newest complete
    time (a restart reads it), a write still in progress or torn (newer
    than that), the start dir, or anything not yet safely at the root.

    Why the anchor must be reconstructed as well: a failed reconstructPar
    can leave that time's ROOT copy torn, and a resume then walks back
    past it to the newest whole root time (backend._resume_start_time,
    P1-5 - it checks every run, not only AMR) and restarts from that
    time's processor*/ copy, which therefore has to still be there.
    Sorted by time."""
    ok = set(reconstructed_ok or ())
    common = [t for t in (common_ready or ()) if _is_time(t) and t in ok]
    if not common:
        return []
    newest = max(float(t) for t in common)
    keep = str(start_dir)
    return sorted({t for t in (done or ()) if t in ok and t != keep
                   and _is_time(t) and float(t) < newest}, key=float)


def purge_paths(case_posix, n_procs, names):
    """The paths one purge deletes: <case>/processor<N>/<time> for every
    rank and name. Refuses (ValueError) a case that is not a plain
    absolute path under the runs root, a name that is not a written
    time, and a case with fewer than two ranks - the deleter never
    builds anything else."""
    from .env import RUNS_ROOT
    case = str(case_posix or '').rstrip('/')
    parts = case.split('/')
    if (not _CASE_POSIX.fullmatch(case) or '..' in parts or '.' in parts
            or not case.startswith(RUNS_ROOT + '/')
            or len(parts) != len(RUNS_ROOT.split('/')) + 1):
        raise ValueError(f'not a run directory under {RUNS_ROOT}: {case!r}')
    n = int(n_procs)
    if n < 2:
        raise ValueError('only a decomposed (parallel) case has '
                         'processor dirs to purge')
    out = []
    for name in names:
        s = str(name)
        if not _is_time(s) or float(s) < 0.0:
            raise ValueError(f'not a written time: {s!r}')
        out.extend(f'{case}/processor{i}/{s}' for i in range(n))
    return out


#: Windows refuses a command line longer than 32,767 characters
#: (CreateProcess, WinError 206), and the whole rm rides on wsl.exe's. One
#: purge of 60 writes on 13 ranks is about 54,000, so the paths go out in
#: chunks of at most this many characters - one WSL stage per chunk, and
#: a normal purge (a few writes) is still exactly one.
RM_CHUNK_CHARS = 16000


def rm_scripts(paths, limit=RM_CHUNK_CHARS):
    """`rm -rf -- '<path>' ...` lines covering `paths` once each, in
    order, none longer than `limit` characters (a single path always
    gets a line of its own)."""
    head = 'rm -rf --'
    out, cur = [], head
    for p in paths:
        arg = f" '{p}'"
        if cur != head and len(cur) + len(arg) > limit:
            out.append(cur)
            cur = head
        cur += arg
    if cur != head:
        out.append(cur)
    return out


def delete_decomposed(spec, names):
    """rm -rf the processor*/<t> dirs of `names` in WSL (no OpenFOAM env
    needed), one stage per `rm_scripts` chunk so that no purge, however
    many writes it removes, meets Windows' command-line cap. True when
    every stage went through."""
    import subprocess
    from . import env
    paths = purge_paths(spec.case_posix, spec.n_procs, names)
    for script in rm_scripts(paths):
        try:
            res = subprocess.run(env.wsl_plain_argv(script),
                                 capture_output=True, timeout=300,
                                 stdin=subprocess.DEVNULL,
                                 creationflags=env.CREATE_NO_WINDOW)
        except (OSError, subprocess.TimeoutExpired):
            return False
        if res.returncode != 0:
            return False
    return True


def _root_whole(spec, fields):
    """Root times that are complete when the loop starts: on a RESUMED
    run, the writes the session before it reconstructed. Their root
    copies are what the record is read from, which is exactly what a
    successful reconstructPar in this session would have established."""
    try:
        return {name for _t, name in reader.list_times(spec.case_unc)
                if name != str(spec.start_dir)
                and reader.time_ready(os.path.join(spec.case_unc, name),
                                      fields)}
    except OSError:
        return set()


class DecomposedPurge:
    """HD1-15: with a write budget, keep the decomposed copy of the
    LATEST complete write only.

    A parallel run keeps every write twice - reconstructed at the root,
    which is the record, and decomposed in processor*/, which only a
    restart ever reads again, and a restart reads the newest complete
    one. On HD1-3d that second copy was 88 GB of 173 GiB. The purge
    deletes a processor*/<t> once the ingest has read t, a reconstructPar
    covering it has succeeded, and a NEWER time is complete on every
    rank and reconstructed too; never the start dir, never
    processor*/constant, never the root or postProcessing (see
    decomposed_purge_plan and purge_paths).

    Rejected: OpenFOAM's `purgeWrite`, which deletes on the solver's own
    clock and so races the per-poll reconstruct (capped at 4 per poll) -
    a write purged before it was reconstructed would be lost from the
    record. A failed delete is logged once and retried; it never raises.
    Inactive (no listing, no deleter call) without a budget, in serial
    and on a decomposed AMR run."""

    def __init__(self, spec, fields, hooks, delete=None):
        self.spec, self.fields, self.hooks = spec, fields, hooks
        self.delete = delete or delete_decomposed
        self.active = purge_active(spec)
        self.reconstructed = set()
        self.purged = set()
        self._warned = self._said = False
        if self.active:
            self.reconstructed |= _root_whole(spec, fields)

    def covered(self, names):
        """Times a successful reconstructPar just covered."""
        if names:
            self.reconstructed.update(names)

    def _present(self, name):
        """Is `name` still in some processor*/ dir?"""
        return any(os.path.isdir(os.path.join(self.spec.case_unc,
                                              f'processor{i}', name))
                   for i in range(self.spec.n_procs))

    def run(self, done):
        """Purge what the plan allows now; returns the times removed."""
        if not self.active:
            return []
        common = common_ready_times(self.spec, self.fields)
        if not common:
            return []
        # ...and still on disk: a resumed run's earlier session already
        # removed its own older copies, which need no second rm
        plan = [t for t in decomposed_purge_plan(
            done, self.reconstructed, common, self.spec.start_dir)
            if t not in self.purged and self._present(t)]
        if not plan:
            return []
        try:
            ok, why = bool(self.delete(self.spec, plan)), ''
        except Exception as exc:            # noqa: BLE001 - never raises
            ok, why = False, f' ({exc})'
        if ok:
            self.purged.update(plan)
            if not self._said:
                self._said = True
                self.hooks.log(
                    f'  [blastfoam] write budget: keeping the decomposed '
                    f'copy of the latest write only ({len(plan)} older '
                    f'removed; every write stays reconstructed)')
            return plan
        if not self._warned:
            self._warned = True
            self.hooks.log(
                f'  [blastfoam] could not remove the decomposed copies of '
                f'{len(plan)} written time(s){why} - retrying at the next '
                f'poll; the reconstructed copies are untouched')
        return []


def check_stability(st, hooks, t):
    """Latch st['unstable'] when the run has gone numerically unstable.

    Called once per `Time =` line, BEFORE st['t'] is overwritten, so `t`
    is the new value and st['t'] is still the previous one.

    Same shape as the A6 time canary: this only sets a flag and logs
    once - `progress_line` stays a pure module-level function with no
    reference to the loop, and the loop body decides what to do. Returns
    True once tripped.
    """
    if st.get('unstable'):
        return True
    dt, dt_max = st.get('dt', 0.0), st.get('dt_max', 0.0)
    if dt_max > 0.0 and 0.0 < dt < DT_COLLAPSE_FRAC * dt_max:
        st['dt_low'] = st.get('dt_low', 0) + 1
    else:
        st['dt_low'] = 0
    st['t_stuck'] = (st.get('t_stuck', 0) + 1) if t <= st.get('t', 0.0) else 0
    low, stuck = st['dt_low'], st['t_stuck']
    if st.get('step', 0) < MIN_STABLE_STEPS:
        return False
    if not (low >= COLLAPSE_STEPS_HARD
            or (low >= COLLAPSE_STEPS and stuck >= CLOCK_STUCK_STEPS)):
        return False
    st['unstable'] = STOP_UNSTABLE
    pmin = st.get('p_min')
    hooks.log(
        f"  [blastfoam] the solve has gone unstable: deltaT collapsed to "
        f"{dt:.2e} s ({dt / dt_max:.1e} of the {dt_max:.2e} s it had "
        f"reached)" + (f", min(p) = {pmin:.3e} Pa" if pmin is not None else "")
        + f", and the solver clock has not advanced for {stuck} steps at "
        f"t = {t:.6g} s.\n"
        f"  [blastfoam] stopping at the next written frame - waiting it "
        f"out ends in a divide-by-zero density (SIGFPE) with no result at "
        f"all. What is already written is kept; a lower CFL number or a "
        f"lower AMR level usually clears it.")
    return True


#: N5-5. How far blastFoam's own reading of the handed-over energy may
#: sit from the writer's before it is worth saying something.
#:
#: Calibrated, not guessed: on a real foam->foam chain the writer put
#: 2.856593e4 J on the mesh and blastFoam's conservedQuantities read
#: 2.856010e4 - a ratio of 1.000204, whose 0.02 % is the wedge's
#: cos(1 deg) vertex geometry (blockMesh puts the outer face at
#: x*cos(a), _init_cell_volumes integrates the ideal sector). The remap
#: itself conserves to 0.11 % measured on the same hand-off. 2 % leaves
#: an order of magnitude over both.
#:
#: The upper end is set by measurement too, and it is tighter than it
#: looks. Reverting B0 on a small profile stage (lambda.expl stripped,
#: so blastFoam blends the products back to the unreacted Murnaghan
#: reactants) moved the first reading by only -4.3 %: the products are a
#: modest share of a domain that is mostly ambient air, so the signature
#: of a totally destroyed fireball is single-digit percent. 2 % catches
#: that with 2.2x to spare; 5 % would have sailed straight past it.
HANDOFF_E_TOL = 0.02


def check_handoff_energy(st, hooks):
    """Latch once: what blastFoam decoded against what we wrote.

    Same shape as check_stability - sets a flag, logs once, and decides
    nothing. It WARNS and never stops: the run is valid, it just began
    from the wrong energy, and the user needs the number rather than a
    killed solver.

    This is the only check in the codebase that can see across the
    file boundary. Python knows what it MEANT to write; blastFoam's
    volume integral says what it actually decoded, after the EOS
    inversion (guide 5.9) and the lambda blend (5.87). B0 and B1 both
    broke in exactly that gap and neither was visible from either side
    alone.
    """
    if st.get('cons_noted') or not st.get('cons0'):
        return False
    want = st.get('E_expect')
    got = st['cons0'].get('rhoE')
    if not want or not got:
        return False
    st['cons_noted'] = True
    rel = got / want - 1.0
    st['cons_rel'] = rel
    if abs(rel) <= HANDOFF_E_TOL:
        hooks.log(f'  [note] hand-off energy checks out: blastFoam reads '
                  f'{got:.4e} J against the {want:.4e} J written '
                  f'({rel:+.2%})')
        return False
    hooks.log(f'  [warn] hand-off energy mismatch: {want:.4e} J was '
              f'written onto this mesh, blastFoam reads {got:.4e} J '
              f'({rel:+.1%}). The state that arrived is not the state '
              f'that was handed over - suspect the EOS the profile was '
              f'priced with, or lambda.<phase> on the products.')
    return True


def progress_line(line, st, hooks, end_time):
    """Parse one solver stdout line into Progress state. st['frac'],
    when not None, overrides the t/end_time estimate (3D uses the
    shock-front radius, updated per ingested write). FOAM warning
    blocks are multi-line ('--> FOAM Warning :' then From/in file then
    the message) - the actual message is captured and logged; the
    benign sector-wedge warnings collapse into one note."""
    m = _RE_TIME.match(line)
    if not m and not st['step'] and not st.get('time_canary'):
        # never yet seen a `Time = ` line: count how long that lasts
        st['no_time'] = st.get('no_time', 0) + 1
        if st['no_time'] >= TIME_CANARY_LINES:
            st['time_canary'] = True
            hooks.log("  [warn] blastFoam output format changed? no "
                      "'Time =' lines yet - live cadence and progress "
                      "may stall")
    if m:
        t = float(m.group(1))
        check_stability(st, hooks, t)
        st['t'] = t
        st['step'] += 1
        frac = st.get('frac')
        if frac is None:
            frac = min(1.0, st['t'] / end_time)
        hooks.progress(Progress(step=st['step'], t=st['t'], dt=st['dt'],
                                p_max=st['p_max'], frac=frac))
        return
    # conservedQuantities' block (N5-5). Cheap prefix test first:
    # progress_line runs on every stdout line and already spends four
    # regexes here.
    if line[:3] == 'rho' or (line[:1] == ' ' and st.get('cons_field')):
        m = _RE_CONS_HEAD.match(line)
        if m:
            st['cons_field'] = m.group(1)
            return
        if st.get('cons_field'):
            m = _RE_CONS_VAL.match(line)
            if m:
                fld, which = st['cons_field'], m.group(1)
                if which == 'Original':
                    # latched once: the first reading is the one that
                    # says what blastFoam decoded from the fields we
                    # wrote, which is the whole point (B0/B1 both broke
                    # exactly there). Later blocks repeat it unchanged.
                    # `st` seeds these to None, so setdefault on the
                    # dict itself would hand back None, not a dict.
                    if st.get('cons0') is None:
                        st['cons0'] = {}
                    st['cons0'].setdefault(fld, float(m.group(2)))
                else:
                    if st.get('cons') is None:
                        st['cons'] = {}
                    st['cons'][fld] = float(m.group(2))
                    st['cons_field'] = None
                    check_handoff_energy(st, hooks)
                return
            st['cons_field'] = None

    m = _RE_DT.match(line)
    if m:
        st['dt'] = float(m.group(1))
        st['dt_max'] = max(st.get('dt_max', 0.0), st['dt'])
        return
    m = _RE_MAXP.match(line)
    if m:
        st['p_max'] = float(m.group(1))
        if m.group(2) is not None:
            st['p_min'] = float(m.group(2))
        return
    if 'FOAM FATAL' in line:
        hooks.log('  [foam] ' + line.rstrip())
        return
    if 'FOAM Warning' in line:
        st['warn_scan'] = 6         # look for the message just below
        return
    if st.get('warn_scan'):
        st['warn_scan'] -= 1
        ls = line.strip()
        if not ls or ls.startswith('From ') or ls.startswith('in file'):
            return
        st['warn_scan'] = 0
        if any(s in ls for s in BENIGN_WARN):
            if not st.get('warn_benign_noted'):
                st['warn_benign_noted'] = True
                hooks.log('  [blastfoam] note: benign wedge-geometry '
                          'warnings from the sector mesh (collapsed '
                          'apex / ~1e-16 planarity round-off) - '
                          'expected, harmless')
        else:
            hooks.log('  [foam] Warning: ' + ls)


def note_pause(hooks, st, will_pause):
    """One-time note: foam Exec/Interrupt operates at written-frame
    granularity (not per solver step like the native solvers)."""
    if will_pause and not st.get('pause_noted'):
        st['pause_noted'] = True
        hooks.log('  [blastfoam] pausing at a written frame - the WSL '
                  'solver is suspended while paused; Exec advances by '
                  'written frames, Stop ends the run')


def gated_step(run, hooks):
    """step_gate() with the WSL solver truly suspended while the GUI
    holds the gate (SIGSTOP/CONT around the blocking wait)."""
    paused = getattr(hooks, 'exec_paused', None)
    if paused is not None and paused() and not run.stop_requested:
        run.suspend()
        try:
            hooks.step_gate()
        finally:
            run.resume()
    else:
        hooks.step_gate()


def tail_live(spec, hooks, st, live, set_name, decode):
    """Shared live-sample tail (1D line / 2D+3D slice): poll the
    postProcessing/<set_name> dirs, emit at most one hooks.frame per
    call (the newest complete sample), delete consumed dirs so disk
    use stays bounded. `decode(tdir)` -> frame payload or None while
    the sample is still mid-write; a `(field, levels)` tuple carries a
    dynamic-AMR frame's level map. The GUI refresh policy is honored:
    seconds mode throttles wall time, steps mode gates on solver steps
    since the last emitted live frame."""
    entries = reader.list_sample_times(spec.case_unc, set_name)
    fresh = [(t, n) for t, n in entries if n not in live['seen']]
    if not fresh:
        return
    mode, val = hooks.refresh
    if mode == 'steps' and live.get('fo_steps') == max(1, int(val)):
        pass    # the sample cadence IS the policy: every sample shows
    elif not due_sparse(hooks.refresh, st['step'], live):
        return
    for t, name in reversed(fresh):
        payload = decode(name)
        if payload is None:
            continue
        if t >= st['t_frame']:
            field = payload[0] if isinstance(payload, tuple) else payload
            if isinstance(payload, tuple):
                hooks.frame(payload[0], t, levels=payload[1])
            else:
                hooks.frame(payload, t)
            # The same array, to the 3D scene's burst plane. A foam run
            # can only emit a full frame3d when it WRITES - measured at
            # one every 8.6 s on a real 3D run, while this sample was
            # arriving about four times a second from the same case. No
            # extra sampling and no extra disk read: the array is already
            # decoded and about to be dropped.
            if spec.dim == 3 and hooks.wants_surf3d():
                hooks.surf3d(t, field)
            st['t_frame'] = t
            live['step'] = st['step']
            live['draw'] = _time.time()
        for tt, nn in entries:
            if tt <= t and nn not in live['seen']:
                live['seen'].add(nn)
                shutil.rmtree(
                    os.path.join(spec.case_unc, 'postProcessing',
                                 set_name, nn),
                    ignore_errors=True)
        break


def new_live():
    return dict(seen=set(), step=-(10 ** 9), draw=0.0)


def due_sparse(policy, step, last):
    """Refresh-policy check for the foam ingest paths. Unlike the
    native solvers, these are evaluated only when output lands on disk
    - at arbitrary step counts - so steps mode gates on solver steps
    elapsed since the last emitted frame (RunHooks._due's `step % n`
    form would almost never hit here). `last` carries the previous
    emission: 'step' and 'draw' (wall time), as built by new_live()."""
    mode, val = policy
    if mode == 'steps':
        return step - last['step'] >= max(1, int(val))
    return _time.time() - last['draw'] > float(val)


def read_fo_fields(dpath, spec, mesh=None):
    """Optional per-step accumulation fields written by the impulse /
    fieldMinMax function objects (writer plants them for 2D/3D cases).
    Returns (p_peak, impulse) grids or (None, None) when either is
    missing/unreadable - the caller falls back to the Python per-write
    accumulators, so an FO failure degrades instead of stalling.
    `mesh` is the time dir's own structure on a dynamic-AMR run."""
    n = spec.n_cells if mesh is None else mesh.n_cells
    try:
        peak = reader.to_grid(rd_scalar(spec, dpath, 'pMax', n),
                              spec, fill=P_AIR, mesh=mesh)
        imp = reader.to_grid(rd_scalar(spec, dpath, 'impulse', n),
                             spec, fill=0.0, mesh=mesh)
    except (ValueError, OSError):
        return None, None
    return peak, imp


def level_counts(counts):
    """'L0 4,753 / L1 5,776 / L2 161,600' from a MeshMap's counts."""
    return ' / '.join(f'L{l} {int(c):,}' for l, c in enumerate(counts))


def amr_note(mesh, n_prev, t):
    """The per-write AMR log line: cells of this write, change against
    the previous write and the per-level histogram."""
    d = mesh.n_cells - (mesh.n_cells if n_prev is None else int(n_prev))
    return (f'  [blastfoam] AMR t = {t*1e3:.3f} ms: {mesh.n_cells:,} cells '
            f'({d:+,}), {level_counts(mesh.counts)}')


def next_interval(n_frames, progress, interval, interval0):
    """Pure controller for the adaptive writeInterval (3D runs): keep
    the projected total frame count inside the writer's N_WRITES band.
    Returns the new interval, or None for no change. Doubling backs
    off a too-dense start (near-field shock much faster than the sizing
    estimate); halving recovers frames when the front stalls."""
    est_total = n_frames / max(progress, 0.05)
    if est_total > 1.5 * writer.N_WRITES_MAX:
        new = interval * 2.0
    elif est_total < 0.7 * writer.N_WRITES_MIN and progress > 0.15:
        new = interval / 2.0
    else:
        return None
    new = min(max(new, interval0 / 4.0), interval0 * 8.0)
    if abs(new - interval) < 1e-15 * max(interval, 1e-30):
        return None
    return new


def maybe_adapt(spec, st, adapt, run, hooks, n_frames):
    """Apply the adaptive-writeInterval controller (all dims; the
    controlDict is runTimeModifiable). Called once per ingested frame."""
    if not getattr(spec, 'adaptive_write', True):
        return                      # writeInterval pinned for this run
    adapt['since'] += 1
    if adapt['since'] < ADAPT_EVERY or run.stop_requested:
        return
    new_iv = next_interval(n_frames, st.get('frac') or 0.0,
                           adapt['interval'], spec.write_interval)
    if new_iv is not None and runner.rewrite_control_entry(
            spec.case_posix, spec.case_unc, 'writeInterval', new_iv,
            hooks.log):
        hooks.log(f"  [blastfoam] writeInterval "
                  f"{adapt['interval']*1e3:.4f} -> "
                  f"{new_iv*1e3:.4f} ms (adaptive)")
        adapt['interval'] = new_iv
        adapt['since'] = 0
        hooks.cadence(dt=new_iv)    # the live view says how fast it moves


class OrderedIngest:
    """Strictly time-ordered time-dir ingest (ROADMAP B16).

    A pass over `pending()` stops at the first dir that is not ready yet,
    so a later write never lands before an earlier one (which used to
    feed a negative dt to the impulse accumulator and make the recorded
    frame timeline non-monotonic). A dir that stays unreadable for
    STALL_POLLS polls *after a later dir is already complete* is skipped
    for good with one log line; on the final sweep (solver exited, files
    complete) any gap is skipped at once so nothing readable is lost."""

    def __init__(self, spec, fields, hooks):
        self.spec, self.fields, self.hooks = spec, fields, hooks
        self.stalls = {}
        self._times, self._i, self._done, self._final = [], 0, {}, False

    def _ready(self, name):
        """A time is ready when EVERY part of it is - on a decomposed
        AMR run the ranks finish their writes independently."""
        d = self.spec.time_dirs(name)
        parts = d if isinstance(d, (list, tuple)) else [d]
        return all(reader.time_ready(p, self.fields) for p in parts)

    def pending(self, done, final=False):
        """Yield (name, dpath) in ascending time; ends at the first gap.
        `dpath` is a list of per-rank dirs on a decomposed AMR run."""
        self._done, self._final = done, final
        self._times = reader.list_times(self.spec.time_root())
        for i, (_t_disp, name) in enumerate(self._times):
            if name in done or self.stalls.get(name, 0) >= STALL_POLLS:
                continue
            self._i = i
            dpath = self.spec.time_dirs(name)
            if not self._ready(name):
                # the writer's own initial-condition dir, not a solver
                # write: '0' for a charge case, t0 for a profile stage,
                # which under AMR has no cellLevel of its own to be
                # "ready" with (T70). Either way the initial state
                # reaches the view through _initial_frame.
                if _t_disp == 0.0 or name == self.spec.start_dir:
                    continue
                if self.unreadable(name):
                    continue
                return
            yield name, dpath

    def unreadable(self, name):
        """Register that `name` could not be ingested on this poll (not
        ready, or torn mid-write). True -> skip it permanently; False ->
        end the pass and retry it next poll."""
        if self._final:
            inc = STALL_POLLS
        elif any(n2 not in self._done and self._ready(n2)
                 for _t2, n2 in self._times[self._i + 1:]):
            inc = 1                 # later writes are complete: it should be too
        else:
            return False            # newest write still in progress: normal
        n = self.stalls.get(name, 0) + inc
        self.stalls[name] = n
        if n < STALL_POLLS:
            return False
        if self._final:
            self.hooks.log(f'  [blastfoam] time dir {name} incomplete '
                           f'after the solver exited - skipped')
        else:
            self.hooks.log(f'  [blastfoam] time dir {name} stayed '
                           f'unreadable while later writes completed '
                           f'- skipped')
        return True

    def skip(self, name):
        """Never yield `name` again (the caller has already logged why)."""
        self.stalls[name] = STALL_POLLS


class PeakImpulse:
    """Per-write Python p_peak/impulse accumulator with blastFoam's
    per-step pMax/impulse function-object fields layered on top.
    Remembers the time each source last covered so `final()` can tell a
    fresh FO read from a stale one (ROADMAP B17)."""

    def __init__(self):
        self.p_peak = self.impulse = None
        self.t_py = None
        self.fo_peak = self.fo_imp = None
        self.t_fo = None
        self._noted = False

    def add(self, p, t, dpath, spec, hooks, mesh=None):
        """Accumulate one ingested write. False (logged) when t is before
        the last accumulated time - unreachable with OrderedIngest, kept
        as the guard B16 asks for; the caller then skips the dir.
        `mesh` is the write's own structure on a dynamic-AMR run."""
        if self.t_py is not None and t < self.t_py:
            hooks.log(f'  [blastfoam] write t = {t*1e3:.3f} ms arrived '
                      f'after {self.t_py*1e3:.3f} ms - not accumulated')
            return False
        if self.p_peak is None:
            self.p_peak = p.copy()
            self.impulse = np.zeros_like(p)
            t_prev = 0.0
        else:
            np.maximum(self.p_peak, p, out=self.p_peak)
            t_prev = self.t_py
        self.impulse += (p - P_AIR) * (t - t_prev)
        self.t_py = t
        # per-step FO fields (preferred over the per-write accumulators
        # above); t=0 has no FO output yet
        got_peak, got_imp = read_fo_fields(dpath, spec, mesh=mesh)
        if got_peak is not None:
            self.fo_peak, self.fo_imp, self.t_fo = got_peak, got_imp, t
        elif t > 0.0 and self.fo_peak is None and not self._noted:
            self._noted = True
            hooks.log('  [blastfoam] pMax/impulse fields not found '
                      '- peak/impulse tracked per write instead of '
                      'per step')
        return True

    def live(self):
        """(p_peak, impulse) for live frames: FO when it exists."""
        if self.fo_peak is not None:
            return self.fo_peak, self.fo_imp
        return self.p_peak, self.impulse

    def final(self, p_fin, dfin, t_fin, spec, mesh=None):
        """(p_peak, impulse, peak_source) for the Result.
        Order: the final dir's FO fields; an FO read that already covers
        t_fin; the Python accumulator - 'python-fallback' when FO data
        exists but is older than the final frame (the stale-FO case B17
        fixes), 'python-writes' when the case never produced FO fields."""
        if self.p_peak is None:
            self.p_peak = p_fin.copy()
            self.impulse = np.zeros_like(p_fin)
        np.maximum(self.p_peak, p_fin, out=self.p_peak)
        got_peak, got_imp = read_fo_fields(dfin, spec, mesh=mesh)
        if got_peak is not None:
            return got_peak, got_imp, 'foam-fo'
        if self.fo_peak is not None and self.t_fo >= t_fin:
            return self.fo_peak, self.fo_imp, 'foam-fo'
        return (self.p_peak, self.impulse,
                'python-fallback' if self.fo_peak is not None
                else 'python-writes')


class FoamRunLoop:
    """One blastFoam run from `FoamRun` start to solver exit.

    `done` is the caller's dirname -> ... mapping of ingested dirs (the
    1D `store`, the 2D/3D `ingested`); the loop only reads it for
    ordering and for the "no readable time steps" check. `live_set` is
    the postProcessing sample set (`writer.LIVE_SET` / `LIVE_SLICE`)
    decoded by `decode(tdir)` for live frames between writes; None
    (dynamic-AMR runs, whose live frames come from the written times)
    disables the live tail.

    Attributes the callbacks use: `st` (progress state: step/t/dt/
    p_max/frac/t_frame), `live` (live-frame throttle, see new_live),
    `stop_requested`, `request_stop(reason)`, `maybe_adapt(n_frames)`,
    `note_pause(will_pause)`, `gated_step()`. Constructing the loop
    starts the solver, exactly where the inline loops created FoamRun."""

    #: HD1-15 (DecomposedPurge). A class default so a loop assembled
    #: with __new__ (the stop-latency test does) simply has none.
    purge = None
    #: OUT-2 (vtk_export.VtkExport), with the same class-default reason
    vtk = None

    def __init__(self, spec, hooks, fields, done, live_set, decode,
                 read_dir, on_frame):
        self.spec, self.hooks, self.fields, self.done = (spec, hooks,
                                                         fields, done)
        self.live_set, self.decode = live_set, decode
        self.read_dir, self.on_frame = read_dir, on_frame
        self.order = OrderedIngest(spec, fields, hooks)
        # frac starts None on purpose: that is what arms progress_line's
        # t/end_time estimate, so the bar moves from the first solver
        # step instead of sitting at 0 until the first ingested write
        # computes a real shock-front fraction
        self.st = dict(step=0, t=0.0, dt=0.0, p_max=float(P_AIR),
                       frac=None, t_frame=-1.0,
                       # N5-5: conservedQuantities' readings, and
                       # what the writer put on the mesh to compare
                       # them against (None for a charge case - there
                       # is no hand-off to check, and rhoE there is not
                       # conserved anyway: E0 is injected as lambda
                       # goes 0 -> 1, measured at +1169 % before the
                       # open boundary drains it)
                       cons0=None, cons=None, cons_field=None,
                       cons_noted=False,
                       E_expect=((spec.init_state or {}).get('E_total')
                                 if spec.init_state else None))
        self.live = new_live()
        # live-sample cadence [solver steps] the case was written with;
        # _sync_live_steps follows the GUI's "Refresh every N steps"
        self.live_steps = int(getattr(spec, 'live_steps', 0)
                              or writer.live_sample_steps(spec.dim))
        self.live['fo_steps'] = self.live_steps
        self.adapt = dict(interval=spec.write_interval, since=0)
        self.stop_reason = 'safety cap'
        self.stop_deadline = None
        # HD1-15: with a write budget, the decomposed copy of the latest
        # write only - inactive (no listing, no deletes) otherwise
        self.purge = DecomposedPurge(spec, fields, hooks)
        # OUT-2: VTK output into the model folder - inactive (no converter
        # call, no delete) without a VTK family or without a folder (D12)
        from .vtk_export import VtkExport
        self.vtk = VtkExport(spec, hooks, fields)
        self.foam = runner.FoamRun(spec.case_posix, spec.case_unc,
                                   n_procs=spec.n_procs, log=hooks.log)

    @property
    def stop_requested(self):
        return self.foam.stop_requested

    def request_stop(self, reason):
        """Graceful stop: `stopAt writeNow`, then kill after the grace."""
        self.stop_reason = reason
        if not self.foam.request_write_now():
            self.hooks.log('  [blastfoam] graceful stop request did not '
                           'go through - the solver will be killed')
        self.stop_deadline = _time.time() + stop_grace(self.spec)

    def maybe_adapt(self, n_frames):
        maybe_adapt(self.spec, self.st, self.adapt, self.foam, self.hooks,
                    n_frames)

    def note_pause(self, will_pause):
        note_pause(self.hooks, self.st, will_pause)

    def gated_step(self):
        gated_step(self.foam, self.hooks)

    def _sync_live_steps(self):
        """'Refresh every N steps' -> the live-sample function object
        writes every N solver steps (the controlDict is
        runTimeModifiable), so the live view follows the setting
        instead of the fixed per-dim cadence; blank / seconds restore
        the default. One rewrite per change, never retried per poll."""
        if self.live_set is None:
            return
        want = writer.live_steps_for(self.hooks.refresh, self.spec.dim)
        if want == self.live_steps:
            return
        self.live_steps = want
        if runner.rewrite_control_entry(
                self.spec.case_posix, self.spec.case_unc, 'writeInterval',
                want, self.hooks.log, within=self.live_set):
            self.live['fo_steps'] = want
            self.hooks.cadence(steps=want)
            self.hooks.log(f'  [blastfoam] live sample every {want} '
                           f'solver step(s)')
        else:
            self.live['fo_steps'] = None    # tail falls back to due_sparse

    def _ingest_live(self):
        if self.live_set is None:
            return
        self._sync_live_steps()
        tail_live(self.spec, self.hooks, self.st, self.live, self.live_set,
                  self.decode)

    def _check_stop(self):
        """Turn the user's Stop into `stopAt writeNow` HERE, between the
        expensive pieces of the ingest, instead of at the top of the
        next lap.

        Same shape, and the same reason, as the live-tail servicing
        below: one lap of `_ingest_ready` can hold four `reconstructPar`
        runs and a full-field read per pending write. Measured on a
        small parallel 3D case, mean 0.09 s but 3.9 s at worst (and
        about 12 s on a big one, T61). The stop flag used to be read
        only after all of that, so pressing Stop bought a wait of
        anywhere between zero and one whole lap before blastFoam was
        even told - pure latency, with no work done in exchange for it.

        Nothing else moves: the ingest carries on and still drains what
        is on disk, `run()` keeps its own check (this one merely gets
        there first), and because `request_stop` latches
        `foam.stop_requested`, an explicit user stop still wins over the
        instability stop and keeps its own reason.
        """
        if self.foam.stop_requested or not self.foam.running:
            return
        if self.hooks.should_stop():
            self.request_stop('stopped by user')

    def _ingest_ready(self, final=False):
        # The live view is serviced BETWEEN the expensive pieces of this
        # method, not only once per loop iteration.
        #
        # Measured on a real 3D foam run: the live tail was called five
        # times a second at the start and four times in the last fifty
        # seconds, while 104 decoded samples piled up unread on disk.
        # The reason is here - one iteration of `run()` calls the live
        # tail once and then does up to four `reconstructPar` runs and
        # every pending write's full-field read, which together took
        # about twelve seconds by the end. The live view degraded to the
        # WRITE cadence exactly when a blast is most worth watching.
        self._covered(maybe_reconstruct(self.spec, self.fields))
        self._ingest_live()
        if not final:
            self._check_stop()
        for name, dpath in self.order.pending(self.done, final):
            try:
                payload = self.read_dir(name, dpath)
            except (ValueError, OSError):
                if self.order.unreadable(name):
                    continue
                break               # mid-write over 9p; retry next poll
            if self.on_frame(name, dpath, payload) is False:
                self.order.skip(name)   # refused for good, not retried
            # reading a written time is a full-field read plus whatever
            # the 3D feed costs; another one may be queued right behind
            # it, so give the live view its turn in between
            self._ingest_live()
            # ...and let the user's Stop out at the same points; `final`
            # is excluded because the solver has already exited by then
            # and a writeNow request would only log that it failed
            if not final:
                self._check_stop()
        self._purge_decomposed()
        self._export_vtk(final)

    def _covered(self, names):
        """Tell the HD1-15 purge (and the OUT-2 export) what a
        reconstructPar just covered."""
        if self.purge is not None:
            self.purge.covered(names)
        if self.vtk is not None:
            self.vtk.covered(names)

    def _purge_decomposed(self):
        """HD1-15: drop the decomposed copies the root now holds for good
        (DecomposedPurge; a no-op without a write budget). Runs after
        every ingest pass, the final sweep's included."""
        if self.purge is not None:
            self.purge.run(self.done)

    def _export_vtk(self, final=False):
        """OUT-2: convert, copy and delete what the VTK export allows now
        (VtkExport; a no-op without a family or a model folder). After
        every ingest pass and on the final sweep, which converts every
        ingested write before finalize reads the ones it keeps."""
        if self.vtk is not None:
            self.vtk.run(self.done, final)

    def protect(self, name, why='read'):
        """The backend: finalize re-reads written time `name` - never
        delete it (OUT-2, D1). `why` keys the reason (VtkExport.protect)."""
        if self.vtk is not None:
            self.vtk.protect(name, why)

    def unprotect(self, name, why='read'):
        if self.vtk is not None:
            self.vtk.unprotect(name, why)

    def run(self):
        """Drive the solver to completion (or stop/kill). Returns the
        stop reason; raises RuntimeError when the solver failed or
        produced no readable time step (case dir kept either way)."""
        spec, hooks, foam = self.spec, self.hooks, self.foam
        try:
            while True:
                for line in foam.drain(POLL_S):
                    progress_line(line, self.st, hooks, spec.end_time)
                self._ingest_live()
                self._ingest_ready()
                if hooks.should_stop() and not foam.stop_requested:
                    self.request_stop('stopped by user')
                # after the user's stop, so an explicit stop still wins
                # and keeps its own reason
                if self.st.get('unstable') and not foam.stop_requested:
                    self.request_stop(STOP_UNSTABLE)
                if self.stop_deadline and foam.running \
                        and _time.time() > self.stop_deadline:
                    hooks.log('  [blastfoam] solver did not stop cleanly '
                              '- killing it')
                    foam.kill()
                if not foam.running:
                    for line in foam.drain(0.05):
                        progress_line(line, self.st, hooks, spec.end_time)
                    self._covered(maybe_reconstruct(spec, self.fields,
                                                    done=True))
                    self._ingest_ready(final=True)  # final sweep - files complete
                    break
        finally:
            # give a solver that is already tearing down a moment to
            # reach its graceful End: the ingest breaks out the instant
            # the final write LANDS, while blastProbes only flushes its
            # buffered gauge samples in the FO destructors - killing
            # here threw those samples away on every stopped run (and
            # on every resumed one, T43/N6: 5 of ~600 samples survived)
            for _ in range(100):
                if not foam.running:
                    break
                _time.sleep(0.1)
            if foam.running:
                foam.kill()
            foam.release()          # the W3 keepalive session
            if self.vtk is not None:
                self.vtk.close()    # a foamToVTK still running (OUT-2)
            # live samples are display-only; drop the leftovers so a kept
            # case dir holds just the real record (time dirs + probes)
            if self.live_set:
                shutil.rmtree(os.path.join(spec.case_unc, 'postProcessing',
                                           self.live_set),
                              ignore_errors=True)

        if foam.returncode not in (0, None) and not foam.stop_requested:
            tail = foam.tail()
            err = WslVanished if wsl_vanished(tail) else RuntimeError
            raise err(
                f"blastFoam failed (exit {foam.returncode}) - case kept at "
                f"{spec.case_unc}\n{tail}")
        if not self.done:
            raise RuntimeError(
                "blastFoam produced no readable time steps - case kept at "
                f"{spec.case_unc}\n{foam.tail()}")
        return self.stop_reason
