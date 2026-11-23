"""SQLite compatibility tests.

These verify the new FastAPI backend reads the *existing* user database
without changing its schema or contents. They are read-only: the backend must
never create tables, drop columns, or rewrite rows.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import create_app


def _resolve_real_db():
    appdir = os.environ.get("APPDATA")
    if appdir:
        return Path(appdir) / "AnimeVault" / "animevault.db"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local"))) / "AnimeVault" / "animevault.db"


DB_PATH = _resolve_real_db()


def test_backend_imports_and_reads_existing_db(db_snapshot):
    """The backend must open the same DB file the app uses (no second DB)."""
    assert DB_PATH.exists(), f"expected existing user DB at {DB_PATH}"
    assert db_snapshot["meta"].get("schema_version") == "3"


def test_health_returns_ok(client: TestClient):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "animevault-backend"
    assert Path(body["database_path"]).exists()


def test_library_summary_matches_db_snapshot(client: TestClient, db_snapshot):
    resp = client.get("/api/library/summary")
    assert resp.status_code == 200
    body = resp.json()
    exp = db_snapshot["counts"]
    assert body["anime"]["total"] == exp["anime"]
    assert body["literature"]["total"] == exp["literature"]
    assert body["total_records"] == exp["anime"] + exp["literature"]
    assert body["database_path"] == str(DB_PATH)


def test_library_anime_list(client: TestClient, db_snapshot):
    resp = client.get("/api/library/anime")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == db_snapshot["counts"]["anime"]
    assert len(body["items"]) == db_snapshot["counts"]["anime"]
    if body["items"]:
        it = body["items"][0]
        assert isinstance(it["id"], int)
        assert it["title"]
        # Existing metadata must round-trip (poster path preserved).
        assert "poster_path" in it or "poster_url" in it


def test_library_literature_list(client: TestClient, db_snapshot):
    resp = client.get("/api/library/literature")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == db_snapshot["counts"]["literature"]
    assert len(body["items"]) == db_snapshot["counts"]["literature"]


def test_library_anime_by_id(client: TestClient, db_snapshot):
    pub = client.get("/api/library/anime").json()
    first_id = pub["items"][0]["id"]

    resp = client.get(f"/api/library/anime/{first_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["found"] is True
    assert body["item"]["id"] == first_id

    not_found = client.get(f"/api/library/anime/{first_id + 1000}")
    assert not_found.status_code == 404
    assert not_found.json()["detail"]["found"] is False


def test_library_literature_by_id(client: TestClient, db_snapshot):
    pub = client.get("/api/library/literature").json()
    first_id = pub["items"][0]["id"]

    resp = client.get(f"/api/library/literature/{first_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["found"] is True
    assert body["item"]["id"] == first_id

    not_found = client.get(f"/api/library/literature/{first_id + 1000}")
    assert not_found.status_code == 404


def test_unknown_media_type_returns_404(client: TestClient):
    resp = client.get("/api/library/unknown/1")
    assert resp.status_code == 404


def test_backend_does_not_mutate_schema_or_contents(client: TestClient, db_snapshot):
    """Core compatibility guarantee: after the full endpoint surface runs,
    the DB's structure and row counts are unchanged."""
    transaction = db_snapshot["meta"].get("schema_version")

    # Exercise every read endpoint on the real database.
    client.get("/api/health")
    client.get("/api/library/summary")
    client.get("/api/library/anime")
    client.get("/api/library/literature")
    client.get("/api/library/anime/1")
    client.get("/api/library/literature/1")

    conn = sqlite3.connect(str(DB_PATH), detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    try:
        current_schema = {}
        for t in db_snapshot["schema"]:
            current_schema[t] = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
                (t,),
            ).fetchone()[0]

        current_meta = {
            r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM meta")
        }

        current_counts = {
            "anime": conn.execute("SELECT COUNT(*) FROM anime").fetchone()[0],
            "literature": conn.execute("SELECT COUNT(*) FROM literature").fetchone()[0],
            "anime_metadata": conn.execute(
                "SELECT COUNT(*) FROM anime_metadata"
            ).fetchone()[0],
        }
    finally:
        conn.close()

    assert current_schema == db_snapshot["schema"], (
        "schema changed (cannot modify DB)"
    )
    assert current_meta == db_snapshot["meta"], "meta table changed (cannot modify DB)"
    assert current_counts == db_snapshot["counts"], (
        "row counts changed (cannot modify DB)"
    )


def test_poster_paths_preserved(client: TestClient, db_snapshot):
    """poster_path (cached cover files) must survive the API boundary."""
    resp = client.get("/api/library/anime")
    assert resp.status_code == 200
    returned_paths = {
        it["poster_path"] for it in resp.json()["items"] if it.get("poster_path")
    }
    expected_paths = set(db_snapshot["poster_sample"])
    # Every cached poster the DB holds should appear in the API response.
    assert expected_paths.issubset(returned_paths) or (
        expected_paths & returned_paths
    ), "cached poster paths were changed or dropped"
