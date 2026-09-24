# Engineering questions for the owner

A running list of suspected engineering issues (coefficient, unit, validity range,
meaning of a quantity) raised by the review and refactor agents. **Reported, not
fixed:** no agent changes any of these; each waits for the owner's decision.

Each entry names its source. The detail and file/line references are in the source
document.

## From the UX review, 2026-09-24 (`docs/UX_REVIEW.md` section 6)

- [ ] **UX-E1. "kg TNT" on a charge that is not TNT.** The form and the exported figures
  label the charge "[kg TNT]", but `core/case.py` sizes it with the *selected
  material's* density. So with ANFO, 5 kg of ANFO is shown as "5 kg TNT". Is the
  field the material mass or a TNT equivalent?
- [ ] **UX-E2. The native solver ignores the material you choose.** In native mode the form
  always sends `'TNT'` (`case_form.py:468/506`), while `core/case.py` and the N11/T46
  note say the native solvers take their JWL set from the shared table. Either the
  comment or the form is wrong. Fixing it changes numbers, so it needs your decision.
- [ ] **UX-E3. The "Vieille a" override has no unit.** In r = a·p^n the unit of `a`
  depends on the units `n` was fitted in. A literature value in mm/s/MPa^n could be
  off by orders of magnitude with no warning.
- [ ] **UX-E4. HD 1.3 turns a zero input into a default.** An explicit 0 for discharge
  coefficient, wall temperature, collapse rotation, cohorts or samples becomes a
  default. Does the report print the value actually used?
- [ ] **UX-E5. No Z column next to the gauge results.** Without Z = R/W^(1/3) the user
  cannot see whether a gauge lies inside the Kingery-Bulmash range. Which W to use
  depends on UX-E1.

## From the architecture review, 2026-09-24 (`docs/ARCHITECTURE_REVIEW.md` section 6)

- [ ] **AR-1. C4 E0: the comment and the table don't match.** The comment in
  `solvers/foam/materials.py:126-129` says E0 = 9.0e9 = 1601 × 5.56e6, but the product
  is 8.90e9 J/m³, 1.1 % lower. Either `e0` should be 5.62e6 or the 9.0e9 is rounded.
  Check against the guide's freeField tutorial. Affects blastFoam C4 runs only.
- [ ] **AR-2. The preview draws the charge circle with TNT density for every material.**
  See `output/preview_draw.py:117` and `viz3d/geometry.py:54`. For ANFO the real radius
  is 24 % larger. Display only; the solver uses the material. Related to UX-E1.
- [ ] **AR-3. Two charge-radius helpers fall back to TNT density when `rho0` is omitted.**
  See `core/case.py:494` and `core/refine.py:120`. Not wrong for TNT, but a trap for any
  new caller.
- [ ] **AR-4. The arrival threshold is 1.10 × ambient** (`output/gauge_summary.py:22-23,53`).
  For far gauges (Z ≳ 4 for 1 kg), `arrival_ms` reads late or `NaN`, and the
  positive-phase impulse starts late. The CSV doesn't say the value depends on the
  threshold.
- [ ] **AR-5. SDOF K_LM for fixed supports.** `core/sdof.py:92-99` has only an elastic
  range (0.77) and a plastic range (0.66). Biggs Table 5.3 / UFC 3-340-02 Table 3-12 give
  fixed-fixed beams under uniform load an elasto-plastic range (K_LM 0.78) in between.
  Confirm the value against the printed table, and document how `average` is formed.
