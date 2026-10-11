# Batch gui-14-backlog, Part C - implementation report

Base `2f947c4` (master, P1-23 already in). Docs only; no code, no DONE entry, GUI-14 not closed.

## C1 - DONE.md under the cap - DONE, commit `af2ddb1`
Moved DONE.md §0l-§0w (old lines 36-417) verbatim to `docs/history/done-gui-redesign.md` (new
header in the style of `done-2026-09.md`). DONE.md got a `## 0l-0w ... — moved` pointer and a
table row; `docs/00-INDEX.md` got a row, and its "(§0l on)" became "(§1 on)".
Files: `DONE.md`, `docs/history/done-gui-redesign.md`, `docs/00-INDEX.md`.
- DONE.md <= 700 lines: PASS, 1017 -> 641. New file <= 1000: PASS, 394.
- §5 and §7 byte-identical: PASS (`c1_check.py`: §5, §7, and everything from `## 1.` to the end
  byte-identical to HEAD~; the moved block is a verbatim substring of the new file).
- Mojibake grep over the three files: PASS, 0 hits.

## C2 - TODO.md under the cap - DONE, commit `2779435`
Precondition held (`git status --porcelain TODO.md` empty before the edit and the commit).
Moved verbatim:
- the GUI-13 row -> the GUI table of `docs/history/todo-closed.md` (after GUI-12);
- the two HD1 pointers (13 lines) -> a new section at the end of `todo-closed.md`; TODO.md has one
  3-line pointer naming `HD1-12` and `HD1-3`;
- P2-14 item 7 -> same new section; TODO.md keeps a one-line pointer;
- P1-14 source record (Table 8-7 text and gap table, 22 lines) -> new
  `docs/verification/material-table-sources.md`; heading, decision list and a link stay.
Files: `TODO.md`, `docs/history/todo-closed.md`, `docs/verification/material-table-sources.md`.
(`docs/00-INDEX.md` got the index row for the new file in the report commit.)
- TODO.md <= 980: PASS, 1009 -> 976. `todo-closed.md` <= 1000: PASS, 252. New file: 32.
- Cited ids (`TODO.md <id>` in `blastlab`, `.claude`: HD1, HD1-3, HD1-16, HD1-17, HD1-19,
  N5-7, N5-11, P1-4, P1-14): none missing from TODO.md. RESUME note, `GUI-14` row, P1-23 present.
- Earlier ids still in TODO.md: all but `GUI-12`, which occurred only in the moved GUI-13 row's
  text; the `GUI-1..13` row (which stays) covers it and links the closed rows.
- Mojibake grep: PASS, 0 hits.

## Scripts (scratchpad `C:\Users\ROTEM~1.OFE\AppData\Local\Temp\claude\c--Users-rotem-ofek-OneDrive---Technion-BlastFoam\9e7c70fd-103e-4dd1-ac72-2a2b0439a54d\scratchpad`)
`c1_move.py`, `c1_check.py`, `c2_move.py`, `c2_check.py`. Commit messages `implC_msg_01/02.txt`.

## Notes
- Numerical changes: none. GUI screens: none.
- Engineering issues: none. The old pointers were copied into `todo-closed.md` only because the
  plan says "move"; they add nothing and can be dropped.
- Open questions: none. At the GUI-14 close, /bl-todo adds its DONE entry (DONE.md has 359 lines
  of headroom, TODO.md 4); TODO.md has little room, so the close should move something too.
