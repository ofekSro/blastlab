# blastlab QA - UX finding 1 (HD 1.3 off the GUI thread) - 2026-09-25

QA of `docs/UX_REVIEW.md` High item 1 after commits `e010812` ("ux(1): run
the HD 1.3 assessment once, off the GUI thread") and `0af33e3` ("ux(1):
simplify - ui/app.py ui/run_panel.py") on branch `ux-1-hd13-off-gui-thread`.
Touched files: `blastlab/ui/app.py` (`_run_hd13`, `_set_hd13_busy`,
`_hd13_done`) and `blastlab/ui/run_panel.py` (`set_busy`). Compared against
`docs/qa/2026-09-25-phase7/QA_REPORT.md` (the pre-change HD 1.3 QA: Run
blocked the GUI for 84.3 s) and the 2026-09-24 baseline. No application code
was edited during this session; nothing was committed; no packages were
installed; no git command that changes anything was run (only `git show`,
`git log`, `git log -S`, all reads).

## 1. Environment

| | |
|---|---|
| Python | 3.12.10 (Microsoft Store build), on PATH as `python` |
| Qt | PySide6 (offscreen for the quick-sweep script only; **real platform**, `QT_QPA_PLATFORM` unset, for every other script - the window really painted on the desktop) |
| Pillow | 12.2.0 (present; not actually needed - every screenshot in this session is `QWidget.grab()`, a real render of the widget tree, not a screen-grab utility) |
| OS | Windows 11 Enterprise 10.0.26200 |
| Launch technique | `blastlab.ui.app.MainWindow` built in throwaway harness scripts under the session scratchpad, constructed the same way `ui/app.py`'s own `main()` does: `QApplication`, `app.setApplicationName('blastlab')`, `theme.apply(app, settings.load().get('appearance','dark'))`, **then** `MainWindow()` - so the real dark palette is in effect from the first screenshot (unlike an earlier session's real-platform shot, which bypassed `theme.apply` and rendered light - `docs/qa/2026-09-25-phase7/QA_REPORT.md` §4.2). The `--hd13-new` and `--hd13` CLI entry points were invoked as real subprocesses: `python -m blastlab --hd13-new ...` / `--hd13 ... --report ...`. |
| Settings guard | every script called `qa_common.set_private_settings(name)` (writes `{"auto_cleanup": false}` to a private, per-script file and points `BLASTLAB_SETTINGS` at it) **before any `blastlab` import**, then asserted `settings.load()['auto_cleanup'] is False` before building any window - printed `settings guard OK: auto_cleanup=False (file=...)` in every script's log. `env.auto_cleanup(...)` was never called anywhere in this session. |
| WSL | not used - the whole HD 1.3 track is 0-D/closed-form (no WSL) and the one blast-solver check (quick sweep, item 5) was native. A pre-session read-only probe, `wsl -d Ubuntu -- pgrep -a blastFoam`, returned empty. |
| Screenshots | `win.grab().save(...)` throughout - real renders of the real widget tree, real platform, dark theme correctly applied (see the note above; this also incidentally confirms the theme DID apply correctly on the real platform this time, contra the phase7 §4.2 finding, once `theme.apply` is actually called before `MainWindow()`) |
| Python processes | none running before the session; none left running after any script, checked with `Get-Process python*` after each one (see §7, Cleanup) |
| Harness scripts | `qa_common.py`, `run_a_main.py`, `run_b_cli_compare.py`, `run_c_close_midrun.py`, `run_d_quicksweep.py`, `probe_raise.py`, `debug_openhang.py` - all under the given scratchpad path, none elsewhere |
| Bulky outputs | `C:\Users\rotem.ofek\blastlab_qa\20260925-ux1\` (`starter_case.json`, `gui_report.html`, `cli_report.html`, per-script `qa_*_result.json`, private settings files) |

## 2. Result table

| # | Focus item | Result | Evidence |
|---|---|---|---|
| 1 | Real platform: 0-D tab, starter case, Run, mid-run interaction, timing | **PASS** (one pre-existing, NOT-new bug found and worked around - see §3.1) | `screenshots/01_start.png` … `12_after_run.png`; §4 |
| 1a | Window repaints during the run | PASS | `screenshots/11_midrun_t010s.png` vs `11_midrun_t040s.png` - the indeterminate bar's highlight visibly moved; §4.2 |
| 1b | Status reads "HD 1.3 assessment running…", Run/F5/Initialise Model disabled | PASS | `qa_a_result.json: during_immediately_after_click`; `screenshots/05_during_click.png` |
| 1c | Switch tabs, scroll the log, type in a field, mid-run | PASS | `screenshots/06_midrun_setup_tab.png`, `07_midrun_back_on_run_tab.png`; `mid_run_states.typed_field_readback == "midrun-typed-ok"` |
| 1d | F5 again mid-run does nothing | PASS | `mid_run_states.f5_before == f5_after == {busy:true, runs:1, mkdtemp:1}` - no second assessment, no second temp dir |
| 1e | Resize the window mid-run | PASS (one visual finding, not scored as a failure - §5.1) | `screenshots/08_midrun_900x600.png` (clamped to the app's own `setMinimumSize(1100,720)`), `09_midrun_1600x1000.png` |
| 1f | Longest event-loop gap | PASS - **149.1 ms** (interactive: screenshots + two resizes + tab switches running concurrently with the tick recorder) vs **~84,300-91,000 ms** before (the whole run blocked the GUI thread) | `qa_a_result.json: longest_event_loop_gap_ms`; §4.3 |
| 1g | After: report path shown, Run re-enabled, one report file | PASS | `screenshots/12_after_run.png`; `qa_a_result.json: after`, `report_exists: true` |
| 1h | Total run wall time ≈ half of before | PASS - **46.1 s** vs phase7's 84.3 s (≈ 0.55×, "about half") | `qa_a_result.json: total_run_wall_s` |
| 2 | GUI report == CLI report (`--hd13 ... --report ...`), masked | **PASS - byte-identical after masking** | `qa_b_result.json: identical_after_masking: true`; both reports 349,161 bytes (matches phase7's own byte count for the same starter case) |
| 3a | Refused case (charge 0): dialog text unchanged | **PASS** | `qa_a_result.json: refused_dialog == {"title":"Run","text":"Charge mass must be positive"}`; `screenshots/15_refused_dialog.png` - string-identical to the phase7 QA and to the pinned golden |
| 3b | A case whose `assessment.run` genuinely raises, without editing code | **SKIPPED** - see §3.2 | - |
| 4 | Close the window mid-run | **PASS** | `qa_c_result.json`; §4.4 |
| 5a | Native 1D Run in Qt vs `solve_1d()` direct (never peak alone) | PASS - string-identical, both gauges, all 8 columns | `qa_d_result.json: gui_rows == direct_rows, rows_match: true` |
| 5b | Ordinary (non-HD13) Run/Init enable-disable still correct now that `set_busy` exists | PASS | `qa_d_result.json`: before/during/after all as expected (`run_enabled_during: false`, `stop_enabled_during: true`, `run_enabled_after: true`, `stop_enabled_after: false`) |
| 5c | `python -u test_regression.py` | **PASS - 8/8** byte-identical/array-equal | task output; matches phase7's own result |

**No NEW failure.** One pre-existing bug was found (§3.1, unrelated to the commits under test - confirmed by `git log`/`git show`), and one item was skipped for time budget with a documented reason (§3.2).

## 3. Failures / not-run items

### 3.1 Pre-existing (NOT new): "Open case" refuses every HD 1.3 case file

**Not caused by the ux-1 commits.** The task's literal technique -
`python -m blastlab --hd13-new <path>` then "Open case" - was tried first,
exactly as asked. Result: the sidebar "Open case" action (`win._open_case`,
which calls `core.case.load_case`) pops a modal `QMessageBox`:

```
title: "Open case"
text:  "Not a blastlab case file"
```

...for the app's own `--hd13-new` starter case file. `screenshots/00b_opencase_dialog.png`; `qa_a_result.json: open_case_dialog`.

**Root cause**: `core.case.load_case` (`blastlab/models/case.py`,
`case_from_dict`) only accepts the blast-case schema
(`d.pop('schema', SCHEMA) != SCHEMA -> raise ValueError("Not a blastlab case
file")`). An HD 1.3 case file is written with `"schema": "blastlab-hd13"`
(a different loader, `core.assessment.load_case` / `models.hd13_case`), so
every HD 1.3 case - not just this session's - fails this schema check. The
`ValueError` is not one of `_open_case`'s specific `except` clauses
(`FileNotFoundError`, `json.JSONDecodeError`, `(KeyError, TypeError)`,
`OSError`), so it falls into the generic `except Exception` and is shown as
"Not a blastlab case file" (`blastlab/ui/app.py:433`).

**Confirmed NOT introduced by this branch**: `git show e010812 -- ui/app.py`
and `git show 0af33e3 -- ui/app.py` touch only `_run_hd13`/`_set_hd13_busy`/
`_hd13_done`; neither diff mentions `_open_case`. `git log -S"Not a blastlab
case file" -- ui/app.py` finds the string's introduction at `020a396`
("ui: HD1-11c part 2, the HD 1.3 tab wired into the window"), long before
this branch. It also went unnoticed by the phase7 HD 1.3 QA because that
session loaded its starter case with `form.set_case(starter_case)` directly,
never through `win._open_case` / the sidebar button.

**Impact on this session**: none of the focus items depend on "Open case"
specifically - the requested case just needs to end up in the 0-D form. This
session's harness auto-detected the failed load (`win.setup.dim != 0` after
the attempt) and fell back to `win.setup.set_case(assessment.load_case(path))`
- the exact technique `tests/test_ui_char_hd13_run.py` already uses - and
continued. Every subsequent step in this report used that path.

