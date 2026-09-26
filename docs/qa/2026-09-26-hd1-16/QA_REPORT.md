# GUI QA - batch 2026-09-26-hd1-16-load-export

Branch `hd1-16-load-export`, HEAD `a3b3c7b`. Run on 2026-09-26. No application code was edited.

## 1. Environment

| | |
|---|---|
| OS | Windows 11 Enterprise 10.0.26200, RDP session |
| Python | 3.12.10 (Microsoft Store build) |
| GUI | PySide6 6.11.2, Qt app (`blastlab.ui`), dark theme |
| Pillow | 12.2.0 |
| Launch | `qa_hd1_16_harness.py` builds the window the same way `ui/app.main` does (crashlog, QApplication, theme, `MainWindow`). `QT_QPA_PLATFORM` is removed, so this is a real window. `qa_hd1_16_launch.py` runs the real entry point `python -m blastlab --case tc.json` as its own process. |
| Settings (8.2) | Before anything ran, `settings.load()['auto_cleanup']` was `False`, and so was the virtualised Store copy. Every GUI process used a private `BLASTLAB_SETTINGS` in the scratchpad, written with `auto_cleanup: false`. `env.auto_cleanup` was never called. |
| WSL | Not used. There was no solve. The only solver-mode click went towards `native`. |
| Screenshots | PIL `ImageGrab` fails in this RDP session most of the time (`OSError: screen grab failed`). Where it failed, windows were captured with Win32 `PrintWindow(PW_RENDERFULLCONTENT)` on the window's own HWND, which is still a real render. The harness log records which method each shot used. The HTML report was rendered with headless Edge. |
| Scratch files | Case files, the run output and the wall-load CSVs are all under the session scratchpad `...\scratchpad\qa\`. Nothing was written to the repo root. |

The harnesses are kept in this folder: `qa_hd1_16_harness.py` (real-window GUI), `qa_hd1_16_cli.py` (CSV against the core, report text, CLI), and `qa_hd1_16_launch.py` (real entry point).

## 2. Result table

| # | Check | Result | Screenshot(s) |
|---|---|---|---|
| 1a | "Structure" card not on screen. Win32 `IsWindowVisible` on its own HWND gives False, while the Heat card probe gives True. It stays hidden after a 2D visit plus a solver switch and back, after a case load, and at both resize sizes. | PASS | 01, 03, 06, 07 |
| 1b | "Loaded wall" card is on screen (Win32). It has the checkbox "Clearing on G1 (UFC 3-340-02 2-15.3.2)", "Wall height H [m]" and "Wall width W [m]". H and W are disabled (Qt) while clearing is off, and a real mouse click on the checkbox enables them. Unticking disables them again, and a disabled box ignores typing. | PASS (functional); see visual V1 | 01, 02 |
| 1c-i | A case JSON with `clearing: true`, H=3, W=4 loads into the form through the **app's Open case**. | **FAIL** (F1) | F1_open_tc_json_refused, F1b_open_starter_refused, 13_launch_case_dialog |
| 1c-ii | The same case **saves back identical through the app's Save case**. | **FAIL** (F1) | F2_reopen_app_saved_refused |
| 1c-iii | Form level: the file loaded with the HD 1.3 reader and `setup.set_case` shows clearing ticked, H=3, W=4 and H/W enabled. The form written back with the HD 1.3 writer is byte-identical to `tc.json`. The starter `t.json` also round-trips byte-identical and gets no wall keys. | PASS | 03 |
| 1d | Clearing ticked and H blank: the Setup card shows an error naming `wall_H_m`, the Run button is disabled, F5 is refused with a "Run" dialog naming `wall_H_m`, no run starts, and the other inputs are kept (clearing ticked, W=4, charge 5). | PASS | 04, 04b, 05 |
| 2a | Run of the starter case from the Run button. It is greyed while running, the window repaints mid-run, and the run finishes in 43.8 s with no exception. | PASS | 08, 08b |
| 2b | The status line text names `...\run\t_hd13_loads` ("SBEDS loads: 1 CSV in ...") and carries `nominal.csv: record ends while the load is still active: p = -45.3645 kPa at t = 30916.4 ms`. | PASS (text) | - |
| 2c | That status line is actually readable on screen. | **FAIL** (F2) | 09, 10, 11 |
| 2d | The folder holds `nominal.csv` and `nominal.txt`. All 448 CSV lines are exactly two comma-separated numbers, with no header, no BOM and no CR. | PASS | - |
| 2e | The CSV matches the core (`services.hd13.assess` on the same case) bit for bit: t [ms] = 1e3 t and p [kPa] = (p - P_AIR)/1e3. The sidecar peak, net impulse and still-active line match too. | PASS | - |
| 3 | The HTML report has no "Structural response" section, no verdict table (no "Does that verdict survive", "verdict", "COLLAPSE", "*_across_band") and no SDOF/ductility figure. Its three figures are Chamber, In the open and Heat. Its sections are Material, Confined, Unconfined, Heat x2, Quantity-distance and figures. | PASS | 12_report_part1, 12_report_part2 |
| 4a | `--hd13-wall-export` with clearing off writes `G1_g124`, `G1_g140`, `planemax_g124` and `planemax_g140`, each .csv + .txt, and every line is two floats. G1 and plane-max equal the `docs/hd13` columns E/1e3 and Emax/1e3 bit for bit. The G1 peak is 153.669 / 146.727 kPa. | PASS | - |
| 4b | With clearing on (H=3, W=4), only G1 gets `_cleared` and plane-max is byte-for-byte unchanged. The sidecar t_c equals 4S/((1+R)C_r) by hand (S=2, R=2/3), giving 14.0275 ms (g1.24) and 12.8041 ms (g1.40). The cleared CSV equals an independent Fig. 2-191a blend with max diff 0. | PASS | - |
| 4c | Rerun with clearing on gives an identical listing. Switching back to off removes the `_cleared` files. A user file in the folder survives, and clearing on with no H exits non-zero naming `wall_H_m` and leaves the folder unchanged. | PASS | - |
| R | Resize to 900x600 and 1600x1000. The window will not go below 1116x759 (outer), so 900x600 is clamped. Nothing overlaps, the Loaded wall card stays visible and Structure stays hidden. | PASS | 06, 07 |
| S | Startup and close of the real entry point. `python -m blastlab --case tc.json` starts, WM_CLOSE on the main window exits with code 0, and stderr is empty. | PASS (but see F1: the case is refused) | 13_launch_case_dialog, 13_launch_case_main |
| X | Project gate `blastlab/tests/_e2e_hd13_gui.py` (real window), with TMP pointed at scratch. | PASS, 21/21 | - |

Totals across the checks above: **16 PASS, 3 FAIL** (1c-i, 1c-ii, 2c). The GUI harness logged 36 pass and 6 fail. Of those 6, three are F1 and one is F2. One is V1. The last was a Win32 `IsWindowEnabled` probe that turned out to be invalid: Qt does not call `EnableWindow` on native *child* HWNDs, so Win32 reports True for a widget Qt has disabled. For enabled state I used Qt `isEnabled()` plus typing into the box instead. The CLI/core script logged 40 pass and 0 fail.

## 3. Failures

### F1 - The Qt app cannot open or save-and-reopen any HD 1.3 case file (1c)

It is **pre-existing** and was not introduced by this batch: the same loader was imported at BASE `01ab997`. I found no TODO entry for it. It blocks the "loads into the form, saves back identical" check in the real app.

Steps:
1. `python -m blastlab --hd13-new t.json`, or the clearing variant `tc.json`.
2. Open case... then choose the file, or start with `python -m blastlab --case tc.json`.

Expected: the 0-D form opens with clearing ticked, H=3 and W=4.
Actual: a modal "Open case - Not a blastlab case file" appears and the form is unchanged. At startup, the app then comes up on the 2D form.
Screenshots: `F1_open_tc_json_refused.png`, `F1b_open_starter_refused.png`, `13_launch_case_dialog.png`, `13_launch_case_main.png`.

Save case from the 0-D form does not raise an error. It writes `schema: "blastlab-case", version: 13, dim: 0` instead of `schema: "blastlab-hd13", version: 1`. All the values survive, including clearing, H, W and the six hidden Structure keys. The app then refuses to reopen that file: "Not a blastlab case file: unsupported or missing field 0." Screenshot: `F2_reopen_app_saved_refused.png`.

Origin:
- `blastlab/ui/app.py:19` imports `load_case` and `save_case` from `core.case`, which covers the blast cases only.
- `_open_case` (`app.py:408-437`) and `_save_case` (`app.py:457-466`) never dispatch to `models/hd13_case`.
- `models/case.py:372-373` refuses the `blastlab-hd13` schema.
- `models/case.py:376-377` has no `_CASE_TYPES[0]`, so it raises `KeyError 0`.

The form itself works. With the HD 1.3 reader/writer the round trip is byte-identical (check 1c-iii, which is what `test_ui_hd13_form.py` pins).

### F2 - The HD 1.3 status line is clipped and disappears after 12 s (2c)

This one is new to this batch in the sense that the batch put the CSV folder and the "still active" message there.

Steps: set a report file with the picker, which gives an absolute path, then Run the starter case at the default window size of 1400x950.

Expected: the user can read where the SBEDS CSVs went and the "record ends while the load is still active" warning.

Actual: the status QLabel is one line with no word wrap and no tooltip. The text is 3274 px wide and the label is 1168 px. Only "HD 1.3 report written: C:\...\scratc" shows. The CSV folder and the warning are never on screen (09, 10). After 12 s the line is cleared (11), and nothing about the run goes to the Run tab's Log, which stays empty (09).

With the default relative `hd13_report.html` I estimate the text at about 1218 px, which is still clipped at 1400 wide. Only the design-load caveat reaches the user, and only if they open the `.txt` sidecar.

Origin: `ui/app.py:104-107` (the label) and `ui/app.py:628-646` (`_hd13_done` builds a single line). `app.py:77-79` sets the 12 s timer. The batch plan said "the Qt status line / log shows it", but the log path is not implemented.

## 4. Visual findings

- **V1 - Disabled H/W boxes look the same as enabled ones.** The mean RGB of the H box is (34, 34, 34) in both states (01 vs 02 and 03). The labels do not dim either. `ui/theme.py:170` styles `QLineEdit:disabled` with the text colour only, so an empty disabled box does not change. Only the typing refusal shows the state.
- **V2 - The blank H field is not red-bordered.** When the validation error names `wall_H_m`, the box gets no red border (04). The message also says "(got 0.0)" for a box the user left blank.
- **V3 - The Run tab shows solver chrome for a 0-D run** (pre-existing): "Live slice / waiting for the solver...", step, t, dt and p max chips, and Exec buttons (08, 09).
- **V4 - The Model Preview for a valid 0-D case says "Enter a valid case to preview the model here."** (01, 03), which is pre-existing.
- **V5 - The window cannot be made smaller than about 1100x720 client**, so a 900x600 request is clamped (06). At that size the form is still usable.
- **V6 - The HTML report does not mention the `_loads/` CSVs or the still-active condition**, so a reader of the report alone does not learn that the load record ends at -45 kPa and is still "active" (12). This is informational, because the batch did not ask for it.

## 5. Numbers check (starter case, band off)

| Quantity | GUI / CSV / report | Core (`services.hd13.assess`, same case) | Match |
|---|---|---|---|
| CSV rows | 448 | 448 samples | exact |
| CSV t [ms], every row | as written | 1e3 * t | bit for bit |
| CSV p [kPa], every row | as written | (p - 101325)/1e3 | bit for bit |
| Last sample (status + sidecar) | p = -45.3645 kPa at t = 30916.4 ms | -45.3645424226778 kPa at 30916.399256328485 ms | 6 s.f. |
| Peak in CSV / sidecar | 1.00853 kPa at 7516.73 ms | 1.0085283419 kPa at 7516.73456 ms (sampled trace) | 6 s.f. |
| Net impulse in sidecar | -216203.85000140627 kPa*ms | trapezoid of core columns -216203.85000140627 | exact |
| Report "Peak overpressure" / "Time of peak" | 1.0 kPa / 7.4861 s | p_max 0.1023525 MPa abs = 1.0275 kPa over | at the report's precision |
| Wall G1 peak, clearing off | 153.669 / 146.727 kPa | max E_1.24 / E_1.40 / 1e3 | bit for bit |
| Wall G1 peak, cleared (H=3, W=4) | 104.48 / 100.932 kPa | independent Fig. 2-191a blend | diff 0 |
| t_c (Eq. 2-8) | 14.0275 / 12.8041 ms | 4*2/((1+2/3)*C_r), C_r 342.185 / 374.88 m/s | 6 s.f. |

Note for the owner, not a failure: the CSV is the sampled trace (about 69 ms spacing), so its peak, 1.0085 kPa at 7.517 s, sits 1.8 % below the model's true p_max of 1.0275 kPa at 7.486 s. That is the number the report quotes. Whether SBEDS gets the sampled or the true peak depends on `n_out`.

## Re-run after F2 fix

Branch `hd1-16-load-export`, HEAD `50ad65b` (fix commits `1b7817d` and `50ad65b`). Run on 2026-09-26. No application code was edited. F1 is known and was not re-tested.

**Setup.**
- Harness: `qa_hd1_16_rerun.py` in this folder. It builds the window the way `ui/app.main` does, at its own default size (1280x840 client, from `MainWindow.__init__`).
- Real window: `QT_QPA_PLATFORM` was unset, so this is not the offscreen platform.
- Win32 ground truth: the status label got `WA_NativeWindow` so it has its own HWND, and its rect was read with `GetWindowRect`.
- Screenshots: taken with `PrintWindow(PW_RENDERFULLCONTENT)`, because `ImageGrab` fails in this RDP session.
- Case: the starter case came from `python -m blastlab --hd13-new <scratch>\rerun\t.json`. It was loaded into the 0-D form with the HD 1.3 reader and `setup.set_case`, because Open case is F1. It was run with a real mouse click on Run, with the report file at `<scratch>\rerun\run\t_hd13.html`.
- Settings (8.2): `settings.load()['auto_cleanup']` printed False before the run. The GUI used a private `BLASTLAB_SETTINGS` (`<scratch>\rerun\settings.json`, auto_cleanup false). `env.auto_cleanup` was never called.
- WSL: not used.
- Run time: 45.3 s. There were no unhandled exceptions.
- Clean-up: `git status` shows nothing new outside this folder, and no python process was left behind.
- Result: the harness logged **35 pass, 0 fail**.

| # | Check | Result | Screenshot(s) |
|---|---|---|---|
| R1a | **Default size (1280x840 client, Win32 outer 1296x879).** The status line reads `HD 1.3 done - report and 1 SBEDS load CSV written; 1 load record ends while the load is still active (see Log)`. Qt `horizontalAdvance` gives 719 px against a contents rect of 1048 px. Win32 `GetWindowRect` of the label is (536, 910, 1584, 930), 1048 device px at DPR 1.0, `IsWindowVisible` is True, and the label lies inside the window. The stylesheet is `color: #ffb86b;`, which is `theme.cur('warn')`. In the screenshot crop, 592 px match the warn colour, and the ink runs from x=2 to x=711 of 1048, so nothing is cut. | PASS | R_1a_status_default_1280.png, R_default_status_crop.png |
| R1b | **Minimum width (1100 client, which is `minimumWidth()`; Win32 outer 1116).** Same text, 719 px against 868 px (Qt contents rect and Win32 rect (536, 910, 1404, 930)). Warn colour, ink ends at x=711 of 868, and there are 149 px to spare. Measured 2.3 s after the run finished, so still inside the 12 s window. | PASS | R_1b_status_min_1100.png, R_min1100_status_crop.png |
| R2 | The tooltip has 4 lines: `HD 1.3 report written: <abs>\run\t_hd13.html`, `SBEDS loads: 1 CSV in <abs>\run\t_hd13_loads`, `  <abs>\run\t_hd13_loads\nominal.csv` and `nominal.csv: record ends while the load is still active: p = -45.3645 kPa at t = 30916.4 ms`. The tooltip was shown for real with `QToolTip.showText`. Its window is on screen per Win32 at (558, 936)-(1695, 1026), and every line is readable. | PASS | R_2_status_tooltip.png |
| R3 | The Run tab Log gained exactly those 4 lines: the absolute report path, the load folder, `nominal.csv` (absolute) and the still-active line verbatim, identical to the tooltip line. The still-active text is also found verbatim in `nominal.txt`. The numbers are unchanged from the first run (p = -45.3645 kPa at t = 30916.4 ms). | PASS | R_3_run_log.png |
| R4 | 13.5 s after the run, the status text is `''` and the tooltip is `''`. The Log still holds all 4 lines. | PASS | R_4_after_12s.png |
| R5 | Regression: the Structure card is hidden (Win32 `IsWindowVisible` False, Qt hidden), while the Heat and Loaded wall cards are visible (Win32 probe sanity). With clearing off, H/W are disabled. A real click ticks clearing and enables H/W, which also brings up the two `wall_H_m`/`wall_W_m` errors. A second click unticks it and disables them again. Structure stays hidden after the toggles. | PASS | R_5a_wall_clearing_off.png, R_5b_wall_clearing_on.png |

**F2 is fixed.** All five re-run checks pass.

Visual notes from the re-run. None of them is a failure of the checks asked for.
- **V7 - The Log wraps long paths heavily.** The Log card is about 330 px wide at 1280 and about 270 px at 1100, so each absolute path wraps over 5-6 lines and the still-active line wraps over 3 (R_3). It is readable but dense.
- **V8 - The Log is not re-scrolled to the bottom after a resize.** After resizing to 1100, the view sits partway up, so the still-active line is scrolled out of view until the user scrolls (R_1b). `run_panel.on_log` pins the scroll only when a line is appended.
- **V9 - The "Clearing on G1 (UFC 3-340-02 2-15.3.2)" checkbox caption is cut off** at "...2-1" at the default 1280 width (R_5a, R_5b). The first run was at 1400 wide, so this is only visible now at the app's real default size.
- **Informational.** The paths in the Log and tooltip keep the 8.3 short form (`ROTEM~1.OFE`) because the harness passed a short-form scratch path, and `os.path.abspath` does not expand it. The paths are still valid, and a path from the file picker would be in long form.
