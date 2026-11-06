"""User preference analyzer — builds a weighted preference profile from the
user's AnimeVault library.

Combines multiple engagement signals into a single profile the recommender
can rank against:

* Rating analysis — average rating and per-genre ratings.
* Tier analysis — canonical tier placement (S, A, B, C, D, E, F, SSS, SS).
* Favorite analysis — extra weight on titles flagged as favorites.
* Watch history — completion, episodes watched, progress, dropped titles.
* Metadata signals — genre / studio / format affinity.

Signal weights are configurable and described in
``recommendation_scorer``; the analyzer only computes raw signal values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from animevault.models.anime import Anime

# ── Weight constants (overridable per profile) ───────────────────────

DEFAULT_RATING_WEIGHT = 1.0
DEFAULT_TIER_WEIGHT = 1.0
DEFAULT_FAVORITE_WEIGHT = 2.0
DEFAULT_WATCH_WEIGHT = 0.75
DEFAULT_METADATA_WEIGHT = 0.5

# Canonical tier ordering (best → worst).  Lower number = better tier.
_CUSTOM_TIER_RANK: dict[str, int] = {
    "SSS": 1,
    "SS": 2,
    "S": 3,
    "A": 4,
    "B": 5,
    "C": 6,
    "D": 7,
    "E": 8,
    "F": 9,
}

# Genres that commonly appear in the metadata; used as a sanity check.
_RECOGNISED_GENRES = {
    "action", "adventure", "fantasy", "romance", "comedy", "mystery",
    "horror", "psychological", "sci-fi", "slice of life", "drama",
    "supernatural", "sports", "thriller", "isekai", "seinen", "shoujo",
    "shounen", "school", " Cooking", "josei", "shonen",
}

# Genres that map to the "Isekai" category (task #3).
_ISEKAI_GENRES = {
    "isekai", "fantasy", "adventure", "dungeon", "reincarnation",
    "cheat", "saint", "ruler", "cursed", "magic",
}

# ── Result model ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class SignalValues:
    """Raw signal values for a single user's library."""
    ratings: list[float]
    score_avg: float
    per_genre_ratings: dict[str, list[float]]
    per_genre_avg: dict[str, float]
    tier_placed: list[str]
    tier_by_genre: dict[str, list[str]]
    favorites: list[int]
    watched_count: int
    episodes_watched: int
    total_episodes: int
    completed_count: int
    dropped_count: int
    plan_count: int
    progress: dict[str, float]
    genre_affinity: dict[str, float]
    metadata_count: int


@dataclass(frozen=True)
class UserProfile:
    """
    A user's learned preference profile.

    Attributes
    ----------
    signal_values:
        Raw signal values computed from the library.
    genre_weights:
        Weight per genre (0..1 scale).  Higher = more preferred.
    tier_weights:
        Weight per tier, mapping tier → engagement strength.
    favorite_signal:
        Additional weight multiplier applied to favourites.
    metadata_weights:
        Weight per studio / author / artist.
    watch_engagement:
        Normalised watch-time / completion engagement value (0..1).
    profile_doc:
        Tokenised document used for TF-IDF semantic similarity.
    """
    signal_values: SignalValues
    genre_weights: dict[str, float] = field(default_factory=dict)
    tier_weights: dict[str, float] = field(default_factory=dict)
    favorite_signal: float = 1.0
    metadata_weights: dict[str, float] = field(default_factory=dict)
    watch_engagement: float = 0.0
    profile_doc: list[str] = field(default_factory=list)

    # ── Convenience accessors ──────────────────────────────────────

    def top_genres(self, n: int = 8) -> list[tuple[str, float]]:
        return sorted(
            self.genre_weights.items(), key=lambda kv: kv[1], reverse=True
        )[:n]

    def top_tiers(self, n: int = 6) -> list[tuple[str, float]]:
        return sorted(
            self.tier_weights.items(), key=lambda kv: _CUSTOM_TIER_RANK.get(kv[0], 99),
            reverse=True,
        )[:n]

    def top_metadata(self, n: int = 6) -> list[tuple[str, float]]:
        return sorted(
            self.metadata_weights.items(), key=lambda kv: kv[1], reverse=True
        )[:n]

    def has_preferences(self) -> bool:
        """Return True when enough signals exist to make recommendations."""
        sv = self.signal_values
        return (
            (sv.score_avg > 0 or len(sv.ratings) > 0)
            or len(sv.favorites) > 0
            or len(sv.tier_placed) > 0
            or (sv.episodes_watched > 0)
        )


