from __future__ import annotations

import hashlib
import io
import posixpath
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile


MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_DOC = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"


class WorkbookExtractionError(ValueError):
    pass


def _xml(archive: ZipFile, name: str) -> ET.Element:
    try:
        return ET.fromstring(archive.read(name))
    except KeyError as error:
        raise WorkbookExtractionError(f"workbook package is missing {name}") from error
    except ET.ParseError as error:
        raise WorkbookExtractionError(
            f"workbook part {name} is not valid XML: {error}"
        ) from error


def _target(base: str, target: str) -> str:
    resolved = posixpath.normpath(
        posixpath.join(posixpath.dirname(base), target)
    )
    if resolved.startswith("../") or resolved.startswith("/"):
        raise WorkbookExtractionError(
            f"relationship target escapes the workbook package: {target}"
        )
    return resolved


def _relationships(
    archive: ZipFile, name: str, base: str
) -> dict[str, str]:
    root = _xml(archive, name)
    result: dict[str, str] = {}
    for item in root.findall(f"{{{REL_PKG}}}Relationship"):
        identity = item.get("Id")
        target = item.get("Target")
        if not identity or not target or identity in result:
            raise WorkbookExtractionError(
                f"relationship part {name} contains an invalid identity or target"
            )
        result[identity] = _target(base, target)
    return result


def _shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = _xml(archive, "xl/sharedStrings.xml")
    return [
        "".join(node.text or "" for node in item.iter(f"{{{MAIN}}}t"))
        for item in root.findall(f"{{{MAIN}}}si")
    ]


def _cell(cell: ET.Element, shared: list[str]) -> dict[str, object]:
    coordinate = cell.get("r")
    if not coordinate:
        raise WorkbookExtractionError("worksheet cell is missing its coordinate")
    kind = cell.get("t", "n")
    formula_node = cell.find(f"{{{MAIN}}}f")
    value_node = cell.find(f"{{{MAIN}}}v")
    inline = cell.find(f"{{{MAIN}}}is")
    raw = value_node.text if value_node is not None else None
    if kind == "s" and raw is not None:
        try:
            value: object = shared[int(raw)]
        except (ValueError, IndexError) as error:
            raise WorkbookExtractionError(
                f"cell {coordinate} has an invalid shared-string index {raw!r}"
            ) from error
    elif kind == "inlineStr" and inline is not None:
        value = "".join(
            node.text or "" for node in inline.iter(f"{{{MAIN}}}t")
        )
    elif kind == "b" and raw is not None:
        value = raw == "1"
    else:
        value = raw
    return {
        "coordinate": coordinate,
        "type": kind,
        "value": value,
        "formula": formula_node.text if formula_node is not None else None,
        "style_index": cell.get("s"),
    }


def extract(data: bytes) -> dict[str, object]:
    try:
        archive = ZipFile(io.BytesIO(data))
    except BadZipFile as error:
        raise WorkbookExtractionError(
            "source is not a readable ZIP-based workbook"
        ) from error
    with archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise WorkbookExtractionError(
                "workbook package contains duplicate part names"
            )
        workbook = _xml(archive, "xl/workbook.xml")
        relationships = _relationships(
            archive, "xl/_rels/workbook.xml.rels", "xl/workbook.xml"
        )
        shared = _shared_strings(archive)
        sheets: list[dict[str, object]] = []
        for position, sheet in enumerate(
            workbook.findall(f".//{{{MAIN}}}sheet"), 1
        ):
            relationship_id = sheet.get(f"{{{REL_DOC}}}id")
            if not relationship_id or relationship_id not in relationships:
                raise WorkbookExtractionError(
                    f"sheet {position} has no valid worksheet relationship"
                )
            part = relationships[relationship_id]
            root = _xml(archive, part)
            cells = [
                _cell(cell, shared)
                for cell in root.findall(f".//{{{MAIN}}}c")
            ]
            merges = [
                item.get("ref")
                for item in root.findall(f".//{{{MAIN}}}mergeCell")
                if item.get("ref")
            ]
            sheets.append(
                {
                    "position": position,
                    "name": sheet.get("name"),
                    "state": sheet.get("state", "visible"),
                    "part": part,
                    "cells": cells,
                    "merged_ranges": merges,
                }
            )
        return {
            "sheets": sheets,
            "sheet_count": len(sheets),
            "cell_count": sum(len(sheet["cells"]) for sheet in sheets),
            "package_parts": [
                {
                    "path": name,
                    "size": len(part),
                    "sha256": hashlib.sha256(part).hexdigest(),
                }
                for name in sorted(names)
                for part in [archive.read(name)]
            ],
        }
