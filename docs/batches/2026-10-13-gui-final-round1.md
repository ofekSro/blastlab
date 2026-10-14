# Batch gui-final-round1 - the two known findings fixed, then the clean loop's first QA/UX pass

- **Name:** `gui-final-round1`. Base `00465a5`, branch `final-gui` (no new branch: the clean loop
  belongs to the final-gui batch, `docs/batches/2026-10-12-gui-final.md` "Running this batch across
  sessions", Stage 4). That plan names the round files `2026-10-12-gui-final-round<N>.md`; this one
  carries today's date (D-R1).
- **Goal:** fix the two product findings already on record from Parts D and F, so the clean loop's
  first full QA/UX pass judges a tree with no known defect.
- **Risk: high** (Part B touches `services/`). Part A `risk: low`, Part B `risk: high`. If the owner
  answers **no** to Q1, Part B is dropped and the batch is `risk: low`.
- **track-end: yes.** After this batch the GUI block keeps only `GUI-14 (j)` (HD13 char drift, home
  PC). The Tk-at-150 % item closes as "Tk frozen, owner 2026-10-13" in final-gui Stage 5. OUT has no
  open row. `yes` sends /bl-todo to Stage 4: gui-qa-tester and gui-ux-reviewer on every Qt screen,
  under the clean-loop rules of `2026-10-12-gui-final.md:315-322` (every finding at any severity goes
  into `round2`; exit after one full pass with zero findings; runaway guard after two rounds that do
  not lower the count). Those rules override the "medium or higher" rule in `docs/agent-rules.md`.
- **Why this and not HD1-18:** the RESUME note (`TODO.md:31-42`) puts `GUI-16` second, as "the LAST
  GUI batch ... QA/UX re-run until clean". Parts A-F are verified (`00465a5`), but Stage 4 (the
  clean loop) and Stage 5 (bookkeeping, merge into `master`) have not run, so `GUI-16` is still open.
  HD1 comes after it.
- **Rules:** `CLAUDE.md` §6, §8.2, §8.7, §9; `docs/agent-rules.md`. Tk (`blastlab/gui/`) is frozen,
  so nothing here touches it and no Tk suite runs. Commits: `ui: ... (GUI-16)`, `services: ... (GUI-16)`.

## Feasibility probes run while planning ("Do it once")

- **R1:** no default, seed or golden is involved. Grep `blastlab/tests/**/*.json` for `"how"`,
  `Stopped after`, `chain_finish`: no hits, so no golden pins how a chain ends. The committed checks
  that call `on_finished` are `test_ui_chain_screen.py:1398-1876` (9 calls) and
  `test_ui_run_screen.py:402-410, 1185, 1234, 1315, 1350`. All of them either post every stage's
  result or post none. None of them stops between stages, so the fix moves no existing pin.
- **R2:** **it would hit its own stop rule.** `test_model_folder.py:1471`
  (`test_e_keep_all_keeps_the_scratch`, OUT-3 E5) asserts `mf.KEEP_ALL_WHY in notice`. That is a
  committed behaviour test, so changing it needs the owner (agent-rules "Never touch"). Nothing else
  pins the notice: grep `_e2e_fields_purge.py`, `_e2e_ui_resume_foam.py`, `_e2e_model_folder.py` for
  `notice` gives no hits. The manifest's `kept_because` and the `[note]` log line (`:1472`) are not
  changed, so no file format changes. Hence **Part B runs only if Q1 = yes**.

## Part A - risk: low (Qt run lifecycle)

