from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "working-agreement" / "codex_office_bootstrap.py"


def _run_install(tmp_path: Path, codex_root: Path) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    report = tmp_path / "report" / "parity.json"
    backups = tmp_path / "backups"
    completed = subprocess.run(
        [
            sys.executable,
            str(BOOTSTRAP),
            "install",
            "--repo",
            str(ROOT),
            "--codex-root",
            str(codex_root),
            "--state-dir",
            str(tmp_path / "state"),
            "--backup-root",
            str(backups),
            "--report",
            str(report),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return completed, report, backups


def test_empty_root_installs_every_managed_skill_and_passes_exact_parity(tmp_path: Path) -> None:
    codex_root = tmp_path / "codex-skills"

    completed, report, _ = _run_install(tmp_path, codex_root)

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["managed_skill_count"] == 21
    assert result["before_parity"] is False
    assert result["after_parity"] is True
    assert result["backup"] is None
    assert json.loads(report.read_text())["parity"] is True


def test_stale_managed_skill_is_backed_up_while_unrelated_skills_are_preserved(tmp_path: Path) -> None:
    codex_root = tmp_path / "codex-skills"
    stale = codex_root / "working-agreement"
    stale.mkdir(parents=True)
    old_bytes = b"older office working agreement\n"
    (stale / "SKILL.md").write_bytes(old_bytes)
    system = codex_root / ".system"
    system.mkdir()
    (system / "sentinel.txt").write_text("system skill stays\n", encoding="utf-8")
    personal = codex_root / "office-local"
    personal.mkdir()
    (personal / "SKILL.md").write_text("office-only skill stays\n", encoding="utf-8")

    completed, report, backups = _run_install(tmp_path, codex_root)

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["before_parity"] is False
    assert result["after_parity"] is True
    assert result["unmanaged_preserved"] is True
    assert (system / "sentinel.txt").read_text() == "system skill stays\n"
    assert (personal / "SKILL.md").read_text() == "office-only skill stays\n"
    archives = list(backups.glob("*.tar.gz"))
    assert len(archives) == 1
    with tarfile.open(archives[0], "r:gz") as archive:
        restored = archive.extractfile("working-agreement/SKILL.md")
        assert restored is not None
        assert restored.read() == old_bytes
    assert json.loads(report.read_text())["parity"] is True


def test_corrupt_canonical_source_refuses_before_destination_mutation(tmp_path: Path) -> None:
    corrupt_repo = tmp_path / "corrupt-repo"
    shutil.copytree(ROOT / "skills", corrupt_repo / "skills")
    (corrupt_repo / "working-agreement").mkdir()
    shutil.copy2(
        ROOT / "working-agreement" / "validate_skills.py",
        corrupt_repo / "working-agreement" / "validate_skills.py",
    )
    (corrupt_repo / "skills" / "working-agreement" / "SKILL.md").unlink()
    codex_root = tmp_path / "codex-skills"
    sentinel = codex_root / ".system" / "sentinel.txt"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text("unchanged\n", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(BOOTSTRAP),
            "install",
            "--repo",
            str(corrupt_repo),
            "--codex-root",
            str(codex_root),
            "--state-dir",
            str(tmp_path / "state"),
            "--backup-root",
            str(tmp_path / "backups"),
            "--report",
            str(tmp_path / "parity.json"),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "validation refused before mutation" in completed.stderr
    assert sentinel.read_text() == "unchanged\n"
    assert not (tmp_path / "backups").exists()


def test_mcp_spec_is_checkout_relative_and_matches_the_live_service_contract(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(BOOTSTRAP),
            "mcp-spec",
            "--repo",
            str(ROOT),
            "--node-bin",
            str(tmp_path / "node-bin"),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    spec = json.loads(completed.stdout)
    assert spec["name"] == "memory-knowledge"
    assert spec["command"] == str((ROOT / "scripts" / "mcp-remote-wrapper.sh").resolve())
    assert spec["args"] == [
        "-y",
        "mcp-remote",
        "https://memory-knowledge.azurewebsites.net/mcp/",
    ]
    assert spec["env"]["PATH"].startswith(str((tmp_path / "node-bin").resolve()))


def test_office_runbook_preserves_config_and_refreshes_repository_projections() -> None:
    runbook = (ROOT / "working-agreement" / "SETUP-codex.md").read_text(encoding="utf-8")

    assert 'mkdir -p "$MK_BACKUPS"' in runbook
    assert "config.toml.before-memory-knowledge-replacement" in runbook
    assert "codex mcp get memory-knowledge --json" in runbook
    assert "--refresh-trusted --create-missing --apply" in runbook
    assert "Do not enable this repository's tracked" in runbook
