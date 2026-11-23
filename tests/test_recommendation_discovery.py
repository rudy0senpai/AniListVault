from __future__ import annotations

from unittest.mock import patch

from animevault.services.providers.base import AnimeMetadata
from animevault.services.recommendation_discovery import Candidate, discover_candidates


class FakeProvider:
    name = "fake"

    def __init__(self, rows):
        self.rows = rows

    def search(self, query, limit=10):
        return self.rows

    def get_details(self, provider_id):
        raise AssertionError("search results are already normalized")


def test_discover_candidates_appends_and_preserves_multiple_provider_results():
    provider = FakeProvider([
        AnimeMetadata(title="Alpha", mal_id=11, media_type="TV", genres=["Action"]),
        AnimeMetadata(title="Beta", anilist_id=22, media_type="Movie", genres=["Drama"]),
    ])
    with patch("animevault.services.recommendation_discovery._get_provider", return_value=provider):
        found = discover_candidates("query", providers=["fake"], limit=10)
    assert [item.title for item in found] == ["Alpha", "Beta"]
    assert found[0].mal_id == 11 and found[0].item_id == 11
    assert found[1].anilist_id == 22 and found[1].item_id == 22


def test_discovery_category_filter_and_media_types_are_preserved():
    provider = FakeProvider([
        AnimeMetadata(title="Action Show", mal_id=1, media_type="TV", genres=["Action"]),
        AnimeMetadata(title="Drama Film", mal_id=2, media_type="Movie", genres=["Drama"]),
    ])
    with patch("animevault.services.recommendation_discovery._get_provider", return_value=provider):
        found = discover_candidates("query", categories=["action"], providers=["fake"])
    assert [(item.title, item.media_type) for item in found] == [("Action Show", "TV")]


def test_empty_or_malformed_provider_responses_are_safe():
    provider = FakeProvider([None, {"not": "metadata"}])
    with patch("animevault.services.recommendation_discovery._get_provider", return_value=provider):
        assert discover_candidates("query", providers=["fake"]) == []
    with patch("animevault.services.recommendation_discovery._get_provider", return_value=FakeProvider([])):
        assert discover_candidates("query", providers=["fake"]) == []


def test_discovery_deduplicates_ids_without_collapsing_media_types():
    provider = FakeProvider([
        AnimeMetadata(title="Same", mal_id=99, media_type="TV", genres=["Action"]),
        AnimeMetadata(title="Same alt", mal_id=99, media_type="TV", genres=["Action"]),
        AnimeMetadata(title="Same", mal_id=100, media_type="Movie", genres=["Action"]),
    ])
    with patch("animevault.services.recommendation_discovery._get_provider", return_value=provider):
        found = discover_candidates("query", providers=["fake"])
    assert len(found) == 2
    assert {item.media_type for item in found} == {"TV", "Movie"}
