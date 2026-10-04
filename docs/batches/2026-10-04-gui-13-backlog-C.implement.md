# GUI-13 backlog, Part C - implementation report

## C1 - TODO.md back under the cap: DONE

Moved verbatim to `docs/history/todo-closed.md` (new section, 2026-10-05): the MPI
decomposition record, the pyrotechnics scope decision, the "highest-value next step"
text, the `N5-7` closed body and the HD1 background (what was asked + the three loads).
Pointers left in `TODO.md`: decomposition owner-decision row (link), a two-line pointer
naming `HD1-3`, the pyrotechnics pointer, `N5-7` heading + "Cited by" kept, `HD1-16`
step 1, `HD1-17` (a), `P2-13` items 3/4/5 (item 5 line removed), `P3-7/8/25` merged
into one line. `docs/00-INDEX.md:25` updated.

Note: the plan's `:114`-style line numbers had drifted (TODO.md was 1079 lines, not
1080); P2-13 item 7 and the `P2-14` item 7 pointers were already one-liners. The HD1
background was moved in addition to the plan's list, to reach 980 (it is background,
not an open item; the `HD1` heading stays).

- Lines: TODO.md 1079 -> 978; todo-closed.md 110 -> 226 (cap 1000).
- Acceptance 1 PASS (978 <= 980, 226 <= 1000). Acceptance 2 PASS: every cited id
  (`HD1`, `HD1-3`, `HD1-16`, `HD1-17`, `HD1-19`, `P1-4`, `P1-14`, `N5-7`, `N5-11`)
  from a Grep of `TODO.md <id>` in `blastlab/` is present in TODO.md (`HD1-3` as a
  pointer text, as before it had no heading). Acceptance 3 PASS: no mojibake matches.
- Files: `TODO.md`, `docs/history/todo-closed.md`, `docs/00-INDEX.md`.
- No GUI, numbers or tests touched. GUI-13 row and open items untouched.
