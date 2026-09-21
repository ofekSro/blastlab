> **Academic CFD — blast-wave gas dynamics, Technion.** This project computes a
> pressure field in air and the structural load it produces, for blast-resistant
> design and explosive-safety siting (UFC 3-340-02, Kingery-Bulmash).
> Energetic materials enter only as a published equation of state. Scope: [docs/SCOPE.md](SCOPE.md)

# Heavy runs — the catalogue, and what is still open

> **Read this first.** This catalogue was written when the development machine
> was **7.7 GB of RAM with 4 physical cores**, and WSL got 5 GB of that. It listed
> the things that could not be decided on such a machine.
>
> **That machine is no longer the one in use.** The current host is an i7-14700,
> 20 physical / 28 logical cores, 128 GB RAM, with a ~62 GiB WSL VM — which *is*
> the strong machine this catalogue was waiting for, and R1–R9 were run on it
> during the first QA night. **Most of this catalogue is now answered.**
>
> What remains is kept here because the runs are still the right runs, and
> because two of them were never completed.

Results and full detail: [history/qa-nights.md](history/qa-nights.md).

---

## Status

| # | Run | What it was for | Status |
|---|---|---|---|
| **R1** | Full-size 2D default | Is the reduced default right, or just compensation for a weak machine? | ✅ **Answered — the reduction was correct.** Not runnable anywhere: 4.6–8.8 **days** |
| **R2** | `_e2e_foam_obstacle2d axi` | The axisymmetric obstacle path, never completed | ✅ **PASS**, ~2.3 h, deterministic end time 3.4610165 ms — but only after three separate fixes |
| **R3** | `_e2e_foam_amr2d` / `_e2e_foam_refine2d` | Confirm the fixture fix on other hardware | ⚠️ refine2d **PASS**; amr2d **FAIL** on two accuracy checks — a real finding, see below |
| **R4** | `test_blast3d` | Wall time — decides whether it returns to the fast matrix | ✅ **PASS, 754 s.** Still too slow for the fast matrix |
| **R5** | `_e2e_solver_viewer.py` | Never finished on the old machine | ✅ **Finished naturally in ~35 s.** The "45 minutes" was folklore predating the current defaults. **Back on the runnable list** |
| **R6** | The real cell-memory ceiling | Is `BYTES_PER_CELL` machine-specific? | ✅ **Answered — it is not.** 2,696 measured against 2,650 assumed, a 1.7 % gap |
| **R7** | Parallel AMR at 4 and 8 ranks | Never tested above 2 ranks | ✅ **Measured.** Monotonic to 8, but 4→8 buys only 18 % |
| **R8** | `_e2e_gui_chain_foam.py` | Never run at all | ⚠️ **FAIL, twice** — both failures real; since fixed |
| **R9** | Eye checks | Four things only a person can judge | ⚠️ **Was BLOCKED** (no interactive desktop). The screenshot problem is since solved by `QWidget.grab()`; the four checks themselves still want a person |

### What is still genuinely open

1. **R3's `_e2e_foam_amr2d` accuracy failure.** AMR reads 11.8 % low on peak and
   11.1 % late on arrival against the uniform reference, on thresholds of 10 %.
   The test is correct — it measures a real thing. **The owner decision is which
   way to resolve it:** relax both thresholds to 15 % and document that as AMR's
   accuracy at this configuration, or tighten the test's AMR configuration (more
   levels / smaller `amr_interval` / larger `amr_buffer`) until it keeps up with
   the uniform mesh.
2. **R9's four eye checks**, which no automation replaces:
   - **ParaView opens the exported VTK files.** Run a small 2D foam case, click
     **VTK** in Results, open one file from the directory in ParaView.
   - **Volume render with manual Min/Max.** In the 3D viewer: enable Volume,
     switch to Density, turn off Auto and type Min/Max. Does the render update
     immediately?
   - **DPI other than 100 %.** Set Windows to 125 % and 150 %, open the
     application, check all four tabs for clipped text or buttons pushed out.
     *(Now partly covered by harness scenario Q04.)*
   - **A second monitor**, preferably at a different resolution. Does the window
     stay usable, and does the 3D viewer render correctly after the move?
3. **`balance yes` at 8 ranks** was never tried — it required editing a tracked
   file, which the night's rules forbade. The measured 1:64 load imbalance is
   strong evidence it is worth testing; a later night measured the balanced case
   at np=4 as **1.33× throughput with the answer unchanged** (79,724 against
   79,715 cells, peaks identical to two digits).

---

## What a machine needs for these

| Requirement | Minimum | Why |
|---|---|---|
| Host RAM | **32 GB** (16 GB partially works) | R6 alone asks ~6.1 GB of WSL |
| WSL VM RAM | **16 GB** (`memory=16GB` in `.wslconfig`) | R1, R6, R7 |
| Physical cores | **8+** | R7 tests 4+ ranks |
| Free disk | **60 GB** | foam runs accumulate in `/root/blastlab_runs` |
| Time | **~6–8 h** for the whole list | Can be split; follow the priority order |

