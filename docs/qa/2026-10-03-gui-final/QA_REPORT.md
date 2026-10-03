# QA report — redesigned Qt GUI, final pass (GUI-1 … GUI-10)

Branch `gui-redesign`, HEAD `c94917d`. Date 2026-10-03. Tester: gui-qa-tester agent.
All screenshots are in this folder; every one cited below was opened and looked at.
No application code was changed.

## 1. Environment

| Item | Value |
|---|---|
| OS | Windows 11 Home 10.0.26300. Primary screen 1920 × 1080 at 96 dpi (device pixel ratio 1.0), plus a second monitor |
| Python | 3.12.10 (Microsoft Store build) |
| Qt | PySide6 6.11.2, pyqtgraph 0.14.0, Pillow 12.2.0. Platform `windows` (`QT_QPA_PLATFORM` unset) |
| RAM | 8 GB. **Available at start: 244 MB** (the WSL VM was resident and idle). One app instance at a time, native solves only |
| Settings | Throwaway `BLASTLAB_SETTINGS` in the session scratchpad, written by `ui.testing.private_settings()`. Before the window was built, `auto_cleanup` was `False` and `runs_dir` was private (checked) |
| Safety | The CLAUDE.md §8.2 dry run printed `False`. `wsl -d Ubuntu -- pgrep -a blastFoam` was empty before and after. Nothing was read from or written to `/root/blastlab_runs`. At the end there were no stray python processes; the viewer child and the app were both gone |

**How the app was launched.**
- **Smoke test:** `python -m blastlab` with private settings, killed by its PID after 20 s. Result: no stderr, title `untitled · BlastLab`, working set 256 MB.
- **Driven session:** a driver script in the scratchpad built `MainWindow` the way `ui/app.main()` does (theme from settings, app icon, AppUserModelID `blastlab`), on the real platform. It ran step scripts inside the GUI process and kept one app alive for the whole session.
  - Real `QMessageBox` modals were grabbed and answered by clicking their own buttons.
  - The native Windows file pickers are not QWidgets, so `dialogs.open_file`, `save_file` and `pick_dir` were stubbed to return paths. `os.startfile` was suppressed.
  - The Windows notification was real (it was wrapped only to record it).
  - F5, Esc, Shift+Esc, Ctrl+C, Ctrl+S, Ctrl+Shift+S and Ctrl+O were sent as **real keyboard input** (`keybd_event`), with the BlastLab window in the foreground.
- **Closing:** a real `WM_CLOSE`. `app.exec` returned 0, with no uncaught exception and empty stderr.

## 2. Results

