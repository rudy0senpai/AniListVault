"""Tests for UI dialog and card interaction flows in offscreen mode."""

from __future__ import annotations

import os

from PySide6.QtWidgets import QApplication

from animevault.models.anime import Anime
from animevault.services.providers.base import AnimeMetadata
from animevault.ui.add_anime_dialog import AddAnimeDialog
from animevault.ui.anime_card import AnimeCard

# Ensure Qt can run in headless CI/test environments
os.environ["QT_QPA_PLATFORM"] = "offscreen"


class TestUIFlow:
    @classmethod
    def setup_class(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_overview_can_hide_and_reopen(self, migrated_database, tmp_path):
        from PySide6.QtCore import QSettings
        from animevault.ui.main_window import MainWindow

        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
        settings = QSettings("AnimeVault", "AnimeVault")
        settings.clear()
        window = MainWindow()
        assert window._overview_toggle.text() == ">>"
        window._overview_toggle.click()
        assert window._overview.isHidden()
        assert window._overview_container.width() <= 42
        assert window._overview_toggle.toolTip() == "Show Overview"
        assert window._overview_toggle.text() == "<<"
        window.close()
        restored = MainWindow()
        assert restored._overview.isHidden()
        restored._overview_toggle.click()
        assert not restored._overview.isHidden()
        assert restored._overview_toggle.text() == ">>"
        restored.close()
        settings.clear()

    def test_overview_uses_scroll_viewport_and_has_no_rec_panel(self, migrated_database, tmp_path):
        from PySide6.QtCore import QSettings, Qt
        from PySide6.QtWidgets import QScrollArea
        from animevault.ui.main_window import MainWindow

        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
        window = MainWindow()
        assert window._overview_scroll.widget() is window._overview
        assert window._overview_scroll.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
        assert not any(type(window._body.itemAt(i).widget()).__name__ == "RecommendationPanel" for i in range(window._body.count()) if window._body.itemAt(i).widget())
        window.close()

    def test_recommendations_open_in_one_independent_reusable_window(self, migrated_database, tmp_path, monkeypatch):
        from PySide6.QtCore import QSettings, Qt
        from PySide6.QtWidgets import QDialog
        from animevault.ui.main_window import MainWindow
        import animevault.ui.recommendation_dialog as rec_module

        class StubWindow(QDialog):
            def __init__(self, parent=None, library_items=None):
                super().__init__(parent, Qt.WindowType.Window)
                self.items = library_items
                self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        monkeypatch.setattr(rec_module, "RecommendationDialog", StubWindow, raising=False)
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
        window = MainWindow()
        window.show()
        window._show_recommendations()
        first = window._recommendation_window
        assert first is not None and first.isVisible() and first.isWindow()
        window._show_recommendations()
        assert window._recommendation_window is first
        first.close()
        self.app.processEvents()
        assert not window.isHidden()
        window._show_recommendations()
        assert window._recommendation_window is not first
        window._recommendation_window.close()
        window.close()

    def test_add_anime_dialog_manual_entry(self, isolated_database):
        dlg = AddAnimeDialog()
        dlg._title_edit.setText("Cowboy Bebop")
        dlg._episodes_spin.setValue(26)
        dlg._status_combo.setCurrentText("completed")
        dlg._score_edit.setText("9.5")
        dlg._on_accept()

        saved = dlg.anime
        assert saved is not None
        assert saved.title == "Cowboy Bebop"
        assert saved.episodes == 26
        assert saved.status == "completed"
        assert saved.score == 9.5

    def test_add_anime_dialog_candidate_selection_and_duplicate(self, isolated_database):
        dlg = AddAnimeDialog()
        meta = AnimeMetadata(
            title="Naruto",
            title_ja="NARUTO -ナルト-",
            title_en="Naruto",
            episodes=220,
            media_type="TV",
            airing_status="FINISHED",
            genres=["Action", "Adventure"],
            synopsis="Ninja story",
            anilist_id=20,
            source_provider="anilist",
        )
        # Simulate provider search result
        dlg._on_search_results([meta])
        assert dlg._results_table.rowCount() == 1
        assert dlg._title_edit.text() == "Naruto"
        assert dlg._title_ja_edit.text() == "NARUTO -ナルト-"
        assert dlg._episodes_spin.value() == 220
        assert dlg._genres_edit.text() == "Action, Adventure"

        dlg._status_combo.setCurrentText("watching")
        dlg._on_accept()
        saved = dlg.anime
        assert saved is not None
        assert saved.anilist_id == 20

        # Now open dialog again and simulate selecting the same anime
        dlg2 = AddAnimeDialog()
        dlg2._on_search_results([meta])
        # Duplicate banner should be visible
        assert dlg2._existing_anime is not None
        assert dlg2._existing_anime.id == saved.id
        assert not dlg2._dup_banner.isHidden()

    def test_anime_card_delete_signal(self, isolated_database):
        anime = Anime.create(title="Trigun", episodes=26)
        card = AnimeCard(anime)

        deleted_tracker = []
        card.deleted.connect(lambda a: deleted_tracker.append(a.id))

        # Directly invoke delete logic
        anime_id = anime.id
        anime.delete()
        card.deleted.emit(anime)

        assert deleted_tracker == [anime_id]
        assert Anime.find_by_id(anime_id) is None
