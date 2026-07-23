from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import discovery_candidate_reconciliation as reconciliation
from scripts import prevention_source_receipt
from scripts import sequence_candidate_contract


def discovery(root: Path, name: str, discovery_id: str, *, promoted: str | None = None) -> Path:
    path = root / "operations/sequences/discovery" / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    promoted_line = f"PromotedSequenceId: {promoted}\n" if promoted else ""
    path.write_text(
        f"# {name}\n\nDiscoveryId: {discovery_id}\nStatus: discovery\n{promoted_line}"
    )
    return path


@pytest.fixture
def candidate_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    discovery(tmp_path, "one", "discovery-one")
    discovery(tmp_path, "two", "discovery-two", promoted="registered-two")
    target = tmp_path / "operations/sequences/registered-two"
    target.mkdir(parents=True)
    (target / "sequence.md").write_text("# registered-two\n")
    (target / "dependencies.json").write_text("{}\n")
    monkeypatch.setattr(reconciliation, "_git_head", lambda root: "a" * 40)
    monkeypatch.setattr(
        reconciliation.work_memory, "registry_rows",
        lambda path=None, selected_sequence_id=None: (
            [{"sequence_id": "registered-two", "lineage_id": "discovery-two"}], "b" * 64
        ),
    )
    monkeypatch.setattr(
        reconciliation.sequence_discovery_log, "discovery_state",
        lambda path, require_bound=False: {
            "status": "ready" if path.stem == "one" else "promoted",
            "successful_runs": 2, "unmet_predicates": [], "open_blocker_ids": [],
            "source_bundle_hash": "c" * 64,
            "lineage_id": "discovery-one" if path.stem == "one" else "discovery-two",
        },
    )
    monkeypatch.setattr(
        reconciliation.discovery_promotion_lifecycle, "_registered_verified",
        lambda sequence_id, repo_roots_file=None: True,
    )
    monkeypatch.setattr(
        reconciliation, "_registered_bundle_hash",
        lambda root, sequence_id: "d" * 64,
    )
    return tmp_path


def test_audit_is_complete_and_leaves_every_decision_pending(candidate_root: Path, tmp_path: Path) -> None:
    folder = candidate_root / "operations/sequences/discovery"
    (folder / "README.md").write_text("# Discovery sequence documentation\n")
    (folder / "ACTIVE.md").write_text("# Generated active index\n")
    output = tmp_path / "audit.json"
    result = reconciliation.cmd_audit(SimpleNamespace(root=str(candidate_root), output=str(output)))
    payload = json.loads(output.read_text())
    assert result["candidate_count"] == 2
    assert payload["snapshot"]["candidate_paths"] == [
        "operations/sequences/discovery/one.md",
        "operations/sequences/discovery/two.md",
    ]
    assert [row["disposition"] for row in payload["candidates"]] == ["pending", "pending"]
    assert [row["suggested_disposition"] for row in payload["candidates"]] == [
        "promotion-review", "already-promoted",
    ]
    assert payload["candidates"][1]["registered_target_verified"] is True
    assert payload["candidates"][1]["registered_target_bundle_hash"] == "d" * 64


def test_audit_live_validates_only_its_selected_owner(
    candidate_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str | None] = []

    def registry_rows(path=None, *, selected_sequence_id=None):
        calls.append(selected_sequence_id)
        return (
            [{"sequence_id": "registered-two", "lineage_id": "discovery-two"}],
            "b" * 64,
        )

    monkeypatch.setattr(reconciliation.work_memory, "registry_rows", registry_rows)
    reconciliation.cmd_audit(SimpleNamespace(
        root=str(candidate_root), output=str(tmp_path / "audit.json"),
    ))
    assert calls == ["discovery-candidate-reconciliation"]


