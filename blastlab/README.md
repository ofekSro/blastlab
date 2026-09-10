# blastlab

Finite-volume blast wave solvers (pure NumPy) with cross-dimension
remapping, a prompt-based CLI and a Tkinter GUI.

- **1D spherical** — fast free-air charges, JWL or ideal-gas EOS
- **2D planar / axisymmetric** — ground reflection, walls, rectangular
  obstacles
- **3D Cartesian** — box obstacles, slice views, shock-front isosurfaces.
  Direct charge init offers two resolutions: `resolve` (refine the grid
  to 8 cells across the charge radius on blastFoam, 5 on the native
  solvers — accurate but cubic in cost, so small charges in large
  domains exceed the cell cap) and `smear` (keep
  your cell size; the charge's mass and detonation energy are deposited
  into a source ball of a few cells — coarse near-field, correct yield)
- **Interactive 3D viewer** — a live VTK window (optional, `pip install
  pyvista`): watch the blast expand around the obstacles while the
  solver runs, then scrub the timeline
- **Remap chain**: resolve the near-field cheaply in 1D, continue in 2D
  (height-of-burst + ground), finish in 3D only where the problem is
  truly three-dimensional.

## Launch

```
blastlab.bat                    # GUI (or: python -m blastlab)
python -m blastlab --cli 2d     # historical prompt workflow
python blast1d.py               # the old scripts still work (thin wrappers)
```

The GUI has four tabs: **Setup** (all parameters with live validation,
File > Open/Save case as JSON, and a live model preview - a 2D domain
drawing with boundary types, or a 3D render with domain, ground,
charge, obstacles and gauges - updating as you type; 3D cases also
choose the live-slice plane, normal + position, shown while running),
**Run** (progress, log, live pressure view with auto or fixed Min/Max
colour scale, Stop keeps partial results, plus
VIPER-style stepped execution: **Initialise Model** starts a run held
at t = 0 and **Exec 1/10/100/1000/END** + **Interrupt** advance or
pause it; a 3D case can set an end time. A **Refresh every** input
sets how often the live views redraw - in seconds or steps, blank =
automatic - and can be changed mid-run; on blastFoam "every N steps"
also sets how often the solver samples the live slice / profile, so
the picture really moves every N solver steps), **Results** (snapshot
browser, gauge histories, animation replay, exports), **Chain**
(auto-wired 1D → 2D → 3D remap workflow into a workspace folder).

## Solver mode

The solver is chosen once, for the whole app, with the **native |
blastFoam** switch in the sidebar (directly above Dark mode); a short
explainer and, in blastFoam mode, the WSL availability sit under it.
Every tab lays itself out for the chosen solver: controls that do not
apply are hidden, not greyed. In native mode that is the Material,
Detonation, Afterburn, Charge refinement and MPI rows and the Dynamic
refinement (AMR), Refinement zones, Extra charges and Detonation points
cards; in blastFoam mode the EOS and (3D) Charge resolution rows.
Switching never loses input - hidden values stay in the form and come
back when you switch back - but the case you run or save carries only
what is visible (hidden fields get that solver's defaults). Open case
adopts the case file's solver; the mode is remembered in
`settings.json`. The Chain tab presets every stage from the sidebar
mode and lets you override it per stage with the switch above the
stage form (a blastFoam 1D stage feeding native 2D/3D stages works
today; blastFoam stages fed by a profile wait for N7). In native mode
the Results tab hides the blastFoam-only **Foam runs…** browser and
**VTK** export.

## Interactive 3D viewer

3D runs get a live 3D view (VTK/OpenGL via **pyvista**, an optional
dependency) showing the blast in space: obstacles as solid boxes, the
domain outline, ground plane and the charge. It is **embedded in the
GUI**: the Run tab's right pane has "Live slice" and "3D view" tabs -
the 3D view **attaches automatically** when a 3D run starts and frames
stream live; the Results tab has a **3D** sub-tab for snapshot playback
of any finished 3D result (via its "3D Viewer" button). In `--cli 3d`
(no GUI) answering `yes` to "Interactive 3D viewer" opens the same
scene in a dedicated window instead.

Mouse on the 3D image: drag rotates, right-drag pans, wheel zooms,
double-click resets. The control column has three tabs:

| Tab | Controls |
| --- | --- |
| Display | displayed field (pressure, density, energy, peak overpressure, impulse), auto or manual Min/Max colour range, log contours, shock isosurface (+ level slider), surface loads, volume render |
| Planes | six cross-section planes: enable, axis, position, opacity % |
| View | Top/Bottom/Front/Back/Left/Right presets, parallel projection, reset |

Peak overpressure and impulse are accumulated by the solver per cell,
so the planes can paint running maxima like VIPER does. The displayed
impulse is *net* overpressure impulse - ∫(p−p₀)dt over the whole
record, negative phase included - not the positive-phase impulse used
in blast engineering (KB) tables, so it reads systematically low
against published data; it decreases once the negative phase passes.
Below the tabs:
follow-live toggle, a time slider over the retained history and
Play/Pause. The auto colour scale tracks each frame's own range (so a
decaying shock stays visible); switch it off and type Min/Max (with
optional log contours) for a fixed range.

