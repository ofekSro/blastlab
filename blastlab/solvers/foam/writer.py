"""blastFoam case generation: render a blastlab Case as a complete
OpenFOAM-9 case tree.

Pure-text rendering (`render_case`) is separated from disk I/O
(`write_case`) so golden tests can pin the generated dicts without WSL.

Geometry mirrors the native solvers: the same effective cell size
(MIN_EXP_CELLS across the charge radius, material-aware density) on the
same uniform grid built by core.grid, so field read-back lands
cell-for-cell on the native x_c/y_c/z_c arrays (a single-block
blockMesh numbers cells x-fastest -> reshape(..., order='F')).

Templates copied from the shipped v6.2.0 tutorials:
  mappedBuilding3D/sector  1D spherical sector (collapsed hex + wedges)
  axisymmetricCharge       2D wedge orientation and face sets
  freeField                3D box, fvSchemes/fvSolution/phaseProperties
The mesh is static and uniform in v1 (no AMR / refineInternal), run
serially; obstacles and profile initialization are later phases.
"""

import math
import os
from dataclasses import dataclass, field

from ...core.constants import (GAMMA_AIR, RHO_AIR, P_AIR, MIN_EXP_CELLS)
from ...core.grid import make_grid_1d, make_geometry, make_grid
from . import env
from .dicts import FLUX_SCHEME, P_OPEN_BC, Raw, block, fmt, foam_file
from .materials import MATERIALS, E0, charge_radius

PHASE = 'expl'                  # fixed phase name for every material
HALF_ANGLE_DEG = 1.0            # wedge half-angle (1D sector, 2D axisym)
CV_AIR = 718.0                  # J/(kg K), freeField tutorial value
MOLW_AIR = 28.97
C_AMB = math.sqrt(GAMMA_AIR * P_AIR / RHO_AIR)
T_AMB = P_AIR / (RHO_AIR * (GAMMA_AIR - 1.0) * CV_AIR)
N_WRITES_MIN, N_WRITES_MAX = 40, 60

#: OpenFOAM dimension vectors
_DIMS = dict(p='[1 -1 -2 0 0 0 0]', T='[0 0 0 1 0 0 0]',
             U='[0 1 -1 0 0 0 0]', alpha='[0 0 0 0 0 0 0]',
             rho='[1 -3 0 0 0 0 0]')


@dataclass
class CaseSpec:
    """Everything the runner/reader need to drive and decode a case."""
    dim: int
    material: str
    phase: str = PHASE
    nx: int = 0
    ny: int = 1
    nz: int = 1
    dx: float = 0.0
    r_exp: float = 0.0
    center: tuple = (0.0, 0.0, 0.0)     # foam coordinates
    end_time: float = 0.0
    cap_is_end: bool = False        # end_time is the user's t_end
    write_interval: float = 0.0
    grid: dict = None                    # core.grid product (per dim)
    probe_pts: list = field(default_factory=list)   # foam (x,y,z)
    gauge_ids: list = field(default_factory=list)   # native radii/points
    patches: list = field(default_factory=list)     # (name, kind)
    files: dict = field(default_factory=dict)       # relpath -> text
    case_posix: str = ''
    case_unc: str = ''

    @property
    def n_cells(self):
        return self.nx * self.ny * self.nz


# ── planning ────────────────────────────────────────────────────────────────

def _effective_dx(cell_size, r_exp):
    """Native refinement rule: >= MIN_EXP_CELLS cells across r_exp."""
    if cell_size > r_exp / MIN_EXP_CELLS:
        return r_exp / MIN_EXP_CELLS
    return cell_size


def _n_writes(n_snapshots):
    return min(N_WRITES_MAX, max(N_WRITES_MIN, 4 * n_snapshots))


