"""Construct a signed, evidence-normalized profile from library rows."""
from __future__ import annotations

import math
from collections import defaultdict
from statistics import mean
from animevault.services.title_norm import normalize_title
from .models import UserPreferenceProfile

_TIER = {"SSS": 1.0, "SS": .95, "S": .9, "A": .75, "B": .55,
         "C": .25, "D": -.35, "E": -.65, "F": -1.0}


def _value(item, name, default=None):
    value = getattr(item, name, default)
    return value() if callable(value) else value


def _key(item):
    domain = "literature" if str(_value(item, "category", "") or "").casefold() in {"manga", "manhwa", "manhua"} else "anime"
    for field in ("anilist_id", "mal_id", "kitsu_id", "tmdb_id"):
        value = _value(item, field)
        if value:
            return domain, field, str(value).casefold()
    return domain, "title", normalize_title(str(_value(item, "title", ""))), str(_value(item, "media_type", "") or _value(item, "category", "")).casefold()


def _signals(item) -> float:
    status = str(_value(item, "status", "") or "").casefold().replace(" ", "_")
    if status == "plan_to_watch":
        return 0.0
    tier = _TIER.get(str(_value(item, "tier", "") or "").upper())
    raw_rating = _value(item, "score")
    rating = None
    if isinstance(raw_rating, (int, float)) and not isinstance(raw_rating, bool) and 0 <= raw_rating <= 10:
        rating = (float(raw_rating) - 5.0) / 5.0
    activity = {"completed": .45, "watching": .3, "on_hold": .05, "dropped": -.8}.get(status, 0.0)
    explicit = [x for x in (tier, rating) if x is not None]
    signal = (.8 * mean(explicit) + .2 * activity) if explicit else activity
    favorite = bool(_value(item, "favorite", False))
    # Explicit strong rating/tier or favorite wins the dropped-status conflict.
    if status == "dropped" and not (favorite or (rating is not None and rating >= .6) or (tier is not None and tier >= .75)):
        signal = min(signal, -.75)
    if favorite:
        signal = max(signal, .9)
    return max(-1.0, min(1.0, signal))


def _normalize(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    total = sum(abs(v) for v in values.values())
    if not total:
        return {}
    # Mean evidence per feature, scaled to [0, 1], not raw library frequency.
    peak = max(abs(v) for v in values.values())
    return {k: min(1.0, abs(v) / peak) for k, v in sorted(values.items()) if v and peak}


def build_profile(items) -> UserPreferenceProfile:
    unique = {}
    for item in items:
        key = _key(item)
        old = unique.get(key)
        if old is None or abs(_signals(item)) > abs(_signals(old)):
            unique[key] = item
    rows = list(unique.values())
    positive, negative, studios, formats, years, tiers = [defaultdict(float) for _ in range(6)]
    rating_values = []
    positive_seeds, negative_seeds = [], []
    genre_evidence = studio_evidence = rating_evidence = 0
    for item in rows:
        signal = _signals(item)
        genres = {str(x).strip().casefold() for x in (_value(item, "genres", []) or []) if str(x).strip()}
        themes = {str(x).strip().casefold() for x in (_value(item, "themes", []) or []) if str(x).strip()}
        if signal:
            genre_evidence += bool(genres)
            target = positive if signal > 0 else negative
            for genre in genres:
                target[genre] += abs(signal) / math.sqrt(max(1, len(genres)))
            if signal > 0:
                for theme in themes:
                    positive["theme:" + theme] += signal / math.sqrt(max(1, len(themes)))
                for studio in (_value(item, "studios", []) or []):
                    if str(studio).strip():
                        studios[str(studio).strip().casefold()] += signal
                media = str(_value(item, "media_type", "") or "").strip().upper()
                if media:
                    formats[media] += signal
                year_value = _value(item, "season_year")
                if not year_value:
                    aired = str(_value(item, "aired_from", "") or "")
                    year_value = aired[:4] if len(aired) >= 4 else None
                try:
                    if year_value and 1900 <= int(year_value) <= 2100:
                        years[int(year_value)] += signal
                except (ValueError, TypeError):
                    pass
            tier = str(_value(item, "tier", "") or "").upper()
            if tier in _TIER:
                tiers[tier] += max(0.0, signal)
            raw_rating = _value(item, "score")
            if isinstance(raw_rating, (int, float)) and not isinstance(raw_rating, bool) and 0 <= raw_rating <= 10:
                rating_values.append(float(raw_rating))
                rating_evidence += 1
        if signal >= .35:
            positive_seeds.append(item)
        elif signal <= -.35:
            negative_seeds.append(item)
    genres = {k: v for k, v in positive.items() if not k.startswith("theme:")}
    themes = {k.removeprefix("theme:"): v for k, v in positive.items() if k.startswith("theme:")}
    year_center = None
    if years:
        year_center = sum(year * weight for year, weight in years.items()) / sum(years.values())
    confidence = {
        "genres": min(1.0, genre_evidence / 8.0),
        "themes": min(1.0, len(themes) / 4.0),
        "studios": min(1.0, len(studios) / 5.0),
        "formats": min(1.0, sum(formats.values()) / 6.0),
        "ratings": min(1.0, rating_evidence / 5.0),
    }
    active = [item for item in rows if str(_value(item, "status", "") or "").casefold().replace(" ", "_") != "plan_to_watch"]
    watched_episodes = sum(max(0, int(_value(item, "episodes_watched", 0) or 0)) for item in active)
    total_episodes = sum(max(0, int(_value(item, "episodes", 0) or 0)) for item in active)
    completed_count = sum(str(_value(item, "status", "") or "").casefold() == "completed" for item in rows)
    dropped_count = sum(str(_value(item, "status", "") or "").casefold() == "dropped" for item in rows)
    on_hold_count = sum(str(_value(item, "status", "") or "").casefold() == "on_hold" for item in rows)
    favorite_count = sum(bool(_value(item, "favorite", False)) for item in rows)
    rewatch_count = sum(max(0, int(_value(item, "rewatches", 0) or 0)) for item in rows)
    profile = UserPreferenceProfile(
        positive_genres=_normalize(genres), negative_genres=_normalize(negative),
        themes=_normalize(themes), studios=_normalize(dict(studios)),
        formats=_normalize(dict(formats)), release_year_center=year_center,
        rating_mean=mean(rating_values) if rating_values else None,
        rating_count=rating_evidence,
        completion_rate=completed_count / max(1, len(active)),
        watched_episodes=watched_episodes, total_episodes=total_episodes,
        dropped_count=dropped_count, on_hold_count=on_hold_count,
        rewatch_count=rewatch_count, favorite_count=favorite_count,
        tier_affinity=_normalize(dict(tiers)),
        engagement={"library_items": float(len(rows)), "positive_items": float(len(positive_seeds)),
                    "negative_items": float(len(negative_seeds)), "completed": float(completed_count),
                    "dropped": float(dropped_count), "on_hold": float(on_hold_count)},
        positive_seeds=tuple(positive_seeds), negative_seeds=tuple(negative_seeds), confidence=confidence,
    )
    return profile
