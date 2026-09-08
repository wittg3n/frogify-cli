from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import frogify.cli.app as cli
from frogify.core.models import BatchResult, DownloadResult, RankedCandidate
from frogify.diagnostics import Diagnostic
from mp3juice.models import SearchResult

runner = CliRunner()


class FakeService:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    @staticmethod
    def _ranked():
        result = SearchResult("id", "Adele - Hello", "YouTube", 295, "4:55", {})
        return [RankedCandidate(result, 98.7)]

    def search(self, request, **kwargs):
        self.calls.append(("search", request.query))
        return self._ranked()

    def download(self, request, **kwargs):
        self.calls.append(("download", request.query))
        return DownloadResult(Path("Adele - Hello.mp3"), self._ranked()[0], "requests")

    def batch(self, csv_path, **kwargs):
        self.calls.append(("batch", str(csv_path)))
        return BatchResult(1, 1, 0, 0)

    def retry(self, **kwargs):
        self.calls.append(("retry", ""))
        return BatchResult(0, 0, 0, 0)


def test_cli_version_and_help():
    assert runner.invoke(cli.app, ["--version"]).exit_code == 0
    assert "frogify 2.0.0" in runner.invoke(cli.app, ["--version"]).stdout
    assert runner.invoke(cli.app, ["--help"]).exit_code == 0


def test_banner_falls_back_on_legacy_windows_encoding(monkeypatch):
    class LegacyConsole:
        encoding = "cp1252"

        def print(self, *values, **kwargs):
            assert "🐸" not in str(values)

    monkeypatch.setattr(cli, "console", LegacyConsole())
    cli._print_candidates("Adele Hello", FakeService._ranked())
    assert cli._safe_text("Hello ❤") == "Hello ?"


def test_root_query_and_named_search_route_distinctly(monkeypatch):
    service = FakeService()
    monkeypatch.setattr(cli, "_service", lambda: service)
    root = runner.invoke(cli.app, ["Adele Hello"])
    search = runner.invoke(cli.app, ["search", "Adele Hello"])
    assert root.exit_code == 0, root.stdout
    assert search.exit_code == 0, search.stdout
    assert service.calls == [("download", "Adele Hello"), ("search", "Adele Hello")]
    assert "Matched: Adele - Hello (98.7/100)" in root.stdout
    assert "Match / 100" in search.stdout
    assert "98.7" in search.stdout


def test_batch_retry_doctor_and_config_commands(tmp_path, monkeypatch):
    service = FakeService()
    monkeypatch.setattr(cli, "_service", lambda: service)
    monkeypatch.setattr(cli, "run_doctor", lambda *args: [Diagnostic("Config", True, "ok")])
    csv_path = tmp_path / "songs.csv"
    csv_path.write_text("Track URI,Track Name,Artist Name(s),Duration (ms)\n", encoding="utf-8")
    assert runner.invoke(cli.app, ["batch", str(csv_path)]).exit_code == 0
    assert runner.invoke(cli.app, ["retry"]).exit_code == 0
    assert runner.invoke(cli.app, ["doctor"]).exit_code == 0
    assert runner.invoke(cli.app, ["config", "path"]).exit_code == 0
    assert [name for name, _ in service.calls] == ["batch", "retry"]
