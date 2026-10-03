"""Responsive card grid.

Widgets are created once and only re-parented when the column count
changes, so resizing the window never rebuilds or re-decodes artwork —
the usual cause of a sluggish grid.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGridLayout, QScrollArea, QWidget

#: Cards never get narrower than this.
MIN_CARD_WIDTH = 268
GRID_H_SPACING = 14
GRID_V_SPACING = 14


class CardGrid(QScrollArea):
    """A scrollable, self-reflowing grid of cards."""

    card_clicked = Signal(object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QScrollArea.Shape.NoFrame)

        self._host = QWidget()
        self._host.setObjectName("gridHost")
        self._layout = QGridLayout(self._host)
        self._layout.setContentsMargins(16, 8, 16, 20)
        self._layout.setSpacing(GRID_V_SPACING)
        self._layout.setHorizontalSpacing(GRID_H_SPACING)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.setWidget(self._host)

        self._cards: list = []
        self._columns = 0

    # ── Content ────────────────────────────────────────────────────

    def set_cards(self, cards: list) -> None:
        """Replace the grid contents with *cards*."""
        self.clear()
        self._cards = list(cards)
        self._relayout(force=True)

    def clear(self) -> None:
        for card in self._cards:
            self._layout.removeWidget(card)
            card.setParent(None)
            card.deleteLater()
        self._cards = []
        self._columns = 0
        self._layout.invalidate()

    @property
    def cards(self) -> list:
        return list(self._cards)

    def card_count(self) -> int:
        return len(self._cards)

    # ── Layout ─────────────────────────────────────────────────────

    def _column_count_for_width(self, width: int) -> int:
        """How many cards fit in *width* pixels."""
        if width <= 0:
            return 1
        usable = width - self._layout.contentsMargins().left() - self._layout.contentsMargins().right()
        per_card = MIN_CARD_WIDTH + GRID_H_SPACING
        columns = int(usable // per_card)
        return max(1, columns)

    def _relayout(self, force: bool = False) -> None:
        """Place cards into the current column count, reusing widgets."""
        viewport = self.viewport().width()
        columns = self._column_count_for_width(viewport)
        if not force and columns == self._columns:
            return
        self._columns = columns

        # Detach everything so the grid can be rebuilt without deleting.
        for card in self._cards:
            self._layout.removeWidget(card)

        for index, card in enumerate(self._cards):
            row = index // columns
            col = index % columns
            self._layout.addWidget(card, row, col)
        self._host.adjustSize()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._relayout()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._relayout()