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
