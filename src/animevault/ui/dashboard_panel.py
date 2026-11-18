"""Full-page Library Analytics Dashboard.

A dedicated analytics dashboard accessible from Tools → Library Dashboard.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime
from typing import Optional

from PySide6.QtCore import QRectF, Qt, QSize, Signal
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QFontMetrics, QLinearGradient
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QSizePolicy,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
    QGridLayout,
    QScrollArea,
    QPushButton,
)

from animevault.media_types import (
    MEDIA_ANIME,
    MEDIA_MANGA,
    MEDIA_MANHWA,
    MEDIA_MANHUA,
    CATEGORY_LABELS,
    normalize_category,
)
from animevault.models.anime import Anime
from animevault.models.literature import Literature
from animevault.tiers import TIERS
from animevault.ui import theme as theme_tokens
from animevault.ui.theme import tier_color, ThemeManager

logger = logging.getLogger(__name__)

# Category colors for charts (theme-aware fallbacks)
_CATEGORY_COLORS = {
    MEDIA_ANIME: "#3b82f6",
    MEDIA_MANGA: "#f59e0b",
    MEDIA_MANHWA: "#a78bfa",
    MEDIA_MANHUA: "#f472b6",
}

_GENRE_BAR_COLORS = ["#4ade80", "#22d3ee", "#a78bfa", "#c084fc", "#fbbf24", "#fb923c"]


def _panel(title: str) -> tuple[QFrame, QVBoxLayout]:
    """A titled bordered panel; returns the frame and its layout."""
    frame = QFrame()
    frame.setObjectName("statPanel")
    frame.setStyleSheet(
        f"#statPanel {{ background:{theme_tokens.BG_PANEL}; border:1px solid {theme_tokens.BORDER};"
        " border-radius:12px; }"
    )
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(12)

    heading = _ElidingLabel(title)
    heading.setObjectName("panelTitle")
    heading.setStyleSheet(f"color:{theme_tokens.TEXT_SECONDARY}; font-weight:600; font-size:12px;")
    layout.addWidget(heading)
    return frame, layout


class _ElidingLabel(QLabel):
    """A label that never forces its parent wider than intended."""

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(text, parent)
        self.setToolTip(text)
        self.setMinimumWidth(0)
        self.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )


class _KPICard(QFrame):
    """A compact Key Performance Indicator card for the dashboard."""

    def __init__(
        self,
        label: str,
        value: str = "0",
        icon: str = "",
        color: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("kpiCard")
        self.setFixedHeight(90)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(120)
        self._color = color or theme_tokens.ACCENT

        self.setStyleSheet(
            f"#kpiCard {{ background:{theme_tokens.BG_PANEL}; border:1px solid {theme_tokens.BORDER};"
            f" border-radius:10px; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        # Top row: icon and label
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)

        if icon:
            icon_label = QLabel(icon)
            icon_label.setStyleSheet(f"color:{self._color}; font-size:18px;")
            icon_label.setFixedWidth(28)
            top_row.addWidget(icon_label, 0)

        self._label = _ElidingLabel(label)
        self._label.setObjectName("kpiLabel")
        self._label.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:11px; font-weight:500;")
        top_row.addWidget(self._label, 1)

        layout.addLayout(top_row)

        # Value
        self._value = QLabel(value)
        self._value.setObjectName("kpiValue")
        self._value.setStyleSheet(
            f"color:{theme_tokens.TEXT_PRIMARY}; font-size:28px; font-weight:700;"
        )
        self._value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._value, 1)

    def set_value(self, value: str) -> None:
        self._value.setText(str(value))

    def set_label(self, label: str) -> None:
        self._label.setText(label)


class _BarTrack(QFrame):
    """A bar track whose fill scales to the available width."""

    def __init__(self, fraction: float, color: str) -> None:
        super().__init__()
        self._fraction = max(0.0, min(1.0, fraction))
        self.setFixedHeight(8)
        self.setStyleSheet(f"background:{theme_tokens.BG_INPUT}; border-radius:4px;")

        self._fill = QFrame(self)
        self._fill.setFixedHeight(8)
        self._fill.setStyleSheet(f"background:{color}; border-radius:4px;")

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_fill()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._sync_fill()

    def _sync_fill(self) -> None:
        width = self.width()
        if self._fraction > 0 and width > 0:
            fill_width = min(width, max(4, int(width * self._fraction)))
            self._fill.setFixedWidth(fill_width)
            self._fill.move(0, 0)
            self._fill.show()
        else:
            self._fill.setFixedWidth(0)
            self._fill.hide()

    def set_fraction(self, fraction: float) -> None:
        self._fraction = max(0.0, min(1.0, fraction))
        self._sync_fill()


class _BarRow(QWidget):
    """A labelled horizontal bar for genre/status counts."""

    def __init__(self, label: str, value: int, maximum: int, color: str, show_percent: bool = True) -> None:
        super().__init__()
        self._color = color
        self._max = maximum
        self._show_percent = show_percent
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)

        name = QLabel(label)
        name.setObjectName("statLabel")
        name.setMinimumWidth(120)
        name.setMaximumWidth(160)
        name.setToolTip(label)
        metrics = name.fontMetrics()
        name.setText(metrics.elidedText(label, Qt.TextElideMode.ElideRight, 160))
        name.setStyleSheet(f"color:{theme_tokens.TEXT_SECONDARY}; font-size:12px; font-weight:500;")
        row.addWidget(name, 0)

        fraction = (value / maximum) if maximum > 0 else 0.0
        self._track = _BarTrack(fraction, color)
        self._track.setMinimumWidth(100)
        row.addWidget(self._track, 1)

        self._count = QLabel(str(value))
        self._count.setObjectName("statLabel")
        self._count.setMinimumWidth(40)
        self._count.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._count.setStyleSheet(f"color:{theme_tokens.TEXT_PRIMARY}; font-size:12px; font-weight:600;")
        row.addWidget(self._count, 0)

        if show_percent:
            self._percent = QLabel(f"{(value / maximum * 100):.0f}%" if maximum > 0 else "0%")
            self._percent.setObjectName("statLabel")
            self._percent.setMinimumWidth(40)
            self._percent.setAlignment(Qt.AlignmentFlag.AlignRight)
            self._percent.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:11px;")
            row.addWidget(self._percent, 0)

    def set_value(self, value: int, maximum: int | None = None) -> None:
        if maximum is not None:
            self._max = maximum
        self._count.setText(str(value))
        fraction = (value / self._max) if self._max > 0 else 0.0
        self._track.set_fraction(fraction)
        if self._show_percent and hasattr(self, '_percent'):
            self._percent.setText(f"{(value / self._max * 100):.0f}%" if self._max > 0 else "0%")


class _TierBarRow(QWidget):
    """A horizontal tier bar row for the dashboard - large, readable, professional."""

    def __init__(self, tier: str, count: int, maximum: int) -> None:
        super().__init__()
        self._tier = tier
        self._max = maximum
        self.setFixedHeight(40)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(0)

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 4, 8, 4)
        root.setSpacing(12)

        # Tier label with color
        self._label = QLabel(tier)
        self._label.setObjectName("tierLabel")
        self._label.setFixedWidth(50)
        self._label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        reduce_effects = ThemeManager.instance().reduce_effects
        tier_bg = tier_color(tier) if not reduce_effects else theme_tokens.ACCENT
        self._label.setStyleSheet(
            f"color:{tier_bg}; font-size:13px; font-weight:700;"
        )
        root.addWidget(self._label, 0)

        # Bar track
        self._track = QFrame()
        self._track.setFixedHeight(16)
        self._track.setStyleSheet(f"background:{theme_tokens.BG_INPUT}; border-radius:8px;")
        self._track.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._track.setMinimumWidth(100)
        track_layout = QHBoxLayout(self._track)
        track_layout.setContentsMargins(0, 0, 0, 0)
        track_layout.setSpacing(0)

        self._fill = QFrame(self._track)
        self._fill.setFixedHeight(16)
        self._fill.setStyleSheet(f"background:{tier_bg}; border-radius:8px;")
        self._fill.setVisible(False)
        track_layout.addWidget(self._fill)

        root.addWidget(self._track, 1)

        # Count label
        self._count = QLabel(str(count))
        self._count.setObjectName("tierCount")
        self._count.setFixedWidth(50)
        self._count.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._count.setStyleSheet(f"color:{theme_tokens.TEXT_PRIMARY}; font-size:13px; font-weight:700;")
        root.addWidget(self._count, 0)

        self._set_count(count)

    def set_value(self, count: int, maximum: int | None = None) -> None:
        if maximum is not None:
            self._max = maximum
        self._set_count(count)

    def _set_count(self, count: int) -> None:
        fraction = (count / self._max) if self._max > 0 else 0.0
        track_width = self._track.width()
        if track_width > 0:
            fill_width = max(0, int(track_width * fraction))
            self._fill.setFixedWidth(fill_width)
            self._fill.setVisible(fraction > 0)
        else:
            self._fill.setFixedWidth(0)
            self._fill.setVisible(False)
        self._count.setText(str(count))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        fraction = (self._count.text().__int__() / self._max) if self._max > 0 else 0.0
        track_width = self._track.width()
        if track_width > 0:
            fill_width = max(0, int(track_width * fraction))
            self._fill.setFixedWidth(fill_width)
            self._fill.setVisible(fraction > 0)

    def update_theme(self) -> None:
        reduce_effects = ThemeManager.instance().reduce_effects
        tier_bg = tier_color(self._tier) if not reduce_effects else theme_tokens.ACCENT
        self._label.setStyleSheet(f"color:{tier_bg}; font-size:13px; font-weight:700;")
        self._fill.setStyleSheet(f"background:{tier_bg}; border-radius:8px;")


class _DonutChart(QFrame):
    """A native QPainter donut chart showing the category split."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("donutChart")
        self._data = {}
        self._total = 0
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(160)
        self.setMaximumHeight(220)
        self.setMinimumWidth(0)

    def set_data(self, data: dict[str, int]) -> None:
        self._data = data
        self._total = sum(data.values())
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(8, 8, -8, -8)

        if self._total == 0 or not self._data:
            painter.setPen(QColor(theme_tokens.TEXT_MUTED))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "No data")
            return

        reduce_effects = ThemeManager.instance().reduce_effects
        ring_width = 18 if not reduce_effects else 14
        ring_gap = 4 if not reduce_effects else 2

        # Draw a ring for each category (outer to inner)
        radius = min(rect.width(), rect.height()) / 2
        center_x = rect.center().x()
        center_y = rect.center().y()

        categories = [MEDIA_ANIME, MEDIA_MANGA, MEDIA_MANHWA, MEDIA_MANHUA]
        for i, category in enumerate(categories):
            count = self._data.get(category, 0)
            if count <= 0:
                continue
            fraction = count / self._total
            if fraction <= 0:
                continue

            color_str = _CATEGORY_COLORS.get(category, "#888888")
            color = QColor(color_str)
            if reduce_effects:
                color = color.darker(120)

            pen = QPen(color)
            pen.setWidth(ring_width)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            painter.setPen(pen)

            r = radius - i * (ring_width + ring_gap)
            if r <= 0:
                break

            start_angle = 90 * 16  # Start at top
            span_angle = int(-360 * fraction * 16)  # Negative for clockwise

            painter.drawArc(
                int(center_x - r), int(center_y - r),
                int(2 * r), int(2 * r),
                start_angle, span_angle
            )

        # Center total label
        painter.setPen(QColor(theme_tokens.TEXT_PRIMARY))
        font = painter.font()
        font.setPointSize(20)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(self._total))

        # Subtitle
        font.setPointSize(10)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor(theme_tokens.TEXT_MUTED))
        subtitle_rect = QRectF(rect.left(), rect.center().y() + 14, rect.width(), 24)
        painter.drawText(subtitle_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, "Total Media")


