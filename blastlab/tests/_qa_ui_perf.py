"""The port's cost, against the numbers the Tk QA runs recorded.

M6 asks for a comparison rather than an impression, so the Tk figures
are pinned here from `~/blastlab_qa/night2` and `night3` (2026-09-08 and
09-10) and printed beside freshly measured Qt ones. Nothing here fails a
build on a timing - machines and loads differ - except the two gates
that exist to catch a REGRESSION rather than a slow machine: the
keystroke burst must not stall the UI, and an idle tab must not spin.

Measured on a real platform, because an offscreen window skips the paint
work that half of these numbers are about.

Two honest caveats about the comparison. The Tk figures come from runs
on other days under other loads, so a 2x is indicative and not a
controlled benchmark. And the idle-CPU columns are not instrumented
identically: the Tk harness sampled the process, this measures
`process_time` over wall time. Both mean "the share of a core this
process burns while nothing is happening", which is the question, but
they are not the same instrument and a few tenths of a per cent between
them means nothing.

Run:  cd blastlab/tests && python _qa_ui_perf.py
      python _qa_ui_perf.py --idle 8     (longer idle sampling)
"""
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
os.environ.pop('QT_QPA_PLATFORM', None)
os.environ.setdefault('MPLBACKEND', 'Agg')
_dir = tempfile.mkdtemp(prefix='blastlab_ui_perf_')
_settings = os.path.join(_dir, 'settings.json')
with open(_settings, 'w', encoding='utf-8') as _f:
    _f.write('{"auto_cleanup": false}')
os.environ['BLASTLAB_SETTINGS'] = _settings

#: what the Tk app measured, from the QA runs named in the docstring.
#: Two runs where there are two, so the spread is visible rather than
#: hidden behind a single figure.
TK = {
    'construction_ms': (3838.0, 3871.0),
    'first_paint_ms': (1996.0, 2034.0),
    'idle_cpu_setup_pct': (5.26, 20.27),
    'idle_cpu_run_pct': (2.50, 3.74),
    'idle_cpu_results_pct': (1.56, 4.05),
    'idle_cpu_chain_pct': (4.04, 4.05),
}

#: a keystroke must never leave the UI blocked this long (G4's shape)
BURST_GAP_GATE_MS = 400.0
#: a tab doing nothing must not spin; Tk's worst recorded was 20 %
IDLE_GATE_PCT = 25.0

FAIL = []
OUT = {}


def gate(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def main():
    idle_s = 5.0
    if '--idle' in sys.argv:
        idle_s = float(sys.argv[sys.argv.index('--idle') + 1])

    from PySide6.QtCore import QEvent, QObject
    from PySide6.QtWidgets import QApplication
    app = QApplication(['blastlab-perf'])
    if app.platformName() == 'offscreen':
        print('SKIP: an offscreen window does not paint')
        return 0
    from blastlab.core.case import Case2D
    from blastlab.ui import theme
    theme.apply(app, 'dark')
    from blastlab.ui.app import MainWindow

    def pump(n):
        for _ in range(n):
            app.processEvents()
            time.sleep(0.005)

    print('measuring...')
    t0 = time.perf_counter()
    win = MainWindow()
    OUT['construction_ms'] = (time.perf_counter() - t0) * 1e3

    class FirstPaint(QObject):
        def __init__(self):
            super().__init__()
            self.at = None

        def eventFilter(self, obj, ev):
            if self.at is None and ev.type() == QEvent.Paint:
                self.at = time.perf_counter()
            return False

    watch = FirstPaint()
    win.centralWidget().installEventFilter(watch)
    win.resize(1280, 860)
    t1 = time.perf_counter()
    win.show()
    for _ in range(2000):
        app.processEvents()
        if watch.at is not None:
            break
        time.sleep(0.002)
    OUT['first_paint_ms'] = ((watch.at or time.perf_counter()) - t1) * 1e3
    pump(150)

    # set_case -> the preview actually holding a figure
    case = Case2D(geometry='planar', Lx=2.0, Ly=1.2, cell_size_m=0.03,
                  charge=5.0, center=(0.4, 0.0), n_snapshots=2,
                  record_frames=0, anim_file=None)
    win._show('setup')
    pump(60)
    t2 = time.perf_counter()
    win.setup.set_case(case)
    win.setup.update_preview(win.setup.get_case())
    for _ in range(1200):
        app.processEvents()
        if win.setup.preview_kind() != 'none':
            break
        time.sleep(0.002)
    OUT['set_case_to_preview_ms'] = (time.perf_counter() - t2) * 1e3
    pump(80)

    # a 40-keystroke burst into a field that drives the preview: the
    # cost is not the typing, it is the debounced redraw behind it
    field = win.setup.form.v['Lx']
    t3 = time.perf_counter()
    gaps = []
    last = t3
    for i in range(40):
        field.set(f'{2.0 + i * 0.01:.2f}')
        app.processEvents()
        now = time.perf_counter()
        gaps.append((now - last) * 1e3)
        last = now
    OUT['burst40_total_ms'] = (time.perf_counter() - t3) * 1e3
    OUT['burst40_max_gap_ms'] = max(gaps)
    pump(200)                       # let the debounce settle

    # idle CPU per tab: this process's own CPU time over wall time,
    # which is what "the tab is spinning" means to the machine
    for key, tab in (('setup', 'setup'), ('run', 'run'),
                     ('results', 'results'), ('chain', 'chain')):
        win._show(tab)
        pump(120)
        c0, w0 = time.process_time(), time.perf_counter()
        while time.perf_counter() - w0 < idle_s:
            app.processEvents()
            time.sleep(0.005)
        OUT[f'idle_cpu_{key}_pct'] = 100.0 * (
            (time.process_time() - c0) / (time.perf_counter() - w0))

    print('\n' + '=' * 66)
    print(f'{"":30} {"Qt":>10}   {"Tk (recorded)":>22}')
    for key in ('construction_ms', 'first_paint_ms',
                'set_case_to_preview_ms', 'burst40_total_ms',
                'burst40_max_gap_ms', 'idle_cpu_setup_pct',
                'idle_cpu_run_pct', 'idle_cpu_results_pct',
                'idle_cpu_chain_pct'):
        qt = OUT.get(key)
        tk = TK.get(key)
        tk_s = ('  ' + ' / '.join(f'{v:.0f}' if v > 100 else f'{v:.2f}'
                                  for v in tk)) if tk else '  (not recorded)'
        ratio = ''
        if tk and qt:
            best = min(tk)
            ratio = f'   {qt / best:.2f}x the best Tk run'
        print(f'{key:30} {qt:10.1f}   {tk_s:>22}{ratio}')
    print('=' * 66)

    print('\ngates (these are about regressions, not about this machine):')
    gate(f'a keystroke never blocks the UI for {BURST_GAP_GATE_MS:.0f} ms',
         OUT['burst40_max_gap_ms'] <= BURST_GAP_GATE_MS,
         f'worst gap {OUT["burst40_max_gap_ms"]:.0f} ms')
    for key in ('setup', 'run', 'results', 'chain'):
        pct = OUT[f'idle_cpu_{key}_pct']
        gate(f'the {key} tab is quiet when idle',
             pct <= IDLE_GATE_PCT, f'{pct:.1f} % of one core')

    path = os.path.join(_dir, 'qt_perf.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(OUT, f, indent=2, sort_keys=True)
    print(f'\nwritten to {path}')
    win.close()
    pump(60)
    if FAIL:
        print(f'\nUI PERF: {len(FAIL)} gate(s) failed: {FAIL}')
        return 1
    print('\nUI PERF: PASS (all gates)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
