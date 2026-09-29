# GUI-6b Run screen - real-platform measurements (2026-09-29)

Batch `docs/batches/2026-09-29-gui-run.md`, T9 (6b verification). Code state:
`4c6149a` (T6 `dc39a3e`, T7 `e1e5948`, T8 `4c6149a`).

## Pre-registered rules (written 2026-09-29 10:39, before any T9 run)

Both rules are fixed here before the runs that are judged by them
(CLAUDE.md §6, measurement discipline). They are not changed afterwards.

**R-COST (the T6 collection rule).**

- Case: `test_ui_live_gauges` G5 (planar 2D, 2.0 × 1.2 m, cell 0.03 m, 8 kg
  at (0.4, 0), `x_hi` / `y_hi` terminate), with **6 gauges** instead of 2:
  (1.0, 0.4), (1.6, 0.2), (0.7, 0.3), (1.2, 0.8), (1.4, 0.1), (1.9, 0.9).
- Two conditions, each run through the MainWindow with `_run_single()`:
  **A** stays on the Run screen, live slice shown (collecting);
  **B** is moved to Setup (live slice selected) right after the start
  (not collecting).
- Wall clock = from `_run_single()` to `ctrl.running` False.
- Three alternating pairs, B A B A B A (the plan's single pair is the first
  pair; the three pairs are there to see the noise on this 8 GB PC).
- **Pass if both:** the first pair's ratio A / B ≤ 1.10 (the plan's rule as
  written) **and** the median of A / median of B ≤ 1.10; **and** every run's
  `Result.gauges` arrays (`times`, each `pressures` series, `points`) are
  `np.array_equal` to the first run's.
- Reported, not gated: the longest gap of a 10 ms QTimer during each A run.

**R-COST-2 (added 2026-09-29 11:07, after R-COST failed and before any
code change or run judged by it).** R-COST failed (below). The plan's
fallback is applied: collect only while the gauge column is visible, and
throttle the GUI side to 2 Hz. The per-render re-styling is also removed.
That code is then re-measured with R-COST's exact case, order B A B A B A
and thresholds (first pair ≤ 1.10, median ratio ≤ 1.10, arrays equal).
R-COST's FAIL stays recorded as the result for the T6 code as committed.

**R-VIEWER (the embedded 3D viewer, CLAUDE.md §8.7, plan §11).**

- Win32 through ctypes (`GetWindowRect`, `GetParent`, `IsWindowVisible`) on
  a sampler thread, never Qt's `geometry()`.
- A sample is **wrong** when a visible viewer window is a top-level while
  it should be embedded, or when it lies outside the Run host container's
  Win32 rect by more than 8 px on any side.
- Actions: a native 3D case with the 3D view shown, run to its finish (the
  banner appears above the host), then a second start (the banner goes).
- **Pass if the longest unbroken wrong stretch is 0 ms over at least 500
  samples with a visible viewer window.**
