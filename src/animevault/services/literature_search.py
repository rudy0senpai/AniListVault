"""Literature search coordination: providers, caching and matching."""

from __future__ import annotations

import difflib
import logging
from typing import Optional

from animevault.models.literature import Literature
from animevault.services import cache
from animevault.services.providers.literature import (
    AniListLiteratureProvider,
    LiteratureMetadata,
)
from animevault.services.providers.base import ProviderError

logger = logging.getLogger(__name__)


def calculate_literature_match_score(query: str, meta: LiteratureMetadata) -> float:
    """Rank candidates by title similarity (higher is better)."""
    q = (query or "").strip().casefold()
    titles = [meta.title, meta.title_en, meta.title_native] + list(meta.synonyms)
    titles = [t.casefold() for t in titles if t and t.strip()]
    if not titles:
        return 0.0

    score = 0.0
    for t in titles:
        if t == q:
            score = max(score, 100.0)
        elif t.startswith(q):
            score = max(score, 70.0)
        elif q in t:
            score = max(score, 50.0)
        else:
            score = max(score, difflib.SequenceMatcher(None, q, t).ratio() * 45.0)
    return score


class LiteratureSearchService:
    """Searches literature providers with caching, ranking and fallback."""

    def __init__(self, providers: Optional[list] = None) -> None:
        self._providers = providers if providers is not None else [
            AniListLiteratureProvider(),
        ]

    @property
    def providers(self) -> list:
        return self._providers

    def search(
        self, query: str, limit: int = 15, *, force_refresh: bool = False
    ) -> list[LiteratureMetadata]:
        q = (query or "").strip()
        if not q:
            return []

        cache_key = f"search:literature:{q.casefold()}:{int(limit)}"
        cached = None if force_refresh else cache.get(cache_key, ttl=cache.TTL_METADATA)
        if cached is not None and isinstance(cached, list):
            return [LiteratureMetadata(**item) for item in cached]

        results: list[LiteratureMetadata] = []
        seen: set = set()
        last_retryable_error: ProviderError | None = None

        for provider in self._providers:
            if not provider.is_available():
                continue
            try:
                for meta in provider.search(q, limit=limit):
                    key = (
                        f"al:{meta.anilist_id}" if meta.anilist_id
                        else f"t:{meta.display_title().casefold()}"
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append(meta)
            except ProviderError as exc:
                logger.warning("Literature provider %s failed: %s", provider.name, exc)
                if exc.retryable:
                    last_retryable_error = exc
                continue
            except Exception as exc:
                logger.warning("Literature provider %s failed: %s", provider.name, exc)
                continue

        if not results and last_retryable_error is not None:
            raise last_retryable_error

        results.sort(
            key=lambda m: calculate_literature_match_score(q, m), reverse=True
        )
        results = results[:limit]

        if results:
            try:
                cache.put(cache_key, [vars(m) for m in results])
            except Exception:
                pass
        return results

    def find_duplicate(self, meta: LiteratureMetadata) -> Optional[Literature]:
        """Locate an existing library entry matching *meta*."""
        found = Literature.find_by_provider_id(
            anilist_id=meta.anilist_id, kitsu_id=meta.kitsu_id, mal_id=meta.mal_id
        )
        if found is not None:
            return found
        for title in (meta.title, meta.title_en, meta.title_native):
            if title and title.strip():
                found = Literature.find_by_title(title)
                if found is not None:
                    return found
        return None