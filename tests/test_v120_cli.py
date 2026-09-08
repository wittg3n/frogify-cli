from __future__ import annotations

from frogify.matching import rank_free_text as rank_results
from mp3juice.client import MP3JuiceMusicClient
from mp3juice.models import SearchResult
from mp3juice.retry import RETRY_PROFILES


def result(title: str, source: str = "YouTube", ident: str = "x") -> SearchResult:
    return SearchResult(
        identifier=ident,
        title=title,
        root_source=source,
        raw_data={},
    )


def test_balanced_profile_is_bounded_and_paced():
    policy = RETRY_PROFILES["balanced"]
    assert policy.theta_min_request_interval_s == 0.20
    assert policy.theta_429_backoff_s == (2.0, 5.0)
    assert policy.theta_429_max_retries == 2
    assert policy.theta_retry_after_cap_s == 5.0


def test_client_applies_retry_profile():
    client = MP3JuiceMusicClient(retry_profile="fast", downloader="requests")
    assert client.retry_profile == "fast"
    assert client.THETA_429_BACKOFF_S == (1.5,)
    assert client.THETA_MIN_REQUEST_INTERVAL_S == 0.08
    client.close()


def test_general_ranking_penalizes_unrequested_live_version():
    ranked = rank_results(
        "Adele Hello",
        [
            result("Adele - Hello (Live)", ident="live"),
            result("Adele - Hello (Official Audio)", ident="plain"),
        ],
    )
    assert ranked[0].result.identifier == "plain"


def test_general_ranking_uses_soundcloud_only_as_tiny_tie_break():
    ranked = rank_results(
        "Artist Song",
        [
            result("Artist - Song", "YouTube", "yt"),
            result("Artist - Song", "SoundCloud", "sc"),
        ],
    )
    assert ranked[0].result.identifier == "sc"


def test_original_mix_query_does_not_penalize_matching_original_mix():
    ranked = rank_results(
        "Frenic Before You Leave Original Mix",
        [result("Frenic - Before You Leave Original Mix")],
    )
    assert ranked[0].score > 90


def test_retry_after_is_capped_by_profile():
    import requests

    client = MP3JuiceMusicClient(retry_profile="balanced", downloader="requests")
    response = requests.Response()
    response.status_code = 429
    response.headers["Retry-After"] = "300"
    exc = requests.HTTPError("429")
    exc.response = response

    assert client._retry_after_seconds(exc) == 5.0
    client.close()
