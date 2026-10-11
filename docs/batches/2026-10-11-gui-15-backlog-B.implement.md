# GUI-15 Part B - implementation report

Worktree `blastlab-worktrees/gui-15`, branch `gui-15`, base `f411d1a` (Part A done and verified).
Starting state: `gate.py --for` the nine Part B source files, 38/38 suites green (12.0 min).
B1-B5 DONE, B6 DONE (AC2 recorded as a finding, as the plan asks).

## Tasks

### B1 - GUI-15 (d) - DONE - `70003c8`
`gauge_drop_reason`, `OUTSIDE_DOMAIN`, `_in_box_closed` and `_in_obstacle_open` moved to
`core/geometry.py` (new section "Dropped gauges"); `services/validation.py` imports them back, so
every caller is unchanged. A drop not strictly inside now reads `within a cell of Wall n`; Where's
measured `on the face of` (0 cm gap, `ui/scaled_distance.py:262`) stays. Docstring in
`ui/run_gauges._drop_reason`. Named pin edits: `test_case_validate.py` `face()` and the GUI-13 (e)
pair, `test_ui_setup_strip.py` pair / split / meta view; one stale comment in
`test_ui_results_screen.py` (GUI-15 (c) block).
- AC1 PASS: `rg "on the face of" blastlab --glob "!tests/**"` finds only `scaled_distance.py:231`
  (docstring) and `:262` (Where's gap 0).
- AC2 PASS: `gate.py --changed HEAD` 13/13 green (incl. `test_case_validate`, `test_ui_setup_strip`,
  `test_char_validation`, golden unchanged); `python test_layering.py` PASS.

### B2 - GUI-15 (b) - DONE - `87dcd03`
`solver2d.py` / `solver3d.py` gauge loops name a solid-centre drop with the validation pair (D6):
`_in_box_closed(snapped centre)` for the wall, `_in_obstacle_open(entered point)` for inside, worded
by `gauge_drop_reason`; a centre no box holds keeps `inside an obstacle`. `hooks.trigger_index`
docstring. Named pin edits: `_e2e_gui_native_warn.py:61`, `_qa_gui_harness.py:1597`,
`_qa_ui_harness.py:2154`; plus the header print in `test_case_validate.py` and the e2e's docstring
(both said "inside an obstacle", needed for AC2's grep).
- AC1 PASS: scratch `b2_scratch.py` (2D planar and 3D 20^3 smeared, each with G2 strictly inside and
  G3 in front of an off-grid face whose snapped centre is solid: 2D x 1.209 before face 1.21, 3D
  x 0.729 before face 0.73). Log reasons equal `validate_case`'s for both gauges in both dims
  (`inside Wall 1`, `within a cell of Wall 1`); kept `times` / `points` / `pressures` `array_equal`
  to the base pin (taken at `f411d1a`, solver code identical to `48d59f9`).
- AC2 PASS: `python -u _e2e_gui_native_warn.py` exit 0 (GUI NATIVE WARN: PASS);
  `rg "inside an obstacle" blastlab/tests` finds nothing. Gate `--changed HEAD` 31/31 green.

### B3 - P1-24 - DONE - `4e4a40f` (characterisation), `84e34f6` (fix)
Characterisation first: `test_trigger_numbering.py` pinned the no-drop control (G2 kept) and printed
the drop case. Before the fix: 2D stopped on G4's point (1.0010, 1.0010) at 0.284 ms against the
control's G3 (0.6031, 0.5036) at 0.091 ms; 3D on G4's at 0.020 ms against 0.007 ms; live labels
[1, 2, 3]; trigger 2 (the dropped gauge) fired on G3. Fix: the gauge loops keep `gauge_num`;
`trigger_index(..., numbers=)` looks the entered number up (a dropped trigger logs `Trigger gauge 2
was dropped - trigger disabled`; `n_gauges` is then the entered count). `meta['trigger_gauge']`,
`meta['trigger']['gauge']`, the `Trigger gauge n` line, `stop_reason` and the live labels
(`run_info['gauges']`, `plane_gauges(numbers=)`) carry the entered number. `_validate_closing`
warns, native only (D13): `Trigger disabled: trigger gauge G2 is dropped (see above), so the run
ends by its normal stop` (worded without "will be dropped" so no drop-warning parser counts it).
`results_gauges._default_gauge` maps the entered number to its row through the labels.
Files: `solvers/hooks.py`, `solver2d.py`, `solver3d.py`, `core/geometry.py`, `services/validation.py`,
`ui/results_gauges.py`, new `tests/test_trigger_numbering.py`.
- AC1 PASS: drop case stops with the control's `stop_reason`, on G3's point; `meta['trigger']['t']`
  equals the control's exactly (2D 0.091 ms, 3D 0.007 ms); `trigger_gauge == 3`; live labels
  [1, 3, 4] in 2D and 3D (3D: every gauge on the live y plane).
- AC2 PASS: trigger 2 - `validate_case` warns once naming G2 and the trigger (blastFoam: none, and
  its validate reaches the closing block, probed); the run ends by its normal stop, `trigger` absent,
  `trigger_gauge` None. `test_bc_trigger.py` (incl. `:189-192`, unchanged) and `test_blast2d.py` in
  the gate (38/38); `python test_blast3d.py` ALL CHECKS PASSED (699 s).
- AC3 PASS: `GaugesView` on the 2D drop result selects the row labelled G3 (without the
  `_default_gauge` change it would select row 3 = G4).

### B4 - GUI-15 (g) - DONE - `5ee21c0`
`_e2e_gui_native_warn.py`: the kept-gauge check now looks for `G1 (0.30, 0.80) m` (could fail
again), docstring and check names updated. New suite `test_solver_gauge_log.py`: 2D planar (the
e2e case) and 3D 20^3 smeared, G2 inside Wall 1, G3 outside the domain, `hooks.log` captured.
- AC PASS: `python test_solver_gauge_log.py` exit 0 in 10.5 s (13.1 s with the gate in parallel);
  `python -u _e2e_gui_native_warn.py` exit 0.

### B5 - GUI-15 (f) - DONE - `a3f4699`
`scaled_distance.outside_domain` tests 1D as `0 < r <= radius_m` (meta views without `radius_m`
still say False); `dropped_numbers` / `any_dropped` cover dim 1, so Setup's and a chain stage's
Gauges node, Run's pre-payload rows and A3's stamp all follow. `_validate_1d` warns
`G2 (r 2.00 m) outside the domain - will be dropped` (both modes, only when radius > 0).
`solver1d.py` logs `[warn] G2 (r 2.00 m) outside the domain - dropped`; live labels carry entered
numbers. `results_gauges.labels_and_dropped` numbers a 1D run from `meta['gauges_dropped']`.
Tests: `test_case_validate.py` (new `gauge_beyond_radius_checks`), `test_ui_setup_strip.py`,
`test_ui_results_screen.py`, `test_ui_drain.py` T5c.
- AC1 PASS: `Case1D(radius_m=1.5, gauge_radii=[1.0, 2.0, 1.2])` warns once naming G2 and the domain
  in both modes; `[1.0, 1.5]` gets none.
- AC2 PASS: scratch `b5_scratch.py`: the G2 line is logged; kept `times` / `radii` / `pressures`
  `array_equal` to the base pin; meta keys unchanged. `python test_char_native_api.py` PASS, golden
  unchanged; `test_regression` byte-identical (closing matrix, last).
- AC3 PASS: T5c, a real native 1D run through `start_stages`: Results labels `{1: G1, 2: G3}`, drop
  line `G2 dropped by the solver (outside the domain)`. Setup: the 1D Gauges node is warn, caption
  `3 gauges · G2 dropped`. Gate `--changed HEAD` 15/15 green.

### B6 - RESUME 2 - DONE (AC2 a finding) - `c6f85d7`
`_e2e_ui_chain_foam.py` stage-3 `Case3D` gets `t_end=2e-4`; nothing else changes.
- AC1 PASS: `pgrep -a blastFoam` empty, section 8.2 dry run `False`; `python -u _e2e_ui_chain_foam.py`
  exit 0, `UI CHAIN FOAM: PASS (33 checks, chain 144 s)` against `CHAIN_TIMEOUT_S` 1800;
  `3d/MODEL.json` holds `"t_end": 0.0002`. Nothing deleted in `/root/blastlab_runs`; `pgrep` empty
  afterwards.
- AC2 recorded: `_e2e_ui_view3d.py` on the real platform (`QT_QPA_PLATFORM` unset), run through
  scratch `b6_view3d_win32.py` (a 20 ms Win32 sampler; twice, same result). G1 and G2 PASS (embed,
  run, playback, 79 frames). G3 FAILS: "the 3D window is now a top-level of its own", "the host shows
  the re-attach note", "re-attached, same container", then `AttributeError` at `:131`
  (`_float_win` is None). Win32 over 37.3 s, 1758 samples: the visible child was never off its
  container (longest wrong stretch 0 s), `GetParent` == the container's native window in every
  sample. Around detach the container id changes 5842150 -> 12988830 (0.6 s after
  `set_floating(True)`, host `_floating` True) -> 15677060 -> 120728132, the child always visible at
  the in-host rect (1383, 382)-(1947, 752). See issue 1.

## Closing matrix
- `gate.py --changed f411d1a --deep`: 117/117 suites green (26.3 min). It includes all 16
  `test_gui_*` Tk suites (section 9: `core/`, `solvers/`, `services/` changed) - all green. WSL
  solve suites not run (8.6); `_e2e_*` / `_qa_*` are not gate suites (the two e2es were run
  above; the harnesses were not run, per the rules).
- `gate.py --only regression`: byte-for-byte PASS (last).
- App start: offscreen MainWindow on private settings after B1, B2 and at the end - PASS (section
  8.2 dry run `False` each time).

## Files touched
`core/geometry.py`, `services/validation.py`, `solvers/solver1d.py`, `solver2d.py`, `solver3d.py`,
`solvers/hooks.py`, `ui/run_gauges.py` (docstring), `ui/results_gauges.py`, `ui/scaled_distance.py`;
tests `test_case_validate.py`, `test_ui_setup_strip.py`, `test_ui_results_screen.py`,
`test_ui_drain.py`, new `test_trigger_numbering.py`, new `test_solver_gauge_log.py`,
`_e2e_gui_native_warn.py`, `_e2e_ui_chain_foam.py`, `_qa_gui_harness.py`, `_qa_ui_harness.py`.

## GUI screens touched (for QA)
Setup Checks (drop wording `within a cell of Wall n`; 1D beyond-radius warning; the trigger
warning), Setup and chain-stage Gauges node for 1D (warn, ` · G2 dropped`), Run gauge column and
log (wall named; 1D drop; trigger lines with entered numbers; live markers G1 G3 G4), Results Gauges
(1D labels G1 G3 and the drop line; default selection = the trigger's row).

## Numerical changes
- P1-24 (TODO.md:645-653, GUI-14 B verify issue 1, owner approved): a native run whose trigger
  comes after a dropped gauge now stops on the trigger gauge. Verify case: 2D 0.284 ms on G4 ->
  0.091 ms on G3 (= the G2-kept control); 3D 0.020 ms -> 0.007 ms. A trigger on the dropped gauge
  used to fire on the next kept gauge (2D 0.091 ms on G3); now it is disabled and the run ends by
  its normal stop. With no gauge dropped nothing moves (`test_bc_trigger`, `test_blast2d/3d`,
  regression).
- Everything else is strings: kept-gauge arrays `array_equal` to base (2D, 3D, 1D scratch).

## Engineering issues noticed
1. **Native-mount detach is undone at once** (`ui/view3d_host.py:664-673`, `:906-918`): on the
   native path `set_floating(True)` drops the mount and asks the viewer to detach; the child
   re-reports its handle, and `on_window` re-embeds because `_container` is None - it does not look
   at `_floating`. Measured above: within 0.6 s the window is back in a new mount while the host
   says floating. `_e2e_ui_view3d.py` G3 still assumes the `_FloatWindow` path. Recommendation: a
   small GUI task - decide the intended native detach, guard `on_window` with `_floating`, update
   G3 for the native path; measure with the same Win32 sampler.
2. The blastFoam chain e2e prints ~50 `[blastlab] probes: rho/U times do not match p - using p only
   (n+1 rows vs n)` lines to stderr while sampling live probes (a torn last row). Harmless (the next
   read is whole) but noisy. Recommendation: log once per run, or drop to debug - low priority.
3. Results on a native result made before P1-24, with a drop before its trigger: its meta holds the
   kept number, which `_default_gauge` now reads as entered (a different row may be selected by
   default). In-memory and reloaded old results only; no number changes. Recommendation: accept.
4. `results_gauges.export_drop_note` stays empty for 1D, so an exported 1D gauge figure carries no
   drop footnote (the screen names it). Recommendation: extend to dim 1 in a later batch if wanted.

## Open questions for the owner
- Issue 1: fix the native detach (recommended, next GUI batch) or keep detach disabled there?
- Issue 4: should 1D exports name a dropped gauge too? Recommendation: yes, low priority.

## Notes for the verifier
- D13's warning text deliberately avoids "will be dropped" (several tests count drop warnings by
  that phrase).
- `trigger_index`'s "does not exist (N gauge(s))" now counts entered gauges when `numbers` is given
  (the solvers pass the entered count); `numbers=None` behaves exactly as before.
- 1D: r <= 0 also reads `outside the domain` - it is the solvers' own test.
- Scratch scripts (pins and probes) are in the session scratchpad: `b2_scratch.py`,
  `b5_scratch.py`, `b3_foam_probe.py`, `b6_view3d_win32.py`, `b6_analyse.py`.
