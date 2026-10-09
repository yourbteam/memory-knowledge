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
_ORIGINAL_REVALIDATE = qc._revalidate


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
    assert "supplemental_evidence" not in selection_packet
    assert "expansion_binding_lineage" not in selection_packet
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


def test_ordinary_selection_packet_hash_gate_rejects_inherited_self_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    question = "Check the ordinary packet hash gate."
    question_file = tmp_path / "question.txt"
    question_file.write_text(question, encoding="utf-8")
    obligations_file = tmp_path / "obligations.json"
    obligations_file.write_bytes(qc._bytes({"questions": {"fixture": {"question": question,
        "required_routes": ["alpha"], "required_behavior_ids": ["behavior.1"],
        "required_obligations": [{"id": "behavior.1", "text": "Alpha has a required source-backed behavior."}]}}}))
    identity = {"repository_root": "/repo", "head": "head", "head_ref": "main", "snapshot_id": "snapshot",
        "extractor_identity": "extractor", "controller_type_id": "A.Controller`0", "repository_status": []}
    candidates = [_candidate("r1", "alpha", claim_text="Alpha has a source-backed behavior.")]
    monkeypatch.setattr(qc, "_candidate_set", lambda *_args: (identity, candidates, {"head": "head"}))
    run = tmp_path / "ordinary"
    qc.prepare("/repo", "/db", str(question_file), str(obligations_file), "A.Controller`0", str(run))
    path = run / "selection-packet.json"
    packet = qc._read_artifact(run, "selection-packet.json")
    assert packet["packet_sha256"] == qc._digest({key: value for key, value in packet.items() if key != "packet_sha256"})
    assert "supplemental_evidence" not in packet
    assert "expansion_binding_lineage" not in packet
    malformed = dict(packet)
    malformed["packet_sha256"] = qc._digest(malformed)
    path.write_bytes(qc._bytes(malformed))
    with pytest.raises(qc.CoordinatorError, match="packet_sha256 does not match its canonical content"):
        qc._revalidate(run, "/repo", "/db", str(obligations_file))


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


def _expansion_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, declaration: str = "public const int ChangeEventDays = 10;",
                       extra_handler: str = "", conditional: bool = False, ambiguous_owner: bool = False,
                       unsafe_source: bool = False, qualified_origin: bool = False,
                       conditional_origin: bool = False, method_signature: str = "public void Handle()",
                       method_extra: str = "", multi_declaration: str | None = None,
                       nested_origin_owner: bool = False, extra_seed: str = "",
                       clip_qualified_snippet: bool = False, extra_obligation_meanings: tuple[str, ...] = (),
                       no_candidates: bool = False):
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    origin_expression = "Other.ChangeEventDays" if qualified_origin else "ChangeEventDays"
    if extra_seed: origin_expression += " + " + extra_seed
    declaration = multi_declaration or declaration
    conditional_use_open = "\n#if FEATURE\n  " if conditional_origin else ""
    conditional_use_close = "\n#endif\n" if conditional_origin else ""
    source_text = ("namespace Demo {\n"
        "public class GetLegacyTimeslotsQueryHandler {\n"
        f"  {method_signature} {{ {method_extra} for (var offset = 0; offset < {conditional_use_open}{origin_expression}{conditional_use_close}; offset++) {{ }} }}\n"
        f"  {extra_handler}\n  {('#if FEATURE\\n  ' if conditional else '')}{declaration}{('\\n  #endif' if conditional else '')}\n"
        "}\n" + ("" if no_candidates else "public class Other { public const int ChangeEventDays = 720; }\n"
        "public class Third { public const int ChangeEventDays = 90; }\n") + "}")
    file_text = source_text
    raw = file_text.encode("utf-8")
    source_hash = __import__("hashlib").sha256(raw).hexdigest()
    path = "src/Handler.cs"
    handler_start = file_text.index("public class GetLegacyTimeslotsQueryHandler")
    other_start = file_text.index("public class Other") if not no_candidates else 0
    third_start = file_text.index("public class Third") if not no_candidates else 0
    graph_facts = [
        {"id": "type-handler", "kind": "type_declaration", "type_id": "Demo.GetLegacyTimeslotsQueryHandler`0",
         "source": {"path": path, "span": {"start_offset": handler_start}}},
        *([] if no_candidates else [
            {"id": "type-other", "kind": "type_declaration", "type_id": "Demo.Other`0",
             "source": {"path": path, "span": {"start_offset": other_start}}},
            {"id": "type-third", "kind": "type_declaration", "type_id": "Demo.Third`0",
             "source": {"path": path, "span": {"start_offset": third_start}}},
        ]),
    ]
    if nested_origin_owner:
        graph_facts.append({"id": "type-nested-origin", "kind": "type_declaration", "type_id": "Demo.NestedOrigin`0",
            "source": {"path": path, "span": {"start_offset": file_text.index(method_signature)}}})
    if ambiguous_owner:
        graph_facts.append({"id": "type-handler-duplicate", "kind": "type_declaration",
            "type_id": "Demo.GetLegacyTimeslotsQueryHandler`0", "source": {"path": path, "span": {"start_offset": handler_start}}})
    snapshot = {"snapshot_id": "snapshot", "files": [{"path": path, "presence": "present", "type": "file", "sha256": source_hash}],
                "source_graph": {"extractor_identity": "extractor", "facts": graph_facts}}
    live = {"repository_root": str(repo), "head": "head", "head_ref": "main", "status": []}
    identity = {"repository_root": str(repo), "head": "head", "head_ref": "main", "snapshot_id": "snapshot",
                "extractor_identity": "extractor", "controller_type_id": "Demo.Controller`0", "repository_status": []}
    q = "What is the source bound?"
    meaning = f"The source declaration fixes ChangeEventDays at 10 and names {extra_seed}." if extra_seed else "The source declaration fixes ChangeEventDays at 10."
    snippet = "ChangeEventDays" if qualified_origin and clip_qualified_snippet else origin_expression
    snippet_start = file_text.index(snippet, file_text.index(method_signature))
    if qualified_origin and clip_qualified_snippet:
        snippet_start = file_text.index("Other.ChangeEventDays", file_text.index(method_signature)) + len("Other.")
    snippet_end = snippet_start + len(snippet)
    candidate = {"route": {"id": "route-origin", "route_literal": "api/source-bound"},
        "map": {"claims": [{"claim": f"The handler loops while offset is less than {origin_expression}.",
            "evidence": [{"fact_id": "method-origin", "source_id": "source-1", "snippet_id": "snippet-use",
                         "span": {"start_offset": snippet_start, "end_offset": snippet_end, "offset_unit": "unicode_codepoint"}}]}],
            "source_anchors": [{"source_id": "source-1", "path": path, "sha256": source_hash}],
            "source_snippets": [{"snippet_id": "snippet-use", "source_id": "source-1",
                "span": {"start_offset": snippet_start, "end_offset": snippet_end, "offset_unit": "unicode_codepoint"}, "text": snippet}]},
        "provenance": {"overlay_id": "overlay-origin"}}
    obligations_path = tmp_path / "obligations.json"
    obligations_path.write_bytes(qc._bytes({"questions": {"fixture": {"question": q}}}))
    db_path = tmp_path / "db.sqlite"
    db_path.write_bytes(b"fixture-db")
    obligations = [{"obligation_id": "behavior.1", "kind": "behavior", "meaning": meaning}]
    obligations.extend({"obligation_id": f"behavior.{index + 2}", "kind": "behavior", "meaning": extra}
                       for index, extra in enumerate(extra_obligation_meanings))
    packet = {"question": q, "question_sha256": __import__("hashlib").sha256(q.encode()).hexdigest(),
        "obligation_id": "fixture", "obligations": obligations,
        "required_routes": ["source-bound"], "identity": {**identity,
            "obligations_file_path": str(obligations_path.resolve()),
            "obligations_file_sha256": __import__("hashlib").sha256(obligations_path.read_bytes()).hexdigest()},
        "candidates": [candidate], "packet_sha256": "selection-hash", "semantic_sha256": "semantic-hash"}
    source = tmp_path / "source-run"
    source.mkdir()
    selection_record = {"reviewer_identity": "auditor", "reviewer_model": "GPT-6.1 Sol High",
        "obligation_reviews": [{"obligation_id": item["obligation_id"], "candidate_status": "absent_from_candidates",
                                "supporting_route_fact_ids": [], "basis": "The bounded map set omits the numeric declaration."}
                               for item in obligations]}
    gap = {"schema_version": 1, "result": "evidence_gap", "packet_sha256": "selection-hash",
           "package_sha256": "gap-hash", "selection_record": selection_record,
           "selected_route_fact_ids": ["route-origin"], "completeness_claim": False}
    (source / "evidence-gap.json").write_bytes(qc._bytes(gap))
    (source / "selection-packet.json").write_bytes(qc._bytes({"fixture": True}))
    (source / "candidate-observations.json").write_bytes(qc._bytes({"fixture": True}))
    monkeypatch.setattr(qc, "_revalidate", lambda *_args: packet)
    monkeypatch.setattr(qc.atlas, "_current_route_snapshot", lambda *_args: (snapshot, {}, "extractor", live))
    monkeypatch.setattr(qc.atlas, "_repo_root", lambda *_args: repo)
    def read_working_file(_fd, _path, collect_source=False):
        return {"presence": "missing"} if unsafe_source else {"presence": "present", "type": "file", "sha256": source_hash, "_source_bytes": raw}
    monkeypatch.setattr(qc.atlas, "_read_working_file", read_working_file)
    return {"repo": str(repo), "db": str(db_path), "source": source,
            "destination": tmp_path / "expansion", "obligations": obligations_path,
            "packet": packet, "gap": gap, "source_bytes": (source / "evidence-gap.json").read_bytes(), "source_text": file_text,
            "snapshot": snapshot, "raw": raw, "source_path": path, "live": live}


def _expand_fixture(fixture: dict[str, object], *, destination: Path | None = None, max_bytes: int = 2_000_000):
    return qc.expand_gap_prepare(str(fixture["repo"]), str(fixture["db"]), str(fixture["source"]),
        str(destination or fixture["destination"]), str(fixture["obligations"]), max_bytes)


def _replace_with_v1_expansion_packet(fixture: dict[str, object]) -> dict[str, object]:
    packet = qc._build_gap_expansion_packet(str(fixture["repo"]), str(fixture["db"]), str(fixture["source"]),
        str(fixture["destination"]), str(fixture["obligations"]), 2_000_000, expansion_schema_version=1)
    (fixture["destination"] / qc.EXPANSION_PACKET).write_bytes(qc._bytes(packet))
    return packet


def _p1_review(packet: dict[str, object], *, classifications: list[str] | None = None,
               decision: str = "accepted", selected_by_obligation: list[list[str]] | None = None) -> dict[str, object]:
    schema = qc.EXPANSION_REVIEW_SCHEMA if packet.get("expansion_schema_version") == qc.EXPANSION_SCHEMA_VERSION else qc._EXPANSION_REVIEW_SCHEMA_V1
    absent = packet["absent_obligations"]
    classifications = classifications or ["local_evidence" if item["eligible_candidate_ids"] else "external_or_unresolved" for item in absent]
    if selected_by_obligation is None:
        selected_by_obligation = [item["eligible_candidate_ids"][:1] if classification == "local_evidence" else []
                                  for item, classification in zip(absent, classifications, strict=True)]
    obligation_reviews = [{"obligation_id": item["obligation"]["obligation_id"], "classification": classification,
        "selected_candidate_ids": selected, "basis": "Sol confirms the declaration semantically answers this obligation."}
        for item, classification, selected in zip(absent, classifications, selected_by_obligation, strict=True)]
    selected = {candidate_id for item in obligation_reviews for candidate_id in item["selected_candidate_ids"]}
    return {"review_schema_version": schema["version"], "packet_sha256": packet["packet_sha256"],
        "reviewer_identity": "sol-reviewer", "reviewer_model": schema["reviewer_model"], "decision": decision,
        "obligation_reviews": obligation_reviews,
        "candidate_reviews": [{"candidate_id": item["candidate_id"], "disposition": "selected" if item["candidate_id"] in selected else "not_selected",
            "basis": "Sol records this candidate disposition against the obligation classifications."}
            for item in packet["declaration_candidates"]]}


def _p1_review_file(tmp_path: Path, review: dict[str, object]) -> Path:
    path = tmp_path / "expansion-sol-review.json"
    path.write_bytes(qc._bytes(review))
    return path


def _review_fixture(fixture: dict[str, object], review: dict[str, object], review_file: Path):
    return qc.expand_gap_review(str(fixture["repo"]), str(fixture["db"]), str(fixture["source"]),
        str(fixture["destination"]), str(fixture["obligations"]), str(review_file))


def _status_fixture(fixture: dict[str, object]):
    return qc.expand_gap_status(str(fixture["repo"]), str(fixture["db"]), str(fixture["source"]),
        str(fixture["destination"]), str(fixture["obligations"]))


def test_gap_expansion_packet_is_canonical_idempotent_and_preserves_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_fixture(tmp_path, monkeypatch)
    before = fixture["source_bytes"]
    result = _expand_fixture(fixture)
    packet = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)
    assert packet["packet_sha256"] == qc._digest({key: value for key, value in packet.items() if key != "packet_sha256"})
    assert packet["source_run_path"] == str(fixture["source"].resolve())
    assert packet["destination_run_path"] == str(fixture["destination"].resolve())
    assert result["packet_sha256"] == packet["packet_sha256"]
    assert packet["search"]["grammar"] == qc.EXPANSION_GRAMMAR
    assert _expand_fixture(fixture) == result
    assert (fixture["source"] / "evidence-gap.json").read_bytes() == before
    use = packet["origin_uses"][0]
    use_span = use["identifier_use_span"]
    assert use_span["offset_unit"] == "unicode_codepoint"
    assert fixture["source_text"][use_span["start_offset"]:use_span["end_offset"]] == use["identifier"]
    assert packet["declaration_candidates"]
    candidate = packet["declaration_candidates"][0]
    assert candidate["source_anchor"]["sha256"] == __import__("hashlib").sha256(fixture["source_text"].encode()).hexdigest()
    assert fixture["source_text"][candidate["span"]["start_offset"]:candidate["span"]["end_offset"]] == candidate["snippet"]


