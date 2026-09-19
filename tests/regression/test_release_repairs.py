from __future__ import annotations

import io
import wave

import pytest

from frogify.config import ConfigManager
from frogify.diagnostics import run_doctor
from frogify.storage import Database
from mp3juice.aria2_downloader import Aria2RPCDownloader
from mp3juice.client import MP3JuiceMusicClient
from mp3juice.exceptions import DownloadError
from mp3juice.models import SearchResult, SongInfo
from mp3juice.spotify_batch import SpotifyTrack, read_spotify_csv, score_candidate


@pytest.mark.parametrize("legacy_name", ["failed_tracks.csv", "downloaded_tracks.csv"])
def test_legacy_import_preserves_current_retry_record(tmp_path, legacy_name):
    database = Database(tmp_path / "state.db")
    database.initialize()
    database.record_failure(
        "current",
        title="Hello",
        artists="Adele",
        query="Adele Hello",
        request={
            "type": "structured",
            "duration_s": 300,
            "output_dir": "/music",
            "candidate_attempts": 2,
            "selected": {"identifier": "chosen"},
            "diagnostics": {"attempt": 3},
        },
        error_type="ResolveError",
        error_message="current failure",
    )
    before = database.failures()[0]
    legacy = tmp_path / legacy_name
    legacy.write_text(
        "track_uri,track_name,artists,reason\ncurrent,Old,Other,old\nlegacy,Song,Artist,missing\n",
        encoding="utf-8",
    )
    database.migrate_legacy([legacy])
    with database.connect() as db:
        assert (
            dict(db.execute("SELECT * FROM downloads WHERE identity='current'").fetchone())
            == before
        )
        assert (
            db.execute("SELECT title FROM downloads WHERE identity='legacy'").fetchone()[0]
            == "Song"
        )
    assert database.migrate_legacy([legacy]) == 0


@pytest.mark.parametrize("error", [FileNotFoundError, PermissionError, OSError])
@pytest.mark.parametrize("engine", ["auto", "aria2"])
def test_process_launch_failure_respects_engine(monkeypatch, error, engine):
    downloader = Aria2RPCDownloader(executable="fixture-aria2")
    client = MP3JuiceMusicClient(downloader=engine)
    client._aria2 = downloader
    fallback = []

    def fail(*args, **kwargs):
        raise error("cannot launch fixture-aria2")

    def requests_download(*args, **kwargs):
        fallback.append(True)
        return b"audio", {}, "audio/mpeg", "https://example.test/audio"

    monkeypatch.setattr("mp3juice.aria2_downloader.subprocess.Popen", fail)
    monkeypatch.setattr(client, "_download_final_url_requests", requests_download)
    try:
        if engine == "auto":
            assert (
                client._download_final_url(
                    "https://example.test/audio", progress_callback=None, chunk_size=1024
                )[0]
                == b"audio"
            )
            assert fallback == [True]
        else:
            with pytest.raises(DownloadError, match="aria2.*cannot launch"):
                client._download_final_url(
                    "https://example.test/audio", progress_callback=None, chunk_size=1024
                )
            assert fallback == []
    finally:
        client.close()


@pytest.mark.parametrize("extension", ["wav", "mp3"])
def test_extensionless_aria2_payload_format(monkeypatch, tmp_path, extension):
    if extension == "wav":
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as audio:
            audio.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
            audio.writeframes(b"\0\0" * 8000)
        data = buffer.getvalue()
    else:
        # MPEG-1 Layer III, 128 kbps, 44.1 kHz frames with silent payload.
        data = (b"\xff\xfb\x90\x00" + b"\0" * 413) * 40
    with MP3JuiceMusicClient(downloader="aria2") as client:
        monkeypatch.setattr(
            client, "resolve_download_url", lambda result: ("https://example.test/audio", {})
        )
        monkeypatch.setattr(
            client,
            "_download_final_url",
            lambda *a, **k: (data, {"engine": "aria2"}, "", "https://example.test/audio"),
        )
        song = client.download(SearchResult("fixture", "Fixture", "SoundCloud"))
        assert song.duration_s and song.duration_s > 0
        assert song.ext == extension
        assert song.save(tmp_path).suffix == "." + extension


@pytest.mark.parametrize("artist", ["Live", "Cover", "Remix", "Acoustic", "Instrumental"])
def test_artist_is_not_a_recording_qualifier(artist):
    track = SpotifyTrack(2, "uri", "Lightning Crashes", "", artist, [artist], "", 300)
    result = SearchResult("one", f"{artist} - Lightning Crashes (Official Audio)", "YouTube", 300)
    assert score_candidate(track, result).accepted
    result.title = f"{artist} - Lightning Crashes (Live)"
    assert not score_candidate(track, result).accepted
    result.title = "Lightning Crashes (Live)"
    assert any("unexpected 'live'" in reason for reason in score_candidate(track, result).reasons)


@pytest.mark.parametrize("field", ["Track URI", "Track Name", "Artist Name(s)", "Duration (ms)"])
@pytest.mark.parametrize("missing", [None, "", "  "])
def test_missing_required_csv_values(field, missing):
    row = {
        "Track URI": "uri",
        "Track Name": "Hello",
        "Artist Name(s)": "Adele",
        "Duration (ms)": "300000",
    }
    row[field] = missing
    with pytest.raises(ValueError, match="missing required"):
        SpotifyTrack.from_csv_row(2, row)
    del row[field]
    with pytest.raises(ValueError, match="missing required"):
        SpotifyTrack.from_csv_row(2, row)


def test_truncated_csv_does_not_create_none_identities(tmp_path):
    path = tmp_path / "truncated.csv"
    path.write_text(
        "Duration (ms),Track Name,Artist Name(s),Track URI\n"
        "300000,Hello,Adele\n300000,Other,Artist\n",
        encoding="utf-8",
    )
    tracks, invalid = read_spotify_csv(path)
    assert tracks == []
    assert len(invalid) == 2
    assert all(row["track_uri"] == "" for row in invalid)


def test_literal_none_string_is_preserved():
    row = {
        "Track URI": "None",
        "Track Name": "None",
        "Artist Name(s)": "None",
        "Duration (ms)": "300000",
    }
    assert SpotifyTrack.from_csv_row(2, row).uri == "None"


def test_unknown_format_cannot_be_saved_as_mp3(tmp_path):
    song = SongInfo(
        "fixture", "SoundCloud", "one", "Unknown", ext="", downloaded_contents=b"unknown"
    )
    with pytest.raises(DownloadError, match="audio format"):
        song.save(tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("engine,required", [("auto", False), ("aria2", True), ("requests", False)])
def test_doctor_aria2_requirement(tmp_path, monkeypatch, engine, required):
    config = ConfigManager(tmp_path / "config.toml", tmp_path / "data")
    config.set("download.engine", engine)
    monkeypatch.setattr("frogify.diagnostics.shutil.which", lambda executable: None)
    checks = {
        c.name: c for c in run_doctor(config, Database(config.database_path), check_network=False)
    }
    assert checks["aria2c"].required is required
    assert not checks["aria2c"].ok
