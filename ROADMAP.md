# blastlab — Roadmap

## State of the project (reviewed 2026-08-18)

The tool is in strong shape at its core: the `solver='blastfoam'` backend is
feature-complete for uniform-mesh cases (serial + MPI, binary writes, FO-based
pMax/impulse, multi-charge, obstacles 2D+3D, adaptive writeInterval, post-mortem
loading), and the physics agrees: this review re-ran the full non-WSL matrix
(writer/reader/validate/adaptive/live-due/gui-drain/regression/blast2d/blast3d),
`test_foam_env` (live probe), `test_foam_3d_smoke --tiny`, `_e2e_foam_obstacle3d`,
`test_foam_1d_vs_native` (peaks within 2–7% of native at r=1–4 m), `test_foam_2d`
(axisym + planar) and the real-GUI `_e2e_gui_foam` — **all green**. The weak spots found by this review are not in the
solvers but around them: (a) a class of crash bugs on the *stop/kill/mid-write*
paths that can throw away an otherwise-good run, (b) Results-panel display bugs
(wrong replay slice, missing final viewer frame, Pa-vs-kPa labeling), (c) native
solver warnings that never reach the GUI, and (d) ops hygiene — the WSL runs dir
measured **7.7 GB** during this review with no automatic cleanup. Every item below
carries What/Why/How/Effort(S/M/L)/Confidence; nothing marked "hypothesis" has
been observed live.

### Top 5 next actions
1. **Harden the stop/ingest path** (B1+B2): fix the `uniform`-field
   `AttributeError` escape and guard the finalize re-reads — today a user Stop on
   a big mesh can crash the run loop and lose the entire Result. Small, surgical.
2. **Fix the two wrong-data display bugs** (B3+B4): 3D animation replay ignores
   the selected slice (crash or silently wrong plot), and the 3D viewer's
   playback history usually lacks the true final frame. Users trust what they see.
3. **Make chains validated and foam preflight visible/stoppable** (B5+B6): the
   Chain tab currently bypasses `validate_case` and a foam stage in a chain
   always dies at runtime; a WSL cold start shows a blank log for minutes with
   Stop inert.
4. **Surface p_peak/impulse + a per-gauge engineering summary in Results**
   (N1+N2): the numbers people transcribe into reports exist in meta and are
   invisible. Highest user-value feature, mostly wiring.
5. **Run-dir hygiene + foam run browser** (N8): 7.7 GB measured; cleanup is
   CLI-only and has no live-run guard (B14). One dialog + an age/size sweep.

## Test matrix (all green as of 2026-08-18)
```
cd blastlab/tests
python test_regression.py         # native byte-parity - MUST stay green
python test_foam_writer.py        # case-generation goldens (no WSL)
python test_foam_reader.py        # ascii+binary parsers, probes merge (no WSL)
python test_case_validate.py      # cap gating per backend (no WSL)
python test_adaptive_interval.py  # writeInterval controller (no WSL)
python test_foam_live_due.py      # live-frame cadence gate (no WSL)   [was missing from this list]
python test_gui_drain.py          # GUI queue-drain resilience (no WSL)
python test_foam_ingest_order.py  # ordered ingest + peak/impulse accumulator (no WSL)
python test_blast2d.py            # 2D native physics suite
python test_blast3d.py            # 3D native physics suite
python test_foam_1d_vs_native.py  # physics gates (~2 min, WSL)
python test_foam_2d.py            # axisym + planar (~3 min, WSL)
python test_foam_3d_smoke.py --tiny
python test_foam_parallel.py      # np1 vs np2 + determinism (~5 min, WSL)
python test_foam_postmortem.py    # live-vs-loaded round trip (WSL)
python test_foam_features.py      # multi-charge + activation none (WSL)
python test_foam_kb_anchor.py     # KB free-air + C4/TNT (~2 min, WSL)
python test_foam_stop.py          # SIGSTOP/writeNow regression (WSL)
python _e2e_foam_obstacle2d.py / _e2e_foam_obstacle3d.py   # obstacle e2e (WSL)
python _e2e_gui_foam.py           # real-GUI session (WSL)
```

---

## 1. Bugs & correctness (ranked by severity)

**B1 — Truncated `uniform` internalField raises AttributeError, escaping every
mid-write retry guard. DONE (2026-09-02).** `read_scalar`/`read_vector` now
raise `ValueError('truncated uniform field: <path>')` when the regex fails (or
matches the wrong shape), so the ingest guards retry as designed; fixture
`tests/foam_fixtures/p_uniform_truncated` (real `p_uniform` cut before the
`;`) plus scalar/vector checks in `test_foam_reader.py`. *Original entry:* *What:* `reader.py:124-126` (and `read_vector`,
`reader.py:141-145`): when `_kind` says `uniform` but the file is torn before the
`;`, the regex returns `None` and `.group()` raises `AttributeError` — but every
ingest/retry site catches only `(ValueError, OSError)` (`backend.py:408,693,1177`),
so the run loop dies instead of retrying. *Why:* a 9p mid-write read can kill a
long run outright. *How:* raise `ValueError` when the regex fails (one line per
reader function); add a truncated-uniform fixture to `test_foam_reader.py`.
*Effort:* S. *Confidence:* parser bug **confirmed by execution** on a torn
fixture; hitting it live is code-read.

**B2 — Kill-escalated stop can crash finalize and lose the whole Result.
DONE (2026-09-02).** `backend._final_read()` re-reads the newest ingested dir
and, on `ValueError`/`OSError`, logs `[blastfoam] final write <t> ms
unreadable - using previous write <t> ms`, drops that dir (and any snapshot
pick on it) and finalizes from the previous write; `RuntimeError` only when
nothing survives. Wired into `_finalize_1d/2d/3d`; `T` added to the 1D/2D
readiness tuples. `postmortem.load_run` skips unreadable dirs with a log
line and walks its grid-sanity probe back from the newest dir.
*Original entry:* *What:* `_finalize_1d/2d/3d` re-read the final time dir (`alpha`, `T`, `U`…)
with no try/except (`backend.py:504-513, 786-816, 1303-1317`), but
`reader.time_ready` checks only file *existence* and the ingest loops
content-verify only `p`; `T` isn't in the readiness tuple at all. A user stop
that escalates to `run.kill()` mid final write leaves a half-written dir that
passes readiness, then finalize raises and `solve_*_foam` throws away all the
good frames. `postmortem.load_run` shares the same unguarded reads
(`postmortem.py:127-136,153-157`). *Why:* the data-loss lands exactly on the
"user pressed Stop" path the backend is designed to survive. *How:* wrap
finalize reads; on failure drop the last dir and finalize from the previous
ingested one (both live and postmortem paths). *Effort:* S–M. *Confidence:*
code-read (trigger path is a designed-for scenario, not observed live).

