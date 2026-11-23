"""Transparent normalized weighted scoring and greedy MMR diversification."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
from .models import RecommendationCandidate, RecommendationExplanation, RecommendationOutput, UserPreferenceProfile

DEFAULT_WEIGHTS = {
    "genre_theme": .22, "seed_similarity": .20, "content_similarity": .13,
    "studio_metadata": .08, "format": .05, "relationship": .08,
    "quality": .06, "profile_activity": .10, "diversity": .08,
}


class RankerAdapter(Protocol):
    """Serving contract for a future learned reranker (e.g. LightGBM)."""
    def rank(self, candidates, profile: UserPreferenceProfile, similarities=None, limit: int = 50) -> list[RecommendationOutput]: ...


def _clamp(x):
    return max(0.0, min(1.0, float(x)))


def _overlap(values, weights):
    vals = {str(x).casefold() for x in values}
    denominator = sum(max(0.0, float(weight)) for weight in weights.values())
    return _clamp(sum(max(0.0, float(weight)) for key, weight in weights.items() if key.casefold() in vals) / denominator) if denominator else 0.0


def _seed_similarity(candidate, profile):
    similarities = []
    for seed in profile.positive_seeds:
        genres = {str(v).casefold() for v in (getattr(seed, "genres", []) or [])}
        themes = {str(v).casefold() for v in (getattr(seed, "themes", []) or [])}
        studios = {str(v).casefold() for v in (getattr(seed, "studios", []) or [])}
        c_genres = {str(v).casefold() for v in candidate.genres}
        c_themes = {str(v).casefold() for v in candidate.themes}
        c_studios = {str(v).casefold() for v in candidate.studios}
        def jaccard(left, right):
            return len(left & right) / len(left | right) if left or right else 0.0
        genre = jaccard(c_genres, genres)
        theme = jaccard(c_themes, themes)
        studio = jaccard(c_studios, studios)
        media = str(getattr(seed, "media_type", "") or "").casefold()
        fmt = 1.0 if media and media == candidate.media_type.casefold() else 0.0
        similarities.append(.55 * genre + .2 * theme + .15 * studio + .1 * fmt)
    return _clamp(max(similarities, default=0.0))


def _feature_values(candidate, profile, content_sim):
    genre = _overlap(candidate.genres, profile.positive_genres)
    theme = _overlap(candidate.themes, profile.themes)
    genre_theme = _clamp(.75 * genre + .25 * theme)
    negative = _overlap(candidate.genres, profile.negative_genres)
    genre_theme = _clamp(genre_theme - .5 * negative)
    year_similarity = 0.0
    if profile.release_year_center and candidate.release_year:
        year_similarity = _clamp(1.0 - abs(candidate.release_year - profile.release_year_center) / 25.0)
    studio = _clamp(.75 * _overlap(candidate.studios, profile.studios) + .25 * year_similarity)
    fmt = _overlap([candidate.media_type], profile.formats)
    seed_similarity = _seed_similarity(candidate, profile)
    content_similarity = content_sim
    relationship = _clamp(candidate.relationship_signal)
    # MAL quality is deliberately weak and normalized to a bounded scale.
    quality = _clamp(((candidate.score or 0) - 5.0) / 5.0) if candidate.score is not None else 0.0
    quality *= .65
    relevance = _clamp(.7 * genre_theme + .3 * content_sim)
    # Bounded per-item user feedback has a small profile-relevance effect.
    feedback_adjusted = _clamp(.5 + max(-.5, min(.5, candidate.feedback_signal)))
    profile_activity = _clamp(.8 * relevance + .2 * feedback_adjusted)
    return {"genre_theme": genre_theme, "seed_similarity": seed_similarity,
            "content_similarity": content_similarity, "studio_metadata": studio,
            "format": fmt, "relationship": relationship, "quality": quality,
            "profile_activity": profile_activity, "diversity": 0.0}, negative


@dataclass
class HybridRanker:
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    mmr_lambda: float = .82

    def __post_init__(self):
        if set(self.weights) != set(DEFAULT_WEIGHTS):
            raise ValueError("Weights must define every supported ranking feature exactly")
        if any(not isinstance(v, (int, float)) or v < 0 for v in self.weights.values()):
            raise ValueError("Ranking weights must be non-negative numbers")
        if abs(sum(self.weights.values()) - 1.0) > 1e-6:
            raise ValueError("Ranking weights must sum to 1")
        if not 0 <= self.mmr_lambda <= 1:
            raise ValueError("mmr_lambda must be in [0, 1]")

    def rank(self, candidates, profile: UserPreferenceProfile, similarities: dict[str, float] | None = None, limit: int = 50):
        similarities = similarities or {}
        scored = []
        for item in candidates:
            c = item if isinstance(item, RecommendationCandidate) else item[0]
            sim = item[1] if isinstance(item, tuple) else similarities.get(c.mal_id and f"mal:{c.mal_id}" or c.title.casefold(), 0.0)
            features, negative = _feature_values(c, profile, sim)
            raw = sum(self.weights[key] * features[key] for key in self.weights)
            features["negative_penalty"] = negative
            reasons = []
            if features["genre_theme"] > .12: reasons.append("Matches genres or themes you rate positively")
            if sim > .12: reasons.append("Content resembles your positively engaged titles")
            if features["studio_metadata"] > 0: reasons.append("Matches studios in your positive history")
            if features["format"] > 0: reasons.append(f"Matches your preferred {c.media_type} format")
            if negative > .2: reasons.append("Down-ranked for genres associated with negative feedback")
            if features["relationship"] > .15: reasons.append("Related to a positively engaged title")
            if not reasons: reasons.append("Best available match across your profile signals")
            scored.append((c, raw, features, reasons))
        chosen, remaining = [], list(scored)
        while remaining and len(chosen) < max(0, limit):
            best = None
            for row in remaining:
                c, relevance, feats, reasons = row
                redundancy = max((_candidate_similarity(c, selected[0]) for selected in chosen), default=0.0)
                diversity = 1.0 - redundancy
                mmr = self.mmr_lambda * relevance + (1.0 - self.mmr_lambda) * diversity
                adjusted = relevance + self.weights["diversity"] * (diversity - .5)
                key = (mmr, adjusted, c.title.casefold())
                if best is None or key > best[0]:
                    best = (key, row, diversity, adjusted)
            remaining.remove(best[1])
            c, _, features, reasons = best[1]
            features = dict(features, diversity=best[2])
            chosen.append((c, best[3], features, reasons))
        return [RecommendationOutput(c, RecommendationExplanation(_clamp(score), features, tuple(reasons)), cached=bool(c.metadata.get("is_cached", False))) for c, score, features, reasons in chosen]


def _candidate_similarity(a: RecommendationCandidate, b: RecommendationCandidate) -> float:
    ga, gb = {x.casefold() for x in a.genres}, {x.casefold() for x in b.genres}
    sa, sb = {x.casefold() for x in a.studios}, {x.casefold() for x in b.studios}
    def jaccard(x, y): return len(x & y) / len(x | y) if x or y else 0.0
    return _clamp(.75 * jaccard(ga, gb) + .25 * jaccard(sa, sb))