class _CategoryDistBar(QWidget):
    """Horizontal bar for media category distribution (alternative to donut)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._data = {}
        self._total = 0
        self.setFixedHeight(32)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(0)

    def set_data(self, data: dict[str, int]) -> None:
        self._data = data
        self._total = sum(data.values())
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(0, 6, 0, -6)

        if self._total == 0 or not self._data:
            return

        categories = [MEDIA_ANIME, MEDIA_MANGA, MEDIA_MANHWA, MEDIA_MANHUA]
        x = rect.left()
        for category in categories:
            count = self._data.get(category, 0)
            if count <= 0:
                continue
            fraction = count / self._total
            if fraction <= 0:
                continue

            color_str = _CATEGORY_COLORS.get(category, "#888888")
            color = QColor(color_str)
            w = max(1, int(rect.width() * fraction))
            r = QRectF(x, rect.top(), w, rect.height())
            painter.fillRect(r, color)
            x += w

        # Draw labels below
        painter.setPen(QColor(theme_tokens.TEXT_MUTED))
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)
        x = rect.left()
        for category in categories:
            count = self._data.get(category, 0)
            if count <= 0:
                continue
            fraction = count / self._total
            w = max(1, int(rect.width() * fraction))
            label = category.capitalize()[:4]
            painter.drawText(
                QRectF(x, rect.bottom() + 2, w, 14),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                label
            )
            x += w


class _MediaCardMini(QFrame):
    """A compact media card for upcoming/in-progress section."""

    def __init__(self, item, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("miniCard")
        self.setFixedHeight(72)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(
            f"#miniCard {{ background:{theme_tokens.BG_PANEL}; border:1px solid {theme_tokens.BORDER};"
            f" border-radius:8px; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # Poster placeholder
        self._poster = QLabel()
        self._poster.setFixedSize(48, 72)
        self._poster.setStyleSheet(f"background:{theme_tokens.BG_INPUT}; border-radius:6px;")
        self._poster.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._poster.setText("▦")
        self._poster.setStyleSheet(f"background:{theme_tokens.BG_INPUT}; border-radius:6px; color:{theme_tokens.TEXT_MUTED}; font-size:16px;")
        layout.addWidget(self._poster, 0)

        # Info
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(2)

        self._title = _ElidingLabel(item.title)
        self._title.setStyleSheet(f"color:{theme_tokens.TEXT_PRIMARY}; font-size:12px; font-weight:600;")
        info_layout.addWidget(self._title)

        # Type and status
        meta_parts = []
        if hasattr(item, 'media_type') and item.media_type:
            meta_parts.append(item.media_type)
        elif hasattr(item, 'format') and item.format:
            meta_parts.append(item.format)
        if hasattr(item, 'category'):
            meta_parts.append(item.category.capitalize())
        meta_text = " · ".join(meta_parts) if meta_parts else ""
        self._meta = QLabel(meta_text)
        self._meta.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:10px;")
        info_layout.addWidget(self._meta)

        # Progress
        if hasattr(item, 'episodes') and item.episodes:
            total = item.episodes
            watched = item.episodes_watched or 0
            progress_text = f"Ep {watched} / {total}"
            percent = min(100, round(watched * 100 / total)) if total else 0
        elif hasattr(item, 'chapters') and item.chapters:
            total = item.chapters
            read = item.chapters_read or 0
            progress_text = f"Ch {read} / {total}"
            percent = min(100, round(read * 100 / total)) if total else 0
        else:
            progress_text = "—"
            percent = 0

        self._progress_text = QLabel(progress_text)
        self._progress_text.setStyleSheet(f"color:{theme_tokens.TEXT_SECONDARY}; font-size:10px;")
        info_layout.addWidget(self._progress_text)

        # Progress bar
        self._progress_bar = QFrame()
        self._progress_bar.setFixedHeight(4)
        self._progress_bar.setStyleSheet(f"background:{theme_tokens.BG_INPUT}; border-radius:2px;")
        bar_layout = QHBoxLayout(self._progress_bar)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        bar_layout.setSpacing(0)

        self._progress_fill = QFrame(self._progress_bar)
        self._progress_fill.setFixedHeight(4)
        fill_color = theme_tokens.ACCENT
        self._progress_fill.setStyleSheet(f"background:{fill_color}; border-radius:2px;")
        self._progress_fill.setVisible(percent > 0)
        bar_layout.addWidget(self._progress_fill)

        info_layout.addWidget(self._progress_bar)
        layout.addLayout(info_layout, 1)

        # Tier badge
        if item.tier:
            tier_bg = tier_color(item.tier)
            tier_badge = QLabel(item.tier)
            tier_badge.setFixedWidth(40)
            tier_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tier_badge.setStyleSheet(
                f"background:{tier_bg}; color:{theme_tokens.TEXT_ON_ACCENT}; "
                f"border-radius:6px; font-size:10px; font-weight:700; padding:2px 4px;"
            )
            layout.addWidget(tier_badge, 0)

        # Sync fill
        self._sync_progress(percent)

    def _sync_progress(self, percent: int) -> None:
        if percent > 0 and self._progress_bar.width() > 0:
            fill_width = max(4, int(self._progress_bar.width() * percent / 100))
            self._progress_fill.setFixedWidth(fill_width)
            self._progress_fill.show()
        else:
            self._progress_fill.setFixedWidth(0)
            self._progress_fill.hide()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        # Re-calculate progress from fill width
        pass


class DashboardPanel(QFrame):
    """Full-page analytics dashboard for the AnimeVault library."""

    refresh_requested = Signal()
    back_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("dashboardPanel")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._kpi_cards: dict[str, _KPICard] = {}
        self._anime_status_rows: dict[str, _BarRow] = {}
        self._literature_status_rows: dict[str, _BarRow] = {}
        self._genre_rows: list[_BarRow] = []
        self._tier_rows: dict[str, _TierBarRow] = {}
        self._upcoming_cards: list[_MediaCardMini] = []

        # Main scroll area
        scroll = QScrollArea()
        scroll.setObjectName("dashboardScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self._content = QWidget()
        self._content.setObjectName("dashboardContent")
        self._content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(24, 24, 24, 24)
        content_layout.setSpacing(20)

        scroll.setWidget(self._content)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(scroll)

        # Build sections
        self._build_header(content_layout)
        self._build_kpi_cards(content_layout)
        self._build_media_distribution(content_layout)
        self._build_status_distribution(content_layout)
        self._build_tier_distribution(content_layout)
        self._build_genre_distribution(content_layout)
        self._build_upcoming_section(content_layout)
        self._build_recent_activity(content_layout)
        self._build_recommendations_section(content_layout)

        # Connect to theme changes
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)
        ThemeManager.instance().effects_changed.connect(self._on_effects_changed)
        ThemeManager.instance().liquid_glass_changed.connect(self._on_liquid_glass_changed)

    def _build_header(self, root: QVBoxLayout, view: str = "overview") -> None:
        header = QWidget()
        header.setFixedHeight(80)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # Category navigation
        self._nav_buttons = {}
        views = ["overview", "anime", "manga", "manhwa", "manhua"]
        view_labels = {
            "overview": "Overview",
            "anime": "Anime",
            "manga": "Manga",
            "manhwa": "Manhwa",
            "manhua": "Manhua",
        }
        for i, v in enumerate(views):
            btn = QPushButton(view_labels[v])
            btn.setObjectName(f"navBtn{v.capitalize()}")
            btn.setCheckable(True)
            btn.setFixedSize(100, 36)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, view=v: self._switch_view(view))
            if v == view:
                btn.setChecked(True)
            layout.addWidget(btn, 0)
            self._nav_buttons[v] = btn

        layout.addStretch(1)

        # Back button (always visible)
        self._back_btn = QPushButton("← Back to Library")
        self._back_btn.setObjectName("backButton")
        self._back_btn.setFixedHeight(36)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.clicked.connect(self.back_requested.emit)
        layout.addWidget(self._back_btn, 0)

        layout.addStretch(1)

        title = QLabel("Library Dashboard")
        title.setObjectName("dashboardTitle")
        title.setStyleSheet(
            f"color:{theme_tokens.TEXT_PRIMARY}; font-size:22px; font-weight:700;"
        )
        layout.addWidget(title, 0)

        subtitle = _ElidingLabel("Your collection at a glance")
        subtitle.setObjectName("dashboardSubtitle")
        subtitle.setStyleSheet(
            f"color:{theme_tokens.TEXT_MUTED}; font-size:13px;"
        )
        layout.addWidget(subtitle, 1)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setObjectName("primaryButton")
        self._refresh_btn.setFixedHeight(36)
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.clicked.connect(self.refresh_requested.emit)
        layout.addWidget(self._refresh_btn, 0)

        self._last_updated = QLabel("Last updated: just now")
        self._last_updated.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:11px;")
        layout.addWidget(self._last_updated, 0)

        root.addWidget(header)

    def _build_kpi_cards(self, root: QVBoxLayout) -> None:
        kpi_container = QWidget()
        kpi_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        kpi_layout = QGridLayout(kpi_container)
        kpi_layout.setContentsMargins(0, 0, 0, 0)
        kpi_layout.setHorizontalSpacing(16)
        kpi_layout.setVerticalSpacing(16)

        # Define KPI cards: (key, label, icon, color)
        kpis = [
            ("total_media", "Total Media", "📚", theme_tokens.ACCENT),
            ("anime_total", "Total Anime", "📺", _CATEGORY_COLORS[MEDIA_ANIME]),
            ("manga_total", "Total Manga", "📖", _CATEGORY_COLORS[MEDIA_MANGA]),
            ("manhwa_total", "Total Manhwa", "📘", _CATEGORY_COLORS[MEDIA_MANHWA]),
            ("manhua_total", "Total Manhua", "📙", _CATEGORY_COLORS[MEDIA_MANHUA]),
            ("favorites", "Favorites", "⭐", "#fbbf24"),
        ]

        # 3 columns, 2 rows
        for idx, (key, label, icon, color) in enumerate(kpis):
            card = _KPICard(label, "0", icon, color)
            self._kpi_cards[key] = card
            row = idx // 3
            col = idx % 3
            kpi_layout.addWidget(card, row, col)

        root.addWidget(kpi_container)

    def _build_media_distribution(self, root: QVBoxLayout) -> None:
        """Media distribution section with donut chart and horizontal bars."""
        frame, frame_layout = _panel("Media Distribution")

        # Donut chart
        self._donut = _DonutChart()
        self._donut.setStyleSheet(
            f"background:{theme_tokens.BG_PANEL}; border-radius:12px; "
            f"border:1px solid {theme_tokens.BORDER};"
        )
        frame_layout.addWidget(self._donut, 0)

        # Horizontal category bars
        self._cat_dist_bar = _CategoryDistBar()
        frame_layout.addWidget(self._cat_dist_bar, 0)

        # Category counts detail
        self._category_counts = QWidget()
        counts_layout = QHBoxLayout(self._category_counts)
        counts_layout.setContentsMargins(0, 8, 0, 0)
        counts_layout.setSpacing(16)
        counts_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self._category_count_labels = {}
        for cat in [MEDIA_ANIME, MEDIA_MANGA, MEDIA_MANHWA, MEDIA_MANHUA]:
            color = _CATEGORY_COLORS[cat]
            label = QLabel(f"{cat.capitalize()}: 0")
            label.setStyleSheet(f"color:{theme_tokens.TEXT_SECONDARY}; font-size:11px; font-weight:500;")
            label.setMinimumWidth(80)
            self._category_count_labels[cat] = label
            counts_layout.addWidget(label)

        frame_layout.addWidget(self._category_counts)
        root.addWidget(frame, 0)

    def _build_status_distribution(self, root: QVBoxLayout) -> None:
        """Library status section with separate anime and literature."""
        frame, frame_layout = _panel("Library Status")

        # Anime status
        anime_frame, anime_layout = _panel("Anime")
        anime_statuses = [
            ("watching", "Watching", "#22d3ee"),
            ("completed", "Completed", "#4ade80"),
            ("plan_to_watch", "Plan to Watch", "#60a5fa"),
            ("on_hold", "On Hold", "#fbbf24"),
            ("dropped", "Dropped", "#f87171"),
        ]

        for key, label, color in anime_statuses:
            row = _BarRow(label, 0, 1, color)
            self._anime_status_rows[key] = row
            anime_layout.addWidget(row, 0)

        frame_layout.addWidget(anime_frame)

        # Literature status
        lit_frame, lit_layout = _panel("Manga / Manhwa / Manhua")
        literature_statuses = [
            ("watching", "Reading", "#22d3ee"),
            ("completed", "Completed", "#4ade80"),
            ("plan_to_watch", "Plan to Read", "#60a5fa"),
            ("on_hold", "On Hold", "#fbbf24"),
            ("dropped", "Dropped", "#f87171"),
        ]

        self._literature_status_rows = {}
        for key, label, color in literature_statuses:
            row = _BarRow(label, 0, 1, color)
            self._literature_status_rows[key] = row
            lit_layout.addWidget(row, 0)

        frame_layout.addWidget(lit_frame)
        root.addWidget(frame, 1)

    def _build_tier_distribution(self, root: QVBoxLayout) -> None:
        """Major visual priority: horizontal tier distribution bars."""
        frame, frame_layout = _panel("Tier Distribution")

        self._tier_container = QWidget()
        self._tier_layout = QVBoxLayout(self._tier_container)
        self._tier_layout.setContentsMargins(0, 0, 0, 0)
        self._tier_layout.setSpacing(6)

        # Create rows for all tiers (SSS to F)
        for tier in TIERS:
            row = _TierBarRow(tier, 0, 1)
            self._tier_rows[tier] = row
            self._tier_layout.addWidget(row, 0)

        frame_layout.addWidget(self._tier_container)
        root.addWidget(frame, 1)

    def _build_genre_distribution(self, root: QVBoxLayout) -> None:
        frame, frame_layout = _panel("Top Genres")
        self._genre_frame = frame
        self._genre_layout = frame_layout
        root.addWidget(frame, 1)

    def _build_upcoming_section(self, root: QVBoxLayout) -> None:
        frame, frame_layout = _panel("Up Next — In Progress")

        self._upcoming_container = QWidget()
        self._upcoming_layout = QVBoxLayout(self._upcoming_container)
        self._upcoming_layout.setContentsMargins(0, 0, 0, 0)
        self._upcoming_layout.setSpacing(8)

        placeholder = QLabel("No in-progress titles. Start watching or reading!")
        placeholder.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:12px; padding:24px;")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._upcoming_layout.addWidget(placeholder)

        frame_layout.addWidget(self._upcoming_container)
        root.addWidget(frame, 0)

    def _build_recent_activity(self, root: QVBoxLayout) -> None:
        frame, frame_layout = _panel("Recent Activity")

        self._activity_container = QWidget()
        self._activity_layout = QVBoxLayout(self._activity_container)
        self._activity_layout.setContentsMargins(0, 0, 0, 0)
        self._activity_layout.setSpacing(6)

        placeholder = QLabel("Activity history will appear here as you update your library.")
        placeholder.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:12px; padding:24px;")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._activity_layout.addWidget(placeholder)

        frame_layout.addWidget(self._activity_container)
        root.addWidget(frame, 0)

    def _build_recommendations_section(self, root: QVBoxLayout) -> None:
        frame, frame_layout = _panel("Recommendations")

        self._rec_container = QWidget()
        self._rec_layout = QHBoxLayout(self._rec_container)
        self._rec_layout.setContentsMargins(0, 0, 0, 0)
        self._rec_layout.setSpacing(12)

        placeholder = QLabel("Recommendations will appear here based on your library.")
        placeholder.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:12px; padding:24px;")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._rec_layout.addWidget(placeholder)

        frame_layout.addWidget(self._rec_container)
        root.addWidget(frame, 0)

    def _on_theme_changed(self, theme_id: str) -> None:
        self._refresh_styles()
        self.apply_theme()

    def _on_effects_changed(self, enabled: bool) -> None:
        self._refresh_styles()
        for row in self._tier_rows.values():
            row.update_theme()

    def _on_liquid_glass_changed(self, enabled: bool) -> None:
        self._refresh_styles()
        for row in self._tier_rows.values():
            row.update_theme()

    def _switch_view(self, view: str) -> None:
        """Switch between the five dashboard views."""
        self._view = view

        # Update navigation buttons
        for v, btn in self._nav_buttons.items():
            btn.setChecked(v == view)

        # Clear existing content sections
        self._clear_view()

        # Build the selected view
        if view == "overview":
            self._build_overview_view()
        elif view == "anime":
            self._build_anime_view()
        elif view == "manga":
            self._build_manga_view()
        elif view == "manhwa":
            self._build_manhwa_view()
        elif view == "manhua":
            self._build_manhua_view()

        # Update nav button states
        self._nav_buttons[view].setChecked(True)

    def _clear_view(self) -> None:
        """Remove all child widgets from the main content area."""
        # Remove all widgets from root layout except header and kpis
        while self._root_layout.count():
            item = self._root_layout.takeAt(0)
            widget = item.widget()
            if widget and widget is not self._header and widget is not self._kpi_container:
                widget.setParent(None)
                widget.deleteLater()

    def _build_overview_view(self) -> None:
        """Build the Combined Overview Dashboard view."""
        # ... (overview content)
        pass

    def _build_anime_view(self) -> None:
        """Build the Anime-specific Dashboard view."""
        # ... (anime content)
        pass

    def _build_manga_view(self) -> None:
        """Build the Manga-specific Dashboard view."""
        # ... (manga content)
        pass

    def _build_manhwa_view(self) -> None:
        """Build the Manhwa-specific Dashboard view."""
        # ... (manhwa content)
        pass

    def _build_manhua_view(self) -> None:
        """Build the Manhua-specific Dashboard view."""
        # ... (manhua content)
        pass

    def _refresh_styles(self) -> None:
        """Refresh inline styles that depend on theme tokens."""
        # Panel frames
        for frame in self.findChildren(QFrame):
            if frame.objectName() == "statPanel":
                frame.setStyleSheet(
                    f"#statPanel {{ background:{theme_tokens.BG_PANEL}; "
                    f"border:1px solid {theme_tokens.BORDER}; border-radius:12px; }}"
                )
            elif frame.objectName() == "kpiCard":
                frame.setStyleSheet(
                    f"#kpiCard {{ background:{theme_tokens.BG_PANEL}; border:1px solid {theme_tokens.BORDER};"
                    f" border-radius:10px; }}"
                )
            elif frame.objectName() == "miniCard":
                frame.setStyleSheet(
                    f"#miniCard {{ background:{theme_tokens.BG_PANEL}; border:1px solid {theme_tokens.BORDER};"
                    f" border-radius:8px; }}"
                )

        # KPI cards
        for card in self._kpi_cards.values():
            card._label.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:11px; font-weight:500;")
            card._value.setStyleSheet(f"color:{theme_tokens.TEXT_PRIMARY}; font-size:28px; font-weight:700;")

        # Status rows
        for row in self._anime_status_rows.values():
            row._count.setStyleSheet(f"color:{theme_tokens.TEXT_PRIMARY}; font-size:12px; font-weight:600;")
            if hasattr(row, '_percent'):
                row._percent.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:11px;")
        for row in self._literature_status_rows.values():
            row._count.setStyleSheet(f"color:{theme_tokens.TEXT_PRIMARY}; font-size:12px; font-weight:600;")
            if hasattr(row, '_percent'):
                row._percent.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:11px;")

        # Category count labels
        for label in self._category_count_labels.values():
            label.setStyleSheet(f"color:{theme_tokens.TEXT_SECONDARY}; font-size:11px; font-weight:500;")

    def apply_theme(self) -> None:
        """Public method to refresh theme-dependent styles."""
        self._refresh_styles()
        self._donut.update()
        self._cat_dist_bar.update()

    def refresh(self, animes: list, literature: list) -> None:
        """Update all dashboard components with fresh data."""
        from datetime import datetime

        self._last_updated.setText(f"Last updated: {datetime.now().strftime('%H:%M:%S')}")

        # KPI Cards
        anime_status = Counter(a.status for a in animes)
        lit_counts = Counter(item.category for item in literature)
        total_media = len(animes) + len(literature)
        favorites = sum(1 for a in animes if a.favorite) + sum(1 for l in literature if l.favorite)

        self._kpi_cards["total_media"].set_value(str(total_media))
        self._kpi_cards["anime_total"].set_value(str(len(animes)))
        self._kpi_cards["manga_total"].set_value(str(lit_counts.get(MEDIA_MANGA, 0)))
        self._kpi_cards["manhwa_total"].set_value(str(lit_counts.get(MEDIA_MANHWA, 0)))
        self._kpi_cards["manhua_total"].set_value(str(lit_counts.get(MEDIA_MANHUA, 0)))
        self._kpi_cards["favorites"].set_value(str(favorites))

        # Media distribution
        by_category = {
            MEDIA_ANIME: len(animes),
            MEDIA_MANGA: lit_counts.get(MEDIA_MANGA, 0),
            MEDIA_MANHWA: lit_counts.get(MEDIA_MANHWA, 0),
            MEDIA_MANHUA: lit_counts.get(MEDIA_MANHUA, 0),
        }
        self._donut.set_data(by_category)
        self._cat_dist_bar.set_data(by_category)

        for cat, label in self._category_count_labels.items():
            label.setText(f"{CATEGORY_LABELS[cat]}: {by_category[cat]}")

        # Anime status bars
        max_anime_status = max(anime_status.values()) if anime_status else 1
        for key, row in self._anime_status_rows.items():
            count = anime_status.get(key, 0)
            row.set_value(count, max(max_anime_status, count))

        # Literature status bars
        lit_status = Counter(item.status for item in literature)
        max_lit_status = max(lit_status.values()) if lit_status else 1
        for key, row in self._literature_status_rows.items():
            count = lit_status.get(key, 0)
            row.set_value(count, max(max_lit_status, count))

        # Genre distribution
        genre_counter: Counter[str] = Counter()
        for a in animes:
            genre_counter.update(g for g in (a.genres or []) if g)
        for item in literature:
            genre_counter.update(g for g in (item.genres or []) if g)

        self._clear(self._genre_layout)
        if not genre_counter:
            placeholder = QLabel("No genres yet")
            placeholder.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:12px; padding:16px;")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._genre_layout.addWidget(placeholder)
        else:
            top = genre_counter.most_common(10)
            maximum = top[0][1] if top else 1
            for index, (genre, count) in enumerate(top):
                color = _GENRE_BAR_COLORS[index % len(_GENRE_BAR_COLORS)]
                row = _BarRow(genre, count, maximum, color)
                self._genre_rows.append(row)
                self._genre_layout.addWidget(row, 0)

        # Tier distribution
        tier_counter: Counter[str] = Counter()
        for a in animes:
            if a.tier:
                tier_counter[a.tier.upper()] += 1
        for item in literature:
            if item.tier:
                tier_counter[item.tier.upper()] += 1

        maximum = max(tier_counter.values()) if tier_counter else 1
        for tier in TIERS:
            count = tier_counter.get(tier, 0)
            row = self._tier_rows[tier]
            row.set_value(count, maximum)

        # Up Next - In Progress
        self._clear(self._upcoming_layout)
        in_progress = []
        for a in animes:
            if a.status == "watching" and (a.episodes or 0) > 0:
                in_progress.append(a)
        for item in literature:
            if item.status == "watching" and (item.chapters or 0) > 0:
                in_progress.append(item)

        if not in_progress:
            placeholder = QLabel("No in-progress titles. Start watching or reading!")
            placeholder.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:12px; padding:24px;")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._upcoming_layout.addWidget(placeholder)
        else:
            # Sort by last_watched/last_read descending
            in_progress.sort(key=lambda x: getattr(x, 'last_watched', '') or getattr(x, 'last_read', ''), reverse=True)
            for item in in_progress[:8]:
                card = _MediaCardMini(item)
                self._upcoming_cards.append(card)
                self._upcoming_layout.addWidget(card)

        # Recent Activity (based on timestamps)
        self._clear(self._activity_layout)
        activities = []

        for a in animes:
            if a.last_watched:
                activities.append(("watched", a.title, a.last_watched, "anime", a.tier))
            if a.completed_date:
                activities.append(("completed", a.title, a.completed_date, "anime", a.tier))
            if a.first_watched and not a.last_watched:
                activities.append(("added", a.title, a.first_watched, "anime", a.tier))

        for item in literature:
            if item.last_read:
                activities.append(("read", item.title, item.last_read, item.category, item.tier))
            if item.completed_date:
                activities.append(("completed", item.title, item.completed_date, item.category, item.tier))
            if item.first_read and not item.last_read:
                activities.append(("added", item.title, item.first_read, item.category, item.tier))

        if not activities:
            placeholder = QLabel("Activity history will appear here as you update your library.")
            placeholder.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:12px; padding:24px;")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._activity_layout.addWidget(placeholder)
        else:
            # Sort by date descending, take top 10
            activities.sort(key=lambda x: x[2], reverse=True)
            for action, title, date_str, category, tier in activities[:10]:
                act_widget = QWidget()
                act_layout = QHBoxLayout(act_widget)
                act_layout.setContentsMargins(0, 4, 0, 4)
                act_layout.setSpacing(12)

                # Icon and action
                icons = {"watched": "▶", "read": "📖", "completed": "✓", "added": "➕"}
                colors = {"watched": "#22d3ee", "read": "#f59e0b", "completed": "#4ade80", "added": "#60a5fa"}
                icon = icons.get(action, "•")
                color = colors.get(action, theme_tokens.TEXT_SECONDARY)

                icon_label = QLabel(icon)
                icon_label.setStyleSheet(f"color:{color}; font-size:14px;")
                icon_label.setFixedWidth(24)
                act_layout.addWidget(icon_label, 0)

                # Title and category
                text = f"{title}"
                if category:
                    text += f"  ({category.capitalize()})"
                if tier:
                    text += f"  [{tier}]"
                title_label = _ElidingLabel(text)
                title_label.setStyleSheet(f"color:{theme_tokens.TEXT_PRIMARY}; font-size:12px;")
                act_layout.addWidget(title_label, 1)

                # Date
                date_label = QLabel(date_str)
                date_label.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:10px;")
                date_label.setFixedWidth(100)
                date_label.setAlignment(Qt.AlignmentFlag.AlignRight)
                act_layout.addWidget(date_label, 0)

                self._activity_layout.addWidget(act_widget)

        # Recommendations (placeholder - uses existing engine)
        self._clear(self._rec_layout)
        rec_placeholder = QLabel("Recommendations will appear here based on your library.")
        rec_placeholder.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:12px; padding:24px;")
        rec_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._rec_layout.addWidget(rec_placeholder)

    @staticmethod
    def _clear(layout: QVBoxLayout | QHBoxLayout) -> None:
        while layout.count():
            child = layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()


def compute_dashboard(animes: Optional[list] = None, literature: Optional[list] = None):
    """Convenience for tests: the raw numbers the panel displays."""
    animes = animes if animes is not None else Anime.all()
    literature = literature if literature is not None else Literature.all()
    genres: Counter[str] = Counter()
    for a in animes:
        genres.update(a.genres or [])
    for item in literature:
        genres.update(item.genres or [])
    tiers: Counter[str] = Counter()
    for a in animes:
        if a.tier:
            tiers[a.tier] += 1
    for item in literature:
        if item.tier:
            tiers[item.tier] += 1
    by_category = {
        MEDIA_ANIME: len(animes),
        MEDIA_MANGA: sum(1 for item in literature if item.category == MEDIA_MANGA),
        MEDIA_MANHWA: sum(1 for item in literature if item.category == MEDIA_MANHWA),
        MEDIA_MANHUA: sum(1 for item in literature if item.category == MEDIA_MANHUA),
    }
    return {
        "anime": len(animes),
        "literature": len(literature),
        "by_category": by_category,
        "genres": genres.most_common(),
        "tiers": {t: tiers.get(t, 0) for t in TIERS},
    }