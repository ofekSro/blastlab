# HEAVY_RUNS.md — ריצות כבדות למכונה חזקה יותר

> ## ⚠️ תוצאות שרשרת במסמך הזה אינן תקפות (נוסף 18.09)
>
> כל מה שכאן שתלוי ב**כדור האש** — impulse, משך הפאזה החיובית, הלם משני,
> התנהגות מאוחרת — רץ לפני תיקון **B0**, שבו `lambda.<phase>` לא נכתב מעולם
> לשלב שמוזן מ-profile. ‏blastFoam מיזג את התוצרים חזרה לרֵאקטנטים הלא-מגיבים
> (‏Murnaghan עם `K0 0`) ואיפס אותם ל-`pRef`: נמדד 4.43 MPa שנכנסו,
> 101,298 Pa שיצאו.
>
> **חזית ההלם עצמה סבירה** — היא נישאת בתאי אוויר שאותחלו נכון — אבל כל כמות
> שתלויה באנרגיה של כדור האש אינה תקפה.
>
> בנוסף, כל מספר **מקבילי בשדה קרוב** כאן נושא את N5-7: ‏`method scotch`
> העריך ביתר ב-7 % ב-Z=0.175 וב-13…28 % ב-Z=0.075.
>
> להרצה מחדש: ראו `TODO.md` → N5-4, N5-7. נקודת ייחוס תקפה: `REFERENCE_CHAIN.md`.


