# דוח סקירה — אפשרויות ה-solver של blastFoam בקוד מול המדריך הרשמי

> **מקורות שנסקרו**
> - `BlastFoam_Basic_Info/BlastFoam_User_Guide.pdf` — *blastFoam Theory and User Guide*, v6.0, Synthetik, 188 עמ' (הטקסט חולץ במלואו ונקרא).
> - הקוד: `blastlab/solvers/foam/` (בעיקר `writer.py`, `dicts.py`, `materials.py`, `backend.py`), `blastlab/core/` (`case.py`, `eos.py`, `profiles.py`, `constants.py`).
> - **אימות מול המקור עצמו** (ולא רק מול המדריך): `/root/blastfoam` ב-WSL — blastFoam 6.2.0 (commit `4e6ee07`), כולל ה-tutorials והספריות הבנויות ב-`/root/OpenFOAM/root-9/platforms/linux64GccDPInt32Opt/lib`.
>
> תאריך: 2026-09-17

---

## 1. תקציר מנהלים

| # | ממצא | חומרה | סטטוס אימות |
|---|------|-------|-------------|
| **B0** | שלב chain שמוזן מ-profile **מאבד את כדור האש כולו** — הלחץ נמחק ל-`pRef` | 🔴🔴 **חוסם** | **אומת בהרצת blastFoam** |
| **B1** | שלב chain שמוזן מ-profile כותב `0/p` שגוי ב-**+33.3%** בכל תא של תוצרי פיצוץ | 🔴 **קריטי** (רדום מאחורי B0) | **אומת מספרית** על fixture אמיתי |
| **B2** | גם אחרי תיקון B1 — פרמטרי ה-JWL שנבחרים הם תמיד של TNT (שגיאה עד 20% ל-C4) | 🟠 גבוה | אומת מספרית |
| **N1** | `reconstructParAll` קיים ופותר בדיוק את המגבלה שהקוד מתעד כבלתי-פתירה | 🟡 בינוני | אומת (הבינארי בנוי) |
| **N2** | חוסר מסת מטען של ~6–15% שמטופל היום בהעלאת רזולוציה יקרה (×4.1 תאים ב-3D) | 🟡 בינוני | מתועד בקוד; פתרון קיים במדריך |
| **N3** | `adjustLocations yes` כברירת מחדל — המדריך מגדיר `no` | 🟢 נמוך | הקוד כבר מתעד את הסיכון |
| **N4** | `libs ("libblastFunctionObject.so")` במדריך — **טעות במדריך**, לא בקוד | ℹ️ מידע | הקוד נכון |

**מה נמצא תקין.** הדיקטים שהקוד מייצר (`controlDict`, `fvSchemes`, `fvSolution`, `phaseProperties`, `setFieldsDict`, `dynamicMeshDict`) הושוו שורה-מול-שורה מול ה-tutorials המקוריים ומול קוד ה-C++ שקורא אותם — והם תואמים. פירוט מלא בסעיף 4.

---

## 2. משטח האפשרויות שהקוד מייצר היום

| תחום | מה הקוד קובע | איפה |
|------|---------------|------|
| Solver | `blastFoam` | `writer._controldict` |
| פאזות | `(expl air)` — `detonating` + `basic` | `writer._phaseproperties` |
| EOS תוצרים | `JWL` (6 חומרים) | `materials.MATERIALS` |
| EOS ריאקטנטים | `Murnaghan` (`K0 0`, `Gamma 0.25`) | `writer._phaseproperties` |
| EOS אוויר | `idealGas`, `gamma 1.4` | קבוע |
| Activation | `linear` \| `none` בלבד | `case.activation` |
| Afterburn | `Miller` \| `none` בלבד | `case.afterburn` |
| Flux scheme | `Kurganov` — **קבוע מודול, לא ניתן לבחירה** | `dicts.FLUX_SCHEME` |
| Time integrator | `RK2SSP` (ללא מספר שלבים) — **קבוע** | `writer._fvschemes` |
| AMR | `adaptiveFvMesh` + `densityGradient` \| `Lohner` | `writer._dynamicmeshdict` |
| Function objects | `impulse`, `fieldMinMax`, `blastProbes`, `writeCellCentres`, `surfaces`, `sets` | `writer._controldict` |
| BC לחץ פתוח | `pressureWaveTransmissive` (ללא `fieldInf`/`lInf`) | `dicts.P_OPEN_BC` |

---

## 3. אי-דיוקים שנמצאו

### 🔴🔴 B0 — שלב profile מאבד את כדור האש: `lambda.expl` לא נכתב לעולם

**זה שורש הבעיה, ו-B1 יושב מתחתיו.**

**המנגנון.** הפאזה `detonating` מערבבת בין המצב הלא-מגיב למגיב לפי משתנה ההתקדמות `λ` (מדריך §5.6.1, משוואה 5.87):

```
x = λ^ℓ · x_reacted + (1 − λ^ℓ) · x_unreacted
```

ב-blastFoam השדה `lambda.<phase>` נבנה עם `READ_IF_PRESENT` וברירת מחדל **0** (`activationModel.C:236-249`). הקוד **לא כותב `0/lambda.expl` לעולם** — אימתתי: `grep` על כל `blastlab/` מוצא את `lambda` רק ב-`fvSchemes` (`writer.py:818, 836`), אף פעם כשדה.

עבור שלב charge רגיל זה **נכון** — המטען באמת לא הגיב ב-t=0, ו-`linear` שורף אותו מנקודות ההצתה. אבל עבור שלב profile הקוד כותב בכוונה `points ()` ריק (`writer.py:937` — ההערה מסבירה שאחרת המטען יתפוצץ פעם שנייה). ו-`linearActivation.C:46` רק מוריד את `tIgn` בלולאה על נקודות ההצתה; עם רשימה ריקה `tIgn = great` בכל תא, ולכן:

> **λ = 0 לנצח → החומר מטופל כנפץ מוצק לא-מגיב עם EOS מסוג Murnaghan.**

