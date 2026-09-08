from __future__ import annotations

import pytest
import requests

from mp3juice.client import MP3JuiceMusicClient
from mp3juice.exceptions import DownloadError
from mp3juice.models import SearchResult
from mp3juice.spotify_batch import (
    SpotifyTrack,
    _search_candidates,
    score_candidate,
)


def make_track(
    name: str,
    artists: str,
    duration: float,
) -> SpotifyTrack:
    return SpotifyTrack(
        row_number=2,
        uri="spotify:track:test",
        track_name=name,
        album_name="Album",
        artists_display=artists,
        artists=artists.split(";"),
        release_date="2026",
        duration_s=duration,
    )


def make_result(
    title: str,
    duration: float | None,
    *,
    identifier: str = "id",
    raw_data: dict | None = None,
) -> SearchResult:
    return SearchResult(
        identifier=identifier,
        title=title,
        root_source="YouTube",
        duration_s=duration,
        duration="--:--" if duration is None else "4:10",
        raw_data=raw_data or {},
    )


def test_missing_album_mix_is_soft_when_identity_and_duration_match():
    scored = score_candidate(
        make_track(
            "I'm On Fire - Album Mix",
            "Stateless;Shara Worden",
            320.066,
        ),
        make_result(
            "Stateless - I'm On Fire",
            322.0,
        ),
    )
    assert scored.accepted is True
    assert not any("missing requested 'mix'" in r for r in scored.reasons)


def test_missing_original_mix_is_soft_when_identity_and_duration_match():
    scored = score_candidate(
        make_track(
            "Before You Leave - Original Mix",
            "Frenic",
            249.012,
        ),
        make_result(
            "Frenic - Before You Leave",
            250.0,
        ),
    )
    assert scored.accepted is True
    assert not any("missing requested 'mix'" in r for r in scored.reasons)


def test_missing_requested_remix_remains_strict():
    scored = score_candidate(
        make_track(
            "Coward - Rone Remix",
            "Yael Naim;Rone",
            240.0,
        ),
        make_result(
            "Yael Naim - Coward",
            240.0,
        ),
    )
    assert scored.accepted is False
    assert any("missing requested 'remix'" in r for r in scored.reasons)


def test_theta_429_honors_retry_and_recovers(monkeypatch):
    client = MP3JuiceMusicClient(downloader="requests")
    client.THETA_MIN_REQUEST_INTERVAL_S = 0.0
    client.THETA_RECOVERY_REQUEST_INTERVAL_S = 0.0
    client.THETA_TRANSIENT_RETRY_DELAYS_S = (0.1, 0.2)
    client.THETA_429_MIN_COOLDOWN_S = 0.1

    calls = {"n": 0}
    sleeps: list[float] = []

    def fake_get_json(url, *, headers=None, params=None):
        calls["n"] += 1
        if calls["n"] == 1:
            response = requests.Response()
            response.status_code = 429
            response.headers["Retry-After"] = "0.25"
            error = requests.HTTPError("429 Too Many Requests")
            error.response = response
            raise error
        return {"ok": True}

    monkeypatch.setattr(client, "_get_json", fake_get_json)
    monkeypatch.setattr(
        "mp3juice.client.time.sleep",
        lambda seconds: sleeps.append(seconds),
    )

    payload = client._theta_get_json("https://theta.thetacloud.org/api/v1/init")

    assert payload == {"ok": True}
    assert calls["n"] == 2
    assert sleeps
    assert sleeps[0] >= 0.24

    client.close()


