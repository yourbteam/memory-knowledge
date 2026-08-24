#!/usr/bin/env python3
"""Project the canonical no-argument intake notice into registered runbooks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

try:
    from scripts import sequence_intake_adapters
except ModuleNotFoundError:
    import sequence_intake_adapters


ROOT = Path(__file__).resolve().parents[1]
BEGIN = "<!-- BEGIN SEMANTIC INTAKE ENTRYPOINT -->"
END = "<!-- END SEMANTIC INTAKE ENTRYPOINT -->"
BLOCK = f"""{BEGIN}
## Operator entry point

After selecting and activating this registered sequence, launch the shared controller with no
arguments:

```bash
python3 scripts/sequence_intake_launch.py
```

Answer only the semantic questions shown. Every question includes its response format, an example,
and constraints. The controller derives JSON, files, environment, flags, and argv; displays the
exact prepared operation; and requires a separate yes/no authorization before guarded dispatch.

Any argument-bearing commands below are machine-compatibility and verification evidence for the
deterministic adapter. Operators and agents must not construct or invoke those forms directly.
{END}
"""
COMMIT_PUSH_BLOCK = f"""{BEGIN}
## Operator entry point

For a new commit/push task, launch the dedicated controller with no arguments:

```bash
python3 scripts/commit_push_main_launch.py
```

It owns classification, exact `commit-push-main` selection, activation, run start, and handoff to
the numbered semantic interview. For a commit/push task that is already selected and activated,
continue through the shared zero-argument handoff:

```bash
python3 scripts/sequence_intake_launch.py
```

Answer only the semantic questions shown. Every question includes its response format, an example,
and constraints. The controller derives JSON, files, environment, flags, and argv; displays the
exact prepared operation; and requires a separate yes/no authorization before guarded dispatch.

Any argument-bearing commands below are machine-compatibility and verification evidence for the
deterministic adapter. Operators and agents must not construct or invoke those forms directly.
{END}
"""
SHARED_DEPENDENCIES = (
    "scripts/script_intake.py",
    "scripts/sequence_intake_adapters.py",
    "scripts/sequence_intake_launch.py",
)


class ProjectionError(ValueError):
    """A registered runbook cannot receive the canonical projection."""


def project(document: str, *, sequence_id: str | None = None) -> str:
    block = COMMIT_PUSH_BLOCK if sequence_id == "commit-push-main" else BLOCK
    if BEGIN in document or END in document:
        if document.count(BEGIN) != 1 or document.count(END) != 1:
            raise ProjectionError("semantic-intake-marker-invalid")
        start = document.index(BEGIN)
        finish = document.index(END, start) + len(END)
        suffix = document[finish:]
        if suffix.startswith("\n"):
            suffix = suffix[1:]
        return document[:start] + block + suffix
    lines = document.splitlines(keepends=True)
    if not lines or not lines[0].startswith("# "):
        raise ProjectionError("sequence-title-required")
    return lines[0] + "\n" + block + "\n" + "".join(lines[1:]).lstrip("\n")


def documents() -> list[Path]:
    paths = [
        ROOT / "operations/sequences" / sequence_id / "sequence.md"
        for sequence_id in sequence_intake_adapters.CANONICAL_SEQUENCE_IDS
    ]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise ProjectionError(
            "registered-sequence-document-missing:" + ",".join(missing)
        )
    return paths


def run(*, check: bool) -> int:
    drift: list[str] = []
    for path in documents():
        current = path.read_text(encoding="utf-8")
        expected = project(current, sequence_id=path.parent.name)
        if current != expected:
            if check:
                drift.append(str(path.relative_to(ROOT)))
            else:
                path.write_text(expected, encoding="utf-8")
        manifest_path = path.with_name("dependencies.json")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProjectionError(
                f"registered-sequence-manifest-invalid:{manifest_path}"
            ) from exc
        dependencies = manifest.get("dependencies")
        if (
            not isinstance(manifest, dict)
            or not isinstance(dependencies, list)
            or any(not isinstance(item, dict) for item in dependencies)
        ):
            raise ProjectionError(
                f"registered-sequence-manifest-invalid:{manifest_path}"
            )
        expected_dependencies = list(dependencies)
        existing = {
            (
                item.get("kind"),
                item.get("repository_key"),
                item.get("path_or_sequence_id"),
            )
            for item in dependencies
        }
        for dependency_path in SHARED_DEPENDENCIES:
            identity = ("file", "memory-knowledge", dependency_path)
            if identity not in existing:
                expected_dependencies.append({
                    "kind": "file",
                    "repository_key": "memory-knowledge",
                    "path_or_sequence_id": dependency_path,
                })
        expected_dependencies.sort(key=lambda item: (
            str(item.get("repository_key")),
            str(item.get("kind")),
            str(item.get("path_or_sequence_id")),
        ))
        expected_manifest = {
            **manifest,
            "dependencies": expected_dependencies,
        }
        expected_bytes = (
            json.dumps(
                expected_manifest,
                sort_keys=True,
                separators=(",", ":"),
            ) + "\n"
        )
        current_bytes = manifest_path.read_text(encoding="utf-8")
        if current_bytes != expected_bytes:
            if check:
                drift.append(str(manifest_path.relative_to(ROOT)))
            else:
                manifest_path.write_text(expected_bytes, encoding="utf-8")
    if drift:
        print(
            "semantic-intake-projection-drift:" + ",".join(drift),
            file=sys.stderr,
        )
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    return run(check=parser.parse_args(argv).check)


if __name__ == "__main__":
    raise SystemExit(main())
