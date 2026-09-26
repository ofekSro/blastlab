# Implement report · 2026-09-26 · hd1-16-load-export

This is the task-implementer's report, saved by `/todo`. It covers branch
`hd1-16-load-export`, from BASE a0f37e3 to 4a3e712.

**Note, a concurrent session:** commit a9c49ca ("materials: remove RDX", P1-14) was
made by another session on this branch during the run. It is not part of this batch.
The same session left uncommitted work in the tree: `docs/references/INDEX.md` is
modified, and `docs/references/ViperTheoryManual_Client.*` and
`docs/wsl-disk-reclaim-plan.md` are untracked. The implementer ran the full gate at
1fe4a1f in a clean checkout, and re-ran a subset at 4a3e712.

## Status per step

| Step | ID | Status | Commits |
|---|---|---|---|
| 1 | HD1-17(a) texts | DONE | 658fb4c, 5e0752d |
| 2 | HD1-16 items 1/2/2a, chamber CSVs | DONE | 7c681ca, 385047b, 13648b0 |
| 2b | HD1-16 item 2, wall traces + optional clearing | DONE | a11cf27, a9a9309 |
| 3 | HD1-16 item 3, no μ / rotation / verdict | DONE | 9a7e80e, ab5a7ae, f1cb45b, e339a38, 2d65b8f, 1fe4a1f |
| 4 | HD1-16 item 4, gates | DONE | 4a3e712 |

## What each step did

**Step 1.**
- The `MACH_QUASI_STATIC` comment now states what was seen: the starter case is at Mach 0.092, 1.8× the threshold. The threshold stays 0.05.
- The CLI Mach line ends in "(upper bound)".
- The docstrings give the band-on time (~20 min).
- Golden diff: that one line only.

**Step 2.**
- New `output/load_csv.py`. `write_report` writes `<stem>_loads/nominal.csv`, plus one `band_<signs>.csv` per band run.
- Each CSV is two columns, t [ms] and p − P_AIR [kPa], written shortest round-trip, with no header and negatives kept.
- Each CSV has a sidecar `.txt` with the case, trace, load type, γ, p_ref, psi factor, net impulse, "no tail" and the "still active" line.
- The "still active" rule is 1 % of peak over the last 1 ms, both as named constants. It is also shown in the CLI and on the Qt status line.
- `sensitivity.band` gains a `'traces'` key, additive only.

**Step 2b.**
- New pure functions in `core/wallload.py`: `clearing_geometry`, `clearing_time`, `incident_from_reflected`, `reflected_sound_speed`, `apply_clearing`. No existing function changed.
- `export_wall_loads` reads `docs/hd13/*.txt` and checks the units line.
- New CLI flag `--hd13-wall-export`.
- New case fields `clearing`, `wall_H_m`, `wall_W_m`, written only when set. They appear in the Qt form as a "Loaded wall" card, where H and W are enabled only while clearing is on.
- C_r is within 1.1 % of Fig. 2-192 at 5 points (tolerance registered at 2 %), and within 0.65 % of the UFC worked example.
- Fig. 2-192 is vector-only. It was read from the page's vector path, mapped through the grid lines, and checked by eye.

**Step 3.**
- `assessment.run` no longer calls SDOF or `structural_verdict`. The keys stay, set to None.
- The report loses the Structural response section, the verdict table and the SDOF figure.
- In the CLI, the structure and verdict lines are gone.
- In the Qt form, the Structure card is hidden and its six keys pass through load and save.
- Residual capacity is still computed.
- Every golden diff is deletions only. `ui_case_form.json` did not change; `hd13_cli_refused.json` did, losing the removed note only.

**Step 4.** All of these passed at 1fe4a1f in a clean checkout:
- `test_regression`, byte-identical;
- `test_foam_writer`, `test_case_validate`, `test_foam_env`;
- the HD1 matrix of 14 suites;
- 8 Qt suites;
- all 14 `test_gui_*` Tk suites (run_browser did not hang);
- the real-window `_e2e_hd13_gui.py`, with the Win32 `IsWindowVisible` check.

At 4a3e712 these were re-run and passed: `test_regression`, `test_case_validate`, `test_load_csv`, `test_wall_clearing`, `test_layering`, `test_char_hd13`.

## Files touched

- **Code:**
  - `blastlab/__main__.py`
  - `core/`: `assessment.py`, `sensitivity.py`, `thermal.py`, `unconfined.py`, `wallload.py`
  - `models/`: `fields.py`, `hd13_case.py`
  - `output/`: `cli_hd13.py`, `hd13.py`, `load_csv.py` (new)
  - `services/hd13.py`
  - `ui/`: `app.py`, `case_form.py`, `setup_spec.py`
- **Tests:** `_e2e_hd13_gui.py`, `test_assessment.py`, `test_char_hd13.py`, `test_hd13_report.py`, `test_load_csv.py` (new), `test_ui_hd13_form.py`, `test_wall_clearing.py` (new).
- **Goldens:** `hd13_cli.json`, `hd13_cli_refused.json`, `hd13_cli_report.html`, `hd13_starter.json`, `ui_case_form.json`, `ui_hd13_run.json`, `ui_hd13_run_report.html`.

## GUI screens touched

- Qt Setup → 0-D (HD 1.3) form: Structure card hidden; new Loaded wall card.
- Qt status line after an HD 1.3 Run.
- The HD 1.3 HTML report.
- Tk: none.

## New numbers

For H = 3 m and W = 4 m:

| | γ 1.24 | γ 1.40 |
|---|---|---|
| C_r | 342.2 m/s | 374.9 m/s |
| t_c | 14.03 ms | 12.80 ms |
| G1 peak, before → after clearing | 153.7 → 104.5 kPa | 146.7 → 100.9 kPa |

## Engineering issues noticed, not changed

1. The starter chamber trace ends at −45.36 kPa at 30.9 s. The 0-D vent has no inflow (`deflagration.py` ~342), so wall cooling pulls the room below ambient. It is exported as computed, and the sidecar notes it.
2. `services/hd13.assess` raises a ValueError for a case with `h_c = 0` that has standoffs, because `figure_thermal` gets an empty q. This bug existed before the batch.
3. Residual capacity is computed but was never printed, in the report or the CLI, before or after this batch.
4. Clearing is applied to a jet stagnation load. With arrival at 1 % of peak, the E peak (~23.8 ms) falls after t_a + t_c, so the whole peak is relieved to Ps + q (−32 %).
5. C_r for γ 1.24 uses ambient air p and ρ, which is inconsistent.

## Open questions

1. Should the Eq. 2-10 check (t_rf = 2 i_r / P_r) be applied to the CFD trace? It is currently not applied, and the sidecar says so.
2. Should the Qt HD 1.3 Run also write the wall CSVs? Only the CLI does now. The wall traces are the single HD1-13 run whatever the case; only H and W come from the case.
3. Is it right to omit the defaulted wall fields from the JSON, so that existing files stay byte-identical?
4. Are the 1 %-of-peak arrival and the linear blend on a time-varying E the right way to apply Fig. 2-191a to a slowly rising jet load?
5. Is suction caused by the missing vent inflow acceptable as an SBEDS input?

## Housekeeping

- A stray `s.json` and `s_wall_loads/` were written to the repo root during a trial run. They were deleted and never committed.
- `.git/worktrees/wt` could not be removed (permission denied, probably OneDrive). `git worktree list` no longer shows it.
- A scratch checkout may remain under the session scratchpad.
