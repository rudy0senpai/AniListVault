"""AniList provider for literature (Manga / Manhwa / Manhua).

AniList's GraphQL API exposes a ``MANGA`` media type that carries the
fields literature needs — chapters, volumes, publication status and,
crucially, ``countryOfOrigin``, which is what lets us tell a manga from a
manhwa or manhua using provider data instead of guessing from the title.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

from animevault.media_types import (
    LITERATURE_COMIC_FORMATS,
    MEDIA_ANIME,
    MEDIA_MANGA,
    category_from_origin,
    normalize_category,
    normalize_format,
)
from animevault.services.providers.anilist import (
    _ANILIST_URL,
    _format_date,
    _strip_html,
)

logger = logging.getLogger(__name__)

# ── Queries ───────────────────────────────────────────────────────

_LIT_FIELDS = """
      id idMal
      title { romaji english native }
      synonyms
      description(asHtml: false)
      format
      status
      countryOfOrigin
      chapters volumes
      genres
      tags { name rank }
      startDate { year month day }
      endDate   { year month day }
      coverImage { large medium }
      staff(perPage: 8) {
        edges {
          role
          node { name { full } }
        }
      }
"""

_LIT_SEARCH_QUERY = """
query ($search: String, $perPage: Int) {
  Page(page: 1, perPage: $perPage) {
    media(search: $search, type: MANGA) {
""" + _LIT_FIELDS + """
    }
  }
}
"""

_LIT_BY_ID_QUERY = """
query ($id: Int) {
  Media(id: $id, type: MANGA) {
""" + _LIT_FIELDS + """
  }
}
"""

#: AniList staff roles mapped to our two author fields.
_AUTHOR_ROLES = {"Story & Art", "Story", "Art", "Writer", "Author", "Artist"}


# ── Normalized record ─────────────────────────────────────────────

@dataclass
class LiteratureMetadata:
    """Canonical literature metadata from any provider."""

    title: str = ""
    title_en: str = ""
    title_native: str = ""
    synonyms: list[str] = field(default_factory=list)
    category: str = MEDIA_MANGA
    format: str = ""
    status: str = ""
    pub_status: str = ""
    synopsis: str = ""
    genres: list[str] = field(default_factory=list)
    authors: list[str] = field(default_factory=list)
    artists: list[str] = field(default_factory=list)
    serialization: str = ""
    chapters: int = 0
    volumes: int = 0
    started_at: str = ""
    ended_at: str = ""
    origin_country: str = ""
    cover_url: str = ""
    anilist_id: Optional[int] = None
    mal_id: Optional[int] = None
    kitsu_id: Optional[str] = None
    source_provider: str = "anilist"

    def display_title(self) -> str:
        return self.title or self.title_en or self.title_native or "Unknown"


def normalize_literature(media: dict) -> LiteratureMetadata:
    """Convert an AniList MANGA payload into :class:`LiteratureMetadata`."""
    titles = media.get("title") or {}
    romaji = (titles.get("romaji") or "").strip()
    english = (titles.get("english") or "").strip()
    native = (titles.get("native") or "").strip()

    fmt = normalize_format(media.get("format"))
    origin = (media.get("countryOfOrigin") or "").strip().upper()

    # Category comes from provider data: country of origin first, then the
    # format AniList reports.  Never inferred from the title.
    category = category_from_origin(origin)
    if category is None:
        if fmt == "MANGA":
            category = MEDIA_MANGA
        elif fmt in LITERATURE_COMIC_FORMATS:
            category = MEDIA_MANGA
        else:
            category = MEDIA_MANGA

    # Genres + high-rank tags (tags carry the fine-grained themes).
    genres: list[str] = list(media.get("genres") or [])
    tags = media.get("tags") or []
    ranked = sorted(
        (t for t in tags if isinstance(t, dict) and t.get("rank")),
        key=lambda t: t.get("rank", 99),
    )
    for t in ranked:
        name = (t.get("name") or "").strip()
        # Only thematic tags; skip demographic/format noise.
        if name and name not in genres and len(genres) < 20:
            genres.append(name)

    authors: list[str] = []
    artists: list[str] = []
    edges = ((media.get("staff") or {}).get("edges")) or []
    for edge in edges:
        role = (edge.get("role") or "").strip()
        node_name = (((edge.get("node") or {}).get("name")) or {}).get("full")
        if not node_name:
            continue
        if role in _AUTHOR_ROLES:
            bucket = authors if role in ("Story", "Story & Art", "Writer", "Author") else artists
            if node_name not in bucket:
                bucket.append(node_name)
        # Cover / Chief Director / Other roles are not credited here.

    cover = media.get("coverImage") or {}
    cover_url = cover.get("large") or cover.get("medium") or ""

    return LiteratureMetadata(
        title=romaji or english or native,
        title_en=english,
        title_native=native,
        synonyms=list(media.get("synonyms") or []),
        category=category,
        format=fmt,
        status=normalize_format(media.get("status")),
        pub_status=normalize_format(media.get("status")),
        synopsis=_strip_html(media.get("description") or ""),
        genres=genres,
        authors=authors,
        artists=artists,
        chapters=int(media.get("chapters") or 0),
        volumes=int(media.get("volumes") or 0),
        started_at=_format_date(media.get("startDate")),
        ended_at=_format_date(media.get("endDate")),
        origin_country=origin,
        cover_url=cover_url,
        anilist_id=int(media["id"]) if media.get("id") else None,
        mal_id=media.get("idMal") or None,
    )


# ── Provider ──────────────────────────────────────────────────────

class AniListLiteratureProvider:
    """Fetches manga / manhwa / manhua metadata from AniList."""

    name = "anilist-literature"

    def __init__(self) -> None:
        self._backoff_until: float = 0.0

    def is_available(self) -> bool:
        return time.monotonic() >= self._backoff_until

    def _post(self, query: str, variables: dict) -> dict:
        """Send a GraphQL query and return the ``data`` object (or {})."""
        if not self.is_available():
            logger.debug("AniList literature provider in backoff")
            return {}

        body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
        req = urllib.request.Request(
            _ANILIST_URL,
            data=body,
            headers={
                "User-Agent": "AnimeVault/0.3",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data.get("data") or {}
        except urllib.error.HTTPError as exc:
            if exc.code == 403:
                self._backoff_until = time.monotonic() + 300.0
                logger.warning("AniList 403 on literature query — backing off 5 minutes")
            elif exc.code == 429:
                retry_after = int(exc.headers.get("Retry-After", "60"))
                self._backoff_until = time.monotonic() + float(retry_after)
                logger.warning("AniList rate limited literature query")
            else:
                logger.warning("AniList literature HTTP %s", exc.code)
            return {}
        except Exception as exc:
            logger.warning("AniList literature query failed: %s", exc)
            return {}

    def search(self, query: str, limit: int = 15) -> list[LiteratureMetadata]:
        text = (query or "").strip()
        if not text:
            return []
        data = self._post(
            _LIT_SEARCH_QUERY, {"search": text, "perPage": min(limit, 25)}
        )
        media = ((data.get("Page") or {}).get("media")) or []
        out: list[LiteratureMetadata] = []
        for m in media:
            try:
                meta = normalize_literature(m)
            except Exception as exc:
                logger.debug("Skipping malformed literature result: %s", exc)
                continue
            # Offer comics; novels are a different medium entirely.
            if meta.format and meta.format not in LITERATURE_COMIC_FORMATS:
                continue
            out.append(meta)
        return out

    def get_details(self, provider_id: str) -> Optional[LiteratureMetadata]:
        data = self._post(_LIT_BY_ID_QUERY, {"id": int(provider_id)})
        media = data.get("Media")
        if not media:
            return None
        try:
            return normalize_literature(media)
        except Exception as exc:
            logger.warning("Could not normalize AniList literature id=%s: %s", provider_id, exc)
            return None