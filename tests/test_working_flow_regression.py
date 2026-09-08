from __future__ import annotations

import inspect

from mp3juice.client import MP3JuiceMusicClient


def test_working_theta_flow_has_no_retry_or_fallback_layer():
    signature = inspect.signature(MP3JuiceMusicClient.__init__)
    assert "theta_retries" not in signature.parameters
    assert "enable_ytdlp_fallback" not in signature.parameters

    assert not hasattr(MP3JuiceMusicClient, "_resolve_youtube_theta")
    assert not hasattr(MP3JuiceMusicClient, "_resolve_youtube_ytdlp")


def test_working_headers_are_original_headers():
    headers = MP3JuiceMusicClient.DEFAULT_HEADERS
    assert "Chrome/120.0.0.0" in headers["User-Agent"]
    assert headers["Referer"] == "https://mp3juice.sc/"
    assert headers["Origin"] == "https://mp3juice.sc"
    assert "Connection" not in headers


def test_youtube_flow_uses_same_client_session_for_all_steps(monkeypatch):
    client = MP3JuiceMusicClient()

    calls = []

    def fake_get_json(url, *, headers=None, params=None):
        calls.append((url, headers, params))
        if url == client.THETA_AUTH_URL:
            return {"key": "abc"}
        if url == client.THETA_INIT_URL:
            return {"convertURL": "https://convert.example/api?x=1"}
        if url.startswith("https://convert.example/api?x=1"):
            return {"redirectURL": "https://redirect.example/api"}
        if url == "https://redirect.example/api":
            return {"downloadURL": "https://cdn.example/file.mp3"}
        raise AssertionError(url)

    monkeypatch.setattr(client, "_get_json", fake_get_json)

    from mp3juice.models import SearchResult

    result = SearchResult(
        identifier="YQHsXMglC9A",
        title="Adele - Hello",
        root_source="YouTube",
        raw_data={},
    )

    url, trace = client._resolve_youtube(result)

    assert url == "https://cdn.example/file.mp3"
    assert len(calls) == 4
    assert calls[0][0] == client.THETA_AUTH_URL
    assert calls[1][0] == client.THETA_INIT_URL
    assert calls[1][1]["Authorization"] == "Bearer abc"
    assert "auth" in trace
    assert "init" in trace
    assert "convert" in trace
    assert "redirect" in trace

    client.close()
