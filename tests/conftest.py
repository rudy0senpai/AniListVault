"""Pytest fixtures — provides a fresh temp database per test session."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from PySide6.QtCore import QSettings

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

    db_mod._disconnect_cached()

    set_database_path(db_file)
    initialize_database(db_file)

    # Bring the schema to the current version so tests exercise the real
    # columns (tier, rewatches, literature tables, …).
    from animevault.migration import run_migrations

    run_migrations()

    yield db_file

    # Clean up thread-local connection after test
    db_mod._disconnect_cached()


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

# ── Backend (FastAPI) fixtures ──────────────────────────────────────────
import os
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import create_app

#: The REAL user database that the PySide6 app opens.
def _resolve_real_db() -> Path:
    appdir = os.environ.get("APPDATA")
    if appdir:
        return Path(appdir) / "AnimeVault" / "animevault.db"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local"))) / "AnimeVault" / "animevault.db"


REAL_DB = _resolve_real_db()


def _snapshot(path: Path) -> dict:
    import sqlite3
    conn = sqlite3.connect(str(path), detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    try:
        tables = [
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            ).fetchall()
        ]
        schema = {}
        for t in tables:
            schema[t] = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (t,)
            ).fetchone()[0]
        meta = {
            r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM meta")
        }
        counts = {
            "anime": conn.execute("SELECT COUNT(*) FROM anime").fetchone()[0],
            "literature": conn.execute("SELECT COUNT(*) FROM literature").fetchone()[0],
            "anime_metadata": conn.execute(
                "SELECT COUNT(*) FROM anime_metadata"
            ).fetchone()[0],
        }
        poster_rows = conn.execute(
            "SELECT poster_path FROM anime_metadata WHERE poster_path != '' ORDER BY poster_path LIMIT 200"
        ).fetchall()
        return {
            "schema": schema,
            "meta": meta,
            "counts": counts,
            "poster_sample": [r["poster_path"] for r in poster_rows],
        }
    finally:
        conn.close()


@pytest.fixture()
def db_snapshot():
    """Snapshot the REAL user database; restore afterwards."""
    old = database_path()
    set_database_path(REAL_DB)
    try:
        snap = _snapshot(REAL_DB)
    finally:
        set_database_path(old)
    return snap


@pytest.fixture()
def client(db_snapshot):
    """TestClient pointing at the real user database."""
    old = database_path()
    set_database_path(REAL_DB)
    app = create_app()
    with TestClient(app) as c:
        yield c
    set_database_path(old)


Path = Path  # no-op tidy-up
DB_PATH = REAL_DB
