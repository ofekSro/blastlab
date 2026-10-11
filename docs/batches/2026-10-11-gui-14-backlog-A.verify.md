# GUI-14 Part A - verification (light)

Worktree gui-14, base 2f947c4, head under test 445c08e. No fixes were needed.

## Per task
- A1 VERIFIED: diff read (`where(..., wall=)`, `where_text` uses `dropped(point)`); new tie check is in `test_ui_setup_strip` (green in the gate).
- A2 VERIFIED: `outside_domain` is `0 <= v <= L` per axis, closed, matching `solver2d.py:283`, `solver3d.py:341` and `validation.py:1567` (same operators; an x == Lx gauge is kept, pinned by a check). `run_gauges._drop_reason` now shares it. Node warn is computed from the rule in Setup and chain stage.
- A3 VERIFIED: `ElideRight`, `selected` dropped, unit from `sd.LABEL`; `test_ui_run_screen` green.
- A4 VERIFIED: `test_ui_results_screen` green (warn colour and weight in both themes).
- A5 VERIFIED by code read plus the Tk suites in the gate (28/28). The scaling 1.0/1.5 screenshots were not re-measured (see QA).
- A6 VERIFIED: `wait_for` only replaces the two `pump(600)`; no `check(` line changed.
- A7 VERIFIED: both `latest_out()` sort by `(mtime, name)`.
- A8 VERIFIED: seed applied once, quietly, stage 1 untouched; golden diff is exactly three `radius_m` lines (10.0 -> 1.5, lines 161, 378, 743); `test_ui_char_chain_wiring` green.

## The three focus points
1. "3D boxes" fixture (Lx = Ly = Lz = 4.0): legitimate. The default 1.5 m cube put the gauge at x 1.9 outside the domain, which A2 now (correctly) reads as dropped. The wall (x 2.0-2.2) and the asserted literal `10 cm in front of Wall 1` are unchanged; the test still pins the wall/gap/side logic. No behaviour change hidden.
2. `test_ui_chain_screen` A8 edits: S5 still tests S2-1 / F45 / B2. The block now sets stage 1 radius to 10.0 and pumps before the original checks, which are untouched. The other two edits (Outer (1.5 m), s6 `CHAIN_SEED` expectation) follow directly from the seed. New checks pin the seed.
3. A2 closed domain: see A2.

## Gates
- `gate.py --changed 2f947c4`: 28/28 green (16.4 min).
- `gate.py --only regression`: PASS byte-for-byte.
- Not run, as instructed: `_e2e_ui_chain_foam.py`, both big harnesses.

## Defects
None found.

## Engineering questions
None. Recommendation carried over: run `_e2e_ui_chain_foam.py` with the 1.5 m seed (stage 1 blastFoam is a smaller 1D solve than at 10 m).

## GUI screens for QA
Setup Gauges tab and the `05 Gauges` node (warn marks); chain stage Gauges node; Run enlarged-gauge card header; Results Gauges drop line (both themes); Tk Results Gauges table at 1100 px (scaling 1.0 and 1.5); Chain screen default route (card 2 clean).

Verdict: Part A (A1-A8) VERIFIED, no fixes.