ו-Murnaghan עם `K0 0` (דפוס ה-vendor) נותן `p ≈ pRef` **ללא תלות בצפיפות**.

**האימות (הרצה אמיתית של blastFoam 6.2.0 על 10³ תאים).** בניתי מקרה מינימלי מ-`freeField` שמדמה בדיוק מה ששלב profile כותב — `alpha.c4 = 1`, `rho.c4 = 24.6`, `p = 4.43e6`, `points ()` — והרצתי ארבע וריאציות:

| וריאנט | `activationModel` | `0/lambda.c4` | `max(p)` בפועל | |
|---|---|---|---|---|
| **A** | `linear` | לא נכתב | **101,298 Pa** | ← **מה שהקוד עושה היום** |
| **B** | `linear` | `uniform 1` | **4.43e+06** | ✔ נכון |
| **C** | `none` | לא נכתב | **3.669e+07** | ✘ E0 נספר פעמיים (×8.3) |
| **D** | `none` | `uniform 1` | 4.43e+06 | ✔ נכון |

וריאנט A מראה שה-`0/p` שהקוד כותב **נזרק בשלמותו** ומוחלף ב-`pRef` של ה-Murnaghan (101,298 Pa — בדיוק ערך ה-`pRef` בדיקט ה-tutorial).

וריאנט C מסביר למה `activationModel none` **אינו** הפתרון: ללא λ התחלתי, `dλ/dt` קופץ מ-0 ל-1 ו-blastFoam מזריק את `E0` מחדש. בדיקה: `ΔE = E0·ρ/ρ0 = 9.0e9 × 24.6/1601 = 1.38e8 J/m³`, ו-`Δp ≈ ω·ΔE = 0.25 × 1.38e8 = 3.46e7` — תואם להפרש הנמדד `3.67e7 − 4.43e6 = 3.23e7`.

**ההשלכה.** בשלב profile תאי **אוויר** (`alpha.expl = 0`) מאותחלים נכון כגז אידיאלי — כלומר חזית ההלם עוברת תקין. רק תאי ה**תוצרים** קורסים ללחץ סביבה. לכן ריצת chain נראית סבירה (יש גל הלם שמתקדם), אבל כדור האש חסר — מה שפוגע בפאזה החיובית הארוכה, בהלם המשני וב-impulse.

**השערה** (לא הוכחה): זה עשוי להיות המקור לפתולוגיה המתועדת ב-`writer.py:1140-1156` — קריסת הלחץ בכדור האש אל מול אוויר מוכה בלחץ גבוה סביבו יוצרת זרימה פנימה אלימה, שהיא בדיוק חתימת ה-"density runaway" שהצריכה את רצפת `RHO_MIN = 1e-3`. שווה לבדוק אם ה-workaround עדיין נחוץ אחרי התיקון.

---

### 🔴 B1 — hand-off של chain כותב לחץ שגוי ב-33% בכל תוצרי הפיצוץ

> **תלוי ב-B0.** היום השגיאה הזו **רדומה**: blastFoam זורק את `0/p` בתאי תוצרים בלי להסתכל עליו. ברגע שמתקנים את B0 היא הופכת פעילה — ולכן **שני התיקונים חייבים לנחות יחד**.

**הקוד.** `blastlab/solvers/foam/writer.py:1235`:

```python
p, _c = pressure_soundspeed(rho, e, phase, getattr(case, 'eos', 'idealGas'))
```

**הבעיה — ה-EOS נלקח מהאובייקט הלא נכון.** הפונקציה מקבלת את ה-EOS של ה-**case היעד**, לא של ה-**profile המקור**. ועבור case של blastFoam, `case.eos` מאולץ ל-`'idealGas'`:

- `blastlab/ui/case_form.py:215` — `return v['eos'].get() if not foam else 'idealGas'`
- `blastlab/gui/forms.py:436` — שורת ה-EOS מסומנת `scope='native'`
- `blastlab/core/case.py:529-533` — ולידציה שאומרת במפורש *"EOS setting is ignored by blastFoam (material JWL products + ideal-gas air)"*

לכן `core/eos.py:71-73` נופל לענף ה-`else` ומחשב גם עבור תאי **תוצרים** את הלחץ בנוסחת האוויר `p = (γ_air − 1)ρe = 0.4ρe`, במקום `jwl_pressure` עם `ω = 0.30`.

בינתיים שלב-1 של blastFoam מייצא את ה-profile שלו עם `eos='JWL'` (`backend.py:1117`) — כי blastFoam באמת רץ עם JWL. אז **כל שרשרת foam→foam נופלת בזה**.

**האימות (הרצתי את הקוד עצמו על ה-fixture בריפו** — `blastlab/tests/_chain_study/gui_foam/stage1_profile.txt`, שכותרתו `# eos = JWL`, מול `stage2_case.json` שבו `"eos": "idealGas"`, `"solver": "blastfoam"`):

```
profile eos header : JWL   n = 100   product cells: 85

-- product cells only --
max |p_idealGas / p_blastFoam - 1| = 33.3 %
max |p_JWL      / p_blastFoam - 1| =  9.2 %   (השארית בקונטקט תוצרים/אוויר בלבד)

  rho=  24.6048 e=6.0016e+05 | blastFoam p=4.4300e+06  הקוד כותב=5.9067e+06 (+33.3%)
  rho=  24.9312 e=6.0250e+05 | blastFoam p=4.5063e+06  הקוד כותב=6.0084e+06 (+33.3%)
  rho=  24.8264 e=6.0194e+05 | blastFoam p=4.4832e+06  הקוד כותב=5.9776e+06 (+33.3%)
```

**למה זה גרוע במיוחד.** לפי המדריך §5.9, עבור EOS מצורת Mie-Grüneisen (וזה בדיוק JWL) — *"by default the pressure and density are used to initialize the internal energy"*. כלומר blastFoam לוקח את `0/p` השגוי ו**הופך את JWL** כדי לשחזר את האנרגיה:

```
energy blastFoam back-derives from the written p (JWL inversion):
  mean e_recovered / e_true = 1.3333   →  +33.3% אנרגיה מוזרקת לכדור האש
```

