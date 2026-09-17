"""Parent <-> viewer-process protocol: the shared-memory frame ring and
the control-message vocabulary. No pyvista/VTK/Qt imports - this module
runs on the solver side (GUI or CLI process) and inside the viewer child.

Frames never travel through a pipe. The producer (solver thread) writes
each decimated payload into one of two slots of a shared-memory segment
and bumps a global sequence number; the viewer copies the newest slot
out on its own timer. Latest wins: a slow viewer simply skips frames,
and the producer never blocks. A seqlock stamp per slot detects a copy
torn by the producer lapping the reader.

Slot layout (bytes):
    header  24   seq i64 | t f64 | final u8 | mask u8 | levels u8 | pad
    fields       one float32 block per FIELD_KEYS entry, decimated shape
    loads        one float32 block per obstacle face (FaceSpec lo/hi)
    levels       optional int8 block on the FULL display grid (dynamic AMR)
The segment is [global seq i64][slot 0][slot 1].

Control messages are small tuples over a duplex Pipe; every message names
its surface ('run' | 'results' | 'setup'), see `viewer.viewer_main`.
"""

import math
from multiprocessing import shared_memory

import numpy as np

from .sampling import EXTRA_FIELDS

#: the three 3D surfaces a GUI hosts; the CLI uses 'run' only
SURFACES = ('run', 'results', 'setup')

#: volume fields a frame may carry, in slot order (bit i of `mask`)
FIELD_KEYS = ('p',) + tuple(EXTRA_FIELDS)

_HDR = np.dtype([('seq', '<i8'), ('t', '<f8'), ('final', 'u1'),
                 ('mask', 'u1'), ('levels', 'u1'), ('_pad', 'u1', (5,))])
assert _HDR.itemsize == 24

#: slot stamp while the producer is mid-write (seqlock)
_WRITING = -1


def _align8(n):
    return (n + 7) & ~7


class FrameLayout:
    """Byte map of one frame slot, derived from the scene init (the
    decimated grid shape and the obstacle faces). Plain data, picklable:
    the parent builds it, the child attaches with the same object."""

    def __init__(self, dshape, faces, full_shape=None):
        self.dshape = tuple(int(v) for v in dshape)
        self.faces = [(str(fid), (int(a), int(b))) for fid, (a, b) in faces]
        self.full_shape = (tuple(int(v) for v in full_shape)
                           if full_shape else None)
        n = int(math.prod(self.dshape))
        off = _HDR.itemsize
        self.field_off = {}
        for key in FIELD_KEYS:
            self.field_off[key] = off
            off += n * 4
        self.face_off = {}
        for fid, shp in self.faces:
            self.face_off[fid] = off
            off += int(math.prod(shp)) * 4
        self.levels_off = None
        if self.full_shape:
            self.levels_off = off
            off += int(math.prod(self.full_shape))
        self.slot_bytes = _align8(off)
        self.total_bytes = 8 + 2 * self.slot_bytes

    @classmethod
    def from_init(cls, init, with_levels=False):
        """From a `sampling.build_scene_init` init dict. `with_levels`
        reserves the int8 level-map block (dynamic-AMR runs only: it is
        the full display grid, the largest block of the slot)."""
        dshape = np.asarray(init['solid_dec']).shape
        faces = [(s.face_id, (s.hi[0] - s.lo[0], s.hi[1] - s.lo[1]))
                 for s in init['face_specs']]
        full = None
        if with_levels:
            full = (len(init['x_c']), len(init['y_c']), len(init['z_c']))
        return cls(dshape, faces, full)

    def __repr__(self):
        return (f'FrameLayout(dshape={self.dshape}, faces={len(self.faces)}, '
                f'levels={self.full_shape}, slot={self.slot_bytes} B)')


