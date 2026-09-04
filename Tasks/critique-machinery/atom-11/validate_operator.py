#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
ATOM = ROOT / "Tasks/critique-machinery/atom-11"
FROZEN = ATOM / "frozen-red"
PROJECTIONS = ROOT / "working-agreement/client-skill-projections.json"
INSTALLS = {
    "codex": Path("/Users/kamenkamenov/.codex/skills/critique-machinery"),
    "claude": Path("/Users/kamenkamenov/.claude/skills/critique-machinery"),
}
TARGET_CELL = "u-018-55cd0f78::upstream-trace"
OWNER_WORDS = "Kamen: approved in bulk 2026-09-04"


def load(name: str, script: Path):
    spec = importlib.util.spec_from_file_location(name, script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hash(path: Path) -> str:
    value = hashlib.sha256()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        value.update(item.relative_to(path).as_posix().encode() + b"\0")
        value.update(item.read_bytes())
    return value.hexdigest()


def writable_copy(root: Path, name: str) -> Path:
    work = root / "Tasks" / name
    shutil.copytree(FROZEN / "run", work)
    for path in [work, *work.rglob("*")]:
        path.chmod(0o755 if path.is_dir() else 0o644)
    return work


def reset_owner(module, work: Path) -> None:
    matrix_path = work / "matrix.json"
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    for cell in matrix["cells"]:
        if cell.get("outcome") != "owner-resolved":
            continue
        for key in ("owner_ruling", "owner_ruling_history", "resolved_verdict"):
            cell.pop(key, None)
        cell["outcome"] = module._reader_outcome(cell)
        cell["status"] = "judged" if cell["outcome"].startswith("agreement-") else "unresolved"
    matrix_path.write_bytes(module.canonical(matrix))
    (work / "owner-rulings.json").unlink(missing_ok=True)
    module.owner_queue(work)


def reset_cell(module, work: Path) -> dict:
    manifest = json.loads((work / "unit-manifest.json").read_text(encoding="utf-8"))
    matrix_path = work / "matrix.json"
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    cell = next(item for item in matrix["cells"] if item["cell_id"] == TARGET_CELL)
    claims = {
        seat: {
            "verdict": reader.get("verdict"),
            "quote": reader.get("quote"),
            "source_id": reader.get("source_id"),
            "source_quote": reader.get("source_quote"),
            **({"intake": copy.deepcopy(reader["intake"])} if reader.get("intake") else {}),
        }
        for seat, reader in cell["readers"].items()
    }
    replacement = next(
        item for item in module.build_matrix(manifest)["cells"] if item["cell_id"] == TARGET_CELL
    )
    matrix["cells"][matrix["cells"].index(cell)] = replacement
    matrix_path.write_bytes(module.canonical(matrix))
    return claims


def cli(script: Path, *arguments: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, str(script), *map(str, arguments)],
        text=True, capture_output=True, cwd=ROOT, env=environment,
    )
    if result.returncode != expected:
        raise RuntimeError(
            f"installed command returned {result.returncode}, expected {expected}: {result.stderr or result.stdout}"
        )
    return result


def main() -> int:
    projection = json.loads(PROJECTIONS.read_text(encoding="utf-8"))["entries"]["critique-machinery"]
    frozen_before = {
        name: digest(FROZEN / name)
        for name in ("run/matrix.json", "run/sources.json", "state.json", "assessment.md", "page-v3-located.txt")
    }
    clients = {}
    with tempfile.TemporaryDirectory(prefix="critique-atom-11-") as raw:
        scratch = Path(raw)
        (scratch / ".git").mkdir()
        for client, install in INSTALLS.items():
            script = install / "scripts/critique.py"
            module = load(f"critique_atom_11_{client}", script)
            client_root = scratch / client
            client_root.mkdir()

            derived_work = client_root / "Tasks/derived"
            opened = cli(
                script, "open", "--page", FROZEN / "page.md", "--from-run", FROZEN / "state.json",
                "--deliverable", "tactical_roadmap", "--work", derived_work,
                "--no-reference", "UP supplies no roadmap-shaped benchmark",
            )
            opening = json.loads(opened.stdout)

            exact_work = writable_copy(client_root, "exact")
            exact_claims = reset_cell(module, exact_work)
            exact = module.record_cell_readers(exact_work, TARGET_CELL, exact_claims)

            altered_work = writable_copy(client_root, "altered")
            altered_claims = reset_cell(module, altered_work)
            altered_claims["reader-2"]["source_quote"] = "Always-on after launch!"
            altered = module.record_cell_readers(altered_work, TARGET_CELL, altered_claims)
            document = cli(script, "document", "--work", altered_work, expected=2)

            bulk_work = writable_copy(client_root, "bulk")
            reset_owner(module, bulk_work)
            bulk = json.loads(cli(
                script, "rule-bulk", "--work", bulk_work, "--assessment", FROZEN / "assessment.md",
                "--by", OWNER_WORDS,
            ).stdout)
            actual_rulings = json.loads((bulk_work / "owner-rulings.json").read_text(encoding="utf-8"))["rulings"]
            expected_rulings = json.loads((FROZEN / "run/owner-rulings.json").read_text(encoding="utf-8"))["rulings"]

            located_work = writable_copy(client_root, "located")
            reset_owner(module, located_work)
            located_output = cli(script, "located", "--work", located_work, "--only", "disputed").stdout
            expected_located = "\n".join((FROZEN / "page-v3-located.txt").read_text(encoding="utf-8").splitlines()[3:]) + "\n"

            policy = json.loads((install / "client-model-policy.json").read_text(encoding="utf-8"))
            installed_hash = tree_hash(install)
            expected_hash = projection["projected_tree_sha256_by_client"][client]
            checks = {
                "projection_match": installed_hash == expected_hash,
                "derived_sources": len(opening["derived"]["sources"]) == 6,
                "exact_short_line": exact["readers"]["reader-2"]["upstream_trace"]["quote"] == "Always-on after launch.",
                "altered_owner_visible": altered["outcome"] == "claim-without-grounded-words",
                "document_blocked": "owner questions remain open" in document.stderr,
                "bulk_count": bulk["filed"] == 16,
                "bulk_choices": [item["choice"] for item in actual_rulings] == [item["choice"] for item in expected_rulings],
                "bulk_marker": all(item["because"].startswith(OWNER_WORDS + module.BULK_RULING_MARKER) for item in actual_rulings),
                "located_line_for_line": located_output == expected_located,
            }
            if not all(checks.values()):
                raise RuntimeError(f"{client} installed validation failed: {checks}")
            clients[client] = {
                "path": str(install),
                "tree_sha256": installed_hash,
                "expected_projection_sha256": expected_hash,
                "policy": policy,
                "checks": checks,
                "model_calls": 0,
            }
    frozen_after = {name: digest(FROZEN / name) for name in frozen_before}
    if frozen_before != frozen_after:
        raise RuntimeError("frozen v3 evidence changed during installed validation")
    result = {
        "schema_version": 1,
        "status": "passed",
        "installer": "working-agreement/install_skills.py",
        "clients": clients,
        "frozen_hashes_before": frozen_before,
        "frozen_hashes_after": frozen_after,
        "model_calls": 0,
    }
    target = ATOM / "installed-validation/summary.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "clients": sorted(clients), "model_calls": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
