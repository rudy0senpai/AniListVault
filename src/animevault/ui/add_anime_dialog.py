"""Dialog for adding or searching and importing an anime entry."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
)

from animevault.models.anime import VALID_STATUSES, Anime
from animevault.services.enrichment import merge_metadata_into_anime
from animevault.services.poster import download_poster
from animevault.services.providers.base import AnimeMetadata
from animevault.services.search import SearchService
from animevault.services.workers import SearchWorker


class AddAnimeDialog(QDialog):
    """Modal dialog that allows online searching or manual entry of anime."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Anime")
        self.setModal(True)
        self.resize(600, 680)

        self._search_service = SearchService()
        self._search_worker: Optional[SearchWorker] = None
        self._current_results: list[AnimeMetadata] = []
        self._selected_meta: Optional[AnimeMetadata] = None
        self._existing_anime: Optional[Anime] = None
        self._anime: Optional[Anime] = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        # ── Online Search Section ──────────────────────────────────
        search_box = QVBoxLayout()
        search_label = QLabel("<b>Search Online:</b> (enter name to auto-discover metadata)")
        search_box.addWidget(search_label)

        search_row = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Enter anime title (e.g. Naruto, Frieren, Steins;Gate)...")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.returnPressed.connect(self._on_search)

        self._search_button = QPushButton("Search")
        self._search_button.clicked.connect(self._on_search)

        search_row.addWidget(self._search_input)
        search_row.addWidget(self._search_button)
        search_box.addLayout(search_row)

        self._search_status_label = QLabel("")
        self._search_status_label.setStyleSheet("color: #666; font-size: 11px;")
        search_box.addWidget(self._search_status_label)

        # Candidates table
        self._results_table = QTableWidget(0, 5)
        self._results_table.setHorizontalHeaderLabels(["Title", "Type", "Year", "Eps", "Provider"])
        self._results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._results_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._results_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._results_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._results_table.itemSelectionChanged.connect(self._on_result_selected)
        self._results_table.setMaximumHeight(140)
        self._results_table.hide()
        search_box.addWidget(self._results_table)

        # Duplicate match alert banner
        self._dup_banner = QLabel("")
        self._dup_banner.setStyleSheet(
            "background: #eef6ff; border: 1px solid #c2e0ff; border-radius: 4px; padding: 6px; color: #004085;"
        )
        self._dup_banner.setWordWrap(True)
        self._dup_banner.hide()
        search_box.addWidget(self._dup_banner)

        layout.addLayout(search_box)

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep)

        # ── Form Fields ───────────────────────────────────────────
        self._build_form()
        layout.addLayout(self._form_layout)

        # ── Button Box ────────────────────────────────────────────
        buttons = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self._button_box = QDialogButtonBox(buttons)
        self._button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Save Anime")
        self._button_box.accepted.connect(self._on_accept)
        self._button_box.rejected.connect(self.reject)
        layout.addWidget(self._button_box)

        self.setLayout(layout)

    def _build_form(self) -> None:
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("Canonical title *")
        self._title_edit.setClearButtonEnabled(True)

        self._title_en_edit = QLineEdit()
        self._title_en_edit.setPlaceholderText("English title")
        self._title_en_edit.setClearButtonEnabled(True)

        self._title_ja_edit = QLineEdit()
        self._title_ja_edit.setPlaceholderText("Japanese / Native title")
        self._title_ja_edit.setClearButtonEnabled(True)

        self._episodes_spin = QSpinBox()
        self._episodes_spin.setRange(0, 9999)
        self._episodes_spin.setValue(0)

        self._status_combo = QComboBox()
        self._status_combo.addItems(list(VALID_STATUSES))

        self._score_edit = QLineEdit()
        self._score_edit.setPlaceholderText("0.0 – 10.0 (leave empty for none)")
        self._score_edit.setValidator(self._validator_doubles())

        self._genres_edit = QLineEdit()
        self._genres_edit.setPlaceholderText("Action, Adventure, Fantasy...")

        self._synopsis_edit = QTextEdit()
        self._synopsis_edit.setPlaceholderText("Synopsis / Description...")
        self._synopsis_edit.setFixedHeight(70)

        self._notes_edit = QTextEdit()
        self._notes_edit.setPlaceholderText("Your personal notes...")
        self._notes_edit.setFixedHeight(50)

        self._form_layout = QFormLayout()
        self._form_layout.addRow("Title *:", self._title_edit)
        self._form_layout.addRow("English title:", self._title_en_edit)
        self._form_layout.addRow("Japanese title:", self._title_ja_edit)
        self._form_layout.addRow("Episodes:", self._episodes_spin)
        self._form_layout.addRow("Watch status:", self._status_combo)
        self._form_layout.addRow("Personal score:", self._score_edit)
        self._form_layout.addRow("Genres:", self._genres_edit)
        self._form_layout.addRow("Synopsis:", self._synopsis_edit)
        self._form_layout.addRow("Personal notes:", self._notes_edit)

    @staticmethod
    def _validator_doubles():
        from PySide6.QtGui import QDoubleValidator
        v = QDoubleValidator(0.0, 10.0, 1)
        v.setNotation(QDoubleValidator.Notation.StandardNotation)
        return v

    # ── Search logic ──────────────────────────────────────────────

    def _on_search(self) -> None:
        query = self._search_input.text().strip()
        if not query:
            return

        self._search_button.setEnabled(False)
        self._search_status_label.setText(f"Searching online providers for '{query}'...")
        self._results_table.setRowCount(0)
        self._results_table.hide()
        self._dup_banner.hide()

        self._search_worker = SearchWorker(query, self._search_service, parent=self)
        self._search_worker.results_ready.connect(self._on_search_results)
        self._search_worker.search_error.connect(self._on_search_error)
        self._search_worker.start()

    def _on_search_results(self, results: list[AnimeMetadata]) -> None:
        self._search_button.setEnabled(True)
        self._current_results = results

        if not results:
            self._search_status_label.setText("No online results found. You can enter details manually below.")
            self._results_table.hide()
            return

        self._search_status_label.setText(f"Found {len(results)} candidate(s). Select one to auto-fill metadata:")
        self._results_table.setRowCount(len(results))
        for row_idx, r in enumerate(results):
            title_text = r.best_title()
            type_text = r.media_type or "TV"
            year_text = str(r.season_year) if r.season_year else (r.aired_from[:4] if r.aired_from else "-")
            eps_text = str(r.episodes) if r.episodes else "?"
            prov_text = r.source_provider.capitalize() if r.source_provider else "API"

            self._results_table.setItem(row_idx, 0, QTableWidgetItem(title_text))
            self._results_table.setItem(row_idx, 1, QTableWidgetItem(type_text))
            self._results_table.setItem(row_idx, 2, QTableWidgetItem(year_text))
            self._results_table.setItem(row_idx, 3, QTableWidgetItem(eps_text))
            self._results_table.setItem(row_idx, 4, QTableWidgetItem(prov_text))

        self._results_table.show()
        self._results_table.selectRow(0)

    def _on_search_error(self, err: str) -> None:
        self._search_button.setEnabled(True)
        self._search_status_label.setText(f"Search provider error ({err}). Manual entry available below.")

    def _on_result_selected(self) -> None:
        selected_rows = self._results_table.selectionModel().selectedRows()
        if not selected_rows:
            return

        idx = selected_rows[0].row()
        if 0 <= idx < len(self._current_results):
            meta = self._current_results[idx]
            self._selected_meta = meta

            # Populate form with candidate metadata
            self._title_edit.setText(meta.best_title())
            if meta.title_en:
                self._title_en_edit.setText(meta.title_en)
            if meta.title_ja:
                self._title_ja_edit.setText(meta.title_ja)
            if meta.episodes:
                self._episodes_spin.setValue(meta.episodes)
            if meta.genres:
                self._genres_edit.setText(", ".join(meta.genres))
            if meta.synopsis:
                self._synopsis_edit.setPlainText(meta.synopsis)

            # Check duplicate in library
            existing = self._search_service.find_duplicate_in_library(meta)
            self._existing_anime = existing
            if existing:
                self._dup_banner.setText(
                    f"ℹ Already in your library as '{existing.title}' (ID: #{existing.id}). "
                    "Saving will enrich missing metadata without modifying your status or score."
                )
                self._dup_banner.show()
                # Mirror existing personal fields
                self._status_combo.setCurrentText(existing.status)
                if existing.score is not None:
                    self._score_edit.setText(str(existing.score))
                if existing.notes:
                    self._notes_edit.setPlainText(existing.notes)
            else:
                self._dup_banner.hide()

    # ── Accept logic ──────────────────────────────────────────────

    def _on_accept(self) -> None:
        title = self._title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "Missing title", "Please enter a title.")
            self._title_edit.setFocus()
            return

        title_en = self._title_en_edit.text().strip()
        title_ja = self._title_ja_edit.text().strip()
        episodes = self._episodes_spin.value()
        status = self._status_combo.currentText()

        score_text = self._score_edit.text().strip()
        score: Optional[float] = None
        if score_text:
            score = float(score_text)

        notes = self._notes_edit.toPlainText().strip()
        genres = [g.strip() for g in self._genres_edit.text().split(",") if g.strip()]
        synopsis = self._synopsis_edit.toPlainText().strip()

        try:
            if self._existing_anime:
                # Merge into existing record
                anime = self._existing_anime
                anime.title = title
                if title_en:
                    anime.title_en = title_en
                if title_ja:
                    anime.title_ja = title_ja
                if episodes:
                    anime.episodes = episodes
                anime.status = status
                anime.score = score
                anime.notes = notes
                if synopsis and not anime.synopsis:
                    anime.synopsis = synopsis
                if genres and not anime.genres:
                    anime.genres = genres

                if self._selected_meta:
                    merge_metadata_into_anime(anime, self._selected_meta)
                    if self._selected_meta.poster_url and not anime.poster_path:
                        local_p = download_poster(self._selected_meta.poster_url)
                        if local_p:
                            anime.poster_path = local_p

                anime.save()
                self._anime = anime
            else:
                # Create new anime record
                anime = Anime(
                    id=None,
                    title=title,
                    title_ja=title_ja,
                    episodes=episodes,
                    status=status,
                    score=score,
                    notes=notes,
                    title_en=title_en,
                    synopsis=synopsis,
                    genres=genres,
                )

                if self._selected_meta:
                    merge_metadata_into_anime(anime, self._selected_meta)
                    if self._selected_meta.poster_url:
                        local_p = download_poster(self._selected_meta.poster_url)
                        if local_p:
                            anime.poster_path = local_p

                anime.save()
                self._anime = anime

        except ValueError as exc:
            QMessageBox.critical(self, "Validation error", str(exc))
            return

        self.accept()

    @property
    def anime(self) -> Optional[Anime]:
        return self._anime
