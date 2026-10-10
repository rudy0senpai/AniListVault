"""Tests for metadata enrichment, deterministic merge, and personal data preservation."""

from __future__ import annotations

import pytest

from animevault.models.anime import Anime
from animevault.services.enrichment import anime_from_metadata, merge_metadata_into_anime
from animevault.services.providers.base import AnimeMetadata
from animevault.services.search import SearchService


class TestEnrichmentAndMerge:
    def test_literature_metadata_merge_keeps_original_title_and_personal_fields(self):
        from animevault.services.providers.literature import LiteratureMetadata
        from animevault.services.workers import BulkEnrichmentWorker
        from animevault.models.literature import Literature

        item = Literature(id=None, title="Kusuriya no Hitorigoto", status="completed", tier="S", notes="personal", chapters_read=25, favorite=True)
        meta = LiteratureMetadata(title="Kusuriya no Hitorigoto", title_en="The Apothecary Diaries", synonyms=["Drugstore Notes"], chapters=50)

        BulkEnrichmentWorker._merge_literature(item, meta)

        assert item.title == "Kusuriya no Hitorigoto"
        assert item.title_en == "The Apothecary Diaries"
        assert item.synonyms == ["Drugstore Notes"]
        assert (item.status, item.tier, item.notes, item.chapters_read, item.favorite) == ("completed", "S", "personal", 25, True)

    def test_anime_from_metadata_creates_unsaved_anime(self):
        meta = AnimeMetadata(
            title="Steins;Gate",
            title_ja="シュタインズ・ゲート",
            title_en="Steins;Gate",
            synopsis="Rintaro Okabe is a self-proclaimed mad scientist...",
            episodes=24,
            media_type="TV",
            airing_status="FINISHED",
            genres=["Sci-Fi", "Suspense"],
            studios=["White Fox"],
            aired_from="2011-04-06",
            aired_to="2011-09-14",
            duration=24,
            mal_id=9253,
            anilist_id=9253,
            source_provider="anilist",
        )
        anime = anime_from_metadata(meta, status="completed")
        assert anime.id is None
        assert anime.title == "Steins;Gate"
        assert anime.status == "completed"
        assert anime.episodes == 24
        assert anime.studios == ["White Fox"]
        assert anime.anilist_id == 9253

    def test_personal_fields_preserved_on_merge(self):
        """User personal fields (status, score, notes) must NEVER be overwritten."""
        anime = Anime(
            id=None,
            title="Naruto",
            title_ja="",
            episodes=0,
            status="completed",
            score=9.5,
            notes="My favorite childhood anime",
        )

        incoming = AnimeMetadata(
            title="Naruto",
            title_en="Naruto",
            title_ja="NARUTO -ナルト-",
            episodes=220,
            media_type="TV",
            airing_status="FINISHED",
            synopsis="Naruto Uzumaki is a young ninja...",
            genres=["Action", "Adventure"],
            studios=["Pierrot"],
            mal_id=20,
            anilist_id=20,
            source_provider="anilist",
        )

        merge_metadata_into_anime(anime, incoming)

        # Personal fields intact
        assert anime.status == "completed"
        assert anime.score == 9.5
        assert anime.notes == "My favorite childhood anime"

        # Missing metadata fields filled
        assert anime.title_ja == "NARUTO -ナルト-"
        assert anime.title_en == "Naruto"
        assert anime.episodes == 220
        assert anime.media_type == "TV"
        assert anime.airing_status == "FINISHED"
        assert anime.genres == ["Action", "Adventure"]
        assert anime.studios == ["Pierrot"]
        assert anime.mal_id == 20
        assert anime.anilist_id == 20

    def test_additive_provider_ids(self):
        """Multiple providers add their IDs without overwriting existing ones."""
        anime = Anime(
            id=None,
            title="Naruto",
            anilist_id=20,
        )

        kitsu_meta = AnimeMetadata(
            title="Naruto",
            kitsu_id="11",
            source_provider="kitsu",
        )
        merge_metadata_into_anime(anime, kitsu_meta)

        assert anime.anilist_id == 20
        assert anime.kitsu_id == "11"

    def test_duplicate_detection_by_provider_id(self, isolated_database):
        existing = Anime.create(
            title="Naruto",
            anilist_id=20,
            status="watching",
        )

        service = SearchService()
        meta = AnimeMetadata(title="Naruto (2002)", anilist_id=20)
        found = service.find_duplicate_in_library(meta)

        assert found is not None
        assert found.id == existing.id
        assert found.title == "Naruto"

    def test_duplicate_detection_by_title(self, isolated_database):
        existing = Anime.create(
            title="Fullmetal Alchemist: Brotherhood",
            status="completed",
        )

        service = SearchService()
        meta = AnimeMetadata(title="Fullmetal Alchemist: Brotherhood", anilist_id=5114)
        found = service.find_duplicate_in_library(meta)

        assert found is not None
        assert found.id == existing.id

    def test_model_saves_can_join_a_caller_managed_batch(self, isolated_database):
        from animevault.database import get_connection

        anime = Anime.create(title="Batchable")
        anime.notes = "metadata refresh"
        anime.save(commit=False)
        with get_connection() as connection:
            connection.commit()

        assert Anime.find_by_id(anime.id).notes == "metadata refresh"

    def test_full_save_and_reload_roundtrip(self, isolated_database):
        anime = Anime.create(
            title="Naruto",
            title_ja="NARUTO -ナルト-",
            title_en="Naruto",
            episodes=220,
            status="plan_to_watch",
            score=8.0,
            notes="Watch with friends",
            synopsis="Twelve years ago...",
            genres=["Action", "Ninja"],
            studios=["Pierrot"],
            season="FALL",
            season_year=2002,
            anilist_id=20,
            mal_id=20,
            source_provider="anilist",
        )

        loaded = Anime.find_by_id(anime.id)
        assert loaded is not None
        assert loaded.title == "Naruto"
        assert loaded.title_ja == "NARUTO -ナルト-"
        assert loaded.title_en == "Naruto"
        assert loaded.episodes == 220
        assert loaded.score == 8.0
        assert loaded.genres == ["Action", "Ninja"]
        assert loaded.studios == ["Pierrot"]
        assert loaded.season_year == 2002
        assert loaded.anilist_id == 20
        assert loaded.mal_id == 20
