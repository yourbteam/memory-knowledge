#!/usr/bin/env python3
"""Build registered sequence invocations from semantic intake answers."""

from __future__ import annotations

import json
import hashlib
from collections.abc import Callable, Mapping
from copy import deepcopy
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

try:
    from scripts import script_intake
except ModuleNotFoundError:  # direct script execution
    import script_intake


class AdapterError(ValueError):
    """A semantic answer set cannot produce a canonical invocation."""


class AdapterUnavailable(AdapterError):
    """The registered sequence has no implemented local adapter yet."""


SCOPED_GIT_PUBLISH_SCRIPT = str(
    Path(__file__).with_name("scoped_git_publish.py").resolve()
)


CANONICAL_SEQUENCE_IDS = (
    "local-workflow-orch-image",
    "greenfield-full-drive",
    "remote-mcp-user-onboarding",
    "taggable-source-reload",
    "mawf-playbook-full-test",
    "mawf-playbook-speed-test",
    "mawf-playbook-blocker-reentry",
    "github-app-repos-refresh",
    "claude-auth-token-refresh",
    "taggable-api-deploy",
    "taggable-admin-spa-deploy",
    "taggable-media-worker-deploy",
    "airgapped-local-bulgarian-stt",
    "airgapped-redaction-stack",
    "callcenter-harness-provision-verify",
    "airgapped-llm-judge",
    "secure-landing-seed",
    "callcenter-harness-engine-invariants",
    "discovery-promotion-lifecycle",
    "commit-push-main",
    "discovery-bootstrap",
    "discovery-candidate-reconciliation",
    "blocker-backlog-reconciliation",
    "convergence-checkpoint-run",
    "scoped-context-edit",
    "convergence-state-review-cycle",
    "greenfield-recreate-resume",
    "workflow-resume-from-phase-live-confirmation",
)

COMMIT_PUSH_OPERATIONS = (
    "dry-run",
    "publish",
    "resume-push",
    "integrate-remote-and-resume",
    "isolated-integrate-and-resume",
    "isolated-reconcile-and-resume",
)
MANIFEST_OPERATIONS = frozenset(COMMIT_PUSH_OPERATIONS) - {"resume-push"}
MESSAGE_OPERATIONS = frozenset({
    "dry-run", "publish", "isolated-integrate-and-resume",
    "isolated-reconcile-and-resume",
})
RESUME_OPERATIONS = frozenset(COMMIT_PUSH_OPERATIONS) - {"dry-run", "publish"}
OVERLAY_OPERATIONS = frozenset({
    "isolated-integrate-and-resume", "isolated-reconcile-and-resume",
})
WORK_MEMORY_EVENTS_PATH = "operations/work-memory/events." + "jsonl"


COMMIT_PUSH_SPEC = {
    "schema_version": script_intake.SCHEMA_VERSION,
    "fields": [
        {
            "id": "operation",
            "prompt": "Commit and push operation",
            "response_format": "One named operation.",
            "example": "dry-run",
            "constraints": "Choose the operation matching the approved Git effect.",
            "type": "choice",
            "choices": list(COMMIT_PUSH_OPERATIONS),
            "required": True,
        },
        {
            "id": "repository_key",
            "prompt": "Repository",
            "response_format": "One registered repository name.",
            "example": "memory-knowledge",
            "constraints": "Choose exactly one repository from the registered values.",
            "type": "choice",
            "choices": ["memory-knowledge"],
            "required": True,
        },
        {
            "id": "approved_paths",
            "prompt": "Approved repository paths",
            "response_format": "One or more repository-relative file paths.",
            "example": "scripts/script_intake.py",
            "constraints": "Include files only; no directories, absolute paths, or parent traversal.",
            "type": "string_list",
            "item_prompt": "Approved repository-relative file path",
            "item_response_format": "One repository-relative file path.",
            "item_example": "tests/test_script_intake.py",
            "item_constraints": "No absolute path, directory shorthand, or parent traversal.",
            "when": {"field": "operation", "in": sorted(MANIFEST_OPERATIONS)},
        },
        {
            "id": "overlay_paths",
            "prompt": "Approved overlay paths",
            "response_format": "One or more repository-relative file paths.",
            "example": "scripts/script_intake.py",
            "constraints": "Every overlay file must also be in the approved path set.",
            "type": "string_list",
            "item_prompt": "Approved overlay repository-relative file path",
            "item_response_format": "One repository-relative file path.",
            "item_example": "scripts/script_intake.py",
            "item_constraints": "No absolute path, directory shorthand, or parent traversal.",
            "when": {"field": "operation", "in": sorted(OVERLAY_OPERATIONS)},
        },
        {
            "id": "message",
            "prompt": "Commit message",
            "response_format": "A subject line, then any body paragraphs on the lines after it.",
            "example": "Add deterministic sequence intake",
            "constraints": "Describe the change and why it was made; do not provide an invocation.",
            "type": "text",
            "required": True,
            "when": {"field": "operation", "in": sorted(MESSAGE_OPERATIONS)},
        },
        {
            "id": "branch",
            "prompt": "Target branch",
            "response_format": "One Git branch name.",
            "example": "main",
            "constraints": "Use the approved target branch name.",
            "type": "string",
            "default": "main",
        },
        {
            "id": "remote",
            "prompt": "Target remote",
            "response_format": "One configured Git remote name.",
            "example": "origin",
            "constraints": "Use the approved repository remote name.",
            "type": "string",
            "default": "origin",
        },
        {
            "id": "resume_commit",
            "prompt": "Existing local commit",
            "response_format": "One full Git commit identifier.",
            "example": "0123456789abcdef0123456789abcdef01234567",
            "constraints": "Use the exact existing HEAD commit approved for resume.",
            "type": "string",
            "required": True,
            "when": {"field": "operation", "in": sorted(RESUME_OPERATIONS)},
        },
        {
            "id": "ledger_path",
            "prompt": "Canonical work-memory ledger path",
            "response_format": "One repository-relative file path.",
            "example": WORK_MEMORY_EVENTS_PATH,
            "constraints": "Use the canonical append-only work-memory ledger.",
            "type": "path",
            "default": WORK_MEMORY_EVENTS_PATH,
            "when": {
                "field": "operation",
                "equals": "isolated-reconcile-and-resume",
            },
        },
        {
            "id": "generated_view_path",
            "prompt": "Generated blocker view path",
            "response_format": "One repository-relative file path.",
            "example": "operations/blockers/BLOCKERS.md",
            "constraints": "Use the generated blocker catalog view paired with the ledger.",
            "type": "path",
            "default": "operations/blockers/BLOCKERS.md",
            "when": {
                "field": "operation",
                "equals": "isolated-reconcile-and-resume",
            },
        },
    ],
}

DEPLOY_SEQUENCE_CONFIG = {
    "taggable-api-deploy": {
        "script": "scripts/deploy-api.sh",
        "repository_example": "taggable-api",
    },
    "taggable-admin-spa-deploy": {
        "script": "scripts/deploy-admin-spa.sh",
        "repository_example": "taggable-admin-spa",
        "api_base": "https://taggable-api-dev.azurewebsites.net/api",
    },
    "taggable-media-worker-deploy": {
        "script": "scripts/deploy-media-worker.sh",
        "repository_example": "taggable-api",
    },
}


def _deploy_spec(sequence_id: str) -> dict[str, Any]:
    config = DEPLOY_SEQUENCE_CONFIG[sequence_id]
    fields: list[dict[str, Any]] = [
        {
            "id": "repository_key",
            "prompt": "Source repository to deploy",
            "response_format": "One registered repository name.",
            "example": config["repository_example"],
            "constraints": "Choose the checkout whose current contents are approved for deployment.",
            "type": "choice",
            "choices": [config["repository_example"]],
            "required": True,
        },
    ]
    if "api_base" in config:
        fields.append({
            "id": "api_base",
            "prompt": "API base URL baked into the SPA",
            "response_format": "One absolute HTTPS URL ending in /api.",
            "example": config["api_base"],
            "constraints": "Press Enter for the displayed dev default; do not add quotes or flags.",
            "type": "string",
            "default": config["api_base"],
        })
    fields.append({
        "id": "verify",
        "prompt": "Run the script's post-deploy verification",
        "response_format": "Answer yes or no.",
        "example": "yes",
        "constraints": "Use yes unless an approved recovery explicitly requires skipping verification.",
        "type": "boolean",
        "default": True,
    })
    return {"schema_version": script_intake.SCHEMA_VERSION, "fields": fields}


DEPLOY_SPECS = {
    sequence_id: _deploy_spec(sequence_id)
    for sequence_id in DEPLOY_SEQUENCE_CONFIG
}

LOCAL_IMAGE_OPERATIONS = (
    "build", "run", "health", "copy-code-project", "logs", "stop",
    "seed-codex-auth", "seed-git-auth", "probe-codex",
    "require-real-memory-knowledge",
)
GREENFIELD_MODES = (
    "start-from-spec", "create-program", "resume-program", "validate-fresh",
)
CLAUDE_AUTH_OPERATIONS = (
    "status", "mint", "seed-local", "seed-host", "push-kv",
    "reseed-azure", "verify", "all",
)


def _semantic_field(
    field_id: str,
    prompt: str,
    response_format: str,
    example: str,
    constraints: str,
    field_type: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "id": field_id,
        "prompt": prompt,
        "response_format": response_format,
        "example": example,
        "constraints": constraints,
        "type": field_type,
        **extra,
    }


LOCAL_IMAGE_SPEC = {
    "schema_version": script_intake.SCHEMA_VERSION,
    "fields": [
        _semantic_field(
            "operation", "Local image operation", "One named operation.",
            "health", "Choose the intended local image lifecycle action.",
            "choice", choices=list(LOCAL_IMAGE_OPERATIONS), required=True,
        ),
        _semantic_field(
            "source_repository_key", "Harness repository",
            "One registered repository name.", "mcp-agents-workflow",
            "Choose the repository containing the checked-in image harness.",
            "choice", choices=["mcp-agents-workflow"], required=True,
        ),
        _semantic_field(
            "tag", "Docker image tag", "One image name and tag.",
            "workflow-orch:local-sequence-check",
            "Do not provide docker syntax or additional arguments.", "string",
            required=True, when={"field": "operation", "in": ["build", "run"]},
        ),
        _semantic_field(
            "container", "Container name", "One container resource name.",
            "workflow-orch-local-sequence-check",
            "Use the registered or approved local container name.", "string",
            required=True,
            when={"field": "operation", "in": [
                "run", "copy-code-project", "logs", "stop", "seed-codex-auth",
                "seed-git-auth", "probe-codex",
            ]},
        ),
        _semantic_field(
            "port", "Preferred host port", "One whole-number TCP port.",
            "18082", "Use a value from 1 through 65535.", "integer",
            minimum=1, maximum=65535, required=True,
            when={"field": "operation", "equals": "run"},
        ),
        _semantic_field(
            "port_file", "Port record path",
            "One filesystem path, or press Enter to omit it.",
            "/private/tmp/workflow-orch-local.port",
            "The harness writes the selected host port here.", "path",
            when={"field": "operation", "equals": "run"},
        ),
        _semantic_field(
            "env_file", "Runtime environment file",
            "One existing filesystem path.",
            "/private/tmp/workflow-orch-local.env",
            "Provide a path handle only; never paste secret contents.", "path",
            required=True, when={"field": "operation", "equals": "run"},
        ),
        _semantic_field(
            "health_location", "Health target source",
            "One target-source name.", "port-file",
            "Choose whether health resolves the endpoint from a port number or a port file.",
            "choice", choices=["port", "port-file"], required=True,
            when={"field": "operation", "equals": "health"},
        ),
        _semantic_field(
            "health_port", "Health-check host port",
            "One whole-number TCP port.", "18082",
            "Use a value from 1 through 65535.", "integer",
            minimum=1, maximum=65535, required=True,
            when={"field": "health_location", "equals": "port"},
        ),
        _semantic_field(
            "health_port_file", "Health-check port record",
            "One existing filesystem path.",
            "/private/tmp/workflow-orch-local.port",
            "The file must contain the selected host port.", "path",
            required=True,
            when={"field": "health_location", "equals": "port-file"},
        ),
        _semantic_field(
            "timeout_seconds", "Health timeout in seconds",
            "One positive whole number.", "180",
            "Use a value from 1 through 3600.", "integer",
            default=180, minimum=1, maximum=3600,
            when={"field": "operation", "equals": "health"},
        ),
        _semantic_field(
            "code_repository_key", "Code repository to copy",
            "One registered repository name.", "memory-knowledge",
            "Choose the source checkout copied into the container.", "choice",
            choices=["memory-knowledge"], required=True,
            when={"field": "operation", "equals": "copy-code-project"},
        ),
        _semantic_field(
            "source_relative_path", "Source directory within that repository",
            "One repository-relative directory path.", ".",
            "Press Enter for the repository root; no parent traversal.", "path",
            default=".",
            when={"field": "operation", "equals": "copy-code-project"},
        ),
        _semantic_field(
            "destination", "Container workspace destination",
            "One absolute container directory.", "/workspaces",
            "Press Enter for the displayed workspace default.", "path",
            default="/workspaces",
            when={"field": "operation", "equals": "copy-code-project"},
        ),
        _semantic_field(
            "tail", "Log line count",
            "One positive whole number, or press Enter for the script default.",
            "200", "Do not add units.", "integer", minimum=1,
            when={"field": "operation", "equals": "logs"},
        ),
        _semantic_field(
            "keyvault_name", "Azure Key Vault resource name",
            "One registered vault name.", "hrness",
            "Provide the resource name only, never credential content.", "string",
            required=True,
            when={"field": "operation", "in": [
                "seed-codex-auth", "seed-git-auth",
            ]},
        ),
        _semantic_field(
            "git_repository_key", "Git repository credential target",
            "One registered repository name.", "memory-knowledge",
            "Choose the repository whose Git credential is seeded.", "choice",
            choices=["mcp-agents-workflow", "memory-knowledge"], required=True,
            when={"field": "operation", "equals": "seed-git-auth"},
        ),
        _semantic_field(
            "seed_port_file", "Post-seed health port record",
            "One existing filesystem path.",
            "/private/tmp/workflow-orch-local.port",
            "The restart health check resolves its port from this file.", "path",
            required=True,
            when={"field": "operation", "equals": "seed-git-auth"},
        ),
        _semantic_field(
            "seed_timeout_seconds", "Post-seed health timeout in seconds",
            "One positive whole number.", "180",
            "Use a value from 1 through 3600.", "integer",
            default=180, minimum=1, maximum=3600,
            when={"field": "operation", "equals": "seed-git-auth"},
        ),
    ],
}

GREENFIELD_SPEC = {
    "schema_version": script_intake.SCHEMA_VERSION,
    "fields": [
        _semantic_field(
            "mode", "Greenfield drive mode", "One named drive mode.",
            "start-from-spec",
            "Choose the durable behavior to perform; do not provide script flags.",
            "choice", choices=list(GREENFIELD_MODES), required=True,
        ),
        _semantic_field(
            "source_repository_key", "Greenfield driver repository",
            "One registered repository name.", "mcp-agents-workflow",
            "Choose the repository containing the checked-in greenfield driver.",
            "choice", choices=["mcp-agents-workflow"], required=True,
        ),
        _semantic_field(
            "target_repository", "Target remote repository",
            "One registered repository alias or owner/name identifier.",
            "thebteambg/supermariobros",
            "Provide only the target repository identity.", "string", required=True,
        ),
        _semantic_field(
            "branch", "Target branch", "One Git branch name.",
            "main", "Press Enter for main; do not provide Git arguments.", "string",
            default="main",
        ),
        _semantic_field(
            "tag", "Local image label", "One image label.", "gf-local",
            "Press Enter for the displayed default.", "string", default="gf-local",
        ),
        _semantic_field(
            "container", "Local container name", "One container resource name.",
            "workflow-orch-local-sequence-check",
            "Press Enter for the registered default.", "string",
            default="workflow-orch-local-sequence-check",
        ),
        _semantic_field(
            "port", "Preferred host port", "One whole-number TCP port.",
            "18082", "Use a value from 1 through 65535.", "integer",
            default=18082, minimum=1, maximum=65535,
        ),
        _semantic_field(
            "env_file", "Operator environment file",
            "One existing filesystem path.",
            "/private/tmp/workflow-orch-local-real-mk.env",
            "Provide a path handle only; never paste secret values.", "path",
            required=True,
        ),
        _semantic_field(
            "skip_build", "Reuse an already verified local image",
            "Answer yes or no.", "no",
            "Answer yes only when the approved image-verification precondition holds.",
            "boolean", default=False,
        ),
        _semantic_field(
            "skip_auth", "Reuse already verified runtime authentication",
            "Answer yes or no.", "no",
            "Answer yes only when live Codex and Git capability probes already pass.",
            "boolean", default=False,
        ),
        _semantic_field(
            "keyvault_name", "Azure Key Vault resource name",
            "One registered vault name.", "hrness",
            "Provide the resource name only, never secret content.", "string",
            default="hrness", when={"field": "skip_auth", "equals": False},
        ),
        _semantic_field(
            "fresh", "Request a fresh N1 evaluation",
            "Answer yes or no.", "yes",
            "This applies to the start-from-spec profile.", "boolean",
            default=True, when={"field": "mode", "equals": "start-from-spec"},
        ),
        _semantic_field(
            "start_feature_index", "First feature index to drive",
            "One whole number from 0 through 19.", "0",
            "Press Enter to start at the first feature.", "integer",
            default=0, minimum=0, maximum=19,
        ),
        _semantic_field(
            "parallel_width", "Independent feature wave width",
            "One whole number from 1 through 5.", "1",
            "Press Enter for serial feature execution.", "integer",
            default=1, minimum=1, maximum=5,
        ),
        _semantic_field(
            "spec_repository_key", "Specification repository",
            "One registered repository name.", "memory-knowledge",
            "Choose the trusted root containing the specification.", "choice",
            choices=["memory-knowledge"], required=True,
            when={"field": "mode", "equals": "start-from-spec"},
        ),
        _semantic_field(
            "spec_relative_path", "Specification path",
            "One repository-relative file path.",
            "Tasks/greenfield/spec.json",
            "No absolute path or parent traversal.", "path", required=True,
            when={"field": "mode", "equals": "start-from-spec"},
        ),
        _semantic_field(
            "decomposition_task_id", "Durable decomposition task identity",
            "One non-empty task identity.", "task-123",
            "Copy the exact persisted identity; do not add labels.", "string",
            required=True,
            when={"field": "mode", "in": [
                "create-program", "resume-program", "validate-fresh",
            ]},
        ),
        _semantic_field(
            "decomposition_run_id", "Durable decomposition run identity",
            "One non-empty run identity.", "run-123",
            "Copy the exact persisted identity; do not add labels.", "string",
            required=True,
            when={"field": "mode", "in": [
                "create-program", "resume-program", "validate-fresh",
            ]},
        ),
        _semantic_field(
            "program_drive_id", "Durable program-drive identity",
            "One UUID.", "01234567-89ab-cdef-0123-456789abcdef",
            "Use the exact persisted UUID.", "string", required=True,
            when={"field": "mode", "in": [
                "resume-program", "validate-fresh",
            ]},
        ),
        _semantic_field(
            "expected_spec_hash", "Expected specification digest",
            "One 64-character lowercase SHA-256 digest.", "a" * 64,
            "Use the exact persisted digest.", "string", required=True,
            when={"field": "mode", "in": [
                "resume-program", "validate-fresh",
            ]},
        ),
    ],
}

