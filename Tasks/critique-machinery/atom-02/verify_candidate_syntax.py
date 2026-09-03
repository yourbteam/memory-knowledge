#!/usr/bin/env python3
"""Read-only syntax check for Atom 2's immutable Python candidates."""

from __future__ import annotations

import ast
from pathlib import Path


ATOM = Path(__file__).resolve().parent
SOURCES = (
    ATOM / "prepare.py",
    ATOM / "development/evaluator.py",
    ATOM / "development/assessment.py",
    ATOM / "development/terminal-only-gates/skills/critique-machinery/scripts/critique.py",
    ATOM / "development/universal-gate/skills/critique-machinery/scripts/critique.py",
)


def main() -> None:
    for source in SOURCES:
        ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    print(f"syntax valid: {len(SOURCES)} immutable Python sources")


if __name__ == "__main__":
    main()
