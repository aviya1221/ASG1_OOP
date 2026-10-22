"""Write the planes files of the demo into demo/ (docs/TESTING.md, section 6.1).

Each file lists planes in the format of docs/SRS.md, section 3.3: one plane per line, 9 numbers for a triangle a, b, c
or 12 for a trapezoid a', a'', b, c, in voxel indices of the volume. All the numbers are fixed, so every run writes the
same files:

    head.csv           DATA/MRHead_1.nrrd        280 frames: 130 slices along z, a square turning around the y axis,
                                                 and a triangle turning within an oblique plane
    onion.csv          DATA/onion.nrrd           120 frames: a square turning around an axis tilted 30 degrees
    biscuit_cake.csv   DATA/biscuit_cake.nrrd    from upright; the same planes in all three files
    swiss_roll.csv     DATA/swiss_roll.nrrd
    croissant.csv      DATA/croissant.nrrd       the 100 triangles of the speed benchmark (docs/SRS.md, NFR-4),
                                                 the same planes that tools/prototype_speed.py measured

After writing a file, the script reads it back as the program will, checks every plane by the rules of docs/SRS.md,
sections 3.4 and 3.5, and prints the number of frames and the frame size of the video (FR-30).
A clean file must have no bad plane, no warning, and no plane that misses the volume.

Usage:
    python tools/make_demo_planes.py [--out FOLDER]
"""

import argparse
import math
from pathlib import Path

import numpy as np

import prototype_speed

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HEAD_GRID = (256, 256, 130)                 # the head and the three smaller foods share this grid
CROISSANT_GRID = (500, 500, 500)
X, Y, Z = np.eye(3)
TRIANGLE_HEADER = "ax,ay,az,bx,by,bz,cx,cy,cz"                     # the first line of a file may name the numbers (FR-11)
TRAPEZOID_HEADER = "a1x,a1y,a1z,a2x,a2y,a2z,bx,by,bz,cx,cy,cz"
DECIMALS = 8                                # rounding stays far below the tolerance of 1e-6 in the image size (FR-16)


def number(value: float) -> str:
    """A coordinate as it is written in the file: 127.5, 0, -3.14159265."""
    text = f"{value:.{DECIMALS}f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def plane_line(points) -> str:
    """One line of the file: the points one after the other, with a space between points."""
    return ", ".join(",".join(number(value) for value in point) for point in points)


def rectangle(center, right, down, width, height):
    """A rectangle around center, written as the trapezoid a', a'', b, c (FR-12).

    right and down are unit vectors along its top side and its left side; they become the directions of FR-15.
    Its image has width + 1 columns and height + 1 rows (FR-16).
    """
    top_left = center - width / 2 * right - height / 2 * down
    bottom_left = top_left + height * down
    return [top_left, top_left + width * right, bottom_left, bottom_left + width * right]


def triangle(apex, right, down, base, height):
    """An isosceles triangle a, b, c with its apex at apex and its base at height below it, along right (FR-12)."""
    middle = apex + height * down
    return [apex, middle - base / 2 * right, middle + base / 2 * right]


def turned(vector, axis, degrees: float):
    """vector turned around the unit vector axis by the given angle (Rodrigues' formula)."""
    angle = math.radians(degrees)
    return (vector * math.cos(angle) + np.cross(axis, vector) * math.sin(angle)
            + axis * (axis @ vector) * (1 - math.cos(angle)))


def run_comment(volume: str, name: str) -> str:
    return f"# python Ex0.py {volume} demo/{name} demo/output/{Path(name).stem}.mp4"


