# Batch 2026-09-26 · hd1-16-load-export

**Goal (one sentence):** make the HD 1.3 assessment deliver its chamber load
as SBEDS-ready CSV traces and stop reporting any in-app structural response
(μ, support rotation, verdict), and fix the two HD 1.3 texts that overstate
(`HD1-16` step 1 for the 0-D traces, plus `HD1-17(a)`).

- Branch at planning time: `ux-2-keep-result-on-write-failure`, BASE `01ab997`.
  Start a topic branch from BASE, e.g. `hd1-16-load-export`.
- Order source: `TODO.md` (HD1 sits above P0, CLAUDE.md §6). `HD1-16` and
  `HD1-17` are the only HD1 items with implementable parts. `HD1-14` is an
  optional WSL run, `HD1-4` waits for an owner decision, and `HD1-17(b)` and
  `HD1-16` step 2 are owner-gated.
- **No WSL in this batch.** The whole HD 1.3 track is 0-D (`core/deflagration`,
  `core/sensitivity`, `core/assessment`). No foam file, no solver default and no
  native solver is touched.
- Total size: **L** (1 × S, 2 × M, 1 × L, 1 × S of tests). Step 2b was added after the
  owner answered Q1 on 2026-09-26.

---

## 0. Pre-flight (before any step that builds a GUI) · CLAUDE.md §8.2 / TODO `P0-5`

`P0-5` itself is **not** in this batch (it touches `core/settings.py` and
`solvers/foam/env.py`, which share no file with this batch; see §5). Its stop-gap is
in place (DONE.md §0a). These checks are **non-destructive**. Do not use the old
check `env.auto_cleanup(settings.load())`: TODO `P0-5` item 4 records that it
deletes when the flag is on.

1. `python -c "from blastlab.core import settings as s; d=s.load(); print(s.config_path(), d['auto_cleanup'])"`
   must print `False`. Under Store Python the path shown is `%APPDATA%\...`, but
   the file actually read is the virtualised copy (`P0-5`). Also open
   `%LOCALAPPDATA%\Packages\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\LocalCache\Roaming\blastlab\settings.json`
   with the Read tool and confirm `"auto_cleanup": false`.
2. Every offscreen `test_ui_*` / `test_gui_*` suite and `_e2e_hd13_gui.py` sets
   `BLASTLAB_SETTINGS` to a throwaway file (`ui/testing.private_settings`,
   `_e2e_hd13_gui.py:37`). Do not unset it.
3. Before any real-window run, copy out any run you care about from
   `/root/blastlab_runs`. `wsl -d Ubuntu -- pgrep -a blastFoam` needs checking only if a WSL
   suite is run, and none is planned.
4. `cd blastlab/tests; python test_regression.py` is green **before** the first
   commit, as the baseline for "byte-identical".

---

## 1. Tasks, in order

Each step leaves the app runnable. Commit style is `area: what changed`, citing the ID.

### Step 1 · `HD1-17(a)` · The HD 1.3 texts that overstate · **S**

Original TODO text, verbatim:

> **(a) Texts. No number or threshold moves.**
> 1. The comment at `MACH_QUASI_STATIC` says the model's cases "come out two to three
>    orders below it". The starter case is 1.8× above. Rewrite it to state what has
>    actually been seen.
> 2. The report and CLI say next to the Mach number that it is an **upper bound**.
> 3. `output/cli_hd13.py` docstring: "in under a second" becomes the measured time
>    (~42 s; ~20 min with the band).

**Found in the code (interpretation):**
- Item 1: `blastlab/core/unconfined.py:82-85`. This is a comment only. `MACH_QUASI_STATIC = 0.05` stays.
- Item 2 is **half done already**. The HTML report prints
  `Expansion Mach (upper bound)` (`output/hd13.py:190`). The CLI does not:
  `output/cli_hd13.py:71-72` prints `unconfined expansion Mach 0.0917   blast
  negligible: False`. Only the CLI line changes.
- Item 3 is **half done already**. The module docstring (`cli_hd13.py:4-5`) already
  says "about 40 s with the sensitivity band off", and "in under a second" is gone. What
  is missing is the band time (~20 min). The same "about 40 s" sentence is in
  `ui/app.py:551` and `tests/test_char_hd13_cli.py:26`. Update the two code
  docstrings. The test docstring is prose and needs no change.

**Files:** `blastlab/core/unconfined.py`, `blastlab/output/cli_hd13.py`,
`blastlab/ui/app.py` (docstring only), `blastlab/tests/char_golden/hd13_cli.json`
(re-pinned).
**References:** none needed. The threshold is not changed, so no standard is involved.
**Depends on:** nothing.

**Acceptance:**
- `cd blastlab/tests; python test_unconfined.py` passes unchanged. The threshold
  and `blast_negligible` do not move.
