"""Appearance controls for selecting and previewing registered themes."""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QPixmap, QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from animevault import __version__
from animevault.services.update import (
    UpdateInfo,
    check_for_updates,
    download_installer,
    launch_installer,
)
from animevault.ui.theme import THEMES, ThemeManager


class _UpdateWorker(QThread):
    """Keep network checks and installer downloads off the GUI thread."""

    result = Signal(object, object)

    def __init__(self, mode: str, info: UpdateInfo | None = None, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.info = info

    def run(self) -> None:
        try:
            if self.mode == "check":
                output = check_for_updates(__version__)
            else:
                if self.info is None:
                    raise RuntimeError("No release is selected for download.")
                output = download_installer(
                    self.info, Path(tempfile.gettempdir()) / "AnimeVaultUpdate"
                )
            self.result.emit(output, None)
        except Exception as exc:
            self.result.emit(None, str(exc))


class ThemeSettingsDialog(QDialog):
    """Grouped theme picker; selection is applied and saved immediately."""

    def __init__(self, parent=None, manager: ThemeManager | None = None):
        super().__init__(parent)
        self.manager = manager or ThemeManager.instance()
        self.setWindowTitle("Appearance — Theme")
        self.resize(560, 620)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Choose a theme. It is applied and saved immediately."))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search themes…")
        self.search.setObjectName("searchField")
        layout.addWidget(self.search)

        self.list = QListWidget()
        self.list.setObjectName("themeList")
        self._items: dict[str, QListWidgetItem] = {}
        self._groups: dict[str, QListWidgetItem] = {}
        for category in ("CORE", "ANIME", "GLASS", "SPECIAL"):
            group = QListWidgetItem(category)
            group.setFlags(Qt.ItemFlag.NoItemFlags)
            self._groups[category] = group
            self.list.addItem(group)
            for theme in (t for t in THEMES.values() if t.category == category):
                pixmap = QPixmap(34, 24)
                pixmap.fill(QColor(theme.background))
                item = QListWidgetItem(QIcon(pixmap), theme.name)
                item.setData(Qt.ItemDataRole.UserRole, theme.id)
                item.setToolTip(theme.description)
                self._items[theme.id] = item
                self.list.addItem(item)
        layout.addWidget(self.list, 1)

        self.description = QLabel()
        self.description.setWordWrap(True)
        layout.addWidget(self.description)
        self.reduce_effects = QCheckBox("Reduce Transparency & Effects")
        self.reduce_effects.setChecked(self.manager.reduce_effects)
        layout.addWidget(self.reduce_effects)

        update_group = QGroupBox("Software Updates")
        update_layout = QHBoxLayout(update_group)
        self.update_status = QLabel(f"Installed version: {__version__}")
        self.update_status.setWordWrap(True)
        update_layout.addWidget(self.update_status, 1)
        self.check_updates_button = QPushButton("Check for updates")
        self.check_updates_button.clicked.connect(self._check_for_updates)
        update_layout.addWidget(self.check_updates_button)
        layout.addWidget(update_group)

        self._update_worker: _UpdateWorker | None = None
        self._pending_update: UpdateInfo | None = None
        self.list.currentItemChanged.connect(self._selection_changed)
        self.search.textChanged.connect(self._filter)
        self.reduce_effects.toggled.connect(self.manager.set_reduce_effects)
        self.manager.theme_changed.connect(self._sync_selected)
        self._sync_selected(self.manager.theme_id)

    def _selection_changed(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            return
        theme_id = current.data(Qt.ItemDataRole.UserRole)
        if not theme_id:
            return
        self.manager.apply_theme(theme_id)
        self.description.setText(THEMES[theme_id].description)

    def _sync_selected(self, theme_id: str) -> None:
        for key, item in self._items.items():
            name = THEMES[key].name
            item.setText(("✓  " if key == theme_id else "     ") + name)
        item = self._items.get(theme_id)
        if item is not None:
            self.list.setCurrentItem(item)
            self.description.setText(THEMES[theme_id].description)

    def _filter(self, query: str) -> None:
        query = query.casefold().strip()
        for key, item in self._items.items():
            theme = THEMES[key]
            item.setHidden(query not in theme.name.casefold() and query not in theme.description.casefold())
        for category, group in self._groups.items():
            group.setHidden(not any(not self._items[k].isHidden() for k in THEMES if THEMES[k].category == category))

    def _check_for_updates(self) -> None:
        if self._update_worker is not None and self._update_worker.isRunning():
            return
        self.check_updates_button.setEnabled(False)
        self.update_status.setText("Checking GitHub Releases…")
        self._start_update_worker("check")

    def _start_update_worker(self, mode: str, info: UpdateInfo | None = None) -> None:
        worker = _UpdateWorker(mode, info, self)
        self._update_worker = worker
        worker.result.connect(self._update_finished)
        worker.start()

    def _update_finished(self, result, error) -> None:
        worker = self._update_worker
        mode = worker.mode if worker is not None else "check"
        self.check_updates_button.setEnabled(True)
        if error:
            self.update_status.setText(f"Update failed: {error}")
            self._pending_update = None
            return

        if mode == "check":
            if result is None:
                self.update_status.setText("No newer stable release found.")
                return
            info: UpdateInfo = result
            self._pending_update = info
            if not info.installer_url or not info.sha256:
                self.update_status.setText(
                    f'Version {info.version} is available, but has no digest-verified installer. '
                    f'<a href="{info.page_url}">View release</a>.'
                )
                self.update_status.setTextFormat(Qt.TextFormat.RichText)
                self.update_status.setOpenExternalLinks(True)
                return
            notes = info.notes.strip()[:1600] or "Release notes were not provided."
            choice = QMessageBox.question(
                self,
                "AnimeVault update available",
                f"Install AnimeVault {info.version}?\n\n{notes}\n\n"
                "The setup file will be downloaded over HTTPS and checked against its SHA-256 digest.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if choice == QMessageBox.StandardButton.Yes:
                self.check_updates_button.setEnabled(False)
                self.update_status.setText(f"Downloading and verifying version {info.version}…")
                self._start_update_worker("download", info)
            else:
                self.update_status.setText(f"Update {info.version} is available.")
            return

        info = self._pending_update
        if info is None or not info.sha256:
            self.update_status.setText("Update metadata is no longer available; check again.")
            return
        try:
            launch_installer(result, info.sha256)
        except Exception as exc:
            self.update_status.setText(f"Verified download could not be launched: {exc}")
            return
        self.update_status.setText(
            f"Version {info.version} setup launched. Follow its prompts to finish the update."
        )
        self._pending_update = None

    def closeEvent(self, event) -> None:  # noqa: N802
        worker = self._update_worker
        if worker is not None and worker.isRunning():
            self.update_status.setText("Please wait for the update operation to finish.")
            event.ignore()
            return
        super().closeEvent(event)
