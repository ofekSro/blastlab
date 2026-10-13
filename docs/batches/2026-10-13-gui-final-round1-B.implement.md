# Implement report - batch gui-final-round1, Part B (R2)

Base `cdbce68` (Part A done), branch `final-gui`. Owner decision 2026-10-13: Q1 = yes, so
`test_model_folder.py:1471` may become `assert notice is None` (D-R3).

## R2 - GUI-16 Stage 4 round 1: "Keep all fields" kept on purpose raises no dialog - DONE

`services/model_folder.py` `verify_and_release_scratch` (`:1286-1288`): the `notice` is built only
when `kind == 'warn' and why != KEEP_ALL_WHY`. `kept_because`, the `[note]` log line, the manifest
and every other `warn` path are unchanged. `release_decision` (`:989-1003`) decides `KEEP_ALL_WHY`
only after every failure reason, so a Keep-all run whose copy or rows failed still gets its notice.

- **Files:** `blastlab/services/model_folder.py`, `blastlab/tests/test_model_folder.py`.
- **Tests:** `gate.py --for` both files (starting state, 9/9 green); `gate.py --changed HEAD` 9/9
  green (6.2 min); `gate.py --changed cdbce68 --deep` 64/64 green (18.6 min);
  `gate.py --only regression` PASS, byte-for-byte.
- **Acceptance 1 - PASS.** `test_model_folder.py:1471` is now `assert notice is None`, and no other
  committed-test line was edited (the commit's diff shows 1 line changed in the test file).
  The `kept_because` (`:1470`) and `[note]` (`:1472`) asserts are unchanged and pass
  (`test_model_folder` green).
- **Acceptance 2 - PASS.** The other notice asserts at `:969`, `:984`, `:998`, `:1008`, `:1045`,
  `:1064` and `:1321` are unchanged and green in `test_model_folder`. Then `--deep` for the
  part, and `--only regression` last, byte-identical.
- **App start:** a MainWindow on the real platform with private settings showed and closed cleanly
  (after the §8.2 dry run: `auto_cleanup` False).
- **Commit:** `71d2920`.

## Files touched

`blastlab/services/model_folder.py`, `blastlab/tests/test_model_folder.py`, this report.

## GUI screens touched (for QA)

None in code. Behaviour seen in the GUI: after a blastFoam run with "Keep all fields in WSL" ticked
on the Run tab, no "WSL scratch was kept" error dialog appears. The `[note] WSL scratch kept` line
still shows in the Run log, and the run browser still opens the scratch. The F12 harness scenario no
longer needs to auto-dismiss a modal there.

## Numerical changes

None.

## Engineering issues noticed

- No test pins the "Keep all + failed copy still warns" precedence. It holds today by
  `release_decision`'s order. **Recommendation:** add a one-case check in a later batch if the owner
  wants it. I did not add it here, because the plan limits this part's test edits to the one line.
- `git commit` prints "failed to delete .git/worktrees/agent-*: Permission denied" from auto-gc on
  stale worktrees that other sessions left. This is harmless; the commit lands. **Recommendation:**
  the owner runs `git worktree prune` once no other session is using them.

## Open questions for the owner

None.
