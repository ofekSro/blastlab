"""HD1-3e: quantity-distance as a mechanism with no numbers in it.

The claim this file pins is a negative one, which makes it easy to lose:
**the table is empty and stays empty.** QD factors are safety-siting
numbers out of a standard, a wrong one is invisible - it produces a
plausible distance in metres with no symptom - and nothing here types
one from memory. A report with nothing entered has to SAY so rather than
print a zero a reader could mistake for a clearance.

Run:  cd blastlab/tests && python test_qd.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core import qd                                  # noqa: E402

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    if not ok:
        FAIL.append(name)


def _raises(fn, exc=ValueError):
    try:
        fn()
    except exc:
        return True
    except Exception:
        return False
    return False


def main():
    print('QD (HD1-3e)')

    # ── 1. THE TABLE IS EMPTY, AND SAYS SO ──────────────────────────────
    print('\n  the table ships empty, and an empty table is a sentence')
    check('no criteria ship with this tool',
          qd.CRITERIA == {}, f'{len(qd.CRITERIA)} rows')
    res = qd.compare([], [10.0, 25.0, 50.0])
    check('a comparison with nothing entered returns NO ROWS - not a '
          'zero distance, which a reader could take for a clearance',
          res['rows'] == [] and not res['have_criteria'])
    check('and it says WHY in words, next to where the number would be',
          'no coefficients have been entered' in res['note'],
          res['note'][:60] + '...')
    check('the one-line summary is that sentence and not a number',
          qd.summary_line(res) == qd.NO_CRITERIA)
    check('nothing is reported as governing when nothing was entered',
          res['governing'] is None)

    # ── 2. A ROW WITHOUT A SOURCE IS REFUSED ────────────────────────────
    #
    # A field that can be left blank will be left blank. Making it an
    # error costs one string at entry and removes the whole class of
    # remembered-number mistakes.
    print('\n  every row has to say where it came from')
    good = qd.QDCriterion(name='inhabited building', k_factor=22.2,
                          basis='mass',
                          source='<owner standard, table X, edition Y>',
                          protects='inhabited building')
    check('a criterion with a source is accepted', good.source != '')
    check('one WITHOUT a source is refused - a factor with no provenance '
          'is the exact failure this module exists to prevent',
          _raises(lambda: qd.QDCriterion(name='x', k_factor=22.2)))
    check('and whitespace does not count as a source',
          _raises(lambda: qd.QDCriterion(name='x', k_factor=22.2,
                                         source='   ')))
    try:
        qd.QDCriterion(name='x', k_factor=1.0)
    except ValueError as exc:
        check('the message names what to supply: standard, table, edition',
              'edition' in str(exc) and 'invisible' in str(exc))
    check('a nameless or non-positive row is refused too',
          _raises(lambda: qd.QDCriterion(name=' ', k_factor=1.0, source='s'))
          and _raises(lambda: qd.QDCriterion(name='x', k_factor=0.0,
                                             source='s')))
    check('and an unknown basis is refused rather than assumed to be mass',
          _raises(lambda: qd.QDCriterion(name='x', k_factor=1.0, source='s',
                                         basis='guess')))

    # ── 3. THE ARITHMETIC, ONCE SOMEONE HAS ENTERED A ROW ───────────────
    print('\n  D = K W^(1/3), on numbers the caller supplied')
    check('the cube-root rule is what it says it is',
          abs(qd.qd_distance(good, charge_kg=8.0) - 22.2 * 2.0) < 1e-12,
          f'{qd.qd_distance(good, charge_kg=8.0):.4f} m for 8 kg')
    check('and it scales as the cube root, not linearly',
          abs(qd.qd_distance(good, charge_kg=64.0)
              / qd.qd_distance(good, charge_kg=8.0) - 2.0) < 1e-12)
    check('a mass criterion with no charge is refused',
          _raises(lambda: qd.qd_distance(good)))

    # ── 4. THE FIREBALL BASIS, WHICH 1.3 USUALLY NEEDS ──────────────────
    #
    # For HD 1.3 the governing harm is normally the fireball rather than
    # the blast, so most 1.3 criteria are written against its radius. A
    # cube-root rule applied to a deflagrating material answers a
    # question about a detonation - which is the same mistake as
    # entering the charge as a TNT equivalent.
    print('\n  the fireball basis, and why it will not fall back')
    fb = qd.QDCriterion(name='thermal, personnel', k_factor=3.0,
                        basis='fireball', source='<owner standard>',
                        protects='personnel in the open')
    check('a fireball criterion is a multiple of the fireball radius',
          abs(qd.qd_distance(fb, fireball_radius=12.0) - 36.0) < 1e-12)
    check('and with NO radius it RAISES rather than quietly using '
          'K W^(1/3) - for a deflagrating material that would be '
          'answering a question about a detonation',
          _raises(lambda: qd.qd_distance(fb, charge_kg=100.0)))
    try:
        qd.qd_distance(fb, charge_kg=100.0)
    except ValueError as exc:
        check('and the message says so, rather than just "missing '
              'argument"', 'detonation' in str(exc))

    # ── 5. THE COMPARISON ───────────────────────────────────────────────
    print('\n  criteria against standoffs')
    res = qd.compare([good, fb], [10.0, 25.0, 50.0], charge_kg=8.0,
                     fireball_radius=12.0)
    check('every criterion gets a row carrying its own source, so a '
          'distance is never printed without its provenance',
          len(res['rows']) == 2
          and all(r['source'] for r in res['rows']))
    check('the binding criterion is named rather than left to a reader '
          'scanning the table',
          res['governing'] == 'inhabited building'
          and abs(res['governing_distance_m'] - 44.4) < 1e-9,
          f"{res['governing']} at {res['governing_distance_m']:.1f} m")
    check('each standoff is judged separately, because a site has '
          'several distances that matter and they do not pass together',
          res['rows'][0]['meets'] == [False, False, True],
          f"44.4 m required against {res['standoffs']}")
    check('and the shortfall is given in metres, which is the number '
          'someone has to act on',
          abs(res['rows'][0]['shortfall_m'][0] - 34.4) < 1e-9
          and res['rows'][0]['shortfall_m'][2] == 0.0,
          f"{res['rows'][0]['shortfall_m']}")
    line = qd.summary_line(res)
    check('the summary names the governing row and how short the worst '
          'standoff is', 'inhabited building' in line and 'short' in line,
          line)
    ok_res = qd.compare([fb], [100.0], fireball_radius=12.0)
    check('a site that meets everything says so plainly',
          'meets every criterion' in qd.summary_line(ok_res))

    print('\nQD: ' + ('FAIL - ' + ', '.join(FAIL) if FAIL else 'PASS'))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
