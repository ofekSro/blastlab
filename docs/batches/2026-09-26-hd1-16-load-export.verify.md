# Verify report · 2026-09-26 · hd1-16-load-export

This is the task-verifier's report, saved by `/todo`. The branch is
`hd1-16-load-export`, commits a0f37e3..95a62ce.

**Verdict:** ready for QA. Every acceptance criterion reproduced. One code defect was
fixed, in 95a62ce. `test_regression.py` is byte-identical at 4a3e712 and at 95a62ce.

**Scope of the review:**
- HEAD did not move during verification.
- a9c49ca (materials: remove RDX, from another session) was left alone.
- The other session's uncommitted files were not touched.
- The first fix commit, de8de5d, picked up a stale scratch message. It was amended at once to 95a62ce; it was not pushed.
- A stray `t.json` and `t_wall_loads/` were created in the repo root by a failed `cd`. They were moved out and never staged.

**Pre-flight:** `settings.load()['auto_cleanup']` is False, and the Store-Python virtual `settings.json` reads `"auto_cleanup": false`.

## Status per step

| Step | ID | Status | Evidence |
|---|---|---|---|
| 1 | HD1-17(a) | **VERIFIED** | `test_unconfined` PASS, with the threshold at 0.05. The word diff of 5e0752d is the single insertion "(upper bound)". The `test_char_hd13` pins are identical. 0.0917 / 0.05 = 1.83. |
| 2 | HD1-16 items 1/2/2a | **VERIFIED** | `test_load_csv` PASS: bit-for-bit round trip, impulse, the exact "still active" line, sidecar, tiny band, stale-file removal. `test_sensitivity` PASS (the diff is one additive key). The CLI and Qt golden diffs are listings, export lines and status text only. Layering, no-pyplot and no-vtk suites PASS. |
| 2b | HD1-16 item 2 | **FIXED** (95a62ce) | `test_wall_clearing` (a)-(e) PASS; `test_ui_hd13_form` PASS; `test_wallload` PASS, with no existing function changed. |
| 3 | HD1-16 item 3 | **VERIFIED** | `test_sdof` and `test_sensitivity` unchanged. The `hd13_starter.json` diff is deletions only. The grep check in `test_assessment` passes (84 checks) and exercises the old path. The report word diff removes only the Structural response table and figure. The six hidden keys pass through. |
| 4 | HD1-16 item 4 | **VERIFIED** | See the gates below. |

## Step 2b, the independent checks

**Fig. 2-192.** The vector path was extracted from PDF page 343 with pypdf and mapped through the page's grid lines (Pso 0-70 psi, C_r 1.15-1.95 ft/ms).
- Rankine-Hugoniot C_r at γ = 1.4 is within **1.09 %** of all 15 vertices from 4.9 to 74.9 psi, and within 0.4 % above 10 psi.
- The implementer's five points agree to the third decimal.
- The registered tolerance of 2 % holds.

**UFC text.** Eq. 2-8, 2-9 and 2-10 were checked against the text sidecar, page 141 (printed p. 65). Fig. 2-191 is printed p. 266 and Fig. 2-192 is printed p. 267. The worked example on printed p. 411 (12.8 psi → 1.325 ft/ms) agrees. Fig. 2-191a could not be rasterised, so the blend shape rests on the text and the pre-registered construction.

**Algebra.** `incident_from_reflected` (the inverse RH quadratic) and the density ratios in `reflected_sound_speed` were checked by hand.

**`--hd13-wall-export`, clearing off.**
- Four CSVs are written: G1 has 3395 rows and plane-max has 749.
- There is no BOM and no CR, and every line is exactly two floats.
- G1 peaks equal max E / 1e3 exactly: 153.66881805162976 kPa at γ 1.24 and 146.72738434666388 kPa at γ 1.40.

**Clearing on, H = 3 m, W = 4 m.** C_r is 342.2 / 374.9 m/s and t_c is 14.03 / 12.8 ms.

**Validation.** H missing gives exit 1, with an error naming `wall_H_m`, and no directory is written. H = 0 together with W = "4" is refused, and both fields are named.

**Fix 95a62ce.** `export_wall_loads` did not clear its directory. A run with clearing on followed by a run with clearing off left `G1_g*_cleared.csv` next to the unrelieved files, which puts two different design loads for one wall in one folder. It now removes `G1_g*.*` and `planemax_g*.*` first, and a new check in `test_wall_clearing.py` pins this.

