# Engineering questions

Questions raised by `/todo` batches that need the owner's decision. Each names the
batch it came from; the batch reports under `docs/batches/` hold the full evidence.
Nothing here has been acted on: numbers, thresholds and defaults stay as they are
until the owner decides.

---

## 2026-09-24 · batch `hd1-3d-close` (HD1-3d, the 3D answer)

Sources: [implement report](batches/2026-09-24-hd1-3d-close.implement.md),
[verify report](batches/2026-09-24-hd1-3d-close.verify.md).

1. **The wall load has no reflection and no drag in it** - tracked as `HD1-13` in
   TODO.md. Only the room is meshed (`build_vent_case`: `obstacles = m['boxes']`, all
   in x 1.0-6.0 m), so the gauges at x = 10 m sit in free air and the SDOF was fed
   side-on pressure. UFC 3-340-02 para. 2-15.3.2 (printed p. 65, `=== page 141 ===` in
   the text sidecar) loads a front wall with the reflected pressure Pr (Fig. 2-15) and,
   after clearing, `P = Ps + C_D q` with C_D = 1 (Eq. 2-9). On the jet axis (G1) the
   probes give 1/2 rho |U|^2 = **114.6 kPa at 24.71 ms** (|U| 672 m/s, rho 0.508 kg/m3)
   while the static trace reads -31.5 kPa; max(static + q) = 99.6 kPa, 2.4x the 41.47 kPa
   static peak (an incompressible estimate - at 672 m/s compressibility matters). G2
   and G3 peak at q = 17.7 and 16.4 kPa. **μ = 0.3027 and C10's "survives" may be
   unconservative.** Mesh the wall and read its face, or apply Pr and C_D q to the
   trace? C10 passes as committed and was not redefined.

2. **Disk use is not bounded by `n_snapshots`.** The writer's interval0 = 1.033e-5 s,
   with the adaptive controller's clamp [interval0/4, 8 interval0], cannot reach its own
   40-60-write band in a 30 ms window: 748 writes (340 at the floor, 337 at the
   ceiling), each kept reconstructed (~130 MB) and again decomposed - **172.96 GiB**
   for the 6-snapshot run, 191.63 GiB for the 30-snapshot attempt. Even at the ceiling
   a 30 ms window means >= ~363 writes. Any rerun of this case, or `HD1-14` (the 24-cell
   `Cd` point), needs ~190 GB unless the write sizing changes. The script comment that
   blamed snapshots was corrected in `3798cec`; the `1c9b238` commit message carries
   the same wrong cause and cannot be amended.

3. **The app and every other tool read different settings files.** Microsoft Store
   Python virtualizes AppData: `python` resolves
   `%APPDATA%\blastlab\settings.json` (27 B, `{ "auto_cleanup": false }`, 2026-09-10) to
   `%LOCALAPPDATA%\Packages\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\LocalCache\Roaming\blastlab\settings.json`
   (444 B, written 2026-09-24 08:21, **auto_cleanup true, 150 GB, 14 d, keep 10**).
   Editors, PowerShell and the Read tool see "false"; the app sees "true". With a
   426.79 GiB corpus, a GUI start today deletes one run (`20260921-123600_2d_p41784-01`,
   30 KB). The judged run is safe only while fewer than 10 newer runs exist. Also: the
   CLAUDE.md §8.2 check `env.auto_cleanup(settings.load())` is not a check - it deletes
   whatever the policy selects before returning. A dry run is `env.cleanup_policy` on
   the listed sizes and mtimes. Which file should govern, and should §8.2 say so?

4. **C8 is narrow.** It looks only at G1, only later than t_peak + 4 ms, and only at
   half the peak. G1's peak is itself a second rise, 8.8 ms after arrival, which C8
   does not examine; the `x_hi` boundary is 2 m behind G1. The full traces are
   committed (`docs/hd13/vent3d_gauges_3d.txt`) for a reader to judge.

5. **The negative phase is still open at 30 ms.** All three gauges sit 22-43 kPa below
   ambient from ~21 ms and are still -22 to -25 kPa at 30 ms; the SDOF sees the record
   only to 30 ms.

