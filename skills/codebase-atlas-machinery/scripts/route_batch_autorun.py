"""Read-only verification of a retained, published c5 route job."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if os.fspath(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, os.fspath(SCRIPT_DIR))

import atlas
import route_autorun
import route_batch
import route_coordinator


WORKER_FILES = (
    "prompt.txt", "argv.json", "events.jsonl", "stderr.txt", "answer.txt",
    "elapsed_ms.json", "schema.json", "cli-schema.json",
)
ROOT_FILES = ("luna-draft.json", "sol-review.json")
COORDINATOR_FILES = {
    "route-find.json", "evidence-pack.json", "luna-draft.json", "review-packet.json",
    "sol-review.json", "review-validation.json", "publish-result.json",
    "published-route-find.json",
}
SOL_ID_RE = re.compile(r"run_once-sol-[0-9a-f]{32}")


class VerificationError(Exception):
    """A retained completion is missing, changed, stale, or inconsistent."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _safe_path(path: Path, root: Path, label: str) -> Path:
    absolute = Path(os.path.abspath(os.fspath(path)))
    if absolute != path or absolute.is_symlink():
        raise VerificationError(f"{label} path is not canonical or is a symlink: {path}")
    try:
        absolute.relative_to(root)
    except ValueError as exc:
        raise VerificationError(f"{label} path escapes the retained job: {path}") from exc
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise VerificationError(f"{label} path contains a symlink: {current}")
    try:
        resolved = absolute.resolve(strict=True)
    except OSError as exc:
        raise VerificationError(f"{label} path is missing: {path}: {exc}") from exc
    if resolved != absolute:
        raise VerificationError(f"{label} path is not canonical: {path}")
    return absolute


def _read_bytes(path: Path, root: Path, label: str) -> bytes:
    safe = _safe_path(path, root, label)
    try:
        info = safe.lstat()
        if not stat.S_ISREG(info.st_mode):
            raise VerificationError(f"{label} is not a regular file: {safe}")
        return safe.read_bytes()
    except OSError as exc:
        raise VerificationError(f"cannot read {label} {safe}: {exc}") from exc


def _json_object(raw: bytes, label: str) -> dict:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"{label} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"{label} must be a JSON object")
    return value


def _write_json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _artifact_hashes(job: Path, coordinator: Path) -> tuple[dict[str, str], dict[str, str]]:
    paths: dict[str, Path] = {}
    for role in ("luna", "sol"):
        for name in WORKER_FILES:
            relative = f"{role}/{name}"
            paths[relative] = job / relative
    for name in ROOT_FILES:
        paths[name] = job / name

    manifest_path = coordinator / route_coordinator.MANIFEST
    manifest_raw = _read_bytes(manifest_path, job, "coordinator manifest")
    manifest = _json_object(manifest_raw, "coordinator manifest")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != COORDINATOR_FILES:
        raise VerificationError("coordinator artifact registry is incomplete or contains unexpected artifacts")
    paths["coordinator/manifest.json"] = manifest_path
    for name in sorted(artifacts):
        if Path(name).name != name:
            raise VerificationError(f"unsafe registered coordinator artifact name: {name!r}")
        paths[f"coordinator/{name}"] = coordinator / name

    hashes: dict[str, str] = {}
    absolute: dict[str, str] = {}
    for relative in sorted(paths):
        path = paths[relative]
        raw = _read_bytes(path, job, f"retained artifact {relative}")
        hashes[relative] = _sha(raw)
        absolute[relative] = os.fspath(path)
    return absolute, hashes


def _worker_argv(role: str, job: Path, worker: Path,
                 executable: str = route_autorun.CLI) -> list[str]:
    answer = worker / "answer.txt"
    cli_schema = worker / "cli-schema.json"
    workspace = worker / "workspace"
    base = [executable, "exec", "--ignore-user-config", "--ignore-rules", "--ephemeral",
            "--skip-git-repo-check", "--sandbox", "read-only", "--model", route_autorun.MODELS[role],
            "-c", 'model_reasoning_effort="high"', "-c", "project_doc_max_bytes=0",
            "-c", "features.shell_tool=false", "-c", 'web_search="disabled"',
            "--cd", os.fspath(workspace), "--json", "--output-last-message", os.fspath(answer),
            "--output-schema", os.fspath(cli_schema), "-"]
    if role not in route_autorun.MODELS:
        raise VerificationError(f"unsupported retained worker role: {role}")
    return base


