from mp3juice.client import MP3JuiceMusicClient
from mp3juice.models import SearchResult


class FakeResponse:
    def __init__(self, chunks, *, content_length=None):
        self._chunks = list(chunks)
        self.headers = {"Content-Type": "audio/mpeg"}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)
        self.url = "https://example.test/audio.mp3"
        self.closed = False

    def iter_content(self, chunk_size=1):
        yield from self._chunks

    def close(self):
        self.closed = True


class FakeClient(MP3JuiceMusicClient):
    def __init__(self, response):
        self.response = response
        self.timeout = 30.0
        self.verify_ssl = True

    def resolve_download_url(self, result):
        return "https://example.test/audio.mp3", {
            "backend": "test",
            "ext": "mp3",
        }

    def _request(self, method, url, **kwargs):
        assert method == "GET"
        assert kwargs["stream"] is True
        return self.response


def result():
    return SearchResult(
        identifier="abc123",
        title="Progress Test",
        root_source="YouTube",
        raw_data={},
    )


def test_progress_callback_with_content_length(monkeypatch):
    response = FakeResponse(
        [b"a" * 4, b"b" * 3, b"c" * 3],
        content_length=10,
    )
    client = FakeClient(response)

    monkeypatch.setattr(
        "mp3juice.client.get_audio_duration",
        lambda _: 61.0,
    )

    updates = []
    song = client.download(
        result(),
        progress_callback=lambda completed, total: updates.append((completed, total)),
        chunk_size=1024,
    )

    assert response.closed is True
    assert song.file_size_bytes == 10
    assert song.downloaded_contents == b"a" * 4 + b"b" * 3 + b"c" * 3
    assert song.duration == "1:01"

    assert updates[0] == (0, 10)
    assert (4, 10) in updates
    assert (7, 10) in updates
    assert updates[-1] == (10, 10)


def test_progress_callback_without_content_length(monkeypatch):
    response = FakeResponse([b"x" * 5, b"y" * 7])
    client = FakeClient(response)

    monkeypatch.setattr(
        "mp3juice.client.get_audio_duration",
        lambda _: None,
    )

    updates = []
    song = client.download(
        result(),
        progress_callback=lambda completed, total: updates.append((completed, total)),
        chunk_size=1024,
    )

    assert song.file_size_bytes == 12
    assert updates[0] == (0, None)
    assert (5, None) in updates
    assert (12, None) in updates

    # Final update promotes the actual byte count to the total so the CLI
    # can render a clean completed state.
    assert updates[-1] == (12, 12)


def test_rejects_tiny_chunk_size():
    response = FakeResponse([b"x"])
    client = FakeClient(response)

    try:
        client.download(result(), chunk_size=100)
    except ValueError as exc:
        assert "chunk_size" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
