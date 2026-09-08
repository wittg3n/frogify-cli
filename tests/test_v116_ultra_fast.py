from mp3juice.client import MP3JuiceMusicClient


def test_ultra_fast_retry_defaults():
    client = MP3JuiceMusicClient(downloader="requests", retry_profile="fast")

    assert client.THETA_429_BACKOFF_S == (1.5,)
    assert client.THETA_429_MAX_RETRIES_PER_REQUEST == 1
    assert client.THETA_TRANSIENT_RETRY_DELAYS_S == (0.75,)
    assert client.THETA_MIN_REQUEST_INTERVAL_S == 0.08
    assert client.THETA_RECOVERY_REQUEST_INTERVAL_S == 0.25
    assert client.THETA_RECOVERY_SUCCESS_REQUESTS == 4

    assert client.CONVERT_POLL_ATTEMPTS == 2
    assert client.CONVERT_POLL_DELAYS_S == (0.35,)
    assert client.DIRECT_AUDIO_RETRY_DELAYS_S == (0.35,)

    client.close()
