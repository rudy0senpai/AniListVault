"""Qt WebEngine host and narrow Python-to-React library bridge."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, QUrl, QUrlQuery, QTimer, Signal, Slot
from PySide6.QtGui import QCursor, QColor
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMenu, QMessageBox

logger = logging.getLogger(__name__)


def dashboard_records() -> list[dict[str, Any]]:
    """Read current model records through AnimeVault's existing data layer."""
    from animevault.models.anime import Anime
    from animevault.models.literature import Literature

    records = []
    for item in Anime.all():
        records.append({
            "id": f"anime:{item.id}", "title": item.title, "media_type": "anime",
            "format": item.media_type, "status": item.status, "tier": item.tier,
            "favorite": item.favorite, "progress": item.episodes_watched, "total": item.episodes,
            "genres": item.genres or [], "year": item.season_year, "score": item.score,
            "first_date": item.first_watched, "last_date": item.last_watched,
            "completed_date": item.completed_date,
        })
    for item in Literature.all():
        category = str(item.category or "").casefold()
        # Literature.category is normalized by the model constructor; reject
        # accidental anime values rather than silently counting them as anime.
        media_type = category if category in {"manga", "manhwa", "manhua"} else "unknown"
        started_at = str(item.started_at or "")
        records.append({
            "id": f"{media_type}:{item.id}", "title": item.title, "media_type": media_type,
            "format": item.format, "status": item.status, "tier": item.tier,
            "favorite": item.favorite, "progress": item.chapters_read, "total": item.chapters,
            "genres": item.genres or [], "year": int(started_at[:4]) if started_at[:4].isdigit() else None,
            "score": None, "first_date": item.first_read, "last_date": item.last_read,
            "completed_date": item.completed_date,
        })
    return records


def _value(record: Any, name: str, default: Any = None) -> Any:
    value = getattr(record, name, default)
    return value if value is not None else default


def _local_cover(path: Any) -> str | None:
    if not path:
        return None
    candidate = Path(str(path)).expanduser()
    if not candidate.is_file():
        return None
    return QUrl.fromLocalFile(str(candidate.resolve())).toString()


def to_card(record: Any) -> dict[str, Any]:
    """Map one existing Anime/Literature model to the stable UI data contract."""
    category = str(_value(record, "category", "") or "").casefold()
    is_literature = category in {"manga", "manhwa", "manhua"}
    media_type = category if is_literature else "anime"
    if is_literature:
        total = _value(record, "chapters", 0) or None
        progress = _value(record, "chapters_read", 0) or 0
        unit = "chapters"
        volume_count = _value(record, "volumes", 0) or None
        kind = _value(record, "format", "") or category.capitalize()
        native_title = _value(record, "title_native", "")
        genres = _value(record, "genres", []) or []
        contributors = _value(record, "authors", []) or []
        serialization = _value(record, "serialization", "")
        aired = " → ".join(filter(None, [str(_value(record, "started_at", "") or ""), str(_value(record, "ended_at", "") or "")]))
        fetched = _value(record, "metadata_fetched_at", "")
        source = _value(record, "source_provider", "")
        anilist = _value(record, "anilist_id")
        mal = _value(record, "mal_id")
        duration = None
        season = None
        year = None
        native_title = native_title or _value(record, "title_en", "")
        rereads = _value(record, "rewatches", 0) or 0
    else:
        total = _value(record, "episodes", 0) or None
        progress = _value(record, "episodes_watched", 0) or 0
        unit = "episodes"
        volume_count = None
        kind = _value(record, "media_type", "") or "Anime"
        native_title = _value(record, "title_ja", "") or _value(record, "title_en", "")
        genres = _value(record, "genres", []) or []
        contributors = _value(record, "studios", []) or []
        serialization = ""
        aired = " → ".join(filter(None, [str(_value(record, "aired_from", "") or ""), str(_value(record, "aired_to", "") or "")]))
        fetched = _value(record, "metadata_fetched_at", "")
        source = _value(record, "source_provider", "")
        anilist = _value(record, "anilist_id")
        mal = _value(record, "mal_id")
        duration = _value(record, "duration") or None
        season = _value(record, "season") or None
        year = _value(record, "season_year")
        rereads = None
    key = f"{media_type}:{_value(record, 'id', '')}"
    data = {
        "id": key,
        "recordId": _value(record, "id"),
        "mediaType": media_type,
        "title": str(_value(record, "title", "") or ""),
        "nativeTitle": native_title or None,
        "cover": _local_cover(_value(record, "cover_path" if is_literature else "poster_path", "") or ""),
        "type": str(kind or ""),
        "total": total,
        "progress": progress,
        "unit": unit,
        "volumes": volume_count,
        "status": _status_label(record, is_literature),
        "tier": _value(record, "tier"),
        "favorite": bool(_value(record, "favorite", False)),
        "rewatches": rereads,
        "duration": duration,
        "season": season,
        "year": year,
        "aired": aired or None,
        "genres": list(genres),
        "studios": list(contributors) if not is_literature else None,
        "authors": list(contributors) if is_literature else None,
        "serialization": serialization or None,
        "synopsis": _value(record, "synopsis", "") or None,
        "anilistId": anilist,
        "malId": mal,
        "source": source or None,
        "fetchedAt": fetched or None,
    }
    return {key: value for key, value in data.items() if value is not None}


