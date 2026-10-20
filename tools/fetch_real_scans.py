"""Download real CT scans of layered objects and save them as NRRD files for 3D Slicer.

The scans come from the Open Scientific Visualization Datasets collection
(https://klacansky.com/open-scivis-datasets/), which gathers public volume data with credits.
Each raw file is checked against the collection's SHA-512 checksum before it is converted.

    boston_teapot.nrrd   uint8    a ceramic teapot with a small lobster inside
    tooth.nrrd           uint8    a tooth: enamel, dentin and the pulp canal
    engine.nrrd          uint8    two cylinders of an engine block
    carp.nrrd            uint16   a carp: skin, muscle, skeleton and swim bladder

The raw files are stored with x varying fastest, the same order as NRRD, so they convert directly.
Each volume is turned so that the object stands upright in 3D Slicer (z points up).
By default the files are written to DATA/real_scans/.

Usage:
    python tools/fetch_real_scans.py [--out DIR] [--cache DIR]
"""

import argparse
import hashlib
import shutil
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import nrrd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Plain HTTP: the collection's HTTPS port does not answer. The SHA-512 checks protect the data.
SOURCE = "http://klacansky.com/open-scivis-datasets"


@dataclass(frozen=True)
class RealScan:
    filename: str        # output file name
    raw: str             # file name in the collection
    sha512: str
    dtype: str
    size: tuple          # voxels along the raw file's x, y, z
    spacing: tuple       # mm along the raw file's x, y, z
    axes: tuple          # raw axes in output order, so the object stands upright
    flip: tuple          # output axes to reverse, so the object is not upside down
    content: str
    credit: str


SCANS = [
    RealScan("boston_teapot.nrrd", "boston_teapot/boston_teapot_256x256x178_uint8.raw",
             "b2bf7ba8ba7a7d5a8ea76ccd8fd2c0f5f043079a83cd6a3055e85f5e0a40c1c4d872b9bbc7aedf628989eb57bffd5729767c29fe8ae018c581406b196caa6359",
             # The teapot lies along the raw y axis with its lid toward -y: swap y and z, then flip z
             # (two mirror steps, so a rotation; the teapot is not mirrored).
             "uint8", (256, 256, 178), (1.0, 1.0, 1.0), axes=(0, 2, 1), flip=(2,),
             content="CT scan of the SIGGRAPH 1989 teapot with a small version of the AVS lobster inside",
             credit="volvis.org and Terarecon Inc, MERL, Brigham and Women's Hospital"),
    RealScan("tooth.nrrd", "tooth/tooth_103x94x161_uint8.raw",
             "5ee3d77ae951e129d29062a4fd4d8730fd8670bdaf4d01ddf907848072180cbfea8ab897880147d2a79dc7f1d1806a34b32853074eca88f6758e01382469f9f6",
             "uint8", (103, 94, 161), (1.0, 1.0, 1.0), axes=(0, 1, 2), flip=(),
             content="Micro CT scan of a tooth",
             credit="GE Aircraft Engines, Evendale, Ohio, USA"),
    RealScan("engine.nrrd", "engine/engine_256x256x128_uint8.raw",
             "f17228483b1b5edb90146eac90ba979531629a2880d9e7a0493a98290da8af6ac2cf80f2c567a3d08695dc7dd854916c861dad8856b2d5721501954e913de13f",
             "uint8", (256, 256, 128), (1.0, 1.0, 1.0), axes=(0, 1, 2), flip=(),
             content="CT scan of two cylinders of an engine block",
             credit="volvis.org and General Electric"),
    RealScan("carp.nrrd", "carp/carp_256x256x512_uint16.raw",
             "0ec57ca05d700e25a87cc2ca976c066f52e254c0269aa5fb7decb08ba3607cbf996b5d72aac8671dfe6589a794935d3fd820aaa756e6f6d32b84def15455fea5",
             # The fish lies along z with its head at the bottom: turn it 180 degrees about y (flip x
             # and z), so the head is up, as in a medical scan.
             "uint16", (256, 256, 512), (0.78125, 0.390625, 1.0), axes=(0, 1, 2), flip=(0, 2),
             content="CT scan of a carp fish",
             credit="Michael Scheuring, Computer Graphics Group, University of Erlangen, Germany"),
]


class FetchError(Exception):
    """A download or a converted file is not what it should be."""


def check(condition: bool, message: str) -> None:
    if not condition:
        raise FetchError(message)


def sha512_of(path: Path) -> str:
    digest = hashlib.sha512()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def download(scan: RealScan, cache: Path) -> Path:
    """Return a verified local copy of the scan's raw file, downloading it if needed."""
    target = cache / Path(scan.raw).name
    if target.exists() and sha512_of(target) == scan.sha512:
        return target
    cache.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    url = f"{SOURCE}/{scan.raw}"
    print(f"downloading {url}")
    with urllib.request.urlopen(url, timeout=120) as response, open(partial, "wb") as out:
        shutil.copyfileobj(response, out, 1 << 20)
    check(sha512_of(partial) == scan.sha512, f"{partial.name}: SHA-512 checksum does not match the collection's")
    partial.replace(target)
    return target


def load(scan: RealScan, raw: Path):
    """Read the raw file and turn it upright. Returns the data, indexed [x, y, z], and its spacing."""
    expected = int(np.prod(scan.size)) * np.dtype(scan.dtype).itemsize
    check(raw.stat().st_size == expected, f"{raw.name}: {raw.stat().st_size} bytes, expected {expected}")
    data = np.fromfile(raw, dtype=np.dtype(scan.dtype).newbyteorder("<")).reshape(scan.size, order="F")
    data = np.transpose(data, scan.axes)
    for axis in scan.flip:
        data = np.flip(data, axis)
    spacing = tuple(scan.spacing[a] for a in scan.axes)
    return np.ascontiguousarray(data).astype(np.dtype(scan.dtype)), spacing


def save(scan: RealScan, data: np.ndarray, spacing, path: Path) -> None:
    header = {
        "space": "left-posterior-superior",
        "space directions": np.diag(spacing),
        "space origin": np.zeros(3),
        "kinds": ["domain", "domain", "domain"],
        "encoding": "gzip",
        "content": scan.content,
        "source": f"{SOURCE}/{scan.raw}",  # key/value pairs, kept for the record
        "credit": scan.credit,
    }
    nrrd.write(str(path), data, header=header, index_order="F")
    written, _ = nrrd.read(str(path), index_order="F")
    check(np.array_equal(written, data), f"{path.name}: data read back differs from data written")


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download real CT scans of layered objects as NRRD files.")
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "DATA" / "real_scans",
                        help="output folder (default: DATA/real_scans/ in the project)")
    parser.add_argument("--cache", type=Path, default=Path(tempfile.gettempdir()) / "open_scivis_raw",
                        help="folder for the downloaded raw files (default: the system temp folder)")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    for scan in SCANS:
        data, spacing = load(scan, download(scan, args.cache))
        path = args.out / scan.filename
        save(scan, data, spacing, path)
        shape = " x ".join(map(str, data.shape))
        mm = " x ".join(f"{s:g}" for s in spacing)
        print(f"{path.name}: {data.dtype}, {shape} voxels of {mm} mm, values {data.min()}..{data.max()}, "
              f"{path.stat().st_size / 1e6:.2f} MB")
    print("All scans downloaded, verified and converted.")


if __name__ == "__main__":
    main()
