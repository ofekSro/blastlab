"""Characterisation: what the Tk Results panel's exports write (Phase 6).

docs/ARCHITECTURE_REVIEW.md section 5, Phase 6 (finding F7). The Tk twin
of `test_char_exports.py`: drives the REAL `gui.results_panel.ResultsPanel`
(customtkinter, withdrawn root) over the same native 1D and 2D runs and
pins, in the same format (`char_golden/exports_tk.json`):

  * the export buttons' enabled state and tooltip for each result and for
    no selection (`_sync_export_buttons`);
  * `_export(kind)` for every export button, with the Title line and
    "Show mesh" off and - for report, pngs and gif - on: the file dialog
    each kind opens with its arguments, the log lines, what is handed to
    `os.startfile`, and every file written, described exactly as
    `test_char_exports.describe_dir` does (text byte-exact, npz
    array-wise, HTML byte-exact up to timestamp and inlined PNG bytes,
    PNG/GIF by pixel size and frame count).

The file dialogs are replaced by recorders and the export's worker
thread by one that runs its target at once, so every file exists when
`_export` returns. The Tk GUI is the permanent way back (CLAUDE.md
section 9); this golden is what proves Phase 6 changed none of its files.

Script only - it builds Tk widgets, so conftest.py keeps it out of
pytest collection (`test_gui_*.py`).

Run:  cd blastlab/tests && python test_gui_char_exports.py [--update]
"""
import os
import shutil
import sys
import tempfile
from types import SimpleNamespace

import char_common as cc

import customtkinter as ctk                                  # noqa: E402

from blastlab.gui import results_panel as rp                 # noqa: E402
from test_char_exports import (TITLE, Opened, describe_dir,  # noqa: E402
                               gif_name, plan, result, scrub, NAMES)


class _SyncThread:
    """threading.Thread whose start() runs the target on this thread."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._run = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        self._run(*self._args, **self._kwargs)


def _buttons(panel):
    out = {}
    for kind, b in panel._export_btns.items():
        tip = getattr(b, '_blastlab_tip', None)
        out[kind] = {'state': str(b.cget('state')),
                     'tooltip': tip.text if tip is not None else None}
    return out


def tk_export(panel, log, key, kind, variant):
    label = NAMES[key][1]
    panel.sel.set(label)
    panel._refresh()
    titled = variant == 'titled'
    panel.title_var.set(TITLE if titled else '')
    panel.show_mesh_var.set(titled)
    out = tempfile.mkdtemp(prefix='blastlab_char_tk_')
    calls, errors = [], []

    def asksaveasfilename(**kw):
        calls.append(['asksaveasfilename', kw])
        name = kw.get('initialfile', '')
        return os.path.join(out, gif_name(name) if kind == 'gif' else name)

    def askdirectory(**kw):
        calls.append(['askdirectory', kw])
        return out

    real = rp.filedialog, rp.threading, rp.messagebox
    rp.filedialog = SimpleNamespace(asksaveasfilename=asksaveasfilename,
                                    askdirectory=askdirectory)
    rp.threading = SimpleNamespace(Thread=_SyncThread)
    rp.messagebox = SimpleNamespace(
        showerror=lambda *a, **k: errors.append(list(a)))
    n_log = len(log)
    try:
        with Opened() as opened:
            panel._export(kind)
            panel.update_idletasks()
        got = dict(dialogs=calls, log=log[n_log:], errors=errors,
                   opened=opened.paths, files=describe_dir(out))
        return scrub(got, out)
    finally:
        rp.filedialog, rp.threading, rp.messagebox = real
        shutil.rmtree(out, ignore_errors=True)


def collect():
    root = ctk.CTk()
    root.withdraw()
    log = []
    try:
        panel = rp.ResultsPanel(root, log_fn=log.append)
        got = {'buttons/none': _buttons(panel)}
        for key in ('1d', '2d'):
            panel.add_result(NAMES[key][1], int(key[0]), result(key))
            got[f'buttons/{key}'] = _buttons(panel)
        for key, kind, variant in plan():
            got[f'{key}/{kind}/{variant}'] = tk_export(panel, log, key, kind,
                                                       variant)
        panel.destroy()
        return got
    finally:
        root.destroy()


def test_gui_exports():
    cc.check_json('exports_tk.json', collect())


def main():
    return cc.run_main('CHAR GUI EXPORTS', [test_gui_exports])


if __name__ == '__main__':
    sys.exit(main())
