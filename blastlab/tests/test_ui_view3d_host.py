"""The Qt 3D host without a viewer process: every control must turn into
the exact message the viewer child expects, and the child's `status`
replies must drive the timeline, the field radios and the Min/Max boxes.
Headless: offscreen Qt, a recording stub in place of the viewer link."""
import os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from blastlab.ui.testing import ensure_qapp, pump          # noqa: E402

app = ensure_qapp()

from blastlab.core.bc import solid_mask_3d                 # noqa: E402
from blastlab.core.constants import P_AIR                  # noqa: E402
from blastlab.core.grid import make_grid                   # noqa: E402
from blastlab.viz3d.feed import Feed3D, N_PLANES           # noqa: E402
from blastlab.viz3d.viewer import FIELDS                   # noqa: E402
from blastlab.ui.view3d_host import View3DHost, make_ring  # noqa: E402

FAIL = []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        FAIL.append(name)


class FakeLink:
    """Records what would have gone down the pipe."""

    def __init__(self):
        self.sent = []
        self.hosts = {}
        self.started = 0

    def register(self, surface, host):
        self.hosts[surface] = host

    def ensure_started(self):
        self.started += 1
        return True

    @property
    def alive(self):
        return True

    def send(self, msg):
        self.sent.append(msg)
        return True

    def ctrls(self, name=None):
        out = [m for m in self.sent if m[0] == 'ctrl']
        return [m for m in out if name is None or m[2] == name]

    def last(self, tag):
        for m in reversed(self.sent):
            if m[0] == tag:
                return m
        return None

    def clear(self):
        self.sent = []


def scene_info():
    grid = make_grid(2.0, 2.0, 2.0, 0.1)
    x_c, y_c, z_c = grid['x_c'], grid['y_c'], grid['z_c']
    obstacles = [(1.2, 1.6, 0.6, 1.2, 0.0, 0.7)]
    solid = solid_mask_3d(x_c, y_c, z_c, obstacles)
    return dict(x_c=x_c, y_c=y_c, z_c=z_c, dx=0.1, solid=solid,
                obstacles=obstacles, Lx=2.0, Ly=2.0, Lz=2.0,
                charge_center=(0.7, 1.0, 0.5), r_exp=0.15,
                bcs=dict(x_lo='terminate', x_hi='terminate',
                         y_lo='terminate', y_hi='terminate',
                         z_lo='reflect', z_hi='terminate'))