**Environment:** WSL2 with a distro named exactly `Ubuntu`; OpenFOAM-9 +
blastFoam with `/root/OpenFOAM/OpenFOAM-9/etc/bashrc` present, and `blastFoam`,
`blockMesh`, `setRefinedFields`, `topoSet`, `refineMesh`, `decomposePar`,
`reconstructPar` on PATH after sourcing it; Python 3.12 with the requirements;
ffmpeg on PATH.

**Sanity gate before starting** — must pass, or nothing else means anything:

```
cd blastlab/tests
python test_foam_env.py            # finds WSL and blastFoam
python test_regression.py          # must be green byte-for-byte
```

> **⚠ Every time estimate written before the charge-resolution change is wrong.**
> Raising the charge resolution from 5 cells to 8 across the radius multiplies 2D
> cells by 2.56 and shrinks `deltaT` by 1.6 — **~4.1× in total cost.** A run
> labelled "~30 min" measured **~105 min**. Treat any un-remeasured estimate in
> this repository as pre-change.

---

## Ground rules for an unattended run

These are the rules the QA nights ran under. They are what made the results
trustworthy, and two of them were learned the hard way.

1. **Do not edit any existing file**, and run no state-changing git command
   (`commit`, `push`, `pull`, `stash`, `checkout`, `reset`, `merge`). All output
   goes to **new files only**. If a test cannot run without a small code fix —
   **do not fix it.** Record the required fix as a diff in the results file and
   mark the run BLOCKED.
2. **Never run two WSL/foam runs at once.** Before every one:
   `wsl -d Ubuntu -- pgrep -a blastFoam` must come back empty. If it is not empty
   and it is not yours, wait up to 10 minutes, then skip and record
   `SKIPPED: foreign solver`. A foreign solver makes memory-sensitive suites fail
   falsely.
3. **Do not touch the baselines.** If `test_regression` fails, that is a result to
   record, not something to fix. **Never** run `test_regression.py --update` or
   `test_foam_writer.py --update`.
4. **Do not delete `/root/blastlab_runs` before you have documented it.** If the
   disk fills: `python -m blastlab --clean-foam-runs --keep-gb 20`, and record
   that you did.
   > **And the trap that actually bit:** you do not have to run the cleanup for it
   > to happen. **blastlab cleans automatically on every GUI start**, and any
   > `_e2e_gui_*` test starts a GUI. That is how 34 runs — including the crash
   > directory under investigation — were destroyed in seconds. Before a session
   > that matters, verify `env.auto_cleanup(settings.load())` returns `(0, 0)`, and
   > copy out any run you care about.
5. **Do not use a timeout** on the deliberately-long runs (`test_blast3d`,
   `_e2e_foam_obstacle2d`) — an interrupted run looks like a failure and is not.
   Give everything else a generous timeout (30 min) so one stuck run cannot
   swallow the night.
6. **Budget the time and stop at a whole run.** Record what you did not get to,
   and why.
7. **If something is unclear, take the conservative option, document the choice,
   and continue.** There is nobody to ask. Every such choice belongs in the
   results file, because each one changes what was measured.

### Two traps specific to this environment

- **A user-level environment variable does not reach shells that already exist.**
  Any script that builds an `App` without pointing `BLASTLAB_SETTINGS` somewhere
  safe starts the automatic cleanup. The fix must be **structural, not
  instructional**: a wrapper script that every python call goes through, which
  sets the variable and does the `cd`. It cannot be forgotten, because it *is* how
  python gets started.
- **Commas in PowerShell.** `--redo B06,I05` without quotes reaches argparse as one
  bad value; the harness prints `nothing to do` and **exits 0** — a silent failure
  that looks like success. Quote every argument containing a comma.

---

## The runs

For each: **the command**, **what to record**, **what counts as success**.
**Record the numbers even when it passes** — for half of these the number *is* the
product, not the PASS.

### R1 · The full-size 2D default

```python
from blastlab.core.case import Case2D, validate_case
from blastlab.solvers.foam import env
print('hardware:', env.hardware(probe=True))
c = Case2D(Lx=10.0, Ly=10.0, cell_size_m=0.025, charge=1.0,
           center=(0.0, 5.0), solver='blastfoam')
r = validate_case(c)
print('errors  :', r.errors); print('warnings:', r.warnings); print('notes   :', r.notes)
```

If `errors` is empty, actually run it and record the wall time, peak pressure and
peak RSS of the blastFoam process.

**Record:** the `env.hardware(probe=True)` output; all three validation lists; the
cell count and the ceiling it reports; and if it runs, **wall time in seconds**.

**Success is a number, not a pass/fail.**

> **Note the headless trap:** a block that does not call `env.hardware(probe=True)`
> itself will be **refused even on a 128 GB machine**, because the hardware probe
> is process-local and only the GUI persists it. That refusal is itself a finding
> worth recording — record both outcomes.

