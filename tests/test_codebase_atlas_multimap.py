from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest


SCRIPT = Path(__file__).parents[1] / "skills/codebase-atlas-machinery/scripts/question_coordinator.py"
SPEC = importlib.util.spec_from_file_location("question_coordinator", SCRIPT)
qc = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(qc)


def _obligations_file(tmp_path: Path, question: str = "Compare alpha and beta.") -> Path:
    path = tmp_path / "frozen-obligations.json"
    value = {"questions": {"fixture": {"question": question, "required_routes": ["alpha"],
              "required_behavior_ids": ["behavior.1"],
              "required_obligations": [{"id": "behavior.1", "text": "Alpha has the required source behavior."}],
              "required_comparisons": ["Compare alpha with beta."], "required_limits": ["Do not infer runtime."]}}}
    path.write_bytes(qc._bytes(value))
    return path


def _packet(tmp_path: Path) -> dict[str, object]:
    import hashlib
    question = "Compare alpha and beta."
    obligations_file = _obligations_file(tmp_path, question)
    normalized, obligation_id, source_identity = qc._obligations(obligations_file, question)
    packet = {
        "selection_schema_version": 1, "packet_type": "controller_map_selection", "question": question,
        "question_sha256": hashlib.sha256(question.encode()).hexdigest(), "obligation_id": obligation_id,
        "required_routes": normalized["required_routes"], "obligations": normalized["obligations"],
        "identity": {"repository_root": "/repo", "head": "head", "head_ref": None,
                     "snapshot_id": "snapshot", "extractor_identity": "extractor",
                     "controller_type_id": "A.Controller`0", "repository_status": [],
                     "obligations_file_path": source_identity["path"], "obligations_file_sha256": source_identity["sha256"]},
        "candidates": [{"route": {"id": "r1", "route_literal": "api/alpha"}, "map": {}, "provenance": {
                            "overlay_id": "overlay-r1", "binding_hash": "binding-r1", "association_review_hash": "association-r1",
                            "flow_review_receipt": {"receipt_hash": "receipt-r1"}}},
                       {"route": {"id": "r2", "route_literal": "api/beta"}, "map": {}, "provenance": {
                            "overlay_id": "overlay-r2", "binding_hash": "binding-r2", "association_review_hash": "association-r2",
                            "flow_review_receipt": {"receipt_hash": "receipt-r2"}}}],
    }
    packet["selection_contract"] = qc._selection_contract(packet["candidates"], packet["obligations"], packet["required_routes"])
    packet["semantic_sha256"] = qc._digest(qc._semantic_payload(packet["identity"], question, packet["question_sha256"],
        obligation_id, packet["required_routes"], packet["obligations"], packet["candidates"]))
    packet["packet_sha256"] = qc._digest(packet)
    return packet


def _live_candidates(packet: dict[str, object]) -> list[dict[str, object]]:
    return [{**candidate, "observations": {"freshness": {"checked_at": "2026-10-08T10:00:00Z", "result": "fresh",
                                                           "repository_root": "/repo", "head": "head", "reasons": []},
                                                   "budget": {"complete": True, "bytes": 10}}}
            for candidate in packet["candidates"]]


def _write_packet(run: Path, packet: dict[str, object]) -> None:
    (run / "selection-packet.json").write_bytes(qc._bytes(packet))
    candidates = _live_candidates(packet)
    observations = {"observation_schema_version": 1, "selection_packet_sha256": packet["packet_sha256"],
                    "observations": [{"route_fact_id": candidate["route"]["id"], **candidate["observations"]}
                                    for candidate in candidates]}
    observations["observations_sha256"] = qc._digest(observations)
    (run / "candidate-observations.json").write_bytes(qc._bytes(observations))


