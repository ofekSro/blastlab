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
 S7  (9b, T4) the 02 Run chain strip, driven through the window's run
     callbacks with a fake clock: the pills and the caption at every step
     of a 3-stage chain, a stop and a failure, the title, a single run
     hiding the slot, the strip's height constant across every state at
     1100 x 720 and 1600 x 1000, nothing clipped, and the viewer shrunk
     ahead only when the 3D view is on screen.
 S8  (9b, T5) 03 Results: a chain is ONE entry with STAGE tabs - the
     window's handlers group a live chain; stage labels as before; the
     tabs; `current()` is the stage's own entry; the Field view draws the
     same image as a plain entry of the same Result; every text export
     and the report equal a plain entry's (`describe_dir`); two chains of
     one model; a plain result hides the slot; Remove takes the chain.

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


# ── S7 (9b) ──────────────────────────────────────────────────────────────
class FakeClock:
    """A settable monotonic clock for RunClock.now."""

    def __init__(self, t=0.0):
        self.t = float(t)

    def __call__(self):
        return self.t


def fake_1d():
    """A small 1D result (test_ui_results.fake_1d's shape)."""
    import numpy as np
    from blastlab.core.constants import P_AIR
    from blastlab.solvers.hooks import Result
    r = np.linspace(0.01, 2.0, 60)
    snap = dict(r=r, p=P_AIR + 200e3 * np.exp(-r), rho=np.full_like(r, 1.2),
                u=np.zeros_like(r))
    return Result({'t = 0.100 ms (final)': snap},
                  dict(times=np.linspace(0, 2e-3, 30), radii=[0.5, 1.0],
                       pressures=[P_AIR + 100e3 * np.ones(30),
                                  P_AIR + 50e3 * np.ones(30)]),
                  dict(eos='JWL', charge_kg=1.0, radius_m=2.0,
                       final_profile=np.column_stack(
                           [r, snap['p'], snap['rho'], snap['u']])),
                  'end time reached', False)


def fakes():
    """{dim: a small Result} for stages 1, 2, 3."""
    from test_gui_results_fields import fake_2d, fake_3d
    return {1: fake_1d(), 2: fake_2d(), 3: fake_3d()}


def stopped(res):
    from blastlab.solvers.hooks import Result
    return Result(res.snapshots, res.gauges, dict(res.meta),
                  'stopped by the user', True)


INFO1D = dict(dim=1, radius_m=2.0, gauges=[])


