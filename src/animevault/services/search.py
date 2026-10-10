"""Multi-provider anime search and metadata coordination service."""

from __future__ import annotations

import difflib
import logging
from typing import Optional

from animevault.models.anime import Anime
from animevault.services import cache
from animevault.services.providers.anilist import AniListProvider
from animevault.services.providers.base import AnimeMetadata, BaseProvider, ProviderError
from animevault.services.providers.jikan import JikanProvider
from animevault.services.providers.kitsu import KitsuProvider
from animevault.services.providers.tmdb import TmdbProvider

logger = logging.getLogger(__name__)


def calculate_match_score(query: str, candidate: AnimeMetadata) -> float:
    """Calculate match relevance score (higher is better).

    Considers exact match, word prefix, and string similarity.
    """
    q = query.strip().lower()
    titles = [
        candidate.title,
        candidate.title_en,
        candidate.title_romaji,
        candidate.title_ja,
    ] + candidate.synonyms
    titles = [t.strip().lower() for t in titles if t and t.strip()]

    if not titles:
        return 0.0

    score = 0.0
    for t in titles:
        if t == q:
            score = max(score, 100.0)
        elif t.startswith(q + " ") or t.startswith(q + ":"):
            # e.g. "Naruto: Shippuden" for query "Naruto"
            score = max(score, 70.0)
        elif q in t:
            score = max(score, 50.0)
        else:
            sim = difflib.SequenceMatcher(None, q, t).ratio() * 45.0
            score = max(score, sim)

    # Boost TV series or movies over obscure formats if ambiguous
    if candidate.media_type in ("TV", "MOVIE"):
        score += 2.0

    return score


class SearchService:
    """Coordinates search across available providers with caching and fallback."""

    def __init__(self, providers: Optional[list[BaseProvider]] = None) -> None:
        if providers is not None:
            self._providers = providers
        else:
            # AniList is confirmed working primary, followed by Kitsu, Jikan, TMDB
            self._providers = [
                AniListProvider(),
                KitsuProvider(),
                JikanProvider(),
                TmdbProvider(),
            ]

    @property
    def providers(self) -> list[BaseProvider]:
        return self._providers

    def search(
        self, query: str, limit: int = 15, *, force_refresh: bool = False
    ) -> list[AnimeMetadata]:
        """Search across providers in priority order with caching and scoring."""
        q = query.strip()
        if not q:
            return []

        cache_key = f"search:multi:{q.casefold()}:{int(limit)}"
        cached = None if force_refresh else cache.get(cache_key, ttl=cache.TTL_METADATA)
        if cached is not None and isinstance(cached, list):
            logger.debug("Cache hit for search %r", q)
            # Reconstruct AnimeMetadata objects from cached dicts
            return [AnimeMetadata(**item) for item in cached]

        all_results: list[AnimeMetadata] = []
        seen_keys: set[str] = set()
        last_retryable_error: ProviderError | None = None

        for provider in self._providers:
            if not provider.is_available():
                logger.debug("Skipping unavailable provider %s", provider.name)
                continue

            try:
                logger.info("Searching %s for %r", provider.name, q)
                results = provider.search(q, limit=limit)
                for r in results:
                    # Deduplicate within search results
                    dedup_key = (
                        f"mal:{r.mal_id}" if r.mal_id
                        else f"anilist:{r.anilist_id}" if r.anilist_id
                        else f"title:{r.best_title().lower()}:{r.season_year}"
                    )
                    if dedup_key not in seen_keys:
                        seen_keys.add(dedup_key)
                        all_results.append(r)

                # If primary provider returned strong matches, we don't need to hammer remaining
                if all_results and any(calculate_match_score(q, r) >= 90.0 for r in all_results):
                    break
            except ProviderError as exc:
                logger.warning("Provider %s error searching %r: %s", provider.name, q, exc)
                if exc.retryable:
                    last_retryable_error = exc
                continue
            except Exception as exc:
                logger.warning("Unexpected error from %s: %s", provider.name, exc)
                continue

        # A failed search must not be treated as a durable not-found response.
        if not all_results and last_retryable_error is not None:
            raise last_retryable_error

        # Rank results by match score
        all_results.sort(key=lambda r: calculate_match_score(q, r), reverse=True)
        final_results = all_results[:limit]

        if final_results:
            try:
                cache.put(cache_key, [vars(r) for r in final_results])
            except Exception:
                pass

        return final_results

    def find_duplicate_in_library(self, meta: AnimeMetadata) -> Optional[Anime]:
        """Check if an anime corresponding to *meta* is already in the library."""
        # 1. By provider IDs
        match = Anime.find_by_provider_id(
            anilist_id=meta.anilist_id,
            mal_id=meta.mal_id,
            kitsu_id=meta.kitsu_id,
            tmdb_id=meta.tmdb_id,
        )
        if match:
            return match

        # 2. By title
        for t in [meta.title, meta.title_en, meta.title_romaji, meta.title_ja]:
            if t and t.strip():
                match = Anime.find_by_title(t)
                if match:
                    return match

        return None
