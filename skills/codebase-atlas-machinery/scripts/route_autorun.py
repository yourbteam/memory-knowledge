"""One-shot, isolated Codex CLI worker calls."""

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import time

CLI = "/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex"
CLI_SHA256 = "6b582e8813ce7e8ed4c52814ee5cf230dba647bf2292df747a4003f2657ef201"
MODELS = {"luna_draft": "gpt-6-luna", "sol_review": "gpt-6.1-sol"}
USAGE_FIELDS = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens",
                "output_tokens", "reasoning_output_tokens")


def _reject(reason):
    return {"accepted": False, "reason": reason}


def admit_terminal(events: list[dict], final_text: str) -> dict:
    """Admit one ordered, completed, tool-free turn matching the answer file."""
    if not isinstance(events, list) or not events or not isinstance(final_text, str):
        return _reject("empty or invalid event stream or final text")
    threads, starts, messages, terminals, completed_items = [], [], [], [], []
    for event_index, event in enumerate(events):
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            return _reject("malformed event")
        kind = event["type"]
        if kind == "thread.started":
            threads.append(event)
        elif kind == "turn.started":
            starts.append(event)
        elif kind == "turn.completed":
            terminals.append(event)
        elif kind == "item.completed":
            completed_items.append(event_index)
            item = event.get("item")
            if not isinstance(item, dict):
                return _reject("malformed completed item")
            item_type = item.get("type")
            if item_type == "agent_message":
                messages.append((event, item))
            elif item_type not in ("reasoning", "todo_list"):
                return _reject("tool, error, or unknown completed item")
        else:
            return _reject("unknown, failed, or nonterminal event")
    if len(threads) != 1 or not isinstance(threads[0].get("thread_id"), str) or not threads[0]["thread_id"]:
        return _reject("missing or conflicting thread identity")
    if len(starts) != 1 or not messages or len(terminals) != 1:
        return _reject("expected one thread, turn start, at least one agent message, and terminal")
    start_index = events.index(starts[0])
    message_indexes = [events.index(event) for event, _item in messages]
    terminal_index = events.index(terminals[0])
    if not (events.index(threads[0]) < start_index < message_indexes[0] <= message_indexes[-1] < terminal_index == len(events) - 1):
        return _reject("events are out of order or terminal is not last")
    if any(not start_index < item_index < terminal_index for item_index in completed_items):
        return _reject("completed item is outside the active turn")
    if messages[-1][1].get("text") != final_text:
        return _reject("final message does not match answer file")
    usage = terminals[0].get("usage")
    if usage is not None:
        if not isinstance(usage, dict):
            return _reject("reported usage is not an object or null")
        for key in USAGE_FIELDS:
            if key in usage and (type(usage[key]) is not int or usage[key] < 0):
                return _reject("reported usage contains an invalid integer field")
        usage = dict(usage)
    return {"accepted": True, "thread_id": threads[0]["thread_id"],
            "final_text": messages[-1][1].get("text"), "usage": usage}


def _new_job_path(job_arg):
    if not isinstance(job_arg, str) or not os.path.isabs(job_arg):
        raise ValueError("job_arg must be an absolute path")
    path = Path(job_arg)
    if str(path) != os.path.normpath(job_arg) or path.resolve(strict=False) != path:
        raise ValueError("job_arg must be canonical and contain no symlink components")
    if path.exists() or path.is_symlink():
        raise FileExistsError("job directory already exists; refusing replacement")
    return path


