"""Dedicated modal dialog for personalized recommendations.

Replaces the embedded recommendation side panel with a focused modal
experience.  Refresh regenerates recommendations from the current library.
"""

from __future__ import annotations

from typing import Optional
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from animevault.services.recommendation_engine import (
    RecommendationEngine,
    RecommendationResult,
)
from animevault.models.anime import Anime
from animevault.models.literature import Literature

import logging

# Track active recommendation loaders at module level
_active_rec_loaders: set = set()

_logger = logging.getLogger(__name__)


def _load_library_items() -> list:
    """Load all supported media types from the database."""
    items = []
    errors = []
    try:
        items.extend(Anime.all())
    except Exception as exc:
        _logger.warning("Failed to load Anime records: %s", exc)
        errors.append(("Anime", exc))
    try:
        items.extend(Literature.all())
    except Exception as exc:
        _logger.warning("Failed to load Literature records: %s", exc)
        errors.append(("Literature", exc))
    if errors and not items:
        raise RuntimeError(f"Failed to load library: {errors}")
    return items


class _RecommendationLoader(QThread):
    """Background thread that fetches recommendations from the engine."""

    results_ready = Signal(list, int)
    load_failed = Signal(str, int)

    def __init__(self, engine: RecommendationEngine, n: int = 12, request_id: int = 0, filters: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self._engine = engine
        self._n = n
        self._request_id = request_id
        self._filters = dict(filters or {})
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            results = self._engine.get_recommendations(n=self._n, **self._filters)
            if not self._cancelled:
                self.results_ready.emit(results, self._request_id)
        except Exception as exc:
            if not self._cancelled:
                self.load_failed.emit(str(exc), self._request_id)


class _PosterLoader(QThread):
    """Background thread that downloads a poster image."""

    poster_ready = Signal(str, str)  # (url, cached_path)
    poster_failed = Signal(str)  # url

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._url = url

    def run(self) -> None:
        try:
            from animevault.services.poster import download_poster
            path = download_poster(self._url)
            if path:
                self.poster_ready.emit(self._url, path)
            else:
                self.poster_failed.emit(self._url)
        except Exception:
            self.poster_failed.emit(self._url)


class _PosterWorkerManager(QObject):
    """Manages poster download workers with safe ownership and cleanup."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active: set = set()
        self._pending_urls: set = set()
        self._shutting_down = False

    def request_poster(self, url: str, on_ready, on_failed) -> None:
        """Request a poster download. Deduplicates by URL."""
        if self._shutting_down or not url or url in self._pending_urls:
            return
        self._pending_urls.add(url)
        loader = _PosterLoader(url, self)
        self._active.add(loader)

        def _cleanup():
            self._active.discard(loader)
            self._pending_urls.discard(url)
            loader.deleteLater()

        def _safe_ready(u, p):
            if not self._shutting_down:
                on_ready(u, p)

        def _safe_failed(u):
            if not self._shutting_down:
                on_failed(u)

        loader.poster_ready.connect(_safe_ready)
        loader.poster_failed.connect(_safe_failed)
        loader.finished.connect(_cleanup)
        loader.start()

    def shutdown(self) -> None:
        """Mark as shutting down; workers complete in background."""
        self._shutting_down = True


# Application-level poster worker manager (singleton)
_app_poster_manager: Optional[_PosterWorkerManager] = None


def get_poster_manager() -> _PosterWorkerManager:
    global _app_poster_manager
    if _app_poster_manager is None:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        _app_poster_manager = _PosterWorkerManager(app)
    return _app_poster_manager


class RecommendationDialog(QDialog):
    """Modal dialog presenting personalized recommendations."""

    def __init__(self, parent=None, library_items: Optional[list] = None):
        super().__init__(parent)
        self.setWindowTitle("AnimeVault — Recommendations")
        self.setWindowFlags(Qt.WindowType.Window)
        self.setMinimumSize(760, 560)
        self.resize(1080, 760)
        self.setModal(False)
        if parent is not None and not parent.windowIcon().isNull():
            self.setWindowIcon(parent.windowIcon())
        else:
            icon_path = Path(__file__).resolve().parent.parent / "resources" / "media" / "app.ico"
            if icon_path.exists():
                self.setWindowIcon(QIcon(str(icon_path)))

        self._library_items = list(library_items or [])
        self._engine = RecommendationEngine(library_items=self._library_items)
        self._loader: Optional[_RecommendationLoader] = None
        self._current_results: list[RecommendationResult] = []
        self._loading = False
        self._request_id = 0
        self._active_request_id = 0
        self._poster_manager = get_poster_manager()
        self._closed = False

        self._build_ui()
        self._start_load()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Discover Your Next Favorite")
        title.setStyleSheet("font-size:18px; font-weight:bold;")
        header.addWidget(title)
        header.addStretch(1)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self._on_refresh_clicked)
        header.addWidget(self._refresh_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        header.addWidget(close_btn)
        root.addLayout(header)

        subtitle = QLabel("Personalized recommendations based on your library.")
        subtitle.setStyleSheet("color:gray; font-size:12px;")
        root.addWidget(subtitle)

        filter_row = QHBoxLayout()
        self._category_filter = QComboBox()
        self._category_filter.setObjectName("recommendationCategoryFilter")
        self._category_filter.addItem("All categories", "all")
        for category in ("action", "adventure", "comedy", "drama", "fantasy", "romance", "sci-fi", "slice of life", "supernatural", "thriller"):
            self._category_filter.addItem(category.title(), category)
        self._genre_filter = QComboBox()
        self._genre_filter.setObjectName("recommendationGenreFilter")
        self._genre_filter.addItems(["Any genre", "Action", "Adventure", "Comedy", "Drama", "Fantasy", "Romance", "Sci-fi", "Supernatural", "Thriller"])
        self._format_filter = QComboBox()
        self._format_filter.setObjectName("recommendationFormatFilter")
        self._format_filter.addItem("All formats", "all")
        for media_format in ("TV", "Movie", "OVA", "ONA", "Special"):
            self._format_filter.addItem(media_format, media_format)
        for label, control in (("Category", self._category_filter), ("Genre", self._genre_filter), ("Format", self._format_filter)):
            filter_row.addWidget(QLabel(label))
            filter_row.addWidget(control)
        from PySide6.QtWidgets import QSlider
        self._score_filter = QSlider(Qt.Orientation.Horizontal)
        self._score_filter.setObjectName("recommendationMinimumScore")
        self._score_filter.setRange(0, 100)
        self._score_filter.setMinimumWidth(130)
        self._score_label = QLabel("Minimum score: 0%")
        filter_row.addWidget(self._score_label)
        filter_row.addWidget(self._score_filter)
        filter_row.addStretch(1)
        root.addLayout(filter_row)
        self._category_filter.currentIndexChanged.connect(self._on_filters_changed)
        self._genre_filter.currentIndexChanged.connect(self._on_filters_changed)
        self._format_filter.currentIndexChanged.connect(self._on_filters_changed)
        self._score_filter.valueChanged.connect(self._on_filters_changed)

        self._status_label = QLabel("Loading recommendations…")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setStyleSheet("font-size:13px; padding:12px;")
        root.addWidget(self._status_label)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._content = QWidget()
        self._content_layout = QGridLayout(self._content)
        self._content_layout.setContentsMargins(8, 8, 8, 8)
        self._content_layout.setHorizontalSpacing(12)
        self._content_layout.setVerticalSpacing(12)
        self._card_widgets: list[QWidget] = []
        self._scroll.setWidget(self._content)
        root.addWidget(self._scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _on_refresh_clicked(self) -> None:
        if self._loading:
            return
        try:
            library_items = _load_library_items()
        except RuntimeError:
            library_items = []
        self._library_items = library_items
        self._engine = RecommendationEngine(library_items=self._library_items)
        self._start_load()

    def _on_filters_changed(self, *_args) -> None:
        value = self._score_filter.value()
        self._score_label.setText(f"Minimum score: {value}%")
        if not self._loading:
            self._start_load()

    def _current_filters(self) -> dict:
        genre = self._genre_filter.currentText()
        return {
            "category": self._category_filter.currentData() or "all",
            "genre_filter": "" if genre == "Any genre" else genre,
            "media_type_filter": self._format_filter.currentData() or "all",
            "min_score": self._score_filter.value() / 100.0,
        }

    def _start_load(self) -> None:
        if self._loading:
            return
        self._loading = True
        self._request_id += 1
        self._active_request_id = self._request_id
        self._refresh_btn.setEnabled(False)
        for control in (self._category_filter, self._genre_filter, self._format_filter, self._score_filter):
            control.setEnabled(False)
        self._status_label.setText("Loading recommendations…")
        self._status_label.setVisible(True)
        self._clear_cards()

        loader = _RecommendationLoader(self._engine, 12, self._active_request_id, self._current_filters(), None)
        self._loader = loader
        _active_rec_loaders.add(loader)
        loader.results_ready.connect(self._on_loaded)
        loader.load_failed.connect(self._on_failed)
        loader.finished.connect(self._on_thread_finished)
        loader.finished.connect(lambda worker=loader: _active_rec_loaders.discard(worker))
        loader.start()

    def _clear_cards(self) -> None:
        self._card_widgets = []
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _reflow_cards(self) -> None:
        if not self._card_widgets:
            return
        while self._content_layout.count():
            self._content_layout.takeAt(0)
        cell_width = 520
        columns = max(1, self._scroll.viewport().width() // cell_width)
        for index, card in enumerate(self._card_widgets):
            self._content_layout.addWidget(card, index // columns, index % columns)
        for column in range(columns):
            self._content_layout.setColumnStretch(column, 1)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._reflow_cards()

    def _on_loaded(self, results: list, request_id: int = 0) -> None:
        if self._closed:
            return
        if request_id != self._active_request_id:
            return
        self._current_results = list(results or [])
        if not self._current_results:
            # Determine the appropriate empty-state message from the engine
            # outcome, which distinguishes the different reasons a result list
            # can be empty: insufficient preference data, no external
            # candidates, provider/network failure, all items owned, or all
            # items filtered out.
            try:
                summary = self._engine.get_preference_summary()
                outcome = summary.get("recommendation_status", "")
                if outcome == "insufficient_preference_data":
                    msg = "Not enough library data yet. Add anime to your library to get started."
                elif outcome == "no_external_candidates":
                    msg = "No external recommendations found. Your library doesn't match any titles outside it yet."
                elif outcome == "provider_failure":
                    msg = "Recommendations could not be generated because of a provider or network error. Please try again later."
                elif outcome == "all_excluded_owned":
                    msg = "All discovered recommendations are already in your library."
                elif outcome == "all_excluded_filter":
                    msg = "Recommendations are filtered out by your current filters."
                else:
                    msg = "No recommendations available at this time."
            except Exception:
                msg = "No recommendations available at this time."
            self._status_label.setText(msg)
            self._status_label.setVisible(True)
            return
        if any(getattr(result, "is_cached", False) for result in self._current_results):
            self._status_label.setText("Showing cached Jikan candidates where available.")
            self._status_label.setVisible(True)
        else:
            self._status_label.setVisible(False)
        self._render_cards(self._current_results)

    def _on_failed(self, msg: str, request_id: int = 0) -> None:
        if self._closed:
            return
        if request_id != self._active_request_id:
            return
        self._status_label.setText(f"Failed to load recommendations: {msg}")
        self._status_label.setVisible(True)

    def _on_thread_finished(self) -> None:
        if self._closed:
            return
        self._loading = False
        self._refresh_btn.setEnabled(True)
        for control in (self._category_filter, self._genre_filter, self._format_filter, self._score_filter):
            control.setEnabled(True)
        if self._loader is not None:
            self._loader.deleteLater()
            self._loader = None

    def _render_cards(self, results: list) -> None:
        self._clear_cards()
        for r in results:
            card = _RecCard(r, self, self._poster_manager)
            card.add_requested.connect(self._on_add_to_library)
            card.details_requested.connect(self._on_view_details)
            self._card_widgets.append(card)
        self._reflow_cards()

    def _on_add_to_library(self, result: RecommendationResult) -> None:
        media_type = (result.media_type or "").strip().lower()
        try:
            if media_type in ("manga", "manhwa", "manhua"):
                existing = [l for l in Literature.all() if l.title.lower() == result.title.lower()]
                if existing:
                    QMessageBox.information(self, "Already in Library", f'"{result.title}" is already in your library.')
                    return
                Literature.create(title=result.title, category=media_type, status="plan_to_watch")
            else:
                existing = [a for a in Anime.all() if a.title.lower() == result.title.lower()]
                if existing:
                    QMessageBox.information(self, "Already in Library", f'"{result.title}" is already in your library.')
                    return
                Anime.create(title=result.title, status="plan_to_watch")
            QMessageBox.information(self, "Added", f'"{result.title}" added to your library.')
        except Exception as exc:
            QMessageBox.warning(self, "Error", f"Could not add: {exc}")

    def _on_view_details(self, result: RecommendationResult) -> None:
        dlg = _RecommendationDetailsDialog(result, self, self._poster_manager)
        dlg.exec()

    def refresh(self, library_items: Optional[list] = None) -> None:
        if library_items is not None:
            self._library_items = list(library_items)
            self._engine = RecommendationEngine(library_items=self._library_items)
        self._on_refresh_clicked()

    def closeEvent(self, event) -> None:
        self._closed = True
        if self._loader is not None:
            self._loader.cancel()
            self._loader = None
        super().closeEvent(event)


class _RecCard(QWidget):
    """Card rendering one recommendation result with poster."""

    add_requested = Signal(object)
    details_requested = Signal(object)

    def __init__(self, result: RecommendationResult, parent=None, poster_manager: Optional[_PosterWorkerManager] = None):
        super().__init__(parent)
        self._result = result
        self._poster_manager = poster_manager
        self._poster_label: Optional[QLabel] = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        poster = QLabel()
        poster.setFixedSize(70, 95)
        poster.setAlignment(Qt.AlignmentFlag.AlignCenter)
        poster.setStyleSheet("background:#f0f0f0; border-radius:4px; color:#aaa; border:1px solid #ddd;")
        poster.setText("...")
        url = self._result.poster_url or ""
        if url:
            if self._poster_manager is not None:
                self._poster_manager.request_poster(
                    url,
                    lambda u, p: self._on_poster_ready(u, p),
                    lambda u: self._on_poster_failed(u),
                )
        else:
            poster.setText("No poster")
        layout.addWidget(poster)
        self._poster_label = poster

        title = QLabel(self._result.title)
        title.setStyleSheet("font-weight:bold; font-size:14px;")
        title.setWordWrap(True)
        layout.addWidget(title)
        title_ja = getattr(self._result, "title_ja", "") or getattr(self._result, "title_japanese", "")
        if title_ja:
            japanese = QLabel(title_ja)
            japanese.setWordWrap(True)
            japanese.setStyleSheet("color:gray; font-size:11px;")
            layout.addWidget(japanese)

        details = [self._result.media_type or "—"]
        if self._result.episodes:
            details.append(f"{self._result.episodes} eps")
        details.append(f"{self._result.score:.0%}")
        meta = QLabel("  •  ".join(details))
        meta.setStyleSheet("color:gray; font-size:11px;")
        layout.addWidget(meta)

        if self._result.synopsis:
            synopsis = QLabel(self._result.synopsis)
            synopsis.setWordWrap(True)
            synopsis.setMaximumHeight(96)
            layout.addWidget(synopsis)

        if self._result.genres:
            genres = QLabel(", ".join(self._result.genres))
            genres.setStyleSheet("font-size:11px;")
            genres.setWordWrap(True)
            layout.addWidget(genres)

        if self._result.reasons:
            reasons = QLabel("Why: " + " • ".join(self._result.reasons))
            reasons.setStyleSheet("font-size:11px; color:gray;")
            reasons.setWordWrap(True)
            layout.addWidget(reasons)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add to Library")
        add_btn.clicked.connect(lambda: self.add_requested.emit(self._result))
        btn_row.addWidget(add_btn)
        view_btn = QPushButton("View Details")
        view_btn.clicked.connect(lambda: self.details_requested.emit(self._result))
        btn_row.addWidget(view_btn)
        layout.addLayout(btn_row)

    def _on_poster_ready(self, url: str, path: str) -> None:
        from PySide6.QtGui import QPixmap
        if self._poster_label is None:
            return
        pix = QPixmap(path)
        if not pix.isNull():
            scaled = pix.scaled(70, 95, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            self._poster_label.setPixmap(scaled)
            self._poster_label.setStyleSheet("background:transparent; border-radius:4px; border:1px solid #ddd;")
            self._poster_label.setText("")

    def _on_poster_failed(self, url: str) -> None:
        if self._poster_label is not None:
            self._poster_label.setText("No poster")


class _RecommendationDetailsDialog(QDialog):
    """Dedicated details dialog for a recommendation (no DB insertion needed)."""

    def __init__(self, result: RecommendationResult, parent=None, poster_manager: Optional[_PosterWorkerManager] = None):
        super().__init__(parent)
        self.setWindowTitle(result.title)
        self.setMinimumSize(400, 300)
        self.setModal(True)

        self._poster_manager = poster_manager
        self._poster_label: Optional[QLabel] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        title = QLabel(result.title)
        title.setStyleSheet("font-size:16px; font-weight:bold;")
        title.setWordWrap(True)
        layout.addWidget(title)

        meta = QLabel(f"{result.media_type or '—'}  •  Score: {result.score:.0%}")
        meta.setStyleSheet("color:gray; font-size:12px;")
        layout.addWidget(meta)

        if result.genres:
            genres = QLabel("Genres: " + ", ".join(result.genres))
            genres.setWordWrap(True)
            layout.addWidget(genres)

        if result.synopsis:
            synopsis = QLabel(result.synopsis)
            synopsis.setWordWrap(True)
            layout.addWidget(synopsis)

        if result.reasons:
            reasons = QLabel("Why recommended: " + " • ".join(result.reasons))
            reasons.setWordWrap(True)
            reasons.setStyleSheet("color:gray; font-size:11px;")
            layout.addWidget(reasons)

        if result.poster_url:
            poster = QLabel()
            poster.setFixedSize(100, 130)
            poster.setAlignment(Qt.AlignmentFlag.AlignCenter)
            poster.setStyleSheet("background:#f0f0f0; border-radius:4px;")
            poster.setText("...")
            if self._poster_manager is not None:
                self._poster_manager.request_poster(
                    result.poster_url,
                    lambda u, p: self._set_poster(poster, p),
                    lambda u: poster.setText("No poster"),
                )
            layout.addWidget(poster)
            self._poster_label = poster

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _set_poster(self, label: QLabel, path: str) -> None:
        from PySide6.QtGui import QPixmap
        pix = QPixmap(path)
        if not pix.isNull() and label is not None:
            scaled = pix.scaled(100, 130, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            label.setPixmap(scaled)
            label.setStyleSheet("background:transparent; border-radius:4px;")
            label.setText("")