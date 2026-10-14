# Batch gui-final-round2 - clean loop round 2: the round-1 QA and UX findings

- **Name:** `gui-final-round2`. Base `9cc172d`, branch `final-gui`. As in round 1, there is no new
  branch: the clean loop belongs to the final-gui batch (`2026-10-12-gui-final.md:310-329`). The file
  name follows round 1's D-R1.
- **Goal:** fix every round-1 finding that can be fixed without the owner, so the next QA/UX pass can
  come back clean. Sources: `docs/qa/2026-10-13-gui-final-round1/report.md` (F-1..F-5) and `ux-review.md`
  (U1..U6).
- **Risk: high.** Part A is `risk: low` (Qt only). Part B is `risk: high`: it touches `output/plots.py`,
  `services/exports.py` and `services/validation.py`.
- **track-end: yes.** After this batch the GUI block holds only `GUI-14 (j)` (home PC) and the owner
  questions below. That sends /bl-todo to the clean loop's next QA + UX pass. The clean-loop rules of
  `2026-10-12-gui-final.md:315-322` apply: every finding at any severity, exit on a pass with zero
  findings, and the runaway guard. Round 1 found 11. Stage 5 (DONE, merge into `master`) runs only
  after a clean pass (round 1 D-R2).
- **Why this batch:** the RESUME note (`TODO.md:31-42`) and the GUI-16 row (`TODO.md:57`) put
  "round 2 takes QA F-1..F-5 and UX U1-U6" first. `VV` (`TODO.md:75-98`) comes after GUI and before
  HD1.
- **Rules:** `CLAUDE.md` §6, §8.2, §8.6, §8.7, §9; `docs/agent-rules.md`. Tk (`blastlab/gui/`) is frozen,
  so nothing here touches it and no `test_gui_*` suite runs. Commits: `ui: ... (GUI-16)`,
  `output: ... (GUI-16)`, `services: ... (GUI-16)`.

## Findings to tasks

