# blastlab QA - phase 5a - 2026-09-25

Post-phase QA after refactor Phase 5a (`docs/ARCHITECTURE_REVIEW.md` section 5,
finding F4; commits `8a3f486` "refactor(phase 5a): one form-to-Case mapping in
models/fields.py, Qt first" and `7e39f13` "simplify(phase 5a): models/fields.py
tests/test_char_case_json.py" on branch `arch-p5a-fields`). The change moved the
Setup form's form-to-Case mapping (`_f`, `_i`, `_trig`, `CaseForm._csv`,
`CaseForm._HD13_UNITS`, `get_case`/`_get_case_hd13`, `set_case`/`_set_case_hd13`/
`_set_trigger`, `_order_label`) out of `blastlab/ui/case_form.py` and into
`blastlab/models/fields.py`, toolkit-free. **The only GUI file touched is
`blastlab/ui/case_form.py`.** No application code was edited during this QA
session. Compared throughout against the baseline:
`docs/qa/2026-09-24-baseline/QA_REPORT.md`.

## 1. Environment

| | |
|---|---|
| Python | 3.12.10 (Microsoft Store build), on PATH as `python` |
| Qt | PySide6 (offscreen for widget work; real platform, `QT_QPA_PLATFORM` unset, for the two startup screenshots) |
| Pillow | 12.2.0 |
| pywin32 | 312 - `win32gui.PrintWindow` does not exist in this build; the ground-truth capture used `ctypes.windll.user32.PrintWindow` directly instead (CLAUDE.md 8.7: "Win32 through ctypes ... is the ground truth"), same `PW_RENDERFULLCONTENT` flag the baseline used |
| pyvista / pyvistaqt | present; this session's WSL/blastFoam probe came back ready (14 cores, 63 GB VM) - harmless environment detection, no solve was triggered |
| OS | Windows 11 Enterprise 10.0.26200 |
| Launch | `blastlab.ui.app.MainWindow` and `blastlab.gui.app.App` built directly in throwaway harness scripts under the session scratchpad (`C:\Users\ROTEM~1.OFE\...\scratchpad\qa-p5a\`), same pattern as the baseline - no `python -m blastlab` subprocess needed for my own scripts |
| Settings guard | every script set `BLASTLAB_SETTINGS` to a private file via `blastlab.ui.testing.private_settings()` **before** importing the app, and asserted `settings.load()['auto_cleanup'] is False` before building any window. `env.auto_cleanup(...)` was never called. The harness's own `main()` writes `auto_cleanup: false` into its `--out` dir's `settings.json` before import, per its source. |
| Environment quirk (carried over from baseline, not an app bug) | `PIL.ImageGrab.grab()` still fails with `"screen grab failed"` in this shell/session, confirmed again this run. Real-platform screenshots used the Win32 `PrintWindow` ground truth instead, exactly as the baseline documented. |
| Python processes | none running before this session; `Get-Process python` confirmed clean afterward too. The QA harness (see §10) ran as the only long-lived process, in the background, and the report was finalised only after it exited. |

## 2. Result table - my own test plan (Setup-form focus)

| # | Item | Result | Evidence | vs. baseline |
|---|---|---|---|---|
| 1 | Startup (offscreen) | PASS | `01_tab_setup.png` - title `blastlab 1.0.0`, no traceback | same |
| 1b | Startup (real platform, Win32/ctypes capture) | PASS | `42_realplatform_start_win32.png` | same (ImageGrab still fails here too; PrintWindow ground truth used, via ctypes this time since `win32gui.PrintWindow` is absent from this pywin32 build) |
| 1c | Startup, Tk (`--tk`, real platform) | PASS | `50_tk_start.png` | same - Tk untouched this phase, dim selector still 1D/2D/3D only (no 0D) |
| 2 | Every tab (Setup/Run/Results/Chain) | PASS | `01-04` | same |
| 2b | Every dimension's Setup form (0D/1D/2D/3D) **x both solver modes** (8 combinations) | PASS | `05_setup_{0,1,2,3}d_{native,blastfoam}.png` | baseline covered 0D/1D/2D/3D but not systematically x2 solver modes; this phase's focus does, since `case_form.py`'s `_apply_mode`/`apply_scope` is exactly what moved-around code touches |
| 3 | Resize 900x600 / 1600x1000 | PASS (same floor as baseline) | `06_resize_900x600.png`, `07_resize_1600x1000.png` | identical: `MainWindow.setMinimumSize(1100, 720)` still enforces the floor |
| 4 | Happy path: default 1D native case (`radius_m=10, charge_kg=1, cell_size_m=0.001`) + 2 gauges, run, compare vs `solve_1d` | PASS | `21-25`; numbers in §5 below | numbers match the baseline's own numbers exactly (see §5) |
| 5 | Invalid input, parse-level (text / empty / decimal comma) across 0D/1D/2D/3D | PASS | `08_invalid_1d_text.png`, `08_invalid_1d_empty.png`, `08_invalid_1d_decimal_comma.png`, `09_invalid_2d_empty_Lx.png`, `10_invalid_3d_text_Lz.png`, `12_invalid_0d_text_volume.png` | baseline tested 1D only; this phase adds decimal-comma and covers 2D/3D/0D too, since the parsing itself moved to `fields.py` |
| 5b | Invalid input, range-level (negative charge / zero or negative cell size) across 1D/2D/3D | PASS | `08_invalid_1d_negative_charge.png`, `08_invalid_1d_zero_cell.png`, `09b_invalid_2d_negative_charge.png`, `11_invalid_3d_negative_cell.png` | new this phase (see note below on the two distinct paths) |
| 5c | Other fields preserved after a bad field is fixed | PASS | `08z_invalid_1d_restored.png`; script log `radius_m='10' charge='1' cell='0.001'` after the round trip | same behaviour as baseline |
| 6 | Solver-mode switch + dimension switch with values already typed (hidden-not-greyed) | PASS | `13_status_2d_native.png`, `14_2d_blastfoam.png`, `15_2d_native_after_switch.png` (13 and 15 are pixel-identical - the native-mode state round-trips exactly through a detour into blastFoam mode) | consistent with the documented, intentional "hidden, never greyed" rule |
| 7 | Status-strip cell count | PASS | `13_status_2d_native.png` - "~143,641 cells at dx = 0.0105424 m"; 1D - "~10,000 cells at dx = 0.001 m" | new focus item this phase; both notes render correctly after the fields.py move |
| 8 | Save case / Open case round trip, JSON compared | PASS | `docs/qa/2026-09-25-phase5a/cases/case1d_a.json` vs `case1d_c.json`, `case2d_a.json` vs `case2d_c.json` - **byte-identical**, and the two `Case` dataclasses compared field-for-field equal, for both 1D and 2D | baseline only checked that the widgets visually restored; this phase additionally diffs the actual JSON bytes and the dataclass fields |
| 9 | Long calculation: window repaints mid-run, Run button disabled | PASS | `23_run_midway.png` (step 1694, t=0.244 ms, live plot updating); `run_btn.isEnabled()` was `False` from the click through the run and `True` again after | same as baseline |
| 10 | Close terminates cleanly | PASS | every script closed its window; no leftover `python` process after any of my own scripts | same |
| 11 | Primary harness `_qa_ui_harness.py` (native/UI scenarios) | PASS - 50/50 done, 2 findings (1 repeat of baseline's, 1 new low-severity timing note) | §10 | see §10 - one new item to flag |
| 12 | `test_regression.py` | PASS - 8/8 | §10 | identical - byte-identical to baseline's own comparison |

No FAILs in my own test plan (0 findings recorded by every script's own
self-check logic across items 1-10 above).

## 3. Failures

None found in the Setup-form surface this phase touched, by my own scripts.
The harness (§10) additionally recorded one NEW low-severity finding (D02,
a solver-log timing check) which is reported there in full, with an
assessment of why it looks like an environment timing flake rather than a
regression caused by this phase's diff.

## 4. Suspected engineering error (not investigated further, per scope)

**Typing a negative charge into a 2D case throws inside the live Model
Preview** (uncaught, but does not crash the app - see below).

- Steps: Setup tab, dim = 2D (default axisymmetric, e.g. `Lx=4, Ly=4,
  cell=0.025`), native or blastFoam mode, type `-2` into "Charge [kg TNT]"
  and wait for the debounced validator (~0.3 s).
- Expected: the status card shows the existing "Charge must be > 0" error
  (which it does correctly) and the Model Preview either keeps its last
  good picture or shows a hint; nothing throws.
- Actual: `_validate()` still calls `SetupPanel.update_preview(case)` (the
  built `Case2D` has `charge=-2.0`, since `case_from_fields` only refuses
  fields that fail to *parse*, not fields that fail *range* validation -
  see the note under §8 below). That reaches `core/refine.py:126`
  `charge_radius()`:
  `(3.0 * mass / (4.0 * math.pi * rho0)) ** (1.0 / 3.0)` with a negative
  `mass`, which Python evaluates as a **complex** number, and
  `core/refine.py:115` `effective_dx()` then does
  `if cell_size > r_exp / n_cells:` - comparing a `float` to a `complex`,
  which raises `TypeError: '>' not supported between instances of 'float'
  and 'complex'`. The traceback surfaces on stderr (via PySide6's default
  `sys.excepthook`, invoked from inside the `QTimer` slot) but the Qt event
  loop swallows it and keeps running - reproduced twice, back to back,
  identical traceback both times. The Model Preview is left showing a
  partially-drawn frame (domain outline and burst marker, no charge
  overlay) rather than either the previous good picture or an error state
  - see `09b_invalid_2d_negative_charge.png`.
- **Not reproduced for 3D** with the same `-2` in a quick follow-up check
  (`09c_invalid_3d_negative_charge.png`; report card correctly shows
  "Charge must be > 0", no traceback on stderr) - the 3D preview path goes
  through the separate pyvista bridge rather than `preview_draw.draw_2d`
  synchronously, so it does not hit this exact line.
- **This is outside the phase-5a diff.** `core/refine.py` and
  `output/preview_draw.py` are untouched by commits `8a3f486`/`7e39f13`; the
  bug is reachable through the OLD `case_form.py` exactly the same way
  (`get_case()` has always built a case for a range-invalid-but-parseable
  value and handed it to `update_preview`). It is not flagged as a NEW
  failure introduced by this phase. It also was not caught by the
  2026-09-24 baseline session, because that session's negative-charge
  check was on the 1D form only (`10_invalid_negative_charge...png`),
  and the 1D preview path does not call `refine.plan_levels`.
- Likely origin: `blastlab/core/refine.py:115` (`effective_dx`) and
  `:120-126` (`charge_radius`), reached via
  `blastlab/output/preview_draw.py:69` (`_plan`) and `:99` (`draw_2d`),
  called from `blastlab/ui/setup_panel.py:264`
  (`SetupPanel.update_preview`).
- Per the task scope, not investigated or fixed further; flagging for
  arch-refactorer / the owner.

A second, minor, unrelated-to-case_form observation from the same session:
closing the `MainWindow` immediately after touching blastFoam mode (before
switching back to native) once printed `RuntimeError: Signal source has
been deleted` from a background WSL-poll thread's queued call
(`blastlab/ui/app.py:312`/`ui/bridge.py:22`) during Qt teardown. This
happened only in one of my own throw-away diagnostic scripts that closed
the window abnormally fast after a mode touch; it did not appear in any of
the main flows (t1/t2/t3), all of which allow `_on_solver_mode` to stop the
WSL timer before closing. Not scored as a failure - a background-thread
teardown race unrelated to the fields.py move.

## 5. Numbers check - happy path (native 1D)

Same default `Case1D()` as the baseline (`radius_m=10, charge_kg=1,
cell_size_m=0.001`, unedited) plus the same two gauges (`r = 3.0 m`,
`r = 6.0 m`), run through the real Setup -> Run -> Results flow (native
mode), 51,781 steps, 130.8 s wall-clock through the GUI. Compared against
`solve_1d()` called directly on the identical `Case1D` object (52.7 s
standalone), summarised with the app's own
`output.gauge_summary.summarize_gauges` + `table_rows` - the same functions
the Results table itself calls.

| Gauge | Metric | Displayed (GUI table) | Direct `solve_1d` | Match | Baseline (2026-09-24) |
|---|---|---|---|---|---|
| G1 r=3.00 m | Peak overpressure [kPa] | 73.1 | 73.1 | yes | 73.1 |
| G1 r=3.00 m | Arrival [ms] | 4.053 | 4.053 | yes | 4.053 |
| G1 r=3.00 m | t peak [ms] | 4.089 | 4.089 | yes | not recorded |
| G1 r=3.00 m | Pos. phase [ms] | 1.949 | 1.949 | yes | not recorded |
| G1 r=3.00 m | Positive impulse [Pa*s] | 53.48 | 53.48 | yes | 53.48 |
| G1 r=3.00 m | Net impulse [Pa*s] | -5.36 | -5.36 | yes | -5.36 |
| G2 r=6.00 m | Peak overpressure [kPa] | 22.0 | 22.0 | yes | 22.0 |
| G2 r=6.00 m | Arrival [ms] | 11.694 | 11.694 | yes | 11.694 |
| G2 r=6.00 m | t peak [ms] | 11.766 | 11.766 | yes | not recorded |
| G2 r=6.00 m | Pos. phase [ms] | 2.931 | 2.931 | yes | not recorded |
| G2 r=6.00 m | Positive impulse [Pa*s] | 27.90 | 27.90 | yes | 27.9 |
| G2 r=6.00 m | Net impulse [Pa*s] | 0.90 | 0.90 | yes | 0.90 |

All twelve values are **string-identical** between the GUI table and the
direct `solve_1d()` call (not just "within display precision" - the exact
same formatted text), and every one of the six values the baseline also
recorded matches the baseline's own numbers exactly. Peak, arrival AND
impulse all checked, never peak alone, per CLAUDE.md's measurement
discipline note. Net impulse is the whole-record signed overpressure
integral (negative phase included), as documented - not a positive-phase-
only reference.

## 6. Save / Load round trip - JSON diff

Two round trips (fill the form -> `get_case()` -> `save_case()` -> perturb
an unsaved field -> `load_case()` -> `set_case()` -> `get_case()` again ->
`save_case()` again -> compare):

- **1D**, `radius_m=12.5, charge_kg=2.5, cell_size_m=0.002, bc_outer=reflect,
  gauge_radii=[3.0, 6.0]`: `case1d_a.json` and `case1d_c.json` are
  **byte-identical**; `case_to_dict()` equal field-for-field.
- **2D**, `Lx=6, Ly=4, cell=0.05, charge=3, geometry=planar`, one gauge
  `(1.0, 2.0)`, one obstacle `(0.5, 1.5, 0.0, 1.0)`: `case2d_a.json` and
  `case2d_c.json` are **byte-identical**; `case_to_dict()` equal
  field-for-field.

Both under `docs/qa/2026-09-25-phase5a/cases/`.

## 7. Status-strip cell count

Confirmed rendering correctly for native mode after the fields.py move:

- 1D default case: `~10,000 cells at dx = 0.001 m`
- 2D default case: `Cell size will be refined to 0.01054 m (5 cells across
  the charge radius)` + `~143,641 cells at dx = 0.0105424 m`

Both notes come from `services/validation.validate_case()`'s `rep.n_cells`
/ `rep.effective_dx`, unchanged by this phase; confirms the case object
`fields.py` now builds still carries everything that computation needs.

## 8. Known-and-intended, not failures (confirmed, matches the task's list)

- **Native mode always sends `material='TNT'`**, regardless of what the
  (hidden) Material row holds - confirmed unchanged in
  `models/fields.py:_charge_model()`, open question UX-E2.
- **AMR fields fall back to 0.4/0.2/2/2/0** when AMR is off - confirmed via
  `AMR_FORM_FALLBACKS` in `models/fields.py`, open question (per
  `docs/history` from phase 5a's own doc commit). Also confirmed round-
  tripping into the saved 2D JSON (`amr_refine: 0.4, amr_unrefine: 0.2, ...`
  even though the case's own dataclass defaults are 0.2/0.1).
- **Hidden-not-greyed** controls per solver mode - confirmed visually
  across all 8 dim x mode screenshots; no control was ever disabled/greyed
  instead of hidden.
- **The two distinct invalid-input paths** (worth stating explicitly since
  it looks like a gap the first time you see it): a field that fails to
  *parse* (text, empty, `nan`/`inf`, a decimal comma) is red-bordered by
  `CaseForm.mark_fields` and blocks `get_case()` with a per-field message;
  a field that parses fine but fails a *domain* check (negative charge,
  zero cell size) is NOT red-bordered - `get_case()` succeeds, and the
  domain error is reported only in the status card by a separate
  `validate_case()` call, which also disables the Run button. Both paths
  were exercised across every dimension this phase and both work
  correctly; this is unchanged behaviour, not a new gap. The harness's own
  I05 scenario independently exercises the same parse-level decimal-comma
  case (`charge='1,5'`) and gets the same `'charge' is not a number: '1,5'`
  message.

## 9. Visual findings

- Nothing clipped, overlapping, or misaligned in any of the 42 screenshots
  taken (offscreen or real-platform), across all 4 dimensions, both solver
  modes, both window sizes, and every invalid-input state.
- `13_status_2d_native.png` and `15_2d_native_after_switch.png` are
  pixel-identical: a detour through blastFoam mode and back to native
  leaves the form in exactly the state it was in before, confirming the
  hidden-not-greyed round trip does not lose or corrupt anything.
- Real-platform Qt startup (`42_realplatform_start_win32.png`) and Tk
  startup (`50_tk_start.png`) both render cleanly; the Tk dimension
  selector still shows only 1D/2D/3D (no 0D), as documented and expected
  (Tk is unchanged this phase).
- The debounced validator (`_validate_timer`, 300 ms `QTimer.singleShot`)
  was observed to occasionally NOT have fired yet after a single
  fixed-length `processEvents()` pump of up to 500 ms in this offscreen
  session (confirmed by wrapping the real `_validate()` with a call
  counter) - not a product bug, just a reminder for future scripted QA in
  this repo that a fixed sleep-then-check is not a reliable way to wait
  for a debounced Qt timer under an offscreen harness; polling on an
  observable side effect (here, the validate-call counter) is reliable and
  fast in practice (typically settling in 0.3-0.4 s). This is directly
  relevant to the one new harness finding in §10 (D02): the harness's own
  `wait_log(text, 40)` is the same kind of fixed-timeout wait, on a
  different observable (the run log's text) - see the assessment there.

## 10. Existing test suites

### `_qa_ui_harness.py`

Ran the same native/UI scenario groups as the baseline (`B, Q, C, D, E, G,
H, I` - 50 scenarios; `F00-F11`, the 12 blastFoam/WSL scenarios, and the
`S00` smoke test were deliberately excluded again, matching the baseline's
scope for this no-WSL-solve session), with an **explicit `--out`** on every
invocation (never a bare `--resume`), per the task's warning about
`--resume`'s stale-directory selection:

```
python -u _qa_ui_harness.py --out ~/blastlab_qa/20260925-0710 \
    --only B,Q,C,D,E,G,H,I --budget 10800 --solver native
```

- **Round 1** (07:10:23 - 07:45:06): ran B01-I02 (49 scenarios), then exited
  75 after `I02` - not a budget exhaustion this time (the 10800 s budget was
  never close to used), but `I02` is registered `terminal=True` (it closes
  the window mid-run on purpose and needs a fresh `QApplication` for
  whatever comes after it) - exactly the harness's own documented "resume
  me" contract, working as designed.
- **Round 2** (07:44:47 - 07:48:44), same explicit `--out`: ran the
  remaining `I03-I06` (4 scenarios), exited 0.
- **Result: 50/50 `done`, 0 crashes, 0 `KillSwitch`.** No `Traceback`,
  `KillSwitch`, `CRASH`, or unhandled `Exception` string anywhere in
  `harness.log` across either round (checked with a direct grep of the
  full log). `checkpoint.json`'s `foreign_pids` stayed empty throughout
  (no stray blastFoam/WSL process interfered).
- Native-3D scenarios: `D04` 525.5 s, `I01` 536.4 s (both estimated at
  330 s, both over - consistent with the app's own "3D steps are slow"
  warning, same as the baseline's D04/I01 overrun, and actually *faster*
  than the baseline's 688 s / 777 s on this machine this session).
- **Two entries in `findings.jsonl`:**
  1. `Q03`, S2, "no result labelled 'QA native2d' to select" - **identical
     text and cause to the baseline's own Q03 finding** (running the `Q`
     group before `D02` has cached a `native2d` result, in one continuous
     `--only B,Q,C,D,E,G,H,I` invocation): **not new**, reproduced exactly.
  2. `D02`, S1, **"the 2D solver announced itself" - failed.** This one is
     **not present in the baseline's `findings.jsonl`**, so it is flagged
     here explicitly as required. What the check does: after clicking
     "Run" on a native 2D case, `qa.wait_log('2D Blast Solver', 40)` polls
     the Run tab's log for up to 40 s for the solver's own banner line
     (`solvers/solver2d.py:302`,
     `hooks.log(f"  2D Blast Solver ({geometry})")`, confirmed present and
     unrelated to this phase's diff). It did not appear within 40 s of the
     click this run. **The scenario did not otherwise fail**: the very
     next check, `qa.check(qa.run_wait(300), 'the 2D run finished', 'S1')`,
     passed (the run actually finished about 9 s after the 40 s timeout,
     i.e. ~49 s after the click), and the subsequent dropped-gauge-warning
     check passed too; `D02`'s own recorded `timing.jsonl` entry shows
     `max_gap_ms: 181` with an empty `big_gaps` list, meaning the harness's
     `processEvents()` pump never stalled (no event-loop freeze) during
     the scenario - so the delay is a genuine ~40-49 s gap between clicking
     Run and the FIRST log line appearing, not a frozen UI. `case_form.py`/
     `fields.py` have no part in the run/log pipeline (they only build the
     `Case` before the click), so this does not look attributable to this
     phase's diff; it reads as an isolated timing hiccup in this
     environment (this machine, this run) rather than a reproducible
     regression, but it was **not seen in the baseline** and I could not
     rule out a genuine slow-first-log-line regression without a second,
     isolated repro of `D02` alone, which was out of this session's time
     budget. **Recommend a follow-up QA session re-run `D02` on its own
     (`--only D --scenario D02`) to see if it reproduces.**
- Exit codes seen: `75` (the `I02` terminal-scenario handoff, expected) on
  round 1, `0` on round 2 - a cleaner two-round pattern than the baseline's
  eight rounds (this session ran as one continuous background process
  rather than across a whole night with gaps).

### `test_regression.py`

**PASS - 8/8**, identical to the baseline: `b1_gauges.txt`, `b1_profile.txt`,
`b2_gauges.txt` byte-identical; `b2_profile.npz` arrays equal;
`b2r_gauges.txt`, `b3_gauges.txt`, `b3r_gauges.txt`, `transcript.txt`
byte-identical. Run from `blastlab/tests` with `python -u test_regression.py`.
This suite exercises the native solvers directly and does not touch the Qt
form at all, so an identical result to the baseline was expected; it is
reported here because the task asked for it, not because phase 5a could
plausibly have changed it.

## 11. Cleanup

Every window/QApplication built by my own scripts was closed
(`win.close()`/`root.destroy()`) before its script exited; `Get-Process
python` showed nothing left over after each one, and nothing left over
after the harness's two invocations finished either. `env.auto_cleanup(...)`
was never called (every script's settings guard was verified before
building a window). No file under `~\Desktop` was touched. Helper scripts
lived only under the scratchpad path given in the task
(`...\scratchpad\qa-p5a\`). No `blastlab` application file was edited; no
git command that changes anything was run. The harness's own run directory
(`~/blastlab_qa/20260925-0710`) was left in place, as the baseline's was.
