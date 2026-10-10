"""Kitsu JSON:API provider (no API key required for read access)."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from .base import AnimeMetadata, BaseProvider, ProviderError, parse_retry_after

logger = logging.getLogger(__name__)

_BASE_URL = "https://kitsu.app/api/edge"
_HEADERS = {
    "User-Agent": "AnimeVault/0.2",
    "Accept": "application/vnd.api+json",
}
# Sparse fieldset to reduce response size
_FIELDS = (
    "canonicalTitle,titles,synopsis,episodeCount,episodeLength,"
    "status,startDate,endDate,posterImage,subtype"
)


def _kitsu_get(url: str, timeout: int = 12) -> dict:
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        code = exc.code
        if code == 404:
            raise ProviderError("Kitsu 404: not found", status_code=404, retryable=False)
        if code == 429:
            retry_after = parse_retry_after(exc.headers.get("Retry-After"), 60.0)
            raise ProviderError(
                "Kitsu rate limited (429)",
                status_code=429,
                retryable=True,
                retry_after=retry_after,
                provider="kitsu",
            )
        if code in (500, 502, 503, 504):
            raise ProviderError(f"Kitsu server error {code}", status_code=code, retryable=True)
        if code == 403:
            raise ProviderError("Kitsu 403 Forbidden", status_code=403, retryable=False)
        raise ProviderError(f"Kitsu HTTP {code}", status_code=code, retryable=False)
    except urllib.error.URLError as exc:
        raise ProviderError(f"Kitsu network error: {exc}", retryable=True)
    except ProviderError:
        raise
    except Exception as exc:
        raise ProviderError(f"Kitsu unexpected error: {exc}", retryable=False)


def _normalize_status(kitsu_status: str) -> str:
    mapping = {
        "finished": "FINISHED",
        "current": "RELEASING",
        "upcoming": "NOT_YET_RELEASED",
        "tba": "NOT_YET_RELEASED",
    }
    return mapping.get((kitsu_status or "").lower(), (kitsu_status or "").upper())


def normalize_entry(entry: dict) -> AnimeMetadata:
    """Convert a raw Kitsu anime entry to :class:`AnimeMetadata`."""
    attrs = entry.get("attributes") or {}
    titles = attrs.get("titles") or {}

    canonical = (attrs.get("canonicalTitle") or "").strip()
    title_en = (titles.get("en") or titles.get("en_us") or "").strip()
    title_ja = (titles.get("ja_jp") or "").strip()
    title = canonical or title_en or title_ja

    synopsis = (attrs.get("synopsis") or "").strip()

    poster_img = attrs.get("posterImage") or {}
    poster = (
        poster_img.get("original")
        or poster_img.get("large")
        or poster_img.get("medium")
        or ""
    )

    episodes = int(attrs.get("episodeCount") or 0)
    duration = int(attrs.get("episodeLength") or 0)
    start_date = (attrs.get("startDate") or "")[:10]
    end_date   = (attrs.get("endDate")   or "")[:10]
    airing_status = _normalize_status(attrs.get("status") or "")

    subtype = (attrs.get("subtype") or "").upper()

    season_year: Optional[int] = None
    if start_date and len(start_date) >= 4:
        try:
            season_year = int(start_date[:4])
        except ValueError:
            pass

    kitsu_id = str(entry.get("id") or "")

    return AnimeMetadata(
        title=title,
        title_en=title_en,
        title_ja=title_ja,
        kitsu_id=kitsu_id if kitsu_id else None,
        synopsis=synopsis,
        media_type=subtype,
        airing_status=airing_status,
        aired_from=start_date,
        aired_to=end_date,
        season_year=season_year,
        episodes=episodes,
        duration=duration,
        poster_url=poster,
        source_provider="kitsu",
    )


class KitsuProvider(BaseProvider):
    """Kitsu JSON:API provider."""

    name = "kitsu"

    def __init__(self) -> None:
        self._backoff_until: float = 0.0

    def search(self, query: str, limit: int = 10) -> list[AnimeMetadata]:
        if time.monotonic() < self._backoff_until:
            raise ProviderError("Kitsu in backoff", retryable=False)

        encoded = urllib.parse.quote(query.strip())
        url = (
            f"{_BASE_URL}/anime"
            f"?filter[text]={encoded}"
            f"&page[limit]={min(limit, 20)}"
            f"&fields[anime]={_FIELDS}"
        )
        try:
            data = _kitsu_get(url)
        except ProviderError as exc:
            if exc.status_code in (500, 502, 503, 504):
                self._backoff_until = time.monotonic() + 120.0
                logger.warning("Kitsu unavailable (%s), backing off", exc.status_code)
            raise

        entries = data.get("data") or []
        results = []
        for e in entries:
            try:
                results.append(normalize_entry(e))
            except Exception as exc:
                logger.debug("Kitsu: skipping malformed entry: %s", exc)
        return results

    def get_details(self, provider_id: str) -> AnimeMetadata:
        if time.monotonic() < self._backoff_until:
            raise ProviderError("Kitsu in backoff", retryable=False)
        url = f"{_BASE_URL}/anime/{provider_id}?fields[anime]={_FIELDS}"
        data = _kitsu_get(url)
        entry = data.get("data")
        if not entry:
            raise ProviderError(f"Kitsu: no data for id={provider_id}", retryable=False)
        return normalize_entry(entry)

    def is_available(self) -> bool:
        return time.monotonic() >= self._backoff_until
