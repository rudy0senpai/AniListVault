"""Add / Edit dialog for Anime and literature.

The primary workflow needs only a title: search a provider, pick a
candidate, and the metadata is fetched automatically.  Manual entry stays
available as a fallback, and the personal fields (status, tier, progress,
notes) are always editable.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from animevault.media_types import (
    CATEGORY_LABELS,
    MEDIA_ANIME,
    is_literature,
    status_labels,
)
from animevault.models.anime import VALID_STATUSES
from animevault.models.literature import Literature
from animevault.tiers import TIERS
from animevault.ui.theme import ACCENT, TEXT_MUTED, TEXT_SECONDARY

logger = logging.getLogger(__name__)


def _tier_combo(include_unassigned: bool = True) -> QComboBox:
    combo = QComboBox()
    if include_unassigned:
        combo.addItem("—", "")
    for tier in TIERS:
        combo.addItem(tier, tier)
    combo.setCurrentIndex(0)
    return combo


def _set_tier(combo: QComboBox, tier: Optional[str]) -> None:
    if not tier:
        combo.setCurrentIndex(0)
        return
    index = combo.findData(tier)
    combo.setCurrentIndex(index if index >= 0 else 0)


class AddMediaDialog(QDialog):
    """Search-driven add/edit dialog for any media category."""

    def __init__(self, category: str = MEDIA_ANIME, parent=None, existing=None) -> None:
        super().__init__(parent)
        self._category = category
        self._existing = existing
        self._literature = is_literature(category)
        self._result_item = None

        self.setWindowTitle(
            f"{'Edit' if existing else 'Add'} {CATEGORY_LABELS[category]}"
        )
        self.setModal(True)
        self.setMinimumWidth(560)

        self._tabs = QTabWidget()

        layout = QVBoxLayout()
        layout.addWidget(self._tabs)
        layout.addWidget(self._build_buttons())
        self.setLayout(layout)

        self._build_search_tab()
        self._build_manual_tab()

        if existing is not None:
            self._load_existing(existing)

    # ── Tabs ───────────────────────────────────────────────────────

    def _build_search_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        hint = QLabel(
            f"Enter just a title — AnimeVault finds everything else."
        )
        hint.setStyleSheet(f"color:{TEXT_SECONDARY};")
        layout.addWidget(hint)

        search_row = QHBoxLayout()
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText(
            f"Search {CATEGORY_LABELS[self._category]}..."
        )
        self._search_edit.returnPressed.connect(self._do_search)
        search_row.addWidget(self._search_edit, 1)

        self._search_button = QPushButton("Search")
        self._search_button.setObjectName("primaryButton")
        self._search_button.clicked.connect(self._do_search)
        search_row.addWidget(self._search_button)
        layout.addLayout(search_row)

        self._results = QListWidget()
        self._results.itemDoubleClicked.connect(lambda _: self._accept_candidate())
        self._results.setMinimumHeight(240)
        layout.addWidget(self._results)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet(f"color:{TEXT_MUTED};")
        layout.addWidget(self._status_label)

        self._tabs.addTab(page, "Search")

    def _build_manual_tab(self) -> None:
        page = QWidget()
        form = QFormLayout(page)
        form.setSpacing(9)
        form.setContentsMargins(14, 14, 14, 14)

        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("Required")
        form.addRow("Title *:", self._title_edit)

        if self._literature:
            self._category_combo = QComboBox()
            self._category_combo.addItems(
                [
                    CATEGORY_LABELS["manga"],
                    CATEGORY_LABELS["manhwa"],
                    CATEGORY_LABELS["manhua"],
                ]
            )
            self._category_combo.setCurrentText(CATEGORY_LABELS[self._category])
            form.addRow("Category:", self._category_combo)

            self._chapters_spin = QSpinBox()
            self._chapters_spin.setRange(0, 99999)
            form.addRow("Chapters:", self._chapters_spin)

            self._chapters_read_spin = QSpinBox()
            self._chapters_read_spin.setRange(0, 99999)
            form.addRow("Chapters read:", self._chapters_read_spin)

            self._volumes_spin = QSpinBox()
            self._volumes_spin.setRange(0, 9999)
            form.addRow("Volumes:", self._volumes_spin)
        else:
            self._episodes_spin = QSpinBox()
            self._episodes_spin.setRange(0, 99999)
            form.addRow("Episodes:", self._episodes_spin)

            self._episodes_watched_spin = QSpinBox()
            self._episodes_watched_spin.setRange(0, 99999)
            form.addRow("Episodes watched:", self._episodes_watched_spin)

        # Status uses literature wording when relevant.
        self._status_combo = QComboBox()
        labels = status_labels(self._category)
        for value in VALID_STATUSES:
            self._status_combo.addItem(labels.get(value, value.title()), value)
        form.addRow("Status:", self._status_combo)

        self._tier_combo = _tier_combo()
        form.addRow("Tier:", self._tier_combo)

        self._favorite_check = QCheckBox("Favorite")
        form.addRow("", self._favorite_check)

        self._notes_edit = QTextEdit()
        self._notes_edit.setFixedHeight(72)
        self._notes_edit.setPlaceholderText("Personal notes…")
        form.addRow("Notes:", self._notes_edit)

        self._tabs.addTab(page, "Manual Entry")

    def _build_buttons(self) -> QDialogButtonBox:
        buttons = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        box = QDialogButtonBox(buttons)
        box.accepted.connect(self._on_save)
        box.rejected.connect(self.reject)
        return box

    # ── Search ─────────────────────────────────────────────────────

    def _do_search(self) -> None:
        """Run a provider search in a background thread."""
        query = self._search_edit.text().strip()
        if not query:
            return

        self._results.clear()
        self._status_label.setText("Searching…")
        self._search_button.setEnabled(False)

        from animevault.ui.workers import LiteratureSearchWorker, SearchWorker

        if self._literature:
            worker = LiteratureSearchWorker(query, parent=self)
            worker.results_ready.connect(self._on_literature_results)
            worker.search_error.connect(self._on_search_error)
            worker.finished.connect(lambda: self._search_button.setEnabled(True))
        else:
            worker = SearchWorker(query, parent=self)
            worker.results_ready.connect(self._on_anime_results)
            worker.search_error.connect(self._on_search_error)
            worker.finished.connect(lambda: self._search_button.setEnabled(True))
        self._search_worker = worker
        worker.start()

    def _on_search_error(self, message: str) -> None:
        self._status_label.setText(f"Search failed: {message}")
        self._results.clear()

    def _on_anime_results(self, results: list) -> None:
        self._results.clear()
        for meta in results:
            bits = " · ".join(
                x for x in (
                    meta.media_type,
                    f"{meta.episodes} ep" if meta.episodes else "",
                    meta.source_provider,
                ) if x
            )
            item = QListWidgetItem(f"{meta.best_title()}\n    {bits}")
            item.setData(Qt.ItemDataRole.UserRole, meta)
            self._results.addItem(item)
        self._status_label.setText(
            f"{len(results)} result(s)" if results else "No results found."
        )

    def _on_literature_results(self, results: list) -> None:
        self._results.clear()
        for meta in results:
            bits = " · ".join(
                x for x in (
                    meta.category.capitalize(),
                    f"{meta.chapters} ch" if meta.chapters else "",
                    meta.source_provider,
                ) if x
            )
            item = QListWidgetItem(f"{meta.display_title()}\n    {bits}")
            item.setData(Qt.ItemDataRole.UserRole, meta)
            self._results.addItem(item)
        self._status_label.setText(
            f"{len(results)} result(s)" if results else "No results found."
        )

    def _accept_candidate(self) -> None:
        """Save the highlighted provider result as a new entry."""
        row = self._results.currentRow()
        if row < 0:
            return
        meta = self._results.item(row).data(Qt.ItemDataRole.UserRole)
        if meta is None:
            return
        try:
            self._result_item = self._save_from_metadata(meta)
        except Exception as exc:
            QMessageBox.critical(self, "Could not save", str(exc))
            return
        self.accept()

    # ── Saving ─────────────────────────────────────────────────────

    def _save_from_metadata(self, meta):
        """Persist a provider result, then apply any manual personal fields."""
        from animevault.services.poster import download_poster

        if self._literature:
            item = Literature(
                id=None,
                title=meta.display_title(),
                category=self._category,
                title_en=getattr(meta, "title_en", "") or "",
                title_native=getattr(meta, "title_native", "") or "",
                synonyms=list(getattr(meta, "synonyms", []) or []),
                format=getattr(meta, "format", "") or "",
                synopsis=getattr(meta, "synopsis", "") or "",
                genres=list(getattr(meta, "genres", []) or []),
                authors=list(getattr(meta, "authors", []) or []),
                artists=list(getattr(meta, "artists", []) or []),
                chapters=int(getattr(meta, "chapters", 0) or 0),
                volumes=int(getattr(meta, "volumes", 0) or 0),
                started_at=getattr(meta, "started_at", "") or "",
                ended_at=getattr(meta, "ended_at", "") or "",
                origin_country=getattr(meta, "origin_country", "") or "",
                cover_url=getattr(meta, "cover_url", "") or "",
                anilist_id=getattr(meta, "anilist_id", None),
                mal_id=getattr(meta, "mal_id", None),
                source_provider=getattr(meta, "source_provider", "anilist"),
                status=self._status_combo.currentData()
                or "watching",
                tier=self._tier_combo.currentData() or None,
            )
            if item.cover_url:
                local = download_poster(item.cover_url)
                if local:
                    item.cover_path = local
            item.save()
            return item

        from animevault.services.enrichment import anime_from_metadata

        item = anime_from_metadata(meta)
        item.status = self._status_combo.currentData() or "plan_to_watch"
        item.tier = self._tier_combo.currentData() or None
        if meta.poster_url:
            local = download_poster(meta.poster_url)
            if local:
                item.poster_path = local
        item.save()
        return item

    def _on_save(self) -> None:
        """Save from the manual tab (or the selected search result)."""
        if self._results.currentRow() >= 0 and self._tabs.currentIndex() == 0:
            self._accept_candidate()
            return

        title = self._title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "Missing title", "Please enter a title.")
            self._tabs.setCurrentIndex(1)
            self._title_edit.setFocus()
            return

        status = self._status_combo.currentData() or "plan_to_watch"
        tier = self._tier_combo.currentData() or None
        notes = self._notes_edit.toPlainText().strip()
        favorite = self._favorite_check.isChecked()

        if self._literature:
            category = self._category_combo.currentText().lower()
            if self._existing is not None and isinstance(self._existing, Literature):
                item = self._existing
                item.category = category
                item.chapters = self._chapters_spin.value()
                item.chapters_read = self._chapters_read_spin.value()
                item.volumes = self._volumes_spin.value()
            else:
                item = Literature(
                    id=None, title=title, category=category,
                    chapters=self._chapters_spin.value(),
                    chapters_read=self._chapters_read_spin.value(),
                    volumes=self._volumes_spin.value(),
                )
            item.status = status
            item.tier = tier
            item.notes = notes
            item.favorite = favorite
            item.save()
        else:
            from animevault.models.anime import Anime

            if self._existing is not None and isinstance(self._existing, Anime):
                item = self._existing
            else:
                item = Anime(id=None, title=title)
            item.episodes = self._episodes_spin.value()
            item.episodes_watched = self._episodes_watched_spin.value()
            item.status = status
            item.tier = tier
            item.notes = notes
            item.favorite = favorite
            item.save()

        self._result_item = item
        self.accept()

    # ── Existing item ──────────────────────────────────────────────

    def _load_existing(self, item) -> None:
        """Pre-fill the manual tab from *item* and open it directly."""
        self._tabs.setCurrentIndex(1)
        self._title_edit.setText(item.title)
        self._search_edit.setText(item.title)

        index = self._status_combo.findData(item.status)
        if index >= 0:
            self._status_combo.setCurrentIndex(index)
        _set_tier(self._tier_combo, getattr(item, "tier", None))
        self._favorite_check.setChecked(bool(getattr(item, "favorite", False)))
        self._notes_edit.setPlainText(getattr(item, "notes", "") or "")

        if self._literature and isinstance(item, Literature):
            cat_index = self._category_combo.findText(
                CATEGORY_LABELS.get(item.category, "Manga")
            )
            if cat_index >= 0:
                self._category_combo.setCurrentIndex(cat_index)
            self._chapters_spin.setValue(item.chapters or 0)
            self._chapters_read_spin.setValue(item.chapters_read or 0)
            self._volumes_spin.setValue(item.volumes or 0)
        elif not self._literature and hasattr(item, "episodes"):
            self._episodes_spin.setValue(item.episodes or 0)
            self._episodes_watched_spin.setValue(item.episodes_watched or 0)

    @property
    def result_item(self):
        return self._result_item