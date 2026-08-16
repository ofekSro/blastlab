#!/usr/bin/env python3
"""blast2d.py - compatibility wrapper.

The implementation lives in the blastlab package (blastlab/legacy/blast2d.py
re-exports the historical API; the physics is in blastlab/core and
blastlab/solvers). Running this script starts the same interactive
prompt workflow as before.
"""
from blastlab.legacy.blast2d import *          # noqa: F401,F403

if __name__ == '__main__':
    from blastlab.legacy.blast2d import _main
    _main()
