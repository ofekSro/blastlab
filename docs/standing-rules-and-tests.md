> **Academic CFD — blast-wave gas dynamics, Technion.** This project computes a
> pressure field in air and the structural load it produces, for blast-resistant
> design and explosive-safety siting (UFC 3-340-02, Kingery-Bulmash).
> Energetic materials enter only as a published equation of state. Scope: [docs/SCOPE.md](SCOPE.md)

# Standing rules and the test matrix

Moved verbatim out of [TODO.md](../TODO.md) on 2026-10-04 (1000-line cap).

## Standing rules for every task

```
Project: blastlab - Python blast-wave simulation desktop app, native numpy
1D/2D/3D solvers in blastlab/solvers/, blastFoam backend in
blastlab/solvers/foam/ (writes OpenFOAM-9 cases, runs them in WSL Ubuntu, reads
results back onto uniform numpy grids), pyvista/VTK viewer in blastlab/viz3d/.
GUI: PySide6 in blastlab/ui/ is THE GUI (`python -m blastlab`). The
customtkinter original in blastlab/gui/ is kept as the way back
(`python -m blastlab --tk`) and must not be deleted.
Ids like B23/G7/A5/N7/W2 refer to DONE.md section 5 (the reference index).

Hard rules:
- Never change native-solver stdout or the byte-pinned outputs unless the task
  explicitly says "re-baseline". `python blastlab/tests/test_regression.py` must
  stay green (or be deliberately re-baselined per the task, in the same commit).
- Foam goldens regenerate only via `python blastlab/tests/test_foam_writer.py --update`
  and an eyeballed diff.
- Tests are plain scripts: `cd blastlab/tests && python test_X.py`. Files named
  `_e2e_*.py` are manual end-to-end runs (need WSL, ~1-6 min each). Run the fast
  no-WSL matrix after every task; WSL suites once at the end of a task that
  touches solvers/foam/.
- WSL work: run in the FOREGROUND (backgrounded shells that spawn WSL children
  report completion early and lose stdout). Before any WSL suite check nothing is
  running (`wsl.exe -d Ubuntu -- pgrep -a blastFoam`); a foreign solver makes
  test_foam_stop and memory-heavy suites fail spuriously. After killing anything,
  check for orphans the same way and kill them. 2D axisym foam cases at default
  size can take 30+ min - use tiny domains.
- Do not touch files outside the task's scope without saying why.
- GUI verification: `python blastlab/tests/_qa_ui_harness.py --resume --scenario <ids>
  --redo <ids>` opens a real Qt window on screen - 63 scenarios (`--list` shows the
  matrix; output under ~\blastlab_qa\<stamp>\shots), plus `test_ui_*.py` (offscreen)
  and `_e2e_ui_*.py`. `_qa_gui_harness.py` is the same protocol against the Tk app
  and stays as long as `--tk` does; run it only when a change touches blastlab/gui/.
- Qt work: `blastlab/ui/` must never import pyvista/VTK - the 3D scenes live in
  the viewer child process (`blastlab/viz3d/process.py`). `test_ui_no_vtk_in_main.py`
  pins this.
- Windows: the test_regression baselines show as modified purely from CRLF
  conversion - do not commit them unless the task re-baselines.
- Markdown here is edited with editor tools only, never through PowerShell
  strings - PowerShell 5.1 mojibakes any file with a non-ASCII character.
- Finish by: (1) listing exactly what changed, (2) pasting the tail of each test
  you ran, (3) ticking the item here + a one-line note of what was done.
```

**Measurement discipline** — the full list is in
[docs/verification/physics-anchors.md §7](../docs/verification/physics-anchors.md).
The two that matter most: **never measure peak alone** (peak, positive-phase
impulse *and* arrival, every time), and **pre-register the decision rule with its
numeric threshold before the run that will be judged by it.**

---

## The test matrix

