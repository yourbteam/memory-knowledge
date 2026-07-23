#!/usr/bin/env python3
"""Closed typed contracts for governed operational-sequence dispatch."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SHELL_META_RE = re.compile(r"[;&|`$<>\n\r]")


class ContractError(ValueError):
    """Raised when persisted or caller-supplied prevention data is non-canonical."""


class ActionClass(StrEnum):
    BASH = "BASH"
    APPLY_PATCH = "APPLY_PATCH"
    MCP = "MCP"
    UNIFIED_SHELL = "UNIFIED_SHELL"
    WEB_SEARCH_BROWSER = "WEB_SEARCH_BROWSER"
    SUBAGENT = "SUBAGENT"
    NON_MCP_REMOTE = "NON_MCP_REMOTE"


class OwnerKind(StrEnum):
    PYTHON_SCRIPT = "PYTHON_SCRIPT"
    SHELL_SCRIPT = "SHELL_SCRIPT"
    COMPOSITE = "COMPOSITE"
    SUBSEQUENCE = "SUBSEQUENCE"
    EXTERNAL = "EXTERNAL"


class DecisionKind(StrEnum):
    SELECT_SUCCESSOR = "SELECT_SUCCESSOR"
    SELECT_PROMOTED = "SELECT_PROMOTED"
    SELECT_REGISTERED = "SELECT_REGISTERED"
    REJECT = "REJECT"


class GovernanceLevel(StrEnum):
    FULLY_GOVERNED = "FULLY_GOVERNED"
    HOST_CAPABILITY_UNSATISFIED = "HOST_CAPABILITY_UNSATISFIED"
    UNGOVERNED_DIAGNOSTIC = "UNGOVERNED_DIAGNOSTIC"


class RecurrencePolicy(StrEnum):
    ONE_SHOT = "ONE_SHOT"
    RECURRENT = "RECURRENT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class AvailabilityPolicy(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    CUSTODIAN_EVIDENCE_REQUIRED = "CUSTODIAN_EVIDENCE_REQUIRED"


class IneligibleReasonCode(StrEnum):
    RECURRENCE_ONE_SHOT = "RECURRENCE_ONE_SHOT"
    RECURRENCE_NOT_APPLICABLE = "RECURRENCE_NOT_APPLICABLE"
    AVAILABILITY_UNAVAILABLE = "AVAILABILITY_UNAVAILABLE"
    AVAILABILITY_CUSTODIAN_EVIDENCE_REQUIRED = "AVAILABILITY_CUSTODIAN_EVIDENCE_REQUIRED"
    OWNER_CONTRACT_UNRESOLVED = "OWNER_CONTRACT_UNRESOLVED"
    UNREGISTERED_ACTION_CLASS = "UNREGISTERED_ACTION_CLASS"


class ParameterType(StrEnum):
    STRING = "STRING"
    INTEGER = "INTEGER"
    BOOLEAN = "BOOLEAN"
    PATH = "PATH"
    ENUM = "ENUM"


class BudgetRoleId(StrEnum):
    CORE = "CORE"
    INTERNAL_READINESS = "INTERNAL_READINESS"
    REQUIREMENTS_COVERAGE = "REQUIREMENTS_COVERAGE"
    REQUIREMENTS_SATISFACTION = "REQUIREMENTS_SATISFACTION"
    ADJUDICATOR = "ADJUDICATOR"
    MATERIALIZATION = "MATERIALIZATION"
    TERMINAL = "TERMINAL"
    RETRY = "RETRY"


class ParameterTag(StrEnum):
    STRING = "STRING"
    INTEGER = "INTEGER"
    NUMBER = "NUMBER"
    BOOLEAN = "BOOLEAN"
    PATH = "PATH"
    ENUM = "ENUM"
    UUID = "UUID"
    SHA1 = "SHA1"
    SHA256 = "SHA256"
    RESOURCE_KEY = "RESOURCE_KEY"
    LIST = "LIST"
    SET = "SET"
    EXACT_OBJECT = "EXACT_OBJECT"
    TAGGED_UNION = "TAGGED_UNION"
    SECRET_HANDLE = "SECRET_HANDLE"


class BindingKind(StrEnum):
    STATIC_ROOT = "STATIC_ROOT"
    REPOSITORY = "REPOSITORY"
    RESOURCE = "RESOURCE"
    SECRET = "SECRET"
    APPROVAL = "APPROVAL"


@dataclass(frozen=True)
class BindingReceipt:
    """Non-secret identity returned by a trusted parameter provider."""

    receipt_id: str
    binding_kind: BindingKind
    provider_id: str
    key_or_resource_id: str
    version_id: str
    scope_sha256: str
    value_fingerprint_sha256: str
    consumable: bool
    expires_at_utc: str | None = None

    def __post_init__(self) -> None:
        require_id(self.receipt_id, label="binding-receipt-id")
        if not isinstance(self.binding_kind, BindingKind):
            object.__setattr__(self, "binding_kind", BindingKind(self.binding_kind))
        for field in ("provider_id", "key_or_resource_id", "version_id"):
            require_id(getattr(self, field), label=field.replace("_", "-"))
        require_sha256(self.scope_sha256, label="binding-scope-sha256")
        require_sha256(
            self.value_fingerprint_sha256, label="binding-value-fingerprint-sha256"
        )
        if type(self.consumable) is not bool:
            raise ContractError("invalid-binding-consumable")
        if self.expires_at_utc is not None:
            try:
                parsed = datetime.fromisoformat(self.expires_at_utc.replace("Z", "+00:00"))
            except (TypeError, ValueError) as exc:
                raise ContractError("invalid-binding-expiry") from exc
            if parsed.tzinfo is None:
                raise ContractError("invalid-binding-expiry")
            parsed.astimezone(UTC)

    def canonical_json(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "receipt_id": self.receipt_id,
            "binding_kind": self.binding_kind.value,
            "provider_id": self.provider_id,
            "key_or_resource_id": self.key_or_resource_id,
            "version_id": self.version_id,
            "scope_sha256": self.scope_sha256,
            "value_fingerprint_sha256": self.value_fingerprint_sha256,
            "consumable": self.consumable,
        }
        if self.expires_at_utc is not None:
            value["expires_at_utc"] = self.expires_at_utc
        return value

    @property
    def receipt_sha256(self) -> str:
        return sha256_bytes(canonical_bytes(self.canonical_json()))


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    type: ParameterType
    required: bool
    repeated: bool = False
    secret: bool = False
    enum_values: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_id(self.name, label="parameter-name")
        if self.type == ParameterType.ENUM:
            if not self.enum_values or len(set(self.enum_values)) != len(self.enum_values):
                raise ContractError("invalid-enum-values")
        elif self.enum_values:
            raise ContractError("enum-values-on-non-enum")


@dataclass(frozen=True)
class ParameterValue:
    tag: ParameterTag
    value: Any

    def __post_init__(self) -> None:
        try:
            tag = self.tag if isinstance(self.tag, ParameterTag) else ParameterTag(self.tag)
        except ValueError as exc:
            raise ContractError("invalid-parameter-tag") from exc
        object.__setattr__(self, "tag", tag)
        raw = self.value
        if tag in {
            ParameterTag.STRING, ParameterTag.PATH, ParameterTag.ENUM,
            ParameterTag.UUID, ParameterTag.SHA1, ParameterTag.SHA256,
            ParameterTag.RESOURCE_KEY,
        }:
            if not isinstance(raw, str) or not raw or "\x00" in raw:
                raise ContractError("invalid-string-parameter-value")
            if tag == ParameterTag.PATH:
                path = Path(raw)
                if path.is_absolute():
                    raise ContractError("absolute-path-parameter-value")
                if any(part in {"", ".", ".."} for part in path.parts):
                    raise ContractError("noncanonical-path-parameter-value")
            elif tag == ParameterTag.UUID:
                try:
                    import uuid
                    uuid.UUID(raw)
                except ValueError as exc:
                    raise ContractError("invalid-uuid-parameter-value") from exc
            elif tag == ParameterTag.SHA1 and not re.fullmatch(r"[0-9a-f]{40}", raw):
                raise ContractError("invalid-sha1-parameter-value")
            elif tag == ParameterTag.SHA256 and not SHA256_RE.fullmatch(raw):
                raise ContractError("invalid-sha256-parameter-value")
        elif tag == ParameterTag.INTEGER:
            if isinstance(raw, bool) or not isinstance(raw, int):
                raise ContractError("invalid-integer-parameter-value")
        elif tag == ParameterTag.NUMBER:
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise ContractError("invalid-number-parameter-value")
        elif tag == ParameterTag.BOOLEAN:
            if not isinstance(raw, bool):
                raise ContractError("invalid-boolean-parameter-value")
        elif tag in {ParameterTag.LIST, ParameterTag.SET}:
            if not isinstance(raw, (list, tuple)) or tag == ParameterTag.SET and len(set(map(repr, raw))) != len(raw):
                raise ContractError("invalid-collection-parameter-value")
            normalized = list(raw)
            if tag == ParameterTag.SET:
                normalized.sort(key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")))
            object.__setattr__(self, "value", normalized)
        elif tag == ParameterTag.EXACT_OBJECT:
            if not isinstance(raw, Mapping):
                raise ContractError("invalid-exact-object-parameter-value")
            object.__setattr__(self, "value", dict(raw))
        elif tag == ParameterTag.TAGGED_UNION:
            if not isinstance(raw, Mapping):
                raise ContractError("invalid-tagged-union-parameter-value")
            require_exact_keys(raw, {"tag", "payload"}, label="tagged-union")
            require_id(raw["tag"], label="tagged-union-tag")
            object.__setattr__(self, "value", {"tag": raw["tag"], "payload": raw["payload"]})
        elif tag == ParameterTag.SECRET_HANDLE:
            if not isinstance(raw, Mapping):
                raise ContractError("invalid-secret-handle")
            require_exact_keys(raw, {"provider_id", "key_id", "version_id"}, label="secret-handle")
            normalized = {}
            for field in ("provider_id", "key_id", "version_id"):
                normalized[field] = require_id(raw[field], label=field.replace("_", "-"))
            object.__setattr__(self, "value", normalized)

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> "ParameterValue":
        if not isinstance(value, Mapping):
            raise ContractError("parameter-value-not-object")
        require_exact_keys(value, {"tag", "value"}, label="parameter-value")
        tag = ParameterTag(value["tag"])
        raw = value["value"]
        if tag in {
            ParameterTag.STRING, ParameterTag.PATH, ParameterTag.ENUM,
            ParameterTag.UUID, ParameterTag.SHA1, ParameterTag.SHA256,
            ParameterTag.RESOURCE_KEY,
        }:
            if not isinstance(raw, str) or not raw or "\x00" in raw:
                raise ContractError("invalid-string-parameter-value")
            if tag == ParameterTag.PATH and Path(raw).is_absolute():
                raise ContractError("absolute-path-parameter-value")
        elif tag == ParameterTag.INTEGER:
            if isinstance(raw, bool) or not isinstance(raw, int):
                raise ContractError("invalid-integer-parameter-value")
        elif tag == ParameterTag.BOOLEAN:
            if not isinstance(raw, bool):
                raise ContractError("invalid-boolean-parameter-value")
        elif tag == ParameterTag.NUMBER:
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise ContractError("invalid-number-parameter-value")
        elif tag in {ParameterTag.LIST, ParameterTag.SET}:
            if not isinstance(raw, list):
                raise ContractError("invalid-collection-parameter-value")
        elif tag in {ParameterTag.EXACT_OBJECT, ParameterTag.TAGGED_UNION}:
            if not isinstance(raw, Mapping):
                raise ContractError("invalid-structured-parameter-value")
        elif tag == ParameterTag.SECRET_HANDLE:
            if not isinstance(raw, Mapping):
                raise ContractError("invalid-secret-handle")
            require_exact_keys(raw, {"provider_id", "key_id", "version_id"}, label="secret-handle")
            for field in ("provider_id", "key_id", "version_id"):
                require_id(raw[field], label=field.replace("_", "-"))
            raw = dict(raw)
        return cls(tag=tag, value=raw)

    def canonical_json(self) -> dict[str, Any]:
        return {"tag": self.tag.value, "value": self.value}


@dataclass(frozen=True)
class TypedParameter:
    name: str
    value: ParameterValue

    def __post_init__(self) -> None:
        require_id(self.name, label="parameter-name")
        if type(self.value) is not ParameterValue:
            raise ContractError("typed-parameter-value-required")

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> "TypedParameter":
        if not isinstance(value, Mapping):
            raise ContractError("typed-parameter-not-object")
        require_exact_keys(value, {"name", "value"}, label="typed-parameter")
        return cls(
            name=require_id(value["name"], label="parameter-name"),
            value=ParameterValue.from_json(value["value"]),
        )


@dataclass(frozen=True)
class ActionIntent:
    intent_id: str
    task_id: str
    run_id: str
    requested_sequence_id: str
    requested_implementation_id: str
    compatibility_key: str
    action_class: ActionClass
    parameters: tuple[TypedParameter, ...]

    def __post_init__(self) -> None:
        require_id(self.intent_id, label="intent-id")
        require_id(self.task_id, label="task-id")
        require_id(self.run_id, label="run-id")
        require_id(self.requested_sequence_id, label="requested-sequence-id")
        require_sha256(self.requested_implementation_id, label="requested-implementation-id")
        require_sha256(self.compatibility_key, label="compatibility-key")
        if not isinstance(self.action_class, ActionClass):
            object.__setattr__(self, "action_class", ActionClass(self.action_class))
        if not isinstance(self.parameters, tuple) or any(
            type(item) is not TypedParameter for item in self.parameters
        ):
            raise ContractError("typed-parameters-tuple-required")
        if len({item.name for item in self.parameters}) != len(self.parameters):
            raise ContractError("duplicate-typed-parameter")

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> "ActionIntent":
        if not isinstance(value, Mapping):
            raise ContractError("action-intent-not-object")
        keys = {
            "schema_version", "intent_id", "task_id", "run_id", "requested_sequence_id",
            "requested_implementation_id", "compatibility_key", "action_class", "parameters",
        }
        require_exact_keys(value, keys, label="action-intent")
        if value["schema_version"] != SCHEMA_VERSION or not isinstance(value["parameters"], list):
            raise ContractError("invalid-action-intent-version-or-parameters")
        parameters = tuple(TypedParameter.from_json(item) for item in value["parameters"])
        if len({item.name for item in parameters}) != len(parameters):
            raise ContractError("duplicate-typed-parameter")
        return cls(
            intent_id=require_id(value["intent_id"], label="intent-id"),
            task_id=require_id(value["task_id"], label="task-id"),
            run_id=require_id(value["run_id"], label="run-id"),
            requested_sequence_id=require_id(value["requested_sequence_id"], label="requested-sequence-id"),
            requested_implementation_id=require_sha256(
                value["requested_implementation_id"], label="requested-implementation-id"
            ),
            compatibility_key=require_sha256(value["compatibility_key"], label="compatibility-key"),
            action_class=ActionClass(value["action_class"]),
            parameters=parameters,
        )

    def parameter_map(self) -> dict[str, ParameterValue]:
        return {item.name: item.value for item in self.parameters}


@dataclass(frozen=True)
class HostCapabilities:
    session_id: str
    challenge_nonce: str
    config_sha256: str
    hook_sha256: str
    trusted: bool
    enabled: bool
    intercepted_classes: frozenset[ActionClass]
    withheld_classes: frozenset[ActionClass]
    granted_classes: frozenset[ActionClass]
    issued_at_utc: str
    expires_at_utc: str
    host_signature: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ContractError("unsupported-host-capabilities-schema")
        require_id(self.session_id, label="session-id")
        require_id(self.challenge_nonce, label="challenge-nonce")
        require_sha256(self.config_sha256, label="config-sha256")
        require_sha256(self.hook_sha256, label="hook-sha256")
        require_sha256(self.host_signature, label="host-signature")
        for field in ("trusted", "enabled"):
            if type(getattr(self, field)) is not bool:
                raise ContractError(f"invalid-host-{field}")
        normalized: dict[str, frozenset[ActionClass]] = {}
        for field in ("intercepted_classes", "withheld_classes", "granted_classes"):
            try:
                normalized[field] = frozenset(ActionClass(item) for item in getattr(self, field))
            except (TypeError, ValueError) as exc:
                raise ContractError(f"invalid-{field.replace('_', '-')}") from exc
            object.__setattr__(self, field, normalized[field])
        if normalized["intercepted_classes"] & normalized["withheld_classes"]:
            raise ContractError("host-class-both-intercepted-and-withheld")
        uncovered = normalized["granted_classes"] - (
            normalized["intercepted_classes"] | normalized["withheld_classes"]
        )
        if uncovered:
            raise ContractError("host-granted-class-uncovered")


@dataclass(frozen=True)
class OperationSignature:
    operation_kind: str
    effect_class: str
    verification_contract_sha256: str
    parameter_schema_sha256: str
    action_class: ActionClass
    owner_implementation_id: str
    source_bundle_sha256: str
    repository_roots_sha256: str

    def canonical_json(self) -> dict[str, str]:
        return {
            "operation_kind": self.operation_kind,
            "effect_class": self.effect_class,
            "verification_contract_sha256": self.verification_contract_sha256,
            "parameter_schema_sha256": self.parameter_schema_sha256,
            "action_class": self.action_class.value,
            "owner_implementation_id": self.owner_implementation_id,
            "source_bundle_sha256": self.source_bundle_sha256,
            "repository_roots_sha256": self.repository_roots_sha256,
        }

    def compatibility_key(self, parameters: Mapping[str, ParameterValue]) -> str:
        compatible_parameters = {
            name: value.canonical_json()
            for name, value in sorted(parameters.items())
            if value.tag != ParameterTag.SECRET_HANDLE
        }
        return sha256_bytes(canonical_bytes({
            "schema_version": 1,
            "operation": {
                "operation_kind": self.operation_kind,
                "effect_class": self.effect_class,
                "verification_contract_sha256": self.verification_contract_sha256,
                "action_class": self.action_class.value,
            },
            "parameters": compatible_parameters,
        }))


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def require_exact_keys(value: Mapping[str, Any], required: set[str], *, label: str) -> None:
    actual = set(value)
    if actual != required:
        missing = sorted(required - actual)
        extra = sorted(actual - required)
        raise ContractError(f"{label}-keys:missing={missing}:extra={extra}")


def require_id(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ContractError(f"invalid-{label}")
    return value


def require_sha256(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise ContractError(f"invalid-{label}")
    return value


@dataclass(frozen=True)
class MigrationOwnerSpec:
    sequence_id: str
    owner_kind: OwnerKind
    handler: str
    parameter_contract: str
    argv_contract: str
    effect_identity_contract: str
    reconciler: str
    terminal_contract: str
    repository_keys: tuple[str, ...]
    standalone: bool
    parent_sequence_ids: tuple[str, ...]
    evidence_pointer: str

    KEYS = {
        "sequence_id", "owner_kind", "handler", "parameter_contract", "argv_contract",
        "effect_identity_contract", "reconciler", "terminal_contract", "repository_keys",
        "standalone", "parent_sequence_ids", "evidence_pointer",
    }

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> "MigrationOwnerSpec":
        if not isinstance(value, Mapping):
            raise ContractError("owner-row-not-object")
        require_exact_keys(value, cls.KEYS, label="owner-row")
        repositories = value["repository_keys"]
        parents = value["parent_sequence_ids"]
        if not isinstance(repositories, list) or not repositories:
            raise ContractError("invalid-repository-keys")
        if not isinstance(parents, list):
            raise ContractError("invalid-parent-sequence-ids")
        if not isinstance(value["standalone"], bool):
            raise ContractError("invalid-standalone")
        repository_keys = tuple(require_id(item, label="repository-key") for item in repositories)
        parent_ids = tuple(require_id(item, label="parent-sequence-id") for item in parents)
        if len(set(repository_keys)) != len(repository_keys) or len(set(parent_ids)) != len(parent_ids):
            raise ContractError("duplicate-owner-reference")
        if value["standalone"] == bool(parent_ids):
            raise ContractError("invalid-parent-cardinality")
        handler = require_id(value["handler"], label="handler")
        reconciler = require_id(value["reconciler"], label="reconciler")
        for label in ("parameter_contract", "argv_contract", "effect_identity_contract", "terminal_contract"):
            require_id(value[label], label=label.replace("_", "-"))
        pointer = value["evidence_pointer"]
        if not isinstance(pointer, str) or not re.fullmatch(r"/rows/(0|[1-9][0-9]*)", pointer):
            raise ContractError("invalid-evidence-pointer")
        return cls(
            sequence_id=require_id(value["sequence_id"], label="sequence-id"),
            owner_kind=OwnerKind(value["owner_kind"]),
            handler=handler,
            parameter_contract=value["parameter_contract"],
            argv_contract=value["argv_contract"],
            effect_identity_contract=value["effect_identity_contract"],
            reconciler=reconciler,
            terminal_contract=value["terminal_contract"],
            repository_keys=repository_keys,
            standalone=value["standalone"],
            parent_sequence_ids=parent_ids,
            evidence_pointer=pointer,
        )


@dataclass(frozen=True)
class OwnerRegistry:
    source_inventory: str
    source_inventory_sha256: str
    lineage_ids: Mapping[str, str]
    rows: tuple[MigrationOwnerSpec, ...]

    @classmethod
    def load(cls, path: Path, *, repository_root: Path) -> "OwnerRegistry":
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ContractError("invalid-owner-manifest") from exc
        required = {
            "schema_version", "source_inventory", "source_inventory_sha256", "contract_rule",
            "lineage_ids", "rows",
        }
        if not isinstance(raw, Mapping):
            raise ContractError("owner-manifest-not-object")
        require_exact_keys(raw, required, label="owner-manifest")
        if raw["schema_version"] != SCHEMA_VERSION or not isinstance(raw["contract_rule"], str):
            raise ContractError("unsupported-owner-manifest-version")
        source = raw["source_inventory"]
        if not isinstance(source, str) or Path(source).is_absolute() or ".." in Path(source).parts:
            raise ContractError("invalid-source-inventory")
        expected_hash = require_sha256(raw["source_inventory_sha256"], label="source-inventory-sha256")
        source_path = repository_root / source
        if not source_path.is_file() or sha256_bytes(source_path.read_bytes()) != expected_hash:
            raise ContractError("source-inventory-hash-mismatch")
        if not isinstance(raw["rows"], list):
            raise ContractError("owner-rows-not-array")
        rows = tuple(MigrationOwnerSpec.from_json(item) for item in raw["rows"])
        if len(rows) != 25 or len({row.sequence_id for row in rows}) != len(rows):
            raise ContractError("owner-cardinality-or-identity")
        lineage_ids = raw["lineage_ids"]
        if not isinstance(lineage_ids, Mapping) or set(lineage_ids) != {row.sequence_id for row in rows}:
            raise ContractError("lineage-id-sequence-set-drift")
        validated_lineages = {
            require_id(sequence_id, label="lineage-sequence-id"):
            require_id(lineage_id, label="lineage-id")
            for sequence_id, lineage_id in lineage_ids.items()
        }
        if len({row.evidence_pointer for row in rows}) != len(rows):
            raise ContractError("duplicate-evidence-pointer")
        source_data = json.loads(source_path.read_text(encoding="utf-8"))
        source_rows = source_data.get("rows") if isinstance(source_data, Mapping) else None
        if not isinstance(source_rows, list) or len(source_rows) != len(rows):
            raise ContractError("source-inventory-cardinality")
        for index, row in enumerate(rows):
            if row.evidence_pointer != f"/rows/{index}":
                raise ContractError("non-canonical-evidence-pointer-order")
            source_row = source_rows[index]
            if not isinstance(source_row, Mapping) or source_row.get("sequence_id") != row.sequence_id:
                raise ContractError("evidence-pointer-identity-mismatch")
        known = {row.sequence_id for row in rows}
        for row in rows:
            if any(parent not in known for parent in row.parent_sequence_ids):
                raise ContractError("unknown-parent-sequence")
        return cls(
            source_inventory=source,
            source_inventory_sha256=expected_hash,
            lineage_ids=validated_lineages,
            rows=rows,
        )


def validate_fixed_argv(tokens: Sequence[str]) -> tuple[str, ...]:
    if isinstance(tokens, (str, bytes)) or not tokens:
        raise ContractError("argv-must-be-nonempty-array")
    result: list[str] = []
    for token in tokens:
        if not isinstance(token, str) or not token or SHELL_META_RE.search(token):
            raise ContractError("unsafe-fixed-argv-token")
        result.append(token)
    executable = Path(result[0]).name
    if executable in {"bash", "sh", "zsh"} and len(result) > 1 and result[1] in {"-c", "-lc"}:
        raise ContractError("unsafe-fixed-argv-token")
    return tuple(result)
