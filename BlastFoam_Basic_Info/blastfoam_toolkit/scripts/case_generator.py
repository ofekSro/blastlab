#!/usr/bin/env python3
"""
BlastFOAM Case Generator
========================
יוצר מבנה תיקיות בסיסי עבור סימולציית BlastFOAM.

Usage:
    python case_generator.py <case_name> [--type TYPE] [--explosive EXPLOSIVE]
    
Options:
    --type      : סוג הסימולציה (airblast, underwater, confined) [default: airblast]
    --explosive : סוג חומר הנפץ (TNT, C4, RDX) [default: TNT]
    
Example:
    python case_generator.py myBlast --type airblast --explosive TNT
"""

import os
import sys
import argparse
from pathlib import Path

# ========================================
# Templates for BlastFOAM case files
# ========================================

CONTROL_DICT_TEMPLATE = """FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      controlDict;
}}

application     blastFoam;

startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         {end_time};

deltaT          {delta_t};
writeControl    adjustableRunTime;
writeInterval   {write_interval};

purgeWrite      0;
writeFormat     binary;
writePrecision  12;
writeCompression uncompressed;

timeFormat      general;
timePrecision   6;

runTimeModifiable true;
adjustTimeStep  yes;
maxCo           0.5;

functions
{{
    overpressureAndImpulse
    {{
        type            overpressureAndImpulse;
        pRef            101325;
    }}
    
    probes
    {{
        type            probes;
        libs            ("libsampling.so");
        writeControl    timeStep;
        writeInterval   1;
        probeLocations
        (
            (0 0 0)
            (1 0 0)
            (2 0 0)
            (5 0 0)
            (10 0 0)
        );
        fields (p rho T U);
    }}
}}
"""

FV_SCHEMES_TEMPLATE = """FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      fvSchemes;
}

fluxScheme      HLLC;

ddtSchemes
{
    default         Euler;
}

gradSchemes
{
    default         cellLimited leastSquares 1;
}

divSchemes
{
    default         none;
    div(tauMC)      Gauss linear;
}

laplacianSchemes
{
    default         Gauss linear corrected;
}

interpolationSchemes
{
    default         linear;
    reconstruct(rho)    MUSCL vanLeer;
    reconstruct(U)      MUSCL vanLeer;
    reconstruct(e)      MUSCL vanLeer;
    reconstruct(p)      MUSCL vanLeer;
    reconstruct(speedOfSound) MUSCL vanLeer;
}

snGradSchemes
{
    default         corrected;
}
"""

FV_SOLUTION_TEMPLATE = """FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      fvSolution;
}

solvers
{
    "(rho|rhoU|rhoE|alpha.*)"
    {
        solver          diagonal;
    }

    "(U|e)"
    {
        solver          PBiCGStab;
        preconditioner  DIC;
        tolerance       1e-12;
        relTol          0;
    }
}
"""

BLOCK_MESH_DICT_TEMPLATE = """FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      blockMeshDict;
}}

scale   1;

// Domain dimensions
xMin    {x_min};
xMax    {x_max};
yMin    {y_min};
yMax    {y_max};
zMin    {z_min};
zMax    {z_max};

// Resolution
nx      {nx};
ny      {ny};
nz      {nz};

vertices
(
    ($xMin $yMin $zMin)  // 0
    ($xMax $yMin $zMin)  // 1
    ($xMax $yMax $zMin)  // 2
    ($xMin $yMax $zMin)  // 3
    ($xMin $yMin $zMax)  // 4
    ($xMax $yMin $zMax)  // 5
    ($xMax $yMax $zMax)  // 6
    ($xMin $yMax $zMax)  // 7
);

blocks
(
    hex (0 1 2 3 4 5 6 7) ($nx $ny $nz) simpleGrading (1 1 1)
);

boundary
(
    walls
    {{
        type wall;
        faces
        (
            (3 7 6 2)   // top
            (1 5 4 0)   // bottom
            (0 4 7 3)   // left
            (2 6 5 1)   // right
            (0 3 2 1)   // front
            (4 5 6 7)   // back
        );
    }}
);
"""

SET_FIELDS_DICT_TEMPLATE = """FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      setFieldsDict;
}}

defaultFieldValues
(
    volScalarFieldValue alpha.{explosive_name} 0
    volScalarFieldValue alpha.air 1
);

regions
(
    sphereToCell
    {{
        centre  ({explosive_x} {explosive_y} {explosive_z});
        radius  {explosive_radius};
        
        fieldValues
        (
            volScalarFieldValue alpha.{explosive_name} 1
            volScalarFieldValue alpha.air 0
        );
    }}
);
"""