def _worker_result(job: Path, role: str, worker: Path) -> tuple[dict, dict]:
    raw_by_name = {name: _read_bytes(worker / name, job, f"{role} {name}") for name in WORKER_FILES}
    try:
        prompt = raw_by_name["prompt.txt"].decode("utf-8")
        answer = raw_by_name["answer.txt"].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise VerificationError(f"{role} prompt or answer is not UTF-8: {exc}") from exc
    try:
        argv = json.loads(raw_by_name["argv.json"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"{role} argv is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(argv, list) or not argv or any(not isinstance(item, str) for item in argv):
        raise VerificationError(f"{role} argv must be a nonempty JSON array of strings")
    executable = Path(argv[0])
    try:
        if (not executable.is_absolute() or executable.resolve(strict=True) != executable
                or not stat.S_ISREG(executable.stat().st_mode) or not os.access(executable, os.X_OK)
                or _sha(executable.read_bytes()) != route_autorun.CLI_SHA256):
            raise VerificationError("retained Codex CLI does not match the approved binary hash")
    except OSError as exc:
        raise VerificationError(f"cannot verify the retained approved Codex CLI: {exc}") from exc
    if argv != _worker_argv(role, job, worker, argv[0]):
        raise VerificationError(f"{role} saved argv differs from the approved run_worker command")

    schema = _json_object(raw_by_name["schema.json"], f"{role} canonical schema")
    cli_schema = _json_object(raw_by_name["cli-schema.json"], f"{role} CLI schema")
    if raw_by_name["schema.json"] != _write_json_bytes(schema):
        raise VerificationError(f"{role} canonical schema serialization changed")
    if raw_by_name["cli-schema.json"] != _write_json_bytes(route_autorun._cli_schema(schema)):
        raise VerificationError(f"{role} CLI transport schema differs from the current conversion")
    if cli_schema != route_autorun._cli_schema(schema):
        raise VerificationError(f"{role} CLI schema does not match the current conversion")

    elapsed = _json_object(raw_by_name["elapsed_ms.json"], f"{role} elapsed record")
    if (set(elapsed) != {"elapsed_ms"} or type(elapsed["elapsed_ms"]) is not int
            or elapsed["elapsed_ms"] < 0
            or raw_by_name["elapsed_ms.json"] != _write_json_bytes(elapsed)):
        raise VerificationError(f"{role} elapsed record is malformed")
    try:
        events_text = raw_by_name["events.jsonl"].decode("utf-8")
        events = [json.loads(line) for line in events_text.splitlines() if line.strip()]
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"{role} event stream is invalid: {exc}") from exc
    admission = route_autorun.admit_terminal(events, answer)
    if admission.get("accepted") is not True:
        raise VerificationError(f"{role} terminal admission failed: {admission.get('reason', 'unknown reason')}")
    value = route_autorun._strict_json_object(answer, f"{role} answer")
    return {"prompt": prompt, "schema": schema, "value": value,
            "thread_id": admission["thread_id"], "usage": admission["usage"],
            "elapsed_ms": elapsed["elapsed_ms"], "answer_bytes": raw_by_name["answer.txt"]}, argv


def _luna_prompt(identity: dict, route_fact_id: str, evidence: dict, catalogue: list,
                 contextual: list, schema: dict) -> str:
    return (
        "This is a closed-input automated JSON worker, not a repository implementation task. Use no tools or skills. "
        "Do not announce plans, working agreements, process, or progress. Produce exactly ONE assistant message total: "
        "the required final JSON object. No commentary channel or prefatory message.\n\n"
        "Draft one Atlas route map from the complete saved evidence packet. Make only source-supported claims. "
        "Cite ordinary Atlas facts only with an exact complete {fact_id, source} object from the canonical citation catalogue. "
        "Do not cite contextual packet spans under their fact IDs. Compiler and runtime observations remain contextual evidence; "
        "do not turn synthetic IDs or anchors into ordinary citations. Do not claim runtime execution or runtime dependency-injection selection. "
        "Include the selected route fact in at least one conclusion. Return exactly one JSON object matching the route-map schema; "
        "do not write files, use pointers, include markdown fences, or add text outside the JSON object.\n\n"
        "SELECTED ROUTE FACT ID:\n" + route_fact_id +
        "\n\nCOMPLETE SAVED EVIDENCE PACKET:\n" + json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2) +
        "\n\nCANONICAL CITATION CATALOGUE:\n" + json.dumps(catalogue, ensure_ascii=False, sort_keys=True, indent=2) +
        "\n\nCONTEXTUAL SOURCES (reasoning only; not canonical citations):\n" +
        json.dumps(contextual, ensure_ascii=False, sort_keys=True, indent=2) +
        "\n\nROUTE-MAP JSON SCHEMA:\n" + json.dumps(schema, ensure_ascii=True, sort_keys=True, indent=2)
    )


