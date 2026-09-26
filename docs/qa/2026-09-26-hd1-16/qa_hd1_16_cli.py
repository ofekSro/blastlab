"""QA for batch hd1-16-load-export, part 2: the GUI run's CSVs against the
core, the HTML report text, and the `--hd13-wall-export` CLI cross-check.
Throwaway, docs/qa. Writes only under SCR. No WSL.

Run:  python qa_hd1_16_cli.py <scratch_dir>
"""
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import replace

import numpy as np

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, REPO)
SCR = os.path.abspath(sys.argv[1])
os.environ['BLASTLAB_SETTINGS'] = os.path.join(SCR, 'settings.json')

from blastlab.core import assessment                          # noqa: E402
from blastlab.core.constants import P_AIR                     # noqa: E402

RESULTS = []


def check(name, ok, detail=''):
    RESULTS.append((name, bool(ok), str(detail)))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f' - {detail}' if detail else ''),
          flush=True)


FLOAT = re.compile(r'^[-+]?(\d+(\.\d*)?|\.\d+)([eE][-+]?\d+)?$')


def two_floats_every_line(path):
    raw = open(path, 'rb').read()
    bad = []
    if raw.startswith(b'\xef\xbb\xbf'):
        bad.append('BOM')
    if b'\r' in raw:
        bad.append('CR')
    lines = raw.decode('utf-8').split('\n')
    if lines and lines[-1] == '':
        lines = lines[:-1]
    for n, ln in enumerate(lines, 1):
        parts = ln.split(',')
        if len(parts) != 2 or not all(FLOAT.match(p) for p in parts):
            bad.append(f'line {n}: {ln!r}')
            if len(bad) > 3:
                break
    return len(lines), bad


def env():
    e = dict(os.environ)
    e['PYTHONPATH'] = REPO
    e.pop('QT_QPA_PLATFORM', None)
    return e


# ── 2. the GUI run's CSV folder, against the core ────────────────────────
print('\n2. the GUI run CSVs')
rr = json.load(open(os.path.join(SCR, 'run_result.json')))
loads = rr['loads']
files = sorted(os.listdir(loads)) if os.path.isdir(loads) else []
check('2 folder holds nominal.csv and nominal.txt', {'nominal.csv', 'nominal.txt'} <= set(files),
      str(files))
n, bad = two_floats_every_line(os.path.join(loads, 'nominal.csv'))
check('2 nominal.csv: every line exactly two comma-separated numbers, no header, no BOM/CR',
      n > 1 and not bad, f'{n} lines; problems: {bad[:3]}')
side = open(os.path.join(loads, 'nominal.txt'), encoding='utf-8').read()
print('  --- nominal.txt ---\n' + side + '  -------------------')
m = re.search(r'record ends while the load is still active: p = (\S+) kPa at t = (\S+) ms', side)
check('2 sidecar carries the still-active line', bool(m), m.group(0) if m else '')
check('2 the status line carries the same still-active text as the sidecar',
      bool(m) and m.group(0) in rr['status'], rr['status'])

# the core, called directly on the same case (the GUI ran t.json unchanged)
case = assessment.load_case(os.path.join(SCR, 't.json'))
from blastlab.services import hd13 as svc                     # noqa: E402
bundle = svc.assess(case)
conf = bundle['out']['confined']
t_csv, p_csv = [], []
for ln in open(os.path.join(loads, 'nominal.csv'), encoding='utf-8'):
    a, b = ln.split(',')
    t_csv.append(float(a))
    p_csv.append(float(b))
t_csv, p_csv = np.array(t_csv), np.array(p_csv)
t_core = 1e3 * np.asarray(conf['t'], float)
p_core = (np.asarray(conf['p'], float) - P_AIR) / 1e3
same_len = len(t_csv) == len(t_core)
check('2 CSV rows == core samples', same_len, f'{len(t_csv)} vs {len(t_core)}')
if same_len:
    check('2 CSV t [ms] == 1e3 * core t, bit for bit', np.array_equal(t_csv, t_core),
          f'max |d| {np.max(np.abs(t_csv - t_core)):.3g}')
    check('2 CSV p [kPa] == (core p - P_AIR)/1e3, bit for bit', np.array_equal(p_csv, p_core),
          f'max |d| {np.max(np.abs(p_csv - p_core)):.3g}')
