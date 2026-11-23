"""Library backend services: thin adapters over the existing models.

These functions deliberately only READ the existing SQLite database. They
reuse the existing ``animevault.models.anime`` / ``animevault.models.literature``
query methods verbatim instead of duplicating SQL.
"""

from __future__ import annotations

from animevault.database import database_path, get_connection
from animevault.models.anime import Anime
from animevault.models.literature import Literature


def list_anime():
    """Return every anime record (existing model query, no SQL duplication)."""
    with get_connection():
        return Anime.all()


def filtered_anime(*, tier=None, status=None, sort_by="title"):
    with get_connection():
        return Anime.filtered(tier=tier, status=status, sort_by=sort_by)


def get_anime(anime_id: int):
    with get_connection():
        return Anime.find_by_id(anime_id)


def find_anime_by_title(title: str):
    with get_connection():
        return Anime.find_by_title(title)


def list_literature():
    with get_connection():
        return Literature.all()


def get_literature(item_id: int):
    with get_connection():
        return Literature.find_by_id(item_id)


def library_summary():
    """Build a cross-format summary from the existing full-record queries."""
    anime = Anime.all()
    literature = Literature.all()

    anime_counts = {"plan_to_watch": 0, "watching": 0, "completed": 0,
                    "on_hold": 0, "dropped": 0, "total": len(anime)}
    for a in anime:
        anime_counts[a.status] = anime_counts.get(a.status, 0) + 1

    lit_counts = {"manga": 0, "manhwa": 0, "manhua": 0,
                  "plan_to_watch": 0, "watching": 0, "completed": 0,
                  "on_hold": 0, "dropped": 0, "total": len(literature)}
    for l in literature:
        cat = (l.category or "").lower()
        if cat in lit_counts:
            lit_counts[cat] = lit_counts.get(cat, 0) + 1
        lit_counts[l.status] = lit_counts.get(l.status, 0) + 1

    return {
        "anime": {"plan_to_watch": anime_counts["plan_to_watch"],
                  "watching": anime_counts["watching"],
                  "completed": anime_counts["completed"],
                  "on_hold": anime_counts["on_hold"],
                  "dropped": anime_counts["dropped"],
                  "total": anime_counts["total"]},
        "literature": {"manga": lit_counts["manga"],
                       "manhwa": lit_counts["manhwa"],
                       "manhua": lit_counts["manhua"],
                       "plan_to_watch": lit_counts["plan_to_watch"],
                       "watching": lit_counts["watching"],
                       "completed": lit_counts["completed"],
                       "on_hold": lit_counts["on_hold"],
                       "dropped": lit_counts["dropped"],
                       "total": lit_counts["total"]},
        "total_records": len(anime) + len(literature),
        "database_path": str(database_path()),
    }
