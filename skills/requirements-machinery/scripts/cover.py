#!/usr/bin/env python3
"""The front door. Cut a document into pieces, then answer for every one of them.

Nothing comes out of it until every piece has an answer. Which pieces are answered, and by whom,
is always visible — that is how you find what is missing. What the answers say is not, until
nothing is missing.

    cover.py open   --source <document> --work <dir>
    cover.py status --work <dir>
    cover.py answer --work <dir> --piece p-0007 --by "reader-1" --quote "<words from the page>" --what "..."
    cover.py run    --work <dir> --target "<document being built>" --out <requirements.md> --reader-command '<command>'
    cover.py report --work <dir>

State lives in <dir>. Stopping and coming back later is the same as never stopping.
"""
import os
import argparse, hashlib, importlib.util, json, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
PARTIAL_SPLIT_POLICY = "atomic-conservation-v1"
CORRECT_OWNER_POLICY = "dedicated-correct-owner-v1"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


splitter = _load("splitter")
register = _load("register")
quotecheck = _load("quotecheck")
reflow = _load("reflow")
STATE = "coverage.json"


class Refused(Exception):
    """A refusal raised where a return value cannot carry it. main() turns it into exit 3, so
    every refusal in this file leaves by the same door and a caller sees one number, not two."""


def _state_path(work):
    return Path(work) / STATE


def _read(work):
    path = _state_path(work)
    if not path.exists():
        print(f"no register at {path}. Run `cover.py open --source <document> --work {work}` "
              f"first.", file=sys.stderr)
        raise Refused()
    state = json.loads(path.read_text())
    _validate_run_identity(work, state)
    try:
        _validate_split_checkability_records(state)
    except (KeyError, TypeError, ValueError) as exc:
        print(f"refusing invalid stored split-child checkability evidence: {exc}", file=sys.stderr)
        raise Refused()
    return state


def _canonical_sha256(value):
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _projection_runtime_manifest(root):
    files = []
    for path in sorted((root / "scripts").glob("*.py")):
        files.append({
            "path": path.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size": path.stat().st_size,
        })
    policy = root / "client-model-policy.json"
    if policy.is_file():
        files.append({
            "path": policy.name,
            "sha256": hashlib.sha256(policy.read_bytes()).hexdigest(),
            "size": policy.stat().st_size,
        })
    return {"schema_version": 1, "files": files}


