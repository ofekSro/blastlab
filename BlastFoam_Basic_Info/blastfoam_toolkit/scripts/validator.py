#!/usr/bin/env python3
"""
BlastFOAM Case Validator
========================
כלי לבדיקת תקינות מקרי סימולציה של BlastFOAM.

Usage:
    python validator.py <case_path> [--fix]
    
Features:
    - בדיקת קיום כל הקבצים הנדרשים
    - וידוא עקביות פרמטרים
    - בדיקת תנאי התחלה
    - הצעות לתיקון בעיות נפוצות
    
Example:
    python validator.py ./myBlast
    python validator.py ./myBlast --fix  # תקן בעיות אוטומטית
"""

import os
import sys
import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional

# צבעים לפלט
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def ok(msg: str):
    print(f"  {Colors.GREEN}✓{Colors.RESET} {msg}")

def warn(msg: str):
    print(f"  {Colors.YELLOW}⚠{Colors.RESET} {msg}")

def error(msg: str):
    print(f"  {Colors.RED}✗{Colors.RESET} {msg}")


# קבצים נדרשים
REQUIRED_FILES = {
    'system': [
        'controlDict',
        'fvSchemes',
        'fvSolution',
        'blockMeshDict'
    ],
    'constant': [
        'phaseProperties'
    ],
    '0': [
        'p',
        'T',
        'U'
    ]
}

# בדיקות ספציפיות
CHECKS = {
    'controlDict': {
        'required_keywords': ['application', 'startTime', 'endTime', 'deltaT'],
        'recommended_keywords': ['adjustTimeStep', 'maxCo']
    },
    'fvSchemes': {
        'required_keywords': ['ddtSchemes', 'gradSchemes', 'divSchemes', 'laplacianSchemes'],
        'recommended_keywords': ['fluxScheme', 'interpolationSchemes']
    },
    'phaseProperties': {
        'required_keywords': ['phases'],
        'recommended_keywords': []
    }
}


def check_file_exists(case_path: Path, relative_path: str) -> bool:
    """בדוק אם קובץ קיים."""
    return (case_path / relative_path).exists()


def read_openfoam_dict(file_path: Path) -> str:
    """קרא קובץ OpenFOAM והחזר את תוכנו."""
    if not file_path.exists():
        return ""
    
    with open(file_path, 'r') as f:
        return f.read()


def check_keywords(content: str, keywords: List[str]) -> Tuple[List[str], List[str]]:
    """בדוק אילו מילות מפתח קיימות ואילו חסרות."""
    found = []
    missing = []
    
    for kw in keywords:
        if re.search(rf'\b{kw}\b', content):
            found.append(kw)
        else:
            missing.append(kw)
    
    return found, missing


def check_mesh_quality(case_path: Path) -> Dict:
    """בדוק איכות הרשת אם קיימת."""
    mesh_path = case_path / 'constant' / 'polyMesh'
    
    result = {
        'exists': mesh_path.exists(),
        'has_points': (mesh_path / 'points').exists() if mesh_path.exists() else False,
        'has_faces': (mesh_path / 'faces').exists() if mesh_path.exists() else False,
        'has_cells': (mesh_path / 'owner').exists() if mesh_path.exists() else False
    }
    
    return result


def estimate_cell_count(case_path: Path) -> Optional[int]:
    """הערכת מספר התאים מ-blockMeshDict."""
    block_mesh_path = case_path / 'system' / 'blockMeshDict'
    
    if not block_mesh_path.exists():
        return None
    
    content = read_openfoam_dict(block_mesh_path)
    
    # חפש את הגדרת הבלוקים
    match = re.search(r'\((\d+)\s+(\d+)\s+(\d+)\)', content)
    if match:
        nx, ny, nz = int(match.group(1)), int(match.group(2)), int(match.group(3))
        return nx * ny * nz
    
    return None


