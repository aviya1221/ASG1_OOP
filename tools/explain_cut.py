"""Draw the picture at the top of the README: a sheet of squares inside a layered cake, and the flat image it becomes.

The cake is the worked example of docs/SRS.md, section 3.4: a 10 x 10 x 10 volume of three layers, cut by
the triangle a = (5, 0, 8), b = (1, 6, 0), c = (9, 6, 0). One square, row 5 and column 2, is followed from
the sheet to the cake and back to the image.

Usage:
    python tools/explain_cut.py [--out FILE]
"""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")                       # draw to files only, no window
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import FancyArrowPatch, Rectangle  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent

N = 10                                       # the cake is 10 x 10 x 10 cells
APEX = np.array([5.0, 0.0, 8.0])
BASE = [np.array([1.0, 6.0, 0.0]), np.array([9.0, 6.0, 0.0])]
RIGHT = np.array([1.0, 0.0, 0.0])            # one step right on the sheet
DOWN = np.array([0.0, 0.6, -0.8])            # one step down on the sheet
CORNER = APEX - 4 * RIGHT                    # top-left square of the image
ROWS, COLS = 11, 9
HIGHLIGHT = (5, 2)                           # row, column

LAYERS = [  # (first cell, last cell, color, name)
    (0, 2, "#b5793a", "Biscuit"),
    (3, 6, "#f3e3c3", "Cream"),
    (7, 9, "#5a3420", "Chocolate"),
]
OUTSIDE = "#2b2b2b"


def layer_of(z_cell):
    for lo, hi, color, name in LAYERS:
        if lo <= z_cell <= hi:
            return color, name
    return OUTSIDE, None


def point(r, c):
    return CORNER + c * RIGHT + r * DOWN


def inside_triangle(r, c):
    return abs(c - 4) <= 0.4 * r + 1e-9


def box_faces(lo, hi):
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    v = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
                  [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]])
    idx = [[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4], [2, 3, 7, 6], [1, 2, 6, 5], [0, 3, 7, 4]]
    return [v[i] for i in idx]


def square(p):
    return [p + sx * 0.5 * RIGHT + sy * 0.5 * DOWN for sx, sy in [(-1, -1), (1, -1), (1, 1), (-1, 1)]]


def setup_3d(ax):
    ax.set_xlim(-0.5, N - 0.5); ax.set_ylim(-0.5, N - 0.5); ax.set_zlim(-0.5, N - 0.5)
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=16, azim=-62)
    ax.computed_zorder = False
    ax.set_xlabel("x"); ax.set_ylabel("y"); ax.set_zlabel("z")
    ax.set_xticks([0, 5, 9]); ax.set_yticks([0, 5, 9]); ax.set_zticks([0, 5, 9])


def draw_cake(ax, alpha):
    for lo, hi, color, _ in LAYERS:
        faces = box_faces((-0.5, -0.5, lo - 0.5), (N - 0.5, N - 0.5, hi + 0.5))
        ax.add_collection3d(Poly3DCollection(faces, facecolor=color, edgecolor="#00000030",
                                             alpha=alpha, linewidth=0.5))


