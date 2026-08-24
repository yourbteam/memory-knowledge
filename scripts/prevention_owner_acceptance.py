#!/usr/bin/env python3
"""Assemble and validate content-addressed owner source-path proof traces."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from scripts.prevention_contract import (
        canonical_bytes, resolve_repository_source_path, sha256_bytes,
    )
except ModuleNotFoundError:  # direct script execution
    from prevention_contract import (
        canonical_bytes, resolve_repository_source_path, sha256_bytes,
    )


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_ROOT = Path.home() / "memory-knowledge"
OUTPUT = ROOT / "Tasks/prevention-system-completion/owner-source-verification.json"
TRACE_DIR = ROOT / "Tasks/prevention-system-completion/owner-acceptance-artifacts"
CONTRACTS = ROOT / "Tasks/prevention-system-completion/owner-executable-contracts.json"
PROVIDER_PATH = ROOT / "scripts/prevention_source_probes.py"
PRODUCER_PATH = ROOT / "scripts/prevention_owner_acceptance_producer.py"
FIXTURES_PATH = ROOT / "scripts/prevention_owner_acceptance_fixtures.py"

PROOF_KINDS = (
    "controller_runtime_positive",
    "controller_runtime_semantic_negative",
    "crash_reconciliation",
    "terminal_semantics",
    "effect_identity_source_binding",
    "production_source_probe_backend",
)
TRACE_FIELDS = {
    "schema_version", "owner_sequence_id", "profile_id", "proof_kind", "case_id",
    "applicability", "acceptance_contract_sha256", "parameter_policy_sha256",
    "reconciliation_policy_sha256", "terminal_policy_sha256", "source_bindings",
    "test_bindings", "provider_implementation_sha256", "production_backend_id",
    "source_edge_kind", "runner_command_sha256", "journal_events",
    "journal_events_sha256", "artifacts", "expected_outcome", "observed_outcome",
}
ARTIFACT_KINDS = (
    "preparation", "reconciliation", "source_capture", "terminal",
)
PROOF_OUTCOMES = {
    "controller_runtime_positive": "TERMINAL",
    "controller_runtime_semantic_negative": "NONTERMINAL_REJECTED",
    "crash_reconciliation": "RECOVERED_WITHOUT_DUPLICATE_MUTATION",
    "terminal_semantics": "EXACTLY_ONE_TERMINAL",
    "effect_identity_source_binding": "SOURCE_IDENTITY_BOUND",
    "production_source_probe_backend": "RAW_PRODUCTION_CAPTURE_VALIDATED",
}


class AcceptanceError(ValueError):
    """A proof corpus is incomplete, stale, or semantically inconsistent."""


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AcceptanceError(f"{label}-unavailable") from exc
    if not isinstance(value, dict):
        raise AcceptanceError(f"{label}-invalid")
    return value


def _source_root_enabled(owner_id: str) -> bool:
    if not os.environ.get("MK_PREVENTION_SOURCE_ROOT"):
        return False
    selected = frozenset(
        value for value in os.environ.get(
            "MK_PREVENTION_SOURCE_ROOT_OWNER_IDS", ""
        ).split(",") if value
    )
    return not selected or owner_id in selected


def _binding_path(path_value: str, *, use_source_root: bool) -> Path:
    repository_root = ROOT
    canonical_root = CANONICAL_ROOT
    source_root_value = os.environ.get("MK_PREVENTION_SOURCE_ROOT")
    canonical_root_value = os.environ.get("MK_PREVENTION_CANONICAL_ROOT")
    if use_source_root and source_root_value and canonical_root_value:
        repository_root = Path(source_root_value)
        canonical_root = Path(canonical_root_value)
    return resolve_repository_source_path(
        path_value,
        repository_root=repository_root,
        canonical_repository_root=canonical_root,
    )


def _binding_current(binding: Any, *, use_source_root: bool = True) -> bool:
    if not _binding_shape_valid(binding):
        return False
    path = _binding_path(
        str(binding["path"]), use_source_root=use_source_root,
    )
    return path.is_file() and sha256_bytes(path.read_bytes()) == binding["sha256"]


def _binding_shape_valid(binding: Any) -> bool:
    return (
        isinstance(binding, Mapping)
        and set(binding) == {"path", "sha256"}
        and isinstance(binding["path"], str)
        and bool(binding["path"])
        and isinstance(binding["sha256"], str)
        and len(binding["sha256"]) == 64
        and all(character in "0123456789abcdef" for character in binding["sha256"])
    )


def _artifact_valid(value: Any) -> bool:
    if not isinstance(value, Mapping) or value.get("applicable") not in {True, False}:
        return False
    if value["applicable"] is False:
        return set(value) == {"applicable"}
    return (
        set(value) == {"applicable", "sha256", "payload"}
        and value["sha256"] == sha256_bytes(canonical_bytes(value["payload"]))
    )


def _applicable_artifact(
    artifacts: Mapping[str, Any], name: str,
) -> Mapping[str, Any] | None:
    value = artifacts.get(name)
    if not isinstance(value, Mapping) or value.get("applicable") is not True:
        return None
    payload = value.get("payload")
    return payload if isinstance(payload, Mapping) else None


def _events_of(
    events: Sequence[Mapping[str, Any]], event_type: str,
) -> list[Mapping[str, Any]]:
    return [event for event in events if event.get("event_type") == event_type]


def _validate_proof_semantics(trace: Mapping[str, Any]) -> None:
    """Replay the typed claim instead of trusting expected/observed PASS text."""
    proof = str(trace["proof_kind"])
    all_events = trace["journal_events"]
    owner_sequence_id = trace["owner_sequence_id"]
    owner_effect_ids = {
        event["effect_id"] for event in all_events
        if event.get("event_type") == "effect_prepared"
        and event.get("owner_sequence_id") == owner_sequence_id
    }
    events = [
        event for event in all_events
        if event.get("effect_id") in owner_effect_ids
    ]
    artifacts = trace["artifacts"]
    terminals = _events_of(events, "owner_terminal")
    prepared = _events_of(events, "effect_prepared")
    started = _events_of(events, "effect_execution_started")
    committed = _events_of(events, "effect_committed")
    reconciled = _events_of(events, "effect_reconciled")
    source = _applicable_artifact(artifacts, "source_capture")
    preparation = _applicable_artifact(artifacts, "preparation")
    preparation_ref = artifacts.get("preparation")
    terminal = _applicable_artifact(artifacts, "terminal")

    if proof == "controller_runtime_positive":
        if (
            len(prepared) != 1 or len(started) != 1 or len(committed) != 1
            or len(terminals) != 1 or preparation is None or terminal is None
            or terminal.get("semantic_verdict") != "PASS"
            or terminals[0].get("result_kind") != "EXECUTED_RESULT"
        ):
            raise AcceptanceError("owner-proof-positive-path-invalid")
    elif proof == "controller_runtime_semantic_negative":
        if (
            len(prepared) != 1 or len(started) != 1 or len(committed) != 1
            or terminals or preparation is None or source is None
            or artifacts["terminal"].get("applicable") is not False
        ):
            raise AcceptanceError("owner-proof-semantic-negative-invalid")
    elif proof == "crash_reconciliation":
        classifications = [event.get("reconciliation") for event in reconciled]
        checkpoint_continuation = (
            owner_sequence_id == "convergence-checkpoint-run"
            and len(committed) == 1
            and len(terminals) == 1
            and terminals[0].get("result_kind") == "EXECUTED_RESULT"
        )
        if (
            len(prepared) != 1 or len(started) != 1 or committed
            and not checkpoint_continuation
            or classifications != ["NOT_APPLIED", "ALREADY_APPLIED"]
            or len(terminals) != 1
            or (
                terminals[0].get("result_kind") != "RECOVERED_RESULT"
                and not checkpoint_continuation
            )
            or preparation is None or terminal is None
        ):
            raise AcceptanceError("owner-proof-crash-reconciliation-invalid")
    elif proof == "terminal_semantics":
        if (
            len(terminals) != 1 or terminal is None
            or terminal.get("semantic_verdict") != "PASS"
            or terminal.get("effect_id") != terminals[0].get("effect_id")
        ):
            raise AcceptanceError("owner-proof-terminal-exactly-once-invalid")
    elif proof == "effect_identity_source_binding":
        if preparation is None or source is None:
            raise AcceptanceError("owner-proof-source-identity-artifact-missing")
        raw = source.get("raw_source_facts")
        ownership = raw.get("ownership") if isinstance(raw, Mapping) else None
        identity = raw.get("identity") if isinstance(raw, Mapping) else None
        independently_derived_identity = (
            sha256_bytes(canonical_bytes({
                "effect_id": ownership.get("effect_id"),
                "owner_sequence_id": ownership.get("owner_sequence_id"),
                "profile": trace["profile_id"],
            })) if isinstance(ownership, Mapping) else None
        )
        if (
            not isinstance(ownership, Mapping)
            or not isinstance(identity, Mapping)
            or ownership.get("effect_id") != preparation.get("effect_id")
            or ownership.get("owner_sequence_id")
            != preparation.get("owner_sequence_id")
            or ownership.get("preparation_artifact_sha256")
            != preparation_ref.get("sha256")
            or identity.get("observed_sha256") != independently_derived_identity
        ):
            raise AcceptanceError("owner-proof-source-identity-binding-invalid")
    elif proof == "production_source_probe_backend":
        if (
            source is None
            or source.get("transport_kind") != "PRODUCTION_SOURCE_PROBE"
            or not isinstance(source.get("raw_source_facts"), Mapping)
        ):
            raise AcceptanceError("owner-proof-production-capture-invalid")


def _trace_path(trace_sha256: str, trace_dir: Path | None = None) -> Path:
    if (
        not isinstance(trace_sha256, str) or len(trace_sha256) != 64
        or any(character not in "0123456789abcdef" for character in trace_sha256)
    ):
        raise AcceptanceError("owner-proof-reference-invalid")
    return (trace_dir or TRACE_DIR) / f"{trace_sha256}.json"


def _load_trace(
    trace_sha256: str, trace_dir: Path | None = None,
    *, require_current_bindings: bool, use_source_root: bool = True,
) -> dict[str, Any]:
    path = _trace_path(trace_sha256, trace_dir)
    try:
        raw = path.read_bytes()
        trace = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise AcceptanceError("owner-proof-trace-unavailable") from exc
    if sha256_bytes(raw) != trace_sha256 or raw != canonical_bytes(trace):
        raise AcceptanceError("owner-proof-content-address-invalid")
    if not isinstance(trace, Mapping) or set(trace) != TRACE_FIELDS:
        raise AcceptanceError("owner-proof-trace-fields-invalid")
    if trace.get("schema_version") != 1 or trace.get("applicability") != "REQUIRED":
        raise AcceptanceError("owner-proof-trace-contract-invalid")
    if trace.get("production_backend_id") != "PRODUCTION_SOURCE_PROBE_V1":
        raise AcceptanceError("owner-proof-non-production-backend")
    source_bindings = trace.get("source_bindings")
    test_bindings = trace.get("test_bindings")
    if (
        not isinstance(source_bindings, list) or not source_bindings
        or not isinstance(test_bindings, list) or not test_bindings
        or any(not _binding_shape_valid(row) for row in [*source_bindings, *test_bindings])
    ):
        raise AcceptanceError("owner-proof-binding-invalid")
    required_tests = {str(PRODUCER_PATH), str(FIXTURES_PATH)}
    resolved_tests = {
        str(_binding_path(
            str(row["path"]), use_source_root=use_source_root,
        ))
        for row in test_bindings
    }
    if require_current_bindings and resolved_tests != required_tests:
        raise AcceptanceError("owner-proof-producer-binding-invalid")
    if require_current_bindings and any(
        not _binding_current(row, use_source_root=use_source_root)
        for row in [*source_bindings, *test_bindings]
    ):
        raise AcceptanceError("owner-proof-binding-drift")
    for name in (
        "acceptance_contract_sha256", "parameter_policy_sha256",
        "reconciliation_policy_sha256", "terminal_policy_sha256",
        "provider_implementation_sha256", "runner_command_sha256",
    ):
        value = trace.get(name)
        if (
            not isinstance(value, str) or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise AcceptanceError(f"owner-proof-hash-invalid:{name}")
    events = trace.get("journal_events")
    if not isinstance(events, list) or trace.get("journal_events_sha256") != sha256_bytes(
        canonical_bytes(events)
    ):
        raise AcceptanceError("owner-proof-journal-evidence-invalid")
    artifacts = trace.get("artifacts")
    if (
        not isinstance(artifacts, Mapping) or set(artifacts) != set(ARTIFACT_KINDS)
        or any(not _artifact_valid(value) for value in artifacts.values())
    ):
        raise AcceptanceError("owner-proof-artifacts-invalid")
    if (
        trace.get("proof_kind") not in PROOF_KINDS
        or trace.get("expected_outcome")
        != PROOF_OUTCOMES.get(trace.get("proof_kind"))
        or trace.get("expected_outcome") != trace.get("observed_outcome")
    ):
        raise AcceptanceError("owner-proof-outcome-mismatch")
    _validate_proof_semantics(trace)
    return dict(trace)


def load_trace(
    trace_sha256: str, trace_dir: Path | None = None,
    *, use_source_root: bool = True,
) -> dict[str, Any]:
    return _load_trace(
        trace_sha256, trace_dir, require_current_bindings=True,
        use_source_root=use_source_root,
    )


def write_trace(trace: Mapping[str, Any], trace_dir: Path | None = None) -> str:
    """Persist one canonical immutable trace only after replay validation passes."""
    payload = canonical_bytes(dict(trace))
    trace_sha256 = sha256_bytes(payload)
    selected_dir = trace_dir or TRACE_DIR
    selected_dir.mkdir(parents=True, exist_ok=True)
    path = selected_dir / f"{trace_sha256}.json"
    if path.is_file() and path.read_bytes() != payload:
        raise AcceptanceError("owner-proof-content-address-conflict")
    if not path.is_file():
        path.write_bytes(payload)
    # Validate through the same reader/report path; never trust the producer.
    try:
        load_trace(trace_sha256, selected_dir)
    except Exception:
        if path.is_file() and path.read_bytes() == payload:
            path.unlink()
        raise
    return trace_sha256


def _profiles(owner_contract: Mapping[str, Any]) -> list[str]:
    reconciliation = {
        row["profile"] for row in owner_contract["reconciliation_contract"]["observables"]
    }
    terminal = {
        row["profile"] for row in owner_contract["terminal_contract"]["observables"]
    }
    if reconciliation != terminal or not reconciliation:
        raise AcceptanceError("owner-proof-profile-contract-invalid")
    return sorted(reconciliation)


def required_profile_set_sha256(owner_contract: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_bytes(_profiles(owner_contract)))


def _proof_requirements(
    owner_contract: Mapping[str, Any],
) -> dict[tuple[str, str], Mapping[str, Any]]:
    rows = owner_contract.get("acceptance_proofs")
    if not isinstance(rows, list):
        raise AcceptanceError("owner-proof-applicability-contract-invalid")
    expected_profiles = _profiles(owner_contract)
    indexed: dict[tuple[str, str], Mapping[str, Any]] = {}
    seen_profiles: list[str] = []
    for row in rows:
        if (
            not isinstance(row, Mapping)
            or set(row) != {"profile_id", "proofs"}
            or not isinstance(row.get("profile_id"), str)
            or not isinstance(row.get("proofs"), list)
        ):
            raise AcceptanceError("owner-proof-applicability-contract-invalid")
        profile = str(row["profile_id"])
        seen_profiles.append(profile)
        for proof in row["proofs"]:
            if not isinstance(proof, Mapping):
                raise AcceptanceError("owner-proof-applicability-contract-invalid")
            proof_kind = proof.get("proof_kind")
            applicability = proof.get("applicability")
            key = (profile, str(proof_kind))
            if key in indexed or proof_kind not in PROOF_KINDS:
                raise AcceptanceError("owner-proof-applicability-contract-invalid")
            if applicability == "REQUIRED":
                if set(proof) != {"proof_kind", "applicability"}:
                    raise AcceptanceError("owner-proof-applicability-contract-invalid")
            elif applicability == "NOT_APPLICABLE":
                if set(proof) != {
                    "proof_kind", "applicability", "contract_clause_pointer",
                    "contract_clause_sha256",
                }:
                    raise AcceptanceError("owner-proof-applicability-contract-invalid")
                clause_hash = proof.get("contract_clause_sha256")
                if (
                    not isinstance(proof.get("contract_clause_pointer"), str)
                    or not isinstance(clause_hash, str) or len(clause_hash) != 64
                    or any(character not in "0123456789abcdef" for character in clause_hash)
                ):
                    raise AcceptanceError("owner-proof-applicability-contract-invalid")
            else:
                raise AcceptanceError("owner-proof-applicability-contract-invalid")
            indexed[key] = dict(proof)
    expected = {
        (profile, proof) for profile in expected_profiles for proof in PROOF_KINDS
    }
    if sorted(seen_profiles) != expected_profiles or set(indexed) != expected:
        raise AcceptanceError("owner-proof-applicability-contract-incomplete")
    return indexed


def verify_owner_report(
    report: Mapping[str, Any], owner_contract: Mapping[str, Any],
) -> Mapping[str, Any]:
    owner_id = owner_contract["owner_sequence_id"]
    use_source_root = _source_root_enabled(str(owner_id))
    if report.get("schema_version") != 2:
        raise AcceptanceError("owner-proof-report-schema-invalid")
    provider = report.get("provider_implementation")
    if not _binding_current(provider, use_source_root=use_source_root):
        raise AcceptanceError("owner-proof-provider-drift")
    rows = [
        row for row in report.get("owners", [])
        if isinstance(row, Mapping) and row.get("owner_sequence_id") == owner_id
    ]
    if len(rows) != 1:
        raise AcceptanceError("owner-proof-owner-row-invalid")
    row = rows[0]
    profiles = _profiles(owner_contract)
    if (
        row.get("required_profile_ids") != profiles
        or row.get("required_profile_set_sha256")
        != required_profile_set_sha256(owner_contract)
    ):
        raise AcceptanceError("owner-proof-profile-set-drift")
    entries = row.get("proof_references")
    if not isinstance(entries, list):
        raise AcceptanceError("owner-proof-reference-set-invalid")
    requirements = _proof_requirements(owner_contract)
    expected = set(requirements)
    indexed: dict[tuple[str, str], Mapping[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise AcceptanceError("owner-proof-reference-invalid")
        key = (entry["profile_id"], entry["proof_kind"])
        if key in indexed:
            raise AcceptanceError("owner-proof-reference-duplicate")
        requirement = requirements.get(key)
        if requirement is None or entry.get("applicability") != requirement["applicability"]:
            raise AcceptanceError("owner-proof-reference-invalid")
        if entry["applicability"] == "REQUIRED":
            if set(entry) != {
                "profile_id", "proof_kind", "applicability", "trace_sha256",
            }:
                raise AcceptanceError("owner-proof-reference-invalid")
        else:
            if set(entry) != {
                "profile_id", "proof_kind", "applicability",
                "contract_clause_pointer", "contract_clause_sha256",
            } or any(
                entry.get(name) != requirement.get(name)
                for name in ("contract_clause_pointer", "contract_clause_sha256")
            ):
                raise AcceptanceError("owner-proof-reference-invalid")
        indexed[key] = dict(entry)
    if set(indexed) != expected:
        raise AcceptanceError("owner-proof-reference-set-incomplete")
    for key, entry in indexed.items():
        if entry["applicability"] == "NOT_APPLICABLE":
            continue
        trace = load_trace(
            str(entry["trace_sha256"]), use_source_root=use_source_root,
        )
        if (
            (trace["profile_id"], trace["proof_kind"]) != key
            or trace["owner_sequence_id"] != owner_id
            or trace["case_id"] != f"{owner_id}/{key[0]}/v1"
            or trace["acceptance_contract_sha256"]
            != owner_contract["acceptance_contract_sha256"]
            or trace["parameter_policy_sha256"]
            != owner_contract["parameter_contract"]["policy_sha256"]
            or trace["reconciliation_policy_sha256"]
            != owner_contract["reconciliation_contract"]["policy_sha256"]
            or trace["terminal_policy_sha256"]
            != owner_contract["terminal_contract"]["policy_sha256"]
            or trace["provider_implementation_sha256"] != provider["sha256"]
        ):
            raise AcceptanceError("owner-proof-trace-identity-drift")
        expected_sources = {
            (item["path"], item["sha256"])
            for item in owner_contract["implementation_sources"]
        }
        actual_sources = {
            (item["path"], item["sha256"])
            for item in trace["source_bindings"]
        }
        if actual_sources != expected_sources:
            raise AcceptanceError("owner-proof-source-binding-set-drift")
    return {
        "contract_verification": "VERIFIED",
        "dispatch_admission": (
            "STANDALONE" if owner_contract["standalone"] else "PARENT_GATED"
        ),
        "reason_code": "SOURCE_PATH_VERIFIED",
        "required_profile_set_sha256": row["required_profile_set_sha256"],
        "proof_corpus_sha256": sha256_bytes(canonical_bytes(entries)),
    }


def _trace_matches_current_contract(
    trace: Mapping[str, Any],
    owner_contract: Mapping[str, Any],
    provider_sha256: str,
) -> bool:
    expected_sources = {
        (item["path"], item["sha256"])
        for item in owner_contract["implementation_sources"]
    }
    actual_sources = {
        (item["path"], item["sha256"])
        for item in trace["source_bindings"]
    }
    expected_tests = {str(PRODUCER_PATH), str(FIXTURES_PATH)}
    test_bindings = trace["test_bindings"]
    return (
        trace["owner_sequence_id"] == owner_contract["owner_sequence_id"]
        and trace["case_id"]
        == f"{owner_contract['owner_sequence_id']}/{trace['profile_id']}/v1"
        and trace["acceptance_contract_sha256"]
        == owner_contract["acceptance_contract_sha256"]
        and trace["parameter_policy_sha256"]
        == owner_contract["parameter_contract"]["policy_sha256"]
        and trace["reconciliation_policy_sha256"]
        == owner_contract["reconciliation_contract"]["policy_sha256"]
        and trace["terminal_policy_sha256"]
        == owner_contract["terminal_contract"]["policy_sha256"]
        and trace["provider_implementation_sha256"] == provider_sha256
        and len(trace["source_bindings"]) == len(expected_sources)
        and actual_sources == expected_sources
        and len(test_bindings) == len(expected_tests)
        and {
            str(_binding_path(
                str(item["path"]),
                use_source_root=_source_root_enabled(
                    str(owner_contract["owner_sequence_id"])
                ),
            ))
            for item in test_bindings
        } == expected_tests
        and all(
            _binding_current(
                item,
                use_source_root=_source_root_enabled(
                    str(owner_contract["owner_sequence_id"])
                ),
            )
            for item in test_bindings
        )
    )


def _scan_traces(
    contracts: list[Mapping[str, Any]],
    provider_sha256: str,
) -> dict[tuple[str, str, str], str]:
    result: dict[tuple[str, str, str], str] = {}
    owners = {
        str(owner["owner_sequence_id"]): owner for owner in contracts
    }
    if not TRACE_DIR.is_dir():
        return result
    for path in sorted(TRACE_DIR.glob("*.json")):
        trace = _load_trace(
            path.stem, require_current_bindings=False,
        )
        owner = owners.get(str(trace["owner_sequence_id"]))
        if owner is None or not _trace_matches_current_contract(
            trace, owner, provider_sha256,
        ):
            continue
        key = (trace["owner_sequence_id"], trace["profile_id"], trace["proof_kind"])
        # Immutable proof history can contain more than one independently valid
        # execution for the same current binding after a restarted batch. Use a
        # stable content-addressed representative; every candidate has already
        # passed the complete current-contract check above.
        result[key] = min(path.stem, result.get(key, path.stem))
    return result


def assemble_report(contracts_path: Path = CONTRACTS) -> dict[str, Any]:
    contracts = _read_object(contracts_path, "owner-contracts").get("owners")
    if not isinstance(contracts, list):
        raise AcceptanceError("owner-contracts-invalid")
    provider = {
        "path": str(PROVIDER_PATH),
        "sha256": sha256_bytes(PROVIDER_PATH.read_bytes()),
    }
    traces = _scan_traces(contracts, provider["sha256"])
    owners = []
    for owner in contracts:
        owner_id = owner["owner_sequence_id"]
        profiles = _profiles(owner)
        requirements = _proof_requirements(owner)
        references = []
        for profile in profiles:
            for proof in PROOF_KINDS:
                requirement = requirements[(profile, proof)]
                if requirement["applicability"] == "NOT_APPLICABLE":
                    references.append({
                        "profile_id": profile,
                        "proof_kind": proof,
                        "applicability": "NOT_APPLICABLE",
                        "contract_clause_pointer": requirement[
                            "contract_clause_pointer"
                        ],
                        "contract_clause_sha256": requirement[
                            "contract_clause_sha256"
                        ],
                    })
                    continue
                key = (owner_id, profile, proof)
                if key not in traces:
                    raise AcceptanceError(
                        f"owner-proof-current-trace-missing:{owner_id}:{profile}:{proof}"
                    )
                references.append({
                    "profile_id": profile, "proof_kind": proof,
                    "applicability": "REQUIRED", "trace_sha256": traces[key],
                })
        owners.append({
            "owner_sequence_id": owner_id,
            "required_profile_ids": profiles,
            "required_profile_set_sha256": required_profile_set_sha256(owner),
            "proof_references": references,
        })
    return {
        "schema_version": 2,
        "provider_implementation": provider,
        "owners": owners,
    }


def validate_report(path: Path = OUTPUT, contracts_path: Path = CONTRACTS) -> dict[str, Any]:
    report = _read_object(path, "owner-proof-report")
    contracts = _read_object(contracts_path, "owner-contracts").get("owners")
    if not isinstance(contracts, list) or len(contracts) != 10:
        raise AcceptanceError("owner-contracts-invalid")
    for owner in contracts:
        verify_owner_report(report, owner)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    report = validate_report(args.output) if args.check else assemble_report()
    if not args.check:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(canonical_bytes(report))
    print(json.dumps({
        "ok": True, "owners": len(report["owners"]),
        "output": str(args.output), "sha256": sha256_bytes(canonical_bytes(report)),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
