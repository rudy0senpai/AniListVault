"""Conservative literature title discovery and provider fallback coordination."""
from __future__ import annotations
import difflib, logging, re, unicodedata
from animevault.models.literature import Literature
from animevault.services import cache
from animevault.services.providers.base import ProviderError
from animevault.services.providers.literature import AniListLiteratureProvider, LiteratureMetadata
from animevault.services.diagnostics import sanitize_error
logger = logging.getLogger(__name__)

def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold()
    value = re.sub(r"[’‘`´]", "'", value)
    value = re.sub(r"[\s\-‐‑‒–—_:：]+", " ", value)
    value = re.sub(r"[^\w\s']", " ", value, flags=re.UNICODE)
    return " ".join(value.split())

def normalize_search_variants(title: str) -> list[str]:
    """Produce original-first and safe subtitle variants; never translate the title."""
    original = (title or "").strip()
    if not original: return []
    out = [original]
    head = re.split(r"\s*[:：]\s*|\s+[—–|]\s*", original, maxsplit=1)[0].strip()
    if len(head) >= 3 and _norm(head) != _norm(original): out.append(head)
    normalized = " ".join(unicodedata.normalize("NFKC", original).split())
    if normalized not in out: out.append(normalized)
    return out[:3]

def calculate_literature_match_score(query: str, meta: LiteratureMetadata) -> float:
    """Conservative title similarity across English, native, romanized, and synonym values."""
    q, score = _norm(query), 0.0
    for raw in [meta.title, meta.title_en, meta.title_romaji, meta.title_native, *meta.synonyms]:
        t = _norm(raw)
        if not t: continue
        if t == q: score = max(score, 100.0)
        elif q and (t.startswith(q + " ") or q.startswith(t + " ")): score = max(score, 82.0)
        else: score = max(score, difflib.SequenceMatcher(None, q, t).ratio() * 78.0)
    return score


def build_search_variants(title: str, aliases=None) -> list[str]:
    """Include stored English/native/synonym titles without guessing translations."""
    values = normalize_search_variants(title) + [str(x).strip() for x in (aliases or []) if str(x or "").strip()]
    cleaned = _norm(title)
    if cleaned:
        values.append(cleaned)
    seen, result = set(), []
    for value in values:
        key = _norm(value)
        if key and key not in seen:
            seen.add(key)
            result.append(value)
        if len(result) >= 6:
            break
    return result

