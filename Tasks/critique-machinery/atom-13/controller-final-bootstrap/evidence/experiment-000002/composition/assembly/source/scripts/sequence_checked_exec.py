#!/usr/bin/env python3
"""Guard, durably claim, execute, and durably return one exact argv command."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Sequence

try:
    from scripts import sequence_guard, work_memory
except ModuleNotFoundError:  # direct script execution
    import sequence_guard
    import work_memory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--context-id", required=True)
    parser.add_argument("--step-ordinal", required=True, type=int)
    parser.add_argument("--step-id", required=True)
    parser.add_argument("--source", required=True, choices=sorted(sequence_guard.ALLOWED_SOURCES))
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--source-ref-repository", required=True)
    parser.add_argument("--evidence-text")
    parser.add_argument("--state")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def run(args: argparse.Namespace) -> int:
    argv = list(args.command)
    if argv and argv[0] == "--":
        argv = argv[1:]
    if not argv:
        raise work_memory.WorkMemoryError("execution-command-required", 2)
    events, _ = work_memory.load_ledger()
    start, related = work_memory._run_state(events, args.run_id)
    context = next((
        event for event in related
        if event["event_type"] == "operation_context_recorded"
        and event["context_id"] == args.context_id
    ), None)
    if context is None:
        raise work_memory.WorkMemoryError("operation-context-not-found", 3)
    roots = start.get("repository_roots") or {"memory-knowledge": str(work_memory.ROOT)}
    guarded = sequence_guard.cmd_guard(SimpleNamespace(
        task_id=args.task_id, root=None, state=args.state, directives_path=None,
        directive_state=None, directive_max_age_minutes=sequence_guard.DEFAULT_MAX_AGE_MINUTES,
        step=args.step_id, command=shlex.join(argv), command_argv=argv, source=args.source,
        source_ref=args.source_ref, correction_bootstrap=False,
        post_correction_bootstrap=False, evidence_text=args.evidence_text,
    ))
    authorized_source = Path(guarded["source_ref"]).resolve()
    authorized_bindings: list[tuple[str, Path, str]] = []
    for repository_key, raw_root in roots.items():
        repository_root = Path(raw_root).resolve()
        try:
            relative = str(authorized_source.relative_to(repository_root))
        except ValueError:
            continue
        authorized_bindings.append((repository_key, repository_root, relative))
    if len(authorized_bindings) != 1:
        raise work_memory.WorkMemoryError("authorized-source-repository-ambiguous", 4)
    source_repository, repository_root, source_path = authorized_bindings[0]
    if source_repository != args.source_ref_repository:
        raise work_memory.WorkMemoryError("authorized-source-repository-mismatch", 4)
    if not repository_root.is_dir():
        raise work_memory.WorkMemoryError("execution-repository-root-not-found", 4)
    if args.source == "script":
        invoked_sources = []
        for token in argv:
            if (
                token == authorized_source.name
                or token == str(authorized_source)
                or token.endswith("/" + authorized_source.name)
            ):
                candidate = Path(token)
                invoked_sources.append(
                    candidate.resolve()
                    if candidate.is_absolute()
                    else (repository_root / candidate).resolve()
                )
        if invoked_sources != [authorized_source]:
            raise work_memory.WorkMemoryError("executed-source-does-not-match-authorized-source", 4)
    claim = work_memory.cmd_execution_claim(SimpleNamespace(
        run_id=args.run_id, context_id=args.context_id, step_ordinal=args.step_ordinal,
        step_id=args.step_id, argv_json=json.dumps(argv), command_source=args.source,
        source_ref_repository=source_repository,
        source_ref_path=source_path,
        repository_roots_hash=context["repository_roots_hash"],
    ))
    exit_code = 125
    try:
        exit_code = subprocess.run(
            argv, cwd=str(repository_root), check=False, shell=False,
        ).returncode
    finally:
        work_memory.cmd_execution_return(SimpleNamespace(
            execution_id=claim["execution_id"], exit_code=exit_code,
        ))
    return exit_code


def main(argv: Sequence[str] | None = None) -> int:
    try:
        values = list(sys.argv[1:] if argv is None else argv)
        if not values:
            print(json.dumps({
                "ok": False,
                "error": "registered-sequence-adapter-required",
            }, sort_keys=True), file=sys.stderr)
            return 2
        return run(build_parser().parse_args(values))
    except work_memory.WorkMemoryError as exc:
        print(json.dumps({"ok": False, "error": exc.code}, sort_keys=True), file=sys.stderr)
        return exc.exit_code
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__}, sort_keys=True), file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
