"""Stage 5 of /bl-todo by script: close a batch in TODO.md and DONE.md.

    python .claude/skills/bl-todo/close_batch.py docs/batches/<plan>.md --base <rev>
        [--notes notes.md] [--still-open "GUI-16=(j)"] [--dry-run]

Reads the `## Status` block at the end of every `<plan>[-<part>].verify.md`
next to the plan - one line per task, written by bl-task-verifier:

    - B1 GUI-16 (a): FIXED f183a4f
    - B2 P1-23: PARTIAL needs the owner's ruling on the wording

VERIFIED and FIXED close; FAILED, PARTIAL and SKIPPED stay open
(docs/agent-rules.md; the /bl-todo rule "never move a task the verifier did
not mark"). For a `risk: none` part with no verifier, the orchestrator writes
a verify file holding only the Status block.

TODO.md, in the file's existing style (see the GUI-15 / P1-24 closures):
- a table row `| `ID` | ...` gets `✅ <date> <items>, DONE.md §0x. Original row: `
  in front of its text (`; **(j) still open**` when something of it is);
- a list bullet `- `ID` text` closed in full becomes `- `ID` ✅ closed <date>
  (DONE.md §0x).` (the text lives on in DONE.md and git; `--keep-body` keeps it);
- a `### ID · title · status` heading closed in full gets `· ✅ closed <date>
  (DONE.md §0x)` and its body becomes one line naming the code that cites the
  id (code cites TODO ids - CLAUDE.md §6), unless `--keep-body ID`; the
  orchestrator may add a one-sentence summary there; partly closed, the heading gets
  `· partly done <date> (DONE.md §0x)` and the body stays.
DONE.md: a new `## 0x.` section before `## 1. The timeline`, from the status
lines plus `--notes` (the orchestrator's few lines: what, tests, open items).

Ends with the 1000-line check of both files (CLAUDE.md §5). Exit 2 if a file
is over the cap - never split here; that is an owner question (/bl-todo
Stage 5 item 4). Exit 1 on bad input. `--dry-run` prints the diff and
writes nothing; otherwise the orchestrator reviews `git diff` and commits.
"""

import argparse
import datetime
import difflib
import glob
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
CAP = 1000
CLOSING = ('VERIFIED', 'FIXED')
STATUS = re.compile(
    r'^\s*[-*]?\s*(?P<task>[A-Z]\d+[a-z]?)\s+`?(?P<todo>[A-Z][A-Za-z0-9]*(?:-\d+[a-z]?)?)`?'
    r'(?:\s*(?P<sub>\([^)]*\)))?\s*:\s*\**(?P<status>VERIFIED|FIXED|FAILED|PARTIAL|SKIPPED)\**'
    r'(?P<rest>.*)$')
HASH = re.compile(r'\b[0-9a-f]{7,12}\b')
TIMELINE = re.compile(r'^## 1\. ', re.M)
DONE_SECTION = re.compile(r'^## 0([a-z]+)(?:-0([a-z]+))?\. ', re.M)