k = int(np.argmax(p_core))
NUM = dict(peak_kpa_core=float(p_core[k]), t_peak_ms_core=float(t_core[k]),
           peak_kpa_csv=float(p_csv.max()), t_peak_ms_csv=float(t_csv[int(np.argmax(p_csv))]),
           last_kpa_core=float(p_core[-1]), last_t_ms_core=float(t_core[-1]),
           last_kpa_csv=float(p_csv[-1]), last_t_ms_csv=float(t_csv[-1]),
           p_max_mpa_core=conf['p_max'] / 1e6,
           impulse_core=float(np.trapezoid(p_core, t_core)))
if m:
    NUM['still_active_p_shown'] = float(m.group(1))
    NUM['still_active_t_shown'] = float(m.group(2))
json.dump(NUM, open(os.path.join(SCR, 'numbers.json'), 'w'), indent=1)
print('  numbers', NUM)
# sidecar peak / impulse lines vs core
mp = re.search(r'peak overpressure: (\S+) kPa at t = (\S+) ms', side)
mi = re.search(r'negative phase included\): (\S+) kPa\*ms', side)
check('2 sidecar peak matches core to 6 s.f.',
      mp and abs(float(mp.group(1)) - NUM['peak_kpa_core']) <= 5e-6 * abs(NUM['peak_kpa_core']),
      f"{mp.group(1) if mp else None} vs {NUM['peak_kpa_core']!r}")
check('2 sidecar net impulse matches trapezoid of the core columns',
      mi and abs(float(mi.group(1)) - NUM['impulse_core']) <= 1e-12 * abs(NUM['impulse_core']) + 1e-12,
      f"{mi.group(1) if mi else None} vs {NUM['impulse_core']!r}")

# ── 3. the HTML report text ──────────────────────────────────────────────
print('\n3. the report')
html = open(rr['report'], encoding='utf-8').read()
for word in ('Structural response', 'Does that verdict survive', 'Ductility', 'ductility',
             'Support rotation', 'survives_across_band', 'fails_across_band',
             'undetermined_within_band', 'COLLAPSE', 'SDOF', 'verdict'):
    check(f'3 report has no {word!r}', word not in html,
          f'{html.count(word)} hits' + (': ' + html[max(0, html.find(word) - 80):
                                                   html.find(word) + 80].replace('\n', ' ')
                                        if word in html else ''))
imgs = re.findall(r'<img[^>]*alt="([^"]*)"', html)
heads = re.findall(r'<h[1-3][^>]*>(.*?)</h[1-3]>', html)
print('  headings:', heads)
print('  figures (alt):', imgs)
json.dump({'headings': heads, 'imgs': imgs, 'len': len(html)},
          open(os.path.join(SCR, 'report_outline.json'), 'w'), indent=1)

# ── 4. CLI --hd13-wall-export ─────────────────────────────────────────────
print('\n4. --hd13-wall-export')
wx = os.path.join(SCR, 'wx')
shutil.rmtree(wx, ignore_errors=True)
os.makedirs(wx)
cpath = os.path.join(wx, 'case.json')
shutil.copyfile(os.path.join(SCR, 't.json'), cpath)
outdir = os.path.join(wx, 'case_wall_loads')


def cli(tag):
    p = subprocess.run([sys.executable, '-m', 'blastlab', '--hd13-wall-export', cpath],
                       cwd=wx, env=env(), capture_output=True, text=True, timeout=300)
    open(os.path.join(SCR, f'cli_{tag}.txt'), 'w', encoding='utf-8').write(
        f'exit {p.returncode}\n--- stdout ---\n{p.stdout}\n--- stderr ---\n{p.stderr}')
    print(f'  [{tag}] exit {p.returncode}\n' + p.stdout + (p.stderr[-800:] if p.stderr else ''))
    return p


