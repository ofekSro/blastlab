# Batch 2026-09-24 `hd1-wall-load` - verifier report

Saved by the orchestrator from the verifier's hand-back (BASE 7dd2446, implementer
HEAD 0ac8217, after the fix b87f76f).

**Verdict: VERIFIED, ready for QA - no GUI screen touched, so no real-window QA.**
HD1-13's BOUND reproduced independently (own raw-probe parse; own binary parse of
three plane writes). HD1-15 works after one fix commit for two purge defects. Two gate
failures remain and fail identically at 7dd2446 (pre-existing -> TODO). One
engineering point for the owner: BOUND bounds the load, not the SDOF response.

## Per task

**A1 `core/wallload.py` - VERIFIED.** Branches meet at M = 1: pitot = isentropic =
((g+1)/2)^(g/(g-1)) to 1e-15 (gamma 1.24, 1.40). Textbook pitot: p02/p1 = 5.640441 at
M = 2 (5.6404), 12.0610 at M = 3; isentropic M = 2 7.8244. Reflection: Cr 2.0000009 at
ps = 1e-6 p0, 7.99996 at 1e6 p0, 8.0000000 at 1e9 p0; gamma 1.24 strong limit 11.333 =
(3g-1)/(g-1); R equals UFC's 2Pso(7P0+4Pso)/(7P0+Pso) exactly; Cr 2.5316 / 2.6639 /
2.9766 at 10 / 12.8 / 20 psi. Low-Mach limit, Appendix 2A anchors, gamma monotonicity,
`wall_load`, `extend_with_tail` - PASS. Imports numpy + `.constants` only; REGRESSION,
no-VTK, no-pyplot green. Every UFC page marker in the docstring checks out (2-15.3.1
page 140 / p. 64; 2-15.3.2, Eq. 2-8, 2-9, C_D = 1 page 141 / p. 65; Fig. 2-15 page 166 /
p. 90; Fig. 2-193 page 344 / p. 268; Appendix 2A pages 486, 487, 501), and so do paras
4-9.1 / 4-9.2 / 4-9.3 (2 / 6 / 12 deg).

**A2 Step 1 - VERIFIED.** (a) Pre-registration PASS: the rule at bf8d89d equals the
plan's fenced block at 7dd2446 byte for byte (94 lines; only line 2, `<date>` ->
`2026-09-24`); sha256 9a7c2678...f842f unchanged; 0e8583a touches only wallload.py and
test_wallload.py and opens nothing from the evidence; the implementer's only scratch
file older than the rule (13:13) uses synthetic states; rule 13:26:04 < first E on the
evidence 13:37 < record 14:02:45. Probe velocities PASS; C10 control reproduced (mu
0.3027, theta 0.154 deg, dynamic); record contents PASS; `_e2e_vent_3d.py` diff empty.

**A3 Step 2 - VERIFIED.** Read-only PASS (fingerprints identical, the record's and the
verifier's). Mapping check PASS against the verifier's own probe parse at all 267
writes after 8 ms: worst p 4.81e-6, rho 4.18e-6, U 4.28e-6 at cell (99, 59, 13). The
plane-max SDOF reproduced. The plane maximum is never below G1's cell E (min
difference 0 Pa), up to 1.83x. Observation: Step 2's first attempt (13:48) printed
`NOT ESTABLISHED - Step 2 cannot be run read-only`, because the script could not parse
blastlab's own `0/p` (writer `);` vs reader bare `)`); it aborted at t = 0 before any
plane number; fix 53f87ad changed no rule text or threshold; E(0) = 0. Judged a
legitimate re-run. The committed record does not mention attempt 1 (commits 53f87ad
and 9889c54 do).

**A4 the record - VERIFIED.** The final line is printed by `outcome_line`; the
verifier's own implementation of the table also gives BOUND, and `outcome()` maps all
16 combinations correctly; every number matches; no impulse, arrival, mu or theta
carries a PASS/FAIL. Slip in the implementer's report: gamma-1.40 arrival / net impulse
at G2 and G3 are in the record (10.414 ms / 182.24 Pa s; 10.496 ms / 225.59 Pa s).

**B1 the option - VERIFIED.** Default path unchanged: `git diff --stat` over
foam_golden, foam_fixtures, baseline empty; FOAM WRITER and REGRESSION pass;
`case_to_dict` has no key at 0 for 1D/2D/3D, VERSION 13; default Case2D and Case3D
`save_case` bytes identical at HEAD and base (sha 7071cf98..., ff3e3925...); the HD1-3d
CFD case saves to exactly the evidence case.json bytes (ac6369da...). `_e2e_vent_3d.py
--load` still "all 56 fields" and VENT 3D: PASS. Option on: writeInterval 0.0005,
adaptive_write False, 0 controlDict rewrites, save/load keeps 60. Validation: a case per
rule.

