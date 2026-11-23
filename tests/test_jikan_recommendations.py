"""Offline tests for Jikan recommendations and the preference profile."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from animevault.models.anime import Anime
from animevault.services.providers.base import AnimeMetadata, ProviderError
from animevault.services.providers.jikan import JikanProvider
from animevault.services.jikan_recommendation_service import JikanRecommendationService
from animevault.services.user_preference_analyzer import analyze_preferences


def _anime(title, **kwargs):
    base = {"id": None, "title": title, "genres": [], "source_provider": "test"}
    base.update(kwargs)
    return Anime(**base)


def test_preferences_weight_tiers_and_favorites_without_double_counting():
    favorite = _anime("Loved", status="completed", tier="SSS", favorite=True, genres=["Fantasy", "Adventure"])
    low = _anime("Okay", status="completed", tier="B", genres=["Fantasy"])
    profile = analyze_preferences([favorite, low])
    assert profile.genre_weights["fantasy"] > profile.genre_weights["adventure"]
    assert profile.top_genres()[0][0] == "fantasy"
    assert profile.tier_weights["SSS"] > profile.tier_weights["B"]


def test_dropped_titles_create_negative_genre_weights_and_plan_only_is_neutral():
    profile = analyze_preferences([
        _anime("Dropped", status="dropped", genres=["Horror"]),
        _anime("Planned", status="plan_to_watch", genres=["Fantasy"]),
    ])
    assert profile.negative_genre_weights["horror"] > 0
    assert "fantasy" not in profile.genre_weights


def test_duplicate_conflicting_entries_count_once_using_strongest_signal():
    high = _anime("Same Show", mal_id=91, status="completed", tier="SSS", genres=["Fantasy"])
    dropped_duplicate = _anime("Same Show (alt)", mal_id=91, status="dropped", genres=["Horror"])
    profile = analyze_preferences([high, dropped_duplicate])
    assert "fantasy" in profile.genre_weights
    assert "horror" not in profile.negative_genre_weights
    assert profile.signal_values.completed_count == 1


def test_missing_score_is_not_negative_and_empty_input_is_safe():
    profile = analyze_preferences([_anime("Unrated", status="completed", genres=["Drama"])])
    assert profile.genre_weights["drama"] > 0
    assert not profile.negative_genre_weights
    assert not analyze_preferences([]).has_preferences()


def test_jikan_recommendation_endpoint_parses_and_deduplicates_metadata():
    response = {
        "data": [
            {"entry": {"mal_id": 15, "title": "Candidate", "type": "TV", "images": {"jpg": {"image_url": "https://img"}}}, "votes": 8},
            {"entry": {"mal_id": 16, "title": "Other", "type": "Movie"}, "votes": 3},
            {"entry": {"title": "Missing ID"}, "votes": "bad"},
            None,
        ]
    }
    provider = JikanProvider()
    with patch.object(provider, "_throttle"), patch("animevault.services.providers.jikan._jikan_get", return_value=response) as get:
        related = provider.get_recommendations(1, limit=1)
    assert get.call_args.args[0].endswith("/anime/1/recommendations")
    assert len(related) == 1
    assert related[0][0].mal_id == 15 and related[0][1] == 8


def test_jikan_timeout_is_reported_as_retryable_provider_error():
    from urllib.error import URLError

    provider = JikanProvider()
    with patch("animevault.services.providers.jikan.urllib.request.urlopen", side_effect=URLError(TimeoutError("timed out"))):
        try:
            provider._get_with_retry("https://api.jikan.moe/v4/anime/1/recommendations", attempts=1)
        except ProviderError as exc:
            assert exc.retryable
            assert "network error" in str(exc).lower()
        else:
            raise AssertionError("timeout was not propagated as ProviderError")


def test_jikan_invalid_json_shape_and_empty_response_are_safe():
    provider = JikanProvider()
    with patch.object(provider, "_throttle"), patch("animevault.services.providers.jikan._jikan_get", return_value=[]):
        try:
            provider.get_recommendations(1)
        except ProviderError as exc:
            assert not exc.retryable
        else:
            raise AssertionError("non-object API payload should be rejected")
    with patch.object(provider, "_throttle"), patch("animevault.services.providers.jikan._jikan_get", return_value={"data": []}):
        assert provider.get_recommendations(1) == []


def test_jikan_retryable_failure_retries_once_with_backoff():
    provider = JikanProvider()
    with patch.object(provider, "_throttle"), \
         patch("animevault.services.providers.jikan.time.sleep"), \
         patch("animevault.services.providers.jikan._jikan_get", side_effect=[ProviderError("busy", 503, True), {"data": []}]) as get:
        assert provider.get_recommendations(123) == []
    assert get.call_count == 2


class _CachedProvider:
    def __init__(self):
        self.calls = 0

    def get_recommendations(self, mal_id, limit=10):
        self.calls += 1
        return [(AnimeMetadata(title="Jikan candidate", mal_id=77, media_type="TV", genres=["Fantasy"], synopsis="Description", studios=["Studio A"]), 12)]

    def get_details(self, provider_id):
        raise AssertionError("complete cached metadata should not trigger detail fetch")


def test_jikan_service_deduplicates_by_mal_id_across_seeds(tmp_path):
    class DuplicateProvider:
        def get_recommendations(self, mal_id, limit=10):
            return [(AnimeMetadata(title="Same", mal_id=77, media_type="TV", genres=["Fantasy"], synopsis="ok"), 10)]

        def get_details(self, provider_id):
            raise AssertionError("metadata is already complete")

    service = JikanRecommendationService(DuplicateProvider(), cache_dir=tmp_path)
    results = service.recommendations_for([(1, "Seed A"), (2, "Seed B")])
    assert len(results) == 1
    assert results[0].mal_id == 77


def test_jikan_cache_hit_and_metadata_are_not_library_records(tmp_path):
    provider = _CachedProvider()
    service = JikanRecommendationService(provider, cache_dir=tmp_path)
    first = service.recommendations_for([(1, "Seed")])
    second = service.recommendations_for([(1, "Seed")])
    assert first[0].mal_id == second[0].mal_id == 77
    assert not first[0].is_cached and second[0].is_cached
    assert first[0].recommendation_signal > 0
    assert first[0].recommendation_reasons
    assert provider.calls == 1
    assert len(list(Path(tmp_path).glob("recommendations_*.json"))) == 1


def test_empty_jikan_response_is_cached_to_prevent_repeat_requests(tmp_path):
    class EmptyProvider:
        calls = 0

        def get_recommendations(self, mal_id, limit=10):
            self.calls += 1
            return []

    provider = EmptyProvider()
    service = JikanRecommendationService(provider, cache_dir=tmp_path)
    assert service.recommendations_for([(3, "No related entries")]) == []
    assert service.recommendations_for([(3, "No related entries")]) == []
    assert provider.calls == 1


def test_jikan_stale_cache_is_used_when_provider_fails(tmp_path):
    class Failing:
        def get_recommendations(self, mal_id, limit=10):
            raise ProviderError("offline", retryable=True)

        def get_details(self, provider_id):
            raise AssertionError

    seed_provider = _CachedProvider()
    JikanRecommendationService(seed_provider, cache_dir=tmp_path, ttl_seconds=0).recommendations_for([(2, "Seed")])
    fallback = JikanRecommendationService(Failing(), cache_dir=tmp_path, ttl_seconds=0).recommendations_for([(2, "Seed")])
    assert len(fallback) == 1 and fallback[0].mal_id == 77