```
cd blastlab/tests

# Fast, no WSL - run after every task
python test_regression.py         # native byte-parity - MUST stay green
python test_foam_writer.py        # case-generation goldens
python test_foam_reader.py        # ascii+binary parsers, probes merge
python test_case_validate.py      # cap gating per backend
python test_foam_env.py           # WSL env probe parse, cleanup policy, settings
python test_hardware.py           # machine identity, cache TTL, host RAM, native caps
python test_adaptive_interval.py  # writeInterval controller
python test_foam_live_due.py      # live-frame cadence gate
python test_refine.py             # refined-mesh plan + AMR remap + validation guards
python test_settings_path.py      # repo settings file, migration, cleanup dry run, disk warning
python test_foam_start_frame.py   # the reader reads the writer's ");" - t = 0 frame
python test_bc_trigger.py         # boundary kinds, end time, trigger gauge, markers
python test_foam_postmortem_decomposed.py   # loading a parallel AMR run
python test_foam_resume.py        # restart points + the AMR FO disable
python test_gauge_summary.py      # per-gauge peak/arrival/impulse
python test_report.py             # field CSVs + HTML report
python test_foam_ingest_order.py  # ordered ingest + accumulators
python test_foam_amr_ingest.py    # AMR per-time ingest on fake time dirs
python test_deflagration.py       # HD1: the 0D burn model
python test_sdof.py               # HD1: the SDOF structural response
python test_unconfined.py         # HD1: the unconfined branch
python test_sensitivity.py        # HD1: the band around an uncalibrated peak
python test_room.py               # HD1-3a: a room as boxes, and what snapping does
python test_vent.py               # HD1-3c: the 0D -> CFD hand-off, phase by phase
python test_foam_chamber.py       # HD1-3b: the room as a blastFoam case
python test_qd.py                 # HD1-3e: siting, as a mechanism with no numbers
python test_vent3d_load.py        # HD1-3d: judging a finished 3-D vent run from its probes
python test_wallload.py           # HD1-13: reflected front + compressible stagnation at a point
python test_vent_wall.py          # HD1-13: the wall-load rule, Step 1 and Step 2's pure parts
python test_write_budget.py       # HD1-15: the write budget and the decomposed-copy purge
python test_ui_crashlog.py        # a raising Qt slot must not kill the process
python test_revolve3d.py          # (belongs in this matrix - fast, native, green)
python test_viz3d_sampling.py / test_viz3d_hooks.py / test_viz3d_scene.py
python test_viz3d_panel.py / test_viz3d_protocol.py
python test_ui_drain.py / test_ui_run_panel.py / test_ui_view3d_host.py
python test_ui_setup_form.py / test_ui_preview.py / test_ui_results.py
python test_ui_chain.py / test_ui_run_browser.py / test_ui_parity.py
python test_ui_three_surfaces.py / test_anim_scale.py
python test_ui_no_vtk_in_main.py  # no VTK in the GUI process
python test_ui_no_mpl_pyplot.py   # no pyplot in the GUI process
python test_gui_*.py              # the Tk suites - run when blastlab/gui/ or a
                                  # shared neutral module changes
python test_blast2d.py            # 2D native physics (the matrix bottleneck, ~47%)

# Slow, no WSL - run on its own, WITHOUT a timeout
python test_blast3d.py            # 3D native physics, ~12 min

# WSL (first confirm it is free: wsl.exe -d Ubuntu -- pgrep -a blastFoam is empty)
python test_foam_1d_vs_native.py  # physics gates (~2 min)
python test_foam_2d.py            # axisym + planar (~3 min)
python test_foam_3d_smoke.py --tiny
python test_foam_parallel.py      # np1 vs np2 + determinism (~5 min)
python test_foam_postmortem.py    # live-vs-loaded round trip
python test_foam_features.py      # multi-charge + activation none
python test_foam_kb_anchor.py     # KB free-air + C4/TNT (~2 min)
python test_foam_kb_anchor.py --impulse    # the impulse anchor
python test_foam_stop.py          # SIGSTOP/writeNow regression
python test_foam_wsl_resume.py    # the EIO / distro-teardown resume path
python _e2e_foam_*.py             # manual end-to-end, one at a time
python _e2e_ui_*.py               # real Qt window, real runs
```

> **A foreign blastFoam process makes `test_foam_stop` and the memory-heavy suites
> fail falsely. Check before blaming the code.**
>
> **Harness exit 0 is not "passed".** A failed `qa.check` records a finding and the
> scenario continues, and checks that passed are not recorded anywhere. The truth is
> in `findings.jsonl`.
