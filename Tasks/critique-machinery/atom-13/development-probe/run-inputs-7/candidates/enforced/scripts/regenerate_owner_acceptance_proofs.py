#!/usr/bin/env python3
"""Regenerate every currently required owner-acceptance proof trace."""

from __future__ import annotations

import json

try:
    from scripts import (
        prevention_owner_acceptance,
        prevention_contract_materializer,
        prevention_owner_acceptance_producer,
    )
    from scripts.prevention_contract import sha256_bytes
except ModuleNotFoundError:  # direct script execution
    import prevention_owner_acceptance
    import prevention_contract_materializer
    import prevention_owner_acceptance_producer
    from prevention_contract import sha256_bytes


POSITIVE_PROOFS = {
    "controller_runtime_positive",
    "terminal_semantics",
    "production_source_probe_backend",
}
NEGATIVE_PROOFS = {"controller_runtime_semantic_negative"}
CRASH_PROOFS = {
    "crash_reconciliation",
    "effect_identity_source_binding",
}


def required_proofs_by_profile(owner: dict) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for row in owner["acceptance_proofs"]:
        profile = str(row["profile_id"])
        result[profile] = {
            str(proof["proof_kind"])
            for proof in row["proofs"]
            if proof["applicability"] == "REQUIRED"
        }
    return result


def current_trace_references(owners: list[dict]) -> dict[tuple[str, str, str], str]:
    provider_sha256 = sha256_bytes(
        prevention_owner_acceptance.PROVIDER_PATH.read_bytes()
    )
    return prevention_owner_acceptance._scan_traces(owners, provider_sha256)


def regenerate() -> dict:
    owners = prevention_contract_materializer.materialize()["owners"]
    current = current_trace_references(owners)
    trace_sha256s: set[str] = set()
    executed_scenarios = 0
    required_scenarios = 0
    for owner in sorted(owners, key=lambda item: item["owner_sequence_id"]):
        owner_id = str(owner["owner_sequence_id"])
        for profile, required in sorted(required_proofs_by_profile(owner).items()):
            trace_sha256s.update(
                current[key]
                for proof in required
                if (key := (owner_id, profile, proof)) in current
            )
            if required & POSITIVE_PROOFS:
                required_scenarios += 1
                if not all(
                    (owner_id, profile, proof) in current
                    for proof in required & POSITIVE_PROOFS
                ):
                    trace_sha256s.update(
                        prevention_owner_acceptance_producer.write_positive_traces(
                            owner_id, profile,
                        )
                    )
                    executed_scenarios += 1
            if required & NEGATIVE_PROOFS:
                required_scenarios += 1
                if not all(
                    (owner_id, profile, proof) in current
                    for proof in required & NEGATIVE_PROOFS
                ):
                    trace_sha256s.add(
                        prevention_owner_acceptance_producer.write_negative_trace(
                            owner_id, profile,
                        )
                    )
                    executed_scenarios += 1
            if required & CRASH_PROOFS:
                required_scenarios += 1
                if not all(
                    (owner_id, profile, proof) in current
                    for proof in required & CRASH_PROOFS
                ):
                    trace_sha256s.update(
                        prevention_owner_acceptance_producer.write_crash_traces(
                            owner_id, profile,
                        )
                    )
                    executed_scenarios += 1
            print(json.dumps({
                "owner_sequence_id": owner_id,
                "profile_id": profile,
                "required_proof_count": len(required),
            }, sort_keys=True), flush=True)
    return {
        "ok": True,
        "owner_count": len(owners),
        "profile_count": sum(
            len(required_proofs_by_profile(owner)) for owner in owners
        ),
        "scenario_count": required_scenarios,
        "executed_scenario_count": executed_scenarios,
        "trace_count": len(trace_sha256s),
    }


def main() -> int:
    print(json.dumps(regenerate(), sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
