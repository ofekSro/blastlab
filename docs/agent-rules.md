# Rules for every agent working in blastlab

Every subagent prompt says "follow docs/agent-rules.md". Read it once; it is short on
purpose. It adds to `CLAUDE.md`, never replaces it. Owner-approved 2026-10-04.
`CLAUDE.md` is already in every agent's context when it starts (an `instructions`
attachment in the first turn, checked in the transcripts 2026-10-13) - never Read it.

## Never touch

- Never stage or modify the owner's private paths: `docs/references/INDEX.md`,
  `docs/references/ViperTheoryManual_Client.pdf`, `docs/references/ViperTheoryManual_Client.txt`,
  `docs/references/viper_vtk_sample/`, `docs/qa/2026-09-27-out-3/`,
  `docs/qa/2026-09-27-viewer-polish/`. Stage by explicit path only - never `git add -A` / `.`.
- `blastlab/gui/` (Tk) is frozen (owner 2026-10-13, CLAUDE.md §9): never edit it, and never
  run its `test_gui_*` suites or `_qa_gui_harness.py` as a gate.
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
  `PYTHONIOENCODING=utf-8`. Long passes: `python -u` in the background, poll at most
  4 min apart (Token budget).
- Run suites through `python .claude/skills/neat/gate.py`: one line per failure, logs
  out of your context, one lane on the 8 GB PC. `--for <files>` before you start,
  `--changed HEAD` per task (the uncommitted edit), `--changed <base>` for a whole part,
  `--deep` at full verification depth, `--only regression` last. Its *no fast suite
  imports* line names files no suite covers - pick those suites yourself.
- `test_regression.py` must stay byte-identical; run it last.

## Do it once (owner-approved 2026-10-05)

- **Planner: probe feasibility before planning.** Any task that changes a default, a
  seed value or anything a golden pins gets a cheap check in the plan itself (validate
  the case unprobed and probed, grep `char_golden/` and `baseline/` for the value). A
  task that would fail its own stop rule is not planned; it goes to the owner as a
  question with the numbers.
- **New tests pin meaning, not prose.** Assert that the warning exists, names `G3`,
  names the wall - not the whole sentence. Exact-string pins only where the string is
  the deliverable.
- **Implementers do not run the big harnesses** (`_qa_ui_harness.py`, `_qa_gui_harness.py`).
  They run once, in the QA stage. Any harness `--resume` gets an explicit `--out`.
- **UX findings: only medium or higher become tasks.** Low ones go to a "parking"
  section of the UX report and are not planned unless the owner picks them.

## Token budget - work as if paid in tokens

- **Never let more than 4 minutes pass between two of your tool calls.** A subagent's
  prompt cache lives 5 minutes; after a longer gap the whole context is written again at
  full price. `Start-Sleep 540`-`595` waits cost a third of the 2026-10-04 /bl-todo run
  (measured 2026-10-11). Anything that may run past ~3 min (gate.py on more than a few
  suites, a harness, a WSL solve): `run_in_background`, then poll with `Start-Sleep 240`
  or shorter.
- Independent calls go in ONE message: several Reads, Greps, or a Read and a Grep that
  do not depend on each other. Every message re-reads the whole context; more than half
  of the implementers' messages carried a single call.
- Read big files by section: Grep first, then Read the lines you need. Never Read a file
  over ~600 lines whole unless the task is that file.
- From `docs/gui-redesign-decisions.md` read only the open rows the task cites.
- Per task, run only the suites for the files you touched; the full matrix once, at the end.
- Screenshots: save them as evidence; open at most 2-3 yourself.
- Never paste file content or diffs into a report. Line refs and commit hashes only.
- **Final message ≤ 40 lines.** The full report goes in the report file the prompt names;
  if the tool refuses that write, put the report in the final message instead.
