"""blastFoam (OpenFOAM-9, WSL) solver backend.

Writes a real blastFoam case from a blastlab Case, runs it inside WSL,
streams progress/frames through the standard RunHooks seam, and returns
a Result with the exact same shapes as the native numpy solvers.
"""
