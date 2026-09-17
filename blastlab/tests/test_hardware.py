"""N21: the hardware model - machine identity, cache staleness, the host
RAM probe and the native-solver cell caps.

No WSL and no assumptions about THIS machine: everything under test is
either a pure function fed explicit numbers, or a module global that the
test saves and restores. The one live call is the ctypes host probe,
which is checked only for plausibility (Windows) or for degrading
cleanly (anywhere else).

Run:  cd blastlab/tests && python test_hardware.py
"""

import os
import sys
import tempfile
import time

os.environ.setdefault('MPLBACKEND', 'Agg')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

# a private settings file: the persistence checks must never read or
# write the user's own (set before anything imports blastlab.gui)
_TMP = tempfile.mkdtemp(prefix='blastlab_hardware_')
os.environ['BLASTLAB_SETTINGS'] = os.path.join(_TMP, 'settings.json')

from blastlab.core import hardware                             # noqa: E402
from blastlab.core.constants import (CELLS_2D_MAX,             # noqa: E402
                                     CELLS_2D_WARN,
                                     CELLS_REFUSE, CELLS_WARN,
                                     NATIVE_CELLS_FLOOR)

FAIL = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail and not ok else ''))
    if not ok:
        FAIL.append(name)


def meminfo_checks():
    print("\nN21: /proc/meminfo parsing")
    MI = 'MemTotal:       %d kB\nMemFree:  99 kB'
    check('meminfo: MemTotal in kB',
          hardware.parse_meminfo_kb(MI % 65_290_840) == 65_290_840)
    check('meminfo: the line is matched by name, not by position',
          hardware.parse_meminfo_kb('Foo: 1\nMemTotal: 42 kB') == 42)
    check('meminfo: unreadable -> None, never a number',
          hardware.parse_meminfo_kb('') is None
          and hardware.parse_meminfo_kb(None) is None
          and hardware.parse_meminfo_kb('MemTotal: x kB') is None
          and hardware.parse_meminfo_kb('MemTotal:') is None)


def fingerprint_checks():
    print("\nN21: machine identity")
    fp = hardware.fingerprint
    base = fp('WORKPC', 28, 128, 'Ubuntu')
    check('fingerprint: stable for the same machine',
          base == fp('WORKPC', 28, 128, 'Ubuntu'))
    check('fingerprint: case and whitespace do not matter',
          base == fp('  workpc ', 28, 128, ' ubuntu'))
    check('fingerprint: a different host name is a different machine',
          base != fp('HOMEPC', 28, 128, 'Ubuntu'))
    check('fingerprint: a different core count is a different machine',
          base != fp('WORKPC', 12, 128, 'Ubuntu'))
    check('fingerprint: a different host RAM is a different machine',
          base != fp('WORKPC', 28, 8, 'Ubuntu'))
    check('fingerprint: a different distro is a different machine',
          base != fp('WORKPC', 28, 128, 'Ubuntu-22.04'))
    check('fingerprint: missing pieces still yield a stable value',
          fp(None, None, None, None) == fp('', 0, 0, ''))
    check('fingerprint: short enough to sit in a settings file',
          len(base) == 16)


def cache_checks():
    print("\nN21: is a persisted measurement still usable?")
    ok = hardware.cache_is_valid
    now = 1_700_000_000.0
    fresh = time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(now - 3600))
    old = time.strftime('%Y-%m-%dT%H:%M:%S',
                        time.localtime(now - 30 * 86400))
    future = time.strftime('%Y-%m-%dT%H:%M:%S',
                           time.localtime(now + 10 * 86400))
    check('cache: same machine, fresh stamp -> usable',
          ok('abc', fresh, 'abc', now) is True)
    check('cache: another machine -> rejected',
          ok('abc', fresh, 'def', now) is False)
    check('cache: no saved fingerprint (a pre-N21 settings file) '
          '-> rejected',
          ok('', fresh, 'abc', now) is False
          and ok(None, fresh, 'abc', now) is False)
    check('cache: expired -> rejected',
          ok('abc', old, 'abc', now) is False)
    check('cache: a .wslconfig edit is caught by the TTL, so the TTL '
          'has to be finite and short-ish',
          hardware.HW_CACHE_TTL_S <= 14 * 86400)
    check('cache: unparseable or missing stamp -> rejected',
          ok('abc', '', 'abc', now) is False
          and ok('abc', 'not-a-date', 'abc', now) is False
          and ok('abc', None, 'abc', now) is False)
    check('cache: a stamp from the future -> rejected (a clock that '
          'moved backwards must not pin a stale number)',
          ok('abc', future, 'abc', now) is False)
    check('cache: exactly at the TTL boundary is still usable',
          ok('abc',
             time.strftime('%Y-%m-%dT%H:%M:%S',
                           time.localtime(now - hardware.HW_CACHE_TTL_S + 60)),
             'abc', now) is True)


