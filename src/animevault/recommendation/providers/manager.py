"""Provider fan-out with fault isolation and normalized discovery batches."""
from __future__ import annotations
from .jikan import DiscoveryBatch, _error


class ProviderManager:
    def __init__(self, providers=()):
        self.providers = list(providers)

    def discover(self, profile, **limits):
        candidates, errors, stats = [], [], {}
        for provider in self.providers:
            try:
                batch = provider.discover(profile, **limits)
                candidates.extend(batch.candidates)
                errors.extend(batch.errors)
                stats[provider.__class__.__name__] = batch.stats
            except Exception as exc:
                errors.append(_error(provider.__class__.__name__, exc))
        return DiscoveryBatch(tuple(candidates), tuple(errors), stats)
