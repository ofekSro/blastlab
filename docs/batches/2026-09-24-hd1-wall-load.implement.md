# Batch 2026-09-24 `hd1-wall-load` - implementer report

Saved by the orchestrator from the implementer's hand-back (BASE 7dd2446, HEAD 0ac8217).

## Result

- **HD1-13 (Part A): BOUND.** The outcome function's line, the last line of
  `docs/hd13/vent3d_wall_load.txt`:
  `HD1-13 ROUTE (b): BOUND - P2 and P3 hold and Step 2 is trusted`
- **HD1-15 (Part B): implemented.** The real-run e2e passes (`WRITE BUDGET E2E: PASS`).
- **Two gate suites fail, both pre-existing** (they also fail at base 7dd2446, and
  the batch touched neither): `test_foam_wsl_resume.py` (AttributeError on
  `spec.init_state`) and `test_foam_postmortem.py` (1 check, "final peak map within
  0.5 %", rel 2.90e-01 - identical when run from an exported copy of 7dd2446).
- The evidence run is unchanged at the end (fingerprint identical to H3's). The
  corpus equals the pre-B3 list. No TODO.md / DONE.md / CLAUDE.md / settings file
  edited. GUI screens touched: none.

## Commits

| Commit | Time | What |
|---|---|---|
| 0e8583a | 13:24:32 | core: HD1-13 A1 - the wall load at a point |
| **bf8d89d** | **13:26:04** | docs: the decision rule, registered before the numbers |
| 46ca1fe | 13:37:04 | tests: A2 - probe velocities + Step 1 |
| fb017ad | 13:47:39 | tests: A3 - Step 2 |
| 53f87ad | 13:53:25 | fix: A3 - reads the writer-framed start time |
| 0703d75 | 14:02:29 | docs: A3 - delivered G1 trace + plane file |
| 9889c54 | 14:02:45 | docs: A4 - the record (BOUND) |
| 6960902 | 14:11:20 | feat: HD1-15 B1 |
| 5507069 | 14:17:16 | feat: HD1-15 B2 |
| a038c16 | 14:20:35 | fix: B2 - a resumed session purges only what is still present |
| 919870e | 14:23:33 | tests: B3 e2e |
| 0ac8217 | 14:27:36 | fix: B3 - the frames check (numpy truth value) |

## The rule file

`docs/hd13/vent3d_wall_rule.txt` = commit **bf8d89d**, sha256
**9a7c2678f412344460b92ac55fcd43a0200775a0da32402f29850011d20f842f** (5272 B): the
plan's fenced block byte for byte with `<date>` -> `2026-09-24` (checked by script);
unchanged since. The only earlier commit, 0e8583a (A1), opens no evidence file.
Every computation of E on the evidence came after 13:26:04 (Step 1 after 46ca1fe;
Step 2 attempt 1 at 13:48:16, aborted before any plane number; attempt 2
13:53:46-13:59:51). The record prints the same sha256.

## A1 - `core/wallload.py`: DONE (0e8583a)

Pure numpy: `reflected_overpressure` (Rankine-Hugoniot normal reflection, no
clearing); `stagnation_pressure` (isentropic below M = 1, Rayleigh pitot at and
above; un < 0 -> 0); `wall_load` -> dict(t, E, R, S, M, un), vector U or normal
speeds, NaN in -> NaN out; `extend_with_tail` (the T1 hold, stepped at the last
sample gap). Docstring cites UFC 3-340-02 para 2-15.3.1/2-15.3.2, Eq. 2-9, Figs. 2-15
and 2-193 with page markers. Files: `blastlab/core/wallload.py`,
`blastlab/tests/test_wallload.py` (new). `python test_wallload.py` -> WALL LOAD: PASS.
Criteria all PASS: pitot = isentropic at M = 1 to 1e-12 (gamma 1.24, 1.40); pitot <
isentropic on (1, 5]; p02/p1 at M = 2 equals the two-step derivation to 1e-12
(5.640441); reflection limits 2.00000086 (weak) / 7.999958 (strong), ps <= 0
unchanged; low-Mach S - (ps + q) = 2.5e-5 q; UFC Appendix 2A: Cr 2.5316 / 2.6639 /
2.9766 against 2.40 / 2.70 / 2.90 (+5.48 %, -1.34 %, +2.64 %), q 3.541 psi (+1.17 %),
S 16.507 psi (+1.27 %); S and R fall strictly in gamma on the 17-point grid; imports
numpy + `.constants` only, no GUI module imports it; REGRESSION, no_vtk, no_pyplot PASS.

## A2 - Step 1 on the probes: DONE (rule bf8d89d; code 46ca1fe)

`reader.read_probes` gains `velocities` ((n, 3) U per probe, same guard as `speeds`;
`speeds == |velocities|` bit for bit). `tests/_e2e_vent_wall.py` (new, manual): sha256
checks against SHA256SUMS.source, key-for-key case.json identity, the rule sha, the
C10 control, E at G1/G2/G3 x gamma x T0/T1 with summarize_trace, P2, P3, then the
delivered G1 trace. The outcome function takes only the four conditions. Files:
`solvers/foam/reader.py`, `tests/test_foam_reader.py`, `tests/_e2e_vent_wall.py`,
`tests/test_vent_wall.py`. VENT WALL: PASS; FOAM READER: PASS. Criteria PASS (rule
before record; C10 control mu 0.3027, theta 0.154 deg, dynamic; everything printed;
gates; `_e2e_vent_3d.py` unchanged).

## A3 - Step 2, the plane x = 10 m: DONE (fb017ad, fix 53f87ad, files 0703d75)

`backend.read_3d` on `writer.render_case(cfd, n_procs=13)` in memory, over 9p; root
time dirs only; layers from x_c (9.95 / 10.05, cells 99 and 100 of 120); a 20 s
process-scan timer thread; the run fingerprinted inside WSL before and after; no
OpenFOAM utility, no `postmortem.load_run`, no install in WSL.
- Attempt 1 (13:48) aborted at t = 0: "unterminated internalField list in ...\0\p" -
  blastlab's writer closes a nonuniform ascii list with `);`, the reader needs a bare
  `)`. No plane number computed; fingerprint identical after. Fix 53f87ad:
  `read_start` tries the reader first, then a parse that accepts `);`. The shared
  reader is unchanged (engineering question 1).
- Attempt 2 (13:53:46-13:59:51): 749 writes; 25,752,728,010 B of p/U/rho in 331 s
  (365 s wall); 18 scans, none hit; fingerprint before == after.
- Mapping check (267 writes after 8 ms; time mismatch <= 4.40e-06): cell
  (9.95, 5.95, 1.35) = (99, 59, 13) matches - p 4.81e-06, rho 4.18e-06, U 4.28e-06; the
  y-mirror cell matches p and rho but not U (8.69e-02); the other six >= 1.6e-02.
  **Step 2 TRUSTED.**

## A4 - the record: DONE (9889c54)

`docs/hd13/vent3d_wall_load.txt` (153 lines, sha256 b21ffae3...af646) = attempt 2's
console output.
- **P2 holds:** un max 687.6 m/s; t10 12.480 ms, t90 22.799 ms, rise 10.319 ms;
  D = 1.200 m, a = 422.1 m/s at t90, D/a = 2.843 ms (ratio 3.630).
- **P3 holds:** at t_open 13.1145 s the rise rate is 65,380.4 Pa/s (larger one-sided
  difference, fixed before the number); ceiling 205.00 kPa / 0.1516 s =
  1,351,849.6 Pa/s; ratio 0.0484.
- **Step 2:** read-only yes; trusted yes. **C10 control:** mu 0.3027, theta 0.154 deg,
  dynamic.

E (impulse "(LB)" = lower bound, still positive at 30 ms):

| Trace | gamma | Peak kPa | At ms | Arrival ms | +impulse Pa s | Net Pa s |
|---|---|---|---|---|---|---|
| G1 | 1.24 | 153.67 (S governs; R -25.96) | 23.815 | 10.024 | 2030.62 (LB) | 2033.12 |
| G1 | 1.40 | 146.73 | 23.201 | 10.024 | 1965.49 (LB) | 1967.99 |
| Plane max, at (9.95, 5.95, 1.25) m | 1.24 | 155.27 | 23.803 | 10.083 | 2092.45 (LB) | 2095.63 |
| Plane max | 1.40 | 148.26 | 23.803 | 10.083 | 2026.10 (LB) | 2029.28 |
| G2 | 1.24 | 59.72 (R governs) | 12.905 | 10.414 | 442.88 | 184.55 |
| G2 | 1.40 | 59.34 | 12.905 | - | 440.64 | - |
| G3 | 1.24 | 54.90 (R governs) | 14.109 | 10.496 | 379.10 | 227.99 |
| G3 | 1.40 | 54.58 | 14.109 | - | 377.36 | - |

|U| against un: G1 max |U| 690.4, un 687.6 m/s (0.9960); G2 max |U| 210.0 m/s
(Ux/|U| 0.1340), un 129.1; G3 232.7 / 231.2. Panel means (estimates, not bounds):
momentum-flux peak 34.89 kPa at 18.844 ms; area-mean E 51.05 / 50.75 kPa; strip-mean
E at y = 6: 66.39 / 65.88 kPa.

Example panel, report only (UFC reference: 2 deg = mu 3.93, 6 deg = 11.82, 12 deg =
23.91; all dynamic, none collapsed; every T1 peak after the record, set by the hold):

| Trace | T0 g1.24 | T0 g1.40 | T1 g1.24 | T1 g1.40 |
|---|---|---|---|---|
| G1 | mu 0.4672, 0.238 deg | 0.4475, 0.228 | 0.6513, 0.332 | 0.6762, 0.344 |
| Plane max | 0.4500, 0.229 | 0.4309, 0.219 | 0.6436, 0.328 | 0.6711, 0.342 |
| G2 | 0.3882, 0.198 | 0.3870, 0.197 | 1.5656, 0.797 | 1.5635, 0.796 |
| G3 | 0.3002, 0.153 | 0.2996, 0.153 | 1.4178, 0.722 | 1.4166, 0.721 |

T1 holds E_tail = 205.00 kPa for 31.99 ms (1.5 Tn).

Delivered files (headers also state the T1 rule and `status: BOUND ...`):
- `docs/hd13/vent3d_wall_load_G1.txt` (3395 rows): `# units: t [s]; un [m/s];
  R_1.24 [Pa over P_AIR]; S_1.24; E_1.24; M_1.24 [-]; R_1.40; S_1.40; E_1.40; M_1.40`
- `docs/hd13/vent3d_wall_plane.txt` (749 rows, t = 0 included): `# units: t [s];
  Emax_1.24 [Pa over P_AIR]; x/y/z_1.24 [m]; Emax_1.40; x/y/z_1.40; G1cell_p [Pa];
  G1cell_rho [kg/m3]; G1cell_Ux/Uy/Uz [m/s]; G1cell_E_1.24; G1cell_E_1.40;
  panel_momentum [Pa]; panel_E_1.24; strip_E_1.24; panel_E_1.40; strip_E_1.40`
- The plane maximum is never below E at G1's cell (smallest difference 0 Pa); it
  reaches up to 1.83x that cell's E at some writes.

A3 fingerprints (before 13:53:33 / after 14:00:54 / end 15:52:38, all identical): du -sb
185,713,059,688; newest mtime 2026-09-23 21:22:50.398; 157,318 files / 21,018 dirs;
tree sha256 40d3a9d5...6367; H3-format listing sha256 2101932063f3... (= H3); case.json
/ gauges p / U / rho = SHA256SUMS.source.

## B1 - write budget: DONE (6960902)

`write_budget: int = 0` on Case2D/Case3D; `case_to_dict` omits the key at 0; VERSION
stays 13. `_validate_write_budget`: whole number >= 0; needs t_end and N >= 2
(errors); a native solver gets a note; a warning below 4 x n_snapshots; notes for a 3D
terminate side normal to the slice, for parallel AMR (not purged), and a disk
estimate at 155 B per cell per write. `writer._timing` pins t_end/N
(`write_budget_of`); `_apply_budget` sets `spec.write_budget` and switches the adaptive
controller off; the 2D and 3D solvers gain `and not spec.write_budget`; the banner
says `(pinned: write budget N)` only when set. Files: core/case.py,
solvers/foam/writer.py, solvers/foam/backend.py, tests/test_case_validate.py,
tests/test_write_budget.py (new). Criteria all PASS: FOAM WRITER green without
`--update`; golden/fixture/baseline status empty; REGRESSION; no key in a default
`case_to_dict`; the evidence case.json equals the CFD case in all 56 keys and
`_e2e_vent_3d.py --load` still ends VENT 3D: PASS; t_end 0.03 s, N 60 -> writeInterval
0.0005, `adaptive_write` False, 0 controlDict rewrites; save/load keeps 60; one
validation case per rule.

## B2 - decomposed copy of the latest write only: DONE (5507069, a038c16)

`maybe_reconstruct` returns the times it covered. `decomposed_purge_plan` (pure)
deletes a time only if ingested, reconstructed, older than the newest complete common
time, and not start_dir. `purge_paths` builds only `<runs root>/<run>/processor<N>/<time>`
(13 bad shapes refused in the test). `delete_decomposed` issues one `rm -rf --` in
WSL. `DecomposedPurge` on FoamRunLoop (class default None so `__new__`-built loops
still work): active only with a budget, in parallel, not on decomposed AMR; runs after
every ingest pass incl. the final one; a failed delete is logged once, retried, never
raises; purges only times still present. Criteria: planner properties over 3000
random cases PASS; a fake 2-rank run ends {constant, 0, t3, t4 partial}, root untouched,
`_n_procs_on_disk` 2, `_resume_start_time` = latest root time, a second purge no-op
PASS; a spy deleter sees 0 calls through a whole fake `_ingest_ready` at budget 0 and
one call [t1, t2] at budget 10 PASS; resume, postmortem_decomposed, ingest_order,
amr_ingest, adaptive_interval, live_due, stop_latency PASS; test_foam_wsl_resume FAIL
(pre-existing).

## B3 - real runs + WSL gates: DONE; one gate suite fails for a pre-existing reason (919870e, fix 0ac8217)

`tests/_e2e_foam_write_budget.py`: the --tiny case, transmit boundaries, t_end 50 us,
N = 10, 2 ranks.
- **Run A:** 10 root writes at the multiples (5e-06 ... 5e-05); {0, 5e-05, constant} per
  rank; 9 purged times read back; 2 snapshots and 10 frames; 180 probe rows 0 to 5e-05,
  largest gap 3.64e-07 s; du 210,893,095 B <= 223,175,423 B (one write 16,907,229 B).
- **Run B:** stopped by should_stop after 4 writes (writeNow at 2.1769006e-05);
  {0, 2.1769006e-05, constant} per rank after the stop; `resume_run` to t_end; root =
  run A's writes plus only 2.1769006e-05; {0, 5e-05, constant} per rank at the end;
  probes continuous (180 rows, largest gap 3.64e-07 s vs bound 1.09e-06 s). The plan's
  literal "same write count as run A" (11 vs 10) cannot hold - a graceful stop always
  adds its writeNow - so the check was pre-registered before the run as "run A's writes
  plus at most the stop's own"; literal counts printed. OpenFOAM-9 keeps `beginTime`
  in `uniform/time`, so post-restart writes stay on run A's multiples (checked in Time.C).
- First e2e attempt (14:24): the script (not the solver) crashed on a numpy
  truth-value test after run A's first 4 checks passed; that run was deleted and the
  e2e rerun whole after 0ac8217.
- WSL gates, one at a time, pgrep before each: test_foam_3d_smoke --tiny PASS (78 s);
  test_foam_parallel PASS 18/18 (976 s); test_foam_stop PASS 12/12 (15 s);
  test_foam_postmortem FAIL 1 check (2.90e-01; 855 s) - also at the base commit with
  the same number (the scripted stop fires after 3 live-slice frames, ~15 steps,
  t = 0.64 us, before the first regular write; the resumed peak map misses the
  earliest peak).
- **Corpus guard (option (c)):** before B3 (14:23:58) and after (15:36:41) the
  `ls -1t` lists are identical ("equal to the record: True"): 20260923-195308_3d_p31468-00,
  20260922-132259_3d_p3756-00, 20260922-011030_3d_p39152-01, 20260922-005601_3d_p39152-00,
  20260921-235453_3d_p18960-00, 20260921-234628_3d_p36304-01, 20260921-234255_3d_p36304-00,
  20260921-215034_3d_p27908-01, 20260921-214703_3d_p27908-00, 20260921-214258_3d_p41288-00.
  The evidence run never left the 5 newest. Deleted by exact path (rc 0, gone):
  20260924-142413_3d_p39932-00; 20260924-142748_3d_p39028-00; 20260924-142916_3d_p39028-01;
  20260924-143206_3d_p38076-00; 20260924-144824_2d_p34872-03; 20260924-144529_2d_p34872-02;
  20260924-144135_2d_p34872-01; 20260924-143506_2d_p34872-00; 20260924-145526_2d_p24584-01;
  20260924-145515_2d_p24584-00; 20260924-150641_2d_p16504-01; 20260924-145947_2d_p16504-00;
  20260924-152744_2d_p25364-01; 20260924-152048_2d_p25364-00 (the last two from the
  base-commit rerun).
- Free space on C: 162,524,323,840 B at 13:47:59; 162,497,773,568 at B3's start;
  162,423,066,624 after B3; 162,417,700,864 at the end. WSL / used 464,993,918,976 B
  before and after B3.

## Final gate

62 suites one at a time: 61 PASS, 1 non-zero (test_foam_wsl_resume, pre-existing).
Includes REGRESSION PASS, FOAM WRITER PASS, the HD1 suites, the new WALL LOAD / VENT
WALL / WRITE BUDGET, the viz3d suites, all 15 offscreen test_ui_*, all 9 Tk
test_gui_*, and test_blast2d ALL CHECKS PASSED. No golden, fixture or baseline moved.
`python -c "import blastlab"` OK. Cleanup-policy dry runs (`env.cleanup_policy`,
never auto_cleanup) at 13:19 and before the final gate: "would sweep: nothing".
Deviation: the baseline runs of test_ui_no_vtk_in_main / test_ui_no_mpl_pyplot came
before the first dry run; both write `auto_cleanup: false` into a private file; the
corpus was verified intact right after. test_foam_env calls `env.auto_cleanup` only
with the opt-out, which returns (0, 0) before listing anything.

## Files touched

Code: blastlab/core/wallload.py (new), core/case.py, solvers/foam/reader.py,
writer.py, backend.py, runloop.py. Tests: test_wallload.py, _e2e_vent_wall.py,
test_vent_wall.py, test_write_budget.py, _e2e_foam_write_budget.py (new);
test_foam_reader.py, test_case_validate.py (edited). Docs: docs/hd13/vent3d_wall_rule.txt,
vent3d_wall_load.txt, vent3d_wall_load_G1.txt, vent3d_wall_plane.txt (new).

## Engineering questions

1. **Reader and writer disagree:** `writer._nonuniform`/`_render_fields` close lists
   with `);`, `reader._nonuniform_body` needs a bare `)`. The repo cannot read its own
   chamber/profile `0/` fields: `backend._initial_frame`/`_initial_frame3d` silently
   skip the t = 0 frame for those stages, and `_time_is_whole` fails on such a start
   dir. Fix the reader (GUI-visible, needs QA) or the writer (moves goldens).
2. **`test_foam_wsl_resume.py` broken since 9b9a039 (2026-09-19):** its stub spec lacks
   `init_state`, so the W3 regression suite has not run since. Fixing it edits a
   committed test (owner's call, §9).
3. **`test_foam_postmortem`'s peak-map check fails deterministically** (N6/T43): the
   FO pMax restart loses the state stored at the restart dir, or the scripted stop has
   drifted to 0.64 us because live frames now arrive faster.
4. **The T1 hold drives every T1 response** - all T1 peaks after 30 ms; the record
   covers 0.198 of the drain time. Route (a) or HD1-14 would want a longer window.
5. **Two artefacts at G2/G3:** T0 peaks after the record because sdof releases a
   suction E (-17.9 / -7.5 kPa at 30 ms, gamma 1.24) to zero; T1 applies 205 kPa where
   the local E is negative (mu 1.57 at G2). Conservative by design.
6. **The mapping check discriminates only through U:** the y-mirror cell matches p and
   rho to 4.8e-6 because the case is symmetric about y = 6.
7. **The jet core sits slightly low:** at the peak the plane maximum is at z = 1.25 m,
   0.15 m below the opening's axis.
8. **B1 uses `spec.write_budget` where the plan wrote `case.write_budget`:** identical
   whenever the budget takes effect; they differ only for a budget without t_end,
   which validation refuses.
9. **B2 extends rule 2 for resumed runs:** root writes already whole at a resumed
   session's start count as reconstructed, else the restart write would stay
   decomposed forever.
10. **The GUI drops the budget:** the Qt form rebuilds Case3D and loses `write_budget`
    on save (plan Risk 13); exposing it is backlog.

## A4 bookkeeping text (BOUND branch)

- TODO.md: `HD1-13` leaves; file `HD1-15` and close it as done; add the two
  pre-existing failures as new items.
- DONE.md §0, under the HD1-3d entry - the `HD1-13` closure paragraph (the
  implementer's full text is in its hand-back; the orchestrator condenses it for the
  1000-line cap), plus one sentence in "What the PASS does not establish": C10's
  "survives" was judged on the side-on load at a free-air gauge; the wall load is now
  in `docs/hd13/` (HD1-13, route (b), BOUND).
- HD1-15 DONE line: `write_budget = N` pins writeInterval to t_end/N and keeps only
  the latest complete decomposed write (runloop.DecomposedPurge; never the start dir,
  constant, the root or postProcessing, never decomposed AMR); default 0 changes
  nothing (no key, VERSION 13, goldens and regression unchanged). B3 on the tiny case
  (N = 10, 2 ranks): 10 writes at the multiples, {constant, 0, final} per rank, and
  resume keeps the schedule. Commits 6960902, 5507069, a038c16, 919870e, 0ac8217.
