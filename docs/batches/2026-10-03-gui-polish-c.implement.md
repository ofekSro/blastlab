# GUI-11 part 11c — implementation report (T10-T15)

Batch plan: `docs/batches/2026-10-03-gui-polish.md`, part 11c only.
Branch `gui-redesign`, from `d5944a7` (11a and 11b done and verified).
One commit per task, plus the two owner-approved golden re-records in
their own commits, then this report. 11d is a later run.

Before starting:
- CLAUDE.md §8.2 dry run: `auto_cleanup` reads `False` (and again at
  the end).
- Baseline: `test_ui_char_case_form` PASS, `test_ui_setup_strip` PASS
  (110).
- Working tree: only the never-stage paths were dirty. None was staged.
- No WSL command was run.

**Owner override on T10.** `TODO.md` GUI-11 (commit `305a351`): UXR-3
hides the Material row in native mode instead of the plan's Checks
warning. T10 below implements the override, not the plan's text.

---

## T10 · UXR-3: Material is hidden in native mode — DONE (owner override)

**What was done.**
- Both Material rows in `ui/setup_spec.py` get `scope='blastfoam'`:
  1D Charge, and 2D / 3D Initialization.
- So 01 Setup and every Chain stage hide the row in native mode and show
  it in blastFoam. This is the "hide, never grey" rule.
- The value stays in the form and is not written to the case. A native
  case keeps carrying `TNT` exactly as before
  (`models/fields._charge_model`, D138).
- No case JSON, number or export changed.
- The Tk app and its golden are untouched, so Tk still shows the row.
- D210 records the override.

**Files:** `blastlab/ui/setup_spec.py`,
`blastlab/tests/test_ui_setup_form.py`,
`docs/gui-redesign-decisions.md` (D210),
`blastlab/tests/char_golden/ui_case_form.json` (own commit).

**Tests:** `cd blastlab/tests && python test_ui_setup_form.py`, S6b (24
checks: dims 1-3 × both placements).

**Criteria (as overridden)**
- PASS. Native hides the row; blastFoam shows it. Dims 1-3,
  `columns` and `nodes` placements.
- PASS. Native with ANFO in the box: `get_case().material == 'TNT'`,
  and the box still holds ANFO.
- PASS. blastFoam with ANFO runs ANFO. Back in native the row hides
  again and keeps ANFO.
- PASS. `test_ui_setup_tree` (the T1b scope-parity check), harness C05
  (native keeps the typed C4 and strips it from the case) and
  `test_ui_chain_screen` (seeding) green unedited.

**Golden re-record** (`64ca7f4`, "owner decision 2026-10-03, UXR-3").
Key-by-key diff, 57 keys before and after; only these four `hidden`
lists changed, each gaining `material`:
- `dim1_native/set_c1/hidden`
- `dim2_native/set_c2_axisym/hidden`
- `dim2_native/set_c2_planar/hidden`
- `dim3_native/set_c3/hidden`

Between `642308d` and `64ca7f4` alone, `test_ui_char_case_form` is red
by construction (the code moved first, the golden in its own commit).

**Commits:** `642308d` (code), `64ca7f4` (golden).

## T11 · F16 (GUI-11 e): a case file's hidden AMR values survive Open → Save — DONE, narrower than the plan's wording

**What was done.**
- `CaseForm._keep_loaded_amr` runs with AMR off, in a form that holds a
  **loaded** case (`set_case` has run).
- It puts the five hidden boxes back into the case when each parses:
  `amr_refine`, `amr_unrefine`, `amr_interval`, `amr_buffer`,
  `amr_max_cells`.
- A box that does not parse keeps the fallback and blocks nothing.
- `models/fields.py`, `AMR_FORM_FALLBACKS`, the dataclass defaults, the
  solver defaults and the Tk app are unchanged. A fresh form still sends
  0.4 / 0.2. D211.

**Why narrower than "the hidden box's value when it parses".** Applied
to every form, the plan's rule also changes the golden's
`dim2_native/amr` entry: AMR values typed into a fresh native form,
where the AMR card is hidden. That is outside the three `/get` entries
the owner approved. It would also write a typed hidden value into the
case, against CLAUDE.md §4. So a form never loaded keeps the
fallbacks.

