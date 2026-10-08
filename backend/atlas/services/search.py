"""Search across entities.

Ranks with a transparent, deterministic scorer: exact and prefix matches on
the name beat qualified-name hits, which beat technology/location hits. A
lightweight fuzzy layer (subsequence + edit-distance-ish penalty) catches
``studnet`` -> ``Student`` without pulling in a search dependency.

10k entities is well within budget to score in memory; this keeps the ranking
identical across SQLite and any future backend.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from atlas.models import Entity

_TOKEN_SPLIT = re.compile(r"[^0-9a-zA-Z]+")


def _tokens(value: str) -> list[str]:
    return [t.lower() for t in _TOKEN_SPLIT.split(value or "") if t]


def _normalise(value: str) -> str:
    return " ".join(_tokens(value))


@dataclass(frozen=True)
class SearchHitResult:
    entity: Entity
    score: float
    matched_on: str


def _fuzzy_ratio(needle: str, haystack: str) -> float:
    """Cheap subsequence/contiguity score in [0, 1]."""
    if not needle or not haystack:
        return 0.0
    if needle in haystack:
        return 1.0
    if haystack in needle and len(haystack) >= 3:
        return 0.75
    idx = 0
    matched = 0
    contiguous = 0
    best_contiguous = 0
    for ch in haystack:
        if idx < len(needle) and ch == needle[idx]:
            matched += 1
            contiguous += 1
            best_contiguous = max(best_contiguous, contiguous)
            idx += 1
        else:
            contiguous = 0
    if matched == 0:
        return 0.0
    coverage = matched / len(needle)
    contiguity = best_contiguous / max(len(needle), 1)
    return round(0.7 * coverage + 0.3 * contiguity, 4)


_FIELDS: tuple[tuple[str, float], ...] = (
    ("name", 1.0),
    ("qualified_name", 0.85),
    ("entity_type", 0.35),
    ("technology", 0.5),
    ("location", 0.5),
    ("owner", 0.45),
    ("description", 0.4),
)


def search_entities(entities: list[Entity], query: str, *, limit: int = 50) -> list[SearchHitResult]:
    q = query.strip().lower()
    if not q:
        return []
    q_norm = _normalise(query)
    q_tokens = _tokens(query)

    scored: list[SearchHitResult] = []
    for entity in entities:
        best_score = 0.0
        best_field = ""
        for field_name, weight in _FIELDS:
            raw = getattr(entity, field_name, "") or ""
            if not raw:
                continue
            value = raw.lower()
            value_norm = _normalise(raw)

            score = 0.0
            if value == q or value_norm == q_norm:
                score = 1.0
            elif value.startswith(q) or value_norm.startswith(q_norm):
                score = 0.9
            elif q in value or q_norm in value_norm:
                score = 0.72
            else:
                fuzzy = max(
                    (_fuzzy_ratio(tok, value_norm) for tok in q_tokens),
                    default=0.0,
                )
                score = fuzzy * 0.55

            weighted = score * weight
            if weighted > best_score:
                best_score = weighted
                best_field = field_name

        if best_score > 0:
            scored.append(SearchHitResult(entity=entity, score=round(best_score, 4), matched_on=best_field))

    scored.sort(key=lambda h: (-h.score, h.entity.name.lower(), h.entity.id))
    return scored[:limit]
