"""Intelligent header recognition for spreadsheet imports.

Spreadsheets exported from other tools use wildly different column names
for the same concept.  This module normalizes a raw header string and
maps it onto a canonical AnimeVault field, preferring exact matches over
aliases so an exact ``Title`` column always wins over a fuzzy match.

Unmapped columns are *reported* rather than silently dropped.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

# ── Canonical fields ──────────────────────────────────────────────

FIELD_TITLE = "title"
FIELD_TITLE_JA = "title_ja"
FIELD_TITLE_EN = "title_en"
FIELD_EPISODES = "episodes"
FIELD_EPISODES_WATCHED = "episodes_watched"
FIELD_STATUS = "status"
FIELD_TIER = "tier"
FIELD_REWATCHES = "rewatches"
FIELD_FAVORITE = "favorite"
FIELD_NOTES = "notes"
FIELD_FIRST_WATCHED = "first_watched"
FIELD_LAST_WATCHED = "last_watched"
FIELD_COMPLETED_DATE = "completed_date"
FIELD_PRIVACY = "privacy"
FIELD_MAL_ID = "mal_id"
FIELD_ANILIST_ID = "anilist_id"
FIELD_KITSU_ID = "kitsu_id"
FIELD_TMDB_ID = "tmdb_id"
FIELD_ANIDB_ID = "anidb_id"
FIELD_SYNOPSIS = "synopsis"
FIELD_GENRES = "genres"
FIELD_MEDIA_TYPE = "media_type"
FIELD_AIRING_STATUS = "airing_status"
FIELD_STUDIOS = "studios"
FIELD_DURATION = "duration"
FIELD_SEASON = "season"
FIELD_SEASON_YEAR = "season_year"
FIELD_AIRED_FROM = "aired_from"
FIELD_AIRED_TO = "aired_to"
FIELD_POSTER_URL = "poster_url"

#: Personal fields the user owns — import must never silently invent these.
PERSONAL_FIELDS = frozenset(
    {
        FIELD_STATUS,
        FIELD_TIER,
        FIELD_REWATCHES,
        FIELD_FAVORITE,
        FIELD_NOTES,
        FIELD_EPISODES_WATCHED,
        FIELD_FIRST_WATCHED,
        FIELD_LAST_WATCHED,
        FIELD_COMPLETED_DATE,
        FIELD_PRIVACY,
    }
)

# ── Alias tables ──────────────────────────────────────────────────

_ALIASES: dict[str, tuple[str, ...]] = {
    FIELD_TITLE: (
        "title", "anime title", "anime", "name", "anime name",
        "series", "series title", "show", "show title",
    ),
    FIELD_TITLE_JA: (
        "japanese title", "japanese", "jp title", "japanese name",
        "title ja", "title japanese", "jpn title", "jp name",
    ),
    FIELD_TITLE_EN: (
        "english title", "english", "en title", "title en",
        "title english", "eng title",
    ),
    FIELD_EPISODES: (
        "episodes", "total episodes", "episode count", "total ep",
        "eps", "episode_count", "ep count", "num episodes",
        "total episode", "episodes total",
    ),
    FIELD_EPISODES_WATCHED: (
        "episodes watched", "watched episodes", "episodes seen",
        "ep watched", "watched", "progress", "episodes completed",
        "completed episodes", "watched eps", "eps watched",
    ),
    FIELD_STATUS: (
        "status", "watch status", "watching status", "my status",
        "watchstate", "watch state", "state", "progress status",
    ),
    FIELD_TIER: (
        "tier", "rank", "anime tier", "personal tier", "rating tier",
        "my tier", "tier rank", "grade",
    ),
    FIELD_REWATCHES: (
        "rewatches", "rewatch", "rewatch count", "times watched",
        "times rewatched", "watched again", "rewatch_count",
        "times rewatch", "repeat count",
    ),
    FIELD_FAVORITE: (
        "favorite", "favourite", "is favorite", "starred", "fav",
        "is favourite", "liked",
    ),
    FIELD_NOTES: (
        "notes", "note", "comment", "comments", "personal notes",
        "my notes", "remarks", "memo",
    ),
    FIELD_FIRST_WATCHED: (
        "first watched", "started", "start date", "date started",
        "first watch date", "watched first", "first seen",
    ),
    FIELD_LAST_WATCHED: (
        "last watched", "last seen", "last watch date",
        "most recently watched", "last watched date",
    ),
    FIELD_COMPLETED_DATE: (
        "completed", "completion date", "finished date",
        "date completed", "completed at", "finish date",
    ),
    FIELD_PRIVACY: ("private", "privacy", "visibility", "is private"),
    FIELD_MAL_ID: (
        "mal id", "jikan id", "myanimelist id", "mal", "malid",
        "myanimelist", "mal_id",
    ),
    FIELD_ANILIST_ID: ("anilist id", "anilist", "anilist_id", "al id"),
    FIELD_KITSU_ID: ("kitsu id", "kitsu", "kitsu_id"),
    FIELD_TMDB_ID: ("tmdb id", "tmdb", "tmdb_id", "themoviedb id"),
    FIELD_ANIDB_ID: ("anidb id", "anidb", "anidb_id"),
    FIELD_SYNOPSIS: (
        "description", "synopsis", "summary", "plot", "overview",
        "desc", "story",
    ),
    FIELD_GENRES: ("genres", "genre", "tags", "categories", "themes"),
    FIELD_MEDIA_TYPE: ("type", "format", "media type", "media format", "show type"),
    FIELD_AIRING_STATUS: (
        "airing status", "air status", "broadcast status",
        "release status", "airing_state",
    ),
    FIELD_STUDIOS: ("studio", "studios", "studio name", "production", "producer"),
    FIELD_DURATION: ("duration", "episode duration", "runtime", "length", "ep length"),
    FIELD_SEASON: ("season", "season name"),
    FIELD_SEASON_YEAR: ("season year", "season_year"),
    FIELD_AIRED_FROM: (
        "first aired", "aired from", "release date", "start aired",
        "aired_from", "premiere", "aired start",
    ),
    FIELD_AIRED_TO: ("last aired", "aired to", "aired_to", "finale", "aired end"),
    FIELD_POSTER_URL: ("poster", "poster url", "cover", "cover url", "image", "image url"),
}

def normalize_header(raw: object) -> str:
    """Normalize a raw header cell into a comparable key.

    Lowercases, strips accents/whitespace, and collapses ``_``, ``-``
    and repeated spaces into a single space so ``"Total_Episodes"``,
    ``"total-episodes"`` and ``"  Total Episodes "`` all compare equal.
    """
    if raw is None:
        return ""
    text = str(raw)
    # Decompose accented characters (é → e) so "Café" == "Cafe".
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold().strip()
    # Collapse separators to single spaces.
    text = re.sub(r"[_\-\./\\]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# Rebuild the exact-match table now that normalize_header is defined.
_EXACT: dict[str, str] = {}
for _f, _names in _ALIASES.items():
    for _n in _names:
        _EXACT[normalize_header(_n)] = _f

# Reverse index for fuzzy fallback: token → field.
_TOKENS: dict[str, set[str]] = {}
for _f, _names in _ALIASES.items():
    for _n in _names:
        for _tok in normalize_header(_n).split():
            _TOKENS.setdefault(_tok, set()).add(_f)


# ── Result type ───────────────────────────────────────────────────

@dataclass
class ColumnMapping:
    """How one spreadsheet column maps onto the AnimeVault schema."""

    column_index: int
    raw_header: str
    field: Optional[str]
    normalized: str

    @property
    def mapped(self) -> bool:
        return self.field is not None


@dataclass
class MappingReport:
    """Result of mapping a full header row."""

    mappings: list[ColumnMapping] = field(default_factory=list)

    @property
    def mapped_fields(self) -> dict[str, int]:
        """Canonical field → column index, for mapped columns only."""
        return {m.field: m.column_index for m in self.mappings if m.mapped}

    @property
    def unmapped_columns(self) -> list[str]:
        """Raw headers that could not be recognised."""
        return [m.raw_header for m in self.mappings if not m.mapped]

    @property
    def mapped_columns(self) -> list[str]:
        return [m.raw_header for m in self.mappings if m.mapped]

    def column_for(self, field_name: str) -> Optional[int]:
        idx = self.mapped_fields.get(field_name)
        if idx is None:
            return None
        return self.mappings[idx].column_index if 0 <= idx < len(self.mappings) else None

    def field_for_column(self, column_index: int) -> Optional[str]:
        if 0 <= column_index < len(self.mappings):
            return self.mappings[column_index].field
        return None


def map_header(raw: object) -> Optional[str]:
    """Map a single raw header to a canonical field, or ``None``.

    Exact normalized matches win over alias/fuzzy matches.  Fuzzy
    matching only fires when a token is unambiguous across all fields,
    which avoids mapping e.g. ``"Type"`` from an unrelated column.
    """
    norm = normalize_header(raw)
    if not norm:
        return None

    # 1. Exact match on a known alias.
    if norm in _EXACT:
        return _EXACT[norm]

    # 2. Minor spelling variation on a single word (e.g. "tierr").
    # 3. Unambiguous token overlap.
    tokens = norm.split()
    candidates: set[str] = set()
    for tok in tokens:
        candidates |= _TOKENS.get(tok, set())
    if len(candidates) == 1:
        return next(iter(candidates))

    # 4. Fuzzy: every token maps to the same field.
    if tokens:
        per_token = [_TOKENS.get(tok, set()) for tok in tokens]
        common = set.intersection(*per_token) if per_token else set()
        if len(common) == 1:
            return next(iter(common))

    return None


def build_mapping(headers: list[object]) -> MappingReport:
    """Map a full header row, reporting unmapped columns explicitly."""
    report = MappingReport()
    for idx, raw in enumerate(headers):
        report.mappings.append(
            ColumnMapping(
                column_index=idx,
                raw_header="" if raw is None else str(raw),
                field=map_header(raw),
                normalized=normalize_header(raw),
            )
        )
    return report