def _selection(packet: dict[str, object], *, decisions: tuple[str, str] = ("accept", "accept"),
               supporters: tuple[str, ...] = ("r1",)) -> dict[str, object]:
    return {
        "selection_schema_version": 1,
        "packet_sha256": packet["packet_sha256"],
        "reviewer_identity": "sol-audit-label",
        "reviewer_model": "GPT-6.1 Sol High",
        "candidate_reviews": [
            {"route_fact_id": "r1", "decision": decisions[0], "basis": "This route directly contributes the required source behavior."},
            {"route_fact_id": "r2", "decision": decisions[1], "basis": "This route supplies the requested comparison details."},
        ],
        "obligation_reviews": [
            {"obligation_id": "behavior.1", "candidate_status": "present_in_candidates",
             "supporting_route_fact_ids": list(supporters), "basis": "The cited candidate source includes the required behavior."},
            {"obligation_id": "comparison:1", "candidate_status": "present_in_candidates",
             "supporting_route_fact_ids": ["r1", "r2"], "basis": "Both candidates provide evidence for this comparison."},
            {"obligation_id": "limit:1", "candidate_status": "present_in_candidates",
             "supporting_route_fact_ids": ["r1", "r2"], "basis": "Both candidate packets preserve the static evidence boundary."},
        ],
    }


def test_selection_refuses_omitted_candidate(tmp_path: Path):
    packet = _packet(tmp_path)
    record = _selection(packet)
    record["candidate_reviews"].pop()
    with pytest.raises(qc.CoordinatorError, match="every candidate exactly once"):
        qc._validate_selection(packet, record)


def test_selection_refuses_required_fact_in_rejected_candidate(tmp_path: Path):
    packet = _packet(tmp_path)
    with pytest.raises(qc.CoordinatorError, match="supported by rejected candidate"):
        qc._validate_selection(packet, _selection(packet, decisions=("accept", "reject"), supporters=("r2",)))


def test_account_guest_create_account_route_cannot_be_rejected_without_obligation_support(tmp_path: Path):
    packet = _packet(tmp_path)
    packet["required_routes"] = ["create-account"]
    packet["candidates"][0]["route"]["route_literal"] = "api/create-account"
    with pytest.raises(qc.CoordinatorError, match="required route 'create-account'.*'api/create-account'.*was rejected"):
        qc._validate_selection(packet, _selection(packet, decisions=("reject", "accept"), supporters=("r2",)))


@pytest.mark.parametrize("definition, expected", [
    (None, "no authoritative definition"),
    ([{"id": "behavior.1", "text": "One meaning."}, {"id": "behavior.1", "text": "One meaning."}], "duplicate definitions"),
    ([{"id": "behavior.1", "text": "First meaning."}, {"id": "behavior.1", "text": "Second meaning."}], "conflicting definitions"),
    ([{"id": "behavior.1", "text": "   "}], "observed meaning '   '"),
    ([{"id": "behavior.1", "text": 17}], "observed meaning 17"),
])
def test_obligation_meanings_fail_closed_with_exact_diagnostic(tmp_path: Path, definition, expected: str):
    question = "Compare alpha and beta."
    value = {"questions": {"fixture": {"question": question, "required_routes": ["alpha"],
             "required_behavior_ids": ["behavior.1"], "required_comparisons": [], "required_limits": []}}}
    if definition is not None:
        value["questions"]["fixture"]["required_obligations"] = definition
    source = tmp_path / "bad-obligations.json"
    source.write_bytes(qc._bytes(value))
    with pytest.raises(qc.CoordinatorError, match=expected):
        qc._obligations(source, question)


def test_obligation_packet_preserves_authoritative_meaning_verbatim(tmp_path: Path):
    packet = _packet(tmp_path)
    assert packet["obligations"] == [
        {"obligation_id": "behavior.1", "kind": "behavior", "meaning": "Alpha has the required source behavior."},
        {"obligation_id": "comparison:1", "kind": "comparison", "meaning": "Compare alpha with beta."},
        {"obligation_id": "limit:1", "kind": "limit", "meaning": "Do not infer runtime."},
    ]