CLAUDE_AUTH_SPEC = {
    "schema_version": script_intake.SCHEMA_VERSION,
    "fields": [
        _semantic_field(
            "operation", "Claude authentication operation",
            "One named authentication action.", "status",
            "Choose the intended credential lifecycle action.", "choice",
            choices=list(CLAUDE_AUTH_OPERATIONS), required=True,
        ),
        _semantic_field(
            "source_repository_key", "Authentication script repository",
            "One registered repository name.", "mcp-agents-workflow",
            "Choose the repository containing the checked-in authentication script.",
            "choice", choices=["mcp-agents-workflow"], required=True,
        ),
        _semantic_field(
            "credential_source", "Credential source",
            "One approved source kind.", "runtime-temp-file",
            "Select a handle or file location; never paste credential content.",
            "choice",
            choices=[
                "runtime-temp-file", "host-credential",
                "approved-container-credential",
            ],
            required=True,
            when={"field": "operation", "in": [
                "seed-local", "seed-host", "push-kv", "all",
            ]},
        ),
        _semantic_field(
            "token_file", "Credential file path",
            "One existing filesystem path.", "/private/tmp/claude-oat.txt",
            "Provide a path handle only; never paste the token.", "path",
            required=True,
            when={"field": "credential_source", "equals": "runtime-temp-file"},
        ),
        _semantic_field(
            "config_source", "Optional Claude configuration source",
            "One approved source kind.", "host-config",
            "Choose none unless an explicit configuration must be seeded.",
            "choice", choices=["none", "runtime-temp-file", "host-config"],
            default="none",
            when={"field": "operation", "in": [
                "seed-local", "seed-host", "push-kv", "all",
            ]},
        ),
        _semantic_field(
            "config_file", "Claude configuration file path",
            "One existing filesystem path.", "/private/tmp/claude-config.json",
            "Provide a path handle only; never paste configuration secrets.",
            "path", required=True,
            when={"field": "config_source", "equals": "runtime-temp-file"},
        ),
        _semantic_field(
            "container", "Local container resource name",
            "One registered container name.",
            "workflow-orch-local-sequence-check",
            "Provide the resource name only.", "string",
            default="workflow-orch-local-sequence-check",
            when={"field": "operation", "in": [
                "status", "seed-local", "seed-host", "verify", "all",
            ]},
        ),
        _semantic_field(
            "keyvault_name", "Azure Key Vault resource name",
            "One registered vault name.", "hrness",
            "Provide the resource name only, never secret content.", "string",
            default="hrness",
            when={"field": "operation", "in": [
                "status", "push-kv", "verify", "all",
            ]},
        ),
        _semantic_field(
            "deployment", "Remote workflow deployment",
            "One absolute HTTPS deployment URL.",
            "https://workflow-orch-app-evbxebcccsd7fpgp.westeurope-01.azurewebsites.net",
            "Provide the deployment identity only.", "string",
            default=(
                "https://workflow-orch-app-evbxebcccsd7fpgp."
                "westeurope-01.azurewebsites.net"
            ),
            when={"field": "operation", "in": [
                "reseed-azure", "verify", "all",
            ]},
        ),
        _semantic_field(
            "verify_targets", "Authentication targets to verify",
            "One or more allowed target names.", "local-container",
            "Allowed targets are local-container, host, and remote-claude.",
            "string_list",
            item_prompt="Authentication target",
            item_response_format="One allowed target name.",
            item_example="host",
            item_constraints=(
                "Use local-container, host, or remote-claude exactly."
            ),
            when={"field": "operation", "equals": "verify"},
        ),
        _semantic_field(
            "dry_run", "Preview without mutating credentials",
            "Answer yes or no.", "no",
            "Answer yes to inspect the derived action without applying it.",
            "boolean", default=False,
        ),
    ],
}

OFFLINE_SEQUENCE_CONFIG = {
    "airgapped-local-bulgarian-stt": {
        "operations": ["provision", "channels", "process", "verify", "all"],
        "script": "scripts/setup_airgapped_stt.sh",
    },
    "airgapped-redaction-stack": {
        "operations": ["provision", "verify"],
        "script": "scripts/setup_airgapped_redaction.sh",
    },
    "airgapped-llm-judge": {
        "operations": ["provision", "verify", "smoke"],
        "script": "scripts/setup_airgapped_judge.sh",
    },
    "secure-landing-seed": {
        "operations": ["seed", "list", "verify", "scrub"],
        "script": "scripts/seed_landing.sh",
    },
    "callcenter-harness-engine-invariants": {
        "operations": ["unit", "redaction-smoke"],
        "script": "scripts/test_engine_upgrades.py",
    },
}


def _offline_spec(sequence_id: str) -> dict[str, Any]:
    operations = OFFLINE_SEQUENCE_CONFIG[sequence_id]["operations"]
    fields = [
        _semantic_field(
            "operation", "Offline harness operation", "One named operation.",
            operations[0],
            "Choose the intended provision, verification, or processing behavior.",
            "choice", choices=operations, required=True,
        ),
        _semantic_field(
            "source_repository_key", "Call-center harness repository",
            "One registered repository name.", "callcenter-harness",
            "Choose the repository containing the checked-in harness scripts.",
            "choice", choices=["callcenter-harness"], required=True,
        ),
    ]
    if sequence_id == "airgapped-local-bulgarian-stt":
        fields.extend([
            _semantic_field(
                "model", "Speech-to-text model", "One model name.",
                "small", "Choose small or large-v3 explicitly.", "choice",
                choices=["small", "large-v3"], required=True,
            ),
            _semantic_field(
                "audio", "Call recording", "One existing audio file path.",
                "/private/tmp/call.wav",
                "Provide the recording path only.", "path", required=True,
                when={"field": "operation", "in": [
                    "channels", "process", "verify", "all",
                ]},
            ),
        ])
    elif sequence_id == "airgapped-llm-judge":
        fields.extend([
            _semantic_field(
                "model", "Offline judge model", "One installed model name.",
                "qwen2.5:32b",
                "Provide the local Ollama model identity only.", "string",
                default="qwen2.5:32b",
            ),
            _semantic_field(
                "audio", "Call recording for the judge smoke",
                "One existing audio file path.", "/private/tmp/call.wav",
                "Provide the recording path only.", "path", required=True,
                when={"field": "operation", "equals": "smoke"},
            ),
        ])
    elif sequence_id == "secure-landing-seed":
        fields.extend([
            _semantic_field(
                "landing_directory", "Secure landing directory",
                "One absolute directory path.",
                str(Path.home() / ".callcenter-harness/landing"),
                "This directory temporarily holds original recordings.", "path",
                default=str(Path.home() / ".callcenter-harness/landing"),
            ),
            _semantic_field(
                "source_directory", "Source recording directory",
                "One absolute directory path.",
                str(Path.home() / "Downloads/audio-files"),
                "The seed operation copies from this directory.", "path",
                default=str(Path.home() / "Downloads/audio-files"),
                when={"field": "operation", "in": ["seed", "verify"]},
            ),
            _semantic_field(
                "scrub_scope", "Recordings to scrub and retire",
                "One scope name.", "all",
                "Choose all or one-recording.", "choice",
                choices=["all", "one-recording"], required=True,
                when={"field": "operation", "equals": "scrub"},
            ),
            _semantic_field(
                "recording", "Landing recording to scrub",
                "One filename or absolute file path.", "call.wav",
                "Choose one recording already present in the landing area.",
                "path", required=True,
                when={"field": "scrub_scope", "equals": "one-recording"},
            ),
        ])
    elif sequence_id == "callcenter-harness-engine-invariants":
        fields.append(_semantic_field(
            "audio", "Call recording for the real-path smoke",
            "One existing audio file path.", "/private/tmp/call.wav",
            "Provide the recording path only.", "path", required=True,
            when={"field": "operation", "equals": "redaction-smoke"},
        ))
    return {"schema_version": script_intake.SCHEMA_VERSION, "fields": fields}


OFFLINE_SPECS = {
    sequence_id: _offline_spec(sequence_id)
    for sequence_id in OFFLINE_SEQUENCE_CONFIG
}

OPERATION_KINDS = [
    "auth", "cleanup", "container", "database", "deploy", "image", "other",
    "package", "read-only", "remote-operator", "single-build", "single-test",
    "workflow-drive",
]

SCOPED_CONTEXT_SPEC = {
    "schema_version": script_intake.SCHEMA_VERSION,
    "fields": [
        _semantic_field(
            "operation", "Scoped edit guard operation", "One named operation.",
            "prepare", "Choose the receipt lifecycle action.", "choice",
            choices=["prepare", "check", "verify", "cancel", "self-check"],
            required=True,
        ),
        _semantic_field(
            "source_repository_key", "Guard script repository",
            "One registered repository name.", "memory-knowledge",
            "Choose the repository containing context_edit_guard.py.", "choice",
            choices=["memory-knowledge"], required=True,
        ),
        _semantic_field(
            "receipt", "Tamper-evident receipt path",
            "One absolute path outside the edited repository.",
            "/private/tmp/context-edit-receipt.json",
            "Provide a path only; the guard owns its JSON contents.", "path",
            required=True,
            when={"field": "operation", "in": [
                "prepare", "check", "verify", "cancel",
            ]},
        ),
        _semantic_field(
            "target_repository_key", "Repository containing the edit target",
            "One registered repository name.", "memory-knowledge",
            "Choose the exact repository to protect.", "choice",
            choices=["memory-knowledge"], required=True,
            choices_from_repository_roots=True,
            when={"field": "operation", "equals": "prepare"},
        ),
        _semantic_field(
            "target", "Edit target path",
            "One repository-relative file path.", "scripts/example.py",
            "No absolute path or parent traversal.", "path", required=True,
            when={"field": "operation", "equals": "prepare"},
        ),
        _semantic_field(
            "anchor", "Exact pre-edit anchor",
            "One literal text fragment.", "def target_function():",
            "Provide the exact unique existing text; do not add patch syntax.",
            "string", required=True,
            when={"field": "operation", "equals": "prepare"},
        ),
        _semantic_field(
            "allowed_paths", "Allowed edit path",
            "One or more repository-relative paths.", "scripts/example.py",
            "Every changed path must be within this set.", "string_list",
            item_prompt="Allowed repository-relative edit path",
            item_response_format="One repository-relative path.",
            item_example="tests/test_example.py",
            item_constraints="No absolute path or parent traversal.",
            when={"field": "operation", "equals": "prepare"},
        ),
        _semantic_field(
            "required_after", "Required post-edit literal",
            "One literal text fragment, or press Enter to omit it.",
            "return verified",
            "The literal must exist after the edit when supplied.", "string",
            when={"field": "operation", "equals": "prepare"},
        ),
        _semantic_field(
            "forbidden_after", "Forbidden post-edit literal",
            "One literal text fragment, or press Enter to omit it.",
            "TODO",
            "The literal must be absent after the edit when supplied.", "string",
            when={"field": "operation", "equals": "prepare"},
        ),
    ],
}

DISCOVERY_RECONCILIATION_SPEC = {
    "schema_version": script_intake.SCHEMA_VERSION,
    "fields": [
        _semantic_field(
            "operation", "Discovery reconciliation operation",
            "One named operation.", "audit",
            "Choose audit, validation, execution, rolling execution, or the one-shot drive.",
            "choice",
            choices=["audit", "validate", "execute", "execute-rolling", "drive"],
            required=True,
        ),
        _semantic_field(
            "source_repository_key", "Reconciliation controller repository",
            "One registered repository name.", "memory-knowledge",
            "Choose the repository containing the checked-in controller.",
            "choice", choices=["memory-knowledge"], required=True,
        ),
        _semantic_field(
            "output", "Audit manifest output path",
            "One absolute task-artifact or runtime-temporary path.",
            "/private/tmp/discovery-reconciliation.json",
            "The controller creates this file.", "path", required=True,
            when={"field": "operation", "equals": "audit"},
        ),
        _semantic_field(
            "manifest", "Approved reconciliation manifest",
            "One existing manifest file path.",
            "/private/tmp/discovery-reconciliation.json",
            "Provide the file path only; never paste or reconstruct its JSON.",
            "path", required=True,
            when={"field": "operation", "in": ["validate", "execute"]},
        ),
        _semantic_field(
            "output_directory", "Rolling execution output directory",
            "One task-artifact or runtime-temporary directory path.",
            "/private/tmp/discovery-reconciliation-runs",
            "The controller owns invocation subdirectories.", "path",
            required=True,
            when={"field": "operation", "equals": "execute-rolling"},
        ),
        _semantic_field(
            "task_id", "One-shot drive task identity",
            "One non-empty task identity.", "discovery-reconcile-20260723",
            "Use the approved task identity exactly.", "string", required=True,
            when={"field": "operation", "equals": "drive"},
        ),
        _semantic_field(
            "output_root", "One-shot drive output root",
            "One task-artifact or runtime-temporary directory path.",
            "/private/tmp/discovery-reconciliation-drive",
            "The controller owns all child outputs below this root.", "path",
            required=True,
            when={"field": "operation", "equals": "drive"},
        ),
    ],
}

BLOCKER_BACKLOG_RECONCILIATION_SPEC = {
    "schema_version": script_intake.SCHEMA_VERSION,
    "fields": [
        _semantic_field(
            "operation", "Blocker backlog operation",
            "One named operation.", "audit",
            "Choose audit, validation, or approved execution.",
            "choice", choices=["audit", "validate", "execute"], required=True,
        ),
        _semantic_field(
            "source_repository_key", "Blocker controller repository",
            "One registered repository name.", "memory-knowledge",
            "Choose the repository containing the canonical blocker ledger.",
            "choice", choices=["memory-knowledge"], required=True,
        ),
        _semantic_field(
            "output", "Audit manifest output path",
            "One absolute task-artifact or runtime-temporary path.",
            "/private/tmp/blocker-backlog-reconciliation.json",
            "The controller creates this file.", "path", required=True,
            when={"field": "operation", "equals": "audit"},
        ),
        _semantic_field(
            "manifest", "Approved blocker disposition manifest",
            "One existing manifest file path.",
            "/private/tmp/blocker-backlog-reconciliation.json",
            "Provide the file path only; never paste or reconstruct its JSON.",
            "path", required=True,
            when={"field": "operation", "in": ["validate", "execute"]},
        ),
        _semantic_field(
            "run_id", "Active reconciliation run identity",
            "One exact active run identity.",
            "00000000-0000-4000-8000-000000000000",
            "Use the run started for the selected blocker reconciliation task.",
            "string", required=True,
            when={"field": "operation", "equals": "execute"},
        ),
    ],
}

DISCOVERY_PROMOTION_SPEC = {
    "schema_version": script_intake.SCHEMA_VERSION,
    "fields": [
        _semantic_field(
            "operation", "Discovery lifecycle operation",
            "One named lifecycle operation.", "status",
            "Choose status, drive, correct, or correct-registered.", "choice",
            choices=["status", "drive", "correct", "correct-registered"],
            required=True,
        ),
        _semantic_field(
            "source_repository_key", "Lifecycle controller repository",
            "One registered repository name.", "memory-knowledge",
            "Choose the repository containing the checked-in lifecycle controller.",
            "choice", choices=["memory-knowledge"], required=True,
        ),
        _semantic_field(
            "discovery_file", "Discovery log path",
            "One existing discovery-log file path.",
            "operations/sequences/discovery/2026-07-23-example.md",
            "Provide the path only.", "path", required=True,
            when={"field": "operation", "in": ["status", "drive", "correct"]},
        ),
        _semantic_field(
            "sequence_id", "Registered sequence identity",
            "One lowercase hyphenated identity.", "example-sequence",
            "Do not add quotes or filesystem paths.", "string", required=True,
            when={"field": "operation", "in": ["status", "drive", "correct"]},
        ),
        _semantic_field(
            "subject_id", "Registered correction subject",
            "One lowercase hyphenated sequence identity.", "example-sequence",
            "Use the exact registered sequence identity.", "string",
            required=True,
            when={"field": "operation", "equals": "correct-registered"},
        ),
        _semantic_field(
            "repo_roots_file", "Optional repository-root registry",
            "One existing registry file path, or press Enter to omit it.",
            "operations/sequences/discovery/example.repositories.json",
            "Provide the path only; never paste its JSON.", "path",
        ),
        _semantic_field(
            "use_when", "Sequence selection purpose",
            "One plain-language sentence.", "Deploy the API to development.",
            "Describe when this sequence should be selected.", "string",
            required=True, when={"field": "operation", "equals": "drive"},
        ),
        _semantic_field(
            "operation_kinds", "Governed operation kind",
            "One or more allowed operation-kind names.", "deploy",
            "Use only registered operation kinds.", "string_list",
            item_prompt="Governed operation kind",
            item_response_format="One registered operation-kind name.",
            item_example="workflow-drive",
            item_constraints="Use an allowed operation kind exactly.",
            when={"field": "operation", "equals": "drive"},
        ),
        _semantic_field(
            "automation_display", "Automation description",
            "One human-readable automation identity.",
            "memory-knowledge:scripts/example.py",
            "Describe the checked-in automation without adding arguments.",
            "string", required=True,
            when={"field": "operation", "equals": "drive"},
        ),
        _semantic_field(
            "pass_signal", "Successful completion signal",
            "One exact observable success description.", "EXAMPLE COMPLETE",
            "State what proves the sequence completed.", "string",
            required=True, when={"field": "operation", "equals": "drive"},
        ),
        _semantic_field(
            "task_id", "Failed-run task identity",
            "One task identity, or press Enter when no protected artifact changed.",
            "task-123",
            "Required only when a protected controller artifact changed.",
            "string",
            when={"field": "operation", "in": ["correct", "correct-registered"]},
        ),
        _semantic_field(
            "solution", "Correction summary",
            "One plain-language solution description.",
            "Bind the missing runtime dependency.",
            "Describe the stable correction, not an invocation.", "string",
            required=True,
            when={"field": "operation", "in": ["correct", "correct-registered"]},
        ),
        _semantic_field(
            "changed_artifacts", "Changed artifact",
            "One changed artifact at a time.",
            "a repository and relative file path",
            "Answer the repository and path subquestions separately.",
            "object_list",
            item_fields=[
                _semantic_field(
                    "repository_key", "Changed artifact repository",
                    "One registered repository name.", "memory-knowledge",
                    "Use the repository containing the changed file.", "string",
                    required=True,
                ),
                _semantic_field(
                    "path", "Changed artifact path",
                    "One repository-relative file path.", "scripts/example.py",
                    "No absolute path or parent traversal.", "path",
                    required=True,
                ),
            ],
            when={"field": "operation", "in": ["correct", "correct-registered"]},
        ),
        _semantic_field(
            "reusable_behavior_changed", "Did reusable behavior change",
            "Answer yes or no.", "yes",
            "Answer yes when the corrected reusable boundary changed.",
            "boolean", required=True,
            when={"field": "operation", "in": ["correct", "correct-registered"]},
        ),
        _semantic_field(
            "superseding", "Does this replace an unverified correction",
            "Answer yes or no.", "no",
            "Answer yes only when explicit prior correction identities must be superseded.",
            "boolean", default=False,
            when={"field": "operation", "in": ["correct", "correct-registered"]},
        ),
        _semantic_field(
            "supersedes_correction_ids", "Correction identity to supersede",
            "One or more UUIDs.", "01234567-89ab-cdef-0123-456789abcdef",
            "Use exact persisted correction UUIDs.", "string_list",
            item_prompt="Correction UUID to supersede",
            item_response_format="One UUID.",
            item_example="01234567-89ab-cdef-0123-456789abcdef",
            item_constraints="Use the exact persisted correction UUID.",
            when={"field": "superseding", "equals": True},
        ),
    ],
}

