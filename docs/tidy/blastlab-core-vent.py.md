# Tidy proposal: blastlab/core/vent.py
tier: A · base commit: 569361e · date: 2026-10-04

1. [unused-import] L88 `AIR_CV` - imported from `.deflagration`, never used in - APPLIED
   vent.py; no `vent.AIR_CV` / `from .vent import AIR_CV` anywhere in blastlab/
   (tests use `d.AIR_CV` from deflagration directly). Drop it from the import.
   Output risk: none.
2. [magic-number] L255-258 `handoff` `mol_weight_p` - literal 8314.46261815324 - APPLIED
   -> module constant `_R_UNIVERSAL = 8314.46261815324  # J/(kmol K); CODATA 2018
   molar gas constant x 1000, so R_specific [J/(kg K)] -> M [g/mol]`, same literal,
   same single division. Turn the misplaced Sphinx `#:` inside the call into `#`
   (text kept). Output risk: none.
3. [duplication] L195, L207, L277 `handoff` - `(m_p * prop.R + m_a * AIR_R)` is
   written three times; bind it once to a local (e.g. `mR_sum`) after L187 and
   use `mR_sum * T / p_0d`, `mR_sum * T / v`, `(mR_sum * T / v_0d) / p_0d`.
   Same operands, same parenthesisation, same order. Output risk: none.
4. [duplication] L212 `handoff` - `pp_p + pp_a` evaluated twice in one line;
   name it `pp_sum`. Same addition. Output risk: none.
5. [false-comment] L461-462 `cfd_point_in_band` - "interpolated in 1/dx" is - APPLIED
   false: L463 is a step switch at 9 cells between the two measured values.
   Reword to say so; keep "the only two this repository has, and the reason the
   range exists at all". Output risk: none.
6. [duplication] L326-327 `validity` - two identical nearest-sample `min(...)` - APPLIED
   lambdas -> private `_nearest_index(t, target)`. Same comparison sequence;
   `state.t_open + t_cfd` computed once instead of per key call, same IEEE
   value. Output risk: none.
7. [magic-number] L460, L463 `cfd_point_in_band` - 0.72/0.90 and 0.7227/0.8102 - APPLIED
   -> module constants (`_CD_RANGE`, `_CD_EFF_6_CELLS`, `_CD_EFF_12_CELLS`,
   `_CD_CELLS_SWITCH = 9`) with a source comment pointing at
   `tests/_e2e_vent_verify.py`, as the docstring already does. Values identical.
   Output risk: none.
8. [magic-number] L338 `validity` - fallback Cd `0.8` -> `_CD_FALLBACK = 0.8` - APPLIED
   with comment "= `deflagration.simulate`'s default `cd`". Output risk: none.
9. [docstring] L104-109 `ChamberState` - list field units: p Pa, T K, m_p/m_a kg, - APPLIED
   E J, volume m^3, rho_* kg/m^3, e_mix J/kg, R_p J/(kg K), mol_weight_p g/mol,
   t_open s, *_shift dimensionless fractions. Output risk: none.
10. [docstring] L177-184 `handoff` - add args (result = `deflagration.simulate` - APPLIED
    dict, prop, mode, p_burst Pa, volume_cfd m^3), return, the three
    ValueErrors, and that `p_amb` is accepted but not used (see EQ 1).
    Output risk: none.
11. [docstring] L293-320 `validity`, L418-424 `energy_check`, L487 - APPLIED
    `summary_line` - units of `t_cfd` (s) / `vent_area` (m^2); `tol` is a
    relative tolerance on E (J); `val` is the dict `validity` returns.
    Output risk: none.
12. [import] L336 `validity` - function-local `from .deflagration import - APPLIED
    _vent_mdot`; `.deflagration` is already imported at L88, so move the name
    into that import. No new import-time effect. Output risk: none.

Not touching: splitting `handoff`/`validity` (long, but linear and mostly WHY
comments + message text); f-strings without placeholders at L222-245 (cosmetic,
string-identical either way); `_R, _cp, _g` unpack at L216 (already marked unused).

Engineering questions:
1. L176 `handoff(p_amb=P_AIR)` never reads `p_amb`, and `validity` L338 passes
   a hard-coded `P_AIR` as back pressure to `_vent_mdot` - a run at non-standard
   ambient (`simulate(p_amb=...)`) gets its drain time at sea-level ambient.
2. L463 Cd is a step at 9 cells, flat beyond 6..12; any `cells_across` > 12 is
   reported at Cd 0.81. Intended, or should it interpolate as the comment said?
3. L327 if `t_open + t_cfd` lies past the last 0-D sample, `j` clamps to the
   end and `burn_fraction` (labelled an upper bound) is silently truncated.
