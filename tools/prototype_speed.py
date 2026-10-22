"""Compare ways to sample a plane with NumPy, to choose the design of the projection (docs/ALGORITHM.md, section 6).

This is a prototype for the design, not the program itself. Every variant samples the same 100 planes of the
speed benchmark (docs/SRS.md, NFR-4): isosceles triangles with a base and a height of 500 voxels, whose middle
is at the center of the volume, turned in random directions with a fixed seed. Each image is 501 x 501 pixels.

The variants:

    pixel list       only the pixels inside the triangle, gathered into one list and scattered back
    rectangle        every pixel of the image rectangle, with masks for the triangle and the volume
    float32          the rectangle in 32-bit floats instead of 64-bit
    fixed point      the rectangle in 32-bit integers with 16 bits of fraction

The image is split into bands of rows, and a pool of threads works on several bands at the same time.
A trimmed band computes only the columns that the triangle reaches in its rows.

Each one prints its time per frame, its frame rate, and how many pixels differ from the exact
64-bit rectangle, which follows the rounding of docs/SRS.md, FR-19.

Usage:
    python tools/prototype_speed.py [--volume FILE] [--random]
"""

import argparse
import os
import platform
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import nrrd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SIZE = 500                                  # base and height of every triangle, in voxels
ROWS = COLS = SIZE + 1
PLANES = 100
SEED = 0

# Columns of the triangle on each row: the apex is at column 250 of row 0, the base fills row 500.
ROW = np.arange(ROWS)
C0 = np.ceil(SIZE / 2 - ROW / 2 - 1e-6).astype(np.int32)
C1 = np.floor(SIZE / 2 + ROW / 2 + 1e-6).astype(np.int32)


def benchmark_planes(center):
    """(corner, right, down) of each benchmark plane."""
    rng = np.random.default_rng(SEED)
    planes = []
    for _ in range(PLANES):
        normal = rng.normal(size=3)
        normal /= np.linalg.norm(normal)
        right = rng.normal(size=3)
        right -= (right @ normal) * normal
        right /= np.linalg.norm(right)
        down = np.cross(normal, right)
        corner = center - SIZE / 2 * right - SIZE / 2 * down
        planes.append((corner, right, down))
    return planes


