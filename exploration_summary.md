# AnimeVault Codebase Exploration Summary

## 1. DATABASE / MODELS STRUCTURE

### Anime Table
- `id` INTEGER PRIMARY KEY AUTOINCREMENT
- `title` TEXT NOT NULL
- `title_ja` TEXT (nullable)
- `episodes` INTEGER DEFAULT 0
- `status` TEXT NOT NULL DEFAULT 'plan_to_watch'
- `score` REAL (legacy numeric rating, retained for backward compat)
- `notes` TEXT DEFAULT ''
- **V2 added columns**: `tier`, `rewatches`, `episodes_watched`, `favorite`, `first_watched`, `last_watched`, `completed_date`, `privacy`
- **V3**: `anidb_id` added to anime_metadata

### Anime_Metadata Table
- `anime_id` INTEGER PRIMARY KEY (FK → anime.id ON DELETE CASCADE)
- `title_en`, `synopsis`, `media_type`, `airing_status`
- `genres` TEXT (JSON), `studios` TEXT (JSON)
- `aired_from`, `aired_to`, `season`, `season_year` (INTEGER)
- `duration` INTEGER DEFAULT 0
- `poster_url`, `poster_path`
- `mal_id`, `anilist_id`, `kitsu_id`, `tmdb_id`, `anidb_id`
- `source_provider`, `metadata_fetched_at`

### Literature Table (manga / manhwa / manhua)
- `id` INTEGER PRIMARY KEY AUTOINCREMENT
- `category` TEXT NOT NULL DEFAULT 'manga' ← distinguishes anime vs literature
- `title` TEXT NOT NULL
- `title_native` TEXT DEFAULT ''
- `synonyms` TEXT (JSON)
- `format` TEXT
- `status` TEXT NOT NULL DEFAULT 'watching'
- `tier` TEXT (personal ranking, same tier system as anime)
- `rewatches` INTEGER DEFAULT 0
- `chapters_read` INTEGER DEFAULT 0
- `chapters` INTEGER DEFAULT 0
- `volumes` INTEGER DEFAULT 0
- `volumes_read` INTEGER DEFAULT 0
- `favorite` INTEGER DEFAULT 0
- `notes` TEXT DEFAULT ''
- `first_read`, `last_read`, `completed_date` TEXT DEFAULT ''
- `privacy` TEXT DEFAULT 'public'
- `origin_country` TEXT DEFAULT '' ← JP→manga, KR→manhwa, CN/TW/HK→manhua

### Literature_Metadata Table
- `literature_id` INTEGER PRIMARY KEY (FK → literature.id ON DELETE CASCADE)
- `title_en`, `synopsis`, `genres` (JSON), `authors` (JSON), `artists` (JSON)
- `serialization`, `pub_status`, `started_at`, `ended_at`
- `cover_url`, `cover_path`
- `anilist_id`, `kitsu_id`, `mal_id`, `source_provider`, `metadata_fetched_at`

### Meta Table
- `key` TEXT PRIMARY KEY, `value` TEXT
- Stores `schema_version` (currently 3)

### Category Distinction
- **Anime**: stored in `anime`/`anime_metadata` tables, `media_type` from AniList
- **Manga/Manhwa/Manhua**: stored in `literature`/`literature_metadata` tables, distinguished by `category` field (`manga`, `manhwa`, `manhua`) and `origin_country` mapping
- `media_types.py` defines: `MEDIA_ANIME="anime"`, `MEDIA_MANGA="manga"`, `MEDIA_MANHWA="manhwa"`, `MEDIA_MANHUA="manhua"`
- `is_literature(category)` returns True for manga/manhwa/manhua
- `category_from_origin()` maps country codes: JP→manga, KR→manhwa, CN/TW/HK→manhua

## 2. TIER SYSTEM (tiers.py)

### Canonical Tiers (best → worst)
```
SSS > SS > S > A > B > C > D > E > F
```

### Constants
- `TIER_SSS = "SSS"`, `TIER_SS = "SS"`, `TIER_S = "S"`, `TIER_A = "A"`, etc.
- `TIERS = (TIER_SSS, TIER_SS, TIER_S, TIER_A, TIER_B, TIER_C, TIER_D, TIER_E, TIER_F)`