def _sol_prompt(packet: dict, catalogue: list, contextual: list, schema: dict,
                review_identity: str, timestamp: str) -> str:
    return (
        "This is a closed-input automated JSON worker, not a repository implementation task. Use no tools or skills. "
        "Do not announce plans, working agreements, process, or progress. Produce exactly ONE assistant message total: "
        "the required final JSON object. No commentary channel or prefatory message.\n\n"
        "You are an independent Sol High reviewer. Review this exact Atlas packet. Decide separately on assignment fit, "
        "every numbered conclusion against its cited source spans, and route association. Verify ordinary citations only "
        "against the exact canonical citation catalogue; contextual spans are for reasoning and cannot support citations "
        "under their fact IDs. Preserve compiler/runtime provenance and do not claim runtime dispatch proof. Reject when any "
        "decision is unsupported. Return exactly one JSON object matching the review schema, without markdown fences or extra text.\n\n"
        "Use this exact caller-generated review-request identity as reviewer_identity: " + review_identity +
        "\nUse this exact frozen UTC timestamp as reviewed_at: " + timestamp +
        "\n\nEXACT REVIEW PACKET:\n" + json.dumps(packet, ensure_ascii=False, sort_keys=True, indent=2) +
        "\n\nCANONICAL CITATION CATALOGUE:\n" + json.dumps(catalogue, ensure_ascii=False, sort_keys=True, indent=2) +
        "\n\nCONTEXTUAL SOURCES (reasoning only; not canonical citations):\n" +
        json.dumps(contextual, ensure_ascii=False, sort_keys=True, indent=2) +
        "\n\nREVIEW JSON SCHEMA:\n" + json.dumps(schema, ensure_ascii=True, sort_keys=True, indent=2)
    )


def _blocked(reason: str, paths: dict[str, str] | None = None,
             hashes: dict[str, str] | None = None) -> dict:
    result = {"result": "blocked", "reason": reason}
    if paths is not None and hashes is not None:
        result["artifact_paths"] = paths
        result["artifact_sha256"] = hashes
    return result