**B3 — GUI 3D animation replay hardcodes the x-z plane; wrong axes/mask or a
crash for other slice choices. DONE (2026-09-02).** `results_panel._setup_anim`
now branches on `meta['slice_axis']`/`meta['s0']` exactly as
`output/animation.py` does (face pair, axis labels, solid-mask slice, plane
position in the title) instead of always reading `x_face`/`z_face` and
`solid[:, j0, :]`. `test_gui_results_anim.py` builds fake x/y/z-sliced 3D
results and drives `_setup_anim`/`_show_frame`; it reproduces the old
broadcast `ValueError` for the x and z axes and passes with the fix.
*Original entry:* *What:* `results_panel.py:300-305` always uses
`x_face`/`z_face` + `solid[:, j0, :]`, but recorded frames follow the user's
`slice_axis`/`slice_pos` (`solver3d.py:456,538`). With `slice_axis='z'` the
shapes mismatch (broadcast ValueError) — or, for cubic domains, it silently
renders the wrong plane with the wrong obstacle mask and axis labels. The
file-export path (`output/animation.py:44-59`) does it correctly. *Why:* users
see wrong data with no hint. *How:* store `slice_axis`/`s0` in meta (foam 3D
already does) and mirror `animation.py`'s axis selection in the replay setup.
*Effort:* S. *Confidence:* code-read (shapes traced; spot-verified this review).

**B4 — The final frame of a run is usually missing from 3D viewer playback.
DONE (2026-09-02).** The transport now carries `final` explicitly:
`('frame', t, payload, final)` in both the standalone-viewer multiprocessing
queue (`client.py`) and the embedded-panel path (`view3d_panel.on_frame`,
fed through `GuiHooks.frame3d`'s coalesced latest-wins slot, which keeps
`final` sticky against being overwritten). `BlastScene.on_message` passes
`force=final` into `FrameStore.append` - never `self.done`. Playback replay
(`open_playback`, `View3DPanel.feed_result`) tags the last snapshot
`final=True` too. *Original entry:* *What:* `viewer.py:436` passes
`force=self.done`, which is False when the forced
final frame arrives ('done' comes after it), so `FrameStore.append` drops it
whenever the thinning stride is >1 — the common case on long runs. Same gap in
the embedded panel (`view3d_panel.py:316`). *Why:* scrubbing after a run can't
reach the true final state. *How:* tag the final frame in the transport
(`('frame', t, payload, final)`) and pass `force=True` into `store.append` in
both hosts. *Effort:* S. *Confidence:* FrameStore rejection **confirmed by
execution**; wiring code-read.

**B5 — Chain runs bypass `validate_case`, and a foam 2D/3D chain stage always
dies at runtime. DONE (2026-09-02).** New `chain_panel.stage_errors()` (pure,
so it is unit-tested without driving Tk) validates every stage *after* the
profile hand-offs are wired - the wiring is what creates the rejected
combination - and reports one dialog of `Stage <n> (<n>D): <message>` lines
without starting the run. For a foam stage fed by a profile it replaces
`validate_case`'s generic wording with "blastFoam stages cannot start from a
profile yet (ROADMAP N7) - run this stage with the native solver, or drop the
stage that feeds it". ⚠ Needed a companion change: a downstream stage's
profile input does not exist yet at validation time (the stage before it
writes it during the run), so a naive per-stage validate blocked *every*
chain. `validate_case(case, pending_inputs=True)` now waives exactly that
existence check and nothing else; the chain passes it for every stage but the
first. Both the refusal and the waiver's narrowness are pinned in
`test_case_validate.py`. *Original entry:* *What:* `chain_panel.py:117-157` → `app.py:271-273` never
validates; the auto-wiring sets `init_mode='profile1d'` which the foam backend
rejects in preflight (`case.py:233-235`), so a chain with a foam later stage is
guaranteed a traceback + "Run failed" box instead of a pre-run message. *Why:*
the chain feature looks broken for foam users; even plain geometry errors only
surface mid-run. *How:* run `validate_case` per stage after auto-wiring in
`ChainPanel`; show per-stage errors before starting. *Effort:* S. *Confidence:*
code-read (certain).

**B6 — Stop cannot interrupt foam preflight/meshing, and the log is blank
during the WSL probe. DONE (2026-09-02).** `_preflight` now logs
"checking WSL / blastFoam availability..." *before* the probe and runs the
probe on a helper thread while polling `should_stop` every 0.25 s; the mesh
pipeline is a list of `(label, command)` stages run one `wsl.exe` call each
(no more `&&` chain), with a stop check between them, the label logged as each
starts, and `runner.run_stage_stoppable` polling `should_stop` *during* a
stage - a stop kills the relay, which takes the WSL-side command with it.
Warnings are still scanned once over the combined output so the benign
wedge-warning note stays collapsed. A stop in this window raises the new
`hooks.StoppedBeforeStart`, which the GUI worker reports as a quiet log line
rather than a "Run failed" dialog: nothing was computed, so there is no
partial Result to post (the brief suggested fabricating an empty one - that
would have added a dead Results entry and risked a KeyError in the 1D gauge
figure). Measured live in `test_foam_stop.py`: stop during `blockMesh` returns
in 0.4 s with no mesh/solver process left in WSL. *Original entry:* *What:* `_preflight` calls `env.check_available()`
(3 retries × up to 90 s, `env.py:139-193`) before the first `hooks.log`, and
meshing runs through synchronous `run_stage` with no `should_stop` checks
(`runner.py:39-47`); `should_stop` is only consulted in the solve loop
(`backend.py:451`). *Why:* on a WSL cold start the user stares at a cleared log
and 0% bar for minutes with Stop doing nothing. *How:* log "checking WSL…"
before the probe; poll `should_stop` around the probe and between per-command
`run_stage` calls (split the `&&` chains). *Effort:* M. *Confidence:* code-read
(worst-case durations, not typical).

**B7 — Foam progress bar sits at 0 until the first write: the t/end_time
fallback is dead code. DONE (2026-09-02).** All three solve loops now build
`st` with `frac=None`, which is what arms `_progress_line`'s t/end_time
estimate; the first ingested write still overrides it with the real
shock-front fraction, and `_next_interval` already read it as `or 0.0`.
Measured on a live 1D foam run: 1505 progress events, **none** at 0.0 (first
frac 2.0e-06), where every pre-write event used to be exactly 0. Unit-pinned
in `test_foam_live_due.py` (fallback armed, tracks t/end_time, clamps at 1.0,
and yields to an ingested fraction). *Original entry:* *What:* `backend.py:169-171` treats `frac is None` as
the fallback trigger, but `st` initializes `frac=0.0` in all three dims
(`backend.py:374,658,1133`). *Why:* early foam runs look hung. *How:* initialize
`frac=None` (one line ×3); this replaces old GUI item 6(c), which asked for a
feature the code already contains. *Effort:* S. *Confidence:* code-read,
spot-verified (two independent reviews found it).

