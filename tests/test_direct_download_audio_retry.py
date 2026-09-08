from __future__ import annotations

from mp3juice.client import MP3JuiceMusicClient
from mp3juice.models import SearchResult


def result():
    return SearchResult(
        identifier="yt123",
        title="Alx Beats - Norma Jeane",
        root_source="YouTube",
        raw_data={},
    )


def test_direct_download_url_retries_non_audio_then_succeeds(monkeypatch):
    client = MP3JuiceMusicClient(downloader="requests")
    client.DIRECT_AUDIO_RETRY_DELAYS_S = (0.0, 0.0)

    monkeypatch.setattr(
        client,
        "resolve_download_url",
        lambda selected: (
            "https://worker.example/download",
            {"download_resolution": "convert.downloadURL"},
        ),
    )

    calls = {"n": 0}

    def fake_download(url, *, progress_callback, chunk_size):
        calls["n"] += 1
        if calls["n"] < 3:
            return (
                b'{"status":"processing"}',
                {"engine": "requests", "total_bytes": 23},
                "application/json",
                url,
                None,
            )
        return (
            b"ID3" + b"\x00" * 100,
            {"engine": "requests", "total_bytes": 103},
            "audio/mpeg",
            url,
            198.4,
        )

    monkeypatch.setattr(client, "_download_verified_audio", fake_download)
    monkeypatch.setattr("mp3juice.client.time.sleep", lambda _: None)

    song = client.download(result())

    assert calls["n"] == 3
    assert song.duration_s == 198.4
    attempts = song.raw_data["http"]["audio_validation_attempts"]
    assert len(attempts) == 3
    assert attempts[0]["duration_s"] is None
    assert attempts[-1]["duration_s"] == 198.4

    client.close()


def test_direct_download_url_fresh_resolve_after_same_url_retries(monkeypatch):
    client = MP3JuiceMusicClient(downloader="requests")
    client.DIRECT_AUDIO_RETRY_DELAYS_S = (0.0,)

    resolve_calls = {"n": 0}

    def fake_resolve(selected):
        resolve_calls["n"] += 1
        if resolve_calls["n"] == 1:
            return (
                "https://worker.example/not-ready",
                {"download_resolution": "convert.downloadURL"},
            )
        return (
            "https://worker2.example/ready",
            {"redirect": {"downloadURL": "https://worker2.example/ready"}},
        )

    monkeypatch.setattr(client, "resolve_download_url", fake_resolve)

    def fake_download(url, *, progress_callback, chunk_size):
        if "not-ready" in url:
            return (
                b"<html>processing</html>",
                {"engine": "requests", "total_bytes": 23},
                "text/html",
                url,
                None,
            )
        return (
            b"ID3" + b"\x00" * 100,
            {"engine": "requests", "total_bytes": 103},
            "audio/mpeg",
            url,
            198.5,
        )

    monkeypatch.setattr(client, "_download_verified_audio", fake_download)
    monkeypatch.setattr("mp3juice.client.time.sleep", lambda _: None)

    song = client.download(result())

    assert resolve_calls["n"] == 2
    assert song.duration_s == 198.5
    assert song.download_url == "https://worker2.example/ready"

    client.close()


def test_invalid_audio_after_all_retries_is_returned_for_ffprobe_fallback(monkeypatch):
    client = MP3JuiceMusicClient(downloader="requests")
    client.DIRECT_AUDIO_RETRY_DELAYS_S = (0.0,)

    monkeypatch.setattr(
        client,
        "resolve_download_url",
        lambda selected: (
            "https://worker.example/download",
            {"download_resolution": "convert.downloadURL"},
        ),
    )
    monkeypatch.setattr(
        client,
        "_download_verified_audio",
        lambda url, *, progress_callback, chunk_size: (
            b'{"status":"processing"}',
            {"engine": "requests", "total_bytes": 23},
            "application/json",
            url,
            None,
        ),
    )
    monkeypatch.setattr("mp3juice.client.time.sleep", lambda _: None)

    song = client.download(result())

    assert song.duration_s is None
    attempts = song.raw_data["http"]["audio_validation_attempts"]
    assert attempts
    assert "processing" in attempts[0]["payload_preview"]

    client.close()
