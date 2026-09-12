# TODO.md — כל מה שנשאר לעשות ב-blastlab

> **הקובץ היחיד לניהול עבודה.** אוחד ב-2026-09-09 מתוך `TASKS.md`, `tasksforofek.md`,
> `QA_REPORT.md` ו-`amr_prompt.md` (כולם נמחקו). מה שכבר נעשה — [DONE.md](DONE.md).
>
> **מצב התור:** T0–T69 סגורות במלואן (T64–T69 = N21, מודל החומרה, נחתו ב-09-09
> אחרי האיחוד הזה). אין אף משימה פתוחה בתור הממוספר הישן.
> כל מה שלמטה נאסף מהשוליים: פריטי watch, החלטות בעלים שנשארו פתוחות, בדיקות שלא
> הורצו, פינות שנרשמו כ"nice to have", ומצב ה-git בפועל.
>
> **סדר.** הרשימה מסודרת מהחמור והדחוף לקל: P0 → P4. בתוך כל רמה, לפי הסדר שכתוב.
> כל פריט נושא מזהה יציב (`P0-1`, `P2-3`…) — צטט אותו בקומיטים ובדיונים.

---

## תוכן

- [כללים קבועים לכל משימה](#כללים-קבועים-לכל-משימה)
- [P0 — דחוף: סיכון לאיבוד עבודה / הריפו שבור](#p0--דחוף-סיכון-לאיבוד-עבודה--הריפו-שבור)
- [P1 — פוגע במשתמש או בנכונות](#p1--פוגע-במשתמש-או-בנכונות)
- [P2 — תצוגה מטעה וכיסוי בדיקות חסר](#p2--תצוגה-מטעה-וכיסוי-בדיקות-חסר)
- [P3 — יכולות ושיפורים לפי בקשה](#p3--יכולות-ושיפורים-לפי-בקשה)
- [P4 — סביבה, דיסק, אישי](#p4--סביבה-דיסק-אישי)
- [החלטות בעלים שממתינות לך](#החלטות-בעלים-שממתינות-לך)
- [מטריצת הבדיקות](#מטריצת-הבדיקות)

---

## כללים קבועים לכל משימה

```
Project: blastlab — Python blast-wave simulation desktop app (customtkinter GUI),
native numpy 1D/2D/3D solvers in blastlab/solvers/, blastFoam backend in
blastlab/solvers/foam/ (writes OpenFOAM-9 cases, runs them in WSL Ubuntu, reads
results back onto uniform numpy grids), pyvista/VTK viewer in blastlab/viz3d/.
Ids like B23/G7/A5/N7/W2 refer to DONE.md §5 (reference index).

Hard rules:
- Never change native-solver stdout or the byte-pinned outputs unless the task
  explicitly says "re-baseline". `python blastlab/tests/test_regression.py` must
  stay green (or be deliberately re-baselined per the task, in the same commit).
- Foam goldens regenerate only via `python blastlab/tests/test_foam_writer.py --update`
  and an eyeballed diff.
- Tests are plain scripts: `cd blastlab/tests && python test_X.py`. Files named
  `_e2e_*.py` are manual end-to-end runs (need WSL, ~1–6 min each). Run the fast
  no-WSL matrix after every task; WSL suites once at the end of a task that
  touches solvers/foam/.
- WSL work: run in the FOREGROUND (backgrounded shells that spawn WSL children
  report completion early and lose stdout). Before any WSL suite check nothing is
  running (`wsl.exe -d Ubuntu -- pgrep -a blastFoam`); a foreign solver makes
  test_foam_stop and memory-heavy suites fail spuriously. After killing anything,
  check for orphans the same way and kill them. 2D axisym foam cases at default
  size can take 30+ min — use tiny domains.
- Do not touch files outside the task's scope without saying why.
- GUI verification: `python blastlab/tests/_qa_gui_harness.py --resume --scenario <ids>
  --redo <ids>` opens a real window on screen (`--list` shows the matrix; output
  under ~\blastlab_qa\<stamp>\shots).
- Windows: the test_regression baselines show as modified purely from CRLF
  conversion — do not commit them unless the task re-baselines.
- Finish by: (1) listing exactly what changed, (2) pasting the tail of each test
  you ran, (3) ticking the item here + a one-line note of what was done.
```

---

## P5 — פתוח מריצת הלילה של 2026-09-09/10

> הרקע המלא ב-`NIGHT_RESULTS.md`; מה שנסגר כבר רשום ב-[DONE.md](DONE.md) §T71.
> ארבעה קומיטים נחתו: `c2b661a`, `4e8c075`, `c66eae8`, `b368046`.

### P5-1 · שלב ה-3D בשרשרת נכשל **לסירוגין** · *הפריט הפתוח הכי חשוב*

> **עדכון 2026-09-11: לא שוחזר ב-5 ריצות רצופות.** הורץ ציד ייעודי
> (ריצה כושלת מתה תוך ~26 שנ', ריצה תקינה לוקחת ~31 דק', אז כל ניסיון
> נקטע ב-4 דק'). חמישה ניסיונות — כולם בריאים. **אני לא טוען שזה תוקן.**
> המכשור קיים (`App.show_error`, `SolverWorker.error`) ויתפוס את
> ה-traceback בפעם הבאה שזה קורה.

`_e2e_gui_chain_foam.py` עבר במלואו ב-2026-09-10 09:10 (שלושה שלבים, 31 דק'),
ובריצה הבאה ב-09:22 שלב 3 מת אחרי 26 שניות. אותו קוד, אותה מכונה, אותו מקרה.

**מה כבר נשלל:** הניקוי האוטומטי של ה-GUI (הכשל חזר גם כשהוא היה כבוי),
ו-`finalize_3d` עצמו (שחזור דרך `postmortem.load_run` על אותה תיקיית ריצה
מחזיר `Result` תקין). מה שנותר לא-משוחזר הוא ה-**hooks החיים** —
`hooks.frame3d` (`backend.py:1801`) עם `Feed3D` אמיתי, ו-`adopt_feed`
(`app.py:805-819`) שיכול לאפס את `feed3d` מהחוט של Tk במקביל.

**מה לעשות:** להריץ שוב עד שהוא נכשל. `App.show_error` ו-`SolverWorker.error`
כבר קיימים, והבדיקה מדפיסה את ה-traceback — **אין צורך לנחש יותר.**

> **עדכון 2026-09-11:** P5-2, P5-4 ו-P5-5 **נסגרו** (קומיטים `ab74c6e`,
> `2dc4c9f`, `efa651b`). P5-3 נסגר **חלקית** — ראה למטה. הסעיפים נשארים
> כאן עם המספרים, כי הם מסבירים למה הספים הם מה שהם.

### ~~P5-2~~ · `_e2e_foam_amr2d` — **נסגר** (`2dc4c9f`)

ברירת המחדל `amr_refine` הועברה 0.4 → 0.2. הסוויפ המלא, שעכשיו מדפיס גם
impulse (זה מה שהסתיר את התמונה קודם):

```
threshold    wall s   max cells   peak %   arrival %   impulse %
uniform          66      25,600     +0.0        +0.0        +0.0
0.4/0.2          52      17,425    -11.8       +11.2        +3.2
0.2/0.1          56      20,224     -3.9       +10.1       +16.0
0.1/0.05         54      20,377     -2.9        +9.6       +16.8
```

**שלושת המדדים מתכנסים** ככל שהסף מתהדק. לכן ה-+3.2 % הישן ב-impulse היה
**מקריות** — עידון-בחסר איבד impulse ובמקרה ביטל את ההפרש. שתי רצועות
הורחבו בהתאם (arrival 10→15 %, impulse 15→20 %).

**מה שנשלל במדידה:** זה **לא** הפרש בהפקדת המטען. שתי הריצות מסמנות
**אותם 392 תאים ב-0.025 מ' לאותם 400 ק"ג** (נמדד ישירות). מה שנשאר הוא
**השדה הרחוק הגס**: AMR מעדן את החזית ומשאיר את השאר על בסיס 0.2 מ',
והגייג' יושב שם — הגל מגיע ~10 % מאוחר עם זנב רחב יותר.

### ~~P5-4~~ · איזון עומס ב-AMR מקבילי — **נבנה** (`ab74c6e`)

שלב `addEmptyPatch` ב-preflight + מתג יחיד `dicts.AMR_LOAD_BALANCE`
שמניע גם אותו וגם את ה-dict. נמדד על המקרה שבו נמדד חוסר האיזון:

| | min | max | יחס | steps/s | cell-steps/s |
|---|-----|-----|-----|---------|--------------|
| לפני | 586 | 37,230 | **63.5:1** | 1.18 | 275k |
| אחרי | 18,432 | 22,685 | **1.2:1** | **1.95** | **491k** |

נוסף גם הגולדן החסר `case2d_planar_amr_np4` — לענף הזה לא היה כיסוי כלל.
**שים לב:** על מקרה שכבר מאוזן האיזון לא משנה כלום (אומת ב-`_e2e_foam_amr_ab`:
אותם מספרים בדיוק עם ובלי) — הוא משתלם רק על עידון א-סימטרי.

### ~~P5-5~~ · `settings.save()` — **נסגר** (`efa651b`)

### P5-2 (היסטורי) · הנימוק המקורי

נכשלת בשתי בדיקות: שיא −11.8 % וזמן הגעה +11.1 % מול הרשת האחידה
(ה-impulse עובר, +2.9 % מתוך 15 %). **נחקר ב-2026-09-10 עם `--sweep`:**

```
case                    wall s  max cells   peak %  arrival %
uniform 0.025 m             66     25,600     +0.0       +0.0
AMR 0.4/0.2  (ברירת מחדל)   55     17,425    -11.8      +11.2
AMR 0.2/0.1                 54     20,224     -3.9      +10.1
AMR 0.1/0.05                54     20,377     -2.9       +9.6
```

**שתי מסקנות:**
1. **שגיאת השיא היא כיול, לא תקרה של AMR.** הורדת סף העידון מ-0.4 ל-0.2
   מכווצת אותה מ-−11.8 % ל-**−3.9 %** — בתוך הסף — **בלי לשלם בזמן קיר**
   (54 שנ' מול 55) ובעלות של ~2,800 תאים.
2. **שגיאת ההגעה כמעט לא זזה** (11.2 → 10.1 → 9.6 %). היא נעולה סביב 10 %
   ולכן נשלטת על ידי משהו אחר — כנראה רשת הבסיס הגסה **לפני** החזית, שבה
   הגל נוסע עד שהעידון מדביק אותו.

**ההחלטה:** `amr_refine=0.4` נראה מעדן בחסר. אפשר (א) לשנות את ברירת המחדל
של האפליקציה ל-0.2/0.1 — משפיע על כל המשתמשים ועל שלושת הגולדנים של AMR;
(ב) לשנות רק את המקרה בבדיקה; או (ג) להרפות את סף ההגעה ל-15 % ולתעד שזו
רמת הדיוק של AMR. **לא נגעתי בכלום.**

### P5-3 · `test_foam_parallel` — סף 1 % מול 1.11 % שנמדד · **החלטת בעלים**

R7 מדד (זמן פיזיקלי זהה, `t = 6.0e-04`):

```
np=1  2,569.13 kPa   66,284 תאים
np=2  2,597.58 kPa   66,905
np=4  2,597.53 kPa   66,914
np=8  2,597.50 kPa   66,938
```

**המקביליים זהים זה לזה ל-0.003 %**, וכולם חורגים מהסריאלי ב-**1.11 %** —
מדרגה אחת בין סריאלי למקבילי, לא רעש שגדל עם מספר ה-ranks. הוא עוקב אחרי
פער של ~1.0 % במספר התאים ש-AMR ייצר.

**ההשערה שטרם אומתה:** `densityGradient` נמדד לכל תת-תחום ו-`nBufferLayers`
מתנהג אחרת ליד גבולות פנימיים, ולכן העידון יוצא נדיב יותר במקביל.
**מה שנשאר לעשות:** להשוות `cellLevel` בין np=1 ל-np=4 באותו זמן כתוב
ולראות **היכן** יושבים התאים העודפים. אם הם רצועה לאורך גבולות ה-processor —
ההשערה אושרה. *(לא בוצע: דורש ~50 דק' של ריצות.)*

> **עדכון 2026-09-11 — תמיכה חזקה בהשערה, ממקור אחר.** ב-`_e2e_foam_amr_ab`
> נמדד שהידוק ה-`amr_refine` מ-0.4 ל-0.2 מעלה את חוסר ההתאמה
> סריאלי-מול-מקבילי מ-0.6 % ל-**1.453 %**, ו**בודד**: הרצה חוזרת של np2 עם
> `AMR_LOAD_BALANCE` כבוי נותנת את אותו מספר בדיוק, כלומר זה הסף ולא
> האיזון. יותר תאים ליד גבולות ה-processor → יותר סטייה. זה בדיוק מה
> שההשערה חוזה. סף ה-A/B הורחב ל-2 % (`2dc4c9f`).
> **מה שעדיין חסר:** האימות המרחבי (`cellLevel`), ו-`test_foam_parallel`
> עצמו עדיין על סף 1 % ולא נגעתי בו.

> **עדכון 2026-09-12 — P5-3 נפתר למעשה על ידי P5-2, והטבלה למעלה מיושנת.**
>
> **הטבלה של R7 למעלה נמדדה על עץ שכבר לא קיים.** ברירת המחדל `amr_refine`
> הועברה 0.4 → 0.2 בקומיט `2dc4c9f`, ולכן כל השוואה בין המספרים ההם
> למספרים של היום חסרת משמעות. נמדד מחדש, אותו מקרה, אותו `t = 6.0e-04`:
>
> ```
> np=1                 78,434 תאים   2,413.96 kPa   2,198 שנ'
> np=4, איזון דלוק     79,724        2,412.94 kPa     699 שנ'
> np=4, איזון כבוי     79,715        2,412.94 kPa     930 שנ'
> ```
>
> **סטיית השיא סריאלי↔מקבילי ירדה מ-1.11 % ל-0.042 % — פי 26.** הסף של
> `test_foam_parallel` הוא 1 %, כלומר הוא עומד עכשיו במרווח של **פי 24**.
> **אין יותר החלטת בעלים לקבל כאן.** הפריט יכול לרדת לרמת "הבנה", לא סף.
>
> **שלוש הסתייגויות, כי הן לא מסתדרות בקלות:**
>
> 1. **זה סותר את העדכון של 09-11 שמעליו.** שם נמדד שהידוק ל-0.2 **מעלה**
>    את חוסר ההתאמה ל-1.453 % ב-`_e2e_foam_amr_ab`. כאן, על R7, אותו
>    הידוק **הוריד** אותה ל-0.042 %. שני מקרים, שתי תשובות הפוכות —
>    **מישהו צריך להחליט איזה מהם מייצג**, וזו כן שאלה פתוחה.
> 2. **מספר התאים והסטייה מנותקים:** עודף התאים עדיין **+1.64 %** בעוד
>    הפיזיקה מסכימה ל-4 חלקים ב-10,000.
> 3. **השערת גבולות ה-processor נחלשת מהנתונים של R7 עצמם.** אפקט גבול
>    צריך לגדול עם מספר הגבולות הפנימיים (np=2 → 1, np=4 → 3, np=8 → 7),
>    והעודף בפועל הוא **621 · 630 · 654** — 5 % גידול מול פי 7 בגבולות.
>
> **איזון העומסים אושר שוב כלא-הסיבה**, הפעם ב-np=4 ועל העץ של היום:
> 79,724 מול 79,715 = **9 תאים מתוך 80,000**, שיאים זהים לשתי ספרות.
> ומה שכן: **פי 1.33 תפוקה** (699 מול 930 שנ'). np=4 מהיר **פי 3.1** מ-np=1.
>
> *(מלכודת למי שיחזור על זה: `writer.py:40` עושה
> `from .dicts import AMR_LOAD_BALANCE`. הצבת `dicts.AMR_LOAD_BALANCE`
> לבדה לא משנה את המקרה שנכתב, והניסוי יחזיר "אין הבדל" מסיבה שגויה.
> יש להציב גם את `writer.AMR_LOAD_BALANCE`.
> הסקריפט: `night_artifacts/NIGHT2/scripts/n2_p53_balance.py`.)*

### P5-4 · `balance yes` דורש שלב `addEmptyPatch` — **לא היפוך שורה**

נוסה ב-2026-09-10 על המקרה שבו נמדד חוסר איזון של **1:64** בין ranks
(586 תאים מול 37,230, ב-13 ranks). הריצה מתה תוך 11 שניות:

```
FOAM FATAL ERROR: When balancing is enabled, an internal patch should be
added to the mesh. To add the necessary patch to the mesh and the fields,
use the command "addEmptyPatch patchName internal -overwrite"
    From function void Foam::fvMeshBalance::checkForInternal() const
    in file fvMeshBalance/fvMeshBalance.C at line 112.
```

כלומר להפעיל איזון = להוסיף שלב `addEmptyPatch` ל-pipeline של ה-preflight
(וגם למסלול ה-resume), לא לשנות את `writer.py:1038`. **שווה לעשות** — יחס
1:64 אומר שרוב המכונה מחכה. הערך הנוכחי והממצא מתועדים בהערה בקוד.

**קשור:** אין היום שום גולדן של **parallel + AMR**, כלומר לענף
`writer.py:1025-1038` אין כיסוי ב-`test_foam_writer` בכלל.

### P5-5 · `settings.save()` נכשל בשקט

`gui/settings.py:79-92` מחזיר `False` על `OSError`, ו-`update()` (:95-104)
מתעלם מערך ההחזרה. כתיבה שנכשלה אינה נראית לאיש. נתקלתי בזה בפועל
(כתיבה שלא נחתה, בלי שום סימן). מינימום: ש-`update` יחזיר את ההצלחה,
ושהקורא שמשמר חומרה ידווח פעם אחת אם לא הצליח.

### P5-6 · R2, R4, R5 — ריצות שלא הספיקו

- **R2** `_e2e_foam_obstacle2d axi` — נעצרה **55 דקות לפני הסוף** (914 צעדים,
  `t = 8.229e-04`, הכל בריא). הכותרת עודכנה ל-~105 דק'.
- **R4** `test_blast3d` — לא הורצה. **אינה תלוית-WSL**, אפשר במקביל לכל דבר.
- **R5** `_e2e_solver_viewer.py` — לא הורצה, וגם **חסומה** (ראה P5-7).

### P5-7 · P2-5 חסום סביבתית — אין שולחן עבודה אינטראקטיבי

`_qa_gui_harness.py --scenario D04,E05,E06`: שלושת התרחישים קרסו על
`OSError: screen grab failed` מ-`PIL.ImageGrab.grab(all_screens=True)`.
ה-GUI **כן** נבנה ("App built in 4225 ms") — רק הצילום נכשל. E05/E06 קרסו
במורד הזרם. **דורש מכונה עם קונסולה אינטראקטיבית אמיתית**, ולכן P2-5 נשאר
פתוח במלואו. תיקון אפשרי אם רוצים ש-R9 ירוץ גם בסשן מנותק: לעטוף את
`shot()` (`_qa_gui_harness.py:412`) ב-`try/except OSError` שמתעד פער במקום
להפיל את התרחיש.

### P5-8 · לעדכן: P4-3 הוא **מלכודת**, לא רק פיצ'ר

הניקוי האוטומטי בהפעלת ה-GUI רץ גם מ-`_e2e_gui_*` ומ-`_qa_gui_harness`,
בלי לשאול. ב-2026-09-10 הוא מחק 34 ריצות (56 GB → 12 GB) **כולל תיקיית
ה-SIGFPE שהייתה נושא החקירה**. לפני כל הרצת GUI שבה ריצה כלשהי חשובה:
`auto_cleanup: false` ב-`%APPDATA%\blastlab\settings.json`, או להעתיק החוצה.

---

## P0 — דחוף: סיכון לאיבוד עבודה / הריפו שבור

> **✅ P0 כולו נסגר ב-2026-09-09, קומיט `e344d17`.** שלושת הפריטים טופלו יחד:
> `.gitignore` הורחב ופלטי הריצה הוצאו מה-index (נשארו על הדיסק); חמשת הקבצים
> ה-untracked + `TODO.md`/`DONE.md` נוספו; ארבעת המסמכים שאוחדו נמחקו.
> אומת בקלון טרי: `import blastlab` עובר, `test_foam_reader`, `test_foam_writer`
> ו-`test_hardware` PASS. המטריצה המהירה: 28 חבילות, כולן PASS, `test_regression`
> בייט-זהה.

### P0-1 · העבודה של T62/T63/T48 אינה מחויבת, וקובץ קריטי אינו ב-git כלל

`blastlab/core/hardware.py` הוא **untracked**, ו-`blastlab/solvers/foam/env.py:36` בעץ העבודה
מייבא ממנו (`from ...core.hardware import CACHED, MEASURED, UNKNOWN, parse_meminfo_kb`).
קומיט בלי `git add` מפורש ישבור את הריפו לכל מי שיקלון אותו; אובדן התיקייה או דריסת סנכרון
של OneDrive יאבד את T48 ואת T62.

באותו מצב, untracked ונדרשים (**עודכן 2026-09-09 אחרי N21**):
- `blastlab/core/hardware.py` — הליבה של N21 (זיהוי מכונה, TTL, בדיקת RAM של המארח,
  תקרות התאים הנייטיביות). `core/case.py`, `solvers/foam/env.py`, `viz3d/sampling.py`
  ו-`solvers/hooks.py` כולם מייבאים ממנו — בלעדיו הריפו לא נטען בכלל
- `blastlab/tests/test_hardware.py` — חבילת הבדיקות של N21 (58 בדיקות, ללא WSL)
- `blastlab/tests/foam_golden/case2d_axi_profile_amr/` — הגולדן ש-`test_foam_writer.py:66`
  (שכן שונה ונשמר) בונה מולו
- `blastlab/tests/_e2e_foam_chain_amr.py`
- `blastlab/tests/foam_fixtures/p_uniform_truncated` — ראה P0-2

ובנוסף **27** קבצי מקור ובדיקה modified שלא חויבו: `README.md`, `cli.py`, `core/case.py`,
`core/constants.py`, `core/geometry.py`, `gui/app.py`, `gui/forms.py`, `gui/run_panel.py`,
`gui/settings.py`, `solvers/foam/backend.py`, `dicts.py`, `env.py`, `postmortem.py`,
`reader.py`, `runloop.py`, `runner.py`, `writer.py`, `solvers/hooks.py`,
`solvers/solver1d.py`, `viz3d/sampling.py`, `viz3d/viewer.py`,
`tests/test_bc_trigger.py`, `test_case_validate.py`, `test_foam_env.py`,
`test_foam_ingest_order.py`, `test_foam_writer.py`, `test_gui_amr_form.py`.

**גם `TODO.md` ו-`DONE.md` עצמם untracked** (`TASKS.md`, `QA_REPORT.md`, `amr_prompt.md`
נמחקו מעץ העבודה אבל עדיין ב-HEAD). כלומר האיחוד של 09-09 חשוף בדיוק לאותו סיכון שהפריט
הזה מתריע עליו: `git checkout` או תקלת סנכרון של OneDrive ימחקו את שני הקבצים ויחזירו את
השלושה הישנים.

**מה לעשות:** להריץ את המטריצה המהירה, ואז `git add` מפורש לחמשת ה-untracked הנדרשים +
ל-`TODO.md`/`DONE.md` + `git rm` לשלושת הקבצים שאוחדו + לקבצים ששונו, וקומיט אחד:
`Land T62/T63 + T64-T69 (N21 hardware model); split TASKS.md into TODO/DONE`.
`blastlab/tests/gauges.txt` הוא פלט ריצה — לא לחייב אותו (ראה P0-3).
לוודא לפני הקומיט: `git status` נקי מהדברים האלה, ו-`python -c "import blastlab"` עובר
מתוך קלון טרי (או לפחות `git stash -u` + הרצת הבדיקות).

### P0-2 · `test_foam_reader` נכשל בקלון נקי — פיקסצ'ר חסר ב-HEAD

`blastlab/tests/test_foam_reader.py:48` ו-`:55` — **קוד שכבר מחויב** — קוראים ל-
`foam_fixtures/p_uniform_truncated`, והקובץ הזה untracked. כלומר master של היום נכשל
בבדיקה הזו על כל מכונה אחרת. זו רגרסיה קיימת, לא "עוד קובץ שנשכח".

**מה לעשות:** `git add blastlab/tests/foam_fixtures/p_uniform_truncated` (חלק מ-P0-1),
ולוודא בקלון טרי ש-`python test_foam_reader.py` עובר.

### P0-3 · `.gitignore` לא מכסה את פלטי הריצה, והם מזהמים כל diff

`.gitignore` מכיל שש שורות בלבד (`__pycache__/`, `*.pyc`, וארבע תיקיות מחקר).
לא מכוסים, ויושבים בשורש הריפו: `case.json`, `gauges.txt`, `gauges_2d.txt`,
`gauges_3d.txt`, `blast_profile.txt`, `run/`, `test_profile_2d.npz`, `test_profile_3d.txt`,
`blast_2d_animation.gif/.mp4`, `blast_3d_animation.gif`, `anim3d_test.gif`, וכל
ה-`blast_3d_*.png`. חלקם כבר tracked ומשתנים בכל ריצה — ה-diff הנוכחי כולל 7,504 שורות
שינוי ב-`blast_profile.txt` בלבד. **זה מה שהסתיר את P0-1 ו-P0-2.**

**מה לעשות:** להרחיב את `.gitignore`; `git rm --cached` לפלטים שכבר tracked (לא למחוק
מהדיסק); להשאיר tracked רק את מה שבדיקה באמת קוראת (הגולדנים תחת `blastlab/tests/`).
שים לב: `blastlab/tests/*.png` ו-`blastlab/tests/anim3d_test.gif` **כן** נבדקים — אל תוציא
אותם.

---

## P1 — פוגע במשתמש או בנכונות

> **✅ P1 כולו נסגר ב-2026-09-09** (קומיטים `62870b5`, `6b0407c`).
> P1-1: `Case3D` ירדה לערכים שה-GUI כבר פותח איתם (1.5 מ' / 25 ק"ג) — שלוש ברירות
> המחדל עוברות עכשיו ולידציה בשני ה-backends. P1-2: הערת W2 בשלושת ה-finalizers.
> P1-3: הרשימה הריקה נשמרה (היא נכונה לשלב profile) ונוסף שומר לכיוון ההפוך.
> P1-4: חמשת החומרים הלא-מכוילים מקבלים אזהרה במקום הערה ששיקרה.
> P1-5: **שוחזר, אובחן ותוקן מול WSL** — ראה למטה.

### P1-1 · המקרה הדו-ממדי שנשלח כברירת מחדל נדחה על המכונה הזו · **החלטת בעלים**

תוצאת T48/N17: ברירת המחדל היא ~2.3M תאים ≈ 6.1 GB, וה-VM של WSL הוא 4 GB, אז
`validate_case` **מסרב** להריץ אותה. לפני T48 היא התקבלה והייתה מתה בתוך WSL — כלומר
הסירוב נכון, אבל משתמש חדש נתקע בהרצה הראשונה.

שתי דרכים, שתיהן החלטה שלך:
1. להעלות `memory=` ב-`%UserProfile%\.wslconfig` (למשל 8–12 GB) ואז `wsl --shutdown`.
2. להוריד את ברירת המחדל שנשלחת (תחום קטן יותר או תא בסיס גס יותר) כך שתתאים ל-4 GB.

מומלץ: (1) אם יש RAM פנוי במכונה, כי זה גם מרחיב את מה שאפשר להריץ בפועל; אחרת (2).

**עדכון N21 (2026-09-09):** המדידה עברה מ-`free -g` ל-`/proc/meminfo`, כך שה-VM כאן נמדד
כ-5 GB ולא 4 — הסירוב עצמו לא השתנה. מה שכן נוסף: מכונה ש**לא נבדקה** (WSL בהתנעה קרה,
timeout) מקבלת עכשיו תקרה שמרנית של VM בגודל 4 GB במקום 120M תאים, ולכן גם היא תסרב
לברירת המחדל — עם אזהרה מפורשת שהחומרה לא ידועה. זה מחזק את הצורך להכריע כאן: היום
משתמש חדש נתקע בהרצה הראשונה גם כשה-WSL שלו פשוט עוד לא ענה.

### P1-2 · W2 — ריצה שנעצרה מאבדת את זנב דגימות הגייג'

`blastProbes` מרוקן את החוצץ שלו רק ב-End תקין. ריצה שנעצרה שומרת ~flush אחד
(נמדד: 5 מתוך ~600), עם או בלי resume (T43). לולאת ההרצה כבר ממתינה עד 10 שניות ל-End
תקין לפני ה-kill של רשת הביטחון. **תיקון אמיתי דורש מתג flush בצד foam** (שינוי ב-
`blastProbes`, או FO חלופי שכותב בכל write).

**מה לעשות:** או לחיות עם זה ולתעד בממשק ("a stopped run may miss the last ~N samples"),
או לבדוק אם ל-blastFoam יש `flushInterval`/`writeControl` על ה-FO הזה. אל תסתפק בהגדלת
ההמתנה — היא כבר 10 שניות.

### P1-3 · `_phaseproperties` פולט רשימת `points` ריקה בשלב profile

נמצא תוך כדי קריאה ב-T62 ולא כוסה. היום לא מזיק — בשלב profile אין מה לפוצץ — אבל זו בדיוק
צורת הבאג של החוסם הראשון ב-T62 (fallback חסר שמתפוצץ שלושה פריימים אחר כך).

**מה לעשות:** או fallback מפורש (`spec.burst_points`, כמו שאר הנתיב אחרי T62), או סירוב
מפורש עם הודעה. `test_foam_writer` הוא המקום לנעוץ את זה.

### P1-4 · פרמטרי afterburn לחומרים שאינם TNT אינם מכוילים · **החלטת בעלים**

מודל ה-afterburn (T16) מכויל ל-TNT מול Kingery-Bulmash. עבור C4, RDX, HMX, PETN ו-ANFO
ה-Q0 נגזר מ**איזון חמצן בלבד** — סדר גודל נכון, בלי כיול מול נתונים. ברירת המחדל היא
`none`, כך שכל מה שרץ עד היום לא הושפע.

**מה לעשות:** אם אתה מתכוון לצטט מספרים לחומר שאינו TNT — צריך כיול או מקור. אחרת: לתייג
בממשק "uncalibrated (oxygen balance)" ליד בחירת החומר כשה-afterburn דלוק.

### P1-5 · resume של ריצת profile+AMR נכשל בתוך blastFoam

נמצא ב-T70. לעצור שלב שמאותחל מפרופיל עם AMR ולחדש אותו (`backend.resume_run`) — הסולבר מת
מיד עם:

```
--> FOAM FATAL IO ERROR:  size 5138 is not equal to the given value of 5189
file: .../<t_last>/pMax
```

כלומר שדה הצבירה של ה-function object בתיקיית הזמן האחרונה לא תואם את הרשת שנכתבה
באותה תיקייה — אי-עקביות בתוך כתיבה אחת, לא משהו שצד ה-Python עושה.

**מה כן עובד:** טעינה של אותה ריצה דרך `postmortem.load_run` (נבדק ב-T70), ו-resume של
ריצת **charge**+AMR — נוסתה פעמיים, גם אחרי 207 צעדים, ועברה. לכן זה נראה ספציפי
לשלבי profile ולא ל-AMR בכללותו.

**מה לעשות:** לבדוק אם `pMax`/`impulse` בכלל ממופות על ידי ה-refiner (הן שדות של FO,
לא שדות פתרון); אם לא — למחוק אותן מתיקיית ההתחלה לפני ה-restart (הצבירה מתחילה
מחדש, מה שכבר קורה בצד ה-Python), או לסרב ל-resume על שלב profile+AMR עם הודעה
ברורה במקום להפיל את הסולבר. לשחזור: `_e2e_foam_chain_amr.py` עם עצירה אחרי ~12 פריימים.

---

## P2 — תצוגה מטעה וכיסוי בדיקות חסר

> **מצב 2026-09-09:** P2-1, P2-2, P2-7, P2-8, P2-9 נסגרו (קומיטים `6b0407c` והבא
> אחריו). P2-6 — המנוע נכתב (`_e2e_gui_chain_foam.py`), ממתין להרצת WSL.
> P2-3/P2-4 — ההרצות הארוכות בעיצומן. P2-5 — נשאר בעיקר עליך.

### P2-1 · פס ההתקדמות של 1D מטעה פי ~10

`solver1d.py:242` מחשב התקדמות כ-`t / safety_cap`, בעוד 2D/3D משתמשים ברדיוס החזית ביחס
ל-R. ה-safety cap הוא ~10× אורך הריצה האמיתי, כך שריצת 1D נראית כאילו היא בקושי מתקדמת.
**שים לב:** אם התיקון נוגע ב-stdout של הסולבר — הוא דורש re-baseline מפורש.

### P2-2 · "Energy [J/kg]" בריצות foam הוא קירוב שמוצג כאמת

בצופה, השדה Energy לריצת foam מחושב כקירוב גז אידאלי `p / 0.4ρ` (`viewer.py`).
או להסתיר אותו לריצות foam, או לתייג "Energy [J/kg] (approx)".

### P2-3 · בדיקות WSL שלא הורצו אחרי T50–T54

בזמן T50–T54 לא הורצו: `test_foam_2d`, `test_foam_3d_smoke --tiny`, וסקריפטי ה-`_e2e_foam_*`.
השינויים שם בצד foam הם בדיקת הטריגר ושינוי שם המסכה — קטנים, אבל לא מאומתים מול WSL.
**להריץ לפני שסומכים על ריצת טריגר ב-blastFoam.** צריך WSL פנוי.

**עודכן 2026-09-09 (N21):** `test_foam_2d` ו-`test_foam_3d_smoke` **הורצו ועברו** מול WSL
פנוי, יחד עם `test_foam_1d_vs_native`, `test_foam_parallel`, `test_foam_stop`,
`test_foam_postmortem` ו-`test_foam_features` — שבע חבילות, כולן PASS. **מה שנשאר פתוח
בפריט הזה: סקריפטי ה-`_e2e_foam_*` בלבד.**

### P2-4 · שלוש בדיקות שמעולם לא הושלמו

- `_e2e_foam_obstacle2d axi` — לפי הכותרת שלו ~30 דקות wall. החלק ה-planar עבר.
- `_e2e_solver_viewer.py` — פתרון נייטיבי 3D של 900 ק"ג ב-60³ תאים; לא הסתיים ב-10 דקות.
  אותו מסלול (סולבר → צופה חי → playback) מכוסה על ידי `_e2e_gui_view3d` שעבר.
- foam 2D אקסיסימטרי בגודל ברירת מחדל — 30+ דקות, נמנע במכוון בסבב ה-QA.

**מה לעשות:** או להריץ אותם פעם אחת ברקע ולתעד, או לסמן אותם רשמית כ"manual, long" בראש
כל קובץ כדי שלא ייחשבו כפער כיסוי.

### P2-5 · מה שלא נבדק בעין מעולם

**עודכן 2026-09-09 אחרי בדיקה בפועל — שניים מהשישה כבר מכוסים ולא צריכים עין:**
- ~~תוצאה ישנה בלי מפות שיא~~ — מכוסה ב-`test_gui_results_fields` (הבלוק
  "hidden without the maps"): `fake_2d(False)`/`fake_3d(False)` מוודאים שהשדות
  נעלמים מהרשימה ושאין איורי ייצוא נוספים. לא צריך עין.
- ~~ריצת afterburn `miller`~~ — הפיזיקה מכוסה ב-`test_foam_kb_anchor --afterburn`
  (רץ בעבר, בתוך הרצועה 0.80–1.35). מה שלא נבדק זה רק **המראה** ב-GUI.

**נשאר, ורק אתה יכול לעשות את זה (דורש עיניים מול מסך):**
- פתיחת קבצי ה-VTK שהאפליקציה מייצאת ב-ParaView — לוודא שהם באמת נטענים.
- volume render עם Min/Max ידני בצופה התלת-ממדי.
- DPI שאינו 100 % (הגדרות תצוגה של Windows).
- מסך שני.

(שאר רשימת הבדיקה הידנית — עידון סטטי, Show mesh, טבלת גייג'ים, דפדפן ריצות, טעינת
post-mortem, Stop בכל שלב — **אושרה בעין בסבב ה-QA של 09-07**, אין צורך לחזור.)

### P2-6 · אין e2e לטאב Chain מול blastFoam

התנאי לזה (T41) נחת ב-09-07. צריך driver בסגנון `_e2e_gui_foam.py` שמריץ שרשרת שלמה
1D→2D→3D דרך ה-GUI מול foam — במיוחד עכשיו, אחרי ש-T62 גילה ששלב 3D מ-profile מעולם לא רץ.

### P2-7 · `test_foam_parallel` יכול להשוות np1 מול np1 בלי לומר זאת · *נמצא ב-N21*

מאז T68 מספר ה-ranks המפורש נחתך לתקרת המכונה (`env.rank_ceiling`: ליבות פחות headroom,
ו-RAM חלקי `RAM_GB_PER_RANK = 2`). על המכונה הזו התקרה היא **2** (VM של 5 GB), כלומר
בדיוק מה שהבדיקה מבקשת — היא עוברת. אבל על VM של 3 GB או פחות התקרה היא 1, והבדיקה
תריץ np1 מול np1, תעבור, **ולא תבדוק כלום**. זו חולשה בבדיקה, לא בקוד.

**מה לעשות:** ש-`test_foam_parallel` יקרא ל-`env.rank_ceiling` בהתחלה, וידלג במפורש
(`[SKIP] VM too small for 2 ranks`) במקום לעבור בשקט.

### P2-8 · `test_gui_run_browser` נתקע על דיאלוג מודאלי · *נמצא ב-N21*

`run_browser.delete_selected` (`:295`) קורא ל-`messagebox.showwarning(..., parent=self)`
כשמסרבים למחוק ריצה חיה. הבדיקה לא עושה patch ל-`messagebox`, ולכן היא נתקעת שם עד
timeout. **אומת שזה קיים ללא קשר ל-N21**: עם כל שינויי N21 ב-`git stash`, הבדיקה נתקעת
באותה שורה בשתי הרצות רצופות. היא כן עברה פעם אחת באותו סבב — כלומר ההתנהגות תלויה
בפוקוס החלון, וזו בדיקה לא דטרמיניסטית.

**מה לעשות:** להזריק `warner=` לצד `confirm=` הקיים (הבדיקה כבר מזריקה `lister`, `sizer`,
`deleter`, `confirm`, `on_resume`) ולתת לבדיקה לספק stub.

### P2-9 · `test_blast3d` לוקח יותר מ-25 דקות כאן

לא נכשלת — **הורצה עד הסוף ב-09-09 והחזירה `ALL CHECKS PASSED`** — פשוט ארוכה מאוד על
המכונה הזו (7.7 GB, 12 ליבות לוגיות). היא ב"מטריצה המהירה", מה שלא נכון: כל הרצה של
המטריצה נחסמת עליה. הודגם ב-N21: ריצה עם timeout של 560 שניות נקטעה באמצע T3–T4 בזמן
שהתקדמה תקין, ורק הרצה בלי timeout כלל הגיעה לסוף.

**מה לעשות:** להעביר אותה לקבוצה נפרדת ("physics, slow") או לתת לה מתג `--tiny` כמו
ל-`test_foam_3d_smoke`.

---

## P3 — יכולות ושיפורים לפי בקשה

*(אף אחד מאלה אינו חוסם. נאספו מ-§5 של TASKS.md.)*

**יכולות פיזיקליות**
- `P3-1` מכשולים שאינם קופסאות (STL → snappyHexMesh) — דורש את אותו resampler כמו AMR.
- `P3-2` הפעלת `pressureBased` — קבועי קצב לכל חומר; רק אם פיזיקת ההצתה חשובה.
- `P3-3` override של `maxDeltaT`/`deltaT` לכל מקרה — חיווט טריוויאלי ב-writer.
- `P3-4` השוואת HLLC: `dicts.FLUX_SCHEME = 'HLLC'` היא היפוך שורה אחת;
  `test_foam_1d_vs_native.py` הוא ה-harness.
- `P3-5` אפשרות smear אקסיסימטרי ב-2D (ב-3D קיימת; 2D מעדן בלבד).
- `P3-12` אזורי עידון סטטיים לשלב המאותחל מפרופיל — החצי ש-T70 לא פתח. `refineMesh`
  ממספר מחדש את התאים, אז צריך להעביר את `writeCellCentres` + `build_remap` לפני
  `write_deferred` ולכתוב את השדות דרך `spec.remap` (המכוון קיים — רק הסדר הפוך).
- `P3-13` מטענים נוספים קיימים רק ב-3D (`case.py`: "Additional charges are only supported
  for 3D blastFoam cases"). ב-2D **planar** זה בר-ביצוע — מטען דו-ממדי הוא גליל אינסופי,
  ו-`spec.charges` כבר רשימה גם במסלול הדו-ממדי (`writer.py:311`); חסרים ה-setFieldsDict,
  בדיקות חפיפה/גבול והטבלה ב-GUI. אקסיסימטרי נשאר מטען יחיד על הציר — זו גאומטריה,
  לא פער.
- `P3-14` אין פורמט remap תלת-ממדי, ולכן **שלב 3D הוא תמיד סוף השרשרת**: הוא לא יכול
  להזין שלב נוסף, ו-`trigger_action='remap'` מסורב ב-3D (`case.py:493`). עבודה גדולה
  (פורמט + remap + ולידציה + GUI) — רק אם באמת רוצים להמשיך ריצה תלת-ממדית בשלב נוסף.
- `P3-15` מכשולים אינם עוברים ב-remap מ-2D ל-3D — הם היו הופכים לטבעות סביב הציר, אז
  `save_profile_2d` מפיל אותם עם אזהרה בלבד (`profiles.py:151`). השלב התלת-ממדי ממשיך
  מצב שהתפתח סביב מכשולים שכבר אינם שם. מינימום: להעלות לאזהרת ולידציה ב-GUI במקום
  הדפסה ב-stdout.

**ביצועים**
- `P3-6` קריאת `processor*/` ישירה גם לריצות MPI אחידות (לדלג על reconstructPar) — רק אם
  ההשהיה של ~3 שניות לכתיבה מפריעה. T42 כבר בנה את המנגנון עבור AMR.
- `P3-7` מסלול ה-blit בצופה מרנדר פעמיים ומקצה ~1.3 MB לפריים (`vtk_host.py` ~130–138).

**ליטוש בצופה**
- `P3-8` log-contours חלים רק על מישורי חתך (`viewer.py` ~345/635).

**קוסמטיקה** *(כל מה שנוגע ב-stdout של סולבר דורש re-baseline)*
- `P3-9` תווית ציר ה-x באנימציה אקסיסימטרית: `x [m]` → `r [m]` (`animation.py:66`).
- `P3-10` ריצה משורשרת מדפיסה "0 kg TNT" בשורת האתחול התלת-ממדית
  (`profiles.py:157`, `solver3d.py:369`).
- `P3-11` הסמנטיקה של `n_snapshots` שונה בין 1D ל-2D/3D.

---

## P4 — סביבה, דיסק, אישי

### P4-1 · הריפו יושב בתוך OneDrive

`git worktree remove` נכשל פעם אחת על "Permission denied" — נעילת סנכרון על `.git`.
שקול להחריג את `.git` מהסנכרון, או להעביר את הריפו אל מחוץ ל-OneDrive.
זה גם מה שהופך את P0-1 למסוכן יותר מהרגיל.

### P4-2 · ניקיון דיסק — הדחיפות ירדה

בסבב ה-QA של 09-07 נמדדו **617 GB פנויים** ב-C:, כך שהלחץ שהיה ב-09-05 נעלם. נשארו
כהחלטות רגועות:
- `OneDrive - Technion\תואר שני\סמסטר ב\אלמנטים סופיים\חומר מרן\OneDrive_1_5-29-2026.zip`
  — 13.4 GB, לצידו תיקייה פרוסה זהה (14 GB, `Lectures`). ה-zip כפול.
- `C:\OneDriveTemp` — 6.2 GB של קבצי `.temp` מהעלאות OneDrive. אם OneDrive לא מנקה לבד,
  אפשר למחוק (הוא יוצר מחדש).
- כפילות `Projects\Project_1\REFERENCES` (45 GB) ↔
  `OneDrive\תואר שני\תזה\calculation_backup\...\Reference Viper Models`:
  `Free_Field_500kg` ו-`Free_Field_1500kg` זהים קובץ-קובץ, `50kg` כמעט.
  `Projects` כולו (117 GB) נראה כעותק מקומי של הגיבוי.
- הרווח הגדול בלי למחוק: קליק ימני על `250` (153 GB), `גיבוי לכרמל` (64 GB),
  `תואר ראשון` (54 GB) → **Free up space** (Files On-Demand).
- `hiberfil.sys` 3.1 GB: אם אינך משתמש ב-Hibernate — `powercfg /h off` (כמנהל).

### P4-3 · ניקוי ריצות ה-WSL

`/root/blastlab_runs` היה 86 ריצות / 27.8 GB בסוף סבב ה-QA. ניקוי:
`python -m blastlab --clean-foam-runs` (או `--older-than 1` / `--keep-gb 5`).
קיים גם ניקוי אוטומטי בהפעלת ה-GUI (מעל 20 GB או ישן מ-14 יום; שלוש האחרונות נשמרות;
כיבוי דרך `auto_cleanup: false` ב-`%APPDATA%\blastlab\settings.json`).
ה-vhdx לא מתכווץ לבד: `wsl --shutdown` ואז `diskpart` →
`select vdisk file=C:\WSL\Ubuntu\ext4.vhdx` → `compact vdisk`.

---

## החלטות בעלים שממתינות לך

| # | ההחלטה | המלצה |
|---|--------|-------|
| P1-1 | ברירת המחדל של 2D מול 4 GB ב-WSL — להעלות RAM או להקטין את המקרה | להעלות `memory=` ב-`.wslconfig` אם יש RAM |
| P1-2 | W2 — לחיות עם זנב הגייג'ים החסר בריצה שנעצרה, או לחפש מתג flush ב-blastFoam | לתעד בממשק; לחפש מתג רק אם זה מפריע בפועל |
| P1-4 | afterburn לחומרים שאינם TNT — לכייל, או לתייג כלא-מכויל | לתייג; לכייל רק אם תצטט מספרים |
| P2-4 | להריץ פעם אחת את שלוש הבדיקות הארוכות, או לסמן אותן "manual, long" | לסמן; להריץ כשיש לילה פנוי |
| P4-1 | להוציא את הריפו מ-OneDrive | כן — אחרי P0-1 |
| P4-2 | מה למחוק מהדיסק | לא דחוף (617 GB פנויים) |

---

## ליל QA 2026-09-12 — פריטים חדשים

> הדוחות המלאים: [NIGHT2_RESULTS.md](NIGHT2_RESULTS.md) ·
> [NIGHT2_LOG.md](NIGHT2_LOG.md). מטריצת ה-GUI בת 58 התרחישים רצה
> **בפעם הראשונה** אחרי `a5ef729`. כל הפריטים כאן **תועדו ולא תוקנו**,
> לפי חופש התיקון שניתן: באגים חד-משמעיים בלבד, בלי ספים וברירות מחדל.

| id | sev | מה | איפה |
|----|-----|-----|-------|
| **N2-07** | **S2** | **ה-preview מתכנן תמיד עם rho0 של TNT** — `preview_panel.py:42` קורא `plan_levels(case)` בלי `rho0`, בעוד `validate_case` ו-`writer` מעבירים את זה של החומר. ב-ANFO ה-preview מצייר **רמת עידון שלמה יותר ותא עדין קטן פי 2** ממה שייבנה, בזמן שהרצועה באותו מסך מציגה את המספר הנכון | `gui/preview_panel.py:42` |
| **N2-09** | **S2** | **טבלת סיכום המדים אינה על המסך** מתחת ל-960 px גובה חלון (`mapped=False`), שמישה רק מ-1060 — והמסך הוא 1080. זה המקום היחיד ב-UI שמציג שיא, זמן הגעה, אורך פאזה ואימפולסים | `gui/results_panel.py:230` מול `:265` |
| **N2-12** | **S2** | **`click Run` על מקרה 3D מקפיא את ה-UI 11,279 ms**, `set_case` 7,836 ms; `F06` רשם 10,947 ms. מחוץ לשני אלה שום תרחיש לא חצה 3.2 שנ' | הנתיב התלת-ממדי |
| **N2-13** | **S2** | **זמן העצירה נקבע ע"י מהירות ה-ingest ולא ע"י הפיזיקה.** `stopAt writeNow` עוצר איפה שהסולבר נמצא, וה-ingest רץ מאחוריו דרך 9p. אותו fixture: שלב 1 ב-±7 %, שלב 2 **פי 2.3**. **שרשרת אינה ניתנת לשחזור** | `runloop.py:578` + `backend.py:818` |
| **N2-14** | **S2** | **כל מסירה 2D→3D בשרשרת לא-פיזיקלית:** 12–572 תאי ואקום מתוך 9,375, ב-3 מ-8 ריצות גם לחץ/טמפ' אפס או שלילי, `T_max` עד 9.0e+08 K | ההמרה לשלב 3 |
| N2-05 | S3 | `set_case` חוסם 3.2–5.6 שנ': `plan_levels` **פעמיים** לכל קריאה, ו-`level_map` בונה את הרשת העדינה המלאה (320³ = 32.8 M תאים) **לכל אזור בנפרד** | `core/refine.py:194`, `:302` |
| N2-08 | S3 | `feed_result` לצופה התלת-ממדי חוסם 2,183 ms מול תקציב G4 של 1,000 | `results._open_3d` |
| N2-11 | S3/S4 | תוויות ציר Y מתנגשות בגרף מדים רב-פאנלים (1D); בפאנל יחיד תקין | `plots.figure_gauges_nd` |
| N2-06 | S4 | ספירת תאים בת 20 ספרות בהודעת החסימה (`cell=1e-9`) | הודעת הסף |
| N2-10 | S4 | הכיתוב על כפתור "Summary CSV" קטוע — מוצג "ummary CSV" בכל צילום של Results | `gui/results_panel.py` |

**N2-07 ו-N2-05 הם תיקון אחד.** להעביר ל-preview את התוכנית ש-`validate_case`
כבר חישבה פותר את שניהם — הנכונות **וגם** הקריאה השנייה של 1.93 שנ'.
**לא לטפל בהם בנפרד.**

**מה שחוסם את N2-07:** צריך להחליט מאיפה `preview_panel` משיג `rho0` —
יש שתי טבלאות חומרים (`_MATS` הנייטיבית מול `solvers.foam.materials.MATERIALS`)
ומה קורה כשהחומר לא בטבלה של הסולבר הנבחר.
**ובדיקה שחייבת להתלוות לתיקון:** `test_gui_refine_preview.py:149` קוראת
בעצמה `plan_levels(c2)` **בלי `rho0`** — היא משכפלת את הבאג ומאשרת אותו
מול עצמו, וכל הבדיקות בקובץ על TNT, החומר היחיד שבו אין פער. בדיקה
שמשווה preview מול validate על **ANFO** הייתה נכשלת מיד.

**הניסוי הבא שיכריע את הקריסה לסירוגין (N2-14 נלווה):** הכשל שוחזר
**1 מתוך 17** (≈6 %) והמקרה שמור ב-`/root/night2_keep/attempt_10/`.
להריץ את שלב 3 מחדש **מהמקרה השמור עם כתיבות מלאות** ולעקוב אחרי
`min(rho.air)`/`min(rho.expl)` לכל צעד. **אם הוא קורס דטרמיניסטית משם,
אפשר לבדוק תיקון בדקות במקום בשעות.** *(הראיות השמורות לא מספיקות: blastFoam
כתב שדה פנימי מלא רק בתיקיית הזמן ההתחלתית.)*
**מה שנפסל במדידה:** "מסירה גרועה ⇒ קריסה". לריצה שקרסה היה אחד מתנאי
ההתחלה ה**נקיים** ביותר (24 תאי ואקום מול 572 בריצה ששרדה). המתאם הפוך.
**וחתימת ה-SIGFPE זהה ללילה הראשון אך המקרה הזה הוא בלי AMR** — כלומר
"AMR הוא הסיבה" נכון למקרה ההוא ואינו הכללה; המשותף הוא `decode()`
שמחלק ב-`rho` שמתאפס.

**המלצה עומדת (CRLF):** להגדיר `core.autocrlf=input` ב-config של הריפו או
לנרמל את ~30 הקבצים בקומיט ייעודי אחד. עד אז **כל** קומיט במכונה הזו
חייב `git -c core.autocrlf=input`, אחרת הוא משכתב קבצים שלמים.

---

## מטריצת הבדיקות

> **עדכון 2026-09-12:** הרשימה למטה **אינה מלאה**. חמש חבילות יתומות אינן
> מופיעות בה ורצות בפועל: **`test_revolve3d`** (0.4 שנ', 30/30 PASS),
> `_e2e_gui_native_warn`, `_e2e_foam_chain`, `_e2e_foam_probe_study`,
> `test_viz3d_e2e`. **`test_revolve3d` שייך למטריצה המהירה** — הוא מהיר,
> נייטיבי וירוק. צוואר הבקבוק של המטריצה המהירה הוא **`test_blast2d`
> ב-162.1 שנ' — 47 % מזמן הקיר של כל 30 החבילות.**
>
> **מטריצת ה-GUI** (`_qa_gui_harness.py`, 58 תרחישים) רצה במלואה לראשונה
> ב-2026-09-12. הרצה: ראה `night_artifacts/NIGHT2/harness_loop.ps1`.
> **יציאה 0 אינה "עבר"** — `qa.check` שנכשל לא עוצר תרחיש ובדיקות שעברו
> אינן נרשמות; האמת ב-`findings.jsonl`, וסקריפט הסיכום הוא
> `night_artifacts/NIGHT2/summarise.py`.

```
cd blastlab/tests

# מהיר, ללא WSL (להריץ אחרי כל משימה)
python test_regression.py         # native byte-parity - MUST stay green
python test_foam_writer.py        # case-generation goldens
python test_foam_reader.py        # ascii+binary parsers, probes merge
python test_case_validate.py      # cap gating per backend
python test_foam_env.py           # WSL env probe parse, cleanup policy, settings
python test_hardware.py           # N21: machine identity, cache TTL, host RAM, native caps
python test_adaptive_interval.py  # writeInterval controller
python test_foam_live_due.py      # live-frame cadence gate
python test_gui_drain.py          # GUI queue-drain resilience
python test_gui_results_fields.py # Results panel (fields, S2 QA checks)
python test_gui_results_anim.py   # Animation tab
python test_refine.py             # refined-mesh plan + AMR remap + validation guards
python test_bc_trigger.py         # boundary kinds, end time, trigger gauge, gauge markers
python test_foam_postmortem_decomposed.py  # loading a parallel AMR run
python test_foam_resume.py        # P1-5: restart points + the AMR FO disable
python test_gui_title_preview1d.py # Results title line + the 1D model preview
python test_gauge_summary.py      # per-gauge peak/arrival/impulse
python test_report.py             # field CSVs + HTML report
python test_gui_gauge_summary.py  # Gauges-tab table + CSV (headless Tk)
python test_gui_run_browser.py    # foam run browser (headless Tk)
python test_gui_refine_preview.py # zones form/preview + show-mesh
python test_gui_amr_form.py       # AMR card + per-frame mesh + 1D live autoscale
python test_gui_solver_mode.py    # sidebar solver mode
python test_foam_ingest_order.py  # ordered ingest + accumulators
python test_foam_amr_ingest.py    # AMR per-time ingest on fake time dirs
python test_viz3d_sampling.py / test_viz3d_hooks.py / test_viz3d_scene.py / test_viz3d_panel.py
python test_blast2d.py            # 2D native physics
python _qa_gui_harness.py --smoke # visible-window harness smoke (~1 min)

# slow, no WSL - run on its own, WITHOUT a timeout (P2-9)
python test_blast3d.py            # 3D native physics, ~25 min here

# WSL (קודם לוודא WSL פנוי: wsl.exe -d Ubuntu -- pgrep -a blastFoam ריק)
python test_foam_1d_vs_native.py  # physics gates (~2 min)
python test_foam_2d.py            # axisym + planar (~3 min)
python test_foam_3d_smoke.py --tiny
python test_foam_parallel.py      # np1 vs np2 + determinism (~5 min)
python test_foam_postmortem.py    # live-vs-loaded round trip
python test_foam_features.py      # multi-charge + activation none
python test_foam_kb_anchor.py     # KB free-air + C4/TNT (~2 min)
python test_foam_stop.py          # SIGSTOP/writeNow regression
python _e2e_foam_obstacle2d.py / _e2e_foam_obstacle3d.py
python _e2e_foam_refine2d.py / _e2e_foam_refine3d.py       # ~3 min each
python _e2e_foam_amr2d.py / _e2e_foam_amr3d.py             # ~3 / ~6 min
python _e2e_foam_chain_amr.py     # chained AMR stage (untracked - ראה P0-1)
python _e2e_gui_foam.py           # real-GUI session
```

**שים לב:** `test_foam_stop` ובדיקות כבדות-זיכרון נכשלות באופן מזויף אם סולבר blastFoam זר
רץ ברקע. בדוק לפני שאתה מאשים את הקוד.
