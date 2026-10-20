"""Generate the food scans: single objects with many layers, made in the style of MRHead_1.nrrd.

    onion.nrrd          int16   simulated MRI of an onion: eleven scales around two growing points (onion.py)
    biscuit_cake.nrrd   int16   simulated MRI of a biscuit cake, 24 x 11 x 8 cm: seven layers of biscuits with
                                cream between them and chocolate on top (biscuit_cake.py)
    swiss_roll.nrrd     int16   simulated MRI of a Swiss roll, 26 x 9 x 7.5 cm: a spiral of sponge and cream
                                (swiss_roll.py)

The three foods have clearly different lengths, widths and heights, so each view in 3D Slicer shows
something else.

Every file copies the head scan's grid (256 x 256 x 130 voxels), voxel shape (slices 1.3 times farther
apart than pixels), orientation (sagittal slices), value type, value range and MRI look; see head_style.py.
Only the voxel size differs, so that each food fills the field of view like the head.
By default the files are written to DATA/, next to MRHead_1.nrrd.

Usage:
    python tools/generate_foods.py [--out DIR] [--only {onion,biscuit_cake,swiss_roll}]
"""

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import nrrd
import numpy as np
from scipy import ndimage, signal

import biscuit_cake
import head_style
import onion
import swiss_roll
from scan_simulation import Scan

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIN_LAYERS = 10         # a line through the middle of the head scan crosses 23 clear steps or lines
EDGE_MARGIN_VOX = 2     # nothing of the object may lie this close to a face of the volume


@dataclass(frozen=True)
class Food:
    filename: str
    build: Callable[[], Scan]
    voxel_mm: float


FOODS = {
    "onion": Food("onion.nrrd", onion.build, onion.VOXEL_MM),
    "biscuit_cake": Food("biscuit_cake.nrrd", biscuit_cake.build, biscuit_cake.VOXEL_MM),
    "swiss_roll": Food("swiss_roll.nrrd", swiss_roll.build, swiss_roll.VOXEL_MM),
}


class FoodError(Exception):
    """A generated file is not what it should be."""


def check(condition: bool, message: str) -> None:
    if not condition:
        raise FoodError(message)


def object_mask(image: np.ndarray) -> np.ndarray:
    """The food itself: every voxel clearly above the background, with the gaps inside it filled."""
    mask = ndimage.gaussian_filter(image.astype(np.float32), 1.0) > 12
    mask = ndimage.binary_fill_holes(ndimage.binary_closing(mask, iterations=3))
    labels, count = ndimage.label(mask)
    sizes = ndimage.sum(mask, labels, range(1, count + 1))
    return labels == 1 + int(np.argmax(sizes))


def layers_across(image: np.ndarray, mask: np.ndarray, spacing) -> float:
    """How many clear steps and dark or bright lines a straight line through the middle of the object
    crosses, along the axis where it crosses the most: local extremes of the smoothed image that stand
    out by at least 12. Each count is the median over 25 parallel lines, up to 6 mm from the middle."""
    smooth = ndimage.gaussian_filter(image.astype(np.float32), 0.7)
    middle = np.rint(np.argwhere(mask).mean(0)).astype(int)
    offsets_mm = (-6, -3, 0, 3, 6)
    best = 0.0
    for axis in range(3):
        a, b = (n for n in range(3) if n != axis)
        counts = []
        for da in offsets_mm:
            for db in offsets_mm:
                line = [slice(None)] * 3
                line[a] = int(np.clip(middle[a] + round(da / spacing[a]), 0, image.shape[a] - 1))
                line[b] = int(np.clip(middle[b] + round(db / spacing[b]), 0, image.shape[b] - 1))
                inside = np.nonzero(mask[tuple(line)])[0]
                if inside.size == 0:
                    continue
                profile = smooth[tuple(line)][max(inside[0] - 4, 0): inside[-1] + 5]
                counts.append(len(signal.find_peaks(profile, prominence=12)[0])
                              + len(signal.find_peaks(-profile, prominence=12)[0]))
        if counts:
            best = max(best, float(np.median(counts)))
    return best


def verify(path: Path, scan: Scan, food: Food) -> None:
    """Read the file back and check it against the head scan's properties."""
    data, header = nrrd.read(str(path), index_order="F")
    check(np.array_equal(data, scan.image), f"{path.name}: data read back differs from data written")
    check(data.dtype == head_style.DTYPE and data.shape == head_style.GRID,
          f"{path.name}: {data.dtype} {data.shape}, expected int16 {head_style.GRID}")
    expected = head_style.header(food.voxel_mm)
    check(np.allclose(header["space directions"], expected["space directions"]), f"{path.name}: space directions")
    check(np.allclose(header["space origin"], expected["space origin"]), f"{path.name}: space origin")
    check(header["space"] == "left-posterior-superior" and header["encoding"] == "gzip", f"{path.name}: header")
    check(0 <= data.min() and data.max() <= 400, f"{path.name}: values {data.min()}..{data.max()}, expected 0..400")
    corner = data[:16, :16, :16].mean()
    check(corner < 4, f"{path.name}: background is not dark (corner mean {corner:.1f})")
    mask = object_mask(data)
    low, high = np.argwhere(mask).min(0), np.argwhere(mask).max(0)
    check(np.all(low >= EDGE_MARGIN_VOX) and np.all(high < np.array(data.shape) - EDGE_MARGIN_VOX),
          f"{path.name}: the object touches the edge of the field of view")
    layers = layers_across(data, mask, head_style.spacing(food.voxel_mm))
    check(layers >= MIN_LAYERS, f"{path.name}: a line through the middle crosses only {layers:.0f} layer boundaries, "
                                f"expected at least {MIN_LAYERS}")


def print_summary(path: Path, scan: Scan, food: Food) -> None:
    data = scan.image
    mask = object_mask(data)
    idx = np.argwhere(mask)
    fill = (idx.max(0) - idx.min(0) + 1) / np.array(data.shape)
    mm = " x ".join(f"{s:g}" for s in head_style.spacing(food.voxel_mm))
    size_mm = (idx.max(0) - idx.min(0) + 1) * np.array(head_style.spacing(food.voxel_mm))
    layers = layers_across(data, mask, head_style.spacing(food.voxel_mm))
    print(f"{path.name}: {data.dtype}, {' x '.join(map(str, data.shape))} voxels of {mm} mm, "
          f"values {data.min()}..{data.max()}, object {size_mm[0]:.0f} (front to back) x {size_mm[1]:.0f} (top to bottom) "
          f"x {size_mm[2]:.0f} (left to right) mm, filling {fill[0]:.0%} / {fill[1]:.0%} / {fill[2]:.0%} of i / j / k, "
          f"{layers:.0f} layer boundaries across, {path.stat().st_size / 1e6:.1f} MB")


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the food scans in the style of MRHead_1.nrrd.")
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "DATA", help="output folder (default: DATA/)")
    parser.add_argument("--only", choices=sorted(FOODS), help="generate just this food")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    for name, food in FOODS.items():
        if args.only and name != args.only:
            continue
        scan = food.build()
        path = args.out / food.filename
        nrrd.write(str(path), scan.image, header=head_style.header(food.voxel_mm), index_order="F")
        verify(path, scan, food)
        print_summary(path, scan, food)
    print("All food scans written and verified.")


if __name__ == "__main__":
    main()
