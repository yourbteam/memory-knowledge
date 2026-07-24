#!/usr/bin/env python3
"""Deterministic client-skill projection manifest: generate, build, and check.

The canonical repository is the only authority. This tool binds every managed skill
to exactly one parity disposition, stages client outputs deterministically, and
fails closed when canonical inputs drift from the recorded projection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

DISPOSITIONS = {"SHARED_IDENTICAL", "GENERATED_CLIENT_PROJECTION", "CLIENT_NOT_APPLICABLE", "BLOCKED"}
INSTALLABLE = {"SHARED_IDENTICAL", "GENERATED_CLIENT_PROJECTION"}
CLIENTS = ("codex", "claude")
SCENARIO_GROUPS = {
    "CAP-GOVERNANCE", "CAP-PDI", "CAP-VERIFY", "CAP-PERSONAS",
    "CAP-OPERATIONS", "CAP-REMOTE", "CAP-MEMORY", "CAP-SHARED",
}


def tree_hash(path: Path) -> str | None:
    if not path.exists(): return None
    h = hashlib.sha256()
    for item in sorted(p for p in path.rglob("*") if p.is_file()):
        h.update(item.relative_to(path).as_posix().encode() + b"\0"); h.update(item.read_bytes())
    return h.hexdigest()


def manifest_names(manifest: Path) -> list[str]:
    return [x.strip() for x in manifest.read_text().splitlines() if x.strip() and not x.lstrip().startswith("#")]


def load_projections(path: Path) -> dict:
    data = json.loads(path.read_text())
    if data.get("schema_version") != 1: raise SystemExit(f"{path}: unsupported schema_version")
    if not isinstance(data.get("entries"), dict): raise SystemExit(f"{path}: entries must be an object")
    return data


def structural_errors(entries: dict, names: list[str]) -> list[str]:
    errors = []
    missing = sorted(set(names) - set(entries))
    stale = sorted(set(entries) - set(names))
    if missing: errors.append("managed skills lack a parity disposition: " + ", ".join(missing))
    if stale: errors.append("projection entries are not managed: " + ", ".join(stale))
    for name in sorted(set(entries) & set(names)):
        row = entries[name]
        disposition = row.get("disposition")
        if disposition not in DISPOSITIONS:
            errors.append(f"{name}: invalid disposition {disposition!r}"); continue
        groups = row.get("scenario_groups")
        if not groups or not isinstance(groups, list) or not set(groups) <= SCENARIO_GROUPS:
            errors.append(f"{name}: scenario_groups must name at least one known CAP-* group")
        targets = row.get("targets")
        if not targets or not isinstance(targets, list) or not set(targets) <= set(CLIENTS):
            errors.append(f"{name}: targets must be a non-empty subset of {CLIENTS}")
        if disposition == "GENERATED_CLIENT_PROJECTION":
            if not row.get("generator") or not row.get("generator_sha256") or not row.get("divergence_reason"):
                errors.append(f"{name}: generated projection requires generator, generator_sha256, divergence_reason")
        if disposition == "CLIENT_NOT_APPLICABLE" and not row.get("divergence_reason"):
            errors.append(f"{name}: client-not-applicable requires an evidence-backed divergence_reason")
        if disposition in INSTALLABLE and not row.get("canonical_tree_sha256"):
            errors.append(f"{name}: installable disposition requires canonical_tree_sha256")
    return errors


def currency_errors(skills_root: Path, entries: dict, names: list[str]) -> list[str]:
    errors = []
    for name in names:
        row = entries.get(name)
        if not row or row.get("disposition") not in INSTALLABLE: continue
        live = tree_hash(skills_root / name)
        if live is None: errors.append(f"{name}: canonical tree missing from {skills_root}")
        elif live != row.get("canonical_tree_sha256"):
            errors.append(f"{name}: canonical tree changed after projection "
                          f"(manifest {row.get('canonical_tree_sha256')}, live {live})")
    return errors


def generate(skills_root: Path, manifest: Path, projections_path: Path) -> int:
    names = manifest_names(manifest)
    data = load_projections(projections_path) if projections_path.exists() else {"schema_version": 1, "entries": {}}
    entries = data["entries"]
    missing = sorted(set(names) - set(entries))
    if missing:
        print("generate refused; assign a disposition first for: " + ", ".join(missing), file=sys.stderr); return 1
    for name in names:
        row = entries[name]
        if row["disposition"] not in INSTALLABLE:
            row["canonical_tree_sha256"] = tree_hash(skills_root / name); row["projected_tree_sha256"] = None; continue
        live = tree_hash(skills_root / name)
        if live is None:
            print(f"{name}: canonical tree missing from {skills_root}", file=sys.stderr); return 1
        row["canonical_tree_sha256"] = live
        if row["disposition"] == "SHARED_IDENTICAL":
            row["projected_tree_sha256"] = live
        # GENERATED_CLIENT_PROJECTION recomputes projected_tree_sha256 during build.
    errors = structural_errors(entries, names)
    if errors:
        print("\n".join(errors), file=sys.stderr); return 1
    data["entries"] = {name: entries[name] for name in sorted(entries)}
    projections_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print(f"generated {projections_path} for {len(names)} managed skills"); return 0


def build(skills_root: Path, manifest: Path, projections_path: Path, client: str, staging_root: Path) -> int:
    names = manifest_names(manifest)
    data = load_projections(projections_path)
    errors = structural_errors(data["entries"], names) + currency_errors(skills_root, data["entries"], names)
    if errors:
        print("\n".join(errors), file=sys.stderr); return 1
    if staging_root.exists() and any(staging_root.iterdir()):
        print(f"staging root {staging_root} is not empty", file=sys.stderr); return 1
    staging_root.mkdir(parents=True, exist_ok=True)
    staged, skipped, blocked = [], [], []
    for name in names:
        row = data["entries"][name]
        if client not in row["targets"] or row["disposition"] == "CLIENT_NOT_APPLICABLE":
            skipped.append(name); continue
        if row["disposition"] == "BLOCKED":
            blocked.append(name); continue
        if row["disposition"] == "GENERATED_CLIENT_PROJECTION":
            print(f"{name}: no generator is registered for {row.get('generator')}", file=sys.stderr); return 1
        shutil.copytree(skills_root / name, staging_root / name)
        produced = tree_hash(staging_root / name)
        if produced != row["projected_tree_sha256"]:
            print(f"{name}: staged tree {produced} does not match projected {row['projected_tree_sha256']}",
                  file=sys.stderr); return 1
        staged.append({"name": name, "projected_tree_sha256": produced})
    if blocked:
        print("blocked entries prevent a complete build: " + ", ".join(blocked), file=sys.stderr); return 1
    report = {"schema_version": 1, "client": client, "staging_root": str(staging_root),
              "staged": staged, "skipped_not_applicable": skipped}
    (staging_root / "projection-build.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"staged {len(staged)} projections for {client} into {staging_root}"); return 0


def check(skills_root: Path, manifest: Path, projections_path: Path, client: str,
          installed_root: Path | None, report_path: Path | None) -> int:
    names = manifest_names(manifest)
    data = load_projections(projections_path)
    errors = structural_errors(data["entries"], names) + currency_errors(skills_root, data["entries"], names)
    rows, unmanaged = [], []
    if installed_root is not None:
        for name in names:
            row = data["entries"].get(name) or {}
            expected = row.get("projected_tree_sha256")
            applicable = row.get("disposition") in INSTALLABLE and client in (row.get("targets") or [])
            installed = tree_hash(installed_root / name)
            if not applicable:
                state = "NOT_APPLICABLE" if installed is None else "UNEXPECTED_PRESENT"
            elif installed is None: state = "MISSING"
            elif installed == expected: state = "MATCH"
            else: state = "DRIFT"
            rows.append({"name": name, "disposition": row.get("disposition"), "state": state,
                         "projected_tree_sha256": expected, "installed_tree_sha256": installed})
        if installed_root.exists():
            unmanaged = sorted(p.name for p in installed_root.iterdir() if p.is_dir() and p.name not in set(names))
    bad_states = [r for r in rows if r["state"] not in {"MATCH", "NOT_APPLICABLE"}]
    report = {"schema_version": 1, "client": client, "skills_root": str(skills_root),
              "installed_root": str(installed_root) if installed_root else None,
              "manifest_errors": errors, "rows": rows, "unmanaged_installed": unmanaged,
              "parity": not errors and not bad_states}
    if report_path: report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    for error in errors: print(f"ERROR   {error}")
    for r in rows:
        if r["state"] != "MATCH": print(f"{r['state']:<18} {r['name']}")
    for name in unmanaged: print(f"UNMANAGED          {name} (preserved, not installed by parity)")
    counts = {}
    for r in rows: counts[r["state"]] = counts.get(r["state"], 0) + 1
    print(f"parity={'PASS' if report['parity'] else 'FAIL'} client={client} "
          + " ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 0 if report["parity"] else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["generate", "build", "check"])
    ap.add_argument("--skills-root", type=Path, default=Path(__file__).resolve().parent.parent / "skills")
    ap.add_argument("--manifest", type=Path)
    ap.add_argument("--projections", type=Path, default=Path(__file__).resolve().with_name("client-skill-projections.json"))
    ap.add_argument("--client", choices=list(CLIENTS))
    ap.add_argument("--staging-root", type=Path)
    ap.add_argument("--installed-root", type=Path)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args()
    manifest = args.manifest or args.skills_root / "managed-skills.txt"
    if args.command == "generate":
        return generate(args.skills_root.resolve(), manifest.resolve(), args.projections.resolve())
    if not args.client: raise SystemExit(f"{args.command} requires --client")
    if args.command == "build":
        if not args.staging_root: raise SystemExit("build requires --staging-root")
        return build(args.skills_root.resolve(), manifest.resolve(), args.projections.resolve(),
                     args.client, args.staging_root.resolve())
    installed = args.installed_root.resolve() if args.installed_root else None
    return check(args.skills_root.resolve(), manifest.resolve(), args.projections.resolve(),
                 args.client, installed, args.report)


if __name__ == "__main__": raise SystemExit(main())
