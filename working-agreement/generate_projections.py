#!/usr/bin/env python3
"""Generate tool-facing projections of the authoritative DIRECTIVES.md.

`DIRECTIVES.md` is the single source of truth for the working agreement. This script
regenerates the *disposable* projections that deliver it to each AI tool, so no projection
is ever hand-authored:

  - **Codex `AGENTS.md`** — Codex loads `AGENTS.md` from the repo tree, so the directives
    reach Codex by projecting them into a per-location `AGENTS.md`.
  - **Thin `CLAUDE.md` pointer** — Claude Code already gets the real directives via the
    `inject-directives.sh` hook; the on-disk `CLAUDE.md` is reduced to a non-authoritative
    pointer so it can never drift from the source.

For a repo that already has its own hand-authored `AGENTS.md`, use ``--append-to PATH`` to
merge the directives into a **fenced generated block** (between BEGIN/END markers) at the end
of that file: the repo's own guidance is preserved, the directives land directly in Codex
context, and re-running replaces only the block — so the generated section never drifts and is
never hand-edited.

Every projection carries a GENERATED header. Never hand-edit a projection — edit
`DIRECTIVES.md` and regenerate. Dry-run by default; pass --write PATH (overwrite) or
--append-to PATH (merge into a fenced block) to apply.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DEFAULT_DIRECTIVES = Path(__file__).resolve().parent / "DIRECTIVES.md"

GENERATED_HEADER = (
    "<!-- GENERATED from working-agreement/DIRECTIVES.md — do not edit here.\n"
    "     Edit DIRECTIVES.md (the single source of truth) and regenerate via\n"
    "     working-agreement/generate_projections.py. -->\n"
)

# Fence markers for --append-to: re-running replaces only the text between them, so a repo's
# own AGENTS.md content is preserved and the generated block never drifts or duplicates.
MERGE_BEGIN = "<!-- BEGIN GENERATED WORKING-AGREEMENT DIRECTIVES (generate_projections.py --append-to) -->"
MERGE_END = "<!-- END GENERATED WORKING-AGREEMENT DIRECTIVES -->"
_MERGE_BLOCK_RE = re.compile(
    re.escape(MERGE_BEGIN) + r".*?" + re.escape(MERGE_END) + r"\n?", re.DOTALL
)

CLAUDE_POINTER_BODY = (
    "# Working agreement\n\n"
    "The authoritative directives live in `working-agreement/DIRECTIVES.md` and the\n"
    "memory-knowledge brain. Claude Code receives them automatically via the\n"
    "`inject-directives.sh` UserPromptSubmit hook. Do not author rules in this file —\n"
    "it is a generated pointer and is not authoritative.\n"
)


def read_directives(path: Path) -> str:
    text = path.read_text()
    if "## G" not in text:
        raise ValueError(f"{path} does not look like DIRECTIVES.md (no G-rule headings found)")
    return text


def agents_projection(directives_text: str) -> str:
    """Codex AGENTS.md: the full directives, prefixed with the generated header."""
    return f"{GENERATED_HEADER}\n{directives_text.rstrip()}\n"


def claude_pointer() -> str:
    """Thin, non-authoritative CLAUDE.md pointer."""
    return f"{GENERATED_HEADER}\n{CLAUDE_POINTER_BODY}"


def render(kind: str, directives_path: Path) -> str:
    if kind == "agents":
        return agents_projection(read_directives(directives_path))
    if kind == "claude-pointer":
        return claude_pointer()
    raise ValueError(f"Unknown kind: {kind!r} (expected 'agents' or 'claude-pointer')")


def merge_block(directives_text: str) -> str:
    """The fenced, regenerable directives block appended to a repo's own AGENTS.md."""
    return f"{MERGE_BEGIN}\n\n{GENERATED_HEADER}\n{directives_text.rstrip()}\n\n{MERGE_END}\n"


def merge_into(existing: str, directives_text: str) -> str:
    """Insert/replace the fenced directives block in `existing`, preserving all other content.

    Idempotent: if the block already exists it is replaced in place; otherwise it is appended
    after the repo's own content. Re-running never duplicates or drifts.
    """
    block = merge_block(directives_text)
    if _MERGE_BLOCK_RE.search(existing):
        return _MERGE_BLOCK_RE.sub(block, existing)
    base = existing.rstrip() + "\n"
    return f"{base}\n{block}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kind", required=True, choices=["agents", "claude-pointer"])
    ap.add_argument("--directives", type=Path, default=DEFAULT_DIRECTIVES)
    ap.add_argument("--write", type=Path, default=None, help="Target path to overwrite; omit for dry-run.")
    ap.add_argument(
        "--append-to", type=Path, default=None,
        help="Existing AGENTS.md to merge the directives into a fenced block (preserves its content).",
    )
    args = ap.parse_args()

    # Merge mode: fold the directives into an existing repo AGENTS.md without clobbering it.
    if args.append_to is not None:
        if args.kind != "agents":
            ap.error("--append-to only applies to --kind agents")
        if not args.append_to.exists():
            ap.error(f"--append-to target does not exist: {args.append_to}")
        merged = merge_into(args.append_to.read_text(), read_directives(args.directives))
        args.append_to.write_text(merged)
        sys.stderr.write(f"merged directives block -> {args.append_to}\n")
        return 0

    content = render(args.kind, args.directives)
    if args.write is None:
        sys.stdout.write(content)
        sys.stderr.write("\n[dry-run] nothing written — pass --write PATH to apply.\n")
        return 0
    args.write.write_text(content)
    sys.stderr.write(f"wrote {args.kind} projection -> {args.write}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
