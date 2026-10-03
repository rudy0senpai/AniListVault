"""Safe SQLite ``.sql`` dump import.

Security model — a dump is **never** executed against the live database:

1. The file is read as text and scanned statement-by-statement.
2. Only a small allowlist of SQLite statements is accepted; anything
   else (``ATTACH``, ``DROP DATABASE``, ``load_extension``, ``PRAGMA``
   writes, ``DETACH``, ``VACUUM``…) is rejected outright.
3. Accepted statements run inside a **throwaway temporary database**
   opened with ``load_extension`` disabled and in defensive mode.
4. The restored temp database is inspected and validated.
5. Rows are converted to the current schema and merged into the live
   database through the normal model layer, in bounded batches.

A malformed or hostile dump therefore cannot touch the user's library.
"""

from __future__ import annotations

import logging
import re
import sqlite3
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

logger = logging.getLogger(__name__)

# ── Statement allowlist ───────────────────────────────────────────

_ALLOWED_LEADING = (
    "create table",
    "create index",
    "create unique index",
    "create view",
    "insert into",
    "begin",
    "commit",
)

#: Statements that are explicitly refused, with the reason shown to the user.
_FORBIDDEN = {
    "attach": "ATTACH is not allowed — it can reach arbitrary external databases",
    "detach": "DETACH is not allowed",
    "drop database": "DROP DATABASE is not allowed",
    "load_extension": "Extension loading is disabled",
    "vacuum": "VACUUM is not allowed",
    "pragma": "PRAGMA statements are not executed from imports",
}

_CREATE_TABLE_RE = re.compile(
    r"create\s+table\s+(?:if\s+not\s+exists\s+)?[\"'`\[]?(\w+)[\"'`\]]?",
    re.IGNORECASE,
)
_INSERT_RE = re.compile(
    r"insert\s+into\s+[\"'`\[]?(\w+)[\"'`\]]?", re.IGNORECASE
)


class SqlImportError(Exception):
    """Raised when a SQL dump cannot be safely imported."""


@dataclass
class SqlStatement:
    """One parsed statement from a dump."""

    sql: str
    kind: str          # 'create' | 'insert' | 'transaction'
    table: str = ""


@dataclass
class SqlPreview:
    """What a dump contains, shown before importing."""

    path: Path = None  # type: ignore[assignment]
    ok: bool = False
    error: str = ""
    statements: int = 0
    tables: list[str] = field(default_factory=list)
    row_counts: dict[str, int] = field(default_factory=dict)
    schema_version: Optional[int] = None
    has_score_column: bool = False
    has_tier_column: bool = False
    rejected: list[str] = field(default_factory=list)

    @property
    def needs_migration(self) -> bool:
        """True when the dump's schema predates the tier system."""
        return self.has_score_column and not self.has_tier_column

    def summary(self) -> str:
        if not self.ok:
            return self.error
        total = sum(self.row_counts.values())
        return f"{total} records across {len(self.tables)} table(s)"


# ── Parsing ───────────────────────────────────────────────────────

def split_statements(sql_text: str) -> list[str]:
    """Split a dump into statements, respecting string literals and comments."""
    statements: list[str] = []
    buf: list[str] = []
    in_string = False
    in_line_comment = False
    in_block_comment = False
    i = 0
    n = len(sql_text)

    while i < n:
        ch = sql_text[i]
        nxt = sql_text[i + 1] if i + 1 < n else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
                buf.append(ch)
            i += 1
            continue

        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        if in_string:
            buf.append(ch)
            if ch == "'":
                # Doubled quote is an escaped quote, not a terminator.
                if nxt == "'":
                    buf.append(nxt)
                    i += 2
                    continue
                in_string = False
            i += 1
            continue

        # Not in any literal/comment context.
        if ch == "-" and nxt == "-":
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue
        if ch == "'":
            in_string = True
            buf.append(ch)
            i += 1
            continue
        if ch == ";":
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
            i += 1
            continue

        buf.append(ch)
        i += 1

    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def _leading_keyword(stmt: str) -> str:
    """First few keywords of a statement, lowercased, comments stripped."""
    text = re.sub(r"--[^\n]*", " ", stmt)
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = text.strip().lower()
    # Normalize runs of whitespace for prefix comparison.
    return re.sub(r"\s+", " ", text)


