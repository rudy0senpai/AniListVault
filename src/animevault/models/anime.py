"""Anime model — a plain dataclass backed by SQLite."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Optional

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
                conn.commit()
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
        ).save()

    @classmethod
    def from_row(cls, row) -> Anime:
        """Build an :class:`Anime` from a ``sqlite3.Row`` or dict-like."""
        return cls(
            id=row["id"],
            title=row["title"],
            title_ja=row["title_ja"] or "",
            episodes=row["episodes"] if row["episodes"] is not None else 0,
            status=row["status"],
            score=row["score"],
            notes=row["notes"] or "",
        )

    # ── Queries ────────────────────────────────────────────────────

    @staticmethod
    def all() -> list[Anime]:
        """Return every anime entry, ordered by title."""
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM anime ORDER BY title ASC, id ASC"
            ).fetchall()
        return [Anime.from_row(r) for r in rows]

    @staticmethod
    def find_by_id(anime_id: int) -> Optional[Anime]:
        """Return the anime with the given id, or ``None``."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM anime WHERE id = ?", (anime_id,)
            ).fetchone()
        if row is None:
            return None
        return Anime.from_row(row)

    def delete(self) -> None:
        """Delete this record from the database (no-op if unsaved)."""
        if self.id is None:
            return
        with get_connection() as conn:
            conn.execute("DELETE FROM anime WHERE id = ?", (self.id,))
            conn.commit()
