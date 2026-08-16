"""One-shot check: real solver run streaming to a real viewer window,
then playback and close (the GUI live path without the GUI)."""
import sys, time

sys.path.insert(0, r'c:\Users\rotem.ofek\Projects\BlastFoam')


def main():
    from blastlab.solvers.solver3d import _run_blast_3d
    from blastlab.solvers.hooks import RunHooks
    from blastlab.viz3d.client import Viewer3DClient, attach_on_start

    hooks = attach_on_start(RunHooks())
    res = _run_blast_3d(Lx=3.0, Ly=3.0, Lz=3.0, cell_size_m=0.05,
                        charge=900.0, charge_center=(1.5, 1.5, 1.0),
                        eos='idealGas',
                        obstacles=[(2.2, 2.6, 1.1, 1.9, 0.0, 0.8)],
                        gauges=[(2.8, 1.5, 1.0)], n_snapshots=4,
                        hooks=hooks)
    v = hooks.viewer3d
    assert v is not None and v.alive, "viewer died during the run"
    v.finish(res.stop_reason)
    time.sleep(3.0)
    assert v.alive, "viewer died on entering playback"
    v.close()
    print("SOLVER+VIEWER E2E OK  "
          f"(stop: {res.stop_reason}, snapshots: {len(res.snapshots)})")


if __name__ == '__main__':
    main()
