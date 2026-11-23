"""AnimeVault API entrypoint.

A FastAPI application that exposes the existing Python business logic and
SQLite-backed models over HTTP. The backend depends only on the already
existing ``animevault`` package and never touches ``animevault.ui``.

Run with::

    uvicorn backend.main:create_app()

or, for production-style binding::

    uvicorn backend.main:create_app() --host 127.0.0.1 --port 8123
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException

from animevault.database import database_path as _default_db_path

from .services.health import health_payload
from .services.library import (
    library_summary,
    list_anime,
    list_literature,
)

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Startup: verify the existing DB is reachable (no schema change)."""
    # Light, read-only reachability check. Never run migrations or rewrites
    # here: the existing app already handles initialisation at startup.
    import sqlite3

    try:
        with sqlite3.connect(str(_default_db_path())) as _conn:
            _conn.execute("SELECT 1").fetchone()
    except Exception:
        pass
    yield


def _find_item(media_type: str, item_id: int):
    """Read a single item via the existing model layer (no SQL duplication)."""
    if media_type == "anime":
        from animevault.models.anime import Anime

        return Anime.find_by_id(item_id)
    if media_type == "literature":
        from animevault.models.literature import Literature

        return Literature.find_by_id(item_id)
    return None


def create_app() -> FastAPI:
    """Build the FastAPI application (singleton on startup)."""
    app = FastAPI(title="AnimeVault API", version="1.0.0", lifespan=_lifespan)

    @app.get("/api/health", response_model=dict)
    def health():
        return health_payload(_default_db_path())

    @app.get("/api/library/summary", response_model=dict)
    def get_library_summary():
        return library_summary()

    @app.get("/api/library/anime", response_model=dict)
    def get_anime_list():
        items = list_anime()
        return {"items": items, "total": len(items), "filters_applied": {}}

    @app.get("/api/library/literature", response_model=dict)
    def get_literature_list():
        items = list_literature()
        return {"items": items, "total": len(items), "filters_applied": {}}

    @app.get("/api/library/{media_type}/{item_id}", response_model=dict)
    def get_library_item(media_type: str, item_id: int):
        item = _find_item(media_type, item_id)
        if item is None:
            raise HTTPException(
                status_code=404, detail={"item": None, "found": False}
            )
        return {"item": item, "found": True}

    return app
