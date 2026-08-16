# מדריך מקיף ל-BlastFOAM

## מבוא

BlastFOAM הוא סולבר קוד פתוח המבוסס על OpenFOAM, המיועד לסימולציית פיצוצים, גלי הלם, וזרימות דחיסות גבוהה. פותח על ידי Synthetik Applied Technologies.

---

## 1. התקנה

### דרישות מוקדמות
- OpenFOAM 9 (מומלץ)
- gnuplot (אופציונלי, לגרפים)

### שלבי התקנה

```bash
# 1. התקנת OpenFOAM 9
cd $HOME
mkdir -p OpenFOAM
cd OpenFOAM
git clone https://github.com/OpenFOAM/OpenFOAM-9.git
cd OpenFOAM-9
echo "source $HOME/OpenFOAM/OpenFOAM-9/etc/bashrc" >> ~/.bashrc
source etc/bashrc
./Allwmake > log.Allwmake 2>&1

# 2. התקנת BlastFOAM
cd $HOME/OpenFOAM
git clone https://github.com/synthetik-technologies/blastfoam.git
cd blastfoam
echo "source $HOME/OpenFOAM/blastfoam/etc/bashrc" >> ~/.bashrc
source ~/.bashrc
./Allwmake -j
```

---

## 2. מבנה תיקיית Case

כל סימולציה ב-BlastFOAM מאורגנת בתיקייה עם המבנה הבא:

```
case_name/
├── 0/                    # תנאי התחלה
│   ├── p                 # לחץ
│   ├── T                 # טמפרטורה
│   ├── U                 # מהירות
│   └── alpha.*           # שבר נפחי (לזרימה רב-פאזית)
├── constant/             # תכונות פיזיקליות קבועות
│   ├── phaseProperties   # הגדרות פאזות וחומרי נפץ
│   ├── thermophysicalProperties
│   ├── turbulenceProperties
│   └── polyMesh/         # הרשת
├── system/               # הגדרות סולבר
│   ├── controlDict       # פרמטרי זמן ופלט
│   ├── fvSchemes         # סכמות נומריות
│   ├── fvSolution        # הגדרות פתרון
│   ├── setFieldsDict     # הגדרת שדות התחלתיים
│   └── decomposeParDict  # הגדרות לריצה מקבילית
└── Allrun                # סקריפט הרצה
```

---

## 3. משוואות מצב (Equations of State)

BlastFOAM תומך במשוואות מצב מגוונות:

| משוואת מצב | שימוש טיפוסי |
|-----------|--------------|
| idealGas | גז אידיאלי, אוויר בתנאים רגילים |
| stiffenedGas | נוזלים, מים |
| JWL | חומרי נפץ (TNT, C4) |
| JWLC | חומרי נפץ - צורה מורחבת |
| BKW | חומרי נפץ מתקדמים |
| Tait | נוזלים בלחץ גבוה |
| Tillotson | נוזלים עם קוויטציה |
| AbelNobel | דלקים מוצקים |

### דוגמה - הגדרת אוויר:
```cpp
air
{
    type            detonatingSolidFluid;
    reactants
    {
        thermoType
        {
            transport       const;
            thermo          eConst;
            equationOfState idealGas;
        }
        specie { molWeight 28.97; }
        thermodynamics { Cv 718; Hf 0; }
        transport { mu 1.8e-5; Pr 0.7; }
    }
    // ...
}
```

---

## 4. מודלים של הפעלה (Activation Models)

| מודל | תיאור |
|-----|-------|
| none | תגובה מיידית |
| linear | הפעלה ליניארית מרובת נקודות |
| pressureBased | הפעלה מבוססת לחץ |
| Arrhenius | קצב תגובה לפי ארהניוס |
| programmedIgnition | הצתה מתוכנתת |

### דוגמה - הפעלה מבוססת לחץ:
```cpp
activationModel pressureBased;
pressureBasedCoeffs
{
    pMin    1e8;    // לחץ מינימלי להפעלה [Pa]
}
```

---

## 5. סולברים עיקריים

| סולבר | שימוש |
|-------|------|
| blastFoam | זרימה דחיסה חד/רב-פאזית |
| blastEulerFoam | שיטות אוילריאניות רב-נוזליות |
| blastParcelFoam | שיטות לגרנז'יאניות |
| blastFSIFoam | אינטראקציה נוזל-מבנה (ניסיוני) |

---

## 6. סכמות נומריות

### fvSchemes - סכמות מומלצות:
```cpp
ddtSchemes
{
    default         Euler;  // או RK2SSP, RK3SSP לדיוק גבוה
}

gradSchemes
{
    default         cellLimited leastSquares 1;
}

divSchemes
{
    default         none;
    div(tauMC)      Gauss linear;
}

laplacianSchemes
{
    default         Gauss linear corrected;
}

interpolationSchemes
{
    default         linear;
    reconstruct(rho) MUSCL vanLeer;
    reconstruct(U)   MUSCL vanLeer;
    reconstruct(e)   MUSCL vanLeer;
    reconstruct(p)   MUSCL vanLeer;
}
```

---

## 7. עיבוד תוצאות

### חישוב לחץ-על שיא ואימפולס:
```cpp
// בקובץ controlDict
functions
{
    overpressureAndImpulse
    {
        type            overpressureAndImpulse;
        pRef            101325;  // לחץ ייחוס [Pa]
    }
}
```

### המרה ל-VTK:
```bash
blastToVTK -case <case_name>
```

### Probes - מדידת ערכים בנקודות ספציפיות:
```cpp
functions
{
    probes
    {
        type        probes;
        probeLocations
        (
            (0 0 0)
            (1 0 0)
            (2 0 0)
        );
        fields (p U T);
        writeControl    timeStep;
        writeInterval   1;
    }
}
```

---

## 8. AMR - עידון רשת אדפטיבי

BlastFOAM תומך בעידון רשת דינמי:

```cpp
// בקובץ dynamicMeshDict
dynamicFvMesh   adaptiveFvMesh;

adaptiveFvMeshCoeffs
{
    refiner         polyRefiner;  // או hexRefiner
    refineInterval  1;
    unrefineInterval 1;
    
    maxRefinement   3;
    nBufferLayers   1;
    
    // קריטריונים לעידון
    adaptCriteria
    {
        field   rho;
        type    gradient;
        lowerRefineLevel 0.1;
        upperRefineLevel 0.9;
    }
}
```

---

## 9. ריצה מקבילית

### הגדרת decomposition:
```cpp
// decomposeParDict
numberOfSubdomains  4;
method              scotch;
```

### הרצה:
```bash
decomposePar
mpirun -np 4 blastFoam -parallel
reconstructPar
```

---

## 10. טיפים חשובים

1. **בדיקת מספר Courant**: שמור על Co < 0.5 לסימולציות פיצוצים
2. **עידון רשת**: השתמש ברשת עדינה יותר באזור הפיצוץ
3. **תנאי שפה**: ודא שתנאי השפה מתאימים לבעיה
4. **וידוא**: השווה לתוצאות ניסיוניות או אנליטיות
5. **AMR**: השתמש בעידון אדפטיבי לחיסכון במשאבים

---

## 11. משאבים נוספים

- [GitHub Repository](https://github.com/synthetik-technologies/blastfoam)
- [User Guide PDF](https://github.com/synthetik-technologies/blastfoam/blob/master/BlastFoam_User_Guide.pdf)
- [Workshop Recording (YouTube)](https://youtu.be/OLpRcjR3cW4)
- [CFD Online Forum](https://www.cfd-online.com/Forums/openfoam-community-contributions/224644-blastfoam-question.html)
