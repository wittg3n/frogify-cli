from __future__ import annotations

import csv
import shutil
import subprocess
from pathlib import Path

import pytest

from mp3juice.models import SearchResult
from mp3juice.spotify_batch import (
    SpotifyTrack,
    canonical_output_path,
    read_spotify_csv,
    score_candidate,
    strip_neutral_qualifiers,
    tag_to_spotify_mp3,
)


def track(
    name: str = "Hello",
    artists: str = "Adele",
    duration: float = 300.0,
) -> SpotifyTrack:
    return SpotifyTrack(
        row_number=2,
        uri="spotify:track:test123",
        track_name=name,
        album_name="Album",
        artists_display=artists,
        artists=artists.split(";"),
        release_date="2020-01-02",
        duration_s=duration,
        genres="Pop",
        record_label="Label",
    )


def result(title: str, duration: float | None, source: str = "YouTube") -> SearchResult:
    return SearchResult(
        identifier="abc",
        title=title,
        root_source=source,
        duration_s=duration,
        duration="5:00" if duration is not None else "--:--",
        raw_data={},
    )


def test_official_video_is_neutral_and_good_match():
    scored = score_candidate(
        track(duration=300),
        result("Adele - Hello (Official Music Video)", 304),
    )
    assert scored.accepted is True
    assert scored.qualifier_penalty == 0
    assert scored.duration_diff_s == 4
    assert scored.title_score >= 95
    assert scored.artist_score >= 95


def test_video_in_real_song_title_is_not_stripped():
    scored = score_candidate(
        track("Video Games", "Lana Del Rey", 282),
        result("Lana Del Rey - Video Games (Official Video)", 282),
    )
    assert scored.accepted is True
    assert scored.title_score >= 95


def test_wrong_live_version_is_penalized():
    scored = score_candidate(
        track("Hello", "Adele", 300),
        result("Adele - Hello Live at Wembley", 300),
    )
    assert scored.qualifier_penalty >= 20
    assert scored.accepted is False
    assert any("unexpected 'live'" in reason for reason in scored.reasons)


def test_requested_remix_is_not_penalized():
    scored = score_candidate(
        track("Coward - Rone Remix", "Yael Naim;Rone", 240),
        result("Yael Naim - Coward (Rone Remix) [Official Audio]", 242),
    )
    assert scored.qualifier_penalty == 0
    assert scored.accepted is True


def test_duration_is_hard_gate():
    inside = score_candidate(
        track(duration=300),
        result("Adele - Hello Official Audio", 310),
    )
    outside = score_candidate(
        track(duration=300),
        result("Adele - Hello Official Audio", 310.01),
    )
    assert inside.accepted is True
    assert outside.accepted is False
    assert any("duration differs" in reason for reason in outside.reasons)


def test_unknown_duration_with_strong_identity_is_deferred_to_post_download_validation():
    scored = score_candidate(
        track(duration=300),
        result("Adele - Hello Official Audio", None),
    )
    assert scored.accepted is True
    assert any("validate after download" in reason for reason in scored.reasons)


def test_unknown_duration_with_weak_artist_is_rejected():
    scored = score_candidate(
        track(name="Norma Jeane", artists="Alx Beats", duration=198),
        SearchResult(
            identifier="x",
            title="Norma Jeane",
            root_source="YouTube",
            duration_s=None,
            duration="--:--",
            raw_data={},
        ),
    )
    assert scored.accepted is False
    assert any(
        "unknown duration requires strong title+artist" in reason for reason in scored.reasons
    )


def test_strip_neutral_suffix_but_preserve_real_words():
    assert strip_neutral_qualifiers("Adele - Hello Official Video").endswith("hello")
    assert "video games" in strip_neutral_qualifiers("Lana Del Rey - Video Games")


def test_read_spotify_csv(tmp_path: Path):
    path = tmp_path / "liked.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "Track URI",
                "Track Name",
                "Album Name",
                "Artist Name(s)",
                "Release Date",
                "Duration (ms)",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "Track URI": "spotify:track:1",
                "Track Name": "Song",
                "Album Name": "Album",
                "Artist Name(s)": "Artist A;Artist B",
                "Release Date": "2026-01-01",
                "Duration (ms)": "123456",
            }
        )

    tracks, invalid = read_spotify_csv(path)
    assert invalid == []
    assert len(tracks) == 1
    assert tracks[0].artists == ["Artist A", "Artist B"]
    assert tracks[0].duration_s == pytest.approx(123.456)


