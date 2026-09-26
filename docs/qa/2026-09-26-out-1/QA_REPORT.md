# QA report - OUT-1 model folder, both GUIs (2026-09-26)

Real render-and-drive pass on branch `out-track` at `1e593c3`, in real windows
(`QT_QPA_PLATFORM` unset) on the owner's desktop. Every claim below comes from
a screenshot in `shots\` that was looked at, a value read out of a live widget,
or a file read from disk. No application code was changed.

## 1. Environment

| | |
|---|---|
| OS | Windows 11 Enterprise 10.0.26200 |
| Python | 3.12.10 (Microsoft Store build) |
| Qt | PySide6 6.11.2, real `windows` platform |
| Tk | tkinter + customtkinter (`python -m blastlab --tk`) |
| Pillow | 12.2.0 (screenshots of native windows use Win32 `PrintWindow`, not screen grabs) |
| WSL | `Ubuntu`, blastFoam 6.2.0; `pgrep -a blastFoam` empty before every solve |
| Settings | `BLASTLAB_SETTINGS=C:\Users\rotem.ofek\blastlab_qa\out1_20260926_191440\settings.json`; `settings.load()` returned `auto_cleanup=False` before any window was built |
| Runs folder | `C:\Users\rotem.ofek\blastlab_qa\out1_20260926_191440\runs` (fresh; not Desktop, Documents or OneDrive) |
| Launch | harness scripts that import `ui.app.MainWindow` / `gui.app.App` (under `scripts\`), plus the real entry points `python -m blastlab` and `python -m blastlab --tk` started as separate processes |

WSL solves, all small: a blastFoam 1D run (301 cells, 45 s), a 2D axisymmetric
run stopped after 60 s (16,562 cells), and its resume from the Tk run browser
(95 s). Afterwards `/root/blastlab_runs/20260926-19*` was empty (both scratches
were released) and no `blastFoam` was running. The owner's runs were listed by
the run browser but not touched.

## 2. Result table

| # | Item | Qt | Tk | Evidence |
|---|---|---|---|---|
| 1a | Run tab: Runs folder box + Browse / folder icon, Model box | PASS | PASS | `qt_01_run_tab_start.png`, `qt_02_run_tab_start_frame.png`, `tk_01_run_tab_start.png` |
| 1b | Tooltips | PASS (Browse has none, V3) | PASS | `qt_03_tooltip_runs_dir.png`, `qt_04_tooltip_model.png`, `tk_02..04_tooltip_*.png` |
| 1c | Tab order | PASS: runs_dir, Browse, Model, Initialise Model (static chain and real Tab keys) | PASS: runs_dir, then Model (the icon button takes no focus) | `qt_pass.out.txt` item1_focus_chain, `tk_pass.jsonl` |
| 1d | Runs folder remembered, Model not | PASS (window closed and a new window opened) | PASS (two separate processes) | `qt_57_run_tab_reopened.png`, `entry_points.jsonl` tk_persist_a, and the process-B printout (section 3.1) |
| 1e | Browse opens in the current runs folder | PASS | PASS (`initialdir` = runs folder) | `extra_qt_browse.png`, `extra_tk_browse.png` |
| 2 | Refusal dialogs | PASS: 14 cases | PASS: 6 cases | `qt_05..18_dialog_*.png`, `tk_05..10_dialog_OK.png` (texts in section 3.2) |
| 2b | Initialise Model goes through the same gate | PASS | PASS | `extra_qt_init_refused.png`, `extra_tk_init_refused.png` |
| 3 | Overwrite Yes/No, No is the default; No leaves the folder, Yes overwrites | PASS (Enter picks No) | PASS (default id = IDNO; Enter picks No) | `qt_19_dialog_enter.png`, `qt_20_dialog_no.png`, `qt_21_dialog_yes.png`, `tk_11_dialog_enter.png`, `tk_12_dialog_No.png`, `tk_13_dialog_Yes.png`, `tkt_01_dialog_enter.png` |
| 4 | Native 1D and 2D runs: the folder matches the README table and the manifest | PASS (1D, planar 2D, axisymmetric 2D) | PASS (1D, planar 2D) | `qt_23_1d_done.png`, `qt_25_QA_2D_done.png`, `qt_31_QA_2DAX_done.png`, `tk_15_1d_done.png`, `tk_17_2d_done.png`, `folders.json` |
| 5 | blastFoam run: `foam\` + SHA256SUMS, scratch released, VTK button explains it | PASS | - | `qtf_02_foam1d_done.png`, `qtf_03_foam1d_results.png`, `qtf_04_foam1d_vtk_tooltip.png` |
| 5b | Stopped blastFoam run keeps its scratch and says why | PASS | - | `qtf_06_foamstop_done.png`, `qt_foam.jsonl` F2_done |
| 6 | Setup Outputs: file-name rows hidden, Animation format shown, no 1D Outputs card, no Remap file row, no 0-D Report file row | PASS | PASS | `qt_32..40_setup_*.png`, `tk_22..24_setup_*_bottom.png` |
| 7a | Chain tab: no workspace box, new hint text | PASS | PASS | `qt_41_chain_tab.png`, `tk_25_chain_tab.png` |
| 7b | Chain refusal ends "The Runs folder and Model boxes are on the Run tab." | PASS | PASS | `qt_42_dialog_ok.png`, `qt_44_dialog_ok.png`, `tk_26_dialog_OK.png` |
| 7c | Native chain 1D->2D (and 1D->2D->3D): `1d\`, `2d\`, (`3d\`), hand-offs at the root, root manifest | PASS (5 chains) | PASS (6 chains that completed) | `qt_47_chain_done_run_tab.png`, `tk_27_chain_done.png`, `folders.json` |
| 7d | Tk chain process stability | - | **FAIL** (1 of 7 Tk chains: the process died, F1) | `tk_timing.out.txt` |
| 8a | HD 1.3 from the GUI: `hd13_report.html`, `hd13_loads\`, `MODEL.json`, `manifest.json` | PASS (2 assessments) | n/a (no Tk HD 1.3 form) | `qt_54_hd13_done.png`, `qtf_12_hd13_starter_done.png` |
| 8b | Chain and resume during the assessment say "A run is already in progress." | PASS | - | `qtf_09_dialog_ok.png`, `qtf_11_dialog_ok.png`, `qtf_10_chain_during_hd13.png` |
| 8c | HD 1.3 `MODEL.json` opens again with Open case | **FAIL** (F2) | - | `qtf_13_dialog_ok.png` |
| 9 | Results export dialogs open in the model folder | PASS (Summary CSV, Report, PNGs) | PASS (the same three) | `qt_27..29_export_*.png`, `tk_19..21_export_*.png` |
| 10 | Tk run browser: Resume really starts a run | PASS: started, finished, wrote `TK_RESUME\`, released the scratch | - | `tkr_01_run_browser.png`, `tkr_02_resume_running.png`, `tkr_03_resume_done.png`, `tkr_04_resume_results.png` |
| 11 | Displayed gauge peak = `gauges_<d>d_summary.csv` = TSV = core | PASS | PASS | `qt_26_results_gauges_QA_2D.png`, `tk_18_results_gauges_2d.png`, section 5 |
| 12 | Switching to the Run tab when a later chain stage starts | PASS in Qt (one stall of 0.46 s or less); Tk: a single `root.update()` runs 10.7-13.5 s, but the window keeps answering (1.3 s at most) | see section 6 | `responsiveness_*.jsonl`, `tk_timing_sample.jsonl` |
| - | Resize 900x600 and 1600x1000 | PASS (900x600 is clamped to the 1100x720 minimum) | - | `qt_55_run_tab_900x600.png`, `qt_56_run_tab_1600x1000.png` |
| - | Startup and close through the real entry points | PASS: exit 0, empty stderr (Qt closes in 0.2 s, Tk in 4.0 s) | PASS | `entry_qt_start.png`, `entry_tk_start.png`, `entry_points.jsonl` |

Counts: 2 FAIL (F1 in Tk, F2 in Qt). Every other row passes. Section 4 lists
smaller defects that do not fail an item.

## 3. What works (the details behind the PASS rows)

### 3.1 Run tab
- **Qt:** `Runs folder` [box] `Browse…`, then `Model` [box] on the control card
  (`qt_02_run_tab_start_frame.png`). Tooltips, read from the live widgets:
  - Runs folder: "Required. The folder that holds one sub-folder per model; a
    run writes every file it produces into <Runs folder>\<Model>. Remembered
    between sessions."
  - Model: "Required. The model folder <Runs folder>\<Model> that receives every
    file of this run (a valid Windows folder name, at most 100 characters). It
    also names the run in the Results picker."
- **Tk:** the same two tooltips, and the folder icon has "Choose the runs folder"
  (`tk_03_tooltip_runs_browse.png`).
- **Memory:** Qt wrote `runs_dir` to settings when Return was pressed and again
  on close. A new window came back with the folder filled in and Model empty.
  Tk, in two separate processes: process A typed a folder and pressed Return,
  then closed; process B printed `B runs box = ...\runs\PERSIST_DIR | model box = ''`.

### 3.2 Refusals: exact texts (Qt title "Run", Tk the same)
| Input | Text |
|---|---|
| empty runs folder | `Runs folder is empty` |
| missing folder | `Runs folder does not exist: C:\...\runs\no_such_dir` |
| `bad:name` / `a/b` | `Model name: a folder name cannot contain :` / `... cannot contain /` |
| `CON` | `Model name: "CON" is a reserved Windows device name` |
| `model.` and `..` | `Model name: a folder name cannot end with a dot or a space` |
| empty name | `Model name: the name is empty` |
| 101 characters | `Model name: at most 100 characters (this one has 101)` |
| runs folder = `~\Desktop` | `Runs folder cannot be the Desktop itself: C:\Users\rotem.ofek\Desktop` |
| runs `~`, model `Desktop` | `Model name: Desktop in C:\Users\rotem.ofek is or holds the Desktop - choose another name` |
| runs `C:\Users`, model `rotem.ofek` | `Model name: rotem.ofek in C:\Users is or holds the Desktop - choose another name` |
| foreign folder (also `foreign` for `FOREIGN`) | `C:\...\runs\FOREIGN was not created by blastlab - choose another model name` |
| empty existing folder | asks the overwrite question (answered No; the folder is unchanged) |

After all of these: no worker had started, the runs folder listing was the
same as before, the home folder listing was the same, and `FOREIGN\notes.txt`
was untouched.

### 3.3 Overwrite question
Text (both toolkits): *"QA_1D already exists in C:\...\runs. Overwrite? The
previous run's files will be deleted."*, title "Model folder".
- **Qt:** `defaultButton()` = `&No`, and focus is on `&No`. `QTest.keyClick(Return)`
  gave No, and every file kept its mtime. An explicit No did the same. Yes
  deleted `old_run.txt` and started the run.
- **Tk:** Win32 `DM_GETDEFID` = 7 (IDNO), and `&No` carries `BS_DEFPUSHBUTTON`.
  A Return posted to the dialog closed it as No, and the folder was unchanged
  (`tkt_01_dialog_enter.png`). No and Yes behave as in Qt.

### 3.4 Native model folders (`folders.json`)
For every stage folder, `manifest.outputs` equals the files on disk (excluding
`manifest.json` and `.blastlab-model`), byte sizes match, `failed == []`, no
file has size 0, and `MODEL.json` loads back through `load_case`. The manifest
keys are exactly those of plan §2.2 plus `failed`.
- 1D `QA_1D`: `.blastlab-model MODEL.json fields\ figures\ gauges\ manifest.json profile.txt report.html run.log`; `missing = [animation: "replay frames were not recorded"]`; n = 400 cells / 1 rank / 1355 steps; `git_commit 1e593c3`.
- Planar 2D `QA_2D` (60 frames recorded): `animation.mp4` present, no profile, `missing = [profile: "3D / planar 2D has no profile export"]`.
- Axisymmetric 2D `QA_2DAX`, no frames: `profile_2d.npz` present, `missing = [animation]`.
- Tk `TK_1D` and `TK_2D`: the same trees as Qt, byte for byte.

### 3.5 blastFoam (Qt)
- `QA_FOAM1D`: `foam\{0,constant,system,postProcessing,log.blastFoam,SHA256SUMS}` (22 hash lines, no `processor*`, no time directories); `wsl_scratch = {deleted: true, deleted_at: 19:32:55}`; `wsl -- test -d` on the posix path fails. The log line reads `[model folder] WSL scratch deleted: /root/blastlab_runs/20260926-193214_1d_p37864-00`.
- The VTK button is visible, disabled, and its tooltip reads: *"This run's WSL scratch was released after a verified copy into the model folder. Its foam\ folder keeps the dictionaries, mesh, probes and logs, not the written fields, so there is nothing left to write as VTK."* (`qtf_04_foam1d_vtk_tooltip.png`).
- Stopped `QA_FOAM_STOP`: `stop_reason "stopped by user"`, `wsl_scratch = {deleted: false, kept_because: "the run ended before its end time"}`; the scratch still existed; VTK is enabled for it. While it ran, the folder already held `MODEL.json` and a manifest with `stop_reason "unfinished: ..."`, as the README says.

### 3.6 Chains
Qt ran `QA_CHAIN`, `QA_CHAINT0/1`, `QA_CHAINC0` (1D->2D) and `QA_CHAIN3S0`
(1D->2D->3D). Tk ran `TK_CHAIN`, `TK_CHAIN_T0..2` and `RESP_TK_0/1`. In each:
- the root holds `.blastlab-model 1d 2d [3d] handoff_1d_to_2d.txt [handoff_2d_to_3d.npz] manifest.json`;
- the root manifest has `chain`, `stages` and `handoffs`;
- stage 1 `MODEL.json` has `profile_file = "../handoff_1d_to_2d.txt"`, and stage 2 has `init_mode = profile1d`, `profile_file_in = "../handoff_1d_to_2d.txt"`;
- a refused chain created no folder.

The hint text is the new one, and no label or box mentions a workspace in
either toolkit.

### 3.7 HD 1.3 (Qt)
`QA_HD13` and `QA_HD13_BUSY` (the starter case, 51 s) each hold `.blastlab-model
MODEL.json hd13_loads\{nominal.csv,nominal.txt} hd13_report.html manifest.json`,
with a manifest of `solver hd13, dim 0, wsl_scratch null`. `outputs` equals the
disk. During the starter assessment:
- **Run chain** gave `Run` / "A run is already in progress." and created no folder;
- `_resume_foam_run(<the stopped run>)` gave the same text, returned False and created no folder.

### 3.8 Tk resume (item 10, the bug fixed in this batch)
The run browser showed 14 runs, and ours was `alive=false` and selectable.
Pressing Resume closed the browser and started `=== Stage Resume 2D (blastfoam) ===`.
The run finished at a terminate boundary after 95 s and wrote a complete
`TK_RESUME\`, including `foam\` and SHA256SUMS. The scratch was then released:
the manifest says `deleted: true`, and WSL agrees.

### 3.9 Close
Both entry points closed through WM_CLOSE with exit 0 and empty stderr. Tk
takes 4.0 s to close with no run live.

## 4. Failures and defects

### F1 (Tk, serious, intermittent): the Tk process died during a native 1D->2D chain
- **Steps:** `tk_timing.py`, first run: Runs folder = QA runs, Model `TK_CHAIN_T0`, Chain 1D (r 0.6 m, dx 4 mm) + 2D axisymmetric (1.0 x 1.6 m, dx 30 mm), press Run chain.
- **Expected:** both stages finish, as they did in the other 6 Tk chains.
- **Actual:** the hand-off was written (`handoff_1d_to_2d.txt saved`), and then stderr showed four times
  `vtkWin32OpenGLRenderWindow: wglMakeCurrent failed in MakeCurrent(), error: unknown error(code 170)`.
  The process ended with no Python traceback and no further output (`tk_timing.out.txt`). A rerun under
  `faulthandler` (all threads) and 5 more Tk chains did not reproduce it: 1 crash in 7 Tk chains.
- **Likely origin:** a 2D axisymmetric stage gets a revolved 3D scene in the Tk process.
  `gui/app.py:915 _attach_view3d_auto` calls `gui/view3d_panel.py:374 adopt_feed`, which calls
  `:336 _ensure_scene` (`BlastScene` on an in-process pyvista plotter). The stack sampler caught the Tk
  main thread in exactly that frame during stage 1->2 of a later chain (`tk_timing_sample.jsonl`,
  chain0). Code 170 is ERROR_BUSY, meaning the GL context is current elsewhere. Not shown to be caused
  by OUT-1, but it sits on the path the chain now takes.

### F2 (Qt): an HD 1.3 `MODEL.json` cannot be opened again
- **Steps:** Open case… on `runs\QA_HD13_BUSY\MODEL.json`.
- **Expected:** README says `MODEL.json` is "the case exactly as run", and a 1D `MODEL.json` does open (checked: dim 1 is loaded).
- **Actual:** the dialog `Open case` / **"Not a blastlab case file"** (`qtf_13_dialog_ok.png`).
  `ui/app.py:427` uses `core.case.load_case`, which refuses `schema: blastlab-hd13`.
  `models/hd13_case.load_case` reads the same file fine. The same thing happens with the
  `--hd13-new` starter file, so this is older than OUT-1, but OUT-1 is what now puts such a file in
  every HD 1.3 model folder.

### Smaller defects and things a user would find confusing
- **V1 (Qt, visual):** the refusal and overwrite dialogs break a path after `C:`, leaving "C:" alone on the first line (`qt_16_dialog_ok.png`, `qt_21_dialog_yes.png`). The Tk dialogs wrap correctly.
- **V2 (both):** the Chain status line joins the two refusal sentences with no stop between them: "Model name: the name is empty The Runs folder and Model boxes are on the Run tab." (`qt_43_chain_refused.png`).
- **V3 (Qt):** `Browse…` has no tooltip, although Tk's icon has one. The Model box has no placeholder, although the Runs folder box has one.
- **V4 (Qt):** during an HD 1.3 assessment, **Run chain** stays enabled. Its refusal is titled "Run" (not "Chain") and is not written to the Chain status line, unlike every other chain refusal (`qtf_10_chain_during_hd13.png`).
- **C1 (both):** the Model box keeps the previous name after Open case (it is filled only when empty), so the next Run asks whether to overwrite the *previous* model (`qt_foam.jsonl` F4: after opening the 1D `MODEL.json`, the box still read `QA_HD13_BUSY`).
- **C2 (both):** a resume writes into whatever the Model box says. The run browser shows scratch names only, never the model a run belongs to (`tkr_01_run_browser.png`). After the resume released the scratch, the original model's manifest (`QA_FOAM_STOP`) still says `deleted: false, kept_because ...`. If the box still holds the original model's name, the resume offers to overwrite the folder that documents the stopped run.
- **C3 (both):** the log prints full paths for some outputs and bare names for figures ("Saved blast_1d_results.png"), which reads as if the PNGs went to the working folder. They are in `<MODEL>\figures\`.
- **C4:** `..` is refused with "cannot end with a dot or a space". That is correct, but the message does not say what is wrong with the name.
- **C5 (Tk, older than OUT-1):**
  - the run browser shows a user-stopped run as State "finished";
  - its "Browse…" button is clipped to "rowse." at 760 px;
  - a resumed run that reached a terminate boundary still logs "[note] the run was stopped before its end time" (`tkr_03_resume_done.png`);
  - `Exception ignored in Image.__del__ ... main thread is not in main loop` appears on stderr at every Tk start, including a bare start and close.
- **C6 (Qt, older than OUT-1):**
  - after an HD 1.3 run, the Run tab chips and the live slice still show the previous 3D chain (`qt_54_hd13_done.png`);
  - the Results colour bar label is drawn twice (`qtf_07_foamstop_results.png`).
- **Outside OUT-1:** in `QA_2D` the second gauge (1.4, 0.3) lies inside the obstacle and is dropped silently. The TSV has 1 gauge and the Setup report gives no warning.

## 5. Numbers check (item 11)

Planar 2D case `QA_2D` / `TK_2D` (20 kg/m, obstacle, G1 at (0.30, 0.80) m, cell (0.305, 0.802) m):

| Quantity | Qt table | Tk table | `gauges_2d_summary.csv` | core `summary_rows(res)` | TSV (numpy) |
|---|---|---|---|---|---|
| Peak overpressure [kPa] | 7759.4 | 7759.4 | 7759.4 | 7759.438 | max p 7,860,763 Pa - 101,325 = 7759.4 |
| Arrival [ms] | 0.211 | 0.211 | 0.211 | 0.21084 | - |
| t of peak [ms] | 0.237 | 0.237 | 0.237 | 0.23722 | - |
| Positive phase [ms] | 0.255 | 0.255 | 0.255 | 0.25495 | - |
| Positive impulse [Pa·s] | 619.31 | 619.31 | 619.31 | 619.305 | - |
| Net impulse [Pa·s] | 619.32 | 619.32 | 619.32 | 619.315 | - |

For every other folder with gauges, the CSV peak equals max(TSV) - 101,325 Pa at 0.1 kPa:
- QA_1D: 3412.8 / 934.0
- QA_2DAX: 2862.7 / 1176.6
- QA_FOAM1D: 4400.1 / 1041.2
- TK_RESUME: 4905.5
- each chain `2d`: 975.0

## 6. Item 12: timings at the chain's stage 1 -> stage 2 switch

Three probes were used:
- **pump:** the time one `processEvents()` / `root.update()` call takes;
- **timer:** the longest interval between ticks of a 20 ms GUI-thread timer;
- **WM_NULL:** the longest time the top-level HWND took to answer `SendMessageTimeout(WM_NULL)`, polled every 50 ms. This is the Windows "Not Responding" criterion.

| Run | Stage 2 starts at | pump (longest) | timer (longest) | WM_NULL (longest unanswered) |
|---|---|---|---|---|
| Qt QA_CHAIN | 1.56 s | 327 ms @1.56 s | - | - |
| Qt QA_CHAINT0 / T1 | 1.36 / 1.41 s | 274 / 318 ms, at the switch | - | - |
| Qt QA_CHAINC0 (user stays on Chain) | 1.24 s | 231 ms | - | - |
| Qt QA_CHAIN3S0 (3 stages) | 1.49 s (3D at 8.39 s) | 419 ms @1.49 s | - | - |
| Qt RESP_QT_0 / 1 | 1.41 / 1.47 s | 315 / 317 ms | 336 / 330 ms | 244 / 462 ms |
| Tk TK_CHAIN | <= 11.98 s | **10,871 ms** @1.11 s | - | - |
| Tk TK_CHAIN_T0 / T1 / T2 | <= 14.1 / 14.1 / 59.7 s | **10,672 / 12,903 / 12,923 ms** | - | - |
| Tk RESP_TK_0 / 1 | <= 12.3 / 13.6 s | **11,084 / 13,480 ms** | 827 / 881 ms | 1,299 / 815 ms |

Reading:
- **Tab behaviour.** In Qt the Run tab is on screen 0.28-0.42 s after Run chain; Tk switches inside `_run_chain`, before the worker starts. A later stage never switches tabs: a user standing on Chain stays there (`tab_at_mark = chain`).
- **Qt.** The switch costs one stall of 0.23-0.46 s.
- **Tk, the "10 s gap".** The gap the verifier saw reproduces 6 of 6 times as a single `root.update()` call lasting 10.7-13.5 s from stage 1 into stage 2.
- **Tk is not frozen during it.** In the same runs the window answered WM_NULL within 0.8-1.3 s and the 20 ms timer never stalled more than 0.9 s.
- **Why the call runs so long.** `update()` does not return while the drain keeps finding work. The sampler put the main thread inside matplotlib text drawing, from the live-slice redraw `run_panel.py:712 on_frame -> mpl.py:104 draw`, in most samples.
- **The real worst stall in Tk.** It is 0.8-1.3 s, close to the "0.9 s four times" the verifier recorded.
- **Stage times in Tk.** The "stage 2 starts at" figures for Tk are upper bounds, because the log could only be read when `update()` returned.

## 7. Harness notes (limits of this pass)
- The first attempt at a real Enter in the Tk dialog used a global `SendInput`. It was not delivered because the dialog was not the foreground window (`fg_ok: false`), and the dialog was answered No from outside. The keystroke went to whatever window was in front at 19:37:01. The retest posts `WM_KEYDOWN VK_RETURN` to the dialog only.
- `qt_pass.jsonl` was cut short by the 3D-viewer child process (a multiprocessing spawn re-imports the harness). `qt_pass.out.txt` has the full stream, and `folders.json` re-derives every folder check from disk.
- Rebuilding a second `ctk.CTk` in one process fails (`image "pyimage3" doesn't exist`). That is a harness artifact, so Tk persistence was tested across two processes.
- Not exercised:
  - a locked-file (ParaView) overwrite refusal;
  - a hash mismatch or partial `foam\` copy;
  - a blastFoam chain;
  - the CLI.

## 8. Files
- Scripts: `scripts\qa_common.py`, `qt_pass.py`, `qt_foam.py`, `tk_pass.py`, `tk_timing.py`, `tk_timing_fh.py`, `responsiveness.py`, `entry_points.py`, `extra.py`, `analyze_folders.py`
- Logs: `*.jsonl`, `*.out.txt`, `*.err.txt`, `folders.json`
- Screenshots: `shots\` (109 PNG)
- Model folders: `C:\Users\rotem.ofek\blastlab_qa\out1_20260926_191440\runs\`
