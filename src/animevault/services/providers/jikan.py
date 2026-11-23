"""Jikan v4 (MyAnimeList) REST API provider.

Note: Jikan may return 504 during downtime.  All errors are classified and
handled without crashing the application or hammering the endpoint.
"""

from __future__ import annotations

import json
import logging
import re
import time
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from .base import AnimeMetadata, BaseProvider, ProviderError, parse_retry_after

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.jikan.moe/v4"
_MIN_INTERVAL: float = 0.5   # seconds — Jikan allows ~3 req/sec
_RATE_LOCK = threading.Lock()
_GLOBAL_LAST_REQUEST = 0.0


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


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
            retry_after = parse_retry_after(exc.headers.get("Retry-After"), 3.0)
            raise ProviderError(
                f"Jikan rate limited (429)",
                status_code=429,
                retryable=True,
                retry_after=retry_after,
                provider="jikan",
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
        global _GLOBAL_LAST_REQUEST
        now = time.monotonic()
        if now < self._backoff_until:
            secs = int(self._backoff_until - now)
            raise ProviderError(f"Jikan in backoff for {secs}s", retryable=False)
        # One limiter shared by every provider instance/thread in this process.
        with _RATE_LOCK:
            wait = _MIN_INTERVAL - (time.monotonic() - _GLOBAL_LAST_REQUEST)
            if wait > 0:
                time.sleep(wait)
            _GLOBAL_LAST_REQUEST = time.monotonic()
            self._last_request = _GLOBAL_LAST_REQUEST

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

    def _get_with_retry(self, url: str, attempts: int = 3) -> dict:
        """Throttle and retry only temporary Jikan failures with bounded backoff."""
        for attempt in range(max(1, attempts)):
            self._throttle()
            try:
                payload = _jikan_get(url)
                if not isinstance(payload, dict):
                    raise ProviderError("Jikan returned an invalid response", retryable=False, provider="jikan")
                return payload
            except ProviderError as exc:
                if not exc.retryable or attempt + 1 >= attempts:
                    raise
                delay = exc.retry_after if exc.retry_after is not None else 0.75 * (2 ** attempt)
                time.sleep(min(15.0, max(0.5, float(delay))))
        return {}

    def get_recommendations(self, mal_id: int, limit: int = 10) -> list[tuple[AnimeMetadata, int]]:
        """Return MAL recommendation relationships with their community votes."""
        data = self._get_with_retry(f"{_BASE_URL}/anime/{int(mal_id)}/recommendations")
        entries = data.get("data")
        if not isinstance(entries, list):
            return []
        results: list[tuple[AnimeMetadata, int]] = []
        for relation in entries:
            if not isinstance(relation, dict) or not isinstance(relation.get("entry"), dict):
                continue
            try:
                entry = relation["entry"]
                meta = normalize_entry(entry)
                if not meta.mal_id:
                    meta.mal_id = int(entry.get("mal_id") or 0) or None
                votes = int(relation.get("votes") or 0)
                results.append((meta, max(0, votes)))
            except (TypeError, ValueError, AttributeError) as exc:
                logger.debug("Jikan: skipping malformed recommendation record: %s", exc)
        return sorted(results, key=lambda pair: pair[1], reverse=True)[:max(1, min(int(limit), 25))]

    def get_genre_catalogue(self) -> list[tuple[int, str]]:
        """Return Jikan's real MAL anime genre IDs and names."""
        payload = self._get_with_retry(f"{_BASE_URL}/genres/anime")
        entries = payload.get("data")
        if not isinstance(entries, list):
            raise ProviderError("Jikan genre catalogue returned an invalid response", retryable=False, provider="jikan")
        genres = []
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("name"):
                continue
            try:
                genre_id = int(entry.get("mal_id"))
            except (TypeError, ValueError):
                continue
            if genre_id > 0:
                genres.append((genre_id, str(entry["name"]).strip()))
        return genres

    def get_anime_by_genre(self, genre_id: int, *, page: int = 1, limit: int = 15) -> tuple[list[AnimeMetadata], bool]:
        """Fetch a bounded, score-sorted page for one catalogue genre ID."""
        genre_id = int(genre_id)
        page = max(1, min(int(page), 1000))
        limit = max(1, min(int(limit), 25))
        if genre_id <= 0:
            raise ValueError("genre_id must be positive")
        params = urllib.parse.urlencode({
            "genres": genre_id,
            "order_by": "score",
            "sort": "desc",
            "page": page,
            "limit": limit,
            "sfw": "true",
        })
        payload = self._get_with_retry(f"{_BASE_URL}/anime?{params}")
        entries = payload.get("data")
        if not isinstance(entries, list):
            raise ProviderError("Jikan genre discovery returned an invalid response", retryable=False, provider="jikan")
        valid_entries = [entry for entry in entries if isinstance(entry, dict) and entry.get("mal_id") and entry.get("title")]
        valid_entries.sort(
            key=lambda entry: (
                -(float(entry.get("score") or 0.0) if _is_number(entry.get("score")) else 0.0),
                int(entry.get("rank") or 10**9) if _is_int(entry.get("rank")) else 10**9,
            )
        )
        results = []
        for entry in valid_entries:
            try:
                results.append(normalize_entry(entry))
            except (TypeError, ValueError, AttributeError) as exc:
                logger.debug("Jikan: skipping malformed genre entry: %s", exc)
        pagination = payload.get("pagination")
        has_next = bool(pagination.get("has_next_page")) if isinstance(pagination, dict) else False
        return results, has_next

    def get_details(self, provider_id: str) -> AnimeMetadata:
        url = f"{_BASE_URL}/anime/{provider_id}/full"
        data = self._get_with_retry(url)
        entry = data.get("data")
        if not entry:
            raise ProviderError(f"Jikan: no data for id={provider_id}", retryable=False)
        return normalize_entry(entry)

    def is_available(self) -> bool:
        return time.monotonic() >= self._backoff_until
