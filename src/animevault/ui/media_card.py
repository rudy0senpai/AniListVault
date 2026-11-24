"""Reusable poster-first media card for Anime and literature.

One widget serves both categories: it takes a small adapter of plain
values (title, badges, progress) rather than a concrete model class, so
anime and manga/manhwa/manhua cards cannot drift apart visually.

Layout (mirrors the reference design)::

    ┌──────────────────────────────┐
    │ ┌────────┐  Title            │  ⋮
    │ │        │  TV · 24 ep       │
    │ │ poster │  24 / 24  ▓▓▓░░░  │
    │ │        │  [Completed] [S]  │
    │ └────────┘                    │
    └──────────────────────────────┘
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSize,
    Qt,
    QPropertyAnimation,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QAction, QColor, QConicalGradient, QFont, QPainter, QPainterPath, QPixmap,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMenu,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from animevault.ui import theme as theme_tokens
from animevault.ui.theme import (
    BORDER_GLASS,
    tier_badge_style,
    tier_color,
    status_badge_style,
)
from animevault.ui.thumb_cache import THUMB_SIZE, ThumbnailCache

#: Artwork area inside the card.
_ART_W, _ART_H = 96, 138


class _PosterLabel(QLabel):
    """Artwork area: rounded thumbnail with a placeholder when absent."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(_ART_W, _ART_H)
        self._pixmap: Optional[QPixmap] = None
        self._placeholder = True

    def set_art(self, path: str) -> None:
        """Show *path* if it loads, otherwise the placeholder."""
        pixmap = ThumbnailCache.instance().get(path) if path else None
        if pixmap is not None:
            self._pixmap = pixmap
            self._placeholder = False
            self.update()
        else:
            self._pixmap = None
            self._placeholder = True
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        path = QPainterPath()
        path.addRoundedRect(QRect(0, 0, self.width(), self.height()), 8, 8)

        if self._pixmap is not None:
            painter.save()
            painter.setClipPath(path)
            # Cover-fit: fill the box, crop the overflow.
            scaled = self._pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (scaled.width() - self.width()) // 2
            painter.drawPixmap(QPoint(-x, 0), scaled)
            painter.restore()
        else:
            painter.fillPath(path, QColor(theme_tokens.BG_INPUT))
            painter.setPen(QColor(theme_tokens.TEXT_MUTED))
            # A default QFont can carry a pixel size (-1 point), which Qt
            # rejects; set both explicitly so the placeholder renders.
            font = QFont()
            font.setPixelSize(28)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "▦")

        painter.setPen(QColor(theme_tokens.BORDER))
        painter.drawPath(path)
        painter.end()