def s7_strip():
    from PySide6.QtCore import QPoint, QRect
    from blastlab.solvers.hooks import Progress
    from blastlab.ui import dialogs
    from blastlab.ui.app import MainWindow
    from blastlab.ui.chain_strip import H_ONE, H_TWO, ChainStrip
    from blastlab.ui.theme import GAP
    from test_ui_parity import clipped
    print('\nS7: the 02 Run chain strip (9b T4)')
    real_notify = dialogs.notify_desktop
    notes = []
    dialogs.notify_desktop = lambda *a, **k: notes.append(a)
    win = MainWindow()
    fake = FakeClock()
    win._run_clock.now = fake
    rp = win.run_panel
    res = fakes()

    def prog(frac):
        return Progress(step=1, t=1e-4, dt=1e-7, p_max=2e5, frac=frac)

    def start(dims, name='M'):
        win.ctrl._stage_dims = list(dims)
        win.ctrl._run_name = name
        fake.t = 0.0
        win.on_running(True)
        pump(30)
        return rp.chain_strip()

    try:
        win.show()
        win._show('run')
        for size in ((1600, 1000), (1100, 720)):
            tag = f'{size[0]} x {size[1]}'
            win.resize(*size)
            pump(150)
            strip = start([1, 2, 3])
            heights = [strip.height() if strip is not None else -1]
            check(f'{tag}: a 3-stage chain puts a ChainStrip in the slot',
                  isinstance(strip, ChainStrip)
                  and rp.chain_slot.isVisibleTo(rp)
                  and strip.texts()[:3] == ['01 1D waiting', '02 2D waiting',
                                            '03 3D waiting'],
                  str(strip.texts() if strip else None))
            check(f'{tag}: the eyebrow reads CHAIN · M',
                  strip.eyebrow.full_text() == 'CHAIN · M',
                  strip.eyebrow.full_text())
            win.on_run_started(INFO1D)
            pump(20)
            heights.append(strip.height())
            check(f'{tag}: stage 1 starts: 01 1D 0 %, 02 2D waiting, '
                  '03 3D waiting',
                  strip.texts() == ['01 1D 0 %', '02 2D waiting',
                                    '03 3D waiting', 'Stage 1 of 3 · the 2D '
                                    'stage starts from handoff_1d_to_2d.txt'],
                  str(strip.texts()))
            fake.t = 9.0
            win.on_result(0, 1, 'M - 1D', res[1])
            win.on_run_started(INFO1D)
            fake.t = 20.0
            win.on_progress(prog(0.78))
            pump(20)
            heights.append(strip.height())
            check(f'{tag}: stage 1 done at a fake 9 s, stage 2 at 78 %',
                  strip.texts() == ['01 1D ✓ 9 s', '02 2D 78 %',
                                    '03 3D waiting', 'Stage 2 of 3 · the 3D '
                                    'stage starts from handoff_2d_to_3d.npz'],
                  str(strip.texts()))
            check(f'{tag}: the title reads Chain 2/3 · 78 % · (F6)',
                  win.windowTitle().startswith('Chain 2/3 · 78 % · '),
                  win.windowTitle())
            check(f'{tag}: the arrow after a done stage is lit, the next not',
                  strip.arrows[0].lit() and not strip.arrows[1].lit())
            if size == (1100, 720):
                cut = clipped(win)
                check('1100 x 720: nothing clipped with the strip shown',
                      not cut, str(cut[:3]))
                boxes = [QRect(p.mapTo(strip, QPoint(0, 0)), p.size())
                         for p in strip.pills]
                pills_in = all(strip.rect().contains(b) for b in boxes) \
                    and not any(p.value.elided() for p in strip.pills)
                check('1100 x 720: every pill is whole, inside the strip',
                      pills_in, f'{boxes} strip {strip.size()}')
                cap = strip.caption
                check('1100 x 720: the caption fits or elides with its whole '
                      'text as the tooltip',
                      not cap.elided() or cap.toolTip() == cap.full_text(),
                      f'{cap.text()!r} tip {cap.toolTip()!r}')
                check(f'1100 x 720: the strip is in two rows '
                      f'({rp.column_widths()[1]} px centre)',
                      strip.two_rows() and strip.height() == H_TWO,
                      f'{strip.two_rows()} {strip.height()}')
            else:
                check('1600 x 1000: one row, 50 px',
                      not strip.two_rows() and strip.height() == H_ONE,
                      f'{strip.two_rows()} {strip.height()}')
            fake.t = 30.0
            win.on_result(1, 2, 'M - 2D', res[2])
            win.on_run_started(INFO1D)
            pump(20)
            heights.append(strip.height())
            check(f'{tag}: the last stage running says so',
                  strip.texts()[2:] == ['03 3D 0 %',
                                        'Stage 3 of 3 · the last stage'],
                  str(strip.texts()))
            fake.t = 40.0
            win.on_result(2, 3, 'M - 3D', res[3])
            win.on_running(False)
            win.on_finished(False, False)
            pump(20)
            heights.append(strip.height())
            check(f'{tag}: after the end three ✓ pills and Chain done in …',
                  strip.texts() == ['01 1D ✓ 9 s', '02 2D ✓ 21 s',
                                    '03 3D ✓ 10 s', 'Chain done in 40 s'],
                  str(strip.texts()))
            check(f'{tag}: the strip stays after the end, beside the banner',
                  rp.chain_strip() is strip and rp.chain_slot.isVisibleTo(rp))
            check(f'{tag}: its height never changed on a stage change',
                  len(set(heights)) == 1, str(heights))

        # a stop in stage 2 (the stage lands a stopped result)
        win.resize(1600, 1000)
        pump(100)
        strip = start([1, 2, 3])
        win.on_run_started(INFO1D)
        fake.t = 5.0
        win.on_result(0, 1, 'M - 1D', res[1])
        win.on_run_started(INFO1D)
        fake.t = 8.0
        win.on_result(1, 2, 'M - 2D (stopped)', stopped(res[2]))
        win.on_running(False)
        win.on_finished(True, False)
        pump(20)
        check('a stop in stage 2: 02 2D stopped, 03 3D not run, the caption',
              strip.texts() == ['01 1D ✓ 5 s', '02 2D stopped',
                                '03 3D not run',
                                'Chain stopped at stage 2 of 3'],
              str(strip.texts()))
        check('a fresh strip per chain (the last one replaced)',
              rp.chain_strip() is strip)
        # an error in stage 2 (no result for it)
        strip = start([1, 2, 3])
        win.on_run_started(INFO1D)
        win.on_result(0, 1, 'M - 1D', res[1])
        win.on_run_started(INFO1D)
        win.on_running(False)
        win.on_finished(False, True)
        pump(20)
        check('an error in stage 2: 02 2D failed, 03 3D not run, the caption',
              strip.texts()[1:] == ['02 2D failed', '03 3D not run',
                                    'Chain failed at stage 2 of 3'],
              str(strip.texts()))
        # the title's whole-percent dedupe must not hold a pill at 0 %: a
        # fast stage 2 whose first percent equals stage 1's last (the 9b
        # e2e saw `02 2D 0 %` through a whole stage)
        strip = start([1, 2])
        win.on_run_started(INFO1D)
        win.on_progress(prog(1.0))
        win.on_result(0, 1, 'M - 1D', res[1])
        win.on_run_started(INFO1D)
        win.on_progress(prog(1.0))
        pump(20)
        check('stage 2 at the percent stage 1 ended on still shows it',
              strip.texts()[1] == '02 2D 100 %', str(strip.texts()))
        win.on_running(False)
        win.on_finished(False, False)
        # a single run: the slot hidden at 0 px (R7)
        start([2])
        pump(30)
        check('a single run empties the slot, hidden at 0 px (R7 holds)',
              rp.chain_strip() is None and rp.chain_slot.isHidden()
              and rp.chain_slot.height() == 0, str(rp.chain_slot.height()))
        win.on_running(False)

        # the viewer is shrunk ahead only with the 3D view on screen (D93)
        host = rp.view3d
        calls = []
        real = host.shrink_ahead
        host.shrink_ahead = calls.append
        try:
            rp.show_3d_tab()
            pump(30)
            s = ChainStrip()
            s.set_chain('M', [1, 2])
            s.arrange(rp.column_widths()[1])
            rp.set_chain_strip(s)
            pump(30)
            check('3D view on screen: set_chain_strip calls shrink_ahead once '
                  "with the strip's height + GAP",
                  calls == [s.height_now() + GAP]
                  and rp.chain_slot.height() == s.height_now(),
                  f'{calls} slot {rp.chain_slot.height()}')
            rp.set_chain_strip(s)
            check('the same strip again (slot already shown): no call',
                  len(calls) == 1, str(calls))
            rp.set_chain_strip(None)
            rp.show_slice_tab()
            pump(30)
            calls.clear()
            rp.set_chain_strip(s)
            check('the live slice on screen: no call', calls == [],
                  str(calls))
            rp.set_chain_strip(None)
        finally:
            host.shrink_ahead = real
        check('no desktop notification escaped the patch',
              all(isinstance(n, tuple) for n in notes))
    finally:
        dialogs.notify_desktop = real_notify
        win.ctrl._stage_dims = []
        win.close()
        pump(100)


