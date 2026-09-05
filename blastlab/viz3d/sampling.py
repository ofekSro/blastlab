"""Pure-NumPy helpers for the 3D viewer: field decimation, obstacle
face-load extraction and the playback frame store.

Nothing here imports pyvista or multiprocessing, so it is unit-testable
and safe to use on the solver side.
"""

from dataclasses import dataclass

import numpy as np

MAX_VIEW_DIM = 128          # decimate fields so no axis exceeds this
FRAME_MEM_CAP = 1.5e9       # playback history budget [bytes]


def choose_stride(shape, max_dim=MAX_VIEW_DIM):
    """Smallest stride that brings every axis of `shape` to <= max_dim."""
    return max(1, int(np.ceil(max(shape) / max_dim)))


def decimate(arr, stride):
    """Strided float32 copy (C-contiguous) of a 3D field."""
    return np.ascontiguousarray(arr[::stride, ::stride, ::stride],
                                dtype=np.float32)


@dataclass
class FaceSpec:
    """One exposed obstacle face (or the ground plane): where to sample
    the adjacent-fluid pressure and where the face sits in space.

    axis  : normal axis (0=x, 1=y, 2=z)
    side  : +1 if the fluid lies on the +axis side of the face, else -1
    layer : index along `axis` of the adjacent fluid cell layer
    lo/hi : [lo, hi) index ranges on the two tangential axes (ascending
            axis order), matching the shape of the extracted load array
    plane : world coordinate of the face along `axis` (cell-edge aligned)
    buried: bool (n0, n1) - True where the sampled cell is itself solid
            (face buried in another box); painted as no-data
    """
    face_id: str
    axis: int
    side: int
    layer: int
    lo: tuple
    hi: tuple
    plane: float
    buried: np.ndarray


def _layer_slice(spec):
    """Index tuple selecting the adjacent-fluid layer of a 3D field."""
    sl = [slice(spec.lo[0], spec.hi[0]), slice(spec.lo[1], spec.hi[1])]
    sl.insert(spec.axis, spec.layer)
    return tuple(sl)


def build_face_index(obstacles, x_c, y_c, z_c, solid, bcs):
    """Precompute FaceSpecs for every exposed box face, plus the ground
    plane when z_lo is a wall. Faces flush with a domain boundary or
    completely buried inside other boxes are dropped."""
    coords = (np.asarray(x_c), np.asarray(y_c), np.asarray(z_c))
    dx = float(coords[0][1] - coords[0][0]) if len(coords[0]) > 1 else 0.0
    specs = []

    for b, box in enumerate(obstacles or []):
        bounds = ((box[0], box[1]), (box[2], box[3]), (box[4], box[5]))
        for axis in range(3):
            c = coords[axis]
            for side, name in ((-1, 'lo'), (+1, 'hi')):
                plane_geom = bounds[axis][1] if side > 0 else bounds[axis][0]
                if side > 0:   # first cell centre strictly beyond the box
                    layer = int(np.searchsorted(c, plane_geom, 'right'))
                    if layer >= len(c):
                        continue
                else:          # last cell centre strictly before the box
                    layer = int(np.searchsorted(c, plane_geom, 'left')) - 1
                    if layer < 0:
                        continue
                t_axes = [a for a in range(3) if a != axis]
                lo, hi = [], []
                for ta in t_axes:
                    tc = coords[ta]
                    lo.append(int(np.searchsorted(tc, bounds[ta][0], 'left')))
                    hi.append(int(np.searchsorted(tc, bounds[ta][1], 'right')))
                if hi[0] <= lo[0] or hi[1] <= lo[1]:
                    continue
                spec = FaceSpec(
                    face_id=f'box{b}:{"xyz"[axis]}_{name}',
                    axis=axis, side=side, layer=layer,
                    lo=tuple(lo), hi=tuple(hi),
                    plane=float(c[layer] - side * 0.5 * dx),
                    buried=np.zeros((hi[0] - lo[0], hi[1] - lo[1]), bool))
                spec.buried = solid[_layer_slice(spec)].copy()
                if spec.buried.all():
                    continue
                specs.append(spec)

    if (bcs or {}).get('z_lo') == 'wall':
        Nx, Ny = len(coords[0]), len(coords[1])
        specs.append(FaceSpec(
            face_id='ground', axis=2, side=+1, layer=0,
            lo=(0, 0), hi=(Nx, Ny), plane=0.0,
            buried=solid[:, :, 0].copy()))
    return specs


