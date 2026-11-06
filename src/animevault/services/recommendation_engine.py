"""Recommendation engine orchestration.

The main entry point for the AnimeVault recommendation subsystem.  This module
orchestrates:

1. Preference analysis (:mod:`user_preference_analyzer`) — builds a weighted
   profile from the user's library.
2. Similarity calculation (:mod:`anime_similarity`) — computes how close a
   candidate is to the user's preferred shows.
3. Weighted ranking (:mod:`recommendation_scorer`) — scores and ranks
   candidates using a configurable hybrid model.
4. External discovery (:mod:`recommendation_discovery`) — fetches new
   candidates from registered metadata providers.
5. Caching / dismissed handling (:mod:`recommendation_cache`) — keeps results
   local and remembers dismissed titles.

The engine never requires network access: offline recommendation is fully
functional using only the local library.  Online discovery is optional and
only triggered when the user enables it.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from animevault.models.anime import Anime
from animevault.database import get_connection

from .user_preference_analyzer import UserProfile, analyze_preferences
from .anime_similarity import anime_similarity, SimilarityScore
from .recommendation_scorer import (
    Recommendation,
    RankingCandidate,
    RecommendationScorer,
)
from .recommendation_discovery import discover_candidates, search_by_title
from .recommendation_cache import RecommendationCache

logger = logging.getLogger(__name__)

# Local cache (file-based).
_CACHE = RecommendationCache()

# Categories recognised by the engine.
KNOWN_CATEGORIES = {
    "isekai", "action", "adventure", "fantasy", "romance", "comedy",
    "mystery", "horror", "psychological", "sci-fi", "slice of life",
    "drama", "supernatural", "sports", "thriller", "seinen", "shoujo",
    "shounen", "school", "josei",
}


# ── Public result model ───────────────────────────────────────────────

@dataclass(frozen=True)
class RecommendationResult:
    """A single recommendation result with its category and group label."""
    item_id: int
    title: str
    media_type: str
    category: str
    genres: list[str]
    synopsis: str
    score: float
    reasons: list[str]
    poster_url: str = ""
    progress: str = ""
    progress_percent: int = 0
    tier: Optional[str] = None
    is_plan_to_watch: bool = False
    is_new_discovery: bool = False
    is_similar: bool = False
    discovery_source: str = ""


@dataclass(frozen=True)
class RecommendationSet:
    """A full recommendation set for a user + category + filters."""
    category: str
    results: list[RecommendationResult]
    preferred_categories: list[tuple[str, float]] = None
    watch_engagement: float = 0.0
    profile_doc: list[str] = None

    def __post_init__(self):
        if self.preferred_categories is None:
            object.__setattr__(self, "preferred_categories", [])
        if self.profile_doc is None:
            object.__setattr__(self, "profile_doc", [])

    @property
    def new_discoveries(self) -> list[RecommendationResult]:
        return [r for r in self.results if r.is_new_discovery]

    @property
    def planned(self) -> list[RecommendationResult]:
        return [r for r in self.results if r.is_plan_to_watch]

    @property
    def similar(self) -> list[RecommendationResult]:
        return [r for r in self.results if r.is_similar]


# ── Engine ────────────────────────────────────────────────────────────

class RecommendationEngine:
    """Orchestrates the recommendation pipeline for a user's library."""

    def __init__(
        self,
        library_items: Optional[Sequence[Anime]] = None,
        user_hash: Optional[str] = None,
        online_discovery: bool = True,
    ):
        self.library_items = list(library_items or [])
        self.user_hash = user_hash or self._default_user_hash()
        self.online_discovery = online_discovery
        self._category_profiles: dict[str, UserProfile] = {}

    @staticmethod
    def _default_user_hash() -> str:
        return hashlib.sha256(b"default").hexdigest()

    @property
    def profile(self) -> UserProfile:
        """Global profile (all categories)."""
        if not self.library_items:
            return UserProfile(
                signal_values=None,
                genre_weights={},
                tier_weights={},
                favorite_signal=1.0,
                metadata_weights={},
                watch_engagement=0.0,
                profile_doc=[],
            )
        # Check a lightweight cache before recomputing.
        cached = _CACHE.get(self.user_hash, "all", "all")
        if cached is not None:
            # Deserialize (simplified for brevity; in production use a proper
            # dataclass->dict converter).
            from recommendation_cache import _cache_path
            import json
            path = _cache_path(_CACHE._cache_key(self.user_hash, "all", "all"))
            try:
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
                return UserProfile(
                    signal_values=None,
                    genre_weights=data.get("genre_weights", {}),
                    tier_weights=data.get("tier_weights", {}),
                    favorite_signal=data.get("favorite_signal", 1.0),
                    metadata_weights=data.get("metadata_weights", {}),
                    watch_engagement=data.get("watch_engagement", 0.0),
                    profile_doc=data.get("profile_doc", []),
                )
            except (json.JSONDecodeError, OSError):
                pass
        return self._build_profile()

    def _build_profile(self) -> UserProfile:
        profile = analyze_preferences(self.library_items)
        self._category_profiles["all"] = profile
        return profile

    def category_profile(self, category: str) -> UserProfile:
        """Return the profile restricted to *category* (e.g. "isekai")."""
        if category in self._category_profiles:
            return self._category_profiles[category]
        # For categories, filter the library to items that belong to the
        # category, then build a profile.
        if not self.library_items:
            return UserProfile(
                signal_values=None,
                genre_weights={},
                tier_weights={},
                favorite_signal=1.0,
                metadata_weights={},
                watch_engagement=0.0,
                profile_doc=[],
            )
        filtered = [i for i in self.library_items if self._category_matches(i, category)]
        if not filtered:
            # Fall back to the global profile if no items match.
            if "all" in self._category_profiles:
                return self._category_profiles["all"]
            profile = self._build_profile()
            self._category_profiles[category] = profile
            return profile
        profile = analyze_preferences(filtered)
        self._category_profiles[category] = profile
        return profile

    @staticmethod
    def _category_matches(item, category: str) -> bool:
        raw = set(str(getattr(item, "genres", []) or []))
        cats = {g.strip().lower() for g in raw}
        if category in {"isekai", "slice of life", "sci-fi", "sports", "romance", "action"}:
            # Isekai: fantasy/adventure genres.
            if category == "isekai":
                return bool(cats & {"isekai", "fantasy", "adventure", "dungeon", "reincarnation", "cheat", "magic"})
            if category == "slice of life":
                return "slice of life" in cats or "school" in cats
            if category == "sci-fi":
                return "sci-fi" in cats or "space" in cats or "cyberpunk" in cats
            if category == "sports":
                return "sports" in cats
            if category == "romance":
                return "romance" in cats
            if category == "action":
                return "action" in cats
        return category in cats

    def get_recommendations(
        self,
        category: str = "all",
        n: int = 12,
        genre_filter: str = "",
        media_type_filter: str = "all",
        min_score: float = 0.0,
        sort_by: str = "relevance",
        search_query: Optional[str] = None,
    ) -> list[RecommendationResult]:
        """Return a ranked list of recommendations."""
        profile = self.category_profile(category)
        candidates = self._build_candidates(
            profile, category, n, genre_filter, media_type_filter, search_query
        )
        results = self._score_and_rank(candidates, profile, category)
        # Apply filters.
        filtered = [
            r for r in results
            if (genre_filter == "" or any(genre_filter.lower() in g.lower() for g in r.genres))
            and (media_type_filter == "all" or r.media_type == media_type_filter.upper())
            and (min_score == 0.0 or r.score >= min_score)
        ]
        filtered.sort(key=lambda r: (
            r.is_plan_to_watch,
            -r.score,
        ))
        return filtered[:n]

    def _build_candidates(
        self,
        profile,
        category: str,
        n: int,
        genre_filter: str,
        media_type_filter: str,
        search_query: Optional[str],
    ) -> list[RankingCandidate]:
        """Build candidate set from library + optional external discovery."""
        candidates: list[RankingCandidate] = []
        seen_ids: set[int] = set()

        # 1. From local library (new discoveries + similar).
        # Skip plan-to-watch items here; they are handled in block 3.
        for item in self.library_items:
            if item.id in seen_ids:
                continue
            # Exclude already watched items. Plan-to-watch items are handled
            # separately in block 3.
            status = getattr(item, "status", "plan_to_watch")
            if status != "plan_to_watch":
                continue
            # Skip plan-to-watch items here too (handled in block 3).
            if status == "plan_to_watch":
                continue
            similarity = self._compute_similarity(item, profile)
            if similarity.total < 0.05:
                continue
            candidates.append(RankingCandidate(
                item=item,
                score=0.0,
                reasons=[],
                similarity=similarity,
                category=category,
                is_plan_to_watch=False,
                is_new_discovery=True,
                is_similar=not (category == "all" and similarity.total < 0.15),
                discovery_source="local",
            ))
            seen_ids.add(item.id)

        # 2. External discovery (if enabled).
        if self.online_discovery and search_query:
            try:
                discovered = discover_candidates(
                    search_query, categories=[category] if category != "all" else None, limit=n
                )
                for c in discovered:
                    if c.item_id in seen_ids:
                        continue
                    candidates.append(RankingCandidate(
                        item=c,
                        score=0.0,
                        reasons=[],
                        similarity=SimilarityScore(),
                        is_plan_to_watch=False,
                        is_new_discovery=True,
                        is_similar=False,
                        discovery_source="online",
                    ))
                    seen_ids.add(c.item_id)
            except Exception as exc:
                logger.warning("Discovery failed: %s", exc)

        # 3. Include plan-to-watch titles (planned anime).
        for item in self.library_items:
            if item.id in seen_ids:
                continue
            if getattr(item, "status", "plan_to_watch") == "plan_to_watch":
                similarity = self._compute_similarity(item, profile)
                candidates.append(RankingCandidate(
                    item=item,
                    score=0.0,
                    reasons=[],
                    similarity=similarity,
                    is_plan_to_watch=True,
                    is_new_discovery=False,
                    is_similar=False,
                    discovery_source="library",
                ))
                seen_ids.add(item.id)

        return candidates

    def _compute_similarity(self, item, profile) -> SimilarityScore:
        """Compute similarity between a candidate and the user's profile."""
        # Compare against a representative set of the user's preferences.
        # In practice, compare against the top-N highly-rated items.
        # For a placeholder, compare the candidate against itself using the
        # same similarity function used by the engine.
        return anime_similarity(item, item)  # placeholder; refined in scoring

    def _score_and_rank(
        self,
        candidates: list[RankingCandidate],
        profile: UserProfile,
        category: str,
    ) -> list[RecommendationResult]:
        """Score candidates and return a ranked list of RecommendationResult."""
        if not candidates:
            return []

        scorer = RecommendationScorer(profile, weights={
            "genre_theme_similarity": 0.25,
            "similarity_to_highly_rated": 0.25,
            "tier_placement": 0.15,
            "favorite_status": 0.15,
            "watch_engagement": 0.10,
            "metadata_similarity": 0.10,
        })

        profile_genre_weights = profile.genre_weights if profile else {}
        ranked = scorer.rank_candidates(candidates, profile_genre_weights)

        results = []
        for rec in ranked:
            results.append(RecommendationResult(
                item_id=rec.item_id,
                title=rec.title,
                media_type=rec.media_type,
                category=rec.category,
                genres=rec.genres,
                synopsis=rec.synopsis,
                score=rec.score,
                reasons=rec.reasons,
                poster_url=rec.poster_url,
                progress=rec.progress,
                progress_percent=rec.progress_percent,
                tier=rec.tier,
                is_plan_to_watch=rec.is_plan_to_watch,
                is_new_discovery=rec.is_new_discovery,
                is_similar=rec.is_similar,
                discovery_source=rec.discovery_source,
            ))
        return results

    def get_preference_summary(self) -> dict:
        """Return a summary of the user's preferences."""
        profile = self.profile
        if not profile or not profile.signal_values:
            return {"status": "insufficient_data"}
        sv = profile.signal_values
        return {
            "has_preferences": profile.has_preferences(),
            "score_avg": round(sv.score_avg, 2) if sv.score_avg else 0.0,
            "rating_count": len(sv.ratings),
            "top_genres": [(g, round(w, 3)) for g, w in profile.top_genres(5)],
            "top_tiers": [(t, round(w, 3)) for t, w in profile.top_tiers(3)],
            "favorites_count": len(sv.favorites),
            "watch_engagement": round(profile.watch_engagement, 3),
            "completed": sv.completed_count,
            "dropped": sv.dropped_count,
            "plan": sv.plan_count,
            "episodes_watched": sv.episodes_watched,
            "total_episodes": sv.total_episodes,
        }


# ── Functional API ────────────────────────────────────────────────────

def get_recommendations(
    library_items: Sequence[Anime],
    user_hash: Optional[str] = None,
    category: str = "all",
    n: int = 12,
    genre_filter: str = "",
    media_type_filter: str = "all",
    online_discovery: bool = True,
    min_score: float = 0.0,
) -> list[RecommendationResult]:
    """Return a ranked list of recommendations.

    This is a convenience function that builds an engine, runs it, and
    returns the top-*n* results.
    """
    engine = RecommendationEngine(
        library_items=library_items,
        user_hash=user_hash or hashlib.sha256(b"default").hexdigest(),
        online_discovery=online_discovery,
    )
    return engine.get_recommendations(
        category=category,
        n=n,
        genre_filter=genre_filter,
        media_type_filter=media_type_filter,
        min_score=min_score,
    )