- `python test_char_hd13_cli.py` fails **only** on the CLI Mach line of
  `hd13_cli.json`. Re-pin it with `python test_char_hd13_cli.py --update` and check that
  the golden diff is exactly that one line, now carrying "(upper bound)".
  `hd13_cli_report.html` is unchanged in this step.
- `python test_char_hd13.py` passes unchanged. No number moves.

### Step 2 · `HD1-16` step 1, items 1 / 2 / 2a · CSV export of every computed chamber trace · **M**

Original TODO text, verbatim:

> 1. One CSV per trace. Columns: `t [ms]`, `p [kPa]`, `p [psi]`, cumulative impulse
>    `[kPa·ms]`. Header lines name the source case, the trace (gauge / plane-max /
>    band sample and its corner signs / nominal), **side-on or reflected**, and γ.
>    Overpressure over ambient, not absolute.
> 2. What is exported: **every** trace already computed. That means every sensitivity-band
>    sample *including the nominal*, and for the wall load G1 and plane-max × both γ.
>    The export must be the load *on the wall* (Pr, and Ps + C_D·q after clearing,
>    UFC 3-340-02 §2-15.3.2), because SBEDS applies a user-defined load as given.
> 2a. **Only what was computed. No tail rule** (owner, 2026-09-25): the T0 / T1 tails
>    are not exported. The trace ends at the run's last sample. If the load has not
>    returned to ambient by then (|p| above 1 % of the peak over the last 1 ms), the
>    header says so, with the last value: **"record ends while the load is still
>    active: p = … kPa at t = … ms"**, and so does the export's console / GUI message.

> **Owner decision 2026-09-26, overrides the column spec quoted above and every
> header / psi / impulse bullet below:** the CSV is what SBEDS loads, two
> comma-separated columns, `t [ms]`, `p_over [kPa]`, **no header, no comment
> line, nothing else**, e.g. `0,100` / `2,50` / `3,0`. Everything that was to go
> in the header (case, trace, load type, γ, psi factor, the "still active" line)
> goes in a sidecar `<same stem>.txt` next to each CSV, and the "still active"
> line is also printed / shown as a message. There is no impulse or psi column;
> `test_load_csv.py` checks the impulse by integrating the two columns it reads
> back, and it asserts that every line of the CSV parses as exactly two floats.
> **Negative pressure is exported as computed.** The owner confirmed on 2026-09-26
> that SBEDS accepts negative values, so suction is not clipped.

**Scope split (see §4, question Q1):** this step exports the traces that the
**HD 1.3 assessment** computes: the confined 0-D chamber trace and every band sample.
The **wall-load CFD traces** (G1 and plane-max × γ 1.24 / 1.40, HD1-13) are
excluded. Their "load on the wall" definition conflicts with what HD1-13 computed:
the E = max(R, S) upper bound has no clearing, while the TODO asks for Ps + C_D·q
after clearing, and clearing needs wall H, W and C_r that no case carries.

**Interpretation chosen (write each one into the module docstring):**
- **Where:** a new `blastlab/output/load_csv.py`, following CLAUDE.md §5: "every FILE
  export goes through `output/`". It is pure and has no Qt, no pyplot and no VTK
  (`test_layering.py`, `test_ui_no_mpl_pyplot.py`). `services/hd13.py` calls it
  after `write_report`, so the CLI (`--hd13`) and the Qt Run both export with no new
  flag. The CSVs are written to `<report stem>_loads/` beside the report.
- **Which traces:**
  - `nominal.csv` is `out['confined']` (`t`, `p`), the assessment's own run.
  - With the band on, there is one `band_<signs>.csv` per run the band made: every
    corner, plus every face run when `check_corners` ran. `<signs>` is the 5-axis sign
    tuple over `sensitivity.PARAMS`, e.g. `band_+1-1+1+1+1`. `core/sensitivity.band`
    today keeps only `low_trace` / `high_trace` (`sensitivity.py:343-345`). It gains a
    `'traces'` key, a list of `(signs, t, p)` for every row in `all_rows`, and no
    existing key or number changes. The band's own nominal sample (signs all 0) is
    written as `band_nominal.csv` only if its `(t, p)` differ from `out['confined']`.
    If they are identical, the nominal header says so and the file is not duplicated.
- **Header "side-on or reflected":** a 0-D chamber pressure is neither. The header
  says `load: chamber pressure, quasi-static and uniform (not side-on, not
  reflected); acts on the inner face of the chamber wall as given`.
- **Header γ:** the products' `prop.gamma` (e.g. 1.24 for `double_base`,
  `core/fuels.py:216`). The line adds that the chamber model mass-weights it with
  the room air (`deflagration.mixture`).
