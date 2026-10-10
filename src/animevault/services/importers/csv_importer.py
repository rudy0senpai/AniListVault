"""CSV import — reader plus the same preview/batch flow as XLSX."""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from animevault.services.importers.column_mapper import MappingReport, build_mapping
from animevault.services.importers.row_parser import ParsedRows, parse_rows
from animevault.services.importers.xlsx_preview import ImportPreview

logger = logging.getLogger(__name__)


class CsvError(Exception):
    """Raised when a file cannot be read as CSV."""


def _decode(path: Path) -> str:
    """Read a text file, tolerating the encodings spreadsheets use."""
    raw = path.read_bytes()
    # utf-8-sig strips the BOM Excel writes.
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise CsvError(f"Could not decode {path.name} as text")


def _sniff_dialect(sample: str) -> str:
    """Pick the delimiter, preferring comma but honouring tabs/semicolons."""
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except csv.Error:
        # Fall back to whichever candidate appears most on the header line.
        first = sample.splitlines()[0] if sample.splitlines() else ""
        counts = {d: first.count(d) for d in (",", ";", "\t", "|")}
        best = max(counts, key=lambda k: counts[k])
        return best if counts[best] else ","


def read_csv(path: str | Path) -> list[list[str]]:
    """Return every row of a CSV file as a list of strings."""
    path = Path(path)
    if not path.exists():
        raise CsvError(f"File not found: {path}")

    text = _decode(path)
    if not text.strip():
        return []

    delimiter = _sniff_dialect(text[:8192])
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    return [list(row) for row in reader]


def preview_csv(
    path: str | Path,
    sheet: Optional[str] = None,
    invalid_tier_policy: str = "unassigned",
) -> ImportPreview:
    """Read and validate a CSV file without writing anything."""
    path = Path(path)
    preview = ImportPreview(path=path)

    try:
        rows = read_csv(path)
    except CsvError as exc:
        preview.error = str(exc)
        return preview
    except Exception as exc:  # unexpected parse failure
        preview.error = f"Could not read {path.name}: {exc}"
        return preview

    preview.sheet_name = "CSV"
    if not rows:
        preview.error = "The file is empty."
        return preview

    # Skip leading blank rows so the real header is found.
    header_idx = 0
    for idx, row in enumerate(rows[:10]):
        if any(str(v).strip() for v in row):
            header_idx = idx
            break

    headers = rows[header_idx]
    data_rows = rows[header_idx + 1 :]

    preview.mapping = build_mapping(headers)
    preview.total_rows = len(data_rows)
    preview.parsed = parse_rows(
        data_rows,
        preview.mapping,
        start_row_number=header_idx + 2,
        invalid_tier_policy=invalid_tier_policy,
    )
    return preview