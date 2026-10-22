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
    ("edge_cases", 8, "tilted top side, warned"), ("edge_cases", 9, "8 numbers: black"),
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


if __name__ == "__main__":
    main()