def check_time_settings(case_path: Path) -> Dict:
    """בדוק הגדרות זמן."""
    control_dict = case_path / 'system' / 'controlDict'
    content = read_openfoam_dict(control_dict)
    
    result = {
        'deltaT': None,
        'endTime': None,
        'maxCo': None,
        'adjustTimeStep': False
    }
    
    # חלץ ערכים
    dt_match = re.search(r'deltaT\s+([0-9eE\-\+\.]+)', content)
    if dt_match:
        result['deltaT'] = float(dt_match.group(1))
    
    end_match = re.search(r'endTime\s+([0-9eE\-\+\.]+)', content)
    if end_match:
        result['endTime'] = float(end_match.group(1))
    
    co_match = re.search(r'maxCo\s+([0-9eE\-\+\.]+)', content)
    if co_match:
        result['maxCo'] = float(co_match.group(1))
    
    if 'adjustTimeStep' in content and 'yes' in content:
        result['adjustTimeStep'] = True
    
    return result


def check_phase_properties(case_path: Path) -> Dict:
    """בדוק הגדרות פאזות."""
    phase_props = case_path / 'constant' / 'phaseProperties'
    content = read_openfoam_dict(phase_props)
    
    result = {
        'phases': [],
        'has_air': False,
        'has_explosive': False,
        'activation_model': None
    }
    
    # חפש פאזות
    phases_match = re.search(r'phases\s*\((.*?)\)', content, re.DOTALL)
    if phases_match:
        phases = phases_match.group(1).split()
        result['phases'] = phases
        result['has_air'] = 'air' in phases
        
        # בדוק אם יש חומר נפץ (לא אוויר)
        explosives = [p for p in phases if p.lower() not in ['air', 'water']]
        result['has_explosive'] = len(explosives) > 0
    
    # בדוק מודל הפעלה
    act_match = re.search(r'activationModel\s+(\w+)', content)
    if act_match:
        result['activation_model'] = act_match.group(1)
    
    return result


def check_boundary_conditions(case_path: Path) -> Dict:
    """בדוק תנאי שפה."""
    zero_path = case_path / '0'
    
    result = {
        'fields_checked': [],
        'issues': []
    }
    
    if not zero_path.exists():
        result['issues'].append("Directory '0' not found")
        return result
    
    for field_file in zero_path.iterdir():
        if field_file.is_file():
            content = read_openfoam_dict(field_file)
            
            if 'boundaryField' not in content:
                result['issues'].append(f"Missing boundaryField in {field_file.name}")
            
            result['fields_checked'].append(field_file.name)
    
    return result


