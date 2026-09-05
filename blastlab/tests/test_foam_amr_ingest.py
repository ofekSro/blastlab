"""Dynamic AMR ingest path (ROADMAP N16, T21) - no WSL.

Fakes the time directories an `adaptiveFvMesh` run writes - each with
its own cell centres `C` and `cellLevel` next to the fields - and drives
`backend.mesh_at`, the `mesh=` decode path (`read_2d`, `to_grid`,
`read_fo_fields`, `PeakImpulse`), the readiness gate with the mesh
files, the torn-file retry, the t = 0 labelList fallback, the AMR mesh
stages and the per-write log line. The static path must be untouched:
a non-AMR spec yields `mesh_at(...) is None` and the old stage list.

Run:  cd blastlab/tests && python test_foam_amr_ingest.py
"""
import os
import shutil
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from blastlab.core import refine                                # noqa: E402
from blastlab.core.case import Case2D, Case3D                    # noqa: E402
from blastlab.core.constants import P_AIR                       # noqa: E402
from blastlab.solvers.foam import backend, reader, runloop, writer  # noqa: E402

FAILS = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAILS.append(name)


class Log:
    def __init__(self):
        self.lines, self.frames = [], []

    def log(self, s):
        self.lines.append(s)

    def frame(self, payload, t, levels=None):
        self.frames.append((payload, t, levels))

    def wants_frame3d(self):
        return False


HEADER = ('FoamFile\n{\n    version     2.0;\n    format      ascii;\n'
          '    class       {cls};\n    object      {obj};\n}}\n')


def field_text(cls, obj, vals=None, uniform=None, vector=False):
    head = HEADER.replace('{cls}', cls).replace('{obj}', obj)
    if uniform is not None:
        return head + f'internalField   uniform {uniform};\n'
    kind = 'vector' if vector else 'scalar'
    body = '\n'.join((f'({v[0]:.10g} {v[1]:.10g} {v[2]:.10g})' if vector
                      else f'{v:.10g}') for v in vals)
    return (head + f'internalField   nonuniform List<{kind}> \n'
            f'{len(vals)}\n(\n{body}\n)\n;\n')


