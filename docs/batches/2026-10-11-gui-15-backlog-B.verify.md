# GUI-15 Part B - verification (full)

Range f411d1a..d286a4f, worktree gui-15. Scratch scripts are in the session scratchpad (`v_ab_run.py`,
`v_ab_compare.py`, `v_fail_on_base.py`, `v_trig_on_base.py`, `v_view3d_probe.py`). For the A/B, a
temporary worktree at f411d1a was used and then removed. Solver, core and services code at f411d1a is
identical to 48d59f9: `git diff --stat 48d59f9 f411d1a -- blastlab/solvers blastlab/core blastlab/services`
is empty.

## Tasks

- **B1 (d) VERIFIED.**
  - AC1: `rg "on the face of" blastlab --glob "!tests/**"` finds only `ui/scaled_distance.py:240`
    (a docstring) and `:271` (Where's gap 0).
  - AC2: `test_case_validate`, `test_ui_setup_strip` and `test_char_validation` are green in the deep
    gate. `python test_layering.py` passes. No golden or fixture is in the diff.
  - Fails when it should: HEAD's `test_case_validate.py` run against the base tree fails on exactly
    the 12 moved wording pins and the 2 new 1D checks. HEAD's `test_ui_setup_strip.py` fails 4 checks:
    3 wording pins and the 1D check.
- **B2 (b) VERIFIED.**
  - AC1: an independent A/B, made stronger than the plan asks:
    - Two walls, so the wall index is tested (Wall 2 and Wall 1, not only 1).
    - 2D gauges: one strictly inside, (1.207, 0.3) in front of an off-grid face at 1.211 whose snapped
      centre is solid, one exactly on that face, one outside the domain, one inside Wall 1.
    - 3D: the same kinds of gauge on a 20^3 smeared grid.
    - Every dropped gauge's log reason equals `validate_case`'s: 5 gauges in 2D, 4 in 3D.
    - Kept `times` / `points` / `pressures` are `array_equal` to base. Only the `[warn]` lines differ.
  - AC2: `python -u _e2e_gui_native_warn.py` exits 0. `rg "inside an obstacle" blastlab/tests` finds
    nothing.
- **B3 (P1-24) VERIFIED. The numeric claim holds exactly.**
  - A/B, base and HEAD, same cases:

    | Case | base | HEAD |
    |---|---|---|
    | 2D, G2 dropped, trigger 3 | 2.839809721551745e-04 s, on G4's point | 9.123631574235016e-05 s, on G3's point |
    | 3D, G2 dropped, trigger 3 | 1.999e-05 s | 7.271778445435593e-06 s |

  - Each HEAD time is bit-equal to the no-drop control's.
  - The drop run's G1/G3/G4 series are `array_equal` to the control's series 1/3/4: the gauges are
    passive.
  - Control run: base and HEAD are bit-identical, so with no drop nothing moves.
  - Live labels are [1, 3, 4] in 2D and 3D, and the live trigger is 3.
  - New case: three gauges with G2 dropped and trigger 3. Base logged `does not exist (2 gauge(s))` and
    ran to the boundary. HEAD fires on G3 at the control's time.
  - Trigger 2 (on the dropped gauge): one warning, the `was dropped - trigger disabled` log line, the
    normal stop, `trigger_gauge` None.
  - AC3: covered by `test_trigger_numbering` (Results selects G3), which is in the gate.
  - Fails when it should: run on base, the suite's drop checks fail 10 times (2D and 3D).
  - `test_bc_trigger`, `test_blast2d` and `test_blast3d` (ALL CHECKS PASSED) are green in the gate.
  - The exported animation also benefits: `output/plots.gauge_points` numbers the gauges as entered,
    so the trigger star now lands on the gauge that fired.
- **B4 (g) VERIFIED.**
  - `test_solver_gauge_log` passes in 13.6 s. Run on base, it fails its 2 Wall-1 checks.
  - `_e2e_gui_native_warn.py` exits 0.
  - The check can fail again: a mutant of the e2e with a second wall over G1 fails exactly
    `the kept gauge G1 is not reported dropped`.
- **B5 (f) VERIFIED.**
  - AC1: the new `test_case_validate` checks pass. Both fail on base.
  - AC2: in the A/B, the 1D G2 log reason equals the warning's. The kept arrays are `array_equal` to
    base, the meta keys are unchanged, and the live labels are [1, 3].
  - `test_char_native_api` is green in the gate.
  - AC3:
    - `test_ui_drain` T5c is a real `start_stages` run.
    - `test_ui_results_screen` checks the 1D rows, and `test_ui_setup_strip` the 1D warn caption.
    - On base, these fail 2, 2 and 1 checks.
  - Probe: for a gauge at exactly `radius_m`, the foam writer keeps it (18 radius/cell combinations).
    So the 1D warning cannot miss a writer drop at the edge.
- **B6 (RESUME 2) VERIFIED, and the AC2 finding is confirmed.**
  - AC1:
    - Before: `pgrep` was empty and the section 8.2 dry run printed `False`.
    - `_e2e_ui_chain_foam.py` exits 0 with `UI CHAIN FOAM: PASS (33 checks, chain 161 s)`.
    - `3d/MODEL.json` holds `"t_end": 0.0002`. `pgrep` was empty afterwards.
    - The e2e's own OUT-1 step released the three WSL scratch runs it had just created
      (`20261011-2315*/2316*`). Nothing else in `/root/blastlab_runs` was touched.
  - AC2: `_e2e_ui_view3d.py` on the real platform with my own probe:
    - G1 and G2 PASS. G3 FAILS 3 checks, then raises `AttributeError` at `:131`.
    - The probe samples every 20 ms, including while the host holds no container (the implementer's
      sampler skipped those samples). It also hooks `set_floating` and `on_window`.
    - At t = 43.182 s, `set_floating(True)`. 113 ms later `on_window` arrives with `_floating` True and
      no container, and it re-embeds.
    - 34 samples are floating with a container, and the stack shows that container. `_float_win` is
      never created.
    - No sample has the visible child off its container. The child is hidden for ~100 ms during the
      hand-back.
    - Diagnosis confirmed in code:
      - `viz3d/viewer.py:1745-1756` (`_detach`) re-reports the handle in both directions.
      - `ui/view3d_host.py:664-673` (`on_window`) and `:827-833` (`_embed`) never look at `_floating`.
      - `_e2e_ui_view3d.py:114-135` assumes the `_FloatWindow` path, which the native mount never
        takes (`:906-918`).
    - Not fixed here, per the plan. `view3d_host.py` is not in Part B's diff, so this is pre-existing.

## Fixes

None needed.

## Defects

1. **Low, not fixed.** `services/validation.py:902` and `:899-900`. A native case whose trigger gauge
   is dropped now gets B3's warning `Trigger disabled: ...`. Next to it, `_validate_trigger` still
   notes `The run ends when the wave reaches gauge 2`, or for `remap`, `Gauge 2 will write the remap
   file`. Checks contradicts itself. With `remap`, no trigger remap file is written
   (`solvers/jobs.py:65-71`). That is correct behaviour, but the note does not say it.
   Recommendation: when D13's warning fires, drop that note in the closing loop. Low, so it goes to
   parking unless the owner picks it.
2. **Medium, pre-existing, reported (B6).** Native-mount detach is undone at once. To the user, the
   Detach button greys out and the viewer stays in the host, with no re-attach note.

## Flagged points (judgement)

- B3 wording `Trigger disabled: trigger gauge G2 is dropped (see above), ...`: accept. It names G2 and
  the trigger, and it keeps out of the `will be dropped` counters.
- `does not exist (N gauge(s))` counts entered gauges: correct. N is what the user typed.
- Unnamed line edits (a comment in `test_ui_results_screen.py`, a header print in
  `test_case_validate.py`, an e2e docstring): accept. None of them is a behaviour pin.
- Old native results whose trigger came after a dropped gauge may select another row by default
  (implementer issue 3): accept. Memory only, no number moves.

## Engineering questions

- Native detach (B6): fix it in the next GUI batch? Recommended fix:
  - guard `on_window` / `_embed` with `_floating` on the native path;
  - update G3 of `_e2e_ui_view3d.py` for the native path;
  - re-measure with the probe.
- Should a dropped trigger gauge with a `remap` action be an error rather than a warning, since no
  remap file is written at the trigger? Recommendation: keep the warning, and say it in the text
  (defect 1).

## Test results

- `gate.py --changed f411d1a --deep`: 117/117 green, 27.0 min. That includes all 16 `test_gui_*` Tk
  suites, plus `test_trigger_numbering`, `test_solver_gauge_log`, `test_blast3d`, `test_bc_trigger`
  and `test_char_native_api`.
- `test_layering.py`: PASS.
- `gate.py --only regression`: byte-for-byte PASS, run last.
- WSL solve suites were not run (CLAUDE.md 8.6). The harnesses were not run (QA runs next).

## GUI screens for QA

- Setup Checks:
  - the wording `within a cell of Wall n`;
  - the 1D beyond-radius warning;
  - the trigger-disabled warning next to its stale note (defect 1).
- Setup and chain-stage Gauges node for 1D: warn, with ` · G2 dropped`.
- Run log: the wall is named. Live markers read G1 G3 G4, with the trigger on G3.
- Run gauge column in 1D.
- Results Gauges:
  - 1D rows G1 and G3, and the drop line;
  - the default row is the trigger's.
- An exported 2D animation with a gauge dropped before the trigger: the star should be on G3.
- 3D tab Detach: known failing (defect 2).

**Verdict:** Part B VERIFIED (B1-B6). No fixes were needed. One low defect is open, and one pre-existing
medium finding (B6) is confirmed.
