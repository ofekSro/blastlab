# TASKS.md — sessions plan (one Claude Code session per task)

> **איך להשתמש (עברית):** כל משימה למטה היא בריף עצמאי לסשן Claude Code אחד.
> פותחים סשן חדש, מדביקים את **הפתיח המשותף** (Common preamble) ואחריו את
> בלוק ה-`SESSION PROMPT` של המשימה — ותו לא. הסדר הוא סדר הביצוע המומלץ
> (T0 → T16). הבריפים כתובים באנגלית בכוונה: הקוד, ה-ROADMAP והבדיקות באנגלית,
> וזה חוסך טוקנים בסשן. כל בריף אומר לסשן **אילו קבצים לקרוא ואילו לא** — זה
> החיסכון העיקרי בטוקנים: לא לתת לסשן לחקור מחדש את הריפו.
> אחרי כל משימה שהושלמה: לסמן `[x]` בטבלה למטה ולעדכן את ROADMAP.md (הסשן
> עושה זאת בעצמו — זה חלק מה-Done criteria).

## Order & status

| # | Task | Bundles (ROADMAP ids) | Effort | Status |
|---|------|------------------------|--------|--------|
| T0 | Commit untracked work | A9 | 10 min | [x] |
| T1 | Harden the foam stop/ingest path | B1, B2, B15 | S–M | [x] |
| T2 | Fix wrong-data display: 3D replay slice + viewer final frame + thinning | B3, B4, B20 | S | [x] |
| T3 | Units & labels: kPa everywhere, impulse naming | B8, B9(relabel) | S | [x] |
| T4 | Runs-dir safety: unique dirs, live-run guard, orphan reaping | B13, B14 | S | [x] |
| T5 | Papercuts bundle (one-liners) | B7, G1, B22, G6a | S | [x] |
| T6 | Chain validation + visible/stoppable foam preflight | B5, B6 | M | [x] |
| T7 | Native solver warnings through hooks (transcript byte-identical) | B11 | M | [x] |
| T8 | Native fixes that need ONE re-baseline | B10, B12, B18 | S + re-baseline | [x] |
| T9 | Extract the shared foam run loop | A1, A2, A3, A4(foam part) | M | [x] |
| T10 | Foam accumulator correctness | B16, B17, B21 | S–M | [x] |
| T11 | Peak-overpressure / impulse views in Results | N1 (+ native 2D accumulators, native 3D meta) | M | [x] |
| T12 | Per-gauge engineering summary + CSV | N2, positive-phase impulse (B9 full) | S–M | [x] |
| T13 | 3D viewer colour-range plumbing + viz3d dead code | B19, A4(viz part), A8 | S | [x] |
| T14 | Foam run browser + auto-cleanup | N8 | M | [x] |
| T15 | VTK/ParaView export button | N4 | S | [x] |
| T16 | Afterburn model (KB gap) | N3 | M | [x] |
| T17 | Local refinement: core model + schema + validation + form + preview + show-mesh (uniform path) | N15 | M | [x] |
| T18 | Local refinement: foam refine stages + remap reader + live slice + postmortem | N15 | M–L | [x] |
| T19 | Local refinement: 3D viewer mesh layer + e2e + docs | N15 | S–M | [x] |
| T20 | Dynamic AMR: core model + schema + validation + writer + goldens | N16 | M | [x] |
| T21 | Dynamic AMR: per-time ingest path + post-mortem + 2D e2e | N16 | M–L | [x] |
| T22 | Dynamic AMR: GUI form + validation line + per-frame mesh in Results | N16 | M | [x] |
| T23 | Dynamic AMR: 3D viewer per-frame mesh + 3D e2e + docs | N16 | S–M | [x] |
| later | N5 mass deficit, N6 resume, N7 profile→foam, N9 run names, N10 MUSCL, N11 materials, G2–G4, G7–G9, A5–A7 | — | — | see ROADMAP.md |

---

## Common preamble (paste at the top of EVERY session)

```
Project: blastlab — Python blast-wave simulation desktop app (customtkinter GUI),
native numpy 1D/2D/3D solvers in blastlab/solvers/, blastFoam backend in
blastlab/solvers/foam/ (writes OpenFOAM-9 cases, runs them in WSL, reads results
back onto uniform numpy grids), pyvista/VTK viewer in blastlab/viz3d/.
Planning doc: ROADMAP.md (item ids like B1/G1/A1/N1 refer to it). Read ONLY the
ROADMAP items named in this task, not the whole file.

Hard rules:
- Never change native-solver stdout or the byte-pinned outputs unless the task
  explicitly says "re-baseline". `python blastlab/tests/test_regression.py` must
  stay green (or be deliberately re-baselined per the task).
- Foam goldens regenerate only via `python blastlab/tests/test_foam_writer.py --update`
  and an eyeballed diff.
- Tests are plain scripts: `cd blastlab/tests && python test_X.py`. Files named
  `_e2e_*.py` are manual end-to-end runs (need WSL, ~1–3 min each).
- WSL work: run in the FOREGROUND (backgrounded shells that spawn WSL children
  report completion early and lose stdout). After killing anything, check for
  orphans: `wsl.exe -d Ubuntu -- pgrep -a blastFoam` and kill them.
  2D axisym foam cases at default size can take 30+ min — use tiny domains.
- Do not commit unless the task says so. Do not touch files outside the task's
  "Files" list without saying why.
- Token discipline: read only the files/line ranges listed; use Grep for
  everything else; do not re-run slow suites more than needed (run the fast
  no-WSL suites first, WSL suites once at the end).
- Finish by: (1) listing exactly what changed, (2) pasting the tail of each test
  you ran, (3) updating the matching ROADMAP.md item to "DONE (date)" and ticking
  the row in TASKS.md.
```

---

## T0 — Commit untracked work (A9)

**Why first:** `postmortem.py`, the binary reader fixtures and the `_e2e_foam_obstacle*`
drivers exist only in the working tree — one `git clean` loses a working, tested
feature. Zero-risk, minutes.

