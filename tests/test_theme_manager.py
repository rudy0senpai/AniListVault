"""Tests for the centralized runtime theme engine."""

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from animevault.ui.theme import (
    DEFAULT_THEME_ID,
    THEMES,
    ThemeManager,
    build_stylesheet,
    status_badge_style,
    status_colors,
    tier_badge_style,
    tier_color,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def manager(app, tmp_path):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    app.setOrganizationName("AnimeVaultTests")
    app.setApplicationName("AnimeVaultTests")
    ThemeManager._instance = None
    current = ThemeManager(app)
    current.settings.clear()
    current.set_reduce_effects(False)
    current.apply_theme(DEFAULT_THEME_ID, persist=False)
    yield current
    current.settings.clear()
    ThemeManager._instance = None


def test_default_theme_and_complete_registry(manager):
    assert DEFAULT_THEME_ID == "minimal-simple"
    assert len(THEMES) == 25
    required = {"minimal-simple", "midnight-blue", "amoled-black", "light", "dracula", "nord", "anime-neon", "sakura"}
    assert required <= THEMES.keys()
    assert manager.active_theme.name == "Minimal Dark"
    assert all(theme.id == key and theme.description for key, theme in THEMES.items())


def test_stylesheet_generates_for_every_theme(manager):
    for theme_id in THEMES:
        assert manager.apply_theme(theme_id, persist=False) == theme_id
        css = build_stylesheet()
        assert THEMES[theme_id].background in css
        assert THEMES[theme_id].accent in css


def test_invalid_theme_falls_back_and_is_persisted_as_default(manager):
    assert manager.apply_theme("not-a-theme") == DEFAULT_THEME_ID
    assert manager.settings.value("appearance/theme_id") == DEFAULT_THEME_ID


def test_restore_persists_and_switches_without_restart(manager, app):
    manager.apply_theme("nvidia-green")
    assert manager.settings.value("appearance/theme_id") == "nvidia-green"
    manager.apply_theme("minimal-light")
    assert THEMES["minimal-light"].accent in app.styleSheet()
    manager.theme_id = DEFAULT_THEME_ID
    assert manager.restore() == "minimal-light"


def test_missing_saved_theme_restores_default(manager):
    manager.settings.setValue("appearance/theme_id", "missing-asset-theme")
    assert manager.restore() == DEFAULT_THEME_ID


def test_badge_helpers_remain_compatible(manager):
    assert tier_color("SSS") != tier_color("F")
    assert "transparent" in tier_badge_style(None)
    assert status_colors("watching") != status_colors("completed")
    assert "background:" in status_badge_style("watching")


def test_theme_picker_applies_and_persists_selection(manager):
    from animevault.ui.theme_dialog import ThemeSettingsDialog

    dialog = ThemeSettingsDialog(manager=manager)
    dialog.list.setCurrentItem(dialog._items["ubuntu"])
    assert manager.theme_id == "ubuntu"
    assert manager.settings.value("appearance/theme_id") == "ubuntu"
    assert dialog.description.text() == THEMES["ubuntu"].description
    dialog.reset_theme_button.click()
    assert manager.theme_id == DEFAULT_THEME_ID
    assert manager.settings.value("appearance/theme_id") == DEFAULT_THEME_ID
    dialog.close()


def test_appearance_dialog_uses_scrollable_responsive_layout(manager):
    from PySide6.QtWidgets import QBoxLayout
    from animevault.ui.theme_dialog import ThemeSettingsDialog

    dialog = ThemeSettingsDialog(manager=manager)
    assert dialog.windowTitle() == "Appearance & Theme"
    assert dialog.content_scroll.widgetResizable()

    dialog.show()
    QApplication.instance().processEvents()
    dialog.resize(700, 600)
    QApplication.instance().processEvents()
    assert dialog._picker_layout.direction() == QBoxLayout.Direction.TopToBottom
    dialog.resize(900, 700)
    QApplication.instance().processEvents()
    assert dialog._picker_layout.direction() == QBoxLayout.Direction.LeftToRight
    dialog.close()


def test_selected_theme_is_visible_after_dialog_opens(manager):
    from animevault.ui.theme_dialog import ThemeSettingsDialog

    manager.apply_theme("japanese-sunset", persist=False)
    dialog = ThemeSettingsDialog(manager=manager)
    dialog.show()
    QApplication.instance().processEvents()
    selected = dialog._items["japanese-sunset"]
    assert dialog.list.visualItemRect(selected).intersects(dialog.list.viewport().rect())
    dialog.close()


def test_dialog_reopening_scrolls_to_current_theme(manager):
    from animevault.ui.theme_dialog import ThemeSettingsDialog

    manager.apply_theme("japanese-sunset", persist=False)
    dialog = ThemeSettingsDialog(manager=manager)
    dialog.show()
    QApplication.instance().processEvents()
    dialog.list.scrollToBottom()
    dialog.hide()
    QApplication.instance().processEvents()
    dialog.show()
    QApplication.instance().processEvents()
    selected = dialog._items["japanese-sunset"]
    assert dialog.list.visualItemRect(selected).intersects(dialog.list.viewport().rect())
    dialog.close()


def test_narrow_resize_keeps_settings_content_at_top(manager):
    from animevault.ui.theme_dialog import ThemeSettingsDialog

    manager.apply_theme("japanese-sunset", persist=False)
    dialog = ThemeSettingsDialog(manager=manager)
    dialog.show()
    QApplication.instance().processEvents()
    dialog.resize(900, 800)
    QApplication.instance().processEvents()
    dialog.content_scroll.verticalScrollBar().setValue(0)
    manager.apply_theme("light", persist=False)
    dialog.resize(700, 600)
    QApplication.instance().processEvents()
    assert dialog.content_scroll.verticalScrollBar().value() == 0
    dialog.close()


def test_theme_search_and_reset_preserve_effect_preference(manager):
    from animevault.ui.theme_dialog import ThemeSettingsDialog

    dialog = ThemeSettingsDialog(manager=manager)
    dialog.search.setText("Japanese Sunset")
    assert not dialog._items["japanese-sunset"].isHidden()
    assert dialog._items["midnight-blue"].isHidden()
    dialog.list.setCurrentItem(dialog._items["japanese-sunset"])
    assert dialog.description.text() == THEMES["japanese-sunset"].description

    dialog.reduce_effects.setChecked(True)
    dialog.reset_theme_button.click()
    assert manager.theme_id == DEFAULT_THEME_ID
    assert manager.reduce_effects is True
    dialog.close()


def test_invalid_theme_definition_falls_back_and_is_hidden_from_picker(manager):
    from dataclasses import replace
    from animevault.ui.theme_dialog import ThemeSettingsDialog

    original = THEMES["dracula"]
    THEMES["dracula"] = replace(original, accent="not-a-color")
    try:
        assert THEMES["dracula"].is_valid is False
        assert manager.apply_theme("dracula") == DEFAULT_THEME_ID
        dialog = ThemeSettingsDialog(manager=manager)
        assert "dracula" not in dialog._items
        dialog.close()
    finally:
        THEMES["dracula"] = original


def test_update_source_is_validated_and_persisted(manager):
    from animevault.ui.theme_dialog import ThemeSettingsDialog

    dialog = ThemeSettingsDialog(manager=manager)
    dialog.release_api_input.setText("https://example.com/releases/latest")
    assert dialog._save_release_source() is False
    dialog.release_api_input.setText(
        "https://api.github.com/repos/sample-owner/sample-repo/releases/latest"
    )
    assert dialog._save_release_source() is True
    assert dialog._settings.value("updates/release_api") == dialog.release_api_input.text()
    dialog.close()


def test_update_source_defaults_to_repository_and_empty_input_saves(manager):
    from animevault.services.update import DEFAULT_RELEASE_API
    from animevault.ui.theme_dialog import ThemeSettingsDialog

    manager.settings.remove("updates/release_api")
    manager.settings.sync()
    dialog = ThemeSettingsDialog(manager=manager)
    assert dialog.release_api_input.text() == DEFAULT_RELEASE_API
    dialog.release_api_input.clear()
    assert dialog._save_release_source() is True
    assert dialog.release_api_input.text() == DEFAULT_RELEASE_API
    assert dialog._settings.value("updates/release_api") == DEFAULT_RELEASE_API
    dialog.close()


def test_check_updates_button_uses_builtin_source_without_user_entry(manager, monkeypatch):
    from animevault.services.update import DEFAULT_RELEASE_API
    from animevault.ui.theme_dialog import ThemeSettingsDialog

    manager.settings.remove("updates/release_api")
    manager.settings.sync()
    dialog = ThemeSettingsDialog(manager=manager)
    dialog.release_api_input.clear()
    started = []
    monkeypatch.setattr(
        dialog,
        "_start_update_worker",
        lambda mode, info=None: started.append((mode, info)),
    )
    dialog._check_for_updates()
    assert started == [("check", None)]
    assert dialog._settings.value("updates/release_api") == DEFAULT_RELEASE_API
    assert dialog.release_api_input.text() == DEFAULT_RELEASE_API
    dialog.close()


def test_legacy_owner_repo_template_migrates_to_builtin_release_source(manager):
    from animevault.services.update import DEFAULT_RELEASE_API
    from animevault.ui.theme_dialog import ThemeSettingsDialog

    manager.settings.setValue(
        "updates/release_api",
        "https://api.github.com/repos/OWNER/REPO/releases/latest",
    )
    manager.settings.sync()
    dialog = ThemeSettingsDialog(manager=manager)
    assert dialog.release_api_input.text() == DEFAULT_RELEASE_API
    dialog.close()


def test_reduce_effects_persists(manager):
    manager.set_reduce_effects(True)
    assert manager.reduce_effects is True
