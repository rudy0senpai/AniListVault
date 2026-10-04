"""Tests for the optional cloud-sync layer.

The Drive upload path needs network access and real credentials, so these
tests cover what can be verified offline: payload construction, the
private-entry rule, merging, and idempotency.
"""

import json

import pytest

from animevault.media_types import MEDIA_MANGA, MEDIA_MANHWA
from animevault.models.anime import Anime
from animevault.models.literature import Literature
from animevault.services import sync_service


@pytest.fixture
def library(migrated_database):
    """A small library with public and private entries."""
    Anime.create(
        title="Naruto", episodes=220, episodes_watched=220, tier="SS",
        status="completed", genres=["Action"], studios=["Studio Pierrot"],
        anilist_id=20, privacy="public",
    )
    Literature.create(
        title="Berserk", category=MEDIA_MANGA, chapters=374, tier="S",
        authors=["Kentarou Miura"], anilist_id=30002, privacy="public",
    )
    Anime.create(title="Secret Show", episodes=12, privacy="private")
    Literature.create(title="Secret Comic", category=MEDIA_MANHWA,
                      privacy="private")
    return True


class TestPayload:
    def test_includes_public_entries(self, library):
        payload = sync_service.build_payload(include_private=False)
        titles = [a["title"] for a in payload["anime"]]
        assert "Naruto" in titles
        assert "Berserk" in [i["title"] for i in payload["literature"]]

    def test_excludes_private_entries_by_default(self, library):
        payload = sync_service.build_payload(include_private=False)
        assert "Secret Show" not in [a["title"] for a in payload["anime"]]
        assert "Secret Comic" not in [i["title"] for i in payload["literature"]]

    def test_includes_private_when_opted_in(self, library):
        payload = sync_service.build_payload(include_private=True)
        assert "Secret Show" in [a["title"] for a in payload["anime"]]

    def test_counts_private(self, library):
        assert sync_service.count_private() == 2

    def test_payload_is_json_serialisable(self, library):
        payload = sync_service.build_payload()
        text = json.dumps(payload, ensure_ascii=False)
        assert json.loads(text)["format_version"] == sync_service.SYNC_FORMAT_VERSION

    def test_payload_carries_metadata(self, library):
        row = sync_service.build_payload()["anime"][0]
        assert row["tier"] == "SS"
        assert row["episodes"] == 220
        assert "Action" in row["genres"]
        assert row["studios"] == ["Studio Pierrot"]

    def test_literature_payload_uses_chapters(self, library):
        row = sync_service.build_payload()["literature"][0]
        assert row["chapters"] == 374
        assert row["authors"] == ["Kentarou Miura"]


class TestMerge:
    def test_adds_entries_to_an_empty_library(self, library):
        payload = sync_service.build_payload()
        Anime.all()
        # Simulate a second machine by clearing the library first.
        for item in Anime.all():
            item.delete()
        for item in Literature.all():
            item.delete()

        added, updated = sync_service.merge_payload(payload)
        assert added == 2
        assert updated == 0
        assert len(Anime.all()) == 1
        assert len(Literature.all()) == 1

    def test_is_idempotent(self, library):
        payload = sync_service.build_payload()
        sync_service.merge_payload(payload)
        added, updated = sync_service.merge_payload(payload)
        assert added == 0, "re-importing created duplicates"
        assert len(Anime.all()) == 2  # Naruto + the private entry

    def test_does_not_clobber_local_values(self, library):
        payload = sync_service.build_payload()
        naruto = Anime.find_by_title("Naruto")
        naruto.episodes_watched = 5
        naruto.notes = "my local edit"
        naruto.save()

        sync_service.merge_payload(payload)
        after = Anime.find_by_title("Naruto")
        assert after.episodes_watched == 5
        assert after.notes == "my local edit"

    def test_overwrite_flag_replaces_values(self, library):
        payload = sync_service.build_payload()
        naruto = Anime.find_by_title("Naruto")
        naruto.episodes_watched = 5
        naruto.save()

        payload["anime"][0]["episodes_watched"] = 999
        sync_service.merge_payload(payload, overwrite=True)
        assert Anime.find_by_title("Naruto").episodes_watched == 999

    def test_matches_existing_by_provider_id(self, library):
        """A row with a known AniList id updates rather than duplicates."""
        payload = {
            "format_version": sync_service.SYNC_FORMAT_VERSION,
            "anime": [{
                "title": "Totally Different Name",
                "anilist_id": 20,
                "notes": "from the cloud",
            }],
            "literature": [],
        }
        added, _updated = sync_service.merge_payload(payload)
        # Matched by provider id, so no second record was created.
        assert added == 0
        assert Anime.find_by_title("Totally Different Name") is None
        # An empty local field is filled from the incoming row.
        assert Anime.find_by_title("Naruto").notes == "from the cloud"

    def test_rejects_newer_format_version(self, library):
        with pytest.raises(ValueError, match="newer version"):
            sync_service.merge_payload({"format_version": 999, "anime": []})


class TestSyncIsOptional:
    def test_app_works_without_an_account(self, library):
        """Nothing in the sync layer is required for normal use."""
        from animevault.services import account

        assert account.load_tokens() is None
        assert account.load_account().connected is False
        # The library is fully usable.
        assert len(Anime.all()) == 2

    def test_requires_client_id_to_be_configured(self):
        from animevault.services import account

        # No client id is set in the test environment.
        if not account.DEFAULT_CLIENT_ID:
            assert account.is_configured() is False
            assert "client id" in account.requires_client_id().lower()

    def test_not_connected_is_a_clean_error_not_a_crash(self, library):
        result = sync_service.pull()
        assert result.ok is False
        assert "connect" in result.message.lower()