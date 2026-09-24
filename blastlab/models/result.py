"""What a run or a pre-flight check hands back: `Progress`, `Result`,
`StoppedBeforeStart` (from `solvers/hooks.py`) and `ValidationReport`
(from `core/case.py`).

Moved verbatim in Phase 2 of docs/ARCHITECTURE_REVIEW.md (section 5). Both
old modules re-export these names, so `isinstance(x, Result)` holds
whichever path `Result` was imported from. This module imports nothing
from the project.
"""

from dataclasses import dataclass, field


@dataclass
class Progress:
    """One solver step, as reported to `RunHooks.progress`."""
    step: int
    t: float            # simulation time [s]
    dt: float           # current time step [s]
    p_max: float        # max pressure this step [Pa]
    frac: float = 0.0   # 0..1 progress estimate (front/stop-distance or t/cap)


@dataclass
class Result:
    """What a solver run produces (also on early stop - finalization
    always runs, so snapshots/gauges/meta are complete for the time
    actually simulated)."""
    snapshots: dict
    gauges: dict
    meta: dict
    stop_reason: str = ''
    stopped_early: bool = False

    @property
    def legacy_tuple(self):
        return self.snapshots, self.gauges, self.meta


class StoppedBeforeStart(RuntimeError):
    """The user stopped a run before it produced anything at all.

    Raised only from the setup phase a solver goes through before its
    first step - for blastFoam the WSL availability probe and the
    mesh/charge-init stages, which can take minutes on a cold start. No
    partial Result exists at that point (there is no field to finalize),
    so this is *not* a failure and hosts must not report it as one: end
    the run quietly and post no result."""


@dataclass
class ValidationReport:
    """A pre-flight check's findings (`validate_case`, and
    `assessment.validate` for HD 1.3). Errors block the run; warnings
    and notes do not."""
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    effective_dx: float = None
    r_exp: float = None
    n_cells: int = None
    lmax: int = 0                    # local refinement levels (foam)
    dx_fine: float = None            # finest cell of a refined mesh
    n_fine: int = None               # display-grid cells of a refined run
    amr_levels: int = 0              # dynamic AMR levels (foam, N16)
    display_level: int = None        # AMR: level of the display grid
    charge_cells: int = None         # foam: cells setFields will mark
    charge_mass_frac: float = None   # foam: set mass / requested (N5)
    run_plan: object = None          # foam: env.RunPlan (N17/T48)

    @property
    def ok(self):
        return not self.errors