**Files:** `blastlab/ui/case_form.py`,
`blastlab/tests/test_ui_setup_form.py`,
`docs/gui-redesign-decisions.md` (D211),
`blastlab/tests/char_golden/ui_case_form.json` (own commit).

**Tests:** `python test_ui_setup_form.py`, S3c (8 checks).

**Criteria**
- PASS. A file with AMR off and 0.2 / 0.1 (and 3, 1, 400000) loads,
  saves and reads back 0.2 / 0.1 (3, 1, 400000). Checked in 2D and 3D,
  native and blastFoam, through `save_case` / `load_case` on disk.
- PASS. A fresh blastFoam form saves 0.4 / 0.2 (and 2, 2, 0), 2D and 3D.
- PASS. `test_ui_char_case_form` is green with the re-recorded golden.
  Its diff touches no other key (below).
- PASS. `test_gui_char_case_form` (Tk) is green unedited.
- PASS. `test_ui_parity`, `test_ui_char_chain_wiring` and
  `test_regression` are green.

**Golden re-record** (`99bce3f`). Three `/get` entries,
`amr_refine` / `amr_unrefine` only:

| Key | Before | After |
|---|---|---|
| `dim2_native/set_c2_axisym/get` | 0.4 / 0.2 | 0.35 / 0.1 |
| `dim3_native/set_c3/get` | 0.4 / 0.2 | 0.2 / 0.1 |
| `dim3_blastfoam/set_c3/get` | 0.4 / 0.2 | 0.2 / 0.1 |

The plan names `set_c2_no_gauge_file`, which is not a key of this
golden. `set_c2_planar/get` is an error entry (`'charge' is not a
number`) and did not move. Every `/fresh` and typed entry is unchanged.

**Commits:** `c9332e3` (code), `99bce3f` (golden).

## T12 · UXR-9: removing a gauge keeps the trigger on the same gauge — DONE

**What was done.**
- `PointList.on_remove` is a plain callback. It is called with the
  removed row's 0-based index, before `on_change`. No signal changed.
- `CaseForm._gauge_removed` keeps the trigger on its gauge:
  - removing a row before the trigger decrements `trigger_gauge`;
  - removing the trigger row blanks it, and with the switch on the
    dropdown shows D27's red pending state;
  - removing a row after it changes nothing.
- A number that named no gauge (D17) is left alone, and `set_case`
  never removes a row, so loaded files round trip.
- The switch's remembered number follows the same rule.
- It covers Setup, every Chain stage and the `columns` form. D219.

**Files:** `blastlab/ui/fieldform.py`, `blastlab/ui/case_form.py`,
`blastlab/tests/test_ui_setup_tree.py`,
`docs/gui-redesign-decisions.md` (D219).

**Tests:** `python test_ui_setup_tree.py`, T3e (22 checks; 260 in all).

**Criteria**
- PASS. Trigger G3, remove G1: `trigger_gauge == '2'`, the point is the
  old G3, and the dropdown shows the same coordinates (`G2 · r 3.00, z
  0.50`).
- PASS. Remove G3 itself: blank, `trigger_pending()` True, the dropdown
  red.
- PASS. Remove G4: still `3`.
- PASS. A loaded `G5 (no such gauge)` is untouched.
- PASS. `test_ui_char_case_form` green unedited.

**Commit:** `25bf398`.

## T13 · UXR-11 + F4 + QA S4-a: axisymmetric r / z on screen — DONE

**What was done.** On screen only; planar and 3D are unchanged. D220
amends D111.
- `AXISYM_LABELS['Ly']` is now `Height H [m]`.
- The axisymmetric hook renames the point-list columns:
  - Gauges and Detonation points read `r z`;
  - Obstacles read `r0 r1 z0 z1`;
  - Refinement zones read `r0 r1 z0 z1 level`.

  The entry hint and the refusal text follow (new
  `PointList.set_columns`, mapping `setup_spec.AXISYM_COLUMNS`).
  Planar restores `x y`.