def write_time(root, name, t, C, lv, p, level_field=True,
               label_list=False, torn=False, complete=True):
    """A fake AMR time dir: C + cellLevel (or the t = 0 polyMesh
    labelList) + p / rho / U / T / alpha.expl / pMax / impulse + time."""
    d = os.path.join(root, name)
    os.makedirs(os.path.join(d, 'uniform'), exist_ok=True)
    n = len(C)
    c3 = np.column_stack([C, np.zeros(n)])
    txt = field_text('volVectorField', 'C', c3, vector=True)
    if torn:
        txt = txt[:len(txt) // 2]
    with open(os.path.join(d, 'C'), 'w') as f:
        f.write(txt)
    if level_field:
        with open(os.path.join(d, 'cellLevel'), 'w') as f:
            f.write(field_text('volScalarField', 'cellLevel',
                               np.asarray(lv, float)))
    if label_list:
        os.makedirs(os.path.join(d, 'polyMesh'), exist_ok=True)
        with open(os.path.join(d, 'polyMesh', 'cellLevel'), 'w') as f:
            f.write(HEADER.replace('{cls}', 'labelList')
                    .replace('{obj}', 'cellLevel')
                    + f'\n{n}\n(\n' + '\n'.join(str(int(v)) for v in lv)
                    + '\n)\n')
    fields = {'p': field_text('volScalarField', 'p', p),
              'pMax': field_text('volScalarField', 'pMax', p + 1.0),
              'impulse': field_text('volScalarField', 'impulse',
                                    np.full(n, 2.0)),
              'rho': field_text('volScalarField', 'rho', uniform='1.225'),
              'T': field_text('volScalarField', 'T', uniform='288'),
              'alpha.expl': field_text('volScalarField', 'alpha.expl',
                                       uniform='0'),
              'U': field_text('volVectorField', 'U', uniform='(0 0 0)')}
    for k, v in fields.items():
        if not complete and k == 'p':
            continue
        with open(os.path.join(d, k), 'w') as f:
            f.write(v)
    with open(os.path.join(d, 'uniform', 'time'), 'w') as f:
        f.write(f'value           {t:g};\ndeltaT          1e-06;\n')
    return d


def block_centres(x0, y0, size, n):
    cx = x0 + (np.arange(n) + 0.5) * size
    cy = y0 + (np.arange(n) + 0.5) * size
    X, Y = np.meshgrid(cx, cy, indexing='ij')
    return np.column_stack([X.ravel(), Y.ravel()])


def amr_spec(root):
    """A 1 x 1 m planar case on a 0.5 m base with 2 AMR levels: the
    display grid is the finest level (8 x 8 at 0.125 m)."""
    case = Case2D(geometry='planar', Lx=1.0, Ly=1.0, cell_size_m=0.5,
                  charge=100.0, center=(0.5, 0.5), solver='blastfoam',
                  amr_levels=2, record_frames=10)
    spec = writer.render_case(case)
    spec.files = None
    spec.case_unc, spec.case_posix = root, '/tmp/x'
    return case, spec


def test_stages_and_static_inertness():
    print("\nmesh stages + static inertness")
    root = tempfile.mkdtemp(prefix='blastlab_amr_')
    try:
        _case, spec = amr_spec(root)
        check('AMR spec: amr 2, display 2, 8x8 display grid, mesh_fields',
              spec.amr == 2 and spec.display_level == 2 and (spec.nx, spec.ny) == (8, 8)
              and spec.mesh_fields == ('C', 'cellLevel'), f'{spec.amr} {spec.nx}')
        cmds = [c for _l, c in backend._mesh_stages(spec, Log())]
        check('AMR stages: setRefinedFields WITHOUT -noRefine, no refineMesh, '
              'cell centres written, serial',
              'setRefinedFields' in cmds and not any('noRefine' in c for c in cmds)
              and not any('refineMesh' in c or 'topoSetDict.refine' in c for c in cmds)
              and any('writeCellCentres' in c for c in cmds)
              and not any('decomposePar' in c for c in cmds), str(cmds))
        labels = [l for l, _c in backend._mesh_stages(spec, Log())]
        check('AMR stage label names the t = 0 refinement level',
              any('t = 0 refinement to level 2' in l for l in labels), str(labels))
        static = writer.render_case(Case3D(
            Lx=1.0, Ly=1.0, Lz=1.0, cell_size_m=0.1, charge=1.0,
            center=(0.5, 0.5, 0.5), charge_refine='zone', solver='blastfoam'))
        scmds = [c for _l, c in backend._mesh_stages(static, Log())]
        check('static refined spec: -noRefine and refineMesh passes as before',
              'setRefinedFields -noRefine' in scmds
              and sum('refineMesh' in c for c in scmds) == static.lmax
              and static.mesh_fields == () and backend.mesh_at(static, root) is None)
        uni = writer.render_case(Case3D(
            Lx=1.0, Ly=1.0, Lz=1.0, cell_size_m=0.1, charge=8.0,
            center=(0.5, 0.5, 0.5), solver='blastfoam'))
        ucmds = [c for _l, c in backend._mesh_stages(uni, Log())]
        check('uniform spec: no cell-centre stage, mesh_at None',
              not any('writeCellCentres' in c for c in ucmds)
              and backend.mesh_at(uni, root) is None)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_mesh_at_and_decode():
    print("\nmesh_at + mesh= decode path")
    root = tempfile.mkdtemp(prefix='blastlab_amr_')
    try:
        case, spec = amr_spec(root)
        # t = 0: the four base cells (level 0), levels only as the
        # polyMesh labelList setRefinedFields writes
        C0 = block_centres(0, 0, 0.5, 2)
        write_time(root, '0', 0.0, C0, [0, 0, 0, 0], np.full(4, P_AIR),
                   level_field=False, label_list=True)
        # t1: the (0.75, 0.75) base cell refined to level 1 (7 cells)
        C1 = np.vstack([C0[:3], block_centres(0.5, 0.5, 0.25, 2)])
        lv1 = [0, 0, 0, 1, 1, 1, 1]
        p1 = P_AIR + 1000.0 * np.arange(7)
        write_time(root, '1e-05', 1e-5, C1, lv1, p1)
        # t2: one of those level-1 cells refined to level 2 (10 cells)
        C2 = np.vstack([C1[:6], block_centres(0.75, 0.75, 0.125, 2)])
        lv2 = [0, 0, 0, 1, 1, 1, 2, 2, 2, 2]
        p2 = P_AIR + 1000.0 * np.arange(10)
        write_time(root, '2e-05', 2e-5, C2, lv2, p2)
        write_time(root, '3e-05', 3e-5, C2, lv2, p2, level_field=False)   # mid-write
        write_time(root, '4e-05', 4e-5, C2, lv2, p2, torn=True)           # torn C

        hooks = Log()
        backend.build_remap(spec, hooks)
        check('build_remap (AMR): t = 0 MeshMap on spec.mesh0, 4 cells, base level',
              spec.mesh0 is not None and spec.n_cells_actual == 4
              and spec.mesh0.counts[0] == 4 and (spec.mesh0.remap[0:4, 0:4] == 0).all()
              and spec.remap is None, str(hooks.lines))
        check('build_remap (AMR) logs the t = 0 line',
              any('AMR mesh at t = 0: 4 cells (L0 4 / L1 0 / L2 0)' in l for l in hooks.lines),
              str(hooks.lines))
        backend._initial_frame(spec, hooks)
        check('initial frame decoded through mesh0 (8x8 ambient)',
              len(hooks.frames) == 1 and hooks.frames[0][0].shape == (8, 8)
              and np.allclose(hooks.frames[0][0], P_AIR))

        m1 = backend.mesh_at(spec, os.path.join(root, '1e-05'))
        check('t1: 7 cells, counts (3, 4, 0)', m1.n_cells == 7 and m1.counts == (3, 4, 0),
              f'{m1.n_cells} {m1.counts}')
        got = backend.read_2d(os.path.join(root, '1e-05'), spec, ('p', 'rho', 'U'), mesh=m1)
        check('read_2d(mesh=): 8x8 display arrays, blocks carry the cell value',
              got['p'].shape == (8, 8) and got['rho'].shape == (8, 8)
              and (got['p'][0:4, 0:4] == p1[0]).all() and (got['p'][0:4, 4:8] == p1[1]).all()
              and (got['p'][4:8, 0:4] == p1[2]).all()
              and (got['p'][4:6, 4:6] == p1[3]).all() and (got['p'][6:8, 6:8] == p1[6]).all(),
              str(got['p']))
        check('to_grid(mesh=) matches MeshMap.gather',
              np.array_equal(reader.to_grid(p1, spec, mesh=m1), m1.gather(p1)))
        peak, imp = runloop.read_fo_fields(os.path.join(root, '1e-05'), spec, mesh=m1)
        check('read_fo_fields(mesh=): FO fields on the display grid',
              peak is not None and peak.shape == (8, 8) and (peak == got['p'] + 1.0).all()
              and np.allclose(imp, 2.0))
        m2 = backend.mesh_at(spec, os.path.join(root, '2e-05'))
        got2 = backend.read_2d(os.path.join(root, '2e-05'), spec, mesh=m2)
        check('t2: 10 cells, level-2 cells map one-to-one',
              m2.n_cells == 10 and m2.counts == (3, 3, 4)
              and sorted(np.unique(m2.remap[6:8, 6:8]).tolist()) == [6, 7, 8, 9]
              and (got2['p'][6:8, 6:8] == p2[m2.remap[6:8, 6:8]]).all())
        # the accumulator across a changing cell count
        acc = runloop.PeakImpulse()
        acc.add(got['p'], 1e-5, os.path.join(root, '1e-05'), spec, Log(), mesh=m1)
        acc.add(got2['p'], 2e-5, os.path.join(root, '2e-05'), spec, Log(), mesh=m2)
        pk, im, src = acc.final(got2['p'], os.path.join(root, '2e-05'), 2e-5, spec, mesh=m2)
        check('PeakImpulse across changing meshes: FO source, display shape',
              src == 'foam-fo' and pk.shape == (8, 8) and (pk == got2['p'] + 1.0).all()
              and acc.p_peak.shape == (8, 8))
        # readiness gate + torn file
        fields = ('p', 'rho', 'U', 'T', 'alpha.expl') + spec.mesh_fields
        order = runloop.OrderedIngest(spec, fields, Log())
        got_names = [n for n, _d in order.pending({'0': 0.0})]
        check('OrderedIngest with the mesh fields stops at the dir without cellLevel',
              got_names == ['1e-05', '2e-05'], str(got_names))
        try:
            backend.mesh_at(spec, os.path.join(root, '4e-05'))
            torn = 'no error'
        except ValueError as exc:
            torn = 'ValueError'
        except Exception as exc:                     # noqa: BLE001
            torn = type(exc).__name__ + ': ' + str(exc)
        check('a torn C raises ValueError (retry next poll)', torn == 'ValueError', torn)
        # geometric mismatch -> RuntimeError (fatal)
        write_time(root, '5e-05', 5e-5, C2[:-1], lv2[:-1], p2[:-1])
        try:
            backend.mesh_at(spec, os.path.join(root, '5e-05'))
            bad = 'no error'
        except RuntimeError as exc:
            bad = str(exc)
        check('a mesh that does not tile the display grid raises RuntimeError',
              'covered 0 times' in bad, bad)
        # t = 0 without any level information -> base level everywhere
        shutil.rmtree(os.path.join(root, '0', 'polyMesh'))
        m0 = backend.mesh_at(spec, os.path.join(root, '0'))
        check('t = 0 without polyMesh/cellLevel falls back to level 0',
              m0.n_cells == 4 and m0.counts[0] == 4)
        # the per-write log line
        line = runloop.amr_note(m1, 4, 1e-5)
        check('amr_note text', line == '  [blastfoam] AMR t = 0.010 ms: 7 cells (+3), L0 3 / L1 4 / L2 0',
              line)
        check('amr_note without a previous count shows +0',
              '(+0)' in runloop.amr_note(m1, None, 1e-5))
        # finalize_2d over the fake dirs: per-time meshes, AMR meta
        ingested = {'1e-05': 1e-5, '2e-05': 2e-5}
        acc = runloop.PeakImpulse()
        frame_lv = [m1.levels, m2.levels]
        res = backend.finalize_2d(case, spec, hooks, 'test', 2, ingested, ['1e-05'],
                                  [1e-5, 2e-5], [got['p'], got2['p']], 10, acc,
                                  frame_lv=frame_lv)
        m = res.meta
        check("finalize_2d: meta['refine'] carries the final mesh's levels + counts",
              m['refine']['amr'] == 2 and m['refine']['n_cells'] == 10
              and m['refine']['counts'] == (3, 3, 4)
              and np.array_equal(m['refine']['levels'], m2.levels), str(m['refine'].keys()))
        check("finalize_2d: frames['levels'] one per frame",
              len(m['frames']['levels']) == len(m['frames']['pressures']) == 2
              and m['frames']['levels'][1].shape == (8, 8))
        check('finalize_2d: final snapshot on the display grid',
              list(res.snapshots.values())[-1]['p'].shape == (8, 8)
              and m['peak_source'] == 'foam-fo')
        check('finalize_2d: the final live frame carries its level map',
              hooks.frames and hooks.frames[-1][2] is not None
              and np.array_equal(hooks.frames[-1][2], m2.levels))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_label_list():
    print("\nread_label_list (ascii + binary)")
    root = tempfile.mkdtemp(prefix='blastlab_amr_')
    try:
        p = os.path.join(root, 'cellLevel')
        with open(p, 'w') as f:
            f.write(HEADER.replace('{cls}', 'labelList').replace('{obj}', 'cellLevel')
                    + '// * * //\n\n5\n(\n0\n1\n2\n1\n0\n)\n')
        check('ascii labelList', reader.read_label_list(p).tolist() == [0, 1, 2, 1, 0])
        with open(p, 'wb') as f:
            f.write(HEADER.replace('{cls}', 'labelList').replace('{obj}', 'cellLevel')
                    .replace('ascii', 'binary').encode()
                    + b'// * * //\n\n\n4\n(' + np.array([0, 2, 1, 3], '<i4').tobytes() + b')\n')
        check('binary labelList (32-bit labels)', reader.read_label_list(p).tolist() == [0, 2, 1, 3])
        with open(p, 'wb') as f:
            f.write(HEADER.replace('{cls}', 'labelList').replace('{obj}', 'cellLevel')
                    .replace('ascii', 'binary').encode()
                    + b'// * * //\n\n\n4\n(' + np.array([0, 2], '<i4').tobytes())
        try:
            reader.read_label_list(p)
            bad = 'no error'
        except ValueError:
            bad = 'ValueError'
        check('truncated binary labelList -> ValueError', bad == 'ValueError', bad)
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == '__main__':
    test_stages_and_static_inertness()
    test_mesh_at_and_decode()
    test_label_list()
    print()
    print('FOAM AMR INGEST: ' + ('PASS' if not FAILS else f'FAIL ({len(FAILS)}): ' + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)
