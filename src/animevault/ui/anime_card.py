"""Visual card widget for a single Anime entry."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from animevault.models.anime import Anime
from animevault.services.enrichment import merge_metadata_into_anime, pick_best_match
from animevault.services.poster import download_poster
from animevault.services.search import SearchService


class AnimeCard(QFrame):
    """A compact card that summarises one :class:`Anime`.

    Includes status badge, poster thumbnail if available, and actions
    menu (refresh metadata, delete).
    """

    # Emitted when the card is clicked
    clicked = Signal(object)
    # Emitted after metadata refresh
    refresh_requested = Signal(object)
    # Emitted after deletion
    deleted = Signal(object)

    def __init__(self, anime: Anime, parent=None) -> None:
        super().__init__(parent)
        self._anime = anime
        self._setup_ui()
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _setup_ui(self) -> None:
        self.setObjectName("anime-card")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)

        root_layout = QHBoxLayout()
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(12)

        # ── Poster thumbnail ──────────────────────────────────────
        self._poster_label = QLabel()
        self._poster_label.setFixedSize(55, 75)
        self._poster_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._poster_label.setStyleSheet("background: #f0f0f0; border-radius: 4px; color: #aaa;")

        has_poster = False
        if self._anime.poster_path:
            p = Path(self._anime.poster_path)
            if p.exists() and p.is_file():
                pixmap = QPixmap(str(p))
                if not pixmap.isNull():
                    scaled = pixmap.scaled(
                        55, 75,
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    self._poster_label.setPixmap(scaled)
                    has_poster = True

        if not has_poster:
            self._poster_label.setText("No\nCover")

        root_layout.addWidget(self._poster_label)

        # ── Card details ──────────────────────────────────────────
        main_col = QVBoxLayout()
        main_col.setContentsMargins(0, 0, 0, 0)
        main_col.setSpacing(3)

        # --- Top row: title + status badge + menu button ---
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)

        title_label = QLabel(self._anime.title)
        title_font = title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 1)
        title_label.setFont(title_font)
        title_label.setObjectName("card-title")

        status_label = QLabel(self._anime.status.replace("_", " ").title())
        status_label.setStyleSheet(
            "background:#e0e0e0; border-radius:4px; padding:2px 8px; font-size:10px;"
        )
        status_label.setObjectName("card-status")

        # ⋮ Action menu button
        self._menu_btn = QPushButton("⋮")
        self._menu_btn.setFixedSize(24, 24)
        self._menu_btn.setStyleSheet(
            "QPushButton { border: none; font-size: 14px; font-weight: bold; color: #555; } "
            "QPushButton:hover { background: #ddd; border-radius: 12px; }"
        )
        self._menu_btn.clicked.connect(self._show_actions_menu)

        top_row.addWidget(title_label)
        top_row.addStretch()
        top_row.addWidget(status_label)
        top_row.addWidget(self._menu_btn)

        # --- Middle row: Japanese / alt title / episodes / genres ---
        mid_row = QHBoxLayout()
        mid_row.setContentsMargins(0, 0, 0, 0)
        mid_row.setSpacing(8)

        secondary_parts: list[str] = []
        if self._anime.title_ja:
            secondary_parts.append(self._anime.title_ja)
        secondary_parts.append(f"{self._anime.episodes} ep" if self._anime.episodes else "? ep")
        if self._anime.genres:
            secondary_parts.append(", ".join(self._anime.genres[:3]))

        secondary_label = QLabel(" · ".join(secondary_parts))
        secondary_label.setStyleSheet("color:#666; font-size:11px;")
        mid_row.addWidget(secondary_label)
        mid_row.addStretch()

        # --- Bottom row: score + synopsis/notes ---
        meta_layout = QHBoxLayout()
        meta_layout.setContentsMargins(0, 0, 0, 0)
        meta_layout.setSpacing(12)

        if self._anime.score is not None:
            score_label = QLabel(f"Score: {self._anime.score:.1f}")
            score_label.setStyleSheet("color:#555; font-size:11px; font-weight:bold;")
            meta_layout.addWidget(score_label)

        display_text = self._anime.synopsis or self._anime.notes
        if display_text:
            snippet = display_text.replace("\n", " ")[:90] + ("..." if len(display_text) > 90 else "")
            text_label = QLabel(snippet)
            text_label.setStyleSheet("color:#777; font-size:10px;")
            text_label.setToolTip(display_text)
            meta_layout.addWidget(text_label)

        meta_layout.addStretch()

        main_col.addLayout(top_row)
        main_col.addLayout(mid_row)
        main_col.addLayout(meta_layout)

        root_layout.addLayout(main_col)
        self.setLayout(root_layout)

    def _show_actions_menu(self) -> None:
        menu = QMenu(self)
        refresh_action = menu.addAction("Fetch / Refresh Metadata")
        delete_action = menu.addAction("Delete Anime")

        chosen = menu.exec(self._menu_btn.mapToGlobal(self._menu_btn.rect().bottomLeft()))
        if chosen == refresh_action:
            self._on_refresh_metadata()
        elif chosen == delete_action:
            self._on_delete_anime()

    def _on_refresh_metadata(self) -> None:
        service = SearchService()
        results = service.search(self._anime.title, limit=5)
        best = pick_best_match(
            self._anime.title,
            results,
            anilist_id=self._anime.anilist_id,
            mal_id=self._anime.mal_id,
        )
        if best:
            merge_metadata_into_anime(self._anime, best)
            if best.poster_url and not self._anime.poster_path:
                local_p = download_poster(best.poster_url)
                if local_p:
                    self._anime.poster_path = local_p
            self._anime.save()
            QMessageBox.information(
                self,
                "Metadata Updated",
                f"Successfully updated metadata for '{self._anime.title}'."
            )
            self.refresh_requested.emit(self._anime)
        else:
            QMessageBox.warning(
                self,
                "No Match",
                f"Could not find matching metadata online for '{self._anime.title}'."
            )

    def _on_delete_anime(self) -> None:
        confirm = QMessageBox.question(
            self,
            "Delete Anime",
            f"Delete \"{self._anime.title}\"?\n\nThis will remove the anime from your library.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self._anime.delete()
            self.deleted.emit(self._anime)

    @property
    def anime(self) -> Anime:
        return self._anime

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._anime)
        super().mousePressEvent(event)