### Functions
- `normalize_tier(value)` → canonical tier or None (handles case/whitespace)
- `is_valid_tier(value)` → True if canonical (not None)
- `tier_sort_key(tier)` → sort key: SSS→(0,""), F→(8,""), None→(99,"")
- `tier_display(tier)` → tier label or "—" when unassigned
- `DEFAULT_SCORE_TO_TIER` mapping boundaries (9.0-10.0→SSS, etc.)
- `score_to_tier(score, mapping)` → explicit conversion (opt-in only)

### Migration
- Score→tier conversion is **never automatic**; requires explicit call to `migrate_scores_to_tiers()`
- Migrations tracked in `meta` table, version 1→2→3
- v1→v2: adds tier/rewatches/etc columns to anime table
- v2→v3: creates literature/literature_metadata tables (adds first-class manga support)

## 3. CARD_FACTORY.PY

### Key Functions
- `anime_card(anime)` → MediaCard widget for Anime
  - Shows episode count/progress, media type badge, status, tier badge, poster
- `literature_card(item)` → MediaCard widget for Literature
  - Shows chapter count/progress (with proper unit), format/category badge, status via `status_label()`, tier badge, poster (cover_path)
- `build_card(item, kind)` → dispatches to right adapter; falls back to literature_card

### Type Labels
- `type_label(raw)` → pretty-prints format (TV→TV, MOVIE→Movie, MANGA→Manga, etc.)

### MediaCard (media_card.py)
- QFrame with poster on LEFT, details on RIGHT
- Layout: title row · type + count meta · progress text + QProgressBar · status + tier badges
- Signals: details_requested, edit_requested, refresh_requested, deleted, selection_changed
- Supports select mode for multi-selection

### Anime Card (anime_card.py)
- Separate QFrame widget with compact UI
- Shows poster, title, status badge, Japanese title/episodes/genres, score, synopsis/notes

## 4. MODEL DEFINITIONS

### Anime (animevault/models/anime.py)
Dataclass attributes:
- **Identity**: `id` (Optional[int])
- **Personal**: `title`, `title_ja`, `episodes`, `status` (from VALID_STATUSES), `score` (Optional[float], legacy), `tier` (Optional[str], personal ranking), `notes`, `rewatches`, `episodes_watched`, `favorite`, `first_watched`, `last_watched`, `completed_date`, `privacy` ("public")
- **Metadata**: `title_en`, `synopsis`, `media_type`, `airing_status`, `genres` (list[str]), `studios` (list[str]), `aired_from`, `aired_to`, `season`, `season_year` (Optional[int]), `duration`, `poster_url`, `poster_path`, `mal_id`, `anilist_id`, `kitsu_id`, `tmdb_id`, `anidb_id`, `source_provider`, `metadata_fetched_at`
- **Validation** in `__post_init__`: title non-empty, episodes ≥ 0, status ∈ VALID_STATUSES, score 0.0-10.0, tier normalized, rewatches/episodes_watched ≥ 0
- **Methods**: `save()`, `create()`, `from_row()`, `all()`, `filtered()`, `find_by_id()`, `find_by_title()`, `find_by_provider_id()`, `delete()`

### Literature (animevault/models/literature.py)
Dataclass attributes:
- **Identity**: `id` (Optional[int])
- **Personal**: `title`, `category` (defaults to MEDIA_MANGA), `status` (from VALID_STATUSES), `tier` (Optional[str]), `rewatches`, `chapters_read`, `chapters`, `volumes`, `volumes_read`, `favorite`, `notes`, `first_read`, `last_read`, `completed_date`, `privacy`
- **Bibliographic**: `title_native`, `format`, `origin_country`, `chapters`, `volumes`, `volumes_read`
- **Metadata**: `title_en`, `synonyms` (list[str]), `synopsis`, `genres` (list[str]), `authors` (list[str]), `artists` (list[str]), `serialization`, `pub_status`, `started_at`, `ended_at`, `cover_url`, `cover_path`, `anilist_id`, `kitsu_id`, `mal_id`, `source_provider`, `metadata_fetched_at`
- **Validation** in `__post_init__`: category normalized via `normalize_category()`, status validated, tier normalized, non-negative checks on rewatches/chapters/volumes
- **Methods**: `status_label()`, `progress()`, `progress_percent`, `poster_path`, `poster_url`, `save()`, `create()`, `from_row()`, `all()`, `by_category()`, `find_by_id()`, `find_by_title()`, `find_by_provider_id()`, `filtered()`, `delete()`

