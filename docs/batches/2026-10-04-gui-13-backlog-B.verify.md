# GUI-13 backlog Part B - verification (light)

Checks run: test_ui_run_screen (221 checks), test_ui_results_screen, test_ui_chain_screen,
test_gauge_summary, test_plots_gauge_titles all exit 0; test_regression last (see verdict).
Diff 6c88eea~1..HEAD read once: no stray numbers, no swallowed errors beyond the
pre-existing `except Exception` around labels_and_dropped; no widget off-thread.

- B1 VERIFIED - run + results screen suites (new checks) pass; Tk column change is width only.
- B2 VERIFIED - chain screen suite (warn at Lz 1.5, ok at 4.0) passes.
- B3 VERIFIED - run screen suite (drop note first, warn colour) passes.
- B4 VERIFIED - results screen suite (hint on All plots / Report buttons, none on canvas).
- B5 VERIFIED - results screen suite (fallback labels) passes.

Fix: formatting typo `fig =plots.` in ui/results_fields.py (no behaviour change).

test_ui_status_cells.py: FLAKY, not real. 5 sequential runs alone gave 4 pass, 1 fail
("the strip follows the keystrokes" in S2). The test types with QTest then `pump(600)`: a
fixed wait against a debounce, so it fails when the machine is loaded. It exercises the
Setup form, which Part B does not touch. Not changed; suggest polling instead of a fixed pump.

Engineering questions: none. GUI QA: Run gauge column + card header at 1100 px, Results
Gauges drop line, export-button tooltips on a 1D result, chain stage Domain & mesh glyph,
Tk Gauges table; `_qa_ui_harness.py` not run (recommended once).

Verdict: Part B VERIFIED (one cosmetic fix).
