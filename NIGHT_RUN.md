# NIGHT_RUN.md — הפרומפט לריצת לילה על המכונה החזקה

> **מה זה.** פרומפט אחד להדבקה ב-Claude Code על המכונה השנייה (`cee-elsl-d`),
> שירוץ לילה שלם ללא השגחה: כל מטריצת הבדיקות, כל חבילות ה-WSL, תשע הריצות
> הכבדות מ-[HEAVY_RUNS.md](HEAVY_RUNS.md), ותחקיר ה-SIGFPE.
>
> **האזהרה החשובה ביותר:** המכונה השנייה עובדת על **אותה תיקייה** (סנכרון
> OneDrive). אני ממשיך לערוך כאן קבצים באותו זמן. לכן הפרומפט אוסר במפורש
> על ריצת הלילה לקמט, לדחוף, לעשות pull/stash/checkout, או לגעת ב-TODO.md /
> DONE.md / HEAVY_RUNS.md. היא כותבת **רק לקבצים חדשים**. בלי זה שני הצדדים
> ידרסו זה את זה, וגם `.git` עצמו בסיכון (זה בדיוק P4-1 ב-TODO).

---

## איך להשתמש

1. במכונה השנייה, לפתוח טרמינל בתיקיית הפרויקט.
2. לוודא שהסנכרון סיים (סמל OneDrive ירוק) — כדי שהיא תראה את הקוד העדכני,
   כולל תיקוני הפיקסצ'רים של R3.
3. להפעיל `claude`, ולהדביק את כל הבלוק שבסעיף הבא.
4. להשאיר את המכונה דולקת ולא לישון (`powercfg /change standby-timeout-ac 0`
   ב-Windows, או `sudo systemd-inhibit --what=sleep sleep infinity &` בלינוקס).
5. בבוקר — לומר לי, ואני אקרא את `NIGHT_RESULTS.md`.

---

## הפרומפט

