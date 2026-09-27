# OUT-2 follow-up · VTK file layout like Viper (owner, 2026-09-27)

Owner decisions after the owner's own ParaView check of the QA run. Binding. They
replace P2 and change Q1 of `2026-09-27-out-2-vtk-output.md` §6 for sections and
obstacles.

## The reference

The owner supplied two Viper::Blast output files,
`docs/references/viper_vtk_sample/section_example.vtk` and `obs_example.vtk` (large;
not to be committed to git). Their structure (keyword lines read 2026-09-27):

| File | Dataset | Content |
|---|---|---|
| `section_example.vtk` | legacy VTK 3.0, `BINARY`, `DATASET STRUCTURED_POINTS`, `DIMENSIONS 668 1 668`, `ORIGIN`, `SPACING` | `FIELD FieldData 1` / `TIME 1 1 float`; `CELL_DATA 444889`; `SCALARS pressure`, `SCALARS Peak_Ovepressure`, `SCALARS Peak_Impulse` (float, 1 component each) |
| `obs_example.vtk` | legacy VTK 3.0, `BINARY`, `DATASET UNSTRUCTURED_GRID`, `POINTS 525800 float`, `CELLS 520000`, `CELL_TYPES` | same `TIME` field; `CELL_DATA 520000`; the same three scalars |

So Viper writes **one file per surface per sample time, holding every chosen quantity
as a cell-data array on that surface, with the sample time inside the file**.

## Decisions

1. **One file per surface per sample time, with all chosen fields.** Each section plane
   (`x = 0`, `y = 2`, the live slice, ...) and the obstacles each get their own series;
   every file of a series holds every quantity the user ticked for that destination, as
   cell data on one geometry. No per-field files. Volumes already work this way (one
   `foamToVTK` file per time, all fields) and stay as they are (P1).
2. **Folder layout:** one folder per series with its `.vtk.series` beside it:
   `vtk\volumes\` + `vtk\volumes.vtk.series`,
   `vtk\slice_x_0.20\` + `vtk\slice_x_0.20.vtk.series`,
   `vtk\obstacles\` + `vtk\obstacles.vtk.series`. All series files at one level.
3. **Opening in ParaView:** each series separately (no master file).
4. **Peak pressure is written as peak OVERPRESSURE**, like Viper: `pMax - p_ambient`
   of the case, computed when the files are assembled on Windows. (The card row and
   tooltip must then say peak overpressure again - the F1 rename to "Peak pressure"
   described the raw blastFoam field; the exported quantity is now the overpressure.)
   Owner addendum 2026-09-27: blastFoam's pMax starts at 0, so the running max includes
   the current pressure - `max(pMax, p) - p_ambient` when `p` is in the same file, else
   `max(pMax - p_ambient, 0)`; gauges unchanged.
5. **Readable field names in the files, the same in every family**, like Viper:
   `pressure`, `Peak_Overpressure`, `Impulse`, `Overpressure`, `Arrival_Time`,
   `density`, `velocity`, `temperature`, `Products_Fraction`, `Energy`
   (spelling "Overpressure", not Viper's "Ovepressure" typo). Volumes get the same
   names (rename arrays when copying the `foamToVTK` output).
6. **The sample time is written inside every file** (`FIELD FieldData 1` /
   `TIME 1 1 float`), as Viper does, in seconds; the `.vtk.series` stays for animation.

## Implementation notes (for the planner / implementer)

- blastFoam's `vtkTimeSeries` surface writer emits one file per field per surface
  (`postProcessing/<fo>/<t>/<field>_<surface>.vtk`). The merge happens on Windows,
  after the sweep: read the per-field files of one surface and one time, check they
  share one geometry (same points/cells), write one legacy binary VTK with every field
  as `CELL_DATA` (or `POINT_DATA` if that is what blastFoam writes - keep what the
  source holds, do not interpolate), add the `TIME` field, rename per decision 5.
  Only then may the per-field sources be deleted (same verify-then-delete order as
  the rest of the export).
- Peak overpressure needs the case's ambient pressure; use the same value the gauges
  use for overpressure.
- Pure Python/NumPy, no VTK import in the GUI process (`test_ui_no_vtk_in_main`).
- Tests: a round-trip on synthetic per-field files; a check that ParaView's reader
  (or a strict legacy-VTK parser) accepts the merged file; the real run re-done and
  the owner re-checks in ParaView.
