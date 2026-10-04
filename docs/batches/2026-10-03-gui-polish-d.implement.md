# GUI-11 part 11d — implementation report (T16-T22, plus F43, F40, F46)

Batch plan: `docs/batches/2026-10-03-gui-polish.md`, part 11d. Branch
`gui-redesign`, from `4d0fb1c` (11a, 11b and 11c done and verified). One
commit per task; each message in its own file (`impl11d_msg_NN_*.txt`,
`git commit -F`). Nothing pushed.

Before starting:
- CLAUDE.md §8.2 dry run: `auto_cleanup` reads `False` (and again at the end).
- Working tree: only the never-stage paths were dirty; none was staged.
- No WSL solve was run. `wsl -d Ubuntu -- pgrep -a blastFoam` was empty at the
  end (the only WSL commands were that probe and the app's own chip probe).

Session additions (the caller's, before T22): **F43, F40, F46**, UI only, each
with a D-row after D224. F42, F44 and F45 were not touched.

---

## Summary

| Task | Status | Commit(s) |
|---|---|---|
| T16 · D191: `●` whenever the case name is elided | DONE | `8c9fe50` |
| T17 · D192: a visible dark tree hover | DONE | `022aedb` |
| T18 · QA S3-1 / S3-2 / S3-7: Run strip and live view | DONE | `9d5f623` |
| T19 · F17: shorter on-screen 1D title | **SKIPPED (blocked)** | `02024f6`, reverted by `0d71956` |
| T20 · UXR-10 small half: method card | DONE | `238a49a` |
| T21 · QA S3-6 text half: Results 3D placeholder | DONE | `48a3ba7` |
| F43 · finish notification names the entered gauge | DONE | `9f52b4a` |
| F40 · Show Details with the whole path | DONE | `f553c3b` |
| F46 · refusal re-worded after r z / x y toggle | DONE | `49c7dfa` |
| T22 · harness F38 + F36, passes, R10, matrix | DONE (F36's WSL step: office machine) | `389a489`, `c171f6f`, `49f9a75`, `cefbe89`, docs commit |

---

## T16 · D191 (GUI-11 a): `●` whenever the case name is elided — DONE

**What was done.** `TopBar._fit_marker` shortens `● unsaved` to `●` (tooltip
`Unsaved changes`) whenever the case name would be elided beside the whole word:
its whole width is past the button's 200 px cap, or the bar's size hints with the
whole name and the whole word are wider than the bar. D198's squeeze rule still
applies. It is predicted from size hints, never read back from the shown text, so
it cannot flip-flop; a name that fits whole only because the word dropped keeps
`●`. D225.

**Files:** `blastlab/ui/topbar.py`, `blastlab/tests/test_ui_frame.py`,
`docs/gui-redesign-decisions.md`.

**Tests:** `cd blastlab/tests && python test_ui_frame.py` (F10b new; 86 checks).

**Criteria**
- PASS. 1100 px, 30-character name, dirty → `●`; 1600 px, `wall_A`, dirty →
  `● unsaved` (F10b).
- PASS. An elided name with a clean case shows no marker (F10b).
- PASS. Real platform (`real_t16_topbar.py`, scratchpad): 32 bar states (✓ / ✓ /
  dirty / four chips) × 3 names × 1100 / 1280 / 1600 px = 288 states, `0D · HD
  1.3` 94 px in every 1100 px state, nothing outside, 0 bad. K02 `--window` (T22)
  is clean in both modes and both solver modes.

## T17 · D192 (GUI-11 b): a visible dark tree hover — DONE

**What was done.** `TREE_HOVER_BLEND['dark']` 0.76 → 0: the dark tree hover is the
global `hover` `#1c1c1f`, 1.13:1 from the panel (was 1.02). Dark `num_dim` on it
is 4.06:1, accepted by the owner. Light unchanged (t 0.66). D212.

**Files:** `blastlab/ui/theme.py`, `blastlab/tests/test_ui_theme.py`,
`docs/gui-redesign-decisions.md`, `docs/qa/2026-10-03-gui-polish/gui11-dark-tree-hover.png`.

**Tests:** `python test_ui_theme.py` (T6).

**Criteria**
- PASS. `test_ui_theme` prints the dark hover `#1c1c1f`, its contrast to the panel
  (1.13 > 1.02) and every role's ratio. All ≥ 4.5 except dark `num_dim` 4.06 ≥ 4.0.
- PASS. Real platform: the screen pixel under an unhovered row `#0e0e10`, hovered
  `#1c1c1f` (the real cursor moved onto `03 Boundaries`; screenshot).

## T18 · QA S3-1, S3-2, S3-7: the Run strip and the live view — DONE

**What was done** (D213).
- **S3-1.** `_RunStrip._one_row_fits` also asks that the P MAX tile's one-row
  share (stretch 10 against Progress's 23, Progress at `PROGRESS_MIN`) hold
  `8.888e+05 kPa` at StatTile's 14 px floor, measured with `QTextDocument` from the
  value's font (never geometry). Otherwise the strip wraps as at 1100. Real
  platform: two rows up to 1400 px, one row from 1420 px. **So the default 1280 ×
  840 now shows two rows** (170 px instead of 82). Readout strings unchanged.
- **S3-2.** A `StyleChange` / `FontChange` re-arranges the strip (`force=True`,
  deferred one turn). The measured cause of the squeeze was the overfull centre:
  its children's minimums summed past the panel (755 against 610 px), so Qt shrank
  everything, the Fixed strip included; S3-7's fix removes that.
- **S3-7.** `runview` has a 200 px minimum (`VIEW_MIN`). `_fit_dock` gives the dock
  what is left with the view at 200, down to its 42 px tab strip; when not even
  that fits (1100 × 720 after a chain with its banner), the dock steps aside
  (hidden) and returns when there is room. Decided with the dock counted as shown,
  re-fitted on the centre's `LayoutRequest`.

**Files:** `blastlab/ui/run_panel.py`, `blastlab/tests/test_ui_run_screen.py`,
`docs/gui-redesign-decisions.md`, three screenshots.

**Tests:** `python test_ui_run_screen.py` (R12 new; 214 checks).

**Criteria**
- PASS. Offscreen: after `theme.apply` to the other mode (and back) at 1100 × 720
  with a chain strip and the banner, every tile ≥ its `minimumSizeHint`.
- PASS. 1100-1600 px in 20 px steps: P MAX's value label ≥ the readout's advance at
  the face it chose (`8.888e+05 kPa`).
- PASS. Real platform: 1280 × 840 with `5.818e+05 kPa` → label 175 px ≥ 145 px
  rendered, `kPa` whole (`gui11-run-pmax-1280.png`). A **real 2-stage native
  chain** (1D → 2D), then 1100 × 720 → `runview` 237 px ≥ 200, no tile under its
  minimum before and after a Dark-mode toggle (`gui11-run-chain-1100x720.png`,
  `…-toggled.png`).
- PASS. R10 on the run surface (T22): tabs / theme 0 ms, resize median 43.3 ms.

## T19 · F17 (GUI-11 f): a shorter on-screen 1D figure title — SKIPPED (blocked)

**What happened.** Implemented as planned (`results_fields.screen_title_1d`: `1D
spherical · 1.0 kg TNT · JWL` on the on-screen figure only, the user's title line
above, `output/plots.py` untouched). `test_ui_char_results_exports` stayed green;
the new `test_ui_results_screen` checks and a real-platform check in
`_e2e_ui_results.py` passed (title x 107-364 of a 405 px canvas, top 468 of 483,
at 1100 × 720).

**Why it is not in.** `test_ui_char_results_meta` went red: its golden
`char_golden/ui_results_meta.json` pins the **on-screen** 1D figure's title (five
`title` entries and the derived `fields` hash). The plan keeps that suite green and
unedited, and this session may not touch a golden. The plan did not foresee the
pin. The commit `02024f6` was reverted (`0d71956`); the tree is as before T19.

**What is needed.** The owner's approval to re-record exactly those entries
(old `1D Spherical Blast - 1.0 kg TNT - EOS: JWL`, new `1D spherical · 1.0 kg TNT ·
JWL`, plus the `fields` hash), as T11 had for `ui_case_form.json`. Then `git
revert 0d71956` and the re-record in its own commit. Recorded as D214 and in F17's
Outcome.

## T20 · UXR-10 (the small half): the method card — DONE

**What was done** (D226).
- A 2D planar charge reads `kg/m`.
- The cell size reads `{:.3g}` (`cell 12.4 mm`); amends D90.
- Afterburn `miller` reads `miller (calibrated for TNT only)` when the material is
  known and not TNT (CLAUDE.md §7).
- The Ended value word-wraps onto at most two lines (`results_panel.TwoLineLabel`),
  the second line elided with the whole text as its tooltip. A plain word-wrapping
  `QLabel` was tried first: its height-for-width made the left column grow past the
  window and stopped the result list scrolling (`test_ui_results_screen` S2a went
  red), so the lines are broken at the label's width instead.

**Files:** `blastlab/ui/results_method.py`, `blastlab/ui/results_panel.py`,
`blastlab/tests/test_ui_results_screen.py`, `docs/gui-redesign-decisions.md`.

**Tests:** `python test_ui_results_screen.py` (S2c +8; 213 checks).

**Criteria**
- PASS. A planar fixture reads `1 kg/m TNT · x 0, y 0.7 m`.
- PASS. `dx 0.0124352` reads `cell 12.4 mm`.
- PASS. A C4 blastFoam fixture with `miller` shows the caveat; TNT does not.
- PASS. The Ended label's `wordWrap()` is True, at most two lines.
- PASS. `test_ui_char_results_meta` green, unedited.

## T21 · QA S3-6 (the text half): the Results 3D placeholder — DONE

**What was done** (D215). `results_panel.ResultsView3DHost`, a `View3DHost`
subclass, overrides only `PLACEHOLDER`: `Select a 3D result, then press` / `Open
the 3D viewer in the` / `Export column.` The plan's break (`…Open the 3D viewer` /
`in the Export column.`) made the first line 49 characters, longer than the shared
text's longest (41), against its own rule; the same words on three lines are 223 px
against 310 px. `view3d_host.py` untouched.

**Files:** `blastlab/ui/results_panel.py`, `blastlab/tests/test_ui_results_screen.py`,
`docs/gui-redesign-decisions.md`, `gui11-results-3d-placeholder.png`.

**Tests:** `python test_ui_results_screen.py` (S3e new).

**Criteria**
- PASS. `results.view3d._holder.text()` is the new text;
  `isinstance(results.view3d, View3DHost)` holds.
- PASS. The Results centre's `minimumSizeHint().width()` at 1100 × 720 is 261 px
  with either text.
- PASS. R10-PLACE `tabs` on the results surface: 0 ms over 1758 samples.

## F43 · the finish notification's gauge number — DONE

**What was done** (D227). `MainWindow._peak_label` labels `highest_peak`'s series
through `run_gauges.numbering` with the last stage's case, the mapping the 02 Run
column uses (D201 / D218). Nothing dropped, or no case: the payload number as
before. `ui/app.py` only.

**Tests:** `python test_ui_run_screen.py` R6 (+2): G2 inside Wall 1, the higher
peak on the second series → `Highest peak: G3, 296 kPa`. The existing `G2, 296 kPa`
check is unchanged. **Commit:** `9f52b4a`.

## F40 · Show Details with the whole path — DONE

**What was done** (D228). When `dialogs._keep_paths` elides a path, the box's
detailed text (`Show Details…`) holds each shortened path whole, one per line,
without its quote or trailing punctuation; a quoted OSError repr has its doubled
backslashes halved back. A box whose paths fit gets no details. `ui/dialogs.py`
only.

**Tests:** `python test_ui_frame.py` F13 (+3). Real platform
(`real_f40_details.py`): a real click on `Show Details...` shows the pane;
Ctrl+A, Ctrl+C copies exactly the path (`gui11-dialog-details.png`).
**Commit:** `f553c3b`.

## F46 · the refusal follows the r z / x y columns — DONE

**What was done** (D229). `PointList._reject(message, words)` keeps a callable
for a refusal that names the columns (the wrong count, an empty Add);
`set_columns` re-words a standing refusal with the new names, still red. Other
refusals stay as they are. `ui/fieldform.py` only; Setup and every Chain 2D stage.

**Tests:** `python test_ui_setup_form.py` S8b (+4 per placement).
**Commit:** `49c7dfa`.

## T22 · F38 + F36, the passes, R10 and the close — DONE (F36's WSL step not run)

### Harness fixes

- **F38** (`389a489`, calibrated in `c171f6f`). `_clipped_labels` measures a
  QToolButton against its label rect: width less the box its size hint puts
  around the text, less the 3 px the style sheet adds to every tool button's hint
  and never paints (`qstylesheetstyle.cpp`, CT_ToolButton, `// ### broken
  QToolButton`), with no slack.
  - Probe (not committed), `0D · HD 1.3` forced to 72 px: reported (`needs 61 has
    48`); at 94 px nothing; real platform and offscreen.
  - Calibration, real platform, against the painted ink of that segment at fixed
    widths 80-96 px: elided at 80-84 px, whole from 85 px; the check reports exactly
    80-84.
  - The first `--window` pass ran with the uncalibrated box (27 px instead of 24)
    and reported the 40 px `1D` / `2D` / `3D` segments, which are whole (165 S2).
    That pass was stopped by its own PID (17976; its child had already exited) and
    set aside as `gui11-d-window-stale`; it is not the evidence.
- **F36** (`389a489`). F02 expects the VTK export disabled on a fresh foam result
  with `services.exports.SCRATCH_RELEASED` as its tooltip, then runs the case with
  Keep all fields on and expects the export offered and `VTK export done`, only on
  an idle VM with ≥ 3 GB free, else a note `office machine`. F10 expects the same
  on the cached foam result. **Not run: no WSL solves in this session → office
  machine.**

### Pass 1 · `--window --solver native --scenario B06,K01,K02,K03`, 1100 × 720

`~\blastlab_qa\gui11-d-window`, real platform, `PYTHONIOENCODING=utf-8`: 4 of 4
`done`, 522 `ok` lines, findings 0 S1 / 0 S2 / 2 S3.

1. PASS. **K02:** 186 states × `nothing clipped` and 186 × `nothing outside`, 0
   findings, dark and light, native and blastFoam, now including tool-button
   elision.
2. PASS. **K03:** luma 196.4-246.0 ≥ 140 on all eight light grabs.
3. PASS. **B06:** 13 `ok`, 0 findings (F5 starts a run, Shift+Esc stops it, Ctrl+O /
   Ctrl+S, plain Esc, Tab order).
4. The two S3 are F30's `External WM_DESTROY` in K03 (D195, predates the redesign;
   viewer-host batch).

### Pass 2 · offscreen `--solver native --only B,C,D,E,G,H,K`, diffed against GUI-10

`~\blastlab_qa\gui11-d-head`, one invocation (no exit 75), 43 IDs `done`, none
crashed, 0 S1. `gui10-head`'s findings were filtered to the same groups (5 of 6)
before the diff (`docs/qa/2026-10-03-gui-polish/findings-diff-11d.txt`):

| Severity | new | gone | same |
|---|---|---|---|
| S1 | 0 | 0 | 0 |
| S2 | 0 | 0 | 4 (K02 run banner) |
| S3 | 0 | 0 | 1 (G01 `QFontEngineFT`, F26, offscreen only) |
| S4 | 1 | 0 | 0 |

Dispositions:
- **new S4** `Tight layout not applied` (K02, Results, a chain's 1D stage at 1100 ×
  720): `--scenario G02,K02` offscreen gives the identical finding at `116ea96`
  and at HEAD (`gui11-d-tight-base` / `-head`, diff: same 1). It appears only when
  G02's chain and K02 share a process; GUI-10 ran them in different invocations.
  Predates GUI-11. **F49.**
- **The four K02 S2 `same`** keep their keys but name a different label: GUI-10's
  was P MAX `2.799e+06 kPa` (fixed by T18); now it is the Progress time line `Done
  in 22 s · shock arrived at a terminate boundary (p_edge = 1.015e+05 Pa)`, 419 px
  in 404. Cut identically at `116ea96` (offscreen A/B, temporary worktree,
  removed). QA S4-e, already in the backlog. **F48.**

### Pass 3 · F02 and F10 in WSL — not run (office machine), by the session's rule.

### R10 (pre-registered in `49f9a75` before any sampled run; results in `cefbe89`)

Real platform, `c171f6f`, `--repeat 5`, one sampler at a time. Each self-test saw
the 60 px / 150 ms displacement (149.5-149.8 ms). Each closed its own viewer child.

| Surface | Action | Repeats (ms) | Samples with window | Rule | Verdict |
|---|---|---|---|---|---|
| results | tabs | 0 ×5 | 1758 | 0 ms, ≥ 500 | PASS |
| results | theme | 0 ×5 | 19973 | 0 ms, ≥ 500 | PASS |
| results | resize | 20.7, 18.2, 17.6, 28.5, 17.7 | — | median ≤ 50, max ≤ 80 | PASS (18.2 / 28.5) |
| run | tabs | 0 ×5 | 1753 | 0 ms, ≥ 500 | PASS |
| run | theme | 0 ×5 | 20965 | 0 ms, ≥ 500 | PASS |
| run | resize | 42.5, 43.3, 43.1, 44.6, 43.8 | — | median ≤ 50, max ≤ 80 | PASS (43.3 / 44.6) |
| setup | chaintab | 0 ×5 | 1761 | 0 ms, ≥ 500 | PASS |
| setup | resize | 29.4, 26.2, 28.5, 32.9, 28.3 | — | median ≤ 50, max ≤ 80 | PASS (28.5 / 32.9) |

No threshold changed after measuring; no A/B needed.
`docs/qa/2026-10-03-gui-polish/viewer_measure_gui11.json`.

### Final matrix

Offscreen, one at a time (`matrix.sh`, scratchpad), all exit 0:
- all 35 `test_ui_*` suites: `test_ui_chain` (114), `test_ui_chain_screen` (220),
  `test_ui_frame` (86), `test_ui_parity` (41), `test_ui_results` (130),
  `test_ui_results_screen` (213), `test_ui_run_screen` (214), `test_ui_setup_strip`
  (129), `test_ui_setup_tree` (260), `test_ui_three_surfaces` (35),
  `test_ui_run_browser` (48), `test_ui_live_gauges` (20), `test_ui_no_mpl_pyplot`
  (19), `test_ui_fieldform_viewport` (11), and the rest PASS;
- the Qt char goldens, all unedited: `test_ui_char_case_form`,
  `test_ui_char_chain_wiring`, `test_ui_char_hd13_run`,
  `test_ui_char_results_exports`, `test_ui_char_results_meta`,
  `test_ui_char_write_failure`;
- `test_case_validate`; the 12 `test_char_*`; `test_worker_stage_progress`;
- the Tk suites the 11b shared-module change calls for: `test_gui_char_write_failure`
  and `test_gui_char_case_form` (scratch settings).

Real platform, one at a time: `_e2e_ui_chain_screen.py` PASS (23),
`_e2e_ui_run_finish.py` PASS (19, `windows`), `_e2e_ui_results.py` PASS (31),
`_e2e_hd13_gui.py` PASS.

App start: `ui.app.main()` with throwaway settings, real platform: the window
Win32-visible on 01 Setup, `main` returned 0.

**Last:** `test_regression.py` PASS, byte-identical (seven files identical,
`b2_profile.npz` arrays equal, no baseline file dirty); then
`test_ui_char_chain_wiring.py` PASS, unedited.

### Frozen paths and the never-stage list

- `git diff 4d0fb1c..HEAD` over `blastlab/gui`, `core`, `models`, `output`,
  `viz3d`, `solvers`, `services`, `ui/view3d_host.py`, `ui/run_controller.py`,
  `ui/viewer_link.py`, the baselines, the fixtures and `char_golden/`: **empty**.
- `git diff 116ea96..HEAD` over the same: only the plan's exceptions
  (`solvers/worker.py` one line, `services/validation.py`, `ui_case_form.json`'s
  approved entries).
- None of the seven never-stage paths is in any 11d commit (all staged by explicit
  path). `git worktree list` shows only the main tree (the A/B worktree was
  removed; its stale `.git/worktrees` record was deleted on the second try, F20's
  lesson).

### T22 acceptance

1. PASS. K02 on the real platform: 0 clipped, 0 outside, both modes, both solver
   modes, tool-button elision included.
2. PASS. K03 luma ≥ 140 (196.4-246.0).
3. PASS. B06 every check.
4. PASS. The diff has one `new` line, with its disposition (F49).
5. PASS. R10 on every surface.
6. PARTIAL. Every GUI-11 item has a line here; (f) F17 is blocked (T19 above).
7. PASS. `docs/gui-redesign-decisions.md` has D200-D215 (D214 records T19 as
   blocked), F39-F49, and Outcomes on F12, F16, F17, F28, F36 and F38.

---

## GUI-11 items (a)-(g) and the in-scope (h), with evidence

| Item | State | Evidence |
|---|---|---|
| (a) D191 `●` when elided | PASS | T16 above |
| (a) F38 harness clip check | PASS | T22 harness fixes, K02 `--window` clean |
| (a) F36 harness F02 / F10 | PASS (code); WSL step office machine | T22 |
| (b) D192 dark tree hover | PASS | T17 |
| (c) F28 | PASS (11b) | D209 / D217, `test_worker_stage_progress` green |
| (d) F12 0-D run flow | PASS (11a) | D206, `test_ui_run_screen` R11 green |
| (e) F16 hidden AMR values | PASS (11c) | D211 / D223, `test_ui_char_case_form` green |
| (f) F17 on-screen 1D title | **BLOCKED** | T19: needs a golden re-record |
| (g) P2-18 / P2-24 (Qt halves) | PASS (11a) | D205-D208, `test_ui_frame` F12 / F13 green |
| (h) UXR-1, UXR-4, UXR-5, UXR-7, UXR-8 | PASS (11a) | `test_ui_close_guard`, `test_ui_crashlog`, `test_ui_frame` green |
| (h) UXR-2, QA S2-1 | PASS (11b) | `test_case_validate`, `test_ui_chain_screen` green |
| (h) UXR-3, -9, -11, -12, -15 | PASS (11c) | `test_ui_setup_form` / `_tree` / `_strip`, `test_ui_chain_screen` green |
| (h) QA S3-1, S3-2, S3-7 | PASS | T18 |
| (h) UXR-10 small half | PASS | T20 |
| (h) QA S3-6 text half | PASS | T21 |
| session: F43, F40, F46 | PASS | above |

## Changed committed assertions

1. `test_ui_theme` T6: dark `num_dim` on the tree hover has a 4.0 floor instead
   of 4.5 (owner-approved, D192 / D212); every other role and all of light keep
   4.5. The check prints the hover-to-panel ratio.
2. `test_ui_results_screen` S2c: the two `Mesh` pins read `{:.3g}` instead of
   `{:g}` (UXR-10 amends D90; a layout string).
3. `_qa_ui_harness.py` F02 / F10: expect the VTK export disabled with its reason on
   a released-scratch foam result (F36); `_clipped_labels` sees tool-button
   elision (F38).

Everything else is new checks. No behaviour or number assertion was weakened, and
no golden was edited.

## All files touched in 11d

- `blastlab/ui/`: `topbar.py`, `theme.py`, `run_panel.py`, `results_method.py`,
  `results_panel.py`, `app.py`, `dialogs.py`, `fieldform.py`
  (`results_fields.py` and `_e2e_ui_results.py` were changed by T19 and restored by
  its revert)
- `blastlab/tests/`: `test_ui_frame.py`, `test_ui_theme.py`,
  `test_ui_run_screen.py`, `test_ui_results_screen.py`, `test_ui_setup_form.py`,
  `_qa_ui_harness.py`
- `docs/gui-redesign-decisions.md`
- `docs/qa/2026-10-03-gui-polish/`: `measurements.md`, `viewer_measure_gui11.json`,
  `findings-diff-11d.txt`, `gui11-dark-tree-hover.png`, `gui11-run-pmax-1280.png`,
  `gui11-run-chain-1100x720.png`, `gui11-run-chain-1100x720-toggled.png`,
  `gui11-results-3d-placeholder.png`, `gui11-dialog-details.png`
- this report

## GUI screens touched (for QA)

- **Top bar:** `●` (tooltip) whenever the case name is elided; `● unsaved`
  otherwise.
- **01 Setup tree (dark):** the hover is visible.
- **01 Setup / Chain 2D point lists:** a red refusal re-worded after a planar ↔
  axisymmetric toggle.
- **02 Run:** the strip goes onto two rows below 1420 px (so at the default 1280 ×
  840); the live view keeps 200 px; at 1100 × 720 after a chain with its banner the
  Log dock steps aside until there is room.
- **03 Results:** method card (`kg/m`, `cell 12.4 mm`, the miller caveat, Ended on
  two lines); the 3D placeholder text.
- **Dialogs:** `Show Details…` with the whole path when a path was shortened.
- **Windows notification:** `Highest peak: G<entered n>`.

## Numerical changes

None. No solver value, solver default, case key, file format, export byte or
hand-off file changed; `test_regression` is byte-identical. `kg/m` on a planar
charge is a unit label for the same number; `cell 12.4 mm` is a display rounding.

## D / F rows

- New D-rows: **D212** (T17), **D213** (T18), **D214** (T19, blocked), **D215**
  (T21) — the plan's reserved numbers; **D225** (T16), **D226** (T20), **D227**
  (F43), **D228** (F40), **D229** (F46) — after D224.
- New F-rows: **F48** (K02's run-banner evidence now names the Progress time line,
  QA S4-e, predates GUI-11), **F49** (the order-dependent `Tight layout` warning,
  predates GUI-11).
- Outcomes added: F16 (11c), F17 (blocked), F36, F38, F40, F43, F46. F12 and F28
  already had theirs.

## Suspected engineering issues noticed, not changed

None numerical. The afterburn caveat (T20) restates CLAUDE.md §7 (only the TNT
row of `materials.py` is calibrated against data); no coefficient was touched.

## Open questions for the owner

1. **T19 / F17:** approve re-recording the five on-screen `title` entries (and the
   `fields` hash) of `char_golden/ui_results_meta.json`? Then the reverted commit
   comes back as is.
2. **D213 trade-off:** at the 1100 × 720 minimum, after a chain with its banner,
   the Log dock steps aside so the live view keeps 200 px. Keep, or prefer a
   shorter view (186 px) with the dock's tab strip visible?
3. **D213, the default window:** at 1280 × 840 the Run strip now uses two rows (a
   one-row P MAX tile cannot hold `8.888e+05 kPa` below 1420 px). Keep, or narrow
   the Progress tile's stretch so one row holds from about 1280 px?

## Left undone

- T19 (F17): blocked on the golden, above.
- F36's Keep-all-fields VTK step and F02 / F10 in WSL: office machine.
- F42, F44, F45: waiting for the owner, as instructed.