def extract_loads(p, face_specs):
    """Per-frame face loading: adjacent-fluid pressure [Pa] per face,
    NaN where the face is buried. Full solver resolution, tiny arrays."""
    loads = {}
    for spec in face_specs:
        arr = np.asarray(p[_layer_slice(spec)], dtype=np.float32).copy()
        if spec.buried.any():
            arr[spec.buried] = np.nan
        loads[spec.face_id] = arr
    return loads


# Optional per-frame volume fields a viewer payload may carry besides
# pressure: density, specific internal energy, running peak pressure
# and accumulated overpressure impulse.
EXTRA_FIELDS = ('rho', 'e', 'p_peak', 'imp')


def build_payload(fields, stride, face_specs):
    """One viewer frame from full-resolution solver fields: decimated
    pressure (+ any EXTRA_FIELDS present) and per-face load arrays.
    Values are copied; the solver arrays are never retained."""
    p = np.asarray(fields['p'])
    payload = dict(p=decimate(p, stride),
                   loads=extract_loads(p, face_specs))
    for key in EXTRA_FIELDS:
        arr = fields.get(key)
        if arr is not None:
            payload[key] = decimate(np.asarray(arr), stride)
    return payload


def build_scene_init(scene_info, max_dim=MAX_VIEW_DIM):
    """Precompute everything a viewer scene needs from the solver's
    `scene3d` payload (or a Result meta via client.scene_from_meta).
    Returns (init_dict, stride, face_specs)."""
    solid = np.asarray(scene_info['solid'])
    stride = choose_stride(solid.shape, max_dim)
    face_specs = build_face_index(
        scene_info['obstacles'], scene_info['x_c'], scene_info['y_c'],
        scene_info['z_c'], solid, scene_info['bcs'])
    init = dict(
        stride=stride,
        x_c=np.asarray(scene_info['x_c']),
        y_c=np.asarray(scene_info['y_c']),
        z_c=np.asarray(scene_info['z_c']),
        dx=float(scene_info['dx']),
        solid_dec=decimate(solid.astype(np.float32), stride) > 0.5,
        obstacles=[tuple(o) for o in scene_info['obstacles'] or []],
        Lx=float(scene_info['Lx']), Ly=float(scene_info['Ly']),
        Lz=float(scene_info['Lz']),
        charge_center=tuple(scene_info['charge_center']),
        r_exp=float(scene_info.get('r_exp') or 0.0),
        cyl=scene_info.get('cyl'),
        rings=[tuple(o) for o in scene_info.get('rings') or []],
        bcs=dict(scene_info['bcs']),
        face_specs=face_specs,
        refine=scene_info.get('refine'),   # local refinement record or None
    )
    return init, stride, face_specs


