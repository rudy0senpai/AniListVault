"""Tests for the Anime dataclass model."""

import pytest

from animevault.models.anime import (
    STATUS_COMPLETED,
    STATUS_DROPPED,
    STATUS_ON_HOLD,
    STATUS_PLAN_TO_WATCH,
    STATUS_WATCHING,
    VALID_STATUSES,
    Anime,
)


class TestAnimeConstruction:
    """Verify the dataclass can be constructed with valid data."""

    def test_minimal_construction(self):
        """Anime with only a title should be constructable."""
        anime = Anime(id=None, title="Naruto")
        assert anime.title == "Naruto"
        assert anime.title_ja == ""
        assert anime.episodes == 0
        assert anime.status == STATUS_PLAN_TO_WATCH
        assert anime.score is None
        assert anime.notes == ""

    def test_full_construction(self):
        """All fields can be set at construction time."""
        anime = Anime(
            id=1,
            title="Fullmetal Alchemist: Brotherhood",
            title_ja="鋼の錬金術師: ブラザーホッド",
            episodes=24,
            status=STATUS_COMPLETED,
            score=9.5,
            notes="Watched twice.",
        )
        assert anime.id == 1
        assert anime.title == "Fullmetal Alchemist: Brotherhood"
        assert anime.title_ja == "鋼の錬金術師: ブラザーホッド"
        assert anime.episodes == 24
        assert anime.status == STATUS_COMPLETED
        assert anime.score == 9.5
        assert anime.notes == "Watched twice."

    def test_empty_title_raises(self):
        """An empty title string should raise ValueError."""
        with pytest.raises(ValueError, match="title must be a non-empty string"):
            Anime(id=None, title="")

    def test_whitespace_title_raises(self):
        """A title of only whitespace should raise ValueError."""
        with pytest.raises(ValueError, match="title must be a non-empty string"):
            Anime(id=None, title="   ")

    def test_non_string_title_raises(self):
        """A non-string title should raise ValueError."""
        with pytest.raises(ValueError, match="title must be a non-empty string"):
            Anime(id=None, title=123)

    def test_negative_episodes_raises(self):
        """Negative episode count should raise ValueError."""
        with pytest.raises(ValueError, match="non-negative integer"):
            Anime(id=None, title="Test", episodes=-1)

    def test_invalid_status_raises(self):
        """An unknown status should raise ValueError."""
        with pytest.raises(ValueError, match="status must be one of"):
            Anime(id=None, title="Test", status="invalid_status")

    def test_score_out_of_range_raises(self):
        """A score above 10.0 should raise ValueError."""
        with pytest.raises(ValueError, match="0.0 and 10.0"):
            Anime(id=None, title="Test", score=10.5)

    def test_score_below_zero_raises(self):
        """A negative score should raise ValueError."""
        with pytest.raises(ValueError, match="0.0 and 10.0"):
            Anime(id=None, title="Test", score=-1.0)

    def test_score_none_allowed(self):
        """score=None should be accepted."""
        anime = Anime(id=None, title="Test", score=None)
        assert anime.score is None

    def test_score_zero_allowed(self):
        """score=0.0 should be accepted (lowest valid score)."""
        anime = Anime(id=None, title="Test", score=0.0)
        assert anime.score == 0.0

    def test_score_ten_allowed(self):
        """score=10.0 should be accepted (highest valid score)."""
        anime = Anime(id=None, title="Test", score=10.0)
        assert anime.score == 10.0

    def test_all_valid_statuses(self):
        """Every status in VALID_STATUSES should be constructable."""
        for status in VALID_STATUSES:
            anime = Anime(id=None, title="Test", status=status)
            assert anime.status == status


class TestAnimePersistence:
    """Verify save / load round-trips through SQLite."""

    def test_create_persists_and_returns_id(self):
        """Anime.create should save the record and return an id."""
        anime = Anime.create(title="Attack on Titan", episodes=25, status=STATUS_WATCHING)
        assert anime.id is not None
        assert anime.id > 0

    def test_save_inserts_new_record(self):
        """Saving a new Anime (id=None) should INSERT into the database."""
        anime = Anime(id=None, title="One Piece", episodes=1000, status=STATUS_WATCHING)
        anime.save()

        loaded = Anime.find_by_id(anime.id)
        assert loaded is not None
        assert loaded.title == "One Piece"
        assert loaded.episodes == 1000
        assert loaded.status == STATUS_WATCHING

    def test_save_updates_existing_record(self):
        """Saving an existing Anime (with id) should UPDATE the record."""
        anime = Anime.create(title="My Hero Academia", episodes=13, status=STATUS_WATCHING)
        original_id = anime.id

        anime.episodes = 25
        anime.status = STATUS_COMPLETED
        anime.save()

        loaded = Anime.find_by_id(original_id)
        assert loaded.episodes == 25
        assert loaded.status == STATUS_COMPLETED

    def test_all_returns_all_anime(self):
        """Anime.all() should return all persisted entries."""
        Anime.create(title="Anime A")
        Anime.create(title="Anime B")
        Anime.create(title="Anime C")

        all_animes = Anime.all()
        assert len(all_animes) == 3
        titles = [a.title for a in all_animes]
        assert titles == ["Anime A", "Anime B", "Anime C"]  # alphabetical order

    def test_all_returns_empty_list_when_no_data(self):
        """Anime.all() should return an empty list for a fresh database."""
        assert Anime.all() == []

    def test_find_by_id_returns_none_for_missing(self):
        """find_by_id with a non-existent id should return None."""
        result = Anime.find_by_id(99999)
        assert result is None

    def test_delete_removes_record(self):
        """delete() should remove the record from the database."""
        anime = Anime.create(title="To Delete")
        anime_id = anime.id

        anime.delete()

        assert Anime.find_by_id(anime_id) is None

    def test_delete_on_unsaved_is_noop(self):
        """delete() on an unsaved record (id=None) should be a no-op."""
        anime = Anime(id=None, title="Unsaved")
        anime.delete()  # should not raise

    def test_full_round_trip(self):
        """Create with all fields → reload → verify every field matches."""
        original = Anime.create(
            title="Steins;Gate",
            title_ja="シュタインズゲート",
            episodes=24,
            status=STATUS_COMPLETED,
            score=9.2,
            notes="Time travel done right.",
        )

        loaded = Anime.find_by_id(original.id)
        assert loaded is not None
        assert loaded.title == original.title
        assert loaded.title_ja == original.title_ja
        assert loaded.episodes == original.episodes
        assert loaded.status == original.status
        assert loaded.score == original.score
        assert loaded.notes == original.notes

    def test_null_title_ja_persists_as_empty(self):
        """When title_ja is None in the DB, from_row should return empty string."""
        anime = Anime.create(title="Ghost in the Shell")
        loaded = Anime.find_by_id(anime.id)
        assert loaded.title_ja == ""

    def test_score_none_persists_correctly(self):
        """When score is None, it should load back as None."""
        anime = Anime.create(title="Unrated Show", score=None)
        loaded = Anime.find_by_id(anime.id)
        assert loaded.score is None
