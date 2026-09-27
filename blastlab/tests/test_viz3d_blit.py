"""Tk blit cost (P3-7): headless, the Tk root stays withdrawn.

VtkTkHost._blit renders once and builds the PPM from two buffers (the
screenshot and the PPM bytes). Cap per blit, owner decision 2026-09-27:
tracemalloc peak <= 2 * img.nbytes + 64 KiB (a fixed allowance for the
size-independent overhead of pyvista's screenshot; Tk accepts only bytes,
so two full buffers are the floor). Renders per blit == 1.
"""
import os, sys, tracemalloc
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

import tkinter as tk
import pyvista as pv
from blastlab.gui.vtk_host import VtkTkHost

FAIL = []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        FAIL.append(name)


print("\nB1: one render and two buffers per blit (P3-7)")
root = tk.Tk()
root.withdraw()                 # never shown: the desktop is not ours
host = VtkTkHost(root, log_fn=print, view_size=(760, 560))
host.pack()
pl = host._make_plotter()
pl.add_mesh(pv.Sphere(), color='orange')
pl.add_mesh(pv.Cube(center=(1.5, 0, 0)), color='steelblue')
host._scene = object()
pl.render()
pl.screenshot(return_img=True)              # warm-up: first-time render
n = [0]
pl.render_window.AddObserver('RenderEvent',
                             lambda *_: n.__setitem__(0, n[0] + 1))
w, h = pl.window_size
nbytes = w * h * 3
cap = 2 * nbytes + 64 * 1024
for k in range(3):
    n[0] = 0
    tracemalloc.start()
    tracemalloc.reset_peak()
    b0 = tracemalloc.get_traced_memory()[0]
    host._blit()
    peak = tracemalloc.get_traced_memory()[1] - b0
    tracemalloc.stop()
    check(f"blit {k}: exactly 1 render", n[0] == 1, f"({n[0]})")
    check(f"blit {k}: peak <= 2 x img.nbytes + 64 KiB",
          peak <= cap, f"({peak / 1e6:.4f} MB = {peak / nbytes:.4f} x "
          f"{nbytes / 1e6:.3f} MB; cap {cap / 1e6:.4f} MB; was 3.00x)")

print("\nB2: the PPM is the screenshot, pixel for pixel")
ref = pl.screenshot(return_img=True)        # no render in between
photo = host._photo
check("photo size matches the window",
      (photo.width(), photo.height()) == (w, h),
      f"{photo.width()}x{photo.height()}")
pts = [(0, 0), (w - 1, h - 1), (w // 2, h // 2), (w // 3, h // 4),
       (2 * w // 3, 3 * h // 4)]
same = all(tuple(photo.get(x, y)) == tuple(int(c) for c in ref[y, x, :3])
           for x, y in pts)
check("sampled pixels equal the screenshot", same)

print("\nB3: a camera move reaches the next blit")
pl.camera.azimuth = 40
host._blit()
img_b = pl.screenshot(return_img=True)
check("blit is not stale", not np.array_equal(ref, img_b))

root.destroy()
pl.close()
print("\n" + "=" * 50)
if FAIL:
    print(f"FAILED: {len(FAIL)} check(s): {FAIL}")
    sys.exit(1)
print("All viz3d blit checks passed.")
