> **Academic CFD — blast-wave gas dynamics, Technion.** This project computes a
> pressure field in air and the structural load it produces, for blast-resistant
> design and explosive-safety siting (UFC 3-340-02, Kingery-Bulmash).
> Energetic materials enter only as a published equation of state. Scope: [docs/SCOPE.md](../../docs/SCOPE.md)

# P1-14 — the material table against its primary source

Moved verbatim out of [TODO.md](../../TODO.md) `P1-14` on 2026-10-11 (1000-line cap). The
decision list, with the owner's gates on RDX and ANFO, stays in `TODO.md`.

**Source found and read, 2026-09-25:** Dobratz & Crawford, *LLNL Explosives Handbook*,
UCRL-52997 (1985), **Table 8-7**, pp. 8-22 / 8-23. The PDF is at
`https://archive.org/download/LLNLExplosivesHandbook/LLNL%20Explosives%20Handbook.pdf`
(PDF pages 229-230). Values were read off the page **images**, not the OCR text layer.
Units there: ρ0 g/cm³, P and A/B/C Mbar, D cm/µs, E0 Mbar·cm³/cm³ (= 100 GPa, per
unit volume, so e0 [J/kg] = E0 / ρ0). Footnote b = "estimated quantities".

| Row | Field | `core/materials.py` | LLNL Table 8-7 | Gap |
|---|---|---|---|---|
| TNT | all 9 | - | 1.630 / 0.210 / 0.693 / 0.07 / 3.712 / 0.03231 / 4.15 / 0.95 / 0.30 | **matches** |
| C4 | e0 | 5.56e6 | E0 0.090 → 9.0e9 / 1601 = **5.62e6** | -1.1 % |
| C4 | other 8 | - | 1.601 / 0.280 / 0.8193 / 6.0977 / 0.1295 / 4.5 / 1.4 / 0.25 | matches |
| HMX | ρ0, D | 1890, 9100 | 1.891, 0.911 | -0.05 %, -0.1 % |
| HMX | e0 | 5.50e6 | E0 0.1050 → 1.05e10 / 1891 = **5.553e6** | -1.0 % |
| HMX | Pcj | 3.9e10 | 0.420ᵇ (estimated) → 4.2e10 | -7 % |
| HMX | A, B, R1, R2, ω | - | 7.783 / 0.07071 / 4.20 / 1.00 / 0.30 | matches |
| PETN (ρ0 1.770) | D | 8400 | 0.830 → **8300** | +1.2 % |
| PETN | e0 | 5.81e6 | E0 0.1010 → 1.01e10 / 1770 = **5.706e6** | +1.8 % |
| PETN | Pcj | 3.1e10 | 0.335 → 3.35e10 | -7 % |
| PETN | A, B, R1, R2, ω | - | 6.170 / 0.16926 / 4.40 / 1.20 / 0.25 | matches (B rounded) |
| **RDX** | all | *(removed 2026-09-26)* | **not in Table 8-7** | removed, see 2 |
| **ANFO** | all | A 4.95e10, B 1.89e9, R1 3.90 ... | **not in Table 8-7** | unsourced |
