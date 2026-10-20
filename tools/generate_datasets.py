"""Generate the NRRD volumes used to test the plane-projection algorithm.

    cake_3layers.nrrd       uint8    simulated MRI scan of a rectangular three-layer cake, styled like MRHead (see cake.py)
    cake_3layers.seg.nrrd   uint8    its ground-truth material labels, as a 3D Slicer segmentation
    tomato.nrrd             uint16   simulated MRI scan of a tomato (see tomato.py)
    tomato.seg.nrrd         uint8    its ground-truth tissue labels, as a 3D Slicer segmentation
    dice.nrrd               uint32   game die with a different number of pips per face (toy geometry)

These synthetic volumes have an exact answer for every voxel, so they serve as test data; the main
data set, the food scans, is made by generate_foods.py. By default the files are written to DATA/synthetic/.

Every volume is indexed vol[x, y, z], like M[x][y][z] in the assignment, and is saved on an LPS
grid with origin (0, 0, 0), so the IJK index that 3D Slicer shows is exactly (x, y, z).
The full spec is in DATA/README.md.

Usage:
    python tools/generate_datasets.py [--out DIR] [--only {cake,tomato,dice}]
"""

import argparse
import math
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Callable

import nrrd
import numpy as np
from scipy import ndimage

import cake
import tomato
from scan_simulation import Scan

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# The toy die: voxel values, shapes and builder
# ---------------------------------------------------------------------------

class Dice(IntEnum):
    """Voxel values of dice.nrrd (uint32). Both are above 65535, so they need 32 bits."""
    BACKGROUND = 0
    BODY = 100_000
    PIP = 200_000


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


def build_dice() -> Scan:
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
    return Scan(vol.data, landmarks={
        (39, 89, 79): Dice.BACKGROUND,   # just outside the -x face
        (99, 89, 79): Dice.BODY,         # center of the cube
        (99, 89, 139): Dice.PIP,         # the single pip on the top face
        (99, 89, 20): Dice.BODY,         # the bottom face (6) has no center pip
        (69, 59, 20): Dice.PIP,          # a corner pip on the bottom face
        (159, 59, 49): Dice.PIP,         # the 2 face: pips on the (-1, -1) / (1, 1) diagonal
        (159, 119, 49): Dice.BODY,       # ... and none on the other diagonal
        (40, 89, 79): Dice.PIP,          # the center pip of the 5 face
    })


# ---------------------------------------------------------------------------
# Data set registry, saving and self-check
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Dataset:
    filename: str
    build: Callable[[], Scan]
    values: type[IntEnum]       # meaning of each label value (of the image itself, for toy volumes)
    colors: Mapping[int, tuple[float, float, float]] | None = None  # segment colors, for scans with labels
    contrast: tuple[IntEnum, ...] = ()  # tissues from brightest to darkest in the image


DATASETS = {
    "cake": Dataset("cake_3layers.nrrd", cake.build, cake.Material, cake.COLORS, cake.CONTRAST),
    "tomato": Dataset("tomato.nrrd", tomato.build, tomato.Tissue, tomato.COLORS, tomato.CONTRAST),
    "dice": Dataset("dice.nrrd", build_dice, Dice),
}


class DatasetError(Exception):
    """A generated file does not match what was written or what the spec says."""


def check(condition: bool, message: str) -> None:
    if not condition:
        raise DatasetError(message)


def nrrd_header(spacing_mm) -> dict:
    """Header shared by all files; same layout as DATA/MRHead_1.nrrd, with the axes along x, y, z."""
    return {
        "space": "left-posterior-superior",
        "space directions": np.diag(spacing_mm),
        "space origin": np.zeros(3),
        "kinds": ["domain", "domain", "domain"],
        "encoding": "gzip",
    }


def segmentation_path(image_path: Path) -> Path:
    return image_path.with_name(image_path.name.removesuffix(".nrrd") + ".seg.nrrd")


