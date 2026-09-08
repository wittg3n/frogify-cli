from __future__ import annotations

import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
from requests.cookies import RequestsCookieJar

from mp3juice.aria2_downloader import Aria2RPCDownloader, Aria2TransferError
from mp3juice.client import MP3JuiceMusicClient


def test_aria2_header_conversion():
    ua, headers = Aria2RPCDownloader._headers_for_aria2(
        {
            "User-Agent": "UA",
            "Referer": "https://example.test/",
            "Origin": "https://example.test",
            "Connection": "keep-alive",
            "Cookie": "session=private",
        }
    )
    assert ua == "UA"
    assert "Referer: https://example.test/" in headers
    assert "Origin: https://example.test" in headers
    assert not any(h.lower().startswith("connection:") for h in headers)
    assert not any(h.lower().startswith("cookie:") for h in headers)


def test_client_auto_falls_back_to_requests(monkeypatch):
    client = MP3JuiceMusicClient(downloader="auto")

    monkeypatch.setattr(
        client,
        "_get_aria2",
        lambda: (_ for _ in ()).throw(RuntimeError("should be aria2 error")),
    )

    # RuntimeError isn't intentionally swallowed: only known aria2 failures are.
    with pytest.raises(RuntimeError):
        client._download_final_url(
            "https://example.test/file.mp3",
            progress_callback=None,
            chunk_size=1024,
        )
    client.close()


def test_client_explicit_aria2_failure_is_download_error(monkeypatch):
    from mp3juice.aria2_downloader import Aria2Unavailable
    from mp3juice.exceptions import DownloadError

    client = MP3JuiceMusicClient(downloader="aria2")
    monkeypatch.setattr(
        client,
        "_get_aria2",
        lambda: (_ for _ in ()).throw(Aria2Unavailable("missing")),
    )

    with pytest.raises(DownloadError, match="aria2 backend failed"):
        client._download_final_url(
            "https://example.test/file.mp3",
            progress_callback=None,
            chunk_size=1024,
        )
    client.close()


def test_aria2_rpc_polling_reports_progress(tmp_path, monkeypatch):
    # Build object without spawning a real aria2 binary.
    downloader = object.__new__(Aria2RPCDownloader)
    downloader.connections = 8
    downloader.timeout = 30.0
    downloader.verify_ssl = True
    downloader.logger = __import__("logging").getLogger("test")
    downloader._process = type("P", (), {"poll": lambda self: None})()
    downloader._secret = "secret"
    downloader._rpc_session = type("S", (), {"close": lambda self: None})()

    monkeypatch.setattr(downloader, "_start", lambda cookies=None: None)

    states = iter(
        [
            {
                "status": "active",
                "totalLength": "1000",
                "completedLength": "250",
                "downloadSpeed": "500",
                "connections": "4",
                "errorCode": "0",
                "errorMessage": "",
            },
            {
                "status": "active",
                "totalLength": "1000",
                "completedLength": "750",
                "downloadSpeed": "700",
                "connections": "4",
                "errorCode": "0",
                "errorMessage": "",
            },
            {
                "status": "complete",
                "totalLength": "1000",
                "completedLength": "1000",
                "downloadSpeed": "0",
                "connections": "0",
                "errorCode": "0",
                "errorMessage": "",
            },
        ]
    )

    gid = "abc"

    # Replace tempfile directory with deterministic path and create output
    # when addUri is called.
    import mp3juice.aria2_downloader as mod

    monkeypatch.setattr(mod.tempfile, "mkdtemp", lambda prefix: str(tmp_path / "aria"))
    (tmp_path / "aria").mkdir()

    def fake_rpc(method, params=None, timeout=2.0):
        if method == "aria2.addUri":
            (tmp_path / "aria" / "audio.download").write_bytes(b"x" * 1000)
            return gid
        if method == "aria2.tellStatus":
            return next(states)
        if method == "aria2.removeDownloadResult":
            return "OK"
        raise AssertionError(method)

    monkeypatch.setattr(downloader, "_rpc", fake_rpc)
    monkeypatch.setattr(mod.time, "sleep", lambda _: None)

    updates = []
    contents, meta = downloader.download(
        "https://example.test/file.mp3",
        headers={"User-Agent": "UA"},
        progress_callback=lambda done, total: updates.append((done, total)),
    )

    assert len(contents) == 1000
    assert meta["engine"] == "aria2"
    assert (250, 1000) in updates
    assert (750, 1000) in updates
    assert updates[-1] == (1000, 1000)


def test_timed_out_aria2_transfer_is_cancelled_and_cleaned(monkeypatch):
    import mp3juice.aria2_downloader as mod

    downloader = Aria2RPCDownloader(executable="fake", timeout=5)
    downloader._process = SimpleNamespace(poll=lambda: None)
    monkeypatch.setattr(downloader, "_start", lambda cookies=None: None)
    calls = []
    directories = []

    def fake_rpc(method, params=None, **kwargs):
        calls.append(method)
        if method == "aria2.addUri":
            directories.append(Path(params[1]["dir"]))
            return "gid"
        return "OK"

    ticks = iter([0, 61])
    monkeypatch.setattr(downloader, "_rpc", fake_rpc)
    monkeypatch.setattr(mod.time, "monotonic", lambda: next(ticks))
    with pytest.raises(Aria2TransferError, match="time limit"):
        downloader.download("https://example.test/audio.mp3")
    assert calls == ["aria2.addUri", "aria2.forceRemove", "aria2.removeDownloadResult"]
    assert not directories[0].exists()
    downloader._rpc_session.close()


@pytest.mark.skipif(not Aria2RPCDownloader.available(), reason="aria2c is not installed")
def test_real_aria2_preserves_cookie_scope_on_redirect_and_refresh():
    observed = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            observed.append((self.path, self.headers.get("Cookie", "").rstrip("; ")))
            if self.path == "/allowed/start":
                self.send_response(302)
                port = self.server.server_address[1]
                self.send_header("Location", f"http://localhost:{port}/final")
                self.end_headers()
            else:
                self.send_response(200)
                self.send_header("Content-Length", "5")
                self.end_headers()
                self.wfile.write(b"audio")

        def log_message(self, *args):
            pass

    cookies = RequestsCookieJar()
    cookies.set("scoped", "first", domain="127.0.0.1", path="/allowed")
    cookies.set("foreign", "private", domain="example.test", path="/")
    cookies.set("other_path", "private", domain="127.0.0.1", path="/private")
    cookies.set("secure", "private", domain="127.0.0.1", path="/", secure=True)
    cookies.set("expired", "private", domain="127.0.0.1", path="/", expires=1)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    downloader = Aria2RPCDownloader(timeout=5)
    cookie_directory = None
    ports = []
    try:
        url = f"http://127.0.0.1:{server.server_port}/allowed/start"
        assert downloader.download(url, cookies=cookies)[0] == b"audio"
        ports.append(downloader._port)
        assert next(c for c in cookies if c.name == "scoped").expires is None
        cookies.set("scoped", "second", domain="127.0.0.1", path="/allowed")
        assert downloader.download(url, cookies=cookies)[0] == b"audio"
        ports.append(downloader._port)
        cookie_directory = Path(downloader._cookie_dir.name)
        assert observed == [
            ("/allowed/start", "scoped=first"),
            ("/final", ""),
            ("/allowed/start", "scoped=second"),
            ("/final", ""),
        ]
    finally:
        downloader.close()
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
    assert cookie_directory is not None and not cookie_directory.exists()
    for port in ports:
        with socket.socket() as connection:
            assert connection.connect_ex(("127.0.0.1", port)) != 0
