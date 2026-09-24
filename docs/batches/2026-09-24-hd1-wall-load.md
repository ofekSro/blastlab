# Batch 2026-09-24 - `hd1-wall-load`

**Goal.** Produce, without a new solve, the load a wall at the HD1-3d target
actually takes, as a time history the owner can put through an SDOF for any
wall. That load is the leading front reflected at normal incidence plus the
jet's compressible stagnation pressure, taken from the existing run's probes and
fields. A rule registered before any number is computed decides only whether
that trace is an upper bound on the wall load (`HD1-13`, route (b)). **No survival
verdict is given** (owner answer 1 below). The batch then adds an opt-in write
budget per case, so that route (a) or `HD1-14` costs about 8 GB of disk instead
of about 190 GB (`HD1-15`).

Planned on branch `hd1-band-cost` at `b0b9afa` (clean tree), 2026-09-24.

The two parts are independent in code. Their order matters for one reason: A3
reads the run's time directories, and B3's WSL runs push that run toward the
corpus sweep (Risks 8). Part B can run as a batch of its own, but A3 must come
first either way.

**Owner answers (2026-09-24). Where they conflict with text further down, they
win; the rule block has been rewritten to match.**
1. **No survival criterion in this batch.** In the owner's words: take the load
   and Pr(t) and put them through an SDOF afterwards - every wall can have
   different criteria. So the product is the load trace: E(t) with its parts
   R(t) (reflected front) and S(t) (stagnation), exported with units. The rule
   judges only whether that trace is an upper bound (BOUND / NOT ESTABLISHED).
   C10's component, the 200 mm panel, goes through `core/sdof` **as a report
   only**: mu and theta, with UFC 3-340-02's rotation limits (2 / 6 / 12 deg)
   listed beside them for reference. No S*, and no KEEP / REOPEN / INCONCLUSIVE.
   Wherever the text below says "verdict function", read "outcome function".
2. **Scope: both parts, A and B.**
3. **Corpus (clarification 3): option (c).** After recording their results, the
   batch deletes by exact name only the runs B3 itself created. Nothing else is
   deleted and no settings file is edited.
4. **Defaults taken by the orchestrator** (the owner may still change them):
   - panel footprint y 4.5-7.5 m, z 0-3 m, for report-only numbers;
   - `write_budget` omitted when 0, and `VERSION` stays 13;
   - TODO id `HD1-15`;
   - NACA 1135 is not registered: the test uses two independent closed forms
     and cites neither.
5. **Not in this batch, still open for the owner:** deleting the 30-snapshot
   run, closing `HD1-4`, and `HD1-14`'s timing.

**GUI screens touched: none.** Nothing under `blastlab/ui/`, `blastlab/gui/` or
`blastlab/viz3d/` is edited, so no real-window QA is needed. Because `core/`
and `solvers/foam/` change, CLAUDE.md §9 asks for the 9 Tk `test_gui_*`
suites, and the final gate also runs the offscreen Qt `test_ui_*` suites. Both
were checked to be sweep-safe:
- The Tk suites build `App` via `App.__new__` (`test_gui_drain.py:199`,
  `test_gui_results_fields.py:530`), or with a private settings file
  (`test_gui_solver_mode.py:21-23`).
- The Qt suites go through `ui/testing.private_settings()`.

---

## What the planner verified (read-only), and what it did not do

1. **The probes do record vector U.** `postProcessing/gauges/0/U` holds
   `(ux uy uz)` per probe (evidence copy, sha256 `4973fe13...`). However,
   `reader.read_probes` keeps only `speeds = |U|` (`solvers/foam/reader.py:485`),
   and that is all `backend.finalize_3d` and `_e2e_vent_3d.load_gauges` pass on.
   A wall-normal component therefore needs a new `velocities` key (A2).
2. **The orchestrator's single-sample numbers, checked** on the evidence copy's
   raw probe files. At G1 = (10, 6, 1.4), 1/2 rho |U|^2 peaks at
   **114.58 kPa at 24.712 ms**. At that sample:
   - p = 69,799 Pa absolute (-31.53 kPa), rho = 0.5079 kg/m3;
   - U = (669.4, -3.7, -56.1) m/s, |U| = 671.7 m/s, **Ux/|U| = 0.9965**.

   | gamma | velocity | a [m/s] | M | Rayleigh pitot overpressure [kPa] |
   |---|---|---|---|---|
   | 1.40 | \|U\| | 438.6 | 1.531 | 145.29 |
   | 1.40 | Ux | 438.6 | 1.526 | 143.85 |
   | 1.24 | \|U\| | 412.8 | 1.627 | 152.31 |
   | 1.24 | Ux | 412.8 | 1.622 | 150.82 |

   "M 1.53-1.62, pitot ~146-152 kPa" holds, with two corrections. The
   propellant gamma is **1.24, not 1.25**: that is the `double_base` row in
   `core/fuels.py:216`, and it is also what the run's `constant/phaseProperties`
   says. The gamma-1.40 end is 145.3 kPa.
   - At G1 the normal component barely matters.
   - At G2 it does: at G2's |U| peak, Ux/|U| = 0.25, and 1/2 rho Ux+^2 peaks at
     5.11 kPa against 1/2 rho |U|^2 = 17.69 kPa.
3. **The two gamma ends bound any mixture.** At a fixed (p, rho, u), the
   stagnation pressure falls monotonically in gamma over [1.24, 1.40]. This was
   checked on 17 points for u = 100-1000 m/s at the G1 state. The
   Rankine-Hugoniot reflection factor falls in gamma analytically:
   d/dgamma of (g+1)/((g-1)ps + 2g p0) is -2(ps + p0)/(...)^2 < 0. So
   gamma = 1.24 is the severe end for both terms. A1 pins this.
4. **The run's fields.**
   - 749 time dirs, i.e. t = 0 plus 748 writes. There are 13 `processor*` dirs
     and each holds all 749 times again.
   - One write is 130,677,089 B (14 fields). p + U + rho is 34,595,024 B.
   - Format: `binary`, `writeCompression off`,
     `nonuniform List<...> 841704`, i.e. fluid cells only, in subsetMesh order.
   - In (0, 8] ms there are 481 writes, with gaps of 2.58-82.65 us. In (8, 30]
     ms there are 267 writes, all at the 8*iv0 ceiling of 82.65 us.
