"""Redesigned main window: header, tabs, toolbar, search row, grid, sidebar."""

from __future__ import annotations

import logging
import os
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize, Qt, Signal, QSettings, QTimer
from PySide6.QtGui import QAction, QKeySequence, QShortcut, QColor
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QDialog,
)

from animevault.media_types import (
    CATEGORY_LABELS,
    MEDIA_ANIME,
    MEDIA_MANGA,
    MEDIA_MANHWA,
    MEDIA_MANHUA,
    type_options,
)
from animevault.models.anime import VALID_STATUSES, Anime
from animevault.models.literature import Literature
from animevault.tiers import TIERS
from animevault.ui.card_factory import anime_card, literature_card
from animevault.ui.card_grid import CardGrid
from animevault.ui.media_card import MediaCard
from animevault.ui.dashboard_analytics import SummaryKpiCard
from animevault.ui.details_dialog import DetailsDialog
from animevault.ui.add_media_dialog import AddMediaDialog

from animevault.ui.video_background import DEFAULT_OPACITY as BACKGROUND_OPACITY
from animevault.ui.video_background import VideoBackground
from animevault.ui.theme import application_stylesheet
from animevault.ui.visual_effects import HoverLiftButton, RadialGradientLabel
from animevault.ui.scroll_animation import ScrollRevealArea

# Services
from animevault.services.backup_service import backup_database, purge_old_backups
from animevault.services.cache_service import CacheService
from animevault.services.notification_service import NotificationService
from animevault.services.update_service import UpdateService, view_licenses
from animevault.ui.settings_service import SettingsService, Settings
from animevault.ui.settings_panel import SettingsPanel
from animevault.ui.liquid_bubble_topbar import LiquidBubbleTopBar

#: Sort modes offered in the Sort control.
SORT_OPTIONS = [
    ("Title A–Z", "title"),
    ("Title Z–A", "title_desc"),
    ("Tier", "tier"),
    ("Recently Added", "added"),
    ("Recently Updated", "updated"),
    ("Release Year", "year"),
    ("Progress", "progress"),
    ("Episodes / Chapters", "episodes"),
]


