"""Right-hand overview / analytics panel.

Every number here is derived from the database at build time — nothing is
hardcoded.  The panel is rebuilt on demand rather than on a timer, so it
costs nothing when the library is idle.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
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


class OverviewPanel(QScrollArea):
    """Dashboard sidebar: counts, top genres and tier distribution."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        # Never scroll horizontally: content must fit the panel width, so
        # long labels elide rather than push the layout wider.
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setMinimumWidth(230)
        self.setMaximumWidth(300)
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )

        self._host = QWidget()
        self._layout = QVBoxLayout(self._host)
        self._layout.setContentsMargins(14, 14, 14, 16)
        self._layout.setSpacing(14)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setWidget(self._host)

        self._rows: dict[str, _StatRow] = {}
        self._category_details: dict[str, QLabel] = {}
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
        """A fresh empty-state label (created per refresh, never reused)."""
        label = QLabel(text)
        label.setObjectName("statLabel")
        label.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED};")
        return label

    # ── Static structure ───────────────────────────────────────────

    def _build_static_panels(self) -> None:
        # ── Overview counts ───────────────────────────────────────
        frame, layout = _panel("Library Totals")
        for key, label, dot in [
            ("anime", "Number of Anime", None),
            ("watching", "Anime (Watching)", _STATUS_DOTS["watching"]),
            ("completed", "Anime (Completed)", _STATUS_DOTS["completed"]),
            ("plan", "Anime (Plan to Watch)", _STATUS_DOTS["plan_to_watch"]),
        ]:
            row = _StatRow(label, dot)
            self._rows[key] = row
            layout.addWidget(row)
        self._layout.addWidget(frame)

        # ── Literature counts ────────────────────────────────────
        frame, layout = _panel("Manga / Manhwa / Manhua")
        for key, label, color in [
            ("manga", "Manga", "#fbbf24"),
            ("manhwa", "Manhwa", "#a78bfa"),
            ("manhua", "Manhua", "#f472b6"),
        ]:
            row = _StatRow(label, color)
            self._rows[key] = row
            layout.addWidget(row)
            detail = QLabel("Reading 0 · Completed 0 · Planned 0")
            detail.setObjectName("categoryStatusSummary")
            detail.setWordWrap(True)
            detail.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:11px;")
            self._category_details[key] = detail
            layout.addWidget(detail)
        anime_detail = QLabel("Watching 0 · Completed 0 · Planned 0")
        anime_detail.setObjectName("categoryStatusSummary")
        anime_detail.setWordWrap(True)
        anime_detail.setStyleSheet(f"color:{theme_tokens.TEXT_MUTED}; font-size:11px;")
        self._category_details[MEDIA_ANIME] = anime_detail
        self._rows["plan"].parentWidget().layout().addWidget(anime_detail)
        self._layout.addWidget(frame)

        # ── Genres ───────────────────────────────────────────────
        self._genre_frame, self._genre_layout = _panel("Most Watched Genres")
        self._layout.addWidget(self._genre_frame)

        # ── Tier distribution ────────────────────────────────────
        self._tier_frame, self._tier_layout = _panel("Tier Distribution")
        self._layout.addWidget(self._tier_frame)

        self._layout.addStretch()

    # ── Data binding ───────────────────────────────────────────────

    def refresh(self, animes: list, literature: list) -> None:
        """Rebuild every statistic from *animes* and *literature*."""
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
            "Watching {watching} · Completed {completed} · Planned {planned}".format(
                watching=anime_status.get("watching", 0),
                completed=anime_status.get("completed", 0),
                planned=anime_status.get("plan_to_watch", 0),
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
                "Reading {reading} · Completed {completed} · Planned {planned}".format(
                    reading=category_status.get("watching", 0),
                    completed=category_status.get("completed", 0),
                    planned=category_status.get("plan_to_watch", 0),
                )
            )

        self._refresh_genres(animes, literature)
        self._refresh_tiers(animes, literature)

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
            self._genre_layout.addWidget(_BarRow(genre, count, maximum, color))

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
            self._tier_layout.addWidget(
                self._placeholder("No tiers assigned")
            )
            return

        maximum = max(counter.values())
        # Always show the full SSS→F ladder so the scale reads clearly.
        for tier in TIERS:
            count = counter.get(tier, 0)
            self._tier_layout.addWidget(
                _BarRow(tier, count, maximum, tier_color(tier))
            )

    # ── Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _clear(layout: QVBoxLayout) -> None:
        """Remove every child widget so the panel can be rebuilt."""
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