#!/usr/bin/env python3
"""Deterministically observe completed governed work without executing it."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import time
from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Iterable, Sequence

try:
    from scripts import (
        discovery_bootstrap, discovery_candidate_reconciliation,
        sequence_candidate_contract as contract, work_memory,
    )
except ImportError:
    import discovery_bootstrap  # type: ignore
    import discovery_candidate_reconciliation  # type: ignore
    import sequence_candidate_contract as contract  # type: ignore
    import work_memory  # type: ignore


OBSERVER_VERSION = 1
RULE_VERSION = 1
VALUE_THRESHOLD = 20
DISPOSITIONS = {"NO_CANDIDATE", "LINK_REGISTERED", "LINK_DISCOVERY", "PROPOSE_DISCOVERY"}
RISK_VALUES = {
    "read-only": 0, "single-test": 0, "single-build": 0,
    "other": 5,
    "image": 15, "container": 15, "workflow-drive": 15, "package": 15,
    "auth": 20, "deploy": 20, "database": 20, "remote-operator": 20,
    "cleanup": 20,
}
EXTERNAL_KINDS = {
    "image", "container", "auth", "deploy", "workflow-drive", "package",
    "database", "remote-operator", "cleanup",
}


class ObserverError(RuntimeError):
    def __init__(self, code: str, exit_code: int = 3):
        super().__init__(code)
        self.code = code
        self.exit_code = exit_code


@dataclass(frozen=True)
class ObserverConfig:
    schema_version: int = 1
    maximum_evidence_age_days: int = 90
    maximum_observation_count: int = 512
    maximum_candidate_writes: int = 1
    maximum_elapsed_ms: int = 2000
    value_threshold: int = VALUE_THRESHOLD
    suppression_days: int = 30
    governed_suppression_days: int = 90
    allowed_repository_keys: tuple[str, ...] = ("memory-knowledge",)
    allowed_path_prefixes: tuple[str, ...] = (
        "scripts/", "operations/sequences/", "tests/", "Tasks/", "working-agreement/",
    )
    cursor_recorded_at_utc: str | None = None
    cursor_event_id: str | None = None

    def validate(self) -> None:
        if (
            self.schema_version != 1
            or self.maximum_evidence_age_days <= 0
            or not 1 <= self.maximum_observation_count
            <= work_memory.OBSERVER_EVIDENCE_MAX_ITEMS
            or self.maximum_candidate_writes != 1
            or not 1 <= self.maximum_elapsed_ms <= 2000
            or self.value_threshold < 0
            or (self.cursor_recorded_at_utc is None) != (self.cursor_event_id is None)
            or not self.allowed_repository_keys
            or not self.allowed_path_prefixes
            or any(not contract._safe_id(item, "invalid-allowed-repository-key") for item in self.allowed_repository_keys)
            or any(not item or item.startswith("/") or ".." in item.split("/") for item in self.allowed_path_prefixes)
        ):
            raise ObserverError("invalid-observer-config", 2)
        if self.cursor_recorded_at_utc is not None:
            work_memory.parse_utc(self.cursor_recorded_at_utc)

    @property
    def digest(self) -> str:
        self.validate()
        return contract.sha256(asdict(self))


def _ordered(events: Iterable[dict[str, Any]], *, reverse: bool = False) -> list[dict[str, Any]]:
    return sorted(
        events,
        key=lambda event: (event.get("recorded_at_utc", ""), event.get("event_id", "")),
        reverse=reverse,
    )


def _component(name: str, status: str, value: int, evidence: Iterable[str]) -> dict[str, Any]:
    return {
        "name": name, "status": status, "value": value,
        "evidence_event_ids": sorted(set(evidence)),
    }


def _empty_eligibility(reason: str) -> dict[str, Any]:
    return {"version": 1, "eligible": False, "triggers": [], "reasons": [reason]}


def _suppression(suppressed: bool, reason: str | None, expires: str | None) -> dict[str, Any]:
    return {
        "rule_version": 1, "suppressed": suppressed,
        "reason": reason, "expires_at_utc": expires,
    }


def _candidate_steps(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{
        "step_ordinal": claim["step_ordinal"],
        "step_id": claim["step_id"],
        "argv": claim["argv"],
        "command_source": claim["command_source"],
        "source_ref": claim["source_ref"],
        "operation_kind": claim["operation_kind"],
    } for claim in claims]


def _reconstruct(
    events: list[dict[str, Any]], start: dict[str, Any], terminal: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None, list[str], str | None]:
    related = [event for event in events if event.get("run_id") == start["run_id"]]
    contexts = [event for event in related if event["event_type"] == "operation_context_recorded"]
    if len(contexts) != 1:
        return None, None, [event["event_id"] for event in related], "operation-context-incomplete"
    context = contexts[0]
    claims = sorted(
        (event for event in related if event["event_type"] == "execution_claimed"),
        key=lambda event: event["step_ordinal"],
    )
    returns = {
        event["execution_id"]: event
        for event in related if event["event_type"] == "execution_returned"
    }
    if (
        not claims
        or [claim["step_ordinal"] for claim in claims] != list(range(len(claims)))
        or any(claim["execution_id"] not in returns for claim in claims)
        or any(returns[claim["execution_id"]]["result"] != "passed" for claim in claims)
    ):
        return None, None, [event["event_id"] for event in related], "execution-evidence-incomplete"
    if terminal["result"] != "passed":
        return None, None, [event["event_id"] for event in related], "terminal-not-passed"
    verification = contract.final_effective_verification(
        related, run_id=start["run_id"], lineage_id=start["lineage_id"],
        source_bundle_hash=start["source_bundle_hash"],
    )
    if verification is None:
        return None, None, [event["event_id"] for event in related], "final-verification-not-proven"
    if verification["evidence"] != context["verification_contract"]["success_evidence"]:
        return None, None, [event["event_id"] for event in related], "verification-evidence-mismatch"
    governed = {
        "run_id": {start["run_id"]},
        "event_id": {event["event_id"] for event in related},
        "timestamp": {
            str(event[field]) for event in related
            for field in ("recorded_at_utc", "started_at_utc", "completed_at_utc",
                          "claimed_at_utc", "returned_at_utc")
            if field in event
        },
        "task_id": set(),
        "receipt_path": set(),
    }
    context_payload = {
        key: context[key] for key in (
            "intended_outcome", "repeatability_reason", "repeatability_evidence_ids",
            "required_inputs", "dependencies", "failure_handling", "verification_contract",
            "effect_class", "environment_annotations", "semantic_flag_annotations",
            "volatility_annotations",
        )
    }
    try:
        identity, fingerprint = contract.build_candidate_identity(
            context_payload, _candidate_steps(claims), governed_values=governed,
        )
    except contract.CandidateContractError as exc:
        return None, None, [event["event_id"] for event in related], exc.code
    evidence_ids = [context["event_id"], terminal["event_id"], verification["event_id"]]
    evidence_ids.extend(claim["event_id"] for claim in claims)
    evidence_ids.extend(returns[claim["execution_id"]]["event_id"] for claim in claims)
    evidence_ids.extend(
        event["event_id"] for event in related
        if event["event_type"] in {"blocker_opened", "blocker_recurred", "correction_recorded"}
    )
    return identity, fingerprint, sorted(set(evidence_ids)), None


def _eligibility(
    start: dict[str, Any], context: dict[str, Any], identity: dict[str, Any],
    related: list[dict[str, Any]], governed_recurrence_ids: list[str],
    governed_corrections: list[dict[str, Any]],
) -> dict[str, Any]:
    triggers: list[str] = []
    step_count = len(identity["steps"])
    if step_count >= 3:
        triggers.append("three-or-more-steps")
    if governed_recurrence_ids:
        triggers.append("evidenced-recurrence")
    if start["operation_kind"] in EXTERNAL_KINDS:
        triggers.append("external-or-standing-operation-kind")
    if context["environment_annotations"] or context["semantic_flag_annotations"]:
        triggers.append("special-environment-or-semantic-flags")
    if _has_repeated_blocker_fingerprint(governed_corrections):
        triggers.append("repeated-corrected-failure")
    eligible = bool(triggers)
    if step_count == 1 and start["operation_kind"] in work_memory.NON_OPERATIONAL and len(triggers) == 0:
        eligible = False
    return {
        "version": 1, "eligible": eligible,
        "triggers": sorted(set(triggers)),
        "reasons": [] if eligible else ["no-eligibility-trigger"],
    }


def _value_components(
    start: dict[str, Any], terminal: dict[str, Any], context: dict[str, Any],
    identity: dict[str, Any], related: list[dict[str, Any]],
    governed_recurrence_ids: list[str], governed_corrections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    recurrence_ids = governed_recurrence_ids
    recurrence_value = 20 if len(set(recurrence_ids)) >= 2 else (10 if recurrence_ids else 0)
    recurrence = _component(
        "recurrence", "KNOWN", recurrence_value,
        recurrence_ids,
    )
    try:
        seconds = (
            work_memory.parse_utc(terminal["completed_at_utc"])
            - work_memory.parse_utc(start["started_at_utc"])
        ).total_seconds()
        effort_value = 20 if seconds >= 1800 else (10 if seconds >= 600 else (5 if seconds >= 120 else 0))
        effort = _component("saved_effort", "KNOWN", effort_value, [start["event_id"], terminal["event_id"]])
    except (KeyError, ValueError):
        effort = _component("saved_effort", "UNKNOWN", 0, [])
    corrections = governed_corrections
    repeated = _has_repeated_blocker_fingerprint(corrections)
    correction_value = 20 if repeated else (10 if corrections else 0)
    correction = _component(
        "correction_reduction", "KNOWN", correction_value,
        [event["event_id"] for event in corrections],
    )
    risk = _component(
        "operational_risk", "KNOWN", RISK_VALUES[start["operation_kind"]], [start["event_id"]],
    )
    steps = len(identity["steps"])
    reconstruction_value = 20 if steps >= 6 else (10 if steps >= 3 else 0)
    if context["environment_annotations"] or context["semantic_flag_annotations"]:
        reconstruction_value = max(10, reconstruction_value)
    reconstruction = _component(
        "reconstruction_avoided", "KNOWN", reconstruction_value,
        [event["event_id"] for event in related if event["event_type"] == "execution_claimed"],
    )
    return [recurrence, effort, correction, risk, reconstruction]


def _governed_value_evidence(
    events: list[dict[str, Any]], start: dict[str, Any], terminal: dict[str, Any],
    fingerprint: str, context: dict[str, Any],
) -> tuple[list[str], list[dict[str, Any]]]:
    """Credit only compatible prior runs and successor-verified corrections."""
    decisions = [
        event for event in events
        if event["event_type"] == "observer_decision_recorded"
        and event.get("candidate_fingerprint") == fingerprint
        and event.get("trigger_event_id") != terminal["event_id"]
    ]
    compatible_terminals = {
        event["event_id"]: event for event in events
        if event["event_type"] == "run_closed" and event["result"] == "passed"
        and event["event_id"] in {decision["trigger_event_id"] for decision in decisions}
    }
    starts = {
        event["run_id"]: event for event in events if event["event_type"] == "run_started"
    }
    proven_terminal_ids: set[str] = set()
    compatible_run_ids: set[str] = set()
    for terminal_id, prior_terminal in compatible_terminals.items():
        prior_start = starts.get(prior_terminal["run_id"])
        if prior_start is None:
            continue
        if contract.final_effective_verification(
            events, run_id=prior_start["run_id"], lineage_id=prior_start["lineage_id"],
            source_bundle_hash=prior_start["source_bundle_hash"],
        ) is None:
            continue
        proven_terminal_ids.add(terminal_id)
        compatible_run_ids.add(prior_start["run_id"])
    recurrence_ids = sorted(
        set(context["repeatability_evidence_ids"]) & proven_terminal_ids
    )
    correction_rows = [
        event for event in events
        if event["event_type"] == "correction_recorded"
        and event["run_id"] in compatible_run_ids
    ]
    superseded = {
        correction_id for event in correction_rows
        for correction_id in work_memory._superseded_correction_ids(event)
    }
    blocker_states: dict[str, str] = {}
    blocker_fingerprints: dict[str, str] = {}
    for event in events:
        if event["event_type"] == "blocker_opened":
            blocker_states[event["blocker_id"]] = event["status"]
            blocker_fingerprints[event["blocker_id"]] = event["fingerprint"]
        elif event["event_type"] == "blocker_recurred" and event["blocker_id"] in blocker_states:
            blocker_states[event["blocker_id"]] = event["status"]
        elif event["event_type"] == "blocker_transitioned" and event["blocker_id"] in blocker_states:
            blocker_states[event["blocker_id"]] = event["to_status"]
    governed: list[dict[str, Any]] = []
    for correction in correction_rows:
        correction_id = correction["correction_id"]
        if correction_id in superseded or blocker_states.get(correction["blocker_id"]) != "closed":
            continue
        successors = [
            item for item in starts.values()
            if item.get("predecessor_run_id") == correction["run_id"]
            and correction_id in item.get("verifies_correction_ids", [])
            and item["lineage_id"] == correction["lineage_id"]
        ]
        if any(
            contract.final_effective_verification(
                events, run_id=successor["run_id"], lineage_id=successor["lineage_id"],
                source_bundle_hash=successor["source_bundle_hash"],
            ) is not None
            and any(
                item["event_type"] == "run_closed" and item["run_id"] == successor["run_id"]
                and item["result"] == "passed" for item in events
            )
            for successor in successors
        ):
            blocker_fingerprint = blocker_fingerprints.get(correction["blocker_id"])
            if blocker_fingerprint is not None:
                governed.append({
                    **correction, "blocker_fingerprint": blocker_fingerprint,
                })
    return recurrence_ids, governed


def _has_repeated_blocker_fingerprint(corrections: list[dict[str, Any]]) -> bool:
    counts: dict[str, int] = {}
    for correction in corrections:
        fingerprint = correction.get("blocker_fingerprint")
        if isinstance(fingerprint, str):
            counts[fingerprint] = counts.get(fingerprint, 0) + 1
    return any(count >= 2 for count in counts.values())


def _proposal_completeness_error(
    context: dict[str, Any], claims: list[dict[str, Any]],
) -> str | None:
    for field in ("repeatability_evidence_ids", "required_inputs", "failure_handling"):
        if not context[field]:
            return f"missing-{field.replace('_', '-')}"
    verify_steps = [claim for claim in claims if claim["step_id"] == "verify-automation"]
    if len(verify_steps) != 1:
        return "missing-exact-verify-automation-step"
    dependencies = {
        (item["repository_key"], item["path"])
        for item in context["dependencies"]
    }
    missing_sources = [
        claim["source_ref"] for claim in claims
        if (claim["source_ref"]["repository_key"], claim["source_ref"]["path"])
        not in dependencies
    ]
    if missing_sources:
        return "missing-command-source-dependency"
    return None


def _identity_within_surfaces(identity: dict[str, Any], config: ObserverConfig) -> bool:
    allowed_keys = set(config.allowed_repository_keys)
    prefixes = config.allowed_path_prefixes
    refs = [step["source_ref"] for step in identity["steps"]]
    refs.extend(identity["dependencies"])
    return all(
        item["repository_key"] in allowed_keys
        and any(item["path"].startswith(prefix) for prefix in prefixes)
        for item in refs
    )


def _document_section(text: str, heading: str) -> str | None:
    match = re.search(
        rf"^## {re.escape(heading)}\s*$\n(.*?)(?=^## |\Z)", text, re.M | re.S,
    )
    return match.group(1).strip() if match else None


def _document_metadata(text: str, name: str) -> str | None:
    match = re.search(rf"^{re.escape(name)}:\s*(.*?)\s*$", text, re.M)
    return match.group(1) if match else None


def _legacy_candidate_identity(
    document: Path, manifest: dict[str, Any], row: dict[str, str],
) -> dict[str, Any] | None:
    """Reconstruct only a fully explicit legacy identity; never infer missing semantics."""
    try:
        text = document.read_text(encoding="utf-8")
        outcome = _document_section(text, "Outcome")
        inputs_text = _document_section(text, "Required Inputs")
        commands_text = _document_section(text, "Commands")
        failures_text = _document_section(text, "Failure Handling")
        verification_text = _document_section(text, "Verification")
        effect_class = _document_metadata(text, "CandidateEffectClass")
        environment = json.loads(_document_metadata(text, "CandidateEnvironmentAnnotations") or "null")
        semantic_flags = json.loads(_document_metadata(text, "CandidateSemanticFlagAnnotations") or "null")
        volatility = json.loads(_document_metadata(text, "CandidateVolatilityPolicy") or "null")
        kinds = sorted(filter(None, row.get("operation_kinds", "").split(",")))
        if (
            not all((outcome, inputs_text, commands_text, failures_text, verification_text, effect_class))
            or len(kinds) != 1
            or not all(isinstance(item, list) for item in (environment, semantic_flags, volatility))
        ):
            return None
        inputs = [
            line[2:].strip() for line in inputs_text.splitlines()
            if line.startswith("- ") and line[2:].strip()
        ]
        dependencies = []
        for item in manifest.get("dependencies", []):
            if (
                not isinstance(item, dict) or item.get("kind") != "file"
                or not isinstance(item.get("repository_key"), str)
                or not isinstance(item.get("path_or_sequence_id"), str)
            ):
                return None
            dependencies.append({
                "repository_key": item["repository_key"],
                "path": item["path_or_sequence_id"],
            })
        recovery_ids = {
            "record-correction", "record-protected-correction", "launch-protected-correction",
            "transition-corrected-blocker", "close-corrected-predecessor",
        }
        steps = []
        for line in commands_text.splitlines():
            if not line.strip().startswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) < 4 or cells[0] in {"step", "---"} or set(cells[0]) == {"-"}:
                continue
            if cells[0] in recovery_ids:
                continue
            provenance = re.fullmatch(
                r"Guard provenance: (sequence_doc|discovery_log|script|tool_help):"
                r"([A-Za-z0-9][A-Za-z0-9._:-]{0,127}):(.+)",
                cells[3],
            )
            if provenance is None:
                return None
            steps.append({
                "step_ordinal": len(steps), "step_id": cells[0],
                "argv": shlex.split(cells[1]), "command_source": provenance.group(1),
                "source_ref": {
                    "repository_key": provenance.group(2), "path": provenance.group(3),
                },
                "operation_kind": kinds[0],
            })
        failures = [{
            "fingerprint": match.group(1), "symptom": match.group(2).strip(),
            "response": match.group(3).strip(),
        } for match in re.finditer(
            r"([0-9a-f]{64}):\s*([^;]+?)\s*->\s*([^;]+)", failures_text,
        )]
        verification_lines = [
            line[2:].strip() for line in verification_text.splitlines()
            if line.startswith("- ") and line[2:].strip()
        ]
        if not inputs or not dependencies or not steps or not failures or len(verification_lines) != 1:
            return None
        return contract.normalize_candidate_identity({
            "schema_version": 1, "steps": steps, "intended_outcome": outcome,
            "required_inputs": inputs, "dependencies": dependencies,
            "failure_handling": failures,
            "verification_contract": {
                "quality": "same-path", "expected_outcome": "passed",
                "success_evidence": verification_lines[0],
            },
            "effect_class": effect_class,
            "environment_annotations": environment,
            "semantic_flag_annotations": semantic_flags,
            "volatility_policy": volatility,
        })
    except (OSError, ValueError, json.JSONDecodeError, contract.CandidateContractError):
        return None


def _registered_identity_is_proven(
    sequence_id: str, document: Path, manifest_path: Path,
    events: list[dict[str, Any]],
) -> tuple[bool, str | None]:
    try:
        _, bundle_hash, lineage = work_memory.resolve_bundle(
            mode="registered", subject_id=sequence_id, document=document,
            manifest=manifest_path, include_bootstrap_trust_anchors=True,
        )
    except (OSError, work_memory.WorkMemoryError):
        return False, "registered-bundle-invalid"
    starts = [
        event for event in events
        if event["event_type"] == "run_started" and event["subject_id"] == sequence_id
        and event["source_bundle_hash"] == bundle_hash
    ]
    passed_terminals = {
        event["run_id"] for event in events
        if event["event_type"] == "run_closed" and event["subject_id"] == sequence_id
        and event["result"] == "passed"
    }
    proven = any(
        start["run_id"] in passed_terminals and
        contract.final_effective_verification(
            events, run_id=start["run_id"], lineage_id=lineage,
            source_bundle_hash=bundle_hash,
        ) is not None
        for start in starts
    )
    return proven, None if proven else "registered-match-unverified"


def _registered_match(
    identity: dict[str, Any], fingerprint: str, operation_kind: str,
    events: list[dict[str, Any]],
) -> tuple[str | None, list[str], str | None]:
    rows, _ = work_memory.registry_rows()
    considered: list[str] = []
    first_source = identity["steps"][0]["source_ref"]["path"]
    for row in rows:
        sequence_id = row["sequence_id"]
        manifest_path = work_memory.ROOT / "operations/sequences" / sequence_id / "dependencies.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        stored_identity = manifest.get("candidate_identity")
        stored_fingerprint = manifest.get("candidate_fingerprint")
        if stored_identity is None and stored_fingerprint is None:
            considered.append(sequence_id)
            legacy_identity = _legacy_candidate_identity(
                work_memory.ROOT / "operations/sequences" / sequence_id / "sequence.md",
                manifest, row,
            )
            if legacy_identity == identity:
                document = work_memory.ROOT / "operations/sequences" / sequence_id / "sequence.md"
                proven, error = _registered_identity_is_proven(
                    sequence_id, document, manifest_path, events,
                )
                return (sequence_id if proven else None), considered, error
            kinds = set(filter(None, row.get("operation_kinds", "").split(",")))
            if operation_kind in kinds and (
                first_source in shlex.split(row.get("automation_display", ""))
            ):
                return None, considered, "legacy-registered-identity-ambiguous"
            continue
        considered.append(sequence_id)
        try:
            stored_identity = contract.validate_candidate_identity(stored_identity, stored_fingerprint)
        except contract.CandidateContractError:
            return None, considered, "invalid-registered-candidate-identity"
        if stored_fingerprint == fingerprint and stored_identity != identity:
            return None, considered, "candidate-fingerprint-collision"
        if stored_identity != identity:
            continue
        document = work_memory.ROOT / "operations/sequences" / sequence_id / "sequence.md"
        proven, error = _registered_identity_is_proven(
            sequence_id, document, manifest_path, events,
        )
        return (sequence_id if proven else None), considered, error
    return None, considered, None


def _discovery_match(
    identity: dict[str, Any], fingerprint: str,
    *, events: list[dict[str, Any]] | None = None,
    repository_roots: dict[str, str] | None = None,
) -> tuple[str | None, list[str], str | None]:
    try:
        rows = discovery_candidate_reconciliation.candidate_identity_inventory(
            work_memory.ROOT, events=events, repository_roots=repository_roots,
        )
    except discovery_candidate_reconciliation.ReconciliationError:
        return None, [], "discovery-inventory-invalid"
    considered = [row["discovery_id"] for row in rows]
    exact = []
    for row in rows:
        if row["candidate_fingerprint"] == fingerprint and row["candidate_identity"] != identity:
            return None, considered, "candidate-fingerprint-collision"
        if row["candidate_identity"] == identity:
            exact.append(row["discovery_id"])
    if len(exact) > 1:
        return None, considered, "multiple-active-discovery-matches"
    return (exact[0] if exact else None), considered, None


def _persist_event(event_type: str, domain_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    event_id = contract.deterministic_uuid(
        f"memory-knowledge:observer:event:{event_type}:{payload[domain_id]}"
    )
    events, _ = work_memory.load_ledger()
    event = work_memory._event(
        event_type, event_id,
        recorded_at_utc=work_memory._observer_recorded_at(event_type, payload, events),
        **payload,
    )
    result = work_memory.transact({
        "schema_version": 1, "expected_ledger_hash": None, "events": [event],
    })
    return {**result, "event_id": event_id, domain_id: payload[domain_id]}


def _decision_payload(
    *, config: ObserverConfig, terminal: dict[str, Any], ledger_hash: str,
    evidence_ids: list[str], identity: dict[str, Any] | None,
    fingerprint: str | None, eligibility: dict[str, Any],
    components: list[dict[str, Any]], disposition: str,
    target_kind: str | None, target_id: str | None,
    considered_registered: list[str], considered_discovery: list[str],
    safe_failure_code: str | None, cap_cursor: dict[str, str] | None = None,
    suppression: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence_hash = contract.sha256(sorted(evidence_ids))
    cursor_label = "root" if cap_cursor is None else f"{cap_cursor['recorded_at_utc']}:{cap_cursor['event_id']}"
    decision_id = contract.deterministic_uuid(
        "memory-knowledge:observer:decision:"
        f"{terminal['event_id']}:{OBSERVER_VERSION}:{RULE_VERSION}:{config.digest}:"
        f"{ledger_hash}:{cursor_label}"
    )
    return {
        "decision_id": decision_id,
        "observer_version": OBSERVER_VERSION,
        "rule_version": RULE_VERSION,
        "config_hash": config.digest,
        "trigger_event_id": terminal["event_id"],
        "trigger_type": "run_closed",
        "ledger_snapshot_hash": ledger_hash,
        "evidence_event_ids": sorted(evidence_ids),
        "evidence_set_hash": evidence_hash,
        "candidate_identity": identity,
        "candidate_fingerprint": fingerprint,
        "eligibility": eligibility,
        "value_components": components,
        "threshold": config.value_threshold,
        "considered_registered_ids": sorted(considered_registered),
        "considered_discovery_ids": sorted(considered_discovery),
        "disposition": disposition,
        "target_kind": target_kind,
        "target_id": target_id,
        "suppression": suppression or _suppression(False, None, None),
        "cap_cursor": cap_cursor,
        "safe_failure_code": safe_failure_code,
    }


def _proposal_spec(
    decision: dict[str, Any], start: dict[str, Any], terminal: dict[str, Any],
    context: dict[str, Any], claims: list[dict[str, Any]],
) -> dict[str, Any]:
    fingerprint = decision["candidate_fingerprint"]
    trigger_prefix = terminal["event_id"].replace("-", "")[:12]
    failure_text = "; ".join(
        f"{item['fingerprint']}: {item['symptom']} -> {item['response']}"
        for item in context["failure_handling"]
    )
    if not failure_text:
        raise ObserverError("missing-failure-handling-evidence")
    return {
        "schema_version": 1,
        "task_id": f"observer-{fingerprint[:12]}-{trigger_prefix}",
        "operation_kind": start["operation_kind"],
        "date": terminal["completed_at_utc"][:10],
        "sequence_name": f"observed-{fingerprint[:16]}",
        "outcome": context["intended_outcome"],
        "why_repeatable": context["repeatability_reason"],
        "steps": [{
            "step": claim["step_id"],
            "command": shlex.join(claim["argv"]),
            "result": "passed",
            "note": f"Guard provenance: {claim['command_source']}:{claim['source_ref']['repository_key']}:{claim['source_ref']['path']}",
        } for claim in claims],
        "inputs": context["required_inputs"],
        "failure_handling": failure_text,
        "verified_path": context["verification_contract"]["success_evidence"],
        "dependencies": [{
            "kind": "file", "repository_key": item["repository_key"],
            "path_or_sequence_id": item["path"],
        } for item in context["dependencies"]],
        "candidate_identity": decision["candidate_identity"],
        "candidate_fingerprint": fingerprint,
        "observer_provenance": {
            "decision_id": decision["decision_id"],
            "observer_version": OBSERVER_VERSION,
            "rule_version": RULE_VERSION,
        },
    }


def _complete_proposal(
    decision: dict[str, Any], start: dict[str, Any], terminal: dict[str, Any],
    context: dict[str, Any], claims: list[dict[str, Any]],
) -> dict[str, Any]:
    spec = discovery_bootstrap.normalize_spec(
        _proposal_spec(decision, start, terminal, context, claims)
    )
    repository_roots = start.get("repository_roots")
    request = {"spec": spec, "repo_roots_file": None}
    if repository_roots is not None:
        request["repository_roots"] = repository_roots
    request_hash = contract.sha256(request)
    events, _ = work_memory.load_ledger()
    prior = [
        event for event in events
        if event["event_type"] == "observer_bootstrap_result_recorded"
        and event["decision_id"] == decision["decision_id"]
        and event["bootstrap_request_sha256"] == request_hash
    ]
    successful = next((event for event in prior if event["outcome"] == "succeeded"), None)
    if successful is None:
        attempt_ordinal = len(prior)
        attempt_id = contract.deterministic_uuid(
            f"memory-knowledge:observer:bootstrap:{decision['decision_id']}:{request_hash}:{attempt_ordinal}"
        )
        try:
            result = discovery_bootstrap.bootstrap(
                spec, root=work_memory.ROOT, repo_roots_file=None,
                repository_roots=repository_roots,
            )
            result_payload = {
                "bootstrap_attempt_id": attempt_id,
                "attempt_ordinal": attempt_ordinal,
                "decision_id": decision["decision_id"],
                "bootstrap_request_sha256": request_hash,
                "outcome": "succeeded",
                "safe_error_code": None,
                "retryable": False,
                "discovery_id": result["discovery_id"],
                "lineage_id": result["discovery_id"],
                "run_id": result["run_id"],
                "source_bundle_hash": result["source_bundle_hash"],
                "document_path": str(Path(result["discovery_path"]).relative_to(work_memory.ROOT)),
                "manifest_path": str(Path(result["manifest_path"]).relative_to(work_memory.ROOT)),
            }
        except (OSError, KeyError, work_memory.WorkMemoryError) as exc:
            code = getattr(exc, "code", type(exc).__name__)
            result_payload = {
                "bootstrap_attempt_id": attempt_id, "attempt_ordinal": attempt_ordinal,
                "decision_id": decision["decision_id"],
                "bootstrap_request_sha256": request_hash, "outcome": "failed",
                "safe_error_code": str(code), "retryable": True,
                "discovery_id": None, "lineage_id": None, "run_id": None,
                "source_bundle_hash": None, "document_path": None, "manifest_path": None,
            }
        _persist_event(
            "observer_bootstrap_result_recorded", "bootstrap_attempt_id", result_payload,
        )
        successful = result_payload if result_payload["outcome"] == "succeeded" else None
    if successful is None:
        return {"ok": False, "status": "BOOTSTRAP_FAILED", "decision_id": decision["decision_id"]}
    link_id = contract.deterministic_uuid(
        f"memory-knowledge:observer:link:{decision['decision_id']}:discovery:{successful['discovery_id']}"
    )
    _persist_event("observer_candidate_linked", "link_id", {
        "link_id": link_id, "decision_id": decision["decision_id"],
        "candidate_fingerprint": decision["candidate_fingerprint"],
        "target_kind": "discovery", "target_id": successful["discovery_id"],
        "link_kind": "proposed",
    })
    return {
        "ok": True, "status": "PROPOSED", "decision_id": decision["decision_id"],
        "disposition": "PROPOSE_DISCOVERY", "target_id": successful["discovery_id"],
    }


def observe_committed_run(
    run_id: str, *, config: ObserverConfig | None = None,
) -> dict[str, Any]:
    started_at = time.monotonic()
    config = config or ObserverConfig()
    config.validate()
    events, ledger_hash = work_memory.load_ledger()
    start, related = work_memory._run_state(events, run_id)
    terminals = [
        event for event in related
        if event["event_type"] in {"run_closed", "run_abandoned"}
    ]
    if len(terminals) != 1 or terminals[0]["event_type"] != "run_closed":
        raise ObserverError("observer-requires-closed-run")
    terminal = terminals[0]
    existing = next((
        event for event in events
        if event["event_type"] == "observer_decision_recorded"
        and event["trigger_event_id"] == terminal["event_id"]
        and event["config_hash"] == config.digest
        and event["rule_version"] == RULE_VERSION
    ), None)
    if existing is not None:
        if existing["disposition"] == "PROPOSE_DISCOVERY":
            context = next(event for event in related if event["event_type"] == "operation_context_recorded")
            claims = sorted(
                (event for event in related if event["event_type"] == "execution_claimed"),
                key=lambda event: event["step_ordinal"],
            )
            return _complete_proposal(existing, start, terminal, context, claims)
        return {
            "ok": True, "status": "ALREADY_OBSERVED", "decision_id": existing["decision_id"],
            "disposition": existing["disposition"], "target_id": existing["target_id"],
        }

    ordered_related = _ordered(related, reverse=True)
    if len(ordered_related) > config.maximum_observation_count:
        remaining_related = ordered_related
        if config.cursor_recorded_at_utc is not None:
            cursor_tuple = (config.cursor_recorded_at_utc, config.cursor_event_id)
            remaining_related = [
                event for event in remaining_related
                if (event.get("recorded_at_utc", ""), event["event_id"]) < cursor_tuple
            ]
        consumed = remaining_related[:config.maximum_observation_count]
        if len(remaining_related) <= config.maximum_observation_count:
            payload = _decision_payload(
                config=config, terminal=terminal, ledger_hash=ledger_hash,
                evidence_ids=[event["event_id"] for event in consumed],
                identity=None, fingerprint=None,
                eligibility=_empty_eligibility("pagination-incomplete"), components=[],
                disposition="NO_CANDIDATE", target_kind=None, target_id=None,
                considered_registered=[], considered_discovery=[],
                safe_failure_code="PAGINATION_INCOMPLETE",
            )
            _persist_event("observer_decision_recorded", "decision_id", payload)
            return {
                "ok": True, "status": "OBSERVED", "decision_id": payload["decision_id"],
                "disposition": "NO_CANDIDATE", "cap_cursor": None,
            }
        last = consumed[-1]
        cursor = {"recorded_at_utc": last["recorded_at_utc"], "event_id": last["event_id"]}
        payload = _decision_payload(
            config=config, terminal=terminal, ledger_hash=ledger_hash,
            evidence_ids=[event["event_id"] for event in consumed],
            identity=None, fingerprint=None,
            eligibility=_empty_eligibility("evidence-cap-reached"), components=[],
            disposition="NO_CANDIDATE", target_kind=None, target_id=None,
            considered_registered=[], considered_discovery=[],
            safe_failure_code="CAP_REACHED", cap_cursor=cursor,
        )
        _persist_event("observer_decision_recorded", "decision_id", payload)
        return {
            "ok": True, "status": "CAP_REACHED", "decision_id": payload["decision_id"],
            "disposition": "NO_CANDIDATE", "cap_cursor": cursor,
        }

    identity, fingerprint, evidence_ids, reconstruction_error = _reconstruct(
        related, start, terminal,
    )
    cutoff = work_memory.parse_utc(terminal["completed_at_utc"]) - timedelta(
        days=config.maximum_evidence_age_days
    )
    age_bounded = [
        event for event in events
        if event.get("run_id") == run_id
        or work_memory.parse_utc(event["recorded_at_utc"]) >= cutoff
    ]
    registry_rows, _ = work_memory.registry_rows()
    registered_subject_ids = {
        row["sequence_id"] for row in registry_rows
        if start["operation_kind"] in row["operation_kinds"].split(",")
    }
    try:
        discovery_rows = discovery_candidate_reconciliation.candidate_identity_inventory(
            work_memory.ROOT,
        )
    except discovery_candidate_reconciliation.ReconciliationError:
        discovery_rows = []
    discovery_subject_ids = {row["discovery_id"] for row in discovery_rows}
    candidate_subject_ids = {
        start["lineage_id"], *registered_subject_ids, *discovery_subject_ids,
    }
    decision_terminal_ids = {
        event["trigger_event_id"] for event in age_bounded
        if event["event_type"] == "observer_decision_recorded"
        and fingerprint is not None
        and event.get("candidate_fingerprint") == fingerprint
    }
    candidate_run_ids = {
        event["run_id"] for event in age_bounded
        if event["event_type"] == "run_closed" and event["event_id"] in decision_terminal_ids
    }
    candidate_run_ids.update(
        event["run_id"] for event in age_bounded
        if event["event_type"] == "run_started"
        and event.get("predecessor_run_id") in candidate_run_ids
    )
    historical = _ordered((
        event for event in age_bounded
        if event.get("run_id") != run_id
        and (
            event.get("run_id") in candidate_run_ids
            or event.get("subject_id") in candidate_subject_ids
            or event.get("lineage_id") in candidate_subject_ids
            or (
                event["event_type"].startswith("observer_")
                and fingerprint is not None
                and event.get("candidate_fingerprint") == fingerprint
            )
            or (
                event["event_type"] == "discovery_promoted"
                and (
                    event.get("discovery_id") in discovery_subject_ids
                    or event.get("sequence_id") in registered_subject_ids
                )
            )
        )
    ), reverse=True)
    if config.cursor_recorded_at_utc is not None:
        cursor = (config.cursor_recorded_at_utc, config.cursor_event_id)
        historical = [
            event for event in historical
            if (event.get("recorded_at_utc", ""), event["event_id"]) < cursor
        ]
    history_budget = config.maximum_observation_count - len(related)
    if len(historical) > history_budget:
        consumed_history = historical[:max(0, history_budget)]
        consumed = [*ordered_related, *consumed_history]
        last = consumed_history[-1] if consumed_history else ordered_related[-1]
        cursor = {"recorded_at_utc": last["recorded_at_utc"], "event_id": last["event_id"]}
        payload = _decision_payload(
            config=config, terminal=terminal, ledger_hash=ledger_hash,
            evidence_ids=sorted(set(evidence_ids) | {event["event_id"] for event in consumed}),
            identity=identity, fingerprint=fingerprint,
            eligibility=_empty_eligibility("evidence-cap-reached"), components=[],
            disposition="NO_CANDIDATE", target_kind=None, target_id=None,
            considered_registered=[], considered_discovery=[],
            safe_failure_code="CAP_REACHED", cap_cursor=cursor,
        )
        _persist_event("observer_decision_recorded", "decision_id", payload)
        return {
            "ok": True, "status": "CAP_REACHED", "decision_id": payload["decision_id"],
            "disposition": "NO_CANDIDATE", "cap_cursor": cursor,
        }
    observed_events = [*related, *historical]
    relevant = _ordered(observed_events, reverse=True)
    context = next((event for event in related if event["event_type"] == "operation_context_recorded"), None)
    considered_registered: list[str] = []
    considered_discovery: list[str] = []
    safe_error = reconstruction_error
    target_kind = target_id = None
    disposition = "NO_CANDIDATE"
    eligibility = _empty_eligibility(reconstruction_error or "candidate-incomplete")
    components: list[dict[str, Any]] = []

    def elapsed_cap_result() -> dict[str, Any]:
        evidence_set = set(evidence_ids)
        consumed = [event for event in relevant if event["event_id"] in evidence_set]
        last = consumed[-1] if consumed else (relevant[0] if relevant else terminal)
        cursor = {
            "recorded_at_utc": last["recorded_at_utc"], "event_id": last["event_id"],
        }
        payload = _decision_payload(
            config=config, terminal=terminal, ledger_hash=ledger_hash,
            evidence_ids=evidence_ids, identity=identity, fingerprint=fingerprint,
            eligibility=eligibility, components=components,
            disposition="NO_CANDIDATE", target_kind=None, target_id=None,
            considered_registered=considered_registered,
            considered_discovery=considered_discovery,
            safe_failure_code="CAP_REACHED", cap_cursor=cursor,
        )
        _persist_event("observer_decision_recorded", "decision_id", payload)
        return {
            "ok": True, "status": "CAP_REACHED", "decision_id": payload["decision_id"],
            "disposition": "NO_CANDIDATE", "cap_cursor": cursor,
        }

    def elapsed_cap_reached() -> bool:
        return (time.monotonic() - started_at) * 1000 > config.maximum_elapsed_ms

    if elapsed_cap_reached():
        return elapsed_cap_result()

    if identity is not None and fingerprint is not None and context is not None:
        claims = sorted(
            (event for event in related if event["event_type"] == "execution_claimed"),
            key=lambda event: event["step_ordinal"],
        )
        governed_recurrence, governed_corrections = _governed_value_evidence(
            observed_events, start, terminal, fingerprint, context,
        )
        eligibility = _eligibility(
            start, context, identity, related, governed_recurrence, governed_corrections,
        )
        components = _value_components(
            start, terminal, context, identity, related,
            governed_recurrence, governed_corrections,
        )
        score = sum(component["value"] for component in components)
        positive = any(component["status"] == "KNOWN" and component["value"] > 0 for component in components)
        if not _identity_within_surfaces(identity, config):
            safe_error = "candidate-surface-not-allowed"
        else:
            if elapsed_cap_reached():
                return elapsed_cap_result()
            registered, considered_registered, match_error = _registered_match(
                identity, fingerprint, start["operation_kind"], observed_events,
            )
            if elapsed_cap_reached():
                return elapsed_cap_result()
            safe_error = match_error
            if registered:
                disposition, target_kind, target_id = "LINK_REGISTERED", "registered", registered
            elif match_error is None:
                discovery, considered_discovery, match_error = _discovery_match(
                    identity, fingerprint, events=observed_events,
                    repository_roots=start.get("repository_roots"),
                )
                if elapsed_cap_reached():
                    return elapsed_cap_result()
                safe_error = match_error
                proposal_error = _proposal_completeness_error(context, claims)
                if discovery:
                    disposition, target_kind, target_id = "LINK_DISCOVERY", "discovery", discovery
                elif match_error is None and proposal_error is not None:
                    safe_error = proposal_error
                elif match_error is None and config.cursor_recorded_at_utc is not None:
                    safe_error = "PAGINATION_INCOMPLETE"
                elif match_error is None and eligibility["eligible"] and score >= config.value_threshold and positive:
                    disposition = "PROPOSE_DISCOVERY"
                elif match_error is None:
                    safe_error = "LOW_VALUE_OR_INELIGIBLE"

    prior_suppression = None
    if fingerprint is not None:
        if elapsed_cap_reached():
            return elapsed_cap_result()
        now = work_memory.parse_utc(terminal["completed_at_utc"])
        feedback = (
            discovery_candidate_reconciliation.candidate_lifecycle_feedback(
                work_memory.ROOT, fingerprint=fingerprint, events=observed_events,
            )
            if disposition not in {"LINK_REGISTERED", "LINK_DISCOVERY"}
            else []
        )
        if feedback:
            latest = feedback[-1]
            disposition_name = latest["disposition"]
            recorded_at = work_memory.parse_utc(latest["recorded_at_utc"])
            if disposition_name == "quarantine":
                expiry = recorded_at + timedelta(days=config.governed_suppression_days)
                if now < expiry:
                    prior_suppression = _suppression(
                        True, "governed-quarantine-suppressed",
                        expiry.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                    )
            elif disposition_name in {
                "promoted", "promote", "absorb", "supersede", "already-promoted",
                "registered-reuse",
            }:
                prior_suppression = _suppression(
                    True, f"governed-{disposition_name}-suppressed", None,
                )
        for event in reversed(observed_events):
            if prior_suppression is not None:
                break
            if (
                event["event_type"] == "observer_decision_recorded"
                and event["candidate_fingerprint"] == fingerprint
                and event["rule_version"] == RULE_VERSION
                and event["evidence_set_hash"] == contract.sha256(sorted(evidence_ids))
                and event["disposition"] == "NO_CANDIDATE"
            ):
                expiry = work_memory.parse_utc(event["recorded_at_utc"]) + timedelta(days=config.suppression_days)
                if now < expiry:
                    prior_suppression = _suppression(
                        True, "unchanged-evidence-suppressed",
                        expiry.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                    )
                break
        if elapsed_cap_reached():
            return elapsed_cap_result()
    if prior_suppression is not None:
        disposition, target_kind, target_id = "NO_CANDIDATE", None, None
        safe_error = "SUPPRESSED"

    payload = _decision_payload(
        config=config, terminal=terminal, ledger_hash=ledger_hash,
        evidence_ids=evidence_ids, identity=identity, fingerprint=fingerprint,
        eligibility=eligibility, components=components, disposition=disposition,
        target_kind=target_kind, target_id=target_id,
        considered_registered=considered_registered,
        considered_discovery=considered_discovery,
        safe_failure_code=safe_error, suppression=prior_suppression,
    )
    _persist_event("observer_decision_recorded", "decision_id", payload)
    if disposition == "PROPOSE_DISCOVERY":
        claims = sorted(
            (event for event in related if event["event_type"] == "execution_claimed"),
            key=lambda event: event["step_ordinal"],
        )
        return _complete_proposal(payload, start, terminal, context, claims)
    if disposition in {"LINK_REGISTERED", "LINK_DISCOVERY"}:
        link_id = contract.deterministic_uuid(
            f"memory-knowledge:observer:link:{payload['decision_id']}:{target_kind}:{target_id}"
        )
        _persist_event("observer_candidate_linked", "link_id", {
            "link_id": link_id, "decision_id": payload["decision_id"],
            "candidate_fingerprint": fingerprint, "target_kind": target_kind,
            "target_id": target_id, "link_kind": "existing",
        })
    return {
        "ok": True, "status": "OBSERVED", "decision_id": payload["decision_id"],
        "disposition": disposition, "target_id": target_id,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--maximum-observation-count", type=int, default=512)
    parser.add_argument("--maximum-elapsed-ms", type=int, default=2000)
    parser.add_argument("--value-threshold", type=int, default=VALUE_THRESHOLD)
    parser.add_argument("--maximum-evidence-age-days", type=int, default=90)
    parser.add_argument("--allowed-repository-key", action="append")
    parser.add_argument("--allowed-path-prefix", action="append")
    parser.add_argument("--cursor-recorded-at-utc")
    parser.add_argument("--cursor-event-id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = observe_committed_run(args.run_id, config=ObserverConfig(
            maximum_evidence_age_days=args.maximum_evidence_age_days,
            maximum_observation_count=args.maximum_observation_count,
            maximum_elapsed_ms=args.maximum_elapsed_ms,
            value_threshold=args.value_threshold,
            allowed_repository_keys=tuple(args.allowed_repository_key or ("memory-knowledge",)),
            allowed_path_prefixes=tuple(args.allowed_path_prefix or ObserverConfig().allowed_path_prefixes),
            cursor_recorded_at_utc=args.cursor_recorded_at_utc,
            cursor_event_id=args.cursor_event_id,
        ))
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ObserverError, work_memory.WorkMemoryError) as exc:
        print(json.dumps({"ok": False, "error": exc.code}, sort_keys=True))
        return exc.exit_code
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__}, sort_keys=True))
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
