#!/usr/bin/env python3
"""Reserve the next independent source identity from immutable ledger identities."""

from __future__ import annotations

import re


SOURCE_ID = re.compile(r"^source-(\d{6})$")


def reserve(existing_source_ids: list[object]) -> dict[str, object]:
    numbers: list[int] = []
    seen: set[str] = set()
    for value in existing_source_ids:
        if not isinstance(value, str) or SOURCE_ID.fullmatch(value) is None:
            raise ValueError(f"malformed source identity: {value!r}")
        if value in seen:
            raise ValueError(f"duplicate source identity: {value}")
        seen.add(value)
        numbers.append(int(value.removeprefix("source-")))
    number = max(numbers, default=0) + 1
    source_id = f"source-{number:06d}"
    return {
        "source_id": source_id,
        "source_number": number,
        "projection_id": f"projection-{source_id}-v1",
    }
