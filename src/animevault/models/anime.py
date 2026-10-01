"""Anime model — a plain dataclass backed by SQLite."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from animevault.database import get_connection

# ── Valid status values ──────────────────────────────────────────

STATUS_PLAN_TO_WATCH = "plan_to_watch"
STATUS_WATCHING = "watching"
STATUS_COMPLETED = "completed"
STATUS_ON_HOLD = "on_hold"
STATUS_DROPPED = "dropped"

VALID_STATUSES = (
    STATUS_PLAN_TO_WATCH,
    STATUS_WATCHING,
    STATUS_COMPLETED,
    STATUS_ON_HOLD,
    STATUS_DROPPED,
)


# ── Model ────────────────────────────────────────────────────────


@dataclass
class Anime:
    """A single anime entry in the library.

    Attributes
    ----------
    id:
        Primary key assigned by SQLite.  ``None`` when the record has
        not yet been persisted.
    title:
        Canonical (romanized) title.  Must not be empty.
    title_ja:
        Japanese title or alternative spelling.  May be empty.
    episodes:
        Total number of episodes.  Must be non-negative.
    status:
        Watching status.  One of :data:`VALID_STATUSES`.
    score:
        User-assigned score from 0.0 to 10.0.  May be ``None``.
    notes:
        Free-form text notes.
    """

    id: Optional[int]
    title: str
    title_ja: str = ""
    episodes: int = 0
    status: str = STATUS_PLAN_TO_WATCH
    score: Optional[float] = None
    notes: str = ""

    # Metadata attributes
    title_en: str = ""
    synopsis: str = ""
    media_type: str = ""
    airing_status: str = ""
    genres: list[str] = field(default_factory=list)
    studios: list[str] = field(default_factory=list)
    aired_from: str = ""
    aired_to: str = ""
    season: str = ""
    season_year: Optional[int] = None
    duration: int = 0
    poster_url: str = ""
    poster_path: str = ""
    mal_id: Optional[int] = None
    anilist_id: Optional[int] = None
    kitsu_id: Optional[str] = None
    tmdb_id: Optional[int] = None
    source_provider: str = ""
    metadata_fetched_at: str = ""

    # ── Validation ────────────────────────────────────────────────

    def __post_init__(self) -> None:
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("title must be a non-empty string")
        if not isinstance(self.episodes, int) or self.episodes < 0:
            raise ValueError("episodes must be a non-negative integer")
        if self.status not in VALID_STATUSES:
            raise ValueError(
                f"status must be one of {VALID_STATUSES}, got {self.status!r}"
            )
        if self.score is not None:
            if not isinstance(self.score, (int, float)):
                raise TypeError("score must be a number or None")
            if not (0.0 <= float(self.score) <= 10.0):
                raise ValueError("score must be between 0.0 and 10.0")

    # ── Persistence ────────────────────────────────────────────────

    def save(self) -> Anime:
        """Insert or update this record in the database.

        If :attr:`id` is ``None`` an ``INSERT`` is performed and the new
        id is assigned back to ``self``.  Otherwise an ``UPDATE`` is
        executed.

        Returns
        -------
        Anime
            ``self`` (for method chaining).
        """
        genres_json = json.dumps(self.genres, ensure_ascii=False)
        studios_json = json.dumps(self.studios, ensure_ascii=False)

        with get_connection() as conn:
            if self.id is None:
                cur = conn.execute(
                    """
                    INSERT INTO anime (title, title_ja, episodes, status, score, notes)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.title,
                        self.title_ja or None,
                        self.episodes,
                        self.status,
                        self.score,
                        self.notes,
                    ),
                )
                self.id = cur.lastrowid
            else:
                conn.execute(
                    """
                    UPDATE anime
                       SET title    = ?,
                           title_ja = ?,
                           episodes = ?,
                           status   = ?,
                           score    = ?,
                           notes    = ?
                     WHERE id = ?
                    """,
                    (
                        self.title,
                        self.title_ja or None,
                        self.episodes,
                        self.status,
                        self.score,
                        self.notes,
                        self.id,
                    ),
                )

            # Persist / update companion metadata record
            conn.execute(
                """
                INSERT INTO anime_metadata (
                    anime_id, title_en, synopsis, media_type, airing_status,
                    genres, studios, aired_from, aired_to, season, season_year,
                    duration, poster_url, poster_path, mal_id, anilist_id,
                    kitsu_id, tmdb_id, source_provider, metadata_fetched_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(anime_id) DO UPDATE SET
                    title_en            = excluded.title_en,
                    synopsis            = excluded.synopsis,
                    media_type          = excluded.media_type,
                    airing_status       = excluded.airing_status,
                    genres              = excluded.genres,
                    studios             = excluded.studios,
                    aired_from          = excluded.aired_from,
                    aired_to            = excluded.aired_to,
                    season              = excluded.season,
                    season_year         = excluded.season_year,
                    duration            = excluded.duration,
                    poster_url          = excluded.poster_url,
                    poster_path         = excluded.poster_path,
                    mal_id              = excluded.mal_id,
                    anilist_id          = excluded.anilist_id,
                    kitsu_id            = excluded.kitsu_id,
                    tmdb_id             = excluded.tmdb_id,
                    source_provider     = excluded.source_provider,
                    metadata_fetched_at = excluded.metadata_fetched_at
                """,
                (
                    self.id,
                    self.title_en,
                    self.synopsis,
                    self.media_type,
                    self.airing_status,
                    genres_json,
                    studios_json,
                    self.aired_from,
                    self.aired_to,
                    self.season,
                    self.season_year,
                    self.duration,
                    self.poster_url,
                    self.poster_path,
                    self.mal_id,
                    self.anilist_id,
                    self.kitsu_id or "",
                    self.tmdb_id,
                    self.source_provider,
                    self.metadata_fetched_at,
                ),
            )
            conn.commit()
        return self

    @classmethod
    def create(
        cls,
        title: str,
        title_ja: str = "",
        episodes: int = 0,
        status: str = STATUS_PLAN_TO_WATCH,
        score: Optional[float] = None,
        notes: str = "",
        **kwargs: Any,
    ) -> Anime:
        """Create **and persist** a new :class:`Anime` record.

        This is a convenience that constructs the object, validates it,
        saves it to the database, and returns the instance with its
        ``id`` populated.
        """
        return cls(
            id=None,
            title=title,
            title_ja=title_ja,
            episodes=episodes,
            status=status,
            score=score,
            notes=notes,
            **kwargs,
        ).save()

    @classmethod
    def from_row(cls, row) -> Anime:
        """Build an :class:`Anime` from a ``sqlite3.Row`` or dict-like."""
        keys = row.keys() if hasattr(row, "keys") else row

        def _get(key: str, default=None):
            if key in keys:
                val = row[key]
                return val if val is not None else default
            return default

        def _json_list(val) -> list[str]:
            if not val:
                return []
            if isinstance(val, list):
                return val
            try:
                parsed = json.loads(val)
                return [str(x) for x in parsed] if isinstance(parsed, list) else [str(parsed)]
            except Exception:
                return [s.strip() for s in str(val).split(",") if s.strip()]

        return cls(
            id=row["id"],
            title=row["title"],
            title_ja=_get("title_ja", "") or "",
            episodes=row["episodes"] if row["episodes"] is not None else 0,
            status=row["status"],
            score=row["score"],
            notes=_get("notes", "") or "",
            title_en=_get("title_en", "") or "",
            synopsis=_get("synopsis", "") or "",
            media_type=_get("media_type", "") or "",
            airing_status=_get("airing_status", "") or "",
            genres=_json_list(_get("genres")),
            studios=_json_list(_get("studios")),
            aired_from=_get("aired_from", "") or "",
            aired_to=_get("aired_to", "") or "",
            season=_get("season", "") or "",
            season_year=_get("season_year"),
            duration=_get("duration", 0) or 0,
            poster_url=_get("poster_url", "") or "",
            poster_path=_get("poster_path", "") or "",
            mal_id=_get("mal_id"),
            anilist_id=_get("anilist_id"),
            kitsu_id=_get("kitsu_id") or None,
            tmdb_id=_get("tmdb_id"),
            source_provider=_get("source_provider", "") or "",
            metadata_fetched_at=_get("metadata_fetched_at", "") or "",
        )

    # ── Queries ────────────────────────────────────────────────────

    @staticmethod
    def all() -> list[Anime]:
        """Return every anime entry, ordered by title."""
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT a.*,
                       m.title_en, m.synopsis, m.media_type, m.airing_status,
                       m.genres, m.studios, m.aired_from, m.aired_to,
                       m.season, m.season_year, m.duration, m.poster_url,
                       m.poster_path, m.mal_id, m.anilist_id, m.kitsu_id,
                       m.tmdb_id, m.source_provider, m.metadata_fetched_at
                  FROM anime a
             LEFT JOIN anime_metadata m ON a.id = m.anime_id
              ORDER BY a.title ASC, a.id ASC
                """
            ).fetchall()
        return [Anime.from_row(r) for r in rows]

    @staticmethod
    def find_by_id(anime_id: int) -> Optional[Anime]:
        """Return the anime with the given id, or ``None``."""
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT a.*,
                       m.title_en, m.synopsis, m.media_type, m.airing_status,
                       m.genres, m.studios, m.aired_from, m.aired_to,
                       m.season, m.season_year, m.duration, m.poster_url,
                       m.poster_path, m.mal_id, m.anilist_id, m.kitsu_id,
                       m.tmdb_id, m.source_provider, m.metadata_fetched_at
                  FROM anime a
             LEFT JOIN anime_metadata m ON a.id = m.anime_id
                 WHERE a.id = ?
                """,
                (anime_id,),
            ).fetchone()
        if row is None:
            return None
        return Anime.from_row(row)

    @staticmethod
    def find_by_title(title: str) -> Optional[Anime]:
        """Return an existing anime with matching title (case-insensitive) or ``None``."""
        t = title.strip().lower()
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT a.*,
                       m.title_en, m.synopsis, m.media_type, m.airing_status,
                       m.genres, m.studios, m.aired_from, m.aired_to,
                       m.season, m.season_year, m.duration, m.poster_url,
                       m.poster_path, m.mal_id, m.anilist_id, m.kitsu_id,
                       m.tmdb_id, m.source_provider, m.metadata_fetched_at
                  FROM anime a
             LEFT JOIN anime_metadata m ON a.id = m.anime_id
                 WHERE LOWER(a.title) = ? OR LOWER(m.title_en) = ? OR LOWER(a.title_ja) = ?
                 LIMIT 1
                """,
                (t, t, t),
            ).fetchone()
        if row is None:
            return None
        return Anime.from_row(row)

    @staticmethod
    def find_by_provider_id(
        *,
        anilist_id: Optional[int] = None,
        mal_id: Optional[int] = None,
        kitsu_id: Optional[str] = None,
        tmdb_id: Optional[int] = None,
    ) -> Optional[Anime]:
        """Find an existing anime by any of its provider IDs."""
        with get_connection() as conn:
            query = """
                SELECT a.*,
                       m.title_en, m.synopsis, m.media_type, m.airing_status,
                       m.genres, m.studios, m.aired_from, m.aired_to,
                       m.season, m.season_year, m.duration, m.poster_url,
                       m.poster_path, m.mal_id, m.anilist_id, m.kitsu_id,
                       m.tmdb_id, m.source_provider, m.metadata_fetched_at
                  FROM anime a
                  JOIN anime_metadata m ON a.id = m.anime_id
                 WHERE ( ? IS NOT NULL AND m.anilist_id = ? )
                    OR ( ? IS NOT NULL AND m.mal_id = ? )
                    OR ( ? IS NOT NULL AND m.kitsu_id = ? )
                    OR ( ? IS NOT NULL AND m.tmdb_id = ? )
                 LIMIT 1
            """
            row = conn.execute(
                query,
                (
                    anilist_id, anilist_id,
                    mal_id, mal_id,
                    str(kitsu_id) if kitsu_id else None, str(kitsu_id) if kitsu_id else None,
                    tmdb_id, tmdb_id,
                ),
            ).fetchone()
            if row:
                return Anime.from_row(row)
        return None

    def delete(self) -> None:
        """Delete this record from the database (no-op if unsaved)."""
        if self.id is None:
            return
        poster_to_clean = self.poster_path
        with get_connection() as conn:
            conn.execute("DELETE FROM anime_metadata WHERE anime_id = ?", (self.id,))
            conn.execute("DELETE FROM anime WHERE id = ?", (self.id,))
            conn.commit()

            if poster_to_clean:
                other = conn.execute(
                    "SELECT anime_id FROM anime_metadata WHERE poster_path = ? LIMIT 1",
                    (poster_to_clean,),
                ).fetchone()
                if not other:
                    try:
                        p = Path(poster_to_clean)
                        if p.exists() and p.is_file():
                            p.unlink()
                    except Exception:
                        pass
