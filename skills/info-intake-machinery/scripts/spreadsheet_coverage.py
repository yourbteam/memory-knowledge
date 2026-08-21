from __future__ import annotations

import io
from zipfile import BadZipFile, ZipFile


class WorkbookCoverageError(ValueError):
    pass


def _represented(name: str) -> bool:
    return name in {
        "[Content_Types].xml",
        "_rels/.rels",
        "xl/workbook.xml",
        "xl/_rels/workbook.xml.rels",
        "xl/sharedStrings.xml",
    } or name.startswith("xl/worksheets/")


def account(data: bytes) -> dict[str, object]:
    try:
        archive = ZipFile(io.BytesIO(data))
    except BadZipFile as error:
        raise WorkbookCoverageError(
            "source is not a readable ZIP-based workbook"
        ) from error
    with archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise WorkbookCoverageError(
                "workbook package contains duplicate part names"
            )
        parts = []
        for name in sorted(names):
            represented = _represented(name)
            parts.append(
                {
                    "path": name,
                    "outcome": "represented" if represented else "gap",
                    "reason": (
                        None
                        if represented
                        else f"workbook part {name} has no readable adapter"
                    ),
                }
            )
        represented_units = sum(
            item["outcome"] == "represented" for item in parts
        )
        gap_units = len(parts) - represented_units
        return {
            "parts": parts,
            "source_units": len(parts),
            "represented_units": represented_units,
            "gap_units": gap_units,
            "status": "complete" if gap_units == 0 else "partial",
        }
