"""Reading the planes file (docs/SRS.md, section 3.3; docs/ALGORITHM.md, section 3.2)."""

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from plane_projection.errors import InputError

COUNTS = (9, 12)                            # 3 points for a triangle, 4 for a trapezoid


@dataclass(frozen=True, eq=False)
class Plane:
    """One plane line of the file.

    line counts every line of the file from 1, and frame counts the plane lines from 1 (FR-27).
    points holds 3 points (a, b, c) or 4 points (a', a'', b, c) as float64 arrays.
    A line that cannot be read has no points, and reason says why (FR-24).
    """

    line: int
    frame: int
    points: tuple[np.ndarray, ...] | None
    reason: str | None = None

    @property
    def readable(self) -> bool:
        return self.points is not None

    @property
    def is_trapezoid(self) -> bool:
        return self.points is not None and len(self.points) == 4


def read_planes(path: str | Path) -> list[Plane]:
    """Read every plane line of the file. A line that is not a plane does not stop the reading (FR-23)."""
    path = Path(path)
    if not path.is_file():
        raise InputError(path, "file not found")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as error:
        raise InputError(path, f"the file cannot be read as text ({error})") from None

    planes = []
    for line, content in enumerate(text.splitlines(), start=1):
        content = content.strip()
        if not content or content.startswith("#"):
            continue
        fields = [field.strip() for field in content.split(",")]
        numbers = [number(field) for field in fields]
        if line == 1 and None in numbers:
            continue                        # a header (FR-11)
        planes.append(make_plane(line, len(planes) + 1, fields, numbers))
    if not planes:
        raise InputError(path, "no planes in the file")
    return planes


def number(field: str) -> float | None:
    try:
        return float(field)
    except ValueError:
        return None


def make_plane(line: int, frame: int, fields: list[str], numbers: list[float | None]) -> Plane:
    for position, (field, value) in enumerate(zip(fields, numbers), start=1):
        if not field:
            return Plane(line, frame, None, f"field {position} is empty")
        if value is None:
            return Plane(line, frame, None, f"field {position} is not a number: {field!r}")
        if not math.isfinite(value):
            return Plane(line, frame, None, f"field {position} is not a finite number: {field!r}")
    if len(numbers) not in COUNTS:
        return Plane(line, frame, None, f"{len(numbers)} numbers instead of 9 (triangle) or 12 (trapezoid)")
    points = tuple(np.array(numbers[i:i + 3], dtype=np.float64) for i in range(0, len(numbers), 3))
    return Plane(line, frame, points)