def _timing(case, cap_dist, est_dist, n_snapshots):
    """(end_time, write_interval, cap_is_end), mirroring the native
    conventions: the safety cap is 10*cap_dist/c_amb (solver3d.py:298
    uses max(L)); t_end overrides it only when smaller (cap_is_end);
    writeInterval is sized from the native shock-transit estimate
    (1.5*est_dist/c_amb, est_dist = nearest open boundary) so an early
    shock-arrival stop still has a full frame record."""
    t_end = getattr(case, 't_end', 0.0) or 0.0
    cap = 10.0 * cap_dist / C_AMB
    cap_is_end = bool(t_end) and t_end < cap
    end_time = t_end if cap_is_end else cap
    # reference speed 2*c_amb: the shock front outruns ambient sound
    # (strongly so in the near field), and frames/snapshots only exist
    # at write times - this keeps the pre-arrival record dense enough
    # without exploding the dir count on slow far-field runs
    t_est = min(end_time, 1.5 * est_dist / (2.0 * C_AMB))
    return end_time, t_est / _n_writes(n_snapshots), cap_is_end


def plan_case(case):
    """Geometry/timing plan (no text yet). Returns a CaseSpec without
    `files`."""
    mat = getattr(case, 'material', 'TNT')
    m = MATERIALS[mat]

    if case.dim == 1:
        r_exp = charge_radius(case.charge_kg, m)
        dx = _effective_dx(case.cell_size_m, r_exp)
        r_face, r, A_face, V_cell = make_grid_1d(case.radius_m, dx)
        grid = dict(r_face=r_face, r=r, A_face=A_face, V_cell=V_cell)
        spec = CaseSpec(dim=1, material=mat, nx=len(r), dx=dx,
                        r_exp=r_exp, center=(0.0, 0.0, 0.0), grid=grid)
        R_out = r_face[-1]
        spec.patches = [('outlet', 'open'), ('wedge', 'wedge')]
        gauges = [g for g in case.gauge_radii if 0.0 < g <= R_out]
        spec.gauge_ids = gauges
        spec.probe_pts = [(g, 0.0, 0.0) for g in gauges]
        spec.end_time, spec.write_interval, spec.cap_is_end = _timing(
            case, R_out, R_out, case.n_snapshots)
        return spec

    if case.dim == 2:
        planar = case.geometry == 'planar'
        r_exp = charge_radius(case.charge, m, planar=planar)
        dx = _effective_dx(case.cell_size_m, r_exp)
        grid = make_geometry(case.geometry, case.Lx, case.Ly, dx)
        Lx_eff, Ly_eff = grid['x_face'][-1], grid['y_face'][-1]
        x0 = 0.0 if not planar else case.center[0]
        y0 = case.center[1]
        spec = CaseSpec(dim=2, material=mat,
                        nx=grid['Nx'], ny=grid['Ny'], dx=dx, r_exp=r_exp,
                        center=(x0, y0, 0.0), grid=grid)
        if planar:
            spec.patches = [(s, case.bcs[s])
                            for s in ('x_lo', 'x_hi', 'y_lo', 'y_hi')]
            spec.patches.append(('frontAndBack', 'empty'))
        else:
            # collapsed x=0 face is the axis; x_lo never becomes a patch
            spec.patches = [(s, case.bcs[s])
                            for s in ('x_hi', 'y_lo', 'y_hi')]
            spec.patches.append(('wedge', 'wedge'))
        gauges = [g for g in case.gauges
                  if 0 <= g[0] <= Lx_eff and 0 <= g[1] <= Ly_eff]
        spec.gauge_ids = gauges
        spec.probe_pts = [(g[0], g[1], 0.0) for g in gauges]
        side_d = dict(x_lo=x0, x_hi=Lx_eff - x0,
                      y_lo=y0, y_hi=Ly_eff - y0)
        if not planar:
            side_d.pop('x_lo')      # collapsed wedge axis, never open
        opens = [d for s, d in side_d.items()
                 if case.bcs.get(s) == 'open']
        corners = [(cx, cy) for cx in (0.0, Lx_eff)
                   for cy in (0.0, Ly_eff)]
        far = max(math.hypot(cx - x0, cy - y0) for cx, cy in corners)
        est = min(opens) if opens else far
        spec.end_time, spec.write_interval, spec.cap_is_end = _timing(
            case, max(Lx_eff, Ly_eff), est, case.n_snapshots)
        return spec

    # 3D
    r_exp = charge_radius(case.charge, m)
    dx = _effective_dx(case.cell_size_m, r_exp)
    grid = make_grid(case.Lx, case.Ly, case.Lz, dx)
    Ls = (grid['x_face'][-1], grid['y_face'][-1], grid['z_face'][-1])
    x0, y0, z0 = case.center
    spec = CaseSpec(dim=3, material=mat,
                    nx=grid['Nx'], ny=grid['Ny'], nz=grid['Nz'],
                    dx=dx, r_exp=r_exp, center=(x0, y0, z0), grid=grid)
    spec.patches = [(s, case.bcs[s])
                    for s in ('x_lo', 'x_hi', 'y_lo', 'y_hi',
                              'z_lo', 'z_hi')]
    gauges = [g for g in case.gauges
              if all(0 <= v <= L for v, L in zip(g, Ls))]
    spec.gauge_ids = gauges
    spec.probe_pts = [tuple(g) for g in gauges]
    side_d = dict(x_lo=x0, x_hi=Ls[0] - x0, y_lo=y0, y_hi=Ls[1] - y0,
                  z_lo=z0, z_hi=Ls[2] - z0)
    opens = [d for s, d in side_d.items() if case.bcs.get(s) == 'open']
    corners = [(cx, cy, cz) for cx in (0.0, Ls[0])
               for cy in (0.0, Ls[1]) for cz in (0.0, Ls[2])]
    far = max(math.sqrt((cx - x0) ** 2 + (cy - y0) ** 2
                        + (cz - z0) ** 2) for cx, cy, cz in corners)
    est = min(opens) if opens else far
    spec.end_time, spec.write_interval, spec.cap_is_end = _timing(
        case, max(Ls), est, case.n_snapshots)
    return spec


