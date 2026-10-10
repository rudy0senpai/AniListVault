from animevault.services.literature_search import (
    LiteratureSearchService,
    calculate_literature_match_score,
    normalize_search_variants,
)
from animevault.services.providers.literature import LiteratureMetadata
from animevault.services.providers.base import ProviderError


class FakeLiteratureProvider:
    def __init__(self, name, responses):
        self.name = name
        self.responses = responses
        self.queries = []

    def is_available(self):
        return True

    def search(self, query, limit=10):
        self.queries.append(query)
        result = self.responses.get(query, [])
        if isinstance(result, Exception):
            raise result
        return result


def test_search_variants_preserve_original_and_remove_safe_subtitle():
    variants = normalize_search_variants("  The Boxer: Season 2! ")
    assert variants[0] == "The Boxer: Season 2!"
    assert "The Boxer" in variants


def test_alias_match_is_high_confidence():
    candidate = LiteratureMetadata(title="Kusuriya no Hitorigoto", title_en="The Apothecary Diaries")
    assert calculate_literature_match_score("The Apothecary Diaries", candidate) >= 95


def test_romanized_title_match_is_high_confidence():
    candidate = LiteratureMetadata(title="The Apothecary Diaries", title_romaji="Kusuriya no Hitorigoto")
    assert calculate_literature_match_score("Kusuriya no Hitorigoto", candidate) == 100


def test_unicode_width_and_punctuation_normalize_for_matching():
    candidate = LiteratureMetadata(title="Tokyo Ghoul")
    assert calculate_literature_match_score("Ｔｏｋｙｏ—Ghoul!", candidate) == 100


def test_stored_english_alias_is_searched_without_replacing_original_title():
    candidate = LiteratureMetadata(title="Known English Title", title_en="Known English Title", anilist_id=88)
    primary = FakeLiteratureProvider("anilist", {"Known English Title": [candidate]})
    service = LiteratureSearchService(providers=[primary])

    selected = service.find_reliable_match("Original Stored Title", aliases=["Known English Title"], force_refresh=True)

    assert selected is candidate
    assert primary.queries[0] == "Original Stored Title"
    assert "Known English Title" in primary.queries


def test_known_anilist_id_uses_details_before_title_search():
    candidate = LiteratureMetadata(title="Stored Title", anilist_id=77)

    class ProviderWithDetails(FakeLiteratureProvider):
        def __init__(self):
            super().__init__("anilist-literature", {})
            self.detail_ids = []

        def get_details(self, provider_id):
            self.detail_ids.append(provider_id)
            return candidate

    primary = ProviderWithDetails()
    service = LiteratureSearchService(providers=[primary])

    selected = service.find_reliable_match("Stored Title", anilist_id=77, force_refresh=True)

    assert selected is candidate
    assert primary.detail_ids == ["77"]
    assert primary.queries == []


def test_only_reliable_single_candidate_is_auto_selected():
    good = LiteratureMetadata(title="Kusuriya no Hitorigoto", title_en="The Apothecary Diaries", anilist_id=1)
    anilist = FakeLiteratureProvider("anilist", {"Kusuriya no Hitorigoto": [good]})
    fallback = FakeLiteratureProvider("mangadex", {})
    service = LiteratureSearchService(providers=[anilist], fallback_providers=[fallback])

    selected = service.find_reliable_match("Kusuriya no Hitorigoto", force_refresh=True)
    assert selected is good
    assert fallback.queries == []


def test_ambiguous_plausible_candidates_are_not_auto_selected():
    one = LiteratureMetadata(title="Blue Period", anilist_id=1)
    two = LiteratureMetadata(title="Blue Period", anilist_id=2)
    anilist = FakeLiteratureProvider("anilist", {"Blue Period": [one, two]})
    fallback = FakeLiteratureProvider("mangadex", {})
    service = LiteratureSearchService(providers=[anilist], fallback_providers=[fallback])

    assert service.find_reliable_match("Blue Period", force_refresh=True) is None
    assert service.last_outcome == "ambiguous_candidates"


def test_subtitle_removal_is_search_only_and_does_not_auto_match_base_title():
    sequel = LiteratureMetadata(title="The Boxer", anilist_id=7)
    primary = FakeLiteratureProvider("anilist", {"The Boxer: Season 2": [sequel], "The Boxer": [sequel]})
    service = LiteratureSearchService(providers=[primary])

    assert service.find_reliable_match("The Boxer: Season 2", force_refresh=True) is None
    assert service.last_outcome == "low_confidence_candidates"


def test_candidate_with_incompatible_literature_category_is_not_selected():
    candidate = LiteratureMetadata(title="Exact Work", category="manhwa", anilist_id=11)
    expected = LiteratureMetadata(title="Exact Work", category="manga", anilist_id=14)
    primary = FakeLiteratureProvider("anilist", {"Exact Work": [candidate]})
    fallback = FakeLiteratureProvider("mangadex", {"Exact Work": [expected]})
    kitsu = FakeLiteratureProvider("kitsu-manga", {})
    service = LiteratureSearchService(providers=[primary], fallback_providers=[fallback, kitsu])

    assert service.find_reliable_match("Exact Work", expected_category="manga", force_refresh=True) is expected
    assert fallback.queries == ["Exact Work"]
    assert kitsu.queries == []


