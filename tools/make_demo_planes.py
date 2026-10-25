"""Write the planes files of the demo into demo/ (docs/TESTING.md, section 6.1).

Each file has the format of the lecturer's example file, demo/lecturer_example.csv (docs/SRS.md, section 3.3):
its header, then one plane per line, the number of points and x, y, z of each point, in voxel indices of the volume:
3 points a, b, c for a triangle, or 4 points a', b, a'', c for a trapezoid. The five clean files have nothing else,
like the lecturer's example; edge_cases.csv adds comments and blank lines (FR-11).
All the numbers are fixed, so every run writes the same files:

    head.csv           DATA/MRHead_1.nrrd        280 frames: 130 slices along z, a square turning around the y axis,
                                                 and a triangle turning within an oblique plane
    onion.csv          DATA/onion.nrrd           120 frames: a square turning around an axis tilted 30 degrees
    biscuit_cake.csv   DATA/biscuit_cake.nrrd    from upright; the same planes in all three files
    swiss_roll.csv     DATA/swiss_roll.nrrd
    croissant.csv      DATA/croissant.nrrd       the 100 triangles of the speed benchmark (docs/SRS.md, NFR-4),
                                                 the same planes that tools/prototype_speed.py measured
    edge_cases.csv     DATA/synthetic/dice.nrrd  16 frames: images of the die known in advance, a plane outside the
                                                 volume, and one line for each bad and doubtful case of FR-24 and FR-25

After writing a file, the script reads it back as the program will, checks every plane by the rules of docs/SRS.md,
sections 3.4 and 3.5, and prints the number of frames and the frame size of the video (FR-30).
A clean file must have no bad plane, no warning, and no plane that misses the volume;
each plane of edge_cases.csv must give the result that its comment names.

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
DICE_GRID = (200, 180, 160)
X, Y, Z = np.eye(3)
HEADER = "Number of Points (3 or 4),x1,y1,z1,x2,y2,z2,x3,y3,z3,x4,y4,z4"   # of the lecturer's example (FR-11)
FILE_ORDER = {3: (0, 1, 2), 4: (0, 2, 1, 3)}  # a, b, c and a', a'', b, c as the file lists them: a, b, c and a', b, a'', c
DECIMALS = 8                                # rounding stays far below the tolerance of 1e-6 in the image size (FR-16)


def number(value: float) -> str:
    """A coordinate as it is written in the file: 127.5, 0, -3.14159265."""
    text = f"{value:.{DECIMALS}f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def plane_line(points) -> str:
    """One line of the file for the points a, b, c or a', a'', b, c (FR-12).

    The line starts with the number of points, and lists them in the order of the file, a, b, c or a', b, a'', c.
    A triangle leaves the fields of the fourth point empty, as the lecturer's example does.
    """
    fields = [number(value) for index in FILE_ORDER[len(points)] for value in points[index]]
    return ",".join([str(len(points)), *fields, *[""] * (12 - len(fields))])


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
    lines = [HEADER]
    # frames 1 to 130: the slices z = 0 ... 129, from one side of the head to the other, as rectangles over the
    # whole slice: the front on the left, the top at the top. x runs from the front to the back of the head,
    # y from the top to the bottom, and z from the left to the right.
    for z in range(sz):
        lines.append(plane_line(rectangle(np.array([center[0], center[1], z]), X, Y, sx - 1, sy - 1)))

    # frames 131 to 220: a 256 x 256 square through the middle, turning 2 degrees per frame around the y axis
    for step in range(90):
        lines.append(plane_line(rectangle(center, turned(X, Y, 2 * step), Y, 255, 255)))

    # The oblique plane: the axial plane (normal y) tilted 40 degrees around a horizontal axis 30 degrees off the z axis.
    normal = turned(Y, turned(Z, Y, 30), 40)
    first_down = X - (X @ normal) * normal                     # toward the back of the head, as near as the plane allows
    first_down /= np.linalg.norm(first_down)
    side = 180
    height = side * math.sqrt(3) / 2
    # frames 221 to 280: an equilateral triangle with sides of 180, turning 6 degrees per frame around its middle,
    # within a plane through the middle of the head, tilted 40 degrees from the axial plane
    for step in range(60):
        down = turned(first_down, normal, 6 * step)
        right = np.cross(normal, down)
        apex = center - 2 / 3 * height * down
        lines.append(plane_line(triangle(apex, right, down, side, height)))
    return lines


def food_lines():
    """onion.csv, biscuit_cake.csv, swiss_roll.csv: the same square turning around an axis tilted 30 degrees from upright.

    The foods share the grid of the head, so the same planes fit all three: 120 frames of a 256 x 256 square through
    the middle, turning 3 degrees per frame around an axis that leans 30 degrees from upright toward the front.
    The axis runs down the middle of the image.
    """
    center = (np.array(HEAD_GRID) - 1) / 2
    down = turned(Y, Z, 30)                    # the axis, pointing down: y leans 30 degrees toward the front (-x)
    first_right = turned(X, Z, 30)
    lines = [HEADER]
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
    lines = [HEADER]
    for corner, right, down in prototype_speed.benchmark_planes(np.full(3, (size - 1) / 2)):
        lines.append(plane_line(triangle(corner + size / 2 * right, right, down, size, size)))
    return lines


def frame_list(frames) -> str:
    """Frame numbers with runs joined: [6, 9, 10, 11] gives "frames 6, 9 to 11"."""
    runs = []
    for frame in frames:
        if runs and frame == runs[-1][1] + 1:
            runs[-1][1] = frame
        else:
            runs.append([frame, frame])
    return "frames " + ", ".join(str(a) if a == b else f"{a} to {b}" for a, b in runs)


def dice_triangle(centroid, side: float):
    """An equilateral triangle around centroid in a plane x + y + z = constant, with its apex toward +z."""
    normal = np.ones(3) / math.sqrt(3)
    down = np.array([1.0, 1.0, -2.0]) / math.sqrt(6)           # in the plane, as near to -z as the plane allows
    height = side * math.sqrt(3) / 2
    return triangle(centroid - 2 / 3 * height * down, np.cross(normal, down), down, side, height)


def edge_case_lines():
    """edge_cases.csv: known images of the die, a plane outside it, and each bad and doubtful case of FR-24 and FR-25.

    Returns the lines, and the expected result of every plane for check_file.
    """
    hexagon = dice_triangle(np.array([99.5, 89.5, 79.5]), 280)
    corner = dice_triangle(np.array([159.5, 149.5, 139.5]) - 40 / 3, 140)    # around the middle of the cut corner
    sections = [
        ("Good planes, whose images are known in advance (docs/TESTING.md, section 3.5)", [
            ("ok", "the top face, z = 139, as a rectangle over the whole slice: a 120 x 120 square with one pip",
             plane_line([(0, 0, 139), (199, 0, 139), (0, 179, 139), (199, 179, 139)])),
            ("ok", "the bottom face, z = 20, in an isosceles trapezoid around it: a square with six pips",
             plane_line([(30, 20, 20), (169, 20, 20), (0, 160, 20), (199, 160, 20)])),
            ("ok", "the front face, y = 30, as a rectangle with the top of the die at the top: a square with four pips.\n"
                   "Spaces around the numbers, and 1.59e2 for 159, are allowed (FR-10)",
             " 4 ,  0 , 30 , 1.59e2 ,  0 , 30 , 0 ,  199 , 30 , 159 ,  199 , 30 , 0"),
            ("ok", "the plane x + y + z = 268.5 through the center: a regular hexagon with sides of 84.9 in a triangle",
             plane_line(hexagon)),
            ("ok", "the plane x + y + z = 408.5: the corner (159, 149, 139) cut off as an equilateral triangle\n"
                   "with sides of 56.6, upside down in a larger triangle",
             plane_line(corner)),
        ]),
        ("A valid plane that misses the volume: a black frame without a warning (FR-26)", [
            ("outside", "a triangle above the die, at z = 300", plane_line([(99.5, 0, 300), (0, 179, 300), (199, 179, 300)])),
        ]),
        ("Doubtful planes: drawn as given, with a warning (FR-25)", [
            ("warning: legs", "legs of 188.8 and 226.6", plane_line([(60, 0, 80), (0, 179, 80), (199, 179, 80)])),
            ("warning: parallel sides", "equal legs of 130, but a'' is 16 lower than a', so the top side is not parallel"
             " to the base", plane_line([(100, 40, 150), (100, 112, 134), (100, -10, 30), (100, 190, 30)])),
        ]),
        ("Bad planes: a black frame and a warning (FR-24)", [
            ("bad: count", "4 points, but only the 9 numbers of a triangle", "4,99.5,0,139,0,179,139,199,179,139,,,"),
            ("bad: numbers", "a word", "3,99.5,0,139,0,179,139,199,179,abc,,,"),
            ("bad: numbers", "an infinite number", "3,99.5,0,139,0,179,inf,199,179,139,,,"),
            ("bad: base", "b and c are the same point", plane_line([(99.5, 0, 80), (150, 179, 80), (150, 179, 80)])),
            ("bad: one line", "a, b and c are on one line", plane_line([(0, 0, 80), (100, 90, 80), (200, 180, 80)])),
            ("bad: flat", "a'' is 10 above the plane through a', b and c",
             plane_line([(30, 20, 20), (169, 20, 30), (0, 160, 20), (199, 160, 20)])),
            ("bad: shape", "a' and a'', points 1 and 3, swapped, so the sides cross",
             plane_line([(169, 20, 20), (30, 20, 20), (0, 160, 20), (199, 160, 20)])),
            ("bad: size", "a base of 10199, so an image of 10200 columns",
             plane_line([(99.5, 0, 80), (-5000, 179, 80), (5199, 179, 80)])),
        ]),
    ]
    cases = [case for _, section in sections for case in section]
    black = [frame for frame, (result, _, _) in enumerate(cases, start=1) if result.startswith("bad") or result == "outside"]
    warned = [frame for frame, (result, _, _) in enumerate(cases, start=1) if result.startswith(("bad", "warning"))]
    lines = [
        HEADER,
        "# Edge cases on DATA/synthetic/dice.nrrd: 200 x 180 x 160 voxels of uint32 (docs/TESTING.md, section 6.1).",
        "# The die is the cube x = 40 ... 159, y = 30 ... 149, z = 20 ... 139, with the value 100000; its pips have 200000.",
        "# The line above is the header of the lecturer's format (FR-11). Each plane starts with its number of points:",
        "# 3 for a triangle a, b, c, or 4 for a trapezoid a', b, a'', c (FR-12).",
        run_comment("DATA/synthetic/dice.nrrd", "edge_cases.csv"),
        f"# Expected: {len(cases)} frames; black: {frame_list(black)}; a warning for {frame_list(warned)}.",
    ]
    frame = 0
    for title, section in sections:
        lines += ["", f"# {title}"]
        for _, description, line in section:
            frame += 1
            first, *more = description.split("\n")
            lines += [f"# frame {frame}: {first}", *(f"# {text}" for text in more), line]
    return lines, [result for result, _, _ in cases]


def fields_of(text: str) -> list[str]:
    """The fields of a line, without spaces around them, and without the empty fields at its end (FR-10)."""
    fields = [field.strip() for field in text.split(",")]
    while len(fields) > 1 and not fields[-1]:
        fields.pop()
    return fields


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
    count, coordinates = numbers[0], numbers[1:]
    if count not in FILE_ORDER or len(coordinates) != 3 * count:
        return "bad: count", 0, 0
    points = np.array(coordinates).reshape(-1, 3)[list(FILE_ORDER[int(count)])]    # a, b, c or a', a'', b, c
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
        fields = fields_of(text)
        if line_no == 1 and any(field and not is_number(field) for field in fields):
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
    edge_lines, edge_results = edge_case_lines()
    files = [  # (file name, lines, grid of the volume, expected results or None for a clean file)
        ("head.csv", head_lines(), HEAD_GRID, None),
        ("onion.csv", food_lines(), HEAD_GRID, None),
        ("biscuit_cake.csv", food_lines(), HEAD_GRID, None),
        ("swiss_roll.csv", food_lines(), HEAD_GRID, None),
        ("croissant.csv", croissant_lines(), CROISSANT_GRID, None),
        ("edge_cases.csv", edge_lines, DICE_GRID, edge_results),
    ]
    for name, lines, grid, expected in files:
        path = args.out / name
        path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        print(f"{name:18s} {check_file(path, grid, expected)}")


if __name__ == "__main__":
    main()
