#!/usr/bin/env python3
"""Execute the closed owner source-path acceptance matrix through production code."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from scripts import (
        prevention_adapters, prevention_budget, prevention_controller,
        prevention_observable_materializer, prevention_owner_runtime,
        prevention_owner_acceptance, prevention_registry, prevention_source_probes,
        prevention_source_receipt,
    )
    from scripts.prevention_contract import canonical_bytes, sha256_bytes
    from scripts.prevention_journal import JournalOwnership, PreventionJournal
    from scripts.prevention_owner_acceptance_cases import load_case_registry
    from scripts.prevention_owner_acceptance_fixtures import (
        ACCEPTANCE_THREAD_ID, AcceptanceBindingProvider, ensure_memory_mirror,
        ensure_rolling_policy, intent_for,
    )
    from scripts.prevention_contract_materializer import materialize
except ModuleNotFoundError:  # direct script execution
    import prevention_adapters
    import prevention_budget
    import prevention_controller
    import prevention_observable_materializer
    import prevention_owner_runtime
    import prevention_owner_acceptance
    import prevention_registry
    import prevention_source_probes
    import prevention_source_receipt
    from prevention_contract import canonical_bytes, sha256_bytes
    from prevention_journal import JournalOwnership, PreventionJournal
    from prevention_owner_acceptance_cases import load_case_registry
    from prevention_owner_acceptance_fixtures import (
        ACCEPTANCE_THREAD_ID, AcceptanceBindingProvider, ensure_memory_mirror,
        ensure_rolling_policy, intent_for,
    )
    from prevention_contract_materializer import materialize


class ProducerError(RuntimeError):
    """A checked acceptance case could not execute through the real source path."""


class AcceptanceBudgetProducer(prevention_budget.SourceOwnerBudgetProducer):
    """Bind acceptance budgeting to the same isolated immutable source artifacts."""

    def __init__(
        self, root: Path, *,
        executable_contracts: Mapping[str, Mapping[str, Any]],
    ):
        class AcceptanceFrontierTransport:
            @staticmethod
            def query(request: Mapping[str, Any]) -> Mapping[str, Any]:
                return {
                    "ownership": dict(request),
                    "source_state_sha256": sha256_bytes(canonical_bytes(request)),
                    "program_counters": {
                        "feature_count": 1,
                        "validation_round": 0,
                        "distinct_fatal_defects_in_round": 0,
                        "validation_fix_chain_count": 0,
                    },
                    "tasks": [{
                        "task_id": "greenfield-acceptance-atomic-task",
                        "task_kind": "FEATURE",
                    }],
                }

        super().__init__(
            executable_contracts=executable_contracts,
            frontier_transport=AcceptanceFrontierTransport(),
        )
        self.root = root

    def profile_variables(
        self, owner_sequence_id: str, profile_name: str,
        executable_contract: Mapping[str, Any], parameters: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        effective = dict(parameters)
        if (
            owner_sequence_id == "discovery-candidate-reconciliation"
            and profile_name in {"execute-rolling", "drive"}
        ):
            effective["baseline"] = str(ensure_rolling_policy(self.root))
        return super().profile_variables(
            owner_sequence_id, profile_name, executable_contract, effective
        )


class SimulatedSourceCrash(RuntimeError):
    """Acceptance-only crash after the real source effect but before result commit."""


@dataclass
class AcceptanceSourceEdge:
    """Schema-valid fake of the one true external edge allowed by the plan."""

    root: Path
    scenario: str
    owner_sequence_id: str
    profile_id: str
    allowed_routes: frozenset[tuple[str, str]] | None = None
    captures: list[tuple[dict[str, Any], prevention_source_probes.SourceProbeCapture]] | None = None
    envelopes: list[dict[str, Any]] | None = None
    source_results: dict[str, prevention_owner_runtime.ExecutionResult] | None = None

    def __post_init__(self) -> None:
        if self.allowed_routes is None:
            self.allowed_routes = frozenset({(
                self.owner_sequence_id, self.profile_id,
            )})
        if self.captures is None:
            self.captures = []
        if self.envelopes is None:
            self.envelopes = []
        if self.source_results is None:
            self.source_results = {}

    def record_observation_envelope(
        self, _request: Mapping[str, Any], envelope: Mapping[str, Any],
    ) -> None:
        assert self.envelopes is not None
        self.envelopes.append(dict(envelope))

    def record_source_result(
        self, effect_id: str, result: prevention_owner_runtime.ExecutionResult,
    ) -> None:
        if effect_id:
            assert self.source_results is not None
            self.source_results[effect_id] = result

    def _receipt(self, effect_id: str) -> Mapping[str, Any] | None:
        direct = self.root / "source-receipts" / f"{effect_id}.json"
        candidates = [direct] if direct.is_file() else list(
            (self.root / "memory-mirror" / "Tasks").glob(
                f"*/prevention-effects/{effect_id}.json"
            )
        )
        if len(candidates) != 1:
            return None
        raw = candidates[0].read_bytes()
        value = json.loads(raw)
        if not isinstance(value, Mapping) or raw != canonical_bytes(dict(value)):
            raise ProducerError("owner-source-receipt-noncanonical")
        return value

    @staticmethod
    def _result_envelope(
        result: prevention_owner_runtime.ExecutionResult | None,
    ) -> Mapping[str, Any] | None:
        if result is None:
            return None
        try:
            whole = json.loads(result.stdout)
        except json.JSONDecodeError:
            whole = None
        if isinstance(whole, Mapping):
            return whole
        for line in reversed(result.stdout.splitlines()):
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, Mapping):
                return value
        return None

    @staticmethod
    def _receipt_semantic_success(
        owner_id: str, profile: str, receipt: Mapping[str, Any],
    ) -> bool:
        if (
            receipt.get("owner_sequence_id") != owner_id
            or receipt.get("profile_id") != profile
            or receipt.get("status") != "APPLIED"
            or not isinstance(receipt.get("source_identity"), Mapping)
        ):
            return False
        result = receipt.get("result_identity")
        if owner_id == "discovery-bootstrap":
            source = receipt["source_identity"]
            return all(
                isinstance(source.get(name), str) and source.get(name)
                for name in (
                    "bootstrap_request_sha256", "discovery_path", "manifest_path",
                    "run_id", "event_id",
                )
            ) and Path(str(source["discovery_path"])).is_file() and Path(
                str(source["manifest_path"])
            ).is_file()
        if not isinstance(result, Mapping):
            return False
        if owner_id == "claude-auth-token-refresh":
            return result == {"command": profile, "returncode": 0}
        if owner_id == "local-workflow-orch-image":
            return result == {"profile": profile, "returncode": 0}
        if owner_id == "discovery-promotion-lifecycle":
            if profile == "drive":
                return (
                    result.get("ok") is True
                    and result.get("stage") == "complete"
                    and len(str(result.get("result_sha256", ""))) == 64
                )
            if profile == "status":
                return (
                    result.get("ok") is True
                    and isinstance(result.get("stage"), str)
                    and bool(result["stage"])
                    and len(str(result.get("result_sha256", ""))) == 64
                )
            return (
                result.get("ok") is True
                and result.get("next_stage") == "successor-verification"
                and len(str(result.get("result_sha256", ""))) == 64
            )
        if owner_id == "discovery-candidate-reconciliation":
            expected_stage = "complete" if profile == "drive" else profile
            return (
                result.get("ok") is True and result.get("stage") == expected_stage
                and len(str(result.get("result_sha256", ""))) == 64
            )
        if owner_id == "commit-push-main":
            return result.get("profile") == profile and result.get("ok") is True
        if owner_id == "convergence-checkpoint-run":
            return (
                result.get("verdict") == "CHECKPOINT_APPLIED"
                and all(
                    isinstance(result.get(name), str) and len(result[name]) == 64
                    for name in (
                        "state_before_sha256", "state_after_accept_sha256",
                        "state_after_guard_sha256",
                    )
                )
            )
        if owner_id == "convergence-state-review-cycle":
            return (
                result.get("cycle_status") == ("DRY_RUN" if profile == "dry-run" else "APPLIED")
                and isinstance(result.get("operation_count"), int)
                and result["operation_count"] > 0
                and len(str(result.get("state_sha256", ""))) == 64
                and isinstance(result.get("convergence_status"), str)
            )
        return False

    @staticmethod
    def _output_semantic_success(
        owner_id: str, profile: str, effect_id: str,
        preparation_sha256: str, result: prevention_owner_runtime.ExecutionResult | None,
        envelope: Mapping[str, Any] | None,
    ) -> bool:
        if result is None or result.returncode != 0 or envelope is None:
            return False
        if envelope.get("ok") is False or envelope.get("finalOk") is False:
            return False
        if envelope.get("errorCode") not in (None, ""):
            return False
        if str(envelope.get("verdict", "")).lower() in {"failed", "blocked", "unknown"}:
            return False
        if owner_id == "greenfield-full-drive":
            return (
                envelope.get("ok") is True
                and envelope.get("effectId") == effect_id
                and envelope.get("preventionPreparationSha256") == preparation_sha256
                and envelope.get("verdict") == "DETACHED"
                and len(str(envelope.get("stdoutSha256", ""))) == 64
                and len(str(envelope.get("stderrSha256", ""))) == 64
            )
        if owner_id == "mawf-playbook-blocker-reentry":
            return (
                envelope.get("preventionEffectId") == effect_id
                and envelope.get("preventionPreparationSha256") == preparation_sha256
                and envelope.get("mode") == profile
                and isinstance(envelope.get("targetRunId"), str)
                and bool(envelope["targetRunId"])
            )
        return True

    def has_source_application(self, effect_id: str) -> bool:
        receipt = self._receipt(effect_id)
        if receipt is not None and receipt.get("status") == "APPLIED":
            return True
        assert self.source_results is not None
        envelope = self._result_envelope(self.source_results.get(effect_id))
        return bool(
            isinstance(envelope, Mapping)
            and envelope.get("preventionEffectId", envelope.get("effectId")) == effect_id
        )

    def capture(self, request: Mapping[str, Any]):
        effect_id = str(request["effect_id"])
        preparation_sha256 = str(request["preparation_artifact_sha256"])
        preparation_path = (
            self.root / "run/prevention/artifacts" / f"{preparation_sha256}.json"
        )
        preparation_raw = preparation_path.read_bytes()
        if sha256_bytes(preparation_raw) != preparation_sha256:
            raise ProducerError("owner-source-preparation-drift")
        preparation = json.loads(preparation_raw)
        if not isinstance(preparation, Mapping):
            raise ProducerError("owner-source-preparation-invalid")
        owner_id = str(request.get("owner_sequence_id", ""))
        profile = str(request.get("profile", ""))
        if (owner_id, profile) not in self.allowed_routes:
            raise ProducerError("owner-source-route-identity-mismatch")
        receipt = self._receipt(effect_id)
        if receipt is not None and (
            receipt.get("effect_id") != effect_id
            or receipt.get("preparation_artifact_sha256") != preparation_sha256
        ):
            receipt = None
        assert self.source_results is not None
        source_result = self.source_results.get(effect_id)
        envelope = self._result_envelope(source_result)
        semantic_success = (
            self._receipt_semantic_success(owner_id, profile, receipt)
            if receipt is not None else self._output_semantic_success(
                owner_id, profile, effect_id, preparation_sha256,
                source_result, envelope,
            )
        )
        if self.scenario == "semantic-negative":
            semantic_success = False
        actual_effect_id = str(receipt.get("effect_id")) if receipt is not None else effect_id
        actual_owner_id = (
            str(receipt.get("owner_sequence_id")) if receipt is not None else owner_id
        )
        actual_profile = str(receipt.get("profile_id")) if receipt is not None else profile
        actual_preparation_sha256 = (
            str(receipt.get("preparation_artifact_sha256"))
            if receipt is not None else preparation_sha256
        )
        identity_observed = sha256_bytes(canonical_bytes({
            "effect_id": actual_effect_id,
            "owner_sequence_id": actual_owner_id,
            "profile": actual_profile,
        }))
        prestate_observed = sha256_bytes(canonical_bytes({
            "effect_id": actual_effect_id,
            "owner_sequence_id": actual_owner_id,
            "profile": actual_profile,
            "source_status": "ABSENT",
        }))
        probe_observed = {
            probe: sha256_bytes(canonical_bytes({
                "effect_id": actual_effect_id,
                "owner_sequence_id": actual_owner_id,
                "profile": actual_profile,
                "probe_id": probe,
                "source_status": "SATISFIED",
            }))
            for probe in request["probe_ids"]
        }
        applied = receipt is not None or self.has_source_application(effect_id)
        capture = prevention_source_probes.SourceProbeCapture(
            identity=prevention_source_probes.SourceHashFact(
                observed_sha256=identity_observed,
                known=True,
            ),
            ownership={
                "effect_id": actual_effect_id,
                "owner_sequence_id": actual_owner_id,
                "preparation_artifact_sha256": actual_preparation_sha256,
            },
            prestate=prevention_source_probes.SourceHashFact(
                observed_sha256=(
                    sha256_bytes(canonical_bytes({
                        "source_receipt": dict(receipt) if receipt is not None else envelope,
                    })) if applied else prestate_observed
                ),
                known=True,
            ),
            receipt=prevention_source_probes.SourceReceiptFact(
                present=applied, known=True,
                effect_id=request["effect_id"] if applied else None,
                preparation_artifact_sha256=(
                    request["preparation_artifact_sha256"] if applied else None
                ),
            ),
            work_state=prevention_source_probes.SourceWorkStateFact(
                terminal=applied, detached=not applied,
            ),
            probes={
                probe: prevention_source_probes.SourceProbeFact(
                    observed_sha256=(
                        probe_observed[probe] if semantic_success
                        else sha256_bytes(canonical_bytes({
                            "probe_id": probe,
                            "receipt": dict(receipt) if receipt is not None else envelope,
                        })) if applied else None
                    ),
                    known=True, absent=not applied,
                )
                for probe in request["probe_ids"]
            },
        )
        assert self.captures is not None
        self.captures.append((dict(request), capture))
        return capture


class RealSourceExecutor:
    """Run the exact materialized argv and mutate only the fake external edge."""

    def __init__(self, edge: AcceptanceSourceEdge, root: Path, *, scenario: str):
        self.edge = edge
        self.root = root
        self.scenario = scenario
        self.commands: list[tuple[str, ...]] = []
        self.executed_commands: list[tuple[str, ...]] = []
        self.last_result: prevention_owner_runtime.ExecutionResult | None = None
        self.crash_injected = False

    def __call__(self, argv: Sequence[str]) -> prevention_owner_runtime.ExecutionResult:
        command = tuple(str(item) for item in argv)
        self.commands.append(command)
        executed = list(command)
        mirror = ensure_memory_mirror(self.root)
        source_path = executed[1] if len(executed) > 1 else ""
        if source_path.startswith("/Users/kamenkamenov/memory-knowledge/scripts/"):
            if source_path.endswith("/discovery_promotion_lifecycle.py"):
                executed[1] = str(mirror / "scripts/discovery_promotion_lifecycle.py")
            for flag in ("--root", "--repo"):
                if flag in executed:
                    executed[executed.index(flag) + 1] = str(mirror)
            if source_path.endswith("/scoped_git_publish.py") and "--repo" in executed:
                executed[executed.index("--repo") + 1] = str(
                    self.root / "git-repository"
                )
            current_root = "/Users/kamenkamenov/memory-knowledge/"
            for index, value in enumerate(executed):
                if index == 1:
                    continue
                if value.startswith(current_root):
                    candidate = mirror / value[len(current_root):]
                    if candidate.exists():
                        executed[index] = str(candidate)
        executed_command = tuple(executed)
        self.executed_commands.append(executed_command)
        environment = dict(os.environ)
        # Versioned client identity: explicit codex kind, legacy thread session (schema-v1 writer).
        environment["MK_CLIENT_KIND"] = "codex"
        environment["CODEX_THREAD_ID"] = ACCEPTANCE_THREAD_ID
        environment.pop("MK_CLIENT_SESSION_ID", None)
        environment.pop("CLAUDE_SESSION_ID", None)
        environment["PREVENTION_SOURCE_RECEIPT_ROOT"] = str(
            self.root / "source-receipts"
        )
        environment["CONVERGENCE_REVIEW_OPERATION_RECEIPT_ROOT"] = str(
            self.root / "review-operation-receipts"
        )
        environment["CONVERGENCE_AUTHORITY_APPROVAL_ROOT"] = str(
            self.root / "authority-approvals"
        )
        environment["XDG_STATE_HOME"] = str(self.root / "xdg-state")
        environment["MK_DIRECTIVE_STATE_PATH"] = str(
            self.root / "directive-state.json"
        )
        source_root = "/Users/kamenkamenov/memory-knowledge"
        existing_pythonpath = environment.get("PYTHONPATH")
        uses_memory_mirror_imports = source_path.endswith((
            "/discovery_promotion_lifecycle.py",
            "/discovery_candidate_reconciliation.py",
        ))
        import_root = str(mirror) if uses_memory_mirror_imports else source_root
        pythonpath_parts = [import_root]
        if import_root != source_root:
            pythonpath_parts.append(source_root)
        if existing_pythonpath:
            pythonpath_parts.append(existing_pythonpath)
        environment["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
        environment["MK_PYTEST_PYTHON"] = source_root + "/.venv/bin/python"
        if source_path.endswith("/claude_auth_refresh.sh"):
            fake_bin = self.root / "claude-auth-fake-bin"
            fake_bin.mkdir(parents=True, exist_ok=True)
            fake_commands = {
                "docker": """#!/bin/sh
