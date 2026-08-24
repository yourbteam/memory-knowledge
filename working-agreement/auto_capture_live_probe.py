#!/usr/bin/env python3
"""Zero-input same-path dry-run probe for the automatic auto-capture hook."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
HOOK = Path(os.environ.get(
    "MK_AUTOCAPTURE_PROBE_HOOK",
    ROOT / "working-agreement" / "auto-capture-stop.sh",
))
HELPER = Path(os.environ.get(
    "MK_AUTOCAPTURE_PROBE_HELPER",
    ROOT / "working-agreement" / "auto_capture.py",
))
PYTHON = ROOT / ".venv" / "bin" / "python"
CONTENT_KINDS = {
    "root-cause", "corrected-approach", "repository-decision", "repository-fact",
}
EVIDENCE_KINDS = {"entity", "revision", "file"}


class ProbeError(RuntimeError):
    """The live hook did not produce a safe canonical dry-run result."""


def validate_payload(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != {"repository_key", "lessons"}:
        raise ProbeError("hook output must contain only repository_key and lessons")
    if raw["repository_key"] != ROOT.name:
        raise ProbeError("hook output repository key does not match the probe repository")
    lessons = raw["lessons"]
    if not isinstance(lessons, list) or not lessons:
        raise ProbeError("the source-free fixture produced no durable lesson")
    for index, lesson in enumerate(lessons, start=1):
        if not isinstance(lesson, dict) or lesson.get("content_kind") not in CONTENT_KINDS:
            raise ProbeError(f"lesson {index} has no canonical content kind")
        refs = lesson.get("evidence_refs")
        if not isinstance(refs, list) or not refs:
            raise ProbeError(f"lesson {index} has no evidence reference")
        if any(not isinstance(ref, dict) or ref.get("kind") not in EVIDENCE_KINDS for ref in refs):
            raise ProbeError(f"lesson {index} has no canonical evidence kind")
        forbidden = {"content_kind_selection", "kind_selection", "continue_selection"}
        if forbidden & set(lesson) or any(forbidden & set(ref) for ref in refs):
            raise ProbeError(f"lesson {index} leaked interview selection fields")
    return raw


def _revision() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False,
    )
    revision = result.stdout.strip()
    if result.returncode or len(revision) != 40:
        raise ProbeError("cannot resolve the probe repository revision")
    return revision


def run_probe() -> dict[str, Any]:
    revision = _revision()
    transcript = [
        {
            "message": {
                "role": "user",
                "content": (
                    "A bounded probe confirmed that working-agreement/auto_capture.py at revision "
                    f"{revision} accepted prose finite-choice labels. The durable corrected approach "
                    "is to present numbered menus, require numeric selections, and map them in code."
                ),
            },
        },
        {
            "message": {
                "role": "assistant",
                "content": (
                    "Confirmed: code-controlled numeric selection with bounded rejection of prose "
                    "labels is the stable boundary."
                ),
            },
        },
    ]
    with tempfile.TemporaryDirectory(prefix="auto-capture-live-probe-") as raw_dir:
        probe_dir = Path(raw_dir)
        transcript_path = probe_dir / "transcript.jsonl"
        transcript_path.write_text(
            "".join(json.dumps(item, sort_keys=True) + "\n" for item in transcript),
            encoding="utf-8",
        )
        payload = {
            "cwd": str(ROOT),
            "transcript_path": str(transcript_path),
        }
        environment = dict(os.environ)
        environment.update({
            "MK_AUTOCAPTURE": "1",
            "MK_AUTOCAPTURE_DRY_RUN": "1",
            "MK_AUTOCAPTURE_DEBUG": "1",
        })
        if os.environ.get("MK_AUTOCAPTURE_PROBE_USE_HOOK_PYTHON") != "1":
            environment["CLAUDE_CORPUS_PYTHON"] = str(PYTHON)
        if os.environ.get("MK_AUTOCAPTURE_PROBE_USE_HOOK_DEFAULT") != "1":
            environment["MK_AUTOCAPTURE_HELPER"] = str(HELPER)
        result = subprocess.run(
            ["/bin/bash", str(HOOK)],
            cwd=ROOT,
            env=environment,
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=False,
        )
    if result.returncode:
        raise ProbeError(f"hook exited {result.returncode}: {result.stderr.strip()}")
    if not result.stdout.strip():
        raise ProbeError(result.stderr.strip() or "hook produced no dry-run payload")
    try:
        normalized = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ProbeError("hook output was not one JSON payload") from exc
    validate_payload(normalized)
    return {
        "ok": True,
        "dry_run": True,
        "memory_writes": 0,
        "normalized_lessons": len(normalized["lessons"]),
        "repository_key": normalized["repository_key"],
    }


def main() -> int:
    try:
        result = run_probe()
    except ProbeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
