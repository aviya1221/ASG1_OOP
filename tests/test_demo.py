"""The demo: Ex0.py as a separate process on the data set (docs/TESTING.md, section 6.2).

Each demo of section 6.1 runs once, into a temporary folder, and every test reads its results.
"""

import re
import subprocess
import sys

import numpy as np
import pytest

from conftest import DATASET, PROJECT_ROOT, video_frames, video_info
from plane_projection.video.frames import ERROR_GRAY, GrayMap
from plane_projection.volume import read_volume

pytestmark = pytest.mark.slow

DEMOS = {                                   # name: volume, frames, frame size (width, height)
    "head": ("MRHead_1.nrrd", 280, (256, 256)),
    "onion": ("onion.nrrd", 120, (256, 256)),
    "biscuit_cake": ("biscuit_cake.nrrd", 120, (256, 256)),
    "swiss_roll": ("swiss_roll.nrrd", 120, (256, 256)),
    "croissant": ("croissant.nrrd", 100, (502, 502)),
    "edge_cases": ("synthetic/dice.nrrd", 16, (282, 244)),
    "lecturer_example": ("croissant.nrrd", 4, (454, 502)),
}

# The warnings of the files that are not clean, as listed in docs/TESTING.md, section 6.1
WARNINGS = {
    "edge_cases": [
        "warning: line 29, frame 7: the legs differ by 37.8 voxels; drawn as given",
        "warning: line 31, frame 8: the top side a' a'' is not parallel to the base: its ends differ by 16 voxels; "
        "drawn as given",
        "warning: line 35, frame 9: 9 numbers for 4 points instead of 12; drawn as an error frame",
        "warning: line 37, frame 10: field 10 is not a number: 'abc'; drawn as an error frame",
        "warning: line 39, frame 11: field 7 is not a finite number: 'inf'; drawn as an error frame",
        "warning: line 41, frame 12: b and c are the same point; drawn as an error frame",
        "warning: line 43, frame 13: points a, b and c are on one line; drawn as an error frame",
        "warning: line 45, frame 14: point a'' is 10 voxels off the plane of a', b and c; drawn as an error frame",
        "warning: line 47, frame 15: the sides of the trapezoid a', a'', c, b cross each other; drawn as an error frame",
        "warning: line 49, frame 16: the image would be 10200 x 180 pixels, more than 4096 on a side; "
        "drawn as an error frame",
    ],
    "lecturer_example": [
        "warning: line 4, frame 3: the legs differ by 20.5 voxels; drawn as given",
    ],
}
BLACK_FRAMES = [6]                          # the plane outside the volume
ERROR_FRAMES = list(range(9, 17))           # the bad lines


@pytest.fixture(scope="module")
def demos(tmp_path_factory):
    """Run every demo once: name -> (completed process, path of the video)."""
    out = tmp_path_factory.mktemp("demo")
    results = {}
    for name, (volume, _, _) in DEMOS.items():
        video = out / f"{name}.mp4"
        command = [sys.executable, "Ex0.py", str(DATASET / volume), str((DATASET / volume).with_name(f"{name}.csv")), str(video)]
        results[name] = (subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True, text=True), video)
    return results


@pytest.mark.parametrize("name", DEMOS)
def test_exit_code_and_video(demos, name):
    """FR-3, FR-28, FR-33"""
    process, video = demos[name]
    assert process.returncode == 0, process.stderr
    width, height = DEMOS[name][2]
    assert video_info(video) == {"codec": "h264", "pixels": "yuv420p", "width": width, "height": height, "fps": 30.0}


@pytest.mark.parametrize("name", DEMOS)
def test_one_frame_per_plane_line(demos, name):
    """FR-23, FR-29"""
    assert len(video_frames(demos[name][1])) == DEMOS[name][1]


@pytest.mark.parametrize("name", [name for name in DEMOS if name not in WARNINGS])
def test_clean_files_give_no_warnings(demos, name):
    """FR-36"""
    assert demos[name][0].stderr == ""


@pytest.mark.parametrize("name", WARNINGS)
def test_expected_warnings(demos, name):
    """FR-24 to FR-27, FR-36"""
    assert demos[name][0].stderr.splitlines() == WARNINGS[name]


@pytest.mark.parametrize("name", DEMOS)
def test_summary(demos, name):
    """FR-35"""
    lines = demos[name][0].stdout.splitlines()
    assert [line.split(":")[0] for line in lines[:5]] == ["volume", "frames", "load", "projection", "video"]
    assert len(lines) == (5 if name != "edge_cases" else 5 + 2 + len(ERROR_FRAMES))
    assert lines[1].split(":", 1)[1].strip().startswith(f"{DEMOS[name][1]} (")
    assert lines[3].endswith(" fps")


def test_error_list_of_the_edge_cases(demos):
    """FR-35: the error frames, listed after the summary with the causes of their warnings"""
    lines = demos["edge_cases"][0].stdout.splitlines()
    assert lines[1].split(":", 1)[1].strip() == "16 (8 errors, 2 warnings)"
    assert lines[5:7] == ["", "8 frames could not be drawn and show an error:"]
    expected = []
    for warning in WARNINGS["edge_cases"]:
        found = re.fullmatch(r"warning: line (\d+), frame (\d+): (.*); drawn as an error frame", warning)
        if found:
            line, frame, cause = found.groups()
            expected.append(f"  frame {frame:<2}  line {line}  {cause}")
    assert lines[7:] == expected


def test_black_and_error_frames_of_the_edge_cases(demos):
    """FR-24, FR-26: black within the loss of H.264, or an error frame, gray with white text; the rest are drawn"""
    frames = video_frames(demos["edge_cases"][1])
    for number, frame in enumerate(frames, start=1):
        assert (frame.max() <= 2) == (number in BLACK_FRAMES), f"frame {number}"
        is_error = abs(np.median(frame) - ERROR_GRAY) <= 4 and frame.max() > 200
        assert is_error == (number in ERROR_FRAMES), f"frame {number}"


def test_known_head_frame(demos):
    """FR-19, FR-32: frame 66 is the slice z = 65, after the gray map, within the loss of H.264.

    On the noise of the MRI the loss is about 2.5 gray levels on average, and the neighboring slices
    are 6 or more away, so frame 66 must be within 3 of slice 65 and closer to it than to its neighbors.
    """
    volume = read_volume(DATASET / "MRHead_1.nrrd")
    gray = GrayMap(volume.lo, volume.hi, volume.dtype)
    frame = video_frames(demos["head"][1])[65].astype(int)
    distance = {z: np.abs(frame - gray(volume.data[:, :, z].T)).mean() for z in range(62, 69)}
    assert distance[65] <= 3
    assert min(distance, key=distance.get) == 65
