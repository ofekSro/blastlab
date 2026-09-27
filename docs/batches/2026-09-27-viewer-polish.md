# Batch 2026-09-27 - viewer-polish

**Goal:** make the 3D viewer's colour scale honest on every colour-mapped layer
(log flag reaches Surface loads and Volume, not just the planes) and stop the
scene from rendering more than once per frame - all inside `blastlab/viz3d/` and
its tests, with synthetic fields only.

Worktree: `C:\Users\rotem.ofek\blastlab-worktrees\viewer` (branch `viewer-polish`,
from `master` at `c73d4fc`). Fixed batch: `P3-7`, `P3-8`, `P3-25`.

Constraints in force: only `blastlab/viz3d/*.py` and `blastlab/tests/test_viz3d_*.py`
change. No WSL solves. The GUI process never imports VTK
(`test_ui_no_vtk_in_main.py` stays green - nothing here touches `ui/`). On-screen
QA (CLAUDE.md §8.7) is gated on another session and is kept to the short
checklist in section 6.

---

## 1. What was found before planning (read, then measured headless)

Measurement script: an off-screen `pv.Plotter(760x560)` + `BlastScene(embedded=True,
n_planes=6)` on the `test_viz3d_scene.py` synthetic 40x40x40 grid, a `RenderEvent`
observer on the render window, `tracemalloc` around each step.
pyvista 0.49.0, VTK 9.7.0, pyvistaqt 0.13.1.

| Claim in TODO | Where | Measured |
|---|---|---|
| P3-7 "blit renders twice" | `gui/vtk_host.py:130-138` (`_blit`: `render()` then `screenshot(return_img=True)`) | **1 render per blit** (`render()`=1, `screenshot()`=+0). pyvista 0.49 `image_from_window` calls `ShouldRerenderOff()`; the explicit `render()` is still required (`screenshot` only renders on `_first_time`). The double render is gone in this pyvista. |
| P3-7 "~1.3 MB per frame" | same | **Real.** `img` 760x560x3 = 1.28 MB, `img.tobytes()` a second 1.28 MB, `header + ...` a third; tracemalloc peak 3.83 MB, 2.55 MB still live after the blit, plus the Tk `PhotoImage` copy. 3.0x the image size per blit. |
| (not in TODO) extra renders inside `viz3d/viewer.py` | every `pl.remove_actor(name)` without `render=False` (lines 830, 947, 994, 1180, 1254) | A frame that supersedes a sampled plane: **1 render inside the scene** (then the Qt host tick renders again = 2 per frame in a live blastFoam run). Field switch p->rho->p: **4**. Volume on/off: **1**. A plain frame: 0. |
| (not in TODO) per-frame field upload | `ensure_field` (`_ovp_kpa` then `.ravel(order='F')` = two copies), `_SurfaceLoads._track` + `refresh` (`_ovp_kpa` twice per face) | tracemalloc peak 0.59 MB per `on_message` for a 0.26 MB field (2.3x one field). At a 128-cubed display grid that is 8 MB x 2 per field per frame. |
| P3-25 loads bar linear | `_SurfaceLoads._load_clim` (1149), `on_clim_changed` (1170), `refresh` (1191) | Confirmed. `set_log_scale` -> `_broadcast_clim` -> `loads.on_clim_changed()` **is** called, but `_load_clim` returns the un-clamped `_own` range and nothing ever sets `mapper.lookup_table.log_scale` or passes `log_scale=` to `add_mesh`. After `set_log_scale(True)`: plane LUT `log_scale=True`, load LUT `log_scale=False`, loads bar `GetLookupTable().GetScale()==0`. |
| P3-8 log only on slice planes | `_CutPlane.refresh` (842/858) and `_SampledPlane.refresh` (964/969) pass the flag; `_Volume` (1259-1274) and `_SurfaceLoads` do not; `_Isosurface` is a single colour (no map) | Confirmed. Colour-mapped layers are exactly: planes, sampled plane, volume, loads. So P3-8 = the Volume layer, P3-25 = the Loads layer, and together they close "every colour-mapped layer follows the log flag". |
| pyvista `add_volume(log_scale=True)` | pyvista `LookupTable.to_color_tf` | **Does not colour in log.** The LUT gets `log_scale=True`, but the volume's colour transfer function is sampled at 256 *linearly* spaced values (`np.linspace(mn, mx, n)`): colour at the geometric midpoint of 1e-3..1e3 came out (0.365, 0.272, 0.227) instead of turbo(0.5) = (0.643, 0.988, 0.231). A custom `opacity=` array is sampled the same way. |
| hand-built log-spaced `vtkColorTransferFunction` / `vtkPiecewiseFunction` on `actor.prop` | tried | Numerically right (colour at geometric mid = turbo(0.5) within 0.01, opacity 0.5) **but VTK warns** `vtkOpenGLVolumeRGBTable: required texture size of 33554432, falling back to 32768 ... may cause an incorrect lookup table mapping`. The GPU mapper samples the TF on a linear texture; at a real run's range (peak ~3e6 kPa, six decades) one texel is ~92 kPa and the whole air shock lands in the first texel. Rejected. |
| `mapper.scalar_range = ...` on an existing volume | pyvista volume mapper | Re-ranges both transfer functions (ctf/otf range followed 0..100 -> 0..1000). So the existing linear `on_clim_changed` path is fine; only log needs a data transform. |