CONVERGENCE_CHECKPOINT_SPEC = {
    "schema_version": script_intake.SCHEMA_VERSION,
    "fields": [
        _semantic_field(
            "source_repository_key", "Checkpoint controller repository",
            "One registered repository name.", "memory-knowledge",
            "Choose the repository containing the checked-in controller.",
            "choice", choices=["memory-knowledge"], required=True,
        ),
        _semantic_field(
            "state", "Convergence state file",
            "One existing file path.", "/private/tmp/convergence-state.json",
            "Provide the file path only; do not paste its contents.", "path",
            required=True,
        ),
        _semantic_field(
            "approval_id", "Baseline approval identity",
            "One exact non-empty approval identity.", "approval-123",
            "Use the approval authorizing the shared ledger/view checkpoint.",
            "string", required=True,
        ),
        _semantic_field(
            "child_intent_file", "Prepared typed child-intent artifact",
            "One existing JSON file path.", "/private/tmp/child-intent.json",
            "Provide the path only; code validates and serializes its JSON.",
            "path", required=True,
        ),
        _semantic_field(
            "stage", "Convergence stage",
            "One stage name.", "implementation",
            "Use the stage covered by the approval.", "choice",
            choices=["research", "plan", "implementation", "review"],
            default="implementation",
        ),
    ],
}

CONVERGENCE_OPERATION_FIELDS = [
    _semantic_field(
        "kind", "Review-state operation", "One named operation.", "status",
        "Choose the semantic state operation.", "choice",
        choices=[
            "record-gap", "grant-autonomy", "grant-scope-change",
            "accept-baseline", "guard-baseline", "record-stage",
            "transition", "check", "status",
        ], required=True,
    ),
    _semantic_field(
        "id", "Gap or grant identity", "One stable semantic identity.",
        "gap-1", "Use the approved gap or grant identity.", "string",
        required=True,
        when={"field": "kind", "in": [
            "record-gap", "grant-autonomy", "grant-scope-change",
        ]},
    ),
    _semantic_field(
        "requirement_ids", "Affected requirement identity",
        "One or more requirement identities.", "REQ-1",
        "List each affected requirement once.", "string_list",
        item_prompt="Affected requirement identity",
        item_response_format="One requirement identity.",
        item_example="REQ-2",
        item_constraints="Use the approved identity exactly.",
        when={"field": "kind", "equals": "record-gap"},
    ),
    _semantic_field(
        "source_stage", "Gap source stage", "One stage name.", "review",
        "Name the stage where the evidence was observed.", "string",
        required=True, when={"field": "kind", "equals": "record-gap"},
    ),
    _semantic_field(
        "impact", "Practical gap impact", "One plain-language sentence.",
        "The approved outcome cannot be verified.",
        "Describe the consequence, not an invocation.", "string",
        required=True, when={"field": "kind", "equals": "record-gap"},
    ),
    _semantic_field(
        "repository_keys", "Authorized repository",
        "One or more registered repository names.", "memory-knowledge",
        "List only repositories covered by the authority receipt.",
        "string_list",
        item_prompt="Authorized repository name",
        item_response_format="One registered repository name.",
        item_example="memory-knowledge",
        item_constraints="Use the registered name exactly.",
        when={"field": "kind", "in": [
            "grant-autonomy", "grant-scope-change",
        ]},
    ),
    _semantic_field(
        "allowed_paths", "Authorized repository path",
        "One or more repository-relative paths.", "scripts/tool.py",
        "No absolute paths or parent traversal.", "string_list",
        item_prompt="Authorized repository-relative path",
        item_response_format="One repository-relative path.",
        item_example="tests/test_tool.py",
        item_constraints="No absolute path or parent traversal.",
        when={"field": "kind", "in": [
            "grant-autonomy", "grant-scope-change",
        ]},
    ),
    _semantic_field(
        "stage", "Operation stage", "One stage name.", "review",
        "Use the stage covered by the approval.", "string", required=True,
        when={"field": "kind", "in": [
            "grant-autonomy", "grant-scope-change", "accept-baseline",
        ]},
    ),
    _semantic_field(
        "evidence", "Bounded operation evidence",
        "One plain-language evidence statement.", "Approved in task record.",
        "Describe the evidence; do not provide invocation syntax.", "string",
        required=True, when={"field": "kind", "in": [
            "record-gap", "grant-autonomy", "grant-scope-change",
        ]},
    ),
    _semantic_field(
        "authority_approval_receipt_id", "Authority receipt identity",
        "One exact receipt identity.",
        "55555555-5555-5555-8555-555555555555",
        "Use the unconsumed receipt identity exactly.", "string",
        required=True, when={"field": "kind", "in": [
            "grant-autonomy", "grant-scope-change",
        ]},
    ),
    _semantic_field(
        "repository_key", "Baseline repository",
        "One state-registered repository name.", "memory-knowledge",
        "Use the repository key recorded in convergence state.", "string",
        required=True, when={"field": "kind", "equals": "accept-baseline"},
    ),
    _semantic_field(
        "changed_paths", "Approved changed path",
        "One or more repository-relative paths.",
        WORK_MEMORY_EVENTS_PATH,
        "No absolute paths or parent traversal.", "string_list",
        item_prompt="Approved changed repository-relative path",
        item_response_format="One repository-relative path.",
        item_example="operations/blockers/BLOCKERS.md",
        item_constraints="No absolute path or parent traversal.",
        when={"field": "kind", "equals": "accept-baseline"},
    ),
    _semantic_field(
        "approval_id", "Baseline approval identity",
        "One exact approval identity.", "approval-123",
        "Use the approval covering these changed paths.", "string",
        required=True, when={"field": "kind", "equals": "accept-baseline"},
    ),
    _semantic_field(
        "accept_approved_dirty_overlap", "Accept approved dirty overlap",
        "Answer yes or no.", "no",
        "Answer yes only when the approval explicitly covers the overlap.",
        "boolean", default=False,
        when={"field": "kind", "equals": "accept-baseline"},
    ),
    _semantic_field(
        "result_file", "Stage result artifact",
        "One trusted runtime-temp/ or task-artifact-root/ path.",
        "task-artifact-root/example/result.json",
        "Provide the trusted path only.", "path", required=True,
        when={"field": "kind", "equals": "record-stage"},
    ),
    _semantic_field(
        "to", "Target convergence status", "One status name.", "review",
        "Use the intended next convergence status.", "choice",
        choices=[
            "research", "plan", "implementation", "review", "blocked",
            "cap_reached", "complete",
        ], required=True, when={"field": "kind", "equals": "transition"},
    ),
]

CONVERGENCE_REVIEW_SPEC = {
    "schema_version": script_intake.SCHEMA_VERSION,
    "fields": [
        _semantic_field(
            "operation", "Review-cycle execution mode",
            "One named mode.", "dry-run",
            "Choose dry-run to inspect or apply to change state.", "choice",
            choices=["dry-run", "apply"], required=True,
        ),
        _semantic_field(
            "source_repository_key", "Review controller repository",
            "One registered repository name.", "memory-knowledge",
            "Choose the repository containing the checked-in controller.",
            "choice", choices=["memory-knowledge"], required=True,
        ),
        _semantic_field(
            "state", "Trusted convergence state reference",
            "One runtime-temp/ or task-artifact-root/ relative reference.",
            "runtime-temp/convergence-state.json",
            "Do not provide an absolute path or JSON contents.", "path",
            required=True,
        ),
        _semantic_field(
            "expected_final_status", "Expected final convergence status",
            "One status name.", "review",
            "Choose the status that must hold after all operations.", "choice",
            choices=[
                "research", "plan", "implementation", "review", "blocked",
                "cap_reached", "complete",
            ], required=True,
        ),
        _semantic_field(
            "operations", "Ordered convergence operation",
            "Answer one operation's semantic subquestions at a time.",
            "a status check followed by a transition",
            "Do not provide JSON, flags, or operation UUIDs.", "object_list",
            item_fields=CONVERGENCE_OPERATION_FIELDS,
        ),
    ],
}

TAGGABLE_RELOAD_SPEC = {
    "schema_version": script_intake.SCHEMA_VERSION,
    "fields": [
        _semantic_field(
            "repository_key", "Taggable API repository",
            "One registered repository name.", "taggable-api",
            "Choose the checkout containing the reload automation.", "choice",
            choices=["taggable-api"], required=True,
        ),
        _semantic_field(
            "export_directory", "Per-table CSV export directory",
            "One existing directory path.", "/private/tmp/app.csv",
            "Provide the directory only; do not add flags.", "path",
            required=True,
        ),
        _semantic_field(
            "source_record_id", "Source system record identity",
            "One positive integer.", "1",
            "Use the approved system_record_id.", "integer",
            required=True, minimum=1,
        ),
        _semantic_field(
            "webjob_missing", "Is the db-import WebJob missing",
            "Answer yes or no.", "no",
            "Answer yes only when preflight confirmed it must be redeployed.",
            "boolean", default=False,
        ),
        _semantic_field(
            "manage_database_tier", "Scale S4 for load and restore S1",
            "Answer yes or no.", "yes",
            "Use yes unless an approved recovery manages scaling separately.",
            "boolean", default=True,
        ),
    ],
}

GITHUB_REFRESH_SPEC = {
    "schema_version": script_intake.SCHEMA_VERSION,
    "fields": [
        _semantic_field(
            "repository_key", "Workflow orchestration repository",
            "One registered repository name.", "mcp-agents-workflow",
            "Choose the checkout containing the refresh wrapper.", "choice",
            choices=["mcp-agents-workflow"], required=True,
        ),
        _semantic_field(
            "server_url", "Target workflow server",
            "One absolute secure WebSocket URL.", "wss://example.test/ws",
            "Target the KV-backed deployment for a durable refresh.", "string",
            required=True,
        ),
        _semantic_field(
            "operator_env", "Administrator operator environment file",
            "One existing env-file path.",
            "/private/tmp/workflow-admin.env",
            "Provide the path only; never paste credentials.", "path",
            required=True,
        ),
        _semantic_field(
            "actor_email", "Administrator email",
            "One email address.", "admin@example.com",
            "Use the administrator identity for this session.", "string",
            required=True,
        ),
        _semantic_field(
            "durability", "Refresh durability",
            "One named durability target.", "durable",
            "Choose durable for Key Vault writeback; local-only is ephemeral.",
            "choice", choices=["durable", "local-only"], required=True,
        ),
        _semantic_field(
            "operation", "Refresh operation", "One named operation.", "dry-run",
            "Choose dry-run to inspect or refresh to apply.", "choice",
            choices=["dry-run", "refresh"], required=True,
        ),
    ],
}

MAWF_ACTIONS = [
    "infra", "start", "poll", "approve-start", "answer-gate",
    "decision", "continue", "repair", "drive",
]


def _mawf_spec(sequence_id: str) -> dict[str, Any]:
    fields = [
        _semantic_field(
            "repository_key", "MAWF controller repository",
            "One registered repository name.", "mcp-agents-workflow",
            "Choose the checkout containing the playbook driver.", "choice",
            choices=["mcp-agents-workflow"], required=True,
        ),
        _semantic_field(
            "action", "Playbook driver action", "One named action.", "poll",
            "Choose the next semantic lifecycle action.", "choice",
            choices=MAWF_ACTIONS, required=True,
        ),
        _semantic_field(
            "task_guid", "Workflow task identity", "One exact task GUID.",
            "task-123", "Use the persisted task identity.", "string",
            required=True, when={"field": "action", "in": [
                "start", "poll", "approve-start", "answer-gate", "decision",
                "continue", "repair", "drive",
            ]},
        ),
        _semantic_field(
            "run_id", "Workflow run identity", "One exact run identity.",
            "run-123", "Use the persisted run identity.", "string",
            required=True, when={"field": "action", "in": [
                "poll", "approve-start", "answer-gate",
            ]},
        ),
        _semantic_field(
            "workflow_name", "Workflow name", "One workflow identity.",
            "research-workflow", "Use the workflow owning the run.", "choice",
            choices=[
                "research-workflow", "plan-workflow",
                "write-code-workflow", "review-workflow",
            ], required=True, when={"field": "action", "in": [
                "approve-start", "answer-gate",
            ]},
        ),
        _semantic_field(
            "code_project_source", "Host code-project checkout",
            "One existing directory path.", "/private/tmp/product",
            "Provide the host directory only.", "path", required=True,
            when={"field": "action", "equals": "infra"},
        ),
        _semantic_field(
            "rebuild_image", "Rebuild the local image",
            "Answer yes or no.", "yes",
            "Answer no only when the current image is already approved.",
            "boolean", default=True,
            when={"field": "action", "equals": "infra"},
        ),
        _semantic_field(
            "code_repository", "In-container code repository",
            "One absolute in-container path.", "/workspaces/product",
            "Provide the repository path only.", "path", required=True,
            when={"field": "action", "in": [
                "start", "decision", "continue", "repair", "drive",
            ]},
        ),
        _semantic_field(
            "prompt_file", "Task prompt file", "One existing file path.",
            "/private/tmp/task.md", "Provide the prompt path only.", "path",
            required=True, when={"field": "action", "equals": "start"},
        ),
        _semantic_field(
            "task_action", "Task start behavior", "One named behavior.",
            "start_over", "Choose new or restart the existing task.", "choice",
            choices=["new", "start_over"], default="start_over",
            when={"field": "action", "equals": "start"},
        ),
        _semantic_field(
            "branch", "Code-project branch", "One branch name.", "main",
            "Use the approved base branch.", "string", default="main",
            when={"field": "action", "in": [
                "start", "decision", "continue", "repair", "drive",
            ]},
        ),
        _semantic_field(
            "completed_workflow", "Completed workflow",
            "One workflow identity, or press Enter when server state owns it.",
            "research-workflow",
            "Supply only as a fallback for continuation or repair.", "string",
            when={"field": "action", "in": ["continue", "repair"]},
        ),
        _semantic_field(
            "dry_run", "Inspect without executing", "Answer yes or no.", "yes",
            "Use yes to review the derived action first.", "boolean",
            default=False,
        ),
    ]
    return {"schema_version": script_intake.SCHEMA_VERSION, "fields": fields}


MAWF_SPECS = {
    sequence_id: _mawf_spec(sequence_id)
    for sequence_id in ("mawf-playbook-full-test", "mawf-playbook-speed-test")
}

MAWF_BLOCKER_SPEC = {
    "schema_version": script_intake.SCHEMA_VERSION,
    "fields": [
        _semantic_field(
            "repository_key", "MAWF controller repository",
            "One registered repository name.", "mcp-agents-workflow",
            "Choose the checkout containing the playbook driver.", "choice",
            choices=["mcp-agents-workflow"], required=True,
        ),
        _semantic_field(
            "action", "Blocker lifecycle action", "One named action.",
            "record-blocker", "Choose record or the narrowest re-entry mode.",
            "choice", choices=[
                "record-blocker", "resume", "restart-workflow", "start-over",
            ], required=True,
        ),
        _semantic_field(
            "task_guid", "Workflow task identity", "One exact task GUID.",
            "task-123", "Use the persisted task identity.", "string",
            required=True, when={"field": "action", "in": [
                "resume", "restart-workflow", "start-over",
            ]},
        ),
        _semantic_field(
            "workflow_name", "Blocked workflow", "One workflow identity.",
            "research-workflow", "Use the workflow containing the blocker.",
            "string", required=True, when={"field": "action", "in": [
                "record-blocker", "resume", "restart-workflow",
            ]},
        ),
        _semantic_field(
            "run_id", "Blocked run identity", "One exact run identity.",
            "run-123", "Use the persisted failed run.", "string",
            required=True, when={"field": "action", "in": [
                "record-blocker", "resume",
            ]},
        ),
        _semantic_field(
            "code_repository", "In-container code repository",
            "One absolute in-container path.", "/workspaces/product",
            "Provide the repository path only.", "path", required=True,
            when={"field": "action", "in": [
                "restart-workflow", "start-over",
            ]},
        ),
        _semantic_field(
            "prompt_file", "Task prompt file", "One existing file path.",
            "/private/tmp/task.md", "Provide the prompt path only.", "path",
            required=True, when={"field": "action", "in": [
                "restart-workflow", "start-over",
            ]},
        ),
        _semantic_field(
            "gate_policy", "Gate policy", "One named policy.", "full",
            "Preserve the calling sequence policy.", "choice",
            choices=["full", "speed"], required=True,
            when={"field": "action", "in": [
                "record-blocker", "start-over",
            ]},
        ),
        _semantic_field(
            "blocker_id", "Catalog blocker identity",
            "One exact RP identity.", "RP-123",
            "Use the assigned blocker identity.", "string", required=True,
            when={"field": "action", "equals": "record-blocker"},
        ),
        _semantic_field(
            "summary", "One-line blocker symptom",
            "One plain-language sentence.", "The phase rejected valid output.",
            "Describe the observed symptom only.", "string", required=True,
            when={"field": "action", "equals": "record-blocker"},
        ),
        _semantic_field(
            "evidence_file", "Blocker evidence artifact",
            "One existing file path.", "/private/tmp/blocker.json",
            "Provide the evidence path only.", "path", required=True,
            when={"field": "action", "equals": "record-blocker"},
        ),
        _semantic_field(
            "dry_run", "Inspect without executing", "Answer yes or no.", "yes",
            "Use yes to review the derived re-entry action.", "boolean",
            default=False, when={"field": "action", "in": [
                "resume", "restart-workflow", "start-over",
            ]},
        ),
    ],
}

