"""Reading the planes file (docs/TESTING.md, section 4.2)."""

import numpy as np
import pytest

from plane_projection.errors import InputError
from plane_projection.planes import read_planes

TRIANGLE = "127.5,0,65, 0,255,65, 255,255,65"
TRAPEZOID = "60,40,20, 190,40,20, 20,200,110, 230,200,110"


def test_triangle_and_trapezoid_points_in_order(write_csv):
    """FR-10, FR-12"""
    triangle, trapezoid = read_planes(write_csv(TRIANGLE, TRAPEZOID))
    assert len(triangle.points) == 3 and len(trapezoid.points) == 4
    assert np.array_equal(triangle.points[0], [127.5, 0, 65])
    assert np.array_equal(triangle.points[2], [255, 255, 65])
    assert np.array_equal(trapezoid.points[1], [190, 40, 20])
    assert np.array_equal(trapezoid.points[3], [230, 200, 110])
    assert not triangle.is_trapezoid and trapezoid.is_trapezoid


def test_number_formats_and_spaces(write_csv):
    """FR-10"""
    (plane,) = read_planes(write_csv("  1 , 2.5,-3e2,\t4,5 ,6,7,8,  9  "))
    assert np.array_equal(np.concatenate(plane.points), [1, 2.5, -300, 4, 5, 6, 7, 8, 9])


def test_blank_lines_and_comments_are_skipped_but_counted(write_csv):
    """FR-11, FR-27"""
    planes = read_planes(write_csv("# first", TRIANGLE, "", "   ", "  # indented comment", TRAPEZOID))
    assert [(p.line, p.frame) for p in planes] == [(2, 1), (6, 2)]


def test_header_on_first_line_is_skipped(write_csv):
    """FR-11"""
    planes = read_planes(write_csv("ax,ay,az,bx,by,bz,cx,cy,cz", TRIANGLE))
    assert [(p.line, p.frame) for p in planes] == [(2, 1)]
    assert planes[0].readable


def test_header_on_second_line_is_a_bad_plane(write_csv):
    """FR-11, FR-24"""
    planes = read_planes(write_csv(TRIANGLE, "ax,ay,az,bx,by,bz,cx,cy,cz"))
    assert planes[1].points is None
    assert not planes[1].readable
    assert "not a number" in planes[1].reason


@pytest.mark.parametrize("count", [8, 10, 13])
def test_wrong_count_is_a_bad_plane(write_csv, count):
    """FR-24"""
    (plane,) = read_planes(write_csv(",".join(["1"] * count)))
    assert plane.points is None
    assert str(count) in plane.reason


@pytest.mark.parametrize("field, words", [("abc", "not a number"), ("", "empty"),
                                          ("nan", "finite"), ("inf", "finite"), ("-inf", "finite")])
def test_fields_that_are_not_numbers_are_bad_planes(write_csv, field, words):
    """FR-24"""
    # a good line comes first, since on line 1 a field that is not a number makes a header
    _, plane = read_planes(write_csv(TRIANGLE, f"1,2,3,4,{field},6,7,8,9"))
    assert plane.points is None
    assert words in plane.reason
    assert "field 5" in plane.reason


def test_bad_line_among_good_ones_keeps_numbering(write_csv):
    """FR-23, FR-27"""
    planes = read_planes(write_csv(TRIANGLE, "1,2,3", TRAPEZOID, "", TRIANGLE))
    assert [(p.line, p.frame, p.readable) for p in planes] == [
        (1, 1, True), (2, 2, False), (3, 3, True), (5, 4, True)]


@pytest.mark.parametrize("lines", [(), ("ax,ay,az,bx,by,bz,cx,cy,cz", "# nothing else", "")])
def test_file_without_planes_is_fatal(write_csv, lines):
    """FR-4, FR-14"""
    path = write_csv(*lines)
    with pytest.raises(InputError) as error:
        read_planes(path)
    assert error.value.path == str(path)
    assert "no planes" in error.value.cause


def test_missing_file_is_fatal(tmp_path):
    """FR-4"""
    path = tmp_path / "missing.csv"
    with pytest.raises(InputError) as error:
        read_planes(path)
    assert error.value.path == str(path)