| Finding | Severity | Goes to |
|---|---|---|
| U1 (screen shows the finished stage while the next one meshes) + F-3 (strip says stage 1) | medium + low | A1 |
| U2 + F-2 (`Stopped` followed by stage 1's own ending) | medium + low | A2 |
| U3 (Keep-all scratch announced only in the log) | low | A3 |
| F-4 (live-gauge peak label clipped at the left) | low | A4 |
| F-1 (1D title and export say `kg TNT` for C4) | medium | B1 |
| U5 (Python exception in the unchecked-radii warning) | low | B2 (pin-safe form) and Q4 |
| U4 (stages numbered by dimension in Checks and dialogs) | low | **Q1**: moves 2 golden lines |
| U6 (stop reason in Pa, three coordinate precisions) | low | **Q2**: conflicts with D66 and D4 |
| F-5 (harness false positive) | low | **Q3**: edits a committed harness check |

## Feasibility probes run while planning ("Do it once")

- **F-1, title pins and goldens.**
  - `plots.charge_label` (`output/plots.py:50-58`) writes `kg TNT` for every material. So the 2D and 3D
    titles have the same defect: the QA report's "2D/3D use `charge_label(meta)`" means they share a
    helper, not that they name C4.
  - blastFoam metas carry `material` (`solvers/foam/backend.py:1311`, `:1764`, `:2534`). Native metas
    do not, and native is TNT.
  - Every fixture meta behind `char_golden/ui_results_meta.json`, `ui_results_exports.json`,
    `exports_qt.json` and `test_char_meta.py` either has `material='TNT'` or has no material (grep for a
    non-TNT `material` in `tests/`). The only C4 metas are `test_ui_results_screen.py:377`, which pins
    the method card and no title, and `_qa_ui_harness.py:2019`, a live scenario.
  - **Result:** a material-aware label with TNT as the fallback moves no golden byte. It also leaves
    `test_ui_results_screen.py:1567`, `:1580` and `:1619` unchanged, because their fixture is TNT. The
    owner's 2026-10-13 permission to change the `:1580` pin is not needed.
  - **The literal reading would move goldens.** "The 1D title uses `charge_label(meta)`" cannot be done
    as written: a 1D meta has `charge_kg`, not `charge` (`models/meta.py:215`). `:g` would also turn
    `1.0` into `1`, which moves 10 lines of `ui_results_meta.json` (`:38`…`:3631`). So B1 shares the
    *material word*, and each dimension keeps its own number format (D-R5).
- **U5:** `test_case_validate.py:170` (`'layout failed' in`) and `:194` (`'ZeroDivisionError' in`) pin
  the exception text inside the warning (B11, a gate suite). Moving the text "to the log only" would
  break both. B2 keeps it as a trailing detail, so every existing assert holds (Q4).
- **U4:** `char_golden/ui_chain_wiring.json:75` and `:83` (`refuse/native1d_foam3d_route13`) record
  `Stage 3 (3D): …` on route 1→3. Any UI renumbering moves them → Q1, not planned.
- **U6:** D66 (`docs/history/gui-redesign-decisions-D1-D198.md:76`, and `UX_REVIEW-redesign.md:534-535`)
  keeps the stop reason verbatim. Seven asserts pin that: `test_ui_results_screen.py:290`, `:335`,
  `:346`, `:353-354`, and `test_ui_run_screen.py:1248`, `:1274`, `:1290`. `baseline/transcript.txt`
  pins the native `p_last = … Pa` strings. GUI-13 D4 pins 2 decimals in Checks → Q2, not planned.
- **A1-A4:** no default, seed or golden is involved. Grep of `char_golden/` for `Stopped after`,
  `meshing` and `kept` gives no title or strip pin. The existing pins that A1 must keep are listed
  in its acceptance.

## Part A - risk: low (Qt run lifecycle, live gauges)

parallel-safe: yes
files: blastlab/ui/app.py, blastlab/ui/run_controller.py, blastlab/ui/run_panel.py, blastlab/ui/chain_strip.py, blastlab/ui/run_gauges.py, blastlab/tests/test_ui_chain_screen.py, blastlab/tests/test_ui_run_screen.py, blastlab/tests/test_ui_live_gauges.py
needs-wsl: yes (only the verifier's live checks; the implementer works headless)

New checks go into **new** check functions. The round-1 R1 check (`test_ui_chain_screen.py:1504-1524`)
and every existing assert stay as they are.

### A1 - GUI-16 round 2: a later chain stage owns the Run screen from its `stage` message (U1, F-3) - M

- **What happens now:** the worker posts `('stage', k, label)` before every stage
  (`solvers/worker.py:328`). The controller only logs it (`ui/run_controller.py:347-348`). `_chain_k`,
  `_run_pct`, the clock and the strip move only on `run_started` (`ui/app.py:1225-1238`), and blastFoam
  sends that after blockMesh, refinement and setRefinedFields. So for minutes the screen shows stage 1's
  `100 %`, `about 0 s left`, `Chain 1/2`, pill 2 `waiting`, and a Stop that asks "stage 1 of 2 at
  100 %?".
- **Change** (the UX fix, `ux-review.md:110-123`):
  - The controller forwards `stage` to a new `handlers.on_stage(k)` and still logs `=== Stage … ===`.
  - `on_stage(k)` does nothing for `k == 0`, so a single run is unchanged. For `k > 0` it:
    - sets `_chain_k = k + 1` and `_run_pct = None`;
    - empties the bar, with no `_frac` and no ETA;
    - sets the time line to `meshing stage k+1 · … elapsed` on a blastFoam stage and `starting stage
      k+1 · … elapsed` on a native one (D-R7);
    - sets pill k+1 to `running` with the value `meshing` or `starting`. The new word goes into
      `chain_strip.VALUE_SAMPLES`; a pill width that changes is a layout pin, listed with the reason;
    - starts the stage clock (D-R6).
  - `on_run_started` then only restarts the stage's ETA.
  - The window title and the Stop question drop the percentage while `_run_pct` is None:
    `Chain 2/2 · …` and "Stop <model> (stage 2 of 2, meshing)?".
  - R1's `reset_bar` branch (`app.py:1422-1424`) goes, because the stage in flight now owns the bar.
- **Acceptance:**
  1. A new check in `test_ui_chain_screen.py` on a blastFoam-like 2-stage chain:
     - stage 1 posts progress and its result, then `stage` 1 arrives with no `run_started`;
     - then the bar is not `100 %`, the time line has no `left`, `_chain_k == 2`, pill 2 is not
       `waiting`, and the Stop question names stage 2.
     - A native-like case (`stage` then `run_started` right away) ends with the same `_chain_k` and pill
       states as today.
  2. `gate.py --changed HEAD` is green on `test_ui_chain_screen`, `test_ui_run_screen` and
     `test_ui_drain`. That includes round 1's R1 checks, G15Q-5a (`test_ui_run_screen.py:1342-1356`)
     and the F25 bar reset.
  3. **Verifier, live:** a blastFoam 1D→2D chain with `QT_QPA_PLATFORM` unset, the §8.2 dry run first,
     and `pgrep` empty before and after. During stage 2's blockMesh, take a screenshot: `0 %`/empty bar,
     `meshing stage 2`, pill 2 `meshing`.
- **Depends on:** nothing.

### A2 - GUI-16 round 2: a chain stopped after a landed stage says so (U2, F-2) - S

- **What happens now:** `_finish_notice` passes `_last_result.stop_reason` to the banner and the time
  line (`app.py:1448-1454`, `run_panel.py:1457-1459`). That is stage 1's own ending, so the screen reads
  `Stopped after 15 s · shock arrived at outer boundary (…)`.
- **Change:** in `on_finished`, when `how == 'stopped'` and the last result is not `stopped_early`,
  `_finish_notice` gets a reason of its own, worded as in D-R8. The result's `stop_reason` stays
  verbatim in the method card (D66). A single run and a chain whose stopped stage posted a
  `stopped_early` result are unchanged. With A1 in place, `finish('stopped')` marks the meshing stage's
  pill `stopped`, and the caption reads `Chain stopped at stage 2 of 2`.
- **Acceptance:**
  1. A new check, with the R1 setup plus A1's `stage` message:
     - the time line starts `Stopped after` and contains `stopped by user`;
     - it contains neither `end time reached` nor `outer boundary`;
     - `strip.texts()[-1]` names stage 2;
     - pill 2 reads `stopped` and pill 1 `done`.
     - Control: a native chain stopped in stage 2's solve keeps its own `stopped by user` reason, as
       `test_ui_chain_screen.py:1504-1524` pins today.
  2. `gate.py --changed HEAD` is green on the same three suites.
  3. The verifier's live A1 run continues: Stop during stage 2's mesh, then a screenshot of the banner,
     the time line and the strip.
- **Depends on:** A1.

### A3 - GUI-16 round 2: a Keep-all scratch is named outside the log (U3) - S

- **Change:**
  - On the `folder` message (`run_controller.py:349-355`), when
    `manifest['wsl_scratch'].get('kept_because') == model_folder.KEEP_ALL_WHY`, send one
    `notify(..., 'info')`. It reaches the status bar and Messages and is not modal. Text: `WSL scratch
    kept (Keep all fields): <posix>`.
  - Add `('[note]', <muted>)` to `run_panel._LOG_TAGS` (`:1496`), with the theme's muted colour.
  - No change in `services/`: `KEEP_ALL_WHY` is only imported.
- **Acceptance:**
  1. A new check: a fake `folder` message whose manifest has `kept_because = KEEP_ALL_WHY` gives exactly
     one info notice, which names the path, and no dialog. A manifest without it gives none. A
     `[note]` line gets the muted colour, and `[warn]` and `[error]` keep theirs.
  2. `gate.py --changed HEAD` is green on `test_ui_run_screen` and `test_ui_drain`.
  3. The verifier's live check: a blastFoam 1D run with Keep all ticked. Messages lists the path, and no
     modal dialog appears.
- **Depends on:** nothing. It edits `app.py`/`run_controller.py` after A1, in the same session.

### A4 - GUI-16 round 2: the live peak-time label stays inside the enlarged card (F-4) - S

- **What happens now:** `run_gauges._SelectedCard.peak_lbl` is anchored at `(1.05, 0.5)` (`:611`), to the
  left of the peak. When the peak comes early (`0.09 ms`), the label runs past the plot's left edge,
  and `0.` is cut off (`R2_after_run.png`).
- **Change:** in `set_row` (`:653-657`), anchor the label to the peak's right (`(-0.05, 0.5)`) when the
  peak lies in the left half of the view range. Otherwise keep today's anchor.
- **Acceptance:**
  1. A new check in `test_ui_live_gauges.py`: with a peak at 2 % of the x-range, the label's scene rect
     lies inside the view box. With a peak at 80 %, the anchor is unchanged.
  2. `gate.py --changed HEAD` is green on `test_ui_live_gauges` and `test_ui_run_screen`.
  3. Verifier, real platform (CLAUDE.md §8.7): a screenshot of the enlarged card after a live 1D run
     shows `0.09 ms` whole.
- **Depends on:** nothing.

## Part B - risk: high (output/, services/)

parallel-safe: yes
files: blastlab/output/plots.py, blastlab/services/exports.py, blastlab/ui/results_fields.py, blastlab/services/validation.py, blastlab/tests/test_title_material.py, blastlab/tests/test_det_radii_text.py
needs-wsl: no

Both tasks are text in titles and warnings. Neither is calculation code, so no number moves. The
characterisation goldens listed in the acceptance are the before-picture, and they must stay
byte-identical. Run `gate.py --for <files>` before the first edit.

### B1 - GUI-16 round 2: figure titles name the charge's material (F-1) - M

- **TODO text:** F-1, "the 1D title uses `charge_label(meta)` as 2D/3D do" (owner 2026-10-13). It is
  also the figure-title share of `P1-9` decision 1, "kg ‹material›" in figure titles. That decision is
  already approved.
- **Interpretation** (probe above): one rule for the material word, used by every figure title.
  - Add `plots.charge_material(meta, material=None)`. It returns `material`, else `meta['material']`,
    else `'TNT'`.
  - `charge_label` uses it, so the 2D and 3D titles and the animation title (`output/animation.py:262`)
    follow.
  - `figure_results_1d` and `figure_gauges_1d` get a keyword `material=None`.
  - `services/exports.py` passes `res.meta.get('material')` at `:199-208` and `:228-235`.
  - `ui/results_fields.screen_title_1d` uses the same rule.
  - Each dimension keeps its own number format (D-R5). Nothing is written to a meta, to `MODEL.json` or
    to any export file (D-R9).
- **Acceptance:**
  1. A new `test_title_material.py`:
     - a C4 blastFoam 1D meta gives `kg C4` in the screen title, in `png_figures(res, 1)` (both
       figures) and in `report_figures(res, 1)`;
     - a C4 2D meta and a C4 3D meta give `kg C4` in the field and gauge titles;
     - a meta with no material, and a TNT meta, give exactly today's strings;
     - a planar 2D C4 gives `kg/m C4`.
  2. Byte-identical: `gate.py --changed HEAD` is green on `test_ui_char_results_meta`,
     `test_ui_char_results_exports`, `test_char_exports`, `test_char_meta`, `test_export_numbers_1d`,
     `test_ui_results_screen` and `test_ui_results`. The `:1580` pin is untouched.
  3. Part end: `gate.py --deep`, then `gate.py --only regression` last, byte-identical.
- **Depends on:** nothing. **References:** none. This is a label, not a standard's equation, and the TNT
  equivalence of P1-9 (3) is not part of it.

### B2 - GUI-16 round 2: the unchecked-radii warning leads with the input, not the exception (U5) - S

- **What happens now:** `_det_radii_unchecked` (`services/validation.py:1457-1467`) prints `the cell layout
  could not be computed (ZeroDivisionError: float division by zero)`.
- **Change:**
  - The warning keeps its start (`Ignition radii not checked` / `Detonation point k: ignition radius
    not checked`).
  - It then says `the cell layout could not be computed from the domain size and cell size` and names
    the values where the caller has them:
    - `ctx.dims` and `dx` at `:1420`;
    - the level and `h` at `:1444`, passed in by those callers.
  - The exception follows as a last clause, `(detail: <Type>: <msg>)` (D-R10, Q4).
- **Acceptance:**
  1. A new `test_det_radii_text.py`, with the same two failure set-ups as `test_case_validate.py:156-196`.
     The warning:
     - names the domain size and the cell size before any exception class;
     - still contains `not checked`;
     - keeps its prefix.
  2. `test_case_validate.py` is unchanged and green, including `:170` and `:194`. `gate.py --changed
     HEAD` is green on `test_case_validate`, `test_char_validation` and `test_ui_char_case_form`.
  3. Part end: as in B1 (3).
- **Depends on:** nothing (different file from B1).

## Verification

- **Part A:** light, by the default model, plus the live checks named in A1-A4. Each live check uses
  the real platform, the §8.2 dry run first, `pgrep` before and after, and a `__main__` guard (round-1
  QA note).
- **Part B:** full, on Opus, with `--deep` and regression last.
- Each verify report ends with a `## Status` block (`A1 GUI-16: …` … `B2 GUI-16: …`) for close_batch.py.
- **Then the clean loop's next pass.** gui-qa-tester and gui-ux-reviewer run on every Qt screen.
  **QA brief:**
  - **Run:**
    - a blastFoam 1D→2D(→3D) chain during stage 2's mesh: bar, time line, title, pills and the Stop
      question (A1);
    - a Stop there: banner, time line and strip (A2);
    - native chain stages (A1 must not flash);
    - Keep all: Messages and the `[note]` colour (A3);
    - the enlarged gauge card with an early peak (A4).
  - **Results:** a **C4** blastFoam 1D and 2D result: the screen titles, the PNG/HTML/GIF titles and the
    method card agree (B1). A TNT result is unchanged.
  - **Setup / Checks:** an incomputable layout reads in plain words (B2).
  - **The owner's answers to Q1-Q4** are decision rows. A finding that repeats an answered row is not a
    new finding.

## Risks and how they are protected

- **A1 moves the moment `_chain_k` changes**, which the strip, the clock, the title and the Stop rule all
  read. That risks an off-by-one on native chains and on stage 3. Protection:
  - the native-like control in A1 (1);
  - round 1's R1 checks and the existing chain checks (`test_ui_chain_screen.py:1398-1876`) stay green
    unedited;
  - `k == 0` is a no-op, so single runs cannot move.
- **A2 could hide a real stop reason.** It applies only when the last result is not `stopped_early`. The
  control in A2 (1) pins the stage-2-solve case.
- **B1 could drift a golden through number formatting or a meta key.** Each dimension keeps its own
  format, nothing writes `material`, and the five char suites in B1 (2) must stay byte-identical.
  Regression runs last.
- **B2 sits in a gate module.** It adds wording and leaves every B11 assert in place.

## Proposed defaults (decision rows)

| Row | Choice | Default | Why |
|---|---|---|---|
| D-R5 | B1 number format | 1D keeps `{charge_kg}` (`1.0`), 2D/3D keep `:g` (`1`) | No golden moves; the probe shows `:g` would move 10 lines |
| D-R6 | Stage clock (D50) in a chain | A stage's pill time starts at its `stage` message, so it includes meshing; the ETA restarts at `run_started` | That is the time the user waits; D50 counts wall time |
| D-R7 | A1 word on native stages | `starting` (native has no mesh), `meshing` on blastFoam | The stage's solver is known from its case |
| D-R8 | A2 wording | Time line `Stopped after 43 s · stopped by user during stage 2 of 2`. Banner `Result ready: <model> · stage 1 of 2 finished; stopped by user during stage 2.` | The UX layout (`ux-review.md:207-211`), shortened |
| D-R9 | B1 material source | `meta['material']`, else TNT; no case-file lookup | blastFoam metas carry it; native is TNT; no file read on a title |
| D-R10 | B2 exception text | Kept as a trailing `(detail: …)` | The live checks have no log, and the B11 pins hold (Q4) |

## Owner answers (2026-10-13)

All four recommendations approved: **Q1 yes** (task A5, re-record exactly `ui_chain_wiring.json:75`
and `:83`); **Q2 no change**, U6 recorded "by design (D66, D4)"; **Q3 yes** (task A6); **Q4** keep the
trailing detail (D-R10). Defaults D-R5..D-R10 stand.

## Needs clarification

- **Q1 - U4 renumbers stages by position, and two golden lines move.** Recommended: **yes**.
  - The format would be `Stage <position> (<d>D)`, used by `chain_panel._refuse`, the compat line
    (`chain_panel.py:358`) and the long-run dialog (`app.py:1122`). `services/chain.py` keeps its prefix,
    and the UI rewrites it.
  - On routes 1→2 and 1→2→3, position equals dimension, so the bytes are identical.
  - Only `ui_chain_wiring.json:75` and `:83` change, `Stage 3 (3D):` → `Stage 2 (3D):`. Re-record exactly
    those two lines (the Q3 precedent of 2026-10-12).
  - If yes, it becomes task A5 (S, `chain_panel.py`, `chain_route.py`, `app.py`). If no, U4 closes as
    "by design" with a decision row.
- **Q2 - U6 contradicts D66 and GUI-13 D4.** Recommended: **no change**. Record U6 as "by design (D66,
  D4)" so the loop does not raise it again.
  - The stop reason is the solver's verbatim record. Native strings are byte-pinned
    (`baseline/transcript.txt:20`, `:45`).
  - A kPa display formatter would mean editing 7 asserts (listed in the probes) and dropping D66.
- **Q3 - F-5 edits a committed QA harness check** (`_qa_ui_harness.py:3197`). Recommended: **yes**.
  - The check would accept an optional dedupe suffix: `re.search(r'\(stopped\)( #\d+)?$', labels[-1])`.
    The app's label `save1 - 2D (stopped) #2` is correct.
  - It is one line. If yes, it becomes task A6 (S) in Part A, and the QA stage runs it.
- **Q4 - U5 asks for the exception text in the log only.** That would mean editing `test_case_validate.py:170`
  and `:194` (B11). Recommended: **keep it as a trailing detail** (B2 as planned). The live checks have no
  log to send it to, and the class name helps a bug report.

## Remaining backlog (one line per item, RESUME order first)

- Clean loop rounds 3..N until a clean pass, then final-gui Stage 5 and the merge into `master`.
- `GUI-14 (j)`: HD13 char drift, home PC.
- `VV-0`, `VV-2`, `VV-4` (no reference data), then `VV-1`, `VV-3`, `VV-5`. `VV-6..8` are blocked on
  reference data, and `VV-9` comes last.
- `P1-9`: the rest after B1. Form labels, report text, preview radius, W_E per UFC 3-340-02 Eq. 2-1, Z.
- `HD1-18` + `P1-15`: severe preset, Qt only. They move the form's goldens, so they need a probe.
- `HD1-19`: (a) and (c) are ready; (b) waits on the owner. `HD1-16` step 2: after SBEDS. `HD1-17 (b)`:
  the owner's scenario.
- `HD1-14`: optional WSL run. `HD1-4`: the owner's call. Closed-vessel data: owner.
- `P1-4` · `N5-11` · the ≈2 % parallel offset · Claim 3 · audit corrections · `P1-8` … `P1-17` ·
  `P1-23` follow-ups · `P1-19`, which closes as Tk frozen in Stage 5.
- `P1-20` … `P1-22` · `P3-14`: the remap chain.
- Items Stage 5 adds: P1 parallel 1D blastFoam; P3 ideal-gas charge; three solver items.
- `P2-1` · `P2-2` · `P2-5` · amr2d thresholds · `N5-12` follow-up · `P2-11` · `P2-13` … `P2-15` ·
  `P2-23` · `P2-26` … `P2-30`. The Tk-only P2 rows close as Tk frozen.
- **P3** on request. **P4:** `P4-1` … `P4-3`.
