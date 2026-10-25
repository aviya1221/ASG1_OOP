"""Demo of the plane projection: cut an NRRD volume by every plane of a CSV file, and write one video frame per plane.

Usage:
    python Ex0.py file.nrrd file.csv file.mp4 [--fps N]

The requirements are in docs/SRS.md, and the way this program meets them in docs/ALGORITHM.md.
"""

import argparse
import math
import sys
from pathlib import Path
from time import perf_counter

import numpy as np

from plane_projection.errors import InputError
from plane_projection.frames import GrayMap, frame_size, place
from plane_projection.geometry import PlaneSetup, plane_setup
from plane_projection.planes import Plane, read_planes
from plane_projection.projector import Projector
from plane_projection.video import VideoWriter
from plane_projection.volume import read_volume

PLANES_FORMAT = """\
The planes file has one plane per line, in comma-separated fields: the number of points,
3 or 4, and then x, y, z of each point, in voxel indices.
  3 points  a triangle a, b, c: the apex a, and the base from b to c
  4 points  a trapezoid a', b, a'', c: the legs from a' to b and from a'' to c,
            the top side from a' to a'', and the base from b to c
A triangle leaves the fields of the fourth point empty. Blank lines and lines starting
with # are skipped, and so is a first line that is not numbers (a header). A line that
is not a plane gives a black frame and a warning.

Example, with the header, a triangle in the slice z = 65 of a 256 x 256 x 130 volume,
and a tilted trapezoid:

  Number of Points (3 or 4),x1,y1,z1,x2,y2,z2,x3,y3,z3,x4,y4,z4
  3,127.5,0,65,0,255,65,255,255,65,,,
  4,60,40,20,20,200,110,190,40,20,230,200,110
"""


def positive(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        value = math.nan
    if not (math.isfinite(value) and value > 0):
        raise argparse.ArgumentTypeError(f"must be a positive number, not {text!r}")
    return value


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="Ex0.py", description="Cut a 3D volume by a list of planes, and write one video frame per plane.",
        epilog=PLANES_FORMAT, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("volume", metavar="file.nrrd", help="the 3D volume, an NRRD file")
    parser.add_argument("planes", metavar="file.csv", help="the planes, 3 or 4 points on each line")
    parser.add_argument("video", metavar="file.mp4", help="the output video, one frame per plane")
    parser.add_argument("--fps", type=positive, default=30.0, help="frame rate of the video (default: 30)")
    return parser.parse_args(argv)


class Run:
    """One run of the demo: the warnings it printed, and its timers (FR-35, NFR-3)."""

    def __init__(self):
        self.warnings = 0
        self.black = 0
        self.load = self.projection = self.video = 0.0

    def warn(self, plane: Plane, text: str) -> None:
        print(f"warning: line {plane.line}, frame {plane.frame}: {text}", file=sys.stderr, flush=True)
        self.warnings += 1

    def set_up(self, plane: Plane) -> PlaneSetup:
        start = perf_counter()
        try:
            setup = plane_setup(plane)
        except Exception as error:          # NFR-8: no plane line can stop the program
            setup = PlaneSetup(plane, f"internal error in the setup ({error})")
        self.projection += perf_counter() - start
        for doubt in setup.warnings:
            self.warn(plane, f"{doubt}; drawn as given")
        if not setup.valid:
            self.warn(plane, f"{setup.reason}; the frame is black")
            self.black += 1
        return setup

    def project(self, projector: Projector, setup: PlaneSetup) -> np.ndarray | None:
        if not setup.valid:
            return None
        start = perf_counter()
        try:
            return projector.project(setup)
        except Exception as error:          # NFR-8
            self.warn(setup.plane, f"internal error while projecting ({error}); the frame is black")
            self.black += 1
            return None
        finally:
            self.projection += perf_counter() - start


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        run(args)
    except InputError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


def run(args: argparse.Namespace) -> None:
    video_path = Path(args.video)
    if not video_path.resolve().parent.is_dir():
        raise InputError(video_path, "the folder of the output file does not exist")
    state = Run()

    start = perf_counter()
    volume = read_volume(args.volume)
    planes = read_planes(args.planes)
    state.load = perf_counter() - start

    setups = [state.set_up(plane) for plane in planes]
    width, height = frame_size(setups)
    gray = GrayMap(volume.lo, volume.hi, volume.dtype)
    frame = np.zeros((height, width), dtype=np.uint8)

    start, projection_before = perf_counter(), state.projection
    try:
        with Projector(volume) as projector, VideoWriter(video_path, width, height, args.fps) as video:
            for setup in setups:
                image = state.project(projector, setup)
                video.write(place(None if image is None else gray(image), frame))
    except (OSError, RuntimeError) as error:
        raise InputError(video_path, f"the video could not be written ({error})") from None
    state.video = perf_counter() - start - (state.projection - projection_before)

    report(args, volume, len(setups), state)


def report(args: argparse.Namespace, volume, frames: int, state: Run) -> None:
    """The summary of FR-35."""
    projection = max(state.projection, 1e-9)
    print(f"volume:      {args.volume}, {' x '.join(map(str, volume.shape))}, {volume.dtype}")
    print(f"frames:      {frames} ({state.black} black, {state.warnings} warning{'' if state.warnings == 1 else 's'})")
    print(f"load:        {state.load:.2f} s")
    print(f"projection:  {state.projection:.2f} s total, {projection / frames * 1000:.1f} ms per frame, "
          f"{frames / projection:.0f} fps")
    print(f"video:       {state.video:.2f} s")


if __name__ == "__main__":
    sys.exit(main())
