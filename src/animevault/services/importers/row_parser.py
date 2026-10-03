"""Turn mapped spreadsheet rows into validated Anime drafts.

Parsing is deliberately separate from persistence so a whole file can be
validated (and previewed) before a single row is written.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from animevault.media_types import normalize_category
from animevault.models.anime import VALID_STATUSES
from animevault.services.importers.column_mapper import (
    FIELD_AIRING_STATUS,
    FIELD_ANIDB_ID,
    FIELD_ANILIST_ID,
    FIELD_ARTISTS,
    FIELD_AUTHORS,
    FIELD_CATEGORY,
    FIELD_CHAPTERS,
    FIELD_CHAPTERS_READ,
    FIELD_COMPLETED_DATE,
    FIELD_DURATION,
    FIELD_ENDED_AT,
    FIELD_EPISODES,
    FIELD_EPISODES_WATCHED,
    FIELD_FAVORITE,
    FIELD_FIRST_WATCHED,
    FIELD_GENRES,
    FIELD_KITSU_ID,
    FIELD_LAST_WATCHED,
    FIELD_MAL_ID,
    FIELD_MEDIA_TYPE,
    FIELD_NOTES,
    FIELD_ORIGIN_COUNTRY,
    FIELD_POSTER_URL,
    FIELD_PRIVACY,
    FIELD_PUB_STATUS,
    FIELD_REWATCHES,
    FIELD_SEASON,
    FIELD_SEASON_YEAR,
    FIELD_SERIALIZATION,
    FIELD_STARTED_AT,
    FIELD_STATUS,
    FIELD_STUDIOS,
    FIELD_SYNONYMS,
    FIELD_SYNOPSIS,
    FIELD_TIER,
    FIELD_TITLE,
    FIELD_TITLE_EN,
    FIELD_TITLE_JA,
    FIELD_TITLE_NATIVE,
    FIELD_TMDB_ID,
    FIELD_VOLUMES,
    MappingReport,
)
from animevault.tiers import InvalidTierError, normalize_tier

logger = logging.getLogger(__name__)

#: Spellings users write for each status value.
_STATUS_SYNONYMS: dict[str, str] = {
    "watching": "watching",
    "watch": "watching",
    "currently watching": "watching",
    "in progress": "watching",
    "completed": "completed",
    "complete": "completed",
    "finished": "completed",
    "done": "completed",
    "on hold": "on_hold",
    "on_hold": "on_hold",
    "onhold": "on_hold",
    "paused": "on_hold",
    "hold": "on_hold",
    "dropped": "dropped",
    "drop": "dropped",
    "abandoned": "dropped",
    "plan to watch": "plan_to_watch",
    "plan_to_watch": "plan_to_watch",
    "planned": "plan_to_watch",
    "plan": "plan_to_watch",
    "not started": "plan_to_watch",
    "": "plan_to_watch",
}

_TRUE_VALUES = {"1", "true", "yes", "y", "t", "✓", "✔", "x", "star", "starred"}
_FALSE_VALUES = {"0", "false", "no", "n", "f", "", "-", "—", "null", "none"}


class RowErrorKind:
    """Kinds of row-level import problem."""

    MISSING_TITLE = "missing_title"
    INVALID_TIER = "invalid_tier"
    INVALID_STATUS = "invalid_status"
    INVALID_NUMBER = "invalid_number"


@dataclass
class RowError:
    """A problem found in one spreadsheet row."""

    row_number: int          # 1-based, including the header row
    kind: str
    message: str
    raw_value: Any = None

    def as_dict(self) -> dict:
        return {
            "row": self.row_number,
            "kind": self.kind,
            "message": self.message,
            "value": self.raw_value,
        }


@dataclass
class AnimeDraft:
    """A parsed but not-yet-persisted anime row."""

    row_number: int
    title: str
    title_ja: str = ""
    title_en: str = ""
    episodes: int = 0
    episodes_watched: int = 0
    status: str = "plan_to_watch"
    tier: Optional[str] = None
    rewatches: int = 0
    favorite: bool = False
    notes: str = ""
    first_watched: str = ""
    last_watched: str = ""
    completed_date: str = ""
    privacy: str = "public"

    # Metadata (optional in the file)
    synopsis: str = ""
    genres: list[str] = field(default_factory=list)
    studios: list[str] = field(default_factory=list)
    media_type: str = ""
    airing_status: str = ""
    duration: int = 0
    season: str = ""
    season_year: Optional[int] = None
    poster_url: str = ""
    mal_id: Optional[int] = None
    anilist_id: Optional[int] = None
    kitsu_id: Optional[str] = None
    tmdb_id: Optional[int] = None
    anidb_id: Optional[int] = None

    # Literature (manga / manhwa / manhua)
    category: str = ""
    title_native: str = ""
    synonyms: list[str] = field(default_factory=list)
    chapters: int = 0
    chapters_read: int = 0
    volumes: int = 0
    authors: list[str] = field(default_factory=list)
    artists: list[str] = field(default_factory=list)
    serialization: str = ""
    pub_status: str = ""
    origin_country: str = ""
    started_at: str = ""
    ended_at: str = ""

    @property
    def is_literature(self) -> bool:
        """Whether this row describes a comic rather than an anime."""
        from animevault.media_types import is_literature as _is_lit

        return bool(self.category) and _is_lit(self.category)

    def dedupe_key(self) -> str:
        """Identity used for in-file duplicate detection."""
        return (self.title or "").strip().casefold()


# ── Scalar coercion ───────────────────────────────────────────────

def _to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _to_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().replace(",", "")
    # Tolerate "12 / 24" and "ep 12".
    if "/" in text:
        text = text.split("/")[0].strip()
    digits = "".join(ch for ch in text if ch.isdigit() or ch == "-")
    if not digits:
        return default
    try:
        return int(digits)
    except ValueError:
        return default


def _to_optional_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    text = _to_text(value)
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().casefold()
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    # Any other non-empty text counts as "yes".
    return bool(text)


def _to_list(value: Any) -> list[str]:
    """Split a cell into a list: JSON array, or comma/semicolon separated."""
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]

    text = str(value).strip()
    # A JSON array as written by some exporters.
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [p.strip().strip('"').strip("'") for p in inner.split(",") if p.strip()]

    parts: list[str] = []
    for chunk in text.replace(";", ",").split(","):
        c = chunk.strip()
        if c:
            parts.append(c)
    return parts


def normalize_status(value: Any) -> Optional[str]:
    """Map a raw status cell onto a canonical status, or ``None``."""
    text = _to_text(value).casefold()
    if text in _STATUS_SYNONYMS:
        return _STATUS_SYNONYMS[text]
    # Try the underscore/space-insensitive form.
    alt = text.replace(" ", "_").replace("-", "_")
    if alt in _STATUS_SYNONYMS:
        return _STATUS_SYNONYMS[alt]
    if text.replace("_", " ") in _STATUS_SYNONYMS:
        return _STATUS_SYNONYMS[text.replace("_", " ")]
    return None


# ── Row parsing ───────────────────────────────────────────────────

@dataclass
class ParsedRows:
    """Result of parsing a spreadsheet's data rows."""

    drafts: list[AnimeDraft] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
    invalid_tiers: list[RowError] = field(default_factory=list)

    @property
    def total_rows(self) -> int:
        return len(self.drafts) + len(self.errors)

    def error_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for e in self.errors:
            counts[e.kind] = counts.get(e.kind, 0) + 1
        return counts


