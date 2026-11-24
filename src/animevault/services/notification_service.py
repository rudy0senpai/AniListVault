"""Desktop notification service for AnimeVault.

Provides desktop notifications with fallback to in-app notifications
when platform notification support is unavailable.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class NotificationService:
    """Desktop notification wrapper with fallback to in-app notifications."""

    def __init__(self) -> None:
        self._enabled = True
        self._episodes = True
        self._reminders = False
        self._badge_count = 0

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def set_episodes(self, enabled: bool) -> None:
        self._episodes = enabled

    def set_reminders(self, enabled: bool) -> None:
        self._reminders = enabled

    def set_badge_count(self, count: int) -> None:
        self._badge_count = count

    def increment_badge_count(self) -> int:
        """Increment and return the current badge count."""
        self._badge_count += 1
        return self._badge_count

    def reset_badge_count(self) -> int:
        """Reset badge count to zero and return the old value."""
        old = self._badge_count
        self._badge_count = 0
        return old

    def new_episode_alert(self, title: str, episode: int) -> None:
        """Show a new episode notification."""
        if not self._enabled or not self._episodes:
            return
        self._show_notification("New episode alert", f"{title} — episode {episode} released")

    def release_reminder(self, title: str, date: str) -> None:
        """Show a release reminder."""
        if not self._enabled or not self._reminders:
            return
        self._show_notification("Release reminder", f"{title} releases on {date}")

    def _show_notification(self, title: str, message: str) -> None:
        """Platform notification with fallback to in-app."""
        try:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None and hasattr(app, "showNotification"):
                app.showNotification(title, message)
        except Exception as exc:
            logger.debug("Desktop notification unavailable: %s", exc)
            # Fallback: in-app toast notification
            self._in_app_toast(title, message)

    def _in_app_toast(self, title: str, message: str) -> None:
        """Fallback in-app notification using a toast label."""
        from PySide6.QtWidgets import QApplication, QLabel
        from PySide6.QtCore import Qt

        app = QApplication.instance()
        if app is None:
            return

        toast = QLabel(f"<b>{title}</b><br>{message}")
        toast.setStyleSheet(
            "background:rgba(163,238,226,0.2);color:#f4f6fb;border-radius:8px;"
            "padding:8px 12px;font-size:13px;"
        )
        toast.setWindowFlags(
            Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        toast.show()
