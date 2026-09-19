from __future__ import annotations

import csv
import math
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from rapidfuzz import fuzz

from .client import MP3JuiceMusicClient
from .exceptions import DownloadError, MP3JuiceError, SearchError
from .models import SearchResult
from .utils import available_audio_path, legalize_filename, publish_audio, seconds_to_hms

# Words/phrases that commonly describe the YouTube upload rather than the song.
# They are deliberately treated as neutral when they exist only in the result.
NEUTRAL_RESULT_QUALIFIERS = (
    "official music video",
    "official video",
    "official audio",
    "official lyric video",
    "official lyrics video",
    "official visualizer",
    "official visualiser",
    "music video",
    "lyric video",
    "lyrics video",
    "official",
    "lyrics",
    "lyric",
    "audio",
    "video",
    "visualizer",
    "visualiser",
    "hd",
    "4k",
    "hq",
)

# These change the musical recording. If they occur in the candidate but not in
# the Spotify title, they reduce confidence. If they are part of the Spotify
# title itself, they are expected and are not penalized.
VERSION_QUALIFIERS: dict[str, int] = {
    "karaoke": 35,
    "instrumental": 32,
    "sped up": 30,
    "speed up": 30,
    "slowed": 30,
    "slowed reverb": 30,
    "reverb": 24,
    "nightcore": 30,
    "cover": 28,
    "remix": 22,
    "mashup": 24,
    "live": 20,
    "acoustic": 18,
    "edit": 17,
    "extended": 17,
    "radio edit": 16,
    "mix": 14,
    "demo": 16,
    "session": 14,
    "performance": 12,
    "remaster": 10,
    "remastered": 10,
}

FEATURE_RE = re.compile(
    r"\b(?:feat(?:uring)?\.?|ft\.?)\s+[^\]\)\-–—]+",
    re.IGNORECASE,
)
BRACKET_RE = re.compile(r"[\(\[\{]([^\)\]\}]*)[\)\]\}]")
WHITESPACE_RE = re.compile(r"\s+")
NON_WORD_RE = re.compile(r"[^\w\s]+", re.UNICODE)


@dataclass(slots=True)
class SpotifyTrack:
    row_number: int
    uri: str
    track_name: str
    album_name: str
    artists_display: str
    artists: list[str]
    release_date: str
    duration_s: float
    popularity: str = ""
    explicit: str = ""
    genres: str = ""
    record_label: str = ""

    @property
    def primary_artist(self) -> str:
        return self.artists[0] if self.artists else self.artists_display

    @property
    def expected_duration(self) -> str:
        return seconds_to_hms(self.duration_s)

    @classmethod
    def from_csv_row(cls, row_number: int, row: dict[str, str | None]) -> SpotifyTrack:
        row = {key: "" if value is None else str(value).strip() for key, value in row.items()}
        required = ("Track URI", "Track Name", "Artist Name(s)", "Duration (ms)")
        missing = [name for name in required if not str(row.get(name, "")).strip()]
        if missing:
            raise ValueError(f"missing required field(s): {', '.join(missing)}")

        artists_display = str(row["Artist Name(s)"]).strip()
        artists = [part.strip() for part in artists_display.split(";") if part.strip()]

        try:
            duration_s = float(str(row["Duration (ms)"]).strip()) / 1000.0
        except ValueError as exc:
            raise ValueError("Duration (ms) is not numeric") from exc

        if not math.isfinite(duration_s) or duration_s <= 0:
            raise ValueError("Duration (ms) must be > 0")

        return cls(
            row_number=row_number,
            uri=str(row["Track URI"]).strip(),
            track_name=str(row["Track Name"]).strip(),
            album_name=str(row.get("Album Name", "") or "").strip(),
            artists_display=artists_display,
            artists=artists,
            release_date=str(row.get("Release Date", "") or "").strip(),
            duration_s=duration_s,
            popularity=str(row.get("Popularity", "") or "").strip(),
            explicit=str(row.get("Explicit", "") or "").strip(),
            genres=str(row.get("Genres", "") or "").strip(),
            record_label=str(row.get("Record Label", "") or "").strip(),
        )


