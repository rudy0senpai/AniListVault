"""Deterministic offline ranking metrics for trusted test/evaluation fixtures."""
from __future__ import annotations
import math


def precision_at_k(recommended, relevant, k):
    if k <= 0: return 0.0
    return sum(x in set(relevant) for x in list(recommended)[:k]) / k


def recall_at_k(recommended, relevant, k):
    rel = set(relevant)
    return sum(x in rel for x in list(recommended)[:max(0, k)]) / len(rel) if rel else 0.0


def ndcg_at_k(recommended, relevance, k):
    relevance = dict(relevance)
    dcg = sum((2 ** max(0.0, float(relevance.get(x, 0))) - 1) / math.log2(i + 2)
              for i, x in enumerate(list(recommended)[:max(0, k)]))
    ideal = sorted((max(0.0, float(v)) for v in relevance.values()), reverse=True)[:max(0, k)]
    idcg = sum((2 ** value - 1) / math.log2(i + 2) for i, value in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def catalog_coverage(recommended, catalogue):
    catalog = set(catalogue)
    return len(set(recommended) & catalog) / len(catalog) if catalog else 0.0


def duplicate_rate(recommended):
    rows = list(recommended)
    return (len(rows) - len(set(rows))) / len(rows) if rows else 0.0


def owned_item_leakage(recommended, owned):
    rows = list(recommended)
    return sum(item in set(owned) for item in rows) / len(rows) if rows else 0.0


def intra_list_diversity(items, similarity):
    rows = list(items)
    pairs = [(a, b) for i, a in enumerate(rows) for b in rows[i + 1:]]
    return 1.0 - sum(float(similarity(a, b)) for a, b in pairs) / len(pairs) if pairs else 0.0
