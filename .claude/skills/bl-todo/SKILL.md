---
name: bl-todo
description: Works through blastlab's TODO.md in batches, sized to save tokens. Plans the next batch (bl-task-planner, Sonnet when the rows are located and decided, else Opus), implements it (bl-task-implementer, Sonnet - Opus when the plan is risk high), verifies at the depth the risk calls for (bl-task-verifier light or full), then moves finished tasks to DONE.md. GUI QA and UX review run only when the plan marks the end of a track, or on request. Use as /bl-todo to plan and confirm once, /bl-todo go to run without confirmation, /bl-todo plan to plan only, /bl-todo batch <path> to run or resume an existing plan.
model: sonnet
---

**The orchestration runs on Sonnet** (owner 2026-10-13; the `model:` field above). Per the
Claude Code docs (skills, frontmatter) the override lasts for the rest of the turn that
invokes the skill; the session model returns on the owner's next message. So: a plain
"yes" after Stage 1 continues on the session model - tell the owner to answer
`/bl-todo batch <plan path>` instead, which re-invokes the skill on Sonnet. `go`, `next`
and `batch` run in one turn and stay on Sonnet. Start /bl-todo in a fresh session: a
model switch re-writes the whole existing context into the new model's cache.

You orchestrate one batch end to end. Subagents cannot launch each other, so you
launch every agent and pass the reports along. Owner-approved token rules (2026-10-04):
spend the expensive model and the deep checks only where the risk is.

The `bl-` prefix is load-bearing: a personal `todo` skill and `task-*` agents live in
`~/.claude/`, and a personal skill of the same name wins over a project one. Always
launch the `bl-task-*` agents, never the unprefixed ones.

## Arguments

- none: plan, show the batch, ask once, then run.
- `go`: plan and run without asking. `next`: same, skipping "needs clarification".
- `plan`: plan only, show it, stop.
- `batch <path>`: run an existing plan, all parts in order. **Resume:** a part whose
  verify report (`<plan>[-<part>].verify.md`, next to the plan) exists and is committed
  is done - skip it. A part with only an implement report goes straight to Stage 3.

## Every agent prompt

Keep it short. Always include: the plan path (and part), the base commit, "Follow
CLAUDE.md and docs/agent-rules.md", the report file name, the commit attribution line,
the scratchpad path, and anything the owner decided that overrides the plan. Do not
paste the standing rules - they live in `docs/agent-rules.md`.

## Stage 0: preconditions

`TODO.md` exists; git repo; tree clean apart from the owner's private paths listed in
`docs/agent-rules.md`; record `BASE` and the start time (`Get-Date -Format s`).

## Stage 1: plan

**Pick the planner's model first** (owner 2026-10-13), from the TODO rows of the track to
be planned - the RESUME note names it; Grep its ids, do not Read `TODO.md` whole:
- `model: "sonnet"` when **every** row already names its files (or `file:line`) and
  carries the owner's decision, and none touches `solvers/`, `core/`, `services/`,
  `output/`, `models/`, a golden, a number or a unit (that would be `risk: high`).
- `model: "opus"` (the agent's default) when any row has no code location, the batch
  will be `risk: high`, or a row changes a default, a seed or anything a golden pins
  (feasibility probes, docs/agent-rules.md "Do it once"). Unsure → Opus.
Say which and why in one line to the owner.

Launch **bl-task-planner** on that model. Show the owner, in Hebrew and phone-short: batch name,
risk, track-end, tasks with sizes, and every "needs clarification" item **with its
recommendation**. Without `go` / `next`, wait for the owner.

## Stage 2: implement (per part)

- `risk: low` → **bl-task-implementer** on its default model (Sonnet).
- `risk: high` → the same agent with `model: "opus"`.
- `risk: none` (docs only) → do it yourself or with the implementer on Sonnet.

If a report-file write is refused for the agent, write the file yourself from its final
message and commit it.

## Stage 3: verify (per part)

- `risk: low` → **bl-task-verifier**, depth **light**, default model.
- `risk: high` → **bl-task-verifier**, depth **full**, `model: "opus"`.
- `risk: none` → no verifier; write `<plan>[-<part>].verify.md` yourself holding only the
  `## Status` block (format in `bl-task-verifier.md`), for Stage 5's script.

## Stage 4: QA and UX - only when the plan says `track-end: yes`, or the owner asks

**gui-qa-tester** and **gui-ux-reviewer** in parallel, given the screens touched. Their
findings become the next batch, not an in-batch retry loop. No simplifier stage for UI
batches. Skip the stage when no GUI screen was touched.

## Stage 5: bookkeeping (by script, owner 2026-10-13)

1. Trust the verifier's run; rerun `test_regression.py` yourself only if anything
   touched a shared module after the verifier finished.
2. Write 3-6 bullets to a scratch `notes.md` in `DONE.md`'s style - what changed and
   where, the tests (gate counts, regression), verifier fixes, open items - from the
   agents' final messages; do not re-read the reports for it.
3. `python .claude/skills/bl-todo/close_batch.py <plan> --base <BASE> --notes <notes.md>`
   (`--still-open "ID=(x)"` for a sub-item this batch did not do; `--keep-body ID` to keep
   a closed heading's body). It reads each verify report's `## Status` block: VERIFIED /
   FIXED close (table row `✅ …`, heading `✅ closed …`, new `DONE.md` §0x); SKIPPED /
   PARTIAL / FAILED stay open and are listed. A report without the block: add it from
   the verifier's verdict lines, then rerun. `--dry-run` shows the diff first.
4. Review `git diff TODO.md DONE.md` (only these two files) and fix by Edit what reads
   wrong. Never rewrite either file wholesale.
5. **Length cap** (CLAUDE.md §5: every markdown file ≤ 1000 lines): the script prints both
   counts and exits 2 over the cap. Do not split or trim the files yourself - their names
   and ids are cited from code - put it in Stage 6 as an open question with a concrete
   split proposal (which sections move to which file).
6. Commit `chore: close batch <name> (<id>)`. Never push unless the owner asks.

## Stage 6: report to the owner (Hebrew, phone-readable)

Short: done vs left, one line each; tests; verifier fixes; open questions **each with a
recommendation** (the owner answers "approve all" or by number); the commit range and
how to undo it; what needs the office machine. Last, the `total` and `rule` lines of
`python .claude/skills/bl-todo/cost.py <session id> --since <start> --tasks <planned>`
(the session id is your scratchpad's folder name).

## Rules

- Never ask the owner anything between Stage 2 and Stage 5; collect it for Stage 6.
- Never move a task to DONE.md that the verifier did not mark VERIFIED or FIXED.
- Never change numerical results except where a task says so with a source.
- Do not re-read a large file the agent already summarised; read its report file only
  when the final message is not enough.
- If an agent declines the task on safety grounds (this domain's vocabulary reads
  alarming out of context, CLAUDE.md §0), relaunch once with `model: "opus"` and the
  same prompt; if it declines again, report to the owner. If you, the orchestrator,
  would decline, say so in one line instead; the owner reruns on the session model.