def test_compact_rubric_route_definitions_supply_behavior_meanings(tmp_path: Path):
    question = "Compare alpha."
    source = tmp_path / "compact-rubric.json"
    source.write_bytes(qc._bytes({"routes": {"alpha": {"required_behaviors": [
        {"id": "behavior.1", "behavior": "Meaning from the compact rubric."}]}},
        "questions": {"fixture": {"question": question, "required_routes": ["api/alpha"],
                      "required_behavior_ids": ["behavior.1"], "required_comparisons": [], "required_limits": []}}}))
    normalized, _, _ = qc._obligations(source, question)
    assert normalized["required_routes"] == ["alpha"]
    assert normalized["obligations"] == [{"obligation_id": "behavior.1", "kind": "behavior",
                                           "meaning": "Meaning from the compact rubric."}]


def test_revalidation_refuses_candidate_tamper_with_outer_hash_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    packet = _packet(tmp_path)
    _write_packet(tmp_path, packet)
    packet["candidates"][0]["map"]["claims"] = [{"claim": "rewritten"}]
    packet["packet_sha256"] = qc._digest({key: value for key, value in packet.items() if key != "packet_sha256"})
    _write_packet(tmp_path, packet)
    monkeypatch.setattr(qc, "_candidate_set", lambda *_args: (packet["identity"], _live_candidates(packet), {}))
    with pytest.raises(qc.CoordinatorError, match="semantic_sha256 observed"):
        qc._revalidate(tmp_path, "/repo", "/db", str(tmp_path / "frozen-obligations.json"))


def test_revalidation_refuses_candidate_tamper_even_when_all_packet_hashes_recomputed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    packet = _packet(tmp_path)
    _write_packet(tmp_path, packet)
    packet["candidates"][0]["map"]["claims"] = [{"claim": "rewritten"}]
    packet["semantic_sha256"] = qc._digest(qc._semantic_payload(packet["identity"], packet["question"], packet["question_sha256"],
        packet["obligation_id"], packet["required_routes"], packet["obligations"], packet["candidates"]))
    packet["packet_sha256"] = qc._digest({key: value for key, value in packet.items() if key != "packet_sha256"})
    _write_packet(tmp_path, packet)
    monkeypatch.setattr(qc, "_candidate_set", lambda *_args: (packet["identity"], _live_candidates(_packet(tmp_path)), {}))
    with pytest.raises(qc.CoordinatorError, match="prepared stable payload differs"):
        qc._revalidate(tmp_path, "/repo", "/db", str(tmp_path / "frozen-obligations.json"))


def test_revalidation_refuses_obligation_meaning_rewrite_with_all_packet_hashes_recomputed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    packet = _packet(tmp_path)
    _write_packet(tmp_path, packet)
    packet["obligations"][0]["meaning"] = "Attacker replacement meaning."
    packet["semantic_sha256"] = qc._digest(qc._semantic_payload(packet["identity"], packet["question"], packet["question_sha256"],
        packet["obligation_id"], packet["required_routes"], packet["obligations"], packet["candidates"]))
    packet["packet_sha256"] = qc._digest({key: value for key, value in packet.items() if key != "packet_sha256"})
    _write_packet(tmp_path, packet)
    monkeypatch.setattr(qc, "_candidate_set", lambda *_args: (packet["identity"], _live_candidates(packet), {}))
    with pytest.raises(qc.CoordinatorError, match="original file requires.*Alpha has the required source behavior"):
        qc._revalidate(tmp_path, "/repo", "/db", str(tmp_path / "frozen-obligations.json"))


def test_revalidation_refuses_question_text_and_hash_rewrite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    packet = _packet(tmp_path)
    _write_packet(tmp_path, packet)
    packet["question"] = "A rewritten question?"
    packet["question_sha256"] = __import__("hashlib").sha256(packet["question"].encode()).hexdigest()
    packet["semantic_sha256"] = qc._digest(qc._semantic_payload(packet["identity"], packet["question"], packet["question_sha256"],
        packet["obligation_id"], packet["required_routes"], packet["obligations"], packet["candidates"]))
    packet["packet_sha256"] = qc._digest({key: value for key, value in packet.items() if key != "packet_sha256"})
    _write_packet(tmp_path, packet)
    monkeypatch.setattr(qc, "_candidate_set", lambda *_args: (packet["identity"], _live_candidates(packet), {}))
    with pytest.raises(qc.CoordinatorError, match="exactly one frozen obligation record"):
        qc._revalidate(tmp_path, "/repo", "/db", str(tmp_path / "frozen-obligations.json"))


