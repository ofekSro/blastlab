"""pvpython, headless: open one volume series and one surface series the
way ParaView's File > Open does (the .vtk.series reader), step through the
time steps and report the arrays and value ranges.
Run:  pvpython pv_load.py <MODEL folder>
"""
import os
import sys

from paraview.simple import OpenDataFile, UpdatePipeline

model = sys.argv[1]
vtk = os.path.join(model, 'vtk')
targets = [os.path.join(vtk, 'volumes', 'volumes.vtk.series'),
           os.path.join(vtk, 'obstacles', 'pMax.vtk.series')]
secs = os.path.join(vtk, 'sections')
if os.path.isdir(secs):
    for plane in sorted(os.listdir(secs)):
        s = os.path.join(secs, plane, 'p.vtk.series')
        if os.path.isfile(s):
            targets.append(s)
for t in targets:
    r = OpenDataFile(t)
    if r is None:
        print('NO READER for', t)
        continue
    times = list(r.TimestepValues) if hasattr(r, 'TimestepValues') else []
    print(f'{os.path.relpath(t, vtk)}: reader {r.GetXMLName()}, '
          f'{len(times)} time steps, {times[:2]} .. {times[-1:]}')
    for tt in ([times[0], times[-1]] if times else [None]):
        UpdatePipeline(time=tt, proxy=r)
        di = r.GetDataInformation()
        cd = r.CellData
        arrs = {cd.GetArray(i).Name: tuple(round(v, 6) for v in
                                           cd.GetArray(i).GetRange())
                for i in range(cd.GetNumberOfArrays())}
        print(f'   t={tt}: {di.GetNumberOfCells()} cells, '
              f'{di.GetNumberOfPoints()} points, cell arrays {arrs}')