def segment_fields(labels: np.ndarray, values: type[IntEnum], colors) -> dict[str, str]:
    """Key/value pairs that make 3D Slicer read a label map as named, colored segments."""
    fields = {
        "Segmentation_MasterRepresentation": "Binary labelmap",
        "Segmentation_ContainedRepresentationNames": "Binary labelmap|",
        "Segmentation_ReferenceImageExtentOffset": "0 0 0",
    }
    boxes = ndimage.find_objects(labels)  # boxes[v - 1] bounds the voxels labeled v
    for i, value in enumerate(v for v in values if v != 0):
        box = boxes[value - 1] if value <= len(boxes) else None
        check(box is not None, f"no voxels are labeled {value.name}")
        fields |= {
            f"Segment{i}_ID": f"Segment_{int(value)}",
            f"Segment{i}_Name": value.name.replace("_", " ").capitalize(),
            f"Segment{i}_NameAutoGenerated": "0",
            f"Segment{i}_LabelValue": str(int(value)),
            f"Segment{i}_Layer": "0",
            f"Segment{i}_Color": " ".join(f"{c:g}" for c in colors[value]),
            f"Segment{i}_ColorAutoGenerated": "0",
            f"Segment{i}_Extent": " ".join(f"{s.start} {s.stop - 1}" for s in box),
        }
    return fields


def save(path: Path, scan: Scan, dataset: Dataset) -> None:
    """Write the image, and its labels as a .seg.nrrd segmentation if it has any."""
    nrrd.write(str(path), scan.image, header=nrrd_header(scan.spacing_mm), index_order="F")
    if scan.labels is not None:
        header = nrrd_header(scan.spacing_mm) | segment_fields(scan.labels, dataset.values, dataset.colors)
        nrrd.write(str(segmentation_path(path)), scan.labels, header=header, index_order="F")


def verify(path: Path, scan: Scan, dataset: Dataset) -> None:
    """Read the files back and check data, header, label values, known voxels and tissue contrast."""
    image, header = nrrd.read(str(path), index_order="F")
    check(image.dtype == scan.image.dtype, f"{path.name}: dtype {image.dtype} != {scan.image.dtype}")
    check(np.array_equal(image, scan.image), f"{path.name}: data read back differs from data written")
    check(header["space"] == "left-posterior-superior", f"{path.name}: wrong space {header['space']}")
    check(np.allclose(header["space directions"], np.diag(scan.spacing_mm)), f"{path.name}: wrong spacing")
    check(header["encoding"] == "gzip", f"{path.name}: wrong encoding {header['encoding']}")

    truth = image  # toy volumes are their own label maps
    if scan.labels is not None:
        seg_path = segmentation_path(path)
        truth, seg_header = nrrd.read(str(seg_path), index_order="F")
        check(np.array_equal(truth, scan.labels), f"{seg_path.name}: labels read back differ")
        check("Segment0_Name" in seg_header, f"{seg_path.name}: segment names are missing")

    values = {int(v) for v in dataset.values}
    present = set(np.unique(truth).tolist())
    check(present == values, f"{path.name}: label values {sorted(present)} != {sorted(values)}")
    for voxel, expected in scan.landmarks.items():
        check(truth[voxel] == expected, f"{path.name}: voxel {voxel} is {truth[voxel]}, expected {expected.name}")
    means = [float(image[truth == tissue].mean()) for tissue in dataset.contrast]
    check(all(a > b for a, b in zip(means, means[1:])),
          f"{path.name}: tissue brightness out of order: {dict(zip(dataset.contrast, means))}")


def print_summary(path: Path, scan: Scan, dataset: Dataset) -> None:
    image = scan.image
    shape = " x ".join(map(str, image.shape))
    spacing = " x ".join(f"{s:g}" for s in scan.spacing_mm)
    print(f"{path.name}: {image.dtype}, {shape} voxels of {spacing} mm, "
          f"{path.stat().st_size / 1e6:.2f} MB on disk")
    truth = image
    if scan.labels is not None:
        truth = scan.labels
        seg_path = segmentation_path(path)
        print(f"{seg_path.name}: {len(dataset.values) - 1} segments, {seg_path.stat().st_size / 1e6:.2f} MB on disk")
    values, counts = np.unique(truth, return_counts=True)
    for value, count in zip(values.tolist(), counts.tolist()):
        mean = float(image[truth == value].mean())
        print(f"    {dataset.values(value).name:<16}{value:>8}{count:>12,} voxels   mean image {mean:9.1f}")


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the NRRD test volumes.")
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "DATA" / "synthetic",
                        help="output folder (default: DATA/synthetic/ in the project)")
    parser.add_argument("--only", choices=DATASETS, help="generate a single volume")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    for name in [args.only] if args.only else DATASETS:
        dataset = DATASETS[name]
        path = args.out / dataset.filename
        scan = dataset.build()
        save(path, scan, dataset)
        verify(path, scan, dataset)
        print_summary(path, scan, dataset)
    print("All files written and verified.")


if __name__ == "__main__":
    main()
