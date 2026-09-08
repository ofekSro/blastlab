"""Verification suite for blastlab.viz3d.sampling (pure NumPy, no pyvista)."""
import os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core.grid import make_grid
from blastlab.core.bc import solid_mask_3d
from blastlab.viz3d.sampling import (choose_stride, decimate,
                                     build_face_index, extract_loads,
                                     FrameStore)

FAIL = []

def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        FAIL.append(name)


# ── T1: stride & decimation ──────────────────────────────────────────────────
print("\nT1: choose_stride / decimate")
check("stride 1 when small", choose_stride((100, 100, 100)) == 1)
check("stride 2 at 200", choose_stride((200, 150, 100)) == 2)
check("stride 3 at 300", choose_stride((300, 10, 10)) == 3)

arr = np.arange(24 * 20 * 16, dtype=np.float64).reshape(24, 20, 16)
dec = decimate(arr, 2)
check("decimated shape", dec.shape == (12, 10, 8))
check("decimated dtype", dec.dtype == np.float32)
check("decimated contiguous", dec.flags['C_CONTIGUOUS'])
check("decimated values", float(dec[3, 4, 5]) == float(arr[6, 8, 10]))


# ── T2: face index on a single box on the ground ─────────────────────────────
print("\nT2: build_face_index - one box on the ground")
grid = make_grid(2.0, 2.0, 2.0, 0.1)
x_c, y_c, z_c = grid['x_c'], grid['y_c'], grid['z_c']
box = (0.5, 1.0, 0.5, 1.0, 0.0, 0.5)          # sits on the ground
solid = solid_mask_3d(x_c, y_c, z_c, [box])
bcs = dict(x_lo='terminate', x_hi='terminate',
           y_lo='terminate', y_hi='terminate',
           z_lo='reflect', z_hi='terminate')
specs = build_face_index([box], x_c, y_c, z_c, solid, bcs)
ids = {s.face_id for s in specs}
check("5 box faces + ground", ids == {'box0:x_lo', 'box0:x_hi',
                                      'box0:y_lo', 'box0:y_hi',
                                      'box0:z_hi', 'ground'},
      str(sorted(ids)))

coords = (x_c, y_c, z_c)
ok_fluid, ok_solid = True, True
for s in specs:
    if s.face_id == 'ground':
        continue
    # sampled layer must be fluid (away from buried cells)
    sl = [slice(s.lo[0], s.hi[0]), slice(s.lo[1], s.hi[1])]
    sl.insert(s.axis, s.layer)
    layer_solid = solid[tuple(sl)]
    ok_fluid &= not layer_solid.any()
    # one step back toward the box must be solid
    sl[s.axis] = s.layer - s.side
    ok_solid &= bool(solid[tuple(sl)].all())
check("face layers are fluid", ok_fluid)
check("cells behind faces are solid", ok_solid)

xhi = next(s for s in specs if s.face_id == 'box0:x_hi')
check("x_hi plane at box surface", abs(xhi.plane - 1.0) < 1e-9,
      f"plane={xhi.plane}")
check("x_hi side is +1", xhi.side == +1)
check("x_hi shape matches box span", xhi.buried.shape == (5, 5),
      str(xhi.buried.shape))

gnd = next(s for s in specs if s.face_id == 'ground')
check("ground covers domain", gnd.buried.shape == (len(x_c), len(y_c)))
check("ground buried under box",
      gnd.buried[6, 6] and not gnd.buried[0, 0])

# no ground spec when z_lo is open
specs_open = build_face_index([box], x_c, y_c, z_c, solid,
                              dict(bcs, z_lo='terminate'))
check("no ground when z_lo open",
      'ground' not in {s.face_id for s in specs_open})


# ── T3: dropped faces - domain-flush and buried ──────────────────────────────
print("\nT3: dropped faces")
box_edge = (1.5, 2.0, 0.5, 1.0, 0.5, 1.0)     # flush with x_hi boundary
solid_e = solid_mask_3d(x_c, y_c, z_c, [box_edge])
specs_e = build_face_index([box_edge], x_c, y_c, z_c, solid_e, bcs)
ids_e = {s.face_id for s in specs_e}
check("x_hi face dropped at domain edge", 'box0:x_hi' not in ids_e, str(sorted(ids_e)))
check("other faces kept", {'box0:x_lo', 'box0:y_lo', 'box0:y_hi',
                           'box0:z_lo', 'box0:z_hi'} <= ids_e)

two = [(0.5, 1.0, 0.5, 1.0, 0.0, 0.5), (1.0, 1.5, 0.5, 1.0, 0.0, 0.5)]
solid_2 = solid_mask_3d(x_c, y_c, z_c, two)
specs_2 = build_face_index(two, x_c, y_c, z_c, solid_2, bcs)
ids_2 = {s.face_id for s in specs_2}
check("touching faces buried & dropped",
      'box0:x_hi' not in ids_2 and 'box1:x_lo' not in ids_2, str(sorted(ids_2)))


