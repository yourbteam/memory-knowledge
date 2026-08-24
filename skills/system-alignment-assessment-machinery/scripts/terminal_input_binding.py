"""Freshly bind every immutable input used by the terminal assessment package."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


class InputBindingError(RuntimeError):
    pass


EXPECTED = {
    "alignment_units": ("system-alignment-assessment-units", "units-admitted"),
    "path_inventory": ("system-alignment-path-inventory", "path-inventory-ready"),
    "actual_trace": ("system-alignment-implementation-trace", "trace-complete"),
    "reference_trace": ("system-alignment-implementation-trace", "trace-complete"),
    "mappings": ("system-alignment-unit-mappings", "mapping-interview-complete"),
    "comparison_results": ("system-alignment-comparison-results", "comparison-complete"),
}


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def artifact_digest(value: dict) -> str:
    return hashlib.sha256(canonical({key: item for key, item in value.items() if key != "artifact_sha256"})).hexdigest()


def bind(spec: dict) -> dict:
    if type(spec) is not dict or set(spec) != {"schema_version", "inputs"} or spec.get("schema_version") != 1:
        raise InputBindingError("spec must contain exactly schema_version 1 and inputs")
    refs = spec["inputs"]
    if type(refs) is not dict or set(refs) != set(EXPECTED):
        raise InputBindingError(f"inputs must name exactly {sorted(EXPECTED)}")
    bound = {}
    for name, (artifact_type, status) in EXPECTED.items():
        ref = refs[name]
        if type(ref) is not dict or set(ref) != {"path", "sha256", "artifact_sha256"}:
            raise InputBindingError(f"inputs.{name} must contain exactly path, sha256, artifact_sha256")
        path = Path(ref["path"])
        try:
            raw = path.read_bytes()
            value = json.loads(raw)
        except Exception as exc:
            raise InputBindingError(f"inputs.{name} is unavailable or invalid: {exc}") from None
        observed = hashlib.sha256(raw).hexdigest()
        if observed != ref["sha256"]:
            raise InputBindingError(f"inputs.{name} bytes changed: expected {ref['sha256']}, observed {observed}")
        if type(value) is not dict or value.get("schema_version") != 1:
            raise InputBindingError(f"inputs.{name} is not a schema-version-1 artifact")
        if value.get("artifact_type") != artifact_type or value.get("status") != status:
            raise InputBindingError(
                f"inputs.{name} identity changed: expected {artifact_type}/{status}, "
                f"observed {value.get('artifact_type')}/{value.get('status')}"
            )
        internal = artifact_digest(value)
        if value.get("artifact_sha256") != internal or ref["artifact_sha256"] != internal:
            raise InputBindingError(f"inputs.{name} artifact digest does not match its content")
        bound[name] = {"ref": dict(ref), "value": value}
    if bound["actual_trace"]["value"].get("lane_role") != "actual":
        raise InputBindingError("actual_trace must carry lane_role actual")
    if bound["reference_trace"]["value"].get("lane_role") != "reference":
        raise InputBindingError("reference_trace must carry lane_role reference")
    return bound
