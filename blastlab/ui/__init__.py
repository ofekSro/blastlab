"""blastlab Qt (PySide6) front-end.

Same layout as the Tk app it replaces - left sidebar (Setup | Run |
Results | Chain) and a content stack - with pyqtgraph for every on-screen
plot and the 3D scenes rendered by a separate viewer process
(`blastlab.viz3d.process`). Nothing in this package imports pyvista or
VTK. Launch: `python -m blastlab --qt` (the default once the port reaches
parity with `blastlab.gui`).
"""
