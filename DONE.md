# DONE.md — כל מה שנעשה בפרויקט blastlab

> **מה זה.** התיעוד המלא של העבודה שהושלמה. אוחד ב-2026-09-09 מתוך ארבעה מסמכים
> שנמחקו: `TASKS.md` (§3 התור, §4 הבריפים, §6 אינדקס המזהים, §7 מאומת-נכון),
> `QA_REPORT.md` (סבב QA של 2026-09-07), `tasksforofek.md` (מה שנסגר מתוכו),
> ו-`amr_prompt.md` (הפרומפט שהוליד את AMR, בוצע).
> **מה שעוד לא נעשה נמצא ב-[TODO.md](TODO.md)** — זה הקובץ היחיד לניהול עבודה מכאן.
>
> **למה זה נשמר.** הערות בקוד מצטטות את מזהי ה-ROADMAP הישנים (`B23`, `G7`, `A5`,
> `N7`, `W1`…). §5 כאן הוא הפתרון שלהם — אל תמחק אותו.
> ההיסטוריה המלאה של ROADMAP.md: `git show 73ca834:ROADMAP.md`.
> טקסט טכני נשאר באנגלית במכוון — הוא הועתק מהמדידות עצמן.

---

## תוכן

1. [ציר הזמן — T0–T70](#1-ציר-הזמן--t0t70)
2. [T0–T26 — הבסיס, התיקונים והיכולות הראשונות](#2-t0t26--הבסיס-התיקונים-והיכולות-הראשונות)
3. [T27–T70 — פירוט מלא](#3-t27t70--פירוט-מלא)
4. [המספרים המדודים — פיזיקה וביצועים](#4-המספרים-המדודים--פיזיקה-וביצועים)
5. [אינדקס מזהים (B / G / A / N / W)](#5-אינדקס-מזהים-b--g--a--n--w)
6. [סבב ה-QA של 2026-09-07 (QA-01…QA-35)](#6-סבב-ה-qa-של-2026-09-07-qa-01qa-35)
7. [מאומת נכון — אל "תתקן"](#7-מאומת-נכון--אל-תתקן)
8. [בייסליינים, גרסאות קובץ וקומיטים](#8-בייסליינים-גרסאות-קובץ-וקומיטים)

---

## 0. 2026-09-17 — Q1: המעבר ל-PySide6 (שלב 0, M0–M4) + סקאלת הצבעים באנימציה

> העבודה הפתוחה והמיילסטונים הבאים (M5–M7) ב-[TODO.md](TODO.md) §Q1;
> התוכנית המאושרת ב-`~/.claude/plans/sunny-twirling-lampson.md`.
> ה-GUI של Tk (`blastlab/gui/`) נשאר ברירת המחדל עד M5.

**שלב 0 · שחרור המכונה.** WSL נפל על `CreateInstance/E_FAIL` בגלל
`[wsl2] vmIdleTimeout=-1` ב-`.wslconfig` — ערך לא חוקי (המפתח במילישניות;
`-1` מתועד רק ל-`[general] instanceIdleTimeout`), והוא מפיל את WSL לגמרי
בלי אזהרה. בנפרד, C: היה מלא (0.6GB מ-1862) כי `auto_cleanup=false`
בהגדרות נתן ל-`/root/blastlab_runs` לתפוח ל-374GB; פונו 111.9GB והניקוי
הוחזר עם תקרה של 150GB ו-10 ריצות שמורות. git הותקן על Windows
(`Git.MinGit`, scope user) כך שגרסאות לא תלויות יותר ב-WSL. הפירוט
המלא, כולל הסיכונים שנשארו פתוחים, ב-[TODO.md](TODO.md) §Q1.

**M0 · תשתית.** נוצרו `requirements.txt` ו-`pyproject.toml` (לא היו כלל).
קוד שהיה נעול ב-`gui/` עבר לבתים נייטרליים, עם shims לתאימות:
`gui/settings.py` → `core/settings.py` (ה-backend של foam ייבא אותו מ-`gui`!),
`gui/mode.py` → `core/mode.py`, `chain_panel.stage_errors` → `core/chain.py`,
`gui/worker.py` → `solvers/worker.py`, `app._solve_stage` + `_write_trigger_remap`
→ `solvers/jobs.py`, `view3d_panel.Feed3D` → `viz3d/feed.py`,
`preview_panel.case_geometry` → `viz3d/geometry.py`.

תהליך המציג התלת-ממדי נכתב מחדש: `viz3d/protocol.py` מחזיק טבעת זיכרון
משותף דו-תאית (`SharedFrameRing`, latest-wins, חותם seq לכל תא לזיהוי
קריאה קרועה) ו-`FrameLayout` שמחשב את מפת הבתים מה-init של הסצנה;
`viz3d/process.py` מחזיק את הצינור; `viewer_main(conn, opts)` הוא עכשיו
אפליקציית Qt קטנה עם חלון רינדור לכל משטח (`run`/`results`/`setup`) במקום
לולאת VTK חוסמת אחת; `client.py` הוא מתאם דק כדי שמסלול ה-CLI ישרוד כלשונו.
**התור החסום נעלם:** 50 פריימים שאף אחד לא קורא חוזרים מיד, והקורא המאוחר
מקבל את החדש (`test_viz3d_scene.py` §A8 נכתב מחדש סביב זה).

**M1 · קליפה + Run + מציג מוטמע.** `blastlab/ui/` עם 11 מודולים:
`theme` (אותה פלטה, QPalette+QSS, ~30 אייקונים ב-QPainter במקום PIL),
`widgets`, `dialogs` (מודאלים מוחלפים בבדיקות), `bridge` (חוט→GUI),
`pg_plots` (pyqtgraph: `ScalarImage`/`MeshOverlay`/`LiveSlicePane`),
`run_panel`, `run_controller`, `view3d_host`, `viewer_link`, `testing`, `app`.
`python -m blastlab --qt [--case FILE]`.

**שלושה דברים שנמדדו ולא נוחשו:**
1. **re-parent כפול של חלון זר = access violation.** `foreign.setParent(None)`
   ואחריו הזזת המכל הרג את התהליך; אותו דבר בסגירה אם Qt מפרק את המכל
   אחרי שהילד כבר מת. הפתרון: המכל נבנה **פעם אחת** ורק *נודד* בין
   הלשונית לחלון הצף (`_FloatWindow`), ובסגירה מפרקים אותו בעוד הילד חי
   ומרוקנים את תור ה-DeferredDelete.
2. **`RunController.running`** לא יכול להסתמך על `is_alive()` לבד — החוט
   ממשיך להתפרק מיקרו-שניות אחרי `done`, ואז ריצה חדשה נדחית סתם.
   נוסף `_done_seen`.
3. **תהליך המציג נפתח רק לקייס תלת-ממדי.** prewarm גורף החזיק VTK
   (~150MB) בסשן דו-ממדי, על מכונה של 7.7GB ש-WSL לוקח 5 ממנה.

**M2 · לשונית Setup.** הטופס נבנה מ**מפרט שדות** חסר-טולקיט
(`ui/setup_spec.py`) ומנוע (`ui/fieldform.py`) במקום 1,076 שורות בנייה
ידנית. המנוע מספק בדיוק את `form.v[name]` שהיה ב-Tk — `get()` מחזיר str,
`set()` מפעיל את הקריאות, `trace_add` — ולכן `get_case()`/`set_case()`
עברו כמעט כלשונם, וכך גם הבדיקות שנוגעות בשדות. שלושת ה-hooks
האימפרטיביים: מצב סולבר, תת-קבוצת AMR, וציר סימטרי. התצוגות המקדימות
חולצו ל-`output/preview_draw.py` והפאנלים של Tk הם עטיפות דקות מעליו,
כך ששתי בדיקות ה-Tk הקיימות הן ההוכחה שהחילוץ לא שינה התנהגות.

**ארבעה דברים שנמדדו ולא נוחשו (M2):**
1. **`QFormLayout` מניח את השדה מעל התווית** כשהוא צר מדי. נמדד: תווית
   x=17 w=132 ושדה x=21 w=272 באותה שורה, כלומר תווית של תו אחד. כל
   השורות הן `QGridLayout` מפורש עם עמודת כיתוב בעלת רוחב קבוע.
2. **חוזה פיזור נדחה הוא חובה, לא ליטוש.** `set()` מתוך trace מוחל מיד
   אבל הפיזור שלו נדחה עד שהנוכחי נגמר (אותו חוזה של
   `core/mode.py:SolverMode`) — בלעדיו ה-hook של הציר הסימטרי איבד את
   `cx` לסירוגין.
3. **`QCheckBox.clicked` לא מעביר את ה-bool** באופן אמין דרך ה-binding;
   ה-handler קורא `isChecked()` במקום לסמוך על הארגומנט.
4. **שני באגים אמיתיים בטופס הישן:** `order` נותח מחוץ לסוגרי השגיאות
   והעיף `IndexError` מתוך `get_case` על תיבה ריקה; ו-`eos`/`order`
   נקראו בשני מצבי הסולבר אף שהשורות שלהן native-only — ה-writer של
   foam אינו קורא אותם, ו-`validate_case` מתעד זאת.

**M3 · לשונית Results.** קליפה (`ui/results_panel.py`) עם בורר תוצאות,
שמונה ייצואים ושורת Title, ושלושה תת-פאנלים נפרדים
(`results_fields`, `results_gauges`, `results_anim`) — וכל הכתיבה
לדיסק ב-`ui/exports.py`, שם היא נבדקת בלי חלון בכלל.

**ההיפוך המרכזי:** ב-Tk כל אינטראקציה בנתה Figure שלמה והעבירה אותה
לבונה רשת הפאנלים עם n=1. כאן הפאנל קיים ברציפות, ולכן החלפת שדה או
תצלום היא **העלאת מערך אחת**: ה-`ScalarImage` ממופתח על
`(תוצאה, צורות הפאות, החתך)` ונשמר; החלפת מישור בתלת-ממד כן בונה מחדש,
כי הפאות והמסכה שונות. `output/plots.py` נשאר האחראי היחיד על הקבצים,
ולכן `PNGs` ו-`Report` ממשיכים לכתוב את הרשת המלאה — וה-tooltips שלהם
אומרים זאת, כי מעכשיו המסך והקובץ שונים **בכוונה**.

**שלושה דברים שנמדדו (M3):**
1. **ל-`extend='max'` אין מקבילה ב-pyqtgraph.** חיתוך האחוזון ה-99.5
   (הכלל הועתק מ-`_panel_grid_figure`) מוכרז במילים: סיומת לכותרת
   **זהה לזו שב-PNG המיוצא**, וסיומת לתווית פס הצבעים.
2. **טבלת המדים חנקה את הגרפים** — נמדד ב-900x600 עם שלושה מדים:
   192px טבלה מול 136px קנבס. הטבלה חסומה ל-4 שורות וגוללת מעבר לכך
   (בדיוק `height=4` של ה-Treeview), והקנבס לוקח את המותח. זו אותה
   בעיה של N2-09, בכיוון ההפוך.
3. **`apply_theme` מעולם לא צבע שום כותרת.** הוא העביר
   `text.lstrip('#')` ל-`LabelItem`, ש-`mkColor` דוחה, והבלוק כולו
   עטוף ב-try/except — כלומר הכשל נבלע בשקט מאז M1.

**pyplot יצא מתהליך ה-GUI.** `pg.colormap.getFromMatplotlib` מייבא
`matplotlib.pyplot` רק כדי לקרוא טבלת צבעים, ולכן די היה **לצייר שדה
על המסך** כדי לגרור פנימה את מנהל הדמויות הגלובלי — בדיוק מה
ש-`output/pyplot_bridge.py` קיים כדי למנוע. הטבלה נדגמת עכשיו ישירות
מ-`matplotlib.colormaps` וה-LUT זהה בית-בית לקודם.

**M4 · Chain + דפדפן הריצות.** `ui/chain_panel.py` ו-`ui/run_browser.py`
(QDialog + QTableWidget), ובית נייטרלי חדש `solvers/foam/runs.py`
לקריאת תיקיות הריצה, ש-`gui/run_browser.py` מייצא מחדש כדי שהמייבאים
והבדיקה שלו לא ייגעו.

**מובלע אחד לשגיאות, והדיאלוג אחרון.** חמישה `showerror` הפכו
ל-`error_sink(title, lines)` ו-`run()` מחזיר False בסירוב, ולכן בדיקה
נשענת על ערך ההחזרה ועל השורות שנרשמו ולא על מודאל. P2-8 חל כאן במלוא
עוצמתו — `QMessageBox` הסטטי מריץ לולאת אירועים מקוננת ויתקע דרייבר
לא-אינטראקטיבי בדיוק כמו `messagebox` — ולכן **הנימוק מגיע לשורת הסטטוס
וללוג לפני שנוגעים בדיאלוג**. שתי הבדיקות מחליפות את הדיאלוג בפונקציה
**שזורקת** ומאמתות שהסירוב עדיין מתועד במלואו; זו תכונה, לא הערה.

**שני דברים שלא רואים בקוד אבל אסור לשנות:** תיקיית ה-workspace נוצרת
**רק** אחרי שכל הבדיקות עברו (היא נוצרה גם כשהריצה סורבה), ו-
`stage_errors` רץ **אחרי** חיווט הפרופילים כדי לשפוט את מה שבאמת ירוץ.
בדפדפן: `alive is None` מסורב כמו `True` — "WSL לא דיווח" אינו
"הסתיים" — והמילוי הדו-שלבי עובר ב-`ThreadBridge`, כך שה-`queue.Queue`
וה-poll של `after` נעלמו והבחירה נשמרת לפי **שם**, כי סדר השורות יכול
להשתנות בין שני המעברים.

**באג אמת שנחשף ב-M4.** ההערה של N2-13 אומרת שהשרשרת נועצת
`adaptive_write=False` על כל שלב כדי שתהיה משוחזרת — אבל זו הייתה
**תכונה מאולתרת** על ה-dataclass, ו-`asdict()` לא רואה כאלה: קובצי
ה-JSON שנשמרו "לשם שחזור" איבדו בדיוק את הדגל שהפך אותם למשוחזרים,
וריצה חוזרת מהם חזרה לבקר האדפטיבי. `adaptive_write` הוא עכשיו שדה
מוצהר בשלוש מחלקות ה-Case (גרסת קובץ 13; ברירת המחדל `True` היא
ההתנהגות הקיימת, ו-`backend.py` קרא אותו ב-`getattr` מאז ומתמיד).

**מה עדיין לא ב-Qt:** כלום מהפאנלים — נשאר להחליף את ברירת המחדל (M5),
סבב שוויון (M6) ו-59 תרחישי ה-QA (M7).

---

**סקאלת הצבעים של האנימציה המיוצאת** (בקשת בעלים, מחוץ למעבר ל-Qt).
האנימציה כיוונה מחדש את הסקאלה **בכל פריים**, ולכן פס הצבעים סימן משהו
אחר בכל תמונה: אי אפשר היה להשוות שני פריימים, והגל לעולם לא נראה דועך.
נוסף לקייס `anim_scale` עם שלושה מצבים (גרסת קובץ 12): `run` — טווח אחד
לכל הסרטון, **ברירת המחדל החדשה**; `frame` — ההתנהגות הישנה, שעדיין
שימושית לריצה שסופה כולו כחול אחיד; ו-`manual` — טווח ב-kPa שאתה נועץ
(`anim_clim`), הדרך היחידה להשוות שני סרטונים זה מול זה.

**מה שלא מובן מאליו כאן:** (א) הטווח של `run` **מחריג תאי מכשול** — הם
מחזיקים לחץ סביבה, והיו נועצים את המינימום באפס בכל מקרה עם גאומטריה.
(ב) הבחירה נרשמת ב-`res.meta`, ולכן ייצוא מאוחר מלשונית Results מכבד את
בחירת הריצה בלי להחזיק את הקייס, וריצה שנטענת מהדיסק נופלת ל-`run`.
(ג) טווח ידני חסר, הפוך או לא-סופי **נופל חזרה** ל-`run` עם הערה מודפסת,
במקום לכתוב סרטון בלתי קריא. (ד) תווית פס הצבעים ושורת ההתקדמות נגזרות
מאותה עובדה אחת, ולכן אינן יכולות לסתור: כשהטווח קבוע השורה מדפיסה
אותו, וכשאין טווח שתיהן אומרות `rescaling per frame`.

**באג שנחשף בדרך:** `plots.set_frame` בלי טווח קרא `nanmax` על פריים
שכל תאיו מוסתרים (מישור חתך שעובר כולו בתוך מכשול — אפשרי בתלת-ממד),
הדפיס `RuntimeWarning` והעביר ל-matplotlib `clim=(nan, nan)`; NaN נכשל
בכל השוואה, אז השומר `hi <= lo` לא תפס אותו. עכשיו נבדק `isfinite`
תחילה, והטווח הוא `(0, 1)` — בדיוק כמו ב-`ui/pg_plots.py`, שכבר שמר על
זה, ולכן רק מסלול ה-matplotlib היה פגיע.

**והתיקון שבאמת היה חשוב, שנמצא רק ב-e2e על ריצה אמיתית:** הטווח של
`run` היה **כשר וחסר תועלת**. הקלטה שמתחילה ב-t=0 מתחילה במטען
הלא-מורחב, ולכן הטווח נקבע מכמה תאים בפריים הראשון וכל הפריימים אחריו
יצאו כמעט שחורים. המדידה, על ריצה דו-ממדית אמיתית של 5 ק"ג ב-32
פריימים:

| | kPa |
|---|---|
| שיא פריים 0 (המטען) | 2.76e6 |
| האחוזון ה-99.5 הגבוה ביותר לפריים | 4.50e4 |
| שיא הפריים האחרון | 7.68e3 |
| **חלקו מפס הצבעים** | **0.28 %** |

זו בדיוק הבעיה של מפות ה-peak (1e7 kPa במטען מול שדה של 1e2, שהפכו את
המפה לנקודה אחת), ולכן הופעל אותו פתרון שכבר קיים בפרויקט: חיתוך
האחוזון ה-99.5, **רק** כשהשיא באמת רחוק מהגוף. הכלל עבר למקום אחד
(`output/plots.py`: `CLIP_PERCENTILE`, `CLIP_RATIO`, `CLIP_NOTE`), ושלוש
השכבות — רשת הפאנלים, טווח הסרטון ופאנל ה-Fields של Qt — מייבאות אותו
במקום להחזיק שלושה עתקים שיסחפו. לרצף פריימים החסם הוא **האחוזון
ה-99.5 הגבוה ביותר בין הפריימים**, כלומר הבהיר ביותר שהגוף של פריים
יחיד מגיע אליו. אותה ריצה נותנת עכשיו `-30 .. 4.87e4 kPa`, והפריים
האחרון מקבל **15.8%**; ה-GIF גדל מ-626KB ל-2.0MB, שזו אותה עובדה מהצד
השני. **ביצועים:** האחוזון נדגם (200k תאים לפריים; נמדד על 150 פריימים
של 1000×1000: 5.7 שנ' → 3.4, מהן 2.5 הן מעבר ה-min/max שמשולם בכל
מקרה), והניגון ב-Results משמר את התוצאה לפי סקאלה.

השורות נוספו לכרטיס Outputs בשני הטפסים, ותיבות ה-min/max מוצגות רק
במצב הידני. **נסגר ב-M3:** לתצוגת Animation ב-Results יש בורר משלה,
שחל גם על הניגון במסך וגם על מה שהייצוא כותב, ומאותחל מהבחירה שהריצה
עצמה רשמה — כך שסרטון שמיוצא מהלשונית זהה לזה שהריצה כתבה, אלא אם
נבחר אחרת.

---

**בדיקות שנוספו:** `test_viz3d_protocol.py` (25), `test_ui_drain.py` (36),
`test_ui_run_panel.py` (58 — כולל אוריינטציית ה-`ImageItem`, מסכת המכשול,
ספירת תאי AMR וקיפול לוג ה-AMR), `test_ui_view3d_host.py` (38),
`test_ui_no_vtk_in_main.py` (9 — נועל את הכלל "אין VTK בתהליך ה-GUI"),
`test_ui_setup_form.py` (88), `test_ui_preview.py` (41),
`test_anim_scale.py` (56 — כולל השוואת פיקסלים בין הסרטונים, ובדיקה
שאותו קייס מייצר אותו תוצר בשני הטפסים), `test_ui_results.py` (104),
`test_ui_three_surfaces.py` (33 — שלושת המשטחים מול חיבור אחד),
`test_ui_no_mpl_pyplot.py` (18 — נועל את הכלל "אין pyplot בתהליך
ה-GUI", בתהליך נקי כי `sys.modules` גלובלי),
`test_ui_chain.py` (42), `test_ui_run_browser.py` (48),
`_e2e_ui_native.py` (35 — ריצה נייטיבית אמיתית דרך החלון האמיתי, עד
לייצוא קבצים; זו הבדיקה שמצאה את בעיית סקאלת הצבעים),
`_e2e_ui_native_warn.py` ו-`_e2e_ui_view3d.py` (ריצות אמיתיות).
`test_gui_refine_preview.py` עודכן ל-`solvers.jobs.solve_stage`.
קומיטים: `b18a9cb` (M0+M1), `68d23dc` (M2), `d54a4e3` (תיעוד),
`8e107fe` (סקאלת הצבעים).

---

## 1. ציר הזמן — T0–T70

**71 משימות, כולן סגורות.** T0–T24 עד 2026-09-05, T25–T48 ב-09-07 (סבב QA + סגירת
ROADMAP), T46–T61 ב-09-08, T62–T70 ב-09-09.

| # | משימה | מזהים | היקף | הושלם |
|---|------|-----|--------|--------|
| T0 | Commit untracked work | A9 | 10 min | 2026-09-02 |
| T1 | Harden the foam stop/ingest path | B1, B2, B15 | S–M | ✔ |
| T2 | Wrong-data display: 3D replay slice + viewer final frame + thinning | B3, B4, B20 | S | ✔ |
| T3 | Units & labels: kPa everywhere, impulse naming | B8, B9 | S | ✔ |
| T4 | Runs-dir safety: unique dirs, live-run guard, orphan reaping | B13, B14 | S | ✔ |
| T5 | Papercuts bundle | B7, G1, B22, G6a | S | ✔ |
| T6 | Chain validation + visible/stoppable foam preflight | B5, B6, G5 | M | ✔ |
| T7 | Native solver warnings through hooks | B11 | M | ✔ |
| T8 | Native fixes with ONE re-baseline | B10, B12, B18 | S | ✔ |
| T9 | Extract the shared foam run loop | A1, A2, A3, A4(foam) | M | ✔ |
| T10 | Foam accumulator correctness | B16, B17, B21 | S–M | ✔ |
| T11 | Peak-overpressure / impulse views in Results | N1 | M | ✔ |
| T12 | Per-gauge engineering summary + CSV | N2, B9 | S–M | ✔ |
| T13 | 3D viewer colour-range plumbing + viz3d dead code | B19, A4(viz), A8 | S | ✔ |
| T14 | Foam run browser + auto-cleanup | N8 | M | ✔ |
| T15 | VTK/ParaView export | N4 | S | ✔ |
| T16 | Afterburn model | N3 | M | ✔ |
| T17–T19 | Local (static) refinement: core → foam → 3D viewer | N15 | M–L | ✔ |
| T20–T24 | Dynamic AMR: core → ingest → GUI → 3D viewer → live slice/wedge fix | N16, B25 | M–L | 2026-09-05 |
| T25 | QA S1: validation/preview memory safety, defaults, finite input | QA-01..04, 14, 15; B27, G10 | M | 2026-09-07 |
| T26 | QA S1: chain feed3d lifecycle + profile-stage validation | QA-05, 06; B26 | S | 2026-09-07 |
| T27 | QA: layout — Run-tab 3D viewport, status card height, truncations | QA-17, 25, 27; G11 | S–M | 2026-09-07 |
| T28 | QA: chain feedback (stage select, workspace, stage prefix) | QA-23; G12 | S | 2026-09-07 |
| T29 | QA: validation & feedback bundle | G3, QA-16, 22 | M | 2026-09-07 |
| T30 | QA: user-named runs + loaded-run replay | N9, QA-24; G2 | S–M | 2026-09-07 |
| T31 | QA: UI stalls + preview extras + viewer field availability | G4, G8, QA-18, 21, 17 | M | 2026-09-07 |
| T32 | QA: theme/affordance + accelerators + persistence | G9, G13, QA-19, 28, 29 | S–M | 2026-09-07 |
| T33 | QA: papercuts | QA-20, 26, 30..35 | S | 2026-09-07 |
| T34 | GUI: global solver mode (sidebar selector; hide, don't grey) | — | L | 2026-09-07 |
| T35 | `test_foam_parallel` determinism check | B23 | S | 2026-09-07 |
| T36 | Mass/energy-conserving resolved-charge init in 2D/3D | B24 | S | 2026-09-07 |
| T37 | Hardening bundle: dead code, shared constants, stdout canaries | A4, A5, A6, A7 | S | 2026-09-07 |
| T38 | Live-view niceties: foam cadence hint, 2D live Min/Max | G7 | S | 2026-09-07 |
| T39 | Charge-mass rasterisation deficit (foam) | N5 | S–M | 2026-09-07 |
| T40 | Arrival-time characterisation: AMR probe cell + foam near-field lag | N16-a, W1 | M | 2026-09-07 |
| T41 | Chains INTO blastFoam (profile-initialised foam stages) | N7 | M–L | 2026-09-07 |
| T48 | Hardware-aware run plan: cores + RAM → MPI ranks and a cell cap | N17 | S–M | 2026-09-07 |
| T42 | Parallel AMR (direct `processor*/` reads) | N16-b | M | 2026-09-07 |
| T43 | Resume a stopped foam run | N6 | M | 2026-09-07 |
| T44 | Gauge fields beyond p (foam) | N12 | S–M | 2026-09-07 |
| T45 | CSV export of field maps + one-click HTML report | N14, N13 | M | 2026-09-07 |
| T46 | Materials beyond TNT for the native solvers | N11 | M | 2026-09-08 |
| T47 | MUSCL second-order native reconstruction (opt-in) | N10 | L | 2026-09-08 |
| T49 | Mesh overlay on the animation a run writes | N15 | S | 2026-09-08 |
| T50 | Boundary kinds: transmit / reflect / terminate | N18 | M | 2026-09-08 |
| T51 | Trigger gauge: terminate and/or remap on arrival | N19 | M | 2026-09-08 |
| T52 | An end time for 1D and 2D runs too | N18 | S | 2026-09-08 |
| T53 | Gauges drawn in the live view and the animation | N19 | S | 2026-09-08 |
| T54 | AMR mesh in the exported video | N15 | S | 2026-09-08 |
| T55 | Bound the replay-frame record's memory | N15 | S | 2026-09-08 |
| T56 | MP4 export reachable (label, dialog, default, ffmpeg) | N15 | S | 2026-09-08 |
| T57 | Loading a PARALLEL AMR run (post-mortem) | N16-b | S | 2026-09-08 |
| T58 | A title line of your own on the Results figures | N20 | S | 2026-09-08 |
| T59 | 1D model preview: the spherical sector | N20 | S | 2026-09-08 |
| T60 | A boundary kind for the end of the 1D sector | N18 | S | 2026-09-08 |
| T61 | The 1D live pane was pinned to 10 kPa | G14 | S | 2026-09-08 |
| T62 | A 1D→3D remap could never run on blastFoam | N7 | S | 2026-09-09 |
| T63 | The trigger gauge leaves 1D (both solvers) | N19 | S | 2026-09-09 |
| T64 | Hardware honesty: per-field measured/cached/unknown, /proc/meminfo, no sticky cache | N21 | S–M | 2026-09-09 |
| T65 | Unknown hardware tightens the caps instead of loosening them | N21 | S | 2026-09-09 |
| T66 | Machine fingerprint + TTL for persisted hardware; settings write bugs | N21 | S–M | 2026-09-09 |
| T67 | Native cell caps from the Windows host's RAM (ctypes) | N21 | M | 2026-09-09 |
| T68 | An explicit `n_procs` is a ceiling, not a command | N21 | S | 2026-09-09 |
| T69 | Frame budgets derived from host RAM; cores beat MAX_AUTO_PROCS | N21 | S | 2026-09-09 |
| T70 | Dynamic AMR for profile-initialised stages | N7, N16 | S–M | 2026-09-09 |

**תלויות שהיו בתוקף בזמנן** (לתיעוד): T27–T33 עצמאיות זו מזו ולפני T34 (שפרס מחדש את
ה-GUI); T35 לפני כל משימה שמריצה `test_foam_parallel`; T40 לפני T42; T48 לפני T42.

---

## 2. T0–T26 — הבסיס, התיקונים והיכולות הראשונות

הבריפים המלאים של T0–T26 חיים בהיסטוריית git (`git show 73ca834:ROADMAP.md`, ובקומיטים
`ba37a65`, `73ca834`, `3cb800c`, `a6c7463`). מה שנעשה, לפי קבוצות:

**באגים בנתיב ה-foam (T1, T2, T10).** נסגרו: `uniform` internalField קטוע שהפיל
AttributeError; עצירה שהסלימה ל-kill והפילה את finalize; `TimeoutExpired` לא-מטופל בנתיבי
העצירה; replay תלת-ממדי שקידד קשיח את מישור x-z; הפריים האחרון שנעלם מה-playback; דילול
FrameStore; ingest מחוץ לסדר; peak/impulse מעופשים מה-FO; מרחקי עצירה במקרה רב-מטענים.

**בטיחות ותברואה של תיקיות ריצה (T4).** שמות ריצה ייחודיים, שמירה מפני מחיקת ריצה חיה,
קצירת יתומים.

**יחידות ותוויות (T3).** kPa בכל מקום, הפרדה בין אימפולס נטו לאימפולס הפאזה החיובית.

**סולברים נייטיביים (T7, T8).** אזהרות שעוברות דרך hooks במקום stdout; שורת גייג' אחרונה
כפולה; תזמון snapshot ב-1D; רשתות שהתכווצו בשקט בתא אחד. **re-baseline אחד** מרוכז.

**ארכיטקטורה (T9, T13).** לולאת ההרצה של foam שהייתה משולשת אוחדה; לוגיקת הגאומטריה
שהייתה מרובעת → `core/geometry.py`; ייבוא פרטי ב-postmortem; חיווט טווח הצבע בצופה
התלת-ממדי; קוד מת ב-viz3d; מסירת הודעות בקרה ב-viz3d.

**יכולות (T11–T16).** מפות שיא-לחץ ואימפולס ב-Results; סיכום הנדסי לכל גייג' + CSV;
דפדפן ריצות foam עם ניקוי אוטומטי (הגדרות ב-`%APPDATA%\blastlab`); ייצוא VTK/ParaView;
מודל afterburn (`none | miller`).

**עידון סטטי (T17–T19)** ו-**AMR דינמי (T20–T24)** — `adaptiveFvMesh`, אומדן ברירת מחדל
`densityGradient`, AMR ואזורים סטטיים סותרים זה את זה, רמת התצוגה מגבילה את רשת התצוגה,
סריאלי ב-v1. מקרה AMR תלת-ממדי לא מוגבל הרג פעם את ה-VM של 4 GB — ה-e2e התלת-ממדי מוגבל
ל-300k תאים.

**T25–T26 (QA S1).** בטיחות זיכרון בוולידציה ובתצוגה המקדימה, ברירות מחדל שעוברות
ולידציה, קלט לא-סופי נדחה, מחזור החיים של feed3d בשרשרת, ולידציה לשלב profile.
פירוט: §6 (QA-01…QA-06, QA-14, QA-15).

---

## 3. T27–T70 — פירוט מלא

### T27 — QA: פריסה (QA-17 layout, QA-25, QA-27) · G11 · 2026-09-07

Run tab — `RunPanel._place_sash` parks the ttk sash after the first real layout (weights
only share out *extra* space) and stops once the user drags it; the log box's requested
width dropped 380 → 280 so the sash can actually move. **Measured: live/3D pane 845 of
1280 px (66 %) and 62 % at 1100 px.** `View3DPanel`: control column 206 → 200 px, its
three tabs are scrollable (the Display tab was taller than the column and used to push the
timeline/Play strip off), and a rail button folds the whole column away — automatically
below 700 px until the user decides otherwise. `viewer.py`: HUD font follows the
render-window width (`_scale_hud`), the field scalar bar moved to x = 0.855 with 11/10 pt
text, and the surface-loads bar is horizontal along the bottom — untitled, because VTK
prints a horizontal bar's title straight over its tick labels, with the caption drawn as
its own viewport text actor (`LOADS_BAR_KEY` / `LOADS_CAPTION`). Truncations:
`theme.Tooltip` / `theme.tooltip` / `theme.wrap_to_width` added; `Card` titles wrap and
carry the full text as a tooltip; the 3D viewer's Min/Max boxes take a row each (an
auto-filled `1.88e+06` read `1.88265e+`); the 2D preview title is short; Run-tab stat chips
are packed before the buttons so the last chip survives at 1100 px.

Tests: test_regression byte-identical, the GUI matrix, test_viz3d_scene (new loads-bar
key), test_viz3d_panel (new P10 block). Harness at 1280×840: S00, C05, D04, E05, F04 (WSL,
idle before and after); B05 covers 1100×720 and 900×600.

### T28 — QA: משוב בשרשרת (QA-23) · G12 · 2026-09-07

Items 1–4 had already landed in `a6c7463` (`ChainPanel._run` parses every stage first,
`focus_stage` raises the offending form, the parse-error dialog reads "Stage n (nD): …",
`os.makedirs(ws)` runs only once the chain will start, workspace defaults to
`~/Documents/blastlab/chain_workspace`). This task closed the gap: the "must be
axisymmetric to feed 3D" refusal now also carries the stage prefix and raises stage 2 — it
was the one chain dialog that still left the switcher where it was. `test_gui_drain` gained
`chain_feedback_checks`; the G01 harness assertion, which asserted the *defect*
(`isdir(ws)` after five refusals), now checks the fix against a fresh workspace path.

### T29 — QA: ולידציה ומשוב (G3, QA-16, QA-22) · 2026-09-07

Verified from `a6c7463`, not redone: `CaseForm.get_case` raises ONE newline-joined
ValueError and `mark_fields` red-borders every offending entry; `_PointList._reject/_accept`
keep the text and print a one-line hint; `RunPanel.set_validation` drives the
"Case OK / N errors — see Setup" chip and disables Run + Initialise; `App.notify` + `_status`
is one window-wide status bar (chosen over a per-panel line — it reaches the user wherever
they stand). Closed here: every file dialog is titled (`_FilePicker` takes `title=`); a
disabled export button carries a tooltip saying why; `ResultsPanel._refresh` re-gates the
export row when the picker matches nothing (it returned early, leaving the previous
result's buttons enabled and live as no-ops — the E08 harness finding); `_export` answers
"Select a result before exporting."

### T30 — QA: ריצות בשם המשתמש + replay לריצה טעונה (N9, QA-24, G2) · 2026-09-07

(1) A "Name" box next to Run/Stop/3D View (`RunPanel.run_name` / `current_run_name` /
`set_run_name`); the result is labelled "\<name\> — 2D", `Result.meta['name']` is written,
Open case pre-fills from the file stem without overwriting what the user typed, and every
suggested export file name gains a slugged prefix. **NOTE: CTkEntry silently drops
`placeholder_text` once a textvariable is attached** — so the box carries a real label (same
for "Refresh every"). (2) `postmortem.load_run` collects a frame per written time — thinned
by halving exactly like the live loop, capped at `case.record_frames` (150), 3D reduced to
the run's own live slice via the now-public `backend.slice_geom_3d` — so a loaded run
replays; its label is "\<run dir\> (loaded, 2D)". (3) A label longer than 34 chars is elided
in the MIDDLE with the full text as a tooltip.

### T31 — QA: תקיעות UI + תוספות לתצוגה מקדימה + זמינות שדות (G4, G8, QA-18/21/17) · 2026-09-07

(1) `View3DPanel.feed_result` streams ONE snapshot per `after(1, …)` tick with a
"loading n/N snapshots" HUD line; a snapshot tick ~1 ms; the E06 gate reads 360 ms for
`_open_3d`, which is the one-off VTK scene build. (2) Setup 3D preview: 500 ms
**leading-edge** throttle on top of the `_key` cache — the first edit renders at once, the
rest collapse into one trailing rebuild. (4) A detonation point is now an octahedron so it
cannot read as one more spherical charge/gauge. (5) `_sync_field_availability` HIDES a
radio whose field is absent instead of greying it.

**NOT DONE — item 3 (off-thread AMR mesh edges), and why:** the premise was refuted.
`mesh_polydata` measures **320 ms on the first call (VTK warm-up, paid at scene build) then
5–8 ms per frame** on a 30³ display grid. Moving it to `Feed3D.make_payload` would hand VTK
objects built on the solver worker thread to the Tk thread — real risk, no measured gain.

### T32 — QA: ערכת נושא, קיצורי מקלדת, התמדה (G9, G13, QA-19/28/29) · 2026-09-07

Verified from `a6c7463`/`3cb800c`: a dedicated `seg` palette entry
(`('#ced6e0', '#3a3f46')`), `theme.Button` with `text_color_disabled=c('muted')`,
`set_running` swapping Stop between `card2`/muted and `danger`/white, matplotlib's
Back/Forward dropped (their disabled images rendered as dark-mode checkerboards),
`forms._entry` focus ring, `App._bind_accelerators` for Ctrl+O / Ctrl+S / F5 / Esc, and
geometry + appearance + refresh persisted through `gui/settings.py` (geometry only from a
really mapped window at least the minimum size). Closed here: 16 call sites build a plain
`ctk.CTkButton` and kept CTk's near-invisible disabled tint — `theme._apply_ctk_defaults()`
now writes the muted disabled text and the `seg` unselected fill straight into
`ctk.ThemeManager` at import, so every widget class inherits them.

### T33 — QA: papercuts (QA-20, 26, 30…35) · 2026-09-07

Verified from `3cb800c`: the Run log's `wrap='word'`, the `p max [kPa]` chip, the run
browser's scrollbar + warning dialog, `_panel_grid_figure(robust=True)` clipping the charge
spike out of the peak/impulse colour range, the collapsed AMR log, the closed logo file.
Closed here: **the `cells` chip** (`RunPanel._chip_cells`, fed from `on_frame(levels=)`) —
it reports REAL cells, not display cells (a display cell at level l stands for
`2**((disp-l)*ndim)` of them), appears with the first frame carrying a level map and hides
again. **QA-33:** `gauge_summary.gauge_labels(gauge_out, requested=None)` numbers every
label and, when the solver snapped a gauge, prints
"G1 (1.000, 2.000, 0.450) → cell (1.000, 2.000, 0.500) m"; every abbreviated column header
explains itself through one tooltip that follows the pointer's column (ttk headings take no
tooltip of their own). **QA-35:** the AMR disk note gives the run total as well as the
per-write figure.

### T34 — GUI: מצב סולבר גלובלי · 2026-09-07

Targeted refactor, not a rewrite. New `gui/mode.py` (`SolverMode` observable, no Tk) seeded
from `settings.json` (`solver`, fresh default `blastfoam`) before the panels are built;
sidebar block (segment + explainer + live WSL status) above Dark mode; `CaseForm` registers
rows/cards per scope and `_apply_mode()` grid_removes the other solver's (EOS / 3D Charge
resolution are native-only; Material, Detonation, Afterburn, Charge refinement, MPI ranks,
AMR / Refinement zones / Extra charges / Detonation points are blastFoam-only). The Solver
combo and every value coercion are gone — `get_case()` strips hidden fields to that solver's
defaults and never parses them. Chain: per-stage native|blastFoam switch. Results hides
"Foam runs…" and VTK in native mode. New `test_gui_solver_mode.py` (31 checks).

### T35 — דטרמיניזם ב-`test_foam_parallel` (B23) · החלטת בעלים · 2026-09-07

Option (b) as the owner decided. `CaseSpec.adaptive_write` (default True) + an
`adaptive_write=` kwarg on `solve_1d/2d/3d_foam`; when False the run never rewrites
`writeInterval`, so `writeControl adjustableRunTime` clips the time step onto the same
write times every time. **Nothing changes by default** — the goldens are untouched.

**Deviation from the brief, and why:** the pair is now bit-identical in every sample it
records — identical times, identical pressures. It is NOT identical in RECORD LENGTH
(372 vs 368 samples). That is not a numerical race: the arrival watcher reads a written time
on the Python side and then asks the solver to stop, so the solver takes a
wall-clock-dependent number of extra steps before the stop lands. The test asserts
(i) identical sample times over the common record, (ii) identical gauge records over it, and
(iii) the common record covers ≥ 95 % of the longer one (**measured 98.9 %**). Before the
change the pair differed by 91 samples with 470 Pa peak error; now 4 samples and 0 Pa.
Physics guard: pinned vs adaptive peaks/arrivals within 1 % (measured +6.6e-4 / −1.1e-3 on
peaks; 0.15 vs 0.15 ms and 0.339 vs 0.339 ms on arrivals).

### T36 — אתחול מטען משמר מסה/אנרגיה ב-2D/3D (B24) · 2026-09-07

`core/geometry.py` gained exact clipped charge volumes (`disc_box_area`, `charge_volume_2d`
planar/axisym-per-radian, `charge_volume_3d` Gauss-Legendre over the analytic disc-in-box
area; **verified against closed forms to 2e-16 and against a 1200³ brute-force count for a
corner-clipped ball to 1.7e-6**). Both resolve paths keep `rho_exp` and scale the products'
specific energy by `V_true / V_discretised`, so the initial energy equals the requested
charge's **to 4e-16** over 12 randomised charges/offsets.

**Why mass is deliberately NOT scaled:** JWL is exponential in rho0/rho, so scaling rho
would move the initial products pressure ~10 % for a 3 % volume error, while scaling e moves
it < 1 %. Mass keeps the staircase deficit on purpose — see N5/T39. Measured scale factors:
b2 ×0.957 (39 cells), b2 profile-source ×0.965 (41), b3 ×0.983 (552), test_blast3d T7
×1.005 (174). One `[note] resolved charge: N cells, energy scaled ×F` line per run.

### T37 — חבילת הקשחה (A4, A5, A6, A7) · 2026-09-07

All four, with `test_regression` byte-identical after every step (no re-baseline).
- **A4:** the identical air/products dispatch in solver1d/2d/3d `primitives()` is now one
  call to `eos.pressure_soundspeed` (the function that already held that block and had no
  caller); solver1d takes `r`, `A_face`, `V_cell` from `make_grid_1d`. `riemann.mirror_state`
  deleted — grep found no CALLER, only two unused imports in `legacy/blast2d.py` and
  `legacy/blast3d.py`, which went with it.
- **A5:** `MIN_EXP_CELLS`, `CELLS_2D_WARN`, `CELLS_2D_MAX` imported from `core.constants`;
  `test_case_validate.shared_constant_checks` asserts constants.py, validate_case and each
  solver see the same numbers AND that no solver re-types the literals.
- **A6:** `runloop.progress_line` counts solver stdout lines while `st['step']` is still 0
  and logs ONE warning after `TIME_CANARY_LINES` (500) — "blastFoam output format changed?".
- **A7:** `backend._surface_refused` / `_surface_ok` wrap every refusal in
  `_decode_surface` / `_decode_surface_amr`; a mid-write sample is refused legitimately, so
  the canary waits for `SURFACE_CANARY_TRIES` (20) CONSECUTIVE refusals (~5 s of polling).

**Note:** `_decode_surface_amr` existed only as UNCOMMITTED work in the working tree (the
live AMR slice + the solver-side "Refresh every N steps" cadence). It was landed first,
unchanged, in its own commit; T37 sits on top.

### T38 — עידוני תצוגה חיה (G7) · 2026-09-07

(1) New `RunHooks.cadence(dt=None, steps=None)` — no-op for native runs. The foam solvers
report `writeInterval` AND the live-sample cadence at run start; `runloop.maybe_adapt` and
`_sync_live_steps` report changes, so the hint follows mid-run. The live title reads
"t = 0.107 ms · frames every ~3.44 µs". A step cadence is turned into a TIME using the
newest solver `dt`, falling back to "frames every ~5 solver steps"; under 0.01 ms reads in
µs. The hint is re-derived every frame from the pane's own label so it never doubles up.
(2) The 2D live pane gained "Auto | Min | Max | kPa" mirroring the 3D viewer's manual clim;
an unusable or inverted range falls back to autoscale rather than freezing the picture.

### T39 — גירעון רסטריזציה של מסת המטען (N5) · 2026-09-07

`constants.FOAM_EXP_CELLS = 8` now drives every blastFoam charge target (1D/2D/3D global
refine, the automatic zone level, the AMR level check, the validation notes) through
`refine.exp_cells(case)`; **native keeps `MIN_EXP_CELLS = 5` and test_regression stays
byte-identical**. `refine.set_mass_fraction` predicts what `sphericalMassToCell` will
deposit; `validate_case` reports "Charge cells: N at dx → ~F of the M kg set by blastFoam";
`backend._scan_set_mass` forwards blastFoam's own line as a `[note]`, handling both printed
forms (3D/planar `Set volume of cell: V m^3`, wedge/sector `V m^3 (V_full actual)`).

**The original "~0.85 of requested mass" premise did not reproduce.** Measured against
blastFoam's own set-volume line the deposit is 0.979 (3D, 5 cells) / 1.027 (3D, 8 cells) /
0.995 (1D, both). Over 400 random burst offsets 8 cells mainly cuts the SPREAD — 3D RMS
1.00 % → 0.41 %, axisym 3.67 % → 2.95 % — for 1.6×/2.6×/4.1× the cells in 1D/2D/3D.
**The real gain is the resolved detonation:** KB anchor 0.72–0.77 → 0.85–0.89; foam-vs-native
arrival gap 13.7/7.3/5.5/3.8 % → 4.5/1.5/1.3/0.7 %.

### T40 — אפיון זמני הגעה: תא הבדיקה ב-AMR (N16-a) + פיגור קרוב-שדה (W1) · 2026-09-07

Both studies run; **the `adjustLocations` hypothesis is REFUTED** — switching it off moves
the AMR-vs-static arrival by 0.15 percentage points (blastProbes reports the containing
cell's value either way), so the default stays `yes`. The +18 % is a real resolution
difference at the gauge: the AMR mesh follows the shock and is at its finest level there,
while the static `zone` reference refines only around the charge. Measured with
`_e2e_foam_probe_study.py`: +4.2 % at a cell corner, −11.5 % at a base-cell centre, point
peaks 57–171 % apart.

**W1 characterised:** foam lags native +36.7 % / +23.6 % at r = 0.6 / 1.0 m with the default
`linear` activation and +23.1 % / +12.8 % with `none` — roughly half the lag is the
activation model burning the charge at vDet, the rest is the resolved charge's expansion.
`none` overshoots the peaks (1.43× / 1.36× native), so **`linear` stays the default** and the
tolerances stay as they are. Documented in `blastlab/README.md`.

### T41 — שרשראות לתוך blastFoam (N7) · 2026-09-07

A blastFoam stage can start from a 1D or 2D profile. `writer.profile_state` runs the SAME
remap the native solvers use (`remap_profile_1d_to_2d/3d`, `remap_profile_2d_to_3d`) onto the
case grid, and `_profile_fields` emits p, T, U, `alpha.expl`, `rho.expl`, `rho.air` as
`nonuniform List<scalar|vector>` internalFields in the mesh's cell order (`ravel(order='F')`,
fluid cells only on a carved mesh — the exact inverse of `reader.to_grid`). T is the inverse
of the reader's `e = Cv(phase)·T` and p comes from the native EOS the profile was produced
with. The two-phase split is sharp (alpha is 0 or 1), which makes the mass transfer exact.

**The one physical clock:** the state is emitted into a time directory named for the
profile's t0 and picked up with `startFrom latestTime` — **without that the chained gauges
read 53 %/34 % early.** Measured against the same domain initialised directly from the
charge: arrivals +2.31 %/+3.36 %, peaks +4.87 %/+3.37 % (`_e2e_foam_chain.py`); emitted
mass/energy match the profile to 1e-11. Refinement zones and AMR are refused with a profile
for now — the cell order is only predictable on the uniform base mesh.

### T48 — תוכנית ריצה מודעת-חומרה (N17) · 2026-09-07

`env.plan_run(n_req, n_cells, cores, ram_gb, dim, amr, headroom)` is a pure function
returning `RunPlan(ranks, cell_cap_warn, cell_cap_refuse, reason, ram_gb, cores)`;
`resolve_nprocs` is a thin wrapper supplying the probed hardware. `detect_ram_gb()` reads the
WSL VM's `free -g` (parse split out as `parse_free_gb`), **`hardware()` returns cached values
only — it is called on every keystroke by `validate_case` and must never touch WSL** —
and `prime_hardware()` seeds the cache from `settings.json`. An 11-row pinned decision table
and a 432-case invariant sweep.

**Measured `BYTES_PER_CELL = 2650`** (blastFoam serial 3D peak RSS: 59,319 cells → 305.1 MB;
262,144 → 843.3 MB; ~148 MB fixed); headroom 1 (was an unjustified 2),
`CELLS_PER_RANK = 50_000`, `RAM_GB_PER_RANK = 2`, caps at 0.70/0.35 of VM RAM.
**On this PC (4 cores, 4 GB VM): 1,134,519 cells and 2 RAM-limited ranks — and it refuses the
shipped default 2D case (2.3M cells ≈ 6.1 GB), which used to be accepted and would have died
inside WSL.** → פתוח כהחלטת בעלים ב-[TODO.md](TODO.md).

### T42 — AMR מקבילי: קריאת `processor*/` ישירה (N16-b) · 2026-09-07

The ingest reads `processor*/` directly and concatenates per rank (cell-for-cell identical to
the serial read, unit-pinned); `maybe_reconstruct` skips decomposed runs; serial guards
lifted. **340 s → 237 s (1.43×) at np=2.**

Serial-vs-parallel AMR are two self-consistent discretisations: arrivals agree 0.3–0.5 %,
point peaks fluctuate 0.15–4 %, impulse drifts 4–9 % late. `balance yes` changes nothing
(load already balanced 1.02–1.04, verified with addEmptyPatch + a live run) and maxCells never
bound. **Acceptance (owner decision):** per-gauge arrival ≤ 1 % and loading-region peak-map
median ≤ 1 % (**0.605 % measured**), point values characterised ungated —
`_e2e_foam_amr_ab.py`, PASS. `balance no` stays the default; revisit balancing only for
asymmetric refinement or 4+ ranks.

### T43 — חידוש ריצת foam שנעצרה (N6) · 2026-09-07

`backend.resume_run(case_dir, hooks)` rebuilds the spec the way postmortem does
(case.json + `render_case` + on-disk 0/C for refined meshes), refuses a run whose solver is
still alive (or whose state WSL cannot report), resets the `stopAt writeNow` a stop left in
the controlDict, flips `startFrom → latestTime`, and re-enters the ORDINARY `solve_Xd_foam`
with that spec (the three entry points gained a `spec=None` parameter that skips
`_preflight`). **No other special-casing was needed** — the shared run loop's ingest is
disk-driven and ordered, so it first replays the times the stopped run wrote (rebuilding the
accumulators, snapshots and recorded frames exactly as a live run would have) and then follows
the new writes. Prefix-identical gauges, peak map within 0.5 %, a Resume button in the run
browser. Works for serial, static-refined and decomposed (T42) runs through the same path.
Stopped-run gauge tails remain **W2**.

### T44 — שדות גייג' מעבר ל-p (N12, foam בלבד) · 2026-09-07

The gauges FO records `fields (p U rho)` (one line in the writer; the goldens' only diff).
The reader gains `_parse_probes_vec` (vector probe rows are `t (ux uy uz) …`) and a
`_merge_chunks` shared by every probe field. `read_probes` attaches `speeds` (|U| per gauge)
and `rhos` **ONLY when their rows align sample-for-sample with p's** — a torn or missing extra
degrades to p-only rather than ever misaligning (pinned by a torn-U fixture test).
`Result.gauges` keeps `pressures` as-is, so every existing consumer is untouched. A p / |U| /
rho selector on the Gauges tab and TSV columns; **native stays p-only and byte-pinned.**

### T45 — ייצוא CSV של מפות שדה (N14) + דוח HTML בלחיצה (N13) · 2026-09-07

New `blastlab/output/report.py`, pure writers shared by two new Results-tab export buttons.
CSVs are long-format per-field (p_peak / impulse / snapshot fields) on the result's own grid,
1D as `r,value`. The HTML report is one self-contained file: banner, the N2 gauge table,
inlined PNGs, the case JSON, and the KB free-air comparison when applicable.

### T46 — חומרים מעבר ל-TNT לסולברים הנייטיביים (N11) · 2026-09-08

`eos.material_jwl(name)` returns the JWL parameter set for a charge material — **'TNT'
returns the byte-pinned `constants.JWL_TNT` OBJECT itself**, everything else comes from the
shared `solvers/foam/materials` table (pure data, lazily imported) as a dict with the same
keys. `pressure_soundspeed` and `jwl_pressure`/`jwl_soundspeed` take the set as a parameter
defaulting to `JWL_TNT`; the three engines take `material='TNT'` threaded from
`case.material`. **test_regression is byte-identical, which is the whole point of the TNT-object
fast path.** C4 1D peak ×1.24 over TNT.

### T47 — שחזור MUSCL מסדר שני, opt-in (N10) · 2026-09-08

Limited MUSCL face reconstruction, opt-in via `case.order == 2` (default 1 on all three case
classes; **test_regression stays byte-identical** — the order-1 statements are untouched).
Implemented in `bc._face_fluxes_axis0` + a 1D block, EOS via a solver callback, with an
unphysical-face fallback to order 1. **r = 1.5 m: 0.75 → 0.90 of KB; anchor sweep 0.74–0.81 →
0.85–0.89; with order 2 the foam/native peak ratios collapse to 0.97–1.01.**

### T49 — שכבת רשת על האנימציה שהריצה כותבת (N15) · 2026-09-08

New case field `anim_mesh: bool = False` on `Case2D`/`Case3D` (case-file `VERSION` 5 → 6),
handed to the existing `write_animation(…, show_mesh=)` at every automatic export:
`gui/app.py::_solve_stage`, `solvers/foam/cli_run.py::_run_2d/_run_3d`, and the native
interactive CLI. GUI: a "Mesh overlay in the animation" checkbox in the Outputs card.
**No solver code touched.** The AMR per-frame overlay path is reused as-is.

### T50–T54 — סוגי גבול, זמן סיום, גייג' טריגר, סימוני גייג'ים (N18, N19) · 2026-09-08

**Why (owner request):** `open` did two jobs at once — it was the transmissive ghost-copy AND
it ended the run the moment `p > 1.001·P_air` reached it. There was no way to let a wave leave
and keep solving.

**T50 — the vocabulary.** `core/bc.py` owns it: `BC_KINDS = (transmit, reflect, terminate)`,
`BC_LEGACY = {open: transmit, wall: reflect}` and `normalize_bc(s)`, which every reader goes
through, so pre-T50 case files still load (with one `[note]` naming the mapping — a silent
`open → transmit` would quietly drop a run's stop condition). Two different questions are asked
of `bcs` and they no longer have the same answer: `geometry.terminate_edge_mask` (was
`open_edge_mask`) feeds the stop condition and counts ONLY terminate sides, while
`stop_dists_2d/3d` size the snapshot radii and the progress bar off EVERY non-reflecting side —
the pre-T50 `open` set, so snapshot scheduling does not move. `_patch_type` / `_bc_entry` map
the new kinds onto the SAME OpenFOAM patch types, so the writer goldens are byte-identical.

**Owner decision, and its cost:** legacy `open` maps to `transmit` and the shipped defaults are
`transmit`, so a default run is no longer ended by the wave leaving — it runs to the safety cap
(`10·max(L)/c_air`) or `t_end`. **That is up to ~10× more solver time, worst on blastFoam.**
Mitigations in the same commit: `validate_case` warns when a case has no terminate side and no
end time (naming the cap in ms), the run banner says `safety cap (no terminate boundaries)`,
and T52 gives every dimension an end time.

**T51 — the trigger gauge.** `trigger_gauge` (1-based, None = off), `trigger_action`
(`terminate` | `remap` | `remap+terminate`) and `trigger_file`. The check sits in the
gauge-sampling block each solver already had, so it costs one comparison per step and fires
once. A remap action captures `meta['trigger_state']` (2D) or `meta['trigger_profile']` (1D) at
that instant; file writing stays with the callers. 3D is terminate-only — there is no 3D remap
format. **Bug found by the owner mid-task:** a stopped blastFoam run died with
`NameError: name 'trig_k' is not defined` — the trigger is armed inside `solve_2d/3d_foam` but
the meta is assembled in `finalize_2d/3d`, also called by `postmortem.load_run`, which never
watched the run. Both now take `trig_k`/`trigger` as keyword arguments defaulting to None.

**T52 — end time.** `t_end` on `Case1D`/`Case2D` (`Case3D` already had it), honoured exactly as
`solver3d` did. Deliberately transcript-neutral at `t_end = 0`. Precedence: whichever comes
first — a terminate boundary, the trigger gauge, or the end time.

**T53 — gauge markers.** `plots.gauge_points` / `add_gauge_markers`: a ringed dot plus `G<n>`
per gauge, the trigger gauge heavier and starred. 3D keeps only the gauges the plotted plane
actually cuts (`geometry.plane_gauges`, tolerance one cell).

**T54 — AMR in the video (the real defect, found by the owner).** The first pass verified the
per-frame machinery on a synthetic record and concluded it already worked. **It did not:** on
the owner's run — 20×20 m axisym, 0.5 m base, `amr_levels=4`, a **640×640 = 409,600-cell display
grid** — `plots.mesh_for` hit its `if src.size > 400_000` guard and *replaced* the overlay with a
uniform base grid, so the exported video and the Results field views showed no refinement at
all. The live pane never had that fallback, which is exactly why the mesh was visible while
running and gone in the video. The synthetic fixtures were all 8×8, three orders of magnitude
under the guard. **Fixed by coarsening instead of discarding:** `_fit_overlay` max-pools the
level map until it fits under `MESH_MAX_CELLS = 1_200_000`. Measured: ~45 ms per frame (~7 s
over a 150-frame gif). All four `mesh_for` branches now go through one level-map path.

**Regression policy.** `make_baseline.py` spells its boundaries out as `terminate`/`reflect`.
**Every numeric baseline stayed byte-identical** (b1/b2/b2r/b3/b3r gauges + b2_profile.npz);
only `transcript.txt` was re-baselined for the reworded banner lines — 30 lines, all wording.
Every call site that RUNS a solver without naming its boundaries now spells the old behaviour
out (`make_baseline.py`, `test_blast2d.py`'s `ALL_TERM`, `test_viz3d_hooks.py`, the WSL suites,
the `_e2e_*` scripts).

**NOT RUN at the time:** the WSL suites (test_foam_2d / _3d_smoke / the foam e2e scripts) — the
foam changes here are the trigger check and the mask rename. → ראה [TODO.md](TODO.md).

### T55 — חסימת הזיכרון של רשומת ה-replay (N15) · 2026-09-08

The AMR run above died mid-ingest with `_ArrayMemoryError: Unable to allocate 400 KiB for an
array with shape (640, 640)` inside `mesh_at`, alongside Windows' own `0xc000012d`
(STATUS_COMMITMENT_LIMIT) in an unrelated process — the machine, not blastlab, was out of
commit. **But blastlab was a large part of why: the frame recorders grew to `2 × record_frames`
before thinning**, so a run asking for 150 frames held up to 300, and at 640² with per-frame AMR
level maps that is 2.05 MB × 300 = **614 MB** of replay record alone. Nothing capped
`record_frames` by grid size either.

Both fixed: all four recorders (native 2D/3D, foam 2D/3D) thin at `record_frames` rather than
twice it, and `hooks.frame_budget` caps `record_frames` against `FRAME_MEM_BUDGET = 200 MB`
(4 bytes per display cell plus 1 more on an AMR run for its int8 level map), with a `[note]`
naming the per-frame cost. **The owner's case: 150 frames → 97, peak 614 MB → 199 MB.** The
helper lives in `solvers/hooks.py`, not in the foam runloop, so the native solvers do not have
to import the blastFoam backend. Small runs are untouched (an 80×60 2D run keeps all 150), so
test_regression stays byte-identical.

### T56 — ייצוא MP4 נגיש (N15) · 2026-09-08

`write_animation` has always picked its writer from the extension — `FFMpegWriter` for `.mp4`,
`PillowWriter` otherwise — but nothing in the GUI said so: the Setup field was labelled
"Animation (gif)" and the Results dialog "Save animation GIF" with no filetypes list, so `.mp4`
was reachable only by typing the extension. **And on this machine it would have fallen back
anyway: ffmpeg was installed nowhere** — not on Windows, not in WSL.

Installed `Gyan.FFmpeg` via winget (9.0.1). The field is now "Animation (.gif / .mp4)", the
dialog offers both types, and both defaults follow `FFMpegWriter.isAvailable()`. Verified end to
end: a 2D run with `anim_mesh=True` wrote a real 222 kB `.mp4` (yuv420p, no stray `.gif`). The
owner's two gifs under `run/1` were converted with `-crf 18 -pix_fmt yuv420p -movflags
+faststart`: 3.31 MB → 0.37 MB and 4.59 MB → 0.84 MB, both 700×800 / 95 frames / 16.67 fps.

**Note for anyone reading an older run log:** a GUI process started before the install keeps the
old PATH, so it still writes gif until it is restarted.

### T57 — טעינת ריצת AMR מקבילית (post-mortem) · 2026-09-08

`postmortem.load_run`'s ingest loop built its time path as `os.path.join(unc, name)` — the case
root plus the time name. A parallel AMR run is never reconstructed (reconstructPar cannot follow
a mesh that changes), so T42 keeps its written times in `processor*/` and `spec.time_dirs(name)`
returns one directory per rank. The readiness gate and the sanity walk-back in the same function
already used `time_dirs`; **only this loop was left behind when T42 landed**, so every time dir
missed, every one was silently `_skip`ped, and the loader ended with "no readable time
directory" — for one of the owner's runs, a run with **96 written times**. It predates the
session (`git blame`: 2026-09-02/09-05).

Fixed to `dpath = spec.time_dirs(name)` with `reader.read_time(first_part(dpath))`. Verified on
the owner's own directories: `20260908-142358_2d_p26780-00` now loads with 95 frames and 6
snapshots. The runs that still refuse are genuinely empty. New
`test_foam_postmortem_decomposed.py` reproduces the exact RuntimeError when the one-line fix is
reverted.

### T58 — שורת כותרת משלך על איורי Results (N20) · 2026-09-08

Everything the Results tab draws was titled automatically and only automatically, so a figure
taken into a report had to be relabelled outside the app. A `Title` box now adds a line of the
user's own; `plots.titled(base, extra)` puts it **ABOVE** the automatic title rather than
replacing it (owner's choice), so a titled animation still shows its running `t`. It reaches the
field maps, the gauge plots, the replay, the exported PNGs, the exported .mp4/.gif and the HTML
report heading. **It lives on the panel, not on the case** (owner's choice): it describes this
presentation of a result, typed just before an export. The box is read on the Tk thread and
handed to the worker as a plain string — a Tk variable must not be touched off-thread.

### T59 — תצוגה מקדימה למודל 1D: הסקטור הכדורי (N20) · 2026-09-08

1D was the one dimension with no preview. A 1D run is not a line: blastFoam solves it on the
spherical SECTOR `_blockmesh_1d` builds — apex at the origin, four wedge lateral faces, the
outlet arc at `radius_m`. `Preview1DPanel` draws that sector in the plane through its axis with
the charge filled at its own radius, the gauge radii as arcs, and, with Show mesh, the radial
cell faces (thinned to `MESH_MAX_LINES` — a default 1D case is 10,000 cells across and would ink
the sector solid). **Two things the drawing deliberately does not take literally, both stated in
the picture:** the real half-angle is 1°, which would draw as a bare line (T60 later settled it
at 0–30° from the axis); and a charge whose radius is under 1.5 % of the domain is drawn at that
floor and labelled `(drawn enlarged)` with its true radius. Radii and cell size come from
`validate_case`, so the preview and the validation strip cannot disagree.

### T60 — סוג גבול לקצה הסקטור החד-ממדי (N18) · 2026-09-08

T50 gave 2D and 3D three boundary kinds but left 1D hard-wired: the outer face was a
transmissive outflow that ALSO ended the run — exactly the pre-T50 `open`. `Case1D.bc_outer`
(default `terminate`, so nothing changes for an existing case) now takes the same three kinds.
`reflect` mirrors a ghost through the same Riemann solver `core.bc` uses for a reflecting 2D/3D
side, rather than a hand-written wall flux. blastFoam follows: the sector's `outlet` patch is
written from the kind (a reflecting end is a `wall` patch, not a `patch`), and the 1D ingest only
stops on `terminate`. The 1D preview draws the outer arc in the same language the 2D preview uses
— solid and bold for reflect, dotted for terminate, dashed for transmit.
**Re-baselined:** `transcript.txt` only, for the one `Outer boundary  : terminate` line —
additions only, every numeric baseline byte-identical.

### T61 — הפאנל החי של 1D היה נעוץ ב-10 kPa (G14) · 2026-09-08

**Owner: "something in the 1D live slice is not right, is it limited to 10 kPa?" It was.**
`on_run_started` pinned the empty axis with `ax.set_ylim(0, 10)` so the first frame would not
show a meaningless −0.04..0.04 kPa range — but **a plain `set_ylim` turns y autoscaling OFF**,
and the per-frame `ax.relim(); ax.autoscale_view(scalex=False)` only acts while it is on. Every
1D run since has been drawn against a 10 kPa ceiling with its shock clipped flat. Measured:
frames of 50, 900 and 12,000 kPa all left `ylim = (0, 10)` while `dataLim` read `[0, 12000]` —
**the data were right the whole time, only the axis never followed.**

`git log -S` dates it to `3cb800c` (2026-09-07, the S4 QA batch). The owner suspected the T53
gauge lines added the day after; that was checked first and ruled out by measurement. Fixed by
`ax.set_ylim(0, 10, auto=True)`. `test_gui_amr_form` gained a RunPanel 1D section, verified to
fail on exactly those checks when the `auto=True` is removed.

### T62 — ריאמפ 1D→3D מעולם לא יכול היה לרוץ ב-blastFoam (N7) · 2026-09-09

**Owner: a chained 3D stage died before its first frame.** Three independent blockers stacked on
the profile-initialised path, each hidden behind the one in front of it. The 2D stage was never
affected, which is why the chain looked healthy.

1. `solve_3d_foam` read the burst point out of `spec.charges`, which a profile stage leaves empty
   on purpose — `d_charge_3d` then folded over nothing and returned `None`
   (`AttributeError: 'NoneType' has no attribute 'astype'`), with `stop_dists_3d` waiting one line
   behind to raise `IndexError` on `centers[0]`. `plan_case` already knew the rule and carried its
   own copy of it; that copy is now the single `CaseSpec.burst_points` (charge centres, else the
   profile's centre), used by the run loop and by `postmortem` too, and both geometry helpers now
   reject an empty list outright instead of failing three frames later.
2. The time directory was named by `fmt` (`%.10g`) while controlDict declared `timePrecision 8`.
   `startFrom latestTime` keeps the VALUE it scanned and rebuilds the name from it, so a t0
   needing more than 8 digits was asked back as `0.00093318663` when the dir on disk read
   `0.0009331866336`: FOAM FATAL, cannot find `processor7/…/U`. **The 2D fixture's t0 is `0.0005`,
   which round-trips at any precision — that is the whole reason this sat undetected.**
   `dicts.TIME_PRECISION` + `tfmt()` are now the one source for both the dict entry and the emitted
   dir name, and `t_start` is snapped to that clock (<1e-8 relative).
3. With that fixed, `subsetMesh` aborted: `size 7640 is not equal to the given value of 8000`. A
   profile stage's fields are nonuniform over the FINAL cells, but they were written with the rest
   of the case, so the carve stage found them at the uncarved mesh. A charge case writes uniform
   fields, which map onto any mesh — hence no prior symptom. `CaseSpec.deferred` now holds those
   entries back and a Python mesh stage (`writer.write_deferred`, run between subsetMesh/refineMesh
   and decomposePar) lays them down once the cell count is final. `_mesh_stages` entries may now be
   a callable, not only a shell command. `writeCellCentres` was pinned to `-time 0` in the same
   spirit and now follows `spec.start_dir`.

**Verified on the owner's own failing case** (10 m box, 50 kg, one carved obstacle, 10 MPI ranks,
`t_end` cut to 2 ms): runs to completion, `p_peak` 2.232 MPa over a 101.325 kPa floor, all finite.
`test_foam_writer` gained `burst_point_checks`, `time_name_checks` and `deferred_state_checks`
(17 checks; goldens byte-identical).

**Not covered, found while reading:** `_phaseproperties` emits an empty detonation `points` list
on a profile stage — harmless today, but the same missing-fallback shape as #1. → [TODO.md](TODO.md).

### T63 — גייג' הטריגר יוצא מ-1D (N19) · החלטת בעלים · 2026-09-09

T51 put the trigger on all three case classes, but in 1D it earned its keep in neither backend.
**blastFoam 1D never implemented it at all:** `solve_1d_foam` never calls
`_trigger_cells`/`_trigger_fire` the way `solve_2d/3d_foam` do, yet `validate_case` accepted the
number and the form showed the card — a control that silently did nothing. In the native 1D solver
it worked, but only ever duplicated what 1D already had: the run's `profile_file` IS the hand-off,
and T60 gave the far end of the sector a `terminate` boundary kind. Rather than implement the foam
half, the owner asked for the whole thing out of 1D.

Removed: the three fields from `Case1D`; the parameters, the arming block, `trig_k` and the
`trigger`/`trigger_profile`/`trigger_gauge` meta keys from `solver1d`; the Trigger-gauge card from
the 1D form; the 1D branches of `forms._set_trigger`'s caller and `app._write_trigger_remap`; the
trigger styling from the 1D live pane. **2D/3D are untouched.**

**Old case files:** `case_from_dict` drops the three keys for `dim == 1` BEFORE the unknown-key
check. Without that, every saved 1D case and every 1D run's `case.json` would have started failing
with "Unknown case keys". `VERSION` 10 → 11 records it. Native stdout is unchanged, so
test_regression stays byte-green with no re-baseline.

Tests: `test_bc_trigger` swaps its 1D remap check for three — `Case1D` carries no trigger
attributes, a 1D run's meta carries no trigger keys, and a pre-T63 1D case dict still loads
(minus the keys); `test_gui_amr_form` dropped a stale `trigger_gauge=2` from its 1D
`on_run_started` payload. Green: test_regression, test_case_validate, test_refine,
test_foam_writer, test_gui_solver_mode, test_gui_title_preview1d, test_gui_results_fields,
test_gui_drain, test_blast2d, test_blast3d, test_gauge_summary, test_report.

### T70 — AMR דינמי לשלב המאותחל מפרופיל (N7 + N16) · בקשת בעלים · 2026-09-09

A chain stage fed by a profile was refused outright if it also asked for AMR ("A
profile-initialised blastFoam stage cannot use dynamic AMR yet"). The refusal was stricter than
the physics needs: **under AMR the mesh at t0 IS the uniform base grid** blockMesh builds — the
static topoSet/refineMesh passes are skipped for AMR (`_mesh_stages`) and `adaptiveFvMesh` refines
only once the run is stepping. The real defect was narrower: `profile_state` remapped onto
`spec.grid`, which for an AMR case is the DISPLAY grid at `display_level`, so the emitted
nonuniform lists were 2**(dim*D) times too long and OpenFOAM would have aborted on the size
mismatch. Static refinement zones stay refused — `refineMesh` renumbers the cells, which needs the
post-refine cell order (see TODO P3-12).

**Code.** `CaseSpec.grid_base` (from `plan.base`) plus `init_grid`/`init_solid`: the grid a
profile stage's state is written on — the base grid under AMR, the display grid otherwise (the
same object on a uniform case, so nothing moves there). `profile_state` and `_cell_order` go
through them, and `_profile_fields` now refuses outright when the emitted length ≠ `spec.n_cells`
rather than letting it become a FOAM FATAL three stages later. `validate_case` drops the AMR
refusal and plans a profile stage exactly like a charge one (`_plan_amr` never looks at the
charge; `validate_amr` already skips its resolve-the-charge rule when there is none), plus a note
that the state lands on the base mesh.

**t0 is not 0.** T62 moved the cell-centre write to `spec.start_dir`, but three places still
hardcoded `0/`: `_build_remap_amr`, `resume_run`'s guard and `postmortem.load_run`'s guard — an
AMR profile run died at "cannot read the t = 0 cell centres" before any of them could help. The
ingest also treated the t0 dir as a stalled solver write (under AMR it has no `cellLevel` of its
own) and logged "stayed unreadable — skipped" once per run; `OrderedIngest.pending` now passes
over `spec.start_dir` in silence exactly as it does `0/`.

**Banner.** A profile stage prints `Initialised from: <file> at t = … ms` + `Source charge`
instead of `Charge: <whatever the form last held>` (`case.charge` is meaningless there), says the
state is written on the base mesh, and warns when the base cell is coarser than the profile's own
spacing (`init_state['dx_src']`) — **the base cell, not the AMR level, sets how sharp the hand-off
is**, because there is nothing to refine until the run steps.

**Verified on WSL (82 s):** native 1D → 2D axisym foam + AMR level 2 on a 25×50 base mesh. The
case starts (so `adaptiveFvMesh` is happy with no `cellLevel` at t0 — a profile stage skips
`setRefinedFields` entirely), the mesh grows 1,250 → 12,848 cells (L0 352 / L1 624 / L2 11,872),
the gauges read 2,826 and 1,774 kPa in the right order, and `postmortem.load_run` reloads the run.
`_e2e_foam_chain_amr.py` pins all of it.

**Found here, still open:** stopping that run and resuming it dies inside blastFoam with
`size 5138 is not equal to the given value of 5189` on `pMax`. A charge+AMR run resumes cleanly
(twice, including after 207 steps), so it looks specific to profile stages — TODO P1-5.

Tests: `test_foam_writer` gained the `case2d_axi_profile_amr` golden + `profile_amr_checks` (every
field sized for the base mesh, blockMesh base counts, adaptiveFvMesh, no setRefinedFields,
writeCellCentres at the t0 dir); `test_case_validate` swaps "profile + AMR refused" for accepted +
the note + AMR/zones still mutually exclusive; `test_foam_ingest_order` pins the silent t0
pass-over. Green: test_regression (byte-identical, no re-baseline), test_refine, test_foam_reader,
test_foam_amr_ingest, test_foam_postmortem_decomposed, test_gui_amr_form, test_gui_refine_preview,
test_bc_trigger.


### T64–T69 — מודל חומרה רובוסטי בין מכונות (N21) · 2026-09-09

The app runs on machines an order of magnitude apart (a 4-core / 5 GB-VM laptop and a
20-core / 128 GB workstation). Every hardware decision was either a fixed constant or a
probe whose failure mode was *permissive*. Six defects, fixed as six shippable steps.

**The inversion (T65).** `plan_run` fell back to `FOAM_CELLS_REFUSE = 120M` cells when VM
RAM was unknown, where a measured 62 GB VM yields 17.6M — less knowledge meant a *higher*
cap, so a WSL cold start silently unlocked a run that could not fit. Unknown RAM now sizes
against `FOAM_VM_GB_ASSUMED = 4` (1,134,519 cells) and the `FOAM_CELLS_*` constants become
a **ceiling** on the RAM-derived number rather than a fallback for it.

**The sticky cache (T64).** `prime_hardware` seeded `_slots`/`_ram_gb` from settings, and
`detect_slots`/`detect_ram_gb` returned early on any non-None cache — so a primed session
**never probed at all**, and a `.wslconfig` edit stayed invisible indefinitely. Now every
number carries a source (`core/hardware.py`: MEASURED | CACHED | UNKNOWN) and only MEASURED
suppresses a probe, with a one-attempt-per-session flag so a failure is not retried into a
string of 30 s timeouts. `detect_cores` still returns 4 on failure but no longer *caches*
it, so no run plan says "4 physical cores" about a machine it never measured.
`detect_ram_gb` reads `/proc/meminfo` (exact kB) instead of `free -g`, which truncated and
made a sub-GiB VM indistinguishable from a failed probe.

**Identity and staleness (T66).** `hw_stamp` was written and never read, and nothing said
which machine the numbers described. `hw_fingerprint` (sha1 of host name + cpu count + host
RAM + distro, deliberately not the VM RAM — that is the value being validated) and a 7-day
TTL now gate priming. A failed probe used to persist `hw_ram_gb=0` and a fabricated 4-core
count over good values; only MEASURED fields are written now. `settings.update()` is under
a lock (the probe thread and the main thread both call it) and `save()` uses a pid-unique
temp name.

**The native side (T67).** The native solvers run in the GUI's own process on host RAM —
where a MemoryError kills the window — and had no memory awareness at all, with a
`~200 B/cell` comment that is low by ~3x. Counted from the actual allocations:
`NATIVE_PEAK` 480 (2D) / 580 (3D), plus order-2 and per-snapshot terms; 3D order-1 with 6
snapshots is 625 B/cell, 2D is 761. Host RAM comes from `GlobalMemoryStatusEx` via ctypes
(no new dependency; `ullTotalPhys`, never `ullAvailPhys` — an available-RAM cap would make
validation non-deterministic). `plan_native` can only ever **lower** `CELLS_*`, never raise
them, and never below `NATIVE_CELLS_FLOOR` — so the solvers keep enforcing the constants
unchanged, `test_regression` is unreachable from the change, and a ≥16 GB host sees no
difference at all. It bites only at 8 GB and below.

**Portable cases (T68).** `n_procs` is serialized in the case file, so a case saved on the
20-core box launched 16 ranks on a 4-core laptop (mpirun was even handed `--oversubscribe`)
and implied 32 GB of VM. `rank_ceiling(cores, ram_gb, headroom)` — hard limits only, not
the cells/rank floor or the rank cap, which are efficiency heuristics — clamps an explicit
ask and says so in the validation note. With nothing known the ask still stands, so the app
stays usable with WSL down.

**Budgets (T69).** `MAX_AUTO_PROCS = 16` becomes the fallback for an *unknown* core count
(a measured 20-core machine is better information than a constant; `mpi_max_ranks` in
settings overrides either way). `FRAME_MEM_CAP` and `hooks.FRAME_MEM_BUDGET` are derived
from host RAM, keeping their old values as the ceiling so a big machine is unchanged.
`MAX_VIEW_DIM` is deliberately **not** derived: 128³ float32 is 8.4 MB, the constraint is
VTK render rate, and deriving it would change what the user sees between machines.

Tests: `blastlab/tests/test_hardware.py` (new — identity, staleness, host probe, a pinned
native-cap table and an invariant sweep), plus new sections in `test_foam_env.py` and
`test_case_validate.py`. Verified against the whole fast matrix (`test_regression`
byte-parity included) and, on an idle WSL, seven foam suites: `1d_vs_native`, `parallel`
(a real np1-vs-np2 comparison — the clamp granted this VM's 2 ranks rather than degrading
it), `stop`, `postmortem`, `features`, `3d_smoke`, `2d`. `test_blast3d` passed too. Several existing rows had to be **pinned** rather than merely
updated: they validated real cases against whatever the ambient hardware cache held, which
under the old permissive fallback happened to pass everywhere and under the new
conservative one would have inverted silently.

---

### T71 — ליל 2026-09-09/10: הריצות הכבדות, והתיקונים שנגזרו מהן

**ריצת לילה ללא השגחה על מכונה חזקה** (i7-14700, 20 ליבות פיזיות / 28 לוגיות,
128 GB, WSL VM של 62 GiB ללא `.wslconfig`), לפי `NIGHT_RUN.md`. הבסיס יצא
ירוק — 29/29 במטריצה המהירה, 8/8 בחבילות ה-WSL, `test_regression` בייט-זהה —
ואז R1–R9. הדו"ח המלא: `NIGHT_RESULTS.md`, יומן: `NIGHT_LOG.md`.

**המספרים שהריצות החזירו:**

| | תוצאה |
|---|-------|
| `rank ceiling here` | **13** (`14 physical cores - 1 headroom`), מול 2 על מכונת הפיתוח |
| **R1** — ברירת המחדל של 2D בגודל מלא | 2,301,289 תאים, 177,073 לכל rank ב-13 ranks, **שיא RSS 10.5 GB**, ~10.3 שנ' לצעד, `Courant Max` נעול על 0.398. הגיעה ל-0.036 % מהריצה ב-48 דק' → **4.6–8.8 ימים** לריצה מלאה |
| **R6** — `BYTES_PER_CELL` | 3 נקודות סריאליות (32,768 / 74,088 / 140,608 תאים → 224.9 / 326.2 / 501.5 MiB): שיפוע **2,696 B/cell**, R² = 0.9996, קבוע 138.8 MiB |
| **R7** — טבלת ה-ranks (זמן קיר ל-`t = 6.0e-04 s`) | 1 → 1,992.5 s · 2 → 1,126.4 s (×1.77) · 4 → 822.6 s (×2.42) · 8 → 698.9 s (×2.85) |
| **R7** — שיאי גייג' ב-r = 1.0 m | np1 2,569.13 kPa; np2/4/8 = 2,597.58 / 2,597.53 / 2,597.50 kPa |
| **R8** | רץ לראשונה אי פעם; ראה למטה |

**P1-1 נסגרה — ברירת המחדל של 2D נשארת מוקטנת.** R1 מכריע: המקרה המלא תופס
10.5 GB מתוך 62 GiB זמינים — **פחות מ-17 % מה-VM** — ובכל זאת דורש ימים.
**החסם הוא חישוב, לא זיכרון**, ולכן אין להפוך את `Case2D` לתלוית-RAM: תקרה
שנגזרת מ-RAM בלבד מאשרת מקרים שאי אפשר להריץ. אם רוצים תלוי-חומרה, לגזור
מתפוקה — נמדד **~4.5 µs לתא לצעד** ב-13 ranks.

**תחקיר ה-SIGFPE — נפתר.** ריצה שקרסה ב-`timeIntegrator::postUpdateAll()`
שוחזרה דטרמיניסטית ופורקה לשלוש ריצות צמצום:

| שינוי | תוצאה |
|-------|-------|
| ללא שינוי (ביקורת) | קרס — שחזור מדויק (אותו זמן כתיבה, אותם 233,292 תאים, אותו שיא גייג') |
| `n_procs = 1` | **קרס ב-SIGFPE אמיתי** ב-`t = 0.0051419` (מול 0.00514334 במקור), אותו סטאק |
| `cfl` חצי | קרס — קנה 2.3 % בזמן פיזיקלי בלבד |
| `amr_levels = 0` | ✅ **שרד** — חצה את נקודת הקריסה ב-31 שניות |

**המסקנה: ה-AMR.** לא חלוקה בין תת-תחומים (הסריאלי קרס זהה — `rank 6` במקור
היה מקרי), ולא צעד זמן. הסטאק מצביע על חלוקת שדה וקטורי בסקלרי בתוך
`compressibleBlastSystem::decode()`, כלומר `U = rhoU / rho` עם `rho = 0`;
`min(T) = 0` ו-`max(T) = 1.35e+15` ברגע הקריסה, ו-`deltaT` קרס מ-6.4e-06
דרך 1e-08 ל-7.5e-12 לאורך ~43 צעדים.

**התיקונים שנחתו בעקבות הלילה** (2026-09-10):

- **`c2b661a` — P2-6 נסגרה.** `_e2e_gui_chain_foam.py` רץ לראשונה וחשף ארבעה
  ליקויים: הבדיקה לא המתינה ל-`_drain_pending` ולכן הודעת השלב האחרון הייתה
  בלתי-נגישה מבנית; `list(g.get('times') or [])` זרק על ndarray; ונדרש
  `meta['p_peak']` גם משלב 1D, שמעולם לא ייצר מפת שיא. ובצד המוצר:
  `_dispatch` דיווח על כשל בדיאלוג **מודאלי** בלי נקודת הזרקה, כך שכל דרייבר
  לא-מפוקח נתקע עליו (נצפה: 27 דקות על חלון "Run failed", ו-`test_gui_drain`
  שרץ 692 שנ' במקום 7). `App.show_error` הוא עכשיו seam, ו-`SolverWorker`
  שומר את ה-traceback של השלב שנכשל. **שתי בדיקות השעון הפיזיקלי של N7/T41
  עוברות לראשונה:** stage 2 ב-2.381e-04 מול 2.381e-04, stage 3 ב-4.225e-03
  מול 4.225e-03.
- **`4e8c075`** — ריצה headless חדלה למדוד את עצמה מול VM משוער של 4 GB.
  ה-probe מקומי לתהליך, ורק ה-GUI שימר והזין אותו בחזרה; `env.prime_from_settings`
  הוא עכשיו המימוש היחיד שה-GUI, ה-CLI והסקריפטים חולקים, ו-`cli_run.run`
  מודד ומשמר בעצמו. אימות: אותו מקרה של 2.3M תאים — נדחה בלי הזנה, מתקבל עם.
- **`c66eae8`** — שומר יציבות ב-`runloop`: ריצה שה-`deltaT` שלה קרס והשעון
  שלה נתקע נעצרת עם `stop_reason = 'numerical instability'` במקום להסתובב עד
  ה-SIGFPE. אומת על המקרה שקרס: `RuntimeError: blastFoam failed (exit 136)`
  הפך ל-`RESULT ok  WALL 654s  stop=numerical instability`.
- **`b368046`** — `BYTES_PER_CELL` 2650 → 2700 (המודל תקף בין מכונות עד 1.7 %,
  אבל נטה כלפי מטה), README תוקן ל-8 תאים ב-blastFoam, והערכות הזמן שעודכנו
  למדוד בפועל.

**הסיבוב השני (2026-09-11)** — שלוש החלטות בעלים שהתקבלו והתבצעו:

- **`ab74c6e` — איזון עומס ב-AMR מקבילי נבנה.** שלב `addEmptyPatch`
  ב-preflight (blastFoam מסרב לאזן בלי patch מסוג `internal`) + מתג יחיד
  `dicts.AMR_LOAD_BALANCE` שמניע גם אותו וגם את ה-dict, כדי שלא יוכלו
  להיפרד. על המקרה שנמדד בו חוסר איזון: **63.5:1 → 1.2:1**, ותפוקה
  1.18 → **1.95 צעדים/שנ'** (275k → **491k** cell-steps/s, פי ~1.8).
  נוסף הגולדן `case2d_planar_amr_np4` — לענף הזה לא היה כיסוי כלל.
- **`2dc4c9f` — `amr_refine` 0.4 → 0.2.** ההערה בקוד טענה שהערך נבחר
  ל-~3.6 % שגיאה; T39 הזיז את המקרה מתחתיו והוא נמדד ב-**−11.8 %**.
  הסוויפ (שעכשיו מדפיס גם impulse) מראה ששלושת המדדים **מתכנסים**:
  peak −11.8/−3.9/−2.9, arrival +11.2/+10.1/+9.6, impulse +3.2/+16.0/+16.8.
  כלומר ה-+3.2 % הישן ב-impulse היה **מקריות**. שלוש רצועות הורחבו בהתאם,
  כל אחת עם המדידה שמצדיקה אותה.
  **נשלל במדידה:** זה לא הפרש בהפקדת המטען — שתי הריצות מסמנות אותם
  392 תאים ב-0.025 מ' לאותם 400 ק"ג. מה שנשאר הוא **השדה הרחוק הגס**.
- **`efa651b` — כתיבת הגדרות שנכשלה כבר לא נראית כמו הצלחה.**

**מה שנשאר פתוח** — `TODO.md` §P5: הכשל לסירוגין בשלב ה-3D (לא שוחזר
ב-5 ריצות; המכשור מוכן), האימות המרחבי של `cellLevel` ל-P5-3, ו-R2/R4/R5.

---

## 4. המספרים המדודים — פיזיקה וביצועים

**נייטיבי מול blastFoam.** foam peaks 1.10–1.16× native at r = 1–4 m with arrivals within
0.7–4.5 %, both monotonic (`test_foam_1d_vs_native`, re-measured after T39). With MUSCL order 2
the foam/native peak ratios collapse to **0.97–1.01** (T47).

**עוגן Kingery-Bulmash.** 0.72–0.77 before T39 → **0.85–0.89** with the 8-cell charge →
**1.02–1.20 with afterburn `miller`** (1.20 at Z = 1, 1.02–1.04 at Z = 2–4). The band in
`test_foam_kb_anchor` is 0.80–1.35. r = 1.5 m with order 2: 0.75 → 0.90 of KB.

**שימור מסה ואנרגיה (T36).** Energy exact to 4e-16; clipped volumes verified to 2e-16 against
closed forms and 1.7e-6 against a 1200³ brute-force count. Mass keeps the staircase deficit by
design. 2D-vs-1D arrival at r = 1.5 m: 5.21 % → 3.92 % (gate 6 % → 5 %); 2D→3D remap peaks
11.9–13.6 % → 7.6–9.4 %.

**מסת המטען שנשקעת בפועל (T39).** 0.979 (3D, 5 cells) / 1.027 (3D, 8 cells) / 0.995 (1D). Over 400
random burst offsets, 8 cells cut the RMS spread 1.00 % → 0.41 % (3D) and 3.67 % → 2.95 % (axisym).

**AMR (T40, T42).** 3D AMR gauge arrival +18 % vs static (peak within 2.7 %) — a real resolution
difference at the gauge, not `adjustLocations`. Parallel vs serial AMR: arrivals 0.3–0.5 %, point
peaks 0.15–4 %, impulse 4–9 % late, peak-map median **0.605 %**. Speed **340 s → 237 s (1.43×)** at
np=2.

**פיגור קרוב-שדה (W1).** foam lags native +36.7 % / +23.6 % at r = 0.6 / 1.0 m with `linear`;
+23.1 % / +12.8 % with `none`, which overshoots peaks by 1.43× / 1.36×.

**שרשראות לתוך foam (T41).** With the shared clock: arrivals +2.31 %/+3.36 %, peaks
+4.87 %/+3.37 %; mass/energy match the profile to 1e-11. Without it the gauges read 53 %/34 % early.

**חומרה (T48).** `BYTES_PER_CELL = 2650` measured; 59,319 cells → 305.1 MB, 262,144 → 843.3 MB,
~148 MB fixed. On this PC: 1,134,519 cells, 2 ranks.

**זיכרון וממשק.** Replay record 614 MB → 199 MB (T55). `feed_result` 2364 ms → 259 ms → ~1 ms per
snapshot tick (T31). `mesh_polydata` 320 ms warm-up then 5–8 ms/frame. AMR mesh overlay ~45 ms/frame
at 640².

---

## 5. אינדקס מזהים (B / G / A / N / W)

> הערות בקוד מצטטות את המזהים האלה. **אל תמחק את הסעיף.**

**Bugs (B)**
- B1 truncated `uniform` internalField AttributeError — DONE (T1)
- B2 kill-escalated stop crashed finalize — DONE (T1)
- B3 3D replay hardcoded the x-z plane — DONE (T2)
- B4 final frame missing from 3D viewer playback — DONE (T2)
- B5 chains bypassed validate_case — DONE (T6)
- B6 Stop could not interrupt foam preflight — DONE (T6)
- B7 foam progress bar at 0 until first write — DONE (T5)
- B8 Pa/kPa inconsistency — DONE (T3)
- B9 net vs positive-phase impulse naming — DONE (T3/T12)
- B10 duplicated last gauge row — DONE (T8)
- B11 native warnings bypassed hooks — DONE (T7)
- B12 1D snapshot scheduling — DONE (T8)
- B13 run-dir name collision — DONE (T4)
- B14 `--clean-foam-runs` live-run guard + orphan reaping — DONE (T4)
- B15 uncaught TimeoutExpired in stop paths — DONE (T1)
- B16 out-of-order ingest — DONE (T10)
- B17 stale FO peak/impulse — DONE (T10)
- B18 grids silently shrank one cell — DONE (T8)
- B19 3D viewer colour-range plumbing — DONE (T13)
- B20 FrameStore thinning — DONE (T2)
- B21 multi-charge stop distances — DONE (T10)
- B22 'Run failed' dialog text — DONE (T5)
- B23 `test_foam_parallel` determinism fails randomly — DONE (2026-09-07, T35)
- B24 resolved-charge init not mass/energy conserving (±3 %) — DONE (2026-09-07, T36)
- B25 controlDict rewrites inside fileModificationSkew ignored — DONE (2026-09-05, T18)
- B26 chain 3D stage reused the 2D revolved feed — DONE (2026-09-07, QA-05)
- B27 validation/preview allocated the full fine grid — DONE (2026-09-07, QA-01..04)

**GUI (G)**
- G1 "Initialise Model" hint erased — DONE (T5)
- G2 results accumulate / duplicate labels — de-dup + Remove DONE (QA-13); user-named runs DONE (T30)
- G3 validation split-brain / silent swallowing — DONE (2026-09-07, T29)
- G4 replay / preview stalls (idle-CPU half refuted) — DONE (2026-09-07, T31)
- G5 chain start race — DONE (T6)
- G6 progress < 100 % (DONE, T5); theme half refuted by QA (mesh overlay colour cosmetic) — closed
- G7 live-view niceties (cadence hint, 2D Min/Max) — DONE (2026-09-07, T38)
- G8 preview lacks extra charges / det points — DONE (2026-09-07, QA-21 + T31)
- G9 accelerators / persistence / focus — DONE (2026-09-07, T32)
- G10 default 3D case invalid, nan/inf accepted — DONE (2026-09-07, QA-14/15)
- G11 layout at 1280×840 / 1100×720 — DONE (QA-07/08 + T27)
- G12 stale state — DONE (QA-09..12 + T28)
- G13 light-mode affordance — DONE (2026-09-07, T32)
- G14 1D live pane pinned to 10 kPa — DONE (2026-09-08, T61)

**Architecture (A)**
- A1 foam run loop triplicated — DONE (T9)
- A2 geometry logic quadruplicated — DONE (T9, `core/geometry.py`)
- A3 postmortem private imports — DONE (T9)
- A4 dead code — foam + viz3d DONE (T9/T13); native DONE (2026-09-07, T37)
- A5 guard-rail constants duplicated as literals — DONE (2026-09-07, T37)
- A6 `Time =` regex needs a canary — DONE (2026-09-07, T37)
- A7 `_decode_surface` silent degrade — DONE (2026-09-07, T37)
- A8 viz3d control-message delivery — DONE (T13)
- A9 commit hygiene — DONE (2026-09-02) · **חזר לפתוח, ראה TODO.md P0**
- A10 regression discipline — standing rule

**New capabilities (N)**
- N1 peak/impulse views — DONE (T11) · N2 per-gauge summary + CSV — DONE (T12)
- N3 afterburn (`none | miller`) — DONE (T16); non-TNT Q0 from oxygen balance only, uncalibrated
- N4 VTK export — DONE (T15) · N5 charge-mass rasterisation — DONE (T39)
- N6 resume a stopped run — DONE (T43; a profile+AMR stage does NOT resume — TODO P1-5)
- N7 chains INTO blastFoam — DONE (T41, fixed T62, AMR opened up in T70; static zones still refused)
- N8 foam run browser + auto-cleanup — DONE (T14) · N9 user-named runs — DONE (T30)
- N10 MUSCL second order — DONE (T47) · N11 native materials beyond TNT — DONE (T46)
- N12 gauge fields beyond p — DONE (T44) · N13 HTML report / N14 CSV field maps — DONE (T45)
- N15 local (static) refinement + show-mesh — DONE (T17–T19); mesh on the run's own animation (T49);
  AMR in the video (T54); replay memory (T55); MP4 (T56)
- N16 dynamic AMR — DONE (T20–T24); N16-a probe cell DONE (T40); N16-b parallel DONE (T42, load fixed T57)
- N17 hardware-aware run plan — DONE (T48)
- N18 boundary kinds + per-run end time — DONE (T50, T52, T60)
- N19 trigger gauge + gauge markers — DONE (T51, T53); **2D/3D only since T63**
- N20 Results title line + 1D model preview — DONE (T58, T59)
- N21 cross-machine hardware model: honest sources, conservative-on-unknown
  caps, machine fingerprint + TTL, host-RAM native caps, n_procs clamp — DONE
  (T64–T69)

**Watch items (W)**
- **W1** foam near-field arrival lag — CHARACTERISED (T40), no action; `linear` stays the default
- **W2** blastProbes flushes buffered gauge samples only at a graceful End — **עדיין פתוח**, ראה
  [TODO.md](TODO.md)

---

## 6. סבב ה-QA של 2026-09-07 (QA-01…QA-35)

**מה נעשה:** ה-GUI האמיתי הורץ על המסך (1280×840, כהה ואז בהיר), נוהג דרך פקודות הווידג'טים עצמם,
**367 צילומי מסך ב-59 תרחישים**: ארבעת הטאבים, ולידציה, ריצות נייטיביות 1D/2D/3D, שרשרת,
**11 ריצות blastFoam אמיתיות ב-WSL** (עידון סטטי, AMR דו- ותלת-ממדי, Stop בזמן ה-mesh ובזמן
הפתרון, דפדפן ריצות, VTK, טעינה post-mortem, סגירת חלון תוך ריצה), החלפת ערכת נושא ורובוסטיות.
נמצאו 6 ממצאי S1, 9 של S2, 10 של S3 ו-11 של S4 — **כולם תוקנו** ב-T25–T33.

**סביבה:** Windows 11, Store Python 3.12.10, customtkinter 6.0.0, matplotlib 3.10.8,
pyvista 0.47.3 / VTK 9.4.2, Pillow 12.2, מסך 1920×1080 @ 100 %, חלון 1280×840.
כלי ההרצה: `blastlab/tests/_qa_gui_harness.py` (`--list`, `--resume`, `--scenario`, `--redo`,
`--solver`, `--smoke`), פלט תחת `~\blastlab_qa\<stamp>\shots`.

**S1 — קריסות (תוקן, T25/T26).** QA-01/02/03 (B27): `refine.plan_levels`/`_plan_amr` דוחים רשת
מנוונת או מפוצצת-זיכרון ב-`ValueError` **לפני** הקצאת מערך מלא; QA-04: `Plan.solid_fine` גוזם
את `expand(solid_base)` לצורת מפת הרמות (641 מול 642); QA-05 (B26): `GuiHooks.run_started` זורק
את ה-feed/scene של השלב הקודם; QA-06: `validate_case` בודק את מרכז הפיצוץ מול התחום בכל מצב אתחול.

**S2 — נתונים שגויים ופריסה (תוקן, T25).** QA-07 רוחב מינימלי לעמודת הקלט + גלישת כיתובים
(13:7 במקום 11:9); QA-08 כותרת Results בשתי שורות; QA-09 `View3DPanel` מרים את טאב Display אחרי
הבנייה (Tk מערים לפי סדר יצירה); QA-10 `set_running` מאפס את הצ'יפים + קריאת "PAUSED at step N";
QA-11 הפאנל החי עובר ל-"waiting for the solver…"; QA-12 קנבס ה-replay מוסבר וריק כשאין פריימים;
QA-13 מספור תווית חוזרת + כפתור Remove; **QA-14 טופס 3D נפתח על מקרה שעובר ולידציה** (8 ק"ג בקופסת
3 מ' ב-2 ס"מ = 3.4M תאים, במקום ברירת המחדל שהתעדנה ל-~852M תאים); QA-15 קלט לא-סופי ושבר נדחים.
שגיאת מכסה מסבירה עכשיו את הסיבה ("resolving the 0.105 m charge forces a 0.01054 m cell across the
whole 10 m domain; use a smaller domain, a larger charge, or charge resolution 'smear' /
blastFoam charge refinement 'zone'").

**S3 (תוקן, T27/T29/T31/T32/T33).** QA-16 (G3) ולידציה; QA-17 פריסה ושדות; **QA-18 ביצועים —
`feed_result` 2364 ms → 259 ms**, מטמון לתצוגה המקדימה, הפער הגרוע ביותר בריצה נייטיבית 3D
3544 → 1100 ms; QA-19 נראות במצב בהיר; QA-20 גלישת שורות ביומן; QA-21 (G8) מטענים נוספים ונקודות
פיצוץ בתצוגות; QA-22 הודעות שגיאה בפתיחת קובץ; QA-23 משוב שרשרת; QA-24 replay לריצה טעונה;
QA-25 כרטיס הוולידציה מוגבל בגובה וגליל.

**S4 (תוקן, T27/T32/T33).** QA-26 `p max` ב-kPa; QA-27 כותרות שנחתכו; QA-28 כפתורי Back/Forward
של matplotlib הוסרו; QA-29 (G9) קיצורים והתמדה; QA-30 סרגל גלילה בדפדפן הריצות; QA-31 גזירת
0.5 % העליונים במפות שיא/אימפולס; QA-32 יומן AMR מקוצץ + צ'יפ `cells`; QA-33 כותרות טבלת הגייג'ים;
QA-34 קובץ הלוגו נסגר; QA-35 הערת דיסק ל-AMR עם סך הריצה.

**QA-18 — תיקון ייחוס שגוי.** ה-3.5 שניות שיוחסו ל"פריימי AMR" היו למעשה בניית התצוגה המקדימה
התלת-ממדית ב-`set_case`, שהמטמון כבר תיקן. `mesh_polydata` עולה 262–320 ms פעם אחת (חימום VTK)
ואז ~5–8 ms לפריים. **לא נדרש throttle**, והייחוס המקורי היה שגוי.

**ניקיון בסוף הסבב:** `pgrep -a blastFoam` ריק, `env.reap_orphans()` לא מצא דבר; `/root/blastlab_runs`
86 ריצות / 27.8 GB; תוכנית החשמל שהוחלפה ללילה הוחזרה.

---

## 7. מאומת נכון — אל "תתקן"

Axisym momentum source is exactly well-balanced against the face-area metric; `bc.py` mirror signs
are correct; the y/z-sweep moveaxis round trip is index-correct (pinned by T1); smear init conserves
mass/energy to 1e-12 (T10); foam `to_grid` F-order reshape ↔ viewer `ravel(order='F')` ↔ VTK point
order is consistent end-to-end (a transpose trips `test_viz3d_scene` S2c); obstacle scatter/carve
ordering matches boxToCell; the GUI worker/queue architecture (latest-wins frame slots,
exception-hardened drain, Tk-thread-only widget access) is clean — **treat it as the pattern for new
panels.**

**מגבלת הציר באקסיסימטרי — מובנית, לא באג:** תאי הציר של טריז ה-wedge הם פריזמות,
ו-hexRef8 לא מעדן אותן. לכן תחת AMR המטען נשאר גס בעמודת הציר (`validate_amr` מזהיר),
ובעידון סטטי אפשרית רק רמה 1 על הציר ואזור שנוגע בציר מסורב (`validate_zones`).
אם השדה צמוד לציר חשוב — תא בסיס עדין יותר או גיאומטריה planar (שמעדנת בכל מקום).
אל תנסה "לתקן" את זה בצד ה-Python.

Native↔foam physics: foam peaks 1.10–1.16× native at r = 1–4 m with arrivals within 0.7–4.5 %, both
monotonic; KB anchor 1.02–1.20 with afterburn `miller`.

מה שאומת בעין בסבב ה-QA: עידון סטטי + Show mesh בכל המקומות, AMR per-frame, טבלת גייג'ים + CSV,
דפדפן ריצות, ייצוא VTK, טעינת post-mortem זהה לריצה חיה, Stop בכל שלב, ואין סולברים יתומים.

---

## 7א. ליל QA 2026-09-12 — מה נחת ואומת

> דוחות מלאים: [NIGHT2_RESULTS.md](NIGHT2_RESULTS.md) ·
> [NIGHT2_LOG.md](NIGHT2_LOG.md). מה שתועד ולא תוקן — ב-[TODO.md](TODO.md).
> **הרגרסיה בייט-זהה בשער ובסגירה.** המטריצה המהירה 30/30.
> קנריית הניקוי האוטומטי: 83 → 153 ריצות, **עלתה בלבד**.
> `%APPDATA%\blastlab\settings.json` — hash `50FA0D03…` ללא שינוי.

### מטריצת ה-GUI רצה בפעם הראשונה · `a5ef729`

`_qa_gui_harness.py:412` לא תפס `OSError` מ-`ImageGrab`, שנכשל תמיד בסשן
RDP מנותק. החריגה יצאה מהתרחיש, נרשמה כ-`harness-crash` והתרחיש סומן
**`crashed`** — ו-`--resume` **לעולם לא מנסה `crashed` שוב**. לילה אחד היה
שורף 55 מ-59 התרחישים לצמיתות. **זו הסיבה שהמטריצה מעולם לא רצה.**

התרופה כבר הייתה בקובץ וישבה כקוד מת: `print_window(PW_RENDERFULLCONTENT)`
מרנדר מה-DC של החלון ולא מהמסך, אבל היה מאחורי תנאי שדרש `ImageGrab`
**שהצליח**. אומת בפיקסלים: `--smoke` יציאה 0, **7/7 צילומים אמיתיים,
1,059–1,788 צבעים שונים** לכל אחד (ספירת צבעים ולא לומיננס — PrintWindow
שמצייר רק מסגרת נותן אפור אחיד שעובר בדיקת לומיננס).

**התוצאה: 58/58 תרחישים, 259+ צילומים, 118 הערות אפיון.** גם P2-5 שוחרר.

### ארבעה באגים בבדיקות — בכולם המוצר ענה נכון

| קומיט | מה |
|-------|-----|
| `75a9e9e` | **`I05`** קרס כי האפליקציה דחתה `n_snapshots=2.7` **נכון** — `get_case()` נקרא בלי הגנה בתוך f-string של הערה, והדחייה התקינה סימנה את התרחיש `crashed` לצמיתות. **`B06`** הדליף סולבר: ה-docstring אמר "אין מאיצים" אבל G9 קשר `<F5>` ל-`_run_single` (`app.py:386`). עכשיו הוא גם **בודק** ש-F5 מתחיל ו-Esc עוצר — לא היה כיסוי למאיצי G9 |
| `62984c7` | **`C10`** טען על `"Local refinement"` במקרה 3D שדורש רמה 6 מעל תקרה של 4, כלומר מקרה שלעולם לא יכול להכיל את הכיתוב. הטענה הועברה ל-`F2D_REF` שכן מתקף, והמקרה התלת-ממדי קיבל את הטענה שנכונה עליו — **הכיתוב התקין שהבדיקה הכושלת הסתירה** |
| `ddb20d2` | **שני ה-fixtures של AMR הם מקרים לא תקפים** (`ok=False`), ולכן שני התרחישים היחידים שבודקים AMR דינמי **מעולם לא הריצו AMR**. המוצר צדק: השבית את Run. ו-**`wait_log` חיפש בלוג המצטבר**, אז `F05` ייחס לעצמו את הריצה של `F04` — צילומים, בדיקה עוברת וזמן קיר, כולם של מישהו אחר |

**אחרי התיקון:** `F05` 653 שנ' (היה 19.7), `F06` 430 שנ' (היה 24.3),
**אפס ממצאים** — לראשונה AMR דינמי באמת נבדק, כולל `per-frame level maps`.
`_foam_run` עוצר עכשיו אם Run מושבת, כך שהייחוס השגוי לא יכול לחזור.

### חקירות שנסגרו עם מסקנה

**P5-3 נפתר על ידי P5-2.** `amr_refine` 0.4 → 0.2 (`2dc4c9f`) הוריד את
סטיית השיא סריאלי↔מקבילי מ-**1.11 % ל-0.042 %** — פי 26, ומרווח פי 24 מול
הסף של 1 %. **אין החלטת בעלים לקבל.** *(הסתייגויות ומספרים מלאים ב-TODO.)*

**איזון עומסי AMR אינו מקור הפער** — np=4 עם ובלי: **9 תאים מתוך 80,000**,
שיאים זהים לשתי ספרות. **ומה שכן:** פי **1.33** תפוקה (699 מול 930 שנ');
np=4 מהיר **פי 3.1** מ-np=1.

**הכשל התלת-ממדי לסירוגין שוחזר: 1 מתוך 17 ≈ 6 %**, המקרה שמור ב-
`/root/night2_keep/attempt_10/`. חתימת ה-SIGFPE זהה ללילה הראשון
(`decode()` → `rhoU/rho`) **אבל המקרה הזה בלי AMR** — כלומר "AMR הוא
הסיבה" נכון למקרה ההוא ואינו הכללה.

### מספרים שהם עכשיו עובדה

- 8/8 חבילות WSL **PASS**. `test_foam_parallel`: np1↔np2 שיא **2795.0 מול
  2794.7 kPa, סטייה יחסית 1.1e-04**. עוגן KB עם afterburn: **יחס 1.02**.
- המטריצה המהירה: 30 חבילות, **`test_blast2d` 162.1 שנ' = 47 %** מזמן הקיר.
- היענות ה-GUI תקינה בכלל — מחוץ ל-`C10`, `D04` ו-`F06` **שום תרחיש לא
  חצה 3.2 שנ'**, ושלושת החריגים על הנתיב התלת-ממדי.
- אפיון קלט מספרי (`I05`): `1e400`/`nan`/`inf` → "must be a finite number";
  `'1,5'` → "is not a number"; `' 1 '` מתקבל; `'-0'` → "must be > 0".

---

## 7ב. סשן התיקונים 2026-09-12 (אחר הצהריים) — עשרת הממצאים טופלו

> אישור בעלים ~15:00: חופש מלא. הניתוח המלא: [NIGHT2_RESULTS.md](NIGHT2_RESULTS.md) §4.9.
> **רגרסיה בייט-זהה אחרי כל קומיט; מטריצה מהירה 30/30 אחרי הכל.**

| ממצא | קומיט | ההוכחה |
|------|-------|---------|
| N2-09 טבלת המדים | `5afe1ca` | `mapped=True` בכל גובה 840–1080 (היה נעלם עד 960) |
| wait_log (תקלת-כלי שנתפסה תוך שעה) | `736c309` | baseline ברגע ה-click; E03 15 שנ' אפס ממצאים, F01 ירוק |
| N2-06/10/11 קוסמטיים | `2fa79f2` | צילום אחד מראה את שלושתם |
| N2-12 הקפאת Run | batch | **13,266→2,643ms** — מפולת ייבוא VTK, מחוממת בדיימון |
| N2-05 level_map | batch | בייט-זהה מול baseline; 1,445→245ms |
| N2-07 rho0 ב-preview | batch | בדיקות ANFO חדשות; טבלת חומרים אחת (N11/T46) |
| **N2-13+14 השרשרת** | `b343d89`+`eeb8853` | **4/4 שרשראות זהות ספרה-בספרה** (s1=0.050, s2=0.194, t0=0.00019422544); IC של שלב 3: T≤2,149K (היה 8.3e6), אפס תאים ברצפה |

**השרשרת — ארבע שכבות עד דטרמיניזם** (עצירה תלוית-שעון → לוח כתיבות
תלוי-שעון → עיגון לכתיבה שלפני-ההגעה → סריקה קדימה כי הזנב מתאוורר) —
כל אחת ננעלה במדידה; המפורט ב-RESULTS. **תובנת המפתח:** המסירה הישנה
הייתה מצב אחרי-אוורור (2–4.7ms במקום 0.194ms) — משם הגיעו מצבי הוואקום.

**נסגרו גם:** הקריסה הלסירוגין ניתנת לשחזור דטרמיניסטי ב-2 דק'
(`/root/night2_keep/`) · סתירת ה-A/B אינה סתירה (1.453 % ו-0.042 % הן
תצפיות שונות; שני השערים עוברים) · **R4 PASS 754 שנ'** (ריצה ראשונה) ·
**R5 מסתיים ב-35 שנ'** — פולקלור ה"45 דקות" קדם ל-T50; חוזר לרשימה.

### השלמות 13.09 (בוקר) — סגירת כל הפתוחים

| מה | קומיט | ההוכחה |
|-----|-------|---------|
| **N2-15** — עצירת ההגעה הדו-ממדית על דגימת ה-live | `08ce68d` | R2 רץ 8.7 שעות מעבר להגעה כי הבדיקה הייתה ingest-gated (2,193 דגימות בתור); עכשיו הבדיקה רואה את מצב הקצה העדכני תמיד. אימות סופי: R2 עצמו (רץ) |
| **N2-08** — חימום GL ב-idle | `ab8acfd` | הזנה ראשונה 1,683→**971ms**; שער G4 של E06 עובר לראשונה (984ms) |
| **שיעור הקריסה — נסגר** | — | אחרי N2-13 השרשרת דטרמיניסטית ⇒ "לפעמים" איננו מבנית; **24/24 ריצות זהות ובריאות** (`s1=0.050 s2=0.194 FAILs=0` — tuple יחיד בכולן) |
| באנר "(pinned schedule)" | `08ce68d` | הבאנר כבר לא משקר לשלבי שרשרת |

### 14.09 — פריטי ההמשך של ליל 3 ("תתקן את פריטי ההמשך")

| מה | קומיט | ההוכחה |
|-----|-------|---------|
| **UX-01/02/03** — צד terminate בברירת-מחדל של הטופס · תווית מטען לפי גאומטריה · רמז-פורמט חי ברשימות | `a0dd97d` | המסך הראשון מוולד נקי; ה-placeholder של CTkEntry 6.0 מת עם textvariable (משווה את האובייקט ל-"") — הרמז עבר לתווית; results-fields/solver-mode/case-validate PASS, regression בייט-זהה |
| **UX-04** — הערת "burst x is ignored" באקסיסימטרי | `fcf34c2` | שלוש בדיקות חדשות ב-test_case_validate (דולק ב-x≠0, כבוי ב-x=0 ובפלנרי) |
| **UX-05** — רצועת-ריק 200px מעל גרף המדים | `8bc1e19` | CTkFrame ריק שומר על גודל ברירת-המחדל 200×200; הבר נארז/נפרק עם הסלקטור. נמדד חי: פער 0 (p-only) / 30px (רב-שדות) / 0; הגרף קיבל 436px במקום 274 |
| **UX-06** — כותרות הדו"ח משם-השדה; "Gauge time histories" | `8bc1e19` | test_report PASS; אין יותר "blast 2d pressure" ואין "Gauges" כפול |
| **E06 — נסגר סופית** | `04fcbee` | ה"בנייה-לכל-תוצאה" של ~1s היא BlastScene **ראשון-בתהליך** (809 מתוך 924ms; השני 14ms) — plotter ריק לא נוגע ב-mappers. חימום idle שלישי (+5.2s, סצנת 4³ זרוקה): הזנה ראשונה 980→**272ms**, חוזרות 134ms; השער נשאר 1000ms ועובר פי 3.7 |
| **הצמדת מכשולים לפאות-תא** | `4e97108` | `refine.snap_obstacles` — הצמדה החוצה לפאות תא-בסיס בזמן תכנון; קשרי-השוויון של N2-16 בטלים מבנית. גולדנים: בדיוק שתי שורות boxToCell (דיף אומת מול החשבון). e2e אמיתי: קצה בכוונה על 20.5·dx — פייתון ו-topoSet מגלפים 84=84 תאים; נייטיבי לא נגוע, regression בייט-זהה |
| **N3-01** — עצירת-הגעה 3D חיה + שער הסימטריה דטרמיניסטי | `f5feb93` | rim-check על מישור ה-live (הוכח יורה: "live slice"); הבי-מודליות = פיצול-מסלול מהשכתוב האדפטיבי (adjustableRunTime גוזר deltaT על זמני-כתיבה) — הבדיקה מקבעת לוח ומיישרת מדים למרכזי-תא-מראה. לפני: 4 FAIL/6; אחרי: 5/5. נותרה תצפית פתוחה: הטיה כיוונית 4.85 % דטרמיניסטית בפתרון (ב-TODO) |

### 14.09 (המשך) — סבב הבאגים וההיגיינה ("תתקן את הבאגים וההיגיינה")

| מה | קומיט | ההוכחה |
|-----|-------|---------|
| **W2/P1-2 נפסל במדידה** — "ריצה שנעצרה מאבדת את זנב הגייג'" אינו נכון על ההתקנה | — (תיעוד) | מקור: `OSstream::endl()` = write+flush לכל שורת דגימה (OpenFOAM-9, `OSstream.C:213`); מדידה: `kill -9` באמצע "Calculating Fluxes" — 208 שורות ב-ext4 = 208 דרך 9p, מיידית ואחרי 30s. אפס אובדן; ריצת הראיה `20260914-134506` |
| **שורש ההטיה הכיוונית נמצא — פירוק ה-MPI** | `12a255a` | np=1→0.10 % · np=2→0.26 % · np=8→4.85 %, בלתי-תלוי בציר ה-slice (slice x = ספרות slice y); השיא זז ±7 % בין np-ים על רשת קבועה — אפקט מקבילי שאינו AMR (קושר ל-P5-3). הבדיקה מקבעת np=2 ⇒ שער עם מרווח פי 19, בלתי-תלוי-מכונה |
| **P2-3/P2-4 — סבב ההשלמה של ה-e2e** | `b2a67ef`, `406810d` | obstacle3d PASS (בדיקת ה-meta עודכנה להצמדה), refine3d PASS, amr3d PASS (רצועות כוילו-מחדש ל-0.2/0.1: נמדד +23 %/+28 % ושוחזר ספרה-בספרה על רגל סטטית טרייה), chain PASS ‏(3.37 %), chain_amr PASS (מאמת גם את מנגנון P1-5 מקצה-לקצה). כל משפחת ה-`_e2e_foam_*` מכוסה |
| **P5-1 נסגר** — "קורס לסירוגין" איננו מבנית | — (תיעוד) | ריצה 25/25 (14.09, על עץ עם ההצמדה וה-rim-check): PASS מלא, אפס אזהרות, החתימה ספרה-בספרה — s1=0.050 · s2=0.194 · t0₂=4.9589474e-05 · t0₃=0.000194225. המכשור נשאר דרוך |
| P2-6, P2-9, CRLF — סגירות רישום | — | chain-e2e קיים ורץ 25/25; test_blast3d כבר בקבוצת slow במטריצה; `core.autocrlf=input` מאומת בקונפיג המקומי |

---

## 8. בייסליינים, גרסאות קובץ וקומיטים

**מדיניות `test_regression`:** חייב להישאר ירוק בייט-בייט. re-baseline רק כשמשימה אומרת זאת
במפורש, ובאותו קומיט. גולדנים של foam מתחדשים רק דרך
`python blastlab/tests/test_foam_writer.py --update` + diff שנבדק בעין.
עץ הגולדן האחרון שנוסף: `case2d_axi_profile_amr` (T70) — שלב מאותחל מפרופיל עם AMR,
שהשדות שלו נכתבים על רשת הבסיס. הוספתו לא הזיזה אף גולדן קיים (נבדק בעין).

**re-baselines שבוצעו:** T8 (חבילת התיקונים הנייטיביים — הריצה המרוכזת היחידה); T36 (אתחול המטען
המשמר); T50–T54 (`transcript.txt` בלבד — 30 שורות ניסוח, כל הבייסליינים המספריים זהים בייט);
T60 (`transcript.txt` בלבד — שורת `Outer boundary` אחת, תוספת בלבד).

**`settings.json` (N21):** נוספו `hw_fingerprint` ו-`hw_host_ram_gb`; שום מפתח לא שונה שם
ולא הוסר, וקובץ ישן נטען כרגיל — הוא פשוט חסר fingerprint, ולכן המספרים השמורים בו
נדחים פעם אחת עד לבדיקה הראשונה. `mpi_max_ranks` נוסף כמפתח ללא UI (כמו `mpi_headroom`).
**`test_regression` לא הושפע מ-N21** ואינו יכול להיות מושפע: התקרה הנגזרת רק מנמיכה את
`CELLS_*`, והסולברים עצמם ממשיכים לאכוף את הקבועים ללא שינוי.

**גרסאות קובץ המקרה (`VERSION`):** 5 → 6 `anim_mesh` (T49) … → 10 (T50–T52 boundary kinds, t_end,
trigger) → **11** (T63: שלושת מפתחות הטריגר נמחקים ב-`dim == 1` לפני בדיקת המפתחות הלא-מוכרים,
כדי שכל קובץ 1D שמור וכל `case.json` של ריצה ישנה ימשיכו להיטען).

**קומיטים מרכזיים:** `ba37a65` + `73ca834` (QA S1/S2), `3cb800c` (QA S4), `a6c7463` (ולידציה
ומשוב), `c3ce365` (T61), `a7930e3` (T60), `a416630` (T58/T59), `5262277` (T57), `972dca9` (T56).
ההיסטוריה המלאה של ROADMAP: `git show 73ca834:ROADMAP.md`.
