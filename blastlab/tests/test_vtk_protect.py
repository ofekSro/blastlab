"""OUT-2 (D1, D10): the backend protects every write finalize re-reads,
so the VTK export's deletes never change a Result (no WSL, no GUI).

docs/batches/2026-09-27-out-2-vtk-output.md, Step 7 (V3c).

A fake finalize tree - ascii time directories written the way blastFoam
lays them out, a shock whose radius grows by a fixed step per write - is
run through the REAL solve_1d/2d/3d_foam callbacks (read_dir, on_frame)
and finalize_1d/2d/3d, with backend.FoamRunLoop replaced by a loop that
feeds the writes in time order. Two runs per dimension:

  * `keep`: nothing is deleted;
  * `purge`: after every write, every dir the pure
    `vtk_export.vtk_purge_plan` allows (everything converted and copied,
    the backend's `protect`ed names excluded) is deleted - the export at
    its most aggressive.

Pinned:
  * the snapshot labels and arrays, the pin time, final_state /
    final_profile, the trigger remap state, the peak / impulse maps and
    the frames are identical between `keep` and `purge`, and the purge
    really deleted writes;
  * the `keep` output equals the characterisation digests taken with the
    backend BEFORE Step 7 (`BEFORE`), so without deletion nothing moved;
  * resume_run's D10 note (`vtk_export.note_resume`).

Run:  cd blastlab/tests && python test_vtk_protect.py   (or pytest)
"""
import hashlib
import os
import shutil
import sys
import tempfile
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

import numpy as np                                             # noqa: E402

from blastlab.core.constants import P_AIR                      # noqa: E402
from blastlab.models.case import Case1D, Case2D, Case3D        # noqa: E402
from blastlab.solvers.foam import backend, env, reader, writer  # noqa: E402
from blastlab.solvers.foam import vtk_export as vx             # noqa: E402
from blastlab.solvers.foam.runloop import new_live             # noqa: E402
from blastlab.solvers.hooks import RunHooks                    # noqa: E402

#: sha256 over the `keep` Result of each dimension, measured with
#: solvers/foam/backend.py as it was BEFORE Step 7 (commit c8e53aa + the
#: Step 6 run-loop wiring, which backend does not see): the
#: characterisation of "without deletion, the output is unchanged"
BEFORE = {
    '1d': '5414485fa790d4923d561e9b5d14984fcebaee08de0c41d8b12eafbd1d951eec',
    '2d': '30d66fbf90917d50c4c3f5fce0c0625168c90c520dcd3cec755028503f3a283a',
    '3d': '1d254c18a2d5e4eda02b051e292cb8982a3e040fac1b454aabbb0860aa1f1563',
}


# ── the fake tree ────────────────────────────────────────────────────────
def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='ascii', newline='\n') as f:
        f.write(text)


def _scalar(path, vals):
    body = '\n'.join(f'{v:.10g}' for v in vals)
    _write(path, 'FoamFile\n{\n    format      ascii;\n    class       '
                 'volScalarField;\n}\n\ninternalField   nonuniform '
                 f'List<scalar>\n{len(vals)}\n(\n{body}\n)\n;\n')


def _vector(path, vals):
    body = '\n'.join(f'({a:.10g} {b:.10g} {c:.10g})' for a, b, c in vals)
    _write(path, 'FoamFile\n{\n    format      ascii;\n    class       '
                 'volVectorField;\n}\n\ninternalField   nonuniform '
                 f'List<vector>\n{len(vals)}\n(\n{body}\n)\n;\n')


def _time(dpath, t):
    _write(os.path.join(dpath, 'uniform', 'time'),
           f'FoamFile\n{{\n    format ascii;\n}}\nvalue           {t!r};\n'
           f'deltaT          1e-08;\n')