parallel-safe: yes
files: blastlab/ui/app.py, blastlab/tests/test_ui_chain_screen.py, blastlab/tests/test_ui_run_screen.py
needs-wsl: yes (the verifier's live check only; the implementer works headless)

### R1 - GUI-16 Stage 4 round 1: a chain stopped in a later stage ends `stopped`, not `done` (S)

- **Source:** `2026-10-12-gui-final-D.verify.md:82-86` (medium, pre-existing). The owner's fix,
  approved 2026-10-13 (`2026-10-12-gui-final.md:361-364`): "a Stop counts as `stopped` when the last
  stage posted no result".
- **What happens now:** `ui/app.py` `on_finished` (`:1407-1418`). Stage 1's result sets
  `_run_got_result` (`:1383`), and the controller's `stopped_early` is False when the Stop lands
  during stage k>1's blockMesh or between stages. So `how = 'done'`, `mark_complete()` fills the bar,
  the banner says Done and the chain strip finishes as done.
- **Interpretation:** count the results posted in this run, and reset the count where
  `_run_got_result` is reset (`:1316`). A run is `stopped` when `stopped_early` is True, or when
  `_stop_asked` is True and fewer results arrived than the run has stages (`max(1, _chain_n)`). A
  Stop pressed after the last stage posted its result still ends `done`, as today. When the stopped
  stage's bar never got a progress message, it shows that stage's state (`0 %`, empty), not stage
  1's `100 %`. G15Q-5a / D4 applied the same rule to a single run.
- **Acceptance:**
  1. A new check in `test_ui_chain_screen.py`: on a 3-stage chain, stage 1 posts its result, then
     `_stop_asked = True` and `on_finished(False, False)`. Afterwards `rp.time_text()` starts with
     `Stopped after`, the strip's last text says the chain stopped (not done), and the bar is not
     100 %. A second case has the Stop land between stages, with the same outcome.
  2. Control, in the same check: all three results posted plus a late `_stop_asked` gives `done`.
     `gate.py --changed HEAD` is green on `test_ui_chain_screen`, `test_ui_run_screen` and
     `test_ui_drain`.
  3. The verifier repeats the D-verify repro live: a blastFoam 1D→2D chain, Stop during stage 2's
     blockMesh, `QT_QPA_PLATFORM` unset. The banner and strip say Stopped. Run `pgrep` before and
     after, and do the §8.2 dry run first.
- **Depends on:** nothing.

## Part B - risk: high (services/) - only if Q1 = yes

parallel-safe: yes
files: blastlab/services/model_folder.py, blastlab/tests/test_model_folder.py
needs-wsl: no

### R2 - GUI-16 Stage 4 round 1: "Keep all fields" kept on purpose raises no error dialog (S)

- **Source:** `2026-10-12-gui-final-2-F.verify.md:25-32` (S3). The F12 harness scenario auto-dismisses
  a modal `show_error` that a real user would have to click.
- **What happens now:** `services/model_folder.py` `verify_and_release_scratch` (`:1280-1290`). With
  `why == KEEP_ALL_WHY` the log line is already downgraded to `[note]` (`:1284`), but `kind` stays
  `'warn'`. The function therefore builds `notice`, and the GUI shows "The blastFoam run finished, but
  its WSL scratch was kept" for an outcome the user asked for.
- **Change:** no `notice` when `why == KEEP_ALL_WHY` (D-R3). `kept_because`, the `[note]` line, the
  manifest and every other `warn` path stay as they are.
- **Acceptance:**
  1. `test_model_folder.py:1471` becomes `assert notice is None`, and this is the only committed-test
     line edited (Q1). The `kept_because` and `[note]` asserts at `:1470` and `:1472` still pass
     unchanged.
  2. The other notice paths still give text: `:969`, `:984`, `:998`, `:1008`, `:1045`, `:1064`,
     `:1321`. `gate.py --changed HEAD` is green on `test_model_folder`, then `gate.py --deep` for the
     part, then `gate.py --only regression` last, byte-identical.
- **Depends on:** Q1.

## Verification

- Part A: light, by the default model. Part B: full, on Opus. The verify reports end with the
  `## Status` block (`R1 GUI-16: ...`, `R2 GUI-16: ...`) so that close_batch.py can read them.
- Then Stage 4, the clean loop. **QA brief** (collected from the verify reports' "screens for QA"
  sections, so the testers start from them):
  - **Setup / Checks:** trigger notes, the unchecked-radii warning, captions, the dropdown and the
    Where column (B-verify:71, C-verify:48).
  - **Run:**
    - the drop line, log colours, `G<n>` trigger lines and `[warn] ... dropped`;
    - live gauges during blastFoam 1D / 2D;
    - the bar after a Stop during meshing;
    - the R1 chain Stop;
    - Detach / Re-attach on native 3D;
    - Close with the Setup 3D preview open and during a native 3D run (D-verify:106-111).
  - **Chain:** cards, Checks, click-to-focus, stage 3 at Lz 2.5.
  - **Results:**
    - the Gauges default row, `→` labels, the 3-decimal drop titles, footnotes and GIF `x` markers;
    - Open a model folder, and the run browser's Model column;
    - the `m/kg¹ᐟ³` glyph;
    - **a live blastFoam 1D result title never says `idealGas`** (C12; the owner's live sighting was
      not reproduced, C-verify:44).
- **Stage 5 runs once, after the loop exits clean** (D-R2), as `2026-10-12-gui-final.md:323-329`
  lists it. It covers the final-gui plans and every round file, then merges `final-gui` into `master`.

## Risks and how they are protected

- **R1 could turn a finished chain into `stopped`.** The control case in acceptance 1-2 pins that a
  late Stop still gives `done`. The single-run checks in `test_ui_run_screen.py:1342-1356` (G15Q-5a)
  stay green.
- **R1's count could drift if `on_result` is fed by hand outside a run** (tests do this). Reset the
  count where `_run_got_result` is reset, and count only while `_running_ui`. This follows the comment
  at `:1373`.
- **R2 sits in a shared services module.** The change is one condition and moves no number or format.
  It gets full verification and the regression gate last. The existing notice tests are listed in
  acceptance 2, so a broader change shows up there.
- **Neither task is calculation code,** so no characterisation test is needed first.

## Proposed defaults (decision rows)

| Row | Choice | Default | Why |
|---|---|---|---|
| D-R1 | Round file name | `2026-10-13-gui-final-round1.md`, later rounds `-round<N>` with their own date | The prompt fixes today's date; the base plan's name is a pattern |
| D-R2 | When final-gui Stage 5 runs | Once, after the clean loop exits, over every final-gui plan and round file | `2026-10-12-gui-final.md:315-329` order |
| D-R3 | KEEP_ALL feedback | No dialog. The `[note]` log line and `kept_because` in MODEL.json are enough | The user ticked the box; the run browser still opens the scratch |
| D-R4 | R1's notion of "stages" | `max(1, _chain_n)` results expected per run | `_chain_n` is 0 for a single run (`:107`) |

## Needs clarification

**Owner answer 2026-10-13: approve all** - Q1 yes (Part B runs, `risk: high`), Q2 yes (the
orchestrator adds the VV header block to `TODO.md` in Stage 5).

- **Q1 - R2 edits a committed behaviour test.** `test_model_folder.py:1471` pins that "Keep all
  fields" produces a dialog text (OUT-3 E5: "says why"). **Recommended: yes.** Change the line to
  `assert notice is None`. The "says why" stays satisfied by the `[note]` log line (`:1472`) and
  `kept_because` (`:1470`). A modal error for an opted-in outcome is the defect. If the answer is no,
  Part B is dropped and the dialog stays as designed.
- **Q2 - the untracked owner draft `docs/vv-plan.md`** (track `VV`, VV-0..9) is not in `TODO.md`, so
  it is not in the priority order. **Recommended:** paste its header block into `TODO.md` as its own
  block below GUI and above HD1, before the next planning run. VV-0, VV-2 and VV-4 need no reference
  data, and VV-2's runs are launched by the owner. If it stays out of `TODO.md`, the next batch after
  GUI is HD1-18 + P1-15 (below).

## Remaining backlog (one line per item, RESUME order first)

- **Clean loop** rounds 2..N (QA/UX findings), then final-gui Stage 5 and the merge into `master`.
- `GUI-14 (j)`: HD13 char drift, home PC.
- `HD1-18` + `P1-15`: the severe preset with `a` in mm/s/MPaⁿ. Now Qt only (§9). It moves the
  form's goldens, so the planner runs the feasibility probe there.
- `HD1-19`: (a) and (c) are ready. (b) waits on the owner's "was the step deliberate".
- `HD1-16` step 2: after the owner's SBEDS run.
- `HD1-17 (b)`: needs the owner's design-basis scenario.
- `HD1-14`: optional, a WSL run with `write_budget`.
- `HD1-4`: close or keep, the owner's call. Closed-vessel data: owner.
- `P1-4` · `N5-11` · the ≈2 % parallel offset · Claim 3 · the audit corrections · `P1-8` … `P1-17` ·
  `P1-19` (closes as Tk frozen in Stage 5).
- `P1-20` … `P1-22` · `P3-14`: the remap chain.
- Stage 5 adds: P1 parallel 1D blastFoam; P3 ideal-gas charge for blastFoam; three solver items
  (2D `t_end` "safety cap", the 3D extra-charges `det_radii` count, `_scan_set_mass`).
- `P2-1` · `P2-2` · `P2-5` · the amr2d thresholds (owner) · `N5-12` follow-up · `P2-11` ·
  `P2-13` … `P2-15` · `P2-23` · `P2-26` … `P2-30`.
- P2-16 / P2-19 / P2-20 and the Tk half of P2-24 close as Tk frozen in Stage 5.
- **P3** on request. **P4:** `P4-1` … `P4-3`.
