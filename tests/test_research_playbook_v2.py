from __future__ import annotations

import hashlib
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest


MODULE_PATH = Path(__file__).parents[1] / "skills/research-playbook/scripts/research_package.py"
SPEC = importlib.util.spec_from_file_location("research_package_v2", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
research_package = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(research_package)

EVALUATOR_PATH = Path(__file__).parents[1] / "scripts/evaluate_research_playbook_v2.py"
EVALUATOR_SPEC = importlib.util.spec_from_file_location("evaluate_research_playbook_v2", EVALUATOR_PATH)
assert EVALUATOR_SPEC is not None and EVALUATOR_SPEC.loader is not None
evaluator = importlib.util.module_from_spec(EVALUATOR_SPEC)
EVALUATOR_SPEC.loader.exec_module(evaluator)

INSTALLER_PATH = Path(__file__).parents[1] / "working-agreement/install_skills.py"
INSTALLER_SPEC = importlib.util.spec_from_file_location("install_skills", INSTALLER_PATH)
assert INSTALLER_SPEC is not None and INSTALLER_SPEC.loader is not None
installer = importlib.util.module_from_spec(INSTALLER_SPEC)
INSTALLER_SPEC.loader.exec_module(installer)

START = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)


def evidence_item(
    evidence_id: str,
    supported_claim: str = "Grounded evidence.",
    *,
    source_sha256: str = "a" * 64,
) -> dict:
    return {
        "id": evidence_id,
        "source_kind": "SUPPLIED_INPUT",
        "source_locator": "fixture:evidence.json",
        "source_sha256": source_sha256,
        "accessed_at": None,
        "supported_claim": supported_claim,
        "limitations": "Supports only the stated claim.",
    }


def planner_readiness(package: dict, evidence_ids: list[str]) -> list[dict]:
    obligation_ids = {
        obligation["id"]
        for requirement in package["requirements"]
        for obligation in requirement.get("planner_obligations", [])
    }
    return [
        {
            "obligation_id": obligation_id,
            "status": "READY",
            "implementation_anchors": [f"Implement at the grounded {obligation_id} boundary."],
            "verification_anchors": [f"Verify the {obligation_id} acceptance observable."],
            "required_inputs": [],
            "owner": "implementation owner",
            "closure_condition": f"The {obligation_id} acceptance observable passes.",
            "evidence_ids": evidence_ids,
        }
        for obligation_id in sorted(obligation_ids)
    ]


def charter() -> dict:
    return {"objective": "Produce planner-ready research.", "boundaries": ["repo-a"]}


def requirements() -> list[dict]:
    return [
        {
            "id": "R1",
            "text": "Ground current behavior in source evidence.",
            "source": "task-intake:R1",
            "operational_maturity": "CURRENT_RUNTIME",
            "evidence_availability": "AVAILABLE",
            "acceptance_intent": "Every current-behavior claim cites source evidence.",
            "scope_id": "repo-a-current-runtime",
            "research_value_type": "string",
            "planner_obligations": [],
        },
        {
            "id": "R2",
            "text": "Separate proposed behavior from current behavior.",
            "source": "task-intake:R2",
            "operational_maturity": "FUTURE_SYSTEM",
            "evidence_availability": "NOT_YET_APPLICABLE",
            "acceptance_intent": "Proposals are labeled as future-system behavior.",
            "scope_id": "repo-a-future-system",
            "research_value_type": "string",
            "planner_obligations": [],
        },
    ]


def state() -> dict:
    return research_package.create_state(
        charter(),
        requirements(),
        "MIXED",
        {"source": "AVAILABLE", "runtime": "MISSING_REQUIRED"},
        started_at=START,
    )


def test_charter_budget_is_authoritative_and_persisted() -> None:
    bounded = charter()
    bounded["budget"] = {
        "maximum_candidate_rounds": 2,
        "maximum_agent_spawn_attempts": 10,
        "maximum_elapsed_minutes": 45,
        "maximum_retries_per_role": 1,
    }
    package = research_package.create_state(
        bounded,
        requirements(),
        "MIXED",
        {"source": "AVAILABLE"},
        started_at=START,
    )
    assert package["budgets"] == {
        "max_rounds": 2,
        "max_attempts": 10,
        "max_minutes": 45,
        "max_role_retries": 1,
        "started_at": "2026-07-14T12:00:00Z",
        "deadline_at": "2026-07-14T12:45:00Z",
    }
    research_package.validate_state(package)


def test_frozen_budget_tampering_is_rejected() -> None:
    package = state()
    package["budgets"]["max_attempts"] += 1
    with pytest.raises(research_package.ResearchPackageError, match="budget max_attempts"):
        research_package.validate_state(package)


def test_frozen_budget_deadline_and_shape_tampering_are_rejected() -> None:
    package = state()
    package["budgets"]["deadline_at"] = "2099-01-01T00:00:00Z"
    with pytest.raises(research_package.ResearchPackageError, match="deadline_at"):
        research_package.validate_state(package)


def test_failed_first_core_attempt_can_be_recorded_before_a_candidate_exists() -> None:
    package = state()
    result = research_package.record_attempt(
        package,
        runtime_agent_id="first-core-failure",
        role="CORE_RESEARCHER",
        round_number=1,
        candidate_hash=None,
        input_envelope_hash="a" * 64,
        status="FAILED",
        output_hash=None,
        slot_closed=True,
        close_evidence={"closed": True},
        now=START,
    )
    assert result["status"] == "FAILED"
    assert package["attempts"][0]["candidate_hash"] is None
    research_package.validate_state(package)

    package = state()
    package["budgets"]["unexpected"] = 1
    with pytest.raises(research_package.ResearchPackageError, match="budget fields"):
        research_package.validate_state(package)


def test_workflow_age_does_not_cap_an_individual_task_attempt() -> None:
    package = state()
    result = research_package.record_attempt(
        package,
        runtime_agent_id="late-core-attempt",
        role="CORE_RESEARCHER",
        round_number=1,
        candidate_hash=None,
        input_envelope_hash="a" * 64,
        status="FAILED",
        output_hash=None,
        slot_closed=True,
        close_evidence={"closed": True},
        now=START + timedelta(hours=2),
    )
    assert result["reason"] == "ATTEMPT_RECORDED"
    assert package["verdict"] == "IN_PROGRESS"
    assert package["attempts"][0]["runtime_agent_id"] == "late-core-attempt"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("maximum_candidate_rounds", 0),
        ("maximum_agent_spawn_attempts", True),
        ("maximum_elapsed_minutes", -1),
        ("maximum_retries_per_role", -1),
    ],
)
def test_invalid_charter_budget_fails_closed(field: str, value: object) -> None:
    bounded = charter()
    bounded["budget"] = {
        "maximum_candidate_rounds": 2,
        "maximum_agent_spawn_attempts": 10,
        "maximum_elapsed_minutes": 45,
        "maximum_retries_per_role": 1,
    }
    bounded["budget"][field] = value
    with pytest.raises(research_package.ResearchPackageError, match=f"charter budget {field}"):
        research_package.create_state(
            bounded,
            requirements(),
            "MIXED",
            {"source": "AVAILABLE"},
            started_at=START,
        )


@pytest.mark.parametrize(
    "budget",
    [
        {"maximum_candidate_rounds": 2},
        {
            "maximum_candidate_rounds": 2,
            "maximum_agent_spawn_attempts": 10,
            "maximum_elapsed_minutes": 45,
            "maximum_retries_per_role": 1,
            "unsupported": 1,
        },
    ],
)
def test_present_charter_budget_requires_exact_governed_shape(budget: dict[str, int]) -> None:
    bounded = charter()
    bounded["budget"] = budget
    with pytest.raises(research_package.ResearchPackageError, match="exactly the four governed fields"):
        research_package.create_state(
            bounded,
            requirements(),
            "MIXED",
            {"source": "AVAILABLE"},
            started_at=START,
        )


def candidate_pair(
    package: dict,
    revision: int = 1,
    *,
    requirement_statuses: list[dict] | None = None,
    include_requirement_statuses: bool = True,
    material_gaps: list[str] | None = None,
) -> tuple[str, str]:
    candidate = {
        "revision": revision,
        "findings": ["grounded"],
        "material_gaps": [] if material_gaps is None else material_gaps,
    }
    if include_requirement_statuses:
        candidate["requirement_statuses"] = (
            requirement_statuses
            if requirement_statuses is not None
            else [
                {
                    "requirement_id": requirement["id"],
                    "research_value": "grounded",
                    "evidence_ids": [],
                }
                for requirement in package["requirements"]
            ]
        )
    result = research_package.record_candidate(
        package,
        candidate,
        {"evidence": [f"src/module.py:{revision}"]},
        now=START + timedelta(minutes=revision),
    )
    return result["candidate_hash"], result["envelope_hash"]


def output_hash(role: str, round_number: int = 1) -> str:
    return research_package.canonical_hash({"role": role, "round": round_number})


def raw_finding(
    finding_id: str,
    *,
    lens: str = "INTERNAL_READINESS",
    finding_type: str = "PLANNER_DECISION",
    materiality: str = "PLANNING",
    proposed_disposition: str = "HANDOFF_TO_PLANNER",
    status: str = "OPEN",
) -> dict:
    finding = {
        "id": finding_id,
        "fingerprint": f"{lens}:{finding_type}:{finding_id}",
        "lens": lens,
        "originating_stage": "RESEARCH",
        "requirement_ids": ["R1"],
        "type": finding_type,
        "materiality": materiality,
        "practical_consequence": f"Planning must resolve {finding_id}.",
        "evidence": f"Source evidence for {finding_id}.",
        "proposed_disposition": proposed_disposition,
        "status": status,
    }
    if status == "CLOSED":
        finding["closure_evidence"] = f"Closure evidence for {finding_id}."
    return finding


def record_attempt(
    package: dict,
    role: str,
    round_number: int,
    hashes: tuple[str, str],
    *,
    runtime_agent_id: str | None = None,
    status: str = "SUCCEEDED",
) -> dict:
    return research_package.record_attempt(
        package,
        runtime_agent_id=runtime_agent_id or f"round-{round_number}-{role}",
        role=role,
        round_number=round_number,
        candidate_hash=hashes[0],
        input_envelope_hash=hashes[1],
        status=status,
        output_hash=output_hash(role, round_number) if status == "SUCCEEDED" else None,
        slot_closed=True,
        close_evidence={"closed_by": "runtime", "role": role},
        now=START + timedelta(minutes=round_number * 5),
    )