### Key Differences
- Anime: episodes-based progress, stored in anime table
- Literature: chapters-based progress, stored in literature table (separate table so anime rows untouched)
- Literature has `category` field to distinguish manga/manhwa/manhua
- Literature has `origin_country` for origin detection

## 5. RECOMMENDATION ENGINE

### RecommendationEngine (recommendation_engine.py)
Orchestrates pipeline:
1. **Preference analysis** (`user_preference_analyzer`) → builds weighted user profile
2. **Similarity calculation** (`anime_similarity`) → computes candidate proximity
3. **Weighted ranking** (`recommendation_scorer`) → scores and ranks candidates
4. **External discovery** (`recommendation_discovery`) → fetches new candidates from providers (optional)
5. **Caching/dismissed handling** (`recommendation_cache`) → keeps results local, remembers dismissed

### RecommendationResult (dataclass)
- `item_id`, `title`, `media_type`, `category`, `genres`, `synopsis`, `score` (float)
- `reasons` (list[str]), `poster_url`, `progress`, `progress_percent`
- `tier`, `is_plan_to_watch`, `is_new_discovery`, `is_similar`, `discovery_source`

### RecommendationSet (dataclass)
- `category`, `results` (list[RecommendationResult])
- `preferred_categories`, `watch_engagement`, `profile_doc`

### RecommendationScorer (recommendation_scorer.py)
6 weighted components (total 100%):
| Component | Weight |
|---|---|
| Genre and theme similarity | 25% |
| Similarity to highly rated | 25% |
| Tier placement | 15% |
| Favorite status | 15% |
| Watch engagement and completion | 10% |
| Similarity to preferred studios/metadata | 10% |

### Scoring Helpers
- `_tier_weight(item)`: SSS→1.0, SS→0.89, S→0.75, A→0.63, B→0.5, C→0.38, D→0.25, E→0.13, F→0.0, None→0.0
- `_watch_engagement(item)`: normalized 0..1 based on episodes watched and status weights
- `_genre_theme_similarity()`: weighted genre overlap with user profile
- `_metadata_similarity()`: compares genres, studios, authors, artists between items

### Functional API
- `get_recommendations(library_items, user_hash, category, n, genre_filter, media_type_filter, online_discovery, min_score)` → list[RecommendationResult]

## 6. CONFTST.PY TEST FIXTURES

### isolated_database (autouse, per-test)
- Creates fresh temp DB file (`tmp_path / "test_animevault.db"`)
- Disconnects cached thread-local connection
- Calls `set_database_path(db_file)` and `initialize_database(db_file)`
- Runs `run_migrations()` to bring schema to version 3
- Yields db_file; cleans up connection after test
- Ensures tests never touch real user database

### reset_theme_manager (autouse)
- Resets ThemeManager singleton state
- Clears QSettings for liquid_glass
- Resets theme tokens to defaults
- Used by all UI tests

### db_conn
- Direct sqlite3 connection to isolated test DB
- Sets `row_factory = sqlite3.Row`
- Yields connection for assertions

### migrated_database (alias)
- Same as isolated_database

### qt_app (module scope)
- Creates QApplication with stylesheet
- Used by PySide6 UI tests

## 7. TEST STRUCTURE (tests/)

### test_database.py
- Verifies schema creation, column presence, index existence
- Tests v1→v2→v3 migration integrity
- Verifies literature tables created by v3 migration
- Tests idempotent initialize_database

### test_tiers.py
- All 9 tier constants present and ordered SSS→F
- Case/whitespace normalization tests
- Invalid tier raises InvalidTierError
- Sort key produces sequential non-alphabetical order
- tier_display shows "—" for None/empty

### test_cards_and_dashboard.py
- Theme tests (stylesheet contains palette, tier colors span scale)
- Type label abbreviation tests
- Anime card tests (title/tier/progress, unassigned shows dash, no episodes)
- Literature card tests (each category renders, labels shown, chapters not episodes)
- Build card dispatch tests (anime→anime_card, literature→literature_card)
- Card selection tests (toggle, clear select mode)
- Card grid tests (reflow columns, clear removes)
- Dashboard tests (counts from database, category summaries, tier distribution, empty library, no overflow)
- Dashboard navigation tests (back button, refresh signals, KPI card population)
- Liquid glass tests (theme manager defaults, persistence, signals, theme dialog)

### test_anime_model.py, test_literature_discovery.py, test_import_tree.py, etc.
- Model-specific and import-specific tests

All tests use `isolated_database` fixture for per-test database isolation with full migrations applied.