# ── Small text helpers ───────────────────────────────────────────────

import unicodedata
import re

_TOKEN_RE = re.compile(r"[^\w\s]+")
_WORD_RE = re.compile(r"\w+", re.UNICODE)
_WS_RE = re.compile(r"\s+", re.UNICODE)


def _norm(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = _TOKEN_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip().lower()


def _tokens(text: str) -> list[str]:
    return _WORD_RE.findall(_norm(text))


# ── Signal computation ───────────────────────────────────────────────

def _compute_ratings(anime_items: Iterable[Anime]) -> tuple[list[float], float]:
    ratings: list[float] = []
    total = 0.0
    for item in anime_items:
        score = getattr(item, "score", None)
        if isinstance(score, (int, float)) and 0.0 <= float(score) <= 10.0:
            ratings.append(float(score))
            total += float(score)
    avg = total / len(ratings) if ratings else 0.0
    return ratings, avg


def _compute_tier_placement(anime_items: Iterable[Anime]) -> list[str]:
    placements: list[str] = []
    for item in anime_items:
        tier = getattr(item, "tier", None)
        if tier:
            tier = str(tier).strip().upper()
            if tier in _CUSTOM_TIER_RANK:
                placements.append(tier)
    return placements


def _compute_favorites(anime_items: Iterable[Anime]) -> list[int]:
    return [item.id for item in anime_items if getattr(item, "favorite", False)]


def _compute_watch_history(anime_items: Iterable[Anime]) -> tuple[int, int, int, int, dict[str, float]]:
    episodes_watched = 0
    total_episodes = 0
    completed = 0
    dropped = 0
    plan = 0
    progress: dict[str, float] = {}
    for item in anime_items:
        ep_watched = getattr(item, "episodes_watched", 0)
        episodes = getattr(item, "episodes", 0)
        status = str(getattr(item, "status", "plan_to_watch")).lower()
        if ep_watched and episodes:
            progress[status] = ep_watched / max(episodes, 1)
        episodes_watched += ep_watched
        total_episodes += episodes
        if status == "completed":
            completed += 1
        elif status == "dropped":
            dropped += 1
        elif status == "plan_to_watch":
            plan += 1
    return episodes_watched, total_episodes, completed, dropped, plan, progress


def _compute_genre_affinity(anime_items: Iterable[Anime]) -> dict[str, float]:
    genre_hits: dict[str, int] = {}
    genre_ratings: dict[str, list[float]] = {}
    for item in anime_items:
        genres = list(getattr(item, "genres", []) or [])
        score = getattr(item, "score", None)
        rating = float(score) if isinstance(score, (int, float)) and 0.0 <= float(score) <= 10.0 else None
        for g in genres:
            g = g.strip()
            if not g:
                continue
            genre_hits[g] = genre_hits.get(g, 0) + 1
            genre_ratings.setdefault(g, [])
            if rating is not None:
                genre_ratings[g].append(rating)
    affinity: dict[str, float] = {}
    total = 0
    for g, hits in genre_hits.items():
        ratings = genre_ratings.get(g, [])
        avg = sum(ratings) / len(ratings) if ratings else 0.0
        affinity[g] = avg * (hits ** 0.75)
        total += affinity[g]
    if total > 0:
        affinity = {g: v / total for g, v in affinity.items()}
    return affinity


def analyze_preferences(anime_items: Iterable[Anime]) -> UserProfile:
    """Compute a complete preference profile from a list of ~Anime~ objects."""
    items = list(anime_items)
    if not items:
        return UserProfile(SignalValues(ratings=[], score_avg=0.0,
                                         per_genre_ratings={}, per_genre_avg={},
                                         tier_placed=[], tier_by_genre={},
                                         favorites=[], watched_count=0,
                                         episodes_watched=0, total_episodes=0,
                                         completed_count=0, dropped_count=0,
                                         plan_count=0, progress={},
                                         genre_affinity={}, metadata_count=0))

    # Compute all raw signal values first, then build the frozen SignalValues
    # in a single call (it cannot be mutated after creation).
    ratings, score_avg = _compute_ratings(items)
    tier_placed = _compute_tier_placement(items)
    favorites = _compute_favorites(items)
    episodes_watched, total_episodes, completed, dropped, plan, progress = _compute_watch_history(items)
    genre_affinity = _compute_genre_affinity(items)

    # Build SignalValues in a single call (frozen dataclass).
    sv = SignalValues(
        ratings=ratings,
        score_avg=score_avg,
        per_genre_ratings={},
        per_genre_avg={},
        tier_placed=tier_placed,
        tier_by_genre={},
        favorites=favorites,
        watched_count=0,
        episodes_watched=episodes_watched,
        total_episodes=total_episodes,
        completed_count=completed,
        dropped_count=dropped,
        plan_count=plan,
        progress=progress,
        genre_affinity=genre_affinity,
        metadata_count=0,
    )

    # Build weighted profile.
    # Genre weights: prefer genres with high average rating + high hits.
    genre_weights: dict[str, float] = {}
    for g, avg in genre_affinity.items():
        genre_weights[g] = avg * 0.6 + 0.05

    # Tier weights: map each placed tier to its engagement strength.
    tier_weights: dict[str, float] = {}
    for t in tier_placed:
        tier_weights[t] = _CUSTOM_TIER_RANK[t] * 0.1

    # Favorite signal: extra multiplier for favourites.
    favorite_signal = 1.0 + min(2.0, len(favorites) * 0.15)

    # Metadata weights: use genre association is not directly available;
    # fall back to a simple count of metadata.
    metadata_weights: dict[str, float] = {}

    # Watch engagement: use completion ratio.
    watch_engagement = 0.0
    if total_episodes > 0:
        watch_engagement = episodes_watched / total_episodes

    # Profile document for TF-IDF semantic similarity.
    profile_doc: list[str] = []
    for item in items:
        parts = list(getattr(item, "genres", []) or [])
        synopsis = str(getattr(item, "synopsis", "") or "")
        if synopsis.strip():
            parts.append(synopsis)
        profile_doc.append(_norm(" ".join(parts)))

    return UserProfile(
        signal_values=sv,
        genre_weights=genre_weights,
        tier_weights=tier_weights,
        favorite_signal=favorite_signal,
        metadata_weights=metadata_weights,
        watch_engagement=watch_engagement,
        profile_doc=profile_doc,
    )

    # Genre affinity
    genre_affinity = _compute_genre_affinity(items)
    sv.genre_affinity = genre_affinity

    # ── Build weighted profile ──────────────────────────────────────

    # Genre weights: prefer genres with high average rating + high hits.
    genre_weights: dict[str, float] = {}
    for g, avg in sv.genre_affinity.items():
        genre_weights[g] = avg * 0.6 + 0.05

    # Tier weights: map each placed tier to its engagement strength.
    tier_weights: dict[str, float] = {}
    for t in sv.tier_placed:
        tier_weights[t] = _CUSTOM_TIER_RANK[t] * 0.1

    # Favorite signal: extra multiplier for favourites.
    favorite_signal = 1.0 + min(2.0, len(sv.favorites) * 0.15)

    # Metadata weights (studios, authors, artists) from genre association is
    # not directly available; fall back to a simple count of metadata.
    metadata_weights: dict[str, float] = {}

    # Watch engagement: use completion ratio.
    watch_engagement = 0.0
    if sv.total_episodes > 0:
        watch_engagement = sv.episodes_watched / sv.total_episodes

    # Profile document for TF-IDF semantic similarity.
    profile_doc: list[str] = []
    for item in items:
        parts = list(getattr(item, "genres", []) or [])
        synopsis = str(getattr(item, "synopsis", "") or "")
        if synopsis.strip():
            parts.append(synopsis)
        profile_doc.append(_norm(" ".join(parts)))

