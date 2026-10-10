"""Tests for the redesigned UI: theme, cards, grid and dashboard."""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from animevault.media_types import (  # noqa: E402
    MEDIA_ANIME,
    MEDIA_MANGA,
    MEDIA_MANHWA,
    MEDIA_MANHUA,
)
from animevault.ui.card_factory import (  # noqa: E402
    anime_card,
    build_card,
    literature_card,
    type_label,
)
from animevault.ui.card_grid import CardGrid  # noqa: E402
from animevault.ui.theme import (  # noqa: E402
    ACCENT,
    BG_DEEP,
    build_stylesheet,
    status_colors,
    tier_badge_style,
    tier_color,
)


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(build_stylesheet())
    return app


def labels_of(widget) -> list[str]:
    return [lbl.text() for lbl in widget.findChildren(QLabel)]


class TestTheme:
    def test_stylesheet_contains_palette(self):
        css = build_stylesheet()
        assert BG_DEEP in css
        assert ACCENT in css

    def test_tier_colours_span_the_scale(self):
        # SSS is gold, F is grey — visually distinct ends.
        assert tier_color("SSS") != tier_color("F")

    def test_unassigned_tier_is_muted_not_gold(self):
        style = tier_badge_style(None)
        assert "transparent" in style

    def test_every_tier_has_a_colour(self):
        from animevault.tiers import TIERS

        for tier in TIERS:
            assert tier_color(tier)


class TestTypeLabel:
    @pytest.mark.parametrize("raw,expected", [
        ("TV", "TV"),
        ("tv", "TV"),
        ("MOVIE", "Movie"),
        ("OVA", "OVA"),
        ("ONE_SHOT", "One Shot"),
    ])
    def test_abbreviations_preserved(self, raw, expected):
        assert type_label(raw) == expected


class TestAnimeCard:
    def test_shows_title_tier_and_progress(self, qt_app, migrated_database):
        from animevault.models.anime import Anime

        anime = Anime.create(
            title="One Piece", episodes=1180, episodes_watched=1090,
            tier="SSS", status="watching", media_type="TV",
        )
        card = anime_card(anime)
        texts = labels_of(card)
        assert "One Piece" in texts
        assert "1090 / 1180" in texts
        assert "SSS" in texts
        assert "Watching" in texts

    def test_unassigned_tier_shows_dash(self, qt_app, migrated_database):
        from animevault.models.anime import Anime

        card = anime_card(Anime.create(title="Untiered"))
        assert "—" in labels_of(card)

    def test_unknown_episodes_do_not_divide(self, qt_app, migrated_database):
        from animevault.models.anime import Anime

        card = anime_card(Anime.create(title="NoEpisodes"))
        assert "—" in labels_of(card)


class TestLiteratureCards:
    @pytest.mark.parametrize("category", [MEDIA_MANGA, MEDIA_MANHWA, MEDIA_MANHUA])
    def test_each_literature_category_renders(self, qt_app, migrated_database, category):
        from animevault.models.literature import Literature

        item = Literature.create(
            title=f"Work {category}", category=category,
            chapters=200, chapters_read=50, tier="S",
        )
        card = literature_card(item)
        texts = labels_of(card)
        assert f"Work {category}" in texts
        assert "50 / 200" in texts
        assert "Reading" in texts

    def test_manhwa_label_shown(self, qt_app, migrated_database):
        from animevault.models.literature import Literature

        item = Literature.create(title="Solo Leveling", category=MEDIA_MANHWA, chapters=201)
        texts = labels_of(literature_card(item))
        assert any(t.startswith("Manhwa") for t in texts)

    def test_manga_label_shown(self, qt_app, migrated_database):
        from animevault.models.literature import Literature

        item = Literature.create(title="Berserk", category=MEDIA_MANGA)
        texts = labels_of(literature_card(item))
        assert any(t.startswith("Manga") for t in texts)

    def test_chapters_are_labelled_not_episodes(self, qt_app, migrated_database):
        from animevault.models.literature import Literature

        item = Literature.create(title="X", category=MEDIA_MANGA, chapters=90)
        texts = labels_of(literature_card(item))
        assert any("chapters" in t for t in texts)
        assert not any("ep" in t for t in texts)


