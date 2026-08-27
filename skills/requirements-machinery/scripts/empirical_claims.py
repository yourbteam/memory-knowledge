#!/usr/bin/env python3
"""Inventory empirical design claims and validate their replayable dispositions."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


CLAIM_PATTERN = re.compile(
    r"\b(?:won (?:a |the |on )|chosen by comparison|champion of|promoted(?: by| merge| dedupe)|"
    r"proved|proven (?:rather than assumed|clean)|measured (?:on|before|over|and rejected|size|without)|"
    r"comparison (?:against|had already shown)|experiment machinery compared|shape that won)\b",
    re.IGNORECASE,
)
SCANNED_SUFFIXES = {".md", ".py"}


class Invalid(RuntimeError):
    pass


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_file(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def discover(skill_root: Path) -> list[dict]:
    claims = []
    for path in sorted(skill_root.rglob("*")):
        relative = path.relative_to(skill_root)
        if (not path.is_file() or path.suffix not in SCANNED_SUFFIXES
                or relative.parts[0] == "evidence"
                or relative.as_posix() == "scripts/empirical_claims.py"):
            continue
        for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            text = raw.strip()
            if not text or not CLAIM_PATTERN.search(text):
                continue
            identity = f"{relative.as_posix()}:{line_number}:{digest_bytes(text.encode())}"
            claims.append({
                "id": f"EC-{digest_bytes(identity.encode())[:16]}",
                "source": relative.as_posix(), "line": line_number, "text": text,
                "text_sha256": digest_bytes(text.encode()),
            })
    return claims


def manifest_body(claims: list[dict]) -> dict:
    entries = [{**claim, "disposition": "unverified",
                "reason": "Historical raw outputs and environment identity are absent; no replayable evidence is claimed."}
               for claim in claims]
    return {"schema_version": 1, "claim_detection": CLAIM_PATTERN.pattern,
            "claims_fingerprint": digest_bytes(canonical(claims)), "claims": entries}


def write_inventory(skill_root: Path, output: Path) -> dict:
    body = manifest_body(discover(skill_root))
    document = {**body, "manifest_sha256": digest_bytes(canonical(body))}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return document


def evidence_path(skill_root: Path, reference: dict, label: str) -> Path:
    try:
        relative = Path(reference["path"])
        expected = reference["sha256"]
    except (KeyError, TypeError) as exc:
        raise Invalid(f"{label} has no complete path/hash identity") from exc
    if relative.is_absolute():
        raise Invalid(f"{label} path must be repository-relative")
    resolved = (skill_root / relative).resolve(strict=True)
    if skill_root != resolved and skill_root not in resolved.parents:
        raise Invalid(f"{label} escapes the skill evidence bundle")
    if digest_file(resolved) != expected:
        raise Invalid(f"{label} hash mismatch")
    return resolved


def validate_ledger(path: Path) -> list[dict]:
    entries = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not entries:
        raise Invalid("experiment ledger is empty")
    previous = None
    for sequence, entry in enumerate(entries, 1):
        recorded = entry.get("entry_sha256")
        payload = {key: value for key, value in entry.items() if key != "entry_sha256"}
        if entry.get("sequence") != sequence or entry.get("previous_entry_sha256") != previous:
            raise Invalid("experiment ledger chain mismatch")
        if recorded != digest_bytes(canonical(payload)):
            raise Invalid("experiment ledger entry hash mismatch")
        previous = recorded
    return entries


def lookup(value, pointer: str):
    current = value
    for part in pointer.split("."):
        if not isinstance(current, dict) or part not in current:
            raise Invalid(f"scorecard pointer is absent: {pointer}")
        current = current[part]
    return current


def validate_verified(skill_root: Path, entry: dict) -> dict:
    evidence = entry.get("evidence", {})
    required = ("experiment_spec", "frozen_input", "ledger", "summary", "scorecard")
    paths = {label: evidence_path(skill_root, evidence.get(label, {}), label) for label in required}
    spec = json.loads(paths["experiment_spec"].read_text(encoding="utf-8"))
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    scorecard = json.loads(paths["scorecard"].read_text(encoding="utf-8"))
    ledger = validate_ledger(paths["ledger"])
    if spec.get("experiment_id") != summary.get("experiment_id"):
        raise Invalid("experiment identity mismatch")
    if spec.get("frozen_input", {}).get("sha256") != digest_file(paths["frozen_input"]):
        raise Invalid("frozen input identity mismatch")
    variants = [variant.get("id") for variant in spec.get("variants", [])]
    criteria = scorecard.get("criteria", [])
    if len(variants) < 2 or not criteria or not spec.get("hypothesis"):
        raise Invalid("experiment lacks competing variants, hypothesis, or declared criteria")
    if [metric.get("name") for metric in spec.get("evaluation", {}).get("metrics", [])] != [item.get("name") for item in criteria]:
        raise Invalid("scorecard criteria differ from the frozen specification")
    environment = scorecard.get("environment_identity", {})
    if not all(environment.get(key) for key in ("runtime", "platform", "captured_at")):
        raise Invalid("environment identity is incomplete")
    raw = scorecard.get("raw_outputs", {})
    declared_scores = scorecard.get("scores", {})
    replayed = {}
    for variant in variants:
        if variant not in raw:
            raise Invalid(f"raw output missing for {variant}")
        replayed[variant] = {}
        for criterion in criteria:
            replayed[variant][criterion["name"]] = float(
                lookup(raw[variant], criterion["pointer"]) == criterion["expected"])
    if replayed != declared_scores:
        raise Invalid("stored scores do not replay from raw outputs")
    summary_scores = {item["variant_id"]: item["metrics"] for item in summary.get("variants", [])}
    if summary_scores != replayed:
        raise Invalid("summary scores differ from replayed scores")
    finished = {item["variant_id"]: item["metrics"] for item in ledger if item.get("event") == "variant_finished"}
    if finished != replayed:
        raise Invalid("ledger scores differ from replayed scores")
    decision = scorecard.get("promotion_decision", {})
    if decision.get("automatic") is not False or "applied" not in decision or not decision.get("recommended"):
        raise Invalid("non-automatic promotion decision is absent")
    return {"claim": entry["id"], "variants": len(variants), "criteria": len(criteria)}


def validate(skill_root: Path, manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    recorded_hash = manifest.get("manifest_sha256")
    body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if recorded_hash != digest_bytes(canonical(body)):
        raise Invalid("claim manifest hash mismatch")
    current = discover(skill_root)
    current_index = {claim["id"]: claim for claim in current}
    recorded = manifest.get("claims", [])
    recorded_index = {claim.get("id"): claim for claim in recorded}
    if len(recorded_index) != len(recorded):
        raise Invalid("duplicate claim identity")
    missing = sorted(set(current_index) - set(recorded_index))
    stale = sorted(set(recorded_index) - set(current_index))
    if missing or stale:
        raise Invalid(f"claim inventory drift: missing={missing}, stale={stale}")
    if manifest.get("claims_fingerprint") != digest_bytes(canonical(current)):
        raise Invalid("claim inventory fingerprint mismatch")
    skill_root = skill_root.resolve()
    verified, unverified = [], []
    identity_fields = ("source", "line", "text", "text_sha256")
    for claim_id, claim in recorded_index.items():
        if any(claim.get(field) != current_index[claim_id].get(field) for field in identity_fields):
            raise Invalid(f"claim source identity drift: {claim_id}")
        if claim.get("disposition") == "verified":
            verified.append(validate_verified(skill_root, claim))
        elif claim.get("disposition") == "unverified":
            if len(claim.get("reason", "")) < 20 or claim.get("evidence"):
                raise Invalid(f"unverified disposition is incomplete: {claim_id}")
            unverified.append(claim_id)
        else:
            raise Invalid(f"unknown claim disposition: {claim_id}")
    return {"status": "valid", "claims": len(recorded), "verified": len(verified),
            "unverified": len(unverified), "missing": 0, "verified_replays": verified}


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    inventory = sub.add_parser("inventory")
    inventory.add_argument("--skill-root", type=Path, required=True)
    inventory.add_argument("--out", type=Path, required=True)
    check = sub.add_parser("validate")
    check.add_argument("--skill-root", type=Path, required=True)
    check.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "inventory":
            result = write_inventory(args.skill_root, args.out)
            print(json.dumps({"status": "written", "claims": len(result["claims"]), "path": str(args.out)}, sort_keys=True))
        else:
            manifest = args.manifest or args.skill_root / "evidence" / "empirical-claims.json"
            print(json.dumps(validate(args.skill_root, manifest), sort_keys=True))
    except (Invalid, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"empirical evidence refuses: {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