# JWL Parameters for common explosives
JWL_PARAMS = {
    'TNT': {
        'A': 3.712e11,
        'B': 3.23e9,
        'R1': 4.15,
        'R2': 0.95,
        'omega': 0.3,
        'rho0': 1630,
        'e0': 4.29e6,
        'pRef': 1e5,
        'detonationVelocity': 6930
    },
    'C4': {
        'A': 6.0977e11,
        'B': 1.295e10,
        'R1': 4.5,
        'R2': 1.4,
        'omega': 0.25,
        'rho0': 1601,
        'e0': 5.56e6,
        'pRef': 1e5,
        'detonationVelocity': 8193
    },
    'RDX': {
        'A': 7.78e11,
        'B': 7.07e9,
        'R1': 4.485,
        'R2': 1.068,
        'omega': 0.30,
        'rho0': 1770,
        'e0': 5.15e6,
        'pRef': 1e5,
        'detonationVelocity': 8750
    }
}

PHASE_PROPERTIES_TEMPLATE = """FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant";
    object      phaseProperties;
}}

phases (air {explosive_name});

air
{{
    type            basic;
    thermoType
    {{
        transport       const;
        thermo          eConst;
        equationOfState idealGas;
    }}
    
    equationOfState
    {{
        gamma       1.4;
    }}
    
    specie
    {{
        molWeight   28.97;
    }}
    
    thermodynamics
    {{
        Cv          718;
        Hf          0;
    }}
    
    transport
    {{
        mu          1.8e-5;
        Pr          0.7;
    }}

    residualRho     1e-6;
    residualAlpha   1e-10;
}}

{explosive_name}
{{
    type            detonatingSolidFluid;
    
    reactants
    {{
        thermoType
        {{
            transport       const;
            thermo          eConst;
            equationOfState rhoConst;
        }}
        
        equationOfState
        {{
            rho         {rho0};
        }}
        
        specie
        {{
            molWeight   222.12;
        }}
        
        thermodynamics
        {{
            Cv          1000;
            Hf          0;
        }}
        
        transport
        {{
            mu          0;
            Pr          1;
        }}
    }}
    
    products
    {{
        thermoType
        {{
            transport       const;
            thermo          eConst;
            equationOfState JWL;
        }}
        
        equationOfState
        {{
            A           {A};
            B           {B};
            R1          {R1};
            R2          {R2};
            omega       {omega};
            rho0        {rho0};
            e0          {e0};
            pRef        {pRef};
        }}
        
        specie
        {{
            molWeight   28.97;
        }}
        
        thermodynamics
        {{
            Cv          850;
            Hf          0;
        }}
        
        transport
        {{
            mu          0;
            Pr          1;
        }}
    }}
    
    activationModel linear;
    linearCoeffs
    {{
        vDet        {detonationVelocity};
        pMin        1e6;
        
        points
        (
            ({explosive_x} {explosive_y} {explosive_z})
        );
    }}

    residualRho     1e-6;
    residualAlpha   1e-10;
}}
"""

INITIAL_CONDITIONS_TEMPLATE = """FoamFile
{{
    version     2.0;
    format      ascii;
    class       volScalarField;
    location    "0";
    object      {field_name};
}}

dimensions      [{dims}];

internalField   uniform {value};

boundaryField
{{
    walls
    {{
        type            zeroGradient;
    }}
}}
"""

VELOCITY_TEMPLATE = """FoamFile
{
    version     2.0;
    format      ascii;
    class       volVectorField;
    location    "0";
    object      U;
}

dimensions      [0 1 -1 0 0 0 0];

internalField   uniform (0 0 0);

boundaryField
{
    walls
    {
        type            slip;
    }
}
"""

ALLRUN_TEMPLATE = """#!/bin/bash
cd "${0%/*}" || exit
. $WM_PROJECT_DIR/bin/tools/RunFunctions

# Clean previous results
rm -rf 0.[0-9]* [1-9]* constant/polyMesh

# Generate mesh
runApplication blockMesh

# Set initial fields
runApplication setFields

# Run solver
runApplication blastFoam

echo "Simulation complete!"
"""

ALLCLEAN_TEMPLATE = """#!/bin/bash
cd "${0%/*}" || exit

# Remove time directories
rm -rf 0.[0-9]* [1-9]*

# Remove mesh
rm -rf constant/polyMesh

# Remove log files
rm -f log.*

# Remove processor directories
rm -rf processor*

echo "Cleaned!"
"""


