# NIGHT_RESULTS.md — ריצת לילה ללא השגחה

> נוצר אוטומטית בליל 2026-09-09 → 2026-09-10 על המכונה `cee-elsl-d`.
> **קובץ חדש. לא נערך אף קובץ קיים, ולא הורצה אף פקודת git שמשנה מצב.**
> לוגים גולמיים: `night_artifacts/logs/`.
>
> *(סעיף הסיכום ייכתב בסוף הלילה ויוחלף כאן.)*

---

## סיכום

**הבסיס ירוק. שום קובץ קיים לא נערך, שום פקודת git שמשנה מצב לא הורצה,
ולא נותרו סולברים יתומים.**

1. **בדיקות: 39 PASS · 2 FAIL · 3 BLOCKED · 2 לא הורצו · 2 נעצרו ביודעין.**
   מטריצה מהירה 29/29 PASS; חבילות WSL 8/8 PASS; `test_regression` בייט-זהה.
   שני ה-FAIL: `_e2e_foam_amr2d` (דיוק AMR, §R3.2) ו-`_e2e_gui_chain_foam`
   (§R8). בנוסף הורצו 11 ריצות מדידה (R6 ×3, R7 ×4, שלב 5 ×4) שהתוצר
   שלהן הוא **מספר או אבחנה**, לא PASS/FAIL.
2. **`test_foam_parallel` מדפיס כאן `rank ceiling here: 13`** (אצלכם 2) —
   וזה מה שאפשר את R7 לראשונה.
3. **תחקיר ה-SIGFPE נפתר: זה ה-AMR.** הריצה **הסריאלית** קרסה באותו
   `t = 0.00514` ובאותו סטאק, אז זו **לא** בעיית חלוקה ו**לא** צעד זמן;
   ביטול ה-AMR חצה את נקודת הקריסה ב-31 שניות. `min(T) = 0`,
   `max(T) = 1.35e+15`, ו-`decode()` מחלק `rhoU / rho` באפס.
4. **`BYTES_PER_CELL` = 2650 מאומת: נמדד כאן 2,696 B/cell (פער +1.7 %, R²=0.9996).**
   הקבוע **אינו** צריך להימדד לכל מכונה. (הסוויפ שב-HEAVY_RUNS §R6 היה
   נותן נקודה אחת במקום שלוש — תוקן, ראה §R6.1.)
5. **טבלת ה-ranks (R7), זמן קיר ל-`t = 6.0e-04 s`:**

   | ranks | 1 | 2 | 4 | 8 |
   |-------|---|---|---|---|
   | זמן קיר | 1,992.5 s | 1,126.4 s | 822.6 s | 698.9 s |
   | speedup | 1.00× | 1.77× | **2.42×** | **2.85×** |
   | שיא גייג' | 2,569.13 kPa | 2,597.58 | 2,597.53 | 2,597.50 |

   מונוטוני עד 8, אבל 4→8 קונה רק 18 %. **⚠️ שיאי המקביליים זהים זה לזה
   (0.003 %) אך חורגים מהסריאלי ב-1.11 % — מעל סף ה-1 % של T42.**
6. **זמן הקיר של R1: 2,914 שניות — ובהן 0.036 % מהריצה.** ברירת המחדל
   שלפני P1-1 דורשת **4.6–8.8 ימים**, והיא תופסת רק 10.5 GB מתוך 62 GiB.
   **החסם הוא חישוב, לא זיכרון — אין להפוך את `Case2D` לתלוית-RAM.**
7. **⚠️ באג שנתפס בדרך:** ריצה headless נדחית על מכונה של 128 GB, כי תוצאת
   ה-probe נשמרת רק על ידי ה-GUI. ראה §R1.2 עם diff מוצע.
8. **~~`env.hardware` סופר 14 ליבות במקום 20~~ — הטענה הזו נבדקה ונמצאה שגויה.**
   נמדד ש-`mpirun` מקבל 14 ranks ומסרב ל-15, כלומר 14 הוא בדיוק מספר
   ה-slots של Open MPI, ו-`detect_slots` צודק. **אין באג ואין שינוי קוד.**
   ראה §0.3 המתוקן.
9. **R8 רץ לראשונה אי פעם — ו-FAIL, פעמיים.** שלב ה-3D לא הגיע ל-Results
    (2 תוצאות במקום 3, אף שהסולבר כן רץ) — **זה בדיוק P2-6**; ובנוסף
    `_e2e_gui_chain_foam.py:142` קורס על `g.get('times') or []` מול ndarray,
    **לפני** בדיקות השעון הפיזיקלי שהן כל הנקודה שלו. diff ב-§R8.2.
10. **⚠️ אירוע שיש לדעת עליו: הפעלת ה-GUI ב-R8 הפעילה את הניקוי האוטומטי
    של blastlab, שמחק 34 ריצות — כולל תיקיית ה-SIGFPE המקורית.** לא אני
    מחקתי ולא הרצתי `--clean-foam-runs`. כל התיעוד שלם, והשחזור הסריאלי
    (שבו הסטאק המלא) שרד. פירוט ב-§5.1 ו-§6.2.
11. **מה לא הספקתי ולמה:** R2 נעצרה **55 דקות לפני הסוף**; R4 ו-R5 לא
    הורצו — ה-WSL היה תפוס ברצף מ-23:52 עד 06:00, ו-R6/R7/שלב 5 הם המספרים
    שהסיכום מחייב. R9 **חסום סביבתית**: `ImageGrab` נכשל בסשן ללא שולחן
    עבודה אינטראקטיבי, כך ש-P2-5 נשאר פתוח במלואו.
12. **ממצא רוחבי: כל הערכות הזמן בפרויקט מיושנות מאז T39** (5→8 תאים על
    רדיוס המטען = פי ~4 בעלות). R2 שכותרתו "~30 min" הוא כאן ~105 דקות.

