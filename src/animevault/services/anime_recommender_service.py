"""Integration service: wraps the new anime_recommender.py for the GUI.

Replaces the legacy recommendation subsystem (RecommendationEngine,
recommendation_scorer, recommendation_discovery, etc.) with the pure-Python
anime_recommender.py implementation.

The new recommender is a standalone CLI tool; this service exposes the same
functionality through a PySide6-friendly API that the existing panels can call
without modification to their UI code.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from animevault.models.anime import Anime
from animevault.models.literature import Literature
from animevault.services.title_norm import normalize_title

logger = logging.getLogger(__name__)

# ── Locating the recommender ────────────────────────────────────────────────────
# The recommender lives at the repo root (sibling of src/) or in the
# Downloads folder (per the user's attachment).
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_RECOMMENDER = _REPO_ROOT / "anime_recommender.py"

if not _RECOMMENDER.exists():
    _ENV_RECOMMENDER = os.environ.get("AV_RECOMMENDER_PATH")
    if _ENV_RECOMMENDER:
        _RECOMMENDER = Path(_ENV_RECOMMENDER)
    else:
        for parent in _REPO_ROOT.parents:
            candidate = parent / "anime_recommender.py"
            if candidate.exists():
                _RECOMMENDER = candidate
                break

# Fallback: look in the Downloads folder
if not _RECOMMENDER.exists():
    _downloads = Path.home() / "Downloads" / "files (2)"
    if _downloads.exists():
        candidate = _downloads / "anime_recommender.py"
        if candidate.exists():
            _RECOMMENDER = candidate

logger.info("Recommendation service using recommender at %s", _RECOMMENDER)

# Ensure the recommender's directory is on sys.path so anime_recommender.py
# can be imported (it may live in the repo root or in a Downloads subfolder).
_rec_dir = _RECOMMENDER.parent
if str(_rec_dir) not in sys.path:
    sys.path.insert(0, str(_rec_dir))


# ── Public result model (compatible with the legacy UI contract) ────────────────

class RecommendationResult:
    """A single recommendation with all fields the UI expects."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.item_id: int = data.get("id", 0)
        self.title: str = data.get("title", "")
        self.media_type: str = data.get("type", "")
        self.category: str = "general"
        self.genres: list[str] = data.get("genres", [])
        self.synopsis: str = data.get("synopsis", "")
        self.score: float = data.get("score", 0.0)
        self.reasons: list[str] = data.get("reasons", [])
        self.poster_url: str = data.get("img", "")
        self.progress: str = ""
        self.progress_percent: int = 0
        self.tier: Optional[str] = None
        self.is_plan_to_watch: bool = False
        self.is_new_discovery: bool = False
        self.is_similar: bool = False
        self.discovery_source: str = "anime_recommender"
        self.title_ja: str = data.get("titleJp", "")
        self.episodes: int = data.get("episodes", 0)
        self.provider_key: str = "anilist"
        self.provider_id: str = str(self.item_id)
        self.is_cached: bool = False
        self.score_breakdown: dict[str, float] = data.get("score_breakdown", {})

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> "RecommendationResult":
        return cls(cls._coerce(data))

    @staticmethod
    def _coerce(d: dict[str, Any]) -> dict[str, Any]:
        out = dict(d)
        if "reasons" in out and not isinstance(out["reasons"], list):
            out["reasons"] = [str(out["reasons"])] if out["reasons"] else []
        if "genres" in out and not isinstance(out["genres"], list):
            out["genres"] = [str(out["genres"])]
        return out


class RecommendationSet:
    """A full recommendation set for the UI."""

    def __init__(self, results: list[RecommendationResult],
                 preferred_categories: list[tuple[str, float]] | None = None,
                 watch_engagement: float = 0.0,
                 profile_doc: list[str] | None = None) -> None:
        self.category: str = "all"
        self.results: list[RecommendationResult] = results
        self.preferred_categories: list[tuple[str, float]] = preferred_categories or []
        self.watch_engagement: float = watch_engagement
        self.profile_doc: list[str] = profile_doc or []


# ── Core API ────────────────────────────────────────────────────────────────────