GREENFIELD_RECREATE_SPEC = {
    "schema_version": script_intake.SCHEMA_VERSION,
    "fields": [
        _semantic_field(
            "repository_key", "Workflow orchestration repository",
            "One registered repository name.", "mcp-agents-workflow",
            "Choose the checkout containing recreate-resume automation.",
            "choice", choices=["mcp-agents-workflow"], required=True,
        ),
        _semantic_field(
            "feature_repository", "Feature repository identity",
            "One github:owner/repository identity.",
            "github:thebteambg/supermariobros",
            "Use the durable program's exact feature repository.", "string",
            required=True,
        ),
        _semantic_field(
            "program_drive_id", "Program drive identity",
            "One exact persisted identity.", "program-drive-123",
            "Use the halted program's drive identity.", "string", required=True,
        ),
        _semantic_field(
            "decomposition_task_id", "Decomposition task identity",
            "One exact mawf-task identity.", "mawf-task-123",
            "Use the task owning the durable program tree.", "string",
            required=True,
        ),
        _semantic_field(
            "rebuild_image", "Rebuild before recreating",
            "Answer yes or no.", "yes",
            "Answer yes when resuming after an engine or image change.",
            "boolean", default=False,
        ),
        _semantic_field(
            "container", "Local container name", "One container name.",
            "workflow-orch-local-sequence-check",
            "Use the sequence container identity.", "string",
            default="workflow-orch-local-sequence-check",
        ),
        _semantic_field(
            "image_tag", "Local image tag", "One image tag.",
            "workflow-orch:local-sequence-check",
            "Use the approved image tag.", "string",
            default="workflow-orch:local-sequence-check",
        ),
        _semantic_field(
            "port", "Local service port", "One integer from 1 through 65535.",
            "18083", "Use an available approved port.", "integer",
            default=18083, minimum=1, maximum=65535,
        ),
        _semantic_field(
            "keyvault", "Credential vault name", "One vault name.", "hrness",
            "Use the vault containing the required runtime credentials.",
            "string", default="hrness",
        ),
        _semantic_field(
            "start_feature_index", "First feature index",
            "One non-negative integer.", "0",
            "Resume from the approved feature boundary.", "integer",
            default=0, minimum=0,
        ),
        _semantic_field(
            "parallel_width", "Parallel feature width",
            "One positive integer.", "1",
            "Use the approved concurrency width.", "integer",
            default=1, minimum=1,
        ),
        _semantic_field(
            "expected_spec_hash", "Expected program specification hash",
            "One 64-character SHA-256, or press Enter to omit it.",
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "Use only when the resume is hash-pinned.", "string",
        ),
    ],
}

WORKFLOW_PHASE_RESUME_SPEC = {
    "schema_version": script_intake.SCHEMA_VERSION,
    "fields": [
        _semantic_field(
            "repository_key", "United Partners repository",
            "One registered repository name.", "united-partners",
            "Choose the checkout containing the persisted run.", "choice",
            choices=["united-partners"], required=True,
        ),
        _semantic_field(
            "client", "Client configuration key", "One client slug.",
            "vivacom", "Use the client whose workflow matches the source run.",
            "string", required=True,
        ),
        _semantic_field(
            "source_run_id", "Persisted source run identity",
            "One exact run identity.", "up-run-123",
            "Use the non-completed source run.", "string", required=True,
        ),
        _semantic_field(
            "first_unfinished_phase", "First unfinished phase",
            "One exact phase identity.", "compose-llm-strategy-brief",
            "Use the boundary reported by persisted state.", "string",
            required=True,
        ),
        _semantic_field(
            "reopen_completed_phase", "Re-open a phase that already completed",
            "Answer yes or no.", "no",
            (
                "Answer yes only when that phase's own logic changed and must run again; "
                "it discards that phase and every phase after it."
            ),
            "boolean", required=True,
        ),
    ],
}

WORKFLOW_CLIENT_REGENERATION_SPEC = {
    "schema_version": script_intake.SCHEMA_VERSION,
    "fields": [
        _semantic_field(
            "repository_key", "United Partners repository",
            "One registered repository name.", "united-partners",
            "Choose the checkout containing the pinned parent run.", "choice",
            choices=["united-partners"], required=True,
        ),
        _semantic_field(
            "client", "Client configuration key", "One client slug.",
            "vivacom", "Use the client whose workflow the parent run belongs to.",
            "string", required=True,
        ),
        _semantic_field(
            "parent_run_id", "Pinned parent run identity",
            "One exact run identity.", "up-run-123",
            "Use the discovery parent whose inputs this regeneration builds on.",
            "string", required=True,
        ),
        _semantic_field(
            "answers_source_run_id", "Run supplying the client's answers",
            "One exact run identity.", "up-run-123",
            "Use the run whose recorded client answers this regeneration reuses.",
            "string", required=True,
        ),
        _semantic_field(
            "controlled_topic_policies_path",
            "Owner controlled-topic policy set",
            "One existing file path.",
            "Tasks/vivacom-corporate-demo/controlled-topic-policies.json",
            "Supply the owner ruling covering every flagged interview answer.",
            "path", required=True,
        ),
    ],
}

CALLCENTER_PROVISION_SPEC = {
    "schema_version": script_intake.SCHEMA_VERSION,
    "fields": [
        _semantic_field(
            "repository_key", "Call-center harness repository",
            "One registered repository name.", "callcenter-harness",
            "Choose the checkout containing the air-gapped scripts.", "choice",
            choices=["callcenter-harness"], required=True,
        ),
        _semantic_field(
            "action", "Provision or verification action",
            "One named action.", "provision-small",
            "Choose the next sequence step.", "choice", choices=[
                "provision-small", "provision-large",
                "provision-redaction", "verify-redaction",
                "smoke-core", "smoke-ingest", "smoke-redact",
                "smoke-pipeline", "smoke-eval",
            ], required=True,
        ),
        _semantic_field(
            "recording", "Call recording",
            "One existing audio file path.", "/private/tmp/call.wav",
            "Provide the recording path only.", "path", required=True,
            when={"field": "action", "in": [
                "smoke-ingest", "smoke-redact",
                "smoke-pipeline", "smoke-eval",
            ]},
        ),
    ],
}

REMOTE_ONBOARDING_ACTIONS = [
    "user-list", "user-list-refresh", "user-detail",
    "new-user-start", "new-user-set-first-name",
    "new-user-set-last-name", "new-user-set-email",
    "new-user-set-role", "repo-access-list", "repo-access-select",
    "repo-access-action", "repo-access-save", "field-update-start",
    "field-update-apply", "role-update-start", "role-update-apply",
    "status-toggle-confirm", "status-toggle-apply",
    "create-user-review", "create-user-apply", "stale-refresh",
    "stale-overwrite", "flow-back-step", "flow-back", "flow-cancel",
    "flow-discard", "flow-stay", "flow-exit",
]

REMOTE_ONBOARDING_SPEC = {
    "schema_version": script_intake.SCHEMA_VERSION,
    "fields": [
        _semantic_field(
            "repository_key", "Remote user-admin package repository",
            "One registered repository name.", "mcp-agents-workflow",
            "Choose the checkout containing the sendable admin package.",
            "choice", choices=["mcp-agents-workflow"], required=True,
        ),
        _semantic_field(
            "server_url", "Deployed workflow server",
            "One absolute secure WebSocket URL.", "wss://example.test/ws",
            "Use the deployed server that owns the authoritative registry.",
            "string", required=True,
        ),
        _semantic_field(
            "actor_email", "Administrator email", "One email address.",
            "admin@example.com", "Use the authenticated administrator.",
            "string", required=True,
        ),
        _semantic_field(
            "action", "User administration action", "One named action.",
            "user-list", "Choose the next state-machine action.", "choice",
            choices=REMOTE_ONBOARDING_ACTIONS, required=True,
        ),
        _semantic_field(
            "state_file", "Admin flow state file", "One local file path.",
            "/private/tmp/user-admin-state.json",
            "Provide the path only; the package owns its contents.", "path",
            required=True,
        ),
        _semantic_field(
            "selected_user_id", "Selected deployed user identity",
            "One exact user identity.", "user-123",
            "Use the identity returned by the deployed user list.", "string",
            required=True, when={"field": "action", "in": [
                "user-detail", "repo-access-list", "field-update-start",
                "role-update-start", "status-toggle-confirm",
            ]},
        ),
        _semantic_field(
            "value", "User field value", "One plain-text field value.",
            "Kamen", "Provide only the intended value.", "string",
            required=True, when={"field": "action", "in": [
                "new-user-set-first-name", "new-user-set-last-name",
                "new-user-set-email", "field-update-start",
            ]},
        ),
        _semantic_field(
            "field", "Existing user field", "One field name.", "email",
            "Choose the field being changed.", "choice",
            choices=["firstName", "lastName", "email"], required=True,
            when={"field": "action", "equals": "field-update-start"},
        ),
        _semantic_field(
            "role", "User role", "One role name.", "employee",
            "Use the approved role.", "choice",
            choices=["employee", "admin"], required=True,
            when={"field": "action", "in": [
                "new-user-set-role", "role-update-start",
            ]},
        ),
        _semantic_field(
            "repo_alias", "Repository access key",
            "One canonical repository key.", "neocurrency-dashboard",
            "Use the memory-knowledge repository key exactly.", "string",
            required=True, when={"field": "action", "equals": "repo-access-select"},
        ),
        _semantic_field(
            "repo_access_operation", "Repository access change",
            "One named change.", "add", "Choose add or remove.", "choice",
            choices=["add", "remove"], required=True,
            when={"field": "action", "equals": "repo-access-action"},
        ),
        _semantic_field(
            "status_action", "User status change", "One named change.",
            "reactivate", "Choose deactivate or reactivate.", "choice",
            choices=["deactivate", "reactivate"], required=True,
            when={"field": "action", "equals": "status-toggle-confirm"},
        ),
        _semantic_field(
            "confirmation_file", "Reviewed confirmation artifact",
            "One existing JSON file path.", "/private/tmp/confirmation.json",
            "Provide the file path only; code serializes its contents.", "path",
            required=True, when={"field": "action", "in": [
                "repo-access-save", "field-update-apply",
                "role-update-apply", "status-toggle-apply",
                "create-user-apply", "stale-overwrite",
            ]},
        ),
        _semantic_field(
            "token_output_file", "Private first-use token destination",
            "One local file path.", "/private/tmp/new-user.token",
            "Provide the destination only; the token is never returned here.",
            "path", required=True,
            when={"field": "action", "equals": "create-user-apply"},
        ),
    ],
}

DISCOVERY_BOOTSTRAP_SPEC = {
    "schema_version": script_intake.SCHEMA_VERSION,
    "fields": [
        _semantic_field(
            "source_repository_key", "Bootstrap controller repository",
            "One registered repository name.", "memory-knowledge",
            "Choose the repository containing discovery_bootstrap.py.",
            "choice", choices=["memory-knowledge"], required=True,
        ),
        _semantic_field(
            "task_id", "Discovery task identity", "One stable task identity.",
            "discover-example-sequence",
            "Use the identity governing this discovery.", "string",
            required=True,
        ),
        _semantic_field(
            "operation_kind", "Governed operation kind",
            "One registered operation-kind name.", "workflow-drive",
            "Use the kind matching the discovered effect.", "choice",
            choices=OPERATION_KINDS, required=True,
        ),
        _semantic_field(
            "date", "Fixed discovery date", "One YYYY-MM-DD date.",
            "2026-07-23", "Use the date this discovery evidence was captured.",
            "string", required=True,
        ),
        _semantic_field(
            "sequence_name", "Human-readable sequence name",
            "One concise name.", "Example sequence",
            "Name the repeatable outcome.", "string", required=True,
        ),
        _semantic_field(
            "outcome", "Intended sequence outcome",
            "One plain-language sentence.", "Complete the governed operation.",
            "Describe the observable result.", "string", required=True,
        ),
        _semantic_field(
            "why_repeatable", "Why this operation will recur",
            "One plain-language sentence.", "The same operation recurs.",
            "Describe the recurrence evidence.", "string", required=True,
        ),
        _semantic_field(
            "steps", "Zero-input script step",
            "Answer one script step's semantic subquestions at a time.",
            "a checked-in Python or shell script",
            "Do not provide command lines, flags, or arguments.", "object_list",
            item_fields=[
                _semantic_field(
                    "step", "Step label", "One lowercase hyphenated label.",
                    "run-example", "Use a unique concise label.", "string",
                    required=True,
                ),
                _semantic_field(
                    "repository_key", "Script repository",
                    "One registered repository name.", "memory-knowledge",
                    "Use the repository containing the script.", "string",
                    required=True,
                ),
                _semantic_field(
                    "script_path", "Checked-in zero-input script",
                    "One repository-relative .py or .sh path.",
                    "scripts/example.py",
                    "The script must launch its own semantic intake.",
                    "path", required=True,
                ),
                _semantic_field(
                    "result", "Required step result",
                    "One concise observable result.", "passed",
                    "State what successful completion returns.", "string",
                    required=True,
                ),
                _semantic_field(
                    "note", "Step correction note",
                    "One concise operational note.",
                    "Stops on the first validation failure.",
                    "Explain the stable boundary, not invocation syntax.",
                    "string", required=True,
                ),
            ],
        ),
        _semantic_field(
            "inputs", "Required semantic input",
            "One or more plain-language input descriptions.",
            "An approved repository checkout.",
            "Describe information, not flags or JSON.", "string_list",
            item_prompt="Required semantic input",
            item_response_format="One plain-language input description.",
            item_example="An approved task identity.",
            item_constraints="Do not provide invocation syntax.",
        ),
        _semantic_field(
            "failure_handling", "Failure handling",
            "One plain-language sentence.",
            "Stop on the first failure and retain its evidence.",
            "Describe the response without command syntax.", "string",
            required=True,
        ),
        _semantic_field(
            "verified_path", "Verification path",
            "One plain-language sentence.",
            "The zero-input script passes its focused tests.",
            "State how the same path is verified.", "string", required=True,
        ),
        _semantic_field(
            "repo_roots_file", "Optional repository-root registry",
            "One existing registry file path, or press Enter to omit it.",
            "operations/sequences/discovery/repositories.json",
            "Provide the path only; never paste its JSON.", "path",
        ),
    ],
}


def _required_text(answers: Mapping[str, Any], key: str) -> str:
    value = answers.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AdapterError(f"answer-required:{key}")
    return value


def _paths(answers: Mapping[str, Any], key: str) -> list[str]:
    raw = answers.get(key)
    if not isinstance(raw, list) or not raw:
        raise AdapterError(f"answer-required:{key}")
    paths: list[str] = []
    for value in raw:
        if not isinstance(value, str) or not value.strip():
            raise AdapterError(f"invalid-repository-path:{key}")
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or value.endswith("/"):
            raise AdapterError(f"invalid-repository-path:{key}")
        paths.append(value)
    if len(set(paths)) != len(paths):
        raise AdapterError(f"duplicate-repository-path:{key}")
    return paths


def _artifact(
    artifact_paths: Mapping[str, str],
    artifact_id: str,
    values: list[str],
) -> dict[str, str]:
    path = artifact_paths.get(artifact_id)
    if not isinstance(path, str) or not path:
        raise AdapterError(f"artifact-path-required:{artifact_id}")
    return {"content": "".join(f"{value}\n" for value in values), "path": path}


def _json_artifact(
    artifact_paths: Mapping[str, str],
    artifact_id: str,
    value: Any,
) -> dict[str, str]:
    path = artifact_paths.get(artifact_id)
    if not isinstance(path, str) or not path:
        raise AdapterError(f"artifact-path-required:{artifact_id}")
    return {
        "content": json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ) + "\n",
        "path": path,
    }


def _registered_repository(
    answers: Mapping[str, Any],
    repository_roots: Mapping[str, str],
    *,
    answer_key: str = "repository_key",
) -> tuple[str, str]:
    repository_key = _required_text(answers, answer_key)
    raw_repository = repository_roots.get(repository_key)
    if not isinstance(raw_repository, str) or not raw_repository:
        raise AdapterError(f"repository-key-unregistered:{repository_key}")
    return repository_key, str(Path(raw_repository).expanduser().resolve())


def _relative_repository_path(
    answers: Mapping[str, Any],
    key: str,
    repository_root: str,
) -> str:
    value = _required_text(answers, key)
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise AdapterError(f"invalid-repository-path:{key}")
    return str(Path(repository_root, *relative.parts).resolve())


def _script_payload(
    *,
    sequence_id: str,
    profile: str,
    argv: list[str],
    repository_key: str,
    repository_root: str,
    effectful: bool,
    operation: str,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "sequence_id": sequence_id,
        "profile": profile,
        "artifacts": {},
        "argv": argv,
        "authorization": {
            "effectful": effectful,
            "required": effectful,
            "operation": operation,
        },
        "repository": {
            "key": repository_key,
            "root": repository_root,
        },
    }
    if environment:
        payload["environment"] = dict(environment)
    return payload


