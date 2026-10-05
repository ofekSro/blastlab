# Tidy proposal: blastlab/solvers/foam/vtk_export.py
tier: B · base commit: 9ced617 · date: 2026-10-05

1. [duplication] L965-968 (`VtkExport.__init__`) and L1063-1066 (`VtkExport.state`) - the same "active families" list (`[VOLUMES] if volumes_on else []` + sections/obstacles comprehension). Extract one private method `_families()` returning that list; both sites call it. - APPLIED
   Output risk: none (same list, same order).
2. [duplication] L966-967, L1049-1050, L1064-1065 - the pair `((VTK_SECTIONS, SECTIONS), (VTK_OBSTACLES, OBSTACLES))` is written three times. Name it `_SURFACE_FAMILIES` beside KINDS, with a one-line comment (function-object name -> vtk\ family). - APPLIED
   Output risk: none.
3. [long-func] L435-534 `decimate()` - 100 lines; the CELLS-walk plus centroid block (L469-499) moves verbatim to a private `_cell_centroids(pts, conn, ctype, n)` returning `(cen, starts, sizes, is_id)`. `decimate` keeps validation, keep-mask and re-indexing. Statements are moved, not changed. - APPLIED
   Output risk: none (same NumPy ops, same order).
4. [docstring] Missing one-liners on `_time_key` L62, `_safe` L246, `_size` L740, `_remove` L754, `_cadence` L771, `VtkExport.unprotect` L998, `_dest` L1016, `_once` L1019, `_add_file` L1111, `_fail` L1122, `_src_volume` L1212, `_todo` L1216, `_start` L1234, `_finished` L1241, `_run` L1182, `Conversion.kill` L650. Each says purpose and return, e.g. `_size` -> bytes, -1 when absent; `_fail` -> retried once then `not_converted` (plan sec. 3.5). - APPLIED
   Output risk: none.
5. [unused-local] L1035 `for entry, t in vtk_series.read_series(path)` - `t` is never used in the loop body (the time comes from the file name `m.group(1)`). Rename to `_t`. - APPLIED
   Output risk: none.
6. [unused-local] L1045 `for rel, (kind, t) in self.files.items()` - `rel` unused. Iterate `self.files.values()` as `(kind, t)`. - APPLIED
   Output risk: none (same order, dict values).
7. [magic-number] L605 `timeout=300` (delete_wsl), L653 `timeout=10` (Conversion.kill), L625 `maxlen=40` (tail lines), L648 `[-3:]` (lines shown in the failure detail). Add named constants in the executor-constants block L573-588 (`DELETE_TIMEOUT_S = 300`, `KILL_WAIT_S = 10`, `TAIL_LINES = 40`, `DETAIL_LINES = 3`), each with a one-line "why" comment, values unchanged. - APPLIED
   Output risk: none.
8. [guard-clause] L429-432 `decimation_of` - the line-continued 4-way `or` can be split into two early returns (`bool`/type check, then value check). Same results for every input. - APPLIED
   Output risk: none.
9. [guard-clause] L1010-1013 `covered`, L995-996 `protect`, L771-773 `_cadence`: already flat, left as is. Instead, in `deleted_note` L728-735 the `if vtk_dir: ... else:` after the early `note` return is flattened into a local `found` computed via a small helper `_manifest_found(vtk_dir, posix, runs_dir)`. Inside the existing `try/except Exception` that stays untouched. - APPLIED
   Output risk: none.
10. [comment] L1038-1044 `_resume_state` - add a comment saying `_T_FILE` keeps only `t_<time>.vtk` entries, so a series entry with a different file name is skipped silently (mirrors `dest_name`). Documents why the `continue` exists. - APPLIED
   Output risk: none.

Not touching: the 4 `except ... pass` blocks (L637, L654, L696, L757) and the `except Exception` at L736 / L1179 - they are teardown or "never raises" guards, documented by their comments; `__init__` (119 lines) is mostly attribute and log setup in a documented order that the tests pin - only item 1 touches it. The `backend.py:line` numbers in the class docstring table are marked "as of Step 7" and left alone.
Engineering questions: none