def verify_completed(repo_arg, db_arg, route_fact_id, job_arg,
                     expected_artifact_sha256=None) -> dict:
    """Recognize only an exact current c5 job with fresh canonical publication."""
    paths = hashes = None
    try:
        if not isinstance(job_arg, str) or not os.path.isabs(job_arg):
            raise VerificationError("job_arg must be an absolute path")
        job = Path(job_arg)
        if job.as_posix() != os.path.normpath(job_arg):
            raise VerificationError("job_arg must be canonical")
        job = _safe_path(job, job, "job root")
        if not job.is_dir():
            raise VerificationError("job root is not a directory")
        identity = route_coordinator._identity(repo_arg, db_arg, route_fact_id)
        repo = route_coordinator._canonical_repo(repo_arg)
        db = Path(identity["database_path"])
        if (job == repo or job.is_relative_to(repo) or repo.is_relative_to(job)
                or job == db or job.is_relative_to(db) or db.is_relative_to(job)):
            raise VerificationError("job, repository, and database paths must not overlap")
        if not isinstance(route_fact_id, str) or not route_fact_id:
            raise VerificationError("route_fact_id must be nonempty")
        coordinator = job / "coordinator"
        for directory in (job, coordinator, job / "luna", job / "sol"):
            _safe_path(directory, job, "job directory")
            if not directory.is_dir():
                raise VerificationError(f"required job directory is missing: {directory.relative_to(job)}")

        current = route_coordinator.status(os.fspath(repo), os.fspath(db), route_fact_id,
                                           os.fspath(coordinator))
        if current.get("result") != "published_and_fresh":
            raise VerificationError(f"current coordinator status is {current.get('result')!r}, not published_and_fresh")
        current_identity = current.get("identity")
        if not isinstance(current_identity, dict) or any(current_identity.get(key) != value for key, value in identity.items()):
            raise VerificationError("current coordinator identity does not match the requested repo, database, and route")

        coordinator_manifest_raw = _read_bytes(coordinator / route_coordinator.MANIFEST, job, "coordinator manifest")
        coordinator_manifest = _json_object(coordinator_manifest_raw, "coordinator manifest")
        manifest_identity = coordinator_manifest.get("identity")
        if not isinstance(manifest_identity, dict) or any(manifest_identity.get(key) != value for key, value in identity.items()):
            raise VerificationError("retained coordinator manifest identity differs from the requested route")
        if any(current_identity.get(key) != manifest_identity.get(key)
               for key in ("snapshot_id", "extractor_identity")):
            raise VerificationError("coordinator status and retained manifest snapshot identity differ")

        route_status, _encoded, route_code = atlas.route_find(os.fspath(db), os.fspath(repo), route_fact_id, 2_147_483_647)
        if route_code != 0:
            raise VerificationError("current Atlas route lookup returned refusal")
        if (route_status.get("result") != "fresh" or route_status.get("route_fact_id") != route_fact_id
                or route_status.get("snapshot_id") != manifest_identity.get("snapshot_id")
                or route_status.get("extractor_identity") != manifest_identity.get("extractor_identity")
                or route_status.get("association_count") != 1):
            raise VerificationError("current route-find is not one fresh accepted association for this exact route")

        paths, hashes = _artifact_hashes(job, coordinator)
        if expected_artifact_sha256 is not None:
            if not isinstance(expected_artifact_sha256, dict):
                raise VerificationError("expected_artifact_sha256 must be a complete prior hash dictionary")
            if (set(expected_artifact_sha256) != set(hashes)
                    or any(expected_artifact_sha256.get(key) != value for key, value in hashes.items())):
                raise VerificationError("retained job artifact keys or hashes differ from the expected prior proof")

        evidence = _json_object(_read_bytes(coordinator / "evidence-pack.json", job, "saved evidence packet"), "saved evidence packet")
        packet = _json_object(_read_bytes(coordinator / "review-packet.json", job, "saved review packet"), "saved review packet")
        identity_record = {key: manifest_identity[key] for key in ("snapshot_id", "extractor_identity")}
        catalogue, contextual = route_batch._canonical_citation_catalogue(
            {"identity": {**identity, **identity_record}}, evidence)
        legacy_luna_schema = route_autorun._luna_schema(identity_record, catalogue)
        sol_schema = route_batch._sol_schema(packet)

        luna = _worker_result(job, "luna_draft", job / "luna")[0]
        sol = _worker_result(job, "sol_review", job / "sol")[0]
        if luna["thread_id"] == sol["thread_id"]:
            raise VerificationError("Luna and Sol retained thread IDs are not distinct")
        if sol["schema"] != sol_schema:
            raise VerificationError("saved Sol schema differs from the current route schema")
        legacy_luna_prompt = _luna_prompt(identity_record, route_fact_id, evidence, catalogue,
                                           contextual, legacy_luna_schema)
        if luna["schema"] == legacy_luna_schema:
            if luna["prompt"] == legacy_luna_prompt:
                luna_prompt_revision = route_autorun.LUNA_LEGACY_PROMPT_REVISION
            elif luna["prompt"] == route_autorun.ground_luna_prompt(legacy_luna_prompt):
                luna_prompt_revision = route_autorun.LUNA_PROMPT_REVISION
            else:
                raise VerificationError("saved Luna prompt differs from the exact retained original-c5 or grounded-v1 request")
        else:
            current_cards = route_autorun._current_source_cards(repo, db, catalogue)
            current_luna_schema = route_autorun._current_luna_schema(identity_record, current_cards)
            current_luna_prompt = route_autorun._current_luna_prompt(
                legacy_luna_prompt, current_cards, current_luna_schema)
            if (luna["schema"] != current_luna_schema
                    or luna["prompt"] != current_luna_prompt):
                raise VerificationError("saved Luna schema or prompt differs from the exact CURRENT source-card request")
            luna_prompt_revision = route_autorun.LUNA_CURRENT_PROMPT_REVISION
        if luna["value"] != route_autorun._strict_json_object(
                _read_bytes(job / "luna" / "answer.txt", job, "Luna answer").decode("utf-8"), "Luna output"):
            raise VerificationError("Luna answer changed during verification")
        if luna_prompt_revision == route_autorun.LUNA_CURRENT_PROMPT_REVISION:
            route_autorun._validate_current_luna(
                luna["value"], identity_record, route_fact_id, current_cards, current_luna_schema)
        else:
            route_autorun._validate_luna(luna["value"], identity_record, route_fact_id, catalogue)

        luna_answer = _read_bytes(job / "luna" / "answer.txt", job, "Luna answer")
        luna_root = _read_bytes(job / "luna-draft.json", job, "root Luna draft")
        coordinator_luna = _read_bytes(coordinator / "luna-draft.json", job, "coordinator Luna draft")
        if luna_prompt_revision == route_autorun.LUNA_CURRENT_PROMPT_REVISION:
            reconstructed = route_autorun._current_luna_overlay_bytes(
                identity_record, current_cards, luna["value"])
            if luna_root != reconstructed or coordinator_luna != reconstructed:
                raise VerificationError("root and coordinator Luna drafts differ from the exact reconstructed source-card overlay")
        elif luna_answer != luna_root or luna_answer != coordinator_luna:
            raise VerificationError("worker, root, and coordinator Luna draft bytes differ")
        sol_answer = _read_bytes(job / "sol" / "answer.txt", job, "Sol answer")
        sol_root = _read_bytes(job / "sol-review.json", job, "root Sol review")
        coordinator_sol = _read_bytes(coordinator / "sol-review.json", job, "coordinator Sol review")
        if sol_answer != sol_root or sol_answer != coordinator_sol:
            raise VerificationError("worker, root, and coordinator Sol review bytes differ")

        review_identity = sol["value"].get("reviewer_identity")
        timestamp = sol["value"].get("reviewed_at")
        if (not isinstance(review_identity, str) or not SOL_ID_RE.fullmatch(review_identity)
                or not isinstance(timestamp, str)):
            raise VerificationError("Sol request identity or frozen timestamp is malformed")
        try:
            parsed_timestamp = dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise VerificationError("Sol frozen timestamp is not an ISO timestamp") from exc
        if parsed_timestamp.tzinfo is None or not timestamp.endswith("Z"):
            raise VerificationError("Sol frozen timestamp must be UTC with the exact Z suffix")
        expected_sol_prompt = _sol_prompt(packet, catalogue, contextual, sol_schema,
                                           review_identity, timestamp)
        if sol["prompt"] != expected_sol_prompt:
            raise VerificationError("saved Sol prompt differs from the exact current c5 request")
        route_autorun._validate_sol(sol["value"], packet, sol_schema, review_identity, timestamp)
        if sol["value"].get("decision") != "accepted":
            raise VerificationError("retained Sol review rejected the route")

        validation = _json_object(_read_bytes(coordinator / "review-validation.json", job,
                                               "review validation"), "review validation")
        checked, _encoded, code = atlas.route_map_review(os.fspath(db), os.fspath(repo),
                                                         os.fspath(coordinator / "review-packet.json"),
                                                         os.fspath(coordinator / "sol-review.json"))
        if code != 0 or checked.get("result") != "accepted" or checked != validation:
            raise VerificationError("current Atlas review validation does not match the retained accepted validation")
        if route_coordinator._expected_overlay(packet) != route_status.get("association", {}).get("binding", {}).get("overlay_id"):
            raise VerificationError("fresh route association does not match the retained review packet draft")
        publish = _json_object(_read_bytes(coordinator / "publish-result.json", job,
                                           "publish result"), "publish result")
        published_find = _json_object(_read_bytes(coordinator / "published-route-find.json", job,
                                                   "published route lookup"), "published route lookup")
        if (publish.get("result") != "published"
                or publish.get("route_fact_id") != route_fact_id
                or publish.get("snapshot_id") != manifest_identity.get("snapshot_id")
                or publish.get("overlay_id") != route_status.get("association", {}).get("binding", {}).get("overlay_id")
                or published_find.get("result") != "fresh"
                or published_find.get("route_fact_id") != route_fact_id
                or published_find.get("association", {}).get("binding") != route_status.get("association", {}).get("binding")):
            raise VerificationError("retained publication receipt or route lookup does not match current canonical status")

        return {
            "result": "verified_completed",
            "identity": {**identity, "snapshot_id": manifest_identity["snapshot_id"],
                         "extractor_identity": manifest_identity["extractor_identity"]},
            "status": current,
            "route_find": route_status,
            "luna": {"role": "luna_draft", "model": route_autorun.MODELS["luna_draft"],
                     "prompt_revision": luna_prompt_revision,
                     "thread_id": luna["thread_id"], "usage": luna["usage"],
                     "elapsed_ms": luna["elapsed_ms"]},
            "sol": {"role": "sol_review", "model": route_autorun.MODELS["sol_review"],
                    "thread_id": sol["thread_id"], "usage": sol["usage"],
                    "elapsed_ms": sol["elapsed_ms"]},
            "artifact_paths": paths,
            "artifact_sha256": hashes,
        }
    except Exception as exc:
        return _blocked(str(exc) or exc.__class__.__name__, paths, hashes)


