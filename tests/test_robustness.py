"""Memory, robustness and determinism (docs/TESTING.md, sections 7.2 and 7.3)."""

import tracemalloc

import numpy as np
import pytest

import Ex0
from conftest import DATA, PROJECT_ROOT, index_volume, video_frames, video_info
from plane_projection.frames import GrayMap, frame_size, place
from plane_projection.geometry import plane_setup
from plane_projection.planes import Plane, read_planes
from plane_projection.projector import Projector
from plane_projection.volume import Volume, read_volume


@pytest.fixture
def traced():
    tracemalloc.start()
    yield
    tracemalloc.stop()


def square_plane(center, side):
    c, h = np.asarray(center, dtype=np.float64), (side - 1) / 2
    points = (c + (-h, -h, 0), c + (h, -h, 0), c + (-h, h, 0), c + (h, h, 0))
    return Plane(line=1, frame=1, points=points)


# ----- memory (section 7.2)

@pytest.mark.parametrize("dtype", [np.uint16, np.int16])
def test_volume_is_held_once(write_nrrd, traced, dtype):
    """NFR-6: after reading, the memory in use is the volume's data, within 10%"""
    path = write_nrrd((np.arange(100 * 100 * 100) % 3000 - 5).astype(dtype).reshape(100, 100, 100))
    before = tracemalloc.get_traced_memory()[0]
    volume = read_volume(path)
    in_use = tracemalloc.get_traced_memory()[0] - before
    assert volume.data.nbytes <= in_use <= 1.1 * volume.data.nbytes


def test_projection_memory_does_not_grow_with_the_volume(traced):
    """NFR-6: the same 200 x 200 plane through volumes of 100³ and 400³.

    One thread, since with several the peak depends on how the bands happen to overlap in time.
    """
    peaks = []
    for side in (100, 400):
        volume = Volume(np.asfortranarray(np.ones((side, side, side), dtype=np.uint8)))
        setup = plane_setup(square_plane((side / 2, side / 2, side / 2), 200))
        with Projector(volume, threads=1) as projector:
            tracemalloc.reset_peak()
            before = tracemalloc.get_traced_memory()[0]
            projector.project(setup)
            peaks.append(tracemalloc.get_traced_memory()[1] - before)
        del volume
    assert abs(peaks[1] - peaks[0]) <= 0.1 * peaks[0]
    assert peaks[1] < 200 * 200 * 100               # about a hundred bytes per pixel, far below the 64 MB volume


def test_run_memory_does_not_grow_with_the_number_of_planes(tmp_path, write_nrrd, write_csv, traced, capsys):
    """NFR-7: each extra plane adds far less memory than one frame, so frames are not kept"""
    volume = write_nrrd(np.ones((256, 256, 8), dtype=np.uint8))
    line = "4, 0,0,4, 0,255,4, 255,0,4, 255,255,4"       # a 256 x 256 frame of 64 KB
    peaks = {}
    for count in (10, 200):
        planes = write_csv(*[line] * count, name=f"planes{count}.csv")
        tracemalloc.reset_peak()
        before = tracemalloc.get_traced_memory()[0]
        assert Ex0.main([str(volume), str(planes), str(tmp_path / f"video{count}.mp4")]) == 0
        peaks[count] = tracemalloc.get_traced_memory()[1] - before
    capsys.readouterr()
    assert (peaks[200] - peaks[10]) / 190 < 256 * 256 / 4


# ----- robustness (section 7.3)

def random_lines(rng, count):
    """Planes files are written by people and scripts: good planes mixed with every kind of mistake."""
    odd = ["1e300", "-1e300", "nan", "inf", "-inf", "", "abc", "1e5", "0x10", "--3", "1,5", "  "]
    counts = ["3", "4", "0", "5", "3.5", "-4", "x", ""]
    lines = []
    for _ in range(count):
        kind = rng.integers(6)
        points = int(rng.choice([3, 4]))
        size = 3 * points if kind < 4 else int(rng.integers(0, 20))
        fields = [f"{rng.uniform(-10, 40):.3f}" for _ in range(size)]
        if kind == 1 and fields:                 # a strange field
            fields[rng.integers(len(fields))] = str(rng.choice(odd))
        elif kind == 2 and size >= 9:            # repeated points or points on one line
            fields[6:9] = fields[3:6] if rng.random() < 0.5 else [f"{2 * float(b) - float(a):.3f}"
                                                                   for a, b in zip(fields[0:3], fields[3:6])]
        elif kind == 5:                          # a line of commas, or a very long line
            fields = [""] * size if rng.random() < 0.5 else fields * 50
        first = str(points) if kind < 4 else str(rng.choice(counts))     # the number of points, right or wrong
        if fields and not any(fields):
            first = ""
        padding = [""] * (3 * (4 - points)) if rng.random() < 0.5 else []   # the empty fields of a missing point
        lines.append(",".join([first, *fields, *padding]))
    return lines


def test_random_lines(tmp_path, write_nrrd, write_csv, capsys):
    """NFR-8, FR-23: 1000 random lines give 1000 frames and no crash"""
    lines = random_lines(np.random.default_rng(2026), 1000)
    lines[0] = "3, 9.5,0,10, 0,19,10, 19,19,10"   # a first line that is not numbers would be a header (FR-11)
    lines = ["3,1,2,3,4,5,6,7,8,9" if not line.strip() or line.lstrip().startswith("#") else line for line in lines]
    video = tmp_path / "video.mp4"
    code = Ex0.main([str(write_nrrd(index_volume((30, 30, 30)))), str(write_csv(*lines)), str(video)])
    out, err = capsys.readouterr()
    assert code == 0
    assert "Traceback" not in err
    assert len(video_frames(video)) == 1000
    assert out.splitlines()[1].split(":", 1)[1].strip().startswith("1000 (")


def test_file_without_a_good_plane(tmp_path, write_nrrd, write_csv, capsys):
    """FR-30, NFR-8: black frames of 64 x 64"""
    video = tmp_path / "video.mp4"
    lines = ["1,2,3", "3, 0,0,0, 1,1,1, 2,2,2", "3,abc,1,2,3,4,5,6,7,8"]
    assert Ex0.main([str(write_nrrd(np.ones((4, 4, 4), np.uint8))), str(write_csv(*lines)), str(video)]) == 0
    capsys.readouterr()
    info = video_info(video)
    assert (info["width"], info["height"]) == (64, 64)
    assert all(frame.max() <= 2 for frame in video_frames(video))


@pytest.mark.parametrize("volume_name, planes_name", [("MRHead_1.nrrd", "head.csv"),
                                                      ("synthetic/dice.nrrd", "edge_cases.csv")])
def test_same_input_gives_the_same_frames(volume_name, planes_name):
    """NFR-9: the images and the frames before encoding are identical on a second run"""
    volume = read_volume(DATA / volume_name)
    setups = [plane_setup(plane) for plane in read_planes(PROJECT_ROOT / "demo" / planes_name)]
    width, height = frame_size(setups)
    gray = GrayMap(volume.lo, volume.hi, volume.dtype)

    def frames():
        with Projector(volume) as projector:
            for setup in setups:
                image = projector.project(setup) if setup.valid else None
                yield (None if image is None else image.tobytes(),
                       place(None if image is None else gray(image), np.zeros((height, width), np.uint8)).tobytes())

    assert list(frames()) == list(frames())