**B8 — Unit inconsistency: 3D figures label overpressure in Pa, 2D in kPa; GUI
3D colorbars have no units at all. DONE (2026-09-02).** `figures_fields_3d`
now converts to kPa and labels `'Overpressure [kPa]'` like the 2D figures;
`results_panel._draw_field` gives every GUI colorbar units - `Density
[kg/m³]`/`Speed [m/s]` for the 2D fields, and for the 3D slice fields a
label built from the actual slice (e.g. `"Overpressure [kPa] — x-z slice at
y = 0.50 m"`) instead of the bare field key. Verified: `test_regression.py`
stays byte-identical (figures are not pinned), `test_blast2d.py` and
`test_viz3d_scene.py` stay green, and sample 2D/3D/GUI PNGs were eyeballed
in the scratchpad. *Original entry:* *What:* `plots.py:246,253` ("Overpressure
[Pa]") vs `plots.py:221-222` (kPa); `results_panel.py:263-264` gives 3D
overpressure the literal label "overpressure (x-z)" with raw-Pa data, and
speed/density GUI colorbars carry no units. *Why:* the same quantity differs by
1000× between a 2D and a 3D run of the same case — a genuine trust hazard.
*How:* standardize on kPa (convert in the 3D panel + plots) and add units to
every colorbar label. *Effort:* S. *Confidence:* code-read.

**B9 — Displayed "Impulse [Pa s]" is *net* overpressure impulse (negative phase
included), not positive-phase impulse. RELABELED (2026-09-02) — positive-phase
accumulator still open, tracked for T12.** Renamed to `"Net overpressure
impulse [Pa·s]"` in `viz3d/viewer.py`'s `FIELDS` (colorbar title) and to
`"Net ovp impulse"` in `view3d_panel.FIELD_LABELS` (compact control-column
label, matching the terseness of its neighbours); `blastlab/README.md` now
explains net vs positive-phase impulse next to the field list.
*Original entry:* *What:* `solver3d.py:484` and the foam
FO (`writer.py:459` with `pRef = P_AIR`; `backend.py:1186`) accumulate
∫(p−p₀)dt over the whole record — consistent native↔foam (good), but the map
*decreases* after the negative phase passes, and blast engineering convention
("impulse" in KB tables) is positive-phase. *Why:* transcribed numbers are
systematically low vs published data. *How:* short-term relabel "net ovp
impulse"; longer-term add a positive-phase accumulator (`max(p−p₀,0)` in the
Python fallback is trivial; the foam FO would need `pMin`-style clamping or
post-processing). *Effort:* S (relabel) / M (positive-phase). *Confidence:*
code-read.

**B10 — Native gauge TSVs end with a duplicated timestamp row. DONE
(2026-09-05, re-baselined with B12/B18).** The finalization record in all three
solvers is skipped when `t` equals the last loop-top record (identical guard
×3: `and (not gauge_times_list or gauge_times_list[-1] != t)`); the loop exits
via `break` at its top in the common case, which is exactly when the two
coincided. In the new baseline every gauge file's last two timestamps are
distinct. *Original entry:* *What:* all
three solvers record gauges at loop top and again in finalization at the same t
(`solver1d.py:170-173` + `246-249`, `solver2d.py:324-327` + `413-416`,
`solver3d.py:424-427` + `529-532`). *Why:* dt-based post-processing
(`np.gradient`, trapezoid with `diff(t)`) hits a zero interval → inf/nan.
*How:* skip the final record if t equals the last recorded t. ⚠ Byte-pinned
baselines — land with a deliberate re-baseline. *Effort:* S (+re-baseline).
*Confidence:* **confirmed** in the pinned baselines (`b1_gauges.txt`,
`b2_gauges.txt` end with two identical rows).

**B11 — Native solver warnings never reach the GUI (prints bypass hooks).
DONE (2026-09-02).** All 74 solver `print(` sites (16 / 25 / 33 in
solver1d/2d/3d) became `hooks.log(` mechanically (`sed`, then counted): every
site sits inside `_run_blast_*d` after its `hooks = ConsoleHooks(n)` default,
so `hooks` is always bound, and no `end=`/`sep=`/multi-arg prints existed.
`ConsoleHooks.log` is literally `print(msg)`, so the CLI and the byte-pinned
transcript are unchanged - `test_regression.py` is green with **no
re-baseline**. The "default hooks that print" the brief asks for is exactly
`ConsoleHooks`, which already did; `RunHooks` (the documented no-op base) is
deliberately left silent, so bare `RunHooks()` callers now run quietly
(`test_viz3d_hooks.py` still passes). `GuiHooks.log` already forwarded to the
log pane - proven end-to-end by the new `_e2e_gui_native_warn.py`: a native
planar 2D run with a gauge inside an obstacle now shows "[warn] Gauge (1.4,
0.3) inside an obstacle - dropped" in the GUI log. Still stdout-only (not
solver code, out of this item's scope): the output helpers' "Gauge data
saved" / "Plot saved" / profile-saved lines. *Original entry:*
*What:* solvers `print()` directly (`solver1d.py:147-158`, `solver2d.py:257-295`,
`solver3d.py:329-392`) despite the hooks contract (`hooks.py:3-4`); nothing
redirects stdout in the GUI. *Why:* "Gauge … dropped", "Charge truncated by
wall", auto-refine notes and the run summary are invisible to GUI users — a
dropped gauge just silently vanishes from results. *How:* route prints through
`hooks.log` with a default implementation that prints (preserving the
byte-pinned transcript) while `GuiHooks.log` forwards to the log pane. *Effort:*
M (touches all solvers; transcript bytes must stay identical). *Confidence:*
code-read + grep-confirmed.

**B12 — 1D snapshot scheduling still uses the acoustic-time estimate;
intermediate snapshots are mostly never taken. DONE (2026-09-05,
re-baselined).** 1D now triggers on shock-front radius like 2D/3D
(`snap_radii = linspace(r_exp, radius_m, n+1)[1:-1]`, front = outermost cell
above `arrival_p`), and its `n_snapshots` semantics are aligned to 2D/3D's
"n total including the final" (was n intermediate + final, which mostly never
fired) - documented in the `_run_blast_1d` docstring; this closes the old
nice-to-have about the 1D/2D/3D count mismatch. Baseline transcript gains
exactly one `Snapshot saved: t = 0.496 ms` line for the n=2 case.
*Original entry:* *What:* `solver1d.py:124-128`
(`linspace(0, 1.5*R/c_amb)`) — the run stops at shock arrival far earlier;
2D/3D switched to front-position triggers for exactly this reason
(`solver2d.py:232-235`). *Why:* users ask for N snapshots, get only the final.
*How:* front-radius-triggered snapshots as in 2D. ⚠ Changes byte-pinned stdout
→ re-baseline. *Effort:* S (+re-baseline). *Confidence:* **confirmed** — the
pinned baseline transcript's 1D run records zero intermediate snapshots.

**B13 — Runs-directory name collision: 1-second timestamp, no uniqueness.
DONE (2026-09-02).** `new_case_dir` appends the launching process's pid and a
per-process counter (`20260902-190039_3d_p1456-00`), so parallel test
processes, GUI + CLI and back-to-back chain stages cannot share a directory;
`write_case` then *claims* a fresh dir with `os.makedirs(exist_ok=False)`, so
any residual collision fails loudly instead of silently rewriting a live run's
controlDict and 0/ fields. An explicit `case_posix` (resume/post-mortem) keeps
the permissive create. Checks in `test_foam_env.py` (uniqueness across a
burst) and `test_foam_writer.py` (second fresh run refuses the dir; explicit
path still reuses); goldens unchanged - the dir name never enters the rendered
case text. *Original entry:* *What:* `env.py:61-66` + `write_case`'s `exist_ok=True`: two same-dim runs in
the same wall-second share a case dir; the second rewrites `controlDict`/`0/*`
under the first, and both fight over `.run.pid` (signals hit the wrong process).
*Why:* parallel test processes or GUI+CLI can silently corrupt each other.
*How:* add a PID/counter suffix, or `exist_ok=False` + retry with suffix.
*Effort:* S. *Confidence:* code-read.

