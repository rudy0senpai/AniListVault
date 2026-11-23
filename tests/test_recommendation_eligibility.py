"""Tests for recommendation eligibility (has_preferences)."""

import pytest

from animevault.models.anime import Anime
from animevault.services.user_preference_analyzer import analyze_preferences


class TestRecommendationEligibility:
    def test_empty_library_returns_false(self):
        profile = analyze_preferences([])
        assert profile.has_preferences() is False

    def test_unweighted_genres_without_user_activity_are_not_preferences(self):
        anime = Anime(id=None, title="Test", genres=["Action", "Drama"], source_provider="anilist")
        profile = analyze_preferences([anime])
        assert profile.has_preferences() is False

    def test_library_without_genres_or_signals_returns_false(self):
        anime = Anime(id=None, title="Test", source_provider="anilist")
        profile = analyze_preferences([anime])
        assert profile.has_preferences() is False

    def test_library_with_ratings_returns_true(self):
        anime = Anime(id=None, title="Test", score=8, source_provider="anilist")
        profile = analyze_preferences([anime])
        assert profile.has_preferences() is True

    def test_library_with_favorites_returns_true(self):
        anime = Anime(id=None, title="Test", favorite=True, source_provider="anilist")
        profile = analyze_preferences([anime])
        assert profile.has_preferences() is True

    def test_library_with_tier_assignments_returns_true(self):
        anime = Anime(id=None, title="Test", tier="SSS", source_provider="anilist")
        profile = analyze_preferences([anime])
        assert profile.has_preferences() is True

    def test_library_with_watch_progress_returns_true(self):
        anime = Anime(id=None, title="Test", episodes=12, episodes_watched=6, source_provider="anilist")
        profile = analyze_preferences([anime])
        assert profile.has_preferences() is True

    def test_library_with_only_plan_to_watch_returns_false(self):
        anime = Anime(id=None, title="Test", status="plan_to_watch", source_provider="anilist")
        profile = analyze_preferences([anime])
        assert profile.has_preferences() is False