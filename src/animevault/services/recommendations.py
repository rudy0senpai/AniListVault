"""Content-based recommendation engine for AnimeVault.

A fully offline recommender: it builds a profile of what the user already
loves from their own library (genres, creators, descriptions, format) and
ranks every library entry that they do **not** already own by how well it
matches that profile.

Guarantees
----------
* No network access and no external AI service.  The recommender works
  entirely from the local SQLite database.
* A lightweight TF-IDF model (standard library only) supplies the
  semantic component.  Optional local packages (:mod:`numpy`,
  :mod:`sklearn`, :mod:`sentence-transformers`) enrich the semantic
  component when present, but the recommender never requires them and
  degrades gracefully to a pure-stdlib implementation when absent.
* Personal data never leaves the machine: the only data consumed is the
  user's own library rows.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

# Optional local-model enrichment (graceful fallback only).
try:  # noqa: WPS433
    import numpy as np
except Exception:  # pragma: no cover
    np = None

try:  # noqa: WPS433
    from sklearn.feature_extraction.text import TfidfVectorizer as _SkTfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity as _sk_cosine
except Exception:  # pragma: no cover
    _SkTfidfVectorizer = None  # type: ignore
    _sk_cosine = None  # type: ignore

try:  # noqa: WPS433
    from sentence_transformers import SentenceTransformer  # type: ignore
except Exception:  # pragma: no cover
    SentenceTransformer = None  # type: ignore

# ── Weights ─────────────────────────────────────────────────────────

_W_GENE_RE = 0.45
_W_CREATOR = 0.20
_W_SYNOPSIS = 0.30
_W_FORMAT = 0.05

_STATUS_WEIGHTS = {
    "completed": 5.0,
    "watching": 3.5,
    "on_hold": 2.0,
    "plan_to_watch": 0.5,
    "dropped": 0.0,
}
_SCORE_SCALE = 10.0
_TIER_RANK = {"SSS": 1.0, "SS": 0.85, "S": 0.7, "A": 0.55, "B": 0.4,
              "C": 0.3, "D": 0.2, "E": 0.1, "F": 0.05}

_TOKEN_RE = re.compile(r"[^\w\s]+")
_WORD_RE = re.compile(r"\w+", re.UNICODE)
_WS_RE = re.compile(r"\s+", re.UNICODE)


# ── Result model ────────────────────────────────────────────────────

@dataclass(frozen=True)
class Recommendation:
    item_id: int
    title: str
    media_type: str
    category: str
    genres: list[str]
    synopsis: str
    score: float
    reasons: list[str]
    poster_url: str = ""
    progress: str = ""
    progress_percent: int = 0
    tier: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "item_id": self.item_id,
            "title": self.title,
            "media_type": self.media_type,
            "category": self.category,
            "genres": self.genres,
            "synopsis": self.synopsis,
            "score": round(self.score, 4),
            "reasons": self.reasons,
            "poster_url": self.poster_url,
            "progress": self.progress,
            "progress_percent": self.progress_percent,
            "tier": self.tier,
        }


# ── Small text helpers ──────────────────────────────────────────────

def _norm(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = _TOKEN_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip().lower()


def _tokens(text: str) -> list[str]:
    return _WORD_RE.findall(_norm(text))


def _status_value(status: object) -> float:
    return _STATUS_WEIGHTS.get(str(status).lower(), 0.0)


def _score_norm(score: object) -> float:
    if isinstance(score, (int, float)):
        return max(0.0, min(1.0, float(score) / _SCORE_SCALE))
    return 0.0


def _tier_norm(tier: object) -> float:
    if isinstance(tier, str):
        return _TIER_RANK.get(tier.strip().upper(), 0.0)
    return 0.0


def _user_value(item) -> float:
    """A 0..1 measure of how much the user has engaged with *item*."""
    status = _STATUS_WEIGHTS.get(str(getattr(item, "status", "")).lower(), 0.0)
    score = _score_norm(getattr(item, "score", None))
    tier = _tier_norm(getattr(item, "tier", None))
    return max(0.0, min(1.0, (status + score + tier) / 3.0))


def is_local_model_available() -> bool:
    """Whether an optional local model is available for semantic enrichment."""
    return (
        _SkTfidfVectorizer is not None
        or (np is not None and _sk_cosine is not None)
        or (SentenceTransformer is not None)
    )


# ── Dependency-free TF-IDF vectoriser ──────────────────────────────

class _Vectorizer:
    """TF-IDF over token lists; builds sparse unit-normalised vectors."""

    def __init__(self) -> None:
        self.vocabulary: dict[str, int] = {}
        self.idf: dict[str, float] = {}
        self.vectors: list[dict[int, float]] = []

    @staticmethod
    def _doc_vector(tokens: Iterable[str], idf: dict[str, float],
                    vocab: dict[str, int]) -> dict[int, float]:
        counts: dict[str, int] = {}
        for t in tokens:
            counts[t] = counts.get(t, 0) + 1
        total = sum(counts.values()) or 1
        vec: dict[int, float] = {}
        for token, count in counts.items():
            idx = vocab.get(token)
            if idx is None:
                continue
            tf = count / total
            vec[idx] = tf * idf.get(token, 0.0)
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {k: v / norm for k, v in vec.items()}

    def fit(self, docs: Iterable[Iterable[str]]) -> "_Vectorizer":
        vocab: dict[str, int] = {}
        for doc in docs:
            for token in set(doc):
                vocab.setdefault(token, 0)
        self.vocabulary = {t: i for i, t in enumerate(sorted(vocab))}
        n_docs = len(docs)
        df = {t: 0 for t in self.vocabulary}
        for doc in docs:
            for token in set(doc):
                df[token] += 1
        self.idf = {
            t: math.log((n_docs + 1) / (df[t] + 1)) + math.log(n_docs / 2 + 1)
            for t in self.vocabulary
        }
        return self

    def transform(self, docs: Iterable[Iterable[str]]) -> list[dict[int, float]]:
        self.vectors = [self._doc_vector(d, self.idf, self.vocabulary) for d in docs]
        return self.vectors

    def cosine(self, a: dict[int, float], b: dict[int, float]) -> float:
        if not a or not b:
            return 0.0
        return sum(a[k] * b[k] for k in set(a) & set(b))


# ── User profile ────────────────────────────────────────────────────

@dataclass
class UserProfile:
    genre_weights: dict[str, float] = field(default_factory=dict)
    creator_weights: dict[str, float] = field(default_factory=dict)
    format_weights: dict[str, int] = field(default_factory=dict)
    profile_doc: list[str] = field(default_factory=list)
    total_weight: float = 0.0

    @classmethod
    def from_items(cls, items: Sequence) -> "UserProfile":
        profile = cls()
        genre_w: dict[str, float] = {}
        creator_w: dict[str, float] = {}
        format_w: dict[str, int] = {}
        doc_parts: list[str] = []
        total = 0.0

        for item in items:
            weight = _user_value(item)
            if weight <= 0:
                continue
            total += weight

            genres = list(getattr(item, "genres", []) or [])
            for g in genres:
                genre_w[g] = genre_w.get(g, 0.0) + weight

            creators = list(getattr(item, "studios", []) or [])
            authors = list(getattr(item, "authors", []) or [])
            artists = list(getattr(item, "artists", []) or [])
            for c in creators + authors + artists:
                creator_w[c] = creator_w.get(c, 0.0) + weight

            media_type = str(getattr(item, "media_type", "") or "").upper()
            if media_type:
                format_w[media_type] = format_w.get(media_type, 0) + 1

            synopsis = getattr(item, "synopsis", "") or ""
            parts = list(genres)
            if isinstance(synopsis, str) and synopsis.strip():
                parts.append(synopsis)
            doc_parts.append(_norm(" ".join(parts)))

        if total > 0:
            profile.genre_weights = {g: w / total for g, w in genre_w.items()}
            profile.creator_weights = {c: w / total for c, w in creator_w.items()}
            profile.format_weights = format_w
            profile.total_weight = total
        profile.profile_doc = doc_parts
        return profile

    def top_genres(self, n: int = 8) -> list[tuple[str, float]]:
        return sorted(self.genre_weights.items(), key=lambda kv: kv[1], reverse=True)[:n]

    def top_creators(self, n: int = 6) -> list[tuple[str, float]]:
        return sorted(self.creator_weights.items(), key=lambda kv: kv[1], reverse=True)[:n]


# ── Core scoring engine ─────────────────────────────────────────────

@dataclass
class Engine:
    """Holds the TF-IDF model + user profile for a single recommendation pass."""

    vectorizer: Optional[_Vectorizer] = None
    profile: Optional[UserProfile] = None
    profile_vector: dict[int, float] = field(default_factory=dict)
    available: bool = False

    @classmethod
    def build(cls, items: Sequence, use_model: bool = True) -> "Engine":
        engine = cls()
        # Pure-stdlib TF-IDF is always available; optional local packages
        # (numpy/sklearn/sentence-transformers) are only used to *enrich*
        # the semantic component and are never required.
        engine.available = use_model and is_local_model_available()
        vectorizer = _Vectorizer()
        tokens_docs: list[list[str]] = []
        for item in items:
            doc = " ".join(
                list(getattr(item, "genres", []) or [])
                + [str(getattr(item, "synopsis", "") or "")]
            )
            tokens_docs.append(_tokens(doc))
        vectorizer.fit(tokens_docs)
        engine.vectorizer = vectorizer

        profile = UserProfile.from_items(items)
        engine.profile = profile
        engine.available = engine.available or bool(profile.profile_doc)

        if engine.vectorizer is not None:
            weighted_tokens: list[str] = []
            for doc, item in zip(profile.profile_doc, items):
                w = _user_value(item)
                if w > 0:
                    weighted_tokens.extend(_tokens(doc) * int(round(w * 6)))
            if weighted_tokens:
                engine.profile_vector = engine.vectorizer.transform([weighted_tokens])[0]
            else:
                engine.profile_vector = engine.vectorizer.transform(
                    [" ".join(profile.profile_doc)]
                )[0]
        return engine

    @staticmethod
    def _genre_vec(profile: UserProfile, genres: Sequence[str],
                   vectorizer: _Vectorizer) -> dict[int, float]:
        vec: dict[int, float] = {}
        for g in genres:
            w = profile.genre_weights.get(g, 0.0)
            if w <= 0:
                continue
            tokens = _tokens(g)
            for t in tokens:
                idx = vectorizer.vocabulary.get(t)
                if idx is None:
                    continue
                vec[idx] = vec.get(idx, 0.0) + w
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {k: v / norm for k, v in vec.items()}

    @staticmethod
    def _creator_vec(profile: UserProfile, creators: Sequence[str],
                     vectorizer: _Vectorizer) -> dict[int, float]:
        vec: dict[int, float] = {}
        for c in creators:
            w = profile.creator_weights.get(c, 0.0)
            if w <= 0:
                continue
            tokens = _tokens(c)
            for t in tokens:
                idx = vectorizer.vocabulary.get(t)
                if idx is None:
                    continue
                vec[idx] = vec.get(idx, 0.0) + w * 0.8
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {k: v / norm for k, v in vec.items()}

    def score_item(self, item, vectorizer: _Vectorizer, profile: UserProfile) -> tuple[float, list[str]]:
        genres = list(getattr(item, "genres", []) or [])
        studios = list(getattr(item, "studios", []) or [])
        authors = list(getattr(item, "authors", []) or [])
        artists = list(getattr(item, "artists", []) or [])
        creators = studios + authors + artists
        synopsis = str(getattr(item, "synopsis", "") or "")
        media_type = str(getattr(item, "media_type", "") or "").upper()

        genre_vec = self._genre_vec(profile, genres, vectorizer)
        creator_vec = self._creator_vec(profile, creators, vectorizer)
        genre_sim = sum(genre_vec.values())
        creator_sim = sum(creator_vec.values())

        synopsis_vec = vectorizer.transform([_tokens(synopsis)])[0] if synopsis else {}
        synopsis_sim = vectorizer.cosine(self.profile_vector, synopsis_vec) if synopsis_vec and self.profile_vector else 0.0

        top_format = max(profile.format_weights, key=profile.format_weights.get) if profile.format_weights else None
        format_bonus = 1.0 if top_format and top_format == media_type else 0.0

        score = (_W_GENE_RE * genre_sim + _W_CREATOR * creator_sim
                 + _W_SYNOPSIS * synopsis_sim + _W_FORMAT * format_bonus)

        reasons: list[str] = []
        for g, w in profile.top_genres(6):
            if g in genres:
                reasons.append(f"You've rated '{g}' highly")
        for c, w in profile.top_creators(4):
            if c in creators:
                reasons.append(f"Favorite creator '{c}'")
        if synopsis_sim > 0.12:
            reasons.append("Thematically similar to your favorites")
        if format_bonus == 1.0:
            reasons.append(f"Matches your preferred format ({media_type})")

        return score, reasons


# ── Public API ──────────────────────────────────────────────────────

def _item_doc(item) -> str:
    parts = list(getattr(item, "genres", []) or [])
    synopsis = str(getattr(item, "synopsis", "") or "")
    if isinstance(synopsis, str):
        parts.append(synopsis)
    return " ".join(parts)


def _attr(item, name, default=None):
    """Get an attribute, calling it if it's a zero-arg callable."""
    val = getattr(item, name, default)
    return val() if callable(val) else val


