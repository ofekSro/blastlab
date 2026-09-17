"""viz3d.protocol: the shared-memory frame ring between the solver side
and the viewer child. In-process (creator + attached reader), no
pyvista, no Qt, no child process."""
import os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core.constants import P_AIR
from blastlab.core.grid import make_grid
from blastlab.core.bc import solid_mask_3d
from blastlab.viz3d.sampling import build_payload, build_scene_init
from blastlab.viz3d.protocol import (FIELD_KEYS, FrameLayout,
                                     SharedFrameRing, _WRITING)

FAIL = []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        FAIL.append(name)


def scene():
    grid = make_grid(2.0, 2.0, 2.0, 0.1)              # 20^3
    x_c, y_c, z_c = grid['x_c'], grid['y_c'], grid['z_c']
    obstacles = [(1.2, 1.6, 0.6, 1.2, 0.0, 0.7)]
    solid = solid_mask_3d(x_c, y_c, z_c, obstacles)
    return dict(x_c=x_c, y_c=y_c, z_c=z_c, dx=0.1, solid=solid,
                obstacles=obstacles, Lx=2.0, Ly=2.0, Lz=2.0,
                charge_center=(0.7, 1.0, 0.5), r_exp=0.15,
                bcs=dict(x_lo='terminate', x_hi='terminate',
                         y_lo='terminate', y_hi='terminate',
                         z_lo='reflect', z_hi='terminate'))


def main():
    print("\nR1: layout from a scene init")
    info = scene()
    init, stride, specs = build_scene_init(info, max_dim=16)   # stride 2
    lay = FrameLayout.from_init(init, with_levels=True)
    check("stride 2 -> 10^3 display grid", lay.dshape == (10, 10, 10),
          str(lay.dshape))
    check("one block per obstacle face + ground",
          len(lay.faces) == len(specs) and 'ground' in lay.face_off)
    check("levels block on the full grid", lay.full_shape == (20, 20, 20))
    n = 1000 * 4 * len(FIELD_KEYS)
    check("slot holds header + fields + faces + levels",
          lay.slot_bytes >= 24 + n + 20 ** 3 and lay.slot_bytes % 8 == 0,
          f"{lay.slot_bytes} B")
    lay2 = FrameLayout.from_init(init, with_levels=False)
    check("no levels block unless asked", lay2.levels_off is None
          and lay2.slot_bytes < lay.slot_bytes)

    print("\nR2: write / read round trip through an attached reader")
    ring = SharedFrameRing(lay)
    reader = SharedFrameRing(lay, name=ring.name, create=False)
    check("fresh ring has no frame", reader.read(0) is None)
    X, Y, Z = np.meshgrid(info['x_c'], info['y_c'], info['z_c'],
                          indexing='ij')
    p = P_AIR + 1e5 * np.exp(-((X - 0.7) ** 2 + (Y - 1.0) ** 2
                               + (Z - 0.5) ** 2) / 0.1)
    rho = 1.2 + p / 3e5
    levels = np.random.RandomState(0).randint(0, 3, size=(20, 20, 20)) \
        .astype(np.int8)
    payload = build_payload(dict(p=p, rho=rho, levels=levels), stride, specs)
    seq = ring.write(1.5e-4, payload)
    got = reader.read(0)
    check("one frame published", seq == 1 and got is not None
          and got[0] == 1, str(seq))
    _s, t, back, final = got
    check("time carried", abs(t - 1.5e-4) < 1e-15, str(t))
    check("p round-trips exactly",
          np.array_equal(back['p'], payload['p'])
          and back['p'].dtype == np.float32)
    check("rho round-trips", np.array_equal(back['rho'], payload['rho']))
    check("fields absent from the frame are absent from the read",
          'e' not in back and 'p_peak' not in back and 'imp' not in back)
    check("levels round-trip", np.array_equal(back['levels'], levels))
    check("loads round-trip (NaN where buried preserved)",
          set(back['loads']) == set(payload['loads']) and all(
              np.array_equal(back['loads'][k], payload['loads'][k],
                             equal_nan=True) for k in payload['loads']))
    check("not final", final is False)
    check("nothing newer than seq 1", reader.read(1) is None)
    check("the read is a copy (mutating it leaves the slot alone)",
          (back['p'].__setitem__((0, 0, 0), -1.0) or True)
          and reader.read(0)[2]['p'][0, 0, 0] == payload['p'][0, 0, 0])

    print("\nR3: latest wins, sticky final, fields may come and go")
    ring.write(2.0e-4, build_payload(dict(p=p * 1.01), stride, specs))
    ring.write(3.0e-4, build_payload(dict(p=p * 1.02, e=rho), stride, specs),
               final=True)
    got = reader.read(1)
    check("reader skips straight to the newest frame",
          got is not None and got[0] == 3 and abs(got[1] - 3e-4) < 1e-15)
    check("final flag carried", got[3] is True)
    check("e present, rho absent this frame",
          'e' in got[2] and 'rho' not in got[2])
    ring.write(4.0e-4, build_payload(dict(p=p), stride, specs))
    got = reader.read(3)
    check("final is sticky on later frames", got is not None and got[3])

    print("\nR4: a torn slot is never returned")
    hdr = ring._slots[ring.seq % 2][0]
    stamp = int(hdr['seq'][0])
    hdr['seq'][0] = _WRITING
    check("mid-write slot -> None", reader.read(0) is None)
    hdr['seq'][0] = stamp
    check("restored slot readable again", reader.read(0) is not None)

    print("\nR5: shape guard + lifetime")
    bad = build_payload(dict(p=p), 1, specs)          # wrong shape (stride 1)
    seq_before = ring.seq
    ring.write(5.0e-4, bad)
    got = reader.read(seq_before)
    check("mismatched field skipped, frame still published",
          got is not None and 'p' not in got[2])
    reader.close()
    ring.close(unlink=True)
    check("closed ring reads None / writes 0",
          ring.read(0) is None and ring.write(0.0, {}) == 0)

    print("\nR6: the parent side stays VTK/Qt-free")
    import blastlab.viz3d.process   # noqa: F401
    import blastlab.viz3d.client    # noqa: F401
    check("no pyvista/vtk/PySide6 imported by protocol/process/client",
          not any(m.split('.')[0] in ('pyvista', 'vtk', 'vtkmodules',
                                      'PySide6', 'pyvistaqt')
                  for m in sys.modules))

    print("\n" + "=" * 50)
    if FAIL:
        print(f"FAILED: {len(FAIL)} check(s): {FAIL}")
        sys.exit(1)
    print("All viz3d protocol checks passed.")


if __name__ == '__main__':
    main()