| # | Item | Result | Screenshots |
|---|---|---|---|
| 1 | Startup: no traceback, title, icon, dark theme | PASS | 001, 002 |
| 2 | Flow A: default 2D Setup → Run → Results (Field, Gauges, 3D) | PASS with findings (S3-6, S4-a) | 004-016, 095-101 |
| 3 | Flow B: native 1D → 2D chain from the Chain screen → one Results entry with STAGE tabs | Mechanics PASS. **Default seed gives a meaningless 2D stage (S2-1)** | 031-042, 061-064, 070, 077 |
| 4 | Flow C: 0-D HD 1.3 assessment | PASS (report + SBEDS CSV written). Busy-state findings (S3-3) | 043-056 |
| 5 | Flow D: Open / Save / Save as / Recent | Save, Save as and Recent work. **Unsaved edits are discarded without asking (S2-2)** | 057-060, 059 |
| 6 | Setup Z against R / W^(1/3) | PASS (6 charge masses) | 005, 058, 060, 065, 085 |
| 7 | Strip (Cells / ranks / memory) against `_validate` | PASS (3 cases) | 001-003, 005, 085 |
| 8 | Results table against `output.gauge_summary` | PASS (exact string match, 2D and 3D, and the exported CSV) | 013, 099 |
| 9 | Live-gauge list sorted by Z | PASS | 007-011 |
| 10 | Light mode on every screen | PASS, except the S3-2 strip squeeze | 072-078, 080, 081, 085, 086, 088 |
| 11 | 1100 × 720 on every screen | PARTIAL: the Run screen is cramped after a finished chain (S3-7). The harness clip check found 1 label (S4-e) | 065-078, 083-089 |
| 12 | 1600 × 1000 | PASS (dark) | 091-094 |
| 13 | Stop under 30 s (Shift+Esc): stops at once, no dialog | PASS | 022, 023 |
| 14 | Stop over 30 s: asks. *Keep running* keeps it running; *Stop the run* stops it | PASS | 024-029 |
| 15 | F5 starts; plain Esc does **not** stop; Shift+Esc stops | PASS (real keys) | 020-023 |
| 16 | Finish banner, `✓ Done` in the title, Windows notification | PASS (notification header reads "Python 3.12", S4-b) | 010, 011, 011b |
| 17 | F21 heights (Setup pill 42, + Gauge / + Obstacle 36, Chain pill 40) | PASS (measured on the real platform) | 083, 085 |
| 18 | F23 path copy without U+200B (mouse select + real Ctrl+C) | PASS | 030 |
| 19 | F27 tiles at a chain stage start | PASS as far as observable: stage 2 showed its own step 18, not stage 1's ~thousands. The `—` moment was too short to capture | 062 |
| 20 | F29 / F37 top bar at 1100 px, blastFoam, ✓ ✓, unsaved, dark + light | PASS. Every control is whole: chip 156/156 px, `0D · HD 1.3` 94/94. The name elides to `qa_ca…` with its tooltip and accessible name | 083-086 |
| 21 | F34 P MAX fits its tile | **FAIL at 1280 × 840 (S3-1).** OK at 1100 for `3,124 kPa` | 007, 096, 102, 103, 089 |
| 22 | D190 tree hover | PASS: fill = `theme.tree_hover()` (dark `#111114`, light `#f4f3f0`). The dark hover is barely visible (D192 is an open owner question) | 087, 088 |
| 23 | Export: Summary .csv | PASS (the file matches the table) | — |
| 24 | Show case / Load into 01 Setup | PASS. Asks *Replace / Keep editing*, drops the path, clears `✓ Done` | 104-113 |
| 25 | Close: process ends with no traceback | PASS. **No unsaved-changes question (S2-2)** | 114 |
| 26 | P1-7 (player frame 0, blastFoam) | **SKIPPED**: it needs a blastFoam run, which is not cheap on this 8 GB PC (244 MB available at start) | — |

Totals: 20 PASS, 2 FAIL (items 5 and 21), 3 partial (items 3, 4 and 11), 1 SKIPPED.

## 3. Failures

### S2-1 — The default 1D → 2D chain hands off after the shock has left the 2D domain, with every check green

**Steps**
1. Open Chain and pick route 1D → 2D.
2. Look at the seeds:
   - Stage 1 is `R 10.0 m · 1 mm`, and its hand-off card says "The profile when the wave reaches Outer (10.0 m)".
   - Stage 2 is `4 × 4 m · 25 mm · from 1D`, with the burst at z 2 m.
   - Both pills read `● case OK` and both stages read *Stage OK* (032, 033).
3. Optionally add gauges G1 (2.95, 0.5) and G2 (2.95, 1.5) to stage 2 (034).
4. Press **Run chain**.

**Expected:** either a warning or refusal before the run, or a 1D radius that fits inside the 2D domain. The Chain board's 1D stage runs to 1.5 m.

**Actual**
- The 1D stage hands off at t = 22.6 ms with the front at 10 m.
- The 2D stage starts in an already-ambient field: p max 101.5 kPa, colour bar 0.06-0.13 kPa, and the gauges read `waiting` all the way through (037, 038).
- Results shows `QA_chain` as a normal result: G1 / G2 peak **0.1 kPa**, no arrival, net impulse 0.28 / 0.30 kPa·ms (040). The banner says *Result ready*.
- The only warning is a transient status-bar line, `[warn] 1D profile shock radius (10.00 m) already reaches a boundary/obstacle - remap is not spherical there` (036, 037), which is gone by the end (038).

