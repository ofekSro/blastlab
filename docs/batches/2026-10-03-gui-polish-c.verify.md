# GUI-11 part 11c — verification report (T10-T15)

Plan: `docs/batches/2026-10-03-gui-polish.md`, part 11c.
Implementer's report: `docs/batches/2026-10-03-gui-polish-c.implement.md`.
Commits checked: `d5944a7..cb740a5` (9 commits). Branch `gui-redesign`.
Verifier fixes: `3487c8b` (T11), `79fcd4c` (T14), then this report with
D223, D224, F46 and F47.

Method:
- Every criterion was re-run, not read.
- A/B ran against a temporary worktree at `d5944a7`, now removed.
- Probes are in the session scratchpad (`v11c/`):
  - `ab_forms.py`: T10 / T11, base against head;
  - `probe_t12_t14.py`, `probe_t13_results.py`, `probe_t11_window.py`,
    `probe_chain_tip.py`;
  - `real_t13_t15.py`: real platform.
- The CLAUDE.md §8.2 dry run read `False`.
- Every MainWindow ran on `ensure_qapp()` / `private_settings()`.
- No WSL command was run. Heavy suites ran one at a time.

## Verdict per task

| Task | Status |
|---|---|
| T10 · Material hidden in native (owner override) | VERIFIED |
| T11 · F16, hidden AMR values survive Open → Save | FIXED (`3487c8b`) |
| T12 · removing a gauge keeps the trigger | VERIFIED |
| T13 · axisymmetric r / z on screen | VERIFIED (one cosmetic finding, F46) |
| T14 · units | FIXED (`79fcd4c`) (one cosmetic finding, F47) |
| T15 · the Chain explains itself | VERIFIED |

---

## T10 · UXR-3, owner override — VERIFIED

The owner's override (`TODO.md` GUI-11, `305a351`) hides the row instead
of the plan's warning. It is implemented as `scope='blastfoam'` on both
Material rows.

- PASS. **Native case output is byte-identical to `d5944a7`.**
  - Check: `ab_forms.py` at base and at head, comparing the
    `save_case` JSON text.
  - Coverage: dims 1-3 × `nodes` / `columns` × native / blastFoam.
  - Each combination ran four times:
    - fresh;
    - ANFO typed in the box;
    - after a switch to the other mode;
    - after switching back.
  - All 48 case JSONs are identical, base against head.
  - Every native JSON carries `material: "TNT"`
    (`models/fields._charge_model`, D138).
- PASS. **blastFoam is unchanged.** It shows the row and runs ANFO, with
  the same JSON as the base.
- PASS. **The value survives mode switches.** The box reads `ANFO` after
  native → blastFoam → native, the same at base and head. `test_ui_setup_form`
  S6b also checks it.
- PASS. **Nothing else became hidden.**
  - Base against head, the hidden rows and the hidden tree nodes differ
    only by `material`.
  - That holds in native, and in blastFoam switched to native, for all
    12 form combinations.
  - No tree node changed visibility.
- PASS. Seeding, harness C05 and the Tk side:
  - `test_ui_chain_screen` (seeding) is green;
  - harness C05 is `done`, and native keeps the typed C4 and strips it;
  - Tk is untouched (`git diff` over `blastlab/gui/` is empty), and
    `test_gui_char_case_form` is green.

## T11 · F16 — FIXED

**What I found.**
- The implementer's code put the hidden **boxes** back into a loaded case.
- A/B probe (`ab_forms.py` E2 / E7, 2D and 3D) showed a typed hidden
  value reaching the case:
  1. Open a file with AMR off (0.2 / 0.1 / 3 / 1 / 400000).
  2. Turn AMR on and type 0.9.
  3. Turn AMR off and Save.
  4. The saved file has `amr_refine` **0.9**. In native mode, typing
     through a mode switch gives the same.
- That violates CLAUDE.md §4. It also undercuts the implementer's own
  D211 reasoning.
- Second issue: the box holds the file's value only to six digits.
  `0.123456789` came back as `0.123457`, so the file did not "survive"
  Open → Save.

**Fix (`3487c8b`, D223).**
- `set_case` keeps the five AMR values **as loaded**.
- `_keep_loaded_amr` writes those values, never the boxes. Parsing is
  the same as before: a value that is not a usable number keeps the
  fallback.