Both GUIs already send the flag to the scene: Qt `ui/view3d_host.py:1242` -> `_ctrl('log', ...)`
-> `viewer._CTRL['log']` -> `set_log_scale`; Tk `gui/view3d_panel.py:536` calls
`set_log_scale` directly. **No change outside `viz3d/` is needed for P3-8 or P3-25.**

References: `docs/references/INDEX.md` has no entry that applies (no standard or manual
governs a viewer colour bar). No `ref:` on any of the three lines. Nothing to attach.

---

## 2. Tasks in order

Each step leaves `python blastlab/tests/test_viz3d_scene.py` green and the app runnable.

### T1 - `P3-25` Surface loads follow the log flag  (S)

> TODO text: "The **"Surface loads" colour bar stays linear** while the field bar is
> logarithmic - the loads layer holds its own range and does not receive the log flag."

Root cause: `_SurfaceLoads` keeps a private linear range (`_own`) and never touches its
actors' lookup tables. The scene's clamp lives only inside `BlastScene.active_clim`.

Files: `blastlab/viz3d/viewer.py` (`BlastScene.active_clim`, `_SurfaceLoads._load_clim`,
`on_clim_changed`, `refresh`), `blastlab/tests/test_viz3d_scene.py`.

Fix:
1. Factor the clamp out of `active_clim` into a module function
   `log_clim(lo, hi, decades=LOG_DECADES) -> (max(lo, hi*10**-decades, 1e-9), hi)` and
   call it from `active_clim`. T2 reuses it.
2. `_load_clim`: after choosing the range (manual overpressure clim or `_own`), apply
   `log_clim` when `s.log_scale`.
3. `on_clim_changed`: for every `load_*` actor set `mapper.scalar_range = clim` **and**
   `mapper.lookup_table.log_scale = s.log_scale`.
4. `refresh`: pass `log_scale=s.log_scale` to `add_mesh` (so loads toggled on while log is
   on are born log), and in the `else` branch set the LUT flag as in 3.
5. The bar: `pl.scalar_bars[LOADS_BAR_KEY]` reads the first load actor's LUT, so a log LUT
   gives log ticks with no further code. The `fmt='%.0f'` on the bar is kept (kPa are
   integers on a 3 kPa..3e6 kPa bar).

Acceptance (headless, `test_viz3d_scene.py`, new section `S3-P25`):
- After `scene.set_log_scale(True)` on a scene with visible loads: every `load_*` actor
  has `mapper.lookup_table.log_scale is True`, `mapper.scalar_range == log_clim(*own)`
  with `scalar_range[0] > 0`, and `pl.scalar_bars[LOADS_BAR_KEY].GetLookupTable().GetScale() == 1`
  (VTK_SCALE_LOG10). After `set_log_scale(False)`: `log_scale is False`, range lower bound
  `== 0.0`, bar scale `== 0`.
- Log stays on across a new frame and across a loads off/on toggle (actors rebuilt via
  `_remove_all`): both re-check the three facts above.
- Existing B19 checks still hold unchanged: with the field switched to `rho`, the loads
  range is still an overpressure range (log-clamped now, but `own[1]` unchanged); manual
  Min/Max on `p` with log on reaches the loads as `log_clim(vmin, vmax)`.

Dependency: none. T2 depends on `log_clim` from here.

### T2 - `P3-8` Log contours reach the Volume layer  (M)

> TODO text: "Log contours apply only to slice planes."