def _prepare_commit_push(
    answers: Mapping[str, Any],
    artifact_paths: Mapping[str, str],
    repository_roots: Mapping[str, str],
) -> dict[str, Any]:
    operation = _required_text(answers, "operation")
    if operation not in COMMIT_PUSH_OPERATIONS:
        raise AdapterError("unsupported-commit-push-operation")
    expected = {"operation", "repository_key", "branch", "remote"}
    if operation in MANIFEST_OPERATIONS:
        expected.add("approved_paths")
    if operation in MESSAGE_OPERATIONS:
        expected.add("message")
    if operation in RESUME_OPERATIONS:
        expected.add("resume_commit")
    if operation in OVERLAY_OPERATIONS:
        expected.add("overlay_paths")
    if operation == "isolated-reconcile-and-resume":
        expected.update({"ledger_path", "generated_view_path"})
    if set(answers) != expected:
        raise AdapterError("answer-fields-do-not-match-operation")

    repository_key, repository = _registered_repository(answers, repository_roots)
    branch = _required_text(answers, "branch")
    remote = _required_text(answers, "remote")
    argv = [
        "python3", SCOPED_GIT_PUBLISH_SCRIPT,
        "--repo", repository,
    ]
    artifacts: dict[str, dict[str, str]] = {}
    if operation in MANIFEST_OPERATIONS:
        approved_paths = _paths(answers, "approved_paths")
        artifacts["approved_paths"] = _artifact(
            artifact_paths, "approved_paths", approved_paths,
        )
        argv.extend(["--manifest", artifacts["approved_paths"]["path"]])
    if operation in OVERLAY_OPERATIONS:
        overlay_paths = _paths(answers, "overlay_paths")
        if not set(overlay_paths).issubset(set(approved_paths)):
            raise AdapterError("overlay-paths-not-subset-of-approved-paths")
        artifacts["overlay_paths"] = _artifact(
            artifact_paths, "overlay_paths", overlay_paths,
        )
        argv.extend(["--overlay-manifest", artifacts["overlay_paths"]["path"]])
    if operation in MESSAGE_OPERATIONS:
        argv.extend(["--message", _required_text(answers, "message")])
    argv.extend(["--branch", branch, "--remote", remote])
    if operation in RESUME_OPERATIONS:
        argv.extend(["--resume-commit", _required_text(answers, "resume_commit")])
    if operation == "publish":
        argv.append("--execute")
    elif operation == "integrate-remote-and-resume":
        argv.append("--integrate-remote")
    elif operation == "isolated-integrate-and-resume":
        argv.append("--isolated-integrate-remote")
    elif operation == "isolated-reconcile-and-resume":
        argv.extend([
            "--ledger-path", _required_text(answers, "ledger_path"),
            "--generated-view-path",
            _required_text(answers, "generated_view_path"),
            "--isolated-reconcile-remote",
        ])
    return {
        "schema_version": 1,
        "sequence_id": "commit-push-main",
        "profile": operation,
        "artifacts": artifacts,
        "argv": argv,
        "repository": {
            "key": repository_key,
            "root": repository,
        },
        "authorization": {
            "effectful": operation != "dry-run",
            "required": operation != "dry-run",
            "operation": operation,
        },
    }


def _prepare_deploy(
    sequence_id: str,
    answers: Mapping[str, Any],
    repository_roots: Mapping[str, str],
) -> dict[str, Any]:
    config = DEPLOY_SEQUENCE_CONFIG[sequence_id]
    expected = {"repository_key", "verify"}
    if "api_base" in config:
        expected.add("api_base")
    if set(answers) != expected:
        raise AdapterError("answer-fields-do-not-match-deploy")
    repository_key, repository = _registered_repository(
        answers, repository_roots,
    )
    verify = answers.get("verify")
    if type(verify) is not bool:
        raise AdapterError("answer-required:verify")
    script_path = str(Path(repository, config["script"]))
    argv = ["bash", script_path]
    if "api_base" in config:
        api_base = _required_text(answers, "api_base")
        if not api_base.startswith("https://") or not api_base.rstrip("/").endswith("/api"):
            raise AdapterError("invalid-api-base")
        argv.extend(["--api-base", api_base])
    if not verify:
        argv.append("--no-verify")
    return _script_payload(
        sequence_id=sequence_id,
        profile="verified" if verify else "no-verify",
        argv=argv,
        repository_key=repository_key,
        repository_root=repository,
        effectful=True,
        operation="deploy",
    )


def _deploy_adapter(sequence_id: str) -> Adapter:
    return lambda answers, _artifact_paths, repository_roots: _prepare_deploy(
        sequence_id, answers, repository_roots,
    )


def _prepare_local_image(
    answers: Mapping[str, Any],
    _artifact_paths: Mapping[str, str],
    repository_roots: Mapping[str, str],
) -> dict[str, Any]:
    operation = _required_text(answers, "operation")
    if operation not in LOCAL_IMAGE_OPERATIONS:
        raise AdapterError("unsupported-local-image-operation")
    expected_by_operation = {
        "build": {"tag"},
        "run": {"tag", "container", "port", "port_file", "env_file"},
        "health": {"health_location", "timeout_seconds"},
        "copy-code-project": {
            "container", "code_repository_key", "source_relative_path",
            "destination",
        },
        "logs": {"container", "tail"},
        "stop": {"container"},
        "seed-codex-auth": {"container", "keyvault_name"},
        "seed-git-auth": {
            "container", "keyvault_name", "git_repository_key",
            "seed_port_file", "seed_timeout_seconds",
        },
        "probe-codex": {"container"},
        "require-real-memory-knowledge": set(),
    }
    expected = {
        "operation", "source_repository_key",
        *expected_by_operation[operation],
    }
    if operation == "health":
        location = _required_text(answers, "health_location")
        if location == "port":
            expected.add("health_port")
        elif location == "port-file":
            expected.add("health_port_file")
        else:
            raise AdapterError("invalid-health-location")
    if set(answers) != expected:
        raise AdapterError("answer-fields-do-not-match-local-image-operation")
    repository_key, repository = _registered_repository(
        answers, repository_roots, answer_key="source_repository_key",
    )
    script = str(Path(repository, "scripts/local_workflow_orch_image_harness.py"))
    argv = ["uv", "run", "python", script, operation]
    if operation in {"build", "run"}:
        argv.extend(["--tag", _required_text(answers, "tag")])
    if operation in {
        "copy-code-project", "logs", "stop", "seed-codex-auth",
        "seed-git-auth", "probe-codex",
    }:
        argv.extend(["--container", _required_text(answers, "container")])
    if operation == "run":
        # `run` names the container with --name, not --container: that is what the harness script
        # defines (local_workflow_orch_image_harness.py:658), what the registered sequence document
        # publishes, and what every historical caller uses. Emitting --container aborted the recreate
        # instantly with "the following arguments are required: --name", so a rebuilt image could
        # never be put into service (live 2026-07-29, blk-af452065311f7f6c0b7ebc6e).
        argv.extend(["--name", _required_text(answers, "container")])
        argv.extend(["--port", str(answers["port"])])
        if answers["port_file"] is not None:
            argv.extend(["--port-file", _required_text(answers, "port_file")])
        argv.extend(["--env-file", _required_text(answers, "env_file")])
    elif operation == "health":
        if answers["health_location"] == "port":
            argv.extend(["--port", str(answers["health_port"])])
        else:
            argv.extend([
                "--port-file", _required_text(answers, "health_port_file"),
            ])
        argv.extend(["--timeout-seconds", str(answers["timeout_seconds"])])
    elif operation == "copy-code-project":
        code_key, code_root = _registered_repository(
            answers, repository_roots, answer_key="code_repository_key",
        )
        source = _relative_repository_path(
            answers, "source_relative_path", code_root,
        )
        argv.extend([
            "--source", source,
            "--destination", _required_text(answers, "destination"),
        ])
        if code_key not in repository_roots:
            raise AdapterError(f"repository-key-unregistered:{code_key}")
    elif operation == "logs" and answers["tail"] is not None:
        argv.extend(["--tail", str(answers["tail"])])
    elif operation in {"seed-codex-auth", "seed-git-auth"}:
        argv.extend([
            "--keyvault-name", _required_text(answers, "keyvault_name"),
        ])
        if operation == "seed-git-auth":
            argv.extend([
                "--repository-key",
                _required_text(answers, "git_repository_key"),
                "--port-file", _required_text(answers, "seed_port_file"),
                "--health-timeout-seconds",
                str(answers["seed_timeout_seconds"]),
            ])
    elif operation == "require-real-memory-knowledge":
        argv.append("--real-memory-knowledge")
    effectful = operation in {
        "build", "run", "copy-code-project", "stop",
        "seed-codex-auth", "seed-git-auth",
    }
    return _script_payload(
        sequence_id="local-workflow-orch-image",
        profile=operation,
        argv=argv,
        repository_key=repository_key,
        repository_root=repository,
        effectful=effectful,
        operation=operation,
    )


def _prepare_greenfield(
    answers: Mapping[str, Any],
    _artifact_paths: Mapping[str, str],
    repository_roots: Mapping[str, str],
) -> dict[str, Any]:
    mode = _required_text(answers, "mode")
    if mode not in GREENFIELD_MODES:
        raise AdapterError("unsupported-greenfield-mode")
    expected = {
        "mode", "source_repository_key", "target_repository", "branch", "tag",
        "container", "port", "env_file", "skip_build", "skip_auth",
        "start_feature_index", "parallel_width",
    }
    if answers.get("skip_auth") is False:
        expected.add("keyvault_name")
    if mode == "start-from-spec":
        expected.update({"fresh", "spec_repository_key", "spec_relative_path"})
    else:
        expected.update({"decomposition_task_id", "decomposition_run_id"})
    if mode in {"resume-program", "validate-fresh"}:
        expected.update({"program_drive_id", "expected_spec_hash"})
    if set(answers) != expected:
        raise AdapterError("answer-fields-do-not-match-greenfield-mode")
    if type(answers["skip_build"]) is not bool or type(answers["skip_auth"]) is not bool:
        raise AdapterError("greenfield-boolean-answer-invalid")
    repository_key, repository = _registered_repository(
        answers, repository_roots, answer_key="source_repository_key",
    )
    script = str(Path(repository, "scripts/greenfield_full_drive.sh"))
    argv = [
        script,
        "--repo", _required_text(answers, "target_repository"),
        "--branch", _required_text(answers, "branch"),
        "--tag", _required_text(answers, "tag"),
        "--container", _required_text(answers, "container"),
        "--port", str(answers["port"]),
        "--env-file", _required_text(answers, "env_file"),
        "--start-feature-index", str(answers["start_feature_index"]),
        "--parallel-width", str(answers["parallel_width"]),
    ]
    if answers["skip_build"]:
        argv.append("--skip-build")
    if answers["skip_auth"]:
        argv.append("--skip-auth")
    else:
        argv.extend(["--keyvault", _required_text(answers, "keyvault_name")])
    if mode == "start-from-spec":
        _, spec_root = _registered_repository(
            answers, repository_roots, answer_key="spec_repository_key",
        )
        argv.extend([
            "--spec",
            _relative_repository_path(
                answers, "spec_relative_path", spec_root,
            ),
        ])
        if type(answers["fresh"]) is not bool:
            raise AdapterError("greenfield-fresh-answer-invalid")
        if not answers["fresh"]:
            argv.append("--no-fresh")
    else:
        argv.extend([
            "--drive-dag",
            "--decomposition-task-id",
            _required_text(answers, "decomposition_task_id"),
            "--decomposition-run-id",
            _required_text(answers, "decomposition_run_id"),
        ])
    if mode in {"resume-program", "validate-fresh"}:
        program_drive_id = _required_text(answers, "program_drive_id")
        expected_hash = _required_text(answers, "expected_spec_hash")
        if (
            len(program_drive_id) != 36
            or len(expected_hash) != 64
            or any(character not in "0123456789abcdef" for character in expected_hash)
        ):
            raise AdapterError("greenfield-durable-identity-invalid")
        argv.extend([
            "--resume-from-checkpoint",
            "--program-drive-id", program_drive_id,
            "--expected-spec-hash", expected_hash,
        ])
        if mode == "validate-fresh":
            argv.append("--validate-fresh")
    return _script_payload(
        sequence_id="greenfield-full-drive",
        profile=mode,
        argv=argv,
        repository_key=repository_key,
        repository_root=repository,
        effectful=True,
        operation="workflow-drive",
    )


def _prepare_claude_auth(
    answers: Mapping[str, Any],
    _artifact_paths: Mapping[str, str],
    repository_roots: Mapping[str, str],
) -> dict[str, Any]:
    operation = _required_text(answers, "operation")
    if operation not in CLAUDE_AUTH_OPERATIONS:
        raise AdapterError("unsupported-claude-auth-operation")
    expected = {"operation", "source_repository_key", "dry_run"}
    credential_operations = {"seed-local", "seed-host", "push-kv", "all"}
    if operation in credential_operations:
        expected.update({"credential_source", "config_source"})
        if answers.get("credential_source") == "runtime-temp-file":
            expected.add("token_file")
        if answers.get("config_source") == "runtime-temp-file":
            expected.add("config_file")
    if operation in {"status", "seed-local", "seed-host", "verify", "all"}:
        expected.add("container")
    if operation in {"status", "push-kv", "verify", "all"}:
        expected.add("keyvault_name")
    if operation in {"reseed-azure", "verify", "all"}:
        expected.add("deployment")
    if operation == "verify":
        expected.add("verify_targets")
    if set(answers) != expected:
        raise AdapterError("answer-fields-do-not-match-claude-auth-operation")
    if type(answers["dry_run"]) is not bool:
        raise AdapterError("claude-auth-dry-run-answer-invalid")
    repository_key, repository = _registered_repository(
        answers, repository_roots, answer_key="source_repository_key",
    )
    script = str(Path(repository, "scripts/claude_auth_refresh.sh"))
    argv = [script, operation]
    if answers.get("credential_source") == "runtime-temp-file":
        argv.extend(["--token-file", _required_text(answers, "token_file")])
    if answers.get("config_source") == "runtime-temp-file":
        argv.extend(["--config-file", _required_text(answers, "config_file")])
    if "container" in answers:
        argv.extend(["--container", _required_text(answers, "container")])
    if "keyvault_name" in answers:
        argv.extend(["--keyvault", _required_text(answers, "keyvault_name")])
    if "deployment" in answers:
        deployment = _required_text(answers, "deployment")
        if not deployment.startswith("https://"):
            raise AdapterError("invalid-deployment-url")
        argv.extend(["--deployment", deployment])
    if operation == "verify":
        targets = answers["verify_targets"]
        allowed_targets = {"local-container", "host", "remote-claude"}
        if (
            not isinstance(targets, list) or not targets
            or len(set(targets)) != len(targets)
            or not set(targets).issubset(allowed_targets)
        ):
            raise AdapterError("invalid-verify-targets")
        for target in targets:
            argv.extend(["--verify-targets", target])
    if answers["dry_run"]:
        argv.append("--dry-run")
    effectful = (
        operation not in {"status", "verify"}
        and not answers["dry_run"]
    )
    return _script_payload(
        sequence_id="claude-auth-token-refresh",
        profile=operation,
        argv=argv,
        repository_key=repository_key,
        repository_root=repository,
        effectful=effectful,
        operation="auth",
    )


def _prepare_offline_sequence(
    sequence_id: str,
    answers: Mapping[str, Any],
    repository_roots: Mapping[str, str],
) -> dict[str, Any]:
    config = OFFLINE_SEQUENCE_CONFIG[sequence_id]
    operation = _required_text(answers, "operation")
    if operation not in config["operations"]:
        raise AdapterError("unsupported-offline-operation")
    expected = {"operation", "source_repository_key"}
    if sequence_id == "airgapped-local-bulgarian-stt":
        expected.add("model")
        if operation != "provision":
            expected.add("audio")
    elif sequence_id == "airgapped-llm-judge":
        expected.add("model")
        if operation == "smoke":
            expected.add("audio")
    elif sequence_id == "secure-landing-seed":
        expected.add("landing_directory")
        if operation in {"seed", "verify"}:
            expected.add("source_directory")
        if operation == "scrub":
            expected.add("scrub_scope")
            if answers.get("scrub_scope") == "one-recording":
                expected.add("recording")
    elif (
        sequence_id == "callcenter-harness-engine-invariants"
        and operation == "redaction-smoke"
    ):
        expected.add("audio")
    if set(answers) != expected:
        raise AdapterError("answer-fields-do-not-match-offline-operation")
    repository_key, repository = _registered_repository(
        answers, repository_roots, answer_key="source_repository_key",
    )
    environment: dict[str, str] = {}
    home_venv_python = str(
        Path.home() / ".callcenter-harness/venv/bin/python"
    )
    if sequence_id == "airgapped-local-bulgarian-stt":
        model = _required_text(answers, "model")
        if model not in {"small", "large-v3"}:
            raise AdapterError("invalid-stt-model")
        environment["STT_MODEL"] = model
        argv = [str(Path(repository, config["script"])), operation]
        if operation != "provision":
            argv.append(_required_text(answers, "audio"))
        effectful = operation in {"provision", "channels", "process", "all"}
    elif sequence_id == "airgapped-redaction-stack":
        argv = [str(Path(repository, config["script"])), operation]
        effectful = operation == "provision"
    elif sequence_id == "airgapped-llm-judge":
        model = _required_text(answers, "model")
        environment["JUDGE_MODEL"] = model
        if operation == "smoke":
            judge = str(Path(repository, "scripts/judge_ollama.py"))
            argv = [
                home_venv_python,
                str(Path(repository, "scripts/cc_command_eval_smoke.py")),
                _required_text(answers, "audio"),
            ]
            environment.update({
                "CC_HARNESS_AGENT_COMMAND": (
                    f"python3 {judge} --model {model}"
                ),
                "PYTHONPATH": str(Path(repository, "src")),
                "HF_HUB_OFFLINE": "1",
                "NO_PROXY": "127.0.0.1",
                "HTTPS_PROXY": "http://127.0.0.1:9",
            })
            effectful = True
        else:
            argv = [str(Path(repository, config["script"])), operation]
            if operation == "verify":
                environment.update({
                    "NO_PROXY": "127.0.0.1",
                    "HTTPS_PROXY": "http://127.0.0.1:9",
                })
            effectful = operation == "provision"
    elif sequence_id == "secure-landing-seed":
        environment["LANDING"] = _required_text(
            answers, "landing_directory",
        )
        if operation in {"seed", "verify"}:
            environment["SRC"] = _required_text(
                answers, "source_directory",
            )
        if operation == "scrub":
            target = (
                "all" if answers["scrub_scope"] == "all"
                else _required_text(answers, "recording")
            )
            argv = [
                home_venv_python,
                str(Path(repository, "scripts/scrub_and_retire.py")),
                target,
            ]
            environment.update({
                "PYTHONPATH": str(Path(repository, "src")),
                "HF_HUB_OFFLINE": "1",
            })
            effectful = True
        else:
            argv = [str(Path(repository, config["script"])), operation]
            effectful = operation == "seed"
    else:
        environment["PYTHONPATH"] = str(Path(repository, "src"))
        if operation == "unit":
            argv = ["python3", str(Path(repository, config["script"]))]
            effectful = False
        else:
            argv = [
                home_venv_python,
                str(Path(repository, "scripts/cc_redact_smoke.py")),
                _required_text(answers, "audio"),
            ]
            environment["HF_HUB_OFFLINE"] = "1"
            effectful = True
    return _script_payload(
        sequence_id=sequence_id,
        profile=operation,
        argv=argv,
        repository_key=repository_key,
        repository_root=repository,
        effectful=effectful,
        operation=operation,
        environment=environment,
    )


