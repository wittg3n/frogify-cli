from __future__ import annotations

import csv
import json
import subprocess

import pytest
from typer.testing import CliRunner

import frogify.cli.app as cli
from frogify.config import ConfigManager
from frogify.core.exceptions import DownloadError, NoSafeCandidateError
from frogify.core.models import FreeTextRequest
from frogify.core.service import FrogifyService
from mp3juice.exceptions import ResolveError, SearchError
from mp3juice.models import SearchResult, SongInfo
from mp3juice.spotify_batch import BatchCallbacks


class Client:
    def __init__(self):
        self.results = [SearchResult("one", "Artist - Song", "YouTube", 180, "3:00")]
        self.searches = []
        self.downloads = []
        self.error = None
        self.extension = "mp3"

    def search(self, query, **kwargs):
        self.searches.append((query, kwargs))
        return self.results

    def download(self, selected, **kwargs):
        self.downloads.append(selected.identifier)
        if self.error:
            raise self.error
        callback = kwargs.get("progress_callback")
        if callback:
            callback(5, 5)
        return SongInfo(
            "test",
            selected.root_source,
            selected.identifier,
            selected.title,
            ext=self.extension,
            duration_s=180,
            downloaded_contents=b"audio",
        )

    def close(self):
        pass


@pytest.fixture
def setup(tmp_path):
    config = ConfigManager(tmp_path / "config.toml", tmp_path / "data")
    config.set("metadata.enabled", "false")
    config.set("download.directory", str(tmp_path / "default"))
    client = Client()
    service = FrogifyService(config, client_factory=lambda **kwargs: client, legacy_paths=[])
    path = tmp_path / "songs.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["Track URI", "Track Name", "Artist Name(s)", "Duration (ms)"]
        )
        writer.writeheader()
        writer.writerow(
            {
                "Track URI": "spotify:track:one",
                "Track Name": "Song",
                "Artist Name(s)": "Artist",
                "Duration (ms)": "180000",
            }
        )
    return service, client, path


def test_batch_commits_before_callbacks_and_resumes_missing_files(setup):
    service, client, csv_path = setup

    def interrupt(*args):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        service.batch(csv_path, callbacks=BatchCallbacks(on_track_success=interrupt))
    saved = service.database.success_path("spotify:track:one")
    assert saved is not None
    assert service.batch(csv_path).skipped == 1
    assert client.downloads == ["one"]
    saved.unlink()
    assert service.batch(csv_path).downloaded == 1
    assert len(client.downloads) == 2


def test_failed_force_preserves_original_and_success_state(setup, monkeypatch):
    service, client, csv_path = setup
    service.batch(csv_path)
    saved = service.database.success_path("spotify:track:one")
    saved.write_bytes(b"original")
    service.config.set("metadata.enabled", "true")
    monkeypatch.setattr("mp3juice.spotify_batch._ffmpeg_binary", lambda: "fake")

    def fail(*args, **kwargs):
        raise RuntimeError("tagging failed")

    monkeypatch.setattr("mp3juice.spotify_batch.tag_to_spotify_mp3", fail)
    assert service.batch(csv_path, force=True).failed == 1
    assert saved.read_bytes() == b"original"
    assert service.database.success_path("spotify:track:one") == saved
    assert not list(saved.parent.glob(".frogify-*"))


def test_csv_no_longer_controls_live_state(setup):
    service, client, csv_path = setup
    output = csv_path.parent / "library"
    output.mkdir()
    legacy = output / "downloaded_tracks.csv"
    legacy.write_text("track_uri,file\n", encoding="utf-8")
    service.database.migrate_legacy([output])
    legacy.write_text("track_uri,file\nspotify:track:one,missing.mp3\n", encoding="utf-8")
    assert service.batch(csv_path, output=output).downloaded == 1
    assert service.database.success_path("spotify:track:one").is_file()
    assert legacy.read_text(encoding="utf-8").endswith("missing.mp3\n")


def test_pick_uses_displayed_result_without_second_search(setup, monkeypatch):
    service, client, _ = setup
    monkeypatch.setattr(cli, "_service", lambda: service)
    original = client.search

    def changing_search(*args, **kwargs):
        results = original(*args, **kwargs)
        client.results = [SearchResult("different", "Artist - Song", "YouTube", 180)]
        return results

    monkeypatch.setattr(client, "search", changing_search)
    invoked = CliRunner().invoke(cli.app, ["Artist Song", "--pick"], input="1\n")
    assert invoked.exit_code == 0, invoked.output
    assert len(client.searches) == 1
    assert client.downloads == ["one"]


