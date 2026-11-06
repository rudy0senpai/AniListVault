"""Appearance controls for selecting and previewing registered themes."""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QSettings, QSize, QRect
from PySide6.QtGui import QColor, QPixmap, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QBoxLayout,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from animevault import __version__

from animevault.ui.theme import THEMES, ThemeManager


class ThemeSettingsDialog(QDialog):
    """Grouped theme picker; selection is applied and saved immediately."""

    def __init__(self, parent=None, manager: ThemeManager | None = None):
        super().__init__(parent)
        self.manager = manager or ThemeManager.instance()
        self.setObjectName("appearanceSettingsDialog")
        self.setWindowTitle("Appearance & Theme")
        self.setSizeGripEnabled(True)
        self._set_initial_geometry(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 16)
        outer.setSpacing(14)

        heading = QLabel("Appearance & Theme")
        heading.setObjectName("settingsTitle")
        subtitle = QLabel("Choose a palette, preview it, and manage your theme settings.")
        subtitle.setObjectName("settingsSubtitle")
        subtitle.setWordWrap(True)
        outer.addWidget(heading)
        outer.addWidget(subtitle)

        self.content_scroll = QScrollArea(self)
        self.content_scroll.setObjectName("settingsScrollArea")
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("settingsContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 4, 0, 8)
        content_layout.setSpacing(18)
        self.content_scroll.setWidget(content)
        outer.addWidget(self.content_scroll, 1)

        theme_heading = QLabel("Theme selection")
        theme_heading.setObjectName("settingsSectionTitle")
        content_layout.addWidget(theme_heading)

        self._picker_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self._picker_layout.setContentsMargins(0, 0, 0, 0)
        self._picker_layout.setSpacing(16)
        picker = QWidget()
        picker.setObjectName("themePicker")
        picker.setLayout(self._picker_layout)
        content_layout.addWidget(picker)

        list_column = QWidget()
        list_layout = QVBoxLayout(list_column)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(10)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search themes…")
        self.search.setAccessibleName("Search themes")
        self.search.setObjectName("searchField")
        self.search.setMinimumHeight(42)
        list_layout.addWidget(self.search)

        self.list = QListWidget()
        self.list.setObjectName("themeList")
        self.list.setAccessibleName("Available themes")
        self.list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setUniformItemSizes(True)
        available = self._available_geometry()
        self.list.setMinimumHeight(min(280, max(190, int(available.height() * 0.30))))
        self._items: dict[str, QListWidgetItem] = {}
        self._groups: dict[str, QListWidgetItem] = {}
        row_height = max(38, self.fontMetrics().height() + 18)
        for category in ("CORE", "ANIME", "GLASS", "SPECIAL"):
            group = QListWidgetItem(category)
            group.setFlags(Qt.ItemFlag.NoItemFlags)
            group.setData(Qt.ItemDataRole.UserRole, f"group:{category}")
            group.setSizeHint(QSize(160, max(30, self.fontMetrics().height() + 12)))
            self._groups[category] = group
            self.list.addItem(group)
            for theme in (
                t for t in THEMES.values()
                if t.category == category and t.is_valid
            ):
                pixmap = QPixmap(26, 20)
                pixmap.fill(QColor(theme.accent))
                item = QListWidgetItem(QIcon(pixmap), theme.name)
                item.setData(Qt.ItemDataRole.UserRole, theme.id)
                item.setData(Qt.ItemDataRole.AccessibleDescriptionRole, theme.description)
                item.setToolTip(theme.description)
                item.setSizeHint(QSize(180, row_height))
                self._items[theme.id] = item
                self.list.addItem(item)
        list_layout.addWidget(self.list, 1)
        self._picker_layout.addWidget(list_column, 3)

        self.preview = QFrame()
        self.preview.setObjectName("themePreview")
        preview_layout = QVBoxLayout(self.preview)
        preview_layout.setContentsMargins(18, 18, 18, 18)
        preview_layout.setSpacing(12)
        preview_header = QHBoxLayout()
        self.selected_theme_name = QLabel()
        self.selected_theme_name.setObjectName("themeName")
        preview_header.addWidget(self.selected_theme_name, 1)
        self.applied_badge = QLabel("Applied")
        self.applied_badge.setObjectName("appliedThemeBadge")
        preview_header.addWidget(self.applied_badge)
        preview_layout.addLayout(preview_header)

        self.theme_swatches = []
        swatch_row = QHBoxLayout()
        swatch_row.setSpacing(8)
        for name in ("Background", "Panel", "Accent", "Text", "Border"):
            swatch = QLabel()
            swatch.setObjectName("themeSwatch")
            swatch.setAccessibleName(f"{name} color preview")
            swatch.setFixedSize(34, 22)
            swatch_row.addWidget(swatch)
            self.theme_swatches.append(swatch)
        swatch_row.addStretch(1)
        preview_layout.addLayout(swatch_row)

        self.sample_card = QFrame()
        self.sample_card.setObjectName("themeSampleCard")
        sample_layout = QHBoxLayout(self.sample_card)
        sample_layout.setContentsMargins(12, 10, 12, 10)
        sample_layout.setSpacing(10)
        self.sample_title = QLabel("Library card")
        self.sample_title.setObjectName("themeSampleTitle")
        sample_layout.addWidget(self.sample_title, 1)
        self.sample_status = QLabel("Reading")
        self.sample_status.setObjectName("themeSampleStatus")
        sample_layout.addWidget(self.sample_status)
        preview_layout.addWidget(self.sample_card)

        self.description = QLabel()
        self.description.setObjectName("themeDescription")
        self.description.setWordWrap(True)
        self.description.setMinimumWidth(0)
        preview_layout.addWidget(self.description, 1)

        self.reduce_effects = QCheckBox("Reduce transparency and effects")
        self.reduce_effects.setObjectName("effectsCheckbox")
        self.reduce_effects.setChecked(self.manager.reduce_effects)
        self.reduce_effects.setMinimumHeight(42)
        preview_layout.addWidget(self.reduce_effects)
        self.reset_theme_button = QPushButton("Reset to Default")
        self.reset_theme_button.setObjectName("settingsSecondary")
        self.reset_theme_button.setMinimumHeight(42)
        self.reset_theme_button.clicked.connect(
            lambda: self.manager.apply_theme("minimal-simple")
        )
        preview_layout.addWidget(self.reset_theme_button)
        self._picker_layout.addWidget(self.preview, 2)

        footer = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        footer.button(QDialogButtonBox.StandardButton.Close).setObjectName("settingsSecondary")
        footer.button(QDialogButtonBox.StandardButton.Close).setMinimumHeight(40)
        footer.rejected.connect(self.reject)
        outer.addWidget(footer)

        self.list.currentItemChanged.connect(self._selection_changed)
        self.search.textChanged.connect(self._filter)
        self.reduce_effects.toggled.connect(self.manager.set_reduce_effects)
        self.manager.theme_changed.connect(self._sync_selected)
        self._sync_selected(self.manager.theme_id)

    def _available_geometry(self):
        screen = self.screen()
        if screen is None and self.parentWidget() is not None:
            screen = self.parentWidget().screen()
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is not None:
            geometry = screen.availableGeometry()
            if geometry.width() > 0 and geometry.height() > 0:
                return geometry
        return QRect(0, 0, 1024, 768)

    def _set_initial_geometry(self, parent) -> None:
        available = self._available_geometry()
        min_width = min(640, available.width())
        min_height = min(520, available.height())
        self.setMinimumSize(min_width, min_height)
        width = min(920, max(min_width, int(available.width() * 0.76)))
        height = min(820, max(min_height, int(available.height() * 0.82)))
        self.resize(width, height)
        if parent is not None:
            frame = parent.frameGeometry()
            self.move(frame.center() - self.rect().center())

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        selected_item = self._items.get(self.manager.theme_id)
        if selected_item is not None and not selected_item.isHidden():
            self.list.scrollToItem(
                selected_item, QAbstractItemView.ScrollHint.PositionAtCenter
            )

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "_picker_layout"):
            narrow = self.width() < 760
            direction = (
                QBoxLayout.Direction.TopToBottom
                if narrow else QBoxLayout.Direction.LeftToRight
            )
            if self._picker_layout.direction() != direction:
                self._picker_layout.setDirection(direction)


    def _selection_changed(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            return
        theme_id = current.data(Qt.ItemDataRole.UserRole)
        theme = THEMES.get(theme_id)
        if theme is None or not theme.is_valid:
            return
        self.manager.apply_theme(theme_id)
        self.description.setText(theme.description)

    def _sync_selected(self, theme_id: str) -> None:
        theme = THEMES.get(theme_id)
        if theme is None or not theme.is_valid:
            theme = THEMES[self.manager.theme_id]
        for key, item in self._items.items():
            selected = key == theme.id
            item.setText(("✓  " if selected else "") + THEMES[key].name)
            item.setData(
                Qt.ItemDataRole.AccessibleDescriptionRole,
                f"{'Selected. ' if selected else ''}{THEMES[key].description}",
            )
        for category, group in self._groups.items():
            group.setForeground(QColor(theme.accent))
            group_font = group.font()
            group_font.setBold(True)
            group.setFont(group_font)
        selected_item = self._items.get(theme.id)
        if selected_item is not None:
            self.list.setCurrentItem(selected_item)

        self.selected_theme_name.setText(theme.name)
        self.description.setText(theme.description)
        colors = (
            theme.background, theme.panel, theme.accent, theme.text, theme.border
        )
        names = ("Background", "Panel", "Accent", "Text", "Border")
        for swatch, name, color in zip(self.theme_swatches, names, colors):
            swatch.setStyleSheet(
                f"background-color: {color}; border: 1px solid {theme.border}; "
                "border-radius: 5px;"
            )
            swatch.setToolTip(f"{name}: {color}")
        self.sample_card.setStyleSheet(
            f"QFrame#themeSampleCard {{ background: {theme.panel}; "
            f"border: 1px solid {theme.border}; border-radius: 9px; }}"
        )
        self.sample_title.setStyleSheet(
            f"color: {theme.text}; background: transparent; font-weight: 600;"
        )
        self.sample_status.setStyleSheet(
            f"background: {theme.accent_dim}; color: {theme.text_on_accent}; "
            "border-radius: 7px; padding: 4px 9px; font-weight: 600;"
        )

    def _filter(self, query: str) -> None:
        query = query.casefold().strip()
        for key, item in self._items.items():
            theme = THEMES[key]
            item.setHidden(
                query not in theme.name.casefold()
                and query not in theme.description.casefold()
            )
        for category, group in self._groups.items():
            has_visible_items = any(
                not self._items[key].isHidden()
                for key, theme in THEMES.items()
                if theme.category == category and key in self._items
            )
            group.setHidden(not has_visible_items)

