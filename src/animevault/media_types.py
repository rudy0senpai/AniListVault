"""Media categories and their type vocabularies.

AnimeVault treats Anime, Manga, Manhwa and Manhua as first-class
categories rather than bolting literature onto the anime table.  The
distinction is driven by provider metadata (``countryOfOrigin`` /
``origin_country``), never by guessing from a title string.
"""

from __future__ import annotations

# ── Media categories ──────────────────────────────────────────────

MEDIA_ANIME = "anime"
MEDIA_MANGA = "manga"
MEDIA_MANHWA = "manhwa"
MEDIA_MANHUA = "manhua"

MEDIA_CATEGORIES: tuple[str, ...] = (
    MEDIA_ANIME,
    MEDIA_MANGA,
    MEDIA_MANHWA,
    MEDIA_MANHUA,
)

CATEGORY_LABELS: dict[str, str] = {
    MEDIA_ANIME: "Anime",
    MEDIA_MANGA: "Manga",
    MEDIA_MANHWA: "Manhwa",
    MEDIA_MANHUA: "Manhua",
}

#: Literature categories share one progress/status vocabulary.
LITERATURE_CATEGORIES = frozenset({MEDIA_MANGA, MEDIA_MANHWA, MEDIA_MANHUA})


def is_literature(category: str) -> bool:
    return category in LITERATURE_CATEGORIES


def normalize_category(value: object) -> str:
    """Map a raw category string onto a canonical category.

    Falls back to :data:`MEDIA_ANIME` for unknown values so a record is
    never orphaned by a stray import value.
    """
    if not value:
        return MEDIA_ANIME
    text = str(value).strip().casefold()
    if text in MEDIA_CATEGORIES:
        return text
    if text in ("anime series", "tv", "show"):
        return MEDIA_ANIME
    if text in ("japanese comic", "manga series"):
        return MEDIA_MANGA
    if text in ("korean comic", "korean manga", "manhwa series"):
        return MEDIA_MANHWA
    if text in ("chinese comic", "chinese manga", "manhua series"):
        return MEDIA_MANHUA
    return MEDIA_ANIME


# ── Literature type detection ─────────────────────────────────────

#: AniList/Kitsu ``countryOfOrigin`` → category.
_ORIGIN_TO_CATEGORY: dict[str, str] = {
    "JP": MEDIA_MANGA,
    "KR": MEDIA_MANHWA,
    "CN": MEDIA_MANHUA,
    "TW": MEDIA_MANHUA,
    "HK": MEDIA_MANHUA,
}

_ORIGIN_ALIASES: dict[str, str] = {
    "JAPAN": "JP",
    "JAPANESE": "JP",
    "KOREA": "KR",
    "KOREAN": "KR",
    "SOUTH KOREA": "KR",
    "CHINA": "CN",
    "CHINESE": "CN",
    "TAIWAN": "TW",
    "HONG KONG": "HK",
}


def category_from_origin(origin: object) -> str | None:
    """Derive a literature category from a provider origin country.

    Returns ``None`` when the origin is absent or unrecognised, so the
    caller can fall back to an explicit choice rather than guessing.
    """
    if not origin:
        return None
    text = str(origin).strip().upper()
    if text in _ORIGIN_TO_CATEGORY:
        return _ORIGIN_TO_CATEGORY[text]
    return _ORIGIN_TO_CATEGORY.get(_ORIGIN_ALIASES.get(text, ""))


# ── Anime formats ─────────────────────────────────────────────────

ANIME_FORMATS: tuple[str, ...] = ("TV", "MOVIE", "OVA", "ONA", "SPECIAL", "MUSIC")

#: Literature formats as AniList reports them.
LITERATURE_FORMATS: tuple[str, ...] = ("MANGA", "MANHWA", "MANHUA", "NOVEL", "ONE_SHOT")

#: Formats that are still a comic rather than prose.
LITERATURE_COMIC_FORMATS: frozenset[str] = frozenset(
    {"MANGA", "MANHWA", "MANHUA", "ONE_SHOT"}
)


def normalize_format(value: object) -> str:
    """Normalize a provider format string to upper case."""
    return str(value or "").strip().upper()


# ── Progress labels ───────────────────────────────────────────────


def unit_for(category: str) -> tuple[str, str]:
    """Return ``(singular, plural)`` progress units for a category.

    Anime counts episodes; literature counts chapters.
    """
    if is_literature(category):
        return ("chapter", "chapters")
    return ("episode", "episodes")


def status_labels(category: str) -> dict[str, str]:
    """Human-facing status labels, which differ for literature."""
    if is_literature(category):
        return {
            "watching": "Reading",
            "completed": "Completed",
            "plan_to_watch": "Plan to Read",
            "on_hold": "On Hold",
            "dropped": "Dropped",
        }
    return {
        "watching": "Watching",
        "completed": "Completed",
        "plan_to_watch": "Plan to Watch",
        "on_hold": "On Hold",
        "dropped": "Dropped",
    }


def type_options(category: str) -> list[str]:
    """Type-filter options relevant to the selected category."""
    if is_literature(category):
        return [
            "All",
            MEDIA_MANGA.capitalize(),
            MEDIA_MANHWA.capitalize(),
            MEDIA_MANHUA.capitalize(),
            "Novel",
            "One Shot",
        ]
    return ["All"] + [f for f in ANIME_FORMATS if f]