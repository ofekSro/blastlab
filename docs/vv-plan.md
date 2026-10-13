## VV · Application validation report (owner, 2026-10-13)

**The whole specification is [docs/vv-plan.md](docs/vv-plan.md).** This entry only
orders it; every rule, target and acceptance criterion lives there. blastFoam backend
only; the native NumPy solvers are out of scope. Never invent reference data: a case
without a cited source file stays `pending`.

Runs are launched by `docs/vv/run_all.py` as a detached process, one at a time
(RAM). Agents write the scripts and read `docs/vv/results/*.json`; they do not wait
on a solve or tail its log.

| Id | What | Size | Risk | Order |
|---|---|---|---|---|
| `VV-0` | Pin versions (blastFoam commit, OpenFOAM, blastlab); `docs/vv/` tree; `run_all.py` with a run cache and a `--only <case>` flag; LaTeX toolchain check | S | low | 1 |
| `VV-1` | Wrapper verification: dictionaries vs input (existing golden tests), charge mass set vs requested, post-processing vs analytic Friedlander, remap-chain conservation, one blastFoam shipped validation case reproduced | M | high | 2 |
| `VV-2` | Case 1 inputs: 1 kg TNT 1D spherical, incident (8 probes, 0.5-20 m) and reflected (1, 3, 10 m), grids 4/2/1 mm, afterburn off. Inputs and run script only; owner launches | S | high | 2 ∥ VV-1 |
| `VV-3` | Case 1 analysis: KB free-air comparison, order of convergence, GCI, error tables, figures, cells-per-charge-radius rule. Needs VV-2 results on disk | M | high | 3 |
| `VV-4` | LaTeX report skeleton, all tables and numbers generated from `results/`, a check script that fails when a number in the PDF text differs from its JSON source | M | low | 2 ∥ VV-1 |
| `VV-5` | Report with Case 1 compiled to PDF; **track-end for part A, owner reviews** | S | high | 4 |
| `VV-6` | Case 2 clearing (Tyas/Rigby). **Blocked: owner supplies paper + digitized gauges** | M | high | 5 |
| `VV-7` | Case 3 urban street (Rose & Smith / Fouchier). **Blocked: reference data; office machine or cloud** | L | high | 6 |
| `VV-8` | Case 4 blast wall (Chapman, Rose & Smith). **Blocked: reference data; office machine or cloud** | L | high | 7 |
| `VV-9` | Afterburn section (on vs off, what was fitted), validity envelope, final report | M | high | 8 |

# Task: produce a formal V&V report for blastlab (LaTeX), running all cases yourself

## Context
blastlab is a Python front end that drives stock, unmodified blastFoam (OpenFOAM-9,
in WSL). I want to offer blast-load simulation as a service to protective-design
engineering firms. They will ask one question: "why should we trust your numbers?"
This report is the answer. Its readers are senior blast engineers who know
UFC 3-340-02 and will look for weak spots, so an honest report with stated
limitations is worth more than a flattering one.

Read first: CLAUDE.md, docs/SCOPE.md, docs/agent-rules.md,
docs/standing-rules-and-tests.md, docs/heavy-runs.md, docs/verification/,
blastlab/tests/test_foam_kb_anchor.py. Follow the repo's existing rules.

## The claim the report must support
"blastlab drives unmodified blastFoam correctly, and the results agree with
published experiments within a stated envelope."
This is an application validation report. It is not a code-verification report
for the solver: that belongs to Synthetik, so cite their published validation
instead of redoing Sod/Sedov.

Out of scope, and say so in the report: the native NumPy solvers
(blastlab/solvers/solver1d/2d/3d.py). Every number in the report comes from the
blastFoam backend.

## Rules that matter more than finishing
1. Never invent or estimate reference data. Experimental values come only from a
   source file in the repo or one I give you, with a citation. If the data for a
   case is missing, do not run a placeholder comparison: mark the case
   "pending reference data" and list exactly what you need from me.
2. Do not tune anything to improve agreement. Fix settings and acceptance targets
   before running, record them, then report what comes out, including failures.
3. Every number in the PDF is generated from a results file by script. No
   hand-typed results in the .tex.
4. Calibration is not validation. The Miller afterburn rate was fitted on TNT
   (see test_foam_kb_anchor.py). Run baseline cases with afterburn off; show
   afterburn-on as a separate, clearly labelled result, and never present
   agreement with the data it was fitted to as validation of that model.
5. If a run fails or diverges, diagnose and report it. Do not silently drop it.

## Work plan

### Phase 0: setup and pinning
- Confirm the WSL blastFoam install works. Record the exact blastFoam commit,
  OpenFOAM version, blastlab commit, OS, CPU. If the blastFoam commit cannot be
  determined, say so in the report.
- Create docs/vv/ with: cases/ (inputs), results/ (JSON/CSV), figures/ (vector
  PDF), report/ (LaTeX), and run_all.py that regenerates everything. Cache
  finished runs so a re-run skips them.
