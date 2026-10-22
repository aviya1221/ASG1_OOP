"""Measure the speed of the projection on the benchmark of docs/SRS.md, NFR-4 (docs/TESTING.md, section 7.1).

For every plane of the planes file, the time of plane_setup and Projector.project together is measured, as NFR-3
defines it: from the points of a plane to its image, without reading the files, the gray levels or the video.
The planes run several rounds, and the median rate is compared with the minimum of 30 fps (NFR-1) and the target of
100 fps (NFR-2). With --types, the same planes also run on copies of the volume in 16 and 32 bits, for information.

Usage:
    python tools/benchmark.py [--volume FILE] [--planes FILE] [--rounds N] [--threads N] [--types]
"""

import argparse
import os
import platform
import statistics
import sys
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from plane_projection.geometry import plane_setup  # noqa: E402
from plane_projection.planes import read_planes  # noqa: E402
from plane_projection.projector import THREADS, Projector  # noqa: E402
from plane_projection.volume import Volume, read_volume  # noqa: E402

MINIMUM, TARGET = 30, 100                   # frames per second, NFR-1 and NFR-2


def rates(volume: Volume, planes, rounds: int, threads: int) -> list[float]:
    """Frames per second of each round."""
    found = []
    with Projector(volume, threads) as projector:
        projector.project(plane_setup(planes[0]))       # warm up the threads
        for _ in range(rounds):
            seconds = 0.0
            for plane in planes:
                start = time.perf_counter()
                setup = plane_setup(plane)
                if setup.valid:
                    projector.project(setup)
                seconds += time.perf_counter() - start
            found.append(len(planes) / seconds)
    return found


def describe(found: list[float]) -> str:
    median = statistics.median(found)
    return (f"{median:6.0f} fps median, {1000 / median:5.2f} ms per frame "
            f"(rounds from {min(found):.0f} to {max(found):.0f} fps)")


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure the speed of the projection (docs/SRS.md, NFR-4).")
    parser.add_argument("--volume", type=Path, default=PROJECT_ROOT / "DATA" / "croissant.nrrd",
                        help="the volume (default: DATA/croissant.nrrd)")
    parser.add_argument("--planes", type=Path, default=PROJECT_ROOT / "demo" / "croissant.csv",
                        help="the planes (default: demo/croissant.csv, the 100 benchmark planes)")
    parser.add_argument("--rounds", type=int, default=3, help="how many times to run all the planes (default: 3)")
    parser.add_argument("--threads", type=int, default=THREADS, help=f"threads of the projection (default: {THREADS})")
    parser.add_argument("--types", action="store_true", help="also run on copies of the volume in 16 and 32 bits")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    volume = read_volume(args.volume)
    planes = read_planes(args.planes)
    print(f"machine:  {platform.processor() or platform.machine()}, {os.cpu_count()} logical processors, "
          f"{platform.platform()}")
    print(f"versions: Python {platform.python_version()}, NumPy {np.__version__}")
    print(f"volume:   {args.volume.name}, {' x '.join(map(str, volume.shape))}, {volume.dtype}")
    print(f"planes:   {len(planes)} from {args.planes.name}, {args.rounds} rounds, {args.threads} threads\n")

    found = rates(volume, planes, args.rounds, args.threads)
    print(f"{volume.dtype.name:8s}  {describe(found)}")
    if args.types:
        for dtype in (np.uint16, np.uint32):
            copy = Volume(np.asfortranarray(volume.data.astype(dtype)))
            print(f"{np.dtype(dtype).name:8s}  {describe(rates(copy, planes, args.rounds, args.threads))}")

    median = statistics.median(found)
    verdict = ("meets the target of" if median >= TARGET else
               "meets the minimum of" if median >= MINIMUM else "is below the minimum of")
    limit = TARGET if median >= TARGET else MINIMUM
    print(f"\nresult:   {median:.0f} fps {verdict} {limit} fps (NFR-1: at least {MINIMUM}, NFR-2: target {TARGET})")
    return 0 if median >= MINIMUM else 1


if __name__ == "__main__":
    sys.exit(main())
