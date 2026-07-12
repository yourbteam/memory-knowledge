from __future__ import annotations

import importlib.util
from pathlib import Path


def load_module():
    path = Path(__file__).parents[1] / "working-agreement/hydrate_repo_memory.py"
    spec = importlib.util.spec_from_file_location("hydrate_repo_memory", path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_hook_hydration_defense_matches_server_trust_contract():
    module = load_module()
    confirmed = {
        "memory_type": "operator_note", "source_kind": "operator_note",
        "verification_status": "human_asserted", "is_active": True,
        "content_kind": "corrected-approach", "evidence_refs": [{"kind": "file"}],
        "evidence_resolution_errors": [],
    }
    assert module._eligible(confirmed)
    assert not module._eligible({**confirmed, "verification_status": "unverified"})
    assert not module._eligible({**confirmed, "content_kind": None})
    assert not module._eligible({**confirmed, "evidence_refs": []})
    assert not module._eligible({**confirmed, "is_active": False})