def write_tree(spec, dist, radii, times, extra=()):
    """One time dir per (t, R): p = P_AIR + 2e5 behind a front at R (a
    little ramp so snapshots differ), rho / T / U / alpha to match, and
    the per-step pMax / impulse fields for 2D/3D. `dist` is each cell's
    distance from the burst, flat in OpenFOAM cell order."""
    n = len(dist)
    peak = np.full(n, P_AIR)
    imp = np.zeros(n)
    for k, (t, R) in enumerate(zip(times, radii)):
        name = writer.tfmt(t)
        d = os.path.join(spec.case_unc, name)
        shocked = dist <= R
        p = np.where(shocked, P_AIR + 2e5 * (1.0 + dist / (R + 1e-9)), P_AIR)
        rho = np.where(shocked, 2.0 + dist, 1.2)
        T = np.where(shocked, 600.0 + 100 * dist, 300.0)
        alpha = (dist < 0.3 * R).astype(float)
        U = np.stack([np.where(shocked, 100.0 * (1 + dist), 0.0),
                      np.where(shocked, 10.0 * k, 0.0), np.zeros(n)], axis=1)
        np.maximum(peak, p, out=peak)
        imp += (p - P_AIR) * 1e-5
        _time(d, t)
        _scalar(os.path.join(d, 'p'), p)
        _scalar(os.path.join(d, 'rho'), rho)
        _scalar(os.path.join(d, 'T'), T)
        _scalar(os.path.join(d, f'alpha.{spec.phase}'), alpha)
        _vector(os.path.join(d, 'U'), U)
        if spec.dim >= 2:
            _scalar(os.path.join(d, 'pMax'), peak)
            _scalar(os.path.join(d, 'impulse'), imp)


class FakeLoop:
    """backend.FoamRunLoop stand-in: feeds every written time to the
    backend's own read_dir / on_frame in time order and, when `purge`,
    deletes after each write what vtk_purge_plan allows."""
    purge = False
    last = None

    def __init__(self, spec, hooks, fields, done, live_set, decode,
                 read_dir, on_frame):
        self.spec, self.hooks, self.done = spec, hooks, done
        self.read_dir, self.on_frame = read_dir, on_frame
        self.st = dict(step=0, t=0.0, dt=0.0, p_max=float(P_AIR),
                       frac=None, t_frame=-1.0)
        self.live = new_live()
        self.stop_requested = False
        self.stop_reason = 'safety cap'
        self._protect = {}
        self.deleted = []
        FakeLoop.last = self

    @property
    def protected(self):
        return set(self._protect)

    def request_stop(self, reason):
        if not self.stop_requested:
            self.stop_requested = True
            self.stop_reason = reason

    def maybe_adapt(self, n):
        pass

    def note_pause(self, will_pause):
        pass

    def gated_step(self):
        pass

    # the same keyed semantics as runloop.FoamRunLoop -> VtkExport
    def protect(self, name, why='read'):
        if name is not None:
            self._protect.setdefault(name, set()).add(why)

    def unprotect(self, name, why='read'):
        keys = self._protect.get(name)
        if keys is not None:
            keys.discard(why)
            if not keys:
                del self._protect[name]

    def run(self):
        spec = self.spec
        for _t, name in reader.list_times(spec.case_unc):
            if name == spec.start_dir:
                continue
            self.st['step'] += 10
            dpath = spec.time_dirs(name)
            self.on_frame(name, dpath, self.read_dir(name, dpath))
            if self.purge:
                done = list(self.done)
                for t in vx.vtk_purge_plan(done, done, done, done,
                                           spec.start_dir, done,
                                           self.protected):
                    if t not in self.deleted:
                        shutil.rmtree(os.path.join(spec.case_unc, t))
                        self.deleted.append(t)
        return self.stop_reason


class Hooks(RunHooks):
    def __init__(self):
        self.lines = []

    def log(self, msg):
        self.lines.append(msg)


# ── the three cases ──────────────────────────────────────────────────────
def spec_for(case, tmp):
    spec = writer.render_case(case)
    spec.case_unc = tmp
    spec.case_posix = env.RUNS_ROOT + '/fake_protect'
    spec.files = None
    spec.adaptive_write = False
    os.makedirs(os.path.join(tmp, spec.start_dir), exist_ok=True)
    return spec


def case_1d():
    return Case1D(radius_m=1.0, charge_kg=0.5, cell_size_m=0.02,
                  solver='blastfoam', n_snapshots=3, gauge_radii=[],
                  bc_outer='terminate')


