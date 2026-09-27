"""List <MODEL>\\vtk\\ in the style of the implementer's
vtk_folder_listing.txt and check every file with a plain text/byte reader:
legacy-VTK header, every .vtk.series parses, times ascending, every named
file exists and is > 0 bytes. Writes the listing to argv[2].
Run:  python check_vtk_tree.py <MODEL folder> <listing out>
"""
import json
import os
import sys

model, out_path = sys.argv[1], sys.argv[2]
vtk = os.path.join(model, 'vtk')
lines = [f'# {model}\\vtk\\ after the QA pass real run (Qt GUI, Run button)', '']
problems = []
n_files = total = 0
for base, dirs, names in sorted(os.walk(vtk)):
    dirs.sort()
    rel = os.path.relpath(base, model).replace('\\', '/')
    names = sorted(names)
    lines.append(f'{rel}/  ({len(names)} files)')
    shown = [n for n in names if not n.startswith('t_')] + \
        [n for n in names if n.startswith('t_')][:3]
    for n in shown:
        p = os.path.join(base, n)
        lines.append(f'    {n:<40} {os.path.getsize(p):>12,} B')
    more = len([n for n in names if n.startswith('t_')]) - 3
    if more > 0:
        lines.append(f'    ... {more} more t_<time>.vtk')
    for n in names:
        p = os.path.join(base, n)
        sz = os.path.getsize(p)
        n_files += 1
        total += sz
        if n.endswith('.vtk'):
            if sz <= 0:
                problems.append(f'empty {rel}/{n}')
                continue
            with open(p, 'rb') as fh:
                head = fh.read(400).split(b'\n')[:5]
            if not head[0].startswith(b'# vtk DataFile Version'):
                problems.append(f'bad header {rel}/{n}: {head[0][:40]!r}')
            if head[2].strip() not in (b'ASCII', b'BINARY'):
                problems.append(f'bad format line {rel}/{n}: {head[2]!r}')
            if not head[3].startswith(b'DATASET'):
                problems.append(f'no DATASET line {rel}/{n}: {head[3]!r}')
        elif n.endswith('.vtk.series'):
            raw = open(p, 'rb').read()
            if raw.startswith(b'\xef\xbb\xbf'):
                problems.append(f'BOM in {rel}/{n}')
            data = json.loads(raw.decode('utf-8'))
            ents = data.get('files', [])
            times = [float(e['time']) for e in ents]
            if data.get('file-series-version') != '1.0':
                problems.append(f'{rel}/{n}: version {data.get("file-series-version")}')
            if times != sorted(times) or len(set(times)) != len(times):
                problems.append(f'{rel}/{n}: times not strictly ascending')
            for e in ents:
                q = os.path.join(base, *e['name'].split('/'))
                if not os.path.isfile(q) or os.path.getsize(q) <= 0:
                    problems.append(f'{rel}/{n} -> {e["name"]} missing/empty')
            # every t_*.vtk next to it is in the series
            sub = os.path.join(base, n[:-len('.vtk.series')])
            listed = {e['name'].split('/')[-1] for e in ents}
            if os.path.isdir(sub):
                orphans = [x for x in os.listdir(sub) if x not in listed]
                if orphans:
                    problems.append(f'{rel}/{n}: {len(orphans)} files not listed')
            lines.append(f'      series {n}: {len(ents)} entries, t {times[0]:.6g}'
                         f' .. {times[-1]:.6g} s' if ents else f'      series {n}: EMPTY')
lines += ['', f'{n_files} files, {total / 1e6:.1f} MB', '',
          'problems: ' + (json.dumps(problems, indent=1) if problems else 'none')]
for name in ('manifest.json',):
    p = os.path.join(vtk, name)
    if os.path.isfile(p):
        m = json.load(open(p, encoding='utf-8'))
        for fam in (m.get('families') or {}).values():
            t = fam.get('times')
            if isinstance(t, list) and len(t) > 6:
                fam['times'] = t[:3] + ['...'] + t[-2:]
        lines += ['', '## vtk/manifest.json', '', json.dumps(m, indent=1)]
mm = json.load(open(os.path.join(model, 'manifest.json'), encoding='utf-8'))
lines += ['', '## the model manifest: vtk, failed, wsl_scratch', '',
          json.dumps({k: mm.get(k) for k in ('vtk', 'failed', 'wsl_scratch',
                                             'n_steps', 'n_cells')}, indent=1)]
with open(out_path, 'w', encoding='utf-8', newline='\n') as fh:
    fh.write('\n'.join(lines) + '\n')
print('\n'.join(lines))
