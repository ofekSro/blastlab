# blastlab QA - phase 8 - 2026-09-25

Post-phase QA after refactor Phase 8 (`docs/ARCHITECTURE_REVIEW.md` section 5,
finding F3; commits `474bd77` "refactor(phase 8): models/meta.py - document
and pin `Result.meta`", `535a6ee` "refactor(phase 8): ui/results_fields.py
reads meta through models/meta", `828d5ed` "...ui/results_anim.py...",
`4909661` "...ui/results_gauges.py...", `73c71a2` "...services/exports.py...",
`043aa4d` "...gui/results_panel.py...", `84d0dae` "simplify(phase 8):
models/meta.py services/exports.py tests/char_meta_results.py", `b824d24`
"docs: the questions raised by phase 8" on branch `arch-p8-meta`). `Result.meta`
stays a plain dict filled by the native/foam solvers; `blastlab/models/meta.py`
adds `slice_geometry`, `frames_of`, `anim_scale_of` and `charge_label`
accessors, and the five results-panel files (Qt `ui/results_fields.py`,
`ui/results_anim.py`, `ui/results_gauges.py`, `services/exports.py`, Tk
`gui/results_panel.py`) now read meta through them instead of literal
`meta[k]`/`meta.get(k, default)` reads - same keys, same order, same
KeyError/default semantics per the commit messages. No application code was
edited during this QA session. Compared throughout against
`docs/qa/2026-09-24-baseline/QA_REPORT.md`, `-phase5a/`, `-phase5b/`,
`-phase6/` and `-phase7/QA_REPORT.md`.

## 1. Environment

