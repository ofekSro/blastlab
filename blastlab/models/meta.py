"""What a finished run's `Result.meta` contains, and the accessors the
results panels read it through.

docs/ARCHITECTURE_REVIEW.md section 5, Phase 8 (finding F3). `meta` stays
a plain dict filled by its producers - the native `solvers/solver1d.py`,
`solver2d.py`, `solver3d.py` and the blastFoam `solvers/foam/backend.py`
(`finalize_1d/2d/3d`) - none of which this module changes. It only says
what they write and gives the panels a handful of functions instead of
literal string reads. Whether `meta` should become a typed object is open
question Q2 of the review and is not decided here.

Key sets
    `META_KEYS_1D/2D/3D` are the keys a native run returns for the Phase 0
    characterisation cases (`tests/char_golden/native_*_result.json`,
    pinned by `tests/test_char_native_api.py`). `META_OPTIONAL_*` are
    written only in some runs, `META_FOAM_KEYS_*` are the blastFoam
    backend's own sets as read from its code (no WSL run pinned them), and
    `META_HOST_KEYS` are added after the solve by whoever ran it.

Accessors
    Each returns exactly what the panels' literal reads returned: every
    key a panel read with `meta[k]` is still read with `meta[k]` (so a
    missing key is the same KeyError), every `meta.get(k, default)` keeps
    its default. `slice_geometry` covers the plane reads of
    `ui/results_fields.py`, `ui/results_anim.py` and `gui/results_panel.py`;
    `frames_of`, `anim_scale_of` and `charge_label` the rest.

Imports only `core`, like the rest of `models/`.
"""

from typing import NamedTuple

from ..core.constants import anim_scale_from_label

# ── what the producers write ─────────────────────────────────────────────
# One line per key: who sets it -> who reads it. "Panels" means the Qt
# ui/results_*.py views, services/exports.py and the Tk gui/results_panel.py.

#: native 1D (solver1d.py `_run_blast_1d`); the foam backend adds
#: `META_FOAM_EXTRA_1D`
META_KEYS_1D = frozenset({
    'final_profile',  # solver1d / finalize_1d -> profile export (services/exports, solvers/jobs), legacy.blast1d
    'r',              # solver1d / finalize_1d: cell centres [m] -> output/report field CSV
    'radius_m',       # solver1d / finalize_1d: domain radius [m] -> charge_label (Fields 1D, exports, Tk)
    'charge_kg',      # solver1d / finalize_1d: charge [kg] -> charge_label (Fields/Gauges 1D, exports, Tk), report
    'eos',            # solver1d / finalize_1d ('JWL' for foam) -> charge_label, plot titles
    'r_exp',          # solver1d / finalize_1d: charge radius [m] -> provenance only, no panel reads it
})

#: native 2D (solver2d.py `_run_blast_2d`), with frames recorded;
#: `finalize_2d` writes all of these too
META_KEYS_2D = frozenset({
    'solver',         # solver2d / finalize_2d: 'native' | 'blastfoam' -> report, core/profiles provenance, export_vtk.can_export
    'x_c', 'y_c',     # solver2d / finalize_2d: cell centres [m] -> plots, report CSV, core/profiles
    'x_face', 'y_face',  # solver2d / finalize_2d: cell faces [m] -> slice_geometry (Fields, Animation, Tk), plots, animation
    'solid',          # solver2d / finalize_2d: obstacle mask (Nx, Ny) -> slice_geometry, plots, core/profiles
    'geometry',       # solver2d / finalize_2d: 'planar' | 'axisymmetric' -> axis labels (Fields, Animation, Tk), exports.can('profile')
    'Lx', 'Ly',       # solver2d / finalize_2d: domain [m] -> Tk Fields aspect, plots, animation
    'dx',             # solver2d / finalize_2d: cell size [m] -> plots.mesh_for, gauge markers
    'eos',            # solver2d / finalize_2d -> plot titles
    'bcs',            # solver2d / finalize_2d: boundary per side -> run description, no panel reads it
    'obstacles',      # solver2d / finalize_2d: boxes -> report
    'charge',         # solver2d / finalize_2d: kg (kg/m planar) -> plots.charge_label titles, report, core/profiles
    'charge_center',  # solver2d / finalize_2d: (x, y) [m] -> report, core/profiles
    'r_exp',          # solver2d / finalize_2d: charge radius [m] -> core/profiles
    'from_profile',   # solver2d / finalize_2d: remapped start? -> plots.charge_label
    'gauges',         # solver2d / finalize_2d: gauge points as ASKED -> gauge summary (exports, Tk), plots
    'trigger_gauge',  # solver2d / finalize_2d: 1-based trigger gauge or None -> output/animation marker
    'p_peak', 'impulse',  # solver2d / finalize_2d: whole-run maps -> Fields peak/impulse entries (plots.peak_items), report
    'final_state',    # solver2d / finalize_2d: last field -> profile export (core/profiles.save_profile_2d)
    'frames',         # solver2d / finalize_2d, only when record_frames > 0 -> frames_of (Animation, Tk), exports.can('gif'), output/animation
})

