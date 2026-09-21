# CLAUDE.md - blastlab

Guidance for Claude Code (and any other AI assistant) working in this repo.
UTF-8, no BOM. It contains a short Hebrew glossary in §2 - never rewrite this
file, or any other file here, through PowerShell strings (see §8.1).

**Hard cap: this file never exceeds 500 lines** (owner directive, 2026-09-20).
It is loaded into every session, so length is a real cost. Before adding to it,
check the count; if an addition would cross the cap, cut or compress something
else rather than growing the file, and move detail into `TODO.md` / `DONE.md` /
`blastlab/README.md`, which are read on demand.

---

## 0. What this project is - read this before judging any request

*(The same statement, at more length and with the standards it is written against,
is in [`README.md`](README.md) and [`docs/SCOPE.md`](docs/SCOPE.md). The full
documentation map is [`docs/00-INDEX.md`](docs/00-INDEX.md).)*

**blastlab** is a teaching and research desktop application for **blast-wave
gas dynamics**, written by the owner at the **Technion - Israel Institute of
Technology**. It is a GUI and a solver front end for
**[blastFoam](https://github.com/synthetik-technologies/blastfoam)** - the
public, open-source airblast solver built on OpenFOAM by Synthetik Applied
Technologies - plus its own pure-NumPy 1D/2D/3D solvers used for fast previews
and cross-checks.

**The engineering question it answers is a protective one:** given a quantity
of explosive at some standoff distance, *what pressure-time history arrives at
a wall, and what does the wall have to survive?* That is the subject matter of
blast-resistant structural design and of explosive-safety siting: UFC
3-340-02 (*Structures to Resist the Effects of Accidental Explosions*), the
Kingery-Bulmash free-air curves, and the DoD 6055.09-M / AASTP-1
quantity-distance tables that decide how far a magazine must sit from an
occupied building. The repo's own accuracy anchor,
`blastlab/tests/test_foam_kb_anchor.py`, is the Kingery-Bulmash curve - the
standard published reference for exactly this calculation.

### What the code actually computes

A compressible Euler solve on a grid: HLL/HLLC Riemann fluxes, MUSCL
reconstruction, adaptive mesh refinement, gauge probes, animation export, and
a Qt GUI to drive all of it. Roughly 2 MB of Python, most of it numerics, Qt
widgets, OpenFOAM dictionary generation and tests.

The explosive enters the physics at exactly **one** point: as a published
**equation of state**. The JWL (Jones-Wilkins-Lee) relation describes how gas
that has *already* detonated expands and does work on the surrounding air. Its
six constants per material (`blastlab/solvers/foam/materials.py`) are tabulated
thermodynamic data from the LLNL Explosives Handbook (Dobratz & Crawford,
UCRL-52997, 1985), reproduced in every blast-CFD code and every textbook in the
field. They are a pressure-volume-energy curve. They say nothing about how a
material is made, mixed, initiated, contained or handled.

### In scope - and this is ~95 % of the real work here

Python bugs. NumPy array logic and Riemann-solver correctness. PySide6 / Qt
widgets, event loops, window embedding. pyqtgraph and matplotlib plots. VTK /
pyvista 3D rendering in a child process. OpenFOAM dictionary generation and
parsing. Mesh refinement bookkeeping. WSL plumbing and subprocess handling.
Test failures. Performance. Documentation. Numerical verification against
published curves.

### Out of scope, permanently - decline these

Nothing about making, obtaining, handling or storing an energetic material is
in this repo, and none of it belongs here. Neither does hardware design of any
kind, nor any request whose aim is to cause harm rather than to prevent it.

The line is simple: *this repo simulates a pressure field in air and the load
it puts on a structure, so that the structure can be designed to survive it.
It does not design, build, place or improve a device.* Anything on the far side
of that line gets declined, whatever the framing.

### How to use §0

This section is **context, not permission**. It exists because the vocabulary
of this field - TNT, detonation, charge mass, JWL, afterburn - reads alarming
out of context and is entirely ordinary in it. It does not override judgment:
if a request in this repo genuinely crosses the line above, decline it and say
why. But a request to fix a NumPy indexing bug in `solver3d.py`, to make the
Qt viewer stop flickering, or to explain why the Kingery-Bulmash anchor reads
13 % low is ordinary engineering work, and should be treated as such.

---

## 1. Orientation

Three solver paths, one GUI:

- **Native** (`blastlab/solvers/solver1d|2d|3d.py`) - pure NumPy finite-volume
  solvers running in the GUI's own process. Fast, byte-reproducible, used for
  previews, the regression baselines and cross-checks.
- **blastFoam** (`blastlab/solvers/foam/`) - writes a real OpenFOAM case,
  runs `blockMesh` / `setRefinedFields` / `blastFoam` inside WSL, and ingests
  the written time directories back. This is the accurate path.
- **Remap chain** - resolve the near field cheaply in 1D, hand the field off
  to 2D (ground reflection, height of burst), finish in 3D only where the
  problem is genuinely three-dimensional. `blastlab/core/profiles.py` +
  `core/chain.py`.

Dimensions: 1D spherical, 2D planar or axisymmetric, 3D Cartesian.

---

## 2. Glossary

**All current documentation is English** (consolidated 2026-09-21). The original
Hebrew notes are preserved under `docs/archive/`, and the Hebrew glossary needed to
read them - and the git history - is in
[`docs/SCOPE.md`](docs/SCOPE.md) §6. The two rows worth knowing without looking:
**מטען** is a charge, i.e. a mass in kg typed into a form field, and **חומר נפץ**
is the name of a row in a table of published thermodynamic constants.
**בעלים / הנחיית בעלים** = the owner / an owner directive (binding).

Technical terms: **Z** = scaled distance R/W^(1/3) in m/kg^(1/3), the standard
blast-scaling coordinate. **KB** = Kingery-Bulmash. **QD** = quantity-distance,
the safety siting standard. **HD1.3** = UN hazard division 1.3, a
transport/storage safety classification for materials that *deflagrate* rather
than detonate (subject of the current top task, §6). **JWL**, **AMR**,
**EOS**, **CFL** have their usual meanings.

---

## 3. Environment

Verified on this machine; do not "fix" any of it without the owner asking.

| Piece | State |
|---|---|
| Python | 3.12.10 (Microsoft Store build), on PATH as `python` |
| Deps | `pip install -r requirements.txt`; `pyvista` + `pyvistaqt` optional (3D viewer only) |
| WSL distro | registered under the exact name **`Ubuntu`**, = Ubuntu 22.04 jammy, imported from a rootfs so **root** is the default user |
| Solver | OpenFOAM-9 in `/opt/openfoam9` (apt) + blastFoam **6.2.0** built at `/root/blastfoam` |
| Shim bashrc | `/root/OpenFOAM/OpenFOAM-9/etc/bashrc` - hand-written, sources `/opt/openfoam9/etc/bashrc` then `/root/blastfoam/etc/bashrc` |
| Runs root | `/root/blastlab_runs` |
| git | **not on PATH**: `C:\Users\rotem.ofek\AppData\Local\Microsoft\WinGet\Packages\Git.MinGit_Microsoft.Winget.Source_8wekyb3d8bbwe\cmd\git.exe` |
| ffmpeg | on PATH (winget `Gyan.FFmpeg`), needed for animation export |
| Host | i7-14700, 20 physical / 28 logical cores, 128 GB RAM; WSL VM gets ~62 GiB |

**The four hard-coded WSL constraints** (`blastlab/solvers/foam/env.py`, top of
file): the distro name `Ubuntu`, the jammy release (the `openfoam9` deb exists
only for jammy), the shim bashrc path, and the `/root` run paths. Each looks
arbitrary and each is load-bearing - the "obvious" alternative (Store Ubuntu,
24.04, a normal user) silently breaks the app.

Probe the install:

```powershell
wsl -d Ubuntu -e bash -lc "source /root/OpenFOAM/OpenFOAM-9/etc/bashrc && command -v blastFoam blockMesh setRefinedFields topoSet subsetMesh refineMesh postProcess"
```

If the WSL side is ever broken, re-run the idempotent installer:
`powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\blastlab-wsl\setup-blastfoam.ps1"`.

---

## 4. Running it

```
python -m blastlab                  # the GUI (PySide6). --qt is a no-op alias
python -m blastlab --case a.json    # open a case at startup
python -m blastlab --tk             # the Tkinter GUI - the permanent way back
python -m blastlab --cli 2d [--solver blastfoam]   # prompt workflow
blastlab_qt.bat                     # double-clickable launcher, forwards args
python -m blastlab --clean-foam-runs [--keep-gb N] [--older-than DAYS]
python -m blastlab --load-foam-run DIR             # post-mortem a finished run
```

The **solver mode** (native | blastFoam) is one app-wide switch in the sidebar;
every tab re-lays itself out for the chosen mode and hides - never greys - the
controls that do not apply. Hidden values stay in the form but are not written
to the case.

Headless scripts must call `env.hardware(probe=True)` (or
`env.prime_from_settings()`) themselves: the hardware probe is process-local,
and without it the cell cap falls back to the conservative "assumed 4 GB WSL
VM" and refuses perfectly runnable cases.

---

## 5. Layout

```
blastlab/
  core/      constants, EOS, HLL Riemann solvers, BC/obstacle fluxes, grids,
             profile save/load/remap, Case dataclasses + validation, settings,
             solver mode, chain validation, refinement bookkeeping
  solvers/   solve_1d/2d/3d(case, hooks) drivers; hooks.py decouples the
             console/GUI from the loop; worker.py is the GUI worker thread and
             its tagged-tuple queue; jobs.py is one run stage
    foam/    the blastFoam backend: env.py (WSL discovery, paths, hardware
             plan), writer.py (OpenFOAM case files), runner.py + runloop.py
             (drive the solve, live sampling, resume), reader.py (ingest),
             postmortem.py, materials.py (EOS table), export_vtk.py
  output/    gauge TSVs, matplotlib figure builders, animation export, CLI
             live view. Every FILE export goes through here.
  gui/       Tkinter app - the permanent way back (§9), not deprecated
  ui/        PySide6 app - THE GUI. Nothing here imports VTK.
  viz3d/     3D viewer: viewer.py (the only pyvista module, child process),
             process.py + protocol.py (pipe + shared-memory frame ring),
             sampling/feed/geometry (pure numpy, solver side)
  cli.py     the historical interactive prompts
  tests/     verification suites + byte-level regression harness
BlastFoam_Basic_Info/   the learning material (Hebrew): the official guide PDF
                        + blastfoam_toolkit/ (guide, JWL tables, cheatsheet,
                        scripts, templates)
docs/        00-INDEX.md (the map) · SCOPE.md (what this project is)
  verification/   physics-anchors · blastfoam-claims (the audit) ·
                  solver-options-review (the code against the guide)
  history/        qa-nights · ui-migration (and the standing Tk decision)
  heavy-runs.md   the R1-R9 catalogue + unattended-run ground rules
  archive/        the 15 pre-2026-09-21 Hebrew originals, unchanged
```

**Every markdown file is capped at 1000 lines** (owner directive, 2026-09-21).
This file's own cap of 500 is separate and tighter, because it loads every session.

Key architectural facts: the **GUI process never imports VTK** (pinned by
`test_ui_no_vtk_in_main.py`) and never imports `matplotlib.pyplot` (pinned by
`test_ui_no_mpl_pyplot.py`). The 3D viewer runs in its own Qt process; frames
reach it through a two-slot shared-memory ring, latest-wins, so a slow viewer
can never block the solve. On-screen plots are pyqtgraph; every exported figure
is still matplotlib via `output/plots.py`.

---

## 6. Working conventions

- **`TODO.md` is the single work-management file.** Everything open lives
  there, ordered P0 -> P4, with one exception: **`HD1` sits above P0** - an
  owner directive from 20.09 to model the structural effect of an HD1.3
  (deflagrating, non-detonating) material. `DONE.md` is the completed record
  and is what code comments citing `B23`, `G7`, `N7`, `W1` refer to; do not
  delete its index. Long-form records live under `docs/` - see §5 and
  `docs/00-INDEX.md`. **Both filenames are load-bearing**: 15 code comments
  cite `TODO.md <id>` / `DONE.md <id>` by name.
- **Beware one identifier collision:** the solver-options review numbers its own
  findings `B0`/`B1`/`B2` and `N1`-`N4`, which clash with `DONE.md` §5 where
  `B1`/`B2` are different bugs entirely. Always write "solver review B0".
- **Cite the stable ID** (`T48`, `N5-7`, `P1-6`, `HD1-1`) in commits and
  discussion. Commit style is `area: what changed` -
  e.g. `foam: write the exact end time, so the chain hand-off is the time asked for`.
- **Branches.** `master` is the trunk; work happens on a topic branch
  (`reverify`, `n5-parallel-and-handoff`, `p1-6-lohner-default`).
- **You can commit, but never push.** There are no push credentials on this
  machine and an HTTPS push hangs silently instead of failing.
- **Measurement discipline, learned the hard way:**
  - **Never measure peak alone.** Every comparison records peak,
    positive-phase impulse *and* arrival time. A 3.7 % impulse shift once
    passed every peak-only anchor in this suite.
  - **Pre-register the decision rule, with its numeric threshold, before the
    run that will be judged by it.** This repo was burned once by arguing
    after the numbers came in.
  - Long runs: `python -u`, no timeout, in the background.
- **Do not contact Synthetik or the upstream blastFoam project**, or report
  findings to anyone outside this repo. Explicit owner decision
  (`REVERIFY_PROMPT.md`). Local analysis only.

### Tests - the gates

```
cd blastlab/tests
python test_regression.py        # reruns baseline cases, byte-compares output
python test_foam_writer.py       # OpenFOAM case generation (no WSL needed)
python test_case_validate.py     # case validation rules
python test_blast2d.py           # 2D physics suite
python test_blast3d.py           # 3D physics suite (T1-T10)
python test_foam_env.py          # finds WSL and blastFoam
python -u test_foam_1d_vs_native.py   # real solve, WSL
python -u test_foam_kb_anchor.py      # Kingery-Bulmash accuracy anchor, WSL
```

Naming: `test_*.py` are fast and safe to run anytime; **`_e2e_*.py` do real
solves and open real windows**; `_qa_*.py` are the big interactive harnesses
(`_qa_ui_harness.py`, 63 Qt scenarios, is the primary one). Qt suites create
their own `QApplication` on the offscreen platform.

`test_regression.py` must be green byte-for-byte before you trust any other
measurement.

---

## 7. Physics notes that change how you read the code

- **Afterburn.** A pure JWL detonation carries only the explosive's own
  anaerobic energy, which lands a free-air 1 kg TNT anchor ~13 % below
  Kingery-Bulmash. `afterburn = miller` adds the energy from products burning
  with atmospheric oxygen and brings the anchor to 1.02-1.20 KB at Z = 1-4.
  **Only the TNT row is calibrated against data**; the others scale by oxygen
  balance and are ordered estimates. Refit only after a change to what the
  charge deposits or to `FOAM_EXP_CELLS`, never before, or it gets calibrated
  twice. See the long comment in `solvers/foam/materials.py`.
- **Activation model.** The native solvers detonate the whole charge at t = 0;
  blastFoam's default `linear` burns it at the detonation velocity, so
  near-field arrival times differ by tens of per cent at 1-2 charge radii and
  converge by a few metres. Expected, not a bug.
- **Pressure is coloured logarithmically by default** in the 3D viewer: a
  blast spans four decades in one frame, and on a linear bar the whole shocked
  field collapses into the bottom fraction of a per cent.
- **Displayed impulse is net overpressure impulse** over the whole record,
  negative phase included - not the positive-phase impulse of KB tables, so it
  reads systematically low against published data. Intentional, documented.
- **AMR runs are serial** in this version: `reconstructPar` cannot follow a
  changing mesh. `Lohner` is the default error estimator (`densityGradient`
  starved the axis).
- **Memory models.** `core/constants.py` carries a measured ~2700 B/cell for
  blastFoam inside WSL and an analytic per-cell model for the native solvers,
  because a native run that does not fit raises `MemoryError` and takes the
  window with it. `core/hardware.py` turns them into cell caps.

---

## 8. Traps - each one has already cost a day

**8.1 Never route a file's content through PowerShell strings.**
Windows PowerShell 5.1 reads BOM-less UTF-8 as ANSI, so
`Get-Content -Raw | -replace | Set-Content` mojibakes any file with a single
non-ASCII character - it corrupted `TODO.md` (committed, then recovered) and
later mojibaked the ellipses and box-drawing characters in
`ui/run_browser.py`. Use Read/Edit/Write for every change, even a one-liner.
PowerShell may still list, move and hash files. Damage hunt: `rg 'ג€|ג”'`.

**And a second PowerShell quoting trap, on the way out:** passing a string
containing `"` to a native exe splits it into several arguments. A commit message
with an embedded quote reaches `git` as three broken pathspecs. Write the message
to a file and use `git commit -F`.

**8.2 Any code path that builds the GUI can delete the run corpus.**
blastlab's automatic cleanup fires at startup - including from
`tests/_e2e_gui_*.py` and the QA harnesses - and it does not ask. It once took
`/root/blastlab_runs` from 56 GB / 40 runs to 12 GB / 6 runs in seconds,
destroying the crashed run that was the entire subject of that night's
investigation. Fixed in two layers on 2026-09-17 (`core/settings.load()`
returns `auto_cleanup=False` for a missing or corrupt file;
`ui/testing.private_settings()` now actually writes the flag). Still, before a
session that matters: `env.auto_cleanup(settings.load())` should return
`(0, 0)`, and copy any run you care about out of `/root/blastlab_runs`.

**8.3 WSL can be torn down under a running solve.** On 2026-09-16 a 13-rank 3D
run died 11 minutes in because WSL terminated the distro - "Init has exited",
ext4 unmount, `EIO` everywhere. Not the solver, not disk, not RAM. Suspected
cause: corporate IT group-policy agents (BigFix, gytpolClient) 43 s earlier.
`W3` (runner/runloop/backend + `test_foam_wsl_resume.py`) now detects the EIO
signature and resumes from the last write, max 3 times per run. If a run "just
stopped" with `Input/output error`, check the Hyper-V-VmSwitch event log and
`dmesg` before blaming the case.

**8.4 `.wslconfig` is a loaded gun.** An out-of-range value makes WSL refuse to
create the VM at all, with no warning (`vmIdleTimeout=-1` cost a full day, and
took git down with it back when git lived only inside WSL). Also never cap RAM
there: `env.detect_ram_gb` derives the cell cap from the VM's memory, so a cap
silently shrinks the largest case the app will allow.

**8.5 Disk.** The run corpus once reached 374 GB and filled C:, and the
`ext4.vhdx` is **not sparse** - deleting runs inside WSL does not return the
space. Reclaim with `wsl --shutdown` then
`wsl --manage Ubuntu --set-sparse true`. **Never touch `~\Desktop`** - about
930 GB of thesis data.

**8.6 Before any WSL run, confirm the VM is free:**
`wsl -d Ubuntu -- pgrep -a blastFoam` must come back empty. A foreign solver
makes memory-sensitive tests fail falsely.

**8.7 GUI bugs: measure with the real component on a real platform.**
Stand-ins and reasoning from the API docs have been wrong every single time -
the 3D-preview jump took four reports and three confident wrong explanations,
each from a reproduction missing something the real app has. The real viewer
child does start here (it needs `if __name__ == '__main__'`, it uses
multiprocessing), `QT_QPA_PLATFORM` must be **unset** because
`QWindow.fromWinId` returns `None` offscreen, and Win32 through ctypes
(`GetWindowRect`, `GetParent`, `IsWindowVisible`) is the ground truth - not
Qt's own `geometry()`, which was the broken thing. "It ends up in the right
place" is not the bar; measure the longest unbroken stretch during which a
visible widget is somewhere wrong.

---

## 9. Do not touch

- **`blastlab/gui/` (Tkinter) and `customtkinter` stay in the tree forever**,
  behind `python -m blastlab --tk`. Owner decision, 2026-09-18, with no
  condition and no date: Qt is the main GUI, Tk is the way back. Never delete
  them and **never describe them as deprecated, retired, "kept for one
  release", or scheduled for removal** - in code, README, TODO or any
  user-facing string. The wording is what deletes code: an earlier "kept for
  one release" would have made a later session *right* to remove it. Their 9
  `test_gui_*` suites and `_qa_gui_harness.py` get run whenever a change
  touches `blastlab/gui/` or the shared neutral modules (`core/`, `solvers/`,
  `output/`) - a fallback nobody runs is not a fallback.
- **The regression fixtures**: `blastlab/tests/baseline/`, `foam_fixtures/`,
  `foam_golden/`. They are tracked on purpose and pinned byte-for-byte.
  `.gitignore` deliberately does not match them.
- **`DONE.md` §7, "verified correct - do not fix"**, and the identifier index
  in §5. Code comments cite them.
- **Solver defaults and committed tests** - do not change them to make
  something pass.
- `logo.gif` is a GUI asset, not run output.
