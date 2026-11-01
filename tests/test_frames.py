"""Frame size, gray levels, placement and error frames (docs/TESTING.md, section 4.5)."""

import numpy as np
import pytest

from plane_projection import font
from plane_projection.frames import (EMPTY_SIZE, ERROR_BORDER, ERROR_GRAY, ERROR_TEXT, GrayMap, error_frame,
                                     frame_size, place)
from plane_projection.geometry import PlaneSetup
from plane_projection.planes import Plane

PLANE = Plane(line=1, frame=1, points=None)
BAD = PlaneSetup(Plane(line=35, frame=9, points=None), reason="9 numbers for 4 points instead of 12",
                 title="WRONG NUMBER OF VALUES")
TITLES = ["WRONG NUMBER OF POINTS", "WRONG NUMBER OF VALUES", "NOT A NUMBER", "B AND C ARE THE SAME POINT",
          "POINTS ON ONE LINE", "TRAPEZOID NOT FLAT", "TRAPEZOID SIDES CROSS", "IMAGE TOO LARGE", "INTERNAL ERROR"]


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


def read_text(frame: np.ndarray) -> list[tuple[str, int]]:
    """The lines of text of an error frame, with their scales, read back from the pixels with the font.

    Every band of rows with text pixels is one line. Its scale is its height over 7, and its text is the one,
    among all lengths of a line centered in the frame, whose glyphs drawn again give exactly the pixels of the band.
    """
    ink = frame == ERROR_TEXT
    rows = np.flatnonzero(ink.any(axis=1))
    lines = []
    for band in np.split(rows, np.flatnonzero(np.diff(rows) > 1) + 1) if len(rows) else []:
        scale = len(band) // font.HEIGHT
        strip = ink[band[0]:band[-1] + 1]
        for length in range(1, frame.shape[1] // ((font.WIDTH + 1) * scale) + 1):
            left = (frame.shape[1] - font.text_width("x" * length, scale)) // 2
            cells = [strip[::scale, left + i * (font.WIDTH + 1) * scale:][:, :font.WIDTH * scale:scale]
                     for i in range(length)]
            text = "".join(next((char for char, bitmap in font.BITMAPS.items()
                                 if cell.shape == bitmap.shape and (cell == bitmap).all()), "?") for cell in cells)
            drawn = np.zeros_like(strip)
            drawn[:, left:left + font.text_width(text, scale)] = font.render(text, scale)
            if "?" not in text and (drawn == strip).all():
                lines.append((text, scale))
                break
        else:
            lines.append(("?", scale))
    return lines


def test_error_frame_shows_the_frame_the_line_and_the_cause():
    """FR-24b: the word ERROR larger than the rest, then the frame, the line and the short cause, wrapped"""
    lines = read_text(error_frame(BAD, np.zeros((244, 282), dtype=np.uint8)))
    assert [text for text, _ in lines] == ["ERROR", "FRAME 9", "LINE 35", "WRONG NUMBER", "OF VALUES"]
    assert lines[0][1] > lines[1][1] == lines[-1][1]


def test_error_frame_is_gray_in_a_border():
    """FR-24b: no pixel is black"""
    frame = error_frame(BAD, np.zeros((244, 282), dtype=np.uint8))
    assert set(np.unique(frame)) == {ERROR_GRAY, ERROR_BORDER, ERROR_TEXT}
    assert (frame[0] == ERROR_BORDER).all() and (frame[-1] == ERROR_BORDER).all()
    assert (frame[:, 0] == ERROR_BORDER).all() and (frame[:, -1] == ERROR_BORDER).all()


def test_error_frame_covers_an_image_drawn_before():
    """FR-24b: one frame buffer serves every frame"""
    frame = np.full((244, 282), 7, dtype=np.uint8)
    assert 7 not in error_frame(BAD, frame)


@pytest.mark.parametrize("size, expected", [((64, 64), ["ERROR", "FRAME 9", "LINE 35", "WRONG", "NUMBER OF", "VALUES"]),
                                            ((60, 50), ["ERROR", "FRAME 9", "LINE 35"]),
                                            ((40, 30), ["ERROR"]),
                                            ((22, 20), [])])
def test_error_frame_in_small_frames(size, expected):
    """FR-24b: the cause is left out whole when it does not fit, then the lines from the bottom, then all the text"""
    width, height = size
    frame = error_frame(BAD, np.zeros((height, width), dtype=np.uint8))
    if expected:
        assert [text for text, _ in read_text(frame)] == expected
    else:                                           # a large X instead of the text
        assert frame[height // 2, width // 2] == ERROR_TEXT and frame[3, 3] == ERROR_TEXT


@pytest.mark.parametrize("width, height", [(2, 2), (4, 2), (2, 4096), (4096, 4096)])
def test_error_frame_of_any_size(width, height):
    """FR-24b, NFR-8"""
    frame = error_frame(BAD, np.zeros((height, width), dtype=np.uint8))
    assert frame.min() >= ERROR_GRAY


@pytest.mark.parametrize("title", TITLES)
def test_every_short_cause_can_be_drawn(title):
    """FR-24b"""
    setup = PlaneSetup(Plane(line=1234, frame=1200, points=None), reason="bad", title=title)
    lines = read_text(error_frame(setup, np.zeros((256, 256), dtype=np.uint8)))
    assert " ".join(text for text, _ in lines[3:]) == title


def test_glyphs_are_5_by_7():
    assert all(bitmap.shape == (font.HEIGHT, font.WIDTH) for bitmap in font.BITMAPS.values())
    assert font.render("AB", 3).shape == (21, 33)


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
