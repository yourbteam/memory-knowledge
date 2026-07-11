#!/usr/bin/env python3
"""Wrapper for the shared verification ledger helper."""

from __future__ import annotations

import runpy
from pathlib import Path


SHARED_HELPER = Path(__file__).resolve().parents[2] / "_shared" / "verification_ledger.py"

if not SHARED_HELPER.is_file():
    raise SystemExit(f"shared verification ledger helper not found: {SHARED_HELPER}")

runpy.run_path(str(SHARED_HELPER), run_name="__main__")
