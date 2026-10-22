"""Writing the video (docs/TESTING.md, section 4.6)."""

import numpy as np
import pytest

from conftest import video_frames, video_info
from plane_projection.video import VideoWriter


def pattern(height, width, shift=0):
    """Stripes on the left half, and steps of brightness on the right half."""
    frame = np.zeros((height, width), dtype=np.uint8)
    frame[:, : width // 2] = ((np.arange(width // 2) // 4 + shift) % 2 * 200 + 20)[None, :]
    frame[:, width // 2:] = (np.arange(height) * 255 // (height - 1))[:, None]
    return frame


def write(path, frames, fps=30):
    height, width = frames[0].shape
    with VideoWriter(path, width, height, fps) as video:
        for frame in frames:
            video.write(frame)


def test_format_size_rate_and_count(tmp_path):
    """FR-28, FR-29, FR-33"""
    path = tmp_path / "video.mp4"
    write(path, [pattern(48, 64, i) for i in range(10)])
    assert video_info(path) == {"codec": "h264", "pixels": "yuv420p", "width": 64, "height": 48, "fps": 30.0}
    assert len(video_frames(path)) == 10


def test_frames_keep_their_order(tmp_path):
    """FR-29"""
    path = tmp_path / "video.mp4"
    write(path, [np.full((48, 64), 20 * i + 10, dtype=np.uint8) for i in range(12)])
    means = [frame.mean() for frame in video_frames(path)]
    assert means == sorted(means)
    assert np.allclose(means, [20 * i + 10 for i in range(12)], atol=2)


def test_content_survives_the_compression(tmp_path):
    """FR-28: H.264 loses a little, but each frame stays within 2 gray levels on average"""
    path = tmp_path / "video.mp4"
    frames = [pattern(96, 128, i) for i in range(5)]
    write(path, frames)
    for written, read in zip(frames, video_frames(path)):
        assert np.abs(written.astype(int) - read).mean() <= 2


def test_rate_with_a_fraction(tmp_path):
    """FR-33"""
    path = tmp_path / "video.mp4"
    write(path, [pattern(16, 16)] * 5, fps=12.5)
    assert video_info(path)["fps"] == 12.5


def test_existing_file_is_replaced(tmp_path):
    """FR-34"""
    path = tmp_path / "video.mp4"
    path.write_text("an old file")
    write(path, [pattern(16, 16)] * 3)
    assert len(video_frames(path)) == 3


def test_unfinished_file_is_deleted(tmp_path):
    """FR-3"""
    path = tmp_path / "video.mp4"
    with pytest.raises(RuntimeError, match="stopped"):
        with VideoWriter(path, 16, 16, 30) as video:
            video.write(pattern(16, 16))
            raise RuntimeError("stopped in the middle")
    assert not path.exists()


@pytest.mark.parametrize("width, height", [(15, 16), (16, 15), (0, 16)])
def test_odd_or_empty_size_is_refused(tmp_path, width, height):
    """FR-30: frame sizes are always even"""
    with pytest.raises(ValueError):
        VideoWriter(tmp_path / "video.mp4", width, height, 30)


def test_frame_of_the_wrong_size_is_refused(tmp_path):
    with VideoWriter(tmp_path / "video.mp4", 16, 16, 30) as video, pytest.raises(ValueError):
        video.write(np.zeros((16, 18), dtype=np.uint8))
