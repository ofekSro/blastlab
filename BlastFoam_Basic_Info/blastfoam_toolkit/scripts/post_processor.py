#!/usr/bin/env python3
"""
BlastFOAM Post-Processing Tool
==============================
כלי לניתוח ועיבוד תוצאות מסימולציות BlastFOAM.

Usage:
    python post_processor.py <case_path> [--probe PROBE_ID] [--plot] [--export CSV_FILE]
    
Features:
    - קריאת נתוני probes (לחץ, טמפרטורה, מהירות)
    - חישוב לחץ-על שיא ואימפולס
    - יצירת גרפים
    - ייצוא לקבצי CSV
    
Example:
    python post_processor.py ./myBlast --probe 0 --plot
    python post_processor.py ./myBlast --export results.csv
"""

import os
import sys
import argparse
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import json


def read_probe_data(case_path: str, field: str = 'p') -> Dict:
    """
    קריאת נתוני probe מתיקיית הסימולציה.
    
    Args:
        case_path: נתיב לתיקיית ה-case
        field: שדה לקריאה (p, T, U, rho)
    
    Returns:
        Dictionary עם נתוני הזמן והערכים לכל probe
    """
    probe_path = Path(case_path) / 'postProcessing' / 'probes'
    
    if not probe_path.exists():
        print(f"Error: Probe data not found at {probe_path}")
        return {}
    
    # מצא את תיקיית הזמן האחרונה
    time_dirs = sorted([d for d in probe_path.iterdir() if d.is_dir()], 
                       key=lambda x: float(x.name))
    
    if not time_dirs:
        print("Error: No time directories found")
        return {}
    
    results = {
        'times': [],
        'probes': {},
        'field': field,
        'units': get_field_units(field)
    }
    
    # קרא את קובץ השדה
    field_file = time_dirs[0] / field
    if not field_file.exists():
        print(f"Error: Field file '{field}' not found")
        return {}
    
    with open(field_file, 'r') as f:
        lines = f.readlines()
    
    # פרש את הנתונים
    probe_count = 0
    for line in lines:
        line = line.strip()
        if line.startswith('#') or not line:
            # שורת כותרת - ספור probes
            if 'Probe' in line:
                probe_count = len(re.findall(r'Probe \d+', line))
            continue
        
        values = line.split()
        if not values:
            continue
        
        try:
            time = float(values[0])
            results['times'].append(time)
            
            for i, val in enumerate(values[1:]):
                probe_id = i
                if probe_id not in results['probes']:
                    results['probes'][probe_id] = []
                
                # טיפול בוקטורים (למשל מהירות)
                if val.startswith('('):
                    # וקטור - קח את הגודל
                    vec_str = val.strip('()')
                    components = [float(c) for c in vec_str.split()]
                    magnitude = sum(c**2 for c in components) ** 0.5
                    results['probes'][probe_id].append(magnitude)
                else:
                    results['probes'][probe_id].append(float(val))
        except (ValueError, IndexError) as e:
            continue
    
    return results


def get_field_units(field: str) -> str:
    """החזר יחידות לשדה נתון."""
    units = {
        'p': 'Pa',
        'T': 'K',
        'U': 'm/s',
        'rho': 'kg/m³'
    }
    return units.get(field, '')


def calculate_peak_overpressure(probe_data: Dict, p_ref: float = 101325) -> Dict:
    """
    חישוב לחץ-על שיא לכל probe.
    
    Args:
        probe_data: נתונים מ-read_probe_data
        p_ref: לחץ ייחוס (אטמוספרי)
    
    Returns:
        Dictionary עם לחץ-על שיא וזמן הגעה לכל probe
    """
    if probe_data.get('field') != 'p':
        print("Warning: Peak overpressure requires pressure field")
        return {}
    
    results = {}
    
    for probe_id, pressures in probe_data['probes'].items():
        overpressures = [p - p_ref for p in pressures]
        max_op = max(overpressures)
        max_idx = overpressures.index(max_op)
        arrival_time = probe_data['times'][max_idx]
        
        # מצא זמן הגעה (10% מעל לחץ ייחוס)
        threshold = p_ref * 1.1
        for i, p in enumerate(pressures):
            if p > threshold:
                arrival_time = probe_data['times'][i]
                break
        
        results[probe_id] = {
            'peak_overpressure_Pa': max_op,
            'peak_overpressure_kPa': max_op / 1000,
            'arrival_time_s': arrival_time,
            'arrival_time_ms': arrival_time * 1000
        }
    
    return results


def calculate_impulse(probe_data: Dict, p_ref: float = 101325) -> Dict:
    """
    חישוב אימפולס (אינטגרל הלחץ-על על הזמן).
    
    Args:
        probe_data: נתונים מ-read_probe_data
        p_ref: לחץ ייחוס
    
    Returns:
        Dictionary עם אימפולס לכל probe
    """
    if probe_data.get('field') != 'p':
        print("Warning: Impulse calculation requires pressure field")
        return {}
    
    results = {}
    times = probe_data['times']
    
    for probe_id, pressures in probe_data['probes'].items():
        # חשב אימפולס חיובי (רק כשהלחץ מעל הייחוס)
        impulse = 0.0
        for i in range(1, len(times)):
            dt = times[i] - times[i-1]
            op = pressures[i] - p_ref
            if op > 0:
                impulse += op * dt
        
        results[probe_id] = {
            'positive_impulse_Pa_s': impulse,
            'positive_impulse_kPa_ms': impulse
        }
    
    return results


