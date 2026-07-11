#!/usr/bin/env python3
"""Generate and safely publish projections of canonical DIRECTIVES.md."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import os
import re
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_DIRECTIVES = ROOT / "DIRECTIVES.md"
DEFAULT_ALLOWLIST = ROOT / "codex-projects.allowlist"
LOCK_ROOT = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "kamen-working-agreement-projections"
GENERATED_HEADER = "<!-- GENERATED from working-agreement/DIRECTIVES.md — do not edit here.\n     Edit DIRECTIVES.md (the single source of truth) and regenerate via\n     working-agreement/generate_projections.py. -->\n"
MERGE_BEGIN = "<!-- BEGIN GENERATED WORKING-AGREEMENT DIRECTIVES (generate_projections.py --append-to) -->"
MERGE_END = "<!-- END GENERATED WORKING-AGREEMENT DIRECTIVES -->"
BLOCK = re.compile(re.escape(MERGE_BEGIN) + r".*?" + re.escape(MERGE_END) + r"\n?", re.DOTALL)


def read_directives(path: Path) -> str:
    text = path.read_text()
    if "## G" not in text: raise ValueError(f"{path} has no G-rule headings")
    return text


def agents_projection(text: str) -> str: return f"{GENERATED_HEADER}\n{text.rstrip()}\n"


def claude_pointer() -> str:
    return (GENERATED_HEADER + "\n# Working agreement\n\n"
            "The authoritative directives live in `working-agreement/DIRECTIVES.md` and the\n"
            "memory-knowledge brain. Claude receives them through `inject-directives.sh`.\n"
            "This generated pointer is not authoritative and must not contain hand-authored rules.\n")


def render(kind: str, directives: Path) -> str:
    if kind == "agents": return agents_projection(read_directives(directives))
    if kind == "claude-pointer": return claude_pointer()
    raise ValueError(f"unknown projection kind: {kind}")


def merge_block(text: str) -> str:
    return f"{MERGE_BEGIN}\n\n{GENERATED_HEADER}\n{readable(text)}\n\n{MERGE_END}\n"


def readable(text: str) -> str: return text.rstrip()


def merge_into(existing: str, directives: str) -> str:
    block = merge_block(directives)
    if BLOCK.search(existing): return BLOCK.sub(block, existing)
    return existing.rstrip() + "\n\n" + block


def refresh_agents_file(existing: str, directives: str) -> str | None:
    if MERGE_BEGIN in existing: return merge_into(existing, directives)
    if existing.lstrip().startswith(GENERATED_HEADER.splitlines()[0]) and "## G0" in existing:
        return agents_projection(directives)
    return None


def codex_trusted_projects(config: Path) -> list[Path]:
    if not config.exists(): return []
    return [Path(m.group(1)).resolve() for line in config.read_text().splitlines() if (m := re.match(r'\[projects\."(.+)"\]\s*$', line.strip()))]


def allowed_projects(path: Path) -> list[Path]:
    return [Path(line.strip()).expanduser().resolve() for line in path.read_text().splitlines() if line.strip() and not line.lstrip().startswith("#")]


@contextmanager
def target_lock(target: Path):
    lock = LOCK_ROOT / (hashlib.sha256(str(target.resolve()).encode()).hexdigest() + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def sha(data: bytes) -> str: return hashlib.sha256(data).hexdigest()


def fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def publish_new(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=".AGENTS.md.", dir=target.parent)
    tmp = Path(raw)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(content); handle.flush(); os.fsync(handle.fileno())
        try: os.link(tmp, target)
        except FileExistsError: raise RuntimeError(f"target appeared during create: {target}")
        fsync_directory(target.parent)
    finally:
        tmp.unlink(missing_ok=True)


def refresh_one(project: Path, directives: str, *, apply: bool, create_missing: bool) -> str:
    target = project / "AGENTS.md"
    with target_lock(target):
        if not target.exists():
            if not create_missing: return f"skip(no-AGENTS.md): {project}"
            if apply:
                try: publish_new(target, agents_projection(directives))
                except RuntimeError: return f"skip(raced-existing): {project}"
                return f"created: {project}"
            return f"would-create: {project}"
        before = target.read_bytes(); existing = before.decode()
        new = refresh_agents_file(existing, directives)
        if new is None: return f"skip(not-generated): {project}"
        if new.encode() == before: return f"skip(up-to-date): {project}"
        if not apply: return f"would-refresh: {project}"
        if not target.exists() or sha(target.read_bytes()) != sha(before):
            raise RuntimeError(f"target changed while locked: {target}")
        fd, raw = tempfile.mkstemp(prefix=".AGENTS.md.", dir=target.parent)
        with os.fdopen(fd, "w") as handle:
            handle.write(new); handle.flush(); os.fsync(handle.fileno())
        os.replace(raw, target)
        fsync_directory(target.parent)
        return f"refreshed: {project}"


def refresh_projects(directives: Path, projects: list[Path], allowlist: Path, *, apply: bool, create_missing: bool) -> list[str]:
    allowed = set(allowed_projects(allowlist)); text = read_directives(directives); results = []
    for project in projects:
        resolved = project.resolve()
        if resolved not in allowed: results.append(f"skip(not-allowlisted): {resolved}"); continue
        if not resolved.exists() or not resolved.is_dir(): results.append(f"skip(no-directory): {resolved}"); continue
        if not os.access(resolved, os.W_OK): results.append(f"skip(not-writable): {resolved}"); continue
        results.append(refresh_one(resolved, text, apply=apply, create_missing=create_missing))
    return results


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--kind", choices=["agents", "claude-pointer"]); ap.add_argument("--directives", type=Path, default=DEFAULT_DIRECTIVES)
    ap.add_argument("--write", type=Path); ap.add_argument("--append-to", type=Path); ap.add_argument("--refresh-trusted", action="store_true")
    ap.add_argument("--codex-config", type=Path, default=Path.home()/".codex/config.toml"); ap.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    ap.add_argument("--create-missing", action="store_true"); ap.add_argument("--create-at", type=Path, action="append", default=[]); ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if args.refresh_trusted or args.create_at:
        projects = codex_trusted_projects(args.codex_config) if args.refresh_trusted else []
        projects.extend(p.parent if p.name == "AGENTS.md" else p for p in args.create_at)
        for line in refresh_projects(args.directives, list(dict.fromkeys(projects)), args.allowlist, apply=args.apply, create_missing=args.create_missing or bool(args.create_at)):
            print(line, file=sys.stderr)
        return 0
    if not args.kind: ap.error("--kind is required")
    if args.append_to:
        if args.kind != "agents" or not args.append_to.exists(): ap.error("--append-to requires an existing agents target")
        with target_lock(args.append_to):
            before = args.append_to.read_bytes(); new = merge_into(before.decode(), read_directives(args.directives))
            if args.apply:
                if sha(args.append_to.read_bytes()) != sha(before): raise SystemExit("skip(raced-existing)")
                fd, raw = tempfile.mkstemp(prefix=".AGENTS.md.", dir=args.append_to.parent)
                with os.fdopen(fd, "w") as handle: handle.write(new); handle.flush(); os.fsync(handle.fileno())
                os.replace(raw, args.append_to); fsync_directory(args.append_to.parent)
            else: sys.stdout.write(new)
        return 0
    content = render(args.kind, args.directives)
    if args.write and args.apply:
        with target_lock(args.write):
            if args.write.exists(): raise SystemExit("--write refuses existing targets")
            publish_new(args.write, content)
    else: sys.stdout.write(content)
    return 0


if __name__ == "__main__": raise SystemExit(main())