- **Overpressure** is `p − P_AIR` (101325 Pa, `core/constants.P_AIR`), the same
  `p_ref` the SDOF path used (`assessment.py:537-538`). The header names it.
- **psi** is `p_kPa / 6.894757293168361`, with the factor written in the header.
- **Impulse** is the cumulative trapezoid of `p [kPa]` over `t [ms]`, starting at
  0 at the first sample.
- **Numbers** are written with `repr(float)` (shortest round-trip), so reading the
  file back gives the writer's float64 values exactly.
- **"Still active" rule (2a):** the window is the samples with `t ≥ t_last − 1 ms`,
  and it always includes the last sample. The 0-D output is sparse, for example
  60 ms spacing at `t_end = 60 s`, `n_out = 1000`. The rule fires if any |p_over| in the
  window is > 1 % of that trace's max |p_over|. Then the header line and the returned
  message read exactly `record ends while the load is still active: p = <kPa> kPa at
  t = <ms> ms`. The CLI prints it and the Qt status line / log shows it. The
  threshold (1 %, 1 ms) is the owner's and is written as a named constant with the
  TODO ID in the comment.
- **No tails:** `core/wallload.extend_with_tail` is not called or touched (step 2
  of HD1-16 removes it).
- **Encoding:** UTF-8 **without** BOM, LF line endings, `#`-prefixed header lines,
  then one comma-separated header row. Written with Python `open(..., 'w',
  encoding='utf-8', newline='\n')`, never through PowerShell (§8.1). The
  `kPa·ms` unit contains a non-ASCII `·`. The column header uses `kPa*ms`, so a
  SBEDS import that expects ASCII is not broken. Record this choice in the docstring.

**Files:** new `blastlab/output/load_csv.py`; `blastlab/core/sensitivity.py`
(adds the `'traces'` key only); `blastlab/services/hd13.py` (calls the export and
returns its paths and messages); `blastlab/output/cli_hd13.py` (prints the export
paths and any "still active" line); `blastlab/ui/app.py` (`_hd13_done` status
line); new `blastlab/tests/test_load_csv.py`.
**GUI screens:** Qt main window status line after an HD 1.3 Run (`ui/app.py:626-634`).
**References:** `ufc-3-340-02`, para. 2-15.3.2 "Front Wall Loads" (text sidecar
`=== page 141 ===`, printed p. 65, lines ~6131-6164, Eq. 2-8 / 2-9). Cite it
in the module docstring only as the reason the wall-load traces are **not** in this
step (see Q1). The chamber trace needs no standard.
**Depends on:** Step 1 only for a clean `hd13_cli.json` diff.

**Acceptance:**
- `cd blastlab/tests; python test_load_csv.py` (new) passes and covers four cases.
  (a) Round trip: reading a written file gives `t_ms == 1e3*t` and
  `p_kPa == (p - P_AIR)/1e3` bit-for-bit (`==`, not `isclose`) for every row. (b) The
  impulse column equals `numpy.trapezoid` cumulated over the same columns to
  1e-12 relative. (c) A synthetic trace still at 5 % of peak over its last 1 ms gets
  the exact "record ends while the load is still active: p = … kPa at t = … ms"
  header line and message. One that has returned below 1 % gets neither. (d) The
  header names the case, the trace, the load type line and γ.
- `python test_sensitivity.py` passes unchanged. The new `'traces'` key holds
  `n_runs` entries, and `low_trace` / `high_trace` are the same objects as before.
- With the starter case, `python -m blastlab --hd13-new t.json; python -m blastlab --hd13 t.json`
  writes `t_hd13.html` and `t_hd13_loads/nominal.csv` (band off → one CSV).
  With `"sensitivity": true`, it writes `nominal.csv` plus one `band_*.csv` per band run.
  This is a ~20-min run and optional: `test_load_csv.py` covers the band path on a
  tiny band.
- `python test_char_hd13_cli.py --update` changes only the `files` listing
  (the new `t_hd13_loads` dir) and the new stdout export lines. Review the golden diff
  line by line before committing.
- `python test_ui_char_hd13_run.py --update` changes only the status-line text and
  the files listing. Review the diff.
- `python test_layering.py`, `python test_ui_no_mpl_pyplot.py` and
  `python test_ui_no_vtk_in_main.py` pass.

### Step 2b · `HD1-16` step 1, item 2 · The wall-load traces, with optional clearing · **M** · *added after owner answer Q1, 2026-09-26*

**Owner decision:** export the wall-load traces too, and **clearing is the user's
choice**. When it is off, the export is E = max(R, S) as HD1-13 computed it, and the
sidecar says "reflected + stagnation, no clearing, upper bound". When it is on, the user
gives the **loaded wall's height H and width W**, and clearing follows UFC 3-340-02
§2-15.3.2 (text sidecar `=== page 141 ===`, lines ~6131-6164):
t_c = 4S / ((1 + R) C_r) (Eq. 2-8), where S = min(H, W/2), G = max(H, W/2) and
R = S/G; after t_c the load is Ps + C_D·q with C_D = 1 (Eq. 2-9).

