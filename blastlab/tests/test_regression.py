"""Regression check: rerun the baseline cases and compare against the
frozen pre-refactor outputs in tests/baseline/.

TSV/transcript files must be byte-identical; npz compared array-by-array
(zip metadata makes raw npz bytes unstable).
"""
import filecmp
import os
import shutil
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BASELINE = os.path.join(HERE, 'baseline')


def compare(outdir):
    ok = True
    for name in sorted(os.listdir(BASELINE)):
        ref = os.path.join(BASELINE, name)
        new = os.path.join(outdir, name)
        if not os.path.exists(new):
            print(f"  [FAIL] {name}: missing from new run")
            ok = False
            continue
        if name.endswith('.npz'):
            za, zb = np.load(ref), np.load(new)
            same = (sorted(za.files) == sorted(zb.files)
                    and all(np.array_equal(za[k], zb[k]) for k in za.files))
            print(f"  [{'PASS' if same else 'FAIL'}] {name}: arrays "
                  f"{'equal' if same else 'DIFFER'}")
        else:
            same = filecmp.cmp(ref, new, shallow=False)
            print(f"  [{'PASS' if same else 'FAIL'}] {name}: "
                  f"{'byte-identical' if same else 'BYTES DIFFER'}")
        ok &= same
    return ok


def main():
    import make_baseline
    outdir = tempfile.mkdtemp(prefix='blastlab_regress_')
    try:
        make_baseline.run(outdir)
        print("\nComparing against frozen baseline:")
        ok = compare(outdir)
    finally:
        shutil.rmtree(outdir, ignore_errors=True)
    print("\nREGRESSION:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
