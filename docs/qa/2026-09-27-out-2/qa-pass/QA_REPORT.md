# OUT-2 "VTK output (ParaView)" card - real render-and-drive QA pass

2026-09-27, gui-qa-tester. Branch `out-2-vtk-output` at `24fd14b`. No application
code was edited. The harnesses are in `harness/`, the screenshots in `shots/` (every
file is prefixed `qt_` or `tk_`), and the implementer's shots one folder up were
left untouched.

## 0. Environment and method

| Item | Value |
|---|---|
| OS | Windows 11 Enterprise 10.0.26200. Screen 3360x1080, DPR 1.0 |
| Python | 3.12.10 (Store build) |
| Qt | PySide6 6.11.2, real window (`QT_QPA_PLATFORM` unset) |
| Tk | customtkinter (reports 6.0.0), real window |
| Imaging | Pillow 12.2.0 |
| ParaView | `C:\Program Files\ParaView 6.0.1\bin\pvpython.exe`, headless |
| Settings | private `C:\Users\rotem.ofek\blastlab_qa\20260927_out2\settings.json` with `auto_cleanup: false`, checked with `settings.load()` before every GUI |
| Runs | `C:\Users\rotem.ofek\blastlab_qa\20260927_out2\runs` (card tests) and `...\runs_real` (the real run) |

**Launch check.** `python -m blastlab` and `python -m blastlab --tk` both started with
no traceback. In a separate launch, each window was sent `WM_CLOSE` (the title-bar
X) and exited with code 0 and empty stderr (`harness/close_test.py`). Both windows
are titled `blastlab 1.0.0`, and both have a minimum size of 1100x720.

**Limitation: the session was locked for the whole pass.** LogonUI was running, so
`ImageGrab` fails with "screen grab failed" and a real cursor cannot hover.

- **Qt shots** are `QWidget.grab()` renders of the real, shown window.
- **Tk shots** are Win32 `PrintWindow` captures of the real top-level window
  (`harness/printwindow.py`).
- **Tooltips** were raised with the event their own handlers listen to, and each
  tooltip window was grabbed on its own:
  - Qt: a `QHelpEvent(QEvent.ToolTip)` sent to the label.
  - Tk: `<Enter>` on the CTkLabel's inner `tk.Label`, where `CTkLabel.bind` puts the
    binding.

  They were not produced by a physical mouse.

---

## 1. Failures

### F1 - "Peak overpr." is peak ABSOLUTE pressure, not overpressure (both GUIs, docs, the exported files)

- **Where:**
  - The matrix row label `Peak overpr.`.
  - Its tooltip `Peak overpressure - blastFoam field pMax`.
  - README "VTK files for ParaView": "fills p + peak overpressure".
- **Origin:**
  - The label and tip come from `blastlab/models/fields.py:139-148`
    (`VTK_QUANTITY_LABELS['pMax']`, `VTK_QUANTITY_TIPS['pMax']`).
  - The field itself is `fieldMinMax` with `minMax max` on `p` (the absolute
    pressure), in `blastlab/solvers/foam/writer.py:899-905`. That is a running
    per-cell maximum of absolute p, with no `pRef`. (The `impulse` function object
    next to it does subtract `pRef: P_AIR`.)
- **Evidence** (the real run, `harness/pmax_vs_p.py`): the final `pMax` was compared
  cell by cell with the running maximum of the exported absolute `p` samples.

  | Surface | Cells | pMax - max(sampled p) | Quietest cell |
  |---|---|---|---|
  | obstacles | 624 | min **0 Pa**, median 206 kPa, never negative | pMax **130,848 Pa** vs sampled max p 130,329 Pa |
  | slice_x_0.20 | 1156 | min **0 Pa**, never negative | pMax 8.54 MPa vs 7.13 MPa |

  If pMax were overpressure, the quietest obstacle cell would read about 29 kPa, not
  130.8 kPa.
