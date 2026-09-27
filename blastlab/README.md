> **Academic CFD — blast-wave gas dynamics, Technion.** This project computes a
> pressure field in air and the structural load it produces, for blast-resistant
> design and explosive-safety siting (UFC 3-340-02, Kingery-Bulmash).
> Energetic materials enter only as a published equation of state. Scope: [../docs/SCOPE.md](../docs/SCOPE.md)

# blastlab

Finite-volume blast wave solvers (pure NumPy) with cross-dimension
remapping, a prompt-based CLI and a desktop GUI.

> **The GUI is the PySide6 one** (`blastlab/ui/`) as of 2026-09-17:
> `python -m blastlab` opens it, and all four tabs - Setup, Run, Results
> and Chain - are real, along with the run browser and the embedded 3D
> viewer. `--qt` is still accepted and does nothing. See "The PySide6
> front-end" below.
>
> The Tkinter original (`blastlab/gui/`) stays behind `python -m
> blastlab --tk` **indefinitely, by owner decision (2026-09-18)** - Qt
> is the main GUI and Tk is the way back if it is ever needed. There is
> no removal date, and `blastlab/gui/` + `customtkinter` are not to be
> deleted without the owner asking for it.

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
blastlab_qt.bat                 # the GUI, double-clickable from anywhere
blastlab.bat                    # the same thing (or: python -m blastlab)
python -m blastlab --case a.json   # open a case at startup
python -m blastlab --tk         # the Tkinter GUI, kept as the way back
python -m blastlab --cli 2d --runs-dir D:\runs --model M   # prompt workflow
python -m blastlab --hd13 m.json --runs-dir D:\runs --model M  # HD 1.3
python blast1d.py               # the old scripts still work (thin wrappers)
```

`blastlab_qt.bat` runs from its own folder, so it works wherever it is
launched from, and it says which of Python / the package / PySide6 is
missing instead of showing a traceback. It forwards its arguments, so
`blastlab_qt.bat --case a.json` works too.

Dependencies are listed in `requirements.txt` (`pip install -r
requirements.txt`); `pyvista` + `pyvistaqt` are optional and only the
3D viewer needs them.

The GUI has four tabs: **Setup** (all parameters with live validation,
File > Open/Save case as JSON, and a live model preview - a 2D domain
drawing with boundary types, or a 3D render with domain, ground,
charge, obstacles and gauges - updating as you type; 3D cases also
choose the live-slice plane, normal + position, shown while running),
**Run** (progress, log, live pressure view with auto or fixed Min/Max
colour scale, **live gauge traces** - overpressure against time at each
gauge, drawn while the run is going rather than only after it - Stop
keeps partial results, plus
VIPER-style stepped execution: **Initialise Model** starts a run held
at t = 0 and **Exec 1/10/100/1000/END** + **Interrupt** advance or
pause it; a 3D case can set an end time. A **Refresh every** input
sets how often the live views redraw - in seconds or steps, blank =
automatic - and can be changed mid-run; on blastFoam "every N steps"
also sets how often the solver samples the live slice / profile, so
the picture really moves every N solver steps), **Results** (snapshot
browser, gauge histories, animation replay with a **0.25x - 4x speed**,
exports), **Chain**
(auto-wired 1D → 2D → 3D remap workflow into the Run tab's model folder).

## Where a run's files go

`OUT-1`, [model-folder-and-vtk-plan.md](../docs/model-folder-and-vtk-plan.md)
§2. No run starts without a **Runs folder** and a **Model** name (the two
boxes on the Run tab, both GUIs; the Runs folder is remembered). Run,
Initialise Model, a resume, the Chain tab and the HD 1.3 tab all refuse,
with one message naming the box, when the folder is empty or missing or
the name is not a valid Windows folder name (at most 100 characters).
Everything the run produces goes into `<Runs folder>\<Model>\`:

| Path | Content |
|---|---|
| `MODEL.json` | the case exactly as run (paths relative to the folder) |
| `run.log` | the solver-side log of the run |
| `manifest.json` | model, times, solver, dim, git commit, stop reason, cells, ranks, steps, the WSL scratch, `outputs`, `missing` (with why), `failed` |
| `gauges\gauges_<d>d.txt`, `gauges\gauges_<d>d_summary.csv` | gauge TSV and per-gauge peak / arrival / impulse |
| `figures\*.png`, `fields\*.csv`, `report.html` | the Results-tab exports |
| `animation.mp4` / `.gif` | only when replay frames were recorded; the format is the Setup tab's choice |
| `profile.txt` / `profile_2d.npz` | 1D / axisymmetric 2D profile; `trigger_remap.npz` for a remap trigger |
| `foam\` (blastFoam) | `system`, `constant`, `0`, `postProcessing`, `log.*` and `SHA256SUMS` |

The Setup tab's output file-name boxes are gone (the names above are
fixed); the `.gif` / `.mp4` choice stays as **Animation format**.

- **An existing model** is overwritten only after a Yes/No question, and
  only if blastlab created it (it holds a `.blastlab-model` marker) or it
  is empty; any other folder is refused. A file open elsewhere (ParaView)
  refuses with the OS error.
- **The WSL scratch.** blastFoam still solves in
  `/root/blastlab_runs/<stamp>_<d>d_p<pid>-NN`. After a run that finished,
  every row above is checked and `foam\` is verified against hashes taken
  inside WSL; only then is the scratch deleted. A failed, stopped or
  partly copied run keeps it (`manifest.json` says why), and the run
  browser, `--load-foam-run` and the VTK button work on it as before.
- **A run that never ends** (the window closed mid-run) still leaves
  `MODEL.json` and a `manifest.json` whose `stop_reason` begins
  `unfinished:` - both are written when the run starts and replaced when
  it ends.
- **Chain**: `<MODEL>\1d\`, `2d\`, `3d\`, one folder per stage as above,
  with `handoff_1d_to_2d.txt` and `handoff_2d_to_3d.npz` at the model root
  and a root `manifest.json` listing the stages and hand-offs. There is no
  workspace box any more.
- **HD 1.3**: `<MODEL>\MODEL.json`, `hd13_report.html`, `hd13_loads\` (the
  SBEDS CSVs) and `manifest.json`; `--hd13-wall-export` writes
  `<MODEL>\wall_loads\`.
- **Command line**: `--cli`, `--hd13` and `--hd13-wall-export` need
  `--runs-dir DIR --model NAME` (without them: exit 2 and the usage);
  an existing model is asked about with y/N. The native `--cli` runs the
  historical prompts with the model folder as working directory, and its
  manifest lists the rows that flow does not write. `--hd13-new`,
  `--load-foam-run` and `--clean-foam-runs` take neither.
- The Results-tab export buttons still work as before, and their file
  dialogs open in the result's model folder.

### VTK files for ParaView (`vtk\`)

`OUT-2`, [model-folder-and-vtk-plan.md](../docs/model-folder-and-vtk-plan.md)
§3. blastFoam only: the Setup card **VTK output (ParaView)** is hidden in
native mode, and a native run ignores the keys.

- **The card** (both GUIs), laid out as Viper's "VTKs and Framerates":
  1D *Whole domain*; 2D *Whole domain* and *Obstacles*; 3D *Sections and
  obstacles* and *Volumes*. Each family has a box, a **Time / Step**
  pair and one interval per mode (the other is greyed): **Time is
  simulated seconds** (`Every [s]`, default 0.001; the case JSON stores
  seconds too, like every other time in the case, and the card says that
  the files and ParaView show time in seconds - owner decision P22),
  Step is solver steps. 3D adds extra section planes (axis, position
  [m]); the live-slice plane is also written whenever *Sections and
  obstacles* is ticked, and a plane is snapped
  to the nearest cell layer but keeps the name typed (`slice_x_0.20`).
  The quantity matrix has a locked Gauge column (p, rho, U) and one
  column per destination - Sect. / Obst. / Vol. (1D/2D: Domain). The
  first tick of a family fills p + peak pressure (surfaces) or p,
  rho, U (volumes). **`pMax` (Peak pressure) is the running per-cell
  maximum of the absolute pressure `p`**, not an overpressure -
  subtract ambient (101.325 kPa) for the peak overpressure. Case keys: `vtk_surfaces` {on, mode, value, fields,
  obstacle_fields, planes}, `vtk_volumes` {on, mode, value, fields}. A
  family that is off is written only when it still has a field ticked,
  as `on: false` with its ticks, so a reload restores the card; the
  solver ignores it (owner decision P15).
- **Cadence.** Sections and obstacles are blastFoam surface function
  objects (vtkTimeSeries, blastFoam User Guide v6.0, sec. 15.5 (p. 124))
  that sample at their own cadence and never change the time step.
  Volumes **are** the solver's write schedule (Time: every `value` s of
  simulated time; Step: every N steps), so they cannot be combined
  with a write budget, and every write is also ingested for the live
  view. A Time-mode volumes write is `writeControl runTime`: it lands on
  **the first solver step past each interval**, and the time step is
  never shortened to hit the interval exactly (owner decision P14 (b),
  2026-09-27 - the earlier `adjustableRunTime` did shorten it, and
  moved a near-field gauge by a few per cent). The written time names
  are therefore not round multiples. The one exact write is the end
  time (T62), as on every run. Validation notes the write count, and
  in Step mode that the count depends on the step count.
- **Layout** - `<time>` is OpenFOAM's own time name in seconds:

  | Path | Content |
  |---|---|
  | `vtk\manifest.json` | fields, cadence, per family count / times / series, `not_converted` (with why), `deleted_in_wsl`, `replay_incomplete` |
  | `vtk\volumes\t_<time>.vtk`, `volumes.vtk.series` | one file per write, every chosen field, cell data only |
  | `vtk\sections\<plane>\<field>\t_<time>.vtk`, `sections\<plane>\<field>.vtk.series` | one series per plane and field |
  | `vtk\obstacles\<field>\t_<time>.vtk`, `obstacles\<field>.vtk.series` | the obstacle walls, one series per field |

  The model's `manifest.json` carries `vtk: {dir, counts, not_converted}`.
- **What is deleted in WSL, and when.** After every ingest pass one
  `foamToVTK` at a time converts the writes already read, the file is
  copied into `vtk\` and size-checked, the index is rewritten, and only
  then are the time directory and the converted file deleted in WSL.
  Never deleted: `0`, a resume's start time, the two newest writes, and
  every write the run's own finalize reads again (the snapshots, the
  2D arrival pin, the 2D remap trigger). **A 1D run deletes no written
  time at all** (owner decision P9): it converts and copies every write,
  removes only the converted file, and its time directories stay in WSL
  until the scratch is released - 1D picks its snapshots from the writes
  on disk, and 1D writes are small. Surface samples are copied
  and removed the same way, the newest one after the run. A conversion
  or copy that fails twice is listed in `not_converted`, its write stays
  in WSL, and the scratch is not released. A run without a model folder
  exports and deletes nothing.
- **Limits.** A parallel AMR run cannot export volumes (its writes stay
  per rank; `reconstructPar` cannot follow a changing mesh) - validation
  says so before the run; sections and obstacles work there. A resume
  after deletion replays only the writes left (`replay_incomplete`).
- **In ParaView:** *File > Open* a `.vtk.series` file - `volumes\
  volumes.vtk.series`, or several of `obstacles\` / `sections\<plane>\`
  at once to get one pipeline item per field - and the time bar follows
  the series times (a JSON list of relative file names and times, the
  format blastFoam's own `createTimeSeries` writes, User Guide sec. 16.3).
- **Results tab.** For a run that wrote `vtk\` and released its WSL
  scratch, the **VTK** button opens `<MODEL>\vtk\` (its tooltip gives the
  path and the file count) instead of converting; while the case
  directory still exists it runs the full `foamToVTK` as before.

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
GUI**: the Run tab's right pane has "Live slice", "Gauges" and
"3D view" tabs - the 3D view **attaches automatically** when a 3D run
starts and frames stream live; the Results tab has a **3D** sub-tab for
snapshot playback
of any finished 3D result (via its "3D Viewer" button). In `--cli 3d`
(no GUI) answering `yes` to "Interactive 3D viewer" opens the same
scene in a dedicated window instead.

Mouse on the 3D image: drag rotates, right-drag pans, wheel zooms,
double-click resets. The control column has three tabs:

| Tab | Controls |
| --- | --- |
| Display | displayed field (pressure, density, energy, peak overpressure, impulse), auto or manual Min/Max colour range, log colour scale, shock isosurface (+ level slider), surface loads, volume render |
| Planes | six cross-section planes: enable, axis, position, opacity % |
| View | Top/Bottom/Front/Back/Left/Right presets, parallel projection, reset |

**Pressure is coloured logarithmically by default.** A blast spans four
decades or more in one frame - the products sit at megapascals while the
air around them is at tens of kilopascals - so on a linear bar the whole
shocked field, which is what you are watching, collapses into the bottom
fraction of a per cent and the view looks frozen. The other fields have
no such range and stay linear; the Display tab's tick overrides either
way, for the rest of the session.

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
run. In the Tk GUI the scene renders off-screen in-process and is
blitted into the panel; the CLI and the PySide6 GUI both drive a
separate viewer process (below). Without pyvista everything else works
unchanged.

## The PySide6 front-end

`blastlab/ui/` is the GUI (`python -m blastlab`). It keeps the Tk layout
- sidebar, cards, dark/light, Ctrl+O / Ctrl+S / F5 / Esc - and everything
below the GUI is shared code, so both front-ends run the same solvers,
hooks and exports.

What is different under the hood:

- **On-screen plots are pyqtgraph**, drawn on the GPU. `output/plots.py`
  (matplotlib) is untouched and still builds every exported figure.
- **3D runs in its own process.** `viz3d/process.py` spawns a small Qt
  application that hosts the pyvista scenes; the GUI process never
  imports VTK (pinned by `test_ui_no_vtk_in_main.py`). Frames reach it
  through a two-slot shared-memory ring (`viz3d/protocol.py`) the solver
  thread writes into: latest wins, so a slow viewer can never block the
  run. Controls and status go over a pipe. Its render window is embedded
  in the Run tab with `QWindow.fromWinId`, **Detach** pops it out onto a
  second screen, and if embedding fails the window simply floats.
- **The viewer child is started only for a 3D case**, so a 2D-only
  session never pays for a VTK process.
- The solver still runs on one worker thread talking to the GUI through
  the tagged-tuple queue of `solvers/worker.py`, drained by a QTimer.
- **The Results tab keeps one live panel** instead of rebuilding a
  matplotlib figure per click: changing snapshot or field is a single
  array upload. `PNGs` and `Report` still write the full multi-panel
  grid, so the screen and the file differ on purpose and the button
  tooltips say so.
- **No `matplotlib.pyplot` in the GUI process** (pinned by
  `test_ui_no_mpl_pyplot.py`), because its global figure manager fights
  the event loop.

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
             grids, profile save/load/remap, Case dataclasses +
             validation, app settings, solver mode, chain validation
  solvers/   solve_1d/2d/3d(case, hooks) time-integration drivers;
             hooks decouple console/GUI from the loop; worker.py is the
             GUI worker thread + its message queue, jobs.py one run
             stage with the output files it writes
  output/    gauge TSV writers, OO figure builders, animation export,
             CLI live view (matplotlib: every FILE export)
  legacy/    backwards-compatible blast1d/2d/3d module APIs
  gui/       Tkinter app (embedded matplotlib, off-screen VTK hosts:
             run-time 3D view + setup preview) - being replaced by ui/
  ui/        PySide6 app (pyqtgraph plots, viewer process host); nothing
             here imports VTK
  viz3d/     interactive 3D viewer: viewer.py (the only pyvista module,
             runs in the child process), process.py + protocol.py (the
             pipe and the shared-memory frame ring), sampling/feed/
             geometry (pure numpy, solver side)
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
python test_viz3d_protocol.py  # shared-memory frame ring (no VTK needed)
python test_viz3d_hooks.py     # solver->viewer payloads, physics unchanged
python test_viz3d_scene.py     # off-screen scene render (needs pyvista)
python test_viz3d_panel.py     # embedded Tk 3D panel (needs pyvista)
python test_viz3d_e2e.py       # viewer process (a window opens)
```

The PySide6 front-end has its own suites, which create their
`QApplication` on the offscreen platform themselves:

```
python test_ui_drain.py           # run controller: queue drain, refresh, errors
python test_ui_run_panel.py       # Run tab + the pyqtgraph live pane
python test_ui_view3d_host.py     # 3D host controls -> viewer messages
python test_ui_no_vtk_in_main.py  # the GUI process stays VTK-free
python _e2e_ui_native_warn.py     # real native 2D run through the window
python _e2e_ui_view3d.py          # real 3D run + embedded viewer (a window opens)
```

The physics is validated against 1D spherical references and across the
remap chains (see the test files for tolerances); the regression harness
pins gauge TSVs and profiles byte-for-byte.
