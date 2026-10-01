"""Dialog for manually adding an anime entry."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
)

from animevault.models.anime import VALID_STATUSES, Anime


class AddAnimeDialog(QDialog):
    """Modal dialog that collects anime fields and returns a saved Anime.

    Usage::

        dlg = AddAnimeDialog(parent)
        if dlg.exec() == QDialog.Accepted:
            anime = dlg.anime  # persisted Anime object
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Anime")
        self.setModal(True)
        self.setMinimumWidth(400)

        self._build_form()

        # Button box
        buttons = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self._button_box = QDialogButtonBox(buttons)
        self._button_box.accepted.connect(self._on_accept)
        self._button_box.rejected.connect(self.reject)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self._form_widget)
        layout.addWidget(self._button_box)
        self.setLayout(layout)

        # Will be set when the user clicks OK
        self._anime: Anime | None = None

    # ── Form construction ─────────────────────────────────────────

    def _build_form(self) -> None:
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("e.g. Fullmetal Alchemist")
        self._title_edit.setClearButtonEnabled(True)

        self._title_ja_edit = QLineEdit()
        self._title_ja_edit.setPlaceholderText("e.g. 鋼の錬金術師")
        self._title_ja_edit.setClearButtonEnabled(True)

        self._episodes_spin = QSpinBox()
        self._episodes_spin.setRange(0, 9999)
        self._episodes_spin.setValue(0)

        self._status_combo = QComboBox()
        self._status_combo.addItems(list(VALID_STATUSES))

        self._score_edit = QLineEdit()
        self._score_edit.setPlaceholderText("0.0 – 10.0 (leave empty for none)")
        self._score_edit.setValidator(self._validator_doubles())

        self._notes_edit = QTextEdit()
        self._notes_edit.setPlaceholderText("Any notes you want to keep…")
        self._notes_edit.setFixedHeight(80)

        self._form_widget = QFormLayout()
        self._form_widget.addRow("Title *:", self._title_edit)
        self._form_widget.addRow("Japanese title:", self._title_ja_edit)
        self._form_widget.addRow("Episodes:", self._episodes_spin)
        self._form_widget.addRow("Status:", self._status_combo)
        self._form_widget.addRow("Score:", self._score_edit)
        self._form_widget.addRow("Notes:", self._notes_edit)

    @staticmethod
    def _validator_doubles():
        """Return a QDoubleValidator for score input (0.0–10.0)."""
        from PySide6.QtGui import QDoubleValidator

        v = QDoubleValidator(0.0, 10.0, 1)
        v.setNotation(QDoubleValidator.Notation.StandardNotation)
        return v

    # ── Accept logic ──────────────────────────────────────────────

    def _on_accept(self) -> None:
        """Validate inputs and persist the Anime record."""
        title = self._title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "Missing title", "Please enter a title.")
            self._title_edit.setFocus()
            return

        title_ja = self._title_ja_edit.text().strip()
        episodes = self._episodes_spin.value()
        status = self._status_combo.currentText()

        score_text = self._score_edit.text().strip()
        score: float | None = None
        if score_text:
            score = float(score_text)

        notes = self._notes_edit.toPlainText().strip()

        try:
            self._anime = Anime.create(
                title=title,
                title_ja=title_ja,
                episodes=episodes,
                status=status,
                score=score,
                notes=notes,
            )
        except ValueError as exc:
            QMessageBox.critical(self, "Validation error", str(exc))
            return

        self.accept()

    # ── Result ───────────────────────────────────────────────────

    @property
    def anime(self) -> Anime | None:
        """The persisted :class:`Anime`, or ``None`` if cancelled."""
        return self._anime