Fields are decimated to ≤128³ float32 before display and the playback
history is memory-capped and thins itself, so the view can't stall the
run. In the GUI the scene renders off-screen in-process and is blitted
into the panel; the CLI window runs in a separate process fed over a
bounded, drop-on-full queue. Without pyvista everything else works
unchanged.

## Afterburn (blastFoam)

A pure detonation run carries only the explosive's own (anaerobic) energy,
which lands a free-air 1 kg TNT anchor ~13 % below Kingery-Bulmash. Setting
**Afterburn** to `miller` on a blastFoam case adds the energy released as the
detonation products burn with atmospheric oxygen (blastFoam's Miller model:
`dc/dt = a (1-c)^m p^n` above `pMin`, releasing `Q0 * c` J/kg), which brings
that anchor to 1.02-1.20 of Kingery-Bulmash at Z = 1-4 m/kg^(1/3). TNT's
parameters are calibrated on that anchor; the other materials scale by oxygen
balance and are estimates - calibrate before quoting them. Default is `none`,
so existing cases and baselines are unchanged.

Near-field blastFoam arrival times depend on the **activation model**: the
native solvers detonate the whole charge at t = 0 while blastFoam's default
`linear` model burns it at the detonation velocity, so a gauge one or two
charge radii out sees the shock later. Measured on a 8 kg axisymmetric case,
foam arrival runs +37 % / +24 % over native at r = 0.6 / 1.0 m with `linear`
and +23 % / +13 % with `none` - about half the near-field lag is the
activation model, the rest is the resolved-charge expansion itself. The gap
closes with distance (a few per cent by r = 3-4 m), and `linear` stays the
default because `none` overshoots the peaks (1.36-1.43x native here).

## Local mesh refinement (blastFoam)

Two kinds of refinement exist. **Static** refinement (this section) builds
the mesh before the run (topoSet + refineMesh per level) and never changes
it. **Dynamic** refinement (next section) lets blastFoam's `adaptiveFvMesh`
follow the shock during the run; the two are mutually exclusive on a case.

The blastFoam backend can refine the mesh locally instead of shrinking the
whole grid. A case has a **base cell size** plus **refinement zones**: axis-
aligned boxes `(x0, x1, y0, y1[, z0, z1], level)` where level *l* halves the
cell *l* times (level 1 = dx/2, level 2 = dx/4, up to level 4). Zones may
nest; each level-*l* zone must sit at least one level-(*l*-1) cell inside a
level-(*l*-1) zone (2:1 grading - validation refuses jumps of two levels),
and zone edges snap outward onto the faces of level *l*-1. **Charge
refinement** `'global'` keeps today's rule (the whole grid is refined to
resolve the charge); `'zone'` keeps the base cell and adds automatic nested
zones around each charge. The native solvers stay uniform - zones on a
native case are a validation error.

Results are resampled onto the **finest uniform grid** (dx / 2^lmax), so
every plot, export, animation and 3D view works unchanged; coarse cells
appear as constant blocks. The **Show mesh** checkbox (setup preview, live
run plot, Results field/replay plots, 3D viewer Display tab) draws the true
cell edges. In 3D the overlay covers the WHOLE domain - the grid on the six
boundary faces plus one grid per visible cut plane - and full-span grid lines
are thinned (refinement boundaries are always kept) so a fine mesh reads as a
grid instead of a solid white sheet. Validation reports the predicted mesh cell count and the size
of the display grid (which is what costs memory - keep lmax at 3-4).