def record_required_attempts(
    package: dict,
    round_number: int,
    hashes: tuple[str, str],
    *,
    omit: str | None = None,
) -> None:
    for role in research_package.REQUIRED_ROLES:
        if role != omit:
            record_attempt(package, role, round_number, hashes)


def record_lenses(
    package: dict,
    round_number: int,
    hashes: tuple[str, str],
    *,
    verdict: str = "PASS",
    raw_findings: list | None = None,
) -> dict:
    result = {}
    for lens in research_package.LENSES:
        findings = [] if raw_findings is None else [item for item in raw_findings if item.get("lens") == lens]
        result = research_package.record_lens_result(
            package,
            round_number=round_number,
            lens=lens,
            runtime_agent_id=f"round-{round_number}-{lens}",
            candidate_hash=hashes[0],
            envelope_hash=hashes[1],
            terminal_envelope={"verdict": verdict, "findings": findings},
            now=START + timedelta(minutes=round_number * 5 + 1),
        )
    return result


def classified(raw_finding: dict, disposition: str = "HANDOFF_TO_PLANNER") -> dict:
    return {
        "raw_finding": raw_finding,
        "finding_type": "PLANNER_DECISION",
        "materiality": "PLANNING",
        "disposition": disposition,
    }


def record_adjudication(
    package: dict,
    round_number: int,
    hashes: tuple[str, str],
    adjudications: list[dict],
) -> dict:
    return research_package.record_adjudication(
        package,
        round_number=round_number,
        runtime_agent_id=f"round-{round_number}-{research_package.ADJUDICATOR_ROLE}",
        candidate_hash=hashes[0],
        envelope_hash=hashes[1],
        adjudications=adjudications,
        now=START + timedelta(minutes=round_number * 5 + 2),
    )


def passing_state(raw_findings: list | None = None) -> dict:
    package = state()
    hashes = candidate_pair(package)
    record_required_attempts(package, 1, hashes)
    record_lenses(package, 1, hashes, raw_findings=raw_findings)
    record_adjudication(
        package,
        1,
        hashes,
        [] if raw_findings is None else [classified(item) for item in raw_findings],
    )
    assert package["verdict"] == "PASS"
    return package


def emit_scorable_package(tmp_path: Path, case_id: str = "current-runtime") -> tuple[Path, dict, dict]:
    fixture = Path(__file__).parent / "fixtures/research-playbook-v2" / case_id
    public_contract = json.loads((fixture / "raw/output-contract.json").read_text(encoding="utf-8"))
    gold = json.loads((fixture / "gold.json").read_text(encoding="utf-8"))
    evidence_path = fixture / "raw/evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))["evidence"]
    evidence_sha256 = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    gold_by_id = {item["id"]: item for item in gold["predicates"]}
    package_requirements = []
    requirement_statuses = []
    for index, predicate in enumerate(public_contract["predicates"]):
        expected = gold_by_id[predicate["id"]]
        package_requirements.append(
            {
                "id": predicate["id"],
                "text": predicate["question"],
                "source": f"fixture:{case_id}:{predicate['id']}",
                "operational_maturity": predicate["maturity"],
                "evidence_availability": "AVAILABLE",
                "acceptance_intent": predicate["question"],
                "scope_id": predicate["scope_id"],
                "research_value_type": predicate["research_value_type"],
                "planner_obligations": (public_contract["planner_obligations"] if index == 0 else []),
            }
        )
        requirement_statuses.append(
            {
                "requirement_id": predicate["id"],
                "research_value": expected["value"],
                "evidence_ids": expected["required_evidence_ids"],
            }
        )
    package = research_package.create_state(
        {"objective": "Produce planner-ready fixture research.", "boundaries": [case_id]},
        package_requirements,
        next(iter(public_contract["scopes"].values())),
        "AVAILABLE",
        started_at=START,
    )
    hashes = candidate_pair(package, requirement_statuses=requirement_statuses)
    raw_findings = [raw_finding(item) for item in gold["true_material_gaps"]]
    record_required_attempts(package, 1, hashes)
    record_lenses(package, 1, hashes, raw_findings=raw_findings)
    record_adjudication(package, 1, hashes, [classified(item) for item in raw_findings])
    output = tmp_path / "scorable-package"
    research_package.emit_package(
        package,
        output,
        research_markdown="# Research\nGrounded fixture result.\n",
        evidence_index=[
            evidence_item(item["id"], item["text"], source_sha256=evidence_sha256)
            for item in evidence
        ],
        planner_readiness=planner_readiness(
            package, sorted({item["id"] for item in evidence})
        ),
        planner_handoff_markdown="# Planner handoff\nUse the package contract.\n",
        now=START + timedelta(minutes=10),
    )
    return output, public_contract, gold


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_canonical_json_and_stable_hash_are_deterministic() -> None:
    left = {"b": [2, 1], "a": {"z": True, "x": None}}
    right = {"a": {"x": None, "z": True}, "b": [2, 1]}

    assert research_package.canonical_json(left) == '{"a":{"x":null,"z":true},"b":[2,1]}'
    assert research_package.canonical_hash(left) == research_package.canonical_hash(right)
    assert research_package.stable_id("candidate", left) == research_package.stable_id("candidate", right)


