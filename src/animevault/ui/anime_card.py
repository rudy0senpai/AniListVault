"""Visual card widget for a single Anime entry."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from animevault.models.anime import Anime


class AnimeCard(QFrame):
    """A compact card that summarises one :class:`Anime`.

    Layout::

        ┌──────────────────────────────┐
        │ Title  [status badge]        │   ← bold title, status on the right
        │ 〈Japanese title〉  (12/24)   │   ← secondary line
        │ Score: 8.5  Notes: …         │   ← optional meta line
        └──────────────────────────────┘
    """

    # Emitted when the card is clicked (e.g. to open a detail view later).
    clicked = Signal(object)

    def __init__(self, anime: Anime) -> None:
        super().__init__()
        self._anime = anime
        self._setup_ui()
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    # ── Layout ────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setObjectName("anime-card")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)

        # --- Top row: title + status badge ---
        top_row = QHBoxLayout()
        top_row.setContentsMargins(12, 10, 12, 4)
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

        top_row.addWidget(title_label)
        top_row.addStretch()
        top_row.addWidget(status_label)

        # --- Middle row: Japanese title / episode count ---
        mid_row = QHBoxLayout()
        mid_row.setContentsMargins(12, 4, 12, 4)
        mid_row.setSpacing(8)

        secondary_parts: list[str] = []
        if self._anime.title_ja:
            secondary_parts.append(self._anime.title_ja)
        secondary_parts.append(f"{self._anime.episodes} ep")

        secondary_label = QLabel(" · ".join(secondary_parts))
        secondary_label.setStyleSheet("color:#666;")
        mid_row.addWidget(secondary_label)
        mid_row.addStretch()

        # --- Bottom row: score + notes (if present) ---
        bottom_widgets: list[QLabel] = []
        meta_layout = QHBoxLayout()
        meta_layout.setContentsMargins(12, 4, 12, 8)
        meta_layout.setSpacing(12)

        if self._anime.score is not None:
            score_label = QLabel(f"Score: {self._anime.score:.1f}")
            score_label.setStyleSheet("color:#666;")
            meta_layout.addWidget(score_label)
            bottom_widgets.append(score_label)

        if self._anime.notes:
            notes_label = QLabel(self._anime.notes)
            notes_label.setStyleSheet("color:#666;")
            notes_label.setToolTip(self._anime.notes)
            meta_layout.addWidget(notes_label)
            bottom_widgets.append(notes_label)

        # If neither score nor notes, keep a small spacer so the card
        # doesn't look too top-heavy.
        if not bottom_widgets:
            meta_layout.addStretch()

        # --- Assemble ---
        main_col = QVBoxLayout()
        main_col.setContentsMargins(0, 0, 0, 0)
        main_col.setSpacing(0)
        main_col.addLayout(top_row)
        main_col.addLayout(mid_row)
        main_col.addLayout(meta_layout)
        self.setLayout(main_col)

    # ── Helpers ───────────────────────────────────────────────────

    @property
    def anime(self) -> Anime:
        return self._anime

    # ── Mouse events (for click signal) ───────────────────────────

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._anime)
        super().mousePressEvent(event)