case "$1" in
  ps) printf '%s\\n' 'acceptance-acceptance-resource' ;;
  exec) printf '%s\\n' 'AUTH_OK' ;;
  cp) : ;;
  *) : ;;
esac
""",
                "az": """#!/bin/sh
if [ "$1 $2 $3" = "keyvault secret show" ]; then
  printf '%s\\n' '2026-07-19T00:00:00Z'
fi
exit 0
""",
                "claude": """#!/bin/sh
printf '%s\\n' 'AUTH_OK'
""",
                "security": """#!/bin/sh
case "$1" in
  find-generic-password) exit 1 ;;
  *) exit 0 ;;
esac
""",
                "uv": """#!/bin/sh
printf '%s\\n' 'acceptance-jwt'
""",
                "curl": """#!/usr/bin/env python3
import json, sys
target = None
for index, value in enumerate(sys.argv):
    if value == "-o" and index + 1 < len(sys.argv):
        target = sys.argv[index + 1]
url = next((value for value in reversed(sys.argv[1:]) if value.startswith("http")), "")
payload = (
    {"claude": {"status": "seeded"}}
    if url.endswith("/reseed")
    else {"credentials": {"claude": {"status": "valid"}}}
)
if target:
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
""",
            }
            for name, content in fake_commands.items():
                target = fake_bin / name
                target.write_text(content, encoding="utf-8")
                target.chmod(0o700)
            fake_home = self.root / "claude-auth-home"
            fake_home.mkdir(parents=True, exist_ok=True)
            environment["PATH"] = str(fake_bin) + os.pathsep + environment["PATH"]
            environment["HOME"] = str(fake_home)
            environment["USER"] = "acceptance"
            environment["WORKFLOW_ORCH_JWT_SECRET"] = "acceptance-not-a-secret"
            security_edge = self.root / "claude-auth-python-edge"
            security_edge.mkdir(parents=True, exist_ok=True)
            security_audit = self.root / "claude-auth-security-audit.jsonl"
            (security_edge / "sitecustomize.py").write_text("""import ctypes
