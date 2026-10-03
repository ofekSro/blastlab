# GUI-11 part 11b — verification report (T7-T9)

Plan: `docs/batches/2026-10-03-gui-polish.md`, part 11b.
Implementer's report: `2026-10-03-gui-polish-b.implement.md`.
Commits verified: `bd8878d`, `65c741f`, `f02f65a`, `1b1ed01`, `286e98a`
(base `2753eb6`). Branch `gui-redesign`.

Verifier fixes: `9d83f5b`, `f694d0d`, then this report.

Before starting:
- CLAUDE.md §8.2 dry run: `auto_cleanup` reads `False`.
- No WSL command was run. No foreign process was touched.
- Every window used throwaway settings (`ensure_qapp`, or a temporary
  `BLASTLAB_SETTINGS`).
- Two temporary worktrees were used (at `2753eb6`, and a scratch copy of
  HEAD for the F42 trial). Both were removed, and `git worktree list`
  shows only the main tree.

Verdicts: **T7 VERIFIED**, **T8 FIXED**, **T9 VERIFIED** (one documented
deviation, accepted).

---

## T7 · F28: a stage start forgets the last stage's progress — VERIFIED

**1. The new test passes, and fails without the line — PASS.**
- At `2753eb6` plus the new test (a worktree):
  `test_worker_stage_progress.py` gives `FAIL (2)`. The queue after
  `run_started` holds `('progress', 201)`. With the real `step_gate`
  held it holds `[run_started, progress 201, paused]`.
- At HEAD it passes (8 checks).

**The race the brief asked about: no legitimate post is lost — PASS.**
- From the code:
  - `progress()`, `flush_progress()` and `run_started()` all run on the
    solver thread.
  - The native solvers and the blastFoam run loop call `progress`
    after `run_started`. `progress_line` runs in the run loop, not in
    the stdout pump threads.
  - `flush_progress` is called only from `step_gate` and
    `SolverWorker.run`.
  - So clearing `_last_p` in `run_started` can only drop a Progress of
    the stage before.
- Measured with my own probe (`probe_t7_race.py`, scratchpad): a real
  `SolverWorker` running fake stages that call the hooks in the
  solvers' order (`run_started`, then per step `step_gate` and
  `progress`).
  - **Free-running chain** (3 × 50 steps) and **single run** (200
    steps): no progress of another stage follows a `run_started`. Each
    stage ends on its own final step (1050 / 2050 / 3050; 1200).
  - **Held chain** (Pause, then Exec 1 at every hold, 2 × 5 steps):
    gate k of stage s shows step k of stage s. The first gate of each
    stage shows none:
    `[(1, None), (1, 1001) … (1, 1004), (2, None), (2, 2001) … (2, 2004)]`.
  - **Held single run** (4 steps): no step is lost.
- At `2753eb6` the same probe fails three checks. Gate 1 of stage 2
  shows step 1005, from stage 1. So the probe can tell the two apart.

**2. `test_regression` byte-identical — PASS.** It was run last, after
the verifier's fixes: seven files byte-identical, `b2_profile.npz`
arrays equal.