def test_gap_expansion_lists_all_values_and_marks_only_same_owner_candidate_eligible(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_fixture(tmp_path, monkeypatch)
    _expand_fixture(fixture)
    packet = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)
    candidates = packet["declaration_candidates"]
    assert [item["literal"] for item in candidates] == ["10", "720", "90"]
    assert [item["literal"] for item in candidates if item["eligible_use_ids"]] == ["10"]
    assert candidates[0]["owner_type_id"] == "Demo.GetLegacyTimeslotsQueryHandler`0"
    assert all("not_same_file_and_lexical_owner_as_origin_use" in item["reasons"] for item in candidates[1:])
    assert packet["absent_obligations"][0]["eligible_candidate_ids"] == [candidates[0]["candidate_id"]]


def test_gap_expansion_does_not_fallback_when_no_local_declaration_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_fixture(tmp_path, monkeypatch, declaration="")
    _expand_fixture(fixture)
    packet = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)
    assert [item["literal"] for item in packet["declaration_candidates"]] == ["720", "90"]
    assert not packet["absent_obligations"][0]["eligible_candidate_ids"]
    assert "no_eligible_declaration" in packet["absent_obligations"][0]["unresolved_reasons"]


@pytest.mark.parametrize("kwargs, reason", [
    ({"conditional": True}, "conditional_directive"),
    ({"declaration": "public const int ChangeEventDays = Compute();"}, "unsupported_constant_syntax"),
    ({"ambiguous_owner": True}, "ambiguous_lexical_owner"),
    ({"extra_handler": "int ChangeEventDays = 12;"}, "shadowed_identifier_in_lexical_owner"),
    ({"unsafe_source": True}, "no_eligible_declaration"),
])
def test_gap_expansion_unsafe_or_ambiguous_candidates_stay_unresolved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kwargs, reason):
    fixture = _expansion_fixture(tmp_path, monkeypatch, **kwargs)
    _expand_fixture(fixture)
    packet = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)
    assert not packet["absent_obligations"][0]["eligible_candidate_ids"]
    all_reasons = {reason for item in packet["declaration_candidates"] for reason in item["reasons"]}
    all_reasons |= {item["reason"] for item in packet["exclusions"]}
    assert reason in all_reasons or reason == "no_eligible_declaration"


def test_gap_expansion_refuses_budget_and_changed_replay_or_reuse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_fixture(tmp_path, monkeypatch)
    with pytest.raises(qc.CoordinatorError, match="exceeds --max-bytes"):
        _expand_fixture(fixture, max_bytes=20)
    _expand_fixture(fixture)
    packet_path = fixture["destination"] / qc.EXPANSION_PACKET
    tampered = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)
    tampered["declaration_candidates"][0]["owner_type_id"] = "Demo.Forged`0"
    tampered["packet_sha256"] = qc._digest({key: value for key, value in tampered.items() if key != "packet_sha256"})
    packet_path.write_bytes(qc._bytes(tampered))
    with pytest.raises(qc.CoordinatorError, match="immutable artifact already exists"):
        _expand_fixture(fixture)


@pytest.mark.parametrize("schema_version", [1, 2])
def test_expansion_prepare_replay_binds_max_bytes_and_preserves_bytes(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, schema_version: int):
    fixture = _expansion_fixture(tmp_path, monkeypatch)
    _expand_fixture(fixture)
    packet = _replace_with_v1_expansion_packet(fixture) if schema_version == 1 else qc._read_artifact(
        fixture["destination"], qc.EXPANSION_PACKET)
    assert packet["expansion_schema_version"] == schema_version
    before = {item.name: item.read_bytes() for item in fixture["destination"].iterdir()}
    assert _expand_fixture(fixture)["packet_sha256"] == packet["packet_sha256"]
    assert {item.name: item.read_bytes() for item in fixture["destination"].iterdir()} == before
    with pytest.raises(qc.CoordinatorError, match=r"--max-bytes requested 2000001; saved expansion packet requires 2000000; supply the saved value"):
        _expand_fixture(fixture, max_bytes=2_000_001)
    assert {item.name: item.read_bytes() for item in fixture["destination"].iterdir()} == before
    with pytest.raises(qc.CoordinatorError, match=r"--max-bytes observed 0; required an exact integer in 1\.\.50000000"):
        _expand_fixture(fixture, max_bytes=0)
    assert {item.name: item.read_bytes() for item in fixture["destination"].iterdir()} == before


def test_gap_expansion_packet_cannot_be_reused_at_another_destination(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_fixture(tmp_path, monkeypatch)
    _expand_fixture(fixture)
    second = tmp_path / "second-expansion"
    second.mkdir()
    (second / qc.EXPANSION_PACKET).write_bytes((fixture["destination"] / qc.EXPANSION_PACKET).read_bytes())
    with pytest.raises(qc.CoordinatorError, match="immutable artifact already exists"):
        _expand_fixture(fixture, destination=second)


def test_gap_expansion_uses_full_source_qualification_even_when_map_snippet_is_clipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_fixture(tmp_path, monkeypatch, qualified_origin=True, clip_qualified_snippet=True)
    _expand_fixture(fixture)
    packet = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)
    use = packet["origin_uses"][0]
    assert use["snippet"] == "ChangeEventDays"
    assert use["qualification_context"]["qualified"] is True
    assert use["qualification_context"]["qualifier_token"] == "Other"
    assert not packet["absent_obligations"][0]["eligible_candidate_ids"]
    assert "origin_use_is_qualified" in packet["declaration_candidates"][0]["reasons"]


def test_gap_expansion_requires_unique_smallest_owner_for_origin_and_declaration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_fixture(tmp_path, monkeypatch, nested_origin_owner=True)
    _expand_fixture(fixture)
    packet = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)
    use = packet["origin_uses"][0]
    candidate = packet["declaration_candidates"][0]
    assert use["owner_fact_id"] == "type-nested-origin"
    assert candidate["owner_fact_id"] == "type-handler"
    assert not packet["absent_obligations"][0]["eligible_candidate_ids"]
    assert "origin_and_declaration_lexical_owner_mismatch" in candidate["reasons"]


@pytest.mark.parametrize("signature, extra", [
    ("public void Handle(Dictionary<string, int>[] ChangeEventDays)", ""),
    ("public void Handle()", "Dictionary<string, int>[] ChangeEventDays = null;"),
    ("public void Handle()", "var item = value is ChangeEventDays;"),
    ("public void Handle()", "Func<int, int> f = ChangeEventDays => ChangeEventDays;"),
    ("public void Handle()", "var (ChangeEventDays, other) = Pair();"),
    ("public void Handle()", "Try(out var ChangeEventDays);"),
])
def test_gap_expansion_refuses_method_scope_binding_collisions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, signature: str, extra: str):
    fixture = _expansion_fixture(tmp_path, monkeypatch, method_signature=signature, method_extra=extra)
    _expand_fixture(fixture)
    packet = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)
    assert not packet["absent_obligations"][0]["eligible_candidate_ids"]
    candidate = next(item for item in packet["declaration_candidates"] if item["literal"] == "10")
    assert candidate["reasons"]
    assert packet["search"]["binding_boundary"].startswith("lexical owner and conservative method/scope token analysis")


def test_gap_expansion_conditional_origin_use_stays_unresolved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_fixture(tmp_path, monkeypatch, conditional_origin=True)
    _expand_fixture(fixture)
    packet = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)
    assert packet["origin_uses"][0]["conditional"] is True
    assert not packet["absent_obligations"][0]["eligible_candidate_ids"]
    assert "conditional_origin_use" in packet["declaration_candidates"][0]["reasons"]


def test_gap_expansion_accounts_for_every_seeded_declarator_in_one_statement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_fixture(tmp_path, monkeypatch,
        multi_declaration="public const int ChangeEventDays = 10, Beta = 2;", extra_seed="Beta")
    _expand_fixture(fixture)
    packet = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)
    candidates = [item for item in packet["declaration_candidates"] if "Beta = 2" in item["snippet"]]
    assert [(item["identifier"], item["literal"]) for item in candidates] == [("Beta", "2"), ("ChangeEventDays", "10")]
    assert candidates[0]["span"] == candidates[1]["span"]
    assert candidates[0]["name_span"] != candidates[1]["name_span"]
    assert candidates[0]["initializer_span"] != candidates[1]["initializer_span"]


@pytest.mark.parametrize("statement", [
    "public const int OtherValue = 1 << 2, ChangeEventDays = 10;",
    "public const int OtherValue = (1 < 2 ? 1 : 0), ChangeEventDays = 10;",
    "public const int OtherValue = 8 >> 1, ChangeEventDays = 10;",
])
def test_gap_expansion_balances_only_delimiters_when_finding_later_declarators(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, statement: str):
    fixture = _expansion_fixture(tmp_path, monkeypatch, multi_declaration=statement)
    _expand_fixture(fixture)
    packet = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)
    candidate = next(item for item in packet["declaration_candidates"] if item["owner_fact_id"] == "type-handler")
    assert candidate["identifier"] == "ChangeEventDays"
    assert candidate["literal"] == "10"
    assert candidate["syntax_supported"] is True


def test_gap_expansion_parses_generic_type_prefix_before_later_declarator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_fixture(tmp_path, monkeypatch,
        multi_declaration="public const Dictionary<int, string> OtherValue = Make(), ChangeEventDays = 10;")
    _expand_fixture(fixture)
    packet = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)
    candidate = next(item for item in packet["declaration_candidates"] if item["owner_fact_id"] == "type-handler")
    assert candidate["identifier"] == "ChangeEventDays"
    assert candidate["literal"] == "10"
    assert candidate["type_prefix_classified"] is True
    assert candidate["syntax_supported"] is False
    assert "unsupported_constant_syntax" in candidate["reasons"]


@pytest.mark.parametrize("statement", [
    "public const int ChangeEventDays = 10",  # missing terminator before the next member
    "public const int OtherValue = (1 << 2, ChangeEventDays = 10;",  # unmatched delimiter
    "public const Dictionary<int, string ChangeEventDays = 10;",  # unclassifiable generic prefix
])
def test_gap_expansion_excludes_unprovable_statement_enumeration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, statement: str):
    fixture = _expansion_fixture(tmp_path, monkeypatch, multi_declaration=statement)
    _expand_fixture(fixture)
    packet = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)
    assert packet["search"]["complete"] is False
    assert not any(item["owner_fact_id"] == "type-handler" for item in packet["declaration_candidates"])
    assert any(item.get("identifier") == "ChangeEventDays" and item.get("incomplete") is True
               for item in packet["exclusions"])


@pytest.mark.parametrize("replacement", ["identical_symlink", "dangling_symlink", "directory"])
def test_gap_expansion_replay_rejects_non_regular_destination_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, replacement: str):
    fixture = _expansion_fixture(tmp_path, monkeypatch)
    _expand_fixture(fixture)
    path = fixture["destination"] / qc.EXPANSION_PACKET
    saved = path.read_bytes()
    path.unlink()
    if replacement == "identical_symlink":
        target = tmp_path / "identical.json"
        target.write_bytes(saved)
        path.symlink_to(target)
    elif replacement == "dangling_symlink":
        path.symlink_to(tmp_path / "missing.json")
    else:
        path.mkdir()
    with pytest.raises(qc.CoordinatorError, match="regular file"):
        _expand_fixture(fixture)


@pytest.mark.parametrize("tamper", ["candidate", "owner", "citation", "source", "lineage"])
def test_rehashed_expansion_tampering_is_refused_by_reconstruction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tamper: str):
    fixture = _expansion_fixture(tmp_path, monkeypatch)
    _expand_fixture(fixture)
    path = fixture["destination"] / qc.EXPANSION_PACKET
    packet = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)
    if tamper == "candidate":
        packet["declaration_candidates"][0]["literal"] = "999"
    elif tamper == "owner":
        packet["declaration_candidates"][0]["owner_type_id"] = "Forged.Owner`0"
    elif tamper == "citation":
        packet["origin_uses"][0]["citation"]["fact_id"] = "forged-fact"
    elif tamper == "source":
        packet["declaration_candidates"][0]["sha256"] = "0" * 64
    else:
        packet["source_gap_sha256"] = "0" * 64
    packet["packet_sha256"] = qc._digest({key: value for key, value in packet.items() if key != "packet_sha256"})
    path.write_bytes(qc._bytes(packet))
    with pytest.raises(qc.CoordinatorError, match="immutable artifact already exists"):
        _expand_fixture(fixture)


def test_gap_expansion_refuses_obligations_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_fixture(tmp_path, monkeypatch)
    packet = fixture["packet"]
    original_hash = packet["identity"]["obligations_file_sha256"]
    def revalidate(_run, _repo, _db, obligations_file):
        observed = __import__("hashlib").sha256(Path(obligations_file).read_bytes()).hexdigest()
        if observed != original_hash:
            raise qc.CoordinatorError("original obligations file SHA-256 changed")
        return packet
    monkeypatch.setattr(qc, "_revalidate", revalidate)
    fixture["obligations"].write_text("{}", encoding="utf-8")
    with pytest.raises(qc.CoordinatorError, match="obligations file SHA-256 changed"):
        _expand_fixture(fixture)
    assert not fixture["destination"].exists()