- A fresh form, the golden, `models/` and the solver defaults are
  unchanged.

**Criteria**

1. PASS. A file with AMR off and 0.2 / 0.1 → save → 0.2 / 0.1.
   - Check: `test_ui_setup_form` S3c (2D / 3D, native / blastFoam, on
     disk).
   - Also `probe_t11_window.py` through `MainWindow._open_case`: Save
     reads back `(0, 0.2, 0.1, 3, 1, 400000)`.
2. PASS. A fresh blastFoam form saves 0.4 / 0.2.
   - Check: S3c.
   - A/B E3 / E4: typed hidden values in a fresh form give 0.4 / 0.2 at
     base and at head.
3. PASS. `test_ui_char_case_form` is green.
   - The golden diff is key by key (below), and nothing else moved.
   - It stays green after the fix, unedited.
4. PASS. `test_gui_char_case_form` (Tk) is green, unedited.
5. PASS. `test_ui_parity` (42), `test_ui_char_chain_wiring` and
   `test_regression` are green (see "Gates").

**Edge cases**, all after the fix:

| Sequence | Result |
|---|---|
| Open A (0.2 / 0.1 / 3 / 1 / 400000) → Open B (no `amr_*` keys) → Save | `(0, 0.2, 0.1, 2, 2, 0)`: B's dataclass values, nothing of A leaks |
| Results → Load into 01 Setup (`_load_case_from_result`, a native `case.json`) | file values, native |
| AMR-on blastFoam file (0.3 / 0.15) → switch to native | 0.3 / 0.15: the file's values, inert |
| Typed after load, hidden again (E2 / E7) | file's 0.2, not 0.9 (was 0.9 before the fix) |
| New case after a load | not reachable: the Qt app has no New case action (grep `app.py`) |

**Note for the owner.**
- A file **without** the AMR keys now re-saves as 0.2 / 0.1 / 2 / 2 / 0,
  the dataclass values it loads as. Before 11c it saved the form
  fallbacks, 0.4 / 0.2.
- This is inert with AMR off, and re-opening the file gives the same
  case. It is recorded in D223.

**Changed assertion (fix).**
- `test_ui_setup_form` S3c, "a hidden box that does not parse keeps the
  fallback": this is a check new in 11c. It now expects the file's 0.2,
  because the box is no longer read.
- The fix also adds three checks:
  - a value typed and then hidden;
  - a value typed in native;
  - the full-precision value.

## T12 · UXR-9 — VERIFIED

1. PASS. Trigger G3, remove G1: the trigger is `2`, and the dropdown reads
   `G2 · r 3.00, z 0.50`, the old G3's point.
   - Check: `test_ui_setup_tree` T3e and `probe_t12_t14.py`.
2. PASS. Removing G3 itself blanks it. `trigger_pending()` is True, and
   the switch stays on.
3. PASS. Removing G4 leaves `3`.
4. PASS. A loaded `G5 (no such gauge)` is untouched (T3e).
5. PASS. `test_ui_char_case_form` is green, unedited.

Extra sequences in `probe_t12_t14.py`, each in Setup `nodes` / `columns`
(2D, 3D) and on the Chain 2D and 3D stage editor forms:

| Sequence | Result |
|---|---|
| remove G1, then add a gauge | trigger stays `2`, same point |
| remove the trigger, then add a gauge | stays blank and pending (not re-targeted to the new row) |
| trigger G4, remove all four | blank; `get_case` gives `trigger_gauge None` |
| Remove with no row selected | refused, trigger kept |
| Chain stage, remove G1 | the wired case (`ch.checks()[d].case`) follows with `trigger_gauge == 2` |

## T13 · UXR-11 + F4 + S4-a — VERIFIED

1. PASS. 2D axisymmetric: every point-list header and hint reads r / z, and
   the captions read `Radius R [m]` / `Height H [m]`. Planar restores
   x / y.
   - Check: S8b, and `probe_t12_t14.py` with **six** planar ↔
     axisymmetric toggles in Setup and on the Chain 2D stage.
   - The headers, and the preview's `get_xlabel` / `get_ylabel`, follow
     on every toggle.
2. PASS. The preview's `get_ylabel()` is `z [m]` in axisymmetric, and
   `y [m]` in planar.
