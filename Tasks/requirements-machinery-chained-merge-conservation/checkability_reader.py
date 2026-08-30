#!/usr/bin/env python3
"""Deterministic real-path reader: keep every numbered checkability item."""

from __future__ import annotations

import re
import sys


prompt = sys.stdin.read()
numbers = re.findall(r"(?m)^(\d+)\. ", prompt)
sys.stdout.write("\n".join(numbers) + "\n")
