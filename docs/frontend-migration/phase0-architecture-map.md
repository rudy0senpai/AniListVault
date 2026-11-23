# Phase 0 — Architecture Audit & Migration Plan

**Project:** AniListVault (renamed AnimeVault) — PySide6/Qt5 desktop app + SQLite.
**Target:** React + Electron + FastAPI, with the Python backend preserved.
**Status:** Phase 0 complete (audit + migration plan). No frontend files changed.

---

## 1. Application entry point & startup workflow

- **Entry:** `src/animevault/__main__.py` → `cli:main()`.
- **Startup sequence** (`cli.py:main`):
  1. `initialize_database()` — creates/upgrades the SQLite DB at
     `$APPDATA\AnimeVault\animevault.db` (or `$XDG_DATA_HOME/animevault/animevault.db` on
     Linux). Creates `anime`, `anime_metadata`, `meta`, `literature`, `literature_metadata`
     (schema version 3).
  2. `run_migrations()` — applies v2 (tier system) and v3 (literature tables); additive
     only, no data destroyed.
  3. `create_app()` → `MainWindow()` → `app.exec()` (PySide6 event loop).
- **Entry points** (pyproject.toml): `[project.scripts] animevault` and `[project.gui-scripts]
  animevault-gui` → `animevault.cli:main`.
- **Window lifecycle:** `closeEvent` shuts the background video worker; `ThemeManager` (QSettings
  singleton) drives theme/effects/glass changes and triggers `refresh()` rebroadcasts.

## 2. PySide6 application structure (UI components & responsibilities)

| File | Responsibility |
|---|---|
| `ui/main_window.py` | Top-level shell: header, 4-category nav tabs (Anime/Manga/Manhwa/Manhua), toolbar, search row, `QStackedWidget` (Library ↔ Dashboard), delete/edit/import/export/backup/settings/recommendation wiring. |
| `ui/overview_panel.py` | KPI cards, media-category donut/bar, anime-status bars, top-genres, tier distribution — analytics sidebar. |
| `ui/card_factory.py` + `ui/media_card.py` + `ui/card_grid.py` | `MediaCard` widget builder for Anime & Literature; paginated grid host. |
| `ui/theme.py` | **Legacy theme system** — 21 `ThemeDefinition` rows, `ThemeManager` QObject, `build_stylesheet()`, tier/status badge helpers. **WIP #7.** |
| `ui/theme_dialog.py` | Theme picker/settings dialog. **WIP #7.** |
| `ui/recommendation_panel.py` + `ui/recommendation_card.py` | Existing recommendation panel/card. **Redesign target #6.** |
| `ui/recommendation_dialog.py` | Recommendation modal (empty-state messages, `_RecommendationLoader` QThread, `_on_loaded` outcome-branching). **WIP #6.** |
| `ui/add_media_dialog.py`, `ui/details_dialog.py`, `ui/import_dialogs.py`, `ui/account_dialog.py`, `ui/dashboard_panel.py`, `ui/video_background.py`, `ui/thumb_cache.py` | Add/edit, details, importers, account, dashboard, background video, poster cache. |
| `ui/media_types.py` | `MEDIA_ANIME/MANGA/MANHWA/MANHUA`, `CATEGORY_LABELS`, `type_options`. |
| `ui/tiers.py` | Tier enum/rank ordering used by filters & sorting. |

State flow: `MainWindow` owns `_category`, `_search_text`, `_filter_*`, `_sort_mode`, `_select_mode`;
`library_changed` signal triggers `refresh()`, which calls ` Anime.all()`/`Literature.all()` and
rebuilds cards + overview + dashboard.

## 3. Python services & business logic (to be preserved behind FastAPI)