def parse_rows(
    rows: list[list[Any]],
    report: MappingReport,
    *,
    start_row_number: int = 2,
    invalid_tier_policy: str = "unassigned",
) -> ParsedRows:
    """Parse data rows into drafts, collecting per-row errors.

    Parameters
    ----------
    rows:
        Data rows (header excluded).
    report:
        The header mapping produced by ``build_mapping``.
    start_row_number:
        Spreadsheet row number of the first data row (for error messages).
    invalid_tier_policy:
        ``"unassigned"`` (default) drops an invalid tier but keeps the
        row; ``"invalid"`` rejects the whole row.
    """
    result = ParsedRows()
    fields_map = report.mapped_fields

    for offset, raw_row in enumerate(rows):
        row_num = start_row_number + offset
        if not any(_to_text(v) for v in raw_row):
            continue  # skip entirely blank rows

        def cell(field_name: str) -> Any:
            idx = fields_map.get(field_name)
            if idx is None or idx >= len(raw_row):
                return None
            return raw_row[idx]

        title = _to_text(cell(FIELD_TITLE))
        if not title:
            result.errors.append(
                RowError(row_num, RowErrorKind.MISSING_TITLE, "Missing title")
            )
            continue

        draft = AnimeDraft(row_number=row_num, title=title)
        draft.title_ja = _to_text(cell(FIELD_TITLE_JA))
        draft.title_en = _to_text(cell(FIELD_TITLE_EN))
        draft.episodes = _to_int(cell(FIELD_EPISODES))
        draft.episodes_watched = _to_int(cell(FIELD_EPISODES_WATCHED))
        draft.rewatches = _to_int(cell(FIELD_REWATCHES))
        draft.favorite = _to_bool(cell(FIELD_FAVORITE))
        draft.notes = _to_text(cell(FIELD_NOTES))
        draft.first_watched = _to_text(cell(FIELD_FIRST_WATCHED))
        draft.last_watched = _to_text(cell(FIELD_LAST_WATCHED))
        draft.completed_date = _to_text(cell(FIELD_COMPLETED_DATE))

        privacy = _to_text(cell(FIELD_PRIVACY)).casefold()
        if privacy in ("private", "hidden", "secret"):
            draft.privacy = "private"
        elif privacy in ("public", "", "shared", "visible"):
            draft.privacy = "public"
        else:
            draft.privacy = privacy

        # ── Status ──────────────────────────────────────────────
        raw_status = cell(FIELD_STATUS)
        if raw_status is not None and _to_text(raw_status):
            status = normalize_status(raw_status)
            if status is None:
                result.errors.append(
                    RowError(
                        row_num,
                        RowErrorKind.INVALID_STATUS,
                        f"Unrecognized status: {_to_text(raw_status)!r}",
                        raw_status,
                    )
                )
                status = "plan_to_watch"
            draft.status = status

        # ── Tier ────────────────────────────────────────────────
        raw_tier = cell(FIELD_TIER)
        if raw_tier is not None and _to_text(raw_tier):
            try:
                draft.tier = normalize_tier(raw_tier)
            except InvalidTierError:
                err = RowError(
                    row_num,
                    RowErrorKind.INVALID_TIER,
                    f"Invalid tier value: {_to_text(raw_tier)!r}",
                    raw_tier,
                )
                result.invalid_tiers.append(err)
                if invalid_tier_policy == "invalid":
                    result.errors.append(err)
                    continue
                draft.tier = None  # unassigned

        # ── Metadata (optional) ─────────────────────────────────
        draft.synopsis = _to_text(cell(FIELD_SYNOPSIS))
        draft.genres = _to_list(cell(FIELD_GENRES))
        draft.studios = _to_list(cell(FIELD_STUDIOS))
        draft.media_type = _to_text(cell(FIELD_MEDIA_TYPE)).upper()
        draft.airing_status = _to_text(cell(FIELD_AIRING_STATUS)).upper()
        draft.duration = _to_int(cell(FIELD_DURATION))
        draft.season = _to_text(cell(FIELD_SEASON)).upper()
        draft.season_year = _to_optional_int(cell(FIELD_SEASON_YEAR))
        draft.poster_url = _to_text(cell(FIELD_POSTER_URL))

        draft.mal_id = _to_optional_int(cell(FIELD_MAL_ID))
        draft.anilist_id = _to_optional_int(cell(FIELD_ANILIST_ID))
        draft.kitsu_id = _to_text(cell(FIELD_KITSU_ID)) or None
        draft.tmdb_id = _to_optional_int(cell(FIELD_TMDB_ID))
        draft.anidb_id = _to_optional_int(cell(FIELD_ANIDB_ID))

        # ── Literature ────────────────────────────────────────────
        draft.category = normalize_category(cell(FIELD_CATEGORY))
        draft.title_native = _to_text(cell(FIELD_TITLE_NATIVE))
        draft.synonyms = _to_list(cell(FIELD_SYNONYMS))
        draft.chapters = _to_int(cell(FIELD_CHAPTERS))
        draft.chapters_read = _to_int(cell(FIELD_CHAPTERS_READ))
        draft.volumes = _to_int(cell(FIELD_VOLUMES))
        draft.authors = _to_list(cell(FIELD_AUTHORS))
        draft.artists = _to_list(cell(FIELD_ARTISTS))
        draft.serialization = _to_text(cell(FIELD_SERIALIZATION))
        draft.pub_status = _to_text(cell(FIELD_PUB_STATUS)).upper()
        draft.origin_country = _to_text(cell(FIELD_ORIGIN_COUNTRY)).upper()
        draft.started_at = _to_text(cell(FIELD_STARTED_AT))
        draft.ended_at = _to_text(cell(FIELD_ENDED_AT))

        # An unset category means anime; a spreadsheet row only becomes
        # literature when it explicitly says so.
        if not _to_text(cell(FIELD_CATEGORY)):
            draft.category = ""

        result.drafts.append(draft)

    return result