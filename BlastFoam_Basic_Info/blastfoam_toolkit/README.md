# BlastFOAM Toolkit
## ערכת כלים ללימוד ועבודה עם BlastFOAM

---

## 📁 מבנה הערכה

```
blastfoam_toolkit/
├── README.md                    # קובץ זה
├── docs/                        # תיעוד ומדריכים
│   ├── blastfoam_guide.md      # מדריך מקיף בעברית
│   ├── jwl_parameters.md       # פרמטרי JWL לחומרי נפץ
│   └── cheatsheet.md           # דף עזר מהיר
├── scripts/                     # סקריפטים לאוטומציה
│   ├── case_generator.py       # יצירת מקרי סימולציה
│   ├── post_processor.py       # עיבוד תוצאות
│   └── validator.py            # בדיקת תקינות מקרים
├── templates/                   # תבניות קבצים
│   └── basic_case/             # תבנית מקרה בסיסי
└── examples/                    # דוגמאות
    └── airblast_sphere/        # פיצוץ כדורי באוויר
```

---

## 🚀 התחלה מהירה

### 1. יצירת מקרה חדש
```bash
cd scripts
python case_generator.py my_blast --type airblast --explosive TNT
```

### 2. בדיקת תקינות המקרה
```bash
python validator.py ../my_blast
```

### 3. הרצת הסימולציה
```bash
cd my_blast
./Allrun
```

### 4. עיבוד תוצאות
```bash
cd ../scripts
python post_processor.py ../my_blast --field p --export results.csv
```

---

## 📚 תיעוד

| קובץ | תיאור |
|------|-------|
| `docs/blastfoam_guide.md` | מדריך מקיף עם הסברים בעברית |
| `docs/jwl_parameters.md` | פרמטרי JWL לחומרי נפץ נפוצים (TNT, C4, RDX, HMX) |
| `docs/cheatsheet.md` | דף עזר מהיר עם פקודות וטיפים |

---

## 🔧 סקריפטים

### case_generator.py
יוצר מבנה תיקיות מלא לסימולציית BlastFOAM.

```bash
python case_generator.py <שם> [--type TYPE] [--explosive EXPLOSIVE]

# סוגי סימולציה:
#   airblast   - פיצוץ באוויר פתוח (ברירת מחדל)
#   underwater - פיצוץ תת-מימי
#   confined   - פיצוץ במרחב סגור

# סוגי חומרי נפץ:
#   TNT, C4, RDX
```

### post_processor.py
מנתח תוצאות מסימולציה ומייצא נתונים.

```bash
python post_processor.py <נתיב> [--field FIELD] [--export FILE]

# שדות זמינים: p (לחץ), T (טמפרטורה), U (מהירות), rho (צפיפות)
```

### validator.py
בודק תקינות מקרה לפני הרצה.

```bash
python validator.py <נתיב>
```

---

## 📖 משאבים נוספים

- **GitHub**: https://github.com/synthetik-technologies/blastfoam
- **User Guide**: https://github.com/synthetik-technologies/blastfoam/blob/master/BlastFoam_User_Guide.pdf
- **Workshop Video**: https://youtu.be/OLpRcjR3cW4
- **OpenFOAM**: https://openfoam.org

---

## 💡 טיפים

1. **התחל קטן** - התחל עם רשת גסה וזמן קצר
2. **בדוק Courant** - שמור על Co < 0.5
3. **השתמש ב-AMR** - עידון אדפטיבי חוסך משאבים
4. **וודא וידוא** - השווה לתוצאות מוכרות

---

*נוצר כחלק מתהליך למידת BlastFOAM*
