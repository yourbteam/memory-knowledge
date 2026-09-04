#!/usr/bin/env python3
"""Apply a bounded convergence review-state request without hand-built JSON flags."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from scripts import prevention_source_receipt
except ModuleNotFoundError:  # direct script execution
    import prevention_source_receipt


PASS_SIGNAL = "CONVERGENCE STATE REVIEW CYCLE OK"
RUNTIME_TEMP_ROOT = Path("/private/tmp")
TASK_ARTIFACT_ROOT = Path(__file__).resolve().parents[1] / "Tasks"
CANONICAL_HELPER_PATH = Path(__file__).resolve().parents[1] / "skills/_shared/convergence_state.py"
# Explicit helper contract: the repository canonical copy is the default; installed client
# copies are acceptable only with the same content identity. HELPER_PATH remains the
# configurable primary location (tests and callers may rebind it).
HELPER_PATH = CANONICAL_HELPER_PATH
ALLOWED_HELPER_PATHS = (
    CANONICAL_HELPER_PATH,
    Path.home() / ".codex/skills/_shared/convergence_state.py",
    Path.home() / ".claude/skills/_shared/convergence_state.py",
)
HELPER_SHA256 = "82c11a852ffa373be821106577b2b2c2b62cb6c537a98b829bfe97e16fd0b8ae"
OPERATION_RECEIPT_ROOT = Path(os.environ.get(
    "CONVERGENCE_REVIEW_OPERATION_RECEIPT_ROOT",
    "/private/tmp/convergence-review-operation-receipts",
))
AUTHORITY_APPROVAL_ROOT = Path(os.environ.get(
    "CONVERGENCE_AUTHORITY_APPROVAL_ROOT",
    "/private/tmp/convergence-authority-approvals",
))
OPERATION_FIELDS = {
    "record-gap": {
        "operation_id", "kind", "id", "requirement_ids", "source_stage", "impact", "evidence",
    },
    "grant-autonomy": {
        "operation_id", "kind", "id", "repository_keys", "allowed_paths", "stage",
        "evidence", "authority_approval_receipt_id",
    },
    "grant-scope-change": {
        "operation_id", "kind", "id", "repository_keys", "allowed_paths", "stage",
        "evidence", "authority_approval_receipt_id",
    },
    "accept-baseline": {
        "operation_id", "kind", "repository_key", "changed_paths", "approval_id", "stage",
        "accept_approved_dirty_overlap",
    },
    "guard-baseline": {"operation_id", "kind"},
    "record-stage": {"operation_id", "kind", "result_file"},
    "transition": {"operation_id", "kind", "to"},
    "check": {"operation_id", "kind"},
    "status": {"operation_id", "kind"},
}


class ReviewCycleError(RuntimeError):
    def __init__(self, code: str, exit_code: int = 2) -> None:
        super().__init__(code)
        self.code = code
        self.exit_code = exit_code


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ReviewCycleError(code)
    return value.strip()


def _string_list(value: Any, code: str, *, nonempty: bool = True) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        raise ReviewCycleError(code)
    normalized = [_text(item, code) for item in value]
    if len(normalized) != len(set(normalized)):
        raise ReviewCycleError(f"duplicate-{code}")
    return normalized


def _regular_file(value: Any, code: str) -> Path:
    raw = str(value) if isinstance(value, Path) else _text(value, code)
    path = Path(raw).expanduser().resolve()
    if not path.is_file():
        raise ReviewCycleError(code)
    return path


def _request(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewCycleError("invalid-review-cycle-request") from exc
    if (
        not isinstance(value, dict)
        or set(value) != {
            "schema_version", "request_id", "state", "initial_state_sha256",
            "expected_final_status", "operations",
        }
        or value.get("schema_version") != 2
        or not isinstance(value.get("operations"), list)
        or not value["operations"]
    ):
        raise ReviewCycleError("invalid-review-cycle-request")
    operation_ids = [item.get("operation_id") for item in value["operations"] if isinstance(item, dict)]
    if len(operation_ids) != len(value["operations"]) or len(set(operation_ids)) != len(operation_ids):
        raise ReviewCycleError("invalid-review-cycle-operation-ids")
    try:
        uuid.UUID(str(value["request_id"]))
        for operation_id in operation_ids:
            uuid.UUID(str(operation_id))
    except (ValueError, AttributeError) as exc:
        raise ReviewCycleError("invalid-review-cycle-operation-ids") from exc
    if not re.fullmatch(r"[0-9a-f]{64}", str(value["initial_state_sha256"])):
        raise ReviewCycleError("invalid-initial-state-sha256")
    return value


def _trusted_path(value: Any, code: str) -> Path:
    raw = _text(value, code)
    token, separator, relative = raw.partition("/")
    roots = {
        "runtime-temp": RUNTIME_TEMP_ROOT,
        "task-artifact-root": TASK_ARTIFACT_ROOT,
    }
    root = roots.get(token)
    if root is None or not separator:
        raise ReviewCycleError(code)
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ReviewCycleError(code) from exc
    return path


def _trusted_input_file(value: Any, code: str) -> Path:
    path = _regular_file(value, code)
    for root in (RUNTIME_TEMP_ROOT, TASK_ARTIFACT_ROOT):
        try:
            path.relative_to(root.resolve())
            return path
        except ValueError:
            continue
    raise ReviewCycleError(code)


def _fixed_helper(value: Any) -> Path:
    helper = _regular_file(value, "helper-is-not-a-file")
    allowed = {Path(HELPER_PATH).resolve(), CANONICAL_HELPER_PATH.resolve()}
    allowed.update(path.resolve() for path in ALLOWED_HELPER_PATHS if path.exists())
    if (
        helper not in allowed
        or hashlib.sha256(helper.read_bytes()).hexdigest() != HELPER_SHA256
    ):
        raise ReviewCycleError("helper-identity-mismatch")
    return helper


def _json_list(values: list[str]) -> str:
    """The one authoritative serialization for helper list-valued flags."""
    return json.dumps(values, ensure_ascii=True, separators=(",", ":"))


def _repository_roots(state_payload: Mapping[str, Any]) -> dict[str, Path]:
    repositories = state_payload.get("repositories")
    if not isinstance(repositories, dict):
        raise ReviewCycleError("state-repositories-invalid")
    result: dict[str, Path] = {}
    for raw in repositories:
        path = Path(raw).resolve()
        key = path.name
        if not key or key in result:
            raise ReviewCycleError("state-repository-key-ambiguous")
        result[key] = path
    return result


def _relative_under(root: Path, value: Any, code: str) -> Path:
    raw = Path(_text(value, code))
    if raw.is_absolute() or any(part in {"", ".", ".."} for part in raw.parts):
        raise ReviewCycleError(code)
    return root / raw


def _operation_argv(
    operation: Any, *, helper: Path, state: Path, repositories: Mapping[str, Path],
) -> list[str]:
    if not isinstance(operation, dict) or operation.get("kind") not in OPERATION_FIELDS:
        raise ReviewCycleError("invalid-review-cycle-operation")
    kind = operation["kind"]
    if set(operation) != OPERATION_FIELDS[kind]:
        raise ReviewCycleError(f"invalid-{kind}-fields")
    base = [sys.executable, str(helper)]
    if kind == "record-gap":
        requirement_ids = _string_list(
            operation["requirement_ids"], "requirement-ids",
        )
        return [
            *base, "record-gap", str(state),
            "--id", _text(operation["id"], "invalid-gap-id"),
            "--requirement-ids", _json_list(requirement_ids),
            "--source-stage", _text(operation["source_stage"], "invalid-source-stage"),
            "--impact", _text(operation["impact"], "invalid-impact"),
            "--evidence", _text(operation["evidence"], "invalid-evidence"),
        ]
    if kind in {"grant-autonomy", "grant-scope-change"}:
        approval_kind = "autonomy" if kind == "grant-autonomy" else "scope-change"
        approval_operation = "accept-baseline" if kind == "grant-autonomy" else "expand-baseline"
        keys = _string_list(operation["repository_keys"], "repository-keys")
        try:
            roots = [repositories[key] for key in keys]
        except KeyError as exc:
            raise ReviewCycleError("unknown-repository-key") from exc
        allowed = _string_list(operation["allowed_paths"], "allowed-paths")
        if len(roots) != 1:
            raise ReviewCycleError("approval-repository-cardinality")
        return [
            *base, "grant-approval", str(state),
            "--id", _text(operation["id"], "invalid-approval-id"),
            "--kind", approval_kind,
            "--operations", _json_list([approval_operation]),
            "--repository-roots", _json_list([str(item) for item in roots]),
            "--allowed-paths", _json_list([
                str(_relative_under(roots[0], item, "allowed-paths")) for item in allowed
            ]),
            "--stage", _text(operation["stage"], "invalid-stage"),
            "--evidence", _text(operation["evidence"], "invalid-evidence"),
        ]
    if kind == "accept-baseline":
        repository = repositories.get(_text(operation["repository_key"], "invalid-repository-key"))
        if repository is None:
            raise ReviewCycleError("unknown-repository-key")
        command = [
            *base, "accept-baseline", str(state),
            "--path", str(repository),
        ]
        for changed_path in _string_list(operation["changed_paths"], "changed-paths"):
            command.extend(["--changed-path", str(_relative_under(
                repository, changed_path, "changed-paths"
            ))])
        command.extend([
            "--approval-id", _text(operation["approval_id"], "invalid-approval-id"),
            "--stage", _text(operation["stage"], "invalid-stage"),
        ])
        if operation["accept_approved_dirty_overlap"] is True:
            command.append("--accept-approved-dirty-overlap")
        elif operation["accept_approved_dirty_overlap"] is not False:
            raise ReviewCycleError("invalid-accept-approved-dirty-overlap")
        return command
    if kind == "guard-baseline":
        return [*base, "guard-baseline", str(state)]
    if kind == "record-stage":
        return [
            *base, "record-stage", str(state), "--result-file",
            str(_regular_file(
                _trusted_path(operation["result_file"], "result-file-is-not-a-file"),
                "result-file-is-not-a-file",
            )),
        ]
    if kind == "transition":
        return [
            *base, "transition", str(state), "--to",
            _text(operation["to"], "invalid-transition-target"),
        ]
    if kind == "check":
        return [*base, "check", str(state)]
    return [*base, "status", str(state), "--json"]


def build_commands(
    request: dict[str, Any], *, helper: Path,
) -> tuple[Path, list[list[str]]]:
    state = _regular_file(_trusted_path(request["state"], "state-is-not-a-file"), "state-is-not-a-file")
    try:
        state_payload = json.loads(state.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewCycleError("state-schema-invalid") from exc
    repositories = _repository_roots(state_payload)
    commands = [
        _operation_argv(
            operation, helper=helper, state=state, repositories=repositories
        )
        for operation in request["operations"]
    ]
    commands.extend([
        [sys.executable, str(helper), "check", str(state)],
        [sys.executable, str(helper), "status", str(state), "--json"],
    ])
    return state, commands


def _safe_command(command: list[str]) -> list[str]:
    safe = list(command)
    for flag in ("--evidence", "--impact"):
        if flag in safe:
            safe[safe.index(flag) + 1] = "<non-secret-text>"
    return safe


def _safe_failure_detail(completed: subprocess.CompletedProcess[str]) -> str:
    raw = (completed.stderr or completed.stdout or "").strip().splitlines()
    if not raw:
        return "helper-rejected"
    detail = raw[-1].strip()
    if not re.fullmatch(r"[A-Za-z0-9 _:-]{1,200}", detail):
        return "helper-rejected"
    return re.sub(r"[ _]+", "-", detail.lower())


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _operation_receipt_path(request: Mapping[str, Any], effect_id: str | None) -> Path:
    identity = effect_id or hashlib.sha256(
        json.dumps(request, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return OPERATION_RECEIPT_ROOT / f"{identity}.json"


def _load_operation_journal(
    path: Path, request: Mapping[str, Any], request_sha256: str,
) -> dict[str, Any]:
    expected = {
        "schema_version": 1,
        "request_id": request["request_id"],
        "request_sha256": request_sha256,
        "initial_state_sha256": request["initial_state_sha256"],
        "entries": [],
    }
    if not path.is_file():
        _atomic_json(path, expected)
        return expected
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewCycleError("operation-journal-invalid") from exc
    if not isinstance(value, dict) or any(
        value.get(name) != expected[name]
        for name in ("schema_version", "request_id", "request_sha256", "initial_state_sha256")
    ) or not isinstance(value.get("entries"), list):
        raise ReviewCycleError("operation-journal-identity-mismatch")
    return value


def _semantic_operation_applied(
    operation: Mapping[str, Any], state_payload: Mapping[str, Any],
) -> bool:
    kind = operation["kind"]
    if kind == "record-gap":
        gap = state_payload.get("gaps", {}).get(operation["id"])
        return isinstance(gap, Mapping) and all(
            gap.get(name) == operation[name]
            for name in ("requirement_ids", "source_stage", "impact", "evidence")
        )
    if kind in {"grant-autonomy", "grant-scope-change"}:
        approval = state_payload.get("approvals", {}).get(operation["id"])
        expected_kind = "autonomy" if kind == "grant-autonomy" else "scope-change"
        return bool(
            isinstance(approval, Mapping)
            and approval.get("status") in {"granted", "consumed"}
            and approval.get("scope", {}).get("kind") == expected_kind
            and approval.get("scope", {}).get("stage") == operation["stage"]
        )
    if kind == "accept-baseline":
        repositories = state_payload.get("repositories", {})
        matching = [
            value for raw, value in repositories.items()
            if Path(raw).name == operation["repository_key"]
        ]
        return bool(
            len(matching) == 1
            and all(path in matching[0].get("expected_allowed", {})
                    for path in operation["changed_paths"])
        )
    if kind == "record-stage":
        return any(
            isinstance(value, Mapping)
            and value.get("input_payload") is not None
            for value in state_payload.get("stages", {}).values()
        )
    if kind == "transition":
        return state_payload.get("status") == operation["to"]
    return False


def _authority_receipt(operation: Mapping[str, Any]) -> tuple[Path, Path]:
    receipt_id = _text(
        operation["authority_approval_receipt_id"],
        "authority-approval-receipt-id-invalid",
    )
    source = AUTHORITY_APPROVAL_ROOT / f"{receipt_id}.json"
    consumed = AUTHORITY_APPROVAL_ROOT / "consumed" / (
        f"{receipt_id}.{operation['operation_id']}.json"
    )
    path = source if source.is_file() else consumed
    if not path.is_file():
        raise ReviewCycleError("authority-approval-receipt-unavailable")
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewCycleError("authority-approval-receipt-invalid") from exc
    required = {
        "authority_approval_receipt_id", "grant_kind", "grant_id",
        "repository_keys", "allowed_paths_sha256", "stage", "evidence_sha256",
        "approved_by", "approved_at_utc",
    }
    expected_kind = (
        "autonomy" if operation["kind"] == "grant-autonomy" else "scope-change"
    )
    allowed_sha256 = hashlib.sha256(
        (json.dumps(sorted(operation["allowed_paths"]), separators=(",", ":")) + "\n").encode()
    ).hexdigest()
    evidence_sha256 = hashlib.sha256(operation["evidence"].encode()).hexdigest()
    if (
        not isinstance(receipt, Mapping) or set(receipt) != required
        or receipt.get("authority_approval_receipt_id") != receipt_id
        or receipt.get("grant_kind") != expected_kind
        or receipt.get("grant_id") != operation["id"]
        or receipt.get("repository_keys") != sorted(operation["repository_keys"])
        or receipt.get("allowed_paths_sha256") != allowed_sha256
        or receipt.get("stage") != operation["stage"]
        or receipt.get("evidence_sha256") != evidence_sha256
        or not isinstance(receipt.get("approved_by"), str)
        or not isinstance(receipt.get("approved_at_utc"), str)
    ):
        raise ReviewCycleError("authority-approval-receipt-invalid")
    return source, consumed


def _consume_authority_receipt(operation: Mapping[str, Any]) -> None:
    if operation["kind"] not in {"grant-autonomy", "grant-scope-change"}:
        return
    source, consumed = _authority_receipt(operation)
    if consumed.is_file():
        return
    consumed.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, consumed)


def _run_operations(
    *, request: Mapping[str, Any], state: Path, commands: Sequence[Sequence[str]],
    effect_id: str | None, request_sha256: str,
) -> list[subprocess.CompletedProcess[str]]:
    journal_path = _operation_receipt_path(request, effect_id)
    journal = _load_operation_journal(journal_path, request, request_sha256)
    operations = request["operations"]
    entries = journal["entries"]
    if len(entries) > len(operations):
        raise ReviewCycleError("operation-journal-cardinality-invalid")
    for index, entry in enumerate(entries):
        operation = operations[index]
        input_sha256 = hashlib.sha256(
            json.dumps(operation, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if (
            not isinstance(entry, Mapping)
            or entry.get("operation_id") != operation["operation_id"]
            or entry.get("kind") != operation["kind"]
            or entry.get("input_sha256") != input_sha256
            or entry.get("status") not in {"PREPARED", "APPLIED"}
        ):
            raise ReviewCycleError("operation-journal-entry-mismatch")
    current_sha256 = hashlib.sha256(state.read_bytes()).hexdigest()
    if entries:
        last = entries[-1]
        if last["status"] == "APPLIED" and current_sha256 != last["post_state_sha256"]:
            raise ReviewCycleError("operation-journal-state-mismatch")
        if last["status"] == "PREPARED" and current_sha256 != last["pre_state_sha256"]:
            state_payload = json.loads(state.read_text(encoding="utf-8"))
            if not _semantic_operation_applied(operations[len(entries) - 1], state_payload):
                raise ReviewCycleError("operation-reconciliation-indeterminate")
            last.update(status="APPLIED", post_state_sha256=current_sha256,
                        result_sha256=hashlib.sha256(b"reconciled\n").hexdigest())
            _consume_authority_receipt(operations[len(entries) - 1])
            _atomic_json(journal_path, journal)
    elif current_sha256 != request["initial_state_sha256"]:
        raise ReviewCycleError("operation-journal-initial-state-mismatch")
    results: list[subprocess.CompletedProcess[str]] = []
    applied_count = sum(entry["status"] == "APPLIED" for entry in entries)
    for index in range(applied_count, len(operations)):
        operation = operations[index]
        command = list(commands[index])
        input_sha256 = hashlib.sha256(
            json.dumps(operation, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        prepared = {
            "operation_id": operation["operation_id"], "kind": operation["kind"],
            "input_sha256": input_sha256, "status": "PREPARED",
            "pre_state_sha256": hashlib.sha256(state.read_bytes()).hexdigest(),
        }
        entries.append(prepared)
        if operation["kind"] in {"grant-autonomy", "grant-scope-change"}:
            _authority_receipt(operation)
        _atomic_json(journal_path, journal)
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        if completed.returncode:
            raise ReviewCycleError(
                f"operation-failed:{index}:{command[2]}:{_safe_failure_detail(completed)}",
                completed.returncode,
            )
        prepared.update(
            status="APPLIED",
            post_state_sha256=hashlib.sha256(state.read_bytes()).hexdigest(),
            result_sha256=hashlib.sha256(
                ((completed.stdout or "") + "\0" + (completed.stderr or "")).encode()
            ).hexdigest(),
        )
        _consume_authority_receipt(operation)
        _atomic_json(journal_path, journal)
        results.append(completed)
    return results


def apply_request(args: argparse.Namespace) -> dict[str, Any]:
    request_path = _trusted_input_file(args.request, "request-is-not-a-file")
    helper = _fixed_helper(args.helper)
    request = _request(request_path)
    state, commands = build_commands(request, helper=helper)
    observed_state_sha256 = hashlib.sha256(state.read_bytes()).hexdigest()
    candidate_effect_id = getattr(args, "prevention_effect_id", None)
    resumable = _operation_receipt_path(request, candidate_effect_id).is_file()
    if (
        request["initial_state_sha256"] != observed_state_sha256
        and (args.dry_run or not resumable)
    ):
        raise ReviewCycleError("initial-state-sha256-mismatch")
    initial_state_sha256 = str(request["initial_state_sha256"])
    expected_status = _text(request["expected_final_status"], "invalid-expected-final-status")
    if expected_status not in {
        "research", "plan", "implementation", "review", "blocked",
        "cap_reached", "complete",
    }:
        raise ReviewCycleError("invalid-expected-final-status")
    source_identity = {
        "request_sha256": hashlib.sha256(request_path.read_bytes()).hexdigest(),
        "helper_sha256": hashlib.sha256(helper.read_bytes()).hexdigest(),
        "state_path_sha256": hashlib.sha256(str(state).encode("utf-8")).hexdigest(),
        "operation_count": len(request["operations"]),
    }
    prevention_effect_id = getattr(args, "prevention_effect_id", None)
    prevention_preparation_sha256 = getattr(
        args, "prevention_preparation_sha256", None
    )
    profile_id = "dry-run" if args.dry_run else "apply"
    if prevention_effect_id or prevention_preparation_sha256:
        prevention_source_receipt.prepare(
            owner_sequence_id="convergence-state-review-cycle",
            profile_id=profile_id,
            effect_id=prevention_effect_id,
            preparation_artifact_sha256=prevention_preparation_sha256,
            source_identity=source_identity,
        )
    if args.dry_run:
        result = {
            "ok": True, "cycle_status": "DRY_RUN",
            "convergence_status": expected_status,
            "initial_state_sha256": initial_state_sha256,
            "final_state_sha256": hashlib.sha256(state.read_bytes()).hexdigest(),
            "operation_count": len(request["operations"]),
            "commands": [_safe_command(item) for item in commands],
        }
        if prevention_effect_id:
            receipt = prevention_source_receipt.complete(
                owner_sequence_id="convergence-state-review-cycle",
                profile_id=profile_id,
                effect_id=prevention_effect_id,
                preparation_artifact_sha256=prevention_preparation_sha256,
                source_identity=source_identity,
                result_identity={
                    "state_sha256": initial_state_sha256,
                    "operation_count": len(request["operations"]),
                    "cycle_status": "DRY_RUN",
                    "convergence_status": expected_status,
                },
            )
            result["preventionSourceReceiptSha256"] = (
                prevention_source_receipt.receipt_sha256(receipt)
            )
        return result
    operation_count = len(request["operations"])
    completed_results = _run_operations(
        request=request, state=state, commands=commands,
        effect_id=prevention_effect_id,
        request_sha256=source_identity["request_sha256"],
    )
    for index, command in enumerate(commands[operation_count:], start=operation_count):
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        if completed.returncode:
            raise ReviewCycleError(
                f"final-verification-failed:{index}:{command[2]}:{_safe_failure_detail(completed)}",
                completed.returncode,
            )
        completed_results.append(completed)
    try:
        final_status = json.loads(completed_results[-1].stdout)["status"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ReviewCycleError("final-status-envelope-invalid") from exc
    if final_status != expected_status:
        raise ReviewCycleError("expected-final-status-mismatch")
    result = {
        "ok": True, "cycle_status": "APPLIED",
        "convergence_status": final_status,
        "initial_state_sha256": initial_state_sha256,
        "final_state_sha256": hashlib.sha256(state.read_bytes()).hexdigest(),
        "operation_count": operation_count,
        "pass_signal": PASS_SIGNAL,
    }
    if prevention_effect_id:
        receipt = prevention_source_receipt.complete(
            owner_sequence_id="convergence-state-review-cycle",
            profile_id=profile_id,
            effect_id=prevention_effect_id,
            preparation_artifact_sha256=prevention_preparation_sha256,
            source_identity=source_identity,
            result_identity={
                "state_sha256": hashlib.sha256(state.read_bytes()).hexdigest(),
                "operation_count": operation_count,
                "cycle_status": "APPLIED",
                "convergence_status": final_status,
            },
        )
        result["preventionSourceReceiptSha256"] = (
            prevention_source_receipt.receipt_sha256(receipt)
        )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apply", nargs="?")
    parser.add_argument("--request", required=True)
    parser.add_argument(
        "--helper",
        default=str(CANONICAL_HELPER_PATH),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--prevention-effect-id")
    parser.add_argument("--prevention-preparation-sha256")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if not values:
        try:
            from scripts import sequence_intake_launch
        except ModuleNotFoundError:
            import sequence_intake_launch  # type: ignore
        return sequence_intake_launch.main_for_sequence(
            "convergence-state-review-cycle", [],
        )
    try:
        args = build_parser().parse_args(values)
        result = apply_request(args)
        if args.prevention_effect_id:
            result = {
                **result,
                "preventionEffectId": args.prevention_effect_id,
                "preventionPreparationSha256": args.prevention_preparation_sha256,
            }
        print(json.dumps(result, sort_keys=True))
        return 0
    except ReviewCycleError as exc:
        print(json.dumps({"ok": False, "error": exc.code}, sort_keys=True))
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