- The Setup and Chain 2D preview set `z [m]` after `preview_draw` returns
  (`preview_panel._draw_2d`). `output/` is untouched.
- The Results replay of a 2D axisymmetric run labels its bottom axis
  `r [m]` (`results_anim.AnimView.set_result`). The hover therefore
  reads `r … · z … m` there too. The snapshot maps already read r / z.
  - `plane_geometry`, the video, This frame .png and every figure keep
    their labels.
  - This file is not in the plan's list. The replay's labels are set
    there, and a Qt-side relabel in `results_field.py` would be undone
    by every Show mesh toggle (`AnimView.set_show_mesh` re-runs
    `set_result`).
- The `[kg TNT]` caption (E1) is untouched.

**Files:** `blastlab/ui/setup_spec.py`, `case_form.py`, `fieldform.py`,
`preview_panel.py`, `results_anim.py`;
`blastlab/tests/test_ui_setup_form.py`,
`blastlab/tests/test_ui_results_screen.py`;
`docs/gui-redesign-decisions.md` (D220); two screenshots.

**Tests:**
- `python test_ui_setup_form.py`: S8 (pin changed) and S8b (new, 18).
- `python test_ui_results_screen.py`: S6f (+3).

**Criteria**
- PASS. Offscreen, 2D axisymmetric, in both placements: every point-list
  header and hint reads r / z, and the captions read `Radius R [m]` /
  `Height H [m]`. Planar restores `x y`, and back again gives r / z. 3D
  keeps `x y z`.
- PASS. The preview's `get_ylabel() == 'z [m]'` in axisymmetric; planar
  gives `x [m]` / `y [m]`.
- PASS. The axisymmetric Results fixture:
  - the replay's bottom axis reads `r [m]`, and still does after the
    mesh overlay is redrawn;
  - the snapshot map's reads `r [m]`;
  - the hover reads `r 0.58 · z 0.15 m`;
  - `plane_geometry(meta)['xlabel']` is still `x [m]`.
- PASS. `test_ui_char_case_form` green unedited. Captions are not in the
  golden.
- PASS. Real platform (`windows`, Win32-visible):
  - `docs/qa/2026-10-03-gui-polish/gui11-axisym-labels-setup.png`: the
    Gauges table `r z`, `add a row: r  z`, the preview `z [m]`;
  - `…/gui11-axisym-labels-results.png`: the replay `r [m]`, the hover
    `r 0.41 · z 0.81 m`.

**Commit:** `3f5d71c`.

## T14 · UXR-15 (the small half): units where they were missing — DONE

**What was done** (D221).
- **Impulse.** The Field view's Impulse map reads
  `Net overpressure impulse [kPa·ms]` on its colour bar, and `kPa·ms`
  as its Min / Max caption and hover unit.
  - This is a label, not a conversion: 1 Pa·s = 1 kPa·ms
    (`results_fields.screen_unit`).
  - `select_field`'s `unit` (This frame .png), `plots.IMPULSE_LABEL`, the
    video and every export keep `Pa·s`.
- **End time.** A faint `= 12.0 ms` sits under the box when End time is
  non-zero (`= 0.3 ms` below 1 ms). It shows nothing for 0, blank or
  unparsed. It applies to Setup and the Chain stages, dims 1-3. The
  row's widget is still the box.
- **Z unit tooltips** (`scaled_distance.UNIT_TIP`, citing UFC 3-340-02,
  para. 2-13.1):
  - the live-gauge column's `Z` header (an `R` header says R is in m);
  - the Derived card's `Nearest gauge · Z 2.99`;
  - the Setup / Chain model-view hover readout
    (`model_overlay.HOVER_TIP`, set while it shows, cleared after).
  - The strip's Z tile tooltip already carried `m/kg^1/3` (its caption);
    it is unchanged.
  - The Derived card is in `setup_panel.py`, not `setup_nodes.py` as the
    plan says.
- Not done: P MAX in MPa (U4 / D52; owner call).

**References.** UFC 3-340-02 (2008), para. 2-13.1, printed p. 44, as
already cited in `ui/scaled_distance.py`. The Z formula is not touched;
only a tooltip string cites it. `docs/references/INDEX.md` was only
read.