class TestBuildCardDispatch:
    def test_anime_dispatches_to_anime_card(self, qt_app, migrated_database):
        from animevault.models.anime import Anime

        card = build_card(Anime.create(title="A"), MEDIA_ANIME)
        assert card.kind == "anime"

    def test_literature_dispatches_to_literature_card(self, qt_app, migrated_database):
        from animevault.models.literature import Literature

        item = Literature.create(title="L", category=MEDIA_MANHWA)
        assert build_card(item, MEDIA_MANHWA).kind == "literature"


class TestCardSelection:
    def test_selection_toggles(self, qt_app, migrated_database):
        from animevault.models.anime import Anime

        card = anime_card(Anime.create(title="Sel"))
        assert card.is_selected() is False
        card.set_selected(True)
        assert card.is_selected() is True
        card.set_selected(False)
        assert card.is_selected() is False

    def test_leaving_select_mode_clears_selection(self, qt_app, migrated_database):
        from animevault.models.anime import Anime

        card = anime_card(Anime.create(title="Sel2"))
        card.set_select_mode(True)
        card.set_selected(True)
        card.set_select_mode(False)
        assert card.is_selected() is False


class TestCardGrid:
    def test_reflows_columns_with_width(self, qt_app):
        grid = CardGrid()
        from animevault.ui.media_card import MediaCard

        cards = [
            MediaCard(
                object(), title=f"T{i}", type_label="TV", count_label="12 ep",
                progress_text="0 / 12", progress_percent=0,
                status_text="Watching", status_key="watching",
                tier="A", poster_path="", kind="anime",
            )
            for i in range(12)
        ]
        grid.set_cards(cards)
        assert grid.card_count() == 12

        grid.resize(1600, 800)
        grid._relayout()
        wide = grid._columns
        grid.resize(700, 800)
        grid._relayout()
        narrow = grid._columns
        assert narrow <= wide
        assert wide >= 1 and narrow >= 1

    def test_clear_removes_cards(self, qt_app):
        grid = CardGrid()
        grid.set_cards([])
        assert grid.card_count() == 0


class TestDashboard:
    def test_counts_derive_from_database(self, qt_app, migrated_database):
        from animevault.models.anime import Anime
        from animevault.models.literature import Literature
        from animevault.ui.overview_panel import compute_dashboard

        Anime.create(title="A", status="watching", genres=["Action"])
        Anime.create(title="B", status="completed", genres=["Action", "Comedy"])
        Literature.create(title="C", category=MEDIA_MANHWA, genres=["Action"])

        data = compute_dashboard(Anime.all(), Literature.all())
        assert data["anime"] == 2
        assert data["literature"] == 1
        assert data["by_category"] == {
            MEDIA_ANIME: 2,
            MEDIA_MANGA: 0,
            MEDIA_MANHWA: 1,
            MEDIA_MANHUA: 0,
        }
        assert dict(data["genres"])["Action"] == 3

    def test_category_summaries_cover_anime_and_all_literature_types(self, qt_app, migrated_database):
        from animevault.models.anime import Anime
        from animevault.models.literature import Literature
        from animevault.ui.overview_panel import OverviewPanel

        anime = [Anime.create(title="Show", status="watching")]
        library = [
            Literature.create(title="Manga", category=MEDIA_MANGA, status="watching"),
            Literature.create(title="Manhwa", category=MEDIA_MANHWA, status="completed"),
            Literature.create(title="Manhua", category=MEDIA_MANHUA, status="plan_to_watch"),
        ]
        panel = OverviewPanel()
        panel.refresh(anime, library)

        assert "Watching 1" in panel._category_details[MEDIA_ANIME].text()
        assert "Reading 1" in panel._category_details["manga"].text()
        assert "Completed 1" in panel._category_details["manhwa"].text()
        assert "Planned 1" in panel._category_details["manhua"].text()

    def test_tier_distribution_covers_full_scale(self, qt_app, migrated_database):
        from animevault.models.anime import Anime
        from animevault.ui.overview_panel import compute_dashboard
        from animevault.tiers import TIERS

        Anime.create(title="X", tier="SSS")
        data = compute_dashboard(Anime.all(), [])
        assert set(data["tiers"]) == set(TIERS)
        assert data["tiers"]["SSS"] == 1

    def test_empty_library_does_not_crash(self, qt_app, migrated_database):
        from animevault.ui.overview_panel import compute_dashboard

        data = compute_dashboard([], [])
        assert data["anime"] == 0
        assert not data["genres"]

