import requests

from mp3juice.client import MP3JuiceMusicClient
from mp3juice.models import SearchResult


def result():
    return SearchResult(
        identifier="abc123",
        title="Test",
        root_source="YouTube",
        raw_data={},
    )


def test_theta_default_headers_match_original_working_client():
    assert "Chrome/120.0.0.0" in MP3JuiceMusicClient.DEFAULT_HEADERS["User-Agent"]
    assert "Connection" not in MP3JuiceMusicClient.DEFAULT_HEADERS


def test_theta_new_session_does_not_force_connection_close():
    client = MP3JuiceMusicClient()
    session = client.session
    try:
        assert session.headers.get("Connection") != "close"
        assert "Chrome/120.0.0.0" in session.headers["User-Agent"]
    finally:
        client.close()


def test_theta_retries_complete_flow(monkeypatch):
    client = MP3JuiceMusicClient()
    client.THETA_MIN_REQUEST_INTERVAL_S = 0.0
    client.THETA_TRANSIENT_RETRY_DELAYS_S = (0.0, 0.0)
    calls = {"n": 0}

    def fake_get_json(url, *, headers=None, params=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise requests.ConnectionError("reset")
        return {"ok": True}

    monkeypatch.setattr(client, "_get_json", fake_get_json)
    monkeypatch.setattr("mp3juice.client.time.sleep", lambda _: None)

    payload = client._theta_get_json("https://theta.example/init")

    assert calls["n"] == 3
    assert payload == {"ok": True}

    client.close()
