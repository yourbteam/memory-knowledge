#!/usr/bin/env python3
"""Rank source files that match stable UI text extracted from a screenshot."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


EXCLUDED_GLOBS = (
    "!**/.git/**",
    "!**/node_modules/**",
    "!**/bin/**",
    "!**/obj/**",
    "!**/dist/**",
    "!**/build/**",
    "!**/coverage/**",
    "!**/packages/**",
    "!**/*.min.*",
    "!**/*.map",
)


def repository_state(repo: Path) -> str:
    if not repo.is_dir():
        return "missing-repository"
    if not any(path.name != ".git" for path in repo.iterdir()):
        return "empty-repository"
    return "ready"


def search(repo: Path, terms: list[str], max_hits: int = 500) -> dict:
    state = repository_state(repo)
    result: dict = {
        "repository": str(repo),
        "repository_state": state,
        "terms": terms,
        "status": state,
        "candidate_files": [],
        "hits": [],
    }
    if state != "ready":
        result["next_action"] = "Confirm the actual checkout before searching outside this directory."
        return result
    if not terms:
        result["status"] = "no-terms"
        result["next_action"] = "Provide two or more stable UI labels from the screenshot."
        return result
    if shutil.which("rg") is None:
        result["status"] = "missing-ripgrep"
        result["next_action"] = "Install ripgrep or use an approved repository-native search tool."
        return result

    pattern = "|".join(re.escape(term) for term in terms)
    command = ["rg", "-n", "-i", "--no-heading", "--color", "never"]
    for glob in EXCLUDED_GLOBS:
        command.extend(["--glob", glob])
    command.extend([pattern, str(repo)])
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode not in (0, 1):
        result["status"] = "search-error"
        result["error"] = completed.stderr.strip()
        return result

    by_file: dict[str, dict] = {}
    for raw in completed.stdout.splitlines()[:max_hits]:
        match = re.match(r"^(.*?):(\d+):(.*)$", raw)
        if not match:
            continue
        absolute = Path(match.group(1))
        try:
            relative = str(absolute.relative_to(repo))
        except ValueError:
            relative = str(absolute)
        text = match.group(3).strip()
        matched_terms = [term for term in terms if term.casefold() in text.casefold()]
        hit = {
            "file": relative,
            "line": int(match.group(2)),
            "text": text,
            "matched_terms": matched_terms,
        }
        result["hits"].append(hit)
        candidate = by_file.setdefault(relative, {"file": relative, "hit_count": 0, "matched_terms": set()})
        candidate["hit_count"] += 1
        candidate["matched_terms"].update(matched_terms)

    candidates = []
    for candidate in by_file.values():
        candidates.append({
            "file": candidate["file"],
            "hit_count": candidate["hit_count"],
            "matched_terms": sorted(candidate["matched_terms"], key=str.casefold),
            "distinct_term_count": len(candidate["matched_terms"]),
        })
    candidates.sort(key=lambda item: (-item["distinct_term_count"], -item["hit_count"], item["file"]))
    result["candidate_files"] = candidates
    result["status"] = "candidates-found" if candidates else "no-matches"
    if not candidates:
        result["next_action"] = (
            "Search localization keys, route/menu concepts, runtime-provided labels, sibling packages, and generated sources."
        )
    return result


def render_text(result: dict) -> str:
    lines = [f"status: {result['status']}", f"repository: {result['repository']}"]
    for candidate in result.get("candidate_files", []):
        terms = ", ".join(candidate["matched_terms"])
        lines.append(
            f"{candidate['file']} | terms={candidate['distinct_term_count']} | "
            f"hits={candidate['hit_count']} | {terms}"
        )
    if result.get("next_action"):
        lines.append(f"next: {result['next_action']}")
    if result.get("error"):
        lines.append(f"error: {result['error']}")
    return "\n".join(lines)


def parser() -> argparse.ArgumentParser:
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--repo", required=True, type=Path)
    arg_parser.add_argument("--term", action="append", default=[])
    arg_parser.add_argument("--max-hits", type=int, default=500)
    arg_parser.add_argument("--format", choices=("json", "text"), default="json")
    return arg_parser


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    result = search(args.repo.resolve(), args.term, max_hits=args.max_hits)
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(render_text(result))
    return 1 if result["status"] in {"missing-ripgrep", "search-error"} else 0


if __name__ == "__main__":
    sys.exit(main())
