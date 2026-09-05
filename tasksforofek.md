# משימות ידניות לאופק

דברים שרק אתה יכול לעשות (החלטות, בדיקות עין ב-GUI, ניקוי קבצים אישיים).
מסודר לפי דחיפות. תאריך: 2026-09-05.

## 1. אימות ב-GUI — עידון רשת אזורי + "Show mesh" (T17–T19)

הקוד עבר בדיקות אוטומטיות ו-e2e ב-WSL, אבל את מה שרואים בעין צריך לבדוק ידנית:

1. פתח את האפליקציה, בחר 3D, סולבר `blastfoam`.
2. תחום 10×10×10 m, רשת בסיס 0.5 m, מטען במרכז (5,5,5).
3. בכרטיס **Refinement zones (blastFoam) [m, level]** הוסף:
   - `4 6 4 6 4 6 1`  (רמה 1 = 25 ס"מ)
   - `4.5 5.5 4.5 5.5 4.5 5.5 2`  (רמה 2 = 12.5 ס"מ)
4. ב-Numerics שנה **Charge refinement (blastFoam)** ל-`zone` וראה שהערת האימות מדווחת
   "Local refinement: N level(s) ... mesh cells; ... display grid" ולא "Cell size will be refined".
5. סמן **Show mesh** בכרטיס Model Preview: אמורים להופיע מסגרות האזורים (צבע לפי רמה)
   וקווי הרשת על מישור החתך החי. נסה גם מקרה 2D planar — קווי התאים 50/25/12.5 ס"מ.
6. הרץ גרסה קטנה (למשל 2×2×2 m, בסיס 0.2 m, מטען 1 kg, `zone`): בזמן הריצה סמן
   **Show mesh** ליד "Live slice / 3D view" — הקווים אמורים לשקף תאים גסים כבלוקים.
7. אחרי הריצה, ב-Results: צ'קבוקס **Show mesh** בשורת השדות — בדוק גם את "peak overpressure"
   ו-"net ovp impulse", את ה-replay ואת ייצוא ה-PNG (הקבצים `blast_3d_peak_overpressure_*.png`).
8. פתח את הצופה ה-3D → טאב Display → **Show mesh**; הזז מישור חתך וודא שהקווים עוקבים.
9. טען את הריצה מחדש (Load foam run) וודא שהתצוגה זהה.
10. נסה מקרה אקסיסימטרי עם אזור רמה 2 שנוגע בציר (x0 = 0) — האימות צריך לסרב עם הסבר.

## 2. אימות ב-GUI — תצוגות peak overpressure / impulse (T11)

ריצה נייטיבית 2D ו-3D: ב-Results, השדות "peak overpressure" ו-"net ovp impulse" (ב-3D גם x-z/x-y).
טען תוצאה ישנה (בלי המפות) וודא שהשדות מוסתרים ולא קורסים.

## 3. דיסק (C: היה מלא לחלוטין; עכשיו ~30 GB פנויים)

לא מחקתי שום דבר מלבד סל המחזור (באישורך). החלטות שלך:

- **`OneDrive - Technion\תואר שני\סמסטר ב\אלמנטים סופיים\חומר מרן\OneDrive_1_5-29-2026.zip` — 13.4 GB**:
  לידו תיקייה פרוסה זהה (14 GB, `Lectures`). ה-zip כפול — כנראה למחיקה.
- **`C:\OneDriveTemp` — 6.2 GB**: 5 קבצי `.temp` של העלאות OneDrive מ-2.9. אם OneDrive לא מנקה
  לבד תוך כמה ימים — אפשר למחוק (OneDrive יוצר מחדש).
- **כפילות `Projects\Project_1\REFERENCES` (45 GB) ↔ `OneDrive\תואר שני\תזה\calculation_backup\...\Reference Viper Models`**:
  `Free_Field_500kg` ו-`Free_Field_1500kg` זהים קובץ-קובץ (גודל+תאריך); `50kg` כמעט.
  `Projects` כולו (117 GB) נראה כעותק מקומי של הגיבוי. לבדוק ולהחליט מה נשאר.
- **הרווח הגדול בלי למחוק:** ב-OneDrive, קליק ימני על `250` (153 GB), `גיבוי לכרמל` (64 GB),
  `תואר ראשון` (54 GB) → **Free up space** (Files On-Demand) — נשאר בענן, מתפנה מקומית.
- **WSL `C:\WSL\Ubuntu\ext4.vhdx` — 15 GB**: ריצות הבדיקה שלי יושבות ב-`/root/blastlab_runs`
  (נמדד: 64 ריצות, 12.1 GB, כולן מהיום וכולן הסתיימו). ניקוי: `python -m blastlab --clean-foam-runs`
  (או `--older-than 1` / `--keep-gb 5`); מהגרסה הזו יש גם ניקוי אוטומטי בהפעלת ה-GUI
  (ברירת מחדל: מעל 20 GB או ריצות ישנות מ-14 יום, 3 האחרונות נשמרות; כיבוי דרך
  `auto_cleanup: false` ב-`%APPDATA%\blastlab\settings.json`) וכפתור "Foam runs…" ב-Results. ה-vhdx לא מתכווץ לבד — אם צריך את המקום:
  `wsl --shutdown` ואז `diskpart` → `select vdisk file=C:\WSL\Ubuntu\ext4.vhdx` → `compact vdisk`.
- `hiberfil.sys` 3.1 GB: אם לא משתמשים ב-Hibernate — `powercfg /h off` (כמנהל).

## 4. Git — עבודה לא מחויבת מ-T1–T7

יש ~30 קבצים שהשתנו ב-T1–T7 ולא חויבו בנפרד (הקומיטים של T8–T19 מציינים שחלקם "נוסעים" איתם).
מומלץ קומיט אחד "Land T1–T7 (stop/ingest hardening, display fixes, units, runs-dir safety,
papercuts, chain validation, hooks warnings)" אחרי `git status`.
קבצי שאריות בשורש הריפו שכדאי למחוק או להוסיף ל-`.gitignore`:
`case.json`, `gauges.txt`, `gauges_2d.txt`, `test_profile.txt`, `blastlab/tests/gauges.txt`.

## 5. הריפו יושב בתוך OneDrive

`git worktree remove` נכשל פעם אחת על "Permission denied" (נעילת סנכרון על `.git`).
שקול להחריג את `.git` מסנכרון או להעביר את הריפו מחוץ ל-OneDrive (ולשמור גיבוי דרך git remote).

## 6. החלטה: פרמטרי afterburn לחומרים שאינם TNT

מודל ה-afterburn (T16) עובד ומכויל ל-TNT מול Kingery-Bulmash (0.95-1.03 במקום 0.72-0.77).
לשאר החומרים (C4, RDX, HMX, PETN, ANFO) ה-Q0 נגזר מ**איזון חמצן** בלבד - סדר גודל נכון,
לא מכויל מול נתונים. אם אתה מתכוון לצטט מספרים לחומר שאינו TNT, צריך כיול (או מקור).
ברירת המחדל היא `none`, כך שכל מה שרץ עד היום לא השתנה.

## 7. החלטה על B24 (ROADMAP)

אתחול מטען "resolved" ב-2D/3D לא מנרמל למסה/אנרגיה האמיתית — ±3% לפי מיקום המרכז ביחס לפאות
(זה מה שהזיז את בדיקת ההגעה ב-`test_blast2d` מ-4.3% ל-5.2%, והסף הורחב ל-6%).
תיקון = S + re-baseline נוסף. להחליט אם לעשות.

## 8. e2e ידניים (WSL, ~1–3 דק' כל אחד)

לא הרצתי את ה-GUI e2e (דורש חלון): `blastlab/tests/_e2e_gui_foam.py`, `_e2e_gui_view3d.py`
(רצוי על ריצה מעודנת — ראה סעיף 1), `_e2e_gui_native_warn.py`.
