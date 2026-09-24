"""Shared plumbing for the characterisation tests (`test_char_*.py`).

docs/ARCHITECTURE_REVIEW.md section 5, Phase 0. The characterisation
tests pin what the code returns TODAY, correct or not, so that the later
phases (which move code, never change it) can prove they changed nothing.
Their goldens live in `tests/char_golden/` and are written once from the
current code:

    cd blastlab/tests
    python test_char_native_api.py --update     # (re)write its goldens
    python test_char_native_api.py              # compare against them

A golden is NEVER rewritten to make a test pass: a mismatch is a change
in behaviour, and the phase that caused it is the thing to fix.

Importing this module points BLASTLAB_SETTINGS at a private file with
`auto_cleanup: false` (`ui.testing.private_settings`) - validation reads
settings (`mpi_headroom`, `mpi_max_ranks`), so the goldens must not
depend on the user's real settings file, and nothing a test does may
ever sweep the run corpus (CLAUDE.md 8.2).
"""

import difflib
import json
import math
import os
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
os.environ.setdefault('MPLBACKEND', 'Agg')

from blastlab.ui.testing import private_settings     # noqa: E402

private_settings()

GOLDEN = os.path.join(HERE, 'char_golden')

#: set by `main()` when a script is run with --update
UPDATE = False


def plain(obj):
    """`obj` as plain JSON-able Python: numpy scalars and small arrays
    become floats/ints/lists, tuples become lists, dict keys strings."""
    if isinstance(obj, dict):
        return {str(k): plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [plain(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return plain(obj.tolist())
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    return obj


def dumps(obj):
    """The canonical golden text: sorted keys, 2-space indent, LF, and
    floats written by repr (round-trips exactly; NaN as NaN)."""
    return json.dumps(plain(obj), sort_keys=True, indent=2,
                      allow_nan=True) + '\n'


def _path(name):
    return os.path.join(GOLDEN, name)


def _require(name):
    """The golden's path; AssertionError if it has not been written yet."""
    path = _path(name)
    if not os.path.exists(path):
        raise AssertionError(
            f'golden {name} is missing - write it from the current code '
            f'with `python <this test>.py --update`')
    return path


def _read_text(name):
    path = _require(name)
    with open(path, 'rb') as f:
        return f.read().replace(b'\r\n', b'\n').decode('utf-8')


def _write_text(name, text):
    os.makedirs(GOLDEN, exist_ok=True)
    with open(_path(name), 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)


def check_text(name, text):
    """Byte-compare `text` with the golden `name` (CRLF-normalised)."""
    if UPDATE:
        _write_text(name, text)
        return
    want = _read_text(name)
    if text != want:
        diff = ''.join(list(difflib.unified_diff(
            want.splitlines(True), text.splitlines(True),
            'golden/' + name, 'now/' + name))[:60])
        raise AssertionError(f'{name} differs from its golden:\n{diff}')


def check_json(name, obj):
    """Exact comparison of `obj` against the golden `name`, through the
    canonical text (so float values must match to the last bit)."""
    check_text(name, dumps(obj))


def load_json(name):
    return json.loads(_read_text(name))


def check_npz(name, arrays):
    """Every array in `arrays` equal (values, dtype, shape) to the golden
    `name`, and the same set of keys."""
    if UPDATE:
        os.makedirs(GOLDEN, exist_ok=True)
        np.savez(_path(name), **arrays)
        return
    with np.load(_require(name)) as z:
        want = {k: z[k] for k in z.files}
    assert sorted(want) == sorted(arrays), \
        f'{name}: keys {sorted(arrays)} != golden {sorted(want)}'
    for k in sorted(want):
        a, b = np.asarray(arrays[k]), want[k]
        assert a.dtype == b.dtype and a.shape == b.shape, \
            f'{name}[{k}]: {a.dtype}{a.shape} != golden {b.dtype}{b.shape}'
        assert np.array_equal(a, b, equal_nan=a.dtype.kind in 'fc'), \
            f'{name}[{k}]: values differ from the golden'


def load_npz(name):
    with np.load(_path(name)) as z:
        return {k: z[k] for k in z.files}


def approx_equal(got, want, rel):
    """Recursive equality with a relative tolerance on floats (NaN == NaN);
    everything else exact. Returns the first mismatch path, or None."""
    def walk(g, w, where):
        if isinstance(w, dict):
            if not isinstance(g, dict) or sorted(g) != sorted(w):
                return where
            for k in w:
                bad = walk(g[k], w[k], f'{where}.{k}')
                if bad:
                    return bad
            return None
        if isinstance(w, list):
            if not isinstance(g, list) or len(g) != len(w):
                return where
            for i, (a, b) in enumerate(zip(g, w)):
                bad = walk(a, b, f'{where}[{i}]')
                if bad:
                    return bad
            return None
        if isinstance(w, float) and not isinstance(g, bool) \
                and isinstance(g, (int, float)):
            if math.isnan(w):
                return None if math.isnan(g) else where
            if math.isinf(w) or w == 0.0:
                return None if g == w else where
            return None if abs(g - w) <= rel * abs(w) else where
        return None if g == w else where
    return walk(plain(got), plain(want), '$')


def hd13_starter_case():
    """The HD 1.3 starter case exactly as `output/cli_hd13` writes it,
    loaded back through `core.assessment.load_case`."""
    # deferred, so the tests that do not need the HD 1.3 chain never import it
    from blastlab.core import assessment
    from blastlab.output.cli_hd13 import write_starter_case
    with tempfile.TemporaryDirectory(prefix='blastlab_char_') as tmp:
        return assessment.load_case(
            write_starter_case(os.path.join(tmp, 'starter.json')))


def run_main(title, tests):
    """The script half of the dual pytest/script pattern (`test_refine.py`
    style): run every test function, print PASS/FAIL per test and a final
    `<TITLE>: PASS` line, return the exit code. `--update` rewrites the
    goldens from the current code instead of comparing."""
    global UPDATE
    UPDATE = '--update' in sys.argv[1:]
    fails = []
    for fn in tests:
        try:
            fn()
        except AssertionError as exc:
            fails.append(fn.__name__)
            print(f'  [FAIL] {fn.__name__} - {exc}')
        else:
            print(f'  [{"WROTE" if UPDATE else "PASS"}] {fn.__name__}')
    print()
    if UPDATE:
        note = ''
        if fails:
            note = f' ({len(fails)} test(s) failed while writing)'
        print(f'{title}: goldens written to {GOLDEN}{note}')
    elif fails:
        print(f'{title}: FAIL ({len(fails)}): ' + ', '.join(fails))
    else:
        print(f'{title}: PASS')
    return 1 if fails else 0
