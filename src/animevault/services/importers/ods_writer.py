"""Minimal ODS spreadsheet writer for AniListVault exports."""

from __future__ import annotations

import datetime as dt
import math
import zipfile
from pathlib import Path
from typing import Any, Sequence
from xml.etree import ElementTree as ET

MIMETYPE = "application/vnd.oasis.opendocument.spreadsheet"
NS = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "style": "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "fo": "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0",
    "meta": "urn:oasis:names:tc:opendocument:xmlns:meta:1.0",
    "manifest": "urn:oasis:names:tc:opendocument:xmlns:manifest:1.0",
}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)


def _q(prefix: str, name: str) -> str:
    return f"{{{NS[prefix]}}}{name}"


def _cell(row: ET.Element, value: Any) -> None:
    if value is None or value == "":
        ET.SubElement(row, _q("table", "table-cell"))
        return
    if isinstance(value, bool):
        cell = ET.SubElement(row, _q("table", "table-cell"), {
            _q("office", "value-type"): "boolean",
            _q("office", "boolean-value"): "true" if value else "false",
        })
        ET.SubElement(cell, _q("text", "p")).text = "TRUE" if value else "FALSE"
    elif isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number):
            ET.SubElement(row, _q("table", "table-cell"))
            return
        cell = ET.SubElement(row, _q("table", "table-cell"), {
            _q("office", "value-type"): "float",
            _q("office", "value"): str(value),
        })
        ET.SubElement(cell, _q("text", "p")).text = str(value)
    elif isinstance(value, (dt.date, dt.datetime)):
        if isinstance(value, dt.datetime):
            date_value = value.isoformat()
            display = value.isoformat(sep=" ")
        else:
            date_value = value.isoformat()
            display = date_value
        cell = ET.SubElement(row, _q("table", "table-cell"), {
            _q("office", "value-type"): "date",
            _q("office", "date-value"): date_value,
        })
        ET.SubElement(cell, _q("text", "p")).text = display
    else:
        cell = ET.SubElement(row, _q("table", "table-cell"), {
            _q("office", "value-type"): "string",
        })
        for part in str(value).split("\n"):
            ET.SubElement(cell, _q("text", "p")).text = part


def write_ods(
    path: str | Path,
    headers: Sequence[Any],
    rows: Sequence[Sequence[Any]],
    sheet_name: str = "AniListVault Library",
) -> Path:
    """Write typed cells and a header row to a standards-compliant ODS archive."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    root = ET.Element(_q("office", "document-content"), {
        _q("office", "version"): "1.3",
        _q("office", "mimetype"): MIMETYPE,
    })
    ET.SubElement(root, _q("office", "automatic-styles"))
    body = ET.SubElement(root, _q("office", "body"))
    spreadsheet = ET.SubElement(body, _q("office", "spreadsheet"))
    table = ET.SubElement(spreadsheet, _q("table", "table"), {
        _q("table", "name"): sheet_name,
    })
    header_group = ET.SubElement(table, _q("table", "table-header-rows"))
    header = ET.SubElement(header_group, _q("table", "table-row"))
    for value in headers:
        _cell(header, str(value))
    for values in rows:
        if len(values) != len(headers):
            raise ValueError("ODS row width does not match header width")
        row = ET.SubElement(table, _q("table", "table-row"))
        for value in values:
            _cell(row, value)

    content_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    styles = ET.Element(_q("office", "document-styles"), {
        _q("office", "version"): "1.3",
    })
    ET.SubElement(styles, _q("office", "styles"))
    ET.SubElement(styles, _q("office", "automatic-styles"))
    ET.SubElement(styles, _q("office", "master-styles"))
    styles_xml = ET.tostring(styles, encoding="utf-8", xml_declaration=True)
    meta = ET.Element(_q("office", "document-meta"), {
        _q("office", "version"): "1.3",
    })
    ET.SubElement(meta, _q("office", "meta"))
    meta_xml = ET.tostring(meta, encoding="utf-8", xml_declaration=True)
    manifest = ET.Element(_q("manifest", "manifest"), {
        _q("manifest", "version"): "1.3",
    })
    ET.SubElement(manifest, _q("manifest", "file-entry"), {
        _q("manifest", "full-path"): "/",
        _q("manifest", "version"): "1.3",
        _q("manifest", "media-type"): MIMETYPE,
    })
    for full_path, media_type in (
        ("content.xml", "text/xml"),
        ("styles.xml", "text/xml"),
        ("meta.xml", "text/xml"),
    ):
        ET.SubElement(manifest, _q("manifest", "file-entry"), {
            _q("manifest", "full-path"): full_path,
            _q("manifest", "media-type"): media_type,
        })
    manifest_xml = ET.tostring(manifest, encoding="utf-8", xml_declaration=True)

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        archive.writestr("content.xml", content_xml, compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("styles.xml", styles_xml, compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("meta.xml", meta_xml, compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("META-INF/manifest.xml", manifest_xml, compress_type=zipfile.ZIP_DEFLATED)
    return path
