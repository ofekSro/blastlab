"""Toolkit-free orchestration over `core`, `models`, `solvers` and
`output`: the pre-flight validation of a case (`validation`) and of a
remap chain (`chain`). docs/ARCHITECTURE_REVIEW.md section 4, Phase 3.

Kept empty on purpose: importing the package imports no submodule, so
`core/case.py` and `core/chain.py` can re-export from here without an
import cycle."""
