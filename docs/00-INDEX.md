> **Academic CFD — blast-wave gas dynamics, Technion.** This project computes a
> pressure field in air and the structural load it produces, for blast-resistant
> design and explosive-safety siting (UFC 3-340-02, Kingery-Bulmash).
> Energetic materials enter only as a published equation of state. Scope: [SCOPE.md](SCOPE.md)

# Documentation index

Every file here is capped at 1000 lines. The working documentation is English;
the original Hebrew notes are preserved under [`archive/`](archive/).

## Start here

| File | What is in it |
|---|---|
| [../README.md](../README.md) | What this project is, what it computes, how to run it |
| [SCOPE.md](SCOPE.md) | The full statement of scope, the standards it is written against, and the glossary |
| [../CLAUDE.md](../CLAUDE.md) | Working context: environment, conventions, traps, invariants |

## Work management

| File | What is in it |
|---|---|
| [../TODO.md](../TODO.md) | **Open work only**, ordered HD1 → P0 → P4, plus the standing rules and the test matrix |
| [../DONE.md](../DONE.md) | The completed record, the timeline, and **the identifier index that code comments cite** |

## Verification — what has been checked, and how

| File | What is in it |
|---|---|
| [verification/physics-anchors.md](verification/physics-anchors.md) | The Kingery-Bulmash anchor, every measured number, the reference chain, and the measurement discipline |
| [verification/blastfoam-claims.md](verification/blastfoam-claims.md) | The independent adversarial audit of the five defects attributed to blastFoam — verdicts, pre-registered rules, and the runs that settle what is left |
| [verification/solver-options-review.md](verification/solver-options-review.md) | Every dictionary the code generates, against the official guide and the vendor source. Also the catalogue of guide features not yet used |

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
| [../BlastFoam_Basic_Info/](../BlastFoam_Basic_Info/) | Learning material — a blastFoam guide, JWL parameter tables, a cheatsheet (Hebrew) |

## Archive

[`archive/`](archive/) holds the 15 original work-management files exactly as they
were before the 2026-09-21 consolidation, untranslated. They are kept so that
nothing exists only in git history. Once the consolidated files have been read and
accepted, the archive can be removed in a single commit — git keeps it either way.

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