@dataclass(slots=True)
class CandidateScore:
    result: SearchResult
    total_score: float
    title_score: float
    artist_score: float
    duration_score: float
    duration_diff_s: float | None
    qualifier_penalty: float
    accepted: bool
    reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BatchCallbacks:
    on_track_start: Callable[[int, int, SpotifyTrack], None] | None = None
    on_status: Callable[[str], None] | None = None
    on_download_start: Callable[[SearchResult], None] | None = None
    on_download_progress: Callable[[int, int | None], None] | None = None
    on_track_success: Callable[[SpotifyTrack, Path, CandidateScore], None] | None = None
    on_track_failure: Callable[[SpotifyTrack, str], None] | None = None


def _ascii_fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_text(value: str) -> str:
    value = _ascii_fold(value or "").casefold()
    value = value.replace("&", " and ")
    value = value.replace("+", " and ")
    value = value.replace("’", "'").replace("`", "'")
    value = value.replace("–", "-").replace("—", "-")
    value = NON_WORD_RE.sub(" ", value)
    return WHITESPACE_RE.sub(" ", value).strip()


def contains_phrase(text: str, phrase: str) -> bool:
    text = normalize_text(text)
    phrase = normalize_text(phrase)
    if not text or not phrase:
        return False
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text) is not None


def strip_neutral_qualifiers(value: str) -> str:
    """Remove upload-only labels while preserving real words in song titles."""
    text = value

    def replace_bracket(match: re.Match[str]) -> str:
        content = normalize_text(match.group(1))
        if not content:
            return " "
        if any(q in content for q in NEUTRAL_RESULT_QUALIFIERS):
            # Keep any meaningful version word if a bracket contains both
            # neutral and recording-specific text.
            kept = [q for q in VERSION_QUALIFIERS if q in content]
            return " " + " ".join(kept) + " " if kept else " "
        return " " + match.group(1) + " "

    text = BRACKET_RE.sub(replace_bracket, text)
    normalized = normalize_text(text)

    # Neutral labels may also appear without brackets, usually as upload
    # suffixes: "Adele - Hello Official Video". Only strip suffixes so real
    # titles such as "Video Games" or "Audio" remain intact.
    changed = True
    while changed and normalized:
        changed = False
        for qualifier in sorted(NEUTRAL_RESULT_QUALIFIERS, key=len, reverse=True):
            q = normalize_text(qualifier)
            if normalized == q:
                continue
            if normalized.endswith(" " + q):
                normalized = normalized[: -(len(q) + 1)].strip()
                changed = True
                break

    return WHITESPACE_RE.sub(" ", normalized).strip()


def target_title_core(value: str) -> str:
    # Spotify title is the source of truth; do not delete words such as
    # "video", "audio", or "lyrics" when they are genuinely in the title.
    value = FEATURE_RE.sub(" ", value)
    return normalize_text(value)


def candidate_title_core(value: str) -> str:
    value = FEATURE_RE.sub(" ", value)
    return strip_neutral_qualifiers(value)


def _candidate_metadata_text(result: SearchResult) -> str:
    raw = result.raw_data or {}
    fields = [result.title]
    for key in (
        "artist",
        "artists",
        "author",
        "uploader",
        "channel",
        "username",
        "user",
    ):
        value = raw.get(key)
        if isinstance(value, str):
            fields.append(value)
        elif isinstance(value, list):
            fields.extend(str(x) for x in value if x)
        elif isinstance(value, dict):
            fields.extend(str(x) for x in value.values() if isinstance(x, str))
    return " ".join(fields)


def _title_similarity(track: SpotifyTrack, result: SearchResult) -> float:
    target = target_title_core(track.track_name)
    candidate = candidate_title_core(result.title)

    if not target or not candidate:
        return 0.0

    scores = [
        float(fuzz.ratio(target, candidate)),
        float(fuzz.partial_ratio(target, candidate)),
        float(fuzz.token_set_ratio(target, candidate)),
        float(fuzz.token_sort_ratio(target, candidate)),
    ]

    # Search result titles often use "Artist - Track". Compare the target
    # against each dash-separated portion too.
    for piece in re.split(r"\s[-–—|:]\s", result.title):
        piece = candidate_title_core(piece)
        if piece:
            scores.extend(
                (
                    float(fuzz.ratio(target, piece)),
                    float(fuzz.token_set_ratio(target, piece)),
                )
            )

    best = max(scores)
    if target in candidate:
        best = min(100.0, best + 4.0)
    return best


