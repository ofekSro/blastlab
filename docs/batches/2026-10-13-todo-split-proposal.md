# TODO.md split - proposal (not applied)

Owner task 2026-10-13, step 8. `TODO.md` is **997 lines / 65 KB** against the 1000-line cap
(CLAUDE.md §5). Nothing below is applied until the owner approves; the ids stay as they
are, and every moved section leaves its heading in `TODO.md` with a pointer, so the ids
cited from code still resolve (code cites `TODO.md` HD1, HD1-3, HD1-16, HD1-17, HD1-19,
P1-4, P1-14, N5-7, N5-11 - none of those moves).

| # | Section (TODO.md lines) | Why it can go | To | Lines out | Left in TODO.md |
|---|---|---|---|---|---|
| 1 | `## P3 — Capabilities and improvements, on request` (840-927, 88 lines, 5.5 KB) | On request only; nothing in it is planned. Code cites `P3-7`, `P3-8`, `P3-25` without `TODO.md` (closed, DONE.md §0e) | new `docs/backlog/p3-on-request.md` | 88 | heading + 2-line pointer naming the ids (4 lines): **-84** |
| 2 | `## P4 — Environment, disk, personal` (928-966, 39 lines, 1.9 KB) | Environment notes, low urgency; P4-3's trap is already CLAUDE.md §8.2 / §8.5 | new `docs/backlog/p4-environment.md` | 39 | heading + pointer (4 lines): **-35** |
| 3 | P1 research block: "The residual ≈2 % parallel-vs-serial peak offset", "Claim 3 — three experiments designed and not run", "Corrections the audit implies" (280-324, 45 lines, 2.7 KB) | Verification research, not app work; dormant since the audit | new `docs/verification/open-research.md` | 45 | the three headings, one pointer line each (9 lines; `test_foam_3d_smoke.py:138` says the offset is "tracked in TODO", so its heading stays): **-36** |
| 4 | The 4 closed `GUI`/`OUT` table rows (lines 54-56, 71; 3.3 KB) | Closed; the file already used for them is `docs/history/todo-closed.md` | `docs/history/todo-closed.md` (append) | 0 net | each row shortened to `✅ <date>, DONE.md §0x - full row in docs/history/todo-closed.md`: **0 lines, -3 KB** |

**Before → after:** 997 → **842 lines** (-155), 65 KB → about **52 KB**. Headroom for
~15 batch closures at today's rate.

Not proposed: the `HD1` block (code cites it), `Closed items that code comments still
cite` (`N5-7`, cited), `Owner decisions waiting for you` and `Standing rules` (short and
read every batch), P1-24 (already collapsed to its citing files).

Apply as one commit `docs: TODO.md split, P3/P4/research out (owner <date>)`, by Edit and
Write only (CLAUDE.md §8.1), with `docs/00-INDEX.md` gaining the three new files.
