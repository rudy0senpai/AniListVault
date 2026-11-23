"""Cached Jikan v4 recommendation candidates based on positively rated seeds."""
from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import Iterable, Optional

from animevault.services.providers.base import ProviderError
from animevault.services.providers.jikan import JikanProvider
from animevault.services.recommendation_discovery import Candidate
from animevault.services.title_norm import normalize_title

logger = logging.getLogger(__name__)
CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
GENRE_CACHE_TTL_SECONDS = 30 * 24 * 60 * 60
GENRE_RESULTS_TTL_SECONDS = 24 * 60 * 60
_SERVICE_LOCK = threading.RLock()


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


def _genre_candidate(meta, genre_name: str) -> Candidate:
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
        discovery_source="jikan_genre",
        recommendation_reasons=[f"Discovered through your positive {genre_name} preference"],
    )


class JikanRecommendationService:
    """Fetch/cache Jikan related-anime candidates; never writes to library tables."""

    def __init__(self, provider=None, *, cache_dir: Path | None = None, ttl_seconds: int = CACHE_TTL_SECONDS):
        self.provider = provider or JikanProvider()
        self.cache_dir = cache_dir or _cache_dir()
        self.ttl_seconds = ttl_seconds
        self.last_error: Optional[str] = None
        self.errors: list[dict] = []
        self.stats = {
            "usable_seeds": 0,
            "related_candidates_raw": 0,
            "genre_ids_mapped": 0,
            "genre_pages": 0,
            "genre_candidates_raw": 0,
            "genre_detail_requests": 0,
            "candidates_before_dedup": 0,
            "duplicates_removed": 0,
        }

    def reset_diagnostics(self) -> None:
        self.last_error = None
        self.errors.clear()
        for key in self.stats:
            self.stats[key] = 0

    @staticmethod
    def _error_category(exc: Exception) -> str:
        status = getattr(exc, "status_code", None)
        message = str(exc).casefold()
        if status == 429:
            return "http_429_rate_limited"
        if status in (500, 502, 503, 504):
            return "http_server_error"
        if status is not None:
            return "http_error"
        if "timeout" in message or "timed out" in message:
            return "timeout"
        if "invalid response" in message or "malformed" in message:
            return "invalid_response"
        return "provider_error"

    def _record_error(self, source: str, exc: Exception) -> None:
        error = {"source": source, "category": self._error_category(exc), "message": str(exc)}
        self.errors.append(error)
        self.last_error = str(exc)

    def _json_cache_read(self, path: Path, ttl_seconds: int):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or "cached_at" not in payload:
                return None, False
            fresh = time.time() - float(payload["cached_at"]) < ttl_seconds
            return payload, fresh
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None, False

    def _json_cache_write(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        try:
            data = {"cached_at": time.time(), **payload}
            temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            temporary.replace(path)
        except OSError as exc:
            logger.warning("Could not persist Jikan cache %s: %s", path.name, exc)
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def genre_ids_for(self, genre_names: Iterable[str]) -> list[tuple[str, int]]:
        """Map profile genre names through Jikan's cached live catalogue."""
        path = self.cache_dir / "anime_genres.json"
        payload, fresh = self._json_cache_read(path, GENRE_CACHE_TTL_SECONDS)
        names = payload.get("genres", []) if payload else []
        if not fresh:
            try:
                catalogue = self.provider.get_genre_catalogue()
                names = [{"id": int(gid), "name": str(name)} for gid, name in catalogue]
                self._json_cache_write(path, {"genres": names})
            except Exception as exc:
                self._record_error("genre_catalogue", exc)
                if not names:
                    return []
        aliases = {"science fiction": "sci-fi", "sci fi": "sci-fi", "slice-of-life": "slice of life"}
        catalogue = {}
        for entry in names:
            try:
                normalized = normalize_title(str(entry["name"]))
                catalogue[aliases.get(normalized, normalized)] = int(entry["id"])
            except (KeyError, TypeError, ValueError):
                continue
        mapped = []
        used = set()
        for raw in genre_names:
            name = str(raw or "").strip()
            normalized = normalize_title(name)
            lookup = aliases.get(normalized, normalized)
            genre_id = catalogue.get(lookup)
            if genre_id and genre_id not in used:
                mapped.append((name, genre_id))
                used.add(genre_id)
        self.stats["genre_ids_mapped"] = len(mapped)
        return mapped

    def genre_candidates(self, genre_names: Iterable[str], *, max_genres: int = 3, pages_per_genre: int = 2, limit: int = 15) -> list[Candidate]:
        """Discover from preferred genres, bounded to three genres and two pages each."""
        with _SERVICE_LOCK:
            return self._genre_candidates_locked(genre_names, max_genres=max_genres, pages_per_genre=pages_per_genre, limit=limit)

    def _genre_candidates_locked(self, genre_names: Iterable[str], *, max_genres: int, pages_per_genre: int, limit: int) -> list[Candidate]:
        candidates: list[Candidate] = []
        detail_requests = 0
        for genre_name, genre_id in self.genre_ids_for(list(genre_names)[:max_genres]):
            for page in range(1, max(1, min(pages_per_genre, 2)) + 1):
                path = self.cache_dir / f"genre_{genre_id}_page_{page}.json"
                cached, fresh = self._json_cache_read(path, GENRE_RESULTS_TTL_SECONDS)
                used_cache = fresh
                if fresh:
                    entries = cached.get("candidates", [])
                    has_next = bool(cached.get("has_next_page", False))
                    batch = []
                    for entry in entries:
                        try:
                            batch.append(Candidate(**entry))
                        except (TypeError, ValueError):
                            continue
                else:
                    try:
                        metadata, has_next = self.provider.get_anime_by_genre(genre_id, page=page, limit=limit)
                        self.stats["genre_pages"] += 1
                        batch = []
                        for meta in metadata:
                            if not meta.mal_id:
                                continue
                            if detail_requests < 2 and (not meta.genres or not meta.synopsis):
                                get_details = getattr(self.provider, "get_details", None)
                                if callable(get_details):
                                    detail_requests += 1
                                    self.stats["genre_detail_requests"] = detail_requests
                                    try:
                                        meta = get_details(str(meta.mal_id))
                                    except Exception as exc:
                                        self._record_error("genre_detail", exc)
                            batch.append(_genre_candidate(meta, genre_name))
                        self._json_cache_write(path, {"candidates": [asdict(item) for item in batch], "has_next_page": bool(has_next)})
                    except Exception as exc:
                        self._record_error("genre_discovery", exc)
                        if not cached:
                            break
                        batch = []
                        for entry in cached.get("candidates", []):
                            try:
                                batch.append(Candidate(**entry))
                            except (TypeError, ValueError):
                                continue
                        has_next = bool(cached.get("has_next_page", False))
                        used_cache = bool(batch)
                self.stats["genre_candidates_raw"] += len(batch)
                for candidate in batch:
                    if used_cache:
                        candidate = replace(candidate, is_cached=True)
                    candidates.append(candidate)
                if not has_next:
                    break
        return candidates

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
        with _SERVICE_LOCK:
            return self._recommendations_for_locked(seeds, per_seed=per_seed, max_seeds=max_seeds)

    def _recommendations_for_locked(self, seeds: Iterable[tuple[int, str]], *, per_seed: int, max_seeds: int) -> list[Candidate]:
        """Fetch related titles for the best few MAL seeds, preferring fresh cache."""
        candidates: list[Candidate] = []
        seen: set[int] = set()
        unique_seeds = []
        seed_ids = set()
        for mal_id, title in seeds:
            try:
                mal_id = int(mal_id)
            except (TypeError, ValueError):
                continue
            if mal_id > 0 and mal_id not in seed_ids:
                seed_ids.add(mal_id)
                unique_seeds.append((mal_id, str(title)))
        unique_seeds = unique_seeds[:max(0, max_seeds)]
        self.stats["usable_seeds"] = len(unique_seeds)
        raw_count = 0
        for mal_id, seed_title in unique_seeds:
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
                    self._record_error("related_recommendations", exc)
                    batch = cached  # stale offline cache is still useful
                    used_cache = bool(cached)
            for candidate in batch:
                raw_count += 1
                if used_cache:
                    candidate = replace(candidate, is_cached=True)
                pid = int(candidate.mal_id or candidate.item_id or 0)
                if pid and pid not in seen:
                    seen.add(pid)
                    candidates.append(candidate)
        self.stats["related_candidates_raw"] = raw_count
        self.stats["duplicates_removed"] = max(0, raw_count - len(candidates))
        return candidates
