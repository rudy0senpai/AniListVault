"""Schema and data migrations.

Migrations are **additive and non-destructive**: new columns and tables are
added, the legacy ``score`` column is retained for backward compatibility,
and no user data is destroyed.  Each migration bumps ``meta.schema_version``.

The score → tier conversion is *never* automatic; see
:func:`migrate_scores_to_tiers`.

v2 — personal tier system (anime).
v3 — literature (manga / manhwa / manhua) support, in its own table so
    the existing anime rows, tiers and poster paths are untouched.
"""

from __future__ import annotations

import datetime
import logging
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from animevault.database import database_path, get_connection
from animevault.tiers import DEFAULT_SCORE_TO_TIER, score_to_tier

logger = logging.getLogger(__name__)

TARGET_SCHEMA_VERSION = 3


# ── Helpers ───────────────────────────────────────────────────────

def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def get_schema_version() -> int:
    """Read the current schema version from ``meta`` (0 if unset)."""
    with get_connection() as conn:
        if not _table_exists(conn, "meta"):
            return 0
        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
        if row is None:
            return 0
        try:
            return int(row["value"])
        except (TypeError, ValueError):
            return 0


def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES ('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(version),),
    )


# ── Backup ────────────────────────────────────────────────────────

def backup_database(suffix: Optional[str] = None) -> Optional[Path]:
    """Copy the live database next to itself with a timestamp suffix.

    Uses SQLite's online backup API so a WAL database is captured
    consistently.  Returns the backup path, or ``None`` when there is no
    database file yet.
    """
    src = database_path()
    if not src.exists():
        return None

    stamp = suffix or datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = src.with_name(f"{src.stem}.backup-{stamp}{src.suffix}")

    try:
        src_conn = sqlite3.connect(str(src))
        dest_conn = sqlite3.connect(str(dest))
        try:
            src_conn.backup(dest_conn)
        finally:
            dest_conn.close()
            src_conn.close()
    except Exception:
        try:
            shutil.copy2(src, dest)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Backup failed for %s: %s", src, exc)
            return None

    logger.info("Database backed up to %s", dest)
    return dest


# ── Schema migrations ─────────────────────────────────────────────

def _add_column_if_missing(
    conn: sqlite3.Connection, table: str, column: str, decl: str
) -> bool:
    """Add *column* to *table* when absent.  Returns True when added."""
    if column in _column_names(conn, table):
        return False
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
    logger.info("Added column %s.%s", table, column)
    return True


def migrate_to_v2(conn: sqlite3.Connection) -> bool:
    """v1 → v2: introduce the personal tier and its supporting fields.

    The legacy ``score`` column is intentionally **kept** so old data and
    old backups remain readable.
    """
    changed = False
    changed |= _add_column_if_missing(conn, "anime", "tier", "TEXT")
    changed |= _add_column_if_missing(conn, "anime", "rewatches", "INTEGER DEFAULT 0")
    changed |= _add_column_if_missing(conn, "anime", "episodes_watched", "INTEGER DEFAULT 0")
    changed |= _add_column_if_missing(conn, "anime", "favorite", "INTEGER DEFAULT 0")
    changed |= _add_column_if_missing(conn, "anime", "first_watched", "TEXT DEFAULT ''")
    changed |= _add_column_if_missing(conn, "anime", "last_watched", "TEXT DEFAULT ''")
    changed |= _add_column_if_missing(conn, "anime", "completed_date", "TEXT DEFAULT ''")
    changed |= _add_column_if_missing(conn, "anime", "privacy", "TEXT DEFAULT 'public'")
    changed |= _add_column_if_missing(conn, "anime_metadata", "anidb_id", "INTEGER")
    return changed


# Literature lives in its own table: no anime row is touched, so the
# migration cannot endanger existing data, tiers or poster paths.
_LITERATURE_SQL = """
CREATE TABLE IF NOT EXISTS literature (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    category         TEXT    NOT NULL DEFAULT 'manga',
    title            TEXT    NOT NULL,
    title_native     TEXT    DEFAULT '',
    synonyms         TEXT    DEFAULT '',
    format           TEXT    DEFAULT '',
    status           TEXT    NOT NULL DEFAULT 'watching',
    tier             TEXT,
    rewatches        INTEGER DEFAULT 0,
    chapters_read    INTEGER DEFAULT 0,
    chapters         INTEGER DEFAULT 0,
    volumes          INTEGER DEFAULT 0,
    volumes_read     INTEGER DEFAULT 0,
    favorite         INTEGER DEFAULT 0,
    notes            TEXT    DEFAULT '',
    first_read       TEXT    DEFAULT '',
    last_read        TEXT    DEFAULT '',
    completed_date   TEXT    DEFAULT '',
    privacy          TEXT    DEFAULT 'public',
    origin_country   TEXT    DEFAULT ''
);

CREATE TABLE IF NOT EXISTS literature_metadata (
    literature_id     INTEGER PRIMARY KEY,
    title_en          TEXT DEFAULT '',
    synopsis          TEXT DEFAULT '',
    genres            TEXT DEFAULT '',
    authors           TEXT DEFAULT '',
    artists           TEXT DEFAULT '',
    serialization     TEXT DEFAULT '',
    pub_status        TEXT DEFAULT '',
    started_at        TEXT DEFAULT '',
    ended_at          TEXT DEFAULT '',
    cover_url         TEXT DEFAULT '',
    cover_path        TEXT DEFAULT '',
    anilist_id        INTEGER,
    kitsu_id          TEXT DEFAULT '',
    mal_id            INTEGER,
    source_provider   TEXT DEFAULT '',
    metadata_fetched_at TEXT DEFAULT '',
    FOREIGN KEY (literature_id) REFERENCES literature(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_lit_category ON literature(category);
CREATE INDEX IF NOT EXISTS idx_lit_tier ON literature(tier);
CREATE INDEX IF NOT EXISTS idx_lit_title ON literature(title);
CREATE INDEX IF NOT EXISTS idx_lit_anilist ON literature_metadata(anilist_id);
"""