> **למה הקובץ הזה קיים.** מחשב הבית הזה הוא **7.7 GB RAM סה"כ, 4 ליבות פיזיות
> (12 לוגיות)**, ו-WSL מקבל 5 GB מתוכם (`%USERPROFILE%\.wslconfig`, מוגדר כך
> במכוון — אי אפשר להעלות בלי להרעיב את Windows). כמה דברים בפרויקט **לא ניתנים
> להכרעה כאן**: הם או לא נכנסים לזיכרון, או שהם תופסים את המכונה לשעות.
> הקובץ מרכז בדיוק אותם, עם פקודה מדויקת, מה למדוד ומה נחשב הצלחה.
>
> **מה זה לא:** זו לא רשימת המשימות. המשימות הפתוחות הן ב-[TODO.md](TODO.md),
> ומה שנעשה ב-[DONE.md](DONE.md). הקובץ הזה הוא רק "מה להריץ על חומרה אחרת".
>
> **הפרומפט להדבקה** נמצא בסוף, בסעיף [§7](#7-הפרומפט-להדבקה).

---

## 1. מה המכונה צריכה

| דרישה | מינימום | למה |
|-------|---------|-----|
| RAM למכונה | **32 GB** (16 GB יעבוד חלקית) | R6 לבד מבקש ~6.1 GB ל-WSL |
| RAM ל-WSL VM | **16 GB** (`memory=16GB` ב-`.wslconfig`) | R1, R6, R7 |
| ליבות פיזיות | **8+** | R7 בודק 4+ ranks, שאי אפשר כאן (התקרה כאן היא 2) |
| דיסק פנוי | **60 GB** | ריצות foam מצטברות ב-`/root/blastlab_runs` |
| זמן | **~6–8 שעות** לכל הרשימה | אפשר לפצל, ראה סדר העדיפויות |

**סביבה (זהה למכונה הזו):**
- WSL2, distro בשם **`Ubuntu`** בדיוק (`env.WSL_DISTRO = 'Ubuntu'`)
- OpenFOAM-9 + blastFoam, כאשר `/root/OpenFOAM/OpenFOAM-9/etc/bashrc` קיים
  (`env.FOAM_BASHRC`), והכלים `blastFoam`, `blockMesh`, `setRefinedFields`,
  `topoSet`, `refineMesh`, `decomposePar`, `reconstructPar` על ה-PATH אחרי
  `source` שלו
- Python 3.12 עם `numpy`, `matplotlib`, `customtkinter`, `pillow`,
  ו-`pyvista` (אופציונלי אבל נדרש ל-R9)
- ffmpeg ב-PATH (ל-R9; `winget install Gyan.FFmpeg`)

**בדיקת שפיות לפני שמתחילים** — חייב לעבור, אחרת כל השאר חסר משמעות:
```
cd blastlab/tests
python test_foam_env.py            # מאתר את WSL ואת blastFoam
python test_regression.py          # חייב להיות ירוק בייט-בייט
```

**כלל ברזל לכל ריצת WSL:** לוודא ש-WSL פנוי לפני כל אחת —
`wsl.exe -d Ubuntu -- pgrep -a blastFoam` חייב לחזור ריק. סולבר זר גורם
ל-`test_foam_stop` ולחבילות כבדות-זיכרון להיכשל כזב.

---

## 2. סדר עדיפויות

אם אין זמן להכל — זה הסדר. R1 ו-R2 הם היחידים שחוסמים **החלטה** פתוחה.

> **⚠️ הערכות הזמן שלמטה היו מלפני T39** (שהעלה את יעד רזולוציית המטען
> מ-5 תאים ל-8, כלומר פי ~4 בעלות של מקרה דו-ממדי). העמודה "נמדד בפועל"
> נוספה ב-2026-09-10 מריצת הלילה, על מכונה של 20 ליבות / VM של 62 GiB.
> ראה `NIGHT_RESULTS.md`.

| # | ריצה | הערכה מקורית | **נמדד בפועל** | למה זה לא כאן |
|---|------|--------------|----------------|----------------|
| **R1** | ברירת המחדל של 2D בגודל מלא | ~40 דק | **4.6–8.8 ימים** ⚠️ | 2.3M תאים ≈ 6.1 GB > 5 GB VM |
| **R2** | `_e2e_foam_obstacle2d axi` | ~30 דק | **~105 דק** | זמן; מעולם לא הושלם |
| **R3** | `_e2e_foam_amr2d` אחרי תיקון | ~5 דק | 2.1 דק (+ refine2d 1.8 דק) | נכשל כאן, צריך אישור על חומרה אחרת |
| **R4** | `test_blast3d` | ~25 דק כאן | *לא הורצה* | זמן; חוסם את המטריצה |
| **R5** | `_e2e_solver_viewer.py` | 10+ דק | *לא הורצה* | מעולם לא הסתיים כאן |
| **R6** | תקרת התאים האמיתית (N17) | ~30 דק | 3×400 שנ' לשיא RSS | כל העניין הוא חומרה אחרת |
| **R7** | AMR מקבילי ב-4 ו-8 ranks | ~60 דק | **~78 דק** (4 ריצות) | התקרה כאן היא 2 ranks |
| **R8** | `_e2e_gui_chain_foam.py` | ~20 דק | **~31 דק** | חדש, טרם רץ אף פעם |
| **R9** | בדיקות עין (P2-5) | ~30 דק | **חסום** — אין שולחן עבודה | דורש עיניים + ParaView + מסך שני |

---

## 3. הריצות

> לכל ריצה: **פקודה**, **מה לתעד**, **מה נחשב הצלחה**.
> תעד גם כשזה עובר — המספרים עצמם הם התוצר, לא רק ה-PASS.

### R1 · ברירת המחדל של 2D בגודל מלא — *חוסמת החלטה*

**רקע:** ב-P1-1 הוחלט להקטין את ברירות המחדל כי המכונה הזו מסרבת להן.
`Case2D` הוקטנה ל-4 מ' ו-`Case3D` ל-1.5 מ'. השאלה הפתוחה: **האם ההקטנה נכונה,
או שהיא רק פיצוי על מכונה חלשה?** אם על מכונה של 32 GB המקרה המלא רץ בזמן שפוי,
כדאי לשקול ברירת מחדל שתלויה בחומרה במקום קבועה.

```
cd blastlab/tests
python - <<'EOF'
import sys; sys.path.insert(0, '../..')
from blastlab.core.case import Case2D, validate_case
from blastlab.solvers.foam import env
print('hardware:', env.hardware(probe=True))
c = Case2D(Lx=10.0, Ly=10.0, cell_size_m=0.025, charge=1.0,
           center=(0.0, 5.0), solver='blastfoam')   # ברירת המחדל שלפני P1-1
r = validate_case(c)
print('errors  :', r.errors)
print('warnings:', r.warnings)
print('notes   :', r.notes)
EOF
```
אם `errors` ריק — להריץ אותו באמת:
```
python - <<'EOF'
import sys, time; sys.path.insert(0, '../..')
from blastlab.core.case import Case2D
from blastlab.solvers import get_solver
from blastlab.solvers.hooks import RunHooks
c = Case2D(Lx=10.0, Ly=10.0, cell_size_m=0.025, charge=1.0,
           center=(0.0, 5.0), solver='blastfoam', n_snapshots=3)
t0 = time.perf_counter()
res = get_solver(2, 'blastfoam')(c, RunHooks())
print(f'WALL {time.perf_counter()-t0:.0f} s  stop={res.stop_reason}')
print('p_peak max [kPa]', res.meta["p_peak"].max()/1e3)
EOF
```

**לתעד:** את הפלט של `env.hardware(probe=True)`; את שלוש הרשימות מהוולידציה;
את מספר התאים ואת התקרה שהוא מדווח; ואם הוא רץ — **זמן הקיר בשניות**, שיא הלחץ,
ו-peak RSS של תהליך ה-blastFoam (`/usr/bin/time -v` או `htop` בזמן הריצה).

**הצלחה:** לא "עבר/נכשל" אלא **מספר**. אם הריצה מסתיימת בפחות מ-20 דקות על
32 GB — זו עדות ש-`Case2D` צריכה להיות תלוית-חומרה ולא 4 מ' קבוע.

---

### R2 · `_e2e_foam_obstacle2d axi` — מעולם לא הושלם

**רקע:** החלק ה-planar עובר כאן. החלק האקסיסימטרי לוקח ~30 דקות ולכן דולג
מאז ומעולם. זה הנתיב **המסוכן** לפי הכותרת של הסקריפט עצמו: `boxToCell` שופט
את הקואורדינטות של הטריז, ואם החיתוך שגוי אף אחד לא ידע.

```
cd blastlab/tests
wsl.exe -d Ubuntu -- pgrep -a blastFoam      # חייב להיות ריק
python _e2e_foam_obstacle2d.py axi
```

**לתעד:** את כל שורות ה-`[PASS]`/`[FAIL]`, את זמן הקיר, ואת השורה
`revolve ring for the 3D view` במיוחד.

**הצלחה:** `E2E FOAM OBSTACLE2D: PASS`. אם נכשל — לצרף את 40 השורות שלפני
הכשל, זו הפעם הראשונה שהנתיב הזה נבדק בכלל.

---

### R3 · `_e2e_foam_amr2d` — נכשל כאן, לאחר תיקון פיקסצ'ר

**רקע:** נכשל במכונה הזו ב-2026-09-09 עוד לפני שהסולבר הופעל:

```
ValueError: Invalid blastFoam case:
  Resolving the charge (8 cells across its radius) needs AMR level 4
  (finest 0.0125 m) - raise the AMR levels or lower the base cell to at most 0.1 m
```

זה **פיקסצ'ר מיושן**, לא באג: T39 העלה את יעד רזולוציית המטען מ-5 תאים ל-8,
והמקרה שהבדיקה בונה (בסיס 0.2 מ', 3 רמות) כבר לא מספיק. אותו שורש הפיל 4 בדיקות
ב-`_e2e_foam_refine2d` (`plan: level 3 auto zones ... - 4 []` — התוכנית מייצרת
lmax 4, הבדיקה מצפה ל-3).

**התיקון ייעשה כאן לפני שתריץ** — אני מעדכן את שני הסקריפטים ל-8 תאים.
המשימה שלך: לאשר שאחרי התיקון הם עוברים גם על חומרה אחרת.

```
cd blastlab/tests
git pull                       # לקחת את התיקון
python _e2e_foam_amr2d.py
python _e2e_foam_refine2d.py
```

**לתעד:** את שורת הסיכום של כל אחד, ואת שורות ה-AMR
(`AMR t = ... : N cells (+M), L0 .. / L1 .. / L2 ..`) של הריצה האחרונה.

**הצלחה:** שניהם PASS.

---

### R4 · `test_blast3d` — פיזיקה נייטיבית תלת-ממדית

**רקע:** עובר כאן, אבל לוקח **מעל 25 דקות** ולכן הוצא מהמטריצה המהירה (P2-9).
על מכונה מהירה זה אמור לרדת משמעותית; המספר עצמו הוא מה שקובע אם להחזיר אותו.

```
cd blastlab/tests
time python test_blast3d.py          # ללא timeout!
```

**לתעד:** `ALL CHECKS PASSED` או הכשל, ו**זמן הקיר המדויק**.

**הצלחה:** PASS. אם זה יורד מתחת ל-8 דקות — לרשום ב-TODO שאפשר להחזיר אותו
למטריצה המהירה על חומרה כזו.

---

### R5 · `_e2e_solver_viewer.py` — מעולם לא הסתיים

**רקע:** פתרון נייטיבי תלת-ממדי של 900 ק"ג ב-60³ תאים, מזרים לחלון צופה אמיתי.
לא הסתיים כאן ב-10 דקות. המסלול (סולבר → צופה חי → playback) מכוסה חלקית
ע"י `_e2e_gui_view3d`, אבל לא במלואו.

```
cd blastlab/tests
python _e2e_solver_viewer.py         # נפתח חלון VTK אמיתי - אל תסגור אותו
```

**לתעד:** האם הסתיים, תוך כמה זמן, האם החלון הראה גל מתפשט, והאם ה-playback
בסוף עבד. צילום מסך אחד באמצע הריצה ואחד ב-playback.

**הצלחה:** מסתיים בלי חריגה, החלון מציג גל, ה-playback מגיב.

---

### R6 · תקרת התאים האמיתית (N17/T48) — אימות מודל החומרה

**רקע:** T48 מדד `BYTES_PER_CELL = 2650` על **המכונה הזו בלבד** (blastFoam
serial 3D: 59,319 תאים → 305.1 MB; 262,144 → 843.3 MB; ~148 MB קבוע).
כל התקרות של האפליקציה נגזרות מהמספר הזה. אם הוא לא נכון על חומרה אחרת —
האפליקציה מסרבת או מאשרת מקרים בטעות אצל כל משתמש אחר.

```
cd blastlab/tests
python test_hardware.py              # קודם: 58 הבדיקות, ללא WSL
python - <<'EOF'
import sys, time, subprocess; sys.path.insert(0, '../..')
from blastlab.core.case import Case3D
from blastlab.solvers import get_solver
from blastlab.solvers.hooks import RunHooks
from blastlab.solvers.foam import env
print('hardware:', env.hardware(probe=True))
# שלושה גדלים, כמו ב-T48, כדי לחלץ שיפוע וקבוע
for dx, L in ((0.05, 1.0), (0.04, 1.0), (0.025, 1.0)):
    c = Case3D(Lx=L, Ly=L, Lz=L, cell_size_m=dx, charge=25.0,
               center=(L/2, L/2, L/2), solver='blastfoam',
               charge_resolution='smear', n_snapshots=1)
    t0 = time.perf_counter()
    res = get_solver(3, 'blastfoam')(c, RunHooks())
    n = int(round((L/dx)**3))
    print(f'CELLS {n}  WALL {time.perf_counter()-t0:.0f}s  {res.stop_reason}')
EOF
```
ובמקביל, בטרמינל שני, למדוד את ה-RSS בשיא:
```
wsl.exe -d Ubuntu -- bash -lc 'while true; do ps -o rss= -C blastFoam | sort -n | tail -1; sleep 2; done'
```

**לתעד:** לכל אחד משלושת הגדלים — מספר התאים, שיא ה-RSS ב-MB, וזמן הקיר.
בנוסף את הפלט המלא של `env.hardware(probe=True)` ואת מה שהאפליקציה מדווחת
בשורת `Parallel run:` בוולידציה.

**הצלחה:** לחשב `BYTES_PER_CELL` מהשלושה (שיפוע הרגרסיה) ולהשוות ל-2650.
אם הפער מעל 20 % — זו עדות שהקבוע צריך להימדד לכל מכונה ולא להיות מקובע.

---

### R7 · AMR מקבילי ב-4 ו-8 ranks — מעולם לא נבדק מעל 2

**רקע:** T42 מדד את ה-AMR המקבילי ב-np=2 בלבד (340 שנ' → 237 שנ', פי 1.43),
וקבע `balance no` כברירת מחדל עם ההערה המפורשת: *"revisit balancing only for
asymmetric refinement or 4+ ranks"*. אי אפשר לבדוק את זה כאן — התקרה של המכונה
הזו היא **2 ranks** (5 GB חלקי 2 GB לכל rank), ומאז P2-7 הבדיקה מדלגת בגלוי
במקום לעבור בשקט על np1 מול np1.

```
cd blastlab/tests
python test_foam_parallel.py         # אמור עכשיו להדפיס תקרה >= 4
python _e2e_foam_amr_ab.py           # השוואת serial מול parallel
```
ואז ידנית, 4 ואז 8 ranks על אותו מקרה:
```
python - <<'EOF'
import sys, time; sys.path.insert(0, '../..')
from blastlab.core.case import Case2D
from blastlab.solvers import get_solver
from blastlab.solvers.hooks import RunHooks
import numpy as np
base = dict(geometry='axisymmetric', Lx=2.0, Ly=4.0, cell_size_m=0.02,
            center=(0.0, 2.0), charge=5.0, solver='blastfoam',
            amr_levels=2, gauges=[(1.0, 2.0), (1.5, 2.0)], n_snapshots=1)
for np_ranks in (1, 2, 4, 8):
    c = Case2D(n_procs=np_ranks, **base)
    t0 = time.perf_counter()
    r = get_solver(2, 'blastfoam')(c, RunHooks())
    pk = [float(np.max(p)) for p in r.gauges['pressures']]
    print(f'RANKS {np_ranks}  WALL {time.perf_counter()-t0:.0f}s  '
          f'peaks {[f"{p/1e3:.1f}" for p in pk]} kPa  {r.stop_reason}')
EOF
```
ולבסוף, אם 8 ranks עובד, לחזור על 8 עם `balance yes`:
```
# ב-blastlab/solvers/foam/dicts.py לחפש את ערך ה-balance ולהפוך אותו,
# להריץ שוב את בלוק ה-8 ranks, ולהחזיר את הקוד לקדמותו
```

**לתעד:** טבלה של ranks → זמן קיר → שיאי הגייג'ים. את הפער היחסי בשיאים בין
1 ל-8 ranks. ואם נוסה `balance yes` — את אותה טבלה שוב, ואת חלוקת העומס
שה-log מדפיס.

**הצלחה:** זמני הקיר יורדים מונוטונית עד לפחות 4 ranks; שיאי הגייג'ים בין
ranks שונים בתוך **1 %** (זה הסף ש-T42 קבע: arrival ≤ 1 %, peak-map median
≤ 1 %). אם `balance yes` משפר משמעותית ב-8 ranks — זו החלטה להחזיר אותו.

---

### R8 · `_e2e_gui_chain_foam.py` — שרשרת מלאה דרך ה-GUI

**רקע:** נכתב ב-P2-6 ו**טרם רץ אף פעם**. עד T62 שלב 3D משורשר מול blastFoam
מעולם לא הצליח לרוץ, ואף בדיקה לא תפסה את זה כי אף אחת לא הריצה שרשרת עד
שלב foam תלת-ממדי. זה המנוע שסוגר את הפער.

```
cd blastlab/tests
wsl.exe -d Ubuntu -- pgrep -a blastFoam      # ריק
python _e2e_gui_chain_foam.py
```

**לתעד:** את כל שורות ה-check, את `gauge time spans per stage`, ואת
`results:` (שלוש התוויות). אם משהו נכשל — את 60 השורות האחרונות.

**הצלחה:** `GUI CHAIN FOAM: PASS`, ובמיוחד ששתי הבדיקות
"stage N starts where stage N-1 ended, not at 0" עוברות — זה השעון הפיזיקלי
האחד (N7/T41), והחצי שנשבר ב-T62.

---

### R9 · בדיקות עין (P2-5) — ארבעה דברים שרק אדם יכול

**רקע:** אלה שרדו את כל סבבי ה-QA בלי שאף אחד הסתכל.

1. **ParaView פותח את קבצי ה-VTK.** להריץ ריצת foam דו-ממדית קטנה דרך ה-GUI,
   ללחוץ **VTK** ב-Results, ואז לפתוח קובץ אחד מהתיקייה ב-ParaView.
   *לתעד:* האם נטען, האם השדות מופיעים, צילום מסך.
2. **Volume render עם Min/Max ידני.** בצופה התלת-ממדי: להדליק Volume,
   לעבור ל-Density, לכבות Auto ולהקליד Min/Max.
   *לתעד:* האם ה-render מתעדכן מיד, צילום לפני ואחרי.
3. **DPI שאינו 100 %.** להגדיר את Windows ל-125 % ו-150 %, לפתוח את האפליקציה.
   *לתעד:* צילום של כל ארבעת הטאבים בכל אחד; כל טקסט חתוך או כפתור שנדחק החוצה.
4. **מסך שני.** לגרור את החלון למסך שני (רצוי ברזולוציה אחרת).
   *לתעד:* האם החלון נשאר שמיש, האם הצופה התלת-ממדי מרנדר נכון אחרי המעבר.

**כלי עזר** — סבב צילומים אוטומטי שמייצר את החומר להסתכלות:
```
cd blastlab/tests
python _qa_gui_harness.py --list                 # מטריצת התרחישים
python _qa_gui_harness.py --scenario D04,E05,E06 # 3D נייטיבי + כל שדות ה-3D + הצופה
```
הפלט תחת `~\blastlab_qa\<חותמת>\shots`.

---

## 4. מה לתעד — הפורמט

צור קובץ אחד בשם `HEAVY_RUNS_RESULTS.md` ובו, לכל ריצה:

```markdown
## R<n> · <שם>
- מכונה: <CPU, ליבות פיזיות/לוגיות, RAM, RAM ל-WSL, גרסת Windows>
- תאריך:
- פקודה שהורצה:
- זמן קיר:
- תוצאה: PASS / FAIL / מספר
- הפלט (הזנב, 30–60 שורות):
- מספרים שנמדדו: <RSS, תאים, שיאים, זמני הגעה...>
- הערות: <כל דבר שנראה חריג>
```

**חשוב:** לתעד גם ריצות שעברו. במחצית מהמקרים כאן **המספר** הוא התוצר
(R1, R4, R6, R7), לא ה-PASS.

**מה לצרף בנוסף:**
- הפלט המלא של `env.hardware(probe=True)` פעם אחת בראש הקובץ
- `wsl.exe -d Ubuntu -- free -h` ו-`nproc`
- תוכן `%USERPROFILE%\.wslconfig`
- אם משהו קרס: 60 השורות שלפני הקריסה, לא רק ההודעה

---

## 5. מה לא לעשות

- **אל תקמט (commit) שינויי קוד** מהמכונה השנייה בלי לומר. אם נדרש תיקון
  כדי להריץ — לתעד אותו כ-diff בקובץ התוצאות, לא לדחוף.
- **אל תריץ שתי ריצות WSL במקביל.** התוצאות של שתיהן ייפגעו,
  ו-`test_foam_stop` ייכשל כזב.
- **אל תריץ עם timeout** על R4 ו-R2 — ריצה שנקטעת באמצע נראית ככשל ואינה.
- **אל תיגע בבייסליינים.** אם `test_regression` נכשל — זו תוצאה לתעד,
  לא משהו לתקן על ידי `--update`.
- **אל תמחק את `/root/blastlab_runs`** לפני שתיעדת. אם נגמר המקום:
  `python -m blastlab --clean-foam-runs --keep-gb 20`.

---

## 6. אחרי שהכל רץ

לשלוח לי (או להחזיר לריפו) את `HEAVY_RUNS_RESULTS.md`. אני אעדכן לפי זה:
- **R1** → ההחלטה על ברירות המחדל (P1-1) — קבוע או תלוי-חומרה
- **R6** → `BYTES_PER_CELL` ותקרות התאים ב-`core/constants.py`
- **R7** → ברירת המחדל של `balance` והתיעוד ב-DONE.md §N16-b
- **R2, R3, R5, R8** → סגירת P2-3, P2-4, P2-6 ב-TODO.md
- **R9** → סגירת P2-5

---

## 7. הפרומפט להדבקה

> העתק את כל הבלוק הזה לתוך Claude Code בתיקיית הפרויקט על המכונה החזקה.

```
אני על מחשב חזק יותר ממה שהפרויקט הזה פותח עליו. יש בריפו קובץ בשם
HEAVY_RUNS.md - קרא אותו במלואו לפני שאתה עושה משהו. הוא מכיל תשע ריצות
כבדות (R1..R9) שאי אפשר להריץ על מחשב הפיתוח (7.7 GB RAM, 4 ליבות פיזיות,
WSL מוגבל ל-5 GB), ולכל אחת יש: פקודה מדויקת, מה למדוד, ומה נחשב הצלחה.

המשימה שלך:

1. קודם כל ודא שהסביבה תקינה. הרץ:
       cd blastlab/tests
       python test_foam_env.py
       python test_regression.py
   אם אחד מהם נכשל - עצור, תעד את הפלט, ואל תמשיך. שאר הריצות חסרות
   משמעות בלי בסיס ירוק.

2. תעד את החומרה פעם אחת בראש קובץ התוצאות: הפלט של
   env.hardware(probe=True) (הקוד בסעיף R6), הפלט של
   "wsl.exe -d Ubuntu -- free -h" ו-"nproc", ותוכן %USERPROFILE%\.wslconfig.

3. הרץ את R1 עד R8 לפי הסדר שבקובץ. R9 הוא בדיקות עין - השאר אותו לבעלים
   ורק הכן את החומר (סבב הצילומים שמתואר שם).

4. לפני כל ריצת WSL ודא ש-WSL פנוי:
       wsl.exe -d Ubuntu -- pgrep -a blastFoam
   חייב לחזור ריק. אל תריץ שתי ריצות WSL במקביל לעולם.

5. אל תריץ את R2 ואת R4 עם timeout. הן ארוכות בכוונה; ריצה שנקטעת באמצע
   נראית ככשל ואינה.

6. כתוב את התוצאות לקובץ חדש בשם HEAVY_RUNS_RESULTS.md, בפורמט המדויק
   שמתואר בסעיף 4 של HEAVY_RUNS.md - סעיף לכל ריצה, עם זמן הקיר, הפלט
   (זנב של 30-60 שורות), והמספרים שנמדדו. תעד גם ריצות שעוברות: בחצי
   מהמקרים המספר הוא התוצר, לא ה-PASS.

7. אם ריצה נכשלת - אל תתקן את הקוד כדי לגרום לה לעבור. תעד את הכשל עם
   60 השורות שלפניו. אם נדרש תיקון קטן רק כדי להריץ בכלל, כתוב אותו
   כ-diff בתוך קובץ התוצאות ואל תקמט אותו.

8. אל תיגע בבייסליינים של test_regression ואל תריץ אותו עם --update.
   אל תמחק את /root/blastlab_runs לפני שתיעדת; אם נגמר המקום השתמש ב-
   "python -m blastlab --clean-foam-runs --keep-gb 20".

9. בסוף, כתוב לי סיכום קצר: אילו ריצות עברו, אילו נכשלו, ומה המספרים
   החשובים - במיוחד BYTES_PER_CELL שחישבת ב-R6, טבלת ה-ranks מ-R7,
   וזמן הקיר של R1.

עבוד לפי הסדר, ואל תדלג על ריצה בלי לומר למה.
```