Limits: axisymmetric zones touching the symmetry axis are level 1 only (the
wedge axis cells are prisms); refinement needs `topoSet`, `refineMesh` and
`postProcess` in the WSL install. The run keeps `0/C` (cell centres) so a
refined run can be reloaded post-mortem. E2E drivers:
`tests/_e2e_foam_refine2d.py`, `tests/_e2e_foam_refine3d.py`.

## Dynamic mesh refinement (blastFoam AMR)

With **AMR levels** > 0 (the "Dynamic refinement (AMR)" card, shown in
blastFoam mode)
the case writer emits an `adaptiveFvMesh` dictionary and blastFoam refines
the mesh around the shock as it moves and unrefines behind it. The base cell
is the case cell size untouched; the charge is refined at t = 0 by
`setRefinedFields` (the finest level must resolve it - validation says which
level a charge needs). Coefficients: the **error estimator**
(`densityGradient`, the blastFoam tutorial default, or `Lohner` on p),
**refine above / unrefine below** thresholds (defaults 0.4 / 0.2, measured
on the 2D e2e: ~1.2x faster than the uniform grid at ~3.6 % gauge error,
where the tutorials' 0.1 / 0.1 refines nearly everything), **refine every**
N steps, **buffer layers**, **max cells** and the **display level**.

Because the cell count and order change at every write, each written time
carries its own cell centres (`C`, a `writeCellCentres` function object)
and refinement levels (`cellLevel`, `dumpLevel`); the reader rebuilds the
mapping onto the **display grid** per time (`core/refine.remap_from_centres`).
The display grid sits at the **display level** (auto = the deepest level
whose grid fits the memory cap): cells finer than it are box-averaged, so a
3D case may run 3-4 levels while displaying at level 1-2. The live slice
samples every few solver steps as on a static mesh (each sampled cell's
centre pins its refinement level, so the rows tile the display grid the
same way a written time does), the log reports the cell
count and per-level histogram at every write, and **Show mesh** follows the
frame in the live plot, the Results replay, the animation export and the 3D
viewer. AMR runs are serial in this version (blastFoam's `reconstructPar`
cannot follow a changing mesh; the measured parallel options are in DONE.md (reference entry
N16). E2E drivers: `tests/_e2e_foam_amr2d.py` (`--sweep=0.2:0.1,...` adds
a threshold table), `tests/_e2e_foam_amr3d.py`.

## Layout

```
blastlab/
  core/      constants, EOS, HLL Riemann solvers, BC/obstacle fluxes,
             grids, profile save/load/remap, Case dataclasses + validation
  solvers/   solve_1d/2d/3d(case, hooks) time-integration drivers;
             hooks decouple console/GUI from the loop
  output/    gauge TSV writers, OO figure builders, animation export,
             CLI live view
  legacy/    backwards-compatible blast1d/2d/3d module APIs
  gui/       Tkinter app (worker thread + queue, embedded matplotlib,
             off-screen VTK hosts: run-time 3D view + setup preview)
  viz3d/     interactive 3D viewer (child process; only viewer.py and
             the gui VTK hosts import pyvista)
  cli.py     the historical interactive prompts
  tests/     verification suites + byte-level regression harness
```

## Tests

```
cd blastlab/tests
python test_regression.py    # reruns baseline cases, byte-compares outputs
python test_hardware.py      # hardware model: identity, staleness, memory caps
python test_blast2d.py       # 2D physics suite (19 checks)
python test_blast3d.py       # 3D physics suite (T1-T10)
python test_viz3d_sampling.py  # viewer decimation/face-load unit tests
python test_viz3d_hooks.py     # solver->viewer payloads, physics unchanged
python test_viz3d_scene.py     # off-screen scene render (needs pyvista)
python test_viz3d_panel.py     # embedded Tk 3D panel (needs pyvista)
python test_viz3d_e2e.py       # CLI viewer process (a window opens)
```

The physics is validated against 1D spherical references and across the
remap chains (see the test files for tolerances); the regression harness
pins gauge TSVs and profiles byte-for-byte.
