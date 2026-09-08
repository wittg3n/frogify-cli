from __future__ import annotations

import pytest
import requests

from mp3juice.client import MP3JuiceMusicClient


def _http_error(status: int, retry_after: str | None = None):
    response = requests.Response()
    response.status_code = status
    if retry_after is not None:
        response.headers["Retry-After"] = retry_after
    exc = requests.HTTPError(f"{status} error")
    exc.response = response
    return exc


def test_theta_429_retries_same_url_with_escalating_global_cooldown(monkeypatch):
    client = MP3JuiceMusicClient(downloader="requests")
    client.THETA_429_BACKOFF_S = (3.0, 7.0, 11.0)
    client.THETA_429_MAX_RETRIES_PER_REQUEST = 5
    client.THETA_MIN_REQUEST_INTERVAL_S = 0.0
    client.THETA_RECOVERY_REQUEST_INTERVAL_S = 0.0

    calls = []
    sleeps = []

    def fake_get_json(url, *, headers=None, params=None):
        calls.append(url)
        if len(calls) == 1:
            raise _http_error(429)
        if len(calls) == 2:
            raise _http_error(429)
        return {"ok": True}

    # Deterministic monotonic clock where sleep advances time.
    clock = {"now": 100.0}

    monkeypatch.setattr(client, "_get_json", fake_get_json)
    monkeypatch.setattr(
        "mp3juice.client.time.monotonic",
        lambda: clock["now"],
    )

    def fake_sleep(seconds):
        sleeps.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr(
        "mp3juice.client.time.sleep",
        fake_sleep,
    )

    url = "https://theta.thetacloud.org/api/v1/init"
    payload = client._theta_get_json(url)

    assert payload == {"ok": True}
    assert calls == [url, url, url]

    # First strike = 3s, second strike = 7s.
    assert sleeps == [3.0, 7.0]

    # Success closes the active cooldown, but the adaptive penalty remains
    # during recovery pacing so another immediate 429 escalates correctly.
    assert client._theta_429_streak == 2
    assert client._theta_cooldown_until == 0.0
    assert client._theta_recovery_requests_remaining > 0

    client.close()


def test_theta_429_retry_after_can_extend_cooldown(monkeypatch):
    client = MP3JuiceMusicClient(downloader="requests")
    client.THETA_429_BACKOFF_S = (3.0,)
    client.THETA_429_MAX_RETRIES_PER_REQUEST = 2
    client.THETA_MIN_REQUEST_INTERVAL_S = 0.0
    client.THETA_RECOVERY_REQUEST_INTERVAL_S = 0.0

    calls = {"n": 0}
    sleeps = []
    clock = {"now": 50.0}

    def fake_get_json(url, *, headers=None, params=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _http_error(429, "9")
        return {"ok": True}

    monkeypatch.setattr(client, "_get_json", fake_get_json)
    monkeypatch.setattr(
        "mp3juice.client.time.monotonic",
        lambda: clock["now"],
    )

    def fake_sleep(seconds):
        sleeps.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr("mp3juice.client.time.sleep", fake_sleep)

    assert client._theta_get_json("https://theta.example/init") == {"ok": True}
    assert sleeps == [5.0]

    client.close()


def test_theta_recovery_pacing_survives_success_after_429(monkeypatch):
    client = MP3JuiceMusicClient(downloader="requests")
    client.THETA_429_BACKOFF_S = (2.0,)
    client.THETA_429_MAX_RETRIES_PER_REQUEST = 2
    client.THETA_MIN_REQUEST_INTERVAL_S = 0.0
    client.THETA_RECOVERY_REQUEST_INTERVAL_S = 1.5
    client.THETA_RECOVERY_SUCCESS_REQUESTS = 3

    clock = {"now": 10.0}
    sleeps = []
    call_count = {"n": 0}

    def fake_get_json(url, *, headers=None, params=None):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise _http_error(429)
        return {"ok": True}

    monkeypatch.setattr(client, "_get_json", fake_get_json)
    monkeypatch.setattr(
        "mp3juice.client.time.monotonic",
        lambda: clock["now"],
    )

    def fake_sleep(seconds):
        sleeps.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr("mp3juice.client.time.sleep", fake_sleep)

    # First call: 429, then 2 second breaker cooldown, then success.
    client._theta_get_json("https://theta.example/init")

    # Recovery mode remains active after the success.
    assert client._theta_recovery_requests_remaining == 2

    # Another immediate Theta request must be paced by 1.5 seconds.
    client._theta_get_json("https://theta.example/convert")

    assert any(abs(s - 1.5) < 1e-9 for s in sleeps)
    assert client._theta_recovery_requests_remaining == 1

    client.close()


def test_theta_recoverable_errors_do_not_use_request_traceback_logging(monkeypatch):
    client = MP3JuiceMusicClient(downloader="requests")
    client.THETA_TRANSIENT_RETRY_DELAYS_S = (0.0,)
    client.THETA_MIN_REQUEST_INTERVAL_S = 0.0

    seen_log_errors = []
    calls = {"n": 0}

    def fake_get_json(url, *, headers=None, params=None):
        seen_log_errors.append(client._suppress_request_error_logging)
        calls["n"] += 1
        if calls["n"] == 1:
            raise requests.exceptions.SSLError("EOF")
        return {"ok": True}

    monkeypatch.setattr(client, "_get_json", fake_get_json)
    monkeypatch.setattr("mp3juice.client.time.sleep", lambda _: None)

    assert client._theta_get_json("https://theta.example/init") == {"ok": True}
    assert seen_log_errors == [True, True]

    client.close()


def test_normal_get_json_still_logs_errors_by_default(monkeypatch):
    client = MP3JuiceMusicClient(downloader="requests")

    class FakeSession:
        def request(self, **kwargs):
            raise requests.ConnectionError("boom")

        def close(self):
            pass

    client.session = FakeSession()

    logged = {"n": 0}
    monkeypatch.setattr(
        client.logger,
        "exception",
        lambda *args, **kwargs: logged.__setitem__("n", logged["n"] + 1),
    )

    with pytest.raises(requests.ConnectionError):
        client._get_json("https://example.invalid")

    assert logged["n"] == 1

    client.close()
