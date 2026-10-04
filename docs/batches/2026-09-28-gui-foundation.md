# Batch 2026-09-28 · gui-foundation — GUI-1, GUI-2, GUI-4

**Goal:** land the design system the whole GUI redesign builds on — the warm-black
token palette and bundled fonts (GUI-1), the QPainter-drawn mark and app icon
(GUI-2), and the five shared components (GUI-4) — with the app fully runnable and
byte-identical in its numbers after every task.

**Branch:** `gui-redesign`, base `0605522`. Specification:
[`docs/gui-redesign-plan.md`](../gui-redesign-plan.md) §2, §3, §2.5, §9, §10, §11;
boards `docs/design/gui-redesign/boards/Logo_Final.dc.html` and
`BC_Combined.dc.html` (HTML with inline styles — **read the source**, they do not
open offline). CLAUDE.md is binding (§8 traps, §9 do-not-touch).

## Why this batch, and why GUI-3 is not in it

The plan's own order is GUI-1 → GUI-2 → GUI-3 → GUI-4, but GUI-3 (window frame)
is L — a day or more on its own: it deletes the sidebar, re-routes navigation for
every panel, moves the solver switch and file actions, adds shortcuts, and
requires real-platform screenshots at two sizes plus updates to
`test_ui_three_surfaces.py` / `test_ui_parity.py` navigation and (eventually) the
QA harness helpers. GUI-4 depends only on GUI-1, and GUI-3's own top bar will
*consume* GUI-4-style pieces. So the completable-in-one-run batch is the
foundation triad **GUI-1 (M) + GUI-2 (S) + GUI-4 (M) ≈ one day**, and GUI-3
becomes the whole next batch with all of its prerequisites in place. Every task
here leaves the current layout working: GUI-1 re-skins it, GUI-2 swaps the icon
and logo, GUI-4 adds components nothing consumes yet (plus their tests).

## Rules for the implementer (binding)

1. **Numbers unchanged.** `cd blastlab/tests && python test_regression.py` green
   byte-for-byte before starting and after each task (plan §9).
2. **Six paths in the working tree belong to other work — never stage or modify:**
   `docs/references/INDEX.md`, `docs/references/ViperTheoryManual_Client.pdf`,
   `docs/references/ViperTheoryManual_Client.txt`,
   `docs/references/viper_vtk_sample/`, `docs/qa/2026-09-27-out-3/`,
   `docs/qa/2026-09-27-viewer-polish/`. Stage only your own files, by name.
3. **`blastlab/gui/` (Tk), `logo.gif` and `gui/theme.py` are untouched**
   (CLAUDE.md §9; plan "Out of scope"). Never describe Tk as deprecated.
4. **Committed tests** (plan §9, owner 2026-09-28): a `test_ui_*.py` assertion
   pinning layout the owner replaced may be updated; behaviour/number assertions
   may not be weakened; list every changed assertion in the task report.
   `test_gui_*` (Tk) are not touched — and this batch touches no shared neutral
   module, so they need not be run.
5. **Every new test that builds a `MainWindow`** starts from
   `blastlab.ui.testing.private_settings()` / the `BLASTLAB_SETTINGS` tempfile
   pattern the existing UI tests use (CLAUDE.md §8.2 — a bare GUI build can
   sweep the run corpus). Offscreen: `QT_QPA_PLATFORM=offscreen`,
   `MPLBACKEND=Agg`, as in `test_ui_three_surfaces.py`.
6. **No PowerShell string round trips** on any file (CLAUDE.md §8.1) —
   `theme.py` is full of `──` box characters and will mojibake. Read/Edit/Write
   only.
7. Commits: `ui: <what changed> (GUI-n)`, one per task at least.

**Reference documents:** `docs/references/INDEX.md` was read. None of the four
registered documents (blastfoam-guide, ufc-3-340-02, llnl-explosives-handbook,
viper-theory) covers GUI styling; nothing in this batch touches a standard's
equation, a solver keyword or a case file. The binding sources for this batch are
`docs/gui-redesign-plan.md` §2–§3, §2.5 and the two boards named above.

