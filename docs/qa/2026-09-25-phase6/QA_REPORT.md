# blastlab QA - phase 6 - 2026-09-25

Post-phase QA after refactor Phase 6 (`docs/ARCHITECTURE_REVIEW.md` section 5,
finding F7; commits `f13c89d` "test(phase 6): pin what both GUIs' Results
exports write", `b980def` "refactor(phase 6): services/exports.py, shared by
both GUIs", `473353d` "simplify(phase 6): services/exports.py ui/exports.py"
on branch `arch-p6-exports`). The Results-tab export orchestration
(`KINDS`, `DIR_KINDS`, `name_prefix`, `summary_rows`, `can`, `why_not`,
`run_export` and its helpers) moved into `blastlab/services/exports.py`,
toolkit-free, shared by both GUIs. **Files touched by the phase:
`blastlab/ui/exports.py`** (Qt - keeps `pick_target`/`export`, re-exports
the moved names) **and `blastlab/gui/results_panel.py`** (Tk - `_export`
keeps its dialogs and worker thread, calls `services.exports.run_export`
for the writing). No application code was edited during this QA session.
Compared throughout against `docs/qa/2026-09-24-baseline/QA_REPORT.md`,
`docs/qa/2026-09-25-phase5a/QA_REPORT.md` and
`docs/qa/2026-09-25-phase5b/QA_REPORT.md`.

## 1. Environment