# ── T4: extract_loads values ─────────────────────────────────────────────────
print("\nT4: extract_loads")
Nx, Ny, Nz = len(x_c), len(y_c), len(z_c)
p = np.arange(Nx * Ny * Nz, dtype=np.float64).reshape(Nx, Ny, Nz)
loads = extract_loads(p, specs)
check("all faces extracted", set(loads) == ids)
xl = next(s for s in specs if s.face_id == 'box0:x_hi')
expect = p[xl.layer, xl.lo[0]:xl.hi[0], xl.lo[1]:xl.hi[1]]
check("x_hi values match layer", np.array_equal(loads['box0:x_hi'], expect))
check("loads are float32", loads['box0:x_hi'].dtype == np.float32)
g = loads['ground']
check("ground NaN under box", np.isnan(g[6, 6]) and not np.isnan(g[0, 0]))
check("source field not modified", not np.isnan(p).any())


# ── T5: FrameStore cap & thinning ────────────────────────────────────────────
print("\nT5: FrameStore")
frame_bytes = 1000 * 4
store = FrameStore(mem_cap=20 * frame_bytes)     # room for ~20 frames
for k in range(200):
    store.append(k * 1e-4, dict(p=np.zeros(1000, np.float32)))
check("count bounded", len(store) <= 22, f"n={len(store)}")
check("times monotonic", all(np.diff(store.times) > 0))
check("history spans the run",
      store.times[0] <= 1e-3 and store.times[-1] >= 150e-4,
      f"[{store.times[0]:g}, {store.times[-1]:g}]")
stored = store.append(0.02, dict(p=np.zeros(1000, np.float32)), force=True)
check("force append kept", stored and store.times[-1] == 0.02)
check("latest returns newest", store.latest[0] == 0.02)

nested = FrameStore()
nested.append(0.0, dict(p=np.zeros(10, np.float32),
                        loads=dict(a=np.zeros(5, np.float32))))
check("nested load bytes counted", nested._bytes == 10 * 4 + 5 * 4)

# ── T5b: B20 - thinning must never discard the frame it just accepted ───────
# (stride-rejected offers - kept=False, unrelated to B20 - are skipped;
# this isolates the accept-then-immediately-thinned case, including the
# "crossed the cap with an even stored length" case the bug hit.)
print("\nT5b: FrameStore thinning keeps the newest frame")
tiny = FrameStore(mem_cap=1)      # every accepted append re-triggers thinning
accepted_but_lost = 0
mismatched_last_t = 0
for k in range(50):
    t = k * 1e-4
    kept = tiny.append(t, dict(p=np.zeros(100, np.float32)))
    if kept and tiny.times[-1] != t:
        mismatched_last_t += 1
check("append() never reports 'kept' while the frame is actually gone "
      "after thinning", mismatched_last_t == 0, f"{mismatched_last_t}/50")
check("store still bounded by thinning", len(tiny) < 50, f"n={len(tiny)}")

# B20's exact trigger: the cap is sized so the FIRST thinning pass fires
# right as the 4th frame lands (len jumps 3 -> 4, an even length). The
# old `frames[::2]` thinning dropped index len-1 (the frame just
# accepted) whenever the pre-thin length was even.
one_frame_bytes = np.zeros(4, np.float32).nbytes
even = FrameStore(mem_cap=3 * one_frame_bytes + 1)   # room for exactly 3
for k in range(4):     # force every offer so all 4 are accepted
    kept = even.append(float(k), dict(p=np.zeros(4, np.float32)), force=True)
    check(f"forced append #{k} (len={len(even)}) reports itself present",
          kept and even.times[-1] == float(k), f"times={even.times}")


# ── T6: build_payload optional fields ────────────────────────────────────────
print("\nT6: build_payload extra fields")
from blastlab.viz3d.sampling import build_payload

full = np.random.rand(10, 10, 10)
pay = build_payload(dict(p=full), stride=2, face_specs=[])
check("p only -> p + loads", set(pay) == {'p', 'loads'})
check("p decimated", pay['p'].shape == (5, 5, 5)
      and pay['p'].dtype == np.float32)
pay = build_payload(dict(p=full, rho=full, e=full, p_peak=full,
                         imp=full), stride=2, face_specs=[])
check("all extras decimated",
      set(pay) == {'p', 'loads', 'rho', 'e', 'p_peak', 'imp'}
      and all(pay[k].shape == (5, 5, 5) for k in
              ('rho', 'e', 'p_peak', 'imp')))
pay = build_payload(dict(p=full, rho=None), stride=1, face_specs=[])
check("None extras skipped", 'rho' not in pay)

# ── Summary ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 50)
if FAIL:
    print(f"FAILED: {len(FAIL)} check(s): {FAIL}")
    sys.exit(1)
print("All viz3d sampling checks passed.")
