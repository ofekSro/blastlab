# GUI-14 Part B - implementation report

Batch `docs/batches/2026-10-11-gui-14-backlog.md`, Part B (B1). Worktree
`C:\Users\rotem.ofek\blastlab-worktrees\gui-14`, branch `gui-14`, base `6d3d1ac` (Part A verified).
Owner decision 2026-10-11: Q3 approved (the two named pin edits). Commit `8a35381`.

## Tasks

### B1 - (g) Native solver logs name the gauge `G<n>`, in metres - DONE (`8a35381`)
`_run_blast_2d` (`solvers/solver2d.py:280-295`) and the 3D setup loop (`solvers/solver3d.py:338-354`)
number the gauges with `enumerate(gauges, start=1)` and log
`[warn] G<n> (x.xx, y.xx[, z.xx]) m inside an obstacle - dropped` /
`... outside the domain - dropped`; the name is built as `validation._validate_closing`
builds it (`:1566`). Literals stay in the solvers; no `services` import; the drop tests and the
cell snapping are untouched. Named pin edits (Q3): `_e2e_gui_native_warn.py:61`,
`_qa_gui_harness.py:1597`. `_qa_ui_harness.py:2154` matches the substring and is unchanged.
- **Deviation from the plan's pin text:** the plan wrote the new pin as `[warn] G1 (1.40, 0.30) m ...`.
  In both cases the dropped gauge `(1.4, 0.3)` is the *second* entry (`gauges=[(0.3, 0.8), (1.4, 0.3)]`,
  `_e2e_gui_native_warn.py:46`, `_qa_gui_harness.py:873`), so D9's own rule makes it `G2`, which is
  also Setup's number. Both pins read `G2`.
- Crit 1 PASS: scratch `b1_arrays.py` (tiny 2D planar, 4 gauges, and tiny 3D with
  `charge_resolution='smear'`, 4 gauges; G2 inside the wall, G3 outside) run at base and after.
  Logged: `[warn] G2 (1.40, 0.30) m inside an obstacle - dropped`,
  `[warn] G3 (5.00, 5.00) m outside the domain - dropped`,
  `[warn] G2 (0.80, 0.60, 0.20) m inside an obstacle - dropped`,
  `[warn] G3 (5.00, 5.00, 5.00) m outside the domain - dropped`. Kept gauges (G1, G4) `times`,
  `points` and every `pressures` array `numpy.array_equal` to the base: 2D True, 3D True; every
  other log line identical to the base: True (634 / 163 samples).
- Crit 2 PASS: §8.2 dry run (`settings.json` in the worktree, `auto_cleanup` False), then
  `python -u _e2e_gui_native_warn.py` -> 4/4 PASS, exit 0.
- Crit 3 PASS: `gate.py --changed 6d3d1ac --deep` 105/105 green, 24.8 min (includes
  `test_blast2d.py` and all 16 `test_gui_*`; the 8 WSL solve suites not run, §8.6, WSL left alone);
  `gate.py --only test_blast3d` 1/1 green, 11.5 min; `gate.py --only regression`, run last,
  `regression (byte-for-byte): PASS`. `rg "Gauge \(\{g" blastlab/solvers`: 0 matches.
- `python -m blastlab` started and ran 12 s (stopped by PID, no child left).
- Tests and commands: `gate.py --for blastlab/solvers/solver2d.py blastlab/solvers/solver3d.py`
  (start, 5/5), `gate.py --changed HEAD` (5/5), the scratch script, the e2e, the closing matrix.

## Files touched
`blastlab/solvers/solver2d.py`, `blastlab/solvers/solver3d.py`, `blastlab/tests/_e2e_gui_native_warn.py`
(line 61), `blastlab/tests/_qa_gui_harness.py` (line 1597), this report.

## GUI screens touched (for QA)
None directly. The new line shows wherever the native run log is shown: Qt Run log and status line,
Tk Run log, the CLI console, the model folder's `run.log`.

## Numerical changes
None. Strings only; kept-gauge records `array_equal` to the base; regression byte-identical.

## Engineering issues noticed
1. **After a drop, the solvers number the kept gauges, not the entered ones.** Unchanged by B1
   (strings only), seen while reading the loop:
   - Live view: `solver2d.py:337-338` and `core/geometry.plane_gauges` (`:114-117`, used at
     `solver3d.py:421`) label `n + 1` over `gauge_actual`, the kept list. With G2 dropped, Setup's G3
     is drawn as 2, while Run's cards and now the log keep the entered number (`run_gauges.py:13`).
   - T51 trigger: `trigger_index(trigger_gauge, len(gauge_ij))` (`solver2d.py:299`, `solver3d.py:359`)
     indexes the kept list, although `hooks.py:60-61` says the number "reads like the gauge table".
     With G2 dropped, `trigger_gauge = 3` watches G4 (or is disabled when only three remain) - a
     silent change of which gauge ends or remaps the run.
   **Recommendation:** a P1 row for the trigger (it can change when a run stops) and a P2 row for the
   live labels: keep the entered number with each kept gauge, and have `validate_case` warn when the
   trigger gauge is a dropped one. Needs a characterisation test first (stop time on such a case).
2. **`_e2e_gui_native_warn.py:63-64` is now vacuous.** Its "kept gauge is not reported dropped" check
   looks for `'Gauge (0.3, 0.8)'`, which the new format never prints. It still passes, but it can no
   longer fail. Not edited (owner approved only `:61`). **Recommendation:** make it
   `'G1 (0.30, 0.80) m' not in log`, a one-line pin edit, next time the file is opened with approval.
   Its docstring (`:4-5`) and check name (`:60`) still quote the old `[warn] Gauge ...` form.
3. **No fast test pins the 3D string.** The only committed pin is the 2D e2e (Tk, a real run). The
   owner's "no other committed test changes" kept me from adding one. **Recommendation:** a fast
   check in `test_blast3d.py` (or a new suite) with a hooks logger on a 12^3 smeared case, ~1 s.

## Open questions for the owner
- None blocking. Items 2 and 3 above need an owner nod because they touch committed tests.