def _artist_similarity(track: SpotifyTrack, result: SearchResult) -> float:
    candidate_text = normalize_text(_candidate_metadata_text(result))
    if not candidate_text or not track.artists:
        return 0.0

    artist_scores: list[float] = []
    for artist in track.artists:
        normalized_artist = normalize_text(artist)
        if not normalized_artist:
            continue
        if contains_phrase(candidate_text, normalized_artist):
            artist_scores.append(100.0)
        else:
            artist_scores.append(
                max(
                    float(fuzz.partial_ratio(normalized_artist, candidate_text)),
                    float(fuzz.token_set_ratio(normalized_artist, candidate_text)),
                )
            )

    if not artist_scores:
        return 0.0

    # Primary artist/composer is the strongest identity signal. Additional
    # collaborators improve the score but are not mandatory because uploads
    # often omit featured/performance credits.
    primary = artist_scores[0]
    extras = max(artist_scores[1:], default=primary)
    return min(100.0, primary * 0.82 + extras * 0.18)


def _qualifier_penalty(track: SpotifyTrack, result: SearchResult) -> tuple[float, list[str]]:
    target = normalize_text(track.track_name)
    candidate = normalize_text(result.title)
    # Remove recognized artist credit at the title boundary, never occurrences
    # inside the track portion (Live - Lightning Crashes (Live) stays live).
    for artist in sorted(track.artists, key=len, reverse=True):
        credit = normalize_text(artist)
        if credit and candidate.startswith(credit + " "):
            candidate = candidate[len(credit) :].strip()
        elif credit and normalize_text(re.split(r"\s[-–—|:]\s", result.title)[-1]) == credit:
            candidate = candidate[: -len(credit)].strip()
    penalty = 0.0
    reasons: list[str] = []

    for qualifier, weight in VERSION_QUALIFIERS.items():
        q = normalize_text(qualifier)
        target_has = contains_phrase(target, q)
        candidate_has = contains_phrase(candidate, q)

        if candidate_has and not target_has:
            penalty += weight
            reasons.append(f"unexpected '{qualifier}'")
        elif target_has and not candidate_has:
            # "Original Mix" / "Album Mix" are commonly omitted from upload
            # titles even when the audio is the same master. Do not hard-fail
            # solely because the generic word "mix" is absent. Materially
            # different qualifiers such as remix/live/extended remain strict.
            soft_missing_mix = qualifier == "mix" and (
                contains_phrase(target, "original mix") or contains_phrase(target, "album mix")
            )
            if soft_missing_mix:
                continue

            # Missing a requested recording version is otherwise meaningful,
            # but slightly less severe than explicitly finding the wrong one.
            missing_weight = max(8, int(weight * 0.65))
            penalty += missing_weight
            reasons.append(f"missing requested '{qualifier}'")

    return min(penalty, 55.0), reasons


