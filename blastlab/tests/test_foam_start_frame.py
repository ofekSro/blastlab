"""P1-7: the reader accepts the `);` blastlab's own writer emits.

`writer._nonuniform` + `_render_fields` close a nonuniform internalField
list with `);` on one line (chamber and profile starts). The reader used
to require a bare `)`, so `backend._initial_frame` silently skipped the
t = 0 frame of every chamber and profile stage. Pinned here, with no
WSL: files framed by the writer itself, read back by the reader, and
the t = 0 frame the backend emits from them.

Run:  cd blastlab/tests && python test_foam_start_frame.py
"""
import os
import sys
import tempfile
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from blastlab.solvers.foam import backend, reader, writer        # noqa: E402

FAILS = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAILS.append(name)


def writer_text(name, kind, vals, vector=False):
    """One 0/ file exactly as the writer frames a chamber / profile
    start: `_render_fields(_nonuniform(...))`."""
    spec = SimpleNamespace(patches=[('x_lo', 'transmit')], l_inf=1.0)
    fields = {f'0/{name}': (name, kind, writer._nonuniform(vals,
                                                            vector=vector),
                            vector)}
    return writer._render_fields(fields, spec)[f'0/{name}']


def put(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='ascii', newline='\n') as f:
        f.write(text)


class Hooks:
    """Records `frame(field, t)` calls, as the live view would get them."""

    def __init__(self):
        self.frames = []

    def frame(self, field, t):
        self.frames.append((np.array(field, copy=True), t))


P = [101325.0, 2.0e5, 3.5e5, 1.25e5, 101325.0, 4.0e5]
U = [(1.0, 2.0, 3.0), (0.0, 0.0, 0.0), (-4.0, 5.0, 6.5),
     (0.5, -0.25, 0.0), (7.0, 0.0, -1.0), (0.0, 0.0, 9.0)]


def test_read_writer_framing():
    print("\n(a, b) the writer's `);` framing reads back")
    p_text = writer_text('p', 'p', P)
    u_text = writer_text('U', 'U', U, vector=True)
    check('the writer closes the list with ");" on one line',
          '\n);\n' in p_text and '\n);\n' in u_text)
    with tempfile.TemporaryDirectory() as d:
        put(os.path.join(d, 'p'), p_text)
        put(os.path.join(d, 'U'), u_text)
        got = reader.read_scalar(os.path.join(d, 'p'), len(P))
        check('(a) scalar reads back exactly', np.array_equal(got, P),
              str(got))
        got = reader.read_vector(os.path.join(d, 'U'), len(U))
        check('(a) vector reads back exactly', np.array_equal(got, U),
              str(got))
        check('(b) scalar_size returns the count',
              reader.scalar_size(os.path.join(d, 'p')) == len(P))


def test_torn_still_refused():
    print('\n(d) a torn file is still refused')
    text = writer_text('p', 'p', P)
    torn = text.replace('\n);\n', '\n', 1)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, 'p')
        put(path, torn)
        for what, fn in (('read_scalar', lambda: reader.read_scalar(
                              path, len(P))),
                         ('scalar_size', lambda: reader.scalar_size(path))):
            try:
                fn()
                check(f'(d) {what}: no ");" line raises', False)
            except ValueError as exc:
                check(f'(d) {what}: no ");" line raises "unterminated"',
                      'unterminated' in str(exc), str(exc))


def test_initial_frame_profile_1d():
    print('\n(c) t = 0 frame of a 1D profile start')
    r = np.array([0.05, 0.15, 0.25, 0.35, 0.45, 0.55])
    with tempfile.TemporaryDirectory() as case:
        spec = SimpleNamespace(case_unc=case, start_dir='0.000125',
                               n_cells=len(P), t_start=0.000125, dim=1,
                               grid=dict(r=r), mesh0=None, remap=None,
                               solid=None)
        put(os.path.join(case, spec.start_dir, 'p'),
            writer_text('p', 'p', P))
        hooks = Hooks()
        backend._initial_frame(spec, hooks)
        check('(c) exactly one frame', len(hooks.frames) == 1,
              str(len(hooks.frames)))
        if hooks.frames:
            field, t = hooks.frames[0]
            check('(c) at spec.t_start', t == spec.t_start, str(t))
            check('(c) [r, p] as written',
                  np.array_equal(field, np.array([r, P])), str(field))


def test_initial_frame_chamber_2d():
    print('\n(c) t = 0 frame of a 2D chamber start')
    nx, ny = 3, 2
    with tempfile.TemporaryDirectory() as case:
        spec = SimpleNamespace(case_unc=case, start_dir='0',
                               n_cells=nx * ny, t_start=0.0, dim=2,
                               nx=nx, ny=ny,
                               grid=dict(x_c=np.arange(nx) + 0.5,
                                         y_c=np.arange(ny) + 0.5),
                               mesh0=None, remap=None, solid=None)
        put(os.path.join(case, '0', 'p'), writer_text('p', 'p', P))
        hooks = Hooks()
        backend._initial_frame(spec, hooks)
        check('(c) exactly one frame', len(hooks.frames) == 1,
              str(len(hooks.frames)))
        if hooks.frames:
            field, t = hooks.frames[0]
            want = np.array(P).reshape((nx, ny), order='F')
            check('(c) at spec.t_start', t == spec.t_start, str(t))
            check('(c) the grid as written (x fastest)',
                  np.array_equal(field, want), str(field))


TESTS = [test_read_writer_framing, test_torn_still_refused,
         test_initial_frame_profile_1d, test_initial_frame_chamber_2d]


if __name__ == '__main__':
    for fn in TESTS:
        fn()
    print()
    print('FOAM START FRAME: ' + ('PASS' if not FAILS else
                                  f'FAIL ({len(FAILS)}): ' + ', '.join(FAILS)))
    sys.exit(1 if FAILS else 0)
