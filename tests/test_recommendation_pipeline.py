"""Regression tests for the recommendation pipeline.

These tests cover owned-item exclusion, candidate deduplication, candidate
validation, empty-state truthfulness, eligibility, and scoring/ranking
stability.  All external discovery is mocked: no live network access is used.

The public API used here is :class:`animevault.services.recommendation_engine
.RecommendationEngine` (with ``online_discovery`` forced off / a mocked
discovery hook), plus the :class:`RecommendationScorer` in isolation.
"""

from __future__ import annotations

import pytest

from animevault.models.anime import Anime
from animevault.services.recommendation_engine import (
    RecommendationEngine,
    RecommendationScorer,
    RecommendationResult,
    RecommendationSet,
    Recommendation,
    RankingCandidate,
    SimilarityScore,
)
from animevault.services.user_preference_analyzer import (
    UserProfile,
    SignalValues,
)
from animevault.services.recommendation_discovery import Candidate


# ── Helpers ──────────────────────────────────────────────────────────────

def make_anime(title, **overrides):
    """Build an in-memory Anime record with sensible defaults."""
    base = dict(
        id=len(title) % 1000,  # stable-ish deterministic id per title
        title=title,
        title_ja="",
        episodes=12,
        status="completed",
        score=None,
        tier=None,
        notes="",
        favorite=False,
        genres=[],
        media_type="",
    )
    base.update(overrides)
    return Anime(**base)


def make_candidate(title, **overrides):
    """Build a :class:`Candidate` for external discovery."""
    defaults = dict(
        item_id=0,
        title=title,
        title_en="",
        title_ja="",
        title_romaji="",
        media_type="ANIME",
        genres=[],
        synopsis="",
        poster_url="",
        mal_id=0,
        anilist_id=0,
        kitsu_id="",
        tmdb_id=0,
        discovery_source="mock",
    )
    defaults.update(overrides)
    return Candidate(**defaults)


def empty_profile(genre_affinity=None):
    """Build a UserProfile with no ratings/tiers/favorites but with
    (optional) genre affinity so ``has_preferences()`` is True."""
    sv = SignalValues(
        ratings=[],
        score_avg=0.0,
        per_genre_ratings={},
        per_genre_avg={},
        tier_placed=[],
        tier_by_genre={},
        favorites=[],
        watched_count=0,
        episodes_watched=0,
        total_episodes=0,
        completed_count=0,
        dropped_count=0,
        plan_count=0,
        progress={},
        genre_affinity=genre_affinity or {},
        metadata_count=0,
    )
    return UserProfile(
        signal_values=sv,
        genre_weights={},
        tier_weights={},
        favorite_signal=1.0,
        metadata_weights={},
        watch_engagement=0.0,
        profile_doc=[],
    )


def build_engine(library, *, online_discovery=True, discover=None):
    """Create an engine whose external discovery returns *discover* (a list or
    a callable).  The hook is injected into the engine module so it is used
    exactly as the real :func:`discover_candidates` call site would use it."""
    class _NoJikan:
        @staticmethod
        def recommendations_for(*args, **kwargs):
            return []

    engine = RecommendationEngine(
        library_items=library,
        user_hash="test",
        online_discovery=online_discovery,
        jikan_service=_NoJikan(),
    )
    if discover is not None:

        def _fake_discover(*args, **kwargs):
            if callable(discover):
                return discover(*args, **kwargs)
            return discover

        import animevault.services.recommendation_engine as re_module

        re_module.discover_candidates = _fake_discover
    return engine


# ── Owned-item exclusion ─────────────────────────────────────────────────

