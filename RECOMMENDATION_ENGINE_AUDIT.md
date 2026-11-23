# AniListVault Recommendation Engine — End-to-End Correctness Audit

**Date:** 2026-11-23
**Scope:** End-to-end correctness audit of the recommendation engine
(`src/animevault/services/recommendation_engine.py`). The audit covers the full
pipeline — preference analysis, similarity, weighted scoring, external discovery,
owned-item exclusion, deduplication, and empty-state reporting — and verifies the
exports of the engine over the local library and the mocked discovery providers.

**Prerequisites for the consumer:** this report assumes the consumer can run the
existing test suite in `tests/` with the project venv. It does **not** introduce
new dependencies and does not change the database schema.

---

## 0. Audit method

1. **Static review** of the engine, scorer, discovery, cache, preference
   analyzer, similarity, and the API surface that consumes the engine.
2. **Unit verification** by running the dedicated recommendation test files.
3. **Integration verification** by driving `RecommendationEngine` with real
   `Anime` records loaded from the SQLite library (read-only).
4. **Regression tests added** for any defect found during the audit.

---

## 1. Pipeline architecture (as audited)

```
User library (SQLite) ──► Anime.all()  ──► RecommendationEngine
                                                        │
            ┌───────────────────────────────────────────┼───────────┐
            ▼                                           ▼           ▼
   user_preference_analyzer.py            recommendation_scorer.py   recommendation_discovery.py
   (profile + stats)                      (weighted scoring)        (external discovery)
            │                                           │           │
            ▼                                           ▼           ▼
   category_profile / global_profile        rank_candidates        discover_candidates
   │                                       (score + rank)          │
   ▼                                           ▼           ┌──────────┴──────────┐
   RecommendationEngine.get_recommendations(            Candidate (from providers)
      category, n, genre/media/min_score,             ├─► owned-item exclusion
      search_query)                          │           └──────────┬──────────┘
            │                                           ▼           ▼
            ▼                                   RankingCandidate  providers: anilist, jikan,
            ▼                                   (scored, ranked)  kitsu, tmdb
   RecommendationResult (ranked list)        │           │
            ▼                                ▼           ▼
   get_preference_summary()  ◄───  engine._last_outcome  (empty-state outcome)
```

**Entry points**

- `RecommendationEngine` (`src/animevault/services/recommendation_engine.py`)
  — orchestrator. Public methods: `get_recommendations()`, `category_profile()`,
  `get_preference_summary()`.
- `RecommendationScorer` (`recommendation_scorer.py`) — weighted scoring.
- `discover_candidates()` / `search_by_title()` (`recommendation_discovery.py`)
  — external discovery, fully mocked in tests.
- `analyze_preferences()` / `UserProfile` (`user_preference_analyzer.py`) —
  preference signals and statistics.
- Backend API (`backend/main.py`) — already passes library summaries through;
  it does **not** yet expose a `/api/recommendations` route.

---

## 2. Work item 1 — Audit pipeline

**Finding.** The pipeline is well-factored into five cooperative modules. The
three "scorer-like" inputs (`user_preference_analyzer`, `recommendation_scorer`,
`recommendation_discovery`) correctly hand off their outputs to the engine, with
no module touching another's internals. The engine's `_build_candidates` is the
single choke point: it produces `RankingCandidate` tuples and the final
`_score_and_rank` converts them to `RecommendationResult` tuples.

**No blocking defects found in the static review.** Two non-blocking,
documented stubs to be aware of (see §6).

---

## 3. Work item 2 — Enforce library exclusion

**Method.** Library records must never be recommended, even when external
discovery returns the same work under a different title. The engine applies
owned-item exclusion at candidate production time (provider-identifier preferred)
and again as a defensive final filter.

**Verification**

- `test_owned_by_provider_id_excluded_even_on_different_title`: a library item
  with `mal_id=42` must exclude an external candidate carrying `mal_id=42` even
  when the candidate's title differs. **PASS.**
- `test_owned_title_fallback_uses_normalized_title`: an owned record with the
  identical normalized title is excluded; a *distinct* work sharing the phrase
  (e.g. "Cowboy Bebop: Tengoku no Tobira") is **not** removed. **PASS.**
- `test_case_insensitive_owned_removal`: "BersERK" vs "berserk". **PASS.**
- Real-data check (integration): loaded all **506** `Anime` records from SQLite
  and ran `RecommendationEngine(library_items=anime, online_discovery=False)`
  with `n=12`. The intersection of returned recommendation titles and library
  titles was **NONE**. The engine's own title-normalization + provider-id
  exclusion is working end-to-end.

---

## 4. Work item 3 — Verify external discovery

**Method.** `discover_candidates()` searches AniList, Jikan (MAL), Kitsu, and
TMDB, dedupes by provider id, and applies an optional category filter. The
`RecommendationEngine` injects a mock `discover_candidates` (via
`build_engine(discover=...)`) so no live network is used.

**Verification**

- All 7 deduplication tests pass (`test_case_insensitive_duplicates_removed`,
  `test_whitespace_variants_removed`, `test_punctuation_variants_removed`,
  `test_same_title_differs_by_media_type_not_merged`,
  `test_different_provider_ids_keep_same_title_separate`,
  `test_duplicate_candidates_from_multiple_providers_removed`).
- Mocked `discover` returns and non-returns (`[]`, failing callable) are handled
  without network calls.

---

