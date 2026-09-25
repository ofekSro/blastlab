# blastlab QA - phase 7 - 2026-09-25

Post-phase QA after refactor Phase 7 (`docs/ARCHITECTURE_REVIEW.md` section 5,
Phase 7; commits `e52b1c6` "test(phase 7): pin the HD 1.3 CLI and the Qt HD 1.3
Run before the move", `61ab709` "refactor(phase 7): services/hd13.py - the
HD 1.3 assessment as a service", `59de071` "simplify(phase 7): services/hd13.py
output/cli_hd13.py ui/app.py tests/test_char_hd13_cli.py
tests/test_ui_char_hd13_run.py" on branch `arch-p7-hd13-service`). The HD 1.3
orchestration (validate -> run -> figures -> write) moved out of
`output/cli_hd13.py` into `blastlab/services/hd13.py`; both
`output/cli_hd13.run_and_report` (the CLI) and `ui/app.py`'s `_run_hd13`
(the Qt 0-D tab's Run button) now call the service. **The only GUI file
touched by this phase is `ui/app.py` (`_run_hd13` only).** No application
code was edited during this QA session. Compared throughout against
`docs/qa/2026-09-24-baseline/QA_REPORT.md`, `docs/qa/2026-09-25-phase5a/`,
`-phase5b/` and `-phase6/QA_REPORT.md`.

## 1. Environment

| | |
|---|---|
| Python | 3.12.10 (Microsoft Store build), on PATH as `python` |
| Qt | PySide6 6.11.2 (offscreen, `blastlab.ui.testing.ensure_qapp()`, for the scripted HD 1.3/1D walkthroughs and the refusal dialog; real platform, `QT_QPA_PLATFORM` unset, for the startup sanity shot) |
| Pillow | 12.2.0 |
| OS | Windows 11 Enterprise 10.0.26200 |
| Launch | `blastlab.ui.app.MainWindow` built directly in throwaway harness scripts under the session scratchpad (`...\scratchpad\qa-p7\`: `fast_qa.py`, `hd13_real_run.py`, `realplatform_start.py`, plus `debug_*.py` diagnostics used only to root-cause a script issue of my own, see §4.1), and the project's own `blastlab/tests/test_char_hd13_cli.py`, `test_ui_char_hd13_run.py`, `test_hd13_report.py`, `test_assessment.py`, `test_regression.py` run unmodified as subprocesses |
| Settings guard | every process set `BLASTLAB_SETTINGS` to a private file **before** any `blastlab` import, and asserted `settings.load()['auto_cleanup'] is False` before building any window (printed `settings guard OK: auto_cleanup=False` in every one of my own scripts). The pinned test files use `char_common`'s own private-settings guard (read, not modified). `env.auto_cleanup(...)` was never called anywhere. |
| Screen capture | offscreen `QWidget.grab()` for scripted work; the real-platform startup shot used `PIL.ImageGrab` first (failed: `"screen grab failed"`, the same environment quirk every earlier session in this repo/shell recorded), falling back to Win32 `PrintWindow(hwnd, hdc, PW_RENDERFULLCONTENT)` via `ctypes`, which worked (`PrintWindow result: 1`) |
| WSL | read-only probe only: `wsl -d Ubuntu -- pgrep -a blastFoam` returned empty (exit 1, no matches) before the session. **No WSL solve, no blastFoam run** - the one blast run in this session was native 1D. |
| Solver used for the one blast run | **native only** (`win.set_solver('native')`, asserted `win.solver == 'native'` before the run) |
| Python processes | none running before the session (`Get-Process python*` empty); none left running after (checked repeatedly through the session and at the end) |

## 2. Result table

| # | Item | Result | Evidence | vs. earlier phases |
|---|---|---|---|---|
| 1 | Startup, offscreen | PASS | `screenshots/01_start_offscreen.png` - title `blastlab 1.0.0`, 1200x800, no traceback | same |
| 1b | Startup, real platform (PrintWindow ground truth) | PASS, functionally; one visual note | `screenshots/00_realplatform_start.png` | see §4.1 (theme-only visual finding, not a new failure) |
| 2 | HD 1.3 (0-D) tab, default state | PASS | `screenshots/02_hd13_tab_default.png` | new focus this phase; renders cleanly, all fields present |
| 3 | HD 1.3 form filled from the starter case (`--hd13-new` writer, loaded via `assessment.load_case`) | PASS | `screenshots/03_hd13_form_filled_from_starter.png`, `10_hd13_ready_to_run.png` | new this phase |
| 4 | HD 1.3 real Run: report path under the QA bulk dir, Run pressed for real, waited for completion | PASS | `screenshots/11_hd13_run_tab_before_click.png`, `12_hd13_after_run.png`; §5 | new this phase - this is the surface Phase 7 touched |
| 5 | GUI-written report vs `python -m blastlab --hd13 <same starter case>` (CLI), byte comparison after masking the timestamp | **PASS - byte-identical** | §5; `C:\Users\rotem.ofek\blastlab_qa\20260925-phase7\gui_report.html` / `cli_report.html`, both 349,161 bytes on disk (349,152 after reading back with universal newlines) | new this phase - the core "no behaviour change" claim of the commits, empirically confirmed |
| 6 | Refused case: charge mass 0 - the dialog text | PASS | `screenshots/04a_hd13_charge0_setup_disabled.png`, `04b_...`, `05_hd13_refused_dialog.png`; §5.2 | matches the pinned golden `char_golden/ui_hd13_run.json` exactly: title `Run`, text `Charge mass must be positive` |
| 7 | Real-platform startup sanity | PASS | `screenshots/00_realplatform_start.png` | same technique as phase5a/6 |
| 8 | Native 1D happy path (small case) vs `solve_1d()` direct | PASS | `screenshots/06_1d_form_filled.png`, `07_1d_run_finished.png`, `08_1d_results_gauges.png`; §6 | **string-identical** to phase 6's own numbers for the same case |
| 9 | Close terminates cleanly | PASS | every script closed its window; no leftover `python` process after any of them | same |
| 10 | `_qa_ui_harness.py` scenarios touching HD 1.3 / 0-D | **N/A - none exist** | `--list` output inspected; `B03` ("Every dimension's form") is the closest match but its source iterates `for d in (1, 2, 3)` only - dim 0 is not exercised by any of the 62 listed scenarios | unchanged from earlier phases (this harness has never had an HD 1.3 scenario) |
| 11 | `test_char_hd13_cli.py` (pinned CLI characterisation, Phase 7's own test) | **PASS - 2/2** | `test_refused_case`, `test_starter_and_report` | new this phase; not run before |
| 12 | `test_ui_char_hd13_run.py` (pinned Qt HD 1.3 Run characterisation, Phase 7's own test) | **PASS - 1/1** | `test_hd13_run` (covers all four sub-scenarios: typed report path, blank report path, refused case, a run that raises) | new this phase; not run before |
| 13 | `test_hd13_report.py` | PASS - 29/29 checks | figure builders, report sections, caveats, uniform-vs-spread wording, bare-run rendering | listed in Phase 7's own verification plan |
| 14 | `test_assessment.py` | PASS - 13/13 checks | venting-stage validation, geometry/opening rules | listed in Phase 7's own verification plan |
| 15 | `python -u test_regression.py` | **PASS - 8/8** | byte-identical/array-equal to the frozen baseline | identical to baseline's, phase5a's, phase5b's and phase6's own comparison |

**No FAILs anywhere in this session.**

## 3. Failures

**None.** No crash, traceback, incorrect displayed number, or wrong file
content was found anywhere in this run (my own scripted plan, the two
Phase-7 pinned characterisation tests, the Phase-7-listed verification
suite, or `test_regression.py`). **No NEW failure vs. the baseline or any
earlier phase report.**

## 4. Visual findings (not scored as failures)

### 4.1 A script-technique pitfall, not an app bug (recorded so a future session doesn't repeat it)

My first two attempts at the "refused case" check produced an EMPTY dialog
capture (`{}` - the patched `show_error` recorder was never called). Root
cause, confirmed with a small diagnostic script
(`debug_refused3/4.py`, kept only under the session scratchpad): typing
`charge_kg = '0'` into the HD 1.3 form correctly fires the SAME live,
debounced validator the blast forms use
(`ui/app.py:_validate`, the `dim == 0` branch, unchanged by this phase) -
`run_panel.set_validation(False, 1)` disables the real `Run` button within
one debounce cycle. `QTest.mouseClick` on a **disabled** `QPushButton` is
correctly a documented Qt no-op (confirmed explicitly: a recorder patched
onto `win.show_error` recorded **zero** calls from that click,
`fast_qa_result.json`'s `click_on_disabled_run_btn_calls: []`). This is
correct, intended app behaviour, not a defect - a real user typing `0` into
Charge sees the Run button grey out and the Setup validation strip show
`Charge mass must be positive` in red (`screenshots/04a_...png`) before
they could ever reach a click. The modal-dialog text pinned by
`test_ui_char_hd13_run.py` (and reproduced here, §5.2, via `win._run_single()`
called directly - the same call the `F5` accelerator or a very fast click
ahead of the 300 ms debounce would make) is a defense-in-depth path, not
the primary one a mouse-driven user hits. Recorded here because it cost
real debugging time; not filed as a product issue.

### 4.2 Real-platform startup renders in a LIGHT palette although "Dark mode" is checked

`screenshots/00_realplatform_start.png` (real platform, ground-truth
`PrintWindow` capture) shows the sidebar's "Dark mode" checkbox in its
checked state, yet the whole window - background, cards, the Setup form -
renders in a light grey/white palette, not the dark palette every offscreen
screenshot in this session and every earlier session's own real-platform
screenshot shows for the same checked state (compare
`screenshots/01_start_offscreen.png`, taken moments earlier in the SAME
session with the SAME fresh private-settings file, which correctly shows
the dark palette). Not re-derived further (theme application lives in
`ui/theme.py`, entirely outside this phase's diff, `ui/app.py`'s
`_run_hd13`); flagging for a follow-up QA session with more budget to
isolate whether it is a genuine real-platform/offscreen QSS-application
difference or an artifact of this particular capture. Not scored as a
phase-7 regression - `ui/theme.py` was not touched by any of the three
phase-7 commits.

### 4.3 The GUI's status line never showed headline numbers - confirmed unchanged, not new

`_run_hd13`'s only user-visible output besides the report file itself is
`self._status.setText(f'HD 1.3 report written: {out}')`
(`screenshots/12_hd13_after_run.png`, bottom status bar) - no peak
pressure, Mach number, ductility or verdict is shown anywhere in the GUI.
Checked against the pre-phase-7 code (`git show 61ab709 -- ui/app.py`):
the call this replaced was `run_and_report(case_path, path, quiet=True)` -
already silent before this phase, since `quiet=True` suppressed the same
`print()` calls that populate the CLI's headline block. **This is
pre-existing behaviour, unaffected by Phase 7**, not a regression. The
headline numbers are only reachable through the CLI's stdout (§5.1) or by
reading the HTML report itself (§5.3), which is exactly what this QA
session's comparison in §5 does.

## 5. The real HD 1.3 Run, GUI vs CLI

### 5.1 Steps and timing

1. Generated the starter case with the real writer
   (`output.cli_hd13.write_starter_case`, the same function
   `--hd13-new` calls) to
   `C:\Users\rotem.ofek\blastlab_qa\20260925-phase7\starter_case.json`.
2. Qt 0-D tab: `form.set_case(starter_case)`, waited for the Run button to
   enable, set the report-path field to
   `C:\Users\rotem.ofek\blastlab_qa\20260925-phase7\gui_report.html`
   (`screenshots/10_hd13_ready_to_run.png`), switched to the Run tab
   (`11_hd13_run_tab_before_click.png`) and clicked the real `Run` button
   (`QTest.mouseClick`).
3. **The click blocked the GUI thread for 84.3 s** - consistent with the
   documented known-and-intended UX debt (`_run_hd13` runs
   `assessment.run` once to fail before touching disk, then
   `services.hd13.assess` runs it again; ~40 s each on this case,
   sensitivity band off; the window is unresponsive for the whole
   interval, exactly as described in the task brief and in
   `ui/app.py:_run_hd13`'s own docstring). After it returned:
   `screenshots/12_hd13_after_run.png` shows the Run button re-enabled,
   `Case OK`, and the status line
   `HD 1.3 report written: C:\Users\rotem.ofek\blastlab_qa\20260925-phase7\gui_report.html`.
   `win._status_timer.isActive()` was `True` (the status-clear timer had
   started, as designed).
4. The CLI was then run, from a subprocess, on the **identical**
   `starter_case.json`:
   `python -m blastlab --hd13 starter_case.json --report cli_report.html`,
   exit code `0`, wall time 44.8 s.
5. `C:\Users\rotem.ofek\blastlab_qa\20260925-phase7\` holds
   `starter_case.json`, `gui_report.html` and `cli_report.html` (bulky
   HD 1.3 artifacts, kept out of `docs/qa/` per the task's instruction).

### 5.2 Refused case: charge mass 0

Steps: HD 1.3 tab, starter case loaded, `Charge [kg]` field set to `0`.
Confirmed via the live validator (§4.1): Run button disables itself, Setup
strip shows `Charge mass must be positive` in red
(`screenshots/04a_hd13_charge0_setup_disabled.png`), Run tab shows
`1 error - see Setup` and a greyed `Run` button
(`04b_hd13_charge0_run_tab_disabled.png`). Calling the exact handler a
real Run press invokes (`win._run_single()`) with a real, on-screen
`QMessageBox` (not a recorder, so it could be screenshotted -
`05_hd13_refused_dialog.png`) gives:

```
title: "Run"
text:  "Charge mass must be positive"
```

**String-identical** to the pinned golden
`blastlab/tests/char_golden/ui_hd13_run.json`'s `"refused"` entry (which
uses `charge_kg=0, t_end=0` together and gets both lines joined by `\n`;
this session's single-field `charge_kg=0` case gets the first line alone,
confirming the join behaviour and the exact wording independently).

### 5.3 Headline numbers - GUI report vs CLI stdout vs CLI report

The CLI's stdout (`_print_headline`, unchanged by this phase) for the
starter case:

```
confined   peak 0.102 MPa   (burnt out and vented)
unconfined expansion Mach 0.0917   blast negligible: False
structure  mu 0.116   quasi-static   theta 0.06 deg
siting     No QD comparison: no coefficients have been entered...
```

Checked against both HTML reports (`gui_report.html`, `cli_report.html`):
`grep`-equivalent search for `0.0917` and `Blast negligible` both hit in
the report body, in the table cell `Blast negligible</td><td>no</td>` -
consistent with the CLI's `blast negligible: False` (`no`/`False` are the
report's and the CLI's own equivalent renderings of the same boolean, not
a discrepancy).

**GUI report vs CLI report, byte comparison** (via
`test_char_hd13_cli.normalise_html` - masks the one timestamp banner line
and replaces inlined base64 PNGs with `<png WxH>` placeholders, the
project's own established diffing method): **`identical_after_masking:
True`**, both files 349,161 bytes on disk. The GUI's Run and the CLI's
`--hd13` on the identical input case produce **byte-identical output**
(after only the timestamp and PNG bytes are masked - the PNGs themselves
were not even byte-different in this run, since the masking only checks
their pixel size, but the underlying figures are drawn from identical
data so this is expected). This directly confirms the commits' own claim
("No behaviour change... the Qt Run path ... match the goldens").

**GUI log/status vs the numbers**: as noted in §4.3, the GUI's status
line carries only the report path, never the headline numbers - so
"matching the GUI log/status" reduces to confirming the file it names was
in fact written with the same content the CLI's own run produces, which
is exactly what the byte comparison above shows.

## 6. Numbers check - native 1D happy path (regression sweep)

Small case (`Case1D(radius_m=2.0, charge_kg=1.0, cell_size_m=0.005,
gauge_radii=[0.5, 1.0], n_snapshots=3)`, the same case phase 6 used), run
through the real Setup -> Run -> Results flow (native, offscreen), 1.41 s
wall through the GUI worker thread, compared against `solve_1d(case,
RunHooks())` called directly:

| Gauge | Peak [kPa] | Arrival [ms] | t peak [ms] | Pos. phase [ms] | Pos. imp [Pa·s] | Net imp [Pa·s] | Phase ended |
|---|---|---|---|---|---|---|---|
| G1 r=0.502 m | 3412.8 | 0.152 | 0.165 | 0.078 | 138.12 | 31.19 | yes |
| G2 r=0.998 m | 934.0 | 0.485 | 0.511 | 0.692 | 137.36 | 123.43 | yes |

**String-identical** between the displayed Results-tab Gauges table
(`win.results.gauges.rows()`) and the direct `solve_1d()` call, for every
one of the 14 values across both gauges - peak, arrival AND impulse all
checked, never peak alone, per CLAUDE.md's measurement discipline note.
**Matches phase 6's own numbers for the identical case exactly**
(`docs/qa/2026-09-25-phase6/QA_REPORT.md` section 6, "1D (native,
`Run 1 - 1D`)" table). `ui/app.py`'s `_run_single`/blast-run path is
untouched by phase 7 (only `_run_hd13` was touched), so an unchanged
result was expected; run because the task asked for a regression sweep.

## 7. Suspected engineering errors (not investigated, per task scope)

Both items already on record in `docs/ENGINEERING_QUESTIONS.md` under
"2026-09-25 - `/refactor` phase 7" were reproduced, unchanged, in this
session's own live run (not merely re-read):

1. **"Blast negligible: False" at Mach 0.0917.** This session's CLI run
   printed `unconfined expansion Mach 0.0917   blast negligible: False`
   and the HTML report (both the GUI's and the CLI's, byte-identical)
   says `Blast negligible: no` - identical to the number on record. A
   Mach number that low reads as though it should count as negligible;
   the threshold/flag logic in the unconfined model was not examined
   further, per task scope.
2. **The whole burn is flagged outside the calibration window.** This
   session's confined peak was `0.102 MPa` (~1 kPa overpressure) against
   the `5.53 MPa` closed-vessel limit the validation warnings quote
   (`Closed-vessel limit p_max = ... = 5.53 MPa`) - the same order of
   magnitude gap already on record. Not investigated further.

No new suspected engineering error was noticed in this session.

## 8. Cleanup

Every window/QApplication built by my own scripts was closed
(`win.close()`) before its script exited; `Get-Process python*` showed
zero processes before the session and zero left running after every
command, including the two long-running ones (the 84.3 s HD 1.3 GUI run
and the background `test_assessment.py`). `env.auto_cleanup(...)` was
never called (every script's settings guard was verified `False` before
building a window; the pinned test files' own guard was read, not
modified). No file under `~\Desktop` was touched. Helper scripts lived
only under the given scratchpad path (`...\scratchpad\qa-p7\`:
`fast_qa.py`, `hd13_real_run.py`, `realplatform_start.py`,
`debug_refused.py`, `debug_refused2.py`, `debug_refused3.py`,
`debug_refused4.py`, `debug_strip.py` - the `debug_*` scripts were pure
diagnostics for my own script's technique, §4.1, not product findings).
No `blastlab` application file was edited; no git command that changes
anything was run (only reads: `git log`, `git show --stat`). Bulky HD 1.3
output (`starter_case.json`, `gui_report.html`, `cli_report.html`) was
written under `C:\Users\rotem.ofek\blastlab_qa\20260925-phase7\`, not
under `docs/qa/`, per the task's instruction.
