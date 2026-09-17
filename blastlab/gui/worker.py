"""Compatibility shim: the solver worker moved to `blastlab.solvers.worker`
(PySide6 migration, M0) so both GUI front-ends share it. Remove with the
Tk package."""

from ..solvers.worker import GuiHooks, SolverWorker  # noqa: F401
