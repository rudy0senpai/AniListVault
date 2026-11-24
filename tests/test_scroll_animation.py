"""Viewport-triggered scroll reveals for all scrollable UI surfaces."""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, QRect
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from animevault.ui.scroll_animation import ScrollRevealArea


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


def _scroll_fixture(qt_app):
    area = ScrollRevealArea()
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    area.setWidgetResizable(False)
    area.set_reveal_duration(0)
    area.set_effects_reduced(False)
    host = QWidget()
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    rows = []
    for index in range(3):
        row = QLabel(f"section {index}")
        row.setFixedSize(100, 100)
        layout.addWidget(row)
        rows.append(row)
    host.resize(100, 300)
    area.setWidget(host)
    area.resize(120, 100)
    return area, rows


def test_reveals_items_at_half_viewport_visibility_once(qt_app):
    area, rows = _scroll_fixture(qt_app)
    started = QSignalSpy(area.reveal_started)
    area.show()
    area.refresh_reveal_targets()
    area._update_reveals()

    assert started.count() == 1

    area.verticalScrollBar().setValue(40)
    assert started.count() == 1

    area.verticalScrollBar().setValue(50)
    assert started.count() == 2

    area.verticalScrollBar().setValue(0)
    area.verticalScrollBar().setValue(50)
    assert started.count() == 2
    area.close()


def test_reveal_overlay_preserves_existing_card_effect(qt_app):
    area, rows = _scroll_fixture(qt_app)
    shadow = QGraphicsDropShadowEffect(rows[0])
    rows[0].setGraphicsEffect(shadow)
    area.show()
    area.refresh_reveal_targets()
    area._update_reveals()

    assert rows[0].graphicsEffect() is shadow
    area.close()


def test_reduce_effects_disables_scroll_reveals(qt_app):
    area, rows = _scroll_fixture(qt_app)
    area.set_effects_reduced(True)
    started = QSignalSpy(area.reveal_started)
    area.show()
    area.refresh_reveal_targets()

    assert started.count() == 0
    assert area.effects_reduced()
    assert all(row.isVisible() for row in rows[:2])
    area.close()


def test_active_reveal_veil_tracks_target_while_scrolling(qt_app):
    area, rows = _scroll_fixture(qt_app)
    area.set_reveal_duration(300)
    area.show()
    area.refresh_reveal_targets()
    area._update_reveals()
    veil = area._veils[rows[0]]
    initial = veil.geometry()

    area.verticalScrollBar().setValue(20)
    expected = QRect(rows[0].mapTo(area.viewport(), QPoint(0, 0)), rows[0].size())

    assert veil.geometry() == expected
    assert veil.geometry().y() != initial.y()
    area.set_effects_reduced(True)
    area.close()
