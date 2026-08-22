#!/usr/bin/env python3
"""Bind recognized spreadsheet columns to exact Reporting V3 evidence."""

from __future__ import annotations

import hashlib
import json


class FormulaColumnBindingError(ValueError):
    """A claim column cannot be bound to the Reporting V3 index."""


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def bind(
    claim_id: str,
    references: list[str],
    columns: list[dict[str, object]],
) -> dict[str, object]:
    index = {
        item.get("excel_column"): item
        for item in columns
        if isinstance(item, dict) and isinstance(item.get("excel_column"), str)
    }
    if len(index) != len(columns):
        raise FormulaColumnBindingError(
            "column index contains malformed or duplicate Excel identities"
        )
    unknown = [value for value in references if value not in index]
    if unknown:
        raise FormulaColumnBindingError(
            f"claim {claim_id!r} references unknown Reporting V3 columns {unknown}"
        )
    return {
        "claim_id": claim_id,
        "referenced_columns": [
            {
                "excel_column": value,
                "column_record": index[value],
                "column_record_sha256": _digest(index[value]),
            }
            for value in references
        ],
    }