```
אתה רץ לילה שלם ללא השגחה על מכונה חזקה, בתיקיית פרויקט blastlab.
קרא את הקבצים HEAVY_RUNS.md ו-TODO.md לפני שאתה מתחיל. אל תשאל שאלות -
אין מי שיענה. אם משהו לא ברור, בחר את האפשרות השמרנית, תעד את הבחירה,
והמשך.

═══ כללי ברזל ═══

1. התיקייה הזו מסונכרנת ב-OneDrive עם מכונה אחרת שעובדת עליה במקביל.
   לכן, בשום שלב:
   - אל תריץ git commit, git push, git pull, git stash, git checkout,
     git reset או git merge. בכלל.
   - אל תערוך אף קובץ קיים. במיוחד לא TODO.md, DONE.md, HEAVY_RUNS.md,
     ולא שום קובץ תחת blastlab/.
   - כל הפלט שלך הולך לקבצים חדשים בלבד: NIGHT_RESULTS.md,
     NIGHT_LOG.md, ותיקייה חדשה בשם night_artifacts/.
   החריג היחיד: אם בדיקה לא רצה בלי תיקון זעיר בקוד - אל תתקן. תעד את
   התיקון הנדרש כ-diff בתוך NIGHT_RESULTS.md, וסמן את הריצה כ-BLOCKED.

2. אל תריץ שתי ריצות WSL/foam במקביל. לעולם. לפני כל ריצה כזו ודא:
       wsl.exe -d Ubuntu -- pgrep -a blastFoam
   (או pgrep -a blastFoam אם זו לינוקס ילידית) - חייב לחזור ריק.
   אם לא ריק וזה לא שלך - חכה עד 10 דקות, ואם עדיין תפוס דלג על הריצה
   ותעד "SKIPPED: foreign solver".

3. אל תיגע בבייסליינים. אם test_regression נכשל - זו תוצאה לתעד, לא
   משהו לתקן. לעולם אל תריץ test_regression.py --update או
   test_foam_writer.py --update.

4. אל תמחק את blastlab_runs לפני שתיעדת. אם הדיסק מתקרב למלא, השתמש ב-
       python -m blastlab --clean-foam-runs --keep-gb 20
   ותעד שעשית זאת.

5. אל תריץ עם timeout את test_blast3d ואת _e2e_foam_obstacle2d - הן
   ארוכות בכוונה, וריצה שנקטעת נראית ככשל ואינה. לכל השאר תן timeout
   נדיב (30 דקות) כדי שריצה תקועה לא תבלע את הלילה.

6. תקציב זמן: 8 שעות. עבוד לפי הסדר שלמטה. אם נגמר הזמן - עצור בגבול
   ריצה שלמה, ותעד מה לא הספקת.

═══ שלב 0: כותרת ═══

צור NIGHT_RESULTS.md ופתח אותו בסעיף "סביבה" ובו:
  - hostname, מערכת ההפעלה, גרסה
  - CPU: דגם, ליבות פיזיות, ליבות לוגיות
  - RAM כולל
  - האם זו WSL או לינוקס ילידית. אם WSL: תוכן %USERPROFILE%\.wslconfig,
    והפלט של "wsl.exe -d Ubuntu -- free -h" ו-"nproc"
  - הפלט של:
        cd blastlab/tests && python -c "import sys; sys.path.insert(0,'../..'); from blastlab.solvers.foam import env; print(env.hardware(probe=True))"
  - git rev-parse HEAD, ו-git status --porcelain (רק לקריאה! כדי שנדע
    על איזו גרסה זה רץ)
  - מקום פנוי בדיסק

שים לב: הפרויקט מצפה ל-WSL בשם Ubuntu ול-
/root/OpenFOAM/OpenFOAM-9/etc/bashrc. אם זו לינוקס ילידית, סביר
שחבילות ה-foam ידלגו או ייכשלו בשלב הזיהוי - זו תוצאה חשובה בפני עצמה,
תעד אותה במפורש בראש הקובץ ואל תנסה לעקוף אותה בקוד.

═══ שלב 1: בסיס (חייב לעבור) ═══

    cd blastlab/tests
    python test_foam_env.py
    python test_regression.py

אם test_regression נכשל - עצור את כל הלילה. תעד את הפלט המלא. שאר
הבדיקות חסרות משמעות בלי בסיס ירוק. כתוב בראש NIGHT_RESULTS.md
"ABORTED: regression baseline broken" והפסק.

═══ שלב 2: המטריצה המהירה (ללא WSL, ~15 דקות) ═══

הרץ, כל אחת בנפרד, ותעד PASS/FAIL + זמן:

    test_foam_writer, test_foam_reader, test_case_validate, test_hardware,
    test_adaptive_interval, test_foam_live_due, test_refine,
    test_bc_trigger, test_foam_ingest_order, test_foam_amr_ingest,
    test_foam_postmortem_decomposed, test_foam_resume, test_gauge_summary,
    test_report, test_gui_drain, test_gui_results_fields,
    test_gui_results_anim, test_gui_refine_preview, test_gui_amr_form,
    test_gui_solver_mode, test_gui_gauge_summary, test_gui_title_preview1d,
    test_gui_run_browser, test_viz3d_sampling, test_viz3d_hooks,
    test_viz3d_scene, test_viz3d_panel, test_blast2d, test_foam_env

לכל כשל: 30 השורות האחרונות של הפלט.

═══ שלב 3: חבילות WSL (~30 דקות) ═══

אחת אחרי השנייה, עם בדיקת פנוי לפני כל אחת:

    test_foam_1d_vs_native, test_foam_2d, test_foam_3d_smoke --tiny,
    test_foam_parallel, test_foam_postmortem, test_foam_features,
    test_foam_kb_anchor --afterburn, test_foam_stop

ב-test_foam_parallel תעד במיוחד את השורה "rank ceiling here: N" -
במכונה שלנו היא 2, וכל העניין הוא לראות מה היא אצלך.

═══ שלב 4: הריצות הכבדות R1..R8 ═══

בצע בדיוק לפי HEAVY_RUNS.md סעיף 3, בסדר R1, R2, R3, R4, R5, R6, R7, R8.
לכל אחת יש שם פקודה מדויקת, "מה לתעד" ו"מה נחשב הצלחה". תעד לפי הפורמט
של סעיף 4 שם: מכונה, פקודה, זמן קיר, תוצאה, זנב הפלט, מספרים שנמדדו.

חשוב במיוחד:
  - R1: אם המקרה המלא רץ - זמן הקיר ושיא ה-RSS הם התוצר. ההחלטה על
    ברירות המחדל של האפליקציה תלויה בהם.
  - R6: חשב BYTES_PER_CELL מהרגרסיה על שלוש הנקודות והשווה ל-2650.
  - R7: טבלת ranks -> זמן קיר -> שיאי גייג'ים. זו הבדיקה שאי אפשר לעשות
    אצלנו בכלל (התקרה שלנו 2).
  - R9 הוא בדיקות עין - אל תריץ, רק הכן את החומר: הרץ
        python _qa_gui_harness.py --scenario D04,E05,E06
    ותעד איפה הצילומים נשמרו.

תעד גם ריצות שעוברות. בחצי מהן המספר הוא התוצר, לא ה-PASS.

═══ שלב 5: תחקיר ה-SIGFPE ═══

לפני כמה שעות רצה על המכונה הזו ריצה שקרסה כך:

    mpirun noticed that process rank 6 ... exited on signal 8
    (Floating point exception)
    stack: blastFoam ... timeIntegrator::postUpdateAll()
                        <- timeIntegrator::integrate()

זו מלכודת FPE של OpenFOAM: נוצר NaN/Inf או חלוקה באפס בשלב עדכון
המשתנים, אצל rank אחד. אני צריך לדעת מה גרם לזה.

עשה כך:
  1. מצא את תיקיית הריצה שקרסה. blastlab לא מוחק מקרה שנכשל; חפש את
     הריצות האחרונות ב-/root/blastlab_runs (או היכן שהן אצלך) ואת אלה
     שאין בהן זמן כתיבה אחרון תקין. תעד את שם התיקייה.
  2. שלוף מתוך הלוג שלה את 60 השורות שלפני הקריסה, ובמיוחד את:
        Time = ...
        Courant Number Mean/Max = ...
        deltaT = ...
        max(p) / min(p) / max(T) / min(T)
     העתק אותן ל-NIGHT_RESULTS.md כמות שהן. אם min(p) או min(T) ירדו
     לאפס או לשלילי, או ש-Courant Max קפץ בסדר גודל - זו התשובה, אמור
     זאת במפורש.
  3. תעד את case.json של אותה ריצה (ממדים, גודל תא, מטען, מספר ranks,
     AMR, מכשולים, מצב אתחול).
  4. נסה לצמצם - שלוש ריצות, ותעד לכל אחת אם קרסה או לא:
       א. אותו מקרה בדיוק עם n_procs=1 (סריאלי)
       ב. אותו מקרה עם cfl נמוך ב-50%
       ג. אותו מקרה בלי AMR (אם היה AMR)
     המסקנה: אם (א) עובר - זו בעיית חלוקה/גבולות בין תת-תחומים. אם (ב)
     עובר - זה צעד זמן. אם (ג) עובר - זה עידון דינמי. אם כולן קורסות -
     המקרה עצמו לא יציב, ואז צרף את הפלט של הריצה הסריאלית.
  5. אל תתקן כלום בקוד. רק תעד.

═══ שלב 6: ניקיון וסיכום ═══

  1. ודא שלא נשארו סולברים יתומים:
        wsl.exe -d Ubuntu -- pgrep -a blastFoam     (חייב להיות ריק)
     אם נשארו - הרוג אותם ותעד.
  2. תעד כמה מקום תופס blastlab_runs בסוף.
  3. ודא ש-git status נראה כמו בהתחלה פרט לקבצים החדשים שלך. אם קובץ
     קיים השתנה - תעד את זה בראש NIGHT_RESULTS.md כאזהרה בולטת.
  4. כתוב בראש NIGHT_RESULTS.md סיכום של 15 שורות:
     - כמה בדיקות עברו / נכשלו / דולגו
     - שלוש התוצאות החשובות ביותר
     - BYTES_PER_CELL שחישבת ב-R6
     - טבלת ה-ranks מ-R7
     - זמן הקיר של R1
     - המסקנה מתחקיר ה-SIGFPE
     - מה לא הספקת ולמה

═══ הערה אחרונה ═══

עבוד לפי הסדר. אל תדלג על ריצה בלי לכתוב שורה שמסבירה למה. אל תסכם
"הכל עבר" אם משהו דולג. עדיף לילה עם חצי מהרשימה ותיעוד מדויק מאשר
לילה שלם עם סיכום מעורפל.
```