def test_hash_json_file_distinguishes_canonical_identity_from_file_bytes(
    tmp_path: Path,
) -> None:
    source = tmp_path / "payload.json"
    source.write_text('{\n  "b": 2,\n  "a": 1\n}\n', encoding="utf-8")

    result = research_package.hash_json_file(source)

    assert result["hash_contract"] == ("sha256-canonical-json-utf8-no-trailing-newline-v1")
    assert result["canonical_json_sha256"] == research_package.canonical_hash({"a": 1, "b": 2})
    assert result["file_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert result["file_sha256"] != result["canonical_json_sha256"]


def test_record_candidate_reports_canonical_hash_contract() -> None:
    package = state()

    result = research_package.record_candidate(
        package,
        {
            "revision": 1,
            "material_gaps": [],
            "requirement_statuses": [
                {
                    "requirement_id": requirement["id"],
                    "research_value": "grounded",
                    "evidence_ids": [],
                }
                for requirement in package["requirements"]
            ],
        },
        {"case": "one"},
        now=START,
    )

    assert result["hash_contract"] == ("sha256-canonical-json-utf8-no-trailing-newline-v1")


def test_contract_enums_are_exact() -> None:
    assert research_package.EVIDENCE_AVAILABILITIES == {
        "AVAILABLE",
        "MISSING_REQUIRED",
        "NOT_YET_APPLICABLE",
        "EXTERNAL_BLOCKED",
    }
    assert research_package.FINDING_TYPES == {
        "FACT_GAP",
        "REQUIREMENT_GAP",
        "SATISFACTION_GAP",
        "CONTRADICTION",
        "EVIDENCE_LIMIT",
        "SCOPE_CHANGE",
        "PLANNER_DECISION",
        "NON_GAP",
    }
    assert research_package.MATERIALITIES == {"BLOCKER", "PLANNING", "CLEANUP"}
    assert research_package.DISPOSITIONS == {
        "FIX_IN_RESEARCH",
        "HANDOFF_TO_PLANNER",
        "REQUEST_SCOPE_APPROVAL",
        "BLOCKED_ON_EVIDENCE",
        "ACCEPT_LIMITATION",
        "MERGE_DUPLICATE",
        "REJECT_NON_GAP",
    }


@pytest.mark.parametrize(
    "field",
    [
        "id",
        "text",
        "source",
        "operational_maturity",
        "evidence_availability",
        "acceptance_intent",
        "scope_id",
        "research_value_type",
        "planner_obligations",
    ],
)
def test_frozen_atomic_requirement_requires_every_contract_field(field: str) -> None:
    incomplete = requirements()
    del incomplete[0][field]

    with pytest.raises(research_package.ResearchPackageError, match="must include"):
        research_package.create_state(charter(), incomplete, "MIXED", "AVAILABLE", started_at=START)


@pytest.mark.parametrize(
    "field",
    [
        "research_value",
        "evidence_ids",
        "value",
        "required_evidence_ids",
        "critical",
        "true_material_gaps",
    ],
)
def test_frozen_requirement_rejects_fields_outside_public_contract(field: str) -> None:
    invalid = requirements()
    invalid[0][field] = True

    with pytest.raises(
        research_package.ResearchPackageError,
        match="frozen requirements contain unsupported fields",
    ):
        research_package.create_state(charter(), invalid, "MIXED", "AVAILABLE", started_at=START)


def test_mixed_is_package_aggregate_only_and_rejected_on_atomic_requirement() -> None:
    package = state()
    invalid = requirements()
    invalid[0]["operational_maturity"] = "MIXED"

    assert package["operational_maturity"] == "MIXED"
    with pytest.raises(research_package.ResearchPackageError, match="aggregate/intake only"):
        research_package.create_state(charter(), invalid, "MIXED", "AVAILABLE", started_at=START)


@pytest.mark.parametrize("invalid_type", ["bool", "integer", "BOOLEAN", "", None])
def test_frozen_requirement_rejects_invalid_research_value_type(invalid_type) -> None:
    invalid = requirements()
    invalid[0]["research_value_type"] = invalid_type

    with pytest.raises(research_package.ResearchPackageError, match="research_value_type"):
        research_package.create_state(charter(), invalid, "MIXED", "AVAILABLE", started_at=START)


@pytest.mark.parametrize("legacy", ["PARTIAL", "UNAVAILABLE", "UNKNOWN"])
def test_legacy_or_unknown_evidence_statuses_fail_closed(legacy: str) -> None:
    with pytest.raises(research_package.ResearchPackageError, match="evidence availability"):
        research_package.create_state(charter(), requirements(), "MIXED", legacy, started_at=START)


def test_create_state_freezes_scope_and_fixed_budgets() -> None:
    package = state()

    assert package["requirements_hash"] == research_package.canonical_hash(package["requirements"])
    assert package["scope_hash"] == research_package.canonical_hash(
        {
            "charter": package["charter"],
            "requirements": package["requirements"],
            "operational_maturity": "MIXED",
        }
    )
    assert package["budgets"]["max_role_retries"] == 1
    assert "max_failed_role_retries" not in package["budgets"]


def test_scope_change_is_blocked_without_mutation() -> None:
    package = state()
    before = research_package.canonical_json(package)
    changed = requirements()
    changed[0]["acceptance_intent"] = "Different acceptance intent."

    result = research_package.scope_check(package, charter(), changed, "MIXED")

    assert result["verdict"] == "BLOCKED"
    assert result["reason"] == "SCOPE_CHANGE"
    assert research_package.canonical_json(package) == before


def test_attempt_retains_required_lifecycle_fields_and_rejects_reused_id() -> None:
    package = state()
    hashes = candidate_pair(package)

    result = record_attempt(package, research_package.CORE_RESEARCHER_ROLE, 1, hashes)

    stored = package["attempts"][0]
    assert stored["runtime_agent_id"] == "round-1-CORE_RESEARCHER"
    assert stored["role"] == research_package.CORE_RESEARCHER_ROLE
    assert stored["round"] == 1
    assert stored["input_envelope_hash"] == hashes[1]
    assert stored["output_hash"] == output_hash(research_package.CORE_RESEARCHER_ROLE)
    assert stored["slot_closed"] is True
    assert stored["close_evidence"]
    assert result["reason"] == "ATTEMPT_RECORDED"
    with pytest.raises(research_package.ResearchPackageError, match="cannot be reused"):
        record_attempt(package, research_package.CORE_RESEARCHER_ROLE, 1, hashes)


@pytest.mark.parametrize(
    ("output", "slot_closed", "close_evidence", "message"),
    [
        (None, True, {"closed": True}, "output_hash"),
        ("valid", False, {"closed": True}, "slot_closed=true"),
        ("valid", True, {}, "close_evidence"),
    ],
)
def test_successful_attempt_without_complete_lifecycle_is_rejected(
    output, slot_closed: bool, close_evidence, message: str
) -> None:
    package = state()
    hashes = candidate_pair(package)
    supplied_hash = output_hash("CORE_RESEARCHER") if output == "valid" else output

    with pytest.raises(research_package.ResearchPackageError, match=message):
        research_package.record_attempt(
            package,
            runtime_agent_id="agent-1",
            role=research_package.CORE_RESEARCHER_ROLE,
            round_number=1,
            candidate_hash=hashes[0],
            input_envelope_hash=hashes[1],
            status="SUCCEEDED",
            output_hash=supplied_hash,
            slot_closed=slot_closed,
            close_evidence=close_evidence,
            now=START,
        )


def test_attempt_roles_are_package_specific_not_a_generic_agent_ledger() -> None:
    package = state()
    hashes = candidate_pair(package)

    with pytest.raises(research_package.ResearchPackageError, match="attempt role"):
        research_package.record_attempt(
            package,
            runtime_agent_id="generic-agent",
            role="GENERIC_AGENT",
            round_number=1,
            candidate_hash=hashes[0],
            input_envelope_hash=hashes[1],
            status="FAILED",
            output_hash=None,
            slot_closed=True,
            close_evidence={"closed": True},
            now=START,
        )


def test_round_attempts_require_identical_input_envelope_hash() -> None:
    package = state()
    first = candidate_pair(package, 1)
    second = candidate_pair(package, 2)
    record_attempt(package, research_package.CORE_RESEARCHER_ROLE, 1, first)

    with pytest.raises(research_package.ResearchPackageError, match="identical"):
        record_attempt(package, research_package.LENSES[0], 1, second)


def test_retry_cap_is_per_round_and_role_and_every_spawn_counts() -> None:
    package = state()
    hashes = candidate_pair(package)
    role = research_package.CORE_RESEARCHER_ROLE
    record_attempt(package, role, 1, hashes, runtime_agent_id="first", status="SUCCEEDED")
    record_attempt(package, role, 1, hashes, runtime_agent_id="retry", status="FAILED")

    result = record_attempt(package, role, 1, hashes, runtime_agent_id="third-spawn", status="FAILED")

    assert result["verdict"] == "CAP_REACHED"
    assert result["reason"] == "ROLE_RETRY_BUDGET"
    assert len(package["attempts"]) == 2


def test_retry_count_resets_for_the_same_role_in_a_new_round() -> None:
    package = state()
    first = candidate_pair(package, 1)
    second = candidate_pair(package, 2)
    role = research_package.CORE_RESEARCHER_ROLE
    record_attempt(package, role, 1, first, runtime_agent_id="round-one")

    result = record_attempt(package, role, 2, second, runtime_agent_id="round-two")

    assert result["reason"] == "ATTEMPT_RECORDED"


def test_record_lens_stores_raw_findings_only() -> None:
    package = state()
    hashes = candidate_pair(package)
    raw = raw_finding("gap-1")
    record_attempt(package, research_package.LENSES[0], 1, hashes)

    research_package.record_lens_result(
        package,
        round_number=1,
        lens=research_package.LENSES[0],
        runtime_agent_id=f"round-1-{research_package.LENSES[0]}",
        candidate_hash=hashes[0],
        envelope_hash=hashes[1],
        terminal_envelope={"verdict": "GAPS", "findings": [raw]},
        now=START,
    )

    stored = package["rounds"][0]["lenses"][research_package.LENSES[0]]
    assert stored["raw_findings"] == [raw]
    assert "dispositions" not in stored
    assert "raw_adjudication" not in stored
    assert "finding_type" not in stored
    assert package["rounds"][0]["adjudication"] is None


def test_no_finding_pass_uses_exact_terminal_envelope() -> None:
    assert research_package.validate_lens_terminal_envelope(
        "INTERNAL_READINESS", {"verdict": "PASS", "findings": []}
    ) == {"verdict": "PASS", "findings": []}


def test_captured_final_v4_wrong_top_level_keys_fail_closed() -> None:
    package = state()
    hashes = candidate_pair(package)
    lens = "REQUIREMENTS_SATISFACTION"
    record_attempt(package, lens, 1, hashes)
    captured_live_output = {
        "lens": lens,
        "verdict": "PASS",
        "candidate_hash": "ce5d39bc60670a6ac7e9b79fab10c3bcd4273d335ecc9b73782ec9d98f9bd305",
        "envelope_hash": "2e4a3c9dc699a0b953e3067e43cfa6eda2abcd4a62d1edc7101c965719fbce6c",
        "raw_findings": [],
    }

    with pytest.raises(
        research_package.ResearchPackageError,
        match="exactly verdict and findings",
    ):
        research_package.record_lens_result(
            package,
            round_number=1,
            lens=lens,
            runtime_agent_id=f"round-1-{lens}",
            candidate_hash=hashes[0],
            envelope_hash=hashes[1],
            terminal_envelope=captured_live_output,
            now=START,
        )


def test_captured_final_v4_wrong_finding_keys_fail_closed() -> None:
    captured_live_finding = raw_finding(
        "current.timeout-after-acceptance-test-missing",
        lens="REQUIREMENTS_SATISFACTION",
        finding_type="SATISFACTION_GAP",
    )
    del captured_live_finding["fingerprint"]
    captured_live_finding["evidence"] = [{"evidence_id": "CR-REQ-01", "claim": "Ambiguous retry must be safe."}]

    with pytest.raises(research_package.ResearchPackageError, match="exact contract"):
        research_package.validate_lens_terminal_envelope(
            "REQUIREMENTS_SATISFACTION",
            {"verdict": "PASS", "findings": [captured_live_finding]},
        )


def test_captured_final_v4_wrong_originating_stage_fails_closed() -> None:
    captured_retry = raw_finding(
        "conflict.archive-retention-versus-pii-deletion",
        lens="REQUIREMENTS_SATISFACTION",
        finding_type="CONTRADICTION",
    )
    captured_retry["originating_stage"] = "REQUIREMENTS_SATISFACTION"

    with pytest.raises(
        research_package.ResearchPackageError,
        match="originating_stage must be RESEARCH",
    ):
        research_package.validate_lens_terminal_envelope(
            "REQUIREMENTS_SATISFACTION",
            {"verdict": "PASS", "findings": [captured_retry]},
        )


def test_captured_final_v4_finding_type_alias_fails_closed() -> None:
    captured_retry = raw_finding(
        "conflict.archive-retention-versus-pii-deletion",
        lens="REQUIREMENTS_SATISFACTION",
        finding_type="CONTRADICTION",
    )
    captured_retry["finding_type"] = captured_retry.pop("type")

    with pytest.raises(research_package.ResearchPackageError, match="exact contract"):
        research_package.validate_lens_terminal_envelope(
            "REQUIREMENTS_SATISFACTION",
            {"verdict": "PASS", "findings": [captured_retry]},
        )


def test_validate_state_rejects_persisted_malformed_raw_finding() -> None:
    package = state()
    hashes = candidate_pair(package)
    lens = "INTERNAL_READINESS"
    record_attempt(package, lens, 1, hashes)
    research_package.record_lens_result(
        package,
        round_number=1,
        lens=lens,
        runtime_agent_id=f"round-1-{lens}",
        candidate_hash=hashes[0],
        envelope_hash=hashes[1],
        terminal_envelope={
            "verdict": "GAPS",
            "findings": [raw_finding("persisted-gap")],
        },
        now=START,
    )
    package["rounds"][0]["lenses"][lens]["raw_findings"][0]["type"] = "GAP"

    with pytest.raises(research_package.ResearchPackageError, match="raw finding type"):
        research_package.validate_state(package)


@pytest.mark.parametrize("evidence", ["Source line 1.", ["Source line 1.", "Source line 2."]])
def test_raw_finding_accepts_both_documented_evidence_shapes(evidence) -> None:
    raw = raw_finding("evidence-shape")
    raw["evidence"] = evidence

    validated = research_package.validate_lens_terminal_envelope(
        "INTERNAL_READINESS", {"verdict": "PASS", "findings": [raw]}
    )

    assert validated["findings"][0]["evidence"] == evidence


def test_raw_finding_closure_evidence_is_status_bound() -> None:
    open_finding = raw_finding("open")
    open_finding["closure_evidence"] = "Not allowed while open."
    with pytest.raises(research_package.ResearchPackageError, match="forbidden"):
        research_package.validate_lens_terminal_envelope(
            "INTERNAL_READINESS", {"verdict": "PASS", "findings": [open_finding]}
        )

    closed_finding = raw_finding("closed", status="CLOSED")
    del closed_finding["closure_evidence"]
    with pytest.raises(research_package.ResearchPackageError, match="required"):
        research_package.validate_lens_terminal_envelope(
            "INTERNAL_READINESS", {"verdict": "PASS", "findings": [closed_finding]}
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("id", " ", "id must be a non-empty string"),
        ("fingerprint", "", "fingerprint must be a non-empty string"),
        ("lens", "REQUIREMENTS_COVERAGE", "lens must equal the invoked lens role"),
        ("practical_consequence", "", "practical_consequence must be a non-empty string"),
        ("type", "CONFLICT", "raw finding type"),
        ("materiality", "OPTIONAL", "raw finding materiality"),
        ("proposed_disposition", "DEFER", "raw finding proposed_disposition"),
        ("status", "TERMINAL", "raw finding status"),
    ],
)
def test_raw_finding_rejects_invalid_strings_roles_and_enums(field: str, value, message: str) -> None:
    raw = raw_finding("invalid-field")
    raw[field] = value

    with pytest.raises(research_package.ResearchPackageError, match=message):
        research_package.validate_lens_terminal_envelope("INTERNAL_READINESS", {"verdict": "PASS", "findings": [raw]})


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("requirement_ids", [], "requirement_ids"),
        ("requirement_ids", ["R1", "R1"], "requirement_ids"),
        ("requirement_ids", ["R1", " "], "requirement_ids"),
        ("evidence", "", "raw finding evidence"),
        ("evidence", [], "raw finding evidence"),
        ("evidence", ["Source.", ""], "raw finding evidence"),
        ("evidence_limitation", " ", "evidence_limitation must be a non-empty string"),
    ],
)
def test_raw_finding_rejects_empty_or_duplicate_collections(field: str, value, message: str) -> None:
    raw = raw_finding("invalid-collection")
    raw[field] = value

    with pytest.raises(research_package.ResearchPackageError, match=message):
        research_package.validate_lens_terminal_envelope("INTERNAL_READINESS", {"verdict": "PASS", "findings": [raw]})


