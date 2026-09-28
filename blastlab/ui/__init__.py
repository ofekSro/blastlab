"""blastlab Qt (PySide6) front-end.

The redesigned frame (GUI-3, docs/gui-redesign-plan.md §4): a top bar
with workflow pills (Setup | Run | Results | Chain) over a content
stack, with pyqtgraph for every on-screen plot and the 3D scenes
rendered by a separate viewer process
(`blastlab.viz3d.process`). Nothing in this package imports pyvista or
VTK. Launch: `python -m blastlab --qt` (the default once the port reaches
parity with `blastlab.gui`).
"""