class Sampler:
    """Holds the volume and samples planes from it in the different ways."""

    def __init__(self, data, bands=1, pool=None, trim=False):
        self.data = data
        self.trim = trim
        self.flat = data.reshape(-1, order="F")
        self.shape = data.shape
        self.strides = (1, data.shape[0], data.shape[0] * data.shape[1])
        self.bands = bands
        self.pool = pool

    def in_bands(self, band_function, plane):
        image = np.empty((ROWS, COLS), self.data.dtype)
        step = -(-ROWS // self.bands)
        starts = range(0, ROWS, step)
        if self.bands == 1:
            band_function(plane, 0, ROWS, image)
        else:
            list(self.pool.map(lambda r0: band_function(plane, r0, min(ROWS, r0 + step), image), starts))
        return image

    def band_columns(self, r0, r1):
        """The columns a band computes: all of them, or with trim, only those the triangle reaches."""
        if not self.trim:
            return 0, COLS
        return int(C0[r0:r1].min()), int(C1[r0:r1].max()) + 1

    def finish(self, image, r0, r1, ok, index, columns):
        ok &= (columns >= C0[r0:r1, None]) & (columns <= C1[r0:r1, None])
        values = self.flat.take(index)
        values[~ok] = 0
        first, last = int(columns[0, 0]), int(columns[0, -1]) + 1
        if first > 0 or last < COLS:
            image[r0:r1] = 0
        image[r0:r1, first:last] = values

    def rectangle(self, plane, r0, r1, image, dtype=np.float64):
        corner, right, down = plane
        first, last = self.band_columns(r0, r1)
        rows = np.arange(r0, r1, dtype=dtype)[:, None]
        columns = np.arange(first, last, dtype=dtype)[None, :]
        ok, index = True, 0
        for k in range(3):
            i = np.floor(dtype(corner[k] + 0.5) + rows * dtype(down[k]) + columns * dtype(right[k])).astype(np.int32)
            ok = ok & (i >= 0) & (i < self.shape[k])
            np.clip(i, 0, self.shape[k] - 1, out=i)
            index = index + i * np.int32(self.strides[k])
        self.finish(image, r0, r1, ok, index, np.arange(first, last)[None, :])

    def rectangle32(self, plane, r0, r1, image):
        self.rectangle(plane, r0, r1, image, np.float32)

    def fixed_point(self, plane, r0, r1, image):
        corner, right, down = plane
        one = 1 << 16
        first, last = self.band_columns(r0, r1)
        rows = np.arange(r0, r1, dtype=np.int32)[:, None]
        columns = np.arange(first, last, dtype=np.int32)[None, :]
        ok, index = True, 0
        for k in range(3):
            start = np.int32(round((corner[k] + 0.5) * one))
            i = (start + rows * np.int32(round(down[k] * one)) + columns * np.int32(round(right[k] * one))) >> 16
            ok = ok & (i >= 0) & (i < self.shape[k])
            np.clip(i, 0, self.shape[k] - 1, out=i)
            index = index + i * np.int32(self.strides[k])
        self.finish(image, r0, r1, ok, index, columns)

    def pixel_list(self, plane, r0, r1, image):
        corner, right, down = plane
        image[r0:r1] = 0
        lengths = np.maximum(C1[r0:r1] - C0[r0:r1] + 1, 0)
        rows = np.repeat(ROW[r0:r1], lengths)
        first = np.cumsum(lengths) - lengths
        columns = np.arange(lengths.sum()) - np.repeat(first - C0[r0:r1], lengths)
        ok, index = True, 0
        for k in range(3):
            i = np.floor(corner[k] + 0.5 + rows * down[k] + columns * right[k]).astype(np.int32)
            ok = ok & (i >= 0) & (i < self.shape[k])
            np.clip(i, 0, self.shape[k] - 1, out=i)
            index = index + i * np.int32(self.strides[k])
        values = self.flat.take(index)
        values[~ok] = 0
        image[rows, columns] = values


def load_volume(path: Path, random: bool):
    if random:
        rng = np.random.default_rng(SEED)
        return np.asfortranarray(rng.integers(0, 256, (SIZE, SIZE, SIZE), dtype=np.uint8)), "random values"
    data, _ = nrrd.read(str(path))
    return data, str(path.relative_to(PROJECT_ROOT))


def measure(name, sample, planes, reference):
    sample(planes[0])                       # warm up
    start = time.perf_counter()
    images = [sample(plane) for plane in planes]
    seconds = time.perf_counter() - start
    differing = sum(int(np.count_nonzero(image != expected)) for image, expected in zip(images, reference))
    print(f"{name:28s} {seconds / len(planes) * 1000:6.2f} ms {len(planes) / seconds:6.0f} fps"
          f" {differing:9d}")
    return images


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare ways to sample a plane with NumPy.")
    parser.add_argument("--volume", type=Path, default=PROJECT_ROOT / "DATA" / "croissant.nrrd",
                        help="a 500 x 500 x 500 NRRD volume (default: DATA/croissant.nrrd)")
    parser.add_argument("--random", action="store_true", help="use random values instead of a file")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    data, source = load_volume(args.volume, args.random)
    if data.shape != (SIZE, SIZE, SIZE):
        sys.exit(f"the volume must be {SIZE} x {SIZE} x {SIZE}, not {' x '.join(map(str, data.shape))}")
    planes = benchmark_planes(np.full(3, (SIZE - 1) / 2))
    print(f"volume: {source}, {data.dtype}")
    print(f"machine: {platform.processor()}, {os.cpu_count()} logical processors, {platform.platform()}")
    print(f"Python {platform.python_version()}, NumPy {np.__version__}")
    print(f"{PLANES} planes of {ROWS} x {COLS} pixels; each variant is followed by threads/bands\n")
    print(f"{'variant':28s} {'per frame':>9s} {'rate':>10s} {'differing':>9s}")

    exact = Sampler(data)
    reference = [exact.in_bands(exact.rectangle, plane) for plane in planes]
    # (name, method, threads, bands, trim)
    variants = [
        ("pixel list", "pixel_list", 1, 1, False),
        ("pixel list", "pixel_list", 4, 4, False),
        ("rectangle", "rectangle", 1, 1, False),
        ("rectangle", "rectangle", 4, 4, False),
        ("rectangle", "rectangle", 8, 8, False),
        ("trimmed rectangle", "rectangle", 4, 4, True),
        ("trimmed rectangle", "rectangle", 8, 8, True),
        ("trimmed rectangle", "rectangle", 4, 16, True),
        ("trimmed float32", "rectangle32", 4, 4, True),
        ("trimmed fixed point", "fixed_point", 4, 4, True),
    ]
    pools = {threads: ThreadPoolExecutor(max_workers=threads) for threads in (4, 8)}
    for name, method, threads, bands, trim in variants:
        sampler = Sampler(data, bands, pools.get(threads), trim)
        label = f"{name}, {threads}/{bands}"
        measure(label, lambda p, s=sampler, m=method: s.in_bands(getattr(s, m), p), planes, reference)


if __name__ == "__main__":
    main()