def test_adjudicator_classifies_and_deduplicates_all_raw_findings() -> None:
    package = state()
    hashes = candidate_pair(package)
    raw = raw_finding("same-gap")
    record_required_attempts(package, 1, hashes)
    record_lenses(package, 1, hashes, raw_findings=[raw])

    result = record_adjudication(package, 1, hashes, [classified(raw)])

    stored = package["rounds"][0]["adjudication"]
    assert result["verdict"] == "PASS"
    assert stored["runtime_agent_id"] == "round-1-ADJUDICATOR"
    assert len(stored["findings"]) == 1
    assert stored["findings"][0]["finding_type"] == "PLANNER_DECISION"
    assert stored["findings"][0]["materiality"] == "PLANNING"
    assert stored["findings"][0]["disposition"] == "HANDOFF_TO_PLANNER"


def test_adjudication_rejects_missing_or_invented_raw_findings() -> None:
    package = state()
    hashes = candidate_pair(package)
    raw = raw_finding("real")
    record_required_attempts(package, 1, hashes)
    record_lenses(package, 1, hashes, raw_findings=[raw])

    with pytest.raises(research_package.ResearchPackageError, match="classify and deduplicate all"):
        record_adjudication(package, 1, hashes, [])
    with pytest.raises(research_package.ResearchPackageError, match="cannot introduce"):
        record_adjudication(package, 1, hashes, [classified(raw_finding("invented"))])


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("finding_type", "UNKNOWN"),
        ("materiality", "OPTIONAL"),
        ("disposition", "ACTIONABLE"),
    ],
)
def test_adjudication_rejects_values_outside_exact_enums(field: str, value: str) -> None:
    package = state()
    hashes = candidate_pair(package)
    raw = raw_finding("gap")
    record_required_attempts(package, 1, hashes)
    record_lenses(package, 1, hashes, raw_findings=[raw])
    item = classified(raw)
    item[field] = value

    with pytest.raises(research_package.ResearchPackageError, match=field):
        record_adjudication(package, 1, hashes, [item])


def test_pass_requires_core_three_lenses_and_adjudicator_success_in_same_round() -> None:
    package = state()
    hashes = candidate_pair(package)
    record_required_attempts(package, 1, hashes, omit=research_package.CORE_RESEARCHER_ROLE)
    record_lenses(package, 1, hashes)

    result = record_adjudication(package, 1, hashes, [])

    assert result["verdict"] == "IN_PROGRESS"
    assert result["reason"] == "AWAITING_REQUIRED_ATTEMPTS"
    result = record_attempt(package, research_package.CORE_RESEARCHER_ROLE, 1, hashes)
    assert result["verdict"] == "PASS"
    assert package["result"]["reason"] == "ROUND_CONTRACT_SATISFIED"


def test_adjudication_rejects_silent_loss_of_candidate_material_gap() -> None:
    package = state()
    hashes = candidate_pair(package, material_gaps=["planner.gap"])
    record_required_attempts(package, 1, hashes)
    record_lenses(package, 1, hashes)

    with pytest.raises(
        research_package.ResearchPackageError,
        match="adjudication omits candidate material gaps: \\['planner.gap'\\]",
    ):
        record_adjudication(package, 1, hashes, [])

    assert package["rounds"][0]["adjudication"] is None


def test_adjudication_preserves_classified_candidate_material_gap() -> None:
    package = state()
    hashes = candidate_pair(package, material_gaps=["planner.gap"])
    finding = raw_finding("planner.gap")
    record_required_attempts(package, 1, hashes)
    record_lenses(package, 1, hashes, raw_findings=[finding])

    result = record_adjudication(package, 1, hashes, [classified(finding)])

    assert result["verdict"] == "PASS"
    assert package["rounds"][0]["adjudication"]["findings"][0]["raw_finding"]["id"] == (
        "planner.gap"
    )


def test_lenses_in_one_round_must_use_same_candidate_and_envelope() -> None:
    package = state()
    first = candidate_pair(package, 1)
    second_record = research_package.record_candidate(
        package,
        {
            "revision": 2,
            "material_gaps": [],
            "requirement_statuses": [
                {
                    "requirement_id": requirement["id"],
                    "research_value": "grounded",
                    "evidence_ids": [],
                }
                for requirement in package["requirements"]
            ],
        },
        {"evidence": ["src/module.py:1"]},
        now=START + timedelta(minutes=2),
    )
    second = (second_record["candidate_hash"], second_record["envelope_hash"])
    assert first[1] == second[1]
    record_attempt(package, research_package.LENSES[0], 1, first)
    research_package.record_lens_result(
        package,
        round_number=1,
        lens=research_package.LENSES[0],
        runtime_agent_id=f"round-1-{research_package.LENSES[0]}",
        candidate_hash=first[0],
        envelope_hash=first[1],
        terminal_envelope={"verdict": "PASS", "findings": []},
        now=START,
    )
    record_attempt(package, research_package.LENSES[1], 1, second)

    with pytest.raises(research_package.ResearchPackageError, match="same candidate/envelope"):
        research_package.record_lens_result(
            package,
            round_number=1,
            lens=research_package.LENSES[1],
            runtime_agent_id=f"round-1-{research_package.LENSES[1]}",
            candidate_hash=second[0],
            envelope_hash=second[1],
            terminal_envelope={"verdict": "PASS", "findings": []},
            now=START,
        )


@pytest.mark.parametrize(
    ("disposition", "expected_verdict"),
    [
        ("FIX_IN_RESEARCH", "IN_PROGRESS"),
        ("REQUEST_SCOPE_APPROVAL", "BLOCKED"),
        ("BLOCKED_ON_EVIDENCE", "BLOCKED"),
    ],
)
def test_pass_is_refused_for_each_blocking_disposition(disposition: str, expected_verdict: str) -> None:
    package = state()
    hashes = candidate_pair(package)
    raw = raw_finding(disposition)
    record_required_attempts(package, 1, hashes)
    record_lenses(package, 1, hashes, raw_findings=[raw])

    result = record_adjudication(package, 1, hashes, [classified(raw, disposition=disposition)])

    assert result["verdict"] == expected_verdict
    assert result["verdict"] != "PASS"


@pytest.mark.parametrize(
    "disposition",
    [
        "HANDOFF_TO_PLANNER",
        "ACCEPT_LIMITATION",
        "MERGE_DUPLICATE",
        "REJECT_NON_GAP",
    ],
)
def test_non_blocking_adjudication_dispositions_allow_pass(disposition: str) -> None:
    package = state()
    hashes = candidate_pair(package)
    raw = raw_finding(disposition)
    record_required_attempts(package, 1, hashes)
    record_lenses(package, 1, hashes, raw_findings=[raw])

    result = record_adjudication(package, 1, hashes, [classified(raw, disposition=disposition)])

    assert result["verdict"] == "PASS"


@pytest.mark.parametrize("lens_verdict", ["GAPS", "BLOCKED"])
def test_adjudication_can_reject_a_provisional_lens_verdict(lens_verdict: str) -> None:
    package = state()
    hashes = candidate_pair(package)
    raw = raw_finding(f"rejected-{lens_verdict.lower()}")
    record_required_attempts(package, 1, hashes)
    record_lenses(package, 1, hashes, verdict=lens_verdict, raw_findings=[raw])

    result = record_adjudication(package, 1, hashes, [classified(raw, disposition="REJECT_NON_GAP")])

    assert result["verdict"] == "PASS"
    research_package.validate_state(package)


def test_rejected_blocker_does_not_hide_an_adjudicated_research_fix() -> None:
    package = state()
    hashes = candidate_pair(package)
    rejected = raw_finding("false-blocker")
    actionable = raw_finding("real-research-fix")
    record_required_attempts(package, 1, hashes)
    record_lenses(package, 1, hashes, verdict="BLOCKED", raw_findings=[rejected, actionable])

    result = record_adjudication(
        package,
        1,
        hashes,
        [
            classified(rejected, disposition="REJECT_NON_GAP"),
            classified(actionable, disposition="FIX_IN_RESEARCH"),
        ],
    )

    assert result["verdict"] == "IN_PROGRESS"
    assert result["reason"] == "FIX_IN_RESEARCH"


def test_idempotent_adjudication_replay_recomputes_a_stale_derived_verdict() -> None:
    package = state()
    hashes = candidate_pair(package)
    raw = raw_finding("rejected-provisional-gap")
    record_required_attempts(package, 1, hashes)
    record_lenses(package, 1, hashes, verdict="GAPS", raw_findings=[raw])
    adjudications = [classified(raw, disposition="REJECT_NON_GAP")]
    first = record_adjudication(package, 1, hashes, adjudications)
    assert first["verdict"] == "PASS"
    package["verdict"] = "IN_PROGRESS"
    package["result"] = {
        "verdict": "IN_PROGRESS",
        "reason": "LENS_GAPS",
        "candidate_hash": hashes[0],
        "envelope_hash": hashes[1],
        "actionable_fingerprints": [],
    }

    replayed = record_adjudication(package, 1, hashes, adjudications)

    assert replayed["verdict"] == "PASS"
    assert replayed["reason"] == "ADJUDICATION_REEVALUATED"
    research_package.validate_state(package)


