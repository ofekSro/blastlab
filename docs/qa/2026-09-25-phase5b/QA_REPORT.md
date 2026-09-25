# blastlab QA - phase 5b - 2026-09-25

Post-phase QA after refactor Phase 5b (`docs/ARCHITECTURE_REVIEW.md` section 5,
finding F4, open question Q1): `blastlab/gui/forms.py`'s `CaseForm.get_case`/
`set_case` (the **Tk** form - CLAUDE.md section 9, the permanent way back) now
call `models.fields.case_from_fields`/`fields_from_case`, the same mapping the
Qt form has used since phase 5a. Commits `ef14a32` (test pin), `1a9ec76`
(the refactor itself), `79b74de` (test tidy-up) on branch `arch-p5a-tk-fields`.
**The only GUI file touched is `blastlab/gui/forms.py`.** No application code
was edited during this session. Compared throughout against
`docs/qa/2026-09-24-baseline/QA_REPORT.md` and
`docs/qa/2026-09-25-phase5a/QA_REPORT.md`.

## 1. Environment

| | |
|---|---|
| Python | 3.12.10 (Microsoft Store build), on PATH as `python` |
| Qt | PySide6 6.11.2 (real platform, `QT_QPA_PLATFORM` unset, for the Qt sanity check) |
| Tk | CustomTkinter, real desktop window (Tk has no offscreen mode) |
| Pillow | 12.2.0 |
| OS | Windows 11 Enterprise 10.0.26200 |
| Launch | `blastlab.gui.app.App` (Tk) and `blastlab.ui.app.MainWindow` (Qt) built directly in throwaway harness scripts under the session scratchpad (`...\scratchpad\qa-p5b\`), plus `blastlab/tests/_qa_gui_harness.py` (the Tk QA driver) run as a subprocess. No `python -m blastlab` subprocess was needed for my own scripts. |
| Settings guard | every process set `BLASTLAB_SETTINGS` to a private file **before** any `blastlab` import, and asserted `settings.load()['auto_cleanup'] is False` before building any window (printed `settings guard OK: auto_cleanup=False` in every script's output). `_qa_gui_harness.py`'s own `main()` writes `auto_cleanup: false` into its `--out` dir's `settings.json` before import, per its source (confirmed by reading it before running). `env.auto_cleanup(...)` was never called anywhere. |
| Screen capture | `ImageGrab` first, falling back to Win32 `PrintWindow(PW_RENDERFULLCONTENT)` via the harness's own `frame_bounds`/`print_window`/`user32` helpers (imported directly from `_qa_gui_harness`, not reimplemented) - every shot in this session actually fell to `printwindow` (lum 38-40), consistent with the baseline/phase-5a note that `ImageGrab.grab()` fails outright in this shell/session. |
| WSL | `wsl -d Ubuntu -- pgrep -a blastFoam` returned empty before the session (no foreign solver); the harness's own kickoff probe also logged `foreign WSL solvers at kickoff: []`. blastFoam mode's read-only hardware/availability probe ran as part of normal UI behaviour (sidebar hint, cell-cap math) in several screenshots - no run and no WSL solve was ever started. |
| Solver used for the one real run | **native only** (`app.set_solver('native')`, asserted `app.solver == 'native'` before the run), per the task's safety rule. |
| Python processes | none running before this session (`Get-Process python` empty); none left running after (`Get-Process python` empty at the end). |

## 2. Result table

| # | Item | Result | Evidence | vs. baseline / phase 5a |
|---|---|---|---|---|
| 1 | Tk startup, real platform | PASS | `01_tk_start.png` - title `blastlab 1.0.0`, no traceback | same |
| 2 | Setup form, 1D/2D/3D x native/blastfoam (6 combinations) | PASS | `02..07_setup_{1,2,3}d_{native,blastfoam}.png` | same layout as baseline/5a; cell-count and blastFoam-note text unchanged |
| 3 | Status-strip cell count (1D, 2D) | PASS | `08_status_2d_native.png`; strip text `~10,000 cells at dx = 0.001 m` (1D), `~143,641 cells at dx = 0.0105424 m` (2D) | **identical numbers** to baseline/5a's own Qt-side numbers for the same default cases |
| 4 | Invalid input: garbage order value, native mode | PASS | `09_order_garbage.png` - `'order' is not a reconstruction order: 'garbageXYZ'`, `form._bad == {'order'}` | **change (2) observed** - see §4 |
| 4b | Invalid input: blank order value, native mode | PASS | `10_order_blank.png` - `'order' is not a reconstruction order: ''`, field marked | change (2), same guard |
| 5 | blastFoam mode: order/eos boxes ignored | PASS | `11_blastfoam_order_eos_ignored.png` - boxes hold `2 (MUSCL)`/`JWL`, `case.order == 1`, `case.eos == 'idealGas'` | **change (1) observed** - see §4 |
| 6 | gauge_file: empty box -> `None`; `None` -> empty box | PASS | `12_gauge_file_none_roundtrip.png` - box renders empty, not the string `'None'` | **change (3) observed** - see §4 |
| 7 | Save case -> Open case round trip, 1D | PASS | `13_after_open_1d.png`; `tk_case1d_a.json` byte-identical to `tk_case1d_c.json`; all compared dataclass fields equal | same behaviour as baseline (5a checked byte-identity for the Qt form; this session checks it for the Tk form for the first time) |
| 8 | Save case -> Open case round trip, 2D (obstacles + gauges) | PASS | `14_after_open_2d.png`; `tk_case2d_a.json` byte-identical to `tk_case2d_c.json`; fields equal | same |
| 9 | Mode switch keeps typed hidden-card values (native -> foam -> native) | PASS | `15_foam_after_switch.png`, `16_native_after_switch_back.png`; `material` stayed `'C4'` through the round trip | same "hidden, never greyed, never coerced" rule as baseline/5a |
| 10 | Native 1D run: window repaints mid-run, Run button disabled | PASS | `03_run_midway_early.png`..`06_run_midway_2.png` (live plot advancing, `t = 3.8 ms` shown mid-run); `run_btn` state `disabled` throughout, `normal` after | same as baseline/5a (Qt); confirms the Tk Run tab is unaffected |
| 11 | Native 1D run numbers vs. `solve_1d()` direct | PASS | `08_run_results.png`; table in §6 | **string-identical to baseline's and phase 5a's own numbers** for the same default case |
| 12 | Qt startup, real platform (sanity) | PASS | `30_qt_start.png` | same as baseline/5a |
| 13 | Qt Setup-form round trip (sanity, `set_case`/`get_case`) | PASS | `31_qt_form_roundtrip.png` | same - Qt form untouched by phase 5b, still shares `models/fields.py` |
| 14 | `_qa_gui_harness.py`, scenarios C01-C12 + I05 (13 scenarios, the CaseForm suite) | PASS - 13/13 `done`, **0 findings, 0 crashes** | `C:\Users\rotem.ofek\blastlab_qa\20260925-phase5b\` (`checkpoint.json`, `harness.log`, `findings.jsonl` empty) | baseline/5a did not run this group (it ran B/Q/C/D/E/G/H/I as a 50-scenario Qt-focused set, minus C which didn't exist as a target then); this is this session's own primary evidence for the Tk CaseForm surface |
| 15 | `test_regression.py` | PASS - 8/8 | byte-identical/array-equal to the frozen baseline | **identical to baseline's and phase 5a's own comparison** (this suite exercises the native solvers directly, not the form, so an unchanged result was expected) |

**No FAILs anywhere in this session:** my own two Tk scripts (20 + 1 checks,
all PASS), the Qt sanity script (2/2 PASS), the 13-scenario harness run
(0 findings), and `test_regression.py` (8/8).

## 3. Failures

None. No new failure was found anywhere in this session.

## 4. The three owner-approved behaviour changes - all observed

1. **blastFoam mode: `order`/`eos` are not read from the hidden boxes.**
   With the form in blastFoam mode, `order` set to `'2 (MUSCL)'` and `eos`
   set to `'JWL'` in the (hidden) widgets, `get_case()` returned
   `case.order == 1` and `case.eos == 'idealGas'` - the Qt form's values,
   not the boxes' - `11_blastfoam_order_eos_ignored.png`.
2. **A blank/garbage `order` value in native mode is a reported field
   error, not an exception.** `form.v['order'].set('garbageXYZ')` (and
   separately `''`) both produced `ValueError("'order' is not a
   reconstruction order: '...'")` out of `get_case()`, with `order` in
   `form._bad` (the order box is red-bordered) - `09_order_garbage.png`,
   `10_order_blank.png`. Before the phase-5b refactor this raised
   `IndexError` (per commit `1a9ec76`'s own message); no `IndexError` or
   any other uncaught exception was seen in this session
   (`report_callback_exception` recorded 0 Tk exceptions across every
   script).
3. **`gauge_file`: empty box -> `None`; `None` -> empty box, not the
   string `'None'`.** `form.v['gauge_file'].set('')` then `get_case()`
   gave `case.gauge_file is None`; `form.set_case(case)` with
   `gauge_file=None` then left the Gauge TSV box **empty**
   (`box_text == ''`), not the literal text `None` -
   `12_gauge_file_none_roundtrip.png`.

Also confirmed, as documented "known/intended, not a failure":
native mode's `_charge_model()` always sends `material='TNT'`
(`C05`'s own check: `native keeps the typed foam values in the form and
strips them from the case`, case came back `TNT`/`amr_levels=0` while the
form still showed `C4`/`2`); AMR fields fall back to `0.4`/`0.2`/`2`/`2`/`0`
when AMR is off (visible in the saved 2D case JSON:
`"amr_refine": 0.4, "amr_unrefine": 0.2, "amr_interval": 2, "amr_buffer":
2, "amr_max_cells": 0`, even though `Case2D`'s own dataclass defaults are
`0.2`/`0.1`); and `live` came back `True` after a form round trip in both
the Tk 2D save/open test and the Qt sanity round trip
(`'live': True` in both saved dicts printed to the script logs).

## 5. Visual findings

- Nothing clipped, overlapping or unreadable in any of the 26 screenshots
  from my own scripts or the 114 from the harness run, across all 6
  dim x mode combinations, the invalid-input states, both save/open round
  trips, and both light/dark mode (`041_C09_setup_overflow_light_light.png`,
  lum 204, confirms light mode still renders cleanly).
- One pre-existing (not phase-5b) cosmetic leftover, visible in several of
  the harness's later screenshots (e.g. `022_C05...`, `050_C12...`): the
  Gauges point-list's entry box stays **red-bordered with "select a row in
  the list first"** after an earlier scenario's `_remove()`-with-nothing-
  selected call, even once the form has been reset to a fresh 2D case by
  `_fresh2d()`/`set_case()`. `_PointList._reject`/`_accept` only reset on
  the next add/remove on that same widget instance, and a fresh case does
  not touch it. Not a regression: the same `_PointList` class (unchanged by
  phase 5b - it lives in `gui/forms.py` but was not part of the
  `get_case`/`set_case` mapping that moved) would show the identical
  leftover state under the same sequence of calls before this phase. Purely
  cosmetic (the box's own text is correctly empty; only the red border and
  hint text linger) - flagging for completeness, not scoring as a failure.
- The Tk and Qt Setup screens continue to look consistent with each other
  (compare `02_setup_1d_native.png` with `30_qt_start.png`'s general
  layout), and the Tk dimension selector still shows only 1D/2D/3D (no 0D)
  - unchanged, expected (0D/HD1.3 is Qt-side work).

## 6. Numbers check - happy path (native 1D, through the Tk GUI)

Same default `Case1D()` as the baseline and phase 5a
(`radius_m=10, charge_kg=1, cell_size_m=0.001`, unedited) plus the same two
gauges (`r = 3.0 m`, `r = 6.0 m`), run through the real Tk Setup -> Run ->
Results flow (native mode, explicitly confirmed via `app.solver == 'native'`
before clicking Run), 51,781 steps, 171.7 s wall-clock through the Tk GUI
(vs. 130.8 s through the Qt GUI in phase 5a - both well inside the same
"3D steps are slow" native-solver profile; the 1D solver itself is
identical code, so the difference is GUI polling/redraw overhead, not the
physics). Compared against `solve_1d()` called directly on the identical
`Case1D` object (52.3 s standalone), summarised with the app's own
`output.gauge_summary.summarize_gauges` + `table_rows` - the same functions
the Results table itself calls.

| Gauge | Metric | Displayed (Tk GUI table) | Direct `solve_1d` | Match | Baseline / phase 5a |
|---|---|---|---|---|---|
| G1 r=3.00 m | Peak overpressure [kPa] | 73.1 | 73.1 | yes | 73.1 |
| G1 r=3.00 m | Arrival [ms] | 4.053 | 4.053 | yes | 4.053 |
| G1 r=3.00 m | t peak [ms] | 4.089 | 4.089 | yes | 4.089 |
| G1 r=3.00 m | Pos. phase [ms] | 1.949 | 1.949 | yes | 1.949 |
| G1 r=3.00 m | Positive impulse [Pa*s] | 53.48 | 53.48 | yes | 53.48 |
| G1 r=3.00 m | Net impulse [Pa*s] | -5.36 | -5.36 | yes | -5.36 |
| G2 r=6.00 m | Peak overpressure [kPa] | 22.0 | 22.0 | yes | 22.0 |
| G2 r=6.00 m | Arrival [ms] | 11.694 | 11.694 | yes | 11.694 |
| G2 r=6.00 m | t peak [ms] | 11.766 | 11.766 | yes | 11.766 |
| G2 r=6.00 m | Pos. phase [ms] | 2.931 | 2.931 | yes | 2.931 |
| G2 r=6.00 m | Positive impulse [Pa*s] | 27.90 | 27.90 | yes | 27.90 |
| G2 r=6.00 m | Net impulse [Pa*s] | 0.90 | 0.90 | yes | 0.90 |

All twelve values are **string-identical** between the Tk GUI table and the
direct `solve_1d()` call, and every one **matches the baseline's and phase
5a's own Qt-GUI numbers exactly** - the same case run through two different
GUI toolkits (and, after this phase, the same `models.fields` mapping in
both) lands on the same displayed numbers. Peak, arrival AND impulse all
checked, never peak alone, per CLAUDE.md's measurement discipline note. Net
impulse is the whole-record signed overpressure integral (negative phase
included), as documented.

## 7. `_qa_gui_harness.py` - C01-C12, I05

Ran as a single invocation, explicit fresh `--out` (never `--resume`, per
the task's warning about stale-directory selection carried over from the
baseline's §4.2 note):

```
python -u _qa_gui_harness.py --out C:\Users\rotem.ofek\blastlab_qa\20260925-phase5b \
    --scenario C01,C02,C03,C04,C05,C06,C07,C08,C09,C10,C11,C12,I05 --budget 3600 --solver native
```

- **13/13 scenarios `done`**, total wall time 08:56:03-08:58:49 (~166 s).
  Exit code 0.
- **0 entries in `findings.jsonl`** (empty file) - no `Traceback`, `CRASH`,
  `crashed`, `KillSwitch` or `Exception` string anywhere in `harness.log`
  (checked with a direct grep of the full log and of the checkpoint's
  per-scenario status, all `done`).
- `checkpoint.json`'s `foreign_pids` stayed empty (`[]`) throughout - no
  stray blastFoam/WSL process interfered, confirmed by the harness's own
  kickoff `pgrep` (read-only, per the task's allowance) as well as by my
  own pre-session check.
- Every C-group scenario exercises exactly the surface phase 5b touched:
  parse errors (C01), numeric range rules across all four dims (C02),
  geometry/obstacle/gauge validation messages (C03), malformed point-list
  rows (C04), native-vs-blastFoam card visibility and value-stripping (C05),
  refinement-zone rules (C06), dynamic-AMR rules (C07), cell caps + the
  Run-button modal error path (C08 - triggers `app._run_single()` on a
  case that **fails validation**, i.e. the modal-error path, never an
  actual solve), strip overflow with 3D extras (C09), preview + mesh
  toggling (C10), axisymmetric relabelling (C11), and the Save/Open round
  trip (C12); I05 adds odd numeric inputs (`1e400`, `nan`, `inf`,
  whitespace, decimal comma). All passed with their own internal
  `qa.check()` assertions green - no regression surfaced anywhere in this
  set.
- C08's one `_run_single()` call is on a 2D case sized at `~100,000,000`
  cells (deliberately over the 8,000,000 cap), so it fails
  `validate_case()` and only exercises the "Run failed" modal dialog path
  (`036_C08_run_dialog-showerror_dark.png`) - confirmed no worker thread
  was ever started, no solve of any kind (native or blastFoam) ran during
  this harness invocation.

## 8. `test_regression.py`

**PASS - 8/8**, identical to both the baseline and phase 5a:
`b1_gauges.txt`, `b1_profile.txt`, `b2_gauges.txt` byte-identical;
`b2_profile.npz` arrays equal; `b2r_gauges.txt`, `b3_gauges.txt`,
`b3r_gauges.txt`, `transcript.txt` byte-identical. Run from
`blastlab/tests` with `python -u test_regression.py`. This suite exercises
the native solvers directly and never touches either GUI form, so an
identical result was expected; reported because the task asked for it.

## 9. Comparison summary vs. the two earlier runs

| | baseline (2026-09-24) | phase 5a (2026-09-25) | **phase 5b (this run)** |
|---|---|---|---|
| Form under test | Qt (`ui/case_form.py`, pre-move) | Qt (`ui/case_form.py`, moved to `fields.py`) | **Tk (`gui/forms.py`, moved to `fields.py`)** |
| Own test-plan result | PASS, 0 FAIL | PASS, 0 FAIL | **PASS, 0 FAIL** |
| Harness scenarios run | B,Q,C(n/a),D,E,G,H,I - 50/50 done, 1 finding (Q03, pre-existing) | same 50/50 done, 2 findings (Q03 repeat + 1 new low-severity D02 timing note, D group not run this phase) | **C01-C12,I05 - 13/13 done, 0 findings** |
| `test_regression.py` | PASS 8/8 | PASS 8/8 | **PASS 8/8** |
| 1D happy-path numbers | 8 values recorded, match `solve_1d` | 12 values, string-identical to `solve_1d`, match baseline | **12 values, string-identical to `solve_1d`, match baseline AND phase 5a exactly** |
| New failures | - | none (D02 flagged as a possible timing flake, not attributed to the phase-5a diff) | **none** |

No new failure was introduced by phase 5b. The three owner-approved
behaviour changes are all present and match their description exactly. The
one visual note in §5 (the point-list red-border leftover) is a
pre-existing cosmetic quirk in unchanged code, not a regression.

## 10. Cleanup

Every window/QApplication/Tk root built by my own scripts was closed
(`root.destroy()` / `win.close()`) before its script exited;
`Get-Process python` showed nothing left over before or after this
session, including after the harness's own invocation (which tears down
its own Tk root in its `finally` block). `env.auto_cleanup(...)` was never
called (every script's settings guard was verified `False` before building
a window). No file under `~\Desktop` was touched. Helper scripts lived
only under the scratchpad path given in the task
(`...\scratchpad\qa-p5b\`: `tk_form_qa.py`, `tk_native_1d_run.py`,
`qt_sanity.py`) - no script outside this task's own scratchpad was run. No
`blastlab` application file was edited; no git command that changes
anything was run (only `git log --stat`, read-only). The harness's own run
directory (`C:\Users\rotem.ofek\blastlab_qa\20260925-phase5b\`) was left in
place, as both earlier sessions' run directories were.