| | |
|---|---|
| Python | 3.12.10 (Microsoft Store build), on PATH as `python` |
| Qt | PySide6 (offscreen, `blastlab.ui.testing.ensure_qapp()` - which itself calls `theme.apply(app, 'dark')` when it creates the `QApplication` - for the Fields/Gauges/Animation walkthrough and the two QA harnesses; real platform, `QT_QPA_PLATFORM` unset, `theme.apply(app, settings.load()['appearance'])` called explicitly exactly as `ui/app.py`'s own `main()` does, for the real-platform startup + 3D-viewer-child check) |
| Tk | CustomTkinter, real desktop window (Tk has no offscreen mode); launch mirrors `blastlab.gui.app.main()` exactly - `ctk.set_appearance_mode('dark')` **then** `root = ctk.CTk()` **then** `App(root)` - see §4.1, a harness pitfall this session caught and fixed before trusting any Tk screenshot |
| Pillow | present; screenshots via `QWidget.grab()` (Qt offscreen) and Win32 `PrintWindow(PW_RENDERFULLCONTENT)` via ctypes (Tk real window, and the one real-platform Qt check) - the same ground-truth technique every earlier session in this repo used |
| OS | Windows 11 Enterprise 10.0.26200 |
| Launch | `blastlab.ui.app.MainWindow` and `blastlab.gui.app.App` built directly in throwaway harness scripts under the session scratchpad (`...\scratchpad\qa-p8\`: `common.py`, `qt_walkthrough.py`, `tk_walkthrough.py`, `qt_realplatform_3d.py`, `compare_qt_tk.py`), plus the project's own `blastlab/tests/_qa_ui_harness.py`, `_qa_gui_harness.py` and `test_regression.py` run unmodified as subprocesses |
| Settings guard | every process set `BLASTLAB_SETTINGS` to a private file **before** any `blastlab` import and asserted `settings.load()['auto_cleanup'] is False` before building any window (`common.verify_guard()`, printed `settings guard OK: auto_cleanup=False` in every one of my own scripts' logs). The two harnesses write their own scratch `settings.json` with `auto_cleanup: false` per their documented startup. `env.auto_cleanup(...)` was never called anywhere. |
| WSL | read-only probe only: `wsl -d Ubuntu -- pgrep -a blastFoam` returned empty (exit 1, no matches) before and after the session. **No WSL solve, no blastFoam run** - every run this session was native (1D, 2D, 3D). |
| Cases | `Case1D(radius_m=2.0, charge_kg=1.0, cell_size_m=0.005, gauge_radii=[0.5, 1.0], n_snapshots=3)` (the same small 1D case phase 6/7 used, for numeric comparability); `blastlab/tests/cases/native_2d_small.json` loaded via `models.case.load_case` with `record_frames` overridden to 20 in the loaded `Case2D` object in memory (the checked-in fixture file itself was never touched); `blastlab/tests/cases/native_3d_small.json` loaded unmodified |
| Python processes | none running before the session; none left running after any of my own scripts or either harness (`Get-Process python*` checked repeatedly, empty every time) |

## 2. Result table

| # | Item | Result | Evidence | vs. earlier phases |
|---|---|---|---|---|
| 1 | Qt startup (offscreen) | PASS | `screenshots_qt/01_startup.png` - title `blastlab 1.0.0`, 1400x900, no traceback | same |
| 1b | Qt startup (real platform, `theme.apply` called explicitly) | PASS | `screenshots_qt/realplatform_start.png` - dark palette, correct | phase 7 flagged a real-platform LIGHT-palette anomaly (§4.2 there); **not reproduced this session** - see §4.2 |
| 1c | Tk startup (real window, dark mode) | PASS | `screenshots_tk/01_startup.png` | see §4.1 - first attempt rendered light, a harness bug I fixed before trusting it, matching the class of mistake phase 7 hit for Qt |
| 2 | Native 1D small case: Run -> Results, Fields (profiles) / Gauges / Animation | PASS | `screenshots_qt/02-07`, `screenshots_tk/02-07`; §6 | new focus this phase - Results panels are exactly what phase 8 touched |
| 3 | Native 2D case with `record_frames=20`: Run -> Results, every field x first/last snapshot, Show mesh, Gauges, Animation (first/mid/last frame, manual vs auto colour scale, play/pause) | PASS | `screenshots_qt/08-22`, `screenshots_tk/08-21`; §5, §7 | new this phase |
| 4 | Native 3D small case: Run -> Results, every field (x-z/x-y planes, isosurface) x first/last snapshot, Show mesh, Gauges, Animation (no recorded frames) | PASS | `screenshots_qt/23-38`, `screenshots_tk/22-36`; §5 | new this phase |
| 5 | 1D displayed Gauges table vs `solve_1d()` called directly | PASS - string-identical, both GUIs | §6 | matches phase 6/7's own numbers for the same case exactly |
| 6 | Qt vs Tk: Gauges rows/titles (1D/2D/3D) and Fields titles (2D/3D, every field) | PASS - 30/30 comparisons matched | `compare_qt_tk.py` output, §7 | new this phase (first session to diff Results panels field-by-field across both GUIs after phase 8's shared-accessor move) |
| 7 | 3D viewer tab (embedded pyvista host): offscreen startup + real-platform startup, with a real 3D result loaded and "3D Viewer" clicked | PASS, with one already-established capture caveat | `screenshots_qt/38_3d_viewer_tab.png` (offscreen), `screenshots_qt/realplatform_3d_viewer_after_open.png` (real platform); §4.3 | consistent with baseline's own §4.1 finding (PrintWindow cannot reach the VTK/pyvista OpenGL swap chain) - not new |
| 8 | Long calculation: window repaints mid-run, Run button disabled (3D case, ~29-32 s native solve) | PASS | `screenshots_qt/23_run_midway.png`/`screenshots_tk/22_run_midway.png` - live slice updating, `Stop` button active | same as every earlier phase |
| 9 | Close terminates cleanly | PASS | every script closed its window; no leftover `python` process after any of them | same |
| 10 | `_qa_ui_harness.py` D01,D02,D04,E01-E09 (Qt, native, fresh `--out`) | PASS - 12/12 done, exit 0, 1 finding (D02 S1, the known flake) | §8 | **identical pattern to phase 6**: 12/12 done, exit 0, 1 finding, same D02 check |
| 11 | `_qa_gui_harness.py` D01,D02,D04,E01-E09 (Tk, native, fresh `--out`) | PASS - 12/12 done, exit 0, 0 findings | §8 | **identical pattern to phase 6**: 12/12 done, exit 0, 0 findings |
| 12 | `python -u test_regression.py` | PASS - 8/8 | §8 | byte-identical/array-equal to the frozen baseline, identical to baseline/5a/5b/6/7's own comparison |

**No FAILs anywhere in this session. No NEW failure vs. any earlier phase report.**

## 3. Failures

**None.** No crash, traceback, incorrect displayed number, or wrong file
content was found anywhere in this run (my own scripted Fields/Gauges/
Animation walkthrough on 1D/2D/3D in both GUIs, the Qt-vs-Tk comparison, the
real-platform 3D-viewer check, both QA harnesses, or `test_regression.py`).

## 4. Visual / technique findings (not scored as failures)

### 4.1 A harness pitfall on the Tk side, the same class of mistake the task warned about for Qt

Building `App(tk.Tk())` directly - the pattern every earlier phase's own Tk
QA script used, going by their reports - renders in **whatever palette the
OS is currently in**, not dark, on this machine right now: `gui/app.py`'s
`App.__init__` only forces `ctk.set_appearance_mode('light')` when the
settings file says `'light'` (`if str(st.get('appearance', 'dark')).lower()
== 'light': ... self._toggle_mode()`); it never forces `'dark'` itself,
because `gui/app.py`'s own `main()` already does that **before** building
the window (`ctk.set_appearance_mode('dark'); root = ctk.CTk(); App(root)`).
A script that skips `main()` and builds `App(root)` straight off a bare
`tk.Tk()` inherits CustomTkinter's own "System" default instead. My first
`tk_walkthrough.py` run did exactly that and produced 36 screenshots in a
light grey/white palette with the "Dark mode" toggle visibly OFF (kept under
`C:\Users\rotem.ofek\blastlab_qa\20260925-phase8\_old_screenshots_tk_lightmode_run1\`
for the record, not under `docs/qa/`). Fixed by mirroring `main()` exactly
(`ctk.set_appearance_mode('dark')`, `root = ctk.CTk()`, then `App(root)`) and
rerun; every Tk screenshot in this report is from the corrected run
(`appearance_mode: "Dark"` recorded in `tk_results.json`). Not a product
bug - `gui/app.py`'s asymmetric settings read (`'light'` is honoured,
`'dark'` relies on `main()`'s own prior call) is pre-existing and outside
phase 8's diff - but worth recording here because it is the Tk-side twin of
the exact Qt mistake the task's own "IMPORTANT technique" note warns about,
and it will bite the next scripted QA session in this repo the same way if
not written down.

### 4.2 Real-platform Qt startup: dark palette, correctly - phase 7's light-palette anomaly not reproduced

`screenshots_qt/realplatform_start.png` (real platform, `theme.apply`
called explicitly before `MainWindow()`, PrintWindow ground truth) renders
in the dark palette with "Dark mode" checked, matching the offscreen
screenshot from the same session. Phase 7's report (§4.2 there) flagged the
opposite - a light render with the checkbox checked - as an unresolved,
not-reproduced-since finding. This session's real-platform capture does
**not** show that anomaly; recorded for the trend, not claimed as a fix
(`ui/theme.py` is outside phase 8's diff either way).

### 4.3 3D viewer tab, real platform: the PrintWindow/VTK swap-chain gap, reproduced again

Opening the Results tab's "3D Viewer" for a real, just-run 3D result and
waiting 10 s (real platform, `QT_QPA_PLATFORM` unset) still shows the
`View3DHost` panel's own **"starting the 3D view…"** placeholder in the
PrintWindow capture
(`screenshots_qt/realplatform_3d_viewer_after_open.png`), even though
`win.results.view()` correctly reports `'3D'` and no exception was raised.
This is **exactly** the baseline session's own §4.1 finding, cited there in
full: `PrintWindow`/`WM_PRINT` is well known not to reach a VTK/pyvista
OpenGL swap chain (it captures GDI/software-rendered content, which is why
it correctly captured the Qt-drawn placeholder text and the rest of the
window chrome around it). Not re-investigated further this session, per
that precedent; not scored as a failure, not new.

### 4.4 The embedded 3D-viewer control tabs truncate to unreadable labels

`screenshots_qt/38_3d_viewer_tab.png` (offscreen) and the harness's own
`contact_E06.png` (`~/blastlab_qa/20260925-phase8-qt/sheets/`) both show the
Results-tab 3D viewer's own three-way tab strip rendering as **"D…y"**,
**"P…s"** and **"View"** instead of "Display", "Planes", "View"
(`ui/view3d_host.py:234`, `Segmented(['Display', 'Planes', 'View'], ...)`)
- the segmented control's own middle-elision (the same mechanism
`ResultsPanel.elide_middle` documents for the result picker) is applied to
a control too narrow for its three labels at this panel width. Reproduced
identically offscreen and on the real platform, so it is a real rendering
outcome, not a capture artifact. `ui/view3d_host.py` is untouched by phase
8's diff (`models/meta.py` and the five results-panel files) - pre-existing,
not a regression, and not previously reported in any earlier QA session
that looked at the Results 3D tab specifically (baseline's own 3D-tab
screenshots were of the Setup screen's Model Preview, a different widget).

### 4.5 The peak/impulse colour bar draws its axis label twice, overlapping

Every "peak overpressure" / "net ovp impulse" field in the Qt Fields view
shows its colour-bar caption as two overlapping copies of the same text
(e.g. `screenshots_qt/14_2d_fields_peak_overpressure_t = 0.191 ms.png`,
`16_2d_fields_mesh_on.png`) - legible individually but visually smeared
where they overlap. Every plain field (overpressure/density/speed) shows a
single, clean label in the same session's own screenshots
(`08_2d_fields_overpressure_t = 0.191 ms.png`), so the duplication is
specific to the "robust"/clipped path. Traced to
`blastlab/ui/pg_plots.py:191-200`, `ScalarImage.set_bar_label`:
```python
for axis in ('right', 'left'):
    try:
        self.bar.getAxis(axis).setLabel(str(text))
    except Exception:
        pass
```
- it sets the SAME text on both the `'right'` and `'left'` axis of the
colour bar item, apparently to cover two different pyqtgraph configurations;
empirically both axes are visible at once in this widget, so both render.
Not touched by phase 8's diff (`results_fields.py`'s diff is the
`slice_geometry`/`charge_label` reads two lines above where `sel['unit']`
is built, not `set_bar_label` itself) - pre-existing, not a regression.
Flagging for a follow-up session with the budget to root-cause which axis
is the real one; not fixed here.

### 4.6 `FieldsView.title()` (Qt) is stale on the two non-map pages - a script gotcha, not a product bug

`ui/results_fields.py`'s `_draw_figure` (the 1D profiles page and the 3D
isosurface page) never sets `self._title`, so `FieldsView.title()` -
`getattr(self, '_title', '')` - returns whatever the LAST `_draw_map` call
left there, not the figure actually on screen. My first pass at
`qt_walkthrough.py` collected `""` for the 1D profiles title and a
leftover 3D-map title for the isosurface page purely because of this. Fixed
by reading the matplotlib figure's own `_suptitle` for the two figure pages
instead (`figure_title()` in `qt_walkthrough.py`); the corrected numbers are
what §6/§7 report. Confirmed by direct read of `results_fields.py` that
`title()` is simply not meaningful off the map page - not a defect in the
app (the on-screen title is correct in every screenshot; only my own
script's cheap accessor was wrong), recorded so a future session's harness
does not repeat it.

### 4.7 Tk's Animation view has no colour-scale control at all - a pre-existing Qt/Tk gap, not phase 8

`gui/results_panel.py` has no `scale_sel`/`min_box`/`max_box` anywhere
(confirmed by `grep`), and `_show_frame` calls `plots.set_frame(mesh,
frames['pressures'][k], solid)` with **no** `clim` - always per-frame
autoscale, matching `output/plots.set_frame`'s own docstring ("Autoscales
per frame unless a fixed (vmin, vmax) ... is given"). Qt's `AnimView` has a
full `Colours` row (`Auto colour scale (whole video)` / `Manual range` /
per-frame, `ANIM_SCALE_LABELS`) that starts from the run's own recorded
`meta['anim_scale']`. Confirmed empirically: `tk_results.json`'s
`2d_anim.has_scale_control` is `false`; the Tk 2D-animation screenshots show
the colour bar's numeric range jumping between frames (t=0 frame tops out
around 2.5e6 "kPa" - the still-detonating charge cell, t=0.054ms frame tops
around 5e5) while the equivalent Qt screenshots, once "fixed (whole video)"
is selected, hold one range throughout. `_show_frame`/`_setup_anim` are
exactly the two functions phase 8's own Tk commit (`043aa4d`) touched for
their meta reads, so this was checked carefully: the diff only changes how
`frames_of`/`slice_geometry` are read, not the missing `clim` argument -
confirmed by reading the commit's own diff. Pre-existing, not phase 8.

### 4.8 `vtkLookupTable` log-scale warning, reproduced - same field, same numbers as phase 6

The Qt harness's E06 scenario (embedded 3D viewer, native 3D result) logged
the identical warning phase 6 recorded:
`vtkLookupTable (...): Bad table range for log scale: [-5621.37, 254182]`
- traced this session to the **"Net ovp impulse"** field specifically
(`screenshots` `058_E06_results_field_imp_dark.png` shows `Min -5621.37`,
`Max 254182` in the viewer's own Min/Max boxes): net impulse can be
negative (the negative phase), and the viewer's default "Log colour scale"
checkbox (checked by default, matching CLAUDE.md §7's documented intended
behaviour for pressure) cannot take a log of a negative range. Harmless -
the scene still renders, just without the requested log scaling for that
one field - and unrelated to phase 8's diff (`viz3d/` was not touched).
Identical numeric range to phase 6's own report, so this is the SAME
deterministic warning on the SAME fixture case, not a new occurrence.

### 4.9 2D case's second gauge sits outside the blast at the run's short stop time - correct, not a bug

`Gauge 2 (2.000, 0.300)` in the `record_frames=20` 2D case reads a flat
`0.0 kPa` peak, blank arrival/t-peak, in both GUIs' Gauges tables and
figures (`screenshots_qt/17_2d_gauges.png`,
`screenshots_tk/17_2d_gauges.png`) - the shock had not reached it by
`t = 0.466 ms`, the case's own automatic stop time. Rendered cleanly (a
flat trace at 0, correctly auto-scaled axes, no NaN/empty-plot artifact);
confirmed by both `gauge_summary` and the raw gauge time histories. Not a
bug - an artifact of this session's deliberately small/fast case, kept as
originally shipped except for `record_frames`.

## 5. Screenshots - representative set

Every one of the 41 Qt / 36 Tk screenshots was read and checked; nothing
clipped, overlapped, or showed the default-Tk-grey look. Representative
ones, referenced above: `01_startup.png` (both GUIs), `03_1d_results_tab.png`
/ `09_2d_results_tab.png` / `24_3d_results_tab.png` (Qt) and their Tk
equivalents (the Results tab reached the same way a user would - via the
sidebar, not just the inner sub-view selector, see the harness fix note
below), `05_1d_fields_mesh_on.png` (Show mesh is a correct no-op on the 1D
profile page), `21_2d_anim_manual.png` (manual colour range 0-500 kPa
applied and clipped correctly), `38_3d_viewer_tab.png` /
`realplatform_3d_viewer_after_open.png` (§4.3/§4.4).

**One more harness fix worth recording** (own script, not a product issue):
`ResultsPanel.show_view(name)` only changes the Results panel's OWN inner
sub-view (Fields/Gauges/Animation/3D); the very first draft of
`qt_walkthrough.py`/`tk_walkthrough.py` called only that after a run and
captured the **Run** tab (the app's top-level sidebar was never told to
switch). Fixed by calling `win._show('results')` / `app._show('results')`
(the same call the sidebar's own "Results" button makes) right after each
run, confirmed via `win.current_tab() == 'results'`; every screenshot in
this report is from the corrected pass. Recorded because it produced six
completely wrong screenshots on the first attempt and would trip up a
future session's harness the same way.

## 6. Numbers check - native 1D, GUI vs `solve_1d()` direct (both GUIs)

`Case1D(radius_m=2.0, charge_kg=1.0, cell_size_m=0.005, gauge_radii=[0.5,
1.0], n_snapshots=3)` - the same case phase 6/7 used - run through the real
Setup -> Run -> Results flow in both GUIs (native, 1.75-2.2 s wall through
the GUI worker), compared against `solve_1d(case, RunHooks())` called
directly and summarised with `output.gauge_summary.summarize_gauges` +
`table_rows` - the same functions the Results table itself calls.

| Gauge | Peak [kPa] | Arrival [ms] | t peak [ms] | Pos. phase [ms] | Pos. imp [Pa·s] | Net imp [Pa·s] | Phase ended |
|---|---|---|---|---|---|---|---|
| G1 r=0.502 m | 3412.8 | 0.152 | 0.165 | 0.078 | 138.12 | 31.19 | yes |
| G2 r=0.998 m | 934.0 | 0.485 | 0.511 | 0.692 | 137.36 | 123.43 | yes |

**String-identical** across all four sources checked - the Qt Results
table, the Tk Results table, and each GUI's own direct `solve_1d()` call -
for every one of the 14 values, peak/arrival/impulse all checked, never
peak alone, per CLAUDE.md's measurement discipline note. **Matches phase
6's and phase 7's own numbers for the identical case exactly.** `Result.meta`
now flows through `models/meta.py`'s `charge_label` for the 1D figure and
gauges titles (confirmed: both read `"1.0 kg TNT"` / `"EOS: idealGas"`
correctly) - phase 8's diff did not change a single displayed digit, as its
own commit messages claim ("Same keys read the same way").

## 7. Qt vs Tk - Results panel comparison

Both GUIs ran the **identical** three cases (1D above; 2D
`native_2d_small.json` with `record_frames=20`; 3D `native_3d_small.json`
unmodified), then every Gauges row/title and every Fields-view title (every
field option, first and last snapshot) was compared
(`compare_qt_tk.py`, full output in
`C:\Users\rotem.ofek\blastlab_qa\20260925-phase8\`):

| Check | Result |
|---|---|
| 1D/2D/3D Gauges table rows | **MATCH**, string-identical, 3/3 |
| 1D/2D/3D Gauges figure title | **MATCH**, string-identical, 3/3 |
| 1D GUI vs `solve_1d()` (Qt and Tk each) | **MATCH**, 2/2 |
| 2D Fields titles, 8 field/snapshot combinations | **MATCH (prefix)**, 8/8 |
| 3D Fields titles, 13 field/snapshot combinations | **MATCH (prefix)**, 13/13 |

**30/30 comparisons matched.** "MATCH (prefix)" for the map fields is the
expected, pre-existing, **by-design** screen/file difference the module's
own docstring states ("Screen and file differ here by design"): Qt's
persistent pyqtgraph panel composes its title as `"{field} - {charge
label}  ·  {panel/snapshot label}"` in one string
(`results_fields.py:315`), while Tk rebuilds a matplotlib multi-panel grid
figure per redraw and puts the snapshot/panel label on the sub-axes instead
of the suptitle (`gui/results_panel.py:589`, `plots._panel_grid_figure`) -
so Tk's title is exactly the Qt title with the trailing `"· t = ... ms"` /
`"· whole run"` segment held back for the sub-axes. Confirmed by direct
string-containment check (`tk_t in qt_t`), not just eyeballing - every one
of the 21 field-title pairs passed. This is unrelated to phase 8 (neither
`_panel_grid_figure` nor the Qt title composition line were touched) and
was already implicitly true before phase 8; this session is the first to
check it field-by-field across both GUIs since the shared-accessor move.

**Peak/arrival/impulse numbers, gauge counts, and every recorded snapshot
label were identical between the two GUIs for all three dimensions** - the
`models/meta.py` accessors read exactly the same keys in exactly the same
order the two GUIs' old literal reads did, confirming the commits' own
"same keys read the same way" claim empirically rather than by re-reading
the diff.

## 8. `_qa_ui_harness.py` / `_qa_gui_harness.py` - D+E groups, and `test_regression.py`

Both run with an explicit fresh `--out` (never `--resume`), `--solver
native`, scenarios `D01,D02,D04,E01,E02,E03,E04,E05,E06,E07,E08,E09` -
the same set phase 6 used (D01/D02/D04 seed the 1D/2D/3D results the E
group's Fields/Gauges/Animation/export scenarios then read; F00-F11, the
blastFoam/WSL scenarios, were deliberately never selected, per the
no-WSL-solve constraint):

```
python -u _qa_ui_harness.py  --out ~/blastlab_qa/20260925-phase8-qt --scenario D01,D02,D04,E01..E09 --budget 3600 --solver native
python -u _qa_gui_harness.py --out ~/blastlab_qa/20260925-phase8-tk --scenario D01,D02,D04,E01..E09 --budget 3600 --solver native
```

- **Qt: 12/12 `done`, exit 0.** One finding: `D02`, S1, **"the 2D solver
  announced itself" - failed** (`qa.wait_log('2D Blast Solver', 40)` did
  not see the banner line within 40 s of clicking Run; the run itself
  finished correctly 51.4 s later and every other D02/E-group check
  passed). **This is the known, pre-registered flake** named explicitly in
  the task brief - reproduced in phase 5a, phase 6, and again here,
  **not reproduced in the 2026-09-24 baseline**. Not attributable to phase
  8's diff (`case_form.py`/the run/log pipeline play no part in it, and
  `results_fields.py`/`results_gauges.py`/`results_anim.py`/`exports.py`
  play no part in the RUN tab's log at all). `D04` (native 3D) took 699.1 s
  wall this run - within the historical 525-777 s range seen across phase
  5a/6/7's own sessions on this machine, attributable to CPU contention
  (the Tk harness was running its own D04 for part of the same interval;
  once the Tk harness finished, Qt's E group ran at its normal 3-20 s per
  scenario pace). `E06` (embedded 3D viewer) logged the same
  `vtkLookupTable` log-scale warning as phase 6, same numeric range - §4.8.
