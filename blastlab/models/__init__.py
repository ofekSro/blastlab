"""Project state that imports only `core`: the case dataclasses and their
JSON (`case`, `hd13_case`) and what a run or a check hands back
(`result`). docs/ARCHITECTURE_REVIEW.md section 4, Phase 2.

Kept empty on purpose: importing the package imports no submodule, so
`core/case.py` and `solvers/hooks.py` can re-export from here without an
import cycle."""
