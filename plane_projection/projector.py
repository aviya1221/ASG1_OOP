"""Sampling the volume on a plane (docs/SRS.md, FR-19 to FR-21; docs/ALGORITHM.md, section 5)."""

from concurrent.futures import ThreadPoolExecutor

import numpy as np

from plane_projection.geometry import PlaneSetup
from plane_projection.volume import Volume

THREADS = 4                                 # the number that measured fastest (docs/ALGORITHM.md, section 6)
MARGIN = 1e-6                               # the early exit skips a plane only when it is clearly outside


class Projector:
    """Projects planes through one volume.

    The image is split into bands of rows, one per thread, and each band computes only the columns its rows need.
    NumPy releases Python's lock inside its array operations, so the bands run at the same time.
    The pool of threads is kept for the whole run; close the projector, or use it in a with block, to stop it.
    """

    def __init__(self, volume: Volume, threads: int = THREADS):
        self.volume = volume
        self.threads = max(1, int(threads))
        self.sizes = volume.shape
        sx, sy, _ = volume.shape
        self.strides = (1, sx, sx * sy)
        self.pool = ThreadPoolExecutor(max_workers=self.threads) if self.threads > 1 else None

    def __enter__(self) -> "Projector":
        return self

    def __exit__(self, *exception) -> None:
        self.close()

    def close(self) -> None:
        if self.pool is not None:
            self.pool.shutdown()
            self.pool = None

    def project(self, setup: PlaneSetup) -> np.ndarray:
        """The image E of a valid plane, in the value type of the volume. Pixels outside the shape or the volume are 0."""
        if not setup.valid:
            raise ValueError(f"the plane of line {setup.plane.line} is bad: {setup.reason}")
        image = np.zeros((setup.rows, setup.cols), dtype=self.volume.dtype)
        if self.misses(setup):
            return image
        edges = np.linspace(0, setup.rows, min(self.threads, setup.rows) + 1).astype(int)
        bands = [(int(r0), int(r1)) for r0, r1 in zip(edges[:-1], edges[1:]) if r1 > r0]
        if self.pool is None or len(bands) == 1:
            for r0, r1 in bands:
                self.sample(setup, image, r0, r1)
        else:
            list(self.pool.map(lambda band: self.sample(setup, image, *band), bands))
        return image

    def misses(self, setup: PlaneSetup) -> bool:
        """True when, on some axis, all four corners of the image lie beyond the same side of the volume (FR-26)."""
        last_col, last_row = setup.cols - 1, setup.rows - 1
        corners = np.array([setup.corner + c * setup.right + r * setup.down
                            for c, r in ((0, 0), (last_col, 0), (0, last_row), (last_col, last_row))])
        for k, size in enumerate(self.sizes):
            if (corners[:, k] < -0.5 - MARGIN).all() or (corners[:, k] >= size - 0.5 + MARGIN).all():
                return True
        return False

    def sample(self, setup: PlaneSetup, image: np.ndarray, r0: int, r1: int) -> None:
        """Fill rows r0 to r1 - 1 of the image (docs/ALGORITHM.md, section 5.2)."""
        c0, c1 = setup.c0[r0:r1], setup.c1[r0:r1]
        filled = c0 <= c1
        if not filled.any():
            return
        first, last = int(c0[filled].min()), int(c1[filled].max()) + 1
        rows = np.arange(r0, r1, dtype=np.float64)[:, None]
        cols = np.arange(first, last, dtype=np.float64)[None, :]
        columns = np.arange(first, last)[None, :]
        ok = (columns >= c0[:, None]) & (columns <= c1[:, None])           # inside the shape, FR-18
        index = np.zeros(ok.shape, dtype=np.int32)
        for k in range(3):
            # each point straight from the corner, with the + 0.5 of rounding to the nearest voxel (FR-19)
            p = np.floor((setup.corner[k] + 0.5) + rows * setup.down[k] + cols * setup.right[k])
            ok &= (p >= 0) & (p < self.sizes[k])                           # inside the volume, FR-20
            np.clip(p, 0, self.sizes[k] - 1, out=p)
            index += p.astype(np.int32) * np.int32(self.strides[k])
        values = self.volume.flat.take(index)
        values[~ok] = 0
        image[r0:r1, first:last] = values
