"""Batch import of anime drafts into the library.

Design constraints:

* Personal fields the user already set are never silently overwritten —
  the default policy is *only fill empty fields*.
* Records are written in chunks inside a single transaction per chunk,
  never one commit per row.
* In-file duplicates collapse onto one record.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

from animevault.database import get_connection
from animevault.models.anime import Anime
from animevault.services.importers.row_parser import AnimeDraft, RowError

logger = logging.getLogger(__name__)

#: Records per transaction.
DEFAULT_BATCH_SIZE = 100

# ── Conflict policies ────────────────────────────────────────────

POLICY_FILL_EMPTY = "fill_empty"     # default: only fill empty fields
POLICY_KEEP_EXISTING = "keep"        # never touch existing values
POLICY_USE_IMPORTED = "imported"     # imported values win

PERSONAL_FIELDS = (
    "status",
    "tier",
    "rewatches",
    "favorite",
    "notes",
    "episodes_watched",
    "first_watched",
    "last_watched",
    "completed_date",
    "privacy",
)


@dataclass
class ImportStats:
    """Counters describing one import run."""

    added: int = 0
    updated: int = 0
    duplicates: int = 0
    invalid: int = 0

    @property
    def total(self) -> int:
        return self.added + self.updated + self.duplicates + self.invalid

    def as_dict(self) -> dict:
        return {
            "added": self.added,
            "updated": self.updated,
            "duplicates": self.duplicates,
            "invalid": self.invalid,
            "total": self.total,
        }


@dataclass
class ImportResult:
    """Outcome of an import, including records needing enrichment."""

    stats: ImportStats = field(default_factory=ImportStats)
    added_ids: list[int] = field(default_factory=list)
    updated_ids: list[int] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
    needs_enrichment: list[int] = field(default_factory=list)
    cancelled: bool = False


class CancelledError(Exception):
    """Raised internally to abort an import at a chunk boundary."""


def _apply_personal(
    anime: Anime, draft: AnimeDraft, policy: str
) -> bool:
    """Apply personal fields from *draft* onto *anime* per *policy*.

    Returns True when anything changed.
    """
    changed = False

    def _set(attr: str, incoming, is_empty) -> None:
        nonlocal changed
        if incoming is None:
            return
        current = getattr(anime, attr)
        if policy == POLICY_KEEP_EXISTING:
            return
        if policy == POLICY_FILL_EMPTY and not is_empty(current):
            return
        if current != incoming:
            setattr(anime, attr, incoming)
            changed = True

    def _empty_str(v):
        return not v

    def _empty_opt(v):
        return v is None

    def _empty_num(v):
        return not v

    def _empty_bool(v):
        return not v

    _set("status", draft.status, _empty_str)
    _set("tier", draft.tier, _empty_opt)
    _set("rewatches", draft.rewatches, _empty_num)
    _set("episodes_watched", draft.episodes_watched, _empty_num)
    _set("favorite", draft.favorite, _empty_bool)
    _set("notes", draft.notes, _empty_str)
    _set("first_watched", draft.first_watched, _empty_str)
    _set("last_watched", draft.last_watched, _empty_str)
    _set("completed_date", draft.completed_date, _empty_str)
    _set("privacy", draft.privacy, _empty_str)

    # Episodes total is metadata-ish but user-supplied here; fill if empty.
    if anime.episodes == 0 and draft.episodes:
        anime.episodes = draft.episodes
        changed = True
    if not anime.title_ja and draft.title_ja:
        anime.title_ja = draft.title_ja
        changed = True
    if not anime.title_en and draft.title_en:
        anime.title_en = draft.title_en
        changed = True

    return changed


def _apply_metadata(anime: Anime, draft: AnimeDraft, policy: str) -> bool:
    """Apply provider-style metadata from *draft*; never clobber good data."""
    changed = False

    def _fill(attr: str, incoming, is_empty) -> None:
        nonlocal changed
        if incoming is None:
            return
        current = getattr(anime, attr)
        if policy == POLICY_KEEP_EXISTING:
            return
        if not is_empty(current):
            return
        if current != incoming:
            setattr(anime, attr, incoming)
            changed = True

    _fill("synopsis", draft.synopsis or None, lambda v: not v)
    _fill("genres", draft.genres or None, lambda v: not v)
    _fill("studios", draft.studios or None, lambda v: not v)
    _fill("media_type", draft.media_type or None, lambda v: not v)
    _fill("airing_status", draft.airing_status or None, lambda v: not v)
    _fill("duration", draft.duration or None, lambda v: not v)
    _fill("season", draft.season or None, lambda v: not v)
    _fill("season_year", draft.season_year, lambda v: v is None)
    _fill("poster_url", draft.poster_url or None, lambda v: not v)

    # Provider IDs are additive.
    for attr in ("mal_id", "anilist_id", "kitsu_id", "tmdb_id", "anidb_id"):
        incoming = getattr(draft, attr)
        if incoming is not None and getattr(anime, attr) is None:
            setattr(anime, attr, incoming)
            changed = True

    return changed


def _find_existing(draft: AnimeDraft) -> Optional[Anime]:
    """Match a draft against the library by provider ID, then title."""
    if any(
        v is not None
        for v in (draft.mal_id, draft.anilist_id, draft.kitsu_id, draft.tmdb_id, draft.anidb_id)
    ):
        found = Anime.find_by_provider_id(
            mal_id=draft.mal_id,
            anilist_id=draft.anilist_id,
            kitsu_id=draft.kitsu_id,
            tmdb_id=draft.tmdb_id,
            anidb_id=draft.anidb_id,
        )
        if found is not None:
            return found
    if draft.title:
        return Anime.find_by_title(draft.title)
    return None


def _needs_enrichment(anime: Anime) -> bool:
    """Whether a record still lacks provider metadata worth fetching."""
    return not (anime.anilist_id or anime.mal_id or anime.kitsu_id or anime.tmdb_id)


def import_drafts(
    drafts: Iterable[AnimeDraft],
    *,
    policy: str = POLICY_FILL_EMPTY,
    batch_size: int = DEFAULT_BATCH_SIZE,
    progress: Optional[Callable[[int, int, ImportStats], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    collect_enrichment: bool = True,
) -> ImportResult:
    """Import drafts in chunks, writing one transaction per chunk.

    Parameters
    ----------
    drafts:
        Parsed rows to import.
    policy:
        One of :data:`POLICY_FILL_EMPTY` (default), :data:`POLICY_KEEP_EXISTING`
        or :data:`POLICY_USE_IMPORTED`.
    batch_size:
        Records per transaction.
    progress:
        Optional callback ``(done, total, stats)`` after each chunk.
    should_cancel:
        Optional predicate checked at each chunk boundary.
    collect_enrichment:
        Record ids that still need provider metadata.
    """
    drafts = list(drafts)
    result = ImportResult()
    total = len(drafts)
    if total == 0:
        return result

    # Collapse in-file duplicates onto the first occurrence.
    by_key: dict[str, AnimeDraft] = {}
    ordered: list[AnimeDraft] = []
    for d in drafts:
        key = d.dedupe_key()
        if key and key in by_key:
            result.stats.duplicates += 1
            # Merge the later row into the retained one (fill blanks only).
            _merge_draft(by_key[key], d)
        else:
            if key:
                by_key[key] = d
            ordered.append(d)

    processed = 0
    with get_connection() as conn:
        for start in range(0, len(ordered), batch_size):
            if should_cancel is not None and should_cancel():
                result.cancelled = True
                conn.commit()
                break

            chunk = ordered[start : start + batch_size]
            for draft in chunk:
                processed += 1
                try:
                    _import_one(draft, policy, result, collect_enrichment)
                except Exception as exc:  # keep going on a bad row
                    logger.warning("Import failed for %r: %s", draft.title, exc)
                    result.stats.invalid += 1
            conn.commit()  # one commit per chunk

            if progress is not None:
                progress(processed, total, result.stats)

    return result


def _merge_draft(target: AnimeDraft, incoming: AnimeDraft) -> None:
    """Fill blanks on *target* from *incoming* (in-file duplicate handling)."""
    for attr, default in (
        ("title_ja", ""),
        ("title_en", ""),
        ("notes", ""),
        ("synopsis", ""),
        ("first_watched", ""),
        ("last_watched", ""),
        ("completed_date", ""),
        ("media_type", ""),
        ("airing_status", ""),
        ("season", ""),
        ("poster_url", ""),
    ):
        if not getattr(target, attr) and getattr(incoming, attr):
            setattr(target, attr, getattr(incoming, attr))

    if not target.episodes and incoming.episodes:
        target.episodes = incoming.episodes
    if not target.episodes_watched and incoming.episodes_watched:
        target.episodes_watched = incoming.episodes_watched
    if not target.rewatches and incoming.rewatches:
        target.rewatches = incoming.rewatches
    if not target.tier and incoming.tier:
        target.tier = incoming.tier
    if not target.favorite and incoming.favorite:
        target.favorite = incoming.favorite
    if not target.genres and incoming.genres:
        target.genres = incoming.genres
    if not target.studios and incoming.studios:
        target.studios = incoming.studios
    for attr in ("mal_id", "anilist_id", "kitsu_id", "tmdb_id", "anidb_id"):
        if getattr(target, attr) is None and getattr(incoming, attr) is not None:
            setattr(target, attr, getattr(incoming, attr))


def _import_one(
    draft: AnimeDraft,
    policy: str,
    result: ImportResult,
    collect_enrichment: bool,
) -> None:
    # Literature rows go to their own model, not the anime table.
    if draft.is_literature:
        _import_literature(draft, policy, result, collect_enrichment)
        return

    existing = _find_existing(draft)
    if existing is None:
        anime = Anime(
            id=None,
            title=draft.title,
            title_ja=draft.title_ja,
            episodes=draft.episodes,
            status=draft.status,
            tier=draft.tier,
            rewatches=draft.rewatches,
            episodes_watched=draft.episodes_watched,
            favorite=draft.favorite,
            notes=draft.notes,
            first_watched=draft.first_watched,
            last_watched=draft.last_watched,
            completed_date=draft.completed_date,
            privacy=draft.privacy,
            title_en=draft.title_en,
            synopsis=draft.synopsis,
            genres=list(draft.genres),
            studios=list(draft.studios),
            media_type=draft.media_type,
            airing_status=draft.airing_status,
            duration=draft.duration,
            season=draft.season,
            season_year=draft.season_year,
            poster_url=draft.poster_url,
            mal_id=draft.mal_id,
            anilist_id=draft.anilist_id,
            kitsu_id=draft.kitsu_id,
            tmdb_id=draft.tmdb_id,
            anidb_id=draft.anidb_id,
        )
        anime.save()
        result.stats.added += 1
        result.added_ids.append(anime.id)
        if collect_enrichment and _needs_enrichment(anime):
            result.needs_enrichment.append(anime.id)
        return

    changed_personal = _apply_personal(existing, draft, policy)
    changed_meta = _apply_metadata(existing, draft, policy)
    if changed_personal or changed_meta:
        existing.save()
        result.stats.updated += 1
        result.updated_ids.append(existing.id)
    else:
        result.stats.duplicates += 1
    if collect_enrichment and _needs_enrichment(existing):
        result.needs_enrichment.append(existing.id)


def _import_literature(
    draft: AnimeDraft,
    policy: str,
    result: ImportResult,
    collect_enrichment: bool,
) -> None:
    """Persist a manga / manhwa / manhua draft."""
    from animevault.models.literature import Literature

    existing = None
    if any(
        v is not None
        for v in (draft.anilist_id, draft.mal_id, draft.kitsu_id)
    ):
        existing = Literature.find_by_provider_id(
            anilist_id=draft.anilist_id,
            kitsu_id=draft.kitsu_id,
            mal_id=draft.mal_id,
        )
    if existing is None:
        existing = Literature.find_by_title(draft.title, draft.category)

    if existing is None:
        item = Literature(
            id=None,
            title=draft.title,
            category=draft.category,
            status=draft.status if draft.status != "plan_to_watch" else "watching",
            tier=draft.tier,
            rewatches=draft.rewatches,
            chapters_read=draft.chapters_read,
            chapters=draft.chapters,
            volumes=draft.volumes,
            favorite=draft.favorite,
            notes=draft.notes,
            first_read=draft.first_watched,
            last_read=draft.last_watched,
            completed_date=draft.completed_date,
            privacy=draft.privacy,
            title_native=draft.title_native,
            synonyms=list(draft.synonyms),
            format=draft.media_type,
            synopsis=draft.synopsis,
            genres=list(draft.genres),
            authors=list(draft.authors),
            artists=list(draft.artists),
            serialization=draft.serialization,
            pub_status=draft.pub_status,
            origin_country=draft.origin_country,
            started_at=draft.started_at,
            ended_at=draft.ended_at,
            anilist_id=draft.anilist_id,
            kitsu_id=draft.kitsu_id,
            mal_id=draft.mal_id,
            source_provider="import",
        )
        item.save()
        result.stats.added += 1
        result.added_ids.append(item.id)
        if collect_enrichment and not (item.anilist_id or item.mal_id):
            result.needs_enrichment.append(item.id)
        return

    changed = False

    def _set(attr, incoming, is_empty) -> None:
        nonlocal changed
        if incoming is None:
            return
        current = getattr(existing, attr)
        if policy == POLICY_KEEP_EXISTING:
            return
        if policy == POLICY_FILL_EMPTY and not is_empty(current):
            return
        if current != incoming:
            setattr(existing, attr, incoming)
            changed = True

    _set("tier", draft.tier, lambda v: not v)
    _set("notes", draft.notes, lambda v: not v)
    _set("favorite", draft.favorite, lambda v: not v)
    _set("rewatches", draft.rewatches, lambda v: not v)
    _set("chapters", draft.chapters, lambda v: not v)
    _set("chapters_read", draft.chapters_read, lambda v: not v)
    _set("volumes", draft.volumes, lambda v: not v)
    _set("synopsis", draft.synopsis or None, lambda v: not v)
    _set("genres", draft.genres or None, lambda v: not v)
    _set("authors", draft.authors or None, lambda v: not v)
    _set("title_native", draft.title_native, lambda v: not v)
    for attr in ("anilist_id", "kitsu_id", "mal_id"):
        incoming = getattr(draft, attr)
        if incoming is not None and getattr(existing, attr) is None:
            setattr(existing, attr, incoming)
            changed = True

    if changed:
        existing.save()
        result.stats.updated += 1
        result.updated_ids.append(existing.id)
    else:
        result.stats.duplicates += 1
    if collect_enrichment and not (existing.anilist_id or existing.mal_id):
        result.needs_enrichment.append(existing.id)