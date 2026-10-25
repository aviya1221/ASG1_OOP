"""Reading the planes file (docs/TESTING.md, section 4.2)."""

import numpy as np
import pytest

from conftest import PROJECT_ROOT
from plane_projection.errors import InputError
from plane_projection.planes import read_planes

HEADER = "Number of Points (3 or 4),x1,y1,z1,x2,y2,z2,x3,y3,z3,x4,y4,z4"
TRIANGLE = "3,127.5,0,65,0,255,65,255,255,65,,,"
TRAPEZOID = "4,60,40,20,20,200,110,190,40,20,230,200,110"     # a', b, a'', c


def test_triangle_and_trapezoid_points_in_order(write_csv):
    """FR-10, FR-12: the trapezoid line a', b, a'', c is kept as a', a'', b, c"""
    triangle, trapezoid = read_planes(write_csv(TRIANGLE, TRAPEZOID))
    assert len(triangle.points) == 3 and len(trapezoid.points) == 4
    assert np.array_equal(triangle.points[0], [127.5, 0, 65])
    assert np.array_equal(triangle.points[1], [0, 255, 65])
    assert np.array_equal(triangle.points[2], [255, 255, 65])
    assert [list(point) for point in trapezoid.points] == [[60, 40, 20], [190, 40, 20], [20, 200, 110], [230, 200, 110]]
    assert not triangle.is_trapezoid and trapezoid.is_trapezoid


def test_triangle_without_the_empty_fields(write_csv):
    """FR-10, FR-12: the empty fields of the fourth point may be left out"""
    short, padded = read_planes(write_csv(TRIANGLE.rstrip(","), TRIANGLE))
    assert np.array_equal(np.concatenate(short.points), np.concatenate(padded.points))


def test_number_formats_and_spaces(write_csv):
    """FR-10"""
    (plane,) = read_planes(write_csv("  3 , 1 , 2.5,-3e2,\t4,5 ,6,7,8,  9  , , ,"))
    assert np.array_equal(np.concatenate(plane.points), [1, 2.5, -300, 4, 5, 6, 7, 8, 9])


def test_blank_lines_and_comments_are_skipped_but_counted(write_csv):
    """FR-11, FR-27"""
    planes = read_planes(write_csv("# first", TRIANGLE, "", "   ", "  # indented comment", TRAPEZOID))
    assert [(p.line, p.frame) for p in planes] == [(2, 1), (6, 2)]


def test_header_on_first_line_is_skipped(write_csv):
    """FR-11"""
    planes = read_planes(write_csv(HEADER, TRIANGLE))
    assert [(p.line, p.frame) for p in planes] == [(2, 1)]
    assert planes[0].readable


def test_first_line_with_empty_fields_is_a_plane(write_csv):
    """FR-11: the empty fields of a triangle do not make a header"""
    (plane,) = read_planes(write_csv(TRIANGLE))
    assert (plane.line, plane.readable) == (1, True)


def test_header_on_second_line_is_a_bad_plane(write_csv):
    """FR-11, FR-24"""
    planes = read_planes(write_csv(TRIANGLE, HEADER))
    assert planes[1].points is None
    assert not planes[1].readable
    assert "field 1 is not a number" in planes[1].reason


def test_the_lecturer_example():
    """FR-10 to FR-12: the example file the lecturer shared, read as it is"""
    planes = read_planes(PROJECT_ROOT / "demo" / "lecturer_example.csv")
    assert [(p.line, len(p.points)) for p in planes] == [(2, 3), (3, 4), (4, 3), (5, 4)]
    assert [list(point) for point in planes[0].points] == [[200, 200, 0], [0, 200, 400], [400, 200, 400]]
    a1, a2, b, c = planes[3].points
    assert [list(a1), list(a2), list(b), list(c)] == [[200, 50, 0], [200, 350, 0], [200, 0, 500], [200, 400, 500]]
    assert np.linalg.norm(b - a1) == np.linalg.norm(c - a2)        # the legs of an isosceles trapezoid


@pytest.mark.parametrize("count", ["0", "2", "5", "3.5", "-3", "1e300"])
def test_wrong_number_of_points_is_a_bad_plane(write_csv, count):
    """FR-12, FR-24"""
    (plane,) = read_planes(write_csv(",".join([count] + ["1"] * 9)))
    assert plane.points is None
    assert f"the number of points is {count}," in plane.reason


@pytest.mark.parametrize("points, numbers", [(3, 8), (3, 12), (4, 9), (4, 11), (4, 13)])
def test_wrong_count_of_numbers_is_a_bad_plane(write_csv, points, numbers):
    """FR-12, FR-24"""
    (plane,) = read_planes(write_csv(",".join([str(points)] + ["1"] * numbers + [""] * 3)))
    assert plane.points is None
    assert f"{numbers} numbers for {points} points instead of {3 * points}" in plane.reason


@pytest.mark.parametrize("field, words", [("abc", "not a number"), ("", "empty"),
                                          ("nan", "finite"), ("inf", "finite"), ("-inf", "finite")])
def test_fields_that_are_not_numbers_are_bad_planes(write_csv, field, words):
    """FR-24"""
    # a good line comes first, since on line 1 a field that is not a number makes a header
    _, plane = read_planes(write_csv(TRIANGLE, f"3,1,2,3,4,{field},6,7,8,9"))
    assert plane.points is None
    assert words in plane.reason
    assert "field 6" in plane.reason


def test_line_of_commas_is_a_bad_plane(write_csv):
    """FR-24"""
    _, plane = read_planes(write_csv(TRIANGLE, ",,,,"))
    assert plane.points is None
    assert "field 1 is empty" in plane.reason


def test_bad_line_among_good_ones_keeps_numbering(write_csv):
    """FR-23, FR-27"""
    planes = read_planes(write_csv(TRIANGLE, "3,1,2,3", TRAPEZOID, "", TRIANGLE))
    assert [(p.line, p.frame, p.readable) for p in planes] == [
        (1, 1, True), (2, 2, False), (3, 3, True), (5, 4, True)]


@pytest.mark.parametrize("lines", [(), (HEADER, "# nothing else", "")])
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
