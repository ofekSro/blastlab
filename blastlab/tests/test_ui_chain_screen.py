"""GUI-9 gate: the Chain screen (docs/gui-redesign-plan.md section 8,
board Chain; batch docs/batches/2026-09-29-gui-chain.md).

 S1  the routes (T1): `chain_route` is toolkit-free; the four routes,
     their keys and labels, `route_dims` / `route_key` refuse anything
     else; the hand-off names are `model_folder.handoff_paths`' own; the
     top bar's Chain link follows the route and still navigates.
 S2  layout (T2): tree 272, properties 340, cards 308 at 1600 x 1000;
     nothing clipped at 1100 x 720 and 1280 x 840, both modes, every
     route, stage and visible node; the caption, key lines, titles and
     hand-off labels are never cut mid-glyph.
 S3  cards and arrows per route: count, numbers, folders, arrow labels,
     the Run chain line, the HAND-OFF IN / OUT files of plan §8.2 and
     their texts (chain_route's, for the wired case).
 S4  the stage editor: the tree is ['stage'] + Setup's nodes; a node
     shows only its cards; 'nodes' placement; a fed stage hides
     Initialize from / Profile file and get_case() is unchanged; the
     header numbers are setup_strip.tiles'; a 3D stage shows the hint,
     no canvas and no View3DHost.
 S5  live validation: a bad field on stage 2 only, the checks equal
     stage_errors line for line, the native -> blastFoam rule, the
     debounce (one check for two edits; the Setup's interval), Run chain
     stays enabled and run() refuses naming the stage.
 S6  Copy from 01 Setup, Load case… and seeding on a MainWindow.

Plain script, offscreen, throwaway settings, no window on screen:
    cd blastlab/tests && python test_ui_chain_screen.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
import traceback

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

from blastlab.ui.testing import ensure_qapp, pump             # noqa: E402

app = ensure_qapp()

FAIL = []
RAN = []
TMP = tempfile.mkdtemp(prefix='blastlab_chainscreen_')


def check(name, ok, detail=''):
    RAN.append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def raises(fn, *args):
    try:
        fn(*args)
    except ValueError:
        return True
    return False


# ── S1 ───────────────────────────────────────────────────────────────────
def s1_routes(win):
    from blastlab.services import model_folder
    from blastlab.ui import chain_route as cr
    print('\nS1: the routes')
    code = ('import sys, blastlab.ui.chain_route; '
            'print(sorted({m.split(".")[0] for m in sys.modules '
            'if m.split(".")[0] in ("PySide6", "shiboken6", "vtk", '
            '"vtkmodules", "pyvista")} | ({"pyplot"} if "matplotlib.pyplot" '
            'in sys.modules else set())))')
    out = subprocess.run([sys.executable, '-c', code], cwd=REPO,
                         capture_output=True, text=True, timeout=120)
    check('chain_route imports no toolkit (no Qt, VTK or pyplot)',
          out.returncode == 0 and out.stdout.strip() == '[]',
          (out.stdout + out.stderr).strip()[-200:])
    check('four routes, board order and labels',
          [(k, lbl, d) for k, lbl, d in cr.ROUTES]
          == [('123', '1D → 2D → 3D', (1, 2, 3)), ('13', '1D → 3D', (1, 3)),
              ('12', '1D → 2D', (1, 2)), ('23', '2D → 3D', (2, 3))])
    check('route_dims / route_key round-trip',
          all(cr.route_key(cr.route_dims(k)) == k for k, _l, _d in cr.ROUTES))
    check('route_dims refuses anything else',
          all(raises(cr.route_dims, k) for k in ('', '1', '32', '132', 'x')))
    check('route_key refuses a single stage and a reversed route',
          all(raises(cr.route_key, d) for d in ((1,), (2,), (3, 2), ())))
    target = model_folder.Target(runs_dir=TMP, model='M',
                                 folder=os.path.join(TMP, 'M'))
    want = {(1, 2): 'handoff_1d_to_2d.txt', (1, 3): 'handoff_1d_to_3d.txt',
            (2, 3): 'handoff_2d_to_3d.npz'}
    got = {e: cr.handoff_name(*e) for e in want}
    svc = {e: os.path.basename(model_folder.handoff_paths(target, e)[e])
           for e in want}
    check('the hand-off names are model_folder.handoff_paths\' own '
          '(plan §8.2)', got == want == svc, str(got))

    link = win.topbar.nav_btns['chain']
    check('the top bar starts on Chain 1D → 2D → 3D',
          link.text() == 'Chain 1D → 2D → 3D', link.text())
    seen = []
    win.chain.route_changed.connect(seen.append)
    win.chain.set_route('13')
    pump(20)
    check('set_route(13) -> the link reads Chain 1D → 3D',
          link.text() == 'Chain 1D → 3D', link.text())
    check('route_changed fired once with the key', seen == ['13'], str(seen))
    win.chain.set_route('13')
    check('the same route again fires nothing', seen == ['13'], str(seen))
    link.click()
    pump(30)
    check('and the link still navigates to the Chain screen',
          win.current_tab() == 'chain', str(win.current_tab()))
    win.chain.route_btns['12'].click()
    pump(20)
    check('a click on a route button is a route change too',
          win.chain.route() == '12' and link.text() == 'Chain 1D → 2D',
          f'{win.chain.route()} {link.text()}')
    win.chain.set_route('123')
    pump(20)
    check('and back to Chain 1D → 2D → 3D',
          link.text() == 'Chain 1D → 2D → 3D', link.text())
    win._show('setup')
    pump(20)


# ── S2 ───────────────────────────────────────────────────────────────────
def cut_texts(panel):
    """Every Chain text cut mid-glyph: an elided label whose painted text
    is wider than the label, or cut without its whole text as the
    tooltip; a hand-off line wider than its label."""
    from PySide6.QtWidgets import QLabel
    from blastlab.ui.results_list import ElidedLabel
    bad = []
    for lbl in panel.findChildren(ElidedLabel):
        if not lbl.isVisible():
            continue
        shown = QLabel.text(lbl)
        if lbl.fontMetrics().horizontalAdvance(shown) > lbl.width() + 1:
            bad.append(('wider than its label', lbl.objectName(),
                        ascii(shown)))
        if lbl.elided() and not lbl.toolTip():
            bad.append(('cut without a tooltip', lbl.objectName(),
                        ascii(lbl.full_text())))
    for a in panel.arrows:
        lab = a.label
        if not lab.isVisible():
            continue
        for line in lab.text().split('\n'):
            if lab.fontMetrics().horizontalAdvance(line) > lab.width() + 1:
                bad.append(('hand-off line cut', ascii(line), lab.width()))
        if lab.toolTip() != lab.full_text():
            bad.append(('hand-off tooltip', ascii(lab.toolTip())))
    return bad


def s2_layout(win):
    from test_ui_parity import clipped
    print('\nS2: layout')
    ch = win.chain
    win._show('chain')
    win.resize(1600, 1000)
    ch.set_route('123')
    ch.focus_stage(2)
    pump(400)
    ed = ch.editors[2]
    check('1600 x 1000: the stage tree is 272 px',
          abs(ed.tree.width() - 272) <= 1, str(ed.tree.width()))
    check('1600 x 1000: the properties column is 340 px',
          abs(ed.props_width() - 340) <= 1, str(ed.props_width()))
    widths = [ch.cards[d].width() for d in (1, 2, 3)]
    check('1600 x 1000: the cards are 308 px (route 123)',
          all(abs(w - 308) <= 1 for w in widths), str(widths))
    check('and the links are the board\'s 118 px',
          [a.width() for a in ch.arrows] == [118, 118],
          str([a.width() for a in ch.arrows]))
    heights = dict(
        group=ch.route_bar.height(),
        routes=sorted({b.height() for b in ch.route_btns.values()}),
        run=(ch.run_btn.width(), ch.run_btn.height()),
        copy=ed.copy_btn.height(), load=ed.load_btn.height(),
        pill=ed.tree.pill.height(),
        tools=sorted({b.height() for b in (ed.show_mesh, ed.fit_btn)}))
    check('the board heights hold under the QSS (D41): route group 38 with '
          '32 px buttons, Run chain 176 x 56, Copy / Load 36, pill 40, '
          'the view tools 28',
          heights == dict(group=38, routes=[32], run=(176, 56), copy=36,
                          load=36, pill=40, tools=[28]), str(heights))
    ch.set_route('13')
    pump(200)
    check('a two-stage route\'s link is 200 px',
          [a.width() for a in ch.arrows] == [200],
          str([a.width() for a in ch.arrows]))
    check('the route row\'s caption is the board\'s line',
          ch.caption.full_text() == 'New stages take the charge, material '
                                    'and solver from 01 Setup.')
    bad, cut, n = [], [], 0
    for mode in ('native', 'blastfoam'):
        win.set_solver(mode)
        pump(100)
        for size in ((1100, 720), (1280, 840)):
            win.resize(*size)
            pump(250)
            for key, _l, dims in __import__(
                    'blastlab.ui.chain_route',
                    fromlist=['ROUTES']).ROUTES:
                ch.set_route(key)
                pump(120)
                for d in dims:
                    ch.focus_stage(d)
                    pump(60)
                    ed = ch.editors[d]
                    for node in ed.visible_nodes():
                        ed.select_node(node)
                        pump(30)
                        n += 1
                        got = clipped(win)
                        if got:
                            got.sort(key=lambda t: -t[2])
                            bad.append((mode, size, key, d, node, got[0]))
                    texts = cut_texts(ch)
                    if texts:
                        cut.append((mode, size, key, d, texts[0]))
    check(f'1100 x 720 and 1280 x 840, both modes, every route, stage and '
          f'node ({n} pages): nothing clipped', not bad, str(bad[:3]))
    check('the caption, titles, key lines, states and hand-off labels are '
          'never cut mid-glyph (elided or wrapped, with the tooltip)',
          not cut, str(cut[:3]))
    win.resize(1100, 720)
    ch.set_route('123')
    pump(200)
    a = ch.arrows[0]
    check('at 1100 x 720 a narrow link wraps its file after an underscore',
          '\n' in a.label.text()
          and all(ln.endswith('_') for ln in a.label.text().split('\n')[:-1])
          and a.label.text().replace('\n', '') == 'handoff_1d_to_2d.txt',
          ascii(a.label.text()))
    check('and the link never widens the row (links 64 px, cards >= 200)',
          all(x.width() >= 64 for x in ch.arrows)
          and all(ch.cards[d].width() >= 200 for d in (1, 2, 3)),
          str([x.width() for x in ch.arrows]))
    win.set_solver('native')
    pump(100)

    # the new text pairs on the selected card / tinted hand-off card and
    # the arrow, both modes (T3's contrast table has every pair)
    from blastlab.ui import theme

    def lum(h):
        c = [int(h[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4
             for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

    def ratio(a, b):
        hi, lo = sorted((lum(a), lum(b)), reverse=True)
        return (hi + 0.05) / (lo + 0.05)
    low = []
    for mode, p in (('dark', theme.DARK), ('light', theme.LIGHT)):
        tint = theme.chain_tint(mode)
        for key in ('accent_text', 'ok', 'warn', 'danger', 'faint', 'text2',
                    'text'):
            if ratio(p[key], tint) < 4.5:
                low.append((mode, key, round(ratio(p[key], tint), 2)))
        arrow = p['accent'] if mode == 'dark' else p['accent_text']
        if ratio(arrow, p['bg']) < 3.0:
            low.append((mode, 'arrow', round(ratio(arrow, p['bg']), 2)))
        if ratio(p['accent_soft'], p['bg']) < 4.5:
            low.append((mode, 'accent_soft on bg'))
    check('the selected card\'s and the hand-off card\'s texts >= 4.5:1, '
          'the arrow >= 3:1, both modes', not low, str(low))


# ── S3 ───────────────────────────────────────────────────────────────────
def s3_cards(win):
    from blastlab.ui import chain_route as cr
    print('\nS3: cards and arrows, per route')
    ch = win.chain
    os.makedirs(os.path.join(TMP, 'runs'), exist_ok=True)
    win.run_panel.set_runs_dir(os.path.join(TMP, 'runs'))
    win.run_panel.set_run_name('CHAIN', replace=True)
    win._show('chain')
    table = {(1, 2): 'handoff_1d_to_2d.txt', (2, 3): 'handoff_2d_to_3d.npz',
             (1, 3): 'handoff_1d_to_3d.txt'}
    for key, _l, dims in cr.ROUTES:
        ch.set_route(key)
        pump(450)
        shown = [d for d in (1, 2, 3) if ch.cards[d].isVisible()]
        check(f'{key}: one card per stage', shown == sorted(dims)
              and len(dims) == len(ch.arrows) + 1, str(shown))
        check(f'{key}: numbered 01… in route order',
              [ch.cards[d].num.text() for d in dims]
              == [f'{i + 1:02d}' for i in range(len(dims))])
        check(f'{key}: the folders',
              [ch.cards[d].folder.text() for d in dims]
              == ['\\' + f'{d}d' for d in dims])
        check(f'{key}: the arrows name the hand-off files',
              [a.name() for a in ch.arrows]
              == [table[(a, b)] for a, b in zip(dims, dims[1:])],
              str([a.name() for a in ch.arrows]))
        check(f'{key}: Run chain says where it goes',
              ch.run_line_text() == f'{len(dims)} stages · into \\CHAIN\\',
              ascii(ch.run_line_text()))
        checks = ch.checks()
        for d in dims:
            prev, nxt = cr.neighbours(dims, d)
            ed = ch.editors[d]
            case = checks[d].case
            want_in = table[(prev, d)] if prev else 'none'
            want_out = table[(d, nxt)] if nxt else 'none'
            check(f'{key}: stage {d} hand-off in {want_in}, out {want_out}',
                  ed.hand_in.file.text() == want_in
                  and ed.hand_out.file.text() == want_out,
                  f'{ed.hand_in.file.text()} / {ed.hand_out.file.text()}')
            check(f'{key}: stage {d} hand-off texts are chain_route\'s '
                  f'for the wired case',
                  case is not None
                  and ed.hand_in.caption.text() == cr.in_text(case, prev)
                  and ed.hand_out.caption.text() == cr.out_text(case, nxt),
                  ascii(ed.hand_in.caption.text()[:60]))
    ch.set_route('123')
    pump(400)
    case1 = ch.checks()[1].case
    check('the 1D out-text names Outer (it ends the run) and its radius',
          'Outer (10.0 m)' in ch.editors[1].hand_out.caption.text()
          and 'Outer' in __import__('blastlab.ui.setup_nodes', fromlist=[
              'terminate_sides']).terminate_sides(case1),
          ascii(ch.editors[1].hand_out.caption.text()))
    f2 = ch.forms[2]
    f2.points['gauges'].set([(1.5, 1.0)])
    f2.v['trigger_gauge'].set('1')
    f2.v['trigger_action'].set('remap')
    pump(450)
    check('the 2D out-text names the trigger gauge and its action',
          ch.editors[2].hand_out.caption.text().startswith(
              'The field when the wave reaches G1 (trigger gauge, remap)'),
          ascii(ch.editors[2].hand_out.caption.text()))
    check('the 2D in-text names the 2D form\'s burst height',
          'z 2.0 m' in ch.editors[2].hand_in.caption.text(),
          ascii(ch.editors[2].hand_in.caption.text()))
    f2.v['trigger_gauge'].set('')
    f2.v['trigger_action'].set('terminate')
    f2.points['gauges'].set([])
    pump(450)

    # the folder note names the model folder (D47's rule) and a long
    # path wraps inside the 340 px column instead of widening it
    from blastlab.services import model_folder
    ed = ch.editors[2]
    ch.focus_stage(2)
    ed.select_node('stage')
    pump(300)
    want = model_folder.folder_for(os.path.join(TMP, 'runs'), 'CHAIN')
    note = ed.note.text().replace('​', '')
    check('the folder note names the model folder',
          f'The files go to {want}{os.sep} (1d, 2d, 3d' in note,
          ascii(note[:120]))
    check(f'and a {len(want)}-character folder path wraps: the column '
          f'stays 340 px', ed.props_width() == 340, str(ed.props_width()))
    win.run_panel.set_run_name('M' * 60, replace=True)
    pump(450)
    path_part = ch.run_line_text().split(' ')[-1]
    check('a 60-character model name is elided on the Run chain line, '
          'whole in its tooltip',
          '…' in ch.run_line_text() and ch.run_line.toolTip()
          == 'Into ' + 'M' * 60
          and ch.run_line.fontMetrics().horizontalAdvance(path_part)
          <= ch.run_line.width(), ascii(ch.run_line_text()))
    win.run_panel.set_run_name('CHAIN', replace=True)
    pump(450)


# ── S4 ───────────────────────────────────────────────────────────────────
def s4_editor(win):
    import dataclasses
    from blastlab.ui import setup_nodes, setup_strip
    from blastlab.ui.chain_stage import HINT_3D, header_numbers
    from blastlab.ui.mpl_canvas import MplCanvas
    from blastlab.ui.view3d_host import View3DHost
    print('\nS4: the stage editor')
    ch = win.chain
    win._show('chain')
    ch.set_route('123')
    pump(400)
    for mode in ('native', 'blastfoam'):
        win.set_solver(mode)
        pump(400)
        for d in (1, 2, 3):
            win.setup.set_dim(d)
            pump(100)
            ch.focus_stage(d)
            pump(100)
            want = ['stage'] + win.setup.visible_nodes()
            check(f'{mode} {d}D: the tree is 00 Stage + Setup\'s nodes',
                  ch.editors[d].visible_nodes() == want,
                  f'{ch.editors[d].visible_nodes()} vs {want}')
    win.setup.set_dim(2)
    win.set_solver('native')
    pump(300)
    ed = ch.editors[2]
    ch.focus_stage(2)
    for node in ed.visible_nodes()[1:]:
        ed.select_node(node)
        pump(30)
        want = [t for t in setup_nodes.node_cards(2, node)
                if ed.form.card_visible(t)]
        check(f'02 {node}: only its cards', ed.shown_cards() == want,
              f'{ed.shown_cards()} vs {want}')
    ed.select_node('stage')
    pump(20)
    check('00 Stage shows the stage page and no node card',
          ed.shown_cards() == [] and ed.stage_page.isVisible())
    check("the stage forms use the 'nodes' placement",
          all(ch.forms[d].placement == 'nodes' for d in (1, 2, 3)))
    f = ch.forms[2]
    check('a fed stage (02 after 1D) hides Initialize from and Profile '
          'file', f.fed and not f.row_visible('init_mode')
          and not f.row_visible('profile_in'),
          f'{f.fed} {f.row_visible("init_mode")}')
    f.set_fed(False)
    before = dataclasses.asdict(f.get_case())
    shown = f.row_visible('init_mode')
    f.set_fed(True)
    after = dataclasses.asdict(f.get_case())
    check('and get_case() is the same before and after set_fed(True)',
          before == after and shown, str(shown))
    check('the Setup\'s forms are never fed',
          not any(sf.fed for sf in win.setup.forms.values()))
    checks = ch.checks()
    for d in (1, 2, 3):
        chk = checks[d]
        want = header_numbers(setup_strip.tiles(chk.case, chk.report))
        check(f'stage {d}: the header numbers are setup_strip.tiles\' '
              f'for the wired case', ch.editors[d].numbers.full_text()
              == want and bool(want), ascii(want))
    e3 = ch.editors[3]
    check('a 3D stage shows the hint, no canvas, no View3DHost',
          e3.hint is not None and e3.hint.text() == HINT_3D
          and not e3.findChildren(MplCanvas)
          and not ch.findChildren(View3DHost)
          and e3.preview is None)
    check('the 1D / 2D stages draw the Setup\'s previews',
          ch.editors[1].preview is not None
          and ch.editors[2].preview is not None)


# ── S5 ───────────────────────────────────────────────────────────────────
def s5_live(win):
    from blastlab.services.chain import HANDOFF_MSG, stage_errors
    from blastlab.ui import chain_route as cr
    from blastlab.ui.chain_panel import CHECK_MS
    print('\nS5: live validation')
    ch = win.chain
    win._show('chain')
    win.set_solver('native')
    ch.set_route('123')
    pump(450)
    check('all three cards start ● case OK',
          [ch.cards[d].state_text() for d in (1, 2, 3)]
          == ['● case OK'] * 3,
          ascii([ch.cards[d].state_text() for d in (1, 2, 3)]))
    ch.forms[2].v['Lx'].set('abc')
    pump(400)
    ed = ch.editors[2]
    check('Lx abc: card 2 reads ● 1 error in danger',
          ch.cards[2].state_text() == '● 1 error'
          and ch.cards[2].state_key() == 'error',
          ascii(ch.cards[2].state_text()))
    check('and 02 Domain is ✗ in its tree',
          ed.tree.rows['domain']._status == 'error'
          and all(ed.tree.rows[n]._status == 'ok'
                  for n in ('threat', 'bounds')))
    check('and its pill says 1 error', ed.pill() == ('error', '1 error'),
          str(ed.pill()))
    check('cards 1 and 3 stay ● case OK',
          ch.cards[1].state_text() == '● case OK'
          and ch.cards[3].state_text() == '● case OK')
    check('Run chain stays enabled through a stage error',
          ch.run_btn.isEnabled())
    seen = []
    ch.error_sink = lambda t, lines: seen.append(list(lines))
    ok = ch.run()
    check('run() refuses, naming the stage, and brings it forward',
          ok is False and seen and all(ln.startswith('Stage 2 (2D): ')
                                       for ln in seen[-1])
          and ch.stage() == 2, ascii(seen[-1:]))
    ch.forms[2].v['Lx'].set('4')
    pump(400)
    check('fixed: all three ● case OK again',
          [ch.cards[d].state_text() for d in (1, 2, 3)]
          == ['● case OK'] * 3 and ed.pill()[0] == 'ok')

    ch.forms[2].v['cy'].set('99')
    pump(400)
    checks = ch.checks()
    wired = {d: checks[d].case for d in (1, 2, 3)}
    pre = cr.stage_prefix(2)
    want = [e[len(pre):] for e in stage_errors([1, 2, 3], wired)
            if e.startswith(pre)]
    check('cy 99: stage 2\'s errors are stage_errors\' Stage 2 lines',
          checks[2].errors == want and bool(want), ascii(want))
    check('and no other stage lists them',
          not any(set(want) & set(checks[d].errors) for d in (1, 3)))
    check('the Checks list shows them, errors first',
          [m for s, m in ed.check_rows() if s == 'error'] == want)
    ch.forms[2].v['cy'].set('2')
    pump(400)

    ch.set_stage_solver(1, 'native')
    ch.set_stage_solver(2, 'blastfoam')
    pump(400)
    checks = ch.checks()
    ch.focus_stage(2)
    ed.select_node('stage')
    pump(30)
    check('native 1D -> blastFoam 2D: card 2 shows the error',
          ch.cards[2].state_key() == 'error'
          and HANDOFF_MSG in checks[2].errors,
          ascii(ch.cards[2].state_text()))
    check('and 00 Stage shows the refusal where the solver is chosen',
          ch._compat[2].isVisibleTo(ed) and ch._compat[2].text()
          == HANDOFF_MSG and ed.tree.rows['stage']._status == 'error')
    ch.set_stage_solver(2, 'native')
    pump(400)

    calls = []
    real = cr.stage_checks

    def counting(*a, **k):
        calls.append(1)
        return real(*a, **k)
    cr.stage_checks = counting
    try:
        ch.forms[2].v['Lx'].set('4.5')
        pump(100)
        ch.forms[2].v['Lx'].set('4')
        pump(450)
    finally:
        cr.stage_checks = real
    check('two edits 100 ms apart run the checks once', len(calls) == 1,
          str(len(calls)))
    check('the debounce is the Setup\'s',
          ch._check_timer.interval() == win._validate_timer.interval()
          == CHECK_MS and ch._check_timer.isSingleShot(),
          str(ch._check_timer.interval()))
    from PySide6.QtCore import QTimer
    timers = [t for t in ch.findChildren(QTimer) if t.isActive()]
    check('and no timer runs on the idle Chain screen', not timers,
          str(len(timers)))


# ── S6 ───────────────────────────────────────────────────────────────────
def s6_copy_load():
    import dataclasses
    from blastlab.models.case import Case1D, Case2D, load_case, save_case
    from blastlab.ui import dialogs
    from blastlab.ui.app import MainWindow
    from blastlab.ui.case_form import CaseForm
    from blastlab.ui.chain_panel import COPY_BAD
    print('\nS6: Copy from 01 Setup, Load case…, seeding')
    real = (dialogs.ask_yes_no, dialogs.open_file, dialogs.show_error)
    asked, errors = [], []
    dialogs.ask_yes_no = lambda *a, **k: asked.append(a[:2]) or False
    dialogs.show_error = lambda t, m, p=None: errors.append((t, m))
    win = MainWindow()
    try:
        win.show()
        pump(200)
        src = Case2D(charge=2.5, material='C4', solver='native')
        win.setup.set_case(src)
        pump(400)
        ch = win.chain
        win._show('chain')
        pump(450)

        def values(d):
            return ch.forms[d].field_values()

        # the seed is the Setup CASE (what runs): a native case always
        # carries material TNT, whatever its hidden box holds
        # (models/fields.py `_charge_model`, UX-E2) - checked again on
        # blastFoam below, where C4 is what runs
        mat = win.setup.get_case().material
        check('the native Setup case carries TNT (the native rule)',
              mat == 'TNT', mat)
        for d in (1, 3):
            fresh = CaseForm(d, mode='native', placement='nodes')
            want = dict(fresh.field_values(), charge='2.5', material=mat)
            fresh.deleteLater()
            got = values(d)
            diff = {k: (got[k], want[k]) for k in want if got[k] != want[k]}
            check(f'untouched stage {d}: charge 2.5, the case\'s material, '
                  f'native, the rest the spec default', not diff
                  and ch.stage_solver[d] == 'native'
                  and not ch.touched(d), ascii(diff))
        ok = ch.copy_from_setup(2)
        pump(100)
        check('stage 2 Copy: the 2D Setup case, whole (asdict)',
              ok and dataclasses.asdict(ch.forms[2].get_case())
              == dataclasses.asdict(win.setup.get_case())
              and ch.touched(2) and not asked, str(asked))
        ok = ch.copy_from_setup(1)
        pump(100)
        check('stage 1 Copy of a 2D Setup: the seeding rule, then touched',
              ok and values(1)['charge'] == '2.5'
              and values(1)['material'] == mat and ch.touched(1)
              and not asked, str(asked))
        before = dataclasses.asdict(ch.forms[2].get_case())
        ok = ch.copy_from_setup(2)
        check('a touched stage asks once; Keep changes nothing',
              ok is False and len(asked) == 1
              and asked[0][1] == 'Replace stage 02\'s settings with 01 '
                                 'Setup\'s?'
              and dataclasses.asdict(ch.forms[2].get_case()) == before,
              ascii(asked))

        # seeding follows Setup for an untouched stage only
        win.setup.form.v['charge'].set('3.5')
        pump(100)
        win._show('setup')
        pump(100)
        win._show('chain')
        pump(450)
        check('Setup changed: the untouched stage 3 follows it',
              values(3)['charge'] == '3.5', values(3)['charge'])
        check('the touched stages 1 and 2 do not',
              values(1)['charge'] == '2.5' and values(2)['charge'] == '2.5',
              f"{values(1)['charge']} {values(2)['charge']}")
        # blastFoam: the material box is what runs, so C4 is seeded
        win._show('setup')
        win.set_solver('blastfoam')
        pump(200)
        win._show('chain')
        pump(450)
        check('on blastFoam the untouched stage 3 takes C4 and blastFoam',
              win.setup.get_case().material == 'C4'
              and values(3)['material'] == 'C4'
              and ch.stage_solver[3] == 'blastfoam' and not ch.touched(3),
              f"{values(3)['material']} {ch.stage_solver[3]}")
        win.set_solver('native')
        pump(200)

        win._show('setup')
        win.setup.form.v['Lx'].set('abc')
        pump(100)
        win._show('chain')
        pump(450)
        btn = ch.editors[2].copy_btn
        check('Setup with a bad field: Copy is off, with the why-not',
              not btn.isEnabled() and btn.toolTip() == COPY_BAD,
              ascii(btn.toolTip()))
        win.setup.form.v['Lx'].set('4')
        pump(100)

        one = os.path.join(TMP, 'one.json')
        two = os.path.join(TMP, 'two.json')
        save_case(Case1D(radius_m=1.5, charge_kg=0.7, cell_size_m=0.004,
                         gauge_radii=[0.5, 1.0], solver='native'), one)
        save_case(Case2D(charge=1.5, solver='native'), two)
        dialogs.open_file = lambda *a, **k: one
        ok = ch.load_case(1)
        pump(100)
        check('Load case… a 1D case into stage 1: get_case() equals '
              'load_case', ok and dataclasses.asdict(ch.forms[1].get_case())
              == dataclasses.asdict(load_case(one)) and not errors,
              ascii(errors))
        before = dataclasses.asdict(ch.forms[1].get_case())
        dialogs.open_file = lambda *a, **k: two
        ok = ch.load_case(1)
        pump(100)
        check('a 2D case into stage 1: one error naming both dimensions, '
              'the stage unchanged',
              ok is False and errors == [('Load case', 'That case is 2D; '
                                                       'stage 01 is 1D.')]
              and dataclasses.asdict(ch.forms[1].get_case()) == before,
              ascii(errors))
        dialogs.open_file = lambda *a, **k: ''
        check('a cancelled dialog loads nothing', ch.load_case(1) is False
              and len(errors) == 1)

        # verify (GUI-9): only a Setup that does not parse (ValueError)
        # reads as "01 Setup has errors"; any other failure of the source
        # is a bug and must reach the crash log, not be swallowed
        from blastlab.ui.chain_panel import ChainPanel

        def bad_parse():
            raise ValueError("'Lx' is not a number: 'abc'")

        def broken():
            raise RuntimeError('a bug in the Setup source')
        lone = ChainPanel(setup_source=bad_parse)
        lone._refresh_copy()
        off = lone.editors[1].copy_btn
        check('a Setup source that does not parse: Copy off, the why-not',
              not off.isEnabled() and off.toolTip() == COPY_BAD,
              ascii(off.toolTip()))
        lone._setup_source = broken
        try:
            lone._refresh_copy()
            raised = False
        except RuntimeError:
            raised = True
        check('any other failure of the Setup source is not swallowed',
              raised)
        lone.deleteLater()
    finally:
        (dialogs.ask_yes_no, dialogs.open_file,
         dialogs.show_error) = real
        win.close()
        pump(100)


def main():
    from blastlab.ui.app import MainWindow
    crashes = []
    sys.excepthook = lambda *a: crashes.append(
        ''.join(traceback.format_exception(*a)))
    win = MainWindow()
    win.show()
    pump(200)
    try:
        s1_routes(win)
        s2_layout(win)
        s3_cards(win)
        s4_editor(win)
        s5_live(win)
        win.close()
        pump(100)
        s6_copy_load()
    finally:
        check('nothing raised', not crashes, crashes[0][-400:]
              if crashes else '')
        # the recorder is for Qt slots only: an exception out of a check
        # function still prints its traceback (61bfd56)
        sys.excepthook = sys.__excepthook__
        win.close()
        pump(100)
        shutil.rmtree(TMP, ignore_errors=True)
    bad = [m for m in sys.modules
           if m.split('.')[0] in ('vtk', 'vtkmodules', 'pyvista', 'pyvistaqt')
           or m == 'matplotlib.pyplot']
    check('no VTK / pyplot in the GUI process', not bad, str(bad[:3]))
    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        return 1
    print(f'UI CHAIN SCREEN: PASS ({len(RAN)} checks)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
