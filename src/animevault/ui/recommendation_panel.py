"""Dedicated Recommendations page/section.

Displays personalised recommendations with filters (genre/category,
minimum relevance, release year, format, status, sort) and actions
(add to Plan to Watch, add to library, mark as Not Interested, view
details, refresh).  Matching the existing AnimeVault visual design.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QSlider,
)

# The recommendation card component.
from animevault.ui.recommendation_card import RecommendationCard

# The engine.
from animevault.services.recommendation_engine import RecommendationEngine

# The card grid from the main window.
from animevault.ui.card_grid import CardGrid

# Media type labels.
from animevault.ui.card_factory import type_label


class RecommendationPanel(QFrame):
    """
    A self-contained Recommendations page with filters, a refresh button,
    and a grid of RecommendationCard widgets.
    """

    # Emitted when the refresh button is clicked.
    refresh_requested = Signal()

    # Emitted when the user selects a new category.
    category_changed = Signal(str)

    # Emitted when the user requests the details dialog for an item.
    details_requested = Signal(int)

    # Emitted when the user requests to add to Plan to Watch.
    to_plan_requested = Signal(int)

    # Emitted when the user requests to add to library.
    to_library_requested = Signal(int)

    # Emitted when the user marks as Not Interested.
    not_interested_requested = Signal(int)

    def __init__(self, parent: Optional["QWidget"] = None):
        super().__init__(parent)
        self.setObjectName("recommendationPanel")
        self._engine = RecommendationEngine()
        self._filter_state = {
            "category": "all",
            "genre": "",
            "media_type": "all",
            "min_score": 0.0,
            "sort_by": "relevance",
        }
        self._cards: list[RecommendationCard] = []
        self._build_ui()
        self._load_recommendations()

    # ── UI build ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # ── Top section ─────────────────────────────────────────────
        self._header = QGroupBox("Personalized Recommendations")
        self._header.setObjectName("recommendationHeader")
        header_layout = QHBoxLayout(self._header)

        self._title = QLabel("Discover what you'll love next")
        self._title.setObjectName("recommendationHeading")
        header_layout.addWidget(self._title)

        self._refresh_btn = QPushButton("Refresh recommendations")
        self._refresh_btn.setObjectName("recommendationRefresh")
        self._refresh_btn.clicked.connect(self._load_recommendations)
        header_layout.addWidget(self._refresh_btn)

        header_layout.addStretch(1)

        # Preference summary (if data exists).
        self._summary = QLabel("Not enough data yet to build a profile.")
        self._summary.setObjectName("recommendationSummary")
        header_layout.addWidget(self._summary)

        root.addWidget(self._header)

        # ── Filters group ────────────────────────────────────────────
        self._filters = QGroupBox("Filters")
        self._filters.setObjectName("recommendationFilters")
        filter_layout = QHBoxLayout(self._filters)

        self._category_combo = self._build_category_combo()
        filter_layout.addWidget(self._category_combo)

        self._genre_combo = self._build_genre_combo()
        filter_layout.addWidget(self._genre_combo)

        self._format_combo = self._build_format_combo()
        filter_layout.addWidget(self._format_combo)

        self._min_score_slider_container = self._build_min_score_slider()
        filter_layout.addWidget(self._min_score_slider_container)
        self._min_score_slider = self._min_score_slider_container.findChild(QSlider)

        filter_layout.addStretch(1)

        root.addWidget(self._filters)

        # ── Grid ─────────────────────────────────────────────────────
        self._grid = CardGrid()
        self._grid.setObjectName("recommendationGrid")
        scroll = QScrollArea()
        scroll.setObjectName("recommendationScroll")
        scroll.setWidget(self._grid)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(scroll)

        # ── Status label ─────────────────────────────────────────────
        self._status_label = QLabel("Showing 0 recommendations.")
        self._status_label.setObjectName("recommendationStatus")
        root.addWidget(self._status_label)

        # ── Connect signals ──────────────────────────────────────────
        self._refresh_btn.clicked.connect(self.refresh_requested)
        self._category_combo.currentTextChanged.connect(self._on_category_changed)
        self._genre_combo.currentTextChanged.connect(self._on_filter_changed)
        self._format_combo.currentTextChanged.connect(self._on_filter_changed)
        self._grid.details_requested.connect(self.details_requested)
        self._grid.to_plan_requested.connect(self.to_plan_requested)
        self._grid.to_library_requested.connect(self.to_library_requested)
        self._grid.not_interested_requested.connect(self.not_interested_requested)
        self._grid.refresh_requested.connect(self.refresh_requested)

    # ── Combo builders ──────────────────────────────────────────────

    def _build_category_combo(self) -> QComboBox:
        from PySide6.QtWidgets import QComboBox
        combo = QComboBox()
        combo.setObjectName("categoryCombo")
        combo.addItem("All categories", "all")
        for c in sorted(["isekai", "action", "adventure", "fantasy", "romance",
                         "comedy", "mystery", "horror", "psychological",
                         "sci-fi", "slice of life", "drama", "supernatural",
                         "sports", "thriller"]):
            combo.addItem(c.title(), c)
        combo.currentTextChanged.connect(self._on_category_changed)
        return combo

    def _build_genre_combo(self) -> QComboBox:
        from PySide6.QtWidgets import QComboBox
        combo = QComboBox()
        combo.setObjectName("genreCombo")
        combo.addItem("Any genre", "")
        for g in sorted(["isekai", "action", "adventure", "fantasy", "romance",
                         "comedy", "mystery", "horror", "psychological",
                         "sci-fi", "slice of life", "drama", "supernatural",
                         "sports", "thriller"]):
            combo.addItem(g, g)
        return combo

    def _build_format_combo(self) -> QComboBox:
        from PySide6.QtWidgets import QComboBox
        combo = QComboBox()
        combo.setObjectName("formatCombo")
        combo.addItem("All formats", "all")
        for f in ["TV", "Movie", "OVA", "ONA", "Special"]:
            combo.addItem(f, f)
        return combo

    def _build_min_score_slider(self):
        from PySide6.QtWidgets import QSlider, QLabel, QWidget, QHBoxLayout
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setObjectName("minScoreSlider")
        slider.setRange(0, 100)
        slider.setValue(0)
        slider.setFixedWidth(120)
        self._min_score_label = QLabel("0%")
        self._min_score_label.setObjectName("minScoreLabel")
        self._min_score_label.setFixedWidth(30)
        container = QWidget()
        h = QHBoxLayout(container)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self._min_score_label)
        h.addWidget(slider)
        return container

    # ── Loading & rendering ─────────────────────────────────────────

    def _load_recommendations(self) -> None:
        """Query the engine and render cards."""
        # Update the header summary.
        summary = self._engine.get_preference_summary()
        if summary.get("has_preferences"):
            self._title.setText("Your Recommendations")
            self._summary.setText(
                f"{summary['rating_count']} rated titles, "
                f"{summary['top_genres'][0][1] if summary['top_genres'] else 0} top genre match"
            )
        else:
            self._title.setText("Personalized Recommendations")
            self._summary.setText(
                "Not enough library data yet. Add anime to your library "
                "to get started."
            )

        # Apply filters.
        self._filter_state["category"] = (
            self._category_combo.currentData() or "all"
        )
        self._filter_state["genre"] = self._genre_combo.currentData() or ""
        self._filter_state["media_type"] = (
            self._format_combo.currentData() or "all"
        )
        self._filter_state["min_score"] = self._min_score_slider.value() / 100.0
        self._filter_state["sort_by"] = "relevance"

        category = self._filter_state["category"]
        genre = self._filter_state["genre"]
        media_type = self._filter_state["media_type"]
        min_score = self._filter_state["min_score"]

        # Build the engine with the current library.
        engine = RecommendationEngine(
            library_items=self._engine.library_items,
            online_discovery=True,
        )
        results = engine.get_recommendations(
            category=category,
            n=60,
            genre_filter=genre,
            media_type_filter=media_type,
            min_score=min_score,
        )

        self._status_label.setText(f"Showing {len(results)} recommendations.")
        self._render_cards(results)
        self._update_poster_hover()

    def _render_cards(self, results: list) -> None:
        """Clear the grid and render the recommendation cards."""
        self._grid.clear()
        self._cards = []
        for r in results:
            card = RecommendationCard(r)
            card.details_requested.connect(self._on_details)
            card.to_plan_requested.connect(self._on_to_plan)
            card.to_library_requested.connect(self._on_to_library)
            card.not_interested_requested.connect(self._on_not_interested)
            card.refresh_requested.connect(self._load_recommendations)
            self._grid.add_card(card)
            self._cards.append(card)

    def _update_poster_hover(self) -> None:
        """Refresh posters on hover (lazy load)."""
        for card in self._cards:
            card._refresh_poster()

    # ── Event handlers ──────────────────────────────────────────────

    def _on_category_changed(self, text: str) -> None:
        self.category_changed.emit(text)
        self._load_recommendations()

    def _on_filter_changed(self) -> None:
        self._load_recommendations()

    def _on_details(self, item_id: int) -> None:
        self.details_requested.emit(item_id)

    def _on_to_plan(self, item_id: int) -> None:
        self.to_plan_requested.emit(item_id)

    def _on_to_library(self, item_id: int) -> None:
        self.to_library_requested.emit(item_id)

    def _on_not_interested(self, item_id: int) -> None:
        self.not_interested_requested.emit(item_id)

    # ── Public API ──────────────────────────────────────────────────

    def set_engine(self, engine: RecommendationEngine) -> None:
        self._engine = engine

    def refresh(self) -> None:
        self._load_recommendations()
