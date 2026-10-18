from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def owner_historical_root(monkeypatch: pytest.MonkeyPatch) -> Path:
    root = Path(__file__).resolve().parents[2]
    verification_path = (
        root / "Tasks/prevention-system-completion/owner-source-verification.json"
    )
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    provider_path = Path(verification["provider_implementation"]["path"])
    assert provider_path.is_absolute()
    assert provider_path.parts[-2:] == ("scripts", "prevention_source_probes.py")
    historical_root = provider_path.parents[1]
    monkeypatch.setenv("MK_PREVENTION_HISTORICAL_ROOT", str(historical_root))
    return historical_root