def test_gap_expansion_refuses_checkout_drift_and_source_run_reuse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(qc.atlas, "_current_route_snapshot", lambda *_args: ({"snapshot_id": "snapshot", "files": [], "source_graph": {"facts": []}}, {}, "extractor",
        {"repository_root": str(fixture["repo"]), "head": "new-head", "head_ref": "main", "status": []}))
    with pytest.raises(qc.CoordinatorError, match="checkout, status, snapshot, or extractor"):
        _expand_fixture(fixture)
    assert not fixture["destination"].exists()


def test_expansion_p1_template_schema_and_packet_only_status_are_read_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_fixture(tmp_path, monkeypatch)
    _expand_fixture(fixture)
    packet_path = fixture["destination"] / qc.EXPANSION_PACKET
    before = {item.name: item.read_bytes() for item in fixture["destination"].iterdir()}
    status = _status_fixture(fixture)
    assert status["state"] == "packet_only"
    template = qc._expansion_review_template(qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET))
    assert set(template) == set(qc.EXPANSION_REVIEW_SCHEMA["fields"])
    assert set(template["obligation_reviews"][0]) == set(qc.EXPANSION_REVIEW_SCHEMA["obligation_fields"])
    assert len(template["candidate_reviews"]) == len(qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)["declaration_candidates"])
    assert {item.name: item.read_bytes() for item in fixture["destination"].iterdir()} == before
    assert packet_path.read_bytes() == before[qc.EXPANSION_PACKET]


def _advertised_v2_review(packet: dict[str, object]) -> dict[str, object]:
    contract = packet["review_contract"]
    candidate_order = contract["candidate_reviews"]["ordered_candidate_ids"]
    obligation_reviews = []
    selected: set[str] = set()
    for obligation in contract["obligation_reviews"]["ordered_obligations"]:
        eligible = obligation["eligible_candidate_ids"]
        classification = "local_evidence" if eligible else "external_or_unresolved"
        ids = list(eligible[:1]) if classification == "local_evidence" else []
        selected.update(ids)
        obligation_reviews.append({"obligation_id": obligation["obligation_id"], "classification": classification,
            "selected_candidate_ids": ids, "basis": "Semantic review confirms the cited declaration supports this obligation."})
    review = {"review_schema_version": contract["review_schema_version"], "packet_sha256": packet["packet_sha256"],
        "reviewer_identity": "contract-derived-sol-review", "reviewer_model": contract["reviewer_model"]["exact"],
        "decision": "accepted", "obligation_reviews": obligation_reviews,
        "candidate_reviews": [{"candidate_id": candidate_id, "disposition": "selected" if candidate_id in selected else "not_selected",
            "basis": "Semantic review records this candidate's selected disposition."} for candidate_id in candidate_order]}
    assert set(review) == set(contract["exact_top_level_fields"])
    return review


def test_expansion_v2_contract_mirrors_validator_and_admits_contract_only_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_fixture(tmp_path, monkeypatch)
    prepared = _expand_fixture(fixture)
    packet_path = fixture["destination"] / qc.EXPANSION_PACKET
    packet = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)
    contract = packet["review_contract"]
    schema = qc.EXPANSION_REVIEW_SCHEMA
    assert packet["expansion_schema_version"] == 2 == qc.EXPANSION_SCHEMA_VERSION
    assert contract["review_schema_version"] == schema["version"] == 2
    assert contract["exact_top_level_fields"] == sorted(schema["fields"])
    assert contract["object_fields"] == {"top_level": sorted(schema["fields"]),
        "obligation_review": sorted(schema["obligation_fields"]), "candidate_review": sorted(schema["candidate_fields"])}
    assert contract["decision"]["allowed"] == schema["decisions"] == ["accepted", "rejected"]
    assert "ASCII-escaped" in contract["encoding"] and "exactly one trailing newline" in contract["encoding"]
    assert contract["reviewer_model"]["exact"] == schema["reviewer_model"]
    assert contract["obligation_reviews"]["ordered_obligations"] == [
        {"obligation_id": item["obligation"]["obligation_id"], "eligible_candidate_ids": item["eligible_candidate_ids"]}
        for item in packet["absent_obligations"]]
    assert contract["candidate_reviews"]["ordered_candidate_ids"] == [item["candidate_id"] for item in packet["declaration_candidates"]]
    template = qc._expansion_review_template(packet)
    assert set(template) == set(schema["fields"])
    review = _advertised_v2_review(packet)
    review_file = _p1_review_file(tmp_path, review)
    assert _review_fixture(fixture, review, review_file)["state"] == "local_expansion_ready"
    before = {item.name: item.read_bytes() for item in fixture["destination"].iterdir()}
    assert _status_fixture(fixture)["state"] == "local_expansion_ready"
    assert {item.name: item.read_bytes() for item in fixture["destination"].iterdir()} == before
    assert prepared["packet_sha256"] == packet["packet_sha256"]
    assert packet_path.read_bytes() == qc._bytes(packet)


CAPTURED_V1_EXPANSION_REVIEW_CONTRACT = {
    "review_schema_version": 1,
    "packet_sha256": "copy expansion-review-packet.json packet_sha256 exactly",
    "reviewer_identity": "nonempty audit label, not authentication",
    "reviewer_model": "GPT-6.1 Sol High audit label, not authentication",
    "obligation_reviews": {"coverage": "one ordered entry for every absent_obligations item",
        "fields": ["obligation_id", "classification", "selected_candidate_ids", "basis"],
        "classification": {"local_evidence": "may select only exact candidate IDs listed eligible_candidate_ids for this obligation",
            "external_or_unresolved": "selected_candidate_ids must be empty"}},
    "candidate_reviews": {"coverage": "account for every declaration_candidates item exactly once",
        "fields": ["candidate_id", "disposition", "basis"], "disposition": ["selected", "not_selected"]},
    "rules": "Every absent obligation and every candidate must be accounted for exactly once. Local evidence requires semantic confirmation that the cited declaration supplies the missing fact; eligibility is only a code-owned lexical boundary. Candidates are leads, not evidence until reviewed. Labels are audit labels, not authentication."
}


def test_captured_v1_contract_omission_remains_rejected_and_replay_is_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_fixture(tmp_path, monkeypatch)
    _expand_fixture(fixture)
    packet = qc._build_gap_expansion_packet(str(fixture["repo"]), str(fixture["db"]), str(fixture["source"]),
        str(fixture["destination"]), str(fixture["obligations"]), 2_000_000, expansion_schema_version=1)
    assert packet["review_contract"] == CAPTURED_V1_EXPANSION_REVIEW_CONTRACT
    packet_path = fixture["destination"] / qc.EXPANSION_PACKET
    packet_path.write_bytes(qc._bytes(packet))
    before = packet_path.read_bytes()
    # Captured provenance: P2a hash-fix run's timeslots-retry-expansion packet contract
    # omitted top-level `decision`; its packet-only Sol review therefore omitted it and
    # was refused by expand-gap-review. This embeds that precise failing shape without
    # reading or modifying the preserved /private/tmp artifacts.
    review = {"review_schema_version": 1, "packet_sha256": packet["packet_sha256"],
        "reviewer_identity": "captured-sol-reviewer", "reviewer_model": "GPT-6.1 Sol High",
        "obligation_reviews": [{"obligation_id": item["obligation"]["obligation_id"],
            "classification": "local_evidence", "selected_candidate_ids": item["eligible_candidate_ids"][:1],
            "basis": "The candidate declaration appears to support this obligation."} for item in packet["absent_obligations"]],
        "candidate_reviews": [{"candidate_id": item["candidate_id"], "disposition": "not_selected",
            "basis": "Candidate disposition recorded by the reviewer."} for item in packet["declaration_candidates"]]}
    review_file = _p1_review_file(tmp_path, review)
    review_bytes = review_file.read_bytes()
    with pytest.raises(qc.CoordinatorError, match="missing fields.*decision.*required correction"):
        _review_fixture(fixture, review, review_file)
    assert not (fixture["destination"] / qc.EXPANSION_REVIEW).exists()
    assert not (fixture["destination"] / qc.EXPANSION_PACKAGE).exists()
    assert packet_path.read_bytes() == before
    assert review_file.read_bytes() == review_bytes
    assert _expand_fixture(fixture)["packet_sha256"] == packet["packet_sha256"]
    assert packet_path.read_bytes() == before


@pytest.mark.parametrize("bad_version", [None, True, 1.0, "2", 3])
def test_expansion_packet_versions_reject_invalid_types_and_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad_version: object):
    fixture = _expansion_fixture(tmp_path, monkeypatch)
    _expand_fixture(fixture)
    path = fixture["destination"] / qc.EXPANSION_PACKET
    packet = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)
    packet["expansion_schema_version"] = bad_version
    packet["packet_sha256"] = qc._digest({key: value for key, value in packet.items() if key != "packet_sha256"})
    path.write_bytes(qc._bytes(packet))
    with pytest.raises(qc.CoordinatorError, match="expansion packet version observed"):
        _status_fixture(fixture)


def test_expansion_packet_rejects_rehashed_mixed_v1_v2_contracts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_fixture(tmp_path, monkeypatch)
    _expand_fixture(fixture)
    path = fixture["destination"] / qc.EXPANSION_PACKET
    packet = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)
    packet["review_contract"] = CAPTURED_V1_EXPANSION_REVIEW_CONTRACT
    packet["packet_sha256"] = qc._digest({key: value for key, value in packet.items() if key != "packet_sha256"})
    path.write_bytes(qc._bytes(packet))
    with pytest.raises(qc.CoordinatorError, match="does not exactly reconstruct"):
        _status_fixture(fixture)


@pytest.mark.parametrize("level", ["top", "obligation", "candidate"])
def test_expansion_review_field_refusals_name_all_differences_and_correction(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, level: str):
    fixture = _expansion_fixture(tmp_path, monkeypatch)
    _expand_fixture(fixture)
    packet = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)
    review = _advertised_v2_review(packet)
    if level == "top":
        review.pop("reviewer_model")
        review["unrequested"] = "value"
        expected = r"missing fields.*reviewer_model.*unexpected fields.*unrequested.*required correction"
    elif level == "obligation":
        review["obligation_reviews"][0].pop("basis")
        review["obligation_reviews"][0]["unrequested"] = "value"
        expected = r"obligation review.*missing fields.*basis.*unexpected fields.*unrequested.*required correction"
    else:
        review["candidate_reviews"][0].pop("basis")
        review["candidate_reviews"][0]["unrequested"] = "value"
        expected = r"candidate review.*missing fields.*basis.*unexpected fields.*unrequested.*required correction"
    review_file = _p1_review_file(tmp_path, review)
    packet_bytes = (fixture["destination"] / qc.EXPANSION_PACKET).read_bytes()
    with pytest.raises(qc.CoordinatorError, match=expected):
        _review_fixture(fixture, review, review_file)
    assert not (fixture["destination"] / qc.EXPANSION_REVIEW).exists()
    assert not (fixture["destination"] / qc.EXPANSION_PACKAGE).exists()
    assert (fixture["destination"] / qc.EXPANSION_PACKET).read_bytes() == packet_bytes


def test_expansion_review_invalid_decision_reports_observed_and_allowed_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_fixture(tmp_path, monkeypatch)
    _expand_fixture(fixture)
    packet = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)
    review = _advertised_v2_review(packet)
    review["decision"] = "conditionally-accepted"
    with pytest.raises(qc.CoordinatorError, match=r"observed 'conditionally-accepted'; allowed values are \['accepted', 'rejected'\]"):
        _review_fixture(fixture, review, _p1_review_file(tmp_path, review))
    assert not (fixture["destination"] / qc.EXPANSION_REVIEW).exists()
    assert not (fixture["destination"] / qc.EXPANSION_PACKAGE).exists()


def test_expansion_p1_local_package_and_status_reconstruct(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_fixture(tmp_path, monkeypatch)
    _expand_fixture(fixture)
    packet = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)
    review = _p1_review(packet)
    review_file = _p1_review_file(tmp_path, review)
    result = _review_fixture(fixture, review, review_file)
    package = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKAGE)
    assert result["state"] == "local_expansion_ready"
    assert package["package_type"] == "local_expansion"
    assert package["current_answer_authority"] is False
    assert package["full_question_completeness"] is False
    assert package["completeness_claim"] is False
    assert package["selected_declaration_evidence"][0]["evidence_kind"] == "supplemental_declaration_candidate"
    assert package["origin_use_evidence"][0]["evidence_kind"] == "origin_use_provenance"
    before_status = {item.name: item.read_bytes() for item in fixture["destination"].iterdir()}
    assert _status_fixture(fixture)["state"] == "local_expansion_ready"
    assert {item.name: item.read_bytes() for item in fixture["destination"].iterdir()} == before_status
    assert "original map receipt does not review these declarations" in package["review_authority_boundary"]


def test_expansion_p1_empty_candidates_and_rejected_review_are_review_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_fixture(tmp_path, monkeypatch, declaration="", no_candidates=True)
    _expand_fixture(fixture)
    packet = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)
    assert packet["declaration_candidates"] == []
    review = _p1_review(packet, decision="rejected")
    review_file = _p1_review_file(tmp_path, review)
    assert review["candidate_reviews"] == []
    assert _review_fixture(fixture, review, review_file)["state"] == "review_only"
    assert not (fixture["destination"] / qc.EXPANSION_PACKAGE).exists()
    assert _status_fixture(fixture)["state"] == "review_only"


