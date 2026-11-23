"""Tests for the pastel glass visual effects used by the desktop UI."""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QGraphicsDropShadowEffect,
    QPushButton,
)

from animevault.ui.theme import (
    ACCENT,
    ACCENT_VIOLET,
    BG_SURFACE,
    application_stylesheet,
)
from animevault.ui.visual_effects import AnimatedToggle, HoverLiftButton, RadialGradientLabel


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    return app


@pytest.fixture
def isolated_settings(tmp_path):
    previous_format = QSettings.defaultFormat()
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    yield
    QSettings.setDefaultFormat(previous_format)


def test_close_button_saves_appearance_preferences(qt_app, isolated_settings):
    from animevault.ui.theme import reduce_effects
    from animevault.ui.theme_dialog import ThemeSettingsDialog

    dialog = ThemeSettingsDialog()
    dialog._reduce_check.setChecked(True)
    close_button = dialog.findChild(QPushButton, "settingsSecondary")
    assert close_button is not None
    close_button.click()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert reduce_effects() is True
    dialog.close()


def test_application_stylesheet_uses_glass_layers_and_clear_focus_states(qt_app):
    style = application_stylesheet()
    assert "#headerBar" in style and "#searchRow" in style
    assert "background-color: rgba(18, 23, 34, 232)" in style
    assert "QPushButton:focus" in style
    assert "QPushButton#primaryButton" in style


def test_visual_tokens_use_pastel_accents_on_graphite(qt_app):
    assert ACCENT.lower() == "#a3eee2"
    assert ACCENT_VIOLET.lower() == "#c7b6ff"
    assert BG_SURFACE.lower() == "#121722"


def test_radial_gradient_label_renders_multitone_text(qt_app):
    label = RadialGradientLabel("AnimeVault")
    label.setFont(QFont("Segoe UI", 28, QFont.Weight.Bold))
    label.resize(300, 58)
    label.show()
    qt_app.processEvents()

    image = QImage(label.size(), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)
    label.render(painter, QPoint(0, 0))
    painter.end()

    colors = set()
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if color.alpha() > 64:
                colors.add((color.red(), color.green(), color.blue()))
    assert label.text() == "AnimeVault"
    assert len(colors) > 3
    label.close()


def test_animated_toggle_keeps_checkbox_interaction(qt_app):
    toggle = AnimatedToggle("Reduce transparency and effects")
    assert toggle.isCheckable()
    toggle.click()
    assert toggle.isChecked()
    toggle.click()
    assert not toggle.isChecked()


def test_primary_button_uses_soft_shadow_hover_effect(qt_app):
    button = HoverLiftButton("Add to library")
    effect = button.graphicsEffect()
    assert isinstance(effect, QGraphicsDropShadowEffect)
    assert effect.blurRadius() > 0
    assert button.accessibleName() == "Add to library"
