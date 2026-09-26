"""Every model folder under the QA runs folder, against README's table:
the files on disk, manifest keys, `outputs` vs disk, `missing`, `failed`,
MODEL.json round-trip through load_case, and each gauge summary CSV
against the gauge TSV (peak overpressure recomputed with numpy)."""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qa_common as Q  # noqa: E402

PLAN_KEYS = {'model', 'runs_dir', 'created', 'finished', 'solver', 'dim',
             'case_file', 'git_commit', 'stop_reason', 'n_cells', 'n_procs',
             'n_steps', 'wsl_scratch', 'outputs', 'missing', 'vtk', 'failed'}


def one(folder, out):
    m_path = os.path.join(folder, 'manifest.json')
    if not os.path.isfile(m_path):
        return
    files = Q.tree(folder)
    with open(m_path, encoding='utf-8') as f:
        m = json.load(f)
    rec = dict(folder=os.path.relpath(folder, Q.RUNS),
               top=sorted({p.split('/')[0] for p, _s in files}),
               keys_extra=sorted(set(m) - PLAN_KEYS),
               keys_missing=sorted(PLAN_KEYS - set(m)) if 'chain' not in m
               else 'chain root',
               missing=m.get('missing'), failed=m.get('failed'),
               stop_reason=m.get('stop_reason'), solver=m.get('solver'),
               n=(m.get('n_cells'), m.get('n_procs'), m.get('n_steps')),
               wsl_scratch=m.get('wsl_scratch'), vtk=m.get('vtk'),
               empty=[p for p, s in files if s == 0])
    if 'outputs' in m:
        listed = {o['path']: o.get('bytes') for o in m['outputs']}
        disk = {p: s for p, s in files
                if p not in ('manifest.json', '.blastlab-model')
                and not p.startswith(('1d/', '2d/', '3d/'))}
        rec['outputs_equal_disk'] = sorted(listed) == sorted(disk)
        rec['only_listed'] = sorted(set(listed) - set(disk))
        rec['only_disk'] = sorted(set(disk) - set(listed))
        rec['size_mismatch'] = sorted(p for p in set(listed) & set(disk)
                                      if listed[p] is not None
                                      and listed[p] != disk[p])
    mj = os.path.join(folder, 'MODEL.json')
    if os.path.isfile(mj):
        try:
            from blastlab.core.case import load_case
            c = load_case(mj)
            rec['model_json_loads'] = type(c).__name__
            rec['model_json_paths'] = {k: getattr(c, k, None) for k in (
                'gauge_file', 'anim_file', 'profile_file', 'profile_file_in',
                'trigger_file')}
        except Exception as exc:
            rec['model_json_loads'] = f'ERROR {exc}'
    # the gauge summary against the TSV
    gdir = os.path.join(folder, 'gauges')
    if os.path.isdir(gdir):
        import numpy as np
        for n in os.listdir(gdir):
            if n.endswith('_summary.csv'):
                tsv = os.path.join(gdir, n.replace('_summary.csv', '.txt'))
                with open(os.path.join(gdir, n), encoding='utf-8') as f:
                    rows = list(csv.DictReader(f))
                try:
                    d = np.genfromtxt(tsv, comments='#', skip_header=1)
                    if d.ndim == 1:
                        d = d[None, :]
                    p0 = 101325.0
                    tsv_peak = [round((float(np.max(d[:, k])) - p0) / 1e3, 1)
                                for k in range(1, d.shape[1])]
                except Exception as exc:
                    tsv_peak = f'ERROR {exc}'
                rec.setdefault('gauges', []).append(dict(
                    csv=n, csv_peak=[r.get('peak_overpressure_kPa')
                                     for r in rows],
                    tsv_peak_minus_101325=tsv_peak))
    out.append(rec)


def main():
    out = []
    for root, dirs, _files in os.walk(Q.RUNS):
        dirs.sort()
        one(root, out)
    path = os.path.join(Q.OUT, 'folders.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=1, default=str)
    for r in out:
        print(json.dumps(r, default=str)[:1200])


if __name__ == '__main__':
    Q.private_env()
    main()
