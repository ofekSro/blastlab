"""Foam run browser (N8): the WSL-side blastFoam run directories as a
table - name / dims / size / date / state - with Load, Delete, Refresh
and a plain directory Browse fallback.

Listing is instant (names + the case.json dims); sizes and the alive
state cost WSL round trips over 9p, so they are filled in from a worker
thread while a status line says so. Delete refuses runs whose solver is
alive (or whose state is unknown) and asks for confirmation. The data
sources are injectable (`lister`, `sizer`, `deleter`, `confirm`) so the
headless test drives the widget without WSL.
"""

import json
import os
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from . import theme
from .theme import GAP, PAD, Card, c

COLS = ('name', 'dims', 'size', 'date', 'state')
HEADS = ('Run', 'Dim', 'Size', 'Started', 'State')
WIDTHS = (260, 50, 90, 150, 110)


def human_size(n):
    if n is None:
        return '?'
    n = float(n)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024 or unit == 'TB':
            return f'{n:.0f} {unit}' if unit == 'B' else f'{n:.1f} {unit}'
        n /= 1024.0


def started_from_name(name):
    """'20260905-162157_2d_p26412-00' -> '2026-09-05 16:21:57' ('' if
    the name does not carry a stamp)."""
    try:
        t = time.strptime(name[:15], '%Y%m%d-%H%M%S')
        return time.strftime('%Y-%m-%d %H:%M:%S', t)
    except ValueError:
        return ''


def dims_from_case_json(unc):
    try:
        with open(os.path.join(unc, 'case.json'), encoding='utf-8') as f:
            return f"{int(json.load(f).get('dim'))}D"
    except (OSError, ValueError, TypeError):
        return '?'


def _default_lister():
    from ..solvers.foam.postmortem import list_runs
    return list_runs(check_alive=True)


def _default_sizer(posix_dirs):
    from ..solvers.foam import env
    return env.run_info(posix_dirs)


def _default_deleter(posix_dirs):
    from ..solvers.foam import env
    return env.delete_runs(posix_dirs)