# ── S8 (9b) ──────────────────────────────────────────────────────────────
def with_manifest(res, folder, created, finished):
    """`res` pointing at a stage folder whose manifest holds the two
    stamps (results_method.records reads it)."""
    import json
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, 'manifest.json'), 'w',
              encoding='utf-8') as f:
        json.dump({'solver': 'native', 'created': created,
                   'finished': finished}, f)
    res.meta['model_dir'] = folder
    return res


def field_array(p):
    """What the Field view's map shows: (title, the image array)."""
    import numpy as np
    img = p.fields.image
    return (p.fields.title(),
            None if img is None else np.array(img.img.image, copy=True))


def same_image(a, b):
    import numpy as np
    return (a[0] == b[0] and a[1] is not None and b[1] is not None
            and a[1].shape == b[1].shape and np.array_equal(a[1], b[1]))


def export_files(p, kind):
    """`p.export(kind)` of its current entry, unthreaded, into a temp
    folder (test_char_exports.qt_export's dialogs); the files described."""
    import test_char_exports as ce
    from blastlab.ui import dialogs
    out = tempfile.mkdtemp(prefix='blastlab_s8_exp_', dir=TMP)
    real = dialogs.save_file, dialogs.pick_dir

    def save_file(title, filters='All files (*.*)', parent=None, start='',
                  default_suffix=None):
        return os.path.join(out, os.path.basename(start) or 'x')

    dialogs.save_file = save_file
    dialogs.pick_dir = lambda *a, **k: out
    try:
        with ce.Opened():
            ret = p.export(kind, threaded=False)
        return bool(ret), ce.describe_dir(out)
    finally:
        dialogs.save_file, dialogs.pick_dir = real


