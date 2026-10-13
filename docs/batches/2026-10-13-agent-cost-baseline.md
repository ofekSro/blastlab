# Agent cost baseline, 2026-10-13

Measured before changing anything in `.claude/` (owner task 2026-10-13, step 0).
Sources: `python .claude/skills/bl-todo/cost.py <session>` on the four most recent
/bl-todo sessions, plus throwaway scripts on the same transcripts for the per-role,
start-up and dollar figures (method below).

| Session | Batch | Total (units) |
|---|---|---|
| `9e7c70fd` | gui-15-backlog A+B, QA, UX | 9.92 M |
| `ba57239d` | p1-23-ignition-radius plan + A, gui-15 B, QA, UX | 14.22 M |
| `0d66e9d8` | gui-final plan (twice) + part B implement/verify | 15.50 M |
| `190303b8` | gui-final part B implement + verify | 8.87 M |

Units are cost.py's input-token units (read 0.1, write 1.25/2, output 5). Dollars use the
prices in the claude-api skill table cached 2026-09-25: Opus 5.5 $4 in / $20 out, Sonnet
5.5 $2 / $10, **cache reads $0.20 on both** - so a read-heavy agent is far less than 2x
cheaper on Sonnet.

## Share per role (all four sessions: 48.5 M units, ≈ $123)

| Role | Units | Share | $ | Share |
|---|---|---|---|---|
| implementer | 19.49 M | 40 % | 44.7 | 36 % |
| orchestrator (main session) | 8.16 M | 17 % | 25.7 | 21 % |
| planner | 6.99 M | 14 % | 18.7 | 15 % |
| verifier | 5.03 M | 10 % | 12.7 | 10 % |
| gui-qa-tester | 4.95 M | 10 % | 9.9 | 8 % |
| gui-ux-reviewer | 2.23 M | 5 % | 6.4 | 5 % |
| Explore (planner side-trips) | 1.66 M | 3 % | 4.8 | 4 % |

Of the verifier's 10 %, the two **light** (Sonnet, risk: low) runs were 0.11 M and 0.14 M
units, ≈ $0.25 each; the rest is `full` on Opus (risk: high).

## Fixed start-up cost of one agent

- Context at the first call: **21-22 k tokens** for every agent type (system prompt, tools,
  CLAUDE.md, MEMORY.md, the prompt). CLAUDE.md (24 250 chars, ≈ 6.6 k tokens) and MEMORY.md
  arrive as an `instructions` attachment in the subagent's first turn.
- Start-up = calls before the first Edit/Write (reading the plan, rules and code):
  implementer 0.05-0.17 M units for a normal part (4-14 calls), 0.32-1.05 M for the large
  Opus parts; light verifier 0.09-0.13 M (≈ 90 % of its whole cost); full verifier
  0.17-0.30 M; planner 0.20-0.89 M (21-58 calls of reading before it writes).
- Context grows with the part: implementer last-call context 70 k (24 calls) to 418 k
  (234 calls, 11 tasks).

## Other measurements

- **Splitting a big part costs less, not more.** Re-pricing each implementer with > 60
  calls as if it had restarted at mid-point (paying its first 10 calls again): net saving
  12 %, 23 %, 13 %, 23 % on the four large parts, ≈ 0 on the 64-call part, -9 % on the
  72-call one. The start-up of a new agent is small next to re-reading a 200-400 k context.
- **CLAUDE.md in every context** costs ≈ $3.6 of $123 (2.9 %); at 10 KB it would be ≈ $1.5.
- **Orchestrator on Sonnet** (same tokens re-priced): $25.7 → $16.3. **Planner**: $18.7 →
  $14.0. Full verifier: $12.2 → $9.6 (not proposed - risk: high stays Opus).
- **Rebuilds.** Main session 24-41 % of its own cost (gaps > 1 h while a long agent runs).
  **gui-qa-tester 62 %** in both runs it made (≈ $6 of its $9.9): it sleeps longer than
  the 5-minute subagent cache; it is a personal agent and its prompt never cites
  `docs/agent-rules.md`.
- No agent Read CLAUDE.md with the Read tool in any of the four sessions; they Read
  `docs/agent-rules.md` once as their first call.

## What the numbers say about the requested changes

| # | Change | Verdict from the data |
|---|---|---|
| 1 | Script gate instead of the light verifier | **Contradicted.** The light verifier is ≈ $0.25 per part (< 0.5 % of the four sessions); the orchestrator running three gate commands on its 100-180 k Opus context costs about the same. Not applied. |
| 2 | CLAUDE.md double load | CLAUDE.md is pre-loaded (attachment evidence above). No agent re-reads it today, so the saving is protection, not measured money. Applied. |
| 3 | Shrink CLAUDE.md | ≈ 1.7 % of /bl-todo cost, plus every other session. Applied. |
| 4 | Planner model by need | Up to -25 % of the planner (≈ 4 % of total) when Sonnet applies. Applied. |
| 5 | Orchestrator on Sonnet | ≈ -37 % of the orchestrator (≈ 7.6 % of total). Applied (skill `model:`). |
| 6 | Bookkeeping by script | Small, unmeasured (Stage 5 is a few Opus calls on a large context). Applied. |
| 7 | Fewer, larger low-risk parts | **Contradicted.** Splitting large parts saves 12-23 %; merging raises it. Not applied. |
| 8 | TODO.md split | Proposal only (owner approves). |
| 9 | Parallel mode | Wall time only, by design. Applied, opt-in. |

## Method

`cost.py` gives per-agent units. The per-role, start-up, re-pricing and split figures
come from scratch scripts that import `cost.py`'s `calls_of` / `cost` and read the
`attachment` and `tool_use` records of the same transcripts. Token count of CLAUDE.md
is chars / 3.7 (an estimate, not a tokenizer count).