**Source of the traces (no WSL, no solve):** the committed `docs/hd13/` files.
- `vent3d_wall_load_G1.txt` (3395 probe rows): R, S and E for γ 1.24 and 1.40, but
  only `un`, with no p or rho.
- `vent3d_wall_plane.txt` (749 writes): Emax per γ, plus `G1cell_p`, `G1cell_rho`
  and `G1cell_U*`, which are Ps and q at G1's cell.
Parse them with a small reader in `output/load_csv.py` (or `core/wallload.py`),
checking that the header's units line is what the parser expects.

**Interpretation to pre-register in the module docstring before any trace is judged
(the owner may correct it after the report):**
- **Which traces:** G1 × {1.24, 1.40} and plane-max × {1.24, 1.40}, four files per
  clearing setting.
- **Clearing applies only to G1.** Plane-max is a maximum over different cells at
  different times, not a point on a wall, so clearing is not defined for it. Plane-max
  is always exported unrelieved, and its sidecar says why.
- **Ps and q for G1:** Ps = G1cell_p − P_AIR and q = ½·ρ·un² with un = max(Ux, 0), from
  `vent3d_wall_plane.txt`, interpolated onto the probe times. The sidecar states that
  these come from the 749 writes, not the probe.
- **C_r:** the sound speed in the normally reflected region, computed from
  Rankine-Hugoniot at the trace's peak reflected state with the trace's γ. Cross-check
  it against Figure 2-192 at two or three points read off the PDF page; the figure is
  for air, γ = 1.4. Cite both.
- **The clearing construction (Figure 2-191a, applied to a CFD trace):** arrival t_a is
  the first sample where E exceeds 1 % of its peak. Write τ = t − t_a. For 0 ≤ τ ≤ t_c
  the load blends linearly, L = (1 − τ/t_c)·E + (τ/t_c)·(Ps + q). For τ > t_c, L = Ps + q.
  Before t_a, L = E. Name every constant.
- **The Eq. 2-10 check (fictitious duration t_rf = 2 i_r / P_r) is not applied.** It is
  meant for idealised triangles and not for a computed trace. Write it into the sidecar
  as not applied, and list it as an engineering question for the owner.
- **Input:** optional fields `wall_H_m`, `wall_W_m` and `clearing` (bool, default
  false) in the HD 1.3 case JSON (`models/hd13_case`), with a matching "Loaded wall"
  group in the Qt HD 1.3 form. H and W are enabled only when clearing is ticked. Tk:
  none (owner Q4). The CLI adds `python -m blastlab --hd13-wall-export case.json`,
  which writes `<case>_wall_loads/{G1,planemax}_g{124,140}[_cleared].csv` plus sidecars.
  Clearing on with H or W missing or ≤ 0 is a validation error that names the field.
  Unknown keys follow whatever the reader does today, because P1-11 is not in this batch.
- **Format:** the same as Step 2. Two columns, ms and kPa over ambient, no header, and a
  sidecar `.txt`.

**Files:** `blastlab/output/load_csv.py`, `blastlab/core/wallload.py` (a new pure
`apply_clearing` function, with no change to the existing functions),
`blastlab/models/hd13_case.py`, `blastlab/models/fields.py`,
`blastlab/ui/setup_spec.py`, `blastlab/cli.py` or `__main__` (the flag),
`blastlab/tests/test_load_csv.py`, and a new `blastlab/tests/test_wall_clearing.py`.
**GUI screens:** Qt Setup → 0-D (HD 1.3) form, the new "Loaded wall" group.
**References:** `ufc-3-340-02` §2-15.3.2, Eq. 2-8 / 2-9, Fig. 2-191a and Fig. 2-192.
Read the figure off the PDF page, not the OCR text.

**Acceptance:**
- `cd blastlab/tests; python test_wall_clearing.py` (new):
  - (a) S, G and R for H=3, W=4 (S = 2, R = 2/3) and for H=2, W=10 (S = 2, R = 0.4);
    t_c matches Eq. 2-8 by hand.
  - (b) A synthetic step trace, E = Pr constant, with Ps and q constant: L equals Pr at
    t_a, equals Ps + q at t_a + t_c, and is linear in between.
  - (c) With clearing off, the exported E equals the file's `E_1.24` and `E_1.40` columns
    bit-for-bit, in kPa.
  - (d) C_r lies within the tolerance registered in the docstring of the Figure 2-192
    points for γ = 1.4.
  - (e) Clearing on with no H is refused, and the error names `wall_H_m`.
