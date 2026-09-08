from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mp3juice.models import SearchResult


@dataclass(frozen=True, slots=True)
class FreeTextRequest:
    query: str


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    result: SearchResult
    score: float
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DownloadResult:
    path: Path
    candidate: RankedCandidate
    transfer_engine: str


@dataclass(frozen=True, slots=True)
class BatchResult:
    total: int
    downloaded: int
    skipped: int
    failed: int
