"""Appearance controls for selecting and previewing registered themes."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap, QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from animevault.ui.theme import THEMES, ThemeManager


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
