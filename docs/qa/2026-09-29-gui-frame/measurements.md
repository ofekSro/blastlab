# GUI-3 window frame — real-platform measurements (2026-09-29)

Machine: the home PC (WSL VM reports 4 cores · 5 GB — not the office
i7-14700 of CLAUDE.md §3). `QT_QPA_PLATFORM` unset for everything here.

## Screenshots (acceptance 9)

`gui3-<screen>-<size>-<mode>.png`: Setup / Run / Results / Chain at
1100×720 and 1600×1000 dark (8), plus Setup 1600×1000 light. Nothing
clipped at 1100×720 after the bar was tightened (gap 26 → 6, pill
padding 10, chain-link padding 8, 40 px dimension buttons, wordmark at
the board's 16 px, chip "blastFoam · checking" during the WSL probe).
Top bar natural width 1070 px offscreen ('untitled', WSL-ready chip);
with a dirty short stem it reaches ~1117, so at exactly 1100 the chain
link / case / chip may compress by a few px each. Long case names are
capped at 200 px (button clips its text; full name on the menu).

## 3D viewer placement (risk item, CLAUDE.md §8.7)

Win32 through ctypes (`GetWindowRect` / `GetParent` /
`IsWindowVisible`), never Qt's `geometry()`. Driver: MainWindow with
`cases/native_3d_small.json` (the Setup preview attaches the real
viewer child), then 3 × (Setup → Run → Results → Setup) switches and a
detach / re-attach on the Setup host, sampling every ~25 ms. "Wrong" =
a visible top-level viewer window while embedded, or an embedded viewer
window outside the host container's Win32 rect (8 px pad).

Result: **514 samples, 0 wrong, longest unbroken wrong stretch 0 ms.**
(Script: session scratchpad `measure_viewer.py`.)

## `_e2e_ui_view3d.py` (run per the batch plan)

Fails on this machine **identically at the pre-GUI-3 base `fbbc698`**
(A/B in a temp worktree): the tiny case yields n = 1 playback frame
(the check wants ≥ 2) and G3's detach refuses (`_float_win` None), so
the script dies at line 131. One extra transient on the first GUI-3
run: the solve itself errored mid-run once ("Run failed" at 60 %), not
reproducible — the same case solves clean headlessly and through the
GUI on retry. Conclusion: pre-existing home-PC flakiness, not a GUI-3
regression; the embedding itself was also verified green by the Win32
measurement above. Worth a re-run on the office machine.

While the failed first run was up, its title read
`60 % · native_3d_small · BlastLab` — the GUI-3 title progress working
on a real run.
