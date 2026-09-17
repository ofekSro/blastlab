"""Three 3D surfaces, one viewer child.

`setup`, `run` and `results` each own one render window inside the same
viewer process, and the Setup preview makes that ownership part of
EDITING, not just of running. So the claim / release choreography is the
likeliest source of a dangling HWND, and this suite pins it:

- one host per surface registers with the same link, and each is
  addressed by its own surface name in every message
- a surface claims the child's window only while its tab is visible, and
  releases it when another tab comes up
- detaching moves the container to a floating window and re-attaching
  brings it back, without ever re-parenting the FOREIGN window twice
  (that combination is an access violation, not an exception)
- shutting the hosts down in any order leaves nothing holding a window

Headless, with a fake link: no viewer child is spawned, so this runs
anywhere. The real child is exercised by `_e2e_ui_view3d.py`.

Run:  cd blastlab/tests && python test_ui_three_surfaces.py
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
sys.path.insert(0, HERE)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('MPLBACKEND', 'Agg')
os.environ.setdefault('BLASTLAB_SETTINGS',
                      os.path.join(tempfile.mkdtemp(prefix='blastlab_3s_'),
                                   'settings.json'))

from blastlab.ui.testing import ensure_qapp, pump            # noqa: E402

FAIL = []
RAN = []


def check(name, ok, detail=''):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
          + (f' - {detail}' if detail else ''))
    RAN.append(name)
    if not ok:
        FAIL.append(name)


def main():
    ensure_qapp()
    from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget
    from test_ui_view3d_host import FakeLink, scene_info
    from blastlab.ui.view3d_host import View3DHost, make_ring
    from blastlab.viz3d.feed import Feed3D

    link = FakeLink()
    # a tab stack, as the main window has: only one page is ever visible
    stack = QStackedWidget()
    hosts = {}
    for surface in ('setup', 'run', 'results'):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        hosts[surface] = View3DHost(link, surface, log_fn=lambda _s: None)
        lay.addWidget(hosts[surface])
        stack.addWidget(page)
    stack.resize(1100, 720)
    stack.show()
    pump(50)

    print('\nS1: three hosts, one link, three names')
    check('each surface registered itself once',
          sorted(link.hosts) == ['results', 'run', 'setup'],
          str(sorted(link.hosts)))
    check('and the link kept the host object, not a copy',
          all(link.hosts[s] is hosts[s] for s in hosts))
    check('no scene anywhere yet',
          not any(h.has_scene for h in hosts.values()))
    check('the placeholder says where a scene comes from',
          'Results tab' in View3DHost.PLACEHOLDER)

    print('\nS2: every message carries its own surface')
    ring_keep = []
    for surface, host in hosts.items():
        n0 = len(link.sent)
        info = scene_info()
        feed = Feed3D(info)
        ring = make_ring(feed, info)
        ring_keep.append(ring)
        ok = host.adopt_feed(feed, ring)
        check(f'{surface}: a scene attaches', ok and host.has_scene)
        mine = [m for m in link.sent[n0:] if len(m) > 1]
        check(f'{surface}: every message names it, none of the others',
              mine and all(m[1] == surface for m in mine),
              str({m[1] for m in mine}))

    print('\nS3: a scene claims the window only from a visible tab')
    # page 0 ('setup') is the one on screen, so only that host's scene
    # asked for the window during S2
    first = [m for m in link.sent if m[0] == 'claim']
    check('only the visible surface claimed it',
          {m[1] for m in first} == {'setup'}, str([m[1] for m in first]))
    n0 = len(link.sent)
    stack.setCurrentIndex(1)
    pump(40)
    rel = [m for m in link.sent[n0:] if m[0] == 'release']
    check('leaving a surface with a scene releases the window',
          [m[1] for m in rel] == ['setup'], str(rel))
    check('a claim needs a container to point at, so none yet',
          not [m for m in link.sent[n0:] if m[0] == 'claim'],
          'on_window is what closes this gap in the real app')

    # QWindow.fromWinId cannot wrap a window under the offscreen
    # platform (winId is 1 and fromWinId returns None), so the real
    # embedding is _e2e_ui_view3d's job. What matters HERE is the
    # parenting dance, which works the same with an ordinary widget
    # standing in for the foreign container.
    for surface, host in hosts.items():
        host._container = QWidget()
        host._view_stack.addWidget(host._container)
    n0 = len(link.sent)
    stack.setCurrentIndex(0)
    pump(40)
    claims = [m for m in link.sent[n0:] if m[0] == 'claim']
    check('with a container, showing the tab claims the window',
          [m[1] for m in claims] == ['setup'], str(claims))
    for i, surface in enumerate(('run', 'results')):
        n0 = len(link.sent)
        stack.setCurrentIndex(i + 1)
        pump(40)
        claims = [m for m in link.sent[n0:] if m[0] == 'claim']
        rel = [m for m in link.sent[n0:] if m[0] == 'release']
        prev = ('setup', 'run')[i]
        check(f'{surface} claims it and only it',
              {m[1] for m in claims} == {surface}, str(claims))
        check(f'{prev} hands it back at the same time',
              {m[1] for m in rel} == {prev}, str(rel))

    print('\nS4: detach and re-attach move the container, never the '
          'foreign window')
    host = hosts['results']
    stack.setCurrentIndex(2)
    pump(40)
    container = host._container
    n0 = len(link.sent)
    host.set_floating(True)
    pump(40)
    check('the container went to a floating window',
          host._floating and host._float_win is not None,
          f'floating={host._floating} win={host._float_win is not None}')
    check('and it is the SAME container, not a new one',
          host._container is container,
          'a foreign window may never be re-parented twice')
    check('the float window took it as its child',
          container.parent() is not None
          and container.parent() is not host)
    # the child is deliberately NOT told: its window never left the
    # container, which only moved inside this process. A 'detach' goes
    # out only when there is no container to carry it, i.e. embedding
    # failed and the child must put its own window on screen.
    check('the child is not told - nothing changed for it',
          not [m for m in link.sent[n0:] if m[0] == 'detach'],
          str([m[0] for m in link.sent[n0:]]))
    check('but it is pointed at the container again',
          any(m[0] == 'claim' and m[1] == 'results'
              for m in link.sent[n0:]),
          str([m[0] for m in link.sent[n0:]]))
    check('and Detach is no longer offered while it is out',
          not host.detach_btn.isEnabled())
    host.set_floating(False)
    pump(40)
    check('re-attaching brings the same container back to the tab',
          not host._floating and host._container is container)
    check('the float window let go', host._float_win is None
          or not host._float_win.isVisible())
    check('and Detach is offered again', host.detach_btn.isEnabled())
    check('setting the state it is already in does nothing',
          (host.set_floating(False) or True) and not host._floating)

    print('\nS5: shutdown in any order leaves nothing holding a window')
    order = ('run', 'results', 'setup')
    for surface in order:
        h = hosts[surface]
        h.shutdown()
        check(f'{surface}: no scene, no ring, no container',
              not h.has_scene and h._ring is None
              and h._container is None,
              f'scene={h.has_scene} ring={h._ring is not None} '
              f'container={h._container is not None}')
    pump(40)
    check('no host is floating',
          not any(h._floating for h in hosts.values()))
    check('shutting one down twice is harmless',
          (hosts['run'].shutdown() or True))
    for ring in ring_keep:
        try:
            ring.close(unlink=True)
        except Exception:
            pass

    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} of {len(RAN)} check(s): {FAIL}')
        sys.exit(1)
    print(f'UI THREE SURFACES: PASS ({len(RAN)} checks)')


if __name__ == '__main__':
    main()