def case_2d():
    return Case2D(geometry='axisymmetric', Lx=0.5, Ly=0.5,
                  cell_size_m=0.025, charge=20.0, center=(0.0, 0.25),
                  solver='blastfoam', n_snapshots=3, record_frames=50,
                  gauges=[(0.3, 0.25)], trigger_gauge=1,
                  trigger_action='remap',
                  bcs=dict(x_lo='reflect', x_hi='terminate',
                           y_lo='reflect', y_hi='reflect'))


def case_3d():
    return Case3D(Lx=0.8, Ly=0.8, Lz=0.8, cell_size_m=0.05, charge=60.0,
                  center=(0.4, 0.4, 0.4), solver='blastfoam', n_snapshots=3,
                  gauges=[], record_frames=50,
                  bcs=dict(x_lo='terminate', x_hi='terminate',
                           y_lo='reflect', y_hi='reflect',
                           z_lo='reflect', z_hi='reflect'))


def run(dim, purge):
    """(Result, FakeLoop, log lines) of one fake run."""
    tmp = tempfile.mkdtemp(prefix=f'blastlab_vtk_protect_{dim}d_')
    real = backend.FoamRunLoop
    try:
        case = {1: case_1d, 2: case_2d, 3: case_3d}[dim]()
        spec = spec_for(case, tmp)
        g = spec.grid
        if dim == 1:
            dist = g['r']
            radii = [0.1 * k for k in range(1, 13)]
        elif dim == 2:
            X, Y = np.meshgrid(g['x_c'], g['y_c'], indexing='ij')
            dist = np.hypot(X - spec.center[0],
                            Y - spec.center[1]).ravel(order='F')
            radii = [0.06 * k for k in range(1, 11)]
        else:
            X, Y, Z = np.meshgrid(g['x_c'], g['y_c'], g['z_c'],
                                  indexing='ij')
            dist = np.sqrt((X - 0.4) ** 2 + (Y - 0.4) ** 2
                           + (Z - 0.4) ** 2).ravel(order='F')
            radii = [0.05 * k for k in range(1, 10)]
        times = [1e-5 * k for k in range(1, len(radii) + 1)]
        write_tree(spec, dist, radii, times)
        FakeLoop.purge = purge
        backend.FoamRunLoop = FakeLoop
        hooks = Hooks()
        solve = {1: backend.solve_1d_foam, 2: backend.solve_2d_foam,
                 3: backend.solve_3d_foam}[dim]
        res = solve(case, hooks, adaptive_write=False, spec=spec)
        return res, FakeLoop.last, hooks.lines
    finally:
        backend.FoamRunLoop = real
        FakeLoop.purge = False
        shutil.rmtree(tmp, ignore_errors=True)


# ── comparing Results ────────────────────────────────────────────────────
def _items(obj, prefix=''):
    """(path, value) leaves of a Result's snapshots / meta subset."""
    if isinstance(obj, dict):
        for k in sorted(obj, key=str):
            yield from _items(obj[k], f'{prefix}/{k}')
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from _items(v, f'{prefix}[{i}]')
    else:
        yield prefix, obj


META_KEYS = ('final_profile', 'final_state', 'trigger_state', 'trigger',
             'p_peak', 'impulse', 'peak_source', 'frames')


def fingerprint(res):
    """What finalize read from disk, as comparable leaves."""
    out = dict(snapshots=res.snapshots, stop=res.stop_reason,
               meta={k: res.meta.get(k) for k in META_KEYS
                     if k in res.meta})
    return list(_items(out))


def digest(res):
    h = hashlib.sha256()
    for path, v in fingerprint(res):
        h.update(path.encode())
        if isinstance(v, np.ndarray):
            h.update(str(v.dtype).encode() + str(v.shape).encode())
            h.update(np.ascontiguousarray(v).tobytes())
        else:
            h.update(repr(v).encode())
    return h.hexdigest()


def same(a, b):
    fa, fb = fingerprint(a), fingerprint(b)
    if [p for p, _ in fa] != [p for p, _ in fb]:
        return False, 'different keys'
    for (p, va), (_q, vb) in zip(fa, fb):
        if isinstance(va, np.ndarray) or isinstance(vb, np.ndarray):
            if not (np.shape(va) == np.shape(vb)
                    and np.array_equal(va, vb)):
                return False, p
        elif va != vb:
            return False, f'{p}: {va!r} != {vb!r}'
    return True, ''


