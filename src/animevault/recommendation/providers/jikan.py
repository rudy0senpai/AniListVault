"""Jikan expands an external candidate pool; it never controls ranking."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from ..models import UserPreferenceProfile


@dataclass(frozen=True)
class DiscoveryBatch:
    candidates: tuple[Any, ...] = ()
    errors: tuple[dict, ...] = ()
    stats: dict = field(default_factory=dict)


class JikanCandidateProvider:
    def __init__(self, service=None):
        self.service = service

    def _service(self):
        if self.service is None:
            from animevault.services.jikan_recommendation_service import JikanRecommendationService
            self.service = JikanRecommendationService()
        return self.service

    def discover(self, profile: UserPreferenceProfile, *, seed_limit: int = 3, genre_limit: int = 3, page_limit: int = 2, per_page: int = 25) -> DiscoveryBatch:
        service = self._service()
        reset = getattr(service, "reset_diagnostics", None)
        if callable(reset): reset()
        candidates, errors = [], []
        seed_pairs, seen = [], set()
        for item in profile.positive_seeds:
            if str(getattr(item, "category", "") or "").casefold() in {"manga", "manhwa", "manhua"}:
                continue  # Jikan's related-anime endpoint requires anime MAL IDs.
            raw = getattr(item, "mal_id", None)
            try: mal_id = int(raw)
            except (TypeError, ValueError): continue
            if mal_id > 0 and mal_id not in seen:
                seen.add(mal_id)
                seed_pairs.append((mal_id, str(getattr(item, "title", ""))))
        if seed_pairs:
            try:
                candidates.extend(service.recommendations_for(seed_pairs[:seed_limit], per_seed=8, max_seeds=seed_limit))
            except Exception as exc:
                errors.append(_error("related_recommendations", exc))
        genres = sorted(profile.positive_genres.items(), key=lambda row: (-row[1], row[0]))[:genre_limit]
        if genres:
            try:
                candidates.extend(service.genre_candidates([name for name, _ in genres], max_genres=genre_limit,
                                                           pages_per_genre=page_limit, limit=per_page))
            except Exception as exc:
                errors.append(_error("genre_discovery", exc))
        errors.extend(list(getattr(service, "errors", []) or []))
        return DiscoveryBatch(tuple(candidates), tuple(errors), dict(getattr(service, "stats", {}) or {}))


def _error(source, exc):
    status = getattr(exc, "status_code", None)
    if status == 429: category = "rate_limited"
    elif status is not None: category = f"http_{status}"
    elif "timeout" in str(exc).casefold(): category = "timeout"
    else: category = "provider_error"
    return {"source": source, "category": category, "message": str(exc)}