def export_to_csv(data: Dict, output_file: str):
    """
    ייצוא נתונים לקובץ CSV.
    
    Args:
        data: נתוני probe
        output_file: שם קובץ הפלט
    """
    if not data:
        print("Error: No data to export")
        return
    
    with open(output_file, 'w') as f:
        # כותרות
        headers = ['Time'] + [f'Probe_{i}' for i in sorted(data['probes'].keys())]
        f.write(','.join(headers) + '\n')
        
        # נתונים
        for i, time in enumerate(data['times']):
            row = [str(time)]
            for probe_id in sorted(data['probes'].keys()):
                if i < len(data['probes'][probe_id]):
                    row.append(str(data['probes'][probe_id][i]))
                else:
                    row.append('')
            f.write(','.join(row) + '\n')
    
    print(f"✓ Data exported to {output_file}")


def create_gnuplot_script(data: Dict, output_prefix: str):
    """
    יצירת סקריפט gnuplot לויזואליזציה.
    
    Args:
        data: נתוני probe
        output_prefix: קידומת לקבצי הפלט
    """
    script = f"""# BlastFOAM Pressure Plot
set terminal pngcairo size 1200,800 enhanced font 'Arial,12'
set output '{output_prefix}_pressure.png'

set xlabel 'Time [s]'
set ylabel 'Pressure [Pa]'
set title 'Pressure History at Probe Locations'
set grid
set key outside right

plot """
    
    plot_commands = []
    for probe_id in sorted(data['probes'].keys()):
        plot_commands.append(f"'{output_prefix}.csv' using 1:{probe_id+2} with lines title 'Probe {probe_id}'")
    
    script += ', \\\n     '.join(plot_commands)
    
    script_file = f"{output_prefix}_plot.gp"
    with open(script_file, 'w') as f:
        f.write(script)
    
    print(f"✓ Gnuplot script created: {script_file}")
    print(f"  Run: gnuplot {script_file}")


def print_summary(probe_data: Dict, peak_op: Dict, impulse: Dict):
    """הדפסת סיכום תוצאות."""
    print("\n" + "="*60)
    print("BlastFOAM Analysis Summary")
    print("="*60)
    
    print(f"\nField: {probe_data.get('field', 'Unknown')} [{probe_data.get('units', '')}]")
    print(f"Time range: {min(probe_data['times']):.6f} - {max(probe_data['times']):.6f} s")
    print(f"Number of probes: {len(probe_data['probes'])}")
    
    if peak_op:
        print("\n--- Peak Overpressure ---")
        print(f"{'Probe':<8} {'Peak OP [kPa]':<15} {'Arrival [ms]':<15}")
        print("-"*40)
        for probe_id in sorted(peak_op.keys()):
            data = peak_op[probe_id]
            print(f"{probe_id:<8} {data['peak_overpressure_kPa']:<15.2f} {data['arrival_time_ms']:<15.4f}")
    
    if impulse:
        print("\n--- Positive Impulse ---")
        print(f"{'Probe':<8} {'Impulse [kPa·ms]':<20}")
        print("-"*30)
        for probe_id in sorted(impulse.keys()):
            data = impulse[probe_id]
            print(f"{probe_id:<8} {data['positive_impulse_kPa_ms']:<20.4f}")


def main():
    parser = argparse.ArgumentParser(
        description='BlastFOAM Post-Processing Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('case_path', help='Path to BlastFOAM case directory')
    parser.add_argument('--field', choices=['p', 'T', 'U', 'rho'],
                        default='p', help='Field to analyze')
    parser.add_argument('--probe', type=int, help='Specific probe ID to analyze')
    parser.add_argument('--export', metavar='FILE', help='Export data to CSV file')
    parser.add_argument('--plot', action='store_true', help='Generate gnuplot script')
    parser.add_argument('--pref', type=float, default=101325,
                        help='Reference pressure [Pa]')
    
    args = parser.parse_args()
    
    # קרא נתונים
    print(f"Reading probe data from: {args.case_path}")
    probe_data = read_probe_data(args.case_path, args.field)
    
    if not probe_data:
        print("Failed to read probe data")
        sys.exit(1)
    
    # חשב מדדים
    peak_op = {}
    impulse = {}
    
    if args.field == 'p':
        peak_op = calculate_peak_overpressure(probe_data, args.pref)
        impulse = calculate_impulse(probe_data, args.pref)
    
    # הצג סיכום
    print_summary(probe_data, peak_op, impulse)
    
    # ייצא אם נדרש
    if args.export:
        export_to_csv(probe_data, args.export)
        
        if args.plot:
            prefix = args.export.rsplit('.', 1)[0]
            create_gnuplot_script(probe_data, prefix)


if __name__ == '__main__':
    main()