```
SESSION PROMPT — T0
Goal: commit the untracked and modified working-tree files in a small number of
coherent commits. Do NOT change any code.
Steps:
1. `git status --porcelain` and `git diff --stat`. Group:
   (a) blastlab/solvers/foam/postmortem.py + its test + anything it needs;
   (b) tests/foam_fixtures binary fixtures (check `.gitattributes` marks them
       binary; if not, add the pattern — that is the only file edit allowed);
   (c) _e2e_foam_obstacle2d.py / _e2e_foam_obstacle3d.py;
   (d) everything else already modified (ROADMAP.md, TASKS.md, source changes,
       regenerated PNG/GIF/baseline artifacts) — inspect `git diff` for the
       baseline/ and foam_golden/ files first: if they are byte-identical
       re-writes, fine; if content changed, STOP and report before committing.
2. One commit per group with a short message. Attribution trailer per the
   session's system instructions.
Done when: `git status` is clean except intentionally ignored files.
Out of scope: any code change.
```

---

## T1 — Harden the foam stop/ingest path (B1, B2, B15)

**Why:** a user Stop that escalates to kill can crash the run loop and lose the whole
Result. B1 is confirmed by execution; B2/B15 are code-read.

```
SESSION PROMPT — T1
Read: ROADMAP.md items B1, B2, B15 only. Then:
  blastlab/solvers/foam/reader.py  (whole file, ~360 lines)
  blastlab/solvers/foam/backend.py lines 360–520 (solve_1d_foam + _finalize_1d),
     640–860 (solve_2d_foam ingest loop + _finalize_2d), 1130–1350 (3D same)
  blastlab/solvers/foam/runner.py  lines 59–91 (rewrite_control_entry) and
     160–210 (FoamRun.request_write_now/_signal/suspend/resume/kill)
  blastlab/solvers/foam/postmortem.py lines 85–185 (load_run)
  blastlab/tests/test_foam_reader.py (to see the fixture/check pattern)
Do:
1. B1 — reader.read_scalar (~line 116–133) and read_vector (~134–153): when
   `_kind` says `uniform` and the regex does not match (torn file), raise
   ValueError("truncated uniform field: <path>") instead of letting
   `m.group()` raise AttributeError. Add fixtures `p_uniform` and
   `p_uniform_truncated` under blastlab/tests/foam_fixtures/ and two checks in
   test_foam_reader.py (parses value / raises ValueError).
2. B2 — in _finalize_1d/_finalize_2d/_finalize_3d, wrap every re-read of the
   final time dir (alpha/T/U/rho/p) in try/except (ValueError, OSError). On
   failure: log via hooks.log("[blastfoam] final write <t> unreadable - using
   previous write <t_prev>"), drop that dir from `ingested`, and finalize from
   the previous ingested dir. If no previous dir exists, re-raise with a clear
   message. Also add 'T' to the readiness fields tuple wherever 1D/2D finalize
   needs T (grep `time_ready(` in backend.py). Apply the same guard to
   postmortem.load_run's per-dir reads (skip unreadable dirs with a log line).
3. B15 — runner.rewrite_control_entry and FoamRun._signal: catch
   subprocess.TimeoutExpired; return False / log "[blastfoam] WSL did not
   answer to <op> within Ns" and let callers degrade (kill() must still try
   its next escalation step, never raise from a `finally`).
Verify (in this order):
  python test_foam_reader.py          (no WSL)
  python test_foam_writer.py          (no WSL, must be untouched)
  python test_foam_stop.py            (WSL — the stop/kill regression)
  python test_foam_postmortem.py      (WSL)
  python test_foam_3d_smoke.py --tiny (WSL)
  then `wsl.exe -d Ubuntu -- pgrep -a blastFoam` → must print nothing.
Done when: all above green; ROADMAP B1/B2/B15 marked DONE; TASKS.md T1 ticked.
Out of scope: extracting the shared run loop (that is T9) — make the same
change three times, keep it minimal and identical.
```

---

## T2 — Wrong-data display bugs in 3D (B3, B4, B20)

```
SESSION PROMPT — T2
Read: ROADMAP.md items B3, B4, B20. Then:
  blastlab/gui/results_panel.py lines 284–360 (_setup_anim/_show_frame/_tick)
  blastlab/output/animation.py lines 30–80 (the CORRECT axis selection to mirror)
  blastlab/solvers/solver3d.py — grep `live_sl`, `slice_axis`, `record_frames`,
     and the meta dict at the end of solve_3d (~lines 540–565)
  blastlab/solvers/foam/backend.py — grep `slice_axis` / `s0` in the 3D meta
  blastlab/viz3d/sampling.py lines 236–280 (FrameStore.append + thinning)
  blastlab/viz3d/viewer.py lines 425–445 (on_message 'frame'/'done')
  blastlab/viz3d/client.py (whole, small) and blastlab/gui/view3d_panel.py
     lines 280–320 (feed_result / on_frame / on_done)
  blastlab/tests/test_viz3d_sampling.py (pattern for FrameStore checks)
Do:
1. B3 — make the GUI replay use the recorded slice: ensure native 3D meta
   carries `slice_axis` and the slice index/position (foam 3D already does —
   match its key names). In results_panel._setup_anim choose faces/solid mask
   exactly as output/animation.py does for each axis (x→(y,z), y→(x,z),
   z→(x,y)); set axis labels accordingly. Add a check in test_blast3d.py or a
   small new no-WSL test that builds a fake 3D result with slice_axis='z' and
   calls _setup_anim/_show_frame without error (Agg backend, hidden Tk root —
   see _e2e_gui_foam.py for the hidden-root pattern).
2. B4 — carry a `final` flag on the frame message: producers (solver3d ~line
   540, backend.py ~line 1339, whatever emits the last 3D frame) already pass
   force=True to the transport; propagate it so both hosts call
   store.append(t, payload, force=final). Never rely on `self.done`.
3. B20 — FrameStore thinning must keep the newest frame: thin as
   `frames[-1:]` anchored (e.g. keep frames[::-2][::-1]) and make append()
   return whether the frame is still present after thinning. Add a check:
   after crossing the cap with an even length, the last stored t equals the
   last appended t.
Verify: python test_viz3d_sampling.py; test_viz3d_hooks.py; test_viz3d_scene.py;
  test_viz3d_panel.py; test_blast3d.py (slow, no WSL, ~10 min — run once at
  the end); then python _e2e_gui_view3d.py if it runs headless in your env.
Done when: green; ROADMAP B3/B4/B20 DONE; TASKS.md ticked.
Out of scope: colour-range plumbing (T13), Results field selector (T11).
```

---

## T3 — Units & labels (B8, B9 relabel)

```
SESSION PROMPT — T3
Read: ROADMAP.md items B8, B9. Then:
  blastlab/output/plots.py lines 200–270 (2D vs 3D snapshot figures)
  blastlab/gui/results_panel.py lines 214–270 (_draw_field: unit label logic)
  blastlab/gui/run_panel.py — grep 'kPa' / 'Pa]'
  blastlab/viz3d/viewer.py lines 30–45 (FIELDS titles)
  blastlab/gui/view3d_panel.py line ~30 (FIELD_LABELS)
  blastlab/output/gauges.py header lines (DO NOT change — byte-pinned)
Do:
1. B8 — one convention: overpressure shown in kPa in every figure/colorbar
   (2D and 3D, CLI figures and GUI). Convert at plot time only (data stays Pa).
   Every colorbar gets units: density [kg/m³], speed [m/s], energy [J/kg],
   impulse [Pa·s] (see 2). GUI 3D label must read e.g. "Overpressure [kPa] —
   x-z slice at y=…", not "overpressure (x-z)".
2. B9 (relabel only) — rename displayed "Impulse [Pa s]" to "Net overpressure
   impulse [Pa·s]" in viewer FIELDS, view3d_panel FIELD_LABELS, and any plot
   label; add one sentence to blastlab/README.md explaining net vs
   positive-phase (positive-phase arrives in T12).
3. Check test_regression: figures are NOT byte-pinned (only gauge TSVs,
   profiles and transcript are) — confirm by reading test_regression.py's file
   list before touching plots.py. If any figure IS pinned, stop and report.
Verify: python test_regression.py (must stay green), test_blast2d.py,
  test_viz3d_scene.py, and a headless GUI import (`python -c "import
  blastlab.gui.app"`). Produce one 2D and one 3D PNG via the existing export
  path or plots.py to eyeball the labels (save to the scratchpad, not the repo).
Done when: green; ROADMAP B8 DONE, B9 marked "relabeled — positive-phase in T12".
Out of scope: gauge TSV headers (byte-pinned), positive-phase accumulator.
```

---

## T4 — Runs-dir safety (B13, B14)

```
SESSION PROMPT — T4
Read: ROADMAP.md items B13, B14. Then:
  blastlab/solvers/foam/env.py lines 55–75 (new_case_dir) + grep RUNS_ROOT
  blastlab/solvers/foam/writer.py lines 755–780 (write_case makedirs)
  blastlab/solvers/foam/cli_run.py lines 70–110 (clean_runs)
  blastlab/solvers/foam/runner.py lines 91–135 (FoamRun init: where .run.pid
     is written) and 195–210 (kill)
  blastlab/solvers/foam/postmortem.py lines 185–end (list_runs)
  blastlab/tests/test_foam_env.py (has "case dir naming" check — extend it)
Do:
1. B13 — new_case_dir: append a uniqueness suffix (pid + 2-digit counter, or
   retry with `-1`, `-2` when the dir exists). writer.write_case must create
   with exist_ok=False for a fresh run (keep exist_ok=True only where a
   resume/post-mortem path legitimately reuses a dir — grep callers first).
   Update the "case dir naming" check in test_foam_env.py and the golden
   expectations if they embed the dir name (they should not; verify with
   test_foam_writer.py).
2. B14a — live-run guard: a helper `env.run_is_alive(case_dir)` that reads
   `.run.pid` and checks the pid inside WSL (`kill -0`) — one wsl call for all
   dirs, not one per dir. clean_runs skips alive runs and prints them; add
   `--force` to override. Wire the same helper into postmortem.list_runs output
   (an `alive` flag) so T14's browser can use it.
3. B14b — orphan reaping: `env.reap_orphans()` — for every `.run.pid` whose pid
   is alive but whose Windows-side owner is gone (record the Windows pid next
   to the Linux pid in `.run.pid` at FoamRun init; owner gone == that Windows
   pid no longer exists), send SIGTERM then SIGKILL. Call it from cli_run's
   clean path and expose `python -m blastlab --reap-foam-runs`. Do NOT call it
   automatically at GUI startup yet (could kill a CLI run in another window —
   note this in ROADMAP as a follow-up decision).
Verify: test_foam_env.py, test_foam_writer.py (no WSL); then a WSL check:
  start test_foam_3d_smoke.py --tiny, and while it runs call clean_runs from a
  second terminal → must refuse the live dir. Finish with the orphan grep.
Done when: green; ROADMAP B13/B14 DONE.
Out of scope: the GUI browser (T14), age/size auto-cleanup (T14).
```

---

## T5 — Papercuts bundle (B7, G1, B22, G6-progress)

```
SESSION PROMPT — T5
Read: ROADMAP.md items B7, G1, B22, G6. Then only these ranges:
  blastlab/solvers/foam/backend.py lines 158–175 and the three `st = dict(`
     lines (~374, ~658, ~1133)
  blastlab/gui/app.py lines 275–300 (_start) and 405–455 (drain: 'error',
     'done', 'result')
  blastlab/gui/run_panel.py lines 195–210 (set_running/_clear_log) and the
     progress widget setter
  blastlab/gui/worker.py lines 75–85 (progress throttle)
Do:
1. B7 — initialize frac=None in all three `st = dict(...)` so the existing
   t/end_time fallback at _progress_line runs until the first ingested write
   sets a real fraction.
2. G1 — in app._start, log the '[model initialised - use the Exec buttons…]'
   hint AFTER run_panel.set_running(True) (which clears the log).
3. B22 — 'error' handling: show the FIRST non-empty line of the message that
   is not a traceback frame (i.e. the exception headline, e.g.
   "RuntimeError: blastFoam failed (exit 1) - case kept at …") plus
   "\n\nSee the run log for details."; keep the full text in the log pane.
4. G6 (progress only) — on 'done', force the progress bar to 1.0 unless the
   run was stopped early (result meta `stopped_early` True → leave as is).
Verify: test_gui_drain.py, test_foam_live_due.py (no WSL); then
  python _e2e_gui_foam.py (WSL, ~2 min) and confirm in its captured log that
  the progress fraction is non-zero before the first '[blastfoam] write' line.
Done when: green; ROADMAP B7/G1/B22 DONE, G6 progress half DONE.
Out of scope: theme colour refresh (other half of G6), everything else.
```

---

## T6 — Chain validation + visible/stoppable foam preflight (B5, B6)

```
SESSION PROMPT — T6
Read: ROADMAP.md items B5, B6. Then:
  blastlab/gui/chain_panel.py lines 100–160 (_run + auto-wiring)
  blastlab/gui/app.py lines 232–300 (_validate/_run_single/_run_chain/_start)
  blastlab/core/case.py — grep `def validate_case` and the init_mode block
     (~lines 225–240)
  blastlab/solvers/foam/backend.py lines 57–160 (_preflight + stage runner)
  blastlab/solvers/foam/runner.py lines 39–58 (run_stage)
  blastlab/solvers/foam/env.py lines 130–200 (_probe/check_available/status)
  blastlab/solvers/hooks.py (should_stop contract)
Do:
1. B5 — ChainPanel._run: after auto-wiring, call validate_case on every stage;
   collect errors as "Stage <n> (<dim>D): <msg>"; if any, show one messagebox
   and do not start. Additionally: if a later stage has solver='blastfoam'
   and init_mode != 'charge', report "blastFoam stages cannot start from a
   profile yet (ROADMAP N7)" as a validation error — do not let it reach the
   backend. Disable the "Run chain" button while a run is active (mirror the
   Run button) — this also closes the G5 start race.
2. B6 — _preflight: hooks.log("[blastfoam] checking WSL/blastFoam
   availability…") BEFORE env.check_available(); run the probe in a helper
   thread and poll every 0.25 s, checking hooks.should_stop(); on stop, return
   a "stopped before start" result (same shape as an early stop). Then split
   the meshing `&&` chains into one run_stage call per command (blockMesh,
   topoSet, subsetMesh, setRefinedFields, decomposePar…) and check
   should_stop() between them; on stop, kill the stage subprocess (run_stage
   needs a Popen variant with a stop callback — keep run_stage's API for
   other callers). Log each stage name as it starts so the user sees progress.
Verify: test_case_validate.py, test_gui_drain.py (no WSL);
  test_foam_writer.py (goldens must be untouched); test_foam_stop.py and
  test_foam_3d_smoke.py --tiny (WSL); orphan grep. Add a WSL check to
  test_foam_stop.py: request stop during preflight → run returns within 15 s
  with no blastFoam process left.
Done when: green; ROADMAP B5/B6/G5 DONE.
Out of scope: profile init into foam (N7).
```

---

## T7 — Native solver warnings through hooks (B11)

```
SESSION PROMPT — T7
Read: ROADMAP.md item B11 and A10. Then:
  blastlab/solvers/hooks.py (whole), blastlab/gui/worker.py lines 60–90
  (GuiHooks.log), blastlab/solvers/solver1d.py / solver2d.py / solver3d.py —
  grep `print(` in each (list every call site before editing)
  blastlab/tests/test_regression.py and make_baseline.py (how transcript.txt
  is captured — it byte-pins stdout)
Do:
- Add `log(msg)` to the default hooks with an implementation that prints
  exactly what print() printed today (same string, same end='' / sep
  behaviour). Replace every solver `print(...)` with `hooks.log(...)`. The
  transcript must stay byte-identical: do this mechanically and diff.
- GuiHooks.log already forwards to the GUI log pane — confirm and leave it.
- The CLI hooks must still print.
Verify: python test_regression.py MUST be green without re-baselining (that is
  the whole point). Then test_blast2d.py, test_blast3d.py (slow; run once),
  test_gui_drain.py, and _e2e_gui_foam.py is not needed (foam already logs) —
  instead run a tiny native 2D case through the GUI e2e pattern with a gauge
  placed inside an obstacle and assert the "[warn] Gauge … dropped" line
  appears in the captured GUI log.
Done when: green with NO baseline change; ROADMAP B11 DONE.
Out of scope: changing any message text.
```

---

## T8 — Native fixes that need ONE re-baseline (B10, B12, B18)

```
SESSION PROMPT — T8
This task deliberately changes byte-pinned outputs. Do all three fixes, then
re-baseline ONCE, then review the baseline diff by eye.
Read: ROADMAP.md items B10, B12, B18, A10. Then:
  blastlab/solvers/solver1d.py lines 110–135 (snapshot scheduling), 160–180
  and 240–255 (gauge record + finalize); solver2d.py lines 225–255, 320–330,
  405–420; solver3d.py lines 310–330, 420–430, 525–535; blastlab/core/grid.py
  (whole, small); blastlab/tests/make_baseline.py and test_regression.py.
Do:
1. B10 — skip the finalization gauge record when t equals the last recorded
   t (all three solvers; identical guard).
2. B12 — 1D snapshots: trigger on shock-front radius fractions like 2D/3D
   (snap radii = linspace over (radius_m - r_charge)), not acoustic time.
   Keep n_snapshots semantics documented in the docstring; if you align 1D
   to 2D/3D's "n total incl. final" note it in ROADMAP (old nice-to-have).
3. B18 — grid.py: compute N = round(L/dx) and use dx_eff = L/N so the domain
   is exact; print a one-line note in the run summary when dx_eff != dx
   ("cell size adjusted 0.3 → 0.2941 m to fit 10 m"). This changes results
   only when dx does not divide L — check the baseline cases: if their dx
   divides L, the byte diff from B18 should be zero.
4. Re-baseline: python blastlab/tests/make_baseline.py (writes ./baseline).
   `git diff --stat blastlab/tests/baseline` and read the diff: expected
   changes are ONLY (a) one duplicated last row gone per gauge file,
   (b) extra 1D snapshot lines in transcript.txt, (c) nothing from B18 for
   dividing cases. Anything else → stop and report.
Verify: test_regression.py (against the new baseline), test_blast2d.py,
  test_blast3d.py, test_foam_1d_vs_native.py (WSL — its gauge post-processing
  must still pass with the deduped rows).
Done when: green; baseline diff reviewed and described in the commit message
  (commit this task — baseline + code together); ROADMAP B10/B12/B18 DONE.
Out of scope: MUSCL, materials, anything numerical beyond these three.
```

---

## T9 — Extract the shared foam run loop (A1, A2, A3, foam dead code from A4)

```
SESSION PROMPT — T9
Refactor only — zero behaviour change. T1 and T10 fixes must already be in
(check TASKS.md).
Read: ROADMAP.md items A1, A2, A3, A4. Then backend.py in full (it is ~1400
lines — read it once, take notes, do not re-read), postmortem.py in full,
solver2d.py lines 215–255 (native geometry helper to compare with).
Do:
1. A1 — new module blastlab/solvers/foam/runloop.py with a class (or
   generator) owning: FoamRun start, stdout pumping → _progress_line, time-dir
   polling + readiness + strictly-ordered ingest (calls a per-dim
   `ingest(tdir)` callback), stop-request → writeNow → grace → kill
   escalation, drain, adaptive writeInterval, and the `finally` cleanup.
   solve_1d/2d/3d_foam become: preflight → build callbacks → runloop.run()
   → _finalize_*. Keep every log string identical (tests grep them).
2. A2 — one geometry helper (open-edge mask, stop distances, snapshot radii)
   in blastlab/core/ used by backend 2D/3D and postmortem._snap_radii; leave
   the native solvers alone (byte-pinned prints) unless the helper is a pure
   drop-in with identical numbers — verify with test_regression.
3. A3 — move the names postmortem imports from backend into the new module
   (or a shared `foam/common.py`); no underscore imports across modules.
4. A4 (foam part) — delete `_todo`, unused `m = MATERIALS[...]` locals.
Verify: test_foam_writer.py (goldens untouched), test_foam_reader.py,
  test_adaptive_interval.py, test_foam_live_due.py, test_regression.py (no
  WSL); then WSL once each: test_foam_1d_vs_native.py, test_foam_2d.py,
  test_foam_3d_smoke.py --tiny, test_foam_stop.py, test_foam_postmortem.py,
  test_foam_features.py; orphan grep.
Done when: green; ROADMAP A1/A2/A3 DONE; A4 foam bullets struck.
Out of scope: any physics/UX change; the viz3d dead code (T13).
```

---

## T10 — Foam accumulator correctness (B16, B17, B21)

```
SESSION PROMPT — T10
Read: ROADMAP.md items B16, B17, B21. Then backend.py: the ingest loops
(2D ~685–715, 3D ~1166–1225), the Python impulse accumulator (~1186), the
FO read + peak_source selection in _finalize_3d (~1320–1335) and _finalize_2d
(~840–850), the 3D `dists`/`stop_dist` block (~1085–1100); writer.py
lines 250–270 (plan_case 3D sizing) and grep `d_charge`.
(If T9 already landed, these live in runloop.py — grep for the same names.)
Do:
1. B16 — ingest strictly in ascending time: if an earlier dir is not ready,
   do not ingest later ones in that pass (wait); if it stays unreadable for
   N polls after a later dir became ready, log and skip it permanently.
   Never let t < t_prev reach the accumulator (assert + log).
2. B17 — if the FO read of the final dir fails but the Python accumulator
   covers the final ingested frame, prefer the Python one and set
   peak_source='python-fallback'; add the same Python fallback accumulator to
   2D (copy the 3D one).
3. B21 — stop/progress distances and writer plan sizing: use the minimum
   over all charges, not spec.center only.
Verify: test_foam_writer.py --update is NOT expected — if goldens change from
  B21 (writeInterval/endTime for the two-charge golden), inspect the diff,
  then `--update` and describe the change. test_foam_reader.py; WSL:
  test_foam_features.py (multi-charge), test_foam_3d_smoke.py --tiny,
  test_foam_2d.py; orphan grep.
Done when: green; ROADMAP B16/B17/B21 DONE.
```

---

## T11 — Peak-overpressure / impulse views in Results (N1)

```
SESSION PROMPT — T11
Read: ROADMAP.md item N1 (and B9 note). Then:
  blastlab/gui/results_panel.py lines 190–270 (_refresh/_draw_field field
  list + data dict), 411–end (_export PNG path); blastlab/output/plots.py
  overpressure_panel and the 2D/3D snapshot figure builders;
  solver3d.py — grep `p_peak`, `impulse`, and the final `meta = dict(`;
  solver2d.py — grep the main loop's `p` update and the meta dict;
  backend.py — grep `'p_peak'` / `'impulse'` in the 2D and 3D meta.
Do:
1. Native 3D: store the p_peak/impulse arrays (already tracked for the
   viewer) in meta under the same keys foam uses.
2. Native 2D: add p_peak (running max of p) and impulse (∫(p−P_AIR)dt,
   same pairing as the state update) accumulators; store in meta. Cost: two
   array ops per step — measure on the test_blast2d case and report the
   slowdown; keep stdout unchanged (test_regression must stay green — do not
   print anything new).
3. Results panel: add "Peak overpressure [kPa]" and "Net ovp impulse [Pa·s]"
   to the field selector (2D full field; 3D as the same x-z / x-y slices the
   other fields use), rendering through the existing per-field dict plumbing;
   include both in the PNG export; hide the entries when meta lacks the keys
   (older loaded runs).
Verify: test_regression.py, test_blast2d.py, test_blast3d.py (once),
  test_foam_3d_smoke.py --tiny (WSL); a headless GUI check that builds a
  Results panel with a synthetic 2D result and selects each new field
  (pattern: _e2e_gui_foam.py hidden root).
Done when: green; ROADMAP N1 DONE (and the "native 2D has no accumulators"
caveat removed).
```

---

## T12 — Per-gauge engineering summary + CSV (N2, positive-phase impulse)

```
SESSION PROMPT — T12
Read: ROADMAP.md items N2, B9. Then blastlab/gui/results_panel.py lines
125–140 and 270–285 (Gauges tab), blastlab/output/gauges.py (readers, if any —
else the TSV format from its header lines), test_foam_1d_vs_native.py's
arrival/peak helpers (reuse the definitions — they are the validated ones).
Do:
1. New module blastlab/output/gauge_summary.py: from (t, p) per gauge →
   peak overpressure [kPa], arrival time [ms] (first crossing of a threshold
   above ambient — use the same rule as test_foam_1d_vs_native), positive-phase
   duration [ms], positive-phase impulse [Pa·s] (∫max(p−P_AIR,0)dt over the
   first positive phase only), net impulse. Pure numpy, unit-tested with a
   synthetic Friedlander pulse (new test_gauge_summary.py, no WSL).
2. Gauges tab: a small table under the figure + "Export summary CSV…"
   (`<gauge_file stem>_summary.csv`). Never touch the byte-pinned gauge TSVs.
3. Works for 1D/2D/3D, native and foam (gauge data shape is the same).
Verify: test_gauge_summary.py, test_regression.py, headless Results-panel
check with a synthetic result.
Done when: green; ROADMAP N2 DONE, B9 DONE.
```

---

## T13 — 3D viewer colour-range plumbing + viz3d dead code (B19, A4 viz, A8)

```
SESSION PROMPT — T13
Read: ROADMAP.md items B19, A4, A8. Then blastlab/viz3d/viewer.py lines
200–240 (state), 330–410 (set_clim/_auto_clim/_apply_cmax/set_log_scale),
600–680 (_CutPlane.refresh + scalar bar), 700–810 (_SurfaceLoads, _Volume);
blastlab/viz3d/client.py (whole); blastlab/gui/view3d_panel.py lines 25–40
and 120–150; blastlab/tests/test_viz3d_scene.py.
Do:
1. B19 — one `_broadcast_clim()` that calls on_clim_changed() on every layer
   (planes, volume, loads) from set_clim, _auto_clim and _apply_cmax; loads
   keep their own overpressure-based (lo, hi) tracked per frame regardless of
   the active field; add a second small scalar bar (or HUD text) for loads
   so the single bar no longer mislabels them.
2. A4 (viz) — delete client.open_playback (no callers), density_planes /
   have_rho / iso_locked and their branches; derive view3d_panel FIELD_LABELS
   from viewer.FIELDS.
3. A8 — client._send_blocking/close: on queue.Full, drop one queued frame and
   retry so 'done'/'close' always land.
Verify: test_viz3d_sampling/hooks/scene/panel.py; test_viz3d_e2e.py opens a
  window — run it only if the environment allows; else state it was skipped.
  Render one off-screen scene with Density active + loads on and eyeball the
  PNG (scratchpad) to confirm loads are no longer saturated.
Done when: green; ROADMAP B19/A8 DONE, A4 viz bullets struck.
```

---

## T14 — Foam run browser + auto-cleanup (N8)

```
SESSION PROMPT — T14
Requires T4 (alive flag on list_runs). Read: ROADMAP.md item N8. Then
postmortem.list_runs, cli_run.clean_runs, results_panel._load_foam_run
(lines 383–410), env.py RUNS_ROOT helpers.
Do:
1. A `FoamRunBrowser` toplevel (customtkinter): table name / dims (from
   case.json) / size / date / alive; Load (→ existing _load_foam_run path
   with the chosen dir), Delete (refuses alive runs; confirm dialog), Refresh.
   Size computation must run off the Tk thread (9p is slow) with a spinner.
2. Auto-cleanup policy in env: max total size (default 20 GB) and max age
   (default 14 days), never touching alive runs or the N most recent (default
   3); runs at GUI startup off-thread with a log line "cleaned X runs, Y GB";
   opt-out flag in the same small json T-later G9 will use (create
   blastlab/gui/settings.py now: load/save a dict from the user config dir).
3. `--clean-foam-runs` gains `--older-than DAYS` / `--keep-gb N`.
Verify: test_foam_env.py (extend with a fake runs tree for the policy — no
  WSL), headless open of the browser with a synthetic list; one real WSL
  listing.
Done when: green; ROADMAP N8 DONE, G9 persistence half started (note it).
```

---

## T15 — VTK / ParaView export (N4)

```
SESSION PROMPT — T15
Read: ROADMAP.md item N4. Then results_panel._export (lines 411–end),
runner.run_stage, env (case_posix/case_unc helpers), and how a foam Result
records its case dir in meta (grep `case_dir` in backend.py).
Do: a Results-panel "Export VTK…" button, enabled only for foam results with
an existing case dir: runs `foamToVTK -useTimeName` (parallel runs: add
`-parallel`? — no: results are reconstructed; use the serial form) via
run_stage in a worker thread with log lines, then opens the VTK folder via
os.startfile on the UNC path. Errors go to the log + a short dialog.
Verify: WSL: run test_foam_3d_smoke.py --tiny, then call the export on that
case dir programmatically and check `VTK/` contains one file per time dir.
Done when: works; ROADMAP N4 DONE. Out of scope: native .vti export.
```

---

## T16 — Afterburn model (N3)

```
SESSION PROMPT — T16
Read: ROADMAP.md items N3, N5. Then blastlab/solvers/foam/materials.py
(whole), dicts.py (whole), writer.py — grep `activationModel` (the phase
properties template), core/case.py — the foam fields on Case (activation,
material, n_procs) and validate_case; test_foam_kb_anchor.py (whole — the
harness); the blastFoam tutorial `internalDetonation_*` under the WSL install
(find it with `wsl.exe -d Ubuntu -- bash -lc 'ls $FOAM_TUTORIALS/…'` or grep
the vendored docs in BlastFoam_Basic_Info/).
Do:
1. Per-material afterburn parameters in materials.py (Miller model constants
   for TNT/C4/ANFO from the literature — cite the source in a comment); Case
   field `afterburn: 'none'|'miller'` (default 'none' so goldens and KB
   baselines are unchanged); writer emits `afterburnModel` + coefficients;
   form control next to activation; validate_case: foam-only.
2. Add a golden `case1d_tnt_afterburn` (test_foam_writer.py --update after
   eyeballing).
3. A/B: run test_foam_kb_anchor.py with afterburn on (add a flag/second run)
   and report the KB ratio before/after; if it moves toward 1 as expected,
   add the after-ratio as a second, separate gate (do not tighten the
   existing one).
Verify: test_foam_writer.py, test_case_validate.py (no WSL); WSL:
  test_foam_kb_anchor.py (both modes, ~5 min), test_foam_1d_vs_native.py
  (must stay green with default 'none').
Done when: green; ROADMAP N3 DONE with the measured ratios written into it.
```

---

## T17 — Local refinement: core + schema + validation + form + preview + show-mesh (N15)

```
SESSION PROMPT — T17   [DONE 2026-09-05]
Read: ROADMAP.md item N15 and the plan ~/.claude/plans/3d-2d-recursive-lerdorf.md.
Do: core/refine.py (plan_levels, validate_zones, fine_src, slice_src,
  mesh_segments_2d, match_cells, auto_charge_zones); Case2D/3D refine_zones +
  charge_refine (schema v3, case_from_dict coercion); validate_case (native ->
  error; foam -> plan, notes, predicted count for FOAM caps, fine grid vs
  native caps); forms (zones card, charge-refinement combo, preview "Show
  mesh"); preview_panel (zone rectangles/wireframes, predicted edges);
  plots.mesh_for/add_mesh_lines + mesh= on the panel builders + show_mesh on
  figures/animation; RunPanel + ResultsPanel checkboxes.
Verify: test_refine, test_gui_refine_preview, test_case_validate,
  test_gui_results_fields/anim, test_foam_writer (byte-identical goldens),
  test_regression (byte-identical), test_viz3d_scene/panel.
Done when: green; ROADMAP N15 T17 part DONE.
```

## T18 — Local refinement: foam refine stages + remap reader + live slice + postmortem (N15)

```
SESSION PROMPT — T18   [DONE 2026-09-05; also fixed B25 + the T10 '0' dir stall]
Read: ROADMAP.md N15, the plan file section "T18", core/refine.py in full,
  writer.py plan_case (2D/3D) + _blockmesh_* + _toposetdict, backend.py
  _mesh_stages/_preflight/_decode_surface/solve_2d_foam/solve_3d_foam
  banners, reader.py to_grid/read_vector, runloop.py FoamRunLoop,
  postmortem.py load_run, env.py NEEDED_TOOLS.
Do (WSL facts are in the plan: refineMesh -dict/-overwrite, e1/e2/e3
  directions, no cellLevel -> postProcess -func writeCellCentres -> 0/C):
1. writer.plan_case: plan = refine.plan_levels(case, rho0); spec gains
   dx_base/nb/levels/lmax/zones/solid_base; spec.grid/nx/ny/nz/dx/solid = the
   FINE grid (solid = expand(solid_base)); blockMesh on spec.nb/dx_base;
   uniform cases render byte-identical. Per level l: system/topoSetDict.refine{l}
   (cellSet refine{l} = boxToCell of snapped zones with level >= l) and
   system/refineMeshDict.{l} (planar/axisym: directions (e1 e2), useHexTopology
   no; 3D: (e1 e2 e3), useHexTopology yes; geometricCut no; writeMesh no).
2. backend._mesh_stages: blockMesh -> [carve] -> per level topoSet -dict +
   refineMesh -dict -overwrite -> setRefinedFields -noRefine -> (if lmax)
   postProcess -func writeCellCentres -time 0 -> [decomposePar]. After the
   stages: C = reader.read_cell_centres (read_vector n_cells=None), spec.remap
   = refine.match_cells(C, spec.grid, refine.fine_src(spec.levels, spec.lmax,
   spec.solid_fine)), spec.n_cells_actual = len(C); log "[blastfoam] refined
   mesh: N cells matched the predicted structure"; mismatch -> RuntimeError,
   case kept. env.NEEDED_TOOLS += topoSet, subsetMesh, refineMesh, postProcess.
3. reader.to_grid remap branch (vals[remap], -1 -> fill); _decode_surface remap
   branch (floor(pt/dx_fine) -> remap_sl -> cell id; count-check; NaN -> None);
   run_info['mesh_src'] = refine.slice_src(...) when spec.lmax.
4. Banners: base cell / per-level sizes + counts / actual foam cells / display
   grid; keep every existing log string. finalize_2d/3d meta['refine'] =
   plan.meta() when refined; scene3d['refine']. postmortem rebuilds remap from
   the kept 0/C. max_snaps from the fine count; stop_grace from actual cells.
Verify: test_foam_writer (new goldens case2d_planar_refine, case2d_axi_refine,
  case3d_refine; existing byte-identical -> --update adds dirs only),
  test_foam_reader (to_grid remap, _decode_surface remap, read_vector
  n_cells=None), test_refine; WSL: _e2e_foam_refine2d.py, _e2e_foam_refine3d.py
  (incl. n_procs=2), test_foam_postmortem (refined run), test_foam_3d_smoke
  --tiny, test_foam_2d, test_foam_stop; orphan grep.
Done when: green; ROADMAP N15 T18 part DONE.
```

## T19 — Local refinement: 3D viewer mesh layer + e2e + docs (N15)

```
SESSION PROMPT — T19   [DONE 2026-09-05]
Read: ROADMAP.md N15, plan file section "T19", viz3d/viewer.py (BlastScene
  layers, _CutPlane, mesh_edges_polydata, add_static_scenery), viz3d/sampling.py
  build_scene_init, viz3d/client.py scene_from_meta, gui/view3d_panel.py
  (checkbox helper, _toggle_layer, _apply_all_controls).
Do: viewer._MeshEdges(_Layer): per visible axis-aligned cut plane, k =
  floor(origin[ax]/dx_fine) on the FULL-resolution init axes (not the
  stride-decimated grid), src2d = refine.slice_src(levels, lmax, ax, k) or
  None, mesh_edges_polydata -> add_mesh(color '#d0d4da', line_width 1,
  opacity 0.7, name mesh_{plane}); refresh on plane move; guard > ~300k
  segments (decimated grid instead); layers['mesh'] off by default;
  _clip_to_cylinder for revolved scenes. build_scene_init/scene_from_meta pass
  refine through. view3d_panel: Display-tab checkbox 'Show mesh' -> 'mesh';
  _apply_all_controls lists it. README "Local mesh refinement (blastFoam)";
  ROADMAP N15 DONE; TASKS rows.
Verify: test_viz3d_scene/panel additions (synthetic refine, toggle, plane
  move, line count == len(mesh_segments_2d(slice_src(...))), screenshot
  differs); manual _e2e_gui_view3d.py on the refined 3D e2e case.
Done when: green; ROADMAP N15 DONE.
```

## T20 — Dynamic AMR: core + schema + validation + writer + goldens (N16)

```
SESSION PROMPT — T20   [DONE 2026-09-05]
Read: ROADMAP.md item N16 and the plan ~/.claude/plans/amr-tranquil-blossom.md;
  core/refine.py; core/case.py (schema, ValidationReport, _validate_solver,
  validate_case refinement + cap blocks); solvers/foam/writer.py (CaseSpec,
  plan_case, _controldict, _setfieldsdict, _dynamicmeshdict, render_case).
Do: refine.remap_from_centres + MeshMap + display_level_for + Plan.amr /
  display_level + _plan_amr + validate_amr; Case2D/3D amr_* fields (schema v5,
  coercion); validate_case AMR rules (native error, zones exclusive, charge
  resolvable, estimator/thresholds, axis warning, maxCells + display caps,
  serial note); CaseSpec.amr/display_level/mesh_fields; _dynamicmeshdict(spec,
  case) adaptiveFvMesh block; cellCentres FO (no live slice); setFieldsDict
  maxRefinement; no static refine dicts for AMR; goldens case2d_planar_amr +
  case3d_amr + amr_checks.
Verify: test_refine (test_amr), test_case_validate (amr_cap_checks),
  test_foam_writer (existing goldens byte-identical, new ones eyeballed),
  test_regression byte-identical, GUI headless suites unchanged.
Done when: green; ROADMAP N16 T20 part DONE.
```

## T21 — Dynamic AMR: per-time ingest path + post-mortem + 2D e2e (N16)

```
SESSION PROMPT — T21   [DONE 2026-09-05; planar AMR charge -> cylindericalMassToCell + backup; defaults 0.4/0.2]
Read: ROADMAP.md N16 (probe numbers), plan file "T21"; solvers/foam/backend.py
  (_mesh_stages, build_remap, _decode_surface, read_2d/read_3d, solve_2d/3d_foam
  read_dir/on_frame, finalize_2d/3d, _initial_frame*); reader.py (read_scalar,
  read_vector, to_grid, time_ready); runloop.py (FoamRunLoop, OrderedIngest,
  PeakImpulse, read_fo_fields, tail_live); postmortem.py load_run;
  tests/test_foam_ingest_order.py, test_foam_reader.py, _e2e_foam_refine2d.py.
Do: reader.read_label_list (0/polyMesh/cellLevel), to_grid(mesh=);
  backend.mesh_at(spec, dpath) -> refine.MeshMap | None (C then cellLevel,
  ValueError = torn -> retry, RuntimeError = fatal); build_remap AMR branch
  (t = 0); _mesh_stages AMR variant (setRefinedFields WITHOUT -noRefine, no
  topoSet/refineMesh, writeCellCentres -time 0 kept, n_procs forced to 1);
  read_2d/read_3d(mesh=), read_fo_fields/PeakImpulse(mesh=); read_dir carries
  the MeshMap in the payload; on_frame logs runloop.amr_note and appends
  frames['levels']; finalize_* re-reads through mesh_at and puts the final
  levels in meta['refine']; FoamRunLoop(live_set=None) skips tail_live (live
  frames = written p through the per-time remap); postmortem per-time path.
  Tests: test_foam_amr_ingest.py (synthetic ascii C/cellLevel/p time dirs with
  changing counts through OrderedIngest, torn-file retry, amr_note text);
  _e2e_foam_amr2d.py (planar 25 kg/m in 2x2 m, base 0.1, 3 levels vs UNIFORM
  0.0125 m: gauge peak within 10 %, arrival within 5 %, impulse within 10 %,
  FO vs Python peak/impulse reported, cells per write, wall-time ratio,
  graceful stop, post-mortem reload identical).
Verify: test_foam_reader, test_foam_ingest_order, test_foam_amr_ingest,
  test_foam_writer, test_regression; WSL: test_foam_2d, test_foam_postmortem,
  test_foam_stop, _e2e_foam_amr2d.py; `wsl.exe -d Ubuntu -- pgrep -a blastFoam`
  must print nothing. Delete /root/amr_probe once the e2e has its own runs.
Done when: green; e2e numbers in ROADMAP N16.
```

## T22 — Dynamic AMR: GUI form + validation line + per-frame mesh in Results (N16)

```
SESSION PROMPT — T22   [DONE 2026-09-05]
Read: ROADMAP.md N16, plan file "T22"; gui/forms.py (row helpers, Numerics
  card, _sync_enabled, get_case/set_case, SetupPanel.show_report); gui/app.py
  _validate; gui/preview_panel.py; gui/results_panel.py (_setup_anim,
  _show_frame); output/plots.py mesh_for; output/animation.py; gui/run_panel.py
  (_rebuild_overlay); tests/test_gui_refine_preview.py, test_gui_results_anim.py.
Do: "Dynamic refinement (blastFoam)" card (levels combo 0..5, estimator combo,
  refine/unrefine/interval/buffer/max-cells entries, display-level combo
  auto/0..L), greyed for native, AMR on <-> zones card + charge combo off;
  get_case/set_case; App._validate line "AMR up to level L (finest X m),
  displayed at level D (N cells)"; preview base grid + caption for AMR;
  plots.mesh_for(levels=); per-frame LineCollection swap in
  ResultsPanel._show_frame and animation.write_animation when
  frames['levels'] exists; hooks.frame(levels=) + RunPanel overlay per write.
  Tests: test_gui_amr_form.py (round trip, native disables, AMR disables
  zones), test_gui_results_anim with a frames['levels'] fixture.
Verify: test_gui_amr_form, test_gui_refine_preview, test_gui_results_fields,
  test_gui_results_anim, test_case_validate, test_regression.
Done when: green.
```

## T23 — Dynamic AMR: 3D viewer per-frame mesh + 3D e2e + docs (N16)

```
SESSION PROMPT — T23   [DONE 2026-09-06; 3D arrival +18 % vs static reference recorded as an open N16 finding]
Read: ROADMAP.md N16, plan file "T23"; viz3d/viewer.py _MeshEdges;
  viz3d/sampling.py (build_scene_init, build_frame, FrameStore);
  viz3d/client.py; gui/view3d_panel.py; tests/test_viz3d_scene.py,
  test_viz3d_panel.py, _e2e_foam_refine3d.py.
Do: frame3d payload `levels` (int8 display grid, AMR only, undecimated);
  _MeshEdges rebuilds per frame when levels are present (cache key + frame
  id), static runs keep the cached edges; _e2e_foam_amr3d.py (8 kg in a 3 m
  box, base 0.1, 3 levels, display 1 vs uniform 0.05 m SMEAR reference at the
  display level: gauge peak within 10 %, arrival within 5 %; cells per write,
  wall time, extrapolated uniform-finest cost); README "Dynamic mesh
  refinement (blastFoam)"; ROADMAP N16 DONE + parallel follow-up item; TASKS
  rows; amr_prompt.md marked done; test matrix block.
Verify: test_viz3d_scene/panel (per-frame levels change the line count,
  static cache intact); WSL: _e2e_foam_amr3d.py, _e2e_foam_refine3d.py,
  test_foam_3d_smoke --tiny; pgrep -a blastFoam empty.
Done when: green; ROADMAP N16 DONE.
```

## Notes for whoever runs these

- T1–T5 are independent of each other and can be done in any order; T6
  touches `_preflight`, so do it before T9. T9 (refactor) should come after
  T1/T6/T10 so the fixes are extracted once. T11 before T12; T4 before T14.
- If a session finds its line numbers drifted, it should Grep the function
  names given in the brief instead of reading whole files.
- Every session ends by updating ROADMAP.md and this file; keep both in the
  same commit as the code so the docs never lie about the state.
