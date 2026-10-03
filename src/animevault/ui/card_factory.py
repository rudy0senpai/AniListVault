"""Builds :class:`MediaCard` widgets from Anime and Literature models.

Keeping the adaptation here means the card widget itself stays free of
model imports, and both categories present identical visual structure.
"""

from __future__ import annotations

from animevault.media_types import is_literature, unit_for
from animevault.ui.media_card import MediaCard

#: Display labels for the abbreviations providers use.
_TYPE_LABELS = {
    "TV": "TV",
    "MOVIE": "Movie",
    "OVA": "OVA",
    "ONA": "ONA",
    "SPECIAL": "Special",
    "MUSIC": "Music",
    "MANGA": "Manga",
    "MANHWA": "Manhwa",
    "MANHUA": "Manhua",
    "NOVEL": "Novel",
    "ONE_SHOT": "One Shot",
}


def type_label(raw: str) -> str:
    """Pretty-print a provider format string (keeps TV/OVA upper-case)."""
    key = (raw or "").strip().upper()
    return _TYPE_LABELS.get(key, key.title())


def _status_label(status: str) -> str:
    """Sentence-case status text, keeping short words lower-case."""
    words = (status or "").replace("_", " ").strip().lower().split()
    if not words:
        return ""
    small = {"to", "on", "in", "a"}
    return " ".join(
        [words[0].capitalize()]
        + [w if w in small else w.capitalize() for w in words[1:]]
    )


def anime_card(anime) -> MediaCard:
    """Create a card for an :class:`~animevault.models.anime.Anime`."""
    total = anime.episodes or 0
    watched = anime.episodes_watched or 0

    if total > 0:
        count_label = f"{total} ep"
        progress_text = f"{watched} / {total}"
        percent = min(100, round(watched * 100 / total)) if total else 0
    elif watched > 0:
        count_label = f"{watched} ep watched"
        progress_text = f"{watched}"
        percent = 0
    else:
        count_label = "— ep"
        progress_text = "—"
        percent = 0

    # Show the media type when the provider supplied one.
    label = type_label(anime.media_type)

    return MediaCard(
        anime,
        title=anime.title,
        type_label=label,
        count_label=count_label,
        progress_text=progress_text,
        progress_percent=percent,
        status_text=_status_label(anime.status),
        status_key=anime.status,
        tier=anime.tier,
        poster_path=anime.poster_path,
        kind="anime",
    )


def literature_card(item) -> MediaCard:
    """Create a card for a :class:`~animevault.models.literature.Literature`."""
    total = item.chapters or 0
    read = item.chapters_read or 0
    _, plural = unit_for(item.category)

    if total > 0:
        count_label = f"{total} {plural}"
        progress_text = f"{read} / {total}"
        percent = min(100, round(read * 100 / total))
    elif read > 0:
        count_label = f"{read} {plural} read"
        progress_text = f"{read}"
        percent = 0
    else:
        count_label = "— ch"
        progress_text = "—"
        percent = 0

    # Type badge: Manga / Manhwa / Manhua, else the provider format.
    if item.format and item.format not in ("MANGA", "MANHWA", "MANHUA"):
        label = type_label(item.format)
    else:
        label = item.category.capitalize()

    return MediaCard(
        item,
        title=item.title,
        type_label=label,
        count_label=count_label,
        progress_text=progress_text,
        progress_percent=percent,
        status_text=item.status_label(),
        status_key=item.status,
        tier=item.tier,
        poster_path=item.cover_path,
        kind="literature",
    )


def build_card(item, kind: str) -> MediaCard:
    """Dispatch to the right adapter for *kind*."""
    if kind == "anime":
        return anime_card(item)
    if is_literature(getattr(item, "category", "")):
        return literature_card(item)
    return literature_card(item)