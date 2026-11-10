"""Right-hand overview / analytics panel.

Every number here is derived from the database at build time — nothing is
hardcoded.  The panel is rebuilt on demand rather than on a timer, so it
costs nothing when the library is idle.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QSizePolicy,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
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
from animevault.ui.theme import tier_color

logger = logging.getLogger(__name__)

#: Accent dots beside each headline stat.
_STATUS_DOTS = {
    "watching": "#22d3ee",
    "completed": "#4ade80",
    "plan_to_watch": "#60a5fa",
    "on_hold": "#fbbf24",
    "dropped": "#f87171",
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
    layout.setContentsMargins(14, 11, 14, 13)
    layout.setSpacing(8)

    heading = _ElidingLabel(title)
    heading.setObjectName("panelTitle")
    layout.addWidget(heading)
    return frame, layout


class _ElidingLabel(QLabel):
    """A label that never forces its parent wider than intended.

    Qt stylesheets already elide overflowing text, so this only has to
    stop the label from *demanding* its full text width.  Setting an
    ignored horizontal size policy plus a small minimum width achieves
    that without overriding size hints, which destabilises layout.
    """

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(text, parent)
        self.setToolTip(text)
        self.setMinimumWidth(0)
        self.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )




class _StatRow(QWidget):
    """One dot + label + value line."""

    def __init__(self, label: str, dot: Optional[str] = None) -> None:
        super().__init__()
        self.setToolTip(label)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        if dot:
            dot_label = QLabel("●")
            dot_label.setStyleSheet(f"color:{dot}; font-size:11px;")
            dot_label.setFixedWidth(12)
            row.addWidget(dot_label, 0)

        self._label = _ElidingLabel(label)
        self._label.setObjectName("statLabel")
        row.addWidget(self._label, 1)

        self._value = QLabel("0")
        self._value.setObjectName("statValue")
        self._value.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._value.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred
        )
        row.addWidget(self._value, 0)

    def set_value(self, value) -> None:
        self._value.setText(str(value))


class _BarTrack(QFrame):
    """A bar track whose fill scales to the *available* width.

    The fill is positioned manually rather than laid out, so the row can
    shrink with the sidebar instead of demanding a fixed pixel width
    (which used to push the whole panel past its maximum and clip it).
    """

    def __init__(self, fraction: float, color: str) -> None:
        super().__init__()
        self._fraction = max(0.0, min(1.0, fraction))
        self.setFixedHeight(7)
        self.setStyleSheet(f"background:{theme_tokens.BG_INPUT}; border-radius:3px;")

        self._fill = QFrame(self)
        self._fill.setFixedHeight(7)
        self._fill.setStyleSheet(f"background:{color}; border-radius:3px;")

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_fill()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._sync_fill()

    def _sync_fill(self) -> None:
        """Resize the fill to match the track's current width."""
        width = self.width()
        if self._fraction > 0 and width > 0:
            # Keep a visible stub for tiny non-zero values, but never let
            # the fill exceed its track.
            fill_width = min(width, max(4, int(width * self._fraction)))
            self._fill.setFixedWidth(fill_width)
            self._fill.move(0, 0)
            self._fill.show()
        else:
            self._fill.setFixedWidth(0)
            self._fill.hide()


class _BarRow(QWidget):
    """A labelled horizontal bar, e.g. for genre counts."""

    def __init__(self, label: str, value: int, maximum: int, color: str) -> None:
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(9)

        name = QLabel(label)
        name.setObjectName("statLabel")
        # Elide rather than force the sidebar wider than its maximum.
        name.setMinimumWidth(58)
        name.setMaximumWidth(84)
        name.setToolTip(label)
        self._elide_name(name, label)
        row.addWidget(name, 0)

        fraction = (value / maximum) if maximum > 0 else 0.0
        track = _BarTrack(fraction, color)
        track.setMinimumWidth(24)
        row.addWidget(track, 1)

        count = QLabel(str(value))
        count.setObjectName("statLabel")
        count.setMinimumWidth(18)
        count.setMaximumWidth(34)
        count.setAlignment(Qt.AlignmentFlag.AlignRight)
        row.addWidget(count, 0)

    @staticmethod
    def _elide_name(label: QLabel, text: str) -> None:
        """Shorten *text* with an ellipsis if it will not fit."""
        metrics = label.fontMetrics()
        label.setText(metrics.elidedText(text, Qt.TextElideMode.ElideRight, 84))
        label.setToolTip(text)