היחס `0.4/0.30 = 1.333` הוא בדיוק היחס `(γ_air − 1)/ω_TNT`. זו לא שגיאת קצה — זו הזרקה שיטתית של שליש מהאנרגיה הפנימית לכל 85 תאי התוצרים, בדיוק ברגע המסירה בין השלבים.

**התיקון.** ל-`profile_state` כבר יש את `prof['eos']` (ה-`load_profile` מחזיר אותו). צריך להעביר אותו דרך `init_state` ולהשתמש בו במקום ב-`case.eos`:

```python
# writer.profile_state — להוסיף למילון המוחזר:
return dict(..., eos=str(prof.get('eos', 'idealGas')))

# writer._profile_fields — להשתמש ב-EOS של המקור + בחומר הנכון:
from ...core.eos import pressure_soundspeed, material_jwl
p, _c = pressure_soundspeed(rho, e, phase,
                            st.get('eos', 'idealGas'),
                            material_jwl(spec.material))
```

**חלופה נקייה יותר (ומגובה במדריך).** המדריך §5.9 קובע: *"If the internal energy field is provided in the initial conditions folder, the pressure and temperature fields are calculated directly from the density and internal energy."* כלומר אפשר לכתוב `0/e` ישירות במקום `0/p` — וזה **משמר את האנרגיה בדיוק** ונותן ל-blastFoam לגזור את הלחץ עם ה-JWL שלו. זה מבטל את כל בעיית התאמת ה-EOS מהשורש, כולל את B2.

> הערה על היקף: כששלב המקור הוא native שרץ עם `eos='idealGas'`, ה-`e` שב-profile באמת עקבי עם אוויר אידיאלי, והתנהגות הקוד הנוכחית נכונה-בכוונה (היא משמרת לחץ). הבאג הוא ספציפית שהקוד בוחר לפי ה-EOS של היעד ולא של המקור.

---

### 🟠 B2 — פרמטרי JWL של TNT מוחלים על כל החומרים

חתימת `core/eos.py:49`:

```python
def pressure_soundspeed(rho, e, phase, eos, jwl=JWL_TNT):
```

`writer._profile_fields` קורא לה עם ארבעה ארגומנטים בלבד — כלומר `jwl` נופל לברירת המחדל **TNT**, גם כשהמטען הוא C4 או ANFO. הפונקציה `material_jwl(name)` קיימת בדיוק בשביל זה (`core/eos.py:36`) אבל לא מועברת.

גודל השגיאה על אותו fixture:

```
C4   : max |p(TNT default) / p(C4)   - 1| = 20.0 %
ANFO : max |p(TNT default) / p(ANFO) - 1| = 14.3 %
RDX  : max |p(TNT default) / p(RDX)  - 1| =  0.0 %   (ω זהה)
```

השגיאה נובעת כולה מ-`ω` (TNT 0.30, C4 0.25, ANFO 0.35). זה באג רדום היום כי B1 מסתיר אותו — אבל תיקון של B1 לבדו, בלי להעביר `material_jwl(spec.material)`, פשוט יחליף שגיאה של 33% בשגיאה של 20%.

---

### 🟡 N1 — `reconstructParAll` פותר את מגבלת ה-AMR המקבילי שהקוד מתעד כבלתי-פתירה

`writer.py:141-147` מתעד:

> *"Uniform parallel runs are reconstructed back to the root by the run loop; a parallel AMR run **cannot be** (the mesh changes under reconstructPar), so its times stay per-rank and the ingest concatenates them"*

המדריך §16.9 מתאר כלי שנועד בדיוק לזה:

> *"A modified version of the standard OpenFOAM `reconstructPar` and `reconstructParMesh` has been added to allow for reconstruction of cases that have been **balanced**, something that will cause a fatal error with `reconstructPar`. ... This also allows for **reconstruction of blastFoam AMR refinement histories** which is not typically supported."*

אימתתי שהבינארי בנוי ב-`/root/OpenFOAM/root-9/platforms/linux64GccDPInt32Opt/bin/reconstructParAll`.

ההסתייגות ההוגנת: ה-workaround הקיים (`CaseSpec.decomposed` + שרשור `processor*/`) עובד ומשמעותית זול יותר מ-reconstruct מלא. אז זה לא באג — זו הזדמנות. הערך: כל נתיב ה-post-processing (`blastToVTK`, ParaView, `foamToVTK`) יעבוד ישירות על AMR מקבילי, במקום דרך ה-ingest המיוחד שנכתב בפייתון. שימו לב לשתי ההערות במדריך: דרוש `-constant` אם ה-mesh ב-`processor*/constant` שונה מזה שב-`constant`, ו-`-withZero` אם ה-mesh ב-`0` שונה.

---

### 🟡 N2 — חוסר מסת המטען: פתרון ישיר קיים ב-`setRefinedFields`

`core/constants.py:50-58` מתעד:

> *"blastFoam's `sphericalMassToCell` sets alpha = 1 in the cells whose CENTRES fall inside r_exp, so the mass it actually deposits is the staircase volume: ~0.85 of the request at 5 cells across the radius... 8 cells brings it to ~0.94 **for a 2.6x (2D) / 4.1x (3D) cell-count cost**."*

כלומר משלמים פי-4.1 בתאים ב-3D כדי לצמצם חוסר מסה מ-15% ל-6%, והחוסר עדיין קיים.

המדריך §16.1 מציע field set type שפותר את זה אנליטית — `MassIntegrated`:

> *"**MassIntegrated**: The mass integrated quantity read and is divided by the mass (density times volume) of the given cell set to determine the field value."*

