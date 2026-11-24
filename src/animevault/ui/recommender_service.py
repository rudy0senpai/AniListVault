"""Qt-free service around anime_recommender.py: library rows -> ranked picks, with a saved pool and feedback.

Network work never holds the lock, so feedback clicks stay instant while a fetch is running.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

# Locate anime_recommender.py (lives in the repo root or a Downloads subfolder)
_RECOM_RECOMMENDER = Path(__file__).resolve().parent.parent.parent / "anime_recommender.py"
if not _RECOM_RECOMMENDER.exists():
    _downloads = Path.home() / "Downloads" / "files (2)"
    if _downloads.exists():
        _c = _downloads / "anime_recommender.py"
        if _c.exists():
            _RECOM_RECOMMENDER = _c

if str(_RECOM_RECOMMENDER.parent) not in sys.path:
    sys.path.insert(0, str(_RECOM_RECOMMENDER.parent))

try:
    from . import anime_recommender as rec
except ImportError:  # plain script / tests
    import anime_recommender as rec

_STATUS = {"done": "completed", "completed": "completed", "active": "watching", "in progress": "watching",
           "watching": "watching", "planned": "plan to watch", "plan to watch": "plan to watch",
           "hold": "on hold", "on hold": "on hold", "dropped": "dropped"}
_KEEP = ("id", "title", "tags", "studios", "type", "year", "episodes")
_CARD = ("id", "malId", "title", "titleJp", "img", "score", "type", "episodes", "year", "tags", "studios",
         "synopsis", "url", "match", "reasons", "airing", "status")


def row_from_record(r):
    """Default adapter: AnimeVault record (dict or object) -> row for anime_recommender. None = skip.
    The AniList ID matters: it is how the recommender avoids suggesting what you already own."""
    g = r.get if isinstance(r, dict) else (lambda k, d=None: getattr(r, k, d))
    if str(g("media_type") or "anime").lower() != "anime":
        return None
    return {
        "title": g("title"), "mal_id": g("anilist_id"),
        "status": _STATUS.get(str(g("status") or "").lower().replace("_", " "), ""),
        "userRating": rec.TIER.get(str(g("tier") or "").strip().upper()),
        "genres": g("genres") or [], "studios": g("studios") or [], "type": g("format") or g("type") or "",
        "year": g("year"), "episodes": g("episodes") or g("total"), "finishedAt": g("completed_date"),
    }


def _fb(st):
    fb = st.get("feedback") or {}
    for k in ("liked", "disliked", "hidden"):
        fb.setdefault(k, {})
    return fb


class RecService:
    def __init__(self, state_dir, library_provider, row_fn=row_from_record):
        self.state_dir, self.library, self.row_fn = state_dir, library_provider, row_fn
        self._lock = threading.RLock()
        os.makedirs(state_dir, exist_ok=True)
        self._path = os.path.join(state_dir, "state.json")

    # ---- state file ----
    def _load(self):
        try:
            with open(self._path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _save(self, st):
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(st, f)
        os.replace(tmp, self._path)

    # ---- main entry (call from a worker thread) ----
    def run(self, mode="balanced", limit=60, force=False, progress=None):
        rows = [x for x in (self.row_fn(r) for r in self.library()) if x]
        with self._lock:
            st = self._load()
        profile = rec.build_profile(rows, _fb(st))
        sig = rec.fetch_signature(profile)
        fetched = False
        if force or not st.get("pool") or st.get("sig") != sig:
            shuffle = st.get("shuffle", 0) + (1 if force else 0)
            client = rec.AniListClient(cache=rec.Cache(os.path.join(self.state_dir, "cache.json")))
            pool, meta = rec.gather_candidates(profile, client, shuffle=shuffle, on_progress=progress)
            client.cache.flush()
            with self._lock:  # merge into the *latest* file so feedback given meanwhile is kept
                cur = self._load()
                cur.update(pool=pool, sig=sig, meta=meta, shuffle=shuffle)
                self._save(cur)
            fetched = True
        with self._lock:
            st = self._load()
        fb = _fb(st)
        profile = rec.build_profile(rows, fb)  # includes the latest likes/dislikes
        items = rec.rank_candidates(st.get("pool", []), profile, mode, limit, fb)
        return {
            "mode": mode, "fetched": fetched, "updatedAt": datetime.now().isoformat(timespec="seconds"),
            "profile": {"size": profile.size, "rated": profile.rated, "mean": profile.mean,
                        "topTags": [t["name"] for t in profile.top_tags],
                        "avoidTags": [t["name"] for t in profile.avoid_tags]},
            "items": [{k: c.get(k) for k in _CARD} for c in items],
        }

    # ---- feedback (fast, safe on the UI thread) ----
    def feedback(self, action, cid):
        with self._lock:
            st = self._load()
            fb = _fb(st)
            c = next((x for x in st.get("pool", []) if x.get("id") == cid), None)
            if action in ("like", "dislike"):
                if not c:
                    return
                fb["liked" if action == "like" else "disliked"][str(cid)] = {k: c.get(k) for k in _KEEP}
                fb["disliked" if action == "like" else "liked"].pop(str(cid), None)
            elif action == "hide":
                fb["hidden"][str(cid)] = time.time()
            st["feedback"] = fb
            self._save(st)

    def candidate(self, cid):
        with self._lock:
            return next((x for x in self._load().get("pool", []) if x.get("id") == cid), None)

    def reset_feedback(self):
        with self._lock:
            st = self._load()
            st["feedback"] = {"liked": {}, "disliked": {}, "hidden": {}}
            self._save(st)
