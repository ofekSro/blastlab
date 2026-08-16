"""Bridge OO Figures into pyplot for the CLI workflow.

The figure builders in output/plots.py deliberately avoid pyplot (the GUI
embeds them directly). The legacy CLI, however, expects `plt.show()` to
pop the figures up. `adopt_figure` registers an OO Figure with pyplot's
figure manager so the historical show() behaviour keeps working.
"""


def adopt_figure(fig):
    import matplotlib
    if matplotlib.get_backend().lower().startswith('agg'):
        return   # headless: nothing to show
    import matplotlib.pyplot as plt
    dummy = plt.figure(figsize=fig.get_size_inches())
    manager = dummy.canvas.manager
    manager.canvas.figure = fig
    fig.set_canvas(manager.canvas)
