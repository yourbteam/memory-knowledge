#!/usr/bin/env python3
"""Dependency-free validation for the managed Codex skill tree."""
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
JUNK = {".DS_Store", "__pycache__"}
NON_STRING = re.compile(r"^(?:null|~|true|false|[-+]?\d+(?:\.\d+)?)$", re.IGNORECASE)


def frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text().splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing opening frontmatter fence")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError("missing closing frontmatter fence") from exc
    result: dict[str, str] = {}
    i = 1
    while i < end:
        line = lines[i]
        if not line.strip() or line.startswith((" ", "\t")):
            i += 1; continue
        match = re.match(r"^([A-Za-z_][\w-]*):(?:\s*(.*))?$", line)
        if not match:
            raise ValueError(f"unsupported frontmatter syntax at line {i + 1}")
        key, value = match.group(1), (match.group(2) or "").strip()
        if key in result: raise ValueError(f"duplicate frontmatter key: {key}")
        if value == "|":
            block = []; i += 1
            while i < end and (not lines[i].strip() or lines[i].startswith((" ", "\t"))):
                block.append(lines[i].lstrip()); i += 1
            result[key] = "\n".join(block).strip(); continue
        if value.startswith(("[", "{", ">", "&", "*", "!")):
            raise ValueError(f"unsupported value for {key}")
        quoted = len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'"
        if not quoted and NON_STRING.fullmatch(value): raise ValueError(f"{key} must be a string scalar")
        result[key] = value[1:-1] if quoted else value
        i += 1
    return result


def validate_openai(path: Path) -> list[str]:
    errors = []
    if not path.exists(): return errors
    values = {}; policy = {}; sections = set(); current = None; lines = path.read_text().splitlines()
    for number, line in enumerate(lines, 1):
        if not line.strip() or line.lstrip().startswith("#"): continue
        if not line.startswith((" ", "\t")):
            match = re.fullmatch(r"([A-Za-z_][\w-]*):", line)
            if not match:
                errors.append(f"{path}:{number}: top-level sections must be empty mappings"); current = None; continue
            current = match.group(1)
            if current not in {"interface", "policy"}:
                errors.append(f"{path}:{number}: unknown top-level section {current}")
            if current in sections:
                errors.append(f"{path}:{number}: duplicate top-level section {current}")
            sections.add(current)
            continue
        match = re.fullmatch(r"  ([A-Za-z_][\w-]*):\s*(.+)", line)
        if current == "policy":
            if not match:
                errors.append(f"{path}:{number}: policy values must be non-empty scalars"); continue
            key, value = match.group(1), match.group(2).strip()
            if key != "allow_implicit_invocation":
                errors.append(f"{path}:{number}: unknown policy key {key}"); continue
            if key in policy: errors.append(f"{path}:{number}: duplicate policy key {key}")
            if value not in {"true", "false"}:
                errors.append(f"{path}:{number}: policy.{key} must be an unquoted YAML boolean")
            policy[key] = value
            continue
        if current != "interface" or not match:
            errors.append(f"{path}:{number}: interface values must be non-empty scalars"); continue
        key, value = match.group(1), match.group(2).strip()
        if key in values: errors.append(f"{path}:{number}: duplicate interface key {key}")
        if value.startswith(("[", "{", "|", ">", "&", "*", "!")): errors.append(f"{path}:{number}: unsupported interface value")
        quoted = len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'"
        if not quoted and NON_STRING.fullmatch(value): errors.append(f"{path}:{number}: interface value must be a string")
        values[key] = value[1:-1] if quoted else value
    if "interface" not in sections: errors.append(f"{path}: missing interface section")
    for key in ("display_name", "short_description", "default_prompt"):
        if not values.get(key): errors.append(f"{path}: missing interface.{key}")
    if "policy" in sections and "allow_implicit_invocation" not in policy:
        errors.append(f"{path}: missing policy.allow_implicit_invocation")
    return errors


def validate(root: Path, manifest: Path) -> list[str]:
    errors = []
    names = [line.strip() for line in manifest.read_text().splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if len(names) != len(set(names)): errors.append(f"{manifest}: duplicate entries")
    for name in names:
        skill = root / name
        if not skill.is_dir(): errors.append(f"{skill}: managed directory missing"); continue
        for item in skill.rglob("*"):
            if item.name in JUNK or item.name.endswith((".pyc", ".bak")) or ".bak." in item.name:
                errors.append(f"{item}: generated/backup artifact is not allowed")
        if name == "_shared":
            helpers = list(skill.glob("*.py"))
            if not helpers: errors.append(f"{skill}: _shared must contain at least one Python helper")
            for helper in helpers:
                try: ast.parse(helper.read_text(), filename=str(helper))
                except SyntaxError as exc: errors.append(f"{helper}:{exc.lineno}: {exc.msg}")
            continue
        doc = skill / "SKILL.md"
        if not doc.exists(): errors.append(f"{doc}: missing"); continue
        try: data = frontmatter(doc)
        except ValueError as exc: errors.append(f"{doc}: {exc}"); continue
        if data.get("name") != name: errors.append(f"{doc}: name must equal directory name")
        if not NAME.fullmatch(data.get("name", "")): errors.append(f"{doc}: invalid name")
        if not data.get("description", "").strip(): errors.append(f"{doc}: description is required")
        errors.extend(validate_openai(skill / "agents" / "openai.yaml"))
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--skills-root", type=Path, required=True); ap.add_argument("--manifest", type=Path)
    args = ap.parse_args(); manifest = args.manifest or args.skills_root / "managed-skills.txt"
    errors = validate(args.skills_root, manifest)
    if errors:
        print("\n".join(errors), file=sys.stderr); return 1
    print(f"PASS validated managed skills from {manifest}"); return 0


if __name__ == "__main__": raise SystemExit(main())
