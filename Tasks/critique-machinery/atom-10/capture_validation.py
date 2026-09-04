#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ATOM = ROOT / "Tasks/critique-machinery/atom-10"
WORK = ATOM / "operator-validation/Tasks/run"
SCRIPT = ROOT / "skills/critique-machinery/scripts/critique.py"
PROJECTIONS = ROOT / "working-agreement/client-skill-projections.json"
INSTALLS = {
    "codex": Path("/Users/kamenkamenov/.codex/skills/critique-machinery"),
    "claude": Path("/Users/kamenkamenov/.claude/skills/critique-machinery"),
}


def load_module():
    spec = importlib.util.spec_from_file_location("critique_atom_10_validation", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def tree_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        digest.update(item.relative_to(path).as_posix().encode() + b"\0")
        digest.update(item.read_bytes())
    return digest.hexdigest()


def main() -> int:
    module = load_module()
    status = module.matrix_status(WORK)
    attempts = []
    for path in sorted(WORK.glob("reader-evidence/batch-*/reader-*/attempt-002/reader-intake.json")):
        intake = json.loads(path.read_text(encoding="utf-8"))
        envelope_path = path.with_name("reader-input-envelope.json")
        envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
        attempts.append({
            "request_id": intake["request_id"],
            "batch_id": intake["batch_id"],
            "seat": intake["seat"],
            "attempt": intake["attempt"],
            "outcome": intake["outcome"],
            "reply_bytes": intake["reply_bytes"],
            "exit_code": intake["exit_code"],
            "evidence_path": str(path.parent.relative_to(ROOT)),
            "intake_sha256": module.digest_file(path),
            "input_envelope_sha256": module.digest_file(envelope_path),
            "client": envelope["client"],
            "isolated_working_directory": envelope["isolated_working_directory"],
            "instruction_sha256": envelope["instruction_sha256"],
            "schema_sha256": envelope["schema_sha256"],
        })
    expected_requests = {
        "batch-u-001-67522c23::reader-2",
        "batch-u-024-14772212::reader-1",
        "batch-u-024-14772212::reader-2",
    }
    if {item["request_id"] for item in attempts} != expected_requests:
        raise RuntimeError(f"retry identities changed: {attempts}")
    if any(item["attempt"] != 2 or item["outcome"] != "valid" for item in attempts):
        raise RuntimeError(f"bounded retry did not produce three valid second attempts: {attempts}")
    if status["recorded_count"] != 150 or status["unjudged_count"] or status["half_recorded_count"]:
        raise RuntimeError(f"post-retry matrix is not fully recorded: {status}")
    if status["retryable_failed_seat_count"] or status["retry_exhausted_seat_count"]:
        raise RuntimeError(f"post-retry matrix retained a failed seat: {status['failed_seats']}")
    post_retry = {
        "schema_version": 1,
        "route": "installed-claude-code-interview-retry-failed",
        "model_calls": 3,
        "attempts": attempts,
        "status": status,
        "matrix_sha256": module.digest_file(WORK / "matrix.json"),
        "frozen_matrix_sha256": module.digest_file(ATOM / "frozen-red/matrix.json"),
        "original_attempts_preserved": all(
            (ROOT / item["evidence_path"]).with_name("attempt-001").is_dir()
            for item in attempts
        ),
        "third_attempts_absent": not any(WORK.glob("reader-evidence/batch-*/reader-*/attempt-003")),
    }
    (ATOM / "operator-validation/post-retry-result.json").write_bytes(module.canonical(post_retry))

    projection = json.loads(PROJECTIONS.read_text(encoding="utf-8"))["entries"]["critique-machinery"]
    installed = {}
    for client, path in INSTALLS.items():
        policy = json.loads((path / "client-model-policy.json").read_text(encoding="utf-8"))
        observed_hash = tree_hash(path)
        expected_hash = projection["projected_tree_sha256_by_client"][client]
        installed[client] = {
            "path": str(path),
            "tree_sha256": observed_hash,
            "expected_projection_sha256": expected_hash,
            "exact_projection_match": observed_hash == expected_hash,
            "policy": policy,
        }
        if observed_hash != expected_hash:
            raise RuntimeError(f"{client} installed tree differs from its generated projection")
        required = "codex exec" if client == "codex" else "claude -p"
        if policy.get("fail_closed") is not True or policy.get("required_runtime") != required:
            raise RuntimeError(f"{client} policy is not fail closed for its own runtime: {policy}")
    install_result = {
        "schema_version": 1,
        "installer": "working-agreement/install_skills.py",
        "selected_managed_skills": ["critique-machinery"],
        "clients": installed,
        "model_calls": 0,
        "global_check_observation": (
            "The whole-root checker reported unrelated description-machinery drift in the Codex root; "
            "this atom did not change or reinstall that skill. Both critique-machinery trees match exactly."
        ),
        "status": "passed",
    }
    target = ATOM / "installed-validation/summary.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(module.canonical(install_result))
    print(json.dumps({"post_retry": post_retry, "installed": install_result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
