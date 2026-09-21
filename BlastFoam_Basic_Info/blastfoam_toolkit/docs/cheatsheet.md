> **Academic CFD — blast-wave gas dynamics, Technion.** Learning material for
> blastFoam, the public open-source airblast solver. This project computes a pressure
> field in air and the structural load it produces, for blast-resistant design and
> explosive-safety siting. Scope: [../../../docs/SCOPE.md](../../../docs/SCOPE.md)

# BlastFOAM Quick Reference / דף עזר מהיר
═══════════════════════════════════════════════════════════════

## הרצה בסיסית / Basic Run Commands

```bash
# יצירת רשת
blockMesh

# הגדרת שדות התחלתיים
setFields

# הרצת הסולבר
blastFoam

# הרצה מקבילית
decomposePar
mpirun -np 4 blastFoam -parallel
reconstructPar

# ניקוי
foamCleanTutorials
# או
rm -rf 0.[0-9]* [1-9]* constant/polyMesh processor* log.*
```

---

## מבנה תיקיות / Directory Structure

```
case/
├── 0/           → תנאי התחלה (p, T, U, alpha.*)
├── constant/    → phaseProperties, polyMesh/
└── system/      → controlDict, fvSchemes, fvSolution
```

---

## controlDict - הגדרות נפוצות

```cpp
application     blastFoam;
endTime         0.01;           // זמן סיום [s]
deltaT          1e-7;           // צעד זמן [s]
writeInterval   1e-4;           // מרווח כתיבה [s]
maxCo           0.5;            // מספר Courant מקסימלי
adjustTimeStep  yes;            // התאמת צעד זמן אוטומטית
```

---

## סכמות מומלצות / Recommended Schemes

```cpp
// fvSchemes
fluxScheme      HLLC;           // או AUSM+
ddtSchemes      { default Euler; }
gradSchemes     { default cellLimited leastSquares 1; }

// אינטרפולציה עם MUSCL
interpolationSchemes
{
    reconstruct(rho)  MUSCL vanLeer;
    reconstruct(U)    MUSCL vanLeer;
    reconstruct(e)    MUSCL vanLeer;
    reconstruct(p)    MUSCL vanLeer;
}
```

---

## משוואות מצב / Equations of State

| EOS          | שימוש                    | פרמטרים עיקריים |
|--------------|--------------------------|----------------|
| idealGas     | גזים בתנאים רגילים       | gamma          |
| stiffenedGas | נוזלים                   | gamma, p0      |
| JWL          | חומרי נפץ               | A,B,R1,R2,ω    |
| Tait         | מים בלחץ גבוה           | B, n           |

---

## מודלים של הפעלה / Activation Models

```cpp
// הפעלה מיידית
activationModel none;

// ליניארית
activationModel linear;
linearCoeffs
{
    vDet    6930;               // מהירות דטונציה [m/s]
    pMin    1e6;                // לחץ מינימלי [Pa]
    points  ( (0 0 0) );        // נקודות הפעלה
}

// מבוססת לחץ
activationModel pressureBased;
pressureBasedCoeffs { pMin 1e8; }
```

---

## תנאי שפה / Boundary Conditions

```cpp
// קירות
walls
{
    type    zeroGradient;  // לסקלרים (p, T, rho)
    type    slip;          // למהירות U
    type    fixedValue;    // ערך קבוע
}

// אינלט/אאוטלט
inlet  { type fixedValue; value uniform (100 0 0); }
outlet { type waveTransmissive; }
```

---

## Post-Processing / עיבוד תוצאות

```cpp
// probes - מדידה בנקודות
functions
{
    probes
    {
        type        probes;
        probeLocations ( (1 0 0) (2 0 0) (5 0 0) );
        fields      (p rho T U);
    }
}

// לחץ-על שיא ואימפולס
functions
{
    overpressure
    {
        type    overpressureAndImpulse;
        pRef    101325;
    }
}
```

---

## AMR - עידון רשת / Adaptive Mesh Refinement

```cpp
// dynamicMeshDict
dynamicFvMesh   adaptiveFvMesh;
adaptiveFvMeshCoeffs
{
    refiner         polyRefiner;
    maxRefinement   3;
    nBufferLayers   1;
    
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

## יחידות / Units (SI)

| גודל         | יחידה      | דוגמה           |
|--------------|-----------|-----------------|
| לחץ          | Pa        | 101325 (1 atm)  |
| טמפרטורה    | K         | 293 (20°C)      |
| צפיפות      | kg/m³     | 1.225 (אוויר)   |
| מהירות      | m/s       | 340 (מהירות קול)|
| אנרגיה סגולית| J/kg     | 4.29e6 (TNT)    |

---

## המרות שימושיות / Useful Conversions

```
1 atm = 101325 Pa
1 bar = 100000 Pa
1 psi = 6894.76 Pa
1 kPa = 1000 Pa
1 MPa = 1e6 Pa
1 GPa = 1e9 Pa

°C → K: T[K] = T[°C] + 273.15

TNT equivalent:
1 kg TNT ≈ 4.184 MJ
```

---

## פקודות ParaView שימושיות

```bash
# המרה לפורמט VTK
blastToVTK -case .

# פתיחת התוצאות
paraview --data=VTK/*.vtk
```

---

## טיפים / Tips

1. ✓ שמור על Co < 0.5 לסימולציות פיצוץ
2. ✓ השתמש ב-AMR לחיסכון במשאבים
3. ✓ בדוק convergence לפני ניתוח תוצאות
4. ✓ וודא תנאי שפה מתאימים
5. ✓ התחל עם רשת גסה ועדן בהדרגה

---

## לינקים שימושיים / Useful Links

- GitHub: https://github.com/synthetik-technologies/blastfoam
- User Guide: [BlastFoam_User_Guide.pdf]
- Workshop: https://youtu.be/OLpRcjR3cW4
- OpenFOAM: https://openfoam.org
