"""Minimal, dependency-free ``.xlsx`` reader.

``.xlsx`` is a ZIP archive containing SpreadsheetML XML.  Rather than
pull in a third-party library, this module reads the parts it needs with
the standard library:

* ``xl/workbook.xml``      → sheet names and relationship ids
* ``xl/_rels/workbook.xml.rels`` → sheet name → part path
* ``xl/sharedStrings.xml`` → the shared-string table
* ``xl/worksheets/sheetN.xml``    → cell values, inline strings, formulas

Supports the common cell encodings: shared strings, inline strings,
numbers, booleans, dates (serial numbers), and empty cells.  Formula
cells use their cached ``<v>`` result, which is what Excel last wrote.
"""

from __future__ import annotations

import datetime
import logging
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

_NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_NS_REL_DOC = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_NS_REL_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"

# Excel serial-date origin (1900 system, with the well-known leap bug).
_EXCEL_EPOCH = datetime.datetime(1899, 12, 30)


class XlsxError(Exception):
    """Raised when a file cannot be read as a valid .xlsx workbook."""


def _tag(name: str) -> str:
    return f"{{{_NS_MAIN}}}{name}"


@dataclass
class Sheet:
    """A single worksheet: its name and raw rows of cell values."""

    name: str
    rows: list[list[Any]] = field(default_factory=list)

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def header_row(self) -> list[Any]:
        return self.rows[0] if self.rows else []

    def data_rows(self) -> list[list[Any]]:
        return self.rows[1:]


# ── Cell value decoding ───────────────────────────────────────────

def _col_index(ref: str) -> int:
    """Convert an A1-style cell reference to a 0-based column index."""
    m = re.match(r"([A-Za-z]+)", ref or "")
    if not m:
        return 0
    letters = m.group(1).upper()
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx - 1


def _is_date_format(style_idx: int, styles: dict[int, bool]) -> bool:
    """Whether a numeric cell with this style should render as a date."""
    return styles.get(style_idx, False)


def _numeric_to_date(value: float) -> Optional[datetime.datetime]:
    try:
        return _EXCEL_EPOCH + datetime.timedelta(days=float(value))
    except (OverflowError, ValueError):
        return None


def _load_date_styles(zf: zipfile.ZipFile) -> dict[int, bool]:
    """Map cellXfs index → whether that format is a date format."""
    try:
        raw = zf.read("xl/styles.xml")
    except KeyError:
        return {}
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return {}

    custom: dict[int, str] = {}
    for numfmt in root.iter(_tag("numFmt")):
        try:
            custom[int(numfmt.get("numFmtId", "-1"))] = numfmt.get("formatCode", "")
        except (TypeError, ValueError):
            continue

    builtin_date_ids = set(range(14, 23)) | {45, 46, 47} | set(range(27, 37))

    def _is_date_code(code: str) -> bool:
        code = re.sub(r"\[[^\]]*\]", "", code)  # drop [Red], [h], …
        code = re.sub(r'"[^"]*"', "", code)  # drop literal text
        return bool(
            re.search(r"[dmyhs]", code, re.IGNORECASE)
            and not re.fullmatch(r"[#0.,%\s]*", code)
        )

    result: dict[int, bool] = {}
    cell_xfs = root.find(_tag("cellXfs"))
    if cell_xfs is None:
        return result
    for idx, xf in enumerate(cell_xfs.findall(_tag("xf"))):
        try:
            fmt_id = int(xf.get("numFmtId", "0"))
        except ValueError:
            fmt_id = 0
        if fmt_id in custom:
            result[idx] = _is_date_code(custom[fmt_id])
        else:
            result[idx] = fmt_id in builtin_date_ids
    return result


def _load_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        raw = zf.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        logger.warning("Could not parse sharedStrings.xml: %s", exc)
        return []

    strings: list[str] = []
    for si in root.findall(_tag("si")):
        # A shared string may be split across multiple <r><t> runs.
        parts = [t.text or "" for t in si.iter(_tag("t"))]
        strings.append("".join(parts))
    return strings


def _sheet_paths(zf: zipfile.ZipFile) -> list[tuple[str, str]]:
    """Return [(sheet_name, zip_path)] in workbook order."""
    try:
        wb_raw = zf.read("xl/workbook.xml")
    except KeyError as exc:
        raise XlsxError("Not a valid .xlsx file: xl/workbook.xml is missing") from exc

    try:
        wb = ET.fromstring(wb_raw)
    except ET.ParseError as exc:
        raise XlsxError(f"Malformed workbook.xml: {exc}") from exc

    # name → r:id
    rid_to_name: dict[str, str] = {}
    sheets_el = wb.find(_tag("sheets"))
    if sheets_el is None:
        return []
    for sh in sheets_el.findall(_tag("sheet")):
        rid = sh.get(f"{{{_NS_REL_DOC}}}id")
        name = sh.get("name", "")
        if rid:
            rid_to_name[rid] = name

    # r:id → zip path
    rid_to_target: dict[str, str] = {}
    try:
        rels_raw = zf.read("xl/_rels/workbook.xml.rels")
        rels = ET.fromstring(rels_raw)
        for rel in rels.findall(f"{{{_NS_REL_PKG}}}Relationship"):
            rid = rel.get("Id", "")
            target = rel.get("Target", "")
            if rid and target:
                if target.startswith("/"):
                    path = target.lstrip("/")
                elif target.startswith("xl/"):
                    path = target
                else:
                    path = f"xl/{target}"
                rid_to_target[rid] = path.replace("/./", "/")
    except (KeyError, ET.ParseError) as exc:
        logger.warning("Could not read workbook relationships: %s", exc)

    # Fall back to positional sheetN.xml when relationships are unusable.
    available = set(zf.namelist())
    out: list[tuple[str, str]] = []
    for rid, name in rid_to_name.items():
        path = rid_to_target.get(rid)
        if path and path in available:
            out.append((name, path))
    if not out:
        for idx in range(1, len(zf.namelist()) + 1):
            path = f"xl/worksheets/sheet{idx}.xml"
            if path in available:
                out.append((path.rsplit("/", 1)[-1].removesuffix(".xml"), path))
    return out


