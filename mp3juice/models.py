from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


@dataclass(slots=True)
class SearchResult:
    identifier: str
    title: str
    root_source: str
    duration_s: float | None = None
    duration: str = "--:--"
    raw_data: dict[str, Any] = field(default_factory=dict)

    @property
    def source_label(self) -> str:
        return self.root_source or "Unknown"


@dataclass(slots=True)
class SongInfo:
    source: str
    root_source: str
    identifier: str
    song_name: str

    singers: str = "NULL"
    album: str = "NULL"
    ext: str = "mp3"

    file_size_bytes: int = 0
    file_size: str = "0.00 MB"

    duration_s: float | None = None
    duration: str = "-:-:-"

    lyric: str = "NULL"
    cover_url: str | None = None

    download_url: str | None = None
    downloaded_contents: bytes = b""

    raw_data: dict[str, Any] = field(default_factory=dict)

    @property
    def with_valid_download_url(self) -> bool:
        return bool(self.download_url)

    def save(self, directory: str | Path = "downloads") -> Path:
        from .utils import available_audio_path, publish_audio

        if not self.downloaded_contents:
            raise ValueError("SongInfo does not contain downloaded audio bytes.")

        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)

        path = available_audio_path(directory, self.song_name, self.ext or "mp3")
        with TemporaryDirectory(prefix=".frogify-", dir=directory) as work:
            staged = Path(work) / "audio"
            staged.write_bytes(self.downloaded_contents)
            return publish_audio(staged, path)