# The batch ledger is intentionally separate from route_batch's native-worker
# ledger. It records only c5 run_once attempts and frozen completion proofs.
BATCH_MANIFEST = "batch-autorun.json"
BATCH_LOCK = ".batch-autorun.lock"


def _batch_safe(path: Path) -> Path:
    path = Path(os.path.abspath(os.fspath(path.expanduser())))
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"batch path contains a symlink: {current}")
    if path.resolve(strict=False) != path:
        raise ValueError(f"batch path is not canonical: {path}")
    return path


def _is_batch_temporary_residue(item: Path) -> bool:
    if not re.fullmatch(r"\.batch-autorun\.json\.[1-9][0-9]*\.[0-9a-f]{16}\.tmp", item.name):
        return False
    try:
        return not item.is_symlink() and stat.S_ISREG(item.lstat().st_mode)
    except OSError:
        return False


def _batch_atomic(path: Path, value: dict) -> None:
    raw = (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + "\n").encode("utf-8")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{os.urandom(8).hex()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def _batch_read(path: Path) -> dict:
    safe = _batch_safe(path)
    info = safe.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"batch manifest is not a regular file: {safe}")
    value = _json_object(safe.read_bytes(), "batch manifest")
    if (safe.read_bytes() != (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + "\n").encode("utf-8")):
        raise ValueError("batch manifest serialization is not canonical")
    return value