def test_revalidation_refuses_rewritten_freshness_observation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    packet = _packet(tmp_path)
    _write_packet(tmp_path, packet)
    current_candidates = _live_candidates(_packet(tmp_path))
    current_candidates[0]["observations"]["freshness"]["result"] = "stale"
    monkeypatch.setattr(qc, "_candidate_set", lambda *_args: (packet["identity"], current_candidates, {}))
    with pytest.raises(qc.CoordinatorError, match="freshness/budget observations changed"):
        qc._revalidate(tmp_path, "/repo", "/db", str(tmp_path / "frozen-obligations.json"))


def test_revalidation_allows_only_checked_at_to_advance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    packet = _packet(tmp_path)
    _write_packet(tmp_path, packet)
    current_candidates = _live_candidates(packet)
    current_candidates[0]["observations"]["freshness"]["checked_at"] = "2026-10-08T10:01:00Z"
    monkeypatch.setattr(qc, "_candidate_set", lambda *_args: (packet["identity"], current_candidates, {}))
    assert qc._revalidate(tmp_path, "/repo", "/db", str(tmp_path / "frozen-obligations.json"))["packet_sha256"] == packet["packet_sha256"]


@pytest.mark.parametrize("section,field,value", [
    ("freshness", "reasons", ["new reason"]),
    ("budget", "bytes", 11),
])
def test_revalidation_refuses_nonvolatile_observation_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                               section: str, field: str, value: object):
    packet = _packet(tmp_path)
    _write_packet(tmp_path, packet)
    current_candidates = _live_candidates(packet)
    current_candidates[0]["observations"][section][field] = value
    monkeypatch.setattr(qc, "_candidate_set", lambda *_args: (packet["identity"], current_candidates, {}))
    with pytest.raises(qc.CoordinatorError, match="freshness/budget observations changed"):
        qc._revalidate(tmp_path, "/repo", "/db", str(tmp_path / "frozen-obligations.json"))


@pytest.mark.parametrize("checked_at", [None, "", "not-a-time", "2026-10-08T10:00:00"])
def test_observation_artifact_refuses_malformed_checked_at(tmp_path: Path, checked_at: object):
    packet = _packet(tmp_path)
    _write_packet(tmp_path, packet)
    record = qc._read_artifact(tmp_path, "candidate-observations.json")
    record["observations"][0]["freshness"]["checked_at"] = checked_at
    record["observations_sha256"] = qc._digest({key: value for key, value in record.items() if key != "observations_sha256"})
    with pytest.raises(qc.CoordinatorError, match="freshness.checked_at observed"):
        qc._validate_candidate_observations(record, packet)


def test_revalidation_refuses_tampered_packet_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    packet = _packet(tmp_path)
    packet["packet_sha256"] = "tampered"
    _write_packet(tmp_path, packet)
    monkeypatch.setattr(qc, "_candidate_set", lambda *_args: (packet["identity"], [], {}))
    with pytest.raises(qc.CoordinatorError, match="packet_sha256 does not match"):
        qc._revalidate(tmp_path, "/repo", "/db", str(tmp_path / "frozen-obligations.json"))


def test_revalidation_refuses_stale_checkout_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    packet = _packet(tmp_path)
    _write_packet(tmp_path, packet)
    current = dict(packet["identity"], head="new-head")
    monkeypatch.setattr(qc, "_candidate_set", lambda *_args: (current, _live_candidates(packet), {}))
    with pytest.raises(qc.CoordinatorError, match="prepared stable payload differs"):
        qc._revalidate(tmp_path, "/repo", "/db", str(tmp_path / "frozen-obligations.json"))


