from __future__ import annotations

from types import SimpleNamespace

from frogify.config import ConfigManager
from frogify.diagnostics import run_doctor
from frogify.storage import Database


def test_doctor_reports_invalid_config_and_database_independently(tmp_path):
    config = ConfigManager(tmp_path / "config.toml", tmp_path / "data")
    config.ensure_directories()
    config.path.write_text("[metadata]\nenabled = 123", encoding="utf-8")
    config.database_path.write_bytes(b"not a sqlite database")
    checks = {
        c.name: c for c in run_doctor(config, Database(config.database_path), check_network=False)
    }
    assert not checks["Config"].ok
    assert not checks["Database"].ok
    assert "ffmpeg" in checks


def test_doctor_rejects_provider_404_and_closes_responses(tmp_path, monkeypatch):
    config = ConfigManager(tmp_path / "config.toml", tmp_path / "data")
    closed = []

    def get(*args, **kwargs):
        return SimpleNamespace(status_code=404, close=lambda: closed.append(True))

    monkeypatch.setattr("frogify.diagnostics.requests.Session.get", get)
    checks = {c.name: c for c in run_doctor(config, Database(config.database_path))}
    assert not checks["MP3Juice"].ok
    assert not checks["Theta"].ok
    assert "reachability only" in checks["Theta"].detail
    assert len(closed) == 2