5. **Probe rows land on write times.** Every write has a probe row at the same
   solver step. They agree to within 4.6e-6 relative in time, which is the
   probe file's 6-digit print. After 8 ms there are 7 solver steps per write.
   So a cell read from the fields can be checked exactly against the probe
   (A3's mapping check).
6. **IO cost, measured.**
   - Over 9p from Windows: p + U + rho of one write takes 0.34-0.35 s, about
     100 MB/s (two writes measured). A parse through the repo reader takes
     0.09 s for p and 0.20 s for U, IO included.
   - Inside WSL, cold: 24 ms for the same 34.6 MB, and 76 ms for a whole write
     (about 1.5-1.7 GB/s).
   - **WSL's `python3` (3.10.12) has no numpy.** All 748 writes are 25.9 GB:
     about **5-9 min over 9p** with the repo reader. Inside WSL the raw read
     would take about 20 s, but only with numpy installed there. That would
     change the verified environment (CLAUDE.md §3), so it is not proposed.
7. **The corpus at 12:14 today** has 10 run dirs, and the evidence run is the
   newest. `20260921-123600_2d_p41784-01`, the single victim of this morning's
   dry run, is **gone**: a sweep ran after 10:45, or the run was removed by
   hand. None of the WSL suites deletes its runs.
8. **C10's component.**
   - K_LM 0.72, m_eq 345.6 kg/m2, Tn 21.33 ms, y_el 13.33 mm, 12 deg collapse
     limit.
   - theta = 2 / 6 / 12 deg corresponds to mu = 3.93 / 11.82 / 23.91.
     mu = 1 corresponds to theta = 0.51 deg.
   - Recorded result: mu 0.3027, theta 0.154 deg.
   - `sdof.response` takes the load as **zero after the record ends**
     (`core/sdof.py:333-334`).
9. **UFC 3-340-02 anchors in the text sidecar.** Figs. 2-15 and 2-193 are
   images, so their text layer holds axis labels only.

   | Item | Page marker | Printed page |
   |---|---|---|
   | Para 2-15.3.1, the four load components | `=== page 140 ===` | 64 |
   | Para 2-15.3.2 and Eq. 2-9, `P = Ps + C_D q`, C_D = 1 on a front wall | `=== page 141 ===` | 65 |
   | Fig. 2-15 | `=== page 166 ===` | 90 |
   | Fig. 2-193, Cr against angle of incidence | `=== page 344 ===` | 268 |
   | Appendix 2A reading of Fig. 2-193 at alpha = 0: Cr = 2.70 at Pso = 12.8 psi | `=== page 486 ===` | 410 |
   | Same example: q = 3.5 psi (Fig. 2-3), and Pso + C_D q = 16.3 psi | `=== page 487 ===` | 411 |
   | Appendix 2A: Cr = 2.40 at 10 psi and 2.90 at 20 psi | `=== page 501 ===` | 425 |

10. **What the planner did not do.**
    - No wall-load trace and no SDOF response on any new load was computed.
    - Nothing was written inside WSL or into any run dir.
    - `env.auto_cleanup` was not called.
    - The rule below was drafted knowing only the numbers above, the
      TODO/DONE/ENGINEERING_QUESTIONS text, and the brief's single-sample
      values.

---

## The decision rule (proposed - approval required, Needs clarification 1)

The owner-approved text goes **verbatim** into `docs/hd13/vent3d_wall_rule.txt`.
That file is committed before A2 first runs on the evidence.

```text
HD1-13, ROUTE (b) - DECISION RULE
Registered <date> by the owner, before any wall-load number was computed.

EVIDENCE. Run 20260923-195308_3d_p31468-00 (HD1-3d), judged from files only,
with no solve. The evidence copy's postProcessing/gauges/0/{p,U,rho} and
case.json each match SHA256SUMS.source, and case.json equals the script's CFD
case in every key. Step 2 reads the run's reconstructed time directories,
read-only. C10 and _e2e_vent_3d.py are not edited.

LOAD AT A POINT, in Pa over P_AIR = 101325, computed for gamma g = 1.24 (the
double_base products, as written into the run's constant/phaseProperties) and
for g = 1.40 (air):
  ps = p - P_AIR
  R  = ps [2 + (g+1) ps / ((g-1) ps + 2 g P_AIR)]   where ps > 0; R = ps otherwise
       (normal reflection of the front, Rankine-Hugoniot; no clearing - the
        wall is taken as unbounded)
  un = max(Ux, 0), the velocity into the wall (the wall at x = 10 m faces -x)
  M  = un / sqrt(g p / rho)
  p0 = p (1 + (g-1) M^2 / 2)^(g/(g-1))                                  if M < 1
  p0 = p [(g+1)^2 M^2 / (4g M^2 - 2(g-1))]^(g/(g-1)) (1 - g + 2g M^2)/(g+1)
                                                                         if M >= 1
       (Rayleigh pitot: a normal shock stands ahead of the wall)
  S  = p0 - P_AIR
  E  = max(R, S)

RESPONSE. core/sdof.response(t, E, comp, p_ref=0) with C10's component
unchanged: span 3.0 m, 480 kg/m2, Ru 400 kPa, kE 3.0e7 Pa/m, simple support,
damping 0, K_LM average, 12 deg collapse limit (Tn 21.33 ms, y_el 13.33 mm).
Two tails after the record ends at 30 ms:
  T0, as recorded: E = 0 afterwards (what C10 did).
  T1, the bound: E held at E_tail = max(p_open - P_AIR, max E over the record)
      for 1.5 Tn, then the solver's own free vibration. p_open is the chamber
      hand-off pressure in case.json (0.30633 MPa, so E_tail >= 205.0 kPa):
      the jet cannot deliver more than the chamber's own pressure (P3).

TRACES.
  Step 1: E at G1 = (10, 6, 1.4), every probe sample.
  Step 2: at every written time, the maximum of E over the two cell layers
      either side of x = 10 m (centres 9.95 and 10.05 m), all y and z.
      Trusted only if one of the eight cells around (10, 6, 1.4) reproduces
      G1's probe p, rho and U to 1e-5 relative (U: relative to |U| + 1 m/s)
      at all 267 writes after 8 ms.

PREMISES.
  P2, quasi-steady stagnation: at G1, t90 - t10 >= D / a, where
      t90 = first time un >= 0.9 max(un);
      t10 = last time before t90 with un <= 0.1 max(un);
      D = sqrt(vent area) = 1.2 m; a = sqrt(1.24 p / rho) at t90.
  P3, the tail is a ceiling: the sealed 0-D run's pressure rise rate at
      t_open < (p_open - P_AIR) / tau_drain.

NO SURVIVAL CRITERION (owner, 2026-09-24). Every wall has its own criterion.
What this rule produces is the LOAD: E(t), with R(t) and S(t), exported for
the owner's SDOF on any wall. Nothing below says whether any wall survives.

OUTCOME - about the load only; first match wins:
  NOT ESTABLISHED  P2 or P3 fails, or Step 2 is untrusted (mapping check), or
                   Step 2 cannot be run read-only. The exported E(t) is still
                   what the formulas above give, but it is NOT claimed as an
                   upper bound on the wall load. HD1-13 stays open. The next
                   step is route (a): mesh the wall at x = 10 m and read its
                   face in a new solve, after HD1-15, with a rule of its own.
  BOUND            otherwise: P2 and P3 hold and Step 2 is trusted. The
                   exported E(t) is the reflected front plus the compressible
                   stagnation load, at the worst point of the wall plane
                   (Step 2) and at G1 (Step 1), at both gammas. It is an upper
                   bound on the load a wall at x = 10 m takes during the
                   record, unrelieved by clearing and taken as uniform over
                   the wall. Beyond the record, the T1 rule applies. HD1-13
                   closes on route (b).

DELIVERED (text files, units in a header line):
  docs/hd13/vent3d_wall_load_G1.txt  every probe sample at G1: t [s]; and
                                     for g = 1.24 and 1.40: R, S, E
                                     [Pa over P_AIR]; un [m/s]; M
  docs/hd13/vent3d_wall_plane.txt    every write: t [s]; the plane maximum of
                                     E per gamma and where it sits; G1's cell;
                                     the panel means
  The T1 tail is not baked into the files, because its length (1.5 Tn) belongs
  to the wall being checked. The files state it as a rule: after the record,
  hold E_tail = max(p_open - P_AIR, max E) for 1.5 Tn of that wall.

REPORTED, NO VERDICT:
  - the example panel (C10's component above) through core/sdof under T0 and
    T1, for G1, G2, G3 and the plane maximum, at both gammas: mu, theta,
    regime, collapsed. UFC 3-340-02's support-rotation limits (2, 6, 12 deg)
    are listed beside them as reference only;
  - peak, positive-phase impulse and arrival of E for every trace
    (gauge_summary.summarize_trace on P_AIR + E);
  - |U| against un;
  - the C10 control: G1's static trace through the same call must give
    mu 0.3027 and theta 0.154 deg;
  - the Step 2 panel means (estimates, not bounds).
```

**Why the rule is shaped this way.** Each point is a requirement for "upper
bound" to be true, not a tuning choice.

- **A point on the jet axis, applied uniformly over the span, is an upper
  bound for the panel.** The jet footprint covers only part of the 3 m span,
  and a uniform load at the peak intensity loads the SDOF more than the real,
  non-uniform one. That holds only under two premises:
  - **P1:** the point sits where the wall load is largest. G1 is on the
    opening's geometric axis, but three probes cannot show that the jet core
    does not drift, for example toward the reflecting ground. Step 2 replaces
    the premise with a measurement: the maximum over the whole plane.
  - **P2:** the stagnation load is quasi-steady. A jet whose velocity arrives
    abruptly loads a wall with a reflected-shock transient. For the G1 state
    at 24.7 ms, the sudden-stop reflection is about 2x the pitot value.
    Pitot pressure bounds the wall only when the stagnation region has time to
    form, which needs at least one acoustic transit of the opening width
    during the rise.
- **T1 exists because the record ends while the jet still blows.**
  `window/drain` is 0.198. `sdof.response` releases the load at 30 ms, which
  is not a bound. The chamber's own pressure is a ceiling on any stagnation
  pressure the jet can deliver, as long as the chamber does not repressurise
  after the burst (P3).
- **Step 2 is read at write resolution (82.65 us after 8 ms).** That is about
  260 samples per Tn, five times finer than the SDOF's own Tn/50 step.
- **Clearing (UFC Eq. 2-8) needs the wall's height and width,** which the case
  does not define. Leaving clearing out is conservative.

---

## Part A - `HD1-13`, route (b): no-solve re-evaluation of the wall load

**TODO text (verbatim, `TODO.md` §HD1):**

> ### `HD1-13` · The wall load in the 3-D answer — owner decision
>
> `HD1-3d`'s 3-D answer (closed 2026-09-24, [DONE.md](DONE.md) §0) judged a 200 mm RC
> panel 4 m from the opening on the **side-on** trace of a gauge in free air: only the
> room is meshed (`build_vent_case`: `obstacles = m['boxes']`), so nothing at x = 10 m
> reflects. UFC 3-340-02 para. 2-15.3.2 (printed p. 65) loads a front wall with the
> **reflected** pressure and, after clearing, `Ps + C_D·q` (Eq. 2-9). The probes already
> record `U` and `rho`: on the jet axis ½ρ|U|² peaks at **114.6 kPa at 24.71 ms**, when
> the static trace reads −31.5 kPa (static + q peaks at 99.6 kPa, 2.4× the 41.47 kPa
> static peak — an incompressible estimate). So μ = 0.3027 and "survives" (C10, which
> passed as committed) may be **unconservative**. *Decide:* mesh the wall and read its
> face, or apply `Pr` and `C_D·q` to the trace — before "survives" is relied on. Either
> means a new solve; see the disk note under `HD1-14`.

**Interpretation (the owner's pick, route (b)):** "apply `Pr` and `C_D·q` to the
trace", made compressible, with **no new solve**. The TODO's "either means a
new solve" is true of route (a) only. Route (b) reads existing files.
- `C_D·q` becomes the compressible stagnation overpressure: isentropic below
  M = 1, Rayleigh pitot above. As M -> 0 it reduces exactly to Eq. 2-9 with
  C_D = 1, and A1 pins that.
- The code lives in `core/` (a pure function) and in `blastlab/tests/`
  (scripts). It stays out of the GUI.

### A1 · `core/wallload.py` - the wall load at a point  (size M; no WSL, no run data)

**Files:** `blastlab/core/wallload.py` (new) and `blastlab/tests/test_wallload.py`
(new). The module imports only numpy and `core.constants`. No GUI module imports
it.

**Functions** (names are a proposal):
- `reflected_overpressure(ps, gamma=1.4, p0=P_AIR)`: the rule's R.
- `stagnation_pressure(p, rho, un, gamma)`: absolute p0; isentropic for
  M < 1, Rayleigh pitot for M >= 1; `un < 0` is treated as 0.
- `wall_load(times, p, U, rho, gamma, normal=(1, 0, 0), p_amb=P_AIR)`: returns
  `dict(t, E, R, S, M, un)`. `U` may be (n, 3) vectors or (n,) normal speeds.
  Everything is vectorised, and NaN in gives NaN out, never 0.
- `extend_with_tail(times, load, level, duration)`: the T1 extension. The step
  width equals the last sample gap, never a vanishing gap, because
  `sdof.response` takes `dt = min(Tn/50, min sample gap)`
  (`core/sdof.py:322-325`). A 1e-9 s step would make that pure-Python loop
  tens of millions of steps long.
- The module docstring cites UFC para 2-15.3.2 / Eq. 2-9, Fig. 2-15 and
  Fig. 2-193 with their page markers. It states the two bound premises
  (P1, P2) in one paragraph.

**Acceptance** (`cd blastlab/tests && python test_wallload.py` ends
`WALL LOAD: PASS`):
- Pitot and isentropic agree **at M = 1** to 1e-12, for gamma = 1.24 and 1.40.
  For every M in (1, 5], **pitot < isentropic** strictly.
- **A textbook Rayleigh value.** p02/p1 at M = 2, gamma = 1.4 equals an
  independent derivation inside the test to 1e-12. That derivation is the
  normal-shock jump to M2 and p2/p1, then the isentropic relation behind the
  shock. Both equal 5.6404 to 1e-4. The formula's source is not a registered
  reference; see Needs clarification 9.
- **The reflection limits.**
  - Pr/ps -> 2 at vanishing overpressure: ps = 1e-6 p0 gives 2 within 1e-6.
  - Pr/ps -> (3g-1)/(g-1) = 8 at gamma 1.4 in the strong limit: ps = 1e6 p0
    gives 8 within 1e-4.
  - ps <= 0 comes back unchanged.
- **The low-Mach limit is UFC Eq. 2-9 with C_D = 1.** At M = 0.01, S equals
  ps + 1/2 rho u^2 to 1e-4 of 1/2 rho u^2.
- **UFC Appendix 2A anchors.**
  - The gamma-1.4 reflection coefficient at Pso = 10, 12.8 and 20 psi is within
    6 % of the chart readings 2.40, 2.70 and 2.90. Why 6 %: the appendix's own
    12.8-psi reading sits 6.3 % above its own 10-20 psi interpolation
    (2.70 against 2.54), so no closed form can be held tighter against it.
    The planner's R-H values are +5.5 %, -1.3 % and +2.7 %.
  - For the 12.8-psi post-shock state, 1/2 rho2 u2^2 is within 5 % of 3.5 psi,
    and S is within 5 % of 16.3 psi.
- **Gamma monotonicity.** At a fixed (p, rho, u), with M(gamma 1.4) spanning
  [0, 3], S falls strictly over a 17-point gamma grid in [1.24, 1.40]. R does
  the same at fixed ps. This is what makes the two ends bounds.
- **`wall_load` behaviour.**
  - An (n, 3) `U` gives `un = max(U . n, 0)`.
  - E >= ps at every sample.
  - E = R where u = 0 and ps > 0, and E = S where ps <= 0.
  - The output shape follows the input.
- **`extend_with_tail`.** The step width equals the last gap. `sdof.response`
  on the extended trace uses the same `dt` as on the bare trace.
- `test_regression.py` stays byte-green. `test_ui_no_vtk_in_main.py` and
  `test_ui_no_mpl_pyplot.py` stay green.

**References:**
- UFC 3-340-02:
  - para 2-15.3.1 (`=== page 140 ===`, p. 64);
  - para 2-15.3.2 and Eq. 2-8/2-9 (`=== page 141 ===`, p. 65);
  - Fig. 2-15 (`=== page 166 ===`, p. 90) and Fig. 2-193 (`=== page 344 ===`,
    p. 268). Read the PDF page for curve values; the text layer is axis labels
    only;
  - Appendix 2A worked examples (`=== page 486 ===`-`=== page 487 ===`,
    pp. 410-411; `=== page 501 ===`, p. 425).
- The Rayleigh pitot and normal-shock relations are not in a registered
  reference (Needs clarification 9).

**Dependency:** none.

### A2 · Step 1: the jet axis, from the probes  (size M; no WSL)

**The order inside this task is the pre-registration. Do not reorder it.**

1. **Commit `docs/hd13/vent3d_wall_rule.txt` first.** It holds the
   owner-approved rule verbatim, with the approval date (no S*: owner answer 1). Suggested
   message: `docs: HD1-13 route (b) - the decision rule, registered before the
   numbers`. No code that computes E on the evidence has run at that point.
2. **`reader.read_probes` gains `velocities`.** These are per-probe (n, 3)
   arrays, attached under exactly the guard `speeds` already has and built from
   the same `ua` array (`solvers/foam/reader.py:481-487`). `speeds` keeps its
   values. No consumer changes: `finalize_2d/3d` and `load_gauges` pick keys by
   name.
3. **`blastlab/tests/_e2e_vent_wall.py` (new, manual)** imports `build` from
   `_e2e_vent_3d` and never edits that file. It:
   - verifies sha256 of `case.json` and `gauges/0/{p,U,rho}` in the evidence
     copy against `SHA256SUMS.source`, and refuses on any mismatch. The default
     `--evidence` is
     `%USERPROFILE%\blastlab_evidence\20260923-195308_3d_p31468-00`;
   - checks identity key for key: `json.load(case.json) ==
     json.loads(json.dumps(case_to_dict(asm.build_vent_case(build())[0])))`
     (the `load_gauges` rule), and refuses otherwise;
   - prints the sha256 of `docs/hd13/vent3d_wall_rule.txt`;
   - runs the **C10 control**: `sdof.response(t, p_G1, comp, p_ref=P_AIR)`
     must give mu 0.3027 and theta 0.154 deg to the printed digits, or the
     script stops;
   - for G1, G2 and G3 at gamma 1.24 and 1.40 computes E, then the SDOF under
     T0 and T1, then `summarize_trace(t, P_AIR + E)`;
   - computes P2 at G1, and P3 from `info['zero_d']` (`t`, `p`),
     `info['state']` and `info['validity']['tau_drain']`;
   - prints Step 1's part of the rule (P2 and P3), and writes the delivered
     trace `docs/hd13/vent3d_wall_load_G1.txt` in the rule's layout, with units
     in a header line and the T1 rule stated there.

   The script writes nothing under the evidence dir or any run dir. Its record
   is its stdout; `--out DIR` adds trace files outside both.
4. **`blastlab/tests/test_vent_wall.py` (new; no WSL, no GUI).** It uses a
   synthetic evidence dir holding `case.json` from `build()`, p/U/rho probe
   files in the blastFoam 6.2 layout, and a matching `SHA256SUMS.source`. It
   pins:
   - E equals `wallload.wall_load` on the same arrays;
   - T0 and T1 are built as the rule says;
   - one changed byte in `U` is refused on sha256, and a changed case field is
     refused with the field named;
   - the directory tree is unchanged afterwards (the `tree()` idiom of
     `test_vent3d_load.py`);
   - P2 on a synthetic u rising linearly over 5 ms gives 4.0 ms, and P3 gives
     the expected ratio on a synthetic 0-D dict;
   - **the outcome function maps every combination** of (P2, P3, Step 2
     trusted, Step 2 runnable read-only) to BOUND or NOT ESTABLISHED exactly as
     the rule says, with first match winning. No SDOF result enters it;
   - the delivered trace file round-trips: its header names the units, and
     re-reading it gives the same R, S, E arrays.
5. **`test_foam_reader.py`:** `velocities` is present and aligned when U
   aligns, `speeds == norm(velocities)`, and it is absent in the existing
   torn-U case.
6. **Only then:** `python -u _e2e_vent_wall.py`, in the foreground. Keep the
   output for A4.

**Acceptance:**
- `git log --follow docs/hd13/vent3d_wall_rule.txt` shows the rule's commit
  **before** the commit that adds the record (A4). The sha256 printed in the
  record matches the committed rule file.
- The C10 control reproduces mu 0.3027, theta 0.154 deg, dynamic.
- Step 1 prints, for {G1, G2, G3} x gamma {1.24, 1.40} x {T0, T1}: mu, theta,
  regime, collapsed; E's peak, positive-phase impulse and arrival; |U| vs un.
  It also prints P2's rise against D/a, P3's ratio, and Step 1's outcome.
- Gates green: `python test_wallload.py`, `python test_vent_wall.py`,
  `python test_foam_reader.py`, `python test_vent3d_load.py` (unchanged,
  15/15), and `python test_regression.py`.
- `git diff --stat` shows no change to `blastlab/tests/_e2e_vent_3d.py`.

**References:**
- UFC Sec. 3-19 / 3-19.2.1.2, the recurrence `core/sdof.py` follows
  (`=== page 672 ===`-`=== page 673 ===`, pp. 597-598); Table 3-12, K_LM
  (`=== page 670 ===`, p. 595).
- blastFoam guide sec. 15.1 blastProbes (pp. 122-123): the default `cell`
  interpolation samples the elected cell's own value every step, and `append`
  keeps one file across restarts.

**Dependency:** A1. The rule approval (Needs clarification 1) is needed before
step 1.

### A3 · Step 2: the plane x = 10 m, read-only from the run  (size M; WSL read-only, about 10 min of reading)

**What it computes.** It reads p, U and rho for **every** written time from the
run's reconstructed root time dirs, over 9p
(`\\wsl.localhost\Ubuntu\root\blastlab_runs\20260923-195308_3d_p31468-00`). The
reader is the live ingest's own (`backend.read_3d` on a spec from
`writer.render_case(cfd, n_procs=13)` in memory, as hd1-3d-close's H1 did). So
the grid mapping is the one the foam tests pin. For each write it:
- keeps the two cell layers either side of x = 10 m, located from
  `spec.grid['x_c']` and not hard-coded;
- computes E per cell at both gammas;
- keeps these reductions:
  - the plane maximum of E per gamma, and where it sits;
  - the eight cells around (10, 6, 1.4), for the mapping check;
  - report-only panel numbers over the footprint of Needs clarification 2: the
    area mean of E, the area mean of the momentum flux
    `max(0, p - P_AIR + rho un^2)`, and the strip mean over z at y = 6.
- Then it runs the SDOF on the plane-max trace (748 samples plus t = 0), at
  both gammas, under T0 and T1.

**Why it runs, and when.** Run it **always, and before B3.**
- BOUND needs Step 2. Its mapping check replaces premise P1 (that G1 sits where
  the wall load is largest) with a measurement: the maximum over the whole
  plane. The plane maximum includes G1's own cell.
- The fields may not survive the corpus sweep once B3 adds runs (Risks 8).
- **Panel means are estimates, not bounds.** A wall spreads the stagnation
  region wider than the free jet. A steady jet fully turned by a large wall
  loads it with its whole momentum flux, int(p - p_a + rho u^2) dA, not with
  int(p - p_a + 1/2 rho u^2) dA. A free-air pitot average can therefore read
  low. That is why both means are reported and neither is judged.

**Protocol (the run dir is evidence; same fingerprint as hd1-3d-close):**
- **Before:** the process scan comes back empty (blastFoam, mpirun, orted,
  reconstructPar, decomposePar, postProcess, foamToVTK). Record the run dir's
  `du -sb`, newest mtime, and file/dir counts. Take a sha256 over
  `find "$R" -printf '%P %s %T@\n' | LC_ALL=C sort`, plus sha256 of `case.json`
  and `gauges/0/{p,U,rho}`. The WSL script sits in the session scratchpad and
  writes to stdout only.
- **Reads:** root time dirs only, never `processor*`. No postProcess,
  reconstructPar, foamToVTK or any OpenFOAM utility. No `postmortem.load_run`,
  because it reconstructs into the run. No numpy install inside WSL.
- **During:** repeat the process scan at least every 30 s. **After:** take the
  same fingerprint again; it must be identical.
- **Output:** `--out` to a scratch directory, plus a committed
  `docs/hd13/vent3d_wall_plane.txt`. That file holds, per write: t, the plane
  maximum of E at both gammas and where it sits, the values at G1's cell, and
  the panel numbers. It is a text file of a few hundred KB.
- **If WSL is torn down mid-read** (§8.3), restart the extraction from the top.
  It is idempotent and writes nothing in WSL.

**Acceptance:**
- The fingerprints before and after are identical, and the process scan is
  empty throughout. Record the wall time and the bytes read (about 25.9 GB,
  5-9 min expected).
- **The mapping check.** One cell among the eight matches G1's probe at all 267
  writes after 8 ms, to the rule's tolerances. If it does not, Step 2 is
  **untrusted** and the rule gives NOT ESTABLISHED. That is an outcome, not a
  threshold to loosen.
- The plane-max trace goes through the SDOF at gamma 1.24 and 1.40, T0 and T1,
  with Step 2's part of the rule printed.
- The pure parts are pinned in `test_vent_wall.py` on synthetic arrays:
  choosing the layers from `x_c`, the max/argmax reduction, the mapping check
  passing and failing, and the panel means on a field with a known answer.

**References:** blastFoam guide sec. 15.1 (pp. 122-123). The probe value is the
elected cell's own value, and that is what makes an exact mapping check
possible.

**Dependency:** A2, with the rule committed and Step 1 run.

### A4 · The outcome and its record  (size S; no code beyond A2/A3)

- Save the complete output of Steps 1 and 2 as `docs/hd13/vent3d_wall_load.txt`.
  It carries:
  - the rule file's sha256 and the evidence sha256 lines;
  - A3's before/after fingerprint;
  - P2, P3 and the mapping check;
  - the example panel's report-only responses (T0 and T1, both gammas);
  - the final line `HD1-13 ROUTE (b): BOUND | NOT ESTABLISHED - <which
    conditions>`, **printed by the outcome function, not typed**.
- Draft the bookkeeping text for the orchestrator, who makes the edits:
  - **BOUND:** `HD1-13` leaves TODO.md. A closure paragraph goes under DONE.md
    §0's HD1-3d entry. It names the delivered load files and gives E's peak
    and impulse at G1 and on the plane (gamma 1.24) and the bound's wording
    from the rule. It gives the example panel's mu and theta as a report,
    beside the UFC reference limits, and says no survival verdict is given:
    each wall is judged by its own criterion (owner, 2026-09-24). It cites the
    record, and the rule file with its sha256. The HD1-3d entry's "What the
    PASS does not establish" note gains one sentence: C10's "survives" was
    judged on the side-on load, and the wall load is now in `docs/hd13/`.
  - **NOT ESTABLISHED:** `HD1-13` stays in TODO.md with a dated line carrying
    the failed condition, the numbers and "route (a) next, after HD1-15". The
    load files are still committed and labelled "not a bound".
    `docs/ENGINEERING_QUESTIONS.md` gains a section for this batch.
  - In every branch: C10 and `_e2e_vent_3d.py` stay as they are. No number is
    quoted without its gamma and its tail. No text says any wall survives or
    fails.

**Acceptance:**
- Every number in the bookkeeping text appears in `vent3d_wall_load.txt` or in
  the delivered load files.
- Impulse, arrival and the example panel's mu and theta carry no PASS/FAIL.
- The outcome line matches the rule's table for the printed conditions.

**Dependency:** A2, A3.

---

## Part B - `HD1-15` (proposed id): an opt-in per-case write budget for blastFoam runs

**Proposed TODO text** (new; the orchestrator files it):

> ### `HD1-15` · A write budget for blastFoam runs, opt-in per case
>
> The adaptive writeInterval controller (`runloop.next_interval`) is clamped to
> [iv0/4, 8·iv0]. iv0 is sized from a charge-centred shock-transit estimate
> (`writer._timing`), not from the window asked for. So the HD1-3d chamber run made
> **748 writes in 30 ms**, and each was kept twice, reconstructed (~130 MB) and
> decomposed: **172.96 GiB**. `write_budget = N` on a 2D/3D blastFoam case with an
> explicit end time pins writeInterval to t_end/N. It keeps the decomposed copy only
> for the latest complete write, for W3/N6 resume. Default 0: nothing changes.

**How it plays out on the HD1-3d case at N = 60:**
- root copies: 60 writes x 130.7 MB = 7.8 GB;
- one decomposed write: about 0.14 GB;
- `processor*/constant`: 0.12 GB;
- `processor*/0`: about 0.04 GB.

That is **about 8.1 GB, against 172.96 GiB**.

**What the option must not break** (read from the code):

| Consumer | Why it is safe with the option on | Pinned by |
|---|---|---|
| W3 auto-resume and N6 manual resume (`backend.resume_run`, `startFrom latestTime`) | A parallel restart reads the newest `processor*` time. The purge never deletes the newest time complete on every rank, nor a write in progress | B2 planner tests; B3 stop + resume |
| P1-5 walk-back (`backend._resume_start_time`) | It walks back only on AMR. Decomposed AMR is never purged, and serial runs have no `processor*` | B2 |
| `postmortem.load_run` (`postmortem.py:71, 92-95`) | It counts `processorN` dirs and reconstructs only times missing at the root. The purge keeps every `processorN/`, its `constant/`, `start_dir` and the newest time, and the root keeps every write | B2 fake-run test |
| Result snapshots and the final read (`finalize_3d`, `_final_read`) | They read the reconstructed root dirs, which are never purged | B3 |
| Frames and the animation export (`record_frames`, `output/animation.py`) | One frame per ingested write: fewer frames, same code path | B3 |
| Peak and impulse maps | The per-step FOs write into every write, and the final one carries the whole run | B3 |
| Gauges | blastProbes samples every step, independent of writes | B3 (contiguous rows) |
| Live view (`tail_live`, `due_sparse`; `test_foam_live_due.py`) | The live slice samples every N steps. Only the 3D frame feed follows writes | `test_foam_live_due.py` unchanged |
| Shock-arrival stop | The live-slice rim check (N3-01) runs every step. A terminate side normal to the slice is checked at writes only, so it can be up to t_end/N late | a B1 validation note |
| B23 determinism | A budget pins the schedule, as `adaptive_write=False` does | `test_adaptive_interval.py` idiom |
| Chain hand-off (the `writeTimeList` end-time write) | The end time is still written | B3 (last write is t_end) |
| Goldens, regression, every saved `case.json` | A default case (0) renders and serialises byte-identically | B1 |

### B1 · The option: case field, pinned interval, validation, JSON  (size M; no WSL)

**Files:**
- `core/case.py`: add `write_budget: int = 0` on `Case2D` and `Case3D`. No 1D
  field: a 1D run is serial and ASCII, and it is small.
- `solvers/foam/writer.py`: add `CaseSpec.write_budget`. `plan_case`, via
  `_timing`, sets `write_interval = end_time / write_budget` when the budget is
  set.
- `solvers/foam/backend.py`:
  - `solve_2d_foam` and `solve_3d_foam`: the `spec.adaptive_write`
    expression (`backend.py:1940-1941` and its 2D twin) gains
    `and not case.write_budget`;
  - the banner says `(pinned: write budget N)` only when the budget is set.
    The default banner line is unchanged, because it is load-bearing.
- `blastlab/tests/test_write_budget.py` (new), and new cases in
  `test_case_validate.py`.

**Validation rules** (in the 2D/3D shared block, `core/case.py:915-936`):
- The budget is an integer >= 0. A value > 0:
  - needs `t_end > 0` (error: the automatic end is a 10x safety cap);
  - needs a budget >= 2 (error);
  - on a native solver, gets a note that it is ignored.
- Warning when the budget is below 4 x `n_snapshots`, the writer's own
  `_n_writes` rule.
- Note when a terminate side lies normal to the live slice: arrival is
  checked at writes only.
- Note on a decomposed-AMR case: no purge.
- Note giving the expected disk: N writes x about 155 B per cell (measured:
  130,677,089 B / 841,704 cells, 14 fields) plus one decomposed write.

**JSON.** `case_to_dict` **omits `write_budget` when it is 0**, and `VERSION`
stays 13. A case without a budget then serialises byte for byte as today, and
the HD1-3d identity check (`_e2e_vent_3d.load_gauges` compares every key,
`version` included) keeps accepting the committed run. This **deviates from
the §8 convention** that a declared field bumps `VERSION` (13 was
`adaptive_write`); see Needs clarification 7.

**Acceptance:**
- **Default unchanged:**
  - `python test_foam_writer.py` is green with no `--update`;
  - `git status --porcelain blastlab/tests/foam_golden blastlab/tests/foam_fixtures
    blastlab/tests/baseline` is empty;
  - `python test_regression.py` prints `REGRESSION PASS`;
  - `case_to_dict(Case2D())` and `case_to_dict(Case3D())` have no
    `write_budget` key;
  - the evidence `case.json`
    (`%USERPROFILE%\blastlab_evidence\20260923-195308_3d_p31468-00\case.json`)
    still equals `case_to_dict(asm.build_vent_case(build())[0])` key for key.
    This needs no WSL.
- **With WSL up** (read-only):
  `python -u _e2e_vent_3d.py --load 20260923-195308_3d_p31468-00` still prints
  `case.json matches this CFD case, all 56 fields` and ends `VENT 3D: PASS`.
- **With the option on:**
  - rendering a 3D blastFoam case with `t_end=0.03, write_budget=60` writes the
    top-level `writeInterval 0.0005`;
  - the spec's `adaptive_write` is False;
  - `runloop.maybe_adapt` then makes zero controlDict rewrites (the
    `test_adaptive_interval.py` idiom);
  - `save_case` / `load_case` keep `write_budget = 60`.
- Each validation rule above has one case in `test_case_validate.py`.
- The fast matrix is green (Final gate).

**References:** blastFoam guide sec. 15.3 writeTimeList (p. 124): the end-time
write the writer already plants, which a pinned budget must not duplicate or
lose.

**Dependency:** none in code. B1 and B2 may run before or after Part A. Only B3
has to wait for A3 (Risks 8).

### B2 · Keep the decomposed copy of the latest write only  (size M; no WSL)

**Files:**
- `solvers/foam/runloop.py`:
  - `maybe_reconstruct` returns the times a **successful** reconstructPar call
    covered. Existing callers ignore the return value.
  - A new pure planner, `decomposed_purge_plan(done, reconstructed_ok,
    common_ready, start_dir)`.
  - `FoamRunLoop._purge_decomposed()`, called at the end of `_ingest_ready` and
    after the final sweep.
- `blastlab/tests/test_write_budget.py`.

**Rule.** The purge is active only when `spec.write_budget > 0 and
spec.n_procs > 1 and not spec.decomposed`. It deletes `processor*/<t>` on all
ranks, with one `rm -rf` stage in WSL per purge, for every t that meets all of:
1. the ingest has read it (`done`);
2. a reconstructPar call covering it returned 0;
3. it is older than the newest time complete on every rank;
4. it is not `spec.start_dir`.

It never touches `processor*/constant`, the case root or `postProcessing`. A
failed delete is logged once and retried; it never raises. The deleter refuses
any path that is not `<case>/processor<N>/<numeric time>`.

**Rejected alternative: OpenFOAM's `purgeWrite`.** It deletes on the solver's
clock, which races the per-poll reconstruct (capped at 4 per poll,
`runloop.py:168`). A write purged before it was reconstructed would be lost
from the record. `purgeWrite` is not in the registered guide.

**Acceptance (no WSL):**
- **Planner properties:** the plan never contains
  - the newest complete common time;
  - `start_dir`;
  - a time not in `done`, or not in `reconstructed_ok`;
  - a time newer than the newest complete one (a torn write).

  The plan is empty when the budget is 0, when `n_procs <= 1`, and when
  `spec.decomposed` is set.
- **A fake run** in local directories: 2 ranks, `0` plus 4 times. Three are
  reconstructed and ingested, and the 4th is partial on rank 1. After the
  purge:
  - `processor*/` hold {constant, 0, t3, t4 (partial)}, and the root is
    untouched;
  - `backend._n_procs_on_disk` still reports 2;
  - `backend._resume_start_time` picks the latest root time;
  - a second purge is a no-op.
- With `write_budget = 0`, a spy deleter records **zero calls** through a
  whole fake ingest.
- These stay green and unchanged: `test_foam_resume.py`,
  `test_foam_postmortem_decomposed.py`, `test_foam_ingest_order.py`,
  `test_foam_amr_ingest.py`, `test_foam_wsl_resume.py` (no WSL, per its
  docstring), `test_adaptive_interval.py`, `test_foam_live_due.py`.

**References:** blastFoam guide sec. 11.2-11.3 (p. 112), dynamic load
balancing. A balanced parallel AMR run keeps its times per rank, so the purge
must never touch a decomposed run.

**Dependency:** B1.

### B3 · One real run, and the WSL gates  (size M; WSL, about 1 h)

**Preconditions:**
- A3 has finished; this batch no longer needs the evidence fields.
- Needs clarification 3 is answered: option (c), see the corpus guard below.
- The process scan is empty.
- Record `ls -1t /root/blastlab_runs`, and free space on C: and in WSL.

**`blastlab/tests/_e2e_foam_write_budget.py`** (new) uses the tiny 3D case of
`test_foam_3d_smoke.py --tiny` (0.6 m box, `n_procs = 2`) with an explicit
`t_end` and `write_budget = 10`.
- **Run A, to the end:**
  - the root has 10 writes after 0, or 11 only if the end-time write lands one
    step apart;
  - each `processorN` holds {constant, 0, the final time};
  - the root copy of every purged time reads back (`reader.read_scalar` on its
    `p`);
  - the Result has snapshots and at least 2 frames;
  - the probe rows run contiguously to t_end;
  - the run's `du -sb` is at most (writes + 2) x one write x 1.1.
- **Run B, stop and resume:** the same case, stopped through `should_stop`
  after the 4th write, then `backend.resume_run(dir)` to t_end. The root ends
  with the same write count as run A, the probe rows are continuous across the
  restart (`read_probes` merges the chunks), and each `processorN` ends with
  {constant, 0, final}.

**The WSL gates** (targeted, because `writer`, `runloop` and `backend`
changed), one at a time, in the foreground, with a process check between them:
`test_foam_3d_smoke.py --tiny`, `test_foam_parallel.py`, `test_foam_stop.py`,
`test_foam_postmortem.py`.

**Corpus guard (owner answer 3, option (c)).**
- **Before B3's first WSL run:** record the run list `ls -1t /root/blastlab_runs`.
- **After each WSL run:** list the runs again. The names that are new against
  the recorded list are the runs B3 created.
- **Once a run's results are recorded:** delete that run by its exact path,
  `rm -rf -- /root/blastlab_runs/<exact name>`. Only a name on B3's own new-name
  list may be deleted, and only after its results are in the handback.
  - The script refuses any other path, anything outside `/root/blastlab_runs/`,
    and any glob.
  - The evidence run `20260923-195308_3d_p31468-00` and every run that existed
    before B3 are never deleted.
- **Stop and report** if the evidence run leaves the 10 newest anyway, for
  example because something else created runs.
- Never start the GUI, and never edit a settings file.

**Acceptance:**
- Runs A and B behave as above.
- The four suites pass.
- The handback lists:
  - the run list before and after;
  - B3's new-name list and every deletion made, each by its exact name;
  - the free space.
- After B3, the run list equals the list recorded before it: every B3 run has
  been deleted, and nothing else has been.

**Dependency:** B1, B2; A3 done; Needs clarification 3 answered.

---

## Final gate

From `blastlab/tests`, one at a time, with no WSL beyond the B1/B3 items above:
- **The whole fast no-WSL matrix of TODO.md** ("The test matrix"), including
  `test_regression.py` byte-for-byte, `test_foam_writer.py` without `--update`,
  and `test_foam_wsl_resume.py`.
- **The new suites:** `test_wallload.py`, `test_vent_wall.py`,
  `test_write_budget.py`.
- **The GUI suites:** the offscreen `test_ui_*` suites, and the 9 Tk
  `test_gui_*` suites that CLAUDE.md §9 requires when shared neutral modules
  change.
- `test_blast3d.py` only if the orchestrator wants the slow one; no native code
  changes.
- `git status --porcelain` shows nothing under `foam_golden/`, `foam_fixtures/`
  or `baseline/`.

---

**Batch total.**
- Part A, about 1 day: A1 M + A2 M + A3 M (about 10 min of reading) + A4 S.
- Part B, about 1 day: B1 M + B2 M + B3 M (about 1 h of WSL).
- Overall L. It can be split at the Part A/Part B line, with A3 first.

---

## Risks

1. **Judging after the numbers.** The guards:
   - the rule is committed before any E is computed on the evidence, and the
     record carries its sha256;
   - the outcome is printed by a function that `test_vent_wall.py` enumerates
     for every input combination;
   - the planner ran no SDOF on any new load;
   - C10 and `_e2e_vent_3d.py` are not edited.
2. **Route (b) produces a load, not a verdict** (owner answer 1). NOT
   ESTABLISHED means that the trace is not claimed as an upper bound. It does not
   mean that any wall fails. The example panel's response is reported only, and
   the bookkeeping text must not say that any wall survives or fails.
3. **The bound's premises.** P1 (location) is replaced by Step 2's plane
   maximum. P2 (quasi-steady stagnation) and P3 (the chamber does not
   repressurise) are checked against numbers set before the run. P2's length
   scale, the 1.2 m opening width, is the smallest defensible one; a wider jet
   would make the check stricter. The owner may amend it (Needs clarification
   1).
4. **The tail dominates if the record is short.** With T1, the maximum
   response may fall after 30 ms. That is the point of T1: the window/drain
   ratio is 0.198 (ENGINEERING_QUESTIONS #5). T1 is a rule applied per wall,
   because its length is 1.5 Tn of that wall. If the example panel's response
   is dominated by the T1 tail, the report says so, and route (a) would want a
   longer window.
5. **Free-air panel means are not bounds** (A3). They are reported only.
6. **Clearing is not modelled** (UFC Eq. 2-8 needs the wall's height and
   width). Leaving it out is conservative, and the record says so.
7. **Numerical results.** `core/sdof.py` does not change. The C10 control must
   reproduce mu 0.3027 before anything else is printed. `test_regression.py`
   stays byte-green. `core/wallload.py` is new and is imported by nothing in
   the GUI.
8. **The evidence run and the corpus sweep.**
   - The app reads the Store-virtualised settings: auto-cleanup on, 150 GB, 14
     days, keep 10 (ENGINEERING_QUESTIONS #3).
   - The corpus is far over 150 GB, so any run outside the 10 newest goes at
     the next real GUI start. The evidence run alone is 173 GiB.
   - B3's runs, plus about 5-8 from the four WSL suites, can push it out of the
     10 newest. The 30 KB run has already been swept since the morning.
   - Mitigations: A3 runs before B3; B3 carries the corpus guard; and
     Needs clarification 3 must be answered first. No harness or real window
     runs in this batch (checked: every harness writes `auto_cleanup: false`).
9. **Reading 26 GB over 9p.** It is read-only by protocol, with a fingerprint
   before and after and the process scan throughout. WSL can be torn down under
   a long read (§8.3); the extraction is idempotent, so it restarts. Before A3,
   confirm that nothing else is using WSL.
10. **B2 deletes data inside WSL, irreversibly.** The guards are:
    - a pure planner with property tests;
    - a deleter that refuses any path outside `processor<N>/<time>`;
    - no purge at `write_budget = 0` (a spy proves zero calls);
    - no purge on decomposed AMR runs;
    - B3 checks that the root copy of every purged time is readable.
11. **Schema drift.** Omitting the field when it is 0 keeps every default
    `case.json` byte-identical, and the HD1-3d evidence identity check keeps
    passing (B1 acceptance). A `VERSION` bump would make `--load` refuse the
    committed run (Needs clarification 7).
12. **Goldens.** The default path is unchanged by construction. Any movement
    under `foam_golden/` means a bug, never an `--update`.
13. **GUI round trip.** The Qt form builds a fresh `Case3D(...)`
    (`ui/case_form.py:540`), so a case with `write_budget` loses it when edited
    and saved in the GUI. This is documented; exposing it in the GUI is
    backlog.

---

## Needs clarification

*(All answered or deferred on 2026-09-24. See "Owner answers" at the top, which
override anything below. Item 1 was answered "no criterion - the load is the
product"; the S* options stay below for reference only.)*

1. **The decision rule and the survival criterion S\*.** Approve the rule text
   above, choosing one S*. Every option's mu and theta are reported whatever
   is chosen.

   | Option | Criterion | This component | UFC 3-340-02 (sidecar marker, printed page) |
   |---|---|---|---|
   | A | not collapsed, theta < 12 deg (`core/sdof` default; C10 as committed) | mu < 23.9 | 12 deg is incipient failure of a **laced** element (para 4-9.3, `=== page 1126 ===`, p. 1050), or of a laterally restrained non-laced one in tension membrane (para 4-25.1, `=== page 1173 ===`, p. 1097). `core/sdof` models flexure only, with no membrane branch, so 12 deg assumes restraint the model does not represent. |
   | B | mu <= 1, elastic | theta <= 0.51 deg | Not a UFC limit. The strictest reading. |
   | **C (recommended)** | theta <= 2 deg | mu <= 3.93 | At 2 deg "the compression concrete crushes. For elements without shear reinforcement, this crushing ... results in failure" (para 4-9.1, `=== page 1124 ===`-`=== page 1125 ===`, pp. 1048-1049). Without lateral restraint, incipient failure is at 2 deg, or 6 deg with adequate single-leg stirrups (para 4-25.1, `=== page 1173 ===`, p. 1097). "For personnel protection, the maximum deflection is limited to a support rotation of 2.0 degrees" (para 4-37, stated for beams, `=== page 1271 ===`-`=== page 1272 ===`, pp. 1195-1196). That is Protection Category 1 (para 1-9, `=== page 84 ===`, p. 8). |
   | D | theta <= 6 deg | mu <= 11.8 | Non-laced elements with shear reinforcement reach 6 deg (para 4-9.2, `=== page 1125 ===`, p. 1049). "Structures intended to protect equipment and/or explosives may be designed for deflections up to incipient failure conditions" (para 4-37, p. 1196), i.e. Protection Category 2. But para 1-14.2.2 (`=== page 102 ===`, p. 26): "In the event personnel and/or expensive equipment is being protected ... incipient failure design is not permitted." |

   **Why C.** The case defines a 200 mm RC panel with **no detailing**: no
   stirrups and no lateral restraint are stated. For such an element, 2 deg is
   UFC's own incipient-failure rotation. It is also where the SDOF's
   elastic-perfectly-plastic flexure stops being a valid model, and it is the
   personnel-protection limit. A and D each assume detailing the case does not
   state.

   The owner may also amend three judgement elements of the rule:
   - the T1 tail ceiling (the chamber pressure);
   - P2's length scale (1.2 m);
   - the mapping tolerance (1e-5, set by the probe file's 6-digit print).

   **Proposed text for the owner to approve:** the fenced block under "The
   decision rule", with S* = option C, the date filled in, and nothing else
   changed.
2. **Panel footprint for the report-only means (A3).** Proposed: y 4.5-7.5 m,
   z 0-3.0 m, a 3 m vertical span from the ground, centred on the opening
   axis. No verdict depends on it. The case gives `span_m = 3.0` but no
   position or width.
3. **Settings file and a dry-run cleanup** (ENGINEERING_QUESTIONS #3,
   CLAUDE.md §8.2).
   - Which file governs? Python resolves
     `%APPDATA%\blastlab\settings.json` (auto_cleanup false) to the
     Store-virtualised copy (auto_cleanup **true**, 150 GB, 14 d, keep 10).
   - Should §8.2 say that `env.auto_cleanup(settings.load())` deletes, and that
     the dry run is `env.cleanup_policy` on the listed sizes and mtimes?
   - New since the morning: the 30 KB run is gone, and B3 will add runs.
     Before B3, choose one:
     (a) set `auto_cleanup: false` in the file the app reads;
     (b) accept that the evidence fields may go at the next GUI start (the
         lightweight evidence copy stays);
     (c) let the batch delete, by exact name, only the runs B3 itself created;
     (d) drop B3's suites to the e2e alone.
   - Not in this batch unless the owner adds it.
4. **Delete the superseded 30-snapshot run `20260922-132259_3d_p3756-00`?** It
   is 191.63 GiB, and the same case except `n_snapshots` (30 against 6). Not
   in this batch. Note that the vhdx does not shrink (§8.5), so this frees
   space inside WSL only.
5. **Close `HD1-4` as not needed?** The chamber route used none of its
   blockers. The orchestrator recommends closing it. The only reason to keep it
   is the `AbelNobel` fallback. Not in this batch.
6. **`HD1-14`'s timing.** The orchestrator recommends deferring it until after
   this batch. With HD1-15 its disk cost drops from about 190 GB to about
   8 GB per run.
7. **JSON versioning for `write_budget`.**
   - Recommended: omit the field when it is 0 and keep `VERSION = 13`, as
     B1 proposes. Default files stay byte-identical, and an older blastlab
     refuses a budget file with "Unknown case keys".
   - The §8 convention instead: `VERSION = 14`, plus teaching
     `_e2e_vent_3d.load_gauges` to ignore `version` and absent keys that
     equal their default. That touches the script verified in hd1-3d-close;
     its identity-refusal mutant must still fail.
8. **The TODO id.** `HD1-15` is proposed: it unblocks HD1's route (a) and
   HD1-14, and it inherits HD1's place above P0. The alternative is `P3-26`,
   under performance/disk, if the owner prefers to file it as generic
   infrastructure.
9. **Optional:** register NACA Report 1135 (the compressible-flow tables) with
   `/ref add` if the Rayleigh test value (p02/p1 = 5.6404 at M = 2) should cite
   a page. Without it, the test derives the value by two independent closed
   forms and cites none.

---

## Remaining backlog

- **Route (a)**, if HD1-13's load is NOT ESTABLISHED as a bound:
  - mesh a wall box at x = 10 m and read its face with
    `viz3d.sampling.extract_loads` then `sdof.face_trace`;
  - run with HD1-15's budget (about 60 writes, about 8 GB) and a window long
    enough to see the jet after its peak;
  - register its own rule first. WSL, L.
- **`HD1-14`:** the 24-cell `Cd` point, after HD1-15. The convergence threshold
  is registered before the run. WSL, M-L.
- **`HD1-4`:** close or keep (Needs clarification 5). S.
- **Closed-vessel data** for a real material: no code, and the highest-value
  HD1 step.
- **ENGINEERING_QUESTIONS #4, #5 and #6.**
  - #4: C8 is narrow.
  - #5: the negative phase is still open at 30 ms. T1 covers the positive side
    for the bound.
  - #6: the arrival rule is a definition note.
- **HD1-15 follow-ups:**
  - the field in the GUI, with Qt and Tk parity, then gui-qa;
  - a default interval sized from an explicit window for chamber cases. That
    changes a default, so it means goldens and regression.
- **`docs/batches/2026-09-24-p1-settling-runs.md`:** T9 (the audit-correction
  docs residue), the N5-11 `RHO_MIN` run, the fixed-timestep run on the ~2 %
  parallel offset, and the stale TODO entries that plan lists.
- **Then, as the hd1-3d-close plan lists them:** the Claim 3 experiments;
  viewer colour scales (P3-25, P3-8); remap-chain honesty (P3-15, P3-10 with a
  re-baseline, P3-9); detonation-point GUI tables (N5-12, P3-21, P3-13); writer
  options (the P3-3 remainder, P3-24, P3-23, P3-4); P3-18 with a KB refit;
  large mesh work; performance; and P2-5, which needs a person at the screen.