3. PASS. Results, through `probe_t13_results.py`:
   - The axisymmetric replay reads `r [m]` / `z [m]`.
   - After four clicks of the real **Show mesh** button
     (`fv.show_mesh.click()`, which re-runs `set_result`), it still
     reads `r [m]`.
   - A planar copy of the same result reads `x [m]` / `y [m]`; back on
     the axisymmetric result, it reads `r` again.
   - A 3D result keeps `x [m]` / `z [m]`.
   - `plane_geometry` (This frame .png) keeps `x [m]`
     (`test_ui_results_screen` S6f).
4. PASS. `test_ui_char_case_form` is green, unedited. Captions are not in
   the golden.
5. PASS. Real platform: the Gauges header reads `r z`
   (`real_t13_t15.py`). The implementer's two screenshots are in
   `docs/qa/2026-10-03-gui-polish/`.

**Finding F46 (cosmetic, not fixed).**
- A red refusal keeps its old column names across a geometry toggle. For
  example, `expected 4 numbers (r0  r1  z0  z1)` stays under `x0 x1 y0
  y1` headers.
- `set_columns` leaves a standing refusal as it is, by design (the error
  is not lost).

## T14 · UXR-15 — FIXED

1. PASS. The Impulse colour bar reads `Net overpressure impulse [kPa·ms]`,
   with no `Pa·s`, and its Min / Max caption reads `kPa·ms`
   (`test_ui_results_screen` S6f).
   - The relabel is exact: 1 kPa·ms = 10³ Pa × 10⁻³ s = 1 Pa·s, so no
     number changes.
2. PASS. `test_ui_char_results_exports` is green unedited, and so is
   `test_char_exports`. `git diff d5944a7..HEAD -- blastlab/tests/char_golden/`
   touches only `ui_case_form.json`, so the export goldens are unedited.
3. PASS. End time `0.012` shows `= 12.0 ms`; `0` shows nothing.
   - Check: S4a, and `probe_t12_t14.py` with odd inputs.

   | Input | Shown | Note |
   |---|---|---|
   | `''` | nothing | |
   | `abc` | nothing | |
   | `1e-3` | `= 1.0 ms` | |
   | `-0.01` | nothing | it parses; validation refuses it |
   | `nan`, `inf` | nothing | the form refuses them |
   | `' 0.012 '` | `= 12.0 ms` | |
   | `3e-4` | `= 0.3 ms` | |
   | `1e-9` | `= 1e-06 ms` | |
   | `0,012` | nothing | the form refuses it too |
   | `1e9` | `= 1000000000000.0 ms` | F47 |

4. FAIL, then FIXED. Each Z tooltip must contain `m/kg^1/3`.
   - Three of them hold on the real platform:
     - the strip tile;
     - the Derived card's `G2 · Z 2.99` (real tooltip shown, with
       `m/kg^1/3`);
     - the live `Z` header (S4b).
   - The model-view **hover readout** tooltip did not. It is set while
     the pointer is on the model and was cleared on leave. On the real
     platform the pointer leaves the model on its way to the caption, so
     the caption reverted and `QToolTip` stayed empty.
   - Measured: `real_t13_t15.py` reported `tooltip shown=''`, caption
     back to `r–z plane · charge on the axis`.

**Fix (`79fcd4c`, D224).**
- Setup and the Chain stages keep `HOVER_TIP` on the caption while a 1D or
  2D model is on screen. It is set in `_sync_toolbar`, and cleared for the
  3D hint and for a stage with no preview.
- `HOVER_TIP` now starts `The readout over the model:`.
- After the fix, on the real platform, moving onto the caption shows the
  tooltip.
- Offscreen, `probe_chain_tip.py` confirms the Chain stages: 1D and 2D
  carry the tip, and 3D carries none.
- `test_ui_setup_strip` S2c: the 11c check "and drops the readout's
  tooltip" now expects it kept. This is a check new in 11c, changed with
  the behaviour.

**Reference check (UFC 3-340-02).**
- Para. 2-13.1, *Free Air Burst*, starts on printed p. 43 and continues
  on p. 44 (PDF p. 120). It defines `Z = R/W^1/3`
  (`ufc_3_340_02.txt`, line 5055).
- The citation in `UNIT_TIP` and `scaled_distance.py` checks out for the
  definition.
- The UFC states the unit in ft/lb^1/3. `m/kg^1/3` is its SI counterpart,
  and no value was converted.

