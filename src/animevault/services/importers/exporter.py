"""Export the library to CSV, XLSX or a SQLite-compatible SQL dump.

One row model feeds every format, so the three outputs stay consistent.
Values are written for round-tripping: an exported file can be re-imported
by the matching importer without losing personal data.
"""

from __future__ import annotations

import csv
import datetime as dt
import logging
import sqlite3
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from animevault.media_types import MEDIA_ANIME
from animevault.models.anime import Anime
from animevault.models.literature import Literature

logger = logging.getLogger(__name__)

# ── Row schema shared by every export format ──────────────────────

COLUMNS: tuple[str, ...] = (
    "media_type",
    "internal_id",
    "title",
    "title_native",
    "title_en",
    "synonyms",
    "episodes",
    "episodes_watched",
    "chapters",
    "chapters_read",
    "volumes",
    "volumes_read",
    "status",
    "tier",
    "score",
    "rewatches",
    "favorite",
    "progress",
    "progress_percent",
    "notes",
    "first_read",
    "last_read",
    "completed_date",
    "privacy",
    "media_format",
    "airing_status",
    "pub_status",
    "serialization",
    "genres",
    "studios",
    "authors",
    "artists",
    "duration",
    "season",
    "season_year",
    "aired_from",
    "aired_to",
    "started_at",
    "ended_at",
    "origin_country",
    "synopsis",
    "mal_id",
    "anilist_id",
    "kitsu_id",
    "tmdb_id",
    "anidb_id",
    "source_provider",
    "metadata_fetched_at",
    "poster_url",
    "poster_path",
)

#: Human-facing column labels, reused by the export UI.
DATE_COLUMNS = frozenset({
    "first_read", "last_read", "completed_date", "aired_from", "aired_to",
    "started_at", "ended_at", "metadata_fetched_at",
})

COLUMN_LABELS: dict[str, str] = {
    "internal_id": "Internal ID",
    "media_type": "Media Type",
    "title": "Title",
    "title_native": "Native Title",
    "title_en": "English Title",
    "synonyms": "Alternate Titles",
    "episodes": "Episodes",
    "episodes_watched": "Episodes Watched",
    "chapters": "Chapters",
    "chapters_read": "Chapters Read",
    "volumes": "Volumes",
    "volumes_read": "Volumes Read",
    "status": "Status",
    "tier": "Tier",
    "score": "Legacy Score",
    "rewatches": "Rewatches",
    "favorite": "Favorite",
    "progress": "Progress",
    "progress_percent": "Progress %",
    "notes": "Notes",
    "first_read": "First Read",
    "last_read": "Last Read",
    "completed_date": "Completed Date",
    "privacy": "Privacy",
    "media_format": "Format",
    "airing_status": "Airing Status",
    "pub_status": "Publication Status",
    "serialization": "Serialization",
    "genres": "Genres",
    "studios": "Studios",
    "authors": "Authors",
    "artists": "Artists",
    "duration": "Duration (min)",
    "season": "Season",
    "season_year": "Year",
    "aired_from": "First Aired",
    "aired_to": "Last Aired",
    "started_at": "Start Date",
    "ended_at": "End Date",
    "origin_country": "Origin",
    "synopsis": "Synopsis",
    "mal_id": "MAL ID",
    "anilist_id": "AniList ID",
    "kitsu_id": "Kitsu ID",
    "tmdb_id": "TMDB ID",
    "anidb_id": "AniDB ID",
    "source_provider": "Source",
    "metadata_fetched_at": "Fetched At",
    "poster_url": "Poster URL",
    "poster_path": "Poster Path",
}


def _join(values: Optional[Iterable[str]]) -> str:
    return "; ".join(str(v) for v in (values or []) if v)


def anime_to_row(anime: Anime) -> dict:
    """Flatten an :class:`Anime` into an export row."""
    watched = anime.episodes_watched or 0
    total = anime.episodes or 0
    return {
        "internal_id": anime.id,
        "media_type": MEDIA_ANIME,
        "title": anime.title,
        "title_native": anime.title_ja,
        "title_en": anime.title_en,
        "synonyms": "",
        "episodes": total,
        "episodes_watched": watched,
        "chapters": "",
        "chapters_read": "",
        "volumes": "",
        "volumes_read": "",
        "status": anime.status,
        "tier": anime.tier or "",
        "score": anime.score,
        "rewatches": anime.rewatches or 0,
        "favorite": bool(anime.favorite),
        "progress": f"{watched} / {total}" if total else "",
        "progress_percent": min(100, round(watched * 100 / total)) if total else 0,
        "notes": anime.notes,
        "first_read": anime.first_watched,
        "last_read": anime.last_watched,
        "completed_date": anime.completed_date,
        "privacy": anime.privacy or "public",
        "media_format": anime.media_type,
        "airing_status": anime.airing_status,
        "pub_status": "",
        "serialization": "",
        "genres": _join(anime.genres),
        "studios": _join(anime.studios),
        "authors": "",
        "artists": "",
        "duration": anime.duration or "",
        "season": anime.season,
        "season_year": anime.season_year if anime.season_year else "",
        "aired_from": anime.aired_from,
        "aired_to": anime.aired_to,
        "started_at": "",
        "ended_at": "",
        "origin_country": "",
        "synopsis": anime.synopsis,
        "mal_id": anime.mal_id or "",
        "anilist_id": anime.anilist_id or "",
        "kitsu_id": anime.kitsu_id or "",
        "tmdb_id": anime.tmdb_id or "",
        "anidb_id": anime.anidb_id or "",
        "source_provider": anime.source_provider,
        "metadata_fetched_at": anime.metadata_fetched_at,
        "poster_url": anime.poster_url,
        "poster_path": anime.poster_path,
    }


