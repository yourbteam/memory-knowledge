#!/usr/bin/env python3
"""Extract each Reporting V3 row writer with exact source-line evidence."""

from __future__ import annotations

import re


class ReportingV3WriterError(ValueError):
    """The Reporting V3 writer block is malformed or incomplete."""


def parse_writers(source: str) -> list[dict[str, object]]:
    lines = source.splitlines()
    starts = [
        index
        for index, line in enumerate(lines)
        if "BuildV3ExcelResult(" in line and "static" in line
    ]
    if len(starts) != 1:
        raise ReportingV3WriterError(
            f"BuildV3ExcelResult declaration count is {len(starts)}; require 1"
        )
    end = next(
        (
            index
            for index in range(starts[0] + 1, len(lines))
            if "private static string V3I(" in lines[index]
        ),
        None,
    )
    if end is None:
        raise ReportingV3WriterError("BuildV3ExcelResult end boundary is missing")
    direct = re.compile(r"ws\.Cell\(r,\s*(\d+)\)\.Value\s*=\s*(.+);")
    helper = re.compile(
        r"(V3ReportAccountingCellWriter\.\w+)"
        r"\(ws\.Cell\(r,\s*(\d+)\),\s*(.+)\);"
    )
    found: dict[int, dict[str, object]] = {}
    for index in range(starts[0], end):
        source_line = lines[index].strip()
        match = direct.fullmatch(source_line)
        write_kind = "value_assignment"
        if match:
            column = int(match.group(1))
            expression = match.group(2)
        else:
            match = helper.fullmatch(source_line)
            if not match:
                continue
            write_kind = "helper_call"
            column = int(match.group(2))
            expression = f"{match.group(1)}({match.group(3)})"
        if not 1 <= column <= 81:
            continue
        if column in found:
            raise ReportingV3WriterError(
                f"duplicate V3 writer for column {column} on line {index + 1}"
            )
        found[column] = {
            "column_number": column,
            "write_kind": write_kind,
            "expression": expression,
            "line_number": index + 1,
            "source_line": source_line,
        }
    missing = sorted(set(range(1, 82)) - set(found))
    if missing:
        raise ReportingV3WriterError(f"V3 writers are missing columns {missing}")
    return [found[column] for column in range(1, 82)]