def listing():
    return sorted(os.listdir(outdir)) if os.path.isdir(outdir) else []


def all_csv_ok():
    probs = {}
    for f in listing():
        if f.endswith('.csv'):
            n_, b_ = two_floats_every_line(os.path.join(outdir, f))
            if b_ or n_ < 2:
                probs[f] = b_[:2]
    return probs


from blastlab.output import load_csv as LC                    # noqa: E402
_, G1 = LC.read_hd13_table(os.path.join(LC.WALL_LOAD_DIR, LC.G1_FILE), LC.G1_UNITS)
_, PL = LC.read_hd13_table(os.path.join(LC.WALL_LOAD_DIR, LC.PLANE_FILE), LC.PLANE_UNITS)


def read(name):
    return LC.read_trace(os.path.join(outdir, name))


OFF = ['G1_g124.csv', 'G1_g124.txt', 'G1_g140.csv', 'G1_g140.txt',
       'planemax_g124.csv', 'planemax_g124.txt', 'planemax_g140.csv', 'planemax_g140.txt']
ON = ['G1_g124_cleared.csv', 'G1_g124_cleared.txt', 'G1_g140_cleared.csv',
      'G1_g140_cleared.txt', 'planemax_g124.csv', 'planemax_g124.txt',
      'planemax_g140.csv', 'planemax_g140.txt']

p = cli('off')
check('4 clearing off: exit 0', p.returncode == 0)
check('4 clearing off: exactly the 4 CSVs + 4 sidecars', listing() == sorted(OFF), str(listing()))
check('4 clearing off: every CSV line is exactly two floats', not all_csv_ok(), str(all_csv_ok()))
for g, tag in (('1.24', 'g124'), ('1.40', 'g140')):
    t_, p_ = read(f'G1_{tag}.csv')
    check(f'4 off: G1_{tag} == file E_{g}/1e3 bit for bit, t == 1e3 t',
          np.array_equal(p_, G1[f'E_{g}'] / 1e3) and np.array_equal(t_, 1e3 * G1['t']),
          f'peak {p_.max():.6g} kPa vs file {G1[f"E_{g}"].max() / 1e3:.6g}')
    t_, p_ = read(f'planemax_{tag}.csv')
    check(f'4 off: planemax_{tag} == file Emax_{g}/1e3 bit for bit',
          np.array_equal(p_, PL[f'Emax_{g}'] / 1e3) and np.array_equal(t_, 1e3 * PL['t']))
off_planemax = {tag: read(f'planemax_{tag}.csv') for tag in ('g124', 'g140')}

# clearing on, H=3, W=4 (written through the case model, as the GUI saves it)
assessment.save_case(replace(assessment.load_case(cpath), clearing=True,
                             wall_H_m=3.0, wall_W_m=4.0), cpath)
p = cli('on')
check('4 clearing on: exit 0', p.returncode == 0)
check('4 clearing on: only G1 gets _cleared; no stale unrelieved G1 left',
      listing() == sorted(ON), str(listing()))
check('4 clearing on: every CSV line is exactly two floats', not all_csv_ok(), str(all_csv_ok()))
for tag in ('g124', 'g140'):
    t_, p_ = read(f'planemax_{tag}.csv')
    check(f'4 on: planemax_{tag} unchanged from clearing off (never relieved)',
          np.array_equal(p_, off_planemax[tag][1]) and np.array_equal(t_, off_planemax[tag][0]))