# ── blockMeshDict ───────────────────────────────────────────────────────────

def _bmd(vertices, block_line, boundary, convert=1):
    body = block({
        'convertToMeters': convert,
        'vertices': [tuple(v) for v in vertices],
        'blocks': [Raw(block_line)],
        'edges': Raw('( )'),
        'boundary': boundary,
        'mergePatchPairs': Raw('( )'),
    })
    return foam_file('blockMeshDict', body)


def _patch_type(kind):
    return dict(wall='wall', open='patch', empty='empty',
                wedge='wedge')[kind]


def _blockmesh_1d(spec):
    """Spherical sector along +x (mappedBuilding3D/sector template):
    collapsed hex, apex at the origin, four wedge lateral faces."""
    R = spec.grid['r_face'][-1]
    a = math.radians(HALF_ANGLE_DEG)
    c, s = R * math.cos(a), R * math.sin(a)
    vertices = [(0, 0, 0), (c, -s, -s), (c, s, -s), (c, -s, s), (c, s, s)]
    boundary = [
        ('wedge0', {'type': 'wedge', 'faces': [(0, 1, 2, 0)]}),
        ('wedge1', {'type': 'wedge', 'faces': [(0, 3, 4, 0)]}),
        ('wedge2', {'type': 'wedge', 'faces': [(0, 2, 4, 0)]}),
        ('wedge3', {'type': 'wedge', 'faces': [(0, 1, 3, 0)]}),
        ('outlet', {'type': _patch_type(spec.patches[0][1]),
                    'faces': [(1, 2, 4, 3)]}),
    ]
    line = (f'hex (0 1 2 0 0 3 4 0) ({spec.nx} 1 1) '
            f'simpleGrading (1 1 1)')
    return _bmd(vertices, line, boundary)


def _blockmesh_2d_axisym(spec, case):
    """1-degree wedge, radial = +x, axial = +y (axisymmetricCharge
    template; the collapsed x=0 face is the axis)."""
    Lx = spec.grid['x_face'][-1]
    Ly = spec.grid['y_face'][-1]
    a = math.radians(HALF_ANGLE_DEG)
    xc, s = Lx * math.cos(a), Lx * math.sin(a)
    vertices = [(0, 0, 0), (xc, 0, -s), (xc, Ly, -s), (0, Ly, 0),
                (xc, 0, s), (xc, Ly, s)]
    boundary = [
        ('y_lo', {'type': _patch_type(case.bcs['y_lo']),
                  'faces': [(0, 1, 4, 0)]}),
        ('x_hi', {'type': _patch_type(case.bcs['x_hi']),
                  'faces': [(1, 2, 5, 4)]}),
        ('y_hi', {'type': _patch_type(case.bcs['y_hi']),
                  'faces': [(3, 2, 5, 3)]}),
        ('wedge0', {'type': 'wedge', 'faces': [(0, 1, 2, 3)]}),
        ('wedge1', {'type': 'wedge', 'faces': [(0, 4, 5, 3)]}),
    ]
    line = (f'hex (0 1 2 3 0 4 5 3) ({spec.nx} {spec.ny} 1) '
            f'simpleGrading (1 1 1)')
    return _bmd(vertices, line, boundary)