def _prepare_scoped_context(
    answers: Mapping[str, Any],
    _artifact_paths: Mapping[str, str],
    repository_roots: Mapping[str, str],
) -> dict[str, Any]:
    operation = _required_text(answers, "operation")
    if operation not in {"prepare", "check", "verify", "cancel", "self-check"}:
        raise AdapterError("unsupported-scoped-context-operation")
    expected = {"operation", "source_repository_key"}
    if operation != "self-check":
        expected.add("receipt")
    if operation == "prepare":
        expected.update({
            "target_repository_key", "target", "anchor", "allowed_paths",
            "required_after", "forbidden_after",
        })
    if set(answers) != expected:
        raise AdapterError("answer-fields-do-not-match-scoped-context-operation")
    source_key, source_root = _registered_repository(
        answers, repository_roots, answer_key="source_repository_key",
    )
    script = str(Path(source_root, "scripts/context_edit_guard.py"))
    argv = ["python3", script, operation]
    if operation == "prepare":
        _, target_root = _registered_repository(
            answers, repository_roots, answer_key="target_repository_key",
        )
        target = _required_text(answers, "target")
        _relative_repository_path(answers, "target", target_root)
        allowed = _paths(answers, "allowed_paths")
        argv.extend([
            "--repo-root", target_root,
            "--target", target,
            "--anchor", _required_text(answers, "anchor"),
            "--anchor-count", "1",
            "--receipt", _required_text(answers, "receipt"),
        ])
        for path in allowed:
            argv.extend(["--allow", path])
        if answers["required_after"] is not None:
            argv.extend([
                "--require-after", _required_text(answers, "required_after"),
            ])
        if answers["forbidden_after"] is not None:
            argv.extend([
                "--forbid-after", _required_text(answers, "forbidden_after"),
            ])
    elif operation != "self-check":
        argv.extend(["--receipt", _required_text(answers, "receipt")])
    return _script_payload(
        sequence_id="scoped-context-edit",
        profile=operation,
        argv=argv,
        repository_key=source_key,
        repository_root=source_root,
        effectful=operation != "self-check",
        operation=operation,
    )


def _prepare_discovery_reconciliation(
    answers: Mapping[str, Any],
    _artifact_paths: Mapping[str, str],
    repository_roots: Mapping[str, str],
) -> dict[str, Any]:
    operation = _required_text(answers, "operation")
    fields = {
        "audit": {"output"},
        "validate": {"manifest"},
        "execute": {"manifest"},
        "execute-rolling": {"output_directory"},
        "drive": {"task_id", "output_root"},
    }
    if operation not in fields:
        raise AdapterError("unsupported-discovery-reconciliation-operation")
    expected = {"operation", "source_repository_key", *fields[operation]}
    if set(answers) != expected:
        raise AdapterError(
            "answer-fields-do-not-match-discovery-reconciliation-operation"
        )
    repository_key, repository = _registered_repository(
        answers, repository_roots, answer_key="source_repository_key",
    )
    script = str(Path(
        repository, "scripts/discovery_candidate_reconciliation.py",
    ))
    argv = ["python3", script, "--root", repository, operation]
    if operation == "audit":
        argv.extend(["--output", _required_text(answers, "output")])
    elif operation == "validate":
        argv.extend(["--manifest", _required_text(answers, "manifest")])
    elif operation == "execute":
        argv.extend([
            "--manifest", _required_text(answers, "manifest"),
            "--active-index",
            str(Path(repository, "operations/sequences/discovery/ACTIVE.md")),
        ])
    elif operation == "execute-rolling":
        argv.extend([
            "--baseline",
            str(Path(
                repository,
                "operations/sequences/discovery/reconciliation-policy.json",
            )),
            "--output-dir", _required_text(answers, "output_directory"),
            "--active-index",
            str(Path(repository, "operations/sequences/discovery/ACTIVE.md")),
            "--max-attempts", "6",
        ])
    else:
        argv.extend([
            "--task-id", _required_text(answers, "task_id"),
            "--output-root", _required_text(answers, "output_root"),
        ])
    return _script_payload(
        sequence_id="discovery-candidate-reconciliation",
        profile=operation,
        argv=argv,
        repository_key=repository_key,
        repository_root=repository,
        effectful=operation in {"execute", "execute-rolling", "drive"},
        operation=operation,
    )


def _prepare_blocker_backlog_reconciliation(
    answers: Mapping[str, Any],
    _artifact_paths: Mapping[str, str],
    repository_roots: Mapping[str, str],
) -> dict[str, Any]:
    operation = _required_text(answers, "operation")
    fields = {
        "audit": {"output"},
        "validate": {"manifest"},
        "execute": {"manifest", "run_id"},
    }
    if operation not in fields:
        raise AdapterError("unsupported-blocker-backlog-operation")
    expected = {"operation", "source_repository_key", *fields[operation]}
    if set(answers) != expected:
        raise AdapterError(
            "answer-fields-do-not-match-blocker-backlog-operation"
        )
    repository_key, repository = _registered_repository(
        answers, repository_roots, answer_key="source_repository_key",
    )
    argv = [
        "python3",
        str(Path(repository, "scripts/blocker_backlog_reconciliation.py")),
        "--root", repository, operation,
    ]
    if operation == "audit":
        argv.extend(["--output", _required_text(answers, "output")])
    else:
        argv.extend(["--manifest", _required_text(answers, "manifest")])
        if operation == "execute":
            argv.extend([
                "--run-id", _required_text(answers, "run_id"),
                "--active-index",
                str(Path(repository, "operations/blockers/ACTIVE.md")),
            ])
    return _script_payload(
        sequence_id="blocker-backlog-reconciliation",
        profile=operation,
        argv=argv,
        repository_key=repository_key,
        repository_root=repository,
        effectful=operation == "execute",
        operation=operation,
    )


def _changed_artifacts(
    answers: Mapping[str, Any],
    repository_roots: Mapping[str, str],
) -> list[dict[str, str]]:
    raw = answers.get("changed_artifacts")
    if not isinstance(raw, list) or not raw:
        raise AdapterError("answer-required:changed_artifacts")
    normalized: list[dict[str, str]] = []
    for item in raw:
        if (
            not isinstance(item, Mapping)
            or set(item) != {"repository_key", "path"}
        ):
            raise AdapterError("invalid-changed-artifact")
        repository_key = _required_text(item, "repository_key")
        if repository_key not in repository_roots:
            raise AdapterError(
                f"repository-key-unregistered:{repository_key}"
            )
        path = _required_text(item, "path")
        relative = PurePosixPath(path)
        if relative.is_absolute() or ".." in relative.parts:
            raise AdapterError("invalid-changed-artifact")
        normalized.append({
            "repository_key": repository_key,
            "path": path,
        })
    if len({
        (item["repository_key"], item["path"]) for item in normalized
    }) != len(normalized):
        raise AdapterError("duplicate-changed-artifact")
    return normalized


def _correction_ids(answers: Mapping[str, Any]) -> list[str]:
    raw = answers.get("supersedes_correction_ids", [])
    if not isinstance(raw, list):
        raise AdapterError("invalid-supersedes-correction-ids")
    normalized: list[str] = []
    for value in raw:
        if not isinstance(value, str):
            raise AdapterError("invalid-supersedes-correction-id")
        try:
            normalized.append(str(UUID(value)))
        except ValueError as exc:
            raise AdapterError(
                "invalid-supersedes-correction-id"
            ) from exc
    if len(set(normalized)) != len(normalized):
        raise AdapterError("duplicate-supersedes-correction-id")
    return normalized


def _prepare_discovery_promotion(
    answers: Mapping[str, Any],
    artifact_paths: Mapping[str, str],
    repository_roots: Mapping[str, str],
) -> dict[str, Any]:
    operation = _required_text(answers, "operation")
    if operation not in {"status", "drive", "correct", "correct-registered"}:
        raise AdapterError("unsupported-discovery-promotion-operation")
    expected = {"operation", "source_repository_key", "repo_roots_file"}
    if operation in {"status", "drive", "correct"}:
        expected.update({"discovery_file", "sequence_id"})
    else:
        expected.add("subject_id")
    if operation == "drive":
        expected.update({
            "use_when", "operation_kinds", "automation_display", "pass_signal",
        })
    if operation in {"correct", "correct-registered"}:
        expected.update({
            "task_id", "solution", "changed_artifacts",
            "reusable_behavior_changed", "superseding",
        })
        if answers.get("superseding") is True:
            expected.add("supersedes_correction_ids")
    if set(answers) != expected:
        raise AdapterError(
            "answer-fields-do-not-match-discovery-promotion-operation"
        )
    repository_key, repository = _registered_repository(
        answers, repository_roots, answer_key="source_repository_key",
    )
    script = str(Path(repository, "scripts/discovery_promotion_lifecycle.py"))
    argv = ["python3", script, operation]
    if operation in {"status", "drive", "correct"}:
        argv.extend([
            "--file", _required_text(answers, "discovery_file"),
            "--sequence-id", _required_text(answers, "sequence_id"),
        ])
    else:
        argv.extend(["--subject-id", _required_text(answers, "subject_id")])
    argv.extend(["--root", repository])
    if answers["repo_roots_file"] is not None:
        argv.extend([
            "--repo-roots-file",
            _required_text(answers, "repo_roots_file"),
        ])
    artifacts: dict[str, dict[str, str]] = {}
    if operation == "drive":
        kinds = answers["operation_kinds"]
        if (
            not isinstance(kinds, list) or not kinds
            or len(set(kinds)) != len(kinds)
            or not set(kinds).issubset(OPERATION_KINDS)
        ):
            raise AdapterError("invalid-operation-kinds")
        argv.extend(["--use-when", _required_text(answers, "use_when")])
        for kind in kinds:
            argv.extend(["--operation-kind", kind])
        argv.extend([
            "--automation-display",
            _required_text(answers, "automation_display"),
            "--pass-signal", _required_text(answers, "pass_signal"),
            "--max-qualification-runs", "3",
        ])
    elif operation in {"correct", "correct-registered"}:
        reusable_behavior_changed = answers["reusable_behavior_changed"]
        superseding = answers["superseding"]
        if not isinstance(reusable_behavior_changed, bool):
            raise AdapterError("invalid-reusable-behavior-changed")
        if not isinstance(superseding, bool):
            raise AdapterError("invalid-superseding")
        correction_ids = _correction_ids(answers)
        if superseding != bool(correction_ids):
            raise AdapterError("superseding-answer-mismatch")
        artifacts["changed_artifacts"] = _json_artifact(
            artifact_paths,
            "changed_artifacts",
            _changed_artifacts(answers, repository_roots),
        )
        if answers["task_id"] is not None:
            argv.extend(["--task-id", _required_text(answers, "task_id")])
        argv.extend([
            "--solution", _required_text(answers, "solution"),
            "--changed-artifacts-file",
            artifacts["changed_artifacts"]["path"],
            "--reusable-behavior-changed",
            "yes" if reusable_behavior_changed else "no",
        ])
        for correction_id in correction_ids:
            argv.extend(["--supersedes-correction-id", correction_id])
    payload = _script_payload(
        sequence_id="discovery-promotion-lifecycle",
        profile=operation,
        argv=argv,
        repository_key=repository_key,
        repository_root=repository,
        effectful=operation != "status",
        operation=operation,
    )
    payload["artifacts"] = artifacts
    return payload


def _json_object_file(path_value: str, error: str) -> dict[str, Any]:
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise AdapterError(error)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdapterError(error) from exc
    if not isinstance(value, dict):
        raise AdapterError(error)
    return value


def _prepare_convergence_checkpoint(
    answers: Mapping[str, Any],
    _artifact_paths: Mapping[str, str],
    repository_roots: Mapping[str, str],
) -> dict[str, Any]:
    expected = {
        "source_repository_key", "state", "approval_id",
        "child_intent_file", "stage",
    }
    if set(answers) != expected:
        raise AdapterError("answer-fields-do-not-match-convergence-checkpoint")
    repository_key, repository = _registered_repository(
        answers, repository_roots, answer_key="source_repository_key",
    )
    child_intent = _json_object_file(
        _required_text(answers, "child_intent_file"),
        "child-intent-file-invalid",
    )
    required_child_fields = {
        "child_owner_sequence_id", "child_contract_sha256",
        "child_intent_id", "child_parameters", "guard_receipt_id",
    }
    if (
        set(child_intent) != required_child_fields
        or not isinstance(child_intent.get("child_parameters"), list)
        or any(
            not isinstance(child_intent.get(key), str)
            or not child_intent[key]
            for key in required_child_fields - {"child_parameters"}
        )
    ):
        raise AdapterError("child-intent-file-invalid")
    stage = _required_text(answers, "stage")
    if stage not in {"research", "plan", "implementation", "review"}:
        raise AdapterError("invalid-convergence-stage")
    argv = [
        "python3",
        str(Path(repository, "scripts/convergence_checkpoint_run.py")),
        "--state", _required_text(answers, "state"),
        "--repo", repository,
        "--approval-id", _required_text(answers, "approval_id"),
        "--child-intent-json",
        json.dumps(
            child_intent, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False,
        ),
        "--stage", stage,
        "--lock-timeout-seconds", "30",
    ]
    return _script_payload(
        sequence_id="convergence-checkpoint-run",
        profile="default",
        argv=argv,
        repository_key=repository_key,
        repository_root=repository,
        effectful=True,
        operation="checkpoint-and-dispatch",
    )


REVIEW_OPERATION_KEYS = {
    kind: fields - {"operation_id", "kind"}
    for kind, fields in {
        "record-gap": {
            "operation_id", "kind", "id", "requirement_ids",
            "source_stage", "impact", "evidence",
        },
        "grant-autonomy": {
            "operation_id", "kind", "id", "repository_keys",
            "allowed_paths", "stage", "evidence",
            "authority_approval_receipt_id",
        },
        "grant-scope-change": {
            "operation_id", "kind", "id", "repository_keys",
            "allowed_paths", "stage", "evidence",
            "authority_approval_receipt_id",
        },
        "accept-baseline": {
            "operation_id", "kind", "repository_key", "changed_paths",
            "approval_id", "stage", "accept_approved_dirty_overlap",
        },
        "guard-baseline": {"operation_id", "kind"},
        "record-stage": {"operation_id", "kind", "result_file"},
        "transition": {"operation_id", "kind", "to"},
        "check": {"operation_id", "kind"},
        "status": {"operation_id", "kind"},
    }.items()
}


def _review_state_path(reference: str, repository: str) -> Path:
    token, separator, relative = reference.partition("/")
    roots = {
        "runtime-temp": Path("/private/tmp"),
        "task-artifact-root": Path(repository, "Tasks"),
    }
    root = roots.get(token)
    if root is None or not separator:
        raise AdapterError("invalid-trusted-state-reference")
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise AdapterError("invalid-trusted-state-reference") from exc
    if not path.is_file():
        raise AdapterError("convergence-state-file-not-found")
    return path


def _review_operations(
    answers: Mapping[str, Any],
    repository_roots: Mapping[str, str],
    request_seed: str,
) -> list[dict[str, Any]]:
    raw = answers.get("operations")
    if not isinstance(raw, list) or not raw:
        raise AdapterError("answer-required:operations")
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise AdapterError("invalid-review-operation")
        kind = _required_text(item, "kind")
        fields = REVIEW_OPERATION_KEYS.get(kind)
        if fields is None or set(item) != {"kind", *fields}:
            raise AdapterError(f"invalid-review-operation-fields:{kind}")
        operation = dict(item)
        for key in (
            "requirement_ids", "repository_keys", "allowed_paths",
            "changed_paths",
        ):
            if key in operation:
                operation[key] = _paths(operation, key) if key in {
                    "allowed_paths", "changed_paths",
                } else _paths_like_text(operation, key)
        if "repository_keys" in operation and not set(
            operation["repository_keys"]
        ).issubset(repository_roots):
            raise AdapterError("review-operation-repository-unregistered")
        if (
            "accept_approved_dirty_overlap" in operation
            and not isinstance(operation["accept_approved_dirty_overlap"], bool)
        ):
            raise AdapterError("invalid-accept-approved-dirty-overlap")
        operation_id = str(uuid5(
            NAMESPACE_URL,
            f"{request_seed}:{index}:"
            + json.dumps(
                operation, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False,
            ),
        ))
        normalized.append({"operation_id": operation_id, **operation})
    return normalized


def _paths_like_text(
    answers: Mapping[str, Any],
    key: str,
) -> list[str]:
    raw = answers.get(key)
    if not isinstance(raw, list) or not raw:
        raise AdapterError(f"answer-required:{key}")
    values = [_required_text({"value": value}, "value") for value in raw]
    if len(set(values)) != len(values):
        raise AdapterError(f"duplicate-answer:{key}")
    return values


