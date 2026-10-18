#!/usr/bin/env python3
"""Build registered sequence invocations from semantic intake answers."""

from __future__ import annotations

import json
import hashlib
import os
import re
import shlex
import subprocess
from collections.abc import Callable, Mapping
from copy import deepcopy
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

try:
    from scripts import goal_tracker, local_multimodal_model_benchmark, script_intake
except ModuleNotFoundError:  # direct script execution
    import goal_tracker  # type: ignore
    import local_multimodal_model_benchmark  # type: ignore
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
    # The outer tool invocation must still run the shared controller in the background;
    # this adapter prepares only fixed-template observation probes and never accepts raw
    # shell from the caller.
    "agent-heartbeat",
    # Goal declaration retains its standalone zero-argument interview and also has a
    # registered adapter below, so the shared controller can collect the same contract
    # once and dispatch an approved answers artifact without a second interview.
    "goal-declaration",
    "local-multimodal-model-benchmark",
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
            "response_format": "One selection number.",
            "example": "1",
            "constraints": "Choose the numbered operation matching the approved Git effect.",
            "type": "choice",
            "choices": list(COMMIT_PUSH_OPERATIONS),
            "numbered_selection": True,
            "required": True,
        },
        {
            "id": "repository_key",
            "prompt": "Repository",
            "response_format": "One selection number.",
            "example": "1",
            "constraints": "Choose exactly one numbered repository.",
            "type": "choice",
            "choices": ["memory-knowledge"],
            "numbered_selection": True,
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
        "requires_dotnet": True,
    },
    "taggable-admin-spa-deploy": {
        "script": "scripts/deploy-admin-spa.sh",
        "repository_example": "taggable-admin-spa",
        "api_base": "https://taggable-api-dev.azurewebsites.net/api",
    },
    "taggable-media-worker-deploy": {
        "script": "scripts/deploy-media-worker.sh",
        "repository_example": "taggable-api",
        "requires_dotnet": True,
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


GOAL_DECLARATION_SPEC = {
    "schema_version": script_intake.SCHEMA_VERSION,
    "fields": [
        _semantic_field(
            "repository_key", "Repository whose goal is being declared",
            "One selection number.", "1",
            "Choose exactly one registered repository; do not type a path.",
            "choice", choices=[], choices_from_repository_roots=True,
            numbered_selection=True, required=True,
        ),
        *deepcopy(goal_tracker.GOAL_SPEC["fields"]),
    ],
}


AGENT_HEARTBEAT_SPEC = {
    "schema_version": script_intake.SCHEMA_VERSION,
    "fields": [
        _semantic_field(
            "source_repository_key", "Heartbeat controller repository",
            "One selection number.", "1",
            "Choose the repository containing the checked-in heartbeat script.",
            "choice", choices=["memory-knowledge"], numbered_selection=True,
            required=True,
        ),
        _semantic_field(
            "seconds", "Wait before the heartbeat completes",
            "One whole number from 1 through 3600.", "270",
            "Use a duration inside the reporting ceiling; 270 leaves turn time inside five minutes.",
            "integer", default=270, minimum=1, maximum=3600,
        ),
        _semantic_field(
            "label", "What this heartbeat is watching",
            "One short plain-language label.", "feature 11 live drive",
            "Name the run or operation; do not provide invocation syntax.",
            "string", required=True,
        ),
        _semantic_field(
            "probes", "State-producing probe",
            "Answer one probe's numbered type and its bounded details at a time.",
            "a file tail followed by container logs",
            "No shell commands are accepted; code derives every command from the selected type.",
            "object_list", required=True,
            item_fields=[
                _semantic_field(
                    "type", "Probe type", "One selection number.", "1",
                    "Choose the observation surface; raw shell is unavailable.",
                    "choice", choices=[
                        "file-metadata", "file-tail", "process-state", "container-logs",
                    ], numbered_selection=True, required=True,
                ),
                _semantic_field(
                    "path", "Observed file path", "One absolute or repository-relative path.",
                    "/private/tmp/run/latest-result.json",
                    "The path must remain under /private/tmp or a registered repository.",
                    "path", required=True,
                    when={"field": "type", "in": ["file-metadata", "file-tail"]},
                ),
                _semantic_field(
                    "lines", "Maximum returned lines", "One whole number from 1 through 500.",
                    "80", "Bound the reported content.", "integer",
                    default=80, minimum=1, maximum=500,
                    when={"field": "type", "in": ["file-tail", "container-logs"]},
                ),
                _semantic_field(
                    "pattern", "Process identity text", "One literal process-name fragment.",
                    "greenfield_drive_dag.py",
                    "Code searches literally; shell syntax is not interpreted.",
                    "string", required=True,
                    when={"field": "type", "equals": "process-state"},
                ),
                _semantic_field(
                    "container", "Container name", "One Docker container name.",
                    "workflow-orch-local-sequence-check",
                    "Letters, digits, period, underscore, and hyphen only.",
                    "string", required=True,
                    when={"field": "type", "equals": "container-logs"},
                ),
                _semantic_field(
                    "lookback_seconds", "Container-log lookback",
                    "One whole number from 1 through 86400.", "300",
                    "Bound how far back the probe reads.", "integer",
                    default=300, minimum=1, maximum=86400,
                    when={"field": "type", "equals": "container-logs"},
                ),
            ],
        ),
    ],
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
    "package", "publish", "read-only", "remote-operator", "single-build", "single-test",
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

# Step 2 clean-copy route: interview and debrief only, through the human gate.
STEP2_ALLOWED_PHASES = (
    "prepare-controlled-topic-policy-inputs", "ingest-leadership-interview",
    "gate-interview-answers", "compose-debrief-write-up", "debrief-gate",
)

STEP3_ALLOWED_PHASES = (
    "compose-final-brief", "convene-final-brief-board",
    "final-brief-board-gate", "final-brief-gate",
)

STEP4_ALLOWED_PHASES = (
    "compose-research-insight-pack", "research-gate",
)
STEP4_NATIVE_PARTS = frozenset((
    "buckets", "personas", "audits", "reputation_reads", "scans", "pestle",
    "stakeholder_map", "patterns", "benchmarks", "pyramid", "ownable_space",
    "executive_summary", "query_logic", "definitions",
))

STEP5_ALLOWED_PHASES = (
    "compose-insight-cards", "convene-insight-mini-board",
    "insight-mini-board-gate", "insight-gate",
)
STEP5_RECORDED_SOURCE = "accepted-step5-source"
STEP6_RECORDED_SOURCE = "held-step6-source"
STEP7_RECORDED_SOURCE = "held-step6-for-step7"
STEP8_RECORDED_SOURCE = "held-step7-for-step8"
STEP9_RECORDED_SOURCE = "held-step8-for-step9"
STEP10_RECORDED_SOURCE = "held-step9-for-step10"
STEP11_RECORDED_SOURCE = "accepted-step10-for-step11"

# Step 12 copy route (D53): the phases after Step 11's annual-review-gate in
# workflows/cd-s-002-corporate-communications-strategy.yaml, through the roadmap gate.
STEP12_ALLOWED_PHASES = (
    "assemble-step-dossier", "step-dossier-gate", "map-the-method", "method-map-gate",
    "read-governance", "governance-gate", "check-language-standard",
    "language-standard-gate", "shared-concepts-gate", "convene-review-board",
    "review-board-gate", "certify-the-work", "certification-gate",
    "compose-tactical-roadmap", "roadmap-gate",
)

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
            ("Use the non-completed source run, accepted-step5-source for Step 5, "
             "held-step6-source for Step 6, or held-step6-for-step7 for the current "
             "Step 7 source and recorded closeout, or held-step7-for-step8 for the "
             "current Step 8 source and recorded closeout, or held-step8-for-step9 "
             "for the current Step 9 source and recorded closeout, or held-step9-for-step10 "
             "for the current Step 10 source and review-only closeout, or "
             "accepted-step10-for-step11 for the current accepted Step 10 pair and Step 11 closeout."),
            "string", required=True,
        ),
        _semantic_field(
            "first_unfinished_phase", "Phase to resume or reopen",
            "One exact phase identity.", "compose-llm-strategy-brief",
            "Use the first unfinished phase, or the completed phase named for an approved reopen.", "string",
            required=True,
        ),
        _semantic_field(
            "reopen_completed_phase", "Re-open a phase that already completed",
            "Answer yes or no.", "no",
            (
                "Answer yes only when that phase's logic changed or recorded Step 4 "
                "interview evidence must enter its completed compose; "
                "it discards that phase and every phase after it."
            ),
            "boolean", required=True,
        ),
        _semantic_field(
            "client_answers_path",
            "Client interview answers arriving after the run settled",
            "One existing file path, or leave blank.",
            "Tasks/bteam-corporate-demo/inputs/leadership-interview-answers.json",
            (
                "Supply only when resuming prepare-controlled-topic-policy-inputs or "
                "ingest-leadership-interview with answers the settled run never had; the "
                "driver refuses it at any other phase."
            ),
            "path", required=False,
        ),
        _semantic_field(
            "debrief_feedback_path",
            "Reviewer's typed debrief decisions",
            "One existing file path, or leave blank.",
            "Tasks/vivacom-corporate-demo/state/up-run-1.debrief-feedback-decisions.json",
            (
                "Supply only when resuming a gate phase with a reviewer's feedback round; "
                "the driver refuses it elsewhere."
            ),
            "path", required=False,
        ),
        _semantic_field(
            "final_brief_feedback_path",
            "Typed decisions on the Step 3 pair",
            "One existing file path, or leave blank.",
            "Tasks/vivacom-corporate-demo/state/up-run-1.final-brief-feedback-decisions.json",
            (
                "Supply only when resuming a gate phase with a feedback round on the "
                "Client Intake Brief and Measurement Brief pair; the driver refuses it "
                "elsewhere."
            ),
            "path", required=False,
        ),
        _semantic_field(
            "gate_approvals_path",
            "Typed gate approvals",
            "One existing file path, or leave blank.",
            "Tasks/vivacom-corporate-demo/state/gate-approvals.json",
            (
                "Supply only when resuming a gate phase with typed approvals; the driver "
                "refuses it elsewhere."
            ),
            "path", required=False,
        ),
        _semantic_field(
            "corrected_topic_policies_path",
            "Corrected controlled-topic policy set",
            "One existing file path, or leave blank.",
            "Tasks/vivacom-corporate-demo/controlled-topic-policies.json",
            (
                "Supply only when resuming prepare-controlled-topic-policy-inputs with a "
                "corrected owner policy set; the driver refuses it at any other phase."
            ),
            "path", required=False,
        ),
        _semantic_field(
            "step11_writer_input_path",
            "Source-bound Step 11 writer input file",
            "One existing file path, or leave blank.",
            "Tasks/vivacom-corporate-demo/state/step11-writer-input.json",
            (
                "Supply together with the shared writer call-budget file and positive call "
                "limit, only when resuming compose-annual-review. These three settings "
                "cannot be combined with another optional resume input file."
            ),
            "path", required=False,
        ),
        _semantic_field(
            "step11_writer_call_budget_path",
            "Shared Step 11 writer call-budget file",
            "One existing file path, or leave blank.",
            "Tasks/vivacom-corporate-demo/state/step11-writer-call-budget.json",
            (
                "Supply together with the source-bound writer input file and positive call "
                "limit, only when resuming compose-annual-review. These three settings "
                "cannot be combined with another optional resume input file."
            ),
            "path", required=False,
        ),
        _semantic_field(
            "step11_writer_call_limit",
            "Step 11 writer call limit",
            "One positive whole number, or leave blank.",
            "12",
            (
                "Supply together with the source-bound writer input file and shared call- "
                "budget file, only when resuming compose-annual-review. These three "
                "settings cannot be combined with another optional resume input file."
            ),
            "integer", required=False, minimum=1,
        ),
        _semantic_field(
            "step11_writer_call_extension_from",
            "Previous Step 11 writer call limit",
            "One positive whole number, or leave blank.",
            "80",
            (
                "Supply only when explicitly extending an existing shared Step 11 writer "
                "ledger. The new call limit above must be greater; the existing reservations "
                "remain spent. Leave blank for an ordinary resume."
            ),
            "integer", required=False, minimum=1,
        ),
        _semantic_field(
            "step9_rehearsal_task_dir",
            "Isolated client rehearsal copy folder",
            "One copy folder path, or leave blank.",
            "Tasks/bteam-rehearsal-demo",
            ("Supply alone for an ordinary automatic Step 9 or Step 11 writer resume, "
             "or with the Step 9 writer call limit or saved-cache continuation choice. "
             "The copy must be "
             "Tasks/<client>-rehearsal-demo; the official client folder is refused."),
            "path", required=False,
        ),
        _semantic_field(
            "step1_clean_task_dir",
            "Isolated Step 1 review copy folder",
            "The matching client copy folder, or leave blank.",
            "Tasks/bteam-step1-clean-demo",
            ("Use with one signed Step 1 Word reply to reopen only the completed "
             "operator review in this client's isolated copy."),
            "path", required=False,
        ),
        _semantic_field(
            "step1_signed_reply_path",
            "Signed Step 1 operator reply",
            "One existing signed Word reply, or leave blank.",
            "/Users/kamenkamenov/Downloads/BTeam_Step1_Operator_Review_SIGNED.docx",
            ("Use only with the matching Step 1 copy. The harness reads the Word reply "
             "and binds its decisions to the selected source run."),
            "path", required=False,
        ),
        _semantic_field(
            "step2_clean_task_dir",
            "Fresh Step 2 clean-copy folder",
            "The exact dated client copy folder, or leave blank.",
            "Tasks/bteam-step2-clean-20261004",
            ("Use for an ordinary Step 2 resume from the selected clean Step 1 run, "
             "or for a debrief-gate feedback or approval round. The controller "
             "keeps the run and local Drive staging in this client's copy."),
            "path", required=False,
        ),
        _semantic_field(
            "step3_clean_task_dir",
            "Fresh Step 3 clean-copy folder",
            "The exact source-run-named client copy folder, or leave blank.",
            "Tasks/bteam-step3-clean-3f239e371b7a",
            ("Use for an ordinary Step 3 resume from the exact held Step 2 pages, "
             "or for a final-brief-gate feedback or approval round. The controller "
             "keeps artifacts and Drive staging in this client's copy."),
            "path", required=False,
        ),
        _semantic_field(
            "step4_clean_task_dir",
            "Fresh Step 4 clean-copy folder",
            "The source-run-named client copy folder, or leave blank.",
            "Tasks/bteam-step4-clean-91d7941f46dd",
            ("Use after a passed Step 3 gate for the ordinary Step 4 writer or its research gate. "
             "The driver prepares an absent copy and refuses stale or blocked Step 3 sources."),
            "path", required=False,
        ),
        _semantic_field(
            "step4_primary_research_path",
            "Recorded Step 4 interview evidence arriving after the draft",
            "One JSON file inside this Step 4 copy's record folder, or leave blank.",
            "Tasks/bteam-step4-clean-91d7941f46dd/record/primary-research-up-run-example.json",
            (
                "Supply only when reopening a completed Step 4 research compose whose "
                "research gate records primary research as missing. The controller binds "
                "the file to the exact saved run; the harness validates its dipstick."
            ),
            "path", required=False,
        ),
        _semantic_field(
            "step5_clean_task_dir",
            "Fresh Step 5 clean-copy folder",
            "The exact manifest-checked client copy folder, or leave blank.",
            "Tasks/bteam-step5-clean-20261005",
            ("Use for the ordinary Step 5 writer and its review gates. The controller "
             "keeps state, artifacts and Drive staging in this client's copy."),
            "path", required=False,
        ),
        _semantic_field(
            "step6_clean_task_dir", "Fresh Step 6 clean-copy folder",
            "The exact manifest-checked client copy folder, or leave blank.",
            "Tasks/bteam-step6-clean-20261006",
            "Use for the ordinary Step 6 writer and strategy gate; files remain inside the copy.",
            "path", required=False,
        ),
        _semantic_field(
            "step6_held_by", "Step 6 reviewer holding this page",
            "Name the person who explicitly reviewed and held the exact saved Step 6 page, or leave blank.",
            "Kamen", "The controller records a content-bound hold; when both clients are held, "
            "the harness builds or verifies the Maria ZIP.", "string", required=False,
        ),
        _semantic_field(
            "step6_feedback_path", "Typed Step 6 part feedback",
            "One existing typed JSON file in the copy, or leave blank.",
            "Tasks/bteam-step6-clean-20261006/record/step6-feedback.json",
            "Use only at compose-strategy-one-pager for a source-bound Step 6 feedback round.",
            "path", required=False,
        ),
        _semantic_field(
            "step7_clean_task_dir", "Fresh Step 7 clean-copy folder",
            "The exact manifest-checked client copy folder, or leave blank for a new start.",
            "Tasks/bteam-step7-clean-03060ad9afb1",
            "Use for a saved Step 7 child or feedback. A new start uses held-step6-for-step7 with this blank.",
            "path", required=False,
        ),
        _semantic_field(
            "step7_held_by", "Step 7 reviewer holding this page",
            "Name the person who reviewed and held the exact saved Step 7 page, or leave blank.",
            "Kamen", "The controller records the exact hold and closes the Maria ZIP when both clients are held.",
            "string", required=False,
        ),
        _semantic_field(
            "step7_feedback_path", "Typed Step 7 section feedback",
            "One existing typed JSON file in the copy, or leave blank.",
            "Tasks/bteam-step7-clean-03060ad9afb1/record/step7-feedback.json",
            "Use only at compose-message-architecture for source-bound Step 7 feedback.",
            "path", required=False,
        ),
        _semantic_field(
            "step8_clean_task_dir", "Fresh Step 8 clean-copy folder",
            "The exact manifest-checked client copy folder, or leave blank for a new start.",
            "Tasks/bteam-step8-clean-b2224d839ce5",
            "Use for a saved Step 8 child or feedback. A new start uses held-step7-for-step8 with this blank.",
            "path", required=False,
        ),
        _semantic_field(
            "step8_held_by", "Step 8 reviewer holding this page",
            "Name the person who reviewed and held the exact saved Step 8 page, or leave blank.",
            "Kamen", "The controller records the exact hold and closes the Maria ZIP when both clients are held.",
            "string", required=False,
        ),
        _semantic_field(
            "step9_held_by", "Step 9 reviewer holding this toolkit",
            "Name the person who reviewed and held the exact saved Step 9 toolkit, or leave blank.",
            "Kamen", "The controller records a content-bound hold and closes the Maria ZIP when both clients are held.",
            "string", required=False,
        ),
        _semantic_field(
            "step11_held_by", "Step 11 reviewer holding both current pages",
            "Name the person who explicitly reviewed and held the exact current Step 11 pair, or leave blank.",
            "Kamen Kamenov", "The harness binds the hold to both saved pages and resumes only the gate.",
            "string", required=False,
        ),
        _semantic_field(
            "step10_held_by", "Step 10 reviewer holding the accepted pair",
            "Name the person who explicitly holds the admitted Step 10 pages for this Step 11 copy, or leave blank.",
            "Kamen Kamenov", "Used only when the current Step 11 copy waits at the Step 10 measurement gate.",
            "string", required=False,
        ),
        _semantic_field(
            "step10_hold_reason", "Reason for the Step 10 hold",
            "Give the holder's explicit reason for this exact accepted pair, or leave blank.",
            "requirements met", "The exact source and reason are recorded before resuming the gate.",
            "string", required=False,
        ),
        _semantic_field(
            "step9_altitude_check_path", "Step 9 toolkit altitude holder check",
            "One existing JSON holder check in this Step 9 copy's record folder, or leave blank.",
            "Tasks/bteam-step9-clean-a291af445ac4/record/toolkit-altitude-check.json",
            "Use only when the toolkit ship gate explicitly requires a named holder decision.",
            "path", required=False,
        ),
        _semantic_field(
            "step9_newsroom_model", "Step 9 newsroom model decision",
            "One of Maria's three newsroom choices, or leave blank when no new decision is being made.",
            "A phased build that stands the newsroom up before the platform leans on it",
            "Choose exactly: A full always-on newsroom; A lighter founder-plus-agency cadence; or A phased build that stands the newsroom up before the platform leans on it.",
            "string", required=False,
        ),
        _semantic_field(
            "step9_earned_pipeline", "Step 9 earned-pipeline decision",
            "Name who produces the earned pipeline and at what cadence, or leave blank.",
            "United Partners produces a weekly earned pipeline",
            "A named human decision is required before the toolkit writer runs; no producer or cadence is inferred.",
            "string", required=False,
        ),
        _semantic_field(
            "step9_decided_by", "Person making both Step 9 operating decisions",
            "One person's name, or leave blank when no new decision is being made.",
            "Kamen Kamenov",
            "The person must have made both answers; the harness records recommendation standing.",
            "string", required=False,
        ),
        _semantic_field(
            "step11_clean_task_dir",
            "Fresh Step 11 clean-copy folder",
            "The exact dated client copy folder, or leave blank.",
            "Tasks/bteam-step11-clean-20261002",
            ("Use only for Maria's accepted v9 Step 10 page admission, its holder check, "
             "or the subsequent automatic Step 11 writer resume. The controller refuses "
             "the official and earlier rehearsal folders."),
            "path", required=False,
        ),
        _semantic_field(
            "step10_admission_path",
            "Accepted Step 10 admission request",
            "One existing typed JSON file in the clean copy, or leave blank.",
            "Tasks/bteam-step11-clean-20261002/record/step10-admission.json",
            "Supply only when reopening compose-measurement-framework in the clean copy.",
            "path", required=False,
        ),
        _semantic_field(
            "step10_altitude_check_path",
            "Step 10 holder check",
            "One existing typed JSON file in the clean copy, or leave blank.",
            "Tasks/bteam-step11-clean-20261002/record/measurement-altitude-check.json",
            "Supply only when resuming the first unfinished measurement-gate in the clean copy.",
            "path", required=False,
        ),
        _semantic_field(
            "step11_altitude_check_path",
            "Step 11 annual-review holder check",
            "One existing typed JSON file in the clean copy, or leave blank.",
            "Tasks/bteam-step11-clean-20261002/record/annual-review-altitude-check.json",
            "Supply only when resuming the first unfinished annual-review-gate in the clean copy.",
            "path", required=False,
        ),
        _semantic_field(
            "step12_task_dir",
            "Step 12 copy folder",
            "The exact dated client copy folder, or leave blank.",
            "Tasks/bteam-step12-20261010",
            ("Use only to resume Step 12 (assemble-step-dossier through the roadmap gate) in a "
             "Tasks/<client>-step12-<YYYYMMDD> copy that holds state/ and record/. The "
             "controller refuses the official, rehearsal and clean Step 11 folders."),
            "path", required=False,
        ),
        _semantic_field(
            "step12_altitude_check_path",
            "Step 12 roadmap holder check",
            "One existing typed JSON file in the Step 12 copy, or leave blank.",
            "Tasks/bteam-step12-20261010/record/roadmap-altitude-check.json",
            "Supply only when resuming the first unfinished roadmap-gate in the Step 12 copy.",
            "path", required=False,
        ),
        _semantic_field(
            "step9_native_writer_call_limit",
            "Step 9 writer call limit for this client",
            "One whole number from 1 to 150, or leave blank.",
            "60",
            ("Supply with the Step 9 rehearsal copy folder for a new native-writer request. "
             "Leave blank when continuing a saved blocked request so its call limit and cache "
             "remain unchanged."),
            "integer", required=False, minimum=1, maximum=150,
        ),
        _semantic_field(
            "step9_native_writer_continuation",
            "Continue the saved Step 9 writer cache",
            "Answer yes or no.",
            "no",
            ("Answer yes only when the selected run in the exact Tasks/<client>-rehearsal-demo "
             "copy has a persisted Step 9 native-writer request and matching cache budget, and "
             "compose-execution-toolkit is its first unfinished blocked or failed phase, or "
             "a stale interrupted running phase recovered under the copy lock. The "
             "driver checks the root identity, budget ceiling, latest continuation leaf and "
             "copy/client identity before dispatch. Yes preserves the saved request, used calls "
             "and cached parts; it does not re-open the phase."),
            "boolean", required=False,
        ),
        _semantic_field(
            "step9_native_writer_extend_to",
            "Extend the saved Step 9 writer ceiling",
            "Leave blank, enter 60 for the historical B Team 30/30 run, or enter 150 for a latest failed 60/60 rehearsal child.",
            "60",
            ("Supply only with saved-cache continuation for failed run "
             "up-run-9e6d9c40be19 in Tasks/bteam-rehearsal-demo. This raises the saved 30-call "
             "ceiling to 60 while retaining the 30 calls already used and the existing cache. "
             "For a 60/60 child, 150 keeps all 60 spent calls and the same cache."),
            "integer", required=False, minimum=60, maximum=150,
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
        _semantic_field(
            "client_classification_path",
            "Declared client facts",
            "One existing file path.",
            "Tasks/vivacom-corporate-demo/client-classification.json",
            "Supply the account manager's true/false answers for the facts the "
            "required-component conditions turn on. A fact left out is reported "
            "unresolved rather than assumed either way.",
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
            "has_runtime_dependencies",
            "Do any steps use additional checked-in runtime files?",
            "One yes or no answer.",
            "yes",
            (
                "Answer yes for imported modules, called scripts, schemas, templates, or other "
                "files whose contents can change the operation."
            ),
            "boolean",
            required=True,
        ),
        _semantic_field(
            "runtime_dependencies",
            "Additional runtime dependency",
            "Answer one dependency's semantic subquestions at a time.",
            "a checked-in module used by the step script",
            "Record files used at runtime that are not themselves executable steps.",
            "object_list",
            when={"field": "has_runtime_dependencies", "equals": True},
            item_fields=[
                _semantic_field(
                    "repository_key", "Dependency repository",
                    "One registered repository name.", "memory-knowledge",
                    "Use the repository containing the runtime file.", "string",
                    required=True,
                ),
                _semantic_field(
                    "path", "Checked-in runtime file",
                    "One repository-relative path.", "scripts/helper.py",
                    "Provide a file path without shell syntax or parent traversal.",
                    "path", required=True,
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


LOCAL_MULTIMODAL_BENCHMARK_SPEC = {
    "schema_version": script_intake.SCHEMA_VERSION,
    "fields": [
        _semantic_field(
            "source_repository_key", "Benchmark controller repository",
            "One registered repository name.", "memory-knowledge",
            "Choose the repository containing the benchmark controller.",
            "choice", choices=["memory-knowledge"], required=True,
        ),
        _semantic_field(
            "model", "Local model", "One Ollama model tag.",
            "gemma4:26b-mlx",
            "Provide only the local model identity; do not provide command syntax.",
            "string", required=True,
        ),
        _semantic_field(
            "endpoint", "Local Ollama endpoint", "One loopback HTTP URL.",
            "http://127.0.0.1:11434",
            "Only localhost or a loopback IP address is accepted.",
            "string", default="http://127.0.0.1:11434",
        ),
        _semantic_field(
            "pull_if_missing", "Download the model if it is absent",
            "Answer yes or no.", "yes",
            "Existing local models are preserved in either case.",
            "boolean", default=True,
        ),
        _semantic_field(
            "thinking_mode", "Model thinking mode",
            "Choose exactly one listed value.", "disabled",
            "Disabled reserves the response budget for the final structured answer; enabled permits a separate reasoning channel.",
            "choice", choices=["disabled", "enabled"], required=True,
        ),
        _semantic_field(
            "timeout_seconds", "Per-request timeout",
            "One whole number of seconds.", "600",
            "Choose a value from 1 through 3600.",
            "integer", default=600, minimum=1, maximum=3600,
        ),
        _semantic_field(
            "context_length", "Model context length",
            "One whole token count.", "32768",
            "Choose a value from 1024 through 262144.",
            "integer", default=32768, minimum=1024, maximum=262144,
        ),
        _semantic_field(
            "output_path", "Immutable benchmark evidence destination",
            "One absolute new JSON file path.",
            "/private/tmp/local-model-benchmark/evidence.json",
            "The destination must not already exist and will never be overwritten.",
            "path", required=True,
        ),
        _semantic_field(
            "cases", "Benchmark case",
            "Answer one case's semantic subquestions at a time.",
            "one multimodal assessment case",
            "Each case binds its prompt, source images, and expected response schema.",
            "object_list", required=True,
            item_fields=[
                _semantic_field(
                    "id", "Case identity", "One stable short identity.",
                    "annotation-map",
                    "Use letters, numbers, dots, underscores, or hyphens.",
                    "string", required=True,
                ),
                _semantic_field(
                    "prompt", "Model task", "One or more lines of task text.",
                    "Return every visible annotation as structured evidence.",
                    "Describe the assessment goal; close the answer with a line containing only a period.",
                    "text", required=True,
                ),
                _semantic_field(
                    "source_files", "Source image",
                    "One or more absolute image file paths.",
                    "/private/tmp/source.png",
                    "Supported image types are PNG, JPEG, and WebP.",
                    "string_list", required=True,
                    item_prompt="Source image path",
                    item_response_format="One absolute image file path.",
                    item_example="/private/tmp/source.png",
                    item_constraints="Provide an existing PNG, JPEG, or WebP file.",
                ),
                _semantic_field(
                    "response_schema_file", "Expected response schema",
                    "One existing JSON Schema file path.",
                    "/private/tmp/response-schema.json",
                    "Provide a schema file; do not paste schema or invocation syntax.",
                    "path", required=True,
                ),
            ],
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
        "--repository-key", repository_key,
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
        **({
            "host_capabilities": ["repository-git-metadata-write"],
        } if operation != "dry-run" else {}),
    }


def promote_commit_push_dry_run(
    prepared: Mapping[str, Any],
) -> dict[str, Any]:
    """Derive the authorized effect from the exact successful dry-run contract."""
    authorization = prepared.get("authorization")
    argv = prepared.get("argv")
    if (
        prepared.get("sequence_id") != "commit-push-main"
        or prepared.get("profile") != "dry-run"
        or not isinstance(argv, list)
        or not argv
        or "--execute" in argv
        or not isinstance(authorization, Mapping)
        or authorization.get("operation") != "dry-run"
        or authorization.get("effectful") is not False
    ):
        raise AdapterError("prepared-dry-run-not-promotable")
    promoted = deepcopy(dict(prepared))
    promoted["profile"] = "publish"
    promoted["argv"] = [*argv, "--execute"]
    promoted["authorization"] = {
        "effectful": True,
        "required": True,
        "operation": "publish",
    }
    promoted["host_capabilities"] = [
        "repository-git-metadata-write",
    ]
    return promoted


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
    environment = None
    if config.get("requires_dotnet"):
        inherited_path = os.environ.get("PATH", "")
        dotnet_path = str(Path.home() / ".dotnet")
        environment = {
            "PATH": (
                f"{dotnet_path}{os.pathsep}{inherited_path}"
                if inherited_path else dotnet_path
            ),
        }
    return _script_payload(
        sequence_id=sequence_id,
        profile="verified" if verify else "no-verify",
        argv=argv,
        repository_key=repository_key,
        repository_root=repository,
        effectful=True,
        operation="deploy",
        environment=environment,
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


def _prepare_goal_declaration(
    answers: Mapping[str, Any],
    artifact_paths: Mapping[str, str],
    repository_roots: Mapping[str, str],
) -> dict[str, Any]:
    expected = {"repository_key", "statement", "set_by", "supersede_reason", "kpis"}
    if set(answers) != expected:
        raise AdapterError("answer-fields-do-not-match-goal-declaration")
    repository_key, repository = _registered_repository(answers, repository_roots)
    goal_answers = {key: deepcopy(answers[key]) for key in expected - {"repository_key"}}
    try:
        goal_tracker.validate_goal_answers(Path(repository), goal_answers)
    except SystemExit as exc:
        raise AdapterError(f"goal-declaration-invalid:{exc}") from exc
    controller_root = repository_roots.get("memory-knowledge")
    if not isinstance(controller_root, str) or not controller_root:
        raise AdapterError("repository-key-unregistered:memory-knowledge")
    artifact = _json_artifact(artifact_paths, "goal_answers", goal_answers)
    payload = _script_payload(
        sequence_id="goal-declaration",
        profile="set",
        argv=[
            "python3",
            str(Path(controller_root).expanduser().resolve() / "scripts/goal_tracker.py"),
            "--repo", repository,
            "set",
            "--answers-file", artifact["path"],
        ],
        repository_key=repository_key,
        repository_root=repository,
        effectful=True,
        operation="set",
    )
    payload["artifacts"] = {"goal_answers": artifact}
    return payload


def _heartbeat_probe_path(
    value: Any,
    repository: str,
    repository_roots: Mapping[str, str],
) -> Path:
    if not isinstance(value, str) or not value.strip() or any(
        character in value for character in ("\x00", "\n", "\r")
    ):
        raise AdapterError("agent-heartbeat-probe-path-invalid")
    supplied = Path(value).expanduser()
    path = supplied.resolve() if supplied.is_absolute() else (Path(repository) / supplied).resolve()
    allowed_roots = {
        Path("/private/tmp").resolve(),
        *(Path(root).expanduser().resolve() for root in repository_roots.values()),
    }
    if not any(path.is_relative_to(root) for root in allowed_roots):
        raise AdapterError("agent-heartbeat-probe-path-outside-trusted-roots")
    return path


def _heartbeat_literal(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or any(
        character in value for character in ("\x00", "\n", "\r")
    ):
        raise AdapterError(f"agent-heartbeat-{field}-invalid")
    return value.strip()


def _prepare_agent_heartbeat(
    answers: Mapping[str, Any],
    _artifact_paths: Mapping[str, str],
    repository_roots: Mapping[str, str],
) -> dict[str, Any]:
    expected = {"source_repository_key", "seconds", "label", "probes"}
    if set(answers) != expected:
        raise AdapterError("answer-fields-do-not-match-agent-heartbeat")
    repository_key, repository = _registered_repository(
        answers, repository_roots, answer_key="source_repository_key",
    )
    if repository_key != "memory-knowledge":
        raise AdapterError("agent-heartbeat-controller-repository-invalid")
    seconds = answers.get("seconds")
    if not isinstance(seconds, int) or isinstance(seconds, bool) or not 1 <= seconds <= 3600:
        raise AdapterError("agent-heartbeat-seconds-invalid")
    probes = answers.get("probes")
    if not isinstance(probes, list) or not probes:
        raise AdapterError("answer-required:probes")
    commands: list[str] = []
    for probe in probes:
        if not isinstance(probe, Mapping):
            raise AdapterError("agent-heartbeat-probe-invalid")
        kind = probe.get("type")
        if kind == "file-metadata" and set(probe) == {"type", "path"}:
            path = _heartbeat_probe_path(probe["path"], repository, repository_roots)
            commands.append(f"ls -la -- {shlex.quote(str(path))}")
        elif kind == "file-tail" and set(probe) == {"type", "path", "lines"}:
            lines = probe.get("lines")
            if not isinstance(lines, int) or isinstance(lines, bool) or not 1 <= lines <= 500:
                raise AdapterError("agent-heartbeat-lines-invalid")
            path = _heartbeat_probe_path(probe["path"], repository, repository_roots)
            commands.append(f"tail -n {lines} -- {shlex.quote(str(path))}")
        elif kind == "process-state" and set(probe) == {"type", "pattern"}:
            pattern = _heartbeat_literal(probe["pattern"], "process-pattern")
            commands.append(
                "ps -ax -o pid=,etime=,command= | grep -F -- "
                f"{shlex.quote(pattern)} | grep -v '[g]rep -F'"
            )
        elif kind == "container-logs" and set(probe) == {
            "type", "container", "lookback_seconds", "lines",
        }:
            container = _heartbeat_literal(probe["container"], "container")
            if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", container) is None:
                raise AdapterError("agent-heartbeat-container-invalid")
            lookback = probe.get("lookback_seconds")
            lines = probe.get("lines")
            if (
                not isinstance(lookback, int) or isinstance(lookback, bool)
                or not 1 <= lookback <= 86400
                or not isinstance(lines, int) or isinstance(lines, bool)
                or not 1 <= lines <= 500
            ):
                raise AdapterError("agent-heartbeat-container-window-invalid")
            commands.append(
                f"docker logs --since {lookback}s {shlex.quote(container)} 2>&1 | tail -n {lines}"
            )
        else:
            raise AdapterError("agent-heartbeat-probe-contract-invalid")
    argv = [
        "bash", str(Path(repository) / "scripts/agent_heartbeat.sh"),
        "--seconds", str(seconds),
        "--label", _heartbeat_literal(answers.get("label"), "label"),
    ]
    for command in commands:
        argv.extend(["--probe", command])
    return _script_payload(
        sequence_id="agent-heartbeat",
        profile="watch",
        argv=argv,
        repository_key=repository_key,
        repository_root=repository,
        effectful=True,
        operation="watch",
    )


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


def _workflow_resume_live_environment(
    python: str,
    *,
    drive_staging_root: Path | None = None,
    agent_max_attempts: str = "3",
) -> dict[str, str]:
    """Build the shared live environment used by registered workflow resumes."""
    environment = {
        "PYTHONPATH": "src:.",
        "UP_HARNESS_AGENT_COMMAND": f"{python} scripts/codex_role_command.py",
        "UP_HARNESS_AGENT_MAX_ATTEMPTS": agent_max_attempts,
        "UP_HARNESS_AGENT_TIMEOUT_SECONDS": "600",
        "UP_HARNESS_CODEX_TIMEOUT_SECONDS": "600",
    }
    if drive_staging_root is not None:
        environment.update({
            "UP_HARNESS_GOOGLE_DRIVE_ROOT": str(drive_staging_root),
            "UP_HARNESS_GOOGLE_DRIVE_ACCESS_TOKEN": "",
            "UP_HARNESS_GOOGLE_DRIVE_PARENT_ID": "",
        })
    return environment


def _prepare_workflow_phase_resume(
    answers: Mapping[str, Any],
    _artifact_paths: Mapping[str, str],
    repository_roots: Mapping[str, str],
) -> dict[str, Any]:
    answers = {"step1_clean_task_dir": None, "step1_signed_reply_path": None,
               "step2_clean_task_dir": None, "step3_clean_task_dir": None,
               "step4_clean_task_dir": None, "step4_primary_research_path": None,
               "step5_clean_task_dir": None,
               "step6_clean_task_dir": None, "step6_feedback_path": None,
               "step6_held_by": None,
               "step7_clean_task_dir": None, "step7_feedback_path": None,
               "step7_held_by": None,
               "step8_clean_task_dir": None, "step8_held_by": None,
               "step9_held_by": None, "step9_altitude_check_path": None,
               "step9_newsroom_model": None, "step9_earned_pipeline": None,
               "step9_decided_by": None,
               "step11_clean_task_dir": None, "step11_held_by": None,
               "step10_held_by": None, "step10_hold_reason": None, "step10_admission_path": None,
               "step10_altitude_check_path": None, "step11_altitude_check_path": None,
               "step12_task_dir": None, "step12_altitude_check_path": None, **answers}
    expected = {
        "repository_key", "client", "source_run_id",
        "first_unfinished_phase", "reopen_completed_phase",
        "corrected_topic_policies_path", "client_answers_path",
        "debrief_feedback_path", "final_brief_feedback_path", "gate_approvals_path",
        "step11_writer_input_path", "step11_writer_call_budget_path",
        "step11_writer_call_limit", "step11_writer_call_extension_from",
        "step9_rehearsal_task_dir", "step9_native_writer_call_limit",
        "step9_native_writer_continuation",
        "step9_native_writer_extend_to",
        "step1_clean_task_dir", "step1_signed_reply_path",
        "step2_clean_task_dir", "step3_clean_task_dir", "step4_clean_task_dir",
        "step4_primary_research_path",
        "step5_clean_task_dir", "step6_clean_task_dir", "step6_feedback_path", "step6_held_by",
        "step7_clean_task_dir", "step7_feedback_path", "step7_held_by",
        "step11_clean_task_dir", "step11_held_by", "step10_held_by", "step10_hold_reason",
        "step10_admission_path", "step10_altitude_check_path",
        "step8_clean_task_dir", "step8_held_by",
        "step9_held_by", "step9_altitude_check_path",
        "step9_newsroom_model", "step9_earned_pipeline", "step9_decided_by",
        "step11_altitude_check_path", "step12_task_dir", "step12_altitude_check_path",
    }
    if set(answers) != expected:
        raise AdapterError(
            "answer-fields-do-not-match-workflow-phase-resume: got "
            f"{sorted(answers)}, want exactly {sorted(expected)}. Re-run the intake so "
            "every listed question is answered (a blank answer satisfies the optional "
            "corrected_topic_policies_path)."
        )
    if answers["step6_held_by"] not in (None, "") and answers["source_run_id"] != STEP6_RECORDED_SOURCE:
        raise AdapterError("Step 6 spoken hold requires the recorded Step 6 route")
    if answers["step7_held_by"] not in (None, "") and answers["source_run_id"] != STEP7_RECORDED_SOURCE:
        raise AdapterError("Step 7 spoken hold requires the recorded Step 7 route")
    if answers["step8_held_by"] not in (None, "") and answers["source_run_id"] != STEP8_RECORDED_SOURCE:
        raise AdapterError("Step 8 spoken hold requires the recorded Step 8 route")
    if answers["step9_held_by"] not in (None, "") and answers["source_run_id"] != STEP9_RECORDED_SOURCE:
        raise AdapterError("Step 9 spoken hold requires the recorded Step 9 route")
    if answers["step11_held_by"] not in (None, "") and answers["source_run_id"] != STEP11_RECORDED_SOURCE:
        raise AdapterError("Step 11 spoken hold requires the recorded Step 11 route")
    if any(answers[key] not in (None, "") for key in ("step10_held_by", "step10_hold_reason")) \
            and answers["source_run_id"] != STEP11_RECORDED_SOURCE:
        raise AdapterError("Step 10 hold for Step 11 requires the recorded Step 11 route")
    if answers["step9_altitude_check_path"] not in (None, "") and answers["source_run_id"] != STEP9_RECORDED_SOURCE:
        raise AdapterError("Step 9 holder check requires the recorded Step 9 route")
    if any(answers[key] not in (None, "") for key in (
            "step9_newsroom_model", "step9_earned_pipeline", "step9_decided_by")) \
            and answers["source_run_id"] != STEP9_RECORDED_SOURCE:
        raise AdapterError("Step 9 operating decisions require the recorded Step 9 route")
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
    step9_dir = answers["step9_rehearsal_task_dir"]
    step9_limit = answers["step9_native_writer_call_limit"]
    step9_continuation = answers["step9_native_writer_continuation"] is True
    step9_extend_to = answers["step9_native_writer_extend_to"]
    step9_supplied = (
        step9_dir is not None or step9_limit is not None or step9_continuation
        or step9_extend_to is not None
    )
    clean_dir_answer = answers["step11_clean_task_dir"]
    clean_admission = answers["step10_admission_path"]
    clean_altitude = answers["step10_altitude_check_path"]
    clean_annual_altitude = answers["step11_altitude_check_path"]
    clean_supplied = any(value is not None for value in (
        clean_dir_answer, clean_admission, clean_altitude, clean_annual_altitude,
    ))
    clean_writer_supplied = any(answers[key] is not None for key in (
        "step11_writer_input_path", "step11_writer_call_budget_path",
        "step11_writer_call_limit", "step11_writer_call_extension_from",
    ))
    step1_dir: Path | None = None
    if answers["step1_clean_task_dir"] is not None or answers["step1_signed_reply_path"] is not None:
        if answers["step1_clean_task_dir"] is None or answers["step1_signed_reply_path"] is None:
            raise AdapterError("step1-signed-review-needs-copy-and-reply")
        client = _required_text(answers, "client")
        if client not in ("bteam", "vivacom"):
            raise AdapterError("step1-signed-review-client-mismatch")
        expected_step1 = Path(repository).resolve() / "Tasks" / f"{client}-step1-clean-demo"
        supplied_step1 = Path(_required_text(answers, "step1_clean_task_dir"))
        if not supplied_step1.is_absolute():
            supplied_step1 = Path(repository, supplied_step1)
        step1_dir = supplied_step1.resolve()
        if step1_dir != expected_step1 or not (step1_dir / "state").is_dir() or not (step1_dir / "record").is_dir():
            raise AdapterError("step1-signed-review-copy-mismatch")
        if (_required_text(answers, "first_unfinished_phase") != "operator-review-of-pre-engagement-pack"
                or answers["reopen_completed_phase"] is not True):
            raise AdapterError("step1-signed-review-needs-completed-review-reopen")
        other_inputs = ("corrected_topic_policies_path", "client_answers_path",
                        "debrief_feedback_path", "final_brief_feedback_path", "gate_approvals_path",
                        "step11_writer_input_path", "step11_writer_call_budget_path",
                        "step11_writer_call_limit", "step11_writer_call_extension_from",
                        "step9_rehearsal_task_dir", "step9_native_writer_call_limit",
                        "step9_native_writer_continuation", "step9_native_writer_extend_to",
                        "step2_clean_task_dir", "step3_clean_task_dir", "step4_clean_task_dir",
                        "step5_clean_task_dir", "step6_clean_task_dir", "step6_feedback_path",
                        "step7_clean_task_dir", "step7_feedback_path", "step8_clean_task_dir",
                        "step11_clean_task_dir", "step10_admission_path", "step10_altitude_check_path",
                        "step11_altitude_check_path", "step12_task_dir", "step12_altitude_check_path")
        if any(answers[key] not in (None, False) for key in other_inputs):
            raise AdapterError("step1-signed-review-exclusive-route")
        selected_id = _required_text(answers, "source_run_id")
        if not re.fullmatch(r"up-run-[a-z0-9]+", selected_id):
            raise AdapterError("step1-signed-review-source-mismatch")
        try:
            source = json.loads((step1_dir / "state" / f"{selected_id}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            raise AdapterError("step1-signed-review-source-missing") from None
        source_inputs = (source.get("context") or {}).get("inputs") or {}
        if (source.get("run_id") != selected_id
                or source.get("status") != "blocked"
                or source_inputs.get("client_code") != {"bteam": "BTM", "vivacom": "VIV"}[client]
                or source_inputs.get("client_name") != {"bteam": "The B Team", "vivacom": "Vivacom"}[client]
                or source_inputs.get("stop_after_phase") != "operator-review-of-pre-engagement-pack"
                or (source.get("phases") or {}).get("operator-review-of-pre-engagement-pack", {}).get("status") != "completed"):
            raise AdapterError("step1-signed-review-source-mismatch")
        reply_path = Path(_required_text(answers, "step1_signed_reply_path"))
        if not reply_path.is_absolute():
            reply_path = Path(repository, reply_path)
        reply_path = reply_path.resolve()
        if reply_path.suffix.lower() != ".docx" or not reply_path.is_file():
            raise AdapterError("step1-signed-review-word-reply-missing")
        argv.extend(["--task-dir", str(step1_dir), "--operator-review-reply-file", str(reply_path)])
    step2_dir_answer = answers["step2_clean_task_dir"]
    step2_dir: Path | None = None
    if step2_dir_answer is not None:
        client = _required_text(answers, "client")
        expected_step2 = Path(repository).resolve() / "Tasks" / f"{client}-step2-clean-20261004"
        supplied_step2 = Path(_required_text(answers, "step2_clean_task_dir"))
        if not supplied_step2.is_absolute():
            supplied_step2 = Path(repository, supplied_step2)
        step2_dir = supplied_step2.resolve()
        source_id = _required_text(answers, "source_run_id")
        current_name = re.fullmatch(rf"{re.escape(client)}-step2-clean-([0-9a-f]{{12}})", step2_dir.name)
        current_copy = (step2_dir.parent == (Path(repository).resolve() / "Tasks")
                        and current_name is not None)
        if step2_dir != expected_step2 and not current_copy:
            raise AdapterError("step2-clean-copy-missing-or-mismatched")
        if current_copy:
            root_source_id = f"up-run-{current_name.group(1)}"
            if not re.fullmatch(r"up-run-[a-z0-9]+", source_id):
                raise AdapterError("step2-clean-copy-source-run-mismatch")
            source = (Path(repository).resolve() / "Tasks" / f"{client}-step1-clean-demo")
            source_state = source / "state" / f"{root_source_id}.json"
            if not source_state.is_file():
                raise AdapterError("step2-clean-copy-source-state-missing")
            source_sha = hashlib.sha256(source_state.read_bytes()).hexdigest()
            if step2_dir.is_dir():
                manifest_path = step2_dir / "record" / "step2-clean-copy.json"
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise AdapterError("step2-clean-copy-manifest-missing-or-invalid") from exc
                try:
                    copy_root = step2_dir.resolve(strict=True)
                    state_root = (step2_dir / "state").resolve(strict=True)
                except OSError:
                    raise AdapterError("step2-clean-copy-needs-state-and-record") from None
                if state_root != copy_root / "state" or not state_root.is_dir():
                    raise AdapterError("step2-clean-copy-state-outside-copy")
                copied_state = state_root / f"{root_source_id}.json"
                if (not isinstance(manifest, dict)
                        or manifest.get("schema") != "step2-clean-copy/v2"
                        or manifest.get("client") != client
                        or manifest.get("source_task_dir") != str(source)
                        or manifest.get("source_run_id") != root_source_id
                        or manifest.get("source_run_sha256") != source_sha
                        or not copied_state.is_file()
                        or hashlib.sha256(copied_state.read_bytes()).hexdigest() != source_sha):
                    raise AdapterError("step2-clean-copy-manifest-mismatch")
                def read_copy_state(run_id: str) -> dict:
                    if not re.fullmatch(r"up-run-[a-z0-9]+", run_id):
                        raise AdapterError("step2-clean-copy-lineage-mismatch")
                    candidate = state_root / f"{run_id}.json"
                    try:
                        state_path = candidate.resolve(strict=True)
                        state_path.relative_to(state_root)
                        if (state_path.parent != state_root
                                or state_path.name != f"{run_id}.json"):
                            raise ValueError("state path is not a direct child")
                        state = json.loads(state_path.read_text(encoding="utf-8"))
                    except (OSError, UnicodeDecodeError, ValueError, TypeError):
                        raise AdapterError("step2-clean-copy-lineage-mismatch") from None
                    if not isinstance(state, dict) or state.get("run_id") != run_id:
                        raise AdapterError("step2-clean-copy-lineage-mismatch")
                    return state

                cursor_id = source_id
                seen: set[str] = set()
                cursor = read_copy_state(cursor_id)
                while cursor_id != root_source_id:
                    if cursor_id in seen or len(seen) >= 100:
                        raise AdapterError("step2-clean-copy-lineage-mismatch")
                    seen.add(cursor_id)
                    parent_id = cursor.get("parent_run_id")
                    if not isinstance(parent_id, str):
                        raise AdapterError("step2-clean-copy-lineage-mismatch")
                    cursor_id = parent_id
                    cursor = read_copy_state(cursor_id)
            elif source_id != root_source_id:
                raise AdapterError("step2-clean-copy-source-run-mismatch")
            elif (_required_text(answers, "first_unfinished_phase")
                  != "prepare-controlled-topic-policy-inputs"):
                raise AdapterError("step2-clean-copy-missing-before-later-phase")
        elif not step2_dir.is_dir():
            raise AdapterError("step2-clean-copy-missing-or-mismatched")
        if step2_dir.is_dir() and (not (step2_dir / "state").is_dir()
                                   or not (step2_dir / "record").is_dir()):
            raise AdapterError("step2-clean-copy-needs-state-and-record")
        if _required_text(answers, "first_unfinished_phase") not in STEP2_ALLOWED_PHASES:
            raise AdapterError("step2-clean-copy-phase-outside-step2")
        if (step9_supplied or clean_supplied or clean_writer_supplied
                or answers["step3_clean_task_dir"] is not None
                or answers["step4_clean_task_dir"] is not None
                or answers["step5_clean_task_dir"] is not None
                or answers["step12_task_dir"] is not None
                or answers["step12_altitude_check_path"] is not None
                or any(answers[key] is not None for key in (
                    "final_brief_feedback_path", "step10_admission_path",
                    "step10_altitude_check_path", "step11_altitude_check_path",
                ))):
            raise AdapterError("step2-clean-copy-exclusive-with-other-routes")
        phase = _required_text(answers, "first_unfinished_phase")
        for key in ("client_answers_path", "corrected_topic_policies_path",
                    "debrief_feedback_path", "gate_approvals_path"):
            raw = answers[key]
            if raw is None:
                continue
            selected = Path(raw)
            if not selected.is_absolute():
                selected = Path(repository, selected)
            selected = selected.resolve()
            if (selected.parent != step2_dir / "record" or not selected.is_file()):
                raise AdapterError(f"step2-clean-copy-input-must-be-in-record:{key}")
            if key in ("debrief_feedback_path", "gate_approvals_path") and phase != "debrief-gate":
                raise AdapterError(f"step2-clean-copy-gate-input-needs-debrief-gate:{key}")
        argv.extend(["--task-dir", str(step2_dir)])
    step3_dir_answer = answers["step3_clean_task_dir"]
    step3_dir: Path | None = None
    if step3_dir_answer is not None:
        client = _required_text(answers, "client")
        supplied_step3 = Path(_required_text(answers, "step3_clean_task_dir"))
        if not supplied_step3.is_absolute():
            supplied_step3 = Path(repository, supplied_step3)
        step3_dir = supplied_step3.resolve()
        tasks_dir = Path(repository).resolve() / "Tasks"
        source_run_id = _required_text(answers, "source_run_id")
        named_root = re.fullmatch(
            rf"{re.escape(client)}-step3-clean-([0-9a-f]{{12}})", step3_dir.name
        )
        root_run_id = f"up-run-{named_root.group(1)}" if named_root else source_run_id
        expected_step3 = tasks_dir / f"{client}-step3-clean-{root_run_id.removeprefix('up-run-')}"
        legacy_step3 = tasks_dir / f"{client}-step3-clean-20261005"
        if step3_dir not in {expected_step3, legacy_step3} or (
            step3_dir != legacy_step3 and named_root is None
        ):
            raise AdapterError("step3-clean-copy-missing-or-mismatched")
        phase = _required_text(answers, "first_unfinished_phase")
        if phase not in STEP3_ALLOWED_PHASES:
            raise AdapterError("step3-clean-copy-phase-outside-step3")
        staging_only = (
            step3_dir.is_dir()
            and all(child.name == "drive-staging" and child.is_dir() and not child.is_symlink()
                    for child in step3_dir.iterdir())
        )
        unprepared_step3 = not step3_dir.is_dir() or staging_only
        if unprepared_step3:
            if (step3_dir != expected_step3 or phase != "compose-final-brief"
                    or source_run_id != root_run_id):
                raise AdapterError("step3-clean-copy-missing-or-mismatched")
            # The ordinary driver prepares this copy and validates the current
            # accepted Step 2 receipt before any model work.
        elif not (step3_dir / "state").is_dir() or not (step3_dir / "record" / "step3-clean-copy.json").is_file():
            raise AdapterError("step3-clean-copy-needs-state-and-record")
        if step3_dir == legacy_step3:
            if phase == "compose-final-brief":
                raise AdapterError("step3-clean-copy-old-source-cannot-start-new-compose")
        elif not unprepared_step3:
            try:
                manifest = json.loads((step3_dir / "record" / "step3-clean-copy.json").read_text(encoding="utf-8"))
                receipt_name = manifest["step2_package_receipt"]
                if (not re.fullmatch(r"maria-step2-pack-[0-9a-f]{16}-receipt\.json", receipt_name)
                        or not re.fullmatch(r"up-run-[0-9a-f]{12}", source_run_id)):
                    raise AdapterError("step3-clean-copy-source-or-receipt-mismatch")
                receipt_path = tasks_dir / "step2-rule-controller" / receipt_name
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                source_dir = Path(repository).resolve() / manifest["source_task_dir"]
                source_path = source_dir / "state" / f"{root_run_id}.json"
                if (manifest.get("schema") != "step3-clean-copy/v3"
                        or manifest.get("client") != client
                        or manifest.get("source_run_id") != root_run_id
                        or source_dir.parent != tasks_dir
                        or receipt.get("runs", {}).get(client) != root_run_id
                        or receipt.get("page_pair_sha256", {}).get(client) != manifest.get("step2_page_pair_sha256")
                        or hashlib.sha256(receipt_path.read_bytes()).hexdigest() != manifest.get("step2_package_receipt_sha256")
                        or hashlib.sha256(source_path.read_bytes()).hexdigest() != manifest.get("source_run_sha256")):
                    raise AdapterError("step3-clean-copy-source-or-receipt-mismatch")
                # The copy is named for its Step 2 source, while a gate resume selects a
                # later Step 3 child. Prove that child descends from the admitted root.
                cursor = source_run_id
                visited: set[str] = set()
                while cursor != root_run_id:
                    if cursor in visited or not re.fullmatch(r"up-run-[0-9a-f]{12}", cursor):
                        raise AdapterError("step3-clean-copy-child-lineage-mismatch")
                    visited.add(cursor)
                    child_path = step3_dir / "state" / f"{cursor}.json"
                    if not child_path.is_file():
                        raise AdapterError("step3-clean-copy-child-lineage-mismatch")
                    child = json.loads(child_path.read_text(encoding="utf-8"))
                    if child.get("run_id") != cursor:
                        raise AdapterError("step3-clean-copy-child-lineage-mismatch")
                    cursor = str(child.get("parent_run_id") or "")
            except AdapterError:
                raise
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise AdapterError("step3-clean-copy-source-or-receipt-mismatch") from exc
        if (step2_dir is not None or step9_supplied or clean_supplied or clean_writer_supplied
                or answers["step4_clean_task_dir"] is not None
                or answers["step5_clean_task_dir"] is not None
                or answers["step12_task_dir"] is not None
                or any(answers[key] is not None for key in (
                    "client_answers_path", "corrected_topic_policies_path",
                    "debrief_feedback_path", "step10_admission_path",
                    "step10_altitude_check_path", "step11_altitude_check_path",
                    "step12_altitude_check_path"))):
            raise AdapterError("step3-clean-copy-exclusive-with-other-routes")
        for key in ("final_brief_feedback_path", "gate_approvals_path"):
            raw = answers[key]
            if raw is None:
                continue
            selected = Path(raw)
            if not selected.is_absolute():
                selected = Path(repository, selected)
            selected = selected.resolve()
            if selected.parent != step3_dir / "record" or not selected.is_file():
                raise AdapterError(f"step3-clean-copy-input-must-be-in-record:{key}")
            if phase != "final-brief-gate":
                raise AdapterError(f"step3-clean-copy-gate-input-needs-final-brief-gate:{key}")
        argv.extend(["--task-dir", str(step3_dir)])
    step4_dir_answer = answers["step4_clean_task_dir"]
    step4_primary_path_answer = answers["step4_primary_research_path"]
    step4_dir: Path | None = None
    step5_handoff_dir: Path | None = None
    step6_handoff_dir: Path | None = None
    step7_handoff_dir: Path | None = None
    step8_handoff_dir: Path | None = None
    step9_handoff_dir: Path | None = None
    if answers["source_run_id"] == STEP5_RECORDED_SOURCE:
        client = _required_text(answers, "client")
        phase = _required_text(answers, "first_unfinished_phase")
        base_fields = {"repository_key", "client", "source_run_id",
                       "first_unfinished_phase", "reopen_completed_phase"}
        other_inputs = [key for key in sorted(expected - base_fields)
                        if answers[key] not in (None, False)]
        if (client not in {"bteam", "vivacom"}
                or phase != "compose-insight-cards"
                or answers["reopen_completed_phase"] is not False
                or other_inputs):
            raise AdapterError(
                "accepted Step 5 source starts only its first compose with no other route inputs: "
                + ", ".join(other_inputs)
            )
        try:
            source_check = subprocess.run(
                [python, str(Path(repository, "scripts/prepare_step5_clean_copy.py")),
                 "--resolve-recorded-route", "--client", client],
                cwd=repository, env={**os.environ, "PYTHONPATH": "src:."},
                capture_output=True, text=True, timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AdapterError(f"{client}: recorded Step 5 source check could not run") from exc
        if source_check.returncode != 0:
            raise AdapterError(
                f"{client}: recorded Step 5 route could not be selected; "
                "inspect the accepted source and saved copy before starting"
            )
        try:
            route = json.loads(source_check.stdout)
            run_id = route["run_id"]
            root_id = route["source_run_id"]
            selected_dir = Path(route["task_dir"])
            target = Path(route["copy_dir"])
            selected_phase = route["phase"]
        except (ValueError, KeyError, TypeError):
            raise AdapterError(f"{client}: recorded Step 5 route result is invalid") from None
        tasks_dir = Path(repository).resolve() / "Tasks"
        expected_target = tasks_dir / f"{client}-step5-clean-{root_id.removeprefix('up-run-')}"
        source_name = selected_dir.name
        if (not re.fullmatch(r"up-run-[0-9a-f]{12}", run_id)
                or not re.fullmatch(r"up-run-[0-9a-f]{12}", root_id)
                or selected_phase not in STEP5_ALLOWED_PHASES
                or target != expected_target
                or selected_dir.parent != tasks_dir
                or (run_id != root_id and selected_dir != target)
                or (run_id == root_id and source_name != f"{client}-corporate-demo"
                    and not re.fullmatch(rf"{re.escape(client)}-step4-clean-[0-9a-f]{{12}}", source_name))):
            raise AdapterError(f"{client}: recorded Step 5 route has the wrong identity")
        if route.get("status") != "ready":
            if route.get("status") == "held":
                other = "vivacom" if client == "bteam" else "bteam"
                try:
                    other_check = subprocess.run(
                        [python, str(Path(repository, "scripts/prepare_step5_clean_copy.py")),
                         "--resolve-recorded-route", "--client", other],
                        cwd=repository, env={**os.environ, "PYTHONPATH": "src:."},
                        capture_output=True, text=True, timeout=30,
                    )
                    other_route = json.loads(other_check.stdout) if other_check.returncode == 0 else {}
                except (OSError, subprocess.TimeoutExpired, ValueError, TypeError) as exc:
                    raise AdapterError(f"{other}: recorded Step 5 hold could not be checked") from exc
                if other_route.get("status") != "held":
                    raise AdapterError(
                        f"{client}: Step 5 is held; {other} is "
                        f"{other_route.get('status', 'unavailable')}; both holds are needed for the Maria ZIP"
                    )
                return _script_payload(
                    sequence_id="workflow-resume-from-phase-live-confirmation",
                    profile="resume",
                    argv=[python, "-m", "up_harness.step5_maria_package", "--close-recorded"],
                    repository_key=repository_key,
                    repository_root=repository,
                    effectful=True,
                    operation="resume",
                    environment={"PYTHONPATH": "src:.",
                                 "UP_HARNESS_GOOGLE_DRIVE_ACCESS_TOKEN": "",
                                 "UP_HARNESS_GOOGLE_DRIVE_PARENT_ID": ""},
                )
            if route.get("status") in {"complete", "awaiting-human"}:
                raise AdapterError(f"{client}: Step 5 is already {route['status']} at {selected_phase}; no writer resume is needed")
            raise AdapterError(f"{client}: recorded Step 5 route has an invalid status")
        argv[argv.index("--resume-run") + 1] = run_id
        argv[argv.index("--from-phase") + 1] = selected_phase
        argv.extend(["--task-dir", str(selected_dir)])
        step5_handoff_dir = target
    if answers["source_run_id"] == STEP6_RECORDED_SOURCE:
        client = _required_text(answers, "client")
        phase = _required_text(answers, "first_unfinished_phase")
        base_fields = {"repository_key", "client", "source_run_id",
                       "first_unfinished_phase", "reopen_completed_phase", "step6_held_by"}
        other_inputs = [key for key in sorted(expected - base_fields)
                        if answers[key] not in (None, False)]
        if (client not in {"bteam", "vivacom"}
                or phase != "compose-strategy-one-pager"
                or answers["reopen_completed_phase"] is not False
                or other_inputs):
            raise AdapterError("held Step 6 source requires only client and first compose")
        check = subprocess.run(
            [python, str(Path(repository, "scripts/prepare_step6_clean_copy.py")),
             "--resolve-recorded-route", "--client", client],
            cwd=repository, env={**os.environ, "PYTHONPATH": "src:."},
            capture_output=True, text=True, timeout=30,
        )
        if check.returncode != 0:
            raise AdapterError(f"{client}: current held Step 5 source could not be selected")
        try:
            route = json.loads(check.stdout)
            run_id = route["run_id"]
            source_id = route["source_run_id"]
            selected_dir = Path(route["task_dir"])
            target = Path(route["copy_dir"])
            selected_phase = route["phase"]
        except (ValueError, KeyError, TypeError) as exc:
            raise AdapterError(f"{client}: recorded Step 6 route is invalid") from exc
        tasks_dir = Path(repository).resolve() / "Tasks"
        expected_target = tasks_dir / f"{client}-step6-clean-{source_id.removeprefix('up-run-')}"
        if (not re.fullmatch(r"up-run-[0-9a-f]{12}", run_id)
                or not re.fullmatch(r"up-run-[0-9a-f]{12}", source_id)
                or selected_phase not in {"compose-strategy-one-pager", "strategy-approach-gate"}
                or target != expected_target or selected_dir.parent != tasks_dir
                or (run_id != source_id and selected_dir != target)):
            raise AdapterError(f"{client}: recorded Step 6 route has the wrong identity")
        held_by = answers["step6_held_by"]
        if route["status"] == "awaiting-human":
            if not isinstance(held_by, str) or not held_by.strip():
                raise AdapterError(f"{client}: the Step 6 page needs an explicit named hold")
            return _script_payload(
                sequence_id="workflow-resume-from-phase-live-confirmation",
                profile="resume", repository_key=repository_key,
                repository_root=repository, effectful=True, operation="resume",
                argv=[python, "-m", "up_harness.step6_review_hold", "--recorded",
                      "--client", client, "--held-by", held_by.strip(), "--confirmed-held"],
                environment={"PYTHONPATH": "src:."},
            )
        if route["status"] == "held":
            if held_by not in (None, ""):
                raise AdapterError(f"{client}: Step 6 is already held; no new hold is needed")
            other = "vivacom" if client == "bteam" else "bteam"
            other_check = subprocess.run(
                [python, str(Path(repository, "scripts/prepare_step6_clean_copy.py")),
                 "--resolve-recorded-route", "--client", other],
                cwd=repository, env={**os.environ, "PYTHONPATH": "src:."},
                capture_output=True, text=True, timeout=30,
            )
            if other_check.returncode != 0:
                raise AdapterError(f"{other}: recorded Step 6 hold could not be checked")
            if json.loads(other_check.stdout).get("status") != "held":
                raise AdapterError(f"{client}: both Step 6 pages must be held before ZIP closeout")
            return _script_payload(
                sequence_id="workflow-resume-from-phase-live-confirmation",
                profile="resume", repository_key=repository_key,
                repository_root=repository, effectful=True, operation="resume",
                argv=[python, "-m", "up_harness.step6_maria_package", "--close-recorded"],
                environment={"PYTHONPATH": "src:."},
            )
        if route["status"] != "ready" or held_by not in (None, ""):
            raise AdapterError(f"{client}: Step 6 is {route['status']}; a writer resume cannot record a hold")
        argv[argv.index("--resume-run") + 1] = run_id
        argv[argv.index("--from-phase") + 1] = selected_phase
        argv.extend(["--task-dir", str(selected_dir)])
        step6_handoff_dir = target
    if answers["source_run_id"] == STEP7_RECORDED_SOURCE:
        client = _required_text(answers, "client")
        phase = _required_text(answers, "first_unfinished_phase")
        base_fields = {"repository_key", "client", "source_run_id",
                       "first_unfinished_phase", "reopen_completed_phase", "step7_held_by"}
        other_inputs = [key for key in sorted(expected - base_fields)
                        if answers[key] not in (None, False)]
        if (client not in {"bteam", "vivacom"}
                or phase != "compose-big-idea"
                or answers["reopen_completed_phase"] is not False
                or other_inputs):
            raise AdapterError("held Step 6 source for Step 7 requires only client and first compose")
        check = subprocess.run(
            [python, str(Path(repository, "scripts/prepare_step7_clean_copy.py")),
             "--resolve-recorded-route", "--client", client],
            cwd=repository, env={**os.environ, "PYTHONPATH": "src:."},
            capture_output=True, text=True, timeout=30,
        )
        if check.returncode != 0:
            raise AdapterError(f"{client}: current held Step 6 source for Step 7 could not be selected")
        try:
            route = json.loads(check.stdout)
            run_id = route["run_id"]
            source_id = route["source_run_id"]
            selected_dir = Path(route["task_dir"])
            target = Path(route["copy_dir"])
            selected_phase = route["phase"]
        except (ValueError, KeyError, TypeError) as exc:
            raise AdapterError(f"{client}: recorded Step 7 route is invalid") from exc
        tasks_dir = Path(repository).resolve() / "Tasks"
        expected_target = tasks_dir / f"{client}-step7-clean-{source_id.removeprefix('up-run-')}"
        if (not re.fullmatch(r"up-run-[0-9a-f]{12}", run_id)
                or not re.fullmatch(r"up-run-[0-9a-f]{12}", source_id)
                or selected_phase not in {"compose-big-idea", "big-idea-gate",
                                          "compose-message-architecture", "narrative-gate"}
                or target != expected_target or selected_dir.parent != tasks_dir
                or (run_id != source_id and selected_dir != target)):
            raise AdapterError(f"{client}: recorded Step 7 route has the wrong identity")
        held_by = answers["step7_held_by"]
        if route["status"] == "awaiting-human":
            if not isinstance(held_by, str) or not held_by.strip():
                raise AdapterError(f"{client}: the Step 7 page needs an explicit named hold")
            return _script_payload(
                sequence_id="workflow-resume-from-phase-live-confirmation",
                profile="resume", repository_key=repository_key,
                repository_root=repository, effectful=True, operation="resume",
                argv=[python, "-m", "up_harness.step7_review_hold", "--recorded",
                      "--client", client, "--held-by", held_by.strip(), "--confirmed-held"],
                environment={"PYTHONPATH": "src:."},
            )
        if route["status"] == "held":
            if held_by not in (None, ""):
                raise AdapterError(f"{client}: Step 7 is already held; no new hold is needed")
            other = "vivacom" if client == "bteam" else "bteam"
            other_check = subprocess.run(
                [python, str(Path(repository, "scripts/prepare_step7_clean_copy.py")),
                 "--resolve-recorded-route", "--client", other],
                cwd=repository, env={**os.environ, "PYTHONPATH": "src:."},
                capture_output=True, text=True, timeout=30,
            )
            if other_check.returncode != 0 or json.loads(other_check.stdout).get("status") != "held":
                raise AdapterError(f"{client}: both Step 7 pages must be held before ZIP closeout")
            return _script_payload(
                sequence_id="workflow-resume-from-phase-live-confirmation",
                profile="resume", repository_key=repository_key,
                repository_root=repository, effectful=True, operation="resume",
                argv=[python, "-m", "up_harness.step7_maria_package", "--close-recorded"],
                environment={"PYTHONPATH": "src:."},
            )
        if route["status"] != "ready" or held_by not in (None, ""):
            raise AdapterError(f"{client}: Step 7 is {route['status']}; a writer resume cannot record a hold")
        argv[argv.index("--resume-run") + 1] = run_id
        argv[argv.index("--from-phase") + 1] = selected_phase
        argv.extend(["--task-dir", str(selected_dir)])
        if route.get("reopen_completed_phase") is True:
            if (run_id == source_id or selected_dir != target
                    or selected_phase != "compose-message-architecture"):
                raise AdapterError(f"{client}: Step 7 completed-phase route is invalid")
            argv.append("--rerun-completed")
        step7_handoff_dir = target
    if answers["source_run_id"] == STEP8_RECORDED_SOURCE:
        client = _required_text(answers, "client")
        phase = _required_text(answers, "first_unfinished_phase")
        base_fields = {"repository_key", "client", "source_run_id",
                       "first_unfinished_phase", "reopen_completed_phase", "step8_held_by"}
        other_inputs = [key for key in sorted(expected - base_fields)
                        if answers[key] not in (None, False)]
        if (client not in {"bteam", "vivacom"}
                or phase != "compose-communications-platform"
                or answers["reopen_completed_phase"] is not False
                or other_inputs):
            raise AdapterError("held Step 7 source for Step 8 requires only client and first compose")
        check = subprocess.run(
            [python, str(Path(repository, "scripts/prepare_step8_clean_copy.py")),
             "--resolve-recorded-route", "--client", client],
            cwd=repository, env={**os.environ, "PYTHONPATH": "src:."},
            capture_output=True, text=True, timeout=30,
        )
        if check.returncode != 0:
            raise AdapterError(f"{client}: current held Step 7 source for Step 8 could not be selected")
        try:
            route = json.loads(check.stdout)
            run_id = route["run_id"]
            source_id = route["source_run_id"]
            selected_dir = Path(route["task_dir"])
            target = Path(route["copy_dir"])
            selected_phase = route["phase"]
        except (ValueError, KeyError, TypeError) as exc:
            raise AdapterError(f"{client}: recorded Step 8 route is invalid") from exc
        tasks_dir = Path(repository).resolve() / "Tasks"
        expected_target = tasks_dir / f"{client}-step8-clean-{source_id.removeprefix('up-run-')}"
        if (not re.fullmatch(r"up-run-[0-9a-f]{12}", run_id)
                or not re.fullmatch(r"up-run-[0-9a-f]{12}", source_id)
                or selected_phase not in {"compose-communications-platform", "platform-architecture-gate"}
                or target != expected_target or selected_dir.parent != tasks_dir
                or (run_id != source_id and selected_dir != target)):
            raise AdapterError(f"{client}: recorded Step 8 route has the wrong identity")
        held_by = answers["step8_held_by"]
        if route["status"] == "awaiting-human":
            if not isinstance(held_by, str) or not held_by.strip():
                raise AdapterError(f"{client}: the Step 8 page needs an explicit named hold")
            return _script_payload(
                sequence_id="workflow-resume-from-phase-live-confirmation",
                profile="resume", repository_key=repository_key,
                repository_root=repository, effectful=True, operation="resume",
                argv=[python, "-m", "up_harness.step8_review_hold", "--recorded",
                      "--client", client, "--held-by", held_by.strip(), "--confirmed-held"],
                environment={"PYTHONPATH": "src:."},
            )
        if route["status"] == "held":
            if held_by not in (None, ""):
                raise AdapterError(f"{client}: Step 8 is already held; no new hold is needed")
            other = "vivacom" if client == "bteam" else "bteam"
            other_check = subprocess.run(
                [python, str(Path(repository, "scripts/prepare_step8_clean_copy.py")),
                 "--resolve-recorded-route", "--client", other],
                cwd=repository, env={**os.environ, "PYTHONPATH": "src:."},
                capture_output=True, text=True, timeout=30,
            )
            if other_check.returncode != 0 or json.loads(other_check.stdout).get("status") != "held":
                raise AdapterError(f"{client}: both Step 8 pages must be held before ZIP closeout")
            return _script_payload(
                sequence_id="workflow-resume-from-phase-live-confirmation",
                profile="resume", repository_key=repository_key,
                repository_root=repository, effectful=True, operation="resume",
                argv=[python, "-m", "up_harness.step8_maria_package", "--close-recorded"],
                environment={"PYTHONPATH": "src:."},
            )
        if route["status"] != "ready" or held_by not in (None, ""):
            raise AdapterError(f"{client}: Step 8 is {route['status']}; a writer resume cannot record a hold")
        argv[argv.index("--resume-run") + 1] = run_id
        argv[argv.index("--from-phase") + 1] = selected_phase
        argv.extend(["--task-dir", str(selected_dir)])
        if route.get("reopen_completed_phase") is True:
            if (run_id == source_id or selected_dir != target
                    or selected_phase != "compose-communications-platform"):
                raise AdapterError(f"{client}: Step 8 completed-phase route is invalid")
            argv.append("--rerun-completed")
        step8_handoff_dir = target
    if answers["source_run_id"] == STEP11_RECORDED_SOURCE:
        client = _required_text(answers, "client")
        base_fields = {"repository_key", "client", "source_run_id",
                       "first_unfinished_phase", "reopen_completed_phase", "step11_held_by",
                       "step10_held_by", "step10_hold_reason", "step11_writer_call_limit"}
        other_inputs = [key for key in sorted(expected - base_fields)
                        if answers[key] not in (None, False)]
        if (client not in {"bteam", "vivacom"}
                or answers["first_unfinished_phase"] != "compose-annual-review"
                or answers["reopen_completed_phase"] is not False or other_inputs):
            raise AdapterError("recorded-step11-route-needs-client-and-no-manual-paths")
        check = subprocess.run(
            [python, str(Path(repository, "scripts/prepare_step11_clean_copy.py")),
             "--resolve-recorded-route", "--client", client],
            cwd=repository, env={**os.environ, "PYTHONPATH": "src:."},
            capture_output=True, text=True, timeout=45,
        )
        if check.returncode != 0:
            raise AdapterError(f"{client}: current accepted Step 10 source for Step 11 could not be selected")
        try:
            route = json.loads(check.stdout)
            target = Path(route["copy_dir"])
            selected = Path(route["task_dir"])
            status = route["status"]
        except (ValueError, KeyError, TypeError) as exc:
            raise AdapterError(f"{client}: recorded Step 11 route is invalid") from exc
        tasks_dir = Path(repository).resolve() / "Tasks"
        if (target.parent != tasks_dir
                or not re.fullmatch(rf"{re.escape(client)}-step11-clean-(?:20261002|[0-9a-f]{{12}})", target.name)
                or selected.parent != tasks_dir
                or status not in {"needs-copy", "ready", "awaiting-step10-hold", "awaiting-human",
                                  "awaiting-writer-budget", "feedback-pending", "held"}
                or (status != "needs-copy" and selected != target)):
            raise AdapterError(f"{client}: recorded Step 11 route has the wrong source or copy identity")
        if status == "feedback-pending":
            outstanding = route.get("feedback_state")
            if (not isinstance(outstanding, list) or not outstanding
                    or any(not isinstance(note, dict)
                           or not re.fullmatch(r"[0-9a-f]{64}", str(note.get("note_sha256", "")))
                           or any(not isinstance(note.get(key), list)
                                  or any(not isinstance(item, str) or not item
                                         for item in note[key])
                                  for key in ("needs_routing", "needs_approval", "needs_other_work"))
                           for note in outstanding)):
                raise AdapterError(f"{client}: recorded Step 11 feedback state is invalid")
            actions = []
            for note in outstanding:
                for key, verb in (("needs_routing", "route"),
                                  ("needs_approval", "approve"),
                                  ("needs_other_work", "complete non-page work for")):
                    if note[key]:
                        actions.append(f"{verb} {', '.join(note[key])}")
            if not actions:
                raise AdapterError(f"{client}: recorded Step 11 feedback state is empty")
            raise AdapterError(
                f"{client}: Step 11 feedback is still open; {'; '.join(actions)} "
                "before resume or ZIP closeout")
        writer_limit = answers["step11_writer_call_limit"]
        if status == "awaiting-writer-budget":
            usage = route.get("writer_call_budget")
            if (not route.get("feedback") or not isinstance(usage, dict)
                    or type(usage.get("limit")) is not int
                    or type(usage.get("reserved_calls")) is not int
                    or usage["reserved_calls"] < usage["limit"]):
                raise AdapterError(f"{client}: recorded Step 11 budget route is invalid")
            if (type(writer_limit) is not int or writer_limit <= usage["limit"]):
                raise AdapterError(
                    f"{client}: Step 11 writer budget is "
                    f"{usage['reserved_calls']}/{usage['limit']}; supply an explicitly approved "
                    "higher step11_writer_call_limit")
        elif writer_limit is not None:
            raise AdapterError(f"{client}: a higher writer limit is due only for exhausted Step 11 feedback")
        held_by = answers["step11_held_by"]
        step10_holder = answers["step10_held_by"]
        step10_reason = answers["step10_hold_reason"]
        if status != "awaiting-step10-hold" and (step10_holder not in (None, "")
                                                 or step10_reason not in (None, "")):
            raise AdapterError(f"{client}: Step 10 hold is due only at the measurement gate")
        if held_by not in (None, "") and (status != "awaiting-human"
                                          or not isinstance(held_by, str)
                                          or not held_by.strip()):
            raise AdapterError(f"{client}: a Step 11 hold is due only for the current saved page pair")
        if status == "awaiting-human":
            if held_by in (None, ""):
                raise AdapterError(f"{client}: current Step 11 pages need an explicit named hold")
            return _script_payload(
                sequence_id="workflow-resume-from-phase-live-confirmation",
                profile="resume", repository_key=repository_key,
                repository_root=repository, effectful=True, operation="resume",
                argv=[python, "-m", "up_harness.step11_review_hold", "--recorded",
                      "--client", client, "--held-by", held_by.strip(), "--confirmed-held"],
                environment={"PYTHONPATH": "src:."},
            )
        if status == "held":
            other = "vivacom" if client == "bteam" else "bteam"
            other_check = subprocess.run(
                [python, str(Path(repository, "scripts/prepare_step11_clean_copy.py")),
                 "--resolve-recorded-route", "--client", other],
                cwd=repository, env={**os.environ, "PYTHONPATH": "src:."},
                capture_output=True, text=True, timeout=45,
            )
            if other_check.returncode != 0 or json.loads(other_check.stdout).get("status") != "held":
                raise AdapterError(f"{client}: both Step 11 pairs must be held before ZIP closeout")
            return _script_payload(
                sequence_id="workflow-resume-from-phase-live-confirmation",
                profile="resume", repository_key=repository_key,
                repository_root=repository, effectful=True, operation="resume",
                argv=[python, "-m", "up_harness.step11_maria_package", "--close-recorded"],
                environment={"PYTHONPATH": "src:."},
            )
        if status == "awaiting-step10-hold":
            if (held_by not in (None, "") or not isinstance(step10_holder, str)
                    or not step10_holder.strip() or not isinstance(step10_reason, str)
                    or not step10_reason.strip()):
                raise AdapterError(f"{client}: Step 10 hold needs an explicit named holder and reason")
            return _script_payload(
                sequence_id="workflow-resume-from-phase-live-confirmation",
                profile="resume", repository_key=repository_key,
                repository_root=repository, effectful=True, operation="resume",
                argv=[python, "-m", "up_harness.step11_review_hold", "--recorded-step10",
                      "--client", client, "--held-by", step10_holder.strip(),
                      "--reason", step10_reason.strip(), "--confirmed-held"],
                environment={"PYTHONPATH": "src:."},
            )
        command = [python, str(Path(repository, "scripts/prepare_step11_clean_copy.py")),
                   "--resume-recorded", "--client", client]
        if held_by not in (None, ""):
            command += ["--held-by", held_by.strip()]
        if writer_limit is not None:
            command += ["--writer-call-limit", str(writer_limit)]
        return _script_payload(
            sequence_id="workflow-resume-from-phase-live-confirmation",
            profile="resume", repository_key=repository_key,
            repository_root=repository, effectful=True, operation="resume",
            argv=command, environment=_workflow_resume_live_environment(
                python, drive_staging_root=target / "drive-staging", agent_max_attempts="1",
            ),
        )
    if answers["source_run_id"] == STEP10_RECORDED_SOURCE:
        client = _required_text(answers, "client")
        phase = _required_text(answers, "first_unfinished_phase")
        base_fields = {"repository_key", "client", "source_run_id",
                       "first_unfinished_phase", "reopen_completed_phase"}
        other_inputs = [key for key in sorted(expected - base_fields)
                        if answers[key] not in (None, False)]
        if (client not in {"bteam", "vivacom"}
                or phase not in {"compose-measurement-framework", "measurement-gate"}
                or answers["reopen_completed_phase"] is not False or other_inputs):
            raise AdapterError("held-step9-source-for-step10-needs-first-compose-only")
        check = subprocess.run(
            [python, str(Path(repository, "scripts/prepare_step9_clean_copy.py")),
             "--resolve-step10-route", "--client", client],
            cwd=repository, env={**os.environ, "PYTHONPATH": "src:."},
            capture_output=True, text=True, timeout=45,
        )
        if check.returncode != 0:
            raise AdapterError(f"{client}: current held Step 9 source for Step 10 could not be selected")
        try:
            route = json.loads(check.stdout)
            run_id = route["run_id"]
            source_id = route["source_run_id"]
            selected_phase = route["phase"]
            selected_dir = Path(route["task_dir"])
            target = Path(route["copy_dir"])
        except (ValueError, KeyError, TypeError) as exc:
            raise AdapterError(f"{client}: recorded Step 10 route is invalid") from exc
        tasks_dir = Path(repository).resolve() / "Tasks"
        expected_target = tasks_dir / f"{client}-step9-clean-{route['step8_root_run_id'].removeprefix('up-run-')}"
        if (route.get("status") != "ready"
                or not re.fullmatch(r"up-run-[0-9a-f]{12}", source_id)
                or not re.fullmatch(r"up-run-[0-9a-f]{12}", run_id)
                or selected_phase not in {"compose-measurement-framework", "measurement-gate"}
                or target != expected_target or selected_dir != target):
            raise AdapterError(f"{client}: Step 10 route is not the current held Step 9 source")
        argv[argv.index("--resume-run") + 1] = run_id
        argv[argv.index("--from-phase") + 1] = selected_phase
        argv.extend(["--task-dir", str(target)])
        return _script_payload(
            sequence_id="workflow-resume-from-phase-live-confirmation",
            profile="resume", repository_key=repository_key,
            repository_root=repository, effectful=True, operation="resume",
            argv=argv, environment=_workflow_resume_live_environment(
                python, drive_staging_root=target / "drive-staging",
                agent_max_attempts="1",
            ),
        )
    if answers["source_run_id"] == STEP9_RECORDED_SOURCE:
        client = _required_text(answers, "client")
        phase = _required_text(answers, "first_unfinished_phase")
        base_fields = {"repository_key", "client", "source_run_id",
                       "first_unfinished_phase", "reopen_completed_phase",
                       "step9_held_by", "step9_altitude_check_path",
                       "step9_newsroom_model", "step9_earned_pipeline", "step9_decided_by"}
        other_inputs = [key for key in sorted(expected - base_fields)
                        if answers[key] not in (None, False)]
        if (client not in {"bteam", "vivacom"}
                or phase != "compose-execution-toolkit"
                or answers["reopen_completed_phase"] is not False
                or other_inputs):
            raise AdapterError("held Step 8 source for Step 9 requires only client and first compose")
        check = subprocess.run(
            [python, str(Path(repository, "scripts/prepare_step9_clean_copy.py")),
             "--resolve-recorded-route", "--client", client],
            cwd=repository, env={**os.environ, "PYTHONPATH": "src:."},
            capture_output=True, text=True, timeout=30,
        )
        if check.returncode != 0:
            raise AdapterError(f"{client}: current held Step 8 source for Step 9 could not be selected")
        try:
            route = json.loads(check.stdout)
            run_id = route["run_id"]
            source_id = route["source_run_id"]
            selected_dir = Path(route["task_dir"])
            target = Path(route["copy_dir"])
            selected_phase = route["phase"]
        except (ValueError, KeyError, TypeError) as exc:
            raise AdapterError(f"{client}: recorded Step 9 route is invalid") from exc
        tasks_dir = Path(repository).resolve() / "Tasks"
        expected_target = tasks_dir / f"{client}-step9-clean-{source_id.removeprefix('up-run-')}"
        if (not re.fullmatch(r"up-run-[0-9a-f]{12}", run_id)
                or not re.fullmatch(r"up-run-[0-9a-f]{12}", source_id)
                or selected_phase not in {"compose-execution-toolkit", "toolkit-ship-gate"}
                or target != expected_target or selected_dir.parent != tasks_dir
                or (run_id != source_id and selected_dir != target)):
            raise AdapterError(f"{client}: recorded Step 9 route has the wrong identity")
        held_by = answers["step9_held_by"]
        altitude_path = answers["step9_altitude_check_path"]
        decision_values = [answers[key] for key in (
            "step9_newsroom_model", "step9_earned_pipeline", "step9_decided_by")]
        deciding = any(value not in (None, "") for value in decision_values)
        if deciding and (not all(isinstance(value, str) and value.strip()
                                 for value in decision_values)
                         or held_by not in (None, "") or altitude_path not in (None, "")):
            raise AdapterError(f"{client}: both Step 9 decisions and their named decider are required together")
        if route["status"] == "awaiting-human":
            if (not isinstance(held_by, str) or not held_by.strip()
                    or altitude_path not in (None, "") or deciding):
                raise AdapterError(f"{client}: the Step 9 toolkit needs an explicit named hold")
            return _script_payload(
                sequence_id="workflow-resume-from-phase-live-confirmation",
                profile="resume", repository_key=repository_key,
                repository_root=repository, effectful=True, operation="resume",
                argv=[python, "-m", "up_harness.step9_review_hold", "--recorded",
                      "--client", client, "--held-by", held_by.strip(), "--confirmed-held"],
                environment={"PYTHONPATH": "src:."},
            )
        if route["status"] == "held":
            if held_by not in (None, "") or altitude_path not in (None, "") or deciding:
                raise AdapterError(f"{client}: Step 9 is already held; no new input is needed")
            other = "vivacom" if client == "bteam" else "bteam"
            other_check = subprocess.run(
                [python, str(Path(repository, "scripts/prepare_step9_clean_copy.py")),
                 "--resolve-recorded-route", "--client", other],
                cwd=repository, env={**os.environ, "PYTHONPATH": "src:."},
                capture_output=True, text=True, timeout=30,
            )
            if other_check.returncode != 0 or json.loads(other_check.stdout).get("status") != "held":
                raise AdapterError(f"{client}: both Step 9 toolkits must be held before ZIP closeout")
            return _script_payload(
                sequence_id="workflow-resume-from-phase-live-confirmation",
                profile="resume", repository_key=repository_key,
                repository_root=repository, effectful=True, operation="resume",
                argv=[python, "-m", "up_harness.step9_maria_package", "--close-recorded"],
                environment={"PYTHONPATH": "src:."},
            )
        if route["status"] != "ready" or held_by not in (None, ""):
            raise AdapterError(f"{client}: Step 9 is {route['status']}; a writer resume cannot record a hold")
        recorded = False
        if not deciding and altitude_path in (None, ""):
            standing_check = subprocess.run(
                [python, str(Path(repository, "scripts/prepare_step9_clean_copy.py")),
                 "--admit-decision-reopen", "--client", client],
                cwd=repository, env={**os.environ, "PYTHONPATH": "src:."},
                capture_output=True, text=True, timeout=30,
            )
            if standing_check.returncode == 0:
                try:
                    standing_proof = json.loads(standing_check.stdout)
                    recorded = set(standing_proof.get("recorded_events") or {}) == {
                        "newsroom_model", "earned_led_resourcing"}
                except (ValueError, TypeError):
                    raise AdapterError(f"{client}: Step 9 recorded decision proof is unreadable")
        if deciding or recorded:
            proof = subprocess.run(
                [python, str(Path(repository, "scripts/prepare_step9_clean_copy.py")),
                 "--admit-decision-reopen", "--client", client],
                cwd=repository, env={**os.environ, "PYTHONPATH": "src:."},
                capture_output=True, text=True, timeout=30,
            )
            if proof.returncode != 0:
                raise AdapterError(f"{client}: Step 9 saved stop is not eligible for operating decisions")
            try:
                decision_mode = json.loads(proof.stdout)["mode"]
            except (ValueError, KeyError, TypeError) as exc:
                raise AdapterError(f"{client}: Step 9 decision admission returned invalid proof") from exc
            if decision_mode not in {"resume", "reopen"} or (
                    decision_mode == "resume" and selected_phase != "compose-execution-toolkit") or (
                    decision_mode == "reopen" and selected_phase != "toolkit-ship-gate"):
                raise AdapterError(f"{client}: Step 9 decision proof differs from its saved phase")
            selected_phase = "compose-execution-toolkit"
            if decision_mode == "reopen":
                argv.append("--rerun-completed")
            if recorded:
                argv.append("--step9-use-recorded-decisions")
            else:
                argv.extend(["--step9-newsroom-model", decision_values[0].strip(),
                             "--step9-earned-pipeline", decision_values[1].strip(),
                             "--step9-decided-by", decision_values[2].strip()])
        if altitude_path not in (None, ""):
            supplied = Path(altitude_path)
            if not supplied.is_absolute():
                supplied = Path(repository, supplied)
            expected_check = target / "record/toolkit-altitude-check.json"
            if selected_phase != "toolkit-ship-gate" or supplied.resolve() != expected_check or not supplied.is_file():
                raise AdapterError(f"{client}: Step 9 holder check must belong to the current toolkit gate")
            argv.extend(["--altitude-check-file", str(supplied)])
        argv[argv.index("--resume-run") + 1] = run_id
        argv[argv.index("--from-phase") + 1] = selected_phase
        argv.extend(["--task-dir", str(selected_dir)])
        step9_handoff_dir = target
    if step4_primary_path_answer is not None and step4_dir_answer is None:
        raise AdapterError("step4-primary-evidence-requires-clean-copy")
    if step4_dir_answer is not None:
        client = _required_text(answers, "client")
        supplied_step4 = Path(_required_text(answers, "step4_clean_task_dir"))
        if not supplied_step4.is_absolute():
            supplied_step4 = Path(repository, supplied_step4)
        step4_dir = supplied_step4.resolve()
        tasks_dir = Path(repository).resolve() / "Tasks"
        legacy_step4 = tasks_dir / f"{client}-step4-clean-20261005"
        current_step4 = (step4_dir.parent == tasks_dir and
                         re.fullmatch(rf"{re.escape(client)}-step4-clean-[0-9a-f]{{12}}",
                                      step4_dir.name) is not None)
        if step4_dir != legacy_step4 and not current_step4:
            raise AdapterError("step4-clean-copy-missing-or-mismatched")
        if (step2_dir is not None or step3_dir is not None or step9_supplied
                or clean_supplied or clean_writer_supplied
                or answers["step5_clean_task_dir"] is not None
                or answers["step12_task_dir"] is not None
                or any(answers[key] is not None for key in (
                    "client_answers_path", "corrected_topic_policies_path",
                    "debrief_feedback_path", "final_brief_feedback_path",
                    "step10_admission_path", "step10_altitude_check_path",
                    "step11_altitude_check_path", "step12_altitude_check_path"))):
            raise AdapterError("step4-clean-copy-exclusive-with-other-routes")
        phase = _required_text(answers, "first_unfinished_phase")
        step5_handoff = phase in STEP5_ALLOWED_PHASES
        if phase not in STEP4_ALLOWED_PHASES and not step5_handoff:
            raise AdapterError("step4-clean-copy-needs-first-unfinished-step4-phase")
        contract_refresh = (
            phase == "compose-research-insight-pack"
            and answers["reopen_completed_phase"] is True
            and step4_primary_path_answer is None
            and current_step4
        )
        if step4_primary_path_answer is None and not contract_refresh:
            if answers["reopen_completed_phase"] is not False:
                raise AdapterError("step4-clean-copy-needs-first-unfinished-step4-phase")
        elif step4_primary_path_answer is not None and (phase != "compose-research-insight-pack"
              or answers["reopen_completed_phase"] is not True
              or not current_step4):
            raise AdapterError("step4-primary-evidence-needs-current-compose-reopen")
        selected_id = _required_text(answers, "source_run_id")
        staging_only = (
            step4_dir.is_dir()
            and all(child.name == "drive-staging" and child.is_dir() and not child.is_symlink()
                    for child in step4_dir.iterdir())
        )
        unprepared_step4 = not step4_dir.is_dir() or staging_only
        if (step4_primary_path_answer is not None or contract_refresh) and unprepared_step4:
            raise AdapterError("step4-primary-evidence-needs-saved-research")
        if unprepared_step4:
            if (not current_step4 or phase != "compose-research-insight-pack"
                    or not re.fullmatch(r"up-run-[0-9a-f]{12}", selected_id)
                    or step4_dir.name != f"{client}-step4-clean-{selected_id.removeprefix('up-run-')}"):
                raise AdapterError("step4-clean-copy-missing-or-mismatched")
            # The ordinary driver verifies the current passed Step 3 source and
            # prepares the copy before any model work.
            argv.extend(["--task-dir", str(step4_dir)])
        else:
            if not (step4_dir / "state").is_dir():
                raise AdapterError("step4-clean-copy-missing-or-mismatched")
        manifest_path = step4_dir / "record" / "step4-clean-copy.json"
        if not unprepared_step4:
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                root_source_id = manifest["source_run_id"]
                root_state_path = step4_dir / "state" / f"{root_source_id}.json"
                root_state_bytes = root_state_path.read_bytes()
                root_state = json.loads(root_state_bytes)
            except (OSError, ValueError, KeyError, TypeError):
                raise AdapterError("step4-clean-copy-manifest-invalid") from None
            if (manifest.get("schema") != ("step4-clean-copy/v1" if step4_dir == legacy_step4
                                           else "step4-clean-copy/v2")
                    or manifest.get("client") != client
                    or manifest.get("first_step4_phase") != "compose-research-insight-pack"
                    or manifest.get("stop_after_phase") != "research-gate"
                    or manifest.get("clean_state_sha256") != hashlib.sha256(root_state_bytes).hexdigest()
                    or root_state.get("run_id") != root_source_id
                    or (current_step4 and step4_dir.name !=
                        f"{client}-step4-clean-{root_source_id.removeprefix('up-run-')}")
                    or root_state.get("workflow_name") != "cd-s-002-corporate-communications-strategy"
                    or (root_state.get("context") or {}).get("inputs", {}).get("client_name") !=
                        {"bteam": "The B Team", "vivacom": "Vivacom"}[client]
                    or (root_state.get("context") or {}).get("inputs", {}).get("client_code") !=
                        {"bteam": "BTM", "vivacom": "VIV"}[client]
                    or (root_state.get("context") or {}).get("inputs", {}).get("stop_after_phase") != "research-gate"
                    or (root_state.get("phases") or {}).get("final-brief-gate", {}).get("status") != "completed"):
                raise AdapterError("step4-clean-copy-manifest-mismatch")
            if current_step4:
                source_task_dir = manifest.get("source_task_dir")
                if not isinstance(source_task_dir, str) or not source_task_dir:
                    raise AdapterError("step4-clean-copy-manifest-mismatch")
                source_dir = (Path(repository).resolve() / source_task_dir).resolve()
                source_path = source_dir / "state" / f"{root_source_id}.json"
                step3_manifest_path = source_dir / "record" / "step3-clean-copy.json"
                try:
                    source_matches = (
                        source_dir.parent == tasks_dir
                        and re.fullmatch(rf"{re.escape(client)}-step3-clean-[0-9a-f]{{12}}",
                                         source_dir.name) is not None
                        and manifest.get("source_sha256") ==
                        hashlib.sha256(source_path.read_bytes()).hexdigest()
                        and manifest.get("step3_manifest_sha256") ==
                        hashlib.sha256(step3_manifest_path.read_bytes()).hexdigest()
                    )
                except OSError:
                    source_matches = False
                if not source_matches:
                    raise AdapterError("step4-clean-copy-manifest-mismatch")
        if phase == "compose-research-insight-pack":
            if step4_dir == legacy_step4:
                raise AdapterError("step4-clean-copy-old-source-cannot-start-new-compose")
            if step4_primary_path_answer is not None and selected_id == root_source_id:
                raise AdapterError("step4-primary-evidence-needs-saved-research")
            if not unprepared_step4 and selected_id != root_source_id:
                try:
                    selected = json.loads(
                        (step4_dir / "state" / f"{selected_id}.json").read_text(encoding="utf-8")
                    )
                except (OSError, ValueError, TypeError):
                    raise AdapterError("step4-clean-copy-compose-source-invalid") from None
                cursor = selected
                seen: set[str] = set()
                while cursor.get("run_id") != root_source_id:
                    cursor_id = cursor.get("run_id")
                    parent_id = cursor.get("parent_run_id")
                    if (not isinstance(cursor_id, str) or cursor_id in seen
                            or not isinstance(parent_id, str) or len(seen) >= 100):
                        raise AdapterError("step4-clean-copy-compose-lineage-mismatch")
                    seen.add(cursor_id)
                    try:
                        cursor = json.loads(
                            (step4_dir / "state" / f"{parent_id}.json").read_text(encoding="utf-8")
                        )
                    except (OSError, ValueError, TypeError):
                        raise AdapterError("step4-clean-copy-compose-lineage-mismatch") from None
                ledger = (
                    (((selected.get("context") or {}).get("up") or {})
                     .get("cd_s_002") or {}).get("step4_part_ledger")
                )
                used = ledger.get("writer_calls_used") if isinstance(ledger, dict) else None
                limit = ledger.get("writer_call_limit") if isinstance(ledger, dict) else None
                terminal_status = selected.get("status")
                if step4_primary_path_answer is not None or contract_refresh:
                    parts = ledger.get("parts") if isinstance(ledger, dict) else None
                    gate = (selected.get("phases") or {}).get("research-gate") or {}
                    saved_pack = (((selected.get("context") or {}).get("up") or {})
                                  .get("cd_s_002") or {}).get("research_pack")
                    source_tier = ((selected.get("context") or {}).get("inputs") or {}).get(
                        "engagement_tier")
                    source_version = (saved_pack or {}).get("step4_contract_version")
                    missing_primary_gate = (
                        source_version == 3
                        and "requires conducted primary_research" in str(gate.get("output") or "")
                    ) or (
                        source_version == 4
                        and ((gate.get("ledger") or {}).get("primary_research_status") == "pending")
                    )
                    if (selected.get("run_id") != selected_id
                            or terminal_status != "blocked"
                            or (selected.get("phases") or {}).get(
                                "compose-research-insight-pack", {}).get("status") != "completed"
                            or gate.get("status") != "blocked"
                            or not missing_primary_gate
                            or not isinstance(saved_pack, dict)
                            or saved_pack.get("depth") != source_tier
                            or (source_version == 4 and source_tier not in {
                                "sme", "standard", "enterprise", "regulated"})
                            or "primary_research" in saved_pack
                            or not isinstance(ledger, dict) or ledger.get("version") != 1
                            or not isinstance(parts, dict) or set(parts) != STEP4_NATIVE_PARTS
                            or any(not isinstance(row, dict) or row.get("status") != "passed"
                                   for row in parts.values())
                            or (ledger.get("document_check") or {}).get("status") != "passed"
                            or type(used) is not int or type(limit) is not int
                            or used < 0 or limit <= 0 or used > limit):
                        raise AdapterError("step4-primary-evidence-source-not-reviewable")
                    if contract_refresh:
                        if source_version != 3 or source_tier not in {
                                "standard-enterprise", "enterprise", "regulated"}:
                            raise AdapterError("step4-contract-refresh-source-not-legacy")
                    if source_tier == "standard-enterprise":
                        standing_tier = (Path(repository).resolve() / "Tasks" /
                                         "bteam-corporate-demo" / "engagement-tier.json")
                        try:
                            ruling = json.loads(standing_tier.read_text(encoding="utf-8"))
                        except (OSError, ValueError, TypeError):
                            raise AdapterError("step4-standard-tier-ruling-missing") from None
                        if client != "bteam" or ruling.get("engagement_tier") != "standard":
                            raise AdapterError("step4-standard-tier-ruling-mismatch")
                        argv.extend(["--engagement-tier", "standard"])
                elif (selected.get("run_id") != selected_id
                      or terminal_status not in {"failed", "blocked"}
                      or (selected.get("phases") or {}).get(
                          "compose-research-insight-pack", {}).get("status") != terminal_status
                      or not isinstance(ledger, dict) or ledger.get("version") != 1
                      or not isinstance(ledger.get("parts"), dict) or not ledger["parts"]
                      or type(used) is not int or type(limit) is not int
                      or used < 0 or limit <= 0 or used > limit):
                    raise AdapterError("step4-clean-copy-compose-source-not-resumable")
            if answers["gate_approvals_path"] is not None:
                raise AdapterError("step4-clean-copy-compose-has-no-gate-input")
        elif step5_handoff:
            if (phase != "compose-insight-cards"
                    or answers["reopen_completed_phase"] is not False
                    or not re.fullmatch(r"up-run-[0-9a-f]{12}", selected_id)):
                raise AdapterError("step5-clean-copy-needs-passed-step4-selection")
            selected_path = (step4_dir / "state" / f"{selected_id}.json").resolve()
            if selected_path.parent != (step4_dir / "state").resolve():
                raise AdapterError("step5-clean-copy-source-outside-step4-copy")
            try:
                selected = json.loads(selected_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                raise AdapterError("step5-clean-copy-source-missing") from None
            expected_name = {"bteam": "The B Team", "vivacom": "Vivacom"}[client]
            expected_code = {"bteam": "BTM", "vivacom": "VIV"}[client]
            selected_inputs = (selected.get("context") or {}).get("inputs") or {}
            selected_gate = (selected.get("phases") or {}).get("research-gate") or {}
            if (selected.get("run_id") != selected_id
                    or selected.get("workflow_name") != "cd-s-002-corporate-communications-strategy"
                    or selected_inputs.get("client_name") != expected_name
                    or selected_inputs.get("client_code") != expected_code
                    or selected_gate.get("status") != "completed"
                    or (selected_gate.get("ledger") or {}).get("status") != "passed"):
                raise AdapterError("step5-clean-copy-source-not-passed-for-client")
            cursor = selected
            seen: set[str] = set()
            while cursor.get("run_id") != root_source_id:
                cursor_id = cursor.get("run_id")
                parent_id = cursor.get("parent_run_id")
                if (not isinstance(cursor_id, str) or cursor_id in seen
                        or not isinstance(parent_id, str) or len(seen) >= 100):
                    raise AdapterError("step5-clean-copy-source-lineage-mismatch")
                seen.add(cursor_id)
                try:
                    cursor = json.loads(
                        (step4_dir / "state" / f"{parent_id}.json").read_text(encoding="utf-8")
                    )
                except (OSError, ValueError, TypeError):
                    raise AdapterError("step5-clean-copy-source-lineage-mismatch") from None
                ancestor_inputs = (cursor.get("context") or {}).get("inputs") or {}
                if (cursor.get("run_id") != parent_id
                        or ancestor_inputs.get("client_name") != expected_name
                        or ancestor_inputs.get("client_code") != expected_code):
                    raise AdapterError("step5-clean-copy-source-lineage-mismatch")
            step5_handoff_dir = (Path(repository).resolve() / "Tasks" /
                                 f"{client}-step5-clean-{selected_id.removeprefix('up-run-')}")
        else:
            try:
                selected = json.loads(
                    (step4_dir / "state" / f"{selected_id}.json").read_text(encoding="utf-8")
                )
            except (OSError, ValueError, TypeError):
                raise AdapterError("step4-clean-copy-gate-source-missing") from None
            cursor = selected
            seen: set[str] = set()
            while cursor.get("run_id") != root_source_id:
                cursor_id = cursor.get("run_id")
                parent_id = cursor.get("parent_run_id")
                if (not isinstance(cursor_id, str) or cursor_id in seen
                        or not isinstance(parent_id, str) or len(seen) >= 100):
                    raise AdapterError("step4-clean-copy-gate-lineage-mismatch")
                seen.add(cursor_id)
                try:
                    cursor = json.loads(
                        (step4_dir / "state" / f"{parent_id}.json").read_text(encoding="utf-8")
                    )
                except (OSError, ValueError, TypeError):
                    raise AdapterError("step4-clean-copy-gate-lineage-mismatch") from None
            gate_status = (selected.get("phases") or {}).get("research-gate", {}).get("status")
            step4_ledger = (
                (((selected.get("context") or {}).get("up") or {})
                 .get("cd_s_002") or {}).get("step4_part_ledger")
            )
            resumable_failed_gate = (
                selected.get("status") == "failed"
                and gate_status == "failed"
                and isinstance(step4_ledger, dict)
                and step4_ledger.get("version") == 1
                and isinstance(step4_ledger.get("parts"), dict)
                and bool(step4_ledger["parts"])
            )
            if (selected.get("run_id") != selected_id
                    or (gate_status not in ("blocked", "running")
                        and not resumable_failed_gate)):
                raise AdapterError("step4-clean-copy-gate-source-not-blocked-at-gate")
            approval = answers["gate_approvals_path"]
            if approval is not None:
                approval_path = Path(approval)
                if not approval_path.is_absolute():
                    approval_path = Path(repository, approval_path)
                if approval_path.resolve().parent != step4_dir / "record" or not approval_path.is_file():
                    raise AdapterError("step4-clean-copy-gate-input-must-be-in-record")
        if not unprepared_step4:
            argv.extend(["--task-dir", str(step4_dir)])
        if step4_primary_path_answer is not None:
            primary_path = Path(_required_text(answers, "step4_primary_research_path"))
            if not primary_path.is_absolute():
                primary_path = Path(repository, primary_path)
            primary_path = primary_path.resolve()
            if (primary_path != step4_dir / "record" / f"primary-research-{selected_id}.json"
                    or not primary_path.is_file()):
                raise AdapterError("step4-primary-evidence-file-must-bind-to-source")
            argv.extend(["--step4-primary-research-file", str(primary_path)])
    step5_dir_answer = answers["step5_clean_task_dir"]
    step5_dir: Path | None = None
    if step5_dir_answer is not None:
        client = _required_text(answers, "client")
        tasks_dir = Path(repository).resolve() / "Tasks"
        legacy_step5 = tasks_dir / f"{client}-step5-clean-20261005"
        supplied_step5 = Path(_required_text(answers, "step5_clean_task_dir"))
        if not supplied_step5.is_absolute():
            supplied_step5 = Path(repository, supplied_step5)
        step5_dir = supplied_step5.resolve()
        current_step5_match = re.fullmatch(
            rf"{re.escape(client)}-step5-clean-([0-9a-f]{{12}})", step5_dir.name,
        ) if step5_dir.parent == tasks_dir else None
        current_step5 = current_step5_match is not None
        if ((step5_dir != legacy_step5 and not current_step5) or not step5_dir.is_dir()):
            raise AdapterError("step5-clean-copy-missing-or-mismatched")
        if (step2_dir is not None or step3_dir is not None or step4_dir is not None
                or step9_supplied or clean_supplied or clean_writer_supplied
                or answers["step12_task_dir"] is not None
                or any(answers[key] is not None for key in (
                    "client_answers_path", "corrected_topic_policies_path",
                    "debrief_feedback_path", "final_brief_feedback_path",
                    "gate_approvals_path", "step10_admission_path",
                    "step10_altitude_check_path", "step11_altitude_check_path",
                    "step12_altitude_check_path"))):
            raise AdapterError("step5-clean-copy-exclusive-with-other-routes")
        phase = _required_text(answers, "first_unfinished_phase")
        reopen_step5 = answers["reopen_completed_phase"] is True
        if phase not in STEP5_ALLOWED_PHASES:
            raise AdapterError("step5-clean-copy-needs-first-unfinished-step5-phase")
        manifest_path = step5_dir / "record" / "step5-clean-copy.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            root_source_id = manifest["source_run_id"]
            root_state_path = step5_dir / "state" / f"{root_source_id}.json"
            root_state_bytes = root_state_path.read_bytes()
            root_state = json.loads(root_state_bytes)
        except (OSError, ValueError, KeyError, TypeError):
            raise AdapterError("step5-clean-copy-manifest-invalid") from None
        root_inputs = (root_state.get("context") or {}).get("inputs") or {}
        root_up = (((root_state.get("context") or {}).get("up") or {})
                   .get("cd_s_002") or {})
        source_hold = root_up.get("step4_review_hold")
        hold_sha = None
        if source_hold is not None:
            hold_sha = hashlib.sha256(
                (json.dumps(source_hold, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":")) + "\n").encode()
            ).hexdigest()
        research_gate = (root_state.get("phases") or {}).get("research-gate") or {}
        admission = manifest.get("source_admission")
        gate_status = (research_gate.get("ledger") or {}).get("status")
        recorded_accepted_step5 = current_step5 and manifest.get("schema") in {
            "step5-clean-copy/v3", "step5-clean-copy/v4"}
        valid_schema = ((current_step5 and manifest.get("schema") in {
                            "step5-clean-copy/v2", "step5-clean-copy/v3",
                            "step5-clean-copy/v4"})
                        or (not current_step5 and manifest.get("schema") == "step5-clean-copy/v1"))
        if (not valid_schema
                or manifest.get("client") != client
                or manifest.get("first_phase") != "compose-insight-cards"
                or manifest.get("stop_after_phase") != "insight-gate"
                or manifest.get("writer_call_limit") != 60
                or manifest.get("clean_state_sha256") != hashlib.sha256(root_state_bytes).hexdigest()
                or root_state.get("run_id") != root_source_id
                or root_inputs.get("stop_after_phase") != "insight-gate"
                or root_inputs.get("step5_writer_call_limit") != 60
                or research_gate.get("status") != "completed"
                or (not current_step5 and admission not in {"passed", "held"})
                or (not current_step5 and gate_status != admission)
                or (not current_step5 and admission == "held" and (
                    not isinstance(source_hold, dict)
                    or source_hold.get("verdict") != "held"
                    or manifest.get("source_review_hold_sha256") != hold_sha
                ))
                or (not current_step5 and admission == "passed"
                    and manifest.get("source_review_hold_sha256") is not None)):
            raise AdapterError("step5-clean-copy-manifest-mismatch")
        if recorded_accepted_step5:
            # The harness owns accepted-source admission for both historical
            # and current clean Step 4 sources. Do not mirror it here.
            repo_root = Path(repository).resolve()
            verifier = repo_root / "scripts/prepare_step5_clean_copy.py"
            interpreter = repo_root / ".venv/bin/python"
            try:
                checked = subprocess.run(
                    [str(interpreter), str(verifier), "--client", client,
                     "--verify-copy", str(step5_dir)],
                    cwd=repo_root, capture_output=True, text=True, timeout=30,
                )
            except (OSError, subprocess.TimeoutExpired):
                raise AdapterError("step5-clean-copy-accepted-admission-unavailable") from None
            if checked.returncode != 0:
                raise AdapterError("step5-clean-copy-accepted-admission-refused")
        elif current_step5:
            repo_root = Path(repository).resolve()
            source_relative = Path(str(manifest.get("source_state_path") or ""))
            if (source_relative.is_absolute() or ".." in source_relative.parts
                    or len(source_relative.parts) != 4
                    or source_relative.parts[0] != "Tasks"
                    or not re.fullmatch(rf"{re.escape(client)}-step4-clean-[0-9a-f]{{12}}",
                                        source_relative.parts[1])
                    or source_relative.parts[2] != "state"
                    or source_relative.stem != root_source_id
                    or source_relative.suffix != ".json"):
                raise AdapterError("step5-clean-copy-manifest-mismatch")
            source_candidate = repo_root / source_relative
            source_path = source_candidate.resolve()
            if source_path != source_candidate:
                raise AdapterError("step5-clean-copy-manifest-mismatch")
            source_step4_dir = source_path.parents[1]
            try:
                source_bytes = source_path.read_bytes()
                source_state = json.loads(source_bytes)
                step4_manifest_bytes = (source_step4_dir / "record" / "step4-clean-copy.json").read_bytes()
                step4_manifest = json.loads(step4_manifest_bytes)
                step4_root_id = step4_manifest["source_run_id"]
                step4_root_bytes = (source_step4_dir / "state" / f"{step4_root_id}.json").read_bytes()
                step4_root = json.loads(step4_root_bytes)
                step3_relative = Path(step4_manifest["source_task_dir"])
                if (step3_relative.is_absolute() or ".." in step3_relative.parts
                        or len(step3_relative.parts) != 2 or step3_relative.parts[0] != "Tasks"
                        or not re.fullmatch(rf"{re.escape(client)}-step3-clean-[0-9a-f]{{12}}",
                                            step3_relative.parts[1])):
                    raise ValueError("unsafe Step 3 source")
                source_step3_dir = (repo_root / step3_relative).resolve()
                step3_manifest_bytes = (source_step3_dir / "record" / "step3-clean-copy.json").read_bytes()
                step3_manifest = json.loads(step3_manifest_bytes)
                step3_root_id = step3_manifest["source_run_id"]
                step3_source_bytes = (source_step3_dir / "state" / f"{step4_root_id}.json").read_bytes()
                step3_source = json.loads(step3_source_bytes)
            except (OSError, ValueError, TypeError, KeyError):
                raise AdapterError("step5-clean-copy-source-missing") from None
            expected_name = {"bteam": "The B Team", "vivacom": "Vivacom"}[client]
            expected_code = {"bteam": "BTM", "vivacom": "VIV"}[client]
            source_inputs = (source_state.get("context") or {}).get("inputs") or {}
            source_gate = (source_state.get("phases") or {}).get("research-gate") or {}
            if (step5_dir.name != f"{client}-step5-clean-{root_source_id.removeprefix('up-run-')}"
                    or manifest.get("source_task_dir") != source_relative.parent.parent.as_posix()
                    or manifest.get("step4_manifest_sha256") != hashlib.sha256(step4_manifest_bytes).hexdigest()
                    or manifest.get("source_state_sha256") != hashlib.sha256(source_bytes).hexdigest()
                    or manifest.get("source_admission") != "passed"
                    or manifest.get("source_review_hold_sha256") is not None
                    or step4_manifest.get("schema") != "step4-clean-copy/v2"
                    or step4_manifest.get("client") != client
                    or source_step4_dir.name != f"{client}-step4-clean-{step4_root_id.removeprefix('up-run-')}"
                    or step4_manifest.get("clean_state_sha256") != hashlib.sha256(step4_root_bytes).hexdigest()
                    or step4_root.get("run_id") != step4_root_id
                    or step4_manifest.get("first_step4_phase") != "compose-research-insight-pack"
                    or step4_manifest.get("stop_after_phase") != "research-gate"
                    or step4_manifest.get("source_sha256") != hashlib.sha256(step3_source_bytes).hexdigest()
                    or step4_manifest.get("step3_manifest_sha256") != hashlib.sha256(step3_manifest_bytes).hexdigest()
                    or step3_manifest.get("client") != client
                    or step3_manifest.get("source_run_id") != step3_root_id
                    or source_step3_dir.name != f"{client}-step3-clean-{step3_root_id.removeprefix('up-run-')}"
                    or step3_source.get("run_id") != step4_root_id
                    or source_state.get("run_id") != root_source_id
                    or source_state.get("workflow_name") != "cd-s-002-corporate-communications-strategy"
                    or source_inputs.get("client_name") != expected_name
                    or source_inputs.get("client_code") != expected_code
                    or source_gate.get("status") != "completed"
                    or (source_gate.get("ledger") or {}).get("status") != "passed"):
                raise AdapterError("step5-clean-copy-manifest-mismatch")
            cursor = source_state
            seen_source: set[str] = set()
            while cursor.get("run_id") != step4_root_id:
                cursor_id, parent_id = cursor.get("run_id"), cursor.get("parent_run_id")
                if (not isinstance(cursor_id, str) or cursor_id in seen_source
                        or not isinstance(parent_id, str) or len(seen_source) >= 100):
                    raise AdapterError("step5-clean-copy-source-lineage-mismatch")
                seen_source.add(cursor_id)
                try:
                    cursor = json.loads((source_step4_dir / "state" / f"{parent_id}.json").read_text(encoding="utf-8"))
                except (OSError, ValueError, TypeError):
                    raise AdapterError("step5-clean-copy-source-lineage-mismatch") from None
                ancestor_inputs = (cursor.get("context") or {}).get("inputs") or {}
                if (cursor.get("run_id") != parent_id
                        or ancestor_inputs.get("client_name") != expected_name
                        or ancestor_inputs.get("client_code") != expected_code):
                    raise AdapterError("step5-clean-copy-source-lineage-mismatch")
        selected_id = _required_text(answers, "source_run_id")
        try:
            selected_path = (step5_dir / "state" / f"{selected_id}.json").resolve(strict=True)
            selected_path.relative_to((step5_dir / "state").resolve(strict=True))
            if selected_path.parent != (step5_dir / "state").resolve(strict=True):
                raise ValueError("state is outside copy")
            selected = json.loads(selected_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            if phase == "compose-insight-cards" and selected_id == root_source_id:
                selected = root_state
            else:
                raise AdapterError("step5-clean-copy-resume-source-missing") from None
        cursor = selected
        seen: set[str] = set()
        while cursor.get("run_id") != root_source_id:
            cursor_id = cursor.get("run_id")
            parent_id = cursor.get("parent_run_id")
            if (not isinstance(cursor_id, str) or cursor_id in seen
                    or not isinstance(parent_id, str) or len(seen) >= 100):
                raise AdapterError("step5-clean-copy-lineage-mismatch")
            seen.add(cursor_id)
            try:
                cursor_path = (step5_dir / "state" / f"{parent_id}.json").resolve(strict=True)
                cursor_path.relative_to((step5_dir / "state").resolve(strict=True))
                if cursor_path.parent != (step5_dir / "state").resolve(strict=True):
                    raise ValueError("parent is outside copy")
                cursor = json.loads(cursor_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                raise AdapterError("step5-clean-copy-lineage-mismatch") from None
            if cursor.get("run_id") != parent_id:
                raise AdapterError("step5-clean-copy-lineage-mismatch")
            if current_step5:
                ancestor_inputs = (cursor.get("context") or {}).get("inputs") or {}
                if (ancestor_inputs.get("client_name") != {"bteam": "The B Team", "vivacom": "Vivacom"}[client]
                        or ancestor_inputs.get("client_code") != {"bteam": "BTM", "vivacom": "VIV"}[client]):
                    raise AdapterError("step5-clean-copy-lineage-mismatch")
        if selected.get("run_id") != selected_id:
            raise AdapterError("step5-clean-copy-lineage-mismatch")
        selected_inputs = (selected.get("context") or {}).get("inputs") or {}
        if (current_step5 and (
                selected_inputs.get("client_name") != {"bteam": "The B Team", "vivacom": "Vivacom"}[client]
                or selected_inputs.get("client_code") != {"bteam": "BTM", "vivacom": "VIV"}[client])):
            raise AdapterError("step5-clean-copy-lineage-mismatch")
        step5_up = (((selected.get("context") or {}).get("up") or {})
                    .get("cd_s_002") or {})
        part_ledger = step5_up.get("step5_part_ledger") or {}
        board_ledger = step5_up.get("step5_mini_board_ledger") or {}
        part_calls = part_ledger.get("writer_calls_used", 0)
        board_calls = board_ledger.get("writer_calls_used", 0)
        if current_step5 and (type(part_calls) is not int or type(board_calls) is not int
                or part_calls < 0 or board_calls < 0 or part_calls + board_calls > 60):
            raise AdapterError("step5-clean-copy-call-budget-invalid")
        selected_phase = (selected.get("phases") or {}).get(phase) or {}
        if selected_id == root_source_id:
            if phase != "compose-insight-cards" or reopen_step5:
                raise AdapterError("step5-clean-copy-compose-needs-manifest-source")
            if any(path.stem != root_source_id for path in (step5_dir / "state").glob("up-run-*.json")):
                raise AdapterError("step5-clean-copy-root-has-saved-descendants")
        else:
            allowed_statuses = {"completed"} if reopen_step5 else {"blocked", "failed", "running"}
            if selected_phase.get("status") not in allowed_statuses:
                raise AdapterError("step5-clean-copy-source-not-resumable")
        argv.extend(["--task-dir", str(step5_dir)])
    STEP6_ALLOWED_PHASES = {"compose-strategy-one-pager", "strategy-approach-gate"}
    step6_dir_answer = answers["step6_clean_task_dir"]
    step6_dir: Path | None = None
    if step6_dir_answer is not None:
        client = _required_text(answers, "client")
        expected_step6 = Path(repository).resolve() / "Tasks" / f"{client}-step6-clean-20261006"
        supplied_step6 = Path(_required_text(answers, "step6_clean_task_dir"))
        if not supplied_step6.is_absolute():
            supplied_step6 = Path(repository, supplied_step6)
        step6_dir = supplied_step6.resolve()
        if step6_dir != expected_step6 or not step6_dir.is_dir():
            raise AdapterError("step6-clean-copy-missing-or-mismatched")
        if (step2_dir is not None or step3_dir is not None or step4_dir is not None
                or step9_supplied or clean_supplied or clean_writer_supplied
                or answers["step12_task_dir"] is not None
                or any(answers[key] is not None for key in (
                    "client_answers_path", "corrected_topic_policies_path",
                    "debrief_feedback_path", "final_brief_feedback_path",
                    "gate_approvals_path", "step10_admission_path",
                    "step10_altitude_check_path", "step11_altitude_check_path",
                    "step12_altitude_check_path"))):
            raise AdapterError("step6-clean-copy-exclusive-with-other-routes")
        phase = _required_text(answers, "first_unfinished_phase")
        reopen_step6 = answers["reopen_completed_phase"] is True
        if phase not in STEP6_ALLOWED_PHASES:
            raise AdapterError("step6-clean-copy-needs-first-unfinished-step6-phase")
        manifest_path = step6_dir / "record" / "step6-clean-copy.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            root_source_id = manifest["source_run_id"]
            root_state_path = step6_dir / "state" / f"{root_source_id}.json"
            root_state_bytes = root_state_path.read_bytes()
            root_state = json.loads(root_state_bytes)
        except (OSError, ValueError, KeyError, TypeError):
            raise AdapterError("step6-clean-copy-manifest-invalid") from None
        root_inputs = (root_state.get("context") or {}).get("inputs") or {}
        root_up = (((root_state.get("context") or {}).get("up") or {})
                   .get("cd_s_002") or {})
        source_hold = root_up.get("step5_review_hold")
        hold_sha = None
        if source_hold is not None:
            hold_sha = hashlib.sha256(
                (json.dumps(source_hold, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":")) + "\n").encode()
            ).hexdigest()
        research_gate = (root_state.get("phases") or {}).get("insight-gate") or {}
        admission = manifest.get("source_admission")
        gate_status = (research_gate.get("ledger") or {}).get("status")
        if (manifest.get("schema") != "step6-clean-copy/v1"
                or manifest.get("client") != client
                or manifest.get("first_phase") != "compose-strategy-one-pager"
                or manifest.get("stop_after_phase") != "strategy-approach-gate"
                or manifest.get("writer_call_limit") != 60
                or manifest.get("clean_state_sha256") != hashlib.sha256(root_state_bytes).hexdigest()
                or root_state.get("run_id") != root_source_id
                or root_inputs.get("stop_after_phase") != "strategy-approach-gate"
                or root_inputs.get("step6_writer_call_limit") != 60
                or research_gate.get("status") != "completed"
                or admission not in {"passed", "held"}
                or gate_status != admission
                or (admission == "held" and (
                    not isinstance(source_hold, dict)
                    or source_hold.get("verdict") != "held"
                    or manifest.get("source_review_hold_sha256") != hold_sha
                ))
                or (admission == "passed"
                    and manifest.get("source_review_hold_sha256") is not None)):
            raise AdapterError("step6-clean-copy-manifest-mismatch")
        selected_id = _required_text(answers, "source_run_id")
        if phase == "compose-strategy-one-pager" and selected_id == root_source_id:
            if reopen_step6:
                raise AdapterError("step6-clean-copy-compose-needs-manifest-source")
        else:
            try:
                selected = json.loads(
                    (step6_dir / "state" / f"{selected_id}.json").read_text(encoding="utf-8")
                )
            except (OSError, ValueError, TypeError):
                raise AdapterError("step6-clean-copy-resume-source-missing") from None
            cursor = selected
            seen: set[str] = set()
            while cursor.get("run_id") != root_source_id:
                cursor_id = cursor.get("run_id")
                parent_id = cursor.get("parent_run_id")
                if (not isinstance(cursor_id, str) or cursor_id in seen
                        or not isinstance(parent_id, str) or len(seen) >= 100):
                    raise AdapterError("step6-clean-copy-lineage-mismatch")
                seen.add(cursor_id)
                try:
                    cursor = json.loads(
                        (step6_dir / "state" / f"{parent_id}.json").read_text(encoding="utf-8")
                    )
                except (OSError, ValueError, TypeError):
                    raise AdapterError("step6-clean-copy-lineage-mismatch") from None
            selected_phase = (selected.get("phases") or {}).get(phase) or {}
            allowed_statuses = {"completed"} if reopen_step6 else {"blocked", "failed", "running"}
            if (selected.get("run_id") != selected_id
                    or selected_phase.get("status") not in allowed_statuses):
                raise AdapterError("step6-clean-copy-source-not-resumable")
        if step5_dir is not None:
            raise AdapterError("step6-clean-copy-exclusive-with-step5-route")
        feedback = answers["step6_feedback_path"]
        if feedback is not None:
            feedback_path = Path(feedback)
            if not feedback_path.is_absolute():
                feedback_path = Path(repository, feedback_path)
            if (phase != "compose-strategy-one-pager" or feedback_path.resolve().parent != step6_dir / "record"
                    or not feedback_path.is_file()):
                raise AdapterError("step6-feedback-must-target-compose-and-record")
            argv.extend(["--step6-feedback-file", str(feedback_path.resolve())])
        argv.extend(["--task-dir", str(step6_dir)])
    elif answers["step6_feedback_path"] is not None:
        raise AdapterError("step6-feedback-requires-its-clean-copy")

    step7_dir_answer = answers["step7_clean_task_dir"]
    step7_dir: Path | None = None
    if step7_dir_answer is not None:
        client = _required_text(answers, "client")
        expected_step7 = Path(repository).resolve() / "Tasks" / f"{client}-step7-clean-20261006"
        supplied_step7 = Path(_required_text(answers, "step7_clean_task_dir"))
        if not supplied_step7.is_absolute():
            supplied_step7 = Path(repository, supplied_step7)
        step7_dir = supplied_step7.resolve()
        current_step7 = (step7_dir.parent == Path(repository).resolve() / "Tasks"
                         and re.fullmatch(rf"{re.escape(client)}-step7-clean-[0-9a-f]{{12}}",
                                          step7_dir.name) is not None)
        if (step7_dir != expected_step7 and not current_step7) or not step7_dir.is_dir():
            raise AdapterError("step7-clean-copy-missing-or-mismatched")
        if current_step7:
            check = subprocess.run(
                [python, str(Path(repository, "scripts/prepare_step7_clean_copy.py")),
                 "--resolve-recorded-route", "--client", client],
                cwd=repository, env={**os.environ, "PYTHONPATH": "src:."},
                capture_output=True, text=True, timeout=30,
            )
            if check.returncode != 0:
                raise AdapterError("step7-current-copy-source-invalid")
            current_route = json.loads(check.stdout)
            if Path(current_route.get("copy_dir", "")) != step7_dir:
                raise AdapterError("step7-current-copy-source-mismatch")
        if (step2_dir is not None or step3_dir is not None or step4_dir is not None
                or step5_dir is not None or step6_dir is not None or step9_supplied
                or clean_supplied or clean_writer_supplied or answers["step12_task_dir"] is not None
                or any(answers[key] is not None for key in (
                    "client_answers_path", "corrected_topic_policies_path",
                    "debrief_feedback_path", "final_brief_feedback_path", "gate_approvals_path",
                    "step10_admission_path", "step10_altitude_check_path",
                    "step11_altitude_check_path", "step12_altitude_check_path"))):
            raise AdapterError("step7-clean-copy-exclusive-with-other-routes")
        phase = _required_text(answers, "first_unfinished_phase")
        if phase not in {"compose-big-idea", "big-idea-gate",
                         "compose-message-architecture", "narrative-gate"}:
            raise AdapterError("step7-clean-copy-phase-outside-step7")
        try:
            manifest = json.loads((step7_dir / "record/step7-clean-copy.json").read_text())
            root_source_id = manifest["source_run_id"]
            root_state_path = step7_dir / "state" / f"{root_source_id}.json"
            root_state_bytes = root_state_path.read_bytes()
            root_state = json.loads(root_state_bytes)
        except (OSError, ValueError, KeyError, TypeError):
            raise AdapterError("step7-clean-copy-manifest-invalid") from None
        root_inputs = (root_state.get("context") or {}).get("inputs") or {}
        root_up = (((root_state.get("context") or {}).get("up") or {}).get("cd_s_002") or {})
        admission = root_inputs.get("step7_source_admission") or {}
        source_hold = root_up.get("step6_review_hold") or {}
        hold_sha = hashlib.sha256((json.dumps(source_hold, ensure_ascii=False,
            sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()
        gate = (root_state.get("phases") or {}).get("strategy-approach-gate") or {}
        if (manifest.get("schema") !=
                ("step7-clean-copy/v2" if current_step7 else "step7-clean-copy/v1")
                or manifest.get("client") != client
                or manifest.get("first_phase") != "compose-big-idea"
                or manifest.get("stop_after_phase") != "narrative-gate"
                or manifest.get("writer_call_limit") != 60
                or manifest.get("clean_state_sha256") != hashlib.sha256(root_state_bytes).hexdigest()
                or root_state.get("run_id") != root_source_id
                or root_inputs.get("stop_after_phase") != "narrative-gate"
                or root_inputs.get("step7_writer_call_limit") != 60
                or gate.get("status") != "completed"
                or (gate.get("ledger") or {}).get("status") != "passed"
                or admission.get("schema") != "step7-held-step6-source/v1"
                or admission.get("source_run_id") != root_source_id
                or admission.get("source_state_sha256") != manifest.get("source_state_sha256")
                or admission.get("step6_hold_sha256") != hold_sha
                or manifest.get("source_review_hold_sha256") != hold_sha
                or source_hold.get("verdict") != "held"):
            raise AdapterError("step7-clean-copy-manifest-mismatch")
        selected_id = _required_text(answers, "source_run_id")
        reopen_step7 = answers["reopen_completed_phase"] is True
        if phase == "compose-big-idea" and selected_id == root_source_id:
            if reopen_step7:
                raise AdapterError("step7-clean-copy-compose-needs-manifest-source")
        else:
            try:
                selected = json.loads((step7_dir / "state" / f"{selected_id}.json").read_text())
            except (OSError, ValueError, TypeError):
                raise AdapterError("step7-clean-copy-resume-source-missing") from None
            cursor = selected
            seen: set[str] = set()
            while cursor.get("run_id") != root_source_id:
                cursor_id, parent_id = cursor.get("run_id"), cursor.get("parent_run_id")
                if (not isinstance(cursor_id, str) or cursor_id in seen
                        or not isinstance(parent_id, str) or len(seen) >= 100):
                    raise AdapterError("step7-clean-copy-lineage-mismatch")
                seen.add(cursor_id)
                try:
                    cursor = json.loads((step7_dir / "state" / f"{parent_id}.json").read_text())
                except (OSError, ValueError, TypeError):
                    raise AdapterError("step7-clean-copy-lineage-mismatch") from None
            selected_phase = (selected.get("phases") or {}).get(phase) or {}
            allowed = {"completed"} if reopen_step7 else {"blocked", "failed", "running"}
            if selected.get("run_id") != selected_id or selected_phase.get("status") not in allowed:
                raise AdapterError("step7-clean-copy-source-not-resumable")
        feedback = answers["step7_feedback_path"]
        if feedback is not None:
            feedback_path = Path(feedback)
            if not feedback_path.is_absolute():
                feedback_path = Path(repository, feedback_path)
            if (phase != "compose-message-architecture"
                    or feedback_path.resolve().parent != step7_dir / "record"
                    or not feedback_path.is_file()):
                raise AdapterError("step7-feedback-must-target-compose-and-record")
            argv.extend(["--step7-feedback-file", str(feedback_path.resolve())])
        argv.extend(["--task-dir", str(step7_dir)])
    elif answers["step7_feedback_path"] is not None:
        raise AdapterError("step7-feedback-requires-its-clean-copy")

    step8_dir_answer = answers["step8_clean_task_dir"]
    step8_dir: Path | None = None
    if step8_dir_answer is not None:
        client = _required_text(answers, "client")
        expected_step8 = Path(repository).resolve() / "Tasks" / f"{client}-step8-clean-20261006"
        supplied_step8 = Path(_required_text(answers, "step8_clean_task_dir"))
        if not supplied_step8.is_absolute():
            supplied_step8 = Path(repository, supplied_step8)
        step8_dir = supplied_step8.resolve()
        current_step8 = (step8_dir.parent == Path(repository).resolve() / "Tasks"
                         and re.fullmatch(rf"{re.escape(client)}-step8-clean-[0-9a-f]{{12}}",
                                          step8_dir.name) is not None)
        if (step8_dir != expected_step8 and not current_step8) or not step8_dir.is_dir():
            raise AdapterError("step8-clean-copy-missing-or-mismatched")
        if current_step8:
            check = subprocess.run(
                [python, str(Path(repository, "scripts/prepare_step8_clean_copy.py")),
                 "--resolve-recorded-route", "--client", client],
                cwd=repository, env={**os.environ, "PYTHONPATH": "src:."},
                capture_output=True, text=True, timeout=30,
            )
            if check.returncode != 0:
                raise AdapterError("step8-current-copy-source-invalid")
            current_route = json.loads(check.stdout)
            if Path(current_route.get("copy_dir", "")) != step8_dir:
                raise AdapterError("step8-current-copy-source-mismatch")
        if (step2_dir is not None or step3_dir is not None or step4_dir is not None
                or step5_dir is not None or step6_dir is not None or step7_dir is not None
                or step9_supplied or clean_supplied or clean_writer_supplied
                or answers["step11_clean_task_dir"] is not None
                or answers["step12_task_dir"] is not None
                or any(answers[key] is not None for key in (
                    "corrected_topic_policies_path", "client_answers_path",
                    "debrief_feedback_path", "final_brief_feedback_path", "gate_approvals_path",
                    "step6_feedback_path", "step7_feedback_path", "step10_admission_path",
                    "step10_altitude_check_path", "step11_altitude_check_path",
                    "step12_altitude_check_path"))):
            raise AdapterError("step8-clean-copy-exclusive-with-other-routes")
        phase = _required_text(answers, "first_unfinished_phase")
        if phase not in {"compose-communications-platform", "platform-architecture-gate"}:
            raise AdapterError("step8-clean-copy-phase-outside-step8")
        try:
            manifest = json.loads((step8_dir / "record/step8-clean-copy.json").read_text())
            root_source_id = manifest["source_run_id"]
            root_state_bytes = (step8_dir / "state" / f"{root_source_id}.json").read_bytes()
            root_state = json.loads(root_state_bytes)
        except (OSError, ValueError, KeyError, TypeError):
            raise AdapterError("step8-clean-copy-manifest-invalid") from None
        root_inputs = (root_state.get("context") or {}).get("inputs") or {}
        root_up = (((root_state.get("context") or {}).get("up") or {}).get("cd_s_002") or {})
        admission = root_inputs.get("step8_source_admission") or {}
        source_hold = root_up.get("step7_review_hold") or {}
        hold_sha = hashlib.sha256((json.dumps(source_hold, ensure_ascii=False,
            sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()
        gate = (root_state.get("phases") or {}).get("narrative-gate") or {}
        if (manifest.get("schema") != "step8-clean-copy/v1"
                or manifest.get("client") != client
                or manifest.get("first_phase") != "compose-communications-platform"
                or manifest.get("stop_after_phase") != "platform-architecture-gate"
                or manifest.get("writer_call_limit") != 60
                or manifest.get("clean_state_sha256") != hashlib.sha256(root_state_bytes).hexdigest()
                or root_state.get("run_id") != root_source_id
                or root_inputs.get("stop_after_phase") != "platform-architecture-gate"
                or root_inputs.get("step8_writer_call_limit") != 60
                or gate.get("status") != "completed"
                or (gate.get("ledger") or {}).get("status") != "passed"
                or admission.get("schema") != "step8-held-step7-source/v1"
                or admission.get("source_run_id") != root_source_id
                or admission.get("source_state_sha256") != manifest.get("source_state_sha256")
                or admission.get("step7_hold_sha256") != hold_sha
                or manifest.get("source_review_hold_sha256") != hold_sha
                or source_hold.get("verdict") != "held"):
            raise AdapterError("step8-clean-copy-manifest-mismatch")
        selected_id = _required_text(answers, "source_run_id")
        reopen_step8 = answers["reopen_completed_phase"] is True
        if phase == "compose-communications-platform" and selected_id == root_source_id:
            if reopen_step8:
                raise AdapterError("step8-clean-copy-compose-needs-manifest-source")
        else:
            try:
                selected = json.loads((step8_dir / "state" / f"{selected_id}.json").read_text())
            except (OSError, ValueError, TypeError):
                raise AdapterError("step8-clean-copy-resume-source-missing") from None
            cursor = selected
            seen: set[str] = set()
            while cursor.get("run_id") != root_source_id:
                cursor_id, parent_id = cursor.get("run_id"), cursor.get("parent_run_id")
                if (not isinstance(cursor_id, str) or cursor_id in seen
                        or not isinstance(parent_id, str) or len(seen) >= 100):
                    raise AdapterError("step8-clean-copy-lineage-mismatch")
                seen.add(cursor_id)
                try:
                    cursor = json.loads((step8_dir / "state" / f"{parent_id}.json").read_text())
                except (OSError, ValueError, TypeError):
                    raise AdapterError("step8-clean-copy-lineage-mismatch") from None
            selected_phase = (selected.get("phases") or {}).get(phase) or {}
            allowed = {"completed"} if reopen_step8 else {"blocked", "failed", "running"}
            if selected.get("run_id") != selected_id or selected_phase.get("status") not in allowed:
                raise AdapterError("step8-clean-copy-source-not-resumable")
        argv.extend(["--task-dir", str(step8_dir)])

    step12_dir_answer = answers["step12_task_dir"]
    step12_altitude = answers["step12_altitude_check_path"]
    step12_dir: Path | None = None
    if step12_dir_answer is not None or step12_altitude is not None:
        # Step 12 copy route (D53): same design as the clean-step11 route above.
        if step12_dir_answer is None:
            raise AdapterError("step12-requires-its-own-copy-folder")
        if any(value is not None for value in (
                clean_admission, clean_altitude, clean_annual_altitude)):
            raise AdapterError("step12-one-gate-input-at-a-time")
        if (step9_supplied or clean_supplied or clean_writer_supplied
                or step5_dir is not None
                or any(answers[key] is not None for key in (
                    "client_answers_path", "debrief_feedback_path", "final_brief_feedback_path",
                    "gate_approvals_path", "corrected_topic_policies_path"))):
            raise AdapterError("step12-exclusive-with-other-resume-inputs")
        client = _required_text(answers, "client")
        tasks_root = Path(repository).resolve() / "Tasks"
        supplied_step12 = Path(_required_text(answers, "step12_task_dir"))
        if not supplied_step12.is_absolute():
            supplied_step12 = Path(repository, supplied_step12)
        step12_dir = supplied_step12.resolve()
        if step12_dir.parent != tasks_root:
            raise AdapterError("step12-copy-folder-outside-tasks")
        if not re.fullmatch(rf"{re.escape(client)}-step12-\d{{8}}", step12_dir.name):
            raise AdapterError("step12-copy-folder-name-mismatch")
        if not step12_dir.is_dir():
            raise AdapterError("step12-copy-folder-missing")
        if not (step12_dir / "state").is_dir() or not (step12_dir / "record").is_dir():
            raise AdapterError("step12-copy-folder-needs-state-and-record")
        selected_phase = _required_text(answers, "first_unfinished_phase")
        if selected_phase not in STEP12_ALLOWED_PHASES:
            raise AdapterError("step12-phase-not-allowed")
        if answers["reopen_completed_phase"] is not False:
            raise AdapterError("step12-must-resume-first-unfinished-phase")
        if step12_altitude is not None:
            if selected_phase != "roadmap-gate":
                raise AdapterError("step12-holder-check-needs-roadmap-gate")
            altitude_path = Path(_required_text(answers, "step12_altitude_check_path"))
            if not altitude_path.is_absolute():
                altitude_path = Path(repository, altitude_path)
            if (altitude_path.resolve() != step12_dir / "record" / "roadmap-altitude-check.json"
                    or not altitude_path.is_file()):
                raise AdapterError("step12-holder-check-file-mismatch")
            argv.extend(["--task-dir", str(step12_dir), "--altitude-check-file", str(altitude_path)])
        else:
            argv.extend(["--task-dir", str(step12_dir)])
    if clean_supplied:
        if step9_supplied or clean_dir_answer is None:
            raise AdapterError("clean-step11-requires-its-own-copy-folder")
        client = _required_text(answers, "client")
        expected_clean = Path(repository).resolve() / "Tasks" / f"{client}-step11-clean-20261002"
        supplied_clean = Path(_required_text(answers, "step11_clean_task_dir"))
        if not supplied_clean.is_absolute():
            supplied_clean = Path(repository, supplied_clean)
        if supplied_clean.resolve() != expected_clean:
            raise AdapterError("clean-step11-copy-folder-mismatch")
        if any(answers[key] is not None for key in (
            "client_answers_path", "debrief_feedback_path", "final_brief_feedback_path",
            "gate_approvals_path", "corrected_topic_policies_path",
        )):
            raise AdapterError("clean-step11-exclusive-with-other-resume-inputs")
        if sum(value is not None for value in (clean_admission, clean_altitude, clean_annual_altitude)) > 1:
            raise AdapterError("clean-step11-one-gate-input-at-a-time")
        if clean_writer_supplied and (clean_admission is not None or clean_altitude is not None
                                      or clean_annual_altitude is not None):
            raise AdapterError("clean-step11-writer-needs-compose-only")
        selected_phase = _required_text(answers, "first_unfinished_phase")
        if clean_admission is not None:
            if selected_phase != "compose-measurement-framework" or answers["reopen_completed_phase"] is not True or clean_altitude is not None:
                raise AdapterError("clean-step11-admission-needs-step10-compose-reopen")
            admission_path = Path(_required_text(answers, "step10_admission_path"))
            if not admission_path.is_absolute():
                admission_path = Path(repository, admission_path)
            if admission_path.resolve() != expected_clean / "record" / "step10-admission.json" or not admission_path.is_file():
                raise AdapterError("clean-step11-admission-file-mismatch")
            argv.extend(["--task-dir", str(expected_clean), "--step10-admission-file", str(admission_path)])
        elif clean_altitude is not None:
            if selected_phase != "measurement-gate" or answers["reopen_completed_phase"] is not False:
                raise AdapterError("clean-step11-holder-check-needs-measurement-gate")
            altitude_path = Path(_required_text(answers, "step10_altitude_check_path"))
            if not altitude_path.is_absolute():
                altitude_path = Path(repository, altitude_path)
            if altitude_path.resolve() != expected_clean / "record" / "measurement-altitude-check.json" or not altitude_path.is_file():
                raise AdapterError("clean-step11-holder-check-file-mismatch")
            argv.extend(["--task-dir", str(expected_clean), "--altitude-check-file", str(altitude_path)])
        elif clean_annual_altitude is not None:
            if selected_phase != "annual-review-gate" or answers["reopen_completed_phase"] is not False:
                raise AdapterError("clean-step11-holder-check-needs-annual-review-gate")
            altitude_path = Path(_required_text(answers, "step11_altitude_check_path"))
            if not altitude_path.is_absolute():
                altitude_path = Path(repository, altitude_path)
            if (altitude_path.resolve() != expected_clean / "record" / "annual-review-altitude-check.json"
                    or not altitude_path.is_file()):
                raise AdapterError("clean-step11-annual-holder-check-file-mismatch")
            argv.extend(["--task-dir", str(expected_clean), "--altitude-check-file", str(altitude_path)])
        else:
            if (selected_phase != "compose-annual-review"
                    or (answers["reopen_completed_phase"] is True and not clean_writer_supplied)):
                raise AdapterError("clean-step11-automatic-writer-needs-annual-review")
            if clean_writer_supplied:
                input_path = Path(_required_text(answers, "step11_writer_input_path"))
                budget_path = Path(_required_text(answers, "step11_writer_call_budget_path"))
                if not input_path.is_absolute():
                    input_path = Path(repository, input_path)
                if not budget_path.is_absolute():
                    budget_path = Path(repository, budget_path)
                try:
                    writer_input = json.loads(input_path.read_text(encoding="utf-8"))
                    writer_source = writer_input["source_run_id"]
                except (OSError, ValueError, KeyError, TypeError):
                    raise AdapterError("clean-step11-writer-input-or-budget-mismatch") from None
                if not isinstance(writer_source, str) or not writer_source.startswith("up-run-"):
                    raise AdapterError("clean-step11-writer-input-or-budget-mismatch")
                expected_budget = expected_clean / "state" / f"step11-writer-budget-{writer_source}.json"
                if (input_path.resolve().parent != expected_clean / "record"
                        or not input_path.name.startswith("step11-writer-input")
                        or input_path.suffix != ".json" or not input_path.is_file()
                        or budget_path.resolve() != expected_budget
                        or not budget_path.is_file()):
                    raise AdapterError("clean-step11-writer-input-or-budget-mismatch")
            argv.extend(["--task-dir", str(expected_clean)])
    if step9_supplied:
        if step9_dir is None:
            raise AdapterError("step9-rehearsal-requires-copy-folder")
        generic_copy_resume = (
            step9_limit is None and not step9_continuation and step9_extend_to is None
        )
        selected_phase = _required_text(answers, "first_unfinished_phase")
        allowed_phases = ("compose-execution-toolkit", "compose-annual-review") if generic_copy_resume else ("compose-execution-toolkit",)
        if selected_phase not in allowed_phases:
            raise AdapterError("rehearsal-copy-needs-step9-or-step11-compose")
        if any(answers[key] is not None for key in (
            "client_answers_path", "debrief_feedback_path", "final_brief_feedback_path",
            "gate_approvals_path", "corrected_topic_policies_path",
            "step11_writer_input_path", "step11_writer_call_budget_path",
            "step11_writer_call_limit", "step11_writer_call_extension_from",
        )):
            raise AdapterError("step9-rehearsal-exclusive-with-other-resume-inputs")
        client = _required_text(answers, "client")
        expected_dir = Path(repository).resolve() / "Tasks" / f"{client}-rehearsal-demo"
        supplied_dir = Path(_required_text(answers, "step9_rehearsal_task_dir"))
        if not supplied_dir.is_absolute():
            supplied_dir = Path(repository, supplied_dir)
        if supplied_dir.resolve() != expected_dir:
            raise AdapterError("step9-rehearsal-copy-folder-mismatch")
        if generic_copy_resume:
            if answers["reopen_completed_phase"] is not False:
                raise AdapterError("automatic-writer-copy-resume-needs-first-unfinished-phase")
            argv.extend(["--task-dir", str(expected_dir)])
        elif step9_continuation:
            if answers["reopen_completed_phase"] is not False:
                raise AdapterError("step9-continuation-must-preserve-blocked-phase")
            if step9_extend_to is not None:
                if (type(step9_extend_to) is not int or step9_extend_to not in (60, 150)
                        or (step9_extend_to == 60 and (answers["client"] != "bteam"
                             or answers["source_run_id"] != "up-run-9e6d9c40be19"))):
                    raise AdapterError("step9-budget-extension-selected-run-mismatch")
                if step9_limit is not None:
                    raise AdapterError("step9-extension-must-use-extend-to-only")
                argv.extend([
                    "--task-dir", str(expected_dir),
                    "--step9-native-writer-continue",
                    "--step9-native-writer-extend-to", str(step9_extend_to),
                ])
            else:
                if step9_limit is not None:
                    raise AdapterError("step9-continuation-must-reuse-saved-call-limit")
                argv.extend([
                    "--task-dir", str(expected_dir),
                    "--step9-native-writer-continue",
                ])
        else:
            if step9_extend_to is not None:
                raise AdapterError("step9-budget-extension-requires-saved-cache-continuation")
            if step9_limit is None:
                raise AdapterError("step9-rehearsal-requires-copy-and-call-limit")
            if answers["reopen_completed_phase"] is not True:
                raise AdapterError("step9-rehearsal-must-reopen-compose")
            if type(step9_limit) is not int or not 1 <= step9_limit <= 150:
                raise AdapterError("invalid-step9-native-writer-call-limit")
            argv.extend([
                "--task-dir", str(expected_dir),
                "--step9-native-writer-call-limit", str(step9_limit),
            ])
    step11_writer_keys = (
        "step11_writer_input_path",
        "step11_writer_call_budget_path",
        "step11_writer_call_limit",
    )
    step11_writer_values = [answers.get(key) for key in step11_writer_keys]
    step11_writer_supplied = any(value is not None for value in step11_writer_values)
    if step11_writer_supplied:
        if not all(value is not None for value in step11_writer_values):
            raise AdapterError(
                "step11-writer-input-requires-input-budget-and-limit: supply all three "
                "Step 11 writer settings together or leave all three blank."
            )
        first_unfinished_phase = _required_text(
            answers, "first_unfinished_phase",
        )
        if first_unfinished_phase != "compose-annual-review":
            raise AdapterError(
                "step11-writer-input-needs-compose-annual-review: supplied while "
                f"resuming {first_unfinished_phase!r}; resume at "
                "'compose-annual-review' or leave all three settings blank."
            )
        other_resume_inputs = (
            "client_answers_path",
            "debrief_feedback_path",
            "final_brief_feedback_path",
            "gate_approvals_path",
            "corrected_topic_policies_path",
        )
        supplied_other_inputs = [
            key for key in other_resume_inputs if answers.get(key) is not None
        ]
        if supplied_other_inputs:
            raise AdapterError(
                "step11-writer-input-exclusive-with-other-resume-inputs: "
                "Step 11 writer settings cannot be combined with "
                f"{', '.join(supplied_other_inputs)}. Leave those input files blank."
            )
        call_limit = answers["step11_writer_call_limit"]
        if (
            not isinstance(call_limit, int)
            or isinstance(call_limit, bool)
            or call_limit < 1
        ):
            raise AdapterError("invalid-step11-writer-call-limit")
    extension_from = answers["step11_writer_call_extension_from"]
    if extension_from is not None:
        if not step11_writer_supplied:
            raise AdapterError("step11-writer-extension-requires-writer-settings")
        if (
            not isinstance(extension_from, int)
            or isinstance(extension_from, bool)
            or extension_from < 1
            or extension_from >= call_limit
        ):
            raise AdapterError("invalid-step11-writer-call-extension")
    if answers.get("corrected_topic_policies_path") is not None:
        # A corrected owner policy set rides only the resume that re-runs its own prepare
        # phase. Added 2026-08-22 after a mid-sentence allowed-fact excerpt blocked a run
        # whose corrected set had no way back in.
        if _required_text(answers, "first_unfinished_phase") != (
            "prepare-controlled-topic-policy-inputs"
        ):
            raise AdapterError(
                "corrected-topic-policies-need-their-own-phase: the corrected policy set "
                f"was supplied while resuming "
                f"{_required_text(answers, 'first_unfinished_phase')!r}, but it is valid "
                "only when resuming 'prepare-controlled-topic-policy-inputs'. Leave the "
                "answer blank, or resume at that phase."
            )
        argv.extend([
            "--controlled-topic-policies-file",
            _required_text(answers, "corrected_topic_policies_path"),
        ])
    if answers.get("client_answers_path") is not None:
        # Answers that surfaced after the run settled ride only the resume that re-enters
        # at their first consuming phase. Added 2026-08-22 for the B-team owners' interview,
        # found in a legacy document after the run had reached its debrief gate.
        if _required_text(answers, "first_unfinished_phase") not in (
            "prepare-controlled-topic-policy-inputs",
            "ingest-leadership-interview",
        ):
            raise AdapterError(
                "client-answers-need-their-consuming-phase: the answers file was supplied "
                f"while resuming {_required_text(answers, 'first_unfinished_phase')!r}, but "
                "it is valid only when resuming 'prepare-controlled-topic-policy-inputs' or "
                "'ingest-leadership-interview'. Leave the answer blank, or resume at one of "
                "those phases."
            )
        argv.extend([
            "--client-answers-file",
            _required_text(answers, "client_answers_path"),
        ])
    for key, flag in (
        ("debrief_feedback_path", "--debrief-feedback-file"),
        ("final_brief_feedback_path", "--final-brief-feedback-file"),
        ("gate_approvals_path", "--gate-approvals-file"),
    ):
        if answers.get(key) is None:
            continue
        # A reviewer's round and her closure enter at the gate holding the document.
        # Added 2026-08-22 for the first real Step 2 replies.
        if "gate" not in _required_text(answers, "first_unfinished_phase"):
            raise AdapterError(
                f"{key.replace('_', '-')}-needs-a-gate-phase: supplied while resuming "
                f"{_required_text(answers, 'first_unfinished_phase')!r}, but it is valid "
                "only when resuming a gate phase. Leave the answer blank, or resume at the "
                "gate."
            )
        argv.extend([flag, _required_text(answers, key)])
    if step11_writer_supplied:
        argv.extend([
            "--step11-writer-input-file",
            _required_text(answers, "step11_writer_input_path"),
            "--step11-writer-call-budget-file",
            _required_text(answers, "step11_writer_call_budget_path"),
            "--step11-writer-call-limit",
            str(call_limit),
        ])
        if extension_from is not None:
            argv.extend([
                "--step11-writer-call-extension-from", str(extension_from),
            ])
    drive_staging_root = None
    if (step1_dir is not None or step2_dir is not None or step3_dir is not None or step4_dir is not None
            or step5_handoff_dir is not None or step5_dir is not None or step6_handoff_dir is not None or step6_dir is not None or step7_handoff_dir is not None or step7_dir is not None
            or step9_handoff_dir is not None or step8_handoff_dir is not None or step8_dir is not None
            or step9_supplied or clean_supplied
            or step12_dir is not None):
        drive_staging_root = ((step9_handoff_dir or step8_handoff_dir or step7_handoff_dir or step6_handoff_dir or step5_handoff_dir or step1_dir or step2_dir or step3_dir or step4_dir or step5_dir or step6_dir or step7_dir or step8_dir or step12_dir or (expected_clean if clean_supplied else expected_dir)) / "drive-staging")
    environment = _workflow_resume_live_environment(
        python, drive_staging_root=drive_staging_root,
        agent_max_attempts="2" if step1_dir is not None else ("1" if drive_staging_root is not None else "3"),
    )
    if step1_dir is not None:
        # A signed review re-enters the general model-reading/amendment seam. Its
        # stateless JSON role may retry one malformed response, with both attempts
        # logged; later writer-copy routes keep their one-attempt call accounting.
        environment["UP_HARNESS_AGENT_MAX_ATTEMPTS"] = "2"
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
        "client_classification_path",
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
        "--client-classification-file",
        _required_text(answers, "client_classification_path"),
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


def _bootstrap_runtime_dependencies(
    answers: Mapping[str, Any],
    repository_roots: Mapping[str, str],
    dependencies: list[dict[str, str]],
) -> None:
    present = answers.get("has_runtime_dependencies")
    if not isinstance(present, bool):
        raise AdapterError("invalid-bootstrap-runtime-dependency-choice")
    raw = answers.get("runtime_dependencies")
    if not present:
        if raw is not None:
            raise AdapterError("unexpected-bootstrap-runtime-dependencies")
        return
    if not isinstance(raw, list) or not raw:
        raise AdapterError("answer-required:runtime_dependencies")
    seen = {
        (item["repository_key"], item["path_or_sequence_id"])
        for item in dependencies
    }
    for item in raw:
        if not isinstance(item, Mapping) or set(item) != {"repository_key", "path"}:
            raise AdapterError("invalid-bootstrap-runtime-dependency")
        repository_key = _required_text(item, "repository_key")
        if repository_key not in repository_roots:
            raise AdapterError(f"repository-key-unregistered:{repository_key}")
        path = _required_text(item, "path")
        relative = PurePosixPath(path)
        if relative.is_absolute() or ".." in relative.parts:
            raise AdapterError("invalid-bootstrap-runtime-dependency-path")
        identity = (repository_key, path)
        if identity not in seen:
            dependencies.append({
                "kind": "file",
                "repository_key": repository_key,
                "path_or_sequence_id": path,
            })
            seen.add(identity)


def _prepare_discovery_bootstrap(
    answers: Mapping[str, Any],
    artifact_paths: Mapping[str, str],
    repository_roots: Mapping[str, str],
) -> dict[str, Any]:
    expected = {
        "source_repository_key", "task_id", "operation_kind", "date",
        "sequence_name", "outcome", "why_repeatable", "steps", "inputs",
        "has_runtime_dependencies", "failure_handling", "verified_path",
        "repo_roots_file",
    }
    if answers.get("has_runtime_dependencies") is True:
        expected.add("runtime_dependencies")
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
    _bootstrap_runtime_dependencies(answers, repository_roots, dependencies)
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


def _prepare_local_multimodal_benchmark(
    answers: Mapping[str, Any],
    artifact_paths: Mapping[str, str],
    repository_roots: Mapping[str, str],
) -> dict[str, Any]:
    expected = {
        "source_repository_key", "model", "endpoint", "pull_if_missing",
        "thinking_mode", "timeout_seconds", "context_length", "output_path", "cases",
    }
    if set(answers) != expected:
        raise AdapterError("answer-fields-do-not-match-local-multimodal-benchmark")
    repository_key, repository = _registered_repository(
        answers, repository_roots, answer_key="source_repository_key",
    )
    thinking_modes = {"disabled": False, "enabled": True}
    thinking_mode = _required_text(answers, "thinking_mode")
    if thinking_mode not in thinking_modes:
        raise AdapterError("answer-invalid:thinking_mode")
    raw_cases = answers.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise AdapterError("answer-required:cases")
    cases: list[dict[str, Any]] = []
    for item in raw_cases:
        if not isinstance(item, Mapping) or set(item) != {
            "id", "prompt", "source_files", "response_schema_file",
        }:
            raise AdapterError("invalid-local-multimodal-benchmark-case")
        source_files = item.get("source_files")
        if not isinstance(source_files, list) or not source_files:
            raise AdapterError("answer-required:source_files")
        schema_path = Path(
            _required_text(item, "response_schema_file")
        ).expanduser()
        try:
            response_schema = json.loads(schema_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AdapterError("response-schema-file-invalid") from exc
        cases.append({
            "id": _required_text(item, "id"),
            "prompt": _required_text(item, "prompt"),
            "source_files": [
                _required_text({"value": value}, "value")
                for value in source_files
            ],
            "response_schema": response_schema,
        })
    spec = {
        "schema_version": 1,
        "model": _required_text(answers, "model"),
        "endpoint": _required_text(answers, "endpoint"),
        "pull_if_missing": answers.get("pull_if_missing"),
        "think": thinking_modes[thinking_mode],
        "timeout_seconds": answers.get("timeout_seconds"),
        "output_path": _required_text(answers, "output_path"),
        "options": {
            "temperature": 0,
            "num_ctx": answers.get("context_length"),
        },
        "cases": cases,
    }
    try:
        local_multimodal_model_benchmark._normalize_spec(spec)
    except local_multimodal_model_benchmark.BenchmarkError as exc:
        raise AdapterError(f"local-multimodal-benchmark-invalid:{exc.code}") from exc
    artifact = _json_artifact(artifact_paths, "benchmark_spec", spec)
    payload = _script_payload(
        sequence_id="local-multimodal-model-benchmark",
        profile="run",
        argv=[
            "python3",
            str(Path(repository, "scripts/local_multimodal_model_benchmark.py")),
            "--spec",
            artifact["path"],
        ],
        repository_key=repository_key,
        repository_root=repository,
        effectful=True,
        operation="run",
    )
    payload["artifacts"] = {"benchmark_spec": artifact}
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
ADAPTER_REGISTRY["goal-declaration"] = _prepare_goal_declaration
ADAPTER_REGISTRY["agent-heartbeat"] = _prepare_agent_heartbeat
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
ADAPTER_REGISTRY[
    "local-multimodal-model-benchmark"
] = _prepare_local_multimodal_benchmark
INTAKE_SPECS = {
    "commit-push-main": COMMIT_PUSH_SPEC,
    "goal-declaration": GOAL_DECLARATION_SPEC,
    "agent-heartbeat": AGENT_HEARTBEAT_SPEC,
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
    "local-multimodal-model-benchmark": LOCAL_MULTIMODAL_BENCHMARK_SPEC,
}

ARTIFACT_IDS: dict[str, tuple[str, ...]] = {
    "commit-push-main": ("approved_paths", "overlay_paths"),
    "goal-declaration": ("goal_answers",),
    "discovery-promotion-lifecycle": ("changed_artifacts",),
    "convergence-state-review-cycle": ("request",),
    "discovery-bootstrap": ("spec",),
    "local-multimodal-model-benchmark": ("benchmark_spec",),
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
    if ADAPTER_REGISTRY[sequence_id] is None:
        raise AdapterUnavailable(f"sequence-not-runnable-through-intake:{sequence_id}")
    try:
        spec = deepcopy(INTAKE_SPECS[sequence_id])
    except KeyError as exc:
        raise AdapterUnavailable(f"adapter-not-implemented:{sequence_id}") from exc
    if sequence_id == "workflow-resume-from-phase-live-confirmation":
        for field in spec["fields"]:
            if field["id"] == "step8_held_by":
                field["when"] = {"field": "source_run_id", "equals": STEP8_RECORDED_SOURCE}
            elif field["id"] in {"step9_held_by", "step9_altitude_check_path",
                                  "step9_newsroom_model", "step9_earned_pipeline",
                                  "step9_decided_by"}:
                field["when"] = {"field": "source_run_id", "equals": STEP9_RECORDED_SOURCE}
            elif field["id"] in {"step11_held_by", "step10_held_by", "step10_hold_reason"}:
                field["when"] = {"field": "source_run_id", "equals": STEP11_RECORDED_SOURCE}
            elif field["id"] not in {"repository_key", "client", "source_run_id"}:
                field["when"] = {"field": "source_run_id",
                                 "not_in": [STEP8_RECORDED_SOURCE, STEP9_RECORDED_SOURCE,
                                           STEP10_RECORDED_SOURCE, STEP11_RECORDED_SOURCE]}
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
        repository_field["example"] = (
            "1" if repository_field.get("numbered_selection", False)
            else choices[0]
        )
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
        raise AdapterUnavailable(f"sequence-not-runnable-through-intake:{sequence_id}")
    return adapter(answers, artifact_paths, repository_roots)


def collect_and_prepare(
    sequence_id: str,
    *,
    artifact_paths: Mapping[str, str],
    repository_roots: Mapping[str, str],
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    spec = intake_spec(sequence_id, repository_roots=repository_roots)
    answers = script_intake.collect(
        spec,
        input_fn=input_fn,
        output_fn=output_fn,
    )
    if (sequence_id == "workflow-resume-from-phase-live-confirmation"
            and answers.get("source_run_id") in {STEP8_RECORDED_SOURCE, STEP9_RECORDED_SOURCE,
                                                  STEP10_RECORDED_SOURCE, STEP11_RECORDED_SOURCE}):
        for field in spec["fields"]:
            if field["id"] not in answers:
                answers[field["id"]] = False if field["type"] == "boolean" else None
        answers["first_unfinished_phase"] = (
            "compose-communications-platform" if answers["source_run_id"] == STEP8_RECORDED_SOURCE
            else ("compose-execution-toolkit" if answers["source_run_id"] == STEP9_RECORDED_SOURCE
                  else ("compose-annual-review" if answers["source_run_id"] == STEP11_RECORDED_SOURCE
                        else "compose-measurement-framework")))
        answers["reopen_completed_phase"] = False
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
