#!/usr/bin/env python3
"""Persistent state and baseline guards for playbook convergence tasks."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
VERDICTS = {"PASS", "GAPS", "BLOCKED", "CAP_REACHED"}
STATUSES = {"research", "plan", "implementation", "review", "blocked", "cap_reached", "complete"}
KINDS = {"autonomy", "directive", "commit", "continue", "scope-change", "exclude", "resume"}
TRANSITIONS = {
    "research": {"plan", "blocked", "cap_reached"},
    "plan": {"implementation", "research", "blocked", "cap_reached"},
    "implementation": {"review", "research", "blocked", "cap_reached"},
    "review": {"research", "complete", "blocked", "cap_reached"},
    "blocked": {"research", "plan", "implementation", "review"},
    "cap_reached": {"research", "plan", "implementation", "review"},
    "complete": set(),
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_file(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def digest_tree(path: Path) -> str | None:
    if not path.exists():
        return None
    if path.is_file():
        return digest_file(path)
    h = hashlib.sha256()
    for item in sorted(p for p in path.rglob("*") if p.is_file() and p.name != ".DS_Store"):
        h.update(item.relative_to(path).as_posix().encode() + b"\0")
        h.update(item.read_bytes())
    return h.hexdigest()


def digest_managed(root: Path, children: list[str] | None) -> str | None:
    if not children: return digest_tree(root)
    h = hashlib.sha256()
    for child in sorted(children):
        value = digest_tree(root / child)
        h.update(child.encode() + b"\0" + str(value).encode() + b"\0")
    return h.hexdigest()


def atomic_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".convergence-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load(path: Path) -> dict:
    data = json.loads(path.read_text())
    if data.get("schema_version") != SCHEMA_VERSION:
        raise SystemExit("unsupported convergence state schema")
    return data


def save(path: Path, data: dict, message: str) -> int:
    data["updated_at"] = now()
    atomic_write(path, data)
    print(message)
    return 0


def task_id(source: Path, objective: str) -> str:
    identity = "file://" + str(source.resolve()) + "\n" + objective
    return str(uuid.uuid5(uuid.NAMESPACE_URL, identity))


def requirement_map(path: Path) -> dict:
    raw = json.loads(path.read_text())
    entries = raw.get("requirements", raw) if isinstance(raw, dict) else raw
    out = {}
    for item in entries:
        if not all(item.get(k) for k in ("id", "text", "source")):
            raise SystemExit("every requirement needs id, text, and source")
        out[item["id"]] = {**item, "status": item.get("status", "open")}
    if not out:
        raise SystemExit("requirements file is empty")
    return out


def git(repo: Path, *args: str, binary: bool = False):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False)
    if result.returncode:
        raise SystemExit(result.stderr.decode(errors="replace").strip())
    return result.stdout if binary else result.stdout.decode().strip()


def repo_snapshot(repo: Path) -> dict:
    return {
        "branch": git(repo, "branch", "--show-current"),
        "head": git(repo, "rev-parse", "HEAD"),
        "index_hash": digest_bytes(git(repo, "diff", "--cached", "--binary", binary=True)),
        "status_hash": digest_bytes(git(repo, "status", "--porcelain=v1", "-z", binary=True)),
    }


def repo_identity(repo: Path) -> dict:
    return {"branch": git(repo, "branch", "--show-current"), "head": git(repo, "rev-parse", "HEAD")}


def path_metadata(repo: Path, relative: str, state: str) -> dict:
    path = repo / relative; stat = path.lstat() if path.exists() else None
    index = git(repo, "ls-files", "-s", "--", relative)
    result = {"path": relative, "git_state": state, "mode": oct(stat.st_mode & 0o777) if stat else None,
              "size": stat.st_size if stat and path.is_file() else None,
              "working_hash": digest_file(path) if path.is_file() else None,
              "index_oid": index.split()[1] if index else None}
    if path.name == "AGENTS.md" and path.is_file():
        raw = path.read_text(errors="replace")
        begin, end = raw.find("<!-- BEGIN GENERATED WORKING-AGREEMENT"), raw.find("<!-- END GENERATED WORKING-AGREEMENT DIRECTIVES -->")
        if begin >= 0 and end >= begin:
            end += len("<!-- END GENERATED WORKING-AGREEMENT DIRECTIVES -->")
            result["generated_region"] = {"start": begin, "end": end,
                "generated_hash": digest_bytes(raw[begin:end].encode()),
                "non_generated_hash": digest_bytes((raw[:begin] + raw[end:]).encode())}
    return result


def status_records(repo: Path) -> list[tuple[str, str]]:
    raw = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all", binary=True)
    fields = raw.split(b"\0"); out = []; index = 0
    while index < len(fields) and fields[index]:
        record = fields[index].decode(errors="surrogateescape"); state, relative = record[:2], record[3:]
        out.append((state, relative))
        index += 2 if state[0] in {"R", "C"} else 1
    return out


def dirty_paths(repo: Path, allowed: list[str] | None = None) -> dict:
    return {relative: path_metadata(repo, relative, state) for state, relative in status_records(repo)
            if allowed is None or path_allowed(relative, allowed)}


def under(path: Path, root: Path) -> bool:
    try: path.resolve().relative_to(root.resolve()); return True
    except ValueError: return False


def path_allowed(relative: str, allowed: list[str]) -> bool:
    return any(relative == item or relative.startswith(item.rstrip("/") + "/") for item in allowed)


def allowed_fingerprints(repo: Path, allowed: list[str]) -> dict:
    return {relative: {
        "working_hash": digest_tree(repo / relative),
        "index_diff_hash": digest_bytes(git(repo, "diff", "--cached", "--binary", "--", relative, binary=True)),
    } for relative in allowed}


def blank_state(source: Path, objective: str, requirements: dict) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": task_id(source, objective),
        "objective": objective,
        "status": "research",
        "outer_iteration": 1,
        "requirements": requirements,
        "gaps": {}, "blockers": {}, "approvals": {},
        "repositories": {}, "managed_paths": {}, "stages": {}, "artifacts": {},
        "blocked_from_status": None, "blocked_stage": None,
        "cap_stage": None, "cap_attempt": None,
        "created_at": now(), "updated_at": now(),
    }


def cmd_init(args) -> int:
    path = Path(args.state)
    state = blank_state(Path(args.source), args.objective, requirement_map(Path(args.requirements_file)))
    if path.exists():
        current = load(path)
        if current["task_id"] != state["task_id"]:
            raise SystemExit("state path belongs to a different task")
        print(current["task_id"])
        return 0
    atomic_write(path, state)
    print(state["task_id"])
    return 0


def cmd_migrate(args) -> int:
    source, destination = Path(args.source), Path(args.destination)
    if destination.exists():
        print(load(destination)["task_id"])
        return 0
    legacy = json.loads(source.read_text())
    requirements = requirement_map(Path(args.requirements_file))
    legacy_ids = {item if isinstance(item, str) else item.get("id") for item in legacy.get("requirements", [])}
    if legacy_ids and legacy_ids != set(requirements):
        raise SystemExit("legacy requirement ids do not match complete requirements file")
    state = blank_state(source, legacy.get("objective", args.objective), requirements)
    approvals = legacy.get("approvals", [])
    if isinstance(approvals, dict): approvals = [{"id": key, "status": value} for key, value in approvals.items()]
    for index, value in enumerate(approvals, 1):
        approval_id = value.get("id", f"legacy-approval-{index}")
        legacy_scope = str(value.get("scope", ""))
        kind = "directive" if "directive" in legacy_scope.lower() or "g0" in legacy_scope.lower() else "autonomy"
        state["approvals"][approval_id] = {
            "status": "granted" if value.get("status") in (True, "approved", "granted") else value.get("status"),
            "scope": {"kind": kind, "operations": ["promote"] if kind == "directive" else ["edit"],
                      "target_ids": [], "repository_roots": [], "allowed_paths": [],
                      "stage": "migration", "outer_iteration": 1},
            "evidence": value.get("evidence"), "legacy_scope": legacy_scope,
        }
    for index, value in enumerate(legacy.get("blockers", []), 1):
        blocker_id = value.get("id", f"legacy-blocker-{index}")
        state["blockers"][blocker_id] = {
            "status": value.get("status", "open"), "stage": "legacy",
            "reason": value.get("symptom") or value.get("impact") or "legacy blocker",
            "required_evidence": value.get("unblock", "user or external evidence required"),
            "closure_evidence": value.get("closure_evidence"),
        }
    for index, value in enumerate(legacy.get("gaps", []), 1):
        gap_id = value.get("id", f"legacy-gap-{index}") if isinstance(value, dict) else f"legacy-gap-{index}"
        state["gaps"][gap_id] = {"requirement_ids": [], "source_stage": "legacy",
            "impact": value.get("impact", str(value)) if isinstance(value, dict) else str(value),
            "evidence": value.get("evidence") if isinstance(value, dict) else None,
            "status": value.get("status", "open") if isinstance(value, dict) else "open"}
    Path(args.backup).parent.mkdir(parents=True, exist_ok=True)
    if not Path(args.backup).exists():
        Path(args.backup).write_bytes(source.read_bytes())
    atomic_write(destination, state)
    print(state["task_id"])
    return 0


def cmd_init_baseline(args) -> int:
    path, state = Path(args.state), load(Path(args.state))
    for raw in args.repository:
        repo = Path(raw).resolve(); snap = repo_snapshot(repo)
        entry = state["repositories"].get(str(repo))
        if entry and entry["base_head"] != snap["head"]:
            if not args.adopt_current_head_before_mutation:
                raise SystemExit(f"immutable base differs: {repo}")
            state.setdefault("baseline_events", []).append({"kind": "pre-mutation-head-adoption",
                "repository": str(repo), "previous_base_head": entry["base_head"],
                "adopted_base_head": snap["head"], "evidence": args.adoption_evidence, "recorded_at": now()})
        allowed = sorted(str(Path(p).resolve().relative_to(repo)) for p in (args.allowed_path or []) if under(Path(p), repo))
        dirty = dirty_paths(repo, allowed); overlaps = {}
        for raw_overlap in args.overlap_path or []:
            overlap = Path(raw_overlap).resolve()
            if under(overlap, repo):
                relative = str(overlap.relative_to(repo))
                if relative in dirty and dirty[relative].get("generated_region"):
                    overlaps[relative] = dirty.pop(relative)
        state["repositories"][str(repo)] = {
            "base_head": snap["head"], "initial_snapshot": entry.get("initial_snapshot", snap) if entry else snap,
            "expected_identity": repo_identity(repo), "expected_allowed": allowed_fingerprints(repo, allowed),
            "allowed_paths": allowed, "commit_policy": args.commit_policy,
            "protected_dirty_paths": dirty,
            "authorized_dirty_overlaps": overlaps,
            "excluded_dirty_paths": {relative: {"path": relative, "git_state": status}
                for status, relative in status_records(repo) if not path_allowed(relative, allowed)},
        }
    for raw in args.managed_path:
        managed = Path(raw).resolve()
        children = sorted(str(Path(child).resolve().relative_to(managed)) for child in (args.managed_child or []) if under(Path(child), managed))
        current = digest_managed(managed, children)
        entry = state["managed_paths"].get(str(managed))
        if entry and entry["baseline_hash"] != current:
            raise SystemExit(f"immutable managed baseline differs: {managed}")
        state["managed_paths"][str(managed)] = {"baseline_hash": current, "expected_hash": current, "allowed_children": children}
    return save(path, state, "baseline initialized")


def cmd_guard(args) -> int:
    state = load(Path(args.state)); failures = []
    for raw, entry in state["repositories"].items():
        repo = Path(raw)
        current_allowed = allowed_fingerprints(repo, entry.get("allowed_paths", []))
        if current_allowed != entry.get("expected_allowed", {}):
            failures.append({"repository_allowed_paths": raw, "expected": entry.get("expected_allowed", {}), "actual": current_allowed})
    for raw, entry in state["managed_paths"].items():
        current = digest_managed(Path(raw), entry.get("allowed_children"))
        if current != entry["expected_hash"]:
            failures.append({"managed_path": raw, "expected": entry["expected_hash"], "actual": current})
    if failures:
        print(json.dumps({"verdict": "BLOCKED", "drift": failures}, indent=2))
        return 3
    print("PASS baseline guard")
    return 0


def cmd_accept(args) -> int:
    path, state = Path(args.state), load(Path(args.state))
    target = str(Path(args.path).resolve())
    if target in state["repositories"]:
        entry = state["repositories"][target]; changed = [str(Path(p).resolve().relative_to(Path(target))) for p in (args.changed_path or [])]
        if not changed or not all(path_allowed(item, entry.get("allowed_paths", [])) for item in changed): raise SystemExit("changed paths are not fully allowed")
        protected_changed = set(changed) & set(entry.get("protected_dirty_paths", {}))
        if protected_changed and not args.accept_generated_overlap: raise SystemExit("cannot accept protected dirty path")
        for relative in protected_changed:
            if Path(relative).name != "AGENTS.md": raise SystemExit("generated overlap is limited to AGENTS.md")
            expected_meta = entry["protected_dirty_paths"][relative]
            actual_meta = path_metadata(Path(target), relative, expected_meta["git_state"])
            expected_region, actual_region = expected_meta.get("generated_region"), actual_meta.get("generated_region")
            if expected_region:
                if not actual_region or expected_region["non_generated_hash"] != actual_region["non_generated_hash"]:
                    raise SystemExit("protected AGENTS.md changed outside generated region")
            else:
                content = (Path(target) / relative).read_text(errors="replace")
                base = subprocess.run(["git", "-C", target, "show", f"{entry['base_head']}:{relative}"], capture_output=True, text=True)
                base_generated = base.returncode == 0 and base.stdout.lstrip().startswith("<!-- GENERATED from working-agreement/DIRECTIVES.md")
                if not content.lstrip().startswith("<!-- GENERATED from working-agreement/DIRECTIVES.md") or not (expected_meta.get("git_state") == "??" or base_generated):
                    raise SystemExit("protected path is not a full generated AGENTS.md")
        if not approval_matches(state, args.approval_id, "autonomy", ["accept-baseline"], [], [target], [str(Path(target)/p) for p in changed], args.stage):
            raise SystemExit("baseline advancement lacks matching approval")
        current_allowed = allowed_fingerprints(Path(target), entry.get("allowed_paths", []))
        for relative, expected_hash in entry.get("expected_allowed", {}).items():
            if not path_allowed(relative, changed) and current_allowed.get(relative) != expected_hash:
                raise SystemExit("an authorized path outside the declared change set drifted")
        for relative, expected in entry.get("authorized_dirty_overlaps", {}).items():
            actual = path_metadata(Path(target), relative, expected["git_state"])
            old_region, new_region = expected.get("generated_region"), actual.get("generated_region")
            if not old_region or not new_region or old_region["non_generated_hash"] != new_region["non_generated_hash"]:
                raise SystemExit("authorized generated overlap changed outside its generated region")
        state["repositories"][target]["expected_identity"] = repo_identity(Path(target))
        state["repositories"][target]["expected_allowed"] = current_allowed
    elif target in state["managed_paths"]:
        if not approval_matches(state, args.approval_id, "autonomy", ["accept-baseline"], [], [], [target], args.stage):
            raise SystemExit("managed baseline advancement lacks matching approval")
        if args.managed_child:
            children = sorted(str(Path(child).resolve().relative_to(Path(target))) for child in args.managed_child if under(Path(child), Path(target)))
            if not children: raise SystemExit("managed child scope is empty")
            state["managed_paths"][target]["allowed_children"] = children
        state["managed_paths"][target]["expected_hash"] = digest_managed(Path(target), state["managed_paths"][target].get("allowed_children"))
    else:
        raise SystemExit("path is not in baseline")
    return save(path, state, "expected baseline advanced")


def cmd_review_surface(args) -> int:
    state = load(Path(args.state)); result = {"repositories": {}, "managed_paths": {}}
    for raw, entry in state["repositories"].items():
        repo = Path(raw); paths = set()
        for command in (("diff", "--name-only", f"{entry['base_head']}...HEAD"), ("diff", "--cached", "--name-only"), ("diff", "--name-only")):
            paths.update(x for x in git(repo, *command).splitlines() if x)
        paths.update(dirty_paths(repo, entry.get("allowed_paths", [])))
        result["repositories"][raw] = sorted(p for p in paths if path_allowed(p, entry.get("allowed_paths", [])))
    for raw, entry in state["managed_paths"].items():
        current = digest_managed(Path(raw), entry.get("allowed_children"))
        if current != entry["baseline_hash"]: result["managed_paths"][raw] = current
    print(json.dumps(result, indent=2, sort_keys=True)); return 0


def cmd_artifact(args) -> int:
    path, state = Path(args.state), load(Path(args.state)); artifact = Path(args.path).resolve()
    record = {"id": args.id, "path": str(artifact), "hash": digest_tree(artifact), "type": args.kind, "stage": args.stage}
    existing = state["artifacts"].get(args.id)
    if existing:
        if {key: existing.get(key) for key in record} == record: print("artifact already recorded"); return 0
        raise SystemExit("artifact id already exists with different content")
    state["artifacts"][args.id] = {**record, "created_at": now()}
    return save(path, state, "artifact recorded")


def cmd_requirement(args) -> int:
    if args.status not in {"open", "satisfied", "excluded"}:
        raise SystemExit("invalid requirement status")
    path, state = Path(args.state), load(Path(args.state))
    if args.id not in state["requirements"]: raise SystemExit("unknown requirement")
    current = state["requirements"][args.id].get("status")
    if current == args.status:
        if args.status != "excluded" or approval_replay(state, args.approval_id, args.operation_id):
            print("requirement transition already applied"); return 0
    if current != "open": raise SystemExit("terminal requirement status cannot change")
    if args.status == "satisfied" and (args.stage != "review" or not args.evidence):
        raise SystemExit("requirement satisfaction requires review evidence")
    if args.status == "excluded":
        if not args.evidence or not args.operation_id or not approval_matches(state, args.approval_id, "exclude", ["exclude"], [args.id], [], [], args.stage):
            raise SystemExit("requirement exclusion lacks matching approval and evidence")
    state["requirements"][args.id]["status"] = args.status
    if args.evidence: state["requirements"][args.id]["evidence"] = args.evidence
    if args.status == "excluded": consume_approval(state, args.approval_id, args.operation_id)
    return save(path, state, "requirement updated")


def cmd_add_requirement(args) -> int:
    path, state = Path(args.state), load(Path(args.state))
    if approval_replay(state, args.approval_id, args.operation_id) and args.id in state["requirements"]:
        print("requirement addition already applied"); return 0
    existing = state["requirements"].get(args.id)
    reserved = {blocker.get("candidate_requirement", {}).get("id") for blocker in state["blockers"].values() if blocker.get("status") == "open"}
    if args.id in reserved: raise SystemExit("requirement id is reserved by an open candidate blocker")
    record = {"id": args.id, "text": args.text, "source": args.source, "status": "open"}
    if existing:
        if existing == record: print("requirement already added"); return 0
        raise SystemExit("requirement id already exists with different content")
    if not args.operation_id or not approval_matches(state, args.approval_id, "scope-change", ["add-requirement"], [args.id], [], [], args.stage):
        raise SystemExit("requirement addition lacks matching scope-change approval")
    state["requirements"][args.id] = record
    consume_approval(state, args.approval_id, args.operation_id)
    return save(path, state, "requirement added")


def cmd_gap(args) -> int:
    if args.status != "open": raise SystemExit("new gaps must start open")
    path, state = Path(args.state), load(Path(args.state)); reqs = parse_json_list(args.requirement_ids)
    if not set(reqs) <= set(state["requirements"]): raise SystemExit("gap references unknown requirement")
    record = {"requirement_ids": reqs, "source_stage": args.source_stage,
        "impact": args.impact, "evidence": args.evidence, "status": args.status,
        "closure_evidence": args.closure_evidence}
    existing = state["gaps"].get(args.id)
    if existing:
        if existing == record: print("gap already recorded"); return 0
        raise SystemExit("gap id already exists with different content")
    state["gaps"][args.id] = record
    return save(path, state, "gap recorded")


def cmd_stage(args) -> int:
    supplied = json.loads(Path(args.result_file).read_text()) if args.result_file else {}
    stage = supplied.get("stage", args.stage); attempt = supplied.get("attempt", args.attempt)
    verdict = supplied.get("verdict", args.verdict)
    if verdict not in VERDICTS:
        raise SystemExit("invalid verdict")
    path, state = Path(args.state), load(Path(args.state))
    if not stage or attempt is None: raise SystemExit("stage and attempt are required")
    expected_status = "review" if stage == "review" else "plan" if stage.startswith("plan") else "implementation" if stage.startswith(("implementation", "execution")) else "research" if stage.startswith("research") else None
    active_status = state.get("blocked_from_status") if state["status"] == "blocked" else state["status"]
    if expected_status and active_status != expected_status: raise SystemExit("stage does not match task status")
    if expected_status != "research" and not state["repositories"] and not state["managed_paths"]: raise SystemExit("non-research stage requires a baseline")
    stage_key = f"{stage}:{state['outer_iteration']}:{attempt}"; prior = state["stages"].get(stage_key)
    if prior and args.result_file and prior.get("input_payload") == supplied:
        print("stage result already recorded"); return 0
    attempts = [record.get("attempt") for record in state["stages"].values()
                if record.get("stage") == stage and record.get("outer_iteration") == state["outer_iteration"]]
    expected_attempt = max(attempts, default=0) + 1
    if not prior and attempt != expected_attempt: raise SystemExit(f"stage attempt must be {expected_attempt}")
    assigned_requirements = supplied.get("assigned_requirement_ids", args.assigned_requirement_id or [])
    if not set(assigned_requirements) <= set(state["requirements"]): raise SystemExit("stage assigns unknown requirements")
    pending_gaps = []
    for gap in supplied.get("new_gaps", []):
        required = {"id", "requirement_ids", "source_stage", "impact", "evidence", "status"}
        if not required <= set(gap): raise SystemExit("new gap is missing required fields")
        if gap["status"] != "open": raise SystemExit("new gaps must start open")
        if gap["source_stage"] != stage: raise SystemExit("new gap source_stage must equal recording stage")
        if not gap["requirement_ids"] or not set(gap["requirement_ids"]) <= set(state["requirements"]):
            raise SystemExit("new gap references unknown or empty requirements")
        if not str(gap["impact"]).strip() or not str(gap["evidence"]).strip(): raise SystemExit("new gap impact/evidence must be non-empty")
        existing = state["gaps"].get(gap["id"])
        if existing is not None and existing != gap:
            raise SystemExit("new gap cannot overwrite an existing gap")
        pending_gaps.append((gap["id"], gap))
    new_blocker_ids = []; pending_blockers = []; seen_blocker_ids = set()
    for blocker in supplied.get("new_blockers", []):
        blocker_id = blocker.get("id"); blocker_stage = blocker.get("stage") or blocker.get("source_stage")
        status = blocker.get("status"); reason = blocker.get("reason") or blocker.get("impact")
        required_evidence = blocker.get("required_evidence") or blocker.get("unblock")
        blocker_type = blocker.get("type")
        if not blocker_id or blocker_stage != stage or status != "open" or blocker_type not in {"execution", "external", "approval"} or not reason or not required_evidence:
            raise SystemExit("new blocker is missing required id/stage/status/reason/unblock fields")
        if blocker_id in seen_blocker_ids: raise SystemExit("new blocker ids must be unique")
        seen_blocker_ids.add(blocker_id)
        normalized = {**blocker, "stage": blocker_stage, "status": status,
                      "reason": reason, "required_evidence": required_evidence}
        existing = state["blockers"].get(blocker_id)
        if existing is not None and existing != normalized:
            raise SystemExit("new blocker cannot overwrite an existing blocker")
        pending_blockers.append((blocker_id, normalized))
        new_blocker_ids.append(blocker_id)
    artifact_ids = list(args.artifact_id or [])
    for raw_artifact in supplied.get("artifact_paths", []):
        artifact_path = Path(raw_artifact).resolve(); artifact_id = f"{stage}:{digest_bytes(str(artifact_path).encode())[:12]}"
        artifact_record = {"id": artifact_id, "path": str(artifact_path), "hash": digest_tree(artifact_path), "type": "stage-evidence", "stage": stage}
        existing_artifact = state["artifacts"].get(artifact_id)
        if existing_artifact and {key: existing_artifact.get(key) for key in artifact_record} != artifact_record:
            raise SystemExit("stage artifact identity changed")
        if not existing_artifact: state["artifacts"][artifact_id] = {**artifact_record, "created_at": now()}
        artifact_ids.append(artifact_id)
    if any(a not in state["artifacts"] for a in artifact_ids): raise SystemExit("stage references unknown artifact")
    assigned_gaps = supplied.get("assigned_gap_ids", args.assigned_gap_id or [])
    proposed_gaps = {**state["gaps"], **dict(pending_gaps)}
    if not set(assigned_gaps) <= set(proposed_gaps): raise SystemExit("stage assigns unknown gaps")
    owned = {gap_id for gap_id, gap in proposed_gaps.items() if gap.get("source_stage") == stage} | set(assigned_gaps)
    open_ids = set(supplied.get("open_gap_ids", args.open_gap_id or []))
    closed_ids = set(supplied.get("closed_gap_ids", args.closed_gap_id or []))
    if owned != open_ids | closed_ids: raise SystemExit("stage result does not reconcile owned gaps")
    if open_ids & closed_ids: raise SystemExit("gap cannot be open and closed")
    owned_blockers = sorted(set(supplied.get("owned_blocker_ids", args.owned_blocker_id or [])) | set(new_blocker_ids))
    proposed_blockers = {**state["blockers"], **dict(pending_blockers)}
    if not set(owned_blockers) <= set(proposed_blockers): raise SystemExit("stage owns unknown blockers")
    transitions = supplied.get("record_transitions", [])
    gap_transitions = {}; blocker_transitions = {}; requirement_transitions = {}; approval_transitions = {}
    for transition in transitions:
        required = {"kind", "id", "from_status", "to_status", "evidence"}
        if not required <= set(transition) or not str(transition["evidence"]).strip():
            raise SystemExit("record transition is missing required fields or evidence")
        if transition["kind"] == "gap":
            if transition["id"] in gap_transitions: raise SystemExit("record transition ids must be unique per kind")
            gap = proposed_gaps.get(transition["id"])
            if not gap or gap.get("status") != transition["from_status"]: raise SystemExit("record transition from_status does not match")
            if transition["from_status"] != "open" or transition["to_status"] not in {"closed", "superseded", "non-gap"}: raise SystemExit("unsupported gap transition")
            if transition["to_status"] == "superseded":
                replacement = transition.get("replacement_id")
                if not replacement or replacement == transition["id"] or replacement not in proposed_gaps: raise SystemExit("superseded gap requires an existing replacement_id")
            gap_transitions[transition["id"]] = transition
        elif transition["kind"] == "blocker":
            if transition["id"] not in owned_blockers: raise SystemExit("stage cannot transition an unowned blocker")
            if transition["id"] in blocker_transitions: raise SystemExit("record transition ids must be unique per kind")
            blocker = proposed_blockers.get(transition["id"])
            if not blocker or blocker.get("status") != transition["from_status"]: raise SystemExit("record transition from_status does not match")
            allowed = {("open", "fixed-awaiting-verification"), ("fixed-awaiting-verification", "verified"),
                       ("verified", "closed"), ("open", "superseded"), ("open", "non-gap")}
            if (transition["from_status"], transition["to_status"]) not in allowed: raise SystemExit("unsupported blocker transition")
            if transition["to_status"] == "superseded" and not transition.get("replacement_id"): raise SystemExit("superseded blocker requires replacement_id")
            blocker_transitions[transition["id"]] = transition
        elif transition["kind"] == "requirement":
            if transition["id"] not in assigned_requirements: raise SystemExit("stage cannot transition an unassigned requirement")
            if transition["id"] in requirement_transitions: raise SystemExit("record transition ids must be unique per kind")
            requirement = state["requirements"].get(transition["id"])
            if not requirement or requirement.get("status") != transition["from_status"]: raise SystemExit("record transition from_status does not match")
            if transition["from_status"] != "open" or transition["to_status"] not in {"satisfied", "excluded"}: raise SystemExit("unsupported requirement transition")
            if stage != "review": raise SystemExit("requirement terminal transitions belong to review")
            if transition["to_status"] == "excluded":
                if not transition.get("approval_id") or not transition.get("operation_id") or not approval_matches(state, transition["approval_id"], "exclude", ["exclude"], [transition["id"]], [], [], stage):
                    raise SystemExit("requirement exclusion transition lacks matching approval")
            requirement_transitions[transition["id"]] = transition
        elif transition["kind"] == "approval":
            if transition["id"] in approval_transitions: raise SystemExit("record transition ids must be unique per kind")
            approval = state["approvals"].get(transition["id"])
            if not approval or approval.get("status") != transition["from_status"]: raise SystemExit("record transition from_status does not match")
            if transition["from_status"] != "granted" or transition["to_status"] != "revoked": raise SystemExit("unsupported approval transition")
            approval_transitions[transition["id"]] = transition
        else:
            raise SystemExit("unsupported stage record transition kind")
    closing_ids = {gap_id for gap_id in closed_ids if proposed_gaps[gap_id].get("status") == "open"}
    if closing_ids != set(gap_transitions): raise SystemExit("open gap closure requires one evidence-bearing transition")
    new_open = {gap["id"] for gap in supplied.get("new_gaps", []) if gap["status"] == "open"}
    effective_blocker_status = {blocker_id: blocker_transitions.get(blocker_id, {}).get("to_status", proposed_blockers[blocker_id].get("status")) for blocker_id in owned_blockers}
    terminal_blockers = {"closed", "superseded", "non-gap"}
    effective_requirements = {req_id: requirement_transitions.get(req_id, {}).get("to_status", state["requirements"][req_id].get("status")) for req_id in assigned_requirements}
    if verdict == "PASS" and stage == "review" and any(status == "open" for status in effective_requirements.values()):
        raise SystemExit("review PASS requires every assigned requirement terminal")
    if verdict == "PASS" and (open_ids or new_open or any(effective_blocker_status[b] not in terminal_blockers for b in owned_blockers)):
        raise SystemExit("PASS cannot leave owned gaps or blockers open")
    if verdict == "BLOCKED" and not any(effective_blocker_status[b] not in terminal_blockers for b in owned_blockers):
        raise SystemExit("BLOCKED requires an owned non-terminal blocker")
    for blocker_id, blocker in pending_blockers:
        state["blockers"][blocker_id] = blocker
    for blocker_id, transition in blocker_transitions.items():
        state["blockers"][blocker_id].update(status=transition["to_status"], transition_evidence=transition["evidence"])
        if transition.get("replacement_id"): state["blockers"][blocker_id]["replacement_id"] = transition["replacement_id"]
    for gap_id, gap in pending_gaps:
        state["gaps"][gap_id] = gap
    for requirement_id, transition in requirement_transitions.items():
        state["requirements"][requirement_id].update(status=transition["to_status"], evidence=transition["evidence"])
        if transition["to_status"] == "excluded": consume_approval(state, transition["approval_id"], transition["operation_id"])
    for approval_id, transition in approval_transitions.items():
        state["approvals"][approval_id].update(status="revoked", revocation_evidence=transition["evidence"])
    for gap_id in closed_ids:
        if gap_id in gap_transitions:
            transition = gap_transitions[gap_id]
            state["gaps"][gap_id].update(status=transition["to_status"], closure_evidence=transition["evidence"])
            if transition.get("replacement_id"): state["gaps"][gap_id]["replacement_id"] = transition["replacement_id"]
    payload = {"stage": stage, "outer_iteration": state["outer_iteration"], "attempt": attempt,
               "iteration": supplied.get("iteration", state["outer_iteration"]), "verdict": verdict,
               "assigned_requirement_ids": assigned_requirements, "assigned_gap_ids": assigned_gaps,
               "owned_blocker_ids": owned_blockers, "artifact_ids": sorted(set(artifact_ids)),
               "open_gap_ids": sorted(open_ids), "closed_gap_ids": sorted(closed_ids),
               "record_transitions": supplied.get("record_transitions", []), "evidence": supplied.get("evidence", [])}
    if prior:
        if {k: prior.get(k) for k in payload} == payload:
            print("stage result already recorded"); return 0
        raise SystemExit("stage idempotency key already has different content")
    record = {**payload, "input_payload": supplied if args.result_file else None, "recorded_at": now()}
    state["stages"][stage_key] = record
    if verdict == "CAP_REACHED":
        state["blocked_from_status"] = state["status"]; state["status"] = "cap_reached"
        state["cap_stage"] = stage; state["cap_attempt"] = attempt
    elif verdict == "BLOCKED" and state["status"] != "blocked":
        state["blocked_from_status"] = state["status"]; state["blocked_stage"] = stage; state["status"] = "blocked"
    return save(path, state, "stage result recorded")


def cmd_transition(args) -> int:
    path, state = Path(args.state), load(Path(args.state)); current = state["status"]
    if args.to == current:
        print("transition already applied"); return 0
    if args.to not in STATUSES or args.to not in TRANSITIONS[current]:
        raise SystemExit(f"invalid transition: {current} -> {args.to}")
    if args.to not in {"research", "blocked"} and not state["repositories"] and not state["managed_paths"]:
        raise SystemExit("cannot leave research without a baseline")
    if args.to == "complete":
        if not state["repositories"] and not state["managed_paths"]: raise SystemExit("cannot complete without a baseline")
        if any(r.get("status") not in {"satisfied", "excluded"} for r in state["requirements"].values()):
            raise SystemExit("cannot complete with open requirements")
        if any(g.get("status") not in {"closed", "superseded", "non-gap"} for g in state["gaps"].values()): raise SystemExit("cannot complete with unresolved or malformed gaps")
        latest = {}
        for result in state["stages"].values():
            key = (result.get("outer_iteration", 0), result.get("attempt", 0))
            if result.get("stage") not in latest or key > latest[result["stage"]][0]: latest[result["stage"]] = (key, result)
        if any(item[1].get("verdict") != "PASS" for item in latest.values()): raise SystemExit("cannot complete with a latest non-PASS stage")
        if "review" not in latest or latest["review"][1].get("verdict") != "PASS": raise SystemExit("cannot complete without review PASS")
        if any(b.get("status") not in {"closed", "superseded", "non-gap"} for b in state["blockers"].values()):
            raise SystemExit("cannot complete with non-terminal blockers")
    if current == "review" and args.to == "research":
        state["outer_iteration"] += 1
    state["status"] = args.to
    return save(path, state, f"transitioned {current} -> {args.to}")


def cmd_block(args) -> int:
    path, state = Path(args.state), load(Path(args.state))
    record = {"status": "open", "type": args.type, "stage": args.stage, "reason": args.reason,
              "required_evidence": args.required_evidence, "resolution": args.resolution}
    existing = state["blockers"].get(args.id)
    if existing:
        if existing == record: print("blocker already recorded"); return 0
        raise SystemExit("blocker id already exists with different content")
    state["blocked_from_status"] = state["status"]; state["blocked_stage"] = args.stage; state["status"] = "blocked"
    state["blockers"][args.id] = record
    return save(path, state, "blocked")


def cmd_resume(args) -> int:
    path, state = Path(args.state), load(Path(args.state))
    if approval_replay(state, args.approval_id, args.operation_id) and state["status"] != "blocked":
        print("resume operation already applied"); return 0
    if state["status"] != "blocked":
        raise SystemExit("generic resume only applies to blocked tasks; use continue-stage at a cap")
    blocker = state["blockers"].get(args.blocker_id)
    if not blocker or blocker.get("status") not in {"closed", "superseded", "non-gap"}:
        raise SystemExit("resume requires a terminal blocker")
    if any(item.get("status") not in {"closed", "superseded", "non-gap"} for item in state["blockers"].values()):
        raise SystemExit("resume requires every blocker terminal")
    if not args.operation_id or not approval_matches(state, args.approval_id, "resume", ["resume"], [args.blocker_id], [], [], blocker["stage"]):
        raise SystemExit("resume lacks matching approval")
    target = state["blocked_from_status"]
    if target not in {"research", "plan", "implementation", "review"}: raise SystemExit("blocked task lacks a valid resume target")
    state.update(status=target, blocked_from_status=None, blocked_stage=None, cap_stage=None, cap_attempt=None)
    consume_approval(state, args.approval_id, args.operation_id)
    return save(path, state, f"resumed {target}")


def cmd_continue(args) -> int:
    path, state = Path(args.state), load(Path(args.state))
    if approval_replay(state, args.approval_id, args.operation_id) and state["status"] != "cap_reached":
        print("continuation operation already applied"); return 0
    if state["status"] != "cap_reached" or state["cap_stage"] != args.stage:
        raise SystemExit("stage is not at cap")
    if not args.operation_id or not approval_matches(state, args.approval_id, "continue", ["continue"], [args.stage], [], [], args.stage):
        raise SystemExit("continuation approval does not match")
    state.update(status=state["blocked_from_status"], cap_stage=None, cap_attempt=None, blocked_from_status=None)
    consume_approval(state, args.approval_id, args.operation_id)
    return save(path, state, "stage continued")


def cmd_resolve_approval(args) -> int:
    path, state = Path(args.state), load(Path(args.state)); blocker = state["blockers"].get(args.blocker_id)
    approval = state["approvals"].get(args.approval_id, {})
    if approval.get("status") == "consumed" and approval.get("consumed_by") == args.operation_id:
        print("approval operation already applied"); return 0
    if state["status"] != "blocked": raise SystemExit("task is not blocked")
    if not blocker or blocker.get("status") != "open": raise SystemExit("approval blocker is not open")
    if blocker.get("resolution", "approval") != "approval": raise SystemExit("blocker does not require approval resolution")
    candidate = blocker.get("candidate_requirement")
    if candidate:
        if args.decision not in {"approve", "reject"}: raise SystemExit("candidate requirement resolution requires a decision")
        operation = f"{args.decision}-candidate"
        if not approval_matches(state, args.approval_id, "scope-change", [operation], [args.blocker_id], [], [], blocker["stage"]):
            raise SystemExit("approval does not match candidate requirement resolution")
        if not all(candidate.get(key) for key in ("id", "text", "source", "discovered_by_stage")) or candidate["discovered_by_stage"] != blocker["stage"]:
            raise SystemExit("candidate requirement is malformed or has invalid provenance")
        if candidate["id"] in state["requirements"]: raise SystemExit("candidate requirement id already exists")
        state["requirements"][candidate["id"]] = {**candidate, "status": "open" if args.decision == "approve" else "excluded",
                                                    "evidence": args.approval_id}
    else:
        if args.decision: raise SystemExit("decision is only valid for candidate requirements")
        if not approval_matches(state, args.approval_id, "resume", ["resolve-blocker"], [args.blocker_id], [], [], blocker["stage"]):
            raise SystemExit("approval does not match blocker resolution")
    blocker.update(status="closed", closure_evidence=args.approval_id)
    approval.update(status="consumed", consumed_by=args.operation_id)
    target = "research" if candidate and args.decision == "approve" else state.get("blocked_from_status")
    if target not in {"research", "plan", "implementation", "review"}: raise SystemExit("blocked task lacks a valid resume target")
    if candidate and args.decision == "approve": state["outer_iteration"] += 1
    state.update(status=target, blocked_from_status=None, blocked_stage=None)
    return save(path, state, "approval blocker resolved")


def parse_json_list(value: str) -> list[str]:
    result = json.loads(value)
    if not isinstance(result, list) or not all(isinstance(v, str) for v in result):
        raise SystemExit("approval scope fields must be JSON string lists")
    return sorted(set(result))


def cmd_approve(args) -> int:
    if args.kind not in KINDS:
        raise SystemExit("invalid approval kind")
    path, state = Path(args.state), load(Path(args.state))
    scope = {
        "kind": args.kind, "operations": parse_json_list(args.operations),
        "target_ids": parse_json_list(args.target_ids),
        "repository_roots": [str(Path(p).resolve()) for p in parse_json_list(args.repository_roots)],
        "allowed_paths": [str(Path(p).resolve()) for p in parse_json_list(args.allowed_paths)],
        "stage": args.stage, "outer_iteration": state["outer_iteration"],
    }
    record = {"status": "granted", "scope": scope, "evidence": args.evidence}
    existing = state["approvals"].get(args.id)
    if existing:
        if existing == record: print("approval already recorded"); return 0
        raise SystemExit("approval id already exists with different content or status")
    state["approvals"][args.id] = record
    return save(path, state, "approval recorded")


def approval_matches(state, approval_id, kind, operations, targets, roots, paths, stage) -> bool:
    approval = state["approvals"].get(approval_id, {})
    scope = approval.get("scope", {})
    return (approval.get("status") == "granted" and scope.get("kind") == kind
            and set(operations) <= set(scope.get("operations", []))
            and set(targets) <= set(scope.get("target_ids", []))
            and set(map(str, roots)) <= set(scope.get("repository_roots", []))
            and set(map(str, paths)) <= set(scope.get("allowed_paths", []))
            and scope.get("stage") == stage and scope.get("outer_iteration") == state["outer_iteration"])


def approval_replay(state, approval_id, operation_id) -> bool:
    approval = state["approvals"].get(approval_id, {})
    return bool(operation_id and approval.get("status") == "consumed" and approval.get("consumed_by") == operation_id)


def consume_approval(state, approval_id, operation_id) -> None:
    approval = state["approvals"][approval_id]
    if approval.get("status") != "granted": raise SystemExit("approval is not granted")
    approval.update(status="consumed", consumed_by=operation_id)


def cmd_check(args) -> int:
    state = load(Path(args.state)); errors = []
    if state["status"] not in {"research", "blocked"} and not state["repositories"] and not state["managed_paths"]:
        errors.append("non-research state lacks baseline")
    if state["status"] == "complete" and any(r.get("status") not in {"satisfied", "excluded"} for r in state["requirements"].values()):
        errors.append("complete state has open requirements")
    for requirement_id, requirement in state["requirements"].items():
        if requirement.get("status") not in {"open", "satisfied", "excluded"}: errors.append(f"invalid requirement status: {requirement_id}")
    for gap_id, gap in state["gaps"].items():
        if gap.get("status") not in {"open", "closed", "superseded", "non-gap"}: errors.append(f"invalid gap status: {gap_id}")
    for blocker_id, blocker in state["blockers"].items():
        if blocker.get("status") not in {"open", "fixed-awaiting-verification", "verified", "closed", "superseded", "non-gap"}: errors.append(f"invalid blocker status: {blocker_id}")
        if blocker.get("type") not in {"execution", "external", "approval"}: errors.append(f"invalid blocker type: {blocker_id}")
    for approval_id, approval in state["approvals"].items():
        if approval.get("status") not in {"granted", "consumed", "revoked"}: errors.append(f"invalid approval status: {approval_id}")
    for stage, result in state["stages"].items():
        missing = [a for a in result.get("artifact_ids", []) if a not in state["artifacts"]]
        if missing: errors.append(f"{stage} references missing artifacts: {missing}")
        for artifact_id in result.get("artifact_ids", []):
            artifact = state["artifacts"].get(artifact_id)
            if artifact and digest_tree(Path(artifact["path"])) != artifact.get("hash", artifact.get("sha256")):
                errors.append(f"{stage} artifact hash drift: {artifact_id}")
    if errors:
        print("\n".join(errors)); return 2
    print("PASS state check"); return 0


def cmd_status(args) -> int:
    state = load(Path(args.state))
    print(json.dumps(state, indent=2, sort_keys=True) if args.json else f"{state['task_id']} {state['status']} iteration={state['outer_iteration']}")
    return 0


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(required=True)
    p = sub.add_parser("init"); p.add_argument("state"); p.add_argument("--source", required=True); p.add_argument("--objective", required=True); p.add_argument("--requirements-file", required=True); p.set_defaults(func=cmd_init)
    p = sub.add_parser("migrate-v0"); p.add_argument("--source", required=True); p.add_argument("--destination", required=True); p.add_argument("--backup", required=True); p.add_argument("--requirements-file", required=True); p.add_argument("--objective", default="Migrated convergence task"); p.set_defaults(func=cmd_migrate)
    p = sub.add_parser("init-baseline"); p.add_argument("state"); p.add_argument("--repository", action="append", default=[]); p.add_argument("--managed-path", action="append", default=[]); p.add_argument("--managed-child", action="append"); p.add_argument("--allowed-path", action="append"); p.add_argument("--overlap-path", action="append"); p.add_argument("--commit-policy", choices=["none", "per_iteration"], default="none"); p.add_argument("--adopt-current-head-before-mutation", action="store_true"); p.add_argument("--adoption-evidence"); p.set_defaults(func=cmd_init_baseline)
    p = sub.add_parser("guard-baseline"); p.add_argument("state"); p.set_defaults(func=cmd_guard)
    p = sub.add_parser("accept-baseline"); p.add_argument("state"); p.add_argument("--path", required=True); p.add_argument("--changed-path", action="append"); p.add_argument("--managed-child", action="append"); p.add_argument("--approval-id", required=True); p.add_argument("--stage", required=True); p.add_argument("--accept-generated-overlap", action="store_true"); p.set_defaults(func=cmd_accept)
    p = sub.add_parser("review-surface"); p.add_argument("state"); p.set_defaults(func=cmd_review_surface)
    p = sub.add_parser("register-artifact"); p.add_argument("state"); p.add_argument("--id", required=True); p.add_argument("--path", required=True); p.add_argument("--kind", required=True); p.add_argument("--stage", required=True); p.set_defaults(func=cmd_artifact)
    p = sub.add_parser("set-requirement"); p.add_argument("state"); p.add_argument("--id", required=True); p.add_argument("--status", required=True); p.add_argument("--evidence"); p.add_argument("--approval-id"); p.add_argument("--operation-id"); p.add_argument("--stage"); p.set_defaults(func=cmd_requirement)
    p = sub.add_parser("add-requirement"); p.add_argument("state"); p.add_argument("--id", required=True); p.add_argument("--text", required=True); p.add_argument("--source", required=True); p.add_argument("--approval-id", required=True); p.add_argument("--operation-id", required=True); p.add_argument("--stage", required=True); p.set_defaults(func=cmd_add_requirement)
    p = sub.add_parser("record-gap"); p.add_argument("state"); p.add_argument("--id", required=True); p.add_argument("--requirement-ids", default="[]"); p.add_argument("--source-stage", required=True); p.add_argument("--impact", required=True); p.add_argument("--evidence", required=True); p.add_argument("--status", default="open"); p.add_argument("--closure-evidence"); p.set_defaults(func=cmd_gap)
    p = sub.add_parser("record-stage"); p.add_argument("state"); p.add_argument("--result-file"); p.add_argument("--stage"); p.add_argument("--attempt", type=int); p.add_argument("--verdict"); p.add_argument("--artifact-id", action="append"); p.add_argument("--assigned-requirement-id", action="append"); p.add_argument("--assigned-gap-id", action="append"); p.add_argument("--owned-blocker-id", action="append"); p.add_argument("--open-gap-id", action="append"); p.add_argument("--closed-gap-id", action="append"); p.set_defaults(func=cmd_stage)
    p = sub.add_parser("transition"); p.add_argument("state"); p.add_argument("--to", required=True); p.set_defaults(func=cmd_transition)
    p = sub.add_parser("block"); p.add_argument("state"); p.add_argument("--id", required=True); p.add_argument("--type", choices=["execution", "external", "approval"], required=True); p.add_argument("--stage", required=True); p.add_argument("--reason", required=True); p.add_argument("--required-evidence", required=True); p.add_argument("--resolution", choices=["evidence", "approval"], required=True); p.set_defaults(func=cmd_block)
    p = sub.add_parser("resume"); p.add_argument("state"); p.add_argument("--stage"); p.add_argument("--blocker-id", required=True); p.add_argument("--approval-id", required=True); p.add_argument("--operation-id", required=True); p.set_defaults(func=cmd_resume)
    p = sub.add_parser("continue-stage"); p.add_argument("state"); p.add_argument("--stage", required=True); p.add_argument("--approval-id", required=True); p.add_argument("--operation-id", required=True); p.set_defaults(func=cmd_continue)
    p = sub.add_parser("resolve-approval-blocker"); p.add_argument("state"); p.add_argument("--blocker-id", required=True); p.add_argument("--approval-id", required=True); p.add_argument("--operation-id", required=True); p.add_argument("--decision", choices=["approve", "reject"]); p.set_defaults(func=cmd_resolve_approval)
    p = sub.add_parser("grant-approval"); p.add_argument("state"); p.add_argument("--id", required=True); p.add_argument("--kind", required=True); p.add_argument("--operations", default="[]"); p.add_argument("--target-ids", default="[]"); p.add_argument("--repository-roots", default="[]"); p.add_argument("--allowed-paths", default="[]"); p.add_argument("--stage", required=True); p.add_argument("--evidence", required=True); p.set_defaults(func=cmd_approve)
    p = sub.add_parser("check"); p.add_argument("state"); p.set_defaults(func=cmd_check)
    p = sub.add_parser("status"); p.add_argument("state"); p.add_argument("--json", action="store_true"); p.set_defaults(func=cmd_status)
    return ap


if __name__ == "__main__":
    args = parser().parse_args()
    raise SystemExit(args.func(args))