def test_revalidation_refuses_tampered_candidate_observation_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    packet = _packet(tmp_path)
    _write_packet(tmp_path, packet)
    observations = qc._read_artifact(tmp_path, "candidate-observations.json")
    observations["observations"][0]["freshness"]["result"] = "stale"
    (tmp_path / "candidate-observations.json").write_bytes(qc._bytes(observations))
    monkeypatch.setattr(qc, "_candidate_set", lambda *_args: (packet["identity"], _live_candidates(packet), {}))
    with pytest.raises(qc.CoordinatorError, match="observation artifact hash is invalid"):
        qc._revalidate(tmp_path, "/repo", "/db", str(tmp_path / "frozen-obligations.json"))


def test_answer_refusal_names_observed_non_atomic_assertion_and_correction():
    answer = {"question_id": "fixture", "answer": "Draft.",
              "material_claims": [{"assertion": "First fact; second fact.", "claim_numbers": [1], "citations": []}],
              "limitations": [], "evidence_measurement": {}}
    with pytest.raises(qc.CoordinatorError, match="observed 'First fact; second fact.'; required one atomic sentence"):
        qc._validate_answer({"obligation_id": "fixture", "claims": [], "source_anchors": [], "source_snippets": []},
                            b"Draft.", answer)


def test_revalidation_refuses_tampered_union_provenance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    packet = _packet(tmp_path)
    _write_packet(tmp_path, packet)
    current = packet["identity"]
    monkeypatch.setattr(qc, "_candidate_set", lambda *_args: (current, _live_candidates(packet), {}))
    record = _selection(packet)
    checked = qc._validate_selection(packet, record)
    chosen = {candidate["route"]["id"]: candidate for candidate in checked["accepted"]}
    selection = {"schema_version": 1, "selection_packet_sha256": packet["packet_sha256"], "selection_record": record,
                 "selected_candidates": [{"route_fact_id": route_id, **{
                                              "overlay_id": chosen[route_id]["provenance"]["overlay_id"],
                                              "binding_hash": chosen[route_id]["provenance"]["binding_hash"],
                                              "association_review_hash": chosen[route_id]["provenance"]["association_review_hash"],
                                              "review_receipt_hash": chosen[route_id]["provenance"]["flow_review_receipt"]["receipt_hash"]}}
                                         for route_id in sorted(chosen)],
                 "obligation_status": checked["obligations"]}
    (tmp_path / "selection.json").write_bytes(qc._bytes(selection))
    monkeypatch.setattr(qc, "_selected_union", lambda *_args: {"claims": [], "source_anchors": [], "source_snippets": []})
    answer = {"answer_schema_version": 1, "packet_type": "multi_map_answer", "question": packet["question"],
              "question_sha256": packet["question_sha256"], "controller_type_id": packet["identity"]["controller_type_id"],
              "obligation_id": packet["obligation_id"], "snapshot_id": packet["identity"]["snapshot_id"],
              "extractor_identity": packet["identity"]["extractor_identity"], "selection": selection, "required_routes": packet["required_routes"],
              "obligations": packet["obligations"], "claims": [], "source_anchors": [], "source_snippets": []}
    answer["answer_contract"] = qc._answer_contract(answer)
    answer["semantic_sha256"] = qc._digest(answer)
    answer["source_anchors"].append({"source_id": "source-tampered", "path": "src/Forged.cs", "sha256": "fake"})
    (tmp_path / "answer-packet.json").write_bytes(qc._bytes(answer))
    with pytest.raises(qc.CoordinatorError, match="selected union packet is tampered"):
        qc._revalidate(tmp_path, "/repo", "/db", str(tmp_path / "frozen-obligations.json"))


def test_stage_artifacts_are_idempotent_only_for_exact_replay(tmp_path: Path):
    artifact = tmp_path / "selection.json"
    qc._save_immutable(artifact, {"decision": "accepted"})
    qc._save_immutable(artifact, {"decision": "accepted"})
    with pytest.raises(qc.CoordinatorError, match="immutable artifact already exists"):
        qc._save_immutable(artifact, {"decision": "rejected"})


