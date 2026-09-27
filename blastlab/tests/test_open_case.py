"""Open case in both toolkits (OUT-1 GUI QA 2026-09-26, F2 and C1).

  F2  an HD 1.3 `MODEL.json` (schema `blastlab-hd13`) opens: the Qt app
      loads it into the 0-D assessment form; the Tk app, which has no
      HD 1.3 form, says so instead of "Not a blastlab case file". A blast
      case opens as before, and a file neither loader reads keeps the
      blast loader's error.
  C1  Open case sets the Model box to the opened model: the folder's name
      for `<MODEL>\\MODEL.json` (the chain's model for a stage's
      `<MODEL>\\2d\\MODEL.json`), the file stem otherwise - replacing
      whatever the box held before. A refused file leaves the box alone.

Each toolkit runs in its own child process (Qt offscreen, Tk withdrawn),
against a private settings file with `auto_cleanup: false` (CLAUDE.md 8.2).

Run:  cd blastlab/tests && python test_open_case.py
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


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    RAN.append(name)
    if not ok:
        FAIL.append(name)


def fixtures(tmp):
    """The case files every part opens, by role."""
    from blastlab.models import hd13_case
    from blastlab.models.case import Case1D, Case2D, save_case
    from blastlab.output.cli_hd13 import write_starter_case
    from blastlab.services.model_folder import CASE_FILE, MARKER_FILE
    runs = os.path.join(tmp, 'runs')
    paths = {}

    def model_dir(*parts, marker=True):
        d = os.path.join(runs, *parts)
        os.makedirs(d, exist_ok=True)
        if marker:
            with open(os.path.join(runs, parts[0], MARKER_FILE), 'w',
                      encoding='utf-8') as f:
                f.write('{}\n')
        return d

    # the HD 1.3 starter, as an HD 1.3 model folder holds it
    paths['hd13'] = write_starter_case(
        os.path.join(model_dir('HD_MODEL'), CASE_FILE))
    paths['hd13_stem'] = write_starter_case(os.path.join(tmp, 'hd_file.json'))
    paths['blast_model'] = os.path.join(model_dir('BLAST_MODEL'), CASE_FILE)
    save_case(Case1D(radius_m=1.0, charge_kg=0.5, cell_size_m=0.01),
              paths['blast_model'])
    paths['blast_stem'] = os.path.join(tmp, 'kitchen_case.json')
    save_case(Case2D(Lx=3.3), paths['blast_stem'])
    paths['chain_stage'] = os.path.join(model_dir('CHAIN', '2d'), CASE_FILE)
    save_case(Case2D(Lx=2.2), paths['chain_stage'])
    paths['neither'] = os.path.join(tmp, 'other.json')
    with open(paths['neither'], 'w', encoding='utf-8') as f:
        json.dump(dict(schema='someone-else', dim=1), f)
    paths['hd13_dict'] = hd13_case.case_to_dict(
        hd13_case.load_case(paths['hd13']))
    return paths


def part_pure(tmp):
    """The helper both toolkits call."""
    from blastlab.models import hd13_case
    from blastlab.models.case import Case1D, Case2D, load_any_case
    p = fixtures(tmp)
    back = load_any_case(p['hd13'])
    check('load_any_case reads an HD 1.3 file as a DeflagrationCase (dim 0)',
          isinstance(back, hd13_case.DeflagrationCase) and back.dim == 0
          and hd13_case.case_to_dict(back) == p['hd13_dict'])
    check('load_any_case reads a blast file as before',
          isinstance(load_any_case(p['blast_model']), Case1D)
          and isinstance(load_any_case(p['blast_stem']), Case2D))
    try:
        load_any_case(p['neither'])
        msg = None
    except ValueError as exc:
        msg = str(exc)
    check('a file neither loader reads keeps the blast error',
          msg == 'Not a blastlab case file', repr(msg))
    from blastlab.services.model_folder import model_for_case_file
    got = {k: model_for_case_file(p[k]) for k in
           ('hd13', 'blast_model', 'blast_stem', 'chain_stage', 'hd13_stem')}
    check('the Model name: the folder for MODEL.json, the chain for a '
          'stage, else the stem',
          got == dict(hd13='HD_MODEL', blast_model='BLAST_MODEL',
                      blast_stem='kitchen_case', chain_stage='CHAIN',
                      hd13_stem='hd_file'), str(got))


def part_qt(tmp):
    from blastlab.ui.testing import ensure_qapp, pump
    ensure_qapp()
    from blastlab.models import hd13_case
    from blastlab.ui.app import MainWindow
    p = fixtures(tmp)
    win = MainWindow()
    errors = []
    win.show_error = lambda t, m: errors.append((t, m))
    rp = win.run_panel
    try:
        pump(50)
        rp.run_name.setText('PREVIOUS')
        win._open_case(p['hd13'])
        pump(50)
        case = win.current_case()
        check('Qt: an HD 1.3 MODEL.json opens into the 0-D form',
              not errors and win.setup.dim == 0
              and isinstance(case, hd13_case.DeflagrationCase)
              and hd13_case.case_to_dict(case) == p['hd13_dict'],
              f'{errors} dim={win.setup.dim}')
        check('Qt: the Model box names the HD 1.3 model folder, replacing '
              'the previous name',
              rp.current_run_name() == 'HD_MODEL', rp.current_run_name())
        win._open_case(p['blast_model'])
        pump(50)
        check('Qt: a blast MODEL.json still opens (1D)',
              not errors and win.setup.dim == 1, str(errors))
        check('Qt: ... and the Model box names its folder',
              rp.current_run_name() == 'BLAST_MODEL', rp.current_run_name())
        win._open_case(p['blast_stem'])
        pump(50)
        check('Qt: a plain blast case file still opens (2D), named after '
              'its stem',
              not errors and win.setup.dim == 2
              and rp.current_run_name() == 'kitchen_case',
              f'{errors} {rp.current_run_name()}')
        win._open_case(p['chain_stage'])
        pump(50)
        check("Qt: a chain stage's MODEL.json names the chain's model",
              not errors and rp.current_run_name() == 'CHAIN',
              rp.current_run_name())
        win._open_case(p['neither'])
        pump(50)
        check('Qt: a file neither loader reads is refused as before, and '
              'the Model box is left alone',
              errors == [('Open case', 'Not a blastlab case file')]
              and win.setup.dim == 2 and rp.current_run_name() == 'CHAIN',
              f'{errors} {rp.current_run_name()}')
        errors.clear()
        save_round_trips(win, p, tmp, errors)
    finally:
        win.close()
        pump(30)


def save_round_trips(win, p, tmp, errors):
    """P1-18, the Save half: Save case... (the slot Ctrl+S drives) from
    the 0-D form writes an HD 1.3 file that Open reads back, and a blast
    case saves exactly as `models.case.save_case` writes it."""
    import dataclasses
    from blastlab.models import hd13_case
    from blastlab.models.case import save_case as blast_save
    from blastlab.ui import dialogs
    from blastlab.ui.testing import pump
    target = []

    def save_file(title, filters='All files (*.*)', parent=None, start='',
                  default_suffix=None):
        return target[-1]

    def read(path):
        with open(path, 'rb') as f:
            return f.read()

    def save_as(name):
        target.append(os.path.join(tmp, name))
        win._save_case()
        pump(30)
        return target[-1]

    real = dialogs.save_file
    dialogs.save_file = save_file
    try:
        clearing = os.path.join(tmp, 'clearing.json')
        hd13_case.save_case(dataclasses.replace(
            hd13_case.load_case(p['hd13']), clearing=True, wall_H_m=3.0,
            wall_W_m=4.0), clearing)
        for what, src in (('the starter', p['hd13']),
                          ('a clearing case', clearing)):
            want = hd13_case.case_to_dict(hd13_case.load_case(src))
            win._open_case(src)
            pump(50)
            b = save_as(f'B_{len(target)}.json')
            with open(b, encoding='utf-8') as f:
                schema = json.load(f).get('schema')
            check(f'Qt Save, {what}: the 0-D form writes schema '
                  f'blastlab-hd13', schema == 'blastlab-hd13', str(schema))
            win._open_case(b)
            pump(50)
            case = win.current_case()
            check(f'Qt Save, {what}: the saved file reopens into the 0-D '
                  f'form, equal to the source',
                  not errors and win.setup.dim == 0
                  and isinstance(case, hd13_case.DeflagrationCase)
                  and hd13_case.case_to_dict(case) == want
                  and hd13_case.case_to_dict(hd13_case.load_case(b)) == want,
                  f'{errors} dim={win.setup.dim}')
            c = save_as(f'C_{len(target)}.json')
            check(f'Qt Save, {what}: Save -> Open -> Save is byte-identical',
                  read(b) == read(c))
        win._open_case(p['blast_stem'])
        pump(50)
        blast = win.current_case()
        got = save_as('blast_saved.json')
        ref = os.path.join(tmp, 'blast_ref.json')
        blast_save(blast, ref)
        check('Qt Save: a 2D blast case saves exactly as models.case.'
              'save_case writes it',
              not errors and win.setup.dim == 2 and read(got) == read(ref),
              str(errors))
    finally:
        dialogs.save_file = real


def part_tk(tmp):
    import customtkinter as ctk
    from blastlab.gui import app as appmod
    from blastlab.gui import theme
    p = fixtures(tmp)
    root = ctk.CTk()
    root.withdraw()
    app = appmod.App(root)
    root.update()
    errors = []
    real = appmod.messagebox.showerror
    appmod.messagebox.showerror = lambda t, m, **k: errors.append((t, m))
    rp = app.run_panel
    try:
        rp.run_name.set('PREVIOUS')
        app._open_case(p['blast_model'])
        root.update()
        check('Tk: a blast MODEL.json opens (1D)',
              not errors and app.setup.dim_var.get() == 1, str(errors))
        check('Tk: the Model box names its folder, replacing the previous '
              'name',
              rp.current_run_name() == 'BLAST_MODEL', rp.current_run_name())
        app._open_case(p['blast_stem'])
        root.update()
        check('Tk: a plain blast case file opens (2D), named after its stem',
              not errors and app.setup.dim_var.get() == 2
              and rp.current_run_name() == 'kitchen_case',
              f'{errors} {rp.current_run_name()}')
        app._open_case(p['chain_stage'])
        root.update()
        check("Tk: a chain stage's MODEL.json names the chain's model",
              not errors and rp.current_run_name() == 'CHAIN',
              rp.current_run_name())
        app._open_case(p['hd13'])
        root.update()
        check('Tk: an HD 1.3 file is recognised, not called "not a case '
              'file", and points to the Qt GUI',
              len(errors) == 1 and errors[0][0] == 'Open case'
              and 'HD 1.3 case file' in errors[0][1]
              and 'python -m blastlab' in errors[0][1]
              and 'Not a blastlab' not in errors[0][1], str(errors))
        check('Tk: ... and leaves the form and the Model box alone',
              app.setup.dim_var.get() == 2
              and rp.current_run_name() == 'CHAIN',
              f'{app.setup.dim_var.get()} {rp.current_run_name()}')
        errors.clear()
        app._open_case(p['neither'])
        root.update()
        check('Tk: a file neither loader reads is refused as before',
              errors == [('Open case', 'Not a blastlab case file')],
              str(errors))
    finally:
        appmod.messagebox.showerror = real
        app._on_close()
        theme._ICON_CACHE.clear()
        try:
            root.destroy()
        except Exception:
            pass


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
    tmp = tempfile.mkdtemp(prefix=f'blastlab_open_{part}_')
    try:
        _private_settings(tmp)
        {'pure': part_pure, 'qt': part_qt, 'tk': part_tk}[part](tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if FAIL:
        print(f'FAILED: {FAIL}')
        return 1
    print(f'{part}: {len(RAN)} checks passed')
    return 0


def main():
    rc = 0
    for part in ('pure', 'qt', 'tk'):
        print(f'\n{part}')
        p = subprocess.run([sys.executable, '-u', __file__, part], cwd=HERE,
                           capture_output=True, text=True, encoding='utf-8',
                           errors='replace')
        print(p.stdout.rstrip())
        if p.returncode != 0:
            print(p.stderr.rstrip()[-2000:])
            rc = 1
    print('\n' + '=' * 52)
    print('OPEN CASE: ' + ('FAIL' if rc else 'PASS'))
    return rc


if __name__ == '__main__':
    if len(sys.argv) > 1:
        sys.exit(child(sys.argv[1]))
    sys.exit(main())