def host_probe_checks():
    print("\nN21: the Windows host RAM probe (ctypes, no dependency)")
    saved = (hardware._host_ram_gb, hardware._host_ram_src,
             hardware._host_probed)
    try:
        hardware.forget_host()
        check('host: cache-only before any probe, and honest about it',
              hardware.host()['ram_gb'] is None
              and hardware.host()['ram_source'] == hardware.UNKNOWN)
        check('host: cores come from os.cpu_count(), which never blocks',
              hardware.host()['cores'] == os.cpu_count())

        got = hardware.detect_host_ram_gb()
        if os.name == 'nt':
            check('host: a Windows probe returns a plausible RAM size',
                  isinstance(got, int) and 1 <= got <= 4096, str(got))
            check('host: a measured value says MEASURED',
                  hardware.host()['ram_source'] == hardware.MEASURED)
        else:
            check('host: off Windows the probe degrades to unknown, '
                  'it does not raise',
                  got is None
                  and hardware.host()['ram_source'] == hardware.UNKNOWN)

        # priming must never clobber a live measurement
        hardware.forget_host()
        hardware.prime_host(ram_gb=64)
        check('host: primed values are CACHED, not MEASURED',
              hardware.host() == dict(ram_gb=64, ram_source=hardware.CACHED,
                                      cores=os.cpu_count()),
              str(hardware.host()))
        hardware.prime_host(ram_gb=999)
        check('host: priming twice does not overwrite',
              hardware.host()['ram_gb'] == 64)
        hardware.forget_host()
        check('host: forget_host() clears the value, the source and the '
              'probe-attempt flag',
              hardware.host()['ram_gb'] is None
              and not hardware._host_probed)
    finally:
        (hardware._host_ram_gb, hardware._host_ram_src,
         hardware._host_probed) = saved


