"""Literature model — Manga / Manhwa / Manhua entries.

Literature is stored in its own ``literature`` table rather than being
forced into the ``anime`` table.  The shape deliberately mirrors
:class:`animevault.models.anime.Anime` where the concepts overlap
(title, status, tier, notes, favorite, provider IDs, poster) and adds the
chapter/volume fields that only apply to print media.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from animevault.database import get_connection
from animevault.media_types import (
    MEDIA_MANGA,
    normalize_category,
    status_labels,
)
from animevault.models.anime import VALID_STATUSES
from animevault.tiers import normalize_tier, tier_sort_key

# ── Model ────────────────────────────────────────────────────────

_SELECT_LIT = """
    SELECT l.*,
           m.title_en, m.synopsis, m.genres, m.authors, m.artists,
           m.serialization, m.pub_status, m.started_at, m.ended_at,
           m.cover_url, m.cover_path, m.anilist_id, m.kitsu_id, m.mal_id,
           m.source_provider, m.metadata_fetched_at
      FROM literature l
 LEFT JOIN literature_metadata m ON l.id = m.literature_id
"""


@dataclass
class Literature:
    """A single manga / manhwa / manhua entry."""

    id: Optional[int]
    title: str
    category: str = MEDIA_MANGA

    # Personal
    status: str = "watching"
    tier: Optional[str] = None
    rewatches: int = 0
    chapters_read: int = 0
    favorite: bool = False
    notes: str = ""
    first_read: str = ""
    last_read: str = ""
    completed_date: str = ""
    privacy: str = "public"

    # Bibliographic
    title_native: str = ""
    format: str = ""
    origin_country: str = ""
    chapters: int = 0
    volumes: int = 0
    volumes_read: int = 0

    # Metadata
    title_en: str = ""
    synonyms: list[str] = field(default_factory=list)
    synopsis: str = ""
    genres: list[str] = field(default_factory=list)
    authors: list[str] = field(default_factory=list)
    artists: list[str] = field(default_factory=list)
    serialization: str = ""
    pub_status: str = ""
    started_at: str = ""
    ended_at: str = ""
    cover_url: str = ""
    cover_path: str = ""
    anilist_id: Optional[int] = None
    kitsu_id: Optional[str] = None
    mal_id: Optional[int] = None
    source_provider: str = ""
    metadata_fetched_at: str = ""

    # ── Validation ────────────────────────────────────────────────

    def __post_init__(self) -> None:
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("title must be a non-empty string")
        self.category = normalize_category(self.category)
        if self.status not in VALID_STATUSES:
            raise ValueError(
                f"status must be one of {VALID_STATUSES}, got {self.status!r}"
            )
        if self.tier is not None:
            self.tier = normalize_tier(self.tier)
        for attr in ("rewatches", "chapters_read", "chapters", "volumes", "volumes_read"):
            if getattr(self, attr) < 0:
                raise ValueError(f"{attr} must be a non-negative integer")

    # ── Derived ───────────────────────────────────────────────────

    def status_label(self) -> str:
        return status_labels(self.category).get(self.status, self.status)

    def progress(self) -> tuple[int, int]:
        """Return ``(read, total)`` for the progress bar."""
        return self.chapters_read, self.chapters

    def progress_percent(self) -> int:
        read, total = self.progress()
        if total <= 0:
            return 0
        return min(100, round(read * 100 / total))

    @property
    def poster_path(self) -> str:
        """Literature covers share the poster field name for card reuse."""
        return self.cover_path

    @property
    def poster_url(self) -> str:
        return self.cover_url

    # ── Persistence ────────────────────────────────────────────────

    def save(self) -> Literature:
        """Insert or update this record and its metadata companion."""
        genres_json = json.dumps(self.genres, ensure_ascii=False)
        synonyms_json = json.dumps(self.synonyms, ensure_ascii=False)
        authors_json = json.dumps(self.authors, ensure_ascii=False)
        artists_json = json.dumps(self.artists, ensure_ascii=False)

        with get_connection() as conn:
            if self.id is None:
                cur = conn.execute(
                    """
                    INSERT INTO literature (
                        category, title, title_native, synonyms, format, status,
                        tier, rewatches, chapters_read, chapters, volumes,
                        volumes_read, favorite, notes, first_read, last_read,
                        completed_date, privacy, origin_country
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.category,
                        self.title,
                        self.title_native or None,
                        synonyms_json,
                        self.format,
                        self.status,
                        self.tier,
                        self.rewatches,
                        self.chapters_read,
                        self.chapters,
                        self.volumes,
                        self.volumes_read,
                        1 if self.favorite else 0,
                        self.notes,
                        self.first_read,
                        self.last_read,
                        self.completed_date,
                        self.privacy,
                        self.origin_country,
                    ),
                )
                self.id = cur.lastrowid
            else:
                conn.execute(
                    """
                    UPDATE literature
                       SET category        = ?,
                           title           = ?,
                           title_native    = ?,
                           synonyms        = ?,
                           format          = ?,
                           status          = ?,
                           tier            = ?,
                           rewatches       = ?,
                           chapters_read   = ?,
                           chapters        = ?,
                           volumes         = ?,
                           volumes_read    = ?,
                           favorite        = ?,
                           notes           = ?,
                           first_read      = ?,
                           last_read       = ?,
                           completed_date  = ?,
                           privacy         = ?,
                           origin_country  = ?
                     WHERE id = ?
                    """,
                    (
                        self.category,
                        self.title,
                        self.title_native or None,
                        synonyms_json,
                        self.format,
                        self.status,
                        self.tier,
                        self.rewatches,
                        self.chapters_read,
                        self.chapters,
                        self.volumes,
                        self.volumes_read,
                        1 if self.favorite else 0,
                        self.notes,
                        self.first_read,
                        self.last_read,
                        self.completed_date,
                        self.privacy,
                        self.origin_country,
                        self.id,
                    ),
                )

            conn.execute(
                """
                INSERT INTO literature_metadata (
                    literature_id, title_en, synopsis, genres, authors, artists,
                    serialization, pub_status, started_at, ended_at,
                    cover_url, cover_path, anilist_id, kitsu_id, mal_id,
                    source_provider, metadata_fetched_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(literature_id) DO UPDATE SET
                    title_en            = excluded.title_en,
                    synopsis            = excluded.synopsis,
                    genres              = excluded.genres,
                    authors             = excluded.authors,
                    artists             = excluded.artists,
                    serialization       = excluded.serialization,
                    pub_status          = excluded.pub_status,
                    started_at          = excluded.started_at,
                    ended_at            = excluded.ended_at,
                    cover_url           = excluded.cover_url,
                    cover_path          = excluded.cover_path,
                    anilist_id          = excluded.anilist_id,
                    kitsu_id            = excluded.kitsu_id,
                    mal_id              = excluded.mal_id,
                    source_provider     = excluded.source_provider,
                    metadata_fetched_at = excluded.metadata_fetched_at
                """,
                (
                    self.id,
                    self.title_en,
                    self.synopsis,
                    genres_json,
                    authors_json,
                    artists_json,
                    self.serialization,
                    self.pub_status,
                    self.started_at,
                    self.ended_at,
                    self.cover_url,
                    self.cover_path,
                    self.anilist_id,
                    self.kitsu_id or "",
                    self.mal_id,
                    self.source_provider,
                    self.metadata_fetched_at,
                ),
            )
            conn.commit()
        return self

    @classmethod
    def create(cls, title: str, **kwargs: Any) -> Literature:
        """Create **and persist** a new literature record.

        Mirrors :meth:`animevault.models.anime.Anime.create` so both
        categories share one creation path.
        """
        return cls(id=None, title=title, **kwargs).save()

    @classmethod
    def from_row(cls, row) -> Literature:
        keys = row.keys() if hasattr(row, "keys") else []

        def _get(key: str, default=None):
            if key in keys:
                v = row[key]
                return v if v is not None else default
            return default

        def _json_list(val) -> list[str]:
            if not val:
                return []
            if isinstance(val, list):
                return val
            try:
                parsed = json.loads(val)
                return [str(x) for x in parsed] if isinstance(parsed, list) else []
            except Exception:
                return [s.strip() for s in str(val).split(",") if s.strip()]

        return cls(
            id=row["id"],
            title=row["title"],
            category=row["category"],
            status=row["status"],
            tier=_get("tier") or None,
            rewatches=_get("rewatches", 0) or 0,
            chapters_read=_get("chapters_read", 0) or 0,
            chapters=_get("chapters", 0) or 0,
            volumes=_get("volumes", 0) or 0,
            volumes_read=_get("volumes_read", 0) or 0,
            favorite=bool(_get("favorite", 0)),
            notes=_get("notes", "") or "",
            first_read=_get("first_read", "") or "",
            last_read=_get("last_read", "") or "",
            completed_date=_get("completed_date", "") or "",
            privacy=_get("privacy", "public") or "public",
            title_native=_get("title_native", "") or "",
            format=_get("format", "") or "",
            origin_country=_get("origin_country", "") or "",
            title_en=_get("title_en", "") or "",
            synonyms=_json_list(_get("synonyms")),
            synopsis=_get("synopsis", "") or "",
            genres=_json_list(_get("genres")),
            authors=_json_list(_get("authors")),
            artists=_json_list(_get("artists")),
            serialization=_get("serialization", "") or "",
            pub_status=_get("pub_status", "") or "",
            started_at=_get("started_at", "") or "",
            ended_at=_get("ended_at", "") or "",
            cover_url=_get("cover_url", "") or "",
            cover_path=_get("cover_path", "") or "",
            anilist_id=_get("anilist_id"),
            kitsu_id=_get("kitsu_id") or None,
            mal_id=_get("mal_id"),
            source_provider=_get("source_provider", "") or "",
            metadata_fetched_at=_get("metadata_fetched_at", "") or "",
        )

    # ── Queries ────────────────────────────────────────────────────

    @staticmethod
    def all() -> list[Literature]:
        with get_connection() as conn:
            rows = conn.execute(
                _SELECT_LIT + " ORDER BY l.title ASC, l.id ASC"
            ).fetchall()
        return [Literature.from_row(r) for r in rows]

    @staticmethod
    def by_category(category: str) -> list[Literature]:
        cat = normalize_category(category)
        with get_connection() as conn:
            rows = conn.execute(
                _SELECT_LIT + " WHERE l.category = ? ORDER BY l.title ASC, l.id ASC",
                (cat,),
            ).fetchall()
        return [Literature.from_row(r) for r in rows]

    @staticmethod
    def find_by_id(item_id: int) -> Optional[Literature]:
        with get_connection() as conn:
            row = conn.execute(
                _SELECT_LIT + " WHERE l.id = ?", (item_id,)
            ).fetchone()
        return Literature.from_row(row) if row else None

    @staticmethod
    def find_by_title(title: str, category: Optional[str] = None) -> Optional[Literature]:
        t = title.strip().lower()
        query = _SELECT_LIT + " WHERE LOWER(l.title) = ?"
        params: list[Any] = [t]
        if category:
            query += " AND l.category = ?"
            params.append(normalize_category(category))
        query += " LIMIT 1"
        with get_connection() as conn:
            row = conn.execute(query, tuple(params)).fetchone()
        return Literature.from_row(row) if row else None

    @staticmethod
    def find_by_provider_id(
        *, anilist_id: Optional[int] = None, kitsu_id: Optional[str] = None,
        mal_id: Optional[int] = None,
    ) -> Optional[Literature]:
        clauses, params = [], []
        if anilist_id is not None:
            clauses.append("m.anilist_id = ?")
            params.append(anilist_id)
        if kitsu_id:
            clauses.append("m.kitsu_id = ?")
            params.append(str(kitsu_id))
        if mal_id is not None:
            clauses.append("m.mal_id = ?")
            params.append(mal_id)
        if not clauses:
            return None
        query = _SELECT_LIT.replace(
            "LEFT JOIN literature_metadata m", "JOIN literature_metadata m"
        ) + " WHERE " + " OR ".join(clauses) + " LIMIT 1"
        with get_connection() as conn:
            row = conn.execute(query, tuple(params)).fetchone()
        return Literature.from_row(row) if row else None

    @staticmethod
    def filtered(
        *,
        category: Optional[str] = None,
        tier: Optional[str] = None,
        status: Optional[str] = None,
        fmt: Optional[str] = None,
        query: str = "",
        sort_by: str = "title",
    ) -> list[Literature]:
        """Filtered + sorted literature list."""
        with get_connection() as conn:
            rows = conn.execute(_SELECT_LIT).fetchall()
        items = [Literature.from_row(r) for r in rows]

        if category and category != "all":
            want = normalize_category(category)
            items = [i for i in items if i.category == want]
        if tier and tier != "all":
            if tier == "unassigned":
                items = [i for i in items if not i.tier]
            else:
                want = normalize_tier(tier)
                items = [i for i in items if i.tier == want]
        if status and status != "all":
            items = [i for i in items if i.status == status]
        if fmt and fmt != "all":
            want = fmt.strip().upper()
            items = [i for i in items if i.format.upper() == want]
        if query.strip():
            q = query.strip().casefold()
            items = [
                i for i in items
                if q in i.title.casefold()
                or q in (i.title_native or "").casefold()
                or any(q in s.casefold() for s in i.synonyms)
            ]

        if sort_by == "tier":
            items.sort(key=lambda i: (tier_sort_key(i.tier), i.title.casefold()))
        elif sort_by == "progress":
            items.sort(key=lambda i: (-i.progress_percent(), i.title.casefold()))
        elif sort_by == "chapters":
            items.sort(key=lambda i: (-i.chapters, i.title.casefold()))
        elif sort_by == "added":
            items.sort(key=lambda i: -(i.id or 0))
        elif sort_by == "title_desc":
            items.sort(key=lambda i: i.title.casefold(), reverse=True)
        else:
            items.sort(key=lambda i: i.title.casefold())
        return items

    def delete(self) -> None:
        """Delete this record, cleaning the cover file when unreferenced."""
        if self.id is None:
            return
        cover_to_clean = self.cover_path
        with get_connection() as conn:
            conn.execute("DELETE FROM literature_metadata WHERE literature_id = ?", (self.id,))
            conn.execute("DELETE FROM literature WHERE id = ?", (self.id,))
            conn.commit()
            if cover_to_clean:
                other = conn.execute(
                    "SELECT literature_id FROM literature_metadata WHERE cover_path = ? LIMIT 1",
                    (cover_to_clean,),
                ).fetchone()
                if not other:
                    try:
                        p = Path(cover_to_clean)
                        if p.exists() and p.is_file():
                            p.unlink()
                    except Exception:
                        pass