def _prepare_convergence_review(
    answers: Mapping[str, Any],
    artifact_paths: Mapping[str, str],
    repository_roots: Mapping[str, str],
) -> dict[str, Any]:
    expected = {
        "operation", "source_repository_key", "state",
        "expected_final_status", "operations",
    }
    if set(answers) != expected:
        raise AdapterError("answer-fields-do-not-match-convergence-review")
    mode = _required_text(answers, "operation")
    if mode not in {"dry-run", "apply"}:
        raise AdapterError("unsupported-convergence-review-operation")
    repository_key, repository = _registered_repository(
        answers, repository_roots, answer_key="source_repository_key",
    )
    state_reference = _required_text(answers, "state")
    state_path = _review_state_path(state_reference, repository)
    state_sha256 = hashlib.sha256(state_path.read_bytes()).hexdigest()
    expected_status = _required_text(answers, "expected_final_status")
    if expected_status not in {
        "research", "plan", "implementation", "review", "blocked",
        "cap_reached", "complete",
    }:
        raise AdapterError("invalid-expected-final-status")
    request_seed = json.dumps({
        "state": state_reference,
        "initial_state_sha256": state_sha256,
        "expected_final_status": expected_status,
        "operations": answers["operations"],
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    request_id = str(uuid5(NAMESPACE_URL, request_seed))
    request = {
        "schema_version": 2,
        "request_id": request_id,
        "state": state_reference,
        "initial_state_sha256": state_sha256,
        "expected_final_status": expected_status,
        "operations": _review_operations(
            answers, repository_roots, request_id,
        ),
    }
    request_artifact = _json_artifact(
        artifact_paths, "request", request,
    )
    argv = [
        "python3",
        str(Path(repository, "scripts/convergence_state_review_cycle.py")),
        "apply", "--request", request_artifact["path"],
    ]
    if mode == "dry-run":
        argv.append("--dry-run")
    payload = _script_payload(
        sequence_id="convergence-state-review-cycle",
        profile=mode,
        argv=argv,
        repository_key=repository_key,
        repository_root=repository,
        effectful=mode == "apply",
        operation=mode,
    )
    payload["artifacts"] = {"request": request_artifact}
    return payload


def _prepare_taggable_reload(
    answers: Mapping[str, Any],
    _artifact_paths: Mapping[str, str],
    repository_roots: Mapping[str, str],
) -> dict[str, Any]:
    expected = {
        "repository_key", "export_directory", "source_record_id",
        "webjob_missing", "manage_database_tier",
    }
    if set(answers) != expected:
        raise AdapterError("answer-fields-do-not-match-taggable-reload")
    repository_key, repository = _registered_repository(
        answers, repository_roots,
    )
    source_record_id = answers["source_record_id"]
    if (
        not isinstance(source_record_id, int)
        or isinstance(source_record_id, bool)
        or source_record_id < 1
    ):
        raise AdapterError("invalid-source-record-id")
    for key in ("webjob_missing", "manage_database_tier"):
        if not isinstance(answers[key], bool):
            raise AdapterError(f"invalid-{key.replace('_', '-')}")
    argv = [
        "bash",
        str(Path(
            repository,
            "tools/Taggable.MigrationRunner/scripts/reload-source.sh",
        )),
        "--export-dir", _required_text(answers, "export_directory"),
        "--srid", str(source_record_id),
    ]
    if answers["webjob_missing"]:
        argv.append("--redeploy-webjob")
    if not answers["manage_database_tier"]:
        argv.append("--no-scale")
    return _script_payload(
        sequence_id="taggable-source-reload",
        profile="reload",
        argv=argv,
        repository_key=repository_key,
        repository_root=repository,
        effectful=True,
        operation="reload",
    )


def _prepare_github_refresh(
    answers: Mapping[str, Any],
    _artifact_paths: Mapping[str, str],
    repository_roots: Mapping[str, str],
) -> dict[str, Any]:
    expected = {
        "repository_key", "server_url", "operator_env", "actor_email",
        "durability", "operation",
    }
    if set(answers) != expected:
        raise AdapterError("answer-fields-do-not-match-github-refresh")
    repository_key, repository = _registered_repository(
        answers, repository_roots,
    )
    durability = _required_text(answers, "durability")
    operation = _required_text(answers, "operation")
    if durability not in {"durable", "local-only"}:
        raise AdapterError("invalid-refresh-durability")
    if operation not in {"dry-run", "refresh"}:
        raise AdapterError("invalid-refresh-operation")
    server_url = _required_text(answers, "server_url")
    if not server_url.startswith("wss://"):
        raise AdapterError("server-url-must-use-wss")
    argv = [
        "python3",
        str(Path(repository, "scripts/github_app_repos_refresh.py")),
        "--server-url", server_url,
        "--operator-env", _required_text(answers, "operator_env"),
        "--actor-email", _required_text(answers, "actor_email"),
        "--auth-auto-refresh", "--no-interactive",
    ]
    if durability == "local-only":
        argv.append("--allow-local-only")
    if operation == "dry-run":
        argv.append("--dry-run")
    return _script_payload(
        sequence_id="github-app-repos-refresh",
        profile=f"{operation}-{durability}",
        argv=argv,
        repository_key=repository_key,
        repository_root=repository,
        effectful=operation == "refresh",
        operation=operation,
    )


MAWF_ACTION_FIELDS = {
    "infra": {"code_project_source", "rebuild_image"},
    "start": {
        "task_guid", "code_repository", "prompt_file", "task_action", "branch",
    },
    "poll": {"task_guid", "run_id"},
    "approve-start": {"task_guid", "run_id", "workflow_name"},
    "answer-gate": {"task_guid", "run_id", "workflow_name"},
    "decision": {"task_guid", "code_repository", "branch"},
    "continue": {
        "task_guid", "code_repository", "branch", "completed_workflow",
    },
    "repair": {
        "task_guid", "code_repository", "branch", "completed_workflow",
    },
    "drive": {"task_guid", "code_repository", "branch"},
}


def _prepare_mawf(
    sequence_id: str,
    gate_policy: str,
    answers: Mapping[str, Any],
    repository_roots: Mapping[str, str],
) -> dict[str, Any]:
    action = _required_text(answers, "action")
    fields = MAWF_ACTION_FIELDS.get(action)
    if fields is None:
        raise AdapterError("unsupported-mawf-action")
    expected = {"repository_key", "action", "dry_run", *fields}
    if set(answers) != expected:
        raise AdapterError("answer-fields-do-not-match-mawf-action")
    repository_key, repository = _registered_repository(
        answers, repository_roots,
    )
    script = str(Path(repository, "scripts/mawf_playbook_test_sequence.py"))
    argv = ["uv", "run", "python", script, action]
    if action == "infra":
        argv.extend([
            "--code-project-source",
            _required_text(answers, "code_project_source"),
        ])
        if answers["rebuild_image"] is False:
            argv.append("--skip-build")
        elif answers["rebuild_image"] is not True:
            raise AdapterError("invalid-rebuild-image")
    else:
        argv.extend(["--task-guid", _required_text(answers, "task_guid")])
        if "run_id" in fields:
            argv.extend(["--run-id", _required_text(answers, "run_id")])
        if "workflow_name" in fields:
            argv.extend([
                "--workflow-name",
                _required_text(answers, "workflow_name"),
            ])
        if "code_repository" in fields:
            argv.extend([
                "--repo", _required_text(answers, "code_repository"),
            ])
        if "prompt_file" in fields:
            argv.extend([
                "--prompt-file", _required_text(answers, "prompt_file"),
            ])
        if "task_action" in fields:
            argv.extend([
                "--task-action", _required_text(answers, "task_action"),
            ])
        if "branch" in fields:
            argv.extend(["--branch", _required_text(answers, "branch")])
        if (
            "completed_workflow" in fields
            and answers["completed_workflow"] is not None
        ):
            argv.extend([
                "--completed-workflow",
                _required_text(answers, "completed_workflow"),
            ])
        if action in {"start", "answer-gate", "drive"}:
            argv.extend(["--gate-policy", gate_policy])
    dry_run = answers["dry_run"]
    if not isinstance(dry_run, bool):
        raise AdapterError("invalid-dry-run")
    if dry_run:
        argv.append("--dry-run")
    return _script_payload(
        sequence_id=sequence_id,
        profile=action,
        argv=argv,
        repository_key=repository_key,
        repository_root=repository,
        effectful=not dry_run and action not in {"poll", "decision"},
        operation=action,
    )


def _mawf_adapter(sequence_id: str, policy: str) -> Adapter:
    return lambda answers, _artifact_paths, repository_roots: _prepare_mawf(
        sequence_id, policy, answers, repository_roots,
    )


def _prepare_mawf_blocker(
    answers: Mapping[str, Any],
    _artifact_paths: Mapping[str, str],
    repository_roots: Mapping[str, str],
) -> dict[str, Any]:
    action = _required_text(answers, "action")
    action_fields = {
        "record-blocker": {
            "workflow_name", "run_id", "gate_policy", "blocker_id", "summary",
            "evidence_file",
        },
        "resume": {"task_guid", "workflow_name", "run_id", "dry_run"},
        "restart-workflow": {
            "task_guid", "workflow_name", "code_repository",
            "prompt_file", "dry_run",
        },
        "start-over": {
            "task_guid", "code_repository", "prompt_file",
            "gate_policy", "dry_run",
        },
    }.get(action)
    if action_fields is None:
        raise AdapterError("unsupported-mawf-blocker-action")
    if set(answers) != {"repository_key", "action", *action_fields}:
        raise AdapterError("answer-fields-do-not-match-mawf-blocker-action")
    repository_key, repository = _registered_repository(
        answers, repository_roots,
    )
    script = str(Path(repository, "scripts/mawf_playbook_test_sequence.py"))
    if action == "record-blocker":
        argv = [
            "uv", "run", "python", script, "record-blocker",
            "--rp-id", _required_text(answers, "blocker_id"),
            "--workflow", _required_text(answers, "workflow_name"),
            "--run-id", _required_text(answers, "run_id"),
            "--gate-policy", _required_text(answers, "gate_policy"),
            "--summary", _required_text(answers, "summary"),
            "--evidence-file", _required_text(answers, "evidence_file"),
        ]
        effectful = True
    else:
        argv = [
            "uv", "run", "python", script, "reenter",
            "--mode", action,
            "--task-guid", _required_text(answers, "task_guid"),
        ]
        if "workflow_name" in answers:
            argv.extend([
                "--workflow-name",
                _required_text(answers, "workflow_name"),
            ])
        if "run_id" in answers:
            argv.extend(["--run-id", _required_text(answers, "run_id")])
        if "code_repository" in answers:
            argv.extend([
                "--repo", _required_text(answers, "code_repository"),
            ])
        if "prompt_file" in answers:
            argv.extend([
                "--prompt-file", _required_text(answers, "prompt_file"),
            ])
        if "gate_policy" in answers:
            argv.extend([
                "--gate-policy", _required_text(answers, "gate_policy"),
            ])
        dry_run = answers["dry_run"]
        if not isinstance(dry_run, bool):
            raise AdapterError("invalid-dry-run")
        if dry_run:
            argv.append("--dry-run")
        effectful = not dry_run
    return _script_payload(
        sequence_id="mawf-playbook-blocker-reentry",
        profile=action,
        argv=argv,
        repository_key=repository_key,
        repository_root=repository,
        effectful=effectful,
        operation=action,
    )


def _prepare_greenfield_recreate(
    answers: Mapping[str, Any],
    _artifact_paths: Mapping[str, str],
    repository_roots: Mapping[str, str],
) -> dict[str, Any]:
    expected = {
        "repository_key", "feature_repository", "program_drive_id",
        "decomposition_task_id", "rebuild_image", "container", "image_tag",
        "port", "keyvault", "start_feature_index", "parallel_width",
        "expected_spec_hash",
    }
    if set(answers) != expected:
        raise AdapterError("answer-fields-do-not-match-greenfield-recreate")
    repository_key, repository = _registered_repository(
        answers, repository_roots,
    )
    for key, minimum, maximum in (
        ("port", 1, 65535),
        ("start_feature_index", 0, None),
        ("parallel_width", 1, None),
    ):
        value = answers[key]
        if (
            not isinstance(value, int) or isinstance(value, bool)
            or value < minimum or (maximum is not None and value > maximum)
        ):
            raise AdapterError(f"invalid-{key.replace('_', '-')}")
    feature_repository = _required_text(answers, "feature_repository")
    if not feature_repository.startswith("github:"):
        raise AdapterError("invalid-feature-repository")
    argv = [
        "bash", str(Path(repository, "scripts/greenfield_recreate_resume.sh")),
        "--repo", feature_repository,
        "--program-drive-id", _required_text(answers, "program_drive_id"),
        "--decomposition-task-id",
        _required_text(answers, "decomposition_task_id"),
        "--container", _required_text(answers, "container"),
        "--tag", _required_text(answers, "image_tag"),
        "--port", str(answers["port"]),
        "--keyvault", _required_text(answers, "keyvault"),
        "--start-feature-index", str(answers["start_feature_index"]),
        "--parallel-width", str(answers["parallel_width"]),
    ]
    if answers["rebuild_image"] is True:
        argv.append("--rebuild")
    elif answers["rebuild_image"] is not False:
        raise AdapterError("invalid-rebuild-image")
    if answers["expected_spec_hash"] is not None:
        digest = _required_text(answers, "expected_spec_hash")
        if len(digest) != 64 or any(
            character not in "0123456789abcdef" for character in digest
        ):
            raise AdapterError("invalid-expected-spec-hash")
        argv.extend(["--expected-spec-hash", digest])
    return _script_payload(
        sequence_id="greenfield-recreate-resume",
        profile="rebuild" if answers["rebuild_image"] else "reuse-image",
        argv=argv,
        repository_key=repository_key,
        repository_root=repository,
        effectful=True,
        operation="recreate-resume",
    )


def _prepare_workflow_phase_resume(
    answers: Mapping[str, Any],
    _artifact_paths: Mapping[str, str],
    repository_roots: Mapping[str, str],
) -> dict[str, Any]:
    expected = {
        "repository_key", "client", "source_run_id",
        "first_unfinished_phase", "reopen_completed_phase",
    }
    if set(answers) != expected:
        raise AdapterError("answer-fields-do-not-match-workflow-phase-resume")
    repository_key, repository = _registered_repository(
        answers, repository_roots,
    )
    python = (
        "/Users/kamenkamenov/.cache/codex-runtimes/"
        "codex-primary-runtime/dependencies/python/bin/python3"
    )
    argv = [
        python,
        str(Path(repository, "scripts/run_client_regeneration.py")),
        "--client", _required_text(answers, "client"),
        "--resume-run", _required_text(answers, "source_run_id"),
        "--from-phase", _required_text(answers, "first_unfinished_phase"),
    ]
    if answers["reopen_completed_phase"] is True:
        # Re-running a phase whose own logic changed is the only way to confirm that
        # change without regenerating the whole run. Added 2026-07-28 after a corrected
        # publication check could not be exercised any other way.
        argv.append("--rerun-completed")
    environment = {
        "PYTHONPATH": "src",
        "UP_HARNESS_AGENT_COMMAND": (
            f"{python} scripts/codex_role_command.py"
        ),
        "UP_HARNESS_AGENT_MAX_ATTEMPTS": "3",
        "UP_HARNESS_AGENT_TIMEOUT_SECONDS": "600",
        "UP_HARNESS_CODEX_TIMEOUT_SECONDS": "600",
    }
    return _script_payload(
        sequence_id="workflow-resume-from-phase-live-confirmation",
        profile="resume",
        argv=argv,
        repository_key=repository_key,
        repository_root=repository,
        effectful=True,
        operation="resume",
        environment=environment,
    )


def _prepare_workflow_client_regeneration(
    answers: Mapping[str, Any],
    _artifact_paths: Mapping[str, str],
    repository_roots: Mapping[str, str],
) -> dict[str, Any]:
    expected = {
        "repository_key", "client", "parent_run_id",
        "answers_source_run_id", "controlled_topic_policies_path",
    }
    if set(answers) != expected:
        raise AdapterError(
            "answer-fields-do-not-match-workflow-client-regeneration"
        )
    repository_key, repository = _registered_repository(
        answers, repository_roots,
    )
    python = (
        "/Users/kamenkamenov/.cache/codex-runtimes/"
        "codex-primary-runtime/dependencies/python/bin/python3"
    )
    argv = [
        python,
        str(Path(repository, "scripts/run_client_regeneration.py")),
        "--client", _required_text(answers, "client"),
        "--parent-run", _required_text(answers, "parent_run_id"),
        "--answers-from-run", _required_text(answers, "answers_source_run_id"),
        "--controlled-topic-policies-file",
        _required_text(answers, "controlled_topic_policies_path"),
    ]
    environment = {
        "PYTHONPATH": "src",
        "UP_HARNESS_AGENT_COMMAND": (
            f"{python} scripts/codex_role_command.py"
        ),
        "UP_HARNESS_AGENT_MAX_ATTEMPTS": "3",
        "UP_HARNESS_AGENT_TIMEOUT_SECONDS": "600",
        "UP_HARNESS_CODEX_TIMEOUT_SECONDS": "600",
    }
    return _script_payload(
        sequence_id="workflow-client-regeneration-live-confirmation",
        profile="regeneration",
        argv=argv,
        repository_key=repository_key,
        repository_root=repository,
        effectful=True,
        operation="regeneration",
        environment=environment,
    )


def _prepare_callcenter_provision(
    answers: Mapping[str, Any],
    _artifact_paths: Mapping[str, str],
    repository_roots: Mapping[str, str],
) -> dict[str, Any]:
    action = _required_text(answers, "action")
    needs_recording = action in {
        "smoke-ingest", "smoke-redact", "smoke-pipeline", "smoke-eval",
    }
    expected = {"repository_key", "action"}
    if needs_recording:
        expected.add("recording")
    if set(answers) != expected:
        raise AdapterError("answer-fields-do-not-match-callcenter-action")
    repository_key, repository = _registered_repository(
        answers, repository_roots,
    )
    home_python = str(Path.home() / ".callcenter-harness/venv/bin/python")
    environment: dict[str, str] = {}
    if action in {"provision-small", "provision-large"}:
        argv = [
            str(Path(repository, "scripts/setup_airgapped_stt.sh")),
            "provision",
        ]
        environment["STT_MODEL"] = (
            "small" if action == "provision-small" else "large-v3"
        )
    elif action in {"provision-redaction", "verify-redaction"}:
        argv = [
            str(Path(repository, "scripts/setup_airgapped_redaction.sh")),
            "provision" if action == "provision-redaction" else "verify",
        ]
    elif action == "smoke-core":
        argv = [
            "python3", str(Path(repository, "scripts/cc_smoke.py")),
        ]
        environment["PYTHONPATH"] = "src"
    else:
        suffix = {
            "smoke-ingest": "cc_ingest_smoke.py",
            "smoke-redact": "cc_redact_smoke.py",
            "smoke-pipeline": "cc_pipeline_smoke.py",
            "smoke-eval": "cc_eval_smoke.py",
        }[action]
        python = "python3" if action == "smoke-ingest" else home_python
        argv = [
            python, str(Path(repository, "scripts", suffix)),
            _required_text(answers, "recording"),
        ]
        environment["PYTHONPATH"] = "src"
        if action != "smoke-ingest":
            environment.update({
                "HF_HUB_OFFLINE": "1",
                "HTTPS_PROXY": "http://127.0.0.1:9",
                "HTTP_PROXY": "http://127.0.0.1:9",
            })
    return _script_payload(
        sequence_id="callcenter-harness-provision-verify",
        profile=action,
        argv=argv,
        repository_key=repository_key,
        repository_root=repository,
        effectful=True,
        operation=action,
        environment=environment,
    )


REMOTE_ACTION_FIELDS = {
    "user-detail": {"selected_user_id"},
    "new-user-set-first-name": {"value"},
    "new-user-set-last-name": {"value"},
    "new-user-set-email": {"value"},
    "new-user-set-role": {"role"},
    "repo-access-list": {"selected_user_id"},
    "repo-access-select": {"repo_alias"},
    "repo-access-action": {"repo_access_operation"},
    "repo-access-save": {"confirmation_file"},
    "field-update-start": {"selected_user_id", "field", "value"},
    "field-update-apply": {"confirmation_file"},
    "role-update-start": {"selected_user_id", "role"},
    "role-update-apply": {"confirmation_file"},
    "status-toggle-confirm": {"selected_user_id", "status_action"},
    "status-toggle-apply": {"confirmation_file"},
    "create-user-apply": {"confirmation_file", "token_output_file"},
    "stale-overwrite": {"confirmation_file"},
}


def _prepare_remote_onboarding(
    answers: Mapping[str, Any],
    _artifact_paths: Mapping[str, str],
    repository_roots: Mapping[str, str],
) -> dict[str, Any]:
    action = _required_text(answers, "action")
    if action not in REMOTE_ONBOARDING_ACTIONS:
        raise AdapterError("unsupported-remote-onboarding-action")
    action_fields = REMOTE_ACTION_FIELDS.get(action, set())
    expected = {
        "repository_key", "server_url", "actor_email", "action",
        "state_file", *action_fields,
    }
    if set(answers) != expected:
        raise AdapterError("answer-fields-do-not-match-remote-onboarding")
    repository_key, repository = _registered_repository(
        answers, repository_roots,
    )
    server_url = _required_text(answers, "server_url")
    if not server_url.startswith("wss://"):
        raise AdapterError("server-url-must-use-wss")
    argv = [
        "python3",
        str(Path(
            repository,
            "dist/remote-mcp-user-admin/remote_mcp_user_admin_tui.py",
        )),
        "--server-url", server_url,
        "--actor-email", _required_text(answers, "actor_email"),
        "--auth-auto-refresh",
        "--tool-timeout-seconds", "60",
        "--agent-action", action,
        "--state-file", _required_text(answers, "state_file"),
    ]
    flag_names = {
        "selected_user_id": "--selected-user-id",
        "value": "--value",
        "field": "--field",
        "role": "--role",
        "repo_alias": "--repo-alias",
        "repo_access_operation": "--repo-access-operation",
        "status_action": "--status-action",
        "token_output_file": "--token-output-file",
    }
    for key, flag in flag_names.items():
        if key in answers:
            argv.extend([flag, _required_text(answers, key)])
    if "confirmation_file" in answers:
        confirmation = _json_object_file(
            _required_text(answers, "confirmation_file"),
            "confirmation-file-invalid",
        )
        argv.extend([
            "--confirmation-json",
            json.dumps(
                confirmation, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False,
            ),
        ])
    return _script_payload(
        sequence_id="remote-mcp-user-onboarding",
        profile=action,
        argv=argv,
        repository_key=repository_key,
        repository_root=repository,
        effectful=action not in {
            "user-list", "user-list-refresh", "user-detail",
        },
        operation=action,
    )


def _bootstrap_steps(
    answers: Mapping[str, Any],
    repository_roots: Mapping[str, str],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    raw = answers.get("steps")
    if not isinstance(raw, list) or not raw:
        raise AdapterError("answer-required:steps")
    steps: list[dict[str, str]] = []
    dependencies: list[dict[str, str]] = []
    labels: set[str] = set()
    seen_dependencies: set[tuple[str, str]] = set()
    for item in raw:
        if not isinstance(item, Mapping) or set(item) != {
            "step", "repository_key", "script_path", "result", "note",
        }:
            raise AdapterError("invalid-bootstrap-step")
        label = _required_text(item, "step")
        if label in labels:
            raise AdapterError("duplicate-bootstrap-step")
        labels.add(label)
        repository_key = _required_text(item, "repository_key")
        if repository_key not in repository_roots:
            raise AdapterError(
                f"repository-key-unregistered:{repository_key}"
            )
        script_path = _required_text(item, "script_path")
        relative = PurePosixPath(script_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise AdapterError("invalid-bootstrap-script-path")
        if script_path.endswith(".py"):
            command = f"python3 {script_path}"
        elif script_path.endswith(".sh"):
            command = f"bash {script_path}"
        else:
            raise AdapterError("unsupported-bootstrap-script-type")
        steps.append({
            "step": label,
            "command": command,
            "result": _required_text(item, "result"),
            "note": _required_text(item, "note"),
        })
        identity = (repository_key, script_path)
        if identity not in seen_dependencies:
            dependencies.append({
                "kind": "file",
                "repository_key": repository_key,
                "path_or_sequence_id": script_path,
            })
            seen_dependencies.add(identity)
    return steps, dependencies


def _prepare_discovery_bootstrap(
    answers: Mapping[str, Any],
    artifact_paths: Mapping[str, str],
    repository_roots: Mapping[str, str],
) -> dict[str, Any]:
    expected = {
        "source_repository_key", "task_id", "operation_kind", "date",
        "sequence_name", "outcome", "why_repeatable", "steps", "inputs",
        "failure_handling", "verified_path", "repo_roots_file",
    }
    if set(answers) != expected:
        raise AdapterError("answer-fields-do-not-match-discovery-bootstrap")
    repository_key, repository = _registered_repository(
        answers, repository_roots, answer_key="source_repository_key",
    )
    date_text = _required_text(answers, "date")
    try:
        if datetime.strptime(date_text, "%Y-%m-%d").strftime(
            "%Y-%m-%d"
        ) != date_text:
            raise ValueError
    except ValueError as exc:
        raise AdapterError("invalid-bootstrap-date") from exc
    operation_kind = _required_text(answers, "operation_kind")
    if operation_kind not in OPERATION_KINDS:
        raise AdapterError("invalid-bootstrap-operation-kind")
    steps, dependencies = _bootstrap_steps(answers, repository_roots)
    repo_roots_file = answers["repo_roots_file"]
    if (
        any(
            item["repository_key"] != repository_key
            for item in dependencies
        )
        and repo_roots_file is None
    ):
        raise AdapterError("repo-roots-file-required-for-cross-repository")
    spec = {
        "schema_version": 1,
        "task_id": _required_text(answers, "task_id"),
        "operation_kind": operation_kind,
        "date": date_text,
        "sequence_name": _required_text(answers, "sequence_name"),
        "outcome": _required_text(answers, "outcome"),
        "why_repeatable": _required_text(answers, "why_repeatable"),
        "steps": steps,
        "inputs": _paths_like_text(answers, "inputs"),
        "failure_handling": _required_text(answers, "failure_handling"),
        "verified_path": _required_text(answers, "verified_path"),
        "dependencies": dependencies,
    }
    artifact = _json_artifact(artifact_paths, "spec", spec)
    argv = [
        "python3", str(Path(repository, "scripts/discovery_bootstrap.py")),
        "start", "--spec", artifact["path"], "--root", repository,
    ]
    if repo_roots_file is not None:
        argv.extend([
            "--repo-roots-file",
            _required_text(answers, "repo_roots_file"),
        ])
    payload = _script_payload(
        sequence_id="discovery-bootstrap",
        profile="start",
        argv=argv,
        repository_key=repository_key,
        repository_root=repository,
        effectful=True,
        operation="start",
    )
    payload["artifacts"] = {"spec": artifact}
    return payload


def _offline_adapter(sequence_id: str) -> Adapter:
    return lambda answers, _artifact_paths, repository_roots: (
        _prepare_offline_sequence(sequence_id, answers, repository_roots)
    )


Adapter = Callable[
    [Mapping[str, Any], Mapping[str, str], Mapping[str, str]],
    dict[str, Any],
]
ADAPTER_REGISTRY: dict[str, Adapter | None] = {
    sequence_id: None for sequence_id in CANONICAL_SEQUENCE_IDS
}
ADAPTER_REGISTRY["commit-push-main"] = _prepare_commit_push
for _deploy_sequence_id in DEPLOY_SEQUENCE_CONFIG:
    ADAPTER_REGISTRY[_deploy_sequence_id] = _deploy_adapter(_deploy_sequence_id)
ADAPTER_REGISTRY["local-workflow-orch-image"] = _prepare_local_image
ADAPTER_REGISTRY["greenfield-full-drive"] = _prepare_greenfield
ADAPTER_REGISTRY["claude-auth-token-refresh"] = _prepare_claude_auth
for _offline_sequence_id in OFFLINE_SEQUENCE_CONFIG:
    ADAPTER_REGISTRY[_offline_sequence_id] = _offline_adapter(
        _offline_sequence_id,
    )
ADAPTER_REGISTRY["scoped-context-edit"] = _prepare_scoped_context
ADAPTER_REGISTRY[
    "discovery-candidate-reconciliation"
] = _prepare_discovery_reconciliation
ADAPTER_REGISTRY[
    "blocker-backlog-reconciliation"
] = _prepare_blocker_backlog_reconciliation
ADAPTER_REGISTRY[
    "discovery-promotion-lifecycle"
] = _prepare_discovery_promotion
ADAPTER_REGISTRY[
    "convergence-checkpoint-run"
] = _prepare_convergence_checkpoint
ADAPTER_REGISTRY[
    "convergence-state-review-cycle"
] = _prepare_convergence_review
ADAPTER_REGISTRY["taggable-source-reload"] = _prepare_taggable_reload
ADAPTER_REGISTRY["github-app-repos-refresh"] = _prepare_github_refresh
ADAPTER_REGISTRY["mawf-playbook-full-test"] = _mawf_adapter(
    "mawf-playbook-full-test", "full",
)
ADAPTER_REGISTRY["mawf-playbook-speed-test"] = _mawf_adapter(
    "mawf-playbook-speed-test", "speed",
)
ADAPTER_REGISTRY[
    "mawf-playbook-blocker-reentry"
] = _prepare_mawf_blocker
ADAPTER_REGISTRY[
    "greenfield-recreate-resume"
] = _prepare_greenfield_recreate
ADAPTER_REGISTRY[
    "workflow-resume-from-phase-live-confirmation"
] = _prepare_workflow_phase_resume
ADAPTER_REGISTRY[
    "workflow-client-regeneration-live-confirmation"
] = _prepare_workflow_client_regeneration
ADAPTER_REGISTRY[
    "callcenter-harness-provision-verify"
] = _prepare_callcenter_provision
ADAPTER_REGISTRY[
    "remote-mcp-user-onboarding"
] = _prepare_remote_onboarding
ADAPTER_REGISTRY["discovery-bootstrap"] = _prepare_discovery_bootstrap
INTAKE_SPECS = {
    "commit-push-main": COMMIT_PUSH_SPEC,
    **DEPLOY_SPECS,
    "local-workflow-orch-image": LOCAL_IMAGE_SPEC,
    "greenfield-full-drive": GREENFIELD_SPEC,
    "claude-auth-token-refresh": CLAUDE_AUTH_SPEC,
    **OFFLINE_SPECS,
    "scoped-context-edit": SCOPED_CONTEXT_SPEC,
    "discovery-candidate-reconciliation": DISCOVERY_RECONCILIATION_SPEC,
    "blocker-backlog-reconciliation": BLOCKER_BACKLOG_RECONCILIATION_SPEC,
    "discovery-promotion-lifecycle": DISCOVERY_PROMOTION_SPEC,
    "convergence-checkpoint-run": CONVERGENCE_CHECKPOINT_SPEC,
    "convergence-state-review-cycle": CONVERGENCE_REVIEW_SPEC,
    "taggable-source-reload": TAGGABLE_RELOAD_SPEC,
    "github-app-repos-refresh": GITHUB_REFRESH_SPEC,
    **MAWF_SPECS,
    "mawf-playbook-blocker-reentry": MAWF_BLOCKER_SPEC,
    "greenfield-recreate-resume": GREENFIELD_RECREATE_SPEC,
    "workflow-resume-from-phase-live-confirmation": (
        WORKFLOW_PHASE_RESUME_SPEC
    ),
    "workflow-client-regeneration-live-confirmation": (
        WORKFLOW_CLIENT_REGENERATION_SPEC
    ),
    "callcenter-harness-provision-verify": CALLCENTER_PROVISION_SPEC,
    "remote-mcp-user-onboarding": REMOTE_ONBOARDING_SPEC,
    "discovery-bootstrap": DISCOVERY_BOOTSTRAP_SPEC,
}

ARTIFACT_IDS: dict[str, tuple[str, ...]] = {
    "commit-push-main": ("approved_paths", "overlay_paths"),
    "discovery-promotion-lifecycle": ("changed_artifacts",),
    "convergence-state-review-cycle": ("request",),
    "discovery-bootstrap": ("spec",),
}


def artifact_ids(sequence_id: str) -> tuple[str, ...]:
    if sequence_id not in ADAPTER_REGISTRY:
        raise AdapterUnavailable(f"sequence-not-registered:{sequence_id}")
    return ARTIFACT_IDS.get(sequence_id, ())


def intake_spec(
    sequence_id: str,
    *,
    repository_roots: Mapping[str, str],
) -> Mapping[str, Any]:
    if sequence_id not in ADAPTER_REGISTRY:
        raise AdapterUnavailable(f"sequence-not-registered:{sequence_id}")
    try:
        spec = deepcopy(INTAKE_SPECS[sequence_id])
    except KeyError as exc:
        raise AdapterUnavailable(f"adapter-not-implemented:{sequence_id}") from exc
    repository_fields = [
        field for field in spec["fields"]
        if (
            field.get("id") == "repository_key"
            or field.get("choices_from_repository_roots") is True
        )
    ]
    for repository_field in repository_fields:
        choices = sorted(repository_roots)
        if not choices:
            raise AdapterError("repository-registry-empty")
        repository_field["choices"] = choices
        repository_field["example"] = choices[0]
    return spec


def prepare(
    sequence_id: str,
    answers: Mapping[str, Any],
    *,
    artifact_paths: Mapping[str, str],
    repository_roots: Mapping[str, str],
) -> dict[str, Any]:
    try:
        adapter = ADAPTER_REGISTRY[sequence_id]
    except KeyError as exc:
        raise AdapterUnavailable(f"sequence-not-registered:{sequence_id}") from exc
    if adapter is None:
        raise AdapterUnavailable(f"adapter-not-implemented:{sequence_id}")
    return adapter(answers, artifact_paths, repository_roots)


def collect_and_prepare(
    sequence_id: str,
    *,
    artifact_paths: Mapping[str, str],
    repository_roots: Mapping[str, str],
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    answers = script_intake.collect(
        intake_spec(sequence_id, repository_roots=repository_roots),
        input_fn=input_fn,
        output_fn=output_fn,
    )
    return prepare(
        sequence_id,
        answers,
        artifact_paths=artifact_paths,
        repository_roots=repository_roots,
    )


INTAKE_CONTRACTS_PATH = "operations/sequences/sequence-intake-contracts.json"
INTAKE_CONTRACT_VERSION = 1
LOCAL_REPOSITORY_KEY = "memory-knowledge"


def _registry_automation_rows(registry_path: Any) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in Path(registry_path).read_text().splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        sequence_id = cells[0].strip("`")
        rows[sequence_id] = cells[3].strip("`").strip()
    return rows


def build_intake_contracts(root: Any) -> dict[str, Any]:
    """Deterministic machine binding between every runnable sequence adapter and its caller.

    A changed local entrypoint source changes its recorded hash, so a stale binding fails
    closed at check time until adapter compatibility is re-verified and this file rebuilt.
    Cross-repository entrypoints are bound by their registry source-receipt identity.
    """
    root = Path(root)
    registry = _registry_automation_rows(root / "operations/sequences/SEQUENCES.md")
    adapter_source_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    entries: list[dict[str, Any]] = []
    non_runnable: list[dict[str, str]] = []
    problems: list[str] = []
    for sequence_id in sorted(set(ADAPTER_REGISTRY) | set(registry)):
        if sequence_id not in ADAPTER_REGISTRY:
            problems.append(f"registry-row-without-canonical-sequence:{sequence_id}")
            continue
        adapter = ADAPTER_REGISTRY[sequence_id]
        if adapter is None:
            non_runnable.append({
                "sequence_id": sequence_id,
                "reason": "no intake adapter is registered; the sequence is not dispatchable "
                          "through zero-input intake and must not be improvised",
            })
            continue
        spec = INTAKE_SPECS.get(sequence_id)
        if spec is None:
            problems.append(f"adapter-without-intake-spec:{sequence_id}")
            continue
        automation = registry.get(sequence_id, "")
        entry: dict[str, Any] = {
            "sequence_id": sequence_id,
            "entrypoint": automation or None,
            "contract_version": INTAKE_CONTRACT_VERSION,
            "adapter_id": getattr(adapter, "__name__", adapter.__class__.__name__),
            "adapter_source_sha256": adapter_source_sha256,
            "semantic_fields": [field["id"] for field in spec["fields"]],
            "required_inputs": sorted(
                field["id"] for field in spec["fields"] if field.get("required")
            ),
            "optional_inputs": sorted(
                field["id"] for field in spec["fields"] if not field.get("required")
            ),
            "argv_shape": {
                "derivation": "scripts/sequence_intake_adapters.py:prepare",
                "caller_constructs_argv": False,
                "artifact_inputs": list(ARTIFACT_IDS.get(sequence_id, ())),
            },
            "verification_case_ids": [
                "tests/test_sequence_intake_adapters.py",
                "tests/test_sequence_intake_launch.py",
            ],
        }
        if automation.startswith(f"{LOCAL_REPOSITORY_KEY}:"):
            source_path = root / automation.split(":", 1)[1].split()[0]
            if source_path.is_file():
                entry["entrypoint_source_sha256"] = hashlib.sha256(
                    source_path.read_bytes()
                ).hexdigest()
            else:
                problems.append(f"entrypoint-source-missing:{sequence_id}:{source_path}")
        elif automation:
            entry["entrypoint_source_receipt"] = automation
        entries.append(entry)
    if problems:
        raise AdapterError("intake-contract-build-failed:" + ";".join(sorted(problems)))
    return {
        "schema_version": 1,
        "contract_version": INTAKE_CONTRACT_VERSION,
        "adapter_source_sha256": adapter_source_sha256,
        "entries": entries,
        "non_runnable": non_runnable,
    }


def check_intake_contracts(root: Any) -> list[str]:
    """Return drift errors between the stored contract file and the rebuilt binding."""
    root = Path(root)
    stored_path = root / INTAKE_CONTRACTS_PATH
    if not stored_path.is_file():
        return [f"intake-contracts-missing:{stored_path}"]
    try:
        stored = json.loads(stored_path.read_text())
    except ValueError:
        return [f"intake-contracts-unreadable:{stored_path}"]
    rebuilt = build_intake_contracts(root)
    if stored == rebuilt:
        return []
    errors: list[str] = []
    stored_entries = {row.get("sequence_id"): row for row in stored.get("entries", [])}
    rebuilt_entries = {row["sequence_id"]: row for row in rebuilt["entries"]}
    for sequence_id in sorted(set(stored_entries) | set(rebuilt_entries)):
        if stored_entries.get(sequence_id) != rebuilt_entries.get(sequence_id):
            errors.append(f"intake-contract-drift:{sequence_id}")
    if stored.get("non_runnable") != rebuilt["non_runnable"]:
        errors.append("intake-contract-drift:non-runnable-set")
    return errors or ["intake-contract-drift:document-level"]