def _batch_identity(repo_arg, db_arg, route_ids, run_arg):
    ids = route_batch._route_ids(route_ids)
    repo, db = route_batch._repo_db(repo_arg, db_arg)
    run = _batch_safe(Path(run_arg))
    if not run.is_absolute() or run == repo or run.is_relative_to(repo) or repo.is_relative_to(run):
        raise ValueError("batch directory and repository must be canonical, separate paths")
    if run == db or run.is_relative_to(db) or db.is_relative_to(run):
        raise ValueError("batch directory and database must not overlap")
    snapshot, extractor, associations = route_batch._snapshot(repo, db)
    graph = snapshot.get("source_graph")
    facts = graph.get("facts") if isinstance(graph, dict) else None
    if not isinstance(facts, list):
        raise ValueError("current source snapshot has no route facts")
    for route_id in ids:
        matches = [fact for fact in facts if isinstance(fact, dict) and fact.get("id") == route_id]
        if len(matches) != 1 or matches[0].get("kind") != "route_action":
            raise ValueError(f"selected ID is not one unique current route_action fact: {route_id}")
    return ({"repository_root": os.fspath(repo), "database_path": os.fspath(db),
             "route_fact_ids": list(ids), "run_dir": os.fspath(run),
             "snapshot_id": snapshot.get("snapshot_id"), "extractor_identity": extractor},
            snapshot, associations, ids, run)


