"""Reading the volume from an NRRD file (docs/SRS.md, section 3.2; docs/ALGORITHM.md, section 3.1)."""

import zlib
from dataclasses import dataclass, field
from pathlib import Path

import nrrd
import numpy as np

from plane_projection.errors import InputError

MAX_SIZE = 1023
TYPES = (np.uint8, np.uint16, np.uint32, np.int8, np.int16, np.int32)
ENCODINGS = ("raw", "gzip", "gz")
READ_ERRORS = (nrrd.NRRDError, OSError, ValueError, EOFError, zlib.error, UnicodeDecodeError)


@dataclass(frozen=True, eq=False)
class Volume:
    """The 3D matrix M, indexed [x, y, z] with x fastest in memory, in the value type of its file.

    flat is a 1D view of the same memory, where voxel (x, y, z) is flat[x + sx·(y + sy·z)].
    lo and hi are the smallest and largest values, for the gray levels of the video.
    """

    data: np.ndarray
    flat: np.ndarray = field(init=False)
    lo: int = field(init=False)
    hi: int = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, "flat", self.data.reshape(-1, order="F"))
        object.__setattr__(self, "lo", int(self.data.min()))
        object.__setattr__(self, "hi", int(self.data.max()))

    @property
    def shape(self) -> tuple[int, int, int]:
        return self.data.shape

    @property
    def dtype(self) -> np.dtype:
        return self.data.dtype


def read_volume(path: str | Path) -> Volume:
    """Read and check an NRRD volume. Any problem raises InputError naming the file (FR-4)."""
    path = Path(path)
    if not path.is_file():
        raise InputError(path, "file not found")
    try:
        header = nrrd.read_header(str(path))
    except READ_ERRORS as error:
        raise InputError(path, f"not a readable NRRD file ({error})") from None
    check_header(path, header)
    try:
        data, _ = nrrd.read(str(path), index_order="F")
    except READ_ERRORS as error:
        raise InputError(path, f"the data cannot be read ({error})") from None
    return Volume(prepare(path, data))


def check_header(path: Path, header: dict) -> None:
    """The checks that need only the header: one file, 3 dimensions, encoding, sizes (FR-5, FR-7)."""
    if "data file" in header or "datafile" in header:
        raise InputError(path, "the data is in a separate file (detached header); use a single .nrrd file")
    if header.get("dimension") != 3:
        raise InputError(path, f"the volume has {header.get('dimension')} dimensions instead of 3")
    if header.get("encoding") not in ENCODINGS:
        raise InputError(path, f"the encoding {header.get('encoding')!r} is not supported; use raw or gzip")
    sizes = [int(size) for size in header["sizes"]]
    if not all(1 <= size <= MAX_SIZE for size in sizes):
        raise InputError(path, f"the sizes {' x '.join(map(str, sizes))} are not all between 1 and {MAX_SIZE}")


def prepare(path: Path, data: np.ndarray) -> np.ndarray:
    """Check the value type, and set negative values to 0 in place (FR-6)."""
    if data.dtype.newbyteorder("=") not in [np.dtype(t) for t in TYPES]:
        raise InputError(path, f"the value type {data.dtype.name} is not supported; "
                               "use 8, 16 or 32-bit integers")
    if not data.dtype.isnative:
        data = data.astype(data.dtype.newbyteorder("="))
    data = np.asfortranarray(data)
    if data.dtype.kind == "i":
        if not data.flags.writeable:
            data = data.copy(order="F")
        np.maximum(data, 0, out=data)
    return data
