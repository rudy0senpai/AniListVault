"""Centralized settings service for AnimeVault.

Replaces the old ``ThemeSettingsDialog`` with a comprehensive settings
system covering appearance, library, notifications, data storage, metadata,
recommendations, performance, language and about sections.

Settings are persisted to a JSON file in the user's app data directory,
with QSettings retained for legacy appearance preferences. This gives
single-source-of-truth semantics and survives application restarts.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from animevault import __version__
from animevault.media_types import MEDIA_ANIME, MEDIA_MANGA, MEDIA_MANHWA, MEDIA_MANHUA

logger = logging.getLogger(__name__)

# ── Paths ────────────────────────────────────────────────────────

_APP_DIR = Path(os.environ.get("APPDATA", Path.home() / ".local")) / "AnimeVault"
_SETTINGS_DIR = _APP_DIR / "config"
_SETTINGS_FILE = _SETTINGS_DIR / "settings.json"
_DEFAULTS_BACKUP_DIR = _APP_DIR / "backups"
_CACHE_DIR = _APP_DIR / "cache" / "posters"


# ── Default settings ─────────────────────────────────────────────

def default_values() -> dict[str, Any]:
    """Return the full default settings dictionary."""
    from .theme import ACCENT, ACCENT_DIM, ACCENT_VIOLET, TEXT_PRIMARY, TEXT_SECONDARY

    return {
        # Appearance
        "themeId": "midnight",
        "colors": {
            "accent": ACCENT,
            "secondary": ACCENT_VIOLET,
            "bg": "#0b1020",
            "surface": "#131a2e",
            "text": TEXT_PRIMARY,
        },
        "customThemes": [],
        "glass": 70,
        "animations": True,
        "reduce": False,

        # Library
        "library": {
            "view": "Grid",
            "progress": True,
            "confirmDelete": True,
            "autoComplete": False,
        },

        # Notifications
        "notifications": {
            "episodes": True,
            "reminders": False,
            "lead": "1 day before",
            "badge": True,
        },

        # Data & Storage
        "data": {
            "autoBackup": True,
            "every": "Weekly",
            "keep": 7,
            "backupNow": False,
            "clearCache": False,
        },

        # Metadata
        "metadata": {
            "source": "AniList",
            "onStart": False,
            "overwrite": False,
            "autoRetry": True,
        },

        # Recommendations
        "recommendations": {
            "basis": "Both",
            "count": 20,
            "hidePlanned": True,
            "adult": False,
        },

        # Performance
        "performance": {
            "gpu": True,
            "cache": 500,
            "lazy": True,
            "virtual": True,
        },

        # Language
        "language": {
            "lang": "English",
            "titles": "Romaji",
            "date": "DD/MM/YYYY",
        },

        # About
        "about": {
            "version": __version__,
            "update": False,
            "licenses": False,
        },

        # Frontend preferences not yet mapped to native behavior are preserved.
        "values": {},
    }


# ── Settings dataclass ───────────────────────────────────────────

def should_auto_complete(progress: int, total: int | None, enabled: bool) -> bool:
    """Return whether reaching the known total should mark an item complete."""
    if not enabled or total is None or isinstance(total, bool) or total <= 0:
        return False
    if isinstance(progress, bool):
        return False
    return int(progress) >= int(total)

@dataclass
class Settings:
    """Typed settings model.\n\n    All fields are optional with defaults; missing keys are filled
    from defaults. Validation is performed in :meth:`validate`.
    """

    # Appearance
    themeId: str = "midnight"
    colors: dict[str, str] = field(default_factory=lambda: default_values()["colors"])
    customThemes: list[dict[str, Any]] = field(default_factory=list)
    glass: int = 70
    animations: bool = True
    reduce: bool = False

    # Library
    library: dict[str, Any] = field(default_factory=lambda: default_values()["library"])

    # Notifications
    notifications: dict[str, Any] = field(default_factory=lambda: default_values()["notifications"])

    # Data & Storage
    data: dict[str, Any] = field(default_factory=lambda: default_values()["data"])

    # Metadata
    metadata: dict[str, Any] = field(default_factory=lambda: default_values()["metadata"])

    # Recommendations
    recommendations: dict[str, Any] = field(default_factory=lambda: default_values()["recommendations"])

    # Performance
    performance: dict[str, Any] = field(default_factory=lambda: default_values()["performance"])

    # Language
    language: dict[str, Any] = field(default_factory=lambda: default_values()["language"])

    # About
    about: dict[str, Any] = field(default_factory=lambda: default_values()["about"])

    # Additional UI values are retained for forward-compatible persistence.
    values: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        """Validate all settings. Raises ValueError on invalid values."""
        # Glass intensity 0-100
        if not 0 <= self.glass <= 100:
            raise ValueError(f"glass must be 0-100, got {self.glass}")
        # Cache size 100-2000 MB
        if not 100 <= self.performance.get("cache", 500) <= 2000:
            raise ValueError(f"cache size must be 100-2000, got {self.performance.get('cache')}")
        # Backups to keep 1-30
        keep = self.data.get("keep", 7)
        if not 1 <= keep <= 30:
            raise ValueError(f"backups to keep must be 1-30, got {keep}")
        # Recommendation count 5-50, step 5
        count = self.recommendations.get("count", 20)
        if not 5 <= count <= 50 or count % 5 != 0:
            raise ValueError(f"recommendation count must be 5-50 (step 5), got {count}")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Settings":
        """Build settings from bridge values and nested persisted sections."""
        data = dict(data)
        defaults = default_values()
        sections = ("library", "notifications", "data", "metadata",
                    "recommendations", "performance", "language", "about")
        for section in sections:
            data[section] = {**defaults[section], **(data.get(section) or {})}
        for key, value in (data.get("values") or {}).items():
            section, dot, name = key.partition(".")
            if dot and section in sections and name in defaults[section]:
                data[section][name] = value
        data["values"] = data.get("values") or {}
        for key in ("themeId", "glass", "animations", "reduce", "customThemes"):
            data.setdefault(key, defaults[key])
        data["colors"] = {**defaults["colors"], **(data.get("colors") or {})}
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON storage."""
        result = {
            "themeId": self.themeId,
            "colors": self.colors,
            "customThemes": self.customThemes,
            "glass": self.glass,
            "animations": self.animations,
            "reduce": self.reduce,
        }
        for section in ("library", "notifications", "data", "metadata",
                        "recommendations", "performance", "language", "about"):
            result[section] = getattr(self, section)
        result["values"] = self.values
        return result


