# Tidy proposal: blastlab/core/assessment.py
tier: A · base commit: 569361e · date: 2026-10-04

1. [unused-import] L29 `scenario as _scenario` - no use in the file, and no - APPLIED
   `assessment._scenario` access anywhere in `blastlab/` (grep: 0 hits; the
   case builds its scenario through `models/hd13_case.py`, which imports
   `core.scenario` itself). Drop it from the import line; keep
   `deflagration, thermal, unconfined`.
   Output risk: none.
2. [docstring] L406-408 `run()` - document the bundle: raises `ValueError` - APPLIED
   (joined `rep.errors`) when `validate` fails; keys always present
   (`case, prop, report, confined, unconfined, thermal, radiation, sdof,
   component, band, sensitivity, sensitivity_note, verdict, qd`, with
   `sdof/component/verdict` always None per HD1-16), keys present only
   conditionally (`fireball` when energy > 0, `residual` when `Ru_pa > 0`
   and a thermal result exists); units of `sensitivity` tuples (MPa, s, -).
   Output risk: none.
3. [docstring] L62-63 `validate()` - say it returns a - APPLIED
   `ValidationReport`, returns early (errors only) when the propellant
   cannot be built, that errors block `run`, and that warning order is the
   order shown in the Setup card.
   Output risk: none.
4. [long-func] L232-326 `validate` vent-stage block - move verbatim into
   `_validate_vent_stage(case, err, warn, note)`, called at the same point
   (it is the last block, so append order of errors/warnings/notes is
   unchanged). Keeps every HD1-3f / MIN_VENT_CELLS_LOAD comment with it.
   Output risk: none (same calls, same order, same strings).
5. [long-func] L101-131 `validate` confined block - move verbatim into
   `_validate_confined(case, prop, err, warn, note)`, called at the same
   point; `wants_confined` stays a local in `validate` only if still used
   (it is not used after L102).
   Output risk: none (pure relocation, append order preserved).
6. [naming] L285 / L315 `cells` - one local means first the vent's - APPLIED
   (nx, ny) cell tuple, then the integer domain cell count. Rename the
   second to `n_cells` (L315-318). Product loop untouched.
   Output risk: none.
7. [magic-number] L307 `0.1` - module constant - APPLIED
   `_ROOM_VOLUME_TOL = 0.1  # 0-D vs meshed room; core/room.py alignment
   can move the cavity by up to ~10 %`. Same value, same comparison.
   Output risk: none.
8. [magic-number] L164 `20` - module constant - APPLIED
   `_MIN_PACKAGE_COHORTS = 20  # flame-spread ramp converges by n = 20
   (scenario.windows); see deflagration._COHORT_TOL`. Same value.
   Output risk: none.
9. [nesting] L204-209 `from . import qd as _qd` inside the per-row `try`
   of the loop - hoist the import above the loop, guarded by
   `if case.qd_criteria:` so no new import happens on an empty list.
   `except (TypeError, ValueError)` stays around the constructor only.
   Output risk: none (module import cached; ImportError was never caught).

Not touching: the long warning strings and the 266-line `validate` body
beyond items 4-5 (their order is the user-facing report); the always-None
`sdof/component/verdict` keys (downstream `is None` checks, HD1-16);
`replace` and the `hd13_case` re-exports (public import paths).

Engineering questions:
1. L120 - the burn-law range warning fires only when the chamber cap is
   BELOW `p_valid_min`; a cap above `p_valid_max` (extrapolation above the
   data) is silent. Intended?
2. L514-515 - for `confinement='both'` the fireball mass uses the
   unconfined burnt fraction, not the confined `Z[-1]`. Which governs?
3. L533 - `case.qd_criteria` is iterated without the `or ()` guard used in
   `validate` (L204); a JSON case with `qd_criteria: null` plus standoffs
   would pass validate and raise TypeError in `run`.
