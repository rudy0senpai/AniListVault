"""Settings panel: Qt-side backend for the LiquidGlass settings UI.

Provides the Python-side handlers for settings persistence, backup,
cache clearing, update checks, and license display. Connects to the
Qt bridge for two-way communication with the React component.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QObject, Signal, Slot, Qt
from PySide6.QtWebChannel import QWebChannel

from animevault.services.backup_service import backup_database
from animevault.services.cache_service import CacheService, get_cache_dir
from animevault.services.notification_service import NotificationService
from animevault.services.update_service import UpdateService, check_for_updates, view_licenses
from animevault.ui.settings_service import SettingsService, Settings

logger = logging.getLogger(__name__)


class SettingsBridge(QObject):
    """Qt bridge for the settings panel.

    Provides the React component with methods to read and write settings,
    and routes action buttons to the appropriate Python services.
    """

    #: Emitted when settings are changed in the UI (before Apply)
    settingsChanged = Signal(str)

    #: Emitted when settings are applied (after validation and persistence)
    settingsApplied = Signal(str)

    #: Emitted when an action button is triggered
    actionTriggered = Signal(str)

    def __init__(self, owner: Any) -> None:
        super().__init__(owner)
        self._owner = owner
        self._settings_service = SettingsService()
        self._notification_service = NotificationService()
        self._cache_service = CacheService()
        self._update_service = UpdateService()

    @Slot(result=str)
    def getSettings(self) -> str:
        """Return the current settings as a JSON string."""
        try:
            settings = self._settings_service.load()
            return json.dumps(settings.to_dict(), ensure_ascii=False)
        except Exception as exc:
            logger.exception("Failed to get settings: %s", exc)
            return json.dumps({"error": str(exc)})

    @Slot(str)
    def setSettings(self, settings_json: str) -> None:
        """Persist settings from a JSON string."""
        try:
            data = json.loads(settings_json)
            settings = Settings.from_dict(data)
            self._settings_service.save(settings)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Invalid settings JSON: %s", exc)

    @Slot(str)
    def settingsAction(self, action_id: str) -> None:
        """Handle a settings action button click."""
        logger.info("Settings action: %s", action_id)

        if action_id == "data.backupNow":
            self._on_back_up_database()
        elif action_id == "data.clearCache":
            self._on_clear_cache()
        elif action_id == "about.update":
            self._on_check_for_updates()
        elif action_id == "about.licenses":
            self._on_view_licenses()

    @Slot(result=str)
    def getVersion(self) -> str:
        """Return the application version."""
        from animevault import __version__
        return __version__

    @Slot()
    def checkForUpdates(self) -> tuple[bool, str]:
        """Check for updates and return (has_update, version)."""
        return check_for_updates()

    @Slot()
    def viewLicenses(self) -> None:
        """Display open-source licenses."""
        view_licenses()

    def _on_back_up_database(self) -> None:
        """Handle immediate database backup."""
        path = backup_database()
        if path is not None:
            self.settingsApplied.emit(json.dumps({"backup_path": str(path)}))
            self.actionTriggered.emit(f"backup_success:{path.name}")
        else:
            self.actionTriggered.emit("backup_failed:No database")

    def _on_clear_cache(self) -> None:
        """Handle cache clearing."""
        count = self._cache_service.clear()
        self.settingsApplied.emit(json.dumps({"cache_cleared": count}))
        self.actionTriggered.emit(f"cache_cleared:{count}")

    def _on_check_for_updates(self) -> None:
        """Check for updates."""
        has_update, version = self._update_service.check_for_updates()
        if has_update:
            self.actionTriggered.emit(f"update_available:{version}")
        else:
            self.actionTriggered.emit("update_current")

    def _on_view_licenses(self) -> None:
        """Display open-source licenses."""
        self.actionTriggered.emit("licenses_opened")


class SettingsPanel:
    """Manager for the settings panel UI.

    Provides a bridge between the Qt backend and the React settings
    component, handling persistence, actions, and UI events.
    """

    def __init__(self, parent: Optional[QObject] = None) -> None:
        self._bridge = SettingsBridge(parent)
        self._notification_service = NotificationService()
        self._cache_service = CacheService()
        self._update_service = UpdateService()
        self._settings_service = SettingsService()

    @property
    def bridge(self) -> SettingsBridge:
        """Return the Qt bridge for the settings panel."""
        return self._bridge

    def load_settings(self) -> dict[str, Any]:
        """Load and return current settings as a dict."""
        return self._settings_service.load().to_dict()

    def save_settings(self, settings: dict[str, Any]) -> None:
        """Save settings from a dict."""
        settings_obj = Settings.from_dict(settings)
        self._settings_service.save(settings_obj)

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a setting value by dot-notation key (e.g. "library.view")."""
        return self._settings_service.get(key, default)

    def set_setting(self, key: str, value: Any) -> None:
        """Set a setting value and persist."""
        self._settings_service.set(key, value)

    def backup_database(self) -> Optional[Path]:
        """Create an immediate database backup. Returns the backup path."""
        return backup_database()

    def clear_cache(self) -> int:
        """Clear the image cache. Returns number of files removed."""
        return self._cache_service.clear()

    def get_cache_size(self) -> int:
        """Return current cache size in bytes."""
        return self._cache_service.current_size()

    def check_for_updates(self) -> tuple[bool, str]:
        """Check for updates. Returns (has_update, version)."""
        return self._update_service.check_for_updates()

    def view_licenses(self) -> None:
        """Display open-source licenses."""
        self._update_service.view_licenses()

    def get_notification_defaults(self) -> dict[str, Any]:
        """Get notification preferences."""
        return {
            "enabled": self._notification_service._enabled,
            "episodes": self._notification_service._episodes,
            "reminders": self._notification_service._reminders,
            "badge_count": self._notification_service._badge_count,
        }

    def set_notification_defaults(self, **kwargs) -> None:
        """Set notification preferences."""
        if "enabled" in kwargs:
            self._notification_service.set_enabled(kwargs["enabled"])
        if "episodes" in kwargs:
            self._notification_service.set_episodes(kwargs["episodes"])
        if "reminders" in kwargs:
            self._notification_service.set_reminders(kwargs["reminders"])
        if "badge_count" in kwargs:
            self._notification_service.set_badge_count(kwargs["badge_count"])