def test_lens_contract_maps_planner_owned_findings_to_pass() -> None:
    contract = (Path(__file__).parents[1] / "skills/research-playbook/references/lenses-and-findings.md").read_text(
        encoding="utf-8"
    )

    assert "Every lens returns one JSON object with exactly these two keys" in contract
    assert "Every raw finding is one JSON object with exactly these required keys" in contract
    assert "No aliases, field translation, dropped/default fields" in contract
    assert "Return `PASS` when the research question is answered" in contract
    assert "A `PASS` lens may therefore emit findings" in contract
    assert "Return `GAPS` only when" in contract
    assert "`FIX_IN_RESEARCH`" in contract
    assert "Return `BLOCKED` only when" in contract
    assert "`BLOCKED_ON_EVIDENCE` or `REQUEST_SCOPE_APPROVAL`" in contract
    assert "emit the exact public material-gap candidate `id`" in contract
    assert "only restates an existing frozen planner" in contract
    assert "absent deployed proof for a `FUTURE_SYSTEM` requirement" in contract
    assert "The parent validates this maturity rule" in contract


def test_core_and_satisfaction_contracts_require_two_sided_negative_evidence() -> None:
    references = Path(__file__).parents[1] / "skills/research-playbook/references"
    handoff = (references / "planner-handoff.md").read_text(encoding="utf-8")
    lenses = (references / "lenses-and-findings.md").read_text(encoding="utf-8")
    normalized_handoff = " ".join(handoff.split())
    normalized_lenses = " ".join(lenses.split())

    required_behavior = "the evidence that defines the required behavior"
    missing_behavior = "the evidence that demonstrates the missing coverage or behavior"
    assert required_behavior in normalized_handoff
    assert missing_behavior in normalized_handoff
    assert required_behavior in normalized_lenses
    assert missing_behavior in normalized_lenses
    assert "A citation to only one side is `FIX_IN_RESEARCH`" in normalized_lenses


def test_emit_package_refuses_non_pass_state(tmp_path: Path) -> None:
    with pytest.raises(research_package.ResearchPackageError, match="terminal PASS"):
        research_package.emit_package(
            state(),
            tmp_path / "package",
            research_markdown="# Research\n",
            evidence_index=[],
            planner_readiness=[],
            planner_handoff_markdown="# Planner handoff\n",
            now=START,
        )


def test_emit_package_writes_and_hashes_exact_contract_files(tmp_path: Path) -> None:
    package = passing_state([raw_finding("planner-choice")])
    frozen_requirements = research_package.canonical_json(package["requirements"])
    frozen_requirements_hash = package["requirements_hash"]
    output = tmp_path / "emitted"

    result = research_package.emit_package(
        package,
        output,
        research_markdown="# Research\nGrounded result.\n",
        evidence_index=[evidence_item("E1")],
        planner_readiness=[],
        planner_handoff_markdown="# Planner handoff\nChoose storage.\n",
        now=START + timedelta(minutes=10),
    )

    assert {path.name for path in output.iterdir()} == set(research_package.EMITTED_FILES)
    assert set(result["file_hashes"]) == set(research_package.EMITTED_FILES)
    for name, expected_hash in result["file_hashes"].items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == expected_hash
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["terminal_verdict"] == "PASS"
    assert manifest["artifact_hashes"] == {
        name: result["file_hashes"][name] for name in research_package.EMITTED_FILES if name != "manifest.json"
    }
    assert manifest["budget_use"]["rounds_used"] == 1
    assert manifest["budget_use"]["attempts_used"] == len(research_package.REQUIRED_ROLES)
    assert {item["role"] for item in manifest["lifecycle_evidence"]} == set(research_package.REQUIRED_ROLES)
    assert all(item["slot_closed"] is True for item in manifest["lifecycle_evidence"])
    emitted_requirements = json.loads((output / "requirements.json").read_text(encoding="utf-8"))
    assert [item["research_value"] for item in emitted_requirements] == [
        "grounded",
        "grounded",
    ]
    assert [item["evidence_ids"] for item in emitted_requirements] == [[], []]
    assert research_package.canonical_json(package["requirements"]) == frozen_requirements
    assert package["requirements_hash"] == frozen_requirements_hash


def test_emit_package_canonicalizes_requirement_evidence_ids_for_planner(tmp_path: Path) -> None:
    package = state()
    statuses = [
        {
            "requirement_id": requirement["id"],
            "research_value": "grounded",
            "evidence_ids": ["E2", "E1"],
        }
        for requirement in package["requirements"]
    ]
    hashes = candidate_pair(package, requirement_statuses=statuses)
    record_required_attempts(package, 1, hashes)
    record_lenses(package, 1, hashes)
    record_adjudication(package, 1, hashes, [])

    output = tmp_path / "canonical-evidence-ids"
    research_package.emit_package(
        package,
        output,
        research_markdown="# Research\nGrounded result.\n",
        evidence_index=[evidence_item("E1"), evidence_item("E2")],
        planner_readiness=[],
        planner_handoff_markdown="# Planner handoff\nUse the package.\n",
        now=START + timedelta(minutes=10),
    )

    emitted = json.loads((output / "requirements.json").read_text(encoding="utf-8"))
    assert [item["evidence_ids"] for item in emitted] == [["E1", "E2"], ["E1", "E2"]]
    assert [item["evidence_ids"] for item in statuses] == [["E2", "E1"], ["E2", "E1"]]

    emitted[0]["evidence_ids"] = ["E2", "E1"]
    with pytest.raises(research_package.ResearchPackageError, match="invalid evidence_ids"):
        research_package._validated_emitted_requirements(emitted, {"E1", "E2"})


def emit_validated_fixture(tmp_path: Path) -> Path:
    package = passing_state([])
    output = tmp_path / "validated-package"
    research_package.emit_package(
        package,
        output,
        research_markdown="# Research\nGrounded result.\n",
        evidence_index=[evidence_item("E1")],
        planner_readiness=[],
        planner_handoff_markdown="# Planner handoff\nUse the validated package.\n",
        now=START + timedelta(minutes=10),
    )
    return output


def test_validate_package_returns_exact_normalized_read_only_receipt(tmp_path: Path) -> None:
    output = emit_validated_fixture(tmp_path)
    before = {path.name: path.read_bytes() for path in output.iterdir()}

    receipt = research_package.validate_package(output)

    assert set(receipt) == {
        "schema_version",
        "valid",
        "package_root",
        "package_id",
        "terminal_verdict",
        "candidate_hash",
        "envelope_hash",
        "manifest_sha256",
        "owned_files",
        "requirements",
        "evidence_index",
    }
    assert receipt["valid"] is True
    assert receipt["terminal_verdict"] == "PASS"
    assert receipt["package_root"] == str(output.resolve())
    assert [item["path"] for item in receipt["owned_files"]] == sorted(
        research_package.EMITTED_FILES
    )
    assert receipt["requirements"] == json.loads(
        (output / "requirements.json").read_text(encoding="utf-8")
    )
    assert receipt["evidence_index"] == [evidence_item("E1")]
    assert {path.name: path.read_bytes() for path in output.iterdir()} == before


def test_validate_package_accepts_exact_legacy_budget_use_shape(tmp_path: Path) -> None:
    output = emit_validated_fixture(tmp_path)
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    current = manifest["budget_use"]
    manifest["budget_use"] = {
        "rounds_used": current["rounds_used"],
        "rounds_max": current["rounds_max"],
        "attempts_used": current["attempts_used"],
        "attempts_max": current["attempts_max"],
        "minutes_used": current["workflow_minutes_used"],
        "minutes_max": current["minutes_max_per_task"],
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    assert research_package.validate_package(output)["valid"] is True


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("artifact", "artifact hash mismatch"),
        ("extra-file", "exactly the six owned files"),
        ("manifest-field", "exact field set"),
        ("lifecycle", "complete successful role set"),
        ("package-id", "package_id is invalid"),
        ("timestamp", "manifest emitted_at is invalid"),
        ("text-encoding", "text is not UTF-8"),
    ],
)
def test_validate_package_rejects_package_tamper(
    tmp_path: Path, mutation: str, message: str
) -> None:
    output = emit_validated_fixture(tmp_path)
    manifest_path = output / "manifest.json"
    if mutation == "artifact":
        (output / "research.md").write_text("tampered\n", encoding="utf-8")
    elif mutation == "extra-file":
        (output / "extra.txt").write_text("unexpected\n", encoding="utf-8")
    elif mutation == "text-encoding":
        (output / "research.md").write_bytes(b"\xff")
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if mutation == "manifest-field":
            manifest["unexpected"] = True
        elif mutation == "package-id":
            manifest["package_id"] = "research-package-not-a-hash"
        elif mutation == "timestamp":
            manifest["emitted_at"] = "not-a-timestamp"
        else:
            final_round = manifest["budget_use"]["rounds_used"]
            manifest["lifecycle_evidence"] = [
                item
                for item in manifest["lifecycle_evidence"]
                if not (item["round"] == final_round and item["role"] == "ADJUDICATOR")
            ]
            manifest["budget_use"]["attempts_used"] -= 1
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    with pytest.raises(research_package.ResearchPackageError, match=message):
        research_package.validate_package(output)


def test_validate_package_rejects_symlink_owned_file(tmp_path: Path) -> None:
    output = emit_validated_fixture(tmp_path)
    research_path = output / "research.md"
    external = tmp_path / "external.md"
    external.write_bytes(research_path.read_bytes())
    research_path.unlink()
    research_path.symlink_to(external)

    with pytest.raises(research_package.ResearchPackageError, match="regular file"):
        research_package.validate_package(output)


def test_validate_package_cli_failure_is_exact_and_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = emit_validated_fixture(tmp_path)
    (output / "research.md").write_text("tampered\n", encoding="utf-8")

    assert research_package.main(["validate-package", str(output)]) == 2
    response = json.loads(capsys.readouterr().out)
    assert set(response) == {"schema_version", "valid", "reason", "error"}
    assert response["schema_version"] == 1
    assert response["valid"] is False
    assert response["reason"] == "INVALID_PACKAGE"
    assert response["error"]


