# Tidy proposal: blastlab/solvers/foam/backend.py
tier: B · base commit: 9ced617 · date: 2026-10-05

1. [duplication] L176-180 `build_remap` / L254-258 `_build_remap_amr` - identical Cx/Cy/Cz `os.remove` loop with `except OSError: pass`. Extract private `_drop_centre_components(directory)`, keep the try/except and the "C itself stays for post-mortem" comment inside it. - APPLIED
   Output risk: none.
2. [duplication] L407-411 / L459-462 `_decode_surface` - same `np.clip(np.floor(pts[:, ax] / dxf).astype(int), 0, shape-1)` pair twice. Extract `_cell_index_uv(pts, ax_u, ax_v, dxf, shape)` returning (iu, iv); dxf is computed at each call site exactly as now. - APPLIED
   Output risk: none.
3. [duplication] L1401-1404 `solve_2d_foam` / L2031-2034 `solve_3d_foam` - identical 4-term `spec.adaptive_write = (...)` expression. One helper `_resolve_adaptive_write(case, spec, adaptive_write)` for 2D/3D only (1D lacks the `write_budget` term and stays inline), same short-circuit order. - APPLIED
   Output risk: none.
4. [magic-number] L1918, L2180, L2321 `_initial_frame3d` / `on_frame` / `finalize_3d` - `0.4` (= gamma_air - 1) and the `1e-10` density floor appear inline; the two `p / (0.4 * np.maximum(rho, 1e-10))` sites are the same expression. Name `_AIR_GAMMA_M1 = 0.4` and `_RHO_FLOOR = 1e-10` (comment: ideal-gas e = p/((gamma-1) rho), live-viewer stand-in, P2-2) and add `_e_approx(p, rho)` for the two identical sites; L1918 only takes the constant. Same values, same operation order. - APPLIED
   Output risk: none.
5. [docstring] L266 `_preflight`, L660 `_log_banner_1d`, L1342 `_log_banner_2d`, L1977 `_log_banner_3d`, L925 `_n_procs_on_disk` - no docstring. Add one-liners (what is returned or logged, units where relevant). - APPLIED
   Output risk: none.
6. [docstring] L1-17 module docstring - "phased bring-up" and `IMPLEMENTED` "(grows per phase)" (L40) are stale: all of dims 1-3 are implemented. Reword those two phrases only; the rest stays. - APPLIED
   Output risk: none.
7. [imports] L35-38 - `from .runloop import ...` appears twice (L35 and L37) and `from ..hooks import frame_budget` (L38) repeats the L29 hooks import. Merge into one import per module; all names stay importable from here. - APPLIED
   Output risk: none.
8. [naming] L1302 `_refine_lines` - loop variable `l` (ambiguous glyph) -> `lev`. L1686, L2084, L2353 - comprehension variable `g` shadows the grid dict `g = spec.grid` of the same function -> `gpt`. - APPLIED
   Output risk: none.
9. [comment] L574-576 - orphan comment about how the 2D pin bounds its cost sits above `_track_pin` and describes `arrived_2d` (finalize_2d, L1701). Move it, unchanged, to just above `arrived_2d`. - APPLIED
   Output risk: none.
10. [dead-code] L2074 `solve_3d_foam` - `j0, k0` unpacked from `slice_geom_3d` but never used in this function (grep within L2019-2262: 0 hits). Rename to `_j0, _k0` so the unused unpack is explicit. - APPLIED
   Output risk: none.

Not touching: the two `decode` wrappers (L1560, L2232) are near-duplicates but close over `loop`, which is created after them - extracting would change closure timing; the `lambda` decoders with `# noqa: E731` stay; every public/underscored name is referenced from tests, vtk_export, writer, runloop, postmortem (grep above) so no renames; the silent `except: pass` at L179/L257/L1573/L2245 are file-cleanup / torn-sample guards, left as is.
Engineering questions: none