def score_candidate(
    track: SpotifyTrack,
    result: SearchResult,
    *,
    duration_tolerance_s: float = 10.0,
    match_threshold: float = 76.0,
) -> CandidateScore:
    title_score = _title_similarity(track, result)
    artist_score = _artist_similarity(track, result)
    qualifier_penalty, qualifier_reasons = _qualifier_penalty(track, result)

    duration_diff: float | None
    if result.duration_s is None:
        duration_diff = None
        duration_score = 0.0
    else:
        duration_diff = abs(float(result.duration_s) - track.duration_s)
        duration_score = max(
            0.0,
            100.0 - (duration_diff / max(duration_tolerance_s, 0.001)) * 25.0,
        )

    total = title_score * 0.58 + artist_score * 0.24 + duration_score * 0.18 - qualifier_penalty

    reasons = list(qualifier_reasons)
    accepted = True

    # A recording-version mismatch is a hard identity failure. "Official
    # Video/Audio/Lyrics" is already stripped as neutral, while Live/Remix/
    # Cover/Slowed/etc. describes a materially different recording.
    if qualifier_reasons:
        accepted = False

    # Duration from search metadata is useful but not authoritative. Some
    # otherwise excellent YouTube results omit it. In that case, allow only a
    # very strong title+artist identity match to proceed; the downloaded file
    # is still measured afterward and MUST satisfy the same ± tolerance.
    if duration_diff is None:
        reasons.append("candidate duration unavailable; validate after download")
        if title_score < 90.0 or artist_score < 70.0:
            accepted = False
            reasons.append("unknown duration requires strong title+artist match")
    elif duration_diff > duration_tolerance_s:
        accepted = False
        reasons.append(f"duration differs by {duration_diff:.1f}s (> {duration_tolerance_s:.1f}s)")

    # Track title is the first identity check; artist/composer is second.
    if title_score < 72.0:
        accepted = False
        reasons.append(f"weak title match ({title_score:.1f})")

    if artist_score < 52.0:
        # Exception only for an almost exact song title plus almost exact duration.
        # This helps sparse uploads while remaining conservative.
        strong_title_duration = (
            title_score >= 96.0 and duration_diff is not None and duration_diff <= 2.0
        )
        if not strong_title_duration:
            accepted = False
            reasons.append(f"weak artist/composer match ({artist_score:.1f})")

    if total < match_threshold:
        accepted = False
        reasons.append(f"score {total:.1f} < {match_threshold:.1f}")

    return CandidateScore(
        result=result,
        total_score=round(total, 2),
        title_score=round(title_score, 2),
        artist_score=round(artist_score, 2),
        duration_score=round(duration_score, 2),
        duration_diff_s=round(duration_diff, 3) if duration_diff is not None else None,
        qualifier_penalty=round(qualifier_penalty, 2),
        accepted=accepted,
        reasons=reasons,
    )


def rank_candidates(
    track: SpotifyTrack,
    results: Iterable[SearchResult],
    *,
    duration_tolerance_s: float = 10.0,
    match_threshold: float = 76.0,
) -> list[CandidateScore]:
    ranked = [
        score_candidate(
            track,
            result,
            duration_tolerance_s=duration_tolerance_s,
            match_threshold=match_threshold,
        )
        for result in results
    ]
    ranked.sort(
        key=lambda item: (
            item.accepted,
            item.total_score,
            item.title_score,
            item.artist_score,
            -(item.duration_diff_s if item.duration_diff_s is not None else 999999.0),
        ),
        reverse=True,
    )
    return ranked


def read_spotify_csv(path: str | Path) -> tuple[list[SpotifyTrack], list[dict[str, str]]]:
    path = Path(path)
    tracks: list[SpotifyTrack] = []
    invalid_rows: list[dict[str, str]] = []

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("CSV has no header row")

        required_columns = {"Track URI", "Track Name", "Artist Name(s)", "Duration (ms)"}
        missing_columns = sorted(required_columns - set(reader.fieldnames))
        if missing_columns:
            raise ValueError("CSV is missing required column(s): " + ", ".join(missing_columns))

        for row_number, row in enumerate(reader, start=2):
            try:
                tracks.append(SpotifyTrack.from_csv_row(row_number, row))
            except (ValueError, TypeError) as exc:
                invalid_rows.append(
                    {
                        "row_number": str(row_number),
                        "track_uri": str(row.get("Track URI", "") or ""),
                        "track_name": str(row.get("Track Name", "") or ""),
                        "artists": str(row.get("Artist Name(s)", "") or ""),
                        "reason": f"invalid_csv_row: {exc}",
                    }
                )

    return tracks, invalid_rows


def _ffmpeg_binary() -> str:
    binary = shutil.which("ffmpeg")
    if not binary:
        raise RuntimeError(
            "ffmpeg was not found in PATH. Install FFmpeg and ensure `ffmpeg -version` works."
        )
    return binary


def _ffprobe_binary() -> str | None:
    return shutil.which("ffprobe")


