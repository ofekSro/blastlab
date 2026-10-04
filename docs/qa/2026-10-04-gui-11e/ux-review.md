# UX review - GUI-11e (read-only)

Scope: `git diff ee9a4b5..HEAD -- blastlab` (F42, F44, T19, D213 b). Framework: PySide6.
No app run; judged from code, golden diffs, the plan/verify reports and the committed
screenshot `docs/qa/2026-10-04-gui-11e/gui11e-run-strip-1280.png`.

## Findings

### 1. [Medium] F44's Setup warning still doesn't name the wall - Run/Results do
`blastlab/services/validation.py` ~1565-1575 (`_validate_closing`), `_gauge_drop_rule`
~1591-1660, vs `blastlab/ui/run_gauges.py` `_drop_reason` (~152-174) and
`blastlab/ui/scaled_distance.py` `where_text`/`where` (~195-225).

F44 makes the *decision* to warn exact per solver, but the wording stays generic:
`Gauge (x, y) inside an obstacle - will be dropped` / `... on an obstacle face - will
be dropped`. With more than one obstacle the engineer cannot tell which one from the
Setup warning. Every other screen that talks about the same geometry names the wall:
Setup's own Where column (`on the face of Wall 1`, `inside Wall 1`) and the Run/Results
missing-gauge explanation (`run_gauges._drop_reason`, same wording). The batch's own
decision log already states the gap in plain words (`docs/gui-redesign-decisions.md`
F44 row): "Run and Results then name it (`on the face of Wall 1`)" while Setup's
warning stays generic - so this is a known, not a newly-discovered, inconsistency, and
F44 was the natural point to close it since it already touches this exact line.
**Fix:** `_gauge_drop_rule`'s native/blastFoam closures already walk `obstacles`/`boxes`
in order; return the matching index (as `_drop_reason` and `where` do) and word the
warning `Gauge (x, y) on the face of Wall {i} - will be dropped` /
`Gauge (x, y) inside Wall {i} - will be dropped`, matching D201's established phrasing
everywhere else. Low implementation cost, no new geometry work.

### 2. [Low] On-screen 1D title now silently diverges from every export of the same figure
`blastlab/ui/results_fields.py` `screen_title_1d` (~71-76) and `_draw_figure` (~424-428).

Confirmed via the golden diff (`char_golden/ui_results_meta.json`): the Results screen
now shows `1D spherical · 1.0 kg TNT · JWL`, while the Summary .csv, HTML report and
every exported PNG/animation keep `1D Spherical Blast - 1.0 kg TNT - EOS: JWL`
(`output/plots.figure_results_1d`, unchanged, by design - D214). This is an approved,
deliberate trade-off for canvas width, not a bug, but nothing on screen signals that the
title is abbreviated. An engineer who screenshots the Results tab for a figure caption
and also attaches the exported PNG will get two different captions for the same plot.
**Fix (optional, cheap):** a short figure caption or tooltip under the canvas
("exports show the full title") would close the gap without touching exported bytes.

### 3. [Low] Title punctuation now differs by tab within the same Results screen
1D now reads `short name · value · EOS` (middle dot); 2D map titles still read
`Field [unit] — slice at ... - charge_label` (em dash + hyphen,
`results_fields.py` ~146); 3D keeps `figure_isosurfaces_3d`'s own builder phrasing.
Not a regression this diff caused on its own (2D/3D titles were already different from
each other), but T19 adds a third, visually distinct style the user meets by switching
tabs. Worth normalizing if a later pass gives 2D/3D the same canvas-width treatment.

### 4. [Low, informational] D213 b (Run strip) - verified clean at 1280 and 1100
Screenshot inspected directly: at 1280x840 dark theme, PROGRESS/TIME/STEP/PMAX sit in
one row, `100 %` and `1.567e+06 kPa` both fully shown, no clipping or wrapping; the
Part B verify report's R12 sweep (1280-1600 px, one row; 1100x720, two rows, unchanged)
corroborates it and finds no squeezed tile. One pre-existing, disclosed gap: the
light-theme Win32-rect check at exactly 1280x840 was not captured as its own
screenshot, only inferred from the 1100x720 theme-toggle checks - minor evidence gap,
not a layout defect.

### 5. [Low] F42's all-or-nothing pairing fallback (P1) is correct but worth watching
`output/gauge_summary._nearest_entered` / `gauge_labels` (~98-141): if nearest-pairing
leaves even one point unmatched (only reachable with mixed-dimension gauges in one
list, an unusual case), *every* label in that result falls back to plain `G<k>`, even
ones that paired cleanly. Matches `run_gauges._numbering`'s own precedent and is the
documented, deliberate choice (D230/P1) - flagging only so a future "why did my mixed
2D/1D batch lose its entered numbers" report isn't a surprise.

## Quick wins (best value, least effort)

1. Name the wall in F44's two warning strings (finding 1) - the index is already a
   short walk away in `_gauge_drop_rule`'s own boxes/obstacles loop.
2. Add a one-line caption/tooltip near the 1D Results title noting exports keep the
   full title (finding 2).
3. Capture the one missing light-theme 1280x840 screenshot for D213 b to close the
   disclosed gap in the Part B verify report (finding 4) - no code change needed.
4. When F44's wall-naming lands, reuse the same helper (or at least the same wording
   function) from `services/validation._gauge_drop_rule` and `ui/run_gauges._drop_reason`
   so the two can't drift again - today they're two independent implementations of
   "which wall is this gauge near" (closed/open box tests aside).
5. Note in `screen_title_1d`'s docstring (or a code comment at the 2D/3D title sites)
   that the three dimension tabs now use three different title styles on purpose, so a
   future unification pass starts from one list rather than rediscovering finding 3.

## Not reviewed (out of scope / no live app)

Did not run the app, the QA harnesses, or re-render the 1D figure; relied on the
committed golden diff, the plan's and verify reports' direct measurements, and the one
committed screenshot. F42/F44 label and warning *correctness* (pairing logic, the
per-solver drop predicate) were reviewed for wording/consistency only, not re-verified
numerically - that is the Part A/B verify reports' job and they already passed it.
