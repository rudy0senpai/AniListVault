"""Optional Google account dialog.

Everything here is opt-in: AnimeVault never asks to connect, and the whole
feature is hidden when no OAuth client id has been configured. The dialog
is reachable from Tools → Cloud Sync.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from animevault.services import account as account_mod
from animevault.services import sync_service

logger = logging.getLogger(__name__)


class AccountDialog(QDialog):
    """Connect a Google account, or manage the sync that follows."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Cloud Sync")
        self.setModal(True)
        self.setMinimumWidth(440)

        self._account = account_mod.load_account()
        self._build_ui()

    # ── Layout ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self._status = QLabel()
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._detail = QLabel()
        self._detail.setWordWrap(True)
        self._detail.setStyleSheet("color:#9aa7b4; font-size:12px;")
        layout.addWidget(self._detail)

        self._include_private = QCheckBox(
            "Include entries marked private"
        )
        self._include_private.setToolTip(
            "Private entries normally stay on this machine only. Tick this "
            "to upload them too."
        )
        layout.addWidget(self._include_private)

        buttons_row = QHBoxLayout()
        self._push_button = QPushButton("Upload Library")
        self._push_button.clicked.connect(self._on_push)
        buttons_row.addWidget(self._push_button)

        self._pull_button = QPushButton("Download Library")
        self._pull_button.clicked.connect(self._on_pull)
        buttons_row.addWidget(self._pull_button)
        layout.addLayout(buttons_row)

        self._disconnect_button = QPushButton("Disconnect Account")
        self._disconnect_button.setObjectName("dangerButton")
        self._disconnect_button.clicked.connect(self._on_disconnect)
        layout.addWidget(self._disconnect_button)

        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

        self._refresh()

    def _refresh(self) -> None:
        """Show the current state and enable only what is possible."""
        self._account = account_mod.load_account()

        if not account_mod.is_configured():
            self._status.setText("Cloud sync is not set up on this build.")
            self._detail.setText(account_mod.requires_client_id())
            for widget in (
                self._push_button, self._pull_button,
                self._disconnect_button, self._include_private,
            ):
                widget.setEnabled(False)
            return

        if self._account.connected:
            self._status.setText(f"Connected as {self._account.email}")
            last = self._account.last_sync or "never"
            self._detail.setText(f"Last synced: {last}")
            self._push_button.setEnabled(True)
            self._pull_button.setEnabled(True)
            self._disconnect_button.setEnabled(True)
        else:
            self._status.setText("Not connected.")
            self._detail.setText(
                "Connect a Google account to keep your library available "
                "on every machine. This is optional — AnimeVault works "
                "fully offline without it."
            )
            self._push_button.setEnabled(False)
            self._pull_button.setEnabled(False)
            self._disconnect_button.setEnabled(False)

    # ── Actions ────────────────────────────────────────────────────

    def _require_connection(self) -> bool:
        if not self._account.connected:
            QMessageBox.information(
                self, "Not connected",
                "Connect a Google account first.",
            )
            return False
        return True

    def _on_push(self) -> None:
        if not self._require_connection():
            return
        private = self._include_private.isChecked()
        if private:
            reply = QMessageBox.question(
                self, "Include private entries?",
                "Entries marked private will be uploaded to your Drive "
                "and leave this machine.\n\nContinue?",
                QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
                QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        result = sync_service.push(include_private=private)
        self._report(result)

    def _on_pull(self) -> None:
        if not self._require_connection():
            return
        reply = QMessageBox.question(
            self, "Download library?",
            "Entries already on this machine are kept.\n\n"
            "Values already set here are not overwritten unless you "
            "clear them first. Continue?",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        result = sync_service.pull(overwrite=False)
        self._report(result)

    def _on_disconnect(self) -> None:
        reply = QMessageBox.question(
            self, "Disconnect",
            "Disconnect this Google account?\n\n"
            "Your local library is not deleted, and anything already in "
            "Drive stays there.",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        account_mod.disconnect()
        self._refresh()

    def _report(self, result: sync_service.SyncResult) -> None:
        if result.ok:
            message = result.message
            if result.skipped_private:
                message += (
                    f"\n\n{result.skipped_private} private entr"
                    f"{'y was' if result.skipped_private == 1 else 'ies were'} "
                    "left on this machine."
                )
            QMessageBox.information(self, "Cloud Sync", message)
        else:
            QMessageBox.warning(self, "Cloud Sync failed", result.message)
        self._refresh()

        parent = self.parent()
        if parent is not None and hasattr(parent, "refresh"):
            parent.refresh()