def head_lines():
    """head.csv: slices along z, a square turning around the y axis, and a triangle turning within an oblique plane."""
    sx, sy, sz = HEAD_GRID
    center = (np.array(HEAD_GRID) - 1) / 2                      # (127.5, 127.5, 64.5)
    lines = [
        "# Demo planes for DATA/MRHead_1.nrrd: 256 x 256 x 130 voxels of int16 (docs/TESTING.md, section 6.1).",
        "# x runs from the front to the back of the head, y from the top to the bottom, and z from the left to the right.",
        run_comment("DATA/MRHead_1.nrrd", "head.csv"),
        "",
        f"# frames 1 to {sz}: the slices z = 0 ... {sz - 1}, from one side of the head to the other,",
        "# as rectangles over the whole slice: the front on the left, the top at the top",
    ]
    for z in range(sz):
        lines.append(plane_line(rectangle(np.array([center[0], center[1], z]), X, Y, sx - 1, sy - 1)))

    lines += ["", "# frames 131 to 220: a 256 x 256 square through the middle, turning 2 degrees per frame around the y axis"]
    for step in range(90):
        lines.append(plane_line(rectangle(center, turned(X, Y, 2 * step), Y, 255, 255)))

    # The oblique plane: the axial plane (normal y) tilted 40 degrees around a horizontal axis 30 degrees off the z axis.
    normal = turned(Y, turned(Z, Y, 30), 40)
    first_down = X - (X @ normal) * normal                     # toward the back of the head, as near as the plane allows
    first_down /= np.linalg.norm(first_down)
    side = 180
    height = side * math.sqrt(3) / 2
    lines += ["", "# frames 221 to 280: an equilateral triangle with sides of 180, turning 6 degrees per frame around its middle,",
              "# within a plane through the middle of the head, tilted 40 degrees from the axial plane"]
    for step in range(60):
        down = turned(first_down, normal, 6 * step)
        right = np.cross(normal, down)
        apex = center - 2 / 3 * height * down
        lines.append(plane_line(triangle(apex, right, down, side, height)))
    return lines


def food_lines(name: str, value_type: str):
    """onion.csv, biscuit_cake.csv, swiss_roll.csv: the same square turning around an axis tilted 30 degrees from upright.

    The foods share the grid of the head, so the same planes fit all three.
    """
    center = (np.array(HEAD_GRID) - 1) / 2
    down = turned(Y, Z, 30)                    # the axis, pointing down: y leans 30 degrees toward the front (-x)
    first_right = turned(X, Z, 30)
    lines = [
        TRAPEZOID_HEADER,
        f"# Demo planes for DATA/{name}.nrrd: 256 x 256 x 130 voxels of {value_type} (docs/TESTING.md, section 6.1).",
        "# The same planes are used for the onion, the biscuit cake and the Swiss roll, which share the grid of the head.",
        run_comment(f"DATA/{name}.nrrd", f"{name}.csv"),
        "",
        "# frames 1 to 120: a 256 x 256 square through the middle, turning 3 degrees per frame around an axis",
        "# that leans 30 degrees from upright toward the front; the axis runs down the middle of the image",
    ]
    for step in range(120):
        lines.append(plane_line(rectangle(center, turned(first_right, down, 3 * step), down, 255, 255)))
    return lines


def croissant_lines():
    """croissant.csv: the 100 planes of the speed benchmark (docs/SRS.md, NFR-4).

    They are the planes that tools/prototype_speed.py measured: isosceles triangles with a base and a height of 500,
    so each image is 501 x 501 pixels, with the point halfway between the apex and the middle of the base at the
    center of the volume, turned in random directions with a fixed seed.
    """
    size = prototype_speed.SIZE
    lines = [
        TRIANGLE_HEADER,
        "# The speed benchmark of docs/SRS.md, NFR-4, on DATA/croissant.nrrd: 500 x 500 x 500 voxels of uint8.",
        f"# {prototype_speed.PLANES} isosceles triangles with a base and a height of {size}, so each image is "
        f"{size + 1} x {size + 1} pixels.",
        "# The point halfway between the apex and the middle of the base is at the center, (249.5, 249.5, 249.5),",
        f"# and the directions are random, spread evenly over all directions, with the seed {prototype_speed.SEED}.",
        run_comment("DATA/croissant.nrrd", "croissant.csv"),
        "",
    ]
    for corner, right, down in prototype_speed.benchmark_planes(np.full(3, (size - 1) / 2)):
        lines.append(plane_line(triangle(corner + size / 2 * right, right, down, size, size)))
    return lines


def is_number(field: str) -> bool:
    try:
        float(field)
    except ValueError:
        return False
    return True