**Control:** the same chain with stage 1 at R = 1.5 m is correct. G2 reads 113 kPa at 3.22 ms (061-064, 077).

**Likely origin**
- The 1D stage is seeded from the 1D form defaults (`radius_m = 10`), as plan §8.1 directs: "everything else from the dimension's defaults".
- Neither the per-stage live checks (`ui/chain_panel.py` `schedule_checks` → `chain_route` stage errors) nor `run()` compares the 1D outer radius with the 2D stage's extent around the burst.
- The runtime warning comes from the remap in `core/profiles.py`.
- The seed is an owner decision. The missing cross-stage check is the finding.

### S2-2 — Open, Recent and closing the window discard unsaved changes without asking

**Steps**
1. Save as `qa_case_A.json` (Ctrl+Shift+S), then Save as `qa_case_B.json`.
2. Change Charge to 5. The top bar shows `● unsaved` and the status bar says `qa_case_B.json has unsaved changes` (060).
3. Choose Case menu ▸ Recent ▸ `qa_case_A.json`.

**Expected:** a "Replace the unsaved changes?" question, the same one **Load into 01 Setup** already asks (111: *Replace / Keep editing*).

**Actual**
- Case A opens at once and the edit to charge 5 is lost (059). No modal appeared.
- The same happens with Ctrl+O.
- Closing the window while it is dirty (title `● untitled · BlastLab`, 114) also exits at once with no question.

**Likely origin**
- `ui/app.py` `_open_case` (line 591) has no dirty check.
- `closeEvent` (line 1462) does not ask.
- Compare `_load_case_from_result` (lines 614-625).
- Not checked against base `0605522`, so this may predate the redesign.

### S3-1 — F34 still clips P MAX at 1280 × 840

**Steps:** at the default 1280 × 840, run the sample 2D case or any small 3D case and watch the P MAX tile during the first seconds.

**Expected:** `5.818e+05 kPa` fits (F34, D197).

**Actual**
- The value label is 87 px wide. `5.542e+05 kPa` needs 110-112 px even at the smallest face (14 px).
- `kPa` is cut to a 1-px sliver: `5.818e+05 ⁞` (007), `5.542e+05 |` (096, 103).
- A 3D run shows this for its whole duration, because p max stays above 10,000 kPa.
- At 1100 × 720 the strip wraps onto two rows, the tile is wider (115 px) and the value fits (089). GUI-10 verified the fix only in that geometry.

**Likely origin:** `ui/components.py` `StatTile(fit=True)` (the 14 px floor) and the Run strip's single-row tile width (`ui/run_panel.py` `_RunStrip`).

### S3-2 — After a Dark-mode toggle at 1100 × 720, the Run strip tiles are squeezed below their minimum

**Steps**
1. At 1100 × 720, on 02 Run after any run, take a shot (067: clean).
2. Toggle Case menu ▸ Dark mode (to light, or back).

**Actual**
- Each tile is 68 px tall against a `minimumSizeHint` of 75. The value labels are 22 px against a hint of 27.
- `100 %` is cut at the top, and `4.600 ms` overlaps `simulated` (074 light, 079 dark).
- It stays like that until the window is resized. At 1280 the tiles go back to 81 px (081).

**Likely origin:** `ui/run_panel.py` `_RunStrip.arrange()` is not re-run after the theme or font change.

### S3-3 — HD 1.3: Setup's Run stays live during the assessment, and the Run screen mixes in the previous run

**Steps:** in 0D · HD 1.3, press F5 or Run, then look at Setup, 02 Run and Chain during the ~20 s assessment.

**Actual**
- Setup's big **Run F5** stays orange and enabled (`isEnabled() == True`). The only sign of the run is `HD 1.3 assessment running…` in the status bar (053).
  - This contradicts the comment in `_run_single`: "F5 and Initialise Model reach here with Run greyed".
  - A second press is silently ignored.