import json
import os

_original_load_library = ctypes.cdll.LoadLibrary
_security_framework = "/System/Library/Frameworks/Security.framework/Security"


class _FakeFunction:
    def __init__(self, name, result):
        self.name = name
        self.result = result
        self.argtypes = None
        self.restype = None

    def __call__(self, *_args):
        with open(os.environ["CLAUDE_AUTH_SECURITY_AUDIT"], "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"operation": self.name}, sort_keys=True) + "\\n")
        return self.result


class _FakeSecurity:
    SecKeychainFindGenericPassword = _FakeFunction(
        "SecKeychainFindGenericPassword", -25300,
    )
    SecKeychainAddGenericPassword = _FakeFunction(
        "SecKeychainAddGenericPassword", 0,
    )
    SecKeychainItemModifyAttributesAndData = _FakeFunction(
        "SecKeychainItemModifyAttributesAndData", 0,
    )
    SecKeychainItemFreeContent = _FakeFunction(
        "SecKeychainItemFreeContent", 0,
    )


def _acceptance_load_library(name, *args, **kwargs):
    if name == _security_framework:
        return _FakeSecurity()
    return _original_load_library(name, *args, **kwargs)


ctypes.cdll.LoadLibrary = _acceptance_load_library
""", encoding="utf-8")
            environment["PYTHONPATH"] = (
                str(security_edge) + os.pathsep + environment["PYTHONPATH"]
            )
            environment["CLAUDE_AUTH_SECURITY_AUDIT"] = str(security_audit)
        if source_path.endswith("/local_workflow_orch_image_harness.py"):
            fake_bin = self.root / "local-image-fake-bin"
            fake_bin.mkdir(parents=True, exist_ok=True)
            docker = fake_bin / "docker"
            docker.write_text("""#!/usr/bin/env python3
import json, sys
args = sys.argv[1:]
if args == ["--version"]:
    print("Docker acceptance")
elif args[:2] == ["system", "df"]:
    print("TYPE TOTAL ACTIVE SIZE RECLAIMABLE")
elif args and args[0] == "inspect":
    raise SystemExit(1)
elif args and args[0] == "run":
    print("a" * 64)
elif args and args[0] == "port":
    print("0.0.0.0:54321")
elif args and args[0] == "logs":
    print("acceptance log")
elif args and args[0] == "exec":
    joined = " ".join(args)
    if "seed_git_secrets_from_keyvault" in joined:
        print(json.dumps({"github": "seeded", "azure_devops": "exists"}))
    elif "build_git_manager_from_settings" in joined:
        print(json.dumps({
            "managerType": "GitRemoteManager",
            "repositoryKey": "mcp-agents-workflow",
            "resolvedRepository": "acceptance/mcp-agents-workflow",
            "acquisitionStatus": "acquired",
            "clonePresent": True,
        }))
    elif "_seed_from_keyvault" in joined:
        print(json.dumps({"codex": "seeded"}))
    elif "codex exec" in joined:
        print("CODEX_OK" if "CODEX_OK" in joined else "OK")
""", encoding="utf-8")
            docker.chmod(0o700)
            az = fake_bin / "az"
            az.write_text(
                "#!/bin/sh\nprintf '%s\\n' acceptance-key-vault-token\n",
                encoding="utf-8",
            )
            az.chmod(0o700)
            environment["PATH"] = str(fake_bin) + os.pathsep + environment["PATH"]
            python_edge = self.root / "local-image-python-edge"
            python_edge.mkdir(parents=True, exist_ok=True)
            (python_edge / "sitecustomize.py").write_text("""import io
import urllib.request

class AcceptanceHealthResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return b'{"status":"ok"}\\n'

urllib.request.urlopen = lambda *_args, **_kwargs: AcceptanceHealthResponse()
""", encoding="utf-8")
            environment["PYTHONPATH"] = (
                str(python_edge) + os.pathsep + environment["PYTHONPATH"]
            )
        if source_path.endswith("/greenfield_full_drive.sh"):
            fake_bin = self.root / "greenfield-fake-bin"
            fake_bin.mkdir(parents=True, exist_ok=True)
            audit_path = self.root / "greenfield-python-audit.jsonl"
            fake_commands = {
                "docker": """#!/usr/bin/env python3
import json, re, sys

args = sys.argv[1:]
joined = " ".join(args)
if args == ["--version"]:
    print("Docker acceptance")
    raise SystemExit(0)
if args and args[0] == "info":
    raise SystemExit(0)
if args[:2] == ["image", "inspect"]:
    raise SystemExit(0)
if args and args[0] == "inspect":
    if "NetworkSettings.Ports" in joined or "8080/tcp" in joined:
        print("18082")
        raise SystemExit(0)
    if ".State.StartedAt" in joined:
        print("2026-07-19T00:00:00Z")
        raise SystemExit(0)
    raise SystemExit(1)
if args and args[0] == "run" and "df" in args:
    print("Filesystem 1G-blocks Used Available Use% Mounted on")
    print("overlay 64G 1G 63G 2% /")
elif args and args[0] == "run":
    print("a" * 64)
elif args and args[0] == "port":
    print("0.0.0.0:18082")
if args and args[0] == "logs":
    print("program-drive READY acceptance")
if args and args[0] == "restart":
    print(args[-1])
if args and args[0] == "exec":
    if "printenv WORKFLOW_ORCH_JWT_SECRET" in joined:
        print("acceptance-jwt-secret")
    elif "seed_git_secrets_from_keyvault" in joined:
        print(json.dumps({"github-app-config": "seeded+enriched"}))
    elif "build_git_manager_from_settings" in joined:
        match = re.search(r"resolve_repo\\((?:'|\\\")(.*?)(?:'|\\\")\\)", joined)
        repository_key = match.group(1) if match else "acceptance"
        print(json.dumps({
            "managerType": "GitRemoteManager",
            "repositoryKey": repository_key,
            "resolvedRepository": "acceptance/repository",
            "acquisitionStatus": "acquired",
            "clonePresent": True,
        }))
    elif "_seed_from_keyvault" in joined:
        print(json.dumps({"codex": "seeded"}))
    elif "codex exec" in joined:
        print("CODEX_OK")
raise SystemExit(0)
""",
                "curl": """#!/usr/bin/env python3
import json

print(json.dumps({
    "status": "ok",
    "runningWorkflowCount": 0,
    "busyWorkflowCount": 0,
    "waitingApprovalCount": 0,
}))
""",
                "az": """#!/bin/sh
if [ "$1 $2 $3" = "account get-access-token --resource" ]; then
  printf '%s\\n' 'acceptance-key-vault-token'
  exit 0
fi
printf '%s\\n' 'acceptance az rejected unexpected command' >&2
exit 64
""",
                "uv": """#!/usr/bin/env python3
import json, os, sys

args = sys.argv[1:]
if args[:2] != ["run", "python"] or len(args) < 3:
    print("acceptance uv permits only: uv run python <checked-in-script>", file=sys.stderr)
    raise SystemExit(64)
script = os.path.realpath(args[2])
root = "/Users/kamenkamenov/mcp-agents-workflow/scripts/"
if not script.startswith(root):
    print("acceptance uv rejected non-MCP script", file=sys.stderr)
    raise SystemExit(64)
with open(os.environ["GREENFIELD_UV_AUDIT"], "a", encoding="utf-8") as handle:
    handle.write(json.dumps({"script": script}, sort_keys=True) + "\\n")
python = "/Users/kamenkamenov/mcp-agents-workflow/.venv/bin/python"
os.execv(python, [python, script, *args[3:]])
""",
                "lsof": "#!/bin/sh\nexit 1\n",
                "ps": "#!/bin/sh\nexit 0\n",
                "sleep": "#!/bin/sh\nexit 0\n",
            }
            for name, content in fake_commands.items():
                target = fake_bin / name
                target.write_text(content, encoding="utf-8")
                target.chmod(0o700)
            fake_home = self.root / "greenfield-home"
            fake_home.mkdir(parents=True, exist_ok=True)
            environment["PATH"] = str(fake_bin) + os.pathsep + environment["PATH"]
            environment["HOME"] = str(fake_home)
            environment["GREENFIELD_UV_AUDIT"] = str(audit_path)
            python_edge = self.root / "greenfield-python-edge"
            python_edge.mkdir(parents=True, exist_ok=True)
            (python_edge / "sitecustomize.py").write_text("""import json
import socket
import sys
import types

if sys.argv[0] == "-" or sys.argv[0].endswith("/local_workflow_orch_image_harness.py"):
    class AcceptanceSocket:
        def __init__(self, *_args, **_kwargs):
            self.port = 0
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            self.close()
            return False
        def bind(self, address):
            self.port = int(address[1]) or 18082
        def getsockname(self):
            return ("127.0.0.1", self.port)
        def close(self):
            return None
    socket.socket = AcceptanceSocket

class AcceptanceHealthResponse:
    def __enter__(self):
        return self
    def __exit__(self, *_args):
        return False
    def read(self):
        return b'{"status":"ok","runningWorkflowCount":0,"busyWorkflowCount":0,"waitingApprovalCount":0}'

import urllib.request
urllib.request.urlopen = lambda *_args, **_kwargs: AcceptanceHealthResponse()

remote = types.ModuleType("remote_mcp_operator_tui")
class RemoteConfig:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
class _Result:
    def __init__(self, payload):
        self.payload = payload
class RemoteMcpClient:
    def __init__(self, _config):
        self.tools = ["workflow.project.set", "workflow.start", "workflow.greenfield.driveDag"]
    async def connect(self):
        return None
    async def close(self):
        return None
    async def call_tool(self, name, args):
        if name == "workflow.project.set":
            return _Result({"projectType": "code", "projectCode": "acceptance"})
        if name == "workflow.start":
            return _Result({
                "runId": "11111111-1111-4111-8111-111111111111",
                "taskGuid": "acceptance-greenfield-task",
                "mawfTaskLeaseAcquired": True,
            })
        if name == "workflow.greenfield.driveDag":
            return _Result({
                "ok": True, "started": True,
                "startFeatureIndex": args.get("startFeatureIndex", 0),
                "programDriveId": args.get("programDriveId"),
            })
        raise RuntimeError("unexpected acceptance MCP tool: " + name)
remote.RemoteConfig = RemoteConfig
remote.RemoteMcpClient = RemoteMcpClient
sys.modules["remote_mcp_operator_tui"] = remote
""", encoding="utf-8")
            environment["PYTHONPATH"] = (
                str(python_edge) + os.pathsep + environment["PYTHONPATH"]
            )
        if source_path.endswith("/mawf_playbook_test_sequence.py"):
            fake_bin = self.root / "mawf-operator-fake-bin"
            fake_bin.mkdir(parents=True, exist_ok=True)
            audit_path = self.root / "mawf-operator-audit.jsonl"
            bash = fake_bin / "bash"
            bash.write_text("""#!/usr/bin/env python3
import json, os, sys

args = sys.argv[1:]
expected = "/Users/kamenkamenov/mcp-agents-workflow/dist/remote-mcp-operator/run.sh"
if not args or os.path.realpath(args[0]) != expected:
    print("acceptance bash rejected non-operator command", file=sys.stderr)
    raise SystemExit(64)
with open(os.environ["MAWF_OPERATOR_AUDIT"], "a", encoding="utf-8") as handle:
    handle.write(json.dumps({"argv": args}, sort_keys=True) + "\\n")
print(json.dumps({
    "finalOk": True,
    "errorCode": None,
    "status": "running",
    "runId": "22222222-2222-4222-8222-222222222222",
    "taskGuid": "acceptance",
}))
""", encoding="utf-8")
            bash.chmod(0o700)
            docker = fake_bin / "docker"
            docker.write_text(
                "#!/bin/sh\nprintf '%s\\n' 8\n",
                encoding="utf-8",
            )
            docker.chmod(0o700)
            environment["PATH"] = str(fake_bin) + os.pathsep + environment["PATH"]
            environment["MAWF_OPERATOR_AUDIT"] = str(audit_path)
        try:
            completed = subprocess.run(
                list(executed_command), shell=False, check=False, text=True,
                capture_output=True, env=environment, timeout=60,
            )
        except subprocess.TimeoutExpired as exc:
            completed = subprocess.CompletedProcess(
                list(executed_command), 124,
                stdout=exc.stdout or "",
                stderr=(exc.stderr or "") + "owner-acceptance-source-timeout:60s\n",
            )
        result = prevention_owner_runtime.ExecutionResult(
            completed.returncode, completed.stdout, completed.stderr
        )
        self.last_result = result
        effect_flag = next(
            (flag for flag in ("--prevention-effect-id", "--effect-id")
             if flag in executed),
            None,
        )
        effect_id = executed[executed.index(effect_flag) + 1] if effect_flag else ""
        self.edge.record_source_result(effect_id, result)
        if (
            self.scenario == "crash-after-source"
            and not self.crash_injected
            and self.edge.has_source_application(effect_id)
        ):
            self.crash_injected = True
            raise SimulatedSourceCrash("crash-after-real-source-effect")
        return result


def _artifact(root: Path, sha256: str) -> dict[str, Any]:
    path = root / "run/prevention/artifacts" / f"{sha256}.json"
    raw = path.read_bytes()
    if sha256_bytes(raw) != sha256:
        raise ProducerError(f"owner-acceptance-artifact-drift:{sha256}")
    return json.loads(raw)


def _registry(edge: AcceptanceSourceEdge) -> prevention_source_probes.SourceEdgeRegistry:
    return prevention_source_probes.SourceEdgeRegistry(
        local_state=edge, git=edge, docker=edge, credential=edge, operator=edge,
    )


def _acceptance_registry_rows(
    executable_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    """Build the isolated proof registry from current materialization, never a stale file."""
    owners = prevention_registry.OwnerRegistry.load(
        prevention_registry.MIGRATION_MANIFEST,
        repository_root=prevention_registry.ROOT,
    )
    contracts, contracts_sha256 = prevention_registry.load_owner_contracts(
        prevention_registry.OWNER_CONTRACTS
    )
    projection = prevention_registry.parse_markdown_projection(
        prevention_registry.MARKDOWN_REGISTRY
    )
    projected = {row["sequence_id"]: row for row in projection}
    executable = {row["owner_sequence_id"]: dict(row) for row in executable_rows}
    rows: list[dict[str, Any]] = []
    for owner in owners.rows:
        human = projected[owner.sequence_id]
        materialized = dict(contracts[owner.sequence_id])
        materialized.setdefault("recurrence_policy", "RECURRENT")
        materialized["registered_host_action_classes"] = sorted(
            prevention_registry.REGISTERED_HOST_ACTION_CLASSES.get(
                owner.sequence_id, frozenset()
            )
        )
        current = executable.get(owner.sequence_id)
        if current is not None:
            materialized["availability_contract_sha256"] = materialized[
                "owner_contract_sha256"
            ]
            materialized["owner_contract_sha256"] = current["owner_contract_sha256"]
            materialized["executable_contract"] = current
            materialized["executable_contract_sha256"] = current["owner_contract_sha256"]
        else:
            materialized["executable_contract"] = None
            materialized["executable_contract_sha256"] = None
        rows.append({
            **human,
            "schema_version": 1,
            "owner_kind": owner.owner_kind.value,
            "handler": owner.handler,
            "parameter_contract": owner.parameter_contract,
            "argv_contract": owner.argv_contract,
            "effect_identity_contract": owner.effect_identity_contract,
            "effect_reconciler": owner.reconciler,
            "terminal_contract": owner.terminal_contract,
            "repository_keys": list(owner.repository_keys),
            "standalone": owner.standalone,
            "parent_sequence_ids": list(owner.parent_sequence_ids),
            "evidence_pointer": owner.evidence_pointer,
            "source_inventory_sha256": owners.source_inventory_sha256,
            **materialized,
        })
    return rows, sha256_bytes(canonical_bytes({
        "schema_version": 1,
        "owner_contracts_sha256": contracts_sha256,
        "executable_rows": list(executable_rows),
        "rows": rows,
    }))


def _seed_parent_delegation(
    journal: PreventionJournal, intent: Any, owner: Mapping[str, Any],
) -> None:
    """Materialize the active parent lifecycle required by a parent-only owner."""
    if owner.get("standalone") is not False:
        return
    parents = tuple(owner.get("parent_sequence_ids", ()))
    if not parents:
        raise ProducerError("owner-acceptance-parent-contract-missing")
    parent_owner = str(parents[0])
    parent_effect_id = sha256_bytes(canonical_bytes({
        "parent_owner_sequence_id": parent_owner,
        "child_intent_id": intent.intent_id,
    }))
    owner_contract_sha256 = "d" * 64
    preparation_sha256 = "f" * 64
    transition = journal.append("transition_prepared", {
        "journal_id": "acceptance-parent-journal",
        "transition": "EFFECT_PREPARED", "state_hash": "1" * 64,
    })
    prepared = journal.append("effect_prepared", {
        "journal_id": "acceptance-parent-journal",
        "effect_id": parent_effect_id, "idempotency_key": "2" * 64,
        "effect_kind": "OWNER_INVOCATION", "owner_sequence_id": parent_owner,
        "implementation_id": "3" * 64,
        "effect_task_id": journal.ownership.task_id,
        "effect_run_id": journal.ownership.run_id,
        "effect_branch_ref": journal.ownership.branch_ref,
        "effect_worktree_id": journal.ownership.worktree_id,
        "transition_prepared_event_id": transition["event_id"],
        "owner_contract_sha256": owner_contract_sha256,
        "reconciler_sha256": "e" * 64,
        "preparation_artifact_sha256": preparation_sha256,
    })
    reconciled = journal.append("effect_reconciled", {
        "journal_id": "acceptance-parent-journal",
        "effect_id": parent_effect_id, "prepared_event_id": prepared["event_id"],
        "attempt_generation": 0,
        "owner_contract_sha256": owner_contract_sha256,
        "reconciler_sha256": "e" * 64,
        "preparation_artifact_sha256": preparation_sha256,
        "reconciliation": "NOT_APPLIED",
        "reconciliation_artifact_sha256": "4" * 64,
        "observable_ownership_sha256": "5" * 64,
        "evidence_sha256": "6" * 64,
    })
    authorized = journal.append("effect_execution_authorized", {
        "journal_id": "acceptance-parent-journal",
        "effect_id": parent_effect_id, "attempt_generation": 1,
        "prior_generation": 0,
        "not_applied_reconciliation_event_id": reconciled["event_id"],
        "owner_contract_sha256": owner_contract_sha256,
        "authorization_sha256": "7" * 64,
    })
    journal.append("effect_execution_started", {
        "journal_id": "acceptance-parent-journal",
        "effect_id": parent_effect_id, "attempt_generation": 1,
        "execution_authorized_event_id": authorized["event_id"],
        "owner_contract_sha256": owner_contract_sha256,
    })
    parameters = intent.parameter_map()
    journal.append("child_delegation_recorded", {
        "delegation_id": parameters["delegation_id"].value,
        "parent_effect_id": parent_effect_id,
        "parent_owner_sequence_id": parent_owner,
        "child_owner_sequence_id": intent.requested_sequence_id,
        "child_intent_id": intent.intent_id,
        "blocker_id": "blk-owner-acceptance-parent",
        "verification_event_id": "00000000-0000-4000-8000-000000000002",
        "mode": parameters["mode"].value,
    })


def execute_case(
    owner_id: str, profile: str, *, scenario: str = "positive",
) -> dict[str, Any]:
    materialized_contracts = materialize()
    contracts = materialized_contracts["owners"]
    contracts_by_owner = {
        row["owner_sequence_id"]: row for row in contracts
    }
    cases, case_registry_sha256 = load_case_registry(contracts)
    case = next((
        row for row in cases
        if row["owner_sequence_id"] == owner_id and row["profile_id"] == profile
    ), None)
    if case is None:
        raise ProducerError(f"owner-acceptance-case-unavailable:{owner_id}:{profile}")
    registry_rows, _ = _acceptance_registry_rows(contracts)
    owner = next((row for row in registry_rows if row["sequence_id"] == owner_id), None)
    if owner is None:
        raise ProducerError(f"owner-registry-row-unavailable:{owner_id}")
    with tempfile.TemporaryDirectory(prefix="prevention-owner-acceptance-") as raw:
        root = Path(raw)
        prevention_source_receipt.ROOT = root / "source-receipts"
        mirror_contract_path = (
            ensure_memory_mirror(root)
            / "Tasks/prevention-system-completion/owner-executable-contracts.json"
        )
        mirror_contract_path.write_bytes(canonical_bytes(
            materialized_contracts,
        ))
        intent = intent_for(
            owner, profile, root, proof_kind="controller_runtime_positive",
            executable_contracts=contracts_by_owner,
        )
        ownership = JournalOwnership(
            task_id=intent.task_id, run_id=intent.run_id,
            branch_ref=f"task/{intent.task_id}",
            worktree_id=sha256_bytes(canonical_bytes({
                "owner": owner_id, "profile": profile, "scenario": scenario,
            })),
        )
        journal = PreventionJournal(root / "run", ownership)
        _seed_parent_delegation(journal, intent, owner)
        edge = AcceptanceSourceEdge(
            root=root, scenario=scenario,
            owner_sequence_id=owner_id, profile_id=profile,
            allowed_routes=frozenset(
                (str(row["owner_sequence_id"]), str(row["profile_id"]))
                for row in cases
            ),
        )
        executor = RealSourceExecutor(edge, root, scenario=scenario)
        authority = prevention_controller.ContractAcceptanceAuthority(
            task_id=intent.task_id, run_id=intent.run_id,
            intent_id=intent.intent_id, owner_sequence_id=owner_id,
            owner_contract_sha256=owner["owner_contract_sha256"],
            profile_id=profile, proof_kind=(
                "controller_runtime_semantic_negative"
                if scenario == "semantic-negative"
                else "controller_runtime_positive"
            ),
            case_registry_sha256=case_registry_sha256,
        )
        controller = prevention_controller.PreventionController.for_contract_acceptance(
            journal, authority, registry_rows=registry_rows,
            acceptance_budget_producer=AcceptanceBudgetProducer(
                root,
                executable_contracts={
                    row["sequence_id"]: row["executable_contract"]
                    for row in registry_rows
                    if row.get("executable_contract") is not None
                },
            ),
            budget_authority=prevention_budget.BudgetAuthority(
                journal, {"duration_milliseconds": 31_536_000_000}
            ),
            owner_runner=executor, owner_source_edges=_registry(edge),
            owner_binding_provider=AcceptanceBindingProvider(root),
            delegation_verifier=lambda _event_id, _blocker_id: True,
        )
        failure = None
        acceptance_observable_path = root / "owner-observable-evidence.json"
        acceptance_observable_path.write_bytes(canonical_bytes(
            prevention_observable_materializer.materialize()
        ))
        original_observable_path = prevention_adapters.OBSERVABLE_EVIDENCE
        prevention_adapters.OBSERVABLE_EVIDENCE = acceptance_observable_path
        try:
            try:
                result = controller.execute(intent)
            except (prevention_owner_runtime.OwnerRuntimeError, SimulatedSourceCrash) as exc:
                result = {"status": "NONTERMINAL_REJECTED"}
                failure = str(exc)
            if scenario == "crash-after-source":
                if failure != "crash-after-real-source-effect":
                    raise ProducerError(
                        f"owner-crash-source-did-not-reach-effect:{owner_id}:{profile}:"
                        f"{failure}:command={executor.executed_commands[-1:]!r}:"
                        f"source={executor.last_result}"
                    )
                result = controller.execute(intent)
                failure = None
        finally:
            prevention_adapters.OBSERVABLE_EVIDENCE = original_observable_path
        events, ledger_sha256 = journal.replay()
        if scenario == "positive" and result.get("status") != "TERMINAL":
            raise ProducerError(
                f"owner-positive-source-not-terminal:{owner_id}:{profile}:"
                f"{result}:failure={failure}:"
                f"command={executor.executed_commands[-1:]!r}:"
                f"source={executor.last_result}"
            )
        effect = result.get("effect") if isinstance(result, Mapping) else None
        prepared_event = next((
            event for event in events
            if event["event_type"] == "effect_prepared"
            and event.get("owner_sequence_id") == owner_id
        ), None)
        if not isinstance(effect, Mapping) and prepared_event is not None:
            effect = {
                "effect_id": prepared_event["effect_id"],
                "preparation_artifact_sha256": prepared_event[
                    "preparation_artifact_sha256"
                ]
            }
        persisted: dict[str, Any] = {}
        if isinstance(effect, Mapping):
            preparation_sha = str(effect["preparation_artifact_sha256"])
            persisted["preparation"] = {
                "sha256": preparation_sha,
                "payload": _artifact(root, preparation_sha),
            }
            reconciliation = next((
                event for event in events
                if event["event_type"] == "effect_reconciled"
                and event.get("effect_id") == effect.get("effect_id")
            ), None)
            if reconciliation is not None:
                reconciliation_sha = str(
                    reconciliation["reconciliation_artifact_sha256"]
                )
                persisted["reconciliation"] = {
                    "sha256": reconciliation_sha,
                    "payload": _artifact(root, reconciliation_sha),
                }
            terminal_event = next((
                event for event in events
                if event["event_type"] == "owner_terminal"
                and event.get("owner_sequence_id") == owner_id
            ), None)
            if terminal_event is not None:
                terminal_sha = str(terminal_event["terminal_artifact_sha256"])
                evidence = _artifact(
                    root, str(terminal_event["terminal_evidence_sha256"])
                )
                persisted["terminal"] = {
                    "sha256": terminal_sha,
                    "payload": _artifact(root, terminal_sha),
                    "evidence": evidence,
                }
                if edge.envelopes:
                    envelope = edge.envelopes[-1]
                    persisted["source_capture"] = {
                        "sha256": sha256_bytes(canonical_bytes(envelope)),
                        "payload": dict(envelope),
                    }
            elif edge.envelopes:
                envelope = edge.envelopes[-1]
                persisted["source_capture"] = {
                    "sha256": sha256_bytes(canonical_bytes(envelope)),
                    "payload": dict(envelope),
                }
        delegated_python_paths: list[str] = []
        greenfield_audit = root / "greenfield-python-audit.jsonl"
        if greenfield_audit.exists():
            delegated_python_paths = [
                json.loads(line)["script"]
                for line in greenfield_audit.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        operator_commands: list[list[str]] = []
        mawf_operator_audit = root / "mawf-operator-audit.jsonl"
        if mawf_operator_audit.exists():
            operator_commands = [
                json.loads(line)["argv"]
                for line in mawf_operator_audit.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        credential_os_operations: list[str] = []
        credential_audit = root / "claude-auth-security-audit.jsonl"
        if credential_audit.exists():
            credential_os_operations = [
                json.loads(line)["operation"]
                for line in credential_audit.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        return {
            "case_id": case["case_id"], "owner_sequence_id": owner_id,
            "profile_id": profile, "scenario": scenario,
            "result": result, "journal_events": events,
            "journal_sha256": ledger_sha256,
            "commands": [list(command) for command in executor.commands],
            "executed_commands": [
                list(command) for command in executor.executed_commands
            ],
            "capture_count": len(edge.captures or []),
            "delegated_python_paths": delegated_python_paths,
            "operator_commands": operator_commands,
            "credential_os_operations": credential_os_operations,
            "artifacts": persisted, "failure": failure,
        }


def _wrapped(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {"applicable": False}
    return {
        "applicable": True, "sha256": value["sha256"],
        "payload": value["payload"],
    }


def write_positive_traces(owner_id: str, profile: str) -> list[str]:
    execution = execute_case(owner_id, profile, scenario="positive")
    contracts = materialize()["owners"]
    owner = next(row for row in contracts if row["owner_sequence_id"] == owner_id)
    commands = execution["commands"]
    expected_commands = 2 if owner_id == "convergence-checkpoint-run" else 1
    if len(commands) != expected_commands:
        raise ProducerError("owner-acceptance-runner-command-count-invalid")
    bindings = lambda path: {
        "path": str(path), "sha256": sha256_bytes(Path(path).read_bytes()),
    }
    source_bindings = [
        {"path": item["path"], "sha256": item["sha256"]}
        for item in owner["implementation_sources"]
    ]
    artifacts = execution["artifacts"]
    common = {
        "schema_version": 1, "owner_sequence_id": owner_id,
        "profile_id": profile, "case_id": execution["case_id"],
        "applicability": "REQUIRED",
        "acceptance_contract_sha256": owner["acceptance_contract_sha256"],
        "parameter_policy_sha256": owner["parameter_contract"]["policy_sha256"],
        "reconciliation_policy_sha256": owner["reconciliation_contract"]["policy_sha256"],
        "terminal_policy_sha256": owner["terminal_contract"]["policy_sha256"],
        "source_bindings": source_bindings,
        "test_bindings": [
            bindings(prevention_owner_acceptance.PRODUCER_PATH),
            bindings(prevention_owner_acceptance.FIXTURES_PATH),
        ],
        "provider_implementation_sha256": sha256_bytes(
            prevention_owner_acceptance.PROVIDER_PATH.read_bytes()
        ),
        "production_backend_id": "PRODUCTION_SOURCE_PROBE_V1",
        "source_edge_kind": next(
            spec.edge_kind.value for key, spec in prevention_source_probes.PROVIDER_SPECS.items()
            if key == (owner_id, profile)
        ),
        "runner_command_sha256": sha256_bytes(canonical_bytes(commands[0])),
        "journal_events": execution["journal_events"],
        "journal_events_sha256": sha256_bytes(canonical_bytes(execution["journal_events"])),
        "artifacts": {
            "preparation": _wrapped(artifacts.get("preparation")),
            "reconciliation": _wrapped(artifacts.get("reconciliation")),
            "source_capture": _wrapped(artifacts.get("source_capture")),
            "terminal": _wrapped(artifacts.get("terminal")),
        },
    }
    references = []
    for proof_kind in (
        "controller_runtime_positive", "terminal_semantics",
        "production_source_probe_backend",
    ):
        outcome = prevention_owner_acceptance.PROOF_OUTCOMES[proof_kind]
        references.append(prevention_owner_acceptance.write_trace({
            **common, "proof_kind": proof_kind,
            "expected_outcome": outcome, "observed_outcome": outcome,
        }))
    return references


def write_negative_trace(owner_id: str, profile: str) -> str:
    execution = execute_case(owner_id, profile, scenario="semantic-negative")
    if execution["result"]["status"] != "NONTERMINAL_REJECTED":
        raise ProducerError("owner-negative-source-was-not-rejected")
    contracts = materialize()["owners"]
    owner = next(row for row in contracts if row["owner_sequence_id"] == owner_id)
    commands = execution["commands"]
    expected_commands = 2 if owner_id == "convergence-checkpoint-run" else 1
    if len(commands) != expected_commands:
        raise ProducerError("owner-acceptance-runner-command-count-invalid")
    binding = lambda path: {
        "path": str(path), "sha256": sha256_bytes(Path(path).read_bytes()),
    }
    artifacts = execution["artifacts"]
    trace = {
        "schema_version": 1, "owner_sequence_id": owner_id,
        "profile_id": profile,
        "proof_kind": "controller_runtime_semantic_negative",
        "case_id": execution["case_id"], "applicability": "REQUIRED",
        "acceptance_contract_sha256": owner["acceptance_contract_sha256"],
        "parameter_policy_sha256": owner["parameter_contract"]["policy_sha256"],
        "reconciliation_policy_sha256": owner["reconciliation_contract"]["policy_sha256"],
        "terminal_policy_sha256": owner["terminal_contract"]["policy_sha256"],
        "source_bindings": [
            {"path": item["path"], "sha256": item["sha256"]}
            for item in owner["implementation_sources"]
        ],
        "test_bindings": [
            binding(prevention_owner_acceptance.PRODUCER_PATH),
            binding(prevention_owner_acceptance.FIXTURES_PATH),
        ],
        "provider_implementation_sha256": sha256_bytes(
            prevention_owner_acceptance.PROVIDER_PATH.read_bytes()
        ),
        "production_backend_id": "PRODUCTION_SOURCE_PROBE_V1",
        "source_edge_kind": prevention_source_probes.PROVIDER_SPECS[
            (owner_id, profile)
        ].edge_kind.value,
        "runner_command_sha256": sha256_bytes(canonical_bytes(commands[0])),
        "journal_events": execution["journal_events"],
        "journal_events_sha256": sha256_bytes(canonical_bytes(execution["journal_events"])),
        "artifacts": {
            "preparation": _wrapped(artifacts.get("preparation")),
            "reconciliation": _wrapped(artifacts.get("reconciliation")),
            "source_capture": _wrapped(artifacts.get("source_capture")),
            "terminal": {"applicable": False},
        },
        "expected_outcome": "NONTERMINAL_REJECTED",
        "observed_outcome": "NONTERMINAL_REJECTED",
    }
    return prevention_owner_acceptance.write_trace(trace)


def write_crash_traces(owner_id: str, profile: str) -> list[str]:
    execution = execute_case(owner_id, profile, scenario="crash-after-source")
    if execution["result"].get("status") != "TERMINAL":
        raise ProducerError("owner-crash-recovery-not-terminal")
    contracts = materialize()["owners"]
    owner = next(row for row in contracts if row["owner_sequence_id"] == owner_id)
    commands = execution["commands"]
    expected_commands = 2 if owner_id == "convergence-checkpoint-run" else 1
    if len(commands) != expected_commands:
        raise ProducerError("owner-crash-duplicated-source-execution")
    binding = lambda path: {
        "path": str(path), "sha256": sha256_bytes(Path(path).read_bytes()),
    }
    artifacts = execution["artifacts"]
    common = {
        "schema_version": 1, "owner_sequence_id": owner_id,
        "profile_id": profile, "case_id": execution["case_id"],
        "applicability": "REQUIRED",
        "acceptance_contract_sha256": owner["acceptance_contract_sha256"],
        "parameter_policy_sha256": owner["parameter_contract"]["policy_sha256"],
        "reconciliation_policy_sha256": owner["reconciliation_contract"]["policy_sha256"],
        "terminal_policy_sha256": owner["terminal_contract"]["policy_sha256"],
        "source_bindings": [
            {"path": item["path"], "sha256": item["sha256"]}
            for item in owner["implementation_sources"]
        ],
        "test_bindings": [
            binding(prevention_owner_acceptance.PRODUCER_PATH),
            binding(prevention_owner_acceptance.FIXTURES_PATH),
        ],
        "provider_implementation_sha256": sha256_bytes(
            prevention_owner_acceptance.PROVIDER_PATH.read_bytes()
        ),
        "production_backend_id": "PRODUCTION_SOURCE_PROBE_V1",
        "source_edge_kind": prevention_source_probes.PROVIDER_SPECS[
            (owner_id, profile)
        ].edge_kind.value,
        "runner_command_sha256": sha256_bytes(canonical_bytes(commands[0])),
        "journal_events": execution["journal_events"],
        "journal_events_sha256": sha256_bytes(canonical_bytes(execution["journal_events"])),
        "artifacts": {
            "preparation": _wrapped(artifacts.get("preparation")),
            "reconciliation": _wrapped(artifacts.get("reconciliation")),
            "source_capture": _wrapped(artifacts.get("source_capture")),
            "terminal": _wrapped(artifacts.get("terminal")),
        },
    }
    references = []
    for proof_kind in ("crash_reconciliation", "effect_identity_source_binding"):
        outcome = prevention_owner_acceptance.PROOF_OUTCOMES[proof_kind]
        references.append(prevention_owner_acceptance.write_trace({
            **common, "proof_kind": proof_kind,
            "expected_outcome": outcome, "observed_outcome": outcome,
        }))
    return references


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner")
    parser.add_argument("--profile")
    parser.add_argument(
        "--all-current",
        action="store_true",
        help=(
            "Regenerate all mechanically required traces for the current "
            "materialized owner/profile contracts."
        ),
    )
    parser.add_argument(
        "--scenario", choices=(
            "positive", "semantic-negative", "crash-after-source",
        ),
        default="positive",
    )
    parser.add_argument("--write-traces", action="store_true")
    args = parser.parse_args(argv)
    if args.all_current:
        if args.owner or args.profile or args.write_traces:
            parser.error("--all-current cannot be combined with owner/profile/write-traces")
        trace_count = 0
        profile_count = 0
        for owner in materialize()["owners"]:
            owner_id = owner["owner_sequence_id"]
            profiles = sorted({
                spec["profile"]
                for spec in owner["reconciliation_contract"]["observables"]
            })
            for profile in profiles:
                references = [
                    *write_positive_traces(owner_id, profile),
                    write_negative_trace(owner_id, profile),
                    *write_crash_traces(owner_id, profile),
                ]
                trace_count += len(references)
                profile_count += 1
                print(json.dumps({
                    "ok": True,
                    "owner_sequence_id": owner_id,
                    "profile_id": profile,
                    "trace_count": len(references),
                }, sort_keys=True), flush=True)
        print(json.dumps({
            "ok": True,
            "owner_count": len(materialize()["owners"]),
            "profile_count": profile_count,
            "trace_count": trace_count,
        }, sort_keys=True))
        return 0
    if not args.owner or not args.profile:
        parser.error("--owner and --profile are required unless --all-current is used")
    if args.write_traces:
        if args.scenario == "positive":
            references = write_positive_traces(args.owner, args.profile)
        elif args.scenario == "semantic-negative":
            references = [write_negative_trace(args.owner, args.profile)]
        else:
            references = write_crash_traces(args.owner, args.profile)
        print(json.dumps({
            "ok": True, "owner_sequence_id": args.owner,
            "profile_id": args.profile, "trace_count": len(references),
            "trace_sha256s": references,
        }, sort_keys=True))
        return 0
    result = execute_case(args.owner, args.profile, scenario=args.scenario)
    print(json.dumps({
        "ok": True, "owner_sequence_id": result["owner_sequence_id"],
        "profile_id": result["profile_id"], "scenario": result["scenario"],
        "status": result["result"]["status"],
        "event_count": len(result["journal_events"]),
        "capture_count": result["capture_count"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
