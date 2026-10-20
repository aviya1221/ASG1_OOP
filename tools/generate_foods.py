"""Generate the food scans: single objects with many layers, made in the style of MRHead_1.nrrd.

    onion.nrrd          uint8    simulated MRI of an onion: eleven scales around two growing points (onion.py)
    biscuit_cake.nrrd   uint16   simulated MRI of a biscuit cake, 24 x 11 x 8 cm: seven layers of biscuits with
                                 vanilla and chocolate cream between them, strawberries, and chocolate on top
                                 (biscuit_cake.py)
    swiss_roll.nrrd     uint32   simulated MRI of a Swiss roll, 26 x 9 x 7.5 cm: a spiral of sponge, jam and
                                 cream, with fruit inside and rosettes of cream on top (swiss_roll.py)
    croissant.nrrd      uint8    simulated MRI of a chocolate croissant, 16 x 9 x 6 cm, at 500 x 500 x 500
                                 voxels: the large file for the speed test (croissant.py)

The three foods have clearly different lengths, widths and heights, so each view in 3D Slicer shows
something else. Each is stored in another of the three sizes the assignment allows for a voxel:
unsigned integers of 8, 16 and 32 bits.

Every file copies the head scan's orientation (sagittal slices) and MRI look; see head_style.py. The
three smaller foods also copy its grid (256 x 256 x 130 voxels) and voxel shape (slices 1.3 times
farther apart than pixels); the croissant has 500 x 500 x 500 cubic voxels, the size of the speed test.
The voxel size differs, so that each food fills the field of view like the head, and the values are the
head scan's, multiplied to suit each value type.
By default the files are written to DATA/, next to MRHead_1.nrrd.

Usage:
    python tools/generate_foods.py [--out DIR] [--only {onion,biscuit_cake,swiss_roll,croissant}]
"""

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import nrrd
import numpy as np
from scipy import ndimage, signal

import biscuit_cake
import croissant
import head_style
import onion
import swiss_roll
from scan_simulation import Scan

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIN_LAYERS = 10         # a line through the middle of the head scan crosses 23 clear steps or lines
MAX_SIGNAL = 400        # the highest value expected, on the head scan's scale
EDGE_MARGIN_VOX = 2     # nothing of the object may lie this close to a face of the volume
LARGE = 50_000_000      # volumes with more voxels are checked at half resolution, to save memory


@dataclass(frozen=True)
class Food:
    filename: str
    build: Callable[[], Scan]
    voxel_mm: float
    dtype: type          # the value type of the file
    scale: float         # the file's values are the head scan's scale times this
    grid: tuple = head_style.GRID
    slice_ratio: float = head_style.SLICE_RATIO

    def spacing(self) -> tuple:
        return head_style.spacing(self.voxel_mm, self.slice_ratio)


FOODS = {
    "onion": Food("onion.nrrd", onion.build, onion.VOXEL_MM, onion.DTYPE, onion.SCALE),
    "biscuit_cake": Food("biscuit_cake.nrrd", biscuit_cake.build, biscuit_cake.VOXEL_MM,
                         biscuit_cake.DTYPE, biscuit_cake.SCALE),
    "swiss_roll": Food("swiss_roll.nrrd", swiss_roll.build, swiss_roll.VOXEL_MM, swiss_roll.DTYPE, swiss_roll.SCALE),
    "croissant": Food("croissant.nrrd", croissant.build, croissant.VOXEL_MM, croissant.DTYPE, croissant.SCALE,
                      croissant.GRID, croissant.SLICE_RATIO),
}


class FoodError(Exception):
    """A generated file is not what it should be."""


def check(condition: bool, message: str) -> None:
    if not condition:
        raise FoodError(message)


def object_mask(image: np.ndarray) -> np.ndarray:
    """The food itself: every voxel clearly above the background, with the gaps inside it filled.
    The image is on the head scan's scale."""
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


def on_head_scale(data: np.ndarray, food: Food):
    """The image on the head scan's scale, with its voxel size; at half resolution for large volumes."""
    spacing = np.array(food.spacing())
    if data.size <= LARGE:
        return data / np.float32(food.scale), spacing, 1
    n = [s // 2 * 2 for s in data.shape]
    half = data[:n[0], :n[1], :n[2]].reshape(n[0] // 2, 2, n[1] // 2, 2, n[2] // 2, 2)
    return half.mean(axis=(1, 3, 5), dtype=np.float32) / np.float32(food.scale), 2 * spacing, 2


def verify(path: Path, scan: Scan, food: Food) -> None:
    """Read the file back and check it against the head scan's properties."""
    data, header = nrrd.read(str(path), index_order="F")
    check(np.array_equal(data, scan.image), f"{path.name}: data read back differs from data written")
    check(data.dtype == food.dtype and data.shape == food.grid,
          f"{path.name}: {data.dtype} {data.shape}, expected {np.dtype(food.dtype)} {food.grid}")
    expected = head_style.header(food.voxel_mm, food.grid, food.slice_ratio)
    check(np.allclose(header["space directions"], expected["space directions"]), f"{path.name}: space directions")
    check(np.allclose(header["space origin"], expected["space origin"]), f"{path.name}: space origin")
    check(header["space"] == "left-posterior-superior" and header["encoding"] == "gzip", f"{path.name}: header")
    check(data.max() <= MAX_SIGNAL * food.scale,
          f"{path.name}: values up to {data.max()}, expected at most {MAX_SIGNAL * food.scale:g}")
    level, spacing, step = on_head_scale(data, food)          # back on the head scan's scale
    corner = level[:16, :16, :16].mean()
    check(corner < 4, f"{path.name}: background is not dark (corner mean {corner:.1f} on the head scan's scale)")
    mask = object_mask(level)
    low, high = np.argwhere(mask).min(0), np.argwhere(mask).max(0)
    margin = EDGE_MARGIN_VOX / step
    check(np.all(low >= margin) and np.all(high < np.array(level.shape) - margin),
          f"{path.name}: the object touches the edge of the field of view")
    layers = layers_across(level, mask, spacing)
    check(layers >= MIN_LAYERS, f"{path.name}: a line through the middle crosses only {layers:.0f} layer boundaries, "
                                f"expected at least {MIN_LAYERS}")


def print_summary(path: Path, scan: Scan, food: Food) -> None:
    data = scan.image
    level, spacing, _ = on_head_scale(data, food)
    mask = object_mask(level)
    idx = np.argwhere(mask)
    fill = (idx.max(0) - idx.min(0) + 1) / np.array(level.shape)
    mm = " x ".join(f"{s:g}" for s in food.spacing())
    size_mm = (idx.max(0) - idx.min(0) + 1) * spacing
    layers = layers_across(level, mask, spacing)
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
        nrrd.write(str(path), scan.image, header=head_style.header(food.voxel_mm, food.grid, food.slice_ratio),
                   index_order="F")
        verify(path, scan, food)
        print_summary(path, scan, food)
    print("All food scans written and verified.")


if __name__ == "__main__":
    main()
