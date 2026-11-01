"""From planes to frames: the loop of every run (docs/ALGORITHM.md, sections 1.2 and 8.1).

Ex0.py and the tests draw frames through the same Renderer, so the tests check the loop that the program runs.
"""

from dataclasses import dataclass
from time import perf_counter

import numpy as np

from plane_projection.frames import GrayMap, error_frame, frame_size, place
from plane_projection.geometry import PlaneSetup, plane_setup
from plane_projection.planes import Plane
from plane_projection.projector import THREADS, Projector
from plane_projection.volume import Volume

INTERNAL = "INTERNAL ERROR"                 # the short cause of an unexpected error (FR-24c, NFR-8)


def safe_setup(plane: Plane) -> PlaneSetup:
    """plane_setup, where an unexpected error makes the plane bad instead of stopping the run (FR-24c, NFR-8)."""
    try:
        return plane_setup(plane)
    except Exception as error:
        return PlaneSetup(plane, reason=f"internal error in the setup ({error})", title=INTERNAL)


@dataclass(frozen=True, eq=False)
class Drawn:
    """One frame of the video, and what it shows.

    setup is the setup of the plane, or a bad setup that says why its projection failed. image is the image E of the
    plane, or None for an error frame. frame is the one frame buffer of the renderer, which the next frame overwrites.
    """

    setup: PlaneSetup
    image: np.ndarray | None
    frame: np.ndarray


class Renderer:
    """Draws the frame of each plane through one volume, one plane at a time (FR-24, FR-30 to FR-32).

    Every frame has the size of the largest valid plane and is drawn into one buffer, so frames are never kept (NFR-6).
    projection adds up the seconds spent projecting (NFR-3). Use it in a with block, which stops the projector's threads.
    """

    def __init__(self, volume: Volume, setups: list[PlaneSetup], threads: int = THREADS):
        self.width, self.height = frame_size(setups)
        self.gray = GrayMap(volume.lo, volume.hi, volume.dtype)
        self.frame = np.zeros((self.height, self.width), dtype=np.uint8)
        self.projector = Projector(volume, threads)
        self.projection = 0.0

    def __enter__(self) -> "Renderer":
        return self

    def __exit__(self, *exception) -> None:
        self.projector.close()

    def draw(self, setup: PlaneSetup) -> Drawn:
        """The gray image of a valid plane in the middle of the frame, or the error frame of a bad one."""
        if setup.valid:
            start = perf_counter()
            try:
                image = self.projector.project(setup)
            except Exception as error:      # FR-24c, NFR-8: no plane can stop the run
                setup = PlaneSetup(setup.plane, reason=f"internal error while projecting ({error})", title=INTERNAL)
            finally:
                self.projection += perf_counter() - start
            if setup.valid:
                return Drawn(setup, image, place(self.gray(image), self.frame))
        return Drawn(setup, None, error_frame(setup, self.frame))