class Revolver:
    """Revolve a live axisymmetric (r, z) field into a Cartesian 3D
    block so the regular 3D viewer can show the cylinder it represents.

    Built once per run from the solver's `revolve3d` info (uniform 2D
    grid: r_c/z_c cell centres, solid mask, 2D bcs, burst height z0,
    r_exp, radius R = Lx, height Lz = Ly). Precomputes nearest-
    neighbour lookup tables onto a uniform cubic grid (equal spacing on
    all axes, as the viewer's ImageData requires; max_dim-capped), so
    `revolve` is a single fancy-indexing gather per frame. Cells beyond
    the outer radius clamp to the outermost ring (ambient while the
    outer boundary is quiet). `scene3d` is a standard scene_info dict,
    so the whole Feed3D / BlastScene pipeline is reused unchanged: the
    symmetry axis lands at the domain centre (R, R), the 2D y axis
    becomes 3D z (y_lo = 'wall' gives the ground plane + its loads).
    Read-only after construction - safe to use on the solver thread."""

    def __init__(self, info, max_dim=MAX_VIEW_DIM):
        r_c = np.asarray(info['r_c'], dtype=np.float64)
        z_c = np.asarray(info['z_c'], dtype=np.float64)
        R, Lz = float(info['R']), float(info['Lz'])
        self._shape2d = (len(r_c), len(z_c))
        dr = float(r_c[1] - r_c[0]) if len(r_c) > 1 else R
        dz = float(z_c[1] - z_c[0]) if len(z_c) > 1 else Lz
        dx = max(max(2.0 * R, Lz) / float(max_dim), min(dr, dz))
        n_xy = max(2, int(np.ceil(2.0 * R / dx)))
        n_z = max(2, int(np.ceil(Lz / dx)))
        x_c = (np.arange(n_xy) + 0.5) * dx
        z3_c = (np.arange(n_z) + 0.5) * dx
        rr = np.hypot(x_c[:, None] - R, x_c[None, :] - R)
        self._ri = np.clip(np.rint((rr - r_c[0]) / dr).astype(np.intp),
                           0, len(r_c) - 1)
        self._zi = np.clip(np.rint((z3_c - z_c[0]) / dz).astype(np.intp),
                           0, len(z_c) - 1)
        bcs2 = dict(info.get('bcs') or {})
        side = bcs2.get('x_hi', 'open')
        # box corners beyond the outer radius are not part of the
        # domain: marked solid so face loads blank there, and the `cyl`
        # entry lets the viewer draw/clip a true cylinder
        solid3 = self.revolve(np.asarray(info['solid'], dtype=bool))
        solid3 |= (rr > R)[:, :, None]
        self.scene3d = dict(
            x_c=x_c, y_c=x_c.copy(), z_c=z3_c, dx=float(dx),
            solid=solid3,
            obstacles=[],
            # (r0, r1, z0, z1) source-plane rectangles: the viewer
            # renders each as a revolved annular ring
            rings=[tuple(float(v) for v in o)
                   for o in info.get('obstacles') or []],
            Lx=2.0 * R, Ly=2.0 * R, Lz=Lz,
            charge_center=(R, R, float(info['z0'])),
            r_exp=float(info.get('r_exp') or 0.0),
            cyl=dict(cx=R, cy=R, R=R),
            bcs=dict(x_lo=side, x_hi=side, y_lo=side, y_hi=side,
                     z_lo=bcs2.get('y_lo', 'open'),
                     z_hi=bcs2.get('y_hi', 'open')))

    def revolve(self, field2d):
        """One (Nr, Nz) frame -> (n_xy, n_xy, n_z) revolved block."""
        f = np.asarray(field2d)
        if f.shape != self._shape2d:
            raise ValueError(
                f"expected a {self._shape2d} axisymmetric frame, "
                f"got {f.shape}")
        return f[self._ri[:, :, None], self._zi[None, None, :]]


class FrameStore:
    """Playback history with a memory cap: when the stored frames exceed
    the budget, every other frame is dropped and the accept stride
    doubles (same thinning as the solver's animation recorder), so the
    kept frames stay evenly spread over the whole run."""

    def __init__(self, mem_cap=FRAME_MEM_CAP):
        self.times = []
        self.frames = []
        self._mem_cap = mem_cap
        self._bytes = 0
        self._stride = 1
        self._seen = 0

    @staticmethod
    def _frame_bytes(frame):
        n = 0
        for v in frame.values():
            if isinstance(v, np.ndarray):
                n += v.nbytes
            elif isinstance(v, dict):
                n += sum(a.nbytes for a in v.values()
                         if isinstance(a, np.ndarray))
        return n

    def append(self, t, frame, force=False):
        """Offer a frame; it is kept every `stride`-th offer (always when
        force=True, e.g. the final frame). Returns True if the frame is
        still present in the store after any thinning triggered by this
        append (thinning is anchored on the newest frame, so it is never
        the one dropped)."""
        keep = force or (self._seen % self._stride == 0)
        self._seen += 1
        if not keep:
            return False
        self.times.append(float(t))
        self.frames.append(frame)
        self._bytes += self._frame_bytes(frame)
        while self._bytes > self._mem_cap and len(self.frames) > 2:
            # anchor thinning on the newest frame (drop from the older
            # end) so the frame we just accepted is never discarded
            self.times = self.times[::-2][::-1]
            self.frames = self.frames[::-2][::-1]
            self._bytes = sum(self._frame_bytes(f) for f in self.frames)
            self._stride *= 2
        return bool(self.frames) and self.frames[-1] is frame

    def __len__(self):
        return len(self.frames)

    def __getitem__(self, k):
        return self.times[k], self.frames[k]

    @property
    def latest(self):
        return self[-1] if self.frames else None