class LiteratureSearchService:
    """Use AniList first; call MangaDex/Kitsu only if primary match is uncertain."""
    def __init__(self, providers=None, fallback_providers=None):
        if providers is None:
            self._providers = [AniListLiteratureProvider()]
            if fallback_providers is None:
                from animevault.services.providers.manga_sources import KitsuMangaProvider, MangaDexProvider
                self._fallback_providers = [MangaDexProvider(), KitsuMangaProvider()]
            else: self._fallback_providers = list(fallback_providers)
        else:
            self._providers = list(providers)
            self._fallback_providers = list(fallback_providers or [])
        self.last_cache_hit, self.last_outcome, self.last_search_report = False, "", {}
    @property
    def providers(self): return self._providers + self._fallback_providers
    @staticmethod
    def _provider_identities(meta):
        identities = {f"al:{meta.anilist_id}"} if meta.anilist_id else set()
        identities.update({f"kitsu:{meta.kitsu_id}"} if meta.kitsu_id else set())
        identities.update({f"mal:{meta.mal_id}"} if meta.mal_id else set())
        identities.update(f"{key}:{value}" for key, value in (meta.provider_ids or {}).items() if value)
        return identities or {f"object:{id(meta)}"}
    @classmethod
    def _identities(cls, meta):
        identities = cls._provider_identities(meta)
        year = (meta.started_at or "")[:4]
        if year:
            for title in (meta.title, meta.title_en, meta.title_native, *meta.synonyms):
                normalized = _norm(title)
                if normalized: identities.add(f"title:{normalized}:{year}")
        return identities
    @classmethod
    def _deduplicate_across_providers(cls, primary, fallback):
        result = list(primary)
        primary_identities = set().union(*(cls._identities(meta) for meta in primary)) if primary else set()
        fallback_ids = set()
        for meta in fallback:
            identities = cls._identities(meta)
            provider_ids = cls._provider_identities(meta)
            if identities.isdisjoint(primary_identities) and provider_ids.isdisjoint(fallback_ids):
                result.append(meta)
            fallback_ids.update(provider_ids)
        return result
    def _query_providers(self, providers, variants, limit, strong_variants, expected_category):
        results, searched, errors, seen = [], [], [], set()
        for provider in providers:
            if not provider.is_available(): continue
            provider_results = []
            for query in variants:
                searched.append(f"{provider.name}:{query}")
                try: found = provider.search(query, limit=limit)
                except ProviderError as exc:
                    exc.provider = exc.provider or provider.name; errors.append((provider.name, exc))
                    logger.warning("Literature provider %s failed: %s", provider.name, sanitize_error(exc)); break
                except Exception as exc:
                    logger.warning("Literature provider %s failed: %s", provider.name, sanitize_error(exc))
                    errors.append((provider.name, ProviderError("provider response could not be processed", retryable=False, provider=provider.name)))
                    break
                for meta in found:
                    identities = self._provider_identities(meta)
                    if identities.isdisjoint(seen):
                        meta.search_query, meta.search_provider = query, provider.name; results.append(meta); provider_results.append(meta)
                    seen.update(identities)
                if self._reliable(provider_results, strong_variants, expected_category):
                    break
            if self._reliable(provider_results, strong_variants, expected_category):
                break
        return results, searched, errors
    @staticmethod
    def _score(meta, variants): return max(calculate_literature_match_score(v, meta) for v in variants)
    @staticmethod
    def _compatible(meta, expected_category):
        return not expected_category or not meta.category or meta.category.casefold() == expected_category.casefold()
    @classmethod
    def _reliable(cls, results, variants, expected_category):
        scores = sorted((cls._score(m, variants) for m in results if cls._compatible(m, expected_category)), reverse=True)
        return bool(scores and scores[0] >= 95 and (len(scores) == 1 or scores[0] - scores[1] >= 8))
    def search(self, query, limit=15, *, force_refresh=False, aliases=None, expected_category=None):
        q = (query or "").strip(); self.last_cache_hit, self.last_outcome = False, ""
        if not q: return []
        alias_values = [str(x).strip() for x in (aliases or []) if str(x or "").strip()]
        key = f"search:literature:{q.casefold()}:{int(limit)}:{'|'.join(alias_values).casefold()}:{(expected_category or '').casefold()}"
        cached = None if force_refresh else cache.get(key, ttl=cache.TTL_METADATA)
        if isinstance(cached, list):
            self.last_cache_hit = True
            cached_results = [LiteratureMetadata(**item) for item in cached]
            variants = build_search_variants(q, alias_values)
            self.last_search_report = {"original_title": q, "variants": variants,
                "providers_searched": list(dict.fromkeys(m.search_provider or m.source_provider for m in cached_results)),
                "queries": [f"{m.search_provider}:{m.search_query}" for m in cached_results if m.search_query],
                "candidates": [{"provider": m.search_provider or m.source_provider, "query": m.search_query, "title": m.display_title(), "score": self._score(m, [q, *alias_values]), "anilist_id":m.anilist_id,"kitsu_id":m.kitsu_id,"mal_id":m.mal_id,"provider_ids":m.provider_ids,"category":m.category,"format":m.format,"status":m.status,"started_at":m.started_at,"authors":m.authors} for m in cached_results],
                "errors": [], "providers_not_configured": []}
            return cached_results
        variants = build_search_variants(q, alias_values)
        strong_variants = [q, *alias_values]
        results, searched, errors = self._query_providers(self._providers, variants, limit, strong_variants, expected_category)
        if not self._reliable(results, strong_variants, expected_category):
            fallback, extra_searches, extra_errors = self._query_providers(self._fallback_providers, variants, limit, strong_variants, expected_category)
            searched += extra_searches; errors += extra_errors
            results = self._deduplicate_across_providers(results, fallback)
        results.sort(key=lambda m: self._score(m, variants), reverse=True)
        self.last_search_report = {"original_title": q, "variants": variants,
            "providers_searched": list(dict.fromkeys(s.split(":", 1)[0] for s in searched)),
            "providers_not_configured": [p.name for p in self.providers if getattr(p, "configuration_required", False) and not p.is_available()],
            "queries": searched,
            "candidates": [{"provider": getattr(m,"search_provider",m.source_provider),"query":getattr(m,"search_query",q),"title":m.display_title(),"score":self._score(m,strong_variants),"anilist_id":m.anilist_id,"kitsu_id":m.kitsu_id,"mal_id":m.mal_id,"provider_ids":m.provider_ids,"category":m.category,"format":m.format,"status":m.status,"started_at":m.started_at,"authors":m.authors} for m in results],
            "errors": [{"provider":n,"category":"rate_limited" if e.status_code==429 else "temporarily_unavailable" if e.retryable else "provider_error"} for n,e in errors]}
        if results:
            try: cache.put(key, [vars(m) for m in results[:limit]])
            except Exception: pass
        return results[:limit]
    def find_reliable_match(self, query, *, force_refresh=False, aliases=None, expected_category=None, authors=None, year=None, anilist_id=None):
        strong_variants = [query, *(aliases or [])]
        if anilist_id is not None:
            for provider in self._providers:
                if getattr(provider, "name", "") != "anilist-literature" or not hasattr(provider, "get_details"):
                    continue
                try:
                    detail = provider.get_details(str(anilist_id))
                except ProviderError as exc:
                    logger.warning("AniList detail lookup failed: %s", sanitize_error(exc))
                    break
                if (detail and str(detail.anilist_id or "") == str(anilist_id)
                        and self._compatible(detail, expected_category)
                        and self._score(detail, strong_variants) >= 95):
                    detail.search_query, detail.search_provider = query, provider.name
                    self.last_cache_hit = False
                    self.last_outcome = "matched"
                    self.last_search_report = {"original_title": query, "variants": build_search_variants(query, aliases),
                        "providers_searched": [provider.name], "queries": [f"{provider.name}:id={anilist_id}"],
                        "candidates": [{"provider": provider.name, "query": f"id={anilist_id}", "title": detail.display_title(), "score": self._score(detail, strong_variants), "anilist_id": detail.anilist_id}],
                        "errors": [], "providers_not_configured": []}
                    return detail
                break
        results = self.search(query, limit=10, force_refresh=force_refresh, aliases=aliases, expected_category=expected_category); errors = self.last_search_report.get("errors", [])
        if not results:
            if any(e["category"]=="rate_limited" for e in errors): self.last_outcome = "provider_rate_limited"
            elif any(e["category"]=="temporarily_unavailable" for e in errors): self.last_outcome = "provider_temporarily_unavailable"
            elif errors: self.last_outcome = "provider_error"
            else: self.last_outcome = "no_candidate_found"
            return None
        strong_variants = [query, *(aliases or [])]
        scored = []
        for meta in results:
            compatible = not expected_category or not meta.category or meta.category.casefold() == expected_category.casefold()
            title_score = self._score(meta, strong_variants) if compatible else 0.0
            candidate_authors = {_norm(name) for name in [*meta.authors, *meta.artists] if name}
            hinted_authors = {_norm(name) for name in (authors or []) if name}
            evidence = (6 if candidate_authors.intersection(hinted_authors) else 0)
            if year and meta.started_at and meta.started_at[:4] == str(year)[:4]: evidence += 3
            scored.append((title_score, evidence, meta))
        scored.sort(key=lambda row: row[0] + row[1], reverse=True)
        if scored[0][0] < 95: self.last_outcome = "low_confidence_candidates"; return None
        if len(scored)>1 and (scored[0][0] + scored[0][1]) - (scored[1][0] + scored[1][1]) < 8: self.last_outcome = "ambiguous_candidates"; return None
        self.last_outcome = "matched"; return scored[0][2]
    def find_duplicate(self, meta):
        found = Literature.find_by_provider_id(anilist_id=meta.anilist_id,kitsu_id=meta.kitsu_id,mal_id=meta.mal_id)
        if found: return found
        for title in (meta.title,meta.title_en,meta.title_native,*meta.synonyms):
            if title and title.strip():
                found=Literature.find_by_title(title)
                if found: return found
        return None
