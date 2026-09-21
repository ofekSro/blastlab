> **Academic CFD — blast-wave gas dynamics, Technion.** Published equation-of-state
> data (LLNL Explosives Handbook, Dobratz & Crawford, UCRL-52997) used to simulate a
> pressure field in air for blast-resistant design and explosive-safety siting.
> These are pressure-volume-energy constants for gas that has already reacted; they
> say nothing about how a material is made, mixed, initiated or handled.
> Scope: [../../../docs/SCOPE.md](../../../docs/SCOPE.md)

# פרמטרי JWL לחומרי נפץ נפוצים
# JWL Parameters for Common Explosives
# =====================================

משוואת ה-JWL (Jones-Wilkins-Lee) מתארת את הקשר בין לחץ לנפח ואנרגיה
עבור תוצרי פיצוץ:

P = A(1 - ω/(R₁V))exp(-R₁V) + B(1 - ω/(R₂V))exp(-R₂V) + ωρe

כאשר:
- P = לחץ [Pa]
- V = נפח יחסי (ρ₀/ρ)
- e = אנרגיה פנימית סגולית [J/kg]
- A, B = פרמטרי לחץ [Pa]
- R₁, R₂ = פרמטרים ללא יחידות
- ω = פרמטר Gruneisen

---

## TNT (Trinitrotoluene)

```cpp
equationOfState
{
    A           3.712e11;       // [Pa]
    B           3.23e9;         // [Pa]
    R1          4.15;           // [-]
    R2          0.95;           // [-]
    omega       0.3;            // [-]
    rho0        1630;           // [kg/m³]
    e0          4.29e6;         // [J/kg]
    pRef        1e5;            // [Pa]
}

// מהירות דטונציה
vDet        6930;               // [m/s]
```

### תכונות:
- צפיפות: 1630 kg/m³
- מהירות דטונציה: 6930 m/s
- לחץ CJ: ~21 GPa
- אנרגיית נפץ: 4.29 MJ/kg

---

## C-4 (Composition 4)

```cpp
equationOfState
{
    A           6.0977e11;      // [Pa]
    B           1.295e10;       // [Pa]
    R1          4.5;            // [-]
    R2          1.4;            // [-]
    omega       0.25;           // [-]
    rho0        1601;           // [kg/m³]
    e0          5.56e6;         // [J/kg]
    pRef        1e5;            // [Pa]
}

// מהירות דטונציה
vDet        8193;               // [m/s]
```

### תכונות:
- צפיפות: 1601 kg/m³
- מהירות דטונציה: 8193 m/s
- לחץ CJ: ~28 GPa
- אנרגיית נפץ: 5.56 MJ/kg
- יציב מאוד, נוח לעיבוד

---

## RDX (Cyclotrimethylenetrinitramine)

```cpp
equationOfState
{
    A           7.78e11;        // [Pa]
    B           7.07e9;         // [Pa]
    R1          4.485;          // [-]
    R2          1.068;          // [-]
    omega       0.30;           // [-]
    rho0        1770;           // [kg/m³]
    e0          5.15e6;         // [J/kg]
    pRef        1e5;            // [Pa]
}

// מהירות דטונציה
vDet        8750;               // [m/s]
```

### תכונות:
- צפיפות: 1770 kg/m³
- מהירות דטונציה: 8750 m/s
- לחץ CJ: ~34 GPa
- אנרגיית נפץ: 5.15 MJ/kg

---

## HMX (Cyclotetramethylenetetranitramine)

```cpp
equationOfState
{
    A           7.783e11;       // [Pa]
    B           7.071e9;        // [Pa]
    R1          4.2;            // [-]
    R2          1.0;            // [-]
    omega       0.30;           // [-]
    rho0        1890;           // [kg/m³]
    e0          5.5e6;          // [J/kg]
    pRef        1e5;            // [Pa]
}

// מהירות דטונציה
vDet        9100;               // [m/s]
```

### תכונות:
- צפיפות: 1890 kg/m³
- מהירות דטונציה: 9100 m/s
- לחץ CJ: ~39 GPa
- חומר הנפץ החזק ביותר בשימוש צבאי נרחב

---

## PETN (Pentaerythritol Tetranitrate)

```cpp
equationOfState
{
    A           6.17e11;        // [Pa]
    B           1.69e10;        // [Pa]
    R1          4.4;            // [-]
    R2          1.2;            // [-]
    omega       0.25;           // [-]
    rho0        1770;           // [kg/m³]
    e0          5.81e6;         // [J/kg]
    pRef        1e5;            // [Pa]
}

// מהירות דטונציה
vDet        8400;               // [m/s]
```

### תכונות:
- צפיפות: 1770 kg/m³
- מהירות דטונציה: 8400 m/s
- משמש בפתילי פיצוץ

---

## ANFO (Ammonium Nitrate / Fuel Oil)

```cpp
equationOfState
{
    A           4.95e10;        // [Pa]
    B           1.89e9;         // [Pa]
    R1          3.9;            // [-]
    R2          1.1;            // [-]
    omega       0.35;           // [-]
    rho0        850;            // [kg/m³]
    e0          3.8e6;          // [J/kg]
    pRef        1e5;            // [Pa]
}

// מהירות דטונציה
vDet        4500;               // [m/s]
```

### תכונות:
- צפיפות: 850 kg/m³
- מהירות דטונציה: 4500 m/s
- נפוץ מאוד בכרייה ובנייה
- זול ובטוח יחסית

---

## טבלת השוואה

| חומר | ρ₀ [kg/m³] | vDet [m/s] | PCJ [GPa] | e₀ [MJ/kg] |
|------|-----------|-----------|----------|----------|
| TNT  | 1630      | 6930      | 21       | 4.29     |
| C-4  | 1601      | 8193      | 28       | 5.56     |
| RDX  | 1770      | 8750      | 34       | 5.15     |
| HMX  | 1890      | 9100      | 39       | 5.50     |
| PETN | 1770      | 8400      | 31       | 5.81     |
| ANFO | 850       | 4500      | 5        | 3.80     |

---

## הערות חשובות

1. **TNT Equivalent**: ניתן להשוות חומרי נפץ שונים באמצעות "מקבילת TNT":
   - C-4: ~1.3 TNT equivalent
   - RDX: ~1.6 TNT equivalent
   - HMX: ~1.7 TNT equivalent

2. **Size Effect**: מהירות הדטונציה תלויה בקוטר המטען. הערכים לעיל הם עבור מטענים גדולים.

3. **Confinement**: כליאה משפרת את ביצועי הנפץ.

4. **Temperature**: פרמטרי JWL נמדדים בטמפרטורת החדר. בטמפרטורות קיצוניות ייתכנו שינויים.

---

## מקורות

1. Dobratz, B.M., Crawford, P.C., "LLNL Explosives Handbook", UCRL-52997, 1985
2. Walters, W.P., Zukas, J.A., "Fundamentals of Shaped Charges", Wiley, 1989
3. Cooper, P.W., "Explosives Engineering", Wiley-VCH, 1996
