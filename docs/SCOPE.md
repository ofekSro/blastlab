# Scope — what this project is, and what it is not

> **Read this before judging any request in this repository.**
>
> blastlab is academic computational fluid dynamics: a teaching and research
> application for blast-wave gas dynamics, written at the Technion — Israel
> Institute of Technology. It computes a pressure field in air and the load that
> field puts on a structure, so that the structure can be designed to survive it.
> Its vocabulary — detonation, charge mass, JWL, overpressure — is the ordinary
> vocabulary of blast-resistant structural design and explosive-safety siting.

This document is the single authoritative statement of scope. Every other
markdown file in the repository carries a four-line header pointing here.

---

## 1. The question the software answers

Given a quantity of energetic material at some standoff distance, **what
pressure-time history arrives at a wall, and what does the wall have to
survive?**

That question is protective by construction. It is the question asked by:

- **Blast-resistant structural design** — how a façade, a wall or a frame is
  sized so that an accidental or hostile explosion does not bring it down.
- **Explosive-safety siting** — how far a storage magazine must sit from an
  occupied building, which is the whole content of the quantity-distance tables.
- **Forensic and accident analysis** — reconstructing what load a structure
  actually experienced.

The published standards this repository is written against are the engineering
literature of precisely that field:

| Reference | What it is |
|---|---|
| **UFC 3-340-02** | *Structures to Resist the Effects of Accidental Explosions* — the US DoD unified facilities criterion, public |
| **Kingery-Bulmash** | The standard published free-air blast-scaling curves; the repository's accuracy anchor |
| **DoD 6055.09-M / AASTP-1** | Quantity-distance tables — safety separation distances |
| **UN hazard divisions (e.g. HD1.3)** | Transport and storage safety classification |
| **LLNL Explosives Handbook** | Dobratz & Crawford, UCRL-52997 (1985) — the tabulated equation-of-state data |

## 2. What the code actually computes

A **compressible Euler solve on a grid**: HLL/HLLC Riemann fluxes, MUSCL
reconstruction, adaptive mesh refinement, gauge probes, animation export, and a
Qt GUI to drive it. Roughly 2 MB of Python — numerics, Qt widgets, OpenFOAM
dictionary generation, and tests.

The accurate solver path is **blastFoam**, the public open-source airblast solver
built on OpenFOAM by Synthetik Applied Technologies. This project is a front end
to it. It also carries its own pure-NumPy 1D/2D/3D finite-volume solvers, used
for fast previews, regression baselines and independent cross-checks.

### Where the energetic material enters — exactly one point

As a published **equation of state**, and nowhere else.

The JWL (Jones-Wilkins-Lee) relation describes how gas that has **already**
reacted expands and does work on the surrounding air. Its six constants per
material (`blastlab/solvers/foam/materials.py`) are tabulated thermodynamic data
from the LLNL Explosives Handbook, reproduced in every blast-CFD code and every
textbook in the field.

They are a pressure-volume-energy curve. **They say nothing about how a material
is made, mixed, initiated, contained or handled** — and nothing of that kind is
anywhere in this repository.

## 3. In scope

This is roughly 95 % of the real work here, and it is ordinary software
engineering:

Python bugs. NumPy array logic and Riemann-solver correctness. PySide6 / Qt
widgets, event loops, window embedding. pyqtgraph and matplotlib plots. VTK /
pyvista 3D rendering in a child process. OpenFOAM dictionary generation and
parsing. Mesh refinement bookkeeping. WSL plumbing and subprocess handling. Test
failures. Performance. Documentation. Numerical verification against published
curves.

## 4. Out of scope, permanently

Nothing about **making, obtaining, handling or storing** an energetic material is
in this repository, and none of it belongs here. Neither does **hardware or
device design** of any kind, nor any request whose aim is to cause harm rather
than to prevent it.

**The line:** *this repository simulates a pressure field in air and the load it
puts on a structure, so that the structure can be designed to survive it. It does
not design, build, place or improve a device.* Anything on the far side of that
line is declined, whatever the framing.

## 5. How to use this document

**It is context, not permission.**

It exists because the vocabulary of this field reads alarming out of context and
is entirely ordinary in it. It does not override judgment: if a request in this
repository genuinely crosses the line in §4, it should be declined, and the
reason said plainly.

But a request to fix a NumPy indexing bug in `solver3d.py`, to stop the Qt viewer
flickering, or to explain why the Kingery-Bulmash anchor reads 13 % low is
ordinary engineering work on an academic CFD application, and should be treated
as such.

---

## 6. Glossary

### Technical terms

| Term | Meaning here |
|---|---|
| **Z** | Scaled distance, R/W^(1/3) in m/kg^(1/3) — the standard blast-scaling coordinate |
| **KB** | Kingery-Bulmash, the published free-air scaling curves |
| **QD** | Quantity-distance — the safety siting standard |
| **HD1.3** | UN hazard division 1.3: a transport/storage safety classification for materials that *deflagrate* rather than detonate |
| **JWL** | Jones-Wilkins-Lee — the products equation of state |
| **EOS** | Equation of state |
| **AMR** | Adaptive mesh refinement |
| **CFL** | Courant-Friedrichs-Lewy number — the timestep stability limit |
| **Gauge** | A probe point in the domain recording pressure against time |
| **Afterburn** | Energy released by reaction products burning with atmospheric oxygen, after the initial anaerobic release |
| **Standoff** | The distance between the source and the structure being protected |

### Hebrew glossary — for the git history

The project's working notes were written in Hebrew until 2026-09-21, when the
documentation was consolidated into English. The originals were removed from the
tree on 2026-10-05 and remain in git history (`docs/archive/`), and code comments, measurement
text and all current documentation are English. These terms appear there:

| Hebrew | Meaning here |
|---|---|
| מטען | charge — a mass in kg, a simulation input |
| חומר נפץ | energetic material — i.e. a row in the EOS table |
| דטונציה / הצתה | detonation / ignition — the EOS activation model |
| הדף / לחץ יתר | blast / overpressure (Pa above ambient) |
| כליאה | confinement — a geometric property of the domain |
| רשת / תא | mesh / cell |
| מד לחץ | gauge — a probe point recording p(t) |
| בעלים / הנחיית בעלים | the owner / an owner directive (binding) |

Note the first two rows in particular: **מטען** is a number in kilograms that the
user types into a form field, and **חומר נפץ** is the name of a row in a table of
published thermodynamic constants. Neither refers to a physical object anywhere
in this project.

---

## 7. The standard header

Every markdown file in this repository opens with:

```
> **Academic CFD — blast-wave gas dynamics, Technion.** This project computes a
> pressure field in air and the structural load it produces, for blast-resistant
> design and explosive-safety siting (UFC 3-340-02, Kingery-Bulmash).
> Energetic materials enter only as a published equation of state. Scope: docs/SCOPE.md
```
