"""XLSX preview: read a file, map its headers, parse rows — without writing.

The UI shows this before committing, so a large import is never a surprise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from animevault.services.importers.column_mapper import MappingReport, build_mapping
from animevault.services.importers.row_parser import (
    AnimeDraft,
    ParsedRows,
    RowError,
    parse_rows,
)
from animevault.services.importers.xlsx_reader import Sheet, XlsxError, list_sheets, read_workbook


@dataclass
class ImportPreview:
    """Everything the preview dialog needs before the user commits."""

    path: Path
    sheet_name: str = ""
    available_sheets: list[str] = field(default_factory=list)
    total_rows: int = 0
    mapping: Optional[MappingReport] = None
    parsed: Optional[ParsedRows] = None
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error

    @property
    def valid_rows(self) -> int:
        return len(self.parsed.drafts) if self.parsed else 0

    @property
    def invalid_rows(self) -> int:
        return len(self.parsed.errors) if self.parsed else 0

    @property
    def mapped_columns(self) -> list[str]:
        return self.mapping.mapped_columns if self.mapping else []

    @property
    def unmapped_columns(self) -> list[str]:
        return self.mapping.unmapped_columns if self.mapping else []

    @property
    def invalid_tier_errors(self) -> list[RowError]:
        return self.parsed.invalid_tiers if self.parsed else []

    @property
    def has_title_column(self) -> bool:
        if not self.mapping:
            return False
        return "title" in self.mapping.mapped_fields

    def summary(self) -> str:
        if not self.ok:
            return self.error
        return (
            f"{self.total_rows} rows · {self.valid_rows} valid · "
            f"{self.invalid_rows} invalid"
        )


def preview_xlsx(
    path: str | Path,
    sheet: Optional[str] = None,
    invalid_tier_policy: str = "unassigned",
) -> ImportPreview:
    """Read and validate an .xlsx file without writing anything."""
    path = Path(path)
    preview = ImportPreview(path=path)

    try:
        preview.available_sheets = list_sheets(path)
        data: Sheet = read_workbook(path, sheet)
    except XlsxError as exc:
        preview.error = str(exc)
        return preview
    except Exception as exc:  # unexpected parse failure
        preview.error = f"Could not read {path.name}: {exc}"
        return preview

    preview.sheet_name = data.name

    # Skip leading blank rows so the real header is found.
    rows = data.rows
    header_idx = 0
    for idx, row in enumerate(rows[:10]):
        if any(str(v).strip() for v in row if v is not None):
            header_idx = idx
            break
    headers = rows[header_idx] if rows else []
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