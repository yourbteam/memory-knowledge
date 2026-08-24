#!/usr/bin/env python3
"""Extract the exact ordered Reporting V3 spreadsheet headers."""

from __future__ import annotations

import re


class ReportingV3HeaderError(ValueError):
    """The Reporting V3 header block is malformed or incomplete."""


def parse_headers(source: str) -> list[dict[str, object]]:
    lines = source.splitlines()
    starts = [
        index
        for index, line in enumerate(lines)
        if re.search(r"\bV3ColumnHeaders\s*=\s*$", line)
    ]
    if len(starts) != 1:
        raise ReportingV3HeaderError(
            f"V3ColumnHeaders declaration count is {len(starts)}; require 1"
        )
    start = starts[0]
    if start + 1 >= len(lines) or lines[start + 1].strip() != "[":
        raise ReportingV3HeaderError(
            "V3ColumnHeaders must use one explicit collection block"
        )
    headers: list[dict[str, object]] = []
    for index in range(start + 2, len(lines)):
        stripped = lines[index].strip()
        if stripped == "];":
            break
        tokens = re.findall(r'"([^"\n]*)"', stripped)
        remainder = re.sub(r'"[^"\n]*"', "", stripped).replace(",", "").strip()
        if remainder or not tokens:
            raise ReportingV3HeaderError(
                f"V3ColumnHeaders line {index + 1} contains non-string content "
                f"{stripped!r}"
            )
        headers.extend(
            {"header": token, "line_number": index + 1} for token in tokens
        )
    else:
        raise ReportingV3HeaderError("V3ColumnHeaders collection does not terminate")
    if len(headers) != 81:
        raise ReportingV3HeaderError(
            f"V3ColumnHeaders contains {len(headers)} columns; require 81"
        )
    return headers
