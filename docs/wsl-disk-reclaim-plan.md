# Reclaiming the 481 GB WSL disk - a plan, nothing executed

**Status: PLAN ONLY.** Written 2026-09-26 from read-only measurements. No run was
deleted, no WSL command that changes state was issued, no other file was touched.
Every step below waits for the owner's tick in §3 and an explicit "go".

The question that prompted it: *the solves saved while building the app take a
lot of disk - are they really needed?* Short answer: **no, except one, and even
that one only as a 100 MB skeleton.** The long answer, and the only procedure
that actually gives the space back to Windows, follows.

---

## 1. What is on the disk (measured 2026-09-26)

| Where | Size |
|---|---|
| `%LOCALAPPDATA%\blastlab-wsl\Ubuntu\ext4.vhdx` (the whole WSL disk) | **481 GB** on C: |
| inside it: `/root/blastlab_runs` (11 run directories) | 428 GB |
| inside it: everything else (Ubuntu + OpenFOAM-9 + blastFoam + apt cache) | 9.3 GB |
| C: free | **148 GB** (1714 used) |
| the repo itself (code, docs, git, gifs) | ~0.25 GB - irrelevant |

There is no second local drive (`Z:` is a disconnected network mapping). The
repo lives under OneDrive; `%LOCALAPPDATA%` and `%USERPROFILE%\blastlab_evidence`
do not.

### The eleven runs

| Run | Size | What it is | Cited by | Verdict |
|---|---|---|---|---|
| `20260923-195308_3d_p31468-00` | 174 GB | **HD1-3d evidence run**: 864,000 cells, 13 ranks, 749 reconstructed writes + 13 `processor*` copies | `DONE.md` HD1-3d, HD1-13; `_e2e_vent_3d.py --load`; `docs/hd13/` | **keep a skeleton, delete the fields** (§2) |
| `20260922-132259_3d_p3756-00` | 193 GB | the same case with `n_snapshots` 30 instead of 6, superseded | `docs/batches/2026-09-24-hd1-wall-load.md` §936 already proposes deleting it | **delete** |
| `20260922-011030_3d_p39152-01` | 54 GB | 7-rank attempt of the same night, 486 writes | only in `ls -1t` listings | **delete** |
| `20260921-235453_3d_p18960-00` | 6.1 GB | serial 3D attempt, 824 writes | only in listings | delete (owner may keep) |
| `20260922-005601_3d_p39152-00` | 2.3 GB | serial 3D attempt, 316 writes | only in listings | delete (owner may keep) |
| `20260925-155244_1d_p39872-00` | 13 MB | 1D run | - | keep (costs nothing) |
| `20260921-2*_3d_p27908-*`, `p36304-*` (4 runs) | 5 MB each | small 3D runs | listings | keep |
| `20260924-195414_2d_p39324-00` | 76 KB | 2D run | - | keep |

`wsl -d Ubuntu -- pgrep -a blastFoam` was empty at measurement time: nothing is
running inside any of these.

### Why the evidence run is 174 GB, and what the checks actually read

From `docs/batches/2026-09-24-hd1-3d-close.implement.md` H1: 749 root time
directories (~130 MB each, 97.5 GB) plus the same 749 writes again inside 13
`processor*` directories (88.1 GB). `n_snapshots = 6` never bounded the writes;
`HD1-15` (the per-case `write_budget`) fixed that for future runs.

The post-mortem judge, `tests/_e2e_vent_3d.py --load RUN`, is documented and
built to read **only `case.json` and `postProcessing/gauges`** (module docstring
lines 36-48; `load_gauges`, lines 118-167). It does not open a single time
directory. `HD1-13` was likewise judged "from the run's own files, with no new
solve" from the probes. So a run directory that keeps

```
case.json  .run.pid  log.blastFoam  SHA256SUMS.source  system/  constant/  postProcessing/  0/
```