def probe_duration(path: Path) -> float | None:
    ffprobe = _ffprobe_binary()
    if not ffprobe:
        return None

    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=30)
    if completed.returncode != 0:
        return None
    try:
        duration = float(completed.stdout.strip())
        return duration if math.isfinite(duration) and duration > 0 else None
    except ValueError:
        return None


def _safe_metadata(value: str) -> str:
    # subprocess argument lists do not need shell escaping. Removing control
    # characters keeps FFmpeg logs and ID3 metadata well-formed.
    return "".join(ch for ch in (value or "") if ch >= " " or ch == "\t").strip()


def tag_to_spotify_mp3(
    input_path: Path,
    output_path: Path,
    track: SpotifyTrack,
    *,
    source_ext: str,
) -> None:
    """Write Spotify metadata and a canonical filename using FFmpeg."""
    ffmpeg = _ffmpeg_binary()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    temp_output = output_path.with_name(output_path.stem + ".tagging.tmp.mp3")
    temp_output.unlink(missing_ok=True)

    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(input_path),
        "-map",
        "0:a:0",
        "-vn",
        "-map_metadata",
        "-1",
        "-id3v2_version",
        "3",
        "-metadata",
        f"title={_safe_metadata(track.track_name)}",
        "-metadata",
        f"artist={_safe_metadata(track.artists_display)}",
        "-metadata",
        f"album={_safe_metadata(track.album_name)}",
        "-metadata",
        f"album_artist={_safe_metadata(track.primary_artist)}",
        "-metadata",
        f"date={_safe_metadata(track.release_date)}",
        "-metadata",
        f"genre={_safe_metadata(track.genres)}",
        "-metadata",
        f"publisher={_safe_metadata(track.record_label)}",
        "-metadata",
        f"comment=Spotify URI: {_safe_metadata(track.uri)}",
    ]

    if source_ext.casefold().lstrip(".") == "mp3":
        # Preserve the MP3Juice audio bit-for-bit; only rewrite its container tags.
        command.extend(["-c:a", "copy"])
    else:
        # Defensive path for non-MP3 backends: normalize the final library to MP3.
        command.extend(["-c:a", "libmp3lame", "-q:a", "0"])

    command.append(str(temp_output))

    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, check=False, timeout=120
        )
        if completed.returncode != 0:
            error = (completed.stderr or completed.stdout or "unknown FFmpeg error").strip()
            raise RuntimeError(f"ffmpeg tagging failed: {error[-1200:]}")
        os.replace(temp_output, output_path)
    finally:
        temp_output.unlink(missing_ok=True)


def canonical_output_path(directory: Path, track: SpotifyTrack, *, extension: str = "mp3") -> Path:
    """
    Prefer the exact Spotify track name. Only add artist/URI when a collision
    would otherwise overwrite another song with the same title.
    """
    stem = legalize_filename(track.track_name)
    candidate = directory / f"{stem}.{extension}"
    if not candidate.exists():
        return candidate

    stem_artist = legalize_filename(f"{stem} - {track.primary_artist}")
    candidate = directory / f"{stem_artist}.{extension}"
    if not candidate.exists():
        return candidate

    spotify_id = track.uri.rsplit(":", 1)[-1][-8:] if track.uri else str(track.row_number)
    return available_audio_path(directory, f"{stem_artist} [{spotify_id}]", extension)