class TestOwnedItemExclusion:
    def test_same_numeric_id_from_different_provider_is_not_owned(self):
        library = [make_anime("Same Title", id=42, status="completed", genres=["Action"], mal_id=1)]
        candidate = make_candidate("Same Title", anilist_id=1, genres=["Action"])
        engine = build_engine(library, online_discovery=True, discover=[candidate])
        results = engine.get_recommendations()
        assert any(result.title == "Same Title" and result.provider_key == "anilist_id" for result in results)

    def test_library_item_never_recommended(self):
        library = [make_anime("One Piece", id=42, status="watching", genres=["Action"])]
        engine = build_engine(
            library,
            online_discovery=True,
            discover=[make_candidate("One Piece")],
        )
        results = engine.get_recommendations()
        assert results == []
        assert engine._last_outcome == "all_excluded_owned"

    def test_owned_by_provider_id_excluded_even_on_different_title(self):
        # The library item has an AniList id; the external candidate carries the
        # same MAL id but a different title.  The provider id must exclude it.
        library = [make_anime("One Piece", id=42, mal_id=42, anilist_id=7, genres=["Action"])]
        engine = build_engine(
            library,
            online_discovery=True,
            discover=[make_candidate("Sword Art Online", mal_id=42)],
        )
        results = engine.get_recommendations()
        assert results == []
        assert engine._last_outcome == "all_excluded_owned"

    def test_case_insensitive_owned_removal(self):
        library = [make_anime("BersERK", id=1, status="completed", genres=["Action"])]
        engine = build_engine(
            library,
            online_discovery=True,
            discover=[make_candidate("berserk")],
        )
        results = engine.get_recommendations()
        assert results == []
        assert engine._last_outcome == "all_excluded_owned"

    def test_owned_title_fallback_uses_normalized_title(self):
        library = [make_anime("Cowboy Bebop", id=1, status="watching", genres=["Action"])]
        engine = build_engine(
            library,
            online_discovery=True,
            discover=[
                make_candidate("Cowboy Bebop"),  # exact normalized title -> owned
                make_candidate("Cowboy Bebop: Tengoku no Tobira"),  # distinct -> not owned
            ],
        )
        results = engine.get_recommendations()
        titles = {r.title for r in results}
        # The owned (identical normalized title) item must be excluded...
        assert "Cowboy Bebop" not in titles
        # ...but a distinct work sharing the phrase must not be removed.
        assert "Cowboy Bebop: Tengoku no Tobira" in titles


# ── Status-based exclusion (plan/watching/completed/hold/dropped) ────────

class TestStatusBasedExclusion:
    @pytest.mark.parametrize("status", ["plan_to_watch", "watching", "completed", "on_hold", "dropped"])
    def test_library_items_of_any_status_are_excluded(self, status):
        # Planned titles are neutral and dropped titles are negative unless an
        # explicit strong rating supplies a positive seed for this exclusion test.
        extras = {"favorite": True} if status == "plan_to_watch" else ({"score": 9} if status == "dropped" else {})
        library = [make_anime("Local Show", id=1, status=status, genres=["Action"], **extras)]
        engine = build_engine(
            library,
            online_discovery=True,
            discover=[make_candidate("External Show")],
        )
        results = engine.get_recommendations()
        titles = {r.title for r in results}
        assert "Local Show" not in titles
        assert "External Show" in titles
        assert len(results) == 1


# ── Deduplication ────────────────────────────────────────────────────────

