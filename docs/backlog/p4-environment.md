# P4 - environment, disk, personal

Moved out of [`TODO.md`](../../TODO.md) on 2026-10-13 (owner-approved split, TODO.md at its
1000-line cap; `docs/batches/2026-10-13-todo-split-proposal.md`). Ids unchanged.

### P4-1 · The repository sits inside OneDrive

`git worktree remove` failed once with "Permission denied" — a sync lock on `.git`.
Consider excluding `.git` from syncing, or moving the repository out of OneDrive.

### P4-2 · Disk cleanup — low urgency

Candidates, all of them calm decisions rather than pressure: a 13.4 GB zip that
duplicates an unpacked folder beside it; `C:\OneDriveTemp` (~6 GB of upload
temporaries, recreated if deleted); a ~45 GB reference-model duplication; and the
large win without deleting anything — **Files On-Demand ("Free up space")** on the
biggest archive folders. `hiberfil.sys` is 3.1 GB and `powercfg /h off` removes it
if Hibernate is unused.

> **Never touch `~\Desktop`** — about 930 GB of thesis data.

### P4-3 · WSL run cleanup, and the trap inside it

`python -m blastlab --clean-foam-runs` (also `--older-than N` / `--keep-gb N`).
Automatic cleanup on GUI start runs only with `auto_cleanup: true` in
`<repo>\settings.json` (P0-5: the file lives in the checkout, git-ignored; every
checkout and worktree has its own). To see what it *would* delete, run the dry run
`env.cleanup_plan` (CLAUDE.md §8.2), never `env.auto_cleanup`, which deletes. In the
OneDrive checkout a sync lock can fail the atomic write in `settings.save()` (the
`P4-1` symptom): it warns once, and the lost `hw_*` cache caps the next headless run
as a 4 GB VM (CLAUDE.md §4).

**The `ext4.vhdx` does not shrink by itself.** Reclaim with `wsl --shutdown` then
`wsl --manage Ubuntu --set-sparse true`.

> The corpus once reached **374 GB and filled C:**. Cleanup is **off by default** since
> 2026-09-27 (owner: deletion inside WSL is final, a full disk is recoverable); it runs
> only when the settings file says `auto_cleanup: true`. With it off, the GUI warns at
> start when the runs root passes `cleanup_max_gb` (150 GB here) and deletes nothing.