- `python -m blastlab --hd13-wall-export <starter>.json` with clearing off writes four
  CSVs. Every line of each parses as exactly two floats. The G1 peak in kPa equals the
  file's max E / 1e3.
- `python test_ui_hd13_form.py`: the "Loaded wall" group round-trips `clearing`,
  `wall_H_m` and `wall_W_m` through load→save. H and W are disabled while clearing is
  off.
- No existing function in `core/wallload.py` changes; `python test_wallload.py` (or
  its existing suite) passes unchanged.

### Step 3 · `HD1-16` step 1, item 3 · No μ, support rotation or verdict in any output · **L**

Original TODO text, verbatim:

> 3. Remove μ, support rotation and the survives / fails / undetermined verdict from the
>    HD 1.3 report, the CLI, the Qt and Tk forms, and the GUI result views. Callers in
>    `core/`: `assessment`, `scenario`, `sensitivity` (`structural_verdict`), `thermal`,
>    `unconfined`, `wallload`. Keep the module and its tests for now.

**Found in the code:**
- `core/assessment.py:529-573` is the only place `run()` calls
  `sdof.response` and `sensitivity.structural_verdict`, and it adds the
  "STRUCTURAL VERDICT" warning or note to the validation report. `assessment.py:175`
  (`validate`, `has_component` checks) is on the same path.
- The report: `output/hd13.py:212-247` (the "Structural response" section),
  `:290-325` ("Does that verdict survive the band?", including the `cfd_point` note).
- The figure: `services/hd13.py:55-58` → `output/plots.figure_sdof_response`
  (`plots.py:731`).
- The CLI: `output/cli_hd13.py:73-87`.
- The Qt form: `ui/setup_spec.py:298-305`, the **"Structure" card** (span,
  mass/area, Ru, kE, supports, collapse rotation), and the `from ..core.sdof import
  SUPPORTS` at `:234`. It is read and written by `models/fields.py:177-210,
  262-266`.
- **The Tk GUI has no HD 1.3 form.** No match for `hd13`, `Vieille` or `deflag` in
  `blastlab/gui/`. TODO says "the Qt and Tk forms", but there is nothing to change
  on the Tk side. Its suites still run because `core/` and `output/` change (§9).
  See Q4.
- "GUI result views": the Qt app shows no HD 1.3 result widget. It writes the HTML
  report and sets a status line (`ui/app.py:626-634`). The views are therefore the
  report plus the status line.
- `core/scenario.py:29`, `core/thermal.py:49-54, 290`, `core/wallload.py:163-167`
  and `core/unconfined.py:241-287` (`compare(..., component=...)`, which derives
  `governing` through SDOF) are **not called with a component by `assessment.run`**.
  `unconfined.compare` is used only by tests and `_e2e_*`. They stay as they are:
  "keep the module and its tests for now". Only docstrings that say the
  *assessment* reports μ are corrected.

**Interpretation chosen:**
- `assessment.run` no longer calls `sdof.response` or `structural_verdict`. The
  keys `sdof`, `component` and `verdict` stay in the output dict, always `None`, so
  downstream `is None` checks keep working until step 2. The "STRUCTURAL VERDICT …"
  warning and note are no longer emitted.
- The report loses the "Structural response" section, the "Does that verdict
  survive the band?" table and note, and the "Structural response" figure.
  `save_hd13_report` keeps its `sdof=` / `verdict=` parameters (ignored and
  documented) so step 2 can remove them with the module. The "What this is" note
  about the pressure-impulse diagram stays, because it is about the load regime and
  not a μ.
- The CLI loses the `structure` and `verdict` lines.
- The Qt form: the "Structure" card is **hidden**, not deleted, so step 2 can
  delete it with `core/sdof.py`. The six keys in `models/hd13_case` still load from
  JSON and are written back unchanged on save (pass-through, the same rule the owner
  set in `P1-8` item 2). The starter case file (`write_starter_case`) is **not**
  changed, because `HD1-17(b)` replaces it.
- **Residual capacity** (`assessment.py:539-541`, `thermal.residual_capacity`,
  Ru after heating) is not μ, rotation or a verdict, and does not call SDOF. It is
  moved out of the SDOF block so it is still computed when the JSON carries `Ru_pa` and
  there is a thermal result, and it is otherwise left exactly as it is. Whether it
  should go too is Q2.

