"""Deterministic Claude-parity invariants over the canonical repository.

These checks pin the parity architecture: one canonical authority, complete
dispositions, PDI routing, zero-input intake wording, no stray host leaks,
and no competing legacy Claude command surface.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
PROJECTIONS = ROOT / "working-agreement" / "client-skill-projections.json"

# Intentionally Codex-targeted surfaces (domain behavior, not host leaks) and the
# shared modules whose job is to know both hosts.
ALLOWED_CODEX_REFERENCES = {
    "skills/_shared/host_agent_runtime.py",
    "skills/shell-canary-foundry/SKILL.md",
    "skills/shell-canary-runner/SKILL.md",
    "skills/reproduce-first-verify/SKILL.md",
}


def manifest_names() -> list[str]:
    return [
        line.strip()
        for line in (SKILLS / "managed-skills.txt").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]


def test_every_managed_skill_has_a_parity_disposition_and_scenario_group():
    data = json.loads(PROJECTIONS.read_text())
    names = manifest_names()
    assert sorted(data["entries"]) == sorted(names)
    for name, row in data["entries"].items():
        assert row["disposition"] in {
            "SHARED_IDENTICAL", "GENERATED_CLIENT_PROJECTION",
            "CLIENT_NOT_APPLICABLE", "BLOCKED",
        }, name
        assert row["scenario_groups"], name
        assert set(row["targets"]) <= {"codex", "claude"} and row["targets"], name


def test_projection_manifest_is_current_for_both_clients():
    for client in ("codex", "claude"):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "working-agreement" / "project_client_skills.py"),
             "check", "--client", client],
            capture_output=True, text=True,
        )
        errors = [line for line in completed.stdout.splitlines() if line.startswith("ERROR")]
        assert errors == [], f"{client}: {errors}"


def test_working_agreement_routes_write_code_to_pdi():
    text = (SKILLS / "working-agreement" / "SKILL.md").read_text()
    assert "prototype-driven-implementation" in text
    assert re.search(r"Write code:.*prototype-driven-implementation", text)


def test_sequence_runner_dispatches_by_persisted_selection_mode():
    text = (SKILLS / "sequence-runner" / "SKILL.md").read_text()
    workflow = text.split("## Workflow", 1)[1].split("## Selection Rules", 1)[0]
    assert "Dispatch from the verified mode in the persisted selection receipt" in workflow
    assert "`registered`: launch `python3 scripts/sequence_intake_launch.py` with no arguments" in workflow
    assert "`discovery`: do not invoke the registered-only intake launcher" in workflow
    assert "Guard and run the exact\n     command already recorded in the selected discovery log" in workflow


def test_self_contained_machinery_is_managed_and_bypasses_sequence_discovery():
    names = manifest_names()
    for name in ("description-machinery", "requirements-machinery"):
        assert name in names

    routing_docs = {
        name: " ".join((SKILLS / name / "SKILL.md").read_text().split())
        for name in ("working-agreement", "task-intake", "sequence-runner")
    }
    assert "self-contained local controller skill is also fast-path machinery" in routing_docs["working-agreement"]
    assert "do not put `task-intake`, `sequence-runner`, registry selection, or sequence discovery around it" in routing_docs["working-agreement"]
    assert "It does not mean a self-contained local controller skill's own bounded worker loop" in routing_docs["task-intake"]
    assert "Do not classify or sequence-wrap them" in routing_docs["task-intake"]
    assert "Do not wrap a self-contained local controller skill" in routing_docs["sequence-runner"]
    assert "does not require sequence selection or discovery" in routing_docs["sequence-runner"]

    requirements = (SKILLS / "requirements-machinery" / "SKILL.md").read_text()
    assert "## The front door" in requirements
    assert "nothing comes out while any part of the source is" in requirements

    description = (SKILLS / "description-machinery" / "SKILL.md").read_text()
    assert "complete local controller" in description
    assert "do not\nput `task-intake`, `sequence-runner`, registry selection, or sequence discovery around it" in description


def test_all_machinery_projects_fail_closed_to_the_invoking_client_model():
    machinery = {"description-machinery", "requirements-machinery"}
    rows = json.loads(PROJECTIONS.read_text())["entries"]
    assert all(rows[name]["disposition"] == "GENERATED_CLIENT_PROJECTION" for name in machinery)
    for client, required, forbidden in (
        ("codex", "codex exec", "claude"),
        ("claude", "claude -p", "codex exec"),
    ):
        with tempfile.TemporaryDirectory() as raw:
            staged = Path(raw)
            completed = subprocess.run(
                [sys.executable, str(ROOT / "working-agreement" / "project_client_skills.py"),
                 "build", "--client", client, "--staging-root", str(staged)],
                capture_output=True, text=True,
            )
            assert completed.returncode == 0, completed.stderr
            for name in machinery:
                policy = json.loads((staged / name / "client-model-policy.json").read_text())
                expected = {
                    "schema_version": 1,
                    "client": client,
                    "required_runtime": required,
                    "forbidden_runtime": forbidden,
                    "fail_closed": True,
                }
                if name == "requirements-machinery":
                    expected["recommended_reader_command"] = required
                assert policy == expected


def test_pdi_skill_is_managed_and_discoverable_from_skill_md():
    assert "prototype-driven-implementation" in manifest_names()
    doc = SKILLS / "prototype-driven-implementation" / "SKILL.md"
    head = doc.read_text().splitlines()
    assert head[0] == "---"
    assert any(line.startswith("name: prototype-driven-implementation") for line in head[:4])


def test_no_unapproved_codex_host_leaks_in_managed_skills():
    pattern = re.compile(r"\.codex/skills|CODEX_THREAD_ID|codex exec")
    offenders = []
    for path in SKILLS.rglob("*"):
        if not path.is_file() or path.suffix not in {".md", ".py", ".sh", ".json"}:
            continue
        relative = path.relative_to(ROOT).as_posix()
        if relative in ALLOWED_CODEX_REFERENCES:
            continue
        if pattern.search(path.read_text(errors="ignore")):
            offenders.append(relative)
    assert offenders == [], offenders


def test_legacy_claude_command_surface_is_retired():
    commands = ROOT / ".claude" / "commands"
    if commands.exists():
        assert sorted(p.name for p in commands.iterdir()) == []


def test_sequence_intake_contracts_are_present_and_current():
    contracts = ROOT / "operations/sequences/sequence-intake-contracts.json"
    assert contracts.is_file()
    sys.path.insert(0, str(ROOT))
    from scripts import sequence_intake_adapters
    assert sequence_intake_adapters.check_intake_contracts(ROOT) == []


def test_host_agent_runtime_is_shared_and_covers_both_hosts():
    text = (SKILLS / "_shared" / "host_agent_runtime.py").read_text()
    for token in ("probe_host", "run_assessment", '"codex"', '"claude"',
                  "CAPABILITY_MISSING", "LEDGER_ERROR"):
        assert token in text, token