- **Tk: 12/12 `done`, exit 0, 0 findings** (`findings.jsonl` does not exist
  - empty run). `D02` logged the same non-scored `wait_log TIMEOUT for '2D
  Blast Solver'` NOTE as every earlier phase - not scored, not new.
- **Neither harness's `checkpoint.json` shows any `foreign_pids`**; no
  WSL/blastFoam process interfered. No `Traceback`, `CRASH`, `crashed`,
  `KillSwitch` or unhandled `Exception` string anywhere in either
  `harness.log` (checked with a direct `grep` of the full logs).
- **This is the identical pass/finding pattern phase 6 recorded**
  (12/12 + 1 finding for Qt, 12/12 + 0 findings for Tk, same D02 cause,
  same E06 warning) - strong evidence phase 8's diff changed nothing this
  surface can observe.

**`python -u test_regression.py`: PASS - 8/8**, byte-identical/array-equal
to the frozen baseline (`b1_gauges.txt`, `b1_profile.txt`, `b2_gauges.txt`
byte-identical; `b2_profile.npz` arrays equal; `b2r_gauges.txt`,
`b3_gauges.txt`, `b3r_gauges.txt`, `transcript.txt` byte-identical) -
identical to baseline's, phase 5a's, phase 5b's, phase 6's and phase 7's
own comparisons. This suite exercises the native solvers directly and
never touches any Results panel, so an unchanged result was expected; run
because the task asked for it.

