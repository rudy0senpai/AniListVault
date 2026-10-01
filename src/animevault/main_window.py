"""Main application window — displays the anime library as cards."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMenuBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from animevault.models.anime import Anime
from animevault.ui.add_anime_dialog import AddAnimeDialog
from animevault.ui.anime_card import AnimeCard


class MainWindow(QMainWindow):
    """Top-level window containing the library browser."""

    # Internal: fired when the anime list changes so the window can
    # re-render the card layout.
    library_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AnimeVault")
        self.resize(900, 600)

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
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.AsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.AsNeeded)

        self._content = QWidget()
        self._content_layout = QVBoxLayout()
        self._content_layout.setContentsMargins(16, 0, 16, 16)
        self._content_layout.setSpacing(12)
        self._content_layout.setAlignment(Qt.AlignmentFlag.Top)
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

        # Help menu
        help_menu: QMenu = menubar.addMenu("&Help")

        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _show_about(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.about(
            self,
            "About AnimeVault",
            "<b>AnimeVault</b> v0.0.1<br>"
            "A minimal desktop anime library manager.<br><br>"
            "Built with PySide6 and SQLite.",
        )

    # ── Slots ─────────────────────────────────────────────────────

    def _on_add_anime(self) -> None:
        """Open the Add Anime dialog; refresh on success."""
        dialog = AddAnimeDialog(self)
        if dialog.exec() == AddAnimeDialog.DialogCode.Accepted:
            self.library_changed.emit()

    def _refresh_library(self) -> None:
        """Rebuild the card layout from the database."""
        # Clear existing cards
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
