"""Small, accessible Qt effects adapted from the supplied web references.

These native widgets use a radial text fill, a checkbox-backed animated
switch, and a restrained hover-lift shadow. They avoid a WebEngine/WebGL
runtime dependency and honor AnimeVault's Reduce Effects preference.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPointF,
    Property,
    QParallelAnimationGroup,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
)
from PySide6.QtGui import QBrush, QColor, QFontMetrics, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QCheckBox,
    QGraphicsDropShadowEffect,
    QLabel,
    QPushButton,
)

from animevault.ui import theme as theme_tokens


def _effects_reduced() -> bool:
    return theme_tokens.reduce_effects()


class RadialGradientLabel(QLabel):
    """A one-line label with a radial, lit-from-within text fill."""

    def paintEvent(self, event) -> None:  # noqa: N802
        text = self.text()
        if not text or "\n" in text:
            super().paintEvent(event)
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setFont(self.font())

        metrics = QFontMetrics(self.font())
        bounds = self.contentsRect()
        width = metrics.horizontalAdvance(text)
        alignment = self.alignment()
        if alignment & Qt.AlignmentFlag.AlignHCenter:
            x = bounds.x() + max(0, (bounds.width() - width) / 2)
        elif alignment & Qt.AlignmentFlag.AlignRight:
            x = bounds.right() - width
        else:
            x = bounds.x()
        baseline = bounds.y() + (bounds.height() - metrics.height()) / 2 + metrics.ascent()

        gradient = QRadialGradient(
            QPointF(x + width * 0.5, baseline - metrics.ascent() * 0.42),
            max(width * 0.58, metrics.height() * 1.2),
        )
        gradient.setColorAt(0.0, QColor(theme_tokens.GRADIENT_CENTRE))
        gradient.setColorAt(0.48, QColor(theme_tokens.ACCENT_VIOLET))
        gradient.setColorAt(1.0, QColor(theme_tokens.GRADIENT_EDGE))
        painter.setPen(QPen(QBrush(gradient), 1))
        painter.drawText(QPointF(x, baseline), text)
        painter.end()


class AnimatedToggle(QCheckBox):
    """Checkbox-backed switch with keyboard behavior and reduced-motion support."""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setAccessibleName(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(42)
        self._position = 1.0 if self.isChecked() else 0.0
        self._animation = QPropertyAnimation(self, b"position", self)
        self._animation.setDuration(180)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate_to_state)

    @Property(float)
    def position(self) -> float:
        return self._position

    @position.setter
    def position(self, value: float) -> None:
        self._position = max(0.0, min(1.0, float(value)))
        self.update()

    def _animate_to_state(self, checked: bool) -> None:
        target = 1.0 if checked else 0.0
        if _effects_reduced():
            self.position = target
            return
        self._animation.stop()
        self._animation.setStartValue(self._position)
        self._animation.setEndValue(target)
        self._animation.start()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(360, 42)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(self.font())

        track = QRectF(max(0, self.width() - 52), (self.height() - 26) / 2, 48, 26)
        text_rect = QRectF(0, 0, max(0, track.x() - 14), self.height())
        text_color = QColor(theme_tokens.TEXT_PRIMARY if self.isEnabled() else theme_tokens.TEXT_MUTED)
        painter.setPen(text_color)
        painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), self.text())

        off = QColor(theme_tokens.BORDER_HOVER)
        on = QColor(theme_tokens.ACCENT_DEEP)
        progress = self._position
        track_color = QColor(
            round(off.red() + (on.red() - off.red()) * progress),
            round(off.green() + (on.green() - off.green()) * progress),
            round(off.blue() + (on.blue() - off.blue()) * progress),
        )
        if not self.isEnabled():
            track_color.setAlpha(115)
        painter.setPen(QPen(QColor(theme_tokens.BORDER_GLASS), 1))
        painter.setBrush(track_color)
        painter.drawRoundedRect(track, 13, 13)

        knob_size = 20.0
        knob_x = track.x() + 3 + (track.width() - knob_size - 6) * progress
        knob = QRectF(knob_x, track.y() + 3, knob_size, knob_size)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(knob)

        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(theme_tokens.ACCENT_VIOLET), 2))
            painter.drawRoundedRect(track.adjusted(-3, -3, 3, 3), 15, 15)
        painter.end()


class HoverLiftButton(QPushButton):
    """Primary action button with a brief, soft shadow-lift hover animation."""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setAccessibleName(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        effect = QGraphicsDropShadowEffect(self)
        effect.setBlurRadius(9)
        effect.setOffset(QPointF(0, 2))
        color = QColor(theme_tokens.ACCENT_DEEP)
        color.setAlpha(58)
        effect.setColor(color)
        self.setGraphicsEffect(effect)
        self._shadow_effect = effect
        self._hover_animation: QParallelAnimationGroup | None = None

    def _animate_shadow(self, raised: bool) -> None:
        if _effects_reduced() or not self.isEnabled():
            if self._hover_animation is not None:
                self._hover_animation.stop()
            self._shadow_effect.setBlurRadius(9)
            self._shadow_effect.setOffset(QPointF(0, 2))
            return

        if self._hover_animation is not None:
            self._hover_animation.stop()
            self._hover_animation.deleteLater()
        group = QParallelAnimationGroup(self)
        blur = QPropertyAnimation(self._shadow_effect, b"blurRadius", group)
        blur.setDuration(170)
        blur.setStartValue(self._shadow_effect.blurRadius())
        blur.setEndValue(16 if raised else 9)
        blur.setEasingCurve(QEasingCurve.Type.OutCubic)
        offset = QPropertyAnimation(self._shadow_effect, b"offset", group)
        offset.setDuration(170)
        offset.setStartValue(self._shadow_effect.offset())
        offset.setEndValue(QPointF(0, 5 if raised else 2))
        offset.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hover_animation = group
        group.start()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._animate_shadow(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._animate_shadow(False)
        super().leaveEvent(event)