- Check a LaTeX toolchain exists (latexmk + pdflatex or lualatex). If not, tell
  me what to install and continue with everything else.

### Phase 1: wrapper verification (the part only blastlab is responsible for)
- Dictionaries written match the case input (reuse the golden-file tests; report
  the test count and result).
- Charge mass actually set in the mesh vs requested, per grid.
- Post-processing: feed the peak/impulse/arrival/duration routines an analytic
  Friedlander signal and report the error.
- Remap chain 1D -> 2D -> 3D: mass and total-energy conservation across each
  handoff.
- Installation check: run one or two of blastFoam's own validation cases through
  blastlab and compare to blastFoam's shipped reference output.

### Phase 2: Case 1, free-air spherical TNT vs Kingery-Bulmash
- 1 kg TNT sphere, 1D spherical, afterburn off, air as ideal gas, JWL from the
  repo's materials table. With 1 kg, R in metres equals Z.
- Incident: one run per grid, domain ~30 m, probes at
  R = 0.5, 1, 2, 3, 5, 8, 12, 20 m, run until the positive phase at 20 m ends
  and before any boundary effect reaches a probe.
- Reflected (normal): rigid wall at the domain end, separate runs at
  R = 1, 3, 10 m; pressure on the wall is the reflected pressure. State the
  limitation that a 1D wall is a spherical shell, and cross-check one point in
  2D axisymmetric against a plane wall.
- Grids: uniform 4, 2, 1 mm, same CFL. Full three-grid study for incident; for
  reflected only at R = 1 m. If peak overpressure at R = 0.5 m changes more than
  3% between 2 mm and 1 mm, add 0.5 mm.
- Report per probe: peak overpressure, positive impulse, arrival time, positive
  duration; observed order of convergence and GCI (Roache / ASME V&V 20),
  separately for peak and impulse.
- Reference: KB free-air (spherical) curves, not the hemispherical ones. Use the
  KB implementation or table already in the repo or in blastFoam's
  KingeryBulmash validation case (SwisdakData.csv); cite its origin. Verify the
  implementation against a few published tabulated points before using it.
- Targets, fixed in advance: peak within 10%, impulse within 15% for Z >= 1.
  Report Z < 1 separately. The existing anchor test measured 0.85-0.89 of KB at
  8 cells per charge radius; show how that changes with resolution.
- Output of this case also includes a practical rule: cells per charge radius
  (or cell size vs Z) needed for a given accuracy. Cases 2-4 will use it.

### Phase 3: Cases 2-4 (need reference data, see rule 1)
For each: check docs/references/ for the paper and data. If present, run it; if
not, stop at "pending" and tell me what to supply (paper + which gauges).
Verify every citation against the actual paper; the ones below are from memory.
- Case 2, clearing on a finite target: Tyas / Rigby et al. (Sheffield), small
  hemispherical PE4 charge, gauges on a finite rigid block. Compare
  pressure-time and impulse; also show the UFC/Hudson clearing prediction.
- Case 3, urban street: Rose & Smith (2002) and/or Fouchier et al. (2017),
  small-scale straight street and junctions. Compare gauges along the street and
  the amplification factor vs free field. Produce an impulse map on the facades.
- Case 4, blast wall: Chapman, Rose & Smith (1995), cantilever wall in front of
  a building. Compare pressure/impulse up the facade with and without the wall.
Each case: grid study with GCI on at least the key gauges, using the resolution
rule from Case 1 and the 1D->3D remap where it applies.

### Phase 4: the report (LaTeX, English, formal engineering report)
docs/vv/report/, built with latexmk into one PDF. article or report class,
booktabs tables, siunitx units, vector figures, BibTeX/biblatex references,
document number, revision table, version/commit block on the title page.
Structure:
1. Executive summary: one table, case / quantity / error / numerical
   uncertainty / target met or not.
2. Scope and claim; what is excluded.
3. Software and versions; solver heritage with citations to Synthetik's
   validation.
4. Wrapper verification (Phase 1).
5. Solution verification method (GCI).
6. Validation cases, same template each: purpose, experiment and gauge layout
   sketch, numerical setup, pressure-time plots with simulation over experiment,
   error table, discussion, limitations.
7. Calibrated models (afterburn): what was fitted, on what, results on and off.
8. Validity envelope and recommended default settings.
9. Reproducibility: how to regenerate every figure; case files in an appendix.
Plots: simulation and reference on the same axes, log-log for the KB sweep,
readable in greyscale, axis units on every plot.

## How to work
- Work on a new branch; commit after each phase. Do not push.
- Start with Phase 0-2 end to end, including a compiled PDF containing Case 1,
  before starting Phase 3. Show me that PDF.
- Keep a docs/vv/LOG.md: what ran, wall time, anything surprising.
- Before reporting done, re-read the PDF: check that every number in the text
  matches the results files, every figure is referenced, and every citation
  resolves.

## Final message to me
What passed, what failed its target and by how much, what is pending and what
data you need from me, and any limitation you found that I should know before
showing this to a client.