def create_case(case_name: str, sim_type: str = 'airblast', explosive: str = 'TNT'):
    """Create a BlastFOAM case directory with all necessary files."""
    
    case_path = Path(case_name)
    
    # Create directories
    dirs = ['0', 'constant', 'system']
    for d in dirs:
        (case_path / d).mkdir(parents=True, exist_ok=True)
    
    # Get explosive parameters
    exp_params = JWL_PARAMS.get(explosive, JWL_PARAMS['TNT'])
    
    # Simulation parameters based on type
    if sim_type == 'airblast':
        domain = {'x_min': -20, 'x_max': 20, 'y_min': -20, 'y_max': 20, 'z_min': -20, 'z_max': 20}
        resolution = {'nx': 80, 'ny': 80, 'nz': 80}
        time_params = {'end_time': 0.01, 'delta_t': 1e-7, 'write_interval': 1e-4}
        explosive_pos = {'x': 0, 'y': 0, 'z': 0, 'radius': 0.5}
    elif sim_type == 'underwater':
        domain = {'x_min': -10, 'x_max': 10, 'y_min': -10, 'y_max': 10, 'z_min': -10, 'z_max': 10}
        resolution = {'nx': 100, 'ny': 100, 'nz': 100}
        time_params = {'end_time': 0.005, 'delta_t': 1e-8, 'write_interval': 5e-5}
        explosive_pos = {'x': 0, 'y': 0, 'z': 0, 'radius': 0.3}
    else:  # confined
        domain = {'x_min': 0, 'x_max': 10, 'y_min': 0, 'y_max': 5, 'z_min': 0, 'z_max': 5}
        resolution = {'nx': 100, 'ny': 50, 'nz': 50}
        time_params = {'end_time': 0.02, 'delta_t': 1e-7, 'write_interval': 2e-4}
        explosive_pos = {'x': 1, 'y': 2.5, 'z': 2.5, 'radius': 0.3}
    
    # Write system files
    system_path = case_path / 'system'
    
    # controlDict
    with open(system_path / 'controlDict', 'w') as f:
        f.write(CONTROL_DICT_TEMPLATE.format(**time_params))
    
    # fvSchemes
    with open(system_path / 'fvSchemes', 'w') as f:
        f.write(FV_SCHEMES_TEMPLATE)
    
    # fvSolution
    with open(system_path / 'fvSolution', 'w') as f:
        f.write(FV_SOLUTION_TEMPLATE)
    
    # blockMeshDict
    with open(system_path / 'blockMeshDict', 'w') as f:
        f.write(BLOCK_MESH_DICT_TEMPLATE.format(**domain, **resolution))
    
    # setFieldsDict
    with open(system_path / 'setFieldsDict', 'w') as f:
        f.write(SET_FIELDS_DICT_TEMPLATE.format(
            explosive_name=explosive.lower(),
            explosive_x=explosive_pos['x'],
            explosive_y=explosive_pos['y'],
            explosive_z=explosive_pos['z'],
            explosive_radius=explosive_pos['radius']
        ))
    
    # Write constant files
    constant_path = case_path / 'constant'
    
    # phaseProperties
    with open(constant_path / 'phaseProperties', 'w') as f:
        f.write(PHASE_PROPERTIES_TEMPLATE.format(
            explosive_name=explosive.lower(),
            explosive_x=explosive_pos['x'],
            explosive_y=explosive_pos['y'],
            explosive_z=explosive_pos['z'],
            **exp_params
        ))
    
    # Write initial conditions (0 directory)
    zero_path = case_path / '0'
    
    # Pressure
    with open(zero_path / 'p', 'w') as f:
        f.write(INITIAL_CONDITIONS_TEMPLATE.format(
            field_name='p',
            dims='1 -1 -2 0 0 0 0',
            value='101325'
        ))
    
    # Temperature
    with open(zero_path / 'T', 'w') as f:
        f.write(INITIAL_CONDITIONS_TEMPLATE.format(
            field_name='T',
            dims='0 0 0 1 0 0 0',
            value='293'
        ))
    
    # Velocity
    with open(zero_path / 'U', 'w') as f:
        f.write(VELOCITY_TEMPLATE)
    
    # Alpha fields
    for phase in ['air', explosive.lower()]:
        default_val = '1' if phase == 'air' else '0'
        with open(zero_path / f'alpha.{phase}', 'w') as f:
            f.write(INITIAL_CONDITIONS_TEMPLATE.format(
                field_name=f'alpha.{phase}',
                dims='0 0 0 0 0 0 0',
                value=default_val
            ))
    
    # Write run scripts
    with open(case_path / 'Allrun', 'w') as f:
        f.write(ALLRUN_TEMPLATE)
    os.chmod(case_path / 'Allrun', 0o755)
    
    with open(case_path / 'Allclean', 'w') as f:
        f.write(ALLCLEAN_TEMPLATE)
    os.chmod(case_path / 'Allclean', 0o755)
    
    print(f"✓ Case '{case_name}' created successfully!")
    print(f"  Type: {sim_type}")
    print(f"  Explosive: {explosive}")
    print(f"\nTo run:")
    print(f"  cd {case_name}")
    print(f"  ./Allrun")
    
    return case_path


def main():
    parser = argparse.ArgumentParser(
        description='Generate BlastFOAM case directory',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('case_name', help='Name of the case directory')
    parser.add_argument('--type', choices=['airblast', 'underwater', 'confined'],
                        default='airblast', help='Type of simulation')
    parser.add_argument('--explosive', choices=['TNT', 'C4', 'RDX'],
                        default='TNT', help='Type of explosive')
    
    args = parser.parse_args()
    create_case(args.case_name, args.type, args.explosive)


if __name__ == '__main__':
    main()