def native_cap_checks():
    print("\nN21: native cell caps from host RAM")
    P = hardware.plan_native
    per = hardware.native_bytes_per_cell

    check('bytes/cell: 2D costs more per cell than 3D (it keeps '
          'final_state, trigger_state and float64 snapshots)',
          per(2) > per(3), f'{per(2)} vs {per(3)}')
    check('bytes/cell: the old "~200 B/cell" comment was low by ~3x',
          per(3) > 500 and per(2) > 700, f'{per(2)} / {per(3)}')
    check('bytes/cell: order 2 costs more than order 1',
          per(3, order=2) > per(3, order=1))
    check('bytes/cell: more snapshots cost more, and 2D much more '
          'per snapshot than 3D',
          per(2, n_snapshots=12) - per(2, n_snapshots=6)
          > per(3, n_snapshots=12) - per(3, n_snapshots=6))

    # unknown host RAM must reproduce exactly the pre-N21 behaviour
    for dim, hard_w, hard_r in ((2, CELLS_2D_WARN, CELLS_2D_MAX),
                                (3, CELLS_WARN, CELLS_REFUSE)):
        pl = P(dim=dim, ram_gb=None)
        check(f'{dim}D: unknown host RAM -> exactly the fixed caps '
              f'(so an unmeasured machine behaves as it always did)',
              pl.cell_cap_refuse == hard_r and pl.cell_cap_warn == hard_w
              and pl.from_memory is False, pl.reason)

    # pinned table: (dim, host GB) -> is the cap the fixed one or lower?
    check('3D: a 128 GB host is not lifted above CELLS_REFUSE',
          P(dim=3, ram_gb=128).cell_cap_refuse == CELLS_REFUSE)
    check('2D: a 128 GB host is not lifted above CELLS_2D_MAX',
          P(dim=2, ram_gb=128).cell_cap_refuse == CELLS_2D_MAX)
    check('3D: a 16 GB host is already at the fixed cap (this change '
          'is a no-op on any ordinary workstation)',
          P(dim=3, ram_gb=16).cell_cap_refuse == CELLS_REFUSE)
    check('3D: an 8 GB laptop is capped below the constant',
          P(dim=3, ram_gb=8).cell_cap_refuse < CELLS_REFUSE,
          str(P(dim=3, ram_gb=8).cell_cap_refuse))
    check('2D: a 4 GB machine is capped well below CELLS_2D_MAX',
          P(dim=2, ram_gb=4).cell_cap_refuse < CELLS_2D_MAX)
    check('a RAM-derived cap explains itself in GB and KB/cell',
          'KB/cell' in P(dim=3, ram_gb=8).reason
          and 'host RAM' in P(dim=3, ram_gb=8).reason,
          P(dim=3, ram_gb=8).reason)
    check('est_bytes: the 3D cap on an 8 GB host really is ~60% of it',
          0.55 < (P(dim=3, ram_gb=8).est_bytes(
              P(dim=3, ram_gb=8).cell_cap_refuse) / (8 * 2 ** 30)) < 0.62)

    # invariants over a sweep, not just the pinned rows
    bad = []
    for dim, hard_w, hard_r in ((2, CELLS_2D_WARN, CELLS_2D_MAX),
                                (3, CELLS_WARN, CELLS_REFUSE)):
        for ram in (None, 1, 2, 4, 8, 16, 64, 128, 1024):
            for order in (1, 2):
                for snaps in (0, 6, 40):
                    pl = P(dim=dim, order=order, n_snapshots=snaps,
                           ram_gb=ram)
                    if pl.cell_cap_refuse > hard_r:
                        bad.append((dim, ram, order, snaps, 'above the '
                                    'fixed cap'))
                    if pl.cell_cap_warn > hard_w:
                        bad.append((dim, ram, order, snaps, 'warn above '
                                    'the fixed warn'))
                    if ram and pl.cell_cap_refuse < \
                            min(NATIVE_CELLS_FLOOR.values()):
                        bad.append((dim, ram, order, snaps, 'below the '
                                    'floor'))
                    if pl.cell_cap_warn > pl.cell_cap_refuse:
                        bad.append((dim, ram, order, snaps, 'warn above '
                                    'refuse'))
    check('native sweep: floor <= cap <= the fixed constant, warn <= '
          'refuse, for every host size and case shape',
          not bad, str(bad[:3]))
    check('native: a tiny host still runs the shipped examples '
          '(1 GB floor >= 2M cells > the 512k regression baseline)',
          P(dim=3, ram_gb=1).cell_cap_refuse >= 2_000_000)


def budget_checks():
    print("\nN21: frame budgets derived from host RAM")
    from blastlab.solvers.hooks import FRAME_MEM_BUDGET, frame_mem_budget
    from blastlab.viz3d.sampling import FRAME_MEM_CAP, frame_mem_cap

    for name, fn, ceiling in (('viewer playback', frame_mem_cap,
                               FRAME_MEM_CAP),
                              ('GUI replay record', frame_mem_budget,
                               FRAME_MEM_BUDGET)):
        check(f'{name}: unknown host RAM keeps the old fixed budget',
              fn(None) == int(ceiling), str(fn(None)))
        check(f'{name}: a big host is capped at the same ceiling '
              f'(no change on a workstation)',
              fn(256) == int(ceiling))
        check(f'{name}: a 4 GB machine gets less than the ceiling',
              fn(4) < int(ceiling), str(fn(4)))
        check(f'{name}: never zero, even on a 1 GB machine',
              fn(1) > 0)
        check(f'{name}: monotonic in host RAM',
              fn(2) <= fn(8) <= fn(64) <= fn(256))

    check('the 3D view resolution is NOT derived - the same case must '
          'look the same on every machine',
          __import__('blastlab.viz3d.sampling', fromlist=['x'])
          .MAX_VIEW_DIM == 128)