**Files:** `blastlab/ui/results_fields.py`, `results_field.py`,
`case_form.py`, `scaled_distance.py`, `model_overlay.py`,
`setup_panel.py`, `chain_stage.py`, `run_gauges.py`;
`blastlab/tests/test_ui_setup_strip.py`,
`blastlab/tests/test_ui_results_screen.py`;
`docs/gui-redesign-decisions.md` (D221).

**Tests:**
- `python test_ui_setup_strip.py`: S2c (+2), S4 (new; 129 in all).
- `python test_ui_results_screen.py`: S6f (+3; 200 in all).

**Criteria**
- PASS. Offscreen: the Impulse colour bar reads `Net overpressure
  impulse [kPa·ms]  (top clipped)`, with no `Pa·s`. Its Min / Max caption
  reads `kPa·ms`.
- PASS. `test_ui_char_results_exports` is green unedited.
  `select_field`'s unit is still `plots.IMPULSE_LABEL`.
- PASS. End time `0.012` shows `= 12.0 ms`; `0`, fresh and `abc` show
  nothing. Checked in dims 1-3, both placements.
- PASS. Each Z tooltip contains `m/kg^1/3`:
  - the strip tile;
  - the Derived card (and none in planar, where Z is hidden);
  - the live Z header;
  - the hover readout (and it is cleared on leave).

**Commit:** `b592831`.

## T15 · UXR-12 (the small half): the Chain screen explains itself — DONE