def literature_to_row(item: Literature) -> dict:
    """Flatten a :class:`Literature` into an export row."""
    read = item.chapters_read or 0
    total = item.chapters or 0
    return {
        "internal_id": item.id,
        "media_type": item.category,
        "title": item.title,
        "title_native": item.title_native,
        "title_en": item.title_en,
        "synonyms": _join(item.synonyms),
        "episodes": "",
        "episodes_watched": "",
        "chapters": total,
        "chapters_read": read,
        "volumes": item.volumes or 0,
        "volumes_read": item.volumes_read or 0,
        "status": item.status,
        "tier": item.tier or "",
        "score": "",
        "rewatches": item.rewatches or 0,
        "favorite": bool(item.favorite),
        "progress": f"{read} / {total}" if total else "",
        "progress_percent": item.progress_percent() if total else 0,
        "notes": item.notes,
        "first_read": item.first_read,
        "last_read": item.last_read,
        "completed_date": item.completed_date,
        "privacy": item.privacy or "public",
        "media_format": item.format,
        "airing_status": "",
        "pub_status": item.pub_status,
        "serialization": item.serialization,
        "genres": _join(item.genres),
        "studios": "",
        "authors": _join(item.authors),
        "artists": _join(item.artists),
        "duration": "",
        "season": "",
        "season_year": "",
        "aired_from": "",
        "aired_to": "",
        "started_at": item.started_at,
        "ended_at": item.ended_at,
        "origin_country": item.origin_country,
        "synopsis": item.synopsis,
        "mal_id": item.mal_id or "",
        "anilist_id": item.anilist_id or "",
        "kitsu_id": item.kitsu_id or "",
        "tmdb_id": "",
        "anidb_id": "",
        "source_provider": item.source_provider,
        "metadata_fetched_at": item.metadata_fetched_at,
        "poster_url": item.cover_url,
        "poster_path": item.cover_path,
    }


def collect_rows(
    category: Optional[str] = None,
) -> list[dict]:
    """Gather export rows for the whole library, or one category."""
    rows: list[dict] = []

    if category in (None, "", "all", MEDIA_ANIME):
        rows.extend(anime_to_row(a) for a in Anime.all())

    if category not in (MEDIA_ANIME,):
        for item in Literature.all():
            if category in (None, "", "all") or item.category == category:
                rows.append(literature_to_row(item))

    # Group by media type, then alphabetically, matching the UI ordering.
    rows.sort(key=lambda r: (r["media_type"], str(r["title"]).casefold()))
    return rows


# ── Formats ───────────────────────────────────────────────────────