class TestDeduplication:
    def test_case_insensitive_duplicates_removed(self):
        library = [make_anime("Reference", id=1, genres=["Action"])]
        engine = build_engine(
            library,
            online_discovery=True,
            discover=[make_candidate("ONE PIECE"), make_candidate("One Piece")],
        )
        results = engine.get_recommendations()
        # The two providers returned the same title -- they must collapse to one.
        assert len(results) == 1

    def test_whitespace_variants_removed(self):
        library = [make_anime("Reference", id=1, genres=["Action"])]
        engine = build_engine(
            library,
            online_discovery=True,
            discover=[
                make_candidate("  One Piece  "),
                make_candidate("One Piece"),
            ],
        )
        results = engine.get_recommendations()
        assert len(results) == 1

    def test_punctuation_variants_removed(self):
        library = [make_anime("Reference", id=1, genres=["Action"])]
        engine = build_engine(
            library,
            online_discovery=True,
            discover=[make_candidate("Naruto!!"), make_candidate("Naruto")],
        )
        results = engine.get_recommendations()
        assert len(results) == 1

    def test_same_title_differs_by_media_type_not_merged(self):
        library = [make_anime("Reference", id=1, genres=["Action"])]
        engine = build_engine(
            library,
            online_discovery=True,
            discover=[
                make_candidate("Test Anime", media_type="ANIME"),
                make_candidate("Test Anime", media_type="MOVIE"),
            ],
        )
        results = engine.get_recommendations()
        # Media types differ, so two distinct works stay separate.
        assert len(results) == 2

    def test_different_provider_ids_keep_same_title_separate(self):
        library = [make_anime("Reference", id=1, genres=["Action"])]
        engine = build_engine(
            library,
            online_discovery=True,
            discover=[
                make_candidate("Berserk", anilist_id=10, item_id=10),
                make_candidate("Berserk", mal_id=20, item_id=20),
            ],
        )
        results = engine.get_recommendations()
        # Both providers have the same title but different provider ids ->
        # distinct works, so both are kept.
        assert len(results) == 2
        assert {r.item_id for r in results} == {10, 20}

    def test_duplicate_candidates_from_multiple_providers_removed(self):
        library = [make_anime("Reference", id=1, genres=["Action"])]
        engine = build_engine(
            library,
            online_discovery=True,
            discover=[
                make_candidate("Naruto", anilist_id=1, mal_id=1),
                make_candidate("Naruto", anilist_id=1, mal_id=1),
            ],
        )
        results = engine.get_recommendations()
        # The same work requested twice still collapses to one.
        assert len(results) == 1


# ── Recommendation eligibility (extracted from engine rules) ─────────────

class TestRecommendationEligibility:
    def test_sparse_ratings_do_not_kill_genre_preferences(self):
        anime = make_anime("One Piece", id=1, genres=["Action", "Adventure"], score=9)
        engine = build_engine([anime], online_discovery=False)
        results = engine.get_recommendations()
        # A library with a single highly-rated, good-genre item still yields
        # a usable profile (it may have no external candidates, but the
        # eligibility check must not crash and must report preferences).
        summary = engine.get_preference_summary()
        assert summary["has_preferences"] is True
        assert engine._last_outcome in {
            "no_external_candidates",
            "valid_recommendations",
        }

    def test_missing_scores_handled_safely(self):
        anime = make_anime("Test", id=1, genres=["Action"], score=None)
        engine = build_engine([anime], online_discovery=False)
        results = engine.get_recommendations()
        summary = engine.get_preference_summary()
        assert summary["has_preferences"] is True
        assert results == []

    def test_empty_profile_safe(self):
        engine = build_engine([], online_discovery=False)
        results = engine.get_recommendations()
        assert results == []
        summary = engine.get_preference_summary()
        assert summary["recommendation_status"] == "insufficient_preference_data"

    def test_cached_profile_missing_signal_values_does_not_crash(self):
        engine = build_engine([], online_discovery=False)
        profile = UserProfile(signal_values=None)
        engine._category_profiles["all"] = profile
        summary = engine.get_preference_summary()
        assert summary["recommendation_status"] == "insufficient_preference_data"

    def test_library_entries_not_treated_as_new_discoveries(self):
        library = [make_anime("One Piece", id=1, status="watching", genres=["Action"])]
        engine = build_engine(library, online_discovery=False)
        res = engine.get_recommendations()
        # All local items are owned and therefore excluded; none may be
        # surfaced as new discoveries.
        assert all(not r.is_new_discovery for r in res)


# ── Empty states ─────────────────────────────────────────────────────────

