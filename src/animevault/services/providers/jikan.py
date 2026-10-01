"""Jikan v4 (MyAnimeList) REST API provider.

Note: Jikan may return 504 during downtime.  All errors are classified and
handled without crashing the application or hammering the endpoint.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from .base import AnimeMetadata, BaseProvider, ProviderError

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.jikan.moe/v4"
_MIN_INTERVAL: float = 0.5   # seconds — Jikan allows ~3 req/sec


def _jikan_get(url: str, timeout: int = 12) -> dict:
    """Make a GET request to Jikan and return parsed JSON."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "AnimeVault/0.2",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        code = exc.code
        if code == 404:
            raise ProviderError("Jikan 404: not found", status_code=404, retryable=False)
        if code == 429:
            retry_after = int(exc.headers.get("Retry-After", "3"))
            raise ProviderError(
                f"Jikan rate limited (429) — retry after {retry_after}s",
                status_code=429,
                retryable=True,
            )
        if code in (500, 502, 503, 504):
            raise ProviderError(f"Jikan server error {code}", status_code=code, retryable=True)
        if code == 403:
            raise ProviderError("Jikan 403 Forbidden", status_code=403, retryable=False)
        raise ProviderError(f"Jikan HTTP {code}", status_code=code, retryable=False)
    except urllib.error.URLError as exc:
        raise ProviderError(f"Jikan network error: {exc}", retryable=True)
    except ProviderError:
        raise
    except Exception as exc:
        raise ProviderError(f"Jikan unexpected error: {exc}", retryable=False)


def _parse_duration_minutes(dur_str: str) -> int:
    """Parse '23 min per ep' or '1 hr 34 min' → integer minutes."""
    if not dur_str:
        return 0
    hr_m = re.search(r"(\d+)\s*hr", dur_str)
    mn_m = re.search(r"(\d+)\s*min", dur_str)
    return (int(hr_m.group(1)) if hr_m else 0) * 60 + (int(mn_m.group(1)) if mn_m else 0)


def _normalize_airing_status(status: str) -> str:
    s = (status or "").lower()
    if "finished" in s:
        return "FINISHED"
    if "currently airing" in s:
        return "RELEASING"
    if "not yet" in s:
        return "NOT_YET_RELEASED"
    return s.upper()


def normalize_entry(entry: dict) -> AnimeMetadata:
    """Convert a raw Jikan anime entry to :class:`AnimeMetadata`."""
    title = (entry.get("title") or "").strip()
    title_en = (entry.get("title_english") or "").strip()
    title_ja = (entry.get("title_japanese") or "").strip()

    # Collect alternate/synonym titles
    titles_raw = entry.get("titles") or []
    synonyms = []
    seen = {title.lower(), title_en.lower(), title_ja.lower()} - {""}
    for t in titles_raw:
        v = (t.get("title") or "").strip()
        if v and v.lower() not in seen:
            synonyms.append(v)
            seen.add(v.lower())

    # Poster
    images = entry.get("images") or {}
    jpg = images.get("jpg") or {}
    poster = jpg.get("large_image_url") or jpg.get("image_url") or ""

    # Dates
    aired = entry.get("aired") or {}
    aired_from = (aired.get("from") or "")[:10]
    aired_to   = (aired.get("to")   or "")[:10]

    # Genres (combine genres + themes + demographics)
    genre_sources = (
        (entry.get("genres") or [])
        + (entry.get("themes") or [])
        + (entry.get("demographics") or [])
    )
    genres = list({g.get("name", "") for g in genre_sources if g.get("name")})

    # Studios
    studios = [s["name"] for s in (entry.get("studios") or []) if s.get("name")]

    return AnimeMetadata(
        title=title,
        title_en=title_en,
        title_ja=title_ja,
        synonyms=synonyms,
        mal_id=entry.get("mal_id") or None,
        synopsis=(entry.get("synopsis") or "").strip(),
        media_type=(entry.get("type") or "").upper(),
        airing_status=_normalize_airing_status(entry.get("status") or ""),
        genres=genres,
        aired_from=aired_from,
        aired_to=aired_to,
        season=(entry.get("season") or "").upper(),
        season_year=entry.get("year") or None,
        episodes=int(entry.get("episodes") or 0),
        duration=_parse_duration_minutes(entry.get("duration") or ""),
        studios=studios,
        poster_url=poster,
        source_provider="jikan",
    )


class JikanProvider(BaseProvider):
    """Jikan v4 (MyAnimeList) REST API provider."""

    name = "jikan"

    def __init__(self) -> None:
        self._backoff_until: float = 0.0
        self._last_request: float = 0.0

    def _throttle(self) -> None:
        now = time.monotonic()
        if now < self._backoff_until:
            secs = int(self._backoff_until - now)
            raise ProviderError(f"Jikan in backoff for {secs}s", retryable=False)
        wait = _MIN_INTERVAL - (now - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def search(self, query: str, limit: int = 10) -> list[AnimeMetadata]:
        self._throttle()
        encoded = urllib.parse.quote(query.strip())
        url = f"{_BASE_URL}/anime?q={encoded}&limit={min(limit, 25)}&sfw=false"
        try:
            data = _jikan_get(url)
        except ProviderError as exc:
            if exc.status_code in (500, 502, 503, 504):
                self._backoff_until = time.monotonic() + 120.0  # 2-min backoff
                logger.warning("Jikan unavailable (%s), backing off 2 minutes", exc.status_code)
            raise
        entries = data.get("data") or []
        results = []
        for e in entries:
            try:
                results.append(normalize_entry(e))
            except Exception as exc:
                logger.debug("Jikan: skipping malformed entry: %s", exc)
        return results

    def get_details(self, provider_id: str) -> AnimeMetadata:
        self._throttle()
        url = f"{_BASE_URL}/anime/{provider_id}/full"
        data = _jikan_get(url)
        entry = data.get("data")
        if not entry:
            raise ProviderError(f"Jikan: no data for id={provider_id}", retryable=False)
        return normalize_entry(entry)

    def is_available(self) -> bool:
        return time.monotonic() >= self._backoff_until
