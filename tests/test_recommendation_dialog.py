"""Tests for the recommendation dialog."""

import pytest
from unittest.mock import patch, MagicMock

from PySide6.QtWidgets import QApplication

from animevault.ui.recommendation_dialog import (
    RecommendationDialog,
    _RecommendationDetailsDialog,
    _load_library_items,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestLoadLibraryItems:
    def test_loads_anime_and_literature(self, qapp):
        with patch("animevault.ui.recommendation_dialog.Anime") as mock_anime, \
             patch("animevault.ui.recommendation_dialog.Literature") as mock_lit:
            mock_anime.all.return_value = [MagicMock(title="Anime1")]
            mock_lit.all.return_value = [MagicMock(title="Manga1")]
            items = _load_library_items()
            assert len(items) == 2

    def test_anime_failure_raises_if_no_items(self, qapp):
        with patch("animevault.ui.recommendation_dialog.Anime") as mock_anime, \
             patch("animevault.ui.recommendation_dialog.Literature") as mock_lit:
            mock_anime.all.side_effect = Exception("DB error")
            mock_lit.all.return_value = []
            with pytest.raises(RuntimeError):
                _load_library_items()

    def test_literature_failure_with_anime_succeeds(self, qapp):
        with patch("animevault.ui.recommendation_dialog.Anime") as mock_anime, \
             patch("animevault.ui.recommendation_dialog.Literature") as mock_lit:
            mock_anime.all.return_value = [MagicMock(title="Anime1")]
            mock_lit.all.side_effect = Exception("DB error")
            items = _load_library_items()
            assert len(items) == 1


class TestRecommendationDialogInit:
    def test_recommendation_grid_reflows_on_resize(self, qapp):
        from animevault.services.recommendation_engine import RecommendationResult

        with patch("animevault.ui.recommendation_dialog._load_library_items", return_value=[]), patch(
            "animevault.ui.recommendation_dialog.RecommendationEngine"
        ) as mock_engine:
            mock_engine.return_value.get_recommendations.return_value = []
            dlg = RecommendationDialog()
            dlg.show()
            qapp.processEvents()
            item = RecommendationResult(
                item_id=1, title="Test", media_type="TV", category="action",
                genres=["Action"], synopsis="Synopsis", score=0.8, reasons=[], poster_url="",
            )
            dlg._render_cards([item, item, item, item])
            dlg._scroll.viewport().resize(1100, 400)
            dlg._reflow_cards()
            wide_has_second_col = dlg._content_layout.itemAtPosition(0, 1) is not None
            dlg._scroll.viewport().resize(600, 400)
            dlg._reflow_cards()
            narrow_has_second_col = dlg._content_layout.itemAtPosition(0, 1) is not None
            assert wide_has_second_col and not narrow_has_second_col
            dlg.close()

    def test_dialog_initializes(self, qapp):
        with patch("animevault.ui.recommendation_dialog._load_library_items", return_value=[]), \
             patch("animevault.ui.recommendation_dialog.RecommendationEngine") as mock_engine:
            mock_engine.return_value.get_recommendations.return_value = []
            dlg = RecommendationDialog()
            assert dlg is not None
            assert dlg.isWindow() and not dlg.isModal()
            assert dlg.minimumWidth() >= 760 and dlg.minimumHeight() >= 560
            dlg._category_filter.setCurrentIndex(dlg._category_filter.findData("fantasy"))
            dlg._genre_filter.setCurrentText("Action")
            dlg._format_filter.setCurrentIndex(dlg._format_filter.findData("Movie"))
            dlg._score_filter.setValue(65)
            assert dlg._current_filters() == {
                "category": "fantasy",
                "genre_filter": "Action",
                "media_type_filter": "Movie",
                "min_score": 0.65,
            }
            dlg.close()


class TestRecommendationDetailsDialog:
    def test_details_dialog_with_all_fields(self, qapp):
        from animevault.services.recommendation_engine import RecommendationResult
        result = RecommendationResult(
            item_id=1, title="Test", media_type="Anime", category="action",
            genres=["Action"], synopsis="Synopsis", score=0.85, reasons=["reason"],
            poster_url="",
        )
        dlg = _RecommendationDetailsDialog(result)
        assert dlg is not None
        dlg.close()

    def test_details_dialog_missing_fields(self, qapp):
        from animevault.services.recommendation_engine import RecommendationResult
        result = RecommendationResult(
            item_id=2, title="Test2", media_type="Manga", category="",
            genres=[], synopsis="", score=0.0, reasons=[], poster_url="",
        )
        dlg = _RecommendationDetailsDialog(result)
        assert dlg is not None
        dlg.close()

    def test_details_dialog_invalid_score(self, qapp):
        from animevault.services.recommendation_engine import RecommendationResult
        result = RecommendationResult(
            item_id=3, title="Test3", media_type="Manhwa", category="",
            genres=[], synopsis="", score=0.0, reasons=[], poster_url="",
        )
        dlg = _RecommendationDetailsDialog(result)
        assert dlg is not None
        dlg.close()