- 02 Run does show the indeterminate bar (`HD 1.3 assessment · 2 s elapsed`). Right under it, though, it still shows the **previous** chain's banner *Result ready: QA_chain*, its 2D live slice and its gauges (054).
- Chain's Run chain stays enabled (055): P2-18 still reproduces.
- At the end, the result is a single status-bar line (051), with no banner and no notification.

**Likely origin:** `ui/app.py` `_set_hd13_busy` (line 952) does not disable `setup.strip.run_btn`, and `RunPanel` does not clear the banner for an HD run (F12 is the open owner call on the 0-D Run screen).

### S3-4 — Progress and time readouts are not honest at the ends of a run

**Sample 2D case (144 k cells)**
- 100 % was reached at about 80 s, but the run ended at 189 s. For 110 s (58 % of the wall time) the title read `100 % ·` while the animation, 20 field CSVs, the figures and `report.html` were written.
- At 35 s the strip said "about 19 s left".

**Chain stage 2 (profile start):** it opens at `85 %` with "about 0 s left" and then runs 13 s more (062).

**Stopped runs:** a run stopped at about 10 s reports `Stopped after 25 s` (023), and one stopped at about 39 s reports `Stopped after 1 min 2 s` (029). The post-processing time is counted as run time.

**Origin:** the solver's progress fraction, and `ui/run_clock.py`, which keeps counting through post-processing.

### S3-5 — The Results Gauges table hides the impulse columns at 1280 and 1100

**Steps:** open 03 Results ▸ Gauges for a 2D result.

**Actual**
- At 1280 × 840 the table shows Gauge … Pos. phase. `Pos. impulse` is cut mid-word, and Net impulse and Phase ended need a sideways scroll (013).
- At 1100 it shows up to `t peak` (069).
- The caption that explains net impulse is elided (`net impulse includes the negative ph…`).
- The board shows all nine columns. Impulse is the number a wall designer reads first.

**Origin:** `ui/results_gauges.py` `_fit_headers` / `_cap_height` (it scrolls rather than reflows, which was a deliberate choice).

### S3-6 — Results ▸ 3D shows a misleading placeholder

**Steps:** for a native 3D result (`QA_3d`), open 03 Results ▸ 3D.

**Actual**
- The view says: *"Run a 3D case - the live view attaches automatically. Finished 3D results replay here from the Results tab."* (098). The user is already on the Results tab and it is a 3D result.
- The viewer appears only after **Open the 3D viewer** in the Export column is pressed (100).
- For a 2D result the same text shows, and the button is disabled with the tooltip "3D results only" (016).
- Once embedded, the viewer leaves a black band of about 38 px at the top and about 15 px at the right of its frame (100). This is the F5 / F13 viewer-host family.

**Origin:** `ui/results_panel.py` (`view3d` placeholder text) and `ui/view3d_host.py` (frozen).

### S3-7 — 02 Run at 1100 × 720 after a finished chain: the live view collapses

**Steps:** run a chain to the end, then resize to 1100 × 720.

**Actual**
- The chain strip, the two-row stats strip, the banner and the dock leave about 70 px for the live slice.
- The image auto-ranges to r −30…40 m and is unreadable (067, 079, 074). At 1280 it is fine (038).
- Plan §4 says every screen must still work at 1100 × 720.

**Origin:** `ui/run_panel.py` centre-column layout (no minimum height on the view).

## 4. Visual findings (S4)

- **S4-a, axisymmetric labels.** In a 2D axisymmetric case:
  - the Setup preview's vertical axis reads `y [m]` (005);
  - the Results Field horizontal axis reads `x [m]` and its hover readout reads `x 2.71 · z 1.94 m` (014);
  - the gauge point list headers read `x  y` (005; this is F4).
  - Run's live slice and the boards use r / z (009; Results board: `r 1.87 z 1.06 m`).
