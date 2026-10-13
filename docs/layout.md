# Orientation and layout (CLAUDE.md §1 and §5)

Moved out of `CLAUDE.md` on 2026-10-13 (owner, token budget); `CLAUDE.md` §1 and §5 keep
their headings, the markdown line caps and the architecture facts, and point here.

## §1 Orientation

Three solver paths, one GUI:

- **Native** (`blastlab/solvers/solver1d|2d|3d.py`) - pure NumPy finite-volume
  solvers running in the GUI's own process. Fast, byte-reproducible, used for
  previews, the regression baselines and cross-checks.
- **blastFoam** (`blastlab/solvers/foam/`) - writes a real OpenFOAM case,
  runs `blockMesh` / `setRefinedFields` / `blastFoam` inside WSL, and ingests
  the written time directories back. This is the accurate path.
- **Remap chain** - resolve the near field cheaply in 1D, hand the field off
  to 2D (ground reflection, height of burst), finish in 3D only where the
  problem is genuinely three-dimensional. `blastlab/core/profiles.py` +
  `core/chain.py`.

Dimensions: 1D spherical, 2D planar or axisymmetric, 3D Cartesian.

What the code computes: a compressible Euler solve on a grid - HLL/HLLC Riemann fluxes,
MUSCL reconstruction, adaptive mesh refinement, gauge probes, animation export, and a Qt
GUI to drive all of it. Roughly 2 MB of Python, most of it numerics, Qt widgets, OpenFOAM
dictionary generation and tests.

## §5 Layout

```
blastlab/
  core/      constants, EOS, HLL Riemann solvers, BC/obstacle fluxes, grids,
             profile save/load/remap, Case dataclasses + validation, settings,
             solver mode, chain validation, refinement bookkeeping
  solvers/   solve_1d/2d/3d(case, hooks) drivers; hooks.py decouples the
             console/GUI from the loop; worker.py is the GUI worker thread and
             its tagged-tuple queue; jobs.py is one run stage
    foam/    the blastFoam backend: env.py (WSL discovery, paths, hardware
             plan), writer.py (OpenFOAM case files), runner.py + runloop.py
             (drive the solve, live sampling, resume), reader.py (ingest),
             postmortem.py, materials.py (EOS table), export_vtk.py
  output/    gauge TSVs, matplotlib figure builders, animation export, CLI
             live view. Every FILE export goes through here.
  gui/       Tkinter app - the permanent way back (CLAUDE.md §9), not deprecated
  ui/        PySide6 app - THE GUI. Nothing here imports VTK.
  viz3d/     3D viewer: viewer.py (the only pyvista module, child process),
             process.py + protocol.py (pipe + shared-memory frame ring),
             sampling/feed/geometry (pure numpy, solver side)
  cli.py     the historical interactive prompts
  tests/     verification suites + byte-level regression harness
BlastFoam_Basic_Info/   the learning material (Hebrew): the official guide PDF
                        + blastfoam_toolkit/ (guide, JWL tables, cheatsheet,
                        scripts, templates)
docs/        00-INDEX.md (the map) · SCOPE.md (what this project is)
  verification/   physics-anchors · blastfoam-claims (the audit) ·
                  solver-options-review (the code against the guide)
  history/        qa-nights · ui-migration (and the standing Tk decision)
  heavy-runs.md   the R1-R9 catalogue + unattended-run ground rules
```

The 3D viewer runs in its own Qt process; frames reach it through a two-slot
shared-memory ring, latest-wins, so a slow viewer can never block the solve. On-screen
plots are pyqtgraph; every exported figure is still matplotlib via `output/plots.py`.