class _MiniBar(QWidget):
    """A compact horizontal bar with a label, count and filled track."""

    def __init__(self, label: str, value: int, maximum: int, color: str) -> None:
        super().__init__()
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 4)
        root.setSpacing(8)

        self._name = _ElidingLabel(label)
        self._name.setObjectName("statLabel")
        self._name.setMinimumWidth(70)
        self._name.setMaximumWidth(110)
        self._name.setToolTip(label)
        root.addWidget(self._name, 0)

        fraction = (value / maximum) if maximum > 0 else 0.0
        self._track = QFrame()
        self._track.setFixedHeight(14)
        self._track.setStyleSheet(f"background:{theme_tokens.BG_INPUT}; border-radius:3px;")
        self._fill = QFrame(self._track)
        self._fill.setFixedHeight(14)
        self._fill.setStyleSheet(f"background:{color}; border-radius:3px;")
        self._track_layout = QHBoxLayout(self._track)
        self._track_layout.setContentsMargins(0, 0, 0, 0)
        self._track_layout.addWidget(self._fill)
        root.addWidget(self._track, 1)

        self._count = QLabel(str(value))
        self._count.setObjectName("statLabel")
        self._count.setMinimumWidth(22)
        self._count.setMaximumWidth(34)
        self._count.setAlignment(Qt.AlignmentFlag.AlignRight)
        root.addWidget(self._count, 0)

        self._max = maximum
        self._set_value(value)

    def set_value(self, value: int) -> None:
        self._set_value(value)

    def _set_value(self, value: int) -> None:
        fraction = (value / self._max) if self._max > 0 else 0.0
        self._fill.setFixedWidth(max(0, int(self._track.width() * fraction)))
        self._fill.setVisible(fraction > 0)
        self._count.setText(str(value))


class _TierRow(QWidget):
    """A vertical mini-bar for one tier, from SSS down to F."""

    def __init__(self, tier: str, count: int, maximum: int) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 2, 6, 2)
        root.setSpacing(4)

        self._label = QLabel(tier)
        self._label.setObjectName("statLabel")
        self._label.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:11px;")
        root.addWidget(self._label, 0)

        self._track = QFrame()
        self._track.setFixedHeight(56)
        self._track.setStyleSheet(f"background:{theme_tokens.BG_INPUT}; border-radius:3px;")
        self._track_layout = QVBoxLayout(self._track)
        self._track_layout.setContentsMargins(0, 0, 0, 0)
        self._track_layout.setSpacing(0)
        self._fill = QFrame(self._track)
        self._fill.setFixedHeight(0)
        self._fill.setStyleSheet(f"background:{tier_color(tier)}; border-radius:3px;")
        self._track_layout.addWidget(self._fill)
        root.addWidget(self._track)

        self._count = QLabel(str(count))
        self._count.setObjectName("statLabel")
        self._count.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:11px;")
        self._count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._count)

        self._max = maximum
        self._set_count(count)

    def set_value(self, count: int) -> None:
        self._set_count(count)

    def _set_count(self, count: int) -> None:
        fraction = (count / self._max) if self._max > 0 else 0.0
        self._fill.setFixedHeight(max(0, int(56 * fraction)))
        self._fill.setVisible(fraction > 0)
        self._count.setText(str(count))