def test_expansion_p1_external_package_and_mixed_review(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    external = _expansion_fixture(tmp_path / "external", monkeypatch, declaration="", no_candidates=True)
    _expand_fixture(external)
    packet = qc._read_artifact(external["destination"], qc.EXPANSION_PACKET)
    review = _p1_review(packet)
    result = _review_fixture(external, review, _p1_review_file(tmp_path, review))
    package = qc._read_artifact(external["destination"], qc.EXPANSION_PACKAGE)
    assert result["state"] == "external_or_unresolved"
    assert package["package_type"] == "external_or_unresolved"
    assert package["completeness_claim"] is False
    assert package["unresolved_obligations"] == [{"obligation_id": "behavior.1", "classification": "external_or_unresolved",
        "reason": "reviewed_external_or_unresolved"}]

    mixed = _expansion_fixture(tmp_path / "mixed", monkeypatch, extra_obligation_meanings=("A separate setting remains unknown.",))
    _expand_fixture(mixed)
    packet = qc._read_artifact(mixed["destination"], qc.EXPANSION_PACKET)
    review = _p1_review(packet, classifications=["local_evidence", "external_or_unresolved"])
    result = _review_fixture(mixed, review, _p1_review_file(tmp_path / "mixed", review))
    assert result["state"] == "external_or_unresolved"
    package = qc._read_artifact(mixed["destination"], qc.EXPANSION_PACKAGE)
    assert package["package_type"] == "external_or_unresolved"
    assert [item["obligation_id"] for item in package["unresolved_obligations"]] == ["behavior.2"]
    assert "selected_declaration_evidence" not in package


def _expansion_import_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, declaration: str = "public const int ChangeEventDays = 10;",
                              no_candidates: bool = False, classifications: list[str] | None = None,
                              conditional: bool = False,
                              extra_obligation_meanings: tuple[str, ...] = (),
                              mark_extra_source_obligations_present: bool = False,
                              schema_version: int = qc.EXPANSION_SCHEMA_VERSION):
    fixture = _expansion_fixture(tmp_path, monkeypatch, declaration="" if no_candidates else declaration,
        no_candidates=no_candidates, conditional=conditional,
        extra_obligation_meanings=extra_obligation_meanings)
    if mark_extra_source_obligations_present:
        gap = fixture["gap"]
        for item in gap["selection_record"]["obligation_reviews"][1:]:
            item["candidate_status"] = "present_in_candidates"
            item["supporting_route_fact_ids"] = ["route-origin"]
            item["basis"] = "The ordinary selected map provides source support for this separate obligation."
        (fixture["source"] / "evidence-gap.json").write_bytes(qc._bytes(gap))
        fixture["source_bytes"] = (fixture["source"] / "evidence-gap.json").read_bytes()
    _expand_fixture(fixture)
    packet = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)
    if schema_version == 1:
        packet = _replace_with_v1_expansion_packet(fixture)
    review = _p1_review(packet, classifications=classifications)
    _review_fixture(fixture, review, _p1_review_file(tmp_path, review))
    ordinary = fixture["packet"]
    (fixture["source"] / "selection-packet.json").write_bytes(qc._bytes(ordinary))
    question_file = tmp_path / "question.txt"
    question_file.write_text(ordinary["question"], encoding="utf-8")
    candidates = []
    for item in ordinary["candidates"]:
        candidates.append({**item, "observations": {"freshness": {"checked_at": "2026-10-08T00:00:00Z"},
            "budget": {"limit": 10_000_000, "used": 1}}})
    monkeypatch.setattr(qc, "_build_prepared_selection", lambda *_args, **_kwargs: (ordinary, candidates))
    fixture["question_file"] = question_file
    fixture["target"] = tmp_path / "target-run"
    return fixture


def _import_prepare_fixture(fixture: dict[str, object], *, target: Path | None = None):
    return qc.expand_gap_import_prepare(str(fixture["repo"]), str(fixture["db"]), str(fixture["source"]),
        str(fixture["destination"]), str(target or fixture["target"]), str(fixture["question_file"]),
        str(fixture["obligations"]))


def _import_status_fixture(fixture: dict[str, object], *, target: Path | None = None):
    return qc.expand_gap_import_status(str(fixture["repo"]), str(fixture["db"]), str(fixture["source"]),
        str(fixture["destination"]), str(target or fixture["target"]), str(fixture["question_file"]),
        str(fixture["obligations"]))


@pytest.mark.parametrize("schema_version", [1, 2])
def test_expansion_prepare_replay_after_import_validates_lineage_read_only(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, schema_version: int):
    fixture = _expansion_import_fixture(tmp_path, monkeypatch, schema_version=schema_version)
    _import_prepare_fixture(fixture)
    expansion_before = {item.name: item.read_bytes() for item in fixture["destination"].iterdir()}
    target_before = {item.name: item.read_bytes() for item in fixture["target"].iterdir()}
    replay = _expand_fixture(fixture)
    assert replay["packet_sha256"] == qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)["packet_sha256"]
    assert {item.name: item.read_bytes() for item in fixture["destination"].iterdir()} == expansion_before
    assert {item.name: item.read_bytes() for item in fixture["target"].iterdir()} == target_before
    assert _status_fixture(fixture)["state"] == "local_expansion_ready"
    assert _import_status_fixture(fixture)["state"] == "expanded_packet_prepared"


@pytest.mark.parametrize("defect", ["missing_review_package", "missing_package", "missing_review", "symlink", "rehash", "unrelated"])
def test_expansion_prepare_replay_refuses_broken_import_lineage_without_writes(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, defect: str):
    fixture = _expansion_import_fixture(tmp_path, monkeypatch)
    _import_prepare_fixture(fixture)
    destination = fixture["destination"]
    binding_path = destination / qc.EXPANSION_IMPORT_BINDING
    if defect == "missing_review_package":
        (destination / qc.EXPANSION_REVIEW).unlink()
        (destination / qc.EXPANSION_PACKAGE).unlink()
    elif defect == "missing_package":
        (destination / qc.EXPANSION_PACKAGE).unlink()
    elif defect == "missing_review":
        (destination / qc.EXPANSION_REVIEW).unlink()
    elif defect == "symlink":
        target = tmp_path / "binding-target.json"
        target.write_bytes(binding_path.read_bytes())
        binding_path.unlink()
        binding_path.symlink_to(target)
    elif defect == "rehash":
        binding = qc._read_artifact(destination, qc.EXPANSION_IMPORT_BINDING)
        binding["support_joins"][0]["route_fact_id"] = "forged-route"
        binding["binding_sha256"] = qc._digest({key: value for key, value in binding.items() if key != "binding_sha256"})
        binding_path.write_bytes(qc._bytes(binding))
    else:
        (destination / "unrelated.txt").write_text("occupied", encoding="utf-8")
    expansion_before = {item.name: (item.is_symlink(), item.read_bytes()) for item in destination.iterdir() if item.is_file() or item.is_symlink()}
    target_before = {item.name: item.read_bytes() for item in fixture["target"].iterdir()}
    with pytest.raises(qc.CoordinatorError):
        _expand_fixture(fixture)
    expansion_after = {item.name: (item.is_symlink(), item.read_bytes()) for item in destination.iterdir() if item.is_file() or item.is_symlink()}
    assert expansion_after == expansion_before
    assert {item.name: item.read_bytes() for item in fixture["target"].iterdir()} == target_before


def _enable_expanded_revalidation(fixture: dict[str, object], monkeypatch: pytest.MonkeyPatch):
    def revalidate(run, repo, db, obligations_file, expansion_run_dir=None):
        saved = qc._read_artifact(Path(run), "selection-packet.json")
        if "expansion_binding_lineage" in saved:
            return _ORIGINAL_REVALIDATE(run, repo, db, obligations_file, expansion_run_dir)
        return fixture["packet"]
    monkeypatch.setattr(qc, "_revalidate", revalidate)


def test_expansion_import_prepare_binds_exact_local_support_and_status_is_read_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_import_fixture(tmp_path, monkeypatch)
    before_source = {path.name: path.read_bytes() for path in fixture["source"].iterdir() if path.is_file()}
    first = _import_prepare_fixture(fixture)
    packet = qc._read_artifact(fixture["target"], "selection-packet.json")
    observations = qc._read_artifact(fixture["target"], "candidate-observations.json")
    binding = qc._read_artifact(fixture["destination"], qc.EXPANSION_IMPORT_BINDING)
    assert set(binding) == qc.EXPANSION_IMPORT_BINDING_FIELDS
    assert binding["binding_schema_version"] == 1
    assert binding["binding_sha256"] == qc._digest({key: value for key, value in binding.items() if key != "binding_sha256"})
    assert first["state"] == "expanded_packet_prepared"
    assert packet["packet_sha256"] == qc._digest({key: value for key, value in packet.items() if key != "packet_sha256"})
    assert packet["candidates"] == fixture["packet"]["candidates"]
    assert packet["supplemental_evidence"]["current_answer_authority"] is False
    assert packet["supplemental_evidence"]["full_question_completeness"] is False
    assert packet["supplemental_evidence"]["completeness_claim"] is False
    assert len(packet["supplemental_evidence"]["records"]) == 1
    record = packet["supplemental_evidence"]["records"][0]
    assert record["obligation_id"] == "behavior.1"
    assert record["declaration"]["literal"] == "10"
    assert record["origin_use"]["route_fact_id"] == "route-origin"
    assert packet["semantic_sha256"] != fixture["packet"]["semantic_sha256"]
    assert observations["selection_packet_sha256"] == packet["packet_sha256"]
    packet_bytes = (fixture["target"] / "selection-packet.json").read_bytes()
    assert _import_prepare_fixture(fixture) == first
    prior = {path.name: path.read_bytes() for path in fixture["target"].iterdir()}
    status = _import_status_fixture(fixture)
    assert status["state"] == "expanded_packet_prepared"
    assert (fixture["target"] / "selection-packet.json").read_bytes() == packet_bytes
    assert {path.name: path.read_bytes() for path in fixture["target"].iterdir()} == prior
    assert {path.name: path.read_bytes() for path in fixture["source"].iterdir() if path.is_file()} == before_source


def _expanded_selection_record(packet: dict[str, object], *, status: str = "present_in_candidates",
                               supporters: list[str] | None = None, decision: str = "accept") -> dict[str, object]:
    route_ids = [item["route"]["id"] for item in packet["candidates"]]
    supporters = route_ids if supporters is None else supporters
    return {"selection_schema_version": 1, "packet_sha256": packet["packet_sha256"],
        "reviewer_identity": "expanded-selector-auditor", "reviewer_model": "GPT-6.1 Sol High",
        "candidate_reviews": [{"route_fact_id": route_id, "decision": decision,
            "basis": "This selected route contributes its reviewed map to the required answer."} for route_id in route_ids],
        "obligation_reviews": [{"obligation_id": item["obligation_id"], "candidate_status": status,
            "supporting_route_fact_ids": list(supporters),
            "basis": "The map route is retained alongside the separately reviewed supplemental declaration."}
            for item in packet["obligations"]]}


def test_expansion_p2b_selector_view_is_exact_and_read_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_import_fixture(tmp_path, monkeypatch)
    _import_prepare_fixture(fixture)
    _enable_expanded_revalidation(fixture, monkeypatch)
    before_target = {item.name: item.read_bytes() for item in fixture["target"].iterdir()}
    before_expansion = {item.name: item.read_bytes() for item in fixture["destination"].iterdir()}
    view = qc.expand_gap_selector_view(str(fixture["repo"]), str(fixture["db"]), str(fixture["target"]),
        str(fixture["obligations"]), str(fixture["destination"]))
    packet = qc._read_artifact(fixture["target"], "selection-packet.json")
    assert view == qc._expansion_selector_view(packet)
    assert view["selection_packet_sha256"] == packet["packet_sha256"]
    assert view["semantic_answer_claim"] is False
    group = view["supplemental_obligations"][0]
    assert group["supporting_route_fact_ids"] == ["route-origin"]
    assert group["route_candidate_ids_must_remain_accepted"] == ["route-origin"]
    assert group["declaration_candidate_ids"]
    assert "must equal" in view["support_rule"]
    assert {item.name: item.read_bytes() for item in fixture["target"].iterdir()} == before_target
    assert {item.name: item.read_bytes() for item in fixture["destination"].iterdir()} == before_expansion
    with pytest.raises(qc.CoordinatorError, match="requires --expansion-run-dir"):
        _ORIGINAL_REVALIDATE(fixture["target"], str(fixture["repo"]), str(fixture["db"]), str(fixture["obligations"]))
    wrong_expansion = tmp_path / "wrong-expansion"
    wrong_expansion.mkdir()
    with pytest.raises(qc.CoordinatorError, match="exact bound --expansion-run-dir"):
        _ORIGINAL_REVALIDATE(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
            str(fixture["obligations"]), str(wrong_expansion))