#: native 3D (solver3d.py `_run_blast_3d`), with frames recorded;
#: `finalize_3d` writes all of these too
META_KEYS_3D = (META_KEYS_2D - {'geometry', 'final_state'}) | frozenset({
    'z_c',            # solver3d / finalize_3d: cell centres [m] -> slice_geometry (plane position), plots
    'z_face',         # solver3d / finalize_3d: cell faces [m] -> slice_geometry; its presence marks a 3D frame record
    'Lz',             # solver3d / finalize_3d: domain [m] -> Tk Fields aspect, plots, viz3d
    'j0', 'k0',       # solver3d / finalize_3d: y / z index of the x-z / x-y Fields planes -> slice_geometry
    'slice_axis',     # solver3d / finalize_3d: axis the frames were recorded across -> slice_geometry('recorded')
    's0',             # solver3d / finalize_3d: index of that recorded slice -> slice_geometry('recorded')
    'r_src',          # solver3d / finalize_3d: source radius [m] -> viz3d/client
})

#: written only when the run had them (both backends)
META_OPTIONAL_2D = frozenset({
    'trigger',        # a trigger gauge fired -> solvers/jobs, viewer
    'trigger_state',  # its remap state (action 'remap') -> solvers/jobs.write_trigger_remap
})
META_OPTIONAL_3D = frozenset({'trigger'})

#: the blastFoam backend's extras over the native sets, read from
#: solvers/foam/backend.py finalize_1d/2d/3d (not pinned by a run here)
META_FOAM_EXTRA_1D = frozenset({
    'solver',         # 'blastfoam' (native 1D writes no `solver` key)
    'material',       # the EOS table row -> provenance
    'conserved',      # conservation check payload or None -> no panel reads it
    'case_dir',       # UNC path of the OpenFOAM case -> export_vtk.can_export, report, Tk "open case"
})
META_FOAM_EXTRA_ND = META_FOAM_EXTRA_1D | frozenset({
    'refine',         # refinement/AMR level maps -> plots.mesh_for ("Show mesh")
    'peak_source',    # where p_peak/impulse came from -> foam/cli_run
})
META_FOAM_KEYS_1D = META_KEYS_1D | META_FOAM_EXTRA_1D
META_FOAM_KEYS_2D = META_KEYS_2D | META_FOAM_EXTRA_ND
META_FOAM_KEYS_3D = META_KEYS_3D | META_FOAM_EXTRA_ND

#: added after the solve, by the host that ran it
META_HOST_KEYS = frozenset({
    'name',           # ui/run_controller.py, gui/app.py, the results panels -> export file names, report title
    'anim_scale',     # solvers/jobs._animate (2D/3D) -> anim_scale_of (Animation), output/animation
    'anim_clim',      # solvers/jobs._animate -> anim_scale_of, output/animation
})


# ── accessors ────────────────────────────────────────────────────────────
class SliceGeometry(NamedTuple):
    """One plane of a 2D/3D result: its faces, obstacle mask and where it
    sits. `axis`, `index`, `sl` and `coord` are None for the 2D grid."""
    xf: object          # horizontal faces [m]
    yf: object          # vertical faces [m] (y_face in 2D, z_face or y_face in 3D)
    solid: object       # the obstacle mask on this plane
    axis: object        # 'x' | 'y' | 'z': the axis the plane cuts across
    index: object       # the cell index along `axis`
    sl: object          # the 3D index tuple selecting the plane
    coord: object       # the plane's position along `axis` [m]


