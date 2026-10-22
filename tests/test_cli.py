"""The command line, Ex0.main() on small files in a temporary folder (docs/TESTING.md, section 5)."""

from pathlib import Path

import numpy as np
import pytest

import Ex0
from conftest import index_volume, video_frames, video_info
from plane_projection.projector import Projector
from plane_projection.video import VideoWriter

GOOD = [
    "9.5,0,10, 0,19,10, 19,19,10",          # a triangle of 20 x 20 pixels
    "0,0,5, 19,0,5, 0,19,5, 19,19,5",       # a rectangle of 20 x 20
    "4.5,2,3, 0,11,3, 9,11,3",              # a triangle of 10 x 10
]
ON_ONE_LINE = "0,0,0, 1,1,1, 2,2,2"
UNEQUAL_LEGS = "0,0,15, 0,10,15, 3.5157,10,15"   # legs of 10 and 10.6, high up where the volume is bright


@pytest.fixture
def files(tmp_path, write_nrrd, write_csv):
    """A 20 x 20 x 20 volume, a planes file made of the given lines, and the path of the video."""

    def make(*lines):
        volume = write_nrrd(index_volume((20, 20, 20)) + 1)
        return [str(volume), str(write_csv(*lines)), str(tmp_path / "video.mp4")]

    return make


def run(argv, capsys):
    code = Ex0.main(argv)
    out, err = capsys.readouterr()
    return code, out, err


@pytest.mark.parametrize("argv", [[], ["a.nrrd", "b.csv"], ["a.nrrd", "b.csv", "c.mp4", "--speed", "2"],
                                  ["a.nrrd", "b.csv", "c.mp4", "--fps", "0"],
                                  ["a.nrrd", "b.csv", "c.mp4", "--fps", "abc"]])
def test_wrong_arguments(argv, capsys):
    """FR-1 to FR-3"""
    with pytest.raises(SystemExit) as stop:
        Ex0.main(argv)
    assert stop.value.code == 2
    assert "usage" in capsys.readouterr().err


def test_help(capsys):
    """FR-2, NFR-15"""
    with pytest.raises(SystemExit) as stop:
        Ex0.main(["--help"])
    assert stop.value.code == 0
    text = capsys.readouterr().out
    for words in ("file.nrrd", "file.csv", "file.mp4", "--fps", "9 numbers", "12 numbers", "header",
                  "Example", "127.5,0,65, 0,255,65, 255,255,65"):
        assert words in text


def test_good_run(files, capsys):
    """FR-1, FR-29, FR-35, FR-36"""
    argv = files(*GOOD, GOOD[0], GOOD[2])
    code, out, err = run(argv, capsys)
    assert code == 0
    assert err == ""
    assert len(video_frames(argv[2])) == 5
    assert video_info(argv[2])["fps"] == 30
    lines = out.splitlines()
    assert [line.split(":")[0] for line in lines] == ["volume", "frames", "load", "projection", "video"]
    assert "20 x 20 x 20, uint32" in lines[0]
    assert lines[1].split(":", 1)[1].strip() == "5 (0 black, 0 warnings)"
    assert "fps" in lines[3]


def test_fps_option(files, capsys):
    """FR-2, FR-33"""
    argv = files(*GOOD)
    assert run(argv + ["--fps", "12.5"], capsys)[0] == 0
    assert video_info(argv[2])["fps"] == 12.5


@pytest.mark.parametrize("broken", ["volume missing", "volume invalid", "planes missing", "no planes", "no folder"])
def test_fatal_errors(files, tmp_path, write_nrrd, write_csv, broken, capsys):
    """FR-3, FR-4"""
    argv = files(*GOOD)
    if broken == "volume missing":
        argv[0] = str(tmp_path / "missing.nrrd")
    elif broken == "volume invalid":
        argv[0] = str(write_nrrd(np.zeros((4, 4, 4), np.float32), "float.nrrd"))
    elif broken == "planes missing":
        argv[1] = str(tmp_path / "missing.csv")
    elif broken == "no planes":
        argv[1] = str(write_csv("# only a comment", name="empty.csv"))
    else:
        argv[2] = str(tmp_path / "missing" / "video.mp4")
    code, out, err = run(argv, capsys)
    assert code == 1
    assert out == ""
    assert err.count("\n") == 1 and err.startswith("error: ")
    assert argv[{"volume missing": 0, "volume invalid": 0, "planes missing": 1, "no planes": 1, "no folder": 2}[broken]] in err
    assert "Traceback" not in err
    assert not (tmp_path / "video.mp4").exists()


def test_bad_and_doubtful_planes(files, capsys):
    """FR-23 to FR-27, FR-35"""
    argv = files(GOOD[0], ON_ONE_LINE, "# a comment", UNEQUAL_LEGS, GOOD[1])
    code, out, err = run(argv, capsys)
    assert code == 0
    assert err.splitlines() == [
        "warning: line 2, frame 2: points a, b and c are on one line; the frame is black",
        "warning: line 4, frame 3: the legs differ by 0.6 voxels; drawn as given",
    ]
    frames = video_frames(argv[2])
    assert len(frames) == 4
    assert frames[1].max() <= 2                         # black, within the loss of H.264
    assert frames[2].max() > 100                        # drawn
    assert "4 (1 black, 2 warnings)" in out


def test_frame_size_is_the_largest_valid_plane_rounded_up(files, capsys):
    """FR-30"""
    argv = files("10,0,10, 0,19,10, 20,19,10", GOOD[2], ON_ONE_LINE)     # 21 x 20, 10 x 10, bad
    assert run(argv, capsys)[0] == 0
    info = video_info(argv[2])
    assert (info["width"], info["height"]) == (22, 20)


def test_error_while_projecting_one_plane(files, monkeypatch, capsys):
    """NFR-8: a black frame and a warning, and the run goes on"""
    project = Projector.project

    def failing(self, setup):
        if setup.plane.frame == 2:
            raise RuntimeError("something unexpected")
        return project(self, setup)

    monkeypatch.setattr(Projector, "project", failing)
    argv = files(*GOOD)
    code, out, err = run(argv, capsys)
    assert code == 0
    assert err.splitlines() == ["warning: line 2, frame 2: internal error while projecting "
                                "(something unexpected); the frame is black"]
    assert len(video_frames(argv[2])) == 3


def test_error_while_writing_the_video(files, monkeypatch, capsys):
    """FR-3: exit code 1, and no file left behind"""

    def failing(self, frame):
        raise OSError("the disk is full")

    monkeypatch.setattr(VideoWriter, "write", failing)
    argv = files(*GOOD)
    code, out, err = run(argv, capsys)
    assert code == 1
    assert err.startswith(f"error: {argv[2]}: ") and "the disk is full" in err
    assert not Path(argv[2]).exists()
