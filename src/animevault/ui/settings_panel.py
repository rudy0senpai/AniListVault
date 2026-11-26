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

from animevault.services.backup_service import backup_database, purge_old_backups
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
    closeRequested = Signal()

    def __init__(self, owner: Any) -> None:
        super().__init__(owner)
        self._owner = owner
        self._settings_service = SettingsService()
        self._notification_service = NotificationService()
        self._cache_service = CacheService()
        self._update_service = UpdateService()

    def validate_contract(self, required_slots: list[str], required_signals: list[str]) -> list[str]:
        """Return missing callable slots or signal attributes for WebChannel."""
        missing = [name for name in required_slots if not callable(getattr(self, name, None))]
        missing.extend(name for name in required_signals if not hasattr(self, name))
        return missing

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

    @Slot()
    def closeSettings(self) -> None:
        """Request that the native settings dialog close."""
        self.closeRequested.emit()

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
            keep = self._settings_service.load().data.get("keep", 7)
            purge_old_backups(max(1, int(keep)))
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

    @Slot(str, result=str)
    def apply_settings(self, settings_json: str) -> str:
        """Validate, save, and apply settings.

        Returns a JSON string with the result: {"status": "success", ...} or
        {"status": "error", "message": "..."}.
        """
        try:
            data = json.loads(settings_json)
            settings = Settings.from_dict(data)
            settings.validate()

            # Save atomically to the authoritative JSON persistence layer.
            self._settings_service.save(settings)

            # Apply supported changes to the running application.
            self._apply_settings(settings)

            logger.info("Settings applied: %s", settings.to_dict())
            return json.dumps({"status": "success"})
        except ValueError as exc:
            logger.exception("Settings validation failed: %s", exc)
            return json.dumps({"status": "error", "message": str(exc)})
        except Exception as exc:
            logger.exception("Failed to apply settings: %s", exc)
            return json.dumps({"status": "error", "message": str(exc)})

    def _apply_settings(self, settings: Settings) -> None:
        """Apply supported settings to the running application."""
        # Appearance & theme
        colors = settings.colors
        self._owner.set_appearance(
            theme_id=settings.themeId,
            accent=colors.get("accent", "#7ee8d0"),
            secondary=colors.get("secondary", "#b79cf5"),
            bg=colors.get("bg", "#0b1020"),
            surface=colors.get("surface", "#131a2e"),
            text=colors.get("text", "#e6ecfa"),
            glass=settings.glass,
            animations=settings.animations,
            reduce=settings.reduce,
        )

        # Library
        lib = settings.library
        self._owner.set_library_defaults(
            view=lib.get("view", "Grid"),
            show_progress=lib.get("progress", True),
            confirm_delete=lib.get("confirmDelete", True),
            auto_complete=lib.get("autoComplete", False),
        )

        owner_applies_remaining = callable(getattr(self._owner, "apply_additional_settings", None))
        if owner_applies_remaining:
            self._owner.apply_additional_settings(settings)

        # Notifications/cache fallback for bridge owners without app services.
        notif = settings.notifications
        if not owner_applies_remaining:
            self._notification_service.set_enabled(True)
            self._notification_service.set_episodes(notif.get("episodes", True))
            self._notification_service.set_reminders(notif.get("reminders", False))
            self._notification_service.set_badge_count(1 if notif.get("badge", True) else 0)

        # Performance
        perf = settings.performance
        if not owner_applies_remaining and hasattr(self._cache_service, "set_max_size"):
            self._cache_service.set_max_size(perf.get("cache", 500))

    def _apply_visibility(self, visible: bool) -> None:
        """Apply the visibility state of the settings panel."""
        if self._owner is not None:
            self._owner._settings_view.setVisible(visible)


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
