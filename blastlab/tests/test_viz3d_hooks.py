"""Hook-level test: a tiny 3D run with a stub 3D-viewer client attached.
Asserts the solver sends well-formed frame payloads and that attaching
a viewer changes nothing about the physics (gauge output identical)."""
import os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.solvers.solver3d import _run_blast_3d
from blastlab.solvers.hooks import RunHooks
from blastlab.viz3d.client import Viewer3DClient

FAIL = []

def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        FAIL.append(name)


class StubClient:
    """Captures send_frame calls without any process/queue."""
    alive = True

    def __init__(self):
        self.calls = []

    def send_frame(self, t, fields, force=False):
        self.calls.append((t, {k: np.asarray(v).copy()
                               for k, v in fields.items()}, force))


# charge big enough that dx=0.1 resolves r_exp without auto-refinement
# (r_exp ~ 0.51 m >= 5 cells) so the grid stays a fast 20^3
CASE = dict(Lx=2.0, Ly=2.0, Lz=2.0, cell_size_m=0.1, charge=900.0,
            charge_center=(1.0, 1.0, 1.0), eos='idealGas',
            obstacles=[(1.6, 1.9, 0.8, 1.2, 0.0, 0.6)],
            # T50: the pre-T50 default (transmit AND terminate); the
            # plain 'transmit' default would run these to the safety cap
            bcs=dict(x_lo='terminate', x_hi='terminate',
                     y_lo='terminate', y_hi='terminate',
                     z_lo='reflect', z_hi='terminate'),
            gauges=[(1.0, 1.0, 1.8), (1.0, 0.2, 0.5)],
            n_snapshots=3)

print("\nH1: run without viewer (reference)")
hooks_a = RunHooks()
res_a = _run_blast_3d(hooks=hooks_a, **CASE)
check("run completed", len(res_a.gauges['times']) > 5)

print("\nH2: run with stub viewer attached")
hooks_b = RunHooks()
stub = StubClient()
hooks_b.viewer3d = stub
res_b = _run_blast_3d(hooks=hooks_b, **CASE)

check("frames were sent", len(stub.calls) >= 1, f"n={len(stub.calls)}")
t_last, fields, forced = stub.calls[-1]
check("final frame forced", forced)
check("payload has p/rho/e/p_peak/imp",
      set(fields) == {'p', 'rho', 'e', 'p_peak', 'imp'}, str(set(fields)))
shape = res_a.meta['solid'].shape
check("full-res fields", all(fields[k].shape == shape for k in fields),
      str(fields['p'].shape))
check("p_peak >= p everywhere",
      bool((fields['p_peak'] >= fields['p'] - 1e-9).all()))
check("impulse accumulated somewhere", float(fields['imp'].max()) > 0.0)
check("final frame time = run end",
      abs(t_last - res_b.gauges['times'][-1]) < 1e-12)
check("times monotonic",
      all(np.diff([c[0] for c in stub.calls]) > 0))

print("\nH3: physics unchanged by the viewer")
check("gauge times identical",
      np.array_equal(res_a.gauges['times'], res_b.gauges['times']))
check("gauge pressures identical",
      all(np.array_equal(pa, pb) for pa, pb in
          zip(res_a.gauges['pressures'], res_b.gauges['pressures'])))
check("stop reason identical", res_a.stop_reason == res_b.stop_reason)

print("\nH4: snapshots carry t and rho3 for playback")
snaps = list(res_a.snapshots.values())
check("snapshot has t", all('t' in s for s in snaps))
check("snapshot t increases",
      all(np.diff([s['t'] for s in snaps]) > 0))
check("snapshot rho3 shape", all(
    s['rho3'].shape == shape and s['rho3'].dtype == np.float32
    for s in snaps), str(snaps[0]['rho3'].shape))

print("\nH5: client-side payload construction (no process)")
scene = dict(x_c=res_a.meta['x_c'], y_c=res_a.meta['y_c'],
             z_c=res_a.meta['z_c'], dx=res_a.meta['dx'],
             solid=res_a.meta['solid'], obstacles=res_a.meta['obstacles'],
             Lx=2.0, Ly=2.0, Lz=2.0, charge_center=(1.0, 1.0, 1.0),
             r_exp=res_a.meta['r_exp'], bcs=res_a.meta['bcs'])
client = Viewer3DClient.__new__(Viewer3DClient)   # skip process spawn
from blastlab.viz3d.sampling import build_face_index, choose_stride
client._stride = choose_stride(shape)
client._face_specs = build_face_index(
    scene['obstacles'], scene['x_c'], scene['y_c'], scene['z_c'],
    scene['solid'], scene['bcs'])
check("stride 1 on tiny grid", client._stride == 1)
check("face specs built (5 faces + ground)",
      len(client._face_specs) == 6, f"n={len(client._face_specs)}")

print("\nH6: stepped-execution gate (GuiHooks)")
import queue as _q
import threading
import time as _time
from blastlab.gui.worker import GuiHooks

gh = GuiHooks(_q.Queue(), threading.Event())
t0 = _time.perf_counter()
gh.step_gate()          # default mode 'run': never blocks
check("run mode passes through", _time.perf_counter() - t0 < 0.05)
check("run mode never 'will pause'", not gh.exec_will_pause())

gh.set_exec('pause')
gh.set_exec(2)          # budget of 2 steps
check("budget of 2: not about to pause", not gh.exec_will_pause())
gh.step_gate()          # consumes 1
check("last budgeted step flagged", gh.exec_will_pause())
gh.step_gate()          # consumes the 2nd
check("budget exhausted -> paused", gh.exec_paused())