**3. `test_ui_chain_screen` and `test_ui_run_screen` green — PASS.**
- `test_ui_chain_screen`: 213 checks, F28 included.
- `test_ui_run_screen`: 203 (201 + the verifier's 2).
- `test_ui_run_panel`: PASS.

**4. Real platform — PASS.**
- `_e2e_ui_chain_screen.py`: 23 checks, platform `windows`.
- The implementer's held-chain probe (`p_t7_held_real.py`), re-run by
  the verifier:
  - the strip reads `PAUSED`;
  - STEP, TIME, dt and P MAX read `—`, the percent `0 %`, the strip
    `02 2D 0 %`;
  - the window is Win32-visible;
  - `RESULT PASS`.
- D217's `_last_step = None` only feeds the badge and the time line
  (`run_panel.py` 1288, 1322). Nothing else reads it.

## T8 · UXR-2: a gauge inside an obstacle — FIXED

**1. `test_case_validate` new cases — PASS.** 141 checks. 2D (axisym)
and 3D, native and blastFoam:
- a gauge inside the box gets exactly the new warning;
- a gauge on the face or outside gets none;
- the errors are unchanged.

Planar 2D is not in the committed test. My probe covers it (below).

**2. `test_char_validation` green, unedited — PASS.**
- `git diff 2753eb6..HEAD` over `test_char_validation.py` and
  `char_golden/` is empty.
- The suite passes.

**3. `test_ui_results_screen` S5g — PASS.** 194 checks. Results:
- the cells read `G3`, `G1`;
- the caption names G2;
- `rows()` and the headers are unchanged;
- the keys are `[2, 1]`.

**4. `test_ui_run_screen` R5b — PASS.**

**5. `test_ui_char_results_meta`, `test_ui_char_results_exports`,
`test_char_exports` — PASS**, all unedited.

**6. Real platform — PASS.** The implementer's `p_t8_checks_real.py`
probe, re-run: platform `windows`. Checks lists `Gauge (3.1, 1.0)
inside an obstacle - will be dropped`. The window is Win32-visible.

**No verdict, golden or number changes — PASS.**
- The new line is a `warn` only (`errors` unchanged in every case
  above).
- `rep.warnings` drives only displays: the Qt and Tk Checks, the Chain
  card and pill, and the CLI print.
- Frozen-path diff `116ea96..HEAD`: only `solvers/worker.py` (1 line)
  and `services/validation.py`. After the verifier's commit,
  `validation.py` also has a docstring edit, with no code change.

**The "strictly inside" test against each solver's own drop rule.**
Real `solve_2d` / `solve_3d` (tiny End time; the gauge setup's own log
lines are the truth), and `writer.plan_case(...).gauge_ids` for
blastFoam. Probe: `probe_t8_drop.py`. W = warned, N = native drop,
F = blastFoam drop.

- **2D planar and 2D axisymmetric**, box x 1.006-1.494 on 0.01 m cells
  (no auto-refine):
  - (1.012, 0.6): W, N, F (agree);
  - (1.25, 0.334), (1.25, 0.966), (1.25, 0.6): W, N, F (agree);
  - **(1.008, 0.6): W, kept natively, F**. The nearest centre, 1.005,
    is outside the box;
  - **(1.492, 0.6): W, kept natively, F**;
  - **(1.004, 0.6): no W, kept natively, F**. This is blastFoam's
    outward snap to x 1.00.
- **3D**, box x 1.06-1.94, z 0.43-1.27 on 0.1 m cells (`smear`):
  - **(1.08, 0.6, 0.8): W, kept natively, F**;
  - **(1.5, 0.6, 0.41): no W, N, F**. This is the native half-cell
    zone: the centre at z 0.45 is solid;
  - (1.03 / 1.01 / 1.06, 0.6, 0.8): no W, kept natively, F (the snap);
  - the rest agree.
- With the charge auto-refined (0.1 m asked, about 0.003 to 0.01 m
  used), only the on-face gauge (1.06, 0.6) disagrees.
- **blastFoam never keeps a warned gauge.** The warning is a subset of
  its drop (a closed test on the outward-snapped boxes).

**What the user sees when they disagree** (F44):
- *Warned, kept natively:* Checks says `will be dropped`, but the
  native run keeps the gauge:
  - no drop line in the log;
  - nothing named in Run or Results;
  - the gauge reads the fluid cell just outside the face (its tooltip
    shows that cell centre).
- *Not warned, dropped* (the face and snap zone, both solvers):
  - Checks is silent;
  - the run drops the gauge (natively with a `[warn]` line; blastFoam
    without one);
  - Run and Results then name it, `G<n> dropped by the solver (on the
    face of Wall 1)`.

The implementer documented the second case but not the first. The
docstring of `_in_obstacle_open` claimed "Both solvers drop such a
gauge". Fixed to say when native keeps it (`f694d0d`, comment only).
The rule itself is the plan's (the open box), so it is not changed.
This is an owner call (F44).

**On-screen labelling** (`probe_t8_numbering.py`, toolkit-free, plus
the suites):
- **No drop:** every label is `G<payload number>` and no caption note.
  Both screens behave as before: `rows()` gives `label == G<number>`
  for every row. R5b's last check and S5g's last check pass.
- **Two drops** (G2 inside Wall 1, G4 outside the domain, five
  entered, three series):
  - labels `G1, G3, G5`;
  - keys `1..3` (D61);
  - caption `G2 dropped by the solver (inside Wall 1) · G4 dropped by
    the solver (outside the domain)`.
  - Correct.
- **A series that matches nothing:** plain labels, no drop named.
  Correct.
- **Defect 1 (fixed, `9d83f5b`).** blastFoam's live 3D payload carries
  x only (`radii`). Case: G2 inside a wall, G3 at the same x.
  - At `286e98a` the live column read `G1, G2` and named
    `G3 dropped by the solver`, the wrong gauge.
  - The finished Results (full points) read `G1, G3` and named G2.
  - Now an x-only tie names no drop and keeps the payload labels (the
    implementer's own "count does not add up" fallback).
  - With no x tie, the entered numbers are still named.
  - `_match` is unchanged, so no Z changes.
  - New checks: R5b +2.
- **Defect 2 (fixed, `9d83f5b`).** The Results Field caption (`Cyan
  tick … arrival at G2.`) kept the payload number. For the same
  selected gauge, the Gauges table now said `G3`.
  - `FieldView.set_arrival` now takes `GaugesView.label(n)`.
  - New checks: S5g +2. With the fix, the caption reads `arrival at
    G3.`.
- **Not fixed (low).** `labels_and_dropped` is wrapped in a bare
  `except Exception` that falls back to plain labels. That matches the
  existing `z_values` pattern and is display-only, but it hides a
  traceback.

## T9 · QA S2-1: the 1D hand-off reach — VERIFIED (deviation accepted)

**1. `test_ui_char_chain_wiring` green, unedited — PASS.** The diff is
empty, and the suite passes.

**2. `test_ui_chain_screen` (213) and `test_ui_chain` (114) green —
PASS.**

**3. Unit checks — PASS** (S5r, 13 checks). My probe
(`probe_t9_reach.py`) also checks the rule against the solvers' **own**
remap warning. It runs a real native 1D (terminating Outer) and then
the real 2D / 3D remap, either side of the predicted limit:

- 1D → 2D axisym, 4 × 4, cy 2 (limit 2.0):
  - R 1.9: solver silent, Chain silent;
  - R 2.1: solver `[warn] … (2.10 m)`, Chain warns with `below 2.0 m`.
- Wall at r 1.2 (limit 1.2):
  - R 1.15: both silent;
  - R 1.25: both warn, with `below 1.2 m`.
- 1D → 3D, 2 × 2 × 2, centre (1, 1, 1) (limit 1.0):
  - R 0.95: both silent;
  - R 1.05: both warn.
- The QA case (10 m into 4 × 4) gives the plan's exact first text.
- With an End time of 0.3 ms: `{}`.

**4. Real platform — PASS.**
- `_e2e_ui_chain_screen.py`: 23 checks.
- The implementer's `p_t9_chain_real.py`, re-run:
  - card 2 reads `● 1 warning`, the pill `Stage OK · 1 warning`;
  - the plan's message is there;
  - Run chain is enabled;
  - Win32-visible.

**The End-time deviation — accepted, owner question kept.**
- `solver1d` stops at the End time or at arrival at a terminating
  Outer, whichever comes first (`solver1d.py` 124-133, 214-216). So
  with an End time the hand-off radius is not known before the run.
- The verifier's e2e confirms E3 hands off at t = 0.300 ms
  (`handoff_1d_to_2d.txt … t = 0.300 ms`). E3 still reads `● case OK`.
- The implementer's own shot shows the run's `[warn] 1D profile shock
  radius (0.70 m)`. So in E3 the Chain is silent while the run warns.
  The plan's text would have stated a false 1.0 m.
- A sound middle way exists for the owner: with an End time,
  R_handoff ≤ `radius_m`. So `radius_m` ≤ limit proves silence, and
  above it the check could say "may reach". This is not done, because
  it is new wording.

**The S5 fixture change hides nothing.**
- Stage 1 is set to 1.5 m only after two new checks assert the default
  seed's warning (on card 2 only, Run chain enabled).
- The error-path checks that follow still test Lx `abc`, cy 99, the
  hand-off conflict and the debounce.
- No check was removed or weakened.

---

## F42 — exported gauge labels after a dropped gauge

**Reproduced** with a real native 2D run (`probe_f42.py`):
- entered: (0.83, 0.61), **(1.2, 0.6) inside the wall**, (1.53, 1.71);
- the solver logs `[warn] Gauge (1.2, 0.6) inside an obstacle -
  dropped`;
- points: (0.8263, 0.6053), (1.5316, 1.7105).

The Summary .csv reads:

```
"G1 (0.830, 0.610) -> cell (0.826, 0.605) m",910.6,…
"G2 (1.200, 0.600) -> cell (1.532, 1.711) m",207.6,…
```

Row 2 puts the dropped G2's entered position beside G3's cell.

**Wrong:** every caller of `summarize_gauges(…, requested=meta['gauges'])`.
- **Summary .csv**: `services/exports.summary_rows` →
  `save_gauge_summary`. This covers the Qt and Tk export buttons, and
  the copy that `services/model_folder.write_all` writes into **every
  model folder** automatically.
- **HTML report, Gauges table** (`output/report.py` 171). This is also
  written into every model folder.
- **Qt Results**: the tooltip of the Gauge cell (`row[0]`). After D201
  the cell says `G3` while its tooltip says `G2 (1.200, 0.600) -> …`.
- **Tk Results**: the summary table's Gauge column, on screen
  (`gui/results_panel.summary_rows`).

**Right:**
- the gauge TSVs (`p_(x,y)` headers from the points);
- the gauge figure titles (`Gauge k (snapped point)`);
- the report's KB rows (`kb_rows`, `gauge_labels` without `requested`);
- the 1D outputs (radii);
- the Run live column;
- Copy table (the cells, entered labels).

**Minimal fix** (not applied; `output/` is frozen). `output/` cannot
import `ui/`, so `match_gauges` cannot be used there. In
`output/gauge_summary.gauge_labels`, pair by nearest entered gauge only
when the points are fewer than the entered gauges:

```python
    pair = (list(range(len(pts))) if len(pts) >= len(want)
            else _nearest_entered(pts, want))
    for k, pt in enumerate(pts):
        label = f'G{k + 1} {fmt(pt)} m'
        j = pair[k]
        if j is not None and j < len(want) and len(want[j]) == len(pt):
            ... same as today, with want[j] for want[k] ...

def _nearest_entered(pts, want):
    """Nearest entered gauge (0-based) per point, each taken once."""
    # greedy, squared distance, same-dimension entries only
```

The full 23-line diff is kept as `f42_minimal_fix.diff` in the
session scratchpad.

**Byte impact, measured.** The fix was applied in a scratch worktree
of HEAD, and the export suites were run there:
`test_char_exports`, `test_char_summary`, `test_gauge_summary`,
`test_ui_char_results_exports`, `test_gui_char_exports` and
`test_gui_gauge_summary`. All PASS, **unedited**.

- **No dropped gauge:** byte-identical, by construction (index pairing
  kept).
- **A dropped gauge (2D/3D, native or blastFoam):** only the first
  (Gauge) column of the Summary .csv and of the report's Gauges table
  changes, for the gauges after the drop.
  - In the run above, row 2 becomes
    `"G2 (1.530, 1.710) -> cell (1.532, 1.711) m"`. Same file size
    here (324 B); every number column is identical.
  - For blastFoam, where a probe sits exactly at its entered point,
    the label can also lose its `-> cell (…)` part.
- **Variant (b):** also print the entered number (`G3 …`), so the
  export agrees with D201's screens. This changes the `G<k>` prefix
  too.
- **Either variant:** the Tk gate must run, because `output/` is
  shared.

---

## Defects found in the 11b diff

1. **Medium.** `ui/run_gauges._numbering` named the wrong gauge as
   dropped on blastFoam's x-only live 3D payload when a kept gauge
   shares the dropped one's x. **Fixed** in `9d83f5b` (D218).
2. **Low.** The Results Field caption's arrival tick kept the payload
   G number beside the relabelled Gauges table
   (`ui/results_field.py` 968, `ui/results_panel.py` 790). **Fixed**
   in `9d83f5b` (D218).
3. **Low.** `services/validation._in_obstacle_open`: the docstring
   claimed both solvers drop a strictly-inside gauge, and native can
   keep it. **Fixed** in `f694d0d`, comment only. The behaviour gap is
   **F44**, an owner call.
4. **Low.** `ui/results_gauges.set_result`: the bare `except
   Exception` around `labels_and_dropped` hides tracebacks. It matches
   the `z_values` pattern. **Not fixed.**
5. **Note.** `test_case_validate`'s new cases are axisymmetric only, so
   planar 2D is untested there. The verifier's probe shows planar
   behaves the same. **Not changed.**
6. **Process note** (the verifier's own). One scratch probe file was
   patched once with a heredoc'd Python command, against the brief's
   rule. It was a scratchpad file, not a repo file, and every repo edit
   went through Edit/Write.

No debug prints, no leftover TODOs, no unrelated numerical change. No
caller of a re-signatured function was missed:
- `set_arrival` has one caller;
- `_numbering`'s new parameter is optional;
- `_row`'s `label` is optional.

## Engineering questions

None numerical. Owner calls:
- F42: apply the minimal fix, variant (a) or (b)?
- F44: the native false positive.
- D200: the End-time condition.

## Tests run (one at a time; the Qt suites offscreen with private settings)

- `test_worker_stage_progress` (8)
- `test_case_validate` (141)
- `test_char_validation`
- `test_foam_writer` (370)
- `test_char_case_json`
- `test_ui_chain_screen` (213), `test_ui_chain` (114)
- `test_ui_char_chain_wiring`, `test_ui_char_results_meta`,
  `test_ui_char_results_exports`, `test_char_exports`,
  `test_ui_char_hd13_run`
- `test_ui_run_screen` (203), `test_ui_results_screen` (194),
  `test_ui_results` (130), `test_ui_run_panel`
- `test_ui_no_vtk_in_main`, `test_ui_no_mpl_pyplot` (19),
  `test_ui_setup_strip` (110)
- `test_char_summary`, `test_gauge_summary`

All rc 0, with no `[FAIL]`.

- Tk, with a scratch `BLASTLAB_SETTINGS`: `test_gui_char_write_failure`,
  `test_gui_drain`, `test_gui_gauge_summary`, `test_gui_char_exports`,
  `test_gui_char_results_meta`. All PASS.
- Real platform (`windows`):
  - `_e2e_ui_chain_screen.py` (23);
  - the T7, T8 and T9 probes, each `RESULT PASS`.
- **`test_regression`, last:** PASS, byte-identical.

## Files touched by the verifier

- `blastlab/ui/run_gauges.py`, `blastlab/ui/results_field.py`,
  `blastlab/ui/results_panel.py`
- `blastlab/services/validation.py` (docstring only)
- `blastlab/tests/test_ui_run_screen.py`,
  `blastlab/tests/test_ui_results_screen.py` (new checks only)
- `docs/gui-redesign-decisions.md`: D218, F44, and a "Verify 11b"
  addendum on F42
- this report

## GUI screens that need QA

- **02 Run, held chain at a stage start:** `—` tiles, the `PAUSED`
  badge.
- **02 Run, live gauges after a drop:** the entered labels and the
  caption.
- **A blastFoam 3D run with a dropped gauge** that shares x with a
  kept one: payload labels, no drop named.
- **03 Results ▸ Gauges after a drop:** the labels, caption and
  readout. Also the Gauge tooltip, still wrong per F42.
- **03 Results ▸ Field:** the arrival-tick caption names the same G as
  the Gauges table.
- **01 Setup ▸ Checks, the Chain stage Checks, the Tk validation list:**
  the `inside an obstacle` warning.
- **Chain:** the hand-off reach warning on card 2, its pill and its
  Checks.

## Still open

- **F42:** the export label pairing. Owner decision; the minimal fix
  and its byte impact are above.
- **F43:** the finish notification's G number.
- **F44:** the native false positive of the new warning.
- **D200:** the End-time stages are not checked; E3 is silent while
  its run warns.
- The 2D → 3D reach is not predicted (backlog, D200).

**Verdict:** ready for QA. T7 and T9 are verified, and T8 is verified
after two small UI fixes. F42 and F44 are owner calls.
