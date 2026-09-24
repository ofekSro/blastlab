# blastlab baseline QA - 2026-09-24

Baseline run before a refactor: what works and how the app looks *now*, on
`arch-p0-characterisation`. No application code was touched. This report and
its screenshots are the only artifacts written; the harness runs below also
wrote to `~/blastlab_qa/20260924-1952` (kept - not deleted, not under
`~/Desktop`).

## 1. Environment

| | |
|---|---|
| Python | 3.12.10 (Microsoft Store build), on PATH as `python` |
| Qt | PySide6 6.11.2 |
| Pillow | 12.2.0 (screenshots via `QWidget.grab()`; Win32 `PrintWindow` used as a ground-truth fallback - see §4.1) |
| pywin32 | present (`win32gui`/`win32ui`), used for the Win32 fallback capture |
| pyvista / pyvistaqt | present (`pyvista_available() == True`) |
| OS | Windows 11 Enterprise 10.0.26200 |
| Launch | `blastlab.ui.app.MainWindow` / `blastlab.gui.app.App` built directly in throwaway harness scripts under the session scratchpad (no `python -m blastlab` subprocess needed) |
| Settings guard | every process set `BLASTLAB_SETTINGS` to a private file **before** any `blastlab` import, and asserted `settings.load()['auto_cleanup'] is False` before building any window. Verified True in every one of the 4 harness scripts and in `_qa_ui_harness.py`'s own `main()` (it writes `auto_cleanup: false` before importing the app). `env.auto_cleanup(...)` was never called. |
| Qt platform | offscreen for widget-only work; **unset** (real platform) for the startup/3D-tab screenshots and for the Tk screenshot, per CLAUDE.md 8.7 |
| python processes | none running before this session; none left running after (checked with `Get-Process`) |

**Environment quirk found and worked around (not an app bug):** this shell's
window station refuses GDI screen capture entirely - `PIL.ImageGrab.grab()`
fails with `"screen grab failed"` even for the whole screen (confirmed with
`GetSystemMetrics` returning a normal 1920x1080 while `ImageGrab.grab()`
still failed). Real-platform screenshots (item 4 and the Tk screenshot) were
taken instead with a Win32 `PrintWindow(hwnd, hdc, PW_RENDERFULLCONTENT)`
capture via `pywin32`, which asks the window to paint itself via `WM_PRINT`
rather than reading the desktop framebuffer, and works in this session.

## 2. Result table - my own test plan

| # | Item | Result | Evidence |
|---|---|---|---|
| 1 | Startup (offscreen) | PASS | `01_start_setup2d.png` - title `blastlab 1.0.0`, 1200x800, no traceback |
| 1b | Startup (real platform, Win32 capture) | PASS | `42_realplatform_start_win32.png` |
| 1c | Startup, Tk (`--tk`, real platform) | PASS | `50_tk_start.png` |
| 2 | Every screen/tab (Setup/Run/Results/Chain) | PASS | `01-05` |
| 2b | Every dimension's Setup form (0D/1D/2D/3D) | PASS | `06_setup_1d_default.png`; 2D/3D covered in the harness's B03 |
| 3 | Resize 900x600 / 1600x1000 | PASS (with a documented floor) | `07_resize_900x600.png`, `08_resize_1600x1000.png` - see §5 |
| 4 | Happy path: default 1D native case, run, compare vs `solve_1d` | PASS | `21-25`; numbers in §6 |
| 5 | Boundary/invalid input (text, negative, zero, empty) | PASS | `09-12` |
| 5b | Save case -> change -> Load case restores inputs | PASS | `14_after_load_case.png` |
| 6 | Long calculation: window repaints mid-run, Run button disabled | PASS | `23_run_midway.png`; Run button `isEnabled()==False` mid-run, re-enabled after |
| 7 | Save/Load | PASS | see 5b |
| 8 | Export | not exercised by my own script; exercised by the harness (Q03, E03, E07, F10 groups - PNGs/report/gauges TSV/summary CSV all wrote real files and were checked) | harness `findings.jsonl`/log |
| 9 | Close terminates cleanly | PASS | every script closed its window; no leftover python process afterward |
| 10 | 3D tab, real platform, embedded viewer | INCONCLUSIVE (see §4.1) | `44_realplatform_3d_tab_win32.png` |
| 11 | Primary harness `_qa_ui_harness.py` (native/UI scenarios) | PASS - 50/50 | §7 |
| 12 | `test_regression.py` | PASS - 8/8 | §7 |

No FAILs. Two items are worth separate treatment, below.

## 3. Failures

None. No crash, traceback, or incorrect displayed number was found anywhere
in this run (my own scripted plan, the 50-scenario harness, or the
regression suite).

## 4. Notes / inconclusive items (not failures)

