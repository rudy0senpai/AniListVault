"""Image cache management with LRU eviction for AnimeVault.

Manages the poster/image cache directory, enforces a configurable size
limit (in MB), and provides cache-clearing with storage reporting.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Cache directory defaults to ~/.AnimeVault/cache/posters
CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "backend" / "instance" / "cache" / "posters"
if os.environ.get("ANIMEVAULT_CACHE_DIR"):
    CACHE_DIR = Path(os.environ["ANIMEVAULT_CACHE_DIR"])
elif os.environ.get("APPDATA"):
    CACHE_DIR = Path(os.environ["APPDATA"]) / "AnimeVault" / "cache" / "posters"
else:
    CACHE_DIR = Path.home() / ".AnimeVault" / "cache" / "posters"

DEFAULT_MAX_SIZE_MB = 500  # 500 MB default
MIN_MAX_SIZE_MB = 100
MAX_MAX_SIZE_MB = 2000


def get_cache_dir() -> Path:
    """Return the cache directory, creating it if needed."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR


class CacheService:
    """Image cache management with LRU eviction.

    Enforces a maximum cache size (in MB), evicts oldest files when the
    limit is exceeded, and provides cache-clearing with storage reporting.
    """

    def __init__(self, cache_dir: Path | None = None, max_size_mb: int = DEFAULT_MAX_SIZE_MB) -> None:
        self._cache_dir = cache_dir or get_cache_dir()
        self._lock = threading.Lock()
        self._max_size_bytes = max_size_mb * 1024 * 1024
        self._current_size = 0
        self._load_cache_state()

    def _load_cache_state(self) -> None:
        """Load current cache state from disk."""
        if not self._cache_dir.is_dir():
            self._current_size = 0
            return
        total = 0
        for f in self._cache_dir.iterdir():
            if f.is_file():
                try:
                    total += f.stat().st_size
                except OSError:
                    pass
        self._current_size = total

    def set_max_size(self, max_mb: int) -> None:
        """Set the maximum cache size (in MB). Enforces the configured limit."""
        if not MIN_MAX_SIZE_MB <= max_mb <= MAX_MAX_SIZE_MB:
            logger.warning("Cache size %d MB out of range [%d, %d]; using %d",
                          max_mb, MIN_MAX_SIZE_MB, MAX_MAX_SIZE_MB, DEFAULT_MAX_SIZE_MB)
            max_mb = DEFAULT_MAX_SIZE_MB
        self._max_size_bytes = max_mb * 1024 * 1024
        self._enforce_limit()

    def current_size(self) -> int:
        """Return current cache size in bytes."""
        return self._current_size

    def current_size_mb(self) -> float:
        """Return current cache size in MB."""
        return self._current_size / (1024 * 1024)

    def _enforce_limit(self) -> None:
        """Evict oldest files if over the configured limit."""
        with self._lock:
            if self._current_size <= self._max_size_bytes:
                return
            # Get files sorted by modification time (oldest first)
            files = []
            for f in self._cache_dir.iterdir():
                if f.is_file():
                    try:
                        files.append((f.stat().st_mtime, f))
                    except OSError:
                        pass
            files.sort()
            for _, f in files:
                if self._current_size <= self._max_size_bytes:
                    break
                try:
                    self._current_size -= f.stat().st_size
                    f.unlink()
                except Exception:
                    pass
            logger.info("Evicted files to enforce cache limit: %.0f MB used of %d MB",
                        self.current_size_mb(), self._max_size_bytes / (1024 * 1024))

    def clear(self) -> int:
        """Clear the entire cache. Returns number of files removed."""
        with self._lock:
            count = 0
            for f in self._cache_dir.iterdir():
                if f.is_file():
                    try:
                        f.unlink()
                        count += 1
                    except Exception:
                        pass
            self._current_size = 0
            logger.info("Cache cleared (%d files removed)", count)
            return count

    def get_storage_freed(self) -> int:
        """Return approximate storage freed in bytes (current cache size)."""
        return self._current_size
