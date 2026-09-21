> **Academic CFD — blast-wave gas dynamics, Technion.** This project computes a
> pressure field in air and the structural load it produces, for blast-resistant
> design and explosive-safety siting (UFC 3-340-02, Kingery-Bulmash).
> Energetic materials enter only as a published equation of state. Scope: [docs/SCOPE.md](../SCOPE.md)

# The PySide6 migration — 2026-09-17/18

The GUI moved from Tkinter to PySide6 in stages M0–M7. Since 2026-09-17,
`python -m blastlab` opens Qt; `--tk` opens the original.

---

## ⛔ The standing owner decision (2026-09-18)

**Qt is the main GUI; Tk stays forever as the way back.**

> **Verbatim, as the owner wrote it:**
> *"אל תמחק את הTK זה פשוט תהיה אפשרות לחזור אליה בעתיד אם נצטרך. מעתה
> והלאה הQT זה הMAIN GUI"*
>
> ("Do not delete the Tk — it will simply be an option to go back to in the
> future if we need it. From now on the Qt is the MAIN GUI.")

Two halves, both binding:

1. **Qt is primary.** `blastlab/ui/` is the product's GUI. Every new feature,
   every bug fix and every UI test goes there. There is no more "the migration" —
   the migration is over.
2. **`blastlab/gui/` and `customtkinter` stay in the tree with no removal date.**
   Not "for one release", not "until parity is proven", not "until the owner
   approves deletion" — but as a **permanent** way back behind `--tk`. **Do not
   delete it, and do not describe it as deprecated or scheduled for removal** in
   code, in the README, or in any error message, unless the owner explicitly asks.

**Why the wording matters this much:** an earlier phrasing — *"kept for one
release"* — would have made a later session **right** to remove it. The wording
is what deletes code.

**What follows operationally:** the `test_gui_*` suites and `_qa_gui_harness.py`
stay, and are run whenever a change touches `blastlab/gui/` or the shared neutral
modules (`core/`, `solvers/`, `output/`) — they are what keeps the way back
usable. A fallback nobody runs is not a fallback. The only incompatible changes
permitted there are ones that follow from a change in a shared module, in that
same commit.

*(This replaced an interim decision of 2026-09-17: "There are serious bugs. Do
not delete Tk until everything is fixed 100 %." That is why the Qt harness (M7)
was built — it is the tool that collected those bugs systematically, across 63
scenarios.)*

---

## Stage 0 — freeing the machine

Before any of it could start, three environmental problems:

- **WSL was down** with `CreateInstance/E_FAIL`, caused by
  `[wsl2] vmIdleTimeout=-1` in `.wslconfig`. That is an **invalid value** — the
  key is in milliseconds, and `-1` is documented only for
  `[general] instanceIdleTimeout`. It takes WSL down completely, with no warning.
- **C: was full** (0.6 GB of 1862) because `auto_cleanup=false` in settings had
  let `/root/blastlab_runs` grow to **374 GB**. 111.9 GB was freed and cleanup was
  re-enabled with a 150 GB ceiling and 10 runs kept.
- **git was installed on Windows** (`Git.MinGit`, user scope) so that version
  control no longer depends on WSL being up.

## M0 — infrastructure

`requirements.txt` and `pyproject.toml` were created (neither existed). Code
locked inside `gui/` moved to neutral homes, with compatibility shims:

| From | To |
|---|---|
| `gui/settings.py` | `core/settings.py` — *the foam backend was importing it from `gui`* |
| `gui/mode.py` | `core/mode.py` |
| `chain_panel.stage_errors` | `core/chain.py` |
| `gui/worker.py` | `solvers/worker.py` |
| `app._solve_stage` + `_write_trigger_remap` | `solvers/jobs.py` |
| `view3d_panel.Feed3D` | `viz3d/feed.py` |
| `preview_panel.case_geometry` | `viz3d/geometry.py` |

**The 3D viewer process was rewritten.** `viz3d/protocol.py` holds a two-slot
shared-memory ring (`SharedFrameRing`, latest-wins, with a sequence stamp per
slot to detect a torn read) and a `FrameLayout` that computes the byte map from
the scene's init; `viz3d/process.py` holds the pipe; `viewer_main(conn, opts)` is
now a small Qt application with a render window per surface
(`run`/`results`/`setup`) instead of one blocking VTK loop; `client.py` is a thin
adapter so the CLI path survives unchanged.

**The blocking queue is gone:** 50 frames nobody reads return immediately, and a
late reader gets the newest one.

## M1 — shell, Run tab, embedded viewer

`blastlab/ui/` with 11 modules: `theme` (same palette, QPalette+QSS, ~30 icons
drawn in QPainter instead of PIL), `widgets`, `dialogs` (modals replaceable in
tests), `bridge` (thread→GUI), `pg_plots` (pyqtgraph:
`ScalarImage`/`MeshOverlay`/`LiveSlicePane`), `run_panel`, `run_controller`,
`view3d_host`, `viewer_link`, `testing`, `app`.

**Three things that were measured, not guessed:**

1. **Re-parenting a foreign window twice is an access violation.**
   `foreign.setParent(None)` followed by moving the container killed the process;
   likewise at shutdown if Qt tears the container down after the child is already
   dead. The fix: the container is built **once** and only *migrates* between the
   tab and the floating window, and at shutdown it is torn down while the child is
   still alive, draining the DeferredDelete queue.
2. **`RunController.running` cannot rely on `is_alive()` alone** — the thread
   keeps tearing down for microseconds after `done`, and a new run gets rejected
   for no reason. A `_done_seen` flag was added.
3. **The viewer process opens only for a 3D case.** Blanket prewarming held VTK
   (~150 MB) through a 2D session, on a 7.7 GB machine where WSL takes 5.

## M2 — the Setup tab

The form is built from a **toolkit-free field specification** (`ui/setup_spec.py`)
and an engine (`ui/fieldform.py`) instead of 1,076 lines of hand construction. The
engine provides exactly the `form.v[name]` contract Tk had — `get()` returns a
str, `set()` fires the callbacks, `trace_add` exists — so `get_case()` /
`set_case()` moved across almost verbatim, and so did the tests that touch fields.
Only three hooks are imperative: solver mode, the AMR sub-group, and the symmetry
axis. The previews were extracted to `output/preview_draw.py`, and the Tk panels
became thin wrappers over it, so the two existing Tk tests are the proof that the
extraction changed no behaviour.

**Four more things measured, not guessed:**

1. **`QFormLayout` puts the field above the label** when it is too narrow.
   Measured: a label at x=17 w=132 and a field at x=21 w=272 on the same row —
   i.e. a one-character label. Every row is now an explicit `QGridLayout` with a
   fixed-width caption column.
2. **A deferred-broadcast contract is mandatory, not polish.** A `set()` from
   inside a trace applies immediately but its broadcast is deferred until the
   current one finishes (the same contract as `core/mode.py:SolverMode`) —
   without it the symmetry-axis hook intermittently lost `cx`.
3. **`QCheckBox.clicked` does not reliably deliver the bool** through the
   binding; the handler calls `isChecked()` instead of trusting the argument.
4. **Two real bugs in the old form:** `order` was parsed outside the error
   brackets and threw `IndexError` out of `get_case` on an empty box; and
   `eos`/`order` were read in both solver modes although their rows are
   native-only.

## M3 — the Results tab

A shell (`ui/results_panel.py`) with a result selector, eight exports and a Title
row, plus three separate sub-panels (`results_fields`, `results_gauges`,
`results_anim`) — and all disk writing in `ui/exports.py`, where it is testable
with no window at all.

**The central inversion:** in Tk, every interaction built a whole Figure and
handed it to the panel-grid builder with n=1. Here the panel exists continuously,
so switching a field or a snapshot is **one array upload**: the `ScalarImage` is
keyed on `(result, face shapes, slice)` and cached. Switching planes in 3D does
rebuild, because the faces and the mask differ. `output/plots.py` remains the sole
owner of files, so `PNGs` and `Report` keep writing the full grid — and their
tooltips say so, because from now on the screen and the file differ **on purpose**.

**Three measurements:**

1. **`extend='max'` has no pyqtgraph equivalent.** The 99.5th-percentile clip is
   declared in words instead: a title suffix **identical to the one in the
   exported PNG**, and a colour-bar label suffix.
2. **The gauge table was choking the plots** — measured at 900×600 with three
   gauges: 192 px of table against 136 px of canvas. The table is capped at 4 rows
   and scrolls beyond that, and the canvas takes the stretch. **This is N2-09's
   problem in the opposite direction.**
3. **`apply_theme` had never coloured any title.** It passed `text.lstrip('#')` to
   `LabelItem`, which `mkColor` rejects, and the whole block was wrapped in
   try/except — so the failure had been swallowed silently since M1.

**pyplot left the GUI process.** `pg.colormap.getFromMatplotlib` imports
`matplotlib.pyplot` just to read a colour table, so **drawing a field on screen**
was enough to drag in the global figure manager — exactly what
`output/pyplot_bridge.py` exists to prevent. The table is now sampled directly
from `matplotlib.colormaps`, and the LUT is byte-identical to before.

## M4 — Chain tab and run browser

`ui/chain_panel.py` and `ui/run_browser.py` (QDialog + QTableWidget), plus a new
neutral home `solvers/foam/runs.py` for reading run directories, which
`gui/run_browser.py` re-exports so its importers and its test need not move.

**One error sink, and the dialog last.** Five `showerror` calls became
`error_sink(title, lines)`, and `run()` returns False on refusal, so a test can
rely on the return value and the recorded lines rather than on a modal. The
harness-hang problem applies here at full force — a static `QMessageBox` runs a
nested event loop and will hang a non-interactive driver exactly as `messagebox`
did — so **the reason reaches the status bar and the log before anything touches
a dialog.** Two tests replace the dialog with a function that **raises** and
verify the refusal is still fully recorded. That is a feature, not a note.

**Two things invisible in the code that must not be changed:** the workspace
directory is created **only** after every check has passed (it used to be created
even when the run was refused), and `stage_errors` runs **after** the profiles are
wired, so it judges what will actually run. In the browser, `alive is None` is
refused like `True` — "WSL did not report" is not "finished" — and the two-phase
fill goes through `ThreadBridge`, so the `queue.Queue` and the `after` poll are
gone and the selection is preserved **by name**, because row order can change
between the two passes.

**A real bug exposed in M4.** The chain pins `adaptive_write=False` on every stage
so it is reproducible — but that was an **ad-hoc attribute** set on the dataclass,
and `asdict()` does not see those. The JSON files saved "for reproducibility" lost
exactly the flag that made them reproducible, and re-running from them went back
to the adaptive controller. `adaptive_write` is now a declared field on all three
Case classes (file version 13; the default `True` is the existing behaviour).

## M5 — the default is switched

`python -m blastlab` opens Qt; `--tk` opens the original; `--qt` is accepted but
hidden (`argparse.SUPPRESS`) so transition-era shortcuts keep working.
`blastlab.bat` was not touched — it only forwards arguments. The last `TabStub`
was deleted and all four tabs are real.

Also added, because the stubs had hidden it: `_result_msg` routes Results messages
to **both** the log and the status bar — someone standing on the Results tab would
not otherwise see that an export finished or failed.

**Two real end-to-end runs through the new window:** `_e2e_ui_native.py` (a full
2D native run, all the way to files on disk — this is the test that found the
animation colour-scale problem) and `_e2e_ui_chain.py` (a 1D→2D chain in 10.5 s,
including the profile passing through disk).

## M6 — the parity round

### The Setup form was clipped

The form asks for two 310 px columns, the Setup tab shares width with the preview,
and `ScrollColumn` has no horizontal scrollbar. Below a ~1290 px window **the
cards in the right-hand column were simply cut off**:

| Window size | viewport | content | clipped |
|---|---|---|---|
| 1600×900 | 856 | 856 | — |
| 1280×840 (the default) | 620 | 628 | **8 px** |
| 1100×720 (**the window's own minimum**) | 440 | 628 | **188 px** |
| 900×600 | 440 | 628 | **188 px** |

So at the minimum size the window itself declares, some fields were not reachable
at all. **The fix:** `FieldForm` collapses to a single column below
`2*COL_MIN + GAP`, after which everything is reachable through the vertical
scrolling that already exists.

**Three things the fix ran into, each of which would have stopped it:**

1. **The form's `resizeEvent` never fired at all.** `QScrollArea` with
   `setWidgetResizable(True)` gives the child `max(viewport, minimumSizeHint)`, so
   as long as two columns demand 628 px the form reports 628 at every window
   width. The solution: an event filter on the **viewport**, whose width is the
   real measure of the space.
2. **The three forms share a `QStackedWidget`**, whose minimum is the **largest**
   of the pages even when they are hidden — so collapsing only the visible page
   changed nothing. All three collapse together.
3. **The scroll area had already measured before the switch.** After the collapse
   `minimumSizeHint` drops 628 → 310 but `width` stays 628 — still clipped. An
   explicit `updateGeometry()` + `resize()` is required.

### What looking at the screenshots found

The harness took screenshots, and looking at them found four bugs — three of which
no assertion catches:

1. **The form columns collapsed at the default size** — closed above.
2. **Export button labels were truncated at every window size.** Four of eight:
   `Animatio`, `Summary C`, `Gauges TS`, `Field CSV`. They were pinned to 106 px
   while needing 116–155. This is N2-10's problem in Tk, which was fixed there by
   widening one button — i.e. merely moved. Now `widgets.WrapRow`: each button
   keeps its own `sizeHint` and the row **wraps** to a second line instead of
   shrinking. Measured: 1600→one row, 1000→7+1, 900→6+2, 700→5+3. **The key:**
   `minimumSizeHint` must return the **widest** button, not the sum, or the layout
   refuses to shrink and the row stays 952 px inside a 500 px panel and overflows.
3. **The Setup status card showed 15 % of what validation says.**
   `STATUS_MAX_H=104` came from Tk's metrics, but here the viewport was **54 px** —
   about two lines — against a **367 px** report for an ordinary 2D blastFoam case.
   And the reason 104 was not enforced: the card is vertically `Fixed` and so took
   the scroll area's small `sizeHint` rather than the ceiling. The height is now
   pinned at 132 and the full warning fits without scrolling.
4. **The Results tab showed empty 0..1 axes before there was a result.** That
   reads as "a result with nothing in it". All three sub-views now say what will
   fill them. *(The fix caused a fifth bug: a two-line export row costs height, and
   then at 900×600 with 12 gauges the table (156) was larger than the plots (128) —
   an inversion of the N2-09 rule. The table is now also capped at
   `TABLE_MAX_SHARE=0.42` of the panel height.)*

### The 3D preview jump — four reports and three confident wrong explanations

The owner reported: *"I set SETTING 3D, went to RUN, came back to SETTINGS and the
preview window jumped to the left."*

> **The first explanation was wrong, and the fix built on it did nothing.** The
> guess was that `release`/`claim` were returning the window to the child. The
> owner reported "it still does it", and only then was the mechanism reproduced
> with a real foreign window and Win32 measurement — which is what should have
> happened from the start.

**What actually happens.** `createWindowContainer` does **not** make the foreign
window a child of the container. Measured with `GetParent`: it makes it a child of
the **top-level** window, and Qt maintains its geometry **manually**. The moment
the container is hidden and shown again — which is what a tab switch does — Qt
stops. Measured without the fix: the window sits at (8, 31) while the container is
at (266, 79), i.e. **258 px left and 48 px up**, in the corner of the client area.
And it appears only on the **second cycle**, which is why it looked inconsistent.

**Of the obvious solutions, only one works** (also measured): a cascade of
`resize`, `updateGeometry()` and hide/show all leave the offset. **Explicitly
setting the `QWindow`'s geometry** is what restores it.

**But enumerating the triggers failed three times.** After binding sync to show
and resize, the owner reported again. Only then was it reproduced with the **real
hierarchy** — a real `SetupPanel` inside a `QStackedWidget`, i.e. two nested
layers rather than a single container — and the measurement showed two more:

| Action | Where the window flies |
|---|---|
| Hide and show the tab | 258 px left, 48 px up |
| Resize the window | 258 px left, 48 px up |
| Switch 3D → 2D and back | **878 px left, 121 px up** |
| Switch to light theme | **751 px left, 121 px up** |

The bottom two rows are what the earlier test missed: **it used a flat hierarchy
and was therefore green while the application was broken.** So the mechanism moved
from **events** to **state**, in two layers: the `QWindow`'s
`xChanged`/`yChanged`/`widthChanged`/`heightChanged` (the move itself, rather than
a guess at what caused it), plus a timer as a safety net for breakage that arrives
with no signal at all — **a theme change is one of those: the window does not
move, the *container* does**, because changing the palette re-runs the whole
layout.

**"Fixed" and "not visible" are not the same thing — and that is the lesson of
this whole chapter.** After position was enforced from state, the window *always*
ended up in the right place. The owner still saw it: *"I saw with my own eyes that
when you switched between the tabs there was a jump of the window from right to
left and back. It was only for an instant, but it was there."* **A
correction-after-the-fact always runs after the broken frame.** Measured on the Qt
path with the real viewer: 18 ms on a tab switch, 68 ms on a theme change.

**So the render window is now a real Windows child of the card**
(`View3DHost._embed_native`): `SetParent` to the card's HWND, `WS_CHILD` instead
of `WS_POPUP`, and the frame removed — all while the window is hidden, so no
intermediate state is visible. **This eliminates the failure rather than
correcting it:**

- Windows clips the window to the card's bounds, so it **cannot** appear over the
  toolbar and the form;
- it is dragged along with the card without anyone maintaining geometry;
- and its coordinates become **relative to the card**, so (0,0) — the value both
  processes fall back to — is exactly the right place.

Measured over 11 operations with the real viewer, including a minimise/restore
that broke the Qt path (915 px left, and it never corrected itself): **never drawn
in the wrong place, 0.0 ms.** The Qt path remains as a fallback for platforms
without `SetParent`, and the timer remains a safety net for both.

> **A mistake only this measurement exposed:** the comparison
> `fw.geometry() != want` trusted **Qt's own bookkeeping** — precisely the thing
> that was broken. On minimise, Qt does not know the window moved, the comparison
> comes out equal, and the correction is skipped. `_real_offset()` now asks the
> window manager via `GetWindowRect`, and `_pin_foreign` moves with
> `SetWindowPos` — because `setGeometry` to a value Qt already believes is a no-op.

Pinned by `_e2e_ui_embed.py` (24 checks), which requires a **real platform** and
**the real viewer**. The fake foreign window remains only as a fallback, because
it **cannot reproduce the flicker** — it does not move itself, whereas the child's
own Qt believes its widget is top-level and pushes a stale position on every
`show()`. That is exactly why the earlier version of the file stayed green through
three reports.

### The truncated-label sweep

The owner photographed: `Exec 1`, `xec 10`, `ec 100`, `Interrup`.
`width=88 if icon else 72`, while `Exec 1000` and `Interrupt` need more — the same
`WrapRow` built for the export row.

**Then every widget was swept, instead of fixing report by report.** Four more:
the `p max [kPa]` chip (20 px short at 1100), `Show mesh` in the live-view row,
`Remove` in Results (4 px), and `blastFoam` in the sidebar.

> **The measurement itself was wrong at first:** it compared against `sizeHint`,
> and a button with QSS padding can sit a few pixels below that and still show
> every letter — `blastFoam` was fully legible in the screenshot. The comparison
> is now against **glyph width** minus the icon and the checkbox indicator.

Widening the sidebar to 232 was fixed and then reverted: it took 16 px from the
form, which needed 612 and got 604 — **a 7 px label fix collapsed the entire form
to one column.** Result: **zero truncated labels across four tabs and three sizes.**

### Tab order and performance

**Tab order** was measured in all four tabs by walking the focus chain against the
geometry. Setup, Results and Chain were already correct, because the forms are
built top to bottom and Qt's default is construction order. **The Run tab was the
exception** — its two rows and two columns are built in an order unrelated to where
they land, and Tab went Run (left) → Name (centre) → Initialise (left) → Refresh
(far right) → the log (left) → the view controls (centre): six crossings of the
window. `RunPanel._set_tab_order` sets a chain by reading order. The log stays in
the chain rather than being removed — it is read-only, but a keyboard user still
needs to reach it to scroll and copy; it is simply last.

**Performance against Tk** (`_qa_ui_perf.py`; the Tk numbers are pinned in the
file from earlier QA nights):

| | Qt | Tk (two runs) | |
|---|---|---|---|
| Build | 1933 ms | 3838 / 3871 | **half** |
| First draw | 989 ms | 1996 / 2034 | **half** |
| `set_case` → preview | 111 ms | not recorded | |
| 40 keystrokes, total | 22 ms | not recorded | |
| 40 keystrokes, worst stall | **1 ms** | not recorded | |
| Idle CPU — Setup | 0.9 % | 5.26 / 20.27 | 5.8× better |
| Idle CPU — Run | 1.2 % | 2.50 / 3.74 | 2× |
| Idle CPU — Results | 1.6 % | 1.56 / 4.05 | equal |
| Idle CPU — Chain | 0.6 % | 4.04 / 4.05 | 6.7× |

Two gates in the file, and they guard against **regression**, not against a slow
machine: typing must not block the interface for more than 400 ms, and an idle tab
must not exceed 25 % of a core. Two caveats are recorded in the file: the Tk
numbers are from other days under other loads, and idle CPU was not measured on
the same instrument on both sides.

## The 3D live view "does not update"

The owner: *"When I run a simple 3D case the 3D in LIVE VIEW does not show
real-time updates."*

**The pipeline works.** Measured end to end on a real native run through the real
window: `auto3d` is set, `feed3d` and `ring` are built, writes to the ring climb,
`host._n_frames` climbs with them, the child reports `follow=True`, and a
screenshot of frame 3 against frame 12 shows **different pixels**. No link is
broken.

**What is broken is the colour bar.** The charge sits at 2.8·10⁶ kPa while the air
around it is at tens of kPa, and 99.94 % of the domain is undisturbed. On a linear
bar everything being looked at is compressed into the bottom fraction of a per
cent — a uniform purple rectangle.

**Every linear rule tested was ruled out by measurement**, documented in
`viewer.LOG_DECADES`:

| Rule | Why it failed |
|---|---|
| 99.5th percentile over the whole domain | Dominated by quiet air — 99.9 % of cells undisturbed |
| Percentile over disturbed cells only | `max/p99.5` came out 1.0–1.4, so the 4× trigger never fired |
| Lower percentiles (p90–p98) | Fire, but **saturate the shock front itself** — up to 1237 % of the bar |
| Separating products by a multiple of the median | The cap moved **100×** when the multiple went from 10 to 1000 |

**What works is a logarithmic scale**, which is exactly what it is for. The floor
was widened from 4 to 6 decades (`LOG_DECADES`), and pressure defaults to log in
`View3DHost._log_default_for`; other fields stay linear and an explicit user choice
wins. Measured on the frames: the shock front lands at 81–93 % of the bar, 10 kPa
gets 8.8 % and 100 kPa gets 25 % — instead of 0.0004 % and 0.004 %.

**Two findings to remember:**

1. **The native 3D solver is too slow to show anything.** dt is ~10⁻⁸ s, and the
   run reaches 7·10⁻⁵ s after 300 s of wall clock — the wave occupies less than
   one per cent of the domain. **A large part of "it does not update" is that, not
   the colour.** Verified against blastFoam: in the same window, a 328-second 3D
   run moves the wave from 0.53 % of the domain to **53.4 %** while the peak falls
   from 8.8·10⁶ to 2.2·10⁴ kPa, and two renders 22 frames apart differ pixel by
   pixel. The live view works; the native solver simply does not get there.
2. **The "Surface loads" bar stays linear** while the field bar is logarithmic —
   the loads layer holds its own range and does not receive the log flag. Not
   fixed.

## blastFoam through the Qt window — the big gap closed

Until this point every Qt suite ran the native solvers only, which means **the
solver the owner actually works with had never been tested end to end through the
new interface.**

| Suite | What it proves |
|---|---|
| `_e2e_ui_foam.py` (28 checks, a 37 s 1D run) | foam fields survive a form round-trip in three dimensions; the sidebar switches to blastFoam per the case; a real run through the Run button path; the log banner; foam warnings arrive with a message and no bare `--> FOAM Warning` marker; the result reaches Results and draws; the VTK button is shown and enabled for a foam run; PNGs are written — **and the run browser against real WSL**, including the second phase of the size column (21 runs; `du` arrives long after the names, and until then there is a deliberate `…`) |
| `_e2e_ui_foam3d.py` (13 checks, a 328 s 3D run) | The live view, measured by **content** rather than "frames were sent" |
| `_e2e_ui_chain_foam.py` (23 checks, a 614 s 1D→2D→3D chain) | **The hand-off is proven, not assumed:** stage 2 starts at 4.95895e-05 s, exactly what stage 1 wrote to its profile, and stage 3 at 1.94225e-04 from stage 2's — a nine-digit match, not "later than". `adaptive_write=False` in all three files, so a re-run lands on the same write schedule |
| `_e2e_ui_resume_foam.py` (16 checks) | `resume_foam_run` had existed since M3 and **had never been run**. This is a place where a day of computation can be lost silently, because a resume that restarts from zero looks exactly like one that worked — until you compare times. So they are compared: the stopped run spans 0 to 4.79e-05 s, the merged one after resume spans 0 to 1.95e-04 — the same start point (replay rebuilt the whole history) and four times further |

## M6b — new features, after parity rather than before

**(a) Live gauges.** Tk could only show gauges after the run finished, which is
backwards from what a gauge is for: a gauge tells you whether the shock reached the
point you care about, and that is a question asked **during** the run.

- `RunHooks.gauges`/`wants_gauges` carry the series, with the same latest-wins slot
  the live frames use. The payload is **the whole series so far**, not a delta, so
  coalescing messages loses nothing and the receiver holds no state the solver
  already holds.
- The three native solvers emit at the existing frame rate; blastFoam re-reads
  blastProbes at 1 Hz. **No `tail_probes` was built** — a full read of a
  few-thousand-line file is cheaper than the bookkeeping of an incremental read,
  and it inherits the restart-chunk merging `read_probes` already does for free.
- **Off unless the view is open**, and off the moment you leave it.
- Traces are decimated above 4000 points **by per-bucket maximum, not by fixed
  stride** — a shock peak is a sample or two wide, and a fixed stride simply
  deletes it.
- 20 checks on a real 2D solve: 178 distinct trace lengths **during** the run, from
  4 to 740 samples, and the live peak matches the finished result's to the last
  digit (6545.779 kPa).

**(b) 3D at the sampling rate — done, but not as the plan drew it.**

A blastFoam run can send a full 3D frame **only when it writes**. Measured on a
real run through the Qt window: 38 frames in 328 s, one every 8.6 s — while the
very same case was decoding its explosion plane for the 2D view **about four times
a second**. The 3D view was tens of times staler than data already sitting on the
machine.

So the already-decoded plane is handed to the 3D scene too. Measured on the same
case afterwards: **106 sampled planes against 38 written frames, 2.8×.**

**What was not built, and why:** the plan called for a new `liveSurf` function
object (planes + isoSurfaceCell + patch), a legacy VTK decoder, and mesh transport.
None was needed: **no writer change and therefore no movement in the golden
files**, no extra sampling and therefore no cost to the solver, and no extra file
read because the array is decoded anyway and about to be dropped. The isosurface
and the volume stay at write rate — and they should, because they need a field the
plane does not have.

**It is one plane and the viewer says so.** `_SampledPlane` draws it as an
independent one-cell-thick mesh rather than writing into the scene's grid, because
patching one layer of a volume would show a shock that exists in that plane and not
around it; the HUD notes that the sample time leads the written frame; and a full
frame cancels it, so the scene never holds a plane that has run ahead of a volume
that has caught up.

**(c) Playback speed control.** 0.25× to 4×, measured at 3.8 to 62.5 frames per
second. Labels rather than a slider, so two sessions can be compared. Above 1× the
timer would be asked for more than Qt provides, so a tick advances more than one
frame instead of trying to beat the screen refresh. The speed does **not** reach
the export, which holds its own frame rate.

## M7 — the Qt harness

All 59 matrix scenarios run against a Qt window, plus four that exist only because
of the migration. The driver layer was replaced as planned; the logging,
checkpoint, budget, `findings.jsonl` and exit codes stayed exactly as they were.

| Group | What it covers |
|---|---|
| S00 | Whether the harness works at all |
| B01–B07 | Appearance, empty states, three dimensions, hover and disabled, resize, keyboard, a light-mode tour |
| C01–C12 | Validation, point lists, native/foam scope, zones, AMR, cell ceilings, the report card, previews, axis labelling, save/open |
| D01–D06 | Native runs through the Run tab |
| E01–E09 | The Results tab over saved results |
| F00–F11 | Real blastFoam runs in WSL |
| G01–G03 | The Chain tab |
| H01–H03 | Light mode over everything that draws |
| I01–I06 | Robustness |
| **Q01–Q04** | **New:** viewer process lifecycle across three surfaces, repolish on every panel, screen against file, and DPI at 125 % and 150 % |

**Three assertions Tk would not have passed**, which is why these groups are worth
something: C01 requires two parse errors to be shown together; B02 requires every
export button to be disabled with no result; D03 requires an interrupted run to say
so next to the run state.

**What replaced what, and what was measured:**

- `pump()` is a `processEvents` loop, not a nested `mainloop`. The nesting stack
  disappeared along with `root.after`, because `ThreadBridge` is a queued signal.
  The gap sampling, `until`, the deadline and the STOP-file check were preserved.
- **Screenshots through `QWidget.grab()`** instead of `ImageGrab` over DWM bounds.
  **This solves the non-interactive-session problem:** `ImageGrab` returns black in
  a disconnected session, while `grab()` renders the widget itself. Measured: 4
  screenshots, 68–113 KB, luma 38.6–40.7 (the failure floor is 6), at the correct
  1280×840.
- Dialogs through `ui.dialogs` + `os.startfile`; exceptions through
  `sys.excepthook` + `qInstallMessageHandler` + a recorder around
  `ThreadBridge._run` (which swallows exceptions deliberately — right for the
  application, wrong for the driver).

**Bugs the harness found immediately:**

- `results_fields.select_field` did `meta['j0']` unguarded, so a result whose meta
  did not match the dimension it was filed under threw `KeyError` **from inside a
  redraw** and took the panel with it.
- And two bugs in the driver itself: `wait_log` counted from a mark taken before the
  run clears the log, and `_cache_result` stored `last_result()` — which is the
  previous run's when the current one overruns.

**Two detectors whose first answer was wrong**, both from the same family:
comparing a button against `sizeHint` (a button with QSS padding sits below it and
still shows every letter), and comparing a **wrapping** label against glyph width —
Q04 reported six truncated labels and all six simply move to a second line. The
detector now asks Qt's `heightForWidth`.

## One more bug, found in `git status`

A file literally named `None`, 29 KB of real gauge data, after a run whose case
said `gauge_file=None`.

Two halves, and either fix alone would have hidden the other. **In the form:**
`gauge_file` was the only optional path without the `or None` / `or ''` that
`profile_file` and `anim_file` have two lines away, so `None` entered the widget as
the string `'None'` and came back as one. **And in `jobs.solve_stage`:** the guard
only asked whether the case **has** gauges, never whether a file was requested, and
`np.savetxt` turned the path into a string and wrote it. The round trip is now
pinned for all three dimensions and all three paths.

---

## Tests added during the migration

`test_viz3d_protocol.py` (25), `test_ui_drain.py` (36), `test_ui_run_panel.py` (58
— including `ImageItem` orientation, the obstacle mask, AMR cell counting and AMR
log folding), `test_ui_view3d_host.py` (38), **`test_ui_no_vtk_in_main.py` (9 —
locks the rule "no VTK in the GUI process")**, `test_ui_setup_form.py` (88),
`test_ui_preview.py` (41), `test_anim_scale.py` (56 — including a pixel comparison
between the movies, and a check that the same case produces the same artefact from
both forms), `test_ui_results.py` (104), `test_ui_three_surfaces.py` (33 — three
surfaces against one connection), **`test_ui_no_mpl_pyplot.py` (18 — locks "no
pyplot in the GUI process", in a clean process because `sys.modules` is global)**,
`test_ui_chain.py` (42), `test_ui_run_browser.py` (48), `test_ui_parity.py` (36),
`_e2e_ui_native.py` (35), `_e2e_ui_embed.py` (24).

Commits: `b18a9cb` (M0+M1), `68d23dc` (M2), `d54a4e3` (documentation), `8e107fe`
(animation colour scale).
