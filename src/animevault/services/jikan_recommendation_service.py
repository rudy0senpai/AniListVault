"""Cached Jikan v4 recommendation candidates based on positively rated seeds."""
from __future__ import annotations

import json
import logging
import math
import os
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import Iterable, Optional

from animevault.services.providers.base import ProviderError
from animevault.services.providers.jikan import JikanProvider
from animevault.services.recommendation_discovery import Candidate

logger = logging.getLogger(__name__)
CACHE_TTL_SECONDS = 7 * 24 * 60 * 60


def _cache_dir() -> Path:
    root = Path(os.environ.get("APPDATA", Path.home() / ".local")) / "AnimeVault" / "cache" / "jikan"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _candidate_from_metadata(meta, votes: int, seed_title: str) -> Candidate:
    signal = min(1.0, math.log1p(max(0, votes)) / math.log(101))
    return Candidate(
        item_id=int(meta.mal_id or 0),
        title=meta.best_title(),
        title_en=meta.title_en,
        title_ja=meta.title_ja,
        title_romaji=meta.title_romaji,
        media_type=(meta.media_type or "ANIME").upper(),
        aired_from=meta.aired_from,
        aired_to=meta.aired_to,
        season=meta.season,
        season_year=meta.season_year or 0,
        genres=list(meta.genres or []),
        studios=list(meta.studios or []),
        synopsis=meta.synopsis or "",
        poster_url=meta.poster_url or "",
        mal_id=int(meta.mal_id or 0),
        anilist_id=int(meta.anilist_id or 0),
        kitsu_id=str(meta.kitsu_id or ""),
        tmdb_id=int(meta.tmdb_id or 0),
        episodes=int(meta.episodes or 0),
        discovery_source="jikan_recommendation",
        recommendation_signal=signal,
        recommendation_reasons=[f"Jikan users recommend it alongside {seed_title}"],
    )


class JikanRecommendationService:
    """Fetch/cache Jikan related-anime candidates; never writes to library tables."""

    def __init__(self, provider=None, *, cache_dir: Path | None = None, ttl_seconds: int = CACHE_TTL_SECONDS):
        self.provider = provider or JikanProvider()
        self.cache_dir = cache_dir or _cache_dir()
        self.ttl_seconds = ttl_seconds
        self.last_error: Optional[str] = None

    def _path(self, mal_id: int) -> Path:
        return self.cache_dir / f"recommendations_{int(mal_id)}.json"

    def _read_cache(self, mal_id: int) -> tuple[list[Candidate], bool]:
        try:
            payload = json.loads(self._path(mal_id).read_text(encoding="utf-8"))
            entries = payload.get("candidates", [])
            candidates = [Candidate(**entry) for entry in entries if isinstance(entry, dict)]
            fresh = time.time() - float(payload.get("cached_at", 0)) < self.ttl_seconds
            return candidates, fresh
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return [], False

    def _write_cache(self, mal_id: int, candidates: list[Candidate]) -> None:
        path = self._path(mal_id)
        temporary = path.with_suffix(".tmp")
        payload = {"cached_at": time.time(), "candidates": [asdict(candidate) for candidate in candidates]}
        try:
            temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            temporary.replace(path)
        except OSError as exc:
            logger.warning("Could not persist Jikan recommendations for MAL %s: %s", mal_id, exc)
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def recommendations_for(self, seeds: Iterable[tuple[int, str]], *, per_seed: int = 8, max_seeds: int = 3) -> list[Candidate]:
        """Fetch related titles for the best few MAL seeds, preferring fresh cache."""
        candidates: list[Candidate] = []
        self.last_error = None
        seen: set[int] = set()
        for mal_id, seed_title in list(seeds)[:max_seeds]:
            if not mal_id:
                continue
            cached, fresh = self._read_cache(int(mal_id))
            used_cache = fresh
            if fresh:
                batch = cached
            else:
                try:
                    related = self.provider.get_recommendations(int(mal_id), limit=per_seed)
                    batch = []
                    for meta, votes in related[:per_seed]:
                        if not meta.mal_id:
                            continue
                        # Related endpoints are intentionally light; retrieve full
                        # detail for top candidates to supply usable scoring data.
                        if len(batch) < 3 and (not meta.genres or not meta.synopsis):
                            try:
                                detail = self.provider.get_details(str(meta.mal_id))
                                meta = detail
                            except Exception as exc:
                                logger.debug("Jikan detail unavailable for MAL %s: %s", meta.mal_id, exc)
                        batch.append(_candidate_from_metadata(meta, votes, seed_title))
                    # Cache successful empty responses too, avoiding repeated
                    # calls for titles with no Jikan recommendation rows.
                    self._write_cache(int(mal_id), batch)
                except Exception as exc:
                    logger.warning("Jikan recommendation lookup failed for MAL %s: %s", mal_id, exc)
                    self.last_error = str(exc)
                    batch = cached  # stale offline cache is still useful
                    used_cache = bool(cached)
            for candidate in batch:
                if used_cache:
                    candidate = replace(candidate, is_cached=True)
                pid = int(candidate.mal_id or candidate.item_id or 0)
                if pid and pid not in seen:
                    seen.add(pid)
                    candidates.append(candidate)
        return candidates
