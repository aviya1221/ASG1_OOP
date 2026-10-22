"""Frame size, gray levels and placement (docs/TESTING.md, section 4.5)."""

import numpy as np
import pytest

from plane_projection.frames import EMPTY_SIZE, GrayMap, frame_size, place
from plane_projection.geometry import PlaneSetup
from plane_projection.planes import Plane

PLANE = Plane(line=1, frame=1, points=None)


def formula(v, lo, hi):
    """FR-32, in exact integer arithmetic: floor(255·(v − lo)/(hi − lo) + 0.5), clipped to 0 … 255."""
    gray = (510 * (v - lo) + (hi - lo)) // (2 * (hi - lo))
    return min(max(gray, 0), 255)


def test_frame_size_is_the_largest_plane_rounded_up_to_even():
    """FR-30"""
    setups = [PlaneSetup(PLANE, cols=101, rows=57), PlaneSetup(PLANE, cols=80, rows=90),
              PlaneSetup(PLANE, reason="bad")]
    assert frame_size(setups) == (102, 90)


def test_frame_size_without_valid_planes():
    """FR-30"""
    assert frame_size([PlaneSetup(PLANE, reason="bad")]) == EMPTY_SIZE == (64, 64)


def test_image_is_placed_in_the_middle():
    """FR-31"""
    frame = np.full((6, 8), 99, dtype=np.uint8)
    image = np.arange(1, 16, dtype=np.uint8).reshape(3, 5)
    place(image, frame)
    assert np.array_equal(frame[1:4, 1:6], image)
    frame[1:4, 1:6] = 0
    assert not frame.any()


def test_missing_image_gives_a_black_frame():
    """FR-24, FR-31"""
    frame = np.full((6, 8), 99, dtype=np.uint8)
    assert not place(None, frame).any()


def test_gray_levels_of_8_bits():
    """FR-32"""
    gray = GrayMap(0, 200, np.dtype(np.uint8))
    assert gray(np.array([[0, 100, 200]], dtype=np.uint8)).tolist() == [[0, 128, 255]]


@pytest.mark.parametrize("dtype, lo, hi", [(np.uint16, 0, 65535), (np.uint16, 300, 4100),
                                           (np.int16, 0, 279), (np.uint8, 0, 255)])
def test_table_gives_the_formula_for_every_value(dtype, lo, hi):
    """FR-32"""
    values = np.arange(0, hi + 1).astype(dtype)
    expected = [formula(int(v), lo, hi) for v in values]
    assert GrayMap(lo, hi, np.dtype(dtype))(values).tolist() == expected


def test_32_bit_values_give_the_formula():
    """FR-32"""
    lo, hi = 1000, 4_000_000_000
    values = np.array([0, 1000, 1001, 2_000_000_500, 3_999_999_999, 4_000_000_000, 7_843_138, 7_843_137 + 1000],
                      dtype=np.uint32)
    assert GrayMap(lo, hi, np.dtype(np.uint32))(values).tolist() == [formula(int(v), lo, hi) for v in values]


def test_zero_stays_black_when_lo_is_above_zero():
    """FR-32"""
    gray = GrayMap(50, 150, np.dtype(np.uint8))
    assert gray(np.array([0, 50, 150], dtype=np.uint8)).tolist() == [0, 0, 255]


@pytest.mark.parametrize("dtype", [np.uint8, np.uint32])
def test_all_values_equal(dtype):
    """FR-32: values above 0 are white, 0 is black"""
    gray = GrayMap(7, 7, np.dtype(dtype))
    assert gray(np.array([0, 7], dtype=dtype)).tolist() == [0, 255]


@pytest.mark.parametrize("dtype", [np.uint8, np.uint16, np.uint32, np.int16])
def test_gray_levels_are_bytes(dtype):
    """FR-32"""
    assert GrayMap(0, 100, np.dtype(dtype))(np.zeros((2, 3), dtype=dtype)).dtype == np.uint8