@pytest.mark.parametrize(
    "query,title",
    [
        ("Artist Song", "Unrelated recording"),
        ("Artist Song", "Artist Song Live"),
        ("Artist Song Live", "Artist Song"),
    ],
)
def test_automatic_download_rejects_unsafe_matches(setup, query, title):
    service, client, _ = setup
    client.results = [SearchResult("bad", title, "YouTube", 180)]
    with pytest.raises(NoSafeCandidateError):
        service.download(FreeTextRequest(query))
    assert client.downloads == []
    assert len(service.database.failures()) == 1


def test_search_failure_is_friendly_persisted_and_retry_restores_options(setup, monkeypatch):
    service, client, csv_path = setup
    output = csv_path.parent / "original-destination"
    original_search = client.search

    def fail(*args, **kwargs):
        raise SearchError("provider unavailable")

    monkeypatch.setattr(client, "search", fail)
    monkeypatch.setattr(cli, "_service", lambda: service)
    invoked = CliRunner().invoke(
        cli.app, ["Artist Song", "--source", "youtube", "--output", str(output)]
    )
    assert invoked.exit_code == 1
    assert "Error:" in invoked.output
    assert len(service.database.failures()) == 1
    monkeypatch.setattr(client, "search", original_search)
    assert service.retry().downloaded == 1
    assert list(output.glob("*.mp3"))
    assert client.searches[-1][1]["source"] == "youtube"
    assert service.database.failures() == []


def test_batch_retry_preserves_destination_and_diagnostics(setup):
    service, client, csv_path = setup
    output = csv_path.parent / "library"
    client.error = ResolveError("failed ?token=secret", details={"stage": "convert"})
    assert service.batch(csv_path, output=output).failed == 1
    failure = service.database.failures()[0]
    assert "secret" not in failure["error_message"]
    payload = json.loads(failure["request_json"])
    assert payload["diagnostics"]["download_diagnostics"][0]["details"]["stage"] == "convert"
    client.error = None
    assert service.retry().downloaded == 1
    assert (output / "Song.mp3").is_file()


def test_metadata_disabled_preserves_format_and_all_skipped_needs_no_ffmpeg(setup, monkeypatch):
    service, client, csv_path = setup
    client.extension = "ogg"
    assert service.batch(csv_path).downloaded == 1
    path = service.database.success_path("spotify:track:one")
    assert path.suffix == ".ogg"
    service.config.set("metadata.enabled", "true")
    monkeypatch.setattr(
        "mp3juice.spotify_batch._ffmpeg_binary", lambda: pytest.fail("unused ffmpeg")
    )
    assert service.batch(csv_path).skipped == 1


def test_incomplete_retry_is_counted_and_explained(setup):
    service, client, _ = setup
    service.database.record_failure(
        "legacy",
        request={"type": "structured", "duration_s": "0"},
        error_type="LegacyFailure",
        error_message="old",
    )
    messages = []
    stats = service.retry(callbacks=BatchCallbacks(on_status=messages.append))
    assert (stats.total, stats.failed) == (1, 1)
    assert "original CSV" in messages[0]
    assert service.database.failures() == []


def test_batch_progress_uses_library_indices_and_deduplicates(setup):
    service, client, csv_path = setup
    with csv_path.open("a", encoding="utf-8") as handle:
        handle.write("spotify:track:two,Song,Artist,180000\nspotify:track:one,Song,Artist,180000\n")
    events = []
    stats = service.batch(
        csv_path,
        callbacks=BatchCallbacks(
            on_track_start=lambda i, n, track: events.append((i, n, track.uri))
        ),
    )
    assert stats.downloaded == 2
    assert events == [(1, 2, "spotify:track:one"), (2, 2, "spotify:track:two")]


def test_audio_probe_timeout_is_persisted_and_cleans_temporary_files(setup, monkeypatch):
    service, client, _ = setup
    original_download = client.download

    def unknown_duration(*args, **kwargs):
        song = original_download(*args, **kwargs)
        song.duration_s = None
        return song

    def timeout(*args):
        raise subprocess.TimeoutExpired("ffprobe", 30)

    monkeypatch.setattr(client, "download", unknown_duration)
    monkeypatch.setattr("frogify.core.service.probe_duration", timeout)
    with pytest.raises(DownloadError, match="validation timed out"):
        service.download(FreeTextRequest("Artist Song"))
    assert len(service.database.failures()) == 1
    assert list(service.config.temp_dir.iterdir()) == []


def test_retry_handles_malformed_saved_json(setup):
    service, _, _ = setup
    service.database.record_failure("bad", error_type="old", error_message="old")
    with service.database.connect() as db:
        db.execute("UPDATE downloads SET request_json = '[]' WHERE identity = 'bad'")
    assert service.retry().failed == 1
    assert service.database.failures() == []
