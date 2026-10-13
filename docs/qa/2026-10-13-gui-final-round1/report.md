# GUI QA - final-gui clean loop, round 1 (2026-10-13)

gui-qa-tester, HEAD `159ece1` on `final-gui`. The agent's Write was refused; the orchestrator
wrote this file from its final message. Screenshots and harness extracts sit next to this file;
the full harness output (564 PNGs) stays in `C:\Users\rotem.ofek\blastlab_qa\r1`.

Verdict: both batch changes pass. No critical or high findings.

## Method

- **Setup:** the §8.2 dry run showed `auto_cleanup False`. `pgrep blastFoam` was empty before and
  after every run.
- **Big harness:** `_qa_ui_harness.py` ran once, in full, offscreen, in three invocations. It exits 75
  at terminal scenarios, then 0. It refuses an `--out` under OneDrive or the repo.
  - All 81 scenarios completed.
  - 1724 `ok:` checks, 1 finding (F-5, a harness false positive), no tracebacks.
- **R1 and R2:** driven live, with `QT_QPA_PLATFORM` unset, blastFoam mode, real WSL solves and
  private settings.
  - The first driver run was contaminated: the app's multiprocessing re-imported the script and
    started a second copy running at the same time. Those results were discarded and the run was
    repeated with a `__main__` guard.

## Result per item

| Item | Result |
|---|---|
| R1: chain Stop during stage 2's blockMesh | PASS |
| R1: Stop just after the handoff | PASS |
| R2: Keep all fields, no kept-scratch dialog | PASS |
| Setup / Checks (trigger notes, captions, dropdown, Where column) | PASS (harness C05-C10, F12, V01-V10) |
| Run: drop line, `[warn] dropped` | PASS (D02, F12) |
| Run: live gauges, blastFoam 1D / 2D | PASS (F01, F02, F12, and a live 1D run) |
| Run: bar after a Stop during meshing | PASS (F07) |
| Run: Detach / Re-attach on native 3D | PASS (D04, D05, Q01) |
| Run: Close with the Setup preview open or during a native 3D run | PASS (I02, F11: no orphan, closed in 5.4 s) |
| Chain: cards, Checks, click-to-focus, stage 3 | PASS (G01, G02) |
| Results: Gauges default row, drop titles, footnotes, `x` markers, Open a model folder, Model column, glyph | PASS (E03, F09, F12, M-series) |
| Results: live blastFoam 1D title never says `idealGas` | PASS (title is `1D spherical · 1.0 kg TNT · JWL`) |

The Where column and the dropdown pass only through the harness checks; they were not inspected
in isolation.

## R1 detail

Live blastFoam 1D to 2D chain.

- **Stop during stage 2's blockMesh:**
  - banner `Stopped after 15 s`
  - strip `01 1D ✓ | 02 2D not run | Chain stopped at stage 1 of 2`
  - bar 0/1000
  - the title has no `✓ Done`
  - no dialogs
  - Screenshots: `R1a_before_stop_stage2_meshing.png`, `R1a_after_stop.png`.
- **Stop just after the handoff:** the Stop landed once stage 2 had started.
  - Banner `Stopped after 20 s · stopped by user`, strip `02 2D stopped`, bar 5/1000.
  - Screenshot: `R1b_between_after_stop.png`.
  - `R1b_after_stop.png` is an earlier try (Stop before stage 1 started), also `Stopped`, bar 0.
- **The exact window between stages** could not be hit by hand. The unit test covers it.

## R2 detail

Live blastFoam 1D run with Keep all fields ticked.

- The only dialog was the `notify_desktop` finish notification. There were no `show_error`, `warn`
  or `show_info` dialogs.
- The log has `[note] WSL scratch kept (Keep all fields in WSL was ticked): /root/blastlab_runs/...`.
- There are no `[warn]` lines, and "scratch was kept" appears nowhere.
- Screenshots: `R2_setup_keep_ticked.png`, `R2_after_run.png`.

## Findings

| # | Severity | Finding |
|---|---|---|
| F-1 | medium | The 1D Field figure title and the export title hard-code TNT. A C4 blastFoam 1D result shows `1D spherical · 1.0 kg TNT · JWL`, and "Exports use the full title: ... 1.0 kg TNT - EOS: JWL", while the "How it was computed" card says `Charge 1 kg C4`. Source: `blastlab/output/plots.py:305` and `:350` (a `kg TNT` literal). The 2D and 3D titles use `charge_label(meta)` (`plots.py:607`, `:689`). `test_ui_results_screen.py:1580` pins the TNT wording, so a fix needs an owner decision on that test. Screenshot: `212_F01_results_results_fields_dark.png`. |
| F-2 | low | After a chain Stop in stage 2's mesh, the banner reads `Stopped after 15 s · shock arrived at outer boundary (p_last = ...)`. That suffix is stage 1's finish reason, not "stopped by user". The strip and the log are correct (`R1a_after_stop.png`). |
| F-3 | low | After a Stop in stage 2's mesh, the strip says `Chain stopped at stage 1 of 2` and `02 2D not run`, though the Stop came while stage 2 was meshing. Defensible, but confusing next to the `[stopped during 'blockMesh']` log line. |
| F-4 | low | The enlarged live-gauge card clips its peak label at the left edge: `09 ms` for `0.09 ms` (`R2_after_run.png`, right column). |
| F-5 | low | A harness false positive, not an app bug. The F08 check `labels[-1].endswith('(stopped)')` fails because the dedupe suffix gives `save1 - 2D (stopped) #2`. Source: `_qa_ui_harness.py:3197`. The app's label is correct. |

## Evidence

Besides `R1*.png`, `R2*.png` and `212_F01_...png`, this folder has these extracts from the harness
run:

- `contact_F12.png`, `contact_G02.png`, `contact_F07.png`, `contact_D04.png`, `contact_I02.png`
- `findings.jsonl`
- `checkpoint.json`

No processes are left running and no blastFoam is left in WSL. The live runs leave kept-scratch run
directories in `/root/blastlab_runs`; this is by design, and the harness's own runs add more.
