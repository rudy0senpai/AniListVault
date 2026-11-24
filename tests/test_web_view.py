from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject

from animevault.models.anime import Anime
from animevault.models.literature import Literature
from animevault.ui.web_view import LibraryBridge, dashboard_records, to_card


@pytest.mark.parametrize("tier", ["SSS", "SS", "S", "A", "B", "C", "D", "E", "F"])
def test_anime_mapper_preserves_unicode_and_tier(tier, tmp_path):
    poster = tmp_path / "poster.jpg"
    poster.write_bytes(b"poster")
    record = Anime(
        id=23,
        title="長い作品名 · A Very Long Anime Title " * 8,
        title_ja="作品名",
        episodes=24,
        episodes_watched=9,
        tier=tier,
        favorite=True,
        media_type="TV",
        poster_path=str(poster),
        genres=["Drama"],
        studios=["Studio"],
    )

    card = to_card(record)

    assert card["id"] == "anime:23"
    assert card["mediaType"] == "anime"
    assert card["nativeTitle"] == "作品名"
    assert card["unit"] == "episodes"
    assert (card["total"], card["progress"], card["tier"]) == (24, 9, tier)
    assert card["cover"].startswith("file:/")
    assert "score" not in card
    assert "None" not in json.dumps(card, ensure_ascii=False)


def test_anime_unknown_total_and_missing_metadata_are_null_or_omitted():
    card = to_card(Anime(id=1, title="No total", episodes=0, episodes_watched=42))
    assert card.get("total") is None
    assert card["progress"] == 42
    assert "duration" not in card or card["duration"] not in ("None", "")
    assert card.get("cover") is None


@pytest.mark.parametrize("category", ["manga", "manhwa", "manhua"])
def test_literature_mapper_uses_chapters_and_category(category):
    record = Literature(
        id=8,
        title="웹툰 · 作品",
        category=category,
        chapters=0,
        chapters_read=42,
        volumes=7,
        volumes_read=3,
        authors=["Author"],
        serialization="Magazine",
        status="watching",
    )

    card = to_card(record)

    assert card["mediaType"] == category
    assert card["unit"] == "chapters"
    assert card.get("total") is None
    assert card["progress"] == 42
    assert card["volumes"] == 7
    assert card["authors"] == ["Author"]
    assert card["serialization"] == "Magazine"
    assert "studios" not in card
    assert "None" not in json.dumps(card, ensure_ascii=False)


def test_dashboard_adapter_preserves_anime_and_marks_invalid_literature_category_unknown(monkeypatch):
    anime = SimpleNamespace(
        id=5, title="Actual anime", media_type="TV", status="watching", tier="S",
        favorite=True, episodes_watched=3, episodes=12, genres=["Drama"], season_year=2001,
        score=8.5, first_watched="2024-01-01", last_watched="2024-01-02", completed_date=None,
    )
    legacy_literature = SimpleNamespace(
        id=9, title="Legacy row", category="anime", format="", status="planned", tier=None,
        favorite=False, chapters_read=0, chapters=0, genres=[], started_at="", first_read=None,
        last_read=None, completed_date=None,
    )
    monkeypatch.setattr(Anime, "all", classmethod(lambda cls: [anime]))
    monkeypatch.setattr(Literature, "all", classmethod(lambda cls: [legacy_literature]))

    records = dashboard_records()

    assert records[0]["media_type"] == "anime"
    assert records[0]["score"] == 8.5
    assert records[0]["progress"] == 3
    assert records[0]["year"] == 2001
    assert records[1]["media_type"] == "unknown"
    assert records[1]["score"] is None
    assert records[1]["year"] is None


class FakeOwner(QObject):
    def __init__(self):
        super().__init__()
        self.selected = []
        self.opened = []

    def _on_web_selection_changed(self, records):
        self.selected = records

    def _on_details(self, record):
        self.opened.append(record)


def test_bridge_returns_cached_library_and_routes_selection_and_open():
    owner = FakeOwner()
    bridge = LibraryBridge(owner)
    record = Anime(id=33, title="Bridge item", episodes=12)
    updates = []
    bridge.libraryChanged.connect(updates.append)

    bridge.replace_library([record])
    assert json.loads(bridge.getLibrary())[0]["id"] == "anime:33"
    bridge.setSelected("anime:33", True)
    assert owner.selected == [record]
    bridge.openRecord("anime:33")
    assert owner.opened == [record]
    assert json.loads(updates[-1])["type"] == "reset"


def test_bridge_pushes_poster_updates_incrementally(tmp_path):
    owner = FakeOwner()
    bridge = LibraryBridge(owner)
    record = Anime(id=34, title="Poster item", episodes=12)
    bridge.replace_library([record])
    poster = tmp_path / "poster.png"
    poster.write_bytes(b"poster")
    events = []
    bridge.libraryChanged.connect(events.append)

    bridge.update_poster(34, str(poster))

    event = json.loads(events[-1])
    assert event["type"] == "upsert"
    assert event["item"]["cover"].startswith("file:/")
