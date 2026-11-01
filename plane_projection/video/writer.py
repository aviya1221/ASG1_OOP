"""Writing the MP4 video (docs/SRS.md, FR-28, FR-33, FR-34; docs/ALGORITHM.md, section 7.4)."""

from pathlib import Path

import imageio_ffmpeg
import numpy as np

QUALITY = ["-crf", "18"]                    # H.264 quality: low enough loss to keep thin layers sharp


class VideoWriter:
    """Writes gray frames of one size to an H.264 video, one frame at a time, so the video is never held in memory.

    Use it in a with block. If the block ends with an error, the unfinished file is deleted (FR-3).
    """

    def __init__(self, path: str | Path, width: int, height: int, fps: float):
        if width <= 0 or height <= 0 or width % 2 or height % 2:
            raise ValueError(f"the frame size must be even and positive, not {width} x {height}")
        self.path = Path(path)
        self.width, self.height, self.fps = width, height, fps
        self.encoder = None

    def __enter__(self) -> "VideoWriter":
        self.encoder = imageio_ffmpeg.write_frames(
            str(self.path), (self.width, self.height), fps=self.fps, codec="libx264",
            pix_fmt_in="gray", pix_fmt_out="yuv420p", quality=None, output_params=QUALITY,
            macro_block_size=1, ffmpeg_log_level="error")
        self.encoder.send(None)             # starts FFmpeg
        return self

    def write(self, frame: np.ndarray) -> None:
        if frame.shape != (self.height, self.width) or frame.dtype != np.uint8:
            raise ValueError(f"a frame must be {self.height} x {self.width} uint8, not "
                             f"{frame.shape[0]} x {frame.shape[1]} {frame.dtype}")
        self.encoder.send(np.ascontiguousarray(frame))

    def __exit__(self, error_type, error, traceback) -> None:
        try:
            self.encoder.close()
        finally:
            if error_type is not None:
                self.path.unlink(missing_ok=True)