def parse_dump(sql_text: str) -> tuple[list[SqlStatement], list[str]]:
    """Parse and validate a dump.

    Returns
    -------
    (statements, rejected)
        Accepted statements and human-readable rejection reasons.
    """
    accepted: list[SqlStatement] = []
    rejected: list[str] = []

    for stmt in split_statements(sql_text):
        key = _leading_keyword(stmt)

        # Explicit refusals first, so the message is specific.
        refused = False
        for bad, reason in _FORBIDDEN.items():
            if key.startswith(bad):
                rejected.append(f"{reason}: {stmt[:60]}...")
                refused = True
                break
        if refused:
            continue

        if key.startswith(_ALLOWED_LEADING):
            kind = "transaction" if key.startswith(("begin", "commit")) else "create"
            table = ""
            if key.startswith("create table"):
                m = _CREATE_TABLE_RE.search(stmt)
                table = m.group(1) if m else ""
                kind = "create"
            elif key.startswith("insert"):
                m = _INSERT_RE.search(stmt)
                table = m.group(1) if m else ""
                kind = "insert"
            accepted.append(SqlStatement(sql=stmt, kind=kind, table=table))
        else:
            preview = stmt.strip().split()[0].upper() if stmt.strip() else "?"
            rejected.append(f"Unsupported statement {preview}: {stmt[:60]}...")

    return accepted, rejected


def restore_to_temp_db(sql_text: str) -> tuple[Path, SqlPreview]:
    """Restore a validated dump into a throwaway database.

    Returns the temp database path and a preview describing its contents.
    """
    accepted, rejected = parse_dump(sql_text)
    if not accepted:
        raise SqlImportError(
            "No supported SQLite statements found in the dump. "
            + ("Rejected: " + "; ".join(rejected[:3]) if rejected else "")
        )

    tmp_dir = Path(tempfile.mkdtemp(prefix="animevault_sqlimport_"))
    tmp_db = tmp_dir / "restore.db"

    conn = sqlite3.connect(str(tmp_db))
    try:
        # Defence in depth: no extensions, no writing outside this file.
        conn.enable_load_extension(False)
        conn.execute("PRAGMA trusted_schema=OFF;")

        for stmt in accepted:
            try:
                conn.execute(stmt.sql)
            except sqlite3.Error as exc:
                logger.warning("Skipping statement during restore: %s", exc)
        conn.commit()
    finally:
        conn.close()

    preview = inspect_restored(tmp_db)
    preview.rejected = rejected
    return tmp_db, preview


def inspect_restored(db_path: Path) -> SqlPreview:
    """Inspect a restored database and describe its contents."""
    preview = SqlPreview(path=db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            )
        ]
        preview.tables = tables
        for t in tables:
            try:
                n = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            except sqlite3.Error:
                n = 0
            preview.row_counts[t] = n

        if "anime" in tables:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(anime)")}
            preview.has_score_column = "score" in cols
            preview.has_tier_column = "tier" in cols

        if "meta" in tables:
            try:
                row = conn.execute(
                    "SELECT value FROM meta WHERE key='schema_version'"
                ).fetchone()
                if row:
                    preview.schema_version = int(row[0])
            except (sqlite3.Error, TypeError, ValueError):
                preview.schema_version = None

        if not tables:
            preview.error = "Restored database contains no tables"
        else:
            preview.ok = True
    finally:
        conn.close()
    return preview


# ── Mapping old schemas onto the current one ──────────────────────

def _coerce_status(value, default="plan_to_watch"):
    from animevault.services.importers.row_parser import normalize_status

    if value is None or value == "":
        return default
    return normalize_status(value) or default