6. **The arrival rule** (first sample above 1.1 x ambient, i.e. 10.13 kPa over) lands
   1.19 ms after the first disturbance on this gradual rise (G1 first exceeds 100 Pa at
   9.127 ms). Counting the positive phase from the first positive overpressure raises
   the impulse by 1.1 % (G1, 326.27 Pa s), 1.7 % (G2) and 2.1 % (G3); a weaker gauge
   would get no arrival and no positive-phase impulse at all. A definition note - no
   verdict attaches.

7. **A judgement taken in the batch, for the owner to overrule.** The plan required
   the run's rendered dicts to be identical to a fresh render, or to differ only in
   `decomposeParDict`. They differ in one line: the controlDict's top-level
   `writeInterval` (1.033114042e-05 rendered, 8.264912335e-05 in the run). Both agents
   traced it to the runner's own run-time rewrite (`runner.rewrite_control_entry`,
   the adaptive controller's 8x ceiling; applying the runner's `sed` reproduces the
   run's file byte for byte) and treated the run as the same case.

8. **Low defects noted, not fixed.** The record's "~141.7 MB each" for the decomposed
   copies is not the per-write mean (~117.6 MB). In `_e2e_vent_3d.evaluate`,
   `traces[0]` raises IndexError on a run with no probes - pre-existing, inside the
   frozen C6-C13 block, and it fails loudly rather than silently.

---

## 2026-09-24 · batch `hd1-wall-load` (HD1-13 route (b), HD1-15)

Sources: [implement report](batches/2026-09-24-hd1-wall-load.implement.md),
[verify report](batches/2026-09-24-hd1-wall-load.verify.md).

1. **BOUND bounds the load, not the SDOF response.** The envelope max(G1, plane
   maximum) is at least G1's E at every sample and carries more impulse (2095.6 against
   2033.1 Pa s). Yet it gives the 200 mm example panel a lower response than G1's trace
   alone: T0 mu 0.4500 against 0.4672, and T1 0.6426 against 0.6513, at gamma 1.24.
   The plane-max trace, sampled only at writes, behaves the same way. A dynamic SDOF
   can respond less to a load that is larger at every instant. **Any wall check should
   therefore run the SDOF on each delivered trace (G1 and plane maximum, both gammas,
   T0 and T1) and take the worst response.** The rule's wording ("upper bound on the
   load") holds. The plan's rationale for P1 ("a uniform load ... loads the SDOF more")
   does not.

