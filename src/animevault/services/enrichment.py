"""Metadata merge and enrichment utilities (provider-agnostic)."""

from __future__ import annotations

import datetime
import logging
from typing import Optional

from animevault.services.providers.base import AnimeMetadata

logger = logging.getLogger(__name__)


def pick_best_match(
    query: str,
    results: list[AnimeMetadata],
    *,
    anilist_id: Optional[int] = None,
    mal_id: Optional[int] = None,
) -> Optional[AnimeMetadata]:
    """Select the best-matching result from a provider result list.

    Priority:
    1. Provider ID exact match (most reliable)
    2. Exact title match (case-insensitive)
    3. First result as fallback
    """
    if not results:
        return None

    q = query.strip().lower()

    # 1. Provider ID match
    if anilist_id:
        for r in results:
            if r.anilist_id == anilist_id:
                return r
    if mal_id:
        for r in results:
            if r.mal_id == mal_id:
                return r

    # 2. Exact title match across all title variants
    for r in results:
        candidates = [r.title, r.title_en, r.title_ja, r.title_romaji] + r.synonyms
        for t in candidates:
            if t and t.strip().lower() == q:
                return r

    # 3. First result
    return results[0]


def merge_metadata_into_anime(anime, meta: AnimeMetadata) -> None:
    """Merge provider metadata into an existing Anime record **in-place**.

    Rules
    -----
    - Only *metadata* fields are touched — personal user fields are NEVER
      overwritten (status, score, notes remain intact).
    - An empty/zero existing value is filled from the provider.
    - A non-empty existing value is preserved.
    - Provider IDs are *additive* (set if missing, never erased).
    """
    # ── Title fields ─────────────────────────────────────────────
    if not anime.title_en and meta.title_en:
        anime.title_en = meta.title_en
    if not anime.title_ja and meta.title_ja:
        anime.title_ja = meta.title_ja

    # ── Description ───────────────────────────────────────────────
    if not anime.synopsis and meta.synopsis:
        anime.synopsis = meta.synopsis

    # ── Classification ────────────────────────────────────────────
    if not anime.media_type and meta.media_type:
        anime.media_type = meta.media_type
    if not anime.airing_status and meta.airing_status:
        anime.airing_status = meta.airing_status
    if not anime.genres and meta.genres:
        anime.genres = list(meta.genres)

    # ── Release ───────────────────────────────────────────────────
    if not anime.aired_from and meta.aired_from:
        anime.aired_from = meta.aired_from
    if not anime.aired_to and meta.aired_to:
        anime.aired_to = meta.aired_to
    if not anime.season and meta.season:
        anime.season = meta.season
    if anime.season_year is None and meta.season_year:
        anime.season_year = meta.season_year

    # ── Episodes / Duration ───────────────────────────────────────
    if anime.episodes == 0 and meta.episodes > 0:
        anime.episodes = meta.episodes
    if anime.duration == 0 and meta.duration > 0:
        anime.duration = meta.duration

    # ── Production ────────────────────────────────────────────────
    if not anime.studios and meta.studios:
        anime.studios = list(meta.studios)

    # ── Poster ────────────────────────────────────────────────────
    if not anime.poster_url and meta.poster_url:
        anime.poster_url = meta.poster_url

    # ── Provider IDs (additive) ───────────────────────────────────
    if meta.mal_id is not None and anime.mal_id is None:
        anime.mal_id = meta.mal_id
    if meta.anilist_id is not None and anime.anilist_id is None:
        anime.anilist_id = meta.anilist_id
    if meta.kitsu_id is not None and anime.kitsu_id is None:
        anime.kitsu_id = meta.kitsu_id
    if meta.tmdb_id is not None and anime.tmdb_id is None:
        anime.tmdb_id = meta.tmdb_id

    # ── Source / timestamp ────────────────────────────────────────
    if not anime.source_provider and meta.source_provider:
        anime.source_provider = meta.source_provider
    anime.metadata_fetched_at = datetime.datetime.now(datetime.timezone.utc).isoformat()


def anime_from_metadata(meta: AnimeMetadata, *, status: str = "plan_to_watch"):
    """Create an *unsaved* Anime from provider metadata.

    Only metadata fields are populated.  Personal fields use their
    dataclass defaults (status is set to *status* param).
    """
    from animevault.models.anime import Anime  # late import to avoid circular

    return Anime(
        id=None,
        title=meta.best_title(),
        title_en=meta.title_en,
        title_ja=meta.title_ja,
        synopsis=meta.synopsis,
        episodes=meta.episodes,
        status=status,
        score=None,
        notes="",
        media_type=meta.media_type,
        airing_status=meta.airing_status,
        aired_from=meta.aired_from,
        aired_to=meta.aired_to,
        season=meta.season,
        season_year=meta.season_year,
        duration=meta.duration,
        genres=list(meta.genres),
        studios=list(meta.studios),
        poster_url=meta.poster_url,
        poster_path="",
        mal_id=meta.mal_id,
        anilist_id=meta.anilist_id,
        kitsu_id=meta.kitsu_id,
        tmdb_id=meta.tmdb_id,
        source_provider=meta.source_provider,
        metadata_fetched_at="",
    )
