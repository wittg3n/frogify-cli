from __future__ import annotations

import csv
import json
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _identity(track_uri: str, title: str, artists: str = "") -> str:
    if track_uri.strip():
        return track_uri.strip()
    normalized = " ".join(f"{title} {artists}".casefold().split())
    return f"legacy:{normalized}"


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS downloads (
                    identity TEXT PRIMARY KEY,
                    status TEXT NOT NULL CHECK (status IN ('success', 'failure')),
                    query TEXT NOT NULL DEFAULT '',
                    track_uri TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL DEFAULT '',
                    artists TEXT NOT NULL DEFAULT '',
                    request_json TEXT NOT NULL DEFAULT '{}',
                    path TEXT NOT NULL DEFAULT '',
                    error_type TEXT NOT NULL DEFAULT '',
                    error_message TEXT NOT NULL DEFAULT '',
                    retryable INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS legacy_imports (
                    source_path TEXT PRIMARY KEY,
                    imported_at TEXT NOT NULL
                );
                """
            )
            row = db.execute("SELECT version FROM schema_meta LIMIT 1").fetchone()
            if row is None:
                db.execute("INSERT INTO schema_meta(version) VALUES (?)", (SCHEMA_VERSION,))
            elif int(row[0]) != SCHEMA_VERSION:
                raise RuntimeError(f"Unsupported Frogify database schema: {row[0]}")

    def is_success(self, identity: str) -> bool:
        with self.connect() as db:
            row = db.execute(
                "SELECT status FROM downloads WHERE identity = ?", (identity,)
            ).fetchone()
        return bool(row and row[0] == "success")

    def success_path(self, identity: str) -> Path | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT path FROM downloads WHERE identity = ? AND status = 'success'",
                (identity,),
            ).fetchone()
        path = Path(row[0]) if row and row[0] else None
        return path if path is not None and path.is_file() else None

    def record_success(
        self,
        identity: str,
        *,
        query: str = "",
        track_uri: str = "",
        title: str = "",
        artists: str = "",
        request: dict[str, Any] | None = None,
        path: str = "",
    ) -> None:
        self._upsert(
            identity,
            status="success",
            query=query,
            track_uri=track_uri,
            title=title,
            artists=artists,
            request=request,
            path=path,
            error_type="",
            error_message="",
            retryable=False,
        )

    def record_failure(
        self,
        identity: str,
        *,
        query: str = "",
        track_uri: str = "",
        title: str = "",
        artists: str = "",
        request: dict[str, Any] | None = None,
        error_type: str,
        error_message: str,
        retryable: bool = True,
    ) -> None:
        if self.success_path(identity):
            return
        self._upsert(
            identity,
            status="failure",
            query=query,
            track_uri=track_uri,
            title=title,
            artists=artists,
            request=request,
            path="",
            error_type=error_type,
            error_message=error_message,
            retryable=retryable,
        )

    def _upsert(
        self,
        identity: str,
        *,
        status: str,
        query: str,
        track_uri: str,
        title: str,
        artists: str,
        request: dict[str, Any] | None,
        path: str,
        error_type: str,
        error_message: str,
        retryable: bool,
        overwrite: bool = True,
    ) -> None:
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO downloads(
                    identity, status, query, track_uri, title, artists,
                    request_json, path, error_type, error_message, retryable, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(identity) DO UPDATE SET
                    status=excluded.status, query=excluded.query,
                    track_uri=excluded.track_uri, title=excluded.title,
                    artists=excluded.artists, request_json=excluded.request_json,
                    path=excluded.path, error_type=excluded.error_type,
                    error_message=excluded.error_message, retryable=excluded.retryable,
                    updated_at=excluded.updated_at
                """
                if overwrite
                else """
                INSERT OR IGNORE INTO downloads(
                    identity, status, query, track_uri, title, artists,
                    request_json, path, error_type, error_message, retryable, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    identity,
                    status,
                    query,
                    track_uri,
                    title,
                    artists,
                    json.dumps(request or {}, ensure_ascii=False),
                    path,
                    error_type,
                    error_message,
                    int(retryable),
                    _now(),
                ),
            )

    def failures(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM downloads WHERE status='failure' AND retryable=1 ORDER BY updated_at"
            ).fetchall()
        return [dict(row) for row in rows]

    def migrate_legacy(self, locations: Iterable[Path]) -> int:
        imported = 0
        files: list[tuple[Path, str]] = []
        for location in locations:
            if location.is_file():
                kind = "success" if "downloaded" in location.name.casefold() else "failure"
                files.append((location, kind))
            else:
                files.extend(
                    (
                        (location / "downloaded_tracks.csv", "success"),
                        (location / "failed_tracks.csv", "failure"),
                    )
                )
        for path, kind in files:
            if not path.is_file():
                continue
            with self.connect() as db:
                already_imported = db.execute(
                    "SELECT 1 FROM legacy_imports WHERE source_path = ?",
                    (str(path.resolve()),),
                ).fetchone()
            if already_imported:
                continue
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    uri = str(row.get("track_uri") or row.get("Track URI") or "").strip()
                    title = str(row.get("track_name") or row.get("Track Name") or "").strip()
                    artists = str(row.get("artists") or row.get("Artist Name(s)") or "").strip()
                    identity = _identity(uri, title, artists)
                    request = {
                        "type": "structured",
                        "uri": uri,
                        "title": title,
                        "artists": artists,
                        "album": str(row.get("album") or ""),
                        "duration_s": str(row.get("expected_duration_s") or "0"),
                        "output_dir": str(path.parent.resolve()),
                    }
                    recorded_path = Path(str(row.get("file") or ""))
                    if row.get("file") and not recorded_path.is_absolute():
                        recorded_path = path.parent / recorded_path
                    # Current retry/success state wins, including concurrent writes.
                    self._upsert(
                        identity,
                        status=kind,
                        query="",
                        track_uri=uri,
                        title=title,
                        artists=artists,
                        request=request,
                        path=str(recorded_path.resolve())
                        if kind == "success" and row.get("file")
                        else "",
                        error_type="LegacyFailure" if kind == "failure" else "",
                        error_message=str(row.get("reason") or "legacy failure")
                        if kind == "failure"
                        else "",
                        retryable=kind == "failure",
                        overwrite=False,
                    )
                    imported += 1
            with self.connect() as db:
                db.execute(
                    "INSERT OR REPLACE INTO legacy_imports(source_path, imported_at) VALUES (?, ?)",
                    (str(path.resolve()), _now()),
                )
        return imported