והדוגמה במדריך (עמ' 131) מפורשת:

```
// alpha.air = 10 [kg] / sum(V * rho.air) [kg]
volScalarFieldMassIntegrated alpha.air 10
```

**המשמעות**: במקום `volScalarFieldValue alpha.expl 1` (שמקבע alpha=1 ונותן למדרגות לקבוע את המסה), `volScalarFieldMassIntegrated alpha.expl <mass_kg>` קובע alpha כך שסכום `alpha·ρ·V` על קבוצת התאים **שווה בדיוק למסה המבוקשת**. זה מפצה על עודף/חוסר המדרגות בעצם ההגדרה.

```python
# writer._setfieldsdict — במקום:
'fieldValues': [Raw(f'volScalarFieldValue {alpha}    1')],
# להשתמש ב:
'fieldValues': [Raw(f'volScalarFieldMassIntegrated {alpha}    {fmt(mass)}')],
```

אם זה מאומת, אפשר להוריד את `FOAM_EXP_CELLS` בחזרה מ-8 ל-5 ולחסוך פי-4.1 בתאים ב-3D — עם מסה **מדויקת יותר** מהיום. מומלץ לאמת מול `test_foam_kb_anchor` לפני החלפה, כי הכיול של ה-afterburn (`Q0=2.0e6`, `a=3e-4`) נעשה עם החוסר הנוכחי בפנים ויצטרך כיול מחדש.

---

### 🟢 N3 — `adjustLocations` ו-`refineProbes`

המדריך §15.1 קובע `adjustLocations` — *"Can probes be moved into the mesh (**default no**)"*. הקוד קובע `'yes'` (`writer.py:110, 799`), וההערה בקוד כבר מזהה את הסיכון: על base mesh גס הבדיקה מוצמדת למרכז תא רחוק, ותחת AMR התא מתעדן מתחתיה.

שני דברים כדאי לדעת:
1. זה **תואם ל-tutorials** (`axisymmetricCharge`, `building3DWorkshop` שניהם כותבים `adjustLocations yes`), אז זו החלטה סבירה.
2. המדריך §15.1 מוסיף שהקפיצה תחת AMR כבר מטופלת: *"This can be eliminated by allowing refinement of probes in `dynamicMeshDict` (`refineProbes`) (**this is the default option**)."* — אימתתי ב-`errorEstimator.C:139`: `refineProbes_(dict.lookupOrDefault("refineProbes", true))`. כלומר הקוד כבר מקבל את ההתנהגות הנכונה מברירת המחדל, ואין צורך בפעולה.

---

### ℹ️ N4 — שתי טעויות במדריך עצמו (הקוד נכון)

1. **שם הספרייה.** המדריך §15 (עמ' 122) כותב `libs ("libblastFunctionObject.so")` — ביחיד. הספרייה הבנויה בפועל היא `libblastFunctionObjects.so` — **ברבים**. הקוד (`writer.py:700, 707`) משתמש בצורה הנכונה.
2. **`MillerCoeffs`.** המדריך (עמ' 70) מציג את פרמטרי ה-Miller בתת-דיקט `MillerCoeffs { ... }`, בעוד הקוד כותב אותם שטוחים בתוך דיקט הפאזה. בדקתי את `newAfterburnModel.C`:
   ```cpp
   const dictionary& modelDict = dict.optionalSubDict(afterburnModelType + "Coeffs");
   ```
   `optionalSubDict` מחזיר את תת-הדיקט אם קיים ואחרת את הדיקט עצמו — **שתי הצורות תקפות**. ההערה בקוד (`materials.py`) נכונה.

---

## 4. מה נבדק ונמצא תקין

הושווה שורה-מול-שורה מול `tutorials/blastFoam/freeField` ומול קוד ה-C++ שקורא כל מפתח:

| פריט | ממצא |
|------|------|
| `fvSchemes` (fluxScheme, ddt, grad, div, laplacian, interpolation, snGrad) | **זהה ל-tutorial**, כולל `reconstruct(...)` |
| `fvSolution` | **זהה ל-tutorial** (`"(rho\|rhoU\|rhoE\|alpha\|.*)"` → `diagonal`) |
| `controlDict` בסיסי | תואם; `timePrecision 8` במקום 12 — בחירה מכוונת ומתועדת ב-`dicts.tfmt` |
| מבנה `phaseProperties` | תואם במדויק (reactants/products/activationModel/initiation/residual*) |
| `E0 = rho0 · e0` | ✔ אומת מול `freeField`: C4 → 1601 × 5.56e6 = 8.90e9 ≈ `E0 9.0e9` |
| `Murnaghan` עם `K0 0` | ✔ **זהו דפוס ה-vendor** (`freeField`, `mappedBuilding3D`, `blastFSIFoam/flap`). `Murnaghan.C` מטפל בזה: `kappa_ = 1/max(K0_, small)`, ו-`n` נופל ל-`K0Prime` ברירת מחדל `1+small` — בדיוק כדי למנוע חלוקה באפס |
| `activationModel none` + `initiation { E0 }` בלבד | ✔ תואם ל-`burstingWindow_workshop` |
| `blastProbes` (ללא `libs`, `adjustLocations`, `append`) | ✔ תואם ל-`axisymmetricCharge` ו-`building3DWorkshop` |
| `pMax` כשם שדה הפלט של `fieldMinMax` | ✔ אומת ב-`fieldMinMax.C:92` — `minMaxName_ = "Max"`, `computedName()` = `"p"+"Max"` |
| `maxCells` ב-`dynamicMeshDict` | ✔ נקרא בפועל (`fvMeshRefiner.C:517`) — **למרות שאינו מופיע בטבלת המדריך §11** |
| `nBufferLayers` (ולא `nBufferLayer`) | ✔ `fvMeshRefiner.C:532` קורא `nBufferLayers` |
| `field` ל-Lohner (המדריך מציג `deltaField`) | ✔ `Lohner.C:55` — `lookupBackwardsCompatible({"deltaField", "field"})` |
| `maxRefinement` ברמה העליונה של `setFieldsDict` | ✔ `setRefinedFields.C:858`; אזורים ללא `level` יורשים אותו (`:877`) |
| `loadBalance { balance }` כתת-דיקט | ✔ תואם לדוגמה §11.3 |
| `addEmptyPatch internal internal` לפני `decomposePar` | ✔ נדרש בפועל (`fvMeshBalance.C:112`), תואם §11.2 |
| `pressureWaveTransmissive` + `value $internalField` | ✔ תואם ל-`axisymmetricCharge`/`delayedDetonation`/`twoChargeDetonation` |
| `T_AMB` עקבי | ✔ 101325/(1.225·0.4·718) = 288.0 K; ו-`(γ−1)Cv = 287.2` תואם ל-`8314/28.97 = 287.0` |
| פרמטרי JWL (TNT, C4) | ✔ TNT תואם ל-Dobratz; C4 תואם **בדיוק** ל-`freeField` |

**הערה על סדר גודל שני** בטבלת החומרים: `RDX` ו-`HMX` ב-`materials.py` חולקים `A`/`B` כמעט זהים (7.78e11/7.07e9 מול 7.783e11/7.071e9) — בעוד ש-`e0` שונה מהותית (5.15 מול 5.50 MJ/kg). זה מגיע מ-`jwl_parameters.md` ולא מ-tutorial כלשהו. שווה אימות מול Dobratz לפני ציטוט תוצאות RDX; ערכי ה-`e0` הנפוצים ל-RDX ב-ρ=1.77 נוטים גבוה יותר (~5.9 MJ/kg).

---

## 5. פיצ'רים מומלצים מהמדריך

מדורג לפי יחס ערך/מאמץ.

### 5.1 — ערך גבוה, מאמץ נמוך

#### (א) `timeOfArrival` — מפת זמן הגעה (§15.12)

```
timeOfArrival { type timeOfArrival; libs ("libblastFunctionObjects.so");
                writeControl writeTime; pName p; }
```

זמן הגעת ההלם הוא אחד משלושת הפלטים הסטנדרטיים בהנדסת פיצוץ (לצד peak pressure ו-impulse), והריפו כבר מייצר את שני האחרים (`pMax`, `impulse`). זו שורה אחת בדיקט ושדה נוסף בכל time dir — ומשלימה את השלישייה.

#### (ב) `overpressure` עם `store yes` (§15.10)

```
overpressure { type overpressure; writeControl writeTime; pRef 101325; store yes; }
```

שני רווחים: (1) `blastProbes` יכול לדגום `overpressure` ישירות במקום `p` — כך ש-`gauge_summary` מקבל את הכמות הנכונה מהמקור; (2) המדריך §16.5 מציין ש-`calculateImpulse` מזהה קובץ overpressure אוטומטית ואז `pRef` מתאפס. ה-tutorials (`burstingWindow_workshop`) כבר עושים `fields (overpressure impulse)` ב-probes.

#### (ג) `conservedQuantities` — בקרת שפיות אוטומטית (§15.4)

```
conserved { type conservedQuantities; fields (rho rhoE); }
```

מדפיס ללוג מסה ואנרגיה כוללות — התחלתי, נוכחי, הפרש מוחלט ויחסי. בהינתן ש-B1 הוא **בדיוק** שגיאת אי-שימור אנרגיה בהעברה בין שלבים, ה-FO הזה היה תופס אותו אוטומטית בכל הרצת chain. שווה לחבר את הפלט ל-`postmortem.py` כבדיקה אוטומטית לכל ריצה.

#### (ד) `writeTimeList` — כתיבה בזמן מדויק (§15.3)

```
writeTimes { type writeTimeList; times (1.234e-4); }
```

היום נקודת המסירה בשרשרת מוצמדת ל-`tfmt` ונשענת על `adjustableRunTime` שיפגע בה. ה-FO הזה מבטיח write בדיוק בזמן המבוקש — פותר מחלקה שלמה של בעיות `startFrom latestTime` (T62) ישירות.

#### (ה) `fieldInf`/`lInf` על גבול פתוח (§ מומלץ; `pressureWaveTransmissive`)

```
type pressureWaveTransmissive; value $internalField;
fieldInf 101325; lInf <גודל תחום>;
```

אימתתי ב-`pressureWaveTransmissiveFvPatchField.C:134` שהשדות אופציונליים ומופעלים כש-`lInf > small`. בלעדיהם ה-BC הוא advective טהור ואינו נרגע חזרה ללחץ הסביבה — מקור לסחיפה איטית והחזרות חלשות בגבול, בדיוק במה שמדידות impulse רגישות לו. ה-tutorials אמנם לא משתמשים בזה, אז ראוי לבדוק השפעה על ה-KB anchor לפני הפעלה.

---

### 5.2 — ערך גבוה, מאמץ בינוני

#### (ו) `rotateFields` — להחליף את ה-remap בפייתון (§16.7)

זו ההמלצה המשמעותית ביותר. הריפו מממש היום מיפוי 1D→2D/3D בפייתון (`profiles.remap_profile_1d_to_3d`) — עם הפתולוגיה המתועדת ב-`writer.py:1140-1156`: אינטרפולציה של גדלים **נשמרים** מייצרת תאים עם `rho ~ 1.6e-6` שנושאים `|U|` עד 3.6e4 m/s ו-`T` עד 8.3e6 K, וגרמו ל-SIGFPE ב-**~6% מהרצות ה-chain**. הפתרון הנוכחי הוא רצפת צפיפות `RHO_MIN = 1e-3`.

המדריך §16.7 מתאר כלי vendor לאותה מטרה בדיוק:

> *"The `rotateFields` utility can be used to map the fields of a 1-D or 2-D solution to that of a 2-D or 3-D solution... The rotation of vector and tensor fields are mapped **using the local rotation tensor** to ensure that the correct radial components are used. **Iterative refinement** can be used to iteratively rotate fields and refine the mesh using the refinement criteria found in `dynamicMeshDict`, allowing for easier initialization when using AMR."*

יתרונות: (1) פועל על **שדות** ולא על גדלים נשמרים מאונטרפולטים — מבטל את מקור הפתולוגיה; (2) סיבוב וקטורים נכון מתמטית; (3) `-refine` פותר את המגבלה שהקוד אוכף היום (`case.py:521-525` — "A profile-initialised blastFoam stage cannot use refinement zones yet"); (4) **מבטל את B1 לחלוטין** — אין המרת EOS בפייתון באמצע.

הסתייגות הוגנת: המדריך מזהיר ש-*"The mapping is not conservative currently so only the nearest cell value will be used"* — כלומר משמר מצב מקומי אך לא אינטגרלים גלובליים. לכן זה שינוי שדורש validation מול ה-baselines הקיימים, לא החלפה עיוורת. ה-flag `-extend` ו-`-maxR` רלוונטיים לקצוות.

#### (ז) `errorEstimator multicomponent` ל-AMR (§11.1.7)

היום בוחרים estimator יחיד. עידון blast נשלט בו-זמנית על ידי חזית ההלם (שיפוע לחץ) **ו**ממשק תוצרים/אוויר (`alpha`). המדריך (עמ' 111) נותן את הדפוס המדויק:

```
errorEstimator multicomponent;
errorEstimators
(
    density  { errorEstimator densityGradient; lowerRefineLevel 0.01; unrefineLevel 0.01; maxRefinement 2; }
    pressure { errorEstimator scaledDelta; deltaField p; minValue 1e3;
               lowerRefineLevel 0.1; unrefineLevel 0.01; maxRefinement 2; }
);
```

שימו לב שכל estimator נושא `maxRefinement` משלו — כלומר אפשר לעדן את הממשק פחות מאשר את החזית ולחסוך תאים.

#### (ח) `beginUnrefine` — המדריך ממליץ עליו **במפורש** לחומרי נפץ (§11)

> *"Because the detonation of explosives may not occur when the simulation starts, the option to begin unrefinement at a designated time (`beginUnrefine`) has been added. This allows the mesh to remain refined in specific regions even though the error is initially small."*

זה בדיוק התרחיש שהקוד מטפל בו היום ב-workaround בצד הפייתון (`backup_radius` ב-`_setfieldsdict`, שמנפח את אזור העידון ל-`0.9 · dx_base` כדי "לתפוס" את התא שמכיל את המרכז תחת AMR). `beginUnrefine` הוא הפתרון שה-vendor התכוון אליו. מפתחות נוספים באותה משפחה שלא בשימוש: `beginRefine`, `endRefine`, `unrefineInterval`, `upperRefineLevel`, `upperUnrefineLevel`, `minDx`, `protectedPatches`, `nUnrefinementBufferLayers`.

#### (ט) `loadBalance` מלא (§11.3)

הקוד כותב `loadBalance { balance yes; }` בלבד. המדריך מוסיף `balanceInterval` (כל כמה צעדי refine לאזן), `allowableImbalance` (0.2), ו-`method scotch`. ההערה ב-`backend.py` מתעדת חוסר איזון שנמדד 1:64 בין rank עמוס לפנוי — `allowableImbalance` הוא בדיוק הידית לזה.

---

### 5.3 — הרחבות מודל (ערך מחקרי)

#### (י) `DoanNickel` EOS לאוויר (§5.2.2.10)

הקוד מקבע `gamma 1.4` לאוויר. המדריך: *"The Doan-Nickel EOS includes changes in the composition of air at high temperatures and the changing specific heat ratio due to **dissociation of molecules**."* בשדה הקרוב טמפרטורות ההלם חוצות את סף הדיסוציאציה של O₂ ו-N₂, ו-γ קבוע מעריך שם את הלחץ ביתר. זה רלוונטי ישירות ל-anchor של Kingery-Bulmash ב-`Z` קטן. כל המקדמים hard-coded (הם מיועדים לאוויר בלבד), אז זה שינוי של מילה אחת:

```
equationOfState DoanNickel;
```

מגבלה מהמדריך: *"can currently only be used with inviscid fluids and a constant specific heat at constant volume (eConst)"* — שני התנאים כבר מתקיימים בקוד (`mu 0`, `eConst`).

#### (יא) מודלי activation נוספים (§5.6.1)

הקוד תומך ב-`linear`/`none` בלבד. זמינים גם:
- **`programmedIgnition`** (§5.6.1.3) — מודל Giroux, עם `burnModel` מסוג `beta`/`programmed`/`programmedBeta`. כולל שחרור אנרגיה תלוי-דחיסה, ו-`λ` שמתקדם לפי `vDet/(1.5·dx)` המקומי במקום מדרגה חדה. **עדיף מובהק על `linear` לשדה קרוב**, כי `linear` מפעיל תא במלואו ברגע ש-`|x − x_det| < v_det·t`.
- **`pressureBased`** (§5.6.1.4) — מודל Lee-Tarver ignition-and-growth מלא, לתרחישי shock-to-detonation.
- **`ArrheniusRate`** (§5.6.1.5) — אך המדריך מסמן במפורש *"still in development and has not been validated"*, אז לא מומלץ.

#### (יב) `initiation`: `delays`, `radii`, `useCOM` (§5.6.1)

הקוד כותב `points` + `vDet` בלבד. המדריך מוסיף:
- **`delays`** — השהיה פר-נקודת דטונציה. יש tutorial ייעודי (`delayedDetonation`). זה פותח מטענים רב-שלביים ו-timing של מטענים מרובים — והקוד **כבר תומך** ברשימת `det_points`, אז זו הרחבה טבעית.
- **`radii`** / `radius` — רדיוס הצתה סביב כל נקודה. כיום *"If no radii are provided, **only the cell containing the point** will be activated"* — כלומר ההצתה תלוית-רזולוציה.
- **`useCOM`** — הצתה ממרכז המסה של המטען (בשימוש ב-`building3D`, `building3DWorkshop`).
- **`lambdaPow`** — מעריך המיזוג בין המצב הלא-מגיב למגיב.

#### (יג) מודלי afterburn פשוטים (§5.6.2.2–3)

`materials.py` מתעד בכנות ש-Miller כויל רק ל-TNT, וששאר החומרים הם *"physically ordered estimates"*. למקרים שבהם רוצים תוספת אנרגיה **דטרמיניסטית** בלי כיול:
- **`constant`** — `Qdot` [J/kg/s].
- **`linear`** — `Q0`, `tStart`, `tEnd`; משחרר `Q0/Δt` בחלון זמן נתון.

שניהם מאפשרים לבודד את השפעת האנרגיה מהשפעת קינטיקת המודל. בנוסף, ל-Miller עצמו יש מפתחות שלא בשימוש: `pScale`, `pUnits`, `tUnits` (אימתתי ב-`MillerAfterburn.C:96-103` — הם מקנים המרת יחידות אוטומטית, שימושי כשמצטטים מקדמים מספרות שעובדת ב-MPa/μs).

#### (יד) Schlieren / shadowgraph לאנימציות (§15.6–15.7)

```
schlieren   { type grad;      field rho; }
shadowgraph { type laplacian; field rho; }
```

הריפו מייצר אנימציות ותמונות (`output/animation.py`, `blast_2d_animation.gif`). Schlieren היא ההדמיה הסטנדרטית לגלי הלם והופכת מבנים חלשים (גלי מגע, החזרות משניות) לנראים — שדה נוסף אחד ב-time dir.

---

### 5.4 — יכולות שלא נוגעים בהן כלל

| יכולת | סעיף | רלוונטיות |
|-------|------|-----------|
| `mergeProbes` | §16.4 | מיזוג קבצי probe מריצות שהופסקו — נוגע ישירות למסלול ה-resume |
| `calculateImpulse` | §16.5 | impulse מקובץ probe — מה ש-`gauge_summary.py` עושה בפייתון |
| `blastToVTK` | §16.2 | VTK של patch בלבד + `.vtk.series` — קל בהרבה מ-VTK מלא לצופה ה-3D |
| `initializeAtmosphere` | §16.6 | אתמוספרה הידרוסטטית/טבלאית — למרחקים גדולים / גובה |
| Burst patches | §7 | חלונות/פאנלים מתנפצים (`pressure`, `impulse`, `pressureAndImpulse`, `field`) |
| Flux schemes אחרים | §10.1 | `HLLC` חד יותר בגלי מגע (ממשק תוצרים/אוויר) מאשר `Kurganov` |
| `RK3SSP` / מספר שלבים | §10.3 | `timeIntegrator RK2SSP 3` — שלושה שלבים ליציבות נוספת |
| `limitT no` | §5.1 | ביטול הגבלת הטמפרטורה (המדריך מזהיר: "Caution should be used") |
| `blastEulerFoam` | §19.2 | מטענים עם מעטפת/אבק |
| `blastFSIFoam` | §19.3 | עיוות מבנה תחת עומס |

---

## 6. סדר פעולות מוצע

| עדיפות | פעולה | מאמץ |
|--------|-------|------|
| **P0** | תיקון **B0 + B1 + B2 בקומיט אחד** — ראו סעיף 7 | קטן |
| **P0** | regression test: profile עם `eos=JWL` → לוודא ש-`0/p` תואם את עמודת ה-`p` השמורה ב-profile, **ו**ש-`0/lambda.expl` קיים | קטן |
| **P1** | `conservedQuantities` בכל ריצה + בדיקה ב-`postmortem` — היה תופס את B1 | קטן |
| **P1** | `timeOfArrival` + `overpressure store yes` | קטן |
| **P2** | POC ל-`volScalarFieldMassIntegrated` (N2) ומדידה מול KB anchor; אם עובד — הורדת `FOAM_EXP_CELLS` ל-5 | בינוני |
| **P2** | `beginUnrefine` + `allowableImbalance` ב-`dynamicMeshDict` | קטן |
| **P3** | POC ל-`rotateFields` כתחליף ל-remap בפייתון | גדול |
| **P3** | חשיפת `activation programmedIgnition` ו-`initiation delays` | בינוני |
| **P4** | `reconstructParAll` למסלול ה-AMR המקבילי | בינוני |

---

## 7. התיקון המומלץ ל-B0 + B1 + B2

שלושת הממצאים נוגעים באותה פונקציה ו**חייבים לנחות יחד**: תיקון B0 לבדו הופך את השגיאה של 33% מרדומה לפעילה, ותיקון B1 לבדו לא עושה דבר כי הערך נזרק בכל מקרה.

### שלב 1 — לכתוב `0/lambda.expl` (שורש B0)

ב-`writer._profile_fields`, להוסיף שדה שביעי למילון `fields`:

```python
fields = {
    '0/p':   ('p', 'p', _nonuniform(_cell_order(p, spec)), False),
    '0/T':   ('T', 'T', _nonuniform(_cell_order(T, spec)), False),
    '0/U':   ('U', 'U', _nonuniform(U, vector=True), True),
    f'0/alpha.{PHASE}':  (...),
    f'0/rho.{PHASE}':    (...),
    '0/rho.air':         (...),
    # B0: the profile's explosive is ALREADY reacted - it arrives as
    # expanded JWL products from the previous stage. Without this field
    # blastFoam defaults lambda to 0 (activationModel.C READ_IF_PRESENT),
    # blends the phase back to the UNREACTED Murnaghan reactants, and
    # that EOS returns pRef regardless of density - the whole fireball
    # is silently reset to ambient. Measured: 4.43 MPa -> 101,298 Pa.
    f'0/lambda.{PHASE}': (f'lambda.{PHASE}', 'alpha',
                          Raw(f'uniform 1'), False),
}
```

הערות מימוש:
- **מפתח השדה `'alpha'`** נבחר בכוונה: `_DIMS['alpha']` הוא `[0 0 0 0 0 0 0]` (λ חסר ממדים), ו-`_bc_entry(fld='alpha', ...)` נותן `zeroGradient` בגבולות פתוחים ובקירות ו-`wedge`/`empty` נכון. אין צורך בקוד BC חדש.
- **`uniform 1` ולא מסכת הפאזה**: בשלב profile אין חומר לא-מגיב בשום מקום בתחום, ובתאי אוויר `alpha.expl = 0` כך ש-λ שם חסר משמעות. מסכת הפאזה (`_nonuniform(_cell_order(phase.astype(float), spec))`) גם תקינה — פשוט מפורטת יותר ללא תועלת.
- **להשאיר `activationModel linear` עם `points ()`**. אל תעברו ל-`none`: וריאנט C בטבלה למעלה מראה שהוא מזריק את `E0` מחדש ומכפיל את הלחץ פי 8.3. עם λ התחלתי = 1, `linearActivation` הוא no-op (`lambda_.ref() = max(..., lambda_())` מונוטוני, ו-`tIgn = great`).
- להוסיף את `0/lambda.expl` ל-`spec.deferred` — הוא nonuniform-over-final-cells בדיוק כמו שאר שדות ה-profile, ולכן חייב להיכתב אחרי שלבי ה-mesh (T62). זה קורה אוטומטית כי `render_case` עושה `spec.deferred = tuple(prof)`.

### שלב 2 — לתקן את בחירת ה-EOS (B1 + B2)

`profile_state` כבר מחזיק את `prof['eos']`; צריך רק להעביר אותו הלאה:

```python
# writer.profile_state - להוסיף למילון המוחזר:
return dict(..., eos=str(prof.get('eos', 'idealGas')))

# writer._profile_fields - להשתמש ב-EOS של המקור ובחומר הנכון:
from ...core.eos import pressure_soundspeed, material_jwl
p, _c = pressure_soundspeed(rho, e, phase,
                            st.get('eos', 'idealGas'),
                            material_jwl(spec.material))
```

שתי טעויות מתוקנות בשתי שורות: ה-EOS נלקח מה-**profile** ולא מה-case היעד (B1), ופרמטרי ה-JWL הם של החומר בפועל ולא של TNT כברירת מחדל (B2).

### שלב 3 — בדיקות שמונעות חזרה

1. **Golden test** על `_profile_fields`: לוודא ש-`0/lambda.expl` קיים, ושעבור fixture עם `# eos = JWL` ערכי `0/p` תואמים לעמודת ה-`p` שב-profile (סטייה < 1%). זו בדיקה טהורה על טקסט, בלי WSL — מתאימה ל-`test_foam_writer.py`.
2. **`conservedQuantities`** בכל ריצה (סעיף 5.1ג): מדפיס מסה ואנרגיה כוללות מול ההתחלה. שני הבאגים הם אי-שימור אנרגיה בהעברה, וה-FO הזה היה תופס את שניהם.
3. **ולידציה ב-`case.py`**: אם `init_mode != 'charge'` ולא נכתב `lambda.<phase>` — לזרוק שגיאה ולא להריץ.

### מה לעשות עם תוצאות קיימות

כל תוצאות ה-chain של foam→foam שנשמרו (NIGHT2/NIGHT3, HEAVY_RUNS) רצו עם A. חזית ההלם שם סבירה כי היא נישאת בתאי אוויר, אבל כל מה שתלוי בכדור האש — impulse, משך הפאזה החיובית, הלם משני, התנהגות מאוחרת — אינו תקף. כדאי לסמן אותם ככאלה ולהריץ מחדש נקודת ייחוס אחת אחרי התיקון.

---

## נספח — איך אומת

1. **חילוץ המדריך**: `pypdf` → 188 עמודים → `manual.txt` (205 KB). נקראו במלואם הסעיפים 5 (thermo/EOS/detonating/activation/afterburn), 6–9, 10 (flux/time integration), 11 (AMR), 12, 15 (function objects), 16 (utilities), 17–19.
2. **הקוד**: `writer.py` (1378 שורות, במלואו), `dicts.py`, `materials.py`, `constants.py`, `eos.py`, `profiles.py` (remap), `case.py` (ולידציה), `backend.py` (mesh stages, ייצוא profile).
3. **מקור blastFoam ב-WSL** (`/root/blastfoam`, 6.2.0 / `4e6ee07`) — אומתו ישירות בקוד ה-C++:
   `newAfterburnModel.C` (`optionalSubDict`), `MillerAfterburn.C` (מפתחות + `pUnits`/`tUnits`), `Murnaghan.C` (טיפול ב-`K0 0`), `fvMeshRefiner.C` (`maxCells`, `nBufferLayers`, `begin*`/`end*`), `errorEstimator.C` (`refineProbes`, `lowerRefineLevel`), `Lohner.C` (`deltaField`/`field`), `fieldMinMax.C` + `fieldMinMaxTemplates.C` (שם שדה הפלט), `setRefinedFields.C` (`maxRefinement` מול `level`), `pressureWaveTransmissiveFvPatchField.C` (`fieldInf`/`lInf`).
4. **Tutorials** — `freeField` (phaseProperties + כל דיקטי system), `axisymmetricCharge`, `twoChargeDetonation`, `building3DWorkshop`, `burstingWindow_workshop`, `delayedDetonation`, `mappedBuilding3D`.
5. **בינאריים בנויים** — אומת ש-`reconstructParAll`, `rotateFields`, `blastToVTK`, `createTimeSeries`, `mergeProbes`, `calculateImpulse`, `initializeAtmosphere`, `blastEquation` כולם קיימים, וש-`libblastFunctionObjects.so` הוא השם הנכון.
6. **אימות מספרי של B1/B2** — הרצת `blastlab.core.eos.pressure_soundspeed` ו-`material_jwl` על `blastlab/tests/_chain_study/gui_foam/stage1_profile.txt` (100 נקודות, 85 מהן תוצרים), והשוואה מול עמודת ה-`p` שכתב blastFoam עצמו.
7. **אימות של B0** — בשני שלבים:
   - *רמת קוד*: `writer.render_case` על `_chain_study/gui_foam/stage2_case.json` האמיתי → אישר `points ();` ריק ואפס שדות `lambda` ברשימת הקבצים הנכתבים.
   - *רמת ריצה*: **הרצה אמיתית של blastFoam 6.2.0** על מקרה בן 10³ תאים שנגזר מ-`freeField`, בארבע וריאציות (`activationModel` × `0/lambda`), כמתואר בטבלה בסעיף 3/B0. זה מה שהפך את הממצא מהשערה לעובדה מדודה.