class _DonutChart(QFrame):
    """A native QPainter donut chart showing the category split."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("donutChart")
        self._data = {}
        self._total = 0

    def set_data(self, data: dict[str, int]) -> None:
        self._data = data
        self._total = sum(data.values())
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(2, 2, -2, -2)

        if self._total == 0 or not self._data:
            painter.setBrush(QColor(theme_tokens.TEXT_MUTED))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "No data")
            return

        # Draw a ring for each category.
        start_angle = 0
        for category, count in self._data.items():
            if count <= 0:
                continue
            fraction = count / self._total
            if fraction > 0:
                color = QColor(_DONUT_COLORS.get(category, "#888888"))
                pen = QPen(color)
                pen.setWidth(3)
                painter.setPen(pen)
                painter.setBrush(color.withAlpha(80))

                start = start_angle
                sweep = int(360 * fraction * 16)
                rect_f = QRectF(rect)
                rect_f = rect_f.adjusted(4, 4, -4, -4)
                painter.drawPie(rect_f, start, sweep)
                start_angle += fraction

        # Center total label.
        painter.setPen(QColor(theme_tokens.TEXT_MUTED))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter,
                         f"Total\n{self._total}")


class OverviewPanel(QFrame):
    """Redesigned two-column overview dashboard."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("overviewPanel")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"background:{theme_tokens.BG_PANEL}; border-radius:12px;")

        self._rows: dict[str, _StatRow] = {}
        self._category_details: dict[str, QLabel] = {}
        self._columns: QWidget | None = None
        self._left: QWidget | None = None
        self._right: QWidget | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Columns container
        self._columns = QWidget()
        self._columns_layout = QHBoxLayout(self._columns)
        self._columns_layout.setContentsMargins(0, 0, 0, 0)
        self._columns_layout.setSpacing(0)
        self._columns_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Left column
        self._left = QWidget()
        self._left_layout = QVBoxLayout(self._left)
        self._left_layout.setContentsMargins(0, 8, 0, 0)
        self._left_layout.setSpacing(8)

        # Library totals
        self._total_frame, self._total_layout = _panel("Library Totals")
        self._left_layout.addWidget(self._total_frame, 0)
        self._left_layout.addSpacing(8)

        # Literature stats
        self._lit_frame, self._lit_layout = _panel("Manga / Manhwa / Manhua")
        self._left_layout.addWidget(self._lit_frame, 0)
        self._left_layout.addSpacing(8)

        # Right column
        self._right = QWidget()
        self._right_layout = QVBoxLayout(self._right)
        self._right_layout.setContentsMargins(0, 8, 0, 0)
        self._right_layout.setSpacing(8)

        # Genres
        self._genre_frame, self._genre_layout = _panel("Top Genres")
        self._right_layout.addWidget(self._genre_frame, 0)

        # Tiers
        self._tier_frame, self._tier_layout = _panel("Tier Distribution")
        self._right_layout.addWidget(self._tier_frame, 0)

        # Donut chart
        self._donut = _DonutChart()
        self._donut.setObjectName("donutChart")
        self._donut.setStyleSheet(
            f"background:{theme_tokens.BG_PANEL}; border-radius:8px; "
            f"border:1px solid {theme_tokens.BORDER};"
        )
        self._right_layout.addWidget(self._donut, 0)

        # Assemble
        self._columns_layout.addWidget(self._left, 0)
        self._columns_layout.addWidget(self._right, 1)
        root.addWidget(self._columns)

        self._build_static_panels()

    def apply_theme(self) -> None:
        """Refresh inline styles that Qt cannot replace from global QSS."""
        for frame in self.findChildren(QFrame):
            if frame.objectName() == "statPanel":
                frame.setStyleSheet(
                    f"#statPanel {{ background:{theme_tokens.BG_PANEL}; "
                    f"border:1px solid {theme_tokens.BORDER}; border-radius:10px; }}"
                )

    @staticmethod
    def _placeholder(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("statLabel")
        label.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED};")
        return label

    def _build_static_panels(self) -> None:
        # Library totals
        frame, layout = _panel("Library Totals")
        for key, label, dot in [
            ("anime", "Number of Anime", None),
            ("watching", "Watching", "#22d3ee"),
            ("completed", "Completed", "#4ade80"),
            ("plan", "Plan to Watch", "#60a5fa"),
        ]:
            row = _StatRow(label, dot)
            self._rows[key] = row
            layout.addWidget(row, 0)
        self._left_layout.addWidget(frame, 0)

        # Literature stats
        self._lit_frame, self._lit_layout = _panel("Manga / Manhwa / Manhua")
        for key, label, color in [
            ("manga", "Manga", "#f59e0b"),
            ("manhwa", "Manhwa", "#a78bfa"),
            ("manhua", "Manhua", "#f472b6"),
        ]:
            row = _MiniBar(label, 0, 1, color)
            self._rows[key] = row
            self._lit_layout.addWidget(row, 0)
        anime_detail = QLabel("Watching 0 \u00b7 Completed 0 \u00b7 Planned 0")
        anime_detail.setObjectName("categoryStatusSummary")
        anime_detail.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:11px;")
        self._category_details[MEDIA_ANIME] = anime_detail
        self._category_details[MEDIA_MANGA] = anime_detail
        self._category_details[MEDIA_MANHWA] = anime_detail
        self._category_details[MEDIA_MANHUA] = anime_detail
        self._lit_layout.addWidget(anime_detail, 0)
        self._left_layout.addWidget(self._lit_frame, 0)

        self._left_layout.addStretch(1)

    def refresh(self, animes: list, literature: list) -> None:
        anime_status = Counter(a.status for a in animes)
        self._rows["anime"].set_value(len(animes))
        self._rows["watching"].set_value(anime_status.get("watching", 0))
        self._rows["completed"].set_value(anime_status.get("completed", 0))
        self._rows["plan"].set_value(anime_status.get("plan_to_watch", 0))

        lit_counts = Counter(item.category for item in literature)
        self._rows["manga"].set_value(lit_counts.get(MEDIA_MANGA, 0))
        self._rows["manhwa"].set_value(lit_counts.get(MEDIA_MANHWA, 0))
        self._rows["manhua"].set_value(lit_counts.get(MEDIA_MANHUA, 0))

        self._category_details[MEDIA_ANIME].setText(
            "Watching {w} \u00b7 Completed {c} \u00b7 Planned {p}".format(
                w=anime_status.get("watching", 0),
                c=anime_status.get("completed", 0),
                p=anime_status.get("plan_to_watch", 0),
            )
        )
        for category, key in (
            (MEDIA_MANGA, "manga"),
            (MEDIA_MANHWA, "manhwa"),
            (MEDIA_MANHUA, "manhua"),
        ):
            category_status = Counter(
                item.status for item in literature if item.category == category
            )
            self._category_details[key].setText(
                "Reading {r} \u00b7 Completed {c} \u00b7 Planned {p}".format(
                    r=category_status.get("watching", 0),
                    c=category_status.get("completed", 0),
                    p=category_status.get("plan_to_watch", 0),
                )
            )

        self._refresh_genres(animes, literature)
        self._refresh_tiers(animes, literature)
        self._refresh_donut(animes, literature)

    def _refresh_genres(self, animes: list, literature: list) -> None:
        counter: Counter[str] = Counter()
        for a in animes:
            counter.update(g for g in (a.genres or []) if g)
        for item in literature:
            counter.update(g for g in (item.genres or []) if g)

        self._clear(self._genre_layout)
        if not counter:
            self._genre_layout.addWidget(self._placeholder("No genres yet"))
            return

        top = counter.most_common(6)
        maximum = top[0][1] if top else 0
        for index, (genre, count) in enumerate(top):
            color = _GENRE_BAR_COLORS[index % len(_GENRE_BAR_COLORS)]
            self._genre_layout.addWidget(_MiniBar(genre, count, maximum, color))

    def _refresh_tiers(self, animes: list, literature: list) -> None:
        counter: Counter[str] = Counter()
        for a in animes:
            if a.tier:
                counter[a.tier.upper()] += 1
        for item in literature:
            if item.tier:
                counter[item.tier.upper()] += 1

        self._clear(self._tier_layout)
        if not counter:
            self._tier_layout.addWidget(self._placeholder("No tiers assigned"))
            return

        maximum = max(counter.values())
        for tier in TIERS:
            count = counter.get(tier, 0)
            self._tier_layout.addWidget(_TierRow(tier, count, maximum))

    def _refresh_donut(self, animes: list, literature: list) -> None:
        by_category = {
            MEDIA_ANIME: len(animes),
            MEDIA_MANGA: sum(1 for item in literature if item.category == MEDIA_MANGA),
            MEDIA_MANHWA: sum(1 for item in literature if item.category == MEDIA_MANHWA),
            MEDIA_MANHUA: sum(1 for item in literature if item.category == MEDIA_MANHUA),
        }
        self._donut.set_data(by_category)

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