### 4.1 3D preview panel content could not be visually confirmed

Steps: real platform (`QT_QPA_PLATFORM` unset), Setup tab, switch to 3D,
wait for `viewer_link.is_ready` (became `True` after 2.0-12.1 s across two
runs, consistent with the ~11-13 s cold-start cost documented in
`CLAUDE.md` §8.7), then wait a further ~9-11 s and screenshot.

Expected: the embedded pyvista/VTK scene for the default 3D case.
Actual: `44_realplatform_3d_tab_win32.png` (Win32 `PrintWindow` ground
truth - confirmed working via a standalone Tk test first) shows the
`View3DHost` panel still on its own **"starting the 3D preview…"**
placeholder text, even though `preview_kind()` correctly reports `'3d'` and
the control channel reports ready.

This is very likely **not** an app bug but a capture-technique limitation:
VTK/pyvista render via an OpenGL swap chain, and `PrintWindow`/`WM_PRINT` is
well known not to reach GPU swap-chain content reliably (it captures
GDI/software-rendered content, which is why it *did* correctly capture the
Qt-drawn "starting..." placeholder text, the window chrome, and the rest of
the app around it). I could not tell, from this environment, whether the
scene had actually arrived and just wasn't visible to `PrintWindow`, or
whether the first frame genuinely had not arrived yet. No exception, no
"embedding failed" log line, and no other anomaly appeared. Flagging this
for a follow-up QA session on a machine where `ImageGrab`/DWM capture
works, rather than reporting it as a defect. The plumbing signals
(`is_ready`, `preview_kind() == '3d'`) all say it worked.

Separately, the **offscreen** 3D embedding path (used by the 63-scenario
harness by default) is confirmed working as documented: the Run tab's log
for a native 3D run (D04) reads *"[3D view: embedding failed (fromWinId
returned None); the viewer window floats]"* - exactly the offscreen
limitation CLAUDE.md §8.7 describes, and the app's own documented fallback
(a floating window) engages instead of crashing. Not a bug.

### 4.2 Harness `--resume` picked up a stale, differently-named run directory once

`_qa_ui_harness.py --resume` (no `--out`) selects the *alphabetically last*
directory under `~/blastlab_qa`, via `sorted(os.listdir(...))[-1]`. My own
run directory was named `20260924-1952` (a timestamp); a pre-existing
directory from an earlier session was named `night3`, and `'n' > '2'`
sorts after any `20260924-...` name. One `--resume` call (round 2, Q group)
was silently applied to `night3`'s checkpoint instead of mine. Nothing was
deleted (the harness only appends), and I switched to explicit `--out
<mydir>` for every subsequent round, which fixed it; `night3` now has a few
extra completed entries (Q01-Q04) it didn't have before. This is a minor
usability quirk in the harness's directory-resolution, worth a one-line fix
(sort by mtime, not name) if arch-refactorer is ever in that file - not
something I changed.

## 5. Visual findings (work, but worth noting)

- **Window floor on resize.** Asking for 900x600 gives 1100x720 -
  `MainWindow.setMinimumSize(1100, 720)` enforces its own floor
  (`07_resize_900x600.png`). Intentional per the code and also asserted by
  the harness itself (B05, I06: `qa.win.width() >= 1100`). Not a bug; noting
  it because a literal reading of "resize to 900x600" doesn't get you there.
- **1600x1000** lays out cleanly with no overlap (`08_resize_1600x1000.png`).
- **125%/150% DPI scaling**: the harness's own Q04 scenario checks for
  clipped widgets and found **0 clipped widgets at both 125% and 150%**
  (`061-068_Q04_*.png` sampled - confirmed clean, e.g.
  `065_Q04_setup_dpi150_setup_dark.png`).
- **Light mode** (B07, H03) is clean and consistent with dark mode; no
  leftover dark-styled widgets spotted in the sampled shots.
- **Tk (`--tk`) startup** (`50_tk_start.png`) visually matches the Qt
  layout closely, confirming the "way back" GUI is not bit-rotted. One
  expected difference: the Tk dimension selector shows only **1D/2D/3D**
  (no **0D** HD1.3 tab) - consistent with HD1.3 being Qt-side work
  (`HD1-11c` etc. in `DONE.md`/`TODO.md`); not a defect, just a known gap
  between the two GUIs.
- **Invalid-input messaging** is specific and field-named throughout
  (`'radius' is not a number: 'abc'`, `Charge must be > 0`, `'charge' must
  be a finite number: 'inf'`, etc. - `09-12`, and the harness's I03/I05).
  Bad fields get a red border; other fields are untouched.
- **Native-3D performance note** (not a UI bug, just worth recording since
  it shaped how long this session took): the Run-tab log says outright
  *"(3D steps are slow: expect roughly 1-1 s/step)"*. The harness's D04/I01
  native-3D scenarios, estimated at 330 s, actually took 688 s and 777 s
  wall-clock on this machine - 2x their estimate but exactly consistent
  with the app's own warning, not a hang (CPU stayed pegged throughout,
  confirmed via `Get-Process`).

