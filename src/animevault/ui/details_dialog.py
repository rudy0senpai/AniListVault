"""Read-only details view for an Anime or literature entry.

Personal data and provider metadata are presented in separate sections so
it is always clear which fields the user owns.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from animevault.media_types import is_literature, unit_for
from animevault.models.literature import Literature
from animevault.ui.theme import (
    BORDER,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    tier_badge_style,
    status_badge_style,
)
from animevault.ui.thumb_cache import ThumbnailCache

_POSTER_W, _POSTER_H = 170, 244


class _Section(QFrame):
    """A titled block of label/value rows."""

    def __init__(self, title: str) -> None:
        super().__init__()
        self.setStyleSheet(
            f"background:transparent; border:1px solid {BORDER}; border-radius:10px;"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 11, 14, 13)
        layout.setSpacing(7)

        heading = QLabel(title)
        heading.setObjectName("panelTitle")
        layout.addWidget(heading)
        self._layout = layout

    def add_row(self, label: str, value) -> None:
        """Append a ``label: value`` line, skipping empty values."""
        if value is None or value == "" or value == []:
            return
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value)
        row = QHBoxLayout()
        row.setSpacing(10)
        key = QLabel(label)
        key.setObjectName("statLabel")
        key.setMinimumWidth(112)
        key.setMaximumWidth(112)
        row.addWidget(key, 0, Qt.AlignmentFlag.AlignTop)
        val = QLabel(str(value))
        val.setWordWrap(True)
        val.setStyleSheet(f"color:{TEXT_PRIMARY};")
        val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(val, 1)
        self._layout.addLayout(row)


class _Poster(QLabel):
    """Cover art with a rounded frame, or a placeholder."""

    def __init__(self, path: str) -> None:
        super().__init__()
        self.setFixedSize(_POSTER_W, _POSTER_H)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = ThumbnailCache.instance().get(path) if path else None
        if pixmap is not None:
            self.setPixmap(
                pixmap.scaled(
                    self.size(),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            self.setText("▦")
            self.setStyleSheet(
                f"color:{TEXT_MUTED}; background:#0f141b; border:1px solid {BORDER};"
                "border-radius:10px; font-size:34px;"
            )


class DetailsDialog(QDialog):
    """Full details for one library item."""

    def __init__(self, item, parent=None) -> None:
        super().__init__(parent)
        self._item = item
        self.setWindowTitle(item.title)
        self.setModal(True)
        self.resize(720, 640)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(16)

        layout.addWidget(self._build_header(item))
        if is_literature(getattr(item, "category", "")) or isinstance(item, Literature):
            layout.addWidget(self._build_literature_body(item))
        else:
            layout.addWidget(self._build_anime_body(item))

        layout.addStretch()
        scroll.setWidget(host)
        outer.addWidget(scroll)

    # ── Header ─────────────────────────────────────────────────────

    def _build_header(self, item) -> QWidget:
        header = QWidget()
        row = QHBoxLayout(header)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(18)

        row.addWidget(_Poster(getattr(item, "poster_path", "") or ""))

        info = QVBoxLayout()
        info.setSpacing(6)

        title = QLabel(item.title)
        title.setStyleSheet("font-size:19px; font-weight:700;")
        title.setWordWrap(True)
        info.addWidget(title)

        native = getattr(item, "title_ja", "") or getattr(item, "title_native", "")
        if native and native != item.title:
            native_label = QLabel(native)
            native_label.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:13px;")
            info.addWidget(native_label)

        badges = QHBoxLayout()
        badges.setSpacing(7)

        status_key = getattr(item, "status", "")
        status_text = (
            item.status_label()
            if isinstance(item, Literature)
            else status_key.replace("_", " ").title()
        )
        status_badge = QLabel(status_text)
        status_badge.setStyleSheet(status_badge_style(status_key))
        status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badges.addWidget(status_badge)

        tier = getattr(item, "tier", None)
        tier_badge = QLabel(tier or "—")
        tier_badge.setStyleSheet(tier_badge_style(tier))
        tier_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badges.addWidget(tier_badge)

        if getattr(item, "favorite", False):
            fav = QLabel("★ Favorite")
            fav.setStyleSheet("color:#fbbf24; font-size:12px; font-weight:600;")
            badges.addWidget(fav)

        badges.addStretch()
        info.addLayout(badges)

        synopsis = getattr(item, "synopsis", "") or "No synopsis available."
        syn = QLabel(synopsis[:600])
        syn.setWordWrap(True)
        syn.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:12px;")
        info.addWidget(syn)

        info.addStretch()
        row.addLayout(info, 1)
        return header

    # ── Bodies ─────────────────────────────────────────────────────

    def _build_anime_body(self, item) -> QWidget:
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        personal = _Section("Personal")
        personal.add_row("Tier", getattr(item, "tier", None) or "—")
        personal.add_row(
            "Status", getattr(item, "status", "").replace("_", " ").title()
        )
        personal.add_row(
            "Progress", f"{getattr(item, 'episodes_watched', 0) or 0} / "
                        f"{getattr(item, 'episodes', 0) or 0}"
        )
        personal.add_row("Rewatches", getattr(item, "rewatches", 0) or 0)
        personal.add_row("Favorite", "Yes" if getattr(item, "favorite", False) else "No")
        personal.add_row("Notes", getattr(item, "notes", ""))
        layout.addWidget(personal)

        metadata = _Section("Metadata")
        metadata.add_row("Type", getattr(item, "media_type", ""))
        metadata.add_row("Episodes", getattr(item, "episodes", 0) or "")
        metadata.add_row("Duration", f"{item.duration} min" if getattr(item, "duration", 0) else "")
        metadata.add_row("Season", getattr(item, "season", ""))
        metadata.add_row("Year", getattr(item, "season_year", None))
        metadata.add_row("Aired", f"{item.aired_from} → {item.aired_to}"
                      if getattr(item, "aired_from", "") else "")
        metadata.add_row("Genres", getattr(item, "genres", []))
        metadata.add_row("Studios", getattr(item, "studios", []))
        layout.addWidget(metadata)

        ids = _Section("Provider IDs")
        ids.add_row("AniList", getattr(item, "anilist_id", None))
        ids.add_row("MAL / Jikan", getattr(item, "mal_id", None))
        ids.add_row("Kitsu", getattr(item, "kitsu_id", None))
        ids.add_row("TMDB", getattr(item, "tmdb_id", None))
        ids.add_row("Source", getattr(item, "source_provider", ""))
        ids.add_row("Fetched", getattr(item, "metadata_fetched_at", ""))
        layout.addWidget(ids)

        return host

    def _build_literature_body(self, item) -> QWidget:
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        _, plural = unit_for(item.category)

        personal = _Section("Personal")
        personal.add_row("Tier", item.tier or "—")
        personal.add_row("Status", item.status_label())
        personal.add_row("Progress", f"{item.chapters_read} / {item.chapters} {plural}")
        personal.add_row("Volumes", item.volumes or "")
        personal.add_row("Rewatches", item.rewatches or 0)
        personal.add_row("Favorite", "Yes" if item.favorite else "No")
        personal.add_row("Notes", item.notes)
        layout.addWidget(personal)

        metadata = _Section("Metadata")
        metadata.add_row("Category", item.category.capitalize())
        metadata.add_row("Format", item.format)
        metadata.add_row("Chapters", item.chapters or "")
        metadata.add_row("Volumes", item.volumes or "")
        metadata.add_row("Publication", item.pub_status)
        metadata.add_row("Authors", item.authors)
        metadata.add_row("Artists", item.artists)
        metadata.add_row("Serialization", item.serialization)
        metadata.add_row("Origin", item.origin_country)
        metadata.add_row(
            "Published", f"{item.started_at} → {item.ended_at}" if item.started_at else ""
        )
        metadata.add_row("Genres", item.genres)
        metadata.add_row("Alternate titles", item.synonyms)
        layout.addWidget(metadata)

        ids = _Section("Provider IDs")
        ids.add_row("AniList", item.anilist_id)
        ids.add_row("Kitsu", item.kitsu_id)
        ids.add_row("MAL / Jikan", item.mal_id)
        ids.add_row("Source", item.source_provider)
        ids.add_row("Fetched", item.metadata_fetched_at)
        layout.addWidget(ids)

        return host