def test_expansion_p2b_rejects_an_extra_valid_but_unbound_map_route(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_import_fixture(tmp_path, monkeypatch)
    _import_prepare_fixture(fixture)
    packet = qc._read_artifact(fixture["target"], "selection-packet.json")
    packet["candidates"].append({"route": {"id": "route-extra", "route_literal": "api/extra"},
        "map": {}, "provenance": {}})
    record = _expanded_selection_record(packet, supporters=["route-origin", "route-extra"])
    with pytest.raises(qc.CoordinatorError, match="supporting_route_fact_ids must equal its bound supplemental route set exactly"):
        qc._check_expanded_selection_support(packet, record)


def test_expansion_p2b_status_rejects_dangling_selection_symlink(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_import_fixture(tmp_path, monkeypatch)
    _import_prepare_fixture(fixture)
    _enable_expanded_revalidation(fixture, monkeypatch)
    (fixture["target"] / "selection.json").symlink_to(tmp_path / "missing-selection.json")
    with pytest.raises(qc.CoordinatorError, match="no-follow regular file"):
        qc.status(fixture["target"], str(fixture["repo"]), str(fixture["db"]), str(fixture["obligations"]),
            str(fixture["destination"]))


def test_expansion_p2b_refuses_conflicting_reused_source_snippet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_import_fixture(tmp_path, monkeypatch)
    fixture["packet"]["candidates"][0]["provenance"].update({"binding_hash": "binding-origin",
        "association_review_hash": "association-origin", "flow_review_receipt": {"receipt_hash": "receipt-origin"}})
    (fixture["source"] / "selection-packet.json").write_bytes(qc._bytes(fixture["packet"]))
    _import_prepare_fixture(fixture)
    packet = qc._read_artifact(fixture["target"], "selection-packet.json")
    union = qc._selected_union(packet, [packet["candidates"][0]])
    declaration = packet["supplemental_evidence"]["records"][0]["declaration"]
    anchor = next(item for item in union["source_anchors"]
        if item["path"] == declaration["path"] and item["sha256"] == declaration["sha256"])
    union["source_snippets"].append({"snippet_id": "conflicting-snippet", "source_id": anchor["source_id"],
        "span": declaration["span"], "text": "different declaration text"})
    with pytest.raises(qc.CoordinatorError, match="collides with different text"):
        qc._build_expanded_answer_packet(packet, {}, union)


def test_expansion_p2b_full_path_preserves_supplemental_support_while_emitting_ordinary_gap(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_import_fixture(tmp_path, monkeypatch,
        extra_obligation_meanings=("A separate ordinary behavior remains unproven.",),
        mark_extra_source_obligations_present=True)
    fixture["packet"]["candidates"][0]["provenance"].update({"binding_hash": "binding-origin",
        "association_review_hash": "association-origin", "flow_review_receipt": {"receipt_hash": "receipt-origin"}})
    (fixture["source"] / "selection-packet.json").write_bytes(qc._bytes(fixture["packet"]))
    _import_prepare_fixture(fixture)
    _enable_expanded_revalidation(fixture, monkeypatch)
    packet = qc._read_artifact(fixture["target"], "selection-packet.json")
    record = _expanded_selection_record(packet)
    ordinary_obligation = record["obligation_reviews"][1]
    ordinary_obligation["candidate_status"] = "absent_from_candidates"
    ordinary_obligation["supporting_route_fact_ids"] = []
    ordinary_obligation["basis"] = "The selected ordinary maps do not establish this separate behavior."
    selection_file = tmp_path / "ordinary-gap-selection.json"
    selection_file.write_bytes(qc._bytes(record))
    gap = qc._write_selection(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
        str(selection_file), str(fixture["obligations"]), str(fixture["destination"]))
    saved_gap = qc._read_artifact(fixture["target"], "evidence-gap.json")
    saved_selection = qc._read_artifact(fixture["target"], "selection.json")
    assert gap["state"] == "evidence_gap"
    assert saved_gap["absent_obligations"] == [ordinary_obligation]
    assert saved_gap["current_answer_authority"] is False
    assert saved_gap["full_question_completeness"] is False
    assert saved_gap["completeness_claim"] is False
    assert saved_gap["selection"] == saved_selection
    assert saved_gap["expansion_binding_sha256"] == saved_selection["supplemental_selection_authority"]["expansion_binding_sha256"]
    assert saved_gap["expansion_package_sha256"] == saved_selection["supplemental_selection_authority"]["expansion_package_sha256"]
    partial_claims = saved_gap["supported_partial_coverage"]["claims"]
    supplemental = [item for item in partial_claims if item["provenance"].get("evidence_kind") == "supplemental_declaration"]
    assert len(supplemental) == 1
    assert supplemental[0]["provenance"]["obligation_id"] == "behavior.1"
    assert not (fixture["target"] / "answer-packet.json").exists()
    gap_bytes = (fixture["target"] / "evidence-gap.json").read_bytes()
    assert qc._write_selection(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
        str(selection_file), str(fixture["obligations"]), str(fixture["destination"])) == gap
    assert (fixture["target"] / "evidence-gap.json").read_bytes() == gap_bytes
    result = qc.status(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
        str(fixture["obligations"]), str(fixture["destination"]))
    assert result["result"] == "current"
    assert result["terminal"] == "evidence_gap"
    assert not (fixture["target"] / "answer-packet.json").exists()
    before_gap = {path.name: path.read_bytes() for path in fixture["target"].iterdir()}
    with pytest.raises(qc.CoordinatorError, match="cannot enter answer or correction stages"):
        qc.submit_answer(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
            str(fixture["obligations"]), str(tmp_path / "missing-draft.txt"), str(tmp_path / "missing-answer.json"),
            correction=True, expansion_run_dir=str(fixture["destination"]))
    assert {path.name: path.read_bytes() for path in fixture["target"].iterdir()} == before_gap


@pytest.mark.parametrize("tamper", [
    "partial_evidence", "gap_lineage", "absent_obligation", "authority_flag", "package_hash", "binding_hash",
])
def test_expansion_p2b_rejects_rehashed_gap_tampering(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tamper: str):
    fixture = _expansion_import_fixture(tmp_path,
        monkeypatch,
        extra_obligation_meanings=("A separate ordinary behavior remains unproven.",),
        mark_extra_source_obligations_present=True)
    fixture["packet"]["candidates"][0]["provenance"].update({"binding_hash": "binding-origin",
        "association_review_hash": "association-origin", "flow_review_receipt": {"receipt_hash": "receipt-origin"}})
    (fixture["source"] / "selection-packet.json").write_bytes(qc._bytes(fixture["packet"]))
    _import_prepare_fixture(fixture)
    _enable_expanded_revalidation(fixture, monkeypatch)
    packet = qc._read_artifact(fixture["target"], "selection-packet.json")
    record = _expanded_selection_record(packet)
    ordinary = record["obligation_reviews"][1]
    ordinary["candidate_status"] = "absent_from_candidates"
    ordinary["supporting_route_fact_ids"] = []
    ordinary["basis"] = "The selected ordinary maps do not establish this separate behavior."
    selection_file = tmp_path / "selection.json"
    selection_file.write_bytes(qc._bytes(record))
    qc._write_selection(fixture["target"], str(fixture["repo"]), str(fixture["db"]), str(selection_file),
        str(fixture["obligations"]), str(fixture["destination"]))
    path = fixture["target"] / "evidence-gap.json"
    gap = qc._read_artifact(fixture["target"], "evidence-gap.json")
    if tamper == "partial_evidence":
        gap["supported_partial_coverage"]["claims"][-1]["claim"] = "forged supplemental evidence"
    elif tamper == "gap_lineage":
        gap["expansion_lineage"]["review_sha256"] = "forged-review"
    elif tamper == "absent_obligation":
        gap["absent_obligations"] = []
    elif tamper == "authority_flag":
        gap["current_answer_authority"] = True
    elif tamper == "package_hash":
        gap["expansion_package_sha256"] = "forged-package"
    else:
        gap["expansion_binding_sha256"] = "forged-binding"
    gap["package_sha256"] = qc._digest({key: value for key, value in gap.items() if key != "package_sha256"})
    path.write_bytes(qc._bytes(gap))
    with pytest.raises(qc.CoordinatorError, match="does not reconstruct"):
        qc.status(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
            str(fixture["obligations"]), str(fixture["destination"]))


@pytest.mark.parametrize("artifact_kind", ["unknown", "dangling_gap"])
def test_expansion_p2b_gap_status_rejects_unknown_or_unsafe_artifacts(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, artifact_kind: str):
    fixture = _expansion_import_fixture(tmp_path, monkeypatch,
        extra_obligation_meanings=("A separate ordinary behavior remains unproven.",),
        mark_extra_source_obligations_present=True)
    fixture["packet"]["candidates"][0]["provenance"].update({"binding_hash": "binding-origin",
        "association_review_hash": "association-origin", "flow_review_receipt": {"receipt_hash": "receipt-origin"}})
    (fixture["source"] / "selection-packet.json").write_bytes(qc._bytes(fixture["packet"]))
    _import_prepare_fixture(fixture)
    _enable_expanded_revalidation(fixture, monkeypatch)
    packet = qc._read_artifact(fixture["target"], "selection-packet.json")
    record = _expanded_selection_record(packet)
    ordinary = record["obligation_reviews"][1]
    ordinary["candidate_status"] = "absent_from_candidates"
    ordinary["supporting_route_fact_ids"] = []
    ordinary["basis"] = "The selected ordinary maps do not establish this separate behavior."
    selection_file = tmp_path / "selection.json"
    selection_file.write_bytes(qc._bytes(record))
    qc._write_selection(fixture["target"], str(fixture["repo"]), str(fixture["db"]), str(selection_file),
        str(fixture["obligations"]), str(fixture["destination"]))
    if artifact_kind == "unknown":
        (fixture["target"] / "unknown-stage.json").write_bytes(b"{}")
        expected = "unrelated artifacts"
    else:
        (fixture["target"] / "evidence-gap.json").unlink()
        (fixture["target"] / "evidence-gap.json").symlink_to(tmp_path / "missing-gap.json")
        expected = "no-follow regular file"
    with pytest.raises(qc.CoordinatorError, match=expected):
        qc.status(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
            str(fixture["obligations"]), str(fixture["destination"]))


@pytest.mark.parametrize("status,supporters,decision,diagnostic", [
    ("absent_from_candidates", [], "accept", "must be present"),
    ("present_in_candidates", [], "accept", "present but names no supporting candidate"),
    ("present_in_candidates", ["route-origin", "extra-route"], "accept", "supporting_route_fact_ids must be unique candidate IDs"),
    ("present_in_candidates", ["route-origin"], "reject", "was rejected"),
])
def test_expansion_p2b_selection_requires_exact_accepted_supplemental_routes(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status, supporters, decision, diagnostic):
    fixture = _expansion_import_fixture(tmp_path, monkeypatch)
    _import_prepare_fixture(fixture)
    _enable_expanded_revalidation(fixture, monkeypatch)
    packet = qc._read_artifact(fixture["target"], "selection-packet.json")
    record = _expanded_selection_record(packet, status=status, supporters=supporters, decision=decision)
    record_file = tmp_path / "selection.json"
    record_file.write_bytes(qc._bytes(record))
    with pytest.raises(qc.CoordinatorError, match=diagnostic):
        qc._write_selection(fixture["target"], str(fixture["repo"]), str(fixture["db"]), str(record_file),
            str(fixture["obligations"]), str(fixture["destination"]))
    assert not (fixture["target"] / "selection.json").exists()
    assert not (fixture["target"] / "answer-packet.json").exists()


def test_expansion_p2b_selection_builds_separate_authority_and_recovers_partial_save(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_import_fixture(tmp_path, monkeypatch)
    fixture["packet"]["candidates"][0]["provenance"].update({"binding_hash": "binding-origin",
        "association_review_hash": "association-origin", "flow_review_receipt": {"receipt_hash": "receipt-origin"}})
    (fixture["source"] / "selection-packet.json").write_bytes(qc._bytes(fixture["packet"]))
    _import_prepare_fixture(fixture)
    _enable_expanded_revalidation(fixture, monkeypatch)
    packet = qc._read_artifact(fixture["target"], "selection-packet.json")
    record = _expanded_selection_record(packet)
    record_file = tmp_path / "selection.json"
    record_file.write_bytes(qc._bytes(record))
    result = qc._write_selection(fixture["target"], str(fixture["repo"]), str(fixture["db"]), str(record_file),
        str(fixture["obligations"]), str(fixture["destination"]))
    selection = qc._read_artifact(fixture["target"], "selection.json")
    answer = qc._read_artifact(fixture["target"], "answer-packet.json")
    authority = selection["supplemental_selection_authority"]
    assert authority["authority_schema_version"] == 1
    assert authority["authority_sha256"] == qc._digest({key: value for key, value in authority.items() if key != "authority_sha256"})
    assert authority["selection_packet_sha256"] == packet["packet_sha256"]
    assert authority["obligations"][0]["joins"][0]["route_fact_id"] == "route-origin"
    original_union = qc._selected_union(packet, [packet["candidates"][0]])
    assert answer["claims"][:len(original_union["claims"])] == original_union["claims"]
    assert answer["source_anchors"][:len(original_union["source_anchors"])] == original_union["source_anchors"]
    assert answer["source_snippets"][:len(original_union["source_snippets"])] == original_union["source_snippets"]
    assert len(answer["claims"]) == len(original_union["claims"]) + 1
    assert answer["claims"][-1]["claim"] == "public const int ChangeEventDays = 10;"
    assert set(answer["claims"][-1]["evidence"][0]) == set(qc.ANSWER_RECORD_SCHEMA["citation_fields"])
    assert answer["claims"][-1]["provenance"]["old_map_receipt_authority"] is False
    declaration = packet["supplemental_evidence"]["records"][0]["declaration"]
    citation = answer["claims"][-1]["evidence"][0]
    assert citation["path"] == declaration["path"]
    assert citation["sha256"] == declaration["sha256"]
    assert citation["span"] == declaration["span"]
    snippet = next(item for item in answer["source_snippets"] if item["snippet_id"] == citation["snippet_id"])
    assert snippet["text"] == declaration["snippet"]
    assert answer["original_map_limitation"]
    assert answer["current_answer_authority"] is False
    assert answer["full_question_completeness"] is False
    assert answer["completeness_claim"] is False
    answer_path = fixture["target"] / "answer-packet.json"
    answer_path.unlink()
    retry = qc._write_selection(fixture["target"], str(fixture["repo"]), str(fixture["db"]), str(record_file),
        str(fixture["obligations"]), str(fixture["destination"]))
    assert retry == result
    assert qc._read_artifact(fixture["target"], "answer-packet.json") == answer
    assert qc.status(fixture["target"], str(fixture["repo"]), str(fixture["db"]), str(fixture["obligations"]),
        str(fixture["destination"]))["terminal"] == "in_progress"
    tampered = qc._read_artifact(fixture["target"], "selection.json")
    tampered["supplemental_selection_authority"]["obligations"][0]["joins"][0]["owner_fact_id"] = "forged-owner"
    tampered["supplemental_selection_authority"]["authority_sha256"] = qc._digest({
        key: value for key, value in tampered["supplemental_selection_authority"].items() if key != "authority_sha256"})
    (fixture["target"] / "selection.json").write_bytes(qc._bytes(tampered))
    with pytest.raises(qc.CoordinatorError, match="differs from exact reconstruction"):
        qc.status(fixture["target"], str(fixture["repo"]), str(fixture["db"]), str(fixture["obligations"]),
            str(fixture["destination"]))
    with pytest.raises(qc.CoordinatorError, match="requires --expansion-run-dir"):
        qc.submit_answer(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
            str(fixture["obligations"]), str(tmp_path / "draft.txt"), str(tmp_path / "answer.json"))


def _p2c_selected_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, schema_version: int = qc.EXPANSION_SCHEMA_VERSION):
    fixture = _expansion_import_fixture(tmp_path, monkeypatch, schema_version=schema_version)
    fixture["packet"]["candidates"][0]["provenance"].update({"binding_hash": "binding-origin",
        "association_review_hash": "association-origin", "flow_review_receipt": {"receipt_hash": "receipt-origin"}})
    (fixture["source"] / "selection-packet.json").write_bytes(qc._bytes(fixture["packet"]))
    _import_prepare_fixture(fixture)
    _enable_expanded_revalidation(fixture, monkeypatch)
    packet = qc._read_artifact(fixture["target"], "selection-packet.json")
    selection_record = _expanded_selection_record(packet)
    selection_file = tmp_path / "p2c-selection.json"
    selection_file.write_bytes(qc._bytes(selection_record))
    result = qc._write_selection(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
        str(selection_file), str(fixture["obligations"]), str(fixture["destination"]))
    assert result["claim_count"] == len(qc._read_artifact(fixture["target"], "answer-packet.json")["claims"])
    return fixture


def _p2c_answer_files(fixture: dict[str, object], tmp_path: Path, *, cite_supplemental: bool = True):
    packet = qc._read_artifact(fixture["target"], "answer-packet.json")
    draft = "The answer is bounded to the cited source evidence."
    draft_file = tmp_path / "p2c-draft.txt"
    draft_file.write_text(draft, encoding="utf-8")
    material_claims = []
    for claim in packet["claims"]:
        citations = [{key: evidence[key] for key in qc.ANSWER_RECORD_SCHEMA["citation_fields"]}
                     for evidence in claim["evidence"]]
        if claim.get("provenance", {}).get("evidence_kind") == "supplemental_declaration" and not cite_supplemental:
            continue
        material_claims.append({"assertion": "The source evidence supports this bounded assertion.",
            "claim_numbers": [claim["claim_number"]], "citations": citations})
    answer = {"question_id": packet["obligation_id"], "answer": draft, "material_claims": material_claims,
        "limitations": ["This answer does not establish compiler or runtime binding."], "evidence_measurement": {}}
    answer_file = tmp_path / "p2c-answer.json"
    answer_file.write_bytes(qc._bytes(answer))
    return packet, draft_file, answer_file, answer


def _p2c_review_record(review_packet: dict[str, object], reviewer: str, *, supplemental_disposition: str = "covered",
                       missing_obligation: str | None = None, unsupported: list[str] | None = None):
    answer = review_packet["answer"]
    cited = {n for item in answer["material_claims"] for n in item["claim_numbers"]}
    mandatory = qc._expanded_review_contract(review_packet)["mandatory_supplemental_claims_by_obligation"]
    mandatory_numbers = {n for values in mandatory.values() for n in values}
    claims = []
    for claim in review_packet["claims"]:
        disposition = supplemental_disposition if claim["claim_number"] in mandatory_numbers else "covered"
        if claim["claim_number"] in mandatory_numbers and claim["claim_number"] not in cited:
            disposition = "incomplete"
        claims.append({"claim_number": claim["claim_number"], "disposition": disposition,
            "basis": "This claim is checked against its structured answer citation and source evidence."})
    obligations = []
    for item in review_packet["obligations"]:
        oid = item["obligation_id"]
        disposition = "missing_supported" if oid == missing_obligation else "covered"
        obligations.append({"obligation_id": oid, "disposition": disposition,
            "basis": "This frozen obligation is covered by the answer and cited evidence." if disposition == "covered"
                     else "This frozen obligation is not covered by the answer."})
    answer_gap = (missing_obligation is not None or bool(unsupported)
                  or any(item["disposition"] == "incomplete" for item in claims))
    return {"review_schema_version": 1, "packet_sha256": review_packet["packet_sha256"],
        "decision": "rejected" if answer_gap else "accepted", "reviewer_identity": reviewer,
        "reviewer_model": "GPT-6.1 Sol High", "claim_reviews": claims, "obligation_reviews": obligations,
        "failure_kind": "answer_gap" if answer_gap else "none", "unsupported_assertions": unsupported or []}


def test_expansion_p2c_direct_acceptance_preserves_expansion_lineage_and_exact_question_boundary(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _p2c_selected_fixture(tmp_path, monkeypatch)
    answer_packet_path = fixture["target"] / "answer-packet.json"
    saved_answer_packet = answer_packet_path.read_bytes()
    tampered_answer = json.loads(saved_answer_packet)
    tampered_answer["claims"][-1]["provenance"]["expansion_binding_sha256"] = "forged-binding"
    tampered_answer["semantic_sha256"] = qc._digest({key: value for key, value in tampered_answer.items()
        if key != "semantic_sha256"})
    answer_packet_path.write_bytes(qc._bytes(tampered_answer))
    with pytest.raises(qc.CoordinatorError, match="does not reconstruct"):
        qc.status(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
            str(fixture["obligations"]), str(fixture["destination"]))
    answer_packet_path.write_bytes(saved_answer_packet)
    packet, draft_file, answer_file, _answer = _p2c_answer_files(fixture, tmp_path)
    expansion = str(fixture["destination"])
    with pytest.raises(qc.CoordinatorError, match="requires --expansion-run-dir"):
        qc.submit_answer(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
            str(fixture["obligations"]), str(draft_file), str(answer_file))
    result = qc.submit_answer(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
        str(fixture["obligations"]), str(draft_file), str(answer_file), expansion_run_dir=expansion)
    review_packet = qc._read_artifact(fixture["target"], "review.json")
    assert review_packet["evidence_packet_sha256"] == packet["semantic_sha256"]
    assert review_packet["supplemental_selection_authority"] == packet["selection"]["supplemental_selection_authority"]
    assert review_packet["expanded_review_contract"]["mandatory_supplemental_claims_by_obligation"] == {"behavior.1": [2]}
    review_record = _p2c_review_record(review_packet, "expanded-reviewer")
    review_file = tmp_path / "p2c-review.json"
    review_file.write_bytes(qc._bytes(review_record))
    with pytest.raises(qc.CoordinatorError, match="requires --expansion-run-dir"):
        qc.review(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
            str(fixture["obligations"]), str(review_file))
    assert qc.review(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
        str(fixture["obligations"]), str(review_file), expansion_run_dir=expansion)["result"] == "accepted"
    with pytest.raises(qc.CoordinatorError, match="requires --expansion-run-dir"):
        qc.accept(fixture["target"], str(fixture["repo"]), str(fixture["db"]), str(fixture["obligations"]))
    accepted = qc.accept(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
        str(fixture["obligations"]), expansion_run_dir=expansion)
    assert accepted["expansion_provenance"] == packet["expansion_provenance"]
    assert accepted["supplemental_selection_authority"] == packet["selection"]["supplemental_selection_authority"]
    assert accepted["historical_answer_authority_flags"] == {"current_answer_authority": False,
        "full_question_completeness": False, "completeness_claim": False}
    assert accepted["expansion_acceptance_boundary"]["question_sha256"] == packet["question_sha256"]
    assert accepted["expansion_acceptance_boundary"]["compiler_runtime_proof"] is False
    assert accepted["expansion_acceptance_boundary"]["full_question_completeness"] is False
    assert qc.accept(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
        str(fixture["obligations"]), expansion_run_dir=expansion) == accepted
    assert qc.status(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
        str(fixture["obligations"]), expansion)["terminal"] == "accepted"
    assert result["review_packet"] == "review.json"
    saved = qc._read_artifact(fixture["target"], "accepted-package.json")
    saved["expansion_acceptance_boundary"]["expansion_binding_sha256"] = "forged-binding"
    saved["package_sha256"] = qc._digest({key: value for key, value in saved.items() if key != "package_sha256"})
    (fixture["target"] / "accepted-package.json").write_bytes(qc._bytes(saved))
    with pytest.raises(qc.CoordinatorError, match="does not reconstruct"):
        qc.status(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
            str(fixture["obligations"]), expansion)


def test_expansion_p2c_correction_requires_first_answer_gap_rejection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _p2c_selected_fixture(tmp_path, monkeypatch)
    expansion = str(fixture["destination"])
    _packet, draft_file, answer_file, _answer = _p2c_answer_files(fixture, tmp_path)
    qc.submit_answer(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
        str(fixture["obligations"]), str(draft_file), str(answer_file), expansion_run_dir=expansion)
    review_packet = qc._read_artifact(fixture["target"], "review.json")
    accepted_review = _p2c_review_record(review_packet, "expanded-reviewer-accepted")
    review_file = tmp_path / "p2c-accepted-first-review.json"
    review_file.write_bytes(qc._bytes(accepted_review))
    qc.review(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
        str(fixture["obligations"]), str(review_file), expansion_run_dir=expansion)
    before = {path.name: path.read_bytes() for path in fixture["target"].iterdir()}
    with pytest.raises(qc.CoordinatorError, match="requires a rejected first review with failure_kind answer_gap"):
        qc.submit_answer(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
            str(fixture["obligations"]), str(draft_file), str(answer_file), correction=True,
            expansion_run_dir=expansion)
    assert {path.name: path.read_bytes() for path in fixture["target"].iterdir()} == before

    forged_rejection = {**accepted_review, "decision": "rejected", "failure_kind": "answer_gap"}
    unused = qc._expanded_correction_packet(qc._read_artifact(fixture["target"], "answer-packet.json"),
        qc._read_artifact(fixture["target"], "answer-review-packet.json"), forged_rejection)
    qc._save_immutable(fixture["target"] / "correction-packet.json", unused)
    with pytest.raises(qc.CoordinatorError, match="requires a rejected first review with failure_kind answer_gap"):
        qc.status(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
            str(fixture["obligations"]), expansion)


def test_expansion_p2c_missing_or_inconsistent_first_review_cannot_create_correction(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _p2c_selected_fixture(tmp_path, monkeypatch)
    expansion = str(fixture["destination"])
    _packet, draft_file, answer_file, _answer = _p2c_answer_files(fixture, tmp_path)
    qc.submit_answer(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
        str(fixture["obligations"]), str(draft_file), str(answer_file), expansion_run_dir=expansion)
    before = {path.name: path.read_bytes() for path in fixture["target"].iterdir()}
    with pytest.raises(qc.CoordinatorError, match="requires a saved rejected first review"):
        qc.submit_answer(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
            str(fixture["obligations"]), str(draft_file), str(answer_file), correction=True,
            expansion_run_dir=expansion)
    assert {path.name: path.read_bytes() for path in fixture["target"].iterdir()} == before

    review_packet = qc._read_artifact(fixture["target"], "review.json")
    accepted_review = _p2c_review_record(review_packet, "expanded-reviewer-inconsistent")
    accepted_review["failure_kind"] = "answer_gap"
    (fixture["target"] / "answer-review-packet.json").write_bytes(qc._bytes(review_packet))
    (fixture["target"] / "review-result.json").write_bytes(qc._bytes(accepted_review))
    before_inconsistent = {path.name: path.read_bytes() for path in fixture["target"].iterdir()}
    with pytest.raises(qc.CoordinatorError, match="failure_kind must be none"):
        qc.submit_answer(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
            str(fixture["obligations"]), str(draft_file), str(answer_file), correction=True,
            expansion_run_dir=expansion)
    assert {path.name: path.read_bytes() for path in fixture["target"].iterdir()} == before_inconsistent
    assert not (fixture["target"] / "correction-packet.json").exists()


@pytest.mark.parametrize("schema_version", [2, 1])
def test_expansion_p2c_missing_supplemental_citation_gets_one_correction_and_accepts(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, schema_version: int):
    fixture = _p2c_selected_fixture(tmp_path, monkeypatch, schema_version=schema_version)
    expansion = str(fixture["destination"])
    expansion_before = {item.name: item.read_bytes() for item in fixture["destination"].iterdir()}
    target_before = {item.name: item.read_bytes() for item in fixture["target"].iterdir()}
    assert _expand_fixture(fixture)["packet_sha256"] == qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)["packet_sha256"]
    assert {item.name: item.read_bytes() for item in fixture["destination"].iterdir()} == expansion_before
    assert {item.name: item.read_bytes() for item in fixture["target"].iterdir()} == target_before
    saved_expansion_bytes = {item.name: item.read_bytes() for item in fixture["destination"].iterdir()}
    assert qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)["expansion_schema_version"] == schema_version
    package = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKAGE)
    assert package["current_answer_authority"] is False
    assert package["full_question_completeness"] is False and package["completeness_claim"] is False
    assert qc.expand_gap_status(str(fixture["repo"]), str(fixture["db"]), str(fixture["source"]),
        expansion, str(fixture["obligations"]))["state"] == "local_expansion_ready"
    assert _import_status_fixture(fixture)["state"] == "expanded_packet_prepared"
    with pytest.raises(qc.CoordinatorError, match="different target"):
        _import_prepare_fixture(fixture, target=tmp_path / "second-target")
    _packet, draft_file, answer_file, _answer = _p2c_answer_files(fixture, tmp_path, cite_supplemental=False)
    qc.submit_answer(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
        str(fixture["obligations"]), str(draft_file), str(answer_file), expansion_run_dir=expansion)
    review_packet = qc._read_artifact(fixture["target"], "review.json")
    record = _p2c_review_record(review_packet, "expanded-reviewer-1")
    review_file = tmp_path / "p2c-incomplete-review.json"
    review_file.write_bytes(qc._bytes(record))
    result = qc.review(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
        str(fixture["obligations"]), str(review_file), expansion_run_dir=expansion)
    assert result["failure_kind"] == "answer_gap"
    correction = qc._read_artifact(fixture["target"], "correction-packet.json")
    original = qc._read_artifact(fixture["target"], "answer-packet.json")
    assert correction["semantic_sha256"] == original["semantic_sha256"]
    assert correction["supplemental_selection_authority"] == original["selection"]["supplemental_selection_authority"]
    assert correction["expansion_provenance"] == original["expansion_provenance"]
    correction_path = fixture["target"] / "correction-packet.json"
    saved_correction = correction_path.read_bytes()
    tampered_correction = json.loads(saved_correction)
    tampered_correction["expansion_provenance"]["review_sha256"] = "forged-review"
    tampered_correction["packet_sha256"] = qc._digest({key: value for key, value in tampered_correction.items() if key != "packet_sha256"})
    correction_path.write_bytes(qc._bytes(tampered_correction))
    with pytest.raises(qc.CoordinatorError, match="correction packet does not preserve"):
        qc.status(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
            str(fixture["obligations"]), expansion)
    correction_path.write_bytes(saved_correction)
    packet, draft_file, answer_file, _answer = _p2c_answer_files(fixture, tmp_path, cite_supplemental=True)
    with pytest.raises(qc.CoordinatorError, match="requires --expansion-run-dir"):
        qc.submit_answer(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
            str(fixture["obligations"]), str(draft_file), str(answer_file), correction=True)
    qc.submit_answer(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
        str(fixture["obligations"]), str(draft_file), str(answer_file), correction=True, expansion_run_dir=expansion)
    corrected_packet = qc._read_artifact(fixture["target"], "corrected-answer-packet.json")
    assert corrected_packet["evidence_packet_sha256"] == packet["semantic_sha256"]
    assert corrected_packet["supplemental_selection_authority"] == packet["selection"]["supplemental_selection_authority"]
    corrected_review = _p2c_review_record(corrected_packet, "expanded-reviewer-2")
    corrected_file = tmp_path / "p2c-corrected-review.json"
    corrected_file.write_bytes(qc._bytes(corrected_review))
    with pytest.raises(qc.CoordinatorError, match="requires --expansion-run-dir"):
        qc.review(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
            str(fixture["obligations"]), str(corrected_file), corrected=True)
    assert qc.review(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
        str(fixture["obligations"]), str(corrected_file), corrected=True,
        expansion_run_dir=expansion)["result"] == "accepted"
    accepted = qc.accept(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
        str(fixture["obligations"]), corrected=True, expansion_run_dir=expansion)
    with pytest.raises(qc.CoordinatorError, match="requires --expansion-run-dir"):
        qc.accept(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
            str(fixture["obligations"]), corrected=True)
    assert accepted["result"] == "accepted"
    assert accepted["correction_lineage"]["semantic_sha256"] == packet["semantic_sha256"]
    assert qc.status(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
        str(fixture["obligations"]), expansion)["terminal"] == "accepted"
    assert qc.expand_gap_status(str(fixture["repo"]), str(fixture["db"]), str(fixture["source"]),
        expansion, str(fixture["obligations"]))["state"] == "local_expansion_ready"
    target_after_acceptance = {item.name: item.read_bytes() for item in fixture["target"].iterdir()}
    assert _expand_fixture(fixture)["packet_sha256"] == qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)["packet_sha256"]
    assert {item.name: item.read_bytes() for item in fixture["destination"].iterdir()} == saved_expansion_bytes
    assert {item.name: item.read_bytes() for item in fixture["target"].iterdir()} == target_after_acceptance
    assert {item.name: item.read_bytes() for item in fixture["destination"].iterdir()} == saved_expansion_bytes


def test_expansion_p2c_review_requires_supplemental_claim_covered_and_exact_lineage(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _p2c_selected_fixture(tmp_path, monkeypatch)
    expansion = str(fixture["destination"])
    _packet, draft_file, answer_file, _answer = _p2c_answer_files(fixture, tmp_path)
    qc.submit_answer(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
        str(fixture["obligations"]), str(draft_file), str(answer_file), expansion_run_dir=expansion)
    review_packet = qc._read_artifact(fixture["target"], "review.json")
    record = _p2c_review_record(review_packet, "expanded-reviewer", supplemental_disposition="incomplete")
    record["decision"] = "rejected"; record["failure_kind"] = "answer_gap"
    review_file = tmp_path / "p2c-supplemental-incomplete-review.json"
    review_file.write_bytes(qc._bytes(record))
    result = qc.review(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
        str(fixture["obligations"]), str(review_file), expansion_run_dir=expansion)
    assert result["failure_kind"] == "answer_gap"
    assert (fixture["target"] / "correction-packet.json").exists()
    tampered = qc._read_artifact(fixture["target"], "answer-review-packet.json")
    tampered["expansion_provenance"]["binding_sha256"] = "forged-binding"
    tampered["packet_sha256"] = qc._digest({k: v for k, v in tampered.items() if k != "packet_sha256"})
    (fixture["target"] / "answer-review-packet.json").write_bytes(qc._bytes(tampered))
    with pytest.raises(qc.CoordinatorError, match="differs from its round-zero packet"):
        qc.status(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
            str(fixture["obligations"]), expansion)


def test_expansion_p2c_wrong_supplemental_citation_is_refused_before_review(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _p2c_selected_fixture(tmp_path, monkeypatch)
    packet, draft_file, answer_file, answer = _p2c_answer_files(fixture, tmp_path)
    supplemental_number = next(claim["claim_number"] for claim in packet["claims"]
        if claim.get("provenance", {}).get("evidence_kind") == "supplemental_declaration")
    item = next(claim for claim in answer["material_claims"] if claim["claim_numbers"] == [supplemental_number])
    item["citations"][0]["sha256"] = "forged-source-hash"
    answer_file.write_bytes(qc._bytes(answer))
    with pytest.raises(qc.CoordinatorError, match="does not resolve into the exact union evidence"):
        qc.submit_answer(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
            str(fixture["obligations"]), str(draft_file), str(answer_file),
            expansion_run_dir=str(fixture["destination"]))
    assert not (fixture["target"] / "review.json").exists()


@pytest.mark.parametrize("defect", ["missing_obligation", "unsupported_assertion"])
def test_expansion_p2c_review_gaps_get_one_correction_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, defect: str):
    fixture = _p2c_selected_fixture(tmp_path, monkeypatch)
    expansion = str(fixture["destination"])
    _packet, draft_file, answer_file, _answer = _p2c_answer_files(fixture, tmp_path)
    qc.submit_answer(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
        str(fixture["obligations"]), str(draft_file), str(answer_file), expansion_run_dir=expansion)
    review_packet = qc._read_artifact(fixture["target"], "review.json")
    record = _p2c_review_record(review_packet, "expanded-reviewer-gap",
        missing_obligation="behavior.1" if defect == "missing_obligation" else None,
        unsupported=["An unsupported assertion."] if defect == "unsupported_assertion" else None)
    review_file = tmp_path / f"p2c-{defect}.json"
    review_file.write_bytes(qc._bytes(record))
    result = qc.review(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
        str(fixture["obligations"]), str(review_file), expansion_run_dir=expansion)
    assert result["failure_kind"] == "answer_gap"
    correction = qc._read_artifact(fixture["target"], "correction-packet.json")
    assert correction["semantic_sha256"] == review_packet["evidence_packet_sha256"]
    assert correction["historical_answer_authority_flags"] == {"current_answer_authority": False,
        "full_question_completeness": False, "completeness_claim": False}


def test_expansion_p2c_corrected_rejection_is_terminal_and_unknown_answer_json_refuses(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _p2c_selected_fixture(tmp_path, monkeypatch)
    expansion = str(fixture["destination"])
    _packet, draft_file, answer_file, _answer = _p2c_answer_files(fixture, tmp_path)
    qc.submit_answer(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
        str(fixture["obligations"]), str(draft_file), str(answer_file), expansion_run_dir=expansion)
    review_packet = qc._read_artifact(fixture["target"], "review.json")
    first = _p2c_review_record(review_packet, "expanded-reviewer-first", missing_obligation="behavior.1")
    first_file = tmp_path / "p2c-first-reject.json"
    first_file.write_bytes(qc._bytes(first))
    qc.review(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
        str(fixture["obligations"]), str(first_file), expansion_run_dir=expansion)
    _packet, draft_file, answer_file, _answer = _p2c_answer_files(fixture, tmp_path, cite_supplemental=False)
    qc.submit_answer(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
        str(fixture["obligations"]), str(draft_file), str(answer_file), correction=True, expansion_run_dir=expansion)
    corrected_packet = qc._read_artifact(fixture["target"], "corrected-answer-packet.json")
    corrected = _p2c_review_record(corrected_packet, "expanded-reviewer-second")
    corrected_file = tmp_path / "p2c-second-reject.json"
    corrected_file.write_bytes(qc._bytes(corrected))
    outcome = qc.review(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
        str(fixture["obligations"]), str(corrected_file), corrected=True, expansion_run_dir=expansion)
    assert outcome["result"] == "terminal_rejection"
    assert qc.status(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
        str(fixture["obligations"]), expansion)["terminal"] == "rejected"
    (fixture["target"] / "answer.json").write_bytes(b"{}\n")
    with pytest.raises(qc.CoordinatorError, match="unrelated artifacts"):
        qc.status(fixture["target"], str(fixture["repo"]), str(fixture["db"]),
            str(fixture["obligations"]), expansion)


def test_expansion_import_prepare_refuses_external_review_and_target_overlap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    external = _expansion_import_fixture(tmp_path / "external", monkeypatch, no_candidates=True)
    with pytest.raises(qc.CoordinatorError, match="cannot be imported"):
        _import_prepare_fixture(external)
    assert not external["target"].exists()
    assert not (external["destination"] / qc.EXPANSION_IMPORT_BINDING).exists()

    local = _expansion_import_fixture(tmp_path / "overlap", monkeypatch)
    with pytest.raises(qc.CoordinatorError, match="overlaps"):
        _import_prepare_fixture(local, target=Path(local["source"]) / "nested-target")
    assert not (local["destination"] / qc.EXPANSION_IMPORT_BINDING).exists()

    expansion_overlap = _expansion_import_fixture(tmp_path / "expansion-overlap", monkeypatch)
    with pytest.raises(qc.CoordinatorError, match="overlaps"):
        _import_prepare_fixture(expansion_overlap, target=Path(expansion_overlap["destination"]))
    assert not (expansion_overlap["destination"] / qc.EXPANSION_IMPORT_BINDING).exists()


def test_expansion_import_prepare_recovers_exact_partial_state_and_refuses_target_reuse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_import_fixture(tmp_path, monkeypatch)
    first = _import_prepare_fixture(fixture)
    observations = fixture["target"] / "candidate-observations.json"
    observations.unlink()
    with pytest.raises(qc.CoordinatorError, match="incomplete"):
        _import_status_fixture(fixture)
    recovered = _import_prepare_fixture(fixture)
    assert recovered == first
    second_target = tmp_path / "second-target"
    with pytest.raises(qc.CoordinatorError, match="different target"):
        _import_prepare_fixture(fixture, target=second_target)
    assert not second_target.exists()


def test_expansion_import_prepare_rejects_nonempty_target_and_binding_rehash_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_import_fixture(tmp_path, monkeypatch)
    fixture["target"].mkdir()
    (fixture["target"] / "unrelated.txt").write_text("occupied", encoding="utf-8")
    with pytest.raises(qc.CoordinatorError, match="unrelated artifacts"):
        _import_prepare_fixture(fixture)
    assert not (fixture["destination"] / qc.EXPANSION_IMPORT_BINDING).exists()

    (fixture["target"] / "unrelated.txt").unlink()
    fixture["target"].rmdir()
    _import_prepare_fixture(fixture)
    binding_path = fixture["destination"] / qc.EXPANSION_IMPORT_BINDING
    binding = qc._read_artifact(fixture["destination"], qc.EXPANSION_IMPORT_BINDING)
    binding["target_run_path"] = str((tmp_path / "another-target").resolve())
    binding["binding_sha256"] = qc._digest({key: value for key, value in binding.items() if key != "binding_sha256"})
    binding_path.write_bytes(qc._bytes(binding))
    with pytest.raises(qc.CoordinatorError, match="does not reconstruct"):
        _import_status_fixture(fixture)


def test_expansion_import_prepare_requires_exact_question_and_obligations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_import_fixture(tmp_path, monkeypatch)
    fixture["question_file"].write_text("changed question", encoding="utf-8")
    with pytest.raises(qc.CoordinatorError, match="question file bytes"):
        _import_prepare_fixture(fixture)
    fixture["question_file"].write_text(fixture["packet"]["question"], encoding="utf-8")
    fixture["obligations"].write_bytes(b"changed obligations")
    with pytest.raises(qc.CoordinatorError, match="obligations path"):
        _import_prepare_fixture(fixture)
    assert not fixture["target"].exists()
    assert not (fixture["destination"] / qc.EXPANSION_IMPORT_BINDING).exists()


def test_expansion_import_prepare_refuses_mixed_incomplete_and_unsafe_targets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    mixed = _expansion_import_fixture(tmp_path / "mixed", monkeypatch,
        classifications=["local_evidence", "external_or_unresolved"],
        extra_obligation_meanings=("A second local declaration remains unresolved.",))
    with pytest.raises(qc.CoordinatorError, match="cannot be imported"):
        _import_prepare_fixture(mixed)
    assert not mixed["target"].exists()
    assert not (mixed["destination"] / qc.EXPANSION_IMPORT_BINDING).exists()

    incomplete = _expansion_import_fixture(tmp_path / "incomplete", monkeypatch, conditional=True)
    with pytest.raises(qc.CoordinatorError, match="cannot be imported"):
        _import_prepare_fixture(incomplete)
    assert not incomplete["target"].exists()
    assert not (incomplete["destination"] / qc.EXPANSION_IMPORT_BINDING).exists()

    unsafe = _expansion_import_fixture(tmp_path / "unsafe", monkeypatch)
    unsafe["target"].parent.mkdir(parents=True, exist_ok=True)
    unsafe["target"].symlink_to(unsafe["target"].parent / "elsewhere", target_is_directory=True)
    with pytest.raises(qc.CoordinatorError, match="real directory"):
        _import_prepare_fixture(unsafe)
    assert not (unsafe["destination"] / qc.EXPANSION_IMPORT_BINDING).exists()


def test_expansion_import_prepare_rejects_symlink_artifacts_and_rehashed_overgrant(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    symlink = _expansion_import_fixture(tmp_path / "symlink", monkeypatch)
    symlink["target"].mkdir()
    (symlink["target"] / "selection-packet.json").symlink_to(symlink["source"] / "selection-packet.json")
    with pytest.raises(qc.CoordinatorError, match="regular file"):
        _import_prepare_fixture(symlink)
    assert not (symlink["destination"] / qc.EXPANSION_IMPORT_BINDING).exists()

    tampered = _expansion_import_fixture(tmp_path / "tampered", monkeypatch)
    _import_prepare_fixture(tampered)
    binding_path = tampered["destination"] / qc.EXPANSION_IMPORT_BINDING
    binding = qc._read_artifact(tampered["destination"], qc.EXPANSION_IMPORT_BINDING)
    binding["support_joins"][0]["route_fact_id"] = "overgrant-route"
    binding["binding_sha256"] = qc._digest({key: value for key, value in binding.items() if key != "binding_sha256"})
    binding_path.write_bytes(qc._bytes(binding))
    with pytest.raises(qc.CoordinatorError, match="does not reconstruct"):
        _import_status_fixture(tampered)


def test_expansion_import_prepare_rejects_ineligible_review_and_rehashed_authority_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    overgrant = _expansion_import_fixture(tmp_path / "overgrant", monkeypatch)
    packet = qc._read_artifact(overgrant["destination"], qc.EXPANSION_PACKET)
    review = qc._read_artifact(overgrant["destination"], qc.EXPANSION_REVIEW)
    invalid_candidate = packet["declaration_candidates"][1]
    review["obligation_reviews"][0]["selected_candidate_ids"] = [invalid_candidate["candidate_id"]]
    for item in review["candidate_reviews"]:
        item["disposition"] = "selected" if item["candidate_id"] == invalid_candidate["candidate_id"] else "not_selected"
    (overgrant["destination"] / qc.EXPANSION_REVIEW).write_bytes(qc._bytes(review))
    (overgrant["destination"] / qc.EXPANSION_PACKAGE).write_bytes(qc._bytes(qc._expansion_package(packet, review)))
    with pytest.raises(qc.CoordinatorError, match="eligible for that exact obligation"):
        _import_prepare_fixture(overgrant)
    assert not overgrant["target"].exists()
    assert not (overgrant["destination"] / qc.EXPANSION_IMPORT_BINDING).exists()

    drift = _expansion_import_fixture(tmp_path / "authority-drift", monkeypatch)
    package_path = drift["destination"] / qc.EXPANSION_PACKAGE
    package = qc._read_artifact(drift["destination"], qc.EXPANSION_PACKAGE)
    package["current_answer_authority"] = True
    package["package_sha256"] = qc._digest({key: value for key, value in package.items() if key != "package_sha256"})
    package_path.write_bytes(qc._bytes(package))
    with pytest.raises(qc.CoordinatorError, match="differs from reconstructed"):
        _import_prepare_fixture(drift)
    assert not drift["target"].exists()
    assert not (drift["destination"] / qc.EXPANSION_IMPORT_BINDING).exists()


def test_expansion_p1_shared_candidate_must_be_eligible_for_each_obligation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_fixture(tmp_path, monkeypatch, extra_obligation_meanings=("The source declaration fixes ChangeEventDays at 10.",))
    _expand_fixture(fixture)
    packet = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)
    candidate_id = packet["absent_obligations"][0]["eligible_candidate_ids"][0]
    review = _p1_review(packet, classifications=["local_evidence", "local_evidence"],
                        selected_by_obligation=[[candidate_id], [candidate_id]])
    result = _review_fixture(fixture, review, _p1_review_file(tmp_path, review))
    assert result["state"] == "local_expansion_ready"
    assert [item["candidate_id"] for item in review["candidate_reviews"] if item["disposition"] == "selected"] == [candidate_id]
    invalid = _p1_review(packet, classifications=["local_evidence", "external_or_unresolved"],
                         selected_by_obligation=[[candidate_id], [candidate_id]])
    with pytest.raises(qc.CoordinatorError, match="must have no selected candidate IDs"):
        _review_fixture(fixture, invalid, _p1_review_file(tmp_path, invalid))


@pytest.mark.parametrize("tamper", ["schema", "order", "missing", "extra", "ineligible", "disposition", "candidate_order"])
def test_expansion_p1_review_contract_refuses_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tamper: str):
    fixture = _expansion_fixture(tmp_path, monkeypatch, extra_obligation_meanings=("Another independent obligation.",))
    _expand_fixture(fixture)
    packet = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)
    review = _p1_review(packet, classifications=["local_evidence", "external_or_unresolved"])
    if tamper == "schema": review["unexpected"] = True
    elif tamper == "order": review["obligation_reviews"].reverse()
    elif tamper == "missing": review["obligation_reviews"].pop()
    elif tamper == "extra": review["candidate_reviews"].append(dict(review["candidate_reviews"][0]))
    elif tamper == "ineligible": review["obligation_reviews"][0]["selected_candidate_ids"] = [packet["declaration_candidates"][1]["candidate_id"]]
    elif tamper == "disposition": review["candidate_reviews"][0]["disposition"] = "not_selected"
    else: review["candidate_reviews"].reverse()
    review_file = _p1_review_file(tmp_path, review)
    with pytest.raises(qc.CoordinatorError):
        _review_fixture(fixture, review, review_file)
    assert not (fixture["destination"] / qc.EXPANSION_REVIEW).exists()
    assert not (fixture["destination"] / qc.EXPANSION_PACKAGE).exists()


def test_expansion_p1_incomplete_search_cannot_be_local_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_fixture(tmp_path, monkeypatch)
    untracked = [{"path": "src/Untracked.cs", "index_status": "?", "worktree_status": "?"}]
    fixture["live"]["status"] = untracked
    fixture["packet"]["identity"]["repository_status"] = untracked
    _expand_fixture(fixture)
    packet = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)
    assert packet["search"]["complete"] is False
    forged_local = {**_p1_review(packet), "obligation_reviews": [{"obligation_id": "behavior.1", "classification": "local_evidence",
        "selected_candidate_ids": [packet["declaration_candidates"][0]["candidate_id"]], "basis": "Sol says local despite incomplete search."}]}
    with pytest.raises(qc.CoordinatorError, match="eligible for that exact obligation"):
        _review_fixture(fixture, forged_local, _p1_review_file(tmp_path, forged_local))
    unresolved = _p1_review(packet)
    result = _review_fixture(fixture, unresolved, _p1_review_file(tmp_path, unresolved))
    assert result["state"] == "external_or_unresolved"
    assert qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKAGE)["package_type"] == "external_or_unresolved"