def _short_search_title(value: str) -> str:
    """
    Build a conservative alternate query title.

    Useful for long classical titles and export labels such as
    "Original Mix"/"Album Mix". This only affects search discovery;
    candidate validation still uses the full Spotify title.
    """
    text = WHITESPACE_RE.sub(" ", value or "").strip()
    text = FEATURE_RE.sub(" ", text)
    text = WHITESPACE_RE.sub(" ", text).strip(" -–—|:")

    # Search engines/uploaders frequently omit these presentation labels.
    text = re.sub(
        r"\s*[-–—]\s*(?:original|album)\s+mix\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()

    # Long classical titles often have movement detail after a colon. The
    # work/catalogue portion before the colon is a much stronger search key.
    if len(text) > 60 and ":" in text:
        head = text.split(":", 1)[0].strip(" -–—")
        if len(head) >= 18:
            text = head

    # Final safety cap for pathological export titles.
    if len(text) > 90:
        words = text.split()
        text = " ".join(words[:14]).strip(" -–—|:")

    return text or value.strip()


def _unique_queries(values: Iterable[str], *, limit: int = 10) -> list[str]:
    seen: set[str] = set()
    queries: list[str] = []

    for value in values:
        query = WHITESPACE_RE.sub(" ", value or "").strip()
        key = normalize_text(query)
        if not query or not key or key in seen:
            continue
        seen.add(key)
        queries.append(query)
        if len(queries) >= limit:
            break

    return queries


def _plausible_candidate_count(
    track: SpotifyTrack,
    candidates: Iterable[SearchResult],
    *,
    duration_tolerance_s: float,
) -> int:
    count = 0
    for result in candidates:
        scored = score_candidate(
            track,
            result,
            duration_tolerance_s=duration_tolerance_s,
            match_threshold=76.0,
        )
        if scored.accepted:
            count += 1
    return count


def _search_candidates(
    client: MP3JuiceMusicClient,
    track: SpotifyTrack,
    *,
    search_limit: int,
    duration_tolerance_s: float,
) -> list[SearchResult]:
    full_title = track.track_name.strip()
    short_title = _short_search_title(full_title)
    primary = track.primary_artist.strip()

    # Stage 1: preserve the established high-value queries.
    primary_queries = _unique_queries(
        [
            f"{full_title} {primary}",
            f"{primary} {full_title}",
            full_title,
        ],
        limit=3,
    )

    # Stage 2 runs only when stage 1 did not discover enough safe alternatives.
    # This avoids multiplying network traffic across a 700+ track library.
    expansion_values: list[str] = []

    # Search every credited artist/composer independently. This helps tracks
    # where Spotify's primary artist is not the name used by the upload.
    for artist in track.artists[1:]:
        expansion_values.extend(
            [
                f"{full_title} {artist}",
                f"{artist} {full_title}",
            ]
        )

    if normalize_text(short_title) != normalize_text(full_title):
        expansion_values.extend(
            [
                f"{short_title} {primary}",
                f"{primary} {short_title}",
                short_title,
            ]
        )
        for artist in track.artists[1:3]:
            expansion_values.extend(
                [
                    f"{short_title} {artist}",
                    f"{artist} {short_title}",
                ]
            )

    # A combined credited-artist query can be useful for collaborations, but
    # keep it bounded so it does not become an oversized search string.
    if len(track.artists) > 1:
        combined = " ".join(track.artists[:2])
        expansion_values.append(f"{combined} {short_title}")

    expansion_queries = _unique_queries(expansion_values, limit=7)

    seen: set[tuple[str, str]] = set()
    candidates: list[SearchResult] = []
    errors: list[str] = []

    def run_queries(queries: Iterable[str]) -> None:
        for query in queries:
            try:
                results = client.search(
                    query,
                    limit=search_limit,
                    source="all",
                )
            except (MP3JuiceError, OSError) as exc:
                errors.append(str(exc))
                continue

            for result in results:
                key = (result.root_source.casefold(), result.identifier)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(result)

            # Three accepted alternatives are enough to survive a bad Theta
            # worker without continuing to hammer MP3Juice search.
            if (
                _plausible_candidate_count(
                    track,
                    candidates,
                    duration_tolerance_s=duration_tolerance_s,
                )
                >= 3
            ):
                return

    run_queries(primary_queries)

    if (
        _plausible_candidate_count(
            track,
            candidates,
            duration_tolerance_s=duration_tolerance_s,
        )
        < 3
    ):
        run_queries(expansion_queries)

    if not candidates and errors:
        raise SearchError("Search failed: " + errors[-1])
    return candidates


class SpotifyTrackDownloader:
    """Match, validate and save one track; persistence belongs to FrogifyService."""

    def __init__(
        self,
        client: MP3JuiceMusicClient,
        *,
        output_dir: str | Path,
        metadata_enabled: bool = True,
        duration_tolerance_s: float = 10.0,
        candidate_attempts: int = 3,
        callbacks: BatchCallbacks | None = None,
    ) -> None:
        self.client = client
        self.output_dir = Path(output_dir)
        self.duration_tolerance_s = duration_tolerance_s
        self.metadata_enabled = metadata_enabled
        self.candidate_attempts = candidate_attempts
        self.callbacks = callbacks or BatchCallbacks()

    def _status(self, text: str) -> None:
        if self.callbacks.on_status:
            self.callbacks.on_status(text)

    def download_track(
        self, track: SpotifyTrack, *, previous_path: Path | None = None
    ) -> tuple[Path, CandidateScore]:
        if not math.isfinite(track.duration_s) or track.duration_s <= 0:
            raise ValueError("Track duration must be a positive finite number")
        self._status("searching MP3Juice")
        ranked = rank_candidates(
            track,
            _search_candidates(
                self.client,
                track,
                search_limit=10,
                duration_tolerance_s=self.duration_tolerance_s,
            ),
            duration_tolerance_s=self.duration_tolerance_s,
        )
        accepted = [item for item in ranked if item.accepted][: self.candidate_attempts]
        if not accepted:
            raise DownloadError("no candidate passed title + artist/composer + duration checks")
        # Dependency checks belong to operations that actually need the executable.
        if self.metadata_enabled:
            _ffmpeg_binary()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        errors: list[str] = []
        diagnostics: list[dict[str, object]] = []
        for candidate in accepted:
            selected = candidate.result
            self._status(f"downloading {selected.title}")
            if self.callbacks.on_download_start:
                self.callbacks.on_download_start(selected)
            try:
                song = self.client.download(
                    selected,
                    progress_callback=self.callbacks.on_download_progress,
                )
                # Stage on the destination volume; failed tagging never touches old audio.
                with tempfile.TemporaryDirectory(prefix=".frogify-", dir=self.output_dir) as work:
                    extension = song.ext.lstrip(".").casefold()
                    raw_path = (
                        available_audio_path(Path(work), "source", extension)
                        if extension
                        else Path(work) / "source"
                    )
                    raw_path.write_bytes(song.downloaded_contents)
                    actual = song.duration_s or probe_duration(raw_path)
                    if actual is None or not math.isfinite(actual) or actual <= 0:
                        raise DownloadError(
                            "actual duration unavailable after Mutagen + ffprobe",
                            details={
                                "audio_validation_attempts": (song.raw_data.get("http") or {}).get(
                                    "audio_validation_attempts", []
                                )
                            },
                        )
                    difference = abs(actual - track.duration_s)
                    if difference > self.duration_tolerance_s:
                        raise DownloadError(f"downloaded duration differs by {difference:.1f}s")
                    if not extension and not self.metadata_enabled:
                        raise DownloadError("Cannot determine the downloaded audio format")
                    staged = raw_path
                    if self.metadata_enabled:
                        self._status("writing Spotify metadata")
                        staged = Path(work) / "tagged.mp3"
                        tag_to_spotify_mp3(raw_path, staged, track, source_ext=extension)
                        extension = "mp3"
                    replace_existing = (
                        previous_path is not None
                        and previous_path.parent.resolve() == self.output_dir.resolve()
                        and previous_path.suffix.casefold() == "." + extension
                    )
                    destination = (
                        previous_path
                        if replace_existing
                        else canonical_output_path(self.output_dir, track, extension=extension)
                    )
                    assert destination is not None
                    saved = publish_audio(staged, destination, overwrite=replace_existing)
                    return saved.resolve(), candidate
            except (
                MP3JuiceError,
                OSError,
                RuntimeError,
                ValueError,
                subprocess.SubprocessError,
            ) as exc:
                errors.append(f"{selected.title}: {exc}")
                diagnostics.append(
                    {
                        "candidate_title": selected.title,
                        "candidate_source": selected.root_source,
                        "candidate_id": selected.identifier,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "details": getattr(exc, "details", {}),
                    }
                )
        raise DownloadError(
            "all accepted candidates failed: " + " | ".join(errors),
            details={"download_diagnostics": diagnostics},
        )