def test_main_returns_registry_failures_as_json(
    candidate_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def registry_rows(path=None, *, selected_sequence_id=None):
        raise reconciliation.work_memory.prevention_registry.RegistryError(
            "selected-owner-source-hash-drift"
        )

    monkeypatch.setattr(reconciliation.work_memory, "registry_rows", registry_rows)
    returncode = reconciliation.main([
        "--root", str(candidate_root), "audit",
        "--output", str(tmp_path / "audit.json"),
    ])
    result = json.loads(capsys.readouterr().err)
    assert returncode == 3
    assert result == {"ok": False, "error": "selected-owner-source-hash-drift"}


def test_mutating_audit_persists_source_owned_effect_identity(
    candidate_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "prevention-audit.json"
    monkeypatch.setattr(prevention_source_receipt, "ROOT", tmp_path / "receipts")
    prior_work_memory_configuration = (
        reconciliation.work_memory.ROOT,
        reconciliation.work_memory.LEDGER,
        reconciliation.work_memory.BLOCKER_VIEW,
        reconciliation.work_memory.REGISTRY,
        reconciliation.work_memory.REGISTRY_GOVERNANCE_LEVEL,
    )

    returncode = reconciliation.main([
        "--root", str(candidate_root), "audit", "--output", str(output),
        "--prevention-effect-id", "e" * 64,
        "--prevention-preparation-sha256", "f" * 64,
    ])

    result = json.loads(capsys.readouterr().out)
    receipt = json.loads(
        prevention_source_receipt.receipt_path("e" * 64).read_text(encoding="utf-8")
    )
    assert returncode == 0
    assert receipt["status"] == "APPLIED"
    assert receipt["profile_id"] == "audit"
    assert receipt["result_identity"]["ok"] is True
    assert result["preventionSourceReceiptSha256"] == (
        prevention_source_receipt.receipt_sha256(receipt)
    )
    assert (
        reconciliation.work_memory.ROOT,
        reconciliation.work_memory.LEDGER,
        reconciliation.work_memory.BLOCKER_VIEW,
        reconciliation.work_memory.REGISTRY,
        reconciliation.work_memory.REGISTRY_GOVERNANCE_LEVEL,
    ) == prior_work_memory_configuration


def test_candidate_identity_inventory_is_fresh_and_ignores_rendered_active_index(
    tmp_path: Path,
) -> None:
    path = discovery(tmp_path, "identity", "discovery-identity")
    identity, fingerprint = sequence_candidate_contract.build_candidate_identity({
        "intended_outcome": "Run the exact operation.", "repeatability_reason": "It recurs.",
        "repeatability_evidence_ids": ["prior"], "required_inputs": ["repository"],
        "dependencies": [], "failure_handling": [{
            "fingerprint": "a" * 64, "symptom": "fails", "response": "stop",
        }], "verification_contract": {
            "quality": "same-path", "expected_outcome": "passed", "success_evidence": "PASS",
        }, "effect_class": "read-only", "environment_annotations": [],
        "semantic_flag_annotations": [], "volatility_annotations": [],
    }, [{
        "step_ordinal": 0, "step_id": "inspect", "argv": ["tool", "inspect"],
        "command_source": "discovery_log",
        "source_ref": {"repository_key": "memory-knowledge", "path": str(path.relative_to(tmp_path))},
        "operation_kind": "read-only",
    }])
    path.with_suffix(".dependencies.json").write_text(json.dumps({
        "schema_version": 1, "lineage_id": "discovery-identity", "dependencies": [],
        "candidate_identity": identity, "candidate_fingerprint": fingerprint,
        "observer_provenance": {
            "decision_id": "00000000-0000-4000-8000-000000000000",
            "observer_version": 1, "rule_version": 1,
        },
    }))
    (path.parent / "ACTIVE.md").write_text("# stale and intentionally ignored\n")

    rows = reconciliation.candidate_identity_inventory(tmp_path)

    assert [row["discovery_id"] for row in rows] == ["discovery-identity"]
    assert rows[0]["candidate_fingerprint"] == fingerprint

    start = {
        "event_type": "run_started", "event_id": "run-start",
        "run_id": "run", "subject_id": "discovery-identity",
        "lineage_id": "discovery-identity", "source_bundle_hash": "b" * 64,
        "repository_roots": {"memory-knowledge": str(tmp_path)},
        "recorded_at_utc": "2026-07-16T00:00:00Z",
    }
    decision = {
        "event_type": "observer_decision_recorded", "event_id": "decision-event",
        "decision_id": "00000000-0000-4000-8000-000000000000",
        "candidate_fingerprint": fingerprint,
        "recorded_at_utc": "2026-07-16T00:00:01Z",
    }
    with pytest.raises(reconciliation.ReconciliationError, match="candidate-repository-root-drift"):
        reconciliation.candidate_identity_inventory(
            tmp_path, events=[start, decision],
            repository_roots={"memory-knowledge": str(tmp_path / "moved")},
        )


def test_candidate_feedback_exposes_all_governed_outcome_kinds(tmp_path: Path) -> None:
    path = discovery(tmp_path, "feedback", "discovery-feedback")
    fingerprint = "f" * 64
    decision_id = "00000000-0000-4000-8000-000000000000"
    path.with_suffix(".dependencies.json").write_text(json.dumps({
        "schema_version": 1, "lineage_id": "discovery-feedback",
        "candidate_fingerprint": fingerprint,
        "observer_provenance": {"decision_id": decision_id},
    }))
    checkpoint = path.parent / "feedback.checkpoint.json"
    checkpoint.write_text(json.dumps({
        "completed": {
            str(path.relative_to(tmp_path)): {
                "disposition": "absorb", "completed_at_utc": "2026-07-16T00:04:00Z",
            },
        },
    }))
    events = [
        {
            "event_type": "discovery_promoted", "event_id": "promoted",
            "discovery_id": "discovery-feedback", "recorded_at_utc": "2026-07-16T00:01:00Z",
        },
        {
            "event_type": "correction_recorded", "event_id": "corrected",
            "lineage_id": "discovery-feedback", "recorded_at_utc": "2026-07-16T00:02:00Z",
        },
        {
            "event_type": "observer_candidate_linked", "event_id": "linked",
            "decision_id": decision_id, "candidate_fingerprint": fingerprint,
            "target_kind": "registered", "recorded_at_utc": "2026-07-16T00:03:00Z",
        },
    ]

    rows = reconciliation.candidate_lifecycle_feedback(
        tmp_path, fingerprint=fingerprint, events=events,
    )

    assert {row["outcome_kind"] for row in rows} == {
        "promotion", "correction", "registered-reuse", "dismissal",
    }


@pytest.mark.parametrize("verification_result", [False, reconciliation.work_memory.WorkMemoryError("missing-repository-root", 3)])
def test_audit_quarantines_promoted_candidate_without_resolvable_registered_verification(
    candidate_root: Path, monkeypatch: pytest.MonkeyPatch, verification_result: object,
) -> None:
    def registered_verified(sequence_id: str, repo_roots_file: str | None = None) -> bool:
        if isinstance(verification_result, Exception):
            raise verification_result
        return bool(verification_result)

    monkeypatch.setattr(
        reconciliation.discovery_promotion_lifecycle, "_registered_verified", registered_verified,
    )
    promoted = reconciliation.audit(candidate_root)["candidates"][1]
    assert promoted["suggested_disposition"] == "quarantine"
    assert promoted["registered_target_verified"] is False
    assert promoted["inspection_error"] in {
        "registered-target-not-verified",
        "registered-target-verification:missing-repository-root",
    }


def approved_manifest(candidate_root: Path, tmp_path: Path) -> Path:
    payload = reconciliation.audit(candidate_root)
    payload["approval"] = {
        "approved": True, "approved_by": "Kamen", "approved_at_utc": "2026-01-01T00:00:00Z",
    }
    first, second = payload["candidates"]
    first.update(
        disposition="remain-discovery", decision_reason="Needs another stable use case.",
    )
    second.update(
        disposition="already-promoted", decision_reason="Registered target preserves it.",
        target_sequence_id="registered-two",
    )
    path = tmp_path / "approved.json"
    path.write_text(json.dumps(payload))
    return path


def test_validate_rejects_unapproved_and_candidate_drift(candidate_root: Path, tmp_path: Path) -> None:
    payload = reconciliation.audit(candidate_root)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(reconciliation.ReconciliationError, match="manifest-not-approved"):
        reconciliation.validate_manifest(path, candidate_root)
    payload["approval"] = {
        "approved": True, "approved_by": "Kamen", "approved_at_utc": "2026-01-01T00:00:00Z",
    }
    for row in payload["candidates"]:
        row.update(disposition="remain-discovery", decision_reason="Not terminal.")
    path.write_text(json.dumps(payload))
    discovery(candidate_root, "three", "discovery-three")
    with pytest.raises(reconciliation.ReconciliationError, match="candidate-set-drift"):
        reconciliation.validate_manifest(path, candidate_root)


def test_validate_rejects_candidate_content_and_registry_drift(
    candidate_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = approved_manifest(candidate_root, tmp_path)
    candidate = candidate_root / "operations/sequences/discovery/one.md"
    candidate.write_text(candidate.read_text() + "\nnew evidence\n")
    with pytest.raises(reconciliation.ReconciliationError, match="candidate-content-drift"):
        reconciliation.validate_manifest(path, candidate_root)

    path = approved_manifest(candidate_root, tmp_path)
    monkeypatch.setattr(
        reconciliation.work_memory, "registry_rows",
        lambda registry=None, selected_sequence_id=None: (
            [{"sequence_id": "registered-two", "lineage_id": "discovery-two"}], "d" * 64
        ),
    )
    with pytest.raises(reconciliation.ReconciliationError, match="registry-drift"):
        reconciliation.validate_manifest(path, candidate_root)


def test_validate_rejects_registered_target_bundle_drift(
    candidate_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = approved_manifest(candidate_root, tmp_path)
    monkeypatch.setattr(
        reconciliation, "_registered_bundle_hash",
        lambda root, sequence_id: "e" * 64,
    )
    with pytest.raises(reconciliation.ReconciliationError, match="registered-target-bundle-drift"):
        reconciliation.validate_manifest(path, candidate_root)


def test_validate_requires_complete_promotion_metadata(candidate_root: Path, tmp_path: Path) -> None:
    path = approved_manifest(candidate_root, tmp_path)
    payload = json.loads(path.read_text())
    payload["candidates"][0].update(
        disposition="promote", decision_reason="Stable candidate.", promotion={"sequence_id": "x"},
    )
    path.write_text(json.dumps(payload))
    with pytest.raises(reconciliation.ReconciliationError, match="invalid-promotion-fields"):
        reconciliation.validate_manifest(path, candidate_root)


def test_execute_checkpoints_and_preserves_discovery_logs(
    candidate_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = approved_manifest(candidate_root, tmp_path)
    monkeypatch.setattr(
        reconciliation.discovery_promotion_lifecycle, "_registered_verified",
        lambda sequence_id, repo_roots_file=None: True,
    )
    index = candidate_root / "operations/sequences/discovery/ACTIVE.md"
    before = {item: item.read_bytes() for item in (candidate_root / "operations/sequences/discovery").glob("*.md")}
    args = SimpleNamespace(root=str(candidate_root), manifest=str(path), active_index=str(index))
    first = reconciliation.cmd_execute(args)
    second = reconciliation.cmd_execute(args)
    assert first["completed_count"] == second["completed_count"] == 2
    assert "one.md" in index.read_text()
    assert "two.md" not in index.read_text()
    assert {item: item.read_bytes() for item in before} == before


def test_execute_removes_quarantine_from_active_index_and_preserves_logs(
    candidate_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = approved_manifest(candidate_root, tmp_path)
    payload = json.loads(path.read_text())
    payload["candidates"][0].update(
        disposition="quarantine",
        decision_reason="Garbage candidate; preserve provenance outside the active queue.",
    )
    path.write_text(json.dumps(payload))
    monkeypatch.setattr(
        reconciliation.discovery_promotion_lifecycle, "_registered_verified",
        lambda sequence_id, repo_roots_file=None: True,
    )
    index = candidate_root / "operations/sequences/discovery/ACTIVE.md"
    discovery_logs = [
        candidate_root / "operations/sequences/discovery/one.md",
        candidate_root / "operations/sequences/discovery/two.md",
    ]
    before = {item: item.read_bytes() for item in discovery_logs}

    reconciliation.cmd_execute(
        SimpleNamespace(root=str(candidate_root), manifest=str(path), active_index=str(index)),
    )

    rendered = index.read_text()
    assert "one.md" not in rendered
    assert "two.md" not in rendered
    assert {item: item.read_bytes() for item in discovery_logs} == before


def test_execute_delegates_promote_once_and_resumes_checkpoint(
    candidate_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = reconciliation.audit(candidate_root)
    payload["approval"] = {
        "approved": True, "approved_by": "Kamen", "approved_at_utc": "2026-01-01T00:00:00Z",
    }
    first, second = payload["candidates"]
    first.update(
        disposition="promote", decision_reason="Two successful same-path runs.",
        promotion={
            "sequence_id": "promoted-one", "use_when": "When one recurs.",
            "operation_kinds": ["other"], "automation_display": "run one",
            "pass_signal": "one passes", "max_qualification_runs": 3,
        },
    )
    second.update(
        disposition="remain-discovery", decision_reason="Keep active for more evidence.",
    )
    path = tmp_path / "promote.json"
    path.write_text(json.dumps(payload))
    calls: list[str] = []
    monkeypatch.setattr(
        reconciliation, "_run_lifecycle",
        lambda row, root: calls.append(row["path"]) or {"ok": True, "stage": "complete"},
    )
    args = SimpleNamespace(
        root=str(candidate_root), manifest=str(path),
        active_index=str(candidate_root / "operations/sequences/discovery/ACTIVE.md"),
    )
    reconciliation.cmd_execute(args)
    reconciliation.cmd_execute(args)
    assert calls == ["operations/sequences/discovery/one.md"]


def rolling_row(
    path: str, suggested: str, *, promoted: str | None = None,
) -> dict[str, object]:
    return {
        "path": path,
        "suggested_disposition": suggested,
        "promoted_sequence_id": promoted,
        "inspection_error": None,
        "disposition": "pending",
        "decision_reason": None,
        "target_sequence_id": None,
    }


def rolling_payload(rows: list[dict[str, object]], *, marker: str = "one") -> dict[str, object]:
    paths = [str(row["path"]) for row in rows]
    return {
        "schema_version": reconciliation.SCHEMA_VERSION,
        "snapshot": {
            "head": "a" * 40,
            "candidate_paths": paths,
            "candidate_set_hash": marker,
            "candidate_hashes": {path: marker for path in paths},
            "registry_hash": "b" * 64,
        },
        "candidates": rows,
    }


def rolling_baseline(tmp_path: Path) -> Path:
    payload = rolling_payload([
        rolling_row("operations/sequences/discovery/active.md", "remain-discovery"),
        rolling_row(
            "operations/sequences/discovery/terminal.md",
            "already-promoted",
            promoted="registered-terminal",
        ),
    ])
    payload["approval"] = {
        "approved": True,
        "approved_by": "Kamen",
        "approved_at_utc": "2026-01-01T00:00:00Z",
        "policy": reconciliation.ROLLING_POLICY,
        "terminal_allowlist": ["registered-terminal"],
    }
    candidates = payload["candidates"]
    assert isinstance(candidates, list)
    candidates[0]["disposition"] = "remain-discovery"
    candidates[1]["disposition"] = "already-promoted"
    path = tmp_path / "rolling-baseline.json"
    path.write_text(json.dumps(payload))
    return path


def test_load_rolling_baseline_requires_approved_named_policy(tmp_path: Path) -> None:
    path = rolling_baseline(tmp_path)
    payload = json.loads(path.read_text())
    payload["approval"]["approved"] = False
    path.write_text(json.dumps(payload))
    with pytest.raises(reconciliation.ReconciliationError, match="rolling-baseline-not-approved"):
        reconciliation._load_rolling_baseline(path)

    payload["approval"]["approved"] = True
    payload["approval"]["policy"] = "some-other-policy"
    path.write_text(json.dumps(payload))
    with pytest.raises(reconciliation.ReconciliationError, match="invalid-rolling-policy"):
        reconciliation._load_rolling_baseline(path)


def test_rolling_policy_accepts_only_new_retain_candidates(tmp_path: Path) -> None:
    baseline = reconciliation._load_rolling_baseline(rolling_baseline(tmp_path))
    current = rolling_payload([
        rolling_row("operations/sequences/discovery/active.md", "remain-discovery"),
        rolling_row(
            "operations/sequences/discovery/terminal.md",
            "already-promoted",
            promoted="registered-terminal",
        ),
        rolling_row("operations/sequences/discovery/new.md", "remain-discovery"),
    ])
    applied = reconciliation._apply_rolling_policy(current, baseline)
    assert [row["disposition"] for row in applied["candidates"]] == [
        "remain-discovery", "already-promoted", "remain-discovery",
    ]

    current["candidates"][2]["suggested_disposition"] = "promotion-review"
    with pytest.raises(reconciliation.ReconciliationError, match="rolling-new-candidate-not-retain"):
        reconciliation._apply_rolling_policy(current, baseline)


def test_rolling_policy_stops_on_existing_decision_or_terminal_allowlist_change(
    tmp_path: Path,
) -> None:
    baseline = reconciliation._load_rolling_baseline(rolling_baseline(tmp_path))
    changed = rolling_payload([
        rolling_row("operations/sequences/discovery/active.md", "promotion-review"),
        rolling_row(
            "operations/sequences/discovery/terminal.md",
            "already-promoted",
            promoted="registered-terminal",
        ),
    ])
    with pytest.raises(reconciliation.ReconciliationError, match="rolling-existing-disposition-changed"):
        reconciliation._apply_rolling_policy(changed, baseline)

    wrong_terminal = rolling_payload([
        rolling_row("operations/sequences/discovery/active.md", "remain-discovery"),
        rolling_row(
            "operations/sequences/discovery/terminal.md",
            "already-promoted",
            promoted="different-terminal",
        ),
    ])
    with pytest.raises(reconciliation.ReconciliationError, match="rolling-terminal-allowlist-mismatch"):
        reconciliation._apply_rolling_policy(wrong_terminal, baseline)


def test_execute_rolling_retries_candidate_arrival_then_requires_stable_post_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = rolling_baseline(tmp_path)
    initial = rolling_payload([
        rolling_row("operations/sequences/discovery/active.md", "remain-discovery"),
        rolling_row(
            "operations/sequences/discovery/terminal.md",
            "already-promoted",
            promoted="registered-terminal",
        ),
    ], marker="initial")
    expanded = rolling_payload([
        rolling_row("operations/sequences/discovery/active.md", "remain-discovery"),
        rolling_row(
            "operations/sequences/discovery/terminal.md",
            "already-promoted",
            promoted="registered-terminal",
        ),
        rolling_row("operations/sequences/discovery/new.md", "remain-discovery"),
    ], marker="expanded")
    audits = iter([initial, expanded, expanded])
    monkeypatch.setattr(reconciliation, "audit", lambda root: next(audits))
    executions = iter([
        reconciliation.ReconciliationError("candidate-set-drift"),
        {
            "manifest_hash": "c" * 64,
            "active_index": str(tmp_path / "ACTIVE.md"),
            "checkpoint": str(tmp_path / "checkpoint.json"),
        },
    ])

    def execute(args: object) -> dict[str, str]:
        result = next(executions)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(reconciliation, "cmd_execute", execute)
    result = reconciliation.cmd_execute_rolling(SimpleNamespace(
        root=str(tmp_path), baseline=str(baseline), output_dir=str(tmp_path / "runs"),
        active_index=str(tmp_path / "ACTIVE.md"), max_attempts=3,
    ))
    assert result["attempt"] == 2
    assert result["candidate_count"] == 3
    assert result["terminal_count"] == 1


def test_execute_rolling_reuses_output_root_without_checkpoint_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = rolling_baseline(tmp_path)
    current = rolling_payload([
        rolling_row("operations/sequences/discovery/active.md", "remain-discovery"),
        rolling_row(
            "operations/sequences/discovery/terminal.md",
            "already-promoted",
            promoted="registered-terminal",
        ),
    ])
    monkeypatch.setattr(reconciliation, "audit", lambda root: deepcopy(current))

    def execute(args: object) -> dict[str, str]:
        manifest = Path(args.manifest)
        return {
            "manifest_hash": "c" * 64,
            "active_index": str(tmp_path / "ACTIVE.md"),
            "checkpoint": str(manifest.with_suffix(".json.checkpoint.json")),
        }

    monkeypatch.setattr(reconciliation, "cmd_execute", execute)
    args = SimpleNamespace(
        root=str(tmp_path), baseline=str(baseline), output_dir=str(tmp_path / "runs"),
        active_index=str(tmp_path / "ACTIVE.md"), max_attempts=1,
    )
    first = reconciliation.cmd_execute_rolling(args)
    second = reconciliation.cmd_execute_rolling(args)
    assert first["invocation_dir"] != second["invocation_dir"]
    assert Path(first["manifest"]).parent.parent == tmp_path / "runs"
    assert Path(second["manifest"]).parent.parent == tmp_path / "runs"


def test_drive_verifies_pending_correction_then_runs_and_closes_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = tmp_path / "operations/sequences/discovery-candidate-reconciliation/sequence.md"
    document.parent.mkdir(parents=True)
    document.write_text("# sequence\n")
    pending = reconciliation.discovery_promotion_lifecycle.PendingCorrection(
        blocker_id="blk-one", correction_id="correction-one",
        predecessor_run_id="run-one", task_id="reconcile-once-verify",
    )
    monkeypatch.setattr(
        reconciliation.discovery_promotion_lifecycle, "_pending_correction", lambda subject: pending,
    )
    monkeypatch.setattr(
        reconciliation.discovery_promotion_lifecycle, "_open_blocker_ids", lambda subject: [],
    )
    monkeypatch.setattr(
        reconciliation.discovery_promotion_lifecycle, "_registered_verified",
        lambda sequence_id, repo_roots_file=None: True,
    )
    classified: list[str] = []
    monkeypatch.setattr(
        reconciliation.discovery_promotion_lifecycle, "_classify",
        lambda task_id, root, operation_kind: classified.append(task_id),
    )
    starts: list[tuple[str, object]] = []

    def start(**kwargs: object) -> tuple[str, dict[str, object]]:
        starts.append((str(kwargs["task_id"]), kwargs["pending"]))
        return f"run-{len(starts)}", {"receipt": True}

    monkeypatch.setattr(reconciliation.discovery_promotion_lifecycle, "_select_and_start", start)
    monkeypatch.setattr(
        reconciliation.discovery_promotion_lifecycle, "_verification_command",
        lambda path: "scripts/run_pytest.sh focused -q",
    )
    monkeypatch.setattr(
        reconciliation.discovery_promotion_lifecycle, "_verify_run",
        lambda **kwargs: {"run_id": kwargs["run_id"], "verification_event_id": "verify-bundle"},
    )
    commands: list[list[str]] = []

    def json_command(command: list[str], *, root: Path) -> dict[str, object]:
        commands.append(command)
        if "execute-rolling" in command and command[1] == "scripts/discovery_candidate_reconciliation.py":
            return {
                "ok": True, "manifest_hash": "a" * 64, "candidate_count": 49,
                "terminal_count": 2, "manifest": "/tmp/manifest.json",
            }
        if "verify" in command:
            return {"ok": True, "event_id": "verify-live"}
        return {"ok": True}

    monkeypatch.setattr(
        reconciliation.discovery_promotion_lifecycle, "_json_command", json_command,
    )
    result = reconciliation.cmd_drive(SimpleNamespace(
        root=str(tmp_path), task_id="reconcile-once", output_root=str(tmp_path / "runs"),
    ))
    assert classified == ["reconcile-once-verify", "reconcile-once-live"]
    assert starts == [("reconcile-once-verify", pending), ("reconcile-once-live", None)]
    assert result["bundle_verification"]["verification_event_id"] == "verify-bundle"
    assert result["live_run"]["run_id"] == "run-2"
    assert result["live_run"]["active_count"] == 47
    assert any(command[1:3] == ["scripts/sequence_guard.py", "guard"] for command in commands)
    assert commands[-1][-2:] == ["--result", "passed"]


def test_drive_catalogs_live_failure_and_does_not_close_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = tmp_path / "operations/sequences/discovery-candidate-reconciliation/sequence.md"
    document.parent.mkdir(parents=True)
    document.write_text("# sequence\n")
    monkeypatch.setattr(
        reconciliation.discovery_promotion_lifecycle, "_pending_correction", lambda subject: None,
    )
    monkeypatch.setattr(
        reconciliation.discovery_promotion_lifecycle, "_open_blocker_ids", lambda subject: [],
    )
    monkeypatch.setattr(
        reconciliation.discovery_promotion_lifecycle, "_registered_verified",
        lambda sequence_id, repo_roots_file=None: True,
    )
    monkeypatch.setattr(
        reconciliation.discovery_promotion_lifecycle, "_classify", lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        reconciliation.discovery_promotion_lifecycle, "_select_and_start",
        lambda **kwargs: ("live-run", {}),
    )
    commands: list[list[str]] = []

    def json_command(command: list[str], *, root: Path) -> dict[str, object]:
        commands.append(command)
        if "execute-rolling" in command and command[1] == "scripts/discovery_candidate_reconciliation.py":
            raise reconciliation.discovery_promotion_lifecycle.LifecycleError("rolling-broke")
        if command[1:4] == ["scripts/blocker_catalog.py", "open", "--run-id"]:
            return {"ok": True, "blocker_id": "blk-live"}
        return {"ok": True}

    monkeypatch.setattr(
        reconciliation.discovery_promotion_lifecycle, "_json_command", json_command,
    )
    with pytest.raises(
        reconciliation.ReconciliationError,
        match="rolling-execution-failed-blocker-cataloged:blk-live",
    ):
        reconciliation.cmd_drive(SimpleNamespace(
            root=str(tmp_path), task_id="reconcile-fail", output_root=str(tmp_path / "runs"),
        ))
    assert any(command[1:3] == ["scripts/blocker_catalog.py", "open"] for command in commands)
    assert not any("run-close" in command for command in commands)


def test_drive_stops_on_open_blocker_before_starting_a_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = tmp_path / "operations/sequences/discovery-candidate-reconciliation/sequence.md"
    document.parent.mkdir(parents=True)
    document.write_text("# sequence\n")
    monkeypatch.setattr(
        reconciliation.discovery_promotion_lifecycle, "_pending_correction", lambda subject: None,
    )
    monkeypatch.setattr(
        reconciliation.discovery_promotion_lifecycle, "_open_blocker_ids",
        lambda subject: ["blk-unresolved"],
    )
    started: list[str] = []
    monkeypatch.setattr(
        reconciliation.discovery_promotion_lifecycle, "_select_and_start",
        lambda **kwargs: started.append(str(kwargs["task_id"])),
    )
    with pytest.raises(
        reconciliation.ReconciliationError,
        match="correction-required:blk-unresolved",
    ):
        reconciliation.cmd_drive(SimpleNamespace(
            root=str(tmp_path), task_id="reconcile-blocked", output_root=str(tmp_path / "runs"),
        ))
    assert started == []
