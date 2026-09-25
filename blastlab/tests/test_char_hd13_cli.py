"""Characterisation: the HD 1.3 command line, end to end (Phase 7).

docs/ARCHITECTURE_REVIEW.md section 5, Phase 7. Pins, from the code as it
is before the HD 1.3 orchestration moves out of `output/cli_hd13.py` into
`services/hd13.py`, what a user of the two commands sees:

    python -m blastlab --hd13-new t.json
    python -m blastlab --hd13 t.json

  * stdout of each (byte for byte, CRLF folded to LF) and the exit code;
  * the starter case file `--hd13-new` writes, byte for byte;
  * the HTML report `--hd13` writes next to the case, byte for byte after
    its `datetime.now()` stamp (`output/hd13.py`, the banner line) and its
    inlined PNGs are replaced by placeholders (the PNGs by pixel size) -
    the masking `test_char_exports.py` uses for the blast report;
  * the refused case (run with `--report r.html`): a case
    `assessment.validate` refuses - the report printed on stdout, the
    `SystemExit` text on stderr, exit code 1, and no report file written.

The commands run in a subprocess with the case given as a RELATIVE path
from a temp working directory, so no absolute path reaches the output;
PYTHONIOENCODING is fixed to utf-8 so the bytes do not depend on the
console's code page.

The starter case runs with the sensitivity band OFF (its default): one
assessment is about 40 s. `test_char_hd13.py` pins the numbers; this file
pins the text around them.

Run:  cd blastlab/tests && python test_char_hd13_cli.py [--update]
"""
import base64
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile

import char_common as cc

_B64 = re.compile(r'data:image/png;base64,([A-Za-z0-9+/=]+)')
_STAMP = re.compile(r'HD 1\.3 deflagration &middot; '
                    r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}</p>')


def png_size(data):
    """(width, height) from a PNG's IHDR chunk."""
    assert data[:8] == b'\x89PNG\r\n\x1a\n', 'not a PNG'
    return tuple(struct.unpack('>II', data[16:24]))


def normalise_html(text):
    """The HD 1.3 report with its timestamp and inlined PNG bytes replaced
    by placeholders (the PNGs by their pixel size): everything else is
    pinned byte for byte. Line ends are folded to LF because the golden
    is a text file; `crlf_count` pins how many the file really has."""
    text = text.replace('\r\n', '\n')
    text, n = _STAMP.subn('HD 1.3 deflagration &middot; <now></p>', text)
    assert n == 1, f'expected one banner timestamp, found {n}'
    return _B64.sub(lambda m: 'data:image/png;<png %dx%d>'
                    % png_size(base64.b64decode(m.group(1))), text)


def blastlab(cwd, *args):
    """`python -m blastlab *args` in `cwd`: (exit code, stdout, stderr),
    text with CRLF folded to LF."""
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONPATH'] = cc.REPO + os.pathsep + env.get('PYTHONPATH', '')
    p = subprocess.run([sys.executable, '-m', 'blastlab', *args], cwd=cwd,
                       env=env, capture_output=True)

    def text(b):
        return b.decode('utf-8').replace('\r\n', '\n')
    return p.returncode, text(p.stdout), text(p.stderr)


def crlf_count(path):
    with open(path, 'rb') as f:
        return f.read().count(b'\r\n')


def read(path):
    with open(path, 'rb') as f:
        return f.read().decode('utf-8')


def listing(d):
    return sorted(os.listdir(d))


def test_starter_and_report():
    tmp = tempfile.mkdtemp(prefix='blastlab_char_hd13cli_')
    try:
        code, out, err = blastlab(tmp, '--hd13-new', 't.json')
        got = {'new': dict(code=code, stdout=out, stderr=err,
                           files=listing(tmp), case=read(
                               os.path.join(tmp, 't.json')))}
        code, out, err = blastlab(tmp, '--hd13', 't.json')
        report = os.path.join(tmp, 't_hd13.html')
        got['run'] = dict(code=code, stdout=out, stderr=err,
                          files=listing(tmp),
                          report_crlf_count=crlf_count(report))
        cc.check_json('hd13_cli.json', got)
        cc.check_text('hd13_cli_report.html', normalise_html(read(report)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_refused_case():
    tmp = tempfile.mkdtemp(prefix='blastlab_char_hd13cli_')
    try:
        blastlab(tmp, '--hd13-new', 'bad.json')
        path = os.path.join(tmp, 'bad.json')
        with open(path, encoding='utf-8') as f:
            case = json.load(f)
        # two errors, so the '; ' join of the refusal text is pinned too
        case['charge_kg'] = 0.0
        case['t_end'] = 0.0
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(case, f, indent=2)
        code, out, err = blastlab(tmp, '--hd13', 'bad.json',
                                  '--report', 'r.html')
        cc.check_json('hd13_cli_refused.json',
                      dict(code=code, stdout=out, stderr=err,
                           files=listing(tmp)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    return cc.run_main('CHAR HD13 CLI', [test_refused_case,
                                         test_starter_and_report])


if __name__ == '__main__':
    sys.exit(main())