and drops `0.000100…`–`0.03` and `processor0…12` is **still the evidence run**
for every check that cites it, at ~135 MB instead of 174 GB. That exact file
set already exists as the sha256-checked Windows copy in
`%USERPROFILE%\blastlab_evidence\20260923-195308_3d_p31468-00\` (97 MB; `0/` is
hashed there but not copied).

**What is lost by dropping the fields:** the volumetric p/U/rho/... of 748
writes. Anything that would need them - re-rendering `hd13_vent_jet_3d.mp4`,
a new field-based analysis, `postmortem.load_run` on this run - would require
a re-solve (the original took 85 min on 13 ranks; with `write_budget` set it
would cost ~8 GB, not 174).

---

## 2. Why deleting is necessary but not sufficient

The vhdx is a **ratchet**: it only grows. Measured on 2026-09-22 (memory
`wsl-run-corpus-fills-disk`): deleting 171 GB of runs and `fstrim` returned
nothing to Windows. The routes that used to work no longer do:

| Route | Why not |
|---|---|
| `wsl --manage Ubuntu --set-sparse true` (still in `CLAUDE.md` §8.5) | gated in WSL 2.7.13: *"Sparse VHD support is currently disabled due to potential data corruption"*, demands `--allow-unsafe`. Not on the disk that holds the whole install. |
| diskpart `compact vdisk` / `Optimize-VHD` | only reclaims **zeroed** blocks; ext4 deletion does not zero. Ran on 2026-09-22, reclaimed nothing. |
| zero the free space first (`dd if=/dev/zero`) | inflates the file toward its 1007 GB virtual size before anything shrinks - with 148 GB free on C: that is a self-inflicted outage. |
| `wsl --manage --move` / `--resize` | moves or grows; never shrinks. |

The one route that works is **export the distro to a tar and import it into a
fresh vhdx**. A fresh vhdx is sized by its content. The 2026-09-22 note rejected
this because the tar would have needed ~300 GB; it is feasible now *only
because* §1 first cuts the content to ~10 GB. Therefore the order is fixed:
**prune inside WSL first, export second, replace the disk third.**

---

## 3. Decisions the owner makes before anything runs

Tick and return; each blank one blocks the plan.

- [ ] **D1 - the evidence run.** *Recommended:* keep the skeleton (file set in
      §1), delete its 749 time directories and 13 `processor*` directories.
      Alternatives: (a) keep it whole - **impossible in one move**, the export
      would need ~185 GB and C: has 148; (b) delete it entirely and rely on
      the Windows copy - not recommended, because `env.case_paths` resolves a
      bare run name only under `/root/blastlab_runs`, so `--load` by the name
      `DONE.md` cites would stop working.
- [ ] **D2 - delete `20260922-132259_3d_p3756-00`** (193 GB, superseded). The
      batch record already proposed it.
- [ ] **D3 - delete `20260922-011030_3d_p39152-01`** (54 GB, uncited).
- [ ] **D4 - the two small 3D attempts** (6.1 GB + 2.3 GB, uncited): delete
      (recommended) or keep (adds ~8 GB and ~5 min to the export; harmless).
- [ ] **D5 - the backup tar.** After the rebuild proves itself (§5, S7), keep
      the ~10 GB tar for ___ days / until ___, then delete it.
- [ ] **D6 - who runs it.** The cut (S6) deletes the 481 GB disk; that step is
      run attended, by the owner or with the owner watching.

---

## 4. Pre-flight - the state that must hold at T-0

All read-only. If any line fails, stop and report; do not improvise.

| # | Check | Command (PowerShell 5.1) | Must show |
|---|---|---|---|
| P1 | no solver running (`CLAUDE.md` §8.6) | `wsl -d Ubuntu -- pgrep -a blastFoam` | empty |
| P2 | no blastlab GUI, no `_e2e_*` / `_qa_*` suite running | Task Manager / `Get-Process python` | none that build the GUI |
| P3 | the app's sweep is off (§8.2) | the CLAUDE.md §8.2 dry run (`env.cleanup_plan`; reads `<repo>\settings.json`, deletes nothing) | `<repo>\settings.json False [...]` |
| P4 | free space on C: | `Get-PSDrive C` | ≥ 40 GB (today 148) |
| P5 | exactly one distro, version 2, named `Ubuntu` | `wsl -l -v` | `* Ubuntu  Running/Stopped  2` |
| P6 | the install is healthy *before* we touch it | the seven-tool probe from `CLAUDE.md` §3 | seven paths, exit 0 |
| P7 | default user is root | `wsl -d Ubuntu -e sh -c "id -un"` | `root` |
| P8 | the Windows evidence copy is intact | in WSL: `cd /mnt/c/Users/rotem.ofek/blastlab_evidence/20260923-195308_3d_p31468-00 && sha256sum -c SHA256SUMS.source` | every copied file `OK`; exactly the six `0/*` entries reported missing (they were hashed, not copied) - nothing `FAILED` |
| P9 | the WSL original still matches its own record | in WSL: `cd /root/blastlab_runs/20260923-195308_3d_p31468-00 && sha256sum -c SHA256SUMS.source` | 25 × `OK` |
| P10 | baseline listing, saved outside OneDrive | `wsl -d Ubuntu -e bash -lc "ls -1 /root/blastlab_runs; du -sh /root/blastlab_runs" > $env:LOCALAPPDATA\blastlab-wsl\export\baseline.txt` | the 11 names of §1 |

Quoting rule for every bash line issued from PowerShell: **no embedded double
quotes** - PowerShell 5.1 splits a native argument on them (`CLAUDE.md` §8.1,
second trap). Use `wsl --% -d Ubuntu -e bash -lc "..."` with single quotes
inside, or run the bash lines from a WSL shell directly.

---

## 5. The procedure

Space budget: ≤ 25 GB extra on C: at peak (10 GB tar + ~12 GB trial disk).
Time: about 1-1.5 h wall, of which only S6 needs eyes on it.

### S1 - prune inside WSL (irreversible; needs D1-D4)

Run from a WSL shell (`wsl -d Ubuntu`) as root:

```bash
cd /root/blastlab_runs
# D2, D3 (and D4 if ticked): whole directories
rm -rf 20260922-132259_3d_p3756-00 20260922-011030_3d_p39152-01
rm -rf 20260921-235453_3d_p18960-00 20260922-005601_3d_p39152-00     # only if D4 = delete
# D1: the evidence run keeps its skeleton. Time dirs except 0/, and the decomposed copies, go.
cd 20260923-195308_3d_p31468-00
ls -d [0-9]* | grep -vx 0 | xargs rm -rf
rm -rf processor*
ls                       # expect: 0 SHA256SUMS.source case.json constant log.blastFoam postProcessing system  (+ .run.pid)
sha256sum -c SHA256SUMS.source   # expect 25 x OK - the skeleton is byte-identical to the record
du -sh /root/blastlab_runs       # expect ~0.2 GB (or ~9 GB if D4 = keep)
```

`0/` stays: it is in the hash record and costs 35 MB. Deleting ~1,500
directories of a few hundred files each takes minutes, not seconds.

**Gate S1:** from Windows, `cd blastlab/tests; python -u _e2e_vent_3d.py --load
20260923-195308_3d_p31468-00` prints `VENT 3D: PASS` (13/13). This proves the
skeleton is sufficient *before* the disk is rebuilt. If it does not pass, stop:
the Windows copy is the fallback, and the rebuild waits.

Optional, 0.9 GB: `apt-get clean` inside WSL. Not needed; skip unless asked.

### S2 - shut WSL down

```powershell
wsl -d Ubuntu -- pgrep -a blastFoam      # empty (again)
wsl --shutdown
wsl -l -v                                # Ubuntu  Stopped  2
```

`.wslconfig` (`instanceIdleTimeout=-1`, `vmIdleTimeout=86400000`) is not
touched by anything below; it applies again when WSL next starts.

### S3 - export to a plain tar, outside OneDrive

```powershell
New-Item -ItemType Directory -Force "$env:LOCALAPPDATA\blastlab-wsl\export" | Out-Null
$tar = "$env:LOCALAPPDATA\blastlab-wsl\export\Ubuntu-slim-2026-09-26.tar"
wsl --export Ubuntu $tar --format tar
Get-Item $tar | Select-Object Length      # expect roughly 9-18 GB
```

Plain `tar`, not `tar.gz`: it fits easily, it is faster, and it removes any
doubt about what `--import` accepts. Never place it under the repo - the repo
is in OneDrive and a 10 GB file would start uploading.

**Gate S3:** the archive lists the load-bearing paths:

```powershell
tar.exe -tf $tar | Select-String -Pattern 'root/OpenFOAM/OpenFOAM-9/etc/bashrc$','root/blastfoam/etc/bashrc$','opt/openfoam9/etc/bashrc$','root/blastlab_runs/20260923-195308_3d_p31468-00/case.json$'
```

Four hits. (Listing a 10 GB tar takes a minute or two.)

### S4 - trial import under a throw-away name

This is the step that makes S6 safe: the tar is proven restorable while the
original disk still exists.

```powershell
wsl --import Ubuntu-trial "$env:LOCALAPPDATA\blastlab-wsl\Ubuntu-trial" $tar --version 2
wsl -d Ubuntu-trial -e sh -c "id -un"                                              # root
wsl -d Ubuntu-trial -e bash -lc "source /root/OpenFOAM/OpenFOAM-9/etc/bashrc && command -v blastFoam blockMesh setRefinedFields topoSet subsetMesh refineMesh postProcess && ls /root/blastlab_runs"
```

**Gate S4:** `root`, seven paths, the kept run names from S1. Then remove the
trial:

```powershell
wsl --unregister Ubuntu-trial
Remove-Item -Recurse -Force "$env:LOCALAPPDATA\blastlab-wsl\Ubuntu-trial" -ErrorAction SilentlyContinue
```

Do **not** try to rename `Ubuntu-trial` into `Ubuntu` (registry surgery). The
name `Ubuntu` is one of the four hard-coded constraints (`env.py` line 42);
the real import in S6 uses it directly.

### S5 - last look before the cut

- `Get-PSDrive C` - note the free space (expect ~125-135 GB).
- `Get-Item "$env:LOCALAPPDATA\blastlab-wsl\Ubuntu\ext4.vhdx"` - 481 GB, the file about to go.
- `wsl -l -v` - only `Ubuntu`, `Stopped`.
- The tar from S3 exists and passed S4. The Windows evidence copy passed P8.

### S6 - the cut (attended; D6)

```powershell
wsl --unregister Ubuntu                    # deletes ext4.vhdx - the 481 GB
Get-PSDrive C                              # free space must have jumped by ~480 GB
Get-ChildItem "$env:LOCALAPPDATA\blastlab-wsl\Ubuntu" -Force   # expect empty or absent
wsl --import Ubuntu "$env:LOCALAPPDATA\blastlab-wsl\Ubuntu" $tar --version 2
wsl --set-default Ubuntu
wsl -l -v                                  # * Ubuntu  Stopped  2
```

The install location is the one the setup script uses
(`setup-blastfoam.ps1` line 18), so every path and every memory note stays
true. An imported rootfs has no `/etc/wsl.conf` and no default user, so the
distro comes back as root - exactly what `env.py` assumes.

### S7 - verification ladder (in this order; stop at the first failure)

| # | Check | Expected |
|---|---|---|
| V1 | `wsl -d Ubuntu -e sh -c "id -un"` | `root` |
| V2 | the seven-tool probe (`CLAUDE.md` §3) | seven paths, exit 0 |
| V3 | `cd blastlab/tests; python test_foam_env.py` | green |
| V4 | `python -u test_foam_1d_vs_native.py` | green - a **real solve**, the same proof the install was accepted on (2026-09-09) |
| V5 | `python -u _e2e_vent_3d.py --load 20260923-195308_3d_p31468-00` | `VENT 3D: PASS` - the skeleton survived the round trip |
| V6 | in WSL: `sha256sum -c SHA256SUMS.source` in the skeleton | 25 × `OK` |
| V7 | `Get-Item ...\Ubuntu\ext4.vhdx` | ~10-20 GB |
| V8 | `python test_regression.py` | green (native; untouched, but it is the gate) |

### S8 - aftercare

- Keep the tar per D5; it is a complete, proven backup of the install.
- Delete `export\baseline.txt` and the trial directory if any remains.
- Two documents are now stale and need their own, separate, owner-approved
  edits (not part of this plan): `CLAUDE.md` §8.5 still gives the
  `--set-sparse` recipe, and the assistant memory note `wsl-run-corpus-fills-disk`
  says export/import is infeasible. Both should point at this file.
- `docs/00-INDEX.md` does not list this file yet; same rule.

---

## 6. Rollback at every step

| After | What is lost | How to get back |
|---|---|---|
| S1 | the deleted runs' fields - irreversible by design; that is what D1-D4 authorise | nothing to roll back; the evidence skeleton is verified twice (S1 gate, P8) |
| S2-S5 | nothing | `wsl -d Ubuntu` starts the old distro as before |
| S6, import fails | the old disk | re-run the `--import` line; the tar was proven in S4 |
| S6, tar turns out bad | the old disk | cannot happen if S4 passed - that is why S4 exists. Last resort: `setup-blastfoam.ps1` rebuilds from the 223 MB rootfs (20-60 min); the run skeleton is then restored from `%USERPROFILE%\blastlab_evidence` |
| S7 fails at V4 | - | the install is intact (V2 passed) but a solve does not; treat as `CLAUDE.md` §8.3, check `dmesg` and the event log before blaming the rebuild |

---

## 7. Risks specific to this machine

- **WSL torn down mid-export** (§8.3, IT agents): the export fails cleanly;
  re-run S3. Do not schedule S3/S6 across a policy-refresh window if one is known.
- **A GUI-building process during the window**: `auto_cleanup` is false in the
  real settings today (P3), so the app would not sweep the skeleton; still, no
  GUI and no `_e2e_gui_*` / `_qa_*` suite runs while the plan is in progress.
- **OneDrive**: nothing in this plan writes under the OneDrive root. The tar,
  the trial disk and the baseline live in `%LOCALAPPDATA%\blastlab-wsl`.
- **`~\Desktop`** is never read or written (930 GB of thesis data).
- **The four hard-coded constraints** (`env.py` 42-44; distro `Ubuntu`, jammy,
  the shim bashrc, `/root` paths) are all preserved by an export/import of the
  same distro. None is re-created by hand.

---

## 8. The standing rule afterwards - so this does not recur

The ratchet does not go away: the fresh vhdx will grow to the next high-water
mark and stay there. What keeps it small:

1. **Every heavy blastFoam run sets `write_budget`** (`HD1-15`; it defaults to
   0 = unlimited). Without it this exact case writes ~190 GB in 30 ms of
   simulated time. `TODO.md` `HD1-14` already says so.
2. **Prune right after a run is judged**: keep the skeleton (case.json, dicts,
   log, probes), drop the fields, unless a named follow-up needs them. The
   Windows evidence copy + sha256 record is the pattern to repeat.
3. `auto_cleanup` stays as the owner set it (false). That makes pruning a
   manual step - point 2 - not an automatic one.
4. Watch two numbers: `Get-Item ...\Ubuntu\ext4.vhdx` (the ratchet) and
   `du -sh /root/blastlab_runs` (the current content). If the vhdx passes
   ~150 GB, repeat this plan while the content is still small enough to export.