**Finding F47 (cosmetic, not fixed).**
- The `= N ms` line has no width limit. With `1e9` it widens the field
  column by 11 px on the real platform (box 156 → 167 px).
- Ordinary values fit.

## T15 · UXR-12 — VERIFIED

1. PASS. The 3D hint names the wired domain and the burst height
   (`test_ui_chain_screen` S4u).
   - Source check: the 2D → 3D height is the 2D stage's
     `center[1]`.
   - That matches `solver3d.py` 136 (`z0 = profile2d['y0']`) and
     `core/profiles.remap_profile_2d_to_3d` (the 2D z maps directly onto
     the 3D z).
   - Fed by 1D, the hint uses this stage's own cz, as
     `remap_profile_1d_to_3d` does.
   - The route tooltips match the remap code:
     - 1D → 2D at `y0 = center[1]`;
     - 2D → 3D swept about the vertical axis through
       `(center[0], center[1])`.
2. PASS. Four route tooltips, non-empty, distinct, one line each (S4u).
   - Real platform: each button shows its own tooltip after a real
     pointer hover.
   - Check: `QToolTip.text()` equals the button's tooltip, and the
     `QTipLabel` window is Win32-visible.
3. PASS. Clicking the line opens 02 Run with the Model box focused.
   - Offscreen: `linkActivated` (S4u).
   - **Real platform:** I scanned the line for the pointing-hand cursor
     and found it at (62, 2) on `set the Model on 02 Run`. A real
     `QTest.mouseClick` there gave:
     - `current_tab() == 'run'`;
     - `QApplication.focusWidget() is run_panel.run_name`;
     - `hasFocus()` True;
     - the window Win32-visible.

F45 (the default 3D box against the 2D burst height) is the
implementer's finding. It is confirmed by the hint text in S4u and left
to the owner.

---

## Golden diff, key by key

Check: `golden_kdiff.py` (flattened JSON, 57 top keys / 2200 leaves before
and after), run over `d5944a7..HEAD` and per commit.

| Commit | Key | Change |
|---|---|---|
| `64ca7f4` (T10) | `dim1_native/set_c1/hidden` | + `material` |
| `64ca7f4` (T10) | `dim2_native/set_c2_axisym/hidden` | + `material` |
| `64ca7f4` (T10) | `dim2_native/set_c2_planar/hidden` | + `material` |
| `64ca7f4` (T10) | `dim3_native/set_c3/hidden` | + `material` |
| `99bce3f` (T11) | `dim2_native/set_c2_axisym/get/case/amr_refine` / `amr_unrefine` | 0.4 / 0.2 → 0.35 / 0.1 |
| `99bce3f` (T11) | `dim3_native/set_c3/get/case/amr_refine` / `amr_unrefine` | 0.4 / 0.2 → 0.2 / 0.1 |
| `99bce3f` (T11) | `dim3_blastfoam/set_c3/get/case/amr_refine` / `amr_unrefine` | 0.4 / 0.2 → 0.2 / 0.1 |

- Nothing else moved.
- `642308d` itself left the golden alone. Between `642308d` and `64ca7f4`
  the golden is red by construction, as the implementer said.
- `gui_case_form.json` (Tk) and every other file in `char_golden/` are
  untouched.
- My fix does not move the golden: `test_ui_char_case_form` is green
  after `3487c8b`, unedited.

## Defects found in the diff

| # | File | Severity | State |
|---|---|---|---|
| 1 | `ui/case_form.py` `_keep_loaded_amr` | Medium | FIXED `3487c8b` (D223) |
| 2 | `ui/setup_panel.py`, `ui/chain_stage.py` | Medium | FIXED `79fcd4c` (D224) |
| 3 | `ui/fieldform.py` `set_columns` | Low | open, F46 |
| 4 | `ui/case_form.py` `_sync_t_end_ms` | Low | open, F47 |

1. A value typed into a hidden AMR box after a load was written to the
   case, and the file's value lost digits past six.
2. The model-view hover tooltip (T14) could not be shown on the real
   platform.
3. A standing refusal keeps the old r / z or x / y names after a geometry
   toggle.
4. The ms line has no width limit (`1e9` widens the column by 11 px).

**Also reviewed, no defect:**
- No bare `except` was added.
- The one `except ValueError: pass` in `_keep_loaded_amr` is the
  documented fallback.
