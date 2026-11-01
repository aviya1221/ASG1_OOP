"""The loop from planes to frames (docs/TESTING.md, section 4.6)."""

import numpy as np

from conftest import CAKE_IMAGE, CAKE_TRIANGLE, assert_same, cake
from plane_projection.planes import Plane
from plane_projection.projector import Projector
from plane_projection.video import render
from plane_projection.video.frames import GrayMap, error_frame, place
from plane_projection.video.render import INTERNAL, Renderer, safe_setup
from plane_projection.volume import Volume

GOOD = Plane(line=2, frame=1, points=tuple(np.array(p, dtype=np.float64) for p in CAKE_TRIANGLE))
BAD = Plane(line=3, frame=2, points=tuple(np.array(p, dtype=np.float64) for p in ((0, 0, 0), (1, 1, 1), (2, 2, 2))))


def test_valid_plane_is_drawn_in_the_middle_and_bad_plane_as_an_error_frame():
    """FR-24b, FR-30 to FR-32"""
    volume = Volume(cake())
    good, bad = safe_setup(GOOD), safe_setup(BAD)
    with Renderer(volume, [good, bad]) as renderer:
        assert (renderer.width, renderer.height) == (10, 12)
        drawn = renderer.draw(good)
        assert drawn.setup is good
        assert_same(drawn.image, CAKE_IMAGE)
        assert_same(drawn.frame, place(GrayMap(volume.lo, volume.hi, volume.dtype)(CAKE_IMAGE), np.zeros((12, 10), np.uint8)))
        drawn = renderer.draw(bad)
        assert drawn.setup is bad and drawn.image is None
        assert_same(drawn.frame, error_frame(bad, np.zeros((12, 10), np.uint8)))


def test_every_frame_is_drawn_into_one_buffer():
    """NFR-6"""
    setups = [safe_setup(GOOD), safe_setup(BAD)]
    with Renderer(Volume(cake()), setups) as renderer:
        assert all(renderer.draw(setup).frame is renderer.frame for setup in setups)


def test_failed_projection_gives_an_error_frame(monkeypatch):
    """FR-24c, NFR-8"""
    def failing(self, setup):
        raise RuntimeError("something unexpected")

    monkeypatch.setattr(Projector, "project", failing)
    good = safe_setup(GOOD)
    with Renderer(Volume(cake()), [good]) as renderer:
        drawn = renderer.draw(good)
    assert drawn.image is None
    assert drawn.setup.plane is GOOD
    assert (drawn.setup.reason, drawn.setup.title) == ("internal error while projecting (something unexpected)", INTERNAL)
    assert_same(drawn.frame, error_frame(drawn.setup, np.zeros((12, 10), np.uint8)))


def test_failed_setup_gives_a_bad_plane(monkeypatch):
    """FR-24c, NFR-8"""
    def failing(plane):
        raise ZeroDivisionError("division by zero")

    monkeypatch.setattr(render, "plane_setup", failing)
    setup = safe_setup(GOOD)
    assert (setup.reason, setup.title) == ("internal error in the setup (division by zero)", INTERNAL)


def test_projection_time_is_counted():
    """NFR-3"""
    good = safe_setup(GOOD)
    with Renderer(Volume(cake()), [good]) as renderer:
        renderer.draw(good)
        assert renderer.projection > 0