class MainWindow(QMainWindow):
    """Top-level window: navigation, search, media grid and analytics."""

    library_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AnimeVault")
        self.resize(1600, 900)
        self.setMinimumSize(900, 600)
        self.setStyleSheet(application_stylesheet())

        self._bulk_worker = None
        self._progress_dialog: Optional[QProgressDialog] = None
        self._failed_items: list = []
        self._last_enrichment_stats: dict = {}

        self._category = MEDIA_ANIME
        self._search_text = ""
        self._filter_status = "All"
        self._filter_type = "All"
        self._filter_tier = "all"
        self._sort_mode = "title"
        self._select_mode = False
        self._settings = QSettings("AnimeVault", "AnimeVault")
        self._cache_service = CacheService()
        self._notification_service = NotificationService()
        self._backup_timer = QTimer(self)
        self._backup_timer.setInterval(60 * 60 * 1000)
        self._backup_timer.timeout.connect(self._maybe_create_scheduled_backup)
        try:
            self._saved_settings = SettingsService().load()
        except Exception:
            logger.exception("Could not load saved settings; using defaults")
            self._saved_settings = Settings()
        self._appearance_preferences = {
            "colors": self._saved_settings.colors,
            "glass": self._saved_settings.glass,
            "animations": self._saved_settings.animations,
            "reduce": self._saved_settings.reduce,
        }
        self._library_preferences = dict(self._saved_settings.library)
        self._glass_cards_enabled = self._settings.value("ui/glass_cards", True, type=bool)
        if os.environ.get("ANIMEVAULT_GLASS_CARDS", "").strip() in {"0", "false", "off"}:
            self._glass_cards_enabled = False
        self._web_selected: list = []
        self._web_view = None
        self._menu_web_view = None
        self._navbar_web_view = None
        self._topbar_available = False
        self._shared_bridge = None
        self._web_view_class = None

        self._build_ui()
        self._build_shortcuts()
        self.set_appearance(
            theme_id=self._saved_settings.themeId,
            accent=self._saved_settings.colors.get("accent", "#a3eee2"),
            secondary=self._saved_settings.colors.get("secondary", "#c7b6ff"),
            bg=self._saved_settings.colors.get("bg", "#0a0c10"),
            surface=self._saved_settings.colors.get("surface", "#121722"),
            text=self._saved_settings.colors.get("text", "#f4f6fb"),
            glass=self._saved_settings.glass,
            animations=self._saved_settings.animations,
            reduce=self._saved_settings.reduce,
        )
        self.set_library_defaults(
            view=self._saved_settings.library.get("view", "Grid"),
            show_progress=self._saved_settings.library.get("progress", True),
            confirm_delete=self._saved_settings.library.get("confirmDelete", True),
            auto_complete=self._saved_settings.library.get("autoComplete", False),
        )
        self.apply_additional_settings(self._saved_settings)
        self._backup_timer.start()
        from animevault.ui.theme import liquid_glass, reduce_effects
        self._background.set_effects_reduced(reduce_effects())
        self._set_liquid_glass(liquid_glass())

        self.library_changed.connect(self.refresh)
        self.refresh()

    # ── UI construction ────────────────────────────────────────────

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("centralWidget")
        central.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Video background sits behind the shared React surfaces and ignores input.
        self._background = VideoBackground(central, opacity=BACKGROUND_OPACITY)
        self._background.setGeometry(central.rect())
        self._background.raise_()

        dev_url = os.environ.get("ANIMEVAULT_DEV_URL", "").strip()
        web_dist = Path(__file__).parent / "web" / "dist" / "index.html"
        if dev_url or web_dist.is_file():
            try:
                from animevault.ui.web_view import AnimeWebView, LibraryBridge
                self._web_view_class = AnimeWebView
                self._shared_bridge = LibraryBridge(self)
            except Exception:
                logger.exception("React toolbar bridge unavailable; using native toolbar")

        navbar = self._build_navbar()
        toolbar = self._build_toolbar()
        header = self._build_header()
        outer.addWidget(navbar)
        outer.addWidget(header)
        outer.addWidget(toolbar)

        # The single embedded React surface hosts both Library and Dashboard.
        self._stack = QStackedWidget()
        self._stack.setObjectName("mainStack")

        # Library page: poster grid; summary metrics live in the shared top header.
        library_page = QWidget()
        library_page.setObjectName("libraryPage")
        body = QHBoxLayout(library_page)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self._body = body
        self._grid = CardGrid()
        self._library_surface = QStackedWidget()
        self._library_surface.addWidget(self._grid)
        dev_url = os.environ.get("ANIMEVAULT_DEV_URL", "").strip()
        web_dist = Path(__file__).parent / "web" / "dist" / "index.html"
        if dev_url or web_dist.is_file():
            try:
                from animevault.ui.web_view import AnimeWebView
                self._web_view_class = AnimeWebView
                if self._shared_bridge is None:
                    from animevault.ui.web_view import LibraryBridge
                    self._shared_bridge = LibraryBridge(self)
                self._web_view = AnimeWebView(self, bridge=self._shared_bridge, surface="library")
                self._web_view.loadFinished.connect(self._apply_settings_to_library_web)
                self._library_surface.addWidget(self._web_view)
                self._library_surface.setCurrentWidget(self._web_view)
            except Exception:
                logger.exception("Glass library unavailable; using native card grid")
                self._web_view = None
        body.addWidget(self._library_surface, 1)

        self._stack.addWidget(library_page)  # page 0
        self._dashboard = None

        outer.addWidget(self._stack, 1)

        # Keep the animated background behind the content and size it with the window.
        self._background.lower()
        central.installEventFilter(self)
        # Overview has been removed from the visible library layout; its compact
        # summary values are now part of the shared header strip.

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        background = getattr(self, "_background", None)
        if background is not None:
            background.setGeometry(self.centralWidget().rect())

    def closeEvent(self, event) -> None:  # noqa: N802
        background = getattr(self, "_background", None)
        if background is not None:
            background.shutdown()
        super().closeEvent(event)

    def _build_header(self) -> QWidget:
        # Keep the host-owned AnimeVault brand/category/settings row.
        header = QWidget()
        header.setObjectName("headerBar")
        header.setFixedHeight(50)
        row = QHBoxLayout(header)
        row.setContentsMargins(18, 5, 18, 5)
        row.setSpacing(12)
        icon = QLabel("◐")
        icon.setObjectName("appIcon")
        row.addWidget(icon)
        title = RadialGradientLabel("AnimeVault")
        title.setObjectName("appTitle")
        row.addWidget(title)
        row.addSpacing(10)
        self._nav_buttons: dict[str, QPushButton] = {}
        for category in (MEDIA_ANIME, MEDIA_MANGA, MEDIA_MANHWA, MEDIA_MANHUA):
            button = QPushButton(CATEGORY_LABELS[category])
            button.setObjectName("navTab")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, c=category: self._on_category_changed(c))
            self._nav_buttons[category] = button
            row.addWidget(button)
        self._nav_buttons[self._category].setChecked(True)
        row.addStretch(1)
        settings = QPushButton("⚙")
        settings.setObjectName("settingsButton")
        settings.setFixedSize(38, 38)
        settings.setToolTip("Settings")
        settings.clicked.connect(self._show_settings_panel)
        row.addWidget(settings)
        return header

    def _build_toolbar(self) -> QWidget:
        # Native PySide6 Bubble toolbar; no duplicate legacy toolbar/search widgets.
        topbar = LiquidBubbleTopBar(
            tier_options=["All", *list(TIERS), "Unassigned"],
            status_options=["All", *list(VALID_STATUSES)],
            format_options=type_options(self._category),
            sort_options=SORT_OPTIONS,
            initial_category=self._category,
            parent=self,
        )
        self._topbar = topbar
        self._summary_kpis = topbar.summary_pills
        self._add_button = topbar.add_button
        self._search_field = topbar.search_field
        self._filter_combo = topbar.tier_combo
        self._status_combo = topbar.status_combo
        self._type_combo = topbar.format_combo
        self._sort_combo = topbar.sort_combo
        self._delete_button = topbar.delete_button
        self._retry_failed_button = topbar.retry_button
        self._select_button = None

        topbar.recommendations_requested.connect(self._show_recommendations)
        topbar.dashboard_requested.connect(self._show_dashboard)
        topbar.add_requested.connect(self._on_add)
        topbar.delete_requested.connect(self._on_delete_selected)
        topbar.fetch_missing_requested.connect(lambda: self._on_bulk_enrich(False))
        topbar.retry_failed_requested.connect(self._retry_failed_enrichment)

        topbar.help_action.connect(
            lambda action: self._show_about() if action == "about" else
            self._show_readme() if action == "open_readme" else None
        )
        topbar.upload_action.connect(
            lambda kind: self._on_import_xlsx() if kind == "xlsx" else
            self._on_import_csv() if kind == "csv" else
            self._on_import_sql() if kind == "sql" else None
        )
        topbar.export_action.connect(
            lambda kind: self._on_export(kind) if kind in {"csv", "xlsx", "ods", "sql"} else None
        )

        def handle_tool_action(action: str) -> None:
            # The dashboard has a dedicated signal to avoid opening twice.
            actions = {
                "fetch_missing": lambda: self._on_bulk_enrich(False),
                "refresh_all": lambda: self._on_bulk_enrich(True),
                "cloud_sync": self._on_cloud_sync,
            }
            callback = actions.get(action)
            if callback is not None:
                callback()
        topbar.tools_action.connect(handle_tool_action)

        topbar.search_changed.connect(self._on_search_changed)
        topbar.tier_changed.connect(self._on_filter_tier_changed)
        topbar.status_changed.connect(self._on_filter_status_changed)
        topbar.media_format_changed.connect(self._on_filter_type_changed)
        topbar.sort_changed.connect(
            lambda value: self._on_sort_changed(self._sort_combo.findData(value))
        )
        topbar.set_category(self._category)
        return topbar

    def _build_navbar(self) -> QWidget:
        # Category navigation is owned by the existing native MainWindow header.
        placeholder = QWidget()
        placeholder.setFixedHeight(0)
        return placeholder

    def _set_menu_bar_height(self, height: int) -> None:
        if self._menu_web_view is not None:
            self._menu_web_view.setFixedHeight(max(60, min(560, int(height))))

    def _build_native_toolbar(self) -> QWidget:
        toolbar = QWidget()
        toolbar.setObjectName("toolBar")
        toolbar.setFixedHeight(44)
        row = QHBoxLayout(toolbar)
        row.setContentsMargins(18, 5, 18, 5)
        row.setSpacing(6)

        tools_btn = QPushButton("Tools")
        tools_btn.setObjectName("toolButton")
        tools_menu = QMenu(tools_btn)
        dashboard_action = tools_menu.addAction("Library Dashboard")
        fetch_missing = tools_menu.addAction("Fetch Missing Data")
        refresh_all = tools_menu.addAction("Refresh Anime Data")
        tools_menu.addSeparator()
        cloud_sync = tools_menu.addAction("Cloud Sync…")
        tools_btn.setMenu(tools_menu)
        row.addWidget(tools_btn)

        rec_btn = HoverLiftButton("🎯 Recommendations")
        rec_btn.setObjectName("primaryButton")
        rec_btn.setToolTip("Open the recommendations panel")
        rec_btn.clicked.connect(self._show_recommendations)
        row.addWidget(rec_btn)

        help_btn = QPushButton("Help")
        help_btn.setObjectName("toolButton")
        help_menu = QMenu(help_btn)
        about = help_menu.addAction("About AnimeVault")
        doc_action = help_menu.addAction("Documentation (README)")
        help_btn.setMenu(help_menu)
        row.addWidget(help_btn)

        row.addSpacing(14)

        upload_btn = QPushButton("⇧  Upload")
        upload_btn.setObjectName("toolButton")
        upload_menu = QMenu(upload_btn)
        upload_xlsx = upload_menu.addAction("Import Excel (.xlsx)…")
        upload_csv = upload_menu.addAction("Import CSV (.csv)…")
        upload_sql = upload_menu.addAction("Import SQL Dump (.sql)…")
        upload_btn.setMenu(upload_menu)
        row.addWidget(upload_btn)

        export_btn = QPushButton("⤓  Export")
        export_btn.setObjectName("toolButton")
        export_menu = QMenu(export_btn)
        export_csv_btn = export_menu.addAction("Export to CSV…")
        export_xlsx_btn = export_menu.addAction("Export to Excel (.xlsx)…")
        export_ods_btn = export_menu.addAction("Export to OpenDocument (.ods)…")
        export_sql_btn = export_menu.addAction("Export to SQL Dump…")
        export_btn.setMenu(export_menu)
        row.addWidget(export_btn)

        self._delete_button = QPushButton("🗑  Delete")
        self._delete_button.setObjectName("dangerButton")
        self._delete_button.setEnabled(False)
        self._delete_button.clicked.connect(self._on_delete_selected)
        row.addWidget(self._delete_button)

        self._select_button = QPushButton("✓  Select")
        self._select_button.setObjectName("toolButton")
        self._select_button.setCheckable(True)
        self._select_button.toggled.connect(self._on_select_toggled)
        row.addWidget(self._select_button)

        fetch_btn = QPushButton("⟳  Fetch Missing Data")
        fetch_btn.setObjectName("toolButton")
        fetch_btn.clicked.connect(lambda: self._on_bulk_enrich(False))
        row.addWidget(fetch_btn)

        self._retry_failed_button = QPushButton("↻  Retry Failed")
        self._retry_failed_button.setObjectName("toolButton")
        self._retry_failed_button.setEnabled(False)
        self._retry_failed_button.clicked.connect(self._retry_failed_enrichment)
        row.addWidget(self._retry_failed_button)

        row.addStretch()

        # Note: File menu items (Import/Export/Backup/Quit) were removed per
        # user requirements. Tools, Help, Recommendations, Upload, Export,
        # Delete, Select, Fetch Missing Data, Retry Failed are the remaining
        # toolbar controls (defined above).

        return toolbar

    def _build_search_row(self) -> QWidget:
        # Search and filters are integrated into LiquidBubbleTopBar.
        placeholder = QWidget()
        placeholder.setFixedHeight(0)
        return placeholder

    def _populate_tier_filter(self) -> None:
        """Fill the tier filter with SSS→F plus Unassigned (never alphabetical)."""
        current = self._filter_combo.currentText()
        self._filter_combo.blockSignals(True)
        self._filter_combo.clear()
        self._filter_combo.addItem("All")
        for tier in TIERS:
            self._filter_combo.addItem(tier)
        self._filter_combo.addItem("Unassigned")
        index = self._filter_combo.findText(current)
        self._filter_combo.setCurrentIndex(max(0, index))
        self._filter_combo.blockSignals(False)

    def _populate_type_filter(self) -> None:
        """Type options depend on the active category.

        Always resets the selection to "All" — a leftover filter from the
        previous tab would otherwise hide every record on the new one.
        """
        self._type_combo.blockSignals(True)
        self._type_combo.clear()
        self._type_combo.addItems(type_options(self._category))
        self._type_combo.setCurrentIndex(0)
        self._filter_type = "All"
        self._type_combo.blockSignals(False)

    def _build_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+K"), self, activated=self._focus_search)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self._focus_search)

    # ── Card wiring ────────────────────────────────────────────────

    def _apply_cards(self, cards: list) -> None:
        if self._web_view is not None:
            # The sorted/filtered models come from Python; React is display-only.
            self._web_view.bridge.replace_library([card.item for card in cards])
            self._delete_button.setEnabled(bool(self._web_selected))
            return
        for card in cards:
            card.details_requested.connect(self._on_details)
            card.edit_requested.connect(self._on_edit)
            card.refresh_requested.connect(self._on_refresh_one)
            card.deleted.connect(self._on_delete_one)
            card.selection_changed.connect(self._on_card_selected)
            card.set_select_mode(self._select_mode)
        self._grid.set_cards(cards)

    def _on_web_selection_mode_changed(self, enabled: bool) -> None:
        self._select_mode = bool(enabled)
        button = getattr(self, "_select_button", None)
        if button is not None:
            previous = button.blockSignals(True)
            button.setChecked(self._select_mode)
            button.setText("✓  Selecting" if self._select_mode else "✓  Select")
            button.blockSignals(previous)
        for card in getattr(self._grid, "cards", []):
            card.set_select_mode(self._select_mode)

    def _on_web_selection_changed(self, selected: list) -> None:
        self._web_selected = list(selected)
        self._delete_button.setEnabled(bool(self._web_selected))

    def _on_card_selected(self, _item, _selected) -> None:
        """Enable the toolbar Delete button once anything is selected."""
        self._delete_button.setEnabled(
            any(c.is_selected() for c in self._grid.cards)
        )

    # ── State changes ──────────────────────────────────────────────

    def _on_category_changed(self, category: str) -> None:
        if category == self._category:
            return
        self._category = category
        for cat, button in self._nav_buttons.items():
            button.setChecked(cat == category)
        self._search_field.setPlaceholderText(
            f"Search {CATEGORY_LABELS[category]}..."
        )
        self._add_button.setText(f"＋  Add {CATEGORY_LABELS[category]}")
        if getattr(self, "_topbar", None) is not None:
            self._topbar.set_category(category)
            self._topbar.set_filter_options(media_format=type_options(category))
        self._populate_type_filter()
        if self._shared_bridge is not None:
            self._shared_bridge.categoryChanged.emit(category)
        self.refresh()

    def _on_search_changed(self, text: str) -> None:
        self._search_text = text
        self.refresh()

    def _on_filter_tier_changed(self, text: str) -> None:
        self._filter_tier = "all" if text == "All" else text
        self.refresh()

    def _on_filter_status_changed(self, text: str) -> None:
        self._filter_status = text
        self.refresh()

    def _on_filter_type_changed(self, text: str) -> None:
        self._filter_type = text
        self.refresh()

    def _on_sort_changed(self, index: int) -> None:
        self._sort_mode = self._sort_combo.itemData(index) or "title"
        self.refresh()

    def _focus_search(self) -> None:
        self._search_field.setFocus()
        self._search_field.selectAll()

    def _on_select_toggled(self, enabled: bool) -> None:
        self._select_mode = enabled
        if self._web_view is not None:
            self._web_selected = []
            self._web_view.bridge.setSelectionMode(enabled)
            self._delete_button.setEnabled(False)
            if self._select_button is not None:
                self._select_button.setText("✓  Selecting" if enabled else "✓  Select")
            return
        for card in self._grid.cards:
            card.set_select_mode(enabled)
            if not enabled:
                card.set_selected(False)
        self._delete_button.setEnabled(
            enabled and any(c.is_selected() for c in self._grid.cards)
        )
        if self._select_button is not None:
            self._select_button.setText("✓  Selecting" if enabled else "✓  Select")

    # ── Data loading ───────────────────────────────────────────────

    def _load_items(self) -> tuple[list, list]:
        """Return (items for current category, all anime, all literature)."""
        animes = Anime.all()
        literature = Literature.all()

        if self._category == MEDIA_ANIME:
            items: list = list(animes)
        else:
            items = [
                item for item in literature if item.category == self._category
            ]

        query = self._search_text.strip().casefold()
        if query:
            items = [
                i for i in items
                if query in i.title.casefold()
                or query in (getattr(i, "title_ja", "") or "").casefold()
                or query in (getattr(i, "title_native", "") or "").casefold()
            ]

        if self._filter_status != "All":
            items = [i for i in items if i.status == self._filter_status]

        if self._filter_tier != "all":
            if self._filter_tier == "Unassigned":
                items = [i for i in items if not i.tier]
            else:
                items = [i for i in items if i.tier == self._filter_tier]

        if self._filter_type != "All":
            wanted = self._filter_type
            if self._category == MEDIA_ANIME:
                items = [
                    i for i in items
                    if (getattr(i, "media_type", "") or "").upper() == wanted.upper()
                ]
            else:
                items = [
                    i for i in items
                    if (getattr(i, "format", "") or "").upper() == wanted.upper()
                    or getattr(i, "category", "") == wanted.lower()
                ]

        items = self._sort_items(items)
        return items, animes, literature

    def _sort_items(self, items: list) -> list:
        from animevault.tiers import tier_sort_key

        mode = self._sort_mode
        if mode == "tier":
            return sorted(items, key=lambda i: (tier_sort_key(i.tier), i.title.casefold()))
        if mode == "title_desc":
            return sorted(items, key=lambda i: i.title.casefold(), reverse=True)
        if mode == "added":
            return sorted(items, key=lambda i: -(i.id or 0))
        if mode == "updated":
            return sorted(items, key=lambda i: (i.metadata_fetched_at or ""), reverse=True)
        if mode == "year":
            return sorted(
                items,
                key=lambda i: (
                    -(getattr(i, "season_year", None) or 0),
                    i.title.casefold(),
                ),
            )
        if mode == "progress":
            def _progress(i):
                total = getattr(i, "episodes", None) or getattr(i, "chapters", 0)
                watched = getattr(i, "episodes_watched", None)
                if watched is None:
                    watched = getattr(i, "chapters_read", 0)
                return (-((watched or 0) / total if total else 0), i.title.casefold())
            return sorted(items, key=_progress)
        if mode == "episodes":
            def _count(i):
                total = getattr(i, "episodes", None)
                if total is None:
                    total = getattr(i, "chapters", 0)
                return (-(total or 0), i.title.casefold())
            return sorted(items, key=_count)
        return sorted(items, key=lambda i: i.title.casefold())

    def refresh(self) -> None:
        """Reload library data, update header summaries, and refresh analytics."""
        items, animes, literature = self._load_items()

        if self._web_view is not None:
            self._web_view.bridge.replace_library(items)
            self._delete_button.setEnabled(bool(self._web_selected))
        else:
            if self._category == MEDIA_ANIME:
                cards = [anime_card(i) for i in items]
            else:
                cards = [literature_card(i) for i in items]
            self._apply_cards(cards)
        self._update_header_summary(animes, literature)

        if self._dashboard is not None:
            self._dashboard.refresh(animes, literature)

    def _update_header_summary(self, animes, literature) -> None:
        # Populate KPI values from real model records on every refresh.
        statuses = Counter(str(getattr(item, "status", "") or "").casefold() for item in animes)
        counts = Counter(str(getattr(item, "category", "") or "").casefold() for item in literature)
        values = {
            "anime_total": len(animes),
            "anime_watching": statuses["watching"],
            "anime_completed": statuses["completed"],
            "anime_planned": statuses["plan_to_watch"],
            "manga_total": counts[MEDIA_MANGA],
            "manhwa_total": counts[MEDIA_MANHWA],
            "manhua_total": counts[MEDIA_MANHUA],
        }
        if getattr(self, "_topbar", None) is not None:
            self._topbar.set_summary(values)

    def _on_add(self) -> None:
        dialog = AddMediaDialog(self._category, self)
        if dialog.exec() == AddMediaDialog.DialogCode.Accepted:
            self.library_changed.emit()

    def _on_details(self, item) -> None:
        DetailsDialog(item, self).exec()

    def _on_edit(self, item) -> None:
        dialog = AddMediaDialog(self._category, self, existing=item)
        if dialog.exec() == AddMediaDialog.DialogCode.Accepted:
            self.library_changed.emit()

    def _on_refresh_one(self, item) -> None:
        self.library_changed.emit()

    # ── Delete ─────────────────────────────────────────────────────

    def _on_delete_one(self, item) -> None:
        name = item.title
        confirm = self._settings.value("library/confirm_delete", True, type=bool)
        if confirm:
            reply = QMessageBox.question(
                self,
                "Delete",
                f'Delete "{name}"?\n\nThis will remove it from your library.',
                QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
                QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        item.delete()
        self.library_changed.emit()

    def _on_delete_selected(self) -> None:
        selected = self._web_selected if self._web_view is not None else [c for c in self._grid.cards if c.is_selected()]
        if not selected:
            return
        selected_items = [item if self._web_view is not None else item.item for item in selected]
        names = "\n".join(f"• {item.title}" for item in selected_items[:10])
        if len(selected_items) > 10:
            names += f"\n… and {len(selected_items) - 10} more"
        confirm = self._settings.value("library/confirm_delete", True, type=bool)
        if confirm:
            reply = QMessageBox.question(
                self,
                "Delete",
                f"Delete {len(selected)} item(s)?\n\n{names}\n\n"
                "This will remove them from your library.",
                QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
                QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        for item in selected_items:
            item.delete()
        self._on_select_toggled(False)
        self.library_changed.emit()

    def _toggle_card_selection(self, card) -> None:
        if not self._select_mode:
            return
        card.set_selected(not card.is_selected())
        self._delete_button.setEnabled(
            any(c.is_selected() for c in self._grid.cards)
        )

    def _toggle_selection_mode(self) -> None:
        # Selection mode remains available to existing card/bridge workflows,
        # but there is deliberately no visible Select control in this toolbar.
        self._select_mode = not self._select_mode
        if self._web_view is not None:
            self._web_view.bridge.setSelectionMode(self._select_mode)
            self._delete_button.setEnabled(False)
        else:
            self._on_select_toggled(self._select_mode)

    def _on_import_xlsx(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Excel", "", "Excel Files (*.xlsx)"
        )
        if path:
            self._run_xlsx_import(path)

    def _on_import_sql(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import SQL Dump", "", "SQL Files (*.sql);;All Files (*)"
        )
        if path:
            self._run_sql_import(path)

    def _on_import_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import CSV",
            "",
            "CSV Files (*.csv *.txt);;All Files (*)",
        )
        if path:
            self._run_csv_import(path)

    # ── Export ─────────────────────────────────────────────────────

    def _on_export(self, fmt: str) -> None:
        """Export the library to CSV, XLSX, ODS or a SQL dump."""
        from animevault.services.importers.exporter import export_library

        filters = {
            "csv": "CSV Files (*.csv)",
            "xlsx": "Excel Files (*.xlsx)",
            "ods": "OpenDocument Files (*.ods)",
            "sql": "SQL Files (*.sql)",
        }
        default_ext = {"csv": "csv", "xlsx": "xlsx", "ods": "ods", "sql": "sql"}[fmt]
        suggested = str(Path.home() / f"animevault-export.{default_ext}")

        path, _ = QFileDialog.getSaveFileName(
            self,
            f"Export to {fmt.upper()}",
            suggested,
            filters.get(fmt, "All Files (*)"),
        )
        if not path:
            return

        # Ensure the extension matches the chosen format.
        if not path.lower().endswith(f".{default_ext}"):
            path = f"{path}.{default_ext}"

        try:
            result = export_library(path, fmt=fmt)
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return

        QMessageBox.information(
            self,
            "Export complete",
            f"Exported {result.row_count} record(s) to:\n{result.path}",
        )

    def _run_csv_import(self, path: str) -> None:
        from animevault.ui.import_dialogs import run_csv_import_flow

        run_csv_import_flow(self, path, on_done=self.library_changed.emit)

    def _run_xlsx_import(self, path: str) -> None:
        from animevault.ui.import_dialogs import run_xlsx_import_flow

        run_xlsx_import_flow(self, path, on_done=self.library_changed.emit)

    def _run_sql_import(self, path: str) -> None:
        from animevault.ui.import_dialogs import run_sql_import_flow

        run_sql_import_flow(self, path, on_done=self.library_changed.emit)

    def _on_cloud_sync(self) -> None:
        """Open the optional Google account / cloud sync dialog."""
        from animevault.ui.account_dialog import AccountDialog

        AccountDialog(self).exec()

    def _on_backup(self) -> None:
        from animevault.migration import backup_database

        path = backup_database()
        if path is None:
            QMessageBox.information(self, "Backup", "No database file to back up yet.")
        else:
            QMessageBox.information(self, "Backup", f"Database backed up to:\n{path}")

    # ── Bulk enrichment ────────────────────────────────────────────

    def _on_bulk_enrich(self, refresh_all: bool, items: list | None = None) -> None:
        from animevault.services.workers import BulkEnrichmentWorker

        if items is None:
            animes = Anime.all()
            literature = Literature.all()
            items = animes + literature
        if not items:
            QMessageBox.information(self, "Empty Library", "There is nothing to enrich.")
            return

        title_mode = "Refreshing All Data" if refresh_all else "Fetching Missing Data"
        self._progress_dialog = QProgressDialog(
            "Initializing fetcher...", "Cancel", 0, len(items), self
        )
        self._progress_dialog.setWindowTitle(title_mode)
        self._progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress_dialog.setMinimumDuration(200)

        from animevault.services.import_tree import ImportTree

        checkpoint = ImportTree.JOBS_DIR / "latest.json"
        self._bulk_worker = BulkEnrichmentWorker(
            items,
            refresh_all=refresh_all,
            parent=self,
            checkpoint_path=checkpoint,
            resume_from=checkpoint if not refresh_all else None,
        )
        self._progress_dialog.canceled.connect(self._bulk_worker.cancel)
        self._bulk_worker.progress.connect(self._on_bulk_progress)
        self._bulk_worker.enrichment_finished.connect(self._on_bulk_finished)
        self._bulk_worker.poster_ready.connect(self._on_poster_ready)
        self._bulk_worker.start()

    def _on_bulk_progress(self, current, total, message, stats) -> None:
        if self._progress_dialog:
            self._progress_dialog.setValue(current)
            self._progress_dialog.setLabelText(
                f"{message}\n\nProgress: {current} / {total}\n"
                f"Updated: {stats.get('updated', 0)} | "
                f"Metadata: {stats.get('metadata_completed', 0)} | "
                f"Posters: {stats.get('poster_completed', 0)} "
                f"(failed {stats.get('poster_failed', 0)}) | "
                f"Cache hits: {stats.get('cached', 0)} | "
                f"Already complete: {stats.get('skipped_complete', 0)} | "
                f"Metadata failed: {stats.get('failed', 0)} | "
                f"No match: {stats.get('not_found', 0)}"
            )

    def _on_poster_ready(self, item_id: int, path: str) -> None:
        """Update visible cards when the existing poster worker completes."""
        if self._web_view is not None:
            self._web_view.bridge.update_poster(item_id, path)
            return
        for card in self._grid.cards:
            item = getattr(card, "item", None)
            if getattr(item, "id", None) != item_id:
                continue
            if isinstance(item, Literature):
                item.cover_path = path
            else:
                item.poster_path = path
            card.refresh_art(path)

    def _on_bulk_finished(self, stats) -> None:
        if self._progress_dialog:
            self._progress_dialog.close()
        self.library_changed.emit()
        self._last_enrichment_stats = dict(stats)
        failure_details = list(stats.get("failure_details", []))
        failed_ids = {
            row.get("item_id") for row in failure_details if row.get("item_id") is not None
        }
        all_items = Anime.all() + Literature.all()
        self._failed_items = [item for item in all_items if getattr(item, "id", None) in failed_ids]
        self._retry_failed_button.setEnabled(bool(self._failed_items))
        if self._shared_bridge is not None:
            self._shared_bridge.retryAvailableChanged.emit(bool(self._failed_items))

        summary = (
            f"Total records: {stats.get('total', 0)}  |  Unique titles: {stats.get('unique_titles', 0)}  |  Tasks: {stats.get('total_tasks', 0)}\n"
            f"Metadata updated: {stats.get('updated', 0)}  |  Cache hits: {stats.get('cached', 0)}\n"
            f"Already complete/skipped: {stats.get('skipped_complete', 0)}\n"
            f"Posters downloaded: {stats.get('poster_completed', 0)}  |  Poster failures: {stats.get('poster_failed', 0)}\n"
            f"Metadata failures: {stats.get('failed', 0)}  |  No reliable title match: {stats.get('not_found', 0)}  |  Permanently unresolved: {stats.get('permanently_unresolved', 0)}\n"
            f"Discovery: {stats.get('no_candidate_found', 0)} no candidates, {stats.get('low_confidence_candidates', 0)} low confidence, {stats.get('ambiguous_candidates', 0)} ambiguous, {stats.get('provider_unavailable', 0)} unavailable, {stats.get('provider_rate_limited', 0)} rate limited\n"
            f"Retries: {stats.get('retry_attempts', 0)}  |  Cancelled: {stats.get('cancelled', 0)}"
        )
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Enrichment Summary")
        dialog.setText(summary)
        dialog.addButton("Close", QMessageBox.ButtonRole.RejectRole)
        export_button = None
        retry_button = None
        if failure_details:
            export_button = dialog.addButton("Export Failure Report…", QMessageBox.ButtonRole.ActionRole)
        if self._failed_items:
            retry_button = dialog.addButton("Retry Failed", QMessageBox.ButtonRole.ActionRole)
        dialog.exec()
        clicked = dialog.clickedButton()
        if clicked is export_button and export_button is not None:
            self._export_enrichment_report()
        elif clicked is retry_button and retry_button is not None:
            self._retry_failed_enrichment()

    def _retry_failed_enrichment(self) -> None:
        if not self._failed_items or self._bulk_worker is not None and self._bulk_worker.isRunning():
            return
        retry_items = list(self._failed_items)
        self._failed_items = []
        self._retry_failed_button.setEnabled(False)
        if self._shared_bridge is not None:
            self._shared_bridge.retryAvailableChanged.emit(False)
        self._on_bulk_enrich(False, items=retry_items)

    def _export_enrichment_report(self) -> None:
        import csv
        import json

        rows = list(self._last_enrichment_stats.get("failure_details", []))
        if not rows:
            QMessageBox.information(self, "Failure Report", "There are no failed tasks to export.")
            return
        path, selected = QFileDialog.getSaveFileName(
            self,
            "Export Enrichment Failure Report",
            "enrichment-failures.json",
            "JSON (*.json);;CSV (*.csv)",
        )
        if not path:
            return
        target = Path(path)
        if not target.suffix:
            target = target.with_suffix(".csv" if "CSV" in selected else ".json")
        try:
            if target.suffix.lower() == ".csv":
                columns = list(rows[0])
                with target.open("w", newline="", encoding="utf-8-sig") as handle:
                    writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
                    writer.writeheader()
                    writer.writerows(rows)
            else:
                target.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Failure Report", f"Could not write the report:\n{exc}")
        else:
            QMessageBox.information(self, "Failure Report", f"Report saved to:\n{target}")


    # ── Menus / dialogs ────────────────────────────────────────────

    def _show_about(self) -> None:
        from animevault import __version__

        QMessageBox.about(
            self,
            "About AnimeVault",
            f"<b>AnimeVault</b> v{__version__}<br>"
            "Anime, Manga, Manhwa and Manhua library manager with "
            "multi-provider metadata enrichment.<br><br>"
            "Built with PySide6 and SQLite.",
        )

    def _show_readme(self) -> None:
        """Open the README.md documentation in a web view rendered as GitHub-flavored markdown."""
        from html import escape

        readme_path = Path(__file__).parent.parent.parent.parent / "README.md"
        if not readme_path.is_file():
            readme_path = Path.cwd() / "README.md"

        if not readme_path.is_file():
            QMessageBox.critical(self, "Documentation", f"README.md not found at: {readme_path}")
            return

        # Convert README.md to HTML with GitHub-flavored markdown styling
        markdown_content = readme_path.read_text(encoding="utf-8")
        html_content = markdown.markdown(markdown_content, extensions=["gfm"])

        # Self-contained HTML document with GitHub-style markdown rendering
        doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>README - AnimeVault</title>
<style>
  :root {{
    color-scheme: light dark;
  }}
  * {{
    box-sizing: border-box;
  }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    color: #24292f;
    background: #fff;
    margin: 0;
    padding: 2rem 1rem;
    line-height: 1.6;
  }}
  h1 {{
    font-size: 2em;
    border-bottom: 1px solid #eaecef;
    padding-bottom: 0.3em;
  }}
  h2 {{
    font-size: 1.5em;
    border-bottom: 1px solid #eaecef;
    padding-bottom: 0.3em;
  }}
  h3 {{
    font-size: 1.25em;
  }}
  a {{
    color: #0366d6;
    text-decoration: none;
  }}
  a:hover {{
    text-decoration: underline;
  }}
  code {{
    background: #f6f8fa;
    border-radius: 3px;
    font-family: "SF Mono", "Consolas", "Liberation Mono", Menlo, monospace;
    font-size: 85%;
  }}
  pre {{
    background: #282c34;
    color: #abb2bf;
    border-radius: 6px;
    padding: 0.75rem 1rem;
  }}
  pre code {{
    background: none;
    color: inherit;
    font-size: 100%;
    padding: 0;
  }}
  blockquote {{
    border-left: 4px solid #dfe2e5;
    padding: 0 1rem;
    color: #6a737d;
    margin: 0;
  }}
  ul, ol {{
    padding-left: 2em;
  }}
  li {{
    margin-bottom: 0.25em;
  }}
  hr {{
    border: 0;
    border-top: 1px solid #eaecef;
  }}
  table {{
    border-collapse: collapse;
    width: 100%;
    margin: 1rem 0;
  }}
  th, td {{
    border: 1px solid #dfe2e5;
    padding: 0.5rem 0.75rem;
    text-align: left;
  }}
  th {{
    background: #f6f8fa;
    font-weight: 600;
  }}
  img {{
    max-width: 100%;
    border-radius: 6px;
  }}
  .markdown-body {{
    max-width: 800px;
    margin: 0 auto;
  }}
  .scrollable {{
    max-height: 600px;
    overflow-y: auto;
  }}