def test_expansion_p1_partial_save_retry_and_read_only_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_fixture(tmp_path, monkeypatch)
    _expand_fixture(fixture)
    packet = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)
    review = _p1_review(packet)
    review_file = _p1_review_file(tmp_path, review)
    save = qc._save_immutable
    def fail_package(path: Path, value: object):
        if path.name == qc.EXPANSION_PACKAGE:
            raise OSError("simulated package save interruption")
        return save(path, value)
    monkeypatch.setattr(qc, "_save_immutable", fail_package)
    with pytest.raises(OSError, match="interruption"):
        _review_fixture(fixture, review, review_file)
    assert (fixture["destination"] / qc.EXPANSION_REVIEW).is_file()
    assert not (fixture["destination"] / qc.EXPANSION_PACKAGE).exists()
    before = {item.name: item.read_bytes() for item in fixture["destination"].iterdir()}
    assert _status_fixture(fixture)["state"] == "review_only"
    assert {item.name: item.read_bytes() for item in fixture["destination"].iterdir()} == before
    monkeypatch.setattr(qc, "_save_immutable", save)
    assert _review_fixture(fixture, review, review_file)["state"] == "local_expansion_ready"


@pytest.mark.parametrize("artifact", [qc.EXPANSION_REVIEW, qc.EXPANSION_PACKAGE])
def test_expansion_p1_status_rejects_symlink_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, artifact: str):
    fixture = _expansion_fixture(tmp_path, monkeypatch)
    _expand_fixture(fixture)
    packet = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)
    if artifact == qc.EXPANSION_REVIEW:
        review = _p1_review(packet)
        qc._save_immutable(fixture["destination"] / artifact, review)
    else:
        review = _p1_review(packet)
        package = qc._expansion_package(packet, review)
        qc._save_immutable(fixture["destination"] / qc.EXPANSION_REVIEW, review)
        qc._save_immutable(fixture["destination"] / artifact, package)
    path = fixture["destination"] / artifact
    target = tmp_path / f"{artifact}.target"
    target.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(target)
    with pytest.raises(qc.CoordinatorError, match="no-follow regular file"):
        _status_fixture(fixture)


