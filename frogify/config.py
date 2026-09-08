from __future__ import annotations

import copy
import json
import math
import os
import tempfile
import tomllib
from pathlib import Path
from typing import Any

from platformdirs import PlatformDirs, user_downloads_path

from frogify.core.exceptions import ConfigurationError

DEFAULTS: dict[str, dict[str, Any]] = {
    "download": {"engine": "auto", "aria2_connections": 8, "directory": ""},
    "matching": {"duration_tolerance": 10.0, "candidate_attempts": 3},
    "network": {"retry_profile": "balanced", "timeout": 30.0},
    "metadata": {"enabled": True},
}


class ConfigManager:
    def __init__(
        self,
        config_path: Path | None = None,
        data_dir: Path | None = None,
    ) -> None:
        dirs = PlatformDirs("Frogify", appauthor=False, roaming=True)
        self.path = config_path or Path(dirs.user_config_path) / "config.toml"
        local_dirs = PlatformDirs("Frogify", appauthor=False, roaming=False)
        self.data_dir = data_dir or Path(local_dirs.user_data_path)
        self.log_dir = self.data_dir / "logs"
        self.temp_dir = self.data_dir / "temp"
        self.database_path = self.data_dir / "frogify.db"

    def ensure_directories(self) -> None:
        for path in (self.path.parent, self.data_dir, self.log_dir, self.temp_dir):
            path.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, dict[str, Any]]:
        config = copy.deepcopy(DEFAULTS)
        if not self.path.exists():
            return config
        try:
            with self.path.open("rb") as handle:
                loaded = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ConfigurationError(f"Cannot read {self.path}: {exc}") from exc
        for section, values in loaded.items():
            if section not in DEFAULTS or not isinstance(values, dict):
                raise ConfigurationError(f"Unknown or invalid configuration section: {section}")
            if section == "download":
                values.pop("overwrite", None)  # Retired setting never affected downloads.
            config[section].update(values)
        self._validate(config)
        return config

    def get(self, key: str) -> Any:
        section, name = self._split_key(key)
        values = self.load()
        if section not in values or name not in values[section]:
            raise ConfigurationError(f"Unknown configuration key: {key}")
        return values[section][name]

    def set(self, key: str, raw_value: str) -> Any:
        section, name = self._split_key(key)
        values = self.load()
        if section not in values or name not in values[section]:
            raise ConfigurationError(f"Unknown configuration key: {key}")
        value = self._coerce(raw_value, DEFAULTS[section][name])
        values[section][name] = value
        self._validate(values)
        self.ensure_directories()
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self.path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            try:
                handle.write(self._to_toml(values))
                handle.flush()
                os.fsync(handle.fileno())
            except BaseException:
                handle.close()
                temporary.unlink(missing_ok=True)
                raise
        try:
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
        return value

    def output_directory(self, override: Path | None = None) -> Path:
        if override is not None:
            return override.expanduser().resolve()
        configured = self.load()["download"].get("directory")
        if configured:
            return Path(configured).expanduser().resolve()
        return (user_downloads_path() / "music").resolve()

    @staticmethod
    def _split_key(key: str) -> tuple[str, str]:
        if key.count(".") != 1:
            raise ConfigurationError("Configuration keys use section.name syntax")
        section, name = key.split(".", 1)
        return section, name

    @staticmethod
    def _coerce(raw: str, example: Any) -> Any:
        if isinstance(example, bool):
            normalized = raw.casefold()
            if normalized not in {"true", "false"}:
                raise ConfigurationError("Boolean values must be true or false")
            return normalized == "true"
        if isinstance(example, int):
            try:
                return int(raw)
            except ValueError as exc:
                raise ConfigurationError("Expected an integer value") from exc
        if isinstance(example, float):
            try:
                return float(raw)
            except ValueError as exc:
                raise ConfigurationError("Expected a numeric value") from exc
        return raw

    @staticmethod
    def _validate(values: dict[str, dict[str, Any]]) -> None:
        for section, options in values.items():
            for name, value in options.items():
                if name not in DEFAULTS[section]:
                    raise ConfigurationError(f"Unknown configuration key: {section}.{name}")
                expected = DEFAULTS[section][name]
                valid = (
                    type(value) in (int, float) and math.isfinite(value)
                    if isinstance(expected, float)
                    else type(value) is type(expected)
                )
                if not valid:
                    raise ConfigurationError(f"Invalid value for {section}.{name}")
        engine = values["download"].get("engine")
        if engine not in {"auto", "aria2", "requests"}:
            raise ConfigurationError("download.engine must be auto, aria2, or requests")
        connections = values["download"].get("aria2_connections")
        if not isinstance(connections, int) or not 1 <= connections <= 16:
            raise ConfigurationError("download.aria2_connections must be between 1 and 16")
        profile = values["network"].get("retry_profile")
        if profile not in {"fast", "balanced", "patient"}:
            raise ConfigurationError("network.retry_profile must be fast, balanced, or patient")
        if float(values["matching"].get("duration_tolerance", -1)) < 0:
            raise ConfigurationError("matching.duration_tolerance must be non-negative")
        if int(values["matching"].get("candidate_attempts", 0)) < 1:
            raise ConfigurationError("matching.candidate_attempts must be at least 1")
        if values["network"]["timeout"] <= 0:
            raise ConfigurationError("network.timeout must be positive")

    @staticmethod
    def _to_toml(values: dict[str, dict[str, Any]]) -> str:
        lines: list[str] = []
        for section, options in values.items():
            lines.append(f"[{section}]")
            for key, value in options.items():
                if isinstance(value, bool):
                    rendered = str(value).lower()
                elif isinstance(value, (int, float)):
                    rendered = str(value)
                else:
                    rendered = json.dumps(value, ensure_ascii=False)
                lines.append(f"{key} = {rendered}")
            lines.append("")
        return "\n".join(lines)