## 6. Numbers check - happy path

Default 1D **native** case (`radius_m=10, charge_kg=1, cell_size_m=0.001`,
i.e. exactly `Case1D()`'s dataclass defaults, unedited) plus two gauges
added the way a user does (typed into the gauge-list entry, "+" clicked):
`r = 3.0 m` and `r = 6.0 m`. Run through the real Setup -> Run -> Results
flow (native solver mode selected via the sidebar toggle), 51,781 steps,
~132 s wall-clock through the GUI. Compared against `solve_1d()` called
directly on the identical `Case1D` (54.5 s standalone), summarized with the
app's own `output.gauge_summary.summarize_trace` - the same function the
Results table itself calls.

| Gauge | Metric | Displayed (GUI table) | Direct `solve_1d` | Match |
|---|---|---|---|---|
| G1 r=3.00 m | Peak overpressure [kPa] | 73.1 | 73.0900 | yes |
| G1 r=3.00 m | Arrival [ms] | 4.053 | 4.05265 | yes |
| G1 r=3.00 m | Positive impulse [Pa·s] | 53.48 | 53.4825 | yes |
| G1 r=3.00 m | Net impulse [Pa·s] | -5.36 | -5.3569 | yes |
| G2 r=6.00 m | Peak overpressure [kPa] | 22.0 | 21.9912 | yes |
| G2 r=6.00 m | Arrival [ms] | 11.694 | 11.69442 | yes |
| G2 r=6.00 m | Positive impulse [Pa·s] | 27.9 | 27.9021 | yes |
| G2 r=6.00 m | Net impulse [Pa·s] | 0.90 | 0.8976 | yes |

All eight values match to display precision (peak/impulse within 0.05,
arrival within 0.01 ms). Net impulse is the whole-record signed overpressure
integral (negative phase included), as documented - not compared against a
positive-phase-only reference.

## 7. Existing test suites

**`_qa_ui_harness.py`** (offscreen, `dangerouslyDisableSandbox` needed only
because this shell's own sandbox blocks the multiprocessing handle
duplication the embedded-viewer child needs - confirmed with `ensure_qapp`'s
own private-settings guard active throughout):

- Ran groups **B, Q, C, D, E, G, H, I** (50 scenarios) across 8 `--resume`
  rounds with `--budget`. **F00-F11 (12 blastFoam/WSL scenarios) were
  deliberately never selected**, per the no-blastFoam/no-WSL-solve
  constraint for this session. `S00` (smoke) was superseded by the full run.
- **Result: 50/50 `done`, 0 crashes, 0 `KillSwitch`.** Only one recorded
  finding in `findings.jsonl`, severity S2:
  `Q03: no result labelled 'QA native2d' to select` - a cross-scenario
  cache-dependency artifact of running Q before D in a partial `--only`
  selection in round 1 (Q03 wants a result cached by an earlier D02 that
  hadn't run yet in that particular invocation), not a product defect;
  later full-D-group scenarios (D02 itself, E01 which reads a cached 2D
  result) never hit this.
  Exit codes seen: `75` (budget exhausted mid-suite, the harness's own
  documented "resume me" signal) on 6 of 8 rounds, `0` on the final two.
- Total wall time: session ended up dominated by native 3D scenarios
  (D04 688 s, I01 777 s - see §5).

**`test_regression.py`**: **PASS**, 8/8 baseline artifacts byte-identical /
array-equal (`b1_gauges.txt`, `b1_profile.txt`, `b2_gauges.txt`,
`b2_profile.npz`, `b2r_gauges.txt`, `b3_gauges.txt`, `b3r_gauges.txt`,
`transcript.txt`).

## 8. Suspected engineering errors

None found. Nothing in this session's numbers, logs, or displayed results
looked physically wrong; the one 1D/3-gauge cross-check in §6 matches the
core solver to display precision, and `test_regression.py`'s byte-identical
comparison against the frozen baseline passed outright. (Per the task
scope, this was not an investigation of the physics - just what surfaced
incidentally while driving the GUI.)

## 9. Cleanup

Every window/QApplication built by my scripts was closed
(`win.close()`/`root.destroy()`) before its script exited. `Get-Process`
showed zero python processes before this session started and zero left
running after the final command. No file under `~/Desktop` was touched. No
`blastlab/tests/` file was created or edited (that tree is
arch-refactorer's). `env.auto_cleanup(...)` was never called.
