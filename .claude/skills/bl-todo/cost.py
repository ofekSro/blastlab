"""Token cost of a /bl-todo run, per agent, from the Claude Code transcripts.

    python .claude/skills/bl-todo/cost.py [SESSION] [--since 2026-10-11T09:30] [--tasks N]

SESSION is the session id - the name of the session's scratchpad folder
(default: the newest session of this repo). `--since` (local time) drops
calls and agents from before the batch started; `--tasks` is the number of
tasks the batch planned, for the per-task line.

Cost is in input-token units, weighted by the API price ratios: input 1,
cache write 1.25 (5-min cache) or 2 (1-h cache), cache read 0.1, output 5.
Opus and Sonnet are reported apart, never mixed by price.

A *rebuild* is the cache written by the first call after a gap longer than
the cache lifetime (5 min for a subagent, 1 h for the main session): the
whole context paid again for nothing but waiting.

Decision rule, pre-registered 2026-10-11 before the first run under the
4-minute waiting rule (docs/agent-rules.md, Token budget; CLAUDE.md 6):
  1. rebuilds < 5 % of the subagents' cost      (2026-10-04: 35 %)
  2. cost per task <= 0.8 x the 2026-10-04 run  (0.96 M per task, 21 tasks)
The 2026-10-04 figures are this script on session e7422584 (gui-12 and
gui-13), `--tasks 21`.
Rule 1 checks the mechanism. Rule 2 is the outcome and is noisy - task
sizes differ from batch to batch - so read it over two or three runs.

Decision rule 3, pre-registered 2026-10-13 before the first run under the
token changes of that day (Sonnet orchestrator and planner-by-need, 9 KB
CLAUDE.md, close_batch.py, the QA agents' 4-minute rule; baseline in
docs/batches/2026-10-13-agent-cost-baseline.md). Units cannot see a move
from Opus to Sonnet, so this rule is in dollars (PRICE below):
  3. $ per task <= 0.85 x the same kind of run in the baseline:
     --kind full  $2.43  (session 9e7c70fd: gui-15, 10 low-risk tasks, QA + UX)
     --kind high  $1.95  (session 190303b8: gui-final B, 11 risk: high tasks,
                          implement + full verify, no plan, no QA)
  and MAIN runs on Sonnet. Expected: about -20 % on a full low-risk run,
  -3 to -5 % on a risk: high part (its cost is the Opus implementer, which
  these changes do not touch). Read it over two or three runs, as rule 2.
"""

import argparse
import glob
import json
import os
from collections import defaultdict
from datetime import datetime

PROJECTS = os.path.expanduser(os.path.join('~', '.claude', 'projects'))
REBUILD_MAX = 0.05
BASE_PER_TASK = 0.96e6
PER_TASK_MAX = 0.8
W_IN, W_W5, W_W1H, W_READ, W_OUT = 1, 1.25, 2, 0.1, 5
#: $ per million tokens (input, 5-min write, 1-h write, cache read, output),
#: from the claude-api skill's table cached 2026-09-25 (Opus 5.5, Sonnet 5.5)
PRICE = {'opus': (4, 5, 8, 0.20, 20), 'sonnet': (2, 2.5, 4, 0.20, 10),
         'haiku': (1, 1.25, 2, 0.10, 5)}
PER_TASK_USD = {'full': 2.43, 'high': 1.95}
USD_MAX = 0.85


def newest_session():
    found = [p for d in glob.glob(os.path.join(PROJECTS, '*BlastFoam*'))
             for p in glob.glob(os.path.join(d, '*.jsonl'))]
    if not found:
        raise SystemExit('no session transcript under ' + PROJECTS)
    return max(found, key=os.path.getmtime)


def find_session(sid):
    hits = glob.glob(os.path.join(PROJECTS, '*', sid + '.jsonl'))
    if not hits:
        raise SystemExit(f'no transcript for session {sid}')
    return hits[0]


def calls_of(path, since):
    """One record per API call (a message is logged once per content block)."""
    calls, order = {}, []
    with open(path, encoding='utf-8') as f:
        for line in f:
            d = json.loads(line)
            msg = d.get('message') or {}
            if d.get('type') != 'assistant' or not msg.get('usage'):
                continue
            t = datetime.fromisoformat(d['timestamp'].replace('Z', '+00:00'))
            if since and t < since:
                continue
            mid = msg.get('id') or d.get('uuid')
            if mid not in calls:
                u = msg['usage']
                split = u.get('cache_creation') or {}
                w1h = split.get('ephemeral_1h_input_tokens', 0)
                calls[mid] = dict(t0=t, t1=t, model=msg.get('model', ''),
                                  inp=u.get('input_tokens', 0),
                                  read=u.get('cache_read_input_tokens', 0),
                                  w5=u.get('cache_creation_input_tokens', 0) - w1h,
                                  w1h=w1h, out=0)
                order.append(mid)
            c = calls[mid]
            c['t1'] = t
            c['out'] = max(c['out'], msg['usage'].get('output_tokens', 0))
    return [calls[m] for m in order]


