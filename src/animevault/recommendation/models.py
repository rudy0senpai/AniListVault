"""Stable data contracts shared by recommendation retrieval and ranking."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class UserPreferenceProfile:
    positive_genres: dict[str, float] = field(default_factory=dict)
    negative_genres: dict[str, float] = field(default_factory=dict)
    themes: dict[str, float] = field(default_factory=dict)
    studios: dict[str, float] = field(default_factory=dict)
    formats: dict[str, float] = field(default_factory=dict)
    release_year_center: float | None = None
    rating_mean: float | None = None
    rating_count: int = 0
    completion_rate: float = 0.0
    watched_episodes: int = 0
    total_episodes: int = 0
    dropped_count: int = 0
    on_hold_count: int = 0
    rewatch_count: int = 0
    favorite_count: int = 0
    tier_affinity: dict[str, float] = field(default_factory=dict)
    engagement: dict[str, float] = field(default_factory=dict)
    positive_seeds: tuple[Any, ...] = ()
    negative_seeds: tuple[Any, ...] = ()
    confidence: dict[str, float] = field(default_factory=dict)

    @property
    def usable(self) -> bool:
        return any((self.positive_genres, self.negative_genres, self.studios,
                    self.formats, self.positive_seeds, self.negative_seeds,
                    self.rating_count))


@dataclass(frozen=True)
class RecommendationCandidate:
    title: str
    title_en: str = ""
    title_romaji: str = ""
    synonyms: tuple[str, ...] = ()
    media_type: str = ""
    genres: tuple[str, ...] = ()
    themes: tuple[str, ...] = ()
    studios: tuple[str, ...] = ()
    synopsis: str = ""
    release_year: int | None = None
    score: float | None = None
    popularity: float | None = None
    rank: int | None = None
    mal_id: int | None = None
    anilist_id: int | None = None
    kitsu_id: str | None = None
    tmdb_id: int | None = None
    poster_url: str = ""
    title_ja: str = ""
    episodes: int = 0
    source: str = ""
    relationship_signal: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)
    feedback_signal: float = 0.0


@dataclass(frozen=True)
class RecommendationExplanation:
    score: float
    features: dict[str, float]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class RecommendationOutput:
    candidate: RecommendationCandidate
    explanation: RecommendationExplanation
    status: str = "available"
    cached: bool = False
