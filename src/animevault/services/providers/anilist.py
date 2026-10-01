"""AniList GraphQL API provider (primary — confirmed working)."""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from typing import Optional

from .base import AnimeMetadata, BaseProvider, ProviderError

logger = logging.getLogger(__name__)

_ANILIST_URL = "https://graphql.anilist.co"

# ── GraphQL queries ───────────────────────────────────────────────

_SEARCH_QUERY = """
query ($search: String, $page: Int, $perPage: Int) {
  Page(page: $page, perPage: $perPage) {
    media(search: $search, type: ANIME) {
      id idMal
      title { romaji english native }
      synonyms
      episodes status format
      description(asHtml: false)
      genres duration season seasonYear
      startDate { year month day }
      endDate   { year month day }
      studios(isMain: true) { nodes { name } }
      coverImage { large medium }
    }
  }
}
"""

_DETAILS_QUERY = """
query ($id: Int) {
  Media(id: $id, type: ANIME) {
    id idMal
    title { romaji english native }
    synonyms
    episodes status format
    description(asHtml: false)
    genres duration season seasonYear
    startDate { year month day }
    endDate   { year month day }
    studios(isMain: true) { nodes { name } }
    coverImage { large medium }
  }
}
"""


# ── Helpers ───────────────────────────────────────────────────────

def _strip_html(text: str) -> str:
    """Remove HTML tags and decode common HTML entities."""
    text = re.sub(r"<[^>]+>", "", text or "")
    for ent, rep in [
        ("&nbsp;", " "), ("&#039;", "'"), ("&amp;", "&"),
        ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'),
    ]:
        text = text.replace(ent, rep)
    return text.strip()


def _format_date(d: Optional[dict]) -> str:
    """AniList date dict → ISO string or ''."""
    if not d:
        return ""
    y = d.get("year")
    if not y:
        return ""
    m = d.get("month")
    day = d.get("day")
    parts = [str(y)]
    if m:
        parts.append(f"{m:02d}")
        if day:
            parts.append(f"{day:02d}")
    return "-".join(parts)


def normalize_media(media: dict) -> AnimeMetadata:
    """Convert a raw AniList media dict to :class:`AnimeMetadata`."""
    titles = media.get("title") or {}
    title_romaji = (titles.get("romaji") or "").strip()
    title_en = (titles.get("english") or "").strip()
    title_ja = (titles.get("native") or "").strip()
    title = title_romaji or title_en or title_ja

    studios_nodes = ((media.get("studios") or {}).get("nodes")) or []
    studios = [n["name"] for n in studios_nodes if n.get("name")]

    cover = media.get("coverImage") or {}
    poster = cover.get("large") or cover.get("medium") or ""

    synopsis = _strip_html(media.get("description") or "")

    return AnimeMetadata(
        title=title,
        title_en=title_en,
        title_ja=title_ja,
        title_romaji=title_romaji,
        synonyms=list(media.get("synonyms") or []),
        mal_id=media.get("idMal") or None,
        anilist_id=int(media["id"]) if media.get("id") else None,
        synopsis=synopsis,
        media_type=(media.get("format") or "").upper(),
        airing_status=(media.get("status") or "").upper(),
        genres=list(media.get("genres") or []),
        aired_from=_format_date(media.get("startDate")),
        aired_to=_format_date(media.get("endDate")),
        season=(media.get("season") or "").upper(),
        season_year=media.get("seasonYear") or None,
        episodes=int(media.get("episodes") or 0),
        duration=int(media.get("duration") or 0),
        studios=studios,
        poster_url=poster,
        source_provider="anilist",
    )


# ── Provider ─────────────────────────────────────────────────────

class AniListProvider(BaseProvider):
    """AniList GraphQL API provider."""

    name = "anilist"

    def __init__(self) -> None:
        self._backoff_until: float = 0.0

    def _post(self, query: str, variables: dict) -> dict:
        """Send a GraphQL POST and return the parsed JSON body."""
        now = time.monotonic()
        if now < self._backoff_until:
            secs = int(self._backoff_until - now)
            raise ProviderError(
                f"AniList is in backoff for {secs}s",
                retryable=False,
            )

        body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
        req = urllib.request.Request(
            _ANILIST_URL,
            data=body,
            headers={
                "User-Agent": "AnimeVault/0.2",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            code = exc.code
            if code == 403:
                self._backoff_until = time.monotonic() + 300.0  # 5 min
                logger.warning("AniList returned 403 — backing off 5 minutes")
                raise ProviderError("AniList 403 Forbidden", status_code=403, retryable=False)
            if code == 429:
                retry_after = int(exc.headers.get("Retry-After", "60"))
                self._backoff_until = time.monotonic() + float(retry_after)
                raise ProviderError(
                    f"AniList rate limited (429) — retry after {retry_after}s",
                    status_code=429,
                    retryable=True,
                )
            if code in (500, 502, 503, 504):
                raise ProviderError(f"AniList server error {code}", status_code=code, retryable=True)
            raise ProviderError(f"AniList HTTP {code}", status_code=code, retryable=False)
        except urllib.error.URLError as exc:
            raise ProviderError(f"AniList network error: {exc}", retryable=True)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"AniList unexpected error: {exc}", retryable=False)

    def search(self, query: str, limit: int = 10) -> list[AnimeMetadata]:
        data = self._post(
            _SEARCH_QUERY,
            {"search": query.strip(), "page": 1, "perPage": min(limit, 25)},
        )
        media_list = (data.get("data") or {}).get("Page", {}).get("media") or []
        results = []
        for m in media_list:
            try:
                results.append(normalize_media(m))
            except Exception as exc:
                logger.debug("AniList: skipping malformed result: %s", exc)
        return results

    def get_details(self, provider_id: str) -> AnimeMetadata:
        data = self._post(_DETAILS_QUERY, {"id": int(provider_id)})
        media = (data.get("data") or {}).get("Media")
        if not media:
            raise ProviderError(
                f"AniList: no media found for id={provider_id}",
                retryable=False,
            )
        return normalize_media(media)

    def is_available(self) -> bool:
        return time.monotonic() >= self._backoff_until
