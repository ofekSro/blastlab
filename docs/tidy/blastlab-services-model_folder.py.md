# Tidy proposal: blastlab/services/model_folder.py
tier: B · base commit: 9ced617 · date: 2026-10-05

1. [dedupe] L1190 `stage_solve.solve` - `getattr(case, 'solver', '') == 'blastfoam'` repeats the `foam` local set at L1152 (same truth value: default differs but only 'blastfoam' matches). Use `foam`. - APPLIED
   Output risk: none.
2. [dedupe] L457-499 `git_commit` - six `with open(...) as f: f.read().strip()` blocks, depth 5. Add private `_read_stripped(path)` and call it; same single outer `except OSError`. - APPLIED
   Output risk: none (all reads stay inside the one try; same exceptions).
3. [magic-number] L483, L489, L496 `git_commit` - `[:7]` three times -> module constant `SHORT_HASH_LEN = 7` ("git's default abbreviation"). - APPLIED
   Output risk: none.
4. [long-func] L863-945 `copy_foam_skeleton` - extract the per-file copy+hash loop (L915-927) into private `_copy_listed(listing, root, foam, out)`; same order of copy, same `out` mutations. - APPLIED
   Output risk: none (same calls, same order).
5. [long-func] L1133-1221 `stage_solve.solve` - move the hooks set-up (L1135-1156) and the post-run `finally` body (L1177-1215) into private helpers taking hooks/info/err/res; keep the outer try/except/finally and the inner restore-finally in `solve` itself so the ordering of restore vs. write stays identical.
   Output risk: none if the try/finally structure is kept; apply with care.
6. [docstring] L71 `_norm`, L430 `_inside`, L855 `_sha256`, L452 `_repo_root` - no docstring. One line each (case/realpath-normalised path; True when path is root or below, False across drives; hex SHA-256 of a file read in 1 MiB chunks; repo checkout root). - APPLIED
   Output risk: none.
7. [magic-number] L858 `_sha256` - `1 << 20` -> `_HASH_CHUNK = 1 << 20  # 1 MiB read size`. - APPLIED
   Output risk: none.
8. [cleanup] L1138 `stage_solve.solve` - `open(log_path, 'a', ...).close()` -> `with open(...): pass`, no handle left to the GC. - APPLIED
   Output risk: none.

Not touching: the silent excepts at L92, L497, L653, L1092, L1105 (each already carries a reason or guards an absent file/folder; teardown-style) and the `except Exception` blocks in `write_all`/`stage_solve` (they exist so a bug does not lose the run).
Engineering questions: none
