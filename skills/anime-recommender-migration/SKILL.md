---
name: anime-recommender-migration
description: Replace legacy recommendation subsystem
homepage: https://github.com/rudy0senpai/AniListVault
icon: dashboard
tags:
  - animevault
  - recommendation
  - anime_recommender
  - migration
---

# AnimeVault Recommendation System Migration

Replace the legacy recommendation subsystem with the new `anime_recommender.py`.

## Architecture

- **Legacy** (`src/animevault/services/recommendation_engine.py` etc.): ~3,450 lines across 10+ modules, complex PySide6-based.
- **New** (`anime_recommender.py`): ~200 lines, pure Python stdlib, CLI + library API.

## Workflow

1. Create `src/animevault/services/anime_recommender_service.py` that wraps `anime_recommender.py`.
2. Locate the recommender (repo root or Downloads folder).
3. Add the recommender's directory to `sys.path` so it can be imported.
4. Update all UI consumers to use the new service.
5. Remove or deprecate old modules.

## New Service API

- `AnimeRecommenderService(library_items=..., online_discovery=True, mode="balanced", limit=24)`
- `get_recommendations(category="all", n=60, genre_filter="", media_type_filter="all", min_score=0.0) -> list[RecommendationResult]`
- `get_preference_summary() -> dict`
- `reset() -> None`

## Result Model

- `RecommendationResult` (compatible with legacy UI contract): `item_id`, `title`, `media_type`, `category`, `genres`, `synopsis`, `score`, `reasons`, `poster_url`, `discovery_source`, etc.
