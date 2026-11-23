"""Two-stage local retrieval plus optional Jikan candidate expansion."""
from __future__ import annotations

from dataclasses import replace
from animevault.services.title_norm import normalize_title
from .cache import CatalogueCache
from .content import SparseContentRetriever, as_candidate
from .feedback import FeedbackStore
from .models import RecommendationCandidate
from .profile import build_profile
from .ranking import HybridRanker, RankerAdapter


class HybridRecommendationEngine:
    """Personalized candidate retrieval and transparent ranking.

    Provider output is candidate metadata only; all ordering is computed from
    the local profile, sparse content similarity, and configured feature blend.
    """
    def __init__(self, library_items=(), *, provider=None, cache=None, feedback_store=None, feature_cache_dir=None, online_discovery=True, ranker: RankerAdapter | None = None):
        self.library_items = list(library_items or [])
        self.provider = provider
        self.cache = cache or CatalogueCache()
        self.feedback_store = feedback_store or FeedbackStore()
        self.feature_cache_dir = feature_cache_dir
        self.online_discovery = online_discovery
        self.ranker = ranker or HybridRanker()
        self.profile = build_profile(self.library_items)
        self.status = "not_run"
        self.errors = []
        self.stats = {}

    def _service(self):
        if self.provider is not None:
            return self.provider
        from animevault.services.jikan_recommendation_service import JikanRecommendationService
        return JikanRecommendationService()

    def _discover(self):
        candidates = []
        self.errors = []
        self.stats = {}
        if self.online_discovery and (self.provider is None or callable(getattr(self.provider, "discover", None))):
            try:
                if self.provider is None:
                    from .providers import JikanCandidateProvider, ProviderManager
                    provider = ProviderManager([JikanCandidateProvider()])
                else:
                    provider = self.provider
                batch = provider.discover(self.profile)
                candidates.extend(batch.candidates)
                self.errors.extend(batch.errors)
                self.stats.update(batch.stats)
            except Exception as exc:
                self.errors.append({"source": "provider", "category": _error_category(exc), "message": str(exc)})
        elif self.online_discovery:
            try:
                service = self._service()
                reset = getattr(service, "reset_diagnostics", None)
                if callable(reset): reset()
                seed_pairs = []
                seen_mal = set()
                for seed in self.profile.positive_seeds:
                    mal = getattr(seed, "mal_id", None)
                    if mal:
                        try: mal = int(mal)
                        except (TypeError, ValueError): continue
                        if mal > 0 and mal not in seen_mal:
                            seen_mal.add(mal)
                            seed_pairs.append((mal, str(getattr(seed, "title", ""))))
                if seed_pairs:
                    try:
                        candidates.extend(service.recommendations_for(seed_pairs[:3], per_seed=8, max_seeds=3))
                    except Exception as exc:
                        self.errors.append({"source": "related_recommendations", "category": _error_category(exc), "message": str(exc)})
                top_genres = sorted(self.profile.positive_genres.items(), key=lambda x: (-x[1], x[0]))[:3]
                if top_genres:
                    try:
                        candidates.extend(service.genre_candidates([name for name, _ in top_genres], max_genres=3, pages_per_genre=2, limit=25))
                    except Exception as exc:
                        self.errors.append({"source": "genre_discovery", "category": _error_category(exc), "message": str(exc)})
                self.errors.extend(list(getattr(service, "errors", []) or []))
                self.stats.update(dict(getattr(service, "stats", {}) or {}))
            except Exception as exc:
                self.errors.append({"source": "provider", "category": _error_category(exc), "message": str(exc)})
        converted = [as_candidate(c) for c in candidates if getattr(c, "title", "").strip()]
        if converted:
            self.cache.write(converted)
            return converted, False
        cached, stale = self.cache.read(allow_stale=True)
        if cached:
            return [replace(c, metadata={**c.metadata, "is_cached": True}) for c in cached], True
        return [], False

    def _owned(self, candidate):
        candidate_ids = set()
        for field in ("mal_id", "anilist_id", "tmdb_id", "kitsu_id"):
            value = getattr(candidate, field, None)
            if value:
                candidate_ids.add((field, str(value).casefold()))
        candidate_titles = {normalize_title(value) for value in
                            (candidate.title, candidate.title_en, candidate.title_romaji, candidate.title_ja, *candidate.synonyms)
                            if value}
        for item in self.library_items:
            if str(getattr(item, "category", "") or "").casefold() in {"manga", "manhwa", "manhua"}:
                continue
            item_ids = set()
            for field in ("mal_id", "anilist_id", "tmdb_id", "kitsu_id"):
                value = getattr(item, field, None)
                if value:
                    item_ids.add((field, str(value).casefold()))
            if candidate_ids & item_ids:
                return True
            # Exact alias + format fallback is scoped to ID-less library rows.
            if not item_ids:
                item_titles = {normalize_title(getattr(item, field, "")) for field in ("title", "title_en", "title_romaji", "title_ja") if getattr(item, field, "")}
                if candidate_titles & item_titles:
                    item_format = str(getattr(item, "media_type", "") or "").casefold()
                    if not item_format or not candidate.media_type or item_format == candidate.media_type.casefold():
                        return True
        return False

    @staticmethod
    def _dedupe(candidates):
        result, ids, title_id_state = [], set(), {}
        for candidate in candidates:
            candidate_ids = {(field, str(getattr(candidate, field)).casefold()) for field in ("mal_id", "anilist_id", "tmdb_id", "kitsu_id") if getattr(candidate, field, None)}
            title_keys = {(normalize_title(value), candidate.media_type.casefold()) for value in
                          (candidate.title, candidate.title_en, candidate.title_romaji, candidate.title_ja, *candidate.synonyms) if value}
            seen_state = next((title_id_state[key] for key in title_keys if key in title_id_state), None)
            if (candidate_ids and candidate_ids & ids) or (seen_state is not None and (not candidate_ids or not seen_state)):
                continue
            result.append(candidate)
            ids.update(candidate_ids)
            state = bool(candidate_ids) if seen_state is None else (seen_state and bool(candidate_ids))
            for key in title_keys:
                title_id_state[key] = state
        return result

    def get_recommendations(self, *, n=12, genre_filter="", media_type_filter="all", min_score=0.0, category="all"):
        if not self.profile.usable:
            self.status = "no_usable_profile"
            return []
        candidates, used_cache = self._discover()
        before = len(candidates)
        unique = self._dedupe(candidates)
        after_dedup = len(unique)
        owned = [c for c in unique if self._owned(c)]
        eligible = [c for c in unique if not self._owned(c)]
        if category and category.casefold() != "all":
            requested = category.casefold()
            eligible = [c for c in eligible if _category_matches(c, requested)]
        if genre_filter:
            eligible = [c for c in eligible if any(genre_filter.casefold() in g.casefold() for g in c.genres)]
        if media_type_filter and media_type_filter.casefold() != "all":
            eligible = [c for c in eligible if c.media_type.casefold() == media_type_filter.casefold()]
        adjustments = self.feedback_store.preference_adjustments()
        eligible = [replace(c, feedback_signal=adjustments.get(_feedback_key(c), 0.0)) for c in eligible]
        retriever = SparseContentRetriever(cache_dir=self.feature_cache_dir).fit([*eligible])
        retrieved = retriever.retrieve(self.profile, limit=max(100, n * 10))
        outputs = self.ranker.rank(retrieved, self.profile, limit=max(n, 1))
        outputs = [o for o in outputs if o.explanation.score >= min_score][:max(0, n)]
        self.stats.update({"library_count": len(self.library_items), "provider_candidates": before,
                           "duplicates_removed": before - after_dedup, "owned_excluded": len(owned),
                           "eligible_candidates": len(eligible), "final_recommendations": len(outputs),
                           "cached_candidates": len(candidates) if used_cache else 0})
        if outputs:
            self.status = "offline_cached" if used_cache else ("partial_provider_failure" if self.errors else "available")
        elif self.errors:
            self.status = "provider_unavailable"
        elif not candidates:
            self.status = "no_candidates"
        elif not eligible:
            self.status = "no_eligible_candidates"
        else:
            self.status = "filtered_out"
        from animevault.services.recommendation_engine import RecommendationResult
        results = []
        for output in outputs:
            c = output.candidate
            provider_key, provider_id = "", ""
            for field in ("anilist_id", "mal_id", "tmdb_id", "kitsu_id"):
                value = getattr(c, field, None)
                if value:
                    provider_key, provider_id = field, str(value)
                    break
            results.append(RecommendationResult(
                item_id=int(c.mal_id or c.anilist_id or 0), title=c.title, media_type=c.media_type,
                category=category, genres=list(c.genres), synopsis=c.synopsis,
                score=output.explanation.score, reasons=list(output.explanation.reasons),
                poster_url=c.poster_url, title_ja=c.title_ja, episodes=c.episodes,
                provider_key=provider_key, provider_id=provider_id, is_cached=output.cached,
                discovery_source=c.source, score_breakdown=dict(output.explanation.features),
            ))
        return results

    def get_preference_summary(self):
        return {"has_preferences": self.profile.usable, "recommendation_status": self.status,
                "discovery_errors": list(self.errors), "discovery_stats": dict(self.stats),
                "top_genres": sorted(self.profile.positive_genres.items(), key=lambda x: -x[1])[:5],
                "confidence": dict(self.profile.confidence),
                "rating_mean": self.profile.rating_mean, "rating_count": self.profile.rating_count}


def _category_matches(candidate, category):
    genres = {str(value).casefold() for value in candidate.genres}
    if category == "sci-fi":
        return bool(genres & {"sci-fi", "science fiction"})
    if category == "slice of life":
        return "slice of life" in genres
    return category in genres


def _feedback_key(candidate):
    for field in ("anilist_id", "mal_id", "tmdb_id", "kitsu_id"):
        value = getattr(candidate, field, None)
        if value:
            return f"{field}:{value}"
    return f"title:{normalize_title(candidate.title)}:{candidate.media_type.casefold()}"


def _error_category(exc):
    status = getattr(exc, "status_code", None)
    if status == 429: return "rate_limited"
    if status is not None: return f"http_{status}"
    if "timeout" in str(exc).casefold(): return "timeout"
    return "provider_error"