def main():
    link = FakeLink()
    host = View3DHost(link, 'run')
    host.resize(900, 600)
    host.show()
    pump(60)

    print("\nV1: the host registers itself and starts idle")
    check("registered for its surface", link.hosts.get('run') is host)
    check("no scene yet", not host.has_scene)
    check("controls are silent before a scene",
          link.ctrls() == [], str(link.ctrls()[:2]))

    print("\nV2: attaching a live scene")
    info = scene_info()
    got = host.prepare_live(info)
    check("prepare_live returned a feed and a ring", got is not None
          and isinstance(got[0], Feed3D))
    feed, ring = got
    check("the host reports a scene", host.has_scene)
    scene = link.last('scene')
    check("a scene message was sent", scene is not None
          and scene[1] == 'run')
    spec = scene[2]
    check("it carries the shared-memory name and the layout",
          spec['shm'] == ring.name and spec['layout'] is ring.layout)
    check("it asks for the GUI's six planes, embedded",
          spec['n_planes'] == N_PLANES and spec['embedded'] is True)
    check("the init is the feed's own (same decimation as the payloads)",
          spec['init'] is feed.init)
    check("the control state was replayed after the scene",
          {m[2] for m in link.ctrls()} >= {'layer', 'field', 'iso_frac',
                                           'auto_scale', 'log', 'follow',
                                           'parallel', 'plane',
                                           'plane_opacity'},
          str(sorted({m[2] for m in link.ctrls()})))
    check("every layer and plane was set",
          len(link.ctrls('layer')) == 4 + N_PLANES,
          str(len(link.ctrls('layer'))))
    check("the viewer was asked to show the window",
          link.last('claim') is not None)

    print("\nV3: a frame published into the ring is what the viewer reads")
    X, Y, Z = np.meshgrid(info['x_c'], info['y_c'], info['z_c'],
                          indexing='ij')
    p = P_AIR + 2e5 * np.exp(-((X - 0.7) ** 2 + (Y - 1.0) ** 2
                               + (Z - 0.5) ** 2) / 0.05)
    ring.write(1.5e-4, feed.make_payload(dict(p=p, rho=1.2 + p / 3e5)))
    from blastlab.viz3d.protocol import SharedFrameRing
    reader = SharedFrameRing(ring.layout, name=ring.name, create=False)
    back = reader.read(0)
    check("the frame arrives with its time and fields",
          back is not None and abs(back[1] - 1.5e-4) < 1e-12
          and 'p' in back[2] and 'rho' in back[2])
    check("decimated to the viewer's display grid",
          back[2]['p'].shape == feed.init['solid_dec'].shape,
          str(back[2]['p'].shape))
    reader.close()

    print("\nV4: each control sends its own message")
    link.clear()
    host._checks['volume'].setChecked(True)
    check("layer toggle", link.ctrls('layer')[-1][3:] == ('volume', True),
          str(link.ctrls('layer')[-1]))
    key = [k for k in FIELDS if k != 'p'][0]
    host._field_btns[key].setChecked(True)
    check("field radio", link.ctrls('field')[-1][3] == key,
          str(link.ctrls('field')[-1]))
    host._iso.setValue(35)
    check("iso slider sends a fraction",
          abs(link.ctrls('iso_frac')[-1][3] - 0.35) < 1e-9,
          str(link.ctrls('iso_frac')[-1]))
    host._checks['auto_scale'].setChecked(False)
    host._vmin.setText('10')
    host._vmax.setText('400')
    host._clim_changed()
    check("manual colour range", link.ctrls('clim')[-1][3:] == (10.0, 400.0),
          str(link.ctrls('clim')[-1]))
    host._vmax.setText('5')                       # max below min
    host._clim_changed()
    check("an inverted range is refused",
          link.ctrls('clim')[-1][3:] == (10.0, 400.0),
          str(link.ctrls('clim')[-1]))
    link.clear()
    axis, pos, op = host._planes['plane1']
    axis.setCurrentText('z')
    pos.setValue(0)
    op.setCurrentText('50')
    last_plane = link.ctrls('plane')[-1]
    check("plane axis and position", last_plane[3] == 'plane1'
          and last_plane[4] == 'z', str(last_plane))
    check("a plane is kept just inside the domain face (never 0.0)",
          last_plane[5] > 0.0 and last_plane[5] < 0.01, str(last_plane[5]))
    check("plane opacity as a fraction",
          abs(link.ctrls('plane_opacity')[-1][4] - 0.5) < 1e-9,
          str(link.ctrls('plane_opacity')[-1]))
    link.clear()
    host._checks['parallel'].setChecked(True)
    check("parallel projection", link.ctrls('parallel')[-1][3] is True)

    print("\nV5: status replies drive the timeline and the radios")
    host.on_status(dict(n=12, index=11, t=3e-4, done=False, playing=False,
                        follow=True, field='p', vmin=0.0, vmax=250.0,
                        have=['p', 'rho'], stop_reason=''))
    check("the slider spans the stored frames",
          host.time_slider.maximum() == 11, str(host.time_slider.maximum()))
    check("and sits on the newest one", host.time_slider.value() == 11)
    hidden = [k for k, _l in [(k, v['label']) for k, v in FIELDS.items()]
              if not host._field_btns[k].isVisible()]
    check("fields this run never recorded are hidden, not greyed",
          set(hidden) == {k for k in FIELDS if k not in ('p', 'rho')},
          str(hidden))
    host._checks['auto_scale'].setChecked(True)
    host.on_status(dict(n=12, index=11, t=3e-4, done=False, playing=False,
                        follow=True, field='p', vmin=0.0, vmax=987.0,
                        have=['p'], stop_reason=''))
    check("auto scale mirrors the live range into the boxes",
          host._vmax.text() == '987', host._vmax.text())
    check("a field that disappeared falls back to pressure",
          host._field_btns['p'].isChecked())

    print("\nV6: scrubbing the timeline leaves follow-live")
    link.clear()
    host.time_slider.setValue(4)
    check("the frame index was sent", link.ctrls('show_frame')[-1][3] == 4,
          str(link.ctrls('show_frame')[-1]))
    check("follow-live was turned off with it",
          not host._follow.isChecked()
          and link.ctrls('follow')[-1][3] is False)

    print("\nV7: play needs frames, and reports through status")
    link.clear()
    host._toggle_play()
    check("play starts", link.ctrls('play')[-1][3] is True
          and host.play_btn.text() == 'Pause')
    host.on_status(dict(n=12, index=5, t=2e-4, done=True, playing=False,
                        follow=False, field='p', vmin=0.0, vmax=987.0,
                        have=['p'], stop_reason='shock arrived'))
    check("the child stopping playback is reflected on the button",
          host.play_btn.text() == 'Play')

    print("\nV8: done and reset")
    link.clear()
    host.on_done('shock arrived')
    check("the run end reaches the viewer",
          link.last('done')[1:] == ('run', 'shock arrived'),
          str(link.last('done')))
    host.reset()
    check("reset drops the scene and releases the window",
          not host.has_scene and link.last('release') is not None)
    link.clear()
    host._checks['volume'].setChecked(False)
    check("controls go quiet again with no scene", link.ctrls() == [])

    print("\nV9: the control column folds away on a narrow host")
    host.resize(600, 500)
    pump(60)
    check("collapsed below 700 px", host._ctl_collapsed
          and not host._ctl.isVisible())
    host.resize(1000, 500)
    pump(60)
    check("back at full width", not host._ctl_collapsed)
    host._collapse_clicked()
    host.resize(1000, 500)
    pump(60)
    check("a manual choice outranks the width", host._ctl_collapsed)

    ring.close(unlink=True)
    host.close()
    pump(20)

    v10_native_detach_stays()
    print("\n" + "=" * 50)
    if FAIL:
        print(f"FAILED: {len(FAIL)} check(s): {FAIL}")
        sys.exit(1)
    print("All Qt 3D-host checks passed.")


