"""The blastFoam run directories, for a front-end, without a toolkit.

A thin re-export (docs/ARCHITECTURE_REVIEW.md section 5, Phase 9) of
`solvers/foam/runs.py` (a run's dimension out of its `case.json`) and of
`solvers/foam/postmortem.py` (listing the WSL runs, loading a finished
one), so a GUI reaches the foam runs through the services layer rather
than through the other toolkit's run browser. Every name is the very
same object as at its source.
"""

from ..solvers.foam.postmortem import list_runs, load_run   # noqa: F401
from ..solvers.foam.runs import dims_from_case_json          # noqa: F401
