"""End-to-end IPC test: spawns the REAL viewer process (a window opens
briefly on screen), streams synthetic frames, then closes it. Verifies
the spawn/queue path works on Windows and that close() reaps the child."""
import os, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core.constants import P_AIR
from blastlab.core.grid import make_grid
from blastlab.core.bc import solid_mask_3d

FAIL = []

def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        FAIL.append(name)


def main():
    from blastlab.viz3d.client import Viewer3DClient

    grid = make_grid(4.0, 4.0, 4.0, 0.05)          # 80^3 full-res
    x_c, y_c, z_c = grid['x_c'], grid['y_c'], grid['z_c']
    obstacles = [(2.5, 3.0, 1.5, 2.5, 0.0, 1.0)]
    solid = solid_mask_3d(x_c, y_c, z_c, obstacles)
    center = (1.5, 2.0, 1.0)
    scene = dict(x_c=x_c, y_c=y_c, z_c=z_c, dx=0.05, solid=solid,
                 obstacles=obstacles, Lx=4.0, Ly=4.0, Lz=4.0,
                 charge_center=center, r_exp=0.15,
                 bcs=dict(x_lo='terminate', x_hi='terminate', y_lo='terminate',
                          y_hi='terminate', z_lo='reflect', z_hi='terminate'))

    print("\nE1: spawn viewer process")
    t0 = time.time()
    client = Viewer3DClient(scene, min_interval=0.05)
    check("child alive", client.alive)
    print(f"    spawn + init took {time.time() - t0:.1f} s")

    print("\nE2: stream synthetic frames")
    X, Y, Z = np.meshgrid(x_c, y_c, z_c, indexing='ij')
    d = np.sqrt((X - center[0])**2 + (Y - center[1])**2
                + (Z - center[2])**2)
    sent = 0
    t0 = time.time()
    for k in range(40):
        r = 0.2 + 0.06 * k
        p = P_AIR + 4e5 * np.exp(-((d - r) / 0.25)**2) + 1e5 * (d < r)
        p[solid] = P_AIR
        client.send_frame(k * 1e-4, dict(p=p, rho=1.2 + p / 3e5))
        sent += 1
        time.sleep(0.08)
    dt = time.time() - t0
    check("still alive after stream", client.alive)
    check("sender never blocked", dt < 8.0, f"{dt:.1f} s for {sent} sends")

    print("\nE3: finish -> playback, then close")
    client.finish('synthetic stream ended')
    time.sleep(2.0)
    check("alive in playback", client.alive)
    client.close()
    time.sleep(0.5)
    check("child reaped after close", not client.alive)

    print("\n" + "=" * 50)
    if FAIL:
        print(f"FAILED: {len(FAIL)} check(s): {FAIL}")
        sys.exit(1)
    print("All viz3d end-to-end checks passed.")


if __name__ == '__main__':   # spawn-safe: child re-imports this module
    main()
