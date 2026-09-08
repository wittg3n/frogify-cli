from __future__ import annotations

import base64
import copy
import json
import logging
import time
from collections.abc import Callable, Iterable
from itertools import zip_longest
from typing import Any
from urllib.parse import quote

import requests

from .aria2_downloader import Aria2RPCDownloader, Aria2TransferError, Aria2Unavailable
from .exceptions import DownloadError, ResolveError, SearchError
from .models import SearchResult, SongInfo
from .retry import get_retry_policy
from .utils import (
    bytes_to_mb,
    get_audio_duration,
    guess_extension,
    parse_duration_seconds,
    seconds_to_hms,
)


class MP3JuiceMusicClient:
    """
    Standalone client implementing the MP3Juice flow represented by the
    original musicdl MP3JuiceMusicClient.

    Search:
        MP3Juice -> YouTube + SoundCloud result metadata

    YouTube resolution:
        Theta auth -> init -> convert -> redirect -> download URL

    SoundCloud resolution:
        ThetaCloud direct route
    """

    source = "MP3JuiceMusicClient"

    BASE_URL = "https://mp3juice.sc"
    SEARCH_URL = f"{BASE_URL}/api/v1/search"

    THETA_AUTH_URL = "https://theta.thetacloud.org/api/v1/auth"
    THETA_INIT_URL = "https://theta.thetacloud.org/api/v1/init"
    THETACLOUD_BASE_URL = "https://thetacloud.org"

    # The first convert response is sometimes accepted by Theta before the
    # redirect URL is ready. Keep the original request flow, but poll only
    # this stage for a short bounded window.
    CONVERT_POLL_ATTEMPTS = 2
    CONVERT_POLL_DELAYS_S = (0.5,)

    # convert.downloadURL can exist before the worker has finished producing
    # audio. If the downloaded payload cannot be parsed as audio, retry the
    # same signed URL briefly, then re-resolve Theta once.
    DIRECT_AUDIO_RETRY_DELAYS_S = (0.5,)

    # Theta occasionally rate-limits long batches. Treat HTTP 429 as a
    # client-global circuit breaker rather than a per-candidate failure.
    #
    # The same API request/candidate is retained while the breaker cools down.
    THETA_429_BACKOFF_S = (2.0,)
    THETA_429_MAX_RETRIES_PER_REQUEST = 1

    # Non-rate-limit transient failures stay short and bounded.
    THETA_TRANSIENT_RETRY_DELAYS_S = (1.0,)

    # Gentle pacing reduces the chance of entering 429 in the first place.
    THETA_MIN_REQUEST_INTERVAL_S = 0.0

    # After any 429, temporarily slow Theta traffic even after the first
    # successful response, so the batch does not immediately trip the limit
    # again.
    THETA_RECOVERY_REQUEST_INTERVAL_S = 0.0
    THETA_RECOVERY_SUCCESS_REQUESTS = 0

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": f"{BASE_URL}/",
        "Origin": BASE_URL,
        "Accept": "*/*",
    }

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        verify_ssl: bool = True,
        session: requests.Session | None = None,
        logger: logging.Logger | None = None,
        downloader: str = "auto",
        aria2_connections: int = 8,
        retry_profile: str = "balanced",
    ) -> None:
        self.timeout = timeout
        self.verify_ssl = verify_ssl

        self.session = session or requests.Session()
        self.session.headers.update(copy.deepcopy(self.DEFAULT_HEADERS))

        self.logger = logger or logging.getLogger(self.source)

        policy = get_retry_policy(retry_profile)
        self.retry_profile = policy.name
        self.THETA_429_BACKOFF_S = policy.theta_429_backoff_s
        self.THETA_429_MAX_RETRIES_PER_REQUEST = policy.theta_429_max_retries
        self.THETA_RETRY_AFTER_CAP_S = policy.theta_retry_after_cap_s
        self.THETA_TRANSIENT_RETRY_DELAYS_S = policy.theta_transient_delays_s
        self.THETA_MIN_REQUEST_INTERVAL_S = policy.theta_min_request_interval_s
        self.THETA_RECOVERY_REQUEST_INTERVAL_S = policy.theta_recovery_request_interval_s
        self.THETA_RECOVERY_SUCCESS_REQUESTS = policy.theta_recovery_success_requests
        self.CONVERT_POLL_ATTEMPTS = policy.convert_poll_attempts
        self.CONVERT_POLL_DELAYS_S = policy.convert_poll_delays_s
        self.DIRECT_AUDIO_RETRY_DELAYS_S = policy.direct_audio_retry_delays_s

        downloader = downloader.strip().lower()
        if downloader not in {"auto", "aria2", "requests"}:
            raise ValueError("downloader must be: auto, aria2, or requests")
        self.downloader = downloader
        self.aria2_connections = max(1, min(int(aria2_connections), 16))
        self._aria2: Aria2RPCDownloader | None = None

        # Theta rate-limit state is shared by every candidate handled by this
        # client instance. This is the actual circuit breaker.
        self._theta_cooldown_until = 0.0
        self._theta_429_streak = 0
        self._theta_last_request_at = 0.0
        self._theta_recovery_requests_remaining = 0
        self._suppress_request_error_logging = False

    # ------------------------------------------------------------------
    # Internal HTTP helpers
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        stream: bool = False,
        timeout: float | None = None,
        log_errors: bool = True,
    ) -> requests.Response:
        try:
            response = self.session.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                allow_redirects=True,
                timeout=timeout or self.timeout,
                verify=self.verify_ssl,
                stream=stream,
            )
            response.raise_for_status()
            return response
        except requests.RequestException:
            suppress = bool(getattr(self, "_suppress_request_error_logging", False))
            if log_errors and not suppress:
                self.logger.exception("Request failed: %s %s", method, url)
            raise

    def _get_json(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self._request(
            "GET",
            url,
            headers=headers,
            params=params,
        )

        try:
            payload = response.json()
        except ValueError as exc:
            raise ResolveError(
                f"Expected JSON from {url}, but the server returned invalid JSON."
            ) from exc

        if not isinstance(payload, dict):
            raise ResolveError(f"Expected a JSON object from {url}, got {type(payload).__name__}.")

        return payload

    def _retry_after_seconds(self, exc: requests.HTTPError) -> float | None:
        response = getattr(exc, "response", None)
        if response is None:
            return None

        raw = response.headers.get("Retry-After")
        if raw is None:
            return None

        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None

        return max(0.0, min(value, float(self.THETA_RETRY_AFTER_CAP_S)))

    def _theta_current_interval_s(self) -> float:
        if self._theta_recovery_requests_remaining > 0:
            return max(
                self.THETA_MIN_REQUEST_INTERVAL_S,
                self.THETA_RECOVERY_REQUEST_INTERVAL_S,
            )
        return self.THETA_MIN_REQUEST_INTERVAL_S

    def _theta_wait_before_request(self) -> None:
        """
        Apply both the global 429 circuit breaker and normal request pacing.
        """
        now = time.monotonic()

        cooldown_remaining = self._theta_cooldown_until - now
        if cooldown_remaining > 0:
            self.logger.warning(
                "Theta rate limit cooldown: %.0fs remaining.",
                cooldown_remaining,
            )
            time.sleep(cooldown_remaining)
            now = time.monotonic()

        interval = self._theta_current_interval_s()
        if self._theta_last_request_at > 0 and interval > 0:
            spacing_remaining = self._theta_last_request_at + interval - now
            if spacing_remaining > 0:
                time.sleep(spacing_remaining)

    def _theta_mark_request_started(self) -> None:
        self._theta_last_request_at = time.monotonic()

    def _theta_mark_success(self) -> None:
        """
        A successful Theta API response closes the breaker.

        Recovery pacing intentionally remains for a number of successful API
        requests after a 429, then automatically returns to normal speed.
        """
        self._theta_cooldown_until = 0.0

        if self._theta_recovery_requests_remaining > 0:
            self._theta_recovery_requests_remaining -= 1
            if self._theta_recovery_requests_remaining <= 0:
                self._theta_429_streak = 0
        else:
            self._theta_429_streak = 0

    def _theta_open_rate_limit_breaker(
        self,
        exc: requests.HTTPError,
    ) -> float:
        """
        Escalate a client-global cooldown after HTTP 429.

        Backoff sequence:
            2s (one retry only)

        Retry-After, when supplied by Theta, always wins if it is longer.
        """
        self._theta_429_streak += 1

        index = min(
            self._theta_429_streak - 1,
            len(self.THETA_429_BACKOFF_S) - 1,
        )
        scheduled = float(self.THETA_429_BACKOFF_S[index])
        retry_after = self._retry_after_seconds(exc) or 0.0
        delay = max(scheduled, retry_after)

        self._theta_cooldown_until = max(
            self._theta_cooldown_until,
            time.monotonic() + delay,
        )
        self._theta_recovery_requests_remaining = max(
            self._theta_recovery_requests_remaining,
            int(self.THETA_RECOVERY_SUCCESS_REQUESTS),
        )

        self.logger.warning(
            "Theta HTTP 429 — global cooldown %.0fs (rate-limit strike %d).",
            delay,
            self._theta_429_streak,
        )
        return delay

    def _theta_get_json(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Theta-only resilient request layer.

        HTTP 429:
        - never emits a traceback while recovery is possible
        - opens a client-global circuit breaker
        - waits and retries the SAME URL / SAME candidate
        - uses one short 2 second cooldown
        - applies slower recovery pacing after service returns

        Other transient network failures:
        - HTTP 5xx
        - SSL EOF / TLS errors
        - connection resets
        - timeouts

        are retried with the shorter bounded transient schedule.
        """
        rate_limit_retries = 0
        transient_retries = 0
        transient_delays = self.THETA_TRANSIENT_RETRY_DELAYS_S

        while True:
            self._theta_wait_before_request()
            self._theta_mark_request_started()

            try:
                # Preserve the original _get_json call signature. Suppression
                # happens inside _request through an instance flag so existing
                # single-song flow and regression monkeypatches remain valid.
                self._suppress_request_error_logging = True
                try:
                    payload = self._get_json(
                        url,
                        headers=headers,
                        params=params,
                    )
                finally:
                    self._suppress_request_error_logging = False
            except requests.HTTPError as exc:
                response = getattr(exc, "response", None)
                status = getattr(response, "status_code", None)

                if status == 429:
                    rate_limit_retries += 1

                    if rate_limit_retries > self.THETA_429_MAX_RETRIES_PER_REQUEST:
                        # Bounded retry budget: do not hold a large library on
                        # one request. Recovery pacing remains active so the
                        # next candidate does not immediately hammer Theta.
                        self._theta_cooldown_until = 0.0
                        self._theta_recovery_requests_remaining = max(
                            self._theta_recovery_requests_remaining,
                            int(self.THETA_RECOVERY_SUCCESS_REQUESTS),
                        )
                        raise ResolveError(
                            "Theta remained rate-limited after "
                            f"{self.THETA_429_MAX_RETRIES_PER_REQUEST} "
                            "bounded retries.",
                            details={
                                "stage": "theta_rate_limit",
                                "url": url,
                                "retry_count": (self.THETA_429_MAX_RETRIES_PER_REQUEST),
                                "retry_profile": self.retry_profile,
                                "fast_fail": True,
                            },
                        ) from exc

                    self._theta_open_rate_limit_breaker(exc)
                    # Same URL, same candidate. The top of the loop waits for
                    # the global cooldown before making another request.
                    continue

                if (
                    isinstance(status, int)
                    and 500 <= status <= 599
                    and transient_retries < len(transient_delays)
                ):
                    delay = float(transient_delays[transient_retries])
                    transient_retries += 1
                    self.logger.warning(
                        "Theta HTTP %s — retrying in %.0fs (%d/%d).",
                        status,
                        delay,
                        transient_retries,
                        len(transient_delays),
                    )
                    time.sleep(delay)
                    continue

                # Non-transient HTTP errors, or an exhausted 5xx schedule, are
                # real failures. Log one concise line; the batch failure report
                # will retain full diagnostics.
                self.logger.error(
                    "Theta HTTP request failed: %s %s",
                    status,
                    url,
                )
                raise

            except (
                requests.exceptions.SSLError,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
            ) as exc:
                if transient_retries >= len(transient_delays):
                    self.logger.error(
                        "Theta network failure after retries: %s",
                        type(exc).__name__,
                    )
                    raise

                delay = float(transient_delays[transient_retries])
                transient_retries += 1
                self.logger.warning(
                    "Theta transient %s — retrying in %.0fs (%d/%d).",
                    type(exc).__name__,
                    delay,
                    transient_retries,
                    len(transient_delays),
                )
                time.sleep(delay)
                continue

            self._theta_mark_success()
            return payload

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    @staticmethod
    def _encode_keyword(keyword: str) -> str:
        encoded = quote(keyword, safe="").encode("utf-8")
        return base64.b64encode(encoded).decode("utf-8")

    @staticmethod
    def _interleave(
        youtube_results: list[dict[str, Any]],
        soundcloud_results: list[dict[str, Any]],
    ) -> Iterable[tuple[str, dict[str, Any]]]:
        for youtube_item, soundcloud_item in zip_longest(
            youtube_results,
            soundcloud_results,
        ):
            if isinstance(youtube_item, dict):
                yield "YouTube", youtube_item

            if isinstance(soundcloud_item, dict):
                yield "SoundCloud", soundcloud_item

    def search(
        self,
        keyword: str,
        *,
        limit: int = 10,
        source: str = "all",
    ) -> list[SearchResult]:
        """
        Search result metadata only.

        This intentionally does NOT convert/download every result. The original
        upstream implementation did that during search, which is expensive and
        wastes short-lived download URLs.
        """

        keyword = keyword.strip()
        if not keyword:
            raise ValueError("keyword cannot be empty")

        if limit < 1:
            raise ValueError("limit must be >= 1")

        source_normalized = source.strip().lower()
        if source_normalized not in {"all", "youtube", "soundcloud"}:
            raise ValueError("source must be: all, youtube, or soundcloud")

        params = {
            "y": "s",
            "q": self._encode_keyword(keyword),
            "_": str(int(time.time() * 1000)),
        }

        try:
            response = self._request(
                "GET",
                self.SEARCH_URL,
                params=params,
            )
            payload = response.json()
        except requests.RequestException as exc:
            raise SearchError(f"Search request failed: {exc}") from exc
        except ValueError as exc:
            raise SearchError("Search endpoint returned invalid JSON.") from exc

        if not isinstance(payload, dict):
            raise SearchError("Search endpoint returned an unexpected payload.")

        yt = payload.get("yt") or []
        sc = payload.get("sc") or []

        if not isinstance(yt, list):
            yt = []

        if not isinstance(sc, list):
            sc = []

        results: list[SearchResult] = []

        for root_source, raw in self._interleave(yt, sc):
            if source_normalized != "all" and root_source.lower() != source_normalized:
                continue

            identifier = raw.get("id")
            title = raw.get("title")

            if not identifier or not title:
                continue

            if root_source == "SoundCloud" and (
                not raw.get("id_base64") or not raw.get("title_base64")
            ):
                continue

            duration_s = parse_duration_seconds(raw)

            results.append(
                SearchResult(
                    identifier=str(identifier),
                    title=str(title),
                    root_source=root_source,
                    duration_s=duration_s,
                    duration=(seconds_to_hms(duration_s) if duration_s is not None else "--:--"),
                    raw_data=raw,
                )
            )

            if len(results) >= limit:
                break

        return results

    # ------------------------------------------------------------------
    # URL resolution
    # ------------------------------------------------------------------

    def _resolve_soundcloud(self, result: SearchResult) -> tuple[str, dict[str, Any]]:
        id_base64 = result.raw_data.get("id_base64")
        title_base64 = result.raw_data.get("title_base64")

        if not id_base64 or not title_base64:
            raise ResolveError("SoundCloud result is missing id_base64/title_base64.")

        url = f"{self.THETACLOUD_BASE_URL}/s/{id_base64}/{title_base64}/"

        return url, {"soundcloud": {"downloadURL": url}}

    def _resolve_youtube(self, result: SearchResult) -> tuple[str, dict[str, Any]]:
        trace: dict[str, Any] = {}

        # 1. Acquire temporary auth key.
        auth = self._theta_get_json(
            self.THETA_AUTH_URL,
            params={"_": str(int(time.time() * 1000))},
        )
        trace["auth"] = auth

        auth_key = auth.get("key")
        if not auth_key:
            raise ResolveError("Theta auth response did not contain a key.")

        # 2. Obtain the current conversion service URL.
        headers = copy.deepcopy(self.DEFAULT_HEADERS)
        headers["Authorization"] = f"Bearer {auth_key}"

        init = self._theta_get_json(
            self.THETA_INIT_URL,
            headers=headers,
            params={"_": str(int(time.time() * 1000))},
        )
        trace["init"] = init

        convert_url = init.get("convertURL")
        if not convert_url:
            raise ResolveError("Theta init response did not contain convertURL.")

        # 3. Request MP3 conversion.
        #
        # IMPORTANT:
        # The successful single-track flow is unchanged. We still call the
        # exact convertURL from Theta init with the same v=<id>&f=mp3 shape.
        # The only addition is bounded polling when Theta returns valid JSON
        # before redirectURL has become available.
        separator = "&" if "?" in str(convert_url) else "?"
        convert_attempts: list[dict[str, Any]] = []
        redirect_url: str | None = None
        direct_download_url: str | None = None

        for attempt in range(1, self.CONVERT_POLL_ATTEMPTS + 1):
            # Refresh only the cache-buster. Video id / format / endpoint are
            # identical to the original working implementation.
            convert_request_url = (
                f"{convert_url}{separator}"
                f"v={quote(result.identifier, safe='')}"
                f"&f=mp3"
                f"&_={int(time.time())}"
            )

            convert = self._theta_get_json(convert_request_url)
            trace["convert"] = convert

            convert_attempts.append(
                {
                    "attempt": attempt,
                    "response": convert,
                }
            )

            candidate_redirect = convert.get("redirectURL")
            candidate_download = convert.get("downloadURL")

            # Theta has two valid response shapes in the wild:
            #   A) redirectURL -> JSON redirect response -> downloadURL
            #   B) downloadURL directly in the convert response, with an empty
            #      redirectURL. The latter was previously misclassified as a
            #      failure even though Theta had already supplied the signed
            #      download endpoint.
            if candidate_redirect:
                redirect_url = str(candidate_redirect)
                break

            if candidate_download:
                direct_download_url = str(candidate_download)
                break

            if attempt < self.CONVERT_POLL_ATTEMPTS:
                delay_index = min(
                    attempt - 1,
                    len(self.CONVERT_POLL_DELAYS_S) - 1,
                )
                time.sleep(self.CONVERT_POLL_DELAYS_S[delay_index])

        trace["convert_attempts"] = convert_attempts

        # Some Theta conversion workers return a signed download endpoint
        # directly. It is a first-class success path, not an error/fallback.
        if direct_download_url:
            trace["download_resolution"] = "convert.downloadURL"
            return direct_download_url, trace

        if not redirect_url:
            raise ResolveError(
                (
                    "Theta convert did not provide redirectURL or downloadURL after "
                    f"{len(convert_attempts)} attempt(s)."
                ),
                details={
                    "stage": "convert",
                    "video_id": result.identifier,
                    "candidate_title": result.title,
                    "attempt_count": len(convert_attempts),
                    # Raw JSON responses are intentionally retained for the
                    # batch failure report. Do not include auth keys or the
                    # temporary convertURL itself.
                    "convert_responses": convert_attempts,
                },
            )

        # 4. Resolve short-lived final download URL (redirect response shape).
        redirect = self._theta_get_json(str(redirect_url))
        trace["redirect"] = redirect

        download_url = redirect.get("downloadURL")
        if not download_url:
            raise ResolveError("Theta redirect response did not contain downloadURL.")

        return str(download_url), trace

    def resolve_download_url(
        self,
        result: SearchResult,
    ) -> tuple[str, dict[str, Any]]:
        source = result.root_source.lower()

        if source == "youtube":
            return self._resolve_youtube(result)

        if source == "soundcloud":
            return self._resolve_soundcloud(result)

        raise ResolveError(f"Unsupported root source: {result.root_source}")

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def _download_final_url_requests(
        self,
        url: str,
        *,
        progress_callback: Callable[[int, int | None], None] | None,
        chunk_size: int,
    ) -> tuple[bytes, dict[str, object], str, str]:
        try:
            response = self._request(
                "GET",
                url,
                stream=True,
            )
        except requests.RequestException as exc:
            raise DownloadError(f"Could not download final audio URL: {exc}") from exc

        raw_total = response.headers.get("Content-Length")
        total_bytes: int | None = None
        if raw_total:
            try:
                parsed = int(raw_total)
                if parsed > 0:
                    total_bytes = parsed
            except (TypeError, ValueError):
                total_bytes = None

        downloaded = 0
        chunks: list[bytes] = []
        if progress_callback is not None:
            progress_callback(0, total_bytes)

        try:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if not chunk:
                    continue
                chunks.append(chunk)
                downloaded += len(chunk)
                if progress_callback is not None:
                    progress_callback(downloaded, total_bytes)
        except requests.RequestException as exc:
            raise DownloadError(f"Connection interrupted while downloading audio: {exc}") from exc
        finally:
            response.close()

        contents = b"".join(chunks)
        if not contents:
            raise DownloadError("The server returned an empty response body.")

        if progress_callback is not None:
            progress_callback(len(contents), total_bytes or len(contents))

        metadata: dict[str, object] = {
            "engine": "requests",
            "total_bytes": len(contents),
        }
        return (
            contents,
            metadata,
            response.headers.get("Content-Type", ""),
            response.url or url,
        )

    def _get_aria2(self) -> Aria2RPCDownloader:
        if self._aria2 is None:
            self._aria2 = Aria2RPCDownloader(
                connections=self.aria2_connections,
                timeout=self.timeout,
                verify_ssl=self.verify_ssl,
                logger=self.logger,
            )
        return self._aria2

    def _download_final_url(
        self,
        url: str,
        *,
        progress_callback: Callable[[int, int | None], None] | None,
        chunk_size: int,
    ) -> tuple[bytes, dict[str, object], str, str]:
        engine = getattr(self, "downloader", "requests")
        use_aria2 = engine in {"auto", "aria2"}

        if use_aria2:
            try:
                aria2 = self._get_aria2()
                contents, metadata = aria2.download(
                    url,
                    headers=self.DEFAULT_HEADERS,
                    cookies=self.session.cookies,
                    progress_callback=progress_callback,
                )
                # Theta explicitly converts YouTube to mp3. For the final CDN
                # response aria2 does not expose Content-Type through tellStatus,
                # so extension inference can safely fall back to URL/default mp3.
                return contents, metadata, "", url
            except (Aria2Unavailable, Aria2TransferError, requests.RequestException) as exc:
                if engine == "aria2":
                    raise DownloadError(f"aria2 backend failed: {exc}") from exc
                self.logger.warning(
                    "aria2 unavailable/failed; falling back to requests: %s",
                    exc,
                )

        return self._download_final_url_requests(
            url,
            progress_callback=progress_callback,
            chunk_size=chunk_size,
        )

    @staticmethod
    def _theta_worker_error(data: bytes) -> dict[str, object] | None:
        """
        Detect tiny JSON error payloads returned by Theta download workers.

        Example observed in real batches:
            {"progress":0,"error":6}

        error=6 is a terminal conversion failure for that candidate/worker;
        retrying the same signed URL repeatedly only wastes time.
        """
        if not data or len(data) > 4096:
            return None

        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None

        if not isinstance(payload, dict):
            return None

        raw_error = payload.get("error")
        if raw_error in (None, 0, "0", ""):
            return None

        try:
            error_code: object = int(raw_error)
        except (TypeError, ValueError):
            error_code = raw_error

        return {
            "error": error_code,
            "progress": payload.get("progress"),
            "payload": payload,
        }

    def _raise_if_terminal_theta_worker_error(
        self,
        result: SearchResult,
        contents: bytes,
        attempts: list[dict[str, object]],
    ) -> None:
        worker_error = self._theta_worker_error(contents)
        if not worker_error:
            return

        # Code 6 is the recurring hard conversion failure observed in the
        # user's real Theta worker responses. Move to the next candidate
        # immediately instead of retrying the same URL three more times.
        if worker_error.get("error") == 6:
            raise DownloadError(
                "Theta worker rejected this conversion (error=6).",
                details={
                    "stage": "theta_worker_download",
                    "video_id": result.identifier,
                    "candidate_title": result.title,
                    "theta_error": worker_error,
                    "audio_validation_attempts": attempts,
                },
            )

    @staticmethod
    def _payload_preview(data: bytes, limit: int = 160) -> str:
        """Short printable preview for diagnosing non-audio HTTP payloads."""
        if not data:
            return ""
        sample = data[:limit]
        text = sample.decode("utf-8", errors="replace")
        return "".join(ch if ch.isprintable() else "." for ch in text)

    def _download_verified_audio(
        self,
        url: str,
        *,
        progress_callback: Callable[[int, int | None], None] | None,
        chunk_size: int,
    ) -> tuple[bytes, dict[str, object], str, str, float | None]:
        contents, transfer_meta, content_type, effective_url = self._download_final_url(
            url,
            progress_callback=progress_callback,
            chunk_size=chunk_size,
        )
        duration_s = get_audio_duration(contents)
        return contents, transfer_meta, content_type, effective_url, duration_s

    def download(
        self,
        result: SearchResult,
        *,
        progress_callback: Callable[[int, int | None], None] | None = None,
        chunk_size: int = 128 * 1024,
    ) -> SongInfo:
        """
        Resolve and immediately download the selected result.

        IMPORTANT: URL resolution is exactly the same as the original working
        single-song implementation. Streaming begins only AFTER MP3Juice/Theta
        has already returned the final short-lived download URL.

        progress_callback receives:
            (downloaded_bytes, total_bytes_or_none)
        """

        if chunk_size < 1024:
            raise ValueError("chunk_size must be >= 1024 bytes")

        download_url, resolution_trace = self.resolve_download_url(result)

        (
            contents,
            transfer_meta,
            content_type,
            effective_url,
            duration_s,
        ) = self._download_verified_audio(
            download_url,
            progress_callback=progress_callback,
            chunk_size=chunk_size,
        )

        audio_validation_attempts: list[dict[str, object]] = [
            {
                "phase": "initial",
                "url_resolution": resolution_trace.get("download_resolution", "redirect"),
                "bytes": len(contents),
                "content_type": content_type,
                "duration_s": duration_s,
                "payload_preview": (
                    "" if duration_s is not None else self._payload_preview(contents)
                ),
            }
        ]

        if (
            duration_s is None
            and result.root_source.casefold() == "youtube"
            and resolution_trace.get("download_resolution") == "convert.downloadURL"
        ):
            self._raise_if_terminal_theta_worker_error(
                result,
                contents,
                audio_validation_attempts,
            )

        # Theta sometimes exposes convert.downloadURL before the generated MP3
        # is actually ready. aria2 correctly downloads the HTTP payload, but
        # that payload may still be JSON/HTML/placeholder content. Retry the
        # same signed endpoint only for this direct-convert response shape.
        if (
            duration_s is None
            and result.root_source.casefold() == "youtube"
            and resolution_trace.get("download_resolution") == "convert.downloadURL"
        ):
            for retry_no, delay in enumerate(
                self.DIRECT_AUDIO_RETRY_DELAYS_S,
                start=1,
            ):
                time.sleep(delay)
                (
                    contents,
                    transfer_meta,
                    content_type,
                    effective_url,
                    duration_s,
                ) = self._download_verified_audio(
                    download_url,
                    progress_callback=progress_callback,
                    chunk_size=chunk_size,
                )
                audio_validation_attempts.append(
                    {
                        "phase": f"same-url-retry-{retry_no}",
                        "bytes": len(contents),
                        "content_type": content_type,
                        "duration_s": duration_s,
                        "payload_preview": (
                            "" if duration_s is not None else self._payload_preview(contents)
                        ),
                    }
                )
                if duration_s is None:
                    self._raise_if_terminal_theta_worker_error(
                        result,
                        contents,
                        audio_validation_attempts,
                    )
                if duration_s is not None:
                    break

            # If the signed endpoint never became audio, ask Theta for one fresh
            # conversion transaction. This can move the request to another worker
            # or return the traditional redirectURL path.
            if duration_s is None:
                fresh_url, fresh_trace = self.resolve_download_url(result)
                (
                    contents,
                    transfer_meta,
                    content_type,
                    effective_url,
                    duration_s,
                ) = self._download_verified_audio(
                    fresh_url,
                    progress_callback=progress_callback,
                    chunk_size=chunk_size,
                )
                audio_validation_attempts.append(
                    {
                        "phase": "fresh-theta-resolve",
                        "url_resolution": fresh_trace.get(
                            "download_resolution",
                            "redirect",
                        ),
                        "bytes": len(contents),
                        "content_type": content_type,
                        "duration_s": duration_s,
                        "payload_preview": (
                            "" if duration_s is not None else self._payload_preview(contents)
                        ),
                    }
                )
                if (
                    duration_s is None
                    and fresh_trace.get("download_resolution") == "convert.downloadURL"
                ):
                    self._raise_if_terminal_theta_worker_error(
                        result,
                        contents,
                        audio_validation_attempts,
                    )
                # Keep the trace corresponding to the bytes we actually return.
                resolution_trace = fresh_trace
                download_url = fresh_url

        ext = guess_extension(
            effective_url,
            content_type,
            default="mp3",
        )

        return SongInfo(
            raw_data={
                "search": result.raw_data,
                "download": resolution_trace,
                "lyric": {},
                "http": {
                    "final_url": effective_url,
                    "content_type": content_type,
                    "content_length": transfer_meta.get("total_bytes"),
                    "download_engine": transfer_meta.get("engine"),
                    "transfer": transfer_meta,
                    "audio_validation_attempts": audio_validation_attempts,
                },
            },
            source=self.source,
            root_source=result.root_source,
            song_name=result.title,
            singers="NULL",
            album="NULL",
            ext=ext,
            file_size_bytes=len(contents),
            file_size=bytes_to_mb(len(contents)),
            identifier=result.identifier,
            duration_s=duration_s,
            duration=seconds_to_hms(duration_s),
            lyric="NULL",
            cover_url=None,
            download_url=effective_url,
            downloaded_contents=contents,
        )

    def search_and_download(
        self,
        keyword: str,
        *,
        index: int = 1,
        limit: int = 10,
        source: str = "all",
    ) -> SongInfo:
        results = self.search(keyword, limit=limit, source=source)

        if not results:
            raise SearchError("No usable search results were returned.")

        if index < 1 or index > len(results):
            raise IndexError(f"index must be between 1 and {len(results)}, got {index}")

        return self.download(results[index - 1])

    def close(self) -> None:
        aria2 = getattr(self, "_aria2", None)
        if aria2 is not None:
            aria2.close()
            self._aria2 = None
        self.session.close()

    def __enter__(self) -> MP3JuiceMusicClient:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