class MediaCard(QFrame):
    """A single poster-first card for any media category."""

    details_requested = Signal(object)
    edit_requested = Signal(object)
    refresh_requested = Signal(object)
    deleted = Signal(object)
    selection_changed = Signal(object, bool)

    def __init__(
        self,
        item: object,
        *,
        title: str,
        type_label: str,
        count_label: str,
        progress_text: str,
        progress_percent: int,
        status_text: str,
        status_key: str,
        tier: Optional[str],
        poster_path: str,
        kind: str,
    ) -> None:
        super().__init__()
        self._item = item
        self._kind = kind
        self._select_mode = False
        self.setObjectName("mediaCard")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._selected = False
        self._hovered = False
        self.setProperty("selected", False)
        self._border_angle = 0.0
        self._effects_reduced = theme_tokens.reduce_effects()
        self.setStyleSheet(
            "QFrame#mediaCard { background: transparent; border: none; }"
        )
        self._border_animation = QVariantAnimation(self)
        self._border_animation.setStartValue(0.0)
        self._border_animation.setEndValue(360.0)
        self._border_animation.setDuration(7200)
        self._border_animation.setLoopCount(-1)
        self._border_animation.valueChanged.connect(self._set_border_angle)
        if not self._effects_reduced:
            self._border_animation.start()
        self._shadow_effect = QGraphicsDropShadowEffect(self)
        self._shadow_effect.setBlurRadius(8)
        self._shadow_effect.setOffset(0, 2)
        self._shadow_effect.setEnabled(False)
        self.setGraphicsEffect(self._shadow_effect)
        self._shadow_animation = QPropertyAnimation(self._shadow_effect, b"blurRadius", self)
        self._shadow_animation.setDuration(180)
        self._shadow_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._build(
            title=title,
            type_label=type_label,
            count_label=count_label,
            progress_text=progress_text,
            progress_percent=progress_percent,
            status_text=status_text,
            status_key=status_key,
            tier=tier,
            poster_path=poster_path,
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    # ── Construction ───────────────────────────────────────────────

    def _build(
        self,
        *,
        title: str,
        type_label: str,
        count_label: str,
        progress_text: str,
        progress_percent: int,
        status_text: str,
        status_key: str,
        tier: Optional[str],
        poster_path: str,
    ) -> None:
        outer = QHBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(11)

        # LEFT — artwork
        self._poster = _PosterLabel()
        self._poster.set_art(poster_path)
        outer.addWidget(self._poster, 0, Qt.AlignmentFlag.AlignTop)

        # RIGHT — details
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(6)

        # Title row + overflow menu
        title_row = QHBoxLayout()
        title_row.setSpacing(6)

        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        title_label.setWordWrap(True)
        title_label.setMaximumHeight(34)
        title_label.setToolTip(title)
        title_row.addWidget(title_label, 1)

        self._menu_button = QLabel("⋮")
        self._menu_button.setStyleSheet(
            f"color:{theme_tokens.TEXT_MUTED}; font-size:15px; padding:0 4px;"
        )
        self._menu_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._menu_button.setToolTip("More actions")
        title_row.addWidget(self._menu_button, 0, Qt.AlignmentFlag.AlignTop)
        right.addLayout(title_row)

        # Type · count
        meta_text = " · ".join(x for x in (type_label, count_label) if x)
        meta_label = QLabel(meta_text)
        meta_label.setObjectName("cardMeta")
        meta_label.setToolTip(meta_text)
        right.addWidget(meta_label)

        # Progress: text + bar
        progress_row = QHBoxLayout()
        progress_row.setSpacing(7)

        progress_text_label = QLabel(progress_text)
        progress_text_label.setObjectName("cardProgressText")
        progress_text_label.setMinimumWidth(52)
        progress_row.addWidget(progress_text_label)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(max(0, min(100, progress_percent)))
        bar.setTextVisible(False)
        bar.setFixedHeight(5)
        bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        progress_row.addWidget(bar, 1)
        right.addLayout(progress_row)

        # Badges: status + tier
        badge_row = QHBoxLayout()
        badge_row.setSpacing(6)

        status_badge = QLabel(status_text)
        status_badge.setStyleSheet(status_badge_style(status_key))
        status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge_row.addWidget(status_badge)

        tier_badge = QLabel(tier or "—")
        tier_badge.setStyleSheet(tier_badge_style(tier))
        tier_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tier_badge.setMinimumWidth(26)
        if tier:
            tier_badge.setToolTip(f"Tier {tier}")
        else:
            tier_badge.setToolTip("No tier assigned")
        badge_row.addWidget(tier_badge)
        badge_row.addStretch()
        right.addLayout(badge_row)
        right.addStretch()
        outer.addLayout(right, 1)

        # Selection check indicator (glass accent, top-right of the card).
        self._check = QLabel("✓")
        self._check.setObjectName("cardCheck")
        self._check.setVisible(False)
        self._check.setStyleSheet(
            f"color:{theme_tokens.ACCENT}; font-size:15px; "
            f"font-weight:700;"
        )
        self._check.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._check.setFixedSize(22, 22)
        outer.addWidget(self._check, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)

        self.setMinimumWidth(_ART_W + 150)
        self.setMaximumHeight(_ART_H + 20)
        self._update_surface()

    # ── Public API ─────────────────────────────────────────────────

    @property
    def item(self) -> object:
        return self._item

    @property
    def kind(self) -> str:
        return self._kind

    def is_selected(self) -> bool:
        return self._selected

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.setProperty("selected", selected)
        self._update_surface()
        self._check.setVisible(selected)

    def set_effects_reduced(self, reduced: bool) -> None:
        """Pause animated borders and shadows when reduced effects is enabled."""
        self._effects_reduced = bool(reduced)
        if self._effects_reduced:
            self._border_animation.stop()
        elif self._border_animation.state() != QVariantAnimation.State.Running:
            self._border_animation.start()
        self._update_surface()

    def _set_border_angle(self, angle: object) -> None:
        self._border_angle = float(angle)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        """Paint the translucent card and its slowly rotating gradient edge."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        outer_rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        border_width = 2.0 if self._selected else 1.4
        corner_radius = 14.0

        surface_color = QColor(
            theme_tokens.BG_SURFACE_HI if self._selected else theme_tokens.BG_SURFACE
        )
        surface_color.setAlpha(242 if self._selected else 232)
        outer_path = QPainterPath()
        outer_path.addRoundedRect(outer_rect, corner_radius, corner_radius)
        painter.fillPath(outer_path, surface_color)

        inner_rect = outer_rect.adjusted(
            border_width, border_width, -border_width, -border_width
        )
        ring = QPainterPath()
        ring.setFillRule(Qt.FillRule.OddEvenFill)
        ring.addRoundedRect(outer_rect, corner_radius, corner_radius)
        ring.addRoundedRect(
            inner_rect,
            max(0.0, corner_radius - border_width),
            max(0.0, corner_radius - border_width),
        )

        gradient = QConicalGradient(QPointF(outer_rect.center()), self._border_angle)
        if self._selected:
            gradient.setColorAt(0.0, QColor(theme_tokens.ACCENT_DIM))
            gradient.setColorAt(0.80, QColor(theme_tokens.ACCENT_DIM))
            gradient.setColorAt(0.88, QColor(theme_tokens.ACCENT_VIOLET))
            gradient.setColorAt(0.94, QColor(theme_tokens.ACCENT))
            gradient.setColorAt(1.0, QColor(theme_tokens.ACCENT_DIM))
        else:
            gradient.setColorAt(0.0, QColor(BORDER_GLASS))
            gradient.setColorAt(0.42, QColor(theme_tokens.BORDER))
            gradient.setColorAt(0.80, QColor(BORDER_GLASS))
            gradient.setColorAt(0.86, QColor(theme_tokens.ACCENT_VIOLET_DIM))
            gradient.setColorAt(0.90, QColor(theme_tokens.ACCENT_VIOLET))
            gradient.setColorAt(0.94, QColor(theme_tokens.ACCENT))
            gradient.setColorAt(1.0, QColor(BORDER_GLASS))
        painter.fillPath(ring, gradient)
        painter.end()

    def refresh_art(self, poster_path: str) -> None:
        self._poster.set_art(poster_path)

    def _update_surface(self) -> None:
        """Refresh the selected/hovered border and soft shadow state."""
        self.update()
        use_shadow = not self._effects_reduced and (self._selected or self._hovered)
        self._shadow_effect.setEnabled(use_shadow)
        shadow = QColor(theme_tokens.ACCENT_VIOLET if self._selected else theme_tokens.ACCENT)
        shadow.setAlpha(46 if self._selected else 30)
        self._shadow_effect.setColor(shadow)
        if use_shadow:
            self._shadow_animation.stop()
            self._shadow_animation.setStartValue(self._shadow_effect.blurRadius())
            self._shadow_animation.setEndValue(18 if self._selected else 14)
            self._shadow_animation.start()
        else:
            self._shadow_animation.stop()
            self._shadow_effect.setBlurRadius(8)

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hovered = True
        self._update_surface()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered = False
        self._update_surface()
        super().leaveEvent(event)

    # ── Interaction ────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            global_pos = self.mapToGlobal(event.position().toPoint())
            if self._menu_button.geometry().contains(
                self._menu_button.parentWidget().mapFromGlobal(global_pos)
            ):
                self._show_menu(global_pos)
            elif self._select_mode:
                self.set_selected(not self._selected)
                self.selection_changed.emit(self._item, self._selected)
            else:
                self.details_requested.emit(self._item)
        super().mousePressEvent(event)

    def set_select_mode(self, enabled: bool) -> None:
        """Toggle multi-select behaviour for this card."""
        self._select_mode = enabled
        self.setCursor(
            Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ArrowCursor
        )
        if not enabled:
            self.set_selected(False)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        self._show_menu(event.globalPos())
        super().contextMenuEvent(event)

    def _show_menu(self, pos) -> None:
        menu = QMenu(self)
        details = menu.addAction("View Details")
        edit = menu.addAction("Edit")
        refresh = menu.addAction("Fetch / Refresh Metadata")
        menu.addSeparator()
        delete = menu.addAction("Delete")

        chosen = menu.exec(pos)
        if chosen == details:
            self.details_requested.emit(self._item)
        elif chosen == edit:
            self.edit_requested.emit(self._item)
        elif chosen == refresh:
            self.refresh_requested.emit(self._item)
        elif chosen == delete:
            self.deleted.emit(self._item)