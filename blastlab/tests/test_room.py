"""HD1-3a: a room as obstacle boxes, and what the mesh does to it.

The claim this file pins is the one that decides whether the 0-D to CFD
hand-off is worth anything: **the room the mesh builds is not the room
that was typed in.** `refine.snap_obstacles` moves every obstacle edge
OUTWARD onto a base-cell face so that the Python carve and foam's
`boxToCell` agree cell-for-cell. For a shell that means every wall grows
inward-facing, so the cavity shrinks and the opening shrinks, by up to
one base cell per face.

That is not a rounding detail. It is measured below at several per cent
of the volume - past the 2 % `check_handoff_energy` runs at - which is
exactly why the hand-off has to conserve MASS AND ENERGY and let
pressure fall out of the EOS, rather than carrying a pressure across.

Run:  cd blastlab/tests && python test_room.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.core import room                                # noqa: E402
from blastlab.core import refine                              # noqa: E402

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


def _volume(boxes):
    return sum((b[1] - b[0]) * (b[3] - b[2]) * (b[5] - b[4]) for b in boxes)


def _overlap(a, b):
    for i in range(3):
        if min(a[2 * i + 1], b[2 * i + 1]) - max(a[2 * i], b[2 * i]) > 1e-12:
            continue
        return 0.0
    return 1.0


def main():
    print('ROOM (HD1-3a)')

    # ── 1. the shell is a shell ─────────────────────────────────────────
    print('\n  the shell closes a volume, without overlapping itself')
    o, s, w = (0.0, 0.0, 0.0), (5.0, 4.0, 3.0), 0.25
    boxes = room.room_boxes(o, s, w)
    check('five slabs with no floor - the ground is a reflecting boundary, '
          'not a slab of cells nothing ever happens in',
          len(boxes) == 5, f'{len(boxes)} boxes')
    check('six with one', len(room.room_boxes(o, s, w, floor=True)) == 6)
    # outer minus inner, exactly - which is only true if the slabs tile
    # the shell without overlapping or leaving a gap
    shell = 5.0 * 4.0 * 3.0 - (5.0 - 2 * w) * (4.0 - 2 * w) * (3.0 - w)
    check('the slabs tile the shell exactly: no overlap, no gap',
          abs(_volume(boxes) - shell) < 1e-9,
          f'{_volume(boxes):.6f} vs {shell:.6f} m3')
    check('and none of them overlaps another',
          not any(_overlap(boxes[i], boxes[j])
                  for i in range(len(boxes))
                  for j in range(i + 1, len(boxes))))
    full = room.room_boxes(o, s, w, floor=True)
    shell_f = 5.0 * 4.0 * 3.0 - (5.0 - 2 * w) * (4.0 - 2 * w) * (3.0 - 2 * w)
    check('with a floor too', abs(_volume(full) - shell_f) < 1e-9)

    # ── 2. the vent is a hole, not a patch ──────────────────────────────
    #
    # The whole architecture of HD1-3 rests on this: the opening is a gap
    # between wall boxes, i.e. FLUID. No separate patch, no createPatch,
    # no createBaffles, no new boundary kind, and no time-varying
    # boundary condition - blastFoam computes the blowdown itself.
    print('\n  the vent is a gap between boxes, which is to say fluid')
    vent = ('x_lo', 1.5, 2.5, 0.5, 1.5)          # 1.0 x 1.0 m in the x_lo wall
    vb = room.room_boxes(o, s, w, vent=vent)
    check('the vented wall splits into four pieces around the hole',
          len(vb) == 8, f'{len(vb)} boxes')
    hole = 1.0 * 1.0 * w
    check('and the shell is short by exactly the hole',
          abs(_volume(vb) - (shell - hole)) < 1e-9,
          f'{shell - _volume(vb):.6f} m3 removed, hole is {hole:.6f}')
    check('the four pieces still do not overlap each other',
          not any(_overlap(vb[i], vb[j]) for i in range(len(vb))
                  for j in range(i + 1, len(vb))))
    parts = room.room_parts(o, s, w, vent=vent)
    check('and they are named, which is what lets the cavity be read off '
          'exactly instead of guessed from geometry',
          {'x_lo:below', 'x_lo:above', 'x_lo:side_lo', 'x_lo:side_hi'}
          <= set(parts), str(sorted(parts)))

    # ── 3. WHAT THE MESH DOES TO IT ─────────────────────────────────────
    print('\n  and then the mesh moves every edge outward')
    # deliberately off-grid, which is what a real number typed by a
    # person looks like
    m = room.measure((0.0, 0.0, 0.0), (5.0, 4.0, 3.0), 0.22, 0.1,
                     vent=('x_lo', 1.53, 2.47, 0.44, 1.38))
    check('the cavity is measured AFTER snapping, not from the numbers '
          'that were typed',
          m['volume'] < m['volume_entered'],
          f"{m['volume']:.4f} vs {m['volume_entered']:.4f} m3 "
          f"({m['volume_shift']:+.2%})")
    check('and it loses several per cent - past the 2 % the hand-off '
          'energy check runs at, which is the whole reason the hand-off '
          'conserves mass and energy rather than pressure',
          abs(m['volume_shift']) > 0.02,
          f"{m['volume_shift']:+.2%}")
    check('so the run says so rather than absorbing it',
          any('hand-off' in t for t in m['warnings']), str(m['warnings']))
    check('the opening shrinks too, and by the same mechanism',
          m['vent_area'] < m['vent_area_entered'],
          f"{m['vent_area']:.4f} vs {m['vent_area_entered']:.4f} m2 "
          f"({m['vent_area_shift']:+.2%})")
    check('the snapped opening is a whole number of base cells across, '
          'because every edge of it is now on a cell face',
          all(abs(m['vent_area'] / 0.1 ** 2 - round(m['vent_area'] / 0.01))
              < 1e-6 for _ in (0,)),
          f"{m['vent_cells']} cells")
    check('and the cavity corners are on cell faces as well',
          all(abs(v / 0.1 - round(v / 0.1)) < 1e-9
              for v in m['cavity_lo'] + m['cavity_hi']),
          f"{m['cavity_lo']} to {m['cavity_hi']}")

    # A room already on the grid must not move at all - otherwise the
    # measurement above is measuring the measurer.
    aligned = room.measure((0.0, 0.0, 0.0), (5.0, 4.0, 3.0), 0.2, 0.1,
                           vent=('x_lo', 1.5, 2.5, 0.5, 1.5))
    check('a room that is already on the grid does not move, which is how '
          'we know the shift above is the snapping and not the arithmetic',
          abs(aligned['volume_shift']) < 1e-12
          and abs(aligned['vent_area_shift']) < 1e-12
          and not aligned['moved'],
          f"{aligned['volume']:.6f} m3, {aligned['vent_area']:.4f} m2")
    check('and its measured volume is the one a person would compute',
          abs(aligned['volume'] - (5 - 0.4) * (4 - 0.4) * (3 - 0.2)) < 1e-9,
          f"{aligned['volume']:.6f} m3")

    # ── 4. THE CONSTRAINTS, ENFORCED BEFORE A MESH IS BUILT ─────────────
    #
    # Both of these are cheap to say now and expensive to discover after
    # a four-million-cell mesh has been generated and queued.
    print('\n  what is refused, and refused early')
    thin = room.measure((0.0, 0.0, 0.0), (5.0, 4.0, 3.0), 0.05, 0.1,
                        vent=('x_lo', 1.5, 2.5, 0.5, 1.5))
    check('a wall thinner than one base cell cannot be carved, and the '
          'measurement says so instead of producing a room with no walls',
          not thin['ok'] and any('base cell' in e for e in thin['errors']),
          str(thin['errors']))
    narrow = room.measure((0.0, 0.0, 0.0), (5.0, 4.0, 3.0), 0.2, 0.1,
                          vent=('x_lo', 1.5, 1.7, 0.5, 1.5))
    check('an opening under six cells across cannot carry a jet, and is '
          'refused rather than quietly under-resolved',
          not narrow['ok'] and any('at least' in e for e in narrow['errors']),
          f"{narrow['vent_cells']} cells")
    check('a room whose walls meet in the middle is refused',
          _raises(lambda: room.room_boxes((0, 0, 0), (1.0, 4.0, 3.0), 0.6)))
    check('a vent that reaches the edge of its face cuts the wall through '
          'instead of making a hole, and is refused',
          _raises(lambda: room.room_boxes(
              o, s, w, vent=('x_lo', 0.0, 2.5, 0.5, 1.5))))
    check('a vent with no extent is refused',
          _raises(lambda: room.room_boxes(
              o, s, w, vent=('x_lo', 1.5, 1.5, 0.5, 1.5))))
    check('an unknown face is refused',
          _raises(lambda: room.room_boxes(
              o, s, w, vent=('x_mid', 1.5, 2.5, 0.5, 1.5))))
    check('and a vent in the floor of a room that has no floor is refused '
          'rather than silently dropped',
          _raises(lambda: room.room_boxes(
              o, s, w, vent=('z_lo', 1.5, 2.5, 0.5, 1.5))))
    check('a negative base cell is refused',
          _raises(lambda: room.measure(o, s, w, 0.0)))

    # ── 5. it is ordinary geometry, going down an ordinary path ─────────
    print('\n  nothing here needs a new mesh mechanism')
    check('the boxes are plain (x0,x1,y0,y1,z0,z1) tuples, which is what '
          'case.obstacles already takes',
          all(isinstance(b, tuple) and len(b) == 6 for b in vb))
    again, _moved = refine.snap_obstacles(vb, 0.1, 3)
    check('and they go through the existing snap unchanged in kind - no '
          'new carve, no new patch type, no createBaffles',
          len(again) == len(vb)
          and all(len(b) == 6 for b in again))

    print('\nROOM: ' + ('FAIL - ' + ', '.join(FAIL) if FAIL else 'PASS'))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