class TestSidebarFitsItsPanel:
    """The overview panel must never overflow and force a horizontal scroll.

    Regression: long labels and the emoji section headings used to demand
    more width than the sidebar allowed, so the panel clipped its content
    and the user had to scroll sideways to read the counts.
    """

    def _panel_with_content(self, app):
        from animevault.models.anime import Anime
        from animevault.models.literature import Literature
        from animevault.ui.overview_panel import OverviewPanel

        animes = [
            Anime.create(title=f"A{i}", tier=t, genres=["Swordplay", "Adventure"])
            for i, t in enumerate(["SSS", "SS", "S", "A", "B"])
        ]
        literature = [
            Literature.create(title=f"L{i}", category=MEDIA_MANHUA, tier="S")
            for i in range(3)
        ]
        panel = OverviewPanel()
        panel.refresh(animes, literature)
        app.processEvents()
        return panel

    def test_no_horizontal_overflow(self, qt_app, migrated_database):
        panel = self._panel_with_content(qt_app)
        panel.resize(260, 900)
        for _ in range(4):
            qt_app.processEvents()
        assert panel.horizontalScrollBar().maximum() == 0

    def test_content_fits_within_panel_maximum_width(self, qt_app, migrated_database):
        panel = self._panel_with_content(qt_app)
        panel.resize(300, 900)
        for _ in range(4):
            qt_app.processEvents()
        assert panel.widget().minimumSizeHint().width() <= 260

    def test_headings_use_no_emoji_glyphs(self):
        # Emoji fall back to a font with very large metrics, which inflates
        # the heading's width requirement.
        import inspect

        from animevault.ui import overview_panel

        source = inspect.getsource(overview_panel)
        panel_titles = [
            line for line in source.splitlines()
            if "_panel(" in line and "def _panel" not in line
        ]
        for line in panel_titles:
            assert not any(ord(ch) > 0x2500 for ch in line), line

    def test_bar_rows_scale_to_available_width(self, qt_app):
        from animevault.ui.overview_panel import _BarRow, _BarTrack

        row = _BarRow("Adventure", 5, 10, "#22d3ee")
        qt_app.processEvents()
        tracks = row.findChildren(_BarTrack)
        assert tracks, "bar row must contain a track"
        track = tracks[0]
        # Shrink the track; the fill must follow it down.  resizeEvent does
        # not fire for a widget that was never shown, so drive it directly.
        track.resize(60, 7)
        track._sync_fill()
        fills = [c for c in track.children() if c.isWidgetType()]
        assert fills, "track must hold a fill"
        for fill in fills:
            assert fill.width() <= track.width() + 1

        # A full bar fills the track; an empty one is hidden.
        full = _BarTrack(1.0, "#ffffff")
        full.resize(80, 7)
        full._sync_fill()
        assert max(c.width() for c in full.children() if c.isWidgetType()) <= 80

        empty = _BarTrack(0.0, "#ffffff")
        empty.resize(80, 7)
        empty._sync_fill()
        assert all(c.isHidden() or c.width() == 0
                   for c in empty.children() if c.isWidgetType())
