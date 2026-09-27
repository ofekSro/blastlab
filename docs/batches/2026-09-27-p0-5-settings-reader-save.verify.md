# Batch p0-5-settings-reader-save · verify report

Range `8aa08bc..25ce709` checked, plus 2 fix commits; HEAD `1bf0792`. No push, merge or
branch switch. Verdict: ready for QA once the held Tk/WSL suites are run.

## Per task
| Step | Task | Status |
|---|---|---|
| 1 | P0-5 items 1, 2, 5 - settings in the repo | FIXED `5903522` |
| 2 | P0-5 item 3 - `cleanup_plan` | VERIFIED |
| 2b | Q3 - cleanup off by default + disk warning | FIXED `1bf0792` |
| 3 | P0-5 item 4, P4-3 - docs | VERIFIED (the one remaining match is the P0-5 task text, removed by bookkeeping) |
| 4 | P1-7 - reader accepts `);` | VERIFIED (on-screen frame-0 QA deferred: WSL + screen) |
| 5 | P2-13 item 3 - `test_vent_wall` under pytest | VERIFIED |
| 6 | P1-18 Save half | VERIFIED (Tk part of `test_open_case` held: screen) |
| 7 | P2-13 item 4 as amended by Q4 - conftest hook | VERIFIED |
| 7b | P2-14 item 7 - `read_probes` by time | VERIFIED |
| - | P2-7 / P2-8 (`c1f3101`), P2-10 (`f8f57f9`) | confirmed already done |

## Defects found in the diff
1. **`settings._migrate`** printed "created …" on every load even when `save()` failed
   (read-only root or sync lock). Medium. **Fixed** in `5903522`; new check (h), which
   fails on the old code.
2. **`env.start_disk_warning`** had `except Exception: pass`, which hid real faults.
   WSL-unreachable never raises there. Medium. **Fixed** in `1bf0792`: one stderr line,
   pinned by a test.
3. **`_migrate`** has an `exists()` / `os.replace` race between two processes starting
   at the same moment. Both would write the same content. Low. Not fixed.
4. **Not from this batch:** at window close, the `ui/app.py:335` `_poll_wsl` thread's
   `bridge.post` sometimes prints "Signal source has been deleted". Both suites where it
   shows still exit 0. Not fixed.

## Review answers
- **Migration.** It can never carry `auto_cleanup` true: it is forced off, and the
  default is off. It never runs under tests (`BLASTLAB_SETTINGS` is set), and it never
  overwrites an existing file.
- **Disk warning.** The Qt sink goes through `bridge.post` and the Tk sink through
  `root.after`, the same pattern as `_log_threadsafe`, so no widget is touched from the
  worker thread.
- **conftest hook.** It cannot report a false failure: every `check()` appends to a
  module-level `FAIL` or `FAILS`, and no suite rebinds its list.
  `test_vent3d_load.evaluate_quietly` clears its list on purpose, which can only give a
  false negative. A test that exits keeps its own exception. pytest 9.1.1 supports
  `hookimpl(wrapper=True)`.
- **`read_probes`.** Exact float equality on time is safe: p, rho and U come from the
  same probes function object, with the same formatting, through the same
  `_merge_chunks`. The matched-case dict is unchanged.
- **Reader `);`.** Nothing relied on the old refusal. The only other caller is
  `scalar_size` in `backend._time_is_whole`, where this is the intended fix.

## Tests run, all PASS
- `test_regression` twice, byte-identical.
- Script and foam suites (no WSL): `settings_path`, `foam_start_frame`, `foam_reader`,
  `foam_writer`, `foam_resume`, `foam_amr_ingest`, `foam_postmortem_decomposed`,
  `foam_wsl_resume`, `hardware`, `case_validate`, `refine`, `vent_wall`,
  `vent3d_load`, `layering`.
- Qt offscreen:
  - `ui_status_cells`, `ui_parity`, `ui_setup_form`, `ui_char_hd13_run`,
    `ui_char_case_form`, `ui_no_vtk_in_main`, `ui_no_mpl_pyplot`.
  - `test_open_case`, the pure and qt parts.
  - `test_run_preflight` parts A, A8 and B.
- Whole-directory pytest: **171 passed, 8 errors**. All 8 errors predate the batch:
  "fixture 'tmp' not found" in `test_load_csv` and `test_wall_clearing`. No new failures,
  so no findings.

## Held
- **Held for WSL:** `test_foam_env` (it probes live WSL), every solving suite, `_e2e_*`,
  and the CLAUDE.md dry-run one-liner.
- **Held for the screen:** all 14 Tk `test_gui_*`, the Tk part of `test_open_case`,
  part C of `test_run_preflight`, and `_qa_*`.

## GUI screens that need QA
- Qt Save case… (Ctrl+S) on the 0-D form: save the starter, then reopen it.
- Qt and Tk startup with cleanup off and the runs root over `cleanup_max_gb`: one log
  line and one status warning, nothing modal, nothing deleted.
- P1-7: the player shows frame 0 for a chamber run and a chained 1D → 2D run (WSL).

## Owner notes
- The disk warning is skipped under `BLASTLAB_SETTINGS`. Owner decision 2026-09-27:
  keep it that way.
- The warning's `run_dirs()` goes through `\\wsl.localhost`, which starts the distro on
  every GUI start. The old default-on sweep did the same.