**Files:** `blastlab/core/assessment.py`, `blastlab/output/hd13.py`,
`blastlab/services/hd13.py`, `blastlab/output/cli_hd13.py`,
`blastlab/ui/setup_spec.py`, `blastlab/models/fields.py` (pass-through of hidden
keys), docstrings in `core/unconfined.py` / `core/thermal.py` if they say the
assessment reports μ. Tests: `test_assessment.py`, `test_hd13_report.py`,
`test_ui_hd13_form.py` (its `'Structure'` card assertion at `:76`),
`test_char_hd13.py` and goldens `hd13_cli.json`, `hd13_cli_report.html`,
`ui_hd13_run.json`, `ui_hd13_run_report.html`, `ui_case_form.json`.
**GUI screens:** Qt Setup tab → the 0-D (HD 1.3) form (Structure card hidden);
the HD 1.3 HTML report as opened from the status line.
**References:** `ufc-3-340-02` Ch. 3 (SDOF, Figure 3-49 onward) only to identify
what is being removed. No coefficient is touched.
**Depends on:** Step 2. The export must exist before the μ output is removed, so
the report never ends up with neither a load file nor a response.

**Acceptance:**
- `cd blastlab/tests; python test_sdof.py` and `python test_sensitivity.py` pass
  **unchanged**. The module and `structural_verdict` stay and are still tested.
- `python test_char_hd13.py`: every pressure / time / thermal / QD pin is unchanged
  to its existing rel = 1e-9. Only the `sdof_*` and `verdict*` keys go, re-pinned
  with `--update` in a commit of its own that cites `HD1-16`. The golden diff shows
  deletions only.
- A grep check, which the implementer adds to `test_assessment.py`: running
  the starter case with the band on a tiny setting gives a report HTML, CLI stdout
  and validation messages in which none of `Ductility`, `ductility`, `mu `,
  `Support rotation`, `survives_across_band`, `fails_across_band`,
  `undetermined_within_band` or `COLLAPSE` appears.
  `python test_assessment.py` passes.
- `python test_char_hd13_cli.py --update` and `python test_ui_char_hd13_run.py --update`:
  the golden diffs remove the structure/verdict lines and the "Structural response"
  section/figure placeholder, and change nothing else.
- `python test_ui_hd13_form.py`: the form has no visible "Structure" card, and a
  JSON with `span_m=4.0, mass_per_area=333.0, …` loads and saves back with those six
  values identical. `python test_ui_char_case_form.py --update` changes only the
  Structure-card entries, and the diff is reviewed.
- `python test_char_case_json.py` passes **unchanged** (the starter file is byte-identical).

### Step 4 · `HD1-16` step 1, item 4 · The gates · **S**

Original TODO text, verbatim:

> 4. Tests: the export round-trips (t, p) exactly, the impulse column matches the
>    trapezoid integral, and no output carries a μ. Tk and Qt suites run (§9).

The first two parts are covered by Step 2's `test_load_csv.py` and the third by
Step 3's grep check. This step is the full run.

**Acceptance (paste the tail of each):**
- `cd blastlab/tests; python test_regression.py` is **byte-identical** with no
  baseline touched. The batch changes no native-solver path, so any difference is a
  stop.
- `python test_foam_writer.py`, `python test_case_validate.py` and
  `python test_foam_env.py` pass unchanged (no foam file touched).
- The HD1 matrix: `python test_deflagration.py`, `test_sdof.py`,
  `test_unconfined.py`, `test_sensitivity.py`, `test_thermal.py`, `test_qd.py`,
  `test_assessment.py`, `test_hd13_report.py`, `test_load_csv.py`,
  `test_char_hd13.py`, `test_char_hd13_cli.py`, `test_char_case_json.py`.
- Qt: `python test_ui_hd13_form.py`, `test_ui_char_hd13_run.py`,
  `test_ui_char_case_form.py`, `test_ui_parity.py`, `test_ui_setup_form.py`,
  `test_ui_no_vtk_in_main.py`, `test_ui_no_mpl_pyplot.py`, `test_layering.py`.
- Tk (§9, because `core/` and `output/` changed): every `python test_gui_*.py`.
  Known independent hang: `test_gui_run_browser` can hang on a modal (`P2-8`). If it
  does, record it as P2-8 and do not "fix" it here.
- Real window (§8.7): `python _e2e_hd13_gui.py` after the pre-flight. Press Run on
  the 0-D starter case, confirm the report and the `_loads/` directory are written,
  the status line names the CSVs, and the Structure card is not on screen, checked
  through the harness's Win32 checks and not `isVisible()`. `_qa_ui_harness.py` has no HD 1.3
  scenario, so it is not required here.

---

## 2. GUI screens touched

| Screen | Change | Toolkit |
|---|---|---|
| Setup tab → 0-D (HD 1.3) form | "Structure" card hidden; keys pass through load→save | Qt only (Tk has no HD 1.3 form) |
| Setup tab → 0-D (HD 1.3) form, new "Loaded wall" group (Step 2b) | clearing checkbox; H, W enabled only when ticked | Qt only |
| Main window status line after an HD 1.3 Run | names the CSV directory; shows the "still active" line when it fires | Qt |
| HD 1.3 HTML report (written by Run / `--hd13`) | no Structural response section, no verdict table, no SDOF figure | shared (`output/hd13.py`) |