| | |
|---|---|
| Python | 3.12.10 (Microsoft Store build), on PATH as `python` |
| Qt | PySide6 (offscreen, `QT_QPA_FONTDIR` set for readable text, for the export walkthrough and the harness; real platform, `QT_QPA_PLATFORM` unset, ground truth via `PrintWindow(PW_RENDERFULLCONTENT)` through ctypes, for the startup sanity shot) |
| Tk | CustomTkinter, real desktop window (Tk has no offscreen mode); screenshots via `PIL.ImageGrab` falling back to the same `PrintWindow` ground truth, reusing `_qa_gui_harness.frame_bounds`/`print_window`/`user32` |
| Pillow | present; both capture paths worked in this session |
| ffmpeg | on PATH (winget `Gyan.FFmpeg`) - the `gif` export therefore actually wrote `.mp4` in every run below, exercising the real ffmpeg writer, not the `.gif` fallback |
| OS | Windows 11 Enterprise 10.0.26200 |
| Launch | `blastlab.ui.app.MainWindow` and `blastlab.gui.app.App` built directly in throwaway harness scripts under the session scratchpad (`...\scratchpad\qa-p6\`), plus `blastlab/tests/_qa_ui_harness.py` and `_qa_gui_harness.py` run as subprocesses with a fresh, explicit `--out` each (never `--resume`) |
| Settings guard | every process set `BLASTLAB_SETTINGS` to a private file **before** any `blastlab` import and asserted `settings.load()['auto_cleanup'] is False` before building a window (printed and verified in every script's output). The two harnesses write their own scratch `settings.json` with `auto_cleanup: false` per their own documented startup, verified by inspection of their `main()`. `env.auto_cleanup(...)` was never called anywhere. |
| WSL | not touched: no WSL solve, no blastFoam run. `_qa_ui_harness`/`_qa_gui_harness` were invoked with `--solver native`; VTK was exercised only on its refusal path (native results have no `case_dir`) |
| Python processes | confirmed none left running at the end of the session (`Get-Process -Name python3.12` empty) |

**Own harness scripts** (all under the given scratchpad path, none elsewhere):
`qt_live_export_qa.py`, `tk_live_export_qa.py`, `qt_sweep.py`,
`compare_qt_tk.py`. All four ran the settings guard before any `blastlab`
import and closed their window (`win.close()` / `root.destroy()`) before
exiting.

**One self-correction worth recording:** the first `qt_live_export_qa.py`
run (offscreen, no `QT_QPA_FONTDIR`) produced screenshots with every label
rendered as empty glyph boxes - the documented "offscreen has no font
database" effect (`blastlab/ui/testing.py`'s own `ensure_qapp` sets
`QT_QPA_FONTDIR` for exactly this reason; my first script didn't). This
was a gap in my own throwaway script, not an app defect - the harness's own
screenshots (which do set the font dir) and the real-platform screenshot
were readable throughout. Fixed and reran; see `screenshots_qt/`.

## 2. Result table

| # | Item | Result | Evidence |
|---|---|---|---|
| 1 | Qt startup (offscreen) | PASS | `screenshots_qt/01_start.png` |
| 1b | Qt startup (real platform, PrintWindow ground truth) | PASS | `screenshots_qt/42_realplatform_start.png` - readable, no traceback |
| 1c | Tk startup (real window) | PASS | `screenshots_tk/01_start.png` |
| 2 | Setup form round trip (Qt, sanity only - Setup form is untouched by this phase; phase 5a/5b did the deep QA) | PASS | `qt_sweep_report.json`: `case1d_a.json`/`case1d_c.json` byte-identical after a detour through a 2D case |
| 3 | Happy path: native 1D run (both GUIs) | PASS | `screenshots_qt/02-04`, `screenshots_tk/02-04`; 1.3-2.5 s wall (Qt), 2.5 s wall (Tk) |
| 4 | Happy path: native 2D run, planar, obstacle, 2 gauges, 60 recorded frames (both GUIs) | PASS | `screenshots_qt/05-07`, `screenshots_tk/05-07`; 25-45 s wall depending on background CPU load |
| 5 | Every export button (`profile`, `gif`, `vtk`, `summary`, `tsv`, `fieldcsv`, `report`, `pngs`) x 2 results (1D, 2D) x 2 GUIs - enabled/disabled state, tooltip, real click, file(s) written | PASS - 32/32 | `qt_live_export_report.json`, `tk_live_export_report.json`; files under `exports/qt/`, `exports/tk/` |
| 6 | VTK button, native result (no blastFoam case dir) | PASS - correctly disabled both GUIs | tooltip `'Only a blastFoam run whose case directory still exists can be written as VTK.'` in both; never clicked (disabled) |
| 7 | Export with no result selected | PASS - all 8 buttons disabled, `'Select a result first.'` tooltip, both GUIs | `screenshots_qt/12_results_no_selection.png`; `no_selection_buttons` in both JSON reports |
| 8 | `os.startfile` called for `report` (and would be for `vtk`) | PASS | both `opened_by_os_startfile` lists contain the two report HTML paths, one per dim |
| 9 | Qt vs Tk export comparison, same case, byte/array/pixel level | PASS - 32/32 common files identical | `qt_vs_tk_export_compare.json`; see §5 |
| 10 | Displayed gauge-summary table vs. exported summary CSV, and Qt vs Tk | PASS - string-identical | see §6 |
| 11 | Close terminates cleanly | PASS | every script closed its window; no leftover `python3.12` process |
| 12 | `test_char_exports.py` (pinned Qt-path characterisation, `exports_qt.json`/`exports_can.json`) | PASS - 3/3 | §7 |
| 13 | `test_gui_char_exports.py` (pinned Tk-path characterisation, `exports_tk.json`) | PASS - 1/1 | §7 |
| 14 | `_qa_ui_harness.py` D01,D02,D04,E01-E09 (Qt, native, fresh `--out`) | PASS - 12/12 done, exit 0, 1 finding (not new - see §4) | §8 |
| 15 | `_qa_gui_harness.py` D01,D02,D04,E01-E09 (Tk, native, fresh `--out`) | PASS - 12/12 done, exit 0, 0 findings | §8 |
| 16 | Phase-6-listed verification suite (`test_ui_results.py`, `test_report.py`, `test_gauge_summary.py`, `test_anim_scale.py`, `test_gui_title_preview1d.py`, `test_ui_no_vtk_in_main.py`, `test_ui_no_mpl_pyplot.py`, `test_gui_results_fields.py`, `test_gui_results_anim.py`, `test_gui_gauge_summary.py`) | PASS - 10/10 | §7 |
| 17 | `test_regression.py` | PASS - 8/8 | §7 |

**No FAILs anywhere in this session.**

## 3. Failures

None. No crash, traceback, incorrect displayed number, or wrong file content
was found anywhere in this run (my own scripted plan, both harnesses, the
pinned characterisation tests, the phase-6 verification suite, or
`test_regression.py`).

## 4. The one harness finding - not new

`_qa_ui_harness.py`'s D02 (native 2D run) recorded one S1 finding: **"the 2D
solver announced itself" - failed.** The check is `qa.wait_log('2D Blast
Solver', 40)` after clicking Run, polling up to 40 s for the solver's own
banner line. It did not appear within 40 s this run either (as in phase 5a's
same D02 finding); the run itself finished correctly afterwards and every
other D02/E-group check passed. **This is not a new failure**: it is the
identical check, identical text, and (per phase 5a's report §10) an already
flagged, not-attributed-to-any-phase-diff timing sensitivity of
`wait_log`'s fixed 40 s window under this machine's variable background
load - `case_form.py`/`gui/results_panel.py`/`ui/exports.py`/
`services/exports.py` play no part in the run/log pipeline the check reads.
Reproduced in phase 5a (2026-09-25) and again here; not reproduced in the
2026-09-24 baseline (which didn't include a D02 in its run set the same way)
- consistent with an environment-timing flake, not a regression from this
phase's diff.

`_qa_gui_harness.py`'s D02 recorded the Tk twin of the same symptom as a
`NOTE`, not a scored finding (`wait_log TIMEOUT for '2D Blast Solver'`) -
same cause, same non-scored outcome as phase 5a/5b.

## 5. Qt vs Tk export comparison

Both GUIs ran the **identical** native cases (`Case1D(radius_m=2.0,
charge_kg=1.0, cell_size_m=0.005, gauge_radii=[0.5, 1.0], n_snapshots=3)` and
`Case2D(geometry='planar', Lx=2.4, Ly=1.6, cell_size_m=0.04, charge=20.0,
center=(0.6, 0.0), obstacles=[(1.2, 1.6, 0.0, 0.6)], gauges=[(0.3, 0.8),
(1.4, 0.3)], n_snapshots=3, record_frames=60)`, the deterministic native
solver - same parameters `_qa_gui_harness.cases()['N1D']`/`['N2D']` use),
then every enabled export button was clicked for real in both GUIs and the
files diffed:

| File kind | Method | Result |
|---|---|---|
| `.txt`/`.csv` (profile, TSV, summary, field CSVs) | sha256 | **byte-identical**, 24/24 files |
| `.html` (report) | sha256 after masking the timestamp (both reports write the same date/time-of-run text, not literally identical machinery, but content-identical up to that) | **identical**, 2/2 |
| `.png` (PNGs export - full snapshot grid) | pixel dimensions | **identical size**, 7/7 files (rendering bytes not pinned, matching the project's own pinning discipline in `test_char_exports.py`) |
| `.mp4` (animation, via real ffmpeg since ffmpeg is on PATH) | byte count | **identical**, 50,415 bytes both, 1/1 |

**32/32 common files, 0 mismatches, 0 files present in only one GUI's
export tree.** Full detail in `qt_vs_tk_export_compare.json`. This
independently confirms, by actually clicking the buttons in two live running
apps rather than only calling `run_export` directly, what the pinned
`test_char_exports.py`/`test_gui_char_exports.py` goldens already assert:
the Tk and Qt exports agree on every file this phase's diff could have
touched.

## 6. Numbers check - displayed summary vs. exported CSV vs. the other GUI

1D (native, `Run 1 - 1D` / `QA native1d`):

| Gauge | Peak [kPa] | Arrival [ms] | t peak [ms] | Pos. phase [ms] | Pos. imp [Pa·s] | Net imp [Pa·s] | Phase ended |
|---|---|---|---|---|---|---|---|
| G1 r=0.502 m | 3412.8 | 0.152 | 0.165 | 0.078 | 138.12 | 31.19 | yes |
| G2 r=0.998 m | 934.0 | 0.485 | 0.511 | 0.692 | 137.36 | 123.43 | yes |

2D (native, planar, `Run 2 - 2D` / `QA native2d`):

| Gauge | Peak [kPa] | Arrival [ms] | t peak [ms] | Pos. phase [ms] | Pos. imp [Pa·s] | Net imp [Pa·s] | Phase ended |
|---|---|---|---|---|---|---|---|
| G1 (0.300, 0.800) | 7759.4 | 0.211 | 0.237 | 0.255 | 619.31 | 619.32 | no |

Every one of these 14 values is **string-identical** across all four sources
checked for each case: the Qt Results table, the Tk Results table, the Qt
`summary` CSV export, and the Tk `summary` CSV export (`gauges_1d_summary.csv`,
`gauges_2d_summary.csv` under `exports/qt/` and `exports/tk/`, and
`qt_live_export_report.json`/`tk_live_export_report.json`'s own
`displayed_summary_table`). Peak, arrival AND impulse all checked, never
peak alone, per CLAUDE.md's measurement discipline note; net impulse is the
whole-record signed overpressure integral (negative phase included, hence
"no" on 2D's phase-ended column - the run's 0.466 ms window is shorter than
the positive phase), as documented.

## 7. Existing pinned/verification test suites

- **`test_char_exports.py`** (`--update` was **not** used - the harness
  blocked one accidental attempt at it, see §9): `test_can_why_not`,
  `test_qt_exports`, `test_ui_exports_reexports_services` all **PASS**
  against the committed `char_golden/exports_can.json`/`exports_qt.json`.
- **`test_gui_char_exports.py`**: `test_gui_exports` **PASS** against
  `char_golden/exports_tk.json`.
- **Phase-6-listed verification suite** (`docs/ARCHITECTURE_REVIEW.md`'s own
  "Verification" line for this phase): `test_ui_results.py` (124 checks),
  `test_report.py`, `test_gauge_summary.py`, `test_anim_scale.py` (68
  checks), `test_gui_title_preview1d.py`, `test_ui_no_vtk_in_main.py`,
  `test_ui_no_mpl_pyplot.py` (18 checks), `test_gui_results_fields.py`,
  `test_gui_results_anim.py`, `test_gui_gauge_summary.py` - **all PASS**,
  run individually as scripts (`python test_x.py`; these are not
  pytest-style files - `pytest` on them collects 0 tests, confirmed).
- **`test_regression.py`**: **PASS - 8/8**, byte-identical/array-equal to
  the frozen baseline (`b1_gauges.txt`, `b1_profile.txt`, `b2_gauges.txt`
  byte-identical; `b2_profile.npz` arrays equal; `b2r_gauges.txt`,
  `b3_gauges.txt`, `b3r_gauges.txt`, `transcript.txt` byte-identical) -
  identical to baseline's, phase 5a's and phase 5b's own comparisons. This
  suite exercises the native solvers directly and never touches either
  Results panel, so an unchanged result was expected; run because the task
  asked for it.

## 8. `_qa_ui_harness.py` / `_qa_gui_harness.py` - D+E groups

Both run with an explicit fresh `--out` (never `--resume`), `--solver
native`, scenarios `D01,D02,D04,E01,E02,E03,E04,E05,E06,E07,E08,E09` (D01/
D02/D04 seed the 1D/2D/3D results the E group's export scenarios read; F00-
F11, the blastFoam/WSL scenarios, were deliberately never selected, per the
no-WSL-solve constraint for this session):

```
python -u _qa_ui_harness.py  --out ~/blastlab_qa/20260925-phase6-qt --only D,E \
    --scenario D01,D02,D04,E01..E09 --budget 3600 --solver native
python -u _qa_gui_harness.py --out ~/blastlab_qa/20260925-phase6-tk \
    --scenario D01,D02,D04,E01..E09 --budget 3600 --solver native
```

- **Qt: 12/12 `done`, exit 0.** One finding, `D02` S1 (§4, not new). D04
  (native 3D, offscreen) took 706.8 s wall this run - about 2x the baseline's
  own D04 timings (525-777 s across three earlier sessions) - fully
  attributable to this session's own CPU contention (my Tk harness and
  Qt export script running at the same time for the first ~10 minutes of
  D04's solve; CPU accounting confirmed the process stayed near 100 % of one
  core throughout, i.e. genuinely computing, not stalled). Once the Tk
  harness finished, the Qt harness's E group ran at its normal pace (60-
  150 s per scenario, matching prior sessions). E06 (embedded 3D viewer)
  logged one pre-existing VTK/pyvista console warning, `vtkLookupTable
  (...): Bad table range for log scale: [-5621.37, 254182]` - a log-scale
  colour-bar warning on a field whose range crosses zero, in the 3D viewer
  code (`viz3d/`), entirely outside this phase's diff (`ui/exports.py`,
  `services/exports.py`); not scored as a finding by the harness, and the
  scenario's own checks all passed.
- **Tk: 12/12 `done`, exit 0, 0 findings** (`findings.jsonl` was not even
  created - empty run). D02 logged the same non-scored `wait_log TIMEOUT`
  note as phase 5a/5b (§4).
- Neither harness's `checkpoint.json` shows any `foreign_pids`; no WSL/
  blastFoam process interfered. Every E-group export scenario (E01 profile,
  E03 summary/TSV/fieldcsv/report, E07 every button on a 2D AND a 3D result)
  wrote real files under its own `exports/` dir and the harness's own
  `qa.check(os.path.exists(...))` assertions passed for every one.

## 9. Note on a blocked destructive command (self-correction, no damage)

While independently re-verifying the pinned characterisation test, I typed
`python test_char_exports.py --update` out of habit (to re-run it, not
intending to touch the golden) - the environment's own classifier correctly
blocked it as an irreversible local write (`--update` overwrites
`char_golden/exports_qt.json`/`exports_can.json`). It never ran.
`git status` immediately after confirms nothing under `blastlab/tests/
char_golden/` is modified - the only untracked path in the whole repo is
this report's own `docs/qa/2026-09-25-phase6/`. No golden file was ever
touched; recorded here for transparency, not because anything happened.

## 10. Visual findings (work, but worth noting - none are phase-6 regressions)

- **Export button tooltips differ in ONE respect between the two GUIs, and
  it predates this phase.** Qt's `_sync_export_buttons`
  (`ui/results_panel.py`) always sets a tooltip: `EXPORT_HELP[kind]` when
  enabled, `why_not(kind, ent)` when disabled - so every Qt export button
  has hover text. Tk's `_sync_export_buttons` (`gui/results_panel.py`, line
  ~502) sets `''` when enabled and only shows text (`why[kind]`) when
  disabled. Confirmed directly in this session's own JSON reports: Qt's
  `1d/profile.tooltip` is `'Save the final state for a later stage to start
  from.'`; Tk's is `''` for the same enabled button. Both files
  (`ui/results_panel.py`'s `_sync_export_buttons`,
  `gui/results_panel.py`'s `_sync_export_buttons`) are untouched by phase 6
  (only `_export`'s file-writing branches moved) - pre-existing, not a
  regression.
- **The `_open()` "could not open" wording is now unified**, confirmed by
  reading `services/exports.py:236-242` (the single `_open` both GUIs now
  call through `run_export`): `log(f'(could not open {path}: {exc})')` -
  exactly the wording the task's "known small behaviour change" describes.
  Not empirically triggered this session (no export's `os.startfile`/folder
  call failed on this machine - both GUIs' `opened_by_os_startfile` lists
  show the report HTML being "opened" successfully every time, since
  `os.startfile` was mocked to a recorder that never raises, matching the
  pinned tests' own approach) - confirmed by source instead. `gui/
  results_panel.py` no longer has any local open-and-report-failure code of
  its own; everything routes through the one shared function.
- **Qt's offscreen platform needs `QT_QPA_FONTDIR` for readable
  screenshots** - not a product issue (see §1's self-correction), but worth
  recording again for the next scripted QA session in this repo, since it
  has now bitten two different sessions' throwaway scripts (this one, and
  the font-boxes note would have applied to any earlier session's own
  screenshot code that didn't reuse `ui/testing.ensure_qapp`).
- Nothing clipped, overlapping, or unreadable in any of the 26 screenshots
  from my own scripts (13 Qt + 12 Tk + 1 shared count) or the ~190 from the
  two harness runs (sampled the E03/E07 export-scenario contact sheets and
  spot-checked others) - export buttons, tooltips, the gauge summary table,
  and the field/gauges/animation views all render cleanly at 1280x840 in
  both GUIs, native mode (VTK button correctly absent/disabled, matching
  the documented "hidden, never greyed" per-mode rule plus the per-result
  `can()`/`why_not()` gating on top of it).

## 11. Suspected engineering errors (not investigated, per task scope)

Already on record in `docs/ENGINEERING_QUESTIONS.md` under "2026-09-25 -
`/refactor` phase 6" (added by this branch's own `122172d`, read but not
investigated): **`output/report.py`'s `kb_rows` compares gauge peaks against
the free-air Kingery-Bulmash table even for an axisymmetric case with a
reflecting ground and no obstacles** (a height-of-burst case), which is a
reflected/Mach-stem peak, not a free-air one, so the printed KB ratio reads
high. Not re-derived or investigated in this QA session (native-only, no
gauge in either of this session's own cases sits in that specific geometry);
flagged only because the HTML `report` export this session exercised is the
exact code path that prints it. Nothing else new was noticed.

## 12. Cleanup

Every window/QApplication/Tk root built by my own scripts was closed
(`win.close()`/`root.destroy()`) before its script exited; both harnesses
tear down their own window in their `finally` blocks. No leftover
`python3.12` process after the session (`Get-Process -Name python3.12`
empty). `env.auto_cleanup(...)` was never called (every script's settings
guard was verified `False` before building a window). No file under
`~\Desktop` was touched. Helper scripts lived only under the scratchpad path
given in the task (`...\scratchpad\qa-p6\`: `qt_live_export_qa.py`,
`tk_live_export_qa.py`, `qt_sweep.py`, `compare_qt_tk.py`). No `blastlab`
application file was edited; no git command that changes anything was run
(only `git show --stat`, `git status` - both read-only; one `--update` test
invocation was blocked before it could run, §9). The two harnesses' own run
directories (`~/blastlab_qa/20260925-phase6-qt`, `.../phase6-tk`) were left
in place, as every earlier session's were.
