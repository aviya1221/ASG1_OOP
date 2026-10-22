"""Plane setup and checks (docs/TESTING.md, section 4.3)."""

import math
import warnings

import numpy as np
import pytest

from conftest import CAKE_TRIANGLE
from plane_projection.geometry import MAX_SIDE, plane_setup
from plane_projection.planes import Plane
from reference import Reference, random_plane


def setup_of(*points):
    return plane_setup(Plane(line=1, frame=1, points=tuple(np.array(p, dtype=np.float64) for p in points)))


def spans(setup):
    return [(int(a), int(b)) for a, b in zip(setup.c0, setup.c1)]


# trapezoids around the base b = (-2, 20, 0), c = (12, 20, 0): right = (1, 0, 0) and down = (0, 1, 0)
B, C = (-2, 20, 0), (12, 20, 0)


def test_worked_example():
    """FR-15 to FR-17, and the row spans of docs/ALGORITHM.md, section 5.3"""
    setup = setup_of(*CAKE_TRIANGLE)
    assert setup.valid and not setup.warnings
    assert np.allclose(setup.right, (1, 0, 0))
    assert np.allclose(setup.down, (0, 0.6, -0.8))
    assert np.allclose(setup.corner, (1, 0, 8))
    assert (setup.rows, setup.cols) == (11, 9)
    assert spans(setup) == [(4, 4), (4, 4), (4, 4), (3, 5), (3, 5), (2, 6), (2, 6), (2, 6), (1, 7), (1, 7), (0, 8)]


def test_swapping_b_and_c_mirrors_the_image():
    """FR-21"""
    a, b, c = CAKE_TRIANGLE
    setup, mirrored = setup_of(a, b, c), setup_of(a, c, b)
    assert np.allclose(mirrored.right, -setup.right)
    assert (mirrored.rows, mirrored.cols) == (setup.rows, setup.cols)
    assert spans(mirrored) == [(setup.cols - 1 - hi, setup.cols - 1 - lo) for lo, hi in spans(setup)]


def test_rectangle_spans_every_column():
    """FR-16, FR-18"""
    setup = setup_of((0, 0, 5), (19, 0, 5), (0, 9, 5), (19, 9, 5))
    assert (setup.rows, setup.cols) == (10, 20)
    assert spans(setup) == [(0, 19)] * 10


def test_apex_is_in_row_0_at_its_own_column():
    """FR-21"""
    setup = setup_of((3, 0, 0), (0, 10, 0), (12, 10, 0))
    assert setup.c0[0] == setup.c1[0] == 3
    assert setup.c0[-1] == 0 and setup.c1[-1] == 12


def test_rounding_error_in_a_length_is_forgiven():
    """FR-16"""
    setup = setup_of((4, 0, 0), (0, 5, 0), (7.9999999, 5, 0))
    assert setup.cols == 9


def test_same_b_and_c_is_bad():
    """FR-24"""
    setup = setup_of((0, 0, 0), (3, 4, 5), (3, 4, 5))
    assert not setup.valid
    assert "same point" in setup.reason


@pytest.mark.parametrize("points", [[(0, 0, 0), (1, 1, 1), (3, 3, 3)],
                                    [(0, 0, 0), (2, 0, 0), (1, 0, 0), (3, 0, 0)]])
def test_points_on_one_line_are_bad(points):
    """FR-24"""
    setup = setup_of(*points)
    assert not setup.valid
    assert "one line" in setup.reason


@pytest.mark.parametrize("off, valid", [(0.6, False), (0.4, True)])
def test_trapezoid_must_be_flat(off, valid):
    """FR-24"""
    setup = setup_of((0, 0, 0), (10, 0, off), B, C)
    assert setup.valid == valid
    if not valid:
        assert "off the plane" in setup.reason


def test_crossed_trapezoid_is_bad():
    """FR-24"""
    setup = setup_of((10, 0, 0), (0, 0, 0), B, C)
    assert not setup.valid
    assert "cross" in setup.reason


def test_trapezoid_with_one_top_point_is_the_triangle():
    """FR-24"""
    trapezoid = setup_of((5, 0, 0), (5, 0, 0), B, C)
    triangle = setup_of((5, 0, 0), B, C)
    assert trapezoid.valid
    assert spans(trapezoid) == spans(triangle)
    assert np.allclose(trapezoid.corner, triangle.corner)


@pytest.mark.parametrize("base, valid", [(MAX_SIDE - 1, True), (MAX_SIDE, False)])
def test_size_limit(base, valid):
    """FR-24"""
    setup = setup_of((base / 2, 0, 0), (0, 10, 0), (base, 10, 0))
    assert setup.valid == valid
    if valid:
        assert setup.cols == MAX_SIDE
    else:
        assert str(MAX_SIDE) in setup.reason


def test_far_points_are_bad_without_numpy_warnings():
    """FR-24, NFR-8"""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        setup = setup_of((1e300, 0, 0), (-1e300, 5, 0), (1e300, 5, 7))
    assert not setup.valid


@pytest.mark.parametrize("difference, warned", [(0.6, True), (0.4, False)])
def test_unequal_legs_give_a_warning(difference, warned):
    """FR-25: legs of 10 and 10 + difference"""
    d = math.sqrt((10 + difference) ** 2 - 100)
    setup = setup_of((0, 0, 0), (0, 10, 0), (d, 10, 0))
    assert setup.valid
    assert any("legs" in w for w in setup.warnings) == warned


@pytest.mark.parametrize("tilt, warned", [(0.6, True), (0.4, False)])
def test_tilted_top_side_gives_a_warning(tilt, warned):
    """FR-25"""
    setup = setup_of((0, 0, 0), (10, tilt, 0), B, C)
    assert setup.valid
    assert any("parallel" in w for w in setup.warnings) == warned


def test_plane_that_could_not_be_read_stays_bad():
    """FR-24"""
    setup = plane_setup(Plane(line=4, frame=3, points=None, reason="field 2 is empty"))
    assert not setup.valid
    assert setup.reason == "field 2 is empty"


def test_row_spans_agree_with_the_reference():
    """FR-18: 1000 random triangles and trapezoids"""
    rng = np.random.default_rng(1)
    checked = 0
    for _ in range(1000):
        points = random_plane(rng, (40, 30, 20))
        setup, reference = setup_of(*points), Reference(points)
        assert (setup.rows, setup.cols) == (reference.rows, reference.cols)
        for row in range(setup.rows):
            for col in range(setup.cols):
                if not reference.near_edge(row, col):
                    assert (setup.c0[row] <= col <= setup.c1[row]) == reference.inside(row, col)
                    checked += 1
    assert checked > 100000
