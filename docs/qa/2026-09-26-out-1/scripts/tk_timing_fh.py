"""tk_timing.py under faulthandler (all threads), so a native crash of the
Tk process leaves a Python traceback of every thread.
`--nosample` turns the stack sampler off (sys._current_frames -> {}), to
rule it out as a cause.

Run:  python -u docs/qa/2026-09-26-out-1/scripts/tk_timing_fh.py [--nosample]
"""
import faulthandler
import os
import sys

if __name__ == '__main__':
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, here)
    tag = 'nosample' if '--nosample' in sys.argv else 'sample'
    fh = open(os.path.join(here, '..', f'tk_timing_faulthandler_{tag}.txt'),
              'w', encoding='utf-8')
    faulthandler.enable(file=fh, all_threads=True)
    if tag == 'nosample':
        sys._current_frames = lambda: {}
    import qa_common as Q
    _set_log = Q.set_log
    Q.set_log = lambda name, append=False: _set_log(f'{name}_{tag}', append)
    import tk_timing
    tk_timing.main()
    os._exit(0)
