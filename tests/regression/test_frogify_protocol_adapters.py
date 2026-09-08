from __future__ import annotations

from frogify.matching import rank_free_text
from mp3juice.client import MP3JuiceMusicClient
from mp3juice.models import SearchResult


def test_free_text_ranking_penalizes_unrequested_live():
    ranked = rank_free_text(
        "Adele Hello",
        [
            SearchResult("live", "Adele - Hello Live", "YouTube"),
            SearchResult("studio", "Adele - Hello Official Audio", "YouTube"),
        ],
    )
    assert ranked[0].result.identifier == "studio"


def test_theta_adapter_preserves_direct_download_shape(monkeypatch):
    client = MP3JuiceMusicClient(downloader="requests")
    client.THETA_MIN_REQUEST_INTERVAL_S = 0
    selected = SearchResult("yt", "Artist - Song", "YouTube")

    def fake_json(url, *, headers=None, params=None):
        if url == client.THETA_AUTH_URL:
            return {"key": "token"}
        if url == client.THETA_INIT_URL:
            return {"convertURL": "https://worker.test/convert"}
        return {"downloadURL": "https://worker.test/audio.mp3", "redirectURL": ""}

    monkeypatch.setattr(client, "_get_json", fake_json)
    url, trace = client.resolve_download_url(selected)
    assert url.endswith("audio.mp3")
    assert trace["download_resolution"] == "convert.downloadURL"
    client.close()
