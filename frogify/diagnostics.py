from __future__ import annotations

import importlib.util
import os
import shutil
import sqlite3
from dataclasses import dataclass

import requests

from frogify.config import ConfigManager
from frogify.storage import Database
from mp3juice.client import MP3JuiceMusicClient


@dataclass(frozen=True, slots=True)
class Diagnostic:
    name: str
    ok: bool
    detail: str
    required: bool = True


def run_doctor(
    config: ConfigManager,
    database: Database,
    *,
    check_network: bool = True,
) -> list[Diagnostic]:
    checks: list[Diagnostic] = []
    values = None
    try:
        config.ensure_directories()
        values = config.load()
        checks.append(Diagnostic("Config", True, str(config.path)))
    except Exception as exc:
        checks.append(Diagnostic("Config", False, str(exc)))
    try:
        database.initialize()
        with database.connect() as db:
            db.execute("SELECT 1").fetchone()
        checks.append(Diagnostic("Database", True, str(database.path)))
    except (OSError, sqlite3.Error, RuntimeError) as exc:
        checks.append(Diagnostic("Database", False, str(exc)))
    try:
        output = config.output_directory()
        parent = output
        while not parent.exists() and parent != parent.parent:
            parent = parent.parent
        writable = parent.is_dir() and os.access(parent, os.W_OK)
        checks.append(Diagnostic("Download directory", writable, str(output)))
    except Exception as exc:
        checks.append(Diagnostic("Download directory", False, str(exc)))
    for executable in ("aria2c", "ffmpeg", "ffprobe"):
        found = shutil.which(executable)
        required = executable == "ffmpeg" and bool(values and values["metadata"]["enabled"])
        if executable == "aria2c":
            required = bool(values and values["download"]["engine"] == "aria2")
        checks.append(Diagnostic(executable, bool(found), found or "not found", required))
    for module in ("requests", "mutagen"):
        checks.append(Diagnostic(module, importlib.util.find_spec(module) is not None, "installed"))
    if check_network:
        with requests.Session() as session:
            session.headers.update(MP3JuiceMusicClient.DEFAULT_HEADERS)
            for name, url in (
                ("MP3Juice", MP3JuiceMusicClient.SEARCH_URL),
                ("Theta", MP3JuiceMusicClient.THETA_AUTH_URL),
            ):
                try:
                    response = session.get(url, timeout=5)
                    checks.append(
                        Diagnostic(
                            name,
                            200 <= response.status_code < 400,
                            f"HTTP {response.status_code}; reachability only",
                        )
                    )
                    response.close()
                except requests.RequestException as exc:
                    checks.append(Diagnostic(name, False, type(exc).__name__))
    return checks
