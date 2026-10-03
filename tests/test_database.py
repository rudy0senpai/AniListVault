"""Tests for database initialization and schema."""

import sqlite3
from pathlib import Path

import pytest

from animevault.database import (
    SCHEMA_VERSION,
    database_path,
    initialize_database,
    set_database_path,
)


class TestInitializeDatabase:
    """Verify the schema is created correctly."""

    def test_creates_database_file(self, tmp_path):
        """initialize_database should create a .db file on disk."""
        db_file = tmp_path / "test.db"
        set_database_path(db_file)

        info = initialize_database(db_file)

        assert info.path == db_file
        assert db_file.exists()

    def test_returns_schema_info(self, tmp_path):
        """initialize_database returns a SchemaInfo with the version."""
        db_file = tmp_path / "test.db"
        set_database_path(db_file)

        info = initialize_database(db_file)

        assert info.version == SCHEMA_VERSION

    def test_anime_table_has_expected_columns(self, db_conn: sqlite3.Connection):
        """The anime table must have the required columns.

        The v2 tier migration adds the personal tier and tracking fields
        on top of the original set; every one must be present.
        """
        cursor = db_conn.execute("PRAGMA table_info(anime)")
        columns = {row["name"]: row for row in cursor.fetchall()}

        expected = {
            "id", "title", "title_ja", "episodes", "status", "score", "notes",
            "tier", "rewatches", "episodes_watched", "favorite",
            "first_watched", "last_watched", "completed_date", "privacy",
        }
        assert expected == set(columns.keys()), (
            f"Missing columns: {expected - set(columns.keys())}"
        )

    def test_legacy_score_column_retained(self, db_conn: sqlite3.Connection):
        """The legacy score column must survive the tier migration."""
        cursor = db_conn.execute("PRAGMA table_info(anime)")
        columns = {row["name"] for row in cursor.fetchall()}
        assert "score" in columns

    def test_anime_primary_key(self, db_conn: sqlite3.Connection):
        """id must be the primary key with autoincrement."""
        cursor = db_conn.execute("PRAGMA table_info(anime)")
        cols = cursor.fetchall()
        id_col = next(c for c in cols if c["name"] == "id")
        assert id_col["pk"] == 1
        assert (id_col["dflt_value"] and "AUTOINCREMENT" in id_col["dflt_value"]) or id_col["type"].upper() == "INTEGER"

    def test_title_not_null(self, db_conn: sqlite3.Connection):
        """title column must have NOT NULL constraint."""
        cursor = db_conn.execute("PRAGMA table_info(anime)")
        cols = cursor.fetchall()
        title_col = next(c for c in cols if c["name"] == "title")
        assert title_col["notnull"] == 1

    def test_status_default(self, db_conn: sqlite3.Connection):
        """status column must default to 'plan_to_watch'."""
        cursor = db_conn.execute("PRAGMA table_info(anime)")
        cols = cursor.fetchall()
        status_col = next(c for c in cols if c["name"] == "status")
        assert status_col["dflt_value"] == "'plan_to_watch'"

    def test_episodes_default_zero(self, db_conn: sqlite3.Connection):
        """episodes column must default to 0."""
        cursor = db_conn.execute("PRAGMA table_info(anime)")
        cols = cursor.fetchall()
        episodes_col = next(c for c in cols if c["name"] == "episodes")
        assert episodes_col["dflt_value"] == "0"

    def test_notes_default_empty(self, db_conn: sqlite3.Connection):
        """notes column must default to empty string."""
        cursor = db_conn.execute("PRAGMA table_info(anime)")
        cols = cursor.fetchall()
        notes_col = next(c for c in cols if c["name"] == "notes")
        assert notes_col["dflt_value"] == "''"

    def test_score_column_is_real(self, db_conn: sqlite3.Connection):
        """score column must accept REAL (float) values."""
        cursor = db_conn.execute("PRAGMA table_info(anime)")
        cols = cursor.fetchall()
        score_col = next(c for c in cols if c["name"] == "score")
        assert score_col["type"].upper() == "REAL"

    def test_title_ja_nullable(self, db_conn: sqlite3.Connection):
        """title_ja column must allow NULL."""
        cursor = db_conn.execute("PRAGMA table_info(anime)")
        cols = cursor.fetchall()
        title_ja_col = next(c for c in cols if c["name"] == "title_ja")
        assert title_ja_col["notnull"] == 0

    def test_indexes_exist(self, db_conn: sqlite3.Connection):
        """Indexes on title and status should exist."""
        cursor = db_conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = {row["name"] for row in cursor.fetchall()}
        assert "idx_anime_title" in indexes
        assert "idx_anime_status" in indexes

    def test_meta_table_stores_schema_version(self, db_conn: sqlite3.Connection):
        """The meta table should record the fully migrated schema version."""
        from animevault.migration import TARGET_SCHEMA_VERSION

        cursor = db_conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        )
        row = cursor.fetchone()
        assert row is not None
        assert int(row["value"]) == TARGET_SCHEMA_VERSION

    def test_literature_tables_created_by_migration(self, db_conn: sqlite3.Connection):
        """The v3 migration must add first-class literature tables."""
        cursor = db_conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row["name"] for row in cursor.fetchall()}
        assert "literature" in tables
        assert "literature_metadata" in tables

    def test_literature_has_chapter_columns(self, db_conn: sqlite3.Connection):
        """Literature rows track chapters, not episodes."""
        cursor = db_conn.execute("PRAGMA table_info(literature)")
        columns = {row["name"] for row in cursor.fetchall()}
        assert {"chapters", "chapters_read", "volumes", "category"} <= columns

    def test_literature_has_tier_and_personal_fields(self, db_conn: sqlite3.Connection):
        cursor = db_conn.execute("PRAGMA table_info(literature)")
        columns = {row["name"] for row in cursor.fetchall()}
        assert {"tier", "status", "favorite", "notes"} <= columns

    def test_idempotent_init(self, tmp_path):
        """Calling initialize_database twice should not error."""
        db_file = tmp_path / "test.db"
        set_database_path(db_file)

        initialize_database(db_file)
        initialize_database(db_file)  # second call should be safe

        # Verify table still has correct structure
        conn = sqlite3.connect(str(db_file))
        cursor = conn.execute("PRAGMA table_info(anime)")
        cols = {row[1] for row in cursor.fetchall()}
        conn.close()

        assert {"id", "title", "title_ja", "episodes", "status", "score", "notes"} == cols

    def test_get_connection_uses_configured_path(self, isolated_database):
        """get_connection should use the path set by set_database_path."""
        set_database_path(isolated_database)
        from animevault.database import get_connection

        with get_connection() as conn:
            assert conn.execute("SELECT 1").fetchone() is not None
