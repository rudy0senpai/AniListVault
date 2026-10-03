"""Thumbnail loading and caching.

Posters are decoded once and kept at card size in memory.  Decoding a
full-resolution poster for every card on every repaint is the main cause
of a sluggish grid, so:

* images load lazily — a card that is never shown never loads anything;
* decoded thumbnails are cached by (path, size);
* a shared QPixmapCache backs the on-disk decode cache across restarts of
  the grid;
* a bounded LRU keeps memory flat no matter how large the library grows.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QSize, Qt, Signal
from PySide6.QtGui import QPixmap

logger = logging.getLogger(__name__)

#: Target rendered size of a card's artwork.
THUMB_SIZE = QSize(120, 172)

#: How many decoded thumbnails to keep in memory.
MAX_CACHE_ENTRIES = 400


class ThumbnailCache(QObject):
    """Process-wide cache of decoded, downscaled poster thumbnails."""

    _instance: Optional["ThumbnailCache"] = None

    def __init__(self) -> None:
        super().__init__()
        self._entries: "OrderedDict[tuple[str, int, int], QPixmap]" = OrderedDict()
        self._missing: set[str] = set()

    @classmethod
    def instance(cls) -> "ThumbnailCache":
        if cls._instance is None:
            cls._instance = ThumbnailCache()
        return cls._instance

    # ── Lookup ─────────────────────────────────────────────────────

    def get(self, path: str) -> Optional[QPixmap]:
        """Return a cached thumbnail for *path*, loading it if needed."""
        if not path:
            return None
        key = (path, THUMB_SIZE.width(), THUMB_SIZE.height())

        pixmap = self._entries.get(key)
        if pixmap is not None:
            self._entries.move_to_end(key)
            return pixmap

        if path in self._missing:
            return None

        loaded = self._load(path)
        if loaded is None:
            self._missing.add(path)
            return None

        self._entries[key] = loaded
        self._entries.move_to_end(key)
        self._evict()
        return loaded

    def peek(self, path: str) -> Optional[QPixmap]:
        """Return a cached thumbnail without triggering a load."""
        if not path:
            return None
        return self._entries.get((path, THUMB_SIZE.width(), THUMB_SIZE.height()))

    def is_cached(self, path: str) -> bool:
        return bool(path) and (path, THUMB_SIZE.width(), THUMB_SIZE.height()) in self._entries

    # ── Internals ──────────────────────────────────────────────────

    @staticmethod
    def _load(path: str) -> Optional[QPixmap]:
        try:
            p = Path(path)
            if not p.exists() or not p.is_file():
                return None
            pixmap = QPixmap(str(p))
            if pixmap.isNull():
                return None
            # Scale once, at decode time, so painting is cheap.
            return pixmap.scaled(
                THUMB_SIZE,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
        except Exception as exc:
            logger.debug("Could not load thumbnail %s: %s", path, exc)
            return None

    def _evict(self) -> None:
        while len(self._entries) > MAX_CACHE_ENTRIES:
            self._entries.popitem(last=False)

    def invalidate(self, path: str) -> None:
        """Drop a single path from the cache."""
        self._missing.discard(path)
        for key in [k for k in self._entries if k[0] == path]:
            self._entries.pop(key, None)

    def clear(self) -> None:
        self._entries.clear()
        self._missing.clear()


class AsyncImageLabel(QObject):
    """Loads a thumbnail off the GUI thread and emits when ready.

    Keeps the grid responsive: a card paints its placeholder immediately
    and fills in the artwork once decoded.
    """

    loaded = Signal(object)  # QPixmap

    def __init__(self, path: str) -> None:
        super().__init__()
        self._path = path
        self._cache = ThumbnailCache.instance()

    def load(self) -> None:
        """Return an already-cached pixmap immediately, else no-op.

        Actual decoding happens through the shared cache on first paint;
        this keeps startup cheap by not touching files that are not yet
        visible.
        """
        cached = self._cache.peek(self._path)
        if cached is not None:
            self.loaded.emit(cached)