def s8_results():
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from blastlab.ui import dialogs
    from blastlab.ui.app import MainWindow
    from blastlab.ui.results_panel import ChainEntry, ResultsPanel
    print('\nS8: 03 Results - a chain is one entry with STAGE tabs (9b T5)')
    real_notify = dialogs.notify_desktop
    dialogs.notify_desktop = lambda *a, **k: None
    win = MainWindow()
    fake = FakeClock()
    win._run_clock.now = fake
    rs = win.results
    home = os.path.join(TMP, 's8', 'M')

    def chain_run(res, stamps):
        win.ctrl._stage_dims = [1, 2, 3]
        win.ctrl._run_name = 'M'
        fake.t = 0.0
        win.on_running(True)
        for k, d in enumerate((1, 2, 3)):
            win.on_run_started(INFO1D)
            fake.t += 5.0
            with_manifest(res[d], os.path.join(home + stamps['tag'],
                                                f'{d}d'),
                          *stamps[d])
            win.on_result(k, d, f'M - {d}D', res[d])
            pump(20)
            if k == 0:
                yield
        win.on_running(False)
        win.on_finished(False, False)
        pump(30)

    try:
        win.resize(1600, 1000)
        win.show()
        win._show('results')
        pump(100)
        res = fakes()
        stamps = {'tag': '', 1: ('2026-09-29T10:00:00', '2026-09-29T10:00:09'),
                  2: ('2026-09-29T10:00:10', '2026-09-29T10:20:00'),
                  3: ('2026-09-29T10:20:01', '2026-09-29T10:41:00')}
        run = chain_run(res, stamps)
        next(run)                                   # stage 1 landed
        row = rs.sel.row(0)
        check('mid-run: one entry, the caption says 1 of 3 stages',
              len(rs.entries()) == 1 and row.caption.full_text()
              == '1D → 2D → 3D · 1 of 3 stages · 9 s',
              row.caption.full_text())
        for _ in run:
            pass
        ents = rs.entries()
        ch = ents[0] if ents else None
        check('one entry, kind chain, labelled after the model',
              len(ents) == 1 and isinstance(ch, ChainEntry)
              and ch.kind == 'chain' and ch.label == 'M',
              str([(e.label, e.kind) for e in ents]))
        check('its stages carry the per-stage labels of before',
              [s.label for s in ch.stages] == ['M - 1D', 'M - 2D', 'M - 3D'],
              str([s.label for s in ch.stages]))
        check('win._results stays per stage (C11 names)',
              [lbl for lbl, _d, _r in win._results]
              == ['M - 1D', 'M - 2D', 'M - 3D'],
              str([lbl for lbl, _d, _r in win._results]))
        tabs = rs.stage_tabs
        check('the tabs read 1D | 2D | 3D with 3D selected, in the slot',
              tabs.texts() == ['1D', '2D', '3D'] and tabs.selected() == 3
              and rs.stage_strip() is tabs and tabs.isVisibleTo(rs)
              and rs.stage_slot.height() == 38,
              f'{tabs.texts()} {tabs.selected()} {rs.stage_slot.height()}')
        check('entries()[0].dim == 3 and .result is the 3D stage\'s',
              ch.dim == 3 and ch.result is res[3] and rs.stage() == 3)
        row = rs.sel.row(0)                 # the list is rebuilt per stage
        check('the row: the chain badge, latest, and the caption',
              not row.chain.isHidden() and not row.latest.isHidden()
              and row.caption.full_text()
              == '1D → 2D → 3D · 3 stages · 41 min 0 s',
              row.caption.full_text())
        check('the tabs sit above the view tabs',
              rs.stage_slot.geometry().bottom() < rs._seg_frame.y())

        rs.select_stage(2)
        pump(30)
        check('select_stage(2): current() is M - 2D, the tab follows',
              rs.current().label == 'M - 2D' and tabs.selected() == 2
              and ch.dim == 2, rs.current().label)
        chain_img = field_array(rs)
        plain = ResultsPanel()
        plain.resize(rs.size())
        plain.add_result('M - 2D', 2, res[2])
        pump(30)
        check('its Field image equals a plain entry\'s of the same Result',
              same_image(chain_img, field_array(plain)),
              f'{chain_img[0]!r}')
        plain.deleteLater()
        QTest.mouseClick(tabs.button(1), Qt.LeftButton)
        pump(30)
        check('a tab click selects the stage (1D), views refreshed',
              rs.current().label == 'M - 1D' and rs.stage() == 1
              and rs.fields.page() in ('image', 'figure'),
              f'{rs.current().label} {rs.fields.page()}')

        # a second chain of the same model, its 2D field its own
        res2 = fakes()
        # the final snapshot (the one shown) holds other numbers
        snap = list(res2[2].snapshots.values())[-1]
        snap['p'] = snap['p'] + 2e3
        stamps2 = dict(stamps, tag='_2')
        shows = []
        real_set = rs.set_stage_strip
        rs.set_stage_strip = lambda w=None: (shows.append(w),
                                             real_set(w))[1]
        try:
            for _ in chain_run(res2, stamps2):
                pass
            ents = rs.entries()
            check('two chains of one model: M, M #2; stages M - 2D #2',
                  [e.label for e in ents] == ['M', 'M #2']
                  and [s.label for s in ents[1].stages]
                  == ['M - 1D #2', 'M - 2D #2', 'M - 3D #2'],
                  str([(e.label, [s.label for s in e.stages])
                       for e in ents]))
            rs.select_stage(2)
            pump(30)
            second = field_array(rs)
            rs.sel.setCurrentIndex(0)
            pump(30)
            rs.select_stage(2)
            pump(30)
            first = field_array(rs)
            check('the second chain\'s 2D Field is its own data',
                  second[1] is not None and first[1] is not None
                  and not same_image(first, second))
            check('switching between two chains never re-shows the slot',
                  shows == [], str(shows))
        finally:
            rs.set_stage_strip = real_set

        rs.add_result('plain', 2, fakes()[2])
        pump(30)
        check('a plain result selected after a chain: stage_slot hidden '
              'at 0 px', rs.stage_slot.isHidden()
              and rs.stage_slot.height() == 0 and rs.stage() is None,
              str(rs.stage_slot.height()))
        logs = []
        rs._log = logs.append
        rs.sel.setCurrentIndex(1)
        pump(20)
        n0 = len(rs.entries())
        rs.remove_current()
        pump(20)
        check('Remove of a chain removes its one row',
              len(rs.entries()) == n0 - 1 and rs.sel.count() == n0 - 1
              and logs[-1:] == ['Removed result: M #2'],
              f'{n0} -> {len(rs.entries())} {logs[-1:]}')
        check('a result fed by hand outside a run stays a plain entry',
              rs.entries()[-1].kind == 'run')
    finally:
        dialogs.notify_desktop = real_notify
        win.ctrl._stage_dims = []
        win.close()
        pump(100)
    s8_exports()