</style>
</head>
<body>
<div class="markdown-body">
{html_content}
</div>
</body>
</html>"""
        # Use a plain QWebEngineView to display the documentation
        doc_view = QWebEngineView(self)
        doc_view.setHtml(doc)
        doc_view.page().setBackgroundColor(QColor(0, 0, 0, 0))
        doc_view.setStyleSheet("background: transparent;")

        dialog = QDialog(self)
        dialog.setObjectName("readmeDialog")
        dialog.setWindowTitle("README - AnimeVault")
        dialog.resize(900, 700)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(doc_view)
        dialog.exec()

# (theme-change callbacks were retired with the 26-theme system)

    def _on_effects_changed(self, reduced: bool) -> None:
        from animevault.ui.theme import liquid_glass, set_reduce_effects

        set_reduce_effects(reduced)
        self._background.set_effects_reduced(reduced)
        for scroll_area in self.findChildren(ScrollRevealArea):
            scroll_area.set_effects_reduced(reduced)
        for card in self.findChildren(MediaCard):
            card.set_effects_reduced(reduced)
        self._set_liquid_glass(liquid_glass())

    def _set_liquid_glass(self, enabled: bool) -> None:
        if enabled:
            self.centralWidget().setProperty("class", "liquid-glass-enabled")
        else:
            self.centralWidget().setProperty("class", "")
        self.centralWidget().style().unpolish(self.centralWidget())
        self.centralWidget().style().polish(self.centralWidget())

    def _on_liquid_glass_changed(self, enabled: bool) -> None:
        self._set_liquid_glass(enabled)

    def _show_dashboard(self) -> None:
        """Open the React dashboard rendered from the Python model bridge."""
        if self._web_view is None:
            QMessageBox.warning(self, "Dashboard", "The React dashboard requires the embedded WebEngine library surface.")
            return
        try:
            self._stack.setCurrentIndex(0)
            self._web_view.page().runJavaScript("window.dispatchEvent(new Event('animevault:dashboard'))")
        except Exception as e:
            logger.exception("Failed to show dashboard: %s", e)
            QMessageBox.critical(self, "Dashboard Error", f"Failed to show dashboard: {e}")

    def _show_library(self) -> None:
        """Return to the React library and refresh its current query."""
        try:
            self._stack.setCurrentIndex(0)
            if self._web_view is not None:
                self._web_view.page().runJavaScript("window.dispatchEvent(new Event('animevault:library'))")
            self.refresh()
        except Exception as e:
            logger.exception("Failed to show library: %s", e)

    def _refresh_dashboard(self) -> None:
        """Request fresh data through the React/Python dashboard bridge."""
        if self._web_view is not None:
            self._web_view.bridge.dashboardChanged.emit()

    def _on_settings_changed(self, settings_json: str) -> None:
        """Handle settings change from the React settings UI."""
        try:
            settings = json.loads(settings_json)
            self._settings_panel.save_settings(settings)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Invalid settings JSON: %s", exc)

    def _on_settings_applied(self, settings_json: str) -> None:
        """Handle settings apply from the React settings UI."""
        try:
            settings = json.loads(settings_json)
            self._settings_panel.save_settings(settings)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Invalid settings JSON: %s", exc)

    def _on_settings_action(self, action_id: str) -> None:
        """Handle a settings action button click."""
        logger.info("Settings action from UI: %s", action_id)
        if action_id == "data.backupNow":
            self._on_backup()
        elif action_id == "data.clearCache":
            self._on_clear_cache()
        elif action_id == "about.update":
            self._on_check_for_updates()
        elif action_id == "about.licenses":
            self._on_view_licenses()

    def _show_settings_panel(self) -> None:
        """Open the LiquidGlass settings panel as a dialog."""
        from animevault.services.backup_service import backup_database
        from animevault.services.cache_service import CacheService
        from animevault.services.notification_service import NotificationService
        from animevault.services.update_service import UpdateService, view_licenses
        from animevault.ui.settings_service import SettingsService, Settings
        from animevault.ui.settings_panel import SettingsPanel

        panel = SettingsPanel(self)
        self._settings_panel = panel

        settings = Settings()
        self._settings_service = SettingsService()

        dialog = QDialog(self)
        dialog.setObjectName("settingsPanelDialog")
        dialog.setWindowTitle("Settings")
        dialog.resize(960, 700)

        # React web view for the LiquidGlass settings UI
        from animevault.ui.web_view import AnimeWebView

        self._settings_view = AnimeWebView(self, bridge=panel.bridge, surface="settings")
        self._settings_view.setObjectName("settingsGlassView")
        self._settings_view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        panel.bridge.closeRequested.connect(dialog.reject)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._settings_view)

        # Settings are applied by the React surface after the Python bridge confirms success.
        # Keep a native Close button as a fallback if the web surface is unavailable.
        action_bar = QHBoxLayout()
        action_bar.setContentsMargins(8, 8, 8, 8)
        close_btn = QPushButton("Close")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setMinimumWidth(100)
        close_btn.clicked.connect(dialog.reject)
        action_bar.addStretch(1)
        action_bar.addWidget(close_btn)
        layout.addLayout(action_bar)

        dialog.exec()

    def _on_clear_cache(self) -> None:
        """Handle cache clearing."""
        count = self._settings_panel.clear_cache()
        self.statusMessage(f"Cache cleared ({count} files removed)")
        self._show_status_notification(f"Cache cleared ({count} files removed)")

    def _on_check_for_updates(self) -> None:
        """Check for updates."""
        has_update, version = self._settings_panel.check_for_updates()
        if has_update:
            self.statusMessage(f"Update available: {version}")
            self._show_status_notification(f"Update available: {version}")
        else:
            self.statusMessage("You are on the latest version")
            self._show_status_notification("You are on the latest version")

    def _on_view_licenses(self) -> None:
        """Display open-source licenses."""
        self._settings_panel.view_licenses()
        self.statusMessage("Licenses dialog displayed")

    def _show_status_notification(self, message: str, level: str = "info") -> None:
        """Show a status message to the user."""
        if self.parent() is not None:
            self.parent().statusMessage(message, level)

    def statusMessage(self, message: str, level: str = "info") -> None:
        """Placeholder for status message display."""
        # In a real app, this would update a status bar widget
        logger.info("[%s] %s", level.upper(), message)

    def _show_recommendations(self) -> None:
        """Show one reusable, independent Recommendations window."""
        from animevault.ui.recommendations_window import open_recommendations

        window = getattr(self, "_recommendation_window", None)
        if window is not None:
            try:
                if window.isVisible():
                    window.show()
                    window.raise_()
                    window.activateWindow()
                    return
            except RuntimeError:
                self._recommendation_window = None

        # Build a library provider (a zero-argument callable returning the items).
        try:
            from animevault.models.anime import Anime
            from animevault.models.literature import Literature
            def library_provider():
                return list(Anime.all()) + list(Literature.all())
        except Exception:
            library_provider = lambda: []

        # Use the app's state directory for persisted pool/feedback.
        from animevault.app import get_app
        state_dir = getattr(get_app(), "state_dir", None) or Path.home() / ".animevault" / "recommendation_state"
        open_recommendations(self, library_provider, state_dir)

    # ── Settings application (Liquid Glass) ───────────────────────────────

    def set_appearance(
        self,
        *,
        theme_id: str,
        accent: str,
        secondary: str,
        bg: str,
        surface: str,
        text: str,
        glass: int,
        animations: bool,
        reduce: bool,
    ) -> None:
        """Apply appearance settings to the running application."""
        from animevault.ui.theme import application_stylesheet_for_preferences

        # Persist appearance preferences to QSettings.
        self._settings.setValue("appearance/reduce_effects", reduce)
        self._settings.setValue("appearance/liquid_glass", glass > 0 and not reduce)
        self._settings.setValue("appearance/theme_id", theme_id)
        self._settings.setValue("appearance/glass", glass)
        self._settings.sync()

        colors = {"accent": accent, "secondary": secondary, "bg": bg,
                  "surface": surface, "text": text}
        self._appearance_preferences = {
            "themeId": theme_id, "colors": colors, "glass": glass,
            "animations": animations, "reduce": reduce,
        }
        self.setStyleSheet(application_stylesheet_for_preferences(colors))

        # Update native widgets (background, scroll areas, cards) so the
        # reduced-effects preference is honoured across the desktop UI.
        self._background.set_effects_reduced(reduce)
        for scroll in self.findChildren(QScrollArea):
            from animevault.ui.scroll_animation import ScrollRevealArea
            if isinstance(scroll, ScrollRevealArea):
                scroll.set_effects_reduced(reduce)
        for card in self.findChildren(MediaCard):
            card.set_effects_reduced(reduce)

        # Keep the desktop chrome and the main embedded surface in sync.
        self._set_liquid_glass(glass > 0 and not reduce)
        self._apply_settings_to_library_web()

    def set_library_defaults(
        self,
        *,
        view: str,
        show_progress: bool,
        confirm_delete: bool,
        auto_complete: bool,
    ) -> None:
        """Apply library display preferences."""
        self._settings.setValue("library/view", view)
        self._settings.setValue("library/progress", show_progress)
        self._settings.setValue("library/confirm_delete", confirm_delete)
        self._settings.setValue("library/auto_complete", auto_complete)
        self._settings.sync()
        self._library_preferences = {
            "view": view,
            "progress": bool(show_progress),
            "confirmDelete": bool(confirm_delete),
            "autoComplete": bool(auto_complete),
        }
        self._apply_settings_to_library_web()

    def _apply_settings_to_library_web(self, *_args) -> None:
        """Push committed appearance and library preferences into the React view."""
        if self._web_view is None:
            return
        appearance = self._appearance_preferences
        colors = appearance.get("colors", {})
        reduce = bool(appearance.get("reduce", False))
        glass = max(0, min(100, int(appearance.get("glass", 70))))
        blur = "blur(0px) saturate(100%) brightness(1)" if reduce else f"blur({glass * 0.16:g}px) saturate(175%) brightness(1.06)"
        payload = json.dumps({"appearance": appearance, "library": self._library_preferences})
        script = f"""(() => {{
          const s = {payload};
          window.AV_settings = s;
          const root = document.documentElement;
          const c = s.appearance.colors || {{}};
          const set = (name, value) => value && root.style.setProperty(name, value);
          set('--av-accent', c.accent || '#a3eee2');
          set('--av-secondary', c.secondary || '#c7b6ff');
          set('--av-bg', c.bg || '#0a0c10');
          set('--av-surface', c.surface || '#121722');
          set('--av-text', c.text || '#f4f6fb');
          set('--lg-teal', c.accent || '#a3eee2');
          set('--lg-text', c.text || '#f4f6fb');
          set('--lg-blur', {json.dumps(blur)});
          root.classList.toggle('av-reduce-effects', !!s.appearance.reduce);
          root.classList.toggle('av-no-animations', !s.appearance.animations || !!s.appearance.reduce);
          window.dispatchEvent(new CustomEvent('animevault:settings-applied', {{ detail: s }}));
        }})()"""
        self._web_view.page().runJavaScript(script)

    def apply_additional_settings(self, settings: Settings) -> None:
        """Apply persisted preferences handled outside appearance/library UI."""
        self._saved_settings = settings
        for section in ("notifications", "data", "metadata", "recommendations", "performance", "language"):
            values = getattr(settings, section, {})
            for key, value in values.items():
                self._settings.setValue(f"preferences/{section}/{key}", value)
        self._settings.sync()

        notifications = settings.notifications
        self._notification_service.set_enabled(True)
        self._notification_service.set_episodes(bool(notifications.get("episodes", True)))
        self._notification_service.set_reminders(bool(notifications.get("reminders", False)))
        self._notification_service.set_badge_count(1 if notifications.get("badge", True) else 0)
        self._cache_service.set_max_size(int(settings.performance.get("cache", 500)))
        self._maybe_create_scheduled_backup()

    def _maybe_create_scheduled_backup(self) -> None:
        """Create one safe backup per selected interval and enforce retention."""
        if not getattr(self, "_saved_settings", None):
            return
        config = self._saved_settings.data
        if not config.get("autoBackup", True):
            return
        now = datetime.now()
        raw_last = self._settings.value("data/last_auto_backup", "", type=str)
        try:
            last = datetime.fromisoformat(raw_last) if raw_last else None
        except ValueError:
            last = None
        interval_days = {"Daily": 1, "Weekly": 7, "Monthly": 30}.get(config.get("every", "Weekly"), 7)
        if last is not None and now - last < timedelta(days=interval_days):
            return
        path = backup_database()
        if path is None:
            return
        self._settings.setValue("data/last_auto_backup", now.isoformat(timespec="seconds"))
        self._settings.sync()
        purge_old_backups(max(1, int(config.get("keep", 7))))

    def set_settings_view_visible(self, visible: bool) -> None:
        """Show or hide the settings web view."""
        if self._settings_view is not None:
            self._settings_view.setVisible(visible)

    def _refresh_recommendations(self) -> None:
        # Re-run recommendation loading.  The panel refreshes itself via
        # its refresh_requested signal; nothing else needed here.
        pass

    def _quit(self) -> None:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.quit()