def cost(c, w5=True, w1h=True):
    return (W_IN * c['inp'] + W_READ * c['read'] + W_OUT * c['out']
            + (W_W5 * c['w5'] if w5 else 0) + (W_W1H * c['w1h'] if w1h else 0))


def usd(c, family):
    i, w5, w1h, r, o = PRICE.get(family, PRICE['opus'])
    return (i * c['inp'] + w5 * c['w5'] + w1h * c['w1h'] + r * c['read']
            + o * c['out']) / 1e6


def summarise(name, cs):
    ttl = 3600 if any(c['w1h'] for c in cs) else 300
    total = sum(cost(c) for c in cs)
    rebuild = sum(W_W5 * c['w5'] + W_W1H * c['w1h'] for a, c in zip(cs, cs[1:])
                  if (c['t0'] - a['t1']).total_seconds() > ttl)
    family = next((f for f in ('opus', 'sonnet', 'haiku') if f in cs[0]['model']), '?')
    ctx = sum(c['inp'] + c['read'] + c['w5'] + c['w1h'] for c in cs) / len(cs)
    dollars = sum(usd(c, family) for c in cs)
    print(f'  {name:20} {family:6} {len(cs):4} calls  ctx {ctx / 1e3:4.0f}k  '
          f'cost {total / 1e6:5.2f}M ${dollars:6.2f}  rebuilds {rebuild / max(total, 1):4.0%}')
    return family, total, rebuild, dollars


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('session', nargs='?')
    ap.add_argument('--since', help='local time, e.g. 2026-10-11T09:30')
    ap.add_argument('--tasks', type=int)
    ap.add_argument('--kind', choices=sorted(PER_TASK_USD), default='full',
                    help='which 2026-10-13 baseline rule 3 compares with')
    args = ap.parse_args()
    main_path = find_session(args.session) if args.session else newest_session()
    since = datetime.fromisoformat(args.since).astimezone() if args.since else None

    agents = [('MAIN', main_path)]
    for p in sorted(glob.glob(os.path.join(main_path[:-6], 'subagents', '*.jsonl')),
                    key=os.path.getmtime):
        meta = p[:-6] + '.meta.json'
        name = '?'
        if os.path.exists(meta):
            with open(meta, encoding='utf-8') as f:
                name = json.load(f).get('agentType', '?')
        agents.append((name, p))

    print('session', os.path.basename(main_path)[:-6], '| since', args.since or 'start')
    by_family, sub_total, sub_rebuild = defaultdict(float), 0.0, 0.0
    dollars, main_family = 0.0, '?'
    for name, p in agents:
        cs = calls_of(p, since)
        if not cs:
            continue
        family, total, rebuild, d = summarise(name, cs)
        by_family[family] += total
        dollars += d
        if name == 'MAIN':
            main_family = family
        else:
            sub_total += total
            sub_rebuild += rebuild
    grand = sum(by_family.values())
    print(f'total {grand / 1e6:.2f}M (' + ', '.join(
        f'{k} {v / 1e6:.2f}M' for k, v in sorted(by_family.items())) + f'), ${dollars:.2f}')
    if sub_total:
        share = sub_rebuild / sub_total
        print(f'rule 1, rebuilds {share:.0%} of subagent cost (< {REBUILD_MAX:.0%}): '
              + ('PASS' if share < REBUILD_MAX else 'FAIL'))
    if args.tasks:
        per = grand / args.tasks
        limit = PER_TASK_MAX * BASE_PER_TASK
        print(f'rule 2, {per / 1e6:.2f}M per task (<= {limit / 1e6:.2f}M): '
              + ('PASS' if per <= limit else 'FAIL'))
        per_usd = dollars / args.tasks
        lim_usd = USD_MAX * PER_TASK_USD[args.kind]
        ok = per_usd <= lim_usd and main_family == 'sonnet'
        print(f'rule 3 ({args.kind}), ${per_usd:.2f} per task (<= ${lim_usd:.2f}), '
              f'MAIN on {main_family}: ' + ('PASS' if ok else 'FAIL'))


if __name__ == '__main__':
    main()
