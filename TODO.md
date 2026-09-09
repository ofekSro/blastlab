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

## P0 — דחוף: סיכון לאיבוד עבודה / הריפו שבור

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

מתוך QA_REPORT §7, ועדיין נכון: ריצת afterburn `miller`, פתיחת קבצי ה-VTK בפועל ב-ParaView,
volume render עם Min/Max ידני, תוצאה ישנה בלי מפות שיא, DPI שאינו 100 %, מסך שני.
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

## מטריצת הבדיקות

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
python test_blast3d.py            # 3D native physics
python _qa_gui_harness.py --smoke # visible-window harness smoke (~1 min)

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