def _status_label(record: Any, is_literature: bool) -> str:
    if is_literature and callable(getattr(record, "status_label", None)):
        return str(record.status_label())
    return str(_value(record, "status", "") or "").replace("_", " ").title()


class LibraryBridge(QObject):
    """Fast cached reads plus UI actions routed back to MainWindow."""
    libraryChanged = Signal(str)
    dashboardChanged = Signal()
    selectionChanged = Signal(int)
    selectionModeChanged = Signal(bool)
    categoryChanged = Signal(str)
    retryAvailableChanged = Signal(bool)

    # Canonical action registry: every valid menu action identifier.
    CANONICAL_ACTIONS = frozenset({
        "dashboard",
        "recommendations",
        "settings",
        "settings_panel",
        "import_xlsx",
        "import_csv",
        "import_sql",
        "export_csv",
        "export_xlsx",
        "export_ods",
        "export_sql",
        "backup",
        "fetch_missing",
        "refresh_all",
        "cloud_sync",
        "about",
        "open_readme",
        "delete_selected",
        "retry_failed",
        "toggle_selection_mode",
    })

    # (action, handler_attribute) pairs resolved via getattr instead of a
    # static dict, so missing methods are fail-closed instead of silent.
    ATTR_RESOLVED_ACTIONS = {
        "backup_now": "_on_backup",
        "clear_cache": "_on_clear_cache",
        "check_for_updates": "_on_check_for_updates",
        "view_licenses": "_on_view_licenses",
    }

    def __init__(self, owner: Any) -> None:
        super().__init__(owner)
        self._owner = owner
        self._records: dict[str, Any] = {}
        self._cards: list[dict[str, Any]] = []
        self._library_json = "[]"
        self._selected: set[str] = set()
        self._selection_mode = False

    def replace_library(self, records: list[Any]) -> None:
        new_records: dict[str, Any] = {}
        cards: list[dict[str, Any]] = []
        for record in records:
            card = to_card(record)
            cards.append(card)
            new_records[card["id"]] = record
        self._records = new_records
        self._cards = cards
        self._selected.intersection_update(self._records)
        self._library_json = json.dumps(self._cards, ensure_ascii=False)
        self._owner._on_web_selection_changed(self.selected_records())
        self.selectionChanged.emit(len(self._selected))
        self.libraryChanged.emit(json.dumps({"type": "reset", "items": self._cards}, ensure_ascii=False))
        self.dashboardChanged.emit()

    def update_record(self, record: Any) -> None:
        card = to_card(record)
        self._records[card["id"]] = record
        self._cards = [card if item["id"] == card["id"] else item for item in self._cards]
        self._library_json = json.dumps(self._cards, ensure_ascii=False)
        self.libraryChanged.emit(json.dumps({"type": "upsert", "item": card}, ensure_ascii=False))
        self.dashboardChanged.emit()

    @Slot(str, result=str)
    def getDashboard(self, filters_json: str) -> str:
        try:
            filters = json.loads(filters_json or "{}")
            if not isinstance(filters, dict):
                raise ValueError("Dashboard filters must be an object")
            allowed = {"media", "status", "format", "genre", "dates"}
            filters = {key: value for key, value in filters.items() if key in allowed and isinstance(value, str)}
            from animevault.ui.dashboard_stats import build_dashboard
            return json.dumps(build_dashboard(dashboard_records(), filters), ensure_ascii=False, default=str)
        except Exception as exc:
            logger.exception("Dashboard data request failed")
            return json.dumps({"error": str(exc), "updatedAt": None}, ensure_ascii=False)

    @Slot()
    def refreshDashboard(self) -> None:
        self.dashboardChanged.emit()

    @Slot(result=str)
    def getCategory(self) -> str:
        return str(self._owner._category)

    @Slot(result=int)
    def getSelectedCount(self) -> int:
        return len(self._selected)

    @Slot(result=bool)
    def getRetryAvailable(self) -> bool:
        return bool(getattr(self._owner, "_failed_items", []))

    @Slot(bool, int)
    def setMenuOpen(self, opened: bool, item_count: int) -> None:
        height = max(60, min(560, 100 + max(0, int(item_count)) * 44)) if opened else 60
        self._owner._set_menu_bar_height(height)

    @Slot(str)
    def menuAction(self, action: str) -> None:
        owner = self._owner
        if action.startswith("category:"):
            category = action.partition(":")[2]
            if category in {"anime", "manga", "manhwa", "manhua"}:
                owner._on_category_changed(category)
                owner._show_library()
            return

        # 1) Validate against the canonical action registry.
        if action not in self.CANONICAL_ACTIONS:
            logger.error(
                "Unknown menu action: %s (canonical set: %s)", action,
                sorted(self.CANONICAL_ACTIONS),
            )
            return

        # 2) Resolve the handler.
        handler: Callable[['MainWindow'], None] | None = None
        method_name = self.ATTR_RESOLVED_ACTIONS.get(action)
        if method_name is not None:
            handler = getattr(owner, method_name, None)
            if not callable(handler):
                logger.error(
                    "Action handler unavailable: %s (owner=%s)",
                    method_name, type(owner).__name__,
                )
                return
        else:
            # Static dict fallback (kept for backwards compatibility).
            handlers = {
                "dashboard": owner._show_dashboard,
                "recommendations": owner._show_recommendations,
                "settings": lambda: QTimer.singleShot(0, owner._show_settings_panel),
                "settings_panel": lambda: QTimer.singleShot(0, owner._show_settings_panel),
                "import_xlsx": owner._on_import_xlsx,
                "import_csv": owner._on_import_csv,
                "import_sql": owner._on_import_sql,
                "export_csv": lambda: owner._on_export("csv"),
                "export_xlsx": lambda: owner._on_export("xlsx"),
                "export_ods": lambda: owner._on_export("ods"),
                "export_sql": lambda: owner._on_export("sql"),
                "backup": owner._on_backup,
                "fetch_missing": lambda: owner._on_bulk_enrich(False),
                "refresh_all": lambda: owner._on_bulk_enrich(True),
                "cloud_sync": owner._on_cloud_sync,
                "about": owner._show_about,
                "open_readme": owner._show_readme,
                "delete_selected": owner._on_delete_selected,
                "retry_failed": owner._retry_failed_enrichment,
                "toggle_selection_mode": owner._toggle_selection_mode,
            }
            handler = handlers.get(action)

        if handler is None:
            logger.error("No handler resolved for action: %s", action)
            return

        # 3) Execute with diagnostic logging (no bare tracebacks to UI).
        try:
            logger.info("menuAction: action=%s handler=%s owner=%s",
                        action, getattr(handler, '__name__', str(handler)),
                        type(owner).__name__)
            handler()
        except Exception as exc:
            # Fail-safe: log detail server-side, show a user-friendly message.
            logger.exception("Failed to execute menuAction %s", action)
            try:
                QMessageBox.critical(
                    owner, "Action failed",
                    f"Could not complete the action. Please try again.\n\n"
                    f"Details: {exc.__class__.__name__}",
                )
            except Exception:
                pass

    @Slot(result=str)
    def getLibrary(self) -> str:
        return self._library_json

    @Slot(str)
    def openRecord(self, record_key: str) -> None:
        record = self._records.get(record_key)
        if record is not None:
            self._owner._on_details(record)

    @Slot()
    def openRecommendations(self) -> None:
        self._owner._show_recommendations()

    @Slot(str)
    def showMenu(self, record_key: str) -> None:
        record = self._records.get(record_key)
        if record is None:
            return
        menu = QMenu(self._owner)
        details = menu.addAction("View Details")
        edit = menu.addAction("Edit")
        refresh = menu.addAction("Fetch / Refresh Metadata")
        menu.addSeparator()
        delete = menu.addAction("Delete")
        chosen = menu.exec(QCursor.pos())
        if chosen == details:
            self._owner._on_details(record)
        elif chosen == edit:
            self._owner._on_edit(record)
        elif chosen == refresh:
            self._owner._on_refresh_one(record)
        elif chosen == delete:
            self._owner._on_delete_one(record)

    @Slot(str, bool)
    def setSelected(self, record_key: str, selected: bool) -> None:
        if record_key not in self._records:
            return
        if selected:
            self._selected.add(record_key)
        else:
            self._selected.discard(record_key)
        self._owner._on_web_selection_changed(self.selected_records())
        self.selectionChanged.emit(len(self._selected))

    @Slot(bool)
    def setSelectionMode(self, enabled: bool) -> None:
        self._selection_mode = bool(enabled)
        if not self._selection_mode:
            self._selected.clear()
        self._owner._on_web_selection_mode_changed(self._selection_mode)
        self._owner._on_web_selection_changed(self.selected_records())
        self.selectionChanged.emit(len(self._selected))
        self.selectionModeChanged.emit(self._selection_mode)

    def update_poster(self, item_id: int, path: str) -> None:
        for record in self._records.values():
            if getattr(record, "id", None) != item_id:
                continue
            if str(_value(record, "category", "") or "").casefold() in {"manga", "manhwa", "manhua"}:
                record.cover_path = path
            else:
                record.poster_path = path
            self.update_record(record)
            break

    def selected_records(self) -> list[Any]:
        return [self._records[key] for key in self._selected if key in self._records]

    # ── Bridge contract validation ───────────────────────────────
    def validate_contract(self, required_slots: list[str], required_signals: list[str]) -> list[str]:
        """Validate that the bridge exposes all required slots and signals.

        Returns a list of missing names (empty list means contract is satisfied).
        """
        missing = []
        for name in required_slots:
            if not hasattr(self, name) or not callable(getattr(self, name)):
                missing.append(name)
        for name in required_signals:
            if not hasattr(self, name):
                missing.append(name)
        return missing



