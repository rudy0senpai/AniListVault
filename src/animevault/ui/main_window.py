"""Redesigned main window: header, tabs, toolbar, search row, grid, sidebar."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QVBoxLayout,
    QWidget,
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
from animevault.ui.details_dialog import DetailsDialog
from animevault.ui.add_media_dialog import AddMediaDialog
from animevault.ui.overview_panel import OverviewPanel

from animevault.ui.video_background import DEFAULT_OPACITY as BACKGROUND_OPACITY
from animevault.ui.video_background import VideoBackground

logger = logging.getLogger(__name__)

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

        self._bulk_worker = None
        self._progress_dialog: Optional[QProgressDialog] = None

        self._category = MEDIA_ANIME
        self._search_text = ""
        self._filter_status = "All"
        self._filter_type = "All"
        self._filter_tier = "all"
        self._sort_mode = "title"
        self._select_mode = False

        self._build_ui()
        self._build_shortcuts()
        from animevault.ui.theme import ThemeManager
        manager = ThemeManager.instance()
        manager.theme_changed.connect(self._on_theme_changed)
        manager.effects_changed.connect(self._on_effects_changed)
        self._background.set_effects_reduced(
            manager.reduce_effects or manager.theme_id == "minimal-simple"
        )

        self.library_changed.connect(self.refresh)
        self.refresh()

    # ── UI construction ────────────────────────────────────────────

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Looping video background sits behind everything and ignores input.
        self._background = VideoBackground(central, opacity=BACKGROUND_OPACITY)
        self._background.setGeometry(central.rect())
        self._background.raise_()

        outer.addWidget(self._build_header())
        outer.addWidget(self._build_toolbar())
        outer.addWidget(self._build_search_row())

        # Body: grid + sidebar
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._grid = CardGrid()
        body.addWidget(self._grid, 1)

        self._overview_container = QWidget()
        overview_layout = QVBoxLayout(self._overview_container)
        overview_layout.setContentsMargins(0, 0, 0, 0)
        overview_layout.setSpacing(2)
        overview_header = QWidget()
        overview_header.setObjectName("overviewHeader")
        overview_header_layout = QHBoxLayout(overview_header)
        overview_header_layout.setContentsMargins(14, 8, 14, 0)
        overview_header_layout.setSpacing(8)
        overview_title = QLabel("Overview")
        overview_title.setObjectName("panelTitle")
        overview_header_layout.addWidget(overview_title)
        overview_header_layout.addStretch(1)
        self._overview_toggle = QPushButton(">>")
        self._overview_toggle.setObjectName("overviewToggle")
        self._overview_toggle.setFixedSize(34, 28)
        self._overview_toggle.setToolTip("Hide overview")
        self._overview_toggle.setAccessibleName("Hide overview")
        self._overview_toggle.clicked.connect(self._toggle_overview)
        overview_header_layout.addWidget(self._overview_toggle)
        overview_layout.addWidget(overview_header)

        self._overview = OverviewPanel()
        overview_layout.addWidget(self._overview, 1)
        body.addWidget(self._overview_container)

        outer.addLayout(body, 1)

        # Keep the background sized to the window, and behind the content.
        self._background.lower()
        central.installEventFilter(self)

    def _toggle_overview(self) -> None:
        """Collapse the analytics sidebar while leaving a reopen control visible."""
        hidden = not self._overview.isHidden()
        self._overview.setVisible(not hidden)
        if hidden:
            self._overview_container.setFixedWidth(130)
            self._overview_toggle.setText("<<")
            self._overview_toggle.setToolTip("Show overview")
            self._overview_toggle.setAccessibleName("Show overview")
        else:
            self._overview_container.setMinimumWidth(0)
            self._overview_container.setMaximumWidth(16777215)
            self._overview_container.setMinimumWidth(230)
            self._overview_toggle.setText(">>")
            self._overview_toggle.setToolTip("Hide overview")
            self._overview_toggle.setAccessibleName("Hide overview")

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
        header = QWidget()
        header.setObjectName("headerBar")
        header.setFixedHeight(62)
        row = QHBoxLayout(header)
        row.setContentsMargins(18, 10, 18, 10)
        row.setSpacing(20)

        icon = QLabel("◐")
        icon.setObjectName("appIcon")
        row.addWidget(icon)

        title = QLabel("AnimeVault")
        title.setObjectName("appTitle")
        row.addWidget(title)

        row.addSpacing(16)

        # Navigation tabs
        self._nav_buttons: dict[str, QPushButton] = {}
        for category in (MEDIA_ANIME, MEDIA_MANGA, MEDIA_MANHWA, MEDIA_MANHUA):
            button = QPushButton(CATEGORY_LABELS[category])
            button.setObjectName("navTab")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _checked, c=category: self._on_category_changed(c)
            )
            self._nav_buttons[category] = button
            row.addWidget(button)
        self._nav_buttons[MEDIA_ANIME].setChecked(True)

        row.addStretch()

        settings = QPushButton("⚙")
        settings.setObjectName("toolButton")
        settings.setFixedSize(34, 32)
        settings.setToolTip("Settings")
        settings.clicked.connect(self._show_settings)
        row.addWidget(settings)

        return header

    def _build_toolbar(self) -> QWidget:
        toolbar = QWidget()
        toolbar.setObjectName("toolBar")
        toolbar.setFixedHeight(44)
        row = QHBoxLayout(toolbar)
        row.setContentsMargins(18, 5, 18, 5)
        row.setSpacing(6)

        file_menu_btn = QPushButton("File")
        file_menu_btn.setObjectName("toolButton")
        menu = QMenu(file_menu_btn)
        import_xlsx = menu.addAction("Import Excel (.xlsx)…")
        import_csv = menu.addAction("Import CSV (.csv)…")
        import_sql = menu.addAction("Import SQL Dump (.sql)…")
        menu.addSeparator()
        export_csv = menu.addAction("Export to CSV…")
        export_xlsx = menu.addAction("Export to Excel (.xlsx)…")
        export_sql = menu.addAction("Export to SQL Dump…")
        menu.addSeparator()
        backup_action = menu.addAction("Back Up Database")
        quit_action = menu.addAction("Quit")
        file_menu_btn.setMenu(menu)
        row.addWidget(file_menu_btn)

        tools_btn = QPushButton("Tools")
        tools_btn.setObjectName("toolButton")
        tools_menu = QMenu(tools_btn)
        fetch_missing = tools_menu.addAction("Fetch Missing Data")
        refresh_all = tools_menu.addAction("Refresh Anime Data")
        tools_menu.addSeparator()
        cloud_sync = tools_menu.addAction("Cloud Sync…")
        tools_btn.setMenu(tools_menu)
        row.addWidget(tools_btn)

        help_btn = QPushButton("Help")
        help_btn.setObjectName("toolButton")
        help_menu = QMenu(help_btn)
        about = help_menu.addAction("About AnimeVault")
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

        row.addStretch()

        # Connect menu actions
        for action in (import_xlsx, upload_xlsx):
            action.triggered.connect(self._on_import_xlsx)
        for action in (import_csv, upload_csv):
            action.triggered.connect(self._on_import_csv)
        for action in (import_sql, upload_sql):
            action.triggered.connect(self._on_import_sql)
        for action in (export_csv, export_csv_btn):
            action.triggered.connect(lambda: self._on_export("csv"))
        for action in (export_xlsx, export_xlsx_btn):
            action.triggered.connect(lambda: self._on_export("xlsx"))
        for action in (export_sql, export_sql_btn):
            action.triggered.connect(lambda: self._on_export("sql"))
        backup_action.triggered.connect(self._on_backup)
        quit_action.triggered.connect(self._quit)
        fetch_missing.triggered.connect(lambda: self._on_bulk_enrich(False))
        refresh_all.triggered.connect(lambda: self._on_bulk_enrich(True))
        cloud_sync.triggered.connect(self._on_cloud_sync)
        about.triggered.connect(self._show_about)

        return toolbar

    def _build_search_row(self) -> QWidget:
        row_widget = QWidget()
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(18, 14, 18, 14)
        row.setSpacing(14)

        self._add_button = QPushButton("＋  Add Anime")
        self._add_button.setObjectName("primaryButton")
        self._add_button.clicked.connect(self._on_add)
        row.addWidget(self._add_button)

        self._search_field = QLineEdit()
        self._search_field.setObjectName("searchField")
        self._search_field.setPlaceholderText("Search Anime...")
        self._search_field.setClearButtonEnabled(True)
        self._search_field.textChanged.connect(self._on_search_changed)
        row.addWidget(self._search_field, 1)

        # Filter — tier + status combined into one control's options
        self._filter_combo = QComboBox()
        self._filter_combo.addItem("All")
        self._filter_combo.setToolTip("Filter by tier")
        self._filter_combo.currentTextChanged.connect(self._on_filter_tier_changed)
        row.addWidget(self._filter_combo)

        self._status_combo = QComboBox()
        self._status_combo.addItems(["All"] + list(VALID_STATUSES))
        self._status_combo.setToolTip("Filter by status")
        self._status_combo.currentTextChanged.connect(
            self._on_filter_status_changed
        )
        row.addWidget(self._status_combo)

        self._type_combo = QComboBox()
        self._type_combo.currentTextChanged.connect(
            self._on_filter_type_changed
        )
        row.addWidget(self._type_combo)

        self._sort_combo = QComboBox()
        for label, value in SORT_OPTIONS:
            self._sort_combo.addItem(label, value)
        self._sort_combo.setToolTip("Sort order")
        self._sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        row.addWidget(self._sort_combo)

        self._populate_tier_filter()
        self._populate_type_filter()
        return row_widget

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
        for card in cards:
            card.details_requested.connect(self._on_details)
            card.edit_requested.connect(self._on_edit)
            card.refresh_requested.connect(self._on_refresh_one)
            card.deleted.connect(self._on_delete_one)
            card.selection_changed.connect(self._on_card_selected)
            card.set_select_mode(self._select_mode)
        self._grid.set_cards(cards)

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
        self._populate_type_filter()
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
        for card in self._grid.cards:
            card.set_select_mode(enabled)
            if not enabled:
                card.set_selected(False)
        self._delete_button.setEnabled(
            enabled and any(c.is_selected() for c in self._grid.cards)
        )
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
        """Reload from the database and rebuild the grid + sidebar."""
        items, animes, literature = self._load_items()

        if self._category == MEDIA_ANIME:
            cards = [anime_card(i) for i in items]
        else:
            cards = [literature_card(i) for i in items]
        self._apply_cards(cards)

        self._overview.refresh(animes, literature)

    # ── Actions ────────────────────────────────────────────────────

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
        reply = QMessageBox.question(
            self,
            "Delete",
            f'Delete "{name}"?\n\nThis will remove it from your library.',
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            item.delete()
            self.library_changed.emit()

    def _on_delete_selected(self) -> None:
        selected = [c for c in self._grid.cards if c.is_selected()]
        if not selected:
            return
        names = "\n".join(f"• {c.item.title}" for c in selected[:10])
        if len(selected) > 10:
            names += f"\n… and {len(selected) - 10} more"
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
        for card in selected:
            card.item.delete()
        self._on_select_toggled(False)
        self.library_changed.emit()

    def _toggle_card_selection(self, card) -> None:
        if not self._select_mode:
            return
        card.set_selected(not card.is_selected())
        self._delete_button.setEnabled(
            any(c.is_selected() for c in self._grid.cards)
        )

    # ── Import ─────────────────────────────────────────────────────

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
        """Export the library to CSV, XLSX or a SQL dump."""
        from animevault.services.importers.exporter import export_library

        filters = {
            "csv": "CSV Files (*.csv)",
            "xlsx": "Excel Files (*.xlsx)",
            "sql": "SQL Files (*.sql)",
        }
        default_ext = {"csv": "csv", "xlsx": "xlsx", "sql": "sql"}[fmt]
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

    def _on_bulk_enrich(self, refresh_all: bool) -> None:
        from animevault.services.workers import BulkEnrichmentWorker

        animes = Anime.all()
        literature = Literature.all()
        if not animes and not literature:
            QMessageBox.information(self, "Empty Library", "There is nothing to enrich.")
            return

        title_mode = "Refreshing All Data" if refresh_all else "Fetching Missing Data"
        items = animes + literature
        self._progress_dialog = QProgressDialog(
            "Initializing fetcher...", "Cancel", 0, len(items), self
        )
        self._progress_dialog.setWindowTitle(title_mode)
        self._progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress_dialog.setMinimumDuration(200)

        self._bulk_worker = BulkEnrichmentWorker(items, refresh_all=refresh_all, parent=self)
        self._progress_dialog.canceled.connect(self._bulk_worker.cancel)
        self._bulk_worker.progress.connect(self._on_bulk_progress)
        self._bulk_worker.enrichment_finished.connect(self._on_bulk_finished)
        self._bulk_worker.start()

    def _on_bulk_progress(self, current, total, message, stats) -> None:
        if self._progress_dialog:
            self._progress_dialog.setValue(current)
            self._progress_dialog.setLabelText(
                f"{message}\n\nProgress: {current} / {total}\n"
                f"Updated: {stats.get('updated', 0)} | "
                f"Cached: {stats.get('cached', 0)} | "
                f"Failed: {stats.get('failed', 0)}"
            )

    def _on_bulk_finished(self, stats) -> None:
        if self._progress_dialog:
            self._progress_dialog.close()
        self.library_changed.emit()
        QMessageBox.information(
            self,
            "Enrichment Complete",
            f"• Updated: {stats.get('updated', 0)}\n"
            f"• Cached/Skipped: {stats.get('cached', 0)}\n"
            f"• Failed: {stats.get('failed', 0)}",
        )

    # ── Menus / dialogs ────────────────────────────────────────────

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About AnimeVault",
            "<b>AnimeVault</b> v0.3.0<br>"
            "Anime, Manga, Manhwa and Manhua library manager with "
            "multi-provider metadata enrichment.<br><br>"
            "Built with PySide6 and SQLite.",
        )

    def _on_theme_changed(self, theme_id: str) -> None:
        """Refresh custom-painted cards while retaining the current selection."""
        from animevault.ui.theme import ThemeManager

        manager = ThemeManager.instance()
        self._background.set_effects_reduced(
            manager.reduce_effects or theme_id == "minimal-simple"
        )
        selected_ids = {
            card.item.id for card in self._grid.cards if card.is_selected()
        }
        self._overview.apply_theme()
        self.refresh()
        for card in self._grid.cards:
            if card.item.id in selected_ids:
                card.set_selected(True)
        self._delete_button.setEnabled(bool(selected_ids))
        self._background.update()

    def _on_effects_changed(self, reduced: bool) -> None:
        from animevault.ui.theme import ThemeManager

        manager = ThemeManager.instance()
        self._background.set_effects_reduced(
            reduced or manager.theme_id == "minimal-simple"
        )

    def _show_settings(self) -> None:
        from animevault.ui.theme_dialog import ThemeSettingsDialog

        ThemeSettingsDialog(self).exec()

    def _quit(self) -> None:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.quit()