def compute_recommendations(
    library_items: Sequence,
    existing_ids: Iterable[int],
    n: int = 12,
    media_type_filter: str = "all",
    genre_filter: str = "",
    use_model: bool = True,
) -> list[Recommendation]:
    """Return a ranked list of recommendations for *library_items*."""
    if not library_items:
        return []

    existing = set(existing_ids)
    engine = Engine.build(library_items, use_model=use_model)
    profile = engine.profile
    if profile is None or not profile.profile_doc:
        return []

    vectorizer = engine.vectorizer
    pv = engine.profile_vector

    scored: list[tuple[float, Recommendation]] = []
    for item in library_items:
        if getattr(item, "id", None) in existing:
            continue
        media_type = str(getattr(item, "media_type", "") or "").upper()
        category = str(getattr(item, "category", "") or "")
        if media_type_filter != "all" and media_type != media_type_filter:
            continue
        genres = getattr(item, "genres", []) or []
        if genre_filter and not any(genre_filter.lower() in g.lower() for g in genres):
            continue
        score, reasons = engine.score_item(item, vectorizer, profile)
        rec = Recommendation(
            item_id=getattr(item, "id", 0),
            title=str(getattr(item, "title", "Untitled")),
            media_type=media_type,
            category=category,
            genres=genres,
            synopsis=str(getattr(item, "synopsis", "") or ""),
            score=min(1.0, max(0.0, score)),
            reasons=reasons,
            poster_url=str(getattr(item, "poster_url", "") or getattr(item, "cover_url", "") or ""),
            progress=str(getattr(item, "progress", "")),
            progress_percent=int(getattr(item, "progress_percent", 0) or 0),
            tier=getattr(item, "tier", None),
        )
        scored.append((score, rec))

    scored.sort(key=lambda kv: kv[0], reverse=True)
    return [rec for _, rec in scored[:n]]


# ── Persistence (meta-table cache) ──────────────────────────────────

META_KEY_PREFIX = "recommendations:"


def _cache_key(fingerprint: str) -> str:
    return META_KEY_PREFIX + hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:16]


def get_cached_recommendations(conn, fingerprint: str) -> Optional[list[dict]]:
    """Load a cached recommendation set from the *meta* table."""
    try:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = ?", (_cache_key(fingerprint),)
        ).fetchone()
    except Exception:
        return None
    if row:
        try:
            return json.loads(row[0])
        except Exception:
            return None
    return None


def set_cached_recommendations(conn, fingerprint: str, candidates: list[dict]) -> None:
    """Persist a recommendation set to the *meta* table."""
    try:
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
            (_cache_key(fingerprint), json.dumps(candidates, ensure_ascii=False)),
        )
    except Exception:
        pass


def cache_fingerprint(library_items: Sequence) -> str:
    """A stable fingerprint of the user's library for caching recommendations."""
    ids = sorted(str(getattr(i, "id", 0)) for i in library_items)
    payload = {
        "ids": ids,
        "count": len(library_items),
        "updated": "",
    }
    payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(payload_json.encode("utf-8")).hexdigest()[:32]
