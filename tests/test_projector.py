"""The projection (docs/TESTING.md, section 4.4)."""

import math
import warnings

import numpy as np
import pytest
from scipy import ndimage

from conftest import CAKE_IMAGE, CAKE_TRIANGLE, DATA, cake, decode, index_volume
from plane_projection.geometry import plane_setup
from plane_projection.planes import Plane
from plane_projection.projector import Projector
from plane_projection.volume import Volume, read_volume
from reference import Reference, random_plane


def setup_of(*points):
    return plane_setup(Plane(line=1, frame=1, points=tuple(np.array(p, dtype=np.float64) for p in points)))


def project(data, *points, threads=1):
    with Projector(Volume(data), threads=threads) as projector:
        return projector.project(setup_of(*points))


def rectangle(origin, right, down):
    """A rectangle written as a trapezoid: a', a'' along right, b and c one step of down below them."""
    o, r, d = (np.array(v, dtype=np.float64) for v in (origin, right, down))
    return o, o + r, o + d, o + r + d


def test_worked_example():
    """FR-17 to FR-21: the image of docs/SRS.md, section 3.4"""
    image = project(cake(), *CAKE_TRIANGLE)
    assert image.dtype == np.uint8
    assert np.array_equal(image, CAKE_IMAGE)


@pytest.mark.parametrize("shape", [(1, 1, 1), (1, 5, 7), (9, 1, 4), (12, 12, 12), (40, 30, 20)])
def test_random_planes_agree_with_the_reference(shape):
    """FR-19, FR-20: 200 planes for each volume, 1000 in all, many partly or fully outside"""
    data = index_volume(shape)
    rng = np.random.default_rng(sum(shape))
    with Projector(Volume(data), threads=1) as projector:
        for _ in range(200):
            points = random_plane(rng, shape, max_side=30)
            reference = Reference(points)
            image = projector.project(setup_of(*points))
            expected = reference.project(data)
            differ = image != expected
            for row, col in zip(*np.nonzero(differ)):
                assert reference.near_edge(row, col), (
                    f"pixel {(row, col)} read voxel {decode(image[row, col])}, "
                    f"the reference read {decode(expected[row, col])}")


def test_halves_round_up():
    """FR-19: x = 0.5 + c and z = 2.5 fall exactly between voxels"""
    image = project(index_volume((6, 6, 6)), *rectangle((0.5, 0, 2.5), (3, 0, 0), (0, 3, 0)))
    assert decode(image[0, 0]) == (1, 0, 3)
    assert decode(image[3, 3]) == (4, 3, 3)


@pytest.mark.parametrize("z, inside", [(-0.5, True), (-0.51, False), (4.49, True), (4.5, False)])
def test_edges_of_the_volume(z, inside):
    """FR-20: voxel 0 reaches down to -0.5, voxel 4 up to just below 4.5"""
    data = index_volume((5, 5, 5)) + 1
    image = project(data, *rectangle((0, 0, z), (4, 0, 0), (0, 4, 0)))
    assert (image > 0).all() == inside
    assert (image == 0).all() == (not inside)


def test_plane_that_misses_the_volume():
    """FR-26"""
    image = project(index_volume((5, 5, 5)) + 1, (20, 0, 0), (15, 6, 0), (25, 6, 0))
    assert image.shape == (7, 11)
    assert not image.any()


def test_plane_far_away_gives_zeros_without_numpy_warnings():
    """FR-20, NFR-8"""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        image = project(index_volume((5, 5, 5)) + 1, (1e9, 1e9, 1e9), (1e9 - 5, 1e9 + 9, 1e9), (1e9 + 5, 1e9 + 9, 1e9))
    assert image.shape == (10, 11)
    assert not image.any()


@pytest.mark.parametrize("dtype", [np.uint8, np.uint16, np.uint32, np.int8, np.int16, np.int32])
def test_image_has_the_type_of_the_volume(dtype):
    """FR-6, FR-20"""
    data = np.asfortranarray(np.full((4, 4, 4), 100, dtype=dtype))
    assert project(data, (1.5, 0, 1), (0, 3, 1), (3, 3, 1)).dtype == dtype


def test_32_bit_values_are_kept():
    """FR-6, FR-20"""
    data = np.asfortranarray(np.full((4, 4, 4), 4_000_000_000, dtype=np.uint32))
    assert project(data, (1.5, 0, 1), (0, 3, 1), (3, 3, 1)).max() == 4_000_000_000


def test_number_of_threads_does_not_change_the_image():
    """NFR-9"""
    data = index_volume((60, 50, 40))
    rng = np.random.default_rng(7)
    planes = [random_plane(rng, data.shape, max_side=120) for _ in range(30)]
    images = {}
    for threads in (1, 2, 4, 8):
        with Projector(Volume(data), threads=threads) as projector:
            images[threads] = [projector.project(setup_of(*points)) for points in planes]
    for threads in (2, 4, 8):
        assert all(np.array_equal(a, b) for a, b in zip(images[1], images[threads]))


def test_bad_plane_cannot_be_projected():
    with Projector(Volume(cake())) as projector, pytest.raises(ValueError):
        projector.project(setup_of((0, 0, 0), (1, 1, 1), (2, 2, 2)))