**What was done** (D222).
- **3D hint.** `chain_route.hint_3d` builds it from the **wired** case:
  `This 3D stage has no preview here. Its domain is 1.5 × 1.5 × 1.5 m,
  burst at z 2.0 m (from the 2D profile).`
  - Fed by 2D, the height is the 2D stage's burst z:
    `core/profiles.remap_profile_2d_to_3d` maps the 2D z straight onto
    the 3D z.
  - Fed by 1D, it is this stage's own cz, with `(set in this stage’s
    form)`.
  - `StageEditor.show_check` gains `source=`.
- **Route tooltips.** Each route button has a one-line tooltip
  (`chain_route.ROUTE_TIPS`). The route group keeps HINT.
- **The Run chain line.** The `\<model>\` part (or `set the Model on 02
  Run`) is a link in `accent_text`, re-coloured with the theme.
  - A click shows 02 Run with the Model box focused and selected
    (`ChainPanel.model_link_clicked` → `MainWindow._focus_model_box`).
  - `run_line_text()` still returns the plain text.
- The hand-off overlay on the previews stays in the backlog.

**Files:** `blastlab/ui/chain_route.py`, `chain_stage.py`,
`chain_panel.py`, `app.py`; `blastlab/tests/test_ui_chain_screen.py`;
`docs/gui-redesign-decisions.md` (D222, F45); one screenshot.

**Tests:** `python test_ui_chain_screen.py`: S4 (pin changed), S4u (new,
7; 220 in all).

**Criteria**
- PASS. The 3D hint equals the text built from the wired case:
  - on 1 → 2 → 3, `1.5 × 1.5 × 1.5 m, burst at z 2.0 m (from the 2D
    profile)`;
  - on 1 → 3, `burst at z 0.75 m (set in this stage’s form)`;
  - `01 Setup` is gone from it.
- PASS. Four route tooltips, non-empty, distinct, each one line.
- PASS. A click on the line gives `current_tab() == 'run'` with the
  Model box as the window's focus widget.
  - Offscreen: `linkActivated`.
  - Real platform: a QTest click on the link's glyphs; `hasFocus()` was
    True too.
- Also green: `test_ui_chain` (114), `test_ui_char_chain_wiring` and
  `test_ui_frame` (78, still five shortcuts).
- Real platform: `docs/qa/2026-10-03-gui-polish/gui11-chain-explains.png`.

**Commit:** `33bfb57`.

---

## The 11c close

Qt suites, offscreen, one at a time, all PASS:

| Suite | Checks |
|---|---|
| `test_ui_setup_form` | PASS |
| `test_ui_setup_tree` | 260 |
| `test_ui_setup_strip` | 129 |
| `test_ui_parity` (narrow sweep, D19 widths) | 41 |
| `test_ui_char_case_form` | PASS (re-recorded golden) |
| `test_ui_chain_screen` | 220 |
| `test_ui_results_screen` | 200 |
| `test_ui_output_card` | PASS |
| `test_ui_no_vtk_in_main` | PASS |
| `test_ui_no_mpl_pyplot` | 19 |
| `test_ui_char_results_meta` | PASS, unedited |
| `test_ui_char_results_exports` | PASS, unedited |
| `test_ui_char_hd13_run` | PASS, unedited |
| `test_ui_run_screen` | 203 |
| `test_ui_frame` | 78 |
| `test_ui_chain` | 114 |
| `test_ui_results` | 130 |
| `test_ui_preview` | PASS |
| `test_ui_hd13_form` | PASS |

Tk: `test_gui_char_case_form` PASS, unedited (scratch settings). The Tk
gate is 11b's. 11c touches only `ui/`, tests, docs and the Qt golden.

**Harness,** offscreen: `--solver native --scenario
C01,C02,C05,G01,G02,K02`, in `~\blastlab_qa\gui11-c-close`.
- All six scenarios ended `done`, exit 0, with 504 `ok` lines.
- There was one finding, S4 `py-warning` in K02: `Tight layout not
  applied…`. It predates 11c:
  - the same six at `d5944a7` (a temporary worktree, removed) give the
    identical finding (`gui11-c-close-base`);
  - K02 alone gives none at either commit (`gui11-c-K02-base`,
    `gui11-c-K02-head`).

  So it is order-dependent and inherited.

**Real platform:**
- the T13 and T15 probes (scratchpad), each `RESULT PASS`, with the
  window Win32-visible;
- `ui.app.main()` started once with throwaway native settings: platform
  `windows`, Win32-visible on 01 Setup, and main returned 0.

**Last:**
- `test_regression` **PASS**, byte-identical: seven files identical and
  `b2_profile.npz` arrays equal;
- `test_ui_char_chain_wiring` **PASS**, unedited.

**Frozen paths.** `git diff 116ea96..HEAD` over the plan's frozen list:
- `solvers/worker.py` (1 line, 11b);
- `services/validation.py` (11b);
- `tests/char_golden/ui_case_form.json`, from 11c only. That is the
  owner-approved T10 (4 `hidden` lists) and T11 (3 `/get` entries).

`blastlab/gui/`, `core/`, `models/`, `output/` and `viz3d/` are
untouched, and so are `view3d_host.py`, `run_controller.py`,
`viewer_link.py`, the baselines and every other golden.

**Never-stage list.** None of the seven paths is in any 11c commit.
Every commit was staged by explicit path. `git worktree list` shows only
the main tree.

## Changed committed assertions (plan §"Committed tests")

1. `test_ui_setup_form` S8: `Height Z [m]` → `Height H [m]`. A caption
   the plan renames (UXR-11).
2. `test_ui_setup_form` S9: the point-list section now sets its form to
   planar first, so its `x0 x1 y0 y1` hint and refusal checks keep their
   meaning.
   - The default axisymmetric form now reads r / z, which S8b asserts.
   - This is a fixture change; no check was removed.
3. `test_ui_chain_screen` S4: `e3.hint.text() == HINT_3D` →
   `.startswith(HINT_3D)`.
   - The hint is now built from the wired case (UXR-12), and S4u asserts
     the full text.
   - The structural half is unchanged: no canvas, no View3DHost.
4. `char_golden/ui_case_form.json`: the owner-approved re-records above
   (T10, T11).

No behaviour or number assertion was weakened. Everything else is new
checks.

## All files touched in 11c

- `blastlab/ui/`: `setup_spec.py`, `case_form.py`, `fieldform.py`,
  `preview_panel.py`, `results_anim.py`, `results_fields.py`,
  `results_field.py`, `scaled_distance.py`, `model_overlay.py`,
  `setup_panel.py`, `chain_stage.py`, `chain_panel.py`, `chain_route.py`,
  `run_gauges.py`, `app.py`
- `blastlab/tests/`: `test_ui_setup_form.py`, `test_ui_setup_tree.py`,
  `test_ui_setup_strip.py`, `test_ui_results_screen.py`,
  `test_ui_chain_screen.py`, `char_golden/ui_case_form.json`
- `docs/gui-redesign-decisions.md`: D210, D211, D219, D220, D221, D222,
  F45
- `docs/qa/2026-10-03-gui-polish/`: `gui11-axisym-labels-setup.png`,
  `gui11-axisym-labels-results.png`, `gui11-chain-explains.png`
- this report

## GUI screens touched (for QA)

- **01 Setup, native, 01 Threat:** no Material row (blastFoam shows it).
  The same holds on every Chain stage.
- **01 Setup, 2D axisymmetric:**
  - `Height H [m]`;
  - the Gauges, Structure, Refinement zones and Detonation points
    tables read `r z` / `r0 r1 z0 z1`, with their hints;
  - the preview's vertical axis reads `z [m]`.
- **01 Setup ▸ 06 Solver (and Chain stages):** the `= 12.0 ms` line
  under End time.
- **01 Setup ▸ 05 Gauges:** removing a gauge moves the trigger with it.
- **Tooltips:** the model-view hover readout, the Derived card's
  Nearest gauge and the 02 Run live `Z` header.
- **03 Results ▸ Field:**
  - an axisymmetric replay reads `r [m]` and `r … · z … m`;
  - Impulse reads `kPa·ms` on the bar, Min / Max and hover.
- **Chain:**
  - the 3D stage's centre text;
  - the route button tooltips;
  - the Run chain line as a link to 02 Run's Model box.

## Numerical changes

None. No solver value, solver default, case key, file format, export
byte or hand-off file changed. `test_regression` is byte-identical.

- A case written from a **loaded** case with AMR off now carries the
  file's own five AMR values instead of the form fallbacks (F16,
  owner-approved). They are inert with AMR off.
- Impulse `kPa·ms` is a relabel of an equal quantity (1 Pa·s = 1 kPa·ms).

## D / F rows added

In `docs/gui-redesign-decisions.md`:
- **D210** (T10): the owner's override, with the four golden `hidden`
  entries.
- **D211** (T11): narrower than the plan's wording, with the three
  `/get` entries.
- **D219** (T12). T12-T15 had no row number in the plan; they take the
  next free numbers after D218.
- **D220** (T13, amends D111).
- **D221** (T14).
- **D222** (T15).
- **F45:** what D222's hint shows on the default seed (below).

D212-D215 stay reserved for 11d.

## Suspected engineering issues noticed, not changed

1. **F45.** The default 1D → 2D → 3D seed has a 1.5 × 1.5 × 1.5 m 3D
   stage, while the 2D burst height is z 2.0 m. The 2D z maps straight
   onto the 3D z, so the burst lies above the 3D domain's top. Nothing
   warns: D200 does not predict 2D → 3D. The new hint states the
   numbers. It is an owner call: seed the 3D stage from the 2D height, or
   build D200's 2D → 3D reach check.
2. **Native materials.** Since T46 / N11 the native solvers take
   `material` (`solver1d/2d/3d`, `material_jwl`). But the Qt form has
   always sent `TNT` in native mode (`models/fields._charge_model`,
   UX-E2, D138: "the native solver only knows TNT"). Hiding the row
   (UXR-3) makes that rule visible rather than silent. If native ANFO /
   C4 runs are wanted, it is a `models/` change with the Tk gate.

   Also, Tk still shows the Material row in native mode (untouched by
   rule).

## Open questions for the owner

- D211: keep the "loaded form only" rule, or also write typed hidden
  AMR values of a fresh form (the plan's wording)? The latter moves the
  golden's `dim2_native/amr` entry.
- F45: the default chain's 3D box against the 2D burst height.
- Native materials (above): keep TNT-only in the Qt native mode?

## Left undone

Nothing in T10-T15. These stay in the backlog, as the plan says:
- P MAX in MPa;
- the charge caption `[kg TNT]` (E1);
- the Chain hand-off overlay;
- the Tk half of P2-24.
