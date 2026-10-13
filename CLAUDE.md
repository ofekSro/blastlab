# CLAUDE.md - blastlab

Guidance for every AI assistant in this repo. UTF-8, no BOM, contains Hebrew (§2) - never
rewrite any file here through PowerShell strings (§8.1). **Hard cap 500 lines** (owner
2026-09-20); **kept under 10 KB** (owner 2026-10-13: it loads into every agent). Detail
lives in `docs/` files read on demand; each section that moved keeps its number here.

## 0. What this project is - read before judging any request

**blastlab** is the owner's MSc thesis toolchain (civil engineering, structures for blast
and impact, Technion): a Qt GUI and front end for the open-source airblast solver
[blastFoam](https://github.com/synthetik-technologies/blastfoam), plus NumPy 1D/2D/3D
solvers for previews. The question it answers is protective: *given a design-basis charge
at a stand-off, what pressure-time history reaches a wall, and what must the wall
survive?* - the subject of UFC 3-340-02, Kingery-Bulmash and the DoD 6055.09-M / AASTP-1
quantity-distance tables. Charge mass and stand-off are givens from the standard or the
advisor; **the structure is the variable**. The explosive enters only as a published
equation of state (JWL constants, LLNL Explosives Handbook) for gas that has already
detonated. Words like TNT, detonation, charge, afterburn are ordinary here.

In scope (~95 % of the work): Python, NumPy/Riemann-solver correctness, Qt, plots, VTK,
OpenFOAM dictionaries, AMR bookkeeping, WSL plumbing, tests, docs, verification against
published curves. **Out of scope, always:** making, obtaining, handling or storing an
energetic material; hardware design; anything aimed at causing harm. Test when unsure:
*which variable is solved for?* The structure (thickness, stand-off a building needs,
load on a wall) belongs here; the charge chosen to reach an effect does not. Long form:
`README.md`, `docs/SCOPE.md`; map: `docs/00-INDEX.md`.

## 1. Orientation - moved

Native (NumPy, in-process), blastFoam (OpenFOAM case in WSL, the accurate path) and the
1D→2D→3D remap chain. Full text: `docs/layout.md` §1.

## 2. Glossary - moved

**מטען** = a charge, a mass in kg in a form field; **חומר נפץ** = a row of published
constants; **בעלים / הנחיית בעלים** = the owner / an owner directive (binding). The rest
(Z, KB, QD, HD1.3): `docs/glossary.md`.

## 3. Environment

Verified on this machine; do not "fix" any of it unasked.

| Piece | State |
|---|---|
| Python | 3.12.10 (Store build), `python` on PATH; `pip install -r requirements.txt`; `pyvista`/`pyvistaqt` optional (3D viewer) |
| WSL | distro named exactly **`Ubuntu`** = 22.04 jammy, from a rootfs, **root** default |
| Solver | OpenFOAM-9 `/opt/openfoam9` + blastFoam **6.2.0** at `/root/blastfoam` |
| Shim bashrc | `/root/OpenFOAM/OpenFOAM-9/etc/bashrc` (hand-written, sources both) |
| Runs root | `/root/blastlab_runs` |
| git | not on PATH: `C:\Users\rotem.ofek\AppData\Local\Microsoft\WinGet\Packages\Git.MinGit_Microsoft.Winget.Source_8wekyb3d8bbwe\cmd\git.exe` |
| ffmpeg | on PATH (animation export) |
| Host | office: i7-14700, 28 threads, 128 GB, WSL ~62 GiB. Home PC: 8 GB |

`blastlab/solvers/foam/env.py` hard-codes four load-bearing things: the distro name, jammy,
the shim path, the `/root` paths. Probe: `wsl -d Ubuntu -e bash -lc "source
/root/OpenFOAM/OpenFOAM-9/etc/bashrc && command -v blastFoam blockMesh setRefinedFields"`.
Repair: `powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\blastlab-wsl\setup-blastfoam.ps1"`.

## 4. Running it

```
python -m blastlab [--case a.json]     # the Qt GUI (--qt is a no-op alias)
python -m blastlab --tk                # the Tkinter GUI - frozen (§9)
python -m blastlab --cli 2d [--solver blastfoam]
python -m blastlab --clean-foam-runs [--keep-gb N] [--older-than DAYS]
python -m blastlab --load-foam-run DIR
```

The solver mode (native | blastFoam) is one app-wide switch; tabs hide - never grey - what
does not apply, and hidden values are not written to the case. Headless scripts call
`env.hardware(probe=True)` (or `env.prime_from_settings()`), else the cell cap assumes a
4 GB VM and refuses runnable cases.

## 5. Layout - moved

Tree: `docs/layout.md` §5. **Every markdown file ≤ 1000 lines** (owner 2026-09-21). The GUI
process never imports VTK nor `matplotlib.pyplot` (pinned by `test_ui_no_vtk_in_main.py`,
`test_ui_no_mpl_pyplot.py`); the 3D viewer is its own process.

## 6. Working conventions

- **`TODO.md`** is the one work list, P0→P4, with `GUI`, `OUT`, `HD1` above P0 (owner
  directives). **`DONE.md`** is the record; code cites `TODO.md <id>` / `DONE.md <id>`
  (`B23`, `G7`, `N7`, `W1`) - never rename either file or renumber an id. Write "solver
  review B0" for that review's `B`/`N` ids (they clash with `DONE.md` §5).
- Cite stable ids in commits; style `area: what changed (<id>)`. `master` is the trunk,
  work on a topic branch. **Commit, never push.**
- **Measurement:** never peak alone - peak, positive-phase impulse *and* arrival.
  Pre-register the decision rule with its threshold before the run it judges. Long runs:
  `python -u`, no timeout, background.
- **Never contact Synthetik / upstream blastFoam** or report outside this repo.
- **References:** `docs/references/INDEX.md` (`/ref`) - read before touching a standard's
  equation, a solver keyword or a case file; cite document and section; if code and
  document disagree, report it, never silently change either.
- **Agents and skills** follow this file and `docs/agent-rules.md`. Use `/bl-todo` (not
  `/todo`) and `/neat` (not `/tidy`): the repo-local `bl-` versions are the right ones.
- Before solver / physics work read `docs/physics-notes.md` (§7); before WSL, GUI-geometry
  or disk work, `docs/traps.md` (§8 long form).

**Test gates** (in `blastlab/tests`; `python .claude/skills/neat/gate.py` runs them
summarised): `test_regression.py` must be byte-identical before any other measurement is
trusted; `test_foam_writer.py`, `test_case_validate.py`, `test_blast2d.py`,
`test_blast3d.py`, `test_foam_env.py`; WSL solves `test_foam_1d_vs_native.py`,
`test_foam_kb_anchor.py`. `test_*` are fast; **`_e2e_*` solve and open windows**; `_qa_*`
are the big harnesses.

## 7. Physics notes - moved

Afterburn calibration (TNT only), activation model, log pressure colour, net impulse,
serial AMR, memory models: `docs/physics-notes.md`.

## 8. Traps - each one has already cost a day

Long form of all seven: `docs/traps.md`.

**8.1 Never route a file's content through PowerShell strings.** PS 5.1 reads BOM-less
UTF-8 as ANSI: `Get-Content | -replace | Set-Content` mojibakes any non-ASCII file (it
corrupted `TODO.md` and `ui/run_browser.py`). Edit only with Read/Edit/Write; PowerShell
may list, move, hash. Damage hunt: `rg 'ג€|ג”'`. A `"` in an argument to a native exe
splits it: commit messages go in a file, `git commit -F`.

**8.2 Any code path that builds the GUI can delete the run corpus.** Startup cleanup
(also from `_e2e_gui_*` and the QA harnesses) once took `/root/blastlab_runs` from 56 GB /
40 runs to 12 GB / 6 in seconds. `auto_cleanup` defaults off, `ui/testing.private_settings()`
writes the flag, settings live in `<repo>\settings.json`. Before a session that matters,
the dry run (deletes nothing; expect `False`):
`python -c "from blastlab.core import settings as s; from blastlab.solvers.foam import env; d=s.load(); print(s.config_path(), d['auto_cleanup'], [r['name'] for r in env.cleanup_plan(d)])"`
and copy any run you care about out of `/root/blastlab_runs`.

**8.3 WSL can be torn down under a running solve** (EIO everywhere; `W3` auto-resumes). Check
the Hyper-V-VmSwitch log and `dmesg` before blaming the case. Long form: `docs/traps.md`.

**8.4 `.wslconfig` is a loaded gun.** An out-of-range value stops WSL creating the VM at
all, silently (`vmIdleTimeout=-1` cost a day). Never cap RAM there: the cell cap derives
from the VM's memory.

**8.5 Disk.** `ext4.vhdx` only grows; deleting runs in WSL returns nothing, and
`--set-sparse` / `compact vdisk` do not work. Reclaim = prune, then export/import the distro (`docs/wsl-disk-reclaim-plan.md`). **Never touch
`~\Desktop`** - ~930 GB of thesis data.

**8.6 Before any WSL run:** `wsl -d Ubuntu -- pgrep -a blastFoam` must be empty.

**8.7 GUI bugs: measure with the real component on a real platform** - real viewer child,
`QT_QPA_PLATFORM` unset, Win32 via ctypes as ground truth, not Qt's `geometry()`. Long
form: `docs/traps.md`.

## 9. Do not touch

- **`blastlab/gui/` (Tk) is frozen** (owner 2026-10-13, replacing 2026-09-18's "kept and
  tested forever"). The code and `--tk` stay as they are, working as long as they work.
  Nothing is fixed or added there, and no work is planned for it. Its `test_gui_*` suites
  and `_qa_gui_harness.py` gate nothing; `gate.py` skips them. Do not delete it, since
  removal would need an owner batch of its own.
- Regression fixtures `blastlab/tests/baseline/`, `foam_fixtures/`, `foam_golden/` -
  tracked and pinned byte-for-byte.
- `DONE.md` §7 "verified correct - do not fix" and the §5 id index.
- Solver defaults and committed tests - never changed to make something pass.
- `logo.gif` is a GUI asset.