def test_second_correction_cannot_be_accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(qc, "_revalidate", lambda *_args: {})
    (tmp_path / "selection.json").write_bytes(qc._bytes({"selection_record": {}}))
    (tmp_path / "corrected-answer-packet.json").write_bytes(qc._bytes({"packet_type": "multi_map_answer_review"}))
    (tmp_path / "corrected-review.json").write_bytes(qc._bytes({"decision": "rejected"}))
    with pytest.raises(qc.CoordinatorError, match="second correction is forbidden"):
        qc.accept(tmp_path, "/repo", "/db", "unused", corrected=True)


def _candidate(route_id: str, route_name: str, *, claim_text: str) -> dict[str, object]:
    source_id = f"source-{route_id}"
    snippet_id = f"snippet-{route_id}"
    return {"route": {"id": route_id, "route_literal": f"api/{route_name}"},
            "observations": {"freshness": {"checked_at": "2026-10-08T10:00:00Z", "result": "fresh",
                                           "repository_root": "/repo", "head": "head", "reasons": []},
                            "budget": {"complete": True, "bytes": 10}},
            "map": {"claims": [{"claim": claim_text, "evidence": [{"fact_id": f"fact-{route_id}", "source_id": source_id,
                                                                         "span": {"start": 0, "end": 8}, "snippet_id": snippet_id}]}],
                    "source_anchors": [{"source_id": source_id, "path": f"src/{route_name}.cs", "sha256": f"hash-{route_id}"}],
                    "source_snippets": [{"snippet_id": snippet_id, "source_id": source_id,
                                         "span": {"start": 0, "end": 8}, "text": claim_text}]},
            "provenance": {"overlay_id": f"overlay-{route_id}", "binding_hash": f"binding-{route_id}",
                           "association_review_hash": f"association-{route_id}",
                           "flow_review_receipt": {"receipt_hash": f"receipt-{route_id}"}}}


