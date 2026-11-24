"""Tests for the settings system: defaults, validation, persistence, and actions.

These tests verify the Python-side settings infrastructure that backs the
Liquid Glass Settings UI in AnimeVault.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest
from PySide6.QtCore import QObject

from animevault.ui.settings_service import Settings, SettingsService
from animevault.ui.theme import ACCENT, ACCENT_VIOLET, TEXT_PRIMARY


@pytest.fixture
def tmp_app_dir(monkeypatch, tmp_path):
    """Point the settings directory to a temporary location."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    # Clear any existing settings so tests start clean
    settings_file = tmp_path / "appdata" / "config" / "settings.json"
    if settings_file.exists():
        settings_file.unlink()
    return tmp_path


class FakeOwner(QObject):
    """Minimal stand-in for the MainWindow owner."""

    def __init__(self):
        super().__init__()
        self.appearance_calls = []
        self.library_calls = []
        self.visibility = True

    def set_appearance(self, *, theme_id, accent, secondary, bg, surface, text, glass, animations, reduce):
        self.appearance_calls.append(
            {
                "theme_id": theme_id,
                "accent": accent,
                "secondary": secondary,
                "bg": bg,
                "surface": surface,
                "text": text,
                "glass": glass,
                "animations": animations,
                "reduce": reduce,
            }
        )

    def set_library_defaults(self, *, view, show_progress, confirm_delete, auto_complete):
        self.library_calls.append(
            {
                "view": view,
                "show_progress": show_progress,
                "confirm_delete": confirm_delete,
                "auto_complete": auto_complete,
            }
        )

    def set_settings_view_visible(self, visible):
        self.visibility = visible


class TestSettingsDefaults:
    """Verify default settings values."""

    def test_default_values_match_schema(self):
        s = Settings()
        assert s.themeId == "midnight"
        assert s.glass == 70
        assert s.animations is True
        assert s.reduce is False
        assert s.library["view"] == "Grid"
        assert s.library["progress"] is True
        assert s.library["confirmDelete"] is True
        assert s.library["autoComplete"] is False
        assert s.recommendations["basis"] == "Both"
        assert s.recommendations["count"] == 20
        assert s.language["lang"] == "English"

    def test_default_colors_match_theme(self):
        s = Settings()
        assert s.colors["accent"] == ACCENT
        assert s.colors["secondary"] == ACCENT_VIOLET
        assert s.colors["bg"] == "#0b1020"
        assert s.colors["surface"] == "#131a2e"
        assert s.colors["text"] == TEXT_PRIMARY


class TestSettingsValidation:
    """Verify the validation rules."""

    def test_valid_settings_pass(self):
        s = Settings(glass=50, performance={"cache": 500}, data={"keep": 7}, recommendations={"count": 20})
        s.validate()

    def test_glass_out_of_range(self):
        s = Settings(glass=101)
        with pytest.raises(ValueError, match="glass must be 0-100"):
            s.validate()

    def test_glass_negative(self):
        s = Settings(glass=-1)
        with pytest.raises(ValueError, match="glass must be 0-100"):
            s.validate()

    def test_cache_size_out_of_range(self):
        s = Settings(performance={"cache": 50})
        with pytest.raises(ValueError, match="cache size must be 100-2000"):
            s.validate()

    def test_backup_retention_out_of_range(self):
        s = Settings(data={"keep": 0})
        with pytest.raises(ValueError, match="backups to keep must be 1-30"):
            s.validate()

    def test_recommendation_count_out_of_range(self):
        s = Settings(recommendations={"count": 3})
        with pytest.raises(ValueError, match="recommendation count must be 5-50"):
            s.validate()


class TestSettingsPersistence:
    """Verify JSON persistence."""

    def test_to_dict_roundtrip(self, tmp_app_dir):
        s = Settings(themeId="dracula", glass=80, library={"view": "List"})
        dumped = s.to_dict()
        assert dumped["themeId"] == "dracula"
        assert dumped["glass"] == 80
        assert dumped["library"]["view"] == "List"
        assert "customThemes" in dumped

    def test_from_dict_fills_defaults(self, tmp_app_dir):
        raw = {
            "themeId": "midnight",
            "colors": {"accent": "#ff0000"},
            "glass": 60,
        }
        s = Settings.from_dict(raw)
        assert s.themeId == "midnight"
        assert s.colors["accent"] == "#ff0000"
        assert s.glass == 60
        assert s.library["view"] == "Grid"  # default preserved

    def test_service_save_and_load(self, tmp_app_dir):
        service = SettingsService()
        original = Settings(themeId="nord", glass=90)
        service.save(original)
        loaded = service.load()
        assert loaded.themeId == "nord"
        assert loaded.glass == 90

    def test_service_get_and_set(self, tmp_app_dir):
        service = SettingsService()
        service.set("library.view", "Compact")
        assert service.get("library.view") == "Compact"
        service.set("library.view", "Grid")
        assert service.get("library.view") == "Grid"


class TestSettingsBridge:
    """Verify the SettingsBridge QObject class."""

    def test_bridge_creates_with_owner(self):
        from animevault.ui.settings_panel import SettingsBridge

        owner = FakeOwner()
        bridge = SettingsBridge(owner)
        assert bridge is not None
        assert bridge._owner is owner

    def test_bridge_has_expected_slots(self):
        from animevault.ui.settings_panel import SettingsBridge

        bridge = SettingsBridge(FakeOwner())
        # These are all @Slot-decorated methods
        assert hasattr(bridge, "getSettings")
        assert hasattr(bridge, "setSettings")
        assert hasattr(bridge, "apply_settings")
        assert hasattr(bridge, "settingsAction")
        assert hasattr(bridge, "getVersion")
        assert hasattr(bridge, "checkForUpdates")
        assert hasattr(bridge, "viewLicenses")

    def test_bridge_signals_exist(self):
        from animevault.ui.settings_panel import SettingsBridge

        bridge = SettingsBridge(FakeOwner())
        assert hasattr(bridge, "settingsChanged")
        assert hasattr(bridge, "settingsApplied")
        assert hasattr(bridge, "actionTriggered")


class TestBackupService:
    """Verify backup operations."""

    def test_backup_service_class_exists(self):
        from animevault.ui.settings_service import BackupService

        assert BackupService is not None


class TestCacheService:
    """Verify cache clearing."""

    def test_cache_service_class_exists(self):
        from animevault.ui.settings_service import CacheService

        assert CacheService is not None

    def test_cache_clear_returns_int(self):
        from animevault.ui.settings_service import CacheService

        service = CacheService()
        count = service.clear()
        assert isinstance(count, int)
        assert count >= 0


class TestNotificationService:
    """Verify notification settings."""

    def test_notification_service_class_exists(self):
        from animevault.ui.settings_service import NotificationService

        assert NotificationService is not None


class TestUpdateService:
    """Verify update check."""

    def test_update_service_class_exists(self):
        from animevault.ui.settings_service import UpdateService

        assert UpdateService is not None


class TestDialogLifecycle:
    """Verify the settings dialog lifecycle."""

    def test_settings_panel_creates_bridge(self):
        from animevault.ui.settings_panel import SettingsPanel

        panel = SettingsPanel()
        assert panel.bridge is not None
        assert hasattr(panel, "load_settings")
        assert hasattr(panel, "save_settings")
        assert hasattr(panel, "get_setting")
        assert hasattr(panel, "set_setting")
        assert hasattr(panel, "backup_database")
        assert hasattr(panel, "clear_cache")
        assert hasattr(panel, "get_cache_size")
        assert hasattr(panel, "check_for_updates")
        assert hasattr(panel, "view_licenses")
