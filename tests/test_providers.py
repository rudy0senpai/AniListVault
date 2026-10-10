"""Tests for individual metadata providers and their error classification."""

from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from animevault.services.providers.anilist import AniListProvider, normalize_media
from animevault.services.providers.base import AnimeMetadata, ProviderError
from animevault.services.providers.jikan import JikanProvider, normalize_entry as normalize_jikan
from animevault.services.providers.kitsu import KitsuProvider, normalize_entry as normalize_kitsu
from animevault.services.providers.tmdb import TmdbProvider, normalize_tv
from animevault.services.providers.manga_sources import (
    normalize_kitsu_manga,
    normalize_mangadex,
)


class TestAniListProvider:
    def test_normalize_media(self):
        raw = {
            "id": 20,
            "idMal": 20,
            "title": {"romaji": "Naruto", "english": "Naruto", "native": "NARUTO -ナルト-"},
            "synonyms": ["Naruto 2002"],
            "episodes": 220,
            "status": "FINISHED",
            "format": "TV",
            "description": "Twelve years before the start of the series...",
            "genres": ["Action", "Adventure"],
            "duration": 23,
            "season": "FALL",
            "seasonYear": 2002,
            "startDate": {"year": 2002, "month": 10, "day": 3},
            "endDate": {"year": 2007, "month": 2, "day": 8},
            "studios": {"nodes": [{"name": "Studio Pierrot"}]},
            "coverImage": {"large": "https://img.example.com/naruto.jpg"},
        }
        meta = normalize_media(raw)
        assert meta.title == "Naruto"
        assert meta.title_ja == "NARUTO -ナルト-"
        assert meta.anilist_id == 20
        assert meta.mal_id == 20
        assert meta.episodes == 220
        assert meta.airing_status == "FINISHED"
        assert meta.media_type == "TV"
        assert meta.studios == ["Studio Pierrot"]
        assert meta.poster_url == "https://img.example.com/naruto.jpg"

    def test_provider_403_non_retryable_backoff(self):
        provider = AniListProvider()
        http_err = urllib.error.HTTPError(
            url="https://graphql.anilist.co",
            code=403,
            msg="Forbidden",
            hdrs={},
            fp=io.BytesIO(b"Forbidden"),
        )
        with patch("urllib.request.urlopen", side_effect=http_err):
            with pytest.raises(ProviderError) as exc_info:
                provider.search("Naruto")
            assert exc_info.value.status_code == 403
            assert not exc_info.value.retryable
            assert not provider.is_available()

    def test_provider_429_rate_limited(self):
        provider = AniListProvider()
        http_err = urllib.error.HTTPError(
            url="https://graphql.anilist.co",
            code=429,
            msg="Rate limit",
            hdrs={"Retry-After": "10"},
            fp=io.BytesIO(b"Too Many Requests"),
        )
        with patch("urllib.request.urlopen", side_effect=http_err):
            with pytest.raises(ProviderError) as exc_info:
                provider.search("Naruto")
            assert exc_info.value.status_code == 429
            assert exc_info.value.retryable

    def test_provider_5xx_server_error(self):
        provider = AniListProvider()
        http_err = urllib.error.HTTPError(
            url="https://graphql.anilist.co",
            code=504,
            msg="Gateway Timeout",
            hdrs={},
            fp=io.BytesIO(b"Gateway Timeout"),
        )
        with patch("urllib.request.urlopen", side_effect=http_err):
            with pytest.raises(ProviderError) as exc_info:
                provider.search("Naruto")
            assert exc_info.value.status_code == 504
            assert exc_info.value.retryable

    def test_provider_timeout_network_error(self):
        provider = AniListProvider()
        url_err = urllib.error.URLError("timed out")
        with patch("urllib.request.urlopen", side_effect=url_err):
            with pytest.raises(ProviderError) as exc_info:
                provider.search("Naruto")
            assert exc_info.value.retryable


