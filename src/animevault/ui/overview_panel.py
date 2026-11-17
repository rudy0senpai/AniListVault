"""Right-hand overview / analytics panel.

A modern, theme-aware analytics dashboard for the AnimeVault library.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Optional

from PySide6.QtCore import QRectF, Qt, QSize
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QFontMetrics
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QSizePolicy,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
    QGridLayout,
)

from animevault.media_types import (
    MEDIA_ANIME,
    MEDIA_MANGA,
    MEDIA_MANHWA,
    MEDIA_MANHUA,
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
        " border-radius:10px; }"
    )
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(6)

    heading = _ElidingLabel(title)
    heading.setObjectName("panelTitle")
    heading.setStyleSheet(f"color:{theme_tokens.TEXT_SECONDARY}; font-weight:600; font-size:11px;")
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
    """A compact Key Performance Indicator card."""

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
        self.setFixedHeight(48)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(40)
        self._color = color or theme_tokens.ACCENT

        self.setStyleSheet(
            f"#kpiCard {{ background:{theme_tokens.BG_PANEL}; border:1px solid {theme_tokens.BORDER};"
            f" border-radius:6px; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(4)

        if icon:
            icon_label = QLabel(icon)
            icon_label.setStyleSheet(f"color:{self._color}; font-size:12px;")
            icon_label.setFixedWidth(16)
            layout.addWidget(icon_label, 0)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(0)

        self._label = _ElidingLabel(label)
        self._label.setObjectName("kpiLabel")
        self._label.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:9px; font-weight:500;")
        text_layout.addWidget(self._label)

        self._value = QLabel(value)
        self._value.setObjectName("kpiValue")
        self._value.setStyleSheet(
            f"color:{theme_tokens.TEXT_PRIMARY}; font-size:14px; font-weight:700;"
        )
        text_layout.addWidget(self._value)

        layout.addLayout(text_layout, 1)

    def set_value(self, value: str) -> None:
        self._value.setText(str(value))

    def set_label(self, label: str) -> None:
        self._label.setText(label)


class _BarTrack(QFrame):
    """A bar track whose fill scales to the available width."""

    def __init__(self, fraction: float, color: str) -> None:
        super().__init__()
        self._fraction = max(0.0, min(1.0, fraction))
        self.setFixedHeight(6)
        self.setStyleSheet(f"background:{theme_tokens.BG_INPUT}; border-radius:3px;")

        self._fill = QFrame(self)
        self._fill.setFixedHeight(6)
        self._fill.setStyleSheet(f"background:{color}; border-radius:3px;")

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_fill()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._sync_fill()

    def _sync_fill(self) -> None:
        width = self.width()
        if self._fraction > 0 and width > 0:
            fill_width = min(width, max(3, int(width * self._fraction)))
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
    """A labelled horizontal bar for genre counts."""

    def __init__(self, label: str, value: int, maximum: int, color: str) -> None:
        super().__init__()
        self._color = color
        self._max = maximum
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        name = QLabel(label)
        name.setObjectName("statLabel")
        name.setMinimumWidth(50)
        name.setMaximumWidth(90)
        name.setToolTip(label)
        metrics = name.fontMetrics()
        name.setText(metrics.elidedText(label, Qt.TextElideMode.ElideRight, 90))
        row.addWidget(name, 0)

        fraction = (value / maximum) if maximum > 0 else 0.0
        self._track = _BarTrack(fraction, color)
        self._track.setMinimumWidth(24)
        row.addWidget(self._track, 1)

        self._count = QLabel(str(value))
        self._count.setObjectName("statLabel")
        self._count.setMinimumWidth(18)
        self._count.setMaximumWidth(30)
        self._count.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._count.setStyleSheet(f"color:{theme_tokens.TEXT_SECONDARY}; font-size:11px;")
        row.addWidget(self._count, 0)

    def set_value(self, value: int) -> None:
        self._count.setText(str(value))
        fraction = (value / self._max) if self._max > 0 else 0.0
        self._track.set_fraction(fraction)


class _TierRow(QWidget):
    """A vertical mini-bar for one tier, from SSS down to F."""

    def __init__(self, tier: str, count: int, maximum: int) -> None:
        super().__init__()
        self._tier = tier
        self._max = maximum
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 2, 4, 2)
        root.setSpacing(3)

        self._label = QLabel(tier)
        self._label.setObjectName("statLabel")
        self._label.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:10px; font-weight:600;")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._label)

        self._track = QFrame()
        self._track.setFixedHeight(48)
        self._track.setStyleSheet(f"background:{theme_tokens.BG_INPUT}; border-radius:3px;")
        self._track_layout = QVBoxLayout(self._track)
        self._track_layout.setContentsMargins(0, 0, 0, 0)
        self._track_layout.setSpacing(0)
        self._fill = QFrame(self._track)
        self._fill.setFixedHeight(0)
        tier_bg = tier_color(tier) if not ThemeManager.instance().reduce_effects else theme_tokens.ACCENT
        self._fill.setStyleSheet(f"background:{tier_bg}; border-radius:3px;")
        self._track_layout.addWidget(self._fill)
        root.addWidget(self._track)

        self._count = QLabel(str(count))
        self._count.setObjectName("statLabel")
        self._count.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:10px;")
        self._count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._count)

        self._set_count(count)

    def set_value(self, count: int) -> None:
        self._set_count(count)

    def _set_count(self, count: int) -> None:
        fraction = (count / self._max) if self._max > 0 else 0.0
        self._fill.setFixedHeight(max(0, int(48 * fraction)))
        self._fill.setVisible(fraction > 0)
        self._count.setText(str(count))


class _DonutChart(QFrame):
    """A native QPainter donut chart showing the category split."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("donutChart")
        self._data = {}
        self._total = 0
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(110)
        self.setMaximumHeight(160)
        self.setMinimumWidth(0)

    def set_data(self, data: dict[str, int]) -> None:
        self._data = data
        self._total = sum(data.values())
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(4, 4, -4, -4)

        if self._total == 0 or not self._data:
            painter.setPen(QColor(theme_tokens.TEXT_MUTED))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "No data")
            return

        reduce_effects = ThemeManager.instance().reduce_effects
        ring_width = 16 if not reduce_effects else 12
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
        font.setPointSize(14)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(self._total))

        # Subtitle
        font.setPointSize(9)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor(theme_tokens.TEXT_MUTED))
        subtitle_rect = QRectF(rect.left(), rect.center().y() + 10, rect.width(), 20)
        painter.drawText(subtitle_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, "Total")