| Module | Responsibility |
|---|---|
| `services/anime_similarity.py` | Similarity scoring scaffolding (currently placeholder). |
| `services/anime_similarity.py` | (see above) |
| `services/bulk_import_worker.py` | Import workers (SQLite bulk import). |
| `services/cache.py` | Recommendation result cache (`recommendation_cache`). |
| `services/diagnostics.py` | Enrichment diagnostics. |
| `services/enrichment.py` | (import tree). |
| `services/import_tree.py` | Bulk import tree + checkpointing. |
| `services/recommendation_cache.py` | Recommendation cache. |
| `services/recommendation_discovery.py` | **External candidate discovery**: `discover_candidates()` + `_candidate_key()` dedup; iterates providers (`anilist`, `kitsu`, `tmdb`, `jikan` default); returns `Candidate` list. |
| `services/recommendation_engine.py` | **Recommendation engine**: owned-item exclusion (provider-id + normalized-title fallback), `_determine_outcome()` + `get_preference_summary()` (produce `recommendation_status`), `_build_candidates()`, `_score_and_rank()`, `_dedup_key()`. |
| `services/recommendation_scorer.py` + `services/recommendation_set.py` | Scoring/ranking: `RecommendationScorer`, `RecommendationResult`, `RecommendationSet`. |
| `services/search.py` + `services/anime_similarity.py` | `SearchService`, `calculate_match_score`. |
| `services/workers.py` | Background workers (`BulkEnrichmentWorker`, `SearchWorker`, poster worker) with Qt signals. |
| `services/poster.py` + `services/thumb_cache.py` | Poster download + local cache. |
| `services/providers/base.py`, `anilist.py`, `jikan.py`, `kitsu.py`, `tmdb.py` | External providers: `BaseProvider` ABC, `AnimeMetadata` dataclass, `ProviderError`, `parse_retry_after`. |
| `services/cache.py` + `services/recommendation_cache.py` | Result cache. |
| `services/user_preference_analyzer.py`, `services/anime_similarity.py` | Preference analysis. |

## 4. SQLite database models, migrations & data location

- **Path:** `%APPDATA%\AnimeVault\animevault.db` (Linux: `$XDG_DATA_HOME/animevault/animevault.db`).
- **Schema (version 3 = current target):**
  - `anime` (id PK, title, title_ja, episodes, status, score, notes, tier, rewatches, episodes_watched, favorite, first_watched, last_watched, completed_date, privacy)
  - `anime_metadata` (anime_id, title_en, synopsis, media_type, airing_status, genres, studios, aired_from/to, season, season_year, duration, poster_url, poster_path, mal_id, anilist_id, kitsu_id, tmdb_id, anidb_id, source_provider, metadata_fetched_at) — FK→anime, poster_path is the cached cover file.
  - `meta` (key, value) — holds `schema_version` (base 1, current 3).
  - `literature` + `literature_metadata` (v3 only; Manga/Manhwa/Manhua).
- **Migrations** (additive, `run_migrations()` idempotent): v2 = tier system columns; v3 = literature tables. `backup_database()` makes a timestamped SQLite online backup.
- **Library records & user settings must be preserved** — never drop columns/tables or rewrite rows.

## 5. Existing API integrations & metadata providers

| Provider | Protocol | Discovery class |
|---|---|---|
| Anilist | GraphQL (`https://graphql.anilist.co`) | `AniListProvider` — `_SEARCH_QUERY`, `search()`, `get_details()` |
| Jikan | REST v4 (`https://api.jikan.moe/v4`) | `JikanProvider` — `search()`, `get_details()` |
| Kitsu | REST | `KitsuProvider` |
| TMDB | REST | `TmdbProvider` |

All implement `BaseProvider.search(query, limit)`, `get_details(provider_id)`, `is_available()`;
`normalize_*` functions convert raw responses to `AnimeMetadata`. Errors are classified
(`ProviderError` with `retryable`, `status_code`, `retry_after`). This is the external-discovery
layer the new design will reuse via a thin FastAPI wrapper.

## 6. Recommendation engine & modal

- **`RecommendationEngine`** (in `rec_engine_service` / `services/recommendation_engine.py`):
  - owned-item exclusion (provider IDs preferred, normalized title fallback),
  - `_determine_outcome()` → `get_preference_summary()["recommendation_status"]` —
    `insufficient_preference_data | no_external_candidates | provider_failure |
    all_excluded_owned | all_excluded_filter | valid_recommendations`.
  - `_build_candidates(owned_ids, owned_titles)`; `_score_and_rank()`; `_dedup_key()`.
- **Recommendation dialog**:
  - MotD UI panel (`recommendation_panel.py`, `recommendation_card.py`) — list view with
    details/precs/add-to-library/dismiss/refresh.
  - `recommendation_dialog.py` — modal with outcome-specific empty-state messages driven by
    `recommendation_status`.
  - `recommendation_cache.py` — recommendation results cache.

## 7. Poster downloading & caching

- `services/poster.py` downloads cover → `poster_path` (cached locally).
- `services/thumb_cache.py` (thumbnail cache).
- `workers.py` fires `poster_ready` signals as covers land (non-blocking UI).
- `anime_metadata.poster_path` points at the cached cover file; `delete()` cleans it up.

## 8. Settings & configuration persistence

