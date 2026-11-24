"""Viewport-triggered, one-shot reveal animation for native Qt scroll areas.

The browser reference uses an intersection threshold of 0.5 and reveals each
item once. This component gives scroll-area content the same behavior without
changing the effect already installed on cards or panels: a short-lived veil is
animated above each item instead of replacing the item's graphics effect.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEasingCurve, QPoint, QRect, QPropertyAnimation, QTimer, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QLayout,
    QScrollArea,
    QWidget,
)

from animevault.ui.theme import BG_DEEP, reduce_effects


class _RevealVeil(QWidget):
    """A temporary overlay whose fade reveals the unchanged target widget."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("scrollRevealVeil")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        color = QColor(BG_DEEP)
        color.setAlpha(92)
        self.setStyleSheet(
            "QWidget#scrollRevealVeil {"
            f"background-color: rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()});"
            "border: none; }"
        )
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity)

    @property
    def opacity_effect(self) -> QGraphicsOpacityEffect:
        return self._opacity


class ScrollRevealArea(QScrollArea):
    """QScrollArea that reveals each direct content item once at 50% visibility.

    Targets are widgets in the scroll area's content layout (including widgets
    inside nested layouts). A viewport overlay fades away when at least half of
    a target's area is visible. ``reduce_effects`` disables the animation.
    """

    reveal_started = Signal(QWidget)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._reveal_duration = 240
        self._visibility_threshold = 0.5
        self._effects_reduced = reduce_effects()
        self._targets: list[QWidget] = []
        self._revealed: set[QWidget] = set()
        self._veils: dict[QWidget, _RevealVeil] = {}
        self._animations: dict[QWidget, QPropertyAnimation] = {}
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self.refresh_reveal_targets)
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._update_reveals)
        self.verticalScrollBar().valueChanged.connect(self._update_reveals)
        self.horizontalScrollBar().valueChanged.connect(self._update_reveals)

    def setWidget(self, widget: QWidget) -> None:  # noqa: N802
        super().setWidget(widget)
        self._schedule_refresh()

    def set_reveal_duration(self, milliseconds: int) -> None:
        """Set the reveal duration; exposed to keep UI timing testable."""
        self._reveal_duration = max(0, int(milliseconds))

    def effects_reduced(self) -> bool:
        """Return whether scroll-reveal motion is currently suppressed."""
        return self._effects_reduced

    def set_effects_reduced(self, reduced: bool) -> None:
        """Apply the existing Reduce Effects preference to this scroll area."""
        self._effects_reduced = bool(reduced)
        if self._effects_reduced:
            self._revealed.update(self._targets)
            self._clear_veils()
        else:
            self.refresh_reveal_targets()
            self._update_reveals()

    def refresh_reveal_targets(self) -> None:
        """Rescan content after dynamic widgets have been added or removed."""
        content = self.widget()
        layout = content.layout() if content is not None else None
        targets = _layout_widgets(layout) if layout is not None else ([content] if content else [])
        current = [widget for widget in targets if widget is not None]
        current_set = set(current)

        for target in tuple(self._veils):
            if target not in current_set:
                self._discard_veil(target)
        self._revealed.intersection_update(current_set)
        self._targets = current
        if self._effects_reduced:
            self._revealed.update(current_set)
            self._clear_veils()
            return
        self._schedule_update()

    def has_revealed(self, target: QWidget) -> bool:
        """Return whether a target has crossed the reveal threshold."""
        return target in self._revealed

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._schedule_refresh()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._schedule_update()

    def _schedule_refresh(self) -> None:
        if not self._effects_reduced:
            self._refresh_timer.start(0)

    def _schedule_update(self) -> None:
        if not self._effects_reduced:
            self._update_timer.start(0)

    def _update_reveals(self, *_args) -> None:
        if self._effects_reduced:
            self._revealed.update(self._targets)
            self._clear_veils()
            return
        viewport = self.viewport()
        viewport_rect = viewport.rect()
        for target in tuple(self._targets):
            if not target.isVisible():
                continue
            rect = QRect(target.mapTo(viewport, QPoint(0, 0)), target.size())
            veil = self._veils.get(target)
            if target in self._revealed:
                if veil is not None:
                    veil.setGeometry(rect)
                    veil.raise_()
                continue

            intersection = rect.intersected(viewport_rect)
            if intersection.isEmpty() or target.width() <= 0 or target.height() <= 0:
                continue

            if veil is None:
                veil = _RevealVeil(viewport)
                self._veils[target] = veil
            veil.setGeometry(rect)
            veil.show()
            veil.raise_()

            visible_fraction = (
                intersection.width() * intersection.height()
                / (target.width() * target.height())
            )
            if visible_fraction >= self._visibility_threshold:
                self._start_reveal(target, veil)

    def _start_reveal(self, target: QWidget, veil: _RevealVeil) -> None:
        if target in self._revealed:
            return
        self._revealed.add(target)
        self.reveal_started.emit(target)
        animation = QPropertyAnimation(veil.opacity_effect, b"opacity", self)
        animation.setDuration(self._reveal_duration)
        animation.setStartValue(1.0)
        animation.setEndValue(0.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(lambda target=target: self._finish_reveal(target))
        self._animations[target] = animation
        if self._reveal_duration == 0:
            self._finish_reveal(target)
        else:
            animation.start()

    def _finish_reveal(self, target: QWidget) -> None:
        animation = self._animations.pop(target, None)
        if animation is not None:
            animation.deleteLater()
        veil = self._veils.pop(target, None)
        if veil is not None:
            veil.hide()
            veil.deleteLater()

    def _discard_veil(self, target: QWidget) -> None:
        animation = self._animations.pop(target, None)
        if animation is not None:
            animation.stop()
            animation.deleteLater()
        veil = self._veils.pop(target, None)
        if veil is not None:
            veil.hide()
            veil.deleteLater()

    def _clear_veils(self) -> None:
        for target in tuple(self._veils):
            self._discard_veil(target)


def _layout_widgets(layout: QLayout) -> list[QWidget]:
    """Return meaningful QWidget items in layout order, descending sublayouts."""
    widgets: list[QWidget] = []
    for index in range(layout.count()):
        item = layout.itemAt(index)
        widget = item.widget()
        if widget is not None:
            widgets.append(widget)
        elif item.layout() is not None:
            widgets.extend(_layout_widgets(item.layout()))
    return widgets
