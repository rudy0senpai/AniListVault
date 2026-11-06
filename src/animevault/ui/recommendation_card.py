"""Visual card widget for a single recommendation.

Displays the recommendation's poster, title, genres, synopsis, predicted
preference score, and an explanation of why it was recommended.  Includes
actions: add to Plan to Watch, add to library, mark as Not Interested,
view details, and refresh.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from animevault.services.recommendation_engine import RecommendationResult


class RecommendationCard(QFrame):
    """A compact card summarising one :class:`RecommendationResult`."""

    # Emitted when the user requests details
    details_requested = Signal(int)
    # Emitted when the user wants to add to Plan to Watch
    to_plan_requested = Signal(int)
    # Emitted when the user wants to add to library
    to_library_requested = Signal(int)
    # Emitted when the user marks as Not Interested
    not_interested_requested = Signal(int)
    # Emitted when the user refreshes recommendations
    refresh_requested = Signal()

    def __init__(
        self,
        result: RecommendationResult,
        parent: Optional["QFrame"] = None,
    ) -> None:
        super().__init__(parent)
        self._result = result
        self._setup_ui()
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    # ── UI setup ────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setObjectName("recommendationCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # ── Header: title + score ───────────────────────────────────
        header = QHBoxLayout()
        self._title_label = QLabel(self._result.title)
        self._title_label.setObjectName("recommendationTitle")
        self._title_label.setWordWrap(True)

        self._score_label = QLabel(f"Predicted: {self._result.score:.1%}")
        self._score_label.setObjectName("recommendationScore")

        header.addWidget(self._title_label)
        header.addStretch(1)
        header.addWidget(self._score_label)
        root.addLayout(header)

        # ── Genres + synopsis ───────────────────────────────────────
        info = QHBoxLayout()
        info.setSpacing(8)

        self._genres_label = QLabel()
        self._genres_label.setObjectName("recommendationGenres")
        self._genres_label.setWordWrap(True)
        self._genres_label.setText("\n".join(self._result.genres) if self._result.genres else "—")

        self._synopsis_label = QLabel(self._result.synopsis or "No synopsis available")
        self._synopsis_label.setObjectName("recommendationSynopsis")
        self._synopsis_label.setWordWrap(True)

        info.addWidget(self._genres_label, 1)
        info.addWidget(self._synopsis_label, 1)
        root.addLayout(info)

        # ── Meta row ────────────────────────────────────────────────
        meta = QHBoxLayout()
        meta.setSpacing(12)

        self._type_label = QLabel(self._result.media_type or "—")
        self._type_label.setObjectName("recommendationMeta")
        meta.addWidget(self._type_label)

        if self._result.progress:
            self._progress_label = QLabel(self._result.progress)
            self._progress_label.setObjectName("recommendationMeta")
            meta.addWidget(self._progress_label)

        if self._result.discovery_source:
            src = QLabel(self._result.discovery_source.upper())
            src.setObjectName("recommendationMeta")
            meta.addWidget(src)

        meta.addStretch(1)

        if self._result.is_plan_to_watch:
            badge = QLabel("Planned")
            badge.setObjectName("recommendationBadge")
            badge.setStyleSheet("color: #b08d57; font-weight: bold;")
            meta.addWidget(badge)

        root.addLayout(meta)

        # ── Explanation ─────────────────────────────────────────────
        if self._result.reasons:
            explan = QHBoxLayout()
            explan.setContentsMargins(0, 2, 0, 0)
            explan.setSpacing(4)
            expl_label = QLabel("Why: " + " • ".join(self._result.reasons))
            expl_label.setObjectName("recommendationReason")
            explan.addWidget(expl_label)
            root.addLayout(explan)

        # ── Poster ──────────────────────────────────────────────────
        self._poster_label = QLabel()
        self._poster_label.setObjectName("recommendationPoster")
        self._poster_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._poster_label.setFixedSize(70, 95)
        self._poster_label.setStyleSheet(
            "background: #f0f0f0; border-radius: 4px; color: #aaa; "
            "border: 1px solid #ddd;"
        )
        self._refresh_poster()

        poster_layout = QHBoxLayout()
        poster_layout.addStretch(1)
        poster_layout.addWidget(self._poster_label)
        poster_layout.addStretch(1)
        root.addLayout(poster_layout)

        # ── Actions ─────────────────────────────────────────────────
        self._build_actions()

    # ── Poster refresh ──────────────────────────────────────────────

    def _refresh_poster(self) -> None:
        url = self._result.poster_url or ""
        if url:
            try:
                from animevault.services.poster import _download_poster
                p = _download_poster(url, cache_dir=Path.home() / ".cache" / "animevault")
                if p and p.exists():
                    pix = QPixmap(str(p))
                    if not pix.isNull():
                        scaled = pix.scaled(
                            70, 95,
                            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                        self._poster_label.setPixmap(scaled)
                        self._poster_label.setStyleSheet(
                            "background: transparent; border-radius: 4px; color: #aaa; "
                            "border: 1px solid #ddd;"
                        )
                        return
            except Exception:
                pass
        self._poster_label.setText("No poster")

    # ── Actions ─────────────────────────────────────────────────────

    def _build_actions(self) -> None:
        self._actions = QHBoxLayout()
        self._actions.setSpacing(4)

        self._to_plan_btn = QPushButton("To Plan")
        self._to_plan_btn.setFixedWidth(64)
        self._to_plan_btn.setToolTip("Add to Plan to Watch")
        self._to_plan_btn.clicked.connect(lambda _: self.to_plan_requested.emit(self._result.item_id))
        self._actions.addWidget(self._to_plan_btn)

        self._to_lib_btn = QPushButton("Add")
        self._to_lib_btn.setFixedWidth(64)
        self._to_lib_btn.setToolTip("Add to AnimeVault")
        self._to_lib_btn.clicked.connect(lambda _: self.to_library_requested.emit(self._result.item_id))
        self._actions.addWidget(self._to_lib_btn)

        self._not_int_btn = QPushButton("Not Interested")
        self._not_int_btn.setFixedWidth(100)
        self._not_int_btn.setToolTip("Mark as Not Interested")
        self._not_int_btn.clicked.connect(lambda _: self.not_interested_requested.emit(self._result.item_id))
        self._actions.addWidget(self._not_int_btn)

        root = self.layout()
        root.addWidget(self._actions)

    # ── Public API ──────────────────────────────────────────────────

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        view = menu.addAction("View details")
        refresh = menu.addAction("Refresh recommendations")
        action = menu.exec(event.globalPos())
        if action == view:
            self.details_requested.emit(self._result.item_id)
        elif action == refresh:
            self.refresh_requested.emit()

    def set_result(self, result: RecommendationResult) -> None:
        self._result = result
        self._title_label.setText(result.title)
        self._score_label.setText(f"Predicted: {result.score:.1%}")
        self._genres_label.setText("\n".join(result.genres) if result.genres else "—")
        self._synopsis_label.setText(result.synopsis or "No synopsis available")
        self._type_label.setText(result.media_type or "—")
        if result.progress:
            self._progress_label = QLabel(result.progress)
            self.layout().itemAt(self.layout().count() - 1).replaceWidget(
                self._progress_label, self._progress_label
            )
            self._progress_label.setText(result.progress)
        self._refresh_poster()
