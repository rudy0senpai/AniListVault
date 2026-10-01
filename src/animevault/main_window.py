"""Main application window — displays the anime library as cards."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from animevault.models.anime import Anime
from animevault.services.workers import BulkEnrichmentWorker
from animevault.ui.add_anime_dialog import AddAnimeDialog
from animevault.ui.anime_card import AnimeCard


class MainWindow(QMainWindow):
    """Top-level window containing the library browser."""

    library_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AnimeVault")
        self.resize(920, 640)

        self._bulk_worker: Optional[BulkEnrichmentWorker] = None
        self._progress_dialog: Optional[QProgressDialog] = None

        self._central = QWidget()
        self.setCentralWidget(self._central)

        # --- Top toolbar (horizontal, left-aligned) ---
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(16, 12, 16, 8)
        toolbar.setSpacing(12)

        self._add_button = QPushButton("＋ Add Anime")
        self._add_button.setObjectName("add-button")
        self._add_button.clicked.connect(self._on_add_anime)
        toolbar.addWidget(self._add_button)

        toolbar.addStretch()
        self._count_label = QLabel()
        toolbar.addWidget(self._count_label)

        # --- Scroll area for cards ---
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self._content = QWidget()
        self._content_layout = QVBoxLayout()
        self._content_layout.setContentsMargins(16, 0, 16, 16)
        self._content_layout.setSpacing(10)
        self._content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._content.setLayout(self._content_layout)

        self._scroll.setWidget(self._content)

        # --- Main layout ---
        main = QVBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        main.addLayout(toolbar)
        main.addWidget(self._scroll)

        self._central.setLayout(main)

        # --- Menu bar ---
        self._build_menubar()

        # --- Populate ---
        self._refresh_library()
        self.library_changed.connect(self._refresh_library)

    # ── Menu bar ──────────────────────────────────────────────────

    def _build_menubar(self) -> None:
        menubar = self.menuBar()

        # File menu
        file_menu: QMenu = menubar.addMenu("&File")

        quit_action = QAction("&Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(QApplication_instance_quit)
        file_menu.addAction(quit_action)

        # Tools menu
        tools_menu: QMenu = menubar.addMenu("&Tools")

        fetch_missing_action = QAction("&Fetch Missing Metadata", self)
        fetch_missing_action.triggered.connect(lambda: self._on_bulk_enrich(refresh_all=False))
        tools_menu.addAction(fetch_missing_action)

        refresh_all_action = QAction("&Refresh All Metadata", self)
        refresh_all_action.triggered.connect(lambda: self._on_bulk_enrich(refresh_all=True))
        tools_menu.addAction(refresh_all_action)

        # Help menu
        help_menu: QMenu = menubar.addMenu("&Help")

        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About AnimeVault",
            "<b>AnimeVault</b> v0.2.0<br>"
            "Anime library manager with multi-provider metadata enrichment.<br><br>"
            "Built with PySide6 and SQLite.",
        )

    # ── Slots ─────────────────────────────────────────────────────

    def _on_add_anime(self) -> None:
        """Open the Add Anime dialog; refresh on success."""
        dialog = AddAnimeDialog(self)
        if dialog.exec() == AddAnimeDialog.DialogCode.Accepted:
            self.library_changed.emit()

    def _on_bulk_enrich(self, refresh_all: bool = False) -> None:
        """Run library-wide enrichment in bounded background chunks."""
        animes = Anime.all()
        if not animes:
            QMessageBox.information(self, "Empty Library", "There are no anime in your library.")
            return

        title_mode = "Refreshing All Metadata" if refresh_all else "Fetching Missing Metadata"
        self._progress_dialog = QProgressDialog(
            "Initializing metadata fetcher...", "Cancel", 0, len(animes), self
        )
        self._progress_dialog.setWindowTitle(title_mode)
        self._progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress_dialog.setMinimumDuration(200)

        self._bulk_worker = BulkEnrichmentWorker(animes, refresh_all=refresh_all, parent=self)
        self._progress_dialog.canceled.connect(self._bulk_worker.cancel)

        self._bulk_worker.progress.connect(self._on_bulk_progress)
        self._bulk_worker.enrichment_finished.connect(self._on_bulk_finished)
        self._bulk_worker.start()

    def _on_bulk_progress(self, current: int, total: int, message: str, stats: dict) -> None:
        if self._progress_dialog:
            self._progress_dialog.setValue(current)
            stat_text = (
                f"{message}\n\n"
                f"Progress: {current} / {total}\n"
                f"Updated: {stats['updated']} | Cached: {stats['cached']} | "
                f"Posters: {stats['posters']} | Failed: {stats['failed']}"
            )
            self._progress_dialog.setLabelText(stat_text)

    def _on_bulk_finished(self, stats: dict) -> None:
        if self._progress_dialog:
            self._progress_dialog.close()

        self.library_changed.emit()
        QMessageBox.information(
            self,
            "Enrichment Complete",
            f"Finished processing anime library!\n\n"
            f"• Updated: {stats['updated']}\n"
            f"• Cached/Skipped: {stats['cached']}\n"
            f"• Posters downloaded: {stats['posters']}\n"
            f"• Failed: {stats['failed']}",
        )

    def _refresh_library(self) -> None:
        """Rebuild the card layout from the database."""
        while self._content_layout.count():
            child = self._content_layout.takeAt(0)
            if child.widget() is not None:
                child.widget().deleteLater()

        animes = Anime.all()
        if not animes:
            placeholder = QLabel("Your library is empty. Click \"＋ Add Anime\" to get started.")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet("color: #888; padding: 40px;")
            self._content_layout.addWidget(placeholder)

        for anime in animes:
            card = AnimeCard(anime)
            card.refresh_requested.connect(self.library_changed.emit)
            card.deleted.connect(self.library_changed.emit)
            self._content_layout.addWidget(card)

        count = len(animes)
        self._count_label.setText(f"{count} anime in library")


# ── Helpers ──────────────────────────────────────────────────────────

def QApplication_instance_quit():
    """Lazy reference to QApplication so main_window stays testable."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is not None:
        app.quit()
