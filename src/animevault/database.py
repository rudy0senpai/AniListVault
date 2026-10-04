"""SQLite database initialization and connection management for AnimeVault."""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

# ── Database path ────────────────────────────────────────────────

_APP_DIR = Path(os.environ.get("APPDATA", Path.home() / ".local")) / "AnimeVault"
_DB_PATH = _APP_DIR / "animevault.db"


def set_database_path(path: Path) -> None:
    """Override the database path.

    Any connection already cached for this thread is closed first —
    otherwise a path change would silently keep using the previous file,
    which shows up as confusing "no such column" errors when the two
    databases have different schemas.
    """
    global _DB_PATH
    _DB_PATH = Path(path)
    _disconnect_cached()


def database_path() -> Path:
    """Return the current database file path."""
    return _DB_PATH


# ── Schema ───────────────────────────────────────────────────────

#: Version of the schema this module creates directly.  Further versions
#: are applied by :mod:`animevault.migration`.
BASE_SCHEMA_VERSION = 1

#: Backwards-compatible alias.
SCHEMA_VERSION = BASE_SCHEMA_VERSION

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS anime (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    title    TEXT    NOT NULL,
    title_ja TEXT,
    episodes INTEGER DEFAULT 0,
    status   TEXT    NOT NULL DEFAULT 'plan_to_watch',
    score    REAL,
    notes    TEXT    DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_anime_title ON anime(title);
CREATE INDEX IF NOT EXISTS idx_anime_status ON anime(status);

CREATE TABLE IF NOT EXISTS anime_metadata (
    anime_id            INTEGER PRIMARY KEY,
    title_en            TEXT    DEFAULT '',
    synopsis            TEXT    DEFAULT '',
    media_type          TEXT    DEFAULT '',
    airing_status       TEXT    DEFAULT '',
    genres              TEXT    DEFAULT '',
    studios             TEXT    DEFAULT '',
    aired_from          TEXT    DEFAULT '',
    aired_to            TEXT    DEFAULT '',
    season              TEXT    DEFAULT '',
    season_year         INTEGER,
    duration            INTEGER DEFAULT 0,
    poster_url          TEXT    DEFAULT '',
    poster_path         TEXT    DEFAULT '',
    mal_id              INTEGER,
    anilist_id          INTEGER,
    kitsu_id            TEXT    DEFAULT '',
    tmdb_id             INTEGER,
    source_provider     TEXT    DEFAULT '',
    metadata_fetched_at TEXT    DEFAULT '',
    FOREIGN KEY (anime_id) REFERENCES anime(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_metadata_anilist_id ON anime_metadata(anilist_id);
CREATE INDEX IF NOT EXISTS idx_metadata_mal_id ON anime_metadata(mal_id);
CREATE INDEX IF NOT EXISTS idx_metadata_kitsu_id ON anime_metadata(kitsu_id);
CREATE INDEX IF NOT EXISTS idx_metadata_tmdb_id ON anime_metadata(tmdb_id);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


# ── Connection management ──────────────────────────────────────
#
# Each thread gets its own connection to avoid cross-thread issues with
# PySide6 signal/slot delivery.

_local = threading.local()


def _disconnect_cached() -> None:
    """Close and forget this thread's cached connection, if any."""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except sqlite3.Error:
            pass
        _local.conn = None


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection for the current thread.

    The connection is created on first use per thread and reused for the
    lifetime of that thread, unless the database path changes.
    """
    conn = getattr(_local, "conn", None)
    # Reconnect when the path no longer matches, so a database switch is
    # never masked by a stale handle.
    if conn is not None and getattr(_local, "path", None) != str(_DB_PATH):
        _disconnect_cached()
        conn = None
    if conn is None:
        conn = sqlite3.connect(str(_DB_PATH), detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        _local.conn = conn
        _local.path = str(_DB_PATH)
    yield conn


# ── Initialization ───────────────────────────────────────────────

@dataclass(frozen=True)
class SchemaInfo:
    """Result of :func:`initialize_database`."""

    path: Path
    version: int


def initialize_database(path: Path | None = None) -> SchemaInfo:
    """Create the database file (if needed) and apply the schema.

    Parameters
    ----------
    path:
        Optional override for the database file location.  When *None*
        the default path returned by :func:`database_path` is used and
        the module-level path is updated so that subsequent calls to
        :func:`get_connection` use the same file.

    Returns
    -------
    SchemaInfo
        Information about the database that was initialized.
    """
    if path is not None:
        set_database_path(path)

    db_path = database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Use a short-lived connection for initialization so that the WAL
    # checkpoint and schema writes are committed independently of the
    # thread-local connection that the GUI will use.
    conn = sqlite3.connect(str(db_path), detect_types=sqlite3.PARSE_DECLTYPES)
    try:
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.executescript(_SCHEMA_SQL)
        # This records the *base* schema version only.  Later versions are
        # applied by animevault.migration.run_migrations(), so stamping the
        # final target here would make the migrations appear already-run
        # and silently skip them.
        conn.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?);",
            (str(BASE_SCHEMA_VERSION),),
        )
        conn.commit()
    finally:
        conn.close()

    return SchemaInfo(path=db_path, version=BASE_SCHEMA_VERSION)