# ----- slow tests on the data set (docs/TESTING.md, sections 3.4 to 3.6)

AXIS_FILES = ["MRHead_1.nrrd", "onion.nrrd", "biscuit_cake.nrrd", "swiss_roll.nrrd", "synthetic/dice.nrrd"]


@pytest.mark.slow
@pytest.mark.parametrize("name", AXIS_FILES)
def test_slices_along_the_axes(name):
    """FR-8, FR-22: images of planes along the axes equal NumPy slices, turned so that rows come first"""
    volume = read_volume(DATA / name)
    data = volume.data
    sx, sy, sz = (n - 1 for n in data.shape)
    x, y, z = (n // 2 for n in data.shape)
    with Projector(volume) as projector:
        cut = lambda *points: projector.project(setup_of(*points))  # noqa: E731
        assert np.array_equal(cut(*rectangle((0, 0, z), (sx, 0, 0), (0, sy, 0))), data[:, :, z].T)
        assert np.array_equal(cut(*rectangle((0, y, 0), (sx, 0, 0), (0, 0, sz))), data[:, y, :].T)
        assert np.array_equal(cut(*rectangle((x, 0, 0), (0, sy, 0), (0, 0, sz))), data[x, :, :].T)


@pytest.fixture(scope="module")
def dice():
    return read_volume(DATA / "synthetic" / "dice.nrrd")


def pips(image):
    return ndimage.label(image == 200000)[1]


@pytest.mark.slow
@pytest.mark.parametrize("points, count", [
    (rectangle((0, 0, 139), (199, 0, 0), (0, 179, 0)), 1),
    (rectangle((0, 0, 20), (199, 0, 0), (0, 179, 0)), 6),
    (rectangle((0, 30, 0), (199, 0, 0), (0, 0, 159)), 4),
])
def test_dice_faces(dice, points, count):
    """FR-19, FR-20: each face is a 120 x 120 square with its own number of pips"""
    with Projector(dice) as projector:
        image = projector.project(setup_of(*points))
    assert np.count_nonzero(image) == 120 * 120
    assert pips(image) == count


def triangle_around(center, normal, radius):
    """An equilateral triangle in the plane through center with this normal, around a circle of the radius."""
    n = np.asarray(normal, dtype=np.float64) / np.linalg.norm(normal)
    right = np.cross(n, (0, 0, 1) if abs(n[2]) < 0.9 else (1, 0, 0))
    right /= np.linalg.norm(right)
    down = np.cross(n, right)
    outer = 2 * radius                      # the corners of the triangle are twice as far as its sides
    c = np.asarray(center, dtype=np.float64)
    apex = c - outer * down
    half = outer * math.sqrt(3) / 2
    return apex, c + outer / 2 * down - half * right, c + outer / 2 * down + half * right


@pytest.mark.slow
@pytest.mark.parametrize("total, side, area, perimeter", [
    (268.5, 60 * math.sqrt(2), 3 * math.sqrt(3) / 2 * (60 * math.sqrt(2)) ** 2, 6 * 60 * math.sqrt(2)),
    (408.5, 40 * math.sqrt(2), math.sqrt(3) / 4 * (40 * math.sqrt(2)) ** 2, 3 * 40 * math.sqrt(2)),
])
def test_dice_diagonal_cuts(dice, total, side, area, perimeter):
    """FR-19, FR-20: the hexagon through the center, and the triangle cut off a corner"""
    center = np.full(3, total / 3)
    with Projector(dice) as projector:
        image = projector.project(setup_of(*triangle_around(center, (1, 1, 1), side * 1.1)))
    assert abs(np.count_nonzero(image) - area) <= perimeter


@pytest.mark.slow
def test_cake_labels():
    """FR-19, FR-20: a horizontal plane in the middle of the ganache layer shows mostly ganache"""
    labels = read_volume(DATA / "synthetic" / "cake_3layers.seg.nrrd")
    sx, sy, _ = (n - 1 for n in labels.shape)
    z = round(41 / 1.3)                     # 41 mm, between 38 and 44 mm
    with Projector(labels) as projector:
        image = projector.project(setup_of(*rectangle((0, 0, z), (sx, 0, 0), (0, sy, 0))))
    found = np.bincount(image[image > 1].ravel())
    assert found.argmax() == 4              # ganache


@pytest.mark.slow
def test_tomato_gel_is_brighter_than_seeds():
    """FR-19, FR-20: the scan and its labels, cut by the same plane through the middle"""
    scan = read_volume(DATA / "synthetic" / "tomato.nrrd")
    labels = read_volume(DATA / "synthetic" / "tomato.seg.nrrd")
    sx, sy, sz = (n - 1 for n in scan.shape)
    points = rectangle((0, 0, sz // 2), (sx, 0, 0), (0, sy, 0))
    with Projector(scan) as scan_projector, Projector(labels) as label_projector:
        values = scan_projector.project(setup_of(*points)).astype(np.float64)
        material = label_projector.project(setup_of(*points))
    gel, seed = material == 6, material == 7
    assert gel.any() and seed.any()
    assert values[gel].mean() > values[seed].mean()
