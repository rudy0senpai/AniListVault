"""Anime similarity calculations.

Computes how similar two anime are along several dimensions:

* Title similarity — token overlap, typed-title match, romaji/Japanese match.
* Metadata similarity — genres, studios, source provider, media type, season.
* Embedding similarity — optional local TF-IDF / sentence-transformer model
  (graceful fallback to a token-overlap metric).

All similarity values are in [0.0, 1.0]; 1.0 = identical.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

# Optional local-model packages (enrichment only, never required).
try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None

try:
    from sklearn.feature_extraction.text import TfidfVectorizer as _SkTfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity as _sk_cosine
except Exception:  # pragma: no cover
    _SkTfidfVectorizer = None  # type: ignore
    _sk_cosine = None  # type: ignore

try:
    from sentence_transformers import SentenceTransformer  # type: ignore
except Exception:  # pragma: no cover
    SentenceTransformer = None  # type: ignore

# Regexes used for tokenisation.
_TOKEN_RE = re.compile(r"[^\w\s]+")
_WORD_RE = re.compile(r"\w+", re.UNICODE)
_WS_RE = re.compile(r"\s+", re.UNICODE)

# Genres that map to the Isekai category.
_ISEKAI_GENRES = {
    "isekai", "fantasy", "adventure", "dungeon", "reincarnation",
    "cheat", "saint", "ruler", "cursed", "magic",
}

# Canonical genres mapped to broader categories.
_CATEGORY_MAP: dict[str, str] = {
    "isekai": "isekai",
    "fantasy": "fantasy",
    "adventure": "adventure",
    "romance": "romance",
    "comedy": "comedy",
    "mystery": "mystery",
    "horror": "horror",
    "psychological": "psychological",
    "sci-fi": "sci-fi",
    "slice of life": "slice_of_life",
    "drama": "drama",
    "supernatural": "supernatural",
    "sports": "sports",
    "thriller": "thriller",
    "seinen": "seinen",
    "shoujo": "shoujo",
    "shounen": "shounen",
    "school": "school",
    "josei": "josei",
    "action": "action",
}


def _norm(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = _TOKEN_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip().lower()


def _tokens(text: str) -> list[str]:
    return _WORD_RE.findall(_norm(text))


def _token_overlap(a: str, b: str) -> float:
    """Jaccard similarity over tokenised words."""
    ta, tb = set(_tokens(a)), set(_tokens(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _typed_title_match(a, b) -> float:
    """Exact match on canonical title, title_en, romaji, or Japanese title."""
    ta = [str(getattr(a, "title", "")), str(getattr(a, "title_en", "")),
          str(getattr(a, "title_romaji", "")), str(getattr(a, "title_ja", ""))]
    tb = [str(getattr(b, "title", "")), str(getattr(b, "title_en", "")),
          str(getattr(b, "title_romaji", "")), str(getattr(b, "title_ja", ""))]
    for x in ta:
        if not x:
            continue
        for y in tb:
            if not y:
                continue
            if x == y:
                return 1.0
            if _norm(x) == _norm(y):
                return 1.0
    return 0.0


def _metadata_similarity(a, b) -> float:
    """Overlap of genres, studios, and other classification fields."""
    def _vec(obj):
        genres = set(str(getattr(obj, "genres", []) or []))
        studios = set(str(getattr(obj, "studios", []) or []))
        authors = set(str(getattr(obj, "authors", []) or []))
        artists = set(str(getattr(obj, "artists", []) or []))
        return genres | studios | authors | artists

    va, vb = _vec(a), _vec(b)
    if not va and not vb:
        return 1.0
    if not va or not vb:
        return 0.0
    intersection = len(va & vb)
    union = len(va | vb)
    return intersection / union if union else 0.0


def _format_similarity(a, b) -> float:
    ta = str(getattr(a, "media_type", "") or "").strip().lower()
    tb = str(getattr(b, "media_type", "") or "").strip().lower()
    if ta and tb:
        return 1.0 if ta == tb else 0.5
    if not ta and not tb:
        return 1.0
    return 0.0


def _category_similarity(a, b) -> float:
    """Compare broad categories (e.g. Isekai vs. action)."""
    def _cat(obj):
        raw = set(str(getattr(obj, "genres", []) or []))
        cats = {_CATEGORY_MAP.get(g.strip().lower(), g.strip().lower()) for g in raw}
        return cats

    ca, cb = _cat(a), _cat(b)
    if not ca and not cb:
        return 1.0
    if not ca or not cb:
        return 0.0
    intersection = len(ca & cb)
    union = len(ca | cb)
    return intersection / union if union else 0.0


def _titled_title_similarity(a, b) -> float:
    return _token_overlap(str(getattr(a, "title", "") or ""), str(getattr(b, "title", "") or ""))


def _synopsis_similarity(a, b) -> float:
    """TF-IDF cosine similarity over synopsis text (if local model available)."""
    sa = str(getattr(a, "synopsis", "") or "")
    sb = str(getattr(b, "synopsis", "") or "")
    if not sa and not sb:
        return 0.0
    if not sa or not sb:
        return 0.0

    # Pure-stdlib TF-IDF fallback.
    if _SkTfidfVectorizer is not None and _sk_cosine is not None:
        vec = _SkTfidfVectorizer().fit([sa, sb])
        sim = _sk_cosine(vec.transform([sa]), vec.transform([sb]))[0][0]
        return min(1.0, max(0.0, float(sim)))

    # Token-overlap fallback.
    return _token_overlap(sa, sb)


def _embedding_similarity(a, b) -> float:
    """Sentence-transformer embedding similarity (optional)."""
    if SentenceTransformer is None:
        return 0.0
    try:
        # Build a tiny corpus from the two synopses + titles + genres.
        corpus = [
            str(getattr(a, "title", "") or "") or "unknown",
            str(getattr(a, "synopsis", "") or "") or "",
            str(getattr(b, "title", "") or "") or "unknown",
            str(getattr(b, "synopsis", "") or "") or "",
        ]
        model = SentenceTransformer("all-MiniLM-L6-v2")
        embeddings = model.encode(corpus)
        sim = float(np.dot(embeddings[0], embeddings[2]) /
                     (np.linalg.norm(embeddings[0]) * np.linalg.norm(embeddings[2]) + 1e-9))
        return min(1.0, max(0.0, sim))
    except Exception:
        return 0.0


@dataclass(frozen=True)
class SimilarityScore:
    """Similarity between two anime.

    Attributes
    ----------
    title:
        Token-overlap on titles.
    typed_title:
        Exact canonical-title match.
    metadata:
        Overlap of genres / studios / authors / artists.
    format:
        Media-type match.
    category:
        Broad category overlap.
    synopsis:
        Synopsis text similarity.
    embedding:
        Optional embedding similarity.
    total:
        Weighted overall similarity in [0.0, 1.0].
    """
    title: float = 0.0
    typed_title: float = 0.0
    metadata: float = 0.0
    format: float = 0.0
    category: float = 0.0
    synopsis: float = 0.0
    embedding: float = 0.0

    @property
    def total(self) -> float:
        return (0.30 * self.title + 0.20 * self.typed_title
                + 0.25 * self.metadata + 0.10 * self.format
                + 0.10 * self.category + 0.05 * self.synopsis)


def anime_similarity(a, b) -> SimilarityScore:
    """Return a full similarity breakdown between two anime."""
    score = SimilarityScore(
        title=_titled_title_similarity(a, b),
        typed_title=_typed_title_match(a, b),
        metadata=_metadata_similarity(a, b),
        format=_format_similarity(a, b),
        category=_category_similarity(a, b),
        synopsis=_synopsis_similarity(a, b),
        embedding=_embedding_similarity(a, b),
    )
    return score


def category_similarity(a, b, category: str) -> float:
    """Return how well two anime belong to a specific category (e.g. Isekai)."""
    if category == "isekai":
        def _isekai(obj):
            raw = set(str(getattr(obj, "genres", []) or []))
            return bool(raw & _ISEKAI_GENRES)
        return 1.0 if _isekai(a) and _isekai(b) else 0.0
    return _category_similarity(a, b)