- **S4-b, notification sender.** The Windows notification works and its text is right (`QA_final_2d finished in 3 min 9 s. Highest peak: G2, 129 kPa at 4.47 ms.`). Its header reads **"Python 3.12"**, not BlastLab (011b). The AppUserModelID has no Start-menu shortcut, so Windows falls back to the exe name.
- **S4-c, stale `✓ Done`.** It stays in the title after Save as of another case (`✓ Done · qa_case_A · BlastLab`) and after a dimension switch (043). Opening a case or Load into 01 Setup clears it.
- **S4-d, Setup strip at 1100.** The tile captions disappear: the radius, the cell size, `of 5 GB VM` and the Z unit `m/kg^1/3`. The Z tile then shows a bare `2.07–2.29` (065, 072, 085).
- **S4-e, clipping at 1100.** The progress caption is clipped: `… (p_edge = 1.014e+05 |`. The harness check reports it needs 419 px and has 404 (067).
  - The status-bar line `Chain: 2 stage(s) into C:\Users\…` also runs past the window edge at 1280 (035).
- **S4-f, 0-D preview text.** The 0-D Setup centre says *"Enter a valid case to preview the model here."* while the pill says `Case OK · 2 warnings · 3 notes` (043).
- **S4-g, colour scales.** Results Field *whole run* is dominated by the 4.4 MPa of the initial charge, so most frames are nearly black (014). The Run and Results boards draw a log colour bar (`p [kPa], log`); the build is linear.
- **S4-h, units.** Units sit in the field labels (`Charge [kg TNT]`), not as suffixes inside the inputs as the board shows (`Charge mass … kg`, plan §5.2, UX-11) (001).
- **S4-i, startup flicker.** For about 1 s after startup, Checks shows `WSL hardware not detected … assume a 4 GB VM` and MPI ranks reads 7, then 3, then 2 as the probe returns (001 → 002 → 003). Harmless.
- **S4-j, now label.** In the live-gauge card, the `now` label overlaps the end of the trace (037).
- **S4-k, dark tree hover.** It meets 4.5:1 (D192) but is visually almost invisible (`#111114` on `#0e0e10`, 087).

**Matches the boards:**
- top bar, pills with ✓, the solver chip menu (003), the dimension control;
- the Setup tree, the Derived card, the dock gauge table with Where `5 cm in front of Wall 1` (005);
- the Z rings and the R labels;
- Run's three columns, the Stop button showing Shift+Esc, Step through folded, the auto colour-range switch, the Log · Messages · Earlier runs dock;
- the Results list with the `latest` / `chain` badges, the method card, the Field time bar with the cyan arrival tick, the shaded positive phase;
- the Chain route buttons, the pipeline with the hand-off file on the arrow, the hand-off cards;
- the STAGE tab strip.

Light mode reads well everywhere (072-078).

## 5. Number checks

**Setup Z = R / W^(1/3)** (sample geometry: burst (0, 2), G1 (2.95, 0.5), G2 (2.95, 1.5)). Core: `math.hypot` and `ui.scaled_distance.gauges`.

| W [kg] | Screen G1 / G2 (or tile range) | Core G1 / G2 |
|---|---|---|
| 1 | 3.31 / 2.99 (R 3.31 / 2.99) | 3.3095 / 2.9921 |
| 2 | 2.37–2.63 | 2.3748 / 2.6268 |
| 3 | 2.29 / 2.07 | 2.2947 / 2.0746 |
| 3.5 | 1.97–2.18 | 1.9707 / 2.1797 |
| 5 | 1.75–1.94 | 1.7498 / 1.9354 |
| 25 (3D, G1 at 0.45 m) | 0.15 | 0.1539 |

**Strip against `validate_case` / `run_plan`**