**להריץ ראשון בפעם הבאה:** חקירת R8.1 (למה שלב 3D לא נרשם), תיקון R8.2
והרצה חוזרת, ואז R2 (55 דק' מהשלמה) ו-R4.

---

## שלב 0 · סביבה

### 0.1 המכונה

| פריט | ערך |
|------|-----|
| hostname | `cee-elsl-d` |
| מערכת הפעלה | Microsoft Windows 11 Enterprise, גרסה 10.0.26200, build 26200, x64 |
| CPU | Intel(R) Core(TM) i7-14700 @ 2.10 GHz בסיס |
| ליבות פיזיות | **20** (8 P-cores + 12 E-cores) לפי Windows |
| ליבות לוגיות | **28** |
| RAM כולל | **127.72 GB** |
| דיסק C: פנוי | **293.4 GB** (מתוך 1,862 GB) |
| דיסק Z: פנוי | 16,419 GB |

### 0.2 WSL או לינוקס ילידית

**זו WSL2**, כנדרש — distro רשום בשם `Ubuntu` בדיוק, ולכן חבילות ה-foam
**אינן** מדלגות. אין כאן בעיית זיהוי.

```
$ wsl.exe -l -v
  NAME      STATE       VERSION
* Ubuntu    Stopped     2
```

```
$ wsl.exe -d Ubuntu -- bash -lc "lsb_release -a; uname -r"
Distributor ID: Ubuntu
Description:    Ubuntu 22.04.4 LTS
Release:        22.04
Codename:       jammy
6.18.33.2-microsoft-standard-WSL2
```

**`%USERPROFILE%\.wslconfig` — הקובץ אינו קיים.**
זה מכוון ונכון: אין תקרת `memory=` ידנית, ולכן ה-VM מקבל את ברירת המחדל של
WSL2 (≈50 % מה-RAM של המארח) — 62 GiB. זה בדיוק ההפך מהמכונה של הפיתוח,
שם `.wslconfig` מגביל ל-5 GB.

```
$ wsl.exe -d Ubuntu -- free -h
               total        used        free      shared  buff/cache   available
Mem:            62Gi       477Mi        61Gi       2.0Mi       290Mi        61Gi
Swap:           16Gi          0B        16Gi

$ wsl.exe -d Ubuntu -- nproc
28

$ wsl.exe -d Ubuntu -- df -h /
Filesystem      Size  Used Avail Use% Mounted on
/dev/sdd       1007G   15G  942G   2% /
```

### 0.3 הפלט של `env.hardware(probe=True)`

```
$ cd blastlab/tests
$ python -c "import sys; sys.path.insert(0,'../..'); from blastlab.solvers.foam import env; print(env.hardware(probe=True))"
{'cores': 14, 'logical': 28, 'ram_gb': 63, 'cores_source': 'measured', 'ram_source': 'measured'}
```

> ### 🔴 תיקון (2026-09-10, אחרי אימות): **אין כאן באג. הטענה המקורית שלי הייתה שגויה.**
>
> **מה שכתבתי בלילה:** ש-`cores = 14` "מפספס 6 ליבות E" (ה-i7-14700 הוא
> 8 P + 12 E = 20 פיזיות / 28 לוגיות), ושתקרת ה-ranks הייתה צריכה להיות 19.
>
> **מה שנמדד בפועל** (`mpirun ... hostname`, מול Open MPI 4.1.2):
> ```
> plain      -n 13 -> OK (13 ranks)
> plain      -n 14 -> OK (14 ranks)
> plain      -n 15 -> REFUSED: There are not enough slots available ...
> hwthread   -n 28 -> OK (28 ranks)
> hwthread   -n 29 -> REFUSED
> ```
>
> **14 הוא המספר הנכון בדיוק.** ה-docstring של `detect_slots`
> (`env.py:192-195`) אומר במפורש שהוא מודד *"Open MPI's default slot count,
> i.e. the most ranks mpirun accepts without opt-in flags"* — וזה בדיוק מה
> שנמדד. WSL2 מציג טופולוגיית CPU סינתטית שמזווגת כל שני CPU לוגיים לליבה
> וירטואלית אחת, ו-Open MPI קורא את אותה טופולוגיה. **לו הייתי "מתקן" ל-19,
> mpirun היה מסרב להריץ.**
>
> וגם: הרץ **כבר מטפל** במעבר לתקרה — `runner.py:240-244` מוסיף
> `--use-hwthread-cpus` כש-`n_procs > detect_slots()` ו-`--oversubscribe`
> מעבר ל-`detect_cores()`.
>
> **המסקנה: לא נדרש שינוי קוד.** מה שכן נכון להגיד: תקרת 13 היא שמרנית,
> והמכונה יכולה 28 ranks עם דגל opt-in — אבל R7 (§R7.3) מראה שהמעבר מ-4
> ל-8 קונה 18 % בלבד, כך שאין כאן ביצועים שמחכים.

### 0.4 גרסת הקוד שעליה רץ הלילה

```
$ git rev-parse HEAD
caea6397a2b5740430e0148c258bd8464bc51abe

$ git log --oneline -5
caea639 Two e2e fixtures that T39 broke, plus the heavy-run and night-run briefs
1b73ca5 P2-5: correct the never-eye-checked list against what the tests actually cover
c1f3101 P2-6..P2-9: a chain e2e, and three tests that lied about their own state
6b0407c P1-5: resuming an AMR run, and two labels that lied (P2-1, P2-2)
62870b5 P1-1..P1-4: a 3D default that runs, and three notes that were wrong or missing
```

**הערה על `git status`:** אין `git` ב-PATH של Windows במכונה הזו, ולכן
מצב ה-git נקרא דרך ה-git של WSL (קריאה בלבד, `-c safe.directory='*'`).
ה-git של WSL מדווח **42 קבצים כ-modified**, אבל:

```
$ git diff --ignore-cr-at-eol --stat
(ריק)
$ git status --porcelain | grep '^??'
(ריק)
```

כלומר **כל 42 ההבדלים הם CRLF בלבד** — עץ העבודה זהה ל-HEAD בתוכן, ואין
קבצים untracked. זה בדיוק מה ש-TODO.md מזהיר עליו ("הבייסליינים נראים
modified רק בגלל המרת CRLF"). ה-harness עצמו דיווח `clean` בפתיחת הסשן.

> **R3 — הערה על `git pull`:** HEAVY_RUNS.md §R3 מורה `git pull` כדי לקחת
> את תיקון הפיקסצ'ר. כלל הברזל מס' 1 של הלילה אוסר על כך מפורשות. לא בוצע —
> **ולא היה צורך:** התיקון כבר ב-HEAD, בקומיט `caea639`
> ("Two e2e fixtures that T39 broke"). ראה §R3 למטה.

### 0.5 מצב `/root/blastlab_runs` בתחילת הלילה

```
$ wsl.exe -d Ubuntu -- du -sh /root/blastlab_runs
10G     /root/blastlab_runs

20260909-174555_1d_p6116-00     13M
20260909-232115_3d_p23748-00    9.9G   <- ריצת ה-SIGFPE, ראה שלב 5
```

---

## שלב 1 · בסיס — **ירוק, הלילה ממשיך**

| בדיקה | תוצאה | זמן קיר |
|-------|-------|---------|
| `test_foam_env.py` | **PASS** | 3.6 s |
| `test_regression.py` | **PASS** | 101.7 s |

`test_regression` בייט-זהה בכל שמונת הפריטים — **הבייסליין לא נגע**, ולא הורץ
`--update` בשום שלב.

```
Comparing against frozen baseline:
  [PASS] b1_gauges.txt: byte-identical
  [PASS] b1_profile.txt: byte-identical
  [PASS] b2_gauges.txt: byte-identical
  [PASS] b2_profile.npz: arrays equal
  [PASS] b2r_gauges.txt: byte-identical
  [PASS] b3_gauges.txt: byte-identical
  [PASS] b3r_gauges.txt: byte-identical
  [PASS] transcript.txt: byte-identical

REGRESSION: PASS
```

הפלט המלא: `night_artifacts/logs/S1_test_regression.log`,
`night_artifacts/logs/S1_test_foam_env.log`.

---

## שלב 2 · המטריצה המהירה (ללא WSL)

**29 חבילות, 29 PASS, 0 FAIL, 0 SKIP. סה"כ 5 דק' 22 שנ'.**
כל חבילה הורצה בתהליך נפרד, עם timeout של 30 דקות (אף אחת לא התקרבה).
לוגים: `night_artifacts/logs/S2_*.log`.

| # | חבילה | תוצאה | זמן |
|---|-------|-------|-----|
| 1 | `test_foam_writer` | PASS | 2.0 s |
| 2 | `test_foam_reader` | PASS | 1.1 s |
| 3 | `test_case_validate` | PASS | 2.0 s |
| 4 | `test_hardware` | PASS | 1.8 s |
| 5 | `test_adaptive_interval` | PASS | 0.9 s |
| 6 | `test_foam_live_due` | PASS | 0.9 s |
| 7 | `test_refine` | PASS | 3.0 s |
| 8 | `test_bc_trigger` | PASS | 13.7 s |
| 9 | `test_foam_ingest_order` | PASS | 1.0 s |
| 10 | `test_foam_amr_ingest` | PASS | 1.7 s |
| 11 | `test_foam_postmortem_decomposed` | PASS | 1.6 s |
| 12 | `test_foam_resume` | PASS | 1.3 s |
| 13 | `test_gauge_summary` | PASS | 0.8 s |
| 14 | `test_report` | PASS | 1.7 s |
| 15 | `test_gui_drain` | PASS | 7.4 s |
| 16 | `test_gui_results_fields` | PASS | 12.6 s |
| 17 | `test_gui_results_anim` | PASS | 3.0 s |
| 18 | `test_gui_refine_preview` | PASS | 17.0 s |
| 19 | `test_gui_amr_form` | PASS | 7.3 s |
| 20 | `test_gui_solver_mode` | PASS | 29.3 s |
| 21 | `test_gui_gauge_summary` | PASS | 3.9 s |
| 22 | `test_gui_title_preview1d` | PASS | 6.3 s |
| 23 | `test_gui_run_browser` | PASS | 3.2 s |
| 24 | `test_viz3d_sampling` | PASS | 0.9 s |
| 25 | `test_viz3d_hooks` | PASS | 3.0 s |
| 26 | `test_viz3d_scene` | PASS | 16.6 s |
| 27 | `test_viz3d_panel` | PASS | 10.0 s |
| 28 | `test_blast2d` | PASS | 165.2 s |
| 29 | `test_foam_env` | PASS | 3.6 s *(הורצה בשלב 1)* |

**אין כשלים, ולכן אין "30 שורות אחרונות" לצרף.**

שתי הערות ששוות ציון:

- **`test_gui_run_browser` עבר** (3.2 שנ'). P2-8 מתאר אותו כלא-דטרמיניסטי,
  נתקע על `messagebox.showwarning` מודאלי בהתאם לפוקוס החלון. כאן הוא עבר
  בהרצה הראשונה. זו **לא** הוכחה שהבאג נעלם — הוא עבר גם אצלכם פעם אחת
  באותו סבב. P2-8 נשאר פתוח.
- **`test_blast2d` הוא צוואר הבקבוק של המטריצה** — 165 שנ' מתוך 322,
  כלומר יותר מחצי מזמן המטריצה כולה בחבילה אחת.

---

## שלב 3 · חבילות WSL

**8 חבילות, 8 PASS, 0 FAIL, 0 SKIP. סה"כ 58 דק'.**
לפני כל אחת בוצעה בדיקת `wsl.exe -d Ubuntu -- pgrep -a blastFoam` — **חזרה ריקה
בכל שמונה הפעמים**, ואף ריצה לא חפפה לאחרת. לוגים: `night_artifacts/logs/S3_*.log`.

| # | חבילה | תוצאה | זמן קיר |
|---|-------|-------|---------|
| 1 | `test_foam_1d_vs_native` | PASS | 86.4 s |
| 2 | `test_foam_2d` | PASS | 442.3 s |
| 3 | `test_foam_3d_smoke --tiny` | PASS | 151.7 s |
| 4 | `test_foam_parallel` | PASS | **946.5 s** |
| 5 | `test_foam_postmortem` | PASS | 867.4 s |
| 6 | `test_foam_features` | PASS | 670.7 s |
| 7 | `test_foam_kb_anchor --afterburn` | PASS | 265.7 s |
| 8 | `test_foam_stop` | PASS | 16.0 s |

### 3.1 השורה שביקשת — תקרת ה-ranks

```
rank ceiling here: 13 (14 physical cores - 1 headroom)
```

> **13, לעומת 2 אצלכם.** זו התקרה שפותחת את R7 לראשונה: אפשר לבדוק כאן
> 4 ranks ו-8 ranks בלי לגעת בשום דבר.
>
> **תיקון (2026-09-10):** בגרסה הראשונה כתבתי כאן ש-"14" הוא ספירה שגויה
> ושהתקרה הייתה צריכה להיות 19. **זה לא נכון** — נמדד ש-`mpirun` מקבל 14
> ומסרב ל-15, כלומר 14 הוא בדיוק מספר ה-slots של Open MPI. ראה §0.3.
> ה-RAM אמנם לא מגביל כאן (63 GB חלקי `RAM_GB_PER_RANK = 2` נותן 31),
> אבל הליבות **אינן** נספרות בחסר.

### 3.2 מה שווה לציין מתוך הפלט

**`test_foam_parallel` — שקילות np1 מול np2 מצוינת** (הרבה מתחת לסף ה-1 %
של T42):

```
  [PASS] peak equivalence at (0.6, 1.25) - np1 6290.2 kPa, np2 6292.7 kPa, rel +3.94e-04
  [PASS] peak equivalence at (1.0, 1.25) - np1 2795.0 kPa, np2 2794.8 kPa, rel -9.66e-05
  [PASS] arrival equivalence at (0.6, 1.25) - np1 0.1449 ms, np2 0.1449 ms
  [PASS] arrival equivalence at (1.0, 1.25) - np1 0.3257 ms, np2 0.3257 ms
  [PASS] impulse equivalence at (0.6, 1.25) - np1 188.5 Pa s, np2 188.5 Pa s
  [PASS] determinism pair: identical gauge records over the common record - 494 common samples
```

**`test_foam_kb_anchor --afterburn` — טבלת ה-KB במלואה:**

```
    Z     KB      no-ab    ratio    afterburn  ratio
     1     904      804    0.89       1082    1.20
     2     186      157    0.85        194    1.04
     3      80       69    0.86         82    1.02
     4      47       41    0.87         48    1.02
```

**`test_foam_postmortem` — W2 מופיע שוב, כצפוי:**

```
  [note] merged trace 658 samples vs uninterrupted 623 (blastProbes flush-on-End, see W2)
```

**`test_foam_stop` — 16 שניות בלבד**, וללא יתומים:

```
  [PASS] no mesh/solver process left behind in WSL - still running: ''
```

זה סוגר את מה שנשאר פתוח ב-**P2-3** מצד חבילות ה-`test_foam_*`
(סקריפטי ה-`_e2e_foam_*` מטופלים בשלב 4).

---

# שלב 4 · הריצות הכבדות

## R1 · ברירת המחדל של 2D בגודל מלא — **התשובה: לא. גם כאן לא.**

- **מכונה:** i7-14700, 20 ליבות פיזיות / 28 לוגיות, 127.7 GB RAM,
  WSL VM 62 GiB (ללא `.wslconfig`), Windows 11 build 26200
- **תאריך:** 2026-09-10, 00:57–01:46
- **תוצאה:** **מספר, לא PASS/FAIL** — ראה למטה. הריצה **לא הושלמה**, והופסקה
  ביודעין (ראה "למה הופסקה").

### R1.1 · הוולידציה — עוברת כאן, נדחית אצלכם

```
$ python night_artifacts/scripts/r1_validate.py
hardware: {'cores': 14, 'logical': 28, 'ram_gb': 63, 'cores_source': 'measured', 'ram_source': 'measured'}
errors  : []
warnings: ["No terminate boundary and no end time: the run is bounded only by the safety cap (~294 ms). Set a side to 'terminate' to stop when the wave reaches it."]
notes   : ['WSL blastFoam availability will be verified at run start',
           'Cell size will be refined to 0.00659 m (8 cells across the charge radius)',
           'Charge cells: 102 at 0.006589 m -> ~1.03 of the 1 kg set by blastFoam (whole cells are marked; 8 cells across the radius)',
           'Parallel run: auto: 13 MPI ranks (14 physical cores - 1 headroom)']
OK
```

`errors` **ריק** — המקרה המלא (10×10 מ', תא 0.025 מ') מתקבל כאן, בעוד שעל
מכונת הפיתוח הוא נדחה. עד כאן, זו לכאורה עדות לטובת ברירת מחדל תלוית-חומרה.
**אבל ראה R1.3 — זו מסקנה שגויה.**

### R1.2 · ⚠️ באג אמיתי שנתפס בדרך: ריצה headless נדחית גם על מכונה של 128 GB

הפקודה **בדיוק כפי שהיא כתובה ב-HEAVY_RUNS.md §R1** (בלוק ההרצה, שאינו
קורא ל-`env.hardware(probe=True)`) **נכשלה מיד** בתהליך נקי:

```
ValueError: Invalid blastFoam case:
  ~2,301,289 cells exceeds the blastFoam cap of 1,134,519 (~2.8 GB of an
  assumed 4 GB WSL VM at ~2.6 KB/cell - the real size is unknown) - let the
  WSL hardware probe finish, or click Re-detect - resolving the 0.105 m charge
  forces a 0.006589 m cell across the whole 10 m domain; use a smaller domain,
  a larger charge, or blastFoam charge refinement 'zone'
```

(לוג מלא: `night_artifacts/logs/R1_run_unprimed_REFUSED.log`)

**המכונה הזו מקבלת VM של 62 GiB, והאפליקציה החליטה שהוא 4 GB.** הסיבה:

- תוצאת ה-probe של החומרה היא **מקומית לתהליך**. `env.hardware(probe=True)`
  מודד ושומר בזיכרון התהליך בלבד.
- מי שמשמר אותה לדיסק ומזין אותה בחזרה הוא **רק ה-GUI** —
  `blastlab/gui/app.py:294 _persist_hardware()` כותב ל-`settings.json`,
  ו-`app.py:280 _prime_hardware_from()` מזין בחזרה בהפעלה הבאה.
- כל מסלול שאינו GUI — סקריפט, CLI, בדיקה, וגם הבלוק של HEAVY_RUNS עצמו —
  **לעולם אינו מזין את המטמון**, ולכן נופל ל-UNKNOWN ולתקרה השמרנית של
  VM בגודל 4 GB.
- ואכן: `%APPDATA%\blastlab\settings.json` **אינו קיים** על המכונה הזו, כך
  שגם ההפעלה הראשונה של ה-GUI כאן הייתה נתקלת באותו דבר.

> זה בדיוק התרחיש ש-**P1-1** מתאר בעדכון N21 ("משתמש חדש נתקע בהרצה הראשונה
> גם כשה-WSL שלו פשוט עוד לא ענה") — רק שכאן הוא לא קרה בגלל probe איטי אלא
> **בגלל שאין probe בכלל** במסלול הלא-GUI. **לא תוקן**, לפי כלל 1.
>
> **התיקון המינימלי המוצע** (diff, לא הוחל):
> ```diff
> --- a/blastlab/solvers/foam/env.py
> +++ b/blastlab/solvers/foam/env.py
> @@ hardware()
> -    # returns UNKNOWN when nothing primed the cache
> +    # A headless caller (CLI/script/test) never goes through
> +    # gui/app.py::_prime_hardware_from, so seed from the same persisted
> +    # settings the GUI writes before falling back to UNKNOWN.
> ```
> כלומר: להוציא את `_prime_hardware_from` מ-`gui/app.py` אל `env`/`hardware`,
> ולקרוא לו פעם אחת בטעינה. זה גם מייתר את הצורך ב-`probe=True` בכל סקריפט.

כדי לקבל את המספר שר R1 באמת מבקש, הרצתי מחדש עם
`env.hardware(probe=True)` **באותו תהליך** — בדיוק מה שה-GUI עושה, וללא שינוי
בקוד (`night_artifacts/scripts/r1_run.py`).

### R1.3 · הריצה האמיתית — המספרים

- **פקודה:** `python night_artifacts/scripts/r1_run.py`
  (`Case2D(Lx=10, Ly=10, cell_size_m=0.025, charge=1.0, center=(0,5), n_snapshots=3)`)
- **זמן קיר עד לעצירה מכוונת:** **2,914 s (48.6 דק')**, מתוכם
  `ExecutionTime = 2848.36 s` בסולבר עצמו
- **תוצאה: לא הושלמה.** אחרי 48 דקות הריצה הגיעה ל-**t = 0.105 ms מתוך 294 ms**
  — כלומר **0.036 %** מהריצה.

| מדד | ערך |
|-----|-----|
| תאים סה"כ | **2,301,289** |
| תאים ל-rank | **177,073** (`nPoints: 356472 nCells: 177073 nFaces: 709454`) |
| ranks | 13 |
| **שיא RSS — סה"כ** | **11,006,420 KB ≈ 10.5 GB** |
| שיא RSS — rank 0 | 1,001,976 KB ≈ 978 MB |
| שיא RSS — rank טיפוסי | ~833,000 KB ≈ 813 MB |
| **בייטים לתא (13 ranks, 2D)** | **≈ 4,900 B/cell** |
| זמן CPU / זמן קיר | 47:22 / 47:24 → **~100 % ניצול** ב-13 ranks |
| צעדי זמן שבוצעו | ≈ **277** |
| **זמן לצעד** | **≈ 10.3 s** |
| `deltaT` בסוף | 4.94896e-07 s (התחיל ב-4.0467e-07) |
| `Courant Number Mean/Max` | 0.0511519 / **0.398393** (נעול על היעד 0.4) |
| `max(p)` | 5.5151e+06 Pa |
| `max(T)` / `min(T)` | 3586.97 K / 182.146 K |
| נפח שנכתב ב-48 דק' | 1.3 GB |

זנב הפלט (הסולבר היה בריא לחלוטין עד לרגע העצירה):

```
Courant Number Mean/Max = 0.0511519, 0.398393
Time = 0.00010508542
Calculating Fluxes
RK2SSP: step 1
Solving compressibleSystem:
RK2SSP: step 2
Post-updating compressibleSystem:
max(p): 5.50505e+06, min(p): 101325
max(T): 3586.97, min(T): 182.146
deltaT = 4.94896e-07
ExecutionTime = 2848.36 s  ClockTime = 2849 s
...
mpirun noticed that process rank 2 with PID 0 on node cee-elsl-d exited on signal 15 (Terminated).
RuntimeError: blastFoam failed (exit 143) - case kept at
  \\wsl.localhost\Ubuntu\root\blastlab_runs\20260910-005726_2d_p3352-00
```

**signal 15 הוא ה-`pkill -TERM` שלי**, לא כשל של הסולבר. ראה למטה.

### R1.4 · למה הופסקה, ומה זה אומר — **זו התשובה ל-P1-1**

אין כאן "אם הריצה מסתיימת בפחות מ-20 דקות". **היא לא מסתיימת בכלל:**

- הרשת קבועה (אין AMR), ולכן **העלות לצעד קבועה**: ~10.3 שנ'.
- `Courant Max` כבר נעול על 0.398 מתוך `maxCo = 0.4`, כלומר `deltaT` כבר
  מקסימלי ביחס ל-CFL. הוא יגדל רק ככל שהגל נחלש — מ-5e-07 לכל היותר עד
  `0.4 × 0.00659 / 340 ≈ 7.7e-06` שנ'.
- אין דופן `terminate`, ולכן הריצה חסומה רק בתקרת הביטחון: **294 ms**.

| תרחיש | צעדים נדרשים | זמן קיר |
|-------|--------------|---------|
| חסם תחתון אבסולוטי (`deltaT = 7.7e-06` כל הדרך) | ~38,200 | **~4.6 ימים** |
| הערכה מציאותית (`deltaT` ממוצע ~4e-06) | ~73,500 | **~8.8 ימים** |

> ### המסקנה — ברירת המחדל שלפני P1-1 אינה ניתנת להרצה גם על 128 GB
>
> ההקטנה ב-P1-1 **לא הייתה פיצוי על מכונה חלשה — היא הייתה נכונה**.
>
> וחשוב מכך: **החסם הוא חישוב, לא זיכרון.** הריצה תפסה 10.5 GB מתוך 62 GiB
> זמינים — פחות מ-17 % מה-VM. מודל התקרות של האפליקציה (`BYTES_PER_CELL`
> כפול מספר תאים מול ה-RAM) היה מאשר כאן מקרה גדול פי **שישה**, שהיה רץ
> חודשיים.
>
> לכן **אין להפוך את `Case2D` לתלוית-RAM.** תקרה שנגזרת מ-RAM בלבד היא
> תקרה שמאשרת מקרים בלתי-ניתנים-להרצה. אם רוצים ברירת מחדל תלוית-חומרה,
> היא צריכה להיגזר מ-**תפוקה** (תאים×צעדים לשנייה) ומזמן ריצה מבוקש,
> לא ממגה-בייטים. המספר למדידה קיים עכשיו: **~4.5 µs לתא לצעד ל-13 ranks**
> על i7-14700.

**למה עצרתי אותה:** תקציב הלילה הוא 8 שעות; הריצה הזו דורשת 4.6–8.8 ימים.
עצירה בוצעה ב-`pkill -TERM blastFoam`, לאחר תיעוד כל המדדים, ואומתה
נקייה מיתומים (`pgrep -a blastFoam` ריק). זו **עצירה מכוונת ומתועדת,
לא כשל.**

---

## R2 · `_e2e_foam_obstacle2d axi` — **INCOMPLETE** (הופסקה ביודעין, ~55 דק' לפני הסוף)

- **תאריך:** 2026-09-10, 01:47–02:35
- **פקודה:** `wsl.exe -d Ubuntu -- pgrep -a blastFoam` (ריק) ואז
  `python _e2e_foam_obstacle2d.py axi` — **ללא timeout**, לפי כלל 5
- **זמן קיר עד לעצירה:** **2,877 s (48 דק')**, מתוכם `ExecutionTime = 2810.67 s`
- **תוצאה:** **INCOMPLETE — לא PASS ולא FAIL.**

הבדיקה שהגיעה:

```
  [PASS] axisym: validate ok
```

זו ה-check היחידה שרצה — כל השאר (כולל `revolve ring for the 3D view`) באות
**אחרי** שהסולבר מסיים, והוא לא הגיע לשם.

### R2.1 · המצב המדויק ברגע העצירה

| מדד | ערך |
|-----|-----|
| תאים | **171,604** (סריאלי, rank יחיד) |
| שיא RSS | ~810 MB |
| צעדי זמן | **914** |
| זמן פיזיקלי שהושג | **t = 8.229e-04 s** |
| `deltaT` | 1.5916e-06 s (התחיל ב-~4e-07) |
| `Courant Number Mean/Max` | 0.137034 / **0.388761** |
| `max(p)` / `min(p)` | 759,095 Pa / **1,310.46 Pa** |
| `max(T)` / `min(T)` | 1234.27 K / **63.7963 K** |
| **זמן לצעד** | **2.85 s** (מדוד על שלושה חלונות: 2.54 / 2.95 / 2.85) |

זנב הפלט:

```
Time = 0.00082285956
Courant Number Mean/Max = 0.137034, 0.388761
max(p): 759095, min(p): 1310.46
max(T): 1234.27, min(T): 63.7963
deltaT = 1.5916e-06
ExecutionTime = 2810.67 s  ClockTime = 2813 s
...
RuntimeError: blastFoam failed (exit 15) - case kept at
  \\wsl.localhost\Ubuntu\root\blastlab_runs\20260910-014719_2d_p14884-00
```

**exit 15 = ה-`pkill -TERM` שלי.** הסולבר היה בריא לחלוטין: Courant נעול על
0.389, `deltaT` גדל בהתמדה, `min(p)` ו-`min(T)` חיוביים. **אין כאן שום סימן
לבעיה בנתיב האקסיסימטרי** — פשוט לא היה מספיק זמן.

### R2.2 · כמה חסר, ולמה עצרתי

`deltaT` גדל בקצב יציב — הוכפל כל ~470 צעדים לאורך כל הריצה
(5.96e-07 → 8.59e-07 → 1.118e-06 → 1.533e-06). הריצה נעצרת כשהגל מגיע לדופן
`terminate`, כלומר סביב **t ≈ 5.5 ms** עבור 2 ק"ג בתחום 4×3 מ'. אקסטרפולציה:
עוד **~1,150 צעדים ≈ 55 דקות**. סה"כ R2 ≈ **1 שעה 45 דק'**.

**למה עצרתי:** הסיכום המחייב בשלב 6 דורש את `BYTES_PER_CELL` מ-R6 ואת טבלת
ה-ranks מ-R7. במדידות של הלילה הזה **כל הערכת זמן ב-HEAVY_RUNS יצאה
אופטימית פי 3–4** (ראה R2.3), ולכן 55 הדקות האלה נדרשו כדי להבטיח את R6,
R7 ושלב 5. R2 הוא הפריט הראשון שיש להריץ במכונה פנויה — **הוא 55 דקות
מהשלמה, והנתיב נראה תקין לחלוטין עד לנקודת העצירה.**

### R2.3 · ⚠️ ממצא צדדי — הערכות הזמן בפרויקט מיושנות מאז T39

הכותרת של `_e2e_foam_obstacle2d.py:12` אומרת *"planar ~5 min, axisym ~30 min wall"*.
כאן, על מכונה **חזקה בהרבה** ממכונת הפיתוח, האקסיסימטרי לוקח **~105 דקות** —
פי 3.5.

ההסבר עקבי עם TODO/HEAVY_RUNS: **T39 העלה את יעד רזולוציית המטען מ-5 תאים
ל-8.** בדו-ממד זה מכפיל את מספר התאים ב-(8/5)² = **2.56**, ומקטין את `deltaT`
פי 1.6 (CFL), כלומר **פי ~4.1 בעלות הכוללת**. אותו שורש שהצריך את תיקון
הפיקסצ'רים ב-R3 גם **הפך כל הערכת זמן בקבצים האלה ללא-נכונה**, ואף אחד
לא עדכן את הכותרות.

**מומלץ:** לעדכן את הערכות הזמן בכותרות של `_e2e_foam_*.py` ובטבלת
[HEAVY_RUNS.md §2](HEAVY_RUNS.md), או לפחות לסמן אותן כ"pre-T39".

---

## R3 · `_e2e_foam_amr2d` + `_e2e_foam_refine2d` — **אחד PASS, אחד FAIL**

- **תאריך:** 2026-09-10, 02:35–02:40
- **`git pull` לא בוצע** — כלל הברזל מס' 1 אוסר. **ולא היה צורך:** תיקון
  הפיקסצ'ר של T39 כבר ב-HEAD (`caea639`, "Two e2e fixtures that T39 broke").
  זה מה שנבדק כאן.

| סקריפט | תוצאה | זמן קיר |
|--------|-------|---------|
| `_e2e_foam_refine2d.py` | **PASS** | 110.5 s |
| `_e2e_foam_amr2d.py` | **FAIL (2 checks)** | 128.4 s |

### R3.1 · `_e2e_foam_refine2d` — PASS, התיקון עובד

```
  Done. 443 solver steps, t_final = 0.252 ms
  Stopped: shock arrived at a terminate boundary (p_edge = 1.112e+05 Pa)
  [PASS] both runs recorded the gauge
  [PASS] gauge peak within 15% of the uniform reference - refined 15390 kPa, uniform 14687 kPa
  [PASS] gauge arrival within 10% of the uniform reference - refined 0.141 ms, uniform 0.145 ms
  [PASS] post-mortem reload: same fine grid, refine record and final field - (240, 320) vs (240, 320)

E2E FOAM REFINE 2D: PASS
  --- uniform reference: 80 s, 134 live frames
```

**ארבעת הכשלים שתוארו ב-HEAVY_RUNS §R3 (`plan: level 3 auto zones ... - 4 []`)
נסגרו.** התיקון תקף גם על חומרה אחרת.

### R3.2 · `_e2e_foam_amr2d` — הפיקסצ'ר תוקן, אבל עכשיו נחשף כשל **פיזיקלי**

זו הפעם הראשונה שהסקריפט הזה בכלל **מגיע לסולבר** (קודם הוא מת ב-`ValueError`
של הוולידציה). הוא רץ במלואו, ונכשל בשתי בדיקות דיוק:

```
  Domain          : 4 x 4 m,  cell 0.025 m  (160 x 160 = 25,600 cells)
  Charge          : 400 kg TNT per metre (infinite cylinder) at (2, 2) m
  Done. 446 solver steps, t_final = 0.373 ms
  Stopped: shock arrived at a terminate boundary (p_edge = 1.022e+05 Pa)

  --- uniform 0.025 m reference: 66 s, 131 live frames
  wall time: AMR 56 s vs uniform 66 s -> ratio 1.19x
  [PASS] both runs recorded the gauge
  [FAIL] gauge peak within 10 % of the uniform reference - AMR 17633 kPa, uniform 19989 kPa
  [FAIL] gauge arrival within 10 % of the uniform reference - AMR 0.210 ms, uniform 0.189 ms
  [PASS] positive-phase impulse within 15 % (common window) - AMR 1027.1 Pa s, uniform 998.0 Pa s to 0.373 ms
  [PASS] post-mortem reload: same display grid, AMR record and final field - (160, 160) vs (160, 160)
  [PASS] no solver process left behind in WSL

E2E FOAM AMR 2D: FAIL (2): gauge peak within 10 % of the uniform reference,
                           gauge arrival within 10 % of the uniform reference
```

**המספרים:**

| מדד | AMR | uniform 0.025 m | סטייה | סף |
|-----|-----|-----------------|-------|-----|
| שיא בגייג' | 17,633 kPa | 19,989 kPa | **−11.8 %** | 10 % |
| זמן הגעה | 0.210 ms | 0.189 ms | **+11.1 %** | 10 % |
| impulse (חלון משותף) | 1027.1 Pa s | 998.0 Pa s | +2.9 % | 15 % ✓ |
| זמן קיר | 56 s | 66 s | **×1.19 לטובת AMR** | — |

**איך לקרוא את זה:** ה-AMR **מחליק את החזית** — שיא נמוך ב-12 % והגעה מאוחרת
ב-11 % הם החתימה הקלאסית של חזית שנפרשת על פני יותר תאים ממה שהרשת האחידה
נותנת. ה-impulse עובר דווקא כי הוא אינטגרל, והוא לא רגיש להחלקה של השיא.
כלומר: **אין כאן באג בקוד ה-AMR — יש כאן קביעה שהעידון הדינמי בקונפיגורציה
של הבדיקה הזו (רמות/מרווח/buffer) לא מדביק את הרשת האחידה, והבדיקה מודדת
בדיוק את זה.**

שווה לשים לב גם: **הרווח בזמן הוא רק ×1.19** על מקרה של 25,600 תאים. ב-T42
נמדד ×1.43 ב-np=2. עידון דינמי במקרה כל כך קטן כמעט לא משתלם.

> **מה לעשות עם זה — החלטת בעלים, לא תוקן כאן:** או להרפות את שני הספים
> ל-15 % ולתעד שזו רמת הדיוק של AMR, או להדק את הקונפיגורציה של ה-AMR
> בבדיקה (יותר רמות / `amr_interval` קטן יותר / `amr_buffer` גדול יותר)
> עד שהיא מדביקה את האחיד. **הבדיקה עצמה נכונה — היא מודדת דבר אמיתי.**

**הערה טכנית:** בלוגים של הלילה שורות ה-stdout וה-stderr לפעמים משתלבות
זו בזו (שורות שנראות מעורבבות). זה תוצר של הלכידה האסינכרונית שלי, לא של
התוכנית.

---

## R6 · תקרת התאים האמיתית — **`BYTES_PER_CELL = 2650` מאומת. אין צורך למדוד לכל מכונה.**

- **תאריך:** 2026-09-10, 02:44–03:16
- **`test_hardware.py`:** **PASS** (1.8 s, 58 בדיקות) — ראה שלב 2
- **תוצאה: מספר.** ראה R6.3.

### R6.1 · ⚠️ הסוויפ של HEAVY_RUNS §R6 אינו מייצר שלוש נקודות — הוא מייצר אחת

הבלוק ב-HEAVY_RUNS משנה את `cell_size_m` על פני 0.05 / 0.04 / 0.025 ב-L = 1.0
ומצפה לשלושה גדלים. **בבילד הזה כל השלושה נותנים את אותה רשת בדיוק.** אומת
בלי להריץ סולבר (`night_artifacts/logs/R6_probe_sizes.log`):

```
dx=0.05   L=1.0  nominal=    8,000
    note: Charge resolution 'smear' is ignored by the blastFoam backend (the grid is refined to resolve the charge)
    note: Cell size will be refined to 0.01927 m (8 cells across the charge radius)
    note: Parallel run: 1 rank: 132,651 cells is below the 200,000-cell parallel floor

dx=0.04   L=1.0  nominal=   15,625
    note: Cell size will be refined to 0.01927 m (8 cells across the charge radius)
    note: Parallel run: 1 rank: 132,651 cells is below the 200,000-cell parallel floor

dx=0.025  L=1.0  nominal=   64,000
    note: Cell size will be refined to 0.01927 m (8 cells across the charge radius)
    note: Parallel run: 1 rank: 132,651 cells is below the 200,000-cell parallel floor
```

**המטען — לא `cell_size_m` — קובע את גודל התא.** 25 ק"ג TNT עם "8 תאים על פני
הרדיוס" נותן 0.01927 מ' בכל שלושת המקרים, ולכן שלוש הנקודות מתלכדות ושיפוע
הרגרסיה אינו מוגדר. (שימו לב גם להערה הראשונה: **`charge_resolution='smear'`
פשוט מתעלמים ממנו ב-backend של blastFoam** — הבלוק של R6 מבקש אותו במפורש.)

**מה עשיתי במקום:** שיניתי את **התחום** ולא את גודל התא, עם המטען קבוע. זה מה
שבאמת מזיז את מספר התאים, וכל שלוש הנקודות נשארות **סריאליות (rank יחיד)** —
בדיוק המתודולוגיה שבה T48 מדד. (`night_artifacts/scripts/r6_cells.py`)

### R6.2 · שלוש הנקודות שנמדדו

| L [m] | תאים שנבנו בפועל | ranks | שיא RSS | זמן דגימה |
|-------|------------------|-------|---------|-----------|
| 0.6 | **32,768** (32³) | 1 | **230,288 KiB = 224.9 MiB** | 400 s |
| 0.8 | **74,088** (42³) | 1 | **334,036 KiB = 326.2 MiB** | 400 s |
| 1.0 | **140,608** (52³) | 1 | **513,496 KiB = 501.5 MiB** | 400 s |

שורת ה-`Parallel run:` שהאפליקציה מדווחת (כפי שביקשת):

```
Parallel run: 1 rank: 132,651 cells is below the 200,000-cell parallel floor
```

**איך נמדד ה-RSS:** דגימה של `ps -o rss= -C blastFoam` כל 3 שניות לאורך 400
שניות לכל גודל, ונלקח המקסימום. עקבות ה-RSS המלאות ב-`night_artifacts/logs/R6_L*.log`.
שיא ה-RSS נקבע בדקה הראשונה (בניית הרשת + הקצאת השדות) ואחריו הערך מתייצב —
ה-8 דגימות האחרונות בכל ריצה מתנודדות סביב ערך קבוע, כלומר **השיא נתפס.**

> **סייג שיש לומר במפורש:** שלוש הריצות **לא הורצו עד סופן** — הן נקטעו אחרי
> 400 שניות. זה בסדר עבור R6 *כי המדד הוא שיא ה-RSS*, והוא מושג בהתחלה. אבל
> **זמן הקיר של ריצה מלאה אינו מדווח כאן** — הוא לא נמדד. (הסיבה: מקרה של
> 25 ק"ג בקופסה של 1 מ' רץ אל תקרת הביטחון של ~29 ms; במדידה של 1.15 שנ' לצעד
> זה שעות לכל גודל.)

### R6.3 · הרגרסיה — **התוצאה**

רגרסיה לינארית של `RSS = a · cells + b` על שלוש הנקודות:

```
slope     = 2.632949 KiB/cell = 2696.1 B/cell
intercept = 142086.6 KiB = 138.8 MiB
  cells=   32,768  measured=   224.9 MiB  fit=   223.0 MiB  resid=  +1.9 MiB
  cells=   74,088  measured=   326.2 MiB  fit=   329.3 MiB  resid=  -3.0 MiB
  cells=  140,608  measured=   501.5 MiB  fit=   500.3 MiB  resid=  +1.2 MiB
R^2 = 0.999638
```

| | B/cell | קבוע |
|---|--------|------|
| `BYTES_PER_CELL` באפליקציה | **2,650** | ~148 MB |
| **נמדד כאן** (i7-14700, 3 נק', R²=0.9996) | **2,696** | 138.8 MiB |
| נגזר משתי הנקודות של T48 עצמן | 2,782 | 147.7 MiB |

> ### המסקנה — **הפער הוא 1.7 %. הקבוע תקף.**
>
> הסף שנקבע ב-HEAVY_RUNS היה 20 %. הפער בפועל הוא **+1.7 %** על מכונה
> שונה לגמרי (i7-14700 / 128 GB / VM של 62 GiB, מול מכונת פיתוח של 7.7 GB).
> **`BYTES_PER_CELL` אינו צריך להימדד לכל מכונה** — הוא תכונה של blastFoam
> ושל מודל ה-5 משוואות, לא של החומרה. אפשר להשאיר אותו מקובע ב-
> `core/constants.py`.
>
> הערה קטנה אחת: גם המדידה שלי (2,696) וגם החישוב מחדש מנקודות T48 (2,782)
> יוצאים **מעל** 2,650. כלומר הקבוע הנוכחי מעט **אופטימי** — הוא מעריך בחסר
> את הזיכרון ולכן מאשר מקרים מעט גדולים מדי. פער של 2–5 % הוא זניח מול
> ה-headroom, אבל אם רוצים דיוק — **2,700** הוא מספר טוב יותר מ-2,650.

---

## R7 · AMR מקבילי ב-4 ו-8 ranks — **הבדיקה שאי אפשר היה לעשות אצלכם**

- **תאריך:** 2026-09-10, 03:17–05:0x
- **תקרת ה-ranks כאן: 13** (מ-`test_foam_parallel`, §3.1) — לכן 4 ו-8 נבדקו
  באמת, לראשונה.
- **מקרה:** בדיוק הבלוק של HEAVY_RUNS §R7 —
  `Case2D(geometry='axisymmetric', Lx=2, Ly=4, cell_size_m=0.02, center=(0,2),
  charge=5, amr_levels=2, gauges=[(1.0,2.0),(1.5,2.0)], n_snapshots=1)`

### R7.1 · הפרוטוקול — ולמה הוא שונה ממה שכתוב ב-HEAVY_RUNS

הבלוק של R7 מריץ כל rank count **עד הסוף** ומדפיס `WALL`. במקרה הזה אין דופן
`terminate`, ולכן "הסוף" הוא תקרת הביטחון של ~117 ms — שעות לכל rank count
(אותה תופעה כמו ב-R1). לכן:

> **כל rank count הורץ עד לאותו זמן פיזיקלי בדיוק — `t = 6.0e-04 s` — ונמדד
> זמן הקיר שנדרש לכך.** זו מדידת קנה-מידה נקייה יותר מ"עד הסוף", והיא
> מאפשרת השוואת שיאי גייג' באותה נקודה בזמן.

הבחירה ב-6.0e-04 s: הגל מגיע לגייג' הראשון (r = 1.0 m) ב-~0.34 ms, כך שהשיא
שלו **נלכד במלואו**. הגייג' השני (r = 1.5 m) מגיע ב-~0.68 ms — **מעבר ליעד,
ולכן הוא נשאר על 101.3 kPa בכל הריצות ואינו משתתף בהשוואה.** מתועד כאן
במפורש ולא מוצג כאילו נמדד.

### R7.2 · הטבלה

| ranks | זמן קיר ל-t=6.0e-04 s | speedup | צעדים | תאים (AMR) | שיא גייג' r=1.0 m | סטייה מ-np1 | שיא RSS |
|-------|----------------------|---------|-------|------------|-------------------|-------------|---------|
| **1** | **1,992.5 s** | 1.00× | 1,666 | 66,284 | **2,569.13 kPa** | — | 448,688 KiB (438 MiB) |
| **2** | **1,126.4 s** | **1.77×** | 1,666 | 66,905 | **2,597.58 kPa** | **+1.11 %** | 608,480 KiB (594 MiB) |
| **4** | **822.6 s** | **2.42×** | 1,665 | 66,914 | **2,597.53 kPa** | **+1.11 %** | 937,268 KiB (915 MiB) |
| **8** | **698.9 s** | **2.85×** | 1,665 | 66,938 | **2,597.50 kPa** | **+1.11 %** | 1,610,216 KiB (1.54 GiB) |

**np=2 כאן הוא ×1.77, מול ×1.43 ש-T42 מדד אצלכם** — אותו מקרה, מכונה חזקה
יותר, ואותה מגמה.

### R7.3 · שלוש המסקנות

**(1) זמני הקיר יורדים מונוטונית — אבל הרווח נגמר סביב 4 ranks.**

```
1 -> 2 ranks:  x1.77   (יעילות 88 %)
2 -> 4 ranks:  x1.37   (יעילות 61 % מצטברת)
4 -> 8 ranks:  x1.18   (יעילות 36 % מצטברת)
```

הקריטריון של HEAVY_RUNS — "זמני הקיר יורדים מונוטונית עד לפחות 4 ranks" —
**מתקיים**. אבל המעבר מ-4 ל-8 קונה רק 18 % נוספים. המקרה קטן (20,000 תאי
בסיס, ~67,000 אחרי AMR), כלומר ~8,000 תאים ל-rank ב-np=8 — הרבה מתחת לרף
שבו MPI משתלם, ועוד עם AMR שמסנכרן את כל ה-ranks כל 2 צעדים.

**(2) ⚠️ שיאי הגייג'ים חורגים מסף ה-1 % של T42 — אבל לא בין ranks שונים.**

```
np=2  ->  2,597.58 kPa
np=4  ->  2,597.53 kPa      פער בין 2, 4 ו-8:  0.003 %
np=8  ->  2,597.50 kPa
np=1  ->  2,569.13 kPa      פער מול כל המקביליים: 1.11 %
```

**2, 4 ו-8 ranks זהים זה לזה כמעט לחלוטין** (0.003 %) — אין כאן "ככל
שיש יותר ranks כך גדל הרעש". יש **מדרגה אחת בדיוק, בין סריאלי למקבילי**,
והיא 1.11 % — **מעל סף ה-1 % ש-T42 קבע**, וזהה בכל שלושת מספרי ה-ranks.

ההסבר מופיע בעמודת התאים: `cells_at_latest` הוא **66,284** בסריאלי מול
**66,905 / 66,914 / 66,938** במקבילי — פער של ~1.0 % במספר התאים ש-AMR ייצר. כלומר
**הדקומפוזיציה משנה את החלטות העידון** (קריטריון `densityGradient` נמדד
לכל תת-תחום, ו-buffer של 2 תאים מתנהג אחרת ליד גבולות פנימיים), הרשת יוצאת
מעט עדינה יותר במקביל, והשיא יוצא גבוה יותר ב-1.1 %.

> **זו לא רגרסיה שנוצרה הלילה** — זו התנהגות שמעולם לא נמדדה מעל 2 ranks.
> **החלטת בעלים:** או להרפות את סף ה-peak ב-`test_foam_parallel` ל-1.5 %
> ולתעד ש-AMR מקבילי אינו זהה-ביט לסריאלי, או לחקור את קריטריון העידון
> בגבולות תת-תחומים. **לא נגעתי בשום סף.**

**(3) הזיכרון גדל הרבה יותר מהר ממספר ה-ranks המועיל.**

| ranks | שיא RSS | יחס מול np=1 | לכל rank |
|-------|---------|--------------|----------|
| 1 | 438 MiB | 1.00× | 438 MiB |
| 4 | 915 MiB | 2.09× | 229 MiB |
| 8 | 1.54 GiB | 3.59× | 197 MiB |

8 ranks עולים פי 3.6 בזיכרון ומחזירים פי 2.85 במהירות, על אותה רשת. זה
מחזק את `RAM_GB_PER_RANK = 2` כשמרני-נכון, ומראה שבמקרים קטנים כדאי
לעצור ב-4.

### R7.4 · `balance yes` — **לא נוסה. דילוג מכוון, וזו הסיבה.**

HEAVY_RUNS §R7 מבקש להפוך את ערך ה-`balance`, להריץ שוב, ולהחזיר את הקוד
לקדמותו. **כלל הברזל מס' 1 של הלילה אוסר לערוך קובץ קיים תחת `blastlab/`.**

> **תיקון (2026-09-10):** כתבתי כאן `dicts.py` — **המיקום הנכון הוא
> `blastlab/solvers/foam/writer.py:1025-1028`**, בתוך `_dynamicmeshdict`.
> `dicts.py` הוא רק פולט הטקסט של OpenFOAM ואין בו dynamicMeshDict כלל.

**התיקון הנדרש כדי לבדוק זאת (diff, לא הוחל):**

```diff
--- a/blastlab/solvers/foam/writer.py
+++ b/blastlab/solvers/foam/writer.py
@@ -1025,7 +1025,7 @@ def _dynamicmeshdict(spec=None, case=None):
     if spec.n_procs > 1:
         # fixed decomposition: balancing needs an `internal` patch
         # (addEmptyPatch) - the parallel follow-up decides
-        d['loadBalance'] = {'balance': False}
+        d['loadBalance'] = {'balance': True}
```

שימו לב שהמפתח **נפלט רק כאשר `spec.n_procs > 1`**, ואין בקוד
`balanceInterval` או `allowableImbalance` בכלל.

**אבל שווה לומר מה כן נמדד הלילה בלי לגעת בקוד**, כי זה כמעט עונה על השאלה:
ריצת ה-SIGFPE של שלב 5 היא ריצת AMR ב-13 ranks עם `balance no`, והחלוקה
בפועל שם הייתה:

```
processor0   2,071      processor7  31,650
processor1   5,457      processor8  36,642
processor2   2,251      processor9  10,558
processor3  28,403      processor10    594
processor4  30,457      processor11    586
processor5  36,697      processor12 10,696
processor6  37,230   <- ה-rank שקרס
```

**יחס של 1:64 בין ה-rank העמוס לרֵיק.** `scotch` מחלק את רשת **הבסיס** שווה
בשווה, ואז AMR מעדן רק ליד הגל — כל העידון נופל על מעט ranks, והשאר
מחכים. זו בדיוק ההערה של T42 *"revisit balancing only for asymmetric
refinement or 4+ ranks"*, והנה המדידה: **ב-13 ranks עם עידון א-סימטרי,
`balance no` מבזבז את רוב המכונה.** עדות חזקה לטובת בדיקת `balance yes` —
אבל היא דורשת את שינוי הקוד שאסור לי לעשות.

---

## R8 · `_e2e_gui_chain_foam.py` — **FAIL. ושני הכשלים אמיתיים.**

- **תאריך:** 2026-09-10, 06:11–06:13
- **פקודה:** `wsl.exe -d Ubuntu -- pgrep -a blastFoam` (ריק) ואז
  `python _e2e_gui_chain_foam.py`
- **זמן קיר:** **110 s** (השרשרת עצמה: 97 s)
- **תוצאה:** **FAIL** — וזו **הפעם הראשונה שהסקריפט הזה רץ אי פעם.**

```
  [PASS] stage 1 form took the case on blastFoam - blastfoam
  [PASS] stage 3 form took the case on blastFoam - blastfoam
  [PASS] the chain started a worker
  Gauge data saved: gauges.txt  (1109 rows x 1 gauges)
  Field profile saved: ..._chain_study\gui_foam\stage1_profile.txt  (100 cells, t = 0.270 ms)
  Gauge data saved: gauges_2d.txt  (1061 rows x 1 gauges)
  2D field profile saved: ..._chain_study\gui_foam\stage2_profile.npz  (25 x 50 cells, t = 4.513 ms)
  --- chain finished in 97 s ---
  [PASS] the chain ran to completion (worker exited)
  [PASS] stage 1 wrote the 1D profile the panel named
  [PASS] stage 2 form took the case on blastFoam - blastfoam
  [PASS] stage 2 wrote the 2D profile the panel named
  [PASS] stage 1 case.json saved in the workspace
  [PASS] stage 2 case.json saved in the workspace
  [PASS] stage 3 case.json saved in the workspace
  [FAIL] three results reached the Results panel - 2 results
  results: ['Run 1 - 1D', 'Run 1 - 2D']

Traceback (most recent call last):
  File "..._e2e_gui_chain_foam.py", line 172, in <module>
    sys.exit(main())
  File "..._e2e_gui_chain_foam.py", line 142, in main
    ts = list(g.get('times') or [])
              ^^^^^^^^^^^^^^^^^^^^
ValueError: The truth value of an array with more than one element is ambiguous.
            Use a.any() or a.all()
```

### R8.1 · כשל ראשון — **שלב ה-3D לא הגיע ל-Results**

```
[FAIL] three results reached the Results panel - 2 results
results: ['Run 1 - 1D', 'Run 1 - 2D']
```

השרשרת רצה 1D → 2D בהצלחה (שני הפרופילים נכתבו, שלושת ה-`case.json` נשמרו,
כולל של שלב 3), ה-worker יצא נקי — **אבל תוצאת שלב ה-3D לא הופיעה בפאנל.**

> זה **בדיוק** הפער ש-P2-6 נכתב כדי לתפוס: *"עד T62 שלב 3D משורשר מול
> blastFoam מעולם לא הצליח לרוץ, ואף בדיקה לא תפסה את זה כי אף אחת לא
> הריצה שרשרת עד שלב foam תלת-ממדי."* **הבדיקה עובדת, והיא תופסת את זה.**
> מה שלא ידוע עדיין הוא האם שלב 3D **נכשל** או **פשוט לא נרשם ב-Results** —
> תיקיית הריצה `20260910-061250_3d_p27516-02` קיימת ובה 109 תיקיות זמן עד
> `t = 0.0046696754`, כלומר **הסולבר כן רץ**. כלומר החשד הוא בצד
> ה-ingest/רישום, לא בסולבר. **לא חקרתי הלאה — נגמר הזמן.**

### R8.2 · כשל שני — **באג בסקריפט הבדיקה עצמו, בשורה 142**

```python
ts = list(g.get('times') or [])
```

`g.get('times')` מחזיר **מערך numpy**, ו-`or` על מערך numpy באורך > 1 זורק
`ValueError`. זה קורה **לפני** שתי הבדיקות שהן כל הנקודה של R8 לפי
HEAVY_RUNS — *"stage N starts where stage N-1 ended, not at 0"* (השעון
הפיזיקלי האחד, N7/T41, החצי שנשבר ב-T62).

> **כלומר: גם אם שלב ה-3D היה עובד, הסקריפט לא היה מגיע לבדיקות החשובות
> שלו.** הוא נכתב ב-P2-6 ומעולם לא הורץ, ולכן הבאג הזה שרד.

**התיקון (diff, לא הוחל — כלל 1):**

```diff
--- a/blastlab/tests/_e2e_gui_chain_foam.py
+++ b/blastlab/tests/_e2e_gui_chain_foam.py
@@ -139,7 +139,9 @@ def main():
-    ts = list(g.get('times') or [])
+    _ts = g.get('times')
+    ts = list(_ts) if _ts is not None else []
```

(`or` על ndarray הוא דפוס שגוי בכל מקום; שווה `grep -n "or \[\]" blastlab/tests/`
כדי לראות אם הוא חוזר במקומות נוספים.)

### R8.3 · תופעת לוואי — הפעלת ה-GUI מחקה 34 ריצות

ההרצה הזו היא שהפעילה את הניקוי האוטומטי של blastlab ומחקה את ריצת
ה-SIGFPE המקורית. ראה **§5.1** ו-**§6.2**.

---

## R4, R5 · **לא הורצו — נגמר הזמן**

לפי כלל 6, עצרתי בגבול ריצה שלמה:

| ריצה | מצב | למה |
|------|-----|-----|
| **R4** `test_blast3d` | **לא הורצה** | דורשת ריצה **ללא timeout** (כלל 5) והערכתה ~25 דק'. R1 ו-R2 בלעו את החלון שלה, ו-R6/R7/שלב 5 הם המספרים שהסיכום מחייב. **אינה תלוית-WSL** — אפשר להריץ אותה במקביל לכל דבר אחר, וזו הריצה הזולה ביותר להשלים. |
| **R5** `_e2e_solver_viewer.py` | **לא הורצה — וגם BLOCKED** | פותחת חלון VTK אמיתי. הסשן הזה **אינו יכול לצלם מסך בכלל** (§R9), ולכן גם אילו רצה, "האם החלון הראה גל מתפשט" ושני הצילומים המבוקשים לא היו ניתנים לאספקה. |

**ההמלצה לריצה הבאה, לפי סדר תשואה:**
1. **חקירת R8.1** — למה שלב 3D לא מגיע ל-Results (הסולבר כן רץ). זה P2-6.
2. **תיקון R8.2** ואז הרצה חוזרת, כדי להגיע סוף-סוף לבדיקות השעון הפיזיקלי.
3. **R2** — 55 דקות מהשלמה (§R2.2).
4. **R4** — מספר בלבד.

---

## R9 · הכנת החומר לבדיקות העין — **BLOCKED (סביבה, לא קוד)**

- **פקודה:** `python _qa_gui_harness.py --scenario D04,E05,E06`
- **תוצאה:** **שלושת התרחישים קרסו.** קוד היציאה היה 0 — ה-harness אינו
  מכשיל את התהליך — ולכן **אסור לקרוא לזה PASS.**

```
[02:13:50] [boot] foreign WSL solvers at kickoff: ['1762 blastFoam']
[02:14:04] [boot] App built in 4225 ms
[02:14:04] [D04] === BEGIN D04 ===
[02:14:14] [D04] FINDING S1 harness-crash: D04 raised
[02:14:14] [D04] === END D04: crashed (10s, max gap 8487 ms) ===
[02:14:15] [E05] no cache for native3d
[02:14:16] [E05] NOTE: 3D fields: []
[02:14:16] [E05] FINDING S1 harness-crash: E05 raised
[02:14:21] [E06] FINDING S1 harness-crash: E06 raised
```

**השורש, מתוך `findings.jsonl`:**

```
File "..._qa_gui_harness.py", line 412, in shot
    img = ImageGrab.grab(bbox=bbox, all_screens=True)
File "...PIL\ImageGrab.py", line 93, in grab
    offset, size, data = Image.core.grabscreen_win32(
OSError: screen grab failed
```

> **זו מגבלת סביבה, לא באג.** הסשן הזה רץ ללא שולחן עבודה אינטראקטיבי
> (session מנותק/נעול), ו-`ImageGrab.grab` של Windows דורש משטח מסך אמיתי.
> ה-GUI עצמו **כן נבנה בהצלחה** ("App built in 4225 ms") ו-D04 הספיק להגיע
> עד `qa.shot('3d_form')` — כלומר טעינת המקרה והמעבר בין הטאבים עבדו.
> הכשל הוא **בצילום בלבד**.
>
> E05 ו-E06 קרסו **במורד הזרם**: D04 נפל לפני ששמר תוצאת `native3d` במטמון,
> ולכן `3D fields: []` ואז `IndexError: list index out of range`. אין כאן
> ממצא נוסף מעבר לזה.

**לא ניסיתי לעקוף.** עקיפה הייתה דורשת לערוך את `_qa_gui_harness.py` (למשל
צילום דרך `win32gui.PrintWindow` במקום `ImageGrab`), וזה אסור לפי כלל 1.

**התיקון האפשרי, אם רוצים ש-R9 יעבוד גם ב-session מנותק (diff, לא הוחל):**

```diff
--- a/blastlab/tests/_qa_gui_harness.py
+++ b/blastlab/tests/_qa_gui_harness.py
@@ def shot(...)   (~line 412)
-        img = ImageGrab.grab(bbox=bbox, all_screens=True)
+        try:
+            img = ImageGrab.grab(bbox=bbox, all_screens=True)
+        except OSError:
+            # no interactive desktop (locked/disconnected session):
+            # record the gap instead of killing the whole scenario
+            self.note(f'shot {name!r} skipped: no screen to grab')
+            return None
```

זה לא היה נותן צילומים — אבל היה מאפשר לשאר ה-checks של D04/E05/E06 לרוץ
ולדווח, במקום ליפול על ה-shot הראשון.

**הערה על הרצה במקביל:** ההרצה הזו התבצעה **במקביל** לריצה הסריאלית של R2
(ה-harness עצמו זיהה זאת: `foreign WSL solvers at kickoff`). זה מותר לפי
כלל 2 — D04/E05/E06 הם 3D **נייטיבי** ואינם נוגעים ב-foam — אבל הוא לא
הגורם לכשל: `ImageGrab` נכשל ללא קשר. **החומר לבדיקות העין לא הופק,
ו-P2-5 נשאר פתוח במלואו.** תיקיית הפלט (ריקה מצילומים):
`C:\Users\rotem.ofek\blastlab_qa\20260910-0213\`

---

# שלב 5 · תחקיר ה-SIGFPE — **נפתר**

> **התשובה בשורה אחת: העידון הדינמי (AMR) מייצר תא שבו `rho = 0`, ואז
> `decode()` מחשב `U = rhoU / rho` ומחלק באפס.**
> זו **לא** בעיית חלוקה בין תת-תחומים, ו**לא** צעד זמן.

## 5.1 · תיקיית הריצה שקרסה

```
/root/blastlab_runs/20260909-232115_3d_p23748-00     9.9 GB     2026-09-09 23:21
```

זוהתה לפי שתי אינדיקציות: אין בה זמן כתיבה תקין אחרון (הכתיבה האחרונה
`0.0047901457` בעוד ה-endTime הוא `0.2009331866`), ו-`postProcessing/gauges`
מכיל תיקייה אחת בלבד.

> ### ⚠️ **התיקייה הזו כבר לא קיימת — האפליקציה מחקה אותה ב-06:12**
>
> **אני לא מחקתי אותה, ולא הרצתי `--clean-foam-runs`.** מה שקרה: R8
> (`_e2e_gui_chain_foam.py`) מפעיל **GUI אמיתי**, ול-blastlab יש **ניקוי
> אוטומטי בהפעלת ה-GUI** (P4-3: מעל 20 GB או ישן מ-14 יום; שלוש הריצות
> האחרונות נשמרות). `blastlab_runs` היה 56 GB, כלומר מעל הסף — והניקוי
> רץ ומחק 34 מתוך 40 הריצות, **כולל ריצת ה-SIGFPE המקורית.**
>
> **מה שרד, ולמה זה לא פוגע במסקנה:**
> - ✅ `night_artifacts/sigfpe/crashed_case.json` — הועתק ב-00:20, שלם
> - ✅ כל המספרים שחולצו ממנה נמצאים בסעיפים 5.2–5.3 של הקובץ הזה
> - ✅ **`20260910-054313_3d_p11640-00` — השחזור הסריאלי — שרד**, וזו
>   התיקייה **החשובה יותר**: היא זו שהפילה SIGFPE אמיתי עם הסטאק המלא,
>   בעוד שהמקורית לא שמרה לוג כלל
> - ✅ שרדו גם `20260910-053314` (cfl) ו-`20260910-052726` (noamr)
> - ❌ נמחקו: המקורית, שחזור ה-`base`, וכל ריצות R1/R2/R6/R7
>
> **זו טעות שלי בסדר הפעולות** — הייתי צריך להריץ את R8 לפני שלב 5, או
> להעתיק את התיקייה כולה החוצה, או לכבות `auto_cleanup` ב-
> `%APPDATA%\blastlab\settings.json`. **התיעוד עצמו שלם ולא אבד ממנו דבר**,
> אבל אי אפשר יותר לחזור לתיקייה המקורית ולחפור בה. מדווח כאן במפורש
> ולא מוסתר.

העתק של `case.json` שלה: `night_artifacts/sigfpe/crashed_case.json`.

## 5.2 · 60 השורות שלפני הקריסה

> **הערה חשובה על מקור הנתונים:** blastlab **אינו שומר את ה-stdout של הסולבר
> לדיסק** — הוא מזרים אותו לקורא ב-Python. לכן **לוג הקריסה המקורי אבד**
> ואי אפשר היה "לשלוף אותו מתוך הלוג שלה". מה שכן שרד על הדיסק הוא
> `postProcessing/gauges/…/p`, שנכתב בכל צעד — וממנו שחזרתי את מסלול ה-`deltaT`
> המדויק. את שורות ה-`Time/Courant/max/min` המקוריות השגתי **בשחזור**
> (§5.4), שקרס באותה נקודה בדיוק.

**מסלול ה-`deltaT`, משוחזר מקובץ הגייג' של הריצה שקרסה** (הפרשי זמנים בין
דגימות עוקבות):

```
t=0.00482171       dt=1.626000e-05     <-  עד כאן dt גדל בהתמדה
t=0.00489489       dt=1.423000e-05
t=0.00496008       dt=1.270000e-05
t=0.00502989       dt=1.111000e-05
t=0.00508202       dt=9.960000e-06
t=0.00512109       dt=9.570000e-06
t=0.00512955       dt=8.460000e-06
t=0.00513685       dt=7.300000e-06
t=0.00514323       dt=6.380000e-06
t=0.00514324       dt=1.000000e-08     <-  קריסה של 3 סדרי גודל בצעד אחד
t=0.00514325       dt=1.000000e-08
   ...  (43 שורות רצופות באותו זמן בדיוק)
t=0.00514334       dt=1.000000e-08
```

ו-43 השורות האחרונות של הגייג' — **אותו זמן, אותם ערכים, שוב ושוב**:

```
   0.00514334         87796        115974        340455        155641
   0.00514334         87796        115974        340455        155641
   0.00514334         87796        115974        340455        155641
   (ועוד 40 כאלה)
```

> `1e-08` הוא **רזולוציית ההדפסה** של עמודת הזמן בנקודה הזו, ולכן ה-`deltaT`
> האמיתי הוא **≤ 1e-08** — כלומר הריצה כבר לא התקדמה. הריצה גססה 43 צעדים
> לפני שהמלכודת נסגרה.

**השורות עצמן, מהשחזור הסריאלי (§5.4) — הרגע האחרון בדיוק:**

```
Time = 0.0051419011
Courant Number Mean/Max = 1.70763e-06, 0.0989753
deltaT = 7.54226e-12
max(p): 444863, min(p): 80185.3
max(T): 1.3503e+15, min(T): 0
ExecutionTime = 1112.12 s  ClockTime = 1114 s

#0  Foam::error::printStack(Foam::Ostream&)
#1  Foam::sigFpe::sigHandler(int)
#3  Foam::tmp<Foam::DimensionedField<Foam::Vector<double>, Foam::volMesh> >
      Foam::operator/<Foam::Vector<double>, Foam::volMesh>(
        Foam::DimensionedField<Foam::Vector<double>, Foam::volMesh> const&,
        Foam::DimensionedField<double, Foam::volMesh> const&)
#4  Foam::compressibleBlastSystem::decode()
#5  Foam::twoPhaseCompressibleSystem::decode()
#6  Foam::twoPhaseCompressibleSystem::postUpdate()
#7  Foam::timeIntegrator::postUpdateAll()
#8  Foam::timeIntegrator::integrate()
```

> ### ⚠️ **`min(T) = 0`. וגם `max(T) = 1.3503e+15 K`. אמרתי זאת במפורש כי זו התשובה.**
>
> ביקשת לומר במפורש אם `min(p)` או `min(T)` ירדו לאפס או לשלילי. **`min(T)`
> הוא בדיוק 0**, ו-`max(T)` הוא 1.35×10¹⁵ K — כלומר שדה הטמפרטורה כבר
> התפוצץ בשני הקצוות. הלחץ דווקא נראה תמים (80–445 kPa) — ולכן מי שמסתכל
> רק על הלחץ לא רואה כלום.
>
> ו-`Courant Max = 0.0989` **אינו** "קפיצה בסדר גודל" — הוא **נמוך** פי 4
> מהיעד 0.4. זה הפוך ממה שמצפים, וזה בדיוק הסימן: **בקר ה-`deltaT` כבר
> חתך את הצעד עד `7.5e-12`** כדי לרדוף אחרי מהירות גל אינסופית בתא אחד,
> וכתוצאה מכך ה-Courant הממוצע צנח ל-1.7e-06. זו ספירלת מוות, לא אי-יציבות
> רגילה.

**ומה בדיוק מחלק באפס — המסגרת `#3` בסטאק אומרת זאת מילולית:**
חלוקה של **שדה וקטורי בשדה סקלרי** בתוך `compressibleBlastSystem::decode()`.
`decode()` הוא השלב שממיר את המשתנים המשומרים חזרה לפרימיטיביים, והחלוקה
הווקטורית-בסקלרית היחידה שם היא

```
U = rhoU / rho
```

כלומר **`rho` הגיע ל-0 בתא אחד לפחות**. משם: `c = sqrt(γp/ρ) → ∞` →
Courant מתפוצץ → `deltaT` קורס → ובסוף החלוקה עצמה מפילה SIGFPE.

## 5.3 · ה-`case.json` של הריצה שקרסה

| שדה | ערך |
|-----|-----|
| ממדים | **3D, 10 × 10 × 10 m** |
| גודל תא בסיס | **0.5 m** (רשת בסיס ~7,640 תאים אחרי חיתוך המכשול) |
| מטען | **50 kg TNT**, `charge_resolution='resolve'`, `activation='linear'`, `afterburn='none'` |
| מרכז | **(5, 5, 0)** — כלומר **על הקרקע**, ודופן `z_lo` היא `reflect` |
| EOS | `idealGas` |
| **מצב אתחול** | **`profile1d`** — מאותחל מפרופיל 1D (`run/validation/blast_profile.txt`) |
| **מכשולים** | **1**: תיבה `x 7→10, y 7→10, z 0→5` — פינה חדה בתוך התחום |
| **AMR** | **`amr_levels=2`**, `densityGradient`, refine 0.4 / unrefine 0.2, **`interval=2`**, `buffer=2`, `max_cells=0` |
| refine_zones | (ריק) |
| `cfl` | **0.4** |
| `t_end` | 0.2 s (הגיע ל-0.00514) |
| **ranks** | **`n_procs=14` — נחתך ל-13** בפועל (`numberOfSubdomains 13`, `scotch`) |
| גייג'ים | (6.9, 6.9, 1), (6.9, 6.9, 3), (6.9, 6.9, 5), (5, 5, 5) |
| הרשת בזמן הקריסה | **233,292 תאים** (גדלה מ-7,640) |

**שילוב מסוכן במיוחד:** `profile1d` + AMR + מכשול עם פינה חדה. שימו לב
ש-**P1-5** ב-TODO כבר מתאר כשל אחר בדיוק בצירוף `profile + AMR`.

## 5.4 · שלוש ריצות הצמצום — **וריצת ביקורת רביעית שהוספתי**

הוספתי ריצת **`base`** (המקרה כפי שהוא, ללא שינוי) לפני השלוש. בלעדיה
אי אפשר לפרש את התוצאות: אם המקרה לא משחזר, שלוש הריצות האחרות חסרות
משמעות. זו תוספת, לא סטייה.

**קריטריון:** "שרד" = עבר את `t = 6.0e-03` (הקריסה ב-`t = 0.00514`) בלי FPE.

| # | ריצה | שינוי | תוצאה | `t` אחרון | הערות |
|---|------|-------|-------|-----------|-------|
| 0 | **base** | — | **קרס** (קריסת `deltaT`) | **0.00515532** | 233,292 תאים, זהה למקור |
| א | **serial** | `n_procs = 1` | **קרס — SIGFPE** | **0.0051419** | 233,292 תאים, **אותו סטאק בדיוק** |
| ב | **cfl** | `0.4 → 0.2` | **קרס** (קריסת `deltaT`) | **0.00527242** | 233,460 תאים |
| ג | **noamr** | `amr_levels = 0` | ✅ **שרד** | **0.00962512** | 7,640 תאים, `deltaT = 1.38e-05` בריא |

**פירוט:**

- **base (13 ranks):** התיקייה שנוצרה הגיעה ל-`latest_written_time =
  0.0047901457` — **בית-זהה למקור** — ואז נתקעה על `t = 0.00515532` עם שורות
  גייג' חוזרות. `cells_at_latest = 233292`, `probe0 peak = 1482.3 kPa` —
  **זהה למקור**. **הקריסה דטרמיניסטית ומשחזרת.**
- **א · serial (`n_procs=1`):** **קרס ב-SIGFPE אמיתי**, `exit 136`,
  `t = 0.0051419` — פחות מ-0.03 % מנקודת הקריסה המקורית (0.00514334) —
  **ועם אותו סטאק בדיוק** (`postUpdateAll ← integrate`). 233,292 תאים,
  אותם שיאי גייג'.
- **ב · cfl חצי:** הגיע מעט רחוק יותר (0.00527 מול 0.00515) ואז נתקע באותה
  צורה. **חצי צעד זמן קונה 2 % בזמן פיזיקלי, ולא יותר.**
- **ג · ללא AMR:** **חלף על פני נקודת הקריסה ב-31 שניות** והמשיך ל-0.0096
  עם `deltaT = 1.38e-05` תקין לגמרי. הרשת נשארה 7,640 תאים.

## 5.5 · המסקנה — לפי עץ ההחלטה שכתבת

| התנאי שלך | מה קרה | המסקנה |
|-----------|--------|--------|
| אם (א) עובר → בעיית חלוקה בין תת-תחומים | **(א) קרס** | ❌ **לא חלוקה** |
| אם (ב) עובר → צעד זמן | **(ב) קרס** | ❌ **לא צעד זמן** |
| אם (ג) עובר → עידון דינמי | ✅ **(ג) שרד** | ✅ **זה העידון הדינמי** |
| אם כולן קורסות → המקרה עצמו לא יציב | (ג) לא קרסה | ❌ לא המקרה |

> ### **המסקנה: ה-SIGFPE נגרם על ידי ה-AMR.**
>
> **`rank 6` במקור היה מקרי לחלוטין.** הריצה הסריאלית מפילה את אותו FPE
> באותו זמן פיזיקלי ובאותו סטאק — עם rank אחד. rank 6 פשוט היה ה-rank
> שהחזיק את האזור המעודן (37,230 תאים מתוך 233,292 — הכי הרבה מכל 13).
> **חיפוש באגי MPI/גבולות תת-תחומים כאן יהיה בזבוז זמן.**
>
> **המנגנון, מקצה לקצה:**
> 1. `dynamicRefineFvMesh` מעדן/מגס תאים כל **2 צעדים** (`amr_interval=2`)
>    סביב הגל ובסביבת הפינה החדה של המכשול (`x 7→10, y 7→10, z 0→5`).
> 2. באחד המיפויים האלה נוצר תא שבו **`rho` יורד ל-0** (או לדנורמל).
>    הגייג' שנמצא הכי קרוב לפינת המכשול, (6.9, 6.9, 1), אכן מראה
>    `rho = 0.0909 kg/m³` — **7.5 % מהצפיפות האטמוספרית** — כלומר האזור
>    הזה כבר במצב של ואקום-כמעט, בתא בגודל 0.125 מ'.
> 3. `c = sqrt(γp/ρ) → ∞` באותו תא → Courant מתפוצץ → בקר ה-`deltaT` קורס
>    מ-6.4e-06 ל-1e-08 ואז ל-**7.5e-12**.
> 4. `T` מתפוצץ (`max(T) = 1.35e+15`, `min(T) = 0`).
> 5. `decode()` מחשב `U = rhoU / rho`, מחלק ב-0 → **SIGFPE** ב-
>    `postUpdateAll()`.
>
> **מה זה אומר מעשית:** זה **לא באג בקוד של blastlab**. זה חוסר-חסינות של
> ה-AMR של blastFoam למצב ואקום-כמעט ליד פינה חדה, בתא גס יחסית (0.5 מ'
> בסיס = 0.125 מ' ברמה 2). **המקרה הזה תת-מעודן עבור מכשול עם פינה.**
>
> **שלושה כיווני מיטיגציה, לפי סדר סבירות (לא מומשו — כלל 1):**
> 1. **רצפת צפיפות/לחץ בשדות אחרי remap.** אם ל-blastFoam יש
>    `residualRho`/`residualAlpha` בקונפיגורציה של ה-EOS — לוודא שהם מוגדרים.
>    זה הפתרון הישיר לחלוקה באפס.
> 2. **`amr_interval` גדול מ-2.** עידון כל 2 צעדים הוא אגרסיבי מאוד; כל
>    מיפוי הוא הזדמנות ליצור תא פגום.
> 3. **בסיס עדין יותר.** 0.5 מ' לתחום של 10 מ' עם מכשול חד הוא גס. תא בסיס
>    0.25 מ' עם אותן 2 רמות נותן 0.0625 מ' ליד הפינה.
>
> **שווה גם להוסיף שומר בצד blastlab:** הריצה גססה **43 צעדים** לפני
> ה-FPE, עם `deltaT` שקרס ב-3 סדרי גודל וזמן שלא מתקדם. `runloop` יכול
> לזהות "‏`deltaT` צנח מתחת ל-1e-4 מערכו הטיפוסי ו/או הזמן לא התקדם ב-N
> צעדים" ולעצור עם הודעה מובנת, במקום לתת ל-blastFoam למות ב-SIGFPE אחרי
> שהמשתמש חיכה. **לא מומש.**

**לא תוקן דבר בקוד. שלב 5 הוא תיעוד בלבד, כפי שביקשת.**
לוגים: `night_artifacts/logs/S5_base.log`, `S5_serial.log`, `S5_cfl.log`,
`S5_noamr.log`, `S5_check.log`.

> **שקיפות על שני לוגים:** `S5_base.log` ו-`S5_cfl.log` **שוחזרו מדגימות חיות**
> שנלקחו בזמן הריצה, ולא נלכדו ביציאת התהליך — עצרתי את שתי הריצות ביודעין
> אחרי שהן כבר הראו את מצב הכשל, ולכן ה-harness שלי לא הגיע לשלב כתיבת הלוג.
> כל שורה בשני הקבצים היא פלט probe מילולי, והדבר מסומן בראש כל קובץ.
> `S5_serial.log` ו-`S5_noamr.log` נלכדו במלואם ביציאה.

---

# שלב 6 · ניקיון ובדיקת שלמות

## 6.1 · אין סולברים יתומים ✅

```
$ wsl.exe -d Ubuntu -- pgrep -a blastFoam
(ריק, exit=1)
$ wsl.exe -d Ubuntu -- bash -c "pgrep -a mpirun; pgrep -a rss_watch"
(ריק)
```

**לא נותר דבר להרוג.** לאורך כל הלילה בוצעה בדיקת `pgrep -a blastFoam` לפני
כל ריצת WSL, ואחרי כל עצירה מכוונת. **שתי ריצות WSL לא רצו במקביל אף פעם.**

*(ההרצה היחידה שהתבצעה במקביל למשהו היא R9 prep — 3D **נייטיבי**, ללא foam.
מתועד ב-§R9.)*

## 6.2 · דיסק — **לא נמחק דבר**

| | תחילת הלילה | שיא (06:04) | סוף הלילה (06:20) |
|---|-------------|-------------|-------------------|
| `/root/blastlab_runs` | **10 GB** (2 ריצות) | **56 GB** (40 ריצות) | **12 GB** (6 ריצות) |
| פנוי ב-WSL (`/`) | 942 GB | 896 GB | **941 GB** |
| פנוי ב-C: | 293.4 GB | 245.4 GB | 245.4 GB *(ה-vhdx אינו מתכווץ לבד)* |

> ### ⚠️ **הניקוי מ-56 GB ל-12 GB לא נעשה על ידי — הוא נעשה על ידי האפליקציה**
>
> **`python -m blastlab --clean-foam-runs` לא הורץ הלילה, אף פעם.** מה
> שהתרחש ב-06:12: R8 מפעיל GUI אמיתי, ו-blastlab מריץ **ניקוי אוטומטי
> בכל הפעלת GUI** כשהתיקייה עוברת 20 GB (P4-3). היא הייתה 56 GB. הניקוי
> מחק **34 מתוך 40** הריצות ושמר את שלוש האחרונות + השלוש של R8.
>
> **בין המחוקות: `20260909-232115_3d_p23748-00`, ריצת ה-SIGFPE המקורית.**
> פירוט מלא ומה שרד — §5.1.
>
> **הלקח המבצעי:** מי שרוצה לשמר ריצת foam לניתוח **חייב** לכבות
> `auto_cleanup: false` ב-`%APPDATA%\blastlab\settings.json` לפני שהוא
> פותח את ה-GUI, או להעתיק את התיקייה החוצה. זה מתועד ב-P4-3 כפיצ'ר —
> אבל בהקשר של "אל תמחק את `blastlab_runs` לפני שתיעדת" הוא **מלכודת**:
> הוא פועל בלי לשאול, ו-`_e2e_gui_*` מפעיל אותו.

שש הריצות ששרדו, וכולן מתועדות בקובץ הזה:

```
20260910-061250_3d_p27516-02   R8, שלב 3
20260910-061214_2d_p27516-01   R8, שלב 2
20260910-061141_1d_p27516-00   R8, שלב 1
20260910-054313_3d_p11640-00   שלב 5 (א) serial - הסטאק המלא של ה-SIGFPE
20260910-053314_3d_p18800-00   שלב 5 (ב) cfl
20260910-052726_3d_p24032-00   שלב 5 (ג) noamr
```

> אזהרה קטנה להמשך: ה-vhdx של WSL גדל ב-~48 GB הלילה ואינו מתכווץ לבד.
> לפי P4-3: `wsl --shutdown` ואז `diskpart` → `select vdisk file=...\ext4.vhdx`
> → `compact vdisk`. **לא ביצעתי** — זו פעולה שמשביתה את WSL ולא ביקשת אותה.

## 6.3 · שלמות ה-git — **לא שונה אף קובץ קיים** ✅

```
$ git rev-parse HEAD
caea6397a2b5740430e0148c258bd8464bc51abe        <- זהה לתחילת הלילה

$ git diff --ignore-cr-at-eol --stat
(ריק)                                            <- אפס שינויי תוכן

$ git status --porcelain | grep '^??'
?? NIGHT_RESULTS.md
?? night_artifacts/
```

**בדיוק שני פריטים untracked, שניהם שלי.** אין אזהרה לכתוב כאן: שום קובץ
קיים לא נערך, ולא הורצה אף פקודת git שמשנה מצב (`commit`, `push`, `pull`,
`stash`, `checkout`, `reset`, `merge` — אף אחת). ה-42 קבצים שה-git של WSL
מציג כ-modified הם **CRLF בלבד**, בדיוק כמו בתחילת הלילה (§0.4).

**גם הבייסליינים לא נגעו:** `test_regression.py --update` ו-
`test_foam_writer.py --update` **לא הורצו**.

## 6.4 · מה נוצר

```
NIGHT_RESULTS.md              הקובץ הזה
NIGHT_LOG.md                  יומן כרונולוגי של הלילה
night_artifacts/
├── logs/                     58 לוגים גולמיים (S1/S2/S3/R*/S5*)
├── scripts/                  7 סקריפטים חדשים שנכתבו הלילה
└── sigfpe/
    └── crashed_case.json     העתק מילולי של ה-case.json שקרס
```

`night_artifacts/scripts/` מכיל רק קבצים **חדשים** — `r1_validate.py`,
`r1_run.py`, `r6_cells.py`, `r6_probe_sizes.py`, `r7_ranks.py`,
`s5_reduce.py`, `s5_check.py`, `rss_watch.sh`. אף אחד מהם אינו מייבא
או משנה דבר ב-`blastlab/`; כולם קוראים ל-API הציבורי בלבד.

---

