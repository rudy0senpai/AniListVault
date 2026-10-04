"""Synchronise the library through the user's Google Drive folder.

The library is exported as a single portable file and uploaded to Drive.
Google Drive itself keeps that file current on every machine, so this
module only has to push and pull — it does not implement replication,
which is what keeps it small enough to trust.

Private entries (``privacy = 'private'``) are excluded unless the user
explicitly opts in, because syncing would otherwise move viewing history
off the machine.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

from animevault.services.account import (
    DRIVE_API,
    DRIVE_UPLOAD_URL,
    load_account,
    load_tokens,
)

logger = logging.getLogger(__name__)

SYNC_FILENAME = "animevault-library.json"
SYNC_FORMAT_VERSION = 1


# ── Payload ───────────────────────────────────────────────────────


def build_payload(include_private: bool = False) -> dict:
    """Collect the library into a JSON-serialisable payload.

    Parameters
    ----------
    include_private:
        When ``False`` (the default) entries marked private are omitted.
    """
    from animevault.models.anime import Anime
    from animevault.models.literature import Literature

    privacy_filter = None if include_private else "public"

    animes = [
        _anime_row(a)
        for a in Anime.all()
        if privacy_filter is None or (a.privacy or "public") != "private"
    ]
    literature = [
        _literature_row(i)
        for i in Literature.all()
        if privacy_filter is None or (i.privacy or "public") != "private"
    ]

    return {
        "format_version": SYNC_FORMAT_VERSION,
        "exported_at": _now(),
        "include_private": include_private,
        "counts": {"anime": len(animes), "literature": len(literature)},
        "anime": animes,
        "literature": literature,
    }


def _now() -> str:
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _anime_row(a) -> dict:
    return {
        "title": a.title,
        "title_ja": a.title_ja,
        "title_en": a.title_en,
        "episodes": a.episodes,
        "episodes_watched": a.episodes_watched,
        "status": a.status,
        "tier": a.tier,
        "score": a.score,
        "notes": a.notes,
        "favorite": bool(a.favorite),
        "rewatches": a.rewatches,
        "privacy": a.privacy or "public",
        "first_watched": a.first_watched,
        "last_watched": a.last_watched,
        "completed_date": a.completed_date,
        "synopsis": a.synopsis,
        "media_type": a.media_type,
        "genres": list(a.genres or []),
        "studios": list(a.studios or []),
        "season": a.season,
        "season_year": a.season_year,
        "aired_from": a.aired_from,
        "aired_to": a.aired_to,
        "duration": a.duration,
        "poster_path": a.poster_path,
        "mal_id": a.mal_id,
        "anilist_id": a.anilist_id,
        "kitsu_id": a.kitsu_id,
        "tmdb_id": a.tmdb_id,
        "anidb_id": a.anidb_id,
        "source_provider": a.source_provider,
    }


def _literature_row(i) -> dict:
    return {
        "category": i.category,
        "title": i.title,
        "title_native": i.title_native,
        "title_en": i.title_en,
        "synonyms": list(i.synonyms or []),
        "format": i.format,
        "status": i.status,
        "tier": i.tier,
        "chapters": i.chapters,
        "chapters_read": i.chapters_read,
        "volumes": i.volumes,
        "volumes_read": i.volumes_read,
        "favorite": bool(i.favorite),
        "rewatches": i.rewatches,
        "privacy": i.privacy or "public",
        "notes": i.notes,
        "first_read": i.first_read,
        "last_read": i.last_read,
        "completed_date": i.completed_date,
        "synopsis": i.synopsis,
        "genres": list(i.genres or []),
        "authors": list(i.authors or []),
        "artists": list(i.artists or []),
        "serialization": i.serialization,
        "pub_status": i.pub_status,
        "origin_country": i.origin_country,
        "started_at": i.started_at,
        "ended_at": i.ended_at,
        "cover_path": i.cover_path,
        "anilist_id": i.anilist_id,
        "kitsu_id": i.kitsu_id,
        "mal_id": i.mal_id,
        "source_provider": i.source_provider,
    }


# ── Result ────────────────────────────────────────────────────────


@dataclass
class SyncResult:
    """Outcome of one sync run."""

    ok: bool = False
    message: str = ""
    uploaded: int = 0
    downloaded: int = 0
    skipped_private: int = 0
    direction: str = ""

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "message": self.message,
            "uploaded": self.uploaded,
            "downloaded": self.downloaded,
            "skipped_private": self.skipped_private,
        }


def count_private() -> int:
    """How many entries would be excluded from a sync right now."""
    from animevault.models.anime import Anime
    from animevault.models.literature import Literature

    return sum(
        1 for item in list(Anime.all()) + list(Literature.all())
        if (getattr(item, "privacy", "public") or "public") == "private"
    )


# ── Drive transport ───────────────────────────────────────────────


class DriveError(Exception):
    """A Drive or auth operation failed."""


def _access_token() -> str:
    tokens = load_tokens()
    if not tokens:
        raise DriveError("Not connected to a Google account.")
    return tokens["access_token"]


def _request(
    url: str,
    *,
    method: str = "GET",
    headers: Optional[dict] = None,
    data: Optional[bytes] = None,
) -> dict:
    token = _access_token()
    all_headers = {"Authorization": f"Bearer {token}"}
    if headers:
        all_headers.update(headers)

    request = urllib.request.Request(
        url, data=data, headers=all_headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        raise DriveError(f"Google Drive returned HTTP {exc.code}. {detail}") from exc
    except urllib.error.URLError as exc:
        raise DriveError(f"Could not reach Google Drive: {exc.reason}") from exc

    import json

    if not body:
        return {}
    try:
        return json.loads(body.decode("utf-8"))
    except ValueError:
        return {}


def find_sync_file() -> Optional[dict]:
    """Locate the sync file in Drive, if it exists."""
    query = (
        "name = 'animevault-library.json' and trashed = false"
    )
    import urllib.parse

    url = (
        f"{DRIVE_API}/files?q={urllib.parse.quote(query)}&spaces=appDataFolder"
        "&fields=files(id,name,modifiedTime,size)"
    )
    data = _request(url)
    files = data.get("files") or []
    return files[0] if files else None


def upload(payload: dict, existing_file_id: str = "") -> str:
    """Upload the payload, replacing an existing sync file when present.

    Returns the Drive file id.
    """
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    if existing_file_id:
        url = (
            f"{DRIVE_UPLOAD_URL}/files/{existing_file_id}?uploadType=media"
            "&fields=id,modifiedTime"
        )
        result = _request(
            url,
            method="PATCH",
            headers={"Content-Type": "application/json"},
            data=body,
        )
        return result.get("id", existing_file_id)

    boundary = "animevault-sync-boundary"
    metadata = json.dumps(
        {"name": SYNC_FILENAME, "parents": ["appDataFolder"]}
    ).encode("utf-8")
    multipart = b"".join([
        b"--" + boundary.encode() + b"\r\n",
        b'Content-Type: application/json; charset=UTF-8\r\n\r\n',
        metadata,
        b"\r\n--" + boundary.encode() + b"\r\n",
        b"Content-Type: application/json; charset=UTF-8\r\n\r\n",
        body,
        b"\r\n--" + boundary.encode() + b"--\r\n",
    ])
    url = (
        f"{DRIVE_UPLOAD_URL}?uploadType=multipart&fields=id"
    )
    result = _request(
        url,
        method="POST",
        headers={
            "Content-Type": f"multipart/related; boundary={boundary}"
        },
        data=multipart,
    )
    file_id = result.get("id", "")
    if not file_id:
        raise DriveError("Drive did not return a file id for the upload.")
    return file_id


def download(file_id: str) -> dict:
    """Fetch and parse the remote sync file."""
    url = f"{DRIVE_API}/files/{file_id}?alt=media"
    token = _access_token()
    request = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}"}
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise DriveError(f"Could not download: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise DriveError(f"Could not reach Google Drive: {exc.reason}") from exc

    import json

    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        raise DriveError("The remote library file is not valid JSON.") from exc


# ── Applying a remote payload ──────────────────────────────────────


def merge_payload(payload: dict, overwrite: bool = False) -> tuple[int, int]:
    """Merge a downloaded payload into the local library.

    Existing entries are matched by provider id, then title, so
    re-downloading the same library does not create duplicates.

    Returns ``(added, updated)``.
    """
    from animevault.models.anime import Anime
    from animevault.models.literature import Literature

    if payload.get("format_version", 1) > SYNC_FORMAT_VERSION:
        raise ValueError(
            "This library was exported by a newer version of AnimeVault."
        )

    added = updated = 0

    for row in payload.get("anime") or []:
        existing = _match_anime(row)
        if existing is None:
            Anime(
                id=None,
                title=row.get("title") or "Untitled",
                title_ja=row.get("title_ja", ""),
                title_en=row.get("title_en", ""),
                episodes=int(row.get("episodes") or 0),
                episodes_watched=int(row.get("episodes_watched") or 0),
                status=row.get("status") or "plan_to_watch",
                tier=row.get("tier"),
                score=row.get("score"),
                notes=row.get("notes", ""),
                favorite=bool(row.get("favorite")),
                rewatches=int(row.get("rewatches") or 0),
                privacy=row.get("privacy", "public"),
                synopsis=row.get("synopsis", ""),
                media_type=row.get("media_type", ""),
                genres=list(row.get("genres") or []),
                studios=list(row.get("studios") or []),
                season=row.get("season", ""),
                season_year=row.get("season_year"),
                aired_from=row.get("aired_from", ""),
                aired_to=row.get("aired_to", ""),
                duration=int(row.get("duration") or 0),
                poster_path=row.get("poster_path", ""),
                mal_id=row.get("mal_id"),
                anilist_id=row.get("anilist_id"),
                kitsu_id=row.get("kitsu_id"),
                tmdb_id=row.get("tmdb_id"),
                anidb_id=row.get("anidb_id"),
                source_provider=row.get("source_provider", "sync"),
            ).save()
            added += 1
            continue

        if _apply_common(existing, row, overwrite):
            updated += 1

    for row in payload.get("literature") or []:
        existing = _match_literature(row)
        if existing is None:
            Literature(
                id=None,
                title=row.get("title") or "Untitled",
                category=row.get("category") or "manga",
                title_native=row.get("title_native", ""),
                title_en=row.get("title_en", ""),
                synonyms=list(row.get("synonyms") or []),
                format=row.get("format", ""),
                status=row.get("status") or "watching",
                tier=row.get("tier"),
                chapters=int(row.get("chapters") or 0),
                chapters_read=int(row.get("chapters_read") or 0),
                volumes=int(row.get("volumes") or 0),
                volumes_read=int(row.get("volumes_read") or 0),
                favorite=bool(row.get("favorite")),
                rewatches=int(row.get("rewatches") or 0),
                privacy=row.get("privacy", "public"),
                notes=row.get("notes", ""),
                synopsis=row.get("synopsis", ""),
                genres=list(row.get("genres") or []),
                authors=list(row.get("authors") or []),
                artists=list(row.get("artists") or []),
                serialization=row.get("serialization", ""),
                pub_status=row.get("pub_status", ""),
                origin_country=row.get("origin_country", ""),
                started_at=row.get("started_at", ""),
                ended_at=row.get("ended_at", ""),
                cover_path=row.get("cover_path", ""),
                anilist_id=row.get("anilist_id"),
                kitsu_id=row.get("kitsu_id"),
                mal_id=row.get("mal_id"),
                source_provider=row.get("source_provider", "sync"),
            ).save()
            added += 1
            continue

        if _apply_common(existing, row, overwrite):
            updated += 1

    return added, updated


def _match_anime(row: dict):
    from animevault.models.anime import Anime

    for key in ("anilist_id", "mal_id", "kitsu_id"):
        value = row.get(key)
        if value:
            found = Anime.find_by_provider_id(
                anilist_id=row.get("anilist_id"),
                mal_id=row.get("mal_id"),
                kitsu_id=row.get("kitsu_id"),
            )
            if found is not None:
                return found
            break
    return Anime.find_by_title(row.get("title") or "")


def _match_literature(row: dict):
    from animevault.models.literature import Literature

    found = Literature.find_by_provider_id(
        anilist_id=row.get("anilist_id"),
        kitsu_id=row.get("kitsu_id"),
        mal_id=row.get("mal_id"),
    )
    if found is not None:
        return found
    return Literature.find_by_title(
        row.get("title") or "", row.get("category")
    )


def _apply_common(item, row: dict, overwrite: bool) -> bool:
    """Copy incoming values onto an existing record.

    With ``overwrite`` false (the default) existing non-empty values are
    preserved, so downloading never destroys local edits.
    """
    changed = False
    simple = (
        "title", "status", "tier", "notes", "synopsis", "privacy",
        "completed_date", "poster_path", "cover_path",
    )
    numeric = (
        "episodes", "episodes_watched", "chapters", "chapters_read",
        "volumes", "rewatches", "duration", "season_year",
    )
    lists = ("genres", "studios", "authors", "artists")

    for attr in simple:
        incoming = row.get(attr)
        if incoming in (None, ""):
            continue
        if overwrite or not getattr(item, attr, ""):
            if getattr(item, attr, "") != incoming:
                setattr(item, attr, incoming)
                changed = True

    for attr in numeric:
        incoming = row.get(attr)
        if not incoming:
            continue
        if overwrite or not getattr(item, attr, 0):
            if getattr(item, attr, 0) != incoming:
                setattr(item, attr, incoming)
                changed = True

    for attr in lists:
        incoming = row.get(attr) or []
        if not incoming:
            continue
        if overwrite or not getattr(item, attr, []):
            if list(getattr(item, attr, []) or []) != list(incoming):
                setattr(item, attr, list(incoming))
                changed = True

    if row.get("favorite") and not getattr(item, "favorite", False):
        item.favorite = True
        changed = True

    if changed:
        item.save()
    return changed


# ── High-level actions ────────────────────────────────────────────


def push(include_private: bool = False) -> SyncResult:
    """Upload the local library, replacing any existing remote copy."""
    account = load_account()
    payload = build_payload(include_private=include_private)
    counts = payload["counts"]

    try:
        existing = find_sync_file()
        file_id = upload(payload, existing["id"] if existing else "")
    except DriveError as exc:
        return SyncResult(ok=False, message=str(exc))

    from animevault.services.account import mark_synced

    mark_synced(file_id or (account.drive_folder_id if account else ""))

    skipped = 0 if include_private else count_private()
    return SyncResult(
        ok=True,
        message=(
            f"Uploaded {counts['anime']} anime and "
            f"{counts['literature']} books to Google Drive."
        ),
        uploaded=counts["anime"] + counts["literature"],
        skipped_private=skipped,
        direction="push",
    )


def pull(overwrite: bool = False) -> SyncResult:
    """Download the remote library and merge it into this machine."""
    try:
        existing = find_sync_file()
        if not existing:
            return SyncResult(
                ok=False,
                message="No library found in Drive yet — upload first.",
                direction="pull",
            )
        payload = download(existing["id"])
    except DriveError as exc:
        return SyncResult(ok=False, message=str(exc), direction="pull")

    try:
        added, updated = merge_payload(payload, overwrite=overwrite)
    except Exception as exc:
        logger.exception("Merging the downloaded library failed")
        return SyncResult(
            ok=False,
            message=f"Could not merge the downloaded library: {exc}",
            direction="pull",
        )

    from animevault.services.account import mark_synced

    mark_synced(existing.get("id", ""))

    return SyncResult(
        ok=True,
        message=f"Added {added} new and updated {updated} existing entries.",
        downloaded=added + updated,
        direction="pull",
    )