class AnimeRecommenderService:
    """Facade around the new anime_recommender.py."""

    def __init__(self, library_items: list | None = None,
                 *, online_discovery: bool = True,
                 mode: str = "balanced",
                 limit: int = 24,
                 embed_posters: bool = False,
                 feature_cache_dir: str | None = None) -> None:
        self.library_items = list(library_items or [])
        self.online_discovery = online_discovery
        self.mode = mode
        self.limit = limit
        self.embed_posters = embed_posters
        self.feature_cache_dir = feature_cache_dir
        self._profile = None
        self._pool = []
        self._ranked = []
        self._errors: list[dict[str, str]] = []
        self._stats: dict[str, Any] = {}

    @property
    def profile(self):
        if self._profile is None:
            self._profile = self._build_profile()
        return self._profile

    def _build_profile(self):
        """Build a taste profile from the library using the new recommender."""
        try:
            from anime_recommender import build_profile, normalize_entry, load_csv
            # Convert library items to CSV rows compatible with normalize_entry
            rows = []
            for item in self.library_items:
                if hasattr(item, "get"):
                    rows.append(dict(item))
                elif isinstance(item, (dict,)):
                    rows.append(item)
                else:
                    # Assume SQLAlchemy model instance with __dict__
                    rows.append(dict(item.__dict__))
            if not rows:
                return None
            return build_profile(rows)
        except Exception as exc:
            logger.exception("Build profile failed: %s", exc)
            self._errors.append({"source": "profile", "message": str(exc)})
            return None

    def get_recommendations(self,
                            category: str = "all",
                            n: int = 60,
                            genre_filter: str = "",
                            media_type_filter: str = "all",
                            min_score: float = 0.0) -> list[RecommendationResult]:
        """Return a ranked list of recommendations for the current library."""
        self._errors = []
        self._stats = {}

        # 1. Build profile from library
        profile = self.profile
        if profile is None or profile.size == 0:
            return []

        # 2. Gather candidates (offline rank from local library first,
        #    online discovery only if enabled and candidates exist)
        from anime_recommender import (build_profile, gather_candidates,
                                       rank_candidates)

        # Build library rows for the recommender
        library_rows = self._library_rows()
        if not library_rows:
            return []

        fb = self._build_feedback()
        profile = build_profile(library_rows, fb)

        # Fetch candidates
        client = None
        pool = []
        if self.online_discovery:
            try:
                from anime_recommender import AniListClient
                client = AniListClient()
                pool, meta = gather_candidates(profile, client, on_progress=lambda m: logger.debug("  %s", m))
                self._stats.update(meta)
            except Exception as exc:
                logger.exception("Candidate gathering failed: %s", exc)
                self._errors.append({"source": "discovery", "message": str(exc)})
                pool = []

        # Combine local library items with fetched candidates
        # NOTE: library entries are NOT ranked as candidates - they are
        # already in the user's library. Only fetched candidates are ranked.
        # If no candidates were fetched (offline mode), the library entries
        # are returned as "library-based" recommendations.
        all_candidates = pool

        # Rank
        def _ensure_id(c):
            if "id" not in c:
                c = dict(c)
                c["id"] = c.get("malId") or c.get("anilist_id") or c.get("id") or 0
            return c

        all_candidates = [_ensure_id(c) for c in all_candidates]

        self._ranked = []
        self._stats = {"requests": 0, "queries": [], "seeds": []}

        if not all_candidates:
            # Offline mode - recommend from library entries
            # Add synthetic IDs to library entries
            ranked = []
            synthetic_id = 100000
            for c in library_rows:
                row = dict(c)
                synthetic_id += 1
                row["id"] = row.get("malId") or row.get("anilist_id") or row.get("id") or synthetic_id
                row["score_"] = 0.0
                row["reasons"] = ["From your library"]
                ranked.append(row)
            self._ranked = ranked
            self._stats = {"requests": 0, "queries": [], "seeds": []}
            results = [RecommendationResult.from_raw(r) for r in ranked]
            return results

        try:
            ranked = rank_candidates(all_candidates, profile, mode=self.mode, limit=self.limit,
                                     feedback=fb, allow_sequels=False)
        except Exception as exc:
            logger.exception("Ranking failed: %s", exc)
            self._errors.append({"source": "ranking", "message": str(exc)})
            ranked = []

        self._ranked = ranked
        self._stats = {"requests": 0, "queries": [], "seeds": []}

        # Convert to UI format
        results = [RecommendationResult.from_raw(r) for r in ranked]
        return results

    def _library_rows(self) -> list[dict]:
        """Convert database library items to row dicts for the recommender."""
        rows = []
        for item in self.library_items:
            if isinstance(item, dict):
                row = dict(item)
            else:
                row = {}
                for k, v in item.__dict__.items():
                    if not k.startswith("_"):
                        row[k] = v
            if row.get("title"):
                rows.append(row)
        return rows

    def _build_feedback(self) -> dict:
        """Build a feedback dict from the UI's feedback store if present."""
        try:
            from animevault.services.recommendation_cache import RecommendationCache
            cache = RecommendationCache()
            fb = {"liked": {}, "disliked": {}, "hidden": {}}
            # Feedback is stored in the legacy cache; read it if available
            for key in ("liked", "disliked", "hidden"):
                if hasattr(cache, key):
                    val = getattr(cache, key)
                    if val:
                        fb[key] = {str(k): v for k, v in val.items()}
            return fb
        except Exception:
            return {"liked": {}, "disliked": {}, "hidden": {}}

    def get_preference_summary(self) -> dict[str, Any]:
        """Return a summary of the user's taste profile."""
        profile = self.profile
        if profile is None:
            return {"has_preferences": False}
        top_genres = [(t.get("name", t), t.get("affinity", 0)) for t in profile.top_tags[:5]]
        return {
            "has_preferences": profile.size > 0,
            "size": profile.size,
            "rated": profile.rated,
            "mean": profile.mean,
            "top_genres": top_genres,
            "top_tags": [t.get("name", t) for t in profile.top_tags[:5]],
            "top_studios": [s.get("name", s) for s in profile.top_studios[:5]],
        }

    def reset(self) -> None:
        """Clear cached recommendation state."""
        self._profile = None
        self._pool = []
        self._ranked = []
        self._errors = []
        self._stats = {}
