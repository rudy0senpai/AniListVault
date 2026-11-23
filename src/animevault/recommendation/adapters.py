"""Stable extension contracts for optional retrieval and ranking backends."""
from __future__ import annotations
from typing import Protocol, Sequence
from .models import RecommendationCandidate, RecommendationOutput, UserPreferenceProfile


class CandidateRetriever(Protocol):
    def retrieve(self, profile: UserPreferenceProfile, limit: int = 200) -> Sequence[RecommendationCandidate]: ...


class CandidateProvider(Protocol):
    def discover(self, profile: UserPreferenceProfile, limit: int = 100) -> Sequence[RecommendationCandidate]: ...


class RecommendationRanker(Protocol):
    def rank(self, candidates, profile: UserPreferenceProfile, *, limit: int = 50) -> Sequence[RecommendationOutput]: ...


class OptionalModelAdapter(Protocol):
    """Future LightGBM/two-tower/BERT4Rec adapter; no model is bundled now."""
    name: str
    def is_available(self) -> bool: ...
    def score(self, candidates, profile: UserPreferenceProfile) -> Sequence[float]: ...
