from __future__ import annotations

from rapidfuzz import fuzz

from frogify.core.models import RankedCandidate
from mp3juice.models import SearchResult
from mp3juice.spotify_batch import (
    VERSION_QUALIFIERS,
    candidate_title_core,
    contains_phrase,
    normalize_text,
)


def rank_free_text(query: str, results: list[SearchResult]) -> list[RankedCandidate]:
    query_core = normalize_text(query)
    ranked: list[RankedCandidate] = []
    for result in results:
        title_core = candidate_title_core(result.title)
        score = float(fuzz.WRatio(query_core, title_core)) * 0.65
        score += float(fuzz.token_set_ratio(query_core, title_core)) * 0.35
        reasons: list[str] = []
        for qualifier, penalty in VERSION_QUALIFIERS.items():
            if contains_phrase(title_core, qualifier) and not contains_phrase(
                query_core, qualifier
            ):
                score -= min(float(penalty), 24.0)
                reasons.append(f"unexpected {qualifier}")
            elif contains_phrase(query_core, qualifier) and not contains_phrase(
                title_core, qualifier
            ):
                if qualifier == "mix" and any(
                    contains_phrase(query_core, phrase) for phrase in ("original mix", "album mix")
                ):
                    continue
                score -= min(float(penalty), 24.0)
                reasons.append(f"missing requested {qualifier}")
        if result.root_source.casefold() == "soundcloud":
            score += 0.5
        ranked.append(RankedCandidate(result, max(0.0, min(100.0, score)), tuple(reasons)))
    return sorted(
        ranked,
        key=lambda item: (
            item.score,
            item.result.duration_s is not None,
            item.result.root_source.casefold() == "soundcloud",
        ),
        reverse=True,
    )