def test_emit_package_rejects_missing_structured_planner_readiness(tmp_path: Path) -> None:
    frozen = requirements()
    frozen[0]["planner_obligations"] = [
        {"id": "locate-current-boundary", "description": "Use grounded current-runtime anchors."}
    ]
    package = research_package.create_state(
        charter(), frozen, "MIXED", "AVAILABLE", started_at=START
    )
    hashes = candidate_pair(package)
    record_required_attempts(package, 1, hashes)
    record_lenses(package, 1, hashes)
    record_adjudication(package, 1, hashes, [])

    with pytest.raises(
        research_package.ResearchPackageError,
        match="planner readiness coverage mismatch",
    ):
        research_package.emit_package(
            package,
            tmp_path / "missing-readiness",
            research_markdown="# Research\nGrounded result.\n",
            evidence_index=[],
            planner_readiness=[],
            planner_handoff_markdown="# Planner handoff\n",
            now=START + timedelta(minutes=10),
        )


def test_emit_package_accepts_adjudicated_rejection_of_provisional_lens_gap(
    tmp_path: Path,
) -> None:
    package = state()
    hashes = candidate_pair(package)
    raw = raw_finding("false-gap")
    record_required_attempts(package, 1, hashes)
    for lens in research_package.LENSES:
        research_package.record_lens_result(
            package,
            round_number=1,
            lens=lens,
            runtime_agent_id=f"round-1-{lens}",
            candidate_hash=hashes[0],
            envelope_hash=hashes[1],
            terminal_envelope={
                "verdict": "GAPS" if lens == "INTERNAL_READINESS" else "PASS",
                "findings": [raw] if lens == "INTERNAL_READINESS" else [],
            },
            now=START + timedelta(minutes=6),
        )
    record_adjudication(
        package,
        1,
        hashes,
        [classified(raw, disposition="REJECT_NON_GAP")],
    )

    assert package["verdict"] == "PASS"
    result = research_package.emit_package(
        package,
        tmp_path / "adjudicated-package",
        research_markdown="# Research\nGrounded result.\n",
        evidence_index=[],
        planner_readiness=[],
        planner_handoff_markdown="# Planner handoff\nUse the package.\n",
        now=START + timedelta(minutes=10),
    )

    assert result["verdict"] == "PASS"
    assert set(result["file_hashes"]) == set(research_package.EMITTED_FILES)


@pytest.mark.parametrize(
    ("statuses", "include_statuses", "message"),
    [
        (None, False, "candidate must include requirement_statuses"),
        (
            [
                {
                    "requirement_id": "R1",
                    "research_value": "grounded",
                    "evidence_ids": [],
                }
            ],
            True,
            "requirement statuses must cover frozen requirements exactly",
        ),
    ],
)
def test_record_candidate_refuses_missing_or_partial_requirement_statuses(
    statuses: list[dict] | None,
    include_statuses: bool,
    message: str,
) -> None:
    package = state()
    with pytest.raises(research_package.ResearchPackageError, match=message):
        candidate_pair(
            package,
            requirement_statuses=statuses,
            include_requirement_statuses=include_statuses,
        )


def test_record_candidate_rejects_richer_status_shape_before_storing() -> None:
    package = state()
    candidate = {
        "revision": 1,
        "requirement_statuses": [
            {
                "requirement_id": requirement["id"],
                "status": "SUPPORTED",
                "conclusion": "grounded",
                "evidence_ids": [],
            }
            for requirement in package["requirements"]
        ],
    }

    with pytest.raises(
        research_package.ResearchPackageError,
        match="every requirement status must contain requirement_id",
    ):
        research_package.record_candidate(package, candidate, {"case": "one"}, now=START)

    assert package["candidates"] == {}


def test_record_candidate_rejects_research_value_type_mismatch_before_storing() -> None:
    typed_requirements = requirements()
    typed_requirements[0]["research_value_type"] = "boolean"
    package = research_package.create_state(
        charter(), typed_requirements, "MIXED", "AVAILABLE", started_at=START
    )
    statuses = [
        {
            "requirement_id": requirement["id"],
            "research_value": "Yes" if requirement["id"] == "R1" else "grounded",
            "evidence_ids": [],
        }
        for requirement in package["requirements"]
    ]

    with pytest.raises(
        research_package.ResearchPackageError,
        match="requirement R1 research_value must have type boolean, got string",
    ):
        candidate_pair(package, requirement_statuses=statuses)

    assert package["candidates"] == {}


def test_record_candidate_accepts_boolean_research_value_for_boolean_contract() -> None:
    typed_requirements = requirements()
    typed_requirements[0]["research_value_type"] = "boolean"
    package = research_package.create_state(
        charter(), typed_requirements, "MIXED", "AVAILABLE", started_at=START
    )
    statuses = [
        {
            "requirement_id": requirement["id"],
            "research_value": True if requirement["id"] == "R1" else "grounded",
            "evidence_ids": [],
        }
        for requirement in package["requirements"]
    ]

    candidate_hash, _ = candidate_pair(package, requirement_statuses=statuses)

    assert candidate_hash


def test_load_rejects_tampered_candidate_payload(tmp_path: Path) -> None:
    package = state()
    candidate_pair(package)
    candidate_record = next(iter(package["candidates"].values()))
    candidate_record["candidate_payload"]["revision"] = 999
    path = tmp_path / "state.json"
    research_package.atomic_write(path, package)

    with pytest.raises(research_package.ResearchPackageError, match="candidate payload hash does not match"):
        research_package.load_state(path)


def test_load_rejects_round_retargeted_to_an_unreviewed_candidate(tmp_path: Path) -> None:
    package = state()
    reviewed = candidate_pair(package, 1)
    unreviewed = candidate_pair(package, 2)
    record_required_attempts(package, 1, reviewed)
    record_lenses(package, 1, reviewed)
    record_adjudication(package, 1, reviewed, [])
    assert package["verdict"] == "PASS"

    round_record = package["rounds"][0]
    unreviewed_record = next(item for item in package["candidates"].values() if item["candidate_hash"] == unreviewed[0])
    round_record["candidate_id"] = unreviewed_record["candidate_id"]
    round_record["candidate_hash"] = unreviewed[0]
    round_record["envelope_hash"] = unreviewed[1]
    round_record["round_id"] = research_package.stable_id(
        "lens-round", package["package_id"], 1, unreviewed[0], unreviewed[1]
    )
    package["result"]["candidate_hash"] = unreviewed[0]
    package["result"]["envelope_hash"] = unreviewed[1]
    path = tmp_path / "retargeted-state.json"
    research_package.atomic_write(path, package)

    with pytest.raises(
        research_package.ResearchPackageError,
        match="lens result is not bound to its round candidate",
    ):
        research_package.load_state(path)


def test_load_rejects_adjudication_retargeted_to_an_unreviewed_candidate(
    tmp_path: Path,
) -> None:
    package = state()
    reviewed = candidate_pair(package, 1)
    unreviewed = candidate_pair(package, 2)
    record_required_attempts(package, 1, reviewed)
    record_lenses(package, 1, reviewed)
    record_adjudication(package, 1, reviewed, [])
    adjudication = package["rounds"][0]["adjudication"]
    adjudication["candidate_hash"] = unreviewed[0]
    adjudication["envelope_hash"] = unreviewed[1]
    adjudication["adjudication_id"] = research_package.stable_id(
        "adjudication",
        package["package_id"],
        1,
        adjudication["runtime_agent_id"],
        unreviewed[0],
        unreviewed[1],
    )
    path = tmp_path / "retargeted-adjudication-state.json"
    research_package.atomic_write(path, package)

    with pytest.raises(
        research_package.ResearchPackageError,
        match="adjudication is not bound to a complete round candidate",
    ):
        research_package.load_state(path)


def test_load_rejects_pass_result_retargeted_to_an_unreviewed_candidate(
    tmp_path: Path,
) -> None:
    package = state()
    reviewed = candidate_pair(package, 1)
    unreviewed = candidate_pair(package, 2)
    record_required_attempts(package, 1, reviewed)
    record_lenses(package, 1, reviewed)
    record_adjudication(package, 1, reviewed, [])
    package["result"]["candidate_hash"] = unreviewed[0]
    package["result"]["envelope_hash"] = unreviewed[1]
    path = tmp_path / "retargeted-pass-result-state.json"
    research_package.atomic_write(path, package)

    with pytest.raises(
        research_package.ResearchPackageError,
        match="PASS result is not bound to its reviewed round",
    ):
        research_package.load_state(path)


def test_emit_package_rejects_unindexed_requirement_evidence(tmp_path: Path) -> None:
    package = state()
    statuses = [
        {
            "requirement_id": requirement["id"],
            "research_value": "grounded",
            "evidence_ids": ["MISSING-EVIDENCE"],
        }
        for requirement in package["requirements"]
    ]
    hashes = candidate_pair(package, requirement_statuses=statuses)
    record_required_attempts(package, 1, hashes)
    record_lenses(package, 1, hashes)
    record_adjudication(package, 1, hashes, [])

    with pytest.raises(
        research_package.ResearchPackageError,
        match="reference evidence absent from evidence_index",
    ):
        research_package.emit_package(
            package,
            tmp_path / "dangling-evidence-package",
            research_markdown="# Research\n",
            evidence_index=[evidence_item("OTHER-EVIDENCE")],
            planner_readiness=[],
            planner_handoff_markdown="# Planner handoff\n",
            now=START + timedelta(minutes=10),
        )


def test_load_rejects_tampered_success_lifecycle(tmp_path: Path) -> None:
    package = state()
    hashes = candidate_pair(package)
    record_attempt(package, research_package.CORE_RESEARCHER_ROLE, 1, hashes)
    package["attempts"][0]["close_evidence"] = {}
    path = tmp_path / "state.json"
    research_package.atomic_write(path, package)

    with pytest.raises(research_package.ResearchPackageError, match="lifecycle"):
        research_package.load_state(path)


