"""Appearance controls (Reduce Effects + 3D Liquid Glass).

The 26-theme registry is retired. There is no palette picker: only the
user's appearance preferences are exposed here. Preferences persist in
QSettings and are read from ``animevault.ui.theme``.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QSettings, QSize, QRect
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from animevault import __version__
from animevault.ui.visual_effects import AnimatedToggle


class ThemeSettingsDialog(QDialog):
    """Appearance panel. Theme selection is retired; only user preferences
    (Reduce Effects, 3D Liquid Glass) are exposed. Preferences persist in
    QSettings via :func:`animevault.ui.theme.set_reduce_effects` and
    :func:`animevault.ui.theme.set_liquid_glass`."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("appearanceSettingsDialog")
        self.setWindowTitle("Appearance")
        self.setSizeGripEnabled(True)
        self._set_initial_geometry(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 16)
        outer.setSpacing(14)

        heading = QLabel("Appearance")
        heading.setObjectName("settingsTitle")
        subtitle = QLabel(
            "Appearance options are stored in your settings. "
            "Theme selection is no longer available."
        )
        subtitle.setObjectName("settingsSubtitle")
        subtitle.setWordWrap(True)
        outer.addWidget(heading)
        outer.addWidget(subtitle)

        content = QWidget()
        content.setObjectName("settingsContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 4, 0, 8)
        layout.setSpacing(18)

        reduce = AnimatedToggle("Reduce transparency and effects")
        reduce.setObjectName("effectsCheckbox")
        reduce.setMinimumHeight(42)
        layout.addWidget(reduce)

        section = QLabel("Appearance mode")
        section.setObjectName("settingsSectionTitle")
        layout.addWidget(section)

        mode = QComboBox()
        mode.setObjectName("effectsCombo")
        mode.addItems(["Standard", "3D Liquid Glass"])
        mode.setMinimumHeight(42)
        layout.addWidget(mode)

        footer = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        footer.button(QDialogButtonBox.StandardButton.Close).setObjectName("settingsSecondary")
        footer.button(QDialogButtonBox.StandardButton.Close).setMinimumHeight(40)
        footer.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.accept)
        outer.addWidget(footer)
        outer.addWidget(content, 1)

        # Keep references for geometry helpers and accept/reject handlers.
        self._reduce_check = reduce
        self._mode_combo = mode

        # Geometry helpers -------------------------------------------------
        self._available_geometry()
        self._sync_from_settings()

    def _available_geometry(self) -> QRect:
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

    def _sync_from_settings(self) -> None:
        from animevault.ui.theme import reduce_effects, liquid_glass
        self._reduce_check.setChecked(reduce_effects())
        self._mode_combo.setCurrentIndex(1 if liquid_glass() else 0)

    def accept(self) -> None:
        from animevault.ui.theme import set_reduce_effects, set_liquid_glass
        set_reduce_effects(self._reduce_check.isChecked())
        set_liquid_glass(self._mode_combo.currentIndex() == 1)
        super().accept()

    def reject(self) -> None:
        super().reject()
