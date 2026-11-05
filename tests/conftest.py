"""Shared fixtures: small volumes built in memory, a writer for small NRRD files (docs/TESTING.md, section 2),
and failure messages that say where the failure is (docs/TESTING.md, section 1)."""

import re
import subprocess
from pathlib import Path

import imageio_ffmpeg
import nrrd
import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASET = PROJECT_ROOT / "DATASET"
SHOWN = 5                                   # differences that a failure message lists

CHOCOLATE, CREAM, BISCUIT = 1, 2, 3

# The image of the worked example (docs/ALGORITHM.md, section 5.3): the triangle a = (5, 0, 8), b = (1, 6, 0),
# c = (9, 6, 0) through the cake, copied square by square from docs/images/how_a_cut_is_made.png.
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
    value = int(value)
    return value % 1000, value // 1000 % 1000, value // 1000000


def assert_same(actual, expected, what: str = "pixels", show=str) -> None:
    """Fail with the places where two arrays differ, and the values found and expected there.

    expected may be a single value, for an array that must hold only that value. show formats a value, such as decode.
    """
    __tracebackhide__ = True                # the failure points at the line of the test, not at this function
    actual = np.asarray(actual)
    expected = np.broadcast_to(expected, actual.shape) if np.ndim(expected) == 0 else np.asarray(expected)
    if actual.shape != expected.shape:
        raise AssertionError(f"the shape is {actual.shape}, expected {expected.shape}")
    places = np.argwhere(actual != expected)
    if len(places):
        listed = "; ".join(f"{tuple(int(i) for i in place)} is {show(actual[tuple(place)])}, "
                           f"expected {show(expected[tuple(place)])}" for place in places[:SHOWN])
        more = f"; and {len(places) - SHOWN} more" if len(places) > SHOWN else ""
        raise AssertionError(f"{len(places)} of {actual.size} {what} differ: {listed}{more}")


def video_info(path) -> dict:
    """Codec, pixel format, size and rate of a video, as FFmpeg reports them."""
    result = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(path)],
                            capture_output=True, text=True)
    stream = next(line for line in result.stderr.splitlines() if "Video:" in line)
    width, height = re.search(r", (\d+)x(\d+)", stream).groups()
    return {
        "codec": re.search(r"Video: (\w+)", stream).group(1),
        "pixels": re.search(r"Video: [^,]+, (\w+)", stream).group(1),
        "width": int(width),
        "height": int(height),
        "fps": float(re.search(r", ([\d.]+) fps", stream).group(1)),
    }


def video_frames(path) -> list[np.ndarray]:
    """Every frame of a video, decoded to gray levels."""
    reader = imageio_ffmpeg.read_frames(str(path), pix_fmt="gray", bpp=1)
    width, height = next(reader)["size"]
    return [np.frombuffer(frame, dtype=np.uint8).reshape(height, width) for frame in reader]


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


# ----- where each failure is: listed as file:line at the end of the run (docs/TESTING.md, section 1)

@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    if report.failed and call.excinfo is not None:
        report.where = where(call.excinfo)
    return report


def where(excinfo) -> tuple[str | None, str | None, str]:
    """The line of the test that failed, the deeper line of the project that raised the error if there is one, and the message."""
    ours = [entry for entry in excinfo.traceback if not entry.ishidden(excinfo) and in_project(entry.path)]
    places = [f"{Path(entry.path).resolve().relative_to(PROJECT_ROOT).as_posix()}:{entry.lineno + 1}" for entry in ours]
    text = str(excinfo.value) if excinfo.errisinstance(AssertionError) else f"{excinfo.typename}: {excinfo.value}"
    lines = [line for line in text.splitlines() if line.strip()]
    message = lines[0] if lines else excinfo.typename
    if not places:
        return None, None, message
    return places[0], places[-1] if len(places) > 1 else None, message


def in_project(path) -> bool:
    """A file of the project, not of Python or of an installed package."""
    path = Path(path)
    if not path.is_file():
        return False
    try:
        relative = path.resolve().relative_to(PROJECT_ROOT)
    except ValueError:
        return False
    return not relative.parts[0].startswith(".")     # .venv


def pytest_terminal_summary(terminalreporter):
    """List the failures by file and line, between the details of pytest and its short summary."""
    reports = [report for key in ("failed", "error") for report in terminalreporter.stats.get(key, [])
               if hasattr(report, "where")]
    if not reports:
        return
    terminalreporter.section("where the tests failed")
    for report in reports:
        test, raised, message = report.where
        name = report.head_line if report.when == "call" else f"{report.head_line}, in {report.when}"
        terminalreporter.line(f"{test or report.nodeid}  {name}")
        terminalreporter.line(f"    {raised}  {message}" if raised else f"    {message}")