---

## 3. Risks

1. **Characterisation goldens change, and §9 protects committed tests.** The owner
   decision `HD1-16` ("no output carries a μ") is what authorises the re-pin.
   Protection: (a) re-pin each golden in its **own commit** citing `HD1-16`; (b) the
   diff of every `char_golden/*` file must contain only the SDOF/verdict lines, the new
   export lines or file listing, and the one Step 1 Mach line. Any changed number is a
   stop; (c) `test_char_hd13.py`'s numeric pins at rel 1e-9 are the proof that no
   pressure moved; run it **before** the re-pin to show that only the removed keys fail.
2. **Numerical results must not move.** The batch changes no coefficient, threshold
   or integrator. The one core change that touches a result path,
   `sensitivity.band` gaining a `'traces'` key, is additive. Protection:
   `test_sensitivity.py` and `test_char_hd13.py` unchanged and green before the
   golden update. `MACH_QUASI_STATIC` stays 0.05 (`test_unconfined.py`).
3. **The export can mislabel a load, which is the dangerous direction for a design
   load.** A chamber trace sent to SBEDS as "reflected" or "side-on" would be misread.
   Protection: the fixed load-type header line in Step 2, and the "still active"
   rule with its exact wording, pinned by `test_load_csv.py`. Because of this risk
   the wall-load traces (whose clearing treatment is open, Q1) are excluded rather than
   exported under a guessed definition.
4. **Removing the verdict removes a warning.** "STRUCTURAL VERDICT UNDETERMINED"
   was the loudest caveat on a banded run. The band's own warnings (spread, not
   sourced, heat-loss, extinction) stay. Protection: the Step 3 grep check tests for
   absence of μ only. `test_assessment.py`'s existing band-warning checks must still
   pass unchanged.
5. **Settings / run corpus (§8.2).** Only offscreen suites and one real-window
   `_e2e_hd13_gui.py` build a GUI, and all of them use a private settings file.
   Protection: the §0 pre-flight. The destructive "check" is explicitly not used.
6. **Encoding (§8.1).** New CSV and doc text may carry `·`, `γ` or `μ`. Every
   file is written with the editor tools or Python `open(..., encoding='utf-8')`, and
   never through PowerShell. Afterwards, `rg 'ג€|ג”'` over the touched files must be
   empty.
7. **Layering.** A new `output/` module must not import `ui/`, `gui/`, pyplot or VTK.
   `test_layering.py` pins this.

---

## 4. Needs clarification (excluded from this batch, questions for the owner)

- **Q1 · `HD1-16` item 2, the wall-load traces (G1, plane-max × γ 1.24 / 1.40).**
  HD1-13 delivered E = max(R, S), with R the Rankine-Hugoniot normal reflection and
  S the compressible stagnation, **unrelieved by clearing** and marked as an upper
  bound (`docs/hd13/vent3d_wall_load_G1.txt`, `vent3d_wall_plane.txt` headers).
  TODO asks for "Pr, and Ps + C_D·q after clearing, UFC 3-340-02 §2-15.3.2".
  Clearing needs t_c = 4S / ((1 + R) C_r) (Eq. 2-8), and so the wall's height and
  width and C_r from Figure 2-192. No case carries those.
  *Question:* export E as computed, with a header that says "reflected + stagnation,
  no clearing, upper bound"? Or implement clearing per Eq. 2-8 / 2-9 with C_D = 1,
  and if so, which wall H × W? Also: should the export read the committed
  `docs/hd13/*.txt` traces, or re-derive them from the evidence run through
  `_e2e_vent_wall.py`?
- **Q2 · Residual capacity.** `thermal.residual_capacity` (Ru after heating) is a
  capacity statement about the wall, not a load. It does not use SDOF and is not in
  HD1-16's list. *Question:* does it leave the report with μ, since "blastlab gives
  the load, not the response"? Until answered, this batch keeps it, computed only
  when the case JSON carries `Ru_pa`.
- **Q1 · answered (owner, 2026-09-26):** clearing is a user choice. When it is on, the
  user gives the loaded wall's H and W. The wall traces are in this batch as Step 2b.
- **Q2 · answered (owner, 2026-09-26):** residual capacity **stays** in the report,
  unchanged. It is kept exactly as Step 3 describes.
- **Q3 · answered (owner, 2026-09-26):** two columns, ms and kPa, no header. See Step 2.
- **Q4 · answered (owner, 2026-09-26):** no Tk HD 1.3 form is needed for now. Tk
  work in this batch is nil. The Tk `test_gui_*` suites still run (§9).
- *(Original Q3, kept for the record:)* **SBEDS import format.** The CSV follows the owner's column spec. No SBEDS
  manual is registered in `docs/references/INDEX.md`. If SBEDS needs a specific layout
  (no header lines, psi-ms only, a maximum row count), *please add the SBEDS user
  manual with `/ref add`* and the format will be matched to it.
