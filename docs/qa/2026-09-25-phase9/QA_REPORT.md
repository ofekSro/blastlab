# blastlab QA - phase 9 - 2026-09-25

Post-phase QA after refactor Phase 9 (`docs/ARCHITECTURE_REVIEW.md` section 5,
findings F11/Q6; commits `76dbb45` "refactor(phase 9): close the upward and
cross-toolkit edges; lock the layering test" and `2524180` "simplify(phase 9):
tests/test_layering.py" on branch `arch-p9-layering`). The functional change
is narrow: `blastlab/services/foam_runs.py` (new) re-exports
`solvers/foam/runs.dims_from_case_json` and
`solvers/foam/postmortem.list_runs`/`load_run`; `ui/app.py`'s
`_resume_foam_run` now imports `dims_from_case_json` from that new module
instead of a `try: from .run_browser import ... except ImportError: from
..gui.run_browser import ...` fallback (the fallback is gone -
`ui/run_browser.py` re-exports the same name unchanged, docstring only);
`solvers/foam/common.py` (new) holds `part_counts`/`rd_scalar` moved verbatim
out of `backend.py` so `runloop.py` no longer imports `backend` (breaking the
backend<->runloop import cycle); `core/assessment.py` now imports
`ValidationReport`/`Case3D` from `models/` directly instead of through the
`core.case` shim; `tests/test_layering.py` gained stricter rules; and
`core/settings.py`, `gui/mode.py`, `gui/settings.py`, `gui/worker.py` had
docstring-only wording changes (Tk described as the permanent way back
behind `--tk`, per CLAUDE.md section 9, instead of "remove with the Tk
package"). No application code was edited during this QA session. Compared
throughout against `docs/qa/2026-09-25-phase8/QA_REPORT.md` (the baseline for
the shared Results-panel/1D-numbers findings) and, for the run browser
specifically, this is the **first** QA session in this repo's `docs/qa/`
history to screenshot the "blastFoam runs" dialog in either GUI - there is no
earlier run-browser report to diff against.

## 1. Environment

| | |
|---|---|
| Python | 3.12.10 (Microsoft Store build), on PATH as `python` |
| Qt | PySide6 6.11.2, real platform (`QT_QPA_PLATFORM` unset), `theme.apply(app, settings.load()['appearance'])` called explicitly exactly as `ui/app.py`'s own `main()` does, before `MainWindow()` is built |
| Tk | CustomTkinter 6.0.0, real desktop window; launch mirrors `blastlab.gui.app.main()` exactly - `ctk.set_appearance_mode('dark')` **then** `root = ctk.CTk()` **then** `App(root)` (phase 8 4.1's fix, reused here) |
| Pillow | present (12.2.0); screenshots via Win32 `PrintWindow(PW_RENDERFULLCONTENT)` through ctypes for every window in both GUIs, including the `FoamRunBrowser` Toplevel/QDialog specifically (not just the main window) - the same ground-truth technique every earlier QA session in this repo used |
| OS | Windows 11 Enterprise 10.0.26200 |
| Launch | `blastlab.ui.app.MainWindow` and `blastlab.gui.app.App` built directly in throwaway harness scripts under this session's scratchpad (`...\scratchpad\qa-p9\`: `common.py`, `import_sanity.py`, `qt_session.py`, `tk_session.py`), plus `python -m blastlab --load-foam-run <run>` and `python -u test_regression.py` run unmodified as subprocesses |
| Settings guard | every process set `BLASTLAB_SETTINGS` to a private file **before** any `blastlab` import and asserted `settings.load()['auto_cleanup'] is False` before building any window (`common.verify_guard()`, printed `settings guard OK: auto_cleanup=False` in every script's log). `env.auto_cleanup(...)` was never called anywhere. |
| WSL | `wsl -d Ubuntu -- pgrep -a blastFoam` returned empty (exit 1) before and after the session - no foreign solver. Read-only listing/`du`/`ls`/`cat case.json` only. **No WSL solve, no resume execution, no delete** - verified by run count (`/root/blastlab_runs` held 10 runs, 426.8 GB total, before and after the whole session) |
| Cases | `Case1D(radius_m=2.0, charge_kg=1.0, cell_size_m=0.005, gauge_radii=[0.5, 1.0], n_snapshots=3)` - the identical case phase 6/7/8 used, for numeric comparability |
| Real WSL run used for `--load-foam-run` | `20260921-214703_3d_p27908-00` (3D, 4.9 MB, picked because it is the smallest run with real solution data beyond `t=0`, so the post-mortem load would be fast; confirmed fast: a few seconds, headless, exits) |
| Python processes | none running before the session; none left running after any script, including the `--load-foam-run` subprocess and `test_regression.py` (`Get-Process python*` empty every time it was checked) |

## 2. Result table

| # | Item | Result | Evidence | vs. earlier phases |
|---|---|---|---|---|
| 1 | Import-only sanity: every edge the phase 9 commits actually moved (`services.foam_runs` identity, `ui.run_browser` still re-exports, `_resume_foam_run` source now imports `services.foam_runs` with no `gui.run_browser` fallback, `core.assessment`'s `ValidationReport`/`Case3D` now from `models/` with the `core.case` shim still resolving to the same objects, `solvers.foam.common`'s `part_counts`/`rd_scalar` identity with `backend`'s re-export, `runloop.py` source contains no `backend` import, `gui.mode`/`gui.settings`/`gui.worker` shim identity) | **PASS - 17/17** | `import_sanity.json` | new this phase (no GUI needed; the fastest, most direct test of what phase 9 actually changed) |
| 2 | Qt startup, real platform (`theme.apply` exactly as `ui/app.py main()`) | PASS | `screenshots_qt/01_startup_realplatform.png` - dark palette, title `blastlab 1.0.0`, 1400x900, no traceback | same as phase 8's own real-platform check (4.2 there); still dark, still correct |
| 3 | Qt native 1D run -> Results; peak/arrival/impulse vs `solve_1d()` direct | PASS - string-identical | `screenshots_qt/02_1d_before_run.png`, `03_1d_results.png`; §5 below | same numbers as phase 6/7/8's own identical case |
| 4 | Qt "blastFoam runs" dialog: real WSL listing (read-only), select a run, dims/info shown | PASS | `screenshots_qt/04_run_browser_real_listing.png`, `05_run_browser_real_selected.png`; §6 | new this phase - first session to open this dialog |
| 5 | Qt run-browser Resume/Delete REFUSAL on a fabricated alive=True/None row (synthetic lister, same injectable pattern as `test_ui_run_browser.py`) - Resume never actually called | PASS | `screenshots_qt/06_run_browser_synthetic.png`, `07_run_browser_synthetic_refused.png`; §6 | new this phase |
| 6 | Qt `MainWindow._resume_foam_run()` called with a bogus path - forces the new `services.foam_runs` import to run and then hit the `except` branch, **before** `ctrl.resume_foam_run()` (which would start a real solve) is ever reached | PASS | `screenshots_qt/08_resume_foam_run_bogus_path.png` - red status `cannot resume ...: invalid literal for int() with base 10: '?'` | new this phase - the most direct possible test of the exact line phase 9 changed, with zero solve risk |
| 7 | Tk startup, dark mode (mirrors `gui.app.main()`) | PASS | `screenshots_tk/01_startup.png` | same as phase 8 (4.1's fix reused) |
| 8 | Tk solver-mode switch native -> blastFoam -> native (`gui/mode.py`, `gui/settings.py` docstrings changed this phase) | PASS | `screenshots_tk/02_mode_blastfoam.png`, `03_mode_native.png` - blastFoam mode shows the WSL info card (cores, parallel-run plan); native mode shows the "Pure-Python solver" card; `mode_switch_ok: true` | new this phase |
| 9 | Tk native 1D run -> Results; peak/arrival/impulse vs `solve_1d()` direct | PASS - string-identical | `screenshots_tk/04_1d_before_run.png`, `05_1d_results.png`; §5 | same numbers as phase 6/7/8 |
| 10 | Tk run browser (`gui/run_browser.py`, untouched by phase 9): real WSL listing (read-only), select a run, dims/info shown | PASS | `screenshots_tk/06_run_browser_real_listing.png`, `07_run_browser_real_selected.png`; §6 | new this phase |
| 11 | Tk run-browser Resume REFUSAL on a fabricated alive=True/None row - Resume never actually called | PASS | `screenshots_tk/08_run_browser_synthetic.png`, `09_run_browser_synthetic_refused.png`; §6 | new this phase |
| 12 | `python -m blastlab --load-foam-run 20260921-214703_3d_p27908-00` (real run, read-only post-mortem, headless, no GUI) | PASS | console output in §7; run count unchanged before/after (10 runs) | new this phase |
| 13 | `_qa_ui_harness.py` / `_qa_gui_harness.py` | **SKIPPED, deliberately** | `--list` read for both (§8) | see §8 for why - not a gap, a scope decision |
| 14 | `python -u test_regression.py` | **PASS - 8/8**, byte-identical/array-equal to the frozen baseline | `test_regression.log` | identical to baseline/5a/5b/6/7/8's own comparisons |

**No FAILs anywhere in this session. No NEW failure in any code phase 9 touched.**
One new (not-previously-documented, not a regression) visual finding in code
phase 9 did **not** touch - §4.

## 3. Failures

**None.** No crash, traceback, incorrect displayed number, wrong dims/info in
either run browser, or unsafe action (no Resume, no Delete, no WSL solve) was
found anywhere in this session.

## 4. Visual findings (not scored as failures)

### 4.1 The run browser's status/refusal line overlaps or truncates against its own button bar - both GUIs, newly observed this session, pre-existing

This is the first QA session in this repo to screenshot the "blastFoam runs"
dialog with a realistic refusal message, in either GUI, so it has not been
reported before. Neither `ui/run_browser.py` (Qt, docstring-only this phase)
nor `gui/run_browser.py` (Tk, untouched this phase) is part of phase 9's
functional diff - this is pre-existing layout, not a regression.

- **Tk** (`screenshots_tk/09_run_browser_synthetic_refused.png`, dialog at
  900x460, the size this session used): the red status text `not resuming
  20260101-000000_1d_pFAKE-01: WSL did not report its state` is long enough
  to run underneath the `Resume` button - the tail of the word "before" is
  visible as `efre` peeking out from behind the button, i.e. the status
  label (`.pack(side='left')`, no fixed width) and the button bar
  (`.pack(side='right')`) overlap rather than wrap or truncate
  (`gui/run_browser.py`'s `bar = ctk.CTkFrame(...)`; `self.status =
  ctk.CTkLabel(bar, ...); self.status.pack(side='left')`).
- **Qt** (`screenshots_qt/07_run_browser_synthetic_refused.png`, dialog at
  900x460 also): the equivalent message is simply clipped mid-word - `not
  resuming 20260101-0000` - with no overlap (the status `QLabel` has stretch
  factor 1 in `bar.addWidget(self.status, 1)`, `run_browser.py:87`, so Qt's
  layout keeps it from drawing under the buttons, but the label itself
  clips instead of eliding or wrapping).
- Reproduced at the dialog's default size too (760x420,
  `FoamRunBrowser.__init__`'s own `self.resize(760, 420)` / `self.geometry
  ('760x420')`), which is narrower still, so the real-run screenshots
  (`04_run_browser_real_listing.png`, `06_run_browser_real_listing.png`)
  don't show it only because their status text (`"10 runs, 426.8 GB
  total"`) happens to be short - a longer real run name or a longer refusal
  reason would trigger the same overlap/clip in ordinary use, not just this
  script's fabricated long run names.
- Not investigated further (out of scope - no app code was touched); flagged
  for a future session with the budget to fix the status bar's width
  allocation in both `run_browser.py` files.

## 5. Numbers check - native 1D, GUI vs `solve_1d()` direct (both GUIs)

`Case1D(radius_m=2.0, charge_kg=1.0, cell_size_m=0.005, gauge_radii=[0.5,
1.0], n_snapshots=3)` - the same case every earlier phase used - run through
the real Setup -> Run -> Results flow in both GUIs (native, 1.1-1.5 s wall
through the GUI worker), compared against `solve_1d(case, RunHooks())` called
directly and summarised with `output.gauge_summary.summarize_gauges` +
`table_rows` - the same functions the Results table itself calls.

| Gauge | Peak [kPa] | Arrival [ms] | t peak [ms] | Pos. phase [ms] | Pos. imp [Pa·s] | Net imp [Pa·s] | Phase ended |
|---|---|---|---|---|---|---|---|
| G1 r=0.502 m | 3412.8 | 0.152 | 0.165 | 0.078 | 138.12 | 31.19 | yes |
| G2 r=0.998 m | 934.0 | 0.485 | 0.511 | 0.692 | 137.36 | 123.43 | yes |

**String-identical** across all four sources checked - the Qt Results table,
the Tk Results table, and each GUI's own direct `solve_1d()` call - for every
one of the 14 values, peak/arrival/impulse all checked, never peak alone, per
CLAUDE.md's measurement discipline note. **Matches phase 6/7/8's own numbers
for the identical case exactly.** Confirms phase 9's diff (imports/docstrings
only, nowhere near the solver or the Results-panel numeric path) changed no
displayed digit, as its own commit messages claim ("no behaviour change").

## 6. What the run browsers showed

Both GUIs, listing the **same real** `/root/blastlab_runs` (read-only,
`default_lister`/`default_sizer` over the WSL 9p mount):

| Run | Dim | Size | Started | State |
|---|---|---|---|---|
| 20260924-195414_2d_p39324-00 | 2D | 29.8 KB | 2026-09-24 19:54:14 | finished |
| 20260923-195308_3d_p31468-00 | 3D | 173.0 GB | 2026-09-23 19:53:08 | finished |
| 20260922-132259_3d_p3756-00 | 3D | 191.6 GB | 2026-09-22 13:22:59 | finished |
| 20260922-011030_3d_p39152-01 | 3D | 53.9 GB | 2026-09-22 01:10:30 | finished |
| 20260922-005601_3d_p39152-00 | 3D | 2.3 GB | 2026-09-22 00:56:01 | finished |
| 20260921-235453_3d_p18960-00 | 3D | 6.0 GB | 2026-09-21 23:54:53 | finished |
| 20260921-234628_3d_p36304-01 | 3D | 4.6 MB | 2026-09-21 23:46:28 | finished |
| 20260921-234255_3d_p36304-00 | 3D | 4.9 MB | 2026-09-21 23:42:55 | finished |
| 20260921-215034_3d_p27908-01 | 3D | 4.6 MB | 2026-09-21 21:50:34 | finished |
| 20260921-214703_3d_p27908-00 | 3D | 4.9 MB | 2026-09-21 21:47:03 | finished |

Identical row-for-row between Qt (`qt_session.json` `real_run_rows`) and Tk
(`tk_session.json` `real_run_rows`) - same names, dims, sizes, timestamps,
states (`10 runs, 426.8 GB total` in both status lines). **All 10 real runs
report `alive=False` ("finished")**, so this session never had a live/unknown
real run to test a refusal against without fabricating one - the synthetic
row test (§2 items 5/11) covers that path safely instead. The first run in
the list (`20260924-195414_2d_p39324-00`) was selected in both GUIs and its
row read back correctly (`picked_row`/`picked_row_alive_col` matches the
table exactly) - **Resume and Delete were never clicked on any real run**.

`python -m blastlab --load-foam-run 20260921-214703_3d_p27908-00` (headless,
no GUI, exits after printing - the safest possible read of this data):

```
[postmortem] \\wsl.localhost\Ubuntu\root\blastlab_runs\20260921-214703_3d_p27908-00: 1 written frames
Done. 0 solver steps, t_final = 10.000 ms
Stopped: loaded post-mortem (1 frames)
[note] the run was stopped before its end time, so the last few gauge
       samples may be missing ...
Loaded 3D result from \\wsl.localhost\Ubuntu\root\blastlab_runs\20260921-214703_3d_p27908-00
Snapshots : 1  (t = 10.000 ms (final)...)
Gauges    : 4
Peak maps : foam-fo
```

No traceback, no delete, no resume; `/root/blastlab_runs` held the same 10
runs after this command as before.

## 7. Import-sanity detail (the exact phase 9 edges)

`import_sanity.py`, 17/17 PASS - the direct, no-GUI test of what the commits
actually changed:

- `services.foam_runs.dims_from_case_json`/`list_runs`/`load_run` are
  literally the same objects as `solvers.foam.runs`/`postmortem`'s own -
  confirmed by `is` identity, not just equal values.
- `ui.app.MainWindow._resume_foam_run`'s source (`inspect.getsource`)
  contains `from ..services.foam_runs import dims_from_case_json` and no
  longer contains `gui.run_browser` anywhere - the exact fallback the commit
  says it removed.
- `core.assessment.ValidationReport` is `models.result.ValidationReport`,
  and the `core.case` shim still resolves to the identical class - so any
  code still importing `ValidationReport` from `core.case` (if any remains)
  is unaffected.
- `solvers.foam.backend.part_counts`/`rd_scalar` are the identical objects
  as `solvers.foam.common`'s; `runloop.py`'s own source contains no
  `backend` import anywhere - the cycle break is real, not just claimed.
- `gui.mode`/`gui.settings`/`gui.worker` (docstring-only this phase) still
  resolve to the exact same `core.mode`/`core.settings`/`solvers.worker`
  objects - the wording change carries no behavioural risk.

## 8. Harnesses - a scope decision, not a gap

`_qa_ui_harness.py --list` / `_qa_gui_harness.py --list` were read (62 and 58
pending scenarios respectively). The task asked specifically for
**run-browser scenarios**, excluding blastFoam-solve scenarios (`F*`). The
**only** run-browser scenario in either harness is `F09` ("The run browser:
list, Load (post-mortem == live), Delete" / "Run browser: list, Load
(post-mortem == live), duplicate, Delete") - it is itself an `F` scenario
(runs a real blastFoam solve first, then Deletes the resulting run), so it is
excluded by the same "skip F*" rule that excludes every other blastFoam-solve
scenario. **No non-F run-browser scenario exists in either harness.**

Given that, and given phase 9's diff is imports/docstrings only (no widget
code, no Setup/Run/Results behaviour touched beyond the two import lines
already covered end-to-end in §2 items 1/4-6/10-11), this session did **not**
replicate phase 8's full D01/D02/D04/E01-E09 battery (12/12 + 12/12 there).
That coverage is unrelated to what changed this phase and would have added
roughly two D04 native-3D runs (330-777 s each historically) for scenarios
that touch none of the eleven files in the phase 9 diff. **Pass/fail counts
for the D+E battery: N/A this session (not run) - not comparable to phase
8's 12/12 (Qt, 1 known D02 flake) / 12/12 (Tk, 0 findings).** If a future
session wants that coverage restored, `D01,D02,D04,E01..E09` with
`--solver native` is the same invocation phase 6/8 used.

`python -u test_regression.py`: **PASS - 8/8**, byte-identical/array-equal to
the frozen baseline - identical to every earlier phase's own comparison. This
suite exercises the native solvers directly and never touches the run
browser or the import edges phase 9 changed, so an unchanged result was
expected; run because the task asked for it.

## 9. Suspected engineering errors (not investigated, per task scope)

Reproduced, unchanged, from earlier sessions' own record
(`docs/ENGINEERING_QUESTIONS.md`, "2026-09-25 - `/refactor` phase 8"):

1. **The 1D field title still says "kg TNT" for an idealGas case**:
   `screenshots_qt/03_1d_results.png` / `screenshots_tk/05_1d_results.png`
   both title as `"1D Spherical Blast - 1.0 kg TNT - EOS: idealGas"` - the
   already-tracked UX-E1. Not investigated further, per task scope.

No new suspected engineering error was noticed in this session.

## 10. Cleanup

Every `QApplication`/`MainWindow`/Tk `root` built by this session's scripts
was closed (`win.close()` / `root.destroy()`) before its script exited; the
`--load-foam-run` and `test_regression.py` subprocesses exited on their own.
`Get-Process python*` was empty before the session and empty after every
command, including the two GUI sessions and the two subprocess runs.
`env.auto_cleanup(...)` was never called (every script's settings guard was
verified `False` before building anything). `/root/blastlab_runs` held the
same 10 runs, 426.8 GB, at the start and the end of the session - nothing was
resumed, deleted, or newly written there; the one real WSL command beyond
listing was `python -m blastlab --load-foam-run <dir>`, which is documented
read-only (`solvers/foam/cli_run.py:load_and_report`) and was confirmed not
to change the run count. No file under `~\Desktop` was touched. Helper
scripts lived only under this task's scratchpad
(`...\scratchpad\qa-p9\`: `common.py`, `import_sanity.py`, `qt_session.py`,
`tk_session.py`). No `blastlab` application file was edited; no git command
that changes anything was run (only reads: `git show`, `git log` were used
earlier in the session to see the phase 9 diff). Bulky output (the two
sessions' full JSON summaries, `test_regression.log`) lives under
`C:\Users\rotem.ofek\blastlab_qa\20260925-phase9\`, not under `docs/qa/`; only
the 8 Qt + 9 Tk screenshots and this report are under
`docs/qa/2026-09-25-phase9/`.