class FoamRunBrowser(ctk.CTkToplevel):
    """`on_load(unc_path)` is called for the selected run (the Results
    panel's loader); `log(str)` receives progress lines."""

    def __init__(self, parent, on_load, log=print, lister=None, sizer=None,
                 deleter=None, confirm=None, autorefresh=True,
                 on_resume=None):
        super().__init__(parent)
        self.title('blastFoam runs')
        self.geometry('760x420')
        self.configure(fg_color=c('bg'))
        self._on_load = on_load
        self._on_resume = on_resume
        self._log = log
        self._lister = lister or _default_lister
        self._sizer = sizer or _default_sizer
        self._deleter = deleter or _default_deleter
        self._confirm = confirm or (lambda title, msg: messagebox.askyesno(
            title, msg, parent=self))
        self.rows = {}              # name -> dict(unc, posix, alive, bytes)
        self._busy = False
        # worker threads post here; the main thread polls (Tk is not
        # thread-safe and `after` from a worker needs a running mainloop)
        self._inbox = queue.Queue()
        self._polling = False

        card = Card(self, title='Runs in WSL (/root/blastlab_runs)', pad=12)
        card.pack(fill='both', expand=True, padx=PAD, pady=PAD)
        # 80+ run dirs with no scrollbar meant mouse-wheel only
        tbl = ctk.CTkFrame(card.body, fg_color='transparent')
        tbl.pack(fill='both', expand=True)
        self.table = ttk.Treeview(tbl, columns=COLS, show='headings',
                                  height=10, selectmode='browse')
        for col, head, w in zip(COLS, HEADS, WIDTHS):
            self.table.heading(col, text=head)
            self.table.column(col, width=w, anchor='w' if col == 'name'
                              else 'center')
        vsb = ttk.Scrollbar(tbl, orient='vertical', command=self.table.yview)
        self.table.configure(yscrollcommand=vsb.set)
        self.table.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')
        self.table.bind('<Double-1>', lambda e: self.load_selected())

        bar = ctk.CTkFrame(card.body, fg_color='transparent')
        bar.pack(fill='x', pady=(GAP, 0))
        self.status = ctk.CTkLabel(bar, text='', font=theme.F_SMALL,
                                   text_color=c('muted'))
        self.status.pack(side='left')

        def button(text, cmd, danger=False):
            return ctk.CTkButton(
                bar, text=text, width=96, height=30, font=theme.F_BODY,
                corner_radius=theme.RADIUS, command=cmd,
                fg_color=c('danger') if danger else c('card2'),
                hover_color=c('danger_hover') if danger else c('border'),
                text_color='white' if danger else c('text'))
        self.btn_close = button('Close', self.destroy)
        self.btn_close.pack(side='right', padx=(GAP, 0))
        self.btn_delete = button('Delete', self.delete_selected, danger=True)
        self.btn_delete.pack(side='right', padx=(GAP, 0))
        self.btn_load = button('Load', self.load_selected)
        self.btn_load.pack(side='right', padx=(GAP, 0))
        if on_resume is not None:
            # N6/T43: continue a STOPPED run from its last written time
            self.btn_resume = button('Resume', self.resume_selected)
            self.btn_resume.pack(side='right', padx=(GAP, 0))
        self.btn_refresh = button('Refresh', self.refresh)
        self.btn_refresh.pack(side='right', padx=(GAP, 0))
        button('Browse…', self.browse).pack(side='right', padx=(GAP, 0))
        if autorefresh:
            self.refresh()

    # ── data ─────────────────────────────────────────────────────────────
    def refresh(self):
        """Names + dims + start time now; sizes and alive state from a
        worker thread (the WSL round trips)."""
        if self._busy:
            return
        self._busy = True
        self.status.configure(text='listing runs…')
        for iid in self.table.get_children():
            self.table.delete(iid)
        self.rows = {}

        def work():
            try:
                runs = self._lister()
                rows = {}
                for name, unc, alive in runs:
                    rows[name] = dict(unc=unc, alive=alive, bytes=None,
                                      posix=self._posix(unc, name),
                                      dims=dims_from_case_json(unc))
                self._inbox.put(('rows', dict(rows), False))
                sizes = self._sizer([r['posix'] for r in rows.values()])
                for r in rows.values():
                    info = sizes.get(r['posix'])
                    if info is not None:
                        r['bytes'] = info.get('bytes')
                self._inbox.put(('rows', rows, True))
            except Exception as exc:          # surfaced, never a dead window
                self._inbox.put(('failed', f'{type(exc).__name__}: {exc}'))

        threading.Thread(target=work, daemon=True).start()
        self._ensure_polling()

    def _ensure_polling(self):
        if not self._polling:
            self._polling = True
            self.after(50, self._poll)

    def _poll(self):
        """Main-thread drain of the worker inbox."""
        if not self.winfo_exists():
            return
        try:
            while True:
                msg = self._inbox.get_nowait()
                kind = msg[0]
                if kind == 'rows':
                    self._fill(msg[1], msg[2])
                elif kind == 'failed':
                    self._failed(msg[1])
                elif kind == 'deleted':
                    self._deleted(msg[1], msg[2])
        except queue.Empty:
            pass
        if self._busy or not self._inbox.empty():
            self.after(100, self._poll)
        else:
            self._polling = False

    @staticmethod
    def _posix(unc, name):
        from ..solvers.foam import env
        return f'{env.RUNS_ROOT}/{name}' if unc else name

    def _state_text(self, alive):
        return ('running' if alive else 'unknown' if alive is None
                else 'finished')

    def _fill(self, rows, sized):
        if not self.winfo_exists():
            return
        self.status.configure(text_color=c('muted'))
        self.rows = rows
        selected = self.table.selection()
        sel_name = self.table.item(selected[0])['values'][0] if selected \
            else None
        for iid in self.table.get_children():
            self.table.delete(iid)
        total = 0
        for name, r in rows.items():
            size = human_size(r['bytes']) if sized else '…'
            total += r['bytes'] or 0
            iid = self.table.insert('', 'end', iid=name, values=(
                name, r['dims'], size, started_from_name(name),
                self._state_text(r['alive'])))
            if name == sel_name:
                self.table.selection_set(iid)
        n = len(rows)
        if sized:
            self._busy = False
            self.status.configure(
                text=f'{n} run{"s" if n != 1 else ""}, '
                     f'{human_size(total)} total' if n else 'no runs')
        else:
            self.status.configure(text=f'{n} run{"s" if n != 1 else ""} - '
                                       f'measuring sizes…')

    def _failed(self, msg):
        self._busy = False
        self.status.configure(text=f'listing failed: {msg}')
        self._log(f'  [runs] listing failed: {msg}')

    # ── actions ──────────────────────────────────────────────────────────
    def selected(self):
        sel = self.table.selection()
        if not sel:
            return None, None
        name = self.table.item(sel[0])['values'][0]
        return str(name), self.rows.get(str(name))

    def load_selected(self):
        name, r = self.selected()
        if r is None:
            self.status.configure(text='select a run first')
            return
        self._log(f'  [runs] loading {name} ...')
        self._on_load(r['unc'])

    def resume_selected(self):
        """Continue the selected run from its last written time (N6).
        Refused while its solver is alive - Resume is for STOPPED runs -
        or when WSL cannot say (resuming blind would race the solver)."""
        name, r = self.selected()
        if r is None:
            self.status.configure(text='select a run first')
            return
        if r['alive'] is not False:
            why = ('its solver is still running' if r['alive']
                   else 'WSL did not report its state')
            self.status.configure(text=f'not resuming {name}: {why}',
                                  text_color=c('danger'))
            self._log(f'  [runs] refused to resume {name}: {why}')
            return
        self._log(f'  [runs] resuming {name} ...')
        self.destroy()                  # the Run tab takes over
        self._on_resume(r['unc'])

    def delete_selected(self):
        name, r = self.selected()
        if r is None:
            self.status.configure(text='select a run first')
            return
        if r['alive'] is not False:
            why = ('its solver is still running' if r['alive']
                   else 'WSL did not report its state')
            # a muted status line was easy to miss for a refused delete
            self.status.configure(text=f'not deleting {name}: {why}',
                                  text_color=c('danger'))
            self._log(f'  [runs] refused to delete {name}: {why}')
            messagebox.showwarning(
                'Delete run', f'{name} was not deleted: {why}.', parent=self)
            return
        size = human_size(r['bytes'])
        if not self._confirm('Delete run', f'Delete {name} ({size}) from the '
                                           f'WSL disk? This cannot be undone.'):
            return
        self.status.configure(text=f'deleting {name}…')

        self._busy = True

        def work():
            ok = self._deleter([r['posix']])
            self._inbox.put(('deleted', name, ok))

        threading.Thread(target=work, daemon=True).start()
        self._ensure_polling()

    def _deleted(self, name, ok):
        self._log(f'  [runs] {"deleted" if ok else "could not delete"} {name}')
        self._busy = False
        if not self.winfo_exists():
            return
        self.refresh()

    def browse(self):
        from ..solvers.foam import env
        initial = env.unc(env.RUNS_ROOT)
        path = filedialog.askdirectory(
            title='Load a finished blastFoam run directory', parent=self,
            initialdir=initial if os.path.isdir(initial) else None)
        if path:
            self._on_load(path)
