"""Separate, local feedback store; never updates Anime/Literature rows."""
from __future__ import annotations
import json
import threading
import time
from pathlib import Path
from .cache import default_cache_dir

_ALLOWED = {"like", "dislike", "not_interested", "watched_elsewhere", "plan_to_watch", "add_to_library", "dismiss"}
_LOCK = threading.Lock()


class FeedbackStore:
    def __init__(self, path: Path | None = None):
        self.path = path or default_cache_dir() / "feedback.json"

    def read(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, ValueError):
            return []

    def record(self, action: str, *, candidate_key: str, title: str = ""):
        if action not in _ALLOWED:
            raise ValueError(f"Unsupported feedback action: {action}")
        if not candidate_key.strip():
            raise ValueError("candidate_key is required")
        with _LOCK:
            rows = self.read()
            rows.append({"action": action, "candidate_key": candidate_key,
                         "title": title, "created_at": time.time()})
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)
        return rows[-1]

    def preference_adjustments(self):
        """Bound feedback strength so one event cannot dominate the profile."""
        out = {}
        for row in self.read():
            key = row.get("candidate_key")
            if key:
                delta = {"like": .25, "dislike": -.25, "not_interested": -.35,
                         "watched_elsewhere": .1, "plan_to_watch": .1,
                         "add_to_library": .1, "dismiss": -.15}.get(row.get("action"), 0)
                out[key] = max(-.5, min(.5, out.get(key, 0.0) + delta))
        return out
