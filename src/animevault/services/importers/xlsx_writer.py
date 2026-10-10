"""Write a real ``.xlsx`` workbook without a third-party dependency.

The counterpart of :mod:`animevault.services.importers.xlsx_reader`: it
emits the same minimal SpreadsheetML parts that module parses, so a file
written here is readable by our own importer and by Excel.
"""

from __future__ import annotations

import zipfile
import datetime as dt
from pathlib import Path
from typing import Any, Sequence

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


def _clean(value: Any) -> str:
    """Strip characters XML cannot carry."""
    # Control characters are illegal in XML 1.0 and make the file unreadable.
    return "".join(
        ch for ch in str(value) if ch == "\n" or ch == "\t" or ord(ch) >= 32
    )


def _cell_xml(ref: str, value: Any, shared: dict[str, int]) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, dt.datetime):
        serial = (value - dt.datetime(1899, 12, 30)).total_seconds() / 86400
        return f'<c r="{ref}" s="3"><v>{serial:.12g}</v></c>'
    if isinstance(value, dt.date):
        serial = (value - dt.date(1899, 12, 30)).days
        return f'<c r="{ref}" s="2"><v>{serial}</v></c>'
    if isinstance(value, bool):
        return f'<c r="{ref}" t="b"><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float)):
        return f'<c r="{ref}"><v>{value}</v></c>'
    text = _clean(value)
    if text in shared:
        return f'<c r="{ref}" t="s"><v>{shared[text]}</v></c>'
    return f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{_esc(text)}</t></is></c>'


def write_sheet(
    path: str | Path,
    headers: Sequence[Any],
    rows: Sequence[Sequence[Any]],
    sheet_name: str = "Sheet1",
) -> Path:
    """Write *rows* under *headers* to a single-sheet .xlsx file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    headers = list(headers)
    rows = [list(r) for r in rows]
    if any(len(row) != len(headers) for row in rows):
        raise ValueError("XLSX row width does not match header width")

    # Shared-string table: every text cell, de-duplicated in first-seen order.
    seen: list[str] = []
    for value in [headers] + rows:
        for v in value:
            if isinstance(v, str) and v != "" and v not in seen:
                seen.append(_clean(v))
    shared = {s: i for i, s in enumerate(seen)}

    def build_row(values: Sequence[Any], row_num: int, style: str = "") -> str:
        cells = []
        for col, value in enumerate(values):
            xml = _cell_xml(f"{col_letter(col)}{row_num}", value, shared)
            if xml:
                if style:
                    # Insert the style attribute into the <c> element.
                    xml = xml.replace("<c ", f'<c {style} ', 1)
                cells.append(xml)
        return f'<row r="{row_num}">{"".join(cells)}</row>'

    # Style 1 is the bold header defined in styles_xml.
    sheet_rows = [build_row(headers, 1, style='s="1"')]
    for i, row in enumerate(rows, start=2):
        sheet_rows.append(build_row(row, i))

    widths = [min(36, max(12, len(str(header)) + 2)) for header in headers]
    cols_xml = "<cols>" + "".join(
        f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
        for index, width in enumerate(widths, start=1)
    ) + "</cols>"
    last_column = col_letter(len(headers) - 1) if headers else "A"
    last_row = len(rows) + 1
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<worksheet xmlns="{NS_MAIN}">'
        # A frozen header row keeps long exports readable.
        '<sheetViews><sheetView workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        "</sheetView></sheetViews>"
        f"{cols_xml}<sheetData>{''.join(sheet_rows)}</sheetData>"
        f'<autoFilter ref="A1:{last_column}{last_row}"/>'
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
        '<Relationship Id="rId1" Target="worksheets/sheet1.xml" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/>'
        "</Relationships>"
    )

    # Excel treats styles.xml as invalid without the fonts/fills/borders
    # sections and offers to "repair" the workbook, discarding cell text.
    # Index 0 is default; 1 is the bold header; 2/3 are date and datetime.
    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<styleSheet xmlns="{NS_MAIN}">'
        '<numFmts count="2">'
        '<numFmt numFmtId="164" formatCode="yyyy-mm-dd"/>'
        '<numFmt numFmtId="165" formatCode="yyyy-mm-dd hh:mm:ss"/>'
        '</numFmts>'
        '<fonts count="2">'
        '<font><sz val="11"/><color theme="1"/><name val="Calibri"/>'
        '<family val="2"/></font>'
        '<font><b/><sz val="11"/><color theme="1"/><name val="Calibri"/>'
        '<family val="2"/></font>'
        "</fonts>"
        '<fills count="2">'
        '<fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        "</fills>"
        '<borders count="1">'
        "<border><left/><right/><top/><bottom/><diagonal/></border>"
        "</borders>"
        '<cellStyleXfs count="1">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>'
        "</cellStyleXfs>"
        '<cellXfs count="4">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
        '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
        '<xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
        "</cellXfs>"
        '<cellStyles count="1">'
        '<cellStyle name="Normal" xfId="0" builtinId="0"/>'
        "</cellStyles>"
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
        '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-'
        'officedocument.spreadsheetml.sharedStrings+xml"/>'
        "</Types>"
    )

    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Target="xl/workbook.xml" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"/>'
        "</Relationships>"
    )

    sst_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<sst xmlns="{NS_MAIN}" count="{len(seen)}" uniqueCount="{len(seen)}">'
        + "".join(f"<si><t xml:space=\"preserve\">{_esc(s)}</t></si>" for s in seen)
        + "</sst>"
    )

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", rels_xml)
        zf.writestr("xl/styles.xml", styles_xml)
        zf.writestr("xl/sharedStrings.xml", sst_xml)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)

    return path