# GUI-6b Run screen - real-platform measurements (2026-09-29)

Batch `docs/batches/2026-09-29-gui-run.md`, T9 (6b verification). The rules
below were written at `4c6149a` (T6 `dc39a3e`, T7 `e1e5948`, T8 `4c6149a`).
T9 then made seven fix commits (`6222392`, `df753a4`, `abd7210`, `da904b7`,
`d143445`, `440635c`, `65d4228`). The results section says which code each
number belongs to.

Machine: the home PC, 8 GB RAM. The commit charge sat at 0.4-2.2 GB free
all session, with other applications holding most of it. Real platform
(`QT_QPA_PLATFORM` unset, `ensure_qapp(offscreen=False)`) for every
screenshot, the toast and the viewer sampler. Throwaway settings throughout
(`ui.testing.private_settings()`; `auto_cleanup` off); the §8.2 dry run
printed `<repo>\settings.json False []` before the session. Scripts are in
the session scratchpad (`t9_cost.py`, `t9_cost_diag.py`, `t9_gap_diag.py`,
`t9_viewer*.py`, `t9_shots.py`, `t9_contrast.py`). The e2e is committed as
`blastlab/tests/_e2e_ui_run_finish.py`.

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

## Results

### R-COST - FAIL at the T6 code; R-COST-2 - PASS after the plan's fallback

`cost_6b.json` (T6 as committed, `abd7210`), offscreen:

| | run 1 | run 2 | run 3 |
|---|---|---|---|
| B, not collecting [s] | 7.96 | 8.09 | 7.84 |
| A, collecting [s] | 9.15 | 9.44 | 8.92 |
| A / B | **1.150** | 1.167 | 1.138 |
| longest 10 ms-timer gap in A [ms] | 269 | 253 | 253 |

First pair 1.150, median ratio 1.150, both over 1.10: **FAIL**. The gauge
arrays were identical in all six runs.

Attribution (`t9_cost_diag.py`, a diagnostic, not the gate). Condition C
shows the Run screen with collection forced off. It measured 8.28 s against
B's 8.16 s and A's 9.21 s, so the cost is the collection path, not the
Run screen's painting. The column's own `_render` accounted for 0.27 s
(25 renders). The rest was repaint after every row and the card re-applied
their style sheets on each refresh.

`cost_6b_fallback.json` (`da904b7`: collect only while the column is
visible, 2 Hz, no re-styling on a same-state refresh), same script:

| | run 1 | run 2 | run 3 |
|---|---|---|---|
| B [s] | 8.26 | 7.75 | 8.15 |
| A [s] | 8.88 | 8.71 | 8.77 |
| A / B | **1.075** | 1.123 | 1.076 |
| longest gap in A [ms] | 239 | 242 | 243 |

First pair 1.075, median ratio 1.076, arrays identical: **PASS**. One pair
of three was 1.123. The long gap is at the run's end: a timed run put it
0.29 s before `running` went False, where the full-trace render arrives
with the result. Mid-run gaps are ≤ 56 ms, against ≤ 72 ms not collecting.

### R-VIEWER - FAIL as scripted; the banner part fixed and 0 ms; the resize part predates 6b

Native 3D case `tests/cases/native_3d_small.json` at a 75 mm cell (64 k
cells instead of 216 k). With 216 k cells, this machine's commit charge did
not hold the solve and the viewer child together. The first try's viewer
died at start-up (`OpenBLAS error: Memory allocation still failed`, 0
samples with a viewer, kept out of the results). All later runs set
`OPENBLAS_NUM_THREADS=1`.