def _pin_line(lines):
    return [ln for ln in lines if 'hand-off state pinned' in ln]


def _check_dim(dim):
    keep, loop_k, lines_k = run(dim, purge=False)
    purge, loop_p, lines_p = run(dim, purge=True)
    assert loop_k.deleted == []
    assert loop_p.deleted, f'{dim}D: the purge deleted nothing'
    ok, why = same(keep, purge)
    assert ok, f'{dim}D keep vs purge differ at {why}'
    assert _pin_line(lines_k) == _pin_line(lines_p)
    return keep, loop_p, lines_k


def test_1d():
    keep, loop, lines = _check_dim(1)
    assert keep.stop_reason.startswith('shock arrived'), keep.stop_reason
    pin = _pin_line(lines)
    assert pin and 't = 0.0900 ms' in pin[0], pin
    assert keep.meta['final_profile']['t'] == 9e-5
    assert '9e-05' in loop.protected, loop.protected
    assert '8e-05' not in loop.protected        # the old candidate released
    got = digest(keep)
    if BEFORE['1d'] is not None:
        assert got == BEFORE['1d'], got
    return got


def test_2d():
    keep, loop, lines = _check_dim(2)
    assert keep.stop_reason.startswith('shock arrived'), keep.stop_reason
    pin = _pin_line(lines)
    assert pin, lines
    assert keep.meta.get('trigger_state') is not None
    trig = keep.meta['trigger']['t']
    assert writer.tfmt(trig) in loop.protected, (trig, loop.protected)
    # the deleted quiet writes were answered from the arrived cache
    assert set(loop.deleted) & set(n for n in loop.done
                                   if loop.done[n] < keep.meta[
                                       'final_state']['t']), loop.deleted
    got = digest(keep)
    if BEFORE['2d'] is not None:
        assert got == BEFORE['2d'], got
    return got


def test_3d():
    keep, loop, _lines = _check_dim(3)
    assert len(keep.snapshots) >= 3, list(keep.snapshots)
    got = digest(keep)
    if BEFORE['3d'] is not None:
        assert got == BEFORE['3d'], got
    return got


def test_resume_note():
    """D10: resume_run's note - a write the export converted that is no
    longer on disk sets replay_incomplete, once, with one log line."""
    from blastlab.output import vtk_series as vs
    tmp = tempfile.mkdtemp(prefix='blastlab_vtk_protect_resume_')
    try:
        lines = []
        assert not vx.note_resume(None, ['0.001'], lines.append)
        assert not vx.note_resume(tmp, ['0.001'], lines.append)  # no manifest
        vs.write_vtk_manifest(tmp, dict(families={'volumes': dict(
            count=3, times=['0.001', '0.002', '0.003'], series=[])}))
        assert not vx.note_resume(tmp, ['0', '0.001', '0.002', '0.003'],
                                  lines.append)
        assert lines == []
        assert vx.note_resume(tmp, ['0', '0.002', '0.003'], lines.append)
        assert len(lines) == 1 and 'removed 1 written time' in lines[0]
        assert vs.load_vtk_manifest(tmp)['replay_incomplete'] is True
        # a W3 auto-resume's new export keeps the flag
        spec = SimpleNamespace(dim=3, vtk_volumes=dict(
            on=True, mode='time', value=0.1, fields=['p']),
            vtk_surfaces=None, decomposed=False, n_procs=1)
        ex = vx.VtkExport(spec, SimpleNamespace(vtk_dir=tmp,
                                                log=lines.append), ('p',))
        assert ex.replay_incomplete and ex.state()['replay_incomplete']
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


TESTS = [test_1d, test_2d, test_3d, test_resume_note]


def main():
    fails = []
    for t in TESTS:
        try:
            got = t()
            print(f'  [PASS] {t.__name__}  ({got})')
        except Exception as exc:                    # noqa: BLE001
            import traceback
            traceback.print_exc()
            print(f'  [FAIL] {t.__name__}: {exc!r}')
            fails.append(t.__name__)
    print(f'\nVTK PROTECT: {"PASS" if not fails else "FAIL"} '
          f'({len(TESTS) - len(fails)}/{len(TESTS)})')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
