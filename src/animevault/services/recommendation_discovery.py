"""External candidate discovery for recommendations.

Uses AnimeVault's existing metadata providers (AniList, Jikan/MyAnimeList,
Kitsu, TMDB, Anidb) to discover anime that are not already in the user's
library.  Only run when the online discovery setting is enabled.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, Sequence

from animevault.services.providers.base import AnimeMetadata, BaseProvider
from animevault.services.providers.anilist import AniListProvider
from animevault.services.providers.jikan import JikanProvider
from animevault.services.providers.kitsu import KitsuProvider
from animevault.services.providers.tmdb import TmdbProvider
from animevault.services.title_norm import normalize_title

logger = logging.getLogger(__name__)

# Providers that return full metadata (search + details).
_FULL_METADATA_PROVIDERS = ("anilist", "kitsu", "tmdb", "jikan")

# Cache of discovered candidate titles per provider; avoids re-fetching.
_discovery_cache: dict[str, dict[str, AnimeMetadata]] = {}


def _get_provider(name: str) -> Optional[BaseProvider]:
    """Return an instance of the named provider, or None if unavailable."""
    registry = {
        "anilist": AniListProvider(),
        "jikan": JikanProvider(),
        "kitsu": KitsuProvider(),
        "tmdb": TmdbProvider(),
    }
    return registry.get(name)


@dataclass(frozen=True)
class Candidate:
    """A discovered candidate for recommendation."""
    item_id: int
    title: str
    title_en: str = ""
    title_ja: str = ""
    title_romaji: str = ""
    media_type: str = ""
    aired_from: str = ""
    aired_to: str = ""
    season: str = ""
    season_year: int = 0
    genres: list[str] = field(default_factory=list)
    studios: list[str] = field(default_factory=list)
    synopsis: str = ""
    poster_url: str = ""
    mal_id: int = 0
    anilist_id: int = 0
    kitsu_id: str = ""
    tmdb_id: int = 0
    episodes: int = 0
    is_plan_to_watch: bool = False
    discovery_source: str = ""
    recommendation_signal: float = 0.0
    recommendation_reasons: list[str] = field(default_factory=list)
    is_cached: bool = False


def _provider_search(provider: BaseProvider, query: str, limit: int = 10) -> list[AnimeMetadata]:
    try:
        return provider.search(query, limit=limit)
    except Exception as exc:
        logger.warning("Provider %s search failed for %r: %s", provider.name, query, exc)
        return []


def discover_candidates(
    query: str,
    categories: Optional[Sequence[str]] = None,
    *,
    limit: int = 10,
    providers: Optional[Sequence[str]] = None,
) -> list[Candidate]:
    """Search providers for anime matching *query* and *categories*.

    Returns a flat list of :class:`Candidate` objects.  When *categories* is
    provided, the search is restricted by genre matching.
    """
    categories = list(categories or [])
    providers = list(providers or _FULL_METADATA_PROVIDERS)

    candidates: list[Candidate] = []
    for pname in providers:
        provider = _get_provider(pname)
        if provider is None:
            continue
        try:
            metas = _provider_search(provider, query, limit=limit)
        except Exception:
            continue

        for meta in metas:
            if not isinstance(meta, AnimeMetadata):
                logger.debug("Provider %s returned malformed metadata: %r", pname, meta)
                continue
            # Category filter.
            if categories:
                cats = {str(g).strip().casefold() for g in (meta.genres or []) if g}
                requested_categories = {str(g).strip().casefold() for g in categories if g}
                if not cats & requested_categories:
                    continue

            candidate = Candidate(
                item_id=meta.anilist_id or meta.mal_id or 0,
                title=meta.best_title(),
                title_en=meta.title_en,
                title_ja=meta.title_ja,
                title_romaji=meta.title_romaji,
                media_type=meta.media_type,
                aired_from=meta.aired_from,
                aired_to=meta.aired_to,
                season=meta.season,
                season_year=meta.season_year or 0,
                genres=list(meta.genres),
                studios=list(meta.studios),
                synopsis=meta.synopsis,
                poster_url=meta.poster_url,
                mal_id=meta.mal_id or 0,
                anilist_id=meta.anilist_id or 0,
                kitsu_id=meta.kitsu_id or "",
                tmdb_id=meta.tmdb_id or 0,
                episodes=meta.episodes or 0,
                discovery_source=pname,
            )
            candidates.append(candidate)
    # Deduplicate by a stable provider identifier when one is available.
    # Otherwise fall back to a normalized title + media type.  Two records with
    # different provider identifiers (e.g. one from Anilist and one from Kitsu)
    # are kept separate even when their titles are identical.  Media type is
    # part of the fallback key so that a TV and a Movie with the same title
    # remain distinct works.
    seen_keys: set = set()
    dedup: list[Candidate] = []
    for c in candidates:
        key = _candidate_key(c)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        dedup.append(c)

    return dedup[:limit]


def _candidate_key(candidate: Candidate) -> tuple:
    """Deduplication key for a discovered candidate.

    A stable provider identifier (AniList, MAL, TMDb, then Kitsu) is preferred.
    When a candidate carries no reliable identifier, a normalized title + media
    type is used so that distinct works are never merged solely because their
    titles are similar or identical.
    """
    for attr in ("anilist_id", "mal_id", "tmdb_id"):
        value = getattr(candidate, attr, None)
        if value:
            try:
                return ("provider", attr, int(value), str(candidate.media_type or "").lower())
            except (TypeError, ValueError):
                continue
    kitsu = getattr(candidate, "kitsu_id", None)
    if kitsu:
        return ("provider", "kitsu_id", str(kitsu), str(candidate.media_type or "").lower())
    return ("title", normalize_title(candidate.title), str(candidate.media_type or "").lower())


def search_by_title(
    query: str,
    limit: int = 10,
) -> list[Candidate]:
    """Search all full-metadata providers by title."""
    return discover_candidates(query, limit=limit)
