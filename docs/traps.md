# Traps - the long form of CLAUDE.md §8

Moved out of `CLAUDE.md` on 2026-10-13 (owner, token budget). `CLAUDE.md` §8 keeps every
heading and number, and keeps the traps that prevent a destructive action (8.1, 8.2, 8.4,
8.5, 8.6) in full; this file is the complete text of all seven, read on demand. Code and
docs cite them as "CLAUDE.md 8.n" - that keeps resolving.

Each one has already cost a day.

## 8.1 Never route a file's content through PowerShell strings

Windows PowerShell 5.1 reads BOM-less UTF-8 as ANSI, so
`Get-Content -Raw | -replace | Set-Content` mojibakes any file with a single
non-ASCII character - it corrupted `TODO.md` (committed, then recovered) and
later mojibaked the ellipses and box-drawing characters in
`ui/run_browser.py`. Use Read/Edit/Write for every change, even a one-liner.
PowerShell may still list, move and hash files. Damage hunt: `rg 'ג€|ג”'`.

**And a second PowerShell quoting trap, on the way out:** passing a string
containing `"` to a native exe splits it into several arguments. A commit message
with an embedded quote reaches `git` as three broken pathspecs. Write the message
to a file and use `git commit -F`.

## 8.2 Any code path that builds the GUI can delete the run corpus

blastlab's automatic cleanup fires at startup - including from
`tests/_e2e_gui_*.py` and the QA harnesses - and it does not ask. It once took
`/root/blastlab_runs` from 56 GB / 40 runs to 12 GB / 6 runs in seconds,
destroying the crashed run that was the entire subject of that night's
investigation. Now locked in layers: `auto_cleanup` defaults to off (2026-09-27;
with it off the GUI only warns when the runs root passes `cleanup_max_gb`),
`ui/testing.private_settings()` writes the flag, and the settings file is
`<repo>\settings.json` (P0-5: git-ignored, beyond Store-Python virtualisation).
Before a session that matters, run the dry run (it deletes nothing; expect `False`):
`python -c "from blastlab.core import settings as s; from blastlab.solvers.foam import env; d=s.load(); print(s.config_path(), d['auto_cleanup'], [r['name'] for r in env.cleanup_plan(d)])"`
- the list is what the sweep would take if it were on - and copy any run you
care about out of `/root/blastlab_runs`.

## 8.3 WSL can be torn down under a running solve

On 2026-09-16 a 13-rank 3D
run died 11 minutes in because WSL terminated the distro - "Init has exited",
ext4 unmount, `EIO` everywhere. Not the solver, not disk, not RAM. Suspected
cause: corporate IT group-policy agents (BigFix, gytpolClient) 43 s earlier.
`W3` (runner/runloop/backend + `test_foam_wsl_resume.py`) now detects the EIO
signature and resumes from the last write, max 3 times per run. If a run "just
stopped" with `Input/output error`, check the Hyper-V-VmSwitch event log and
`dmesg` before blaming the case.

## 8.4 `.wslconfig` is a loaded gun

An out-of-range value makes WSL refuse to
create the VM at all, with no warning (`vmIdleTimeout=-1` cost a full day, and
took git down with it back when git lived only inside WSL). Also never cap RAM
there: `env.detect_ram_gb` derives the cell cap from the VM's memory, so a cap
silently shrinks the largest case the app will allow.

## 8.5 Disk

The run corpus once reached 374 GB and filled C:, and the
`ext4.vhdx` only grows - deleting runs inside WSL does not return the space, and
`--set-sparse` / `compact vdisk` no longer work. Reclaim = prune the runs, then
export/import the distro: `docs/wsl-disk-reclaim-plan.md` (done 2026-09-27, 481 ->
8.6 GB). **Never touch `~\Desktop`** - about 930 GB of thesis data.

## 8.6 Before any WSL run, confirm the VM is free

`wsl -d Ubuntu -- pgrep -a blastFoam` must come back empty. A foreign solver
makes memory-sensitive tests fail falsely.

## 8.7 GUI bugs: measure with the real component on a real platform

Stand-ins and reasoning from the API docs have been wrong every single time -
the 3D-preview jump took four reports and three confident wrong explanations,
each from a reproduction missing something the real app has. The real viewer
child does start here (it needs `if __name__ == '__main__'`, it uses
multiprocessing), `QT_QPA_PLATFORM` must be **unset** because
`QWindow.fromWinId` returns `None` offscreen, and Win32 through ctypes
(`GetWindowRect`, `GetParent`, `IsWindowVisible`) is the ground truth - not
Qt's own `geometry()`, which was the broken thing. "It ends up in the right
place" is not the bar; measure the longest unbroken stretch during which a
visible widget is somewhere wrong.
