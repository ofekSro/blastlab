# GUI-14 Part B - verification report (depth: full)

Batch `docs/batches/2026-10-11-gui-14-backlog.md`, Part B (B1). Worktree
`C:\Users\rotem.ofek\blastlab-worktrees\gui-14`, branch `gui-14`. Checked: change `8a35381`,
report `b95fa78`, base `6d3d1ac`. Owner decision 2026-10-11: Q3 approved (only
`_e2e_gui_native_warn.py:61` and `_qa_gui_harness.py:1597` may change).

**Verdict: VERIFIED.** No fix commits. Big harnesses not run (prompt).

## B1 - (g) Native solver logs name the gauge `G<n>`, in metres - VERIFIED

| Crit | Check | Result |
|---|---|---|
| 1 | Scratch `vb1_arrays.py`, run against a temporary worktree at `6d3d1ac` and against HEAD (since removed). 2D planar, cell 0.08, gauges G1 kept, G2 in the wall, G3 at (5, 5), G4 kept; 3D smeared, cell 0.1, same pattern | HEAD logs `[warn] G2 (1.40, 0.30) m inside an obstacle - dropped`, `[warn] G3 (5.00, 5.00) m outside the domain - dropped`, `[warn] G2 (0.80, 0.60, 0.20) m inside an obstacle - dropped`, `[warn] G3 (5.00, 5.00, 5.00) m outside the domain - dropped`. Kept gauges `times`, `points` and every `pressures` array `numpy.array_equal` to base: 2D True (634 samples), 3D True (3386). Every other log line identical (18 / 19 lines). PASS |
| 2 | §8.2 dry run (worktree `settings.json`, `auto_cleanup` False), then `python -u _e2e_gui_native_warn.py` | 4/4 PASS, exit 0, 35 s. PASS |
| 3 | `gate.py --changed 6d3d1ac --deep`; then `gate.py --only regression`, last; Grep `Gauge \(\{g` in `blastlab/solvers` | 105/105 green, 24.5 min (includes `test_blast2d`, `test_blast3d` and all 16 `test_gui_*`, the Tk gate of CLAUDE.md §9). Regression byte-for-byte PASS. 0 matches. PASS |

**The changed pin can still fail.** HEAD's `_e2e_gui_native_warn.py` was copied into the base
worktree and run against the old solver: the `:61` check FAILs, exit 1. The `_qa_gui_harness.py:1597`
pin was not run. Its `N2D` case (`:868-874`) is the e2e's case except for snapshots and frames, and
`log_has` is a substring test (`:543-544`). The e2e therefore shows that the string it pins is
produced. `_qa_ui_harness.py:2154` matches `inside an obstacle`, which HEAD still prints.

**Reading the diff.** The change is to strings only. Each gauge's name is formatted before its bounds
test. A non-numeric gauge used to raise `TypeError`; it now raises `ValueError`. Both raise. No swallowed errors, no GUI-thread code and no leftovers. No non-test
code parses the old line: the `[warn]` consumers are the generic status routing at `ui/app.py:1208`
and `gui/app.py:954`.

**The comment's claim checks out.** The code comment says "as Setup and the validation warning name
it". Setup numbers its rows `enumerate(rows, start=1)` in the order they were entered
(`ui/setup_panel.py:623-625`, `ui/case_form.py:407-412`). Validation builds the same
`G<k> (x.xx, y.xx) m` (`services/validation.py:1562-1566`). Same rule, same format.

## Judged items

**G2, not the plan's G1 - the implementer is right.** Both fixtures enter
`gauges=[(0.3, 0.8), (1.4, 0.3)]` (`_e2e_gui_native_warn.py:46`, `_qa_gui_harness.py:873`).
Scratch `vb1_numbers.py` ran the exact e2e case at HEAD:
- validation: `G2 (1.40, 0.30) m inside Wall 1 - will be dropped`;
- solver: `[warn] G2 (1.40, 0.30) m inside an obstacle - dropped`;
- Run caption (`run_gauges.numbering`): `G2 dropped by the solver (inside Wall 1)`.

The plan's pin text (`backlog.md:163`) contradicts its own D9 (`:155-157`).

