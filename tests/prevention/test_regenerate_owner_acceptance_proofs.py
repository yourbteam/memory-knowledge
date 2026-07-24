import pytest

from scripts import regenerate_owner_acceptance_proofs as target


def test_required_proofs_by_profile_keeps_only_required_rows():
    owner = {
        "acceptance_proofs": [{
            "profile_id": "one",
            "proofs": [
                {
                    "proof_kind": "controller_runtime_positive",
                    "applicability": "REQUIRED",
                },
                {
                    "proof_kind": "crash_reconciliation",
                    "applicability": "NOT_APPLICABLE",
                },
            ],
        }],
    }
    assert target.required_proofs_by_profile(owner) == {
        "one": {"controller_runtime_positive"},
    }


def test_regenerate_derives_scenarios_from_required_proofs(monkeypatch):
    owner = {
        "owner_sequence_id": "owner",
        "acceptance_proofs": [{
            "profile_id": "profile",
            "proofs": [
                {"proof_kind": proof, "applicability": "REQUIRED"}
                for proof in (
                    "controller_runtime_positive",
                    "controller_runtime_semantic_negative",
                    "crash_reconciliation",
                )
            ],
        }],
    }
    calls = []
    monkeypatch.setattr(
        target.prevention_contract_materializer,
        "materialize",
        lambda: {"owners": [owner]},
    )
    monkeypatch.setattr(target, "current_trace_references", lambda _owners: {})
    monkeypatch.setattr(
        target.prevention_owner_acceptance_producer,
        "write_positive_traces",
        lambda owner_id, profile: calls.append(("positive", owner_id, profile))
        or ["a" * 64],
    )
    monkeypatch.setattr(
        target.prevention_owner_acceptance_producer,
        "write_negative_trace",
        lambda owner_id, profile: calls.append(("negative", owner_id, profile))
        or "b" * 64,
    )
    monkeypatch.setattr(
        target.prevention_owner_acceptance_producer,
        "write_crash_traces",
        lambda owner_id, profile: calls.append(("crash", owner_id, profile))
        or ["c" * 64, "d" * 64],
    )

    result = target.regenerate()

    assert calls == [
        ("positive", "owner", "profile"),
        ("negative", "owner", "profile"),
        ("crash", "owner", "profile"),
    ]
    assert result == {
        "ok": True,
        "owner_count": 1,
        "profile_count": 1,
        "scenario_count": 3,
        "executed_scenario_count": 3,
        "trace_count": 4,
    }


def test_regenerate_reuses_complete_current_profile(monkeypatch):
    proofs = {
        "controller_runtime_positive",
        "controller_runtime_semantic_negative",
        "crash_reconciliation",
    }
    owner = {
        "owner_sequence_id": "owner",
        "acceptance_proofs": [{
            "profile_id": "profile",
            "proofs": [
                {"proof_kind": proof, "applicability": "REQUIRED"}
                for proof in sorted(proofs)
            ],
        }],
    }
    current = {
        ("owner", "profile", proof): str(index) * 64
        for index, proof in enumerate(sorted(proofs), start=1)
    }
    monkeypatch.setattr(
        target.prevention_contract_materializer,
        "materialize",
        lambda: {"owners": [owner]},
    )
    monkeypatch.setattr(
        target, "current_trace_references", lambda _owners: current,
    )
    monkeypatch.setattr(
        target.prevention_owner_acceptance_producer,
        "write_positive_traces",
        lambda *_args: pytest.fail("positive scenario was regenerated"),
    )
    monkeypatch.setattr(
        target.prevention_owner_acceptance_producer,
        "write_negative_trace",
        lambda *_args: pytest.fail("negative scenario was regenerated"),
    )
    monkeypatch.setattr(
        target.prevention_owner_acceptance_producer,
        "write_crash_traces",
        lambda *_args: pytest.fail("crash scenario was regenerated"),
    )

    result = target.regenerate()

    assert result["scenario_count"] == 3
    assert result["executed_scenario_count"] == 0
    assert result["trace_count"] == 3
