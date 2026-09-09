"""Host-side hardware discovery, and the pure helpers both backends share.

Two machines matter to a run. The **Windows host** is where the native
solvers and the whole GUI live, so a MemoryError there kills the window;
the **WSL VM** is where blastFoam solves. `solvers/foam/env` owns the VM
side. This module owns the host side plus every pure function the two
have in common, so `core.case` can size a native case without importing
the foam package.

Every number carries a source. Nothing is ever fabricated: a value of
None always means UNKNOWN, and the caller decides what to do about it
rather than being handed a plausible guess (the old `detect_cores`
returned 4 on failure and the run plan then said "4 physical cores" as
if it had measured them).
"""

import datetime
import hashlib
import os
import platform
import threading
from dataclasses import dataclass

from .constants import (CELLS_2D_MAX, CELLS_2D_WARN, CELLS_REFUSE,
                        CELLS_WARN, NATIVE_CELLS_FLOOR, NATIVE_HELD_BASE,
                        NATIVE_HELD_PER_SNAP, NATIVE_ORDER2_EXTRA,
                        NATIVE_PEAK, NATIVE_RAM_REFUSE_FRACTION,
                        NATIVE_RAM_WARN_FRACTION)

#: probed during this session - trust it
MEASURED = 'measured'
#: a previous session's number whose fingerprint and stamp still check
#: out; usable, but a live probe should still be attempted
CACHED = 'cached'
#: never obtained, or the persisted value was rejected
UNKNOWN = 'unknown'

#: how long a persisted hardware measurement stays usable. A .wslconfig
#: edit does not change the fingerprint, so this is the only thing that
#: catches one; a probe normally lands within seconds of startup, so a
#: discarded cache costs almost nothing.
HW_CACHE_TTL_S = 7 * 86400

#: clock skew tolerated before a stamp is called bogus
_FUTURE_SLACK_S = 86400


# -- pure helpers ------------------------------------------------------------

def parse_meminfo_kb(text):
    """/proc/meminfo -> MemTotal in kB, or None when the line is absent.

    Replaces the `free -g` parse for the VM probe: `free -g` truncates to
    whole GiB, so a 900 MB VM and a failed probe both read as 0."""
    for line in (text or '').splitlines():
        parts = line.split()
        if parts and parts[0].rstrip(':') == 'MemTotal':
            try:
                return int(parts[1])
            except (IndexError, ValueError):
                return None
    return None


def fingerprint(node, cpu_count, host_ram_gb, distro):
    """Identity of the machine a persisted measurement belongs to.

    Deliberately NOT the VM's RAM (that is the value being validated -
    including it would make the check circular) and not a MAC address or
    volume serial (privacy-adjacent, and they change for reasons that
    have nothing to do with capacity)."""
    raw = '|'.join((str(node or '').strip().lower(),
                    str(int(cpu_count or 0)),
                    str(int(host_ram_gb or 0)),
                    str(distro or '').strip().lower()))
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]


def native_bytes_per_cell(dim, order=1, n_snapshots=6):
    """Bytes of host RAM one cell of a native run costs at peak.

    The step's transient peak plus everything the finished Result keeps,
    because both are live at the same time: the last step runs with every
    earlier snapshot still in memory."""
    d = 2 if int(dim) == 2 else 3
    per = NATIVE_PEAK[d] + NATIVE_HELD_BASE[d]
    if int(order or 1) >= 2:
        per += NATIVE_ORDER2_EXTRA[d]
    per += NATIVE_HELD_PER_SNAP[d] * (max(int(n_snapshots or 0), 0) + 1)
    return per


@dataclass(frozen=True)
class NativePlan:
    """What the host allows for one native run."""
    cell_cap_warn: int
    cell_cap_refuse: int
    bytes_per_cell: int
    reason: str
    ram_gb: int = None
    ram_source: str = UNKNOWN

    @property
    def from_memory(self):
        """True when the caps came from the host's measured RAM."""
        return self.ram_gb is not None

    def est_bytes(self, n_cells):
        return int(n_cells) * self.bytes_per_cell


def plan_native(n_cells=0, dim=3, order=1, n_snapshots=6, ram_gb=None,
                ram_source=None):
    """Pure planner: (cells, case shape, host RAM) -> NativePlan.

    The derived cap can only ever LOWER the fixed CELLS_* constants,
    never raise them. That is what keeps this change safe: the solvers
    themselves still enforce the constants unchanged, so no numerics and
    no byte-parity baseline can be affected, and a machine we know
    nothing about behaves exactly as it did before N21.

    It also never falls below NATIVE_CELLS_FLOOR, so a small or unknown
    machine can still run every shipped example."""
    d = 2 if int(dim) == 2 else 3
    per = native_bytes_per_cell(d, order, n_snapshots)
    hard_refuse = CELLS_2D_MAX if d == 2 else CELLS_REFUSE
    hard_warn = CELLS_2D_WARN if d == 2 else CELLS_WARN
    ram = int(ram_gb) if ram_gb else None
    src = ram_source or (UNKNOWN if ram is None else MEASURED)

    if ram is None:
        return NativePlan(hard_warn, hard_refuse, per,
                          'host RAM unknown: the fixed %s-cell cap'
                          % format(hard_refuse, ','),
                          ram_source=UNKNOWN)

    floor = NATIVE_CELLS_FLOOR[d]
    refuse = min(hard_refuse,
                 max(floor, int(NATIVE_RAM_REFUSE_FRACTION
                                * ram * 2 ** 30 / per)))
    warn = min(hard_warn,
               max(floor // 2, int(NATIVE_RAM_WARN_FRACTION
                                   * ram * 2 ** 30 / per)))
    if refuse >= hard_refuse:
        reason = ('%d GB host holds more than the fixed %s-cell cap'
                  % (ram, format(hard_refuse, ',')))
    else:
        reason = ('%s cells: %d%% of %d GB host RAM at ~%.2f KB/cell'
                  % (format(refuse, ','),
                     int(NATIVE_RAM_REFUSE_FRACTION * 100), ram,
                     per / 1000.0))
    return NativePlan(warn, refuse, per, reason, ram_gb=ram, ram_source=src)