def test_expansion_p1_status_rejects_packet_copy_and_rehashed_bundle_tampering(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_fixture(tmp_path, monkeypatch)
    _expand_fixture(fixture)
    packet = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)
    review = _p1_review(packet)
    _review_fixture(fixture, review, _p1_review_file(tmp_path, review))
    package_path = fixture["destination"] / qc.EXPANSION_PACKAGE
    tampered = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKAGE)
    tampered["lineage"]["source_gap_sha256"] = "0" * 64
    tampered["package_sha256"] = qc._digest({key: value for key, value in tampered.items() if key != "package_sha256"})
    package_path.write_bytes(qc._bytes(tampered))
    with pytest.raises(qc.CoordinatorError, match="does not reconstruct"):
        _status_fixture(fixture)
    copied = tmp_path / "copied-expansion"
    copied.mkdir()
    (copied / qc.EXPANSION_PACKET).write_bytes((fixture["destination"] / qc.EXPANSION_PACKET).read_bytes())
    with pytest.raises(qc.CoordinatorError, match="source/destination binding"):
        qc.expand_gap_status(str(fixture["repo"]), str(fixture["db"]), str(fixture["source"]),
            str(copied), str(fixture["obligations"]))


def test_expansion_p1_status_rejects_review_package_disagreement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_fixture(tmp_path, monkeypatch)
    _expand_fixture(fixture)
    packet = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)
    review = _p1_review(packet)
    _review_fixture(fixture, review, _p1_review_file(tmp_path, review))
    saved_review = qc._read_artifact(fixture["destination"], qc.EXPANSION_REVIEW)
    saved_review["obligation_reviews"][0]["classification"] = "external_or_unresolved"
    saved_review["obligation_reviews"][0]["selected_candidate_ids"] = []
    saved_review["candidate_reviews"][0]["disposition"] = "not_selected"
    (fixture["destination"] / qc.EXPANSION_REVIEW).write_bytes(qc._bytes(saved_review))
    with pytest.raises(qc.CoordinatorError, match="package does not reconstruct"):
        _status_fixture(fixture)


