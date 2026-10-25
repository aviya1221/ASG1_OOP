"""Run the experiment of the assignment and write its results into experiment/ (experiment/README.md is the report).

Three parts, each of which can run alone with --only:

    demos    run Ex0.py on the six demo planes files; keep the videos, the printed output, and an image of chosen frames
    speed    the benchmark of docs/SRS.md, NFR-4, by threads, by image size and by value type
    slicer   the same planes resliced by vtkImageReslice inside 3D Slicer, the filter its slice views use, compared pixel by pixel

Usage:
    python tools/run_experiment.py [--only demos|speed|slicer] [--slicer PATH]
"""

import argparse
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")                       # draw to files only, no window
import matplotlib.pyplot as plt  # noqa: E402

from conftest import video_frames  # noqa: E402
from plane_projection.geometry import plane_setup  # noqa: E402
from plane_projection.planes import read_planes  # noqa: E402
from plane_projection.projector import Projector  # noqa: E402
from plane_projection.volume import Volume, read_volume  # noqa: E402

OUT = PROJECT_ROOT / "experiment"
DATA = PROJECT_ROOT / "DATA"
DEMOS = {                                   # demo name: volume
    "head": "MRHead_1.nrrd",
    "onion": "onion.nrrd",
    "biscuit_cake": "biscuit_cake.nrrd",
    "swiss_roll": "swiss_roll.nrrd",
    "croissant": "croissant.nrrd",
    "edge_cases": "synthetic/dice.nrrd",
}
# frames shown in the image of the demos: (demo, frame, what it shows)
CHOSEN_FRAMES = [
    ("head", 66, "slice z = 65"), ("head", 160, "square turned 58°"), ("head", 200, "square turned 138°"),
    ("head", 250, "turning triangle"), ("onion", 1, "uint8, first frame"), ("onion", 31, "turned 90°"),
    ("biscuit_cake", 1, "uint16, first frame"), ("biscuit_cake", 31, "turned 90°"),
    ("swiss_roll", 1, "uint32, first frame"), ("swiss_roll", 31, "turned 90°"),
    ("croissant", 1, "benchmark plane 1"), ("croissant", 50, "benchmark plane 50"),
    ("edge_cases", 1, "top face: one pip"), ("edge_cases", 4, "across the diagonal"),
    ("edge_cases", 5, "corner cut off"), ("edge_cases", 7, "unequal legs, warned"),
    ("edge_cases", 8, "tilted top side, warned"), ("edge_cases", 9, "wrong count: black"),
]


def machine() -> str:
    return (f"{platform.processor() or platform.machine()}, {os.cpu_count()} logical processors, {platform.platform()}, "
            f"Python {platform.python_version()}, NumPy {np.__version__}")


def commit() -> str:
    result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT, capture_output=True, text=True)
    return result.stdout.strip() or "unknown"


# ----- part 1: the demos

def run_demos() -> None:
    videos, results, images = OUT / "videos", OUT / "results", OUT / "images"
    for folder in (videos, results, images):
        folder.mkdir(parents=True, exist_ok=True)
    log = [f"# Demo runs, commit {commit()}", f"# {machine()}", ""]
    for name, volume in DEMOS.items():
        command = [sys.executable, "Ex0.py", f"DATA/{volume}", f"demo/{name}.csv", f"experiment/videos/{name}.mp4"]
        process = subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True, text=True)
        log += [f"$ python {' '.join(command[1:])}", process.stderr + process.stdout + f"exit code {process.returncode}", ""]
        print(f"{name}: exit code {process.returncode}")
    (results / "demo_runs.txt").write_text("\n".join(log), encoding="utf-8")

    fig, axes = plt.subplots(3, 6, figsize=(18, 11.5))
    frames = {name: video_frames(videos / f"{name}.mp4") for name in DEMOS}
    for ax, (name, number, what) in zip(axes.flat, CHOSEN_FRAMES):
        ax.imshow(frames[name][number - 1], cmap="gray", vmin=0, vmax=255)
        ax.set_title(f"{name}.mp4, frame {number}\n{what}", fontsize=10)
        ax.axis("off")
    fig.suptitle("Frames of the six demo videos, as decoded from the MP4 files", fontsize=14)
    fig.tight_layout(h_pad=3)
    fig.savefig(images / "demo_frames.png", dpi=80)
    plt.close(fig)
    print(f"wrote {results / 'demo_runs.txt'} and {images / 'demo_frames.png'}")


# ----- part 2: speed

ROUNDS = 5
THREADS = (1, 2, 4, 8)
SIZES = (100, 200, 300, 400, 500, 700)      # base and height of the triangles, in voxels