**B2 the purge - FIXED in b87f76f.** Line-by-line review PASS: only ever builds
`<runs root>/<run>/processor<N>/<numeric time>` with `<run>` exactly one level under the
runs root; quotes, spaces, `..`, `constant`, negative or infinite times refused; never
the root copy, constant, postProcessing or the start dir; inactive at budget 0, in
serial and on decomposed AMR (no listing, no deleter call); a failed delete is logged
once with its reason and never raises.
- **Defect 1 (Medium), fixed:** the purge anchored on the newest time complete on every
  rank even when its reconstructPar had failed (root copy without `p`). A resume walks
  back to the newest whole root time (`backend._resume_start_time`, P1-5, on EVERY
  resume, not only AMR as the plan's safety table assumed) and restarts from that
  time's `processor*/` copy - which the purge had deleted. Reproduced on a fake run.
  Fix: the anchor is the newest time complete on every rank AND reconstructed.
- **Defect 2 (Medium), fixed:** `delete_decomposed` put every path on one `wsl.exe`
  command line; 60 writes x 13 ranks = 53,612 characters > Windows' 32,767 (WinError
  206, confirmed); caught and logged once, and since the plan only grows the purge
  would stay off for the rest of the run. Fix: `rm_scripts` chunks paths to <= 16,000
  characters, one WSL stage per chunk; a normal purge is still one stage.
- New checks added to `test_write_budget.py` (no existing check edited); they fail on
  0ac8217 and pass on b87f76f.