- No debug prints, no TODOs.
- `PointList.on_remove` has one caller.
- The rich-text run line escapes its text (`html.escape`).
- The theme signal connection follows the existing pattern.
- `run_line_text()` keeps the plain text for its callers.
- The Impulse relabel only replaces `[Pa·s]` on screen.
- `plots.IMPULSE_LABEL` and `select_field` keep `Pa·s`.

## Engineering questions

None numerical. No coefficient, unit conversion, solver value or export
byte changed.

- The `kPa·ms` relabel is an identity.
- D223's change for key-less files (0.4 / 0.2 → 0.2 / 0.1) is in inert
  fields. It is listed above for the owner.

## Tests run (offscreen unless said; all one at a time)

At `cb740a5`, before the fixes, all exit 0:
- 20 Qt and char suites: `test_ui_setup_form`, `test_ui_setup_tree` (261
  lines), `test_ui_setup_strip` (130), `test_ui_char_case_form`,
  `test_gui_char_case_form` (Tk), `test_ui_chain_screen` (221),
  `test_ui_results_screen` (201), `test_ui_output_card` (163),
  `test_ui_no_vtk_in_main`, `test_ui_no_mpl_pyplot`, `test_ui_chain`
  (115), `test_ui_frame` (79), `test_ui_preview`, `test_ui_results`,
  `test_ui_char_results_exports`, `test_ui_char_results_meta`,
  `test_ui_char_hd13_run`, `test_char_exports`, `test_char_validation`,
  `test_ui_parity` (42);
- also `test_ui_hd13_form` and `test_ui_run_screen`.

After the fixes, all exit 0:
- `test_ui_setup_form` (144);
- `test_ui_setup_strip`;
- `test_ui_char_case_form` (unedited);
- `test_gui_char_case_form`;
- `test_ui_setup_tree`;
- `test_ui_chain_screen`;
- `test_ui_chain`;
- `test_ui_parity`;
- `test_ui_no_vtk_in_main`;
- `test_ui_no_mpl_pyplot`;
- `test_ui_frame`;
- `test_ui_results_screen`.

Harness, offscreen:
- Command: `--solver native --scenario C01,C02,C05,G01,G02,K02`, in
  `~\blastlab_qa\gui11-c-verify`, after the fixes.
- All six scenarios ended `done`, exit 0, with 504 `ok` lines.
- There is one finding, the inherited S4 `Tight layout not applied` in
  K02, the same as the implementer's base run.

Real platform (`windows`, Win32-visible):
- `real_t13_t15.py`: PASS after the fix.
- It found the hover-tooltip FAIL before the fix.

**Gates (run last):**
- `test_regression`: **PASS**, byte-identical. Seven files are
  identical, the `b2_profile.npz` arrays are equal, and no baseline file
  is dirty.
- `test_ui_char_chain_wiring`: **PASS**, unedited.

## Files touched by the fixes

- `blastlab/ui/case_form.py`
- `blastlab/ui/setup_panel.py`
- `blastlab/ui/chain_stage.py`
- `blastlab/ui/model_overlay.py`
- `blastlab/tests/test_ui_setup_form.py`
- `blastlab/tests/test_ui_setup_strip.py`
- `docs/gui-redesign-decisions.md` (D223, D224, F46, F47)
- this report

Frozen paths: `git diff d5944a7..HEAD` over `gui/`, `core/`, `models/`,
`output/`, `viz3d/`, `solvers/`, `services/`, `view3d_host.py`,
`run_controller.py`, `viewer_link.py`, the baselines, the fixtures and
`char_golden/` shows only `char_golden/ui_case_form.json` (the approved
entries). No never-stage path is in any commit, and no worktree is left.

## GUI screens that need QA

These are the implementer's list, plus:
- **01 Setup and Chain 1D / 2D stages, model view:** after hovering the
  model, move onto the caption. It shows the units tooltip (`The readout
  over the model: …`), also beside the plane caption. It shows none on
  3D.
- **01 Setup ▸ 06 Solver (and Chain):** Open a case with AMR off, turn
  AMR on, type a threshold, turn AMR off, then Save. The file keeps its
  own value.

## Still open

- F46 and F47 (cosmetic, a later UI pass).
- F45, D211 / D223 and native materials: owner calls, as listed in the
  implementer's report.

**Verdict:** ready for QA. T10-T15 are verified or fixed, the gates are
green, and two Medium defects were fixed.
