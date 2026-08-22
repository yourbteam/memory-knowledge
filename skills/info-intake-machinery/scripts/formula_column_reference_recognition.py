#!/usr/bin/env python3
"""Recognize explicit spreadsheet-column references in claim text."""

from __future__ import annotations

import re


def recognize(statement: str) -> list[str]:
    found: list[str] = []
    for match in re.finditer(
        r"\bcolumn\s*:?\s*([A-Za-z]{1,3})\b", statement, re.IGNORECASE
    ):
        value = match.group(1).upper()
        if value not in found:
            found.append(value)
    return found