def check_plane(fields, grid):
    """The result of one plane line by the rules of docs/SRS.md, sections 3.4 and 3.5, and its image size (cols, rows).

    The result is "ok", "outside" (valid, but it misses the volume, FR-26), "bad: <check>" (FR-24),
    or "warning: <checks>" (FR-25).
    """
    numbers = [float(field) for field in fields] if all(is_number(field) for field in fields) else None
    if numbers is None or not all(math.isfinite(n) for n in numbers):
        return "bad: numbers", 0, 0
    if len(numbers) not in (9, 12):
        return "bad: count", 0, 0
    points = np.array(numbers).reshape(-1, 3)
    p0, b, c = points[0], points[-2], points[-1]
    q = points[1] if len(points) == 4 else p0                  # the start of the second leg
    if np.linalg.norm(c - b) < 1e-6:
        return "bad: base", 0, 0
    right = (c - b) / np.linalg.norm(c - b)
    w = (b - p0) - ((b - p0) @ right) * right
    if np.linalg.norm(w) < 1e-6:
        return "bad: one line", 0, 0
    down = w / np.linalg.norm(w)
    if len(points) == 4 and abs((q - p0) @ np.cross(right, down)) > 0.5:
        return "bad: flat", 0, 0
    s, t = (points - p0) @ right, (points - p0) @ down
    if len(points) == 4:
        corners = np.stack([s, t], axis=1)[[0, 1, 3, 2]]       # a', a'', c, b: in order around the shape
        edges = np.roll(corners, -1, axis=0) - corners
        following = np.roll(edges, -1, axis=0)
        turns = edges[:, 0] * following[:, 1] - edges[:, 1] * following[:, 0]
        if not (np.all(turns >= -1e-6) or np.all(turns <= 1e-6)):
            return "bad: shape", 0, 0
    cols = math.floor(s.max() - s.min() + 1e-6) + 1
    rows = math.floor(t.max() - t.min() + 1e-6) + 1
    if max(cols, rows) > 4096:
        return "bad: size", cols, rows
    warnings = []
    if abs(np.linalg.norm(b - p0) - np.linalg.norm(c - q)) > 0.5:
        warnings.append("legs")
    if len(points) == 4 and abs(t[1]) > 0.5:
        warnings.append("parallel sides")
    if warnings:
        return "warning: " + ", ".join(warnings), cols, rows
    corner = p0 + s.min() * right + t.min() * down
    steps = np.array([[0, 0], [cols - 1, 0], [0, rows - 1], [cols - 1, rows - 1]])
    image_corners = corner + steps @ np.stack([right, down])
    size = np.array(grid)
    if np.any(np.all(image_corners < -0.5, axis=0) | np.all(image_corners >= size - 0.5, axis=0)):
        return "outside", cols, rows
    return "ok", cols, rows


def check_file(path: Path, grid, expected=None) -> str:
    """Read a planes file back as the program will (FR-10, FR-11), check every plane, and describe the video.

    expected lists the result of every plane, in order; without it, every plane must be "ok".
    """
    results, sizes = [], []
    for line_no, text in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not text.strip() or text.startswith("#"):
            continue
        fields = [field.strip() for field in text.split(",")]
        if line_no == 1 and not all(is_number(field) for field in fields):
            continue                                            # the header
        result, cols, rows = check_plane(fields, grid)
        results.append(result)
        if not result.startswith("bad"):
            sizes.append((cols, rows))
    expected = expected or ["ok"] * len(results)
    if results != expected:
        wrong = [f"frame {frame}: {got}, expected {want}"
                 for frame, (got, want) in enumerate(zip(results, expected), start=1) if got != want]
        raise SystemExit(f"{path}: " + ("; ".join(wrong) or f"{len(results)} planes, expected {len(expected)}"))
    even = lambda n: n + n % 2                                  # noqa: E731
    width, height = (even(max(c for c, _ in sizes)), even(max(r for _, r in sizes))) if sizes else (64, 64)
    black = sum(r.startswith("bad") or r == "outside" for r in results)
    warnings = sum(r.startswith("warning") for r in results)
    return f"{len(results)} frames of {width} x {height}, {black} black, {warnings} warnings"


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write the planes files of the demo.")
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "demo", help="output folder (default: demo/)")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    files = [  # (file name, lines, grid of the volume, expected results or None for a clean file)
        ("head.csv", head_lines(), HEAD_GRID, None),
        ("onion.csv", food_lines("onion", "uint8"), HEAD_GRID, None),
        ("biscuit_cake.csv", food_lines("biscuit_cake", "uint16"), HEAD_GRID, None),
        ("swiss_roll.csv", food_lines("swiss_roll", "uint32"), HEAD_GRID, None),
        ("croissant.csv", croissant_lines(), CROISSANT_GRID, None),
    ]
    for name, lines, grid, expected in files:
        path = args.out / name
        path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        print(f"{name:18s} {check_file(path, grid, expected)}")


if __name__ == "__main__":
    main()
