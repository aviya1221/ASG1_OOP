"""Generate the synthetic NRRD volumes used to test the plane-projection algorithm.

Three volumes with known geometry (full spec in DATA/README.md):

    cake_3layers.nrrd   uint8    three-layer cake with a ball in the center
    tomato.nrrd         uint16   tomato with skin, five chambers and seeds
    dice.nrrd           uint32   game die with a different number of pips per face

Every volume is indexed vol[x, y, z], like M[x][y][z] in the assignment, and is
saved on a 1 mm LPS grid with origin (0, 0, 0), so the IJK index that 3D Slicer
shows is exactly (x, y, z).

Usage:
    python tools/generate_datasets.py [--out DIR] [--only {cake,tomato,dice}]
"""

import argparse
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Callable

import nrrd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Header shared by all volumes; same layout as DATA/MRHead_1.nrrd.
NRRD_HEADER = {
    "space": "left-posterior-superior",
    "space directions": np.eye(3),
    "space origin": np.zeros(3),
    "kinds": ["domain", "domain", "domain"],
    "encoding": "gzip",
}

TOMATO_SEED = 2026  # fixed RNG seed, so the tomato seeds land in the same place on every run

INF = math.inf


# ---------------------------------------------------------------------------
# Voxel values (one IntEnum per volume)
# ---------------------------------------------------------------------------

class Cake(IntEnum):
    """Voxel values of cake_3layers.nrrd (uint8)."""
    BACKGROUND = 0
    PLATE = 40
    CHOCOLATE = 80     # bottom layer
    STRAWBERRY = 120   # top layer
    VANILLA = 160      # middle layer
    FROSTING = 200
    CREAM = 220
    CANDLE = 230
    FLAME = 250
    BALL = 255


class Tomato(IntEnum):
    """Voxel values of tomato.nrrd (uint16, an MRI-like range)."""
    BACKGROUND = 0
    GEL = 250          # jelly inside the chambers
    FLESH = 600        # outer wall and the septa between chambers
    CORE = 700         # columella
    SEPAL = 750
    STEM = 800
    SKIN = 900
    SEED = 1200


class Dice(IntEnum):
    """Voxel values of dice.nrrd (uint32). Both are above 65535, so they need 32 bits."""
    BACKGROUND = 0
    BODY = 100_000
    PIP = 200_000


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------