| File | Code | Samples / with viewer | Wrong | Longest |
|---|---|---|---|---|
| `viewer_measure_6b.json` (as scripted: finish, resizes, dock, Setup ↔ Run, 2nd and 3rd start) | `da904b7` | 9863 / 2913 | 30 | **44.6 ms - FAIL** |
| `viewer_control_6b.json` (attribution) | `da904b7` | 8163 / 7377 | 146 | 49.1 ms |
| `viewer_ab_resize_90d2718.json` (resizes only, 6a's HEAD) | `90d2718` | 4831 / 3923 | 94 | 44.6 ms |
| `viewer_ab_resize_da904b7.json` (the same, 6b) | `da904b7` | 4833 / 4309 | 89 | 43.8 ms |
| `viewer_control_6b_fixed.json` | `d143445` | 8171 / 7264 | 133 (all resizes, or D's direct `banner.show()`) | 44.6 ms |
| `viewer_banner_6b_fixed.json` (run end + 5 hide / `show_finish` cycles) | `d143445` | 5472 / 4558 | 0 | **0 ms** |
| `viewer_banner_6b_final.json` (the same) | `440635c` | 5436 / 4468 | 0 | **0 ms - PASS** |

- **The banner appearing** (6b's own transition): 8.5-31 ms with the viewer
  window 70 px taller than its card at the bottom (the banner's height),
  never top-level. The card shrank in Qt's layout pass and the host's
  resize sync followed. Fixed in `d143445`: `show_finish` first calls
  `View3DHost.shrink_ahead(banner height + GAP)`. After the fix it is 0 ms
  over 4468 samples with a viewer, at the real run end and in five cycles.
- **The banner going** (what the next start does): 0 wrong in every run.
  F9 prevents measuring it at a real second start: neither a second Run
  nor an Initialise after a finished native 3D run shows a viewer window
  (B/C phases: 4 and 0 samples with a viewer).
- **Resizes 1600 ↔ 1100**: 22-49 ms per step, at 6a's HEAD as at 6b's, with
  the same overhangs (476 px right / 280-298 below on the shrink, 24-88 px
  on the grow). So they predate 6b. 6a's report measured 0 ms here; its
  sampler is lost, and this rect-based one does not reproduce that. At 6b
  only, a 1100 → 1600 grow sometimes adds one 29-39 ms stretch 70 px too
  tall at the bottom. Recorded as F13, not fixed (the host's resize sync,
  the §8.7 zone).

### The e2e (`_e2e_ui_run_finish.py`, real platform, final run at `440635c`)

`E2E UI RUN FINISH: PASS (19 checks, real)`:

- 144 k cells, the run took 189 s;
- the column was sorted by Z at all 5924 looks;
- all six rows read `waiting`, and G1, G2, G3 and G5 later showed a peak;
- the banner text is the stop reason verbatim plus the folder;
- one `notify_desktop` call, forwarded to the real one, `shown` True:
  `run_finish finished in 3 min 8 s. Highest peak: G5, 321 kPa at 1.06 ms.`;
- the title read `✓ Done · ● untitled · BlastLab`, and the button `Run again`;
- the tray icon was gone after its timer (shortened to 15 s in the e2e;
  60 s in the app);
- Earlier runs holds the first run's 1487-character log;
- the next start cleared the banner and `✓ Done`.

**The toast is real:** `gui6b-e2e-toast-screen.png` is a whole-screen grab
with the Windows notification at the lower right. Windows heads it
"Python 3.12", because the test process sets no AppUserModelID; the app's
`main()` sets `blastlab`. Focus Assist did not suppress it.

Not measured: a click on the real toast, so the foreground-lock behaviour of
`activateWindow()` (batch risk 7) is unknown. The click path is exercised
by calling `on_click` in R6.

Offscreen (`--offscreen`): 17 checks PASS. The real notify_desktop returns
False there, because there is no system tray.

### Screenshots (`t9_shots.py`, `440635c`)

`gui6b-<state>-<W>x<H>-<mode>.png`, dark and light, 1100 × 720 and 1600 ×
1000. States:

- `running`: a native 2D run with 2 rows peaked, 4 `waiting`;
- `clicked`: G3 enlarged by a click, with the now line;
- `finished`: the banner and the full traces;
- `planar-finished`: a planar case, header `R`, card `R 0.42 m`.

Plus the three e2e shots (`gui6b-e2e-*`: about 60 %, finished, the toast).
The light `running` / `clicked` shots predate `65d4228`, the now label's
colour in light.

From `shots_measure_6b.json`:

| Item | Board (line) | 1600 × 1000 | 1100 × 720 |
|---|---|---|---|
| columns | 280 / flex / 340 | 280 / 932 / 340 | 280 / 432 / 340 (with the banner too, after `440635c`) |
| enlarged card | ≈ 304 × 166 (265-288) | 302 × 165, plot 116 | same |
| list | header 28, rows 40 (290-331) | 302 × 272: 6 rows, no scrolling | same |
| sparkline | 90 × 24 (297) | 90 × 24 | same |
| banner | one line + 36 px action (183-189) | 932 × 62, two lines (D70) | 432 × 62 |
| view | - | 932 × 609; 932 × 539 with the banner | 432 × 271; **432 × 201 with the banner** |

With the banner up at 1100 × 720, the view is 201 px tall. U15's
240 px pin is for the idle layout. Batch risk 6 foresaw the banner taking
about 60 px; it takes 70 (62 + GAP).

### Contrast (`contrast_6b.json`, WCAG, plan §2.2)

Every new text pair is ≥ 4.5:1 in both modes after `65d4228`. Three rows
are close to the limit in light:

- `gauge` on `gauge_bg` (the selected G number, the peak time): 9.19 dark,
  4.52 light;
- `faint` on `gauge_bg` (the card's meta line, the selected row's unit):
  5.16 dark, 4.56 light;
- the now label (`accent_text` dark / `accent_soft` light): 7.59 dark,
  4.75 light. It was 4.37 in light with `accent_text`.

The banner's check mark is a graphic (3:1): 10.78 dark, 4.53 light. The
banner action is 11.27 dark, 5.17 light. The remaining pairs are listed in
the JSON.