- `ui/theme.py::ThemeManager` — QSettings singleton ("AnimeVault"/"AnimeVault"):
  `theme_id`, `appearance/liquid_glass`, `appearance/reduce_effects`, `ui/overview_visible`.
- Recommendation profile keyed by `user_hash`; `recommendation_cache.py` (file cache on disk).
- `database.py` (DB path), `services/cache.py`.

## 9. Existing tests

`tests/` contains 380 passing tests (including `test_recommendation_dialog.py`,
`test_recommendation_eligibility.py`, `test_recommendation_pipeline.py`, `test_providers.py`,
`test_ui_flow.py`, etc.). All must stay passing; new frontend/backend tests are additive.

## 10. Recommendation discovery — current state (what to reuse)

`recommendation_discovery.discover_candidates(query, categories, limit, providers)` already
implements provider iteration, per-provider exception isolation, categorization, and
`_candidate_key()` dedup (provider ID preferred → normalized title + media type). `get_recommendations()`
triggers it only when `profile.has_preferences()`. The engine's owned exclusion is applied inside
`_build_candidates()`; the final safety-net is `_is_owned_result()`. The recommendation UI (panel +
dialog) must be adapted (new design) without changing engine semantics.

---

# Migration Plan (Phase 0b)

## Compatibility risks

| Risk | Impact | Mitigations |
|---|---|---|
| Old SQLite DB must not be touched/duplicated. | High | New app reads the *same* DB file via FastAPI (SQLAlchemy + sqlite3); migrations run only once at first launch. |
| Theme tokens (theme.py) drive 70k+ lines of QSS across 25 legacy themes + `liquid_glass` flags. | High | Replace entire theme system with a design-token set; keep the `ThemeManager` *interface* (name/signal/event) but route it to the new JS layer, or migrate settings on migration. |
| Video background (`ui/video_background.py`) must be removed per spec. | Medium | Delete the widget + its geometry logic; no fallbacks. |
| Recommendation engine is Anime-only. | Medium | Do not advertise literature recommendations until `recommendation_engine` is genuinely extended/tested; surface "no literature recommendations" empty state. |
| Existing PySide6 QSS (theme.py) must be removed. | High | Rewrite QSS in CSS-in-JS/Electron `index.css`; the new `.liquid-glass` classes are CSS, not QSS. |
| Poster path / cache: legacy files remain on disk. | Low | Reuse `poster_path`/`thumb_cache` via API; optionally hardlink new covers to the same files. |

## Migration phases (approved order)

- **Phase 0 — (this document).**
- **Phase 1 — Foundation:** scaffold React + Electron + FastAPI; confirm the existing Python
  backend + SQLite still run unchanged; add a thin `backend/services/recommendation.py`
  FastAPI layer over the existing engine/discovery.
- **Phase 2 — Design system:** CSS custom-properties design tokens; `GlassSurface`; embossed
  controls; remove `ui/theme.py` style tokens & `ui/video_background.py`; wire new tokens to
  renderer theme settings.
- **Phase 3 — Application shell:** top nav + global search + dialogs/notifications.
- **Phase 4 — Library/media:** 4 library views, add/edit workflows, preserve filtering/sorting/
  selection/edit/delete.
- **Phase 5 — Dashboard/Overview:** stats + charts + activity + progress + recommendations.
- **Phase 6 — Recommendations:** redesign panel, integrate `recommendation_discovery` via API,
  preserve owned-exclusion & empty states; document engine is Anime-only.
- **Phase 7 — Settings:** general/appearance/library/providers/recommendations/storage/about.
- **Phase 8 — Integration & verification:** end-to-end, DB compatibility, restart, regression suite.

## Deliverables for Phase 0

1. This document (`phase0-architecture-map.md`).
2. A short migration-risk memo (below).
3. No frontend files changed in this working session.

## Migration-risk memo

- **Keep:** SQLite DB (same file path), `models/anime.py` + `models/literature.py`, all
  `services/` business logic, poster cache files, user settings (*stored via QSettings* — migration
  will copy relevant keys to the new electron-store-backed store if needed), existing tests.
- **Replace:** PySide6 UI layer (React/Electron), legacy theme system, video background, old
  recommendation dialog/card, old card/grid widgets.
- **Wires:** FastAPI → `services/recommendation_engine.py` (engine + discovery) → SQLite. New
  Electron `main` process will act as the preload bridge and HTTP server.
- **Verification:** full pytest suite must remain green; read-only DB queries during UI dev;
  new tests for the API layer and React components.
