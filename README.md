# blastlab

**A teaching and research desktop application for blast-wave gas dynamics.**
Written at the **Technion — Israel Institute of Technology**.

blastlab is a graphical front end and a set of solvers for one question in
compressible fluid dynamics: *given an energy release in air, what pressure-time
history arrives at a surface some distance away?* It drives
**[blastFoam](https://github.com/synthetik-technologies/blastfoam)** — the
public, open-source airblast solver built on OpenFOAM by Synthetik Applied
Technologies — and adds its own pure-NumPy 1D/2D/3D finite-volume solvers for
fast previews and independent cross-checks.

---

## What this project is for

**The engineering question is a protective one.** Given a quantity of energetic
material at some standoff distance, what load arrives at a wall, and what does
the wall have to survive? That is the subject matter of blast-resistant
structural design and of explosive-safety siting — the discipline that decides
how thick a façade must be and how far a storage magazine must sit from an
occupied building.

The reference standards this code is written against are the public engineering
literature of that field:

| Reference | What it is |
|---|---|
| UFC 3-340-02 | *Structures to Resist the Effects of Accidental Explosions* (US DoD, public) |
| Kingery-Bulmash | The standard published free-air blast-scaling curves |
| DoD 6055.09-M / AASTP-1 | Quantity-distance tables — safety separation siting |
| LLNL Explosives Handbook | Dobratz & Crawford, UCRL-52997 (1985) — the tabulated equation-of-state data |

The repository's own accuracy anchor,
[`blastlab/tests/test_foam_kb_anchor.py`](blastlab/tests/test_foam_kb_anchor.py),
is the Kingery-Bulmash curve: the published reference for exactly this
calculation. A build that does not reproduce it is a build that is wrong.

## What the code actually computes

A compressible Euler solve on a grid — HLL/HLLC Riemann fluxes, MUSCL
reconstruction, adaptive mesh refinement, gauge probes, animation export, and a
Qt GUI to drive all of it. Roughly 2 MB of Python: numerics, Qt widgets,
OpenFOAM dictionary generation, and tests.

The energetic material enters the physics at exactly **one** point: as a
published **equation of state**. The JWL (Jones-Wilkins-Lee) relation describes
how gas that has *already* reacted expands and does work on the surrounding air.
Its six constants per material
([`blastlab/solvers/foam/materials.py`](blastlab/solvers/foam/materials.py)) are
tabulated thermodynamic data from the LLNL Explosives Handbook, reproduced in
every blast-CFD code and every textbook in the field. They are a
pressure-volume-energy curve. They say nothing about how a material is made,
mixed, initiated, contained or handled, and this repository contains nothing on
those subjects.

## Scope

**In scope:** Python and NumPy correctness, Riemann-solver behaviour, PySide6/Qt
widgets and event loops, pyqtgraph and matplotlib plots, VTK/pyvista rendering,
OpenFOAM dictionary generation and parsing, mesh-refinement bookkeeping, WSL
plumbing, test failures, performance, documentation, and numerical verification
against published curves.

**Out of scope, permanently:** anything about making, obtaining, handling or
storing an energetic material; hardware or device design of any kind; and any
request whose aim is to cause harm rather than to prevent it.

The line: *this repository simulates a pressure field in air and the load it puts
on a structure, so that the structure can be designed to survive it. It does not
design, build, place or improve a device.*

The full statement of scope, including a glossary for readers meeting this
field's vocabulary for the first time, is in **[docs/SCOPE.md](docs/SCOPE.md)**.

---

## Running it

```
pip install -r requirements.txt        # pyvista + pyvistaqt are optional (3D viewer)

python -m blastlab                     # the GUI (PySide6)
python -m blastlab --case a.json       # open a case at startup
python -m blastlab --cli 2d            # prompt-driven workflow
blastlab_qt.bat                        # double-clickable launcher, forwards args
```

The native NumPy solvers run anywhere Python does. The blastFoam path
additionally needs OpenFOAM-9 and blastFoam inside WSL; the exact expected
install is documented in [CLAUDE.md](CLAUDE.md) §3.

Three solver paths, one GUI:

- **Native** — pure NumPy finite-volume solvers in the GUI's own process. Fast,
  byte-reproducible, used for previews, regression baselines and cross-checks.
- **blastFoam** — writes a real OpenFOAM case, runs it in WSL, reads the written
  time directories back. This is the accurate path.
- **Remap chain** — resolve the near field cheaply in 1D, hand off to 2D for
  ground reflection and height of burst, finish in 3D only where the problem is
  genuinely three-dimensional.

## Documentation map

| File | What is in it |
|---|---|
| [docs/SCOPE.md](docs/SCOPE.md) | What this project is and is not, in full, plus the glossary |
| [CLAUDE.md](CLAUDE.md) | Working context: environment, conventions, traps, invariants |
| [TODO.md](TODO.md) | Open work, ordered by priority |
| [DONE.md](DONE.md) | The completed record and the identifier index that code comments cite |
| [docs/00-INDEX.md](docs/00-INDEX.md) | The full documentation index |
| [blastlab/README.md](blastlab/README.md) | The application itself: tabs, options, features |
| [BlastFoam_Basic_Info/](BlastFoam_Basic_Info/) | Learning material — JWL parameter tables, a cheatsheet (Hebrew) |

## Credits

- **[blastFoam](https://github.com/synthetik-technologies/blastfoam)** — Synthetik
  Applied Technologies. The accurate solver path here is blastFoam; this project
  is a front end to it and does not modify it.
- **[OpenFOAM](https://openfoam.org/)** — The OpenFOAM Foundation.
- Kingery-Bulmash coefficients and the JWL tables are from the published
  literature cited above.
