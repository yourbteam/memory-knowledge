#!/usr/bin/env python3
"""Prepare and validate a resumable answer over every accepted map for one controller."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if os.fspath(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, os.fspath(SCRIPT_DIR))

import atlas  # noqa: E402


SCHEMA_VERSION = 1
DEFAULT_LIMIT = 10_000_000
ARTIFACTS = {
    "selection-packet.json", "candidate-observations.json", "selection.json", "answer-packet.json", "answer.json",
    "review.json", "answer-review-packet.json", "review-result.json", "correction-packet.json",
    "corrected-answer-packet.json", "corrected-review.json", "accepted-package.json", "evidence-gap.json",
}

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
    if path.exists():
        try:
            old = path.read_bytes()
        except OSError as exc:
            raise CoordinatorError(f"cannot verify existing artifact {path}: {exc}") from exc
        if old != encoded:
            raise CoordinatorError(f"immutable artifact already exists with different content: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise CoordinatorError(f"artifact appeared while saving; verify exact content: {path}") from exc
    with os.fdopen(fd, "wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def _read_artifact(run: Path, name: str) -> dict[str, object]:
    path = run / name
    if path.is_symlink() or not path.is_file():
        raise CoordinatorError(f"required stage artifact is missing or unsafe: {path}")
    value = _read(path, name)
    if path.read_bytes() != _bytes(value):
        raise CoordinatorError(f"stage artifact is not canonical JSON: {path}")
    return value


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


def prepare(repo: str, db: str, question_file: str, obligations_file: str, controller: str, run_dir: str,
            limit: int = DEFAULT_LIMIT) -> dict[str, object]:
    try:
        question_raw = Path(question_file).read_bytes()
        question = question_raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise CoordinatorError(f"question file must be readable UTF-8: {exc}") from exc
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
            "semantic_sha256": semantic_hash, "candidate_count": len(candidates), "obligation_id": obligation_id}


def _revalidate(run: Path, repo: str, db: str, obligations_file: str) -> dict[str, object]:
    packet = _read_artifact(run, "selection-packet.json")
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


def _write_selection(run: Path, repo: str, db: str, selection_file: str, obligations_file: str) -> dict[str, object]:
    packet = _revalidate(run, repo, db, obligations_file)
    selection = _read(Path(selection_file), "independent selection")
    checked = _validate_selection(packet, selection)
    union = _selected_union(packet, checked["accepted"])
    absent = [key for key, status in checked["obligations"].items() if status == "absent_from_candidates"]
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
    return {"result": "selected", "selected_map_count": len(chosen), "claim_count": len(union["claims"]),
            "packet_sha256": union_packet["semantic_sha256"]}


def _answer_contract(packet: dict[str, object]) -> dict[str, object]:
    contract = _answer_schema_contract()
    contract["fields"]["question_id"]["exact"] = packet.get("obligation_id")
    contract["fields"]["answer"]["exact"] = "draft-file UTF-8 text"
    return contract


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
    if round_number == 1:
        result["correction_lineage"] = {"correction_packet_sha256": packet["packet_sha256"],
                                        "original_packet_sha256": packet["original_packet_sha256"],
                                        "rejected_review_sha256": packet["rejected_review_sha256"],
                                        "correction_round": 1, "max_corrections": 1}
    result["packet_sha256"] = _digest(result)
    return result


def submit_answer(run: Path, repo: str, db: str, obligations_file: str, draft_file: str, answer_file: str, correction: bool = False) -> dict[str, object]:
    _revalidate(run, repo, db, obligations_file)
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


def review(run: Path, repo: str, db: str, obligations_file: str, review_file: str, corrected: bool = False) -> dict[str, object]:
    _revalidate(run, repo, db, obligations_file)
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
    final["package_sha256"] = _digest(final)
    return final


def accept(run: Path, repo: str, db: str, obligations_file: str, corrected: bool = False) -> dict[str, object]:
    _revalidate(run, repo, db, obligations_file)
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


def status(run: Path, repo: str, db: str, obligations_file: str) -> dict[str, object]:
    packet = _revalidate(run, repo, db, obligations_file)
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
    return {"result": "current", "semantic_sha256": packet["semantic_sha256"], "candidate_count": len(packet["candidates"]),
            "artifacts": artifacts, "terminal": "accepted" if (run / "accepted-package.json").exists() else "evidence_gap" if (run / "evidence-gap.json").exists() else "in_progress"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare")
    p.add_argument("--repo", required=True); p.add_argument("--db", required=True)
    p.add_argument("--question-file", required=True); p.add_argument("--obligations-file", required=True)
    p.add_argument("--controller-type-id", required=True); p.add_argument("--run-dir", required=True)
    p.add_argument("--max-bytes", type=int, default=DEFAULT_LIMIT)
    for stage in ("select", "status"):
        s = commands.add_parser(stage); s.add_argument("--repo", required=True); s.add_argument("--db", required=True); s.add_argument("--run-dir", required=True)
        s.add_argument("--obligations-file", required=True)
        if stage == "select": s.add_argument("--selection-file", required=True)
    for stage in ("answer", "correct"):
        s = commands.add_parser(stage); s.add_argument("--repo", required=True); s.add_argument("--db", required=True); s.add_argument("--run-dir", required=True)
        s.add_argument("--obligations-file", required=True)
        s.add_argument("--draft-file", required=True); s.add_argument("--answer-file", required=True)
    for stage in ("review", "review-correction"):
        s = commands.add_parser(stage); s.add_argument("--repo", required=True); s.add_argument("--db", required=True); s.add_argument("--run-dir", required=True); s.add_argument("--review-file", required=True)
        s.add_argument("--obligations-file", required=True)
    for stage in ("accept", "accept-correction"):
        s = commands.add_parser(stage); s.add_argument("--repo", required=True); s.add_argument("--db", required=True); s.add_argument("--run-dir", required=True)
        s.add_argument("--obligations-file", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare": out = prepare(args.repo, args.db, args.question_file, args.obligations_file, args.controller_type_id, args.run_dir, args.max_bytes)
        elif args.command == "select": out = _write_selection(Path(args.run_dir), args.repo, args.db, args.selection_file, args.obligations_file)
        elif args.command == "status": out = status(Path(args.run_dir), args.repo, args.db, args.obligations_file)
        elif args.command == "answer": out = submit_answer(Path(args.run_dir), args.repo, args.db, args.obligations_file, args.draft_file, args.answer_file)
        elif args.command == "correct": out = submit_answer(Path(args.run_dir), args.repo, args.db, args.obligations_file, args.draft_file, args.answer_file, True)
        elif args.command == "review": out = review(Path(args.run_dir), args.repo, args.db, args.obligations_file, args.review_file)
        elif args.command == "review-correction": out = review(Path(args.run_dir), args.repo, args.db, args.obligations_file, args.review_file, True)
        elif args.command == "accept": out = accept(Path(args.run_dir), args.repo, args.db, args.obligations_file)
        else: out = accept(Path(args.run_dir), args.repo, args.db, args.obligations_file, True)
    except (CoordinatorError, atlas.AtlasError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"question-coordinator: {exc}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(_bytes(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
