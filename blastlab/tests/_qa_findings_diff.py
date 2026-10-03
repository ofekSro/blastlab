"""Compare two QA-harness `findings.jsonl` files (GUI-10, plan T6).

Each finding is keyed on (scenario, severity, category, text), with the
text normalised so that run-to-run noise does not read as a difference:
hex addresses become `<hex>`, file paths become `<path>` (a Windows path
may hold spaces, `C:\\Users\\Ofek Rotem\\...`), and every run of digits
becomes `#`. A key may occur more than once; the counts are
compared, so a finding that doubled shows one `new`.

Prints, per scenario, the `new` (only in B), `gone` (only in A) and
`same` counts and the new / gone texts, then a total line. Always exits
0: this is a manual triage tool, not a gate (hence the underscore).

Run:
    python _qa_findings_diff.py A\\findings.jsonl B\\findings.jsonl
"""

import collections
import json
import re
import sys

_HEX = re.compile(r'0x[0-9a-fA-F]+')
_END = r"[^\s\\/'\"<>|*?(),;\[\]{}]*"
#: a Windows drive path: inner folders may hold spaces (`C:\Users\Ofek
#: Rotem\...`), the last segment stops at whitespace; a UNC path; a POSIX
#: path of two or more segments that does not start mid-word (`1/3` and
#: `kPa/ms` stay text). The inner folders end with the separator the path
#: started with and hold no `:` (verify10a): otherwise "C:\runs\M1 is
#: missing, ratio 1/3" ran on to the `/` and "missing" vs "written"
#: compared as `same`.
_PATH = re.compile(r"[A-Za-z]:([\\/])(?:[^\\/\n'\"<>|*?:]+\1)*" + _END
                   + r"|\\\\[^\s'\"]+"
                   + r"|(?<![\w.])/(?:[^\s/'\"]+/)+" + _END)
_DIGITS = re.compile(r'\d+')


def normalise(text):
    """The text with addresses, paths and numbers made comparable."""
    text = _HEX.sub('<hex>', str(text))
    text = _PATH.sub('<path>', text)
    return _DIGITS.sub('#', text)


def load(path):
    """Counter of (scenario, sev, cat, normalised text) -> occurrences,
    and one original text per key (for printing)."""
    keys = collections.Counter()
    shown = {}
    with open(path, encoding='utf-8') as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                print(f'  (skipped unreadable line {n} of {path})')
                continue
            key = (str(rec.get('scenario', '?')), str(rec.get('sev', '?')),
                   str(rec.get('cat', '?')), normalise(rec.get('text', '')))
            keys[key] += 1
            shown.setdefault(key, str(rec.get('text', '')))
    return keys, shown


def diff(a_path, b_path, out=print):
    a, a_text = load(a_path)
    b, b_text = load(b_path)
    totals = collections.Counter()
    for sid in sorted({k[0] for k in a} | {k[0] for k in b}):
        rows = {'new': [], 'gone': [], 'same': []}
        for key in sorted(set(a) | set(b)):
            if key[0] != sid:
                continue
            na, nb = a.get(key, 0), b.get(key, 0)
            same = min(na, nb)
            rows['same'] += [key] * same
            rows['new'] += [key] * (nb - same)
            rows['gone'] += [key] * (na - same)
        for kind in rows:
            totals[kind] += len(rows[kind])
        out(f'{sid}: new {len(rows["new"])} · gone {len(rows["gone"])} · '
            f'same {len(rows["same"])}')
        for kind, texts in (('new', b_text), ('gone', a_text)):
            for key in rows[kind]:
                out(f'    {kind:4s} {key[1]} {key[2]}: {texts[key][:200]}')
    out(f'TOTAL: new {totals["new"]} · gone {totals["gone"]} · '
        f'same {totals["same"]}')
    return totals


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 0
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass
    diff(argv[1], argv[2])
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