| Case | Screen | Core |
|---|---|---|
| default 2D, blastFoam, 1 kg | 368 k · cell 6.59 mm · 2 ranks · 0.9 GB of 5 GB VM | 368,449 · 0.0065890 m · 2 · 0.9265 GB, `ram_gb` 5 |
| sample 2D, native, 1 kg | 144 k · cell 10.5 mm (ranks and memory hidden) | 143,641 · 0.010542 m · `run_plan` None |
| sample 2D, blastFoam, 3.5 kg | 159 k · cell 10 mm · 1 rank (serial) · 0.4 GB | 159,201 · 0.010004 · 1 ("below the 200,000-cell parallel floor") · 0.4003 GB |

**Results table against `output.gauge_summary.summarize_gauges`.** Same result object; the exported Summary .csv gives the same strings. Impulse is shown in kPa·ms, which is numerically equal to Pa·s; net impulse is net overpressure by design (CLAUDE.md §7).

| Gauge | Value | Screen | Core |
|---|---|---|---|
| G2 (Z 2.99) | Peak [kPa] | 128.9 | 128.878 |
| | Arrival [ms] | 3.996 | 3.99571 |
| | t peak [ms] | 4.474 | 4.47385 |
| | Pos. phase [ms] | 2.305 | 2.30463 |
| | Pos. impulse | 141.23 kPa·ms | 141.226 Pa·s |
| | Net impulse | 141.70 | 141.698 |
| | Phase ended | no | False |
| G1 (Z 3.31) | Peak | 106.4 | 106.403 |
| | Arrival | 4.747 | 4.74740 |
| | t peak | 5.204 | 5.20405 |
| | Pos. phase | 1.553 | 1.55294 |
| | Pos. impulse | 114.25 | 114.246 |
| | Net impulse | 114.79 | 114.791 |
| 3D G1 (QA_3d) | peak / arr / tpk / pos / pos. imp / net | 11996.2 / 0.038 / 0.096 / 0.058 / 397.13 / 397.15 | identical strings from `table_rows` |

**Notification against the table:** `G2, 129 kPa at 4.47 ms` against 128.9 kPa at 4.474 ms.

**Live-gauge list sorted by Z:** the gauges were entered as G1 (Z 3.31) then G2 (Z 2.99), and the list shows G2 2.99 above G1 3.31 (007-011), with `waiting` before arrival. A profile-start stage sorts by R and labels the column `R`, by design (037).

## 6. Not tested

- **P1-7:** it needs a blastFoam run (WSL). Skipped because of memory: about 250 MB available at start on an 8 GB PC with the WSL VM resident.
- **blastFoam solves in general** (native only, by instruction). The blastFoam strip was checked, but nothing was run in WSL.
- **Clicking the notification** to raise the window on Results.
- **The native file pickers themselves** (stubbed).
- **Step through.**
- **Exports other than Summary .csv**, and the animation export with each colour scale.
- **Base comparison** for S2-2 and S3-4.
- **1600 × 1000 in light mode.**

## 7. Screenshot index (selected)

| File | What it shows |
|---|---|
| 001 / 002 | Startup (grab and desktop) |
| 003 | Solver chip menu |
| 005 | Sample case, Gauges dock with Z |
| 006-011, 011b | Run: before, live, finished; the notification |
| 012-016 | Results: Field, Gauges, 3D for a 2D result |
| 018-029 | Overwrite and Stop dialogs, plain Esc, Shift+Esc, Stop under / over 30 s |
| 030 | F23 path selection |
| 031-042 | Chain (default seed) and its results |
| 043-056 | HD 1.3 |
| 057-060, 059 | Case menu, Save as, dirty state, Recent, Ctrl+O |
| 061-064 | Chain with R = 1.5 m |
| 065-082 | 1100 × 720 dark / light sweep and theme-toggle squeeze |
| 083-088 | Top bar at 1100 in blastFoam mode, tree hover |
| 089-094 | 1100 live run, 1600 × 1000 |
| 095-103 | Native 3D: Setup, live, Results 3D placeholder and viewer, P MAX at 1280 |
| 104-113 | Show case, Load into 01 Setup |
| 114 | Before close (dirty) |