def memory_budget(host_ram_gb, fraction, floor, ceiling):
    """A host-RAM slice, clamped - the shape every frame budget uses.

    Unknown RAM keeps the ceiling, which is the value these budgets were
    hard-coded to before N21: a machine we cannot measure behaves as it
    always did, and only a measurably small one is cut back."""
    if not host_ram_gb:
        return int(ceiling)
    return int(max(floor, min(ceiling,
                              fraction * int(host_ram_gb) * 2 ** 30)))


def parse_stamp(text):
    """ISO-8601 stamp -> epoch seconds, or None when unparseable."""
    try:
        return datetime.datetime.fromisoformat(str(text)).timestamp()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def cache_is_valid(saved_fp, saved_stamp, now_fp, now, ttl=HW_CACHE_TTL_S):
    """May a persisted hardware measurement be reused on this machine?

    False on: a missing fingerprint either side, a different machine, an
    unparseable or expired stamp, or a stamp from the future (a clock
    that moved backwards would otherwise pin a stale number for a week).
    """
    if not saved_fp or not now_fp or saved_fp != now_fp:
        return False
    ts = parse_stamp(saved_stamp)
    if ts is None:
        return False
    if ts > now + _FUTURE_SLACK_S:
        return False
    return (now - ts) <= ttl


# -- the Windows host --------------------------------------------------------

_lock = threading.Lock()
_host_ram_gb = None         # total physical RAM, GiB (0 = probe failed)
_host_ram_src = UNKNOWN
_host_probed = False


def _global_memory_status():
    """(total, available) physical bytes from GlobalMemoryStatusEx, or
    None off Windows / when ctypes cannot make the call.

    Same defensive shape as `foam.env._win_pid_alive`: a local WinDLL
    with explicit argtypes, and every failure mode collapses to None."""
    if os.name != 'nt':
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [('dwLength', wintypes.DWORD),
                        ('dwMemoryLoad', wintypes.DWORD),
                        ('ullTotalPhys', ctypes.c_ulonglong),
                        ('ullAvailPhys', ctypes.c_ulonglong),
                        ('ullTotalPageFile', ctypes.c_ulonglong),
                        ('ullAvailPageFile', ctypes.c_ulonglong),
                        ('ullTotalVirtual', ctypes.c_ulonglong),
                        ('ullAvailVirtual', ctypes.c_ulonglong),
                        ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]

        k32 = ctypes.WinDLL('kernel32', use_last_error=True)
        k32.GlobalMemoryStatusEx.restype = wintypes.BOOL
        k32.GlobalMemoryStatusEx.argtypes = (ctypes.POINTER(MEMORYSTATUSEX),)
        st = MEMORYSTATUSEX()
        st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if not k32.GlobalMemoryStatusEx(ctypes.byref(st)):
            return None
        return int(st.ullTotalPhys), int(st.ullAvailPhys)
    except (AttributeError, OSError, ValueError):
        return None


def detect_host_ram_gb():
    """Total physical RAM of the Windows host in GiB (cached; None when
    it cannot be measured). Probed at most once per session - a failure
    is not retried, since nothing about it is transient."""
    global _host_ram_gb, _host_ram_src, _host_probed
    with _lock:
        if _host_ram_src == MEASURED or _host_probed:
            return _host_ram_gb or None
        _host_probed = True
    mem = _global_memory_status()
    with _lock:
        if mem is None:
            _host_ram_gb = 0
        else:
            _host_ram_gb = int(mem[0] / 2 ** 30)
            _host_ram_src = MEASURED
        return _host_ram_gb or None


def host(probe=False):
    """dict(ram_gb, ram_source, cores) for the Windows host.

    Cache-only unless `probe` - `validate_case` calls this on every
    keystroke. `cores` is os.cpu_count(), which costs nothing and is
    display-only: the native solvers are single-threaded numpy."""
    if probe:
        detect_host_ram_gb()
    with _lock:
        return dict(ram_gb=_host_ram_gb or None, ram_source=_host_ram_src,
                    cores=os.cpu_count())


def prime_host(ram_gb=None, source=CACHED):
    """Seed the host cache from persisted settings, so the first
    validation of a session sizes against real numbers.

    Fills a gap only - it never overwrites a value already there, live
    or primed. Same contract as `foam.env.prime_hardware`."""
    global _host_ram_gb, _host_ram_src
    with _lock:
        if _host_ram_gb is None and ram_gb:
            _host_ram_gb, _host_ram_src = int(ram_gb), source


def forget_host():
    """Drop the host cache (Re-detect, and tests)."""
    global _host_ram_gb, _host_ram_src, _host_probed
    with _lock:
        _host_ram_gb, _host_ram_src, _host_probed = None, UNKNOWN, False


def machine_fingerprint(distro=''):
    """This machine's fingerprint, from cached values only (no probe)."""
    with _lock:
        ram = _host_ram_gb or 0
    return fingerprint(platform.node(), os.cpu_count(), ram, distro)
