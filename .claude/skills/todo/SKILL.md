---
name: todo
description: Works through blastlab's TODO.md in batches, sized to save tokens. Plans the next batch (task-planner, Opus), implements it (task-implementer, Sonnet - Opus when the plan is risk high), verifies at the depth the risk calls for (task-verifier light or full), then moves finished tasks to DONE.md. GUI QA and UX review run only at the end of a track or on request. Use as /todo to plan and confirm once, /todo go to run without confirmation, /todo plan to plan only, /todo batch <path> to run an existing plan.
---

You orchestrate one batch end to end. Subagents cannot launch each other, so you
launch every agent and pass the reports along. Owner-approved token rules (2026-10-04):
spend the expensive model and the deep checks only where the risk is.

## Arguments

- none: plan, show the batch, ask once, then run.
- `go`: plan and run without asking. `next`: same, skipping "needs clarification".
- `plan`: plan only, show it, stop.
- `batch <path>`: run an existing plan (all parts, in order).

## Every agent prompt

Keep it short. Always include: the plan path (and part), the base commit, "Follow
CLAUDE.md and docs/agent-rules.md", the report file name, the commit attribution line,
the scratchpad path, and anything the owner decided that overrides the plan. Do not
paste the standing rules - they live in `docs/agent-rules.md`.

## Stage 0: preconditions

`TODO.md` exists; git repo; tree clean apart from the owner's private paths listed in
`docs/agent-rules.md`; record `BASE`.

## Stage 1: plan

Launch **task-planner** (Opus). Show the owner, in Hebrew and phone-short: batch name,
risk, tasks with sizes, and every "needs clarification" item **with its recommendation**.
Without `go` / `next`, wait for the owner.

## Stage 2: implement (per part)

- `risk: low` → **task-implementer** on its default model (Sonnet).
- `risk: high` → the same agent with `model: "opus"`.
- `risk: none` (docs only) → do it yourself or with the implementer on Sonnet.

If a report-file write is refused for the agent, write the file yourself from its final
message and commit it.

## Stage 3: verify (per part)

- `risk: low` → **task-verifier**, depth **light**, default model.
- `risk: high` → **task-verifier**, depth **full**, `model: "opus"`.
- `risk: none` → no verifier.

## Stage 4: QA and UX - only at the end of a track, or when the owner asks

**gui-qa-tester** and **gui-ux-reviewer** in parallel, given the screens touched. Their
findings become the next batch, not an in-batch retry loop. No simplifier stage for UI
batches.

## Stage 5: bookkeeping (you, exact and small)

1. Trust the verifier's run; rerun `test_regression.py` yourself only if anything
   touched a shared module after the verifier finished.
2. VERIFIED / FIXED tasks: mark them done in `TODO.md` (keep its ids and order) and add
   an entry to `DONE.md` in the file's existing style: what, tests, verifier fixes, open
   items, commit range. Never rewrite either file wholesale.
3. SKIPPED / PARTIAL / FAILED stay in `TODO.md` with a one-line reason.
4. Commit `chore: close batch <name> (<id>)`. Never push unless the owner asks.

## Stage 6: report to the owner (Hebrew, phone-readable)

Short: done vs left, one line each; tests; verifier fixes; open questions **each with a
recommendation** (the owner answers "approve all" or by number); the commit range and
how to undo it; what needs the office machine.

## Rules

- Never ask the owner anything between Stage 2 and Stage 5; collect it for Stage 6.
- Never move a task to DONE.md that the verifier did not mark VERIFIED or FIXED.
- Never change numerical results except where a task says so with a source.
- Do not re-read a large file the agent already summarised; read its report file only
  when the final message is not enough.
- If an agent declines the task on safety grounds (this domain's vocabulary reads
  alarming out of context, CLAUDE.md §0), relaunch once with `model: "opus"` and the
  same prompt; if it declines again, report to the owner.