**B14 — `--clean-foam-runs` has no live-run guard; orphaned WSL solvers are
never reaped. DONE (2026-09-02).** `.run.pid` now carries two lines - the
WSL-side solver pid and the Windows-side owner pid (the Python process that
launched it) - written by the same shell that starts the solver; all
signalling reads line 1 only (`head -n1`). On top of that,
`env.scan_runs`/`runs_alive`/`run_is_alive` answer liveness for a whole list of
run dirs in ONE `wsl.exe` round trip (`kill -0`), and report `None` - never
`False` - when WSL could not be asked, so a failed probe can never read as
"nothing is running". `clean_runs` deletes only provably-dead dirs, lists the
skipped ones (`<- RUNNING, skipped`) and takes `--force`; `env.reap_orphans`
TERM->KILLs solvers whose owner pid is provably gone (`_win_pid_alive` uses
OpenProcess, *not* `os.kill`, which on Windows terminates the target), and is
wired into the clean path plus `python -m blastlab --reap-foam-runs`.
`postmortem.list_runs(check_alive=True)` exposes the same flag for T14's
browser. Verified live: a run started by another process was skipped by
`clean_runs` while solving, and a fabricated orphan (relay alive, owner pid
dead) was reaped while a still-owned run beside it kept running.
⚠ Follow-up decision for T14: reaping is NOT called automatically at GUI
startup - a GUI launch would then kill a CLI run started from another window.
It stays explicit (`--reap-foam-runs`, or the clean path) until the run browser
can show the user what it is about to reap. *Original entry:* *What:* `cli_run.py:99-102` `rm -rf`'s every run dir even while
another process is mid-solve; and if Python dies hard, the WSL solver runs to
`endTime` (hours for big 3D) with nothing reaping it despite `.run.pid`
existing per case. *Why:* data loss / silent CPU burn. *How:* skip dirs whose
`.run.pid` is alive (and offer `--force`); at startup (or via the run browser)
reap stale pids. *Effort:* S. *Confidence:* code-read.

**B15 — Uncaught `TimeoutExpired` in stop/pause/kill signal paths.
DONE (2026-09-02).** `rewrite_control_entry` and `FoamRun._signal` catch
`TimeoutExpired`/`OSError`, log `[blastfoam] WSL did not answer to ...` and
return False; `kill()` escalates through a wedged signal and never raises
out of a caller's `finally`. `FoamRun` takes a `log` callback (the backend
passes `hooks.log`), so the degradation is visible in the run log.
*Original entry:* *What:*
`runner.rewrite_control_entry` (`runner.py:66-73`) and `FoamRun._signal`
(`runner.py:180-184`) don't catch `subprocess.TimeoutExpired`; if WSL wedges —
the exact moment you're trying to stop — `kill()`/`suspend()` raise, masking
the original error in `finally` blocks, and the Windows-side fallback kills only
the wsl.exe relay, not the Linux solver. *Why:* the escalation contract quietly
breaks when it's most needed. *How:* catch + degrade (log, fall through to next
escalation step). *Effort:* S. *Confidence:* code-read.

**B16 — Out-of-order ingestion can corrupt the Python impulse fallback and the
recorded-frame timeline. DONE (2026-09-05).** `backend._OrderedIngest` drives
all three ingest loops: a pass ends at the first time dir that is not ready
(or tears mid-read) so a later write never lands before an earlier one; a dir
that stays unreadable for 20 polls *after a later dir is complete* is skipped
for good with one `[blastfoam] time dir <n> stayed unreadable ... - skipped`
line (the newest write still in progress never counts); the final sweep skips
gaps at once so nothing readable is lost. `_PeakImpulse.add` refuses t < t_prev
with a log line (belt and braces). `test_foam_ingest_order.py` drives both
with fake time dirs (no WSL). *Original entry:* *What:* ingest loops `continue` past an unreadable
earlier time dir and ingest a later one first (`backend.py:396-409,685-695,
1166-1179`); the late-arriving earlier dir then adds a *negative* dt to
`impulse += (p-P_AIR)*(t-t_prev)` (`backend.py:1186`) and makes `meta['frames']`
non-monotonic. Post-mortem replays sorted, so live and loaded results silently
disagree. *Why:* wrong numbers with no error, if a 9p visibility anomaly occurs.
*How:* buffer out-of-order dirs and ingest strictly in time order (or skip an
earlier dir permanently once a later one is ingested, logging it). *Effort:* S.
*Confidence:* code-read; trigger is **hypothesis** (needs a 9p anomaly).

**B17 — Stale 'foam-fo' peak/impulse when the final dir's FO read fails; 2D has
no fallback at all. DONE (2026-09-05).** One `backend._PeakImpulse` (per-write
Python maps + the per-step FO fields, each with the time it last covered) is
shared by the 2D/3D live loops and `postmortem.load_run`; `final()` prefers the
final dir's FO, then an FO read that already covers t_fin, else the Python maps
labelled `peak_source='python-fallback'` (FO existed but is older than the final
frame) or `'python-writes'` (no FO at all). 2D Results now always carry
p_peak/impulse/peak_source. *Original entry:* *What:* `backend.py:1325-1333` — on final-dir FO failure
the result keeps an earlier-time FO accumulation labeled `peak_source='foam-fo'`
and discards the fresher Python accumulator; 2D drops p_peak/impulse entirely
(acknowledged comment, `backend.py:842-847`). *Why:* under-reported impulse
looks authoritative. *How:* prefer the Python accumulator when FO's last read
is older than the last ingested frame; add a 2D Python fallback (same code as
3D). *Effort:* S–M. *Confidence:* code-read.