## Gates, run at 95a62ce

- `test_regression`: byte-identical.
- `test_foam_writer`, `test_case_validate`, `test_foam_env`: PASS.
- HD1 matrix, all PASS: `test_deflagration`, `sdof`, `unconfined`, `sensitivity`, `thermal`, `qd`, `assessment`, `hd13_report`, `load_csv`, `wall_clearing`, `char_hd13`, `char_hd13_cli`, `char_case_json`, `wallload`.
- Qt, all PASS: `test_ui_hd13_form`, `ui_char_hd13_run`, `ui_char_case_form`, `ui_parity`, `ui_setup_form`, `layering`, `no_vtk`, `no_pyplot`. The no-pyplot suite prints teardown noise from `_poll_wsl` (`Signal source has been deleted`) but reports 18/18 with exit 0; this has nothing to do with the batch.
- Tk: all 14 `test_gui_*` PASS; `run_browser` passed 21 checks and did not hang.
- Real window, `_e2e_hd13_gui.py`, with `QT_QPA_PLATFORM` unset and private settings: PASS.
  - Win32 `IsWindowVisible` returns False for the Structure card and True for the Heat card, the positive control.
  - The report and `report_loads/nominal.{csv,txt}` are written.
  - The status line names the CSVs.

## Defects in the diff

1. `output/load_csv.export_wall_loads`: stale `_cleared` files survived a re-run. Medium. **Fixed**, 95a62ce.
2. `models/fields.py:162-171` `wall_dim`: an unparseable H or W becomes 0 silently while clearing is off. Low. This is deliberate and documented. Not fixed.
3. `ui/fieldform.py:555-562` `apply_scope` re-shows every card whose scope is None. The Structure card stays hidden only because `_mode_changed` skips the 0-D form. Low; nothing reaches it today. Not fixed.
4. `core/assessment.wall_errors`: `True` is accepted as 1 m, and `inf` is accepted. Low; this is P1-11 territory. Not fixed.
5. `output/load_csv.still_active`: a trace containing NaN gets no "still active" line. Low; the current files contain no NaN. Not fixed.

The scan found no debug prints, no bare `except` and no mojibake.

## Engineering questions for the owner

1. **Suction in the chamber trace.** The starter `nominal.csv` ends at −45.36 kPa at 30916 ms, because the 0-D vent has no inflow: `deflagration._vent_mdot` returns 0 whenever p ≤ p_amb (lines 352-353). Is this acceptable as an SBEDS input?
2. **`h_c = 0` with standoffs** gives a ValueError in `services/hd13.assess`. The bug existed before the batch and the batch does not make it newly reachable.
3. **Residual capacity** is computed but has never been printed.
4. **Clearing applied to a slow jet load.**
   - With t_a = 9.58 ms and t_c = 14.03 ms, the E peak at ~23.8 ms falls after t_a + t_c. The G1 peak drops from 153.7 to 104.5 kPa at γ 1.24 (−32 %), and from 146.7 to 100.9 kPa at γ 1.40.
   - After t_c the two cleared files are identical at the same times (for example 78.5335 kPa at 30 ms), because Ps + q comes from one plane file that does not depend on γ.
   - Is the Fig. 2-191a construction meant for this kind of trace?
5. **C_r at γ 1.24** is computed with ambient air p and ρ (ambient c ≈ 320 instead of 340 m/s), which is inconsistent. Which should it be?
6. **Eq. 2-10** (t_rf = 2 i_r / P_r) is not applied. Should it be?
7. **Clearing validation blocks the Qt Run.** Clearing ticked with H or W blank refuses `--hd13` and the Qt Run, although only `--hd13-wall-export` uses the wall. Should the Qt Run also write the wall CSVs?
8. **Arrival and the default fields.** Is 1 %-of-peak arrival with a linear blend right on a slowly rising E? And is it right to leave the defaulted wall fields out of the JSON?

## Files touched by the verifier

- `blastlab/output/load_csv.py`
- `blastlab/tests/test_wall_clearing.py`

## GUI screens for QA

- Qt Setup → 0-D (HD 1.3) form: the Structure card is hidden; there is a new Loaded wall card.
- Qt status line after an HD 1.3 Run.
- The HD 1.3 HTML report.
