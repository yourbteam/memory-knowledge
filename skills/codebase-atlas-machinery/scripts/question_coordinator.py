#!/usr/bin/env python3
"""Prepare and validate a resumable answer over every accepted map for one controller."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if os.fspath(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, os.fspath(SCRIPT_DIR))

import atlas  # noqa: E402
import csharp_facts  # noqa: E402


SCHEMA_VERSION = 1
DEFAULT_LIMIT = 10_000_000
ARTIFACTS = {
    "selection-packet.json", "candidate-observations.json", "selection.json", "answer-packet.json", "answer.json",
    "review.json", "answer-review-packet.json", "review-result.json", "correction-packet.json",
    "corrected-answer-packet.json", "corrected-review.json", "accepted-package.json", "evidence-gap.json",
}
EXPANSION_PACKET = "expansion-review-packet.json"
EXPANSION_REVIEW = "expansion-review.json"
EXPANSION_PACKAGE = "expansion-package.json"
EXPANSION_IMPORT_BINDING = "expansion-import-binding.json"
EXPANSION_SCHEMA_VERSION = 2
EXPANSION_PACKAGE_SCHEMA_VERSION = 1
EXPANSION_IMPORT_BINDING_SCHEMA_VERSION = 1
EXPANSION_SELECTION_AUTHORITY_VERSION = 1
EXPANSION_SELECTOR_VIEW_VERSION = 1
EXPANSION_MAX_BYTES = 50_000_000
EXPANSION_GRAMMAR = "csharp-member-const-literal-v1"
C_SHARP_KEYWORDS = {
    "abstract", "as", "base", "bool", "break", "byte", "case", "catch", "char", "checked", "class", "const",
    "continue", "decimal", "default", "delegate", "do", "double", "else", "enum", "event", "explicit", "extern",
    "false", "finally", "fixed", "float", "for", "foreach", "goto", "if", "implicit", "in", "int", "interface",
    "internal", "is", "lock", "long", "namespace", "new", "null", "object", "operator", "out", "override",
    "params", "private", "protected", "public", "readonly", "ref", "return", "sbyte", "sealed", "short", "sizeof",
    "stackalloc", "static", "string", "struct", "switch", "this", "throw", "true", "try", "typeof", "uint", "ulong",
    "unchecked", "unsafe", "ushort", "using", "virtual", "void", "volatile", "while", "add", "alias", "ascending",
    "async", "await", "by", "descending", "dynamic", "equals", "from", "get", "global", "group", "init", "into",
    "join", "let", "managed", "nameof", "not", "notnull", "on", "or", "orderby", "partial", "record", "remove",
    "select", "set", "unmanaged", "value", "var", "when", "where", "with", "yield", "and", "file", "required", "scoped",
}
EXPANSION_FORBIDDEN = {
    "answer-packet.json", "answer.json", "review.json", "answer-review-packet.json",
    "review-result.json", "correction-packet.json", "corrected-answer-packet.json",
    "corrected-review.json", "accepted-package.json",
}
EXPANSION_REVIEW_SCHEMA = {
    "version": 2,
    "fields": ["candidate_reviews", "decision", "obligation_reviews", "packet_sha256", "reviewer_identity", "reviewer_model", "review_schema_version"],
    "obligation_fields": ["basis", "classification", "obligation_id", "selected_candidate_ids"],
    "candidate_fields": ["basis", "candidate_id", "disposition"],
    "classifications": ["local_evidence", "external_or_unresolved"],
    "dispositions": ["selected", "not_selected"],
    "decisions": ["accepted", "rejected"],
    "reviewer_model": "GPT-6.1 Sol High",
}
_EXPANSION_REVIEW_SCHEMA_V1 = {**EXPANSION_REVIEW_SCHEMA, "version": 1}

# These definitions are the sole authority for both the model-facing contracts and
# the validators. Packet prose and the accepted wire format must never drift apart.
SELECTION_RECORD_SCHEMA = {
    "version": 1,
    "top_level_fields": ["selection_schema_version", "packet_sha256", "reviewer_identity", "reviewer_model", "candidate_reviews", "obligation_reviews"],
    "candidate_fields": {"route_fact_id": "string; exact candidate route.id", "decision": "accept or reject", "basis": "nonempty concrete semantic basis of at least 20 characters"},
    "candidate_decisions": ["accept", "reject"],
    "obligation_fields": {"obligation_id": "exact string from obligation_ids", "candidate_status": "present_in_candidates or absent_from_candidates", "supporting_route_fact_ids": "array of unique route_fact_id values from the complete candidates; nonempty when present and empty when absent", "basis": "nonempty concrete evidence-based basis of at least 20 characters"},
    "candidate_statuses": ["present_in_candidates", "absent_from_candidates"],
}
ANSWER_RECORD_SCHEMA = {
    "version": 1,
    "top_level_fields": ["question_id", "answer", "material_claims", "limitations", "evidence_measurement"],
    "material_claim_fields": ["assertion", "claim_numbers", "citations"],
    "citation_fields": ["claim_number", "fact_id", "source_id", "path", "sha256", "span", "snippet_id"],
}
REVIEW_RECORD_SCHEMA = {
    "version": 1,
    "top_level_fields": ["review_schema_version", "packet_sha256", "decision", "reviewer_identity", "reviewer_model", "claim_reviews", "obligation_reviews", "failure_kind", "unsupported_assertions"],
    "claim_fields": ["claim_number", "disposition", "basis"],
    "claim_dispositions": ["covered", "not_relevant", "incomplete"],
    "obligation_fields": ["obligation_id", "disposition", "basis"],
    "obligation_dispositions": ["covered", "missing_supported", "evidence_absent", "contradicted"],
    "failure_kinds": ["none", "answer_gap", "evidence_gap"],
    "decisions": ["accepted", "rejected"],
}


def _selection_contract(candidates: list[dict[str, object]], obligations: list[dict[str, object]], required_routes: list[str]) -> dict[str, object]:
    schema = SELECTION_RECORD_SCHEMA
    obligation_ids = _obligation_ids(obligations)
    return {
        "contract_schema_version": schema["version"],
        "selection_record": {
            "encoding": "UTF-8 JSON object; no additional fields",
            "required_top_level_fields": list(schema["top_level_fields"]),
            "fields": {
                "selection_schema_version": {"type": "integer", "exact": schema["version"]},
                "packet_sha256": {"type": "string", "exact": "copy selection-packet.json packet_sha256 exactly", "meaning": "bind selection to these exact candidates and obligations"},
                "reviewer_identity": {"type": "nonempty string", "meaning": "audit label, not authentication"},
                "reviewer_model": {"type": "string", "exact": "GPT-6.1 Sol High", "meaning": "audit label, not authentication"},
                "candidate_reviews": {"type": "array", "length": len(candidates), "ordered_by": "selection-packet.json candidates order", "item_fields": schema["candidate_fields"]},
                "obligation_reviews": {"type": "array", "length": len(obligation_ids), "ordered_by": "obligation_id array below", "item_fields": schema["obligation_fields"]},
            },
            "obligation_ids": obligation_ids,
            "obligations": obligations,
        },
        "packet_hash": {"field": "packet_sha256", "algorithm": "SHA-256 of canonical ASCII JSON (sorted keys, compact separators) with packet_sha256 omitted, plus one trailing newline"},
        "candidate_coverage": "account for every candidate exactly once; every frozen required route must be accepted",
        "required_route_keys": required_routes,
        "required_fact_selection_error": "if a required behavior/comparison/limit is supported by any candidate, name every supporting route_fact_id, and accept every named candidate; any rejected supporting candidate makes selection invalid",
        "evidence_gap": "absent_from_candidates with an empty supporting route list is the only basis for a required evidence gap; the complete bounded candidate set is frozen here",
        "refusal": {"behavior": "exit code 2; stderr begins question-coordinator: and names every offending route/obligation, observed value, and required correction; no stage artifact is overwritten"},
    }


def _answer_schema_contract() -> dict[str, object]:
    schema = ANSWER_RECORD_SCHEMA
    return {"answer_schema_version": schema["version"], "encoding": "UTF-8 JSON object; no additional fields",
            "required_fields": list(schema["top_level_fields"]),
            "fields": {"question_id": {"type": "string", "meaning": "exact frozen obligation identity"},
                       "answer": {"type": "string", "meaning": "exact draft-file UTF-8 text"},
                       "material_claims": {"type": "nonempty array", "item_fields": {
                           "assertion": "nonempty atomic assertion sentence", "claim_numbers": "nonempty unique array of existing global union claim numbers",
                           "citations": {"type": "nonempty array", "exact_item_fields": list(schema["citation_fields"]),
                                         "meaning": "each citation exactly matches one citation on each named union claim, including the union source_id"}}},
                       "limitations": {"type": "array of nonempty strings"},
                       "evidence_measurement": {"type": "object", "exact": {}, "meaning": "Atlas computes lifecycle-v2 measurement"}}}


def _review_schema_contract(obligations: list[dict[str, object]]) -> dict[str, object]:
    schema = REVIEW_RECORD_SCHEMA
    obligation_ids = _obligation_ids(obligations)
    return {"review_schema_version": schema["version"], "encoding": "UTF-8 JSON object; no additional fields",
            "required_top_level_fields": list(schema["top_level_fields"]),
            "packet_hash": {"field": "packet_sha256", "value": "copy this review packet packet_sha256 exactly", "algorithm": "SHA-256 of canonical ASCII JSON (sorted keys, compact separators) with packet_sha256 omitted, plus one trailing newline"},
            "reviewer_identity": "nonempty audit label, not authentication", "reviewer_model": "exact string GPT-6.1 Sol High; audit label, not authentication",
            "claim_reviews": {"coverage": "one entry for every union claim in global claim_number order", "item_fields": {"claim_number": "integer, exact global number", "disposition": ", ".join(schema["claim_dispositions"]), "basis": "concrete nonempty string of at least 20 characters"}},
            "obligation_reviews": {"coverage": "one entry for every frozen behavior, comparison, and limit in the obligations array, in this order", "obligation_ids": obligation_ids, "obligations": obligations, "item_fields": {"obligation_id": "exact ordered ID", "disposition": ", ".join(schema["obligation_dispositions"]), "basis": "concrete nonempty string of at least 20 characters"}},
            "failure_kind": {"allowed": list(schema["failure_kinds"]), "rules": "answer_gap for incomplete claims, missing supported obligations, contradictions, or unsupported assertions; evidence_gap only for evidence_absent obligations whose exact selection record says absent_from_candidates; none only when accepted"},
            "decision": {"allowed": list(schema["decisions"]), "accepted": "failure_kind none, all obligations covered, no incomplete claim and no unsupported assertion", "rejected": "failure_kind answer_gap or evidence_gap"},
            "unsupported_assertions": "array of concrete nonempty unsupported answer assertions; must be empty for accepted"}


def _obligation_ids(obligations: list[dict[str, object]]) -> list[str]:
    return [item["obligation_id"] for item in obligations]


def _route_key(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise CoordinatorError(f"route key observed {value!r}; required a nonempty saved route spelling")
    key = value[4:] if value.startswith("api/") else value
    if not key or key.startswith("/") or "/" in key:
        raise CoordinatorError(f"route key observed {value!r}; required a route literal or its exact api/<literal> spelling")
    return key


class CoordinatorError(Exception):
    """An expected identity, provenance, contract, or stage failure."""


def _bytes(value: object) -> bytes:
    return atlas._canonical_json(value) + b"\n"


def _digest(value: object) -> str:
    return hashlib.sha256(_bytes(value)).hexdigest()


def _read(path: Path, label: str) -> object:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoordinatorError(f"cannot read {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CoordinatorError(f"{label} must contain a JSON object: {path}")
    return value


def _save_immutable(path: Path, value: object) -> None:
    encoded = _bytes(value)
    try:
        existing = os.lstat(path)
    except FileNotFoundError:
        existing = None
    except OSError as exc:
        raise CoordinatorError(f"cannot inspect existing artifact {path}: {exc}") from exc
    if existing is not None:
        if not stat.S_ISREG(existing.st_mode):
            raise CoordinatorError(f"existing immutable artifact is not a regular file: {path}")
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                opened = os.fstat(fd)
                if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (existing.st_dev, existing.st_ino):
                    raise CoordinatorError(f"existing immutable artifact changed during validation: {path}")
                with os.fdopen(fd, "rb", closefd=False) as stream:
                    old = stream.read()
            finally:
                os.close(fd)
        except OSError as exc:
            raise CoordinatorError(f"cannot verify existing artifact {path}: {exc}") from exc
        if old != encoded:
            raise CoordinatorError(f"immutable artifact already exists with different content: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except FileExistsError as exc:
        raise CoordinatorError(f"artifact appeared while saving; verify exact content: {path}") from exc
    with os.fdopen(fd, "wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def _read_artifact(run: Path, name: str) -> dict[str, object]:
    path = run / name
    raw = _read_regular_bytes(path, name)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoordinatorError(f"cannot read {name} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CoordinatorError(f"{name} must contain a JSON object: {path}")
    if raw != _bytes(value):
        raise CoordinatorError(f"stage artifact is not canonical JSON: {path}")
    return value


def _read_regular_bytes(path: Path, label: str) -> bytes:
    try:
        before = os.lstat(path)
    except OSError as exc:
        raise CoordinatorError(f"cannot inspect {label} {path}: {exc}") from exc
    if not stat.S_ISREG(before.st_mode):
        raise CoordinatorError(f"{label} must be a no-follow regular file: {path}")
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            opened = os.fstat(fd)
            if not stat.S_ISREG(opened.st_mode) or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
                raise CoordinatorError(f"{label} changed during no-follow validation: {path}")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                return stream.read()
        finally:
            os.close(fd)
    except OSError as exc:
        raise CoordinatorError(f"cannot read {label} {path}: {exc}") from exc


def _stable_focus(value: dict[str, object]) -> dict[str, object]:
    """Drop observation-only freshness and budget values from semantic identity."""
    result = {key: item for key, item in value.items() if key not in {"freshness", "budget"}}
    return result


def _candidate_set(repo: str, db: str, controller: str, limit: int) -> tuple[dict[str, object], list[dict[str, object]], dict[str, object]]:
    db_path = Path(db).expanduser().resolve(strict=True)
    snapshot, snapshots_by_id, extractor, live = atlas._current_route_snapshot(db_path, repo)
    graph = snapshot.get("source_graph")
    facts = graph.get("facts") if isinstance(graph, dict) else None
    if not isinstance(facts, list) or any(not isinstance(item, dict) for item in facts):
        raise CoordinatorError("current saved source graph facts are malformed")
    fact_ids: set[str] = set()
    for fact in facts:
        fact_id = fact.get("id")
        if not isinstance(fact_id, str) or not fact_id or fact_id in fact_ids:
            raise CoordinatorError(f"current source graph has missing or duplicate fact identity: {fact_id!r}")
        fact_ids.add(fact_id)
    members = sorted((item for item in facts if item.get("kind") == "route_action"
                      and item.get("controller_type_id") == controller), key=lambda item: str(item["id"]))
    if not members:
        raise CoordinatorError(f"controller has no current route_action members: {controller}")
    associations = atlas._validated_route_associations(db, db_path, snapshot, snapshots_by_id)
    candidates: list[dict[str, object]] = []
    errors: list[str] = []
    for route in members:
        route_id = str(route["id"])
        linked = associations.get(route_id, [])
        if len(linked) != 1:
            errors.append(f"route {route_id}: observed accepted-map association count={len(linked)}, required exactly 1")
            continue
        association = linked[0]
        binding = association.get("binding")
        if not isinstance(binding, dict):
            errors.append(f"route {route_id}: accepted association has no binding object")
            continue
        overlay_id = binding.get("overlay_id")
        try:
            found, _rendered, code = atlas.route_find(db, repo, route_id, limit)
        except atlas.AtlasError as exc:
            errors.append(f"route {route_id}, overlay {overlay_id}: fresh complete route retrieval failed: {exc}")
            continue
        if code != 0 or found.get("result") != "fresh" or found.get("association_count") != 1:
            errors.append(f"route {route_id}, overlay {overlay_id}: observed result={found.get('result')!r}, code={code}, required fresh with one association")
            continue
        selection = found.get("claim_selection")
        if (not isinstance(selection, dict) or selection.get("omitted_claims") != 0
                or selection.get("included_claims") != selection.get("total_claims")):
            errors.append(f"route {route_id}, overlay {overlay_id}: observed claim selection={selection!r}, required complete retrieval")
            continue
        flow = atlas.query_flow(db, snapshot["snapshot_id"], str(overlay_id))
        receipt = flow.get("review_receipt")
        if (flow.get("review_status") != "accepted" or not isinstance(receipt, dict)
                or receipt.get("receipt_hash") != binding.get("flow_review_receipt_hash")):
            errors.append(f"route {route_id}, overlay {overlay_id}: accepted flow receipt or association provenance does not match")
            continue
        assoc = found.get("association")
        if not isinstance(assoc, dict) or assoc.get("binding_hash") != association.get("binding_hash") or assoc.get("association_review_hash") != association.get("association_review_hash"):
            errors.append(f"route {route_id}, overlay {overlay_id}: route association hashes changed during retrieval")
            continue
        candidates.append({
            "route": route,
            "map": _stable_focus(found),
            "observations": {"freshness": found.get("freshness"), "budget": found.get("budget")},
            "provenance": {
                "snapshot_id": snapshot["snapshot_id"], "extractor_identity": extractor,
                "route_fact_id": route_id, "overlay_id": overlay_id,
                "overlay_content_hash": flow.get("overlay", {}).get("content_hash"),
                "flow_review_receipt": receipt,
                "binding": binding, "binding_hash": association["binding_hash"],
                "association_review": association["association_review"],
                "association_review_hash": association["association_review_hash"],
                "carry_provenance": association.get("carry_provenance"),
            },
        })
    if errors:
        raise CoordinatorError("incomplete controller candidate set; correct every item and rerun prepare:\n- " + "\n- ".join(errors))
    identity = {
        "repository_root": live["repository_root"], "head": live["head"], "head_ref": live["head_ref"],
        "snapshot_id": snapshot["snapshot_id"], "extractor_identity": extractor,
        "controller_type_id": controller, "repository_status": live["status"],
    }
    return identity, candidates, live


def _candidate_observations(candidates: list[dict[str, object]], packet_sha256: str) -> dict[str, object]:
    record = {"observation_schema_version": 1, "selection_packet_sha256": packet_sha256,
              "observations": [{"route_fact_id": candidate["route"]["id"], **candidate["observations"]}
                               for candidate in candidates]}
    record["observations_sha256"] = _digest(record)
    return record


def _observation_projection(record: dict[str, object]) -> dict[str, object]:
    """Retain every observation fact except freshness.checked_at, which is volatile."""
    projected = []
    for item in record["observations"]:
        freshness = dict(item["freshness"])
        freshness.pop("checked_at")
        projected.append({"route_fact_id": item["route_fact_id"], "freshness": freshness, "budget": item["budget"]})
    return {"observations": projected}


def _validate_candidate_observations(record: object, packet: dict[str, object]) -> dict[str, object]:
    if not isinstance(record, dict) or set(record) != {"observation_schema_version", "selection_packet_sha256", "observations", "observations_sha256"}:
        raise CoordinatorError("candidate observation artifact must contain its exact versioned fields")
    if record.get("observation_schema_version") != 1 or record.get("selection_packet_sha256") != packet.get("packet_sha256"):
        raise CoordinatorError("candidate observation artifact is not bound to this deterministic selection packet")
    expected_hash = _digest({key: value for key, value in record.items() if key != "observations_sha256"})
    if record.get("observations_sha256") != expected_hash:
        raise CoordinatorError(f"candidate observation artifact hash is invalid; observed={record.get('observations_sha256')}, required={expected_hash}")
    observations = record.get("observations")
    expected_ids = [item["route"]["id"] for item in packet.get("candidates", [])]
    if (not isinstance(observations, list) or [item.get("route_fact_id") for item in observations if isinstance(item, dict)] != expected_ids
            or any(not isinstance(item, dict) or set(item) != {"route_fact_id", "freshness", "budget"} for item in observations)):
        raise CoordinatorError("candidate observation artifact does not account for every packet candidate in order")
    for item in observations:
        freshness = item["freshness"]
        if not isinstance(freshness, dict):
            raise CoordinatorError(f"candidate {item['route_fact_id']} freshness observed {freshness!r}; required a freshness object with a UTC checked_at timestamp")
        checked_at = freshness.get("checked_at")
        if not isinstance(checked_at, str) or not checked_at.strip():
            raise CoordinatorError(f"candidate {item['route_fact_id']} freshness.checked_at observed {checked_at!r}; required a nonempty timezone-qualified timestamp")
        try:
            parsed = dt.datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise CoordinatorError(f"candidate {item['route_fact_id']} freshness.checked_at observed {checked_at!r}; required a valid timezone-qualified ISO-8601 timestamp") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise CoordinatorError(f"candidate {item['route_fact_id']} freshness.checked_at observed {checked_at!r}; required an explicit timezone")
        if not isinstance(item["budget"], dict):
            raise CoordinatorError(f"candidate {item['route_fact_id']} budget observed {item['budget']!r}; required a budget object")
    return record


def _obligations(path: Path, question: str) -> tuple[dict[str, object], str, dict[str, str]]:
    try:
        canonical_path = path.expanduser().resolve(strict=True)
        raw = canonical_path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoordinatorError(f"original question obligations observed path={os.fspath(path)!r}, error={exc}; required restore the original readable UTF-8 JSON file and pass that exact file") from exc
    if not isinstance(value, dict):
        raise CoordinatorError(f"question obligations must contain a JSON object; observed {type(value).__name__}")
    questions = value.get("questions")
    if isinstance(questions, dict):
        matches = [(key, item) for key, item in questions.items()
                   if isinstance(item, dict) and item.get("question") == question]
        if len(matches) != 1:
            raise CoordinatorError(f"question must match exactly one frozen obligation record; observed matches={len(matches)} for {question!r}")
        question_id, item = matches[0]
    elif value.get("question") == question:
        question_id = value.get("question_id", "heldout")
        item = value
    else:
        raise CoordinatorError(f"original obligations file has no exact question record for {question!r}; provide the matching frozen wrapper")
    if not isinstance(question_id, str) or not question_id.strip():
        raise CoordinatorError(f"obligation identity observed {question_id!r}; required a nonempty string key")

    raw_routes = item.get("required_routes")
    if not isinstance(raw_routes, list):
        raise CoordinatorError(f"frozen obligations {question_id}.required_routes observed {raw_routes!r}; required a list of saved route spellings")
    route_errors: list[str] = []
    required_routes: list[str] = []
    for index, route in enumerate(raw_routes):
        try:
            required_routes.append(_route_key(route))
        except CoordinatorError as exc:
            route_errors.append(f"required_routes[{index}] observed {route!r}; {exc}; correct it to the exact saved route spelling")
    if len(set(required_routes)) != len(required_routes):
        route_errors.append(f"required_routes contains duplicate canonical keys {required_routes!r}; retain each route once")

    raw_required_ids = item.get("required_behavior_ids")
    heldout_defs = item.get("required_obligations", value.get("required_obligations"))
    if raw_required_ids is None and isinstance(heldout_defs, list):
        raw_required_ids = [entry.get("id") if isinstance(entry, dict) else None for entry in heldout_defs]
    if not isinstance(raw_required_ids, list):
        raise CoordinatorError(f"frozen obligations {question_id}.required_behavior_ids observed {raw_required_ids!r}; required a list of defined behavior IDs")
    behavior_ids: list[str] = []
    for index, identifier in enumerate(raw_required_ids):
        if not isinstance(identifier, str) or not identifier.strip():
            route_errors.append(f"required_behavior_ids[{index}] observed {identifier!r}; required a nonempty string ID with exactly one meaning definition")
        else:
            behavior_ids.append(identifier)
    if len(set(behavior_ids)) != len(behavior_ids):
        duplicates = sorted({identifier for identifier in behavior_ids if behavior_ids.count(identifier) > 1})
        route_errors.append(f"required_behavior_ids contains duplicate IDs {duplicates!r}; retain each obligation once")

    definitions: dict[str, list[tuple[object, str]]] = {}
    malformed_definitions: list[str] = []
    if isinstance(value.get("routes"), dict):
        for route_name, route_record in value["routes"].items():
            behaviors = route_record.get("required_behaviors") if isinstance(route_record, dict) else None
            if not isinstance(behaviors, list):
                continue
            for index, definition in enumerate(behaviors):
                source = f"routes[{route_name!r}].required_behaviors[{index}]"
                if not isinstance(definition, dict):
                    malformed_definitions.append(f"{source}: observed {definition!r}; required an object with string id and nonblank string behavior")
                elif not isinstance(definition.get("id"), str) or not definition.get("id", "").strip():
                    malformed_definitions.append(f"{source}.id: observed {definition.get('id')!r}; required a nonblank string ID")
                else:
                    definitions.setdefault(definition["id"], []).append((definition.get("behavior"), source))
    elif isinstance(heldout_defs, list):
        for index, definition in enumerate(heldout_defs):
            source = f"required_obligations[{index}]"
            if not isinstance(definition, dict):
                malformed_definitions.append(f"{source}: observed {definition!r}; required an object with string id and nonblank string text")
            elif not isinstance(definition.get("id"), str) or not definition.get("id", "").strip():
                malformed_definitions.append(f"{source}.id: observed {definition.get('id')!r}; required a nonblank string ID")
            else:
                definitions.setdefault(definition["id"], []).append((definition.get("text"), source))

    obligation_items: list[dict[str, object]] = []
    definition_errors: list[str] = []
    definition_errors.extend(malformed_definitions)
    for identifier in behavior_ids:
        matches = definitions.get(identifier, [])
        meanings = [meaning for meaning, _source in matches]
        if not matches:
            definition_errors.append(f"{identifier!r}: observed no authoritative definition; required exactly one nonblank string meaning in routes[*].required_behaviors or required_obligations")
        elif len(matches) > 1:
            classification = "conflicting" if len({json.dumps(m, sort_keys=True, ensure_ascii=False) for m in meanings}) > 1 else "duplicate"
            definition_errors.append(f"{identifier!r}: observed {classification} definitions {[(source, meaning) for meaning, source in matches]!r}; required exactly one authoritative definition, remove duplicates or resolve the conflict")
        else:
            meaning = matches[0][0]
            if not isinstance(meaning, str) or not meaning.strip():
                definition_errors.append(f"{identifier!r}: observed meaning {meaning!r}; required one nonblank string definition")
            else:
                obligation_items.append({"obligation_id": identifier, "kind": "behavior", "meaning": meaning})
    for field, kind, prefix in (("required_comparisons", "comparison", "comparison"), ("required_limits", "limit", "limit")):
        values = item.get(field, [])
        if not isinstance(values, list):
            definition_errors.append(f"{question_id}.{field}: observed {values!r}; required a list of nonblank strings")
            continue
        for index, meaning in enumerate(values, 1):
            if not isinstance(meaning, str) or not meaning.strip():
                definition_errors.append(f"{question_id}.{field}[{index - 1}]: observed {meaning!r}; required one nonblank string meaning")
            else:
                obligation_items.append({"obligation_id": f"{prefix}:{index}", "kind": kind, "meaning": meaning})
    obligation_item_ids = [entry["obligation_id"] for entry in obligation_items]
    if len(set(obligation_item_ids)) != len(obligation_item_ids):
        definition_errors.append(f"obligation IDs collide across categories: {obligation_item_ids!r}; give each required obligation one unique ID")
    if route_errors or definition_errors:
        raise CoordinatorError("invalid frozen obligation authority; correct every item:\n- " + "\n- ".join(route_errors + definition_errors))
    normalized = {"required_routes": required_routes, "obligations": obligation_items}
    source_identity = {"path": os.fspath(canonical_path), "sha256": hashlib.sha256(raw).hexdigest()}
    return normalized, question_id, source_identity


def _semantic_payload(identity: dict[str, object], question: str, question_sha256: str,
                      obligation_id: str, required_routes: list[str], obligations: list[dict[str, object]],
                      candidates: list[dict[str, object]]) -> dict[str, object]:
    stable_candidates = [{key: value for key, value in candidate.items() if key != "observations"}
                         for candidate in candidates]
    return {"identity": identity, "question": question, "question_sha256": question_sha256,
            "obligation_id": obligation_id, "required_routes": required_routes,
            "obligations": obligations, "candidates": stable_candidates}


def _build_prepared_selection(repo: str, db: str, question_raw: bytes, question: str,
                              obligations_file: str, controller: str,
                              limit: int = DEFAULT_LIMIT) -> tuple[dict[str, object], list[dict[str, object]]]:
    if not question.strip() or not controller.strip():
        raise CoordinatorError("question and exact controller type identity must be nonempty")
    normalized, obligation_id, obligations_source = _obligations(Path(obligations_file), question)
    identity, candidates, _live = _candidate_set(repo, db, controller, limit)
    identity.update({"obligations_file_path": obligations_source["path"],
                     "obligations_file_sha256": obligations_source["sha256"]})
    packet_candidates = [{key: value for key, value in candidate.items() if key != "observations"}
                         for candidate in candidates]
    route_names = {_route_key(candidate["route"].get("route_literal")): candidate for candidate in candidates}
    missing_required = sorted(set(normalized["required_routes"]) - route_names.keys())
    if missing_required:
        raise CoordinatorError(f"frozen required routes are absent from exact controller membership: {missing_required}; observed members={sorted(route_names)}")
    obligation_items = normalized["obligations"]
    packet = {
        "selection_schema_version": SCHEMA_VERSION,
        "packet_type": "controller_map_selection",
        "question": question,
        "question_sha256": hashlib.sha256(question_raw).hexdigest(),
        "obligation_id": obligation_id,
        "required_routes": normalized["required_routes"],
        "obligations": obligation_items,
        "identity": identity,
        "candidates": packet_candidates,
        "selection_contract": _selection_contract(packet_candidates, obligation_items, normalized["required_routes"]),
    }
    semantic_hash = _digest(_semantic_payload(identity, question, packet["question_sha256"], obligation_id,
                                              normalized["required_routes"], obligation_items, packet_candidates))
    packet["semantic_sha256"] = semantic_hash
    packet["packet_sha256"] = _digest(packet)
    return packet, candidates


def prepare(repo: str, db: str, question_file: str, obligations_file: str, controller: str, run_dir: str,
            limit: int = DEFAULT_LIMIT) -> dict[str, object]:
    try:
        question_raw = Path(question_file).read_bytes()
        question = question_raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise CoordinatorError(f"question file must be readable UTF-8: {exc}") from exc
    packet, candidates = _build_prepared_selection(repo, db, question_raw, question, obligations_file, controller, limit)
    semantic_hash = packet["semantic_sha256"]
    run = Path(run_dir).expanduser()
    if run.exists() and (run.is_symlink() or not run.is_dir()):
        raise CoordinatorError("run path must be a real directory")
    run.mkdir(parents=True, exist_ok=True)
    _save_immutable(run / "selection-packet.json", packet)
    observations_path = run / "candidate-observations.json"
    observed = _candidate_observations(candidates, packet["packet_sha256"])
    if observations_path.exists():
        saved_observations = _validate_candidate_observations(_read_artifact(run, "candidate-observations.json"), packet)
        current_observations = _validate_candidate_observations(observed, packet)
        if _bytes(_observation_projection(saved_observations)) != _bytes(_observation_projection(current_observations)):
            raise CoordinatorError(f"immutable candidate observations differ from this prepare attempt; observed {saved_observations.get('observations_sha256')}, required {observed['observations_sha256']}; use a fresh run directory")
    else:
        _save_immutable(observations_path, observed)
    return {"result": "prepared", "run_dir": os.fspath(run.resolve()), "packet_sha256": packet["packet_sha256"],
            "semantic_sha256": semantic_hash, "candidate_count": len(candidates), "obligation_id": packet["obligation_id"]}


def _revalidate(run: Path, repo: str, db: str, obligations_file: str,
                expansion_run_dir: str | None = None) -> dict[str, object]:
    packet = _read_artifact(run, "selection-packet.json")
    expanded = "expansion_binding_lineage" in packet or "supplemental_evidence" in packet
    if expanded:
        if expansion_run_dir is None:
            raise CoordinatorError("expanded run requires --expansion-run-dir bound to the exact path recorded at import preparation")
        return _revalidate_expanded_selection(run, repo, db, obligations_file, expansion_run_dir, packet)
    if expansion_run_dir is not None:
        raise CoordinatorError("--expansion-run-dir is only valid for an expansion-aware selection packet")
    if packet.get("packet_sha256") != _digest({key: value for key, value in packet.items() if key != "packet_sha256"}):
        raise CoordinatorError("selection packet packet_sha256 does not match its canonical content")
    saved_observations = _validate_candidate_observations(_read_artifact(run, "candidate-observations.json"), packet)
    identity = packet.get("identity")
    if not isinstance(identity, dict):
        raise CoordinatorError("selection packet identity is malformed")
    try:
        source_path = Path(obligations_file).expanduser().resolve(strict=True)
    except OSError as exc:
        raise CoordinatorError(f"original obligations observed path={obligations_file!r}, error={exc}; required pass the same existing canonical obligations file used at prepare") from exc
    observed_path = os.fspath(source_path)
    if observed_path != identity.get("obligations_file_path"):
        raise CoordinatorError(f"original obligations path observed {observed_path!r}; required canonical path {identity.get('obligations_file_path')!r}")
    obligations, obligation_id, source_identity = _obligations(source_path, str(packet.get("question", "")))
    if source_identity["sha256"] != identity.get("obligations_file_sha256"):
        raise CoordinatorError(f"original obligations file SHA-256 observed {source_identity['sha256']}; required frozen {identity.get('obligations_file_sha256')}; restore the exact original file or prepare a fresh run")
    if packet.get("question_sha256") != hashlib.sha256(str(packet.get("question", "")).encode("utf-8")).hexdigest():
        raise CoordinatorError(f"selection packet question observed={packet.get('question')!r}, question_sha256={packet.get('question_sha256')!r}; required SHA-256 of that exact UTF-8 text; restore original packet or prepare a fresh run")
    if (packet.get("obligation_id") != obligation_id or packet.get("required_routes") != obligations["required_routes"]
            or packet.get("obligations") != obligations["obligations"]):
        raise CoordinatorError(f"selection packet authority observed obligation_id={packet.get('obligation_id')!r}, required_routes={packet.get('required_routes')!r}, obligations={packet.get('obligations')!r}; original file requires obligation_id={obligation_id!r}, required_routes={obligations['required_routes']!r}, obligations={obligations['obligations']!r}; restore original packet/file or prepare a fresh run")
    current_identity, candidates, _live = _candidate_set(repo, db, str(identity.get("controller_type_id")), DEFAULT_LIMIT)
    current_identity.update({"obligations_file_path": source_identity["path"], "obligations_file_sha256": source_identity["sha256"]})
    current_observations = _candidate_observations(candidates, str(packet["packet_sha256"]))
    _validate_candidate_observations(current_observations, packet)
    if _bytes(_observation_projection(saved_observations)) != _bytes(_observation_projection(current_observations)):
        old_by_id = {item.get("route_fact_id"): item for item in saved_observations["observations"]}
        new_by_id = {item.get("route_fact_id"): item for item in current_observations["observations"]}
        changed = [route_id for route_id in dict.fromkeys([*old_by_id, *new_by_id])
                   if old_by_id.get(route_id) != new_by_id.get(route_id)]
        details = [f"{route_id!r}: observed {old_by_id.get(route_id)!r}; current {new_by_id.get(route_id)!r}; rerun prepare in a fresh directory" for route_id in changed]
        raise CoordinatorError("candidate freshness/budget observations changed since prepare; " + "; ".join(details))
    saved_payload = _semantic_payload(identity, str(packet["question"]), str(packet["question_sha256"]),
                                      str(packet["obligation_id"]), packet["required_routes"], packet["obligations"], packet["candidates"])
    saved_semantic_hash = _digest(saved_payload)
    if packet.get("semantic_sha256") != saved_semantic_hash:
        raise CoordinatorError(f"selection packet semantic_sha256 observed {packet.get('semantic_sha256')!r}; required from its stable payload {saved_semantic_hash}")
    current_packet_candidates = [{key: value for key, value in candidate.items() if key != "observations"}
                                 for candidate in candidates]
    current_payload = _semantic_payload(current_identity, str(packet["question"]), str(packet["question_sha256"]),
                                        obligation_id, obligations["required_routes"], obligations["obligations"],
                                        current_packet_candidates)
    if _bytes(saved_payload) != _bytes(current_payload):
        current_semantic_hash = _digest(current_payload)
        raise CoordinatorError(f"prepared stable payload differs from independently reconstructed current checkout/maps/question/obligations; observed current semantic_sha256={current_semantic_hash}, required packet payload sha256={saved_semantic_hash}")
    if packet.get("selection_contract") != _selection_contract(packet["candidates"], packet["obligations"], packet["required_routes"]):
        raise CoordinatorError("selection packet contract differs from the authoritative selection record schema")
    if (run / "selection.json").exists():
        saved_selection = _read_artifact(run, "selection.json")
        record = saved_selection.get("selection_record")
        if not isinstance(record, dict):
            raise CoordinatorError("saved selection record is malformed")
        checked = _validate_selection(packet, record)
        if saved_selection.get("obligation_status") != checked["obligations"]:
            raise CoordinatorError("saved obligation coverage differs from the exact independent selection record")
        chosen = {candidate["route"]["id"]: candidate for candidate in checked["accepted"]}
        expected_selection = {"schema_version": 1, "selection_packet_sha256": packet["packet_sha256"],
                              "selection_record": record,
                              "selected_candidates": [
                                  {"route_fact_id": route_id, "overlay_id": chosen[route_id]["provenance"]["overlay_id"],
                                   "binding_hash": chosen[route_id]["provenance"]["binding_hash"],
                                   "association_review_hash": chosen[route_id]["provenance"]["association_review_hash"],
                                   "review_receipt_hash": chosen[route_id]["provenance"]["flow_review_receipt"]["receipt_hash"]}
                                  for route_id in sorted(chosen)],
                              "obligation_status": checked["obligations"]}
        if _bytes(saved_selection) != _bytes(expected_selection):
            raise CoordinatorError("saved selected-map provenance differs from the validated independent selection")
        if (run / "answer-packet.json").exists():
            answer_packet = _read_artifact(run, "answer-packet.json")
            selected_union = _selected_union(packet, checked["accepted"])
            expected = {"answer_schema_version": 1, "packet_type": "multi_map_answer", "question": packet["question"],
                        "question_sha256": packet["question_sha256"], "controller_type_id": packet["identity"]["controller_type_id"],
                        "obligation_id": packet["obligation_id"], "snapshot_id": packet["identity"]["snapshot_id"],
                        "extractor_identity": packet["identity"]["extractor_identity"], "selection": expected_selection,
                        "required_routes": packet["required_routes"], "obligations": packet["obligations"], **selected_union}
            expected["answer_contract"] = _answer_contract(expected)
            expected["semantic_sha256"] = _digest({k: v for k, v in expected.items() if k != "semantic_sha256"})
            if _bytes(expected) != _bytes(answer_packet):
                raise CoordinatorError("selected union packet is tampered or no longer reconstructs from current accepted maps")
        review_packet_path = run / "review.json"
        answer_review_path = run / "answer-review-packet.json"
        if review_packet_path.exists() or answer_review_path.exists():
            review_packet = _read_artifact(run, "answer-review-packet.json" if answer_review_path.exists() else "review.json")
            if review_packet.get("packet_sha256") != _digest({k: v for k, v in review_packet.items() if k != "packet_sha256"}):
                raise CoordinatorError("round-zero answer review packet hash is invalid")
            if review_packet.get("review_contract") != _review_schema_contract(review_packet["obligations"]):
                raise CoordinatorError("review packet contract differs from the authoritative review record schema")
            answer_packet = _read_artifact(run, "answer-packet.json")
            answer_value = review_packet.get("answer")
            if not isinstance(answer_value, dict) or not isinstance(answer_value.get("answer"), str):
                raise CoordinatorError("round-zero review packet does not preserve a structured answer")
            draft_raw = answer_value["answer"].encode("utf-8")
            _validate_answer(answer_packet, draft_raw, answer_value)
            rebuilt_review = _make_answer_review_packet(answer_packet, answer_value, draft_raw, 0)
            if _bytes(rebuilt_review) != _bytes(review_packet):
                raise CoordinatorError("round-zero review packet does not reconstruct from the exact answer and selected union")
            if review_packet_path.exists() and answer_review_path.exists() and _bytes(_read_artifact(run, "review.json")) != _bytes(review_packet):
                raise CoordinatorError("round-zero review packet copies differ")
        if (run / "review-result.json").exists():
            review_packet = _read_artifact(run, "answer-review-packet.json")
            review_record = _read_artifact(run, "review-result.json")
            _validate_review(review_packet, review_record, saved_selection)
        if (run / "correction-packet.json").exists():
            correction = _read_artifact(run, "correction-packet.json")
            if correction.get("packet_sha256") != _digest({k: v for k, v in correction.items() if k != "packet_sha256"}):
                raise CoordinatorError("correction packet hash is invalid")
            original = _read_artifact(run, "answer-packet.json")
            rejected = _read_artifact(run, "review-result.json")
            original_review_packet = _read_artifact(run, "answer-review-packet.json")
            if (rejected.get("decision") != "rejected" or rejected.get("failure_kind") != "answer_gap"
                    or correction.get("rejected_review_sha256") != _digest(rejected)
                    or correction.get("original_packet_sha256") != original.get("semantic_sha256")
                    or correction.get("semantic_sha256") != original.get("semantic_sha256")
                    or correction.get("question_sha256") != original.get("question_sha256")
                    or correction.get("required_routes") != original.get("required_routes")
                    or correction.get("obligation_id") != original.get("obligation_id")
                    or correction.get("correction_round") != 1 or correction.get("max_corrections") != 1
                    or correction.get("question") != original_review_packet.get("question")
                    or correction.get("obligations") != original_review_packet.get("obligations")
                    or correction.get("claims") != original_review_packet.get("claims")
                    or correction.get("source_anchors") != original_review_packet.get("source_anchors")
                    or correction.get("source_snippets") != original_review_packet.get("source_snippets")):
                raise CoordinatorError("correction packet does not preserve the exact rejected round-zero evidence and review")
            expected_correction = {"schema_version": 1, "packet_type": "multi_map_correction", "result": "correction_required",
                                   "original_packet_sha256": original["semantic_sha256"], "semantic_sha256": original["semantic_sha256"],
                                   "question_sha256": original["question_sha256"], "obligation_id": original["obligation_id"],
                                   "rejected_review_sha256": _digest(rejected), "correction_round": 1, "max_corrections": 1,
                                   "question": original_review_packet["question"], "required_routes": original_review_packet["required_routes"],
                                   "obligations": original_review_packet["obligations"],
                                   "claims": original_review_packet["claims"], "source_anchors": original_review_packet["source_anchors"],
                                   "source_snippets": original_review_packet["source_snippets"],
                                   "rejection_reasons": {"claim_reviews": rejected["claim_reviews"],
                                                         "obligation_reviews": rejected["obligation_reviews"],
                                                         "unsupported_assertions": rejected["unsupported_assertions"]}}
            expected_correction["packet_sha256"] = _digest(expected_correction)
            if _bytes(expected_correction) != _bytes(correction):
                raise CoordinatorError("correction packet does not reconstruct from the exact round-zero rejection")
        if (run / "corrected-answer-packet.json").exists():
            correction = _read_artifact(run, "correction-packet.json")
            corrected = _read_artifact(run, "corrected-answer-packet.json")
            if corrected.get("packet_sha256") != _digest({k: v for k, v in corrected.items() if k != "packet_sha256"}):
                raise CoordinatorError("corrected answer review packet hash is invalid")
            answer = corrected.get("answer")
            if not isinstance(answer, dict):
                raise CoordinatorError("corrected answer packet has no structured answer")
            if corrected.get("review_contract") != _review_schema_contract(corrected["obligations"]):
                raise CoordinatorError("corrected review packet contract differs from the authoritative review record schema")
            _validate_answer(correction, str(answer.get("answer", "")).encode("utf-8"), answer)
            rebuilt = _make_answer_review_packet(correction, answer, answer["answer"].encode("utf-8"), 1)
            if _bytes(rebuilt) != _bytes(corrected):
                raise CoordinatorError("corrected answer packet does not reconstruct from its correction lineage")
        if (run / "corrected-review.json").exists():
            corrected = _read_artifact(run, "corrected-answer-packet.json")
            first_review = _read_artifact(run, "review-result.json")
            _validate_review(corrected, _read_artifact(run, "corrected-review.json"), saved_selection,
                             previous_reviewer_identity=str(first_review.get("reviewer_identity", "")))
    if (run / "evidence-gap.json").exists():
        gap = _read_artifact(run, "evidence-gap.json")
        if gap.get("package_sha256") != _digest({k: v for k, v in gap.items() if k != "package_sha256"}) or gap.get("completeness_claim") is not False:
            raise CoordinatorError("evidence-gap package hash or no-completeness assertion is invalid")
        if (run / "answer-packet.json").exists():
            answer_packet = _read_artifact(run, "answer-packet.json")
            review_packet = _read_artifact(run, "answer-review-packet.json")
            review_record = _read_artifact(run, "review-result.json")
            if review_record.get("failure_kind") != "evidence_gap":
                raise CoordinatorError("answer-derived evidence gap lacks an evidence_gap Sol review")
            expected_gap = {"schema_version": 1, "result": "evidence_gap", "question": answer_packet["question"],
                            "packet_sha256": answer_packet["semantic_sha256"], "review": review_record,
                            "required_routes": answer_packet["required_routes"], "obligations": answer_packet["obligations"],
                            "selection_record": answer_packet["selection"]["selection_record"],
                            "selected_route_fact_ids": [item["route_fact_id"] for item in answer_packet["selection"]["selected_candidates"]],
                            "supported_partial_coverage": {"claims": answer_packet["claims"], "source_anchors": answer_packet["source_anchors"],
                                                            "source_snippets": answer_packet["source_snippets"]},
                            "completeness_claim": False}
        else:
            selection_record = gap.get("selection_record")
            if not isinstance(selection_record, dict):
                raise CoordinatorError("selection-derived evidence gap does not preserve its independent selection record")
            checked = _validate_selection(packet, selection_record)
            if not any(value == "absent_from_candidates" for value in checked["obligations"].values()):
                raise CoordinatorError("selection-derived evidence gap has no frozen absent obligation")
            partial = _selected_union(packet, checked["accepted"])
            expected_gap = {"schema_version": 1, "result": "evidence_gap", "question": packet["question"],
                            "packet_sha256": packet["packet_sha256"], "semantic_sha256": packet["semantic_sha256"],
                            "required_routes": packet["required_routes"], "obligations": packet["obligations"],
                            "supported_partial_coverage": partial,
                            "absent_obligations": [item for item in selection_record["obligation_reviews"]
                                                   if item["candidate_status"] == "absent_from_candidates"],
                            "selection_record": selection_record,
                            "selected_route_fact_ids": sorted(candidate["route"]["id"] for candidate in checked["accepted"]),
                            "completeness_claim": False,
                            "reviewer": {"identity": selection_record["reviewer_identity"], "model": selection_record["reviewer_model"]}}
        expected_gap["package_sha256"] = _digest(expected_gap)
        if _bytes(expected_gap) != _bytes(gap):
            raise CoordinatorError("evidence-gap artifact does not reconstruct from its exact candidate set, selection, and review")
    if (run / "accepted-package.json").exists():
        accepted = _read_artifact(run, "accepted-package.json")
        if accepted.get("package_sha256") != _digest({k: v for k, v in accepted.items() if k != "package_sha256"}):
            raise CoordinatorError("accepted package hash does not match canonical content")
        corrected_terminal = (run / "corrected-review.json").exists()
        review_packet = _read_artifact(run, "corrected-answer-packet.json" if corrected_terminal else "answer-review-packet.json")
        review_record = _read_artifact(run, "corrected-review.json" if corrected_terminal else "review-result.json")
        _validate_review(review_packet, review_record, _read_artifact(run, "selection.json"))
        if review_record.get("decision") != "accepted":
            raise CoordinatorError("accepted package is not backed by an accepted fresh review")
        expected_package = _accepted_package(run, _read_artifact(run, "answer-packet.json"), review_packet, review_record, corrected_terminal)
        if _bytes(expected_package) != _bytes(accepted):
            raise CoordinatorError("accepted package does not reconstruct from the exact answer and accepted review")
    return packet


def _canonical_run_path(path: Path, label: str, *, must_exist: bool) -> Path:
    expanded = path.expanduser()
    if expanded.is_symlink() or (expanded.exists() and not expanded.is_dir()):
        raise CoordinatorError(f"{label} must be a real directory: {expanded}")
    try:
        return expanded.resolve(strict=must_exist)
    except OSError as exc:
        raise CoordinatorError(f"cannot resolve {label} {expanded}: {exc}") from exc


def _type_boundaries(graph: dict[str, object], path: str, text: str) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    tokens, directives = csharp_facts.lex(text)
    pairs: dict[int, int] = {}
    stack: list[int] = []
    for index, token in enumerate(tokens):
        if token.value == "{":
            stack.append(index)
        elif token.value == "}" and stack:
            pairs[stack.pop()] = index
    boundaries: list[dict[str, object]] = []
    facts = graph.get("facts")
    if not isinstance(facts, list):
        raise CoordinatorError("current source graph facts are unavailable for lexical owner reconstruction")
    for fact in facts:
        if not isinstance(fact, dict) or fact.get("kind") != "type_declaration":
            continue
        source = fact.get("source")
        span = source.get("span") if isinstance(source, dict) else None
        if not isinstance(source, dict) or source.get("path") != path or not isinstance(span, dict):
            continue
        start = span.get("start_offset")
        if not isinstance(start, int):
            continue
        keyword = next((i for i, token in enumerate(tokens) if token.start == start), None)
        if keyword is None:
            continue
        opening = next((i for i in range(keyword, len(tokens)) if tokens[i].value in {"{", ";"}), None)
        if opening is None or tokens[opening].value != "{" or opening not in pairs:
            continue
        boundaries.append({"fact": fact, "open": opening, "close": pairs[opening],
                           "start_offset": tokens[opening].start, "end_offset": tokens[pairs[opening]].end})
    conditional_ranges: list[tuple[int, int]] = []
    conditional_stack: list[int] = []
    for directive in directives:
        command = directive.value.lstrip()[1:].strip().split(None, 1)[0] if directive.value.lstrip().startswith("#") else ""
        if command in {"if", "elif", "else"}:
            if command == "if":
                conditional_stack.append(directive.start)
        elif command == "endif" and conditional_stack:
            conditional_ranges.append((conditional_stack.pop(), directive.end))
    for start in conditional_stack:
        conditional_ranges.append((start, len(text)))
    return boundaries, [{"start": start, "end": end} for start, end in sorted(conditional_ranges)]


def _lexical_owner_at(boundaries: list[dict[str, object]], offset: int) -> tuple[dict[str, object] | None, str | None]:
    containing = [item for item in boundaries if item["start_offset"] <= offset <= item["end_offset"]]
    if not containing:
        return None, "lexical_owner_missing"
    smallest = min(int(item["end_offset"]) - int(item["start_offset"]) for item in containing)
    owners = [item for item in containing if int(item["end_offset"]) - int(item["start_offset"]) == smallest]
    if len(owners) != 1 or not isinstance(owners[0].get("fact"), dict) or not owners[0]["fact"].get("id"):
        return None, "ambiguous_lexical_owner"
    return owners[0], None


def _member_constant_candidates(graph: dict[str, object], files: dict[str, tuple[str, str]], identifiers: set[str]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    found: list[dict[str, object]] = []
    exclusions: list[dict[str, object]] = []
    for path in sorted(files, key=lambda value: value.encode("utf-8")):
        text, source_hash = files[path]
        boundaries, conditional_ranges = _type_boundaries(graph, path, text)
        tokens, _ = csharp_facts.lex(text)
        for ti, token in enumerate(tokens):
            if token.value != "const":
                continue
            owner, owner_error = _lexical_owner_at(boundaries, token.start)
            if owner is None or not (owner["open"] < ti < owner["close"]):
                lookahead = tokens[ti:min(len(tokens), ti + 16)]
                seeded = sorted({item.value.lstrip("@") for item in lookahead if item.kind == "identifier" and item.value.lstrip("@") in identifiers})
                exclusions.extend({"path": path, "reason": owner_error or "constant_owner_boundary_unresolved", "identifier": name,
                                   "start_offset": token.start, "incomplete": True} for name in seeded)
                continue
            # Only visit member-scope declarations. Angle brackets are deliberately
            # absent here: comparisons and shifts in initializers have no delimiter role.
            curly = paren = bracket = 0
            for prior in range(owner["open"] + 1, ti):
                value = tokens[prior].value
                if value == "{": curly += 1
                elif value == "}": curly -= 1
                elif value == "(": paren += 1
                elif value == ")": paren -= 1
                elif value == "[": bracket += 1
                elif value == "]": bracket -= 1
            if curly != 0 or paren != 0 or bracket != 0:
                continue
            end_i = ti
            stack: list[str] = []
            malformed = False
            while end_i < owner["close"]:
                value = tokens[end_i].value
                if end_i > ti and not stack and value in {"const", "public", "private", "protected", "internal", "static"}:
                    malformed = True
                    break
                if (end_i > ti and not stack and tokens[end_i].line > tokens[end_i - 1].line
                        and tokens[end_i].kind == "identifier" and end_i + 1 < owner["close"]
                        and tokens[end_i + 1].kind == "identifier"
                        and tokens[end_i + 2].value in {"(", "{", "=", ";"}):
                    malformed = True
                    break
                if value in {"(", "[", "{"}: stack.append(value)
                elif value in {")", "]", "}"}:
                    expected = {")": "(", "]": "[", "}": "{"}[value]
                    if not stack or stack[-1] != expected:
                        malformed = True
                        break
                    stack.pop()
                if value == ";" and not stack:
                    break
                end_i += 1
            if malformed or end_i >= owner["close"] or tokens[end_i].value != ";" or stack:
                end_bound = min(end_i, int(owner["close"]))
                seeded = sorted({item.value.lstrip("@") for item in tokens[ti + 1:end_bound]
                                 if item.kind == "identifier" and item.value.lstrip("@") in identifiers})
                exclusions.extend({"path": path, "reason": "constant_statement_unterminated_or_unbalanced", "identifier": name,
                                   "start_offset": token.start, "incomplete": True} for name in seeded)
                continue
            # Find the first top-level initializer before splitting comma-separated
            # declarators. This keeps commas in a generic type prefix out of the split.
            first_eq = None
            stack = []
            for idx in range(ti + 1, end_i):
                value = tokens[idx].value
                if value in {"(", "[", "{"}: stack.append(value)
                elif value in {")", "]", "}"}:
                    expected = {")": "(", "]": "[", "}": "{"}[value]
                    if not stack or stack[-1] != expected: malformed = True; break
                    stack.pop()
                elif value == "=" and not stack:
                    first_eq = idx
                    break
            if malformed or first_eq is None:
                seeded = sorted({item.value.lstrip("@") for item in tokens[ti + 1:end_i]
                                 if item.kind == "identifier" and item.value.lstrip("@") in identifiers})
                exclusions.extend({"path": path, "reason": "constant_declarator_unclassifiable", "identifier": name,
                                   "start_offset": token.start, "incomplete": True} for name in seeded)
                continue
            first_name_i = first_eq - 1
            while first_name_i > ti and tokens[first_name_i].kind != "identifier": first_name_i -= 1
            type_prefix = tokens[ti + 1:first_name_i]
            # Parse the type prefix independently from initializer tokenization. The
            # narrow accepted form is one identifier; other balanced prefixes remain
            # visible as unsupported candidates rather than hiding later declarators.
            type_prefix_classified = bool(type_prefix) and type_prefix[0].kind == "identifier"
            angle_depth = 0
            for type_token in type_prefix:
                if type_token.value == "<": angle_depth += 1
                elif type_token.value == ">":
                    angle_depth -= 1
                    if angle_depth < 0: type_prefix_classified = False
                elif not (type_token.kind == "identifier" or type_token.value in {".", "::", ",", "<", ">", "[", "]", "?"}):
                    type_prefix_classified = False
            type_prefix_classified = type_prefix_classified and angle_depth == 0
            type_supported = len(type_prefix) == 1 and type_prefix[0].kind == "identifier"
            type_name = text[type_prefix[0].start:type_prefix[-1].end] if type_prefix else None
            parts: list[tuple[int, int, int, int | None]] = []
            part_start = first_eq + 1
            first_value_end = end_i
            stack = []
            for idx in range(first_eq + 1, end_i):
                value = tokens[idx].value
                if value in {"(", "[", "{"}: stack.append(value)
                elif value in {")", "]", "}"}:
                    expected = {")": "(", "]": "[", "}": "{"}[value]
                    if not stack or stack[-1] != expected: malformed = True; break
                    stack.pop()
                elif value == "," and not stack:
                    first_value_end = idx
                    break
            parts.append((first_name_i, first_eq, first_eq + 1, first_value_end))
            if first_value_end < end_i:
                part_start = first_value_end + 1
                stack = []
                for idx in range(part_start, end_i):
                    value = tokens[idx].value
                    if value in {"(", "[", "{"}: stack.append(value)
                    elif value in {")", "]", "}"}:
                        expected = {")": "(", "]": "[", "}": "{"}[value]
                        if not stack or stack[-1] != expected: malformed = True; break
                        stack.pop()
                    elif value == "," and not stack:
                        # The segment is one declarator; its initializer is literal-only
                        # in the supported grammar, so later top-level commas delimit it.
                        eq_part = next((j for j in range(part_start, idx) if tokens[j].value == "="), None)
                        parts.append((part_start, eq_part if eq_part is not None else idx,
                                      eq_part + 1 if eq_part is not None else idx, idx))
                        part_start = idx + 1
                if not malformed and part_start < end_i:
                    eq_part = next((j for j in range(part_start, end_i) if tokens[j].value == "="), None)
                    parts.append((part_start, eq_part if eq_part is not None else end_i,
                                  eq_part + 1 if eq_part is not None else end_i, end_i))
            if malformed or stack:
                seeded = sorted({item.value.lstrip("@") for item in tokens[ti + 1:end_i]
                                 if item.kind == "identifier" and item.value.lstrip("@") in identifiers})
                exclusions.extend({"path": path, "reason": "constant_declarator_unclassifiable", "identifier": name,
                                   "start_offset": token.start, "incomplete": True} for name in seeded)
                continue
            decl_start_i = ti
            modifiers = {"public", "protected", "internal", "private", "static", "new", "unsafe", "extern"}
            while decl_start_i > 0 and tokens[decl_start_i - 1].value in modifiers:
                decl_start_i -= 1
            statement_span = {"start_offset": tokens[decl_start_i].start, "end_offset": tokens[end_i].end,
                "start_line": tokens[decl_start_i].line, "start_column": tokens[decl_start_i].column,
                "end_line": tokens[end_i].end_line, "end_column": tokens[end_i].end_column,
                "offset_unit": "unicode_codepoint"}
            is_conditional = any(item["start"] <= token.start < item["end"] for item in conditional_ranges)
            for part_index, (name_i, eq_i, value_start, part_end) in enumerate(parts):
                if name_i is None or name_i >= part_end or tokens[name_i].kind != "identifier":
                    seeded_names = sorted({item.value.lstrip("@") for item in tokens[part_start:part_end]
                                           if item.kind == "identifier" and item.value.lstrip("@") in identifiers})
                    exclusions.extend({"path": path, "reason": "unsupported_constant_declarator_syntax", "identifier": name,
                                       "start_offset": tokens[part_start].start if part_start < part_end else token.start,
                                       "incomplete": True} for name in seeded_names)
                    continue
                name = tokens[name_i].value.lstrip("@")
                if name not in identifiers:
                    continue
                if not type_prefix_classified:
                    exclusions.append({"path": path, "reason": "constant_type_prefix_unclassifiable", "identifier": name,
                                       "start_offset": tokens[name_i].start, "incomplete": True})
                    continue
                if eq_i is None:
                    exclusions.append({"path": path, "reason": "constant_initializer_missing", "identifier": name,
                                       "start_offset": tokens[name_i].start, "incomplete": True})
                    continue
                value_tokens = tokens[value_start:part_end]
                initializer_supported = ((len(value_tokens) == 1 and value_tokens[0].kind in {"number", "string", "raw_literal", "char"})
                    or (len(value_tokens) == 2 and value_tokens[0].value in {"+", "-"} and value_tokens[1].kind == "number")
                    or (len(value_tokens) == 1 and value_tokens[0].value in {"true", "false", "null"}))
                parsed = type_supported and initializer_supported
                literal = text[value_tokens[0].start:value_tokens[-1].end] if initializer_supported else None
                name_span = {"start_offset": tokens[name_i].start, "end_offset": tokens[name_i].end,
                             "offset_unit": "unicode_codepoint"}
                initializer_span = ({"start_offset": value_tokens[0].start, "end_offset": value_tokens[-1].end,
                                     "offset_unit": "unicode_codepoint"} if value_tokens else None)
                owner_fact = owner.get("fact") if owner else None
                owner_id = owner_fact.get("id") if isinstance(owner_fact, dict) else None
                owner_name = owner_fact.get("type_id") if isinstance(owner_fact, dict) else None
                reasons: list[str] = []
                if owner_error: reasons.append(owner_error)
                if is_conditional: reasons.append("conditional_directive")
                if not parsed: reasons.append("unsupported_constant_syntax")
                candidate = {"identifier": name, "path": path, "sha256": source_hash,
                    "span": statement_span, "name_span": name_span, "initializer_span": initializer_span,
                    "source_anchor": {"path": path, "sha256": source_hash},
                    "snippet": text[statement_span["start_offset"]:statement_span["end_offset"]],
                    "source_snippet": {"span": statement_span, "text": text[statement_span["start_offset"]:statement_span["end_offset"]]},
                    "owner_type_id": owner_name, "owner_fact_id": owner_id, "constant_type": type_name,
                    "type_prefix_classified": type_prefix_classified,
                    "literal": literal, "syntax_supported": bool(parsed), "conditional": is_conditional,
                    "eligible_use_ids": [], "reasons": reasons}
                candidate["candidate_id"] = "candidate-" + _digest({key: value for key, value in candidate.items() if key != "candidate_id"})[:24]
                found.append(candidate)
    return found, exclusions


def _method_identifier_safety(text: str, tokens: list[object], use_start: int, use_end: int, identifier: str) -> tuple[bool, str | None]:
    """Conservative lexical screen; this records syntax evidence, never compiler binding."""
    pairs: dict[int, int] = {}
    stack: list[int] = []
    for index, token in enumerate(tokens):
        if token.value == "{": stack.append(index)
        elif token.value == "}" and stack: pairs[stack.pop()] = index
    use_i = next((i for i, token in enumerate(tokens) if token.start == use_start and token.end == use_end), None)
    if use_i is None:
        return False, "origin_use_token_not_found"
    bodies = [(opening, closing) for opening, closing in pairs.items() if tokens[opening].start < use_start < tokens[closing].end]
    if not bodies:
        return False, "containing_method_scope_unresolved"
    controls = {"if", "for", "foreach", "while", "switch", "catch", "using", "lock", "fixed"}
    method_bodies = []
    for opening, closing in bodies:
        if opening == 0 or tokens[opening - 1].value != ")":
            continue
        depth = 0
        left_paren = None
        for idx in range(opening - 1, -1, -1):
            if tokens[idx].value == ")": depth += 1
            elif tokens[idx].value == "(":
                depth -= 1
                if depth == 0:
                    left_paren = idx
                    break
        if left_paren is not None and left_paren > 0 and tokens[left_paren - 1].value not in controls:
            method_bodies.append((opening, closing, left_paren))
    if not method_bodies:
        return False, "containing_method_scope_unresolved"
    # The direct method body is the widest method-shaped brace enclosing the use;
    # nested local functions/lambdas are scanned as part of its conservative scope.
    opening, closing, left_paren = max(method_bodies, key=lambda item: tokens[item[1]].end - tokens[item[0]].start)
    # Any other same-name token in the method can be a declaration or a binding-relevant
    # occurrence in a nested scope. Without a compiler, refuse to claim it cannot shadow.
    occurrences = [i for i, token in enumerate(tokens) if token.kind == "identifier"
                   and token.value.lstrip("@") == identifier and i != use_i
                   and ((left_paren < i < opening) or (opening < i < closing))]
    if occurrences:
        known_type_words = {"var", "const", "bool", "byte", "char", "decimal", "double", "float", "int", "long",
            "object", "sbyte", "short", "string", "uint", "ulong", "ushort", "out", "is", "case", "foreach", "catch"}
        for i in occurrences:
            prior = tokens[i - 1].value if i else ""
            following = tokens[i + 1].value if i + 1 < len(tokens) else ""
            if prior in known_type_words or following in {"=>", ",", ")", "}"} or prior in {"out", "var"}:
                return False, "shadowed_identifier_in_lexical_owner"
        return False, "identifier_binding_context_unclassified"
    return True, None


def _owner_has_same_name_member(graph: dict[str, object], path: str, text: str,
                                candidate: dict[str, object], use: dict[str, object]) -> bool:
    tokens, _ = csharp_facts.lex(text)
    boundaries, _ = _type_boundaries(graph, path, text)
    owner = next((item for item in boundaries if item["fact"].get("id") == use.get("owner_fact_id")), None)
    if owner is None: return False
    name_span = candidate.get("name_span", {})
    candidate_offset = name_span.get("start_offset") if isinstance(name_span, dict) else None
    use_span = use.get("identifier_use_span", {})
    use_offset = use_span.get("start_offset") if isinstance(use_span, dict) else None
    for i, token in enumerate(tokens):
        if token.value.lstrip("@") != candidate.get("identifier") or token.start in {candidate_offset, use_offset}:
            continue
        if not (owner["start_offset"] < token.start < owner["end_offset"]): continue
        prior = tokens[i - 1].value if i else ""
        following = tokens[i + 1].value if i + 1 < len(tokens) else ""
        type_like = (i > 0 and (tokens[i - 1].kind == "identifier" or prior in {">", "]", "?"}))
        if type_like and following in {"=", ",", ";"}:
            return True
    return False


def _validate_expansion_max_bytes(max_bytes: object) -> int:
    if type(max_bytes) is not int or not 1 <= max_bytes <= EXPANSION_MAX_BYTES:
        raise CoordinatorError(f"--max-bytes observed {max_bytes!r}; required an exact integer in 1..{EXPANSION_MAX_BYTES}")
    return max_bytes


def _build_gap_expansion_packet(repo: str, db: str, source_run_dir: str, destination_run_dir: str,
                                obligations_file: str, max_bytes: int,
                                expansion_schema_version: int = EXPANSION_SCHEMA_VERSION) -> dict[str, object]:
    max_bytes = _validate_expansion_max_bytes(max_bytes)
    source = _canonical_run_path(Path(source_run_dir), "source run", must_exist=True)
    destination = _canonical_run_path(Path(destination_run_dir), "destination run", must_exist=False)
    if source == destination:
        raise CoordinatorError("source and destination run paths must be distinct")
    for name in EXPANSION_FORBIDDEN:
        if os.path.lexists(source / name):
            raise CoordinatorError(f"source run is not a selection-stage evidence gap; forbidden artifact exists: {name}")
    if any(path.name.startswith("expansion-") for path in source.iterdir()):
        raise CoordinatorError("source run already contains expansion lineage")
    packet = _revalidate(source, repo, db, obligations_file)
    if not (source / "evidence-gap.json").is_file():
        raise CoordinatorError("source run must contain a validated selection-stage evidence-gap terminal")
    gap = _read_artifact(source, "evidence-gap.json")
    selection_record = gap.get("selection_record")
    if not isinstance(selection_record, dict):
        raise CoordinatorError("source evidence gap does not preserve its exact selection record")
    if (gap.get("result") != "evidence_gap" or gap.get("packet_sha256") != packet.get("packet_sha256")
            or gap.get("completeness_claim") is not False
            or "review" in gap):
        raise CoordinatorError("source evidence gap is not the canonical selection-stage terminal for this packet")
    identity = packet.get("identity")
    if not isinstance(identity, dict):
        raise CoordinatorError("selection identity is malformed")
    snapshot, _snapshots, extractor, live = atlas._current_route_snapshot(Path(db).expanduser().resolve(strict=True), repo)
    if (snapshot.get("snapshot_id") != identity.get("snapshot_id") or extractor != identity.get("extractor_identity")
            or live.get("repository_root") != identity.get("repository_root") or live.get("head") != identity.get("head")
            or live.get("status") != identity.get("repository_status")):
        raise CoordinatorError("current checkout, status, snapshot, or extractor differs from the selection-stage identity")
    root = atlas._repo_root(repo)
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    files: dict[str, tuple[str, str]] = {}
    scanned_bytes = 0
    exclusions: list[dict[str, object]] = []
    try:
        inventory = snapshot.get("files")
        if not isinstance(inventory, list):
            raise CoordinatorError("current snapshot lacks its tracked-file inventory")
        for entry in inventory:
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                raise CoordinatorError("tracked-file inventory contains an invalid entry")
            path = entry["path"]
            if not path.lower().endswith(".cs"):
                continue
            if entry.get("presence") != "present" or entry.get("type") != "file" or not isinstance(entry.get("sha256"), str):
                exclusions.append({"path": path, "reason": "unsafe_or_missing_tracked_source"})
                continue
            evidence = atlas._read_working_file(root_fd, path, collect_source=True)
            raw = evidence.get("_source_bytes")
            if evidence.get("presence") != "present" or evidence.get("type") != "file" or evidence.get("sha256") != entry["sha256"] or not isinstance(raw, bytes):
                exclusions.append({"path": path, "reason": "unsafe_or_changed_source"})
                continue
            scanned_bytes += len(raw)
            if scanned_bytes > max_bytes:
                raise CoordinatorError(f"verified source scan exceeds --max-bytes: observed {scanned_bytes}, limit {max_bytes}; no packet written")
            try:
                files[path] = (raw.decode("utf-8-sig"), str(entry["sha256"]))
            except UnicodeDecodeError:
                exclusions.append({"path": path, "reason": "source_not_utf8"})
    finally:
        os.close(root_fd)
    untracked_csharp = [item for item in live.get("status", []) if isinstance(item, dict)
                        and str(item.get("path", "")).lower().endswith(".cs")
                        and (item.get("index_status") == "?" or item.get("worktree_status") == "?")]
    exclusions.extend({"path": item["path"], "reason": "untracked_source_excluded"} for item in untracked_csharp)
    absent = [item for item in packet["obligations"] if any(
        review.get("obligation_id") == item["obligation_id"] and review.get("candidate_status") == "absent_from_candidates"
        for review in selection_record.get("obligation_reviews", []))]
    selected_ids = set(gap.get("selected_route_fact_ids", []))
    by_route = {candidate["route"]["id"]: candidate for candidate in packet["candidates"]
                if candidate.get("route", {}).get("id") in selected_ids}
    origin_uses: list[dict[str, object]] = []
    seeds: set[str] = set()
    for obligation in absent:
        meaning_ids = {match.group(0).lstrip("@") for match in re.finditer(r"@?[A-Za-z_][A-Za-z0-9_]*", str(obligation["meaning"]))
                       if match.group(0).lstrip("@") not in C_SHARP_KEYWORDS}
        for route_id in sorted(by_route):
            focus = by_route[route_id].get("map", {})
            anchors = {item.get("source_id"): item for item in focus.get("source_anchors", []) if isinstance(item, dict)}
            snippets = {item.get("snippet_id"): item for item in focus.get("source_snippets", []) if isinstance(item, dict)}
            for claim_index, claim in enumerate(focus.get("claims", [])):
                if not isinstance(claim, dict): continue
                claim_ids = {match.group(0).lstrip("@") for match in re.finditer(r"@?[A-Za-z_][A-Za-z0-9_]*", str(claim.get("claim", "")))
                             if match.group(0).lstrip("@") not in C_SHARP_KEYWORDS}
                for evidence in claim.get("evidence", []):
                    if not isinstance(evidence, dict): continue
                    anchor = anchors.get(evidence.get("source_id")); snippet = snippets.get(evidence.get("snippet_id"))
                    if not isinstance(anchor, dict) or not isinstance(snippet, dict) or snippet.get("source_id") != evidence.get("source_id"):
                        continue
                    source_text = files.get(str(anchor.get("path")))
                    span = snippet.get("span")
                    if not source_text or not isinstance(span, dict) or anchor.get("sha256") != source_text[1]: continue
                    start, end = span.get("start_offset"), span.get("end_offset")
                    snippet_text = snippet.get("text")
                    if (not isinstance(start, int) or not isinstance(end, int) or not isinstance(snippet_text, str)
                            or source_text[0][start:end] != snippet_text):
                        continue
                    source_tokens, _ = csharp_facts.lex(source_text[0])
                    for source_token in csharp_facts.lex(snippet_text)[0]:
                        if source_token.kind != "identifier": continue
                        identifier = source_token.value.lstrip("@")
                        if identifier in C_SHARP_KEYWORDS or identifier not in meaning_ids or identifier not in claim_ids:
                            continue
                        absolute_start, absolute_end = start + source_token.start, start + source_token.end
                        matching = [i for i, token in enumerate(source_tokens) if token.start == absolute_start and token.end == absolute_end
                                    and token.kind == "identifier" and token.value.lstrip("@") == identifier]
                        if len(matching) != 1:
                            continue
                        use_i = matching[0]
                        qualified = use_i > 0 and source_tokens[use_i - 1].value in {".", "?.", "::"}
                        qualifier = (source_tokens[use_i - 2].value if qualified and use_i > 1 else source_tokens[use_i - 1].value if qualified else None)
                        use_owner, use_owner_error = _lexical_owner_at(_type_boundaries(snapshot["source_graph"], str(anchor["path"]), source_text[0])[0], absolute_start)
                        use_owner_fact = use_owner.get("fact") if use_owner else None
                        owner_id = use_owner_fact.get("id") if isinstance(use_owner_fact, dict) else None
                        owner_type_id = use_owner_fact.get("type_id") if isinstance(use_owner_fact, dict) else None
                        conditional_ranges = _type_boundaries(snapshot["source_graph"], str(anchor["path"]), source_text[0])[1]
                        conditional_use = any(item["start"] <= absolute_start < item["end"] for item in conditional_ranges)
                        method_safe, method_reason = _method_identifier_safety(source_text[0], source_tokens, absolute_start, absolute_end, identifier)
                        use_id = "use-" + _digest({"obligation_id": obligation["obligation_id"], "route_fact_id": route_id,
                            "claim_index": claim_index, "source_id": anchor["source_id"], "path": anchor["path"],
                            "sha256": anchor["sha256"], "span": [absolute_start, absolute_end], "identifier": identifier})[:24]
                        origin_uses.append({"use_id": use_id, "obligation_id": obligation["obligation_id"],
                            "route_fact_id": route_id, "claim_index": claim_index, "map_claim": claim["claim"],
                            "citation": {"fact_id": evidence.get("fact_id"), "source_id": anchor["source_id"],
                                         "snippet_id": snippet["snippet_id"], "span": span},
                            "source_anchor": {"path": anchor["path"], "sha256": anchor["sha256"]},
                            "identifier": identifier, "identifier_use_span": {"start_offset": absolute_start,
                                "end_offset": absolute_end, "offset_unit": "unicode_codepoint"},
                            "unqualified": not qualified, "qualification_context": {"qualified": qualified,
                                "preceding_tokens": [item.value for item in source_tokens[max(0, use_i - 2):use_i]],
                                "qualifier_token": qualifier},
                            "owner_fact_id": owner_id, "owner_type_id": owner_type_id, "owner_resolution_reason": use_owner_error,
                            "conditional": conditional_use, "method_lexical_safe": method_safe,
                            "method_lexical_reason": method_reason, "snippet": snippet_text})
                        seeds.add(identifier)
    origin_uses = list({item["use_id"]: item for item in origin_uses}.values())
    origin_uses.sort(key=lambda item: (str(item["obligation_id"]), str(item["route_fact_id"]),
                                       str(item["source_anchor"]["path"]), item["identifier_use_span"]["start_offset"], str(item["use_id"])))
    candidates, parser_exclusions = _member_constant_candidates(snapshot["source_graph"], files, seeds)
    exclusions.extend(parser_exclusions)
    for candidate in candidates:
        for use in origin_uses:
            if candidate["identifier"] != use["identifier"]:
                continue
            if candidate["path"] != use["source_anchor"]["path"]:
                continue
            if candidate.get("owner_fact_id") != use.get("owner_fact_id"):
                candidate["reasons"].append("not_same_file_and_lexical_owner_as_origin_use")
                candidate["reasons"].append("origin_and_declaration_lexical_owner_mismatch")
                continue
            if not use.get("unqualified"):
                candidate["reasons"].append("origin_use_is_qualified")
            elif use.get("conditional"):
                candidate["reasons"].append("conditional_origin_use")
            elif use.get("owner_resolution_reason"):
                candidate["reasons"].append(str(use["owner_resolution_reason"]))
            elif not use.get("owner_fact_id") or candidate.get("owner_fact_id") != use.get("owner_fact_id"):
                candidate["reasons"].append("origin_and_declaration_lexical_owner_mismatch")
            elif use.get("method_lexical_reason"):
                candidate["reasons"].append(str(use["method_lexical_reason"]))
            elif _owner_has_same_name_member(snapshot["source_graph"], candidate["path"], files[candidate["path"]][0], candidate, use):
                candidate["reasons"].append("shadowed_identifier_in_lexical_owner")
            elif candidate["syntax_supported"] and not candidate["conditional"] and not untracked_csharp and not exclusions:
                candidate["eligible_use_ids"].append(use["use_id"])
            else:
                candidate["reasons"].extend(reason for reason in ("unsupported_or_conditional_source",) if reason not in candidate["reasons"])
    eligible_groups: dict[tuple[str, str, str], list[dict[str, object]]] = {}
    for candidate in candidates:
        if candidate["eligible_use_ids"]:
            eligible_groups.setdefault((str(candidate["identifier"]), str(candidate["path"]), str(candidate["owner_fact_id"])), []).append(candidate)
    for group in eligible_groups.values():
        if len(group) > 1:
            for candidate in group:
                candidate["eligible_use_ids"] = []
                candidate["reasons"].append("ambiguous_same_owner_declarations")
    for candidate in candidates:
        if not candidate["eligible_use_ids"] and not candidate["reasons"]:
            candidate["reasons"].append("not_same_file_and_lexical_owner_as_origin_use")
    candidates.sort(key=lambda item: (str(item["identifier"]), str(item["path"]).encode("utf-8"),
                                      item["span"]["start_offset"], str(item["owner_type_id"]), str(item["candidate_id"])))
    by_obligation = []
    for obligation in absent:
        uses = [item for item in origin_uses if item["obligation_id"] == obligation["obligation_id"]]
        matched = [item for item in candidates if any(item["identifier"] == use["identifier"] for use in uses)]
        use_ids = {item["use_id"] for item in uses}
        eligible = [item["candidate_id"] for item in matched if use_ids.intersection(item["eligible_use_ids"])]
        by_obligation.append({"obligation": obligation, "origin_use_ids": [item["use_id"] for item in uses],
                              "candidate_ids": [item["candidate_id"] for item in matched],
                              "eligible_candidate_ids": eligible,
                              "unresolved_reasons": sorted(
                                  {reason for item in matched for reason in item["reasons"]}
                                  | (set() if eligible else {"no_eligible_declaration"}))})
    packet_out: dict[str, object] = {
        "expansion_schema_version": expansion_schema_version, "packet_type": "gap_local_evidence_expansion_review",
        "source_run_path": os.fspath(source), "destination_run_path": os.fspath(destination),
        "question": packet["question"], "question_bytes_utf8_hex": str(packet["question"]).encode("utf-8").hex(),
        "question_sha256": packet["question_sha256"],
        "obligations": {"canonical_path": identity["obligations_file_path"], "raw_sha256": identity["obligations_file_sha256"],
                        "meanings": packet["obligations"]},
        "source_gap_sha256": gap["package_sha256"], "source_gap_file_sha256": hashlib.sha256(_read_regular_bytes(source / "evidence-gap.json", "source evidence gap")).hexdigest(),
        "selection_packet_sha256": packet["packet_sha256"],
        "selection_semantic_sha256": packet["semantic_sha256"], "selection_sha256": _digest(selection_record),
        "identity": {key: identity[key] for key in ("repository_root", "head", "head_ref", "repository_status",
                     "snapshot_id", "extractor_identity", "controller_type_id")},
        "search": {"grammar": EXPANSION_GRAMMAR, "max_bytes": max_bytes, "scanned_source_bytes": scanned_bytes,
                   "complete": not bool(exclusions or untracked_csharp), "seed_rule": "exact case-sensitive C# identifier overlap among authoritative meaning, map claim, and verified cited source snippet",
                   "binding_boundary": "lexical owner and conservative method/scope token analysis only; no compiler binding is claimed",
                   "identifiers": sorted(seeds), "candidate_order": ["identifier", "path UTF-8 bytes", "start_offset", "owner_type_id", "candidate_id"]},
        "absent_obligations": by_obligation, "origin_uses": origin_uses, "declaration_candidates": candidates,
        "exclusions": sorted(exclusions, key=lambda item: (str(item.get("path", "")), str(item.get("reason", "")))),
        "review_contract": _expansion_review_contract(expansion_schema_version, by_obligation, candidates),
        "evidence_boundary": "Supplemental expansion evidence is distinct from candidate.map and its original receipt. A later import requires separate expansion packet, review, and package hashes and cannot reuse map-review authority. The original map's numeric value remains unproven from that map.",
    }
    packet_out["packet_sha256"] = _digest(packet_out)
    encoded = _bytes(packet_out)
    if len(encoded) > max_bytes:
        raise CoordinatorError(f"canonical expansion packet exceeds --max-bytes: observed {len(encoded)}, limit {max_bytes}; no packet written")
    return packet_out


def _expansion_review_contract(version: int, absent_obligations: list[dict[str, object]],
                               candidates: list[dict[str, object]]) -> dict[str, object]:
    if version == 1:
        # Frozen v1 packet wire shape. The omission of `decision` is retained so old
        # packet bytes reconstruct exactly; the validator still requires it.
        return {"review_schema_version": 1, "packet_sha256": "copy expansion-review-packet.json packet_sha256 exactly",
            "reviewer_identity": "nonempty audit label, not authentication", "reviewer_model": "GPT-6.1 Sol High audit label, not authentication",
            "obligation_reviews": {"coverage": "one ordered entry for every absent_obligations item", "fields": ["obligation_id", "classification", "selected_candidate_ids", "basis"],
                "classification": {"local_evidence": "may select only exact candidate IDs listed eligible_candidate_ids for this obligation", "external_or_unresolved": "selected_candidate_ids must be empty"}},
            "candidate_reviews": {"coverage": "account for every declaration_candidates item exactly once", "fields": ["candidate_id", "disposition", "basis"], "disposition": ["selected", "not_selected"]},
            "rules": "Every absent obligation and every candidate must be accounted for exactly once. Local evidence requires semantic confirmation that the cited declaration supplies the missing fact; eligibility is only a code-owned lexical boundary. Candidates are leads, not evidence until reviewed. Labels are audit labels, not authentication."}
    if version != EXPANSION_REVIEW_SCHEMA["version"]:
        raise CoordinatorError(f"unsupported expansion schema version {version!r}; allowed versions are 1 and {EXPANSION_REVIEW_SCHEMA['version']}")
    schema = EXPANSION_REVIEW_SCHEMA
    return {
        "reviewer_model": {"exact": schema["reviewer_model"], "meaning": "audit label, not authentication"},
        "encoding": "JSON encoded as ASCII-escaped bytes valid as UTF-8; sorted object keys; compact separators (',', ':'); no BOM; exactly one trailing newline",
        "exact_top_level_fields": sorted(schema["fields"]),
        "object_fields": {
            "top_level": sorted(schema["fields"]),
            "obligation_review": sorted(schema["obligation_fields"]),
            "candidate_review": sorted(schema["candidate_fields"]),
        },
        "packet_sha256": "copy expansion-review-packet.json packet_sha256 exactly",
        "reviewer_identity": "nonempty audit label; not authentication",
        "review_schema_version": schema["version"],
        "decision": {"allowed": list(schema["decisions"]),
            "accepted": "save the review and package; local, unresolved, or mixed classifications are allowed and unresolved obligations yield an external_or_unresolved package",
            "rejected": "save the review only; do not create an expansion package"},
        "obligation_reviews": {"coverage": "exactly one entry for every absent_obligations item, in packet order",
            "ordered_obligations": [{"obligation_id": item["obligation"]["obligation_id"],
                "eligible_candidate_ids": list(item["eligible_candidate_ids"])} for item in absent_obligations],
            "fields": sorted(schema["obligation_fields"]),
            "basis": "nonempty string of at least 20 characters",
            "classification": {"allowed": list(schema["classifications"]),
                "local_evidence": "selected_candidate_ids must be nonempty and contain only IDs in this obligation's eligible_candidate_ids, in declaration_candidates packet order",
                "external_or_unresolved": "selected_candidate_ids must be empty"},
            "selected_candidate_ids": "array of unique strings in declaration_candidates packet order; local_evidence requires at least one eligible ID"},
        "candidate_reviews": {"coverage": "exactly one entry for every declaration_candidates item, in packet order",
            "ordered_candidate_ids": [item["candidate_id"] for item in candidates],
            "fields": sorted(schema["candidate_fields"]), "disposition": list(schema["dispositions"]),
            "basis": "nonempty string of at least 20 characters",
            "selected_union": "disposition is selected exactly when candidate_id occurs in the union of local obligation selected_candidate_ids"},
        "rules": "All object fields are exact; arrays have complete ordered coverage. Every absent obligation is classified once, every candidate is reviewed once, and each selected candidate is eligible for every obligation that selects it. Sol provides the semantic judgment; code validates schema, ordering, and code-owned eligibility. Reviewer labels are unauthenticated.",
    }


def expand_gap_prepare(repo: str, db: str, source_run_dir: str, destination_run_dir: str,
                       obligations_file: str, max_bytes: int = 10_000_000) -> dict[str, object]:
    max_bytes = _validate_expansion_max_bytes(max_bytes)
    destination = _canonical_run_path(Path(destination_run_dir), "destination run", must_exist=False)
    if destination.exists():
        if destination.is_symlink() or not destination.is_dir():
            raise CoordinatorError("destination run must be a real directory")
        allowed = {EXPANSION_PACKET, EXPANSION_REVIEW, EXPANSION_PACKAGE, EXPANSION_IMPORT_BINDING}
        existing = {item.name for item in destination.iterdir()}
        if existing - allowed:
            raise CoordinatorError("destination run already contains unrelated artifacts; choose an empty destination")
        if EXPANSION_PACKET in existing:
            try:
                saved_packet = _read_artifact(destination, EXPANSION_PACKET)
                saved_search = saved_packet.get("search")
                saved_max_bytes = saved_search.get("max_bytes") if isinstance(saved_search, dict) else None
                if type(saved_max_bytes) is not int or saved_max_bytes != max_bytes:
                    raise CoordinatorError(f"--max-bytes requested {max_bytes}; saved expansion packet requires {saved_max_bytes!r}; supply the saved value to replay")
                destination, packet = _reconstruct_expansion_packet(repo, db, source_run_dir, os.fspath(destination), obligations_file)
                if EXPANSION_IMPORT_BINDING in existing:
                    expand_gap_status(repo, db, source_run_dir, os.fspath(destination), obligations_file)
            except CoordinatorError as exc:
                raise CoordinatorError(f"immutable artifact already exists and does not match the requested replay: {exc}") from exc
            return {"result": "expansion_review_prepared", "destination_run_dir": os.fspath(destination),
                "packet_sha256": packet["packet_sha256"], "packet_bytes": len(_bytes(packet)),
                "absent_obligation_count": len(packet["absent_obligations"]),
                "candidate_count": len(packet["declaration_candidates"])}
        if existing:
            raise CoordinatorError("expansion destination contains review/package artifacts without its packet")
    packet = _build_gap_expansion_packet(repo, db, source_run_dir, os.fspath(destination), obligations_file, max_bytes)
    destination.mkdir(parents=True, exist_ok=True)
    _save_immutable(destination / EXPANSION_PACKET, packet)
    return {"result": "expansion_review_prepared", "destination_run_dir": os.fspath(destination),
            "packet_sha256": packet["packet_sha256"], "packet_bytes": len(_bytes(packet)),
            "absent_obligation_count": len(packet["absent_obligations"]),
            "candidate_count": len(packet["declaration_candidates"])}


def _expansion_review_template(packet: dict[str, object]) -> dict[str, object]:
    schema = EXPANSION_REVIEW_SCHEMA if packet.get("expansion_schema_version") == EXPANSION_SCHEMA_VERSION else _EXPANSION_REVIEW_SCHEMA_V1
    return {"review_schema_version": schema["version"], "packet_sha256": packet["packet_sha256"],
        "reviewer_identity": "<Sol reviewer identity>", "reviewer_model": EXPANSION_REVIEW_SCHEMA["reviewer_model"],
        "decision": "<accepted|rejected>",
        "obligation_reviews": [{"obligation_id": item["obligation"]["obligation_id"], "classification": "<local_evidence|external_or_unresolved>",
            "selected_candidate_ids": [], "basis": "<Sol semantic judgment: explain whether local declarations satisfy the missing meaning>"}
            for item in packet["absent_obligations"]],
        "candidate_reviews": [{"candidate_id": item["candidate_id"], "disposition": "<selected|not_selected>",
            "basis": "<Sol semantic judgment for candidate>"} for item in packet["declaration_candidates"]]}


def _reconstruct_expansion_packet(repo: str, db: str, source_run_dir: str, destination_run_dir: str,
                                  obligations_file: str) -> tuple[Path, dict[str, object]]:
    source = _canonical_run_path(Path(source_run_dir), "source run", must_exist=True)
    destination = _canonical_run_path(Path(destination_run_dir), "destination run", must_exist=True)
    packet_path = destination / EXPANSION_PACKET
    saved = _read_artifact(destination, EXPANSION_PACKET)
    if saved.get("source_run_path") != os.fspath(source) or saved.get("destination_run_path") != os.fspath(destination):
        raise CoordinatorError("expansion packet source/destination binding differs from the requested run paths")
    version = saved.get("expansion_schema_version")
    if type(version) is not int or version not in (1, EXPANSION_SCHEMA_VERSION):
        raise CoordinatorError(f"expansion packet version observed {version!r}; allowed exact integer versions are 1 and {EXPANSION_SCHEMA_VERSION}")
    search = saved.get("search")
    max_bytes = search.get("max_bytes") if isinstance(search, dict) else None
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or not 1 <= max_bytes <= EXPANSION_MAX_BYTES:
        raise CoordinatorError("saved expansion packet has an invalid frozen max_bytes")
    expected = _build_gap_expansion_packet(repo, db, os.fspath(source), os.fspath(destination), obligations_file,
                                           max_bytes, expansion_schema_version=version)
    if _bytes(expected) != _read_regular_bytes(packet_path, "expansion packet"):
        raise CoordinatorError("expansion packet does not exactly reconstruct from current source, checkout, DB, obligations, and run binding")
    _validate_expansion_artifacts(destination)
    return destination, expected


def _validate_expansion_artifacts(destination: Path) -> None:
    allowed = {EXPANSION_PACKET, EXPANSION_REVIEW, EXPANSION_PACKAGE, EXPANSION_IMPORT_BINDING}
    entries = {item.name for item in destination.iterdir()}
    if entries - allowed:
        raise CoordinatorError("expansion destination contains unknown artifacts")
    for name in sorted(entries):
        artifact = _read_artifact(destination, name)
        if name == EXPANSION_PACKAGE:
            _validate_expansion_package_schema(artifact)
        elif name == EXPANSION_IMPORT_BINDING:
            _validate_expansion_import_binding_schema(artifact)


def _validate_expansion_package_schema(package: dict[str, object]) -> None:
    version = package.get("package_schema_version")
    if type(version) is not int or version != EXPANSION_PACKAGE_SCHEMA_VERSION:
        raise CoordinatorError("expansion package schema version must be the exact integer version 1")


EXPANSION_IMPORT_BINDING_FIELDS = {
    "binding_schema_version", "expansion_run_path", "source_run_path", "target_run_path",
    "question", "obligations", "controller_type_id", "checkout", "snapshot_id", "extractor_identity",
    "packet_sha256", "review_sha256", "package_sha256", "source_gap_sha256", "source_gap_file_sha256",
    "selection_packet_sha256", "selection_semantic_sha256", "selection_sha256", "support_joins",
    "source_inventory", "binding_sha256",
}


def _validate_expansion_import_binding_schema(binding: dict[str, object]) -> None:
    version = binding.get("binding_schema_version")
    if type(version) is not int or version != EXPANSION_IMPORT_BINDING_SCHEMA_VERSION:
        raise CoordinatorError("expansion import binding schema version must be the exact integer version 1")
    if set(binding) != EXPANSION_IMPORT_BINDING_FIELDS:
        raise CoordinatorError("expansion import binding must contain the exact code-owned fields")
    expected_hash = _digest({key: value for key, value in binding.items() if key != "binding_sha256"})
    if binding.get("binding_sha256") != expected_hash:
        raise CoordinatorError("expansion import binding self-hash does not match canonical content")


def _validate_expansion_review(packet: dict[str, object], review: object) -> dict[str, object]:
    packet_version = packet.get("expansion_schema_version")
    schema = EXPANSION_REVIEW_SCHEMA if packet_version == EXPANSION_SCHEMA_VERSION else _EXPANSION_REVIEW_SCHEMA_V1
    if not isinstance(review, dict):
        raise CoordinatorError("expansion review observed a non-object; required a JSON object with the exact code-owned top-level fields")
    _require_exact_fields(review, schema["fields"], "expansion review", "add missing fields and remove unexpected fields")
    version = review.get("review_schema_version")
    if type(version) is not int or version != schema["version"]:
        raise CoordinatorError(f"expansion review schema version observed {version!r}; required exact integer {schema['version']} for packet version {packet_version}")
    if review.get("packet_sha256") != packet.get("packet_sha256"):
        raise CoordinatorError(f"expansion review packet_sha256 observed {review.get('packet_sha256')!r}; copy the reconstructed packet_sha256 exactly")
    atlas._answer_nonempty(review.get("reviewer_identity"), "expansion reviewer_identity")
    if review.get("reviewer_model") != schema["reviewer_model"]:
        raise CoordinatorError(f"expansion reviewer_model must be exactly {schema['reviewer_model']}")
    decision = review.get("decision")
    if not isinstance(decision, str) or decision not in schema["decisions"]:
        raise CoordinatorError(f"expansion review decision observed {decision!r}; allowed values are {schema['decisions']!r}")
    obligations = packet["absent_obligations"]
    reviews = review.get("obligation_reviews")
    if not isinstance(reviews, list) or len(reviews) != len(obligations):
        raise CoordinatorError("expansion review must account for every absent obligation exactly once in packet order")
    selected_union: set[str] = set()
    local_count = 0
    for index, item in enumerate(reviews):
        expected = obligations[index]
        oid = expected["obligation"]["obligation_id"]
        if not isinstance(item, dict):
            raise CoordinatorError(f"expansion obligation review {index + 1} observed a non-object; required exact fields for {oid}")
        _require_exact_fields(item, schema["obligation_fields"], f"expansion obligation review {index + 1} ({oid})",
                              "add missing fields and remove unexpected fields")
        if item.get("obligation_id") != oid:
            raise CoordinatorError(f"expansion obligation review {index + 1} observed obligation_id {item.get('obligation_id')!r}; required {oid!r} in packet order")
        atlas._answer_nonempty(item.get("basis"), f"expansion obligation {oid} basis", 20)
        classification = item.get("classification")
        ids = item.get("selected_candidate_ids")
        eligible = set(expected["eligible_candidate_ids"])
        if not isinstance(ids, list) or any(not isinstance(value, str) for value in ids) or len(ids) != len(set(ids)):
            raise CoordinatorError(f"selected candidate IDs for {oid} must be a unique ordered string array")
        ordered_ids = [candidate["candidate_id"] for candidate in packet["declaration_candidates"] if candidate["candidate_id"] in set(ids)]
        if ids != ordered_ids:
            raise CoordinatorError(f"selected candidate IDs for {oid} observed order {ids!r}; required declaration_candidates packet order {ordered_ids!r}")
        if classification == "local_evidence":
            if not ids or any(value not in eligible for value in ids):
                raise CoordinatorError(f"local_evidence for {oid} requires nonempty IDs eligible for that exact obligation")
            local_count += 1
            selected_union.update(ids)
        elif classification == "external_or_unresolved":
            if ids:
                raise CoordinatorError(f"external_or_unresolved for {oid} must have no selected candidate IDs")
        else:
            raise CoordinatorError(f"expansion classification for {oid} is invalid")
    candidate_reviews = review.get("candidate_reviews")
    candidates = packet["declaration_candidates"]
    if not isinstance(candidate_reviews, list) or len(candidate_reviews) != len(candidates):
        raise CoordinatorError("expansion review must account for every declaration candidate exactly once in packet order")
    for index, item in enumerate(candidate_reviews):
        expected = candidates[index]
        candidate_id = expected["candidate_id"]
        if not isinstance(item, dict):
            raise CoordinatorError(f"candidate review {index + 1} observed a non-object; required exact fields for {candidate_id}")
        _require_exact_fields(item, schema["candidate_fields"], f"candidate review {index + 1} ({candidate_id})",
                              "add missing fields and remove unexpected fields")
        if item.get("candidate_id") != candidate_id:
            raise CoordinatorError(f"candidate review {index + 1} observed candidate_id {item.get('candidate_id')!r}; required {candidate_id!r} in packet order")
        atlas._answer_nonempty(item.get("basis"), f"candidate {candidate_id} basis", 20)
        disposition = item.get("disposition")
        should_select = candidate_id in selected_union
        if not isinstance(disposition, str) or disposition not in schema["dispositions"] or (disposition == "selected") != should_select:
            raise CoordinatorError(f"candidate disposition for {candidate_id} must match the union of selected obligation IDs")
        if should_select:
            eligible_for_local = [obligation for obligation, review_item in zip(obligations, reviews, strict=True)
                if review_item["classification"] == "local_evidence" and candidate_id in review_item["selected_candidate_ids"]]
            if any(candidate_id not in obligation["eligible_candidate_ids"] for obligation in eligible_for_local):
                raise CoordinatorError(f"shared candidate {candidate_id} is not independently eligible for every selecting obligation")
    normalized = dict(review)
    normalized["obligation_reviews"] = reviews
    normalized["candidate_reviews"] = candidate_reviews
    return normalized


def _require_exact_fields(value: dict[str, object], expected_fields: list[str], label: str, correction: str) -> None:
    expected = set(expected_fields)
    observed = set(value)
    missing = sorted(expected - observed)
    unexpected = sorted(observed - expected)
    if missing or unexpected:
        details = []
        if missing:
            details.append(f"missing fields {missing!r}")
        if unexpected:
            details.append(f"unexpected fields {unexpected!r}")
        raise CoordinatorError(f"{label} has {'; '.join(details)}; required correction: {correction}")


def _expansion_package(packet: dict[str, object], review: dict[str, object]) -> dict[str, object]:
    review_hash = _digest(review)
    selected_ids = {candidate_id for item in review["obligation_reviews"] for candidate_id in item["selected_candidate_ids"]}
    fully_local = (review["decision"] == "accepted" and packet["search"]["complete"]
                   and bool(review["obligation_reviews"])
                   and all(item["classification"] == "local_evidence" for item in review["obligation_reviews"]))
    lineage_fields = ("source_run_path", "destination_run_path", "question", "question_bytes_utf8_hex", "question_sha256",
        "obligations", "source_gap_sha256", "source_gap_file_sha256", "selection_packet_sha256", "selection_semantic_sha256",
        "selection_sha256", "identity", "search")
    package: dict[str, object] = {"package_schema_version": EXPANSION_PACKAGE_SCHEMA_VERSION,
        "package_type": "local_expansion" if fully_local else "external_or_unresolved",
        "packet_sha256": packet["packet_sha256"], "review_sha256": review_hash,
        "lineage": {key: packet[key] for key in lineage_fields},
        "current_answer_authority": False, "full_question_completeness": False, "completeness_claim": False,
        "review_authority_boundary": "This semantic review covers expansion candidates only. The original map receipt does not review these declarations and supplies no authority to import them."}
    if fully_local:
        candidates = {item["candidate_id"]: item for item in packet["declaration_candidates"]}
        selected_evidence = [{"evidence_kind": "supplemental_declaration_candidate", "candidate_id": candidate_id,
                              "declaration": candidates[candidate_id]}
                             for candidate_id in sorted(selected_ids)]
        use_ids = {use_id for candidate_id in selected_ids for use_id in candidates[candidate_id]["eligible_use_ids"]}
        origins = [{"evidence_kind": "origin_use_provenance", **use} for use in packet["origin_uses"] if use["use_id"] in use_ids]
        package["selected_declaration_evidence"] = selected_evidence
        package["origin_use_evidence"] = origins
        package["obligation_reviews"] = review["obligation_reviews"]
    else:
        incomplete_search = not packet["search"]["complete"]
        unresolved = []
        for item in review["obligation_reviews"]:
            if incomplete_search or item["classification"] == "external_or_unresolved":
                unresolved.append({"obligation_id": item["obligation_id"], "classification": item["classification"],
                    "reason": "search_incomplete" if incomplete_search else "reviewed_external_or_unresolved"})
        package["unresolved_obligations"] = unresolved
        package["unresolved_candidates"] = [{"candidate_id": item["candidate_id"], "reasons": item["reasons"],
                                               "review_disposition": review_item["disposition"]}
                                              for item in packet["declaration_candidates"]
                                              for review_item in review["candidate_reviews"]
                                              if review_item["candidate_id"] == item["candidate_id"]
                                              and review_item["disposition"] == "not_selected"]
    package["package_sha256"] = _digest(package)
    return package


def expand_gap_review(repo: str, db: str, source_run_dir: str, destination_run_dir: str,
                      obligations_file: str, review_file: str) -> dict[str, object]:
    destination, packet = _reconstruct_expansion_packet(repo, db, source_run_dir, destination_run_dir, obligations_file)
    if EXPANSION_PACKAGE in {item.name for item in destination.iterdir()}:
        _read_artifact(destination, EXPANSION_PACKAGE)
    review_path = Path(review_file).expanduser()
    raw_review = _read_regular_bytes(review_path, "expansion review input")
    try:
        review_input = json.loads(raw_review.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoordinatorError(f"cannot read expansion review input {review_path}: {exc}") from exc
    if not isinstance(review_input, dict) or raw_review != _bytes(review_input):
        raise CoordinatorError("expansion review input must be a canonical JSON object")
    review = _validate_expansion_review(packet, review_input)
    review_path_in_run = destination / EXPANSION_REVIEW
    if review["decision"] == "rejected" and (destination / EXPANSION_PACKAGE).exists():
        raise CoordinatorError("rejected review conflicts with an existing authoritative expansion package")
    _save_immutable(review_path_in_run, review)
    if review["decision"] == "rejected":
        return {"result": "expansion_review_saved", "state": "review_only", "review_sha256": _digest(review)}
    package = _expansion_package(packet, review)
    _save_immutable(destination / EXPANSION_PACKAGE, package)
    state = "local_expansion_ready" if package["package_type"] == "local_expansion" else "external_or_unresolved"
    return {"result": "expansion_review_saved", "state": state, "review_sha256": _digest(review),
            "package_sha256": package["package_sha256"], "package_type": package["package_type"]}


def expand_gap_status(repo: str, db: str, source_run_dir: str, destination_run_dir: str,
                      obligations_file: str) -> dict[str, object]:
    destination, packet = _reconstruct_expansion_packet(repo, db, source_run_dir, destination_run_dir, obligations_file)
    names = {item.name for item in destination.iterdir()}
    allowed = {EXPANSION_PACKET, EXPANSION_REVIEW, EXPANSION_PACKAGE, EXPANSION_IMPORT_BINDING}
    if names - allowed:
        raise CoordinatorError("expansion destination contains unknown artifacts")
    package_path = destination / EXPANSION_PACKAGE
    if EXPANSION_REVIEW not in names:
        if EXPANSION_PACKAGE in names:
            raise CoordinatorError("expansion package exists without its review")
        if EXPANSION_IMPORT_BINDING in names:
            raise CoordinatorError("expansion import binding exists without a reviewed package")
        return {"state": "packet_only", "packet_sha256": packet["packet_sha256"]}
    review = _read_artifact(destination, EXPANSION_REVIEW)
    review = _validate_expansion_review(packet, review)
    expected_package = _expansion_package(packet, review) if review["decision"] == "accepted" else None
    if EXPANSION_PACKAGE not in names:
        if EXPANSION_IMPORT_BINDING in names:
            raise CoordinatorError("expansion import binding exists without its package")
        return {"state": "review_only", "decision": review["decision"], "review_sha256": _digest(review),
                "package_pending": review["decision"] == "accepted"}
    if expected_package is None:
        raise CoordinatorError("rejected review must not have an expansion package")
    saved_package = _read_artifact(destination, EXPANSION_PACKAGE)
    if _bytes(expected_package) != _read_regular_bytes(package_path, "expansion package"):
        raise CoordinatorError("expansion package does not reconstruct from exact packet and review")
    binding_path = destination / EXPANSION_IMPORT_BINDING
    if binding_path.exists() or binding_path.is_symlink():
        binding = _read_artifact(destination, EXPANSION_IMPORT_BINDING)
        question_binding = binding.get("question")
        if not isinstance(question_binding, dict) or not isinstance(question_binding.get("canonical_path"), str):
            raise CoordinatorError("expansion import binding question path is malformed")
        _reconstruct_expanded_prepare(repo, db, source_run_dir, os.fspath(destination),
            os.fspath(question_binding["canonical_path"]), obligations_file,
            str(binding.get("target_run_path", "")))
    state = "local_expansion_ready" if saved_package["package_type"] == "local_expansion" else "external_or_unresolved"
    return {"state": state, "decision": review["decision"], "packet_sha256": packet["packet_sha256"],
            "review_sha256": _digest(review), "package_sha256": saved_package["package_sha256"],
            "package_type": saved_package["package_type"]}


def _paths_overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _canonical_target_path(path: str) -> Path:
    supplied = Path(path).expanduser()
    if supplied.is_symlink() or (supplied.exists() and not supplied.is_dir()):
        raise CoordinatorError(f"target run must be a real directory: {supplied}")
    try:
        return supplied.resolve(strict=False)
    except OSError as exc:
        raise CoordinatorError(f"cannot resolve target run {supplied}: {exc}") from exc


def _expansion_support_joins(packet: dict[str, object], review: dict[str, object],
                             package: dict[str, object]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if (packet.get("search", {}).get("complete") is not True
            or package.get("package_type") != "local_expansion"
            or package.get("current_answer_authority") is not False
            or package.get("full_question_completeness") is not False
            or package.get("completeness_claim") is not False):
        raise CoordinatorError("expansion is not complete local evidence with answer and completeness authority disabled")
    candidates = {item["candidate_id"]: item for item in packet["declaration_candidates"]}
    uses = {item["use_id"]: item for item in packet["origin_uses"]}
    joins: list[dict[str, object]] = []
    supplemental: list[dict[str, object]] = []
    for item in review["obligation_reviews"]:
        oid = item["obligation_id"]
        if item["classification"] != "local_evidence" or not item["selected_candidate_ids"]:
            raise CoordinatorError(f"local expansion import requires local evidence for every absent obligation; observed {oid}")
        absent = next((row for row in packet["absent_obligations"] if row["obligation"]["obligation_id"] == oid), None)
        if absent is None:
            raise CoordinatorError(f"selected obligation {oid} is absent from the reconstructed expansion packet")
        allowed_candidates = set(absent["eligible_candidate_ids"])
        for candidate_id in item["selected_candidate_ids"]:
            candidate = candidates.get(candidate_id)
            if candidate is None or candidate_id not in allowed_candidates:
                raise CoordinatorError(f"selected candidate {candidate_id} is not eligible for exact obligation {oid}")
            matched_uses = []
            for use_id in candidate["eligible_use_ids"]:
                use = uses.get(use_id)
                if use is None or use.get("obligation_id") != oid:
                    continue
                anchor = use.get("source_anchor")
                if (use.get("identifier") != candidate.get("identifier")
                        or not isinstance(anchor, dict)
                        or anchor.get("path") != candidate.get("path")
                        or anchor.get("sha256") != candidate.get("sha256")
                        or use.get("owner_fact_id") != candidate.get("owner_fact_id")
                        or use.get("owner_type_id") != candidate.get("owner_type_id")
                        or not use.get("unqualified") or use.get("conditional")):
                    raise CoordinatorError(f"candidate {candidate_id} does not exactly join eligible source, owner, route, and use for {oid}")
                matched_uses.append(use)
            if not matched_uses:
                raise CoordinatorError(f"candidate {candidate_id} has no obligation-matched eligible origin use for {oid}")
            for use in matched_uses:
                join = {"obligation_id": oid, "candidate_id": candidate_id, "use_id": use["use_id"],
                    "route_fact_id": use["route_fact_id"], "owner_fact_id": use["owner_fact_id"],
                    "source_anchor": use["source_anchor"], "citation": use["citation"]}
                joins.append(join)
                supplemental.append({"evidence_kind": "supplemental_declaration_candidate",
                    "eligibility": "eligible_for_later_selection_review", "answer_authority": False,
                    "obligation_id": oid, "candidate_id": candidate_id, "declaration": candidate,
                    "origin_use": {"use_id": use["use_id"], "route_fact_id": use["route_fact_id"],
                        "citation": use["citation"], "source_anchor": use["source_anchor"],
                        "identifier_use_span": use["identifier_use_span"], "owner_fact_id": use["owner_fact_id"],
                        "owner_type_id": use["owner_type_id"]}})
    joins.sort(key=lambda row: (row["obligation_id"], row["candidate_id"], row["use_id"]))
    supplemental.sort(key=lambda row: (row["obligation_id"], row["candidate_id"], row["origin_use"]["use_id"]))
    return joins, supplemental


def _build_expansion_import_state(repo: str, db: str, source_run_dir: str, expansion_run_dir: str,
                                  question_file: str, obligations_file: str, target_run_dir: str
                                  ) -> tuple[dict[str, object], dict[str, object], dict[str, object], Path, Path]:
    source = _canonical_run_path(Path(source_run_dir), "source run", must_exist=True)
    expansion, expansion_packet = _reconstruct_expansion_packet(repo, db, source_run_dir, expansion_run_dir, obligations_file)
    if EXPANSION_REVIEW not in {item.name for item in expansion.iterdir()} or EXPANSION_PACKAGE not in {item.name for item in expansion.iterdir()}:
        raise CoordinatorError("expansion import requires a saved accepted review and package")
    review = _validate_expansion_review(expansion_packet, _read_artifact(expansion, EXPANSION_REVIEW))
    if review["decision"] != "accepted":
        raise CoordinatorError("expansion import requires an accepted semantic review")
    expected_package = _expansion_package(expansion_packet, review)
    if expected_package["package_type"] != "local_expansion":
        raise CoordinatorError("external, mixed, or incomplete expansion package cannot be imported")
    if _bytes(expected_package) != _read_regular_bytes(expansion / EXPANSION_PACKAGE, "expansion package"):
        raise CoordinatorError("saved expansion package differs from reconstructed packet and review")
    joins, supplemental = _expansion_support_joins(expansion_packet, review, expected_package)

    try:
        question_input = Path(question_file).expanduser()
        if question_input.is_symlink():
            raise CoordinatorError(f"question file must be a no-follow regular file: {question_input}")
        question_path = question_input.resolve(strict=True)
        question_raw = _read_regular_bytes(question_input, "question file")
        question = question_raw.decode("utf-8")
    except CoordinatorError:
        raise
    except (OSError, UnicodeDecodeError) as exc:
        raise CoordinatorError(f"question file must be readable no-follow UTF-8: {exc}") from exc
    if (question != expansion_packet.get("question")
            or hashlib.sha256(question_raw).hexdigest() != expansion_packet.get("question_sha256")):
        raise CoordinatorError("question file bytes do not exactly match the original selection and expansion question")
    obligations = expansion_packet["obligations"]
    obligations_path = Path(obligations_file).expanduser().resolve(strict=True)
    obligations_raw = _read_regular_bytes(obligations_path, "obligations file")
    if (os.fspath(obligations_path) != obligations["canonical_path"]
            or hashlib.sha256(obligations_raw).hexdigest() != obligations["raw_sha256"]):
        raise CoordinatorError("obligations path differs from the frozen expansion packet")
    # Rebuild the ordinary packet against current maps and require exact byte identity with the original run.
    source_packet = _read_artifact(source, "selection-packet.json")
    ordinary_packet, candidates = _build_prepared_selection(repo, db, question_raw, question, obligations_file,
        str(source_packet.get("identity", {}).get("controller_type_id", "")), DEFAULT_LIMIT)
    if _bytes(ordinary_packet) != _read_regular_bytes(source / "selection-packet.json", "source selection packet"):
        raise CoordinatorError("current question, obligations, controller, checkout, maps, or receipts differ from the original source selection packet")
    current_route_ids = {candidate["route"]["id"] for candidate in candidates}
    if any(join["route_fact_id"] not in current_route_ids for join in joins):
        raise CoordinatorError("supplemental origin use route is not present in the current accepted route maps")
    if ordinary_packet["obligations"] != obligations["meanings"]:
        raise CoordinatorError("original obligations meanings differ from expansion lineage")

    target = _canonical_target_path(target_run_dir)
    db_path = Path(db).expanduser().resolve(strict=True)
    repo_path = Path(repo).expanduser().resolve(strict=True)
    paths = [("source run", source), ("expansion run", expansion), ("target run", target),
             ("repository", repo_path), ("database", db_path)]
    for index, (left_name, left) in enumerate(paths):
        for right_name, right in paths[index + 1:]:
            if _paths_overlap(left, right):
                raise CoordinatorError(f"{left_name} path overlaps {right_name}: {left} and {right}")

    packet = {key: value for key, value in ordinary_packet.items()
              if key not in {"semantic_sha256", "packet_sha256"}}
    identity = ordinary_packet["identity"]
    binding: dict[str, object] = {
        "binding_schema_version": EXPANSION_IMPORT_BINDING_SCHEMA_VERSION,
        "expansion_run_path": os.fspath(expansion), "source_run_path": os.fspath(source),
        "target_run_path": os.fspath(target),
        "question": {"canonical_path": os.fspath(question_path), "raw_sha256": hashlib.sha256(question_raw).hexdigest(),
                     "text": question, "question_sha256": ordinary_packet["question_sha256"]},
        "obligations": {"canonical_path": obligations["canonical_path"], "raw_sha256": obligations["raw_sha256"],
                        "meanings": obligations["meanings"]},
        "controller_type_id": identity["controller_type_id"],
        "checkout": {key: identity[key] for key in ("repository_root", "head", "head_ref", "repository_status")},
        "snapshot_id": identity["snapshot_id"], "extractor_identity": identity["extractor_identity"],
        "packet_sha256": expansion_packet["packet_sha256"], "review_sha256": _digest(review),
        "package_sha256": expected_package["package_sha256"],
        "source_gap_sha256": expansion_packet["source_gap_sha256"],
        "source_gap_file_sha256": expansion_packet["source_gap_file_sha256"],
        "selection_packet_sha256": expansion_packet["selection_packet_sha256"],
        "selection_semantic_sha256": expansion_packet["selection_semantic_sha256"],
        "selection_sha256": expansion_packet["selection_sha256"],
        "support_joins": joins,
        "source_inventory": {
            "routes": [{"route_fact_id": candidate["route"]["id"], "map_sha256": _digest(candidate["map"]),
                "review_receipt_hash": candidate["provenance"].get("flow_review_receipt", {}).get("receipt_hash"),
                "binding_hash": candidate["provenance"].get("binding_hash"),
                "association_review_hash": candidate["provenance"].get("association_review_hash")}
                for candidate in candidates],
            "declarations": [{"path": candidate["path"], "sha256": candidate["sha256"]}
                for candidate in expansion_packet["declaration_candidates"] if candidate["candidate_id"] in
                    {row["candidate_id"] for row in joins}],
        },
    }
    binding["binding_sha256"] = _digest(binding)
    packet["supplemental_evidence"] = {"schema_version": 1, "current_answer_authority": False,
        "full_question_completeness": False, "completeness_claim": False,
        "state": "eligible_for_later_selection_review", "records": supplemental}
    packet["expansion_binding_lineage"] = {"binding_sha256": binding["binding_sha256"],
        "expansion_run_path": os.fspath(expansion), "packet_sha256": binding["packet_sha256"],
        "review_sha256": binding["review_sha256"], "package_sha256": binding["package_sha256"],
        "source_run_path": os.fspath(source), "target_run_path": os.fspath(target)}
    semantic_payload = _semantic_payload(packet["identity"], packet["question"], packet["question_sha256"],
        packet["obligation_id"], packet["required_routes"], packet["obligations"], packet["candidates"])
    semantic_payload["supplemental_evidence"] = packet["supplemental_evidence"]
    semantic_payload["expansion_binding_lineage"] = packet["expansion_binding_lineage"]
    packet["semantic_sha256"] = _digest(semantic_payload)
    packet["packet_sha256"] = _digest(packet)
    observations = _candidate_observations(candidates, packet["packet_sha256"])
    return binding, packet, observations, expansion, target


def _reconstruct_expanded_prepare(repo: str, db: str, source_run_dir: str, expansion_run_dir: str,
                                  question_file: str, obligations_file: str, target_run_dir: str,
                                  *, allow_partial: bool = True
                                  ) -> tuple[dict[str, object], dict[str, object], dict[str, object], Path, Path]:
    binding, packet, observations, expansion, target = _build_expansion_import_state(repo, db,
        source_run_dir, expansion_run_dir, question_file, obligations_file, target_run_dir)
    saved_binding = _read_artifact(expansion, EXPANSION_IMPORT_BINDING)
    _validate_expansion_import_binding_schema(saved_binding)
    if _bytes(binding) != _read_regular_bytes(expansion / EXPANSION_IMPORT_BINDING, "expansion import binding"):
        raise CoordinatorError("saved expansion import binding does not reconstruct from current source, review, package, question, maps, and target")
    names = {item.name for item in target.iterdir()} if target.exists() else set()
    allowed = {"selection-packet.json", "candidate-observations.json", "selection.json", "answer-packet.json", "evidence-gap.json",
               "review.json", "answer-review-packet.json", "review-result.json", "correction-packet.json",
               "corrected-answer-packet.json", "corrected-review.json", "accepted-package.json"}
    if names - allowed:
        raise CoordinatorError("target run contains unrelated artifacts; expanded prepare requires a fresh target")
    if not allow_partial and not {"selection-packet.json", "candidate-observations.json"}.issubset(names):
        raise CoordinatorError("expanded target is incomplete; status requires both packet artifacts")
    packet_path = target / "selection-packet.json"
    if packet_path.exists() or packet_path.is_symlink():
        if _read_regular_bytes(packet_path, "expanded target selection packet") != _bytes(packet):
            raise CoordinatorError("expanded target selection packet differs from independent reconstruction")
    observation_path = target / "candidate-observations.json"
    if observation_path.exists() or observation_path.is_symlink():
        saved_observations = _validate_candidate_observations(_read_artifact(target, "candidate-observations.json"), packet)
        if _bytes(_observation_projection(saved_observations)) != _bytes(_observation_projection(observations)):
            raise CoordinatorError("expanded target observations differ from current maps, excluding only freshness.checked_at")
        observations = saved_observations
    return binding, packet, observations, expansion, target


def _expanded_join_rows(packet: dict[str, object]) -> list[dict[str, object]]:
    supplemental = packet.get("supplemental_evidence")
    records = supplemental.get("records") if isinstance(supplemental, dict) else None
    if not isinstance(records, list):
        raise CoordinatorError("expanded packet supplemental records are malformed")
    joins = []
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("declaration"), dict) or not isinstance(record.get("origin_use"), dict):
            raise CoordinatorError("expanded packet supplemental record is malformed")
        declaration, origin = record["declaration"], record["origin_use"]
        joins.append({"obligation_id": record.get("obligation_id"), "candidate_id": record.get("candidate_id"),
            "use_id": origin.get("use_id"), "route_fact_id": origin.get("route_fact_id"),
            "path": declaration.get("path"), "sha256": declaration.get("sha256"),
            "owner_fact_id": declaration.get("owner_fact_id"), "owner_type_id": declaration.get("owner_type_id")})
    joins.sort(key=lambda item: (str(item["obligation_id"]), str(item["candidate_id"]), str(item["use_id"])))
    if any(not isinstance(item[key], str) or not item[key] for item in joins for key in item):
        raise CoordinatorError("expanded packet contains an incomplete candidate/use/route/source/owner join")
    return joins


def _expanded_obligation_groups(packet: dict[str, object]) -> list[dict[str, object]]:
    by_id: dict[str, list[dict[str, object]]] = {}
    for row in _expanded_join_rows(packet):
        by_id.setdefault(str(row["obligation_id"]), []).append(row)
    obligation_ids = _obligation_ids(packet["obligations"])
    groups = []
    for obligation_id in obligation_ids:
        rows = by_id.get(obligation_id, [])
        if rows:
            groups.append({"obligation_id": obligation_id,
                "supporting_route_fact_ids": sorted({str(row["route_fact_id"]) for row in rows}),
                "route_candidate_ids_must_remain_accepted": sorted({str(row["route_fact_id"]) for row in rows}),
                "declaration_candidate_ids": sorted({str(row["candidate_id"]) for row in rows}),
                "joins": rows})
    extra = set(by_id) - set(obligation_ids)
    if extra:
        raise CoordinatorError(f"expanded packet has supplemental records for unknown obligations: {sorted(extra)}")
    return groups


def _expansion_selector_view(packet: dict[str, object]) -> dict[str, object]:
    return {"selector_view_schema_version": EXPANSION_SELECTOR_VIEW_VERSION,
        "selection_packet_sha256": packet["packet_sha256"],
        "supplemental_obligations": _expanded_obligation_groups(packet),
        "support_rule": "For each listed obligation, supporting_route_fact_ids must equal its bound supplemental route set exactly; every candidate listed must remain accepted.",
        "semantic_answer_claim": False}


def _expanded_selection_authority(packet: dict[str, object]) -> dict[str, object]:
    lineage = packet.get("expansion_binding_lineage")
    if not isinstance(lineage, dict):
        raise CoordinatorError("expanded packet binding lineage is malformed")
    authority = {"authority_schema_version": EXPANSION_SELECTION_AUTHORITY_VERSION,
        "selection_packet_sha256": packet["packet_sha256"],
        "expansion_packet_sha256": lineage.get("packet_sha256"),
        "expansion_review_sha256": lineage.get("review_sha256"),
        "expansion_package_sha256": lineage.get("package_sha256"),
        "expansion_binding_sha256": lineage.get("binding_sha256"),
        "obligations": _expanded_obligation_groups(packet)}
    authority["authority_sha256"] = _digest(authority)
    return authority


def _check_expanded_selection_support(packet: dict[str, object], record: dict[str, object]) -> dict[str, object]:
    groups = _expanded_obligation_groups(packet)
    reviews, candidates = record.get("obligation_reviews"), record.get("candidate_reviews")
    if not isinstance(reviews, list) or not isinstance(candidates, list):
        raise CoordinatorError("expanded selection reviews are malformed")
    candidate_decisions = {item.get("route_fact_id"): item.get("decision") for item in candidates if isinstance(item, dict)}
    for group in groups:
        obligation_id = str(group["obligation_id"])
        item = next((value for value in reviews if isinstance(value, dict) and value.get("obligation_id") == obligation_id), None)
        if item is None or item.get("candidate_status") != "present_in_candidates":
            raise CoordinatorError(f"expanded obligation {obligation_id} must be present through reviewed supplemental support")
        expected_routes = group["supporting_route_fact_ids"]
        if item.get("supporting_route_fact_ids") != expected_routes:
            raise CoordinatorError(f"expanded obligation {obligation_id} supporting_route_fact_ids must equal its bound supplemental route set exactly: {expected_routes!r}")
        rejected = [route_id for route_id in expected_routes if candidate_decisions.get(route_id) != "accept"]
        if rejected:
            raise CoordinatorError(f"expanded obligation {obligation_id} requires accepted supplemental route candidate(s): {rejected!r}")
    return _expanded_selection_authority(packet)


def _build_expanded_answer_packet(packet: dict[str, object], selection_payload: dict[str, object],
                                  union: dict[str, object]) -> dict[str, object]:
    result = {"answer_schema_version": 1, "packet_type": "multi_map_answer", "question": packet["question"],
        "question_sha256": packet["question_sha256"], "controller_type_id": packet["identity"]["controller_type_id"],
        "obligation_id": packet["obligation_id"], "snapshot_id": packet["identity"]["snapshot_id"],
        "extractor_identity": packet["identity"]["extractor_identity"], "selection": selection_payload,
        "required_routes": packet["required_routes"], "obligations": packet["obligations"],
        "claims": list(union["claims"]), "source_anchors": list(union["source_anchors"]),
        "source_snippets": list(union["source_snippets"])}
    anchors, snippets = result["source_anchors"], result["source_snippets"]
    records = packet["supplemental_evidence"]["records"]
    for record in sorted(records, key=lambda value: (str(value["obligation_id"]), str(value["candidate_id"]), str(value["origin_use"]["use_id"]))):
        declaration = record["declaration"]
        path, sha, span, claim_text = declaration["path"], declaration["sha256"], declaration["span"], declaration["snippet"]
        if not isinstance(claim_text, str) or not claim_text:
            raise CoordinatorError("supplemental declaration claim has no exact source snippet")
        anchor = next((item for item in anchors if item["path"] == path and item["sha256"] == sha), None)
        if anchor is None:
            anchor = {"source_id": f"source-{len(anchors) + 1}", "path": path, "sha256": sha}
            anchors.append(anchor)
        snippet = next((item for item in snippets if item["source_id"] == anchor["source_id"] and item["span"] == span), None)
        if snippet is not None and snippet["text"] != claim_text:
            raise CoordinatorError(f"supplemental source snippet collides with different text at {path} {span!r}")
        if snippet is None:
            snippet_id = "snippet-" + hashlib.sha256(_bytes([path, sha, _bytes(span).decode("ascii")])).hexdigest()
            if any(item["snippet_id"] == snippet_id and item["text"] != claim_text for item in snippets):
                raise CoordinatorError("supplemental snippet identity collides with conflicting text")
            snippet = {"snippet_id": snippet_id, "source_id": anchor["source_id"], "span": span, "text": claim_text}
            snippets.append(snippet)
        elif not snippet.get("snippet_id"):
            raise CoordinatorError("reused source snippet is missing its stable identity")
        claim_number = len(result["claims"]) + 1
        origin, lineage = record["origin_use"], packet["expansion_binding_lineage"]
        result["claims"].append({"claim_number": claim_number, "claim": claim_text,
            "evidence": [{"claim_number": claim_number, "fact_id": "expansion-" + str(record["candidate_id"]),
                "source_id": anchor["source_id"], "path": path, "sha256": sha, "span": span,
                "snippet_id": snippet["snippet_id"]}],
            "provenance": {"evidence_kind": "supplemental_declaration", "obligation_id": record["obligation_id"],
                "candidate_id": record["candidate_id"], "use_id": origin["use_id"], "route_fact_id": origin["route_fact_id"],
                "owner_fact_id": declaration["owner_fact_id"], "owner_type_id": declaration["owner_type_id"],
                "expansion_packet_sha256": lineage["packet_sha256"], "expansion_review_sha256": lineage["review_sha256"],
                "expansion_package_sha256": lineage["package_sha256"], "expansion_binding_sha256": lineage["binding_sha256"],
                "old_map_receipt_authority": False}})
    result["expansion_provenance"] = dict(packet["expansion_binding_lineage"])
    result["original_map_limitation"] = "The original candidate.map and its receipt did not prove the supplemental declaration or numeric value; this evidence has separate expansion review authority."
    result["current_answer_authority"] = False
    result["full_question_completeness"] = False
    result["completeness_claim"] = False
    result["answer_contract"] = _answer_contract(result)
    result["semantic_sha256"] = _digest({key: value for key, value in result.items() if key != "semantic_sha256"})
    return result


def _expanded_evidence_gap(packet: dict[str, object], selection_payload: dict[str, object],
                           partial_packet: dict[str, object]) -> dict[str, object]:
    record = selection_payload["selection_record"]
    reviews = record["obligation_reviews"]
    absent = [item for item in reviews if item["candidate_status"] == "absent_from_candidates"]
    mandatory = {group["obligation_id"] for group in _expanded_obligation_groups(packet)}
    if not absent:
        raise CoordinatorError("expanded evidence-gap terminal requires at least one absent ordinary obligation")
    if any(item["obligation_id"] in mandatory for item in absent):
        raise CoordinatorError("a mandatory supplemental obligation cannot remain absent in an expanded evidence gap")
    lineage = packet["expansion_binding_lineage"]
    gap = {"schema_version": 1, "result": "evidence_gap", "question": packet["question"],
        "packet_sha256": packet["packet_sha256"], "semantic_sha256": packet["semantic_sha256"],
        "selection_packet_sha256": packet["packet_sha256"],
        "expansion_packet_sha256": lineage["packet_sha256"], "expansion_review_sha256": lineage["review_sha256"],
        "expansion_package_sha256": lineage["package_sha256"], "expansion_binding_sha256": lineage["binding_sha256"],
        "expansion_lineage": lineage, "selection": selection_payload,
        "selection_sha256": _digest(record), "selection_payload_sha256": _digest(selection_payload),
        "selected_route_fact_ids": [item["route_fact_id"] for item in selection_payload["selected_candidates"]],
        "absent_obligations": absent,
        "supported_partial_coverage": {"claims": partial_packet["claims"],
            "source_anchors": partial_packet["source_anchors"], "source_snippets": partial_packet["source_snippets"]},
        "original_map_limitation": partial_packet["original_map_limitation"],
        "current_answer_authority": False, "full_question_completeness": False, "completeness_claim": False}
    gap["package_sha256"] = _digest(gap)
    return gap


def _revalidate_expanded_selection(run: Path, repo: str, db: str, obligations_file: str,
                                   expansion_run_dir: str, packet: dict[str, object]) -> dict[str, object]:
    lineage = packet.get("expansion_binding_lineage")
    if not isinstance(lineage, dict):
        raise CoordinatorError("expanded selection packet lineage is malformed")
    expansion = _canonical_run_path(Path(expansion_run_dir), "expansion run", must_exist=True)
    if os.fspath(expansion) != lineage.get("expansion_run_path"):
        raise CoordinatorError("expanded selection requires the exact bound --expansion-run-dir")
    binding = _read_artifact(expansion, EXPANSION_IMPORT_BINDING)
    question = binding.get("question") if isinstance(binding, dict) else None
    question_path = question.get("canonical_path") if isinstance(question, dict) else None
    source_path = binding.get("source_run_path") if isinstance(binding, dict) else None
    if not isinstance(question_path, str) or not isinstance(source_path, str):
        raise CoordinatorError("expanded import binding lacks exact source/question paths")
    rebuilt_binding, rebuilt_packet, _observations, _expansion, target = _reconstruct_expanded_prepare(
        repo, db, source_path, os.fspath(expansion), question_path, obligations_file, os.fspath(run), allow_partial=True)
    if os.fspath(target) != os.fspath(_canonical_target_path(os.fspath(run))):
        raise CoordinatorError("expanded target path differs from its canonical bound path")
    if _bytes(packet) != _bytes(rebuilt_packet) or _bytes(binding) != _bytes(rebuilt_binding):
        raise CoordinatorError("expanded packet or binding differs from independent P2a reconstruction")
    names = {item.name for item in run.iterdir()}
    allowed = {"selection-packet.json", "candidate-observations.json", "selection.json", "answer-packet.json",
               "evidence-gap.json", "review.json", "answer-review-packet.json", "review-result.json",
               "correction-packet.json", "corrected-answer-packet.json", "corrected-review.json", "accepted-package.json"}
    if not {"selection-packet.json", "candidate-observations.json"}.issubset(names):
        raise CoordinatorError("expanded selection target is incomplete; packet and observations are required")
    if names - allowed:
        raise CoordinatorError(f"expanded run contains unsupported later-stage artifacts: {sorted(names - allowed)!r}")
    for artifact in run.iterdir():
        try:
            mode = artifact.lstat().st_mode
        except OSError as exc:
            raise CoordinatorError(f"expanded artifact cannot be inspected without following links: {artifact.name}: {exc}") from exc
        if not stat.S_ISREG(mode):
            raise CoordinatorError(f"expanded artifact must be a no-follow regular file: {artifact.name}")
    if (run / "selection.json").exists():
        saved = _read_artifact(run, "selection.json")
        record = saved.get("selection_record")
        if not isinstance(record, dict):
            raise CoordinatorError("expanded saved selection record is malformed")
        checked = _validate_selection(packet, record)
        authority = _check_expanded_selection_support(packet, record)
        chosen = {candidate["route"]["id"]: candidate for candidate in checked["accepted"]}
        expected_selection = {"schema_version": 1, "selection_packet_sha256": packet["packet_sha256"],
            "selection_record": record,
            "selected_candidates": [{"route_fact_id": route_id, "overlay_id": chosen[route_id]["provenance"]["overlay_id"],
                "binding_hash": chosen[route_id]["provenance"]["binding_hash"],
                "association_review_hash": chosen[route_id]["provenance"]["association_review_hash"],
                "review_receipt_hash": chosen[route_id]["provenance"]["flow_review_receipt"]["receipt_hash"]}
                for route_id in sorted(chosen)], "obligation_status": checked["obligations"],
            "supplemental_selection_authority": authority}
        if _bytes(saved) != _bytes(expected_selection):
            raise CoordinatorError("expanded selection authority or selected-map provenance differs from exact reconstruction")
        absent = [item for item in record["obligation_reviews"] if item["candidate_status"] == "absent_from_candidates"]
        if (run / "answer-packet.json").exists() and (run / "evidence-gap.json").exists():
            raise CoordinatorError("expanded evidence gap cannot coexist with an answer packet")
        partial_packet = _build_expanded_answer_packet(packet, expected_selection, _selected_union(packet, checked["accepted"]))
        if (run / "answer-packet.json").exists():
            if absent:
                raise CoordinatorError("expanded answer packet cannot exist while an ordinary obligation remains absent")
            if _bytes(_read_artifact(run, "answer-packet.json")) != _bytes(partial_packet):
                raise CoordinatorError("expanded answer packet does not reconstruct from selected maps and supplemental joins")
        if (run / "evidence-gap.json").exists():
            if not absent:
                raise CoordinatorError("expanded evidence-gap artifact has no absent ordinary obligation")
            expected_gap = _expanded_evidence_gap(packet, expected_selection, partial_packet)
            if _bytes(_read_artifact(run, "evidence-gap.json")) != _bytes(expected_gap):
                raise CoordinatorError("expanded evidence-gap artifact does not reconstruct from exact lineage, selection, and supplemental partial evidence")
        elif not absent and (run / "evidence-gap.json").exists():
            raise CoordinatorError("expanded evidence-gap artifact is inconsistent with complete ordinary selection coverage")
    elif (run / "answer-packet.json").exists():
        raise CoordinatorError("expanded answer packet cannot exist without its validated selection")
    elif (run / "evidence-gap.json").exists():
        raise CoordinatorError("expanded evidence-gap artifact cannot exist without its validated selection")
    # Enforce the stage dependency graph. An expanded selection gap is terminal for
    # answer work; answer artifacts may only follow a complete selected packet.
    names = {item.name for item in run.iterdir()}
    if (run / "evidence-gap.json").exists() and names & {
            "answer-packet.json", "review.json", "answer-review-packet.json", "review-result.json",
            "correction-packet.json", "corrected-answer-packet.json", "corrected-review.json", "accepted-package.json"}:
        raise CoordinatorError("expanded evidence-gap terminal cannot enter answer, review, correction, or acceptance stages")
    if names & (allowed - {"selection-packet.json", "candidate-observations.json", "selection.json", "answer-packet.json", "evidence-gap.json"}):
        if not (run / "answer-packet.json").exists() or not (run / "selection.json").exists():
            raise CoordinatorError("expanded answer lifecycle artifact has impossible missing selection or answer-packet dependency")
        if (run / "evidence-gap.json").exists():
            raise CoordinatorError("expanded answer lifecycle cannot coexist with evidence-gap terminal")
    if (run / "answer-packet.json").exists():
        if not (run / "selection.json").exists():
            raise CoordinatorError("expanded answer packet exists without selection")
        answer_packet = _read_artifact(run, "answer-packet.json")
        # Every later artifact is independently rebuilt from the exact expanded answer
        # evidence and the ordinary code-owned schemas.
        if (run / "review.json").exists():
            review_packet = _read_artifact(run, "review.json")
            answer_value = review_packet.get("answer")
            if not isinstance(answer_value, dict) or not isinstance(answer_value.get("answer"), str):
                raise CoordinatorError("expanded round-zero review packet does not preserve a structured answer")
            _validate_answer(answer_packet, answer_value["answer"].encode("utf-8"), answer_value)
            rebuilt = _make_answer_review_packet(answer_packet, answer_value, answer_value["answer"].encode("utf-8"), 0)
            if _bytes(rebuilt) != _bytes(review_packet):
                raise CoordinatorError("expanded round-zero review packet does not preserve exact answer evidence and authority")
        if (run / "answer-review-packet.json").exists():
            if not (run / "review.json").exists() or _bytes(_read_artifact(run, "answer-review-packet.json")) != _bytes(_read_artifact(run, "review.json")):
                raise CoordinatorError("expanded answer-review packet is missing or differs from its round-zero packet")
        if (run / "review-result.json").exists():
            if not (run / "answer-review-packet.json").exists():
                raise CoordinatorError("expanded review result exists without its review packet")
            _validate_review(_read_artifact(run, "answer-review-packet.json"), _read_artifact(run, "review-result.json"),
                             _read_artifact(run, "selection.json"))
        if (run / "correction-packet.json").exists():
            if not (run / "review-result.json").exists() or not (run / "answer-review-packet.json").exists():
                raise CoordinatorError("expanded correction packet exists without its rejected round-zero review")
            correction = _read_artifact(run, "correction-packet.json")
            rejected = _read_artifact(run, "review-result.json")
            review_packet = _read_artifact(run, "answer-review-packet.json")
            expected = _expanded_correction_packet(answer_packet, review_packet, rejected)
            if _bytes(correction) != _bytes(expected):
                raise CoordinatorError("expanded correction packet does not preserve exact expanded evidence and rejection lineage")
        if (run / "corrected-answer-packet.json").exists():
            if not (run / "correction-packet.json").exists():
                raise CoordinatorError("expanded corrected review packet exists without its correction packet")
            correction = _read_artifact(run, "correction-packet.json")
            corrected = _read_artifact(run, "corrected-answer-packet.json")
            value = corrected.get("answer")
            if not isinstance(value, dict) or corrected.get("review_contract") != _review_schema_contract(corrected["obligations"]):
                raise CoordinatorError("expanded corrected answer packet is malformed")
            _validate_answer(correction, str(value.get("answer", "")).encode("utf-8"), value)
            rebuilt = _make_answer_review_packet(correction, value, value["answer"].encode("utf-8"), 1)
            if _bytes(rebuilt) != _bytes(corrected):
                raise CoordinatorError("expanded corrected answer packet does not reconstruct from preserved evidence")
        if (run / "corrected-review.json").exists():
            if not (run / "corrected-answer-packet.json").exists() or not (run / "review-result.json").exists():
                raise CoordinatorError("expanded corrected review exists without corrected packet and first review")
            _validate_review(_read_artifact(run, "corrected-answer-packet.json"), _read_artifact(run, "corrected-review.json"),
                _read_artifact(run, "selection.json"), previous_reviewer_identity=str(_read_artifact(run, "review-result.json").get("reviewer_identity", "")))
        if (run / "accepted-package.json").exists():
            corrected_terminal = (run / "corrected-review.json").exists()
            review_packet = _read_artifact(run, "corrected-answer-packet.json" if corrected_terminal else "answer-review-packet.json")
            review_record = _read_artifact(run, "corrected-review.json" if corrected_terminal else "review-result.json")
            final = _accepted_package(run, answer_packet, review_packet, review_record, corrected_terminal)
            if _bytes(final) != _read_regular_bytes(run / "accepted-package.json", "expanded accepted package"):
                raise CoordinatorError("expanded accepted package does not reconstruct from the exact question, answer, review, and lineage")
    return packet


def expand_gap_import_prepare(repo: str, db: str, source_run_dir: str, expansion_run_dir: str,
                              target_run_dir: str, question_file: str, obligations_file: str
                              ) -> dict[str, object]:
    # Build and validate every input before the first filesystem write.
    binding, packet, observations, expansion, target = _build_expansion_import_state(repo, db,
        source_run_dir, expansion_run_dir, question_file, obligations_file, target_run_dir)
    entries = {item.name for item in target.iterdir()} if target.exists() else set()
    if entries - {"selection-packet.json", "candidate-observations.json"}:
        raise CoordinatorError("target run contains unrelated artifacts; expanded prepare requires a fresh target")
    packet_path = target / "selection-packet.json"
    if packet_path.exists() or packet_path.is_symlink():
        if _read_regular_bytes(packet_path, "expanded target selection packet") != _bytes(packet):
            raise CoordinatorError("existing target selection packet conflicts with expanded prepare")
    observation_path = target / "candidate-observations.json"
    if observation_path.exists() or observation_path.is_symlink():
        saved_observations = _validate_candidate_observations(_read_artifact(target, "candidate-observations.json"), packet)
        if _bytes(_observation_projection(saved_observations)) != _bytes(_observation_projection(observations)):
            raise CoordinatorError("existing target observations conflict with expanded prepare")
    binding_path = expansion / EXPANSION_IMPORT_BINDING
    if binding_path.exists() or binding_path.is_symlink():
        saved = _read_artifact(expansion, EXPANSION_IMPORT_BINDING)
        _validate_expansion_import_binding_schema(saved)
        if _bytes(saved) != _bytes(binding):
            raise CoordinatorError("expansion run is already bound to a different target or import state")
    target.mkdir(parents=True, exist_ok=True)
    _save_immutable(binding_path, binding)
    _save_immutable(target / "selection-packet.json", packet)
    if not observation_path.exists():
        _save_immutable(observation_path, observations)
    return {"result": "expanded_packet_prepared", "state": "expanded_packet_prepared",
        "target_run_dir": os.fspath(target), "binding_sha256": binding["binding_sha256"],
        "packet_sha256": packet["packet_sha256"], "semantic_sha256": packet["semantic_sha256"],
        "candidate_count": len(packet["candidates"]), "supplemental_record_count": len(packet["supplemental_evidence"]["records"])}


def expand_gap_import_status(repo: str, db: str, source_run_dir: str, expansion_run_dir: str,
                             target_run_dir: str, question_file: str, obligations_file: str) -> dict[str, object]:
    binding, packet, observations, _expansion, target = _reconstruct_expanded_prepare(repo, db,
        source_run_dir, expansion_run_dir, question_file, obligations_file, target_run_dir, allow_partial=False)
    return {"state": "expanded_packet_prepared", "binding_sha256": binding["binding_sha256"],
        "packet_sha256": packet["packet_sha256"], "semantic_sha256": packet["semantic_sha256"],
        "observations_sha256": observations["observations_sha256"],
        "candidate_count": len(packet["candidates"]),
        "supplemental_record_count": len(packet["supplemental_evidence"]["records"])}


def expand_gap_selector_view(repo: str, db: str, run_dir: str, obligations_file: str,
                             expansion_run_dir: str) -> dict[str, object]:
    packet = _revalidate(Path(run_dir), repo, db, obligations_file, expansion_run_dir)
    if "expansion_binding_lineage" not in packet:
        raise CoordinatorError("expand-gap-selector-view requires an expansion-aware prepared packet")
    return _expansion_selector_view(packet)


def _validate_selection(packet: dict[str, object], selection: object) -> dict[str, object]:
    schema = SELECTION_RECORD_SCHEMA
    if not isinstance(selection, dict) or set(selection) != set(schema["top_level_fields"]):
        raise CoordinatorError("selection record must contain the exact advertised top-level fields")
    if selection.get("selection_schema_version") != schema["version"] or selection.get("packet_sha256") != packet.get("packet_sha256"):
        raise CoordinatorError("selection record schema or packet hash does not match the exact selection packet")
    for key in ("reviewer_identity", "reviewer_model"):
        atlas._answer_nonempty(selection.get(key), f"selection {key}")
    if selection["reviewer_model"] != "GPT-6.1 Sol High":
        raise CoordinatorError("selection record reviewer_model must be GPT-6.1 Sol High")
    candidates = packet["candidates"]
    expected = {item["route"]["id"]: item for item in candidates}
    required_route_keys = set(packet["required_routes"])
    reviews = selection.get("candidate_reviews")
    if not isinstance(reviews, list) or len(reviews) != len(expected):
        raise CoordinatorError("selection must account for every candidate exactly once")
    accepted = []
    seen = set()
    for index, item in enumerate(reviews):
        if not isinstance(item, dict) or set(item) != set(schema["candidate_fields"]):
            raise CoordinatorError("each candidate review must contain route_fact_id, decision, and basis")
        route_id = item.get("route_fact_id")
        required_route_id = candidates[index]["route"]["id"]
        if route_id != required_route_id:
            raise CoordinatorError(f"selection candidate {index + 1} must account for route_fact_id {required_route_id} in packet order")
        if route_id not in expected or route_id in seen:
            raise CoordinatorError(f"selection candidate is missing, unknown, or duplicated: {route_id!r}")
        seen.add(route_id)
        if item.get("decision") not in set(schema["candidate_decisions"]):
            raise CoordinatorError(f"candidate {route_id} decision must be accept or reject")
        atlas._answer_nonempty(item.get("basis"), f"candidate {route_id} basis", 20)
        if item["decision"] == "accept":
            accepted.append(expected[route_id])
        else:
            route_literal = expected[route_id]["route"].get("route_literal")
            route_key = _route_key(route_literal)
            if route_key in required_route_keys:
                raise CoordinatorError(f"selection error: required route {route_key!r} represented by candidate {route_id} / {route_literal!r} was rejected; accept it or correct the independent selection")
    if not accepted:
        raise CoordinatorError("selection must accept at least one map candidate")
    selected_route_keys = {_route_key(candidate["route"].get("route_literal")) for candidate in accepted}
    missing_selected_routes = sorted(required_route_keys - selected_route_keys)
    if missing_selected_routes:
        raise CoordinatorError(f"selection omitted required route key(s) {missing_selected_routes!r}; required routes must each be accepted independently of obligation supporter lists")
    obligation_ids = _obligation_ids(packet["obligations"])
    obligation_reviews = selection.get("obligation_reviews")
    if not isinstance(obligation_reviews, list) or len(obligation_reviews) != len(obligation_ids):
        raise CoordinatorError("selection must account for every frozen behavior, comparison, and limit exactly once")
    obligations = {}
    for index, item in enumerate(obligation_reviews):
        if not isinstance(item, dict) or set(item) != set(schema["obligation_fields"]) or item.get("obligation_id") != obligation_ids[index]:
            raise CoordinatorError(f"obligation review {index + 1} must name {obligation_ids[index]} in packet order")
        if item.get("candidate_status") not in set(schema["candidate_statuses"]):
            raise CoordinatorError(f"obligation {obligation_ids[index]} status must be present_in_candidates or absent_from_candidates")
        atlas._answer_nonempty(item.get("basis"), f"obligation {obligation_ids[index]} basis", 20)
        supporters = item.get("supporting_route_fact_ids")
        candidate_ids = set(expected)
        if (not isinstance(supporters, list) or len(set(supporters)) != len(supporters)
                or any(route_id not in candidate_ids for route_id in supporters)):
            raise CoordinatorError(f"obligation {obligation_ids[index]} supporting_route_fact_ids must be unique candidate IDs")
        if item["candidate_status"] == "present_in_candidates" and not supporters:
            raise CoordinatorError(f"obligation {obligation_ids[index]} is present but names no supporting candidate")
        if item["candidate_status"] == "absent_from_candidates" and supporters:
            raise CoordinatorError(f"selection error: obligation {obligation_ids[index]} is absent but candidate {supporters[0]} was named as supporting; accept that candidate or correct the selection")
        rejected_supporters = [route_id for route_id in supporters
                               if next(review for review in reviews if review["route_fact_id"] == route_id)["decision"] == "reject"]
        if rejected_supporters:
            raise CoordinatorError(f"selection error: required fact {obligation_ids[index]} is supported by rejected candidate(s) {rejected_supporters}; accept each supporting candidate or correct the independent selection")
        obligations[item["obligation_id"]] = item["candidate_status"]
    return {"accepted": accepted, "obligations": obligations, "validated": selection}


def _selected_union(packet: dict[str, object], accepted: list[dict[str, object]]) -> dict[str, object]:
    anchors: dict[tuple[str, str], dict[str, object]] = {}
    snippets: dict[tuple[str, str, str], dict[str, object]] = {}
    records = []
    for candidate in sorted(accepted, key=lambda c: str(c["route"]["id"])):
        route_id = str(candidate["route"]["id"])
        focus = candidate["map"]
        source_map = {a["source_id"]: (a["path"], a["sha256"]) for a in focus["source_anchors"]}
        snippet_remap = {}
        for snippet in focus["source_snippets"]:
            path, sha = source_map[snippet["source_id"]]
            key = (path, sha, _bytes(snippet["span"]).decode("ascii"))
            snippet_id = "snippet-" + hashlib.sha256(_bytes(list(key))).hexdigest()
            snippet_value = {"snippet_id": snippet_id, "span": snippet["span"], "text": snippet["text"], "path": path, "sha256": sha}
            prior = snippets.setdefault(key, snippet_value)
            if prior["text"] != snippet_value["text"]:
                raise CoordinatorError(f"same source path/hash/span has conflicting snippet text: {path} {snippet['span']}")
            snippet_remap[snippet["snippet_id"]] = snippet_id
            anchors[(path, sha)] = {"path": path, "sha256": sha}
        for index, claim in enumerate(focus["claims"], 1):
            citations = []
            for evidence in claim["evidence"]:
                path, sha = source_map[evidence["source_id"]]
                citations.append({"fact_id": evidence["fact_id"], "path": path, "sha256": sha,
                                  "span": evidence["span"], "snippet_id": snippet_remap[evidence["snippet_id"]]})
            records.append({"claim_number": len(records) + 1, "claim": claim["claim"], "citations": citations,
                            "provenance": {"route_fact_id": route_id, "overlay_id": candidate["provenance"]["overlay_id"],
                                           "map_claim_number": index, "map_claim": claim["claim"],
                                           "map_citations": claim["evidence"], "review_receipt_hash": candidate["provenance"]["flow_review_receipt"]["receipt_hash"],
                                           "binding_hash": candidate["provenance"]["binding_hash"],
                                           "association_review_hash": candidate["provenance"]["association_review_hash"]}})
    anchor_items = [{"source_id": f"source-{i}", "path": path, "sha256": sha}
                    for i, (path, sha) in enumerate(sorted(anchors, key=lambda k: (os.fsencode(k[0]), k[1])), 1)]
    source_by_key = {(item["path"], item["sha256"]): item["source_id"] for item in anchor_items}
    snippet_items = []
    for (_path, _sha, _span), item in sorted(snippets.items(), key=lambda kv: (os.fsencode(kv[0][0]), kv[0][1], kv[0][2])):
        snippet_items.append({"snippet_id": item["snippet_id"], "source_id": source_by_key[(item["path"], item["sha256"])],
                              "span": item["span"], "text": item["text"]})
    union_snippet = {item["snippet_id"]: item for item in snippet_items}
    claims = []
    for claim in records:
        mapped = []
        for cite in claim["citations"]:
            source_id = source_by_key[(cite["path"], cite["sha256"])]
            mapped.append({"claim_number": claim["claim_number"], "fact_id": cite["fact_id"], "source_id": source_id,
                           "path": cite["path"], "sha256": cite["sha256"], "span": cite["span"], "snippet_id": cite["snippet_id"]})
            if cite["snippet_id"] not in union_snippet:
                raise CoordinatorError(f"citation remap lost preserved snippet: {cite['snippet_id']}")
        claims.append({"claim_number": claim["claim_number"], "claim": claim["claim"], "evidence": mapped,
                       "provenance": claim["provenance"]})
    return {"claims": claims, "source_anchors": anchor_items, "source_snippets": snippet_items}


def _write_selection(run: Path, repo: str, db: str, selection_file: str, obligations_file: str,
                     expansion_run_dir: str | None = None) -> dict[str, object]:
    packet = _revalidate(run, repo, db, obligations_file, expansion_run_dir)
    selection = _read(Path(selection_file), "independent selection")
    checked = _validate_selection(packet, selection)
    expanded = "expansion_binding_lineage" in packet
    supplemental_authority = _check_expanded_selection_support(packet, checked["validated"]) if expanded else None
    union = _selected_union(packet, checked["accepted"])
    absent = [key for key, status in checked["obligations"].items() if status == "absent_from_candidates"]
    if expanded and absent:
        chosen = {candidate["route"]["id"]: candidate for candidate in checked["accepted"]}
        selection_payload = {"schema_version": 1, "selection_packet_sha256": packet["packet_sha256"],
            "selection_record": checked["validated"], "selected_candidates": [
                {"route_fact_id": route_id, "overlay_id": chosen[route_id]["provenance"]["overlay_id"],
                 "binding_hash": chosen[route_id]["provenance"]["binding_hash"],
                 "association_review_hash": chosen[route_id]["provenance"]["association_review_hash"],
                 "review_receipt_hash": chosen[route_id]["provenance"]["flow_review_receipt"]["receipt_hash"]}
                for route_id in sorted(chosen)], "obligation_status": checked["obligations"],
            "supplemental_selection_authority": supplemental_authority}
        partial_packet = _build_expanded_answer_packet(packet, selection_payload, union)
        gap = _expanded_evidence_gap(packet, selection_payload, partial_packet)
        _save_immutable(run / "selection.json", selection_payload)
        _save_immutable(run / "evidence-gap.json", gap)
        return {"result": "evidence_gap", "state": "evidence_gap", "package_sha256": gap["package_sha256"],
            "selection_packet_sha256": packet["packet_sha256"], "semantic_sha256": packet["semantic_sha256"],
            "absent_obligations": [item["obligation_id"] for item in gap["absent_obligations"]],
            "selected_map_count": len(chosen), "supplemental_claim_count": len(partial_packet["claims"]) - len(union["claims"])}
    if absent:
        gap = {"schema_version": 1, "result": "evidence_gap", "question": packet["question"],
               "packet_sha256": packet["packet_sha256"], "semantic_sha256": packet["semantic_sha256"],
               "required_routes": packet["required_routes"], "obligations": packet["obligations"],
               "supported_partial_coverage": {"claims": union["claims"], "source_anchors": union["source_anchors"],
                                               "source_snippets": union["source_snippets"]},
               "absent_obligations": [item for item in checked["validated"]["obligation_reviews"]
                                       if item["candidate_status"] == "absent_from_candidates"],
               "selection_record": checked["validated"],
               "selected_route_fact_ids": sorted(candidate["route"]["id"] for candidate in checked["accepted"]),
               "completeness_claim": False,
               "reviewer": {"identity": selection["reviewer_identity"], "model": selection["reviewer_model"]}}
        gap["package_sha256"] = _digest(gap)
        _save_immutable(run / "evidence-gap.json", gap)
        return gap
    chosen = {c["route"]["id"]: c for c in checked["accepted"]}
    selection_payload = {"schema_version": 1, "selection_packet_sha256": packet["packet_sha256"],
                         "selection_record": checked["validated"], "selected_candidates": [
                             {"route_fact_id": route_id, "overlay_id": chosen[route_id]["provenance"]["overlay_id"],
                              "binding_hash": chosen[route_id]["provenance"]["binding_hash"],
                              "association_review_hash": chosen[route_id]["provenance"]["association_review_hash"],
                              "review_receipt_hash": chosen[route_id]["provenance"]["flow_review_receipt"]["receipt_hash"]}
                             for route_id in sorted(chosen)],
                         "obligation_status": checked["obligations"]}
    if expanded:
        selection_payload["supplemental_selection_authority"] = supplemental_authority
        union_packet = _build_expanded_answer_packet(packet, selection_payload, union)
    else:
        union_packet = {"answer_schema_version": 1, "packet_type": "multi_map_answer", "question": packet["question"],
                        "question_sha256": packet["question_sha256"], "controller_type_id": packet["identity"]["controller_type_id"],
                        "obligation_id": packet["obligation_id"],
                        "snapshot_id": packet["identity"]["snapshot_id"], "extractor_identity": packet["identity"]["extractor_identity"],
                        "selection": selection_payload, "required_routes": packet["required_routes"],
                        "obligations": packet["obligations"], **union}
        union_packet["answer_contract"] = _answer_contract(union_packet)
        union_packet["semantic_sha256"] = _digest({k: v for k, v in union_packet.items() if k != "semantic_sha256"})
    _save_immutable(run / "selection.json", selection_payload)
    _save_immutable(run / "answer-packet.json", union_packet)
    return {"result": "selected", "selected_map_count": len(chosen), "claim_count": len(union_packet["claims"]),
            "packet_sha256": union_packet["semantic_sha256"]}


def _answer_contract(packet: dict[str, object]) -> dict[str, object]:
    contract = _answer_schema_contract()
    contract["fields"]["question_id"]["exact"] = packet.get("obligation_id")
    contract["fields"]["answer"]["exact"] = "draft-file UTF-8 text"
    return contract


def _expanded_claim_requirements(claims: object, authority: object) -> dict[str, list[int]]:
    """Derive required supplemental answer claims from bound selection joins."""
    if not isinstance(claims, list) or not isinstance(authority, dict):
        raise CoordinatorError("expanded answer lacks claims or supplemental selection authority")
    obligations = authority.get("obligations")
    if not isinstance(obligations, list):
        raise CoordinatorError("expanded supplemental selection authority has no ordered obligations")
    joined: dict[str, set[tuple[str, str, str, str, str]]] = {}
    for item in obligations:
        if not isinstance(item, dict) or not isinstance(item.get("obligation_id"), str) or not isinstance(item.get("joins"), list):
            raise CoordinatorError("expanded supplemental authority obligation is malformed")
        expected = set()
        for join in item["joins"]:
            if not isinstance(join, dict):
                raise CoordinatorError("expanded supplemental authority join is malformed")
            expected.add((str(join.get("candidate_id")), str(join.get("use_id")), str(join.get("route_fact_id")),
                          str(join.get("owner_fact_id")), str(join.get("sha256"))))
        joined[item["obligation_id"]] = expected
    result = {key: [] for key in joined}
    seen: set[tuple[str, str, str, str, str]] = set()
    for claim in claims:
        if not isinstance(claim, dict) or not isinstance(claim.get("provenance"), dict):
            continue
        provenance = claim["provenance"]
        if provenance.get("evidence_kind") != "supplemental_declaration":
            continue
        oid = provenance.get("obligation_id")
        key = (str(provenance.get("candidate_id")), str(provenance.get("use_id")),
               str(provenance.get("route_fact_id")), str(provenance.get("owner_fact_id")),
               str((claim.get("evidence") or [{}])[0].get("sha256")))
        if oid not in joined or key not in joined[oid]:
            raise CoordinatorError("supplemental answer claim is not joined to exact selected expansion authority")
        result[oid].append(claim.get("claim_number"))
        seen.add(key)
    if any(not numbers for numbers in result.values()):
        raise CoordinatorError("expanded authority obligation has no corresponding supplemental declaration claim")
    for oid, expected in joined.items():
        if not expected.issubset(seen):
            raise CoordinatorError(f"supplemental answer omits one or more bound declarations for {oid}")
    return result


def _expanded_review_contract(packet: dict[str, object]) -> dict[str, object]:
    authority = packet.get("supplemental_selection_authority")
    lineage = packet.get("expansion_provenance")
    required = _expanded_claim_requirements(packet.get("claims"), authority)
    flags = packet.get("historical_answer_authority_flags")
    if flags != {"current_answer_authority": False, "full_question_completeness": False, "completeness_claim": False}:
        raise CoordinatorError("expanded review must preserve all historical false answer-authority and completeness flags")
    return {"contract_schema_version": 1, "kind": "expanded_answer_review_supplement",
        "evidence_packet_sha256": packet.get("evidence_packet_sha256"),
        "expansion_packet_sha256": (lineage or {}).get("packet_sha256") if isinstance(lineage, dict) else None,
        "expansion_review_sha256": (lineage or {}).get("review_sha256") if isinstance(lineage, dict) else None,
        "expansion_package_sha256": (lineage or {}).get("package_sha256") if isinstance(lineage, dict) else None,
        "expansion_binding_sha256": (lineage or {}).get("binding_sha256") if isinstance(lineage, dict) else None,
        "supplemental_selection_authority": authority,
        "historical_answer_authority_flags": packet.get("historical_answer_authority_flags"),
        "mandatory_supplemental_claims_by_obligation": required,
        "acceptance_rule": "Every mandatory supplemental claim must be cited by at least one structured material claim and receive covered claim disposition; every frozen obligation must be covered and unsupported assertions empty. Otherwise classify answer_gap, eligible for the single existing correction.",
        "authority_boundary": "This review covers this exact question, answer, and reviewed expansion evidence only. It does not establish full-question completeness, compiler/runtime binding, or acceptance."}


def _expanded_correction_packet(answer_packet: dict[str, object], review_packet: dict[str, object],
                                rejected: dict[str, object]) -> dict[str, object]:
    if rejected.get("decision") != "rejected" or rejected.get("failure_kind") != "answer_gap":
        raise CoordinatorError("expanded correction requires a rejected first review with failure_kind answer_gap")
    expected = {"schema_version": 1, "packet_type": "multi_map_correction", "result": "correction_required",
        "original_packet_sha256": answer_packet["semantic_sha256"], "semantic_sha256": answer_packet["semantic_sha256"],
        "question_sha256": answer_packet["question_sha256"], "obligation_id": answer_packet["obligation_id"],
        "required_routes": review_packet["required_routes"], "rejected_review_sha256": _digest(rejected),
        "correction_round": 1, "max_corrections": 1, "question": review_packet["question"],
        "obligations": review_packet["obligations"], "claims": review_packet["claims"],
        "source_anchors": review_packet["source_anchors"], "source_snippets": review_packet["source_snippets"],
        "rejection_reasons": {"claim_reviews": rejected["claim_reviews"], "obligation_reviews": rejected["obligation_reviews"],
                              "unsupported_assertions": rejected["unsupported_assertions"]},
        "supplemental_selection_authority": answer_packet["selection"]["supplemental_selection_authority"],
        "expansion_provenance": answer_packet["expansion_provenance"]}
    expected["historical_answer_authority_flags"] = {key: answer_packet[key] for key in
        ("current_answer_authority", "full_question_completeness", "completeness_claim")}
    expected["packet_sha256"] = _digest(expected)
    return expected


def _validate_answer(packet: dict[str, object], draft_raw: bytes, answer: object) -> dict[str, object]:
    schema = ANSWER_RECORD_SCHEMA
    if not isinstance(answer, dict) or set(answer) != set(schema["top_level_fields"]):
        raise CoordinatorError("answer must contain exactly question_id, answer, material_claims, limitations, evidence_measurement")
    if answer.get("question_id") != packet.get("obligation_id"):
        raise CoordinatorError("answer question_id does not match the frozen obligation identity")
    try:
        draft = draft_raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CoordinatorError("answer draft must be UTF-8") from exc
    if answer.get("answer") != draft:
        raise CoordinatorError("structured answer.answer must exactly equal draft bytes decoded as UTF-8")
    if answer.get("evidence_measurement") != {}:
        raise CoordinatorError("worker evidence_measurement must be exactly {}; Atlas computes it")
    claims = answer.get("material_claims")
    if not isinstance(claims, list) or not claims:
        raise CoordinatorError("material_claims must be a nonempty list")
    packet_claims = packet["claims"]
    by_num = {item["claim_number"]: item for item in packet_claims}
    anchors = {item["source_id"]: item for item in packet["source_anchors"]}
    snippets = {item["snippet_id"]: item for item in packet["source_snippets"]}
    for index, item in enumerate(claims):
        if not isinstance(item, dict) or set(item) != set(schema["material_claim_fields"]):
            raise CoordinatorError(f"material_claims[{index}] must contain assertion, claim_numbers, and citations")
        atlas._answer_nonempty(item.get("assertion"), f"material_claims[{index}].assertion", 8)
        if "\n" in item["assertion"] or ";" in item["assertion"] or len(item["assertion"].split(". ")) > 1:
            raise CoordinatorError(f"material_claims[{index}].assertion observed {item['assertion']!r}; required one atomic sentence without a newline, semicolon, or second sentence")
        numbers = item.get("claim_numbers")
        citations = item.get("citations")
        if not isinstance(numbers, list) or not numbers or not isinstance(citations, list) or not citations:
            raise CoordinatorError(f"material_claims[{index}] requires claim_numbers and citations")
        if len(set(numbers)) != len(numbers) or any(type(n) is not int or n not in by_num for n in numbers):
            raise CoordinatorError(f"material_claims[{index}] references invalid or repeated union claim numbers")
        cited = set()
        for citation in citations:
            required = set(schema["citation_fields"])
            if not isinstance(citation, dict) or set(citation) != required:
                raise CoordinatorError(f"material_claims[{index}] citation fields do not match the union contract")
            n = citation["claim_number"]
            if type(n) is not int or n not in numbers:
                raise CoordinatorError(f"material_claims[{index}] citation claim number is outside claim_numbers")
            claim = by_num[n]
            matches = [cite for cite in claim["evidence"] if cite["fact_id"] == citation["fact_id"]
                       and cite["source_id"] == citation["source_id"]
                       and cite["path"] == citation["path"] and cite["sha256"] == citation["sha256"]
                       and cite["span"] == citation["span"] and cite["snippet_id"] == citation["snippet_id"]]
            if not matches or citation["snippet_id"] not in snippets:
                raise CoordinatorError(f"material_claims[{index}] citation does not resolve into the exact union evidence")
            anchor = next((a for a in packet["source_anchors"] if a["path"] == citation["path"] and a["sha256"] == citation["sha256"]), None)
            if anchor is None or anchors.get(anchor["source_id"]) != anchor:
                raise CoordinatorError(f"material_claims[{index}] citation source anchor is absent or tampered")
            cited.add(n)
        if cited != set(numbers):
            raise CoordinatorError(f"material_claims[{index}] claim_numbers do not match cited claims")
    limitations = answer.get("limitations")
    if not isinstance(limitations, list) or any(not isinstance(v, str) or not v.strip() for v in limitations):
        raise CoordinatorError("limitations must be a list of nonempty strings")
    return answer


def _make_answer_review_packet(packet: dict[str, object], answer: dict[str, object], draft_raw: bytes, round_number: int) -> dict[str, object]:
    evidence = {"claims": packet["claims"], "source_anchors": packet["source_anchors"], "source_snippets": packet["source_snippets"]}
    evidence_bytes = _bytes(evidence)
    measurement = {"measurement_schema_version": 1, "measurement_kind": "canonical_review_evidence",
                   "original_packet_sha256": packet["semantic_sha256"], "canonical_evidence_sha256": hashlib.sha256(evidence_bytes).hexdigest(),
                   "canonical_evidence_bytes": len(evidence_bytes), "unit": "ASCII bytes including one trailing newline",
                   "excluded_claims": list(atlas.EVIDENCE_MEASUREMENT_EXCLUDED_CLAIMS)}
    result = {"review_schema_version": 1, "packet_type": "multi_map_answer_review", "result": "semantic_review_required",
            "round": round_number, "evidence_packet_sha256": packet["semantic_sha256"], "question": packet["question"],
            "required_routes": packet["required_routes"], "obligations": packet["obligations"], "answer": answer, "draft_sha256": hashlib.sha256(draft_raw).hexdigest(),
            "claims": packet["claims"], "source_anchors": packet["source_anchors"], "source_snippets": packet["source_snippets"],
            "evidence_measurement": measurement,
            "review_contract": _review_schema_contract(packet["obligations"]),
            "evidence_measurement_contract": {"value": "Atlas-computed canonical union evidence measurement", "bytes": "ASCII canonical JSON for claims/source_anchors/source_snippets plus trailing newline", "scope": "evidence content only; not model consumption, retrieval stdout, time, or provider tokens"}}
    authority = packet.get("supplemental_selection_authority")
    lineage = packet.get("expansion_provenance")
    if authority is None and isinstance(packet.get("selection"), dict):
        authority = packet["selection"].get("supplemental_selection_authority")
    if lineage is None and isinstance(packet.get("expansion_provenance"), dict):
        lineage = packet.get("expansion_provenance")
    if isinstance(authority, dict) and isinstance(lineage, dict):
        result["supplemental_selection_authority"] = authority
        result["expansion_provenance"] = lineage
        result["historical_answer_authority_flags"] = (packet.get("historical_answer_authority_flags")
            if isinstance(packet.get("historical_answer_authority_flags"), dict) else
            {key: packet.get(key) for key in ("current_answer_authority", "full_question_completeness", "completeness_claim")})
        result["expanded_review_contract"] = _expanded_review_contract(result)
    if round_number == 1:
        result["correction_lineage"] = {"correction_packet_sha256": packet["packet_sha256"],
                                        "original_packet_sha256": packet["original_packet_sha256"],
                                        "rejected_review_sha256": packet["rejected_review_sha256"],
                                        "correction_round": 1, "max_corrections": 1}
    result["packet_sha256"] = _digest(result)
    return result


def submit_answer(run: Path, repo: str, db: str, obligations_file: str, draft_file: str, answer_file: str,
                  correction: bool = False, expansion_run_dir: str | None = None) -> dict[str, object]:
    _revalidate(run, repo, db, obligations_file, expansion_run_dir)
    if (run / "evidence-gap.json").exists():
        raise CoordinatorError("expanded evidence-gap terminal cannot enter answer or correction stages")
    if correction and "expansion_binding_lineage" in _read_artifact(run, "selection-packet.json"):
        if not (run / "review-result.json").exists():
            raise CoordinatorError("expanded correction requires a saved rejected first review with failure_kind answer_gap")
        first_review = _read_artifact(run, "review-result.json")
        if first_review.get("decision") != "rejected" or first_review.get("failure_kind") != "answer_gap":
            raise CoordinatorError("expanded correction requires a rejected first review with failure_kind answer_gap")
        if not (run / "correction-packet.json").exists():
            raise CoordinatorError("expanded rejected answer_gap review lacks its reconstructed correction packet")
    name = "answer-packet.json" if not correction else "correction-packet.json"
    packet = _read_artifact(run, name)
    try:
        draft_raw = Path(draft_file).read_bytes()
    except OSError as exc:
        raise CoordinatorError(f"cannot read answer draft: {exc}") from exc
    answer = _validate_answer(packet, draft_raw, _read(Path(answer_file), "structured answer"))
    out = _make_answer_review_packet(packet, answer, draft_raw, 1 if correction else 0)
    output_name = "corrected-answer-packet.json" if correction else "review.json"
    _save_immutable(run / output_name, out)
    return {"result": "review_required", "round": out["round"], "packet_sha256": out["packet_sha256"],
            "review_packet": output_name, "evidence_measurement": out["evidence_measurement"]}


def _validate_review(review_packet: dict[str, object], review: object, selection: dict[str, object],
                     previous_reviewer_identity: str | None = None) -> dict[str, object]:
    schema = REVIEW_RECORD_SCHEMA
    if not isinstance(review, dict) or set(review) != set(schema["top_level_fields"]):
        raise CoordinatorError("Sol review must contain the exact advertised review fields")
    expected_packet_hash = _digest({key: value for key, value in review_packet.items() if key != "packet_sha256"})
    if review.get("review_schema_version") != schema["version"] or review.get("packet_sha256") != expected_packet_hash:
        raise CoordinatorError("Sol review schema or packet hash is stale")
    for key in ("reviewer_identity", "reviewer_model"):
        atlas._answer_nonempty(review.get(key), f"Sol review {key}")
    if review["reviewer_model"] != "GPT-6.1 Sol High":
        raise CoordinatorError("Sol review reviewer_model must be GPT-6.1 Sol High")
    selection_identity = selection.get("selection_record", {}).get("reviewer_identity") if isinstance(selection.get("selection_record"), dict) else None
    if review["reviewer_identity"] == selection_identity:
        raise CoordinatorError("fresh Sol answer review must use a different reviewer_identity audit label from selection")
    if previous_reviewer_identity is not None and review["reviewer_identity"] == previous_reviewer_identity:
        raise CoordinatorError("corrected answer requires a fresh reviewer_identity audit label different from the round-zero reviewer")
    claims = review_packet["claims"]
    claim_reviews = review.get("claim_reviews")
    if not isinstance(claim_reviews, list) or len(claim_reviews) != len(claims):
        raise CoordinatorError("Sol review must account for every union claim")
    incomplete = False
    for index, item in enumerate(claim_reviews, 1):
        if not isinstance(item, dict) or set(item) != set(schema["claim_fields"]) or item.get("claim_number") != index:
            raise CoordinatorError(f"claim review {index} is missing, duplicated, or out of order")
        if item.get("disposition") not in set(schema["claim_dispositions"]):
            raise CoordinatorError(f"claim {index} disposition is invalid")
        atlas._answer_nonempty(item.get("basis"), f"claim {index} basis", 20)
        incomplete |= item["disposition"] == "incomplete"
    obligations = review_packet["obligations"]
    obligation_ids = _obligation_ids(obligations)
    obligation_reviews = review.get("obligation_reviews")
    if not isinstance(obligation_reviews, list) or len(obligation_reviews) != len(obligation_ids):
        raise CoordinatorError("Sol review must account for every frozen behavior, comparison, and limit")
    gap = False
    for index, item in enumerate(obligation_reviews):
        oid = obligation_ids[index]
        if not isinstance(item, dict) or set(item) != set(schema["obligation_fields"]) or item.get("obligation_id") != oid:
            raise CoordinatorError(f"obligation review {index + 1} must name {oid} in frozen order")
        disposition = item.get("disposition")
        if disposition not in set(schema["obligation_dispositions"]):
            raise CoordinatorError(f"obligation {oid} disposition is invalid")
        atlas._answer_nonempty(item.get("basis"), f"obligation {oid} basis", 20)
        if disposition == "evidence_absent":
            if selection.get("obligation_status", {}).get(oid) != "absent_from_candidates":
                raise CoordinatorError(f"evidence_gap is not permitted for {oid}: complete candidate selection recorded it as present")
            gap = True
        if disposition in {"missing_supported", "contradicted"}:
            incomplete = True
    unsupported = review.get("unsupported_assertions")
    if not isinstance(unsupported, list) or any(not isinstance(v, str) or not v.strip() for v in unsupported):
        raise CoordinatorError("unsupported_assertions must be an array of concrete assertion strings")
    incomplete |= bool(unsupported)
    expanded_contract = review_packet.get("expanded_review_contract")
    if expanded_contract is not None:
        expected_contract = _expanded_review_contract(review_packet)
        if _bytes(expanded_contract) != _bytes(expected_contract):
            raise CoordinatorError("expanded answer-review supplement differs from exact packet authority and evidence")
        requirements = expected_contract["mandatory_supplemental_claims_by_obligation"]
        answer = review_packet.get("answer")
        answer_claims = answer.get("material_claims", []) if isinstance(answer, dict) else []
        cited_numbers = {number for item in answer_claims if isinstance(item, dict)
                         for number in item.get("claim_numbers", []) if type(number) is int}
        review_by_number = {item["claim_number"]: item for item in claim_reviews}
        for oid, mandatory_numbers in requirements.items():
            obligation_review = next(item for item in obligation_reviews if item["obligation_id"] == oid)
            if obligation_review["disposition"] != "covered":
                incomplete = True
            for number in mandatory_numbers:
                item = review_by_number[number]
                cited = number in cited_numbers
                if not cited and item["disposition"] != "incomplete":
                    raise CoordinatorError(f"mandatory supplemental claim {number} for {oid} lacks structured citation and must be reviewed incomplete")
                if cited and item["disposition"] != "covered":
                    incomplete = True
    expected_kind = "evidence_gap" if gap else ("answer_gap" if incomplete else "none")
    if review.get("failure_kind") != expected_kind:
        raise CoordinatorError(f"review failure_kind must be {expected_kind} for its structured dispositions")
    if expected_kind not in set(schema["failure_kinds"]):
        raise CoordinatorError(f"review failure_kind is not part of the authoritative contract: {expected_kind}")
    expected_decision = "accepted" if expected_kind == "none" else "rejected"
    if expected_decision not in set(schema["decisions"]):
        raise CoordinatorError(f"review decision is not part of the authoritative contract: {expected_decision}")
    if review.get("decision") != expected_decision:
        raise CoordinatorError(f"review decision must be {expected_decision} for its structured dispositions")
    return review


def review(run: Path, repo: str, db: str, obligations_file: str, review_file: str, corrected: bool = False,
           expansion_run_dir: str | None = None) -> dict[str, object]:
    _revalidate(run, repo, db, obligations_file, expansion_run_dir)
    if (run / "evidence-gap.json").exists():
        raise CoordinatorError("expanded evidence-gap terminal cannot enter review stages")
    selection = _read_artifact(run, "selection.json")
    packet_name = "corrected-answer-packet.json" if corrected else "review.json"
    packet = _read_artifact(run, packet_name)
    previous_identity = None
    if corrected:
        previous_identity = str(_read_artifact(run, "review-result.json").get("reviewer_identity", ""))
    record = _validate_review(packet, _read(Path(review_file), "independent Sol review"), selection,
                              previous_reviewer_identity=previous_identity)
    output_name = "corrected-review.json" if corrected else "review.json"
    # Round-zero answer review packet is named review.json; preserve it elsewhere before review result.
    if not corrected:
        _save_immutable(run / "answer-review-packet.json", packet)
        output_name = "review-result.json"
    _save_immutable(run / output_name, record)
    if record["failure_kind"] == "evidence_gap":
        answer_packet = _read_artifact(run, "answer-packet.json")
        gap = {"schema_version": 1, "result": "evidence_gap", "question": answer_packet["question"],
               "packet_sha256": answer_packet["semantic_sha256"], "review": record,
               "required_routes": answer_packet["required_routes"], "obligations": answer_packet["obligations"],
               "selection_record": selection["selection_record"],
               "selected_route_fact_ids": [item["route_fact_id"] for item in answer_packet["selection"]["selected_candidates"]],
               "supported_partial_coverage": {"claims": answer_packet["claims"], "source_anchors": answer_packet["source_anchors"],
                                               "source_snippets": answer_packet["source_snippets"]},
               "completeness_claim": False}
        gap["package_sha256"] = _digest(gap)
        _save_immutable(run / "evidence-gap.json", gap)
    elif record["failure_kind"] == "answer_gap" and not corrected:
        answer_packet = _read_artifact(run, "answer-packet.json")
        review_packet = _read_artifact(run, "answer-review-packet.json")
        if "expansion_provenance" in answer_packet:
            correction = _expanded_correction_packet(answer_packet, review_packet, record)
        else:
            correction = {"schema_version": 1, "packet_type": "multi_map_correction", "result": "correction_required",
                      "original_packet_sha256": _read_artifact(run, "answer-packet.json")["semantic_sha256"],
                      "semantic_sha256": _read_artifact(run, "answer-packet.json")["semantic_sha256"],
                      "question_sha256": _read_artifact(run, "answer-packet.json")["question_sha256"],
                      "obligation_id": _read_artifact(run, "answer-packet.json")["obligation_id"],
                      "required_routes": packet["required_routes"],
                      "rejected_review_sha256": _digest(record), "correction_round": 1, "max_corrections": 1,
                      "question": packet["question"], "obligations": packet["obligations"], "claims": packet["claims"],
                      "source_anchors": packet["source_anchors"], "source_snippets": packet["source_snippets"],
                      "rejection_reasons": {"claim_reviews": record["claim_reviews"], "obligation_reviews": record["obligation_reviews"],
                                            "unsupported_assertions": record["unsupported_assertions"]}}
            correction["packet_sha256"] = _digest(correction)
        _save_immutable(run / "correction-packet.json", correction)
    elif record["failure_kind"] == "answer_gap" and corrected:
        return {"result": "terminal_rejection", "reason": "corrected answer remains rejected; second correction is forbidden"}
    return {"result": record["decision"], "failure_kind": record["failure_kind"], "reviewer": record["reviewer_identity"]}


def _accepted_package(run: Path, answer_packet: dict[str, object], packet: dict[str, object],
                      record: dict[str, object], corrected: bool) -> dict[str, object]:
    if record.get("decision") != "accepted":
        raise CoordinatorError("review did not accept the answer")
    if corrected:
        correction = _read_artifact(run, "correction-packet.json")
        if correction.get("correction_round") != 1 or correction.get("max_corrections") != 1:
            raise CoordinatorError("correction lineage is invalid")
    evidence = {"claims": answer_packet["claims"], "source_anchors": answer_packet["source_anchors"], "source_snippets": answer_packet["source_snippets"]}
    measurement_bytes = _bytes(evidence)
    measurement = {"measurement_schema_version": 1, "measurement_kind": "canonical_review_evidence",
                   "original_packet_sha256": answer_packet["semantic_sha256"], "canonical_evidence_sha256": hashlib.sha256(measurement_bytes).hexdigest(),
                   "canonical_evidence_bytes": len(measurement_bytes), "unit": "ASCII bytes including one trailing newline",
                   "excluded_claims": list(atlas.EVIDENCE_MEASUREMENT_EXCLUDED_CLAIMS)}
    answer_value = packet["answer"]
    if not isinstance(answer_value, dict) or not isinstance(answer_value.get("answer"), str):
        raise CoordinatorError("review packet does not preserve the exact structured answer")
    final = {"lifecycle_schema_version": 2, "result": "accepted", "question": answer_packet["question"],
             "question_sha256": answer_packet["question_sha256"], "answer": answer_value["answer"],
             "required_routes": answer_packet["required_routes"], "obligations": answer_packet["obligations"],
             "answer_sha256": hashlib.sha256(answer_value["answer"].encode("utf-8")).hexdigest(),
             "structured_answer": {**answer_value, "evidence_measurement": measurement},
             "provenance": {"snapshot_id": answer_packet["snapshot_id"], "extractor_identity": answer_packet["extractor_identity"],
                            "controller_type_id": answer_packet["controller_type_id"], "selection_packet_sha256": answer_packet["selection"]["selection_packet_sha256"],
                            "selected_maps": answer_packet["selection"]["selected_candidates"]},
             "claims": answer_packet["claims"], "source_anchors": answer_packet["source_anchors"],
             "source_snippets": answer_packet["source_snippets"],
             "review": {"packet_sha256": packet["packet_sha256"], "review_sha256": _digest(record),
                        "reviewer_identity": record["reviewer_identity"], "reviewer_model": record["reviewer_model"]},
             "correction_lineage": None if not corrected else _read_artifact(run, "correction-packet.json")}
    if "expansion_provenance" in answer_packet:
        if (answer_packet.get("current_answer_authority") is not False
                or answer_packet.get("full_question_completeness") is not False
                or answer_packet.get("completeness_claim") is not False):
            raise CoordinatorError("expanded answer acceptance cannot change frozen false answer-authority or completeness flags")
        contract = packet.get("expanded_review_contract")
        expected_contract = _expanded_review_contract(packet)
        if _bytes(contract) != _bytes(expected_contract):
            raise CoordinatorError("expanded accepted answer lacks its exact expansion review contract")
        mandatory = expected_contract["mandatory_supplemental_claims_by_obligation"]
        cited_numbers = {number for item in answer_value.get("material_claims", []) if isinstance(item, dict)
                         for number in item.get("claim_numbers", []) if type(number) is int}
        review_by_number = {item["claim_number"]: item for item in record.get("claim_reviews", [])}
        if any(number not in cited_numbers or review_by_number.get(number, {}).get("disposition") != "covered"
               for numbers in mandatory.values() for number in numbers):
            raise CoordinatorError("expanded acceptance requires every mandatory supplemental claim to be cited and reviewed covered")
        if (record.get("failure_kind") != "none" or record.get("decision") != "accepted"
                or record.get("unsupported_assertions") != []
                or any(item.get("disposition") != "covered" for item in record.get("obligation_reviews", []))):
            raise CoordinatorError("expanded acceptance requires every obligation covered and no unsupported assertions")
        lineage = answer_packet["expansion_provenance"]
        authority = answer_packet["selection"]["supplemental_selection_authority"]
        final["expansion_provenance"] = lineage
        final["supplemental_selection_authority"] = authority
        final["historical_answer_authority_flags"] = {key: answer_packet[key] for key in
            ("current_answer_authority", "full_question_completeness", "completeness_claim")}
        final["expansion_acceptance_boundary"] = {"boundary_schema_version": 1,
            "boundary_kind": "exact_question_answer_review_only", "question_sha256": answer_packet["question_sha256"],
            "answer_evidence_semantic_sha256": answer_packet["semantic_sha256"],
            "review_packet_sha256": packet["packet_sha256"], "review_sha256": _digest(record),
            "expansion_packet_sha256": lineage["packet_sha256"], "expansion_review_sha256": lineage["review_sha256"],
            "expansion_package_sha256": lineage["package_sha256"], "expansion_binding_sha256": lineage["binding_sha256"],
            "supplemental_selection_authority_sha256": authority["authority_sha256"],
            "compiler_runtime_proof": False, "full_question_completeness": False,
            "authority_statement": "Acceptance applies only to this exact question, answer, evidence packet, and semantic review; it does not establish compiler or runtime binding, and does not rewrite the preserved historical false authority flags."}
    final["package_sha256"] = _digest(final)
    return final


def accept(run: Path, repo: str, db: str, obligations_file: str, corrected: bool = False,
           expansion_run_dir: str | None = None) -> dict[str, object]:
    _revalidate(run, repo, db, obligations_file, expansion_run_dir)
    if (run / "evidence-gap.json").exists():
        raise CoordinatorError("expanded evidence-gap terminal cannot enter acceptance stages")
    if corrected:
        packet = _read_artifact(run, "corrected-answer-packet.json")
        record = _read_artifact(run, "corrected-review.json")
        if record.get("decision") != "accepted":
            raise CoordinatorError("corrected answer review did not accept; second correction is forbidden")
    else:
        packet = _read_artifact(run, "answer-review-packet.json")
        record = _read_artifact(run, "review-result.json")
        if record.get("decision") != "accepted":
            raise CoordinatorError("round-zero review did not accept; use one correction or emit the evidence gap")
    answer_packet = _read_artifact(run, "answer-packet.json")
    final = _accepted_package(run, answer_packet, packet, record, corrected)
    _save_immutable(run / "accepted-package.json", final)
    return final


def status(run: Path, repo: str, db: str, obligations_file: str,
           expansion_run_dir: str | None = None) -> dict[str, object]:
    packet = _revalidate(run, repo, db, obligations_file, expansion_run_dir)
    artifacts = sorted(p.name for p in run.iterdir() if p.is_file())
    unexpected = sorted(set(artifacts) - ARTIFACTS)
    if unexpected:
        raise CoordinatorError(f"run contains unregistered stage artifacts: {unexpected}")
    if (run / "accepted-package.json").exists():
        accepted = _read_artifact(run, "accepted-package.json")
        if accepted.get("package_sha256") != _digest({key: value for key, value in accepted.items() if key != "package_sha256"}):
            raise CoordinatorError("accepted package hash does not match canonical content")
    if (run / "evidence-gap.json").exists():
        gap = _read_artifact(run, "evidence-gap.json")
        if gap.get("package_sha256") != _digest({key: value for key, value in gap.items() if key != "package_sha256"}) or gap.get("completeness_claim") is not False:
            raise CoordinatorError("evidence-gap package hash or no-completeness assertion is invalid")
    terminal = "accepted" if (run / "accepted-package.json").exists() else "evidence_gap" if (run / "evidence-gap.json").exists() else "in_progress"
    if "expansion_binding_lineage" in packet and (run / "corrected-review.json").exists():
        if _read_artifact(run, "corrected-review.json").get("decision") == "rejected":
            terminal = "rejected"
    return {"result": "current", "semantic_sha256": packet["semantic_sha256"], "candidate_count": len(packet["candidates"]),
            "artifacts": artifacts, "terminal": terminal}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare")
    p.add_argument("--repo", required=True); p.add_argument("--db", required=True)
    p.add_argument("--question-file", required=True); p.add_argument("--obligations-file", required=True)
    p.add_argument("--controller-type-id", required=True); p.add_argument("--run-dir", required=True)
    p.add_argument("--max-bytes", type=int, default=DEFAULT_LIMIT)
    x = commands.add_parser("expand-gap-prepare", help="reconstruct a selection-stage evidence gap and prepare a local declaration review packet")
    x.add_argument("--repo", required=True); x.add_argument("--db", required=True)
    x.add_argument("--source-run-dir", required=True); x.add_argument("--destination-run-dir", required=True)
    x.add_argument("--obligations-file", required=True); x.add_argument("--max-bytes", type=int, default=10_000_000)
    xr = commands.add_parser("expand-gap-review", help="validate an independent semantic review and save a separate expansion package")
    xr.add_argument("--repo", required=True); xr.add_argument("--db", required=True)
    xr.add_argument("--source-run-dir", required=True); xr.add_argument("--destination-run-dir", required=True)
    xr.add_argument("--obligations-file", required=True); xr.add_argument("--review-file", required=True)
    xs = commands.add_parser("expand-gap-status", help="read-only reconstruction and status for a gap expansion")
    xs.add_argument("--repo", required=True); xs.add_argument("--db", required=True)
    xs.add_argument("--source-run-dir", required=True); xs.add_argument("--destination-run-dir", required=True)
    xs.add_argument("--obligations-file", required=True)
    xp = commands.add_parser("expand-gap-import-prepare", help="prepare a fresh selection packet with reviewed local expansion candidates")
    xp.add_argument("--repo", required=True); xp.add_argument("--db", required=True)
    xp.add_argument("--source-run-dir", required=True); xp.add_argument("--expansion-run-dir", required=True)
    xp.add_argument("--target-run-dir", required=True); xp.add_argument("--question-file", required=True)
    xp.add_argument("--obligations-file", required=True)
    xps = commands.add_parser("expand-gap-import-status", help="read-only reconstruction of an expansion-aware prepared packet")
    xps.add_argument("--repo", required=True); xps.add_argument("--db", required=True)
    xps.add_argument("--source-run-dir", required=True); xps.add_argument("--expansion-run-dir", required=True)
    xps.add_argument("--target-run-dir", required=True); xps.add_argument("--question-file", required=True)
    xps.add_argument("--obligations-file", required=True)
    xv = commands.add_parser("expand-gap-selector-view", help="emit the read-only mandatory support view for an expanded selector")
    xv.add_argument("--repo", required=True); xv.add_argument("--db", required=True); xv.add_argument("--run-dir", required=True)
    xv.add_argument("--obligations-file", required=True); xv.add_argument("--expansion-run-dir", required=True)
    for stage in ("select", "status"):
        s = commands.add_parser(stage); s.add_argument("--repo", required=True); s.add_argument("--db", required=True); s.add_argument("--run-dir", required=True)
        s.add_argument("--obligations-file", required=True)
        s.add_argument("--expansion-run-dir")
        if stage == "select": s.add_argument("--selection-file", required=True)
    for stage in ("answer", "correct"):
        s = commands.add_parser(stage); s.add_argument("--repo", required=True); s.add_argument("--db", required=True); s.add_argument("--run-dir", required=True)
        s.add_argument("--obligations-file", required=True)
        s.add_argument("--expansion-run-dir")
        s.add_argument("--draft-file", required=True); s.add_argument("--answer-file", required=True)
    for stage in ("review", "review-correction"):
        s = commands.add_parser(stage); s.add_argument("--repo", required=True); s.add_argument("--db", required=True); s.add_argument("--run-dir", required=True); s.add_argument("--review-file", required=True)
        s.add_argument("--obligations-file", required=True)
        s.add_argument("--expansion-run-dir")
    for stage in ("accept", "accept-correction"):
        s = commands.add_parser(stage); s.add_argument("--repo", required=True); s.add_argument("--db", required=True); s.add_argument("--run-dir", required=True)
        s.add_argument("--obligations-file", required=True)
        s.add_argument("--expansion-run-dir")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare": out = prepare(args.repo, args.db, args.question_file, args.obligations_file, args.controller_type_id, args.run_dir, args.max_bytes)
        elif args.command == "expand-gap-prepare": out = expand_gap_prepare(args.repo, args.db, args.source_run_dir, args.destination_run_dir, args.obligations_file, args.max_bytes)
        elif args.command == "expand-gap-review": out = expand_gap_review(args.repo, args.db, args.source_run_dir, args.destination_run_dir, args.obligations_file, args.review_file)
        elif args.command == "expand-gap-status": out = expand_gap_status(args.repo, args.db, args.source_run_dir, args.destination_run_dir, args.obligations_file)
        elif args.command == "expand-gap-import-prepare": out = expand_gap_import_prepare(args.repo, args.db, args.source_run_dir,
            args.expansion_run_dir, args.target_run_dir, args.question_file, args.obligations_file)
        elif args.command == "expand-gap-import-status": out = expand_gap_import_status(args.repo, args.db, args.source_run_dir,
            args.expansion_run_dir, args.target_run_dir, args.question_file, args.obligations_file)
        elif args.command == "expand-gap-selector-view": out = expand_gap_selector_view(args.repo, args.db, args.run_dir,
            args.obligations_file, args.expansion_run_dir)
        elif args.command == "select": out = _write_selection(Path(args.run_dir), args.repo, args.db, args.selection_file,
            args.obligations_file, args.expansion_run_dir)
        elif args.command == "status": out = status(Path(args.run_dir), args.repo, args.db, args.obligations_file, args.expansion_run_dir)
        elif args.command == "answer": out = submit_answer(Path(args.run_dir), args.repo, args.db, args.obligations_file, args.draft_file, args.answer_file, expansion_run_dir=args.expansion_run_dir)
        elif args.command == "correct": out = submit_answer(Path(args.run_dir), args.repo, args.db, args.obligations_file, args.draft_file, args.answer_file, True, args.expansion_run_dir)
        elif args.command == "review": out = review(Path(args.run_dir), args.repo, args.db, args.obligations_file, args.review_file, expansion_run_dir=args.expansion_run_dir)
        elif args.command == "review-correction": out = review(Path(args.run_dir), args.repo, args.db, args.obligations_file, args.review_file, True, args.expansion_run_dir)
        elif args.command == "accept": out = accept(Path(args.run_dir), args.repo, args.db, args.obligations_file, expansion_run_dir=args.expansion_run_dir)
        else: out = accept(Path(args.run_dir), args.repo, args.db, args.obligations_file, True, args.expansion_run_dir)
    except (CoordinatorError, atlas.AtlasError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"question-coordinator: {exc}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(_bytes(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