def test_cli_initializes_frozen_scope_with_aggregate_mixed(tmp_path: Path, capsys) -> None:
    state_path = tmp_path / "package.json"
    charter_path = tmp_path / "charter.json"
    requirements_path = tmp_path / "requirements.json"
    evidence_path = tmp_path / "evidence.json"
    write_json(charter_path, charter())
    write_json(requirements_path, requirements())
    write_json(evidence_path, "AVAILABLE")

    exit_code = research_package.main(
        [
            "init",
            str(state_path),
            "--charter",
            str(charter_path),
            "--requirements",
            str(requirements_path),
            "--operational-maturity",
            "MIXED",
            "--evidence-availability",
            str(evidence_path),
            "--started-at",
            "2026-07-14T12:00:00Z",
        ]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["reason"] == "INITIALIZED"
    assert research_package.load_state(state_path)["operational_maturity"] == "MIXED"


def test_evaluator_tree_hash_matches_installer(tmp_path: Path) -> None:
    skill = tmp_path / "skill"
    nested = skill / "nested"
    nested.mkdir(parents=True)
    (skill / "SKILL.md").write_text("alpha\n", encoding="utf-8")
    (nested / "helper.py").write_text("print('ok')\n", encoding="utf-8")

    assert evaluator._tree_hash(skill) == installer.tree_hash(skill)


def test_managed_snapshot_allows_only_expected_v2_addition(tmp_path: Path) -> None:
    root = tmp_path / "installed"
    root.mkdir()
    manifest = tmp_path / "managed.txt"
    manifest.write_text("research-playbook\nresearch-playbook-v2\n", encoding="utf-8")
    legacy = root / "research-playbook"
    legacy.mkdir()
    (legacy / "SKILL.md").write_text("legacy\n", encoding="utf-8")
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"

    evaluator.cmd_snapshot_managed(SimpleNamespace(manifest=manifest, root=root, output=before))
    candidate = root / "research-playbook-v2"
    candidate.mkdir()
    (candidate / "SKILL.md").write_text("v2\n", encoding="utf-8")
    evaluator.cmd_snapshot_managed(SimpleNamespace(manifest=manifest, root=root, output=after))

    result = evaluator.cmd_compare_managed(
        SimpleNamespace(
            before=before,
            after=after,
            allow_added=["research-playbook-v2"],
            exact=False,
        )
    )
    assert result["ok"] is True
    assert result["added"] == ["research-playbook-v2"]


def test_managed_snapshot_exact_mode_allows_stable_missing_candidate(tmp_path: Path) -> None:
    root = tmp_path / "installed"
    root.mkdir()
    manifest = tmp_path / "managed.txt"
    manifest.write_text("research-playbook\nresearch-playbook-v2\n", encoding="utf-8")
    legacy = root / "research-playbook"
    legacy.mkdir()
    (legacy / "SKILL.md").write_text("legacy\n", encoding="utf-8")
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    evaluator.cmd_snapshot_managed(SimpleNamespace(manifest=manifest, root=root, output=before))
    evaluator.cmd_snapshot_managed(SimpleNamespace(manifest=manifest, root=root, output=after))

    result = evaluator.cmd_compare_managed(SimpleNamespace(before=before, after=after, allow_added=[], exact=True))

    assert result["ok"] is True
    assert result["stable_missing"] == ["research-playbook-v2"]


def restore_fixture(tmp_path: Path) -> dict[str, Path]:
    root = tmp_path / "installed"
    shared = root / "_shared"
    shared.mkdir(parents=True)
    target = shared / "state.py"
    target.write_text("sealed\n", encoding="utf-8")
    installed = shared / "cache/installed.py"
    installed.parent.mkdir()
    installed.write_text("sealed\n", encoding="utf-8")
    manifest = tmp_path / "managed.txt"
    manifest.write_text("_shared\nresearch-playbook-v2\n", encoding="utf-8")
    expected = tmp_path / "expected.json"
    evaluator.cmd_snapshot_managed(SimpleNamespace(manifest=manifest, root=root, output=expected))

    recovery = tmp_path / "recovery.py"
    recovery.write_text("sealed\n", encoding="utf-8")
    target.write_text("dirty\n", encoding="utf-8")
    installed.unlink()
    installed.parent.rmdir()
    candidate = root / "research-playbook-v2"
    candidate.mkdir()
    (candidate / "SKILL.md").write_text("candidate\n", encoding="utf-8")
    plan = tmp_path / "restore.json"
    write_json(
        plan,
        {
            "schema_version": 1,
            "operations": [
                {"kind": "move_aside", "target": "research-playbook-v2"},
                {
                    "kind": "restore_file",
                    "source": str(recovery),
                    "source_sha256": evaluator._sha256_file(recovery),
                    "target": "_shared/state.py",
                },
                {
                    "kind": "restore_file",
                    "source": str(recovery),
                    "source_sha256": evaluator._sha256_file(recovery),
                    "target": "_shared/cache/installed.py",
                },
            ],
        },
    )
    return {
        "root": root,
        "target": target,
        "installed": installed,
        "manifest": manifest,
        "expected": expected,
        "recovery": recovery,
        "candidate": candidate,
        "plan": plan,
        "backup": tmp_path / "backup",
        "output": tmp_path / "restored.json",
    }


def test_restore_managed_recovers_exact_snapshot_and_keeps_backup(tmp_path: Path) -> None:
    fixture = restore_fixture(tmp_path)

    result = evaluator.cmd_restore_managed(
        SimpleNamespace(
            manifest=fixture["manifest"],
            root=fixture["root"],
            expected=fixture["expected"],
            plan=fixture["plan"],
            backup_root=fixture["backup"],
            output=fixture["output"],
        )
    )

    assert result["ok"] is True
    assert result["operation_count"] == 3
    assert fixture["target"].read_text(encoding="utf-8") == "sealed\n"
    assert fixture["installed"].read_text(encoding="utf-8") == "sealed\n"
    assert not fixture["candidate"].exists()
    assert (fixture["backup"] / "move_aside/research-playbook-v2/SKILL.md").is_file()
    assert json.loads(fixture["output"].read_text()) == json.loads(fixture["expected"].read_text())


def test_restore_managed_refuses_bad_source_hash_before_mutation(tmp_path: Path) -> None:
    fixture = restore_fixture(tmp_path)
    plan = json.loads(fixture["plan"].read_text())
    plan["operations"][1]["source_sha256"] = "0" * 64
    write_json(fixture["plan"], plan)

    with pytest.raises(evaluator.HarnessError, match="restore-source-mismatch"):
        evaluator.cmd_restore_managed(
            SimpleNamespace(
                manifest=fixture["manifest"],
                root=fixture["root"],
                expected=fixture["expected"],
                plan=fixture["plan"],
                backup_root=fixture["backup"],
                output=fixture["output"],
            )
        )

    assert fixture["target"].read_text(encoding="utf-8") == "dirty\n"
    assert not fixture["installed"].exists()
    assert not fixture["installed"].parent.exists()
    assert fixture["candidate"].is_dir()
    assert not fixture["backup"].exists()


def test_restore_managed_rolls_back_when_full_snapshot_does_not_match(tmp_path: Path) -> None:
    fixture = restore_fixture(tmp_path)
    plan = json.loads(fixture["plan"].read_text())
    plan["operations"] = plan["operations"][1:]
    write_json(fixture["plan"], plan)

    with pytest.raises(evaluator.HarnessError, match="restored-managed-snapshot-mismatch"):
        evaluator.cmd_restore_managed(
            SimpleNamespace(
                manifest=fixture["manifest"],
                root=fixture["root"],
                expected=fixture["expected"],
                plan=fixture["plan"],
                backup_root=fixture["backup"],
                output=fixture["output"],
            )
        )

    assert fixture["target"].read_text(encoding="utf-8") == "dirty\n"
    assert not fixture["installed"].exists()
    assert not fixture["installed"].parent.exists()
    assert fixture["candidate"].is_dir()
    assert not fixture["backup"].exists()


def prepared_evaluation(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run"
    fixtures = Path(__file__).parent / "fixtures/research-playbook-v2"
    result = evaluator.cmd_prepare(SimpleNamespace(fixtures=fixtures, output=run_dir))
    assert result["execution_count"] == 18
    return run_dir


def test_evaluator_prepare_stages_only_raw_inputs_and_locks_matrix(tmp_path: Path) -> None:
    run_dir = prepared_evaluation(tmp_path)
    lock = json.loads((run_dir / evaluator.LOCK_FILE).read_text(encoding="utf-8"))

    assert len(lock["matrix"]) == 18
    assert set(lock["case_ids"]) == set(evaluator.CASE_IDS)
    assert not (run_dir / ".evaluator").exists()
    for case_id in evaluator.CASE_IDS:
        visible = run_dir / "inputs" / case_id
        assert sorted(path.name for path in (visible / "raw").iterdir()) == [
            "evidence.json",
            "output-contract.json",
            "request.md",
        ]
        assert not list(visible.rglob("*gold*"))
        envelope_text = "\n".join(path.read_text(encoding="utf-8") for path in visible.glob("*-research-envelope.json"))
        assert ".evaluator" not in envelope_text
        assert "gold" not in envelope_text.lower()


def test_evaluator_prepare_can_lock_the_canonical_three_sentinel_profile(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "bounded-run"
    fixtures = Path(__file__).parent / "fixtures/research-playbook-v2"
    selected = ["scope-inflation-trap", "current-runtime", "mixed-maturity"]

    result = evaluator.cmd_prepare(
        SimpleNamespace(fixtures=fixtures, output=run_dir, case_id=selected)
    )
    lock = evaluator._load_lock(run_dir)

    assert result["case_count"] == 3
    assert result["execution_count"] == 9
    assert lock["case_ids"] == [
        "current-runtime",
        "mixed-maturity",
        "scope-inflation-trap",
    ]
    assert len(lock["matrix"]) == 9
    assert sorted(path.name for path in (run_dir / "inputs").iterdir()) == lock[
        "case_ids"
    ]


@pytest.mark.parametrize(
    ("case_ids", "error"),
    [
        (["current-runtime", "current-runtime"], "selected-case-ids-contains-duplicates"),
        (["not-a-case"], "unknown-selected-case-ids:not-a-case"),
    ],
)
def test_evaluator_prepare_rejects_invalid_case_selection(
    tmp_path: Path, case_ids: list[str], error: str
) -> None:
    fixtures = Path(__file__).parent / "fixtures/research-playbook-v2"

    with pytest.raises(evaluator.HarnessError, match=error):
        evaluator.cmd_prepare(
            SimpleNamespace(
                fixtures=fixtures,
                output=tmp_path / "invalid-run",
                case_id=case_ids,
            )
        )


def test_evaluator_stages_public_output_contract_without_gold_answers(tmp_path: Path) -> None:
    run_dir = prepared_evaluation(tmp_path)
    fixtures = Path(__file__).parent / "fixtures/research-playbook-v2"

    for case_id in evaluator.CASE_IDS:
        contract_path = run_dir / "inputs" / case_id / "raw" / "output-contract.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        gold = json.loads((fixtures / case_id / "gold.json").read_text(encoding="utf-8"))

        assert contract["scopes"] == gold["scopes"]
        assert {item["id"] for item in contract["predicates"]} == {item["id"] for item in gold["predicates"]}
        assert all(
            set(item) == {"id", "scope_id", "maturity", "question", "research_value_type"}
            for item in contract["predicates"]
        )
        gold_by_id = {item["id"]: item for item in gold["predicates"]}
        assert all(
            evaluator._research_value_type(gold_by_id[item["id"]]["value"])
            == item["research_value_type"]
            for item in contract["predicates"]
        )
        assert set(gold["true_material_gaps"]) <= {item["id"] for item in contract["material_gap_candidates"]}
        assert {item["id"] for item in contract["planner_obligations"]} == set(gold["planner_rubric"])
        serialized = json.dumps(contract, sort_keys=True)
        for hidden_field in ("value", "required_evidence_ids", "critical", "true_material_gaps"):
            assert f'"{hidden_field}"' not in serialized


def test_evaluator_record_rejects_duplicate_tuple(tmp_path: Path) -> None:
    run_dir = prepared_evaluation(tmp_path)
    lock = json.loads((run_dir / evaluator.LOCK_FILE).read_text(encoding="utf-8"))
    entry = next(item for item in lock["matrix"] if item["key"] == "current-runtime:legacy:research")
    output = tmp_path / "output.json"
    write_json(output, {"schema_version": 1, "claims": [], "material_gaps": []})
    args = SimpleNamespace(
        run_dir=run_dir,
        case_id="current-runtime",
        arm="legacy",
        role="research",
        agent_id="019f6188-f506-7d92-8f9c-5d95e38e0f7f",
        input_hash=entry["input"]["sha256"],
        output=output,
        output_hash=hashlib.sha256(output.read_bytes()).hexdigest(),
        slot_closed="yes",
    )

    evaluator.cmd_record(args)
    with pytest.raises(evaluator.HarnessError, match="duplicate-execution-tuple"):
        evaluator.cmd_record(args)


def test_evaluator_records_real_v2_package_and_binds_planner_to_tree_hash(
    tmp_path: Path,
) -> None:
    run_dir = prepared_evaluation(tmp_path)
    lock = json.loads((run_dir / evaluator.LOCK_FILE).read_text(encoding="utf-8"))
    research_entry = next(item for item in lock["matrix"] if item["key"] == "current-runtime:v2:research")
    package_dir = tmp_path / "package"
    research_package.emit_package(
        passing_state(),
        package_dir,
        research_markdown="# Research\nGrounded result.\n",
        evidence_index=[evidence_item("CR-CODE-01")],
        planner_readiness=[],
        planner_handoff_markdown="# Planner handoff\nUse the package.\n",
        now=START + timedelta(minutes=10),
    )
    package_hash = evaluator._tree_snapshot(package_dir)["tree_sha256"]

    evaluator.cmd_record(
        SimpleNamespace(
            run_dir=run_dir,
            case_id="current-runtime",
            arm="v2",
            role="research",
            agent_id="019f7000-0000-7000-8000-000000000001",
            input_hash=research_entry["input"]["sha256"],
            output=package_dir,
            output_hash=package_hash,
            slot_closed="yes",
        )
    )
    recorded_package = run_dir / "outputs/current-runtime/v2-research"
    assert recorded_package.is_dir()
    assert {path.name for path in recorded_package.iterdir()} == set(research_package.EMITTED_FILES)

    invalid_planner_output = tmp_path / "invalid-planner.json"
    write_json(
        invalid_planner_output,
        {
            "schema_version": 1,
            "planner": {
                "verdict": "PASS",
                "checks": {},
                "obligations": [],
                "questions": [],
                "unresolved_choices": [],
            },
        },
    )
    with pytest.raises(evaluator.HarnessError, match="invalid-output-fields"):
        evaluator.cmd_record(
            SimpleNamespace(
                run_dir=run_dir,
                case_id="current-runtime",
                arm="v2",
                role="planner",
                agent_id="019f7000-0000-7000-8000-000000000002",
                input_hash=package_hash,
                output=invalid_planner_output,
                output_hash=hashlib.sha256(invalid_planner_output.read_bytes()).hexdigest(),
                slot_closed="yes",
            )
        )
    assert not (run_dir / "outputs/current-runtime/v2-planner.json").exists()

    planner_output = tmp_path / "planner.json"
    write_json(
        planner_output,
        {
            "schema_version": 1,
            "claims": [],
            "material_gaps": [],
            "planner": {
                "verdict": "PASS",
                "checks": {},
                "obligations": [],
                "questions": [],
                "unresolved_choices": [],
            },
        },
    )
    evaluator.cmd_record(
        SimpleNamespace(
            run_dir=run_dir,
            case_id="current-runtime",
            arm="v2",
            role="planner",
            agent_id="019f7000-0000-7000-8000-000000000003",
            input_hash=package_hash,
            output=planner_output,
            output_hash=hashlib.sha256(planner_output.read_bytes()).hexdigest(),
            slot_closed="yes",
        )
    )


def test_evaluator_loads_scoring_data_from_real_v2_package_and_rejects_tamper(
    tmp_path: Path,
) -> None:
    package_dir, public_contract, gold = emit_scorable_package(tmp_path)

    loaded = evaluator._load_v2_package(package_dir)

    assert {item["predicate_id"] for item in loaded["claims"]} == {item["id"] for item in gold["predicates"]}
    assert loaded["material_gaps"] == gold["true_material_gaps"]
    assert loaded["planner_contract"] == sorted(public_contract["planner_obligations"], key=lambda item: item["id"])
    assert all(item["slot_closed"] is True for item in loaded["lifecycle"])

    (package_dir / "research.md").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(evaluator.HarnessError, match="artifact-hash-mismatch:research.md"):
        evaluator._load_v2_package(package_dir)


def test_evaluator_score_refuses_incomplete_matrix(tmp_path: Path) -> None:
    run_dir = prepared_evaluation(tmp_path)
    with pytest.raises(evaluator.HarnessError, match="incomplete-matrix"):
        evaluator.cmd_score(SimpleNamespace(run_dir=run_dir))


def test_evaluator_lifecycle_requires_hashes_close_evidence_and_complete_round() -> None:
    lifecycle = []
    for index, role in enumerate(evaluator.REQUIRED_LIFECYCLE_ROLES, 1):
        lifecycle.append(
            {
                "round": 1,
                "role": role,
                "runtime_agent_id": f"019f0000-0000-7000-8000-{index:012d}",
                "input_envelope_hash": "a" * 64,
                "output_hash": "b" * 64,
                "status": "SUCCEEDED",
                "slot_closed": True,
                "close_evidence": f"closed role {role}",
            }
        )
    output = {
        "budget": {
            "rounds": 1,
            "attempts": 5,
            "workflow_elapsed_minutes": 90,
            "minutes_max_per_task": 60,
        },
        "lifecycle": lifecycle,
    }

    result = evaluator._evaluate_budget(output)
    assert result["pass"] is True
    assert result["complete_rounds"] == [1]

    lifecycle[0]["close_evidence"] = ""
    with pytest.raises(evaluator.HarnessError, match="close-evidence"):
        evaluator._evaluate_budget(output)


def test_evaluator_lifecycle_allows_unhashed_failed_retry_but_does_not_count_it() -> None:
    lifecycle = [
        {
            "round": 1,
            "role": "INTERNAL_READINESS",
            "runtime_agent_id": "019f0000-0000-7000-8000-000000000000",
            "input_envelope_hash": "a" * 64,
            "output_hash": None,
            "status": "FAILED",
            "slot_closed": True,
            "close_evidence": "failed attempt closed without retained output",
        }
    ]
    for index, role in enumerate(evaluator.REQUIRED_LIFECYCLE_ROLES, 1):
        lifecycle.append(
            {
                "round": 1,
                "role": role,
                "runtime_agent_id": f"019f0000-0000-7000-8001-{index:012d}",
                "input_envelope_hash": "a" * 64,
                "output_hash": "b" * 64,
                "status": "SUCCEEDED",
                "slot_closed": True,
                "close_evidence": f"closed role {role}",
            }
        )
    output = {
        "budget": {
            "rounds": 1,
            "attempts": 6,
            "workflow_elapsed_minutes": 90,
            "minutes_max_per_task": 60,
        },
        "lifecycle": lifecycle,
    }

    result = evaluator._evaluate_budget(output)

    assert result["pass"] is True
    assert result["complete_rounds"] == [1]

    lifecycle[-1]["status"] = "FAILED"
    lifecycle[-1]["output_hash"] = None
    assert evaluator._evaluate_budget(output)["pass"] is False


def test_evaluator_planner_rejects_self_attested_checks_without_plan() -> None:
    gold = {"planner_rubric": ["scope_is_preserved"]}
    output = {
        "planner": {
            "verdict": "PASS",
            "checks": {"scope_is_preserved": True},
        }
    }

    assert evaluator._evaluate_planner(gold, output)["pass"] is False


def test_evaluator_planner_accepts_actionable_steps_for_every_obligation() -> None:
    public_contract = {
        "planner_obligations": [
            {"id": "scope_is_preserved", "description": "Preserve scope."},
            {"id": "verification_is_grounded", "description": "Verify from evidence."},
        ]
    }
    gold = {"planner_rubric": ["scope_is_preserved", "verification_is_grounded"]}
    output = {
        "planner": {
            "verdict": "PASS",
            "checks": {
                "scope_is_preserved": True,
                "verification_is_grounded": True,
            },
            "obligations": [
                {
                    "id": obligation_id,
                    "implementation_steps": [f"Implement {obligation_id}."],
                    "verification_steps": [f"Verify {obligation_id}."],
                    "evidence_ids": ["E1"],
                }
                for obligation_id in gold["planner_rubric"]
            ],
            "questions": [],
            "unresolved_choices": [],
        }
    }

    result = evaluator._evaluate_planner(gold, output, public_contract, allowed_evidence={"E1"})

    assert result["pass"] is True