def _blockmesh_2d_planar(spec, case):
    """One-cell-thick slab with empty front/back."""
    Lx = spec.grid['x_face'][-1]
    Ly = spec.grid['y_face'][-1]
    zh = spec.dx / 2.0
    vertices = [(0, 0, -zh), (Lx, 0, -zh), (Lx, Ly, -zh), (0, Ly, -zh),
                (0, 0, zh), (Lx, 0, zh), (Lx, Ly, zh), (0, Ly, zh)]
    boundary = [
        ('x_lo', {'type': _patch_type(case.bcs['x_lo']),
                  'faces': [(0, 3, 7, 4)]}),
        ('x_hi', {'type': _patch_type(case.bcs['x_hi']),
                  'faces': [(1, 2, 6, 5)]}),
        ('y_lo', {'type': _patch_type(case.bcs['y_lo']),
                  'faces': [(0, 1, 5, 4)]}),
        ('y_hi', {'type': _patch_type(case.bcs['y_hi']),
                  'faces': [(3, 2, 6, 7)]}),
        ('frontAndBack', {'type': 'empty',
                          'faces': [(0, 1, 2, 3), (4, 5, 6, 7)]}),
    ]
    line = (f'hex (0 1 2 3 4 5 6 7) ({spec.nx} {spec.ny} 1) '
            f'simpleGrading (1 1 1)')
    return _bmd(vertices, line, boundary)


def _blockmesh_3d(spec, case):
    """Single uniform hex block (freeField template), six bc patches."""
    Lx = spec.grid['x_face'][-1]
    Ly = spec.grid['y_face'][-1]
    Lz = spec.grid['z_face'][-1]
    vertices = [(0, 0, 0), (Lx, 0, 0), (Lx, Ly, 0), (0, Ly, 0),
                (0, 0, Lz), (Lx, 0, Lz), (Lx, Ly, Lz), (0, Ly, Lz)]
    faces = dict(x_lo=(0, 3, 7, 4), x_hi=(1, 2, 6, 5),
                 y_lo=(0, 1, 5, 4), y_hi=(3, 2, 6, 7),
                 z_lo=(0, 1, 2, 3), z_hi=(4, 5, 6, 7))
    boundary = [(side, {'type': _patch_type(case.bcs[side]),
                        'faces': [faces[side]]})
                for side in ('x_lo', 'x_hi', 'y_lo', 'y_hi',
                             'z_lo', 'z_hi')]
    line = (f'hex (0 1 2 3 4 5 6 7) ({spec.nx} {spec.ny} {spec.nz}) '
            f'simpleGrading (1 1 1)')
    return _bmd(vertices, line, boundary)


# ── system/ + constant/ dicts ───────────────────────────────────────────────

def _controldict(spec, case):
    d = {
        'application': 'blastFoam',
        'startFrom': 'startTime',
        'startTime': 0,
        'stopAt': 'endTime',
        'endTime': spec.end_time,
        'deltaT': Raw('1e-7'),
        'writeControl': 'adjustableRunTime',
        'writeInterval': spec.write_interval,
        'cycleWrite': 0,
        'writeFormat': 'ascii',
        'writePrecision': 6,
        'writeCompression': 'off',
        'timeFormat': 'general',
        'timePrecision': 8,
        'runTimeModifiable': 'true',
        'adjustTimeStep': 'yes',
        'maxCo': case.cfl,
        'maxDeltaT': 1,
        # stop requests rewrite this file to `stopAt writeNow`; the
        # default 10 s fileModificationSkew can swallow that edit
        # forever (a fixed mtime never clears the skew window), so
        # tighten it to 1 s for this case. (inotify would be cleaner
        # but this OpenFOAM build lacks FOAM_USE_INOTIFY; the WSL-side
        # sed rewrite guarantees a fresh native mtime.)
        'OptimisationSwitches': {
            'fileModificationChecking': 'timeStampMaster',
            'fileModificationSkew': 1,
        },
    }
    if spec.probe_pts:
        d['functions'] = {
            'gauges': {
                'type': 'blastProbes',
                'writeControl': 'timeStep',
                'writeInterval': 1,
                'adjustLocations': 'yes',
                'append': 'yes',
                'probeLocations': [tuple(p) for p in spec.probe_pts],
                'fields': ['p'],
            },
        }
    return foam_file('controlDict', block(d), location='system')