**Issue 1 - the T51 trigger and the live labels count kept gauges only. CONFIRMED, and wider than
reported.** Scratch `vb1_trigger.py` used gauges G1 (0.3, 0.8), G2 (1.4, 0.3) in the wall,
G3 (0.6, 0.5) and G4 (1.0, 1.0), with `trigger_gauge=3` and `terminate`. `validate_case` raises no
error; its only warning is the G2 drop.
- The native solve logs `Trigger gauge 3 (1.0010, 1.0010) m reached at t = 0.284 ms` and stops
  there - on G4's point.
- The same case with G2 kept at (0.2, 0.2) stops on G3 (0.6031, 0.5036) at t = 0.091 ms.
- The run therefore went on 3.1x longer and stopped on a different gauge, without a word.
- With three gauges (G2 dropped, trigger 3), validation is silent and the solver logs
  `Trigger gauge 3 does not exist (2 gauge(s)) - trigger disabled`.
- blastFoam indexes the gauges as entered (`solvers/foam/backend.py:1785-1814`). The same case
  therefore triggers on G3 in blastFoam and on G4 natively.
- Since B1, one native log names the drop `G2` (entered numbering) and the trigger `gauge 3` at
  G4's coordinates (kept numbering).
- The live labels (`solver2d.py:337-338`, `core/geometry.plane_gauges:114-117`) also number the
  kept list.
- `meta['trigger_gauge']` is the kept number (`solver2d.py:535`); `ui/results_gauges.py:558` reads
  it, while `ui/run_gauges.py:363` reads the entered `case.trigger_gauge`.

**Recommendation:** open a P1 row (native only). Carry each kept gauge's entered number, so the
trigger, the live labels and `meta['trigger_gauge']` all use Setup's number. Have
`_validate_trigger` warn when the trigger gauge is one the drop rule removes. First write a
characterisation test (this probe: stop at 0.284 ms vs 0.091 ms). This changes when a run stops, so
it needs the owner's approval.

**Issue 2 - `_e2e_gui_native_warn.py:63-64` can no longer fail. CONFIRMED.** Grep `Gauge \(` over
`blastlab/` finds no code that writes that text to a run log. The only hits are the Tk results
column heading `Gauge (cell)` (`gui/results_panel.py:252`), a comment, and the check itself. The
check is therefore always true. The docstring (`:4-5`) and the check name (`:60`) still quote the
old form. Severity: low, because the positive check at `:61` still pins the feature.
**Recommendation:** with the owner's approval, change it to `'G1 (0.30, 0.80) m' not in log` and
update the docstring and name in the same edit.

**Issue 3 - no fast test pins the 3D string. CONFIRMED, and it holds for 2D too.** Grepping the
tests for the solver's `- dropped` line finds only:
- `_e2e_gui_native_warn.py:61` (2D, a Tk e2e that the gate does not run);
- `_qa_gui_harness.py:1597` (2D, the big harness);
- `_qa_ui_harness.py:2154` (2D, a substring).

No fast suite would catch a regression in the 2D or the 3D line. `vb1_arrays.py` shows both are
correct today. Severity: low. **Recommendation:** add one fast check (in `test_blast3d.py` or a new
suite) that captures `hooks.log` on a tiny smeared 3D case like the probe's (20^3 cells, G2 inside a
box). Assert that the lines name `G2` and `G3` (meaning, not prose, per agent-rules). Add the same for
2D. This is a new test, so it needs the owner's approval.

## Defects

None in B1. Issues 1-3 are pre-existing or outside the approval and were left unchanged, as the
prompt directs.

## Engineering questions

- Issue 1: should the trigger number mean Setup's number in both backends (recommended), and may the
  native stop time on such a case change?

## GUI screens for QA

None directly. The new line appears in the Qt Run log and status line, the Tk Run log, the CLI
console and the model folder's `run.log`.

## Housekeeping

The temporary base worktree was removed. Its admin folder in the main repo's `.git/worktrees` held
OneDrive placeholders; `git worktree prune` could not delete them, so I removed them by path. They
are gone, and `git worktree list` shows only master and gui-14. The untracked
`docs/qa/2026-10-11-gui-14-ux.md` in the worktree is not mine and was not touched.
