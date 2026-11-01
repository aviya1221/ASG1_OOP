"""Frame size, gray levels, placement and error frames (docs/SRS.md, FR-24, FR-30 to FR-32;
docs/ALGORITHM.md, sections 7.1 to 7.4)."""

from collections.abc import Iterable

import numpy as np

from plane_projection import font
from plane_projection.geometry import PlaneSetup

EMPTY_SIZE = (64, 64)                       # width and height of the frames when no plane is valid
ERROR_GRAY, ERROR_BORDER, ERROR_TEXT = 64, 160, 255     # gray levels of an error frame
LARGEST_SCALE = 8                           # pixels per pixel of the font, at most, for the small lines
PITCH = 10                                  # rows from one line of text to the next, per pixel of the font


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


def place(image: np.ndarray, frame: np.ndarray) -> np.ndarray:
    """Clear the frame and copy the gray image into its middle (FR-31)."""
    frame.fill(0)
    rows, cols = image.shape
    height, width = frame.shape
    top, left = (height - rows) // 2, (width - cols) // 2
    frame[top:top + rows, left:left + cols] = image
    return frame


def error_frame(setup: PlaneSetup, frame: np.ndarray) -> np.ndarray:
    """Draw the error frame of a bad plane over the whole frame (FR-24b).

    A gray field in a lighter border shows ERROR in large letters, then the frame and the line of the plane,
    and its short cause, all centered. The text takes the largest scale at which it fits. A frame too small for all
    of it shows the lines that fit, from the top, and a frame too small for the word ERROR shows a large X.
    """
    height, width = frame.shape
    frame.fill(ERROR_GRAY)
    border = max(1, min(height, width) // 64)
    frame[:border] = frame[height - border:] = ERROR_BORDER
    frame[:, :border] = frame[:, width - border:] = ERROR_BORDER
    margin = border + max(1, min(height, width) // 32)
    lines = ["ERROR", f"FRAME {setup.plane.frame}", f"LINE {setup.plane.line}"]
    rows = layout(lines, setup.title or "", width - 2 * margin, height - 2 * margin)
    if not rows:
        cross(frame[margin:height - margin, margin:width - margin])
    top = (height - text_height(rows)) // 2
    for text, scale in rows:
        bitmap = font.render(text, scale)
        stamp(frame, bitmap, top, (width - bitmap.shape[1]) // 2, ERROR_TEXT)
        top += PITCH * scale
    return frame


def layout(lines: list[str], cause: str, width: int, height: int) -> list[tuple[str, int]]:
    """The lines of text with their scales: the first line larger than the others, up to twice their scale, the other
    lines whole, and then the cause wrapped at its words. The largest scale whose text fits in width × height wins;
    at scale 1 the first line may be as small as the others. When nothing fits, the cause is left out whole, and
    then lines from the bottom, at scale 1; there may be none left.
    """
    def fits(rows):
        return all(font.text_width(text, s) <= width for text, s in rows) and text_height(rows) <= height

    for scale in range(LARGEST_SCALE, 0, -1):
        for first in range(2 * scale, scale if scale > 1 else 0, -1):
            rows = [(lines[0], first)] + [(line, scale) for line in lines[1:] + wrap(cause, width, scale)]
            if fits(rows):
                return rows
    rows = [(line, 1) for line in lines]
    while rows and not fits(rows):
        rows.pop()
    return rows


def wrap(text: str, width: int, scale: int) -> list[str]:
    """Split the text at spaces into lines of at most width pixels; a word longer than a line keeps a line alone."""
    lines = []
    for word in text.split():
        if lines and font.text_width(f"{lines[-1]} {word}", scale) <= width:
            lines[-1] += f" {word}"
        else:
            lines.append(word)
    return lines


def text_height(rows: list[tuple[str, int]]) -> int:
    """Rows of pixels from the top of the first line of text to the bottom of the last."""
    return sum(PITCH * scale for _, scale in rows[:-1]) + font.HEIGHT * rows[-1][1] if rows else 0


def cross(area: np.ndarray) -> None:
    """Draw the two diagonals of the area, one pixel wide."""
    height, width = area.shape
    if height and width:
        rows = np.arange(height)
        cols = np.floor(rows * (width - 1) / max(height - 1, 1) + 0.5).astype(np.int64)
        area[rows, cols] = area[rows, width - 1 - cols] = ERROR_TEXT


def stamp(frame: np.ndarray, bitmap: np.ndarray, top: int, left: int, value: int) -> None:
    """Set the pixels of the frame under the true pixels of the bitmap, whose corner is at (top, left), to value.

    The parts of the bitmap outside the frame are left out.
    """
    height, width = frame.shape
    r0, c0 = max(top, 0), max(left, 0)
    r1, c1 = min(top + bitmap.shape[0], height), min(left + bitmap.shape[1], width)
    if r0 < r1 and c0 < c1:
        frame[r0:r1, c0:c1][bitmap[r0 - top:r1 - top, c0 - left:c1 - left]] = value
