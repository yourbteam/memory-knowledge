#!/usr/bin/env python3
"""Zero-argument numbered launcher for the durable Atlas workspace."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, os.fspath(HERE))
import atlas_workspace as workspace  # noqa: E402


def _ask(label: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or (default or "")


def main() -> int:
    print("Atlas workspace")
    print("1. Prepare or resume workspace")
    print("2. Read workspace status")
    print("3. Publish an independently reviewed route map")
    print("4. Correct a rejected map")
    print("5. Publish a review directory")
    choice = _ask("Choose 1-5")
    try:
        if choice == "1":
            state = _ask("Durable state directory")
            repo = _ask("Target checkout")
            project = _ask("Repository-relative project path")
            framework = _ask("Target framework")
            interface = _ask("Exact fully qualified source interface")
            seed = _ask("Historical seed database path, or 'none'")
            if seed.lower() == "none":
                seed = ""
            dotnet = os.environ.get("ATLAS_DOTNET", "").strip()
            if not dotnet:
                dotnet = _ask(".NET SDK executable")
            result = workspace.prepare(repo, state, project, framework, interface, dotnet, seed or None)
        elif choice == "2":
            state = _ask("Durable state directory")
            result = workspace.status(state)
        elif choice == "3":
            state = _ask("Durable state directory")
            route_id = _ask("Prepared route fact ID")
            review = _ask("Independent Sol review JSON path")
            result = workspace.publish(state, route_id, review)
        elif choice == "4":
            state = _ask("Durable state directory")
            route_id = _ask("Rejected route fact ID")
            draft = _ask("Corrected route-map draft JSON path")
            result = workspace.correct(state, route_id, draft)
        elif choice == "5":
            state = _ask("Durable state directory")
            review_dir = _ask("Directory of independent Sol review JSON files")
            result = workspace.publish_reviews(state, review_dir)
        else:
            raise workspace.WorkspaceError("choose one listed option: 1, 2, 3, 4, or 5")
    except (workspace.WorkspaceError, OSError, ValueError) as exc:
        print(f"Atlas workspace refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
