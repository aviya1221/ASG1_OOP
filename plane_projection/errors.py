"""The error that stops the program (docs/SRS.md, FR-4)."""

from pathlib import Path


class InputError(Exception):
    """A problem with an input or output file, found before the video is written.

    It names the file and the cause, so the program can print one line without a traceback.
    """

    def __init__(self, path: str | Path, cause: str):
        self.path = str(path)
        self.cause = cause
        super().__init__(f"{self.path}: {cause}")
