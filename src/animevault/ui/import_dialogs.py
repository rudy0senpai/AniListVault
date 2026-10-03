"""Import flows: preview dialogs for XLSX and SQL, then batch import."""

from __future__ import annotations

import logging
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QVBoxLayout,
)

from animevault.ui.theme import DANGER, TEXT_MUTED, TEXT_SECONDARY, WARNING

logger = logging.getLogger(__name__)


def _bullets(parent, title: str, mapped: list, unmapped: list) -> QListWidget:
    """A list showing mapped and unmapped columns explicitly."""
    listing = QListWidget()
    for name in mapped:
        item = QListWidgetItem(f"✓  {name}")
        item.setForeground(Qt.GlobalColor.green)
        listing.addItem(item)
    for name in unmapped:
        item = QListWidgetItem(f"•  {name}  (unmapped)")
        item.setForeground(Qt.GlobalColor.yellow)
        listing.addItem(item)
    return listing


def run_xlsx_import_flow(parent, path: str, on_done: Optional[Callable] = None) -> None:
    """Preview an XLSX, then import it if the user confirms."""
    from animevault.services.importers.xlsx_preview import preview_xlsx
    from animevault.services.importers.xlsx_importer import import_drafts

    preview = preview_xlsx(path)
    if not preview.ok:
        QMessageBox.critical(parent, "Import Failed", preview.error)
        return

    dialog = QDialog(parent)
    dialog.setWindowTitle("Import Anime Library")
    dialog.setMinimumWidth(520)
    layout = QVBoxLayout(dialog)

    layout.addWidget(QLabel(f"<b>File:</b> {preview.path.name}"))
    layout.addWidget(QLabel(f"<b>Sheet:</b> {preview.sheet_name}"))
    layout.addWidget(QLabel(f"<b>Rows detected:</b> {preview.total_rows}"))
    layout.addWidget(QLabel(preview.summary()))

    if not preview.has_title_column:
        QMessageBox.warning(
            dialog,
            "No title column",
            "No column could be recognised as a title, so nothing can be imported.\n\n"
            f"Unmapped columns: {', '.join(preview.unmapped_columns) or 'none'}",
        )
        return

    layout.addWidget(QLabel("<b>Mapped fields / unmapped columns:</b>"))
    layout.addWidget(
        _bullets(dialog, "Mapping", preview.mapped_columns, preview.unmapped_columns)
    )

    if preview.invalid_tier_errors:
        warning = QLabel(
            f"{len(preview.invalid_tier_errors)} row(s) have an invalid tier value "
            "and will be imported as unassigned."
        )
        warning.setStyleSheet(f"color:{WARNING};")
        warning.setWordWrap(True)
        layout.addWidget(warning)

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
    )
    buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Import")
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    if dialog.exec() != QDialog.DialogCode.Accepted:
        return

    drafts = preview.parsed.drafts if preview.parsed else []
    progress = QProgressDialog("Importing…", "Cancel", 0, len(drafts), parent)
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(150)

    def on_progress(done: int, total: int, stats) -> None:
        progress.setValue(done)
        progress.setLabelText(
            f"Importing {done} / {total}\n"
            f"Added: {stats.added}  Updated: {stats.updated}  "
            f"Duplicates: {stats.duplicates}  Invalid: {stats.invalid}"
        )

    result = import_drafts(
        drafts,
        progress=on_progress,
        should_cancel=lambda: progress.wasCanceled(),
    )
    progress.close()

    stats = result.stats
    message = (
        "Import complete\n\n"
        f"Total rows: {stats.total}\n"
        f"Added: {stats.added}\n"
        f"Updated: {stats.updated}\n"
        f"Skipped: {stats.duplicates}\n"
        f"Invalid: {stats.invalid}"
    )
    if result.needs_enrichment:
        message += f"\n\n{len(result.needs_enrichment)} entries require metadata enrichment."

    if result.needs_enrichment:
        box = QMessageBox(parent)
        box.setWindowTitle("Import complete")
        box.setText(message)
        enrich = box.addButton("Enrich Now", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is enrich and on_done is not None:
            on_done()
    else:
        QMessageBox.information(parent, "Import complete", message)
        if on_done is not None:
            on_done()


def run_sql_import_flow(parent, path: str, on_done: Optional[Callable] = None) -> None:
    """Preview a SQL dump, offer score→tier conversion, then import."""
    from animevault.services.importers.sql_importer import import_sql, preview_sql

    preview = preview_sql(path)
    if not preview.ok:
        QMessageBox.critical(parent, "Import Failed", preview.error)
        return

    dialog = QDialog(parent)
    dialog.setWindowTitle("SQL Import")
    dialog.setMinimumWidth(520)
    layout = QVBoxLayout(dialog)

    layout.addWidget(QLabel(f"<b>Source:</b> {preview.path.name}"))
    layout.addWidget(QLabel(f"<b>Tables detected:</b> {', '.join(preview.tables) or 'none'}"))
    layout.addWidget(
        QLabel(f"<b>Records:</b> anime: {preview.row_counts.get('anime', 0)}")
    )
    layout.addWidget(
        QLabel(
            f"<b>Schema version:</b> {preview.schema_version or 'unknown'} → current"
        )
    )

    if preview.rejected:
        note = QLabel(
            f"{len(preview.rejected)} statement(s) were refused for safety:\n"
            + "\n".join(f"  • {r}" for r in preview.rejected[:6])
        )
        note.setStyleSheet(f"color:{WARNING};")
        note.setWordWrap(True)
        layout.addWidget(note)

    convert = False
    if preview.needs_migration:
        warn = QLabel(
            "Migration required: this dump uses the legacy <b>score</b> field.\n"
            "The current version uses <b>Tier</b>.\n\n"
            "Scores are NOT converted unless you choose to."
        )
        warn.setStyleSheet(f"color:{WARNING};")
        warn.setWordWrap(True)
        layout.addWidget(warn)

        choice = QMessageBox(parent)
        choice.setWindowTitle("Migration required")
        choice.setText(
            "This dump uses the legacy score field.\n\n"
            "Import without scores (tier stays unassigned), or convert "
            "9–10 → SSS, 8–8.9 → SS, 7–7.9 → S, and so on?"
        )
        without = choice.addButton("Import without scores", QMessageBox.ButtonRole.AcceptRole)
        with_scores = choice.addButton("Convert scores to tiers", QMessageBox.ButtonRole.DestructiveRole)
        choice.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        choice.exec()
        clicked = choice.clickedButton()
        if clicked is None or clicked == choice.button(
            QMessageBox.StandardButton.Cancel
        ):
            return
        convert = clicked is with_scores

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
    )
    buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Import")
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    if dialog.exec() != QDialog.DialogCode.Accepted:
        return

    progress = QProgressDialog("Importing SQL dump…", "Cancel", 0, 0, parent)
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(150)

    result = import_sql(
        path,
        convert_scores=convert,
        progress=lambda done, total: progress.setValue(done),
        should_cancel=lambda: progress.wasCanceled(),
    )
    progress.close()

    message = (
        "Import complete\n\n"
        f"Added: {result.added}\n"
        f"Updated: {result.updated}\n"
        f"Duplicates: {result.duplicates}\n"
        f"Invalid: {result.invalid}"
    )
    if result.notes:
        message += "\n\n" + "\n".join(result.notes[:3])
    QMessageBox.information(parent, "Import complete", message)
    if on_done is not None:
        on_done()