- **Q4 · "Qt and Tk forms" for HD 1.3.** The Tk GUI has no HD 1.3 form. `HD1-16`,
  `P1-11` and `P1-15` all say "Qt and Tk". `P1-15` even cites `gui/case_form.py:184`,
  but no `gui/case_form.py` HD 1.3 field exists. *Question:* confirm the Tk side is
  "nothing to do" (and correct those TODO lines), or is a Tk HD 1.3 form wanted?
- Already owner-gated and not planned: `HD1-16` step 2, `HD1-17(b)` (scenario),
  the RDX/ANFO rows of `P1-14`, and the `P2-11` test change unless it is a code bug.
  Open owner decisions from TODO also stand: `HD1-4` (close or keep), `P1-4`, the amr2d
  thresholds, decomposition, the `P1-12` 50 GB warning threshold, and `P4-1` / `P4-2`.

---

## 5. Remaining backlog, grouped into future batches

**Suggested next batch: `p0-5-settings-in-repo`** — `P0-5` (M). It is P0 and
independent. It turns the §0 pre-flight above into code (`settings.config_path()` →
repo-local file, migration forcing `auto_cleanup: false`, `env.cleanup_plan` dry run),
and it makes every later GUI batch safe. It could equally run *before* this batch if
the owner prefers. Note that TODO calls the function `default_path()`, but the code has
`config_path()`. Keep `config_path` and add `default_path` as the repo path, or rename
and update the 3 callers (`crashlog.py:50`, `_qa_gui_harness.py:273`, `load`/`save`).
Decide that in the plan. Also add CLAUDE.md §8.2 / TODO P4-3 text updates.

Then, one line each:
- **hd13-inputs:** `P1-11` (strict HD 1.3 reader, blank vs 0, used values in the
  report) + `P1-15` (Vieille `a` in mm/s/MPaⁿ). These are the same files
  (`models/hd13_case`, `models/fields`, `ui/setup_spec`, `output/hd13`,
  `cli_hd13`). Wait for Q4. Add `HD1-17(b)` if the owner supplies the scenario.
- **hd1-16-wall-export:** the Q1 remainder of `HD1-16` item 2 (G1 / plane-max CSVs),
  after the owner answers Q1. Then `HD1-16` step 2 (delete `core/sdof.py`,
  `structural_verdict`, T0/T1) once the owner has run SBEDS. Pair it with the docs-only
  `P2-15`, the same HD1-3d / HD1-13 records in DONE.md §0.
- **foam-reader-and-grid:** `P1-7` (reader accepts `);`) + `P1-16` (validation uses the
  solver's grid builder; extra charges in 'zone' mode). High priority by owner. These
  are foam reader/writer and validation files, the WSL-free parts first.
- **amr-defaults:** `P1-8` (one source for 0.2/0.1 / Lohner; the form keeps the case's AMR
  fields). Qt + Tk forms, `core/refine.py`, `models/fields.py`.
- **materials-sourced:** `P1-14` rows TNT/C4/HMX/PETN + text fixes 5-6 (RDX/ANFO gated),
  then `P1-9` (labels "kg ‹material›", preview `rho0`, W_E via UFC Eq. 2-1 / Table
  2-1) and `P1-10` (ground-burst KB, Fig. 2-15). `P1-4` label if the owner chooses
  "label".
- **write-interval:** `P1-12` (user write interval + disk estimate, needs the
  blastFoam guide `controlDict` section and a WSL acceptance run).
- **gauge-arrival:** `P1-13` (arrival at a fraction of peak; re-baselines the gauge
  summaries in their own commit).
- **test-repairs:** `P2-13` items 1, 3, 4 (wsl_resume stub, vent_wall collection,
  refine `check()`), and `P2-11` investigation only. Also `P2-7`, `P2-8`.
- **hygiene:** `P2-14` items 1-9 (negative charge preview, profile `charge=None`,
  `C_AMB_AIR`, one charge-radius function, …).
- **display:** `P2-1` (1D progress; stdout re-baseline rule), `P2-2` (Energy approx
  label), `P3-25`, `P3-9`, `P3-10`.
- **research runs (WSL, owner go):** `N5-11` settling run, the ≈2 % parallel offset
  fixed-Δt run, Claim 3 R3.1b/R3.2/R3.3, `HD1-14` third `Cd` point (with
  `write_budget`). Pre-register the thresholds before each run.
- **docs-only:** the "corrections the audit implies" (`adjustLocations` comments,
  `snGradAlpha` name), `P2-15`.
- **P3 / P4:** on request (`P3-1` … `P3-24`, `P4-1` … `P4-3`). Nothing is scheduled.
