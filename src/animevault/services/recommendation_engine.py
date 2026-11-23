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

from .user_preference_analyzer import UserProfile, analyze_preferences, _activity_signal
from .anime_similarity import anime_similarity, SimilarityScore
from .recommendation_scorer import (
    Recommendation,
    RankingCandidate,
    RecommendationScorer,
)
from .recommendation_discovery import discover_candidates, search_by_title
from .recommendation_cache import RecommendationCache
from .recommendation_discovery import _candidate_key
from .title_norm import normalize_title

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
    title_ja: str = ""
    episodes: int = 0
    provider_key: str = ""
    provider_id: str = ""
    is_cached: bool = False
    score_breakdown: dict[str, float] = None


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
        jikan_service=None,
    ):
        self.library_items = list(library_items or [])
        self.user_hash = user_hash or self._default_user_hash()
        self.online_discovery = online_discovery
        self.jikan_service = jikan_service
        self._category_profiles: dict[str, UserProfile] = {}
        self._external_candidates = []
        self._external_candidates_after_owned = 0
        self._discovery_failures = 0
        self._discovery_errors = []
        self._discovery_stats = {}
        # Outcome of the most recent :meth:`get_recommendations` run.  Defaults
        # to "none" so callers that ask before any run are not misleading.
        self._last_outcome: str = "none"

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
        """Return a ranked list of recommendations.

        Owned items (anything already present in the user's library) are
        excluded from the final list, preferring a reliable provider
        identifier when one is available and falling back to a normalized
        title.  The run outcome is stored on the engine and exposed by
        :meth:`get_preference_summary` so the UI can distinguish:
        insufficient preference data, no external candidates, provider /
        network failure, all items owned, all items filtered out, or valid
        recommendations.
        """
        profile = self.category_profile(category)

        # Owned-item exclusion prefers provider identifiers; titles are the
        # fallback.  These sets are reused by candidate production and the
        # final safety filter.
        owned_ids = self._owned_provider_ids()
        owned_titles = set()
        for anime in self.library_items:
            has_provider_id = any(
                (isinstance(value, int) and not isinstance(value, bool) and value > 0)
                or (isinstance(value, str) and value.isdigit() and int(value) > 0)
                for value in (getattr(anime, attr, None) for attr in ("anilist_id", "mal_id", "tmdb_id"))
            ) or bool(str(getattr(anime, "kitsu_id", "") or "").strip())
            if not has_provider_id:
                owned_titles.add((normalize_title(anime.title), str(getattr(anime, "media_type", "") or "").strip().casefold()))

        candidates = self._build_candidates(
            profile, category, n, genre_filter, media_type_filter, search_query,
            owned_ids=owned_ids, owned_titles=owned_titles,
        )
        results = self._score_and_rank(candidates, profile, category)

        # Apply filters.
        filtered = [
            r for r in results
            if (genre_filter == "" or any(genre_filter.lower() in g.lower() for g in r.genres))
            and (media_type_filter == "all" or r.media_type == media_type_filter.upper())
            and (min_score == 0.0 or r.score >= min_score)
        ]
        # Safety net: drop anything already owned (provider ids were already
        # applied when the candidates were produced).
        filtered = [r for r in filtered if not self._is_owned_result(r, owned_titles, owned_ids)]

        filtered.sort(key=lambda r: (
            r.is_plan_to_watch,
            -r.score,
        ))
        # Deduplicate.  A stable provider identifier (the result's item_id) is
        # preferred; otherwise fall back to a normalized title + media type.
        seen_keys: set = set()
        deduped = []
        for r in filtered:
            key = self._dedup_key(r)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduped.append(r)

        self._determine_outcome(profile, deduped)
        return deduped[:n]

    def _owned_provider_ids(self) -> set:
        """Stable provider identifiers present in the library.

        Provider identifiers are the most reliable signal that two records
        refer to the same work, so they are preferred for owned-item
        exclusion.  Kitsu IDs are strings and are stored as-is.
        """
        ids: set = set()
        for item in self.library_items:
            for attr in ("anilist_id", "mal_id", "tmdb_id"):
                value = getattr(item, attr, None)
                if value:
                    try:
                        ids.add((attr, int(value)))
                    except (TypeError, ValueError):
                        pass
            kitsu = getattr(item, "kitsu_id", None)
            if kitsu:
                ids.add(("kitsu_id", str(kitsu)))
        return ids

    @staticmethod
    def _title_is_owned(title: str, media_type: str, owned_titles: set[tuple[str, str]]) -> bool:
        normalized = normalize_title(title)
        media = str(media_type or "").strip().casefold()
        return (normalized, media) in owned_titles or (normalized, "") in owned_titles or (not media and any(name == normalized for name, _ in owned_titles))

    def _is_owned_result(self, result: "RecommendationResult", owned_titles: set[tuple[str, str]], owned_ids: set) -> bool:
        """Return True when a scored result is already in the library.

        Candidates that carried a provider identifier were checked against the
        library at production time.  This title-only check is the defensive
        fallback for results that do not carry an identifier.
        """
        if result.provider_key and result.provider_id:
            try:
                provider_id = int(result.provider_id) if result.provider_key != "kitsu_id" else result.provider_id
            except ValueError:
                return self._title_is_owned(result.title, result.media_type, owned_titles)
            return (result.provider_key, provider_id) in owned_ids or self._title_is_owned(result.title, result.media_type, owned_titles)
        return self._title_is_owned(result.title, result.media_type, owned_titles)

    def _dedup_key(self, result: "RecommendationResult") -> tuple:
        """Deduplicate key for a recommendation result.

        A stable provider identifier is preferred; otherwise a normalized
        title + media type is used.  This keeps distinct works with identical
        titles (different provider IDs) separate.
        """
        if result.provider_key and result.provider_id:
            return ("provider", result.provider_key, result.provider_id, (result.media_type or "").strip().lower())
        if result.item_id > 0:
            return ("provider", result.item_id, (result.media_type or "").strip().lower())
        return ("title", normalize_title(result.title), (result.media_type or "").strip().lower())

    @staticmethod
    def _candidate_provider_ids(candidate: "Candidate") -> set[tuple[str, object]]:
        """Return all reliable provider IDs carried by a candidate."""
        ids: set[tuple[str, object]] = set()
        for attr in ("anilist_id", "mal_id", "tmdb_id"):
            value = getattr(candidate, attr, None)
            if value:
                try:
                    ids.add((attr, int(value)))
                except (TypeError, ValueError):
                    pass
        kitsu = getattr(candidate, "kitsu_id", None)
        if kitsu:
            ids.add(("kitsu_id", str(kitsu)))
        return ids

    @staticmethod
    def _error_category(exc: Exception) -> str:
        status = getattr(exc, "status_code", None)
        message = str(exc).casefold()
        if status == 429:
            return "http_429_rate_limited"
        if status in (500, 502, 503, 504):
            return "http_server_error"
        if status is not None:
            return "http_error"
        if "timeout" in message or "timed out" in message:
            return "timeout"
        if "invalid response" in message:
            return "invalid_response"
        return "provider_error"

    @staticmethod
    def _select_positive_seeds(library_items: Sequence[Anime], *, limit: int = 3) -> list[tuple[int, str]]:
        """Prioritize MAL seeds by explicit positive user evidence; skip PTW."""
        tier_strength = {"SSS": 1.0, "SS": 0.95, "S": 0.9, "A": 0.75, "B": 0.55, "C": 0.3, "D": 0.1}
        ranked_by_mal = {}
        for item in library_items:
            status = str(getattr(item, "status", "") or "").casefold().replace(" ", "_")
            if status == "plan_to_watch":
                continue
            try:
                mal_id = int(getattr(item, "mal_id", 0) or 0)
            except (TypeError, ValueError):
                continue
            if mal_id <= 0:
                continue
            strength = _activity_signal(item)
            score = getattr(item, "score", None)
            score_value = float(score) if isinstance(score, (int, float)) and not isinstance(score, bool) else 0.0
            tier = str(getattr(item, "tier", "") or "").upper()
            explicit_positive = bool(getattr(item, "favorite", False)) or score_value >= 8.0 or tier in {"SSS", "SS", "S", "A", "B", "C"}
            if status == "dropped" and not explicit_positive:
                continue
            if strength <= 0.15 and not (status == "dropped" and explicit_positive):
                continue
            priority = (bool(getattr(item, "favorite", False)), tier_strength.get(tier, 0.0), score_value, strength)
            entry = (priority, mal_id, str(getattr(item, "title", "")))
            if mal_id not in ranked_by_mal or priority > ranked_by_mal[mal_id][0]:
                ranked_by_mal[mal_id] = entry
        ranked = list(ranked_by_mal.values())
        ranked.sort(key=lambda entry: entry[0], reverse=True)
        return [(mal_id, title) for _, mal_id, title in ranked[:max(0, limit)]]

    def _build_candidates(
        self,
        profile,
        category: str,
        n: int,
        genre_filter: str,
        media_type_filter: str,
        search_query: Optional[str],
        owned_ids: set,
        owned_titles: set[str],
    ) -> list[RankingCandidate]:
        """Build candidate set from library + optional external discovery."""
        # Outcome tracking for the empty-state messages.
        self._external_candidates = []
        self._external_candidates_after_owned = 0
        self._discovery_failures = 0
        self._discovery_errors = []
        self._discovery_stats = {}
        candidates: list[RankingCandidate] = []
        seen_ids: set[int] = set()

        # 1. From local library (new discoveries + similar).
        # Skip plan-to-watch items here; they are handled in block 3.
        for item in self.library_items:
            if item.id in seen_ids:
                continue
            status = getattr(item, "status", "plan_to_watch")
            # Block 1: process non-plan-to-watch items (completed, watching, etc.)
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
                is_new_discovery=False,
                is_similar=not (category == "all" and similarity.total < 0.15),
                discovery_source="local",
            ))
            seen_ids.add(item.id)

        # Select a few strongest positive AnimeVault library signals.
        all_discovered = []
        seed_ids = self._select_positive_seeds(self.library_items, limit=3)
        genre_names = [name for name, weight in profile.top_genres(3) if weight > 0.0]
        service = None
        if self.online_discovery and profile and profile.has_preferences():
            try:
                from .jikan_recommendation_service import JikanRecommendationService
                service = self.jikan_service or JikanRecommendationService()
            except Exception as exc:
                self._discovery_failures += 1
                logger.exception("Could not initialize Jikan discovery service")
                self._discovery_errors.append({"source": "service_initialization", "category": "provider_error", "message": str(exc)})
        if service is not None:
            reset = getattr(service, "reset_diagnostics", None)
            if callable(reset):
                reset()
            if seed_ids:
                try:
                    all_discovered.extend(service.recommendations_for(seed_ids, per_seed=8, max_seeds=3))
                except Exception as exc:
                    logger.warning("Related-anime discovery failed: %s", exc)
                    self._discovery_errors.append({"source": "related_recommendations", "category": self._error_category(exc), "message": str(exc)})
            if genre_names:
                try:
                    all_discovered.extend(service.genre_candidates(genre_names, max_genres=3, pages_per_genre=2, limit=15))
                except Exception as exc:
                    logger.warning("Jikan genre discovery failed: %s", exc)
                    self._discovery_errors.append({"source": "genre_discovery", "category": self._error_category(exc), "message": str(exc)})
            self._discovery_errors.extend(list(getattr(service, "errors", []) or []))
            self._discovery_stats = dict(getattr(service, "stats", {}) or {})
            self._discovery_failures = len(self._discovery_errors)

        # A literal title search is only appropriate for an explicit user
        # search query; genre names are never sent as title queries.
        if self.online_discovery and search_query:
            try:
                all_discovered.extend(discover_candidates(search_query, categories=None, limit=min(n, 20)))
            except Exception as exc:
                self._discovery_failures += 1
                logger.warning("Supplementary title search failed for %r: %s", search_query, exc)
                self._discovery_errors.append({"source": "title_search", "category": self._error_category(exc), "message": str(exc)})

        # Exclude items already in the library.  Provider identifiers are
        # preferred (a stable id means two records are the same work even when
        # titles differ); otherwise a normalized title + media type is used so
        # that a TV and a Movie with the same title remain distinct works.
        # Library entries are therefore excluded before scoring, and the final
        # safety filter below is a redundant defensive check.
        external_candidates = []
        seen_ext: set = set()
        unique_candidates = []
        duplicates_removed = 0
        for c in all_discovered:
            key = _candidate_key(c)
            if key in seen_ext:
                duplicates_removed += 1
                continue
            seen_ext.add(key)
            unique_candidates.append(c)

        owned_excluded = 0
        for c in unique_candidates:
            provider_ids = self._candidate_provider_ids(c)
            if provider_ids and provider_ids & owned_ids:
                owned_excluded += 1
                continue
            if self._title_is_owned(c.title, c.media_type, owned_titles):
                owned_excluded += 1
                continue
            external_candidates.append(c)

        upstream_duplicates = int(self._discovery_stats.get("duplicates_removed", 0) or 0)
        self._discovery_stats.update({
            "anime_library_count": len(self.library_items),
            "usable_seeds": len(seed_ids),
            "preferred_genres": len(genre_names),
            "candidates_before_dedup": len(all_discovered) + upstream_duplicates,
            "duplicates_removed": duplicates_removed + upstream_duplicates,
            "owned_candidates_excluded": owned_excluded,
            "final_external_candidates": len(external_candidates),
        })

        # Add external candidates to the candidate list.
        for c in external_candidates:
            candidates.append(RankingCandidate(
                item=c,
                score=0.0,
                reasons=[],
                similarity=self._compute_similarity(c, profile),
                category=category,
                is_plan_to_watch=False,
                is_new_discovery=True,
                is_similar=False,
                discovery_source=c.discovery_source or "external",
                recommendation_signal=float(getattr(c, "recommendation_signal", 0.0) or 0.0),
                recommendation_reasons=list(getattr(c, "recommendation_reasons", []) or []),
            ))

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

        # Record the external candidate counts for the empty-state outcome.
        self._external_candidates = all_discovered
        self._external_candidates_after_owned = len(external_candidates)

        return candidates

    def _compute_similarity(self, item, profile) -> SimilarityScore:
        """Compute similarity between a candidate and the user's profile."""
        positive_seeds = sorted(
            (seed for seed in self.library_items if _activity_signal(seed) > 0.15),
            key=_activity_signal,
            reverse=True,
        )[:10]
        if not positive_seeds:
            return SimilarityScore()
        return max((anime_similarity(item, seed) for seed in positive_seeds), key=lambda value: value.total)

    def _score_and_rank(
        self,
        candidates: list[RankingCandidate],
        profile: UserProfile,
        category: str,
    ) -> list[RecommendationResult]:
        """Score candidates and return a ranked list of RecommendationResult."""
        if not candidates:
            return []

        scorer = RecommendationScorer(profile)

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
                title_ja=rec.title_ja,
                episodes=rec.episodes,
                provider_key=rec.provider_key,
                provider_id=rec.provider_id,
                is_cached=rec.is_cached,
            ))
        return results

    def _determine_outcome(
        self,
        profile: UserProfile,
        results: list["RecommendationResult"],
    ) -> None:
        """Decide why the final list is empty (or not) and store it on the engine.

        The outcome is exposed via :meth:`get_preference_summary` so the UI can
        present a truthful empty state.  Provider/network failures are tracked
        separately so they are never confused with an empty discovery response.
        """
        has_prefs = bool(profile and profile.has_preferences())
        candidates_before_owned = len(self._external_candidates)
        candidates_after_owned = self._external_candidates_after_owned
        failures = self._discovery_failures

        if not has_prefs:
            self._last_outcome = "insufficient_preference_data"
        elif results:
            self._last_outcome = "valid_recommendations"
        elif failures > 0 and candidates_before_owned == 0:
            self._last_outcome = "provider_failure"
        elif candidates_before_owned == 0:
            if (
                self._discovery_stats.get("usable_seeds", 0) == 0
                and self._discovery_stats.get("preferred_genres", 0) > 0
                and self._discovery_stats.get("genre_ids_mapped", 0) > 0
            ):
                self._last_outcome = "no_matching_genre_candidates"
            elif self._discovery_stats.get("usable_seeds", 0) == 0 and self._discovery_stats.get("preferred_genres", 0) == 0:
                self._last_outcome = "no_usable_mal_seeds"
            else:
                self._last_outcome = "no_external_candidates"
        elif candidates_after_owned == 0:
            self._last_outcome = "all_excluded_owned"
        elif not results:
            self._last_outcome = "all_excluded_filter"
        else:
            self._last_outcome = "valid_recommendations"

    def get_preference_summary(self) -> dict:
        """Return a summary of the user's preferences.

        Also reports the outcome of the most recent :meth:`get_recommendations`
        run via ``recommendation_status`` so the UI can present truthful empty
        states (insufficient data, no candidates, provider/network failure,
        all owned, all filtered, valid).
        """
        profile = self.profile
        if not profile or not getattr(profile, "signal_values", None):
            return {
                "status": "insufficient_data",
                "recommendation_status": "insufficient_preference_data",
            }
        sv = profile.signal_values
        return {
            "has_preferences": profile.has_preferences(),
            "recommendation_status": self._last_outcome
            if self._last_outcome
            else "none",
            "discovery_errors": list(self._discovery_errors),
            "discovery_stats": dict(self._discovery_stats),
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
