from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts import (
    prevention_adapters,
    prevention_contract_materializer,
    prevention_observable_materializer,
)
from scripts.prevention_contract import (
    canonical_bytes, resolve_repository_source_path, sha256_bytes,
)


def test_observable_evidence_is_byte_stable_source_bound_and_complete():
    document = prevention_observable_materializer.materialize()
    assert prevention_observable_materializer.OUTPUT.read_bytes() == canonical_bytes(document)
    assert document["admission_effect"] == "PROVIDER_IMPLEMENTED_SOURCE_PATH_UNVERIFIED"
    provider = document["provider_implementation"]
    assert sha256_bytes(resolve_repository_source_path(
        provider["path"],
        repository_root=prevention_observable_materializer.ROOT,
        canonical_repository_root=prevention_observable_materializer.CANONICAL_ROOT,
    ).read_bytes()) == provider["sha256"]
    assert len(document["owners"]) == 10
    assert sum(len(owner["profiles"]) for owner in document["owners"]) == 44

    for owner in document["owners"]:
        stored = owner["evidence_sha256"]
        payload = {key: value for key, value in owner.items() if key != "evidence_sha256"}
        assert sha256_bytes(canonical_bytes(payload)) == stored
        assert owner["sources"]
        for source in owner["sources"]:
            path = resolve_repository_source_path(
                source["path"],
                repository_root=prevention_observable_materializer.ROOT,
                canonical_repository_root=prevention_observable_materializer.CANONICAL_ROOT,
            )
            assert path.is_file()
            assert sha256_bytes(path.read_bytes()) == source["sha256"]
            text = path.read_text(encoding="utf-8")
            assert all(anchor in text for anchor in source["anchors"])
        for source_test in owner["source_tests"]:
            path = resolve_repository_source_path(
                source_test["path"],
                repository_root=prevention_observable_materializer.ROOT,
                canonical_repository_root=prevention_observable_materializer.CANONICAL_ROOT,
            )
            assert path.is_file()
            assert sha256_bytes(path.read_bytes()) == source_test["sha256"]
            assert source_test["test_ids"]


def test_every_owner_profile_has_closed_schema_and_five_finite_fixture_classes():
    for owner in prevention_observable_materializer.materialize()["owners"]:
        for profile in owner["profiles"]:
            schema = profile["capture_schema"]
            assert schema["closed"] is True
            assert schema["probe_ids"]
            assert len(schema["probe_ids"]) == len(set(schema["probe_ids"]))
            assert schema["probe_result"] == [
                "SATISFIED", "ABSENT", "CONFLICT", "UNKNOWN"
            ]
            fixtures = {row["fixture_id"]: row for row in profile["fixture_specs"]}
            assert set(fixtures) == {
                "applied", "absent", "conflicting", "malformed", "stale"
            }
            assert fixtures["applied"]["expected_reconciliation"] == "ALREADY_APPLIED"
            assert fixtures["absent"]["expected_reconciliation"] == "NOT_APPLIED"
            assert fixtures["conflicting"]["expected_reconciliation"] == "INDETERMINATE"
            assert fixtures["malformed"]["expected_error"] == "OBSERVABLE_SCHEMA_INVALID"
            assert fixtures["stale"]["capture"]["observed_age_seconds"] > (
                profile["maximum_age_seconds"]
            )
            assert set(fixtures["applied"]["capture"]["probes"]) == set(
                schema["probe_ids"]
            )
            assert set(fixtures["malformed"]["capture"]["probes"]) < set(
                schema["probe_ids"]
            )


def test_observable_materializer_rejects_incomplete_profile_map(monkeypatch):
    changed = deepcopy(prevention_observable_materializer.PROFILE_PROBES)
    changed["local-workflow-orch-image"] = {
        key: value
        for key, value in changed["local-workflow-orch-image"].items()
        if key != "build"
    }
    monkeypatch.setattr(prevention_observable_materializer, "PROFILE_PROBES", changed)
    with pytest.raises(
        prevention_observable_materializer.ObservableMaterializationError,
        match="observable-profile-map-incomplete:local-workflow-orch-image",
    ):
        prevention_observable_materializer.materialize()


def test_observable_materializer_rejects_source_anchor_drift(tmp_path: Path):
    path = tmp_path / "source.py"
    path.write_text("def different():\n    pass\n", encoding="utf-8")
    with pytest.raises(
        prevention_observable_materializer.ObservableMaterializationError,
        match="observable-source-anchor-missing",
    ):
        prevention_observable_materializer._source_row(
            str(path), ("def required(",)
        )


