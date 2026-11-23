"""Request-scoped SQLite access for the FastAPI backend.

This module deliberately does **not** create, modify, or replace any
database file. It reuses the existing :mod:`animevault.database` connection
logic, which is per-thread. The existing SQLite database is opened read-only
from the API's perspective; no schema or row mutations are performed here.

The backend intentionally depends only on the already-existing ``animevault``
package (``models``, ``services``, ``database``) and never touches
``animevault.ui``.
"""

from __future__ import annotations

from contextlib import contextmanager

from animevault.database import get_connection, database_path


@contextmanager
def get_db():
    """Yield a SQLite connection for the current request thread.

    The connection is the thread-local handle already used by the existing
    ``animevault.models`` layer, so model queries and this dependency share
    exactly one connection per request. It is closed again when the request
    finishes.
    """
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
