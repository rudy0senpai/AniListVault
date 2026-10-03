"""Tests for media categories, type detection and the Literature model."""

import pytest

from animevault.media_types import (
    CATEGORY_LABELS,
    LITERATURE_CATEGORIES,
    MEDIA_ANIME,
    MEDIA_MANGA,
    MEDIA_MANHWA,
    MEDIA_MANHUA,
    category_from_origin,
    is_literature,
    normalize_category,
    normalize_format,
    status_labels,
    type_options,
    unit_for,
)


class TestCategories:
    def test_four_categories(self):
        assert set(CATEGORY_LABELS) == {
            MEDIA_ANIME, MEDIA_MANGA, MEDIA_MANHWA, MEDIA_MANHUA
        }

    def test_anime_is_not_literature(self):
        assert is_literature(MEDIA_ANIME) is False

    @pytest.mark.parametrize("cat", [MEDIA_MANGA, MEDIA_MANHWA, MEDIA_MANHUA])
    def test_literature_categories(self, cat):
        assert is_literature(cat) is True

    def test_literature_frozenset(self):
        assert LITERATURE_CATEGORIES == {MEDIA_MANGA, MEDIA_MANHWA, MEDIA_MANHUA}


class TestNormalizeCategory:
    @pytest.mark.parametrize("raw,expected", [
        ("Anime", MEDIA_ANIME),
        ("MANGA", MEDIA_MANGA),
        ("  manhwa  ", MEDIA_MANHWA),
        ("Manhua", MEDIA_MANHUA),
        ("korean comic", MEDIA_MANHWA),
        ("chinese comic", MEDIA_MANHUA),
        ("japanese comic", MEDIA_MANGA),
        (None, MEDIA_ANIME),
        ("nonsense", MEDIA_ANIME),   # never orphans a record
    ])
    def test_variants(self, raw, expected):
        assert normalize_category(raw) == expected


class TestCategoryFromOrigin:
    @pytest.mark.parametrize("origin,expected", [
        ("JP", MEDIA_MANGA),
        ("KR", MEDIA_MANHWA),
        ("CN", MEDIA_MANHUA),
        ("TW", MEDIA_MANHUA),
        ("JAPAN", MEDIA_MANGA),
        ("South Korea", MEDIA_MANHWA),
    ])
    def test_known_origins(self, origin, expected):
        assert category_from_origin(origin) == expected

    @pytest.mark.parametrize("origin", [None, "", "ZZ", "unknown"])
    def test_unknown_origin_returns_none(self, origin):
        # None means "can't tell" — the caller must not guess.
        assert category_from_origin(origin) is None


class TestFormatAndUnits:
    def test_normalize_format_uppercases(self):
        assert normalize_format("manga") == "MANGA"

    def test_anime_units_are_episodes(self):
        assert unit_for(MEDIA_ANIME) == ("episode", "episodes")

    @pytest.mark.parametrize("cat", [MEDIA_MANGA, MEDIA_MANHWA, MEDIA_MANHUA])
    def test_literature_units_are_chapters(self, cat):
        assert unit_for(cat) == ("chapter", "chapters")

    def test_anime_status_labels(self):
        labels = status_labels(MEDIA_ANIME)
        assert labels["watching"] == "Watching"
        assert labels["plan_to_watch"] == "Plan to Watch"

    def test_literature_status_labels(self):
        labels = status_labels(MEDIA_MANHWA)
        assert labels["watching"] == "Reading"
        assert labels["plan_to_watch"] == "Plan to Read"


class TestTypeOptions:
    def test_anime_offers_anime_formats(self):
        options = type_options(MEDIA_ANIME)
        assert "TV" in options and "Movie" in options or "MOVIE" in options

    def test_literature_offers_literature_types(self):
        options = type_options(MEDIA_MANGA)
        assert "Manga" in options
        assert "Manhwa" in options
        assert "Manhua" in options
        # Irrelevant anime formats must not appear.
        assert "OVA" not in options and "ONA" not in options

    def test_all_always_first(self):
        assert type_options(MEDIA_ANIME)[0] == "All"
        assert type_options(MEDIA_MANHUA)[0] == "All"


class TestLiteratureModel:
    @pytest.fixture(autouse=True)
    def _schema(self, migrated_database):
        self.db = migrated_database

    def test_create_and_reload(self):
        from animevault.models.literature import Literature

        item = Literature.create(
            title="Solo Leveling",
            category=MEDIA_MANHWA,
            chapters=200,
            chapters_read=145,
            tier="SSS",
            genres=["Action"],
        )
        loaded = Literature.find_by_id(item.id)
        assert loaded.title == "Solo Leveling"
        assert loaded.category == MEDIA_MANHWA
        assert loaded.chapters == 200
        assert loaded.chapters_read == 145
        assert loaded.tier == "SSS"
        assert loaded.genres == ["Action"]

    def test_tier_normalized_on_construction(self):
        from animevault.models.literature import Literature

        item = Literature(id=None, title="X", tier="sss")
        assert item.tier == "SSS"

    def test_invalid_tier_rejected(self):
        from animevault.models.literature import Literature

        with pytest.raises(ValueError):
            Literature(id=None, title="X", tier="Legendary")

    def test_progress_and_percent(self):
        from animevault.models.literature import Literature

        item = Literature(id=None, title="X", chapters=200, chapters_read=50)
        assert item.progress() == (50, 200)
        assert item.progress_percent() == 25

    def test_progress_zero_total(self):
        from animevault.models.literature import Literature

        item = Literature(id=None, title="X", chapters=0, chapters_read=5)
        assert item.progress_percent() == 0

    def test_category_defaults_to_manga(self):
        from animevault.models.literature import Literature

        assert Literature(id=None, title="X").category == MEDIA_MANGA

    def test_filter_by_category(self):
        from animevault.models.literature import Literature

        Literature.create(title="M", category=MEDIA_MANGA)
        Literature.create(title="H", category=MEDIA_MANHWA)
        assert [i.title for i in Literature.by_category(MEDIA_MANHWA)] == ["H"]

    def test_status_label_uses_reading(self):
        from animevault.models.literature import Literature

        item = Literature.create(title="X", category=MEDIA_MANHWA, status="watching")
        assert item.status_label() == "Reading"

    def test_negative_chapters_rejected(self):
        from animevault.models.literature import Literature

        with pytest.raises(ValueError):
            Literature(id=None, title="X", chapters=-1)

    def test_delete_removes_record(self):
        from animevault.models.literature import Literature

        item = Literature.create(title="Doomed")
        item_id = item.id
        item.delete()
        assert Literature.find_by_id(item_id) is None