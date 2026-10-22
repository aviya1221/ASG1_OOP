"""Shared fixtures: small volumes built in memory, and a writer for small NRRD files (docs/TESTING.md, section 2)."""

from pathlib import Path

import nrrd
import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "DATA"

CHOCOLATE, CREAM, BISCUIT = 1, 2, 3

# The image of the worked example (docs/SRS.md, section 3.4): the triangle a = (5, 0, 8), b = (1, 6, 0),
# c = (9, 6, 0) through the cake, copied square by square from DATA/images/explain/how_a_cut_is_made.png.
CAKE_TRIANGLE = ((5, 0, 8), (1, 6, 0), (9, 6, 0))
CAKE_IMAGE = np.array([
    [0, 0, 0, 0, 1, 0, 0, 0, 0],
    [0, 0, 0, 0, 1, 0, 0, 0, 0],
    [0, 0, 0, 0, 2, 0, 0, 0, 0],
    [0, 0, 0, 2, 2, 2, 0, 0, 0],
    [0, 0, 0, 2, 2, 2, 0, 0, 0],
    [0, 0, 2, 2, 2, 2, 2, 0, 0],
    [0, 0, 2, 2, 2, 2, 2, 0, 0],
    [0, 0, 3, 3, 3, 3, 3, 0, 0],
    [0, 3, 3, 3, 3, 3, 3, 3, 0],
    [0, 3, 3, 3, 3, 3, 3, 3, 0],
    [3, 3, 3, 3, 3, 3, 3, 3, 3],
], dtype=np.uint8)


def cake() -> np.ndarray:
    """The 10 x 10 x 10 cake of the worked example: biscuit for z 0 to 2, cream for z 3 to 6, chocolate for z 7 to 9."""
    data = np.zeros((10, 10, 10), dtype=np.uint8, order="F")
    data[:, :, 0:3] = BISCUIT
    data[:, :, 3:7] = CREAM
    data[:, :, 7:10] = CHOCOLATE
    return data


def index_volume(shape) -> np.ndarray:
    """A volume whose every voxel holds its own position, x + 1000·y + 1000000·z (docs/TESTING.md, section 3.3)."""
    x, y, z = np.indices(shape, dtype=np.uint32)
    return np.asfortranarray(x + 1000 * y + 1000000 * z)


def decode(value: int) -> tuple[int, int, int]:
    """The voxel that a value of the index volume came from."""
    return value % 1000, value // 1000 % 1000, value // 1000000


@pytest.fixture
def write_nrrd(tmp_path):
    """Write an array to an NRRD file in the temporary folder and return its path."""

    def write(data, name="volume.nrrd", encoding="gzip", detached=False, **header):
        path = tmp_path / name
        nrrd.write(str(path), np.asarray(data), header={"encoding": encoding, **header},
                   detached_header=detached, index_order="F")
        return path

    return write


@pytest.fixture
def write_csv(tmp_path):
    """Write lines of text to a planes file in the temporary folder and return its path."""

    def write(*lines, name="planes.csv"):
        path = tmp_path / name
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    return write
