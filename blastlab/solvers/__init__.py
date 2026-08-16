"""Time-integration drivers: solve_1d / solve_2d / solve_3d operating on
Case objects with pluggable RunHooks (console or GUI).

`get_solver(dim, backend)` resolves the solve callable for a dimension
and a solver backend: 'native' (the built-in numpy solvers) or
'blastfoam' (the OpenFOAM/blastFoam WSL backend in `foam/`). Imports
stay lazy so importing this package never drags in solver modules."""


def get_solver(dim, backend='native'):
    dim = int(dim)
    if dim not in (1, 2, 3):
        raise ValueError(f"Unknown dimension {dim}")
    if backend == 'native':
        if dim == 1:
            from .solver1d import solve_1d
            return solve_1d
        if dim == 2:
            from .solver2d import solve_2d
            return solve_2d
        from .solver3d import solve_3d
        return solve_3d
    if backend == 'blastfoam':
        from .foam import backend as foam
        return {1: foam.solve_1d_foam, 2: foam.solve_2d_foam,
                3: foam.solve_3d_foam}[dim]
    raise ValueError(f"Unknown solver backend '{backend}'")