def _fvschemes():
    body = block({
        'fluxScheme': FLUX_SCHEME,
        'ddtSchemes': {'default': 'Euler', 'timeIntegrator': 'RK2SSP'},
        'gradSchemes': {'default': Raw('cellMDLimited leastSquares 1.0')},
        'divSchemes': {
            'default': 'none',
            f'div(alphaRhoPhi.{PHASE},lambda.{PHASE})': 'Riemann',
        },
        'laplacianSchemes': {'default': Raw('Gauss linear corrected')},
        'interpolationSchemes': {
            'default': 'cubic',
            'reconstruct(alpha)': 'vanAlbada',
            'reconstruct(rho)': 'vanAlbada',
            'reconstruct(U)': 'vanAlbadaV',
            'reconstruct(e)': 'vanAlbada',
            'reconstruct(p)': 'vanAlbada',
            'reconstruct(speedOfSound)': 'vanAlbada',
            f'reconstruct(lambda.{PHASE})': 'vanAlbada',
        },
        'snGradSchemes': {'default': 'corrected'},
    })
    return foam_file('fvSchemes', body, location='system')


def _fvsolution():
    body = block({
        'solvers': {'"(rho|rhoU|rhoE|alpha|.*)"': {'solver': 'diagonal'}},
    })
    return foam_file('fvSolution', body, location='system')


def _setfieldsdict(spec, case):
    alpha = f'alpha.{PHASE}'
    charge = case.charge_kg if spec.dim == 1 else case.charge
    if spec.dim == 2 and case.geometry == 'planar':
        x0, y0, _ = spec.center
        region = ('cylinderToCell', {
            'p1': (x0, y0, -spec.dx),
            'p2': (x0, y0, spec.dx),
            'radius': spec.r_exp,
            'fieldValues': [Raw(f'volScalarFieldValue {alpha}    1')],
        })
    else:
        m = MATERIALS[spec.material]
        region = ('sphericalMassToCell', {
            'centre': spec.center,
            'rho': m.rho0,
            'mass': charge,
            'backup': {'centre': spec.center,
                       'radius': 2.0 * spec.r_exp},
            'fieldValues': [Raw(f'volScalarFieldValue {alpha}    1')],
        })
    body = block({
        'fields': [alpha],
        'nBufferLayers': 1,
        'defaultFieldValues': [Raw(f'volScalarFieldValue {alpha} 0')],
        'regions': [region],
    })
    return foam_file('setFieldsDict', body, location='system')


def _phaseproperties(spec):
    m = MATERIALS[spec.material]
    body = block({
        'phases': [PHASE, 'air'],
        'radiationModel': 'none',
        PHASE: {
            'type': 'detonating',
            'reactants': {
                'thermoType': {'transport': 'const', 'thermo': 'eConst',
                               'equationOfState': 'Murnaghan'},
                'equationOfState': {'rho0': m.rho0,
                                    'Gamma': m.Gamma_reactants,
                                    'pRef': P_AIR, 'K0': 0},
                'specie': {'molWeight': m.molWeight},
                'transport': {'mu': 0, 'Pr': 1},
                'thermodynamics': {'Cv': m.Cv_reactants, 'Hf': 0.0},
            },
            'products': {
                'thermoType': {'transport': 'const', 'thermo': 'eConst',
                               'equationOfState': 'JWL'},
                'equationOfState': {'rho0': m.rho0, 'A': m.A, 'B': m.B,
                                    'R1': m.R1, 'R2': m.R2,
                                    'omega': m.omega},
                'specie': {'molWeight': m.molWeight},
                'transport': {'mu': 0, 'Pr': 1},
                'thermodynamics': {'Cv': m.Cv_products, 'Hf': 0.0},
            },
            'activationModel': 'linear',
            'initiation': {
                'E0': E0(m),
                'points': [spec.center],
                'vDet': m.vDet,
            },
            'residualRho': Raw('1e-6'),
            'residualAlpha': Raw('1e-10'),
        },
        'air': {
            'type': 'basic',
            'thermoType': {'transport': 'const', 'thermo': 'eConst',
                           'equationOfState': 'idealGas'},
            'equationOfState': {'gamma': GAMMA_AIR},
            'specie': {'molWeight': MOLW_AIR},
            'transport': {'mu': 0, 'Pr': 1},
            'thermodynamics': {'type': 'eConst', 'Cv': CV_AIR, 'Hf': 0},
            'residualRho': Raw('1e-6'),
            'residualAlpha': Raw('1e-10'),
        },
    })
    return foam_file('phaseProperties', body, location='constant')


