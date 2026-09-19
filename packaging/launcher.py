"""Standalone entry point; CLI behavior stays in frogify.cli.app."""

import os

# The loader has already located bundled libraries. External FFmpeg/ffprobe/
# aria2 must inherit the user's library path, not PyInstaller's private one.
# https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html
if "LD_LIBRARY_PATH_ORIG" in os.environ:
    os.environ["LD_LIBRARY_PATH"] = os.environ["LD_LIBRARY_PATH_ORIG"]
else:
    os.environ.pop("LD_LIBRARY_PATH", None)

from frogify.cli.app import main  # noqa: E402

if __name__ == "__main__":
    main()