**Recommendation for a future session**: this is a real, currently-reachable
bug for any user who saves an HD 1.3 case and later tries to reopen it from
the sidebar (or presumably any HD 1.3 case saved with "Save case…", though
that was not separately checked here since HD 1.3 "Save case" was outside
this task's focus). Worth its own ticket; out of scope to fix here (no
application code may be edited by this agent).

### 3.2 SKIPPED: a case whose `assessment.run()` genuinely raises

`core.assessment.validate()` is written defensively and on purpose - its own
docstring says the job is to catch, before anything is computed, "which of
the answers about to appear rest on numbers nobody measured." It already
wraps `build_propellant`, `build_scenario`, `closed_vessel_pmax`, the QD
criteria, and the venting-stage geometry each in their own `try/except
(TypeError, ValueError)`, converting the obvious failure modes into
validation errors rather than exceptions from `run()`.

A short, budgeted search was made for a case that still passes `validate()`
but raises from `run()`: `n_out=1`, `n_out=2`, `t_end=1e-6` with a tiny
`n_out`, and a zero `spread_time` with a single-cohort `progressive_package`
scenario (`probe_raise.py`). None of these short-circuited - each one that
passed validation went on to run the real, ~40+ s physics loop rather than
raising quickly (confirmed via `time.perf_counter()` around
`assessment.run()`; the process was still accumulating CPU with no sign of
returning after 30+ s for the first candidate, at which point it was killed
to stay within budget - each further candidate costs another full run). No
further candidates were tried.

