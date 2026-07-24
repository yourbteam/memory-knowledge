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
    "skills/playbook-convergence-loop/SKILL.md",
    "skills/plan-playbook/integration/playbook-convergence-loop.SKILL.md",
    "skills/reproduce-first-verify/SKILL.md",
    "skills/research-playbook/scripts/research_run.py",
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


def test_sequence_runner_instructs_zero_argument_intake():
    text = (SKILLS / "sequence-runner" / "SKILL.md").read_text()
    assert "sequence_intake_launch.py" in text
    assert "no arguments" in text


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
