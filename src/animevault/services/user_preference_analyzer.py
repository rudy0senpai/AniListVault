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
from .title_norm import normalize_title

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
    negative_genre_weights: dict[str, float] = field(default_factory=dict)
    format_weights: dict[str, float] = field(default_factory=dict)

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
        """Return True when user activity provides usable recommendation signals.

        Unweighted metadata and Plan to Watch genres alone are not evidence of
        preference; signed activity, ratings, favorites, tiers, or progress are.
        """
        sv = self.signal_values
        if sv is None:
            return False
        # Explicit user preferences
        if (
            (sv.score_avg > 0 or len(sv.ratings) > 0)
            or len(sv.favorites) > 0
            or len(sv.tier_placed) > 0
            or (sv.episodes_watched > 0)
            or (sv.completed_count > 0)
            or (sv.dropped_count > 0)
        ):
            return True
        # Genre counts from Plan to Watch are metadata, not positive evidence.
        # Only signed activity-weighted genre evidence makes the fallback profile usable.
        return bool(self.genre_weights or self.negative_genre_weights)


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


def _activity_signal(item) -> float:
    """Signed preference evidence, with plan-to-watch entries neutral."""
    status = str(getattr(item, "status", "plan_to_watch") or "plan_to_watch").casefold().replace(" ", "_")
    tier = str(getattr(item, "tier", "") or "").strip().upper()
    tier_signal = {"SSS": 1.0, "SS": 0.95, "S": 0.9, "A": 0.75, "B": 0.55, "C": 0.3, "D": 0.1, "E": -0.15, "F": -0.35}.get(tier)
    score = getattr(item, "score", None)
    rated = isinstance(score, (int, float)) and not isinstance(score, bool) and 0 <= float(score) <= 10
    rating_signal = (float(score) - 5.0) / 5.0 if rated else None
    status_signal = {"completed": 0.45, "watching": 0.35, "on_hold": 0.1, "dropped": -0.8, "plan_to_watch": 0.0}.get(status, 0.0)
    if status == "plan_to_watch":
        signal = 0.0
    elif tier_signal is not None and status == "completed":
        signal = tier_signal
    elif rating_signal is not None:
        signal = 0.65 * rating_signal + 0.35 * status_signal
    else:
        signal = status_signal
    if getattr(item, "favorite", False):
        signal += 0.35
    return max(-1.0, min(1.0, signal))


def _deduplicate_library(items: Iterable[Anime]) -> list[Anime]:
    """Count each work once, retaining its strongest signed activity signal."""
    unique: dict[tuple, Anime] = {}
    for item in items:
        key = None
        for attr in ("anilist_id", "mal_id", "tmdb_id"):
            value = getattr(item, attr, None)
            if value:
                key = (attr, str(value))
                break
        if key is None and getattr(item, "kitsu_id", None):
            key = ("kitsu_id", str(item.kitsu_id))
        if key is None:
            key = (
                "title",
                normalize_title(str(getattr(item, "title", ""))),
                str(getattr(item, "media_type", "") or "").casefold(),
            )
        previous = unique.get(key)
        if previous is None or abs(_activity_signal(item)) > abs(_activity_signal(previous)):
            unique[key] = item
    return list(unique.values())


def _scale_positive(values: dict[str, float]) -> dict[str, float]:
    maximum = max((value for value in values.values() if value > 0), default=0.0)
    return {key: min(1.0, value / maximum) for key, value in values.items() if value > 0} if maximum else {}


def _compute_genre_affinity(anime_items: Iterable[Anime]) -> dict[str, float]:
    """Normalize observed genre frequency, independent of missing ratings."""
    counts: dict[str, float] = {}
    for item in anime_items:
        genres = {str(g).strip() for g in (getattr(item, "genres", []) or []) if str(g).strip()}
        for genre in genres:
            counts[genre] = counts.get(genre, 0.0) + 1.0 / max(1.0, len(genres) ** 0.5)
    total = sum(counts.values())
    return {genre: value / total for genre, value in counts.items()} if total else {}



def analyze_preferences(anime_items: Iterable[Anime]) -> UserProfile:
    """Compute a complete preference profile from a list of ~Anime~ objects."""
    items = _deduplicate_library(anime_items)
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
    positive_genres: dict[str, float] = {}
    negative_genres: dict[str, float] = {}
    studio_affinity: dict[str, float] = {}
    format_affinity: dict[str, float] = {}
    per_genre_ratings: dict[str, list[float]] = {}
    for item in items:
        signal = _activity_signal(item)
        genres = {str(g).strip() for g in (getattr(item, "genres", []) or []) if str(g).strip()}
        target = positive_genres if signal >= 0 else negative_genres
        for genre in genres:
            key = genre.casefold()
            target[key] = target.get(key, 0.0) + abs(signal) / max(1.0, len(genres) ** 0.5)
            score = getattr(item, "score", None)
            if isinstance(score, (int, float)) and not isinstance(score, bool) and 0 <= float(score) <= 10:
                per_genre_ratings.setdefault(genre, []).append(float(score))
        if signal > 0:
            for studio in getattr(item, "studios", []) or []:
                studio = str(studio).strip()
                if studio:
                    studio_affinity[studio] = studio_affinity.get(studio, 0.0) + signal
            media_format = str(getattr(item, "media_type", "") or "").strip().upper()
            if media_format:
                format_affinity[media_format] = format_affinity.get(media_format, 0.0) + signal
    genre_weights = _scale_positive(positive_genres)
    negative_genre_weights = _scale_positive(negative_genres)
    format_weights = _scale_positive(format_affinity)
    metadata_weights = _scale_positive(studio_affinity)
    per_genre_avg = {g: sum(values) / len(values) for g, values in per_genre_ratings.items() if values}

    sv = SignalValues(
        ratings=ratings,
        score_avg=score_avg,
        per_genre_ratings=per_genre_ratings,
        per_genre_avg=per_genre_avg,
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

    # Tier weights: map each placed tier to its engagement strength.
    tier_weights: dict[str, float] = {}
    for t in tier_placed:
        tier_items = [item for item in items if str(getattr(item, "tier", "") or "").upper() == t]
        tier_weights[t] = sum(max(0.0, _activity_signal(item)) for item in tier_items)

    # Favorite signal: extra multiplier for favourites.
    favorite_signal = 1.0 + min(2.0, len(favorites) * 0.15)


    # Watch engagement: use completion ratio, clamped to [0, 1] so that
    # rewatched/extended episodes never inflate engagement above 100%.
    watch_engagement = 0.0
    if total_episodes > 0:
        watch_engagement = min(1.0, episodes_watched / total_episodes)

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
        negative_genre_weights=negative_genre_weights,
        format_weights=format_weights,
    )