resumed = []
def _resume():
    _time.sleep(0.3)
    gh.set_exec('run')
    resumed.append(True)
threading.Thread(target=_resume, daemon=True).start()
t0 = _time.perf_counter()
gh.step_gate()          # blocks until the thread resumes it
dt_block = _time.perf_counter() - t0
check("gate blocked until resume", resumed and 0.2 < dt_block < 3.0,
      f"({dt_block:.2f}s)")

gh2 = GuiHooks(_q.Queue(), threading.Event())
gh2.set_exec('pause')
def _stop():
    _time.sleep(0.3)
    gh2._stop.set()
threading.Thread(target=_stop, daemon=True).start()
t0 = _time.perf_counter()
gh2.step_gate()         # paused, but Stop must release it
check("stop releases a paused gate",
      0.2 < _time.perf_counter() - t0 < 3.0)

print("\nH6b: live-view refresh policy")
rh = RunHooks()
check("default seconds policy", rh.refresh == ('seconds', 0.05)
      and rh.refresh3d == ('seconds', 0.2))
rh.refresh = ('steps', 3)
check("steps mode: due on multiples",
      [rh.draw_due(s, _time.time()) for s in range(7)]
      == [True, False, False, True, False, False, True])
rh.refresh = ('seconds', 0.05)
check("seconds mode: throttles recent draws",
      not rh.draw_due(1, _time.time())
      and rh.draw_due(1, _time.time() - 1.0))

class CountingHooks(RunHooks):
    def __init__(self):
        self.n_frames = 0
    def frame(self, field2d, t):
        self.n_frames += 1

ch1, ch3 = CountingHooks(), CountingHooks()
ch1.refresh = ('steps', 1)
ch3.refresh = ('steps', 3)
r1 = _run_blast_3d(hooks=ch1, **CASE)
r3 = _run_blast_3d(hooks=ch3, **CASE)
check("steps=1 draws every step (+final)",
      ch1.n_frames >= 5, f"n={ch1.n_frames}")
check("steps=3 draws about 1/3 as often",
      2 <= ch3.n_frames < ch1.n_frames,
      f"{ch3.n_frames} vs {ch1.n_frames}")
check("policy does not change physics",
      np.array_equal(r1.gauges['times'], r3.gauges['times']))

print("\nH7: end time cap")
# shock hits the open boundary at ~0.026 ms; t_end must be earlier
res_t = _run_blast_3d(hooks=RunHooks(), t_end=1e-5, **CASE)
check("run stopped at end time",
      res_t.stop_reason == 'end time reached', res_t.stop_reason)
check("t_final ~ t_end",
      abs(res_t.gauges['times'][-1] - 1e-5) < 1e-9,
      f"t={res_t.gauges['times'][-1]:.2e}")

print("\nH8: selectable live slice")
class SliceHooks(RunHooks):
    def __init__(self):
        self.info = None
        self.shapes = []
    def run_started(self, info):
        self.info = info
    def frame(self, field2d, t):
        self.shapes.append(np.asarray(field2d).shape)

# non-cubic domain so each slice orientation has a distinct shape:
# 20 x 20 x 12 cells, burst at (1, 1, 0.6). 900 kg keeps r_exp/5 > dx
# so the grid is NOT auto-refined.
SCASE = dict(Lx=2.0, Ly=2.0, Lz=1.2, cell_size_m=0.1, charge=900.0,
             charge_center=(1.0, 1.0, 0.6), eos='idealGas',
             bcs=dict(x_lo='terminate', x_hi='terminate',
                      y_lo='terminate', y_hi='terminate',
                      z_lo='reflect', z_hi='terminate'),
             n_snapshots=1, gauges=[])

sh_y = SliceHooks()
_run_blast_3d(hooks=sh_y, **SCASE)                       # default: y
check("default y slice: x-z shape", sh_y.shapes[-1] == (20, 12))
check("default y labels", sh_y.info['xlabel'] == 'x [m]'
      and sh_y.info['ylabel'] == 'z [m]'
      and sh_y.info['title'].startswith('y ='))

sh_z = SliceHooks()
res_z = _run_blast_3d(hooks=sh_z, slice_axis='z', slice_pos=0.15,
                      record_frames=10, **SCASE)
check("z slice: x-y shape", sh_z.shapes[-1] == (20, 20))
check("z labels + position", sh_z.info['xlabel'] == 'x [m]'
      and sh_z.info['ylabel'] == 'y [m]'
      and sh_z.info['title'] == 'z = 0.15 m', sh_z.info['title'])
check("meta records the slice", res_z.meta['slice_axis'] == 'z'
      and res_z.meta['s0'] == 1)
check("animation frames use the slice",
      res_z.meta['frames']['pressures'][0].shape == (20, 20))
check("solid slice matches", sh_z.info['solid'].shape == (20, 20))

sh_x = SliceHooks()
_run_blast_3d(hooks=sh_x, slice_axis='x', **SCASE)
check("x slice: y-z shape + labels", sh_x.shapes[-1] == (20, 12)
      and sh_x.info['xlabel'] == 'y [m]'
      and sh_x.info['title'].startswith('x ='))

import os as _os
import tempfile as _tf
from blastlab.output.animation import write_animation
_gif = _os.path.join(_tf.gettempdir(), 'blastlab_slice_test.gif')
out = write_animation(res_z.meta, _gif, fps=10)
check("animation written for a z slice",
      out is not None and _os.path.getsize(out) > 2000)
try:
    _os.remove(out)
except OSError:
    pass

print("\n" + "=" * 50)
if FAIL:
    print(f"FAILED: {len(FAIL)} check(s): {FAIL}")
    sys.exit(1)
print("All viz3d hook checks passed.")
