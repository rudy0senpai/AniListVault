"""Grounded analytics data and compact native chart widgets for the dashboard.

All numbers are derived from current AnimeVault model records. No schema
changes, synthetic history, remote calls, or additional chart dependencies are
required.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any, Iterable

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from animevault.media_types import (
    CATEGORY_LABELS,
    MEDIA_ANIME,
    MEDIA_MANGA,
    MEDIA_MANHWA,
    MEDIA_MANHUA,
)
from animevault.ui import theme as theme_tokens

CATEGORIES = (MEDIA_ANIME, MEDIA_MANGA, MEDIA_MANHWA, MEDIA_MANHUA)
STATUSES = ("plan_to_watch", "watching", "completed", "on_hold", "dropped")
_STATUS_LABELS = {
    "plan_to_watch": "Planned",
    "watching": "In progress",
    "completed": "Completed",
    "on_hold": "On hold",
    "dropped": "Dropped",
}


# Chart colors inherit the application tokens while maintaining category identity.
_CHART_COLORS = (
    theme_tokens.ACCENT_VIOLET,
    theme_tokens.ACCENT,
    theme_tokens.ACCENT_AMBER,
    theme_tokens.ACCENT_PINK,
    theme_tokens.ACCENT_SKY,
    theme_tokens.SUCCESS,
    theme_tokens.DANGER,
    theme_tokens.ACCENT_VIOLET_DIM,
    theme_tokens.ACCENT_DIM,
    theme_tokens.WARNING,
)
_CATEGORY_COLORS = {
    MEDIA_ANIME: theme_tokens.ACCENT_SKY,
    MEDIA_MANGA: theme_tokens.ACCENT_AMBER,
    MEDIA_MANHWA: theme_tokens.ACCENT_VIOLET,
    MEDIA_MANHUA: theme_tokens.ACCENT_PINK,
}


def _personal_dates(item: Any) -> list[date]:
    """Return unique, parseable user-progress dates stored on a model."""
    if hasattr(item, "first_watched"):
        names = ("first_watched", "last_watched", "completed_date")
    else:
        names = ("first_read", "last_read", "completed_date")
    found: set[date] = set()
    for name in names:
        raw = str(getattr(item, name, "") or "").strip()
        if not raw:
            continue
        try:
            found.add(date.fromisoformat(raw[:10]))
        except ValueError:
            continue
    return sorted(found)


def _item_format(item: Any, category: str) -> str:
    value = getattr(item, "media_type", "") if category == MEDIA_ANIME else getattr(item, "format", "")
    return str(value or "Unspecified").strip().upper() or "UNSPECIFIED"


def build_dashboard_data(
    animes: Iterable[Any] | None,
    literature: Iterable[Any] | None,
    *,
    category: str = "all",
    status: str = "all",
    media_format: str = "all",
    genre: str = "all",
    activity_window: str = "all",
    today: date | None = None,
) -> dict[str, Any]:
    """Build complete, zero-filled chart data from supplied library records.

    ``activity_window='12m'`` includes only entries with a recorded personal
    progress date in the last 365 days. Missing or invalid dates are never
    inferred from metadata or database row IDs.
    """
    anime_rows = list(animes or ())
    literature_rows = list(literature or ())
    records: list[tuple[str, Any]] = [(MEDIA_ANIME, item) for item in anime_rows]
    records.extend((str(getattr(item, "category", MEDIA_MANGA)), item) for item in literature_rows)

    reference_day = today or date.today()
    cutoff = reference_day - timedelta(days=365) if activity_window == "12m" else None
    selected_category = str(category or "all").casefold()
    selected_status = str(status or "all").casefold()
    selected_format = str(media_format or "all").casefold()
    selected_genre = str(genre or "all").casefold()

    selected: list[tuple[str, Any, list[date]]] = []
    for record_category, item in records:
        if selected_category not in ("all", "") and record_category.casefold() != selected_category:
            continue
        item_status = str(getattr(item, "status", "") or "").casefold()
        if selected_status not in ("all", "") and item_status != selected_status:
            continue
        item_format = _item_format(item, record_category)
        if selected_format not in ("all", "") and item_format.casefold() != selected_format:
            continue
        item_genres = [str(value).strip() for value in (getattr(item, "genres", ()) or ()) if str(value).strip()]
        if selected_genre not in ("all", "") and not any(value.casefold() == selected_genre for value in item_genres):
            continue
        activity_dates = _personal_dates(item)
        if cutoff is not None and not any(cutoff <= value <= reference_day for value in activity_dates):
            continue
        selected.append((record_category, item, activity_dates))

    by_category = {key: 0 for key in CATEGORIES}
    status_counts = {key: 0 for key in STATUSES}
    status_by_category = {key: {value: 0 for value in STATUSES} for key in CATEGORIES}
    format_counts: Counter[str] = Counter()
    genre_counts: Counter[str] = Counter()
    tier_counts: Counter[str] = Counter()
    release_years: Counter[int] = Counter()
    timeline: Counter[str] = Counter()
    heatmap: Counter[tuple[int, int]] = Counter()
    bubbles: Counter[tuple[str, str]] = Counter()
    favorites = 0
    anime_scores: list[float] = []
    episodes_total = episodes_watched = chapters_total = chapters_read = 0

    for record_category, item, activity_dates in selected:
        by_category[record_category] = by_category.get(record_category, 0) + 1
        item_status = str(getattr(item, "status", "") or "")
        if item_status in status_counts:
            status_counts[item_status] += 1
            status_by_category[record_category][item_status] += 1
        format_counts[_item_format(item, record_category)] += 1
        favorites += int(bool(getattr(item, "favorite", False)))
        tier = str(getattr(item, "tier", "") or "").strip().upper()
        if tier:
            tier_counts[tier] += 1
        unique_genres = {str(value).strip() for value in (getattr(item, "genres", ()) or ()) if str(value).strip()}
        for item_genre in unique_genres:
            genre_counts[item_genre] += 1
            bubbles[(record_category, item_genre)] += 1
        for event_date in activity_dates:
            if cutoff is not None and not (cutoff <= event_date <= reference_day):
                continue
            month_key = event_date.strftime("%Y-%m")
            timeline[month_key] += 1
            heatmap[(event_date.year, event_date.month)] += 1
        year = getattr(item, "season_year", None)
        if not year:
            aired = str(getattr(item, "aired_from", "") or "")
            year = int(aired[:4]) if aired[:4].isdigit() else None
        if not year:
            started = str(getattr(item, "started_at", "") or "")
            year = int(started[:4]) if started[:4].isdigit() else None
        if isinstance(year, int) and 1800 <= year <= reference_day.year + 2:
            release_years[year] += 1
        score = getattr(item, "score", None) if record_category == MEDIA_ANIME else None
        if score is not None:
            try:
                anime_scores.append(float(score))
            except (TypeError, ValueError):
                pass
        episodes_total += int(getattr(item, "episodes", 0) or 0) if record_category == MEDIA_ANIME else 0
        episodes_watched += int(getattr(item, "episodes_watched", 0) or 0) if record_category == MEDIA_ANIME else 0
        chapters_total += int(getattr(item, "chapters", 0) or 0) if record_category != MEDIA_ANIME else 0
        chapters_read += int(getattr(item, "chapters_read", 0) or 0) if record_category != MEDIA_ANIME else 0

    bubble_rows = [
        {"category": cat, "genre": item_genre, "count": count}
        for (cat, item_genre), count in sorted(bubbles.items(), key=lambda pair: (-pair[1], pair[0]))[:24]
    ]
    return {
        "records": [(cat, item) for cat, item, _ in selected],
        "total": len(selected),
        "by_category": by_category,
        "status_counts": status_counts,
        "status_by_category": status_by_category,
        "formats": dict(sorted(format_counts.items())),
        "genres": dict(genre_counts.most_common()),
        "tiers": dict(tier_counts),
        "release_years": dict(sorted(release_years.items())),
        "timeline": dict(sorted(timeline.items())),
        "heatmap": dict(heatmap),
        "bubbles": bubble_rows,
        "funnel": {key: status_counts[key] for key in STATUSES},
        "favorites": favorites,
        "average_score": round(sum(anime_scores) / len(anime_scores), 2) if anime_scores else None,
        "rated_anime": len(anime_scores),
        "tiered_items": sum(tier_counts.values()),
        "unique_genres": len(genre_counts),
        "episodes_total": episodes_total,
        "episodes_watched": episodes_watched,
        "chapters_total": chapters_total,
        "chapters_read": chapters_read,
    }


class DashboardChart(QWidget):
    """Lightweight, responsive QPainter chart with readable empty states."""

    def __init__(self, kind: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.kind = kind
        self._data: dict[str, Any] = {}
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setToolTip("Interactive data is filtered by the dashboard ribbon.")

    def set_data(self, data: dict[str, Any]) -> None:
        self._data = data
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))
        area = self.rect().adjusted(12, 8, -12, -8)
        if not self._has_data():
            painter.setPen(QColor(theme_tokens.TEXT_MUTED))
            painter.drawText(area, Qt.AlignmentFlag.AlignCenter, "No matching library data")
            painter.end()
            return
        if self.kind in ("bar", "tiers", "years", "clustered", "funnel"):
            self._paint_bars(painter, area)
        elif self.kind in ("pie", "donut"):
            self._paint_pie(painter, area, self.kind == "donut")
        elif self.kind == "line":
            self._paint_line(painter, area)
        elif self.kind == "heatmap":
            self._paint_heatmap(painter, area)
        elif self.kind == "bubble":
            self._paint_bubbles(painter, area)
        painter.end()

    def _has_data(self) -> bool:
        source_key = {
            "bar": "genres",
            "tiers": "tiers",
            "years": "release_years",
            "clustered": "status_by_category",
            "funnel": "funnel",
            "pie": "formats",
            "donut": "by_category",
            "line": "timeline",
            "heatmap": "heatmap",
            "bubble": "bubbles",
        }.get(self.kind)
        values = self._data.get(source_key, {}) if source_key else {}
        if self.kind == "clustered":
            return any(any(row.values()) for row in values.values())
        return bool(values)

    def _text(self, painter: QPainter, rect: QRectF, text: str, color: str | None = None, size: int = 9, align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter) -> None:
        painter.setPen(QColor(color or theme_tokens.TEXT_SECONDARY))
        font = QFont(self.font())
        font.setPointSize(size)
        painter.setFont(font)
        painter.drawText(rect, align, text)

    def _paint_bars(self, painter: QPainter, rect: QRectF) -> None:
        if self.kind == "clustered":
            cats = [cat for cat in CATEGORIES]
            statuses = [status for status in STATUSES]
            data = self._data["status_by_category"]
            max_value = max((value for row in data.values() for value in row.values()), default=1) or 1
            top = rect.top() + 6
            legend_h = 20.0
            row_h = max(22.0, min(34.0, (rect.height() - legend_h - 24) / max(1, len(cats))))
            label_w = min(74.0, rect.width() * 0.2)
            plot = QRectF(rect.left() + label_w, top, rect.width() - label_w, row_h * len(cats))
            group_h = row_h / len(statuses)
            for ci, cat in enumerate(cats):
                y = top + ci * row_h
                self._text(painter, QRectF(rect.left(), y, label_w - 4, row_h), CATEGORY_LABELS.get(cat, cat), size=8)
                for si, stat in enumerate(statuses):
                    bar_y = y + si * group_h + 2
                    bar_w = max(2.0, plot.width() * data[cat][stat] / max_value)
                    color = QColor(_CHART_COLORS[si % len(_CHART_COLORS)])
                    color.setAlpha(205)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(color)
                    painter.drawRoundedRect(QRectF(plot.left(), bar_y, bar_w, max(3.0, group_h - 3)), 3, 3)
                    if bar_w > 24:
                        self._text(painter, QRectF(plot.left() + bar_w - 26, bar_y, 23, group_h - 3), str(data[cat][stat]), theme_tokens.TEXT_PRIMARY, 7, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            legend_y = rect.bottom() - 13
            legend_gap = rect.width() / len(statuses)
            short_labels = ("Planned", "Active", "Done", "Hold", "Dropped")
            for index, label in enumerate(short_labels):
                x = rect.left() + index * legend_gap
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(_CHART_COLORS[index % len(_CHART_COLORS)]))
                painter.drawRoundedRect(QRectF(x, legend_y + 2, 7, 7), 2, 2)
                self._text(painter, QRectF(x + 10, legend_y - 1, legend_gap - 10, 13), label, size=7)
            return
        if self.kind == "funnel":
            data = self._data["funnel"]
            labels = [_STATUS_LABELS.get(key, key) for key in STATUSES]
            values = [data.get(key, 0) for key in STATUSES]
            max_value = max(values, default=0) or 1
            row_h = rect.height() / max(1, len(labels))
            for idx, (label, value) in enumerate(zip(labels, values)):
                width = rect.width() * 0.72 * value / max_value
                x = rect.center().x() - width / 2
                y = rect.top() + idx * row_h + 3
                height = max(5.0, row_h - 8)
                taper = min(width * 0.08, 10.0)
                color = QColor(_CHART_COLORS[idx % len(_CHART_COLORS)])
                color.setAlpha(210)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                path = QPainterPath()
                path.moveTo(x, y)
                path.lineTo(x + width, y)
                path.lineTo(x + width - taper, y + height)
                path.lineTo(x + taper, y + height)
                path.closeSubpath()
                painter.drawPath(path)
                self._text(painter, QRectF(rect.left(), y, rect.width() * 0.22, height), label, size=8)
                self._text(painter, QRectF(rect.right() - rect.width() * 0.22, y, rect.width() * 0.22, height), str(value), size=8, align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return
        source = "tiers" if self.kind == "tiers" else "release_years" if self.kind == "years" else "genres"
        data = self._data[source]
        values = list(data.items())[-8:] if self.kind == "years" else list(data.items())[:8]
        maximum = max((value for _, value in values), default=1) or 1
        row_h = rect.height() / max(1, len(values))
        label_w = min(112.0, rect.width() * 0.32)
        count_w = 28.0
        for index, (label, value) in enumerate(values):
            y = rect.top() + index * row_h
            self._text(painter, QRectF(rect.left(), y, label_w, row_h), label, size=8)
            track = QRectF(rect.left() + label_w, y + row_h * 0.27, max(4.0, rect.width() - label_w - count_w), max(5.0, row_h * 0.46))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(theme_tokens.BG_INPUT))
            painter.drawRoundedRect(track, 4, 4)
            fill = QRectF(track.left(), track.top(), track.width() * value / maximum, track.height())
            painter.setBrush(QColor(_CHART_COLORS[index % len(_CHART_COLORS)]))
            painter.drawRoundedRect(fill, 4, 4)
            self._text(painter, QRectF(rect.right() - count_w, y, count_w, row_h), str(value), size=8, align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def _paint_pie(self, painter: QPainter, rect: QRectF, donut: bool) -> None:
        data = self._data["by_category"] if donut else self._data["formats"]
        entries = []
        for key, value in data.items():
            if value <= 0:
                continue
            label = CATEGORY_LABELS.get(key, key) if donut else str(key)
            entries.append((label, value))
        if not entries:
            return
        total = sum(value for _, value in entries)
        diameter = min(rect.height() - 8, rect.width() * 0.52)
        diameter = max(60.0, diameter)
        chart = QRectF(rect.left(), rect.center().y() - diameter / 2, diameter, diameter)
        angle = 90 * 16
        for index, (_, value) in enumerate(entries):
            span = round(360 * 16 * value / total)
            painter.setPen(QPen(QColor(theme_tokens.BG_SURFACE), 1))
            painter.setBrush(QColor(_CHART_COLORS[index % len(_CHART_COLORS)]))
            painter.drawPie(chart, angle, -span)
            angle -= span
        if donut:
            hole = chart.adjusted(diameter * 0.28, diameter * 0.28, -diameter * 0.28, -diameter * 0.28)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(theme_tokens.BG_SURFACE))
            painter.drawEllipse(hole)
            self._text(painter, hole, str(total), theme_tokens.TEXT_PRIMARY, 13, Qt.AlignmentFlag.AlignCenter)
        legend_x = chart.right() + 12
        available_w = rect.right() - legend_x
        row_h = rect.height() / max(1, len(entries))
        for index, (label, value) in enumerate(entries):
            y = rect.top() + index * row_h
            color = QColor(_CHART_COLORS[index % len(_CHART_COLORS)])
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QRectF(legend_x, y + row_h * 0.36, 7, 7))
            pct = value * 100 / total
            self._text(painter, QRectF(legend_x + 12, y, max(20.0, available_w - 48), row_h), f"{label}  {value} ({pct:.0f}%)", size=8)

    def _paint_line(self, painter: QPainter, rect: QRectF) -> None:
        values = list(self._data["timeline"].items())[-12:]
        if not values:
            return
        plot = rect.adjusted(24, 14, -8, -24)
        max_value = max(value for _, value in values) or 1
        painter.setPen(QPen(QColor(theme_tokens.BORDER), 1, Qt.PenStyle.DashLine))
        for idx in range(1, 4):
            y = plot.top() + plot.height() * idx / 4
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
        points = []
        for idx, (label, value) in enumerate(values):
            x = plot.left() + (plot.width() * idx / max(1, len(values) - 1))
            y = plot.bottom() - plot.height() * value / max_value
            points.append(QPointF(x, y))
            if idx % max(1, len(values) // 6) == 0 or idx == len(values) - 1:
                month_label = label[5:] if len(label) == 7 else label
                self._text(painter, QRectF(x - 24, plot.bottom() + 4, 48, 16), month_label, size=7, align=Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        pen = QPen(QColor(theme_tokens.ACCENT), 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath(points[0])
        for point in points[1:]:
            path.lineTo(point)
        painter.drawPath(path)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme_tokens.ACCENT))
        for point in points:
            painter.drawEllipse(point, 3.0, 3.0)

    def _paint_heatmap(self, painter: QPainter, rect: QRectF) -> None:
        cells = self._data["heatmap"]
        if not cells:
            return
        years = sorted({year for year, _ in cells})[-5:]
        label_w = 40.0
        gap = 3.0
        cell_w = max(4.0, (rect.width() - label_w - 11 * gap) / 12)
        cell_h = max(9.0, min(20.0, (rect.height() - 8) / max(1, len(years))))
        maximum = max(cells.values()) or 1
        for row, year in enumerate(years):
            y = rect.top() + row * cell_h
            self._text(painter, QRectF(rect.left(), y, label_w - 4, cell_h), str(year), size=8)
            for month in range(1, 13):
                value = cells.get((year, month), 0)
                strength = value / maximum
                color = QColor(theme_tokens.ACCENT)
                color.setAlpha(35 + int(190 * strength))
                x = rect.left() + label_w + (month - 1) * (cell_w + gap)
                cell = QRectF(x, y + 1, cell_w, cell_h - 3)
                painter.setPen(QPen(QColor(theme_tokens.BORDER), 1))
                painter.setBrush(color)
                painter.drawRoundedRect(cell, 3, 3)
                if cell_w >= 18:
                    self._text(painter, cell, str(month), theme_tokens.TEXT_PRIMARY, 7, Qt.AlignmentFlag.AlignCenter)

    def _paint_bubbles(self, painter: QPainter, rect: QRectF) -> None:
        values = self._data["bubbles"][:18]
        if not values:
            return
        max_count = max(value["count"] for value in values) or 1
        rows = 3
        cols = 6
        cell_w = rect.width() / cols
        cell_h = max(20.0, (rect.height() - 18) / rows)
        for index, item in enumerate(values):
            col, row = index % cols, index // cols
            radius = 9 + 17 * (item["count"] / max_count) ** 0.5
            center = QPointF(rect.left() + col * cell_w + cell_w / 2, rect.top() + row * cell_h + cell_h / 2)
            color = QColor(_CATEGORY_COLORS.get(item["category"], _CHART_COLORS[index % len(_CHART_COLORS)]))
            color.setAlpha(150)
            painter.setPen(QPen(QColor(color), 1))
            painter.setBrush(color)
            painter.drawEllipse(center, radius, radius)
            label = item["genre"]
            if len(label) > 11:
                label = label[:10] + "…"
            self._text(painter, QRectF(center.x() - radius + 2, center.y() - 9, radius * 2 - 4, 18), label, theme_tokens.TEXT_PRIMARY, 7, Qt.AlignmentFlag.AlignCenter)
            painter.setPen(QColor(theme_tokens.TEXT_PRIMARY))
            painter.drawText(QRectF(center.x() - 18, center.y() + radius - 3, 36, 12), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, str(item["count"]))
        legend_y = rect.bottom() - 12
        legend_gap = rect.width() / len(CATEGORIES)
        for index, category in enumerate(CATEGORIES):
            x = rect.left() + index * legend_gap
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(_CATEGORY_COLORS[category]))
            painter.drawEllipse(QRectF(x, legend_y + 2, 7, 7))
            self._text(painter, QRectF(x + 10, legend_y - 1, legend_gap - 10, 12), CATEGORY_LABELS[category], size=7)


class ChartPanel(QFrame):
    """Frosted chart container with title, footnote and a native chart canvas."""

    def __init__(self, title: str, kind: str, footnote: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("analyticsChartPanel")
        self.setStyleSheet(
            f"#analyticsChartPanel {{ background:{theme_tokens.GLASS_SURFACE}; border:1px solid {theme_tokens.BORDER}; border-radius:12px; }}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)
        from PySide6.QtWidgets import QLabel

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(f"color:{theme_tokens.TEXT_PRIMARY}; font-size:12px; font-weight:650; background:transparent; border:none;")
        layout.addWidget(self.title_label)
        if footnote:
            note = QLabel(footnote)
            note.setWordWrap(True)
            note.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:9px; background:transparent; border:none;")
            layout.addWidget(note)
        self.chart = DashboardChart(kind)
        layout.addWidget(self.chart, 1)


class DashboardSlicers(QWidget):
    """Compact dashboard ribbon controls, emitting changes for each filter."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QHBoxLayout

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.controls: dict[str, QComboBox] = {}
        for key, label, initial in (
            ("category", "Media", [("All media", "all")] + [(CATEGORY_LABELS[cat], cat) for cat in CATEGORIES]),
            ("status", "Status", [("All statuses", "all")] + [(name.replace("_", " ").title(), name) for name in STATUSES]),
            ("media_format", "Format", [("All formats", "all")]),
            ("genre", "Genre", [("All genres", "all")]),
            ("activity_window", "Recorded dates", [("All dates", "all"), ("Last 12 months", "12m")]),
        ):
            control = QComboBox()
            control.setObjectName(f"dashboardSlicer_{key}")
            control.setMinimumWidth(100)
            control.setMaximumWidth(180)
            for text, value in initial:
                control.addItem(text, value)
            control.setToolTip(label)
            control.currentIndexChanged.connect(lambda _index: self.changed.emit())
            layout.addWidget(control, 1)
            self.controls[key] = control
        layout.addStretch(1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def values(self) -> dict[str, str]:
        return {key: str(control.currentData() or "all") for key, control in self.controls.items()}

    def set_options(self, formats: Iterable[str], genres: Iterable[str]) -> None:
        self._set_options("media_format", "All formats", sorted(formats))
        self._set_options("genre", "All genres", sorted(genres, key=str.casefold))

    def _set_options(self, key: str, all_label: str, values: Iterable[str]) -> None:
        control = self.controls[key]
        selected = str(control.currentData() or "all")
        options = [(all_label, "all")] + [(value.replace("_", " ").title(), value) for value in values]
        control.blockSignals(True)
        control.clear()
        for label, value in options:
            control.addItem(label, value)
        index = control.findData(selected)
        control.setCurrentIndex(index if index >= 0 else 0)
        control.blockSignals(False)

    def connect_changed(self, callback) -> None:
        self.changed.connect(callback)


class SummaryKpiCard(QFrame):
    """A compact, theme-aware metric card for the library header."""

    def __init__(
        self,
        label: str,
        value: str = "0",
        parent: QWidget | None = None,
        *,
        compact: bool = True,
    ) -> None:
        super().__init__(parent)
        self._compact = compact
        self.setObjectName("summaryKpiCard")
        self.setMinimumWidth(108 if compact else 138)
        self.setMaximumHeight(34 if compact else 74)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(
            f"#summaryKpiCard {{ background:{theme_tokens.GLASS_SURFACE}; "
            f"border:1px solid {theme_tokens.BORDER}; border-radius:{8 if compact else 12}px; }}"
        )
        layout = QHBoxLayout(self) if compact else QVBoxLayout(self)
        layout.setContentsMargins(9 if compact else 14, 2 if compact else 8, 9 if compact else 14, 2 if compact else 8)
        layout.setSpacing(7 if compact else 2)
        self._value = QLabel(str(value))
        self._value.setObjectName("summaryKpiValue")
        self._value.setStyleSheet(f"color:{theme_tokens.ACCENT}; font-size:{12 if compact else 17}px; font-weight:700; background:transparent; border:none;")
        self._label = QLabel(label)
        self._label.setObjectName("summaryKpiLabel")
        self._label.setStyleSheet(f"color:{theme_tokens.TEXT_SECONDARY}; font-size:{10 if compact else 9}px; background:transparent; border:none;")
        if compact:
            layout.addWidget(self._value)
            layout.addWidget(self._label)
        else:
            layout.addWidget(self._label)
            layout.addWidget(self._value, 1)

    def set_value(self, value: str | int) -> None:
        self._value.setText(str(value))


class DashboardPanel(QFrame):
    """Responsive analytics dashboard backed only by stored library data."""

    refresh_requested = Signal()
    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from animevault.ui.scroll_animation import ScrollRevealArea

        self.setObjectName("dashboardPanel")
        self._animes: list[Any] = []
        self._literature: list[Any] = []
        self._analytics_data: dict[str, Any] = {}
        self._kpi_cards: dict[str, SummaryKpiCard] = {}
        self._analytics_charts: dict[str, ChartPanel] = {}

        scroll = ScrollRevealArea()
        scroll.setObjectName("dashboardScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setMinimumSize(0, 0)
        self._scroll = scroll

        self._content = QWidget()
        self._content.setObjectName("dashboardContent")
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(24, 20, 24, 24)
        content_layout.setSpacing(14)
        content_layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetNoConstraint)
        scroll.setWidget(self._content)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(scroll)

        self._build_ribbon(content_layout)
        self._build_kpis(content_layout)
        self._build_slicers(content_layout)
        self._build_chart_grid(content_layout)
        self._build_library_activity(content_layout)

    def _build_ribbon(self, root: QVBoxLayout) -> None:
        ribbon = QWidget()
        ribbon.setObjectName("dashboardRibbon")
        layout = QHBoxLayout(ribbon)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(2)
        title = QLabel("Library Dashboard")
        title.setObjectName("dashboardTitle")
        title.setStyleSheet(f"color:{theme_tokens.TEXT_PRIMARY}; font-size:20px; font-weight:700; background:transparent;")
        subtitle = QLabel("Collection metrics and recorded progress activity")
        subtitle.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:10px; background:transparent;")
        text.addWidget(title)
        text.addWidget(subtitle)
        layout.addLayout(text, 1)

        self._last_updated = QLabel("Not refreshed")
        self._last_updated.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:9px;")
        layout.addWidget(self._last_updated)

        self._back_btn = QPushButton("← Back to Library")
        self._back_btn.setObjectName("backButton")
        self._back_btn.setFixedHeight(34)
        self._back_btn.clicked.connect(self.back_requested.emit)
        layout.addWidget(self._back_btn)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setObjectName("primaryButton")
        self._refresh_btn.setFixedHeight(34)
        self._refresh_btn.clicked.connect(self.refresh_requested.emit)
        layout.addWidget(self._refresh_btn)
        root.addWidget(ribbon)

    def _build_kpis(self, root: QVBoxLayout) -> None:
        self._kpi_container = QWidget()
        self._kpi_grid = QGridLayout(self._kpi_container)
        self._kpi_grid.setContentsMargins(0, 0, 0, 0)
        self._kpi_grid.setHorizontalSpacing(10)
        self._kpi_grid.setVerticalSpacing(8)
        labels = (
            ("total", "Total items"),
            ("completed", "Completed items"),
            ("in_progress", "In progress"),
            ("favorites", "Favorites"),
            ("average_score", "Avg Anime score"),
            ("rated_anime", "Rated Anime"),
            ("progress", "Episodes / chapters"),
            ("tiered_items", "Tiered items"),
            ("unique_genres", "Unique genres"),
        )
        self._kpi_items: list[tuple[str, SummaryKpiCard]] = []
        for key, label in labels:
            card = SummaryKpiCard(label, compact=False)
            self._kpi_cards[key] = card
            self._kpi_items.append((key, card))
        root.addWidget(self._kpi_container)
        self._reflow_kpis()

    def _reflow_kpis(self) -> None:
        if not hasattr(self, "_kpi_grid"):
            return
        width = self.width()
        columns = 5 if width >= 1550 else 4 if width >= 1080 else 2
        while self._kpi_grid.count():
            self._kpi_grid.takeAt(0)
        for index, (_, card) in enumerate(self._kpi_items):
            self._kpi_grid.addWidget(card, index // columns, index % columns)

    def _build_slicers(self, root: QVBoxLayout) -> None:
        ribbon = QFrame()
        ribbon.setObjectName("dashboardSlicerRibbon")
        ribbon.setStyleSheet(
            f"#dashboardSlicerRibbon {{ background:{theme_tokens.GLASS_SURFACE}; "
            f"border:1px solid {theme_tokens.BORDER}; border-radius:10px; }}"
        )
        layout = QHBoxLayout(ribbon)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(8)
        self._slicers = DashboardSlicers()
        self._slicers.connect_changed(self._apply_filters)
        layout.addWidget(self._slicers)
        root.addWidget(ribbon)

    def _build_chart_grid(self, root: QVBoxLayout) -> None:
        self._analytics_grid_host = QWidget()
        self._analytics_grid = QGridLayout(self._analytics_grid_host)
        self._analytics_grid.setContentsMargins(0, 0, 0, 0)
        self._analytics_grid.setHorizontalSpacing(12)
        self._analytics_grid.setVerticalSpacing(12)
        definitions = (
            ("media", "Media distribution", "donut", "Share of the selected collection by media category."),
            ("formats", "Format proportions", "pie", "Format mix from saved Anime media types and literature formats."),
            ("genres", "Most common genres", "bar", "Counts distinct genre tags on matching library records."),
            ("clustered", "Status by media type", "clustered", "Grouped counts compare each status across the four categories."),
            ("timeline", "Recorded personal dates by month", "line", "Uses saved first/last progress and completion dates; no history is inferred."),
            ("heatmap", "Recorded-date heat map", "heatmap", "Saved personal progress dates grouped by year and month."),
            ("bubbles", "Genre bubble map", "bubble", "Bubble size is matching record count; position is category grouping, not geography."),
            ("funnel", "Status breakdown", "funnel", "Statuses are independent states, not sequential conversion stages."),
            ("tiers", "Tier distribution", "tiers", "Counts saved personal tiers; unranked items are not assigned a tier."),
            ("years", "Release years", "years", "Uses Anime season year / aired date and literature start dates when available."),
        )
        for key, title, kind, note in definitions:
            panel = ChartPanel(title, kind, note)
            panel.chart.setMinimumHeight(190)
            self._analytics_charts[key] = panel
        root.addWidget(self._analytics_grid_host)
        self._reflow_analytics()

    def _reflow_analytics(self) -> None:
        if not hasattr(self, "_analytics_grid"):
            return
        viewport_width = self._scroll.viewport().width() if hasattr(self, "_scroll") else 0
        width = max(viewport_width, self.width() - 48)
        columns = 3 if width >= 1750 else 2 if width >= 1030 else 1
        while self._analytics_grid.count():
            self._analytics_grid.takeAt(0)
        for index, panel in enumerate(self._analytics_charts.values()):
            self._analytics_grid.addWidget(panel, index // columns, index % columns)

    def _build_library_activity(self, root: QVBoxLayout) -> None:
        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self._up_next_panel, self._up_next_layout = self._text_panel("In progress", "No in-progress titles.")
        self._recent_panel, self._recent_layout = self._text_panel("Recent recorded activity", "No personal activity dates are recorded.")
        recommendations, rec_layout = self._text_panel("Recommendations", "Recommendations are generated from the existing recommendation workflow.")
        self._recommendation_button = QPushButton("Open Recommendations")
        self._recommendation_button.setObjectName("secondaryButton")
        self._recommendation_button.clicked.connect(self._open_recommendation_dialog)
        rec_layout.addWidget(self._recommendation_button)
        self._activity_grid_host = grid_host
        self._activity_grid = grid
        self._activity_panels = [self._up_next_panel, self._recent_panel, recommendations]
        root.addWidget(grid_host)
        self._reflow_library_activity()

    @staticmethod
    def _text_panel(title: str, empty_text: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("statPanel")
        frame.setStyleSheet(f"#statPanel {{ background:{theme_tokens.GLASS_SURFACE}; border:1px solid {theme_tokens.BORDER}; border-radius:12px; }}")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)
        heading = QLabel(title)
        heading.setStyleSheet(f"color:{theme_tokens.TEXT_PRIMARY}; font-size:12px; font-weight:650; background:transparent; border:none;")
        layout.addWidget(heading)
        label = QLabel(empty_text)
        label.setObjectName("activityPlaceholder")
        label.setWordWrap(True)
        label.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:10px; background:transparent; border:none;")
        layout.addWidget(label)
        return frame, layout

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._reflow_kpis()
        self._reflow_analytics()
        self._reflow_library_activity()

    def _reflow_library_activity(self) -> None:
        if not hasattr(self, "_activity_grid"):
            return
        viewport_width = self._scroll.viewport().width() if hasattr(self, "_scroll") else 0
        width = max(viewport_width, self.width() - 48)
        columns = 3 if width >= 1750 else 2 if width >= 1030 else 1
        while self._activity_grid.count():
            self._activity_grid.takeAt(0)
        for column in range(3):
            self._activity_grid.setColumnStretch(column, 1 if column < columns else 0)
        for index, panel in enumerate(self._activity_panels):
            self._activity_grid.addWidget(panel, index // columns, index % columns)

    def refresh(self, animes: Iterable[Any], literature: Iterable[Any]) -> None:
        from datetime import datetime

        self._animes = list(animes or ())
        self._literature = list(literature or ())
        self._last_updated.setText(f"Updated {datetime.now().strftime('%H:%M:%S')}")
        base = build_dashboard_data(self._animes, self._literature)
        self._slicers.set_options(base["formats"].keys(), base["genres"].keys())
        self._apply_filters()

    def _apply_filters(self) -> None:
        if not hasattr(self, "_slicers"):
            return
        self._analytics_data = build_dashboard_data(
            self._animes, self._literature, **self._slicers.values()
        )
        data = self._analytics_data
        status_counts = data["status_counts"]
        self._kpi_cards["total"].set_value(data["total"])
        self._kpi_cards["completed"].set_value(status_counts["completed"])
        self._kpi_cards["in_progress"].set_value(status_counts["watching"])
        self._kpi_cards["favorites"].set_value(data["favorites"])
        self._kpi_cards["average_score"].set_value("—" if data["average_score"] is None else f"{data['average_score']:.2f} / 10")
        self._kpi_cards["rated_anime"].set_value(data["rated_anime"])
        self._kpi_cards["progress"].set_value(f"Ep {data['episodes_watched']}/{data['episodes_total']} · Ch {data['chapters_read']}/{data['chapters_total']}")
        self._kpi_cards["tiered_items"].set_value(data["tiered_items"])
        self._kpi_cards["unique_genres"].set_value(data["unique_genres"])
        for key, panel in self._analytics_charts.items():
            panel.chart.set_data(data)
            panel.chart.setToolTip(self._chart_tooltip(key, panel.title_label.text(), data))
        visible_animes = [item for category, item in data["records"] if category == MEDIA_ANIME]
        visible_literature = [item for category, item in data["records"] if category != MEDIA_ANIME]
        self._refresh_auxiliary(visible_animes, visible_literature)

    @staticmethod
    def _chart_tooltip(key: str, title: str, data: dict[str, Any]) -> str:
        if key == "media":
            rows = [(CATEGORY_LABELS.get(label, label), count) for label, count in data["by_category"].items()]
        elif key == "clustered":
            rows = [(f"{CATEGORY_LABELS.get(category, category)} / {_STATUS_LABELS[status]}", count) for category, values in data["status_by_category"].items() for status, count in values.items()]
        elif key == "funnel":
            rows = [(_STATUS_LABELS[status], count) for status, count in data["funnel"].items()]
        elif key == "timeline":
            rows = list(data["timeline"].items())
        elif key == "heatmap":
            rows = [(f"{year}-{month:02d}", count) for (year, month), count in sorted(data["heatmap"].items())]
        elif key == "bubbles":
            rows = [(f"{CATEGORY_LABELS.get(row['category'], row['category'])} / {row['genre']}", row["count"]) for row in data["bubbles"]]
        elif key == "years":
            rows = [(str(year), count) for year, count in data["release_years"].items()]
        else:
            source = {"formats": "formats", "genres": "genres", "tiers": "tiers"}.get(key, "genres")
            rows = list(data[source].items())
        detail = ", ".join(f"{label}: {value}" for label, value in rows[:12]) or "No matching values"
        return f"{title} · {data['total']} matching items\n{detail}\nValues come from saved AnimeVault records."

    def _refresh_auxiliary(self, animes: list[Any], literature: list[Any]) -> None:
        self._clear_layout(self._up_next_layout, keep_title=True)
        in_progress = [(MEDIA_ANIME, item) for item in animes if getattr(item, "status", "") == "watching"]
        in_progress.extend((item.category, item) for item in literature if getattr(item, "status", "") == "watching")
        in_progress.sort(key=lambda pair: getattr(pair[1], "last_watched", "") or getattr(pair[1], "last_read", ""), reverse=True)
        if not in_progress:
            self._add_empty(self._up_next_layout, "No in-progress titles match these filters.")
        else:
            for category, item in in_progress[:6]:
                count = getattr(item, "episodes_watched", 0) if category == MEDIA_ANIME else getattr(item, "chapters_read", 0)
                total = getattr(item, "episodes", 0) if category == MEDIA_ANIME else getattr(item, "chapters", 0)
                label = QLabel(f"{getattr(item, 'title', 'Untitled')}  ·  {CATEGORY_LABELS.get(category, category)}  ·  {count}/{total}")
                label.setWordWrap(True)
                label.setMinimumWidth(0)
                label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
                label.setStyleSheet(f"color:{theme_tokens.TEXT_SECONDARY}; font-size:10px; background:transparent; border:none;")
                label.setToolTip(label.text())
                self._up_next_layout.addWidget(label)
        self._clear_layout(self._recent_layout, keep_title=True)
        activities: list[tuple[str, str, str]] = []
        for category, rows in ((MEDIA_ANIME, animes), ("literature", literature)):
            for item in rows:
                for attr in (("last_watched", "completed_date") if category == MEDIA_ANIME else ("last_read", "completed_date")):
                    stamp = str(getattr(item, attr, "") or "")
                    if stamp:
                        activities.append((stamp, getattr(item, "title", "Untitled"), attr.replace("_", " ").title()))
        activities.sort(key=lambda row: row[0], reverse=True)
        if not activities:
            self._add_empty(self._recent_layout, "No personal activity dates are recorded for these filters.")
        else:
            for stamp, title, action in activities[:8]:
                label = QLabel(f"{stamp}  ·  {action}  ·  {title}")
                label.setWordWrap(True)
                label.setMinimumWidth(0)
                label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
                label.setStyleSheet(f"color:{theme_tokens.TEXT_SECONDARY}; font-size:10px; background:transparent; border:none;")
                label.setToolTip(label.text())
                self._recent_layout.addWidget(label)

    @staticmethod
    def _clear_layout(layout: QVBoxLayout, keep_title: bool = False) -> None:
        start = 1 if keep_title else 0
        while layout.count() > start:
            item = layout.takeAt(start)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    @staticmethod
    def _add_empty(layout: QVBoxLayout, text: str) -> None:
        label = QLabel(text)
        label.setObjectName("activityPlaceholder")
        label.setWordWrap(True)
        label.setMinimumWidth(0)
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        label.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:10px; background:transparent; border:none;")
        layout.addWidget(label)

    def _open_recommendation_dialog(self) -> None:
        from animevault.ui.recommendation_dialog import RecommendationDialog

        dialog = RecommendationDialog(self, library_items=self._animes)
        dialog.exec()

    def _refresh_styles(self) -> None:
        """Refresh chart/panel painting after application theme changes."""
        self.update()
        for panel in self._analytics_charts.values():
            panel.update()
            panel.chart.update()
