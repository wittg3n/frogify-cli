from __future__ import annotations

from mp3juice.client import MP3JuiceMusicClient
from mp3juice.models import SearchResult


def make_result():
    return SearchResult(
        identifier="6X_iJYPgQO4",
        title="Le banc - Papa Tout Gris",
        root_source="YouTube",
        raw_data={},
    )


def test_convert_direct_download_url_is_success(monkeypatch):
    client = MP3JuiceMusicClient()
    calls = []

    def fake_get_json(url, *, headers=None, params=None):
        calls.append(url)
        if url == client.THETA_AUTH_URL:
            return {"key": "token"}
        if url == client.THETA_INIT_URL:
            return {"convertURL": "https://convert.example/api?x=1"}
        if url.startswith("https://convert.example/api?x=1"):
            return {
                "error": 0,
                "progressURL": "https://worker.example/progress?sig=x",
                "downloadURL": "https://worker.example/download?sig=x",
                "redirectURL": "",
                "redirect": 0,
                "title": "Le banc - Papa Tout Gris",
            }
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(client, "_get_json", fake_get_json)
    monkeypatch.setattr("mp3juice.client.time.sleep", lambda _: None)

    url, trace = client._resolve_youtube(make_result())

    assert url == "https://worker.example/download?sig=x"
    assert trace["download_resolution"] == "convert.downloadURL"
    assert len(trace["convert_attempts"]) == 1
    # Most important regression: no request is made to an empty redirectURL.
    assert "" not in calls
    client.close()


def test_redirect_shape_still_works(monkeypatch):
    client = MP3JuiceMusicClient()

    def fake_get_json(url, *, headers=None, params=None):
        if url == client.THETA_AUTH_URL:
            return {"key": "token"}
        if url == client.THETA_INIT_URL:
            return {"convertURL": "https://convert.example/api?x=1"}
        if url.startswith("https://convert.example/api?x=1"):
            return {"redirectURL": "https://redirect.example/final"}
        if url == "https://redirect.example/final":
            return {"downloadURL": "https://cdn.example/file.mp3"}
        raise AssertionError(url)

    monkeypatch.setattr(client, "_get_json", fake_get_json)

    url, trace = client._resolve_youtube(make_result())
    assert url == "https://cdn.example/file.mp3"
    assert trace["redirect"]["downloadURL"] == url
    client.close()