def draw(out):
    plt.rcParams["font.family"] = "Arial"
    fig = plt.figure(figsize=(17, 8.2), dpi=130)
    fig.patch.set_facecolor("white")

    # panel 1: the cake
    ax1 = fig.add_axes([0.0, 0.25, 0.33, 0.68], projection="3d")
    setup_3d(ax1)
    draw_cake(ax1, 0.55)
    ax1.set_title("1.  The cake: a box of 10 × 10 × 10 cubes", fontsize=15, pad=2)
    for lo, hi, color, name in LAYERS:
        ax1.text(N + 1.2, -0.5, (lo + hi) / 2, name, fontsize=13, color="black", fontweight="bold")

    # panel 2: the sheet inside the cake
    ax2 = fig.add_axes([0.33, 0.25, 0.33, 0.68], projection="3d")
    setup_3d(ax2)
    draw_cake(ax2, 0.07)
    squares, colors = [], []
    for r in range(ROWS):
        for c in range(COLS):
            if not inside_triangle(r, c):
                continue
            p = point(r, c)
            squares.append(square(p))
            colors.append(layer_of(int(round(p[2])))[0])
    ax2.add_collection3d(Poly3DCollection(squares, facecolor=colors, edgecolor="#555555", linewidth=0.6))
    hp = point(*HIGHLIGHT)
    ax2.add_collection3d(Poly3DCollection([square(hp)], facecolor=layer_of(int(round(hp[2])))[0],
                                          edgecolor="red", linewidth=3))
    ax2.scatter(*hp, color="red", s=30, depthshade=False)
    ax2.plot([hp[0], hp[0] - 4.0], [hp[1], hp[1]], [hp[2], hp[2] - 3.0], color="red", linewidth=1.5)
    ax2.text(hp[0] - 7.5, hp[1], hp[2] - 3.8, "(3, 3, 4)", color="red", fontsize=14, fontweight="bold")
    for q in [APEX] + BASE:
        ax2.scatter(*q, color="black", s=25, depthshade=False)
    ax2.text(APEX[0] - 0.5, APEX[1], APEX[2] + 1.0, "apex", fontsize=12, fontweight="bold")
    ax2.set_title("2.  A sheet of squares, at an angle inside the cake", fontsize=15, pad=2)

    # panel 3: the flat image
    ax3 = fig.add_axes([0.70, 0.30, 0.27, 0.58])
    for r in range(ROWS):
        for c in range(COLS):
            color = layer_of(int(round(point(r, c)[2])))[0] if inside_triangle(r, c) else OUTSIDE
            ax3.add_patch(Rectangle((c - 0.5, r - 0.5), 1, 1, facecolor=color, edgecolor="#777777", linewidth=0.6))
    ax3.add_patch(Rectangle((HIGHLIGHT[1] - 0.5, HIGHLIGHT[0] - 0.5), 1, 1, facecolor="none",
                            edgecolor="red", linewidth=3))
    ax3.set_xlim(-0.5, COLS - 0.5); ax3.set_ylim(ROWS - 0.5, -0.5)
    ax3.set_aspect("equal")
    ax3.set_xticks(range(COLS)); ax3.set_yticks(range(ROWS))
    ax3.xaxis.tick_top()
    ax3.set_xlabel("column", fontsize=13); ax3.xaxis.set_label_position("top")
    ax3.set_ylabel("row", fontsize=13)
    ax3.set_title("3.  Take the sheet out and lay it flat: this is the image", fontsize=15, pad=40)

    # bottom strip: the red square, step by step, left to right
    strip = fig.add_axes([0.03, 0.02, 0.94, 0.17]); strip.axis("off")
    strip.set_xlim(0, 100); strip.set_ylim(0, 10)
    strip.text(2, 8.6, "What happens to the red square", ha="left", fontsize=15, fontweight="bold")
    boxes = [  # x center, top line, bottom line
        (13, "Square on the sheet", "row 5, column 2"),
        (38, "Point in the cake", "(3, 3, 4)"),
        (63, "What is there", "cream"),
        (87, "Color of the square in the image", None),
    ]
    for x, top, bottom in boxes:
        strip.add_patch(Rectangle((x - 10, 0.5), 20, 6.3, facecolor="#f6f6f6", edgecolor="#999999"))
        strip.text(x, 5.0, top, ha="center", fontsize=13, color="#444444")
        if bottom:
            strip.text(x, 2.0, bottom, ha="center", fontsize=15, fontweight="bold")
    strip.add_patch(Rectangle((84, 1.3), 6, 2.6, facecolor=LAYERS[1][2], edgecolor="red", linewidth=2.5))
    for x0 in (23, 48, 73):
        strip.add_patch(FancyArrowPatch((x0 + 0.5, 3.6), (x0 + 4.5, 3.6), arrowstyle="-|>",
                                        mutation_scale=22, color="black"))
    strip.text(38, -1.2, "(1, 0, 8) + 2 × (1, 0, 0) + 5 × (0, 0.6, −0.8) = (3, 3, 4)", ha="center",
               fontsize=11, color="#666666")

    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("saved", out)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "DATA" / "images" / "explain" / "how_a_cut_is_made.png")
    draw(parser.parse_args().out)


if __name__ == "__main__":
    main()