2. **blastlab cannot read the `0/` fields it writes itself.** The writer closes lists
   with `);` and the reader wants a bare `)`. Chamber and profile stages therefore lose
   their t = 0 frame silently. Tracked as `P1-7` in TODO.md. Which side to fix is the
   owner's decision: the reader is GUI-visible and needs QA; the writer moves goldens.
   The same defect made Step 2's first attempt print `NOT ESTABLISHED - Step 2 cannot be
   run read-only`. That attempt aborted at t = 0, before any plane number existed, and
   the re-run after fix `53f87ad` changed no rule or threshold. The verifier judged the
   re-run legitimate. The committed record does not mention attempt 1; the commits do.
   Should the record say so?

3. **Two committed WSL suites fail, identically at `7dd2446`.**
   `test_foam_wsl_resume.py` has not run since `9b9a039` (2026-09-19), because its stub
   spec lacks `init_state`; this is `P2-10`. `test_foam_postmortem.py`'s peak-map check
   fails deterministically at 2.90e-01, 620 against 632 samples; this is `P2-11`, cause
   undetermined. Fixing either means editing a committed test (§9).

4. **The T1 hold drives every T1 response.** Every T1 peak falls after the 30 ms record,
   which covers only 0.198 of the drain time. Any meshed-wall run (route (a)) wants a
   longer window, and with `HD1-15` its disk cost is ~8 GB.

5. **Artefacts at G2 and G3.** Their T0 peaks come after the record, because sdof
   releases a suction E (-17.9 / -7.5 kPa at 30 ms, gamma 1.24) to zero there. Their T1
   applies 205 kPa where the local E is negative, which gives mu 1.57 at G2. This is
   conservative by design.

6. **Observations.** The mapping check tells G1's cell from its y-mirror only through
   U, because the case is symmetric about y = 6. At the peak, the jet core sits at
   z = 1.25 m, 0.15 m below the opening's axis.

7. **The plan's safety table was wrong about P1-5.** `_resume_start_time` walks back on
   every resume, not only on AMR. The purge interaction this caused is fixed in
   `b87f76f`.

8. **Low defects, not fixed.**
   - `DecomposedPurge.run` logs "retrying at the next poll" after a failed final sweep,
     but no poll follows. It fails safe.
   - `read_probes` aligns U and rho with p by row count, not by time. This guard
     predates the batch, and the evidence's times are identical.
   - The guide citation in `purge_active` pointed at 11.2-11.3, p. 112, which covers
     load balancing. The orchestrator corrected it to sec. 16.9, p. 136 (a balanced case
     makes the standard reconstructPar fail fatally). It is a comment only.
   - **The validation and the writer read `write_budget` differently.**
     `_validate_write_budget` refuses a bool, a non-integer and anything below 2.
     `writer.write_budget_of` passes the value through `int()`, so `True` becomes 1,
     `12.7` becomes 12 and `'60'` becomes 60. It is safe only on paths that run
     `validate_case` first; a headless call that skips validation gets the coerced
     value. Should `write_budget_of` return 0 for anything that is not a positive whole
     number? That is a behaviour change, so it needs one new test.
   - The validation warning "below 4 x n_snapshots ... the writer's own rule" ignores
     the writer's clamp `min(60, max(40, 4n))`. At n_snapshots = 20 it warns for any
     budget below 80, while the default writer uses 60. It is a note only; the
     threshold is frozen.
   - `_e2e_foam_write_budget.du_sb` hard-codes `'Ubuntu'` instead of `env.WSL_DISTRO`,
     omits `stdin=DEVNULL` / `CREATE_NO_WINDOW`, and does not check `returncode`
     before parsing. Behaviour is the same on this machine, but a fix needs a WSL
     rerun.
   - The Qt form rebuilds `Case3D` and drops `write_budget` on save. Exposing the
     field in the GUI is backlog.
   - **Fixed by the orchestrator:** `test_vent_wall.py`'s "a scan that fails means not
     read-only" was flaky, failing about 1 in 10 runs. Its fake scanner raised only on
     its 4th call, which needs the 1 ms timer to fire twice during a tiny read. It now
     raises from the 2nd call, i.e. the timer's first scan or the after-scan: 30 of 30
     runs pass. The check's condition is unchanged. The test is new in this batch.

---

## 2026-09-24 · `/refactor` review - UX review

Source: [docs/UX_REVIEW.md](UX_REVIEW.md) section 6 (E1-E5). Static reading only; the
GUI was not launched.

1. **"kg TNT" on a charge that is not TNT.** The form and the exported figures label the
   charge "[kg TNT]" (`setup_spec.py:371,384,459,462`, `output/plots.py:56-57`), but
   `core/case.py:494-498` sizes it with the *selected material's* `rho0`. With ANFO,
   5 kg of ANFO is shown as "5 kg TNT". Is the field the material mass or a TNT
   equivalent?
2. **The native solver ignores the material the user picks.** In native mode the form
   always sends `'TNT'` (`case_form.py:468/506`), while `core/case.py:548-566` and the
   N11/T46 note say the native solvers take their JWL set from the shared table. Either
   the comment or the form is wrong. Honouring the choice changes numbers; hiding the
   row changes the form. Both are the owner's decision.
3. **The "Vieille a" override has no unit** (`setup_spec.py:241`, `case_form.py:184`).
   In r = a·p^n the unit of `a` depends on the units `n` was fitted in. A literature
   value in mm/s/MPa^n could be off by orders of magnitude with no warning.
4. **HD 1.3 turns an explicit 0 into a default.** This applies to discharge coefficient,
   wall temperature, collapse rotation, cohorts and samples. Does the HTML report print
   the value actually used?
5. **No Z column next to the gauge results.** Without Z = R/W^(1/3) the user cannot see
   whether a gauge is inside the Kingery-Bulmash range. Which W to use depends on item 1.

---

## 2026-09-24 · `/refactor` review - architecture review

Source: [docs/ARCHITECTURE_REVIEW.md](ARCHITECTURE_REVIEW.md) section 6. None of these
is part of the migration plan, and none affects the byte-pinned baselines.

1. **C4 E0: the comment and the table don't match.** The comment in
   `solvers/foam/materials.py:126-129` says E0 = 9.0e9 = 1601 × 5.56e6, but the product
   is 8.90e9 J/m³, 1.1 % lower. Either `e0` should be 5.62e6 or the 9.0e9 is rounded.
   The table matches `blastfoam_toolkit/docs/jwl_parameters.md:195-198`; check it against
   the guide's freeField tutorial. Affects blastFoam C4 runs only.
2. **The preview charge circle uses TNT density for every material**
   (`output/preview_draw.py:117`, `viz3d/geometry.py:54`). For ANFO the real radius is
   24 % larger. Display only; the solver and the writer use the material. Related to
   item 1 of the UX section.
3. **Two charge-radius helpers fall back to TNT density when `rho0` is omitted**
   (`core/case.py:494`, `core/refine.py:120`). Not wrong for TNT, but a trap for any new
   caller.
4. **The arrival rule for far gauges.** The rule is 1.10 × ambient
   (`output/gauge_summary.py:22-23,53`). For gauges with Z ≳ 4 (1 kg), `arrival_ms` reads
   late or `NaN`, and the positive-phase impulse starts late. The CSV doesn't say the
   value depends on the threshold. This is the same question as item 6 of
   `hd1-3d-close`, from another direction.
5. **SDOF K_LM for fixed supports.** `core/sdof.py:92-99` has only an elastic range (0.77)
   and a plastic range (0.66). Biggs Table 5.3 / UFC 3-340-02 Table 3-12 give fixed-fixed
   beams under uniform load an elasto-plastic range (K_L 0.64, K_M 0.50, K_LM 0.78) in
   between. The text sidecar doesn't carry the table values, so confirm them on the
   printed PDF page, and document how `average` is formed.

---

## 2026-09-24 · `/refactor` phase 0 (characterisation tests, `389247d`)

Source: the arch-refactorer's phase 0 report. Noticed while pinning outputs; nothing
changed.

1. **The HD 1.3 sensitivity band does not contain the nominal result.** On the starter
   case with `sensitivity=True`, the nominal SDOF ductility is 0.1164, but the band's
   ends are 0.0509 (low) and 0.1049 (high). The verdict "survives_across_band" is
   therefore taken between two ends that bracket everything except the nominal point.
   Worth checking `core/sensitivity.band` and `structural_verdict`; the heat-loss (h_c)
   axis is a suspect.
2. **`validate_case` reports a different grid from the one the native solver builds.**
   For the native 2D case, validation reports dx 0.010542 and 17,063 cells (113 × 151,
   rounded down). The solver builds 114 × 152 = 17,328 cells at dx 0.010526. So the
   cell-cap check undercounts by ~1.5 % in 2D, and probably more in 3D. Worth deciding
   before phases 3-4 split `validate_case`, because the split pins the current numbers.
3. **The HD 1.3 starter case is a weak check.** Its confined peak is 102.35 kPa absolute
   (~1 kPa over ambient), with ductility 0.12 (quasi-static). The `cli_hd13.py` docstring
   says the assessment finishes "in under a second". The starter case took ~42 s here,
   and ~20 min with the band on.
4. **Two existing tests are weaker under pytest than they look.** `test_vent_wall.py`'s
   `test_evidence/test_tails/test_step2_driver` take arguments, so pytest reports 3
   "fixture not found" errors. `test_refine.py`'s `check()` only appends to a list, so
   its 10 pytest functions cannot fail. Fixing either edits a committed test (§9).

---

## 2026-09-24 · `/refactor` phase 1 (the material table moves to `core/materials.py`, `880516e`)

Source: the arch-refactorer's phase 1 report. The table was moved byte for byte; nothing
here was changed.

1. **The `Pcj` comment overstates the fit.** It says `rho0*vDet^2/4` "lands within ~7 %
   of every row". That holds for five rows (ratios 0.93-1.007), but for ANFO the ratio
   is 0.861 (4.30e9 against the table's 5.0e9, a 14 % gap). Check ANFO's `Pcj` against
   `blastfoam_toolkit/docs/jwl_parameters.md`.
2. **The `Afterburn` docstring disagrees with CLAUDE.md §7.** The docstring puts the
   pure-JWL gap at "~25 %". The TNT comment's own no-afterburn ratios (0.85-0.89) put it
   at 11-15 %, and CLAUDE.md §7 says ~13 %. It also cites "ROADMAP N3", which may not
   exist after the 2026-09-21 documentation consolidation.
3. *(Checked, agrees:)* the TNT row matches `constants.JWL_TNT` field for field on the
   seven JWL keys.

---

## 2026-09-24 · `/refactor` phase 2 (`models/` package, `6d7a13d`)

Source: the eng-code-simplifier's phase 2 report. Nothing changed.

1. **An HD 1.3 case file with a misspelled field loads silently at the default.**
   `models/case.py` (blast cases) refuses unknown keys, but
   `models/hd13_case.case_from_dict` drops them silently and never checks `version`. A
   typo in a DeflagrationCase JSON (for example a wall or vent parameter) gives an
   assessment of a different case with no warning. Should the HD 1.3 reader refuse
   unknown keys, as the blast reader does? That is a behaviour change, so it needs a test.
2. **`material_rho0` returns None on `KeyError`, `ImportError` or `AttributeError`.** A
   broken import of `core.materials` would quietly fall back to TNT density in the
   preview instead of failing. Low risk, but it hides a real fault.

---

## 2026-09-24 · `/refactor` phase 3 (`services/validation.py`, `7a89030`)

Source: the arch-refactorer's phase 3 report. Moved verbatim; nothing changed.

1. **The ambient sound speed is defined three times.** `validate_case` recomputes
   `c_air = sqrt(1.4*101325/1.225)` in the 1D and in the 2D/3D safety-cap warnings, next
   to the module constant `C_AMB_AIR`. The values agree today, but a change to one would
   not reach the others.
2. **`_charge_radius` return type.** The 2D planar branch returns `np.float64`, and the
   other branches return a Python float. Harmless in arithmetic, but visible in JSON or
   repr. It still defaults to TNT's 1630 kg/m³ (see the architecture-review item 3).
3. **A fourth sound speed.** The fixed-time-step Courant check hard-codes
   `2.0 * 340.3` and says "~680 m/s" in its message, while every other stop condition
   uses `C_AMB_AIR` (340.294 m/s). The difference is negligible, but it is one more
   source for the same quantity (see item 1).
4. **AMR disk note: 60 against 155 bytes per cell per write.** The AMR note assumes
   "~60 B per cell per write", but `BYTES_PER_CELL_WRITE = 155` was measured on HD1-3d
   for static runs. Either they are meant to differ (AMR writes fewer fields?) or one
   is stale. It matters for the disk estimate, given the ~190 GB runs in `hd1-3d-close`
   item 2.
5. **The "Charge cells" note can vanish silently.** A `ValueError`, `ZeroDivisionError`
   or `IndexError` in `set_mass_fraction` sets n_set = 0, and the note that reports what
   fraction of the charge blastFoam marks disappears with no message.

---

## 2026-09-25 · `/refactor` phase 4 (`validate_case` split, `12e5435`)

Source: the eng-code-simplifier's phase 4 report. A byte-identical dump over ~100 cases
proves no behaviour changed; these were noticed on the way.

1. **Are AMR runs serial or parallel?** A comment in the AMR branch of
   `_validate_refinement` says "T42/N16-b: AMR runs in parallel; the ingest reads
   processor*/ directly", and `_validate_write_budget` speaks of "a parallel AMR run".
   CLAUDE.md §7 says AMR runs are serial (`reconstructPar` cannot follow a changing mesh).
   One of them is out of date.
2. **Extra charges refine the grid when the main charge would not.** The main charge
   skips dx refinement under `foam and charge_refine == 'zone'`, but extra charges
   refine dx whenever AMR is off, even in 'zone' mode. Intended, or should extra charges
   follow the same rule?
3. **A second copy of the sphere-radius formula.** `_validate_1d` computes the charge
   radius itself instead of calling `_charge_radius`. It is correct (1D uses `charge_kg`,
   not `case.charge`), but it is another place where the formula could drift (see the
   architecture-review item 3).

---

## 2026-09-25 · `/refactor` phase 5a (`models/fields.py`, `8a3f486`)

Source: the arch-refactorer's phase 5a report. The Qt form's behaviour is pinned as is.

1. **The GUI uses the stale AMR thresholds.** `models/case.py:135-149` re-tuned the
   default `amr_refine`/`amr_unrefine` to 0.2/0.1 on 2026-09-10; its own comment records
   the sweep (0.4/0.2 gave -11.8 % gauge error, 0.2/0.1 gave -3.9 %). But 0.4/0.2 is
   still used in:
   - the Qt form defaults (`ui/setup_spec.py:118-119`);
   - the Tk form defaults (`gui/forms.py:505-506`);
   - the value both forms use when AMR is off, and the `set_case` fallback (now in
     `models/fields.py`);
   - the `getattr` fallback in `core/refine.py:1053-1054`.

   **So a GUI user who switches AMR on gets the thresholds with ~12 % gauge error**
   unless they type new ones. Should the forms default to 0.2/0.1?
2. **Loading a case into the Qt form with AMR off rewrites its AMR fields.** For
   `tests/cases/native_2d_small.json`, `amr_estimator` goes from `densityGradient` to
   `Lohner` and `amr_refine`/`amr_unrefine` go from 0.2/0.1 to 0.4/0.2. No effect on a
   run while AMR is off, but a file saved from the GUI no longer matches the one loaded.
   It follows from item 1.
3. **A profile-initialised 2D case with `charge=None` cannot be read back.** `set_case`
   writes `''` into the charge box, and `get_case` then refuses it with `'charge' is not
   a number: ''`, although profile initialisation does not use the charge.
4. **HD1.3 form: a blank Samples or Cohorts box is an error** (`'Samples' is not an
   integer: ''`), while the code's `or 1000` / `or 1` suggests a blank was meant to fall
   back to the default.
5. **A negative charge in 2D breaks the live preview** (found by the post-5a QA,
   `docs/qa/2026-09-25-phase5a/QA_REPORT.md` section 4). `charge_radius()` of a negative
   mass is complex, and `core/refine.py:115` `effective_dx()` then raises
   `TypeError: '>' not supported between 'float' and 'complex'` from
   `ui/setup_panel.py:264` `update_preview()`. The event loop swallows it: no crash, just
   a stale preview. Validation still refuses the run. This is pre-existing code, not
   phase 5a; the baseline tested a negative charge in 1D only. It is a bug rather than an
   engineering question: a guard for mass <= 0 in the preview path (or in
   `charge_radius`) is a behaviour change, for TODO.md.

---

## 2026-09-25 · `/refactor` phase 6 (`services/exports.py`, `b980def`)

Source: the arch-refactorer's phase 6 report. Nothing changed.

1. **The report compares a ground burst with free-air Kingery-Bulmash.**
   `output/report.py` `kb_rows` compares the gauge peaks with the free-air KB table.
   It skips the comparison only for obstacles, extra charges and planar 2D, and never
   checks the boundary conditions. So an axisymmetric case with a reflecting ground
   (`y_lo='reflect'`, a height-of-burst case) and no obstacles is compared with
   free-air values, and the ratio reads high: a reflected or Mach-stem peak against a
   free-air one. Should the comparison be skipped there, or switched to the surface-burst
   curve (hemispherical, 2W) when the charge sits on the ground?
2. **The report footnote says "see ROADMAP N3", and no ROADMAP file exists.** It is the
   same dead reference as in the `Afterburn` docstring (phase 1, item 2).

---

## 2026-09-25 · `/refactor` phase 7 (`services/hd13.py`, `61ab709`)

Source: the arch-refactorer's phase 7 report. Nothing changed.

1. **"Blast negligible: False" at Mach 0.0917.** On the starter case the CLI prints
   "unconfined expansion Mach 0.0917, blast negligible: False", and the report says
   "Blast negligible: no". A Mach number that low looks like it should count as
   negligible. Check the threshold and the flag logic in the unconfined model.
2. **The whole burn is flagged outside the calibration window.** The confined peak is
   0.102 MPa (~1 kPa overpressure) against the 5.53 MPa closed-vessel limit that
   validation quotes. That is plausible for a well-vented case, but the report marks
   "the whole burn" as outside the calibration window. Is the window defined in
   pressure terms that a vented case can never reach? (This connects to phase 0 item 3:
   the starter case is a weak check.)