def v10_native_detach_stays():
    """GUI-16 (g): the bookkeeping of a native-mount Detach. Offscreen
    there is no real window to adopt, so the mount is a plain widget and
    the Win32 release is stubbed; `_e2e_ui_view3d.py` G3 measures the
    real window."""
    from PySide6.QtWidgets import QWidget
    print("\nV10: a native Detach stays detached until Re-attach or close")
    link = FakeLink()
    host = View3DHost(link, 'nat')
    host.resize(900, 600)
    host.show()
    pump(30)
    embeds = []
    host._embed = lambda: embeds.append(host._hwnd) or True

    def release():
        host._native = False
    host._release_native = release
    host._has_scene = True
    host._hwnd = 4242
    mount = QWidget()
    host._view_stack.addWidget(mount)
    host._view_stack.setCurrentWidget(mount)
    host._container, host._native = mount, True

    host.set_floating(True)
    check("Detach hands the window back (mount dropped)",
          host._floating and host._container is None
          and link.last('detach')[1:] == ('nat', True))
    host.on_window(4242)     # the child re-reports after every detach
    check("the re-reported handle is NOT re-embedded while floating",
          embeds == [] and host._floating, str(embeds))
    check("the card keeps the 'in its own window' note",
          host._view_stack.currentWidget() is host._float_box)
    host.on_closed()         # the floating window's own close button
    check("closing the floating window re-attaches",
          not host._floating and link.last('detach')[1:] == ('nat', False))
    host.on_window(4242)
    check("and the handle the child re-reports is embedded again",
          embeds == [4242], str(embeds))

    print("\nV11: a failed embed floats, and closing it does not loop")
    link2 = FakeLink()
    other = View3DHost(link2, 'flt')
    other._has_scene = True
    other._floating = True          # what a failed `_embed` leaves
    other.on_closed()
    check("the window stays floating with the 'closed' note",
          other._floating and 'closed' in other._float_lbl.text()
          and link2.last('detach') is None)
    host.close()
    other.close()
    pump(20)


if __name__ == '__main__':
    main()