- **Expected:** the label and tooltip say what the array holds (for example "Peak
  pressure (absolute)"). Alternatively, the field is written as an overpressure.
- **Actual:** an engineer who reads `pMax` in ParaView as the peak overpressure on the
  wall overstates it by 101.3 kPa. At the far-field levels a wall is usually
  designed for, that is a factor, not a percentage.
- **Screenshots:**
  - `shots/qt_tip_dark_3d_Peak_overpr.png`
  - `shots/qt_tip_light_3d_Peak_overpr.png`
  - `shots/tk_tip_dark_Peak_overpr.png`
  - `shots/qt_3d_step_1280_card.png` (the row, ticked by default on Sect. and Obst.)

### F2 - After a VTK run, the Results tab says nothing about the export, and its "VTK" button says there is nothing to write

- **Steps:**
  1. Run the real case (item 6) from the Qt window with the Run button.
  2. Open Results.
- **Actual:**
  - The `VTK` export button is greyed (`shots/qt_run_11_results.png`).
  - Nothing on the tab mentions `<MODEL>\vtk\`.
  - A greyed button's tooltip comes from `services/exports.why_not` →
    `SCRATCH_RELEASED` (`blastlab/services/exports.py:72-76, :95`): "...so there is
    nothing left to write as VTK." At that moment `vtk\` holds 258 files (42.4 MB).
  - This tooltip text was read from the code path, not captured live: the Results
    window had closed before I checked it.
- **The run log is right:**
  `[blastfoam] VTK: 10 volumes file(s), 160 sections file(s), 80 obstacles file(s) in ...\QA_OUT2_VTK\vtk; 7 written time(s) deleted in WSL`
  (`shots/qt_run_10_done_runtab.png` shows the end of it).
- **Expected:** after an OUT-2 run, the Results tab (or at least the greyed VTK button's
  tooltip) points to `<MODEL>\vtk\` and the series to open.

### Pre-existing failures that the card inherits (not OUT-2 regressions, but they hit the card)

**F3 - Tk at the 1100x720 minimum window: the right column is clipped.**

- **What the user sees:**
  - The VTK card's `Step` radio reads `Ste`.
  - The matrix's `Vol.` column is cut in half.
  - The Trigger card's combo arrow is cut.
  - Validation-strip rows are cut at the right edge ("...by the safety ca").
- **Measured** (`harness/qa_tk2.py`): canvas 534 px wide. Every card asks for
  264-442 px and gets 259 px.
- **Why it is pre-existing:** the same overflow is there in native mode with the VTK
  card hidden (Numerics 347 px, Boundaries 349 px). The VTK card (293 px) is not the
  widest card.
- **Screenshots:**
  - `shots/tk_3d_card_top_1100x720.png`
  - `shots/tk_3d_bottom_1100x720.png`
  - `shots/tk_3d_matrix_1100x720_crop.png`
  - `shots/tk_1100_native_3d_bottom.png`
- **Likely origin:** `gui/forms.py` card widths (`INPUT_MIN`, `LABEL_WRAP`) against
  the 13:7 column split in `SetupPanel` (`gui/forms.py:1023-1024`). The status rows
  have a fixed `wraplength=520` (`:1206`).

**F4 - Tk: switching dimension keeps the old scroll offset, so the form column goes blank.**

- **Steps:**
  1. Load a 3D case.
  2. Scroll the form to about 70 %.
  3. Press `1D`.
- **What happens:**
  - The form column is empty.
  - `canvas.yview` stays at (0.70, 0.87).
  - The scrollregion stays at the 3D height (`0 0 651 2790`).
  - The 1D form (1088 px) is unmapped.
- **Why it is pre-existing:** the same happens on `master` (`c73d4fc`, run from a
  `git archive` copy). OUT-2 makes it more likely: the Tk 3D form grew from
  **1848 px to 2790 px (+51 %)**, so users now scroll deeper before they switch.
- **Screenshots:**
  - `shots/tk_branch_1d_via_button_after_3d_scrolled.png`
  - `shots/tk_master_1d_via_button_after_3d_scrolled.png`
  - `shots/tk_1d_dark_window.png` (the same blank, hit by the main harness)
- **Likely origin:** `gui/forms.py` `SetupPanel._swap` (about `:1118-1123`) does not
  reset `yview` or the scrollregion. The Qt `_mode_changed` does reset the scroll.
  Tk `_mode_changed` resets it, but `_swap` does not.

**F5 - Qt: scrolled to the end, the 3D native form column is blank.**

- `shots/qt_3d_native_bottom_window.png`.
- The `QStackedWidget` takes its tallest page's height. The QA harness's own V04
  comment already records this.
- OUT-2's card makes the tallest blastFoam page taller, so the blank tail is longer.

---

## 2. Passes

| # | Test | Qt | Tk | Screenshots |
|---|---|---|---|---|
| 1a | Card in 1D/2D/3D, Time and Step, at 1100 and 1280: first tick fills the defaults | PASS (12 of 12) | PASS at 1280 | `qt_{1,2,3}d_{time,step}_{1100,1280}_card.png`, `qt_*_window.png`, `tk_3d_card_top_1280x840.png` |
| 1b | Matrix fits: no clipped header or row label, every box inside the grid, grid inside the card, no card overlap, no horizontal scroll | PASS at both widths (card 440 px at 1100, where the form goes to one column; 306 px at 1280) | PASS at 1280, **FAIL at 1100 (F3)** | `qt_3d_time_1100_card.png`, `qt_3d_step_1280_card.png` |
| 1c | Header and row tooltips show the full names, readable in both themes | PASS: all 14 rows and 4 headers (3D), 3 headers (2D), text equals `toolTip()` | PASS: 7 of 7, dark and light | `qt_tip_{dark,light}_{3d,2d}_*.png`, `tk_tip_{dark,light}_*.png` |
| 1d | Locked Gauge ticks distinguishable from live ones | PASS, weak (see V1) | PASS, clear (muted grey vs accent blue) | `qt_3d_matrix_{dark,light}_zoom4x.png`, `tk_3d_{dark,light}_matrix_crop.png` |
| 1e | Inactive cadence box greyed: `isEnabled` / `state` follows Time and Step for every family | PASS | PASS (`disabled`, text `#9aa4b2` dark / `#5f6b7a` light) | `qt_3d_step_1280_card.png`, `tk_3d_dark_card_crop.png` |
| 1f | Plane `q, 1` typed plus Return is refused with a reason; `y, 1.4` is accepted | PASS: "axis must be x, y or z, not 'q'" | PASS, same text | `qt_3d_plane_q1_refused_1100_card.png`, `qt_3d_plane_y14_1100_card.png`, `tk_3d_plane_q1_refused_crop.png` |
| 1g | Also refused or flagged (not asked for): `x 0.5 1` ("expected 2 values"), `x, abc` ("not a number: abc"); `z, 9` enters the table and the strip says "plane z = 9 m is not inside the domain (0..1.5 m, ends excluded)" | PASS | - | `qt_3d_plane_z9_window.png` |
| 1h | Bad cadence values: `-1` and `0` give "VTK volumes: the interval must be > 0 (ms)"; `abc` and empty give "'VTK Volumes every [ms]' is not a number"; `2.5` steps gives "must be a whole number". Other inputs kept. `abc` in the greyed box does not block | PASS | - | `qt_bad_vtk_*_window.png` |
| 2 | Tk 3D real window: right column 2778 px (left 1412 px); scrolled to the end, the Trigger card is fully in view (1280: y 324-460 of 472; 1100: 204-340 of 352); validation strip on screen | PASS | PASS | `tk_3d_bottom_1280x840.png`, `tk_3d_bottom_1100x720.png` |
| 3a | Native mode hides the card (Qt `isHidden()` True with `isEnabled()` True, so not greyed; Tk `winfo_manager() == ''`) | PASS | PASS | `qt_3d_native_top_window.png`, `tk_3d_native_bottom.png`, `tk_3d_native_mid.png` |
| 3b | Back to blastFoam restores the ticks, families and a Step mode exactly | PASS | PASS | `qt_3d_foam_again_card.png`, `tk_3d_foam_again_crop.png` |
| 3c | Case saved through the real Save path in native mode has no `vtk_` key; saved in blastFoam mode it carries both keys | PASS | PASS | (JSON in `...\blastlab_qa\20260927_out2\work\`) |
| 4 | 2D Obstacles family, no obstacles: strip error "VTK obstacles: the case has no obstacles - nothing to sample"; typing an obstacle plus Return / + clears it | PASS | PASS | `qt_2d_no_obstacles_window.png`, `qt_2d_with_obstacle_window.png`, `tk_2d_no_obstacles.png`, `tk_2d_with_obstacle.png` |
| 5a | Open case with keys (sections Step 10, planes x 0.5 / z 0.3, sections p+impulse, obstacles pMax; volumes Time 0.5 ms, p+T): every value shown, greying per family mode | PASS | PASS | `qt_3d_loaded_with_keys_card.png`, `tk_3d_loaded_with_keys_crop.png` |
| 5b | Then a case without keys: P12 defaults (off, Time, 1 ms, 25 steps, no planes, empty matrix, steps boxes greyed) | PASS | PASS | `qt_3d_loaded_without_keys_card.png`, `tk_3d_loaded_without_keys_crop.png` |
| 5c | Open a native case: the card is hidden | PASS | - | - |
| 6a | Real run, Qt GUI: Run disabled and Stop enabled while running; window repaints (live slice); finished in 354 s; 991 steps; no dialogs | PASS | - | `qt_run_00_setup_card.png`, `qt_run_0{1..4}_running.png`, `qt_run_10_done_runtab.png` |
| 6b | `<MODEL>\vtk\` well-formed, checked with a text reader: every `.vtk` starts `# vtk DataFile Version 2.0` / title / `ASCII` or `BINARY` / `DATASET ...`; every `.vtk.series` is JSON without BOM, version 1.0, times strictly ascending, every named file exists and is > 0 B, no orphan files | PASS (258 files, 42.4 MB, 0 problems) | - | `vtk_folder_listing_qa.txt` |
| 6c | Matches `../vtk_folder_listing.txt`: the same 258 files, the same counts (10 / 160 / 80), the same surface times and byte sizes | PASS (see §4) | - | - |
| 6d | WSL scratch released: manifest `deleted: true`, `wsl test -d` returns 1, `not_converted: []`, `failed: []`, 7 writes deleted in WSL | PASS | - | - |
| 6e | Run log says what was exported | PASS | - | `qt_run_10_done_runtab.png` |
| 6f | Results tab says what was exported | **FAIL (F2)** | - | `qt_run_11_results.png` |
| 6g | pvpython loads the series headlessly (LegacyVTKFileReader): volumes 10 steps, 38,296 cells, p/rho/U (+cellID); obstacles/pMax 40 steps, 624 cells; both section planes 40 steps | PASS | - | (output in §4) |
| 7 | Light mode as well as dark, 1D/2D/3D | PASS; see V1 and V2 | PASS; see V4 | `qt_{1,2,3}d_light_card.png`, `qt_3d_light_window.png`, `tk_{1,2}d_light_window.png`, `tk_3d_light_card_crop.png` |
| - | Close: `WM_CLOSE` exits with code 0 and no stderr, both toolkits | PASS | PASS | - |

---

## 3. Visual findings (work, but look wrong)

- **V1 - Qt locked Gauge column (item 1d), weak.**
  - Dark: a locked tick is a slate-grey check on the same dark box, and a live tick is
    a white check. At 1x the difference is small: mean box RGB (56,58,60) locked vs
    (63,63,63) live. Tk is much clearer: grey fill vs accent blue.
  - Light: the polarity is inverted. The locked *unticked* boxes are drawn white,
    while live unticked boxes are light grey (as "Show mesh" and "Dark mode" are). So
    the disabled column looks the more active one.
  - Screenshots: `qt_3d_matrix_dark_zoom4x.png`, `qt_3d_matrix_light_zoom4x.png`.
- **V2 - Qt greyed cadence box.** Only the text colour changes: the value turns
  blue-grey, and the box background is identical (mean RGB 36 vs 37). It reads as
  disabled, but it is subtle, and the blue tint can read as "link".
  `qt_3d_step_1280_card.png`.
- **V3 - The plane entry keeps rejected text across Open case.**
  - `x 0.5 1` was refused, then a different case was opened. The text stays in the
    entry, and the hint goes back to the idle "add a row: axis position [m]", so the
    stale text looks accepted.
  - Screenshots: `qt_3d_loaded_with_keys_card.png`, `qt_3d_light_window.png`.
  - Origin: `ui/fieldform.py` `PointList.set` (`:334-341`) does not clear `entry`.
- **V4 - Tk light mode (pre-existing).** The sidebar's unselected `native` segment and
  the unselected `1D/2D/3D` buttons are almost invisible (white on light grey).
  `tk_2d_light_window.png`, `tk_1d_light_window.png`.
- **V5 - Qt, all right-column cards (pre-existing).** Each card's right edge touches the
  scrollbar with no margin: card right = viewport width = 620 px at 1280, and the
  inputs look cut flat. `qt_3d_time_1280_rightedge_zoom4x.png`.

---

## 4. Numbers check - this run vs the implementer's listing

The case is `_e2e_vtk_3d.py` case C:

- 0.6 m cube, 4 cm base cells refined for 20 kg TNT;
- one obstacle box and one gauge;
- t_end 1 ms, serial, adaptive write off;
- sections and obstacles p + pMax every 25 steps, with the extra plane x = 0.2;
- volumes p, rho, U every 0.1 ms.

It was opened from a case file in the real Qt window and run with the Run button.

| Quantity | Implementer (`../vtk_folder_listing.txt`) | This pass (`vtk_folder_listing_qa.txt`) |
|---|---|---|
| Steps / cells (model manifest) | 991 / 35,937 | 991 / 35,937 |
| Files, total | 258, 42.4 MB | 258, 42.4 MB |
| volumes count, times | 10, 0.0001 .. 0.001 | 10, 0.0001 .. 0.001 |
| sections / obstacles counts | 160 / 80 | 160 / 80 |
| surface times | 0, 9.8229778e-06 .. 0.00097955278 | identical |
| obstacles/p `t_0.00010616096.vtk` | 33,285 B | 33,285 B |
| slice_x_0.20/p `t_0.00010616096.vtk` | 67,402 B | 67,402 B |
| volumes `t_0.0001.vtk` | 2,956,986 B | 2,956,987 B (+1 B: the VTK title line is the WSL run-dir name, `..._p41036-00` vs `..._p4616-02`) |
| deleted_in_wsl | 0.0002 .. 0.0008 (7) | 0.0002 .. 0.0008 (7) |
| not_converted / failed | [] / [] | [] / [] |

pvpython (headless, the reader ParaView's File > Open uses):

```
volumes\volumes.vtk.series: LegacyVTKFileReader, 10 time steps, [0.0001, 0.0002] .. [0.001]
   t=0.0001: 38296 cells, 42149 points, cell arrays cellID, rho, p (5425.7 .. 3.93e8), U
   t=0.001:  38296 cells, p 1531.4 .. 91139.6
obstacles\pMax.vtk.series: 40 time steps; 624 cells; t=0 pMax 0..0; final 130848 .. 3.99e9
sections\slice_x_0.20\p.vtk.series: 40 steps; 1156 cells; t=0 p = 101325 everywhere
sections\slice_y_0.30\p.vtk.series: 40 steps; 1072 cells
```

**Observation (not OUT-2):** the volume files hold **38,296** cells, but the Setup strip
and the model manifest say `~35,937 cells` (33³, the pre-carve estimate). That is 6.6 %
off. The section plane named `slice_x_0.20` sits at x = 0.2029 m (snapped, per Q6). The
live slice shows `y = 0.29 m`, while its VTK series is `slice_y_0.30`: the name keeps
the requested position, which is by design but visible.

---

## 5. Confusions for an engineer entering these settings

1. **ms vs s.**
   - The card says `Every [ms] (simulated time)`, while the rest of the form says
     `End time [s]`.
   - The case JSON stores this value in ms (Q3) but `t_end` in s.
   - The files and ParaView's time bar are in **seconds** (`t_0.0005.vtk`, series
     `"time": 0.0005`).
   - So the value typed as `0.5` reappears as `0.0005` in ParaView. One line on the
     card saying that files and ParaView use seconds would close this.
2. **`Sect. / Obst. / Vol.`**
   - The tooltips explain them: "Sections - the live-slice plane and the extra
     planes", "Obstacles - their walls", "Volumes - the whole 3D domain".
   - But `Vol.` reads like the quantity "volume".
   - The same column is `Domain` in 1D/2D and `Vol.` in 3D.
   - In 2D the columns run `Obst. | Domain` while the family boxes above run
     `Whole domain`, `Obstacles`: the opposite order.
3. **An internal ticket ID in the UI.** "Quantities (Gauges: fixed until OUT-4)" and
   the tooltip "...(fixed until OUT-4)" mean nothing to a user.
4. **A Gauge column inside a "VTK output" card** suggests that the gauges get VTK
   files. They do not: it only states which fields the gauge TSV carries.
5. **"the live-slice plane is always written"** is true only when *Sections and
   obstacles* is ticked.
6. **Step-mode volumes get no write-count or disk note.** Time mode does ("one write
   every 1 ms, up to 45 writes (~3.2 GB ...)"). "Every 25 steps" on a large 3D case
   can mean thousands of full-field writes, with no warning (strips for
   `1D/2D/3D_step` in `shots/qt_results.json`).
7. **A Time-mode volumes cadence changes the solve.** Writes land exactly on their
   times and clip dt (P14: +4.2 % peak at the near-field gauge). The note warns only
   that "a dense cadence slows" the live view. An engineer would expect an output
   setting never to change the answer.
8. **Row names.** `Energy` is `rhoE` (total energy per unit volume). `Products` is the
   products' volume fraction (`alpha.expl`). `Peak overpr.` is wrong (F1). The
   tooltips give the field names, but not what the quantities are or their units.
9. **In 3D the `Obst.` column is ticked by default even with no obstacles.** The strip
   only notes "the case has no obstacles - only the sections are written". That is
   fine, but it is a silent no-op tick.
10. **An error the GUI cannot reach (pre-existing).** "VTK volumes and the write budget
    both pin the write interval - clear one" exists only headless. The Qt form has no
    `write_budget` field, and opening a case with `write_budget: 10` drops it silently
    (`harness/qa_write_budget.py`).

---

## 6. Housekeeping

- **WSL:** `wsl -d Ubuntu -- pgrep -a blastFoam` was empty before the run and after
  it. The run's scratch `/root/blastlab_runs/20260927-035403_3d_p41036-00` is gone.
- **Evidence kept:** the run's model folder is
  `C:\Users\rotem.ofek\blastlab_qa\20260927_out2\runs_real\QA_OUT2_VTK`. The
  throwaway `master` copy used for F4 was deleted.
- **Processes:** no Python or pvpython processes are left running.
- **Harness close codes:** the Qt tooltip harness's own process exited with code 255
  after `win.close()`. Its output was complete; the cause is not established and may
  be harness teardown. The real app closes with 0 (§0).
