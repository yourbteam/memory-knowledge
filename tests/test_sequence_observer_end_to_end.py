from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import discovery_bootstrap, discovery_promotion_lifecycle
from scripts import sequence_candidate_contract, sequence_checked_exec, sequence_guard, work_memory
from scripts.directive_guard import write_directive_read_state

def _registry() -> str:
    return """# Repeatable Operational Sequences

## Available Sequences

| sequence id | use when | sequence folder | automation | pass signal | operation kinds | lineage id |
| --- | --- | --- | --- | --- | --- | --- |
| `seed-sequence` | Seed only for producing actual observed runs. | `operations/sequences/seed-sequence/` | `python3 scripts/not-the-observed-tool.py` | PASS | `workflow-drive` | `seed-lineage` |

## Missing Sequence Discovery

Create a discovery when no registered sequence matches.
"""


def _patch_copied_directive_defaults(root: Path, state: Path) -> None:
    path = root / "scripts/directive_guard.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        'Path("/Users/kamenkamenov/memory-knowledge/working-agreement/DIRECTIVES.md")',
        f"Path({str(root / 'working-agreement/DIRECTIVES.md')!r})",
    ).replace(
        'Path("/private/tmp/workflow-orch-directive-guard.json")',
        f"Path({str(state)!r})",
    )
    path.write_text(text, encoding="utf-8")


def _run_observed_operation(root: Path, task_id: str, seed: Path) -> dict[str, object]:
    work_memory.cmd_classify(SimpleNamespace(
        task_id=task_id, operation_kind="workflow-drive",
        repeatable="yes", meaningful_steps=3,
    ))
    work_memory.cmd_select(SimpleNamespace(
        task_id=task_id, sequence_id="seed-sequence", discovery_log=None,
        fingerprint=None, verification_successor_of=None, verifies_correction_id=None,
        repo_roots_file=None, repository_roots={"memory-knowledge": str(root)},
    ))
    sequence_guard.cmd_activate(SimpleNamespace(
        task_id=task_id, root=str(root), state=None, sequence_doc=str(seed),
        discovery_log=None, sequence_id=None, directives_path=None,
        directive_state=None, directive_max_age_minutes=60,
    ))
    started = work_memory.cmd_run_start(SimpleNamespace(
        task_id=task_id, run_id=None, event_id=None,
    ))
    context_path = root / f"{task_id}-context.json"
    success_evidence = "PASS"
    context_path.write_text(json.dumps({
        "intended_outcome": "Repeat the governed workflow safely.",
        "repeatability_reason": "The workflow recurs across tasks.",
        "repeatability_evidence_ids": ["prior-task-one"],
        "required_inputs": ["checked-out repository"],
        "dependencies": [{
            "repository_key": "memory-knowledge", "path": "scripts/tool.py",
        }],
        "failure_handling": [{
            "fingerprint": "d" * 64, "symptom": "tool exits nonzero", "response": "stop",
        }],
        "verification_contract": {
            "quality": "same-path", "expected_outcome": "passed",
            "success_evidence": success_evidence,
        },
        "effect_class": "idempotent-local", "environment_annotations": [],
        "semantic_flag_annotations": [], "volatility_annotations": [],
    }), encoding="utf-8")
    context = work_memory.cmd_record_operation_context(SimpleNamespace(
        run_id=started["run_id"], context_file=str(context_path),
    ))
    for ordinal, step_id in enumerate(("prepare", "execute", "verify-automation")):
        exit_code = sequence_checked_exec.run(SimpleNamespace(
            task_id=task_id, run_id=started["run_id"], context_id=context["context_id"],
            step_ordinal=ordinal, step_id=step_id, source="script",
            source_ref="scripts/tool.py", source_ref_repository="memory-knowledge",
            evidence_text=None, state=None,
            command=["python3", "scripts/tool.py"],
        ))
        assert exit_code == 0
    work_memory.cmd_verify(SimpleNamespace(
        run_id=started["run_id"], outcome="passed", quality="same-path",
        evidence=success_evidence, blocker_id=[], correction_id=[], event_id=None,
    ))
    return work_memory.cmd_run_close(SimpleNamespace(
        run_id=started["run_id"], result="passed", event_id=None, observer="enabled",
    ))


