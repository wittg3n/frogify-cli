from __future__ import annotations

import io
import math
import mimetypes
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from mutagen import File as MutagenFile

INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1F]')
WHITESPACE = re.compile(r"\s+")

VALID_AUDIO_EXTENSIONS = {
    "mp3",
    "m4a",
    "aac",
    "ogg",
    "opus",
    "wav",
    "flac",
    "webm",
    "mp4",
}


def legalize_filename(value: str | None, fallback: str = "audio") -> str:
    value = (value or "").strip()
    value = INVALID_FILENAME_CHARS.sub("_", value)
    value = WHITESPACE.sub(" ", value)
    value = value.rstrip(". ")

    if not value:
        value = fallback

    if re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³]", value.split(".")[0], re.I):
        value = "_" + value
    # Bound the complete stem in bytes, also keeping Unicode paths portable.
    return value.encode("utf-8")[:180].decode("utf-8", errors="ignore").rstrip(". ") or fallback


def available_audio_path(directory: Path, stem: str, extension: str = "mp3") -> Path:
    extension = extension.lstrip(".").casefold()
    if extension not in VALID_AUDIO_EXTENSIONS:
        raise ValueError(f"Unsupported audio extension: {extension}")
    stem = legalize_filename(stem)
    path = directory / f"{stem}.{extension}"
    counter = 2
    while path.exists():
        path = directory / f"{stem} ({counter}).{extension}"
        counter += 1
    return path


def publish_audio(staged: Path, destination: Path, *, overwrite: bool = False) -> Path:
    """Publish a complete file on the same volume without clobbering another download."""
    if overwrite:
        os.replace(staged, destination)
        return destination
    while True:
        try:
            if os.name == "nt":
                # Windows rename refuses an existing destination and also works on exFAT.
                os.rename(staged, destination)
            else:
                # POSIX rename replaces existing files; link refuses concurrent collisions.
                os.link(staged, destination)
                staged.unlink()
            return destination
        except FileExistsError:
            destination = available_audio_path(
                destination.parent, destination.stem, destination.suffix
            )


def bytes_to_mb(size: int) -> str:
    return f"{size / (1024 * 1024):.2f} MB"


def seconds_to_hms(seconds: float | int | None) -> str:
    if seconds is None or not math.isfinite(seconds):
        return "-:-:-"

    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)

    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"

    return f"{minutes}:{secs:02d}"


def get_audio_duration(data: bytes) -> float | None:
    if not data:
        return None

    try:
        audio = MutagenFile(io.BytesIO(data))
        if audio is None or audio.info is None:
            return None

        length = getattr(audio.info, "length", None)
        duration = float(length) if length is not None else 0.0
        return duration if math.isfinite(duration) and duration > 0 else None
    except Exception:
        return None


def guess_extension(
    url: str,
    content_type: str | None = None,
    default: str = "mp3",
) -> str:
    content_type = (content_type or "").split(";", 1)[0].strip().lower()

    content_type_map = {
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
        "audio/mp4": "m4a",
        "audio/x-m4a": "m4a",
        "audio/aac": "aac",
        "audio/ogg": "ogg",
        "application/ogg": "ogg",
        "audio/opus": "opus",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/flac": "flac",
        "audio/webm": "webm",
        "video/webm": "webm",
        "video/mp4": "mp4",
    }

    if content_type in content_type_map:
        return content_type_map[content_type]

    path = urlparse(url).path
    suffix = Path(path).suffix.lower().lstrip(".")

    if suffix in VALID_AUDIO_EXTENSIONS:
        return suffix

    guessed = mimetypes.guess_extension(content_type) if content_type else None
    if guessed:
        guessed = guessed.lstrip(".").lower()
        if guessed in VALID_AUDIO_EXTENSIONS:
            return guessed

    return default


def parse_duration_seconds(raw: dict) -> float | None:
    """
    Extract duration from search-result metadata without downloading audio.

    Handles common API representations:
      - duration_seconds: 367
      - duration: 367
      - duration: "6:07"
      - length: "6:07"
      - duration_ms: 367000
      - duration: 367000 (treated as ms when implausibly large)
    """
    if not isinstance(raw, dict):
        return None

    # Explicit millisecond fields first.
    for key in ("duration_ms", "durationMillis", "duration_milliseconds"):
        value = raw.get(key)
        if value is None:
            continue
        try:
            value = float(value)
            if math.isfinite(value) and value > 0:
                return value / 1000.0
        except (TypeError, ValueError):
            pass

    # Explicit seconds.
    for key in ("duration_seconds", "durationSeconds"):
        value = raw.get(key)
        if value is None:
            continue
        try:
            value = float(value)
            if math.isfinite(value) and value > 0:
                return value
        except (TypeError, ValueError):
            pass

    # Generic fields may contain seconds, milliseconds, or HH:MM:SS text.
    for key in ("duration", "length", "duration_string", "durationString"):
        value = raw.get(key)
        if value is None:
            continue

        if isinstance(value, str):
            value = value.strip()
            if not value:
                continue

            # 6:07 / 01:06:07
            if ":" in value:
                try:
                    parts = [float(part) for part in value.split(":")]
                    if len(parts) == 2:
                        minutes, seconds = parts
                        total = minutes * 60 + seconds
                        return total if math.isfinite(total) and total > 0 else None
                    if len(parts) == 3:
                        hours, minutes, seconds = parts
                        total = hours * 3600 + minutes * 60 + seconds
                        return total if math.isfinite(total) and total > 0 else None
                except ValueError:
                    pass

        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue

        if not math.isfinite(numeric) or numeric <= 0:
            continue

        # Audio tracks are not normally hundreds of thousands of seconds long.
        # Large generic numeric values are therefore almost certainly ms.
        if numeric > 100_000:
            return numeric / 1000.0

        return numeric

    return None
