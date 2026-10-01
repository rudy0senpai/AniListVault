"""TMDB provider — requires ANIMEVAULT_TMDB_KEY environment variable.

If the key is not set, the provider reports itself as unavailable and is
silently skipped by the search service.  Nothing crashes.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from .base import AnimeMetadata, BaseProvider, ProviderError

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.themoviedb.org/3"
_POSTER_BASE = "https://image.tmdb.org/t/p/w500"


def _api_key() -> Optional[str]:
    return os.environ.get("ANIMEVAULT_TMDB_KEY") or None


def _tmdb_get(path: str, params: dict, timeout: int = 12) -> dict:
    key = _api_key()
    if not key:
        raise ProviderError("TMDB API key not configured", retryable=False)
    params["api_key"] = key
    qs = urllib.parse.urlencode(params)
    url = f"{_BASE_URL}{path}?{qs}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "AnimeVault/0.2", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        code = exc.code
        if code == 401:
            raise ProviderError("TMDB invalid API key (401)", status_code=401, retryable=False)
        if code == 404:
            raise ProviderError("TMDB 404: not found", status_code=404, retryable=False)
        if code == 429:
            raise ProviderError("TMDB rate limited (429)", status_code=429, retryable=True)
        if code in (500, 502, 503, 504):
            raise ProviderError(f"TMDB server error {code}", status_code=code, retryable=True)
        raise ProviderError(f"TMDB HTTP {code}", status_code=code, retryable=False)
    except urllib.error.URLError as exc:
        raise ProviderError(f"TMDB network error: {exc}", retryable=True)
    except ProviderError:
        raise
    except Exception as exc:
        raise ProviderError(f"TMDB unexpected error: {exc}", retryable=False)


def normalize_tv(show: dict) -> AnimeMetadata:
    """Convert a raw TMDB TV show dict to :class:`AnimeMetadata`."""
    title = (show.get("name") or "").strip()
    title_orig = (show.get("original_name") or "").strip()
    overview = (show.get("overview") or "").strip()

    genres = [g.get("name", "") for g in (show.get("genres") or []) if g.get("name")]
    networks = show.get("networks") or []
    studios = [n.get("name", "") for n in networks if n.get("name")]

    first_air = (show.get("first_air_date") or "")[:10]
    poster_path = show.get("poster_path") or ""
    poster_url = f"{_POSTER_BASE}{poster_path}" if poster_path else ""

    episodes = int(show.get("number_of_episodes") or 0)

    raw_status = (show.get("status") or "").lower()
    if "ended" in raw_status or "canceled" in raw_status:
        airing_status = "FINISHED"
    elif "airing" in raw_status or "returning" in raw_status:
        airing_status = "RELEASING"
    else:
        airing_status = raw_status.upper()

    season_year: Optional[int] = None
    if first_air and len(first_air) >= 4:
        try:
            season_year = int(first_air[:4])
        except ValueError:
            pass

    return AnimeMetadata(
        title=title,
        title_en=title,
        title_ja=title_orig if title_orig != title else "",
        synopsis=overview,
        media_type="TV",
        airing_status=airing_status,
        genres=genres,
        aired_from=first_air,
        season_year=season_year,
        episodes=episodes,
        studios=studios,
        poster_url=poster_url,
        tmdb_id=show.get("id"),
        source_provider="tmdb",
    )


class TmdbProvider(BaseProvider):
    """TMDB provider (TV anime).  Requires ANIMEVAULT_TMDB_KEY env var."""

    name = "tmdb"

    def is_available(self) -> bool:
        return bool(_api_key())

    def search(self, query: str, limit: int = 10) -> list[AnimeMetadata]:
        if not self.is_available():
            raise ProviderError("TMDB API key not configured", retryable=False)
        data = _tmdb_get(
            "/search/tv",
            {"query": query.strip(), "page": 1, "language": "en-US"},
        )
        raw = (data.get("results") or [])[:limit]
        results = []
        for show in raw:
            try:
                results.append(normalize_tv(show))
            except Exception as exc:
                logger.debug("TMDB: skipping malformed result: %s", exc)
        return results

    def get_details(self, provider_id: str) -> AnimeMetadata:
        if not self.is_available():
            raise ProviderError("TMDB API key not configured", retryable=False)
        data = _tmdb_get(f"/tv/{provider_id}", {"language": "en-US"})
        return normalize_tv(data)