**B3 real runs - VERIFIED, with one listed gate FAIL that predates the batch.**
`_e2e_foam_write_budget.py`: WRITE BUDGET E2E: PASS twice (an export of 0ac8217 and at
b87f76f), reproducing the implementer's numbers. The implementer's changed criterion
("run A's writes by name plus at most the stop's own writeNow" instead of "same write
count") is a legitimate correction, at least as strict, committed in 919870e
(14:23:33) before the first run at 14:24. WSL gates at b87f76f: 3d_smoke --tiny PASS;
stop PASS; parallel 18/18 PASS; postmortem FAIL 1 check ("final peak map within
0.5 %", max rel 2.90e-01, 620 vs 632 samples) - identical from a `git archive
7dd2446` export, and the batch is a no-op on that path (10,000 cells -> serial, budget
0: purge inactive, `maybe_reconstruct` returns early, `_timing`/adaptive/banner
unchanged; the check runs through PeakImpulse and FO pMax, untouched).
`test_foam_wsl_resume.py` fails identically at HEAD and base: `AttributeError:
'types.SimpleNamespace' object has no attribute 'init_state'` in `FoamRunLoop.__init__`.

## Independent numbers

G1 from the raw evidence with the verifier's own numpy and the rule's formulas (no
blastlab import): p, U, rho times identical across the three files; un, R, M match
exactly; S and E differ by <= 2.0e-10 Pa (gamma 1.24) and 1.5e-10 Pa (1.40); a second
pitot route (normal shock then isentropic stop) agrees to 2.4e-15.

| Trace | Peak kPa at ms (governs) | Arrival ms | +impulse Pa s | Net Pa s |
|---|---|---|---|---|
| G1, 1.24 | 153.67 at 23.815 (S; R -25.96) | 10.024 | 2030.62 (LB) | 2033.12 |
| G1, 1.40 | 146.73 at 23.201 | 10.024 | 1965.49 | 1967.99 |
| G2, 1.24 | 59.72 at 12.905 (R) | 10.414 | 442.88 | 184.55 |
| G3, 1.24 | 54.90 at 14.109 (R) | 10.496 | 379.10 | 227.99 |

P2 holds (rise 10.319 ms; a 422.1 m/s; D 1.200 m; D/a 2.843 ms; ratio 3.630). P3 holds
(backward 65,380.4, forward 49,156.6, central 56,953.4 Pa/s against 1,351,849.6; ratio
0.0484; the largest rise rate anywhere before t_open is 0.051 of the ceiling). Example
panel reproduced with the verifier's own E arrays and T1 tail (G1: T0 0.4672 / 0.238 deg,
0.4475 / 0.228; T1 0.6513 / 0.332, 0.6762 / 0.344; plane max: T0 0.4500 / 0.229, 0.4309
/ 0.219; T1 0.6436 / 0.328, 0.6711 / 0.342; G2, G3 match). The outcome takes only P2,
P3, `trusted` and `read_only`.

Plane spot check, read-only over 9p with the verifier's own binary parse and cell
mapping (841,704 fluid cells):

| Write | Plane max, gamma 1.24, where | Match | G1 cell vs probe (p / rho / U) |
|---|---|---|---|
| 0.023802948 | 155270.782771 Pa at (9.95, 5.95, 1.25) | identical; 1.40 off 2.9e-11 | 5.2e-7 / 8.3e-7 / 3.1e-7 |
| 0.012893263 | 65232.021614 Pa at (9.95, 6.05, 1.45) | identical | 3.7e-6 / 1.4e-8 / 7.8e-7 |
| 0.029009842 | 137990.533100 Pa at (10.05, 6.05, 1.15) | identical; 1.40 off 5.8e-11 | 5.9e-7 / 6.3e-7 / 7.6e-8 |

Panel and strip means identical to the file.

## Evidence and corpus

Fingerprint identical at 15:58 and 17:31 (du -sb 185,713,059,688; newest mtime
2026-09-23 21:22:50.398; 157,318 files / 21,018 dirs; listing sha256 40d3a9d5...6367;
case.json and gauges p/U/rho = SHA256SUMS.source). No OpenFOAM utility, no load_run,
no auto_cleanup, nothing installed in WSL. Run list identical before (15:58, 16:30)
and after (17:31) - the same 10 runs as before B3. Deleted by exact path, 15 of the
verifier's own runs (rc 0, gone): 20260924-163019_3d_p33772-00, -163148_3d_p33772-01,
-163407_3d_p9704-00, -163535_3d_p9704-01, -163807_2d_p38668-00, -164503_2d_p38668-01,
-165533_2d_p7612-00, -170229_2d_p7612-01, -171049_3d_p26000-00, -171224_2d_p27540-00,
-171234_2d_p27540-01, -171251_2d_p29744-00, -171918_2d_p29744-01, -172309_2d_p29744-02,
-172603_2d_p29744-03 (all prefixed 20260924-). WSL `/` available 561,114,902,528 B
before and after; C: free 162,216,116,224 B (16:30) and 162,214,498,304 B (17:31).

## Gates

No-WSL matrix at 0ac8217: 49/50 PASS (only test_foam_wsl_resume.py). After the fix
(b87f76f): the 16 runloop / writer / reader / HD1 suites plus REGRESSION 15/16 PASS
(the same test_foam_wsl_resume.py). Skipped under the overrides: test_foam_env.py
(calls env.auto_cleanup), the 9 Tk test_gui_*, test_anim_scale.py and
test_viz3d_panel.py (real Tk windows); the batch touches none of their code and the
implementer reports them green.

## Fix

b87f76f `fix(verify): HD1-15 B2 - the purge keeps the resume's walk-back target, and its
rm fits a Windows command line` - `blastlab/solvers/foam/runloop.py`,
`blastlab/tests/test_write_budget.py`.

## Low defects, not fixed

- `DecomposedPurge.run`: a failed final-sweep purge logs "retrying at the next poll",
  but no poll follows; nothing is deleted, so it fails safe (cosmetic).
- `reader.read_probes` aligns U and rho with p by row count, not by time (pre-existing
  guard, inherited by `velocities` as planned); the evidence's times are identical, so
  HD1-13 is unaffected.
- `runloop.purge_active` cites guide 11.2-11.3 (p. 112) for "keeps its times per rank";
  that page is about dynamic load balancing - the support is indirect.
- `writer.write_budget_of` turns a malformed budget into 0 silently; validation refuses
  it as an error first, so it fails safe.

## Engineering questions

1. **BOUND bounds the load, not the response.** The envelope max(G1, plane max) is at
   least G1's E at every sample and carries more impulse (2095.6 against 2033.1 Pa s),
   yet gives the example panel a LOWER response than G1 alone (T0 mu 0.4500 vs 0.4672;
   T1 0.6426 vs 0.6513, gamma 1.24); the same for the plane-max trace, sampled only at
   writes. For a dynamic SDOF a load larger at every instant does not guarantee a
   larger peak response. The rule's wording ("upper bound on the load") holds; the
   plan's P1 rationale ("a uniform load ... loads the SDOF more") does not. The owner's
   SDOF should take the worst response over the delivered traces, and DONE.md must not
   call either trace a response bound.
2. Step 2's first printed outcome was NOT ESTABLISHED, from the tool defect (A3); the
   owner may want a line about it in the record or DONE.md.
3. The plan's safety table was wrong about P1-5 (the walk-back runs on every resume);
   the purge interaction is fixed in b87f76f.
4. Confirmed the implementer's #1, #2, #3, #4, #6, #7; relayed #5, #8, #9, #10 as they
   stand.

**GUI screens that need QA:** none.
