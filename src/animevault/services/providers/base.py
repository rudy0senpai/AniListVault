"""Abstract provider base, shared AnimeMetadata structure, and ProviderError."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


class ProviderError(Exception):
    """Raised when a provider call fails."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        retryable: bool = True,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


@dataclass
class AnimeMetadata:
    """Canonical, normalised metadata from any provider.

    Fields are intentionally permissive — a provider may leave many
    empty.  Consumers must not assume non-empty values.
    """

    # ── Identity ──────────────────────────────────────────────────
    title: str = ""
    title_en: str = ""
    title_ja: str = ""
    title_romaji: str = ""
    synonyms: list[str] = field(default_factory=list)

    # ── Provider IDs ─────────────────────────────────────────────
    mal_id: Optional[int] = None
    anilist_id: Optional[int] = None
    kitsu_id: Optional[str] = None
    tmdb_id: Optional[int] = None

    # ── Description ───────────────────────────────────────────────
    synopsis: str = ""

    # ── Classification ────────────────────────────────────────────
    media_type: str = ""        # TV, OVA, Movie, Special, ONA, Music
    airing_status: str = ""     # FINISHED, RELEASING, NOT_YET_RELEASED
    genres: list[str] = field(default_factory=list)

    # ── Release ───────────────────────────────────────────────────
    aired_from: str = ""        # ISO date string e.g. "2002-10-03"
    aired_to: str = ""
    season: str = ""            # FALL, WINTER, SPRING, SUMMER
    season_year: Optional[int] = None

    # ── Episodes ──────────────────────────────────────────────────
    episodes: int = 0
    duration: int = 0           # minutes per episode

    # ── Production ────────────────────────────────────────────────
    studios: list[str] = field(default_factory=list)

    # ── Media ─────────────────────────────────────────────────────
    poster_url: str = ""

    # ── Source ────────────────────────────────────────────────────
    source_provider: str = ""

    def best_title(self) -> str:
        """Return the most useful display title (never empty if any title exists)."""
        return (
            self.title
            or self.title_en
            or self.title_romaji
            or self.title_ja
            or "Unknown"
        )


class BaseProvider(ABC):
    """Abstract base class that every provider must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short lowercase identifier, e.g. 'anilist'."""

    @abstractmethod
    def search(self, query: str, limit: int = 10) -> list[AnimeMetadata]:
        """Search for anime by title.  Returns a list of candidates."""

    @abstractmethod
    def get_details(self, provider_id: str) -> AnimeMetadata:
        """Fetch detailed metadata by provider-specific ID."""

    def is_available(self) -> bool:
        """Return False when the provider is known to be unavailable."""
        return True