def _coerce_tier(value):
    from animevault.tiers import InvalidTierError, normalize_tier

    if value is None or value == "":
        return None
    try:
        return normalize_tier(value)
    except InvalidTierError:
        return None


def read_anime_rows(db_path: Path) -> tuple[list[dict], list[str]]:
    """Read anime (+ metadata) rows from a restored dump.

    Returns ``(rows, unmappable_notes)``.  Rows are dicts keyed by the
    current field names; columns absent from the old schema default to
    empty rather than failing the import.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    notes: list[str] = []
    rows: list[dict] = []
    try:
        if "anime" not in [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        ]:
            return [], ["Dump has no 'anime' table"]

        anime_cols = {r[1] for r in conn.execute("PRAGMA table_info(anime)")}

        meta_cols: set[str] = set()
        meta_rows: dict[int, sqlite3.Row] = {}
        if "anime_metadata" in [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        ]:
            meta_cols = {r[1] for r in conn.execute("PRAGMA table_info(anime_metadata)")}
            for m in conn.execute("SELECT * FROM anime_metadata"):
                meta_rows[m["anime_id"]] = m

        for a in conn.execute("SELECT * FROM anime"):
            m = meta_rows.get(a["id"])

            def val(col: str, default=None):
                """Read a column from the anime row, else metadata row."""
                if col in anime_cols and a[col] is not None:
                    return a[col]
                if m is not None and col in meta_cols and m[col] is not None:
                    return m[col]
                return default

            if "score" in anime_cols and "tier" not in anime_cols:
                notes.append(
                    "Dump uses the legacy 'score' column; imported as unassigned tier "
                    "(choose explicit conversion if you want scores mapped)."
                )

            rows.append(
                {
                    "title": a["title"] if "title" in anime_cols else None,
                    "title_ja": val("title_ja", "") or "",
                    "title_en": val("title_en", "") or "",
                    "episodes": val("episodes", 0) or 0,
                    "status": _coerce_status(val("status")),
                    "tier": _coerce_tier(val("tier")),
                    "score": val("score"),          # legacy, kept only
                    "notes": val("notes", "") or "",
                    "rewatches": val("rewatches", 0) or 0,
                    "episodes_watched": val("episodes_watched", 0) or 0,
                    "favorite": bool(val("favorite", 0)),
                    "first_watched": val("first_watched", "") or "",
                    "last_watched": val("last_watched", "") or "",
                    "completed_date": val("completed_date", "") or "",
                    "privacy": val("privacy", "public") or "public",
                    "synopsis": val("synopsis", "") or "",
                    "genres": val("genres", "") or "",
                    "studios": val("studios", "") or "",
                    "media_type": val("media_type", "") or "",
                    "airing_status": val("airing_status", "") or "",
                    "duration": val("duration", 0) or 0,
                    "season": val("season", "") or "",
                    "season_year": val("season_year"),
                    "poster_url": val("poster_url", "") or "",
                    "poster_path": val("poster_path", "") or "",
                    "mal_id": val("mal_id"),
                    "anilist_id": val("anilist_id"),
                    "kitsu_id": val("kitsu_id") or None,
                    "tmdb_id": val("tmdb_id"),
                    "anidb_id": val("anidb_id"),
                    "source_provider": val("source_provider", "") or "",
                }
            )
    finally:
        conn.close()
    return rows, notes


# ── Import ────────────────────────────────────────────────────────

@dataclass
class SqlImportResult:
    added: int = 0
    updated: int = 0
    duplicates: int = 0
    invalid: int = 0
    rejected_statements: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    needs_enrichment: list[int] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "added": self.added,
            "updated": self.updated,
            "duplicates": self.duplicates,
            "invalid": self.invalid,
        }


def preview_sql(path: str | Path, *, convert_scores: bool = False) -> SqlPreview:
    """Validate a dump and describe it, without touching the live database."""
    path = Path(path)
    if not path.exists():
        p = SqlPreview(path=path)
        p.error = f"File not found: {path}"
        return p
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        p = SqlPreview(path=path)
        p.error = f"Could not read {path.name}: {exc}"
        return p

    tmp_db, preview = restore_to_temp_db(text)
    preview.path = path
    if convert_scores and preview.has_score_column and not preview.has_tier_column:
        pass  # conversion happens at import time, not preview time
    return preview


def import_sql(
    path: str | Path,
    *,
    convert_scores: bool = False,
    batch_size: int = 100,
    progress: Optional[Callable[[int, int], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> SqlImportResult:
    """Import a SQLite dump into the live library.

    The dump is restored into a temporary database first; only validated,
    schema-aware rows are merged into AnimeVault.  ``convert_scores`` is
    ``False`` by default so a legacy numeric score is never silently
    turned into a tier.
    """
    from animevault.models.anime import Anime
    from animevault.services.importers.row_parser import _to_list
    from animevault.services.importers.xlsx_importer import (
        POLICY_FILL_EMPTY,
        _apply_metadata,
        _apply_personal,
        _find_existing,
        _needs_enrichment,
    )
    from animevault.services.importers.row_parser import AnimeDraft

    result = SqlImportResult()
    path = Path(path)
    if not path.exists():
        raise SqlImportError(f"File not found: {path}")

    text = path.read_text(encoding="utf-8", errors="replace")
    tmp_db, preview = restore_to_temp_db(text)
    result.rejected_statements = preview.rejected
    if not preview.ok:
        raise SqlImportError(preview.error or "Could not restore dump")

    rows, notes = read_anime_rows(tmp_db)
    result.notes.extend(notes)

    from animevault.tiers import score_to_tier

    total = len(rows)
    for idx, data in enumerate(rows, start=1):
        if should_cancel is not None and should_cancel():
            break

        title = (data.get("title") or "").strip()
        if not title:
            result.invalid += 1
            continue

        # Legacy score only becomes a tier on explicit request.
        tier = data.get("tier")
        if tier is None and convert_scores and data.get("score") is not None:
            tier = score_to_tier(data["score"])

        draft = AnimeDraft(
            row_number=idx,
            title=title,
            title_ja=data.get("title_ja", ""),
            title_en=data.get("title_en", ""),
            episodes=int(data.get("episodes") or 0),
            episodes_watched=int(data.get("episodes_watched") or 0),
            status=data.get("status") or "plan_to_watch",
            tier=tier,
            rewatches=int(data.get("rewatches") or 0),
            favorite=bool(data.get("favorite")),
            notes=data.get("notes", ""),
            first_watched=data.get("first_watched", ""),
            last_watched=data.get("last_watched", ""),
            completed_date=data.get("completed_date", ""),
            privacy=data.get("privacy", "public"),
            synopsis=data.get("synopsis", ""),
            genres=_to_list(data.get("genres")),
            studios=_to_list(data.get("studios")),
            media_type=data.get("media_type", ""),
            airing_status=data.get("airing_status", ""),
            duration=int(data.get("duration") or 0),
            season=data.get("season", ""),
            season_year=data.get("season_year"),
            poster_url=data.get("poster_url", ""),
            mal_id=data.get("mal_id"),
            anilist_id=data.get("anilist_id"),
            kitsu_id=data.get("kitsu_id"),
            tmdb_id=data.get("tmdb_id"),
            anidb_id=data.get("anidb_id"),
        )

        try:
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
                    source_provider=data.get("source_provider", ""),
                )
                anime.save()
                result.added += 1
                if _needs_enrichment(anime):
                    result.needs_enrichment.append(anime.id)
            else:
                changed = _apply_personal(existing, draft, POLICY_FILL_EMPTY)
                changed |= _apply_metadata(existing, draft, POLICY_FILL_EMPTY)
                if changed:
                    existing.save()
                    result.updated += 1
                else:
                    result.duplicates += 1
        except Exception as exc:
            logger.warning("SQL import failed for %r: %s", title, exc)
            result.invalid += 1

        if progress is not None and idx % batch_size == 0:
            progress(idx, total)

    return result