def _batch_report(manifest: dict, blocked: dict | None = None) -> dict:
    routes = []
    for route in manifest["routes"]:
        item = {"route_fact_id": route["route_fact_id"], "state": route["state"]}
        for key in ("job_dir", "result", "proof", "reason"):
            if key in route:
                item[key] = route[key]
        routes.append(item)
    report = {"result": "blocked" if blocked else (
                  "rejected" if any(item["state"] == "rejected" for item in routes) else
                  "completed" if all(item["state"] == "completed" for item in routes) else "in_progress"),
              "identity": manifest["identity"], "routes": routes}
    if blocked is not None:
        report["blocked"] = blocked
    return report


def run_batch(repo_arg, db_arg, route_ids, run_arg, cli_path=None, timeout_seconds=600):
    """Sequentially run and source-verify a selected batch of one to three routes."""
    import fcntl

    identity, snapshot, associations, ids, run = _batch_identity(repo_arg, db_arg, route_ids, run_arg)
    if type(timeout_seconds) is not int or timeout_seconds <= 0:
        return {"result": "blocked", "reason": "timeout_seconds must be a positive integer"}
    created = False
    try:
        run.parent.mkdir(parents=True, exist_ok=True)
        run.mkdir(mode=0o700, exist_ok=True)
        created = True
        _batch_safe(run)
        if not run.is_dir() or run.is_symlink():
            raise ValueError("batch run path must be a real directory")
        lock_path = _batch_safe(run / BATCH_LOCK)
        lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    except Exception as exc:
        return {"result": "blocked", "reason": str(exc)}

    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"result": "blocked", "reason": "another batch process holds the exclusive run lock"}
        manifest_path = run / BATCH_MANIFEST
        if manifest_path.exists():
            manifest = _batch_read(manifest_path)
            if (manifest.get("schema_version") != 1 or manifest.get("identity") != identity
                    or not isinstance(manifest.get("routes"), list)
                    or [r.get("route_fact_id") for r in manifest["routes"] if isinstance(r, dict)] != list(ids)
                    or len(manifest["routes"]) != len(ids)):
                raise ValueError("saved batch belongs to different source, path, or ordered route inputs")
            known = {BATCH_MANIFEST, BATCH_LOCK}
            for route in manifest["routes"]:
                if isinstance(route, dict) and isinstance(route.get("job_dir"), str):
                    known.add(Path(route["job_dir"]).name)
            extras = {item.name for item in run.iterdir()
                      if item.name not in known and not _is_batch_temporary_residue(item)}
            if extras:
                raise ValueError("batch directory contains unrecognized entries: " + ", ".join(sorted(extras)))
        else:
            extras = {item.name for item in run.iterdir()
                      if item.name != BATCH_LOCK and not _is_batch_temporary_residue(item)}
            if extras:
                raise ValueError("new batch directory contains foreign contents: " + ", ".join(sorted(extras)))
            route_batch._current_open_routes(snapshot, associations, ids)
            manifest = {"schema_version": 1, "identity": identity,
                        "routes": [{"route_fact_id": route_id, "state": "pending"} for route_id in ids]}
            _batch_atomic(manifest_path, manifest)

        for route in manifest["routes"]:
            route_id = route["route_fact_id"]
            job_dir = run / f"job-{ids.index(route_id) + 1:02d}-{route_id}"
            if route["state"] == "completed":
                proof = route.get("proof")
                hashes = proof.get("artifact_sha256") if isinstance(proof, dict) else None
                checked = verify_completed(os.fspath(identity["repository_root"]),
                                           os.fspath(identity["database_path"]), route_id,
                                           route.get("job_dir"), hashes)
                if checked.get("result") != "verified_completed":
                    return _batch_report(manifest, {"route_fact_id": route_id, "job_dir": route.get("job_dir"),
                                                    "reason": checked.get("reason", "saved completion proof failed")})
                route["proof"] = checked
                _batch_atomic(manifest_path, manifest)
                continue
            if route["state"] == "rejected":
                continue
            if route["state"] == "attempted":
                if (route.get("job_dir") != os.fspath(job_dir)
                        or not (job_dir.exists() or job_dir.is_symlink())):
                    return _batch_report(manifest, {"route_fact_id": route_id, "job_dir": route.get("job_dir"),
                                                    "reason": "attempted route has no bound existing job; refusing replacement calls"})
                recovered = verify_completed(os.fspath(identity["repository_root"]),
                                             os.fspath(identity["database_path"]), route_id,
                                             os.fspath(job_dir))
                if recovered.get("result") != "verified_completed":
                    return _batch_report(manifest, {"route_fact_id": route_id, "job_dir": os.fspath(job_dir),
                                                    "reason": "existing attempted job is inconclusive; refusing replacement calls"})
                route.update({"state": "completed", "result": {"result": "recovered_verified_completion"},
                              "proof": recovered})
                _batch_atomic(manifest_path, manifest)
                continue
            if route["state"] != "pending":
                return _batch_report(manifest, {"route_fact_id": route_id,
                                                "reason": "saved route state is inconclusive; refusing replay"})
            latest, extractor, current_associations = route_batch._snapshot(
                Path(identity["repository_root"]), Path(identity["database_path"]))
            if (latest.get("snapshot_id") != identity["snapshot_id"] or extractor != identity["extractor_identity"]):
                return _batch_report(manifest, {"route_fact_id": route_id, "reason": "source snapshot or extractor changed"})
            if job_dir.exists() or job_dir.is_symlink():
                recovered = verify_completed(os.fspath(identity["repository_root"]),
                                             os.fspath(identity["database_path"]), route_id,
                                             os.fspath(job_dir))
                if recovered.get("result") == "verified_completed":
                    route.update({"state": "completed", "job_dir": os.fspath(job_dir),
                                  "result": {"result": "recovered_verified_completion"}, "proof": recovered})
                    _batch_atomic(manifest_path, manifest)
                    continue
                return _batch_report(manifest, {"route_fact_id": route_id, "job_dir": os.fspath(job_dir),
                                                "reason": "existing attempted job is inconclusive; refusing replacement calls"})
            found, _encoded, code = atlas.route_find(identity["database_path"], identity["repository_root"], route_id, 2_147_483_647)
            if (code != 0 or found.get("snapshot_id") != identity["snapshot_id"]
                    or found.get("extractor_identity") != identity["extractor_identity"]
                    or found.get("result") != "unmapped" or found.get("association_count") != 0):
                return _batch_report(manifest, {"route_fact_id": route_id, "reason": "pending route is not currently open and source-bound"})
            route.update({"state": "attempted", "job_dir": os.fspath(job_dir)})
            _batch_atomic(manifest_path, manifest)
            try:
                actual = route_autorun.run_once(identity["repository_root"], identity["database_path"],
                                                route_id, os.fspath(job_dir), cli_path, timeout_seconds)
            except Exception as exc:
                return _batch_report(manifest, {"route_fact_id": route_id, "job_dir": os.fspath(job_dir),
                                                "reason": str(exc) or exc.__class__.__name__})
            if not isinstance(actual, dict):
                return _batch_report(manifest, {"route_fact_id": route_id, "job_dir": os.fspath(job_dir),
                                                "reason": "c5 runner returned a non-object result"})
            if actual.get("result") == "rejected":
                route.update({"state": "rejected", "result": actual})
                _batch_atomic(manifest_path, manifest)
                continue
            checked = verify_completed(identity["repository_root"], identity["database_path"],
                                       route_id, os.fspath(job_dir))
            if checked.get("result") != "verified_completed":
                return _batch_report(manifest, {"route_fact_id": route_id, "job_dir": os.fspath(job_dir),
                                                "reason": checked.get("reason", "completion checker refused the returned c5 job")})
            route.update({"state": "completed", "result": actual, "proof": checked})
            _batch_atomic(manifest_path, manifest)
        return _batch_report(manifest)
    except Exception as exc:
        try:
            if 'manifest' in locals() and isinstance(manifest, dict):
                return _batch_report(manifest, {"reason": str(exc) or exc.__class__.__name__})
        except Exception:
            pass
        return {"result": "blocked", "reason": str(exc) or exc.__class__.__name__}
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description="Run a source-bound selected Atlas route batch")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--route-id", action="append", required=True)
    parser.add_argument("--codex-cli")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args(argv)
    result = run_batch(args.repo, args.db, args.route_id, args.run_dir,
                       args.codex_cli, args.timeout_seconds)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2), flush=True)
    return 2 if result.get("result") == "blocked" else 1 if result.get("result") == "rejected" else 0


if __name__ == "__main__":
    raise SystemExit(main())