def _write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _cli_schema(schema):
    """Return a CLI-compatible equivalent without mutating the canonical schema."""
    schema_keywords = {
        "additionalProperties", "contains", "else", "if", "items", "not", "then",
        "properties", "patternProperties", "dependentSchemas", "allOf", "anyOf",
        "oneOf", "prefixItems",
    }

    def convert(node):
        if not isinstance(node, dict):
            return node
        result = {}
        for key, value in node.items():
            if key == "const":
                if type(value) is str:
                    result["type"] = "string"
                    result["const"] = value
                elif type(value) is int:
                    result["type"] = "integer"
                    result["const"] = value
                elif type(value) is dict and all(isinstance(name, str) for name in value):
                    result["type"] = "object"
                    result["additionalProperties"] = False
                    result["required"] = list(value)
                    result["properties"] = {name: convert({"const": item})
                                             for name, item in value.items()}
                else:
                    raise ValueError("output schema contains an unsupported const value for CLI transport")
            elif key in schema_keywords:
                if isinstance(value, dict):
                    if key == "properties" or key == "patternProperties" or key == "dependentSchemas":
                        result[key] = {name: convert(child) for name, child in value.items()}
                    else:
                        result[key] = convert(value)
                elif isinstance(value, list):
                    result[key] = [convert(child) if isinstance(child, dict) else child for child in value]
                else:
                    result[key] = value
            else:
                result[key] = value
        return result

    return convert(schema)


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_worker(role: str, prompt: str, job_arg: str, cli_path: str | None = None,
               timeout_seconds: int = 600, output_schema: dict | None = None) -> dict:
    """Run one fresh configured CLI call in a caller-provided exclusive job."""
    if role not in MODELS:
        raise ValueError("unsupported worker role")
    if not isinstance(prompt, str):
        raise TypeError("prompt must be text")
    if type(timeout_seconds) is not int or timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be a positive integer")
    if output_schema is not None and not isinstance(output_schema, dict):
        raise TypeError("output_schema must be a dictionary or None")
    job = _new_job_path(job_arg)
    executable = Path(cli_path if cli_path is not None else CLI)
    if not executable.is_absolute() or executable.resolve(strict=False) != executable:
        raise ValueError("CLI path must be absolute and canonical")
    try:
        mode = executable.stat().st_mode
    except OSError as exc:
        raise ValueError("approved CLI is unavailable") from exc
    if not stat.S_ISREG(mode) or not os.access(executable, os.X_OK) or _sha256(executable) != CLI_SHA256:
        raise ValueError("CLI is not the executable owner-approved binary")

    # Claim the job before starting any process. Artifacts remain in the job parent;
    # Codex receives a separate empty workspace child.
    job.mkdir(parents=True, exist_ok=False)
    workspace = job / "workspace"
    workspace.mkdir()
    prompt_path, argv_path = job / "prompt.txt", job / "argv.json"
    events_path, stderr_path = job / "events.jsonl", job / "stderr.txt"
    answer_path, elapsed_path = job / "answer.txt", job / "elapsed_ms.json"
    schema_path = job / "schema.json" if output_schema is not None else None
    cli_schema_path = job / "cli-schema.json" if output_schema is not None else None
    if schema_path is not None:
        _write_json(schema_path, output_schema)
        _write_json(cli_schema_path, _cli_schema(output_schema))
    prompt_path.write_text(prompt, encoding="utf-8")
    answer_path.write_text("", encoding="utf-8")
    argv = [str(executable), "exec", "--ignore-user-config", "--ignore-rules", "--ephemeral",
            "--skip-git-repo-check", "--sandbox", "read-only", "--model", MODELS[role],
            "-c", 'model_reasoning_effort="high"', "-c", "project_doc_max_bytes=0",
            "-c", "features.shell_tool=false", "-c", 'web_search="disabled"',
            "--cd", str(workspace), "--json", "--output-last-message", str(answer_path), "-"]
    if cli_schema_path is not None:
        argv[-1:-1] = ["--output-schema", str(cli_schema_path)]
    _write_json(argv_path, argv)
    started = time.monotonic()
    try:
        with events_path.open("x", encoding="utf-8") as stdout, stderr_path.open("x", encoding="utf-8") as stderr:
            process = subprocess.run(argv, input=prompt, text=True, stdout=stdout, stderr=stderr,
                                     timeout=timeout_seconds, check=False)
    finally:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        _write_json(elapsed_path, {"elapsed_ms": elapsed_ms})
    if process.returncode != 0:
        raise RuntimeError("CLI exited unsuccessfully; evidence retained at " + str(job))
    try:
        events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        final_text = answer_path.read_text(encoding="utf-8")
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError("CLI evidence is inconclusive; evidence retained at " + str(job)) from exc
    admission = admit_terminal(events, final_text)
    if not admission["accepted"]:
        raise RuntimeError(admission["reason"] + "; evidence retained at " + str(job))
    files = (prompt_path, argv_path, events_path, stderr_path, answer_path, elapsed_path)
    if schema_path is not None:
        files += (schema_path, cli_schema_path)
    artifact_sha256 = {p.name: _sha256(p) for p in files}
    completion_register = {"schema_version": 1, "kind": "completed-native-worker-turn",
            "worker_directory": job.name, "role": role, "model": MODELS[role],
            "thread_id": admission["thread_id"], "prompt_sha256": _sha256(prompt_path),
            "schema_sha256": _sha256(schema_path) if schema_path is not None else None,
            "argv_sha256": _sha256(argv_path), "answer_sha256": _sha256(answer_path),
            "events_sha256": _sha256(events_path), "artifact_sha256": artifact_sha256}
    register_path = job.with_name(job.name + ".completion-register.json")
    raw_register = (json.dumps(completion_register, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    fd = os.open(register_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw_register); stream.flush(); os.fsync(stream.fileno())
    return {"role": role, "model": MODELS[role], "thread_id": admission["thread_id"],
            "final_text": admission["final_text"], "usage": admission["usage"], "elapsed_ms": elapsed_ms,
            "artifact_dir": str(job), "artifact_paths": {p.name: str(p) for p in files},
            "artifact_sha256": artifact_sha256, "completion_register_path": str(register_path),
            "completion_register_sha256": hashlib.sha256(raw_register).hexdigest()}


def _strict_json_object(text, label):
    class DuplicateKeyError(ValueError):
        pass

    def reject_duplicates(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise DuplicateKeyError("duplicate JSON key")
            value[key] = item
        return value

    try:
        value = json.loads(text, object_pairs_hook=reject_duplicates)
    except (json.JSONDecodeError, DuplicateKeyError, TypeError) as exc:
        raise ValueError(label + " must be exactly one JSON object without duplicate keys or code fences") from exc
    if not isinstance(value, dict):
        raise ValueError(label + " must be exactly one JSON object")
    return value


def _save_exact(path, raw):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _citation_shape(entry):
    return {
        "type": "object", "additionalProperties": False, "required": ["fact_id", "source"],
        "properties": {"fact_id": {"const": entry["fact_id"]}, "source": {"const": entry["source"]}},
    }


LUNA_PROMPT_REVISION = "grounded-v1"

LUNA_LEGACY_PROMPT_REVISION = "original-c5"


def ground_luna_prompt(prompt: str) -> str:
    """Add the shared source-grounding guidance to a Luna request."""
    warning = (
        "Ground every claim in what its cited source syntax establishes. A typed identifier or "
        "injection-candidate span alone does not establish a field or property declaration, "
        "constructor or receiver binding, resolved call target, or effective dependency-injection "
        "selection. Do not upgrade lexical candidates to resolved compiler or runtime facts; keep "
        "uncertainty in the evidence packet visible.\n\n"
    )
    return warning + prompt





def _luna_schema(identity, catalogue):
    return {
        "type": "object", "additionalProperties": False,
        "required": ["overlay_schema_version", "snapshot_id", "extractor_identity", "title", "reviewed_conclusions"],
        "properties": {
            "overlay_schema_version": {"const": 1},
            "snapshot_id": {"const": identity["snapshot_id"]},
            "extractor_identity": {"const": identity["extractor_identity"]},
            "title": {"type": "string", "minLength": 1},
            "reviewed_conclusions": {"type": "array", "minItems": 1, "items": {
                "type": "object", "additionalProperties": False, "required": ["claim", "evidence"],
                "properties": {
                    "claim": {"type": "string", "minLength": 1},
                    "evidence": {"type": "array", "minItems": 1, "items": {
                        "anyOf": [_citation_shape(entry) for entry in catalogue],
                    }},
                },
            }},
        },
    }


def _current_source_cards(repo, db, catalogue):
    """Bind every canonical catalogue fact to its exact current source literal."""
    import route_batch
    import atlas

    snapshot, _extractor, _associations = route_batch._snapshot(repo, db)
    graph = snapshot.get("source_graph")
    facts = graph.get("facts") if isinstance(graph, dict) else None
    if not isinstance(facts, list):
        raise ValueError("current source snapshot has no source graph facts")
    cards = []
    for entry in catalogue:
        fact_id, source = entry.get("fact_id"), entry.get("source")
        if not isinstance(fact_id, str) or not isinstance(source, dict):
            raise ValueError("canonical catalogue contains an incomplete fact identity")
        matches = [fact for fact in facts if isinstance(fact, dict) and fact.get("id") == fact_id]
        if len(matches) != 1:
            raise ValueError(f"current source graph fact identity is missing or duplicated: {fact_id}")
        fact = matches[0]
        if fact.get("source") != source:
            raise ValueError(f"canonical source identity differs from the current graph fact: {fact_id}")
        kind = fact.get("kind")
        if not isinstance(kind, str) or not kind.strip():
            raise ValueError(f"current graph fact has no lexical kind: {fact_id}")
        snippets = atlas._source_texts(repo, [(fact_id, source)])
        literals = [snippet.get("text") for snippet in snippets
                    if snippet.get("fact_id") == fact_id
                    and {key: snippet.get(key) for key in ("path", "sha256", "span")} == source]
        if len(literals) != 1 or not isinstance(literals[0], str) or not literals[0].strip():
            raise ValueError(f"canonical fact has no unique nonempty verified source literal: {fact_id}")
        claim = (f"Canonical source fact {fact_id} has verified literal source syntax "
                 f"{json.dumps(literals[0], ensure_ascii=False)}. "
                 "Source syntax alone does not establish compiler or runtime semantics.")
        cards.append({"fact_id": fact_id, "kind": kind, "claim": claim,
                      "evidence": {"fact_id": fact_id, "source": source}})
    return cards











def _validate_luna(value, identity, route_fact_id, catalogue):
    required = {"overlay_schema_version", "snapshot_id", "extractor_identity", "title", "reviewed_conclusions"}
    if set(value) != required or value.get("overlay_schema_version") != 1:
        raise ValueError("Luna output does not match the closed route-map draft shape")
    if (value.get("snapshot_id") != identity.get("snapshot_id")
            or value.get("extractor_identity") != identity.get("extractor_identity")):
        raise ValueError("Luna output is bound to another snapshot or extractor")
    if not isinstance(value.get("title"), str) or not value["title"].strip():
        raise ValueError("Luna route-map title must be nonempty text")
    allowed = {(entry["fact_id"], json.dumps(entry["source"], sort_keys=True, separators=(",", ":")))
               for entry in catalogue}
    conclusions = value.get("reviewed_conclusions")
    if not isinstance(conclusions, list) or not conclusions:
        raise ValueError("Luna route map must contain at least one conclusion")
    selected_route_cited = False
    for conclusion in conclusions:
        if (not isinstance(conclusion, dict) or set(conclusion) != {"claim", "evidence"}
                or not isinstance(conclusion.get("claim"), str) or not conclusion["claim"].strip()
                or not isinstance(conclusion.get("evidence"), list) or not conclusion["evidence"]):
            raise ValueError("Luna conclusion does not match the closed claim and evidence shape")
        for citation in conclusion["evidence"]:
            if not isinstance(citation, dict) or set(citation) != {"fact_id", "source"}:
                raise ValueError("Luna citation does not match the canonical citation shape")
            key = (citation.get("fact_id"), json.dumps(citation.get("source"), sort_keys=True, separators=(",", ":")))
            if key not in allowed:
                raise ValueError("Luna citation is not an exact canonical citation")
            selected_route_cited = selected_route_cited or citation["fact_id"] == route_fact_id
    if not selected_route_cited:
        raise ValueError("Luna route map does not cite the selected route fact")


def _validate_sol(value, packet, schema, request_identity, timestamp):
    required = set(schema["required"])
    if set(value) != required:
        raise ValueError("Sol output does not match the closed independent-review shape")
    for key in ("review_schema_version", "packet_sha256", "evidence_sha256", "draft_sha256", "reviewer_model"):
        expected = schema["properties"][key].get("const")
        if value.get(key) != expected:
            raise ValueError("Sol output does not match the exact review packet identity")
    if value.get("review_schema_version") != 1:
        raise ValueError("Sol output has an unsupported review schema version")
    if value.get("reviewer_identity") != request_identity or value.get("reviewed_at") != timestamp:
        raise ValueError("Sol output changed the frozen review-request identity or timestamp")
    if value.get("reviewer_model") != "GPT-6.1 Sol High" or value.get("decision") not in {"accepted", "rejected"}:
        raise ValueError("Sol output has an invalid reviewer model or decision")

    def check_decision(item):
        if (not isinstance(item, dict) or set(item) != {"decision", "basis"}
                or item.get("decision") not in {"accepted", "rejected"}
                or not isinstance(item.get("basis"), str) or not 20 <= len(item["basis"]) <= 2000):
            raise ValueError("Sol output contains an invalid independent decision")

    check_decision(value.get("assignment_review"))
    check_decision(value.get("route_association_review"))
    claims = packet.get("claims")
    reviews = value.get("conclusion_reviews")
    if not isinstance(claims, list) or not isinstance(reviews, list) or len(reviews) != len(claims):
        raise ValueError("Sol output does not review every packet conclusion")
    for number, review in enumerate(reviews, 1):
        if (not isinstance(review, dict) or set(review) != {"conclusion_number", "decision", "basis"}
                or type(review.get("conclusion_number")) is not int
                or review["conclusion_number"] != number
                or review.get("decision") not in {"accepted", "rejected"}
                or not isinstance(review.get("basis"), str)
                or not 20 <= len(review["basis"]) <= 2000):
            raise ValueError("Sol output contains an invalid or unordered conclusion decision")
    return value


def run_once(repo_arg: str, db_arg: str, route_fact_id: str, job_arg: str,
             cli_path: str | None = None, timeout_seconds: int = 600) -> dict:
    """Run one fresh Luna draft and Sol review through the existing route coordinator."""
    import datetime as dt
    import uuid

    import route_batch
    import route_coordinator

    job = _new_job_path(job_arg)
    repo = route_coordinator._canonical_repo(repo_arg)
    if job == repo or job.is_relative_to(repo) or repo.is_relative_to(job):
        raise ValueError("job directory and target repository must not contain or overlap each other")
    if type(timeout_seconds) is not int or timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be a positive integer")
    job.mkdir(parents=True, exist_ok=False)
    coordinator_dir = job / "coordinator"
    prepared = route_coordinator.prepare(repo_arg, db_arg, route_fact_id, str(coordinator_dir))
    if prepared.get("result") != "prepared" or not isinstance(prepared.get("identity"), dict):
        raise RuntimeError("route coordinator did not prepare the selected route")
    identity = prepared["identity"]
    evidence_path = coordinator_dir / "evidence-pack.json"
    evidence_raw = evidence_path.read_bytes()
    evidence = _strict_json_object(evidence_raw.decode("utf-8"), "saved evidence packet")
    catalogue, contextual_sources = route_batch._canonical_citation_catalogue(
        {"identity": identity}, evidence)
    luna_schema = _luna_schema(identity, catalogue)
    luna_prompt = (
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
        json.dumps(contextual_sources, ensure_ascii=False, sort_keys=True, indent=2) +
        "\n\nROUTE-MAP JSON SCHEMA:\n" + json.dumps(luna_schema, ensure_ascii=True, sort_keys=True, indent=2)
    )
    luna_cards = _current_source_cards(repo, Path(identity["database_path"]), catalogue)
    current_luna_schema = _current_luna_schema(identity, luna_cards)
    current_luna_prompt = _current_luna_prompt(luna_prompt, luna_cards, current_luna_schema)
    luna = run_worker("luna_draft", current_luna_prompt, str(job / "luna"), cli_path, timeout_seconds,
                      output_schema=current_luna_schema)
    luna_value = _strict_json_object(luna["final_text"], "Luna selector")
    _validate_current_luna(luna_value, identity, route_fact_id, luna_cards, current_luna_schema)
    luna_path = job / "luna-draft.json"
    _save_exact(luna_path, _current_luna_overlay_bytes(identity, luna_cards, luna_value))
    draft_result = route_coordinator.draft(repo_arg, db_arg, route_fact_id,
                                           str(coordinator_dir), str(luna_path))
    if draft_result.get("result") != "review_ready":
        raise RuntimeError("route coordinator did not produce the independent review packet")

    packet_path = coordinator_dir / "review-packet.json"
    packet_raw = packet_path.read_bytes()
    packet = _strict_json_object(packet_raw.decode("utf-8"), "saved review packet")
    review_schema = route_batch._sol_schema(packet)
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    review_identity = "run_once-sol-" + uuid.uuid4().hex
    sol_prompt = (
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
        json.dumps(contextual_sources, ensure_ascii=False, sort_keys=True, indent=2) +
        "\n\nREVIEW JSON SCHEMA:\n" + json.dumps(review_schema, ensure_ascii=True, sort_keys=True, indent=2)
    )
    sol = run_worker("sol_review", sol_prompt, str(job / "sol"), cli_path, timeout_seconds,
                     output_schema=review_schema)
    sol_raw = sol["final_text"].encode("utf-8")
    sol_path = job / "sol-review.json"
    _save_exact(sol_path, sol_raw)
    sol_value = _strict_json_object(sol["final_text"], "Sol output")
    _validate_sol(sol_value, packet, review_schema, review_identity, timestamp)
    if luna["thread_id"] == sol["thread_id"]:
        raise RuntimeError("Luna and Sol worker calls did not produce distinct thread identities")
    if luna["role"] != "luna_draft" or sol["role"] != "sol_review":
        raise RuntimeError("worker results do not match their configured roles")
    publication = route_coordinator.publish(repo_arg, db_arg, route_fact_id,
                                           str(coordinator_dir), str(sol_path))
    result = {"result": publication.get("result"), "route_fact_id": route_fact_id,
              "identity": identity, "review_request_identity": review_identity,
              "luna": luna, "sol": sol, "publication": publication}
    if publication.get("result") == "rejected":
        return result
    if publication.get("result") != "published_and_fresh":
        raise RuntimeError("route coordinator did not publish and retrieve a fresh route map")
    current = route_coordinator.status(repo_arg, db_arg, route_fact_id, str(coordinator_dir))
    if current.get("result") != "published_and_fresh":
        raise RuntimeError("route coordinator status did not corroborate fresh publication")
    result["status"] = current
    return result


LUNA_CURRENT_PROMPT_REVISION = "source-selector-derived-v2"


def _current_luna_schema(identity, cards):
    fact_ids = [card["fact_id"] for card in cards]
    if (not fact_ids or any(not isinstance(fact_id, str) for fact_id in fact_ids)
            or len(set(fact_ids)) != len(fact_ids)):
        raise ValueError("current source cards must have unique canonical fact IDs")
    return {
        "type": "object", "additionalProperties": False,
        "required": ["selector_schema_version", "snapshot_id", "extractor_identity", "selected_fact_ids"],
        "properties": {
            "selector_schema_version": {"const": 1},
            "snapshot_id": {"const": identity["snapshot_id"]},
            "extractor_identity": {"const": identity["extractor_identity"]},
            "selected_fact_ids": {"type": "array", "minItems": len(fact_ids), "maxItems": len(fact_ids),
                                  "items": {"type": "string", "enum": fact_ids}},
        },
    }


def _current_luna_prompt(legacy_prompt, cards, schema):
    return (legacy_prompt +
            "\n\nCURRENT SOURCE-SELECTOR CONTRACT (authoritative for this request):\n"
            "The legacy schema and prose above provide the complete prepared evidence and context. "
            "They do not govern the output. Return only the exact CURRENT selector schema below. "
            "Select and order every supplied canonical source-card fact ID exactly once, including the selected route fact. "
            "Do not copy, paraphrase, shorten, or reproduce card claims, citations, or source bytes. "
            "The host validates the complete selection and assembles the derived source-card overlay.\n\n"
            "CURRENT SOURCE CARDS (complete verified metadata and contextual limits):\n" +
            json.dumps(cards, ensure_ascii=False, sort_keys=True, indent=2) +
            "\n\nCURRENT SELECTOR JSON SCHEMA (authoritative):\n" +
            json.dumps(schema, ensure_ascii=True, sort_keys=True, indent=2))


def _validate_current_luna(value, identity, route_fact_id, cards, schema):
    required = {"selector_schema_version", "snapshot_id", "extractor_identity", "selected_fact_ids"}
    if (not isinstance(value, dict) or set(value) != required
            or type(value.get("selector_schema_version")) is not int
            or value.get("selector_schema_version") != 1):
        raise ValueError("CURRENT Luna selector does not match the closed selector shape")
    if (not isinstance(value.get("snapshot_id"), str)
            or not isinstance(value.get("extractor_identity"), str)
            or value["snapshot_id"] != identity.get("snapshot_id")
            or value["extractor_identity"] != identity.get("extractor_identity")):
        raise ValueError("CURRENT Luna selector source identity differs from its request")
    expected = [card.get("fact_id") for card in cards]
    selected = value.get("selected_fact_ids")
    if (not expected or any(not isinstance(fact_id, str) for fact_id in expected)
            or len(set(expected)) != len(expected)
            or not isinstance(selected, list) or len(selected) != len(expected)
            or any(not isinstance(fact_id, str) for fact_id in selected)
            or len(set(selected)) != len(selected) or set(selected) != set(expected)
            or route_fact_id not in selected):
        raise ValueError("CURRENT Luna selector must select every canonical fact exactly once, including the selected route")


def _current_luna_overlay_bytes(identity, cards, selection):
    by_id = {card["fact_id"]: card for card in cards}
    conclusions = []
    for fact_id in selection["selected_fact_ids"]:
        card = by_id[fact_id]
        conclusions.append({"claim": card["claim"], "evidence": [card["evidence"]]})
    overlay = {
        "overlay_schema_version": 1,
        "snapshot_id": identity["snapshot_id"],
        "extractor_identity": identity["extractor_identity"],
        "title": "Atlas source cards",
        "reviewed_conclusions": conclusions,
    }
    return (json.dumps(overlay, indent=2, sort_keys=True) + "\n").encode("utf-8")


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description="Run one fresh Luna draft and Sol review for an Atlas route")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--route-fact-id", required=True)
    parser.add_argument("--job-dir", required=True)
    parser.add_argument("--codex-cli")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args(argv)
    result = run_once(args.repo, args.db, args.route_fact_id, args.job_dir,
                      args.codex_cli, args.timeout_seconds)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
