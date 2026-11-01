"""Plane setup and checks (docs/SRS.md, sections 3.4 and 3.5; docs/ALGORITHM.md, section 4).

plane_setup runs once per plane, before any projection. It finds where the image of the plane lies in the
volume, and which columns of every row belong to the shape, or the reason the plane gives an error frame.
"""

import math
from dataclasses import dataclass

import numpy as np

from plane_projection.planes import Plane

EPS = 1e-6                                  # lengths and areas below this count as zero
TOLERANCE = 0.5                             # voxels allowed off the promises of the assignment
MAX_SIDE = 4096                             # pixels on a side of an image
TOO_FAR = f"the points are too far apart for an image of at most {MAX_SIDE} pixels on a side"
TOO_LARGE = "IMAGE TOO LARGE"               # the short cause of TOO_FAR and of the size check


@dataclass(frozen=True, eq=False)
class PlaneSetup:
    """Everything the projection needs to know about one plane.

    A valid plane has no reason. Pixel (r, c) of its image is at corner + c·right + r·down in the volume,
    and belongs to the shape when c0[r] <= c <= c1[r] (FR-17, FR-18).
    A bad plane has a reason, for the warning and the report, and a title, the short cause on its error frame (FR-24).
    """

    plane: Plane
    reason: str | None = None
    title: str | None = None
    warnings: tuple[str, ...] = ()
    corner: np.ndarray | None = None
    right: np.ndarray | None = None
    down: np.ndarray | None = None
    rows: int = 0
    cols: int = 0
    c0: np.ndarray | None = None
    c1: np.ndarray | None = None

    @property
    def valid(self) -> bool:
        return self.reason is None


def plane_setup(plane: Plane) -> PlaneSetup:
    """Set up one plane, or say why it is bad (FR-24). Warnings do not make it bad (FR-25)."""
    if not plane.readable:
        return bad(plane, plane.reason, plane.title)
    with np.errstate(all="ignore"):         # far-away points may overflow; the checks below catch them
        return setup(plane)


def bad(plane: Plane, reason: str, title: str) -> PlaneSetup:
    return PlaneSetup(plane, reason=reason, title=title)


def setup(plane: Plane) -> PlaneSetup:
    if plane.is_trapezoid:
        p0, q, b, c = plane.points
        corners = (p0, q, c, b)
        first = "a'"
    else:
        p0, b, c = plane.points
        q = p0
        corners = (p0, c, b)
        first = "a"

    base = c - b
    base_length = np.linalg.norm(base)
    if not np.isfinite(base_length):
        return bad(plane, TOO_FAR, TOO_LARGE)
    if base_length < EPS:
        return bad(plane, "b and c are the same point", "B AND C ARE THE SAME POINT")
    right = base / base_length
    w = (b - p0) - ((b - p0) @ right) * right
    w_length = np.linalg.norm(w)
    if not np.isfinite(w_length):
        return bad(plane, TOO_FAR, TOO_LARGE)
    if w_length < EPS:
        return bad(plane, f"points {first}, b and c are on one line", "POINTS ON ONE LINE")
    down = w / w_length

    if plane.is_trapezoid:
        off = abs((q - p0) @ np.cross(right, down))
        if not off <= TOLERANCE:
            return bad(plane, f"point a'' is {off:.3g} voxels off the plane of a', b and c", "TRAPEZOID NOT FLAT")

    s = np.array([(v - p0) @ right for v in corners])
    t = np.array([(v - p0) @ down for v in corners])
    if not (np.isfinite(s).all() and np.isfinite(t).all()):
        return bad(plane, TOO_FAR, TOO_LARGE)
    if plane.is_trapezoid and not convex(s, t):
        return bad(plane, "the sides of the trapezoid a', a'', c, b cross each other", "TRAPEZOID SIDES CROSS")

    width, height = s.max() - s.min(), t.max() - t.min()
    if width + EPS >= MAX_SIDE or height + EPS >= MAX_SIDE:
        return bad(plane, f"the image would be {width + 1:.6g} x {height + 1:.6g} pixels, "
                          f"more than {MAX_SIDE} on a side", TOO_LARGE)
    cols = math.floor(width + EPS) + 1
    rows = math.floor(height + EPS) + 1
    corner = p0 + s.min() * right + t.min() * down
    c0, c1 = row_spans(s, t, rows, cols)
    return PlaneSetup(plane, warnings=doubts(plane, p0, q, b, c, t), corner=corner, right=right, down=down,
                      rows=rows, cols=cols, c0=c0, c1=c1)


def convex(s: np.ndarray, t: np.ndarray) -> bool:
    """The corners, in order, turn the same way at every corner: the sides do not cross (FR-24)."""
    n = len(s)
    turns = []
    for i in range(n):
        j, k = (i + 1) % n, (i + 2) % n
        turns.append((s[j] - s[i]) * (t[k] - t[j]) - (t[j] - t[i]) * (s[k] - s[j]))
    return all(turn >= -EPS for turn in turns) or all(turn <= EPS for turn in turns)


def doubts(plane: Plane, p0, q, b, c, t: np.ndarray) -> tuple[str, ...]:
    """The promises of the assignment that the plane breaks (FR-25)."""
    found = []
    legs = abs(np.linalg.norm(b - p0) - np.linalg.norm(c - q))
    if legs > TOLERANCE:
        found.append(f"the legs differ by {legs:.3g} voxels")
    if plane.is_trapezoid and abs(t[1]) > TOLERANCE:
        found.append(f"the top side a' a'' is not parallel to the base: its ends differ by {abs(t[1]):.3g} voxels")
    return tuple(found)


def row_spans(s: np.ndarray, t: np.ndarray, rows: int, cols: int) -> tuple[np.ndarray, np.ndarray]:
    """The columns c0[r] to c1[r] of the shape on every row (docs/ALGORITHM.md, section 4.3).

    Row r lies on the line t = t_min + r. The shape is convex, so the line meets it in one interval,
    found by intersecting the line with every edge. A row that misses the shape gets c0 > c1.
    """
    s_min, line = s.min(), t.min() + np.arange(rows)
    low, high = np.full(rows, np.inf), np.full(rows, -np.inf)
    n = len(s)
    for i in range(n):
        sp, tp, sq, tq = s[i], t[i], s[(i + 1) % n], t[(i + 1) % n]
        if tp != tq:
            hit = (line >= min(tp, tq) - EPS) & (line <= max(tp, tq) + EPS)
            where = sp + np.clip((line - tp) / (tq - tp), 0, 1) * (sq - sp)
            low = np.where(hit, np.minimum(low, where), low)
            high = np.where(hit, np.maximum(high, where), high)
        else:
            hit = np.abs(line - tp) <= EPS
            low = np.where(hit, np.minimum(low, min(sp, sq)), low)
            high = np.where(hit, np.maximum(high, max(sp, sq)), high)
    found = low <= high
    c0 = np.zeros(rows, dtype=np.int64)
    c1 = np.full(rows, -1, dtype=np.int64)
    c0[found] = np.maximum(np.ceil(low[found] - s_min - EPS), 0)
    c1[found] = np.minimum(np.floor(high[found] - s_min + EPS), cols - 1)
    return c0, c1
