"""Pytest fixtures — provides a fresh temp database per test session."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from animevault.database import database_path, initialize_database, set_database_path


@pytest.fixture(autouse=True)
def isolated_database(tmp_path: Path, monkeypatch):
    """Redirect the module-level DB path to a temp file for each test.

    This ensures tests never touch the real user database.
    """
    db_file = tmp_path / "test_animevault.db"

    # Clear any cached thread-local connection so a fresh one is created.
    import animevault.database as db_mod

    if hasattr(db_mod._local, "conn"):
        db_mod._local.conn.close()
        del db_mod._local.conn

    set_database_path(db_file)
    initialize_database(db_file)

    # Bring the schema to the current version so tests exercise the real
    # columns (tier, rewatches, literature tables, …).
    from animevault.migration import run_migrations

    run_migrations()

    yield db_file

    # Clean up thread-local connection after test
    if hasattr(db_mod._local, "conn"):
        db_mod._local.conn.close()
        del db_mod._local.conn


@pytest.fixture
def db_conn(isolated_database: Path) -> sqlite3.Connection:
    """Direct connection to the test database for assertions."""
    conn = sqlite3.connect(str(isolated_database))
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture
def migrated_database(isolated_database: Path):
    """Isolated database with all schema migrations applied.

    ``isolated_database`` already migrates, so this is an explicit alias
    for tests that want to state that dependency.
    """
    return isolated_database