def test_author_and_year_break_an_exact_title_tie():
    expected = LiteratureMetadata(title="Twin Title", authors=["A. Writer"], started_at="2020-04-01", anilist_id=12)
    other = LiteratureMetadata(title="Twin Title", authors=["B. Writer"], started_at="2018-02-01", anilist_id=13)
    primary = FakeLiteratureProvider("anilist", {"Twin Title": [other, expected]})
    service = LiteratureSearchService(providers=[primary])

    selected = service.find_reliable_match("Twin Title", authors=["A. Writer"], year="2020", force_refresh=True)

    assert selected is expected


def test_fallback_providers_run_only_when_primary_has_no_reliable_match():
    near = LiteratureMetadata(title="A Different Story")
    anilist = FakeLiteratureProvider("anilist", {"Rare Title": [near]})
    manga = LiteratureMetadata(title="Rare Title", kitsu_id="k1")
    fallback = FakeLiteratureProvider("kitsu-manga", {"Rare Title": [manga]})
    service = LiteratureSearchService(providers=[anilist], fallback_providers=[fallback])

    assert service.find_reliable_match("Rare Title", force_refresh=True) is manga
    assert fallback.queries == ["Rare Title"]


def test_fallback_query_budget_is_bounded_across_variants():
    primary = FakeLiteratureProvider("anilist", {})
    mangadex = FakeLiteratureProvider("mangadex", {})
    kitsu = FakeLiteratureProvider("kitsu-manga", {})
    service = LiteratureSearchService(providers=[primary], fallback_providers=[mangadex, kitsu])

    service.find_reliable_match("Original: Subtitled", aliases=[f"Alias {n}" for n in range(10)], force_refresh=True)

    assert sum(len(p.queries) for p in (primary, mangadex, kitsu)) <= 18


def test_cross_provider_duplicates_are_removed_by_shared_title_and_year():
    first = LiteratureMetadata(title="Twin Work", started_at="2020-01-01", anilist_id=21)
    second = LiteratureMetadata(title="Twin Work", started_at="2019-01-01", anilist_id=22)
    duplicate = LiteratureMetadata(title="Twin Work", started_at="2020-07-01", kitsu_id="k-21")
    primary = FakeLiteratureProvider("anilist", {"Twin Work": [first, second]})
    fallback = FakeLiteratureProvider("mangadex", {"Twin Work": [duplicate]})
    service = LiteratureSearchService(providers=[primary], fallback_providers=[fallback])

    service.search("Twin Work", force_refresh=True)

    assert len(service.last_search_report["candidates"]) == 2


def test_distinct_same_title_and_year_candidates_remain_ambiguous():
    one = LiteratureMetadata(title="Same Name", started_at="2020-01-01", anilist_id=31)
    two = LiteratureMetadata(title="Same Name", started_at="2020-01-01", anilist_id=32)
    primary = FakeLiteratureProvider("anilist", {"Same Name": [one, two]})
    service = LiteratureSearchService(providers=[primary])

    assert service.find_reliable_match("Same Name", force_refresh=True) is None
    assert service.last_outcome == "ambiguous_candidates"


def test_provider_errors_do_not_become_no_candidate_outcome():
    anilist = FakeLiteratureProvider("anilist", {"Title": ProviderError("down", status_code=503)})
    fallback = FakeLiteratureProvider("kitsu-manga", {})
    service = LiteratureSearchService(providers=[anilist], fallback_providers=[fallback])

    assert service.find_reliable_match("Title", force_refresh=True) is None
    assert service.last_outcome == "provider_temporarily_unavailable"


def test_permanent_provider_error_is_not_mislabeled_as_no_match_or_temporary():
    anilist = FakeLiteratureProvider("anilist", {"Title": ProviderError("forbidden", status_code=403, retryable=False)})
    fallback = FakeLiteratureProvider("mangadex", {})
    service = LiteratureSearchService(providers=[anilist], fallback_providers=[fallback])

    assert service.find_reliable_match("Title", force_refresh=True) is None
    assert service.last_outcome == "provider_error"


def test_rate_limit_is_reported_separately():
    anilist = FakeLiteratureProvider("anilist", {"Title": ProviderError("limited", status_code=429, retryable=True, retry_after=30)})
    service = LiteratureSearchService(providers=[anilist])

    assert service.find_reliable_match("Title", force_refresh=True) is None
    assert service.last_outcome == "provider_rate_limited"


def test_cached_candidates_are_reused_without_provider_requests(monkeypatch):
    from animevault.services import literature_discovery

    candidate = LiteratureMetadata(title="Cached Title", anilist_id=42, search_provider="anilist", search_query="Cached Title")
    monkeypatch.setattr(literature_discovery.cache, "get", lambda *args, **kwargs: [vars(candidate)])
    primary = FakeLiteratureProvider("anilist", {})
    service = LiteratureSearchService(providers=[primary])

    selected = service.find_reliable_match("Cached Title")

    assert selected.anilist_id == 42
    assert service.last_cache_hit is True
    assert primary.queries == []