def test_canonical_filename_prefers_spotify_title(tmp_path: Path):
    t = track("Hello: World", "Adele", 300)
    path = canonical_output_path(tmp_path, t)
    assert path.name == "Hello_ World.mp3"

    path.write_bytes(b"existing")
    collision = canonical_output_path(tmp_path, t)
    assert collision.name == "Hello_ World - Adele.mp3"


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_ffmpeg_tags_and_normalizes_to_mp3(tmp_path: Path):
    source = tmp_path / "source.mp3"
    completed = subprocess.run(
        [
            shutil.which("ffmpeg"),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=0.5",
            "-c:a",
            "libmp3lame",
            str(source),
        ],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr

    target = tmp_path / "Tagged.mp3"
    tag_to_spotify_mp3(source, target, track(), source_ext="mp3")
    assert target.exists()
    assert target.stat().st_size > 0

    from mutagen.id3 import ID3

    tags = ID3(target)
    assert str(tags.get("TIT2")) == "Hello"
    assert str(tags.get("TPE1")) == "Adele"
    assert str(tags.get("TALB")) == "Album"


def test_track_download_tags_valid_audio(tmp_path: Path, monkeypatch):
    from mp3juice.models import SongInfo
    from mp3juice.spotify_batch import SpotifyTrackDownloader

    t = track("Hello", "Adele", 300)

    class FakeClient:
        def search(self, keyword, *, limit=10, source="all"):
            return [result("Adele - Hello (Official Audio)", 301)]

        def download(self, selected, *, progress_callback=None):
            if progress_callback:
                progress_callback(0, 100)
                progress_callback(100, 100)
            return SongInfo(
                source="test",
                root_source="YouTube",
                identifier=selected.identifier,
                song_name=selected.title,
                ext="mp3",
                file_size_bytes=4,
                file_size="0.00 MB",
                duration_s=300.5,
                duration="5:00",
                download_url="https://example.test/file.mp3",
                downloaded_contents=b"fake",
                raw_data={"download": {"backend": "theta"}},
            )

    def fake_tag(input_path, output_path, track, *, source_ext):
        output_path.write_bytes(input_path.read_bytes())

    monkeypatch.setattr("mp3juice.spotify_batch.tag_to_spotify_mp3", fake_tag)
    monkeypatch.setattr("mp3juice.spotify_batch._ffmpeg_binary", lambda: "ffmpeg")

    out = tmp_path / "spotify"
    downloader = SpotifyTrackDownloader(FakeClient(), output_dir=out)
    saved, candidate = downloader.download_track(t)
    assert saved == out / "Hello.mp3"
    assert saved.read_bytes() == b"fake"
    assert candidate.accepted


def test_batch_rejects_wrong_actual_download_duration(tmp_path: Path, monkeypatch):
    from mp3juice.exceptions import DownloadError
    from mp3juice.models import SongInfo
    from mp3juice.spotify_batch import SpotifyTrackDownloader

    t = track("Hello", "Adele", 300)

    class FakeClient:
        def search(self, keyword, *, limit=10, source="all"):
            return [result("Adele - Hello (Official Audio)", 300)]

        def download(self, selected, *, progress_callback=None):
            return SongInfo(
                source="test",
                root_source="YouTube",
                identifier=selected.identifier,
                song_name=selected.title,
                ext="mp3",
                duration_s=315.0,
                duration="5:15",
                download_url="https://example.test/file.mp3",
                downloaded_contents=b"fake",
                raw_data={"download": {"backend": "theta"}},
            )

    monkeypatch.setattr("mp3juice.spotify_batch._ffmpeg_binary", lambda: "ffmpeg")

    out = tmp_path / "spotify"
    downloader = SpotifyTrackDownloader(FakeClient(), output_dir=out)
    with pytest.raises(DownloadError, match="downloaded duration differs by 15.0s"):
        downloader.download_track(t)
    assert not (out / "Hello.mp3").exists()


@pytest.mark.parametrize("duration", ["nan", "inf", "-1", "0"])
def test_csv_rejects_nonfinite_and_nonpositive_duration(tmp_path, duration):
    path = tmp_path / "songs.csv"
    path.write_text(
        "Track URI,Track Name,Artist Name(s),Duration (ms)\n"
        f"spotify:track:test,Song,Artist,{duration}\n",
        encoding="utf-8",
    )
    tracks, invalid = read_spotify_csv(path)
    assert tracks == []
    assert len(invalid) == 1


def test_tag_timeout_keeps_original_and_removes_partial_output(tmp_path, monkeypatch):
    source = tmp_path / "source.mp3"
    destination = tmp_path / "tagged.mp3"
    source.write_bytes(b"source")
    destination.write_bytes(b"original")
    monkeypatch.setattr("mp3juice.spotify_batch._ffmpeg_binary", lambda: "fake")

    def timeout(command, **kwargs):
        Path(command[-1]).write_bytes(b"partial")
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr("mp3juice.spotify_batch.subprocess.run", timeout)
    with pytest.raises(subprocess.TimeoutExpired):
        tag_to_spotify_mp3(source, destination, track(), source_ext="mp3")
    assert destination.read_bytes() == b"original"
    assert not (tmp_path / "tagged.tagging.tmp.mp3").exists()