# independent clearing construction (UFC 3-340-02 para. 2-15.3.2, Eq. 2-8/2-9)
S_, G_ = min(3.0, 4.0 / 2), max(3.0, 4.0 / 2)
R_ = S_ / G_
ps = np.interp(G1['t'], PL['t'], PL['G1cell_p'] - P_AIR)
un = np.maximum(PL['G1cell_Ux'], 0.0)
q = np.interp(G1['t'], PL['t'], 0.5 * PL['G1cell_rho'] * un * un)
for g, tag in (('1.24', 'g124'), ('1.40', 'g140')):
    side_c = open(os.path.join(outdir, f'G1_{tag}_cleared.txt'), encoding='utf-8').read()
    mc = re.search(r'C_r = (\S+) m/s', side_c)
    mt = re.search(r't_c = 4 S / \(\(1 \+ R\) C_r\) = (\S+) ms', side_c)
    c_r = float(mc.group(1))
    tc_hand = 4 * S_ / ((1 + R_) * c_r)
    check(f'4 on {tag}: sidecar t_c == 4S/((1+R)C_r) by hand (S=2, R=2/3)',
          mt and abs(float(mt.group(1)) - tc_hand * 1e3) <= 1e-5 * tc_hand * 1e3,
          f'sidecar {mt.group(1) if mt else None} ms, hand {tc_hand * 1e3:.6g} ms, C_r {c_r:.6g} m/s')
    E = G1[f'E_{g}']
    ia = int(np.argmax(E > 0.01 * E.max()))
    ta = G1['t'][ia]
    tau = G1['t'] - ta
    # full-precision t_c from the sidecar's 6 s.f. C_r is not exact; rebuild
    # with the core's C_r for the shape check
    from blastlab.core import wallload
    r_max = float(np.max(G1[f'R_{g}']))
    c_r_core = wallload.reflected_sound_speed(
        float(wallload.incident_from_reflected(r_max, float(g), P_AIR)), float(g), P_AIR)
    tc = 4 * S_ / ((1 + R_) * c_r_core)
    w = np.clip(tau / tc, 0.0, 1.0)
    L = np.where(tau < 0, E, (1 - w) * E + w * (ps + q))
    t_, p_ = read(f'G1_{tag}_cleared.csv')
    err = np.max(np.abs(p_ - L / 1e3))
    check(f'4 on {tag}: CSV equals an independent Fig. 2-191a construction',
          err <= 1e-9 * max(1.0, np.max(np.abs(L / 1e3))),
          f'max |d| {err:.3g} kPa; peak cleared {p_.max():.6g} vs unrelieved {E.max() / 1e3:.6g} kPa; '
          f't_a {ta * 1e3:.6g} ms, t_c {tc * 1e3:.6g} ms')

# rerun with clearing on: same listing, nothing stale
p = cli('on_rerun')
check('4 clearing on, rerun: identical listing, no stale files', listing() == sorted(ON), str(listing()))
# back to clearing off: the _cleared files must go
assessment.save_case(replace(assessment.load_case(cpath), clearing=False), cpath)
p = cli('off_again')
check('4 clearing off after on: _cleared files removed, 4 unrelieved back',
      listing() == sorted(OFF), str(listing()))
# a foreign file in the folder is not touched
open(os.path.join(outdir, 'mine.csv'), 'w').write('0,1\n')
cli('off_foreign')
check('4 a user file in the folder survives a rerun', 'mine.csv' in listing())
os.remove(os.path.join(outdir, 'mine.csv'))
# clearing on, H missing: refused naming wall_H_m, nothing written
assessment.save_case(replace(assessment.load_case(cpath), clearing=True, wall_H_m=0.0,
                             wall_W_m=4.0), cpath)
before = listing()
p = cli('on_noH')
check('4 CLI clearing on with no H: non-zero exit naming wall_H_m, folder unchanged',
      p.returncode != 0 and 'wall_H_m' in (p.stderr + p.stdout) and listing() == before,
      (p.stderr or p.stdout).strip()[-300:])

json.dump(RESULTS, open(os.path.join(SCR, 'cli_results.json'), 'w'), indent=1)
nf = sum(1 for r in RESULTS if not r[1])
print(f'\nCLI/core checks: {len(RESULTS) - nf} pass, {nf} fail')
