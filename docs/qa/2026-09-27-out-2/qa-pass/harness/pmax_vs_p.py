"""Is the exported pMax (labelled "Peak overpr." on the card) a peak
OVERpressure or a peak ABSOLUTE pressure? Compare, cell by cell on the
obstacle surface, the final pMax with the running max of the sampled p
(absolute, Pa). Plain-text parse of the ASCII legacy VTK files.
Run:  python pmax_vs_p.py <MODEL folder>
"""
import json
import os
import sys

import numpy as np


def cell_array(path, name):
    toks = open(path, encoding='ascii', errors='replace').read().split()
    i = toks.index('CELL_DATA')
    n = int(toks[i + 1])
    j = toks.index(name, i)
    # "<name> <ncomp> <ntuples> <type>" (FIELD) or SCALARS name type / LOOKUP
    if toks[j - 1] == 'SCALARS':
        k = toks.index('LOOKUP_TABLE', j) + 2
        return np.array(toks[k:k + n], float)
    ncomp, ntup = int(toks[j + 1]), int(toks[j + 2])
    return np.array(toks[j + 4:j + 4 + ncomp * ntup], float)


model = sys.argv[1]
for fam in (os.path.join('obstacles'), os.path.join('sections', 'slice_x_0.20')):
    base = os.path.join(model, 'vtk', fam)
    sp = json.load(open(os.path.join(base, 'p.vtk.series')))['files']
    sm = json.load(open(os.path.join(base, 'pMax.vtk.series')))['files']
    runmax = None
    for e in sp:
        a = cell_array(os.path.join(base, *e['name'].split('/')), 'p')
        runmax = a if runmax is None else np.maximum(runmax, a)
    last = sm[-1]
    pmax = cell_array(os.path.join(base, *last['name'].split('/')), 'pMax')
    d = pmax - runmax
    print(f'{fam}: {len(pmax)} cells; final pMax range '
          f'{pmax.min():.0f} .. {pmax.max():.4g} Pa; running max of sampled p '
          f'{runmax.min():.0f} .. {runmax.max():.4g} Pa')
    print(f'   pMax - max(sampled p): min {d.min():.0f} Pa, median '
          f'{np.median(d):.0f} Pa; cells with pMax < max(sampled p): '
          f'{int((d < -1).sum())}; cells with pMax < max(sampled p) - 101325: '
          f'{int((d < -101325 - 1).sum())}')
    print(f'   quietest cell: pMax {pmax[np.argmin(runmax)]:.0f} Pa vs sampled '
          f'max p {runmax.min():.0f} Pa (ambient 101325 Pa)')