def test_theta_ssl_error_retries_and_recovers(monkeypatch):
    client = MP3JuiceMusicClient(downloader="requests")
    client.THETA_MIN_REQUEST_INTERVAL_S = 0.0
    client.THETA_RECOVERY_REQUEST_INTERVAL_S = 0.0
    client.THETA_TRANSIENT_RETRY_DELAYS_S = (0.1,)

    calls = {"n": 0}
    sleeps: list[float] = []

    def fake_get_json(url, *, headers=None, params=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise requests.exceptions.SSLError("UNEXPECTED_EOF_WHILE_READING")
        return {"ok": True}

    monkeypatch.setattr(client, "_get_json", fake_get_json)
    monkeypatch.setattr(
        "mp3juice.client.time.sleep",
        lambda seconds: sleeps.append(seconds),
    )

    payload = client._theta_get_json("https://worker.thetacloud.org/api/v1/convert")

    assert payload == {"ok": True}
    assert calls["n"] == 2
    assert sleeps == [0.1]

    client.close()


def test_theta_worker_error_6_fails_fast_without_same_url_retries(monkeypatch):
    client = MP3JuiceMusicClient(downloader="requests")
    client.DIRECT_AUDIO_RETRY_DELAYS_S = (0.0, 0.0, 0.0)

    resolve_calls = {"n": 0}
    download_calls = {"n": 0}

    def fake_resolve(selected):
        resolve_calls["n"] += 1
        return (
            "https://worker.example/download",
            {"download_resolution": "convert.downloadURL"},
        )

    def fake_download(url, *, progress_callback, chunk_size):
        download_calls["n"] += 1
        return (
            b'{"progress":0,"error":6}',
            {"engine": "requests", "total_bytes": 24},
            "",
            url,
            None,
        )

    monkeypatch.setattr(client, "resolve_download_url", fake_resolve)
    monkeypatch.setattr(client, "_download_verified_audio", fake_download)

    selected = make_result(
        "Balanescu Quartet - Life and Death",
        573.8,
        identifier="3MqIFA_DP5A",
    )

    with pytest.raises(DownloadError) as caught:
        client.download(selected)

    assert "error=6" in str(caught.value)
    assert caught.value.details["theta_error"]["error"] == 6
    assert resolve_calls["n"] == 1
    assert download_calls["n"] == 1

    client.close()


def test_search_expands_to_secondary_artist_when_primary_queries_are_insufficient():
    track = make_track(
        "Clubbed to Death",
        "Rob Dougan;Maxence Cyrin",
        244.613,
    )

    class FakeClient:
        def __init__(self):
            self.queries = []

        def search(self, keyword, *, limit=10, source="all"):
            self.queries.append(keyword)
            if "Maxence Cyrin" in keyword:
                return [
                    make_result(
                        "Maxence Cyrin - Clubbed to Death",
                        245.0,
                        identifier="correct",
                        raw_data={"artist": "Maxence Cyrin"},
                    )
                ]
            if keyword == "Clubbed to Death":
                return [
                    make_result(
                        "The Matrix - Clubbed to Death - Rob Dougan",
                        262.0,
                        identifier="wrong-version",
                        raw_data={"artist": "Rob Dougan"},
                    )
                ]
            return []

    fake = FakeClient()
    results = _search_candidates(
        fake,
        track,
        search_limit=10,
        duration_tolerance_s=10.0,
    )

    assert any("Maxence Cyrin" in q for q in fake.queries)
    assert any(r.identifier == "correct" for r in results)


def test_long_classical_title_gets_shorter_search_variant():
    track = make_track(
        "Fantasy for Piano 4 Hands in F Minor, D. 940: I. Allegro molto moderato –",
        "Franz Schubert;Maurizio Pollini;Daniele Pollini",
        287.173,
    )

    class FakeClient:
        def __init__(self):
            self.queries = []

        def search(self, keyword, *, limit=10, source="all"):
            self.queries.append(keyword)
            return []

    fake = FakeClient()
    _search_candidates(
        fake,
        track,
        search_limit=10,
        duration_tolerance_s=10.0,
    )

    assert any(
        "Fantasy for Piano 4 Hands in F Minor, D. 940" in q and "Allegro" not in q
        for q in fake.queries
    )
