# Implement report - gui-final Part D, group 3: D5 only

Plan: `docs/batches/2026-10-12-gui-final.md` §D5. Branch `final-gui`, base `872c7de` (checked with
`git log -1` before starting). D1-D3 and D4+D6 ran in parallel in their own worktrees; this group
ran offscreen only, with no WSL solve and no viewer child.

## D5 - Owner decision 4: chain stage 3 opens at Lz 2.5 m - DONE

- **What / where:** `CHAIN_SEED` (`ui/chain_panel.py`, the module constant above `CHECK_MS`) now
  holds `3: {'Lz': '2.5'}`. Its comment gives the probe numbers (360,000 cells, unprobed cap
  1,113,510) and says why not 4.0 m (GUI-13 A1) and why not a 1.0 m 2D burst (S2-1). The seed is
  applied once, while the panel is still quiet, so stage 3 stays untouched.
- **Tests:**
  - `test_ui_chain_screen.py` S5 `s5_live` has two new checks:
    - D5 native: stage 3 is at Lz 2.5 and untouched, and cards 1-3 read `● case OK`.
    - D5 blastFoam on a probed plan: the cache is primed with `env.prime_hardware(cores=14,
      ram_gb=63)`, the planner's probed VM, and restored afterwards; cards 1-3 read `● case OK`.
  - The S2-1 / F45 / B2 block now sets stage 3's Lz to the form's 1.5 m first, so F45 and B2
    still fire at 1.5.
  - The S6 seed check picks up `CHAIN_SEED[3]` by itself, at the existing line `**CHAIN_SEED.get(d, {})`.
  - `char_golden/ui_chain_wiring.json` was re-recorded with `test_ui_char_chain_wiring.py --update`.
- **Files:** `blastlab/ui/chain_panel.py`, `blastlab/tests/test_ui_chain_screen.py`,
  `blastlab/tests/char_golden/ui_chain_wiring.json`.
- **Commands:**
  - `gate.py --changed HEAD`: 3/3 suites green (`test_ui_chain`, `test_ui_chain_screen`,
    `test_ui_char_chain_wiring`).
  - Also run directly: `test_ui_chain_screen.py` passed 252 checks (250 before the change, plus
    the 2 new ones), and `test_ui_char_chain_wiring.py` passed.
  - `gate.py --only regression` was run last (see below).
- **Criteria:**
  1. PASS. `test_ui_chain_screen.py`: the two D5 checks pass (native, and blastFoam probed plan).
     `F45: the seed's 2D burst (z 2.0 m) over a 3D Lz 1.5 m warns on card 3` passes, and so does
     `B2: at Lz 1.5 the stage-3 Domain & mesh row shows warn`.
  2. PASS. `test_ui_char_chain_wiring.py` exits 0. `git diff -U0` on the golden showed exactly 6
     hunks, at lines 455, 640, 755, 870, 1021 and 1177, each `"Lz": "1.5"` → `"Lz": "2.5"`.
     Nothing else in the file changed.
  3. PASS for the unprobed half; the probed half rests on the plan's recorded numbers.
     - I re-ran the planner's `probe_lz.py` and `probe_lz_routes.py` `unprobed` from the session
       scratchpad `d-g3`. They reproduce the table:
       - 1→2→3 native: Lz 1.5 gives card 3 F45; Lz 2.5 gives all `case OK`; burst 1.0 gives card 2 S2-1.
       - 1→2→3 blastFoam unprobed: Lz 2.5 leaves only the hardware warning, 7 ranks, 360,000
         cells, cap 1,113,510.
       - 2→3: F45 at Lz 1.5 and clean at 2.5 (the hardware line only, on blastFoam).
       - 1→3: still warns at either Lz (Q5).
     - The `probed` run was not made. `wsl -d Ubuntu -- pgrep -a blastFoam` showed a running
       solve at both checks (PIDs 1437004 and 1466869, the D4/D6 group). The test's primed-plan
       check stands in for it and gives the same all-`case OK` result.
- **Commit:** `dd192de`.

## Closing

- `gate.py --only regression`: 1/1 green, `regression (byte-for-byte): PASS`. It was run after
  `dd192de`.
- App start: `d-g3/app_start.py` built the MainWindow offscreen on private settings, with the
  `_probe_hw_async` stub. Stage 3 Lz read 2.5. The cards read `case OK`, `1 warning`,
  `1 warning`; both warnings are the unprobed "WSL hardware not detected" line, as in the
  table's unprobed row. Exit 0.
- The cleanup dry run printed `False` before the app was built.

## Summary

- **Files touched:**
  - `blastlab/ui/chain_panel.py`
  - `blastlab/tests/test_ui_chain_screen.py`
  - `blastlab/tests/char_golden/ui_chain_wiring.json`
  - this report
- **GUI screens touched (QA):** Chain screen, stage 3 editor. The Domain & mesh `Lz` field now
  opens at 2.5, and card 3 opens clean on 1→2→3 and 2→3.
- **Numerical changes:**
  - Seed value only: chain stage 3 `Lz` goes from 1.5 to 2.5 m (owner decision 4; golden approved
    as Q3).
  - The 3D stage of the default chain grows from 216,000 to 360,000 cells, and its auto ranks on
    blastFoam from 4 to 7.
  - No solver default, `baseline/` or `foam_golden/` change.
- **Engineering issues noticed:**
  - The committing `git` printed `failed to delete '.git/worktrees/wt-final-gui': Permission
    denied`. This is a stale worktree record left by an earlier session, not by this group. The
    commit itself went through.
  - `gate.py` runs share one GUI-suite lane across worktrees. With three implementers running,
    `--for` queued behind the others; I stopped my own queued run (by PID) and used
    `--changed HEAD`.
- **Open questions:** none.
  - Recommendation for the verifier: re-run `probe_lz.py probed` once WSL is idle, to close the
    probed half of criterion 3 on the real probe.