def test_all_43_source_bound_profiles_execute_the_five_fixture_classes():
    contracts = {
        row["owner_sequence_id"]: row
        for row in prevention_contract_materializer.materialize()["owners"]
    }
    evidence = prevention_observable_materializer.materialize()

    class FixtureTransport:
        def __init__(self, capture):
            self.capture = capture

        def query(self, request):
            capture = deepcopy(self.capture)
            age = capture.pop("observed_age_seconds")
            capture["observed_at_utc"] = (
                datetime.now(UTC) - timedelta(seconds=age)
            ).isoformat()
            capture["ownership"] = {
                "effect_id": request["effect_id"],
                "owner_sequence_id": request["owner_sequence_id"],
                "preparation_artifact_sha256": request[
                    "preparation_artifact_sha256"
                ],
            }
            capture["source_evidence_sha256"] = request[
                "source_evidence_sha256"
            ]
            return capture

    for owner in evidence["owners"]:
        contract = contracts[owner["owner_sequence_id"]]
        for profile in owner["profiles"]:
            plan = prevention_adapters.InvocationPlan(
                sequence_id=owner["owner_sequence_id"],
                argv=("true",),
                owner_contract_sha256=contract["owner_contract_sha256"],
                implementation_source_sha256="a" * 64,
                parameter_schema_sha256="b" * 64,
                resolved_parameters={"command": profile["profile"]},
                root_bindings={},
                binding_receipts={},
            )
            state = {
                "effect_id": "e" * 64,
                "preparation_artifact_sha256": "f" * 64,
                "observation_targets": {},
                "prepared_prestate_identities": {},
                "prepared_receipt_identities": {},
            }
            preparation = {
                "reconciliation_contract": contract["reconciliation_contract"],
                "observation_targets": {},
                "prepared_prestate_identities": {},
                "prepared_receipt_identities": {},
            }
            fixtures = {row["fixture_id"]: row for row in profile["fixture_specs"]}
            for fixture_id in ("applied", "absent", "conflicting"):
                observed = prevention_adapters.acquire_reconciliation_observation(
                    plan,
                    state,
                    preparation,
                    FixtureTransport(fixtures[fixture_id]["capture"]),
                )
                decision = prevention_adapters.reconcile_observation(
                    observed,
                    reconciliation_contract=contract["reconciliation_contract"],
                )
                assert decision.classification == fixtures[fixture_id][
                    "expected_reconciliation"
                ]
            with pytest.raises(
                prevention_adapters.AdapterError,
                match="reconciliation-capture-probes-invalid",
            ):
                prevention_adapters.acquire_reconciliation_observation(
                    plan,
                    state,
                    preparation,
                    FixtureTransport(fixtures["malformed"]["capture"]),
                )
            stale = prevention_adapters.acquire_reconciliation_observation(
                plan,
                state,
                preparation,
                FixtureTransport(fixtures["stale"]["capture"]),
            )
            with pytest.raises(prevention_adapters.AdapterError, match="stale"):
                prevention_adapters.reconcile_observation(
                    stale,
                    reconciliation_contract=contract["reconciliation_contract"],
                )
            terminal = prevention_adapters.acquire_terminal_observation(
                plan,
                state,
                "EXECUTED_RESULT",
                contract["terminal_contract"],
                FixtureTransport(fixtures["applied"]["capture"]),
            )
            assert terminal.raw_result == {
                "semantic": "PASS",
                "output_schema": "VALID",
                "identity": "MATCH",
                "work_state": "TERMINAL",
            }


def test_finite_source_transport_requires_backend_ownership_and_exact_probe_execution():
    calls = []

    class Backend:
        def observe_identity(self, request):
            return "MATCH"

        def observe_ownership(self, request):
            return {
                "effect_id": request["effect_id"],
                "owner_sequence_id": request["owner_sequence_id"],
                "preparation_artifact_sha256": request[
                    "preparation_artifact_sha256"
                ],
            }

        def observe_prestate(self, request):
            return "CHANGED"

        def observe_receipt(self, request):
            return "PRESENT"

        def observe_work_state(self, request):
            return "TERMINAL"

        def observe_probe(self, request, probe_id):
            calls.append((request["owner_sequence_id"], request["profile"], probe_id))
            return "SATISFIED"

    transport = prevention_adapters.SourceObservationTransport(Backend())
    evidence = prevention_observable_materializer.materialize()
    for owner in evidence["owners"]:
        for profile in owner["profiles"]:
            request = {
                "effect_id": "e" * 64,
                "owner_sequence_id": owner["owner_sequence_id"],
                "preparation_artifact_sha256": "f" * 64,
                "observation_targets": {},
                "prepared_prestate_identities": {},
                "prepared_receipt_identities": {},
                "profile": profile["profile"],
                "probe_ids": profile["capture_schema"]["probe_ids"],
                "provider_symbol": profile["provider_symbol_prefix"] + "_terminal",
                "source_evidence_sha256": owner["evidence_sha256"],
            }
            capture = transport.query(request)
            assert set(capture["probes"]) == set(request["probe_ids"])
            assert capture["ownership"] == {
                "effect_id": request["effect_id"],
                "owner_sequence_id": request["owner_sequence_id"],
                "preparation_artifact_sha256": request[
                    "preparation_artifact_sha256"
                ],
            }
            assert capture["source_evidence_sha256"] == owner["evidence_sha256"]
    assert len(calls) == sum(
        len(profile["capture_schema"]["probe_ids"])
        for owner in evidence["owners"] for profile in owner["profiles"]
    )