class _CategoryDistBar(QWidget):
    """Horizontal bar for media category distribution (alternative to donut)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._data = {}
        self._total = 0
        self.setFixedHeight(40)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(0)

    def set_data(self, data: dict[str, int]) -> None:
        self._data = data
        self._total = sum(data.values())
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(0, 8, 0, -8)

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
            label = category.capitalize()[:4]  # "Anim", "Mang", "Manh", "Manh"
            painter.drawText(
                QRectF(x, rect.bottom() + 2, w, 14),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                label
            )
            x += w


class OverviewPanel(QFrame):
    """Modern analytics dashboard for the AnimeVault library."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("overviewPanel")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)

        self._kpi_cards: dict[str, _KPICard] = {}
        self._category_bars: dict[str, _BarRow] = {}
        self._category_details: dict[str, QLabel] = {}
        self._genre_rows: list[_BarRow] = []
        self._tier_rows: dict[str, _TierRow] = {}
        # Backward compatibility for tests
        self._category_details: dict[str, QLabel] = {}
        self._rows: dict[str, _StatRow] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        root.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Header
        self._build_header(root)

        # KPI Cards Row
        self._build_kpi_cards(root)

        # Main content area (two columns)
        self._columns = QWidget()
        self._columns.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self._columns.setMinimumWidth(0)
        columns_layout = QHBoxLayout(self._columns)
        columns_layout.setContentsMargins(0, 0, 0, 0)
        columns_layout.setSpacing(8)

        # Left column
        self._left = QWidget()
        self._left.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self._left.setMinimumWidth(0)
        self._left_layout = QVBoxLayout(self._left)
        self._left_layout.setContentsMargins(0, 0, 0, 0)
        self._left_layout.setSpacing(8)

        # Category distribution (donut + bars)
        self._build_category_distribution(self._left_layout)

        # Progress & Status
        self._build_progress_status(self._left_layout)

        # Right column
        self._right = QWidget()
        self._right.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._right.setMinimumWidth(0)
        self._right_layout = QVBoxLayout(self._right)
        self._right_layout.setContentsMargins(0, 0, 0, 0)
        self._right_layout.setSpacing(8)

        # Genre distribution
        self._build_genre_distribution(self._right_layout)

        # Tier distribution
        self._build_tier_distribution(self._right_layout)

        columns_layout.addWidget(self._left, 0)
        columns_layout.addWidget(self._right, 1)
        root.addWidget(self._columns)

        # Connect to theme changes
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)
        ThemeManager.instance().effects_changed.connect(self._on_effects_changed)

    def _build_header(self, root: QVBoxLayout) -> None:
        header = QWidget()
        header.setFixedHeight(40)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title = QLabel("Overview")
        title.setObjectName("dashboardTitle")
        title.setStyleSheet(
            f"color:{theme_tokens.TEXT_PRIMARY}; font-size:16px; font-weight:700;"
        )
        layout.addWidget(title, 1)

        subtitle = _ElidingLabel("Your personal media library analytics")
        subtitle.setObjectName("dashboardSubtitle")
        subtitle.setStyleSheet(
            f"color:{theme_tokens.TEXT_MUTED}; font-size:11px;"
        )
        layout.addWidget(subtitle, 0)

        root.addWidget(header)

    def _build_kpi_cards(self, root: QVBoxLayout) -> None:
        kpi_container = QWidget()
        kpi_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        kpi_layout = QGridLayout(kpi_container)
        kpi_layout.setContentsMargins(0, 0, 0, 0)
        kpi_layout.setHorizontalSpacing(4)
        kpi_layout.setVerticalSpacing(4)

        # Define KPI cards: (key, label, icon, color)
        kpis = [
            ("anime_total", "Anime", "📺", _CATEGORY_COLORS[MEDIA_ANIME]),
            ("anime_watching", "Watching", "👁", "#22d3ee"),
            ("anime_completed", "Completed", "✓", "#4ade80"),
            ("anime_planned", "Plan to Watch", "📋", "#60a5fa"),
            ("manga_total", "Manga", "📖", _CATEGORY_COLORS[MEDIA_MANGA]),
            ("manhwa_total", "Manhwa", "📘", _CATEGORY_COLORS[MEDIA_MANHWA]),
            ("manhua_total", "Manhua", "📙", _CATEGORY_COLORS[MEDIA_MANHUA]),
        ]

        # 3 columns, 3 rows
        for idx, (key, label, icon, color) in enumerate(kpis):
            card = _KPICard(label, "0", icon, color)
            self._kpi_cards[key] = card
            row = idx // 3
            col = idx % 3
            kpi_layout.addWidget(card, row, col)

        root.addWidget(kpi_container)

    def _build_category_distribution(self, layout: QVBoxLayout) -> None:
        frame, frame_layout = _panel("Media Distribution")

        # Donut chart
        self._donut = _DonutChart()
        self._donut.setStyleSheet(
            f"background:{theme_tokens.BG_PANEL}; border-radius:8px; "
            f"border:1px solid {theme_tokens.BORDER};"
        )
        frame_layout.addWidget(self._donut, 0)

        # Horizontal category bars (compact)
        self._cat_dist_bar = _CategoryDistBar()
        frame_layout.addWidget(self._cat_dist_bar, 0)

        layout.addWidget(frame, 0)

    def _build_progress_status(self, layout: QVBoxLayout) -> None:
        frame, frame_layout = _panel("Progress & Status")

        # Anime status bars
        anime_statuses = [
            ("watching", "Watching", "#22d3ee"),
            ("completed", "Completed", "#4ade80"),
            ("plan_to_watch", "Plan to Watch", "#60a5fa"),
            ("on_hold", "On Hold", "#fbbf24"),
            ("dropped", "Dropped", "#f87171"),
        ]

        self._anime_status_rows = {}
        for key, label, color in anime_statuses:
            row = _BarRow(label, 0, 1, color)
            self._anime_status_rows[key] = row
            frame_layout.addWidget(row, 0)

        layout.addWidget(frame, 0)

    def _build_genre_distribution(self, layout: QVBoxLayout) -> None:
        frame, frame_layout = _panel("Top Genres")
        self._genre_frame = frame
        self._genre_layout = frame_layout
        layout.addWidget(frame, 1)

    def _build_tier_distribution(self, layout: QVBoxLayout) -> None:
        frame, frame_layout = _panel("Tier Distribution")
        self._tier_frame = frame
        self._tier_layout = frame_layout
        layout.addWidget(frame, 1)

    def _on_theme_changed(self, theme_id: str) -> None:
        self._refresh_styles()
        self.apply_theme()

    def _on_effects_changed(self, enabled: bool) -> None:
        self._refresh_styles()

    def _refresh_styles(self) -> None:
        """Refresh inline styles that depend on theme tokens."""
        # Panel frames
        for frame in self.findChildren(QFrame):
            if frame.objectName() == "statPanel":
                frame.setStyleSheet(
                    f"#statPanel {{ background:{theme_tokens.BG_PANEL}; "
                    f"border:1px solid {theme_tokens.BORDER}; border-radius:10px; }}"
                )
            elif frame.objectName() == "kpiCard":
                frame.setStyleSheet(
                    f"#kpiCard {{ background:{theme_tokens.BG_PANEL}; border:1px solid {theme_tokens.BORDER};"
                    f" border-radius:8px; }}"
                )

        # KPI cards
        for card in self._kpi_cards.values():
            card._label.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:11px; font-weight:500;")
            card._value.setStyleSheet(f"color:{theme_tokens.TEXT_PRIMARY}; font-size:20px; font-weight:700;")

        # Status rows
        for row in self._anime_status_rows.values():
            row._count.setStyleSheet(f"color:{theme_tokens.TEXT_SECONDARY}; font-size:11px;")

        # Tier rows
        reduce_effects = ThemeManager.instance().reduce_effects
        for tier, row in self._tier_rows.items():
            row._label.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:10px; font-weight:600;")
            row._count.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:10px;")
            tier_bg = tier_color(tier) if not reduce_effects else theme_tokens.ACCENT
            row._fill.setStyleSheet(f"background:{tier_bg}; border-radius:3px;")

    def apply_theme(self) -> None:
        """Public method to refresh theme-dependent styles."""
        self._refresh_styles()
        self._donut.update()
        self._cat_dist_bar.update()

    def refresh(self, animes: list, literature: list) -> None:
        # KPI Cards
        anime_status = Counter(a.status for a in animes)
        self._kpi_cards["anime_total"].set_value(str(len(animes)))
        self._kpi_cards["anime_watching"].set_value(str(anime_status.get("watching", 0)))
        self._kpi_cards["anime_completed"].set_value(str(anime_status.get("completed", 0)))
        self._kpi_cards["anime_planned"].set_value(str(anime_status.get("plan_to_watch", 0)))

        lit_counts = Counter(item.category for item in literature)
        self._kpi_cards["manga_total"].set_value(str(lit_counts.get(MEDIA_MANGA, 0)))
        self._kpi_cards["manhwa_total"].set_value(str(lit_counts.get(MEDIA_MANHWA, 0)))
        self._kpi_cards["manhua_total"].set_value(str(lit_counts.get(MEDIA_MANHUA, 0)))

        # Backward compatibility: populate _category_details
        anime_detail_text = (
            "Watching {w} \u00b7 Completed {c} \u00b7 Planned {p}".format(
                w=anime_status.get("watching", 0),
                c=anime_status.get("completed", 0),
                p=anime_status.get("plan_to_watch", 0),
            )
        )
        # Create labels if they don't exist
        for cat, key in [
            (MEDIA_ANIME, "anime"),
            (MEDIA_MANGA, "manga"),
            (MEDIA_MANHWA, "manhwa"),
            (MEDIA_MANHUA, "manhua"),
        ]:
            if cat not in self._category_details:
                lbl = _ElidingLabel("")
                lbl.setObjectName("categoryStatusSummary")
                lbl.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:11px;")
                self._category_details[cat] = lbl
        self._category_details[MEDIA_ANIME].setText(anime_detail_text)

        for category, key in (
            (MEDIA_MANGA, "manga"),
            (MEDIA_MANHWA, "manhwa"),
            (MEDIA_MANHUA, "manhua"),
        ):
            category_status = Counter(
                item.status for item in literature if item.category == category
            )
            self._category_details[category].setText(
                "Reading {r} \u00b7 Completed {c} \u00b7 Planned {p}".format(
                    r=category_status.get("watching", 0),
                    c=category_status.get("completed", 0),
                    p=category_status.get("plan_to_watch", 0),
                )
            )

        # Category distribution
        by_category = {
            MEDIA_ANIME: len(animes),
            MEDIA_MANGA: sum(1 for item in literature if item.category == MEDIA_MANGA),
            MEDIA_MANHWA: sum(1 for item in literature if item.category == MEDIA_MANHWA),
            MEDIA_MANHUA: sum(1 for item in literature if item.category == MEDIA_MANHUA),
        }
        self._donut.set_data(by_category)
        self._cat_dist_bar.set_data(by_category)

        # Anime status bars
        max_anime_status = max(anime_status.values()) if anime_status else 1
        for key, row in self._anime_status_rows.items():
            count = anime_status.get(key, 0)
            row.set_value(count)
            row._max = max(max_anime_status, count)
            fraction = (count / row._max) if row._max > 0 else 0.0
            row._track.set_fraction(fraction)

        # Genre distribution
        genre_counter: Counter[str] = Counter()
        for a in animes:
            genre_counter.update(g for g in (a.genres or []) if g)
        for item in literature:
            genre_counter.update(g for g in (item.genres or []) if g)

        self._clear(self._genre_layout)
        if not genre_counter:
            placeholder = QLabel("No genres yet")
            placeholder.setObjectName("statLabel")
            placeholder.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:11px;")
            self._genre_layout.addWidget(placeholder)
        else:
            top = genre_counter.most_common(6)
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

        self._clear(self._tier_layout)
        if not tier_counter:
            placeholder = QLabel("No tiers assigned")
            placeholder.setObjectName("statLabel")
            placeholder.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:11px;")
            self._tier_layout.addWidget(placeholder)
        else:
            maximum = max(tier_counter.values())
            for tier in TIERS:
                count = tier_counter.get(tier, 0)
                row = _TierRow(tier, count, maximum)
                self._tier_rows[tier] = row
                self._tier_layout.addWidget(row, 0)

    @staticmethod
    def _clear(layout: QVBoxLayout) -> None:
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