### R2 · `_e2e_foam_obstacle2d axi`

```
wsl -d Ubuntu -- pgrep -a blastFoam      # must be empty
python _e2e_foam_obstacle2d.py axi       # NO timeout
```

The dangerous path by the script's own docstring: `boxToCell` judges the wedge's
coordinates, and if the intersection is wrong nobody would know.

**Record:** every `[PASS]`/`[FAIL]` line, the wall time, and the
`revolve ring for the 3D view` line in particular.

### R3 · `_e2e_foam_amr2d` + `_e2e_foam_refine2d`

```
python _e2e_foam_amr2d.py
python _e2e_foam_refine2d.py
```

**Record:** each summary line, and the AMR lines
(`AMR t = ... : N cells (+M), L0 .. / L1 .. / L2 ..`) of the last run.

### R4 · `test_blast3d` — native 3D physics

```
time python test_blast3d.py          # NO timeout
```

**Record:** `ALL CHECKS PASSED` or the failure, and the **exact wall time**. If it
drops below 8 minutes, it can return to the fast matrix on such hardware. *(It
measured 754 s — so it stays out.)*

### R5 · `_e2e_solver_viewer.py`

```
python _e2e_solver_viewer.py         # opens a real VTK window - do not close it
```

**Record:** whether it finished and how long it took, whether the window showed an
expanding wave, and whether playback worked at the end. One screenshot mid-run and
one during playback.

### R6 · The real cell ceiling

> **Do not vary `cell_size_m` to build the sweep.** The **charge**, not the cell
> size, sets the cell size — 25 kg at "8 cells across the radius" gives 0.01927 m
> regardless, so all points collapse and the regression slope is undefined. **Vary
> the domain with the charge held fixed**, and keep all points serial.

Sample RSS alongside:

```
wsl -d Ubuntu -- bash -lc 'while true; do ps -o rss= -C blastFoam | sort -n | tail -1; sleep 2; done'
```

**Record:** for each of three sizes — cell count, peak RSS in MB, wall time.

**Success:** compute `BYTES_PER_CELL` from the regression slope and compare to
2,650. A gap above 20 % would mean the constant must be measured per machine.
*(Measured 2,696 — a 1.7 % gap. It does not.)*

### R7 · Parallel AMR at 4 and 8 ranks

```
python test_foam_parallel.py         # should now print a ceiling >= 4
python _e2e_foam_amr_ab.py           # serial against parallel
```

Then 1 / 2 / 4 / 8 ranks manually on one case
(`Case2D(geometry='axisymmetric', Lx=2, Ly=4, cell_size_m=0.02, center=(0,2),
charge=5, amr_levels=2, gauges=[(1.0,2.0),(1.5,2.0)], n_snapshots=1)`).

> **Run every rank count to the same physical time**, not "to the end". With no
> terminate boundary, "the end" is a ~117 ms safety cap — hours per rank count.
> And say explicitly which gauges the wave never reached, so they are not presented
> as measured.

**Record:** ranks → wall time → gauge peaks, and the relative peak spread between
1 and 8 ranks.

**Success:** wall times fall monotonically to at least 4 ranks; gauge peaks across
rank counts agree within **1 %**.

> **A trap when testing `balance`:** `writer.py` does
> `from .dicts import AMR_LOAD_BALANCE` — a *from*-import. Setting
> `dicts.AMR_LOAD_BALANCE = False` alone **does not change the case written**, and
> the experiment returns "no difference" for entirely the wrong reason. Set both
> modules and print both at the top of the log.

### R8 · `_e2e_gui_chain_foam.py`

```
wsl -d Ubuntu -- pgrep -a blastFoam      # empty
python _e2e_gui_chain_foam.py
```

**Record:** every check line, `gauge time spans per stage`, and `results:` (three
labels).

**Success:** and in particular that both *"stage N starts where stage N−1 ended,
not at 0"* checks pass — that is the single physical clock, and the half that was
broken.

### R9 · The eye checks

See "What is still genuinely open" above. The automated screenshot round that
produces the material:

```
python _qa_ui_harness.py --list                 # the scenario matrix
python _qa_ui_harness.py --scenario D04,E05,E06
```

Output lands under `~\blastlab_qa\<timestamp>\shots`.

---

## Reporting format

One file, and for each run:

```markdown
## R<n> · <name>
- machine: <CPU, physical/logical cores, RAM, WSL RAM, Windows version>
- date:
- command run:
- wall time:
- result: PASS / FAIL / a number
- output (the tail, 30-60 lines):
- numbers measured: <RSS, cells, peaks, arrivals...>
- notes: <anything that looked unusual>
```

**Attach once at the top:** the full `env.hardware(probe=True)` output,
`wsl -d Ubuntu -- free -h` and `nproc`, the contents of `%USERPROFILE%\.wslconfig`,
and — if anything crashed — **the 60 lines before the crash, not just the message.**