**B18 — Grids silently shrink up to one cell when dx doesn't divide L. DONE
(2026-09-05, re-baselined + goldens regenerated).** `core/grid.py` lays every
axis out in `N = round(L/dx)` whole cells with `dx_eff = L/N` (exact domain);
when dx divides L the faces are bit-identical to the old `i*dx` (verified for
all 7 baseline pairs). Square/cubic cells are kept: 2D/3D take `dx_eff` from x
and round the other axes to whole cells of it. The solvers use the effective
spacing/extents and log `[note] Cell size adjusted a -> b m to fit L m exactly`
when they differ. The real reach turned out to be **auto-refine**: its
`r_exp/5` essentially never divides L, so every auto-refined case had a
silently wrong domain (3D baseline: 0.991 m for 1.0 m; 2D profile run: 0.4955
for 0.5). Refine now picks the largest spacing that keeps MIN_EXP_CELLS across
the charge AND divides L (`L/ceil(L/(r_exp/N))` - ceil so it never goes
coarser), so one `[auto]` line reports the final value. This moved every
baseline file (refined dx -0.15..-1.2 %, grids 47->48 where the old one was
short, profile hand-off cascade into b2r/b3r) and all 9 writer goldens: the
foam writer's `_effective_dx` now takes the same divisor rule (L = radius_m
in 1D, Lx in 2D/3D) so a foam case lays out the same cell count as its native
twin - `test_foam_1d_vs_native`'s final_profile contract caught the 474-vs-475
mismatch when only the native side had it. Auto-refined goldens therefore gain
the one cell per axis the old rule dropped (case1d_tnt 474->475, the 2D axi
cases 379->380, case3d_c4/np4 47->48, domains now exact), non-refined cases
only move in dx-derived endTime/writeInterval and probe points that snap to
the true cell centres (e.g. 0.4984648512 -> 0.5) - accepted by the owner on
review. *Original entry:*
*What:* `core/grid.py:13,28-29,53-55` (`arange(0, L+0.5*dx, dx)`): `Lx=10,
dx=0.3` → 9.9 m domain; `L=1, dx=0.07` → 2% shrink, while summaries, stop
distances and containment checks use nominal L. *Why:* the user is never told
the domain isn't what they asked for; derived distances are subtly off.
*How:* either round N and adjust dx (exact L), or print/validate a note with
the effective domain. *Effort:* S. *Confidence:* **confirmed by execution**.