Interpretation (pinned): "log contours" is the `Log contours` / `Log colour scale`
checkbox = `BlastScene.log_scale`; the layers that colour-map a field are the cut planes,
the sampled plane, the volume and the loads. Planes and sampled plane already follow;
loads are T1; **this task is the Volume layer.** The isosurface is a single colour and is
out of scope by construction. The earlier batch (`2026-09-24-p1-settling-runs.md` §"needs
clarification" 6) asked "which layers, and is it the same fix as P3-25?" - answer: the
volume, and no, it is a different mechanism (see the pyvista findings in §1).

Root cause: `_Volume.refresh` calls `add_volume` without `log_scale`, and `on_clim_changed`
only sets `scalar_range`. Passing `log_scale=True` to pyvista would not help (its colour TF
is sampled linearly) and a hand-built log TF hits VTK's 32768-texel cap (§1).

Files: `blastlab/viz3d/viewer.py` (`BlastScene.ensure_field`/`_display` or a helper on
`_Volume`, `_Volume.refresh`, `_Volume.on_clim_changed`), `blastlab/tests/test_viz3d_scene.py`.

Fix (data transform, linear transfer functions):
1. Add a derived point array `VOL_LOG_KEY = 'vol_log'` on `scene.grid`, filled only when
   the volume is visible **and** `s.log_scale`:
   `np.log10(np.clip(field, lo, hi))` with `(lo, hi) = log_clim(*active_clim-without-clamp)`,
   i.e. the same `(lo, hi)` the planes use. Compute it in `_Volume.refresh` (per displayed
   frame while volume+log are on; skip entirely otherwise) - one float32 array of the
   display grid, F-ordered like the others.
2. `_Volume.refresh`: the "added" key becomes `(field, log_scale)`; on change, `_remove()`
   and `add_volume(scalars=VOL_LOG_KEY if log else field, clim=(log10 lo, log10 hi) if log
   else active_clim(), opacity='linear', ...)`. Same frame, same key: `grid.Modified()` as now.
3. `_Volume.on_clim_changed`: if `_added[1] != s.log_scale` -> rebuild (a checkbox click,
   never per frame); else set `scalar_range` to the (log10 or linear) range - pyvista
   re-ranges both transfer functions on that setter (§1).
4. The volume shows no scalar bar (`show_scalar_bar=False`), so the log10 values never
   appear as labels. The planes' bar remains the reference bar for the field.
5. Opacity: `'linear'` over the log10 range = linear in log(value), so the shock cloud at
   1 % of peak is 5/6 of the way up the ramp instead of 1 %. This is the intended reading
   of "log contours" for a cloud and is what the on-screen checklist confirms.

Acceptance (headless, `test_viz3d_scene.py`, new section `S3-P8`):
- With the volume visible and `set_log_scale(True)`: `pl.actors['volume_f'].mapper.array_name == 'vol_log'`,
  `mapper.scalar_range == (log10(lo), log10(hi))` where `(lo, hi) == scene.active_clim()`,
  and `grid.point_data['vol_log']` equals `log10(clip(p, lo, hi))` to 1e-5 relative.
- Colour honesty: `vol.prop.GetRGBTransferFunction().GetColor(log10(sqrt(lo*hi)))` is within
  0.02 per channel of `pv.LookupTable('turbo').map_value(0.5)[:3]`, and
  `vol.prop.GetScalarOpacity().GetValue(log10(sqrt(lo*hi)))` is within 0.02 of 0.5. In
  linear mode the same geometric midpoint maps to opacity `< 0.05` (this is the behaviour
  being fixed; pre-registered as the contrast).
- `set_log_scale(False)` returns the volume to `array_name == field` and the linear range;
  a field switch to `rho` while log is on rebuilds with `vol_log` computed from `rho`.
- A new frame while volume+log are on fires **0** renders inside the scene (see T3) and
  refreshes `vol_log` (its max changes with the frame).
- `test_viz3d_scene.py` S5 screenshot still `std > 1.0` with the volume on and log on.

Dependency: T1 (`log_clim`).

### T3 - `P3-7` One render per frame, fewer copies per frame (the `viz3d/` part)  (S)

> TODO text: "The viewer's blit path renders twice and allocates ~1.3 MB per frame."
> (archive: `vtk_host.py ~130-138`)

Split. The named site is `blastlab/gui/vtk_host.py` - **outside this batch's boundary**;
see the cross-boundary flag below. Inside `viz3d/` the same symptom class exists and is
fixable here:

Root cause (viz3d): five `remove_actor(...)` calls use pyvista's default `render=True`,
so a live blastFoam frame that supersedes the sampled plane renders once inside
`BlastScene._display` and once more in `_ViewerHost.tick` (`w.render()`), and a field
switch renders four extra times. Separately, `ensure_field` makes two full-grid copies per
field per frame (`_ovp_kpa` C-order temp, then `ravel(order='F')` copy) and
`_SurfaceLoads` converts each face to overpressure twice (`_track`, then `refresh`).

Files: `blastlab/viz3d/viewer.py` (`_CutPlane.refresh:830`, `_SampledPlane.clear:947`,
`_MeshEdges._remove:994`, `_SurfaceLoads._remove_all:1180`, `_Volume._remove:1254`,
`ensure_field:472`, `_SurfaceLoads._track/refresh`), `blastlab/tests/test_viz3d_scene.py`.

Fix:
1. `render=False` on every `remove_actor` in `viewer.py` (the host tick is the single
   render point; `_ViewerHost.tick` and the Tk `_render_tick` both already render once
   when dirty).
2. `ensure_field`: build the F-ordered float32 in one step, e.g.
   `vals = np.subtract(arr, P_AIR, dtype=np.float32, order='F'); vals /= 1e3` (or
   `np.asarray(arr, np.float32, order='F')`), then `.ravel(order='F')` is a view. Same
   numbers: `_ovp_kpa` semantics are (p - P_AIR)/1e3 in float32; keep the results
   bit-identical to today (see Risks).
3. `_SurfaceLoads.refresh`: convert each face once, reuse the array for `_track`.

Acceptance (headless, `test_viz3d_scene.py`, new section `S7-P3-7`; the test attaches a
`RenderEvent` observer on `pl.render_window` after a warm-up `pl.render(); pl.screenshot()`):
- Renders fired inside the scene, pre-registered thresholds (measured today in brackets):
  `on_message('frame')` after `on_sampled_plane(...)` = **0** [1]; `set_field('rho'); set_field('p')`
  = **0** [4]; `layers['volume'].set_visible(True); set_visible(False)` = **0** [1];
  a plain frame stays **0** [0].
- Allocation per frame, pre-registered: `tracemalloc` peak during one `on_message('frame')`
  on the 64,000-point synthetic grid (`p`, `rho`, `loads` in the payload, field `p`, loads
  on, volume off) **<= 1.5 x one float32 display field** (0.26 MB -> cap 0.39 MB) [0.59 MB,
  2.3x]. Print the ratio in the check detail.
- Bit-identity: `grid.point_data['p']` after the change equals the array the old
  `_ovp_kpa(arr).ravel(order='F')` produces (`np.array_equal`, not allclose) on the
  synthetic frame - keep the old expression in the test as the oracle.
- The existing panel test still passes: `python blastlab/tests/test_viz3d_panel.py`
  ("blit re-renders (frames not stale)", "camera moves show up in the blit") - it exercises
  `gui/vtk_host.py` unchanged and proves that removing in-scene renders did not make the
  Tk blit stale.

Dependency: none (do it after T1/T2 so their new checks run on a scene that already
counts renders - or first; either order is runnable).

#### Cross-boundary flag - `P3-7` at its named site (`gui/vtk_host.py`) - NOT in this batch

What the other session would change (Tk GUI only; the Qt GUI embeds the child window and
never blits): in `VtkTkHost._blit`, keep the explicit `render()` (it is the one render, and
without it the blit is stale - `test_viz3d_panel.py` pins this), and cut the copies:
`ppm = b''.join((header, memoryview(np.ascontiguousarray(img)).cast('B')))` removes the
`tobytes()` copy (3 -> 2 buffers), or keep one reusable `bytearray` for the PPM.
Pre-registered criterion for that change: tracemalloc peak per `_blit` **<= 2.0 x
`img.nbytes`** [3.0x today] - **superseded, owner decision 2026-09-27:** the cap is
**`<= 2 * img.nbytes + 64 KiB`**, a fixed allowance, not a ratio. The two-buffer join
measured 2.0018x: the ~2.3 KB above two full buffers is size-independent overhead
(PPM header + pyvista's screenshot objects), and Tk accepts only `bytes` (a `bytearray`
was rejected), so two full buffers are the floor. Pinned headless in
`blastlab/tests/test_viz3d_blit.py`. Renders per `_blit` **== 1** [1 today - already met; the TODO's
"renders twice" is stale on pyvista 0.49 and should be recorded as such when the item is
closed]. Also relevant there: `P1-19` (Tk `wglMakeCurrent failed` under a chained
hand-off) lives in the same host.

Smallest alternative that stays inside `viz3d/`: none that fixes the Tk blit - the scene
does not own the plotter's screenshot loop. The in-`viz3d/` work above (T3) is the part
that applies to both GUIs.

---

## 3. Risks

- **Numerical display values.** T3's `ensure_field` rewrite touches the numbers uploaded
  to VTK. Protect with the characterisation check first (bit-identity against the old
  expression on the synthetic frame) before touching the code. No solver output, no
  regression baseline, no standard coefficient is involved; `test_regression.py` is
  unaffected but run it once at the end anyway (it is the trust gate).
- **`log_clim` refactor** changes no value: `active_clim` must return exactly what it
  returns today for `(vmin, cmax, log_scale)` - add a three-case check (log off; log on
  with lo>0; log on with lo=0) before moving the code.
- **B19 behaviour** (loads keep an overpressure range under Density; manual Min/Max on a
  density field leaves the loads alone) is pinned by the existing S3-B19 section; keep it
  green after T1.
- **Volume in log mode costs one extra float32 field per frame** (only while volume and
  log are both on; the volume is off by default). At a 128-cubed display grid that is
  8 MB per frame - same order as one `ensure_field`. Acceptable; state it in the docstring.
- **VTK texture cap** is why T2 transforms the data instead of the LUT. If a future
  pyvista fixes `to_color_tf`, the data transform still works; do not revisit.
- **Tk host untouched**: `test_viz3d_panel.py` (real Tk root, off-screen pyvista) must
  stay green - it is the only test that exercises `gui/vtk_host.py` with a `BlastScene`
  and CLAUDE.md §9 says the Tk suites run whenever a change touches shared modules.

Tests to run (all headless, no WSL, no windows):
```
cd blastlab/tests
python test_viz3d_scene.py       # the harness for T1-T3
python test_viz3d_panel.py       # Tk host + blit, unchanged code, must stay green
python test_viz3d_sampled_plane.py
python test_viz3d_protocol.py
python test_ui_no_vtk_in_main.py # GUI process never imports VTK
python test_regression.py        # trust gate, byte-for-byte
```

---

## 4. Needs clarification (nothing excluded from the batch; two notes for the owner)

1. `P3-7` half-stale: "renders twice" is not reproducible on pyvista 0.49 (one render per
   blit, measured). When the item is closed, the DONE entry should say the allocation
   half was the real one and the render half was fixed upstream by pyvista's
   `ShouldRerenderOff`. Question for the other session: may `gui/vtk_host.py._blit` take
   the two-buffer PPM change under the pre-registered 2.0x criterion above?
2. `P3-8` interpretation is pinned here (Volume layer, log10-data transform, opacity
   linear in log). If the owner meant the isosurface too, that layer has no colour map -
   the only "log" meaning there would be a log-spaced iso level, which is a different
   feature (not in this batch).

---

## 5. Remaining backlog (viewer-adjacent, not this batch)

- **Tk host follow-up:** `P3-7` at `gui/vtk_host.py` (cross-boundary, see T3 flag), `P1-19`
  (Tk `wglMakeCurrent failed` under a chained 2D stage building a 3D scene in-process),
  `P2-16` (Tk `root.update()` 10-13 s in a chain's later stage, matplotlib live slice).
- **Cosmetic, native stdout untouched:** `P3-9` (`x [m]` -> `r [m]` on axisymmetric
  animations, `output/animation.py`).
- **Cosmetic, needs re-baseline:** `P3-10` ("0 kg TNT" in the chained 3D init line),
  `P3-11` (`n_snapshots` semantics 1D vs 2D/3D - still needs the owner's choice).
- **Performance:** `P3-6` (read `processor*/` directly for uniform MPI runs).
- **Animations:** `P3-24` (Schlieren / shadowgraph field, one extra field per time dir).

---

## 6. On-screen QA checklist (separate, gated on the other session's OK)

Real viewer child, `QT_QPA_PLATFORM` unset, a finished 3D run loaded with
`python -m blastlab --load-foam-run DIR` or the Qt `_qa_ui_harness.py` viewer scenario.
Each item is a look, not a measurement; the numbers are already pinned headless.

1. Toggle `Log colour scale` with Surface loads on: the bottom (loads) bar's tick labels
   change from evenly spaced kPa to decades (e.g. 1, 10, 100, 1000) and the box faces
   near the charge stop reading as one saturated colour. Toggle back: linear labels return.
2. Turn `Volume` on, then toggle log: in log mode the shock shell is visible as a
   coloured cloud beyond the products; in linear mode it is nearly transparent. No VTK
   warning about texture size appears in the child's stdout.
3. Switch field to Density with volume + log on, then back to Pressure: no leftover
   `Overpressure` bar, the volume recolours, the loads bar stays in kPa.
4. Play back 20 frames with the sampled-plane HUD line present: no flicker between
   frames (the in-scene render is gone), frame rate not lower than before.
5. `python -m blastlab --tk`, same run, the 3D panel: blits still update on frames and on
   camera drags (nothing in `gui/` changed, but T3 removed renders the Tk path might have
   leaned on - the headless panel test says it did not; confirm once on screen).