def validate_case(case_path: str, auto_fix: bool = False) -> bool:
    """
    וידוא מלא של מקרה BlastFOAM.
    
    Returns:
        True אם המקרה תקין, False אחרת
    """
    case_path = Path(case_path)
    issues = []
    warnings = []
    
    print(f"\n{Colors.BOLD}BlastFOAM Case Validator{Colors.RESET}")
    print(f"Case: {case_path.absolute()}")
    print("="*60)
    
    # בדיקה 1: קיום תיקיות וקבצים
    print(f"\n{Colors.BOLD}1. Checking Required Files{Colors.RESET}")
    
    for directory, files in REQUIRED_FILES.items():
        dir_path = case_path / directory
        if not dir_path.exists():
            error(f"Missing directory: {directory}/")
            issues.append(f"Missing directory: {directory}")
            continue
        
        for filename in files:
            file_path = dir_path / filename
            if file_path.exists():
                ok(f"{directory}/{filename}")
            else:
                error(f"Missing: {directory}/{filename}")
                issues.append(f"Missing file: {directory}/{filename}")
    
    # בדיקה 2: מילות מפתח בקבצים
    print(f"\n{Colors.BOLD}2. Checking File Contents{Colors.RESET}")
    
    for filename, checks in CHECKS.items():
        # מצא את הקובץ
        for directory in REQUIRED_FILES.keys():
            file_path = case_path / directory / filename
            if file_path.exists():
                content = read_openfoam_dict(file_path)
                
                found, missing = check_keywords(content, checks['required_keywords'])
                
                if missing:
                    error(f"{filename}: Missing required keywords: {', '.join(missing)}")
                    issues.extend([f"{filename}: Missing {kw}" for kw in missing])
                else:
                    ok(f"{filename}: All required keywords present")
                
                # בדוק מומלצים
                found_rec, missing_rec = check_keywords(content, checks['recommended_keywords'])
                if missing_rec:
                    warn(f"{filename}: Recommended keywords missing: {', '.join(missing_rec)}")
                    warnings.extend([f"{filename}: Recommended {kw}" for kw in missing_rec])
                break
    
    # בדיקה 3: הגדרות זמן
    print(f"\n{Colors.BOLD}3. Checking Time Settings{Colors.RESET}")
    
    time_settings = check_time_settings(case_path)
    
    if time_settings['deltaT']:
        ok(f"deltaT = {time_settings['deltaT']}")
        
        if time_settings['deltaT'] > 1e-5:
            warn("deltaT might be too large for blast simulations")
            warnings.append("deltaT might be too large")
    else:
        error("deltaT not defined")
        issues.append("Missing deltaT")
    
    if time_settings['endTime']:
        ok(f"endTime = {time_settings['endTime']}")
    
    if time_settings['maxCo']:
        if time_settings['maxCo'] <= 0.5:
            ok(f"maxCo = {time_settings['maxCo']} (good for blast)")
        else:
            warn(f"maxCo = {time_settings['maxCo']} (recommend <= 0.5 for blast)")
            warnings.append("maxCo should be <= 0.5 for blast simulations")
    
    if time_settings['adjustTimeStep']:
        ok("Adaptive time stepping enabled")
    else:
        warn("Consider enabling adjustTimeStep")
        warnings.append("adjustTimeStep not enabled")
    
    # בדיקה 4: הגדרות פאזות
    print(f"\n{Colors.BOLD}4. Checking Phase Properties{Colors.RESET}")
    
    phase_info = check_phase_properties(case_path)
    
    if phase_info['phases']:
        ok(f"Phases defined: {', '.join(phase_info['phases'])}")
    else:
        error("No phases defined")
        issues.append("No phases defined in phaseProperties")
    
    if phase_info['has_air']:
        ok("Air phase present")
    else:
        warn("No air phase found")
        warnings.append("No air phase")
    
    if phase_info['has_explosive']:
        ok("Explosive phase present")
        if phase_info['activation_model']:
            ok(f"Activation model: {phase_info['activation_model']}")
        else:
            warn("No activation model specified")
            warnings.append("No activation model")
    
    # בדיקה 5: רשת
    print(f"\n{Colors.BOLD}5. Checking Mesh{Colors.RESET}")
    
    mesh_info = check_mesh_quality(case_path)
    
    if mesh_info['exists']:
        ok("polyMesh directory exists")
        if mesh_info['has_points'] and mesh_info['has_faces'] and mesh_info['has_cells']:
            ok("Mesh files present")
        else:
            warn("Some mesh files might be missing (run blockMesh first)")
    else:
        warn("No mesh found (run blockMesh to generate)")
    
    cell_count = estimate_cell_count(case_path)
    if cell_count:
        ok(f"Estimated cell count: {cell_count:,}")
        if cell_count > 1e6:
            warn("Large mesh - consider parallel running")
            warnings.append("Large mesh detected")
    
    # בדיקה 6: תנאי שפה
    print(f"\n{Colors.BOLD}6. Checking Boundary Conditions{Colors.RESET}")
    
    bc_info = check_boundary_conditions(case_path)
    
    if bc_info['fields_checked']:
        ok(f"Fields checked: {', '.join(bc_info['fields_checked'])}")
    
    for issue in bc_info['issues']:
        error(issue)
        issues.append(issue)
    
    # סיכום
    print(f"\n{'='*60}")
    print(f"{Colors.BOLD}Summary{Colors.RESET}")
    print(f"{'='*60}")
    
    if not issues:
        print(f"\n{Colors.GREEN}✓ Case validation passed!{Colors.RESET}")
    else:
        print(f"\n{Colors.RED}✗ Found {len(issues)} issue(s):{Colors.RESET}")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
    
    if warnings:
        print(f"\n{Colors.YELLOW}⚠ Found {len(warnings)} warning(s):{Colors.RESET}")
        for i, warning in enumerate(warnings, 1):
            print(f"  {i}. {warning}")
    
    print()
    return len(issues) == 0


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Validate BlastFOAM case directory'
    )
    parser.add_argument('case_path', help='Path to case directory')
    parser.add_argument('--fix', action='store_true',
                        help='Attempt to fix common issues (not implemented yet)')
    
    args = parser.parse_args()
    
    if not Path(args.case_path).exists():
        print(f"Error: Case directory '{args.case_path}' not found")
        sys.exit(1)
    
    success = validate_case(args.case_path, args.fix)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