def git(*a):
    p = subprocess.run(['git', *a], cwd=ROOT, capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else ''


def read(path):
    with open(path, encoding='utf-8', newline='') as f:
        text = f.read()
    nl = '\r\n' if '\r\n' in text else '\n'
    return text.replace('\r\n', '\n'), nl


def write(path, text, nl):
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(text.replace('\n', nl))


def statuses(plan):
    """[(report, task, todo, sub, status, rest)] from every verify report of the plan."""
    stem = plan[:-3]
    reports = sorted(set(glob.glob(stem + '.verify.md') + glob.glob(stem + '-*.verify.md')))
    if not reports:
        sys.exit(f'no verify report next to {plan} ({os.path.basename(stem)}[-<part>].verify.md)')
    rows = []
    for r in reports:
        text, _ = read(r)
        m = re.search(r'^## Status\s*$', text, re.M)
        if not m:
            sys.exit(f'{os.path.relpath(r, ROOT)} has no "## Status" block - add one '
                     '(one line per task, see this script\'s docstring) and rerun')
        block = text[m.end():]
        block = block[:re.search(r'^## ', block, re.M).start()] if re.search(r'^## ', block, re.M) else block
        for line in block.splitlines():
            s = STATUS.match(line)
            if s:
                rows.append((os.path.relpath(r, ROOT).replace('\\', '/'),) + s.group(
                    'task', 'todo', 'sub', 'status', 'rest'))
    if not rows:
        sys.exit('the Status blocks hold no task line')
    return reports, rows


def next_section(done):
    last = ''
    for m in DONE_SECTION.finditer(done):
        for g in m.groups():
            if g and (len(g), g) > (len(last), last):
                last = g
    if not last:
        return 'a'
    return last[:-1] + chr(ord(last[-1]) + 1) if last[-1] < 'z' else last + 'a'


def citers(todo_id):
    """Repo-relative code files that cite the id, for the collapsed body."""
    pat = re.compile(r'(?<![\w-])' + re.escape(todo_id) + r'(?![\w-])')
    hits = []
    for dirpath, dirs, files in os.walk(os.path.join(ROOT, 'blastlab')):
        dirs[:] = [d for d in dirs if d not in ('__pycache__', 'baseline', 'foam_golden',
                                                 'foam_fixtures', 'char_golden')]
        for f in files:
            if f.endswith('.py'):
                p = os.path.join(dirpath, f)
                with open(p, encoding='utf-8', errors='replace') as fh:
                    if pat.search(fh.read()):
                        hits.append(os.path.relpath(p, os.path.join(ROOT, 'blastlab')).replace('\\', '/'))
    return sorted(hits)


def close_todo(todo, todo_id, closed_subs, open_subs, sec, date, notes, keep_body=False):
    """Edit one id in TODO.md text (`sec` like '0z'); returns the new text."""
    idre = re.escape(todo_id)
    items = ' '.join(closed_subs)
    still = '; **' + ' '.join(open_subs) + ' still open**' if open_subs else ''
    # table row
    row = re.compile(r'^(\| `' + idre + r'` \| )(?!✅)', re.M)
    if row.search(todo):
        lead = f'✅ {date}{" " + items if items else ""}, DONE.md §{sec}{still}. Original row: '
        return row.sub(lambda m: m.group(1) + lead, todo, count=1)
    # list bullet `- `ID` text` (the P2 list): closed in full, the text goes to
    # DONE.md and the bullet keeps only the id, as `- `P3-7` ... ✅ closed` does
    bullet = re.compile(r'^(- `' + idre + r'`)(?! ✅)(.*)$', re.M)
    b = bullet.search(todo)
    if b:
        if open_subs:
            tail = f'{b.group(2)} · partly done {date} (DONE.md §{sec}){still}'
        elif keep_body:
            tail = f'{b.group(2)} · ✅ closed {date} (DONE.md §{sec})'
        else:
            tail = f' ✅ closed {date} (DONE.md §{sec}).'
        return todo[:b.start()] + b.group(1) + tail + todo[b.end():]
    # heading
    head = re.compile(r'^(### `?' + idre + r'`? · .*?)( · \*\*[^\n]*\*\*)?[ \t]*$', re.M)
    m = head.search(todo)
    if not m:
        notes.append(f'{todo_id}: not found in TODO.md as a table row, a list bullet or a '
                     '### heading - edit by hand')
        return todo
    if '✅' in m.group(0):
        notes.append(f'{todo_id}: already closed in TODO.md - left alone')
        return todo
    if open_subs:
        new_head = f'{m.group(1)}{m.group(2) or ""} · partly done {date} (DONE.md §{sec}){still}'
        return todo[:m.start()] + new_head + todo[m.end():]
    new_head = f'{m.group(1)} · ✅ closed {date} (DONE.md §{sec})'
    if keep_body:
        return todo[:m.start()] + new_head + todo[m.end():]
    nxt = re.compile(r'^(#{1,3} |---$)', re.M).search(todo, m.end() + 1)
    end = nxt.start() if nxt else len(todo)
    cited = citers(todo_id)
    body = (f'\nCited by ' + ', '.join(f'`{c}`' for c in cited) + '. ' if cited
            else '\nNot cited from code. ') + f'Details: DONE.md §{sec}.\n\n'
    return todo[:m.start()] + new_head + '\n' + body + todo[end:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('plan')
    ap.add_argument('--base', required=True, help='the batch base commit')
    ap.add_argument('--notes', help='markdown bullets for the DONE.md entry (what, tests, open)')
    ap.add_argument('--still-open', action='append', default=[], metavar='ID=(x)',
                    help='a sub-item of a closed id that this batch did not do')
    ap.add_argument('--keep-body', action='append', default=[], metavar='ID',
                    help='close the heading of ID but keep its body as it is')
    ap.add_argument('--date', default=datetime.date.today().isoformat())
    ap.add_argument('--todo', default=os.path.join(ROOT, 'TODO.md'))
    ap.add_argument('--done', default=os.path.join(ROOT, 'DONE.md'))
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    plan = os.path.abspath(args.plan)
    reports, rows = statuses(plan)
    todo, todo_nl = read(args.todo)
    done, done_nl = read(args.done)
    sec = next_section(done)
    notes = []

    by_id = {}
    for _, task, tid, sub, status, _ in rows:
        by_id.setdefault(tid, ([], []))[0 if status in CLOSING else 1].append(sub or task)
    extra = {}
    for s in args.still_open:
        tid, _, sub = s.partition('=')
        extra.setdefault(tid.strip(), []).append(sub.strip())
    new_todo = todo
    for tid, (closed, opened) in by_id.items():
        if not closed:
            continue
        subs = [s for s in closed if s.startswith('(')]
        new_todo = close_todo(new_todo, tid, subs, opened + extra.get(tid, []),
                              '0' + sec, args.date, notes, tid in args.keep_body)

    name = re.sub(r'^\d{4}-\d{2}-\d{2}-', '', os.path.basename(plan)[:-3])
    ids = ', '.join(t for t, (c, _) in by_id.items() if c)
    branch = git('branch', '--show-current') or '?'
    head = git('rev-parse', '--short', 'HEAD') or '?'
    lines = [f'## 0{sec}. {args.date} — batch `{name}` ({ids or "nothing closed"}; branch `{branch}`)',
             '',
             f'Plan `{os.path.relpath(plan, ROOT).replace(chr(92), "/")}`; verify '
             + ', '.join(f'`{os.path.basename(r)}`' for r in reports) + '.']
    if args.notes:
        lines += [read(args.notes)[0].strip()]
    task_lines = [f'{task} {tid}{" " + sub if sub else ""} {status}'
                  + (' `' + '`, `'.join(HASH.findall(rest)) + '`' if HASH.findall(rest) else '')
                  for _, task, tid, sub, status, rest in rows]
    lines.append('- **Tasks:** ' + '; '.join(task_lines) + '.')
    left = [f'{task} {tid}{" " + sub if sub else ""} {status}{rest.rstrip()}'
            for _, task, tid, sub, status, rest in rows if status not in CLOSING]
    if left:
        lines.append('- **Left open:** ' + '; '.join(left) + '.')
    lines.append(f'- **Commits:** `{args.base}`..`{head}` (branch `{branch}`).')
    entry = '\n'.join(lines) + '\n\n---\n\n'
    m = TIMELINE.search(done)
    if not m:
        sys.exit('DONE.md has no "## 1. " heading to insert before')
    new_done = done[:m.start()] + entry + done[m.start():]

    n_todo, n_done = new_todo.count('\n'), new_done.count('\n')
    if args.dry_run:
        for path, a, b in ((args.todo, todo, new_todo), (args.done, done, new_done)):
            sys.stdout.writelines(difflib.unified_diff(
                a.splitlines(True), b.splitlines(True), path, path + ' (closed)', n=1))
    else:
        write(args.todo, new_todo, todo_nl)
        write(args.done, new_done, done_nl)
    for n in notes:
        print('NOTE', n)
    print(f'DONE.md §0{sec}; closed: {ids or "none"}; left open: {len(left)} task(s)')
    over = [f'{os.path.basename(p)} {n}' for p, n in ((args.todo, n_todo), (args.done, n_done)) if n > CAP]
    print(f'lines: TODO.md {n_todo}, DONE.md {n_done} (cap {CAP})'
          + (' - OVER CAP: ' + ', '.join(over) + ' (owner question, do not split)' if over else ''))
    return 2 if over else 0


if __name__ == '__main__':
    sys.exit(main())
