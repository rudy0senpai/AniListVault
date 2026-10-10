"""File-based JSON response cache with per-key TTL."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from threading import Lock
from typing import Any, Optional

logger = logging.getLogger(__name__)

_CACHE_DIR: Path = (
    Path(os.environ.get("APPDATA", Path.home() / ".local")) / "AnimeVault" / "cache"
)

# Default TTL presets (seconds)
TTL_SEARCH: float = 600.0       # 10 minutes
TTL_METADATA: float = 86400.0   # 24 hours
TTL_POSTER: Optional[float] = None  # Persistent (no expiry)
_write_locks: dict[str, Lock] = {}
_write_locks_guard = Lock()


def set_cache_dir(path: Path) -> None:
    """Override cache directory (use in tests)."""
    global _CACHE_DIR
    _CACHE_DIR = path


def cache_dir() -> Path:
    return _CACHE_DIR


def _key_to_path(key: str) -> Path:
    safe = key.replace(":", "_").replace("/", "_").replace(" ", "_").replace("\\", "_")
    if len(safe) > 180:
        safe = hashlib.md5(key.encode()).hexdigest()
    return _CACHE_DIR / f"{safe}.json"


def get(key: str, ttl: Optional[float] = None) -> Optional[Any]:
    """Return cached payload for *key*, or ``None`` if missing/expired."""
    path = _key_to_path(key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if ttl is not None:
            age = time.time() - float(data.get("_cached_at", 0))
            if age > ttl:
                logger.debug("Cache expired for %r (age=%.0fs)", key, age)
                return None
        return data.get("_payload")
    except Exception as exc:
        logger.debug("Cache read error for %r: %s", key, exc)
        return None


def put(key: str, payload: Any) -> None:
    """Store *payload* in the cache under *key*."""
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _key_to_path(key)
        with _write_locks_guard:
            lock = _write_locks.setdefault(str(path), Lock())
        with lock:
            data = {"_cached_at": time.time(), "_payload": payload}
            temporary = path.with_name(f"{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
            try:
                temporary.write_text(
                    json.dumps(data, ensure_ascii=False, default=str),
                    encoding="utf-8",
                )
                os.replace(temporary, path)
            finally:
                if temporary.exists():
                    temporary.unlink()
    except Exception as exc:
        logger.debug("Cache write error for %r: %s", key, exc)


def invalidate(key: str) -> None:
    path = _key_to_path(key)
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass


def clear_all() -> None:
    """Remove every cached file (for testing / reset)."""
    try:
        for f in _CACHE_DIR.glob("*.json"):
            try:
                f.unlink()
            except Exception:
                pass
    except Exception:
        pass