**B19 — 3D viewer colour-range plumbing misses two layers and mixes units.**
*What:* (a) the Volume layer's clim is frozen at add-time — `_Volume.
on_clim_changed` (`viewer.py:774`) has no callers, so auto-scale/manual Min-Max
never reach it (`viewer.py:791-806`); (b) GUI manual Min/Max never reaches
Surface Loads (`viewer.py:338-343` skips `loads.on_clim_changed`, unlike the CLI
slider path); (c) with Density/Energy active, loads (painted in kPa) inherit a
density/energy clim → saturated red or flat blue (`viewer.py:727-731`), and the
single scalar bar titles the active field while faces show overpressure.
*Why:* the volume/loads views become misleading exactly during long decaying
runs. *How:* one clim broadcast loop over all layers from
`set_clim`/`_auto_clim`; track a dedicated p-based range for loads. *Effort:* S.
*Confidence:* code-read.

**B20 — FrameStore thinning can discard the frame it just accepted (and report
it stored). DONE (2026-09-02).** Thinning is now anchored on the newest frame
(`frames[::-2][::-1]` instead of `frames[::2]`), so the just-appended frame is
never the one dropped; `append()` returns the actual post-thin presence
(`frames[-1] is frame`) instead of an unconditional `True`. Covered by a
dedicated `FrameStore` case in `test_viz3d_sampling.py` (cap sized so the
first thin fires exactly at an even pre-thin length - the old bug's trigger)
and an end-to-end `BlastScene.on_message` case in `test_viz3d_scene.py`.
*Original entry:* *What:* `sampling.py:271-276` thins with `[::2]` after appending;
when the list length is even the newest frame is dropped while `append`
returned True, so the viewer briefly shows a frame that then vanishes from
history (one-frame backwards jump per thinning event). *Why:* confusing time
jumps in LIVE mode; compounds B4. *How:* thin anchored on the last element
(`frames[-1]` always kept) and return actual status. *Effort:* S. *Confidence:*
**confirmed by execution**.

**B21 — Multi-charge stop/progress distances use only the primary charge. DONE
(2026-09-05).** `backend._stop_dists_3d` (per open side: distance from the
NEAREST charge; closed box: far corner from the primary) feeds `solve_3d_foam`
and `postmortem._snap_radii`; `writer.plan_case` 3D sizing uses the same
min-over-charges. Golden `case3d_two_charges`: only `writeInterval` moved
(9.64e-6 -> 8.26e-6 s, ratio 0.6/0.7 = the secondary's distance to x_hi
replacing the primary's to x_lo); endTime unchanged. *Original entry:*
*What:* `writer.plan_case` 3D sizing (`writer.py:258-266`) and `solve_3d_foam`
`dists`/`stop_dist` (`backend.py:1091-1100`) measure to `spec.center` only,
though `d_charge` is multi-charge aware. *Why:* with a secondary charge near an
open boundary, progress/writeInterval sizing skew and arrival-stop fires much
earlier in the front's life than the estimates assume (the stop itself remains
pressure-based and correct). *How:* min-over-charges in both spots. *Effort:* S.
*Confidence:* code-read.

**B22 — 'Run failed' dialog shows the last traceback line — for foam failures,
an arbitrary tail line of solver output. DONE (2026-09-02).** New
`app._error_headline()` returns the first non-empty line that is not the
traceback header, a chaining separator or an indented frame/source line - i.e.
the exception headline - and the dialog shows it plus "See the run log for
details."; the full traceback still goes to the log pane. Checked in
`test_gui_drain.py` with a foam-shaped message whose *last* line is solver
noise ("End"), which is exactly what the dialog used to show.
*Original entry:* *What:* `app.py:419`
`msg[1].splitlines()[-1]`; backend errors are multi-line with the headline
first. *Why:* the one dialog the user reads carries noise; the useful "case
kept at …" path is only in the log. *How:* show the exception headline + "see
log"; keep full text in the log. *Effort:* S. *Confidence:* code-read,
spot-verified.

**B23 — `test_foam_parallel`'s determinism check asserts a wall-clock
outcome, so it fails at random.** *What:* `test_foam_parallel.py:70-74`
requires two identical np=2 runs to produce gauge arrays of *equal length*
(`len(a) == len(b) and array_equal`), but each run ends when the arrival
watcher notices the shock at the boundary — a wall-clock-polled event, so the
two runs stop one write apart. Measured this review: the probe records are
**bit-identical over their common prefix** (the pipeline really is race-free)
while the lengths differ 699 vs 652 and `t_end` 7.31e-4 vs 6.81e-4 s. *Why:* a
suite that fails ~randomly trains the next session to ignore it; the check as
written cannot pass reliably. *How:* assert what the comment actually claims —
bit-equality over `min(len(a), len(b))` — plus a loose bound on the length
difference (the stop jitter is the thing to keep honest, not to hide).
Deliberately left for the owner to decide: weakening a determinism assertion
should be a conscious call, not a drive-by edit. *Effort:* S. *Confidence:*
**confirmed by execution** (found while verifying T4; unrelated to it — T4
touches no ingest/stop-timing code).

---


**B24 — Resolved-charge initialisation in 2D/3D does not conserve the charge's
mass/energy; the stair-stepped sphere carries ±3% depending on where the centre
falls.** *What:* with `dx = r_exp/MIN_EXP_CELLS` the explosive is a 5-cell-radius
stair-step; the set of cells whose centre lies inside r_exp is 39 or 40 cells
(axisym volume +0.2% vs +2.7% of the true sphere) depending on whether the
centre sits mid-cell or on a face, and rho/e are set per cell without rescaling
to the true mass/energy. 3D `charge_resolution='smear'` already rescales; the
`'resolve'` path and 2D do not. Found in T8 (2026-09-05): the exact-domain grids
put `test_blast2d`'s y0 = 4.0 on a face and moved the r = 1.5 m arrival gap
1D-vs-2D from 4.3% to 5.2%; that gate was widened to 6% (the peak gate already
allows 15%). *Why:* initial energy is the one number every downstream
peak/arrival scales with; a placement-dependent ±3% is avoidable noise, and it
makes 1D-vs-2D/3D gates sensitive to grid layout. *How:* after marking the
explosive cells, scale e (keeping rho_exp) or rho and e by V_true/V_discretised
as the 3D smear path does, log it as a `[note]`; re-baseline b2/b2r/b3/b3r once
more. *Effort:* S + re-baseline. *Confidence:* volume ratio computed this
review; the energy-to-arrival link is inferred (consistent with the 3.6% rise
in the 2D peak at r = 1.5 m).
## 2. GUI & UX

**G1 — "Initialise Model" hint is erased the instant it's written.
DONE (2026-09-02).** `_start` now logs the hint *after*
`run_panel.set_running(True)` (the call that clears the log pane), with a
comment at the call site so the ordering is not "tidied" back.
*Original entry:* *What:*
`app.py:286-290` logs the hint, then `set_running(True)` clears the log
(`run_panel.py:203-204`) — the user sees a held run, empty log, 0% bar. *How:*
log the hint after `set_running(True)` (2-line move). *Effort:* S. *Confidence:*
code-read (certain).

**G2 — Results accumulate unboundedly and duplicate labels make entries
unreachable.** *What:* `results_panel.py:178-189` — no removal UI, full
snapshots + up to 150 frames retained per entry for the process lifetime;
"Loaded - name (3D)" labels collide, and the combo can only ever select the
first match. *How:* "Remove result" button; de-dupe labels with a counter; free
frames on removal. Pairs with N9 (user-named runs). *Effort:* S–M. *Confidence:*
code-read.

**G3 — Validation split-brain and silent input swallowing.** *What:* only the
first parse error is shown (`app.py:234-237`); Run-tab failures are modal
dialogs while the strip lives on Setup; `_PointList` ignores malformed
gauge/obstacle/charge rows with zero feedback (`forms.py:98-109`); an invalid
"Refresh every" silently means "automatic" (`app.py:311-325`); exports with
nothing selected no-op (`results_panel.py:412-414`). *How:* inline red-border +
message on the offending row; a validation chip on the Run tab. *Effort:* M.
*Confidence:* code-read.

**G4 — Hidden 3D panels keep rendering; result replay blocks the Tk thread.**
*What:* three `VtkTkHost` instances tick at 20 Hz forever (`vtk_host.py:43,
114-128`); during a live 3D run `_blit` does full render+screenshot+PhotoImage
per frame even when the Live-slice tab covers it (`view3d_panel.py:304-314`);
`feed_result` replays all snapshots synchronously on the Tk thread
(`view3d_panel.py:289-302`). *How:* check `winfo_ismapped`/tab visibility before
blitting; chunk `feed_result` via `after`. *Effort:* S. *Confidence:* code-read
(magnitude is a hypothesis).

**G5 — Narrow start race from the Chain tab can leak a drain loop and drop a
finished result. DONE (2026-09-02).** `ChainPanel.set_running()` mirrors the
Run button (the app drives both from `_start` and from the drain's 'done'),
and `_start` additionally refuses while `App._drain_pending` is set - i.e.
until the drain has actually seen the previous worker's 'done', closing the
~50 ms window that `is_alive()` alone left open. *Original entry:* *What:* `_start`'s only guard is `worker.is_alive()`
(`app.py:276`); "Run chain" is never disabled, so a start in the ≤50 ms window
after a worker exits but before its 'done' drains orphans the old queue
(`app.py:423,451`). *How:* disable Run-chain while running (mirror the Run
button) and require the drain to have seen 'done' before a new start.
*Effort:* S. *Confidence:* mechanism certain from code; occurrence unlikely.

**G6 — Progress bar can end below 100% and theme toggles leave stale artist
colors. PROGRESS HALF DONE (2026-09-02); theme half still open.** On 'done'
the drain calls the new `run_panel.mark_complete()` (progress -> 1.0), but
only for a run that reached its own end: `App._run_stopped_early` /
`_run_errored` are set from the drained 'result'/'error' messages and reset
per run, so a stopped **or failed** run keeps the bar where it stopped rather
than claiming 100% (the brief only asked for the stopped case - filling the
bar on a failed run would be a lie the user reads as success). Covered in
`test_gui_drain.py`. Still open: the theme half (preview/live-line artists
bake the old palette on `_toggle_mode`). *Original entry:* *What:* final progress message can be throttled away (`worker.py:
79-83`) with nothing forcing 1.0 on 'done'; `_toggle_mode` restyles figure
chrome only, so preview/live-line colors bake the old theme
(`preview_panel.py:86-90`, `run_panel.py:236`, `theme.py:294-329`). *How:*
`progress.set(1.0)` on 'done'; redraw preview on theme change. *Effort:* S.
*Confidence:* code-read.

**G7 — Live-view niceties (carried from old roadmap, still open).** (a) foam
runs: show "frames land every ~X ms of sim time" in the live-view title so the
coarse cadence reads as intended; (b) the fixed Min/Max colour scale exists in
the 3D viewer but not the 2D live pane; (c) is B7 (one-line fix). *Effort:* S
each. *Confidence:* code-read (verified still open this review).

**G8 — Setup preview doesn't draw extra charges or detonation points.** Still
open: `case_geometry` packs only the primary `charge_center`
(`preview_panel.py:21-37,107-127`). Orange balls per extra charge + markers for
det points, both previews. *Effort:* S. *Confidence:* code-read (verified).

**G9 — Keyboard/state ergonomics.** No accelerators anywhere (no root binds, no
menu shortcuts), no UI-state persistence (geometry hard-coded `'1280x840'`,
mode always dark on start, refresh field blank — `app.py:65,465`). *How:*
Ctrl+O/S for case files, F5 run; a tiny json in the user config dir. *Effort:*
S. *Confidence:* code-read (verified still open).

---

## 3. Architecture & code health

**A1 — The foam run loop is triplicated (~250 lines ×3). DONE (2026-09-05).**
`solvers/foam/runloop.py`: `FoamRunLoop` owns FoamRun start, stdout pumping ->
`progress_line`, time-dir polling + readiness + strictly ordered ingest
(`OrderedIngest`), stop-request -> writeNow -> grace -> kill, drain, adaptive
writeInterval and the `finally` cleanup; each dim supplies `read_dir(name,
dpath)` (torn reads raise -> retry) and `on_frame(name, dpath, payload)`.
`solve_1d/2d/3d_foam` are preflight -> callbacks -> `FoamRunLoop.run()` ->
`finalize_*`; backend.py went 1593 -> ~980 lines, every log string kept
verbatim. *Original entry:* `solve_1d/2d/3d_foam`
share poll/ingest/stop-grace/kill/drain/`finally` machinery with small deltas
(`backend.py:360-482,593-766,1060-1283`) — B1/B2/B16-class fixes must land three
times. *How:* extract a `_FoamRunLoop` helper owning polling, readiness,
stop-escalation and ingest ordering; keep per-dim ingest/finalize as callbacks.
Do it *together with* the B1/B2 fixes so they land once. *Effort:* M.
*Confidence:* code-read.

**A2 — Geometry logic quadruplicated. DONE (2026-09-05).** `core/geometry.py`
(`open_edge_mask`, `stop_dists_2d/3d`, `snap_radii`, `d_charge_2d/3d`) is used
by backend 2D/3D, `postmortem._snap_radii`/`load_run` AND the native
solver2d/solver3d - a pure drop-in there, `test_regression` byte-identical.
*Original entry:* Open-edge mask + stop distances +
snapshot radii exist in backend 2D, backend 3D, `postmortem._snap_radii`
(`postmortem.py:49-82`) and the native solvers (`solver2d.py:219-250`); the
postmortem copy must stay bug-for-bug identical by hand. *How:* one shared
helper in `core/`. *Effort:* S–M. *Confidence:* code-read.

**A3 — `postmortem.py` imports seven underscore-private names from `backend`.
DONE (2026-09-05).** postmortem now imports public names only:
`finalize_1d/2d/3d`, `read_2d/3d` (backend), `ARRIVAL_P`, `PeakImpulse`,
`maybe_reconstruct` (runloop) and `core.geometry`; the tests follow suit
(`test_adaptive_interval`, `test_foam_live_due`, `test_foam_ingest_order`).
*Original entry:*
(`postmortem.py:21-23`). Promote them to a shared module (natural home for the
A1 extraction) or drop the underscores. *Effort:* S. *Confidence:* code-read.

**A4 — Dead code sweep.** `core/eos.py:36 pressure_soundspeed` is never called
yet is exactly the block copy-pasted into all three solvers' `primitives()`
(call it instead — bit-identical, regression-safe); `core/riemann.py:108
mirror_state` dead; solver1d rebuilds its grid inline twice duplicating
`make_grid_1d`; ~~`_todo` unreachable in `backend.py:51`; unused `m = MATERIALS…`
locals (`backend.py:365,598`)~~ (foam part DONE with T9, 2026-09-05); viz3d: `client.open_playback` has no callers and
duplicates `feed_result` line-for-line, `density_planes`/`have_rho`/`iso_locked`
are dead CLI-era toggles (`viewer.py:216-231,668-672`), `FIELD_LABELS`
duplicates viewer `FIELDS`. `legacy/blast2d/3d.py` carry ~100 lines of fossil
scaffolding (stale imports, empty headers) — the exported names must stay.
*Effort:* S. *Confidence:* code-read, grep-verified.

**A5 — Guard-rail constants duplicated as magic numbers.** `MIN_EXP_CELLS = 5`
re-hardcoded in all three solvers (`solver1d.py:87`, `solver2d.py:152`,
`solver3d.py:161`); 2D caps hardcoded despite `constants.CELLS_2D_MAX/WARN`
(`solver2d.py:157-170`) — `validate_case` uses the constants, the solvers use
literals, so they can drift apart silently. *Effort:* S. *Confidence:*
code-read.

**A6 — Load-bearing stdout regex needs a canary.** `st['step']` increments only
on `Time =` matches (`backend.py:165-168`) and drives steps-mode live cadence —
a blastFoam upgrade that changes the token silently freezes the live view and
progress. *How:* log a one-time warning after N output lines with no `Time =`
match. *Effort:* S. *Confidence:* code-read.

**A7 — Silent-degrade paths deserve one-time log lines.** `_decode_surface`'s
exact-count gate returns None forever on a persistent face-count mismatch
(`backend.py:295-301`) — live slice never updates, no message. Same spirit as
A6. *Effort:* S. *Confidence:* code-read.

**A8 — viz3d control-message delivery is best-effort.** `client.finish()` gives
up after 5 s on a full queue (zombie-LIVE viewer); `close()` uses `put_nowait`
and falls through to `terminate()` (`client.py:64-76`). *How:* on `Full`, drop
one queued frame and retry so 'done'/'close' always land. *Effort:* S.
*Confidence:* code-read / partially hypothesis (needs a stalled child).

**A9 — Commit hygiene. DONE (2026-09-02).** All working-tree state (source,
tests, goldens/baselines, docs) committed in four coherent commits:
`postmortem.py` + its test, the binary reader fixtures, the manual e2e
drivers, and everything else (the accumulated backend/GUI/viz3d work plus
ROADMAP.md/TASKS.md). `.gitattributes` already marked the fixture/baseline/
golden dirs `-text`, so no edit was needed there. Left untracked on purpose
(stray manual-run scratch output, not source): `case.json`, `gauges_2d.txt`,
`test_profile.txt`, `blastlab/tests/gauges.txt` — worth a `git clean` or
`.gitignore` entry when convenient. Re-verified before committing:
test_regression.py, test_foam_writer.py, test_foam_reader.py,
test_foam_env.py (all but the live-WSL-probe check), test_case_validate.py,
test_gui_drain.py, test_adaptive_interval.py, test_foam_live_due.py,
test_viz3d_sampling/hooks/scene/panel.py, and `import blastlab.gui.app` —
all green.

**A10 — Regression discipline (unchanged, restated).** Never touch
native-solver stdout without a deliberate re-baseline (`test_regression.py` is
the gate; B10/B12 both require one). Foam goldens regenerate only via
`test_foam_writer.py --update` + eyeballed diff. Version coupling: templates
target blastFoam v6.2.0 / OpenFOAM-9; reader/runner regexes and
`test_foam_reader` fixtures are the canary (see A6). WSL cold starts can time
out; the env probe retries 3× (`wsl --shutdown` if wedged).

---

## 4. New capabilities (ranked by impact/effort)

**N1 — Peak-overpressure / impulse views in the Results panel** *(top gap — the
data exists and is invisible)*. `meta['p_peak']`/`meta['impulse']` are computed
for every foam 2D/3D run, and the 3D viewer already offers them
(`view3d_panel.py:31`), but the Results field selector is still exactly
overpressure/density/speed (`results_panel.py:203-207`). Add both (2D
full-field; 3D as slices) + PNG export. ⚠ Caveat found this review: native 3D
tracks them for the viewer but not meta; **native 2D has no accumulators at
all** — that half is "add the tracking", not "expose it". *Effort:* M.
*Confidence:* verified still open.

**N2 — Per-gauge engineering summary.** Table per gauge: peak overpressure,
arrival time, positive-phase impulse (+ export `gauges_summary.csv` — keep it
out of the byte-pinned TSVs). This is the number users transcribe into reports;
today they read it off the curve. Depends on B9's positive-phase definition.
*Effort:* S–M. *Confidence:* verified still open.

**N3 — Afterburn** *(the KB gap closer)*. The anchor sits at 0.73–0.77 of
Kingery-Bulmash — the classic detonation-only-energy signature. blastFoam
v6.2.0 ships `afterburnModel` (`Miller|constant|linear`). Per-material
parameters + a Case field; `test_foam_kb_anchor.py` is a ready harness — expect
the ratio to move meaningfully toward 1. *Effort:* M (~1 day + re-baseline KB
numbers). *Confidence:* verified still absent (no `afterburnModel` anywhere).

**N4 — VTK / ParaView export** *(cheap, high value)*. `foamToVTK` is installed
WSL-side; a Results button running `run_stage(case_posix, ['foamToVTK
-useTimeName'])` + open-folder gives the full ParaView pipeline for reports.
Native runs: optional `.vti` via pyvista later. *Effort:* S. *Confidence:*
code-read (still absent).

**N5 — Charge-mass rasterization deficit.** `sphericalMassToCell` at 5
cells/radius sets ~0.85 of requested mass (visible in forwarded warnings; native
has the same staircase, so cross-comparisons stay fair — absolute yields are
low). Prefer: (a) foam-only refine target ~8 cells/radius; (b) surface reported
set-mass in `validate_case`; (c) investigate mass-conserving init. Re-baseline
KB afterwards. *Effort:* S–M. *Confidence:* carried forward (still open).

**N6 — Resume a stopped run.** Most machinery exists: postmortem rebuilds the
spec and replays ingest, probes/FO handle restarts (`READ_IF_PRESENT`, probes
merge), `rewrite_control_entry` can flip `startFrom`→`latestTime`. Needed:
pre-populate accumulators from disk, reattach `FoamRun`, skip mesh/init in
preflight. *Effort:* M (1–2 days). *Confidence:* code-read.

**N7 — Chains INTO blastfoam (profile init).** Write nonuniform internalFields
(p/T/U/alpha/rho) from a loaded 1D/2D profile (incl. e→T per-phase conversion —
the inverse of `_finalize_2d`), skip `setRefinedFields`, drop the
`init_mode != 'charge'` validation block. Unblocks B5's foam-chain scenario for
real. *Effort:* M–L (2–4 days incl. physics sanity test). *Confidence:*
code-read (writer has no nonuniform emitter today).

**N8 — Foam run browser + run-dir hygiene.** Replace the bare directory dialog
(`results_panel.py:385-396`) with a list fed by `postmortem.list_runs()`
(exists, unused): name/dims/size/date + per-run Delete reusing
`--clean-foam-runs` logic (after B14's live-run guard). Add age/size-based
auto-cleanup with opt-out. **Measured 7.7 GB in `/root/blastlab_runs` during
this review.** *Effort:* M. *Confidence:* verified (size measured; browser
absent).

**N9 — User-named runs.** Free-text name on the Run tab (default = case file
stem), carried into the Results combo and export filenames; fixes G2's label
collisions as a side effect. *Effort:* S. *Confidence:* verified still open.

**N10 — MUSCL second-order native reconstruction.** The native solvers are
1st-order Godunov — diffusive at shocks, peaks visibly dx-dependent. Land as
opt-in `order=2` (default 1 keeps `test_regression.py` bit-exact). *Effort:* L.
*Confidence:* verified still absent.

**N11 — Materials beyond TNT for the native solvers.** The JWL table exists
(`foam/materials.py`) but solvers hardcode `JWL_TNT` (`solver1d.py:78`,
`solver2d.py:101`, `solver3d.py:134`). Plumb through, default TNT stays
bit-exact. *Effort:* M. *Confidence:* verified still open.

**N12 — Gauge fields beyond p (foam-only).** blastProbes accepts `fields (p U
rho)`; reader gains columns; extra traces in the Gauges tab. Native gauges stay
p-only (byte-pinned). *Effort:* S–M. *Confidence:* carried forward.

**N13 — Report stub.** One-click HTML summary: banner, case JSON, gauge summary
table (N2), field PNGs, KB comparison for free-air cases. All pieces exist as
figures. *Effort:* M. *Confidence:* carried forward.

**N14 — CSV export of field maps** (p_peak/impulse/snapshots as x,y[,z],value).
*Effort:* S. *Confidence:* carried forward.

---

## 5. Nice-to-have

- **AMR** (`adaptiveFvMesh`): breaks the entire x-fastest uniform-grid contract
  (`to_grid`, `_decode_surface`, obstacle scatter) — needs a cell-centre
  resampler + second mapping path. 1–2 weeks; correctly last. *(code-read)*
- **Non-box obstacles** (STL → snappyHexMesh): needs the same resampler as AMR.
- **`pressureBased` activation** — per-material rate constants; revisit if
  ignition physics matters.
- **Direct `processor*/` reads** (skip reconstructPar): only if the ~3 s/write
  latency ever hurts; measured unnecessary so far.
- **Per-case `maxDeltaT`/`deltaT` overrides** — trivial writer plumbing, add
  when first needed.
- **HLLC A/B**: `dicts.FLUX_SCHEME = 'HLLC'` is a one-line flip;
  `test_foam_1d_vs_native.py` doubles as the harness.
- **2D axisym smear option** (3D has it; 2D refines only — quadratic cost,
  rarely binding).
- **Chain tab foam e2e coverage**: after B5 lands, one manual pass foam 1D →
  native 2D → native 3D, then a `_e2e_gui_foam.py`-style scripted driver.
- **Viewer polish**: log-contours currently apply to cut planes only
  (`viewer.py:345,635`); plane sliders at 0.0/1.0 produce an empty cut with no
  feedback (`viewer.py:513-523`); "Energy [J/kg]" for foam runs is the
  ideal-gas `p/0.4ρ` approximation — hide or label "approx" (`backend.py:1230,
  1338`); blit path renders twice and allocates ~1.3 MB/frame — persistent
  PhotoImage/PIL would roughly halve it (`vtk_host.py:130-138`). *(code-read)*
- **Axisym animation x-label** says 'x [m]' not 'r [m]' (`animation.py:66`);
  chained runs print "0 kg TNT" in the 3D init line (`profiles.py:157`,
  `solver3d.py:369`); 1D progress uses `t/safety_cap` (~10× actual run length —
  use front radius / R like 2D/3D, `solver1d.py:242`); `n_snapshots` semantics
  differ 1D vs 2D/3D. *(cosmetic, code-read)*

---

## Verified-correct this review (do not "fix")

Worth recording so future reviews don't re-litigate: axisym momentum source is
exactly well-balanced against the face-area metric; `bc.py` mirror signs are
correct; the y/z-sweep moveaxis round trip is index-correct (pinned by T1);
smear init conserves mass/energy to 1e-12 (T10); foam `to_grid` F-order
reshape ↔ viewer `ravel(order='F')` ↔ VTK point order is consistent end-to-end
(a transpose would trip `test_viz3d_scene` S2c); obstacle scatter/carve
ordering matches boxToCell; the GUI worker/queue architecture (latest-wins
frame slots, exception-hardened drain, Tk-thread-only widget access) is clean —
treat it as the pattern for new panels. Native↔foam physics agreement
re-verified live: peaks within 2–7% at r=1–4 m, both monotonic
(`test_foam_1d_vs_native`), KB anchor ratio 0.73–0.77 pending N3.

One watch item from this review's runs: in `test_foam_2d` (axisym), foam
*arrival times* at the near-field gauges lag native by 27–39% (peaks agree to
0.88–0.99). The test tolerances accept it and near-field arrival is expected to
differ under the linear activation model, but it has not been characterized —
worth a quick A/B (activation `none` vs `linear`, and after N3/N5 land) before
anyone uses foam near-field arrival times quantitatively. *(observed-by-running,
cause hypothesis)*
