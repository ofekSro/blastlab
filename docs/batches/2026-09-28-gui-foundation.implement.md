# Implementer report — batch 2026-09-28-gui-foundation (GUI-1, GUI-2, GUI-4)

Branch `gui-redesign`, base `0605522`. All three tasks DONE, one commit each; the app
runs and is byte-identical in its numbers at every commit. `test_regression.py` green
before the batch and after each task.

## GUI-1 · Design tokens and fonts · DONE · `f553014`

- Palettes in `blastlab/ui/theme.py` rewritten to plan §2.1/§2.2: every old key
  re-pointed, 21 new keys, `tile == card2`. Header docstring corrected (the Qt palette
  is the redesign's own; Tk keeps `gui/theme.py`, untouched).
- Fonts bundled in `blastlab/ui/fonts/`, registered in `apply()` behind a run-once
  guard from the package directory; `font()` gains `display`, `body`, `mono` with
  `QFont.setFamilies` fallbacks (Segoe UI / Consolas).
  - IBM Plex Sans 400/500/600: statics from the IBM/plex release `@ibm/plex-sans@1.1.0`.
  - IBM Plex Mono 400/500/600: statics from google/fonts.
  - Space Grotesk: the variable `SpaceGrotesk[wght].ttf` from google/fonts (the
    upstream static set has no SemiBold). The test asserts 600/700 render heavier
    (ink 400/600/700 = 2935/3591/4342 px). One `OFL.txt` per family.
- White on orange swept out of QSS, `QPalette.HighlightedText`,
  `widgets.button()` / `set_button_kind()` and two hard-coded play-button tints
  (→ `on_accent`).
- `error` / `danger_hover`: dark `#ff5c7a` / `#ff7490`; light `#cb3067` / `#b52a5b`.
- Light values of §2.2 that failed the plan's own 4.5:1 gate, darkened minimally:
  faint `#7a7e85→#696c72`, accent_text `#c7430f→#c5420f`, gauge `#0e7fa6→#0d7599`,
  ok `#2f9e44→#257d36`, warn `#b07d00→#926800`, danger `#d6336c→#cb3067`. Light keys
  §2.2 omits, derived: card2 `#f1efeb`, accent_hover `#e85d20`, num_dim `#9b958c`,
  on_accent `#1a0d06`, accent_border `#e0b394`, gauge_bg `#e3f1f7`, ok_bg `#e7f3ea`,
  ok_border `#c4dccb`, stop_bg `#fbe4e9`, stop_border `#e3aab8`, stop_text `#b02a48`,
  title_bar `#dedad3`.
- Contrast: dark worst = faint on tile 5.37; light worst = warn on bg 4.50. Danger
  buttons: white on dark danger 2.97, so dark mode uses `on_accent` (6.40); light keeps
  white (5.05). `on_accent` on `accent` = 6.66 in both modes.
- Files: `ui/theme.py`, `ui/widgets.py`, `ui/results_anim.py`, `ui/view3d_host.py`,
  `ui/fonts/**` (10 files), `tests/test_ui_theme.py` (new),
  `docs/qa/2026-09-28-gui-foundation/gui1-{dark,light}.png`.
- Test: `python test_ui_theme.py` → `THEME: PASS`.

## GUI-2 · Logo and app icon · DONE · `3dda85e`

- `theme.logo_pixmap(size, mode)` draws the mark directly from the Logo_Final
  rectangles at 64 / 32 / 16 (16 pixel-crisp, antialiasing off); never scaled below
  24 px. `theme.app_icon()` = the mark on a `#1f1c1b` rounded square, one QIcon with
  16/24/32/48/64/128/256.
- `app.py`: the gif logo removed; mark (30 px) + BLASTLAB wordmark (`LAB` in
  `accent_text`, re-tinted on theme switch); icon on window and QApplication;
  `SetCurrentProcessExplicitAppUserModelID('blastlab')` guarded (win32 + try/except).
- Files: `ui/theme.py`, `ui/app.py`, `tests/test_ui_logo.py` (new),
  `docs/qa/2026-09-28-gui-foundation/gui2-window.png`, `gui2-screen-taskbar.png`.
- Test: `python test_ui_logo.py` → `LOGO: PASS` (pixel colours at known coordinates
  at 64/32/16, icon sizes, window icon, wordmark present, no `logo.gif` under
  `blastlab/ui/`, root `logo.gif` still used by `gui/app.py`). The real-platform grab
  shows the drawn icon in the title bar and on the taskbar.

## GUI-4 · Shared components · DONE · `2f64601`

- New `blastlab/ui/components.py`: `ToggleSwitch` (QCheckBox subclass, painted),
  `StatTile`, `TreeRow`, `DockTabs`, `Banner`, `HandoffCard`. `theme.qss()`: the
  §2.5 Segmented restyle and object-name rules for the components; components re-tint
  on `theme.signals.changed`.
- Also here, a measured GUI-1/GUI-2 defect: the app-wide `QWidget { font-family;
  font-size }` QSS rule overrides programmatic QFont family/size. `QLabel#h1/#h2`
  now carry Space Grotesk in QSS; the wordmark and the components set family/size
  through per-widget style sheets.
- Files: `ui/components.py` (new), `ui/theme.py`, `ui/app.py`,
  `tests/test_ui_components.py` (new), `docs/qa/2026-09-28-gui-foundation/gui4-{dark,light}.png`.
- Test: `python test_ui_components.py` → `COMPONENTS: PASS`.

## Tests run after every task (tails)

`test_ui_parity` PASS (42) · `test_ui_setup_form` passed · `test_ui_results` PASS (129)
· `test_ui_chain` PASS (65) · `test_ui_three_surfaces` PASS (35) ·
`test_ui_output_card` PASS · `test_ui_char_hd13_run` PASS · `test_ui_run_panel` passed ·
`test_ui_preview` passed · `test_ui_run_browser` PASS (48) · `test_ui_no_vtk_in_main`
PASS · `test_ui_no_mpl_pyplot` PASS (18) · `test_ui_crashlog` PASS · `test_ui_drain`
passed · `test_ui_theme` / `test_ui_logo` / `test_ui_components` PASS ·
`test_regression` PASS · `test_foam_writer` PASS · `test_case_validate` PASS.
`python -m blastlab` (throwaway settings) stayed up until killed. §8.2 dry run before
the session: `auto_cleanup` False, plan empty.

Committed test assertions changed: **none**.

## Suspected issues (not changed)

1. The app-wide QSS font rule overrides every programmatic QFont family/size in the
   whole Qt UI; fixed only where this batch needed it. Candidate for a sweep.
2. `test_ui_no_mpl_pyplot` teardown race (hardware-probe thread posts after the window
   is deleted) prints a RuntimeError after PASS; exit 0; pre-existing.
3. `_wsl_hint` / `_status` labels bake `theme.cur()` colours into style sheets, so they
   keep the old mode's colour after an Appearance toggle; pre-existing.

## Open questions (moved to docs/gui-redesign-decisions.md)

Light-value adjustments, variable Space Grotesk, light toggle/wake values, commit
attribution line.