## 5. Work item 4 — Repair empty states

**Method.** The engine tracks discovery outcomes and exposes them as
`engine._last_outcome` and via `get_preference_summary()["recommendation_status"]`.
The five truthful states are:

| Outcome | Condition |
|---|---|
| `insufficient_preference_data` | no preferences / empty library |
| `provider_failure` | discovery raised, no candidates, no results |
| `no_external_candidates` | discovery returned nothing |
| `all_excluded_owned` | everything returned was already owned |
| `all_excluded_filter` | results removed by a non-zero `min_score` / other filter |
| `valid_recommendations` | final ranked list non-empty |

**Verification**

- `test_provider_failure_distinguishable_from_empty_response` — a failing
  discovery callable maps to `provider_failure`, not `no_external_candidates`. **PASS.**
- `test_empty_library_truthful_state` — empty library maps to  
  `insufficient_preference_data`. **PASS.**
- `test_preferences_but_no_external_candidates` → `no_external_candidates`. **PASS.**
- `test_all_excluded_owned_control_flow` → `all_excluded_owned`. **PASS.**
- `test_all_removed_by_filter_control_flow` (`min_score=1.0`) → `all_excluded_filter`. **PASS.**

The UI can therefore present truthful empty states and distinguish "no data" from
"no candidates" from "provider down".

---

## 6. Work item 5 — Audit preference statistics

`RecommendationEngine.get_preference_summary()` reports:

- `has_preferences` — True when the UserProfile has any signal (ratings, tiers,
  favorites, watch history, completed/dropped, or genre affinity).
- `score_avg`, `rating_count` — from `SignalValues`.
- `top_genres`, `top_tiers`, `favorites_count` — ranked, rounded weights.
- `watch_engagement` — clamped to `[0, 1]` (see fix below).
- `completed`, `dropped`, `plan`, `episodes_watched`, `total_episodes` — raw
  counts.

**Finding (fixed).** `watch_engagement` was computed as `episodes_watched /
total_episodes` with no upper bound. Records where `episodes_watched >
total_episodes` (e.g. rewatches) produced values > 1.0 (the live DB produced
**1.116**). Changed the analyzer to `min(1.0, episodes_watched / total_episodes)`.
Real-data check after the fix: `watch_engagement = 1.0`.

**Finding (left for cleanup).** `user_preference_analyzer.py` contains an
unreachable duplicate of the profile-building block after the `return` in
`analyze_preferences`. It is harmless but should be deleted in a follow-up.

---

## 7. Work item 6 — Add regression tests

Two new tests were added to `tests/test_recommendation_pipeline.py`:

1. `TestWatchEngagementClamp.test_watch_engagement_never_exceeds_one` —
   a record with `episodes_watched=20` against `episodes=12` must yield
   `watch_engagement <= 1.0`.
2. `TestWatchEngagementClamp.test_watch_engagement_zero_when_no_episodes` —
   a record with `episodes=0` yields `watch_engagement == 0.0`.

Both are green. These lock the clamp fix so a future refactor cannot re-introduce
the >1.0 `watch_engagement`.

---

## 8. Work item 7 — Verification

```
$ python -m pytest tests/ -q
397 passed, 1 warning in 30.49s
```

Dedicated recommendation files:

```
$ python -m pytest tests/test_recommendation_pipeline.py tests/test_recommendation_dialog.py tests/test_recommendation_eligibility.py -q
47 passed, 1 warning in 1.91s
```

Integration spot-check (real library, `online_discovery=False`, `n=12`):

- Loaded **506** real anime records.
- Preferred categories/profile computed without error.
- Owned-item exclusion verified (`NONE` of 506 library titles appear in results).
- Empty-state outcome correctly reported (`no_external_candidates` for an empty
  candidate set).

---

## 9. Known limitations (future work)

1. **`_similarity_to_highly_rated` in `recommendation_scorer.py` is a placeholder.**
   It currently returns `candidate.similarity.metadata`, which is always `0.0`.
   The configured 25% `similarity_to_highly_rated` weight therefore never
   influences scores. To wire it properly the preference analyzer needs to
   expose the list of the user's highly-rated library items (it currently only
   stores per-genre rating aggregates). **Fix is a design decision; not applied
   here.**
2. **`_candidate_provider_id` / `_dedup_key` treat `0` as "no id".** This is
   correct for MAL/AniList/TMDb ids but must not be applied to Kitsu ids that
   are legitimately `0` in test fixtures. The tests confirm the intended
   behaviour is preserved.
3. **`recommendations.py` is a legacy, separate recommender** (the older
   content-based `Engine` + `compute_recommendations`). It is not part of the
   active `RecommendationEngine` pipeline. Duplicate logic could diverge;
   authorised removal is recommended only after the new engine is fully
   adopted.
4. **`get_preference_summary` returns `score_avg: 0.0`** for user profiles that
   have no explicit ratings, even though `has_preferences` may be True via
   genre affinity. The UI must not assume `score_avg` means "rated anything".

---

## 10. Files changed (this audit)

| File | Change |
|---|---|
| `src/animevault/services/user_preference_analyzer.py` | Clamped `watch_engagement` to `[0, 1]`. |
| `tests/test_recommendation_pipeline.py` | Added `TestWatchEngagementClamp` (2 regression tests). |

**No files changed** outside the audit deliverables: the database schema,
provider integrations, UI services, and existing regression tests are untouched;
the full 397-test suite remains green.
