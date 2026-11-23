"""Pydantic response schemas for the AnimeVault API (v1).

Schemas mirror the existing SQLite model projections so the renderer can
consume a stable, validated shape without caring about the underlying DB
columns.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "animevault-backend"
    database_path: str
    schema_version: int


# ---------------------------------------------------------------------------
# Generic item
# ---------------------------------------------------------------------------

class BaseItemOut(BaseModel):
    id: int
    title: str
    status: str
    tier: str | None = None
    favorite: bool = False
    notes: str = ""
    poster_path: str = ""
    poster_url: str = ""
    synopsis: str = ""


# ---------------------------------------------------------------------------
# Anime
# ---------------------------------------------------------------------------

class AnimeItemOut(BaseItemOut):
    """A lean view of an ``anime`` library record."""

    title_ja: str = ""
    title_en: str = ""
    episodes: int = 0
    episodes_watched: int = 0
    media_type: str = ""
    aired_from: str = ""
    aired_to: str = ""
    season: str = ""
    season_year: int | None = None
    duration: int = 0
    mal_id: int | None = None
    anilist_id: int | None = None
    kitsu_id: str = ""
    tmdb_id: int | None = None
    rewatches: int = 0
    first_watched: str = ""
    last_watched: str = ""
    completed_date: str = ""
    privacy: str = "public"


class AnimeSummary(BaseModel):
    """Per-status counts for the anime library."""

    plan_to_watch: int = 0
    watching: int = 0
    completed: int = 0
    on_hold: int = 0
    dropped: int = 0
    total: int = 0


class LibrarySummary(BaseModel):
    anime: AnimeSummary = Field(default_factory=AnimeSummary)
    literature: AnimeSummary = Field(default_factory=AnimeSummary)
    total_records: int = 0
    database_path: str = ""


class AnimeListResponse(BaseModel):
    items: list[AnimeItemOut] = Field(default_factory=list)
    total: int = 0
    filters_applied: dict[str, object] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Literature
# ---------------------------------------------------------------------------

class LiteratureItemOut(BaseItemOut):
    """A lean view of a ``literature`` library record."""

    title_ja: str = ""
    title_en: str = ""
    chapters: int = 0
    chapters_read: int = 0
    volumes: int = 0
    category: str = ""  # manga | manhwa | manhua
    authors: str = ""
    artists: str = ""
    serialization: str = ""
    pub_status: str = ""
    started_at: str = ""
    ended_at: str = ""
    cover_url: str = ""
    mal_id: int | None = None
    anilist_id: int | None = None
    tmdb_id: int | None = None
    kitsu_id: str = ""
    rewatches: int = 0
    first_watched: str = ""
    last_watched: str = ""


class LiteratureSummary(AnimeSummary):
    """Per-category/per-status summary for literature."""

    manga: int = 0
    manhwa: int = 0
    manhua: int = 0


class LibraryItemResponse(BaseModel):
    item: AnimeItemOut | None = None
