"""Per-rank field reads shared by the blastFoam backend and its run loop.

`rd_scalar` and the `part_counts` it needs, moved verbatim from
`backend.py` (docs/ARCHITECTURE_REVIEW.md section 5, Phase 9) so that
`runloop.read_fo_fields` no longer imports `backend`: the dependency now
runs one way, backend -> runloop -> common. `backend` re-exports both
names, so `backend.rd_scalar` and `backend.part_counts` are unchanged.
"""

import os

import numpy as np

from . import reader


def part_counts(spec, dpath):
    """Cells per part of a decomposed time, learned from each part's own
    `C` (memoised per time: every field read needs the same numbers, and
    a rank whose field happens to be `uniform` cannot report its own
    count). None for an ordinary single-directory time."""
    if not isinstance(dpath, (list, tuple)):
        return None
    key = tuple(dpath)
    memo = getattr(spec, '_part_n', None)
    if memo is None:
        memo = spec._part_n = {}
    if key not in memo:
        memo[key] = [len(reader.read_vector(os.path.join(d, 'C'), None))
                     for d in dpath]
    return memo[key]


def rd_scalar(spec, dpath, field, n_cells):
    """One scalar field of a time, whole or concatenated across ranks."""
    if isinstance(dpath, (list, tuple)):
        return np.concatenate([
            reader.read_scalar(os.path.join(d, field), k)
            for d, k in zip(dpath, part_counts(spec, dpath))])
    return reader.read_scalar(os.path.join(dpath, field), n_cells)
