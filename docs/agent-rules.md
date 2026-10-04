# Rules for every agent working in blastlab

Every subagent prompt says "follow docs/agent-rules.md". Read it once; it is short on
purpose. It adds to `CLAUDE.md`, never replaces it. Owner-approved 2026-10-04.

## Never touch

- Never stage or modify the owner's private paths: `docs/references/INDEX.md`,
  `docs/references/ViperTheoryManual_Client.pdf`, `docs/references/ViperTheoryManual_Client.txt`,
  `docs/references/viper_vtk_sample/`, `docs/qa/2026-09-27-out-3/`,
  `docs/qa/2026-09-27-viewer-polish/`. Stage by explicit path only - never `git add -A` / `.`.
- `blastlab/gui/` (Tk) stays untouched unless the task names it (CLAUDE.md §9).
- No numerical change, no solver default change, no edit to a committed behaviour /
  number test or a golden unless the plan names it and the owner approved it. Layout
  pins may change, listed with the reason (`docs/gui-redesign-plan.md` §9).
- Never delete anything in `/root/blastlab_runs`. Before any WSL use,
  `wsl -d Ubuntu -- pgrep -a blastFoam` must be empty (CLAUDE.md §8.6).
- Never a broad process kill (no `taskkill` by image name or window title). Stop only
  processes you started, by PID. Leave other processes alone - the owner may be running
  another session. Remove any git worktree you create.

## How to edit and commit

- Every file edit through Edit/Write or a Python script **file** in the scratchpad.
  Never `sed -i`, never heredoc'd edits or heredoc'd Python, never PowerShell strings for
  file content (CLAUDE.md §8.1).
- One commit per task, style `area: what changed (<TODO id>)`. Each message in a NEW,
  uniquely named file (include your role and a counter, e.g. `impl_msg_03.txt`) and
  `git commit -F <file>`. A reused message file once committed the wrong text (F19).
  End every message with the attribution line the session gives you. Type non-ASCII
  literally. Never amend, never force, never push.
- Do not ask questions. A non-blocking choice: take the sensible default and record it as
  a decision row where the plan says (D-rows / F-rows); an engineering question goes in
  the report.

## Running things

- GUI: throwaway settings for every MainWindow (`ui/testing.private_settings()`); run the
  CLAUDE.md §8.2 cleanup dry run before building the app (expect `False`).
- Geometry, dialogs-on-screen and viewer claims: real platform (`QT_QPA_PLATFORM` unset),
  Win32 as ground truth, `if __name__ == '__main__':` on scripts that may start the
  viewer child (CLAUDE.md §8.7).
- The home PC has 8 GB RAM: heavy suites and harness passes ONE AT A TIME. A
  `MemoryError` on a heavy suite: rerun it alone before blaming code. Harness with
  `PYTHONIOENCODING=utf-8`. Long passes: `python -u` in the background, poll.
- `test_regression.py` must stay byte-identical; run it last.

## Token budget - work as if paid in tokens

- Read big files by section: Grep first, then Read the lines you need. Never Read a file
  over ~600 lines whole unless the task is that file.
- From `docs/gui-redesign-decisions.md` read only the open rows the task cites.
- Per task, run only the suites for the files you touched; the full matrix once, at the end.
- Screenshots: save them as evidence; open at most 2-3 yourself.
- Never paste file content or diffs into a report. Line refs and commit hashes only.
- **Final message ≤ 40 lines.** The full report goes in the report file the prompt names;
  if the tool refuses that write, put the report in the final message instead.