class TestEmptyStates:
    def test_empty_library_truthful_state(self):
        engine = build_engine([], online_discovery=False)
        results = engine.get_recommendations()
        assert results == []
        summary = engine.get_preference_summary()
        assert summary["recommendation_status"] == "insufficient_preference_data"

    def test_preferences_but_no_external_candidates(self):
        library = [make_anime("One Piece", id=1, genres=["Action"])]
        engine = build_engine(
            library,
            online_discovery=True,
            discover=[],  # provider returned nothing
        )
        results = engine.get_recommendations()
        assert results == []
        summary = engine.get_preference_summary()
        assert summary["recommendation_status"] == "no_external_candidates"

    def test_provider_failure_distinguishable_from_empty_response(self):
        library = [make_anime("One Piece", id=1, genres=["Action"])]
        engine = build_engine(
            library,
            online_discovery=True,
            discover=lambda q, cats, lim: (_ for _ in ()).throw(RuntimeError("network down")),
        )
        results = engine.get_recommendations()
        assert results == []
        summary = engine.get_preference_summary()
        assert summary["recommendation_status"] == "provider_failure"

    def test_all_excluded_owned_control_flow(self):
        library = [make_anime("Sailor Moon", id=1, status="completed", genres=["Action"])]
        engine = build_engine(
            library,
            online_discovery=True,
            discover=[make_candidate("Sailor Moon")],
        )
        results = engine.get_recommendations()
        assert results == []
        assert engine._last_outcome == "all_excluded_owned"

    def test_all_removed_by_filter_control_flow(self):
        library = [make_anime("One Piece", id=1, genres=["Action"])]
        engine = build_engine(
            library,
            online_discovery=True,
            discover=[make_candidate("External Show")],
        )
        # min_score excludes the candidate.
        results = engine.get_recommendations(min_score=1.0)
        assert results == []
        assert engine._last_outcome == "all_excluded_filter"


# ── Scoring and ranking remain stable ────────────────────────────────────

class TestScoringAndRanking:
    def test_genre_weights_rank_higher_match_first(self):
        library = [make_anime("Action Show", id=1, genres=["Action"], score=9),
                   make_anime("Romance Show", id=2, genres=["Romance"], score=8)]
        engine = build_engine(library, online_discovery=False)
        profile = engine.category_profile("all")
        score1 = engine.category_profile("all")
        # Build two ranking candidates by hand.
        cand_action = RankingCandidate(
            item=Anime(id=10, title="Action Show", genres=["Action"], score=9),
            score=0.0, reasons=[], similarity=SimilarityScore(),
            category="all", is_plan_to_watch=False, is_new_discovery=False,
            is_similar=False, discovery_source="local",
        )
        cand_romance = RankingCandidate(
            item=Anime(id=11, title="Romance Show", genres=["Romance"], score=8),
            score=0.0, reasons=[], similarity=SimilarityScore(),
            category="all", is_plan_to_watch=False, is_new_discovery=False,
            is_similar=False, discovery_source="local",
        )
        scorer = RecommendationScorer(profile, weights={
            "genre_theme_similarity": 0.25,
            "similarity_to_highly_rated": 0.25,
            "tier_placement": 0.15,
            "favorite_status": 0.15,
            "watch_engagement": 0.10,
            "metadata_similarity": 0.10,
        })
        ranked = scorer.rank_candidates([cand_action, cand_romance],
                                        profile.genre_weights)
        assert ranked[0].title == "Action Show"

    def test_scores_are_clamped_between_zero_and_one(self):
        library = [make_anime("One Piece", id=1, genres=["Action"])]
        engine = build_engine(library, online_discovery=False)
        profile = engine.category_profile("all")
        scorer = RecommendationScorer(profile, weights={
            "genre_theme_similarity": 0.25,
            "similarity_to_highly_rated": 0.25,
            "tier_placement": 0.15,
            "favorite_status": 0.15,
            "watch_engagement": 0.10,
            "metadata_similarity": 0.10,
        })
        cand = RankingCandidate(
            item=Anime(id=2, title="X", genres=[]),
            score=0.0, reasons=[], similarity=SimilarityScore(),
            category="all", is_plan_to_watch=False, is_new_discovery=False,
            is_similar=False, discovery_source="local",
        )
        score, _ = scorer.score_candidate(cand, profile.genre_weights)
        assert 0.0 <= score <= 1.0

    def test_ranking_is_deterministic(self):
        library = [make_anime("One Piece", id=1, genres=["Action"])]
        engine = build_engine(library, online_discovery=False)
        profile = engine.category_profile("all")
        cand_a = RankingCandidate(
            item=Anime(id=3, title="Aa", genres=["Action"]),
            score=0.0, reasons=[], similarity=SimilarityScore(),
            category="all", is_plan_to_watch=False, is_new_discovery=False,
            is_similar=False, discovery_source="local",
        )
        cand_b = RankingCandidate(
            item=Anime(id=4, title="Bb", genres=["Action"]),
            score=0.0, reasons=[], similarity=SimilarityScore(),
            category="all", is_plan_to_watch=False, is_new_discovery=False,
            is_similar=False, discovery_source="local",
        )
        scorer = RecommendationScorer(profile, weights={
            "genre_theme_similarity": 0.25,
            "similarity_to_highly_rated": 0.25,
            "tier_placement": 0.15,
            "favorite_status": 0.15,
            "watch_engagement": 0.10,
            "metadata_similarity": 0.10,
        })
        first = scorer.rank_candidates([cand_a, cand_b], profile.genre_weights)
        second = scorer.rank_candidates([cand_a, cand_b], profile.genre_weights)
        assert [r.title for r in first] == [r.title for r in second]