---

## למה הפרומפט בנוי כך

- **קבצים חדשים בלבד** — כי שתי מכונות על אותה תיקייה. ריצת לילה שתעשה
  `git commit` תתנגש עם העבודה שלי כאן ותשבור את `.git` דרך סנכרון OneDrive.
- **`test_regression` כשער** — אם הבסיס אדום, כל מדידה אחרת חסרת ערך, ועדיף
  לילה שנעצר מייד מאשר שמונה שעות של מספרים שאי אפשר לסמוך עליהם.
- **בדיקת WSL פנוי לפני כל ריצה** — סולבר זר מפיל `test_foam_stop` וחבילות
  כבדות-זיכרון בכזב, וזה הבזבוז הכי מתסכל בריצת לילה.
- **timeout על הכל חוץ משתיים** — ריצה תקועה בולעת את הלילה; אבל
  `test_blast3d` ו-`_e2e_foam_obstacle2d axi` ארוכות באמת, וקטיעה שלהן
  מייצרת "כשל" מזויף.
- **שלב 5 מובנה כצמצום ולא כתיקון** — שלוש ריצות שמפרידות בין חלוקה, צעד זמן
  ועידון דינמי. זה מה שיגיד לנו אם ה-SIGFPE הוא באג אצלנו או מקרה לא יציב.
