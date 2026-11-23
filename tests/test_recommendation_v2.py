from animevault.models.anime import Anime
from animevault.models.literature import Literature
from animevault.recommendation.cache import CatalogueCache
from animevault.recommendation.content import SparseContentRetriever
from animevault.recommendation.engine import HybridRecommendationEngine
from animevault.recommendation.evaluation import ndcg_at_k, precision_at_k, recall_at_k
from animevault.recommendation.feedback import FeedbackStore
from animevault.recommendation.models import RecommendationCandidate
from animevault.recommendation.profile import build_profile


def anime(title, **kw):
    values = dict(id=None, title=title, status="completed", episodes=12,
                  episodes_watched=12, genres=[], studios=[], media_type="TV")
    values.update(kw)
    return Anime(**values)


def candidate(title, **kw):
    values = dict(title=title, media_type="TV", genres=(), studios=(), synopsis="")
    values.update(kw)
    return RecommendationCandidate(**values)


def test_jikan_provider_adapter_and_manager_fault_isolation():
    from animevault.recommendation.providers import JikanCandidateProvider, ProviderManager
    profile = build_profile([anime("Seed", mal_id=21, favorite=True, genres=["Action"]),
                             Literature(id=None, title="Manga Seed", category="manga", status="completed", favorite=True, mal_id=21, genres=["Action"])])
    fetched = candidate("Jikan result", mal_id=31, genres=("Action",))
    class Service:
        errors = []
        stats = {"related": 1}
        def recommendations_for(self, seeds, **kwargs):
            assert seeds == [(21, "Seed")]
            return [fetched]
        def genre_candidates(self, names, **kwargs):
            assert names == ["action"]
            return []
    class Broken:
        def discover(self, _profile, **_kwargs): raise TimeoutError("timeout")
    manager = ProviderManager([JikanCandidateProvider(Service()), Broken()])
    batch = manager.discover(profile)
    assert [row.title for row in batch.candidates] == ["Jikan result"]
    assert batch.stats["JikanCandidateProvider"] == {"related": 1}
    assert batch.errors[0]["category"] == "timeout"


def test_profile_uses_signed_signals_and_ignores_plan_to_watch():
    profile = build_profile([
        anime("Fav", favorite=True, genres=["Action"], mal_id=1),
        anime("Bad", status="dropped", score=2, genres=["Comedy"], mal_id=2),
        anime("Planned", status="plan_to_watch", score=None, genres=["Romance"], mal_id=3),
    ])
    assert profile.positive_genres["action"] == 1.0
    assert profile.negative_genres["comedy"] == 1.0
    assert "romance" not in profile.positive_genres
    assert [x.title for x in profile.positive_seeds] == ["Fav"]
    assert [x.title for x in profile.negative_seeds] == ["Bad"]


def test_profile_keeps_anime_and_literature_id_namespaces_separate():
    profile = build_profile([
        anime("Anime title", mal_id=42, favorite=True, genres=["Action"]),
        Literature(id=None, title="Manga title", category="manga", status="completed", favorite=True, mal_id=42, genres=["Romance"]),
    ])
    assert len(profile.positive_seeds) == 2
    assert "action" in profile.positive_genres and "romance" in profile.positive_genres


def test_profile_resolves_dropped_positive_favorite_and_deduplicates_ids():
    profile = build_profile([
        anime("Weak copy", mal_id=42, status="dropped", score=1, genres=["Comedy"]),
        anime("Positive favorite", mal_id=42, status="dropped", score=9, favorite=True, genres=["Action"]),
    ])
    assert len(profile.positive_seeds) == 1
    assert not profile.negative_seeds
    assert profile.positive_genres == {"action": 1.0}


def test_sparse_retriever_handles_missing_synopses_and_returns_shortlist(tmp_path):
    profile = build_profile([anime("Anchor", genres=["Action"], favorite=True)])
    retriever = SparseContentRetriever(cache_dir=tmp_path / "features").fit([
        candidate("A", genres=("Action",)), candidate("B", genres=("Romance",)),
    ])
    results = retriever.retrieve(profile, limit=2)
    assert len(results) == 2
    assert results[0][0].title == "A"
    assert results[0][1] >= results[1][1]
    retriever_again = SparseContentRetriever(cache_dir=tmp_path / "features").fit([
        candidate("A", genres=("Action",)), candidate("B", genres=("Romance",)),
    ])
    assert retriever_again.cache_hit
    assert retriever_again.retrieve(profile, limit=2)[0][0].title == "A"
    changed = SparseContentRetriever(cache_dir=tmp_path / "features").fit([
        candidate("A", genres=("Action",), synopsis="new synopsis"), candidate("B", genres=("Romance",)),
    ])
    assert not changed.cache_hit