def migrate_to_v3(conn: sqlite3.Connection) -> bool:
    """v2 → v3: add first-class Manga / Manhwa / Manhua support.

    Creates the ``literature`` and ``literature_metadata`` tables.  Purely
    additive: the ``anime`` table is not altered, so existing anime,
    tiers, notes and poster paths are preserved by construction.
    """
    conn.executescript(_LITERATURE_SQL)
    logger.info("Literature tables created (manga / manhwa / manhua)")
    return True


_MIGRATIONS = {
    2: migrate_to_v2,
    3: migrate_to_v3,
}


def run_migrations() -> bool:
    """Apply any outstanding schema migrations.  Returns True if changed.

    Safe to call on every startup — migrations are idempotent.
    """
    with get_connection() as conn:
        current = get_schema_version()
        target = TARGET_SCHEMA_VERSION

        changed = False
        for version in range(current + 1, target + 1):
            fn = _MIGRATIONS.get(version)
            if fn is None:
                logger.warning("No migration defined for schema version %s", version)
                continue
            if fn(conn):
                changed = True
            _set_schema_version(conn, version)
            logger.info("Applied migration to schema version %s", version)

        if changed:
            conn.commit()
        return changed


# ── Score → tier conversion (explicit opt-in only) ────────────────

@dataclass
class ScoreConversionResult:
    """Outcome of an opt-in score → tier conversion."""

    converted: int = 0
    skipped_no_score: int = 0
    skipped_existing_tier: int = 0

    def as_dict(self) -> dict:
        return {
            "converted": self.converted,
            "skipped_no_score": self.skipped_no_score,
            "skipped_existing_tier": self.skipped_existing_tier,
        }


def migrate_scores_to_tiers(
    mapping: Optional[tuple[tuple[float, float, str], ...]] = None,
    *,
    overwrite_existing: bool = False,
) -> ScoreConversionResult:
    """Convert legacy numeric scores into tiers — **only when called explicitly**.

    Records that already have a tier are left alone unless
    *overwrite_existing* is true.  Records without a score are skipped.

    Never invoked by ``initialize_database`` or ``run_migrations``.
    """
    result = ScoreConversionResult()
    table = DEFAULT_SCORE_TO_TIER if mapping is None else mapping

    with get_connection() as conn:
        cols = _column_names(conn, "anime")
        if "score" not in cols:
            logger.warning("No score column present; nothing to convert")
            return result
        if "tier" not in cols:
            logger.warning("No tier column present; run run_migrations() first")
            return result

        rows = conn.execute("SELECT id, score, tier FROM anime").fetchall()
        updates: list[tuple[str, int]] = []

        for row in rows:
            score = row["score"]
            existing_tier = row["tier"]
            if existing_tier and not overwrite_existing:
                result.skipped_existing_tier += 1
                continue
            if score is None:
                result.skipped_no_score += 1
                continue
            tier = score_to_tier(float(score), table)
            if tier is None:
                result.skipped_no_score += 1
                continue
            updates.append((tier, row["id"]))

        if updates:
            conn.executemany("UPDATE anime SET tier = ? WHERE id = ?", updates)
            conn.commit()

    result.converted = len(updates)
    logger.info("Converted %s scores to tiers", result.converted)
    return result


def unassigned_tier_count() -> int:
    """Count anime with no tier assigned."""
    with get_connection() as conn:
        if "tier" not in _column_names(conn, "anime"):
            return 0
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM anime WHERE tier IS NULL OR tier = ''"
        ).fetchone()
        return int(row["n"]) if row else 0


def legacy_score_count() -> int:
    """Count anime that still carry a legacy numeric score."""
    with get_connection() as conn:
        if "score" not in _column_names(conn, "anime"):
            return 0
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM anime WHERE score IS NOT NULL"
        ).fetchone()
        return int(row["n"]) if row else 0