## 9. Suspected engineering errors (not investigated, per task scope)

Already on record in `docs/ENGINEERING_QUESTIONS.md` under "2026-09-25 -
`/refactor` phase 8" (added by this branch's own `b824d24`, read but not
investigated) and reproduced, unchanged, in this session's own live runs:

1. **Every title says "kg TNT" whatever the EOS or material.**
   `output/plots.charge_label` always writes "kg TNT" / "kg/m TNT" -
   confirmed again this session: the idealGas 2D case (`eos: idealGas`)
   titles as `"... - 20 kg/m TNT"`, the idealGas 3D case as `"... - 900 kg
   TNT"`, both in the field titles (§7) and the gauges figure titles (§6),
   for a case whose EOS is not TNT at all. This is the display side of the
   already-tracked UX-E1 (the field is a material mass, not a TNT
   equivalent). Not investigated further, per task scope.

No new suspected engineering error was noticed in this session.

## 10. Cleanup

Every window/QApplication/Tk root built by my own scripts was closed
(`win.close()`/`root.destroy()`) before its script exited; both harnesses
tear down their own window in their `finally` blocks; the one real-platform
3D-viewer script's `win.close()` also tore down the pyvista child process
(`viewer_link.close()`, confirmed via `closeEvent`) - `Get-Process
python*` was empty before the session and empty after every command,
including the long-running ones (the two ~11-12-minute harness runs and the
699 s `D04` scenario inside the Qt one). `env.auto_cleanup(...)` was never
called (every script's settings guard was verified `False` before building
a window; the two harnesses' own guards were read, not modified). No file
under `~\Desktop` was touched. Helper scripts lived only under the given
scratchpad path (`...\scratchpad\qa-p8\`: `common.py`, `qt_walkthrough.py`,
`tk_walkthrough.py`, `qt_realplatform_3d.py`, `compare_qt_tk.py`). No
`blastlab` application file was edited; no git command that changes
anything was run (only reads: `git log`, `git show --stat`). Bulky output
(both harnesses' full run directories, the two walkthroughs' JSON summaries,
the one light-mode Tk screenshot set kept for the §4.1 record) lives under
`C:\Users\rotem.ofek\blastlab_qa\20260925-phase8\` and
`...\20260925-phase8-qt\` / `...\20260925-phase8-tk\`, not under `docs/qa/`,
per the task's instruction; only the 41 Qt + 36 Tk final screenshots and
this report are under `docs/qa/2026-09-25-phase8/`.