def _parse_sheet(
    zf: zipfile.ZipFile,
    path: str,
    shared: list[str],
    date_styles: dict[int, bool],
) -> list[list[Any]]:
    """Parse one worksheet part into a dense list of row value-lists."""
    try:
        root = ET.fromstring(zf.read(path))
    except (KeyError, ET.ParseError) as exc:
        raise XlsxError(f"Could not read worksheet {path}: {exc}") from exc

    sheet_data = root.find(_tag("sheetData"))
    if sheet_data is None:
        return []

    rows: list[list[Any]] = []
    for row_el in sheet_data.findall(_tag("row")):
        cells: dict[int, Any] = {}
        max_col = -1
        # Position within <row> is the authoritative column order.  The
        # r="A1" reference is only a hint — some writers omit it or emit
        # duplicated refs, so fall back to ordinal position.
        for ordinal, c in enumerate(row_el.findall(_tag("c"))):
            ref = c.get("r")
            col = _col_index(ref) if ref else -1
            if col < 0 or col in cells:
                col = ordinal
                while col in cells:
                    col += 1
            max_col = max(max_col, col)
            cells[col] = _decode_cell(c, shared, date_styles)
        width = max_col + 1
        rows.append([cells.get(i, "") for i in range(width)])
    return rows


def _decode_cell(
    c: ET.Element, shared: list[str], date_styles: dict[int, bool]
) -> Any:
    """Decode a single ``<c>`` element into a Python value."""
    ctype = c.get("t", "n")

    # Inline string: <is><t>text</t></is>
    if ctype == "inlineStr":
        is_el = c.find(_tag("is"))
        if is_el is None:
            return ""
        return "".join(t.text or "" for t in is_el.iter(_tag("t")))

    v_el = c.find(_tag("v"))
    raw = v_el.text if v_el is not None else None
    if raw is None:
        # Formula cell with no cached result.
        f_el = c.find(_tag("f"))
        return "" if f_el is None else ""

    if ctype == "s":  # shared string index
        try:
            return shared[int(raw)]
        except (ValueError, IndexError):
            return ""

    if ctype == "b":  # boolean
        return raw not in ("0", "", "false", "FALSE")

    if ctype in ("str", "e"):  # formula string / error
        return raw

    if ctype == "inlineStr":  # pragma: no cover - handled above
        return raw

    # Numeric (n is the default).
    try:
        num = float(raw)
    except ValueError:
        return raw
    try:
        style_idx = int(c.get("s", "-1"))
    except ValueError:
        style_idx = -1
    if _is_date_format(style_idx, date_styles):
        dt = _numeric_to_date(num)
        if dt is not None:
            return dt.strftime("%Y-%m-%d")
    # Keep integers integral so "220" doesn't become "220.0".
    if num.is_integer() and abs(num) < 1e15:
        return int(num)
    return num


# ── Public API ────────────────────────────────────────────────────

def read_workbook(path: str | Path, sheet: Optional[str] = None) -> Sheet:
    """Read a ``.xlsx`` workbook and return its first (or named) sheet."""
    path = Path(path)
    if not path.exists():
        raise XlsxError(f"File not found: {path}")

    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise XlsxError(
            f"{path.name} is not a valid .xlsx file (not a ZIP archive). "
            "Legacy .xls files are not supported."
        ) from exc

    with zf:
        shared = _load_shared_strings(zf)
        date_styles = _load_date_styles(zf)
        sheets = _sheet_paths(zf)
        if not sheets:
            raise XlsxError(f"No worksheets found in {path.name}")

        target = None
        if sheet is not None:
            for name, spath in sheets:
                if name.casefold() == sheet.casefold():
                    target = (name, spath)
                    break
            if target is None:
                raise XlsxError(
                    f"Sheet {sheet!r} not found. Available: "
                    + ", ".join(n for n, _ in sheets)
                )
        else:
            target = sheets[0]

        name, spath = target
        rows = _parse_sheet(zf, spath, shared, date_styles)

    return Sheet(name=name, rows=rows)


def list_sheets(path: str | Path) -> list[str]:
    """Return the worksheet names in *path*."""
    path = Path(path)
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise XlsxError(f"{path.name} is not a valid .xlsx file") from exc
    with zf:
        return [n for n, _ in _sheet_paths(zf)]


def iter_rows(path: str | Path, sheet: Optional[str] = None) -> Iterator[list[Any]]:
    """Yield each row of the target sheet, skipping the header."""
    s = read_workbook(path, sheet)
    yield from s.data_rows()