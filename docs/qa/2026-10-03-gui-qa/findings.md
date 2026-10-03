# GUI-10 findings — base vs HEAD (batch `gui-qa`, part 10b)

Plan: `docs/batches/2026-10-03-gui-qa.md` (T7-T11). Raw diff: `findings-diff.txt` in this
folder. Harness output folders are under `~\blastlab_qa\`.

## Passes

| Pass | Folder | Code | Platform | Scenarios | Findings |
|---|---|---|---|---|---|
| base | `gui10-base` | `0605522` (worktree outside OneDrive) | offscreen, native, F excluded | 66 `done` | 1 S2 |
| HEAD | `gui10-head` | `3a09351` | offscreen, native, F excluded | 69 `done`, none crashed | 0 S1, 5 S2, 1 S3 |
| window | `gui10-window` | HEAD | real platform | 10 `done` | see T9 |
| F group | `gui10-foam` | HEAD | offscreen, blastFoam in WSL | 12 `done` | 14 (3 S1), all dispositioned below |

The base pass ran in 5 invocations, split after C06/C07/V04/V06/V10, because the base
harness has no solver-seed restore and those scenarios leave blastFoam on (D196). Every
base run log reads native. The base harness got the same F33 `press()` check, uncommitted
(D193), so the comparison is like-for-like.

## Diff: new 5, gone 0, same 1

- **new** — G01 S3 `QFontEngineFT`: F26, offscreen-platform only (D178: absent in 2 of 2
  real-platform runs). Kept visible, not hidden in the harness.
- **new** — K02 S2 ×4, "nothing clipped" on the run banner and run finished, dark and
  light: **F34**, the Run strip's P MAX lost its unit at 1100 px. Fixed in `38a9673`; the
  re-run `gui10-b-k02redo` is clean, and K02 on the real platform is clean.
- **same** — Q03 S2 "no result labelled 'QA native2d'": harness order, Q03 runs before
  group D caches its results.

The plan expected some items to read as "gone" (B01 sidebar, B06 offscreen S3 = F10,
G01 refusals = F18, E03 `canvas`). They never appeared in this base pass, so they are
listed as intended changes instead.

## Intended layout and harness changes

- The redesign itself (GUI-1 … GUI-9).
- Layout in GUI-10: F29 top bar, F21 heights, F8 tree contrast, D190 tree hover, F34 tile fit.
- Harness in 10a: navigation through the frame, B06 platform-aware, `wait_log`
  generations, `select_result` stages, the view lists, the B01 note, rich-text clip
  measurement, the solver-seed restore.
- Harness in 10b: F33, D03 opening Step through first, F32, F35, and K01-K03 (HEAD only).

## T9 — real platform

- B06: every check passes (Ctrl+O and Ctrl+S reach their dialogs, F5 starts, plain Esc
  does not stop, Shift+Esc stops).
- Q01: each of the three surfaces got its own render window.
- K02: 0 clipped, 0 outside — dark and light, native and blastFoam, 1100 × 720.
- K03: luma 194.4-246.0 (floor 140).
- E06, I06: first lacked a results cache; with HEAD's cache copied in and redone, 0
  findings, the viewer opened with a 29 ms UI block. (`findings.jsonl` in `gui10-window`
  still lists the first attempts; the redo runs recorded nothing.)
- F26 rule: the 13-scenario sequence twice with `--window` (`gui10-window-f26-1`, `-2`)
  gave 0 `QFontEngine` messages → offscreen-platform only.
- F30 (`External WM_DESTROY` ×2) shows in K03 and in H03 of the 13-scenario sequence; the
  same sequence at base on the real platform (`gui10-f30-base`) gives the identical two
  S3, so F30 predates the redesign.
- Light-mode screenshots of every screen at both sizes are in this folder.

## F group (WSL) dispositions

pgrep empty before and after every invocation; §8.2 dry run `False`; all 65 pre-existing
runs in `/root/blastlab_runs` kept; nothing deleted. VM: 4 cores (8 logical), 5 GB.

| Scenario | Disposition |
|---|---|
| F00, F01, F03 (3D, 112 s), F04, F09, F11 | clean |
| F02 (3 S2), F10 (VTK not offered) | **F36**, pre-existing and identical at base (`gui10-foam-base-ab`). OUT-1 releases the WSL scratch, so VTK export is correctly disabled with its reason; the harness expectation is stale. F10's "no QA native2d" is the F-only folder having no cache. |
| F05 (2 S2), F06 (S1) | **P2-22**, pre-existing: blastFoam exits 134 at t = 0, "No cells will be activated using the detonation point" (`(2 2 0)`, `(0.75 0.75 0.75)`). Not a GUI finding. |
| F07 (3 S2) | **office machine**: 1,562,500 cells exceed this VM's cap of 1,391,887, so Run is disabled by design (D31). |
| F08 | **F35**, harness: a queued "No" for a Delete that never asks was consumed by GUI-6's Stop confirmation (D54). Fixed in `8585aa6`; re-run alone: 0 findings, graceful stop in 6.5 s. |

New kept runs: `20261003-202839_2d_p21764-04`, `-203357_3d_p21764-05`,
`-204254_2d_p21764-06`, `-204906_2d_p21764-07`, `-205815_2d_p29120-01` (base A/B),
`-205953_2d_p28044-00` (F08 re-run).

## P2 re-checks (real platform, 1100 × 720)

- **P2-18: still reproduces.** Chain Run stays enabled during an HD 1.3 assessment; its
  refusal box is titled `Run` ("A run is already in progress."). The overwrite dialog
  breaks the path after `C:`. Shots: `gui10-dark-1100x720-chain-p2-18-during-hd13.png`,
  `gui10-dark-617x158-dialog-p2-18-overwrite.png`.
- **P2-21: gone.** No 3D properties page scrolls into a blank tail (range 0, Gauges 5 px
  with a 1 px tail). Shot: `gui10-dark-340x610-setup-p2-21-3d-gauges-end.png`.
- **P2-24: still reproduces.** The tooltip is 187 characters with no break, one 976 px line.

## Needs the office machine

- F07 (over this VM's cell cap).
- `_e2e_ui_chain_foam.py` (from GUI-9) and F6 `_e2e_ui_view3d.py`: the blastFoam 3D Setup
  preview is still blank on this PC (`gui10-dark-1100x720-setup-blastfoam.png`).