Bridge = LibraryBridge


class AnimeWebView(QWebEngineView):
    """Embedded React surface, with a Vite URL override for development."""

    # Required slots/signals for the library bridge contract
    _LIBRARY_BRIDGE_SLOTS = [
        "getLibrary", "getDashboard", "refreshDashboard", "getCategory",
        "getSelectedCount", "getRetryAvailable", "setMenuOpen", "menuAction",
        "openRecord", "openRecommendations", "showMenu", "setSelected",
        "setSelectionMode", "update_poster", "replace_library", "libraryChanged",
        "dashboardChanged", "selectionChanged", "selectionModeChanged",
        "categoryChanged", "retryAvailableChanged",
    ]
    _LIBRARY_BRIDGE_SIGNALS = [
        "libraryChanged", "dashboardChanged", "selectionChanged",
        "selectionModeChanged", "categoryChanged", "retryAvailableChanged",
    ]

    # Required settings bridge contract
    _SETTINGS_BRIDGE_SLOTS = [
        "getSettings", "setSettings", "settingsAction", "getVersion",
        "apply_settings", "closeSettings",
    ]
    _SETTINGS_BRIDGE_SIGNALS = ["settingsChanged", "settingsApplied", "actionTriggered", "closeRequested"]

    def __init__(self, owner: Any, bridge: QObject | None = None, surface: str = "library") -> None:
        super().__init__(owner)
        if bridge is None:
            bridge = LibraryBridge(owner)
        self.bridge = bridge
        if surface == "settings":
            self._validate_bridge_contract(self.bridge, self._SETTINGS_BRIDGE_SLOTS, self._SETTINGS_BRIDGE_SIGNALS)
        else:
            self._validate_bridge_contract(self.bridge, self._LIBRARY_BRIDGE_SLOTS, self._LIBRARY_BRIDGE_SIGNALS)
        self.channel = QWebChannel(self.page())
        self.channel.registerObject("bridge", self.bridge)
        self.page().setWebChannel(self.channel)
        settings = self.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        dev_url = os.environ.get("ANIMEVAULT_DEV_URL", "").strip()
        page = Path(__file__).parent / "web" / "dist" / "index.html"
        url = QUrl(dev_url) if dev_url else QUrl.fromLocalFile(str(page.resolve()))
        query = QUrlQuery(url)
        if surface != "library":
            query.addQueryItem("surface", surface)
            url.setQuery(query)
            self.page().setBackgroundColor(QColor(0, 0, 0, 0))
            self.setStyleSheet("background: transparent;")
        self.setUrl(url)

    @classmethod
    def _validate_bridge_contract(cls, bridge: QObject, required_slots: list[str], required_signals: list[str]) -> None:
        """Validate the bridge contract; raise on missing methods/signals."""
        missing = bridge.validate_contract(required_slots, required_signals)
        if missing:
            raise RuntimeError(f"Bridge contract validation failed: missing {missing}")
