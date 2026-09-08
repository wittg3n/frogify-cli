from __future__ import annotations

import hashlib
import json
import logging
import math
import sqlite3
import subprocess
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from frogify.config import ConfigManager
from frogify.core.exceptions import (
    ConfigurationError,
    DownloadError,
    FrogifyError,
    NoSafeCandidateError,
    SearchError,
    ValidationError,
)
from frogify.core.models import BatchResult, DownloadResult, FreeTextRequest, RankedCandidate
from frogify.logging import redact
from frogify.matching import rank_free_text
from frogify.storage import Database
from mp3juice.client import MP3JuiceMusicClient
from mp3juice.exceptions import MP3JuiceError
from mp3juice.models import SearchResult
from mp3juice.spotify_batch import (
    BatchCallbacks,
    SpotifyTrack,
    SpotifyTrackDownloader,
    probe_duration,
    read_spotify_csv,
)

ClientFactory = Callable[..., MP3JuiceMusicClient]


class FrogifyService:
    """Own request orchestration and SQLite state, independently of the CLI."""

    def __init__(
        self,
        config: ConfigManager | None = None,
        database: Database | None = None,
        *,
        client_factory: ClientFactory = MP3JuiceMusicClient,
        legacy_paths: Iterable[Path] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.config = config or ConfigManager()
        self.database = database or Database(self.config.database_path)
        self.client_factory = client_factory
        self.logger = logger or logging.getLogger("frogify")
        try:
            self.config.ensure_directories()
            self.database.initialize()
            self.database.migrate_legacy(
                legacy_paths if legacy_paths is not None else [Path.cwd(), Path.cwd() / "spotify"]
            )
        except (sqlite3.Error, RuntimeError) as exc:
            raise ConfigurationError(f"Cannot initialize download state: {exc}") from exc

    def _client(self) -> MP3JuiceMusicClient:
        values = self.config.load()
        return self.client_factory(
            timeout=values["network"]["timeout"],
            downloader=values["download"]["engine"],
            aria2_connections=values["download"]["aria2_connections"],
            retry_profile=values["network"]["retry_profile"],
            logger=self.logger,
        )

    def search(
        self, request: FreeTextRequest, *, limit: int = 10, source: str = "all"
    ) -> list[RankedCandidate]:
        client = self._client()
        try:
            return rank_free_text(
                request.query, client.search(request.query, limit=limit, source=source)
            )
        except MP3JuiceError as exc:
            raise SearchError(str(exc)) from exc
        finally:
            client.close()

    def download(
        self,
        request: FreeTextRequest,
        *,
        output: Path | None = None,
        candidate_attempts: int | None = None,
        selected: RankedCandidate | None = None,
        limit: int = 10,
        source: str = "all",
        progress_callback: Callable[[int, int | None], None] | None = None,
        status_callback: Callable[[str], None] | None = None,
    ) -> DownloadResult:
        values = self.config.load()
        attempts = (
            candidate_attempts
            if candidate_attempts is not None
            else values["matching"]["candidate_attempts"]
        )
        if attempts < 1 or not request.query.strip():
            raise ValueError("A query and at least one candidate attempt are required")
        directory = self.config.output_directory(output)
        identity = "query:" + " ".join(request.query.casefold().split())
        payload: dict[str, Any] = {
            "type": "free",
            "query": request.query,
            "output_dir": str(directory),
            "source": source,
            "candidate_attempts": attempts,
        }
        if selected is not None:
            payload["selected"] = asdict(selected.result)
        client = self._client()
        try:
            if selected is not None:
                candidates = [selected]
            else:
                if status_callback:
                    status_callback("searching")
                ranked = rank_free_text(
                    request.query, client.search(request.query, limit=limit, source=source)
                )
                candidates = [item for item in ranked if item.score >= 76 and not item.reasons][
                    :attempts
                ]
            if not candidates:
                raise NoSafeCandidateError(
                    "No safe match found. Use search or --pick to inspect results."
                )
            failures: list[str] = []
            for candidate in candidates:
                try:
                    if status_callback:
                        status_callback(f"downloading {candidate.result.title}")
                    song = client.download(candidate.result, progress_callback=progress_callback)
                    self._validate_song(song.downloaded_contents, song.duration_s)
                    path = song.save(directory).resolve()
                    transfer = str(
                        (song.raw_data.get("http") or {}).get("download_engine") or "requests"
                    )
                except (MP3JuiceError, OSError, ValidationError) as exc:
                    failures.append(f"{candidate.result.title}: {exc}")
                    continue
                self.database.record_success(
                    identity,
                    query=request.query,
                    title=candidate.result.title,
                    request=payload,
                    path=str(path),
                )
                return DownloadResult(path, candidate, transfer)
            raise DownloadError(" | ".join(failures))
        except (FrogifyError, MP3JuiceError, OSError) as exc:
            self.database.record_failure(
                identity,
                query=request.query,
                request=payload,
                error_type=type(exc).__name__,
                error_message=redact(str(exc)),
            )
            if isinstance(exc, FrogifyError):
                raise
            raise DownloadError(str(exc)) from exc
        finally:
            client.close()

    def _validate_song(self, data: bytes, duration: float | None) -> None:
        if duration is not None and math.isfinite(duration) and duration > 0 and data:
            return
        with tempfile.TemporaryDirectory(dir=self.config.temp_dir) as work:
            path = Path(work) / "audio"
            path.write_bytes(data)
            try:
                measured = probe_duration(path)
            except subprocess.SubprocessError as exc:
                raise ValidationError("Audio validation timed out or failed") from exc
            if measured is None:
                raise ValidationError("downloaded payload is not valid audio")

    def batch(
        self,
        csv_path: Path,
        *,
        output: Path | None = None,
        callbacks: BatchCallbacks | None = None,
        force: bool = False,
        max_tracks: int | None = None,
    ) -> BatchResult:
        tracks, invalid = read_spotify_csv(csv_path)
        unique: dict[str, SpotifyTrack] = {}
        for track in tracks:
            unique.setdefault(track.uri, track)
        selected = list(unique.values())
        if max_tracks is not None:
            if max_tracks < 1:
                raise ValueError("max_tracks must be at least 1")
            selected = selected[:max_tracks]
        source_id = hashlib.sha256(str(csv_path.resolve()).encode()).hexdigest()[:16]
        for row in invalid:
            self.database.record_failure(
                f"invalid-row:{source_id}:{row['row_number']}",
                title=row.get("track_name", ""),
                artists=row.get("artists", ""),
                request={"type": "invalid", "source": str(csv_path.resolve())},
                error_type="InvalidCSVRow",
                error_message=row["reason"],
                retryable=False,
            )
        stats = self._run_tracks(selected, output=output, callbacks=callbacks, force=force)
        return BatchResult(
            stats.total + len(invalid), stats.downloaded, stats.skipped, stats.failed + len(invalid)
        )

    def _run_tracks(
        self,
        tracks: list[SpotifyTrack],
        *,
        output: Path | None,
        callbacks: BatchCallbacks | None = None,
        force: bool = False,
    ) -> BatchResult:
        output_dir = self.config.output_directory(output)
        self.database.migrate_legacy([output_dir])
        values = self.config.load()
        callbacks = callbacks or BatchCallbacks()
        downloaded = skipped = failed = 0
        client = self._client()
        try:
            runner = SpotifyTrackDownloader(
                client,
                output_dir=output_dir,
                metadata_enabled=values["metadata"]["enabled"],
                duration_tolerance_s=values["matching"]["duration_tolerance"],
                candidate_attempts=values["matching"]["candidate_attempts"],
                callbacks=callbacks,
            )
            for index, track in enumerate(tracks, 1):
                if callbacks.on_track_start:
                    callbacks.on_track_start(index, len(tracks), track)
                previous = self.database.success_path(track.uri)
                if not force and previous is not None:
                    skipped += 1
                    if callbacks.on_status:
                        callbacks.on_status("already downloaded — skipped")
                    continue
                payload = self._track_payload(track, output_dir)
                try:
                    path, candidate = runner.download_track(
                        track, previous_path=previous if force else None
                    )
                except (MP3JuiceError, OSError, RuntimeError, ValueError) as exc:
                    details = getattr(exc, "details", {})
                    payload["diagnostics"] = json.loads(
                        redact(json.dumps(details, ensure_ascii=False))
                    )
                    reason = redact(str(exc))
                    self.database.record_failure(
                        track.uri,
                        track_uri=track.uri,
                        title=track.track_name,
                        artists=track.artists_display,
                        request=payload,
                        error_type=type(exc).__name__,
                        error_message=reason,
                    )
                    failed += 1
                    if callbacks.on_track_failure:
                        callbacks.on_track_failure(track, reason)
                    continue
                # Commit before notifying observers, including UI callbacks that may interrupt.
                self.database.record_success(
                    track.uri,
                    track_uri=track.uri,
                    title=track.track_name,
                    artists=track.artists_display,
                    request=payload,
                    path=str(path),
                )
                downloaded += 1
                if callbacks.on_track_success:
                    callbacks.on_track_success(track, path, candidate)
        finally:
            client.close()
        return BatchResult(len(tracks), downloaded, skipped, failed)

    def retry(
        self, *, output: Path | None = None, callbacks: BatchCallbacks | None = None
    ) -> BatchResult:
        downloaded = skipped = failed = total = 0
        groups: dict[Path, list[SpotifyTrack]] = {}
        for row in self.database.failures():
            total += 1
            payload: dict[str, Any] = {}
            try:
                saved = json.loads(row["request_json"])
                if not isinstance(saved, dict):
                    raise ValueError("Saved request must be an object; import the CSV again")
                payload = saved
                destination = (
                    output
                    if output is not None
                    else (Path(payload["output_dir"]) if payload.get("output_dir") else None)
                )
                if payload.get("type") == "free":
                    selected = None
                    if payload.get("selected"):
                        result = SearchResult(**payload["selected"])
                        selected = rank_free_text(payload["query"], [result])[0]
                    self.download(
                        FreeTextRequest(payload["query"]),
                        output=destination,
                        selected=selected,
                        source=payload.get("source", "all"),
                        candidate_attempts=payload.get("candidate_attempts"),
                        progress_callback=callbacks.on_download_progress if callbacks else None,
                        status_callback=callbacks.on_status if callbacks else None,
                    )
                    downloaded += 1
                elif payload.get("type") == "structured":
                    track = self._payload_track(payload)
                    if (
                        not track.uri
                        or not track.track_name
                        or not track.artists
                        or not math.isfinite(track.duration_s)
                        or track.duration_s <= 0
                    ):
                        raise ValueError("Saved track is incomplete; import the original CSV again")
                    groups.setdefault(self.config.output_directory(destination), []).append(track)
                else:
                    raise ValueError(
                        "Saved request cannot be reconstructed; import the original CSV again"
                    )
            except (FrogifyError, OSError) as exc:
                failed += 1
                if callbacks and callbacks.on_status:
                    callbacks.on_status(str(exc))
            except (ValueError, TypeError, KeyError) as exc:
                failed += 1
                self.database.record_failure(
                    row["identity"],
                    title=row["title"],
                    artists=row["artists"],
                    request=payload,
                    error_type="InvalidSavedRequest",
                    error_message=str(exc),
                    retryable=False,
                )
                if callbacks and callbacks.on_status:
                    callbacks.on_status(str(exc))
        for destination, tracks in groups.items():
            stats = self._run_tracks(tracks, output=destination, callbacks=callbacks)
            downloaded += stats.downloaded
            skipped += stats.skipped
            failed += stats.failed
        return BatchResult(total, downloaded, skipped, failed)

    @staticmethod
    def _track_payload(track: SpotifyTrack, output_dir: Path) -> dict[str, Any]:
        return {
            "type": "structured",
            "uri": track.uri,
            "title": track.track_name,
            "artists": track.artists_display,
            "album": track.album_name,
            "release_date": track.release_date,
            "duration_s": track.duration_s,
            "popularity": track.popularity,
            "explicit": track.explicit,
            "genres": track.genres,
            "record_label": track.record_label,
            "output_dir": str(output_dir),
        }

    @staticmethod
    def _payload_track(payload: dict[str, Any]) -> SpotifyTrack:
        artists = str(payload.get("artists") or "")
        return SpotifyTrack(
            row_number=0,
            uri=str(payload.get("uri") or ""),
            track_name=str(payload.get("title") or ""),
            album_name=str(payload.get("album") or ""),
            artists_display=artists,
            artists=[part.strip() for part in artists.split(";") if part.strip()],
            release_date=str(payload.get("release_date") or ""),
            duration_s=float(payload.get("duration_s") or 0),
            popularity=str(payload.get("popularity") or ""),
            explicit=str(payload.get("explicit") or ""),
            genres=str(payload.get("genres") or ""),
            record_label=str(payload.get("record_label") or ""),
        )
