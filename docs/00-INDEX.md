> **Academic CFD — blast-wave gas dynamics, Technion.** This project computes a
> pressure field in air and the structural load it produces, for blast-resistant
> design and explosive-safety siting (UFC 3-340-02, Kingery-Bulmash).
> Energetic materials enter only as a published equation of state. Scope: [SCOPE.md](SCOPE.md)

# Documentation index

Every file here is capped at 1000 lines. The working documentation is English;
the original Hebrew notes survive only in git history (`docs/archive/`).

## Start here

| File | What is in it |
|---|---|
| [../README.md](../README.md) | What this project is, what it computes, how to run it |
| [SCOPE.md](SCOPE.md) | The full statement of scope, the standards it is written against, and the glossary |
| [../CLAUDE.md](../CLAUDE.md) | Working context: environment, conventions, traps, invariants (under 10 KB since 2026-10-13) |
| [traps.md](traps.md) | CLAUDE.md §8 in full: the seven traps and their history |
| [physics-notes.md](physics-notes.md) | CLAUDE.md §7: afterburn, activation, impulse, AMR, memory models |
| [layout.md](layout.md) | CLAUDE.md §1 and §5: the three solver paths and the source tree |
| [glossary.md](glossary.md) | CLAUDE.md §2: the glossary |
| [agent-rules.md](agent-rules.md) | Rules every subagent follows (edit, commit, run, token budget) |

## Work management

| File | What is in it |
|---|---|
| [../TODO.md](../TODO.md) | **Open work only**, ordered GUI → OUT → HD1 → P0 → P4 |
| [standing-rules-and-tests.md](standing-rules-and-tests.md) | The standing rules for every task and the test matrix (out of TODO.md, 2026-10-04) |
| [backlog/p3-on-request.md](backlog/p3-on-request.md) | TODO.md P3, capabilities on request (out of TODO.md, 2026-10-13) |
| [backlog/p4-environment.md](backlog/p4-environment.md) | TODO.md P4, environment, disk, personal (out of TODO.md, 2026-10-13) |
| [verification/open-research.md](verification/open-research.md) | The P1 research block: parallel-vs-serial offset, Claim 3, audit corrections (out of TODO.md, 2026-10-13) |
| [history/todo-closed.md](history/todo-closed.md) | Closed GUI / OUT rows and the HD1 status, background and deviation records, the MPI-decomposition and pyrotechnics records, the closed `N5-7` body (out of TODO.md, 2026-10-04 and 10-05) |
| [../DONE.md](../DONE.md) | The completed record (§1 on), the timeline, and **the identifier index that code comments cite** |
| [history/done-2026-09.md](history/done-2026-09.md) | DONE.md §0-§0k: the HD1.3 track and the batches of 2026-09-20 … 09-28 |
| [history/done-gui-redesign.md](history/done-gui-redesign.md) | DONE.md §0l-§0w: the GUI-redesign batches of 2026-09-28 … 10-05 |

## Verification — what has been checked, and how

| File | What is in it |
|---|---|
| [verification/physics-anchors.md](verification/physics-anchors.md) | The Kingery-Bulmash anchor, every measured number, the reference chain, and the measurement discipline |
| [verification/blastfoam-claims.md](verification/blastfoam-claims.md) | The independent adversarial audit of the five defects attributed to blastFoam — verdicts, pre-registered rules, and the runs that settle what is left |
| [verification/solver-options-review.md](verification/solver-options-review.md) | Every dictionary the code generates, against the official guide and the vendor source. Also the catalogue of guide features not yet used |
| [verification/material-table-sources.md](verification/material-table-sources.md) | P1-14: the JWL material table against LLNL Table 8-7, row by row (moved out of `TODO.md`, 2026-10-11) |
| [verification/remap-chain-gaps.md](verification/remap-chain-gaps.md) | The 1D→2D / 2D→3D / 1D→3D hand-offs and the missing 3D→3D: every gap with its evidence, behind `TODO.md` P1-20..22, P3-14, P2-26..30, P3-27..28 (2026-10-11) |

## History — how things came to be the way they are

| File | What is in it |
|---|---|
| [history/qa-nights.md](history/qa-nights.md) | Three unattended QA nights and the UX review: what was measured, what was refuted, and the traps found |
| [history/ui-migration.md](history/ui-migration.md) | The PySide6 migration M0–M7, and **the standing owner decision that Tk stays forever** |

## Operations

| File | What is in it |
|---|---|
| [heavy-runs.md](heavy-runs.md) | The heavy-run catalogue R1–R9, what each answered, and the ground rules for an unattended run |
| [model-folder-and-vtk-plan.md](model-folder-and-vtk-plan.md) | **The `OUT` track (owner, 2026-09-26, highest priority):** mandatory model folder, Viper-style VTK output options, newest-fields-only in WSL, the rest of the Viper matrix, and the disk rebuild — decisions, specification, tasks, acceptance criteria |
| [wsl-disk-reclaim-plan.md](wsl-disk-reclaim-plan.md) | Why the 481 GB WSL disk cannot be shrunk in place, and the prune → export → trial import → rebuild procedure with its six owner decisions (`OUT-5`) |

## The application and the learning material

| File | What is in it |
|---|---|
| [../blastlab/README.md](../blastlab/README.md) | The application itself: tabs, options, features; [where a run's files go](../blastlab/README.md#where-a-runs-files-go) (the model folder, `OUT-1`) |
| [../BlastFoam_Basic_Info/](../BlastFoam_Basic_Info/) | Learning material — JWL parameter tables, a cheatsheet (Hebrew); the PDFs themselves are in [references/](references/) |

## Archive (removed from the tree, 2026-10-05)

The 15 original Hebrew work-management files of the 2026-09-21 consolidation were
deleted from the working tree; they live in git history under `docs/archive/`
(`git log -- docs/archive`). Where their content is now:

| Original | Where its content is now |
|---|---|
| `TODO.md` | [../TODO.md](../TODO.md) (open) + [../DONE.md](../DONE.md) (closed) + history files |
| `DONE.md` | [../DONE.md](../DONE.md) |
| `NIGHT_RESULTS.md`, `NIGHT_LOG.md`, `NIGHT_RUN.md` | [history/qa-nights.md](history/qa-nights.md), [heavy-runs.md](heavy-runs.md) |
| `NIGHT2_RESULTS.md`, `NIGHT2_LOG.md` | [history/qa-nights.md](history/qa-nights.md) |
| `NIGHT3_RESULTS.md`, `NIGHT3_LOG.md`, `UX_REVIEW.md` | [history/qa-nights.md](history/qa-nights.md) |
| `REVERIFY_PROMPT.md`, `REVERIFY_RESULTS.md` | [verification/blastfoam-claims.md](verification/blastfoam-claims.md) |
| `BLASTFOAM_SOLVER_REVIEW.md` | [verification/solver-options-review.md](verification/solver-options-review.md) |
| `REFERENCE_CHAIN.md` | [verification/physics-anchors.md](verification/physics-anchors.md) |
| `HEAVY_RUNS.md` | [heavy-runs.md](heavy-runs.md) |
