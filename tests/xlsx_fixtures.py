"""Helpers for building real .xlsx files in tests without a third-party lib.

An ``.xlsx`` file is a ZIP of SpreadsheetML XML parts.  These helpers emit
a minimal but genuinely valid workbook so the reader under test parses a
real file rather than a mock.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any, Iterable, Sequence

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL_DOC = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def col_letter(index: int) -> str:
    """0-based column index → spreadsheet letters (0 → 'A')."""
    letters = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return letters


def _esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _cell_xml(ref: str, value: Any, shared: dict[str, int]) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return f'<c r="{ref}" t="b"><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float)):
        return f'<c r="{ref}"><v>{value}</v></c>'
    text = str(value)
    if text in shared:
        return f'<c r="{ref}" t="s"><v>{shared[text]}</v></c>'
    return f'<c r="{ref}" t="inlineStr"><is><t>{_esc(text)}</t></is></c>'


def write_xlsx(
    path: str | Path,
    headers: Sequence[Any],
    rows: Iterable[Sequence[Any]],
    sheet_name: str = "Sheet1",
    use_shared_strings: bool = False,
) -> Path:
    """Write a valid single-sheet .xlsx file.

    Parameters
    ----------
    headers:
        First row of the sheet.
    rows:
        Subsequent data rows.
    use_shared_strings:
        Emit text cells via ``sharedStrings.xml`` instead of inline
        strings, exercising the other decode path.
    """
    path = Path(path)
    headers = list(headers)
    rows = [list(r) for r in rows]

    # Build the shared-string table when asked.
    shared: dict[str, int] = {}
    shared_list: list[str] = []
    if use_shared_strings:
        seen: list[str] = []
        for row in [headers] + rows:
            for v in row:
                if isinstance(v, str) and v != "" and v not in seen:
                    seen.append(v)
        shared_list = seen
        shared = {s: i for i, s in enumerate(shared_list)}

    def build_row(values: Sequence[Any], row_num: int) -> str:
        cells = []
        for col, value in enumerate(values):
            ref = f"{col_letter(col)}{row_num}"
            xml = _cell_xml(ref, value, shared)
            if xml:
                cells.append(xml)
        return f'<row r="{row_num}">{"".join(cells)}</row>'

    sheet_rows = [build_row(headers, 1)]
    for i, row in enumerate(rows, start=2):
        sheet_rows.append(build_row(row, i))

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<worksheet xmlns="{NS_MAIN}">'
        f'<sheetData>{"".join(sheet_rows)}</sheetData>'
        "</worksheet>"
    )

    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<workbook xmlns="{NS_MAIN}" xmlns:r="{NS_REL_DOC}">'
        f'<sheets><sheet name="{_esc(sheet_name)}" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )

    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Target="worksheets/sheet1.xml" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/worksheet"/>'
        "</Relationships>"
    )

    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<styleSheet xmlns="{NS_MAIN}">'
        '<numFmts count="0"/>'
        '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellXfs>'
        "</styleSheet>"
    )

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-'
        'officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-'
        'officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-'
        'officedocument.spreadsheetml.styles+xml"/>'
        "</Types>"
    )

    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Target="xl/workbook.xml" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/officeDocument"/>'
        "</Relationships>"
    )

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", rels_xml)
        zf.writestr("xl/styles.xml", styles_xml)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        if use_shared_strings:
            items = "".join(f"<si><t>{_esc(s)}</t></si>" for s in shared_list)
            sst_xml = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<sst xmlns="{NS_MAIN}" count="{len(shared_list)}" '
                f'uniqueCount="{len(shared_list)}">{items}</sst>'
            )
            zf.writestr("xl/sharedStrings.xml", sst_xml)

    return path