def _roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, *, answer_gap: bool = False,
               evidence_gap: bool = False) -> dict[str, object]:
    question = "Compare alpha and beta."
    qfile = tmp_path / f"{name}-question.txt"
    qfile.write_text(question, encoding="utf-8")
    obligations = {"questions": {"fixture": {"question": question, "required_routes": ["alpha"],
                   "required_behavior_ids": ["behavior.1"], "required_obligations": [{"id": "behavior.1", "text": "Alpha has a required source-backed behavior."}], "required_comparisons": ["Compare alpha with beta."],
                   "required_limits": ["Do not infer runtime."]}}}
    ofile = tmp_path / f"{name}-obligations.json"
    ofile.write_bytes(qc._bytes(obligations))
    identity = {"repository_root": "/repo", "head": "head", "head_ref": "main", "snapshot_id": "snapshot",
                "extractor_identity": "extractor", "controller_type_id": "A.Controller`0", "repository_status": []}
    candidates = [_candidate("r1", "alpha", claim_text="Alpha has a source-backed behavior."),
                  _candidate("r2", "beta", claim_text="Beta has a source-backed behavior.")]
    monkeypatch.setattr(qc, "_candidate_set", lambda *_args: (identity, candidates, {"head": "head"}))
    run = tmp_path / name
    qc.prepare("/repo", "/db", str(qfile), str(ofile), "A.Controller`0", str(run))
    selection_packet = qc._read_artifact(run, "selection-packet.json")
    selection = _selection(selection_packet)
    if evidence_gap:
        selection["obligation_reviews"][0] = {"obligation_id": "behavior.1", "candidate_status": "absent_from_candidates",
                                              "supporting_route_fact_ids": [], "basis": "Neither bounded candidate contains this required behavior."}
    selection_file = tmp_path / f"{name}-selection.json"
    selection_file.write_bytes(qc._bytes(selection))
    qc._write_selection(run, "/repo", "/db", str(selection_file), str(ofile))
    if evidence_gap:
        return qc.status(run, "/repo", "/db", str(ofile))

    union_packet = qc._read_artifact(run, "answer-packet.json")
    draft = "Alpha and beta both have source-backed behavior."
    draft_file = tmp_path / f"{name}-draft.txt"
    draft_file.write_text(draft, encoding="utf-8")
    claims = []
    for claim in union_packet["claims"]:
        citations = [{key: evidence[key] for key in qc.ANSWER_RECORD_SCHEMA["citation_fields"]}
                     for evidence in claim["evidence"]]
        claims.append({"assertion": claim["claim"], "claim_numbers": [claim["claim_number"]], "citations": citations})
    answer = {"question_id": "fixture", "answer": draft, "material_claims": claims,
              "limitations": ["The packet describes bounded source evidence."], "evidence_measurement": {}}
    answer_file = tmp_path / f"{name}-answer.json"
    answer_file.write_bytes(qc._bytes(answer))
    qc.submit_answer(run, "/repo", "/db", str(ofile), str(draft_file), str(answer_file))
    review_packet = qc._read_artifact(run, "review.json")

    def review_record(packet: dict[str, object], reviewer: str, missing_supported: bool) -> dict[str, object]:
        ids = qc._obligation_ids(packet["obligations"])
        return {"review_schema_version": qc.REVIEW_RECORD_SCHEMA["version"],
                "packet_sha256": packet["packet_sha256"], "decision": "rejected" if missing_supported else "accepted",
                "reviewer_identity": reviewer, "reviewer_model": "GPT-6.1 Sol High",
                "claim_reviews": [{"claim_number": i, "disposition": "covered", "basis": "This union claim is represented in the answer with its exact source citation."}
                                  for i, _ in enumerate(packet["claims"], 1)],
                "obligation_reviews": [{"obligation_id": oid, "disposition": "missing_supported" if missing_supported and i == 0 else "covered",
                                        "basis": "The answer omits this source-supported obligation and must add it." if missing_supported and i == 0 else "The answer explicitly covers this frozen question obligation."}
                                       for i, oid in enumerate(ids)],
                "failure_kind": "answer_gap" if missing_supported else "none", "unsupported_assertions": []}

    first_review = review_record(review_packet, "sol-review-1", answer_gap)
    review_file = tmp_path / f"{name}-review.json"
    review_file.write_bytes(qc._bytes(first_review))
    first_result = qc.review(run, "/repo", "/db", str(ofile), str(review_file))
    if answer_gap:
        correction_file = tmp_path / f"{name}-correction.json"
        correction_file.write_bytes(qc._bytes(answer))
        qc.submit_answer(run, "/repo", "/db", str(ofile), str(draft_file), str(correction_file), correction=True)
        corrected_packet = qc._read_artifact(run, "corrected-answer-packet.json")
        final_review_file = tmp_path / f"{name}-corrected-review.json"
        final_review_file.write_bytes(qc._bytes(review_record(corrected_packet, "sol-review-2", False)))
        qc.review(run, "/repo", "/db", str(ofile), str(final_review_file), corrected=True)
        qc.accept(run, "/repo", "/db", str(ofile), corrected=True)
    else:
        assert first_result["result"] == "accepted"
        qc.accept(run, "/repo", "/db", str(ofile))
    return qc.status(run, "/repo", "/db", str(ofile))