def _pin_projection_runtime(work):
    """Use one immutable projection identity for every stage of one persisted run."""
    global HERE
    destination = Path(work) / ".projection-runtime-v1"
    if HERE.parent == destination:
        expected = json.loads((destination / "manifest.json").read_text())
        if _projection_runtime_manifest(destination) != expected:
            raise Refused("the run's projection snapshot changed; restore its recorded bytes")
        return
    if destination.exists():
        expected = json.loads((destination / "manifest.json").read_text())
        if _projection_runtime_manifest(destination) != expected:
            raise Refused("the run's projection snapshot changed; restore its recorded bytes")
        HERE = destination / "scripts"
        return
    source = HERE.parent
    temporary = Path(tempfile.mkdtemp(prefix=".projection-runtime-v1.", dir=work))
    shutil.copytree(source / "scripts", temporary / "scripts",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    policy = source / "client-model-policy.json"
    if policy.is_file():
        shutil.copy2(policy, temporary / policy.name)
    manifest = _projection_runtime_manifest(temporary)
    (temporary / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    for path in temporary.rglob("*"):
        path.chmod(0o555 if path.is_dir() else 0o444)
    os.replace(temporary, destination)
    HERE = destination / "scripts"


def _build_split_graph(target, decision_id, parent_index, items, child_indexes):
    """Bind one split ruling to its parent and exact persisted children."""
    body = {
        "schema_version": 1,
        "target": target,
        "decision_id": decision_id,
        "parent_index": parent_index,
        "child_indexes": list(child_indexes),
        "children": [
            {
                "index": index,
                "statement_sha256": hashlib.sha256(
                    items[index]["statement"].encode("utf-8")
                ).hexdigest(),
                "checkability_record_sha256": items[index]["checkability_record"][
                    "record_sha256"
                ],
            }
            for index in child_indexes
        ],
    }
    return {**body, "record_sha256": _canonical_sha256(body)}


def _validate_split_checkability_records(state):
    """Reconcile every persisted split graph before a resumed command can spend a reader."""
    checkability_mod = _load("checkability")
    distilled_by_target = state.get("distilled", {})
    rulings_by_target = state.get("owner_rulings", {})
    if not isinstance(distilled_by_target, dict) or not isinstance(rulings_by_target, dict):
        raise ValueError("split lineage containers must be objects")
    for target, distilled in distilled_by_target.items():
        if not isinstance(distilled, dict) or not isinstance(distilled.get("items"), list):
            raise ValueError(f"distilled items for {target!r} must be one list")
        items = distilled["items"]
        target_rulings = rulings_by_target.get(target, {})
        if not isinstance(target_rulings, dict):
            raise ValueError(f"owner rulings for {target!r} must be one object")
        bound_parents, bound_children = set(), set()
        for decision_id, ruling in target_rulings.items():
            if not isinstance(ruling, dict) or ruling.get("choice") != "split":
                continue
            graph = ruling.get("split_graph")
            if not isinstance(graph, dict):
                raise ValueError(f"split ruling {decision_id!r} has no integrity-bound graph")
            expected_graph_keys = {
                "schema_version", "target", "decision_id", "parent_index", "child_indexes",
                "children", "record_sha256",
            }
            if set(graph) != expected_graph_keys:
                raise ValueError(f"split ruling {decision_id!r} graph has the wrong shape")
            body = {key: graph[key] for key in graph if key != "record_sha256"}
            if graph["record_sha256"] != _canonical_sha256(body):
                raise ValueError(f"split ruling {decision_id!r} graph hash disagrees with its body")
            if graph["schema_version"] != 1 or graph["target"] != target:
                raise ValueError(f"split ruling {decision_id!r} graph identity disagrees with state")
            if graph["decision_id"] != decision_id:
                raise ValueError(f"split ruling {decision_id!r} graph decision identity disagrees")
            parent_index = graph["parent_index"]
            child_indexes = graph["child_indexes"]
            descriptors = graph["children"]
            if type(parent_index) is not int or not 0 <= parent_index < len(items):
                raise ValueError(f"split ruling {decision_id!r} has an invalid parent index")
            if not isinstance(child_indexes, list) or not child_indexes:
                raise ValueError(f"split ruling {decision_id!r} has no child indexes")
            if any(type(index) is not int or not 0 <= index < len(items)
                   for index in child_indexes):
                raise ValueError(f"split ruling {decision_id!r} has an invalid child index")
            if len(set(child_indexes)) != len(child_indexes) or parent_index in child_indexes:
                raise ValueError(f"split ruling {decision_id!r} repeats a lineage index")
            if parent_index in bound_parents or any(index in bound_children for index in child_indexes):
                raise ValueError(f"split ruling {decision_id!r} overlaps another split graph")
            if not isinstance(descriptors, list) or len(descriptors) != len(child_indexes):
                raise ValueError(f"split ruling {decision_id!r} child descriptors disagree")
            parent = items[parent_index]
            if not isinstance(parent, dict) or parent.get("how") != "split":
                raise ValueError(f"split ruling {decision_id!r} parent is not marked split")
            if parent.get("split_into") != child_indexes:
                raise ValueError(f"split ruling {decision_id!r} parent links disagree with graph")
            if ruling.get("children") != len(child_indexes):
                raise ValueError(f"split ruling {decision_id!r} child count disagrees with graph")
            for descriptor, index in zip(descriptors, child_indexes):
                if not isinstance(descriptor, dict) or set(descriptor) != {
                    "index", "statement_sha256", "checkability_record_sha256"
                }:
                    raise ValueError(f"split child {index + 1} for {target!r} has a bad descriptor")
                if descriptor["index"] != index:
                    raise ValueError(f"split child {index + 1} index disagrees with graph")
                item = items[index]
                if not isinstance(item, dict) or item.get("split_from") != decision_id:
                    raise ValueError(f"split child {index + 1} lineage marker disagrees with graph")
                statement = item.get("statement")
                if not isinstance(statement, str) or not statement.strip():
                    raise ValueError(f"split child {index + 1} has no statement")
                statement_sha256 = hashlib.sha256(statement.encode("utf-8")).hexdigest()
                if descriptor["statement_sha256"] != statement_sha256:
                    raise ValueError(f"split child {index + 1} statement hash disagrees with graph")
                record = item.get("checkability_record")
                if not isinstance(record, dict):
                    raise ValueError(
                        f"split child {index + 1} for {target!r} has no checkability record")
                if descriptor["checkability_record_sha256"] != record.get("record_sha256"):
                    raise ValueError(f"split child {index + 1} record hash disagrees with graph")
                prompt = SPLIT_CHECKABLE_ASK.format(target=target, statement=statement)
                try:
                    checkability_mod.validate_binary(record, statement, target, prompt)
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(
                        f"split child {index + 1} for {target!r} has invalid "
                        f"checkability evidence: {exc}"
                    ) from exc
                decision = record["aggregate"][0]
                disposition = decision["disposition"]
                if item.get("checkable") is not (disposition == "keep"):
                    raise ValueError(
                        f"split child {index + 1} derived checkable flag disagrees with record")
                if disposition == "drop":
                    if item.get("refused_because") != "no ask kept it (0 of 3)":
                        raise ValueError(
                            f"split child {index + 1} drop explanation disagrees with record")
                elif "refused_because" in item:
                    raise ValueError(
                        f"split child {index + 1} has a drop explanation without a drop")
                if disposition == "owner":
                    expected = f"{decision['votes']} of 3 asks kept it — for the owner"
                    if item.get("checkable_doubt") != expected:
                        raise ValueError(
                            f"split child {index + 1} owner explanation disagrees with record")
                elif "checkable_doubt" in item:
                    raise ValueError(
                        f"split child {index + 1} has owner doubt without an owner disposition")
            bound_parents.add(parent_index)
            bound_children.update(child_indexes)
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"distilled item {index + 1} for {target!r} must be one object")
            if item.get("how") == "split" and index not in bound_parents:
                raise ValueError(f"split parent {index + 1} for {target!r} has no ruling graph")
            if "split_from" in item and index not in bound_children:
                raise ValueError(f"split child {index + 1} for {target!r} has no ruling graph")


def _identity_refusal(message):
    print(f"run identity drift: {message}", file=sys.stderr)
    raise Refused()


def _validate_run_identity(work, state):
    """Fail closed unless source bytes and the exact registered piece manifest still exist."""
    try:
        source = Path(state["source"])
        source_sha256 = state["source_sha256"]
        manifest = state["pieces"]
    except (KeyError, TypeError):
        _identity_refusal("state has no complete source and piece identity")
    if not source.is_absolute():
        _identity_refusal("stored source path is not absolute")
    if not source.is_file():
        _identity_refusal(f"registered source is missing: {source}")
    actual_source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if actual_source_hash != source_sha256:
        _identity_refusal(f"source hash mismatch: expected {source_sha256}, got {actual_source_hash}")
    ids = [piece.get("id") for piece in manifest]
    if any(not isinstance(piece_id, str) or not piece_id for piece_id in ids) or len(set(ids)) != len(ids):
        _identity_refusal("piece manifest has missing or duplicate identities")
    pieces_dir = Path(work) / "pieces"
    if not pieces_dir.is_dir():
        _identity_refusal("pieces directory is missing")
    expected_names = {f"{piece_id}.txt" for piece_id in ids}
    actual_names = {entry.name for entry in pieces_dir.iterdir()}
    missing = sorted(expected_names - actual_names)
    extra = sorted(actual_names - expected_names)
    if missing:
        _identity_refusal(f"missing piece file(s): {', '.join(missing)}")
    if extra:
        _identity_refusal(f"unregistered piece file(s): {', '.join(extra)}")
    for piece in manifest:
        piece_path = pieces_dir / f"{piece['id']}.txt"
        if piece_path.is_symlink() or not piece_path.is_file():
            _identity_refusal(f"piece is not a regular registered file: {piece['id']}")
        payload = piece_path.read_bytes()
        actual_hash = hashlib.sha256(payload).hexdigest()
        if actual_hash != piece.get("sha256"):
            _identity_refusal(
                f"piece hash mismatch for {piece['id']}: expected {piece.get('sha256')}, got {actual_hash}")
        try:
            chars = len(payload.decode("utf-8"))
        except UnicodeDecodeError:
            _identity_refusal(f"piece is not valid UTF-8: {piece['id']}")
        if chars != piece.get("chars"):
            _identity_refusal(
                f"piece character count mismatch for {piece['id']}: expected {piece.get('chars')}, got {chars}")


def _write(work, state):
    Path(work).mkdir(parents=True, exist_ok=True)
    _state_path(work).write_text(json.dumps(state, indent=1))


def _rebuild(state):
    reg = register.Register([{"id": p["id"]} for p in state["pieces"]])
    reg._answers = dict(state["answers"])
    return reg


def _read_source_text(source):
    suffix = source.suffix.lower()
    if suffix == ".pdf":
        return subprocess.run(
            ["pdftotext", "-layout", str(source), "-"],
            capture_output=True,
            check=True,
        ).stdout.decode("utf-8", "replace")
    if suffix == ".md":
        try:
            return source.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            print(f"refusing to open: Markdown source is not valid UTF-8: {source}", file=sys.stderr)
            return None
    print(
        f"refusing to open: unsupported source format {suffix or '<none>'}; "
        "supported formats are .pdf and .md",
        file=sys.stderr,
    )
    return None


_ARTIFACT_LINE = re.compile(r"(?m)^ARTIFACT\s+(\d+)\b")
_ARTIFACT_RECORD = re.compile(
    r"(?m)^={20,}\nARTIFACT\s+(\d+)\s+·\s+[^\n]+\n"
    r"source file:\s+[^\n]+\n={20,}\n"
)


def _split_source_text(source, text):
    if source.suffix.lower() != ".md" or splitter.FF in text:
        return splitter.split(text)
    declared = list(_ARTIFACT_LINE.finditer(text))
    if not declared:
        return splitter.split(text)
    records = list(_ARTIFACT_RECORD.finditer(text))
    numbers = [int(match.group(1)) for match in records]
    if len(records) != len(declared) or numbers != list(range(1, len(records) + 1)):
        print(
            "refusing to open: malformed ARTIFACT provenance boundaries; "
            "records must be framed, carry a source file, and be numbered consecutively from 1",
            file=sys.stderr,
        )
        return None
    starts = [record.start() for record in records]
    parts = []
    for index, start in enumerate(starts):
        if index == 0:
            start = 0
        end = starts[index + 1] if index + 1 < len(starts) else len(text)
        parts.append(text[start:end] + splitter.FF)
    return parts


def open_document(source, work):
    source = Path(source).expanduser().resolve(strict=True)
    work_path = Path(work)
    if _state_path(work).exists() or (work_path / "pieces").exists():
        print(f"refusing to open: {work} already contains a run identity or piece artifacts. "
              f"Use a new nested work directory; open never replaces a run.", file=sys.stderr)
        return 3
    text = _read_source_text(source)
    if text is None:
        return 3
    parts = _split_source_text(source, text)
    if parts is None:
        return 3
    pieces = [{"id": f"p-{i:04d}", "chars": len(t), "sha256": hashlib.sha256(t.encode()).hexdigest()}
              for i, t in enumerate(parts, 1)]
    work_path.mkdir(parents=True, exist_ok=True)
    (work_path / "pieces").mkdir(exist_ok=False)
    for piece, t in zip(pieces, parts):
        (work_path / "pieces" / f"{piece['id']}.txt").write_text(t)
    _write(work, {"source": str(source), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                  "strategy": splitter.STRATEGY, "opened_at": time.time(),
                  "pieces": pieces, "answers": {}})
    # The cut is by page, and nothing here ever checked whether a sentence runs across a page
    # boundary. On this library it does not, at any of the 103 boundaries — but that is a property
    # of the document, not of the cut, and a document where it fails would hand every later pass a
    # statement split in half with neither half readable. Now it is counted and said out loud.
    crossings = [(pieces[i]["id"], pieces[i + 1]["id"]) for i in range(len(parts) - 1)
                 if reflow.sentence_crosses(parts[i], parts[i + 1])]
    print(f"{len(pieces)} pieces, none answered. They are in {Path(work) / 'pieces'}.")
    if crossings:
        print(f"\n{len(crossings)} place(s) where a sentence runs from one piece into the next. "
              f"Each one is a statement neither piece states whole:", file=sys.stderr)
        for a, b in crossings[:10]:
            print(f"   {a} -> {b}", file=sys.stderr)
    else:
        print(f"no sentence runs across a piece boundary ({len(parts) - 1} checked).")
    return 0


def status(work):
    state = _read(work)
    view = _rebuild(state).status()
    unanswered = sorted(k for k, v in view.items() if not v["answered"])
    print(f"{len(state['pieces'])} pieces · {len(state['pieces']) - len(unanswered)} answered · "
          f"{len(unanswered)} not")
    for piece_id in unanswered[:20]:
        print(f"   unanswered: {piece_id}")
    if len(unanswered) > 20:
        print(f"   ... and {len(unanswered) - 20} more")
    if unanswered:
        print("answer bodies remain private operator state; public output releases them only "
              "after coverage is complete")
    return 0


def answer(work, piece, by, what, quote):
    state = _read(work)
    if piece not in {p["id"] for p in state["pieces"]}:
        print(f"{piece} is not a piece of this document. Run `cover.py status --work {work}` to "
              f"see them.", file=sys.stderr)
        return 3
    piece_text = (Path(work) / "pieces" / f"{piece}.txt").read_text()
    grounded = quotecheck.grounding(quote, piece_text)
    if grounded is None:
        print(f"refused: this is not on {piece}. The quote given was:\n\n    {quote.strip()}\n\n"
              f"{piece} is still unanswered. Quote words that are on the page — they are in "
              f"{Path(work) / 'pieces' / (piece + '.txt')} — or leave it unanswered.", file=sys.stderr)
        return 3
    state["answers"][piece] = {"what": what, "quote": grounded, "by": by, "at": time.time()}
    _write(work, state)
    print(f"{piece} answered by {by}, grounded in its own words.")
    return 0


COVERAGE_ASK = """Read the complete source piece below before answering.

SOURCE PIECE START
{piece_text}
SOURCE PIECE END

Copy one complete, substantive passage that demonstrates the piece was read. The passage must
appear exactly in the source piece. Do not summarize or add words."""


def cover_unanswered(work, reader_command):
    """Ground every source piece in the public coverage register before extraction begins."""
    interview_mod = _load("interview")
    state = _read(work)
    unanswered = [piece["id"] for piece in state["pieces"]
                  if piece["id"] not in state["answers"]]
    for piece_id in unanswered:
        piece_text = (Path(work) / "pieces" / f"{piece_id}.txt").read_text()
        grounded, _transcript = interview_mod.ask_quote(
            reader_command,
            COVERAGE_ASK.format(piece_text=piece_text),
            piece_text,
            quotecheck,
            stage="coverage",
            piece=piece_id,
        )
        if grounded is None:
            print(f"cannot complete coverage: reader did not ground {piece_id}; "
                  "the piece remains unanswered", file=sys.stderr)
            return 3
        code = answer(work, piece_id, "self-sustained reader", grounded, grounded)
        if code != 0:
            return code
    print(f"coverage complete: {len(state['pieces'])} of {len(state['pieces'])} pieces answered")
    return 0


def _verdicts(state, target):
    """Verdicts for one target, kept beside any others this directory already holds.

    The first version refused a work directory whose target had changed and told the operator to
    start a fresh one. That is a real cost: judging 104 pieces takes about an hour, and the target's
    wording is exactly the thing anyone would want to try two ways. Comparing two wordings should
    cost the second wording, not both. Verdicts are keyed by the target they were made against, so
    going back to an earlier wording costs nothing and neither set is thrown away.
    """
    rel = state.setdefault("relevance", {})
    if "target" in rel:                       # written by the version that held one target
        rel = state["relevance"] = {"targets": {rel["target"]: {"pieces": rel.get("pieces", {})}},
                                    "last": rel["target"]}
    rel.setdefault("targets", {})
    rel["last"] = target
    return rel["targets"].setdefault(target, {}).setdefault("pieces", {})


def _last_target(state):
    rel = state.get("relevance", {})
    return rel.get("target") or rel.get("last")


def relevance(work, target, reader_command):
    """Ask, of every piece the register holds, whether it bears on the document being built.

    Runs over pieces, not over the document: the register already guarantees no piece is skipped,
    so this cannot quietly judge a subset. A piece the readers split on is written down as the
    owner's to settle and is neither in nor out — the machinery does not get a casting vote.
    """
    relevance_mod = _load("relevance")
    state = _read(work)
    rows = _verdicts(state, target)
    for piece in state["pieces"]:
        if piece["id"] in rows:
            continue
        text = (Path(work) / "pieces" / f"{piece['id']}.txt").read_text()
        verdict, seats = relevance_mod.judge(text, target, reader_command, quotecheck,
                                             piece=piece["id"])
        rows[piece["id"]] = {"verdict": verdict, "seats": seats, "at": time.time()}
        _write(work, state)
        print(f"{piece['id']}: {verdict}", flush=True)
    tally = {}
    for row in rows.values():
        tally[row["verdict"]] = tally.get(row["verdict"], 0) + 1
    print(json.dumps({"target": target, "pieces": len(state["pieces"]), "verdicts": tally}, indent=1))
    owner = [k for k, v in rows.items() if v["verdict"] == relevance_mod.FOR_THE_OWNER]
    if owner:
        print(f"\n{len(owner)} piece(s) the two readers answered differently. They are neither in "
              f"nor out, and this machinery will not settle them:")
        for piece_id in owner:
            print(f"   {piece_id}")
    return 0


def obligations(work, reader_command):
    """Take every obligation out of each piece the relevance pass admitted.

    Runs over the admitted set, never over the document, and refuses to start while relevance is
    itself incomplete — an obligation pass over a half-judged source would look like a finished
    list and be one page short of the truth, which is the failure the register exists to prevent.
    """
    obligations_mod = _load("obligations")
    relevance_mod = _load("relevance")
    state = _read(work)
    target = _last_target(state)
    if target is None:
        print(f"nothing has been judged for relevance in {work}. Run `cover.py relevance --work "
              f"{work} --target ... --reader-command ...` first.", file=sys.stderr)
        return 3
    judged = _verdicts(state, target)
    unjudged = [p["id"] for p in state["pieces"] if p["id"] not in judged]
    if unjudged:
        print(f"cannot take obligations: {len(unjudged)} of {len(state['pieces'])} piece(s) have "
              f"no relevance verdict for {target!r}. Finish `cover.py relevance` first; it "
              f"resumes where it stopped.", file=sys.stderr)
        return 3
    admitted = [p for p, row in judged.items() if row["verdict"] == "bears"]
    # The pieces the two readers split on are read too. Not to settle them — that stays the
    # owner's, and nothing here changes their verdict — but so that what reaches him is the
    # obligations the piece would contribute rather than a page number. A split piece that yields
    # nothing takes a second to wave away; one that yields three real lines takes a second to
    # admit. Either way he decides, with the material in front of him instead of without it.
    unsettled = [p for p, row in judged.items()
                 if row["verdict"] in (relevance_mod.FOR_THE_OWNER, relevance_mod.NOT_GROUNDED,
                                       relevance_mod.NO_ANSWER)]
    store = state.setdefault("obligations", {}).setdefault(target, {})
    for piece_id in sorted(admitted) + sorted(unsettled):
        if piece_id in store:
            continue
        text = (Path(work) / "pieces" / f"{piece_id}.txt").read_text()
        seats = state["relevance"]["targets"][target]["pieces"].get(piece_id, {}).get("seats", [])
        admitted_on = [str(s.get("quote")) for s in seats
                       if s.get("quote") and str(s.get("quote")) != "None"]
        found, asked, by_cut = obligations_mod.extract(text, target, reader_command, quotecheck,
                                                       admitted_on=admitted_on, piece=piece_id)
        store[piece_id] = {"obligations": found, "units_offered": asked, "at": time.time(),
                           "settled": piece_id in admitted, "by_cut": by_cut,
                           "relevance_verdict": judged[piece_id]["verdict"]}
        _write(work, state)
        print(f"{piece_id}: {len(found)} of {asked} lines"
              f"{'' if piece_id in admitted else '   (unsettled — for the owner)'}", flush=True)
    expected = sorted(set(admitted) | set(unsettled))
    complete = all(piece_id in store for piece_id in expected)
    if complete:
        state.setdefault("obligation_completion", {})[target] = {
            "complete": True, "piece_ids": expected,
            "admitted_piece_ids": sorted(admitted),
            "unresolved_piece_ids": sorted(unsettled), "at": time.time(),
        }
        # Completion is a fact independent of cardinality. In the all-negative case this is the
        # first write: an intentionally empty store must not be indistinguishable from never run.
        _write(work, state)
    if not admitted:
        print(f"no piece bears on {target!r}, so there is nothing to take obligations from. "
              f"That is an answer, not a failure — but check it against "
              f"`cover.py bearing --work {work}` before treating it as one.")
        return 0
    # Counted over the admitted pieces only. The store also holds what the unsettled pieces would
    # contribute, and summing the whole store reported one of those as though it had been admitted
    # — a number quietly larger than the thing it named.
    # A piece is admitted because two readers quoted a line from it. If that line is not among the
    # obligations the piece then yields, the two steps have contradicted each other about the same
    # page, and the page reads as empty when it is not. Measured on the fourteen: five of thirteen,
    # and every piece that yielded nothing was one of the five — including page 83's "Each campaign
    # must have measures on at least three levels", which is plainly an obligation. This is not
    # settled here. It is named and sent to the owner with both halves in front of him.
    reflow_mod = _load("reflow")
    judged_rows = state["relevance"]["targets"][target]["pieces"]
    contradicted = []
    for piece_id in admitted:
        quotes = [str(seat.get("quote") or "") for seat in judged_rows.get(piece_id, {}).get("seats", [])]
        quotes = [q for q in quotes if q and q != "None"]
        obs = store.get(piece_id, {}).get("obligations", [])
        if quotes and not any(reflow_mod.flow(q) in reflow_mod.flow(o)
                              or reflow_mod.flow(o) in reflow_mod.flow(q)
                              for q in quotes for o in obs):
            contradicted.append({"piece": piece_id, "admitted_on": reflow_mod.flow(quotes[0]),
                                 "obligations_found": len(obs)})
    total = sum(len(store[p]["obligations"]) for p in admitted if p in store)
    waiting = sum(len(store[p]["obligations"]) for p in unsettled if p in store)
    print(json.dumps({"target": target, "admitted_pieces": len(admitted), "obligations": total,
                      "unsettled_pieces": len(unsettled),
                      "obligations_they_would_add": waiting,
                      "admitted_on_a_line_that_did_not_survive": contradicted}, indent=1))
    return 0


def collapse(work, reader_command):
    """Collapse the obligations store's repeats into groups, the doubtful pairs to the owner.

    Runs the promoted dedupe rule (dedupe.py — atom-5-dedupe round 2's champion) over every entry
    the obligations pass produced, admitted and unsettled alike. Pairs code proves or the reader
    affirms four times merge; a split vote, or a four-NO on a pair textually half-identical, goes
    to the owner as genuine doubt. Refuses while the obligations pass is incomplete, exactly as
    the passes before it refuse.
    """
    dedupe_mod = _load("dedupe")
    relevance_mod = _load("relevance")
    state = _read(work)
    target = _last_target(state)
    completion = state.get("obligation_completion", {}).get(target, {}) if target else {}
    if (target is None or target not in state.get("obligations", {})
            or completion.get("complete") is not True):
        print(f"no obligations store in {work}. Run `cover.py obligations` first.", file=sys.stderr)
        return 3
    store = state["obligations"][target]
    judged = _verdicts(state, target)
    missing = [p for p, row in judged.items()
               if row["verdict"] in ("bears", relevance_mod.FOR_THE_OWNER,
                                     relevance_mod.NOT_GROUNDED, relevance_mod.NO_ANSWER)
               and p not in store]
    if missing:
        print(f"cannot collapse: {len(missing)} piece(s) have no obligations record. Finish "
              f"`cover.py obligations` first; it resumes where it stopped.", file=sys.stderr)
        return 3
    rows = [(pid, text) for pid in sorted(store) for text in store[pid]["obligations"]]
    entries = [t for _, t in rows]
    prior = state.get("collapse", {}).get(target)
    if prior and [e["text"] for e in prior["entries"]] == entries:
        # The judgement is already on record for exactly these entries. Re-asking the same
        # questions of the same material buys nothing but drift — the pairs are reused and only
        # what is derived from them is recomputed.
        merged = [tuple(p) for p in prior["merged_pairs"]]
        owner = [tuple(p) for p in prior["owner_pairs"]]
        detail = prior["detail"]
        print(f"reusing the recorded judgement of these exact {len(entries)} entries "
              f"(0 reader calls)", flush=True)
    else:
        merged, owner, detail = dedupe_mod.judge(entries, reader_command)
    # The pairs are the proven deliverable. The first production run also formed groups by
    # transitive closure, and that closure — never experimented — chained 17 of 28 entries into
    # one: A shared a rule with B and B another with C, so A and C fused while sharing nothing.
    # "States a shared rule" is not an equivalence, because these entries are composite excerpts
    # carrying several rules each. So the pairs are stored and shown as pairs, and how pairs
    # become one-entry-per-requirement is decided by its own proven step, not silently here.
    # Reconciling the unsettled pieces is derived, not judged: a piece the relevance readers
    # split on is resolved by evidence when every obligation it contributed states a rule an
    # admitted entry also states — the doubt was about the piece, and its content is already in
    # the list either way. A piece with any unpaired or owner-paired line keeps its doubt.
    settled_idx = {n for n, (pid, _) in enumerate(rows, 1) if store[pid]["settled"]}
    paired_to_admitted = set()
    for a, b in merged:
        if b in settled_idx: paired_to_admitted.add(a)
        if a in settled_idx: paired_to_admitted.add(b)
    reconciled, still_owner = [], []
    for pid in sorted(store):
        if store[pid]["settled"]:
            continue
        mine = [n for n, (p2, _) in enumerate(rows, 1) if p2 == pid]
        if mine and all(n in paired_to_admitted for n in mine):
            reconciled.append({"piece": pid, "covered_by_pairs": True})
        else:
            still_owner.append(pid)
    pair_records = []
    for a, b in sorted(owner):
        left, right = rows[a - 1], rows[b - 1]
        evidence = next((d for d in detail if d.get("pair") == [a, b]), None)
        identity = hashlib.sha256(json.dumps({
            "a": {"piece": left[0], "text": left[1]},
            "b": {"piece": right[0], "text": right[1]},
        }, sort_keys=True).encode()).hexdigest()[:12]
        pair_records.append({
            "id": f"source-pair-{identity}",
            "a": {"piece": left[0], "text": left[1]},
            "b": {"piece": right[0], "text": right[1]},
            "evidence": evidence,
        })
    state.setdefault("collapse", {})[target] = {
        "entries": [{"piece": pid, "text": t} for pid, t in rows],
        "merged_pairs": sorted(map(list, merged)),
        "owner_pairs": sorted(map(list, owner)),
        "owner_pair_records": pair_records,
        "reconciled_unsettled": reconciled, "still_for_owner": still_owner,
        "detail": detail, "at": time.time()}
    _write(work, state)
    print(f"{len(entries)} entries; {len(merged)} same-rule pair(s); "
          f"{len(owner)} pair(s) for the owner; "
          f"unsettled pieces resolved by evidence: {[r['piece'] for r in reconciled]}; "
          f"still with the owner: {still_owner}", flush=True)
    for a, b in merged:
        print(f"  SAME-RULE {a}~{b}: {rows[a - 1][1][:65]!r} ~ {rows[b - 1][1][:65]!r}")
    for a, b in owner:
        print(f"  OWNER {a}~{b}: {rows[a - 1][1][:65]!r} vs {rows[b - 1][1][:65]!r}")
    return 0


def requirements(work, reader_command):
    """The atom's whole pipeline to its final list: rules cut once each, entries judged checkable,
    the unsettled reconciled, the doubtful with the owner. Refuses while collapse has not run."""
    rules_mod = _load("rules")
    state = _read(work)
    target = _last_target(state)
    col = state.get("collapse", {}).get(target)
    if not col:
        print(f"no collapse record in {work}. Run `cover.py collapse` first.", file=sys.stderr)
        return 3
    rows = col["entries"]; entries = [e["text"] for e in rows]
    merged = [tuple(p) for p in col["merged_pairs"]]
    prior = state.get("requirements", {}).get(target, {})
    if prior.get("rules_stage") and [e["text"] for e in rows] == prior.get("entries_at_rules"):
        rules = prior["rules_stage"]["rules"]
        unresolved = prior["rules_stage"]["unresolved"]
        detail = prior["rules_stage"]["detail"]
        for r in rules:
            src = next((entries[n - 1] for n in r["entries"] if r["text"] in entries[n - 1]), None)
            if src:
                r["text"] = rules_mod.to_sentences(r["text"], src)
        print(f"reusing the recorded rule extraction ({len(rules)} rules, 0 reader calls), "
              f"expanded to whole sentences", flush=True)
    else:
        rules, unresolved, detail = rules_mod.extract(entries, merged, reader_command)
        # Written before the next stage starts. The first run of this command crashed one stage
        # later on a missing import and lost twenty reader calls, because nothing was saved until
        # the very end. Each stage's reader work is durable the moment it completes.
        state.setdefault("requirements", {})[target] = {
            "rules_stage": {"rules": rules, "unresolved": unresolved, "detail": detail},
            "entries_at_rules": [e["text"] for e in rows], "at": time.time()}
        _write(work, state)
    paired = {n for p in merged for n in p}
    represented = rules_mod.fully_represented_entries(entries, rules)
    carriers = [n for n in range(1, len(entries) + 1)
                if n not in paired or n not in represented]
    # The final list: every extracted rule once, plus every entry no pair touched, each carrying
    # its pages. Checkability: three independent asks over the numbered list, the intersection
    # survives — the shape that won the checkable comparison; what every ask leaves out is
    # refused, with that as its recorded reason, never silently dropped.
    items = ([{"text": r["text"], "pages": sorted({rows[n - 1]["piece"] for n in r["entries"]}),
               "kind": "rule", "source_rule_ids": [rule_number]} for rule_number, r in enumerate(rules, 1)]
             + [{"text": entries[n - 1], "pages": [rows[n - 1]["piece"]], "kind": "entry"}
                for n in carriers])
    # The repeat survives one level down when quotes from a reworded pair are themselves a
    # reworded pair. The promoted dedupe runs again — but ONLY over the extracted rules, never
    # over composite items. Merging composite carriers loses rules, and this build has now proven
    # that three times: entry containment swallowed page 9, transitive closure fused 17 entries,
    # and a keep-longer merge over mixed items deleted "No research starts until the brief and
    # the measurement brief are approved in writing" — the engine's central gate — by absorbing
    # it into the register table. Two atomic rules stating the same thing may merge, keeping the
    # fuller wording and both page sets. A composite is never merge material.
    dedupe_mod = _load("dedupe")
    rule_items = [it for it in items if it["kind"] == "rule"]
    other_items = [it for it in items if it["kind"] != "rule"]
    rule_texts = [it["text"] for it in rule_items]
    prior_j = state.get("requirements", {}).get(target, {}).get("rule_judgement")
    if prior_j and prior_j.get("texts") == rule_texts:
        item_merged = [tuple(x) for x in prior_j["merged"]]
        item_owner = [tuple(x) for x in prior_j["owner"]]
        print(f"reusing the recorded rule judgement (0 reader calls)", flush=True)
    else:
        item_merged, item_owner, _ = dedupe_mod.judge(rule_texts, reader_command)
        state.setdefault("requirements", {}).setdefault(target, {})["rule_judgement"] = {
            "texts": rule_texts, "merged": sorted(map(list, item_merged)),
            "owner": sorted(map(list, item_owner))}
        _write(work, state)
    # A same-rule verdict between two texts of different scale is containment, not sameness: the
    # register-table quote contains the final-brief gate's words, the readers honestly said
    # same-rule, and keep-longer buried the gate inside the table — the fourth appearance of the
    # absorption class in one build. Two texts merge only when neither exceeds twice the other
    # (the bound the merge experiment measured: every real same-statement pair sat at or under
    # 2x, every swallow at 6.6x or more). A same-rule verdict across scales is genuine overlap
    # for the owner — one text states the rule alone, the other states it among several.
    lineage_mod = _load("rule_lineage")
    reduction = lineage_mod.reduce(rule_items, item_merged)
    item_owner = list(item_owner) + reduction["owner_pairs"]
    item_owner_texts = [[rule_items[a - 1]["text"][:80], rule_items[b - 1]["text"][:80]]
                        for a, b in item_owner]
    rule_items = reduction["items"]
    conservation_mod = _load("rule_conservation")
    conservation = conservation_mod.check(len(rules), rule_items)
    req_state = state.setdefault("requirements", {}).setdefault(target, {})
    req_state["rule_lineage"] = {
        "source_count": len(rules),
        "components": reduction["components"],
        "ambiguous": reduction["ambiguous"],
    }
    req_state["rule_conservation"] = conservation
    _write(work, state)
    if not conservation["valid"]:
        print(
            "refusing incomplete rule merge before checkability: "
            f"missing={conservation['missing']} duplicates={conservation['duplicates']} "
            f"unknown={conservation['unknown']}",
            file=sys.stderr,
        )
        return 3
    items = rule_items + other_items
    interview_mod = _load("interview")
    numbered = "\n".join(f"{i}. {it['text']}" for i, it in enumerate(items, 1))
    # The target names itself. The first version hardcoded "for the Step 3 Measurement Brief"
    # here — the subject the machinery was built against — and the Step 5 production run's 23
    # items were voted checkable against the wrong document's name (found 2026-08-25).
    ask = ("Below are numbered requirements taken from one methodology library.\n"
           f"The document they are for is: {target}\n\n"
           "For which of them could you write a check that a finished copy of that document "
           "would either pass or fail?\n\nReply with the numbers only, one per line.\n\n"
           "This is a data-extraction request, not a task report. Do not begin with any status "
           "line, anchor or preamble. The first character of your reply must be the first "
           "character of the answer.\n\n" + numbered)
    checkability_mod = _load("checkability")
    item_texts = [item["text"] for item in items]
    saved_record = state.get("requirements", {}).get(target, {}).get("checkability_record")
    if saved_record:
        try:
            decision_record = checkability_mod.validate(saved_record, item_texts, target, ask)
        except (KeyError, TypeError, ValueError) as exc:
            req_state = state.setdefault("requirements", {}).setdefault(target, {})
            # Unanimous yes keeps, unanimous no refuses, a split is genuine doubt and goes to the owner
            # — the same gray band the promoted dedupe uses, because a judgement the asks disagree on is
            # not a judgement either way.
            req_state.setdefault("checkability_history", []).append({
                "record": saved_record,
                "invalidated_because": str(exc),
                "at": time.time(),
            })
            req_state.pop("checkability_record", None)
            _write(work, state)
            saved_record = None
            print(f"preserved stale checkability evidence before reassessment: {exc}", flush=True)
        else:
            print("reusing the replay-validated checkability record (0 reader calls)", flush=True)
    if not saved_record:
        raw_replies = [
            interview_mod.ask_free(reader_command, ask, stage="checkable", seat=seat)
            for seat in range(1, 4)
        ]
        decision_record = checkability_mod.build(raw_replies, item_texts, target, ask)
        state.setdefault("requirements", {}).setdefault(target, {})["checkability_record"] = decision_record
        _write(work, state)
    for i, it in enumerate(items, 1):
        decision = decision_record["aggregate"][i - 1]
        votes = decision["votes"]
        it["checkable"] = decision["disposition"] == "keep"
        if decision["disposition"] == "drop":
            it["refused_because"] = "no ask kept it (0 of 3)"
        elif decision["disposition"] == "owner":
            it["checkable_doubt"] = f"{votes} of 3 asks kept it — for the owner"
    source_owner_pairs = col.get("owner_pair_records")
    if source_owner_pairs is None:
        source_owner_pairs = []
        for a, b in col.get("owner_pairs", []):
            left, right = col["entries"][a - 1], col["entries"][b - 1]
            evidence = next((d for d in col.get("detail", []) if d.get("pair") == [a, b]), None)
            identity = hashlib.sha256(json.dumps({"a": left, "b": right},
                                                 sort_keys=True).encode()).hexdigest()[:12]
            source_owner_pairs.append({
                "id": f"source-pair-{identity}", "a": left, "b": right,
                "evidence": evidence,
            })
    shared_rule_owner_records = []
    for a, b in unresolved:
        left, right = rows[a - 1], rows[b - 1]
        extraction = next((d for d in detail if d.get("pair") == [a, b]), None)
        identity = hashlib.sha256(json.dumps({"a": left, "b": right},
                                             sort_keys=True).encode()).hexdigest()[:12]
        shared_rule_owner_records.append({
            "id": f"shared-rule-{identity}", "a": left, "b": right,
            "extraction": extraction,
        })
    state["requirements"][target].update({
        "items": items, "unresolved_pairs": unresolved, "rule_detail": detail,
        "source_conservation": {
            "represented_by_rule": sorted(represented),
            "retained_as_carrier": carriers,
        },
        "owner_pairs": col["owner_pairs"],
        "source_owner_pairs": source_owner_pairs,
        "shared_rule_owner_records": shared_rule_owner_records,
        "still_for_owner": col["still_for_owner"],
        "item_owner_pairs": item_owner_texts,
        "reconciled": col["reconciled_unsettled"], "at": time.time()})
    _write(work, state)
    kept_n = sum(1 for it in items if it["checkable"])
    print(f"{len(items)} items ({len(rules)} rules cut once, {len(carriers)} source carriers); "
          f"{kept_n} checkable, {len(items) - kept_n} refused with reason; "
          f"{len(unresolved)} pair(s) yielded no verbatim rule; "
          f"owner items: pairs {col['owner_pairs']} pieces {col['still_for_owner']}", flush=True)
    for i, it in enumerate(items, 1):
        mark = "KEEP " if it["checkable"] else ("DOUBT" if it.get("checkable_doubt") else "DROP ")
        print(f"  {mark}{i:2d} [{','.join(it['pages'])}] {it['text'][:95]}")
    for a, b in item_owner_texts:
        print(f"  OWNER-PAIR {a!r} vs {b!r}")
    return 0


def distill(work, reader_command):
    """The pen: each item written as one clean statement, code proving no word was invented.

    An item with one verbatim wording keeps it — scissors output is already a statement. An item
    that absorbed rewordings gets all of them as anchors and the reader writes the rule once,
    through the term-preservation gate: every content word and number must trace to the anchors,
    and a refusal names each invented word (G33). Owner pairs, doubt items and unsettled pieces
    are carried unchanged — the pen never settles what is the owner's. Refuses until the
    requirements pass has run.
    """
    distill_mod = _load("distill")
    state = _read(work)
    target = _last_target(state)
    req = state.get("requirements", {}).get(target)
    if not req or "items" not in req:
        print(f"no requirements record in {work}. Run `cover.py requirements` first.",
              file=sys.stderr)
        return 3
    out = []
    for it in req["items"]:
        anchors = [it["text"]] + it.get("also_stated_as", [])
        # Every item goes through the pen, uniformly. A rule deciding which items "read as a
        # statement" was tried twice and misclassified tables both times; the pen with the term
        # gate needs no such rule — an already-clean sentence comes back as itself, a table block
        # comes back as prose, and the gate blocks invention in both cases. What stays verbatim
        # is only what the pen fails to write within its attempts, refused with the gate's reason.
        if False:
            statement, how, transcript = it["text"], "verbatim", []
        else:
            statement, transcript = distill_mod.write_one(anchors, reader_command,
                                                          stage="distill",
                                                          piece=",".join(it["pages"]))
            how = "pen"
            if statement is None:
                out.append({"pages": it["pages"], "statement": None, "how": "refused",
                            "anchors": anchors, "transcript": transcript,
                            "checkable": it.get("checkable"),
                            "doubt": it.get("checkable_doubt")})
                continue
        out.append({"pages": it["pages"], "statement": statement, "how": how,
                    "anchors": anchors, "transcript": transcript,
                    "checkable": it.get("checkable"), "doubt": it.get("checkable_doubt")})
        state.setdefault("distilled", {})[target] = {"items": out, "at": time.time()}
        _write(work, state)
    state.setdefault("distilled", {})[target] = {
        "items": out,
        "owner_pairs": req.get("item_owner_pairs", []),
        "source_owner_pairs": req.get("source_owner_pairs", []),
        "shared_rule_owner_records": req.get("shared_rule_owner_records", []),
        "still_for_owner": req.get("still_for_owner", []),
        "at": time.time()}
    _write(work, state)
    written = sum(1 for o in out if o["how"] == "pen")
    refused = sum(1 for o in out if o["how"] == "refused")
    print(f"{len(out)} statements ({written} written by the pen through the gate, "
          f"{len(out) - written - refused} kept verbatim, {refused} refused with the gate's "
          f"reason); owner material carried unchanged", flush=True)
    for o in out:
        tag = {"pen": "PEN ", "verbatim": "VERB", "refused": "REFU"}[o["how"]]
        extra = " [DOUBT: " + o["doubt"] + "]" if o.get("doubt") else ("" if o.get("checkable") else " [refused by checkability]")
        print(f"  {tag} [{','.join(o['pages'])}] {(o['statement'] or '(refused)')[:100]}{extra}")
    return 0


def _owner_queue(state, target):
    """Every ruling only the owner can make, one stable id each, with its material and choices."""
    d = state.get("distilled", {}).get(target)
    if not d:
        return None
    rulings = state.get("owner_rulings", {}).get(target, {})
    # The owner judges with the material in front of him, exactly as the unsettled pieces were
    # handled in atom 4: the first interview attempt showed a statement bare, and he rightly
    # refused to rule on it — "there is zero context. I do not know what the optimization gate
    # weekly checkpoints are." Every item now carries where its page opens and the verbatim
    # anchors the statement was written from.
    def _page_context(pieces):
        out = {}
        for pid in pieces:
            path = Path(state.get("_work", "")) / "pieces" / f"{pid}.txt"
            try:
                text = path.read_text()
            except OSError:
                continue
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            out[pid] = " ".join(lines[:2])[:200]
        return out
    queue = []
    for i, o in enumerate(d["items"], 1):
        if o["how"] in ("refused", "split"):
            continue
        if o.get("doubt") or not o.get("checkable"):
            why = o.get("doubt") or "refused by checkability (0 of 3 asks kept it)"
            queue.append({"id": f"check-{i}", "kind": "checkability",
                          "question": "Does this belong in the requirements list?",
                          "statement": o["statement"], "pages": o["pages"], "why": why,
                          "page_opens": _page_context(o["pages"]),
                          "anchors": o.get("anchors", []),
                          "choices": ["keep", "drop", "split"]})
    # Two defects fixed here after the live interview surfaced them: the pair id came from
    # Python's salted hash, so it changed every process and an answer could never match its
    # question; and the pair texts were stored truncated at 80 characters — the same zero-context
    # class the owner refused to rule on. The id is now a content digest, and each side is
    # rejoined to its full rule text from the register.
    full = {r["text"][:80]: r["text"] for r in state.get("requirements", {})
            .get(target, {}).get("rules_stage", {}).get("rules", [])}
    for a, b in d.get("owner_pairs", []):
        fa, fb = full.get(a, a), full.get(b, b)
        digest = hashlib.sha256((fa + "||" + fb).encode()).hexdigest()[:8]
        queue.append({"id": f"pair-{digest}", "kind": "overlap",
                      "question": "Do these state the same rule?",
                      "a": fa, "b": fb, "statement": f"A: {fa}\nB: {fb}", "pages": [],
                      "why": "the readers split, or the texts share a rule across a scale gap",
                      "choices": ["merge", "keep-separate"]})
    for pair in d.get("source_owner_pairs", []):
        queue.append({
            "id": pair["id"], "kind": "source-overlap",
            "question": "Do these source-supported statements state the same requirement?",
            "a": pair["a"]["text"], "b": pair["b"]["text"],
            "a_piece": pair["a"]["piece"], "b_piece": pair["b"]["piece"],
            "statement": f"A: {pair['a']['text']}\nB: {pair['b']['text']}",
            "pages": sorted({pair["a"]["piece"], pair["b"]["piece"]}),
            "why": "the first deduplication readers could not reach one verdict",
            "evidence": pair.get("evidence"),
            "choices": ["merge", "keep-separate"],
        })
    for pair in d.get("shared_rule_owner_records", []):
        queue.append({
            "id": pair["id"], "kind": "shared-rule",
            "question": "No validated shared rule could be extracted; which source duties survive?",
            "a": pair["a"]["text"], "b": pair["b"]["text"],
            "a_piece": pair["a"]["piece"], "b_piece": pair["b"]["piece"],
            "statement": f"A: {pair['a']['text']}\nB: {pair['b']['text']}",
            "pages": sorted({pair["a"]["piece"], pair["b"]["piece"]}),
            "why": "every shared-rule extraction attempt failed its verbatim gate",
            "extraction": pair.get("extraction"),
            "choices": ["keep-both", "select-a", "select-b"],
        })
    for pid in d.get("still_for_owner", []):
        relevance_verdict = (state.get("relevance", {}).get("targets", {}).get(target, {})
                             .get("pieces", {}).get(pid, {}).get("verdict"))
        if relevance_verdict == "no-answer":
            question = ("Neither relevance reader produced a valid answer for this page; does its "
                        f"material belong to the requirements of {target}?")
            why = "both reader seats exhausted their permitted replies without a valid answer"
        elif relevance_verdict == "yes-without-words":
            question = ("The relevance readers admitted this page but produced no grounding words; "
                        f"does its material belong to the requirements of {target}?")
            why = "the relevance answer could not be grounded in the page's own words"
        else:
            question = ("The relevance readers split on this page; does its material "
                        f"belong to the requirements of {target}?")
            why = "one reader said it bears, one said it does not"
        queue.append({"id": f"piece-{pid}", "kind": "unsettled-piece",
                      # The target names itself here too: this question carried "the Measurement
                      # Brief" hardcoded until 2026-08-25 — the B5 class's second instance, missed
                      # by the first sweep and caught by run-2's page questions.
                      "question": question,
                      "statement": f"page {pid} — its contributed lines are in the list above, "
                                   f"marked with this page", "pages": [pid],
                      "why": why, "relevance_verdict": relevance_verdict,
                      "choices": ["admit", "dismiss"]})
    final_state = (state.get("document_preparation", {}).get(target, {})
                   .get("final_semantic", {}))
    active_signature = final_state.get("active_signature")
    final_record = final_state.get(active_signature, {}) if active_signature else {}
    if final_record and _normalize_final_semantic_record(final_record, rulings):
        work = state.get("_work")
        if work:
            _write(work, state)
    for pair in final_record.get("owner_pairs", []):
        queue.append({
            "id": pair["id"], "kind": "final-overlap",
            "question": "Do these final owner-materialized statements state the same requirement?",
            "a": pair["a"], "b": pair["b"],
            "statement": f"A: {pair['a']}\nB: {pair['b']}",
            "pages": pair.get("pages") or [],
            "why": "the final blind readers split, or the texts share a rule across a scale gap",
            "choices": ["merge", "keep-separate"],
        })
    open_queue = [q for q in queue if q["id"] not in rulings]
    # Auto re-queue: a recorded ruling a later ruling invalidated comes back as pending, with
    # its prior answer attached, so the ordinary answer path can accept the owner's correction.
    # On 2026-08-27 a checkability drop consumed one side of a recorded merge; the ruling could
    # neither apply nor be corrected, and assembly dead-ended until a hand edit. Detection uses
    # ruling_validity when the composed tree carries it, else this approach's own inline check.
    stale_reasons = {}
    stale_conflicts = []

    def _stale_recorded_ids():
        if os.environ.get("RULING_VALIDITY_DRY_RUN"):
            # Inside the replay detector's own dry run: behave as the bare assembly seam so the
            # refusal it reads surfaces, instead of recursing back into the detector.
            return set()
        try:
            import ruling_validity
            conflicts = ruling_validity.conflicts(state.get("_work", ""))
            stale_conflicts.extend(conflicts)
            for conflict in conflicts:
                duty = conflict["source_duty"]
                drop_id = conflict["dropped_ruling_id"]
                selecting_id = conflict["selecting_ruling_id"]
                reason = (f"{drop_id} drops source duty {duty!r}, while {selecting_id} "
                          f"selects that same duty. Change this selection to retain only a "
                          f"non-dropped side or drop both; the prior answer remains in its history.")
                stale_reasons.setdefault(selecting_id, []).append(reason)
            return {conflict["selecting_ruling_id"] for conflict in conflicts}
        except Exception:
            stale = set()
            items = d.get("items") or []
            for rid_, r_ in rulings.items():
                item_ = r_.get("item") or {}
                if item_.get("kind") != "source-overlap" or r_.get("choice") != "merge":
                    continue
                sides_ = [item_.get("a"), item_.get("b")]
                matched_ = [i_ for i_, it_ in enumerate(items)
                            if any(s_ in (it_.get("anchors") or []) for s_ in sides_)]
                if len(matched_) != 2:
                    stale.add(rid_)
            return stale
    for rid_ in sorted(_stale_recorded_ids()):
        prior_ = rulings.get(rid_)
        if prior_ is None:
            continue
        reopened = dict(prior_["item"])
        reopened["id"] = rid_
        conflicts_for_ruling = [conflict for conflict in stale_conflicts
                                if conflict["selecting_ruling_id"] == rid_]
        if reopened.get("kind") in ("overlap", "shared-rule") and conflicts_for_ruling:
            conflicting_sides = {conflict["selected_side"] for conflict in conflicts_for_ruling}
            choices = []
            if "a" not in conflicting_sides:
                choices.append("select-a")
            if "b" not in conflicting_sides:
                choices.append("select-b")
            choices.append("drop-both")
            reopened["question"] = ("A recorded checkability ruling drops at least one of these "
                                    "source duties; which non-dropped duty, if any, survives?")
            reopened["choices"] = choices
        reopened["why"] = (" ".join(stale_reasons.get(rid_, [])) or
                           "a later ruling invalidated this recorded answer; it is pending "
                           "again and the prior answer is preserved in its history")
        reopened["reopened"] = True
        reopened["prior_choice"] = prior_.get("choice")
        open_queue.append(reopened)
    return open_queue


ASSESSMENT_POLICY = "dynamic-lines-v1"


def _assessment_prompt(target, item, material, prior, choices):
    if not isinstance(choices, list) or not 1 <= len(choices) <= 3 or any(
            not isinstance(choice, str) or not choice for choice in choices):
        raise ValueError(
            f"assessment choices must contain one, two, or three nonempty strings; got {choices!r}"
        )
    consequence_lines = "\n".join(
        f"CONSEQUENCE-{choice}: what the list looks like after choosing {choice}, one sentence."
        for choice in choices
    )
    offered = " or ".join(choices)
    return (
        f"You are assessing one decision for the owner of a requirements list for {target}.\n\n"
        f"THE ITEM\n{item}\n\n"
        f"ITS VERBATIM SOURCE MATERIAL\n{material}\n\n"
        f"THE OWNER'S RULINGS SO FAR (his own words)\n{prior}\n\n"
        f"Write exactly {len(choices) + 1} lines:\n{consequence_lines}\n"
        f"RECOMMEND: {offered}, one sentence of grounds from the material above, and the single "
        "fact that would flip it.\n\n"
        "This is a data-extraction request, not a task report. Do not begin with any status line, "
        "anchor or preamble. The first characters of your reply must be CONSEQUENCE-."
    )


def _assess(q, state, target, reader_command):
    """The machinery's own assessment of one pending ruling: the consequence of each choice and
    a grounded recommendation, produced by a reader shown the item's verbatim material and the
    owner's recorded rulings. Built after the owner's direction that the interview itself must
    assess and recommend — the first fourteen rulings received their assessments from the
    session's operator by hand, which the next engagement would not have."""
    interview_mod = _load("interview")
    prior = "\n".join(f"- {rid}: {r['choice']} — {r['because']}"
                       for rid, r in sorted(state.get("owner_rulings", {})
                                            .get(target, {}).items())) or "(none yet)"
    material = "\n".join(q.get("anchors", []) or [q.get("a", ""), q.get("b", "")])
    choices = q.get("choices")
    prompt = _assessment_prompt(
        target[:120],
        json.dumps({k: q[k] for k in ("kind", "question", "statement", "pages", "why")
                    if k in q}, ensure_ascii=False),
        material[:3000], prior[:3000], choices,
    )
    raw = interview_mod.ask_free(reader_command, stage="assess", question=prompt)
    lines = [l.strip() for l in raw.split("\n") if l.strip()]
    out = {}
    expected = [f"CONSEQUENCE-{choice}" for choice in choices] + ["RECOMMEND"]
    for l in lines:
        for key in expected:
            if l.upper().startswith(key.upper()):
                out[key] = l.split(":", 1)[-1].strip()
    return out if list(out) == expected and all(out.values()) else {"raw": raw[:500]}


def ask_owner(work, reader_command=None):
    """Present the single next item that needs the owner's ruling — one at a time, never a list.
    With a reader command, the item carries the machinery's own assessment: the consequence of
    each choice and a grounded recommendation, stored so the eventual ruling records what the
    owner was shown."""
    state = _read(work)
    state["_work"] = work
    target = _last_target(state)
    queue = _owner_queue(state, target)
    if queue is None:
        print(f"no distilled record in {work}. Run `cover.py distill` first.", file=sys.stderr)
        return 3
    done = len(state.get("owner_rulings", {}).get(target, {}))
    if not queue:
        print(f"nothing pending — all {done} ruling(s) recorded.")
        return 0
    q = queue[0]
    if reader_command:
        q["assessment"] = _assess(q, state, target, reader_command)
        state.pop("_work", None)
        state.setdefault("owner_assessments", {}).setdefault(target, {})[q["id"]] = q["assessment"]
        _write(work, state)
    print(json.dumps({"pending": len(queue), "recorded": done, "item": q}, indent=1,
                     ensure_ascii=False))
    return 0


SPLIT_DUTY_ASK = (
    "Below is a verbatim passage from a methodology library, and one candidate requirement cut "
    "from it by code.\n\n"
    "The requirements are for: {target}\n\n"
    "--- PASSAGE ---\n{anchor}\n--- END PASSAGE ---\n\n"
    "--- CANDIDATE ---\n{candidate}\n--- END CANDIDATE ---\n\n"
    "Is the candidate ONE self-contained duty or obligation — something separately true or false "
    "of the finished work — rather than a fragment or a bundle of several duties?")

SPLIT_CHECKABLE_ASK = (
    "Below is one requirement taken from a methodology library.\n"
    "The document it is for is: {target}\n\n"
    "Could you write a check that a finished copy of that document would either pass or fail "
    "on this requirement?\n\n"
    "--- REQUIREMENT ---\n{statement}\n--- END REQUIREMENT ---")


SPAN_PROPOSE_ASK = (
    "Below is one verbatim line from a methodology library.\n\n"
    "The requirements are for: {target}\n\n"
    "--- LINE ---\n{anchor}\n--- END LINE ---\n\n"
    "The line may bundle several separate duties or framings. Copy them out, ONE PER LINE — "
    "each line of your reply must be an EXACT contiguous substring of the line above, copied "
    "character for character, nothing added and nothing reworded.\n"
    "If the line states a single duty and nothing can be separated, reply with exactly: ONE DUTY\n\n"
    "This is a data-extraction request, not a task report. Do not begin with any status line, "
    "anchor or preamble. The first character of your reply must be the first character of the "
    "answer.")


def _propose_spans(anchor, target, reader_command, interview_mod, decision_id):
    """The meaning cut: two blind readers each propose where the duties begin and end, in the
    line's own words. Code admits only exact substrings, and only spans both blind proposals
    contain survive. Built 2026-08-25 after the reputation-lens line refused to split — its
    duties are comma-joined, and the owner ruled the semicolon-only cut too narrow: a line
    without semicolons is not thereby unsplittable by meaning.

    Returns (agreed_spans, record) where record names every proposed span and its fate, so a
    refusal can say exactly which spans failed verbatim or agreement (G33)."""
    flat = re.sub(r"\s+", " ", anchor).strip()
    seats, record = [], []
    for seat in (1, 2):
        raw = interview_mod.ask_free(
            reader_command, SPAN_PROPOSE_ASK.format(target=target, anchor=anchor),
            stage="split", piece=decision_id, seat=seat)
        if interview_mod._match(raw, ["ONE DUTY"]) is not None:
            seats.append(None)
            record.append({"seat": seat, "verdict": "one duty"})
            continue
        verified, rejected = [], []
        for line in raw.split("\n"):
            span = re.sub(r"^\s*(?:[-*\u2022]|\d+[.)])\s*", "", line).strip().strip('"\u201c\u201d')
            if len(span) < 10:
                continue
            if re.sub(r"\s+", " ", span) in flat:
                verified.append(re.sub(r"\s+", " ", span))
            else:
                rejected.append(span[:60])
        seats.append(verified)
        record.append({"seat": seat, "verified": verified, "not_verbatim": rejected})
    if seats[0] is None or seats[1] is None:
        return [], record
    agreed = [s for s in seats[0] if s in seats[1]]
    # Containment dedup: when both a whole and its part agree, keep the part-free set of
    # non-overlapping spans by preferring the longer span that is not contained in another.
    agreed = [s for s in agreed if not any(o != s and s in o for o in agreed)]
    return agreed, record


def _split_bundle(state, work, target, decision_id, match, choice, because, reader_command,
                  reopen_on_conservation_refusal=False):
    """Execute one split ruling on the stored state. Cuts are code's; judging is the readers';
    every child rides the same pen gate and checkability vote the whole list rode. State is
    written after the children land, so the interview resumes where it stood."""
    interview_mod = _load("interview")
    distill_mod = _load("distill")
    checkability_mod = _load("checkability")
    idx = int(decision_id.split("-")[1]) - 1
    d = state["distilled"][target]
    parent = d["items"][idx]
    # Code fixes the candidates: each anchor is cut at its own semicolons, the source's own
    # boundary between listed duties. A model never chooses what may be split.
    candidates = []
    for anchor in parent.get("anchors") or []:
        for part in anchor.split(";"):
            part = part.strip(" .;")
            if len(part) < 25:
                continue
            # A table cell's first duty arrives with the row label fused on ("What the AI
            # drafts Generates many candidate insights…"), and a blind reader fairly refuses
            # the label-bearing cut. A lowercase word followed by a Capitalised one mid-part
            # is the layout's own seam; the sub-part from that Capital is offered too — still
            # a verbatim substring, still code's choice, and the readers judge both.
            m = re.search(r"[a-z][),]?\s+(?=[A-Z][a-z])", part)
            if m and len(part) - m.end() >= 25:
                subcandidate = part[m.end():]
                candidates.append({"anchor": anchor, "candidate": part,
                                   "redundant_if_confirmed": subcandidate})
                candidates.append({"anchor": anchor, "candidate": subcandidate,
                                   "redundant_if_confirmed": None})
            else:
                candidates.append({"anchor": anchor, "candidate": part,
                                   "redundant_if_confirmed": None})
    cut_by = "the source line's own semicolon seams"
    if len(candidates) < 2:
        # No punctuation seams: fall back to the meaning cut — reader-proposed, code-verified.
        interview_mod = _load("interview")
        proposals = []
        candidates = []
        for anchor in parent.get("anchors") or []:
            agreed, record = _propose_spans(anchor, target, reader_command, interview_mod,
                                            decision_id)
            proposals.append((anchor, agreed, record))
            for span in agreed:
                candidates.append({"anchor": anchor, "candidate": span,
                                   "redundant_if_confirmed": None})
        cut_by = "the two blind readers' agreed verbatim spans"
        if len(candidates) < 2:
            detail = "; ".join(
                (f"seat {r['seat']}: one duty" if r.get("verdict") == "one duty" else
                 f"seat {r['seat']}: verified {len(r.get('verified', []))} span(s)"
                 + (f", not verbatim: {r['not_verbatim']}" if r.get("not_verbatim") else ""))
                for _, _, rec in proposals for r in rec)
            print(f"refused: the line has no semicolon seams, and the meaning cut found no two "
                  f"spans both blind readers agree on — {detail or 'no anchors to read'}. The "
                  f"item stays as it is; rule keep or drop instead.", file=sys.stderr)
            return 3
    state.pop("_work", None)
    children, unconfirmed = [], []
    for candidate_spec in candidates:
        anchor = candidate_spec["anchor"]
        cand = candidate_spec["candidate"]
        answers = []
        for seat in (1, 2):
            a, _ = interview_mod.ask_choice(
                reader_command, SPLIT_DUTY_ASK.format(target=target, anchor=anchor,
                                                      candidate=cand),
                ["YES", "NO"], stage="split", piece=decision_id, seat=seat)
            answers.append(a)
        if answers != ["YES", "YES"]:
            unconfirmed.append({"candidate": cand, "answers": answers,
                                "redundant_if_confirmed":
                                    candidate_spec["redundant_if_confirmed"]})
            continue
        statement, transcript = distill_mod.write_one([cand], reader_command,
                                                      stage="split", piece=decision_id)
        child = {"pages": list(parent["pages"]), "statement": statement,
                 "how": "pen" if statement else "refused", "anchors": [cand],
                 "transcript": transcript, "split_from": decision_id}
        if statement:
            checkability_prompt = SPLIT_CHECKABLE_ASK.format(
                target=target, statement=statement)
            raw_attempts = []
            for seat in range(1, 4):
                _answer, transcript = interview_mod.ask_choice(
                    reader_command, checkability_prompt, ["YES", "NO"],
                    stage="split", piece=decision_id, seat=seat, preserve_raw=True)
                raw_attempts.append([attempt["raw_reply"] for attempt in transcript])
            decision_record = checkability_mod.build_binary(
                raw_attempts, statement, target, checkability_prompt)
            child["checkability_record"] = decision_record
            decision = decision_record["aggregate"][0]
            votes = decision["votes"]
            child["checkable"] = decision["disposition"] == "keep"
            if decision["disposition"] == "drop":
                child["refused_because"] = "no ask kept it (0 of 3)"
            elif decision["disposition"] == "owner":
                child["checkable_doubt"] = f"{votes} of 3 asks kept it — for the owner"
        children.append(child)
    # When a label-bearing cut and its label-free sub-part both confirm, they are one duty:
    # keep the contained wording, whose words are all duty and no table label.
    children = [c for c in children
                if not any(o is not c and o["anchors"][0] != c["anchors"][0]
                           and o["anchors"][0] in c["anchors"][0] for o in children)]
    confirmed_anchors = {child["anchors"][0] for child in children}
    unresolved = [
        item for item in unconfirmed
        if not item.get("redundant_if_confirmed")
        or item["redundant_if_confirmed"] not in confirmed_anchors
    ]
    if children and unresolved:
        detail = "; ".join(
            f"{item['candidate'][:50]!r}: seats answered {item['answers']}"
            for item in unresolved
        )
        print(f"refused: {len(unresolved)} non-redundant candidate duty or duties remain "
              f"unconfirmed — {detail}. A partial split cannot resolve the parent or discard "
              "those source words.", file=sys.stderr)
        if reopen_on_conservation_refusal:
            _write(work, state)
            print(f"reopened {decision_id}: the legacy partial split was removed and its parent "
                  "is pending for an owner ruling")
            return 0
        return 3
    # A split into nothing is a silent drop wearing a split's name: on 2026-08-25 the
    # reputation-lens ruling cut four agreed spans, the confirmers rejected all four, and the
    # ruling recorded with zero children — the lens vanished from the list with no one choosing
    # that. An empty split refuses instead, and the item stays the owner's to rule.
    if not children:
        detail = "; ".join(f"{u['candidate'][:50]!r}: seats answered {u['answers']}"
                           for u in unconfirmed)
        print(f"refused: {cut_by} produced {len(candidates)} candidate(s), but the blind "
              f"confirmers rejected every one as not a self-contained duty — {detail}. Nothing "
              f"entered, nothing was recorded; the item stays as it is — rule keep or drop.",
              file=sys.stderr)
        return 3
    d["items"].extend(children)
    parent["how"] = "split"
    parent["split_into"] = [len(d["items"]) - len(children) + n for n in range(len(children))]
    split_graph = _build_split_graph(target, decision_id, idx, d["items"], parent["split_into"])
    state.setdefault("owner_rulings", {}).setdefault(target, {})[decision_id] = {
        "item": match, "choice": choice, "because": because or "",
        "children": len(children), "unconfirmed": unconfirmed, "split_graph": split_graph,
        "at": time.time()}
    _write(work, state)
    kept = sum(1 for c in children if c.get("checkable"))
    doubt = sum(1 for c in children if c.get("checkable_doubt"))
    print(f"split {decision_id}: {len(candidates)} candidate dut(ies), {len(children)} confirmed "
          f"and entered ({kept} checkable, {doubt} for the owner), "
          f"{len(unconfirmed)} unconfirmed by the blind readers")
    for c in children:
        print(f"  + [{','.join(c['pages'])}] {(c['statement'] or '(pen refused)')[:95]}")
    return 0


def answer_owner(work, decision_id, choice, because, reader_command=None):
    """Record one ruling. Refuses an id it did not ask for and a choice it did not offer —
    exactly the requirements-machine's owner-decision contract. The owner's words are the record.

    `split` is a ruling the machinery executes, not only records: the bundled statement's own
    verbatim anchors are cut by code into candidate duties, two blind readers confirm each duty,
    every confirmed duty enters the list as its own item with a fresh checkability pass, and the
    bundle is recorded as split into its children. Built 2026-08-25 when the first live interview
    question was a five-duty bundle and the only door out was hand-editing — which the owner
    ruled out: "the machinery should be capable of doing this not you manually intervening."
    """
    state = _read(work)
    state["_work"] = work
    target = _last_target(state)
    queue = _owner_queue(state, target)
    if queue is None:
        print(f"no distilled record in {work}. Run `cover.py distill` first.", file=sys.stderr)
        return 3
    match = next((q for q in queue if q["id"] == decision_id), None)
    if match is None:
        pending = ", ".join(q["id"] for q in queue) or "none"
        print(f"'{decision_id}' is not a pending ruling — pending: {pending}. An id already "
              f"answered is not re-opened here.", file=sys.stderr)
        return 3
    if choice not in match["choices"]:
        print(f"'{choice}' is not one of the offered choices for {decision_id}: "
              f"{', '.join(match['choices'])}.", file=sys.stderr)
        return 3
    if choice == "split":
        if match["kind"] != "checkability":
            print(f"'split' applies only to a requirement statement; {decision_id} is a "
                  f"{match['kind']} ruling — its choices are {', '.join(c for c in match['choices'] if c != 'split')}.",
                  file=sys.stderr)
            return 3
        if not reader_command:
            print("'split' spends readers to confirm each duty and vote its checkability — pass "
                  "--reader-command with the projection's reader.", file=sys.stderr)
            return 3
        return _split_bundle(state, work, target, decision_id, match, choice, because,
                             reader_command)
    state.pop("_work", None)
    shown = state.get("owner_assessments", {}).get(target, {}).get(decision_id)
    ruling = {"item": match, "choice": choice, "because": because or "",
              "assessment_shown": shown, "at": time.time()}
    prior = state.get("owner_rulings", {}).get(target, {}).get(decision_id)
    if prior is not None:
        history = list(prior.get("history") or [])
        history.append({k: v for k, v in prior.items() if k != "history"})
        ruling["history"] = history
    state.setdefault("owner_rulings", {}).setdefault(target, {})[decision_id] = ruling
    _write(work, state)
    remaining = len(queue) - 1
    print(f"recorded: {decision_id} -> {choice}" + (f" ({because})" if because else "")
          + f"; {remaining} ruling(s) still pending")
    return 0


def correct_owner(work, decision_id, choice, because):
    """Correct one recorded non-split owner ruling without reopening or hand-editing state."""
    state = _read(work)
    target = _last_target(state)
    rulings = state.get("owner_rulings", {}).get(target, {})
    prior = rulings.get(decision_id)
    if prior is None:
        print(f"'{decision_id}' is not a recorded owner ruling. correct-owner accepts only an "
              "existing recorded non-split ruling; use answer-owner for a pending id.",
              file=sys.stderr)
        return 3
    if prior.get("choice") == "split" or prior.get("split_graph") is not None:
        print(f"'{decision_id}' is a recorded split ruling. correct-owner cannot change a split "
              "graph or its children; use replay-owner-split for that exact split.",
              file=sys.stderr)
        return 3
    item = prior.get("item") or {}
    choices = item.get("choices") or []
    if choice not in choices or choice == "split":
        offered = ", ".join(c for c in choices if c != "split") or "none"
        print(f"'{choice}' is not a permitted non-split correction for {decision_id}. Choose "
              f"one of the ruling's originally offered non-split choices: {offered}.",
              file=sys.stderr)
        return 3
    history = list(prior.get("history") or [])
    history.append({key: value for key, value in prior.items() if key != "history"})
    ruling = {
        "item": item,
        "choice": choice,
        "because": because or "",
        "assessment_shown": prior.get("assessment_shown"),
        "at": time.time(),
        "history": history,
    }
    rulings[decision_id] = ruling
    _write(work, state)
    print(f"corrected: {decision_id} -> {choice}" +
          (f" ({because})" if because else "") +
          f"; prior ruling preserved in history ({len(history)} entr{'y' if len(history) == 1 else 'ies'})")
    return 0


def replay_owner_split(work, decision_id, reader_command):
    """Rebuild one recorded terminal split without disturbing any other paid run state.

    Replay is intentionally narrower than correction: only the newest split may be replayed,
    and its graph must identify a contiguous suffix. That makes every removed child attributable
    to the one ruling and avoids reindexing unrelated split graphs.
    """
    state = _read(work)
    target = _last_target(state)
    ruling = state.get("owner_rulings", {}).get(target, {}).get(decision_id)
    if not isinstance(ruling, dict) or ruling.get("choice") != "split":
        print(f"refused: {decision_id} is not one recorded split ruling", file=sys.stderr)
        return 3
    graph = ruling.get("split_graph")
    if not isinstance(graph, dict) or graph.get("decision_id") != decision_id:
        print(f"refused: {decision_id} has no matching integrity-bound split graph",
              file=sys.stderr)
        return 3
    items = state["distilled"][target]["items"]
    child_indexes = graph.get("child_indexes")
    parent_index = graph.get("parent_index")
    if (not isinstance(child_indexes, list) or not child_indexes
            or child_indexes != list(range(len(items) - len(child_indexes), len(items)))):
        print(f"refused: {decision_id} is not the terminal split; replay would move unrelated "
              "item indexes", file=sys.stderr)
        return 3
    if (not isinstance(parent_index, int) or parent_index < 0 or parent_index >= len(items)
            or any(items[index].get("split_from") != decision_id for index in child_indexes)):
        print(f"refused: {decision_id} split graph does not identify its exact parent and children",
              file=sys.stderr)
        return 3
    candidate = json.loads(json.dumps(state))
    candidate_items = candidate["distilled"][target]["items"]
    del candidate_items[child_indexes[0]:]
    parent = candidate_items[parent_index]
    parent["how"] = "pen"
    parent.pop("split_into", None)
    del candidate["owner_rulings"][target][decision_id]
    return _split_bundle(candidate, work, target, decision_id, ruling["item"], "split",
                         ruling.get("because", ""), reader_command,
                         reopen_on_conservation_refusal=True)


FINAL_CONSOLIDATION_POLICY = "final-semantic-v1"


def _merge_kept_item_lineage(prior, item):
    prior["pages"] = sorted(set(prior.get("pages") or []) | set(item.get("pages") or []))
    prior["anchors"] = list(dict.fromkeys(
        (prior.get("anchors") or []) + (item.get("anchors") or [])
    ))
    notes = [note for note in (prior.get("_kept_by_owner"), item.get("_kept_by_owner"))
             if note]
    if notes:
        prior["_kept_by_owner"] = "; ".join(dict.fromkeys(notes))
    materialized = []
    for candidate in (prior, item):
        materialized.extend(candidate.get("_materialized_source_duties") or [])
        if candidate.get("_materialized_source_duty"):
            materialized.append(candidate["_materialized_source_duty"])
    if materialized:
        prior["_materialized_source_duties"] = list(dict.fromkeys(materialized))


def _consolidate_kept_items(items, reflow_mod, same_rule_pairs=(), distinct_pairs=()):
    """Materialize an identical kept duty once while retaining all of its lineage."""
    consolidated, by_statement, by_single_anchor = [], {}, {}
    same_rule_pairs = set(same_rule_pairs)
    distinct_pairs = set(distinct_pairs)
    for item in items:
        if item.get("_drop") or item.get("how") == "refused" or not item.get("statement"):
            consolidated.append(item)
            continue
        identity = reflow_mod.flow(item["statement"])
        prior = by_statement.get(identity)
        source_duty = item.get("_materialized_source_duty")
        source_identity = reflow_mod.flow(source_duty) if source_duty else None
        if prior is None and source_identity:
            prior = by_single_anchor.get(source_identity)
        if prior is None and source_identity:
            for candidate in consolidated:
                if candidate.get("_drop") or candidate.get("how") == "refused":
                    continue
                anchors = [reflow_mod.flow(anchor) for anchor in candidate.get("anchors") or []]
                direct = any(
                    frozenset((source_identity, anchor)) in same_rule_pairs
                    and frozenset((source_identity, anchor)) not in distinct_pairs
                    for anchor in anchors if anchor != source_identity
                )
                represented_inside_family = (
                    source_identity in anchors
                    and any(frozenset((source_identity, anchor)) in same_rule_pairs
                            and frozenset((source_identity, anchor)) not in distinct_pairs
                            for anchor in anchors if anchor != source_identity)
                )
                if direct or represented_inside_family:
                    prior = candidate
                    break
        if prior is None:
            by_statement[identity] = item
            consolidated.append(item)
            anchors = item.get("anchors") or []
            if len(anchors) == 1:
                by_single_anchor.setdefault(reflow_mod.flow(anchors[0]), item)
            continue
        _merge_kept_item_lineage(prior, item)
    return consolidated


_FINAL_SEMANTIC_STOPWORDS = {
    "about", "after", "again", "against", "along", "also", "because", "before", "being",
    "between", "carry", "could", "every", "first", "from", "have", "into", "itself",
    "never", "other", "rather", "should", "their", "there", "these", "they", "this",
    "through", "under", "when", "where", "which", "while", "with", "without", "would",
}


def _final_semantic_tokens(text):
    return {word for word in re.findall(r"[a-z0-9]+", text.lower())
            if len(word) >= 5 and word not in _FINAL_SEMANTIC_STOPWORDS}


def _has_materialized_lineage(item):
    return bool(item.get("_materialized_source_duty")
                or item.get("_materialized_source_duties"))


def _canonical_final_pair(pair):
    if (not isinstance(pair, (list, tuple)) or len(pair) != 2
            or any(type(value) is not int or value < 1 for value in pair)
            or pair[0] == pair[1]):
        raise ValueError(f"invalid final semantic pair: {pair!r}")
    return tuple(sorted(pair))


def _final_pair_record(pair, left, right, pages):
    pair = _canonical_final_pair(pair)
    digest = hashlib.sha256((left + "||" + right).encode()).hexdigest()[:8]
    return {
        "id": f"final-pair-{digest}", "pair": list(pair), "a": left, "b": right,
        "pages": sorted(set(pages)),
    }


def _normalize_final_semantic_record(record, rulings):
    """Make unordered pair identity stable and let an owner gate override a merge."""
    owner_by_pair, id_map = {}, {}
    for stored in record.get("owner_pairs", []):
        original = tuple(stored["pair"])
        canonical = _canonical_final_pair(original)
        left, right = stored["a"], stored["b"]
        if original != canonical:
            left, right = right, left
        normalized = _final_pair_record(canonical, left, right, stored.get("pages") or [])
        owner_by_pair.setdefault(canonical, normalized)
        id_map[stored["id"]] = normalized["id"]
    owner_pairs = set(owner_by_pair)
    merged = sorted({_canonical_final_pair(pair) for pair in record.get("merged", [])}
                    - owner_pairs)
    normalized_owner = [owner_by_pair[pair] for pair in sorted(owner_by_pair)]
    changed = (record.get("merged") != [list(pair) for pair in merged]
               or record.get("owner_pairs") != normalized_owner)
    record["merged"] = [list(pair) for pair in merged]
    record["owner_pairs"] = normalized_owner
    for old_id, new_id in id_map.items():
        if old_id == new_id or old_id not in rulings:
            continue
        previous = rulings[old_id]
        if new_id in rulings and rulings[new_id].get("choice") != previous.get("choice"):
            raise ValueError(f"conflicting rulings for unordered final pair {new_id}")
        if new_id not in rulings:
            moved = dict(previous)
            item = dict(moved.get("item") or {})
            item["id"] = new_id
            moved["item"] = item
            rulings[new_id] = moved
        del rulings[old_id]
        changed = True
    return changed


def _is_recorded_distinct(left, right, distinct_pairs, reflow_mod):
    left_anchors = [reflow_mod.flow(value) for value in left.get("anchors") or []]
    right_anchors = [reflow_mod.flow(value) for value in right.get("anchors") or []]
    return any(frozenset((a, b)) in distinct_pairs
               for a in left_anchors for b in right_anchors if a != b)


def _final_semantic_candidates(items, dedupe_mod, reflow_mod, distinct_pairs):
    """Bound the final meaning pass to textual proof or owner-materialized, source-local pairs."""
    kept = [item for item in items
            if not item.get("_drop") and item.get("how") != "refused" and item.get("statement")]
    automatic, reader = [], []
    for left_number in range(1, len(kept) + 1):
        for right_number in range(left_number + 1, len(kept) + 1):
            left, right = kept[left_number - 1], kept[right_number - 1]
            if _is_recorded_distinct(left, right, distinct_pairs, reflow_mod):
                continue
            if dedupe_mod.code_merges(left["statement"], right["statement"]):
                automatic.append((left_number, right_number))
                continue
            source_local = bool(set(left.get("pages") or []) & set(right.get("pages") or []))
            shared_terms = (_final_semantic_tokens(left["statement"])
                            & _final_semantic_tokens(right["statement"]))
            if ((_has_materialized_lineage(left) or _has_materialized_lineage(right))
                    and source_local and len(shared_terms) >= 2):
                reader.append((left_number, right_number))
    return kept, automatic, reader


def _read_final_semantic_pair(dedupe_mod, reader_command, left, right, pair):
    votes = []
    for _ in range(dedupe_mod.ASKS):
        raw = dedupe_mod.interview.ask_free(
            reader_command,
            dedupe_mod.ASK.format(a=left, b=right),
            stage="final-semantic-dedupe",
            piece=f"{pair[0]}-{pair[1]}",
        )
        answer = next((re.sub(r"[^A-Z]", "", line.upper())
                       for line in raw.split("\n")
                       if re.sub(r"[^A-Z]", "", line.upper()) in ("YES", "NO")), None)
        votes.append(answer)
    return votes, dedupe_mod.verdict(votes, dedupe_mod.cover(left, right))


def _final_semantic_consolidate(items, state, target, work, reader_command, reflow_mod,
                                distinct_pairs):
    """Run and persist the last meaning check after every owner ruling has materialized."""
    dedupe_mod = _load("dedupe")
    lineage_mod = _load("rule_lineage")
    kept, automatic, reader_pairs = _final_semantic_candidates(
        items, dedupe_mod, reflow_mod, distinct_pairs)
    print(f"final semantic consolidation: {len(automatic)} code-proven pair(s), "
          f"{len(reader_pairs)} bounded reader pair(s)", flush=True)
    signature_payload = {
        "policy": FINAL_CONSOLIDATION_POLICY,
        "items": [{"statement": item["statement"], "pages": sorted(item.get("pages") or []),
                   "anchors": item.get("anchors") or [],
                   # Candidate eligibility depends only on whether owner-materialized lineage
                   # exists. Its incidental representative text can vary with persisted mapping
                   # order while statements, pairs, and every reader verdict remain identical.
                   "materialized": _has_materialized_lineage(item)}
                  for item in kept],
        "automatic": automatic,
        "reader_pairs": reader_pairs,
    }
    signature = _canonical_sha256(signature_payload)
    prepared = (state.setdefault("document_preparation", {}).setdefault(target, {})
                .setdefault("final_semantic", {}))
    record = prepared.get(signature)
    if record is None:
        if reader_pairs and not reader_command:
            print("cannot write the document: final semantic consolidation needs the configured "
                  "blind reader", file=sys.stderr)
            return None
        merged = {_canonical_final_pair(pair) for pair in automatic}
        owner, detail = set(), [
            {"pair": list(pair), "by": "code", "verdict": "merge"}
            for pair in automatic
        ]
        for pair in reader_pairs:
            left, right = (kept[pair[0] - 1]["statement"], kept[pair[1] - 1]["statement"])
            votes, verdict = _read_final_semantic_pair(
                dedupe_mod, reader_command, left, right, pair)
            if verdict == "merge":
                merged.add(_canonical_final_pair(pair))
            elif verdict == "owner":
                owner.add(_canonical_final_pair(pair))
            detail.append({"pair": list(pair), "by": "reader", "votes": votes,
                           "cover": round(dedupe_mod.cover(left, right), 2),
                           "verdict": verdict})
        reduction = lineage_mod.reduce(
            [{"text": item["statement"], "pages": item.get("pages") or []}
             for item in kept], sorted(merged))
        owner.update(_canonical_final_pair(pair) for pair in reduction["owner_pairs"])
        safe_merged = sorted(merged - owner)
        pair_records = []
        for left_number, right_number in sorted(owner):
            left, right = kept[left_number - 1], kept[right_number - 1]
            pair_records.append(_final_pair_record(
                (left_number, right_number), left["statement"], right["statement"],
                set(left.get("pages") or []) | set(right.get("pages") or [])))
        record = {"signature": signature, "merged": [list(pair) for pair in safe_merged],
                  "owner_pairs": pair_records, "detail": detail, "policy": FINAL_CONSOLIDATION_POLICY,
                  "at": time.time()}
        prepared[signature] = record
        prepared["active_signature"] = signature
        _write(work, state)
    elif prepared.get("active_signature") != signature:
        prepared["active_signature"] = signature
        _write(work, state)

    rulings = state.get("owner_rulings", {}).get(target, {})
    if _normalize_final_semantic_record(record, rulings):
        _write(work, state)
    unresolved = [pair for pair in record["owner_pairs"] if pair["id"] not in rulings]
    if unresolved:
        print(f"cannot write the document: {len(unresolved)} final semantic ruling(s) still "
              "pending — run `cover.py ask-owner` and answer them first.", file=sys.stderr)
        return None
    merged = {_canonical_final_pair(pair) for pair in record["merged"]}
    merged.update(_canonical_final_pair(pair["pair"]) for pair in record["owner_pairs"]
                  if rulings[pair["id"]]["choice"] == "merge")
    reduction = lineage_mod.reduce(
        [{"text": item["statement"], "pages": item.get("pages") or []}
         for item in kept], sorted(merged), ratio_limit=10 ** 9)
    if reduction["owner_pairs"]:
        print("cannot write the document: a final semantic merge still crosses a scale gap",
              file=sys.stderr)
        return None
    survivors = []
    for component in reduction["components"]:
        keeper = kept[component["keeper_rule_id"] - 1]
        for member_number in component["member_rule_ids"]:
            member = kept[member_number - 1]
            if member is not keeper:
                _merge_kept_item_lineage(keeper, member)
        survivors.append((min(component["member_rule_ids"]), keeper))
    kept_ids = {id(item) for item in kept}
    untouched = [item for item in items if id(item) not in kept_ids]
    return untouched + [item for _, item in sorted(survivors)]


def document(work, out_path, reader_command=None):
    """The finished requirements document, written by the machinery with every owner ruling
    applied. Refuses while any ruling is still pending — a document over an unanswered question
    would look complete and be one decision short of the truth."""
    state = _read(work)
    try:
        _rebuild(state).report()
    except register.Incomplete as refusal:
        print(f"cannot write the document: {refusal}", file=sys.stderr)
        return 3
    state["_work"] = work
    target = _last_target(state)
    queue = _owner_queue(state, target)
    if queue is None:
        print(f"no distilled record in {work}. Run `cover.py distill` first.", file=sys.stderr)
        return 3
    if queue:
        print(f"cannot write the document: {len(queue)} ruling(s) still pending — run "
              f"`cover.py ask-owner` and answer them first.", file=sys.stderr)
        return 3
    state.pop("_work", None)
    d = state["distilled"][target]
    rulings = state.get("owner_rulings", {}).get(target, {})
    reflow_mod = _load("reflow")
    items = [dict(o) for o in d["items"]]
    dropped, notes = [], []
    # checkability rulings
    for rid, r in rulings.items():
        if r["item"]["kind"] != "checkability":
            continue
        idx = int(rid.split("-")[1]) - 1
        if r["choice"] == "drop":
            items[idx]["_drop"] = f"dropped by the owner: {r['because']}"
        elif r["choice"] == "split":
            items[idx]["_drop"] = (f"split by the owner into its separate duties "
                                   f"({r.get('children', 0)} entered): {r['because']}")
        else:
            items[idx]["_kept_by_owner"] = r["because"]
    # unsettled-piece rulings
    for rid, r in rulings.items():
        if r["item"]["kind"] != "unsettled-piece":
            continue
        pid = rid.replace("piece-", "")
        if r["choice"] == "dismiss":
            for it in items:
                if it["pages"] == [pid]:
                    it["_drop"] = f"its page was dismissed by the owner: {r['because']}"
        else:
            notes.append(f"page {pid} admitted by the owner: {r['because']}")
    # First-stage source-pair rulings. Both statements already reached the distilled list; merge
    # combines their provenance and removes exactly one, while keep-separate leaves both intact.
    for rid, r in rulings.items():
        if r["item"]["kind"] != "source-overlap" or r["choice"] != "merge":
            continue
        sides = [r["item"]["a"], r["item"]["b"]]
        matched = [index for index, item in enumerate(items)
                   if any(side in item.get("anchors", []) for side in sides)]
        if len(matched) != 2:
            print(f"cannot apply {rid}: its two source statements no longer map to exactly two "
                  f"distilled items", file=sys.stderr)
            return 3
        keep_index, drop_index = sorted(matched, key=lambda n: len(items[n].get("statement") or ""),
                                        reverse=True)
        items[keep_index]["pages"] = sorted(set(items[keep_index]["pages"])
                                             | set(items[drop_index]["pages"]))
        items[keep_index]["_kept_by_owner"] = f"merged by ruling {rid}: {r['because']}"
        items[drop_index]["_drop"] = f"merged with its paired statement by the owner: {r['because']}"
    # A failed shared-rule extraction consumed neither source. The owner's ruling materializes
    # one or both originals verbatim, so every supported choice is nonempty and traceable.
    for rid, r in rulings.items():
        if r["item"]["kind"] != "shared-rule":
            continue
        selected = (("a", "b") if r["choice"] == "keep-both"
                    else (("a",) if r["choice"] == "select-a"
                          else (("b",) if r["choice"] == "select-b" else ())))
        page_by_side = {"a": r["item"]["a_piece"], "b": r["item"]["b_piece"]}
        for side in selected:
            items.append({
                "pages": [page_by_side[side]], "statement": r["item"][side],
                "anchors": [r["item"][side]], "how": "verbatim", "checkable": True,
                "_materialized_source_duty": r["item"][side],
                "_kept_by_owner": f"selected by ruling {rid}: {r['because']}",
            })
    # keep-separate rulings resurrect a rule the merge had folded away, verbatim from the register
    rules_register = state["requirements"][target]["rules_stage"]["rules"]
    col_rows = state["collapse"][target]["entries"]
    present = " ".join((it.get("statement") or "") for it in items)
    # A side is resurrected only when its rule is genuinely absent: a side that equals a kept
    # item's anchor is already carried in that item's penned form, and twin wordings the rule
    # judgement merged are one rule and get one line. The first assembly skipped both checks and
    # re-introduced four duplicates the whole build existed to remove.
    # Represented means represented: a side is covered only when it is the SOLE anchor of a
    # kept item (that item is its penned form) or its words appear inside a kept statement.
    # Membership in a multi-anchor family is not coverage — the first fix used it and silently
    # deleted the HARD STOP gate's completeness conditions, which the owner had explicitly ruled
    # onto its own line: a family statement is not obliged to carry every anchor's content, only
    # to invent nothing.
    kept_anchor_texts = {reflow_mod.flow((it.get("anchors") or [""])[0])
                         for it in items
                         if not it.get("_drop") and len(it.get("anchors") or []) == 1}
    kept_statements = " ".join(reflow_mod.flow(it.get("statement") or "")
                               for it in items if not it.get("_drop"))
    twin_of = {}
    rj = state["requirements"][target].get("rule_judgement", {})
    rule_texts = rj.get("texts", [])
    for a_i, b_i in rj.get("merged", []):
        if a_i <= len(rule_texts) and b_i <= len(rule_texts):
            twin_of[reflow_mod.flow(rule_texts[b_i - 1])] = reflow_mod.flow(rule_texts[a_i - 1])
    resurrected = {}
    for rid, r in rulings.items():
        if r["item"]["kind"] != "overlap" or r["choice"] not in (
                "keep-separate", "select-a", "select-b"):
            continue
        selected_names = (("a", "b") if r["choice"] == "keep-separate"
                          else (("a",) if r["choice"] == "select-a" else ("b",)))
        for side in (r["item"].get(name) for name in selected_names):
            if not side:
                continue
            flowed = reflow_mod.flow(side)
            canonical = twin_of.get(flowed, flowed)
            if flowed in kept_anchor_texts or flowed in kept_statements:
                continue          # its penned form, or a statement, already carries this rule
            rule = next((x for x in rules_register if x["text"] == side), None)
            if rule is None:
                continue
            pages = sorted({col_rows[n - 1]["piece"] for n in rule["entries"]})
            note = f"kept separate by ruling {rid}: {r['because']}"
            if canonical in resurrected:
                prev = resurrected[canonical]
                prev["pages"] = sorted(set(prev["pages"]) | set(pages))
                if len(side) > len(prev["statement"]):
                    prev["statement"] = side
                continue
            resurrected[canonical] = {"pages": pages, "statement": side, "how": "verbatim",
                                      "checkable": True, "_materialized_source_duty": side,
                                      "_kept_by_owner": note}
    # A resurrected side is verbatim and can carry the page layout's damage ("Quality gate
    # (three Measurement gate: ..."). One pen pass cleans it: the gate blocks additions, and
    # removing a layout artifact is allowed. Verbatim stands when no reader command is given or
    # the pen fails.
    if reader_command:
        distill_mod = _load("distill")
        prepared = (state.setdefault("document_preparation", {}).setdefault(target, {})
                    .setdefault("resurrected", {}))
        legacy_pre_controller = not isinstance(state.get("self_sustained_run"), dict)
        for entry in resurrected.values():
            source_statement = entry["statement"]
            preparation_id = _canonical_sha256({
                "statement": source_statement, "pages": sorted(entry["pages"]),
            })
            recorded = prepared.get(preparation_id)
            if (isinstance(recorded, dict)
                    and recorded.get("source_statement") == source_statement
                    and recorded.get("pages") == sorted(entry["pages"])
                    and recorded.get("how") in ("pen", "verbatim")
                    and isinstance(recorded.get("statement"), str)):
                entry["how"] = recorded["how"]
                entry["statement"] = recorded["statement"]
                continue
            if legacy_pre_controller:
                written, transcript = None, [{
                    "compatibility": "pre-controller-verbatim",
                    "removal_condition": "all pre-controller runs have rendered or migrated",
                }]
                _controller_feed(
                    work, "controller compatibility", stage="document",
                    transition="pre-controller-verbatim", status="completed", target=target,
                    preparation_id=preparation_id,
                    removal_condition="all pre-controller runs have rendered or migrated")
            else:
                written, transcript = distill_mod.write_one(
                    [source_statement], reader_command, attempts=2, stage="document")
            entry["how"] = "pen" if written else "verbatim"
            entry["statement"] = written or source_statement
            prepared[preparation_id] = {
                "source_statement": source_statement,
                "pages": sorted(entry["pages"]),
                "how": entry["how"],
                "statement": entry["statement"],
                "transcript": transcript,
                "at": time.time(),
            }
            _write(work, state)
    items.extend(resurrected.values())
    # One selected source duty becomes one requirement even when several owner rulings select it.
    # Consolidate only kept, identical statements: distinct wording remains distinct, while pages,
    # anchors, and every owner-selection note remain traceable on the surviving item.
    same_rule_pairs = {
        frozenset((reflow_mod.flow(rule_texts[a_i - 1]),
                   reflow_mod.flow(rule_texts[b_i - 1])))
        for a_i, b_i in rj.get("merged", [])
        if a_i <= len(rule_texts) and b_i <= len(rule_texts)
    }
    same_rule_pairs.update(
        frozenset((reflow_mod.flow(r["item"]["a"]), reflow_mod.flow(r["item"]["b"])))
        for r in rulings.values()
        if r["item"].get("kind") == "overlap" and r.get("choice") == "merge"
    )
    distinct_pairs = {
        frozenset((reflow_mod.flow(r["item"]["a"]), reflow_mod.flow(r["item"]["b"])))
        for r in rulings.values()
        if r["item"].get("kind") in ("overlap", "source-overlap")
        and r.get("choice") == "keep-separate"
    }
    items = _consolidate_kept_items(items, reflow_mod, same_rule_pairs, distinct_pairs)
    items = _final_semantic_consolidate(
        items, state, target, work, reader_command, reflow_mod, distinct_pairs)
    if items is None:
        return 3
    lines = [f"# Requirements — {target}", "",
             f"Source of truth: {Path(state['source']).name}. Every",
             "requirement traces to the verbatim pages named beside it; statements were written by",
             "the machinery through a gate proving no word was added, and every doubtful item was",
             "ruled on by the owner in a recorded interview.", "", "## The requirements", ""]
    n = 0
    for it in items:
        if it.get("_drop") or it["how"] == "refused" or not it.get("statement"):
            continue
        n += 1
        pages = ", ".join(pg.replace("p-00", "p.").replace("p-0", "p.") for pg in it["pages"])
        lines.append(f"{n}. {it['statement']}  \n   *({pages})*")
        if it.get("_kept_by_owner"):
            lines.append(f"   — kept by the owner: {it['_kept_by_owner']}")
        lines.append("")
    lines += ["## Rejected, with reasons", ""]
    for it in items:
        if it.get("_drop"):
            reason = it["_drop"]
        elif it["how"] == "refused":
            named = (it.get("transcript") or [{}])[-1].get("refusal")
            reason = ("the pen refused it: " + named) if named else (
                "the pen could not produce a statement above the length floor — a fragment; "
                "recorded before the floor learned to name itself")
        else:
            reason = None
        if reason:
            src = (it.get("anchors") or [it.get("statement") or ""])[0][:90]
            lines.append(f"- {src!r} — {reason}")
    lines += ["", "## Owner rulings (recorded)", ""]
    for rid, r in sorted(rulings.items()):
        lines.append(f"- {rid}: {r['choice']} — {r['because']}")
    Path(out_path).write_text("\n".join(lines))
    print(f"document written: {out_path} — {n} requirements, "
          f"{sum(1 for it in items if it.get('_drop') or it['how'] == 'refused')} rejected with "
          f"reasons, {len(rulings)} rulings recorded inside")
    return 0


def obligation_list(work):
    """The obligations themselves — refused while any admitted piece has not been read.

    Same rule as everything else here. A list that is one piece short reads exactly like a whole
    one, and nothing in it would say so.
    """
    state = _read(work)
    target = _last_target(state)
    judged = _verdicts(state, target) if target else {}
    admitted = [p for p, row in judged.items() if row["verdict"] == "bears"]
    store = state.get("obligations", {}).get(target, {})
    # Three separate states, and the first version collapsed them into one wrong sentence: it
    # told an operator whose relevance pass had finished and admitted nothing that "no piece has
    # been judged relevant yet". Relevance had run. It had answered. The answer was none.
    if target is None or not judged:
        print(f"cannot list obligations: nothing has been judged for relevance in {work}. Run "
              f"`cover.py relevance --work {work} --target ... --reader-command ...` first.",
              file=sys.stderr)
        return 3
    unjudged = [p["id"] for p in state["pieces"] if p["id"] not in judged]
    if unjudged:
        print(f"cannot list obligations: {len(unjudged)} of {len(state['pieces'])} piece(s) have "
              f"no relevance verdict for {target!r}. Finish `cover.py relevance` first.",
              file=sys.stderr)
        return 3
    missing = [p for p in admitted if p not in store]
    if missing:
        print(f"cannot list obligations: {len(missing)} of {len(admitted)} admitted piece(s) have "
              f"not been read for obligations: {', '.join(sorted(missing)[:10])}. Run "
              f"`cover.py obligations --work {work} --reader-command ...`; it resumes where it "
              f"stopped.", file=sys.stderr)
        return 3

    # A piece the two readers split on is neither in nor out. The list is handed over anyway —
    # refusing would make one unsettled page withhold every settled one — but it carries the
    # unsettled pieces by name, because a list that could still grow must not read as final.
    relevance_mod = _load("relevance")
    pending = sorted(p for p, row in judged.items()
                     if row["verdict"] in (relevance_mod.FOR_THE_OWNER, relevance_mod.NOT_GROUNDED,
                                           relevance_mod.NO_ANSWER))
    out = {"target": target, "source": state["source"], "admitted_pieces": len(admitted),
           "obligations": {p: store[p]["obligations"] for p in sorted(admitted)},
           "total": sum(len(store[p]["obligations"]) for p in admitted),
           "not_settled": {p: store[p]["obligations"] for p in pending if p in store},
           "not_settled_without_obligations": [p for p in pending
                                               if p in store and not store[p]["obligations"]]}
    print(json.dumps(out, indent=1))
    if pending:
        print(f"\n{len(pending)} piece(s) are neither in nor out and are yours to settle: "
              f"{', '.join(pending)}. Admitting any of them adds to this list.", file=sys.stderr)
    return 0


def bearing(work):
    """The pieces that bear on the target — refused while any piece is unjudged.

    The relevance pass prints each verdict as it goes, and that is progress, not a result. Without
    this, a run stopped at piece 50 leaves a half-finished set in the state file that reads exactly
    like a finished one, which is the failure the register was built to make impossible. So the
    same rule applies to this answer as to every other: nothing comes out while any part of the
    source is unjudged.
    """
    relevance_mod = _load("relevance")
    state = _read(work)
    judged = _verdicts(state, _last_target(state))
    missing = [p["id"] for p in state["pieces"] if p["id"] not in judged]
    if missing:
        shown = ", ".join(missing[:10])
        more = f", and {len(missing) - 10} more" if len(missing) > 10 else ""
        print(f"cannot say what bears on the target: {len(missing)} of {len(state['pieces'])} "
              f"piece(s) unjudged: {shown}{more}. Run `cover.py relevance --work {work} "
              f"--target ... --reader-command ...`; it resumes where it stopped.", file=sys.stderr)
        return 3
    by = {}
    for piece_id, row in judged.items():
        by.setdefault(row["verdict"], []).append(piece_id)
    out = {"target": _last_target(state), "source": state["source"],
           "pieces": len(state["pieces"]),
           "bears": sorted(by.get(relevance_mod.BEARS, [])),
           "for_the_owner": sorted(by.get(relevance_mod.FOR_THE_OWNER, [])),
           "no_answer": sorted(by.get(relevance_mod.NO_ANSWER, [])),
           "yes_without_words": sorted(by.get(relevance_mod.NOT_GROUNDED, [])),
           "does_not_bear": len(by.get(relevance_mod.DOES_NOT, [])),
           "words": {pid: [s["quote"] for s in judged[pid]["seats"] if s["quote"]]
                     for pid in sorted(by.get(relevance_mod.BEARS, []))}}
    print(json.dumps(out, indent=1))
    return 0


def report(work):
    state = _read(work)
    reg = _rebuild(state)
    try:
        result = reg.report()
    except register.Incomplete as refusal:
        print(str(refusal), file=sys.stderr)
        return 3
    print(json.dumps({"source": state["source"], "pieces": len(state["pieces"]), **result,
                      "answers": reg.all_answers()}, indent=1))
    return 0


AUTOMATIC_STAGES = ("coverage", "relevance", "obligations", "collapse", "requirements", "distill")
DISTILLED_FINAL_FIELDS = {
    "items", "owner_pairs", "source_owner_pairs", "shared_rule_owner_records", "still_for_owner",
}


def _controller_feed(work, event, **fields):
    """Record code-owned stage selection and transitions beside reader-call telemetry."""
    path = os.environ.get("REQ_MACHINERY_FEED") or str(Path(work) / "feed.jsonl")
    try:
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(json.dumps({"at": round(time.time(), 1), "event": event, **fields}) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    except OSError:
        pass


def _next_stage_from_state(state, target, work=None):
    """Derive the only lawful next stage from durable machinery state."""
    if any(piece["id"] not in state["answers"] for piece in state["pieces"]):
        return "coverage"
    rows = (state.get("relevance", {}).get("targets", {}).get(target, {})
            .get("pieces", {}))
    piece_ids = [piece["id"] for piece in state["pieces"]]
    if any(piece_id not in rows for piece_id in piece_ids):
        return "relevance"
    expected_obligations = sorted(
        piece_id for piece_id, row in rows.items()
        if row.get("verdict") in ("bears", "for-the-owner", "yes-without-words", "no-answer")
    )
    completion = state.get("obligation_completion", {}).get(target, {})
    if (completion.get("complete") is not True
            or sorted(completion.get("piece_ids", [])) != expected_obligations):
        return "obligations"
    if target not in state.get("collapse", {}):
        return "collapse"
    requirements_state = state.get("requirements", {}).get(target, {})
    if not isinstance(requirements_state.get("items"), list):
        return "requirements"
    distilled = state.get("distilled", {}).get(target, {})
    if not DISTILLED_FINAL_FIELDS.issubset(distilled):
        return "distill"
    owner_state = dict(state)
    if work is not None:
        owner_state["_work"] = work
    return "owner" if _owner_queue(owner_state, target) else "document"


def run_automatic(work, target, out_path, reader_command):
    """Carry one persisted run until its next legitimate human or terminal boundary."""
    _pin_projection_runtime(work)
    handlers = {
        "coverage": lambda: cover_unanswered(work, reader_command),
        "relevance": lambda: relevance(work, target, reader_command),
        "obligations": lambda: obligations(work, reader_command),
        "collapse": lambda: collapse(work, reader_command),
        "requirements": lambda: requirements(work, reader_command),
        "distill": lambda: distill(work, reader_command),
    }
    started = time.monotonic()
    while True:
        state = _read(work)
        stage = _next_stage_from_state(state, target, work)
        if stage in AUTOMATIC_STAGES and not isinstance(state.get("self_sustained_run"), dict):
            state["self_sustained_run"] = {
                "schema_version": 1,
                "started_from": stage,
                "at": time.time(),
            }
            _write(work, state)
        _controller_feed(work, "controller stage", stage=stage, transition="selected",
                         attempt=1, elapsed_seconds=round(time.monotonic() - started, 3),
                         status="running", target=target)
        if stage == "owner":
            code = ask_owner(work, reader_command)
            _controller_feed(work, "controller stop", stage=stage,
                             transition="owner-decision-required", attempt=1,
                             elapsed_seconds=round(time.monotonic() - started, 3),
                             status="waiting-for-owner", target=target, exit_code=code)
            return code
        if stage == "document":
            code = document(work, out_path, reader_command)
            _controller_feed(work, "controller stop", stage=stage,
                             transition="completed", attempt=1,
                             elapsed_seconds=round(time.monotonic() - started, 3),
                             status="completed" if code == 0 else "error",
                             target=target, exit_code=code, output=str(out_path))
            return code
        code = handlers[stage]()
        if code != 0:
            _controller_feed(work, "controller stage", stage=stage, transition="failed",
                             attempt=1, elapsed_seconds=round(time.monotonic() - started, 3),
                             status="error", target=target, exit_code=code)
            return code
        next_stage = _next_stage_from_state(_read(work), target, work)
        if next_stage == stage:
            print(f"refused: stage {stage!r} returned success but durable state still selects it; "
                  "the stage must record its completion before the controller can continue.",
                  file=sys.stderr)
            _controller_feed(work, "controller stage", stage=stage,
                             transition="no-durable-progress", attempt=1,
                             elapsed_seconds=round(time.monotonic() - started, 3),
                             status="error", target=target, exit_code=3)
            return 3
        _controller_feed(work, "controller stage", stage=stage, transition="completed",
                         attempt=1, elapsed_seconds=round(time.monotonic() - started, 3),
                         status="completed", target=target, exit_code=0,
                         next_stage=next_stage)


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    o = sub.add_parser("open"); o.add_argument("--source", required=True); o.add_argument("--work", required=True)
    s = sub.add_parser("status"); s.add_argument("--work", required=True)
    a = sub.add_parser("answer"); a.add_argument("--work", required=True); a.add_argument("--piece", required=True)
    a.add_argument("--by", required=True); a.add_argument("--what", required=True)
    a.add_argument("--quote", required=True, help="words copied from the piece itself")
    v = sub.add_parser("relevance"); v.add_argument("--work", required=True)
    v.add_argument("--target", required=True); v.add_argument("--reader-command", required=True)
    g = sub.add_parser("obligations"); g.add_argument("--work", required=True)
    g.add_argument("--reader-command", required=True)
    ol = sub.add_parser("obligation-list"); ol.add_argument("--work", required=True)
    c = sub.add_parser("collapse"); c.add_argument("--work", required=True)
    c.add_argument("--reader-command", required=True)
    q = sub.add_parser("requirements"); q.add_argument("--work", required=True)
    q.add_argument("--reader-command", required=True)
    di = sub.add_parser("distill"); di.add_argument("--work", required=True)
    di.add_argument("--reader-command", required=True)
    ao = sub.add_parser("ask-owner"); ao.add_argument("--work", required=True)
    ao.add_argument("--reader-command", default=None)
    an = sub.add_parser("answer-owner"); an.add_argument("--work", required=True)
    an.add_argument("--id", required=True); an.add_argument("--choice", required=True)
    an.add_argument("--because", default=""); an.add_argument("--reader-command", default=None)
    correction = sub.add_parser("correct-owner"); correction.add_argument("--work", required=True)
    correction.add_argument("--id", required=True); correction.add_argument("--choice", required=True)
    correction.add_argument("--because", default="")
    replay = sub.add_parser("replay-owner-split"); replay.add_argument("--work", required=True)
    replay.add_argument("--id", required=True); replay.add_argument("--reader-command", required=True)
    doc = sub.add_parser("document"); doc.add_argument("--work", required=True)
    doc.add_argument("--out", required=True); doc.add_argument("--reader-command", default=None)
    b = sub.add_parser("bearing"); b.add_argument("--work", required=True)
    r = sub.add_parser("report"); r.add_argument("--work", required=True)
    run = sub.add_parser("run"); run.add_argument("--work", required=True)
    run.add_argument("--target", required=True); run.add_argument("--out", required=True)
    run.add_argument("--reader-command", required=True)
    return ap


def validate_work_path(work):
    """Return (resolved work, repository root), or refuse before state or readers are touched."""
    resolved = Path(work).expanduser().resolve(strict=False)
    temp_roots = {
        Path("/tmp").resolve(strict=False), Path("/private/tmp").resolve(strict=False),
        Path("/var/folders").resolve(strict=False),
        Path(os.environ.get("TMPDIR", "/nonexistent-temp-root")).resolve(strict=False),
    }
    temp_root = next((root for root in temp_roots
                      if resolved == root or root in resolved.parents), None)
    if temp_root is not None:
        raise ValueError(f"resolves inside temporary root {temp_root}")
    if resolved.exists() and not resolved.is_dir():
        raise ValueError("resolves to a file, not a work directory")
    probe = resolved if resolved.is_dir() else resolved.parent
    repository = None
    for candidate in (probe, *probe.parents):
        marker = candidate / ".git"
        if marker.is_dir() or marker.is_file():
            repository = candidate
            break
    if repository is None:
        raise ValueError("is not inside a recognized repository")
    if resolved == repository:
        raise ValueError(f"is the repository root {repository}, not a nested run directory")
    if repository not in resolved.parents:
        raise ValueError(f"escapes recognized repository {repository}")
    return resolved, repository


def main(argv=None):
    args = build_parser().parse_args(argv)
    reader_command = getattr(args, "reader_command", None)
    if reader_command:
        # Validate the invocation itself, not only a later process launch. Completed and resumed
        # paths may legitimately spend zero readers; policy must not become history-dependent.
        args.reader_command = _load("interview").validate_reader_command(reader_command)
    if getattr(args, "work", None):
        # A run's state is the record of every reader call it paid for. The Step 3 build kept its
        # run in the session scratchpad, and only a hand rescue at the end moved 281 calls' worth
        # of state into the repository — one flush away from gone. The owner's standing rule
        # (2026-08-24): every run persists in the repository. A work directory under a temp root
        # is refused with the fix named, before a single reader is spent.
        try:
            resolved, repository = validate_work_path(args.work)
        except ValueError as exc:
            print(f"--work {args.work} {exc}. A run's "
                  f"state is the paid record of its reader calls and must survive the session: "
                  f"put the work directory inside the repository, e.g. "
                  f"Tasks/<task>/runs/<run-name>, and re-run.", file=sys.stderr)
            return 3
        os.environ.setdefault("REQ_MACHINERY_FEED", str(Path(args.work) / "feed.jsonl"))
    try:
        return _dispatch(args)
    except Refused:
        return 3


def _dispatch(args):
    if args.command == "open":
        return open_document(args.source, args.work)
    if args.command == "status":
        return status(args.work)
    if args.command == "answer":
        return answer(args.work, args.piece, args.by, args.what, args.quote)
    if args.command == "relevance":
        return relevance(args.work, args.target, args.reader_command)
    if args.command == "obligations":
        return obligations(args.work, args.reader_command)
    if args.command == "obligation-list":
        return obligation_list(args.work)
    if args.command == "collapse":
        return collapse(args.work, args.reader_command)
    if args.command == "requirements":
        return requirements(args.work, args.reader_command)
    if args.command == "distill":
        return distill(args.work, args.reader_command)
    if args.command == "ask-owner":
        return ask_owner(args.work, args.reader_command)
    if args.command == "answer-owner":
        return answer_owner(args.work, args.id, args.choice, args.because,
                            args.reader_command)
    if args.command == "correct-owner":
        return correct_owner(args.work, args.id, args.choice, args.because)
    if args.command == "replay-owner-split":
        return replay_owner_split(args.work, args.id, args.reader_command)
    if args.command == "document":
        return document(args.work, args.out, args.reader_command)
    if args.command == "run":
        return run_automatic(args.work, args.target, args.out, args.reader_command)
    if args.command == "bearing":
        return bearing(args.work)
    return report(args.work)


if __name__ == "__main__":
    raise SystemExit(main())
