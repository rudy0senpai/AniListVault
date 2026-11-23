"""Sparse TF-IDF retrieval over candidate metadata; no all-pairs matrix."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

try:
    import numpy as np
    from scipy.sparse import load_npz, save_npz
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.preprocessing import normalize
except ImportError:  # offline metadata-only fallback
    np = None
    load_npz = save_npz = TfidfVectorizer = normalize = None

from .cache import default_cache_dir
from .models import RecommendationCandidate, UserPreferenceProfile


def as_candidate(value) -> RecommendationCandidate:
    if isinstance(value, RecommendationCandidate):
        return value
    def names(key):
        raw = getattr(value, key, ()) or ()
        if isinstance(raw, str):
            return tuple(x.strip() for x in raw.split(",") if x.strip())
        return tuple(str(x) for x in raw if x)
    year = getattr(value, "season_year", None)
    try:
        year = int(year) if year else None
    except (ValueError, TypeError):
        year = None
    return RecommendationCandidate(
        title=str(getattr(value, "title", "") or ""),
        title_en=str(getattr(value, "title_en", "") or ""),
        title_romaji=str(getattr(value, "title_romaji", "") or ""),
        synonyms=names("synonyms"),
        media_type=str(getattr(value, "media_type", "") or ""),
        genres=names("genres"), themes=names("themes"), studios=names("studios"),
        synopsis=str(getattr(value, "synopsis", "") or ""), release_year=year,
        score=getattr(value, "score", None), popularity=getattr(value, "popularity", None),
        rank=getattr(value, "rank", None), mal_id=getattr(value, "mal_id", None),
        anilist_id=getattr(value, "anilist_id", None), kitsu_id=getattr(value, "kitsu_id", None),
        tmdb_id=getattr(value, "tmdb_id", None), poster_url=str(getattr(value, "poster_url", "") or ""),
        title_ja=str(getattr(value, "title_ja", "") or ""), episodes=int(getattr(value, "episodes", 0) or 0),
        source=str(getattr(value, "discovery_source", "") or ""),
        relationship_signal=float(getattr(value, "recommendation_signal", 0.0) or 0.0),
        metadata={"raw": value, "is_cached": bool(getattr(value, "is_cached", False))},
    )


def content_text(item) -> str:
    tags = list(item.genres) + list(item.themes) + list(item.studios)
    parts = [" ".join(tags), str(item.media_type or ""), str(item.synopsis or "")]
    return " ".join(part for part in parts if part.strip())


@dataclass
class SparseContentRetriever:
    """Fit a bounded pool and retrieve near positive seeds with disk caching."""
    min_df: int = 1
    vectorizer: object = None
    matrix: object = None
    candidates: tuple[RecommendationCandidate, ...] = ()
    cache_dir: object = None
    cache_hit: bool = False

    def _cache_paths(self, fingerprint):
        try:
            root = self.cache_dir or (default_cache_dir() / "features")
            root.mkdir(parents=True, exist_ok=True)
            return root / f"{fingerprint}.npz", root / f"{fingerprint}.json"
        except OSError:
            return None, None

    def fit(self, candidates):
        self.candidates = tuple(as_candidate(c) for c in candidates)
        texts = [content_text(c) for c in self.candidates]
        if TfidfVectorizer is None or not texts or not any(text.strip() for text in texts):
            self.vectorizer = self.matrix = None
            return self
        digest = hashlib.sha256(json.dumps(texts, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
        matrix_path, manifest_path = self._cache_paths(digest)
        self.cache_hit = False
        if matrix_path is not None and manifest_path is not None and matrix_path.exists() and manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                matrix = load_npz(matrix_path).tocsr()
                vocabulary = manifest["vocabulary"]
                idf = np.asarray(manifest["idf"], dtype=float)
                if manifest.get("fingerprint") == digest and matrix.shape == (len(texts), len(vocabulary)) and len(idf) == len(vocabulary):
                    vectorizer = TfidfVectorizer(stop_words="english", min_df=self.min_df, ngram_range=(1, 2), sublinear_tf=True, vocabulary=vocabulary)
                    vectorizer.fit([next(text for text in texts if text.strip())])
                    vectorizer.idf_ = idf
                    self.vectorizer, self.matrix, self.cache_hit = vectorizer, matrix, True
                    return self
            except (OSError, ValueError, TypeError, KeyError):
                pass
        vectorizer = TfidfVectorizer(stop_words="english", min_df=self.min_df, ngram_range=(1, 2), sublinear_tf=True)
        try:
            matrix = vectorizer.fit_transform(texts).tocsr()
        except ValueError:
            self.vectorizer = self.matrix = None
            return self
        self.vectorizer, self.matrix = vectorizer, matrix
        if matrix_path is None or manifest_path is None:
            return self
        temporary_matrix = matrix_path.with_suffix(".tmp.npz")
        temporary_manifest = manifest_path.with_suffix(".tmp")
        try:
            save_npz(temporary_matrix, matrix)
            temporary_manifest.write_text(json.dumps({"fingerprint": digest, "vocabulary": vectorizer.vocabulary_, "idf": vectorizer.idf_.tolist()}, ensure_ascii=False), encoding="utf-8")
            temporary_matrix.replace(matrix_path)
            temporary_manifest.replace(manifest_path)
        except OSError:
            temporary_matrix.unlink(missing_ok=True)
            temporary_manifest.unlink(missing_ok=True)
        return self

    def similarities(self, profile: UserPreferenceProfile) -> dict[int, float]:
        if self.matrix is None or self.vectorizer is None or not profile.positive_seeds:
            return {}
        texts, weights = [], []
        from .profile import _signals
        for seed in profile.positive_seeds:
            from .models import RecommendationCandidate
            # Existing library models and provider records share metadata fields.
            seed_candidate = RecommendationCandidate(
                title=str(getattr(seed, "title", "") or ""),
                media_type=str(getattr(seed, "media_type", "") or ""),
                genres=tuple(getattr(seed, "genres", []) or ()),
                themes=tuple(getattr(seed, "themes", []) or ()),
                studios=tuple(getattr(seed, "studios", []) or ()),
                synopsis=str(getattr(seed, "synopsis", "") or ""),
            )
            text = content_text(seed_candidate)
            if text.strip():
                texts.append(text)
                weights.append(max(.05, _signals(seed)))
        if not texts:
            return {}
        seed_matrix = self.vectorizer.transform(texts)
        import numpy as np
        query = np.asarray(seed_matrix.multiply(np.asarray(weights)[:, None]).sum(axis=0)).reshape(1, -1)
        query = normalize(query)
        sims = np.asarray(self.matrix @ query.T).ravel()
        return {i: float(score) for i, score in enumerate(sims)}

    def retrieve(self, profile: UserPreferenceProfile, limit: int = 200):
        scores = self.similarities(profile)
        if not scores:
            return [(candidate, 0.0) for candidate in self.candidates[:max(0, limit)]]
        return sorted(((self.candidates[i], score) for i, score in scores.items()), key=lambda pair: (-pair[1], pair[0].title.casefold()))[:max(0, limit)]