def resized(planes, size: int):
    """The benchmark triangles with another base and height, around the same middle and in the same directions."""
    from plane_projection.planes import Plane
    found = []
    for plane in planes:
        a, b, c = plane.points
        right = (c - b) / np.linalg.norm(c - b)
        down = (b + c) / 2 - a
        middle = a + down / 2
        down /= np.linalg.norm(down)
        half = size / 2
        points = (middle - half * down, middle + half * down - half * right, middle + half * down + half * right)
        found.append(Plane(plane.line, plane.frame, points))
    return found


def power() -> str:
    """Whether the laptop runs on its charger, and the processor clock: both change the speed a lot."""
    if platform.system() != "Windows":
        return "power state unknown"
    command = ("$b = Get-CimInstance Win32_Battery; $p = Get-CimInstance Win32_Processor | Select-Object -First 1; "
               "\"$($b.BatteryStatus) $($p.CurrentClockSpeed) $($p.MaxClockSpeed)\"")
    result = subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True, text=True)
    fields = result.stdout.split()
    if len(fields) != 3:
        return "power state unknown"
    source = {"1": "on battery", "2": "on the charger"}.get(fields[0], f"battery status {fields[0]}")
    return f"{source}, processor at {fields[1]} of {fields[2]} MHz"


def run_speed() -> None:
    """Every configuration runs once in each round, in turn, so changes of the clock over time affect all of them alike."""
    import benchmark
    volume = read_volume(DATA / "croissant.nrrd")
    planes = read_planes(PROJECT_ROOT / "demo" / "croissant.csv")
    copies = {np.dtype(t).name: Volume(np.asfortranarray(volume.data.astype(t))) for t in (np.uint16, np.uint32)}
    copies["uint8"] = volume
    configurations = (
        [("threads", f"{n} thread{'s' if n > 1 else ''}", "uint8", planes, n) for n in THREADS]
        + [("type", name, name, planes, 4) for name in ("uint8", "uint16", "uint32")]
        + [("size", f"{s + 1} x {s + 1}", "uint8", resized(planes, s), 4) for s in SIZES])
    found = {label: [] for _, label, *_ in configurations}
    lines = [f"# Speed of the projection, commit {commit()}", f"# {machine()}", f"# at the start: {power()}",
             f"# DATA/croissant.nrrd, the {len(planes)} planes of demo/croissant.csv (docs/SRS.md, NFR-4) and resized copies;",
             f"# {ROUNDS} rounds, each running every configuration once, in turn;",
             "# fps = planes / time of plane_setup and Projector.project (NFR-3)"]
    for round_number in range(ROUNDS):
        for _, label, dtype, chosen, threads in configurations:
            found[label] += benchmark.rates(copies[dtype], chosen, 1, threads)
        print(f"round {round_number + 1} of {ROUNDS} done")
    lines.append(f"# at the end: {power()}")

    titles = {"threads": "threads (uint8, images of 501 x 501)", "type": "value type (4 threads, images of 501 x 501)",
              "size": "image size (uint8, 4 threads): triangles with this base and height"}
    for group, title in titles.items():
        lines += ["", f"## {title}"]
        for kind, label, _, chosen, _ in configurations:
            if kind != group:
                continue
            median = statistics.median(found[label])
            text = (f"{label:12s} {median:6.0f} fps median {1000 / median:6.2f} ms per frame   "
                    f"rounds {min(found[label]):.0f} to {max(found[label]):.0f}")
            if group == "size":
                side = int(label.split(" x ")[0])
                text += f"   {1e9 / median / (side * side / 2):6.1f} ns per pixel of the triangle"
            lines.append(text)
    (OUT / "results").mkdir(parents=True, exist_ok=True)
    (OUT / "results" / "speed.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


# ----- part 3: comparison with vtkImageReslice in 3D Slicer

SLICER_SETS = [("MRHead_1.nrrd", "head"), ("swiss_roll.nrrd", "swiss_roll"), ("synthetic/dice.nrrd", "edge_cases")]
FIGURE_FRAMES = [(66, "slice z = 65"), (160, "square turned 58°"), (250, "turning triangle")]   # frames of head.csv


def inside(setup) -> np.ndarray:
    columns = np.arange(setup.cols)[None, :]
    return (columns >= setup.c0[:, None]) & (columns <= setup.c1[:, None])


def halfway(setup, rows, cols) -> np.ndarray:
    """Pixels whose point lies halfway between two voxels on some axis, within 1e-5 of a voxel.

    There the nearest voxel is a tie: this program rounds exactly by floor(p + 0.5) (FR-19), while VTK rounds with
    a small tolerance, so the two may pick different neighbors.
    """
    p = setup.corner + cols[:, None] * setup.right + rows[:, None] * setup.down + 0.5
    return (np.abs(p - np.round(p)) < 1e-5).any(axis=1)


def resliced_by_slicer(slicer_exe: Path, volume_path: Path, setups, folder: Path, name: str):
    planes = [{"corner": s.corner.tolist(), "right": s.right.tolist(), "down": s.down.tolist(),
               "rows": s.rows, "cols": s.cols} for s in setups]
    planes_path, out_path = folder / f"{name}.json", folder / f"{name}.npz"
    planes_path.write_text(json.dumps(planes), encoding="utf-8")
    command = [str(slicer_exe), "--no-splash", "--no-main-window", "--python-script",
               str(PROJECT_ROOT / "tools" / "slicer_reslice.py"), str(volume_path), str(planes_path), str(out_path)]
    process = subprocess.run(command, capture_output=True, text=True, timeout=600)
    report = next((line for line in process.stdout.splitlines() if line.startswith("resliced")), None)
    if report is None or not out_path.exists():
        raise RuntimeError(f"3D Slicer failed on {volume_path.name}:\n{process.stdout}\n{process.stderr}")
    with np.load(out_path) as images:
        return report, [images[f"nearest{i}"] for i in range(len(setups))], [images[f"linear{i}"] for i in range(len(setups))]


def run_slicer(slicer_exe: Path) -> None:
    if not slicer_exe.exists():
        print(f"3D Slicer was not found at {slicer_exe}; the slicer part is skipped")
        return
    lines = [f"# Comparison with vtkImageReslice in 3D Slicer, commit {commit()}", f"# {machine()}",
             "# For every valid plane, the pixels inside the shape are compared with vtkImageReslice using the nearest voxel.",
             ""]
    figure = []
    with tempfile.TemporaryDirectory() as folder:
        for volume_name, name in SLICER_SETS:
            volume = read_volume(DATA / volume_name)
            setups = [setup for setup in map(plane_setup, read_planes(PROJECT_ROOT / "demo" / f"{name}.csv")) if setup.valid]
            report, nearest, linear = resliced_by_slicer(slicer_exe, DATA / volume_name, setups, Path(folder), name)
            with Projector(volume) as projector:
                ours = [projector.project(setup) for setup in setups]
            compared = identical = differ_halfway = 0
            for setup, image, theirs in zip(setups, ours, nearest):
                mask = inside(setup)
                same = image == theirs
                compared += int(mask.sum())
                identical += int((same & mask).sum())
                rows, cols = np.nonzero(mask & ~same)
                differ_halfway += int(halfway(setup, rows, cols).sum())
            differ = compared - identical
            lines += [f"{volume_name} with demo/{name}.csv: {report}",
                      f"    {len(setups)} planes, {compared} pixels inside the shapes",
                      f"    identical: {identical} ({100 * identical / compared:.4f}%)",
                      f"    different: {differ}, of which {differ_halfway} lie halfway between two voxels, within 1e-5 of a voxel", ""]
            print("\n".join(lines[-5:]))
            if name == "head":
                for frame, what in FIGURE_FRAMES:
                    i = frame - 1
                    mask = inside(setups[i])
                    figure.append((frame, what, ours[i], np.where(mask, nearest[i], 0), np.where(mask, linear[i], 0),
                                   mask & (ours[i] != nearest[i]), volume))
    (OUT / "results" / "slicer_comparison.txt").write_text("\n".join(lines), encoding="utf-8")

    columns = ["this program: nearest voxel", "vtkImageReslice: nearest voxel",
               "vtkImageReslice: linear, as 3D Slicer shows", "pixels that differ (white)"]
    fig, axes = plt.subplots(len(figure), 4, figsize=(14, 3.6 * len(figure)))
    for row, (frame, what, ours_image, near, lin, differ, volume) in zip(axes, figure):
        for ax, image, title in zip(row, (ours_image, near, lin), columns):
            ax.imshow(image, cmap="gray", vmin=volume.lo, vmax=volume.hi)
            ax.set_title(f"{title}\nhead.csv frame {frame}, {what}", fontsize=9)
        row[3].imshow(differ, cmap="gray", vmin=0, vmax=1)
        row[3].set_title(f"{columns[3]}\n{int(differ.sum())} of {differ.size} pixels", fontsize=9)
        for ax in row:
            ax.axis("off")
    fig.tight_layout()
    fig.savefig(OUT / "images" / "slicer_comparison.png", dpi=80)
    plt.close(fig)
    print(f"wrote {OUT / 'results' / 'slicer_comparison.txt'} and {OUT / 'images' / 'slicer_comparison.png'}")


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the experiment and write its results into experiment/.")
    parser.add_argument("--only", choices=["demos", "speed", "slicer"], help="run one part only")
    parser.add_argument("--slicer", type=Path, default=Path(r"C:\Users\Hod Cohen\3D Slicer 5.12.4\Slicer.exe"),
                        help="the 3D Slicer program, for the slicer part")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    if args.only in (None, "demos"):
        run_demos()
    if args.only in (None, "speed"):
        sys.path.insert(0, str(PROJECT_ROOT / "tools"))
        run_speed()
    if args.only in (None, "slicer"):
        run_slicer(args.slicer)


if __name__ == "__main__":
    main()
