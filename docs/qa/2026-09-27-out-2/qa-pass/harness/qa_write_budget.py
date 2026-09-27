"""Offscreen probe (no screenshot needed): a case file with write_budget > 0
and VTK volumes on - what does the Setup strip say, and does the form keep
write_budget at all (it has no field for it)?"""
import json
import os
import sys
import time

REPO = r'C:\Users\rotem.ofek\OneDrive - Technion\BlastFoam'
sys.path.insert(0, REPO)
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from blastlab.ui.testing import ensure_qapp  # noqa: E402

app = ensure_qapp()
from blastlab.core.case import Case3D, save_case, case_to_dict  # noqa: E402
from blastlab.ui.app import MainWindow  # noqa: E402
from blastlab.services.validation import validate_case  # noqa: E402


def pump(s):
    end = time.monotonic() + s
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


work = sys.argv[1]
c = Case3D(solver='blastfoam', write_budget=10,
           vtk_volumes=dict(on=True, mode='time', value=1.0, fields=['p']))
rep = validate_case(c)
print('headless validate errors:', rep.errors)
p = os.path.join(work, 'case_budget_vtk.json')
save_case(c, p)
print('file write_budget:', json.load(open(p)).get('write_budget'))
win = MainWindow()
win.show()
pump(1.5)
win._open_case(p)
pump(1.0)
win._schedule_validate()
pump(1.5)
print('strip:', [t for _s, t in win.setup.report_rows()][:3])
back = case_to_dict(win.setup.get_case())
print('form -> case write_budget:', back.get('write_budget'),
      'vtk_volumes:', back.get('vtk_volumes'))
win.close()
pump(0.5)
