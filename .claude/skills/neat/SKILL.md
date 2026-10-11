---
name: neat
description: Proposal-first tidying of blastlab code, built for this repo. /neat scan [path] ranks files worth tidying (a script, no model). /neat <file> writes a numbered proposal to docs/tidy/. /neat apply <file> <items> applies only the approved items, behind a test gate that must stay byte-identical. Nothing is edited or committed without the owner's explicit yes.
---

Readable code, identical behaviour. `CLAUDE.md` binds you; reply in
Hebrew, short, phone-width (no wide tables). Every open decision comes
with your recommendation.

## Models and budget

| Step | Who | Model |
|---|---|---|
| scan | `scan.py` | none - deterministic |
| propose / apply, tier A | `bl-tidier` | `model: "opus"` override |
| propose / apply, tiers B-E | `bl-tidier` | its default, Sonnet |
| tests | `gate.py` | none |

- Never Read the target file yourself - the agent does. You read only
  `gate.py` / `scan.py` output and the agent's ≤ 30-line report.
- Show the owner the proposal **item lines**, not the file. The full
  proposal lives in `docs/tidy/` for anyone who wants it.
- One agent per file, at most 4 in parallel. More than 4 files → scan
  first and let the owner pick.
- **Fallback:** if a Sonnet agent refuses on safety grounds or returns an
  evasive/empty report (this field says charge, TNT, detonation in the
  ordinary engineering sense), relaunch once with `model: "opus"`, same
  prompt, and say so. If Opus declines, report it. Never reword to get
  around a refusal.

## Tiers (scan.py prints them; `bl-tidier.md` has the rules)

A numerics · B plumbing · C Qt `ui/` · D viewer `viz3d/` · E Tk `gui/` ·
X fixtures - never. Tier decides the model and what is allowed; the test
gate is the same for all.

## `/neat scan [path]` (default `blastlab`)

1. `python .claude/skills/neat/scan.py <path> --top 12`
2. Relay the ranked lines. Add your recommendation: which 1-3 files to
   propose first and why. Heavy `silent-except` counts in C/D/E are mostly
   deliberate widget-teardown guards - say so; they do not make a file a
   good target.

## `/neat <file> [<file>...]`

1. Tier from `scan.py <file> --detail` (first line).
2. Launch `bl-tidier` with: `propose`, the file path, the tier, and the
   scan detail lines (so it does not re-scan).
3. Relay: proposal path, then one line per item with its Output risk, then
   any *Engineering questions* - those also get appended to
   `docs/ENGINEERING_QUESTIONS.md`; they are never fixed here.
4. Recommend which items to take. Stop.

## `/neat apply <file> <items>`

1. **Preconditions** - stop and say which failed:
   - branch is not `master` (offer `tidy/<area>`; create it on a yes);
   - `git status --porcelain -- <file>` is empty (other dirty files are fine);
   - `docs/tidy/<slug>.md` exists and has those items not yet `APPLIED`.
2. Explain in Hebrew, ≤ 8 lines: **מה ישתנה**, **מה לא ישתנה**, **איך
   נוודא** (gate = byte regression + all fast suites). Wait for a yes.
3. `python .claude/skills/neat/gate.py --baseline` → note the `base-...`
   name. 128 suites, **~28 min** (4 lanes + a serial GUI lane; measured
   2026-10-04, 36 min serial - and serial it is under 16 GB RAM): run it in the background with `python -u`,
   no timeout, and tell the owner. On an unchanged tree it is reused
   instantly. It refuses to start if `auto_cleanup` is on (§8.2).
   Record `git status --porcelain` now.
4. Launch `bl-tidier` with `apply <items>`, file, tier.
5. `python .claude/skills/neat/gate.py --against <base-name>` (background,
   ~28 min).
   - `GATE: FAIL` → first compare `git status --porcelain` with step 3:
     the owner often edits in another session, and a file that changed
     there can be the cause. Say which. Otherwise `git checkout --
     <file>` and `git checkout -- docs/tidy/<slug>.md`, show the NEW
     FAILURE lines, stop.
   - `GATE: PASS` → show `git diff --stat` and the diff itself only if
     ≤ 60 lines (otherwise offer it).
6. Tier C: recommend `/gui-qa` before committing; do not launch it unasked.
7. Ask to commit. On a yes: write the message to a scratch file and
   `git commit -F` (§8.1) - `area: tidy <what> (neat 2,5,7)`, ending with
   the attribution line from the system reminder. Stage only `<file>` and
   its proposal. Never stage `tests/baseline/` (CRLF noise). Never push.

## Rules

- Never apply an item the owner did not name; never run `bl-tidier` in
  apply mode without a baseline gate before and an `--against` gate after.
- Architecture or moving code between modules is not tidying → `/refactor`.
  `/neat` never writes `docs/ARCHITECTURE_REVIEW.md` or `docs/UX_REVIEW*.md`.
- The gate excludes the WSL solve suites on purpose (no numeric change is
  allowed, so the byte regression is the stronger check). If an applied
  item touched a foam path and the owner wants more, offer
  `test_foam_1d_vs_native.py` after `wsl -d Ubuntu -- pgrep -a blastFoam`
  comes back empty (§8.6).