def test_authoritative_schemas_drive_packet_contracts_and_all_terminal_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    selection_contract = qc._selection_contract([{}, {}], [{"obligation_id": "behavior.1", "kind": "behavior", "meaning": "Required behavior."}], ["alpha"])
    assert selection_contract["selection_record"]["required_top_level_fields"] == qc.SELECTION_RECORD_SCHEMA["top_level_fields"]
    assert set(selection_contract["selection_record"]["fields"]["candidate_reviews"]["item_fields"]) == set(qc.SELECTION_RECORD_SCHEMA["candidate_fields"])
    answer_contract = qc._answer_schema_contract()
    assert answer_contract["required_fields"] == qc.ANSWER_RECORD_SCHEMA["top_level_fields"]
    assert answer_contract["fields"]["material_claims"]["item_fields"]["citations"]["exact_item_fields"] == qc.ANSWER_RECORD_SCHEMA["citation_fields"]
    review_contract = qc._review_schema_contract([{"obligation_id": "behavior.1", "kind": "behavior", "meaning": "Required behavior."}])
    assert review_contract["required_top_level_fields"] == qc.REVIEW_RECORD_SCHEMA["top_level_fields"]
    assert set(review_contract["claim_reviews"]["item_fields"]) == set(qc.REVIEW_RECORD_SCHEMA["claim_fields"])
    assert set(review_contract["obligation_reviews"]["item_fields"]) == set(qc.REVIEW_RECORD_SCHEMA["obligation_fields"])

    accepted = _roundtrip(tmp_path, monkeypatch, "accepted")
    corrected = _roundtrip(tmp_path, monkeypatch, "corrected", answer_gap=True)
    gap = _roundtrip(tmp_path, monkeypatch, "gap", evidence_gap=True)
    assert accepted["terminal"] == "accepted"
    assert corrected["terminal"] == "accepted"
    assert gap["terminal"] == "evidence_gap"


@pytest.mark.skipif(not all(os.environ.get(key) for key in (
    "ATLAS_MULTIMAP_TEST_REPO", "ATLAS_MULTIMAP_TEST_DB", "ATLAS_MULTIMAP_FROZEN_DIR",
    "ATLAS_MULTIMAP_TEST_OBLIGATIONS")),
    reason="real public-auth controller paths are supplied only for the frozen development regression")
def test_real_public_auth_prepare_is_byte_stable_across_two_runs(tmp_path: Path):
    frozen = Path(os.environ["ATLAS_MULTIMAP_FROZEN_DIR"])
    repo = os.environ["ATLAS_MULTIMAP_TEST_REPO"]
    db = os.environ["ATLAS_MULTIMAP_TEST_DB"]
    controller = "Taggable.Api.Controllers.CustomerPublicAuthController`0"
    questions = json.loads((frozen / "questions.json").read_text(encoding="utf-8"))
    question = questions["account_guest"]
    qfile = tmp_path / "question.txt"
    qfile.write_text(question, encoding="utf-8")
    obligations_file = Path(os.environ["ATLAS_MULTIMAP_TEST_OBLIGATIONS"])
    packets = []
    for run_name in ("run-one", "run-two"):
        run = tmp_path / run_name
        result = subprocess.run([sys.executable, str(SCRIPT), "prepare", "--repo", repo, "--db", db,
                                 "--question-file", str(qfile), "--obligations-file", str(obligations_file),
                                 "--controller-type-id", controller, "--run-dir", str(run)],
                                text=True, capture_output=True)
        assert result.returncode == 0, result.stderr
        packet = qc._read_artifact(run, "selection-packet.json")
        observations = qc._read_artifact(run, "candidate-observations.json")
        assert all("observations" not in candidate for candidate in packet["candidates"])
        assert observations["selection_packet_sha256"] == packet["packet_sha256"]
        assert len(observations["observations"]) == len(packet["candidates"])
        packets.append((packet, (run / "selection-packet.json").read_bytes()))
    assert packets[0][0]["packet_sha256"] == packets[1][0]["packet_sha256"]
    assert packets[0][1] == packets[1][1]
    saved_observations = qc._read_artifact(tmp_path / "run-one", "candidate-observations.json")
    time.sleep(1.1)
    _, current_candidates, _ = qc._candidate_set(repo, db, controller, qc.DEFAULT_LIMIT)
    saved_times = {item["route_fact_id"]: item["freshness"]["checked_at"] for item in saved_observations["observations"]}
    assert any(candidate["observations"]["freshness"]["checked_at"] != saved_times[candidate["route"]["id"]]
               for candidate in current_candidates)
    result = subprocess.run([sys.executable, str(SCRIPT), "status", "--repo", repo, "--db", db,
                             "--run-dir", str(tmp_path / "run-one"), "--obligations-file", str(obligations_file)],
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["result"] == "current"