# ── Settings service ─────────────────────────────────────────────

class SettingsService:
    """Centralized settings service with QSettings + JSON persistence."""

    def __init__(self, app: Any | None = None) -> None:
        self._app = app
        self._settings = self._get_qsettings()
        self._data: Settings | None = None

    def _get_qsettings(self) -> "QSettings":
        from PySide6.QtCore import QSettings
        return QSettings("AnimeVault", "AnimeVault")

    def _load(self) -> dict[str, Any]:
        """Load raw settings from disk, merging with defaults and legacy QSettings."""
        raw = default_values()
        # 1. Try JSON file
        if _SETTINGS_FILE.is_file():
            try:
                raw.update(json.loads(_SETTINGS_FILE.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to read settings JSON: %s", exc)
        # 2. Migrate legacy QSettings keys
        for key in self._settings.allKeys():
            if key.startswith("ui/"):
                # e.g. ui/glass_cards — map to appearance
                pass
        return raw

    def load(self) -> Settings:
        """Load and validate settings. Returns a validated Settings instance."""
        raw = self._load()
        merged = default_values()
        merged.update(raw)
        settings = Settings.from_dict(merged)
        settings.validate()
        self._data = settings
        return settings

    def save(self, settings: Settings) -> None:
        """Validate and persist settings."""
        settings.validate()
        self._data = settings
        _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        _SETTINGS_FILE.write_text(json.dumps(settings.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        # Update legacy QSettings for appearance preferences
        self._settings.setValue("appearance/reduce_effects", settings.reduce)
        self._settings.setValue("appearance/liquid_glass", True)
        self._settings.sync()

    @property
    def data(self) -> Settings:
        """Current settings (load from disk if needed)."""
        if self._data is None:
            self.load()
        return self._data

    def get(self, key: str, default: Any = None) -> Any:
        """Get a setting value by dot-notation key (e.g. "library.view")."""
        path = key.split(".")
        data = self.data.to_dict()
        value: Any = data
        for part in path:
            if isinstance(value, dict):
                value = value.get(part, default)
            else:
                return default
        return value

    def set(self, key: str, value: Any) -> None:
        """Set a setting value and persist."""
        path = key.split(".")
        data = self.data.to_dict()
        target: dict[str, Any] = data
        for part in path[:-1]:
            target = target.setdefault(part, {})
        target[path[-1]] = value
        settings = Settings.from_dict(data)
        self.save(settings)


# ── Backup service ───────────────────────────────────────────────

class BackupService:
    """Database backup and retention management."""

    def __init__(self, app: Any | None = None) -> None:
        self._settings_service: SettingsService = SettingsService(app)
        self._db_path = self._resolve_db_path()

    def _resolve_db_path(self) -> Path:
        from animevault.database import database_path
        return database_path()

    def backup(self) -> Optional[Path]:
        """Create an immediate database backup. Returns the backup path."""
        if not self._db_path.exists():
            return None
        try:
            _DEFAULTS_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = _DEFAULTS_BACKUP_DIR / f"animevault_{timestamp}.backup"
            # Use SQLite backup API for a safe, atomic copy
            import sqlite3
            with sqlite3.connect(str(self._db_path)) as src:
                with sqlite3.connect(str(backup_path)) as dst:
                    dst.backup(src)
            return backup_path
        except Exception as exc:
            logger.exception("Backup failed: %s", exc)
            return None

    def schedule(self) -> None:
        """Run scheduled backup if configured. Returns True if a backup was created."""
        settings = self._settings_service.load()
        if not settings.data.get("data", {}).get("autoBackup", False):
            return False
        freq = settings.data.get("data", {}).get("every", "Weekly")
        if freq == "Daily":
            self.backup()
        elif freq == "Weekly":
            from datetime import datetime
            if datetime.now().weekday() == 0:
                self.backup()
        elif freq == "Monthly":
            from datetime import datetime
            if datetime.now().day == 1:
                self.backup()
        return True

    def purge_old_backups(self, keep: int = 7) -> int:
        """Delete old backups beyond the retention limit. Returns number deleted."""
        if not _DEFAULTS_BACKUP_DIR.is_dir():
            return 0
        try:
            backups = sorted(_DEFAULTS_BACKUP_DIR.glob("animevault_*.backup"),
                            key=lambda p: p.stat().st_mtime, reverse=True)
            deleted = 0
            for backup in backups[keep:]:
                backup.unlink()
                deleted += 1
            return deleted
        except Exception as exc:
            logger.exception("Backup purge failed: %s", exc)
            return 0


# ── Cache service ────────────────────────────────────────────────

class CacheService:
    """Image cache management with LRU eviction."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self._cache_dir = cache_dir or _CACHE_DIR
        self._lock = threading.Lock()
        self._current_size = 0
        self._max_size = 500 * 1024 * 1024  # 500 MB default
        self._poster_cache: dict[str, Path] = {}
        self._load_cache_state()

    def _load_cache_state(self) -> None:
        """Load cache state from disk (simple approximation)."""
        if self._cache_dir.is_dir():
            total = 0
            for f in self._cache_dir.iterdir():
                if f.is_file():
                    total += f.stat().st_size
            self._current_size = total

    def set_max_size(self, max_mb: int) -> None:
        """Set the maximum cache size (in MB)."""
        self._max_size = max_mb * 1024 * 1024
        self._enforce_limit()

    def current_size(self) -> int:
        """Return current cache size in bytes."""
        return self._current_size

    def _enforce_limit(self) -> None:
        """Evict oldest files if over limit (simple size-based cleanup)."""
        with self._lock:
            if self._current_size <= self._max_size:
                return
            # Get files sorted by modification time (oldest first)
            files = []
            for f in self._cache_dir.iterdir():
                if f.is_file():
                    files.append((f.stat().st_mtime, f))
            files.sort()
            for _, f in files:
                if self._current_size <= self._max_size:
                    break
                try:
                    self._current_size -= f.stat().st_size
                    f.unlink()
                except Exception:
                    pass

    def clear(self) -> int:
        """Clear the entire cache. Returns number of files removed."""
        with self._lock:
            count = 0
            for f in self._cache_dir.iterdir():
                if f.is_file():
                    try:
                        f.unlink()
                        count += 1
                    except Exception:
                        pass
            self._current_size = 0
            return count


# ── Notification service ─────────────────────────────────────────

class NotificationService:
    """Desktop notification wrapper with fallback to in-app notifications."""

    def __init__(self, app: Any | None = None) -> None:
        self._enabled = True
        self._badge_count = 0
        self._episodes = True
        self._reminders = False

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def set_episodes(self, enabled: bool) -> None:
        self._episodes = enabled

    def set_reminders(self, enabled: bool) -> None:
        self._reminders = enabled

    def new_episode_alert(self, title: str, episode: int) -> None:
        """Show a new episode notification."""
        if not self._enabled or not self._episodes:
            return
        self._show_notification(f"New episode alert", f"{title} — episode {episode} released")

    def release_reminder(self, title: str, date: str) -> None:
        """Show a release reminder."""
        if not self._enabled or not self._reminders:
            return
        self._show_notification(f"Release reminder", f"{title} releases on {date}")

    def _show_notification(self, title: str, message: str) -> None:
        """Platform notification with fallback to in-app."""
        try:
            from PySide6.QtGui import QGuiApplication
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None and hasattr(app, "showNotification"):
                app.showNotification(title, message)
        except Exception as exc:
            logger.debug("Desktop notification unavailable: %s", exc)
            # Fallback: in-app toast notification
            self._in_app_toast(title, message)

    def _in_app_toast(self, title: str, message: str) -> None:
        """Fallback in-app notification."""
        from PySide6.QtWidgets import QApplication, QLabel
        app = QApplication.instance()
        if app is None:
            return
        toast = QLabel(f"<b>{title}</b><br>{message}")
        toast.setStyleSheet("background:rgba(163,238,226,0.2);color:#f4f6fb;border-radius:8px;padding:8px 12px;font-size:13px;")
        toast.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        toast.show()


# ── Update service ───────────────────────────────────────────────

class UpdateService:
    """Application update checker."""

    def __init__(self, app: Any | None = None) -> None:
        self._app = app
        # Default GitHub releases endpoint (configurable in ThemeSettingsDialog)
        self._releases_url = "https://api.github.com/repos/rudy0senpai/AniListVault/releases/latest"

    def check_for_updates(self) -> tuple[bool, str]:
        """Check for updates. Returns (has_update, version_string)."""
        import urllib.request
        import json
        try:
            req = urllib.request.Request(self._releases_url, headers={"User-Agent": "AnimeVault"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                latest = data.get("tag_name", "")
                return (latest != __version__, latest)
        except Exception as exc:
            logger.exception("Update check failed: %s", exc)
            return (False, f"Error checking for updates: {exc}")

    def view_licenses(self) -> None:
        """Display the project's open-source licenses."""
        # Show a dialog with license info (basic implementation)
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            None, "Open Source Licenses",
            "AnimeVault uses the following:\n\n"
            "• PySide6 (Qt for Python) — BSD-style license\n"
            "• SQLite — Public Domain\n"
            "• scikit-learn — BSD-style license\n"
            "• React/Vite — MIT license\n"
            "• Various npm packages — MIT/Apache-2.0\n\n"
            "See https://github.com/rudy0senpai/AniListVault for full details.",
        )


# ── Localization service ─────────────────────────────────────────

class LocalizationService:
    """Centralized localization for AnimeVault."""

    _LOCALES = {
        "English": {
            "app": "AnimeVault",
            "settings": "Settings",
            "save": "Save",
            "cancel": "Cancel",
            "delete": "Delete",
            "confirm": "Confirm",
            "ok": "OK",
            "apply": "Apply",
            "restore": "Restore",
            "search": "Search",
            "theme": "Theme",
            "accent": "Accent colour",
            "glass": "Glass intensity",
            "animations": "Animations",
            "reduce": "Reduce effects",
            "library": "Library",
            "view": "Default view",
            "progress": "Show progress",
            "delete_confirm": "Confirm before deleting",
            "auto_complete": "Auto complete",
            "notifications": "Notifications",
            "new_episode": "New episode alerts",
            "release_reminder": "Release reminders",
            "reminder_lead": "Reminder lead time",
            "badge": "App icon badge count",
            "data": "Data & Storage",
            "auto_backup": "Automatic backups",
            "backup_freq": "Backup frequency",
            "backups_to_keep": "Backups to keep",
            "back_up_now": "Back up now",
            "clear_cache": "Clear cache",
            "metadata": "Metadata",
            "source": "Metadata source",
            "fetch_on_start": "Fetch missing data on startup",
            "overwrite": "Overwrite existing fields",
            "auto_retry": "Retry failed lookups",
            "recommendations": "Recommendations",
            "basis": "Base suggestions on",
            "num_suggestions": "Number of suggestions",
            "hide_planned": "Hide Plan to Watch",
            "adult": "Include adult titles",
            "performance": "Performance",
            "hardware_accel": "Hardware acceleration",
            "cache_size": "Image cache size",
            "lazy_load": "Lazy-load posters",
            "virtual_list": "Virtualize long lists",
            "language": "Language",
            "app_language": "App language",
            "title_language": "Anime title language",
            "date_format": "Date format",
            "about": "About",
            "version": "Version",
            "check_updates": "Check for Updates",
            "licenses": "Open source licenses",
            "restart_required": "Restart required to take effect",
            "apply_success": "Settings applied successfully",
        },
        "日本語": {
            "app": "AnimeVault",
            "settings": "設定",
            "save": "保存",
            "cancel": "キャンセル",
            "delete": "削除",
            "confirm": "確認",
            "ok": "OK",
            "apply": "適用",
            "restore": "デフォルトに戻す",
            "search": "検索",
            "theme": "テーマ",
            "accent": "アクセント色",
            "glass": "ガラス濃度",
            "animations": "アニメーション",
            "reduce": "効果を減らす",
            "library": "ライブラリ",
            "view": "デフォルト表示",
            "progress": "進捗を表示",
            "delete_confirm": "削除前に確認",
            "auto_complete": "自動完了",
            "notifications": "通知",
            "new_episode": "新エピソード通知",
            "release_reminder": "発売リマインダー",
            "reminder_lead": "リマインダー時間",
            "badge": "アプリアイコンにバッジを表示",
            "data": "データと保存",
            "auto_backup": "自動バックアップ",
            "backup_freq": "バックアップ頻度",
            "backups_to_keep": "保持するバックアップ数",
            "back_up_now": "今すぐバックアップ",
            "clear_cache": "キャッシュをクリア",
            "metadata": "メタデータ",
            "source": "メタデータソース",
            "fetch_on_start": "起動時にデータを取得",
            "overwrite": "既存フィールドを上書き",
            "auto_retry": "失敗した検索を自動再試行",
            "recommendations": "おすすめ",
            "basis": "推薦の基準",
            "num_suggestions": "おすすめ数",
            "hide_planned": "計画中の作品を隠す",
            "adult": "成人向け作品を含める",
            "performance": "パフォーマンス",
            "hardware_accel": "ハードウェアアクセラレーション",
            "cache_size": "画像キャッシュサイズ",
            "lazy_load": "ポスターを遅延読み込み",
            "virtual_list": "長いリストを仮想化",
            "language": "言語",
            "app_language": "アプリ言語",
            "title_language": "作品タイトルの言語",
            "date_format": "日付形式",
            "about": "について",
            "version": "バージョン",
            "check_updates": "更新を確認",
            "licenses": "オープンソースライセンス",
            "restart_required": "再起動が必要です",
            "apply_success": "設定を適用しました",
        },
        # ... additional locales would go here
    }

    def __init__(self, app: Any | None = None) -> None:
        self._settings_service = SettingsService(app)
        self._lang = self._settings_service.get("language.lang", "English")

    def set_language(self, lang: str) -> None:
        self._lang = lang
        self._settings_service.set("language.lang", lang)

    def get(self, key: str, **kwargs) -> str:
        """Get a translated string."""
        translations = self._LOCALES.get(self._lang, self._LOCALES["English"])
        text = translations.get(key, translations.get("English", {}).get(key, key))
        # Simple placeholder replacement
        for k, v in kwargs.items():
            text = text.replace(f"{{{k}}}", str(v))
        return text
