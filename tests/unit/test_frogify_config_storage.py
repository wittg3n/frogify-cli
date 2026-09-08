from __future__ import annotations

import csv
import logging
import sqlite3

import pytest

from frogify.config import ConfigManager
from frogify.core.exceptions import ConfigurationError
from frogify.logging import RedactingFormatter
from frogify.storage import Database


def test_config_round_trip_and_validation(tmp_path):
    config = ConfigManager(tmp_path / "config.toml", tmp_path / "data")
    assert config.get("network.retry_profile") == "balanced"
    assert config.set("network.retry_profile", "fast") == "fast"
    assert config.set("download.aria2_connections", "10") == 10
    assert config.get("download.aria2_connections") == 10
    with pytest.raises(ConfigurationError):
        config.set("download.aria2_connections", "99")


def test_legacy_migration_is_idempotent_and_success_wins(tmp_path):
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    success = legacy / "downloaded_tracks.csv"
    failure = legacy / "failed_tracks.csv"
    with success.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["track_uri", "track_name", "artists", "file"])
        writer.writeheader()
        writer.writerow(
            {
                "track_uri": "spotify:track:1",
                "track_name": "Song",
                "artists": "Artist",
                "file": "old.mp3",
            }
        )
    with failure.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["track_uri", "track_name", "reason"])
        writer.writeheader()
        writer.writerow(
            {"track_uri": "spotify:track:1", "track_name": "Song", "reason": "old failure"}
        )

    database = Database(tmp_path / "frogify.db")
    database.initialize()
    assert database.migrate_legacy([success, failure]) == 2
    assert database.migrate_legacy([success, failure]) == 0
    assert database.is_success("spotify:track:1")
    with database.connect() as db:
        assert db.execute("SELECT count(*) FROM downloads").fetchone()[0] == 1


def test_failure_can_be_retried_then_becomes_success(tmp_path):
    database = Database(tmp_path / "frogify.db")
    database.initialize()
    database.record_failure(
        "spotify:track:2",
        request={"type": "structured"},
        error_type="NetworkError",
        error_message="timeout",
    )
    assert len(database.failures()) == 1
    database.record_success("spotify:track:2", path="song.mp3")
    assert database.failures() == []


def test_log_formatter_redacts_signed_url_parameters():
    record = logging.LogRecord(
        "frogify",
        logging.INFO,
        "",
        0,
        "url=https://worker.test/audio?sig=secret&token=also-secret",
        (),
        None,
    )
    rendered = RedactingFormatter("%(message)s").format(record)
    assert "secret" not in rendered
    assert "sig=<redacted>" in rendered


@pytest.mark.parametrize(
    "document",
    [
        "[network]\ntimeout = nan",
        "[matching]\nduration_tolerance = inf",
        "[network]\ntimeout = -1",
        "[download]\naria2_connections = true",
        '[metadata]\nenabled = "false"',
        "[matching]\ncandidate_attempts = 0",
        "[download]\nunknown = 1",
        'network = "fast"',
    ],
)
def test_config_rejects_invalid_toml_values(tmp_path, document):
    config = ConfigManager(tmp_path / "config.toml", tmp_path / "data")
    config.path.write_text(document, encoding="utf-8")
    with pytest.raises(ConfigurationError):
        config.load()


def test_config_escapes_strings_and_failed_save_preserves_original(tmp_path, monkeypatch):
    config = ConfigManager(tmp_path / "config.toml", tmp_path / "data")
    value = 'D:\\Music\\"quoted"\n\tUnicode: آواز'
    config.set("download.directory", value)
    assert config.get("download.directory") == value
    original = config.path.read_bytes()

    def fail(*args):
        raise PermissionError("file locked")

    monkeypatch.setattr("frogify.config.os.replace", fail)
    with pytest.raises(PermissionError):
        config.set("network.timeout", "12")
    assert config.path.read_bytes() == original
    assert sorted(p.name for p in tmp_path.iterdir()) == ["config.toml", "data"]


def test_database_context_closes_and_rolls_back_on_error(tmp_path):
    database = Database(tmp_path / "frogify.db")
    database.initialize()
    with pytest.raises(RuntimeError), database.connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS test_transaction (value TEXT)")
        db.execute("INSERT INTO test_transaction VALUES ('uncommitted')")
        raise RuntimeError("interrupted")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        db.execute("SELECT 1")
    with database.connect() as reopened:
        assert reopened.execute("SELECT count(*) FROM test_transaction").fetchone()[0] == 0
