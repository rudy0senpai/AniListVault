"""Pure-Python stats for the AnimeVault dashboard (no Qt imports, easy to test).

Each record may be a dict or an object with these (all optional) fields:
id, title, media_type (anime|manga|manhwa|manhua), format, status, tier,
favorite, progress, total, genres (list[str]), year, score,
first_date, last_date, completed_date (ISO strings or date objects).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import date, datetime, timedelta

MEDIA = ("anime", "manga", "manhwa", "manhua", "unknown")
STATUSES = (("planned", "Planned"), ("active", "In progress"), ("done", "Completed"),
            ("hold", "On hold"), ("dropped", "Dropped"), ("unknown", "Unknown"))
TIER_ORDER = ("SSS", "SS", "S", "A", "B", "C", "D", "E", "F")
DATE_FIELDS = (("first_date", "Started"), ("last_date", "Last progress"), ("completed_date", "Completed"))
DATE_WINDOWS = {"30d": 30, "90d": 90, "365d": 365}

_ALIASES = {
    "planned": "planned", "plan to watch": "planned", "plan to read": "planned", "planning": "planned",
    "active": "active", "in progress": "active", "watching": "active", "reading": "active",
    "current": "active", "rewatching": "active", "rereading": "active", "repeating": "active",
    "done": "done", "completed": "done",
    "hold": "hold", "on hold": "hold", "paused": "hold",
    "dropped": "dropped",
}


def _get(rec, key, default=None):
    value = rec.get(key, default) if isinstance(rec, Mapping) else getattr(rec, key, default)
    return default if value is None else value


def norm_status(value) -> str:
    return _ALIASES.get(str(value or "").strip().lower().replace("_", " "), "unknown")


def norm_media(value) -> str:
    v = str(value or "").strip().lower()
    return v if v in MEDIA[:-1] else "unknown"


def parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _fmt(rec) -> str:
    return str(_get(rec, "format", "") or "Unknown").strip().upper() or "UNKNOWN"


def _keep(rec, f, cutoff) -> bool:
    if f.get("media", "all") != "all" and norm_media(_get(rec, "media_type")) != f["media"]:
        return False
    if f.get("status", "all") != "all" and norm_status(_get(rec, "status")) != f["status"]:
        return False
    if f.get("format", "all") != "all" and _fmt(rec) != f["format"]:
        return False
    if f.get("genre", "all") != "all" and f["genre"] not in (_get(rec, "genres", []) or []):
        return False
    if cutoff:
        dates = (parse_date(_get(rec, k)) for k, _ in DATE_FIELDS)
        if not any(d and d >= cutoff for d in dates):
            return False
    return True


def _sum_field(records, key):
    total = 0
    for record in records:
        try:
            value = _get(record, key)
            if value not in (None, ""):
                number = int(value)
                if number >= 0:
                    total += number
        except (TypeError, ValueError, OverflowError):
            continue
    return total


def build_dashboard(records, filters=None, now=None) -> dict:
    now = now or datetime.now()
    f = filters or {}
    allrec = list(records)
    days = DATE_WINDOWS.get(f.get("dates", "all"))
    cutoff = now.date() - timedelta(days=days) if days else None
    rows = [r for r in allrec if _keep(r, f, cutoff)]

    statuses = Counter(norm_status(_get(r, "status")) for r in rows)
    media = Counter(norm_media(_get(r, "media_type")) for r in rows)
    genre_n, genre_media = Counter(), defaultdict(Counter)
    for r in rows:
        for g in dict.fromkeys(_get(r, "genres", []) or []):
            genre_n[g] += 1
            genre_media[g][norm_media(_get(r, "media_type"))] += 1

    by_media = {m: {k: 0 for k, _ in STATUSES} for m in MEDIA}
    for r in rows:
        by_media[norm_media(_get(r, "media_type"))][norm_status(_get(r, "status"))] += 1

    tiers = Counter(str(_get(r, "tier", "")).strip().upper() for r in rows
                    if str(_get(r, "tier", "") or "").strip().upper() in TIER_ORDER)
    tier_list = [{"tier": t, "count": tiers[t]} for t in TIER_ORDER if tiers[t]]
    tier_list += [{"tier": t, "count": c} for t, c in sorted(tiers.items()) if t not in TIER_ORDER]

    events = []
    for r in rows:
        for key, label in DATE_FIELDS:
            d = parse_date(_get(r, key))
            if d:
                events.append((d, label, str(_get(r, "title", ""))))
    events.sort(key=lambda e: e[0], reverse=True)
    months = Counter(f"{d.year}-{d.month:02d}" for d, _, _ in events)
    heat = defaultdict(lambda: defaultdict(int))
    for d, _, _ in events:
        heat[str(d.year)][str(d.month)] += 1

    anime = [r for r in rows if norm_media(_get(r, "media_type")) == "anime"]
    other = [r for r in rows if norm_media(_get(r, "media_type")) != "anime"]
    scores = []
    for r in anime:
        raw = _get(r, "score")
        try:
            value = float(raw)
            if raw not in (None, "") and value != 0 and 0 <= value <= 10:
                scores.append(value)
        except (TypeError, ValueError, OverflowError):
            continue
    years = Counter(int(_get(r, "year")) for r in rows if str(_get(r, "year", "")).isdigit())

    active = [r for r in rows if norm_status(_get(r, "status")) == "active"]
    active.sort(key=lambda r: str(_get(r, "last_date", "")), reverse=True)

    def opts(values):
        return [{"value": v, "label": v.title() if v.islower() else v} for v in values]

    return {
        "updatedAt": now.isoformat(timespec="seconds"),
        "kpis": {
            "total": len(rows), "completed": statuses["done"], "inProgress": statuses["active"],
            "favorites": sum(1 for r in rows if _get(r, "favorite", False)),
            "avgScore": round(sum(scores) / len(scores), 2) if scores else None,
            "ratedCount": len(scores),
            "episodes": [_sum_field(anime, "progress"), _sum_field(anime, "total")],
            "chapters": [_sum_field(other, "progress"), _sum_field(other, "total")],
            "tiered": sum(tiers.values()), "uniqueGenres": len(genre_n),
        },
        "media": [{"label": m.title(), "key": m, "count": media[m]} for m in MEDIA if media[m]],
        "formats": [{"label": k, "count": v} for k, v in sorted(Counter(_fmt(r) for r in rows).items())],
        "genres": [{"label": g, "count": c, "media": genre_media[g].most_common(1)[0][0]}
                   for g, c in genre_n.most_common(24)],
        "status": [{"key": k, "label": lbl, "count": statuses[k]} for k, lbl in STATUSES],
        "statusByMedia": by_media,
        "tiers": tier_list,
        "months": [{"ym": k, "count": months[k]} for k in sorted(months)],
        "heat": {y: dict(m) for y, m in sorted(heat.items())},
        "years": [{"year": y, "count": years[y]} for y in sorted(years)],
        "inProgress": [{"id": _get(r, "id"), "title": str(_get(r, "title", "")),
                        "media": norm_media(_get(r, "media_type")),
                        "progress": int(_get(r, "progress", 0) or 0),
                        "total": int(_get(r, "total", 0) or 0)} for r in active[:8]],
        "activity": [{"date": d.isoformat(), "label": lbl, "title": t} for d, lbl, t in events[:8]],
        # filter options come from ALL records so choosing one never empties the lists
        "options": {
            "media": opts([m for m in MEDIA if any(norm_media(_get(r, "media_type")) == m for r in allrec)]),
            "status": [{"value": k, "label": lbl} for k, lbl in STATUSES
                       if k != "unknown" or any(norm_status(_get(r, "status")) == k for r in allrec)],
            "format": opts(sorted({_fmt(r) for r in allrec})),
            "genre": opts(sorted({g for r in allrec for g in (_get(r, "genres", []) or [])})),
        },
    }
