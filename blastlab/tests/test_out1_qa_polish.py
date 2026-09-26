"""The small texts the OUT-1 GUI QA (2026-09-26) asked for, V2, V3, C3:

  qt   the Model box has a placeholder; Browse... has a tooltip naming
       the Runs folder; the Chain status line puts a full stop between
       the refusal's sentences
  tk   the folder icon's tooltip names the Runs folder the same way
  log  the model folder's run log names each figure PNG by its
       folder-relative path (figures\\...), not bare

Each part runs in its own child process (Qt offscreen, Tk withdrawn),
against a private settings file with `auto_cleanup: false` (CLAUDE.md 8.2).

Run:  cd blastlab/tests && python test_out1_qa_polish.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
os.environ.setdefault('MPLBACKEND', 'Agg')

FAIL = []
RAN = []
TIP = ('Choose the Runs folder: the folder that holds one sub-folder per '
       'model.')


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    RAN.append(name)
    if not ok:
        FAIL.append(name)


def part_qt(tmp):
    from blastlab.ui.testing import ensure_qapp, pump
    ensure_qapp()
    from blastlab.ui.app import MainWindow
    runs = os.path.join(tmp, 'runs')
    os.makedirs(runs, exist_ok=True)
    win = MainWindow()
    try:
        pump(50)
        rp = win.run_panel
        check('Qt: the Model box has the placeholder MODEL',
              rp.run_name.placeholderText() == 'MODEL',
              rp.run_name.placeholderText())
        check('Qt: Browse... has a tooltip naming the Runs folder',
              rp.runs_browse.toolTip() == TIP, rp.runs_browse.toolTip())
        seen = []
        win.chain.error_sink = lambda title, lines: seen.append(lines)
        rp.set_runs_dir(runs)
        rp.run_name.setText('')
        ok = win.chain.run()
        pump(20)
        want = ('Model name: the name is empty. The Runs folder and Model '
                'boxes are on the Run tab.')
        check('Qt: the Chain status line has a stop between its sentences',
              ok is False and win.chain.status.text() == want,
              win.chain.status.text())
        check('Qt: ... while the dialog keeps one sentence per line',
              seen and seen[-1] == ['Model name: the name is empty',
                                    'The Runs folder and Model boxes are '
                                    'on the Run tab.'], str(seen))
    finally:
        win.close()
        pump(30)


def part_tk(tmp):
    import customtkinter as ctk
    from blastlab.gui import theme
    from blastlab.gui.run_panel import RunPanel
    root = ctk.CTk()
    root.withdraw()
    rp = RunPanel(root, on_run=lambda: None, on_stop=lambda: None,
                  on_init=lambda: None, on_refresh=lambda: None)
    root.update()
    try:
        tip = getattr(rp._runs_browse, '_blastlab_tip', None)
        check('Tk: the folder icon names the Runs folder like Qt',
              tip is not None and tip.text == TIP,
              getattr(tip, 'text', None))
    finally:
        rp.destroy()
        theme._ICON_CACHE.clear()
        root.destroy()


def part_log(tmp):
    """write_all with run_export stubbed: only the log line is at stake."""
    from types import SimpleNamespace
    from blastlab.models.case import Case1D
    from blastlab.services import exports, model_folder

    def fake_export(kind, ent, target, opts=None, log=print, parent=None,
                    on_error=None, open_after=True):
        if kind == 'pngs':
            with open(os.path.join(target, 'blast_1d_results.png'),
                      'wb') as f:
                f.write(b'png')
            log('Saved blast_1d_results.png')
            return ['blast_1d_results.png']
        if kind == 'report':
            with open(target, 'w', encoding='utf-8') as f:
                f.write('<html></html>')
            log(f'Saved {target}')
            return target
        return []

    real = exports.run_export
    exports.run_export = fake_export
    lines = []
    try:
        stage = os.path.join(tmp, 'M')
        os.makedirs(stage)
        res = SimpleNamespace(gauges={}, meta={}, snapshots=[object()],
                              stop_reason=None)
        model_folder.write_all(res, Case1D(), 1, stage,
                               run_info=dict(model='M'), log=lines.append)
    finally:
        exports.run_export = real
    want = f'Saved {os.path.join("figures", "blast_1d_results.png")}'
    check('log: a figure is named by its folder-relative path',
          want in lines and want.startswith('Saved figures\\'), str(lines))
    check('log: other exports keep their full path',
          f'Saved {os.path.join(stage, "report.html")}' in lines,
          str(lines))


def _private_settings(tmp):
    """A throwaway settings file with the sweep off (CLAUDE.md 8.2)."""
    path = os.path.join(tmp, 'settings.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(dict(auto_cleanup=False), f)
    os.environ['BLASTLAB_SETTINGS'] = path
    from blastlab.core import settings
    assert settings.load().get('auto_cleanup') is False
    return path


def child(part):
    tmp = tempfile.mkdtemp(prefix=f'blastlab_polish_{part}_')
    try:
        _private_settings(tmp)
        {'qt': part_qt, 'tk': part_tk, 'log': part_log}[part](tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if FAIL:
        print(f'FAILED: {FAIL}')
        return 1
    print(f'{part}: {len(RAN)} checks passed')
    return 0


def main():
    rc = 0
    for part in ('qt', 'tk', 'log'):
        print(f'\n{part}')
        p = subprocess.run([sys.executable, '-u', __file__, part], cwd=HERE,
                           capture_output=True, text=True, encoding='utf-8',
                           errors='replace')
        print(p.stdout.rstrip())
        if p.returncode != 0:
            print(p.stderr.rstrip()[-2000:])
            rc = 1
    print('\n' + '=' * 52)
    print('OUT-1 QA POLISH: ' + ('FAIL' if rc else 'PASS'))
    return rc


if __name__ == '__main__':
    if len(sys.argv) > 1:
        sys.exit(child(sys.argv[1]))
    sys.exit(main())
