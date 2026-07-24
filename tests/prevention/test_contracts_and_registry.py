from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import prevention_contract, prevention_registry, work_memory


def test_repository_registry_is_typed_and_complete():
    rows, registry_hash = prevention_registry.load_typed_registry()

    assert len(rows) == 25
    assert len({row["sequence_id"] for row in rows}) == 25
    assert len(registry_hash) == 64
    assert all(row["handler"].startswith("prevention_adapters:") for row in rows)
    assert all(row["parameter_contract"].endswith(".parameters.v1") for row in rows)
    assert all(row["effect_reconciler"].startswith("prevention_adapters:reconcile_") for row in rows)
    assert all(isinstance(row["standalone"], bool) for row in rows)
    blocker = next(row for row in rows if row["sequence_id"] == "mawf-playbook-blocker-reentry")
    assert blocker["standalone"] is False
    assert blocker["parent_sequence_ids"] == ["mawf-playbook-full-test", "mawf-playbook-speed-test"]
    promoted = next(row for row in rows if row["sequence_id"] == "discovery-promotion-lifecycle")
    assert promoted["lineage_id"] == "discovery-b6658d35-7870-5d15-9f4b-d316138cec83"


def test_discovery_lifecycle_bundle_contains_directive_guard_intake_dependency():
    manifest = json.loads(Path(
        "operations/sequences/discovery-promotion-lifecycle/dependencies.json"
    ).read_text(encoding="utf-8"))
    dependency_paths = {
        row["path_or_sequence_id"] for row in manifest["dependencies"]
    }

    assert "scripts/directive_guard.py" in dependency_paths
    assert "scripts/script_intake.py" in dependency_paths


def test_work_memory_uses_typed_registry_by_default():
    rows, registry_hash = work_memory.registry_rows()
    typed_rows, _ = prevention_registry.load_typed_registry()

    runtime_ids = {row["sequence_id"] for row in rows}
    typed_ids = {row["sequence_id"] for row in typed_rows}
    assert len(runtime_ids) == len(rows)
    assert typed_ids <= runtime_ids
    assert len(registry_hash) == 64
    assert all("handler" in row for row in rows if row["sequence_id"] in typed_ids)


def test_runtime_registry_retains_promoted_non_owner_without_relabeling_owner():
    typed = [{"sequence_id": "typed-owner", "handler": "owner-handler"}]
    projection = [
        {"sequence_id": "typed-owner", "use_when": "owner"},
        {"sequence_id": "promoted-sequence", "use_when": "promoted"},
    ]

    rows, registry_hash = prevention_registry._merge_runtime_projection(
        typed, projection, "a" * 64,
    )

    assert rows == [typed[0], projection[1]]
    assert rows[0]["handler"] == "owner-handler"
    assert "handler" not in rows[1]
    assert len(registry_hash) == 64


def test_explicit_markdown_fixture_remains_supported(tmp_path: Path):
    registry = tmp_path / "SEQUENCES.md"
    registry.write_text(
        "| Sequence | Use when | Folder | Automation | Pass signal | Operation kinds | Lineage |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
        "| `fixture` | fixture use | `operations/sequences/fixture/` | fixture.py | OK | `other` | `fixture` |\n",
        encoding="utf-8",
    )

    rows, registry_hash = prevention_registry.legacy_fixture_rows(
        registry, governance_level="UNGOVERNED_DIAGNOSTIC"
    )

    assert rows == [{
        "sequence_id": "fixture",
        "use_when": "fixture use",
        "folder": "operations/sequences/fixture/",
        "automation": "fixture.py",
        "pass_signal": "OK",
        "operation_kinds": "other",
        "lineage_id": "fixture",
    }]
    assert len(registry_hash) == 64


def test_manifest_rejects_unknown_keys(tmp_path: Path):
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"rows": [{"sequence_id": f"s-{i}"} for i in range(25)]}), encoding="utf-8")
    raw = json.loads(prevention_registry.MIGRATION_MANIFEST.read_text(encoding="utf-8"))
    raw["source_inventory"] = "source.json"
    raw["source_inventory_sha256"] = prevention_contract.sha256_bytes(source.read_bytes())
    raw["rows"][0]["unexpected"] = True
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(prevention_contract.ContractError, match="owner-row-keys"):
        prevention_contract.OwnerRegistry.load(manifest, repository_root=tmp_path)


def test_manifest_rejects_source_hash_drift(tmp_path: Path):
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"rows": []}), encoding="utf-8")
    raw = json.loads(prevention_registry.MIGRATION_MANIFEST.read_text(encoding="utf-8"))
    raw["source_inventory"] = "source.json"
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(prevention_contract.ContractError, match="source-inventory-hash-mismatch"):
        prevention_contract.OwnerRegistry.load(manifest, repository_root=tmp_path)


@pytest.mark.parametrize("tokens", [["bash", "-lc", "echo ok"], ["safe", "a|b"], ["safe", "$HOME"]])
def test_fixed_argv_rejects_shell_interpretation(tokens: list[str]):
    with pytest.raises(prevention_contract.ContractError, match="unsafe-fixed-argv-token"):
        prevention_contract.validate_fixed_argv(tokens)