class TestJikanProvider:
    def test_normalize_entry(self):
        raw = {
            "mal_id": 20,
            "title": "Naruto",
            "title_english": "Naruto",
            "title_japanese": "NARUTO -ナルト-",
            "type": "TV",
            "episodes": 220,
            "status": "Finished Airing",
            "duration": "23 min per ep",
            "aired": {"from": "2002-10-03T00:00:00+00:00", "to": "2007-02-08T00:00:00+00:00"},
            "images": {"jpg": {"large_image_url": "https://cdn.myanimelist.net/images/anime/13/17405l.jpg"}},
            "studios": [{"name": "Pierrot"}],
            "genres": [{"name": "Action"}, {"name": "Adventure"}],
            "synopsis": "Moments prior to Naruto Uzumaki's birth...",
        }
        meta = normalize_jikan(raw)
        assert meta.title == "Naruto"
        assert meta.mal_id == 20
        assert meta.episodes == 220
        assert meta.duration == 23
        assert meta.airing_status == "FINISHED"
        assert meta.studios == ["Pierrot"]

    def test_jikan_504_gateway_timeout_triggers_backoff(self):
        provider = JikanProvider()
        http_err = urllib.error.HTTPError(
            url="https://api.jikan.moe/v4/anime",
            code=504,
            msg="Gateway Timeout",
            hdrs={},
            fp=io.BytesIO(b"Gateway Timeout"),
        )
        with patch("urllib.request.urlopen", side_effect=http_err):
            with pytest.raises(ProviderError) as exc:
                provider.search("Naruto")
            assert exc.value.status_code == 504
            assert not provider.is_available()


class TestKitsuProvider:
    def test_normalize_entry(self):
        raw = {
            "id": "11",
            "attributes": {
                "canonicalTitle": "Naruto",
                "titles": {"en": "Naruto", "ja_jp": "NARUTO -ナルト-"},
                "synopsis": "Twelve years ago...",
                "episodeCount": 220,
                "episodeLength": 23,
                "status": "finished",
                "startDate": "2002-10-03",
                "endDate": "2007-02-08",
                "subtype": "TV",
                "posterImage": {"large": "https://media.kitsu.app/anime/poster.jpg"},
            },
        }
        meta = normalize_kitsu(raw)
        assert meta.title == "Naruto"
        assert meta.kitsu_id == "11"
        assert meta.episodes == 220
        assert meta.airing_status == "FINISHED"


class TestTmdbProvider:
    def test_tmdb_skipped_when_no_api_key(self, monkeypatch):
        monkeypatch.delenv("ANIMEVAULT_TMDB_KEY", raising=False)
        provider = TmdbProvider()
        assert not provider.is_available()
        with pytest.raises(ProviderError) as exc:
            provider.search("Naruto")
        assert "not configured" in str(exc.value)


def test_mangadex_normalization_keeps_alternate_titles_and_cross_ids():
    meta = normalize_mangadex({
        "id": "md-1",
        "attributes": {
            "title": {"en": "Example Manhwa"},
            "altTitles": [{"ko": "예시 웹툰"}, {"en": "Example Webtoon"}],
            "originalLanguage": "ko",
            "links": {"al": "42", "mal": "84"},
            "description": {"en": "Story"},
            "status": "ongoing",
            "tags": [],
        },
        "relationships": [{"type": "cover_art", "attributes": {"fileName": "cover.png"}}],
    })
    assert meta.title_en == "Example Manhwa"
    assert "Example Webtoon" in meta.synonyms
    assert meta.category == "manhwa"
    assert meta.anilist_id == 42 and meta.mal_id == 84
    assert meta.cover_url.endswith("/md-1/cover.png.512.jpg")


def test_mangadex_non_english_original_is_not_falsely_labeled_english_and_keeps_credits():
    meta = normalize_mangadex({
        "id": "md-2",
        "attributes": {"title": {"ko": "한국어 제목"}, "originalLanguage": "ko", "links": {}},
        "relationships": [
            {"type": "author", "attributes": {"name": "Writer"}},
            {"type": "artist", "attributes": {"name": "Artist"}},
        ],
    })

    assert meta.title == "한국어 제목"
    assert meta.title_en == ""
    assert meta.authors == ["Writer"]
    assert meta.artists == ["Artist"]


def test_kitsu_manga_normalization_maps_manga_fields():
    meta = normalize_kitsu_manga({"id": "k-1", "attributes": {
        "canonicalTitle": "Example", "titles": {"en": "Example", "ja_jp": "例"},
        "chapterCount": 12, "volumeCount": 2, "status": "finished",
        "posterImage": {"original": "https://img.example/cover.jpg"},
    }})
    assert meta.title == "Example"
    assert meta.kitsu_id == "k-1"
    assert meta.chapters == 12 and meta.volumes == 2
    assert meta.cover_url == "https://img.example/cover.jpg"
