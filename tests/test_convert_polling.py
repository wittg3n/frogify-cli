from __future__ import annotations

import pytest

from mp3juice.client import MP3JuiceMusicClient
from mp3juice.exceptions import ResolveError
from mp3juice.models import SearchResult


def make_result():
    return SearchResult(
        identifier="abc123",
        title="Artist - Track",
        root_source="YouTube",
        raw_data={},
    )


def test_theta_convert_polls_until_redirect(monkeypatch):
    client = MP3JuiceMusicClient()
    client.THETA_MIN_REQUEST_INTERVAL_S = 0.0
    client.THETA_RECOVERY_REQUEST_INTERVAL_S = 0.0
    client.CONVERT_POLL_ATTEMPTS = 5
    client.CONVERT_POLL_DELAYS_S = (0.1, 0.2, 0.3, 0.4)

    convert_calls = {"count": 0}
    sleeps = []

    def fake_get_json(url, *, headers=None, params=None):
        if url == client.THETA_AUTH_URL:
            return {"key": "token"}

        if url == client.THETA_INIT_URL:
            return {"convertURL": "https://convert.example/api?x=1"}

        if url.startswith("https://convert.example/api?x=1"):
            convert_calls["count"] += 1
            if convert_calls["count"] == 1:
                return {"status": "queued", "progress": 0}
            if convert_calls["count"] == 2:
                return {"status": "processing", "progress": 65}
            return {
                "status": "completed",
                "redirectURL": "https://redirect.example/final",
            }

        if url == "https://redirect.example/final":
            return {"downloadURL": "https://cdn.example/track.mp3"}

        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(client, "_get_json", fake_get_json)
    monkeypatch.setattr(
        "mp3juice.client.time.sleep",
        lambda seconds: sleeps.append(seconds),
    )

    url, trace = client._resolve_youtube(make_result())

    assert url == "https://cdn.example/track.mp3"
    assert convert_calls["count"] == 3
    assert sleeps == [0.1, 0.2]
    assert len(trace["convert_attempts"]) == 3
    assert trace["convert_attempts"][0]["response"]["status"] == "queued"
    assert trace["convert_attempts"][1]["response"]["progress"] == 65
    assert trace["convert"]["redirectURL"] == "https://redirect.example/final"

    client.close()


def test_theta_convert_exhaustion_contains_raw_responses(monkeypatch):
    client = MP3JuiceMusicClient()
    client.THETA_MIN_REQUEST_INTERVAL_S = 0.0
    client.THETA_RECOVERY_REQUEST_INTERVAL_S = 0.0
    client.CONVERT_POLL_ATTEMPTS = 3
    client.CONVERT_POLL_DELAYS_S = (0.0, 0.0)

    convert_calls = {"count": 0}

    def fake_get_json(url, *, headers=None, params=None):
        if url == client.THETA_AUTH_URL:
            return {"key": "token"}

        if url == client.THETA_INIT_URL:
            return {"convertURL": "https://convert.example/api?x=1"}

        if url.startswith("https://convert.example/api?x=1"):
            convert_calls["count"] += 1
            return {
                "status": "processing",
                "progress": convert_calls["count"] * 10,
                "message": "not ready",
            }

        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(client, "_get_json", fake_get_json)
    monkeypatch.setattr("mp3juice.client.time.sleep", lambda _: None)

    with pytest.raises(ResolveError) as caught:
        client._resolve_youtube(make_result())

    error = caught.value

    assert "after 3 attempt(s)" in str(error)
    assert error.details["stage"] == "convert"
    assert error.details["video_id"] == "abc123"
    assert error.details["attempt_count"] == 3
    assert len(error.details["convert_responses"]) == 3
    assert error.details["convert_responses"][-1]["response"]["progress"] == 30

    client.close()