def _plane_sl(axis, index):
    """The 3D index tuple fixing `axis` at `index`, e.g. ('y', 4) ->
    (slice(None), 4, slice(None))."""
    return tuple(index if a == 'xyz'.index(axis) else slice(None)
                 for a in range(3))


def _on_plane(meta, xf, yf, axis, index):
    """The 3D plane across `axis` at `index`; reads `solid`, then
    `<axis>_c`, in the order the panels did."""
    sl = _plane_sl(axis, index)
    return SliceGeometry(xf, yf, meta['solid'][sl], axis, index, sl,
                         meta[f'{axis}_c'][index])


def slice_geometry(meta: dict, plane: str = 'recorded') -> SliceGeometry:
    """The faces, mask and position of one plane of a result.

    `plane`:
      * 'grid' - the whole 2D grid (x_face, y_face, solid);
      * 'x-z' / 'x-y' - the two 3D Fields planes, at y = y_c[j0] and
        z = z_c[k0] (both indices are read either way, as the panels did);
      * 'recorded' - the plane the replay frames were recorded on: the 2D
        grid when meta has no 'z_face', else `slice_axis` (default 'y') at
        `s0` (default j0; j0 is read even when s0 is present, as the
        panels did). All three face arrays are read.
    """
    if plane == 'grid':
        return SliceGeometry(meta['x_face'], meta['y_face'], meta['solid'],
                             None, None, None, None)
    if plane in ('x-z', 'x-y'):
        j0, k0 = meta['j0'], meta['k0']
        if plane == 'x-z':
            axis, index = 'y', j0
            xf, yf = meta['x_face'], meta['z_face']
        else:
            axis, index = 'z', k0
            xf, yf = meta['x_face'], meta['y_face']
        return _on_plane(meta, xf, yf, axis, index)
    if plane == 'recorded':
        if 'z_face' not in meta:
            return slice_geometry(meta, 'grid')
        axis = meta.get('slice_axis', 'y')
        index = meta.get('s0', meta['j0'])
        xf, yf = {'x': (meta['y_face'], meta['z_face']),
                  'y': (meta['x_face'], meta['z_face']),
                  'z': (meta['x_face'], meta['y_face'])}[axis]
        return _on_plane(meta, xf, yf, axis, index)
    raise ValueError(f'unknown plane {plane!r}')


def frames_of(meta: dict) -> dict | None:
    """The recorded replay frames (`{'times', 'pressures'[, 'levels']}`),
    or None when the run recorded none or an empty set."""
    frames = meta.get('frames')
    if not frames or not len(frames['pressures']):
        return None
    return frames


class AnimScale(NamedTuple):
    scale: str          # 'run' | 'frame' | 'manual'
    clim: object        # the recorded manual range [kPa], or None


def anim_scale_of(meta: dict) -> AnimScale:
    """The colour scale the run recorded for its animation
    (`solvers/jobs._animate`), 'run' when it recorded none."""
    return AnimScale(anim_scale_from_label(meta.get('anim_scale') or 'run'),
                     meta.get('anim_clim'))


class ChargeLabel(NamedTuple):
    eos: object
    charge_kg: object
    radius_m: object    # None when asked for without it


def charge_label(meta: dict, radius: bool = True) -> ChargeLabel:
    """The EOS, charge [kg] and domain radius [m] a 1D figure is titled
    with. `radius=False` is the gauges figure, which never read the radius
    (so a meta without it still draws; `radius_m` is then None).

    Not `output.plots.charge_label`, which formats the 2D/3D title text."""
    if radius:
        return ChargeLabel(meta['eos'], meta['charge_kg'], meta['radius_m'])
    # charge_kg before eos: the order figure_gauges_1d's arguments were read
    charge_kg = meta['charge_kg']
    return ChargeLabel(meta['eos'], charge_kg, None)