def test_new_engine_ranks_profile_match_and_excludes_owned_candidate(tmp_path):
    library = [anime("My Favorite", mal_id=5, favorite=True, genres=["Action"]),
               anime("Owned Work", mal_id=7, genres=["Action"])]
    candidates = [candidate("Owned Work", mal_id=7, genres=("Action",)),
                  candidate("Action Pick", mal_id=10, genres=("Action",), synopsis="hero adventure"),
                  candidate("Popular Comedy", mal_id=11, genres=("Comedy",), score=10)]

    class Provider:
        errors = []
        stats = {}
        def reset_diagnostics(self): pass
        def recommendations_for(self, *_args, **_kwargs): return []
        def genre_candidates(self, *_args, **_kwargs): return candidates

    engine = HybridRecommendationEngine(library, provider=Provider(), cache=CatalogueCache(tmp_path / "catalogue.json"),
                                        feedback_store=FeedbackStore(tmp_path / "feedback.json"),
                                        feature_cache_dir=tmp_path / "features")
    results = engine.get_recommendations(n=5)
    assert [r.title for r in results][0] == "Action Pick"
    assert all(r.title != "Owned Work" for r in results)
    assert engine.get_preference_summary()["discovery_stats"]["owned_excluded"] == 1
    assert results[0].score_breakdown["genre_theme"] > results[-1].score_breakdown["genre_theme"]


def test_new_engine_owned_fallback_uses_alias_when_either_side_lacks_ids(tmp_path):
    library = [anime("Japanese Name", title_ja="日本語", media_type="TV", status="completed", favorite=True, genres=["Action"])]
    owned_alias = candidate("English Name", title_en="Japanese Name", mal_id=401, genres=("Action",))
    class Provider:
        errors = []
        stats = {}
        def recommendations_for(self, *_args, **_kwargs): return []
        def genre_candidates(self, *_args, **_kwargs): return [owned_alias]
    engine = HybridRecommendationEngine(library, provider=Provider(), cache=CatalogueCache(tmp_path / "cache.json"),
                                        feedback_store=FeedbackStore(tmp_path / "feedback.json"),
                                        feature_cache_dir=tmp_path / "features")
    assert engine.get_recommendations() == []
    assert engine.stats["owned_excluded"] == 1


def test_manga_library_ids_do_not_exclude_anime_candidates(tmp_path):
    manga = Literature(id=None, title="Shared title", category="manga", status="completed", favorite=True,
                       mal_id=42, genres=["Action"])
    engine = HybridRecommendationEngine([manga], online_discovery=False,
        cache=CatalogueCache(tmp_path / "cache.json"), feedback_store=FeedbackStore(tmp_path / "feedback.json"),
        feature_cache_dir=tmp_path / "features")
    assert not engine._owned(candidate("Different anime", mal_id=42, genres=("Action",)))


def test_engine_falls_back_to_stale_catalogue_without_network(tmp_path):
    library = [anime("Anchor", favorite=True, genres=["Action"])]
    cache = CatalogueCache(tmp_path / "catalogue.json", ttl_seconds=0)
    cache.write([candidate("Cached Action", mal_id=91, genres=("Action",))])
    engine = HybridRecommendationEngine(library, online_discovery=False, cache=cache,
                                        feedback_store=FeedbackStore(tmp_path / "feedback.json"),
                                        feature_cache_dir=tmp_path / "features")
    results = engine.get_recommendations(n=3)
    assert [result.title for result in results] == ["Cached Action"]
    assert engine.status == "offline_cached"
    assert results[0].is_cached


def test_new_engine_isolates_related_failure_from_genre_candidates(tmp_path):
    library = [anime("Anchor", mal_id=5, favorite=True, genres=["Action"])]
    class Provider:
        errors = []
        stats = {}
        def recommendations_for(self, *_args, **_kwargs): raise TimeoutError("related timed out")
        def genre_candidates(self, *_args, **_kwargs): return [candidate("Genre Candidate", mal_id=102, genres=("Action",))]
    engine = HybridRecommendationEngine(library, provider=Provider(), cache=CatalogueCache(tmp_path / "cat.json"),
                                        feedback_store=FeedbackStore(tmp_path / "feedback.json"),
                                        feature_cache_dir=tmp_path / "features")
    results = engine.get_recommendations(n=2)
    assert results[0].title == "Genre Candidate"
    assert engine.status == "partial_provider_failure"
    assert engine.errors[0]["source"] == "related_recommendations"


def test_feedback_store_is_separate_and_capped(tmp_path):
    store = FeedbackStore(tmp_path / "feedback.json")
    for _ in range(5):
        store.record("dislike", candidate_key="mal_id:12", title="Title")
    assert store.preference_adjustments()["mal_id:12"] == -.5
    assert len(store.read()) == 5


def test_cache_roundtrip_and_stale_fallback(tmp_path):
    cache = CatalogueCache(tmp_path / "cache.json", ttl_seconds=0)
    cache.write([candidate("Cached", mal_id=99, genres=("Action",))])
    items, stale = cache.read(allow_stale=True)
    assert stale and items[0].title == "Cached"
    assert cache.read(allow_stale=False) == ([], False)


def test_ranking_metrics_have_expected_values():
    assert precision_at_k(["a", "b"], {"a"}, 2) == .5
    assert recall_at_k(["a", "b"], {"a", "c"}, 2) == .5
    assert ndcg_at_k(["a", "b"], {"a": 1, "b": 0}, 2) == 1.0
