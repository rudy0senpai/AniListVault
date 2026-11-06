"""Recommendation caching and dismissed-recommendation handling.

Provides local caching for generated recommendation sets and tracks which
titles the user has dismissed, so they are not re-shown unless the user
explicitly resets the dismissed recommendations.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from animevault.database import get_connection

logger = logging.getLogger(__name__)

# Local cache directory (persists across sessions).
_CACHE_DIR = Path(os.environ.get("APPDATA", Path.home() / ".local")) / "AnimeVault" / "cache"
_CANDIDATE_KEY_PREFIX = "recommendation"


def _ensure_cache_dir() -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_key(user_hash: str, category: str, filters: str) -> str:
    raw = f"{user_hash}:{category}:{filters}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _cache_path(key: str) -> Path:
    return _CACHE_DIR / f"{_CANDIDATE_KEY_PREFIX}_{key}.json"


class RecommendationCache:
    """Local, file-based cache for recommendation results."""

    def __init__(self, cache_dir: Optional[Path] = None):
        self._dir = cache_dir or _CACHE_DIR
        _ensure_cache_dir()

    def get(self, user_hash: str, category: str, filters: str) -> Optional[list[dict]]:
        """Return cached recommendations, or None if not present."""
        path = _cache_path(_cache_key(user_hash, category, filters))
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read recommendation cache for %r: %s", user_hash, exc)
            return None

    def set(self, user_hash: str, category: str, filters: str,
            recommendations: list[dict]) -> None:
        """Persist recommendations to the local cache."""
        path = _cache_path(_cache_key(user_hash, category, filters))
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(recommendations, fh, ensure_ascii=False, indent=2)
        except OSError as exc:
            logger.warning("Failed to write recommendation cache for %r: %s", user_hash, exc)

    def get_dismissed(self, user_hash: str) -> set[int]:
        """Return the set of item IDs the user has dismissed."""
        path = _CACHE_DIR / f"{_CANDIDATE_KEY_PREFIX}_dismissed_{user_hash}.json"
        if not path.exists():
            return set()
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            return set(data if isinstance(data, list) else data.get("item_ids", []))
        except (json.JSONDecodeError, OSError):
            return set()

    def add_dismissed(self, user_hash: str, item_ids: Iterable[int]) -> None:
        """Record that *item_ids* have been dismissed."""
        existing = self.get_dismissed(user_hash)
        for i in item_ids:
            existing.add(i)
        path = _CACHE_DIR / f"{_CANDIDATE_KEY_PREFIX}_dismissed_{user_hash}.json"
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(sorted(existing), fh, ensure_ascii=False)
        except OSError as exc:
            logger.warning("Failed to write dismissed cache: %s", exc)

    def clear_dismissed(self, user_hash: str) -> None:
        """Clear the dismissed-recommendation set."""
        path = _CACHE_DIR / f"{_CANDIDATE_KEY_PREFIX}_dismissed_{user_hash}.json"
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass


# ── Database-backed cache (optional) ────────────────────────────────

def cache_key_from_library(user_id: int, category: str, filters: str) -> str:
    """Deterministic cache key derived from the user's library hash."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, title, genres, synopsis, tier, episodes, status "
            "FROM anime LIMIT 200"
        ).fetchall()
        payload = json.dumps([dict(r) for r in rows], ensure_ascii=False)
        return hashlib.sha256(f"{user_id}:{category}:{filters}:{payload}".encode()).hexdigest()
    finally:
        conn.close()