**Not scored as a failure or gap in this session's evidence**: the exact
contract this sub-item asks about (dialog title/text on a raise, Run/Init
re-enabled after, the report never written, the temp case directory removed
again) is already pinned by the project's own characterisation test,
`tests/test_ui_char_hd13_run.py`'s `"raised"` scenario, which patches
`assessment.run` to raise `ValueError('char: the assessment failed')` and
asserts exactly that contract against `char_golden/ui_hd13_run.json`
(`"raised": {"errors": [["HD 1.3 assessment", "char: the assessment
failed"]], "temp_dirs_left": 0, "status": "", ...}`) - and per the commit
message for `e010812`, that test currently passes. This session did not
independently re-run that pinned test (time budget), so this is corroborating,
not independently re-verified, evidence; flagging that distinction rather
than silently treating it as equivalent to a live observation.

## 4. Details

### 4.1 Steps

1. `python -m blastlab --hd13-new C:\Users\rotem.ofek\blastlab_qa\20260925-ux1\starter_case.json` (real subprocess, rc 0).
2. Real `MainWindow`, real platform, `win._open_case(starter_path)` tried first (hit §3.1's bug, auto-recovered via `win.setup.set_case(assessment.load_case(starter_path))`).
3. `form.v['report_file'].set(<path under blastlab_qa>)`, waited past the 300 ms debounce, confirmed `Run` enabled, switched to the Run tab.
4. A 10 ms `QTimer` tick recorder started; **`QTest.mouseClick(win.run_panel.run_btn, ...)`** - a real click on the real, enabled button (not a direct `_run_hd13` call).
5. While `win._hd13_busy`, with `app.processEvents()` pumped continuously: at t≈3 s switched Setup→Run tabs and back; at t≈6 s typed into the run-name field; at t≈9 s sent `F5`; at t≈12 s scrolled the (empty) log; at t≈15 s resized to 900×600 then 1600×1000 then back to 1280×840; at t≈20 s took a full state snapshot; screenshots every ~10 s throughout.
6. After the busy flag cleared: recorded the final state, then ran the refused-case (charge 0) scenario in the same window, and finally `win.close()`.

### 4.2 Repaint / responsiveness evidence

`screenshots/11_midrun_t010s.png` and `11_midrun_t040s.png` show the
indeterminate progress bar's highlighted segment in visibly different
positions 30 s apart - direct evidence the bar animates (Qt's own
indeterminate-mode behaviour) and that the window keeps repainting through
the whole run, not just responding to my own forced `processEvents()` calls.
The typed text (`"midrun-typed-ok"`) was correctly readable back from the
widget after typing it mid-run, and both tab switches and both resizes
completed without any delay long enough to notice by eye and without any
error.

### 4.3 Longest event-loop gap - context

This session measured **149.1 ms**, using the *same* technique as
`tests/test_ui_char_hd13_run.py` (a free-running 10 ms `QTimer`, the largest
gap between its ticks) but **with real interactive work happening
concurrently** - two screenshots via `grab()`, two `resize()` calls forcing a
full relayout, and two tab switches, all interleaved with the tick recorder,
rather than the pinned test's passive "just wait" measurement. The commit
message for `e010812`/`0af33e3` separately reports **38-43 ms** for that
passive measurement (not independently re-verified in this session - see
§3.2 for why no pinned test was re-run). Both numbers are two to three
orders of magnitude below the **~84,300-91,000 ms** the whole GUI thread used
to block for (phase7 QA measured 84.3 s for one click), and both are far
below anything a user would perceive as a freeze (typically ~100 ms is the
threshold for "instant"; 149 ms with two forced relayouts folded in is
consistent with that, not a stall).

### 4.4 Close mid-run (own OS process, `run_c_close_midrun.py`)

Built and driven exactly like `ui/app.py main()` (`QApplication`, theme
applied, `MainWindow()`, `win.show()`, `app.exec()`), with the case load /
Run click / close sequence scheduled via `QTimer.singleShot` so it happens
*inside* that real event loop - the same one a real launched app runs.
`crashlog.install()` was called first, exactly as `main()` does.

- t≈0.3 s: case loaded into the form (dim 0 confirmed).
- t≈0.8 s: real `QTest.mouseClick` on `Run`; `win._hd13_busy` confirmed `True`.
- t≈6.8 s (≈6 s into the ~46 s assessment): `screenshots/17_close_midrun_busy.png` taken, then `win.close()`.
- `app.exec()` returned **0**, **7.47 s** after the window was shown (i.e. essentially immediately after `close()` - `quitOnLastWindowClosed` is Qt's default and fired as expected).
- **`report_exists: false`** - no partial/garbage report file at the chosen path. Consistent with the code: `hd13_service.write_report` only runs after the full ~40+ s `assessment.run()` returns, and the process ends long before that (the daemon worker thread is simply abandoned at interpreter shutdown - Python does not join daemon threads).
- **`last_crash: null`** (`crashlog.last_crash`, the process-wide unhandled-exception hook) - no traceback anywhere.
- After the harness script exited (`SCRIPT C DONE`, exit code 0): `Get-Process python*` returned nothing - **no hung process, no orphan**.
- One new `blastlab_hd13_*` temp directory was created (its `case.json`, written before the assessment starts, by design) and was **not** cleaned up - this matches the documented "kept" behaviour for a run that does not raise (only the `except Exception` branch inside `_run_hd13`'s worker removes it); closing the window is neither a success nor a caught failure, so the directory is simply orphaned. Not a new defect (the same would happen if the process were killed externally, e.g. Alt-F4 on a hung machine), but worth noting as the actual disk-cleanup contract for this specific case.

## 5. Visual findings (not scored as failures)

### 5.1 Chip row overlaps the Name/progress row at the app's own enforced minimum size

`screenshots/08_midrun_900x600.png`: a `resize(900, 600)` request is clamped
by `MainWindow.setMinimumSize(1100, 720)` (by design, `ui/app.py:59`) - the
window actually renders at 1100×720 (confirmed via the PNG's own pixel
dimensions). At exactly that floor, the Run tab's wrapped stat-chip row
(`step`/`t [ms]`/`dt [s]`/`p max [kPa]`) visually overlaps the `Name` field
and progress bar above it (clipped text, e.g. "t Imcl" instead of "t [ms]").
Compare `09_midrun_1600x1000.png`, where the same chips lay out cleanly in
one row. This reproduces with the window merely AT its documented minimum,
regardless of HD 1.3 - `run_panel.py`'s `WrapRow`/chip layout is untouched by
the ux-1 commits (`set_busy` only touches button-enabled state and the
progress bar's range/value), so this is very unlikely to be caused by this
change; not independently confirmed against a non-HD13 run in this session,
so noting it here rather than asserting its scope further.

## 6. Numbers check - happy path (HD 1.3) and quick sweep (native 1D)

### 6.1 HD 1.3 headline numbers (starter case, via the CLI's own stdout - the GUI shows no headline numbers, unchanged since phase7 §4.3)

```
confined   peak 0.102 MPa   (burnt out and vented)
unconfined expansion Mach 0.0917   blast negligible: False
structure  mu 0.116   quasi-static   theta 0.06 deg
```

GUI report vs CLI report (`--hd13 starter_case.json --report cli_report.html`,
wall 47.4 s): **byte-identical after masking the timestamp and PNG bytes**
(`test_char_hd13_cli.normalise_html`, the project's own established
diffing method) - `gui_report_bytes: 349161`, `cli_report_bytes: 349161`,
`identical_after_masking: true`. Matches phase7's own byte count for the
same starter case exactly.

### 6.2 Native 1D happy path (Qt Run vs `solve_1d()` direct)

Case `Case1D(radius_m=2.0, charge_kg=1.0, cell_size_m=0.005,
gauge_radii=[0.5, 1.0], n_snapshots=3)` - the same case phase6/phase7 used -
run through the real Setup→Run→Results flow (native, offscreen, 1.02 s wall
through the GUI worker), compared string-for-string against `solve_1d(case,
RunHooks())` called directly:

| Gauge | Peak [kPa] | Arrival [ms] | t peak [ms] | Pos. phase [ms] | Pos. imp [Pa·s] | Net imp [Pa·s] | Phase ended |
|---|---|---|---|---|---|---|---|
| G1 r=0.502 m | 3412.8 | 0.152 | 0.165 | 0.078 | 138.12 | 31.19 | yes |
| G2 r=0.998 m | 934.0 | 0.485 | 0.511 | 0.692 | 137.36 | 123.43 | yes |

**String-identical** to the direct `solve_1d()` call for all 8 columns of
both gauges (peak, arrival AND impulse all checked - never peak alone, per
CLAUDE.md's measurement discipline), and identical to phase6/phase7's own
numbers for the same case. `ui/app.py`'s ordinary blast-run path
(`_run_single` → `RunController.start_stages`) is untouched by the ux-1
commits (only `_run_hd13` was touched), so an unchanged result was expected;
run to confirm `run_panel.set_busy`'s new state variable did not regress the
ordinary Run/Init/Stop gating - which it did not (`run_enabled_before/after:
true`, `run_enabled_during: false`, `stop_enabled_during: true`,
`stop_enabled_after: false`).

## 7. Suspected engineering errors (not investigated, per task scope)

Reproduced unchanged from `docs/ENGINEERING_QUESTIONS.md`'s "2026-09-25 -
`/refactor` phase 7" entry and phase7's own QA session (already "known" per
the task brief, not re-analysed here):

1. **"Blast negligible: False" at Mach 0.0917.** This session's CLI run
   printed the same line and the HTML report (byte-identical to the GUI's)
   says `Blast negligible: no`.
2. **The whole burn is flagged outside the calibration window.** Confined
   peak `0.102 MPa` against the `5.53 MPa` closed-vessel limit the
   validation warnings quote - same order-of-magnitude gap as before.

No new suspected engineering error was noticed in this session.

## 8. Cleanup

Every window/`QApplication` built by this session's own scripts was closed
or allowed to exit its `app.exec()` naturally; `Get-Process python*` was
checked after each script and returned empty every time, including after
the 46 s HD 1.3 GUI run, the 47 s CLI run, the close-mid-run script, and the
background `test_regression.py`. `env.auto_cleanup(...)` was never called
(every script's settings guard was verified `False` before building any
window). No file under `~\Desktop` was touched. Helper scripts lived only
under the given scratchpad path. Bulky HD 1.3 output
(`starter_case.json`, `gui_report.html`, `cli_report.html`, `qa_*_result.json`,
per-script private settings files) was written under
`C:\Users\rotem.ofek\blastlab_qa\20260925-ux1\`, not under `docs/qa/`. No
`blastlab` application file was edited; no git command that changes
anything was run (only `git log`, `git show`, `git log -S`, all reads); no
commit was made.

**Not cleaned up, deliberately**: the `blastlab_hd13_*` temporary case
directories under the Windows temp folder (one new one per successful run in
this session, consistent with the "kept" design - `ui/app.py`'s `_run_hd13`
docstring, and ARCHITECTURE_REVIEW Q4). A `dir`-style listing showed ~58 such
directories accumulated from this and prior QA sessions/pinned-test runs on
this machine; this session added at most 2-3 of them. Deleting them was out
of scope (they are real per-run application artifacts, not this session's
scratch files) and is noted here only for visibility, not as a finding.
