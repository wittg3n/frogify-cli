from __future__ import annotations

import pytest
import requests

from mp3juice.client import MP3JuiceMusicClient
from mp3juice.exceptions import ResolveError


def make_429():
    response = requests.Response()
    response.status_code = 429
    exc = requests.HTTPError("429")
    exc.response = response
    return exc


def test_fast_policy_defaults():
    client = MP3JuiceMusicClient(downloader="requests", retry_profile="fast")

    assert client.THETA_429_BACKOFF_S == (1.5,)
    assert client.THETA_429_MAX_RETRIES_PER_REQUEST == 1
    assert client.THETA_MIN_REQUEST_INTERVAL_S == 0.08
    assert client.THETA_RECOVERY_REQUEST_INTERVAL_S == 0.25
    assert client.THETA_RECOVERY_SUCCESS_REQUESTS == 4

    client.close()


def test_fast_policy_exhausts_without_extra_long_cooldown(monkeypatch):
    client = MP3JuiceMusicClient(downloader="requests", retry_profile="fast")
    client.THETA_MIN_REQUEST_INTERVAL_S = 0.0
    client.THETA_RECOVERY_REQUEST_INTERVAL_S = 0.0

    clock = {"now": 100.0}
    sleeps = []
    calls = {"n": 0}

    def fake_get_json(url, *, headers=None, params=None):
        calls["n"] += 1
        raise make_429()

    monkeypatch.setattr(client, "_get_json", fake_get_json)
    monkeypatch.setattr(
        "mp3juice.client.time.monotonic",
        lambda: clock["now"],
    )

    def fake_sleep(seconds):
        sleeps.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr("mp3juice.client.time.sleep", fake_sleep)

    with pytest.raises(ResolveError) as caught:
        client._theta_get_json("https://theta.example/init")

    # Initial request + one retry + final failed request.
    assert calls["n"] == 2

    # Only one short retry wait is paid.
    assert sleeps == [1.5]

    assert caught.value.details["fast_fail"] is True
    assert client._theta_cooldown_until == 0.0
    assert client._theta_429_streak == 1

    client.close()


def test_healthy_theta_has_no_artificial_pacing(monkeypatch):
    client = MP3JuiceMusicClient(downloader="requests", retry_profile="fast")
    client.THETA_MIN_REQUEST_INTERVAL_S = 0.0
    client.THETA_RECOVERY_REQUEST_INTERVAL_S = 0.0

    sleeps = []
    monkeypatch.setattr(
        "mp3juice.client.time.sleep",
        lambda seconds: sleeps.append(seconds),
    )
    monkeypatch.setattr(
        client,
        "_get_json",
        lambda url, *, headers=None, params=None: {"ok": True},
    )

    assert client._theta_get_json("https://theta.example/auth") == {"ok": True}
    assert client._theta_get_json("https://theta.example/init") == {"ok": True}

    assert sleeps == []

    client.close()
