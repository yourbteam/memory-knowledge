from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[1] / "working-agreement" / "auto_capture_live_probe.py"
SPEC = importlib.util.spec_from_file_location("auto_capture_live_probe", MODULE)
assert SPEC is not None and SPEC.loader is not None
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def _payload() -> dict:
    return {
        "repository_key": probe.ROOT.name,
        "lessons": [{
            "title": "Use numbered choices",
            "body": "Map finite choices in code.",
            "content_kind": "corrected-approach",
            "evidence_refs": [{
                "kind": "revision",
                "revision_commit": "a" * 40,
            }],
        }],
    }


def test_live_probe_accepts_only_canonical_dry_run_payload() -> None:
    assert probe.validate_payload(_payload())["lessons"][0]["content_kind"] == (
        "corrected-approach"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("content_kind", "2"),
        ("content_kind_selection", 2),
    ],
)
def test_live_probe_rejects_noncanonical_or_leaked_selections(field: str, value: object) -> None:
    payload = _payload()
    payload["lessons"][0][field] = value

    with pytest.raises(probe.ProbeError):
        probe.validate_payload(payload)
