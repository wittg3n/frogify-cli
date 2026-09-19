from __future__ import annotations

import copy
import logging
import os
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
from collections.abc import Callable
from contextlib import suppress
from http.cookiejar import CookieJar, MozillaCookieJar
from pathlib import Path

import requests

ProgressCallback = Callable[[int, int | None], None]


class Aria2Unavailable(RuntimeError):
    """Raised when aria2c is requested but unavailable."""


class Aria2TransferError(RuntimeError):
    """Raised when aria2c cannot complete an HTTP transfer."""


class Aria2RPCDownloader:
    """
    Persistent local aria2c JSON-RPC worker.

    Only the final short-lived audio URL is handed to aria2. MP3Juice/Theta
    resolution stays entirely in MP3JuiceMusicClient.
    """

    def __init__(
        self,
        *,
        executable: str | None = None,
        connections: int = 8,
        timeout: float = 30.0,
        verify_ssl: bool = True,
        logger: logging.Logger | None = None,
    ) -> None:
        self.executable = executable or shutil.which("aria2c")
        if not self.executable:
            raise Aria2Unavailable(
                "aria2c was not found in PATH. Install aria2 or use --downloader requests."
            )

        self.connections = max(1, min(int(connections), 16))
        self.timeout = max(5.0, float(timeout))
        self.verify_ssl = bool(verify_ssl)
        self.logger = logger or logging.getLogger("Aria2RPCDownloader")

        self._process: subprocess.Popen | None = None
        self._rpc_session = requests.Session()
        self._rpc_session.trust_env = False  # RPC is local; never send it through a proxy.
        self._secret = secrets.token_urlsafe(24)
        self._port = self._find_free_port()
        self._rpc_url = f"http://127.0.0.1:{self._port}/jsonrpc"
        self._rpc_id = 0
        self._cookie_state: tuple = ()
        self._cookie_dir: tempfile.TemporaryDirectory | None = None

    @staticmethod
    def available(executable: str | None = None) -> bool:
        return bool(executable or shutil.which("aria2c"))

    @staticmethod
    def _find_free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def _start(self, cookies: CookieJar | None = None) -> None:
        cookie_state = tuple(
            (c.domain, c.domain_specified, c.path, c.name, c.value, c.secure, c.expires)
            for c in (cookies or [])
        )
        if (
            self._process is not None
            and self._process.poll() is None
            and cookie_state == self._cookie_state
        ):
            return
        self.close()
        self._cookie_state = cookie_state
        self._port = self._find_free_port()
        self._rpc_url = f"http://127.0.0.1:{self._port}/jsonrpc"

        args = [
            str(self.executable),
            "--no-conf=true",
            "--enable-rpc=true",
            "--rpc-listen-all=false",
            f"--rpc-listen-port={self._port}",
            f"--rpc-secret={self._secret}",
            "--max-concurrent-downloads=1",
            "--console-log-level=error",
            "--summary-interval=0",
            "--max-download-result=10",
            "--file-allocation=none",
        ]
        if cookies:
            self._cookie_dir = tempfile.TemporaryDirectory(prefix="frogify-cookies-")
            cookie_path = Path(self._cookie_dir.name) / "cookies.txt"
            jar = MozillaCookieJar(str(cookie_path))
            for cookie in cookies:
                exported = copy.copy(cookie)
                # Netscape session cookies use 0; MozillaCookieJar otherwise writes a blank.
                if exported.expires is None:
                    exported.expires = 0
                jar.set_cookie(exported)
            jar.save(ignore_discard=True, ignore_expires=True)
            # Native cookie handling preserves scope even when the CDN redirects.
            args.append(f"--load-cookies={cookie_path}")

        creationflags = 0
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags = subprocess.CREATE_NO_WINDOW

        try:
            self._process = subprocess.Popen(
                args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
        except OSError as exc:
            self.close()
            raise Aria2Unavailable(f"Cannot start aria2c: {exc}") from exc

        deadline = time.monotonic() + 4.0
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                raise Aria2Unavailable("aria2c exited while starting its local RPC server.")
            try:
                self._rpc("aria2.getVersion", timeout=0.5)
                return
            except Exception as exc:
                last_error = exc
                time.sleep(0.08)

        self.close()
        raise Aria2Unavailable(f"aria2c RPC server did not become ready: {last_error}")

    def _rpc(
        self,
        method: str,
        params: list | None = None,
        *,
        timeout: float = 2.0,
    ):
        self._rpc_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": str(self._rpc_id),
            "method": method,
            "params": [f"token:{self._secret}", *(params or [])],
        }
        response = self._rpc_session.post(
            self._rpc_url,
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            error = data["error"]
            raise Aria2TransferError(f"aria2 RPC error {error.get('code')}: {error.get('message')}")
        return data.get("result")

    @staticmethod
    def _headers_for_aria2(headers: dict[str, str] | None) -> tuple[str | None, list[str]]:
        user_agent: str | None = None
        extra: list[str] = []
        blocked = {"host", "content-length", "connection", "transfer-encoding", "cookie"}

        for name, value in (headers or {}).items():
            lname = name.casefold()
            if lname == "user-agent":
                user_agent = str(value)
                continue
            if lname in blocked:
                continue
            extra.append(f"{name}: {value}")

        return user_agent, extra

    def download(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        cookies: CookieJar | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> tuple[bytes, dict[str, object]]:
        self._start(cookies)

        temp_dir = Path(tempfile.mkdtemp(prefix="mp3juice-aria2-"))
        output_name = "audio.download"
        output_path = temp_dir / output_name
        gid: str | None = None
        complete = False

        user_agent, extra_headers = self._headers_for_aria2(headers)
        options: dict[str, object] = {
            "dir": str(temp_dir),
            "out": output_name,
            "split": str(self.connections),
            "max-connection-per-server": str(self.connections),
            # Music files here are commonly only ~3-10 MiB. aria2's larger
            # default min split size would otherwise collapse to one connection.
            "min-split-size": "1M",
            "piece-length": "1M",
            "continue": "true",
            "allow-overwrite": "true",
            "auto-file-renaming": "false",
            "file-allocation": "none",
            "max-tries": "3",
            "retry-wait": "1",
            "connect-timeout": str(max(1, min(int(self.timeout), 15))),
            "timeout": str(max(5, int(self.timeout))),
            "check-certificate": "true" if self.verify_ssl else "false",
        }
        if user_agent:
            options["user-agent"] = user_agent
        if extra_headers:
            options["header"] = extra_headers

        try:
            gid = str(self._rpc("aria2.addUri", [[url], options]))
            peak_speed_bps = 0
            max_connections_seen = 0
            deadline = time.monotonic() + max(60.0, self.timeout * 4)

            while True:
                if time.monotonic() >= deadline:
                    raise Aria2TransferError("aria2 transfer exceeded its time limit.")
                if self._process is None or self._process.poll() is not None:
                    raise Aria2TransferError("aria2c exited during the download.")

                status = self._rpc(
                    "aria2.tellStatus",
                    [
                        gid,
                        [
                            "status",
                            "totalLength",
                            "completedLength",
                            "downloadSpeed",
                            "connections",
                            "errorCode",
                            "errorMessage",
                        ],
                    ],
                    timeout=2.0,
                )
                if not isinstance(status, dict):
                    raise Aria2TransferError("aria2 returned an invalid status response.")
                peak_speed_bps = max(
                    peak_speed_bps,
                    int(status.get("downloadSpeed") or 0),
                )
                max_connections_seen = max(
                    max_connections_seen,
                    int(status.get("connections") or 0),
                )

                total_raw = int(status.get("totalLength") or 0)
                completed = int(status.get("completedLength") or 0)
                total = total_raw if total_raw > 0 else None

                if progress_callback is not None:
                    progress_callback(completed, total)

                state = str(status.get("status") or "")
                if state == "complete":
                    complete = True
                    break
                if state in {"error", "removed"}:
                    code = status.get("errorCode") or "?"
                    message = status.get("errorMessage") or "unknown aria2 error"
                    raise Aria2TransferError(f"aria2 download failed ({code}): {message}")

                time.sleep(0.18)

            if not output_path.exists():
                raise Aria2TransferError(
                    "aria2 reported completion but the output file is missing."
                )

            contents = output_path.read_bytes()
            if not contents:
                raise Aria2TransferError("aria2 downloaded an empty file.")

            if progress_callback is not None:
                progress_callback(len(contents), len(contents))

            metadata: dict[str, object] = {
                "engine": "aria2",
                "connections_requested": self.connections,
                "max_connections_seen": max_connections_seen,
                "peak_download_speed_bps": peak_speed_bps,
                "total_bytes": len(contents),
            }
            return contents, metadata

        finally:
            if gid:
                if not complete:
                    with suppress(Exception):
                        self._rpc("aria2.forceRemove", [gid], timeout=0.5)
                with suppress(Exception):
                    self._rpc("aria2.removeDownloadResult", [gid], timeout=0.5)
            shutil.rmtree(temp_dir, ignore_errors=True)

    def close(self) -> None:
        if self._process is not None:
            with suppress(Exception):
                self._rpc("aria2.forceShutdown", timeout=0.5)
            try:
                self._process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                self._process.terminate()
                try:
                    self._process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait()
        self._process = None
        self._rpc_session.close()
        if self._cookie_dir is not None:
            self._cookie_dir.cleanup()
            self._cookie_dir = None
        self._cookie_state = ()

    def __enter__(self) -> Aria2RPCDownloader:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