def _dynamicmeshdict():
    return foam_file('dynamicMeshDict',
                     block({'dynamicFvMesh': 'staticFvMesh'}),
                     location='constant')


# ── 0/ field files ──────────────────────────────────────────────────────────

def _bc_entry(fld, kind):
    """Boundary entry dict for one field on one patch kind."""
    if kind == 'wedge':
        return {'type': 'wedge'}
    if kind == 'empty':
        return {'type': 'empty'}
    if kind == 'wall':
        return {'type': 'slip'} if fld == 'U' else {'type': 'zeroGradient'}
    # open
    if fld == 'p':
        return {'type': P_OPEN_BC, 'value': Raw('$internalField')}
    return {'type': 'zeroGradient'}


def _field_file(obj, fld, internal, spec, vector=False):
    bfield = {name: _bc_entry(fld, kind) for name, kind in spec.patches}
    body = block({
        'dimensions': Raw(_DIMS[fld]),
        'internalField': Raw(f'uniform {internal}'),
        'boundaryField': bfield,
    })
    cls = 'volVectorField' if vector else 'volScalarField'
    return foam_file(obj, body, cls=cls)


def _zero_fields(spec):
    m = MATERIALS[spec.material]
    return {
        '0/p': _field_file('p', 'p', fmt(P_AIR), spec),
        '0/T': _field_file('T', 'T', fmt(T_AMB), spec),
        '0/U': _field_file('U', 'U', '(0 0 0)', spec, vector=True),
        f'0/alpha.{PHASE}': _field_file(f'alpha.{PHASE}', 'alpha',
                                        '0', spec),
        f'0/rho.{PHASE}': _field_file(f'rho.{PHASE}', 'rho',
                                      fmt(m.rho0), spec),
        '0/rho.air': _field_file('rho.air', 'rho', fmt(RHO_AIR), spec),
    }


# ── top level ───────────────────────────────────────────────────────────────

def render_case(case):
    """Plan + render every case file. Returns a CaseSpec whose `files`
    maps 'system/controlDict'-style relpaths to file text."""
    spec = plan_case(case)
    if spec.dim == 1:
        bmd = _blockmesh_1d(spec)
    elif spec.dim == 2:
        bmd = (_blockmesh_2d_planar(spec, case)
               if case.geometry == 'planar'
               else _blockmesh_2d_axisym(spec, case))
    else:
        bmd = _blockmesh_3d(spec, case)
    spec.files = {
        'system/blockMeshDict': bmd,
        'system/controlDict': _controldict(spec, case),
        'system/fvSchemes': _fvschemes(),
        'system/fvSolution': _fvsolution(),
        'system/setFieldsDict': _setfieldsdict(spec, case),
        'constant/phaseProperties': _phaseproperties(spec),
        'constant/dynamicMeshDict': _dynamicmeshdict(),
    }
    spec.files.update(_zero_fields(spec))
    return spec


def write_case(case, case_posix=None):
    """Render and write the case tree into the WSL filesystem (over
    UNC, LF endings). Returns the CaseSpec with paths filled in."""
    spec = render_case(case)
    if case_posix is None:
        case_posix, case_unc = env.new_case_dir(case.dim)
    else:
        case_unc = env.unc(case_posix)
    spec.case_posix, spec.case_unc = case_posix, case_unc
    for rel, text in spec.files.items():
        path = os.path.join(case_unc, *rel.split('/'))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='ascii', newline='\n') as f:
            f.write(text)
    return spec
