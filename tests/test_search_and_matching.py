"""Tests for SearchService, provider fallback, and candidate ranking."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from animevault.services import cache
from animevault.services.providers.base import AnimeMetadata, BaseProvider, ProviderError
from animevault.services.search import SearchService, calculate_match_score


class DummyProvider(BaseProvider):
    def __init__(self, name: str, results: list[AnimeMetadata] | Exception) -> None:
        self._name = name
        self._results = results
        self.call_count = 0

    @property
    def name(self) -> str:
        return self._name

    def search(self, query: str, limit: int = 10) -> list[AnimeMetadata]:
        self.call_count += 1
        if isinstance(self._results, Exception):
            raise self._results
        return self._results

    def get_details(self, provider_id: str) -> AnimeMetadata:
        return AnimeMetadata(title="Dummy")


class TestSearchAndMatching:
    def setup_method(self):
        cache.clear_all()

    def test_search_success(self):
        meta = AnimeMetadata(title="Naruto", anilist_id=20, episodes=220, source_provider="mock")
        provider = DummyProvider("mock", [meta])
        service = SearchService(providers=[provider])

        results = service.search("Naruto")
        assert len(results) == 1
        assert results[0].title == "Naruto"
        assert results[0].anilist_id == 20
        assert provider.call_count == 1

    def test_search_no_results(self):
        provider = DummyProvider("mock", [])
        service = SearchService(providers=[provider])

        results = service.search("UnknownNonExistentAnimeXYZ")
        assert results == []

    def test_provider_fallback(self):
        # Provider 1 fails with 504 server error
        p1 = DummyProvider("failing_provider", ProviderError("504 Gateway Timeout", status_code=504))
        # Provider 2 succeeds
        meta = AnimeMetadata(title="Naruto", kitsu_id="11", episodes=220, source_provider="kitsu")
        p2 = DummyProvider("fallback_provider", [meta])

        service = SearchService(providers=[p1, p2])
        results = service.search("Naruto")

        assert len(results) == 1
        assert results[0].title == "Naruto"
        assert results[0].kitsu_id == "11"
        assert p1.call_count == 1
        assert p2.call_count == 1

    def test_permanent_provider_errors_are_not_reported_as_not_found(self):
        provider = DummyProvider(
            "blocked_provider",
            ProviderError("403 Forbidden", status_code=403, retryable=False),
        )
        service = SearchService(providers=[provider])
        with pytest.raises(ProviderError) as exc_info:
            service.search("Any title")
        assert exc_info.value.status_code == 403
        assert exc_info.value.provider == "blocked_provider"

    def test_candidate_ranking_exact_match(self):
        m1 = AnimeMetadata(title="Boruto: Naruto Next Generations", episodes=293)
        m2 = AnimeMetadata(title="Naruto: Shippuuden", episodes=500)
        m3 = AnimeMetadata(title="Naruto", episodes=220)

        # "Naruto" exact query should rank m3 highest
        score_exact = calculate_match_score("Naruto", m3)
        score_sequel = calculate_match_score("Naruto", m2)
        score_spinoff = calculate_match_score("Naruto", m1)

        assert score_exact > score_sequel > score_spinoff

    def test_empty_result_is_not_cached_as_a_transient_failure(self):
        provider = DummyProvider("mock", [])
        service = SearchService(providers=[provider])

        service.search("Temporarily unavailable title")
        service.search("Temporarily unavailable title")

        assert provider.call_count == 2

    def test_force_refresh_bypasses_successful_cache(self):
        first = AnimeMetadata(title="Title", anilist_id=1, synopsis="old")
        refreshed = AnimeMetadata(title="Title", anilist_id=1, synopsis="new")
        provider = DummyProvider("mock", [first])
        service = SearchService(providers=[provider])

        assert service.search("Title")[0].synopsis == "old"
        provider._results = [refreshed]
        assert service.search("Title", force_refresh=True)[0].synopsis == "new"
        assert provider.call_count == 2

    def test_search_results_cached(self):
        meta = AnimeMetadata(title="Frieren", anilist_id=154587, episodes=28, source_provider="mock")
        provider = DummyProvider("mock", [meta])
        service = SearchService(providers=[provider])

        # First call hits provider
        res1 = service.search("Frieren")
        assert len(res1) == 1
        assert provider.call_count == 1

        # Second call hits cache
        res2 = service.search("Frieren")
        assert len(res2) == 1
        assert res2[0].title == "Frieren"
        assert provider.call_count == 1  # Not called again
