"""Save preview images of the data set in DATA/images/, so the volumes can be seen without 3D Slicer.

For every volume, one image shows the cuts through its middle that 3D Slicer shows in its three
views, turned the same way, and one oblique cut:

    Axial     from above: the patient's right on the left of the image, the front at the top
    Coronal   from the front: the right on the left, the top at the top
    Sagittal  from the side: the front on the left, the top at the top
    Oblique   a plane through the middle, tilted 40 degrees from the axial plane

Each cut is zoomed in on the object, drawn to scale with a scale bar, and marked with letters for the
directions at its edges (R/L, A/P, S/I). The brightness is set from each file's own range of values, as
3D Slicer does. For every folder there is also an overview image with one row per file.

Usage:
    python tools/make_previews.py [--data DIR] [--out DIR]
"""

import argparse
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")                       # draw to files only, no window
import matplotlib.pyplot as plt  # noqa: E402
import nrrd  # noqa: E402
import numpy as np  # noqa: E402
from scipy import ndimage  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LPS_TO_RAS = np.diag([-1.0, -1.0, 1.0])
# (screen right, screen up) of each view, in RAS, as 3D Slicer sets them
VIEWS = {
    "Axial": ((-1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    "Coronal": ((-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    "Sagittal": ((0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),
}
VIEW_TITLES = {"Axial": "Axial: from above", "Coronal": "Coronal: from the front",
               "Sagittal": "Sagittal: from the side"}
OBLIQUE_TILT_DEG = 40.0                     # the oblique cut leans this far from the axial plane ...
OBLIQUE_TOWARD_DEG = 30.0                   # ... toward this direction (from the left, toward the front)
MAX_PIXELS = 520                            # longest side of a cut, in pixels
ZOOM_LEVEL = 0.15                           # a cut is cropped to where it is brighter than this part of the range, ...
ZOOM_MARGIN_MM = 6.0                        # ... plus this margin
SCALE_BARS_MM = (5, 10, 20, 50, 100)
SKIP = (".seg.nrrd",)                       # segmentations are label maps, not scans


def load(path: Path):
    """The volume, indexed [i, j, k], and the 4 x 4 matrix from voxel index (i, j, k) to RAS (mm)."""
    data, header = nrrd.read(str(path), index_order="F")
    directions = np.asarray(header["space directions"], float)       # one row per index axis
    origin = np.asarray(header.get("space origin", np.zeros(3)), float)
    to_ras = np.eye(4)
    to_ras[:3, :3] = LPS_TO_RAS @ directions.T
    to_ras[:3, 3] = LPS_TO_RAS @ origin
    return data, to_ras


def oblique_axes():
    """Screen right and up of the oblique cut, in RAS."""
    tilt, toward = math.radians(OBLIQUE_TILT_DEG), math.radians(OBLIQUE_TOWARD_DEG)
    normal = np.array([math.sin(tilt) * math.cos(toward), math.sin(tilt) * math.sin(toward), math.cos(tilt)])
    up = np.array([0.0, 0.0, 1.0]) - normal[2] * normal              # as close to "up" as the plane allows
    up = np.array([0.0, 1.0, 0.0]) if np.linalg.norm(up) < 1e-6 else up / np.linalg.norm(up)
    return np.cross(normal, up), up


def cut(data, to_ras, right, up):
    """The plane through the middle of the volume spanned by screen directions right and up (RAS):
    the image, its extent in mm for drawing, and the size of a pixel in mm."""
    right, up = np.asarray(right, float), np.asarray(up, float)
    shape = np.array(data.shape)
    middle = to_ras[:3, :3] @ ((shape - 1) / 2) + to_ras[:3, 3]
    corners = np.array([[i, j, k] for i in (0, shape[0] - 1) for j in (0, shape[1] - 1) for k in (0, shape[2] - 1)])
    corners_ras = corners @ to_ras[:3, :3].T + to_ras[:3, 3] - middle
    half_w, half_h = np.abs(corners_ras @ right).max(), np.abs(corners_ras @ up).max()
    spacing = np.linalg.norm(to_ras[:3, :3], axis=0)
    pixel = max(spacing.min(), 2 * max(half_w, half_h) / MAX_PIXELS)
    xs = np.arange(-half_w, half_w + pixel / 2, pixel)
    ys = np.arange(half_h, -half_h - pixel / 2, -pixel)              # top row first
    points = middle + xs[None, :, None] * right + ys[:, None, None] * up
    index = np.linalg.solve(to_ras[:3, :3], (points - to_ras[:3, 3]).reshape(-1, 3).T)
    image = ndimage.map_coordinates(data, index, order=1, cval=0.0, output=np.float32)
    extent = (-half_w, half_w, -half_h, half_h)
    return image.reshape(len(ys), len(xs)), extent, pixel


def zoom_to_object(image, extent, pixel, high):
    """Crop a cut to the object in it, plus a margin, so the object fills the picture."""
    found = ndimage.gaussian_filter(image, 1.5) > ZOOM_LEVEL * high
    if not found.any():
        return image, extent
    rows, cols = np.nonzero(found.any(1))[0], np.nonzero(found.any(0))[0]
    margin = max(int(round(ZOOM_MARGIN_MM / pixel)), int(0.06 * max(rows[-1] - rows[0], cols[-1] - cols[0])))
    r0, r1 = max(rows[0] - margin, 0), min(rows[-1] + margin + 1, image.shape[0])
    c0, c1 = max(cols[0] - margin, 0), min(cols[-1] + margin + 1, image.shape[1])
    left, _, _, top = extent
    return image[r0:r1, c0:c1], (left + c0 * pixel, left + c1 * pixel, top - r1 * pixel, top - r0 * pixel)


def direction_letter(vector) -> str:
    """The anatomical letter of a direction in RAS, by its largest component."""
    axis = int(np.argmax(np.abs(vector)))
    return ("LR", "PA", "IS")[axis][int(vector[axis] > 0)]


def brightness_range(data) -> tuple:
    """Display range from the file's values, ignoring the background and the brightest 0.5%."""
    step = max(1, int(round((data.size / 4e6) ** (1 / 3))))
    sample = data[::step, ::step, ::step].astype(np.float32)
    inside = sample[sample > np.percentile(sample, 50) + 1e-6]
    high = np.percentile(inside if inside.size else sample, 99.5)
    return 0.0, float(high) if high > 0 else 1.0


def cuts(data, to_ras, high):
    """(title, image, extent, letters at the left, right, top and bottom edges) for the four cuts,
    each zoomed in on the object."""
    result = []
    for name, (right, up) in VIEWS.items():
        image, extent, pixel = cut(data, to_ras, right, up)
        right, up = np.array(right), np.array(up)
        letters = (direction_letter(-right), direction_letter(right), direction_letter(up), direction_letter(-up))
        result.append((VIEW_TITLES[name], *zoom_to_object(image, extent, pixel, high), letters))
    right, up = oblique_axes()
    image, extent, pixel = cut(data, to_ras, right, up)
    result.append((f"Oblique: {OBLIQUE_TILT_DEG:g}° from axial", *zoom_to_object(image, extent, pixel, high), None))
    return result


def describe(path: Path, data, to_ras) -> str:
    spacing = np.linalg.norm(to_ras[:3, :3], axis=0)
    return (f"{path.name}   {' x '.join(map(str, data.shape))} voxels of {data.dtype}, "
            f"voxel {' x '.join(f'{s:g}' for s in spacing)} mm")


def draw_row(axes, panels, low, high) -> None:
    for ax, (title, image, extent, letters) in zip(axes, panels):
        ax.imshow(image, cmap="gray", vmin=low, vmax=high, extent=extent, interpolation="nearest")
        ax.set_title(title, fontsize=10)
        ax.set_xticks([])
        ax.set_yticks([])
        width, height = extent[1] - extent[0], extent[3] - extent[2]
        bar = max([b for b in SCALE_BARS_MM if b <= width / 4] or [SCALE_BARS_MM[0]])
        x1, y = extent[1] - 0.05 * width, extent[2] + 0.06 * height
        ax.plot([x1 - bar, x1], [y, y], color="white", linewidth=3, solid_capstyle="butt")
        ax.text(x1 - bar / 2, y + 0.02 * height, f"{bar / 10:g} cm" if bar >= 10 else f"{bar} mm",
                color="white", fontsize=8, ha="center", va="bottom")
        ax.set_xlim(extent[0], extent[1])
        ax.set_ylim(extent[2], extent[3])
        if letters:
            style = dict(color="yellow", fontsize=10, fontweight="bold", transform=ax.transAxes)
            ax.text(0.02, 0.5, letters[0], ha="left", va="center", **style)
            ax.text(0.98, 0.5, letters[1], ha="right", va="center", **style)
            ax.text(0.5, 0.98, letters[2], ha="center", va="top", **style)
            ax.text(0.5, 0.02, letters[3], ha="center", va="bottom", **style)


def preview(path: Path, out: Path) -> None:
    """One image with the four cuts of one volume."""
    data, to_ras = load(path)
    low, high = brightness_range(data)
    figure, axes = plt.subplots(1, 4, figsize=(16, 4.6), facecolor="black")
    draw_row(axes, cuts(data, to_ras, high), low, high)
    for ax in axes:
        ax.title.set_color("white")
    figure.suptitle(describe(path, data, to_ras), color="white", fontsize=11)
    figure.tight_layout(rect=(0, 0, 1, 0.95))
    out.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(out, dpi=110, facecolor="black")
    plt.close(figure)


def overview(paths, out: Path, title: str) -> None:
    """One row of four cuts for each volume."""
    figure, axes = plt.subplots(len(paths), 4, figsize=(16, 4.2 * len(paths)), facecolor="black", squeeze=False)
    for row, path in zip(axes, paths):
        data, to_ras = load(path)
        low, high = brightness_range(data)
        draw_row(row, cuts(data, to_ras, high), low, high)
        row[0].set_ylabel(path.name, color="white", fontsize=11)
        for ax in row:
            ax.title.set_color("white")
    figure.suptitle(title, color="white", fontsize=13)
    figure.tight_layout(rect=(0, 0, 1, 1 - 0.25 / len(paths)))
    figure.savefig(out, dpi=90, facecolor="black")
    plt.close(figure)


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Save preview images of the NRRD volumes.")
    parser.add_argument("--data", type=Path, default=PROJECT_ROOT / "DATA", help="folder of volumes (default: DATA/)")
    parser.add_argument("--out", type=Path, help="folder for the images (default: DATA/images/)")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    out = args.out or args.data / "images"
    folders = [args.data] + sorted(p for p in args.data.iterdir() if p.is_dir() and p != out)
    for folder in folders:
        paths = sorted((p for p in folder.glob("*.nrrd") if not p.name.endswith(SKIP)),
                       key=lambda p: (not p.name.startswith("MRHead"), p.name.lower()))   # the head first
        if not paths:
            continue
        target = out if folder == args.data else out / folder.name
        for path in paths:
            preview(path, target / (path.name[: -len(".nrrd")] + ".png"))
            print(f"{target / (path.name[: -len('.nrrd')] + '.png')}")
        name = "main data set" if folder == args.data else f"{folder.name}/"
        overview(paths, target / "overview.png", f"DATA: {name}")
        print(target / "overview.png")


if __name__ == "__main__":
    main()
