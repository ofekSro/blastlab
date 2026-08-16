"""blastFoam backend entry points (phased bring-up).

Signatures mirror the native solvers exactly:
    solve_1d_foam(case, hooks=None) -> Result
Dims are switched on as their phase lands; `IMPLEMENTED` gates the
pre-flight validation so a not-yet-available dim errors while editing
the form instead of at launch.
"""

#: dims with a working blastFoam backend (grows per phase)
IMPLEMENTED = frozenset()


def _todo(dim):
    raise NotImplementedError(
        f"The blastFoam backend for {dim}D cases is not implemented yet "
        f"- select the 'native' solver for this case.")


def solve_1d_foam(case, hooks=None):
    _todo(1)


def solve_2d_foam(case, hooks=None):
    _todo(2)


def solve_3d_foam(case, hooks=None):
    _todo(3)
