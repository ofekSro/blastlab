# GUI-11e QA - render-and-drive, real platform

Worktree `D:\blastlab_wt\gui-11e`, branch `gui-11e`, HEAD `d49cc4e`. Covers the
five screens named in the QA request, cross-checked against the batch's own
`docs/batches/2026-10-04-gui-11e.verifyA.md` / `.verifyB.md`.

## 1. Environment

- Python 3.12.10 (Microsoft Store build).
- PySide6 6.11.2; `customtkinter` for the Tk GUI; Pillow 12.2.0 (screenshots).
- Windows 10 Enterprise 10.0.19045, real desktop (`QT_QPA_PLATFORM` unset for
  Qt; tkinter has no offscreen mode).
- Launch: a throwaway harness script (not committed; ran from
  `D:\blastlab_tmp\`) that imports `blastlab.ui.app.MainWindow` /
  `blastlab.gui.app.App` directly, uses `blastlab.ui.testing.private_settings()`
  / `use_model()` (throwaway `BLASTLAB_SETTINGS`, `auto_cleanup: false`,
  private runs folder under `D:\blastlab_tmp\...\runs`), and drives real
  `QTest`-free Qt (`win._run_single()`, `app.processEvents()` pumps) / real Tk
  (`root.update()` pumps) calls. Native solver only, no WSL.
- `TEMP`/`TMP` pointed at `D:\blastlab_tmp` for every launch. C: free space
  was checked (exact bytes via `GetDiskFreeSpaceExW`, not the rounded `df -h`
  figure) before every launch; the machine is shared and swung between
  2.6 GB and 4.3 GB during this session (consistent with the batch's own
  verifyA note). One run was stopped mid-script when C: read 2.97e9 bytes
  (below the 3e9 floor) and resumed once it recovered; no app code or other
  worktree was touched. No stray python/pythonw process remained after any
  run (checked via `Get-Process`).
- Test case: a native 2D planar case (20 kg/m TNT, 2.4 x 1.6 m, obstacle
  `Wall 1` at x 1.2-1.6, y 0.0-0.6) with 5 entered gauges: G1 (0.3,0.8)
  survives, G2 (1.4,0.3) strictly inside the obstacle (dropped), G3 (1.2,0.3)
  on the obstacle's left face (dropped), G4 (1.8,0.8) and G5 (2.0,1.2) survive
  after the two drops - built to exercise F42's entered-number pairing, not
  plain re-indexing.

## 2. Result table

| # | Item | Verdict | Screenshots |
|---|---|---|---|
| 1 | Native 2D, obstacle-dropped gauges: Gauges tooltip, Summary .csv, HTML report | **PASS** | `09_results_gauges_tab.png`, `10_gauges_summary.csv`, `11_gauges_report.html`, `04_run_strip_1280x840_finished.png` |
| 2a | Setup warning text (inside / on-face) | **PASS** | `01_setup_warnings.png` |
| 2b | Chain 2D stage warning text | **PARTIAL** (see Finding 1) | `02_chain_2d_stage_warnings.png` |
| 3 | Results 1D Field short title, dark/light, 1100x720 / 1280x840 | **PASS** | `12_field_1d_title_{1100x720,1280x840}_{dark,light}.png` |
| 4 | 02 Run strip rows (1280x840/1600x1000 one row, 1100x720 two rows), dark+light | **PASS** | `03..08_run_strip_*.png` |
| 5 | Tk Results summary table after a dropped gauge | **PASS** | `13_tk_results_summary_table.png` |
| - | New finding: exported/exported-figure gauge-trace titles not renumbered | **FAIL (new defect, not in this batch's diff)** | `14_report_gauge_trace_titles_mismatch.png`, `13_tk_results_summary_table.png` |

28 harness checks ran for items 1-4 (Qt), 7 for item 5 (Tk); every check is
backed by a value read from the live widget or the real exported file, listed
below. 25/28 + 7/7 passed outright; the 3 Qt "fails" are the Chain nuance in
Finding 1, already explained, not a blind assertion failure.

## 3. Findings

### Finding 1 (low, Chain screen only) - the Chain 2D stage's live warnings do not reproduce the "on an obstacle face" line that Setup shows for the identical case

**Repro:** Setup screen, the test case above -> Checks tab shows both
`Gauge (1.4, 0.3) inside an obstacle - will be dropped` and
`Gauge (1.2, 0.3) on an obstacle face - will be dropped` (`01_setup_warnings.png`,
confirmed). Chain screen, route `1D -> 2D`, stage 2 set to the *same* case
object -> its Checks list shows only the "inside an obstacle" line; the
"on an obstacle face" line for the same (1.2, 0.3) gauge does not appear
(`02_chain_2d_stage_warnings.png`). The same happens on route `2D -> 3D` with
an axisymmetric twin of the case (tried to dodge the unrelated "fed stage"
wiring) - still only "inside", not "face".

**Expected vs actual:** expected both lines, as on Setup, since F44's docstring
says the native drop rule depends only on the obstacle geometry and the
solver's own auto-refine `dx` for *that* case. Actual: the Chain-wired stage's
effective `dx` evidently differs from Setup's standalone `dx` for the identical
`cell_size_m`/charge/obstacle (Setup: refined to 0.0125 m; Chain route 1D->2D
stage: refined to 0.02862 m per one run's log), which moves gauge (1.2, 0.3)
off the face-tie that trips the "face" wording.

**Likely cause / where:** `services/validation._gauge_drop_rule`
(`blastlab/services/validation.py` ~1589-1654) computes `dx` from the case's
own `charge_refine`/auto-refine path; a Chain-wired stage reaches
`validate_case` through `ui/chain_route.stage_checks()` after `wire()` has
set up the hand-off (`profile_file_in` for a fed stage, or a different
`center`/`init_mode` for a feeding stage), which plausibly changes the
auto-refine `dx` relative to a plain Setup case with the same
`cell_size_m`. This matches the GUI-11e A2 report's own "Engineering question
2": the on-face classification is already flagged as "fragile across grid
changes" - this QA run reproduces that fragility concretely as a
cross-screen (Setup vs Chain) discrepancy for the one case that should be
least ambiguous (hand-picked exactly on a face).

**Severity:** low. The "inside an obstacle" warning (the more serious of the
two - a gauge the user placed is silently useless) is correctly live on both
screens. Only the softer "on a face" wording is inconsistent, and only
between Setup and Chain, never within a single screen.

### Finding 2 (medium, new - not part of this batch's diff) - exported/exported-figure gauge-trace subplot titles use the solver's survivor index, not the entered gauge number; mismatched against the table in the very same report

**Repro:** run the test case above (2 gauges dropped, 3 survive), then either
(a) Results -> Export -> Report (.html) in the Qt GUI, or (b) open the Tk
GUI's Results -> Gauges tab directly after the run. In both, the gauge-trace
figure titles each panel "Gauge 1 (0.30, 0.80) m", "Gauge 2 (1.80, 0.80) m",
"Gauge 3 (2.00, 1.20) m" - a plain 1-based index over the 3 *surviving*
points. The per-gauge summary table immediately below/beside the same figure
(in the same HTML report, or the same Tk screen) correctly labels the three
rows `G1 (0.300, 0.800)`, `G4 (1.800, 0.800)`, `G5 (2.000, 1.200)` - the
entered numbers (F42/A1 of this batch). The second and third trace panels are
*the same traces* as table rows G4 and G5, but the figure calls them "Gauge 2"
and "Gauge 3".

**Evidence:** `14_report_gauge_trace_titles_mismatch.png` (the exact figure
extracted from the Qt-generated `11_gauges_report.html`, base64-decoded, byte
for byte what the report embeds) and `13_tk_results_summary_table.png` (the
same mismatch live in the Tk app: plot titles "Gauge 1/2/3" above a table
that correctly reads G1/G4/G5).

**Where:** `blastlab/output/plots.py`, `figure_gauges_1d()` (title at line
~333, `f'Gauge {k+1}  (r = {r_val:.2f} m)'`) and `figure_gauges_nd()` (title
at line ~398, `f'Gauge {k+1}  ({loc}) m'`). Neither function takes a
`requested=` argument the way `output/gauge_summary.gauge_labels()` does, so
neither can know a gauge's entered number - they only see the solver's
surviving-point list and its 0-based position in it. This same path is
reached by:
- `services/exports.report_figures()` (~202-220) and `png_figures()`
  (~186-193), i.e. every "Report .html" and "All plots .png" export in
  **both** GUIs, and
- `blastlab/gui/results_panel.py` `_draw_gauges()` (~628-662), i.e. the Tk
  app's own on-screen Gauges tab (not just its exports) - the Qt app's
  on-screen Gauges tab is unaffected, because `ui/results_gauges.py` has its
  own plotting that already goes through the F42-fixed `labels_and_dropped`.

**Severity:** medium. Not a data-correctness bug (the values are right,
nothing is silently wrong), but it is a visible, user-facing numbering
mismatch in exactly the scenario this batch's A1 (F42) was written to fix,
and it ships in the HTML report - the artifact most likely to be printed,
emailed or cited as a design-basis record. A reader comparing "Gauge 2" in
the figure against "G2" in the Setup screen's gauge list would be looking at
the wrong gauge (the dropped one), not at the figure's actual second panel
(entered G4). This is outside the diff this QA pass was asked to verify
(`docs/batches/2026-10-04-gui-11e.verifyA.md`/`verifyB.md` scope was F42,
F44, T19/F17 and D213(b) only), so it is reported here as a new finding for
triage, not scored against this batch's acceptance criteria.

## 4. Numbers check (item 1, happy path)

Core function (`output.gauge_summary.table_rows(gauge_summary.summarize_gauges(
res.gauges, requested=res.meta.get('gauges')))`, called directly on the real
`Result` object returned by the same `win._run_single()` click) vs every
on-screen/exported surface, for the 3 surviving gauges:

| Entered gauge | Entered position | Core function | Qt Gauges-tab tooltip | Summary .csv | HTML report table | Tk summary table |
|---|---|---|---|---|---|---|
| G1 | (0.300, 0.800) | `G1 (0.300, 0.800) -> cell (0.305, 0.802) m` | identical | identical | identical | identical |
| G4 | (1.800, 0.800) | `G4 (1.800, 0.800) -> cell (1.797, 0.802) m` | identical | identical | identical | identical |
| G5 | (2.000, 1.200) | `G5 (2.000, 1.200) -> cell (1.996, 1.200) m` | identical | identical | identical | identical |

Peak/arrival numbers for G1 (the only gauge the wave reached in the run
window) also match across every surface: peak 7759.4 kPa at t=0.237 ms,
arrival 0.211 ms, pos. impulse 619.31 Pa.s, net impulse 619.32 Pa.s - byte
for byte the same string in the Qt table, the .csv, the .html report and the
Tk table.

The Run screen's own "LIVE GAUGES" side panel and status bar independently
say `G2 dropped by the solver (inside Wall 1)` / `G3 dropped by the solver
(on the face of Wall 1)` and `[warn] Gauge (1.2, 0.3) inside an obstacle -
dropped` respectively - the solver's own log line always says "inside an
obstacle" regardless of inside/face (by design, `solver2d.py` line ~289; only
the *validator*'s wording distinguishes the two cases), which is expected,
not a mismatch.

## 5. Visual findings

- All 12 Qt screenshots and the 1 Tk screenshot: no clipped labels, no
  missing units, no default-Tk-grey, no overlap, legible fonts, both themes.
- `01_setup_warnings.png`: the two obstacle warnings, the gauge list with
  entered positions, and the Checks tab's `0.2.3` (errors.warnings.notes)
  counter are all clean and readable.
- `03_run_strip_1280x840_running.png`: mid-run (18%), live slice plot
  animates, Stop button live, PMAX/TIME/STEP update - window repaints during
  the run as expected (native 2D case finished in 17-23 s across runs, so no
  "frozen UI" risk was tested beyond this).
- `04`-`08` (run-strip rows): confirmed both by the `_RunStrip.rows()` live
  property (1 at 1280x840/1600x1000, 2 at 1100x720, both themes) and by
  pixel-cropping the screenshots - at 1100x720 PROGRESS sits on its own row
  above a second row holding TIME/STEP/PMAX; at 1280x840+ all four tiles
  share one row. Matches the D213(b) plan exactly.
- `12_field_1d_title_*`: `1D spherical · 1.0 kg TNT · idealGas` (idealGas,
  not JWL - this harness's 1D case left `eos` at its default; the short-title
  *format* is what A3/T19 changed, and it is what's shown) sits centered
  inside the plot canvas at all 4 combinations, never clipped, legend and
  axes intact.

## 6. Cleanup

No application code was edited. No throwaway test files were added under
`tests/gui/` (the harness scripts lived under `D:\blastlab_tmp\`, outside the
repo, and are not part of this commit). All Qt/Tk windows opened by the
harnesses were closed (`win.close()` / `root.destroy()`) before the process
exited; `Get-Process python,pythonw` showed none running afterward. All run
output went to the throwaway `runs_dir` under `D:\blastlab_tmp\...`, never to
`/root/blastlab_runs` or the repo's own `runs` folder.