# ── Result model ─────────────────────────────────────────────────────────

class TestResultModel:
    def test_recommendation_set_status_exposed(self):
        result = RecommendationResult(
            item_id=1, title="Test", media_type="Anime", category="all",
            genres=[], synopsis="", score=0.5, reasons=[],
        )
        assert result.score == 0.5
        assert result.media_type == "Anime"

    def test_recommendation_set_aggregates(self):
        results = [
            RecommendationResult(item_id=1, title="A", media_type="Anime",
                                 category="all", genres=[], synopsis="",
                                 score=0.5, reasons=[]),
            RecommendationResult(item_id=2, title="B", media_type="Anime",
                                 category="all", genres=[], synopsis="",
                                 score=0.5, reasons=[], is_plan_to_watch=True),
        ]
        s = RecommendationSet(category="all", results=results)
        assert s.new_discoveries == []
        assert s.planned == [results[1]]
        assert s.similar == []


# ── Regression: watch engagement must stay within [0, 1] ──────────────

class TestWatchEngagementClamp:
    def test_watch_engagement_never_exceeds_one(self):
        # episodes_watched > episodes would push the raw ratio above 1.0;
        # the analyzer clamps it so engagement stays in [0, 1].
        anime = make_anime("Overwatch", id=7, episodes=12, episodes_watched=20)
        engine = build_engine([anime], online_discovery=False)
        profile = engine.category_profile("all")
        assert 0.0 <= profile.watch_engagement <= 1.0

    def test_literature_progress_method_is_resolved_before_int_conversion(self):
        from animevault.models.literature import Literature

        item = Literature(id=22, title="Progress Method", chapters=10, chapters_read=4)
        candidate = RankingCandidate(
            item=item, score=0.0, reasons=[], similarity=SimilarityScore(),
            category="all", is_plan_to_watch=False, is_new_discovery=False,
            is_similar=False, discovery_source="local",
        )
        ranked = RecommendationScorer(empty_profile()).rank_candidates([candidate], {})
        assert ranked[0].progress_percent == 40

    def test_watch_engagement_zero_when_no_episodes(self):
        anime = make_anime("Nothing", id=8, episodes=0, episodes_watched=0)
        engine = build_engine([anime], online_discovery=False)
        profile = engine.category_profile("all")
        assert profile.watch_engagement == 0.0
