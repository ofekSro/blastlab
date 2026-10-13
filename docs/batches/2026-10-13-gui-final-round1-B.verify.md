# Verify report - batch gui-final-round1, Part B (R2)

Depth **full** (`risk: high`). Base `cdbce68`, implementer commits `71d2920` (code + test),
`d85801f` (report). Owner decision 2026-10-13: Q1 = yes, so `test_model_folder.py:1471` →
`assert notice is None` is approved (D-R3).

## R2 - GUI-16: "Keep all fields" kept on purpose raises no dialog - FIXED

Code: `services/model_folder.py:1286-1288` builds `notice` only when
`kind == 'warn' and why != KEEP_ALL_WHY`. The single consumer, `ui/run_controller.py:354`
(`if notice: show_error(...)`), and the CLI (`solvers/foam/cli_run.py:31`) both skip a `None`.
`kept_because`, the `[note]` line (`:1284`), the manifest and the other `warn` paths are untouched.
The docstring at `:1242-1244` ("when ... the copy or a row failed; None otherwise") was already true
after the change. The diff adds no number, unit, sign, swallowed error or GUI-thread access.

- **Acceptance 1 - PASS.** `git diff cdbce68..71d2920` changes exactly one committed-test line,
  `test_model_folder.py:1471`. `:1470` and `:1472` are unchanged. Check: the scratch script
  `verify_r2_mutants.py` runs the test on HEAD (PASS) and again with the pre-fix condition
  `if kind == 'warn':` loaded into the module. The test then FAILS, so the changed line can fail.
- **Acceptance 2 - PASS.** The notice asserts at `:969 :984 :998 :1008 :1045 :1064 :1321` are
  unchanged. `python blastlab/tests/test_model_folder.py` gives PASS.
  `gate.py --changed cdbce68 --deep`: 64/64 green, 19.3 min. `gate.py --only regression`, run last:
  PASS, byte-for-byte.
- **The implementer's flag, judged.** Before this verify, "Keep all + a failed copy still warns"
  held only because `release_decision` (`:989-1003`) checks `keep_all` after the row and hash
  checks. No test pinned that order. A refactor that moved `keep_all` up would silently drop the
  dialog for a failed copy, which is a real defect (medium). **Fixed** with the new check
  `test_e_keep_all_failed_copy_still_warns` (`test_model_folder.py:1483-1501`). It covers a flipped
  byte in the foam copy and a failed row, both with Keep all ticked. Each case must give a notice
  that names the file, a `kept_because` that is not `KEEP_ALL_WHY`, and a `[warn]` log line. It is a
  new test, so no committed line was edited. Check that it can fail: the mutant with `keep_all`
  decided before the row check FAILS it (`('system/controlDict', None)`), and HEAD PASSES it.
- **Leftover doc.** `blastlab/README.md:134-136` still said the Keep all reason goes into "the
  folder notice". **Fixed:** it now says `manifest.json` plus a `[note]` log line, with no dialog.
- **Live check.** No WSL solve was run. The plan names no live demonstration for R2, and the GUI
  wiring is one `if notice:`. §8.2 dry run (`auto_cleanup` False) and §8.6 pgrep (empty) were
  done before the gate.

Fixes: `c28e54d` (the new check), `a55e4e5` (README).

## Defects

| Where | Severity | State |
|---|---|---|
| `test_model_folder.py` - no pin that Keep all + failed copy/row still gives the dialog | medium | fixed `c28e54d` |
| `blastlab/README.md:134-136` - stale "folder notice" for Keep all | low | fixed `a55e4e5` |

## Engineering questions

None. No number changed. `_qa_ui_harness.py` F12 and F36 still tick Keep all. They no longer meet
a dialog, and they assert none, so nothing there needs changing.

## GUI screens for QA

- Run tab, blastFoam 2D with "Keep all fields in WSL" ticked: at the end, no "WSL scratch was kept"
  dialog appears, the log shows `[note] WSL scratch kept (Keep all fields in WSL was ticked)`, and
  the run browser opens the scratch.

Verdict: R2 FIXED. The change is correct and minimal; the order it depends on is now pinned, and the README is updated.

## Status

- R2 GUI-16: FIXED c28e54d a55e4e5