class Shape(ABC):
    """A solid in voxel coordinates. Voxel (x, y, z) is sampled at its center point."""

    @abstractmethod
    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        """Return the (low, high) corners of a box that holds the whole shape."""

    @abstractmethod
    def contains(self, x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
        """Return a boolean mask; x, y and z are broadcastable coordinate arrays."""


class Box(Shape):
    """Axis-aligned box: low <= p < high on every axis."""

    def __init__(self, low, high):
        self.low = np.asarray(low, dtype=float)
        self.high = np.asarray(high, dtype=float)

    def bounds(self):
        return self.low, self.high

    def contains(self, x, y, z):
        (x0, y0, z0), (x1, y1, z1) = self.low, self.high
        return (x0 <= x) & (x < x1) & (y0 <= y) & (y < y1) & (z0 <= z) & (z < z1)


class Ellipsoid(Shape):
    """Ellipsoid with semi-axes (a, b, c), optionally rotated about the z axis."""

    def __init__(self, center, semi_axes, angle_deg: float = 0.0):
        self.center = np.asarray(center, dtype=float)
        self.semi_axes = np.asarray(semi_axes, dtype=float)
        self.angle = math.radians(angle_deg)

    def bounds(self):
        a, b, c = self.semi_axes
        r = max(a, b)  # loose in x and y, but holds for any rotation
        reach = np.array([r, r, c])
        return self.center - reach, self.center + reach

    def contains(self, x, y, z):
        cx, cy, cz = self.center
        dx, dy, dz = x - cx, y - cy, z - cz
        cos, sin = math.cos(self.angle), math.sin(self.angle)
        u = dx * cos + dy * sin    # along the rotated first axis
        v = -dx * sin + dy * cos   # along the rotated second axis
        a, b, c = self.semi_axes
        return (u / a) ** 2 + (v / b) ** 2 + (dz / c) ** 2 <= 1.0


def sphere(center, radius: float) -> Ellipsoid:
    return Ellipsoid(center, (radius, radius, radius))


class CylinderZ(Shape):
    """Vertical cylinder: distance from the axis <= radius, and z_low <= z < z_high."""

    def __init__(self, center_xy, radius: float, z_low: float = -INF, z_high: float = INF):
        self.cx, self.cy = map(float, center_xy)
        self.radius = float(radius)
        self.z_low, self.z_high = float(z_low), float(z_high)

    def bounds(self):
        r = self.radius
        return (np.array([self.cx - r, self.cy - r, self.z_low]),
                np.array([self.cx + r, self.cy + r, self.z_high]))

    def contains(self, x, y, z):
        in_disk = (x - self.cx) ** 2 + (y - self.cy) ** 2 <= self.radius ** 2
        return in_disk & (self.z_low <= z) & (z < self.z_high)


class RadialWalls(Shape):
    """Vertical walls that radiate from a z-parallel axis, like the spokes of a wheel.

    Wall k starts on the axis and points at angle start_deg + k * 360 / count,
    measured from +x toward +y. A voxel is inside if it lies within half_width
    of a wall. The walls are unbounded, so intersect them with a finite shape.
    """

    def __init__(self, center_xy, count: int, start_deg: float, half_width: float):
        self.cx, self.cy = map(float, center_xy)
        self.angles = [math.radians(start_deg + k * 360.0 / count) for k in range(count)]
        self.half_width = float(half_width)

    def bounds(self):
        return np.full(3, -INF), np.full(3, INF)

    def contains(self, x, y, z):
        dx, dy = x - self.cx, y - self.cy
        mask = np.zeros(np.broadcast_shapes(dx.shape, dy.shape), dtype=bool)
        for angle in self.angles:
            cos, sin = math.cos(angle), math.sin(angle)
            along = dx * cos + dy * sin
            across = -dx * sin + dy * cos
            mask |= (along >= 0) & (np.abs(across) <= self.half_width)
        return mask


class Intersection(Shape):
    """Voxels that are inside every one of the given shapes."""

    def __init__(self, *shapes: Shape):
        self.shapes = shapes

    def bounds(self):
        lows, highs = zip(*(shape.bounds() for shape in self.shapes))
        return np.max(lows, axis=0), np.min(highs, axis=0)

    def contains(self, x, y, z):
        mask = self.shapes[0].contains(x, y, z)
        for shape in self.shapes[1:]:
            mask = mask & shape.contains(x, y, z)
        return mask


class Difference(Shape):
    """Voxels inside `outer` but not inside `hole`."""

    def __init__(self, outer: Shape, hole: Shape):
        self.outer, self.hole = outer, hole

    def bounds(self):
        return self.outer.bounds()

    def contains(self, x, y, z):
        return self.outer.contains(x, y, z) & ~self.hole.contains(x, y, z)


class Volume:
    """A voxel grid that shapes are painted onto in order, so later paint wins."""

    def __init__(self, size: tuple[int, int, int], dtype):
        self.data = np.zeros(size, dtype=dtype)

    def paint(self, shape: Shape, value: int) -> None:
        size = np.array(self.data.shape)
        low, high = shape.bounds()
        # Evaluate the shape only inside its bounding box, clipped to the grid.
        start = np.clip(np.floor(low), 0, size).astype(int)
        stop = np.clip(np.floor(high) + 1, 0, size).astype(int)
        if np.any(start >= stop):
            return
        region = tuple(slice(a, b) for a, b in zip(start, stop))
        block = self.data[region]  # a view, so writing to it writes to self.data
        x, y, z = np.ogrid[region]
        block[np.broadcast_to(shape.contains(x, y, z), block.shape)] = value


# ---------------------------------------------------------------------------
# Volume builders
# ---------------------------------------------------------------------------

def build_cake() -> np.ndarray:
    """A round cake with three layers stacked along z and a ball hidden in the middle."""
    vol = Volume((300, 280, 200), np.uint8)
    axis = (150, 140)
    radius = 110

    vol.paint(CylinderZ(axis, 135, 20, 26), Cake.PLATE)
    layers = [  # (z_low, z_high, value), bottom to top
        (26, 66, Cake.CHOCOLATE),
        (66, 72, Cake.CREAM),
        (72, 112, Cake.VANILLA),
        (112, 118, Cake.CREAM),
        (118, 158, Cake.STRAWBERRY),
        (158, 164, Cake.FROSTING),
    ]
    for z_low, z_high, value in layers:
        vol.paint(CylinderZ(axis, radius, z_low, z_high), value)

    vol.paint(sphere((150, 140, 92), 40), Cake.BALL)            # crosses all three layers
    vol.paint(CylinderZ((210, 100), 5, 164, 186), Cake.CANDLE)  # off-center, breaks symmetry
    vol.paint(Ellipsoid((210, 100, 191), (3, 3, 5)), Cake.FLAME)
    return vol.data


def build_tomato() -> np.ndarray:
    """An oblate tomato: skin, flesh wall, five gel chambers with seeds, core, stem and sepals."""
    vol = Volume((240, 220, 200), np.uint16)
    center = np.array([120.0, 110.0, 100.0])
    axes = np.array([85.0, 85.0, 70.0])  # flatter along z, like a real tomato
    axis_xy = center[:2]
    chambers = 5
    # At 10 degrees, no flip, swap or 90-degree turn of the xy plane maps the septa onto themselves.
    septum_start = 10.0

    skin = Ellipsoid(center, axes)
    interior = Ellipsoid(center, 0.78 * axes)
    vol.paint(skin, Tomato.SKIN)
    vol.paint(Ellipsoid(center, 0.96 * axes), Tomato.FLESH)
    vol.paint(interior, Tomato.GEL)
    septa = RadialWalls(axis_xy, chambers, septum_start, half_width=3)
    vol.paint(Intersection(interior, septa), Tomato.FLESH)
    vol.paint(Intersection(interior, CylinderZ(axis_xy, 14)), Tomato.CORE)

    rng = np.random.default_rng(TOMATO_SEED)
    for k in range(chambers):
        middle = septum_start + (k + 0.5) * 360.0 / chambers
        for _ in range(5):
            angle = middle + rng.uniform(-14, 14)  # stays clear of the septa
            r = rng.uniform(30, 48)
            dz = rng.uniform(-22, 22)
            seed_center = center + [r * math.cos(math.radians(angle)),
                                    r * math.sin(math.radians(angle)), dz]
            vol.paint(Ellipsoid(seed_center, (4, 2.5, 2.5), angle), Tomato.SEED)  # points outward

    # Sepals: a thin layer on top of the skin, cut into five strips between the septa.
    calyx_layer = Difference(Ellipsoid(center, 1.05 * axes), skin)
    sepal_strips = RadialWalls(axis_xy, chambers, septum_start + 36, half_width=4)
    upper_cap = CylinderZ(axis_xy, 30, z_low=center[2])
    vol.paint(Intersection(calyx_layer, sepal_strips, upper_cap), Tomato.SEPAL)

    top = center[2] + axes[2]  # z of the top pole
    vol.paint(CylinderZ(axis_xy, 5, top - 4, top + 18), Tomato.STEM)
    return vol.data


# Number of pips on each face, keyed by (axis, side). Opposite faces add up to 7.
DICE_FACES = {
    (2, +1): 1, (2, -1): 6,   # top / bottom (z)
    (0, +1): 2, (0, -1): 5,   # x faces
    (1, +1): 3, (1, -1): 4,   # y faces
}

# Pip positions in (u, v) steps on a face, where u and v are the face's other two axes in order.
PIP_LAYOUTS = {
    1: [(0, 0)],
    2: [(-1, -1), (1, 1)],
    3: [(-1, -1), (0, 0), (1, 1)],
    4: [(-1, -1), (-1, 1), (1, -1), (1, 1)],
    5: [(-1, -1), (-1, 1), (0, 0), (1, -1), (1, 1)],
    6: [(-1, -1), (-1, 0), (-1, 1), (1, -1), (1, 0), (1, 1)],
}


def build_dice() -> np.ndarray:
    """A game die: a 120-voxel cube with round pips sunk into each face."""
    vol = Volume((200, 180, 160), np.uint32)
    low = np.array([40, 30, 20])
    side = 120
    cube = Box(low, low + side)
    vol.paint(cube, Dice.BODY)

    center = low + (side - 1) / 2  # middle of voxels low .. low + side - 1
    step = side / 4                # 30 voxels between neighboring pips
    for (axis, sign), count in DICE_FACES.items():
        u_axis, v_axis = [a for a in range(3) if a != axis]
        for du, dv in PIP_LAYOUTS[count]:
            pip = center.copy()
            pip[axis] += sign * side / 2  # on the face plane, half a voxel outside the last layer
            pip[u_axis] += du * step
            pip[v_axis] += dv * step
            vol.paint(Intersection(sphere(pip, 9), cube), Dice.PIP)
    return vol.data


# ---------------------------------------------------------------------------
# Data set registry, saving and self-check
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Dataset:
    filename: str
    build: Callable[[], np.ndarray]
    labels: type[IntEnum]
    spot_checks: dict[tuple[int, int, int], IntEnum]  # voxel (x, y, z) -> expected value


DATASETS = {
    "cake": Dataset("cake_3layers.nrrd", build_cake, Cake, {
        (0, 0, 0): Cake.BACKGROUND,
        (150, 140, 23): Cake.PLATE,
        (150, 140, 40): Cake.CHOCOLATE,
        (60, 140, 69): Cake.CREAM,
        (60, 140, 92): Cake.VANILLA,
        (60, 140, 130): Cake.STRAWBERRY,
        (60, 140, 160): Cake.FROSTING,
        (150, 140, 92): Cake.BALL,
        (210, 100, 175): Cake.CANDLE,
        (210, 100, 191): Cake.FLAME,
    }),
    "tomato": Dataset("tomato.nrrd", build_tomato, Tomato, {
        (0, 0, 0): Tomato.BACKGROUND,
        (120, 110, 100): Tomato.CORE,
        (204, 110, 100): Tomato.SKIN,
        (195, 110, 100): Tomato.FLESH,
        (159, 117, 100): Tomato.FLESH,   # on the septum at 10 degrees
        (134, 124, 55): Tomato.GEL,
        (120, 110, 180): Tomato.STEM,
    }),
    "dice": Dataset("dice.nrrd", build_dice, Dice, {
        (39, 89, 79): Dice.BACKGROUND,   # just outside the -x face
        (99, 89, 79): Dice.BODY,         # center of the cube
        (99, 89, 139): Dice.PIP,         # the single pip on the top face
        (99, 89, 20): Dice.BODY,         # the bottom face (6) has no center pip
        (69, 59, 20): Dice.PIP,          # a corner pip on the bottom face
        (159, 59, 49): Dice.PIP,         # the 2 face: pips on the (-1, -1) / (1, 1) diagonal
        (159, 119, 49): Dice.BODY,       # ... and none on the other diagonal
        (40, 89, 79): Dice.PIP,          # the center pip of the 5 face
    }),
}


class DatasetError(Exception):
    """A generated file does not match what was written or what the spec says."""


def check(condition: bool, message: str) -> None:
    if not condition:
        raise DatasetError(message)


def save_nrrd(path: Path, data: np.ndarray) -> None:
    """Write data (indexed [x, y, z]) as a gzip NRRD that 3D Slicer opens directly."""
    nrrd.write(str(path), data, header=dict(NRRD_HEADER), index_order="F")


def count_values(data: np.ndarray) -> dict[int, int]:
    values, counts = np.unique(data, return_counts=True)
    return dict(zip(values.tolist(), counts.tolist()))


def verify(path: Path, expected: np.ndarray, counts: dict[int, int], dataset: Dataset) -> None:
    """Read the file back and check its data, header, values and known voxels."""
    data, header = nrrd.read(str(path), index_order="F")
    check(data.dtype == expected.dtype, f"{path.name}: dtype {data.dtype} != {expected.dtype}")
    check(np.array_equal(data, expected), f"{path.name}: data read back differs from data written")
    check(header["space"] == NRRD_HEADER["space"], f"{path.name}: wrong space {header['space']}")
    check(np.array_equal(header["space directions"], np.eye(3)), f"{path.name}: wrong space directions")
    check(header["encoding"] == "gzip", f"{path.name}: wrong encoding {header['encoding']}")

    labels = {int(label) for label in dataset.labels}
    check(set(counts) == labels, f"{path.name}: values {sorted(counts)} != labels {sorted(labels)}")
    for point, label in dataset.spot_checks.items():
        check(data[point] == label, f"{path.name}: voxel {point} is {data[point]}, expected {label.name}")


def print_summary(path: Path, data: np.ndarray, counts: dict[int, int], labels: type[IntEnum]) -> None:
    shape = " x ".join(map(str, data.shape))
    print(f"{path.name}: {data.dtype}, {shape}, {path.stat().st_size / 1e6:.2f} MB on disk")
    for value, count in counts.items():
        print(f"    {labels(value).name:<11}{value:>9}{count:>13,} voxels")


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the synthetic NRRD test volumes.")
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "DATA",
                        help="output folder (default: DATA/ in the project)")
    parser.add_argument("--only", choices=DATASETS, help="generate a single volume")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    for name in [args.only] if args.only else DATASETS:
        dataset = DATASETS[name]
        path = args.out / dataset.filename
        data = dataset.build()
        save_nrrd(path, data)
        counts = count_values(data)
        verify(path, data, counts, dataset)
        print_summary(path, data, counts, dataset.labels)
    print("All files written and verified.")


if __name__ == "__main__":
    main()
