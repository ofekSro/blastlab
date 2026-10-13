# Physics notes that change how you read the code (CLAUDE.md §7)

Moved out of `CLAUDE.md` on 2026-10-13 (owner, token budget); `CLAUDE.md` §7 keeps its
heading and a pointer here. Read before any task in `solvers/`, `core/`, `output/` or
the gauge / impulse / arrival display. Cited as "CLAUDE.md §7" - that keeps resolving.

- **Afterburn.** A pure JWL detonation carries only the explosive's own
  anaerobic energy, which lands a free-air 1 kg TNT anchor ~13 % below
  Kingery-Bulmash. `afterburn = miller` adds the energy from products burning
  with atmospheric oxygen and brings the anchor to 1.02-1.20 KB at Z = 1-4.
  **Only the TNT row is calibrated against data**; the others scale by oxygen
  balance and are ordered estimates. Refit only after a change to what the
  charge deposits or to `FOAM_EXP_CELLS`, never before, or it gets calibrated
  twice. See the long comment in `solvers/foam/materials.py`.
- **Activation model.** The native solvers detonate the whole charge at t = 0;
  blastFoam's default `linear` burns it at the detonation velocity, so
  near-field arrival times differ by tens of per cent at 1-2 charge radii and
  converge by a few metres. Expected, not a bug.
- **Pressure is coloured logarithmically by default** in the 3D viewer: a
  blast spans four decades in one frame, and on a linear bar the whole shocked
  field collapses into the bottom fraction of a per cent.
- **Displayed impulse is net overpressure impulse** over the whole record,
  negative phase included - not the positive-phase impulse of KB tables, so it
  reads systematically low against published data. Intentional, documented.
- **AMR runs are serial** in this version: `reconstructPar` cannot follow a
  changing mesh. `Lohner` is the default error estimator (`densityGradient`
  starved the axis).
- **Memory models.** `core/constants.py` carries a measured ~2700 B/cell for
  blastFoam inside WSL and an analytic per-cell model for the native solvers,
  because a native run that does not fit raises `MemoryError` and takes the
  window with it. `core/hardware.py` turns them into cell caps.