def s8_exports():
    """Every text export and the report of a chain's stage equal a plain
    entry's of the same Result (plan T5: export bytes cannot change)."""
    import test_char_exports as ce
    from blastlab.ui.results_panel import ResultsPanel
    r1, r2 = ce.result('1d'), ce.result('2d')
    pc, pp = ResultsPanel(), ResultsPanel()
    for p in (pc, pp):
        p.resize(1000, 700)
    ch = pc.start_chain('M', [1, 2])
    pc.add_stage(ch, 'M - 1D', 1, r1)
    pc.add_stage(ch, 'M - 2D', 2, r2)
    pp.add_result('M - 2D', 2, r2)
    pump(30)
    check('S8 exports: the chain\'s current() is its 2D stage',
          pc.current().label == 'M - 2D' and pc.current().result is r2)
    for kind in ('summary', 'tsv', 'fieldcsv', 'profile', 'report'):
        got_c = export_files(pc, kind)
        got_p = export_files(pp, kind)
        check(f'{kind}: the chain stage writes what a plain entry writes',
              got_c[0] and got_c == got_p and got_c[1],
              f'{sorted(got_c[1])} vs {sorted(got_p[1])}')
    pc.deleteLater()
    pp.deleteLater()
    pump(20)


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
        s7_strip()
        s8_results()
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
