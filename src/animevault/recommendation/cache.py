"""Atomic local candidate catalogue cache with expiry and stale fallback."""
from __future__ import annotations
import json
import os
import time
from pathlib import Path
from .models import RecommendationCandidate


def default_cache_dir() -> Path:
    root = Path(os.environ.get("APPDATA", Path.home() / ".local")) / "AnimeVault" / "cache" / "recommendation-v2"
    root.mkdir(parents=True, exist_ok=True)
    return root


class CatalogueCache:
    def __init__(self, path: Path | None = None, ttl_seconds: int = 86400):
        self.path = path or default_cache_dir() / "catalogue.json"
        self.ttl_seconds = ttl_seconds

    def read(self, *, allow_stale: bool = True):
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if payload.get("schema") != 1 or not isinstance(payload.get("candidates"), list):
                return [], False
            fresh = time.time() - float(payload.get("cached_at", 0)) < self.ttl_seconds
            if not fresh and not allow_stale:
                return [], False
            candidates = [RecommendationCandidate(**row) for row in payload["candidates"] if isinstance(row, dict)]
            return candidates, not fresh
        except (OSError, ValueError, TypeError):
            return [], False

    def write(self, candidates):
        temp = self.path.with_suffix(".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"schema": 1, "cached_at": time.time(), "candidates": [
                {key: getattr(candidate, key) for key in RecommendationCandidate.__dataclass_fields__ if key != "metadata"}
                for candidate in candidates
            ]}
            temp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            temp.replace(self.path)
        except OSError:
            temp.unlink(missing_ok=True)
