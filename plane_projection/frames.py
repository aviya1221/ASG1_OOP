"""Frame size, gray levels and placement (docs/SRS.md, FR-30 to FR-32; docs/ALGORITHM.md, sections 7.1 to 7.3)."""

from collections.abc import Iterable

import numpy as np

from plane_projection.geometry import PlaneSetup

EMPTY_SIZE = (64, 64)                       # width and height of the frames when no plane is valid


def frame_size(setups: Iterable[PlaneSetup]) -> tuple[int, int]:
    """Width and height of every frame: the largest valid plane, rounded up to even numbers for H.264 (FR-30)."""
    valid = [setup for setup in setups if setup.valid]
    if not valid:
        return EMPTY_SIZE
    width = max(setup.cols for setup in valid)
    height = max(setup.rows for setup in valid)
    return width + width % 2, height + height % 2


class GrayMap:
    """Turns raw values into gray levels by one linear map for the whole video (FR-32).

    gray(v) = floor(255·(v − lo)/(hi − lo) + 0.5), clipped to 0 … 255. For 8 and 16-bit volumes the map is a
    lookup table built once; for 32-bit volumes it is computed per pixel in float64, which keeps it exact.
    """

    def __init__(self, lo: int, hi: int, dtype: np.dtype):
        self.lo, self.hi = int(lo), int(hi)
        self.table = self.formula(np.arange(self.hi + 1)) if np.dtype(dtype).itemsize <= 2 else None

    def __call__(self, image: np.ndarray) -> np.ndarray:
        if self.table is not None:
            return self.table[image]
        return self.formula(image)

    def formula(self, values: np.ndarray) -> np.ndarray:
        values = np.asarray(values)
        if self.hi == self.lo:
            return np.where(values > 0, 255, 0).astype(np.uint8)
        gray = np.floor(255.0 * (values.astype(np.float64) - self.lo) / (self.hi - self.lo) + 0.5)
        return np.clip(gray, 0, 255).astype(np.uint8)


def place(image: np.ndarray | None, frame: np.ndarray) -> np.ndarray:
    """Clear the frame and copy the gray image into its middle (FR-31). With no image, the frame stays black."""
    frame.fill(0)
    if image is not None:
        rows, cols = image.shape
        height, width = frame.shape
        top, left = (height - rows) // 2, (width - cols) // 2
        frame[top:top + rows, left:left + cols] = image
    return frame
