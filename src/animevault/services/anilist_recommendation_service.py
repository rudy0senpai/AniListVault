"""AniList-based recommendation discovery service.

Replaces the Jikan-based discovery with AniList's GraphQL API. Uses the
pure-Python anime_recommender.py implementation internally, which is a
throttled, disk-cached GraphQL client with no external dependencies.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from animevault.services.recommendation_discovery import Candidate
from animevault.services.title_norm import normalize_title

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_RECOMMENDER = _REPO_ROOT / "anime_recommender.py"

if not _RECOMMENDER.exists():
    _ENV_RECOMMENDER = __import__("os").environ.get("AV_RECOMMENDER_PATH")
    if _ENV_RECOMMENDER:
        _RECOMMENDER = Path(_ENV_RECOMMENDER)
else:
    for parent in _REPO_ROOT.parents:
        candidate = parent / "anime_recommender.py"
        if candidate.exists():
            _RECOMMENDER = candidate
            break

if not _RECOMMENDER.exists():
    _downloads = Path.home() / "Downloads" / "files (2)"
    if _downloads.exists():
        _candidate = _downloads / "anime_recommender.py"
        if _candidate.exists():
            _RECOMMENDER = _candidate

if str(_RECOMMENDER.parent) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(_RECOMMENDER.parent))

import anime_recommender as _ar  # noqa: E402

# ── Thread safety ────────────────────────────────────────────────────────────

_SERVICE_LOCK = threading.RLock()
_client_cache: dict[bool, object] = {}


def _get_client(online: bool):
    """Thread-safe lazy creation of an AniList client."""
    if online not in _client_cache:
        with _SERVICE_LOCK:
            if online not in _client_cache:
                _client_cache[online] = _ar.AniListClient()
    return _client_cache[online]


# ── Public service API ───────────────────────────────────────────────────────

class AniListRecommendationService:
    """Recommendation discovery backed by AniList's GraphQL API.

    This service replaces JikanRecommendationService. It uses the pure-Python
    anime_recommender.py implementation internally, which connects directly to
    graphql.anilist.co without any third-party API libraries.
    """

    def __init__(self, online_discovery: bool = True) -> None:
        self.online_discovery = online_discovery
        self.errors: list[dict[str, str]] = []
        self.stats: dict[str, object] = {}
        self._client = None

    def reset_diagnostics(self) -> None:
        """Reset internal state (mirrors Jikan service interface)."""
        self.errors = []
        self.stats = {}

    def recommendations_for(self, seed_ids: Iterable[int], per_seed: int = 8, max_seeds: int = 3) -> list[Candidate]:
        """Fetch recommendations for a list of seed ANIList IDs."""
        seeds = list(seed_ids)[:max_seeds]
        if not seeds:
            return []

        candidates = []
        with _SERVICE_LOCK:
            client = _get_client(self.online_discovery)
            if self.online_discovery:
                self._client = client

        for mid in seeds:
            try:
                # fetch related recommendations from AniList
                from anime_recommender import gather_candidates, rank_candidates

                import anime_recommender as ar
                client = _get_client(self.online_discovery)
                if self.online_discovery:
                    self._client = client

                # Get the anime details to build a profile
                anime = client.anime(mid)
                if anime is None:
                    continue

                # Build a temporary profile from this single anime
                # (anime_recommender expects a full library, so we use a
                # minimal profile with the seed's features)
                from anime_recommender import normalize_entry

                seed_entry = normalize_entry({"mal_id": mid, "title": anime.get("title", "")})
                if not seed_entry.get("title"):
                    continue

                # Get candidates via related recommendations
                related = client.recommendations_of(mid)
                for r in related:
                    candidates.append(self._candidate_from_recommendation(r, seed_entry))

                # Also get the anime details for a richer candidate
                anime_details = client.anime(mid)
                if anime_details:
                    candidates.append(self._candidate_from_anime(anime_details, seed_entry))

            except Exception as exc:
                logger.warning("AniList recommendation fetch for %s failed: %s", mid, exc)
                self.errors.append({
                    "source": "anilist_recommendation",
                    "category": "provider_error",
                    "message": str(exc),
                })

        return candidates

    def _candidate_from_recommendation(self, rec: dict, seed_entry: dict) -> Candidate:
        """Convert an anime_recommender recommendation into a Candidate."""
        return Candidate(
            item_id=rec.get("id", 0),
            title=rec.get("title", ""),
            title_en="",
            title_ja="",
            title_romaji="",
            media_type="ANIME",
            aired_from="",
            aired_to="",
            season="",
            season_year=0,
            genres=[],
            studios=[],
            synopsis="",
            poster_url="",
            mal_id=rec.get("id", 0),
            anilist_id=rec.get("id", 0),
            kitsu_id="",
            tmdb_id=0,
            episodes=0,
            discovery_source="anilist_recommendation",
            recommendation_signal=0.0,
            recommendation_reasons=[f"AniList users recommend this alongside {seed_entry.get('title', '')}"],
        )

    def _candidate_from_anime(self, anime: dict, seed_entry: dict) -> Candidate:
        """Convert an anime_recommender anime dict into a Candidate."""
        return Candidate(
            item_id=anime.get("id", 0),
            title=anime.get("title", ""),
            title_en="",
            title_ja="",
            title_romaji=anime.get("titleJp", ""),
            media_type=(anime.get("type", "") or "TV").upper(),
            aired_from="",
            aired_to="",
            season="",
            season_year=anime.get("year", 0),
            genres=anime.get("genres", []),
            studios=anime.get("studios", []),
            synopsis=anime.get("synopsis", ""),
            poster_url=anime.get("img", ""),
            mal_id=anime.get("malId", 0),
            anilist_id=anime.get("id", 0),
            kitsu_id="",
            tmdb_id=0,
            episodes=anime.get("episodes", 0),
            discovery_source="anilist_anime",
            recommendation_signal=0.0,
            recommendation_reasons=["AniList database entry"],
        )

    def genre_candidates(self, genre_names: Iterable[str], max_genres: int = 3,
                         pages_per_genre: int = 2, limit: int = 15) -> list[Candidate]:
        """Fetch candidates by genre from AniList."""
        names = list(genre_names)[:max_genres]
        if not names:
            return []

        candidates = []
        with _SERVICE_LOCK:
            client = _get_client(self.online_discovery)
            if self.online_discovery:
                self._client = client

        for genre in names:
            try:
                # Create a temporary library with one entry tagged with this genre
                # to use the recommender's genre search
                from anime_recommender import normalize_entry

                genre_entries = []
                for i, _ in enumerate(names):
                    entry = {
                        "title": f"Genre: {genre}",
                        "tags": [genre.lower()],
                        "studios": [],
                        "type": "TV",
                        "year": 2024,
                        "episodes": 12,
                        "rating": 7.0,
                        "date": "2020-01-01",
                    }
                    genre_entries.append(entry)

                profile = _ar.build_profile(genre_entries)
                if profile.size == 0:
                    continue

                # Fetch candidates using the genre
                from anime_recommender import gather_candidates

                client = _get_client(self.online_discovery)
                if self.online_discovery:
                    self._client = client

                pool, meta = gather_candidates(profile, client, on_progress=lambda m: None)
                for c in pool:
                    candidates.append(self._candidate_from_anime(c, genre_entries[0]))

            except Exception as exc:
                logger.warning("AniList genre candidate fetch for %s failed: %s", genre, exc)
                self.errors.append({
                    "source": "anilist_genre",
                    "category": "provider_error",
                    "message": str(exc),
                })

        return candidates[:limit]