def export_csv(path: str | Path, rows: list[dict]) -> Path:
    """Write rows to a UTF-8 CSV with a human-readable header row.

    Headers use the same labels as the XLSX export so both open readably,
    and every one of them is still recognised by the importers.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    labels = [COLUMN_LABELS.get(c, c) for c in COLUMNS]
    # utf-8-sig so Excel opens accented/native titles correctly.
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=labels)
        writer.writeheader()
        for row in rows:
            writer.writerow({labels[i]: row.get(c, "") for i, c in enumerate(COLUMNS)})
    return path


def _spreadsheet_value(column: str, value):
    """Convert stored ISO date strings to native spreadsheet date values."""
    if column not in DATE_COLUMNS or not value or isinstance(value, (dt.date, dt.datetime)):
        return value
    text = str(value).strip()
    if len(text) == 10:
        try:
            return dt.date.fromisoformat(text)
        except ValueError:
            pass
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
    except ValueError:
        try:
            return dt.date.fromisoformat(text)
        except ValueError:
            return value


def export_xlsx(path: str | Path, rows: list[dict]) -> Path:
    """Write a real .xlsx workbook with typed cells and standard worksheet controls."""
    from animevault.services.importers.xlsx_writer import write_sheet

    headers = [COLUMN_LABELS.get(c, c) for c in COLUMNS]
    body = [[_spreadsheet_value(c, row.get(c, "")) for c in COLUMNS] for row in rows]
    return write_sheet(path, headers, body, sheet_name="AniListVault Library")


def export_ods(path: str | Path, rows: list[dict]) -> Path:
    """Write an ODS spreadsheet using the canonical columns and typed values."""
    from animevault.services.importers.ods_writer import write_ods

    headers = [COLUMN_LABELS.get(c, c) for c in COLUMNS]
    body = [[_spreadsheet_value(c, row.get(c, "")) for c in COLUMNS] for row in rows]
    return write_ods(path, headers, body, sheet_name="AniListVault Library")


def _schema_statements() -> list[str]:
    """Return CREATE TABLE / CREATE INDEX statements matching the live schema.

    ``_SCHEMA_SQL`` is only the *base* (v1) DDL — the tier and literature
    columns arrive via migrations.  Rather than duplicating that DDL here,
    a throwaway database is created and migrated, then its schema is read
    back out, so an export always matches what the app actually uses.
    """
    import sqlite3
    import tempfile as _tf

    from animevault.database import (
        database_path,
        initialize_database,
        set_database_path,
    )
    from animevault.migration import run_migrations

    original = database_path()
    probe_dir = Path(_tf.mkdtemp(prefix="animevault_export_schema_"))
    probe_db = probe_dir / "schema.db"

    # Clear the thread-local connection so it points at the probe database.
    import animevault.database as db_mod

    had_conn = hasattr(db_mod._local, "conn")
    if had_conn:
        db_mod._local.conn.close()
        del db_mod._local.conn

    try:
        set_database_path(probe_db)
        initialize_database(probe_db)
        run_migrations()

        conn = sqlite3.connect(str(probe_db))
        try:
            rows = conn.execute(
                "SELECT sql FROM sqlite_master "
                "WHERE sql IS NOT NULL AND type IN ('table','index') "
                "AND name NOT LIKE 'sqlite_%' ORDER BY type DESC, name"
            ).fetchall()
        finally:
            conn.close()
    finally:
        # Restore the caller's database.
        set_database_path(original)
        if had_conn:
            db_mod._local.conn = None
            del db_mod._local.conn

    return [f"{r[0].strip()};" for r in rows if r[0]]


def export_sql(path: str | Path, rows: list[dict]) -> Path:
    """Write an AnimeVault-compatible SQL dump.

    The dump contains only ``INSERT`` statements against the current
    schema, so it can be re-imported through the SQL importer (which
    restores it into a temporary database first).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = [
        "-- AnimeVault export",
        "-- Schema + data. Import restores this into a temporary database",
        "-- first, so it never executes against the live library.",
        "",
    ]

    # The importer restores into an empty database, so the dump must carry
    # the schema it inserts into.
    lines += _schema_statements()
    lines += ["", "BEGIN TRANSACTION;"]

    for row in rows:
        is_anime = row.get("media_type") == MEDIA_ANIME
        table = "anime" if is_anime else "literature"
        lines.append(_insert_sql(table, row, is_anime))
        # Provider IDs and other metadata live in the companion table.
        meta_stmt = _metadata_insert_sql(table, row, is_anime)
        if meta_stmt:
            lines.append(meta_stmt)

    lines += ["", "COMMIT;", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _metadata_insert_sql(table: str, row: dict, is_anime: bool) -> str:
    """Build the companion metadata INSERT, keyed to the row just added.

    Uses ``last_insert_rowid()`` so the metadata attaches to the parent
    without hard-coding ids.
    """
    if is_anime:
        meta_table = "anime_metadata"
        key = "anime_id"
        columns = [
            ("title_en", row.get("title_en")),
            ("synopsis", row.get("synopsis")),
            ("airing_status", row.get("airing_status")),
            ("media_type", row.get("media_format")),
            ("genres", _split(row.get("genres"))),
            ("studios", _split(row.get("studios"))),
            ("aired_from", row.get("aired_from")),
            ("aired_to", row.get("aired_to")),
            ("season", row.get("season")),
            ("season_year", row.get("season_year")),
            ("duration", row.get("duration")),
            ("poster_url", row.get("poster_url")),
            ("poster_path", row.get("poster_path")),
            ("mal_id", row.get("mal_id")),
            ("anilist_id", row.get("anilist_id")),
            ("kitsu_id", row.get("kitsu_id")),
            ("tmdb_id", row.get("tmdb_id")),
            ("anidb_id", row.get("anidb_id")),
            ("source_provider", row.get("source_provider")),
            ("metadata_fetched_at", row.get("metadata_fetched_at")),
        ]
    else:
        meta_table = "literature_metadata"
        key = "literature_id"
        columns = [
            ("title_en", row.get("title_en")),
            ("synopsis", row.get("synopsis")),
            ("genres", _split(row.get("genres"))),
            ("authors", _split(row.get("authors"))),
            ("artists", _split(row.get("artists"))),
            ("serialization", row.get("serialization")),
            ("pub_status", row.get("pub_status")),
            ("started_at", row.get("started_at")),
            ("ended_at", row.get("ended_at")),
            ("cover_url", row.get("poster_url")),
            ("cover_path", row.get("poster_path")),
            ("anilist_id", row.get("anilist_id")),
            ("kitsu_id", row.get("kitsu_id")),
            ("mal_id", row.get("mal_id")),
            ("source_provider", row.get("source_provider")),
            ("metadata_fetched_at", row.get("metadata_fetched_at")),
        ]

    cols = [key] + [name for name, _ in columns]
    vals = ["last_insert_rowid()"] + [_sql_value(v) for _, v in columns]
    return (
        f"INSERT INTO {meta_table} ({', '.join(cols)}) "
        f"VALUES ({', '.join(vals)});"
    )


def _sql_bool(value) -> int:
    if isinstance(value, bool):
        return int(value)
    return int(str(value).strip().casefold() in {"1", "true", "yes", "y"})


def _sql_value(value) -> str:
    """Render a Python value as a SQL literal."""
    if value is None or value == "":
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("'", "''")
    return f"'{text}'"


def _insert_sql(table: str, row: dict, is_anime: bool) -> str:
    """Build one INSERT for *row* against *table*."""
    if is_anime:
        columns = [
            "id", "title", "title_ja", "episodes", "status", "score", "notes",
            "tier", "rewatches", "episodes_watched", "favorite",
            "first_watched", "last_watched", "completed_date", "privacy",
        ]
        values = [
            row.get("internal_id"), row.get("title"), row.get("title_native"), row.get("episodes") or 0,
            row.get("status") or "plan_to_watch", row.get("score"),
            row.get("notes"), row.get("tier") or None, row.get("rewatches") or 0,
            row.get("episodes_watched") or 0,
            _sql_bool(row.get("favorite")),
            row.get("first_read"), row.get("last_read"),
            row.get("completed_date"), row.get("privacy") or "public",
        ]
    else:
        columns = [
            "id", "category", "title", "title_native", "synonyms", "format", "status",
            "tier", "rewatches", "chapters_read", "chapters", "volumes", "volumes_read",
            "favorite", "notes", "first_read", "last_read", "completed_date",
            "privacy", "origin_country",
        ]
        values = [
            row.get("internal_id"), row.get("media_type"), row.get("title"), row.get("title_native"),
            _split(row.get("synonyms")), row.get("media_format"),
            row.get("status") or "watching", row.get("tier") or None,
            row.get("rewatches") or 0, row.get("chapters_read") or 0,
            row.get("chapters") or 0, row.get("volumes") or 0,
            row.get("volumes_read") or 0,
            _sql_bool(row.get("favorite")),
            row.get("notes"), row.get("first_read"), row.get("last_read"),
            row.get("completed_date"), row.get("privacy") or "public",
            row.get("origin_country"),
        ]

    def render(values: list) -> str:
        return "(" + ", ".join(_sql_value(v) for v in values) + ")"

    # Metadata columns live in the companion table and are joined by the
    # importer, so only the base INSERT is emitted here.
    return f"INSERT INTO {table} ({', '.join(columns)}) VALUES {render(values)};"


def _split(value: str) -> str:
    """Render a list field as a compact JSON array for the dump."""
    import json

    if not value:
        return ""
    parts = [p.strip() for p in str(value).split(";") if p.strip()]
    return json.dumps(parts, ensure_ascii=False)


# ── Entry point ───────────────────────────────────────────────────

@dataclass
class ExportResult:
    """Outcome of one export."""

    path: Path
    row_count: int
    format: str
    columns: tuple[str, ...] = COLUMNS
    skipped_empty: int = 0

    def as_dict(self) -> dict:
        return {
            "path": str(self.path),
            "rows": self.row_count,
            "format": self.format,
        }


def export_library(
    path: str | Path,
    fmt: str = "csv",
    category: Optional[str] = None,
) -> ExportResult:
    """Export the library to *path* in ``csv`` / ``xlsx`` / ``sql`` format."""
    fmt = (fmt or "csv").strip().lower()
    rows = collect_rows(category)
    path = Path(path)

    if fmt == "csv":
        export_csv(path, rows)
    elif fmt == "xlsx":
        export_xlsx(path, rows)
    elif fmt == "ods":
        export_ods(path, rows)
    elif fmt == "sql":
        export_sql(path, rows)
    else:
        raise ValueError(f"Unsupported export format: {fmt!r}")

    logger.info("Exported %d rows to %s", len(rows), path)
    return ExportResult(path=path, row_count=len(rows), format=fmt)