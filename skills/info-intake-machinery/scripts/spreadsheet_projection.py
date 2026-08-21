from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
from zipfile import BadZipFile, ZipFile


def _load_sibling(name: str):
    spec = importlib.util.spec_from_file_location(
        f"info_intake_{name}", Path(__file__).resolve().with_name(f"{name}.py")
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"{name} is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


spreadsheet_extract = _load_sibling("spreadsheet_extract")
spreadsheet_coverage = _load_sibling("spreadsheet_coverage")


ADAPTER_VERSION = 1
WORKBOOK_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
    "application/vnd.ms-excel.sheet.macroenabled.main+xml",
}


class SpreadsheetProjectionError(ValueError):
    pass


def is_workbook(path: Path, media_type: str, data: bytes) -> bool:
    del path
    if media_type in {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel.sheet.macroenabled.12",
    }:
        return True
    try:
        with ZipFile(io.BytesIO(data)) as archive:
            content_types = archive.read("[Content_Types].xml")
    except (BadZipFile, KeyError):
        return False
    return any(
        content_type.encode("utf-8") in content_types
        for content_type in WORKBOOK_TYPES
    )


def project(data: bytes) -> dict[str, object]:
    try:
        extracted = spreadsheet_extract.extract(data)
        coverage = spreadsheet_coverage.account(data)
    except Exception as error:
        raise SpreadsheetProjectionError(str(error)) from error
    return {
        "schema_version": 1,
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "format": "xlsx",
        "workbook": extracted,
        "coverage": coverage,
    }


def canonical_bytes(projection: dict[str, object]) -> bytes:
    return json.dumps(projection, indent=2, sort_keys=True).encode("utf-8") + b"\n"