def test_observed_candidate_traverses_real_lifecycle_then_reuses_registered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = Path(__file__).parents[1]
    root = tmp_path / "memory-knowledge"
    shutil.copytree(source_root / "scripts", root / "scripts")
    (root / "working-agreement").mkdir(parents=True)
    (root / "working-agreement/DIRECTIVES.md").write_text("# Directives\n", encoding="utf-8")
    (root / "operations/sequences").mkdir(parents=True)
    (root / "operations/sequences/SEQUENCES.md").write_text(_registry(), encoding="utf-8")
    (root / "scripts/tool.py").write_text(
        "#!/usr/bin/env python3\nprint('PASS')\n", encoding="utf-8",
    )
    seed = root / "operations/sequences/seed-sequence/sequence.md"
    seed.parent.mkdir(parents=True)
    seed.write_text("# seed sequence\n", encoding="utf-8")
    seed.with_name("dependencies.json").write_text(json.dumps({
        "schema_version": 1, "lineage_id": "seed-lineage",
        "dependencies": [{
            "kind": "file", "repository_key": "memory-knowledge",
            "path_or_sequence_id": "scripts/tool.py",
        }],
    }), encoding="utf-8")
    directive_state = tmp_path / "directive-state.json"
    write_directive_read_state(
        directives_path=root / "working-agreement/DIRECTIVES.md",
        state_path=directive_state, mode="test",
    )
    _patch_copied_directive_defaults(root, directive_state)
    monkeypatch.setenv("MK_DIRECTIVE_STATE_PATH", str(directive_state))
    monkeypatch.setenv(
        "WORK_MEMORY_REGISTRY_GOVERNANCE_LEVEL", "UNGOVERNED_DIAGNOSTIC"
    )
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(work_memory, "RECEIPT_ROOT", tmp_path / "receipts")
    monkeypatch.setattr(discovery_bootstrap, "LOCK_PATH", tmp_path / "bootstrap.lock")
    monkeypatch.setattr(sequence_guard, "DEFAULT_DIRECTIVES_PATH", root / "working-agreement/DIRECTIVES.md")
    monkeypatch.setattr(sequence_guard, "DEFAULT_DIRECTIVE_STATE_PATH", directive_state)

    original = (work_memory.ROOT, work_memory.LEDGER, work_memory.BLOCKER_VIEW, work_memory.REGISTRY)
    try:
        work_memory.configure_root(
            root, registry_governance_level="UNGOVERNED_DIAGNOSTIC"
        )
        first_close = _run_observed_operation(root, "observed-first", seed)
        proposed = first_close["observer"]
        assert "disposition" in proposed, proposed
        assert proposed["disposition"] == "PROPOSE_DISCOVERY"
        discovery = next(
            (root / "operations/sequences/discovery").glob("*observed-*.md")
        )
        sequence_id = "observed-registered"
        args = discovery_promotion_lifecycle.build_parser().parse_args([
            "drive", "--file", str(discovery), "--sequence-id", sequence_id,
            "--use-when", "Repeat the exact observed governed workflow.",
            "--operation-kind", "workflow-drive",
            "--automation-display", "python3 scripts/tool.py",
            "--pass-signal", "PASS", "--root", str(root),
        ])
        registered_folder = root / "operations/sequences" / sequence_id
        assert registered_folder.exists() is False

        lifecycle = discovery_promotion_lifecycle.cmd_drive(args)

        assert lifecycle["stage"] == "complete"
        assert len(lifecycle["qualification_runs"]) == 2
        qualification_run_ids = {
            row["run_id"] for row in lifecycle["qualification_runs"]
        }
        events, _ = work_memory.load_ledger()
        qualification_starts = [
            event for event in events
            if event["event_type"] == "run_started"
            and event["run_id"] in qualification_run_ids
        ]
        assert len(qualification_starts) == 2
        assert {event["lineage_id"] for event in qualification_starts} == {proposed["target_id"]}
        assert len({event["source_bundle_hash"] for event in qualification_starts}) == 1
        promotions = [
            event for event in events if event["event_type"] == "discovery_promoted"
        ]
        assert len(promotions) == 1
        promotion = promotions[0]
        assert any(
            event["event_type"] == "bundle_transition_recorded"
            and event.get("transition_reason") == "promotion"
            and event.get("discovery_id") == promotion["discovery_id"]
            and event.get("promoted_sequence_id") == sequence_id
            for event in events
        )
        assert registered_folder.joinpath("sequence.md").is_file()
        assert registered_folder.joinpath("dependencies.json").is_file()
        assert any(row["sequence_id"] == sequence_id for row in work_memory.registry_rows()[0])
        registered_runs = [
            event for event in events
            if event["event_type"] == "run_started"
            and event["subject_id"] == sequence_id and event["mode"] == "registered"
        ]
        assert len(registered_runs) == 1
        registered_run = registered_runs[0]
        assert events.index(registered_run) > events.index(promotion)
        _, registered_hash, registered_lineage = work_memory.resolve_bundle(
            mode="registered", subject_id=sequence_id,
            document=registered_folder / "sequence.md",
            manifest=registered_folder / "dependencies.json",
            include_bootstrap_trust_anchors=True,
        )
        assert sequence_candidate_contract.final_effective_verification(
            events, run_id=registered_run["run_id"], lineage_id=registered_lineage,
            source_bundle_hash=registered_hash,
        ) is not None
        assert any(
            event["event_type"] == "run_closed"
            and event["run_id"] == registered_run["run_id"] and event["result"] == "passed"
            for event in events
        )
        assert discovery_promotion_lifecycle._registered_verified(
            sequence_id, repo_roots_file=None,
        ) is True
        discovery_manifest = json.loads(discovery.with_suffix(".dependencies.json").read_text())
        registered_manifest = json.loads(
            registered_folder.joinpath("dependencies.json").read_text()
        )
        for field in ("candidate_identity", "candidate_fingerprint", "observer_provenance"):
            assert registered_manifest[field] == discovery_manifest[field]

        second_close = _run_observed_operation(root, "observed-second", seed)
        linked = second_close["observer"]
    finally:
        work_memory.ROOT, work_memory.LEDGER, work_memory.BLOCKER_VIEW, work_memory.REGISTRY = original
        work_memory.REGISTRY_GOVERNANCE_LEVEL = "FULLY_GOVERNED"

    assert linked["disposition"] == "LINK_REGISTERED"
    assert linked["target_id"] == sequence_id
    assert len(list((root / "operations/sequences/discovery").glob("*observed-*.md"))) == 1
