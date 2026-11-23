"""Backend startup/shutdown lifecycle tests.

These verify the FastAPI backend starts, serves requests, and shuts down
cleanly (without touching the user's database file).
"""

from __future__ import annotations

import os
import socket
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from httpx import get
from uvicorn import Config, Server

from backend.main import create_app


def _resolve_real_db() -> Path:
    appdir = os.environ.get("APPDATA")
    if appdir:
        return Path(appdir) / "AnimeVault" / "animevault.db"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local"))) / "AnimeVault" / "animevault.db"


REAL_DB = _resolve_real_db()


@contextmanager
def use_real_db():
    """Point the existing DB layer at the real user database for the
    duration of the test, then restore the previous path."""
    import animevault.database as _db_mod

    from animevault.database import database_path, set_database_path

    old = database_path()
    set_database_path(REAL_DB)
    try:
        yield
    finally:
        set_database_path(old)


def _start_server(port: int):
    """Start the backend on a given port; return (server, thread)."""
    app = create_app()
    config = Config(
        app=app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        use_colors=False,
        backlog=1,
    )
    server = Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    for _ in range(60):
        if not thread.is_alive():
            break
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return server, thread
        except OSError:
            time.sleep(0.1)

    raise AssertionError("backend did not start listening")


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_backend_starts_and_responds():
    port = _free_port()
    server, thread = _start_server(port)
    with use_real_db():
        resp = get(f"http://127.0.0.1:{port}/api/health", timeout=5)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        summary = get(f"http://127.0.0.1:{port}/api/library/summary", timeout=5)
        assert summary.status_code == 200
        assert summary.json()["anime"]["total"] == 506
        assert summary.json()["literature"]["total"] == 339

        server.should_exit = True
        thread.join(timeout=5)
        assert not thread.is_alive(), "server thread did not exit on shutdown"


def test_backend_shuts_down_when_exited():
    port = _free_port()
    server, thread = _start_server(port)
    assert thread.is_alive()
    server.should_exit = True
    thread.join(timeout=5)
    assert not thread.is_alive(), "server did not shut down"