class SharedFrameRing:
    """Two-slot latest-wins frame exchange in shared memory.

    Producer side: `SharedFrameRing(layout)` creates the segment (pass
    its `name` to the viewer), `write(t, payload, final)` publishes one
    `sampling.build_payload`-shaped dict. Consumer side:
    `SharedFrameRing(layout, name=..., create=False)` attaches,
    `read(last_seq)` returns the newest frame newer than `last_seq` as
    `(seq, t, payload, final)` or None. `final` is sticky once set, so a
    run-ending frame's flag survives being overwritten before it is read.
    """

    def __init__(self, layout, name=None, create=True):
        self.layout = layout
        self._shm = shared_memory.SharedMemory(
            name=name, create=create, size=layout.total_bytes)
        self._buf = self._shm.buf
        self._gseq = np.ndarray((1,), '<i8', self._buf, 0)
        self._slots = [self._views(k) for k in (0, 1)]
        if create:
            self._gseq[0] = 0
            for hdr, _f, _l, _lv in self._slots:
                hdr[0] = (0, 0.0, 0, 0, 0, (0,) * 5)
        self._final = False
        self._closed = False

    # ── views ────────────────────────────────────────────────────────────
    @property
    def name(self):
        return self._shm.name

    def _views(self, k):
        lay = self.layout
        base = 8 + k * lay.slot_bytes
        hdr = np.ndarray((1,), _HDR, self._buf, base)
        fields = {key: np.ndarray(lay.dshape, '<f4', self._buf, base + off)
                  for key, off in lay.field_off.items()}
        loads = {fid: np.ndarray(shp, '<f4', self._buf,
                                 base + lay.face_off[fid])
                 for fid, shp in lay.faces}
        levels = None
        if lay.levels_off is not None:
            levels = np.ndarray(lay.full_shape, np.int8, self._buf,
                                base + lay.levels_off)
        return hdr, fields, loads, levels

    # ── producer ─────────────────────────────────────────────────────────
    def write(self, t, payload, final=False):
        """Publish one frame; returns its sequence number. Arrays are
        copied in place, so `payload` may be discarded afterwards. A
        field whose shape does not match the layout is skipped (the mask
        says what landed)."""
        if self._closed:
            return 0
        seq = int(self._gseq[0]) + 1
        hdr, fields, loads, levels = self._slots[seq % 2]
        hdr['seq'][0] = _WRITING
        mask = 0
        for i, key in enumerate(FIELD_KEYS):
            arr = payload.get(key)
            if arr is None:
                continue
            arr = np.asarray(arr)
            if arr.shape != fields[key].shape:
                continue
            np.copyto(fields[key], arr, casting='unsafe')
            mask |= 1 << i
        have_loads = payload.get('loads') or {}
        for fid, view in loads.items():
            arr = have_loads.get(fid)
            if arr is not None and np.shape(arr) == view.shape:
                np.copyto(view, arr, casting='unsafe')
            else:
                view.fill(np.nan)
        has_levels = 0
        lv = payload.get('levels')
        if lv is not None and levels is not None \
                and np.shape(lv) == levels.shape:
            np.copyto(levels, lv, casting='unsafe')
            has_levels = 1
        self._final = bool(final) or self._final
        hdr['t'][0] = float(t)
        hdr['final'][0] = 1 if self._final else 0
        hdr['mask'][0] = mask
        hdr['levels'][0] = has_levels
        hdr['seq'][0] = seq            # slot complete ...
        self._gseq[0] = seq            # ... then publish
        return seq

    # ── consumer ─────────────────────────────────────────────────────────
    def read(self, last_seq=0):
        """Newest frame newer than `last_seq` as (seq, t, payload, final),
        or None. A copy torn by the producer lapping this reader is
        detected by the slot stamp and retried once."""
        if self._closed:
            return None
        for _attempt in range(3):
            seq = int(self._gseq[0])
            if seq <= last_seq:
                return None
            hdr, fields, loads, levels = self._slots[seq % 2]
            if int(hdr['seq'][0]) != seq:
                continue                      # mid-write: try again
            t = float(hdr['t'][0])
            final = bool(hdr['final'][0])
            mask = int(hdr['mask'][0])
            has_lv = bool(hdr['levels'][0])
            payload = {key: fields[key].copy()
                       for i, key in enumerate(FIELD_KEYS) if mask & (1 << i)}
            payload['loads'] = {fid: v.copy() for fid, v in loads.items()}
            if has_lv and levels is not None:
                payload['levels'] = levels.copy()
            if int(hdr['seq'][0]) != seq:
                continue                      # lapped during the copy
            return seq, t, payload, final
        return None

    @property
    def seq(self):
        return int(self._gseq[0]) if not self._closed else 0

    # ── lifetime ─────────────────────────────────────────────────────────
    def close(self, unlink=False):
        """Drop this process's mapping; `unlink` (creator only) releases
        the name. On Windows the segment lives while any process holds a
        handle, so a viewer that outlives its parent keeps its frames."""
        if self._closed:
            return
        self._closed = True
        self._slots = []
        self._gseq = None
        self._buf = None
        try:
            self._shm.close()
        except Exception:
            pass
        if unlink:
            try:
                self._shm.unlink()
            except Exception:
                pass

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