---

## Task 1 · GUI-1 — Design tokens and fonts · size M

**TODO.md text (verbatim):** *"`GUI-1` | **Design tokens and fonts** — warm-black
palette + light, orange accent, cyan gauges; Space Grotesk / IBM Plex Sans / IBM
Plex Mono bundled (OFL). Plan §2 | M | 1"*

**Files:**
- `blastlab/ui/theme.py` — the whole task lives here plus the fonts dir.
  - `DARK` (lines 15–22): re-point every existing key (`bg card card2 border
    entry accent accent_hover text muted view danger danger_hover error warn ok
    seg`) to plan §2.1 values; **add** the new keys: `panel tile hover border2
    entry_border text2 faint num_dim on_accent accent_text accent_soft accent_bg
    accent_border gauge gauge_bg ok_bg ok_border stop_bg stop_border stop_text
    title_bar` (`tile` = same value as `card2`, both keys kept). §2.1 gives no
    value for `error` / `danger_hover`: derive from the `danger` family
    (`error` may equal `danger` `#ff5c7a`; a hover a step lighter) and record the
    choice in the task report.
  - `LIGHT` (lines 23–30): plan §2.2 values; keys §2.2 omits (`accent_hover`,
    `danger_hover`, `error`, `num_dim`, `on_accent`, `accent_soft`,
    `accent_border`, `gauge_bg`, `ok_bg`, `ok_border`, `stop_*`, `title_bar`,
    `panel`/`tile`/`view` are given) are **derived with the same roles** and must
    pass the contrast gate below. `view` in LIGHT is `#ecebe7` per §2.2 (today
    light mode reuses the dark view — keep whichever the QSS `QLabel#view` rule
    needs consistent; the boards' light view is light).
  - `FONT` / `MONO` (lines 33–34) → `'IBM Plex Sans'` / `'IBM Plex Mono'` with
    fallbacks; new `DISPLAY = 'Space Grotesk'`. Use `QFont.setFamilies([primary,
    'Segoe UI'])` / `(['IBM Plex Mono', 'Consolas'])` so a missing file falls
    back without error (plan §2.3 — never crash).
  - `font()` (line 69): existing kinds (`h1 h2 body small small_bold chip mono`)
    keep working — `h1`/`h2` move to the display family; **add kinds `display`,
    `body` (explicit), `mono`** per acceptance (plan §10 GUI-1).
  - Font loading: bundle TTFs under **new** `blastlab/ui/fonts/` (dir does not
    exist yet) with each family's `OFL.txt`; register with
    `QFontDatabase.addApplicationFont` inside `apply()` behind a run-once guard,
    so every entry path (app `main()` line ~936, tests, harness) gets them.
    Load from the package directory, never `%WINDIR%\Fonts` (plan §11 — Store
    Python sandbox). Only the weights used: Space Grotesk 600/700, IBM Plex
    Sans 400/500/600, IBM Plex Mono 400/500/600. **Prefer static per-weight
    TTFs** (IBM Plex GitHub releases / google-fonts static folders): google/fonts
    now ships variable TTFs for some of these, and weight selection from a
    variable font is not reliable on every Qt 6 minor. If only variable files
    are practical, prove SemiBold actually renders heavier than Regular in the
    test before accepting it.
  - `qss()` (line 117): re-point; and the token-level "never white on orange"
    sweep — `QPushButton#primary { color: white }` → `on_accent` (and its icon
    tint in `widgets.button()` line 42 / `set_button_kind()` line 64:
    `'white'` → `theme.cur('on_accent')` for `primary`), `QToolButton#seg:checked
    { color: white }` (restyle itself is GUI-4, but the white must go),
    table/menu `selection-color: white` and `QPalette.HighlightedText '#ffffff'`
    (line 101) → `on_accent`, since Highlight is now `#ff6a2b` and white fails
    4.5:1 on it. Leave `danger` buttons' white unless the contrast script flags
    it (record either way).
  - Header docstring (lines 1–3): "the palette shared with the Tk app /
    identical to gui/theme.py" is no longer true — correct it to say the Qt
    palette is the redesign's own and Tk keeps `gui/theme.py`
    (do **not** touch `gui/theme.py`).
- `blastlab/tests/test_ui_theme.py` — **new** fast offscreen test (this is the
  "script" of the acceptance criterion, made a permanent gate):
  contrast + keys + fonts, see acceptance.

**Acceptance (all commands from `blastlab/tests` unless said):**
1. `python -c "from blastlab.ui import theme; ks={'bg','card','card2','border','entry','accent','accent_hover','text','muted','view','danger','danger_hover','error','warn','ok','seg'}; assert ks<=set(theme.DARK) and ks<=set(theme.LIGHT); assert theme.DARK['bg']=='#0b0b0c' and theme.DARK['accent']=='#ff6a2b' and theme.DARK['gauge']=='#4cc9f0' and theme.DARK['tile']==theme.DARK['card2']"`
   passes (run from the repo root).
2. `python test_ui_theme.py` passes and **prints the contrast-ratio table**
   (WCAG relative luminance) for every text role on its background, both modes —
   at least: `text`/`text2`/`muted`/`faint` on `bg`, `panel`, `card`, `tile`;
   `accent_text` and `accent_soft` on `bg` and `card`; `on_accent` on `accent`;
   `stop_text` on `stop_bg`; `gauge` on `gauge_bg` and `bg`; `ok` on `ok_bg`;
   `warn` and `danger` on `bg`. All ≥ 4.5, display-size roles (≥ 24 px:
   stat-tile values, step titles) ≥ 3.0. The ratios go in the task report
   (plan §2.2: "check it with a script, not by eye").
3. Same test: after `ensure_qapp()` + `theme.apply(app,'dark')`,
   `QFontDatabase.families()` contains `Space Grotesk`, `IBM Plex Sans`,
   `IBM Plex Mono`; `theme.font('display')`, `font('body')`, `font('mono')`
   return QFonts with those families first; with the fonts dir temporarily
   pointed elsewhere (monkeypatch), `apply()` still succeeds and `font('display')`
   falls back to Segoe UI — no exception (plan §2.3).
4. Every palette value in both modes is a full 7-char `#rrggbb`
   (`test_ui_parity.py` P2 feeds them to pyqtgraph's `mkColor`).
5. `blastlab/ui/fonts/` contains only the used weights + one `OFL.txt` per
   family; the licence files are committed with the TTFs.
6. Fast gates green: `python test_regression.py` (byte-identical),
   `test_ui_parity.py`, `test_ui_setup_form.py`, `test_ui_results.py`,
   `test_ui_chain.py`, `test_ui_three_surfaces.py`, `test_ui_output_card.py`,
   `test_ui_char_hd13_run.py`, `test_ui_run_panel.py`, `test_ui_preview.py`,
   `test_ui_run_browser.py`, `test_ui_no_vtk_in_main.py`,
   `test_ui_no_mpl_pyplot.py`, `test_ui_crashlog.py`, `test_ui_drain.py`.
   (These read colours through `theme.cur/qcolor`, so they should adapt; any
   assertion that pinned an old colour/name falls under the §9 committed-tests
   rule — update, and list it.)
7. `python -m blastlab` opens, dark and light both usable (Appearance toggle),
   one screenshot each in the task report.

**Depends on:** nothing. **Everything else in the batch depends on it.**

## Task 2 · GUI-2 — Logo and app icon · size S

**TODO.md text (verbatim):** *"`GUI-2` | **Logo and app icon** — the stepped
front on an 8 × 8 grid, drawn with QPainter at 16/32/64; BLASTLAB wordmark;
window + taskbar icon. Plan §3 | S | 2"*

**Interpretation:** the wordmark goes where the ELSL `logo.gif` sits today — the
sidebar top (`ui/app.py` lines 191–196) — as mark (≈30 px) + "BLASTLAB" (Space
Grotesk Bold, caps, tracking +8 %, `LAB` in `accent_text`). GUI-3 will move it
into the top bar; this task only replaces the pixmap. Confirmed against
`Logo_Final.dc.html` (front `#ff6a2b` dark / `#e0501a` light, icon plate
`#1f1c1b`).

**Files:**
- `blastlab/ui/theme.py` — new functions next to the icon code (~line 239):
  `logo_pixmap(size, mode)` drawing the mark from the §3 rectangle lists
  (three hand-tuned sizes 64/32/16 — never scale below 24; wake at 35 %
  opacity; grid strokes per size; colours: front `#ff6a2b`/`#e0501a`, frame
  `#e7eaee`/`#1f2430`) and `app_icon()` — the 64 mark on a `#1f1c1b` rounded
  square (radius ≈ 20/88), one `QIcon` with 16/24/32/48/64/128/256 pixmaps.
  **Do not route the mark through `_glyph()`** — that pipeline tints
  single-colour glyphs white-then-recolour; the mark is multi-colour and is
  drawn directly. Mind `setDevicePixelRatio` if supersampling: the pixel test
  reads device pixels.
- `blastlab/ui/app.py` — lines 39–40/63–64: drop `_LOGO`/`logo.gif`, set
  `theme.app_icon()` on the window **and** the `QApplication` (in `main()`,
  ~line 936); lines 191–196: mark + wordmark labels instead of the scaled gif.
  Windows taskbar grouping: in `main()`, before the window shows,
  `ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('blastlab')`
  guarded by `sys.platform == 'win32'` + try/except (plan §3).
- `blastlab/tests/test_ui_theme.py` (extend) or new `test_ui_logo.py` — the
  pixel test.

**Acceptance:**
1. Offscreen pixel test: render `logo_pixmap(64,'dark')` to `QImage`; assert the
   colour at the centre of front cell (8,20) (i.e. ≈(10.5, 22.5) in the 64 box,
   scaled to the image) is `#ff6a2b`, at a wake cell (8,26) is orange at reduced
   alpha/blend, at an empty grid corner is transparent/background, and a frame
   pixel is `#e7eaee`; at 16, assert one step cell (e.g. inside rect (2,4,3,2))
   is `#ff6a2b` and the 16 render has **no** grid/wake pixels. A light-mode
   front pixel is `#e0501a`. (Plan §10 GUI-2: "a test compares a few pixel
   colours at known coordinates".)
2. `theme.app_icon().availableSizes()` includes 16/24/32/48/64/128/256, and a
   `MainWindow` built offscreen has `not windowIcon().isNull()`.
3. `rg -l "logo\.gif" blastlab/ui/` returns nothing; `logo.gif` still exists at
   the repo root; `git status` shows **no** change under `blastlab/gui/`
   (ELSL stays in Tk — plan §3 last line).
4. On the real platform (`QT_QPA_PLATFORM` unset): the window and the taskbar
   button show the new icon, not Python's — screenshot in the report.
5. Fast UI gates of Task 1 item 6 stay green (the sidebar changed: any
   `test_ui_*` assertion that pinned the gif label is layout-pinning →
   §9 rule, update and list).

**Depends on:** GUI-1 (fonts for the wordmark, `accent_text` token).

## Task 3 · GUI-4 — Shared components · size M

**TODO.md text (verbatim):** *"`GUI-4` | **Shared components** — toggle switch,
stat tile, tree row, dock tabs, banner. Plan §2.5 | M | 4"*

**Interpretation:** plan §2.5 offers `ui/widgets.py` **or** a new
`ui/components.py`; choose a new `blastlab/ui/components.py` so nothing that
imports `widgets` today can be disturbed. Nothing in the app consumes the new
components yet — GUI-3/5/6/7 will; this task delivers them working, styled and
tested. The §2.5 Segmented restyle and the Banner/Hand-off card are part of this
task.

**Files:**
- `blastlab/ui/components.py` — **new**:
  - `ToggleSwitch(QCheckBox)` — `paintEvent` draws a 42–46 × 24–26 track with a
    white knob; `accent` when checked, `#3a3a40` (dark) / a derived light value
    when off; hit area, focus, Space-toggling and accessibility stay the
    checkbox's own (plan §2.5: "keyboard and screen-reader behaviour of a
    checkbox" — subclass, don't reimplement).
  - `StatTile` — caps label 10.5 px letter-spaced (`QFont.setLetterSpacing`),
    value in Space Grotesk 21–26 px (`theme.font('display')`), caption line;
    optional thin bar (for memory); `variant='accent'` uses `accent_bg` (the Z
    tile). `set(value, caption=None, frac=None)` API.
  - `TreeRow` — number (Space Grotesk 12.5, `num_dim`, `accent_text` when
    selected) · title · mono caption underneath · right-side status mark
    (✓ `ok`, ! `warn`, ✗ `danger`); selected fill `accent_bg`; min height 44 px
    (§2.4); emits `clicked(str_id)`; `set_selected(bool)` repolishes.
  - `DockTabs` — tab strip whose active tab has a 2 px `accent` underline, over
    a `QStackedWidget`; `changed(str)` signal, `set(name)` silent (the
    `Segmented` API convention).
  - `Banner` — the finished-run banner (`ok`/`ok_bg`/`ok_border`, message +
    action button slot) — and `HandoffCard` (tinted `accent_bg`, border
    `accent_border`, title + mono file line), per §2.5.
- `blastlab/ui/theme.py` — `qss()`: Segmented restyle (§2.5):
  `QToolButton#seg:checked` → background `seg`, text `text`; unchecked text
  `muted`; radii per §2.4 (9–10 px segmented); any object-name rules the new
  components need (`#tile`, `#treerow`, `#banner`…) — or paint in `paintEvent`
  where QSS cannot (plan §11: no shadows/gradients/blur, no new dependency).
- `blastlab/tests/test_ui_components.py` — **new** offscreen suite, plain
  script like its siblings.

**Acceptance (plan §10 GUI-4: "each component has an offscreen test"):**
1. `python test_ui_components.py` green, covering at least:
   - ToggleSwitch: programmatic `setChecked` and a synthesized click both flip
     `isChecked()` and emit `toggled`; Space key toggles when focused; it is a
     `QCheckBox` (`isinstance`), so the accessibility contract holds.
   - StatTile: `set('368 k','cells')` shows both strings
     (`collect_text`-style); the value label's family is Space Grotesk; the
     accent variant picks `accent_bg`; the bar clamps to [0, 1].
   - TreeRow: click emits `clicked` with the row's id; `set_selected(True)`
     changes the painted/background state (assert the dynamic property +
     `repolish`, or a rendered-pixel check); the status mark switches ✓/!/✗.
   - DockTabs: `set()` is silent, a user click emits `changed` with the tab
     name and switches the stacked page; exactly one underline active.
   - Banner/HandoffCard: text set is text shown; the banner's action button
     fires its callback.
2. Segmented after restyle: `test_ui_setup_form.py`, `test_ui_run_panel.py`,
   `test_ui_results.py`, `test_ui_chain.py`, `test_ui_parity.py` green (the
   `Segmented` API — `changed` only on click, `set()` silent — is behaviour and
   must not move).
3. `test_ui_no_vtk_in_main.py` / `test_ui_no_mpl_pyplot.py` green
   (`components.py` imports neither).
4. `python test_regression.py` byte-identical; `python -m blastlab` still opens
   and every screen behaves as before (no consumer changed).

**Depends on:** GUI-1 (tokens, fonts). Independent of GUI-2.

---

## Risks

- **No numerical surface is touched** — no file under `core/`, `solvers/`,
  `output/`, `models/`, `services/` changes in this batch. The characterisation
  guard is `test_regression.py` byte-parity before/after each task, plus the
  full fast `test_ui_*` set; no new characterisation baseline is needed.
- **The white-on-accent sweep (GUI-1)** touches `QPalette.HighlightedText` and
  QSS `selection-color`, which affects every table/menu selection. The contrast
  test is the guard; eyeball dark and light once each.
- **Fonts are the only external input.** Downloading TTFs needs network access;
  google/fonts serves *variable* TTFs for some of these families, and weight
  selection from a variable font is Qt-version-sensitive. Mitigation: static
  per-weight files (IBM Plex GitHub release; Space Grotesk static instances),
  and the test asserts the families actually register. If the implementer's
  session has no network, this task blocks → ask the owner to drop the TTFs
  into `blastlab/ui/fonts/` (see "Needs clarification").
- **QSS coverage** — pills/underlines that QSS cannot draw are painted in
  `paintEvent` (plan §11); no new dependency, ever.
- **Mojibake (CLAUDE.md §8.1)** — `theme.py`, `widgets.py` and this file carry
  non-ASCII; every edit through Read/Edit/Write, none through PowerShell
  strings. Damage hunt after the batch: `rg 'ג€|ג”' blastlab/ui docs/batches`.
- **Test-triggered cleanup (CLAUDE.md §8.2)** — new tests that build a
  `MainWindow` (GUI-2 item 2) must set `BLASTLAB_SETTINGS` to a throwaway file
  first, like `test_ui_three_surfaces.py` does. Run the dry-run check from
  CLAUDE.md §8.2 before the session.
- **The embedded 3D viewer** does not move in this batch (no layout change
  around `view3d_host.py`), so no ctypes re-measurement is due yet — it becomes
  due at GUI-3/6/7 (plan §11).

## Needs clarification (owner)

1. **Font files, if offline:** if the implementing session cannot reach the
   google/fonts / IBM Plex repositories, please drop the TTFs (Space Grotesk
   600/700; IBM Plex Sans 400/500/600; IBM Plex Mono 400/500/600, each with its
   OFL.txt) into `blastlab/ui/fonts/` — or approve static files from another
   OFL mirror. Not blocking the batch start: GUI-1's fallback path is built and
   tested first either way.
2. **`error` / `danger_hover` values** are absent from plan §2.1/§2.2; the batch
   derives them from the `danger` family and records the hex in the task report
   — say if you want specific values.
3. No other ambiguity: every task in this batch is fully specified by plan
   §2/§2.5/§3 and the two boards.

## Remaining backlog (the GUI track, future batches, in the plan's order)

- **Batch next — GUI-3** (L): the window frame — top bar with workflow pills,
  solver chip, case menu, status bar, title progress, F5 / Shift+Esc; removes
  the sidebar; updates `test_ui_three_surfaces.py` / `test_ui_parity.py`
  navigation pins (§9 rule) and re-measures the 3D viewer placement on the real
  platform; screenshots at 1100 × 720 and 1600 × 1000.
- **GUI-5** (L): 01 Setup — model tree + per-node properties + live-number
  strip, Z rings, gauge table with Z (consumes GUI-4's TreeRow/StatTile/
  DockTabs; the riskiest task — split `FieldForm` placement, not parsing).
- **GUI-6** (L): 02 Run — progress strip + ETA, live-gauge list sorted by Z,
  Stop-after-30-s confirmation, finish banner + Windows notification.
- **GUI-7** (L): 03 Results — Field (= Fields + Animation) · Gauges · 3D,
  table with Z + Copy, impulse kPa·ms on screen only, grouped exports.
- **GUI-8** (S): chain 1D → 3D wiring in `ChainPanel.run()` + tests — could
  ride with GUI-6 or GUI-7 as it has no dependencies, or precede GUI-9.
- **GUI-9** (L): the Chain screen — routes, pipeline, stage editor, per-stage
  validation; chain strip in Run, one result with stage tabs in Results.
- **GUI-10** (M): QA pass — harness navigation on the new frame, all 63
  scenarios, light mode, 1100 × 720.

*(The non-GUI backlog — OUT residue, HD1, P0–P4 — is outside this planning
directive: the owner ordered the GUI track implemented batch after batch, in
order, before returning to it.)*