def test_expansion_p1_review_input_rejects_symlink(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture = _expansion_fixture(tmp_path, monkeypatch)
    _expand_fixture(fixture)
    packet = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)
    review = _p1_review(packet)
    target = _p1_review_file(tmp_path, review)
    alias = tmp_path / "review-link.json"
    alias.symlink_to(target)
    with pytest.raises(qc.CoordinatorError, match="no-follow regular file"):
        _review_fixture(fixture, review, alias)


@pytest.mark.parametrize("mode", ["local", "external"])
@pytest.mark.parametrize("bad_version", [True, 1.0, "2", None, 1, 3])
@pytest.mark.parametrize("boundary", ["review_submit", "review_status", "package_status"])
def test_expansion_p1_schema_versions_require_exact_integer_wire_values(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, bad_version: object, boundary: str):
    fixture = _expansion_fixture(tmp_path, monkeypatch, declaration="" if mode == "external" else "public const int ChangeEventDays = 10;",
                                 no_candidates=mode == "external")
    _expand_fixture(fixture)
    packet = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKET)
    review = _p1_review(packet)
    if boundary == "review_submit":
        review["review_schema_version"] = bad_version
        with pytest.raises(qc.CoordinatorError, match="expansion review schema"):
            _review_fixture(fixture, review, _p1_review_file(tmp_path, review))
        assert not (fixture["destination"] / qc.EXPANSION_REVIEW).exists()
        assert not (fixture["destination"] / qc.EXPANSION_PACKAGE).exists()
        return
    _review_fixture(fixture, review, _p1_review_file(tmp_path, review))
    expected_state = "local_expansion_ready" if mode == "local" else "external_or_unresolved"
    assert _status_fixture(fixture)["state"] == expected_state
    if boundary == "review_status":
        artifact_path = fixture["destination"] / qc.EXPANSION_REVIEW
        artifact = qc._read_artifact(fixture["destination"], qc.EXPANSION_REVIEW)
        artifact["review_schema_version"] = bad_version
    else:
        artifact_path = fixture["destination"] / qc.EXPANSION_PACKAGE
        artifact = qc._read_artifact(fixture["destination"], qc.EXPANSION_PACKAGE)
        artifact["package_schema_version"] = 2 if bad_version == 1 else bad_version
    artifact_path.write_bytes(qc._bytes(artifact))
    with pytest.raises(qc.CoordinatorError, match="schema version|expansion review schema"):
        _status_fixture(fixture)