def persistence_checks():
    """T66: what the GUI saves and what it is willing to prime from.

    Drives App's methods unbound - no window, no event loop."""
    print("\nN21: persisting and priming the hardware numbers")
    try:
        from blastlab.core import settings as gs
        from blastlab.gui.app import App
    except Exception as exc:                 # no customtkinter on this box
        print(f'  [SKIP] GUI not importable: {exc}')
        return
    from blastlab.solvers.foam import env

    class Fake:
        pass
    for m in ('_prime_hardware_from', '_persist_hardware', '_hw_suffix',
              '_hw_tooltip'):
        setattr(Fake, m, getattr(App, m))
    app = Fake()
    saved = _save_env_hw(env)
    saved_host = (hardware._host_ram_gb, hardware._host_ram_src,
                  hardware._host_probed)
    try:
        good = dict(gs.DEFAULTS, hw_cores=20, hw_ram_gb=96,
                    hw_stamp='2026-09-09T10:00:00',
                    hw_fingerprint='deadbeefdeadbeef')
        gs.save(good)
        # the bug this fixes: a failed probe used to write hw_ram_gb=0
        # and a fabricated 4-core count over a real measurement
        app._persist_hardware(dict(cores=4, ram_gb=0,
                                   cores_source=hardware.UNKNOWN,
                                   ram_source=hardware.UNKNOWN))
        st = gs.load()
        check('persist: a failed probe leaves good values alone',
              st['hw_cores'] == 20 and st['hw_ram_gb'] == 96, str(st))

        hardware.detect_host_ram_gb()
        app._persist_hardware(dict(cores=8, ram_gb=15,
                                   cores_source=hardware.MEASURED,
                                   ram_source=hardware.MEASURED))
        st = gs.load()
        check('persist: a measured probe writes through',
              st['hw_cores'] == 8 and st['hw_ram_gb'] == 15, str(st))
        check('persist: it also records which machine, and the host RAM',
              len(st['hw_fingerprint']) == 16 and st['hw_stamp'], str(st))

        env.forget_hardware()
        app._prime_hardware_from(dict(gs.load(),
                                      hw_fingerprint='0' * 16,
                                      hw_cores=99, hw_ram_gb=999))
        check('prime: a settings file from another machine is ignored '
              '(this is what stops a synced profile sizing runs here)',
              env.hardware() is None, str(env.hardware()))

        env.forget_hardware()
        app._prime_hardware_from(gs.load())
        hw = env.hardware() or {}
        check('prime: this PC\'s own fresh entry is used, as CACHED',
              hw.get('ram_gb') == 15
              and hw.get('ram_source') == hardware.CACHED, str(hw))
        check('sidebar: names the VM and flags the value as cached',
              'GB VM' in app._hw_suffix() and 'cached' in app._hw_suffix(),
              app._hw_suffix())

        env.forget_hardware()
        check('sidebar: unknown hardware says so rather than showing '
              'nothing - the caps depend on it',
              'unknown' in app._hw_suffix()
              and 'Re-detect' in app._hw_tooltip(), app._hw_suffix())
    finally:
        _restore_env_hw(env, saved)
        (hardware._host_ram_gb, hardware._host_ram_src,
         hardware._host_probed) = saved_host


_ENV_HW = ('_cores', '_slots', '_ram_gb', '_cores_src', '_slots_src',
           '_ram_src', '_cores_tried', '_slots_tried', '_ram_tried')


def _save_env_hw(env):
    return tuple(getattr(env, a) for a in _ENV_HW)


def _restore_env_hw(env, saved):
    for a, v in zip(_ENV_HW, saved):
        setattr(env, a, v)


def main():
    meminfo_checks()
    fingerprint_checks()
    cache_checks()
    host_probe_checks()
    native_cap_checks()
    budget_checks()
    persistence_checks()

    print()
    if FAIL:
        print(f"HARDWARE: FAIL ({len(FAIL)}): {', '.join(FAIL)}")
        return 1
    print("HARDWARE: PASS")
    return 0


if __name__ == '__main__':
    sys.exit(main())
