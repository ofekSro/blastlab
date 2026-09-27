"""Start `python -m blastlab [--tk]` as the user does, wait, send WM_CLOSE
to its top-level window (the title-bar X), and report exit code + stderr.
Run:  python close_test.py qt|tk
"""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

REPO = r'C:\Users\rotem.ofek\OneDrive - Technion\BlastFoam'
kind = sys.argv[1]
args = [sys.executable, '-m', 'blastlab'] + (['--tk'] if kind == 'tk' else [])
env = dict(os.environ)
env.pop('QT_QPA_PLATFORM', None)
assert env.get('BLASTLAB_SETTINGS')
p = subprocess.Popen(args, cwd=REPO, env=env, stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE, text=True)
user32 = ctypes.windll.user32
found = []


@ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
def enum(hwnd, _l):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == p.pid and user32.IsWindowVisible(hwnd):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        if buf.value.startswith('blastlab'):
            found.append((hwnd, buf.value))
    return True


t0 = time.time()
while time.time() - t0 < 30 and not found:
    time.sleep(1)
    user32.EnumWindows(enum, 0)
time.sleep(6)
print('window:', found[:1], 'after', round(time.time() - t0), 's')
if found:
    user32.PostMessageW(found[0][0], 0x0010, 0, 0)       # WM_CLOSE
try:
    out, err = p.communicate(timeout=30)
    print('exit code', p.returncode)
except subprocess.TimeoutExpired:
    p.kill()
    out, err = p.communicate()
    print('DID NOT EXIT within 30 s of WM_CLOSE - killed')
print('stdout tail:', out[-1500:])
print('stderr tail:', err[-3000:])
